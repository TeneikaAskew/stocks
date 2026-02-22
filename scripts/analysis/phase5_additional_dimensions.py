#!/usr/bin/env python3
"""
Phase 5: Additional Dimensions — Regime, Time, Day, Cross-Ticker, Drawdown, Options, Walk-Forward

Produces:
  5A. Market regime analysis (ATR-based volatility regime)
  5B. Time-of-day analysis
  5C. Day-of-week analysis
  5D. Cross-ticker correlation & confirmation
  5E. Drawdown & streak analysis per setup
  5F. Options-specific P/L translation
  5G. Walk-forward validation

Output: reports/phase5_additional_dimensions_{ticker}.md
"""

import sys
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import time, datetime
from typing import Dict, List, Tuple, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.analysis.shared_utils import (
    TICKERS, REPORTS_DIR, DATA_DIR, PROJECT_ROOT, MARKET_OPEN, MARKET_CLOSE,
    load_ticker_1m, enrich_with_indicators, classify_strat_series,
    build_multi_timeframe_dict, resample_to_timeframe,
    md_header, md_table, fmt_pct, fmt_bps, fmt_num, save_report,
    timestamp_str, sample_size_label, progress,
    IndicatorConfig,
)


# ---------------------------------------------------------------------------
# 5A. Market Regime Analysis
# ---------------------------------------------------------------------------

def analyze_regimes(ticker: str, df: pd.DataFrame) -> str:
    """Segment performance by volatility regime (ATR-based)."""
    report = md_header(f"5A. Market Regime Analysis — {ticker}", 2)
    report += "\nPerformance segmented by ATR-based volatility regime.\n\n"

    ind = IndicatorConfig()
    atr_col = ind.atr_col
    if atr_col not in df.columns:
        return report + "No ATR data available.\n\n"

    close = df['Close'] if 'Close' in df.columns else df['Last']
    labels = df['strat_type'] if 'strat_type' in df.columns else classify_strat_series(df)
    next_return = close.pct_change().shift(-1) * 10000

    # ATR-based regime: rolling 20-day ATR percentile
    # Use daily ATR
    dates = pd.to_datetime(df.index).date
    daily_atr = df.groupby(dates)[atr_col].mean()
    atr_pct_rank = daily_atr.rolling(50, min_periods=20).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
    )

    # Map back to 1m bars
    daily_regime = pd.Series('Normal', index=daily_atr.index)
    daily_regime[atr_pct_rank < 0.25] = 'Low Vol'
    daily_regime[atr_pct_rank > 0.75] = 'High Vol'

    bar_regime = pd.Series(dates, index=df.index).map(daily_regime).fillna('Normal')

    # Trend regime from daily EMAs
    daily_close = df.groupby(dates)['Close'].last() if 'Close' in df.columns else df.groupby(dates)['Last'].last()
    ema20_daily = daily_close.ewm(span=20).mean()
    ema50_daily = daily_close.ewm(span=50).mean()

    daily_trend = pd.Series('Range-Bound', index=daily_close.index)
    daily_trend[(ema20_daily > ema50_daily) & (daily_close > ema20_daily)] = 'Trending Up'
    daily_trend[(ema20_daily < ema50_daily) & (daily_close < ema20_daily)] = 'Trending Down'

    bar_trend = pd.Series(dates, index=df.index).map(daily_trend).fillna('Range-Bound')

    # Volatility regime table
    report += md_header("Volatility Regime Performance", 3)
    headers = ['Regime', 'Bars', '% of Data', 'Avg Next Return (bps)',
               '2U Freq', '2D Freq', 'Type 3 Freq', 'Suggested Target Adj']
    rows = []

    for regime in ['Low Vol', 'Normal', 'High Vol']:
        mask = bar_regime == regime
        n = mask.sum()
        if n < 100:
            continue

        pct = n / len(df) * 100
        avg_ret = next_return[mask].mean()
        l = labels[mask]
        p2u = (l == '2U').mean() * 100
        p2d = (l == '2D').mean() * 100
        p3 = (l == '3').mean() * 100

        adj = '0.5x' if regime == 'Low Vol' else ('2x' if regime == 'High Vol' else '1x')

        rows.append([
            f"**{regime}**", fmt_num(n), fmt_pct(pct),
            fmt_bps(avg_ret), fmt_pct(p2u), fmt_pct(p2d),
            fmt_pct(p3), adj,
        ])

    report += md_table(headers, rows) + '\n'

    # Trend regime table
    report += md_header("Trend Regime Performance", 3)
    headers = ['Regime', 'Days', '% of Data', 'Avg Next Return (bps)',
               '2U Freq', '2D Freq', 'CALL Edge', 'PUT Edge']
    rows = []

    for regime in ['Trending Up', 'Range-Bound', 'Trending Down']:
        mask = bar_trend == regime
        n = mask.sum()
        if n < 100:
            continue

        pct = n / len(df) * 100
        avg_ret = next_return[mask].mean()
        l = labels[mask]
        p2u = (l == '2U').mean() * 100
        p2d = (l == '2D').mean() * 100

        # Edge for CALL vs PUT
        call_edge = fmt_bps(next_return[mask & (labels == '2U')].mean()) if (mask & (labels == '2U')).sum() > 0 else 'N/A'
        put_edge = fmt_bps((-next_return)[mask & (labels == '2D')].mean()) if (mask & (labels == '2D')).sum() > 0 else 'N/A'

        rows.append([
            f"**{regime}**", fmt_num(n), fmt_pct(pct),
            fmt_bps(avg_ret), fmt_pct(p2u), fmt_pct(p2d),
            call_edge, put_edge,
        ])

    report += md_table(headers, rows) + '\n'

    # Regime-adaptive targets
    report += md_header("Suggested Regime-Adaptive Targets", 3)

    for regime in ['Low Vol', 'Normal', 'High Vol']:
        mask = bar_regime == regime
        if mask.sum() < 100:
            continue

        rets = next_return[mask].dropna()
        report += f"\n**{regime}:** "
        report += f"Avg move = {fmt_bps(rets.abs().mean())}, "
        report += f"P75 = {fmt_bps(rets.abs().quantile(0.75))}, "
        report += f"P90 = {fmt_bps(rets.abs().quantile(0.90))}\n"

    report += "\n"
    return report


