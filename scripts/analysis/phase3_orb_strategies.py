#!/usr/bin/env python3
"""
Phase 3: ORB-Based Strategies — Per-Ticker ORB Analysis & Backtests

Produces per-ticker:
  3A. ORB Breakout + Strat Confirmation backtest
  3B. ORB Failure / Mean Reversion backtest
  3C. ORB Range-Bound strategy backtest
  3D. ORB Width Analysis (characteristics per ticker)

Output: reports/phase3_orb_strategies_{ticker}.md
"""

import sys
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import time, datetime, timedelta
from typing import Dict, List, Tuple, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.analysis.shared_utils import (
    TICKERS, REPORTS_DIR, MARKET_OPEN,
    load_ticker_1m, enrich_with_indicators, classify_strat_series,
    md_header, md_table, fmt_pct, fmt_bps, fmt_num, save_report,
    timestamp_str, sample_size_label, progress,
    IndicatorConfig,
)


# ---------------------------------------------------------------------------
# 3D. ORB Width Analysis (run first — it informs the strategies)
# ---------------------------------------------------------------------------

def analyze_orb_width(ticker: str, df: pd.DataFrame) -> str:
    """Analyze ORB characteristics per ticker across different windows."""
    report = md_header(f"3D. ORB Width Analysis — {ticker}", 2)
    report += "\nORB characteristics, breakout frequency, and timing.\n\n"

    close = df['Close'] if 'Close' in df.columns else df['Last']
    dates = pd.to_datetime(df.index).date if isinstance(df.index, pd.DatetimeIndex) else pd.to_datetime(df['Time']).dt.date

    for orb_label in ['5m', '15m', '30m']:
        range_col = f'ORB_{orb_label}_Range'
        high_col = f'ORB_{orb_label}_High'
        low_col = f'ORB_{orb_label}_Low'
        broke_high = f'ORB_{orb_label}_Broke_High'
        broke_low = f'ORB_{orb_label}_Broke_Low'
        within_col = f'ORB_{orb_label}_Within_Range'
        trend_col = f'ORB_{orb_label}_Trend'

        if range_col not in df.columns:
            continue

        report += md_header(f"{ticker}: {orb_label} ORB", 3)

        # ORB range statistics (as % of price)
        orb_range_pct = df[range_col] / close * 100
        orb_range_pct = orb_range_pct.replace([np.inf, -np.inf], np.nan).dropna()

        if len(orb_range_pct) == 0:
            report += "No ORB data.\n\n"
            continue

        # Per-day stats
        day_series = pd.Series(dates, index=df.index)
        daily_orb = df.groupby(day_series).agg({
            range_col: 'first',
            high_col: 'first',
            low_col: 'first',
        }).dropna()

        if daily_orb.empty:
            report += "No daily ORB data.\n\n"
            continue

        daily_range = daily_orb[range_col]
        daily_high = daily_orb[high_col]
        daily_low = daily_orb[low_col]

        # Range in bps (relative to price)
        first_close = df.groupby(day_series)['Close'].first() if 'Close' in df.columns else df.groupby(day_series)['Last'].first()
        daily_range_bps = (daily_range / first_close * 10000).dropna()

        report += "**ORB Range Statistics:**\n\n"
        headers = ['Metric', 'Value']
        rows = [
            ['Mean Range (bps)', fmt_bps(daily_range_bps.mean())],
            ['Median Range (bps)', fmt_bps(daily_range_bps.median())],
            ['P10 Range (bps)', fmt_bps(daily_range_bps.quantile(0.1))],
            ['P25 Range (bps)', fmt_bps(daily_range_bps.quantile(0.25))],
            ['P75 Range (bps)', fmt_bps(daily_range_bps.quantile(0.75))],
            ['P90 Range (bps)', fmt_bps(daily_range_bps.quantile(0.9))],
            ['Trading Days', fmt_num(len(daily_range))],
        ]
        report += md_table(headers, rows) + '\n'

        # Breakout frequency and timing
        if broke_high in df.columns:
            # Filter to post-ORB bars only
            times = pd.to_datetime(df.index).time if isinstance(df.index, pd.DatetimeIndex) else pd.to_datetime(df['Time']).dt.time
            orb_end_time = (datetime.combine(datetime.today(), MARKET_OPEN) + timedelta(minutes=int(orb_label.replace('m', '')))).time()
            post_orb = pd.Series(times, index=df.index).apply(lambda t: t > orb_end_time)

            post_df = df[post_orb]
            if len(post_df) > 0:
                # Per-day breakout stats
                day_broke_high = post_df.groupby(pd.to_datetime(post_df.index).date)[broke_high].max()
                day_broke_low = post_df.groupby(pd.to_datetime(post_df.index).date)[broke_low].max()

                pct_broke_high = day_broke_high.mean() * 100
                pct_broke_low = day_broke_low.mean() * 100
                pct_contained = (1 - day_broke_high.clip(0, 1) - day_broke_low.clip(0, 1)).clip(0, 1).mean() * 100

                report += "**Breakout Frequency:**\n\n"
                headers = ['Outcome', 'Frequency']
                rows = [
                    ['Broke ORB High', fmt_pct(pct_broke_high)],
                    ['Broke ORB Low', fmt_pct(pct_broke_low)],
                    ['Stayed Within ORB', fmt_pct(max(0, 100 - pct_broke_high - pct_broke_low))],
                ]
                report += md_table(headers, rows) + '\n'

                # Breakout timing: when does first breakout happen?
                first_breakout_times = []
                for day, day_group in post_df.groupby(pd.to_datetime(post_df.index).date):
                    broke = day_group[(day_group[broke_high] == 1) | (day_group[broke_low] == 1)]
                    if len(broke) > 0:
                        first_time = pd.to_datetime(broke.index[0]).time()
                        minutes_after_orb = (first_time.hour * 60 + first_time.minute) - \
                                           (orb_end_time.hour * 60 + orb_end_time.minute)
                        first_breakout_times.append(minutes_after_orb)

                if first_breakout_times:
                    bt = pd.Series(first_breakout_times)
                    report += "**Breakout Timing (minutes after ORB close):**\n\n"
                    headers = ['Metric', 'Value']
                    rows = [
                        ['Median first breakout', f"{bt.median():.0f} min"],
                        ['Mean first breakout', f"{bt.mean():.0f} min"],
                        ['P25 (fast breakout)', f"{bt.quantile(0.25):.0f} min"],
                        ['P75 (slow breakout)', f"{bt.quantile(0.75):.0f} min"],
                    ]
                    report += md_table(headers, rows) + '\n'

        # ORB range vs daily range correlation
        if 'High' in df.columns and 'Low' in df.columns:
            daily_full_range = df.groupby(day_series).agg({'High': 'max', 'Low': 'min'})
            daily_full_range['full_range'] = daily_full_range['High'] - daily_full_range['Low']
            merged = pd.DataFrame({
                'orb_range': daily_range,
                'full_range': daily_full_range['full_range'],
            }).dropna()

            if len(merged) > 30:
                corr = merged['orb_range'].corr(merged['full_range'])
                report += f"\n**ORB Range vs Daily Range Correlation:** {corr:.3f}\n\n"

    return report


