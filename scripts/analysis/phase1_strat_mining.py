#!/usr/bin/env python3
"""
Phase 1: Strat Pattern Mining — Per-Ticker Transition Matrices & Sequence Analysis

Produces per-ticker:
  1A. Two-bar transition matrices (4 types x 6 timeframes)
  1B. Three-bar sequence probabilities
  1C. Consecutive move reversal analysis
  1D. Multi-timeframe Strat alignment statistics

Output: reports/phase1_strat_mining_{ticker}.md + CSV data files
"""

import sys
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict
from itertools import product as iter_product
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.analysis.shared_utils import (
    TICKERS, STRAT_TYPES, TIMEFRAMES, REPORTS_DIR, DATA_DIR, PROJECT_ROOT,
    load_ticker_1m, resample_to_timeframe, classify_strat_series,
    build_multi_timeframe_dict, enrich_with_indicators, split_by_period,
    calculate_forward_returns, calculate_mfe_mae, filter_rth,
    md_header, md_table, fmt_pct, fmt_bps, fmt_num, save_report,
    timestamp_str, confidence_interval_95, sample_size_label, progress,
)


# ---------------------------------------------------------------------------
# 1A. Two-Bar Transition Matrix
# ---------------------------------------------------------------------------

def compute_transition_matrix(labels: pd.Series) -> pd.DataFrame:
    """Compute the two-bar transition probability matrix.

    Returns DataFrame with rows = current type, cols = next type,
    values = probability (0-1).
    """
    transitions = defaultdict(lambda: defaultdict(int))
    total_per_type = defaultdict(int)

    prev = None
    for label in labels:
        if label in STRAT_TYPES and prev in STRAT_TYPES:
            transitions[prev][label] += 1
            total_per_type[prev] += 1
        prev = label

    # Build matrix
    matrix = pd.DataFrame(0.0, index=STRAT_TYPES, columns=STRAT_TYPES)
    counts = pd.DataFrame(0, index=STRAT_TYPES, columns=STRAT_TYPES)

    for from_type in STRAT_TYPES:
        total = total_per_type[from_type]
        for to_type in STRAT_TYPES:
            count = transitions[from_type][to_type]
            counts.loc[from_type, to_type] = count
            if total > 0:
                matrix.loc[from_type, to_type] = count / total

    return matrix, counts


def compute_transition_returns(df: pd.DataFrame, labels: pd.Series,
                               close_col: str = 'Close') -> pd.DataFrame:
    """For each transition, compute average return of the NEXT bar in bps."""
    close = df[close_col] if close_col in df.columns else df['Close']
    returns = close.pct_change().shift(-1) * 10000  # next bar return in bps

    result = pd.DataFrame(0.0, index=STRAT_TYPES, columns=STRAT_TYPES)
    counts = pd.DataFrame(0, index=STRAT_TYPES, columns=STRAT_TYPES)

    prev_label = labels.shift(1)
    for from_type in STRAT_TYPES:
        for to_type in STRAT_TYPES:
            mask = (prev_label == from_type) & (labels == to_type)
            vals = returns[mask].dropna()
            if len(vals) > 0:
                result.loc[from_type, to_type] = vals.mean()
                counts.loc[from_type, to_type] = len(vals)

    return result, counts


def analyze_two_bar_transitions(ticker: str, tf_dict: Dict) -> str:
    """Generate 1A analysis for all timeframes."""
    report = md_header(f"1A. Two-Bar Transition Matrix — {ticker}", 2)
    report += f"\nFor each current bar type, probability of each next bar type.\n\n"

    all_matrices = {}
    all_counts = {}
    all_returns = {}

    for tf in TIMEFRAMES:
        if tf not in tf_dict or tf_dict[tf].empty:
            continue

        df_tf = tf_dict[tf]
        labels = classify_strat_series(df_tf)

        matrix, counts = compute_transition_matrix(labels)
        ret_matrix, ret_counts = compute_transition_returns(df_tf, labels)

        all_matrices[tf] = matrix
        all_counts[tf] = counts
        all_returns[tf] = ret_matrix

        report += md_header(f"{ticker} — {tf} Bars", 3)

        # Probability table
        report += "**Transition Probabilities:**\n\n"
        headers = ['Current \\ Next'] + STRAT_TYPES + ['Sample']
        rows = []
        for from_type in STRAT_TYPES:
            row = [f"**{from_type}**"]
            total = int(counts.loc[from_type].sum())
            for to_type in STRAT_TYPES:
                prob = matrix.loc[from_type, to_type]
                n = int(counts.loc[from_type, to_type])
                row.append(f"{prob:.1%} (n={n:,})")
            row.append(fmt_num(total))
            rows.append(row)
        report += md_table(headers, rows) + '\n'

        # Average return table
        report += "**Average Next-Bar Return (bps):**\n\n"
        headers = ['Current \\ Next'] + STRAT_TYPES
        rows = []
        for from_type in STRAT_TYPES:
            row = [f"**{from_type}**"]
            for to_type in STRAT_TYPES:
                ret = ret_matrix.loc[from_type, to_type]
                row.append(fmt_bps(ret))
            rows.append(row)
        report += md_table(headers, rows) + '\n'

    return report, all_matrices, all_counts, all_returns