# ---------------------------------------------------------------------------
# 5B. Time-of-Day Analysis
# ---------------------------------------------------------------------------

def analyze_time_of_day(ticker: str, df: pd.DataFrame) -> str:
    """Analyze performance by time-of-day windows."""
    report = md_header(f"5B. Time-of-Day Analysis — {ticker}", 2)
    report += "\nPerformance by intraday time window.\n\n"

    close = df['Close'] if 'Close' in df.columns else df['Last']
    labels = df['strat_type'] if 'strat_type' in df.columns else classify_strat_series(df)
    next_return = close.pct_change().shift(-1) * 10000

    times = pd.to_datetime(df.index).time

    windows = [
        ('Open (9:30-10:00)', time(9, 30), time(10, 0)),
        ('Mid-Morning (10:00-11:00)', time(10, 0), time(11, 0)),
        ('Midday (11:00-13:00)', time(11, 0), time(13, 0)),
        ('Afternoon (13:00-15:00)', time(13, 0), time(15, 0)),
        ('Close (15:00-16:00)', time(15, 0), time(16, 0)),
    ]

    headers = ['Window', 'Bars', '% of Data', 'Avg Return (bps)',
               'Std (bps)', '2U %', '2D %', '3 %',
               'CALL Edge', 'PUT Edge']
    rows = []

    for label, start, end in windows:
        time_series = pd.Series(times, index=df.index)
        mask = time_series.apply(lambda t: start <= t < end)
        n = mask.sum()
        if n < 100:
            continue

        pct = n / len(df) * 100
        avg_ret = next_return[mask].mean()
        std_ret = next_return[mask].std()
        l = labels[mask]
        p2u = (l == '2U').mean() * 100
        p2d = (l == '2D').mean() * 100
        p3 = (l == '3').mean() * 100

        # Directional edges
        call_rets = next_return[mask & (next_return > 0)]
        put_rets = (-next_return)[mask & (next_return < 0)]
        call_edge = fmt_bps(call_rets.mean()) if len(call_rets) > 0 else 'N/A'
        put_edge = fmt_bps(put_rets.mean()) if len(put_rets) > 0 else 'N/A'

        rows.append([
            f"**{label}**", fmt_num(n), fmt_pct(pct),
            fmt_bps(avg_ret), fmt_bps(std_ret),
            fmt_pct(p2u), fmt_pct(p2d), fmt_pct(p3),
            call_edge, put_edge,
        ])

    report += md_table(headers, rows) + '\n'

    # Optimal entry windows
    report += md_header("Optimal Entry Windows", 3)
    report += "Current config: CALL 9:30-10:00, PUT 9:30-14:00\n\n"

    for direction in ['CALL', 'PUT']:
        report += f"\n**{direction} by half-hour window:**\n\n"
        headers = ['Window', 'Bars', f'{direction} Next Return', 'Win Rate']
        rows = []

        for hour in range(9, 16):
            for minute in [0, 30]:
                start = time(hour, minute)
                end_m = minute + 30
                if end_m >= 60:
                    end = time(hour + 1, end_m - 60) if hour < 15 else time(16, 0)
                else:
                    end = time(hour, end_m)

                if start < time(9, 30):
                    continue

                time_series = pd.Series(times, index=df.index)
                mask = time_series.apply(lambda t: start <= t < end)
                n = mask.sum()
                if n < 50:
                    continue

                if direction == 'CALL':
                    rets = next_return[mask]
                    wr = (rets > 0).mean()
                else:
                    rets = -next_return[mask]
                    wr = (rets > 0).mean()

                rows.append([
                    f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}",
                    fmt_num(n),
                    fmt_bps(rets.mean()),
                    fmt_pct(wr * 100),
                ])

        report += md_table(headers, rows) + '\n'

    return report


