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
import sys
import time
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from lib.config import load_config
from lib.data_loader import DataLoader
from lib.indicators import calculate_rsi


logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")
_SESSION_CLOSE_ET = dt_time(16, 0)  # 4:00 PM ET — same as MarketConfig default


def _exit_return_pct(direction: str, entry_price: float, exit_price: float) -> float:
    """Mirror of SignalMonitor._exit_return_pct — kept here so the resolver
    has no runtime dependency on a SignalMonitor instance (which would
    construct a watchlist + Discord webhook + AV client just to read one
    static method)."""
    if direction == 'CALL':
        return (exit_price - entry_price) / entry_price * 100.0
    return (entry_price - exit_price) / entry_price * 100.0


class EODResolver:
    """Replay exit logic against historical bars to close stuck alerts."""

    def __init__(self):
        cfg = load_config()
        self.exit_cfg = cfg.exit
        self.indicator_cfg = cfg.indicator
        self.loader = DataLoader(data_dir=cfg.market.data_dir)
        # Per-day (ticker, alert_date) → DataFrame cache. Reset per run.
        self._intraday_cache: dict[Tuple[str, str], pd.DataFrame] = {}

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

        # Strip TZ so timestamps compare as naive UTC, matching alert_ts.
        if 'Time' in df.columns:
            df = df.set_index('Time')
        df = df.sort_index()
        try:
            df.index = df.index.tz_localize(None)
        except (TypeError, AttributeError):
            pass  # already naive

        # Precompute RSI once for the whole day; per-bar lookup is O(1).
        df[self.indicator_cfg.rsi_col] = calculate_rsi(
            df['Close'], self.indicator_cfg.rsi_period
        )
        self._intraday_cache[key] = df
        return df

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

    def resolve_one(self, alert: pd.Series) -> Optional[dict]:
        """Walk one alert's bar-by-bar history; return the resolution dict.

        Returns None when the day's intraday partition is missing — the
        caller logs and continues to the next alert.
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

        bars = self._load_day(ticker, alert_date)
        if bars.empty:
            return None

        # Walk only bars at or after the alert timestamp.
        forward = bars[bars.index >= alert_ts]
        if forward.empty:
            # Alert fired after the day's last logged bar (e.g. alert at 15:59,
            # AV's last bar is 15:58). Fall through to eod_close at session close.
            return self._eod_close_resolution(
                alert, entry_price, alert_ts, alert_date, bars,
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

        # No trigger fired before the day's last bar → eod_close at session close.
        return self._eod_close_resolution(
            alert, entry_price, alert_ts, alert_date, bars,
        )

    def _eod_close_resolution(
        self,
        alert: pd.Series,
        entry_price: float,
        alert_ts: pd.Timestamp,
        alert_date,
        bars: pd.DataFrame,
    ) -> dict:
        """Fall-back resolution: nothing fired before session close.

        Use the day's last bar's Close as the exit price (the value the
        position would have liquidated at). exit_ts is set to 16:00 ET
        converted to naive UTC so comparisons with alert_ts (naive UTC)
        align.
        """
        last_bar = bars.iloc[-1]
        exit_price = float(last_bar['Close'])
        # Build session-close timestamp as 16:00 ET, then convert to naive UTC
        # so it lines up with alert_ts which is also naive UTC.
        date_obj = (
            alert_date if isinstance(alert_date, (datetime, pd.Timestamp))
            else datetime.fromisoformat(str(alert_date))
        )
        close_et = datetime.combine(date_obj.date(), _SESSION_CLOSE_ET, tzinfo=_ET)
        close_utc_naive = close_et.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
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
        """UPDATE the signal_alerts row. Returns 1 on success, 0 on no-op.

        Idempotency: this UPDATE flips `is_open=FALSE` so the next run's
        query filter excludes the row. Safe to re-run a partial batch.
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
            return result.rowcount or 0

    # ── 4. Orchestration ──────────────────────────────────────────────

    def run(self, since: Optional[str] = None) -> dict:
        """Top-level entry. Returns a per-reason count summary."""
        t0 = time.time()
        df = self.find_open_alerts(since=since)
        if df.empty:
            logger.info("nothing to resolve")
            return {'resolved': 0, 'skipped': 0, 'wall_clock_s': time.time() - t0}

        per_reason: dict[str, int] = {}
        skipped = 0
        groups = df.groupby(['ticker', 'alert_date'])
        for (ticker, alert_date), group in groups:
            logger.info("ticker=%s date=%s alerts=%d", ticker, alert_date, len(group))
            for _, alert in group.iterrows():
                resolution = self.resolve_one(alert)
                if resolution is None:
                    skipped += 1
                    continue
                try:
                    n = self.persist(resolution)
                    if n:
                        per_reason[resolution['exit_reason']] = (
                            per_reason.get(resolution['exit_reason'], 0) + 1
                        )
                except Exception as e:
                    logger.warning(
                        "persist failed for %s @%s: %s",
                        ticker, alert['alert_ts'], e,
                    )
                    skipped += 1

        wall_clock = time.time() - t0
        resolved = sum(per_reason.values())
        logger.info(
            "EOD resolver complete: resolved=%d skipped=%d by_reason=%s wall_clock=%.1fs",
            resolved, skipped, per_reason, wall_clock,
        )
        return {
            'resolved': resolved,
            'skipped': skipped,
            'by_reason': per_reason,
            'wall_clock_s': wall_clock,
        }


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
    args = parser.parse_args()

    if args.backfill and not args.since:
        # Backfill = "resolve everything currently unresolved". Equivalent
        # to the default behaviour but logged distinctly so the operator
        # sees they invoked the one-shot path on purpose.
        logger.info("backfill mode — resolving all unresolved alerts")

    summary = EODResolver().run(since=args.since)
    return 0 if summary['skipped'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
