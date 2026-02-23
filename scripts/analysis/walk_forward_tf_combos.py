#!/usr/bin/env python3
"""
Walk-Forward Validation of Timeframe Combo Strategies.

Tests whether key timeframe combo findings from timeframe_combo_analysis.md
hold consistently across time using rolling windows, and whether the edge
is regime-dependent (high-VIX vs low-VIX periods).

For non-parametric strategies (no parameters learned on training data),
walk-forward measures regime stability: does the edge hold in each 6-month
period independently?

Tested combos:
  1m+30m   (primary: Sharpe 11.05 IS — expected winner)
  1m+15m   (secondary: Sharpe 10.34 IS)
  5m+15m   (high-WR: 62.6% IS — fewer but higher-conviction entries)
  5m+30m   (mid-tier: Sharpe 7.29 IS)
  15m+30m  (highest WR: 62.9% IS)

Method:
  - Run each combo once on the full dataset to capture all individual trades
  - Slice trades into non-overlapping N-month windows
  - Per window: compute win rate, expectancy, Sharpe, profit factor
  - Aggregate: mean, std dev, stability score (% windows profitable)
  - Break down by volatility regime (Low/Normal/High)

Verdict thresholds:
  STRONG     — ≥90% windows profitable, avg WR ≥ 55%
  VALIDATED  — ≥80% windows profitable, avg WR ≥ 52%
  MARGINAL   — ≥70% windows profitable, avg WR ≥ 50%
  WEAK       — avg WR ≥ 50% but inconsistent
  REGIME-DEP — avg WR < 50%

Usage:
    python scripts/analysis/walk_forward_tf_combos.py
    python scripts/analysis/walk_forward_tf_combos.py --tickers IWM
    python scripts/analysis/walk_forward_tf_combos.py --window-months 3
"""

import sys
import argparse
import warnings
from copy import deepcopy
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

warnings.filterwarnings('ignore', category=FutureWarning)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.analysis.shared_utils import (
    TICKERS, REPORTS_DIR,
    load_ticker_1m, resample_to_timeframe,
    md_header, md_table, fmt_pct, fmt_bps, fmt_num, save_report,
    timestamp_str, progress,
)
from lib.config import load_config
from lib.indicators import add_all_indicators
from lib.backtest import BacktestEngine


# ---------------------------------------------------------------------------
# Combo definitions — (entry_tf, filter_tf, label, IS description)
# ---------------------------------------------------------------------------
COMBOS = [
    ('1m',  '30m', '1m+30m',  'Sharpe 11.05 IS — primary candidate'),
    ('1m',  '15m', '1m+15m',  'Sharpe 10.34 IS — close second'),
    ('5m',  '15m', '5m+15m',  'WR 62.6% IS — fewer, higher-conviction entries'),
    ('5m',  '30m', '5m+30m',  'Sharpe 7.29 IS'),
    ('15m', '30m', '15m+30m', 'WR 62.9% IS — highest win rate'),
]

BAR_MINUTES = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60}


# ---------------------------------------------------------------------------
# Backtest runner — returns per-trade DataFrame
# ---------------------------------------------------------------------------