# ---------------------------------------------------------------------------
# 5C. Day-of-Week Analysis
# ---------------------------------------------------------------------------

def analyze_day_of_week(ticker: str, df: pd.DataFrame) -> str:
    """Analyze performance by day of week."""
    report = md_header(f"5C. Day-of-Week Analysis — {ticker}", 2)
    report += "\nPerformance by trading day.\n\n"

    close = df['Close'] if 'Close' in df.columns else df['Last']
    labels = df['strat_type'] if 'strat_type' in df.columns else classify_strat_series(df)
    next_return = close.pct_change().shift(-1) * 10000

    day_of_week = pd.to_datetime(df.index).dayofweek  # 0=Mon, 4=Fri
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

    headers = ['Day', 'Bars', 'Avg Return (bps)', 'Volatility (bps)',
               '2U %', '2D %', '3 %', 'CALL WR', 'PUT WR']
    rows = []

    for dow in range(5):
        mask = day_of_week == dow
        n = mask.sum()
        if n < 100:
            continue

        avg_ret = next_return[mask].mean()
        vol = next_return[mask].std()
        l = labels[mask]
        p2u = (l == '2U').mean() * 100
        p2d = (l == '2D').mean() * 100
        p3 = (l == '3').mean() * 100

        call_wr = (next_return[mask] > 0).mean() * 100
        put_wr = (next_return[mask] < 0).mean() * 100

        rows.append([
            f"**{day_names[dow]}**", fmt_num(n),
            fmt_bps(avg_ret), fmt_bps(vol),
            fmt_pct(p2u), fmt_pct(p2d), fmt_pct(p3),
            fmt_pct(call_wr), fmt_pct(put_wr),
        ])

    report += md_table(headers, rows) + '\n'

    return report


