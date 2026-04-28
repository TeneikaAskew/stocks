#!/usr/bin/env python3
"""
Phase 2: Indicator Confirmation — Per-Ticker Strat + Indicator Cross-Tabs

Produces per-ticker:
  2A. Strat + Indicator cross-tabs (continuation vs reversal by indicator state)
  2B. Indicator predictive power ranking (lift over base rate)
  2C. Reversal early warning scorecard (weighted checklist)

Output: reports/phase2_indicator_confirmation_{ticker}.md
"""

import sys
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.analysis.shared_utils import (
    TICKERS, STRAT_TYPES, TIMEFRAMES, REPORTS_DIR,
    load_ticker_1m, resample_to_timeframe, classify_strat_series,
    build_multi_timeframe_dict, enrich_with_indicators, filter_rth,
    md_header, md_table, fmt_pct, fmt_bps, fmt_num, save_report,
    timestamp_str, confidence_interval_95, sample_size_label, progress,
    IndicatorConfig,
)


# ---------------------------------------------------------------------------
# Indicator condition definitions
# ---------------------------------------------------------------------------

def define_indicator_conditions(df: pd.DataFrame, ind: IndicatorConfig = None) -> Dict[str, pd.Series]:
    """Define all binary indicator conditions for cross-tab analysis."""
    if ind is None:
        ind = IndicatorConfig()

    conditions = {}
    close = df['Close'] if 'Close' in df.columns else df['Last']

    # RSI buckets
    rsi = df.get(ind.rsi_col, pd.Series(50.0, index=df.index))
    conditions['RSI < 30'] = rsi < 30
    conditions['RSI 30-40'] = (rsi >= 30) & (rsi < 40)
    conditions['RSI 40-50'] = (rsi >= 40) & (rsi < 50)
    conditions['RSI 50-60'] = (rsi >= 50) & (rsi < 60)
    conditions['RSI 60-70'] = (rsi >= 60) & (rsi < 70)
    conditions['RSI > 70'] = rsi > 70

    # VWAP
    if 'Price_vs_VWAP' in df.columns:
        conditions['Price > VWAP'] = df['Price_vs_VWAP'] > 0
        conditions['Price < VWAP'] = df['Price_vs_VWAP'] < 0

    # EMA relationships
    ema_fast = ind.ema_fast_period
    ema_mid = ind.ema_mid_period
    if f'EMA{ema_fast}' in df.columns:
        conditions[f'Price > EMA{ema_fast}'] = close > df[f'EMA{ema_fast}']
        conditions[f'Price < EMA{ema_fast}'] = close <= df[f'EMA{ema_fast}']
    if f'EMA{ema_mid}' in df.columns:
        conditions[f'Price > EMA{ema_mid}'] = close > df[f'EMA{ema_mid}']
        conditions[f'Price < EMA{ema_mid}'] = close <= df[f'EMA{ema_mid}']
    if f'EMA{ema_fast}' in df.columns and f'EMA{ema_mid}' in df.columns:
        conditions['EMA9 > EMA20 (bullish)'] = df[f'EMA{ema_fast}'] > df[f'EMA{ema_mid}']
        conditions['EMA9 < EMA20 (bearish)'] = df[f'EMA{ema_fast}'] <= df[f'EMA{ema_mid}']

    # Order Block
    if 'Order_Block_Position' in df.columns:
        conditions['Above Order Block'] = df['Order_Block_Position'] == 1
        conditions['Within Order Block'] = df['Order_Block_Position'] == 0
        conditions['Below Order Block'] = df['Order_Block_Position'] == -1
    if 'Order_Block_Test' in df.columns:
        conditions['Order Block Test'] = df['Order_Block_Test'] == 1

    # ORB
    for orb_label in ['5m', '15m', '30m']:
        trend_col = f'ORB_{orb_label}_Trend'
        broke_high = f'ORB_{orb_label}_Broke_High'
        broke_low = f'ORB_{orb_label}_Broke_Low'
        within = f'ORB_{orb_label}_Within_Range'
        if trend_col in df.columns:
            conditions[f'ORB {orb_label} Bullish'] = df[trend_col] == 1
            conditions[f'ORB {orb_label} Bearish'] = df[trend_col] == -1
            conditions[f'ORB {orb_label} Within'] = df.get(within, pd.Series(0, index=df.index)) == 1

    # Historical levels
    if 'Broke_Prev_Day_High' in df.columns:
        conditions['Broke Prev Day High'] = df['Broke_Prev_Day_High'] == 1
        conditions['Broke Prev Day Low'] = df['Broke_Prev_Day_Low'] == 1
    if 'At_Prev_Day_High' in df.columns:
        conditions['At Prev Day High'] = df['At_Prev_Day_High'] == 1
        conditions['At Prev Day Low'] = df['At_Prev_Day_Low'] == 1
    if 'At_Prev_Week_High' in df.columns:
        conditions['At Prev Week High'] = df['At_Prev_Week_High'] == 1
    if 'At_Prev_Week_Low' in df.columns:
        conditions['At Prev Week Low'] = df['At_Prev_Week_Low'] == 1

    # RVOL
    if 'RVOL' in df.columns:
        conditions['RVOL > 1.5'] = df['RVOL'] > 1.5
        conditions['RVOL 0.8-1.5'] = (df['RVOL'] >= 0.8) & (df['RVOL'] <= 1.5)
        conditions['RVOL < 0.8'] = df['RVOL'] < 0.8

    # StochRSI
    if 'StochRSI_K' in df.columns:
        conditions['StochRSI Oversold (<20)'] = df['StochRSI_K'] < 20
        conditions['StochRSI Neutral'] = (df['StochRSI_K'] >= 20) & (df['StochRSI_K'] <= 80)
        conditions['StochRSI Overbought (>80)'] = df['StochRSI_K'] > 80

    # OBV
    if 'OBV_Slope' in df.columns:
        conditions['OBV Rising'] = df['OBV_Slope'] > 0
        conditions['OBV Falling'] = df['OBV_Slope'] <= 0

    # ATR
    atr_col = ind.atr_col
    if atr_col in df.columns:
        atr_avg = df[atr_col].rolling(50).mean()
        conditions['ATR > 1.5x avg'] = df[atr_col] > (atr_avg * 1.5)
        conditions['ATR normal'] = (df[atr_col] >= atr_avg * 0.5) & (df[atr_col] <= atr_avg * 1.5)
        conditions['ATR < 0.5x avg'] = df[atr_col] < (atr_avg * 0.5)

    return conditions