# ---------------------------------------------------------------------------
# 1B. Three-Bar Sequence Probabilities
# ---------------------------------------------------------------------------

KEY_SEQUENCES = [
    ('2U', '2U'),    # Momentum continuation
    ('2D', '2D'),    # Downward momentum
    ('2U', '1'),     # Pause after up
    ('2D', '1'),     # Pause after down
    ('3', '1'),      # Expansion then compression
    ('2D', '2U'),    # Bullish reversal
    ('2U', '2D'),    # Bearish reversal
    ('1', '2U'),     # Inside bar bullish breakout
    ('1', '2D'),     # Inside bar bearish breakout
]

# Named pattern sequences (3-bar combos from the plan)
NAMED_PATTERNS = {
    '2U-2U-2U': ('2U', '2U', '2U'),  # Triple continuation
    '2U-2U-2D': ('2U', '2U', '2D'),  # Exhaustion reversal
    '2D-2D-2D': ('2D', '2D', '2D'),  # Triple bearish
    '2D-2D-2U': ('2D', '2D', '2U'),  # Downward exhaustion
    '2U-1-2U': ('2U', '1', '2U'),    # Bullish continuation
    '2U-1-2D': ('2U', '1', '2D'),    # Bearish reversal (2-1-2)
    '2D-1-2U': ('2D', '1', '2U'),    # Bullish reversal (2-1-2)
    '2D-1-2D': ('2D', '1', '2D'),    # Bearish continuation
    '3-1-2U': ('3', '1', '2U'),      # Expansion reversal bullish
    '3-1-2D': ('3', '1', '2D'),      # Expansion reversal bearish
}


def compute_three_bar_sequences(df: pd.DataFrame, labels: pd.Series,
                                 close_col: str = 'Close',
                                 fwd_periods: list = None) -> pd.DataFrame:
    """Compute probabilities and returns for all 3-bar sequences (vectorized)."""
    if fwd_periods is None:
        fwd_periods = [5, 10, 15, 30]

    close = df[close_col] if close_col in df.columns else df['Close']
    close_arr = close.values

    results = []

    # Shifted labels
    label_1 = labels.shift(2)  # 2 bars ago
    label_2 = labels.shift(1)  # 1 bar ago
    label_3 = labels           # current bar
    next_label = labels.shift(-1)

    # Pre-compute forward returns for all periods
    fwd_cache = {}
    for p in fwd_periods:
        fwd_cache[p] = close.pct_change(p).shift(-p) * 10000

    # Pre-compute MFE/MAE using rolling max/min (vectorized)
    # For MFE: max of future 30 bars' return
    # For MAE: min of future 30 bars' return
    mfe_30 = pd.Series(np.nan, index=df.index)
    mae_30 = pd.Series(np.nan, index=df.index)
    n_bars = len(close_arr)
    # Use vectorized rolling on reversed returns
    for horizon in [30]:
        # Build forward max/min using a loop over offsets (still vectorized per offset)
        fwd_max = pd.Series(-np.inf, index=df.index)
        fwd_min = pd.Series(np.inf, index=df.index)
        for offset in range(1, min(horizon + 1, n_bars)):
            fwd_price = close.shift(-offset)
            fwd_ret = (fwd_price - close) / close * 10000
            fwd_max = fwd_max.clip(lower=fwd_ret)
            fwd_min = fwd_min.clip(upper=fwd_ret)
        # Replace inf values
        fwd_max[fwd_max == -np.inf] = np.nan
        fwd_min[fwd_min == np.inf] = np.nan
        mfe_30 = fwd_max
        mae_30 = fwd_min

    for name, (b1, b2, b3) in NAMED_PATTERNS.items():
        mask = (label_1 == b1) & (label_2 == b2) & (label_3 == b3)
        n = mask.sum()

        if n == 0:
            results.append({'pattern': name, 'count': 0})
            continue

        row = {'pattern': name, 'count': int(n)}

        # Next bar probabilities
        for next_type in STRAT_TYPES:
            next_mask = mask & (next_label == next_type)
            n_next = next_mask.sum()
            row[f'next_{next_type}_pct'] = n_next / n if n > 0 else 0
            row[f'next_{next_type}_n'] = int(n_next)

        # Forward returns
        for p in fwd_periods:
            vals = fwd_cache[p][mask].dropna()
            row[f'fwd_{p}_mean_bps'] = vals.mean() if len(vals) > 0 else np.nan
            row[f'fwd_{p}_median_bps'] = vals.median() if len(vals) > 0 else np.nan

        # MFE/MAE (vectorized)
        mfe_vals = mfe_30[mask].dropna()
        mae_vals = mae_30[mask].dropna()
        row['mfe_30_bps'] = mfe_vals.mean() if len(mfe_vals) > 0 else np.nan
        row['mae_30_bps'] = mae_vals.mean() if len(mae_vals) > 0 else np.nan

        results.append(row)

    return pd.DataFrame(results)