# ---------------------------------------------------------------------------
# ORB Strategy Backtests (3A, 3B, 3C)
# ---------------------------------------------------------------------------

def backtest_orb_strategy(
    df: pd.DataFrame,
    strategy: str,
    orb_label: str = '30m',
    target_bps: float = 30,
    stop_bps: float = 15,
    time_stop_min: int = 30,
    min_confirmations: int = 2,
) -> Dict:
    """Backtest an ORB-based strategy using vectorized entry detection
    and per-day bar-by-bar exit simulation (fast enough for ~2700 trading days)."""
    close = df['Close'] if 'Close' in df.columns else df['Last']
    labels = df['strat_type'] if 'strat_type' in df.columns else classify_strat_series(df)

    broke_high = f'ORB_{orb_label}_Broke_High'
    broke_low = f'ORB_{orb_label}_Broke_Low'
    high_col = f'ORB_{orb_label}_High'
    low_col = f'ORB_{orb_label}_Low'

    required_cols = [broke_high, broke_low, high_col, low_col]
    if not all(c in df.columns for c in required_cols):
        return {'trades': 0, 'win_rate': 0, 'pf': 0, 'sharpe': 0, 'expectancy': 0,
                'strategy': strategy, 'orb_label': orb_label, 'avg_return': 0}

    ind = IndicatorConfig()
    rsi_col = ind.rsi_col

    orb_minutes = int(orb_label.replace('m', ''))
    orb_end_time = (datetime.combine(datetime.today(), MARKET_OPEN) + timedelta(minutes=orb_minutes)).time()

    # --- Vectorized entry signal detection ---
    bar_times = pd.to_datetime(df.index).time
    post_orb = pd.Series(bar_times, index=df.index).apply(lambda t: t > orb_end_time)

    rsi = df[rsi_col] if rsi_col in df.columns else pd.Series(50, index=df.index)
    vwap_pos = df.get('Price_vs_VWAP', pd.Series(0, index=df.index))
    ema_cross = df.get('EMA_Cross', pd.Series(0, index=df.index))
    ob_high = df[high_col]
    ob_low = df[low_col]

    is_above = (close > ob_high) & ob_high.notna()
    is_below = (close < ob_low) & ob_low.notna()
    is_within = ~is_above & ~is_below & ob_high.notna()

    prev_close = close.shift(1)
    prev_above = (prev_close > ob_high) & ob_high.notna()
    prev_below = (prev_close < ob_low) & ob_low.notna()

    call_signal = pd.Series(False, index=df.index)
    put_signal = pd.Series(False, index=df.index)

    if strategy == 'breakout':
        confirms_bull = ((rsi > 40) & (rsi < 70)).astype(int) + (vwap_pos > 0).astype(int) + (ema_cross == 1).astype(int)
        confirms_bear = ((rsi > 30) & (rsi < 60)).astype(int) + (vwap_pos < 0).astype(int) + (ema_cross == 0).astype(int)

        call_signal = post_orb & is_above & labels.isin(['2U', '3']) & (confirms_bull >= min_confirmations)
        put_signal = post_orb & is_below & labels.isin(['2D', '3']) & (confirms_bear >= min_confirmations)

    elif strategy == 'failure':
        call_signal = post_orb & prev_below & is_within & (labels == '2U') & (rsi < 40)
        put_signal = post_orb & prev_above & is_within & (labels == '2D') & (rsi > 60)

    elif strategy == 'range_bound':
        elapsed_post = pd.Series(bar_times, index=df.index).apply(
            lambda t: (t.hour * 60 + t.minute) - (orb_end_time.hour * 60 + orb_end_time.minute)
        )
        orb_range = ob_high - ob_low
        pct_in_range = ((close - ob_low) / orb_range.where(orb_range > 0, np.nan)).fillna(0.5)

        call_signal = post_orb & is_within & (elapsed_post >= 15) & (pct_in_range < 0.2) & labels.isin(['2U', '1']) & (rsi < 45)
        put_signal = post_orb & is_within & (elapsed_post >= 15) & (pct_in_range > 0.8) & labels.isin(['2D', '1']) & (rsi > 55)

    # --- Simulate trades day by day (fast: ~2700 iterations) ---
    dates_arr = pd.to_datetime(df.index).date
    day_series = pd.Series(dates_arr, index=df.index)
    unique_days = sorted(set(dates_arr))

    trades = []
    close_arr = close.values
    call_arr = call_signal.values
    put_arr = put_signal.values
    idx_arr = df.index

    for day in unique_days:
        day_mask = day_series == day
        day_indices = np.where(day_mask.values)[0]
        if len(day_indices) == 0:
            continue

        daily_trades = 0
        in_trade = False
        entry_price = 0.0
        entry_idx = 0
        trade_direction = None

        for pos in day_indices:
            price = close_arr[pos]

            if in_trade:
                if trade_direction == 'CALL':
                    unrealized = (price - entry_price) / entry_price * 10000
                else:
                    unrealized = (entry_price - price) / entry_price * 10000

                elapsed = (pos - entry_idx)  # bars as proxy for minutes (1m bars)

                exit_reason = None
                if unrealized >= target_bps:
                    exit_reason = 'target'
                elif unrealized <= -stop_bps:
                    exit_reason = 'stop'
                elif elapsed >= time_stop_min:
                    exit_reason = 'time_stop'

                if exit_reason:
                    trades.append({
                        'entry_time': idx_arr[entry_idx],
                        'direction': trade_direction,
                        'return_bps': unrealized,
                        'exit_reason': exit_reason,
                        'won': unrealized > 0,
                    })
                    in_trade = False
                    daily_trades += 1
                continue

            if daily_trades >= 3:
                continue

            if call_arr[pos]:
                in_trade = True
                entry_price = price
                entry_idx = pos
                trade_direction = 'CALL'
            elif put_arr[pos]:
                in_trade = True
                entry_price = price
                entry_idx = pos
                trade_direction = 'PUT'

        # Force-close EOD
        if in_trade:
            last_price = close_arr[day_indices[-1]]
            if trade_direction == 'CALL':
                unrealized = (last_price - entry_price) / entry_price * 10000
            else:
                unrealized = (entry_price - last_price) / entry_price * 10000
            trades.append({
                'entry_time': idx_arr[entry_idx],
                'direction': trade_direction,
                'return_bps': unrealized,
                'exit_reason': 'eod',
                'won': unrealized > 0,
            })

    # Compute summary stats
    if not trades:
        return {
            'strategy': strategy, 'orb_label': orb_label,
            'trades': 0, 'win_rate': 0, 'pf': 0,
            'sharpe': 0, 'expectancy': 0, 'avg_return': 0,
        }

    trades_df = pd.DataFrame(trades)
    total = len(trades_df)
    winners = trades_df[trades_df['won'] == True]
    losers = trades_df[trades_df['won'] == False]
    win_rate = len(winners) / total if total > 0 else 0
    avg_win = winners['return_bps'].mean() if len(winners) > 0 else 0
    avg_loss = losers['return_bps'].mean() if len(losers) > 0 else 0
    pf = abs(winners['return_bps'].sum() / losers['return_bps'].sum()) if len(losers) > 0 and losers['return_bps'].sum() != 0 else 0
    expectancy = trades_df['return_bps'].mean()

    # Simple Sharpe
    trades_df['entry_date'] = pd.to_datetime(trades_df['entry_time']).dt.date
    daily_returns = trades_df.groupby('entry_date')['return_bps'].sum()
    sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(252)) if daily_returns.std() > 0 else 0

    return {
        'strategy': strategy,
        'orb_label': orb_label,
        'trades': total,
        'win_rate': win_rate,
        'pf': pf,
        'sharpe': sharpe,
        'expectancy': expectancy,
        'avg_return': trades_df['return_bps'].mean(),
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'trades_df': trades_df,
    }