# ---------------------------------------------------------------------------
# 5D. Cross-Ticker Correlation & Confirmation
# ---------------------------------------------------------------------------

def analyze_cross_ticker(all_data: Dict[str, pd.DataFrame]) -> str:
    """Analyze cross-ticker correlations and confirmation effects."""
    report = md_header("5D. Cross-Ticker Correlation & Confirmation", 2)
    report += "\nHow tickers' Strat patterns relate to each other.\n\n"

    if len(all_data) < 2:
        return report + "Need at least 2 tickers for cross-correlation.\n\n"

    # Align all tickers to common timestamps
    common_index = None
    for ticker, df in all_data.items():
        if common_index is None:
            common_index = df.index
        else:
            common_index = common_index.intersection(df.index)

    if len(common_index) < 1000:
        return report + "Insufficient overlapping bars.\n\n"

    report += f"Overlapping bars: {len(common_index):,}\n\n"

    # Return correlations
    report += md_header("Return Correlations", 3)
    returns = {}
    for ticker, df in all_data.items():
        close = df['Close'] if 'Close' in df.columns else df['Last']
        returns[ticker] = close.reindex(common_index).pct_change()

    corr_matrix = pd.DataFrame(returns).corr()

    headers = ['Ticker'] + list(returns.keys())
    rows = []
    for t1 in returns.keys():
        row = [f"**{t1}**"]
        for t2 in returns.keys():
            row.append(f"{corr_matrix.loc[t1, t2]:.3f}")
        rows.append(row)

    report += md_table(headers, rows) + '\n'

    # Strat alignment analysis
    report += md_header("Strat Alignment Effects", 3)

    strat_labels = {}
    for ticker, df in all_data.items():
        labels = classify_strat_series(df.reindex(common_index).ffill())
        strat_labels[ticker] = labels

    tickers_list = list(all_data.keys())
    close_first = all_data[tickers_list[0]]['Close'].reindex(common_index) if 'Close' in all_data[tickers_list[0]].columns else all_data[tickers_list[0]]['Last'].reindex(common_index)

    # When all tickers show same type
    for stype in ['2U', '2D']:
        all_same = pd.Series(True, index=common_index)
        for ticker in tickers_list:
            all_same &= (strat_labels[ticker] == stype)

        n_same = all_same.sum()
        if n_same < 30:
            continue

        next_rets = {}
        for ticker, df in all_data.items():
            close = df['Close'].reindex(common_index) if 'Close' in df.columns else df['Last'].reindex(common_index)
            next_ret = close.pct_change().shift(-1) * 10000
            next_rets[ticker] = next_ret[all_same].mean()

        report += f"\n**All tickers show {stype}** (n={n_same:,}):\n"
        for ticker, avg_ret in next_rets.items():
            report += f"  - {ticker} avg next return: {fmt_bps(avg_ret)}\n"

    # Confirmation effect: does agreement improve individual ticker's edge?
    report += md_header("Confirmation Effect", 3)
    report += "Does cross-ticker agreement improve win rates?\n\n"

    for target_ticker in tickers_list:
        other_tickers = [t for t in tickers_list if t != target_ticker]

        close = all_data[target_ticker]['Close'].reindex(common_index) if 'Close' in all_data[target_ticker].columns else all_data[target_ticker]['Last'].reindex(common_index)
        next_ret = close.pct_change().shift(-1) * 10000

        target_2u = strat_labels[target_ticker] == '2U'
        others_2u = pd.Series(True, index=common_index)
        for t in other_tickers:
            others_2u &= (strat_labels[t] == '2U')

        # Base: target shows 2U alone
        n_alone = target_2u.sum()
        base_wr = (next_ret[target_2u] > 0).mean() if n_alone > 0 else 0

        # Confirmed: target shows 2U AND others agree
        confirmed = target_2u & others_2u
        n_confirmed = confirmed.sum()
        conf_wr = (next_ret[confirmed] > 0).mean() if n_confirmed > 0 else 0

        report += f"**{target_ticker} 2U signal:**\n"
        report += f"  - Alone: WR={fmt_pct(base_wr * 100)} (n={n_alone:,})\n"
        report += f"  - Confirmed by all others: WR={fmt_pct(conf_wr * 100)} (n={n_confirmed:,})\n"
        report += f"  - Lift: {(conf_wr - base_wr) * 100:+.1f}pp\n\n"

    return report


