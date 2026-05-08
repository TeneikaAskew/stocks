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
    """1-min bars from alert_ts through market close (20:00 UTC = 16:00
    ET) of the alert's date."""
    return """
        SELECT ts, close, rsi_14
          FROM market_data_intraday
         WHERE ticker = :ticker
           AND interval = '1min'
           AND ts >= :alert_ts
           AND ts <= :alert_close_ts
         ORDER BY ts
    """


def _alert_close_ts(alert_date) -> datetime:
    """Market close (16:00 ET) for the alert's date, returned as a naive
    UTC timestamp matching the rest of the system. ET 16:00 = 20:00 UTC
    during EST and 20:00 UTC during EDT — wait, that's wrong.

    EDT (Mar–Nov): 16:00 ET = 20:00 UTC.
    EST (Nov–Mar): 16:00 ET = 21:00 UTC.

    Use zoneinfo to get the exact UTC instant rather than a naive
    arithmetic shift.
    """
    from zoneinfo import ZoneInfo
    et_close = datetime.combine(alert_date, datetime.min.time()).replace(
        hour=16, minute=0, tzinfo=ZoneInfo("America/New_York"))
    return et_close.astimezone(timezone.utc).replace(tzinfo=None)


def _row_to_position(row: dict) -> Position:
    """Translate a signal_alerts row into a Position for replay."""
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

    for row in open_df.to_dict('records'):
        pos = _row_to_position(row)
        close_ts = _alert_close_ts(row['alert_date'])
        bars = query_to_dataframe(intraday_bars_sql(), {
            'ticker': pos.ticker,
            'alert_ts': pos.alert_ts,
            'alert_close_ts': close_ts,
        })

        if bars is None or bars.empty:
            resolved['no_bars'] += 1
            logger.warning("No intraday bars for %s after %s through %s; skipping.",
                           pos.ticker, pos.alert_ts, close_ts)
            continue

        # Normalize ts to naive UTC — query_to_dataframe may return tz-aware
        if hasattr(bars['ts'].iloc[0], 'tzinfo') and bars['ts'].iloc[0].tzinfo is not None:
            bars = bars.assign(ts=pd.to_datetime(bars['ts'], utc=True).dt.tz_localize(None))

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