# ---------------------------------------------------------------------------
# 2A. Strat + Indicator Cross-Tabs
# ---------------------------------------------------------------------------

def compute_strat_indicator_crosstab(
    df: pd.DataFrame,
    labels: pd.Series,
    conditions: Dict[str, pd.Series],
    pattern_seq: Tuple[str, ...],
    min_samples: int = 20,
) -> pd.DataFrame:
    """For a given Strat sequence, compute continuation/reversal rates
    conditioned on each indicator state."""

    # Identify bars matching the pattern
    if len(pattern_seq) == 2:
        prev1 = labels.shift(1)
        mask = (prev1 == pattern_seq[0]) & (labels == pattern_seq[1])
    elif len(pattern_seq) == 3:
        prev2 = labels.shift(2)
        prev1 = labels.shift(1)
        mask = (prev2 == pattern_seq[0]) & (prev1 == pattern_seq[1]) & (labels == pattern_seq[2])
    else:
        return pd.DataFrame()

    next_label = labels.shift(-1)

    # Determine what "continuation" and "reversal" mean based on the last bar
    last_bar = pattern_seq[-1]
    if last_bar == '2U':
        continuation_type = '2U'
        reversal_type = '2D'
    elif last_bar == '2D':
        continuation_type = '2D'
        reversal_type = '2U'
    else:
        continuation_type = '2U'
        reversal_type = '2D'

    # Base rates (no condition)
    base_n = mask.sum()
    if base_n < min_samples:
        return pd.DataFrame()

    base_cont = (mask & (next_label == continuation_type)).sum()
    base_rev = (mask & (next_label == reversal_type)).sum()
    base_cont_rate = base_cont / base_n if base_n > 0 else 0
    base_rev_rate = base_rev / base_n if base_n > 0 else 0

    rows = []
    rows.append({
        'condition': '**ALL (base rate)**',
        'continuation_pct': base_cont_rate * 100,
        'reversal_pct': base_rev_rate * 100,
        'sample': base_n,
        'cont_lift': 0,
        'rev_lift': 0,
        'confidence': sample_size_label(base_n),
    })

    for cond_name, cond_mask in conditions.items():
        sub_mask = mask & cond_mask
        n = sub_mask.sum()
        if n < min_samples:
            continue

        cont_n = (sub_mask & (next_label == continuation_type)).sum()
        rev_n = (sub_mask & (next_label == reversal_type)).sum()
        cont_rate = cont_n / n if n > 0 else 0
        rev_rate = rev_n / n if n > 0 else 0

        cont_lift = (cont_rate - base_cont_rate) * 100  # percentage points
        rev_lift = (rev_rate - base_rev_rate) * 100

        rows.append({
            'condition': cond_name,
            'continuation_pct': cont_rate * 100,
            'reversal_pct': rev_rate * 100,
            'sample': n,
            'cont_lift': cont_lift,
            'rev_lift': rev_lift,
            'confidence': sample_size_label(n),
        })

    return pd.DataFrame(rows)


