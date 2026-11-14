#!/usr/bin/env python3
"""
End-of-day signal_alerts reconciliation — Cloud Run Job.

Closes the gap from Track D audit § 2 / G.P0.10: ~1,209 historical alerts
have `exit_ts IS NULL` and 26 of 360 May-7 resolved alerts are stuck
`is_open=true` because the in-process exit-watcher in
`gcp/signal_monitor.py` only runs while the SignalMonitor process is
alive. If a position is still open at session close, the watcher exits
without resolving it. The schema docs anticipated an `eod_close` exit
reason but no implementation existed until this module.

This job runs once per session at 16:30 ET (20:30 UTC, after the close
+ a 30-min cushion for late-arriving intraday bars), scans for any
`signal_alerts` rows with `(is_open IS TRUE OR exit_ts IS NULL)` and
`alert_date < CURRENT_DATE`, replays `lib.indicators.calculate_rsi` +
the same exit-trigger logic from `SignalMonitor._check_exits` against
the day's `market_data_intraday` partition, and resolves each row to
the first triggered reason (target_hit / time_stop / rsi_extreme) or
falls back to `eod_close` if nothing fired before the session ended.

Architecture per CLAUDE.md §0:
- **Volume**: ~1,209 alerts × ~250 KB intraday window ≈ 300 MB peak
  working set during the one-shot backfill. Daily steady-state is ~1
  alert × 1 minute of bars ≈ negligible.
- **Velocity**: 1 SQL query per (ticker, day) covering the union of
  alert windows. Backfill against ~10 (ticker, day) pairs ≈ 10 queries.
- **Wall-clock**: ~10 queries × ~1.5 s pg8000 round-trip + per-row math
  ≈ ~5 min for the one-shot backfill; daily steady-state ~30 s.
- **Cloud Run task-timeout**: 1 hour (4× the 5-min wall-clock budget),
  set in the deploy script. max-retries=0 because the job is
  idempotent (`is_open IS FALSE` after the first successful run leaves
  no work for a retry) but transient retries don't help — the next
  scheduled run is the natural retry.
- **Idempotency**: every UPDATE flips `is_open=FALSE`; the next run's
  query filter excludes already-resolved rows. Re-running a partial
  failure converges, never duplicates.
- **Observability**: per-(ticker, day) progress log so a stuck job is
  debuggable, not a black box.
- **Resilience**: a missing intraday partition for one (ticker, day)
  logs a warning and skips that pair; the rest of the batch still
  resolves.

Usage:
    python -m gcp.signal_monitor_eod_resolver           # daily mode
    python -m gcp.signal_monitor_eod_resolver --backfill  # backfill mode
    python -m gcp.signal_monitor_eod_resolver --since 2026-04-01

The backfill flag is informational — both modes use the same query
predicate (`is_open IS TRUE OR exit_ts IS NULL`); --since narrows the
date range when the operator wants to re-process a known window.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.eastern_time import (
    ET,
    eastern_bounds_utc,
    eastern_index_to_utc,
    localize_assuming_utc,
    market_today,
    session_close,
)

import pandas as pd
import requests

from lib.config import load_config
from lib.data_loader import DataLoader
from lib.indicators import calculate_rsi


logger = logging.getLogger(__name__)
_ET = ET
# `eod_close` is written only when the day's stored bars reach this far before
# the session close. A day whose bars stop earlier (premarket only at 16:30 ET,
# a session the vendor served thin) has no known closing price: the alert is
# left unresolved rather than closed at whatever bar happens to be last.
EOD_CLOSE_REACH = timedelta(minutes=5)
# `av-intraday-nightly` (gcp/deploy.sh) writes a calendar day's own intraday
# partition at 21:00 ET. Before this, a same-day skip is the expected
# pre-ingestion race (see EODResolver._same_day_skip_is_benign); at or after
# it, tonight's fetch should already have landed, so a same-day skip is a
# real gap too (Codex P2 review, PR #745).
_INTRADAY_INGESTION_CUTOFF_ET = dt_time(21, 0)


def _exit_return_pct(direction: str, entry_price: float, exit_price: float) -> float:
    """Mirror of SignalMonitor._exit_return_pct — kept here so the resolver
    has no runtime dependency on a SignalMonitor instance (which would
    construct a watchlist + Discord webhook + AV client just to read one
    static method)."""
    if direction == 'CALL':
        return (exit_price - entry_price) / entry_price * 100.0
    return (entry_price - exit_price) / entry_price * 100.0


def _alert_day(alert_date):
    """`alert_date` as a calendar date: the column arrives as a date, an ISO
    string, or (from a grouped frame) a naive midnight timestamp."""
    if isinstance(alert_date, datetime):
        return alert_date.date()
    if isinstance(alert_date, str):
        return datetime.fromisoformat(alert_date).date()
    return alert_date


class EODResolver:
    """Replay exit logic against historical bars to close stuck alerts."""

    def __init__(self):
        cfg = load_config()
        self.exit_cfg = cfg.exit
        self.indicator_cfg = cfg.indicator
        self.loader = DataLoader(data_dir=cfg.market.data_dir)
        # Per-day (ticker, alert_date) → DataFrame cache. Reset per run.
        self._intraday_cache: dict[Tuple[str, str], pd.DataFrame] = {}
        # Post-close exits route to the dedicated signals channel when
        # configured; fall back to the main webhook otherwise.
        self.webhook_url = (
            os.environ.get('DISCORD_WEBHOOK_SIGNALS_URL')
            or os.environ.get('DISCORD_WEBHOOK_URL')
        )
        self.discord_timeout = cfg.monitor.discord_timeout

    # ── 1. Find unresolved alerts ─────────────────────────────────────

    def find_open_alerts(self, since: Optional[str] = None) -> pd.DataFrame:
        """Return rows of unresolved alerts up to and including today.

        Predicate is `alert_date <= CURRENT_DATE` so the daily 16:30 ET
        scheduled run actually closes the session it was scheduled for.
        Pre-fix this was `<` which skipped today's session entirely
        (Codex P1 review on PR #319): at 16:30 ET = 20:30 UTC,
        Postgres `CURRENT_DATE` is the same calendar day as the
        alerts being reconciled, so `<` excluded every same-day row
        and Friday alerts had to wait until Monday's run.

        Including today is safe because the in-process exit-watcher
        in signal_monitor.py exits at 16:00 ET; the 30-minute cushion
        before this resolver fires guarantees no race. The
        `is_open=FALSE` filter on individual rows ensures any row the
        live monitor already resolved is excluded.
        """
        from gcp.database import is_cloud_sql_configured, query_to_dataframe
        if not is_cloud_sql_configured():
            logger.error("Cloud SQL not configured — cannot run resolver")
            return pd.DataFrame()

        sql = """
            SELECT ticker, alert_ts, alert_date, direction,
                   price_at_signal, target_price, time_stop_minutes
              FROM signal_alerts
             WHERE (is_open IS TRUE OR exit_ts IS NULL)
               AND run_kind = 'live'
               AND alert_date <= CURRENT_DATE
        """
        params: dict = {}
        if since:
            sql += " AND alert_date >= :since"
            params['since'] = since
        sql += " ORDER BY alert_date, ticker, alert_ts"
        df = query_to_dataframe(sql, params)
        logger.info("Found %d unresolved alerts (since=%s)", len(df), since or "all")
        return df

    # ── 1b. Find closed alerts the resolver itself resolved ───────────

    # The alerts a bounded re-resolve may rewrite (--re-resolve). An exit this
    # job wrote sits on a whole minute: a bar's minute or the session close.
    # The live monitor's exit watcher stamps the clock, with microseconds, and
    # its exits are observations that the bars do not replace. The live trade
    # of each alert is read in the same query, so the stored exit of the trade
    # is known before anything is written.
    RESOLVED_ALERTS_SQL = """
        SELECT a.ticker, a.alert_ts, a.alert_date, a.direction, a.price_at_signal, a.target_price,
               a.time_stop_minutes, a.exit_ts, a.exit_reason, a.exit_price, a.exit_return_pct,
               a.exit_recompute_run,
               t.entry_time IS NOT NULL AS trade_found, t.exit_time AS trade_exit_time,
               t.exit_price AS trade_exit_price, t.exit_reason AS trade_exit_reason,
               t.return_pct AS trade_return_pct, t.exit_recompute_run AS trade_exit_recompute_run
          FROM signal_alerts a
          LEFT JOIN trades t
            ON t.ticker = a.ticker AND t.entry_time = a.alert_ts AND t.run_kind = 'live'
         WHERE a.run_kind = 'live' AND a.is_open IS FALSE AND a.exit_ts IS NOT NULL
           AND a.exit_ts = date_trunc('minute', a.exit_ts)
           AND a.ticker = ANY(:tickers) AND a.alert_date >= :first AND a.alert_date <= :last
         ORDER BY a.alert_date, a.ticker, a.alert_ts
    """

    def find_resolved_alerts(self, tickers: list[str], first, last) -> pd.DataFrame:
        """The closed live alerts of *tickers* in ``[first, last]`` whose exit
        this job wrote, each with its live trade's stored exit.

        One strict query: an outage raises and is never "nothing to do".
        """
        from gcp.database import query_to_dataframe_strict
        return query_to_dataframe_strict(
            self.RESOLVED_ALERTS_SQL, {"tickers": tickers, "first": first, "last": last})

    # ── 2. Replay exit logic per-bar ──────────────────────────────────

    def _load_day(self, ticker: str, alert_date) -> pd.DataFrame:
        """Load the (ticker, day) intraday partition with RSI precomputed.

        Cached per-run so multiple alerts on the same (ticker, day) don't
        re-fetch from Cloud SQL.
        """
        key = (ticker, str(alert_date))
        if key in self._intraday_cache:
            return self._intraday_cache[key]

        # Pull the full session window. DataLoader._load_intraday_from_sql
        # binds these as Postgres timestamp comparisons (`ts >= :start AND
        # ts <= :end`); a bare date string parses as midnight at the start
        # of that day, so passing the same date for both bounds matches
        # ZERO bars (Codex P1 review on PR #319). Use [00:00 of alert_date,
        # 00:00 of next day] to capture the full session.
        day = pd.Timestamp(alert_date)
        df = self.loader.load_intraday(
            ticker,
            start_date=day.isoformat(),
            end_date=(day + pd.Timedelta(days=1)).isoformat(),
        )
        if df.empty:
            logger.warning("no intraday partition for %s on %s", ticker, alert_date)
            self._intraday_cache[key] = df
            return df

        # The loader returns naive Eastern wall clock; alert_ts and the exit_ts
        # this job writes are naive UTC, so convert the bars to instants and
        # drop the (UTC) zone. Before #1185 the loader handed out the stored
        # clock unconverted, which is only UTC on true-UTC days.
        if 'Time' in df.columns:
            df = df.set_index('Time')
        df = df.sort_index()
        df.index = eastern_index_to_utc(df.index).tz_convert(None)

        # Precompute RSI once for the whole day; per-bar lookup is O(1).
        df[self.indicator_cfg.rsi_col] = calculate_rsi(
            df['Close'], self.indicator_cfg.rsi_period
        )
        self._intraday_cache[key] = df
        return df

    def _same_day_skip_is_benign(self, ticker: str, now_et: Optional[datetime] = None) -> bool:
        """Decide whether a same-day `_load_day` miss is the expected
        pre-ingestion race, or a real failure worth paging on.

        Two conditions both have to hold, per the Codex review on PR #745:

        1. **Timing (P2)** — tonight's `av-intraday-nightly` (21:00 ET)
           hasn't run yet. After that cutoff, today's own partition
           should already be written, so a same-day skip is a real gap
           too, not just an early-in-the-day race.
        2. **Read-path health (P1)** — `_query_cloud_sql`
           (lib/data_loader.py) swallows ANY exception — auth,
           connection, schema — into an empty DataFrame, so an empty
           same-day result is indistinguishable from a live Cloud SQL
           outage without an independent control query. We probe a
           trailing window that should already be fully ingested
           (yesterday and before); if that's ALSO empty, the read path
           itself is broken and this is a real failure, not "not
           ingested yet".
        """
        now_et = now_et or datetime.now(_ET)
        if now_et.time() >= _INTRADAY_INGESTION_CUTOFF_ET:
            return False
        return self._control_query_ok(ticker, as_of=now_et.date())

    def _control_query_ok(self, ticker: str, as_of) -> bool:
        """Confirm Cloud SQL intraday reads work at all for `ticker`, via
        a trailing window that should already be fully ingested (today is
        deliberately excluded — that's the thing under test)."""
        key = ('__control__', ticker)
        if key in self._intraday_cache:
            return not self._intraday_cache[key].empty
        end = pd.Timestamp(as_of)
        start = end - pd.Timedelta(days=6)
        df = self.loader.load_intraday(
            ticker, start_date=start.isoformat(), end_date=end.isoformat(),
        )
        self._intraday_cache[key] = df
        return not df.empty

    def _detect_exit(
        self,
        bar: pd.Series,
        elapsed_min: float,
        direction: str,
        target_price: float,
        time_stop_minutes: int,
    ) -> Optional[str]:
        """Return the exit reason this bar triggers, or None.

        Mirrors `SignalMonitor._check_exits` exactly so live-monitor and
        EOD-resolver semantics match. If they ever drift, signal_alerts
        rows resolved by the two paths are no longer comparable.
        """
        price = float(bar['Close'])
        rsi = float(bar.get(self.indicator_cfg.rsi_col, 0) or 0)

        is_call = direction == 'CALL'
        dir_mode = getattr(
            self.exit_cfg,
            'call_exit_mode' if is_call else 'put_exit_mode',
            'target_stop')
        if dir_mode == 'fixed_horizon':
            # Mirror of SignalMonitor._check_exits per-direction
            # fixed-horizon mode (audit 2026-08-25 §12) — hold exactly N
            # minutes, nothing else exits. Keep in lock-step with the
            # live monitor.
            horizon = (self.exit_cfg.call_fixed_horizon_minutes if is_call
                       else self.exit_cfg.put_fixed_horizon_minutes)
            if elapsed_min >= horizon:
                return 'fixed_horizon'
            return None

        if direction == 'CALL':
            if price >= target_price:
                return 'target_hit'
            if elapsed_min >= time_stop_minutes:
                return 'time_stop'
            if rsi >= self.exit_cfg.call_rsi_exit:
                return 'rsi_extreme'
        else:  # PUT
            if price <= target_price:
                return 'target_hit'
            if elapsed_min >= time_stop_minutes:
                return 'time_stop'
            if 0 < rsi <= self.exit_cfg.put_rsi_exit:
                return 'rsi_extreme'
        return None

    def resolve_one(self, alert: pd.Series,
                    bars: Optional[pd.DataFrame] = None) -> Optional[dict]:
        """Walk one alert's bar-by-bar history; return the resolution dict.

        The walk ends at the session close (`lib.eastern_time.session_close`:
        16:00 ET, 13:00 ET on a half day). A bar after the close is never an
        exit, and `eod_close` is the last bar before the close.

        `bars`, when given, is the day's frame as `_load_day` shapes it; the
        loader is then not called (the bounded re-resolve hands in a frame it
        read itself).

        Returns None when the day's intraday partition is missing, or when
        nothing triggered and the stored bars do not reach the last
        `EOD_CLOSE_REACH` before the close — the caller logs and continues to
        the next alert.
        """
        ticker = alert['ticker']
        alert_ts = pd.Timestamp(alert['alert_ts'])
        if alert_ts.tzinfo is not None:
            alert_ts = alert_ts.tz_localize(None)
        alert_date = alert['alert_date']
        direction = alert['direction']
        entry_price = float(alert['price_at_signal'])
        target_price = float(alert['target_price'])
        time_stop = int(alert['time_stop_minutes'] or 30)

        if bars is None:
            bars = self._load_day(ticker, alert_date)
        if bars.empty:
            return None

        # The day's frame holds premarket and after-hours bars too (the RSI is
        # computed over all of them). Only bars before the session close can
        # be an exit or price one.
        close_utc = pd.Timestamp(session_close(_alert_day(alert_date))).tz_convert(None)
        session = bars[bars.index < close_utc]

        # Walk only bars at or after the alert timestamp.
        forward = session[session.index >= alert_ts]
        if forward.empty:
            # Alert fired after the session's last logged bar (e.g. alert at
            # 15:59, AV's last bar is 15:58). Fall through to eod_close at
            # session close.
            return self._eod_close_resolution(
                alert, entry_price, alert_ts, alert_date, session,
            )

        for ts, bar in forward.iterrows():
            elapsed_min = (ts - alert_ts).total_seconds() / 60.0
            reason = self._detect_exit(
                bar, elapsed_min, direction, target_price, time_stop,
            )
            if reason:
                exit_price = float(bar['Close'])
                return {
                    'ticker': ticker,
                    'alert_ts': alert['alert_ts'],
                    'exit_ts': ts.to_pydatetime(),
                    'exit_reason': reason,
                    'exit_price': exit_price,
                    'exit_return_pct': _exit_return_pct(
                        direction, entry_price, exit_price
                    ),
                }

        # No trigger fired before the session close → eod_close at session close.
        return self._eod_close_resolution(
            alert, entry_price, alert_ts, alert_date, session,
        )

    def _eod_close_resolution(
        self,
        alert: pd.Series,
        entry_price: float,
        alert_ts: pd.Timestamp,
        alert_date,
        bars: pd.DataFrame,
    ) -> Optional[dict]:
        """Fall-back resolution: nothing fired before session close.

        `bars` holds the day's bars before the session close. The exit price
        is the close of the last of them (the value the position would have
        liquidated at) and exit_ts is the session close as naive UTC, so
        comparisons with alert_ts (naive UTC) align.

        Returns None when there is no such bar, or when the last one is more
        than `EOD_CLOSE_REACH` before the close: the closing price is not
        known from bars that stop early.
        """
        close_et = session_close(_alert_day(alert_date)).astimezone(_ET)
        close_utc_naive = close_et.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        if bars.empty or bars.index[-1] < close_utc_naive - EOD_CLOSE_REACH:
            return None
        last_bar = bars.iloc[-1]
        exit_price = float(last_bar['Close'])
        return {
            'ticker': alert['ticker'],
            'alert_ts': alert['alert_ts'],
            'exit_ts': close_utc_naive,
            'exit_reason': 'eod_close',
            'exit_price': exit_price,
            'exit_return_pct': _exit_return_pct(
                alert['direction'], entry_price, exit_price
            ),
        }

    # ── 3. Persist ────────────────────────────────────────────────────

    def persist(self, resolution: dict) -> int:
        """UPDATE the signal_alerts row AND mirror the exit onto trades.
        Returns the signal_alerts rowcount (1 on success, 0 on no-op).

        Idempotency: the signal_alerts UPDATE flips `is_open=FALSE` so
        the next run's query filter excludes the row, and the trades
        UPDATE is guarded by `exit_time IS NULL` so a recorded exit is
        never overwritten. Safe to re-run a partial batch.

        The trades row is matched on (ticker, entry_time == alert_ts):
        the entry path in signal_monitor._persist_signal_alert writes
        both timestamps from the SAME `now` value, and (ticker,
        entry_time) is the trades upsert conflict key — verified
        2071/2071 live rows since 2026-05-01 join exactly on it. Both
        UPDATEs share one transaction so the tables can't drift on a
        mid-write failure. A trades rowcount of 0 logs a WARNING per
        Rule 3.7 (no silent no-ops) — expected for pre-dual-write
        historical alerts that have no trades row at all.
        """
        from gcp.database import get_engine
        from sqlalchemy import text
        sql = text("""
            UPDATE signal_alerts
               SET exit_ts          = :exit_ts,
                   exit_reason      = :reason,
                   exit_price       = :price,
                   exit_return_pct  = :ret,
                   is_open          = FALSE
             WHERE ticker   = :ticker
               AND alert_ts = :alert_ts
               AND run_kind = 'live'
        """)
        # return_pct units: direction-aware underlying-move percent
        # (_exit_return_pct above) — same units as the pre-existing
        # closed trades rows and signal_alerts.exit_return_pct.
        trades_sql = text("""
            UPDATE trades
               SET exit_time   = :exit_ts,
                   exit_price  = :price,
                   exit_reason = :reason,
                   return_pct  = :ret
             WHERE ticker     = :ticker
               AND entry_time = :entry_time
               AND run_kind   = 'live'
               AND exit_time IS NULL
        """)
        with get_engine().begin() as conn:
            result = conn.execute(sql, {
                'exit_ts':  resolution['exit_ts'],
                'reason':   resolution['exit_reason'],
                'price':    resolution['exit_price'],
                'ret':      resolution['exit_return_pct'],
                'ticker':   resolution['ticker'],
                'alert_ts': resolution['alert_ts'],
            })
            trade_result = conn.execute(trades_sql, {
                'exit_ts':    resolution['exit_ts'],
                'reason':     resolution['exit_reason'],
                'price':      resolution['exit_price'],
                'ret':        resolution['exit_return_pct'],
                'ticker':     resolution['ticker'],
                'entry_time': resolution['alert_ts'],
            })
            if (trade_result.rowcount or 0) == 0:
                logger.warning(
                    "exit mirror matched no open trades row for %s "
                    "entry_time=%s reason=%s — row missing or already "
                    "closed; signal_alerts resolution still recorded",
                    resolution['ticker'], resolution['alert_ts'],
                    resolution['exit_reason'],
                )
            return result.rowcount or 0

    # ── 4. Discord digest ─────────────────────────────────────────────

    @staticmethod
    def build_digest_embed(resolved_exits: list[dict],
                           since: Optional[str]) -> dict:
        """Build a single summary embed for the run's resolved exits.

        One embed per run (not per exit) — the resolver closes a whole
        batch at once post-close, and a --backfill run can resolve
        hundreds of rows; individual messages would hit Discord's rate
        limit. The per-exit list is capped and sorted by |return| so the
        biggest movers always show.
        """
        by_reason: dict[str, int] = {}
        for ex in resolved_exits:
            by_reason[ex['exit_reason']] = by_reason.get(ex['exit_reason'], 0) + 1
        reason_summary = ' · '.join(f"{n} {r}" for r, n in sorted(by_reason.items()))

        n = len(resolved_exits)
        net = sum(ex['exit_return_pct'] for ex in resolved_exits)
        avg = net / n
        wins = sum(1 for ex in resolved_exits if ex['exit_return_pct'] > 0)

        cap = 25
        ranked = sorted(resolved_exits,
                        key=lambda e: abs(e['exit_return_pct']), reverse=True)
        lines = [
            f"{'🟢' if ex['exit_return_pct'] >= 0 else '🔴'} "
            f"**{ex['ticker']}** {ex['direction']} · {ex['exit_reason']} "
            f"· {ex['exit_return_pct']:+.2f}%"
            for ex in ranked[:cap]
        ]
        if n > cap:
            lines.append(f"_…and {n - cap} more_")

        return {
            'title': 'EOD Signal Resolution',
            'description': (
                f"Resolved **{n}** post-close {'exit' if n == 1 else 'exits'}"
                f"{f' (since {since})' if since else ''} — {reason_summary}\n"
                f"Win rate {wins}/{n} · avg {avg:+.2f}% · net {net:+.2f}%\n\n"
                + '\n'.join(lines)
            ),
            'color': 0x2ecc71 if net >= 0 else 0xe74c3c,
            'timestamp': datetime.now(ZoneInfo("UTC")).isoformat(),
        }

    def _post_digest(self, resolved_exits: list[dict],
                     since: Optional[str]) -> None:
        """POST the digest embed. No-op when nothing resolved or no
        webhook configured."""
        if not self.webhook_url or not resolved_exits:
            return
        embed = self.build_digest_embed(resolved_exits, since)
        try:
            requests.post(self.webhook_url, json={'embeds': [embed]},
                          timeout=self.discord_timeout)
            logger.info("EOD digest posted: %d exits", len(resolved_exits))
        except Exception as e:
            logger.warning("EOD digest Discord post failed: %s", e)

    # ── 4b. Bounded re-resolve (--re-resolve) ─────────────────────────

    # One (ticker, Eastern day) of stored bars, with the insert time that
    # proves each row. `interval` is named: the table also holds other bars.
    DAY_BARS_SQL = """
        SELECT ts, open, high, low, close, volume, inserted_at
          FROM market_data_intraday
         WHERE ticker = :t AND interval = '1min' AND ts >= :start AND ts < :end
         ORDER BY ts
    """

    EXIT_CSV_COLUMNS = ("exit_ts", "exit_reason", "exit_price", "exit_return_pct")
    _TRADE_EXIT_COLUMNS = ("exit_time", "exit_price", "exit_reason", "return_pct")
    _RESOLVE_INPUTS = ("price_at_signal", "target_price", "direction", "time_stop_minutes")

    def read_day_bars(self, ticker: str, day) -> pd.DataFrame:
        """The stored 1-minute bars of *ticker* on the Eastern day *day*,
        ``[D 00:00, D+1 00:00)`` as UTC instants: the window `_load_day`
        loads. One strict read; a failed read raises."""
        from gcp.database import query_to_dataframe_strict
        start, _ = eastern_bounds_utc(day, dt_time(0), dt_time(0))
        end, _ = eastern_bounds_utc(day + timedelta(days=1), dt_time(0), dt_time(0))
        return query_to_dataframe_strict(
            self.DAY_BARS_SQL, {"t": ticker, "start": start, "end": end})

    def day_frame(self, raw: pd.DataFrame) -> pd.DataFrame:
        """Shape a day of stored rows as `_load_day` shapes it: a naive UTC
        index and the RSI computed once over all of the day's bars.

        Each ``ts`` is taken as the instant it stores. The caller has checked
        that every row is proven, so nothing is placed by inference here, and
        a naive ``ts`` is not localized: it raises.
        """
        frame = pd.DataFrame({
            'Open': raw['open'].to_numpy(),
            'High': raw['high'].to_numpy(),
            'Low': raw['low'].to_numpy(),
            'Close': raw['close'].to_numpy(),
            'Volume': raw['volume'].to_numpy(),
        }, index=pd.DatetimeIndex(raw['ts']).tz_convert("UTC").tz_convert(None))
        frame.index.name = 'Time'
        frame = frame.sort_index()
        frame[self.indicator_cfg.rsi_col] = calculate_rsi(
            frame['Close'], self.indicator_cfg.rsi_period
        )
        return frame

    def _exit_configuration(self) -> dict:
        """The configuration that decides a re-resolved exit; each alert's own
        target and time stop come from its row."""
        return {
            'call_exit_mode': getattr(self.exit_cfg, 'call_exit_mode', 'target_stop'),
            'put_exit_mode': getattr(self.exit_cfg, 'put_exit_mode', 'target_stop'),
            'rsi_period': self.indicator_cfg.rsi_period,
            'call_rsi_exit': self.exit_cfg.call_rsi_exit,
            'put_rsi_exit': self.exit_cfg.put_rsi_exit,
        }

    def _re_resolve_group(self, ticker: str, day, group: pd.DataFrame, basis_fixed: dict):
        """Re-resolve the alerts of one (ticker, date) from that day's bars.

        Returns the report rows, one an alert, and the units to write.
        """
        from gcp import bar_recompute

        def stored_exit(record) -> dict:
            return {column: record[column] for column in self.EXIT_CSV_COLUMNS}

        def refused(status: str):
            return [bar_recompute.ReportRow(
                ticker=ticker, session_date=day,
                row_key=bar_recompute.json_value(record['alert_ts']),
                old=stored_exit(record), new=None, changed=None, status=status,
                bars_rows=None, bars_sha256=None)
                for record in group.to_dict('records')], []

        raw = self.read_day_bars(ticker, day)
        if raw.empty:
            return refused('no_bars')
        try:
            bar_recompute.require_proven(raw['ts'], raw['inserted_at'])
        except bar_recompute.UnprovenRows as unproven:
            logger.warning("%s %s: %s; every alert of the day is left", ticker, day, unproven)
            return refused('unproven_rows')

        frame = self.day_frame(raw)
        bars = bar_recompute.bars_basis(raw)
        basis = {'bars': bars, **basis_fixed}
        rows, units = [], []
        for _, alert in group.iterrows():
            row_key = bar_recompute.json_value(alert['alert_ts'])
            for column in self._RESOLVE_INPUTS:
                if pd.isna(alert[column]):
                    raise ValueError(
                        f"{ticker} alert {row_key} has no {column}; "
                        "its exit cannot be re-resolved")
            old = stored_exit(alert)
            resolution = self.resolve_one(alert, bars=frame)
            if resolution is None:
                rows.append(bar_recompute.ReportRow(
                    ticker=ticker, session_date=day, row_key=row_key, old=old, new=None,
                    changed=None, status='bars_incomplete',
                    bars_rows=bars['rows'], bars_sha256=bars['sha256']))
                continue
            new = {
                'exit_ts': localize_assuming_utc(
                    pd.Timestamp(resolution['exit_ts']).to_pydatetime()),
                'exit_reason': resolution['exit_reason'],
                'exit_price': resolution['exit_price'],
                'exit_return_pct': resolution['exit_return_pct'],
            }
            marker = alert['exit_recompute_run']
            changed, write = bar_recompute.decide(old, new, marker, self.EXIT_CSV_COLUMNS)

            status = 'recomputed'
            follower = None
            trade_old = {
                'exit_time': alert['trade_exit_time'],
                'exit_price': alert['trade_exit_price'],
                'exit_reason': alert['trade_exit_reason'],
                'return_pct': alert['trade_return_pct'],
            }
            if not bool(alert['trade_found']):
                status = 'trade_missing'
            elif not (bar_recompute.same(trade_old['exit_time'], old['exit_ts'])
                      and bar_recompute.same(trade_old['exit_price'], old['exit_price'])
                      and bar_recompute.same(trade_old['exit_reason'], old['exit_reason'])):
                # Someone changed the trade: it is no longer its alert's mirror.
                status = 'trade_diverged'
            else:
                trade_new = {
                    'exit_time': new['exit_ts'],
                    'exit_price': new['exit_price'],
                    'exit_reason': new['exit_reason'],
                    'return_pct': new['exit_return_pct'],
                }
                trade_changed, _ = bar_recompute.decide(
                    trade_old, trade_new, marker, self._TRADE_EXIT_COLUMNS)
                changed = changed or trade_changed
                write = write or trade_changed
                follower = bar_recompute.TableWrite(
                    spec=bar_recompute.TRADE_EXITS,
                    key={'ticker': ticker, 'entry_time': alert['alert_ts']},
                    old={**trade_old,
                         'exit_recompute_run': alert['trade_exit_recompute_run']},
                    new=trade_new)
            if not write and status != 'trade_diverged':
                status = 'already_current'
            rows.append(bar_recompute.ReportRow(
                ticker=ticker, session_date=day, row_key=row_key, old=old, new=new,
                changed=changed, status=status,
                bars_rows=bars['rows'], bars_sha256=bars['sha256']))
            if write:
                units.append(bar_recompute.WriteUnit(
                    ticker=ticker, session_date=day, row_key=row_key,
                    primary=bar_recompute.TableWrite(
                        spec=bar_recompute.ALERT_EXITS,
                        key={'ticker': ticker, 'alert_ts': alert['alert_ts']},
                        old={**old, 'exit_recompute_run': marker},
                        new=new),
                    follower=follower, changed=changed, basis=basis))
        return rows, units

    @staticmethod
    def _outcomes(rows) -> dict:
        """Per ticker and over all: the wins (`exit_return_pct > 0`) and the
        mean return before and after, over the selected rows. A row with no
        new value counts its stored one both times."""
        def measure(chosen) -> dict:
            before = [r.old.get('exit_return_pct') for r in chosen]
            after = [(r.new if r.new is not None else r.old).get('exit_return_pct')
                     for r in chosen]
            before = [float(v) for v in before if v is not None and not pd.isna(v)]
            after = [float(v) for v in after if v is not None and not pd.isna(v)]
            return {
                'alerts': len(chosen),
                'changed': sum(1 for r in chosen if r.changed),
                'wins_before': sum(1 for v in before if v > 0),
                'wins_after': sum(1 for v in after if v > 0),
                'mean_return_before': sum(before) / len(before) if before else None,
                'mean_return_after': sum(after) / len(after) if after else None,
            }

        outcomes = {}
        for ticker in sorted({r.ticker for r in rows}):
            outcomes[ticker] = measure([r for r in rows if r.ticker == ticker])
        outcomes['all'] = measure(list(rows))
        return {'outcomes': outcomes}

    def re_resolve(self, tickers: list[str], first, last, *, commit: bool,
                   run_id: str, report_dir: Optional[str]) -> int:
        """Re-resolve the resolver-written exits of *tickers* in
        ``[first, last]`` and return the exit code.

        One (ticker, date) at a time, with that day's bars in memory: one
        strict read of the bars, refused unless every row is proven a true UTC
        instant, then each alert through `resolve_one`, the function the
        scheduled path runs. No exit logic lives here, the loader is not used,
        and no digest is posted.
        """
        from gcp import bar_recompute

        if commit:
            raise NotImplementedError("the committed re-resolve is not written yet")
        alerts = self.find_resolved_alerts(tickers, first, last)
        logger.info("re-resolve %s..%s tickers=%s candidates=%d commit=%s run_id=%s",
                    first, last, " ".join(tickers), len(alerts), commit, run_id)
        configuration = self._exit_configuration()
        code = bar_recompute.code_version()
        basis_fixed = {'code': code, 'configuration': configuration}

        rows: list = []
        groups: list = []
        if not alerts.empty:
            for (day, ticker), group in alerts.groupby(['alert_date', 'ticker'], sort=False):
                group_rows, units = self._re_resolve_group(ticker, day, group, basis_fixed)
                computed = [r for r in group_rows if r.new is not None]
                logger.info(
                    "RECOMPUTE-EXITS %s %s candidates=%d changed=%d unchanged=%d refused=%d",
                    ticker, day, len(group_rows),
                    sum(1 for r in computed if r.changed),
                    sum(1 for r in computed if not r.changed),
                    len(group_rows) - len(computed))
                rows.extend(group_rows)
                groups.append((f"{ticker} {day}", units))

        summary = {
            'target': bar_recompute.TARGET_EXITS,
            'run_id': run_id,
            'arguments': {'tickers': list(tickers), 'from': str(first), 'to': str(last),
                          'commit': bool(commit)},
            'code_version': code,
            'configuration': configuration,
        }
        return bar_recompute.finish_run(
            target=bar_recompute.TARGET_EXITS, run_id=run_id, commit=False,
            action='recompute', rows=rows, groups=groups, summary=summary,
            csv_columns=self.EXIT_CSV_COLUMNS, report_dir=report_dir,
            summarize=self._outcomes)

    # ── 5. Orchestration ──────────────────────────────────────────────

    def run(self, since: Optional[str] = None) -> dict:
        """Top-level entry. Returns a per-reason count summary."""
        t0 = time.time()
        df = self.find_open_alerts(since=since)
        if df.empty:
            logger.info("nothing to resolve")
            return {'resolved': 0, 'skipped': 0, 'skipped_stale': 0, 'wall_clock_s': time.time() - t0}

        per_reason: dict[str, int] = {}
        resolved_exits: list[dict] = []
        skipped = 0
        # `av-intraday-nightly` (gcp/deploy.sh: `0 21 * * 2-6`) writes
        # TODAY's own intraday partition hours after this resolver's
        # 16:30 ET schedule (`signal-monitor-eod-resolver-daily`,
        # `30 16 * * 1-5`). A same-day alert still open at 16:30 ET
        # therefore hits an EXPECTED empty `_load_day` — it self-heals on
        # tomorrow's run once tonight's fetch lands (`alert_date <=
        # CURRENT_DATE` picks it back up). A skip for a PRIOR day (data
        # that already had a full night to land and still didn't), a
        # persist() exception, or a same-day skip past the ingestion
        # cutoff / with an unhealthy read path (see
        # `_same_day_skip_is_benign`) all indicate a genuine gap worth
        # paging on.
        skipped_stale = 0
        now_et = datetime.now(_ET)
        today_et = now_et.date()
        groups = df.groupby(['ticker', 'alert_date'])
        for (ticker, alert_date), group in groups:
            logger.info("ticker=%s date=%s alerts=%d", ticker, alert_date, len(group))
            for _, alert in group.iterrows():
                resolution = self.resolve_one(alert)
                if resolution is None:
                    skipped += 1
                    is_same_day = pd.Timestamp(alert_date).date() >= today_et
                    if not is_same_day or not self._same_day_skip_is_benign(ticker, now_et):
                        skipped_stale += 1
                    continue
                try:
                    n = self.persist(resolution)
                    if n:
                        per_reason[resolution['exit_reason']] = (
                            per_reason.get(resolution['exit_reason'], 0) + 1
                        )
                        resolved_exits.append({
                            'ticker': resolution['ticker'],
                            'direction': alert['direction'],
                            'exit_reason': resolution['exit_reason'],
                            'exit_return_pct': resolution['exit_return_pct'],
                        })
                except Exception as e:
                    logger.warning(
                        "persist failed for %s @%s: %s",
                        ticker, alert['alert_ts'], e,
                    )
                    skipped += 1
                    skipped_stale += 1  # DB write failure is a real bug, not
                    # a same-day data-not-yet-landed race — always hard-fail.

        self._post_digest(resolved_exits, since)

        wall_clock = time.time() - t0
        resolved = sum(per_reason.values())
        logger.info(
            "EOD resolver complete: resolved=%d skipped=%d (stale=%d) by_reason=%s wall_clock=%.1fs",
            resolved, skipped, skipped_stale, per_reason, wall_clock,
        )
        return {
            'resolved': resolved,
            'skipped': skipped,
            'skipped_stale': skipped_stale,
            'by_reason': per_reason,
            'wall_clock_s': wall_clock,
        }


def _recompute_main(args) -> int:
    """--re-resolve and --revert-run. Returns 2, with the reason on one line,
    for anything refused before a query or a write."""
    from gcp import bar_recompute

    try:
        if not (args.re_resolve or args.revert_run):
            raise bar_recompute.Refusal(
                "--from, --to, --tickers, --commit and --report-dir belong to "
                "--re-resolve or --revert-run")
        if args.re_resolve and (args.since or args.backfill or args.revert_run):
            raise bar_recompute.Refusal(
                "--re-resolve does not combine with --since, --backfill or --revert-run")
        if args.revert_run and (args.first or args.last or args.tickers
                                or args.since or args.backfill):
            raise bar_recompute.Refusal(
                "--revert-run takes a run id and no --from, --to, --tickers, "
                "--since or --backfill")
        window = None
        if args.re_resolve:
            window = bar_recompute.parse_window(
                args.tickers, args.first, args.last, market_today())
        resolver = EODResolver()
        if args.re_resolve:
            # Every stored exit reason is one only `target_stop` produces.
            # Re-resolving under another mode would change outcomes for a
            # reason that is not the bars.
            for direction in ('call_exit_mode', 'put_exit_mode'):
                mode = getattr(resolver.exit_cfg, direction, 'target_stop')
                if mode != 'target_stop':
                    raise bar_recompute.Refusal(
                        f"exit.{direction} is {mode!r}; stored exits are re-resolved "
                        "only under 'target_stop'")
        bar_recompute.require_report_destination(args.report_dir)
    except bar_recompute.Refusal as refusal:
        logger.error("refused: %s", refusal)
        return 2

    # The first query. The selection reads the marker columns, so a database
    # without them is refused in a dry run too.
    missing = bar_recompute.schema_missing()
    if missing:
        logger.error(
            "refused: the database does not hold %s; apply gcp/schema.sql first",
            ", ".join(missing))
        return 2

    run_id = bar_recompute.run_id()
    if args.revert_run:
        raise NotImplementedError("--revert-run is not written yet")
    tickers, first, last = window
    return resolver.re_resolve(
        tickers, first, last, commit=args.commit, run_id=run_id,
        report_dir=args.report_dir)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )
    parser = argparse.ArgumentParser(
        description='EOD reconciliation for signal_alerts'
    )
    parser.add_argument(
        '--since', metavar='YYYY-MM-DD',
        help='Only resolve alerts on or after this date (default: all unresolved)',
    )
    parser.add_argument(
        '--backfill', action='store_true',
        help='Informational flag for one-shot backfill runs (same query as default)',
    )
    parser.add_argument(
        '--re-resolve', action='store_true',
        help='Re-resolve closed alerts whose exit this job wrote, from stored bars '
             'proven true UTC, for SPY, QQQ and IWM in [--from, --to]. A dry run '
             'that writes a report unless --commit is given.',
    )
    parser.add_argument(
        '--from', dest='first', metavar='YYYY-MM-DD',
        help='First alert date of --re-resolve',
    )
    parser.add_argument(
        '--to', dest='last', metavar='YYYY-MM-DD',
        help="Last alert date of --re-resolve; before today's Eastern date",
    )
    parser.add_argument(
        '--tickers', metavar='"SPY QQQ"',
        help='One space-separated value for --re-resolve (default: SPY QQQ IWM, '
             'which is also every ticker allowed)',
    )
    parser.add_argument(
        '--commit', action='store_true',
        help='With --re-resolve or --revert-run: write. Without it nothing is written '
             'to the database.',
    )
    parser.add_argument(
        '--revert-run', metavar='RUN_ID',
        help='Write back the exits a committed --re-resolve run replaced, from its '
             'ledger rows. A dry run unless --commit is given.',
    )
    parser.add_argument(
        '--report-dir', metavar='PATH',
        help='Write rows.csv and summary.json under PATH instead of the bucket',
    )
    args = parser.parse_args()

    if (args.re_resolve or args.revert_run or args.first or args.last
            or args.tickers or args.commit or args.report_dir):
        return _recompute_main(args)

    if args.backfill and not args.since:
        # Backfill = "resolve everything currently unresolved". Equivalent
        # to the default behaviour but logged distinctly so the operator
        # sees they invoked the one-shot path on purpose.
        logger.info("backfill mode — resolving all unresolved alerts")

    summary = EODResolver().run(since=args.since)
    # Same-day skips (today's own intraday partition not yet fetched by
    # av-intraday-nightly, 21:00 ET) are expected and self-heal on the
    # next run — only a stale (prior-day) skip is a real failure worth
    # paging on (see run()).
    return 0 if summary.get('skipped_stale', 0) == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
