#!/usr/bin/env python3
"""
Run trading_analysis.py's signal voter against Cloud SQL bars and insert
results into the ``historical_signals`` table.

Replaces the parquet-based ``python trading_analysis.py --symbol X`` flow
with an idempotent Cloud SQL one. Re-running over a date range that's
already been processed is a no-op.

Examples
--------
    # default: process from MAX(entry_time) → today, ON CONFLICT skip
    python scripts/run_historical_signals.py --symbol IWM

    # explicit window
    python scripts/run_historical_signals.py --symbol IWM \
        --start-date 2024-01-01 --end-date 2024-03-31

    # full backfill (deletes existing rows for ticker first)
    python scripts/run_historical_signals.py --symbol IWM --force

    # one-shot backfill from earlier date than MAX(entry_time)
    python scripts/run_historical_signals.py --symbol IWM \
        --backfill-from 2015-06-01
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

# Repo root on path so we can import trading_analysis + gcp
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trading_analysis import MarketAnalyzer  # noqa: E402
from gcp.historical_signals import (  # noqa: E402
    bulk_insert,
    delete_for_ticker,
    latest_entry_time,
    load_intraday_bars,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

# Columns from MarketAnalyzer's signals_df → historical_signals table
SIGNAL_COLUMN_MAP = {
    'entry_time': 'entry_time',
    'trade_type': 'trade_type',
    'entry_price': 'entry_price',
    'signal_strength': 'signal_strength',
    'conditions_met': 'conditions_met',
    'duration_minutes': 'duration_minutes',
    'return_pct': 'return_pct',
    'best_return': 'best_return',
    'best_window_minutes': 'best_window_min',
    'return_5min': 'return_5min',
    'return_10min': 'return_10min',
    'return_15min': 'return_15min',
    'return_20min': 'return_20min',
    'return_30min': 'return_30min',
    'return_45min': 'return_45min',
    'return_60min': 'return_60min',
    'entry_rsi': 'entry_rsi',
    'entry_ema9': 'entry_ema9',
    'entry_ema20': 'entry_ema20',
    'entry_vwap': 'entry_vwap',
    'entry_volume': 'entry_volume',
}

# Columns to capture into the JSONB ``extra`` blob — everything in the
# signals_df that isn't a flat column gets bundled here so the parquet
# parity is preserved without bloating the table.
EXTRA_PREFIXES = (
    'entry_prev_', 'entry_vs_prev_', 'entry_broke_prev_', 'entry_at_prev_',
    'entry_orb_', 'entry_order_block_', 'entry_stochrsi_', 'entry_atr',
    'entry_obv', 'exit_',
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--symbol', required=True, help='Ticker symbol (IWM, QQQ, SPY, …)')
    p.add_argument('--start-date', help='YYYY-MM-DD inclusive start (overrides MAX(entry_time))')
    p.add_argument('--end-date', help='YYYY-MM-DD exclusive end (default: today)')
    p.add_argument('--backfill-from', help='YYYY-MM-DD inclusive — process from this date forward')
    p.add_argument('--force', action='store_true',
                   help='DELETE all rows for ticker, then re-process from --start-date or --backfill-from')
    p.add_argument('--dry-run', action='store_true', help='Compute signals but do not write to Cloud SQL')
    p.add_argument('--lookback-days', type=int, default=2,
                   help='Extra days BEFORE start to load for indicator warmup (default: 2)')
    return p.parse_args()


def resolve_window(args: argparse.Namespace) -> tuple[datetime, datetime]:
    """Determine [start, end) bar window to load from market_data_intraday."""
    ticker = args.symbol.upper()

    if args.end_date:
        end = datetime.fromisoformat(args.end_date).replace(tzinfo=timezone.utc)
    else:
        end = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)  # exclusive

    if args.start_date:
        start = datetime.fromisoformat(args.start_date).replace(tzinfo=timezone.utc)
    elif args.backfill_from:
        start = datetime.fromisoformat(args.backfill_from).replace(tzinfo=timezone.utc)
    else:
        # Default: resume from MAX(entry_time) + 1 minute, or fall back
        # to a 30-day window if the table is empty for this ticker.
        last = latest_entry_time(ticker)
        if last is None:
            log.info('no existing rows for %s — defaulting to last 30 days', ticker)
            start = end - timedelta(days=30)
        else:
            start = last + timedelta(minutes=1)
            log.info('resuming from MAX(entry_time)=%s', last)

    return start, end


def map_signals_to_table(signals_df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Reshape MarketAnalyzer output into the historical_signals schema."""
    if signals_df.empty:
        return signals_df

    out_cols = {}
    for src, dest in SIGNAL_COLUMN_MAP.items():
        if src in signals_df.columns:
            out_cols[dest] = signals_df[src]

    out = pd.DataFrame(out_cols)
    out['ticker'] = ticker
    out['entry_time'] = pd.to_datetime(out['entry_time'], utc=True)
    if 'entry_volume' in out.columns:
        # Cast NaN-tolerant int — keep nullable
        out['entry_volume'] = out['entry_volume'].astype('Int64')

    # Bundle every "extra" column into the JSONB blob
    extra_cols = [c for c in signals_df.columns if c.startswith(EXTRA_PREFIXES)]
    if extra_cols:
        extras = signals_df[extra_cols].to_dict(orient='records')
        out['extra'] = extras
    else:
        out['extra'] = None

    return out