# ---------------------------------------------------------------------------
# 5E. Drawdown & Streak Analysis
# ---------------------------------------------------------------------------

def analyze_drawdowns(ticker: str, df: pd.DataFrame) -> str:
    """Analyze drawdown and losing streak characteristics."""
    report = md_header(f"5E. Drawdown & Streak Analysis — {ticker}", 2)
    report += "\nWorst-case scenarios and streak analysis.\n\n"

    close = df['Close'] if 'Close' in df.columns else df['Last']
    labels = df['strat_type'] if 'strat_type' in df.columns else classify_strat_series(df)
    next_return = close.pct_change().shift(-1) * 10000

    # Simulate simple trades: every 2U signal is a CALL, every 2D is a PUT
    trades = []
    for i in range(1, len(df)):
        if labels.iloc[i] in ('2U', '2D'):
            direction = 'CALL' if labels.iloc[i] == '2U' else 'PUT'
            ret = next_return.iloc[i]
            if pd.notna(ret):
                won = (ret > 0) if direction == 'CALL' else (ret < 0)
                trades.append({
                    'time': df.index[i],
                    'direction': direction,
                    'return_bps': ret if direction == 'CALL' else -ret,
                    'won': won,
                })

    if not trades:
        return report + "No trades to analyze.\n\n"

    trades_df = pd.DataFrame(trades)

    # Streak analysis
    report += md_header("Losing Streak Distribution", 3)

    streaks = []
    current_streak = 0
    for won in trades_df['won']:
        if not won:
            current_streak += 1
        else:
            if current_streak > 0:
                streaks.append(current_streak)
            current_streak = 0
    if current_streak > 0:
        streaks.append(current_streak)

    if streaks:
        streak_series = pd.Series(streaks)
        headers = ['Metric', 'Value']
        rows = [
            ['Max consecutive losses', fmt_num(streak_series.max())],
            ['Avg losing streak length', f"{streak_series.mean():.1f}"],
            ['Median losing streak', f"{streak_series.median():.0f}"],
            ['Streaks of 3+', fmt_num((streak_series >= 3).sum())],
            ['Streaks of 5+', fmt_num((streak_series >= 5).sum())],
            ['Streaks of 7+', fmt_num((streak_series >= 7).sum())],
            ['Total losing streaks', fmt_num(len(streaks))],
        ]
        report += md_table(headers, rows) + '\n'

        # Distribution
        report += "\n**Streak Length Distribution:**\n\n"
        headers = ['Streak Length', 'Occurrences', '% of Streaks']
        rows = []
        for length in range(1, min(int(streak_series.max()) + 1, 11)):
            count = (streak_series == length).sum()
            pct = count / len(streaks) * 100
            rows.append([str(length), fmt_num(count), fmt_pct(pct)])
        report += md_table(headers, rows) + '\n'

    # Cumulative P&L drawdown
    report += md_header("Cumulative P&L Drawdown", 3)

    cum_pnl = trades_df['return_bps'].cumsum()
    peak = cum_pnl.expanding().max()
    drawdown = cum_pnl - peak

    headers = ['Metric', 'Value']
    rows = [
        ['Max drawdown (bps)', fmt_bps(drawdown.min())],
        ['Max drawdown duration (trades)', fmt_num((drawdown < 0).astype(int).groupby((drawdown >= 0).cumsum()).sum().max() if len(drawdown) > 0 else 0)],
        ['Total P&L (bps)', fmt_bps(cum_pnl.iloc[-1] if len(cum_pnl) > 0 else 0)],
        ['Total trades', fmt_num(len(trades_df))],
        ['Win rate', fmt_pct(trades_df['won'].mean() * 100)],
    ]
    report += md_table(headers, rows) + '\n'

    # Psychological preparation
    report += md_header("Psychological Preparation", 3)
    if streaks:
        max_streak = streak_series.max()
        monthly_3plus = (streak_series >= 3).sum() / (len(trades_df) / 20)  # rough monthly estimate
        report += f'> "This system wins {trades_df["won"].mean():.0%} of the time on {ticker}, '
        report += f'but you should expect 3+ consecutive losses about {monthly_3plus:.1f}x per month. '
        report += f'The max consecutive loss streak in the data was {max_streak}."\n\n'

    return report