def analyze_crosstabs(ticker: str, df: pd.DataFrame, labels: pd.Series,
                      conditions: Dict[str, pd.Series]) -> str:
    """Generate 2A cross-tab analysis for key patterns."""
    report = md_header(f"2A. Strat + Indicator Cross-Tabs — {ticker}", 2)
    report += "\nFor each Strat pattern, how indicators change continuation vs reversal probability.\n\n"

    key_patterns = [
        (('2U', '2U'), '2U-2U (Bullish Momentum)'),
        (('2D', '2D'), '2D-2D (Bearish Momentum)'),
        (('2U', '1'), '2U-1 (Pause After Up)'),
        (('2D', '1'), '2D-1 (Pause After Down)'),
        (('2D', '1', '2U'), '2D-1-2U (Bullish Reversal)'),
        (('2U', '1', '2D'), '2U-1-2D (Bearish Reversal)'),
    ]

    for pattern, label in key_patterns:
        progress(f"  Cross-tab: {label}", ticker)
        ct = compute_strat_indicator_crosstab(df, labels, conditions, pattern)
        if ct.empty:
            report += f"\n**{label}**: Insufficient data (n < 20)\n\n"
            continue

        report += md_header(f"{ticker}: {label}", 3)

        # Sort by absolute lift (most impactful first)
        ct['abs_lift'] = ct['cont_lift'].abs() + ct['rev_lift'].abs()
        ct = ct.sort_values('abs_lift', ascending=False)

        headers = ['Condition', 'Continuation %', 'Reversal %', 'Sample',
                   'Cont Lift', 'Rev Lift', 'Confidence']
        rows = []
        for _, r in ct.iterrows():
            rows.append([
                r['condition'],
                fmt_pct(r['continuation_pct']),
                fmt_pct(r['reversal_pct']),
                fmt_num(r['sample']),
                f"{r['cont_lift']:+.1f}pp",
                f"{r['rev_lift']:+.1f}pp",
                r['confidence'],
            ])

        report += md_table(headers, rows) + '\n'

    return report


# ---------------------------------------------------------------------------
# 2B. Indicator Predictive Power Ranking
# ---------------------------------------------------------------------------

