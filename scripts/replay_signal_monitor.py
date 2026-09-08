"""Replay historical 1-min bars through the live SignalMonitor — Phase 0.5 #8.

Loads market_data_intraday for a given ticker × date range and replays
the bars one minute at a time through the EXACT same code path the
live signal-monitor exercises during market hours: update_window →
calculate_indicators → evaluate_ticker → _evaluate_strategies_for_bar
→ assign_timeframe → fire_alert / _persist_signal_alert.

Discord webhook + DB upsert are mocked so this is hermetic against
production side effects: no fake alerts, no real signal_alerts rows.

Output is a structured summary of:
  * total fires, direction split (CALL vs PUT)
  * timeframe_tag distribution
  * stacked-agreement events (Phase 1.6)
  * the per-fire dataframe row that WOULD have been written

Use cases:
  1. Validate a freshly-deployed signal_monitor against held-out data
     BEFORE waiting for market open (Phase 0.5 spec item #8 — the
     live-vs-offline parity test).
  2. Hermetic regression check after refactors that touch the
     signal-fire path.
  3. What-if: tune assign_timeframe thresholds and replay to see how
     the timeframe distribution shifts.

Usage:
    python -m scripts.replay_signal_monitor --ticker SPY --date 2026-05-01
    python -m scripts.replay_signal_monitor --ticker IWM --start 2026-04-29 --end 2026-05-01
    python -m scripts.replay_signal_monitor --ticker SPY --date 2026-05-01 --tickers SPY,QQQ,IWM

Bypasses live AV. Reads creds from env (CLOUD_SQL_CONNECTION_NAME,
DB_USER, DB_PASS, DB_NAME) so the script works locally with the
.creds_tmp/ shim AND in Cloud Run with the standard env-var setup.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta, timezone
import os
import uuid
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pandas as pd

from gcp.signal_monitor import _ET, rvol_gate_verdict

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

logger = logging.getLogger(__name__)


@dataclass
class FireRecord:
    """One captured signal-fire event from the replay."""
    timestamp:         pd.Timestamp
    ticker:            str
    direction:         str
    base_score:        int
    total_score:       float
    timeframe_tag:     Optional[str]
    expected_hold_min: Optional[int]
    strategy_agreement: Optional[dict]
    conditions_met:    list[str]
    embed_title:       str
    brief_alignment:   Optional[str] = None
    level_state:       Optional[str] = None
    opp_level_state:   Optional[str] = None
    rvol_mod:          Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "timestamp":          self.timestamp.isoformat(),
            "ticker":             self.ticker,
            "direction":          self.direction,
            "base_score":         self.base_score,
            "total_score":        self.total_score,
            "brief_alignment":    self.brief_alignment,
            "level_state":        self.level_state,
            "opp_level_state":    self.opp_level_state,
            "rvol_mod":           self.rvol_mod,
            "timeframe_tag":      self.timeframe_tag,
            "expected_hold_min":  self.expected_hold_min,
            "strategy_agreement": self.strategy_agreement,
            "conditions_met":     self.conditions_met,
            "embed_title":        self.embed_title,
        }


def load_intraday_for_replay(
    engine, ticker: str, start: datetime, end: datetime,
) -> pd.DataFrame:
    """Pull 1-min bars from market_data_intraday into the column shape
    SignalMonitor.update_window expects: Time / Open / High / Low / Close / Volume.

    The signal_monitor's rolling window keys on 'Time' (capitalized),
    'Close' (not 'Last') — different from gcp/historical_signals.py's
    load_intraday_bars which aliases close as 'Last' for MarketAnalyzer.
    """
    from sqlalchemy import text
    sql = text("""
        SELECT ts AS "Time",
               open AS "Open",
               high AS "High",
               low AS "Low",
               close AS "Close",
               volume AS "Volume"
        FROM market_data_intraday
        WHERE ticker = :t
          AND ts >= :start AND ts < :end
          AND interval = '1min'
        ORDER BY ts
    """)
    df = pd.read_sql(sql, engine, params={"t": ticker.upper(), "start": start, "end": end})
    df["Time"] = pd.to_datetime(df["Time"])
    return df


def replay_ticker(
    monitor, ticker: str, bars: pd.DataFrame,
    captured_fires: list[FireRecord],
    evaluate_rth_only: bool = False,
) -> tuple[int, int]:
    """Replay one ticker's bars through the live monitor code path.

    For each bar T, append it to the rolling window then call
    evaluate_ticker. The monitor's existing logic computes indicators,
    runs both strategies, detects agreement, assigns timeframe, and
    (with our patches) calls a stub fire_alert that captures the fire
    instead of actually posting to Discord.

    ``evaluate_rth_only`` separates what the window HOLDS from what can
    FIRE. Persist mode used to drop premarket bars before they reached
    this function, so each session began at 09:30 with an empty window
    and evaluate_ticker suppressed every bar until min_bars_for_signals
    (30) RTH bars existed — roughly 09:30 to 09:59 missing from every
    replayed day (Codex on #1022). Live does not start empty: run_loop's
    first in-hours fetch asks for `extended_hours=true` with
    `outputsize=compact`, so at the open the window already carries ~100
    of that day's premarket bars. Premarket bars now enter the window
    exactly as they do live, and only RTH bars are evaluated, which is
    what keeps replayed fire counts comparable to live signal_alerts.

    Returns (bars_evaluated, signals_fired) — bars fed to the window but
    not evaluated are warm-up, not work.
    """
    if bars.empty:
        return (0, 0)

    fires_before = len(captured_fires)
    evaluated = 0

    # Rolling-window replay: feed bars one at a time so the monitor
    # operates on the same shape it sees in production (1-bar deltas).
    # Setting `replay_clock_ts` before each call routes the monitor's
    # _now() to bar-time so brief-bias and catalyst-proximity lookups
    # use the bar's date, not wall-clock-today (the bug that made the
    # PR #379 FTFC fix architecturally inert during replay).
    prev_date = None
    for i in range(len(bars)):
        single_bar = bars.iloc[i:i + 1].copy()
        if 'Time' in single_bar.columns:
            _ts = pd.Timestamp(single_bar['Time'].iloc[0])
            monitor.replay_clock_ts = _ts
            # `daily_trades` is SESSION state: production runs one
            # SignalMonitor per trading day, so the counter starts at 0 each
            # morning. A --start/--end replay drives many dates through one
            # instance, so without this rollover date 1 exhausting the cap
            # would suppress every candidate on every later date (Codex P1 on
            # PR #934). The window is framed in ET (resolve_window), so a
            # single-date replay holds one session and never resets.
            #
            # A session is an EASTERN date, and it is derived through the
            # monitor's own clock so it matches the date refresh_level_map
            # bounds by. Replay bars carry naive UTC stamps, so the bar's
            # own .date() rolled at 00:00 UTC: extended-hours bars between
            # 00:00 and 04:00 UTC reset the session early and the real ET
            # change then reset nothing (Codex on #1022).
            _bar_date = monitor._now(_ET).date()
            if prev_date is not None and _bar_date != prev_date:
                # Everything a fresh production monitor starts a session
                # without: the fire counter, the level map (bounded to rows
                # before the session's date, #823), the brief cache the leg
                # trackers are built from, last price and fired breaks, ORB
                # and session extremes. The monitor owns the list (Codex on
                # #1022, rounds 9 to 11).
                monitor.reset_session_state(ticker)
                logger.info(
                    "replay: %s session rollover %s -> %s, session state reset",
                    ticker, prev_date, _bar_date)
            prev_date = _bar_date
        monitor.update_window(ticker, single_bar)
        if evaluate_rth_only and not _is_rth(single_bar):
            continue          # warm-up only, as live's premarket bars are
        evaluated += 1
        try:
            monitor.evaluate_ticker(ticker)
        except Exception as e:
            logger.warning("replay: ticker=%s bar=%d evaluate_ticker raised: %s",
                           ticker, i, e)
    # Clear the clock at the end so a subsequent live run isn't sticky.
    monitor.replay_clock_ts = None

    fires_after = len(captured_fires)
    return (evaluated, fires_after - fires_before)


def _is_rth(bar: pd.DataFrame) -> bool:
    """True when this one bar falls inside 09:30-16:00 ET.

    The single-bar form of filter_to_rth, used to gate EVALUATION while
    the bar still enters the window (see replay_ticker).
    """
    if bar.empty or 'Time' not in bar.columns:
        return True
    ts = pd.Timestamp(bar['Time'].iloc[0])
    et = ts.tz_convert(_ET) if ts.tz is not None else ts.tz_localize('UTC').tz_convert(_ET)
    return time(9, 30) <= et.time() < time(16, 0)


# The live monitor's first in-hours fetch is `outputsize=compact`, which is
# the last 100 one-minute points (gcp/signal_monitor.py:331). That, and not
# "everything since midnight", is the warm-up a session actually opens with.
_LIVE_WARMUP_BARS = 100


def trim_to_live_window_scope(bars: pd.DataFrame,
                              warmup_bars: int = _LIVE_WARMUP_BARS) -> pd.DataFrame:
    """Keep, per Eastern session, the bars the LIVE window would hold.

    Feeding every bar since Eastern midnight warms the open with up to
    `rolling_window_bars` (200) bars where live has at most 100, and
    cumulative VWAP and the seeded EMA/MACD values differ enough to change
    fires (Codex on #1022). Parity is the same warm-up SIZE, not merely a
    non-empty one.

    Post-close bars go too: `run_loop` stops fetching at the close, so
    16:00-20:00 never enters the live window either. They were inert in
    replay (nothing is evaluated after 16:00, and the rollover clears the
    window) but "inert and different" is still different.
    """
    if bars.empty or 'Time' not in bars.columns:
        return bars
    ts = bars['Time']
    et = ts.dt.tz_convert(_ET) if ts.dt.tz is not None \
        else ts.dt.tz_localize('UTC').dt.tz_convert(_ET)
    is_pre = et.dt.time < time(9, 30)
    is_rth = (et.dt.time >= time(9, 30)) & (et.dt.time < time(16, 0))

    keep = is_rth.copy()
    for _day, idx in et.dt.date.groupby(et.dt.date).groups.items():
        pre_idx = [i for i in idx if is_pre.loc[i]]
        for i in pre_idx[-warmup_bars:]:
            keep.loc[i] = True
    return bars[keep].sort_values('Time').reset_index(drop=True)


def limit_to_evaluated_bars(bars: pd.DataFrame,
                            limit: Optional[int]) -> pd.DataFrame:
    """Apply ``--limit`` to the bars that will be EVALUATED.

    `bars.head(N)` selected from the Eastern-midnight query before the
    RTH-only gate, so on a ticker with N or more premarket bars every
    selected bar was warm-up and the replay evaluated nothing (Codex on
    #1022). Truncating at the Nth RTH bar keeps the warm-up in front of it
    and counts what the operator asked to see.
    """
    if not limit or bars.empty or 'Time' not in bars.columns:
        return bars
    rth = filter_to_rth(bars)
    if len(rth) <= limit:
        return bars
    cutoff = pd.Timestamp(rth['Time'].iloc[limit - 1])
    return bars[bars['Time'] <= cutoff].reset_index(drop=True)


def filter_to_rth(bars: pd.DataFrame) -> pd.DataFrame:
    """Filter intraday bars to RTH only (09:30-16:00 ET).

    This matches the live signal-monitor scope so replay fire counts are
    comparable to live counts. Without this, replay processes ~1,200
    bars/day (24h coverage) vs live's ~390 bars/day (6.5h RTH).

    The 'Time' column is in UTC (per market_data_intraday storage). RTH
    in ET = 13:30-20:00 UTC during EDT (March-November), 14:30-21:00
    UTC during EST (November-March). We use ET-aware filtering rather
    than fixed UTC offsets to handle DST transitions correctly.
    """
    if bars.empty or 'Time' not in bars.columns:
        return bars
    et = bars['Time'].dt.tz_convert('America/New_York') if bars['Time'].dt.tz \
        else bars['Time'].dt.tz_localize('UTC').dt.tz_convert('America/New_York')
    rth_mask = (et.dt.time >= time(9, 30)) & (et.dt.time < time(16, 0))
    return bars[rth_mask].reset_index(drop=True)


def simulate_exit(
    fire: 'FireRecord', engine, target_price: Optional[float] = None,
    time_stop_minutes: int = 60,
) -> dict:
    """Walk forward from fire timestamp through subsequent intraday bars
    until target / time_stop / EOD triggers. Returns dict matching the
    signal_alerts exit columns.

    Reuses the same exit policy the live monitor uses (target / time_stop
    / eod_close). Stop-loss simulation is approximate — we assume a stop
    at target * 0.5 R-multiple distance below entry for longs (above for
    shorts). For a more precise replay, the persona plan's actual stop
    would be passed in (Phase 1 prereq for clean acceptance testing).
    """
    from sqlalchemy import text
    fire_ts = fire.timestamp
    end_ts = fire_ts + timedelta(minutes=time_stop_minutes)
    sql = text("""
        SELECT ts AS time, open, high, low, close
        FROM market_data_intraday
        WHERE ticker = :t AND ts > :start AND ts <= :end
          AND interval = '1min'
        ORDER BY ts
    """)
    df = pd.read_sql(sql, engine, params={
        "t": fire.ticker,
        "start": fire_ts.to_pydatetime(),
        "end": end_ts.to_pydatetime(),
    })
    if df.empty:
        return {
            'exit_ts': end_ts.isoformat(),
            'exit_reason': 'no_data',
            'exit_price': None,
            'exit_return_pct': 0.0,
        }
    entry = float(df.iloc[0]['open'])  # fill at next bar's open
    sign = 1 if fire.direction == 'CALL' else -1
    for _, bar in df.iterrows():
        if target_price is not None:
            if (sign > 0 and bar['high'] >= target_price) or \
               (sign < 0 and bar['low'] <= target_price):
                exit_price = float(target_price)
                ret = sign * (exit_price - entry) / entry * 100
                return {
                    'exit_ts': pd.Timestamp(bar['time']).isoformat(),
                    'exit_reason': 'target',
                    'exit_price': exit_price,
                    'exit_return_pct': round(ret, 4),
                }
    last_bar = df.iloc[-1]
    exit_price = float(last_bar['close'])
    ret = sign * (exit_price - entry) / entry * 100
    return {
        'exit_ts': pd.Timestamp(last_bar['time']).isoformat(),
        'exit_reason': 'time_stop',
        'exit_price': exit_price,
        'exit_return_pct': round(ret, 4),
    }


def persist_fire_to_signal_alerts(fire: 'FireRecord', monitor, engine, replay_id: str):
    """Insert a captured fire into signal_alerts with run_kind='replay'.

    Reuses monitor's _persist_signal_alert path conceptually, but builds
    the row directly so we can stamp run_kind + replay_id. Fields match
    the production signal_alerts schema.
    """
    from sqlalchemy import text
    # Compute approximate target_price from the fire's score (placeholder)
    # — Phase 1's full integration would pass through the persona plan
    # target. For now, use a 0.5% target for CALL, -0.5% for PUT.
    sign = 1 if fire.direction == 'CALL' else -1
    target_pct = 0.005 * sign
    # Approximate entry from the bar's close (the fire was triggered on this bar)
    entry_price = None  # need bar context — populated at fire time
    insert_sql = text("""
        INSERT INTO signal_alerts (
            ticker, alert_ts, alert_date, direction,
            base_score, total_score, strength_label,
            position_size, time_stop_minutes,
            conditions_met, brief_alignment, level_state, opp_level_state,
            rvol_mod, run_kind, replay_id,
            inserted_at
        ) VALUES (
            :ticker, :alert_ts, :alert_date, :direction,
            :base_score, :total_score, :strength,
            :size, :time_stop,
            :conditions, :brief_alignment, :level_state, :opp_level_state,
            :rvol_mod, 'replay', :replay_id,
            NOW()
        )
        ON CONFLICT DO NOTHING
    """)
    # signal_alerts is unique on (ticker, alert_ts) and this INSERT is ON
    # CONFLICT DO NOTHING, so replaying a session that ran live drops every
    # fire on a live fire's minute. Legitimate, never silent: the rowcount
    # is returned and a dropped row is logged. A failed write raises; an
    # operator --persist run must not report success over one.
    with engine.begin() as conn:
        res = conn.execute(insert_sql, {
                'ticker': fire.ticker,
                'alert_ts': fire.timestamp.to_pydatetime(),
                'alert_date': fire.timestamp.date(),
                'direction': fire.direction,
                'base_score': fire.base_score,
                'total_score': fire.total_score,
                'strength': 'replay-strong' if fire.total_score >= 5 else 'replay-medium' if fire.total_score >= 3 else 'replay-weak',
                'size': 1.0,
                'time_stop': fire.expected_hold_min or 60,
                'conditions': json.dumps(fire.conditions_met),
                'brief_alignment': fire.brief_alignment,
                'level_state': fire.level_state,
                'opp_level_state': fire.opp_level_state,
                'rvol_mod': fire.rvol_mod,
                'replay_id': replay_id,
            })
    n = int(res.rowcount)
    if n == 0:
        logger.warning("replay fire %s %s not persisted: a signal_alerts row with the same "
                       "(ticker, alert_ts) exists (unique key uq_signal_alerts), i.e. a live "
                       "fire at that minute; the replay row is dropped, not merged",
                       fire.ticker, fire.timestamp)
    return n


def make_capturing_fire_alert(captured: list[FireRecord], monitor):
    """Replace SignalMonitor.fire_alert with a callable that captures
    the fire into `captured` instead of posting to Discord / Cloud SQL.
    """
    def _capture(self, ticker, sig, total_score, strength, size, strat_bonus, latest):
        agreement = getattr(self, "_latest_agreement", None)
        tf_tag = getattr(self, "_latest_timeframe_tag", None)
        tf_hold = getattr(self, "_latest_expected_hold_min", None)
        # Same brief-tag resolution live fire_alert runs — shared method
        # so the replay can never drift from production tag semantics
        # (Rule 3.6). Session extremes are fed by update_window, which
        # this harness already drives bar-by-bar.
        brief, align = self._resolve_brief_alignment(ticker, sig["direction"])
        # Same level-state resolution live fire_alert runs (audit §15) —
        # trackers are fed by update_window, which this harness already
        # drives bar-by-bar, so replay tags carry production semantics.
        own_state, opp_state = self._resolve_level_state(ticker, sig["direction"])
        # Production fire_alert also records the corrected RVOL (audit §16);
        # compute it here too or replay rows carry a NULL the live path
        # would have filled, and the shadow comparison loses the replay arm.
        rvol_mod = self._corrected_rvol(ticker)
        # Mirror the production RVOL gate (Codex P2 on PR #934). Live
        # fire_alert returns on a 'below' verdict under `enforce` BEFORE
        # Discord, persist and the daily-trades counter — its own comment
        # says a suppressed fire is "invisible to the risk caps too". The
        # raw bar RVOL is used, not self._corrected_rvol(): the gate reads
        # latest['RVOL'] in production, and passing a missing value through
        # as None is deliberate (§3.7) so rvol_gate_verdict's always-'below'
        # guarantee applies instead of a 0 default sneaking past a legal
        # rvol_gate_min=0.
        if getattr(self.signal_cfg, "rvol_gate_mode", "shadow") == "enforce":
            if rvol_gate_verdict(latest.get("RVOL"),
                                 self.signal_cfg.rvol_gate_min,
                                 self.signal_cfg.rvol_gate_mode) == "below":
                return

        # Mirror production enforcement (Codex P2 on PR #799): under
        # `enforce`, live fire_alert returns before Discord/persist for
        # late-state fires, so the replay must not capture them either —
        # otherwise replay counts and --persist rows include fires the
        # live monitor would suppress.
        if (getattr(self.signal_cfg, "level_gate_mode", "shadow") == "enforce"
                and own_state in ("post_t1", "post_t1_open", "invalidated")):
            return
        title_prefix = "STACKED " if agreement else ""
        tf_label = f" [{tf_tag}]" if tf_tag else ""
        brief_label = f" [brief:{align}]" if align else ""
        title = (
            f"{title_prefix}{sig['direction']} SIGNAL{tf_label}{brief_label} "
            f"@ ${latest.get('Close', 0):.2f}"
        )
        captured.append(FireRecord(
            timestamp=pd.Timestamp(latest.get("Time", datetime.now())),
            ticker=ticker,
            direction=sig["direction"],
            base_score=int(sig["base_score"]),
            total_score=float(total_score),
            timeframe_tag=tf_tag,
            expected_hold_min=tf_hold,
            strategy_agreement=agreement,
            conditions_met=list(sig["conditions_met"]),
            embed_title=title,
            brief_alignment=align,
            level_state=own_state,
            opp_level_state=opp_state,
            rvol_mod=rvol_mod,
        ))
        # Production `fire_alert` increments the per-ticker fire counter at
        # this point — AFTER the level-gate early return above, so a
        # suppressed fire does not consume cap. Replacing fire_alert wholesale
        # dropped that mutation, so `daily_trades` stayed 0 for the whole
        # replay and the `max_daily_trades` gate in evaluate_ticker never
        # engaged (#818).
        #
        # This is not only replay fidelity. Per Codex's #816 review the daily
        # cap is currently the ONLY bound on concurrent exposure, so a replay
        # where it never binds cannot reproduce today's behaviour as the
        # baseline for any shadow-control analysis.
        self.daily_trades[ticker] = self.daily_trades.get(ticker, 0) + 1
    return _capture


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--ticker", help="Single ticker to replay (alias for --tickers TICKER)")
    p.add_argument("--tickers", help="Comma-separated tickers (overrides --ticker)")
    p.add_argument("--date", help="Single trading date YYYY-MM-DD (alias for --start = --end)")
    p.add_argument("--start", help="Eastern start date YYYY-MM-DD (a session is an ET day)")
    p.add_argument("--end", help="Eastern end date YYYY-MM-DD (exclusive)")
    p.add_argument("--limit", type=int, default=None,
                   help="Max bars per ticker (debug/dev)")
    p.add_argument("--json", action="store_true",
                   help="Print fires as a JSON array (machine-readable)")
    p.add_argument(
        "--persist", action="store_true",
        help=(
            "Persist captured fires to signal_alerts with run_kind='replay' "
            "and replay_id=<UUID>. Required for Phase 1 acceptance testing "
            "and any analysis that needs full per-fire detail (Cloud Run "
            "log truncation drops the JSON output at ~85 records). When set, "
            "ALSO restricts bars to RTH (9:30-16:00 ET) to match live "
            "signal-monitor scope. Equivalent env var: REPLAY_PERSIST=true."
        ),
    )
    return p.parse_args(argv)


def resolve_window(args: argparse.Namespace) -> tuple[datetime, datetime]:
    """The bar window to load, framed in ET like the session it replays.

    A session is an Eastern date: the rollover keys on ``monitor._now(_ET)``
    and refresh_level_map bounds by that date. The window was built on UTC
    midnights, i.e. 20:00 ET of D-1 to 20:00 ET of D, so a single --date
    replay began in session D-1, reset once at the 04:00Z bar, and never
    saw D's 16:00-20:00 ET bars (internal review of #1022; CLAUDE.md 3.9:
    the query that lists and the query that fetches must frame time
    identically). ``ts`` is TIMESTAMPTZ, so the aware ET bounds compare as
    instants.
    """
    if args.date:
        d = date.fromisoformat(args.date)
        start = datetime(d.year, d.month, d.day, tzinfo=_ET)
        return start, start + timedelta(days=1)
    if args.start and args.end:
        s = date.fromisoformat(args.start)
        e = date.fromisoformat(args.end)
        return (
            datetime(s.year, s.month, s.day, tzinfo=_ET),
            datetime(e.year, e.month, e.day, tzinfo=_ET),
        )
    raise SystemExit("Must specify --date or --start/--end")


def resolve_tickers(args: argparse.Namespace) -> list[str]:
    if args.tickers:
        return [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if args.ticker:
        return [args.ticker.strip().upper()]
    raise SystemExit("Must specify --ticker or --tickers")


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    args = parse_args(argv)
    start, end = resolve_window(args)
    tickers = resolve_tickers(args)

    # REPLAY_PERSIST env var is an alias for --persist. Either source enables.
    persist_mode = args.persist or os.environ.get('REPLAY_PERSIST', '').lower() == 'true'
    replay_id = str(uuid.uuid4()) if persist_mode else None

    logger.info("replay window: %s -> %s tickers=%s persist=%s replay_id=%s",
                start, end, tickers, persist_mode, replay_id)

    from gcp.database import get_engine
    engine = get_engine()

    # Patch the watchlist source so SignalMonitor.__init__ doesn't fail
    # if signals=TRUE is set differently from what the replay needs.
    # We override with the explicit --tickers list.
    captured_fires: list[FireRecord] = []
    summary_per_ticker: dict[str, tuple[int, int]] = {}

    with patch("gcp.fetchers._watchlist.load_watchlist", return_value=tickers):
        from gcp.signal_monitor import SignalMonitor
        monitor = SignalMonitor()
        monitor.webhook_url = ""           # disable Discord
        # Replace fire_alert with the capturing stub. Persist path is
        # also bypassed since fire_alert calls _persist_signal_alert.
        capture_fn = make_capturing_fire_alert(captured_fires, monitor)
        monitor.fire_alert = capture_fn.__get__(monitor, type(monitor))

        # The put-side 9:31 re-anchor (audit §15.5) is computed by
        # update_window and normally UPDATEs the day's premarket_analysis row.
        # A replay recomputes it from replayed bars, so letting that write
        # through would overwrite the REAL playbook row for the replayed date
        # with a shadow value the live session never produced. Capture it
        # in-memory instead — the replay stays hermetic (only --persist writes,
        # and only to signal_alerts), and the re-anchor is still visible in the
        # summary for validation.
        replay_reanchors: dict[str, dict] = {}

        def _capture_reanchor(ticker, r):
            replay_reanchors[ticker] = r

        monitor._persist_put_reanchor = _capture_reanchor

        for ticker in tickers:
            bars = load_intraday_for_replay(engine, ticker, start, end)
            if persist_mode:
                # Match live signal-monitor scope (RTH only, 9:30-16:00 ET)
                # so persisted fire counts are comparable to live
                # signal_alerts. The bars are NOT dropped: premarket bars
                # feed the window exactly as they do live, where the first
                # in-hours fetch returns them, and only RTH bars are
                # evaluated. Dropping them left every session's 09:30-09:59
                # unevaluated for want of min_bars_for_signals (Codex on
                # #1022).
                pre_n = len(bars)
                bars = trim_to_live_window_scope(bars)
                rth_n = int(len(filter_to_rth(bars)))
                logger.info("ticker=%s persist mode: %d bars loaded, trimmed to "
                            "%d in the live window's scope, of which %d RTH bars "
                            "are evaluated; the rest are warm-up",
                            ticker, pre_n, len(bars), rth_n)
                bars = limit_to_evaluated_bars(bars, args.limit)
            elif args.limit:
                bars = bars.head(args.limit)
            logger.info("ticker=%s loaded %d bars", ticker, len(bars))
            ticker_fires_before = len(captured_fires)
            n_bars, n_fires = replay_ticker(monitor, ticker, bars, captured_fires,
                                            evaluate_rth_only=persist_mode)
            summary_per_ticker[ticker] = (n_bars, n_fires)

            # Persist this ticker's captured fires to signal_alerts
            if persist_mode:
                new_fires = captured_fires[ticker_fires_before:]
                logger.info("ticker=%s persisting %d fires to signal_alerts",
                            ticker, len(new_fires))
                for f in new_fires:
                    persist_fire_to_signal_alerts(f, monitor, engine, replay_id)

    if replay_reanchors:
        logger.info("put re-anchor (shadow, NOT persisted in replay):")
        for tk, r in sorted(replay_reanchors.items()):
            logger.info("  %s open=%.4f trigger=%.4f (%s) stop=%s",
                        tk, r['open'], r['trigger'], r.get('trigger_name'),
                        r.get('stop'))

    # ── Summary ────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("REPLAY SUMMARY")
    print("=" * 70)
    print(f"Window: {start.date()} -> {end.date()}")
    print(f"Tickers: {', '.join(tickers)}")
    print()
    print(f"{'Ticker':<8}{'Bars':<10}{'Fires':<8}")
    for tk, (n_bars, n_fires) in summary_per_ticker.items():
        print(f"{tk:<8}{n_bars:<10}{n_fires:<8}")
    print()

    if not captured_fires:
        print("No signals fired during the replay window.")
        return 0

    # Direction split
    dirs = Counter(f.direction for f in captured_fires)
    print(f"Direction:  CALL={dirs.get('CALL', 0)}  PUT={dirs.get('PUT', 0)}")

    # Brief-alignment distribution (level-aware tag)
    aligns = Counter(f.brief_alignment for f in captured_fires)
    print("Brief alignment: "
          + "  ".join(f"{k or 'untagged'}={n}"
                      for k, n in sorted(aligns.items(),
                                         key=lambda x: (x[0] or ''))))

    # Playbook leg-state distribution (audit §16). Printed so a replay can
    # be read as a check on the tracker itself — in particular whether the
    # gap-through route ('post_t1_open') separates from plain 'post_t1'.
    states = Counter(f.level_state for f in captured_fires)
    print("Level state:     "
          + "  ".join(f"{k or 'untagged'}={n}"
                      for k, n in sorted(states.items(),
                                         key=lambda x: (x[0] or ''))))

    vals = [f.rvol_mod for f in captured_fires if f.rvol_mod is not None]
    if vals:
        # statistics.median averages the two middle values on an even
        # sample; vals_sorted[n // 2] would report the upper middle and
        # skew this headline regression number (Codex review, PR #806).
        med = statistics.median(vals)
        below = sum(1 for v in vals if v < 1.0) / len(vals)
        print(f"Corrected RVOL:  n={len(vals)}/{len(captured_fires)} median "
              f"{med:.2f}  below 1.0 {below:.0%}")
    else:
        print(f"Corrected RVOL:  no values (baseline unavailable for all "
              f"{len(captured_fires)} fires)")

    # Timeframe distribution
    tfs = Counter(f.timeframe_tag for f in captured_fires)
    print("Timeframe distribution:")
    for tf, n in sorted(tfs.items(), key=lambda x: (x[0] or "")):
        pct = (100.0 * n / len(captured_fires))
        print(f"  {str(tf):<8}{n:>6}  ({pct:5.1f}%)")

    # Stacked agreements
    stacked = [f for f in captured_fires if f.strategy_agreement is not None]
    print(f"\nStacked agreements: {len(stacked)} ({100.0 * len(stacked) / len(captured_fires):.1f}% of fires)")
    if stacked:
        for f in stacked[:5]:
            comp = f.strategy_agreement.get("composite_score") if f.strategy_agreement else 0
            print(f"  {f.timestamp} {f.ticker} {f.direction} composite={comp:.1f} {f.embed_title!r}")

    # Sample fires
    print(f"\nSample fires (first 5):")
    for f in captured_fires[:5]:
        print(f"  {f.timestamp} {f.ticker} {f.direction} score={f.base_score} tf={f.timeframe_tag} | {f.embed_title!r}")

    if args.json:
        print()
        print(json.dumps([f.to_dict() for f in captured_fires], default=str, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