def analyze_three_bar_sequences(ticker: str, tf_dict: Dict) -> str:
    """Generate 1B analysis."""
    report = md_header(f"1B. Three-Bar Sequence Probabilities — {ticker}", 2)
    report += "\nKey Strat sequences and what follows.\n\n"

    for tf in ['1m', '5m', '15m', '30m']:
        if tf not in tf_dict or tf_dict[tf].empty:
            continue

        df_tf = tf_dict[tf]
        labels = classify_strat_series(df_tf)
        seq_df = compute_three_bar_sequences(df_tf, labels)

        if seq_df.empty:
            continue

        report += md_header(f"{ticker} — {tf}", 3)

        # Main table
        headers = ['Pattern', 'Count', 'Next 1', 'Next 2U', 'Next 2D', 'Next 3',
                    'Fwd 5 bps', 'Fwd 15 bps', 'MFE 30', 'MAE 30']
        rows = []
        for _, r in seq_df.iterrows():
            if r['count'] == 0:
                continue
            rows.append([
                f"**{r['pattern']}**",
                fmt_num(r['count']),
                fmt_pct(r.get('next_1_pct', 0) * 100),
                fmt_pct(r.get('next_2U_pct', 0) * 100),
                fmt_pct(r.get('next_2D_pct', 0) * 100),
                fmt_pct(r.get('next_3_pct', 0) * 100),
                fmt_bps(r.get('fwd_5_mean_bps', 0)),
                fmt_bps(r.get('fwd_15_mean_bps', 0)),
                fmt_bps(r.get('mfe_30_bps', 0)),
                fmt_bps(r.get('mae_30_bps', 0)),
            ])
        report += md_table(headers, rows) + '\n'

    return report


# ---------------------------------------------------------------------------
# 1C. Consecutive Move Analysis
# ---------------------------------------------------------------------------

