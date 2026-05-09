"""End-of-day reconciler for signal_alerts that the live monitor never closed.

Track A G.P0.10. The live signal_monitor (`gcp/signal_monitor.py`) only
walks open positions while the market-hours loop is alive. If the
container crashes, restarts, or simply hits market close before any
exit condition fires, the alert row stays `is_open = TRUE` /
`exit_ts = NULL` forever. The audit found ~1,209 such rows by
2026-05-08.

This script reconciles them by replaying the same exit logic over the
1-min intraday bars from `alert_ts` through market close (16:00 ET) of
the alert's date, using `lib.exit_replay`. If a target/time/RSI
condition would have fired live, the row is updated with the
corresponding `exit_reason`. Otherwise it's marked `eod_close`.

Usage:
    python -m gcp.signal_monitor_eod_resolver                    # last 30 days
    python -m gcp.signal_monitor_eod_resolver --lookback-days 60 # backfill
    python -m gcp.signal_monitor_eod_resolver --dry-run          # report only

Idempotent: re-running on a fully-reconciled window updates 0 rows.
The Cloud Scheduler invocation runs at 16:30 ET on weekdays so that
the daily fetcher's intraday landing (which happens by 21:00 UTC) is
NOT a precondition; the script reads only what's already persisted.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.exit_replay import (  # noqa: E402
    PERSIST_EXIT_SQL,
    Position,
    persist_exit_params,
    simulate_exit,
)

logger = logging.getLogger(__name__)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconcile open signal_alerts using EOD intraday replay."
    )
    parser.add_argument(
        '--lookback-days', type=int, default=30,
        help='Reconcile alerts whose alert_date is within the last N days '
             '(default: 30). Use a larger value for one-shot backfill.',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Compute exits but do not write UPDATEs. Logs the resolved '
             'count per ticker and exits 0.',
    )
    parser.add_argument(
        '--rsi-col', default='rsi_14',
        help='Column in market_data_intraday holding the RSI series '
             '(default: rsi_14).',
    )
    parser.add_argument(
        '--call-rsi-exit', type=float, default=80.0,
        help='RSI threshold above which an open CALL exits (default: 80).',
    )
    parser.add_argument(
        '--put-rsi-exit', type=float, default=20.0,
        help='RSI threshold below which an open PUT exits (default: 20).',
    )
    return parser.parse_args(argv)


# ── Pure helpers (no DB) ──────────────────────────────────────────────


def open_alerts_sql() -> str:
    """Returns alerts that need reconciliation: still flagged open OR
    missing an exit_ts. The OR catches both legacy rows (no is_open)
    and the live monitor's "is_open = TRUE" rows."""
    return """
        SELECT id, ticker, alert_ts, alert_date, direction,
               price_at_signal, target_price, time_stop_minutes
          FROM signal_alerts
         WHERE alert_date >= :cutoff_date
           AND (is_open IS NOT FALSE OR exit_ts IS NULL)
         ORDER BY alert_ts
    """


def intraday_bars_sql() -> str:
    """Return 1-min bars from alert_ts through market close (16:00 ET)
    on the alert's date.

    Two timezone subtleties:

    1. `market_data_intraday.ts` is stored as **naive ET** — the AV
       writer in `gcp/fetchers/fetch_market_data.py` strips the tz tag
       and stores the AV-returned ET timestamp as-is (the "ET-as-UTC"
       convention the frontend RTH filter relies on). Comparing it
       against a UTC `alert_ts` is wrong: a 10:00 ET alert stored as
       14:00 UTC would skip every bar before 14:00 (which is 14:00 ET,
       4 hours after market close).

    2. The schema only carries OHLCV columns (no rsi_14). RSI is
       computed downstream from the close series via
       `lib.indicators.calculate_rsi` after the bars load.

    Both `:alert_ts_et` and `:alert_close_et` MUST be naive ET; the
    callers convert before binding.
    """
    return """
        SELECT ts, close
          FROM market_data_intraday
         WHERE ticker = :ticker
           AND interval = '1min'
           AND ts >= :alert_ts_et
           AND ts <= :alert_close_et
         ORDER BY ts
    """


def _alert_ts_to_et_naive(alert_ts) -> datetime:
    """Convert a `signal_alerts.alert_ts` (TIMESTAMPTZ stored as UTC,
    or already-naive UTC) to naive ET to match the
    `market_data_intraday.ts` storage convention."""
    from zoneinfo import ZoneInfo
    if hasattr(alert_ts, 'tzinfo') and alert_ts.tzinfo is not None:
        # tz-aware → ET
        return alert_ts.astimezone(ZoneInfo("America/New_York")).replace(tzinfo=None)
    # Assume naive UTC, attach UTC, convert to ET
    return alert_ts.replace(tzinfo=timezone.utc).astimezone(
        ZoneInfo("America/New_York")).replace(tzinfo=None)


