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

from lib.trading_analysis import MarketAnalyzer  # noqa: E402
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


DEFAULT_MAX_TICKERS = 25


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--symbol', help='Ticker symbol (IWM, QQQ, SPY, …)')
    g.add_argument('--from-watchlist', action='store_true',
                   help='Iterate every active ticker in the Cloud SQL watchlists table.')
    p.add_argument('--start-date', help='YYYY-MM-DD inclusive start (overrides MAX(entry_time))')
    p.add_argument('--end-date', help='YYYY-MM-DD exclusive end (default: today)')
    p.add_argument('--backfill-from', help='YYYY-MM-DD inclusive — process from this date forward')
    p.add_argument('--force', action='store_true',
                   help='DELETE all rows for ticker, then re-process from --start-date or --backfill-from')
    p.add_argument('--dry-run', action='store_true', help='Compute signals but do not write to Cloud SQL')
    p.add_argument('--lookback-days', type=int, default=2,
                   help='Extra days BEFORE start to load for indicator warmup (default: 2)')
    p.add_argument(
        '--strategy', choices=['momentum', 'mean_reversion'], default='momentum',
        help=('Which signal-generation strategy to use (Phase 0.7). '
              "'momentum' (default) = MarketAnalyzer.generate_technical_signals "
              "(consec_UP + above_VWAP + above_EMA9 + RSI 25-50 = CALL). "
              "'mean_reversion' = lib.signals.evaluate_signal "
              "(consec_DOWN + below_VWAP + below_EMAs + RSI 25-50 = CALL — "
              "OPPOSITE call logic). The two strategies are complementary; see "
              "docs/plans/SIGNAL_QUALITY_TEST_PLAN.md §3.8-3.9. Each writes its "
              "rows to historical_signals with its strategy tag, and ON CONFLICT "
              "is keyed on (ticker, entry_time, strategy) so they coexist.")
    )
    p.add_argument(
        '--max-tickers', type=int, default=DEFAULT_MAX_TICKERS,
        help=(f'Cap on tickers processed per invocation (default {DEFAULT_MAX_TICKERS}). '
              'Each ticker loads months of intraday bars + runs the full voter, so a '
              'runaway list will OOM the Cloud Run Job. Use --override-max to bypass.'),
    )
    p.add_argument(
        '--override-max', action='store_true',
        help='Bypass --max-tickers cap. Required when running > max-tickers.',
    )
    return p.parse_args()


def _resolve_tickers(args: argparse.Namespace) -> list[str]:
    """Single ticker (--symbol) or whatever's currently active in the
    Cloud SQL watchlists table (--from-watchlist)."""
    if args.symbol:
        return [args.symbol.strip().upper()]
    # --from-watchlist
    try:
        from gcp.fetchers._watchlist import load_watchlist
        return load_watchlist()
    except Exception as exc:
        log.error('watchlist load failed: %s', exc)
        return []


def resolve_window(args: argparse.Namespace) -> tuple[datetime, datetime]:
    """Determine [start, end) bar window to load from market_data_intraday.

    The auto-resume path (no --start-date / --backfill-from) reads
    MAX(entry_time) scoped to the requested ``args.strategy`` so that
    momentum and mean_reversion backfills resume from independent cursors.
    """
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
        # Default: resume from MAX(entry_time) + 1 minute scoped to THIS
        # strategy, or fall back to a 30-day window if the table has no
        # rows yet for this (ticker, strategy) combination.
        last = latest_entry_time(ticker, strategy=args.strategy)
        if last is None:
            log.info('no existing rows for %s [%s] — defaulting to last 30 days',
                     ticker, args.strategy)
            start = end - timedelta(days=30)
        else:
            start = last + timedelta(minutes=1)
            log.info('resuming from MAX(entry_time)=%s [%s]', last, args.strategy)

    return start, end