def analyze_consecutive_moves(ticker: str, tf_dict: Dict, max_consec: int = 7) -> str:
    """Analyze reversal probability after N consecutive same-direction bars."""
    report = md_header(f"1C. Consecutive Move Analysis — {ticker}", 2)
    report += "\nReversal probability after N consecutive same-direction Strat bars.\n\n"

    for tf in ['1m', '5m', '15m']:
        if tf not in tf_dict or tf_dict[tf].empty:
            continue

        df_tf = tf_dict[tf]
        labels = classify_strat_series(df_tf)
        close = df_tf['Close'] if 'Close' in df_tf.columns else df_tf['Last']

        report += md_header(f"{ticker} — {tf}", 3)

        for direction, reversal, dir_label in [
            ('2D', '2U', 'Bearish (2D)'),
            ('2U', '2D', 'Bullish (2U)'),
        ]:
            report += f"\n**Consecutive {dir_label} bars → reversal probability:**\n\n"

            headers = ['Consecutive', 'Total', 'Reversal Prob', 'Avg Bounce (bps)',
                        'Median Bounce', 'Continuation Prob', 'Confidence']
            rows = []

            # Vectorized consecutive count using cumsum trick
            is_dir = (labels == direction)
            # Group consecutive runs: each time is_dir changes, increment group
            groups = (~is_dir).cumsum()
            # Within each group of True values, compute cumulative position
            consec_count = is_dir.groupby(groups).cumsum().astype(int)

            next_labels = labels.shift(-1)
            # Pre-compute 5-bar forward max/min for bounce calculation
            fwd_max_5 = close.rolling(5).max().shift(-5)
            fwd_min_5 = close.rolling(5).min().shift(-5)

            for n in range(2, max_consec + 1):
                # Bars where consecutive count just reached n
                ge_mask = (consec_count == n) & is_dir
                ge_idx = df_tf.index[ge_mask]
                total = len(ge_idx)

                if total < 5:
                    rows.append([f">={n}", fmt_num(total), 'N/A', 'N/A', 'N/A', 'N/A', 'Low'])
                    continue

                # Next bar analysis
                next_at_ge = next_labels[ge_mask]
                reversal_count = (next_at_ge == reversal).sum()
                cont_count = (next_at_ge == direction).sum()

                # Bounce calculation (vectorized)
                entry_prices = close[ge_mask]
                if direction == '2D':
                    bounce_vals = (fwd_max_5[ge_mask] - entry_prices) / entry_prices * 10000
                else:
                    bounce_vals = (entry_prices - fwd_min_5[ge_mask]) / entry_prices * 10000

                bounce_clean = bounce_vals.dropna()
                rev_prob = reversal_count / total if total > 0 else 0
                cont_prob = cont_count / total if total > 0 else 0
                avg_bounce = bounce_clean.mean() if len(bounce_clean) > 0 else 0
                med_bounce = bounce_clean.median() if len(bounce_clean) > 0 else 0

                rows.append([
                    f">={n}",
                    fmt_num(total),
                    fmt_pct(rev_prob * 100),
                    fmt_bps(avg_bounce),
                    fmt_bps(med_bounce),
                    fmt_pct(cont_prob * 100),
                    sample_size_label(total),
                ])

            report += md_table(headers, rows) + '\n'

    return report


# ---------------------------------------------------------------------------
# 1D. Multi-Timeframe Strat Alignment
# ---------------------------------------------------------------------------

