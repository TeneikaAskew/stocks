#!/usr/bin/env python3
"""
CLI runner for the backtesting engine.

Usage:
    python scripts/run_backtest.py --ticker IWM --start 2020-01-01 --end 2025-11-01
    python scripts/run_backtest.py --ticker IWM --use-strat
    python scripts/run_backtest.py --ticker IWM --walk-forward
    python scripts/run_backtest.py --ticker IWM --param-sweep
"""

import argparse
import sys
import os
import uuid
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from lib.data_loader import DataLoader
from lib.indicators import add_all_indicators
from lib.config import load_config
from lib.backtest import BacktestEngine
from lib.walk_forward import WalkForwardValidator


def persist_trades(
    trades_df: pd.DataFrame,
    run_id: str,
    ticker: str,
    use_strat: bool,
) -> int:
    """Write simulated trade rows to the backtest_trades Cloud SQL table.

    This is the canonical hand-off seam between the "simulate" stage
    (this script) and the "report" stage (generate_backtest_report.py),
    replacing the old CSV plumbing. Each trade is tagged with the shared
    pipeline ``run_id`` plus ``ticker`` / ``use_strat`` / ``mode`` so the
    report stage can slice by run.

    Returns the number of rows written. Raises on Cloud SQL failure —
    the table is the canonical path, so a write failure must surface
    (per CLAUDE.md §3.7: no silent fallbacks in data-access code).
    """
    from gcp.database import upsert_dataframe

    df = trades_df.copy()
    df.insert(0, 'run_id', run_id)
    df.insert(1, 'ticker', ticker)
    df.insert(2, 'use_strat', bool(use_strat))
    df.insert(3, 'mode', 'strat' if use_strat else 'base')
    # 0-based trade index within (run_id, ticker, mode) — completes the
    # natural key so a re-run with the same run_id converges via
    # ON CONFLICT DO UPDATE rather than appending duplicate rows.
    df.insert(4, 'trade_seq', range(len(df)))

    return upsert_dataframe(
        df,
        table='backtest_trades',
        conflict_cols=['run_id', 'ticker', 'mode', 'trade_seq'],
    )