def map_signals_to_table(signals_df: pd.DataFrame, ticker: str,
                          strategy: str = 'momentum') -> pd.DataFrame:
    """Reshape MarketAnalyzer output into the historical_signals schema.

    Phase 1: also populates timeframe_tag + expected_hold_min via the
    approximate `assign_timeframe_for_backfill` helper, since this
    layer has access to strategy + signal_strength but NOT RVOL or
    ATR at the per-signal level. Same limitation as the backfill
    script — see lib/strategies/timeframe.py for the full doc.
    """
    if signals_df.empty:
        return signals_df

    out_cols = {}
    for src, dest in SIGNAL_COLUMN_MAP.items():
        if src in signals_df.columns:
            out_cols[dest] = signals_df[src]

    out = pd.DataFrame(out_cols)
    out['ticker'] = ticker
    out['strategy'] = strategy   # Phase 0.7
    out['entry_time'] = pd.to_datetime(out['entry_time'], utc=True)
    if 'entry_volume' in out.columns:
        # Cast NaN-tolerant int — keep nullable
        out['entry_volume'] = out['entry_volume'].astype('Int64')

    # Phase 1: timeframe tagging on every research-pipeline row.
    # signals_df has entry_rsi at the per-row level. Pass it through
    # so the empirical lookup (EMPIRICAL_LOOKUP in
    # lib/strategies/timeframe.py) hits the populated buckets instead
    # of cold-starting on the rsi='unknown' bucket. ATR is still
    # unavailable at this layer (no per-row snapshot in signals_df).
    from lib.strategies.timeframe import assign_timeframe_for_backfill
    if 'signal_strength' in out.columns:
        rsi_series = out['entry_rsi'] if 'entry_rsi' in out.columns else None
        tags_holds = []
        for i in range(len(out)):
            ss = out['signal_strength'].iloc[i]
            rsi = rsi_series.iloc[i] if rsi_series is not None else None
            tags_holds.append(assign_timeframe_for_backfill(
                strategy=strategy,
                signal_strength=int(ss) if pd.notna(ss) else None,
                atr_5m_pct=None,
                entry_rsi=float(rsi) if rsi is not None and pd.notna(rsi) else None,
            ))
        out['timeframe_tag'] = [t for t, _ in tags_holds]
        out['expected_hold_min'] = [h for _, h in tags_holds]
    else:
        out['timeframe_tag'] = None
        out['expected_hold_min'] = None

    # Phase 1.5: catalyst proximity per row. The lru_cache in
    # get_catalyst_context collapses repeat lookups within the same
    # 5-min bucket on the same ticker — so a research run over a
    # full month of intraday signals does at most ~12 DB queries per
    # ticker per day rather than one per signal. Lookup failure
    # (no DB / table absent) is non-fatal — returns EMPTY_CONTEXT
    # → proximity_bucket='quiet', the rest NULL.
    from lib.strategies.catalyst_proximity import get_catalyst_context
    proximity_keys = (
        'next_catalyst_min', 'next_catalyst_type',
        'last_catalyst_min', 'last_catalyst_type',
        'catalyst_session', 'proximity_bucket',
    )
    if 'entry_time' in out.columns and len(out) > 0:
        ctxs = [get_catalyst_context(ticker, ts) for ts in out['entry_time']]
        for k in proximity_keys:
            out[k] = [c.get(k) for c in ctxs]
    else:
        for k in proximity_keys:
            out[k] = None

    # Bundle every "extra" column into the JSONB blob
    extra_cols = [c for c in signals_df.columns if c.startswith(EXTRA_PREFIXES)]
    if extra_cols:
        extras = signals_df[extra_cols].to_dict(orient='records')
        out['extra'] = extras
    else:
        out['extra'] = None

    return out


