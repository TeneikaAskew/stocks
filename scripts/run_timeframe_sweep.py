#!/usr/bin/env python3
"""
Multi-timeframe backtest sweep.

Resamples 1-minute data to 5m/15m/30m/1h/4h, runs the backtest engine on
each interval, compares performance, and tests multi-TF combination filters.

Phase 1: Individual timeframe sweep (1m, 5m, 15m, 30m, 1h)
Phase 2: 1m signals + higher-TF trend filter (original)
Phase 3: All entry+filter combos (5m+15m, 5m+30m, 15m+30m, etc.)

Usage:
    python scripts/run_timeframe_sweep.py --ticker IWM
    python scripts/run_timeframe_sweep.py --ticker IWM --use-strat
    python scripts/run_timeframe_sweep.py --ticker IWM --all-combos
"""

import argparse
import sys
import os
import uuid
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


def persist_sweeps(
    sweep_rows: list,
    run_id: str,
    ticker: str,
) -> int:
    """Write timeframe-sweep rows to the backtest_sweeps Cloud SQL table.

    Replaces the CSV hand-off to generate_backtest_report.py. Each row
    is one (timeframe / combo) tested, tagged with the shared pipeline
    ``run_id``. Raises on Cloud SQL failure — the table is the canonical
    path (per CLAUDE.md §3.7: no silent fallbacks in data-access code).

    Returns the number of rows written.
    """
    from gcp.database import upsert_dataframe

    df = pd.DataFrame(sweep_rows)
    if df.empty:
        return 0

    # Map the in-memory result_to_row() dict keys → table columns.
    # 'label' and 'type' already match; the rest are 1:1.
    df = df.rename(columns={'type': 'sweep_type'})
    df.insert(0, 'run_id', run_id)
    df.insert(1, 'ticker', ticker)

    return upsert_dataframe(
        df,
        table='backtest_sweeps',
        conflict_cols=['run_id', 'ticker', 'label'],
    )


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
    filter_ema_period: int = 20,
) -> BacktestResult:
    """Run 1-minute signals filtered by a higher-TF trend direction.

    Logic:
    - Resample 1m -> higher TF, compute EMA(``filter_ema_period``) on higher TF
    - For each 1m bar, look up the *most recent completed* higher-TF bar
    - Only allow CALL signals when higher-TF price > higher-TF EMA
    - Only allow PUT signals when higher-TF price < higher-TF EMA
    - If neutral (within 0.05%), allow both directions

    We implement this by adding a 'Higher_TF_Trend' column to the 1m
    DataFrame and patching the evaluate_signal call indirectly through
    indicator manipulation.

    ``filter_ema_period`` (default 20) parameterises the trend-filter
    EMA — previously hardcoded to 20. Different periods materially
    change which 1m bars are gated: a faster EMA (e.g. 10) flips trend
    more often and lets through more counter-trend signals; a slower
    EMA (e.g. 50) is more committal but misses regime shifts. Which
    period performs best is an empirical question worth a separate
    sweep; the parameterisation contract is covered by
    ``tests/test_filter_ema_period.py``.
    """
    if filter_ema_period <= 0:
        raise ValueError(
            f"filter_ema_period must be a positive integer "
            f"(got {filter_ema_period!r})"
        )
    close_col = 'Close' if 'Close' in df_1m.columns else 'Last'
    tf_info = TIMEFRAMES[higher_tf_key]
    rule = tf_info['resample']

    # 1) Build higher-TF data with the configured EMA period
    df_higher = resample_ohlcv(df_1m, rule)
    higher_close = df_higher['Close']
    higher_ema = higher_close.ewm(span=filter_ema_period, adjust=False).mean()
    df_higher['htf_trend'] = 0
    df_higher.loc[higher_close > higher_ema * 1.0005, 'htf_trend'] = 1
    df_higher.loc[higher_close < higher_ema * 0.9995, 'htf_trend'] = -1

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