# ---------------------------------------------------------------------------
# 5F. Options P/L Translation
# ---------------------------------------------------------------------------

def analyze_options_translation(ticker: str, df: pd.DataFrame) -> str:
    """Translate underlying moves to estimated options P/L."""
    report = md_header(f"5F. Options P/L Translation — {ticker}", 2)
    report += "\nTranslating underlying moves to options P/L estimates.\n\n"

    # Check for options data
    options_dir = DATA_DIR / ticker.lower() / 'options'
    has_options_data = options_dir.exists() and any(options_dir.glob('*.parquet'))

    if has_options_data:
        report += md_header("Actual Options Chain Data Available", 3)

        # Load a sample options file to get typical Greeks
        option_files = sorted(options_dir.glob('*.parquet'))
        sample_files = option_files[-5:] if len(option_files) >= 5 else option_files

        all_greeks = []
        for f in sample_files:
            try:
                opt_df = pd.read_parquet(f)
                # Filter to ATM calls and puts
                if 'strike' in opt_df.columns and 'delta' in opt_df.columns:
                    atm = opt_df[opt_df['delta'].abs().between(0.40, 0.60)]
                    if len(atm) > 0:
                        all_greeks.append(atm[['delta', 'gamma', 'theta', 'vega',
                                                'implied_volatility', 'bid', 'ask']].describe())
            except Exception:
                pass

        if all_greeks:
            combined = pd.concat(all_greeks)
            report += "**Typical ATM Options Greeks (recent snapshots):**\n\n"
            headers = ['Greek', 'Mean', 'Median', 'Min', 'Max']
            for greek in ['delta', 'gamma', 'theta', 'vega', 'implied_volatility']:
                if greek in combined.columns:
                    vals = combined.loc['mean', greek] if 'mean' in combined.index else np.nan
                    # Handle case where loc returns a Series (multiple 'mean' rows)
                    if isinstance(vals, pd.Series):
                        vals = vals.mean()
                    if pd.notna(vals):
                        report += f"- **{greek}**: mean={vals:.4f}\n"
            report += '\n'

            # Bid-ask spread analysis
            if 'bid' in combined.columns and 'ask' in combined.columns:
                report += "**Typical Bid-Ask Spreads:**\n\n"
                # This is approximate
                report += "See options chain data for exact spreads.\n\n"
    else:
        report += "*No options chain data available for this ticker. Using theoretical estimates.*\n\n"

    # Theoretical translation
    report += md_header("Theoretical Options P/L Translation", 3)
    report += "\nEstimated options returns using standard delta/theta assumptions.\n\n"

    scenarios = [
        ('+15 bps', 0.0015, 18),
        ('+20 bps', 0.0020, 18),
        ('+30 bps', 0.0030, 18),
        ('+40 bps', 0.0040, 18),
        ('-10 bps', -0.0010, 18),
        ('-15 bps', -0.0015, 18),
        ('-20 bps', -0.0020, 18),
    ]

    headers = ['Underlying Move', 'ATM 0DTE (~50 delta)', 'OTM 0DTE (~25 delta)',
               'ATM Weekly (~50 delta)', 'After Spread Cost']
    rows = []

    for label, move, hold_min in scenarios:
        # ATM 0DTE: ~5x leverage, high theta
        atm_0dte = move * 5 * 100  # rough %
        theta_cost_0dte = 0.002 * (hold_min / 60)  # rough theta decay for 0DTE
        atm_0dte_net = (move * 5 - theta_cost_0dte) * 100

        # OTM 0DTE: ~10x leverage, even higher theta
        otm_0dte = move * 10 * 100
        otm_0dte_net = (move * 10 - theta_cost_0dte * 2) * 100

        # ATM Weekly: ~3x leverage, lower theta
        atm_weekly = move * 3 * 100
        theta_cost_weekly = 0.0005 * (hold_min / 60)
        atm_weekly_net = (move * 3 - theta_cost_weekly) * 100

        # After bid-ask spread (estimate $0.05 / $3.00 option = 1.7%)
        spread_cost = 1.7

        rows.append([
            label,
            f"{atm_0dte:.1f}%",
            f"{otm_0dte:.1f}%",
            f"{atm_weekly:.1f}%",
            f"~{spread_cost:.1f}% cost",
        ])

    report += md_table(headers, rows) + '\n'

    # Break-even analysis
    report += md_header("Break-Even Analysis", 3)
    report += "\nMinimum underlying move to be profitable after costs:\n\n"
    report += "- ATM 0DTE: ~3 bps underlying (spread + theta)\n"
    report += "- OTM 0DTE: ~5 bps underlying (wider spread + theta)\n"
    report += "- ATM Weekly: ~2 bps underlying (smaller spread + theta)\n\n"

    report += "> **Key Insight**: Setups with < 5 bps average return may be unprofitable\n"
    report += "> when traded with actual options due to spread and theta costs.\n\n"

    return report