def _add_mean_reversion_extra_cols(df: pd.DataFrame) -> pd.DataFrame:
    """MarketAnalyzer's add_technical_indicators emits column names that don't
    match what lib.signals.evaluate_signal expects. Bridge the gap so we don't
    have to refactor either side mid-flight.

    - RSI14_W → also expose as RSI14 (lib.signals reads ind.rsi_col = 'RSI14')
    - Derive Price_vs_VWAP, Price_vs_EMA9, Price_vs_EMA20
    - Derive Consecutive_Up, Consecutive_Down (streak counter, not rolling sum)
    - Alias Last → Close (lib.signals checks both)
    """
    import numpy as np
    if 'RSI14_W' in df.columns and 'RSI14' not in df.columns:
        df['RSI14'] = df['RSI14_W']
    df['Price_vs_VWAP']  = (df['Last'] - df['VWAP']) / df['VWAP']  * 100
    df['Price_vs_EMA9']  = (df['Last'] - df['EMA9']) / df['EMA9']  * 100
    df['Price_vs_EMA20'] = (df['Last'] - df['EMA20']) / df['EMA20'] * 100
    ret = df['Last'].diff()
    cu = (ret > 0).astype(int)
    cd = (ret < 0).astype(int)
    # Streak counter via cumcount on grouped runs
    df['Consecutive_Up']   = cu * (cu.groupby((cu != cu.shift()).cumsum()).cumcount() + 1)
    df['Consecutive_Down'] = cd * (cd.groupby((cd != cd.shift()).cumsum()).cumcount() + 1)
    if 'Close' not in df.columns:
        df['Close'] = df['Last']
    return df


def _generate_mean_reversion_signals(enriched: pd.DataFrame) -> pd.DataFrame:
    """Run lib.signals.evaluate_signal on the indicator-enriched bars
    and return a DataFrame in the same shape MarketAnalyzer produces
    (so map_signals_to_table can be reused).

    The lib.signals output is a list of {direction, base_score, total_score,
    conditions_met, time, price, ...} dicts. We map:
      direction  → trade_type (lower-cased)
      time       → entry_time
      price      → entry_price
      total_score → signal_strength
      conditions_met → JSON-serialized conditions list (matching what
                       signal_alerts already stores for the live monitor)
    """
    import json as _json
    import numpy as np
    from lib.signals import generate_signals
    from lib.config import IndicatorConfig

    enriched_with_extras = _add_mean_reversion_extra_cols(enriched.copy())
    raw = generate_signals(enriched_with_extras, min_conditions=3,
                            consecutive_periods=3,
                            indicator_config=IndicatorConfig())
    if raw is None or len(raw) == 0:
        return pd.DataFrame()

    out_rows = []
    for _, sig in raw.iterrows():
        out_rows.append({
            'entry_time': sig.get('time'),
            'trade_type': sig['direction'].lower(),  # 'CALL' → 'call' to match momentum schema
            'entry_price': float(sig['price']),
            'signal_strength': int(sig['total_score']),
            'conditions_met': _json.dumps(sig['conditions_met']),
            'duration_minutes': None,
            'return_pct': None,
            'best_return': None,
            'best_window_minutes': None,
            'return_5min': None,
            'return_10min': None,
            'return_15min': None,
            'return_20min': None,
            'return_30min': None,
            'return_45min': None,
            'return_60min': None,
            'entry_rsi': float(sig['rsi']) if 'rsi' in sig.index and pd.notna(sig['rsi']) else None,
            'entry_ema9': float(sig['ema_fast']) if 'ema_fast' in sig.index and pd.notna(sig['ema_fast']) else None,
            'entry_ema20': float(sig['ema_mid']) if 'ema_mid' in sig.index and pd.notna(sig['ema_mid']) else None,
            'entry_vwap': float(sig['vwap']) if 'vwap' in sig.index and pd.notna(sig['vwap']) else None,
            'entry_volume': None,
        })
    return pd.DataFrame(out_rows)