def main():
    parser = argparse.ArgumentParser(description='Run backtests on trading signals')
    parser.add_argument('--ticker', default='IWM',
                        help=('Ticker to backtest. Free-text — accepts any '
                              'symbol with daily history in market_data_daily. '
                              'Originally hardcoded to IWM/SPY/QQQ/SPX; relaxed '
                              'so the Discord /backtest command can target '
                              'newly-added watchlist tickers (NVDA, AMD, etc).'))
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--use-strat', action='store_true',
                        help='Enable Strat candle classification bonus')
    parser.add_argument('--walk-forward', action='store_true',
                        help='Run walk-forward validation instead of single backtest')
    parser.add_argument('--train-months', type=int, default=None,
                        help='Training window for walk-forward (months, default from config)')
    parser.add_argument('--test-months', type=int, default=None,
                        help='Test window for walk-forward (months, default from config)')
    parser.add_argument('--param-sweep', action='store_true',
                        help='Run parameter sensitivity analysis')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Directory to save results (default from config)')
    parser.add_argument('--daily-data', action='store_true',
                        help='Use daily data instead of intraday')
    parser.add_argument('--run-id', type=str, default=None,
                        help=('Shared pipeline run UUID. run_pipeline.py '
                              'passes one id to every sub-step so the report '
                              'stage can group all rows from one run. If '
                              'omitted, a fresh uuid4 is generated.'))

    args = parser.parse_args()
    run_id = args.run_id or str(uuid.uuid4())

    # Load config (with per-ticker overrides)
    cfg = load_config(ticker=args.ticker)
    print(f"Configuration loaded: max {cfg.risk.max_daily_trades} trades/day, "
          f"CALL target {cfg.exit.call_target:.2%}, PUT target {cfg.exit.put_target:.2%}")

    # Load data
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

    # Add indicators
    print("Calculating indicators...")
    df = add_all_indicators(df, close_col=close_col)
    print(f"Added indicators -- {len(df.columns)} total columns")

    # Create output directory (CLI arg overrides config)
    output_dir = Path(args.output_dir or cfg.market.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Resolve train/test months (CLI arg overrides config defaults)
    train_months = args.train_months if args.train_months is not None else cfg.walk_forward.default_train_months
    test_months = args.test_months if args.test_months is not None else cfg.walk_forward.default_test_months

    if args.walk_forward:
        # Walk-forward validation
        print(f"\nRunning walk-forward validation ({train_months}mo train / {test_months}mo test)...")
        validator = WalkForwardValidator(
            risk_config=cfg.risk,
            exit_config=cfg.exit,
            signal_config=cfg.signal,
            strat_config=cfg.strat,
            backtest_config=cfg.backtest,
            indicator_config=cfg.indicator,
            walk_forward_config=cfg.walk_forward,
            train_months=args.train_months,
            test_months=args.test_months,
        )
        wf_result = validator.run(df, use_strat=args.use_strat, close_col=close_col)
        print(f"\n{wf_result.summary()}")

        # Save results
        output_file = output_dir / f'walk_forward_{args.ticker}_{timestamp}.csv'
        all_trades = []
        for fold_result in wf_result.fold_results:
            all_trades.append(fold_result.to_dataframe())
        if all_trades:
            pd.concat(all_trades).to_csv(output_file, index=False)
            print(f"\nTrades saved to {output_file}")

    elif args.param_sweep:
        # Parameter sensitivity
        print("\nRunning parameter sensitivity analysis...")
        validator = WalkForwardValidator(
            risk_config=cfg.risk,
            exit_config=cfg.exit,
            signal_config=cfg.signal,
            strat_config=cfg.strat,
            backtest_config=cfg.backtest,
            indicator_config=cfg.indicator,
            walk_forward_config=cfg.walk_forward,
        )
        param_grid = {
            'consecutive_periods': [2, 3, 4],
            'call_target': [0.0020, 0.0025, 0.0030, 0.0035, 0.0040],
            'call_time_stop': [20, 25, 30, 35, 40],
        }
        results_df = validator.parameter_sensitivity(
            df, param_grid, use_strat=args.use_strat, close_col=close_col,
        )
        print(f"\nParameter Sensitivity Results:")
        print(results_df.sort_values('expectancy_pct', ascending=False).head(20).to_string())

        output_file = output_dir / f'param_sweep_{args.ticker}_{timestamp}.csv'
        results_df.to_csv(output_file, index=False)
        print(f"\nResults saved to {output_file}")

    else:
        # Single backtest
        strat_label = " + Strat" if args.use_strat else ""
        print(f"\nRunning backtest{strat_label}...")
        engine = BacktestEngine(
            risk_config=cfg.risk,
            exit_config=cfg.exit,
            signal_config=cfg.signal,
            strat_config=cfg.strat,
            backtest_config=cfg.backtest,
            indicator_config=cfg.indicator,
        )
        result = engine.run(df, use_strat=args.use_strat, close_col=close_col)
        print(f"\n{result.summary()}")

        # Save trades — the backtest_trades Cloud SQL table is the
        # canonical hand-off to the report stage. The local CSV is
        # kept too: it's harmless and useful for offline/local dev
        # where Cloud SQL isn't configured.
        trades_df = result.to_dataframe()
        if not trades_df.empty:
            output_file = output_dir / f'backtest_{args.ticker}_{timestamp}.csv'
            trades_df.to_csv(output_file, index=False)
            print(f"\nTrades saved to {output_file}")

            n_written = persist_trades(
                trades_df, run_id, args.ticker, args.use_strat,
            )
            print(f"Wrote {n_written} trade row(s) to backtest_trades "
                  f"(run_id={run_id}, mode={'strat' if args.use_strat else 'base'})")
        else:
            print("\nNo trades simulated — nothing written to backtest_trades.")

        # Save equity curve (local CSV only — equity curves aren't
        # part of the report stage's table-based contract).
        if not result.equity_curve.empty:
            eq_file = output_dir / f'equity_{args.ticker}_{timestamp}.csv'
            result.equity_curve.to_csv(eq_file)
            print(f"Equity curve saved to {eq_file}")


if __name__ == '__main__':
    main()