def run_combination_general(
    df_1m: pd.DataFrame,
    entry_tf_key: str,
    filter_tf_key: str,
    cfg,
    base_exit: ExitConfig,
    base_signal: SignalConfig,
    use_strat: bool,
    filter_ema_period: int = 20,
) -> BacktestResult:
    """Run entry signals on any timeframe, filtered by a higher-TF trend.

    Generalises run_combination() so the entry timeframe is not restricted
    to 1m.  The filter timeframe must be coarser than the entry timeframe.

    Logic is the same as run_combination:
    - Resample 1m data to *both* timeframes
    - Compute EMA(``filter_ema_period``) on the filter TF to determine trend
    - Forward-fill trend into the entry-TF index
    - Only allow CALL when higher-TF price > EMA, PUT when < EMA

    ``filter_ema_period`` mirrors the run_combination() parameter — same
    rationale, default 20. Tests pin the parameterisation contract.
    """
    if filter_ema_period <= 0:
        raise ValueError(
            f"filter_ema_period must be a positive integer "
            f"(got {filter_ema_period!r})"
        )
    close_col = 'Close' if 'Close' in df_1m.columns else 'Last'
    entry_info = TIMEFRAMES[entry_tf_key]
    filter_info = TIMEFRAMES[filter_tf_key]

    # Resample to entry TF (or use raw 1m)
    if entry_info['resample'] is None:
        df_entry = df_1m.copy()
    else:
        df_entry = resample_ohlcv(df_1m, entry_info['resample'])

    # Resample to filter TF
    df_filter = resample_ohlcv(df_1m, filter_info['resample'])

    # Build higher-TF trend from filter TF (parameterised EMA period)
    filter_close = df_filter['Close']
    filter_ema = filter_close.ewm(span=filter_ema_period, adjust=False).mean()
    df_filter['htf_trend'] = 0
    df_filter.loc[filter_close > filter_ema * 1.0005, 'htf_trend'] = 1
    df_filter.loc[filter_close < filter_ema * 0.9995, 'htf_trend'] = -1

    # Forward-fill trend into entry-TF index
    htf_trend = df_filter['htf_trend'].reindex(df_entry.index, method='ffill').fillna(0).astype(int)

    # Scale configs for entry TF
    bar_min = entry_info['bar_minutes']
    exit_cfg = scale_exit_config(base_exit, bar_min)
    sig_cfg = scale_signal_config(base_signal, bar_min)

    # Compute indicators on entry-TF data
    df_work = add_all_indicators(df_entry.copy(), close_col=close_col)

    engine = BacktestEngine(
        risk_config=cfg.risk,
        exit_config=exit_cfg,
        signal_config=sig_cfg,
        strat_config=cfg.strat,
        backtest_config=cfg.backtest,
        indicator_config=cfg.indicator,
    )

    # Monkey-patch to add higher-TF filter
    original_check_entry = engine._check_entry

    def filtered_check_entry(row, bar_time, use_strat_flag, strat_df, ftfc_series, bar_idx, day_df):
        trade = original_check_entry(row, bar_time, use_strat_flag, strat_df, ftfc_series, bar_idx, day_df)
        if trade is None:
            return None

        idx = day_df.index[bar_idx]
        trend = htf_trend.get(idx, 0)

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
    parser.add_argument('--all-combos', action='store_true',
                        help='Test ALL entry+filter combinations (5m+15m, 5m+30m, 15m+30m, etc.)')
    parser.add_argument(
        '--filter-ema-period', type=int, default=20,
        help=('EMA period for the higher-TF trend filter (default 20). Was '
              'previously hardcoded. Used as the SINGLE period when '
              '--filter-ema-periods is not given; ignored otherwise.'),
    )
    parser.add_argument(
        '--filter-ema-periods', nargs='+', type=int, default=None,
        help=('Sweep over multiple trend-filter EMA periods (e.g. '
              '"--filter-ema-periods 10 20 50"). When set, every Phase-2 '
              'and Phase-3 combo is re-run for EACH period; the combo '
              'label becomes "<entry>+<filter>@ema<N>" so all variants '
              'are independently rankable in backtest_sweeps. When '
              'omitted, --filter-ema-period (singular) is used.'),
    )
    parser.add_argument('--run-id', type=str, default=None,
                        help=('Shared pipeline run UUID. run_pipeline.py '
                              'passes one id to every sub-step so the report '
                              'stage can group all rows from one run. If '
                              'omitted, a fresh uuid4 is generated.'))
    args = parser.parse_args()
    run_id = args.run_id or str(uuid.uuid4())

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

    # Resolve the EMA period(s) to test. Single value → preserve the
    # legacy label '1m+15m' (backward compatible). A multi-value sweep
    # → label becomes '1m+15m@ema10' so each variant is its own
    # backtest_sweeps row (UNIQUE keyed on run_id+ticker+label).
    ema_periods = (
        args.filter_ema_periods
        if args.filter_ema_periods
        else [args.filter_ema_period]
    )
    sweep_emas = len(ema_periods) > 1

    for htf in args.combos:
        if htf not in TIMEFRAMES or TIMEFRAMES[htf]['resample'] is None:
            continue

        for ema_period in ema_periods:
            suffix = f"@ema{ema_period}" if sweep_emas else ""
            label = f"1m+{htf}{suffix}"
            print(f"  [{label} filter] Running combination backtest...")

            try:
                combo_result = run_combination(
                    df, htf, cfg, cfg.exit, cfg.signal, args.use_strat,
                    filter_ema_period=ema_period,
                )
                row = result_to_row(label, combo_result)
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

    # -- Phase 3: All entry+filter combinations ----------------------------------
    general_combo_rows = []

    if args.all_combos:
        # Build all valid (entry, filter) pairs where filter is coarser than entry
        tf_order = ['1m', '5m', '15m', '30m', '1h']
        available = [tf for tf in tf_order if tf in args.timeframes]

        pairs = []
        for i, entry_tf in enumerate(available):
            for filter_tf in available[i + 1:]:
                # Skip 1m entry combos -- already covered in Phase 2
                if entry_tf == '1m':
                    continue
                pairs.append((entry_tf, filter_tf))

        if pairs:
            print("\n\n" + "=" * 70)
            print("  PHASE 3: All Entry + Filter Combinations")
            print("=" * 70)
            print("  Testing coarser entry TFs with higher-TF trend filters\n")

            for entry_tf, filter_tf in pairs:
                for ema_period in ema_periods:
                    suffix = f"@ema{ema_period}" if sweep_emas else ""
                    label = f'{entry_tf}+{filter_tf}{suffix}'
                    print(f"  [{label}] Running {entry_tf} entries filtered by {filter_tf} trend...")

                    try:
                        combo_result = run_combination_general(
                            df, entry_tf, filter_tf, cfg,
                            cfg.exit, cfg.signal, args.use_strat,
                            filter_ema_period=ema_period,
                        )
                        row = result_to_row(label, combo_result)
                        general_combo_rows.append(row)
                        print(f"         -> {row['trades']} trades, "
                              f"WR={row['win_rate']:.1%}, "
                              f"E={row['expectancy']:+.3%}/trade, "
                              f"Sharpe={row['sharpe']:.2f}")
                    except Exception as e:
                        print(f"         -> Error: {e}")

            if general_combo_rows:
                print("\n\n" + "=" * 70)
                print("  ALL ENTRY+FILTER COMBINATION RESULTS (ranked by expectancy)")
                print("=" * 70)
                ranked_general = rank_results(general_combo_rows)
                print(format_metrics_table(ranked_general))

                if ranked_general and ranked_general[0]['trades'] > 0:
                    best_g = ranked_general[0]
                    print(f"\n  >>> Best general combo: {best_g['label']} "
                          f"(E={best_g['expectancy']:+.3%}, Sharpe={best_g['sharpe']:.2f})")

    # -- Save all results to CSV -----------------------------------------------
    all_rows = []
    for r in single_rows:
        r['type'] = 'single'
        all_rows.append(r)
    for r in combo_rows:
        r['type'] = 'combo'
        all_rows.append(r)
    for r in general_combo_rows:
        r['type'] = 'general_combo'
        all_rows.append(r)

    results_df = pd.DataFrame(all_rows)
    output_file = output_dir / f'timeframe_sweep_{args.ticker}_{timestamp}.csv'
    results_df.to_csv(output_file, index=False)
    print(f"\n\nResults saved to {output_file}")

    # The backtest_sweeps Cloud SQL table is the canonical hand-off to
    # the report stage; the local CSV above is kept for offline dev.
    n_written = persist_sweeps(all_rows, run_id, args.ticker)
    print(f"Wrote {n_written} sweep row(s) to backtest_sweeps (run_id={run_id})")

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