def analyze_mtf_alignment(ticker: str, tf_dict: Dict) -> str:
    """Analyze what happens when higher timeframes align vs. conflict."""
    report = md_header(f"1D. Multi-Timeframe Strat Alignment — {ticker}", 2)
    report += "\nWhen higher timeframes agree vs. conflict.\n\n"

    if '1m' not in tf_dict or tf_dict['1m'].empty:
        return report + "No 1m data available.\n"

    df_1m = tf_dict['1m']
    labels_1m = classify_strat_series(df_1m)

    # Build higher-TF label series aligned to 1m index
    htf_labels = {}
    for tf in ['15m', '1h', 'D']:
        if tf not in tf_dict or tf_dict[tf].empty:
            continue
        df_tf = tf_dict[tf]
        tf_labels = classify_strat_series(df_tf)
        # Map to 1m index using forward-fill (use completed bar only)
        tf_numeric = tf_labels.map({'2U': 1, '2D': -1, '1': 0, '3': 0, 'X': 0}).fillna(0)
        aligned = tf_numeric.shift(1).reindex(df_1m.index).ffill().fillna(0)
        htf_labels[tf] = aligned

    if len(htf_labels) < 2:
        return report + "Insufficient higher-TF data.\n"

    close = df_1m['Close'] if 'Close' in df_1m.columns else df_1m['Last']

    # Alignment categories
    report += md_header("Alignment Scenarios", 3)

    scenarios = {
        'All Bullish': lambda: all(htf_labels[tf] > 0 for tf in htf_labels if tf in htf_labels),
        'All Bearish': lambda: all(htf_labels[tf] < 0 for tf in htf_labels if tf in htf_labels),
        'Mixed': lambda: not all(htf_labels[tf] > 0 for tf in htf_labels if tf in htf_labels) and
                         not all(htf_labels[tf] < 0 for tf in htf_labels if tf in htf_labels),
    }

    # Build alignment series
    alignment = pd.Series('Mixed', index=df_1m.index)
    if '15m' in htf_labels and '1h' in htf_labels and 'D' in htf_labels:
        all_bull = (htf_labels['15m'] > 0) & (htf_labels['1h'] > 0) & (htf_labels['D'] > 0)
        all_bear = (htf_labels['15m'] < 0) & (htf_labels['1h'] < 0) & (htf_labels['D'] < 0)
        alignment[all_bull] = 'All Bullish'
        alignment[all_bear] = 'All Bearish'

    fwd_1 = close.pct_change(1).shift(-1) * 10000
    fwd_5 = close.pct_change(5).shift(-5) * 10000
    fwd_15 = close.pct_change(15).shift(-15) * 10000

    headers = ['Alignment', 'Count', '% of Bars', 'Next 1 Bar (bps)',
               'Next 5 Bars (bps)', 'Next 15 Bars (bps)',
               '1m 2U Prob', '1m 2D Prob']
    rows = []

    for scenario_name in ['All Bullish', 'All Bearish', 'Mixed']:
        mask = alignment == scenario_name
        n = mask.sum()
        if n == 0:
            continue

        pct_bars = n / len(df_1m) * 100
        avg_1 = fwd_1[mask].mean()
        avg_5 = fwd_5[mask].mean()
        avg_15 = fwd_15[mask].mean()

        # 1m type probabilities when in this alignment
        labels_in_scenario = labels_1m[mask]
        prob_2u = (labels_in_scenario == '2U').mean() * 100
        prob_2d = (labels_in_scenario == '2D').mean() * 100

        rows.append([
            f"**{scenario_name}**",
            fmt_num(n),
            fmt_pct(pct_bars),
            fmt_bps(avg_1),
            fmt_bps(avg_5),
            fmt_bps(avg_15),
            fmt_pct(prob_2u),
            fmt_pct(prob_2d),
        ])

    report += md_table(headers, rows) + '\n'

    # Specific alignment combinations
    report += md_header("Specific HTF Combinations", 3)

    if 'D' in htf_labels and '1h' in htf_labels and '15m' in htf_labels:
        combos = [
            ('D 2U + 1h 2U + 15m 2U', (1, 1, 1)),
            ('D 2U + 1h 2U + 15m 2D', (1, 1, -1)),
            ('D 2U + 1h 2D + 15m 2U', (1, -1, 1)),
            ('D 2D + 1h 2D + 15m 2D', (-1, -1, -1)),
            ('D 2D + 1h 2D + 15m 2U', (-1, -1, 1)),
            ('D 2D + 1h 2U + 15m 2D', (-1, 1, -1)),
        ]

        headers = ['Combination', 'Count', '1m Next Return (bps)',
                   '1m 2U Follows', '1m 2D Follows', 'Net Direction']
        rows = []

        for label, (d_dir, h_dir, m15_dir) in combos:
            mask = ((htf_labels['D'] == d_dir) &
                    (htf_labels['1h'] == h_dir) &
                    (htf_labels['15m'] == m15_dir))
            n = mask.sum()
            if n < 30:
                rows.append([label, fmt_num(n), 'N/A (low n)', 'N/A', 'N/A', 'N/A'])
                continue

            avg_ret = fwd_1[mask].mean()
            scenario_labels = labels_1m[mask]
            p_2u = (scenario_labels == '2U').mean() * 100
            p_2d = (scenario_labels == '2D').mean() * 100
            net = 'Bullish' if p_2u > p_2d + 5 else ('Bearish' if p_2d > p_2u + 5 else 'Neutral')

            rows.append([
                label, fmt_num(n), fmt_bps(avg_ret),
                fmt_pct(p_2u), fmt_pct(p_2d), net,
            ])

        report += md_table(headers, rows) + '\n'

    return report


# ---------------------------------------------------------------------------
# Cross-Ticker Comparison Section
# ---------------------------------------------------------------------------

def generate_cross_ticker_comparison(all_matrices: Dict, all_counts: Dict) -> str:
    """Side-by-side comparison highlighting where tickers diverge most."""
    report = md_header("Cross-Ticker Divergence Analysis", 2)
    report += "\nHighlighting transitions where tickers behave most differently.\n\n"

    # Focus on 1m timeframe for comparison
    tf = '1m'
    if not all(ticker in all_matrices and tf in all_matrices[ticker]
               for ticker in TICKERS):
        return report + "Insufficient data for cross-ticker comparison.\n"

    headers = ['Transition'] + [f'{t} Prob' for t in TICKERS] + ['Max Divergence']
    rows = []

    for from_type in STRAT_TYPES:
        for to_type in STRAT_TYPES:
            probs = []
            for ticker in TICKERS:
                p = all_matrices[ticker][tf].loc[from_type, to_type]
                probs.append(p)

            divergence = max(probs) - min(probs)
            row = [f"{from_type} → {to_type}"]
            for i, ticker in enumerate(TICKERS):
                row.append(fmt_pct(probs[i] * 100))
            row.append(fmt_pct(divergence * 100))
            rows.append((divergence, row))

    # Sort by divergence (highest first)
    rows.sort(key=lambda x: x[0], reverse=True)
    report += md_table(headers, [r[1] for r in rows]) + '\n'

    return report


# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------

def run_phase1(tickers: list = None, save_csv: bool = True):
    """Run full Phase 1 analysis for all tickers."""
    if tickers is None:
        tickers = TICKERS

    all_matrices = {}
    all_counts = {}
    all_returns = {}
    all_reports = {}

    for ticker in tickers:
        progress(f"Starting Phase 1 analysis", ticker)

        # Load data
        progress("Loading 1m data...", ticker)
        df_1m = load_ticker_1m(ticker)
        if df_1m.empty:
            progress("No data found, skipping.", ticker)
            continue

        progress(f"Loaded {len(df_1m):,} bars ({df_1m.index.min()} to {df_1m.index.max()})", ticker)

        # Build multi-timeframe dict
        progress("Building multi-timeframe data...", ticker)
        tf_dict = build_multi_timeframe_dict(df_1m)
        for tf, df_tf in tf_dict.items():
            progress(f"  {tf}: {len(df_tf):,} bars", ticker)

        # Split into full and recent periods
        full_dict = tf_dict
        # For recent period analysis (last 3 years)
        _, recent_1m = split_by_period(df_1m, recent_years=3)
        recent_dict = build_multi_timeframe_dict(recent_1m) if not recent_1m.empty else {}

        # === Build report ===
        report = md_header(f"Phase 1: Strat Pattern Mining — {ticker}", 1)
        report += f"\nGenerated: {timestamp_str()}\n"
        report += f"Data range: {df_1m.index.min()} to {df_1m.index.max()}\n"
        report += f"Total 1m bars: {len(df_1m):,}\n\n"

        # 1A. Two-Bar Transitions
        progress("Computing two-bar transitions...", ticker)
        section_1a, matrices, counts, returns = analyze_two_bar_transitions(ticker, full_dict)
        report += section_1a
        all_matrices[ticker] = matrices
        all_counts[ticker] = counts
        all_returns[ticker] = returns

        # Recent period comparison
        if recent_dict:
            report += md_header(f"1A (Recent 3 Years) — {ticker}", 3)
            recent_1a, _, _, _ = analyze_two_bar_transitions(f"{ticker} Recent", recent_dict)
            report += recent_1a

        # 1B. Three-Bar Sequences
        progress("Computing three-bar sequences...", ticker)
        report += analyze_three_bar_sequences(ticker, full_dict)

        # 1C. Consecutive Moves
        progress("Computing consecutive move analysis...", ticker)
        report += analyze_consecutive_moves(ticker, full_dict)

        # 1D. Multi-Timeframe Alignment
        progress("Computing MTF alignment...", ticker)
        report += analyze_mtf_alignment(ticker, full_dict)

        # Save individual ticker report
        save_report(report, f'phase1_strat_mining_{ticker.lower()}.md')
        all_reports[ticker] = report

        # Save CSV data
        if save_csv:
            csv_dir = REPORTS_DIR / 'data'
            csv_dir.mkdir(parents=True, exist_ok=True)

            for tf, matrix in matrices.items():
                matrix.to_csv(csv_dir / f'transition_matrix_{ticker.lower()}_{tf}.csv')

        progress("Phase 1 complete!", ticker)

    # Cross-ticker comparison
    if len(all_matrices) >= 2:
        progress("Generating cross-ticker comparison...")
        comparison = generate_cross_ticker_comparison(all_matrices, all_counts)

        # Combined report
        combined = md_header("Phase 1: Strat Pattern Mining — Cross-Ticker Comparison", 1)
        combined += f"\nGenerated: {timestamp_str()}\n\n"
        combined += comparison

        # Add key divergences for each transition
        combined += md_header("Per-Ticker Summaries", 2)
        for ticker in tickers:
            if ticker in all_reports:
                combined += f"\n---\n\n"
                combined += all_reports[ticker]

        save_report(combined, 'phase1_strat_mining_combined.md')

    return all_matrices, all_counts, all_returns


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Phase 1: Strat Pattern Mining')
    parser.add_argument('--tickers', nargs='+', default=TICKERS,
                        help='Tickers to analyze')
    args = parser.parse_args()

    run_phase1(tickers=args.tickers)