def analyze_predictive_power(ticker: str, df: pd.DataFrame, labels: pd.Series,
                             conditions: Dict[str, pd.Series]) -> str:
    """Rank indicators by how much they improve prediction for key patterns."""
    report = md_header(f"2B. Indicator Predictive Power Ranking — {ticker}", 2)
    report += "\nRanked by absolute lift in continuation or reversal prediction.\n\n"

    close = df['Close'] if 'Close' in df.columns else df['Last']
    next_label = labels.shift(-1)

    for direction, pattern_label in [
        ('continuation', 'Trend Continuation'),
        ('reversal', 'Reversal Detection'),
    ]:
        report += md_header(f"{ticker}: {pattern_label}", 3)

        # For continuation: after 2U, predict more 2U
        # For reversal: after 2U-2U, predict 2D
        if direction == 'continuation':
            mask = labels == '2U'
            target = next_label == '2U'
        else:
            prev = labels.shift(1)
            mask = (prev == '2U') & (labels == '2U')
            target = next_label == '2D'

        base_n = mask.sum()
        if base_n < 50:
            report += "Insufficient data.\n\n"
            continue

        base_rate = (mask & target).sum() / base_n

        lifts = []
        for cond_name, cond_mask in conditions.items():
            sub_mask = mask & cond_mask
            n = sub_mask.sum()
            if n < 30:
                continue
            rate = (sub_mask & target).sum() / n if n > 0 else 0
            lift = (rate - base_rate) * 100
            lifts.append({
                'indicator': cond_name,
                'rate': rate * 100,
                'base_rate': base_rate * 100,
                'lift_pp': lift,
                'sample': n,
            })

        if not lifts:
            report += "No indicators with sufficient sample size.\n\n"
            continue

        lifts_df = pd.DataFrame(lifts).sort_values('lift_pp', key=abs, ascending=False)

        headers = ['Rank', 'Indicator', f'{pattern_label} Rate', 'Base Rate',
                   'Lift (pp)', 'Sample', 'Signal']
        rows = []
        for rank, (_, r) in enumerate(lifts_df.head(20).iterrows(), 1):
            signal = 'Confirms' if r['lift_pp'] > 0 else 'Contradicts'
            rows.append([
                rank,
                r['indicator'],
                fmt_pct(r['rate']),
                fmt_pct(r['base_rate']),
                f"{r['lift_pp']:+.1f}pp",
                fmt_num(r['sample']),
                signal,
            ])

        report += md_table(headers, rows) + '\n'

        # Same for bearish direction
        report += md_header(f"{ticker}: {pattern_label} (Bearish)", 4)

        if direction == 'continuation':
            mask = labels == '2D'
            target = next_label == '2D'
        else:
            prev = labels.shift(1)
            mask = (prev == '2D') & (labels == '2D')
            target = next_label == '2U'

        base_n = mask.sum()
        if base_n < 50:
            report += "Insufficient data.\n\n"
            continue

        base_rate = (mask & target).sum() / base_n

        lifts = []
        for cond_name, cond_mask in conditions.items():
            sub_mask = mask & cond_mask
            n = sub_mask.sum()
            if n < 30:
                continue
            rate = (sub_mask & target).sum() / n if n > 0 else 0
            lift = (rate - base_rate) * 100
            lifts.append({
                'indicator': cond_name,
                'rate': rate * 100,
                'base_rate': base_rate * 100,
                'lift_pp': lift,
                'sample': n,
            })

        if not lifts:
            report += "No indicators with sufficient sample size.\n\n"
            continue

        lifts_df = pd.DataFrame(lifts).sort_values('lift_pp', key=abs, ascending=False)

        rows = []
        for rank, (_, r) in enumerate(lifts_df.head(20).iterrows(), 1):
            signal = 'Confirms' if r['lift_pp'] > 0 else 'Contradicts'
            rows.append([
                rank, r['indicator'], fmt_pct(r['rate']),
                fmt_pct(r['base_rate']), f"{r['lift_pp']:+.1f}pp",
                fmt_num(r['sample']), signal,
            ])

        report += md_table(headers, rows) + '\n'

    return report


# ---------------------------------------------------------------------------
# 2C. Reversal Early Warning Scorecard
# ---------------------------------------------------------------------------