def main() -> int:
    args = parse_args()
    ticker = args.symbol.upper()

    if args.force:
        if not (args.start_date or args.backfill_from):
            log.warning(
                '--force without --start-date or --backfill-from will reprocess '
                'only from MAX(entry_time)=NULL → last 30 days. Probably not what you want.'
            )
        n = delete_for_ticker(ticker)
        log.info('--force: deleted %d existing rows for %s', n, ticker)

    start, end = resolve_window(args)
    if start >= end:
        log.info('start (%s) >= end (%s) — nothing to do, table is up-to-date', start, end)
        return 0

    # Indicator warmup — load extra days before `start` so RSI/EMA/etc.
    # have history. The signals voter still skips bars before `start`.
    load_start = start - timedelta(days=args.lookback_days)

    log.info('loading bars %s [%s → %s) (warmup from %s)', ticker, start, end, load_start)
    bars = load_intraday_bars(ticker, load_start, end)
    log.info('loaded %d bars', len(bars))

    if len(bars) < 30:
        log.warning('only %d bars loaded — not enough for indicators, exiting', len(bars))
        return 0

    log.info('running MarketAnalyzer (indicators + signal voter)')
    analyzer = MarketAnalyzer()
    enriched = analyzer.add_technical_indicators(bars)
    signals_df = analyzer.generate_technical_signals(enriched)
    log.info('voter produced %d candidate signals', len(signals_df))

    if signals_df.empty:
        log.info('no signals fired in window — exiting clean')
        return 0

    # Trim to entries strictly within the requested window. Normalize the
    # signals_df timestamps to tz-aware UTC so the comparison with the
    # tz-aware window bounds doesn't blow up.
    entry_ts = pd.to_datetime(signals_df['entry_time'], utc=True)
    signals_df = signals_df.loc[(entry_ts >= start) & (entry_ts < end)].copy()
    log.info('after window trim: %d signals to insert', len(signals_df))

    if signals_df.empty:
        return 0

    table_df = map_signals_to_table(signals_df, ticker)

    if args.dry_run:
        log.info('--dry-run: would insert %d rows. Sample:', len(table_df))
        log.info('\n%s', table_df.head(3).to_string())
        return 0

    attempted, inserted = bulk_insert(table_df)
    log.info('done: attempted=%d inserted=%d skipped=%d',
             attempted, inserted, attempted - inserted)
    return 0


if __name__ == '__main__':
    sys.exit(main())
