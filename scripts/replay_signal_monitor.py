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
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pandas as pd

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

    def to_dict(self) -> dict:
        return {
            "timestamp":          self.timestamp.isoformat(),
            "ticker":             self.ticker,
            "direction":          self.direction,
            "base_score":         self.base_score,
            "total_score":        self.total_score,
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
) -> tuple[int, int]:
    """Replay one ticker's bars through the live monitor code path.

    For each bar T, append it to the rolling window then call
    evaluate_ticker. The monitor's existing logic computes indicators,
    runs both strategies, detects agreement, assigns timeframe, and
    (with our patches) calls a stub fire_alert that captures the fire
    instead of actually posting to Discord.

    Returns (bars_processed, signals_fired).
    """
    if bars.empty:
        return (0, 0)

    fires_before = len(captured_fires)

    # Rolling-window replay: feed bars one at a time so the monitor
    # operates on the same shape it sees in production (1-bar deltas).
    for i in range(len(bars)):
        single_bar = bars.iloc[i:i + 1].copy()
        monitor.update_window(ticker, single_bar)
        try:
            monitor.evaluate_ticker(ticker)
        except Exception as e:
            logger.warning("replay: ticker=%s bar=%d evaluate_ticker raised: %s",
                           ticker, i, e)

    fires_after = len(captured_fires)
    return (len(bars), fires_after - fires_before)


def make_capturing_fire_alert(captured: list[FireRecord], monitor):
    """Replace SignalMonitor.fire_alert with a callable that captures
    the fire into `captured` instead of posting to Discord / Cloud SQL.
    """
    def _capture(self, ticker, sig, total_score, strength, size, strat_bonus, latest):
        agreement = getattr(self, "_latest_agreement", None)
        tf_tag = getattr(self, "_latest_timeframe_tag", None)
        tf_hold = getattr(self, "_latest_expected_hold_min", None)
        title_prefix = "STACKED " if agreement else ""
        tf_label = f" [{tf_tag}]" if tf_tag else ""
        title = (
            f"{title_prefix}{sig['direction']} SIGNAL{tf_label} "
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
        ))
    return _capture


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--ticker", help="Single ticker to replay (alias for --tickers TICKER)")
    p.add_argument("--tickers", help="Comma-separated tickers (overrides --ticker)")
    p.add_argument("--date", help="Single trading date YYYY-MM-DD (alias for --start = --end)")
    p.add_argument("--start", help="UTC start date YYYY-MM-DD")
    p.add_argument("--end", help="UTC end date YYYY-MM-DD (exclusive)")
    p.add_argument("--limit", type=int, default=None,
                   help="Max bars per ticker (debug/dev)")
    p.add_argument("--json", action="store_true",
                   help="Print fires as a JSON array (machine-readable)")
    return p.parse_args(argv)


def resolve_window(args: argparse.Namespace) -> tuple[datetime, datetime]:
    if args.date:
        d = date.fromisoformat(args.date)
        return (
            datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
            datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1),
        )
    if args.start and args.end:
        s = date.fromisoformat(args.start)
        e = date.fromisoformat(args.end)
        return (
            datetime(s.year, s.month, s.day, tzinfo=timezone.utc),
            datetime(e.year, e.month, e.day, tzinfo=timezone.utc),
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

    logger.info("replay window: %s -> %s tickers=%s", start, end, tickers)

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

        for ticker in tickers:
            bars = load_intraday_for_replay(engine, ticker, start, end)
            if args.limit:
                bars = bars.head(args.limit)
            logger.info("ticker=%s loaded %d bars", ticker, len(bars))
            n_bars, n_fires = replay_ticker(monitor, ticker, bars, captured_fires)
            summary_per_ticker[ticker] = (n_bars, n_fires)

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