def analyze_orb_strategies(ticker: str, df: pd.DataFrame) -> str:
    """Run all ORB strategies and compare results."""
    report = md_header(f"3A-3C. ORB Strategy Backtests — {ticker}", 2)
    report += "\nComparing ORB breakout, failure, and range-bound strategies.\n\n"

    strategies = ['breakout', 'failure', 'range_bound']
    orb_labels = ['5m', '15m', '30m']

    all_results = []

    for orb_label in orb_labels:
        for strategy in strategies:
            progress(f"  Backtesting {strategy} / {orb_label} ORB", ticker)
            result = backtest_orb_strategy(df, strategy, orb_label=orb_label)
            all_results.append(result)

    # Summary table per ORB window
    for orb_label in orb_labels:
        report += md_header(f"{ticker}: {orb_label} ORB Results", 3)

        headers = ['Strategy', 'Trades', 'Win Rate', 'Profit Factor',
                   'Sharpe', 'Expectancy (bps)', 'Avg Win', 'Avg Loss']
        rows = []

        for result in all_results:
            if result['orb_label'] != orb_label:
                continue
            rows.append([
                result['strategy'].replace('_', ' ').title(),
                fmt_num(result['trades']),
                fmt_pct(result['win_rate'] * 100),
                f"{result['pf']:.2f}",
                f"{result['sharpe']:.2f}",
                fmt_bps(result['expectancy']),
                fmt_bps(result.get('avg_win', 0)),
                fmt_bps(result.get('avg_loss', 0)),
            ])

        report += md_table(headers, rows) + '\n'

    # Best strategy per ticker
    best = max([r for r in all_results if r['trades'] >= 30],
               key=lambda x: x['sharpe'], default=None)
    if best:
        report += f"\n**Best strategy for {ticker}:** {best['strategy']} with {best['orb_label']} ORB "
        report += f"(Sharpe {best['sharpe']:.2f}, WR {best['win_rate']:.1%}, n={best['trades']})\n\n"

    # Exit reason breakdown for best
    if best and 'trades_df' in best and not best['trades_df'].empty:
        report += md_header(f"Exit Reason Breakdown — {best['strategy']}/{best['orb_label']}", 4)
        exit_breakdown = best['trades_df'].groupby('exit_reason').agg(
            trades=('won', 'count'),
            win_rate=('won', 'mean'),
            avg_return=('return_bps', 'mean'),
        ).round(2)
        headers = ['Exit Reason', 'Trades', 'Win Rate', 'Avg Return (bps)']
        rows = []
        for reason, r in exit_breakdown.iterrows():
            rows.append([reason, fmt_num(r['trades']), fmt_pct(r['win_rate'] * 100), fmt_bps(r['avg_return'])])
        report += md_table(headers, rows) + '\n'

    return report


# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------

def run_phase3(tickers: list = None):
    """Run full Phase 3 analysis for all tickers."""
    if tickers is None:
        tickers = TICKERS

    for ticker in tickers:
        progress(f"Starting Phase 3 analysis", ticker)

        # Load and enrich
        progress("Loading and enriching 1m data...", ticker)
        df_1m = load_ticker_1m(ticker)
        if df_1m.empty:
            progress("No data, skipping.", ticker)
            continue

        df = enrich_with_indicators(df_1m)
        progress(f"Enriched {len(df):,} bars", ticker)

        # Build report
        report = md_header(f"Phase 3: ORB-Based Strategies — {ticker}", 1)
        report += f"\nGenerated: {timestamp_str()}\n"
        report += f"Data: {df.index.min()} to {df.index.max()} ({len(df):,} bars)\n\n"

        # 3D first (informs strategy design)
        progress("Analyzing ORB width...", ticker)
        report += analyze_orb_width(ticker, df)

        # 3A-3C strategies
        progress("Running ORB strategy backtests...", ticker)
        report += analyze_orb_strategies(ticker, df)

        save_report(report, f'phase3_orb_strategies_{ticker.lower()}.md')
        progress("Phase 3 complete!", ticker)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Phase 3: ORB Strategies')
    parser.add_argument('--tickers', nargs='+', default=TICKERS)
    args = parser.parse_args()
    run_phase3(tickers=args.tickers)
