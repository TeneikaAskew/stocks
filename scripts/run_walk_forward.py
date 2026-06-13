#!/usr/bin/env python3
"""
CLI runner for walk-forward validation on a single ticker.

Mirrors scripts/run_backtest.py — loads data via DataLoader, runs
WalkForwardValidator, then persists per-fold aggregate metrics to the
backtest_walk_forward_folds Cloud SQL table. The persisted rows are the
canonical hand-off to generate_backtest_report.py's
``_section_walk_forward``.

Usage:
    python scripts/run_walk_forward.py --ticker IWM
    python scripts/run_walk_forward.py --ticker IWM --use-strat
    python scripts/run_walk_forward.py --ticker SPY --train-months 12 \
            --test-months 3 --run-id <existing-uuid>
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from lib.data_loader import DataLoader
from lib.indicators import add_all_indicators
from lib.config import load_config
from lib.walk_forward import WalkForwardValidator, WalkForwardResult


# Per-fold metric column names in the backtest_walk_forward_folds table.
# Mapped from BacktestResult.metrics() keys.
_METRIC_MAP = {
    'total_trades': 'total_trades',
    'win_rate': 'win_rate',
    'profit_factor': 'profit_factor',
    'expectancy_pct': 'expectancy',
    'sharpe_ratio': 'sharpe',
    'max_drawdown_pct': 'max_dd',
    'avg_win_pct': 'avg_win',
    'avg_loss_pct': 'avg_loss',
}

# INTEGER-typed columns in backtest_walk_forward_folds. The float-widening
# fix from run_backtest.py:persist_trades applies here too — when a fold
# returns zero trades, derived metrics are NaN which widens the column
# dtype to float64 and breaks pg8000's INTEGER bind.
_INT_COLS = ('fold_index', 'total_trades')


def _wf_result_to_dataframe(
    wf_result: WalkForwardResult,
    run_id: str,
    ticker: str,
    use_strat: bool,
    mode_label: str | None = None,
) -> pd.DataFrame:
    """Build one row per fold from a WalkForwardResult.

    stability_score is denormalised across all rows for the same
    (run_id, ticker, mode) — see schema comment.

    ``mode_label`` (when provided) overrides the default 'strat'/'base'
    label persisted to the ``mode`` column. This is what lets the
    calibration orchestrator distinguish multiple parallel strat
    variants in the same table (e.g. mode='s_noorb', mode='s_call'
    instead of all rolling up to mode='strat').
    """
    rows: list[dict] = []
    mode = mode_label or ('strat' if use_strat else 'base')
    for fold_idx, (result, dates) in enumerate(
        zip(wf_result.fold_results, wf_result.fold_dates)
    ):
        m = result.metrics()
        row: dict = {
            'run_id': run_id,
            'ticker': ticker,
            'use_strat': bool(use_strat),
            'mode': mode,
            'fold_index': fold_idx,
            'train_start': pd.Timestamp(dates['train_start']).date(),
            'train_end': pd.Timestamp(dates['train_end']).date(),
            'test_start': pd.Timestamp(dates['test_start']).date(),
            'test_end': pd.Timestamp(dates['test_end']).date(),
            'stability_score': wf_result.stability_score,
        }
        for src_key, dest_col in _METRIC_MAP.items():
            v = m.get(src_key)
            row[dest_col] = v
        rows.append(row)
    return pd.DataFrame(rows)


def persist_walk_forward(
    wf_df: pd.DataFrame,
    run_id: str,
    ticker: str,
    use_strat: bool,
) -> int:
    """Write per-fold walk-forward metrics to the
    backtest_walk_forward_folds Cloud SQL table.

    The natural key (run_id, ticker, mode, fold_index) is unique so a
    re-run with the same run_id converges via ON CONFLICT DO UPDATE
    rather than appending duplicates.

    Returns the number of rows written. Raises on Cloud SQL failure —
    the table is the canonical path, so a write failure must surface
    (per CLAUDE.md §3.7: no silent fallbacks in data-access code).
    """
    from gcp.database import upsert_dataframe

    if wf_df.empty:
        return 0

    df = wf_df.copy()

    # INT-coercion guard — mirrors run_backtest.py:persist_trades. Any
    # fold with zero trades produces NaN-widening; per-value coercion
    # restores int / None semantics so pg8000 binds INTEGER columns
    # correctly. Building the list manually + dtype=object is required
    # because pd.Series.apply() on a float column re-widens None back
    # to NaN — destroying the int/None distinction the table relies
    # on (Postgres NULL vs INTEGER 0 are not interchangeable).
    for col in _INT_COLS:
        if col in df.columns:
            coerced: list = []
            for v in df[col]:
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    coerced.append(None)
                else:
                    coerced.append(int(v))
            df[col] = pd.Series(coerced, dtype=object, index=df.index)

    return upsert_dataframe(
        df,
        table='backtest_walk_forward_folds',
        conflict_cols=['run_id', 'ticker', 'mode', 'fold_index'],
    )


def _print_fold_summary(wf_df: pd.DataFrame, ticker: str, mode: str) -> None:
    """Print a compact per-fold table to stdout for operator review."""
    if wf_df.empty:
        print(f"  {ticker} {mode}: no folds — dataset too short for "
              "configured train/test windows.")
        return

    print(f"\n  {ticker} {mode}: {len(wf_df)} folds")
    print("  fold | test period              | trades | WR     | PF    | "
          "Sharpe | Max DD")
    print("  -----|--------------------------|--------|--------|-------|"
          "--------|--------")
    for _, r in wf_df.iterrows():
        wr = r['win_rate'] if pd.notna(r['win_rate']) else float('nan')
        pf = r['profit_factor'] if pd.notna(r['profit_factor']) else float('nan')
        sh = r['sharpe'] if pd.notna(r['sharpe']) else float('nan')
        dd = r['max_dd'] if pd.notna(r['max_dd']) else float('nan')
        trades = (int(r['total_trades']) if pd.notna(r['total_trades'])
                  else 0)
        print(
            f"  {int(r['fold_index']):>4d} | {str(r['test_start'])} → "
            f"{str(r['test_end'])} | {trades:>6d} | "
            f"{wr*100 if not np.isnan(wr) else 0:>5.1f}% | "
            f"{pf:>5.2f} | {sh:>6.2f} | "
            f"{dd*100 if not np.isnan(dd) else 0:>6.2f}%"
        )
    stability = wf_df['stability_score'].iloc[0]
    mean_sharpe = wf_df['sharpe'].mean()
    print(f"  stability_score={stability:.2f}  mean_fold_sharpe="
          f"{mean_sharpe:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Run walk-forward validation on a ticker and persist '
                    'per-fold metrics to backtest_walk_forward_folds')
    parser.add_argument('--ticker', default='IWM',
                        help='Ticker to validate (free-text; any symbol '
                             'with daily history in market_data_daily).')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--use-strat', action='store_true',
                        help='Enable Strat candle classification bonus')
    parser.add_argument('--train-months', type=int, default=None,
                        help='Training window (months, default from config)')
    parser.add_argument('--test-months', type=int, default=None,
                        help='Test window (months, default from config)')
    parser.add_argument('--daily-data', action='store_true',
                        help='Use daily data instead of intraday')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Directory for the per-fold CSV summary '
                             '(default from config)')
    parser.add_argument('--run-id', type=str, default=None,
                        help=('Shared pipeline run UUID. run_pipeline.py '
                              'passes one id to every sub-step so the '
                              'report stage can group all rows from one '
                              'run. If omitted, a fresh uuid4 is generated.'))
    # ---- Strat-config overrides (calibration knobs) ---------------------
    # These let scripts/calibrate_iwm_strat.py (and ad-hoc operators)
    # run WF with non-default StratConfig without editing alert_config.json.
    # Each flag is back-compat: default=None means "leave config as-is."
    parser.add_argument('--no-ftfc-filter', action='store_true',
                        help='Override StratConfig.ftfc_filter_enabled=False')
    parser.add_argument('--no-orb-filter', action='store_true',
                        help='Override StratConfig.orb_filter_enabled=False')
    parser.add_argument('--ftfc-threshold', type=float, default=None,
                        help='Override StratConfig.ftfc_threshold (e.g. 0.8 '
                             'for strong-trend-only)')
    parser.add_argument('--strat-directions', type=str, default=None,
                        help='Comma-separated direction allow-list for the '
                             'Strat overlay (e.g. "CALL" to skip Strat on '
                             'PUTs). Default: both directions.')
    parser.add_argument('--mode-label', type=str, default=None,
                        help='Override the persisted mode label (default '
                             'derived from --use-strat). Used by the '
                             'calibration orchestrator to distinguish '
                             'multi-config runs that share a ticker.')

    args = parser.parse_args()
    run_id = args.run_id or str(uuid.uuid4())

    # Validate CLI inputs EARLY — before the ~10s data load — so the
    # operator sees the error immediately rather than 5-7 min in.
    if args.mode_label is not None and len(args.mode_label) > 8:
        raise ValueError(
            f'--mode-label={args.mode_label!r} exceeds 8 chars '
            '(schema VARCHAR(8))')

    cfg = load_config(ticker=args.ticker)
    # Apply StratConfig overrides BEFORE the validator is constructed —
    # the dataclass is passed by reference and mutated in-place.
    if args.no_ftfc_filter:
        cfg.strat.ftfc_filter_enabled = False
    if args.no_orb_filter:
        cfg.strat.orb_filter_enabled = False
    if args.ftfc_threshold is not None:
        if not (0.0 <= args.ftfc_threshold <= 1.0):
            raise ValueError(
                f'--ftfc-threshold={args.ftfc_threshold}, must be in [0,1]')
        cfg.strat.ftfc_threshold = args.ftfc_threshold
    if args.strat_directions is not None:
        dirs = {d.strip().upper() for d in args.strat_directions.split(',')
                if d.strip()}
        valid = {'CALL', 'PUT'}
        if not dirs or not dirs.issubset(valid):
            raise ValueError(
                f'--strat-directions={args.strat_directions!r} must be a '
                f'comma-separated subset of {sorted(valid)}')
        cfg.strat.allowed_directions = dirs
    train_months = (args.train_months if args.train_months is not None
                    else cfg.walk_forward.default_train_months)
    test_months = (args.test_months if args.test_months is not None
                   else cfg.walk_forward.default_test_months)

    loader = DataLoader()
    print(f"\nLoading data for {args.ticker}...")
    if args.daily_data:
        df = loader.load_daily(args.ticker)
        close_col = 'Close'
    else:
        df = loader.load_best_available(args.ticker, args.start, args.end)
        close_col = 'Close' if 'Close' in df.columns else 'Last'

    if df.empty:
        print(f"No data found for {args.ticker}. Check data/ directory.")
        sys.exit(1)

    print(f"Loaded {len(df):,} bars from {df.index.min()} to {df.index.max()}")

    print("Calculating indicators...")
    df = add_all_indicators(df, close_col=close_col)

    mode = args.mode_label or ('strat' if args.use_strat else 'base')
    print(f"\nRunning walk-forward validation ({train_months}mo train / "
          f"{test_months}mo test, mode={mode})...")
    validator = WalkForwardValidator(
        risk_config=cfg.risk,
        exit_config=cfg.exit,
        signal_config=cfg.signal,
        strat_config=cfg.strat,
        backtest_config=cfg.backtest,
        indicator_config=cfg.indicator,
        walk_forward_config=cfg.walk_forward,
        train_months=train_months,
        test_months=test_months,
    )
    wf_result = validator.run(df, use_strat=args.use_strat, close_col=close_col)

    wf_df = _wf_result_to_dataframe(
        wf_result, run_id=run_id, ticker=args.ticker,
        use_strat=args.use_strat,
        mode_label=args.mode_label,
    )

    _print_fold_summary(wf_df, args.ticker, mode)

    # Optional local CSV — harmless, useful for offline dev where Cloud
    # SQL isn't configured. The table is the canonical hand-off.
    output_dir = Path(args.output_dir or cfg.market.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_path = (output_dir
                / f'walk_forward_folds_{args.ticker}_{mode}_{timestamp}.csv')
    wf_df.to_csv(csv_path, index=False)
    print(f"\nPer-fold metrics CSV: {csv_path}")

    if wf_df.empty:
        print("\nNo folds — nothing to persist to backtest_walk_forward_folds.")
        return

    n = persist_walk_forward(wf_df, run_id, args.ticker, args.use_strat)
    print(f"\nWrote {n} fold row(s) to backtest_walk_forward_folds "
          f"(run_id={run_id}, ticker={args.ticker}, mode={mode})")


if __name__ == '__main__':
    main()