def build_reversal_scorecard(ticker: str, df: pd.DataFrame, labels: pd.Series,
                              conditions: Dict[str, pd.Series]) -> str:
    """Build a weighted reversal warning scorecard based on indicator lifts."""
    report = md_header(f"2C. Reversal Early Warning Scorecard — {ticker}", 2)
    report += "\nWeighted checklist of conditions that predict reversals.\n\n"

    next_label = labels.shift(-1)
    close = df['Close'] if 'Close' in df.columns else df['Last']

    for direction, momentum_type, reversal_type, scenario_label in [
        ('bullish_reversal_warning', '2U', '2D', 'Bullish-to-Bearish (take profit on CALL)'),
        ('bearish_reversal_warning', '2D', '2U', 'Bearish-to-Bullish (take profit on PUT)'),
    ]:
        report += md_header(f"{ticker}: {scenario_label}", 3)

        # Base: after 2 consecutive momentum bars
        prev = labels.shift(1)
        mask = (prev == momentum_type) & (labels == momentum_type)
        target = next_label == reversal_type

        base_n = mask.sum()
        if base_n < 50:
            report += "Insufficient data for scorecard.\n\n"
            continue

        base_rate = (mask & target).sum() / base_n

        # Score each indicator by its lift
        scored = []
        for cond_name, cond_mask in conditions.items():
            sub_mask = mask & cond_mask
            n = sub_mask.sum()
            if n < 20:
                continue
            rate = (sub_mask & target).sum() / n if n > 0 else 0
            lift = rate - base_rate

            if lift > 0.02:  # Only include conditions that increase reversal probability
                # Weight proportional to lift and reliability
                weight = min(3, int(lift / 0.05) + 1)
                scored.append({
                    'condition': cond_name,
                    'reversal_rate': rate * 100,
                    'lift': lift * 100,
                    'weight': weight,
                    'sample': n,
                })

        if not scored:
            report += "No significant reversal warning indicators found.\n\n"
            continue

        scored_df = pd.DataFrame(scored).sort_values('lift', ascending=False)

        headers = ['Condition', 'Points', 'Rev Rate', 'Lift vs Base', 'Sample']
        rows = []
        for _, r in scored_df.head(15).iterrows():
            rows.append([
                r['condition'],
                f"+{r['weight']}",
                fmt_pct(r['reversal_rate']),
                f"+{r['lift']:.1f}pp",
                fmt_num(r['sample']),
            ])

        report += f"**Base reversal rate:** {fmt_pct(base_rate * 100)}\n\n"
        report += md_table(headers, rows) + '\n'

        # Scoring guide
        total_max = scored_df['weight'].sum() if len(scored_df) > 0 else 0
        report += f"\n**Scoring Guide:**\n"
        report += f"- Score 0-{int(total_max*0.3)}: Low reversal risk (stay in trade)\n"
        report += f"- Score {int(total_max*0.3)+1}-{int(total_max*0.6)}: Moderate risk (tighten stop)\n"
        report += f"- Score {int(total_max*0.6)+1}+: High risk (take profit)\n\n"

    return report


# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------

def run_phase2(tickers: list = None):
    """Run full Phase 2 analysis for all tickers."""
    if tickers is None:
        tickers = TICKERS

    for ticker in tickers:
        progress(f"Starting Phase 2 analysis", ticker)

        # Load and enrich data
        progress("Loading and enriching 1m data...", ticker)
        df_1m = load_ticker_1m(ticker)
        if df_1m.empty:
            progress("No data found, skipping.", ticker)
            continue

        progress(f"Loaded {len(df_1m):,} bars, adding indicators...", ticker)
        df = enrich_with_indicators(df_1m)
        labels = df['strat_candle'] if 'strat_candle' in df.columns else classify_strat_series(df)

        # Define conditions
        progress("Defining indicator conditions...", ticker)
        conditions = define_indicator_conditions(df)
        progress(f"  Defined {len(conditions)} indicator conditions", ticker)

        # Build report
        report = md_header(f"Phase 2: Indicator Confirmation — {ticker}", 1)
        report += f"\nGenerated: {timestamp_str()}\n"
        report += f"Data range: {df.index.min()} to {df.index.max()}\n"
        report += f"Total bars: {len(df):,}\n"
        report += f"Indicator conditions: {len(conditions)}\n\n"

        # 2A: Cross-tabs
        progress("Computing Strat + Indicator cross-tabs...", ticker)
        report += analyze_crosstabs(ticker, df, labels, conditions)

        # 2B: Predictive power ranking
        progress("Computing predictive power rankings...", ticker)
        report += analyze_predictive_power(ticker, df, labels, conditions)

        # 2C: Reversal scorecard
        progress("Building reversal scorecard...", ticker)
        report += build_reversal_scorecard(ticker, df, labels, conditions)

        save_report(report, f'phase2_indicator_confirmation_{ticker.lower()}.md')
        progress("Phase 2 complete!", ticker)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Phase 2: Indicator Confirmation')
    parser.add_argument('--tickers', nargs='+', default=TICKERS)
    args = parser.parse_args()
    run_phase2(tickers=args.tickers)