def run_combo_full(df_1m: pd.DataFrame, entry_tf: str, filter_tf: str, cfg) -> pd.DataFrame:
    """Run entry_tf+filter_tf combo on the full dataset; return per-trade DataFrame.

    Uses the same EMA-20-on-filter-TF logic as run_timeframe_sweep.py.
    """
    close_col = 'Close' if 'Close' in df_1m.columns else 'Last'
    bar_min = BAR_MINUTES[entry_tf]

    # Scale time-based exit params for the entry timeframe
    exit_cfg = deepcopy(cfg.exit)
    exit_cfg.call_time_stop = max(1, int(cfg.exit.call_time_stop / bar_min))
    exit_cfg.put_time_stop  = max(1, int(cfg.exit.put_time_stop  / bar_min))

    sig_cfg = deepcopy(cfg.signal)
    if bar_min >= 30:
        sig_cfg.call_entry_end = '11:00'
    if bar_min >= 60:
        sig_cfg.call_entry_end = '12:00'
        sig_cfg.put_entry_end  = '15:30'

    # Resample entry TF
    df_entry = df_1m.copy() if entry_tf == '1m' else resample_to_timeframe(df_1m, entry_tf)
    if 'Time' not in df_entry.columns:
        df_entry['Time'] = df_entry.index

    # Build filter-TF trend (EMA-20)
    df_filter   = resample_to_timeframe(df_1m, filter_tf)
    f_close     = df_filter['Close']
    f_ema20     = f_close.ewm(span=20, adjust=False).mean()
    htf_trend   = pd.Series(0, index=df_filter.index)
    htf_trend[f_close > f_ema20 * 1.0005] =  1
    htf_trend[f_close < f_ema20 * 0.9995] = -1
    htf_trend = htf_trend.reindex(df_entry.index, method='ffill').fillna(0).astype(int)

    df_work = add_all_indicators(df_entry.copy(), close_col=close_col)

    engine = BacktestEngine(
        risk_config=cfg.risk,
        exit_config=exit_cfg,
        signal_config=sig_cfg,
        strat_config=cfg.strat,
        backtest_config=cfg.backtest,
        indicator_config=cfg.indicator,
    )

    orig = engine._check_entry

    def filtered_check_entry(row, bar_time, use_strat_flag, strat_df, ftfc_series, bar_idx, day_df):
        trade = orig(row, bar_time, use_strat_flag, strat_df, ftfc_series, bar_idx, day_df)
        if trade is None:
            return None
        trend = htf_trend.get(day_df.index[bar_idx], 0)
        if trade.direction == 'CALL' and trend == -1:
            return None
        if trade.direction == 'PUT'  and trend ==  1:
            return None
        return trade

    engine._check_entry = filtered_check_entry
    result = engine.run(df_work, use_strat=False, close_col=close_col)

    if not result.trades:
        return pd.DataFrame(columns=['entry_time', 'exit_time', 'direction', 'return_pct'])

    rows = [
        {
            'entry_time': t.entry_time,
            'exit_time':  t.exit_time,
            'direction':  t.direction,
            'return_pct': t.return_pct,
        }
        for t in result.trades if t.return_pct is not None
    ]
    trades = pd.DataFrame(rows)
    trades['entry_time'] = pd.to_datetime(trades['entry_time'])
    trades['exit_time']  = pd.to_datetime(trades['exit_time'])
    return trades


# ---------------------------------------------------------------------------
# Window generation & metrics
# ---------------------------------------------------------------------------

def build_windows(start: pd.Timestamp, end: pd.Timestamp, window_months: int):
    windows = []
    cur = start
    while cur < end:
        nxt = cur + pd.DateOffset(months=window_months)
        windows.append((cur, min(nxt, end)))
        cur = nxt
    return windows


def window_metrics(trades: pd.DataFrame, ws: pd.Timestamp, we: pd.Timestamp):
    mask = (trades['entry_time'] >= ws) & (trades['entry_time'] < we)
    sub  = trades[mask]
    n    = len(sub)
    if n < 5:
        return None

    rets = sub['return_pct'].values
    wr   = (rets > 0).mean()
    exp  = rets.mean()

    g_wins   = rets[rets > 0].sum() if (rets > 0).any() else 0.0
    g_losses = abs(rets[rets < 0].sum()) if (rets < 0).any() else 0.0
    pf = g_wins / g_losses if g_losses > 0 else (999.0 if g_wins > 0 else 0.0)

    daily = sub.groupby(sub['entry_time'].dt.date)['return_pct'].sum()
    sharpe = (daily.mean() / daily.std() * np.sqrt(252)
              if len(daily) > 5 and daily.std() > 0 else 0.0)

    return {
        'window_start':  ws,
        'window_end':    we,
        'trades':        n,
        'win_rate':      wr,
        'expectancy':    exp,
        'profit_factor': pf,
        'sharpe':        sharpe,
        'profitable':    exp > 0,
        'low_sample':    n < 100,
    }


# ---------------------------------------------------------------------------
# Volatility regime
# ---------------------------------------------------------------------------

