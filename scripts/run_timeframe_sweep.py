#!/usr/bin/env python3
"""
Multi-timeframe backtest sweep.

Resamples 1-minute data to 5m/15m/30m/1h/4h, runs the backtest engine on
each interval, compares performance, and tests multi-TF combination filters.

Usage:
    python scripts/run_timeframe_sweep.py --ticker IWM
    python scripts/run_timeframe_sweep.py --ticker IWM --use-strat
"""

import argparse
import sys
import os
from pathlib import Path
from datetime import datetime, time as dtime
from copy import deepcopy

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np

from lib.data_loader import DataLoader
from lib.indicators import add_all_indicators
from lib.config import load_config, ExitConfig, SignalConfig
from lib.backtest import BacktestEngine, BacktestResult


# -- Timeframe definitions ----------------------------------------------------
# bar_minutes: minutes per candle  (for scaling time-based params)
TIMEFRAMES = {
    '1m':  {'bar_minutes': 1,   'resample': None},     # base -- no resampling
    '5m':  {'bar_minutes': 5,   'resample': '5min'},
    '15m': {'bar_minutes': 15,  'resample': '15min'},
    '30m': {'bar_minutes': 30,  'resample': '30min'},
    '1h':  {'bar_minutes': 60,  'resample': '1h'},
    '4h':  {'bar_minutes': 240, 'resample': '4h'},
}


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample an OHLCV DataFrame to a higher timeframe."""
    close_col = 'Close' if 'Close' in df.columns else 'Last'
    agg = {
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        close_col: 'last',
        'Volume': 'sum',
    }
    resampled = df.resample(rule).agg(agg).dropna()
    if close_col != 'Close':
        resampled = resampled.rename(columns={close_col: 'Close'})

    # Restore a 'Time' column from the resampled index
    resampled['Time'] = resampled.index
    return resampled


def scale_exit_config(base_exit: ExitConfig, bar_minutes: int) -> ExitConfig:
    """Scale time-based exit params to match the new bar size.

    Percentage targets/stops stay the same (they're price-relative).
    Time stops scale so they represent roughly the same wall-clock duration,
    but clamped to a minimum of 1 bar.
    """
    cfg = deepcopy(base_exit)
    cfg.call_time_stop = max(1, int(base_exit.call_time_stop / bar_minutes))
    cfg.put_time_stop = max(1, int(base_exit.put_time_stop / bar_minutes))
    return cfg


def scale_signal_config(base_signal: SignalConfig, bar_minutes: int) -> SignalConfig:
    """Adjust signal config for the timeframe.

    Consecutive-periods stays at 3 bars (semantically: 3 bars of pressure).
    Entry windows are time-based and don't change.

    For longer bars (>=30 min), we widen the entry window so the engine can
    find enough bars to evaluate.
    """
    cfg = deepcopy(base_signal)

    # For 30m+ bars the call window (9:30-10:00) is only 1 bar wide.
    # Widen it so we get meaningful signal detection.
    if bar_minutes >= 30:
        cfg.call_entry_end = '11:00'
    if bar_minutes >= 60:
        cfg.call_entry_end = '12:00'
        cfg.put_entry_end = '15:30'

    return cfg


def run_single_tf(
    df_tf: pd.DataFrame,
    cfg,
    exit_cfg: ExitConfig,
    signal_cfg: SignalConfig,
    use_strat: bool,
    label: str,
) -> BacktestResult:
    """Run the backtest engine on one timeframe DataFrame."""
    close_col = 'Close' if 'Close' in df_tf.columns else 'Last'

    # Compute indicators fresh on the resampled data
    df_tf = add_all_indicators(df_tf, close_col=close_col)

    engine = BacktestEngine(
        risk_config=cfg.risk,
        exit_config=exit_cfg,
        signal_config=signal_cfg,
        strat_config=cfg.strat,
        backtest_config=cfg.backtest,
        indicator_config=cfg.indicator,
    )
    return engine.run(df_tf, use_strat=use_strat, close_col=close_col)


# -- Combination analysis -----------------------------------------------------
def run_combination(
    df_1m: pd.DataFrame,
    higher_tf_key: str,
    cfg,
    base_exit: ExitConfig,
    base_signal: SignalConfig,
    use_strat: bool,
) -> BacktestResult:
    """Run 1-minute signals filtered by a higher-TF trend direction.

    Logic:
    - Resample 1m -> higher TF, compute EMA20 on higher TF
    - For each 1m bar, look up the *most recent completed* higher-TF bar
    - Only allow CALL signals when higher-TF price > higher-TF EMA20
    - Only allow PUT signals when higher-TF price < higher-TF EMA20
    - If neutral (within 0.05%), allow both directions

    We implement this by adding a 'Higher_TF_Trend' column to the 1m
    DataFrame and patching the evaluate_signal call indirectly through
    indicator manipulation.
    """
    close_col = 'Close' if 'Close' in df_1m.columns else 'Last'
    tf_info = TIMEFRAMES[higher_tf_key]
    rule = tf_info['resample']

    # 1) Build higher-TF data with EMA20
    df_higher = resample_ohlcv(df_1m, rule)
    higher_close = df_higher['Close']
    higher_ema20 = higher_close.ewm(span=20, adjust=False).mean()
    df_higher['htf_trend'] = 0
    df_higher.loc[higher_close > higher_ema20 * 1.0005, 'htf_trend'] = 1
    df_higher.loc[higher_close < higher_ema20 * 0.9995, 'htf_trend'] = -1

    # 2) Forward-fill higher-TF trend into 1m index
    htf_trend = df_higher['htf_trend'].reindex(df_1m.index, method='ffill').fillna(0).astype(int)

    # 3) Compute 1m indicators
    df_work = add_all_indicators(df_1m.copy(), close_col=close_col)

    # 4) Filter: zero-out signal conditions that conflict with higher-TF trend.
    #    Simpler approach: run backtest bar-by-bar manually with filter
    engine = BacktestEngine(
        risk_config=cfg.risk,
        exit_config=base_exit,
        signal_config=base_signal,
        strat_config=cfg.strat,
        backtest_config=cfg.backtest,
        indicator_config=cfg.indicator,
    )

    # Monkey-patch _check_entry to add higher-TF filter
    original_check_entry = engine._check_entry

    def filtered_check_entry(row, bar_time, use_strat_flag, strat_df, ftfc_series, bar_idx, day_df):
        trade = original_check_entry(row, bar_time, use_strat_flag, strat_df, ftfc_series, bar_idx, day_df)
        if trade is None:
            return None

        # Look up the higher-TF trend at this bar's time
        idx = day_df.index[bar_idx]
        trend = htf_trend.get(idx, 0)

        # Filter: CALL only when higher TF bullish or neutral,
        #         PUT only when higher TF bearish or neutral
        if trade.direction == 'CALL' and trend == -1:
            return None
        if trade.direction == 'PUT' and trend == 1:
            return None

        return trade

    engine._check_entry = filtered_check_entry
    result = engine.run(df_work, use_strat=use_strat, close_col=close_col)
    return result


# -- Reporting -----------------------------------------------------------------
def format_metrics_table(rows: list) -> str:
    """Pretty-print a comparison table of backtest metrics."""
    headers = [
        'Timeframe', 'Trades', 'Win Rate', 'Avg Win', 'Avg Loss',
        'P/F', 'Expect/Trade', 'Max DD', 'Sharpe',
    ]
    col_widths = [14, 8, 10, 10, 10, 8, 13, 10, 8]

    # Header
    hdr = ''.join(h.ljust(w) for h, w in zip(headers, col_widths))
    sep = '-' * len(hdr)

    lines = [sep, hdr, sep]
    for r in rows:
        line = (
            f"{r['label']:<14}"
            f"{r['trades']:<8}"
            f"{r['win_rate']:>8.1%}  "
            f"{r['avg_win']:>+8.3%}  "
            f"{r['avg_loss']:>+8.3%}  "
            f"{r['pf']:>6.2f}  "
            f"{r['expectancy']:>+10.3%}   "
            f"{r['max_dd']:>8.2%}  "
            f"{r['sharpe']:>6.2f}"
        )
        lines.append(line)
    lines.append(sep)
    return '\n'.join(lines)


def result_to_row(label: str, result: BacktestResult) -> dict:
    m = result.metrics()
    return {
        'label': label,
        'trades': m['total_trades'],
        'win_rate': m['win_rate'],
        'avg_win': m['avg_win_pct'],
        'avg_loss': m['avg_loss_pct'],
        'pf': m['profit_factor'],
        'expectancy': m['expectancy_pct'],
        'max_dd': m['max_drawdown_pct'],
        'sharpe': m['sharpe_ratio'],
    }


def rank_results(rows: list) -> list:
    """Sort rows by expectancy descending, mark the best."""
    return sorted(rows, key=lambda r: r['expectancy'], reverse=True)


# -- Main ---------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='Multi-timeframe backtest sweep')
    parser.add_argument('--ticker', default='IWM', choices=['IWM', 'SPY', 'QQQ', 'SPX'])
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--use-strat', action='store_true',
                        help='Enable Strat bonus scoring')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Directory to save results (default from config)')
    parser.add_argument('--timeframes', nargs='+',
                        default=['1m', '5m', '15m', '30m', '1h'],
                        help='Timeframes to test (default: 1m 5m 15m 30m 1h)')
    parser.add_argument('--combos', nargs='+',
                        default=['15m', '30m', '1h'],
                        help='Higher-TF filters for combination tests (default: 15m 30m 1h)')
    args = parser.parse_args()

    # Load config (with per-ticker overrides)
    cfg = load_config(ticker=args.ticker)
    print(f"Config: max {cfg.risk.max_daily_trades} trades/day, "
          f"CALL target {cfg.exit.call_target:.2%}, PUT target {cfg.exit.put_target:.2%}")

    # Load 1-minute data (base)
    loader = DataLoader()
    print(f"\nLoading 1-minute data for {args.ticker}...")
    df = loader.load_best_available(args.ticker, args.start, args.end)

    if df.empty:
        print(f"No data found for {args.ticker}.")
        sys.exit(1)

    close_col = 'Close' if 'Close' in df.columns else 'Last'
    print(f"Loaded {len(df):,} bars from {df.index.min()} to {df.index.max()}")

    output_dir = Path(args.output_dir or cfg.market.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # -- Phase 1: Individual timeframe sweep -----------------------------------
    print("\n" + "=" * 70)
    print("  PHASE 1: Individual Timeframe Sweep")
    print("=" * 70)

    single_rows = []
    tf_results = {}

    for tf_key in args.timeframes:
        tf_info = TIMEFRAMES[tf_key]
        bar_min = tf_info['bar_minutes']
        rule = tf_info['resample']

        print(f"\n  [{tf_key}] Resampling & running backtest (bar={bar_min}min)...")

        # Resample (or use raw for 1m)
        if rule is None:
            df_tf = df.copy()
        else:
            df_tf = resample_ohlcv(df, rule)

        # Scale configs
        exit_cfg = scale_exit_config(cfg.exit, bar_min)
        sig_cfg = scale_signal_config(cfg.signal, bar_min)

        print(f"         time_stop: CALL={exit_cfg.call_time_stop} bars "
              f"({exit_cfg.call_time_stop * bar_min}min), "
              f"PUT={exit_cfg.put_time_stop} bars "
              f"({exit_cfg.put_time_stop * bar_min}min)")
        print(f"         entry window: CALL {sig_cfg.call_entry_start}-{sig_cfg.call_entry_end}, "
              f"PUT {sig_cfg.put_entry_start}-{sig_cfg.put_entry_end}")
        print(f"         bars: {len(df_tf):,}")

        result = run_single_tf(df_tf, cfg, exit_cfg, sig_cfg, args.use_strat, tf_key)
        tf_results[tf_key] = result

        row = result_to_row(tf_key, result)
        single_rows.append(row)

        print(f"         -> {row['trades']} trades, "
              f"WR={row['win_rate']:.1%}, "
              f"E={row['expectancy']:+.3%}/trade, "
              f"Sharpe={row['sharpe']:.2f}")

    # Print ranked comparison
    print("\n\n" + "=" * 70)
    print("  INDIVIDUAL TIMEFRAME RESULTS (ranked by expectancy)")
    print("=" * 70)
    ranked = rank_results(single_rows)
    print(format_metrics_table(ranked))

    if ranked and ranked[0]['trades'] > 0:
        best = ranked[0]
        print(f"\n  >>> Best single TF: {best['label']} "
              f"(E={best['expectancy']:+.3%}, Sharpe={best['sharpe']:.2f})")

    # -- Phase 2: Combination analysis (1m signals + higher-TF filter) ---------
    print("\n\n" + "=" * 70)
    print("  PHASE 2: Combination Analysis (1m signals + higher-TF trend filter)")
    print("=" * 70)
    print("  Logic: only take CALL when higher-TF price > EMA20,")
    print("         only take PUT  when higher-TF price < EMA20\n")

    combo_rows = []

    # Baseline: 1m with no filter
    if '1m' in tf_results:
        combo_rows.append(result_to_row('1m (baseline)', tf_results['1m']))

    for htf in args.combos:
        if htf not in TIMEFRAMES or TIMEFRAMES[htf]['resample'] is None:
            continue

        print(f"  [1m + {htf} filter] Running combination backtest...")

        try:
            combo_result = run_combination(
                df, htf, cfg, cfg.exit, cfg.signal, args.use_strat,
            )
            row = result_to_row(f'1m+{htf}', combo_result)
            combo_rows.append(row)
            print(f"         -> {row['trades']} trades, "
                  f"WR={row['win_rate']:.1%}, "
                  f"E={row['expectancy']:+.3%}/trade, "
                  f"Sharpe={row['sharpe']:.2f}")
        except Exception as e:
            print(f"         -> Error: {e}")

    if combo_rows:
        print("\n\n" + "=" * 70)
        print("  COMBINATION RESULTS (ranked by expectancy)")
        print("=" * 70)
        ranked_combos = rank_results(combo_rows)
        print(format_metrics_table(ranked_combos))

        if ranked_combos and ranked_combos[0]['trades'] > 0:
            best_c = ranked_combos[0]
            print(f"\n  >>> Best combo: {best_c['label']} "
                  f"(E={best_c['expectancy']:+.3%}, Sharpe={best_c['sharpe']:.2f})")

    # -- Phase 3: Save all results to CSV --------------------------------------
    all_rows = []
    for r in single_rows:
        r['type'] = 'single'
        all_rows.append(r)
    for r in combo_rows:
        r['type'] = 'combo'
        all_rows.append(r)

    results_df = pd.DataFrame(all_rows)
    output_file = output_dir / f'timeframe_sweep_{args.ticker}_{timestamp}.csv'
    results_df.to_csv(output_file, index=False)
    print(f"\n\nResults saved to {output_file}")

    # -- Summary ---------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)

    all_ranked = rank_results(all_rows)
    if all_ranked and all_ranked[0]['trades'] > 0:
        overall_best = all_ranked[0]
        print(f"\n  Overall best: {overall_best['label']}")
        print(f"    Trades:      {overall_best['trades']}")
        print(f"    Win Rate:    {overall_best['win_rate']:.1%}")
        print(f"    Expectancy:  {overall_best['expectancy']:+.3%}/trade")
        print(f"    Profit Factor: {overall_best['pf']:.2f}")
        print(f"    Max Drawdown:  {overall_best['max_dd']:.2%}")
        print(f"    Sharpe Ratio:  {overall_best['sharpe']:.2f}")

    # Print all ranked
    print(f"\n  Full ranking:")
    for i, r in enumerate(all_ranked, 1):
        flag = ' <<<' if i == 1 else ''
        print(f"    {i}. {r['label']:<14} E={r['expectancy']:+.3%}  "
              f"Sharpe={r['sharpe']:.2f}  "
              f"WR={r['win_rate']:.1%}  "
              f"({r['trades']} trades){flag}")


if __name__ == '__main__':
    main()