def _alert_close_ts(alert_date) -> datetime:
    """Market close (16:00 ET) for the alert's date, returned as a
    NAIVE ET timestamp to match `market_data_intraday.ts` storage.

    Earlier versions of this function returned naive UTC, which
    DESYNCHRONIZES against the intraday writer's ET-as-UTC convention
    and silently dropped 4–5 hours of bars per alert. Fixed in PR #324
    after codex review caught the off-by-tz bug."""
    return datetime.combine(alert_date, datetime.min.time()).replace(
        hour=16, minute=0)


def _row_to_position(row: dict) -> Position:
    """Translate a signal_alerts row into a Position for replay.

    `Position.alert_ts` carries naive UTC (matches the rest of the
    system's lib.exit_replay convention). The intraday-bar query uses
    `_alert_ts_to_et_naive` for the ET-bound parameter so the SQL
    range-filter aligns with the intraday writer's storage."""
    alert_ts = row['alert_ts']
    if hasattr(alert_ts, 'tzinfo') and alert_ts.tzinfo is not None:
        alert_ts = alert_ts.astimezone(timezone.utc).replace(tzinfo=None)
    return Position(
        ticker=row['ticker'],
        direction=row['direction'],
        alert_ts=alert_ts,
        entry_price=float(row['price_at_signal']),
        target_price=float(row['target_price']),
        time_stop_minutes=int(row['time_stop_minutes']),
    )


# ── Main loop ─────────────────────────────────────────────────────────


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    args = parse_args(argv)

    from gcp.database import get_engine, is_cloud_sql_configured, query_to_dataframe

    if not is_cloud_sql_configured():
        logger.error("Cloud SQL not configured — set CLOUD_SQL_CONNECTION_NAME, DB_USER, DB_PASS, DB_NAME")
        return 2

    cutoff_date = (datetime.now(timezone.utc).date() - timedelta(days=args.lookback_days))
    logger.info("EOD reconciler: lookback=%d days, cutoff_date=%s, dry_run=%s",
                args.lookback_days, cutoff_date, args.dry_run)

    open_df = query_to_dataframe(open_alerts_sql(), {'cutoff_date': cutoff_date})
    if open_df.empty:
        logger.info("No open alerts to reconcile.")
        return 0

    logger.info("Found %d open alerts in window.", len(open_df))

    engine = get_engine()
    resolved = {'target_hit': 0, 'time_stop': 0, 'rsi_extreme': 0,
                'eod_close': 0, 'no_bars': 0, 'partial_data': 0}

    from sqlalchemy import text
    update_sql = text(PERSIST_EXIT_SQL)

    from lib.indicators import calculate_rsi
    from zoneinfo import ZoneInfo
    _UTC = ZoneInfo("UTC")
    _ET = ZoneInfo("America/New_York")

    for row in open_df.to_dict('records'):
        pos = _row_to_position(row)
        # Convert UTC alert_ts → naive ET for the SQL range filter
        # (market_data_intraday.ts is naive ET — see intraday_bars_sql doc).
        alert_ts_et = _alert_ts_to_et_naive(row['alert_ts'])
        close_ts_et = _alert_close_ts(row['alert_date'])
        bars = query_to_dataframe(intraday_bars_sql(), {
            'ticker': pos.ticker,
            'alert_ts_et': alert_ts_et,
            'alert_close_et': close_ts_et,
        })

        if bars is None or bars.empty:
            resolved['no_bars'] += 1
            logger.warning("No intraday bars for %s after %s ET through %s ET; skipping.",
                           pos.ticker, alert_ts_et, close_ts_et)
            continue

        # Bars come back with naive ET timestamps. Compute RSI on the
        # close series (the schema doesn't carry an rsi_14 column —
        # see intraday_bars_sql doc) and re-anchor ts to naive UTC so
        # simulate_exit's elapsed-minute math against pos.alert_ts
        # (naive UTC) lines up.
        bars = bars.copy()
        bars['rsi_14'] = calculate_rsi(bars['close'], period=14)
        bars['ts'] = (
            pd.to_datetime(bars['ts'])
              .dt.tz_localize(_ET, ambiguous='infer', nonexistent='shift_forward')
              .dt.tz_convert(_UTC)
              .dt.tz_localize(None)
        )

        event = simulate_exit(
            pos, bars,
            rsi_col=args.rsi_col,
            call_rsi_exit=args.call_rsi_exit,
            put_rsi_exit=args.put_rsi_exit,
        )
        if event is None:
            resolved['partial_data'] += 1
            logger.warning("Partial intraday data for %s @ %s "
                           "(last bar before market close); will retry tomorrow.",
                           pos.ticker, pos.alert_ts)
            continue

        resolved[event.exit_reason] = resolved.get(event.exit_reason, 0) + 1

        if not args.dry_run:
            with engine.begin() as conn:
                conn.execute(update_sql, persist_exit_params(pos, event))

    logger.info("Reconciliation summary: %s", resolved)
    return 0


if __name__ == "__main__":
    sys.exit(main())