def vol_regime(df_1m: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """Classify each 1m bar into Low/Normal/High vol regime."""
    close = df_1m['Close'] if 'Close' in df_1m.columns else df_1m['Last']
    rv = close.pct_change().rolling(lookback).std() * np.sqrt(252 * 390)
    p25 = rv.expanding(min_periods=200).quantile(0.25)
    p75 = rv.expanding(min_periods=200).quantile(0.75)
    regime = pd.Series('Normal', index=df_1m.index)
    regime[rv < p25] = 'Low'
    regime[rv > p75] = 'High'
    return regime


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def _verdict(pct_prof: float, avg_wr: float, low_sample_majority: bool = False) -> str:
    if pct_prof >= 90 and avg_wr >= 0.55:
        label = 'STRONG'
    elif pct_prof >= 80 and avg_wr >= 0.52:
        label = 'VALIDATED'
    elif pct_prof >= 70 and avg_wr >= 0.50:
        label = 'MARGINAL'
    elif avg_wr >= 0.50:
        label = 'WEAK'
    else:
        label = 'REGIME-DEPENDENT'

    if low_sample_majority:
        if label == 'STRONG':
            label = 'VALIDATED (low sample)'
        elif label == 'VALIDATED':
            label = 'MARGINAL (low sample)'

    messages = {
        'STRONG':                    '✅ STRONG — Consistent edge across regimes. Trade-ready.',
        'VALIDATED':                 '✅ VALIDATED — Edge holds across most windows.',
        'VALIDATED (low sample)':    '✅ VALIDATED (low sample) — Edge holds but <100 trades/window; treat as indicative.',
        'MARGINAL':                  '⚠️ MARGINAL — Profitable most windows; add filters before live trading.',
        'MARGINAL (low sample)':     '⚠️ MARGINAL (low sample) — Profitable but thin windows; validate on more data.',
        'WEAK':                      '⚠️ WEAK — Barely positive. High regime sensitivity.',
        'REGIME-DEPENDENT':          '❌ REGIME-DEPENDENT — Edge not consistent. Not tradeable as-is.',
    }
    return messages[label]


def section_combo(label: str, desc: str, window_results: list) -> str:
    valid = [r for r in window_results if r is not None]
    if not valid:
        return f'\n### {label}\nNo valid windows.\n\n'

    wrs       = [r['win_rate']      for r in valid]
    exps      = [r['expectancy']    for r in valid]
    sharpes   = [r['sharpe']        for r in valid]
    pfs       = [r['profit_factor'] for r in valid]
    total_tr  = sum(r['trades']     for r in valid)

    avg_wr    = np.mean(wrs)
    std_wr    = np.std(wrs)
    avg_exp   = np.mean(exps)
    avg_sh    = np.mean(sharpes)
    pct_prof  = sum(1 for r in valid if r['profitable']) / len(valid) * 100
    pct_low   = sum(1 for r in valid if r.get('low_sample', False)) / len(valid) * 100
    cv        = std_wr / avg_wr if avg_wr > 0 else float('inf')

    out = f'\n### {label} — {desc}\n\n'
    out += md_table(['Metric', 'Value'], [
        ['Windows tested',          fmt_num(len(valid))],
        ['Total OOS trades',        fmt_num(total_tr)],
        ['**Avg WR across windows**', f'**{fmt_pct(avg_wr * 100)}**'],
        ['WR Std Dev',              fmt_pct(std_wr * 100)],
        ['WR Coeff of Variation',   f'{cv:.3f} ({"STABLE" if cv < 0.15 else "VOLATILE"})'],
        ['Avg Expectancy/trade',    fmt_pct(avg_exp * 100)],
        ['Avg Window Sharpe',       f'{avg_sh:.2f}'],
        ['% Windows Profitable',    fmt_pct(pct_prof)],
        ['% Windows Low Sample',    fmt_pct(pct_low)],
    ]) + '\n'
    out += f'\n**Verdict: {_verdict(pct_prof, avg_wr, low_sample_majority=pct_low > 50)}**\n\n'

    # Per-window detail table
    out += '**Per-Window Results:**\n\n'
    tbl = []
    for r in valid:
        ws = r['window_start'].strftime('%Y-%m')
        we = r['window_end'].strftime('%Y-%m')
        pf_s = f"{r['profit_factor']:.2f}" if r['profit_factor'] < 100 else '>100'
        tbl.append([
            f'{ws}→{we}',
            fmt_num(r['trades']),
            fmt_pct(r['win_rate'] * 100),
            fmt_pct(r['expectancy'] * 100),
            pf_s,
            f"{r['sharpe']:.2f}",
            '✅' if r['profitable'] else '❌',
            'LOW' if r.get('low_sample', False) else 'OK',
        ])
    out += md_table(
        ['Window', 'Trades', 'Win Rate', 'Expectancy', 'Prof Factor', 'Sharpe', 'OK', 'Sample'],
        tbl,
    ) + '\n'
    if pct_low > 0:
        out += '_Windows marked LOW have fewer than 100 trades and should be treated as indicative only._\n\n'
    return out


def section_regime(label: str, trades: pd.DataFrame, regime_s: pd.Series) -> str:
    if trades.empty:
        return ''
    out = f'\n**{label} — By Volatility Regime:**\n\n'
    regime_at = regime_s.reindex(trades['entry_time'], method='ffill').values
    rows = []
    for reg in ['Low', 'Normal', 'High']:
        sub = trades[regime_at == reg]
        n   = len(sub)
        if n < 20:
            rows.append([reg, fmt_num(n), 'N/A', 'N/A', 'N/A', 'Insufficient data'])
            continue
        rets = sub['return_pct'].values
        wr   = (rets > 0).mean()
        exp  = rets.mean()
        g_w  = rets[rets > 0].sum() if (rets > 0).any() else 0.0
        g_l  = abs(rets[rets < 0].sum()) if (rets < 0).any() else 0.0
        pf   = g_w / g_l if g_l > 0 else 999.0
        rows.append([reg, fmt_num(n), fmt_pct(wr * 100), fmt_pct(exp * 100), f'{pf:.2f}', ''])
    out += md_table(
        ['Regime', 'Trades', 'Win Rate', 'Expectancy', 'Prof Factor', 'Notes'],
        rows,
    ) + '\n'
    return out


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(tickers=None, window_months: int = 6):
    tickers = tickers or TICKERS
    cross_rows = []

    for ticker in tickers:
        progress('Starting TF combo walk-forward validation', ticker)

        df_1m = load_ticker_1m(ticker)
        if df_1m.empty:
            progress('No data, skipping.', ticker)
            continue

        cfg = load_config(ticker=ticker)
        progress(
            f'Loaded {len(df_1m):,} bars '
            f'({df_1m.index.min().date()} → {df_1m.index.max().date()})',
            ticker,
        )

        progress('Computing volatility regime...', ticker)
        regime = vol_regime(df_1m)

        windows = build_windows(df_1m.index.min(), df_1m.index.max(), window_months)
        progress(f'Built {len(windows)} non-overlapping {window_months}-month windows', ticker)

        report = md_header(f'Walk-Forward Validation: TF Combos — {ticker}', 1)
        report += f'\nGenerated: {timestamp_str()}\n'
        report += (
            f'Data: {df_1m.index.min().date()} → {df_1m.index.max().date()} '
            f'({len(df_1m):,} 1m bars)\n'
            f'Windows: {len(windows)} non-overlapping {window_months}-month periods\n\n'
        )
        report += (
            '> **Method**: Run each combo on the full dataset, slice trades into rolling\n'
            '> windows to assess consistency. No parameters are optimised on training data;\n'
            '> this tests whether the edge is robust across market regimes.\n\n'
        )
        report += md_header('Results by Timeframe Combo', 2)

        combo_summaries = []

        for entry_tf, filter_tf, label, desc in COMBOS:
            progress(f'Running {label}...', ticker)
            try:
                all_trades = run_combo_full(df_1m, entry_tf, filter_tf, cfg)
            except Exception as exc:
                progress(f'ERROR: {exc}', ticker)
                report += f'\n### {label}\nError: {exc}\n\n'
                continue

            if all_trades.empty:
                progress(f'No trades for {label}', ticker)
                report += f'\n### {label}\nNo trades generated.\n\n'
                continue

            n_total   = len(all_trades)
            overall_wr = (all_trades['return_pct'] > 0).mean()
            progress(f'  {n_total:,} trades, overall WR={overall_wr:.1%}', ticker)

            win_results = [window_metrics(all_trades, ws, we) for ws, we in windows]

            report += section_combo(label, desc, win_results)
            report += section_regime(label, all_trades, regime)

            # Save per-window CSV
            csv_dir = REPORTS_DIR / 'data'
            csv_dir.mkdir(exist_ok=True)
            wf_df = pd.DataFrame([r for r in win_results if r is not None])
            wf_df.to_csv(
                csv_dir / f'wf_tf_combos_{ticker.lower()}_{label.replace("+", "_")}.csv',
                index=False,
            )

            valid = [r for r in win_results if r is not None]
            if valid:
                avg_wr   = np.mean([r['win_rate']   for r in valid])
                pct_prof = sum(1 for r in valid if r['profitable']) / len(valid) * 100
                cv       = np.std([r['win_rate'] for r in valid]) / avg_wr if avg_wr > 0 else 999.0
                combo_summaries.append({
                    'combo':                  label,
                    'total_trades':           n_total,
                    'overall_wr':             overall_wr,
                    'avg_window_wr':          avg_wr,
                    'pct_windows_profitable': pct_prof,
                    'stable':                 cv < 0.15,
                })
                cross_rows.append({
                    'ticker':                 ticker,
                    'combo':                  label,
                    'total_trades':           n_total,
                    'overall_wr':             overall_wr,
                    'avg_window_wr':          avg_wr,
                    'pct_windows_profitable': pct_prof,
                })

        # Summary table for this ticker
        if combo_summaries:
            report += md_header('Summary: All Combos', 2)
            sorted_cs = sorted(combo_summaries, key=lambda x: x['avg_window_wr'], reverse=True)
            report += md_table(
                ['Combo', 'Total Trades', 'Overall WR', 'Avg Window WR',
                 '% Windows Profitable', 'Stability'],
                [
                    [
                        s['combo'],
                        fmt_num(s['total_trades']),
                        fmt_pct(s['overall_wr'] * 100),
                        fmt_pct(s['avg_window_wr'] * 100),
                        fmt_pct(s['pct_windows_profitable']),
                        '✅ STABLE' if s['stable'] else '⚠️ VOLATILE',
                    ]
                    for s in sorted_cs
                ],
            ) + '\n'

        fn = f'walk_forward_tf_combos_{ticker.lower()}.md'
        save_report(report, fn)
        progress(f'Report saved: reports/{fn}', ticker)

    # Cross-ticker summary
    if len(tickers) > 1 and cross_rows:
        report = md_header('Walk-Forward TF Combos — Cross-Ticker Summary', 1)
        report += f'\nGenerated: {timestamp_str()}\n\n'

        ct_df = pd.DataFrame(cross_rows)
        for combo in [c[2] for c in COMBOS]:
            sub = ct_df[ct_df['combo'] == combo]
            if sub.empty:
                continue
            report += md_header(combo, 2)
            report += md_table(
                ['Ticker', 'Trades', 'Overall WR', 'Avg Window WR', '% Windows Profitable'],
                [
                    [
                        r['ticker'],
                        fmt_num(r['total_trades']),
                        fmt_pct(r['overall_wr'] * 100),
                        fmt_pct(r['avg_window_wr'] * 100),
                        fmt_pct(r['pct_windows_profitable']),
                    ]
                    for _, r in sub.iterrows()
                ],
            ) + '\n'

        save_report(report, 'walk_forward_tf_combos_summary.md')
        print('  Cross-ticker summary saved: reports/walk_forward_tf_combos_summary.md')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Walk-forward validation of timeframe combo strategies',
    )
    parser.add_argument('--tickers', nargs='+', default=TICKERS,
                        choices=['IWM', 'SPY', 'QQQ'])
    parser.add_argument('--window-months', type=int, default=6,
                        help='Window size in months (default: 6)')
    args = parser.parse_args()
    run(tickers=args.tickers, window_months=args.window_months)


if __name__ == '__main__':
    main()