# ---------------------------------------------------------------------------
# 5G. Walk-Forward Validation
# ---------------------------------------------------------------------------

def run_walk_forward(ticker: str, df: pd.DataFrame) -> str:
    """Walk-forward validation of key patterns."""
    report = md_header(f"5G. Walk-Forward Validation — {ticker}", 2)
    report += "\nTesting pattern stability over rolling windows.\n\n"

    close = df['Close'] if 'Close' in df.columns else df['Last']
    labels = df['strat_type'] if 'strat_type' in df.columns else classify_strat_series(df)
    next_return = close.pct_change().shift(-1) * 10000
    next_label = labels.shift(-1)

    # Split into 6-month windows
    dates = pd.to_datetime(df.index)
    start = dates.min()
    end = dates.max()

    windows = []
    current = start
    while current < end:
        window_end = current + pd.DateOffset(months=6)
        if window_end > end:
            window_end = end
        windows.append((current, window_end))
        current = window_end

    if len(windows) < 3:
        return report + "Insufficient data for walk-forward (need 18+ months).\n\n"

    # Test key patterns across windows
    patterns = [
        ('2U continuation', lambda l: (l.shift(1) == '2U') & (l == '2U'), '2U'),
        ('2D continuation', lambda l: (l.shift(1) == '2D') & (l == '2D'), '2D'),
        ('2D-1-2U reversal', lambda l: (l.shift(2) == '2D') & (l.shift(1) == '1') & (l == '2U'), '2U'),
        ('2U-1-2D reversal', lambda l: (l.shift(2) == '2U') & (l.shift(1) == '1') & (l == '2D'), '2D'),
    ]

    for pattern_name, pattern_fn, expected_next in patterns:
        report += md_header(f"Pattern: {pattern_name}", 3)

        headers = ['Window', 'Period', 'Occurrences', 'Next={} Rate'.format(expected_next),
                   'Avg Fwd Return (bps)', 'Stable?']
        rows = []
        window_rates = []

        for i, (w_start, w_end) in enumerate(windows):
            mask_window = (dates >= w_start) & (dates < w_end)
            window_labels = labels[mask_window]
            window_returns = next_return[mask_window]
            window_next = next_label[mask_window]

            pattern_mask = pattern_fn(window_labels)
            n = pattern_mask.sum()
            if n < 10:
                continue

            rate = (pattern_mask & (window_next == expected_next)).sum() / n
            avg_ret = window_returns[pattern_mask].mean()
            window_rates.append(rate)

            rows.append([
                f"Window {i+1}",
                f"{w_start.strftime('%Y-%m')}-{w_end.strftime('%Y-%m')}",
                fmt_num(n),
                fmt_pct(rate * 100),
                fmt_bps(avg_ret),
                '',
            ])

        if rows:
            # Stability check
            if window_rates:
                std_rate = np.std(window_rates)
                mean_rate = np.mean(window_rates)
                cv = std_rate / mean_rate if mean_rate > 0 else float('inf')

                stable = cv < 0.3
                for row in rows:
                    row[-1] = 'Yes' if stable else 'No'

                report += md_table(headers, rows) + '\n'
                report += f"Coefficient of variation: {cv:.2f} "
                report += f"({'STABLE' if stable else 'UNSTABLE - possible overfit'})\n"
                report += f"Mean rate: {fmt_pct(mean_rate * 100)}, Std: {fmt_pct(std_rate * 100)}\n\n"
            else:
                report += "Insufficient data for stability assessment.\n\n"
        else:
            report += "Pattern not found in any window.\n\n"

    return report


# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------

def run_phase5(tickers: list = None):
    """Run full Phase 5 analysis."""
    if tickers is None:
        tickers = TICKERS

    all_data = {}

    for ticker in tickers:
        progress(f"Starting Phase 5 analysis", ticker)

        # Load and enrich
        progress("Loading and enriching 1m data...", ticker)
        df_1m = load_ticker_1m(ticker)
        if df_1m.empty:
            progress("No data, skipping.", ticker)
            continue

        df = enrich_with_indicators(df_1m)
        progress(f"Enriched {len(df):,} bars", ticker)
        all_data[ticker] = df

        # Build report
        report = md_header(f"Phase 5: Additional Dimensions — {ticker}", 1)
        report += f"\nGenerated: {timestamp_str()}\n"
        report += f"Data: {df.index.min()} to {df.index.max()} ({len(df):,} bars)\n\n"

        # 5A: Regime
        progress("Analyzing market regimes...", ticker)
        report += analyze_regimes(ticker, df)

        # 5B: Time of day
        progress("Analyzing time-of-day patterns...", ticker)
        report += analyze_time_of_day(ticker, df)

        # 5C: Day of week
        progress("Analyzing day-of-week patterns...", ticker)
        report += analyze_day_of_week(ticker, df)

        # 5E: Drawdowns
        progress("Analyzing drawdowns and streaks...", ticker)
        report += analyze_drawdowns(ticker, df)

        # 5F: Options translation
        progress("Analyzing options P/L translation...", ticker)
        report += analyze_options_translation(ticker, df)

        # 5G: Walk-forward
        progress("Running walk-forward validation...", ticker)
        report += run_walk_forward(ticker, df)

        save_report(report, f'phase5_dimensions_{ticker.lower()}.md')
        progress("Phase 5 (per-ticker) complete!", ticker)

    # 5D: Cross-ticker (needs all data)
    if len(all_data) >= 2:
        progress("Analyzing cross-ticker correlations...")
        cross_report = md_header("Phase 5D: Cross-Ticker Correlation & Confirmation", 1)
        cross_report += f"\nGenerated: {timestamp_str()}\n\n"
        cross_report += analyze_cross_ticker(all_data)
        save_report(cross_report, 'phase5d_cross_ticker.md')
        progress("Phase 5D (cross-ticker) complete!")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Phase 5: Additional Dimensions')
    parser.add_argument('--tickers', nargs='+', default=TICKERS)
    args = parser.parse_args()
    run_phase5(tickers=args.tickers)