def _process_ticker(ticker: str, args: argparse.Namespace) -> int:
    """Process one ticker. Returns 0 on success, non-zero on hard error.
    Soft cases (no bars / no signals / window already covered) are 0."""
    if args.force:
        if not (args.start_date or args.backfill_from):
            log.warning(
                '--force without --start-date or --backfill-from will reprocess '
                'only from MAX(entry_time)=NULL → last 30 days. Probably not what you want.'
            )
        n = delete_for_ticker(ticker, strategy=args.strategy)
        log.info('--force: deleted %d existing rows for %s strategy=%s',
                 n, ticker, args.strategy)

    # `resolve_window` reads args.symbol — patch it through for this ticker
    # in the watchlist iteration path.
    args.symbol = ticker
    start, end = resolve_window(args)
    if start >= end:
        log.info('  %s: window [%s, %s) empty — already up-to-date', ticker, start, end)
        return 0

    load_start = start - timedelta(days=args.lookback_days)
    log.info('  %s [%s]: loading bars [%s → %s) (warmup from %s)',
             ticker, args.strategy, start, end, load_start)
    bars = load_intraday_bars(ticker, load_start, end)
    log.info('  %s: loaded %d bars', ticker, len(bars))

    if len(bars) < 30:
        log.warning('  %s: only %d bars — skipping (need >= 30 for indicators)',
                    ticker, len(bars))
        return 0

    log.info('  %s: computing indicators (shared across strategies)', ticker)
    analyzer = MarketAnalyzer()
    enriched = analyzer.add_technical_indicators(bars)

    # Dispatch by strategy. Both share `enriched` so indicator computation
    # only happens once even when both strategies are backfilled in sequence.
    if args.strategy == 'momentum':
        log.info('  %s: running MarketAnalyzer.generate_technical_signals (momentum)', ticker)
        signals_df = analyzer.generate_technical_signals(enriched)
    elif args.strategy == 'mean_reversion':
        log.info('  %s: running lib.signals.evaluate_signal (mean_reversion)', ticker)
        signals_df = _generate_mean_reversion_signals(enriched)
    else:
        log.error('unknown strategy: %s', args.strategy)
        return 1

    log.info('  %s: voter produced %d candidate signals', ticker, len(signals_df))
    if signals_df.empty:
        return 0

    entry_ts = pd.to_datetime(signals_df['entry_time'], utc=True)
    signals_df = signals_df.loc[(entry_ts >= start) & (entry_ts < end)].copy()
    log.info('  %s: %d signals after window trim', ticker, len(signals_df))

    if signals_df.empty:
        return 0

    table_df = map_signals_to_table(signals_df, ticker, strategy=args.strategy)
    if args.dry_run:
        log.info('  %s: --dry-run, would insert %d rows (strategy=%s)',
                 ticker, len(table_df), args.strategy)
        return 0

    attempted, inserted = bulk_insert(table_df)
    log.info('  %s [%s]: done attempted=%d inserted=%d skipped=%d',
             ticker, args.strategy, attempted, inserted, attempted - inserted)
    return 0


def main() -> int:
    args = parse_args()

    tickers = _resolve_tickers(args)
    if not tickers:
        log.error('no tickers — set --symbol or populate the Cloud SQL watchlist')
        return 2

    if len(tickers) > args.max_tickers and not args.override_max:
        log.error(
            'refusing to process %d tickers (max-tickers=%d). '
            'Use --override-max=1 to bypass. tickers=%s',
            len(tickers), args.max_tickers, tickers,
        )
        return 1

    log.info('historical_signals batch — %d ticker(s): %s',
             len(tickers), ', '.join(tickers))

    failures: list[str] = []
    for tk in tickers:
        try:
            rc = _process_ticker(tk, args)
            if rc != 0:
                failures.append(tk)
        except Exception as exc:
            log.exception('  %s: unexpected error: %s', tk, exc)
            failures.append(tk)

    if failures:
        log.warning('completed with %d ticker failure(s): %s', len(failures), failures)
        return 0  # don't fail the whole batch on one ticker
    return 0


if __name__ == '__main__':
    sys.exit(main())
