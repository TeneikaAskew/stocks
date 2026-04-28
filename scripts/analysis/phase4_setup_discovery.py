#!/usr/bin/env python3
"""
Phase 4: High-Probability Setup Discovery — Per-Ticker Combinatorial Scan

Produces per-ticker:
  4A. Combinatorial feature scan (2-way and 3-way indicator combos)
  4B. Decision tree analysis (high-purity paths)
  4C. Per-ticker feature importance ranking
  4D. Sample size analysis and confidence thresholds

Output: reports/phase4_setup_discovery_{ticker}.md
"""

import sys
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from itertools import combinations
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.analysis.shared_utils import (
    TICKERS, REPORTS_DIR,
    load_ticker_1m, enrich_with_indicators, classify_strat_series,
    resample_to_timeframe,
    md_header, md_table, fmt_pct, fmt_bps, fmt_num, save_report,
    timestamp_str, sample_size_label, progress,
    IndicatorConfig,
)
from scripts.analysis.phase2_indicator_confirmation import define_indicator_conditions


# ---------------------------------------------------------------------------
# Feature definitions for combinatorial scan
# ---------------------------------------------------------------------------

def define_feature_groups(df: pd.DataFrame, labels: pd.Series,
                          ind: IndicatorConfig = None) -> Dict[str, Dict[str, pd.Series]]:
    """Define mutually exclusive feature groups for combinatorial scanning."""
    if ind is None:
        ind = IndicatorConfig()

    close = df['Close'] if 'Close' in df.columns else df['Last']
    groups = {}

    # RSI state
    rsi = df.get(ind.rsi_col, pd.Series(50.0, index=df.index))
    groups['RSI'] = {
        'RSI < 30': rsi < 30,
        'RSI 30-50': (rsi >= 30) & (rsi < 50),
        'RSI 50-70': (rsi >= 50) & (rsi < 70),
        'RSI > 70': rsi >= 70,
    }

    # VWAP position
    if 'Price_vs_VWAP' in df.columns:
        groups['VWAP'] = {
            'Above VWAP': df['Price_vs_VWAP'] > 0,
            'Below VWAP': df['Price_vs_VWAP'] <= 0,
        }

    # EMA position
    ema_fast = ind.ema_fast_period
    if f'EMA{ema_fast}' in df.columns:
        groups['EMA9'] = {
            f'Above EMA{ema_fast}': close > df[f'EMA{ema_fast}'],
            f'Below EMA{ema_fast}': close <= df[f'EMA{ema_fast}'],
        }

    ema_mid = ind.ema_mid_period
    if f'EMA{ema_mid}' in df.columns:
        groups['EMA20'] = {
            f'Above EMA{ema_mid}': close > df[f'EMA{ema_mid}'],
            f'Below EMA{ema_mid}': close <= df[f'EMA{ema_mid}'],
        }

    # EMA cross
    if 'EMA_Cross' in df.columns:
        groups['EMA_Cross'] = {
            'EMA9 > EMA20': df['EMA_Cross'] == 1,
            'EMA9 < EMA20': df['EMA_Cross'] == 0,
        }

    # ORB trend (30m)
    if 'ORB_30m_Trend' in df.columns:
        groups['ORB_30m'] = {
            'ORB Bullish': df['ORB_30m_Trend'] == 1,
            'ORB Bearish': df['ORB_30m_Trend'] == -1,
            'ORB Within': df.get('ORB_30m_Within_Range', pd.Series(0, index=df.index)) == 1,
        }

    # Historical levels
    if 'Broke_Prev_Day_High' in df.columns:
        groups['Prev_Day_Break'] = {
            'Broke Prev Day High': df['Broke_Prev_Day_High'] == 1,
            'Broke Prev Day Low': df['Broke_Prev_Day_Low'] == 1,
        }

    # RVOL
    if 'RVOL' in df.columns:
        groups['RVOL'] = {
            'RVOL > 1.5': df['RVOL'] > 1.5,
            'RVOL 0.8-1.5': (df['RVOL'] >= 0.8) & (df['RVOL'] <= 1.5),
            'RVOL < 0.8': df['RVOL'] < 0.8,
        }

    # StochRSI
    if 'StochRSI_K' in df.columns:
        groups['StochRSI'] = {
            'StochRSI Oversold': df['StochRSI_K'] < 20,
            'StochRSI Neutral': (df['StochRSI_K'] >= 20) & (df['StochRSI_K'] <= 80),
            'StochRSI Overbought': df['StochRSI_K'] > 80,
        }

    # OBV
    if 'OBV_Slope' in df.columns:
        groups['OBV'] = {
            'OBV Rising': df['OBV_Slope'] > 0,
            'OBV Falling': df['OBV_Slope'] <= 0,
        }

    # ATR volatility
    atr_col = ind.atr_col
    if atr_col in df.columns:
        atr_avg = df[atr_col].rolling(50).mean()
        groups['ATR'] = {
            'ATR High (>1.5x)': df[atr_col] > atr_avg * 1.5,
            'ATR Normal': (df[atr_col] >= atr_avg * 0.5) & (df[atr_col] <= atr_avg * 1.5),
            'ATR Low (<0.5x)': df[atr_col] < atr_avg * 0.5,
        }

    # Strat type
    groups['Strat'] = {
        'Strat 1': labels == '1',
        'Strat 2U': labels == '2U',
        'Strat 2D': labels == '2D',
        'Strat 3': labels == '3',
    }

    # Prev bar Strat
    prev_labels = labels.shift(1)
    groups['Prev_Strat'] = {
        'Prev 1': prev_labels == '1',
        'Prev 2U': prev_labels == '2U',
        'Prev 2D': prev_labels == '2D',
        'Prev 3': prev_labels == '3',
    }

    # Order Block
    if 'Order_Block_Position' in df.columns:
        groups['Order_Block'] = {
            'Above OB': df['Order_Block_Position'] == 1,
            'Within OB': df['Order_Block_Position'] == 0,
            'Below OB': df['Order_Block_Position'] == -1,
        }
    if 'Order_Block_Test' in df.columns:
        groups['OB_Test'] = {
            'OB Test': df['Order_Block_Test'] == 1,
            'No OB Test': df['Order_Block_Test'] == 0,
        }

    return groups


# ---------------------------------------------------------------------------
# 4A. Combinatorial Feature Scan
# ---------------------------------------------------------------------------

def run_combinatorial_scan(
    df: pd.DataFrame,
    labels: pd.Series,
    groups: Dict[str, Dict[str, pd.Series]],
    min_samples: int = 30,
    min_win_rate: float = 0.65,
    max_combos: int = 3,
) -> pd.DataFrame:
    """Scan 2-way and 3-way feature combinations for high win rate setups.

    "Win" = next bar continues in predicted direction.
    For bullish setups (Strat 2U or CALL conditions): next bar is 2U
    For bearish setups (Strat 2D or PUT conditions): next bar is 2D
    """
    close = df['Close'] if 'Close' in df.columns else df['Last']
    next_return = close.pct_change().shift(-1) * 10000  # bps
    next_label = labels.shift(-1)

    group_names = list(groups.keys())
    results = []

    # For each direction, define what "win" means
    for direction, win_type, dir_label in [
        ('CALL', '2U', 'Bullish'),
        ('PUT', '2D', 'Bearish'),
    ]:
        win_mask = next_label == win_type
        if direction == 'CALL':
            return_signed = next_return
        else:
            return_signed = -next_return

        # 2-way combinations
        for i, g1_name in enumerate(group_names):
            for g2_name in group_names[i + 1:]:
                for f1_name, f1_mask in groups[g1_name].items():
                    for f2_name, f2_mask in groups[g2_name].items():
                        combined = f1_mask & f2_mask
                        n = combined.sum()
                        if n < min_samples:
                            continue

                        wins = (combined & win_mask).sum()
                        wr = wins / n
                        avg_ret = return_signed[combined].mean()

                        if wr >= min_win_rate:
                            results.append({
                                'direction': dir_label,
                                'combo_size': 2,
                                'setup': f"{f1_name} + {f2_name}",
                                'win_rate': wr,
                                'trades': int(n),
                                'avg_return_bps': avg_ret,
                                'confidence': sample_size_label(int(n)),
                            })

        # 3-way combinations (limit to keep runtime reasonable)
        if max_combos >= 3 and len(group_names) >= 3:
            for combo_groups in combinations(range(len(group_names)), 3):
                g1, g2, g3 = [group_names[i] for i in combo_groups]

                for f1_name, f1_mask in groups[g1].items():
                    for f2_name, f2_mask in groups[g2].items():
                        for f3_name, f3_mask in groups[g3].items():
                            combined = f1_mask & f2_mask & f3_mask
                            n = combined.sum()
                            if n < min_samples:
                                continue

                            wins = (combined & win_mask).sum()
                            wr = wins / n
                            avg_ret = return_signed[combined].mean()

                            if wr >= min_win_rate:
                                results.append({
                                    'direction': dir_label,
                                    'combo_size': 3,
                                    'setup': f"{f1_name} + {f2_name} + {f3_name}",
                                    'win_rate': wr,
                                    'trades': int(n),
                                    'avg_return_bps': avg_ret,
                                    'confidence': sample_size_label(int(n)),
                                })

    if not results:
        return pd.DataFrame()

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('win_rate', ascending=False)
    return results_df


def format_scan_results(ticker: str, results_df: pd.DataFrame) -> str:
    """Format combinatorial scan results into markdown."""
    report = md_header(f"4A. Combinatorial Feature Scan — {ticker}", 2)
    report += "\nHigh-probability setups from 2-way and 3-way indicator combinations.\n\n"

    if results_df.empty:
        return report + "No setups met the minimum criteria (65%+ WR, 30+ trades).\n\n"

    for direction in ['Bullish', 'Bearish']:
        dir_df = results_df[results_df['direction'] == direction]
        if dir_df.empty:
            continue

        report += md_header(f"{ticker} — {direction} Setups (WR >= 65%, n >= 30)", 3)

        headers = ['Rank', 'Setup', 'WR', 'Trades', 'Avg Return', 'Combo Size', 'Confidence']
        rows = []

        for rank, (_, r) in enumerate(dir_df.head(30).iterrows(), 1):
            rows.append([
                rank,
                r['setup'],
                fmt_pct(r['win_rate'] * 100),
                fmt_num(r['trades']),
                fmt_bps(r['avg_return_bps']),
                r['combo_size'],
                r['confidence'],
            ])

        report += md_table(headers, rows) + '\n'

        # Summary stats
        report += f"\nTotal setups found: {len(dir_df)}\n"
        report += f"Best win rate: {dir_df['win_rate'].max():.1%} "
        report += f"({dir_df.iloc[0]['setup']})\n"
        top_reliable = dir_df[dir_df['trades'] >= 100].head(1)
        if not top_reliable.empty:
            r = top_reliable.iloc[0]
            report += f"Best reliable (n>=100): {r['win_rate']:.1%} with {r['trades']} trades "
            report += f"({r['setup']})\n"
        report += '\n'

    return report


# ---------------------------------------------------------------------------
# 4B. Decision Tree Analysis
# ---------------------------------------------------------------------------

def run_decision_tree_analysis(
    df: pd.DataFrame,
    labels: pd.Series,
    ind: IndicatorConfig = None,
    max_depth: int = 4,
    min_leaf_samples: int = 50,
) -> str:
    """Train decision trees per ticker and extract high-purity paths."""
    if ind is None:
        ind = IndicatorConfig()

    report = ""
    close = df['Close'] if 'Close' in df.columns else df['Last']
    next_return = close.pct_change().shift(-1) * 10000

    # Build feature matrix
    feature_cols = []
    rsi_col = ind.rsi_col
    if rsi_col in df.columns:
        feature_cols.append(rsi_col)
    if 'StochRSI_K' in df.columns:
        feature_cols.append('StochRSI_K')
    if 'RVOL' in df.columns:
        feature_cols.append('RVOL')
    if 'Price_vs_VWAP' in df.columns:
        feature_cols.append('Price_vs_VWAP')
    if f'Price_vs_EMA{ind.ema_fast_period}' in df.columns:
        feature_cols.append(f'Price_vs_EMA{ind.ema_fast_period}')
    if f'Price_vs_EMA{ind.ema_mid_period}' in df.columns:
        feature_cols.append(f'Price_vs_EMA{ind.ema_mid_period}')
    if 'EMA_Cross' in df.columns:
        feature_cols.append('EMA_Cross')
    if 'ORB_30m_Trend' in df.columns:
        feature_cols.append('ORB_30m_Trend')
    if 'Order_Block_Position' in df.columns:
        feature_cols.append('Order_Block_Position')
    if 'Order_Block_Test' in df.columns:
        feature_cols.append('Order_Block_Test')
    if ind.atr_col in df.columns:
        feature_cols.append(ind.atr_col)
    if 'BB_Pct' in df.columns:
        feature_cols.append('BB_Pct')
    if 'MACD_Histogram' in df.columns:
        feature_cols.append('MACD_Histogram')
    if 'Broke_Prev_Day_High' in df.columns:
        feature_cols.extend(['Broke_Prev_Day_High', 'Broke_Prev_Day_Low'])

    # Strat numeric encoding
    strat_numeric = labels.map({'1': 0, '2U': 1, '2D': -1, '3': 2, 'X': 0}).fillna(0)
    prev_strat = strat_numeric.shift(1)
    df_features = df[feature_cols].copy()
    df_features['strat_numeric'] = strat_numeric
    df_features['prev_strat'] = prev_strat

    # Target: positive next-bar return
    target = (next_return > 0).astype(int)

    # Drop NaN rows
    valid = df_features.notna().all(axis=1) & target.notna()
    X = df_features[valid]
    y = target[valid]

    if len(X) < 200:
        return report + "Insufficient data for decision tree.\n\n"

    try:
        from sklearn.tree import DecisionTreeClassifier, export_text
        from sklearn.ensemble import RandomForestClassifier
    except ImportError:
        # Fallback: rule-based analysis instead
        report += "\n*sklearn not available — using rule-based analysis instead.*\n\n"
        return report + _rule_based_analysis(df, labels, ind)

    # Decision Tree
    dt = DecisionTreeClassifier(
        max_depth=max_depth,
        min_samples_leaf=min_leaf_samples,
        class_weight='balanced',
    )
    dt.fit(X, y)

    # Extract high-purity leaf nodes
    tree = dt.tree_
    report += md_header("Decision Tree — High-Purity Paths", 3)

    paths = []
    _extract_paths(dt, X.columns.tolist(), tree, 0, [], paths)

    # Filter to high win rate paths
    high_purity = [p for p in paths if p['win_rate'] >= 0.60 and p['samples'] >= min_leaf_samples]
    high_purity.sort(key=lambda x: x['win_rate'], reverse=True)

    if high_purity:
        headers = ['Path', 'Win Rate', 'Samples', 'Avg Return (bps)']
        rows = []
        for path in high_purity[:15]:
            # Calculate average return for this path
            mask = pd.Series(True, index=X.index)
            for feature, op, threshold in path['conditions']:
                col_idx = X.columns.get_loc(feature)
                if op == '<=':
                    mask &= X.iloc[:, col_idx] <= threshold
                else:
                    mask &= X.iloc[:, col_idx] > threshold

            avg_ret = next_return[mask & valid].mean() if mask.sum() > 0 else 0

            conditions_str = ' AND '.join(
                f"{f} {op} {t:.2f}" for f, op, t in path['conditions']
            )
            rows.append([
                conditions_str,
                fmt_pct(path['win_rate'] * 100),
                fmt_num(path['samples']),
                fmt_bps(avg_ret),
            ])

        report += md_table(headers, rows) + '\n'
    else:
        report += "No paths with 60%+ win rate and sufficient samples found.\n\n"

    # Random Forest feature importance
    report += md_header("Random Forest Feature Importance", 3)

    rf = RandomForestClassifier(
        n_estimators=100,
        max_depth=6,
        min_samples_leaf=50,
        class_weight='balanced',
        random_state=42,
        n_jobs=-1,
    )
    rf.fit(X, y)

    importances = pd.Series(rf.feature_importances_, index=X.columns)
    importances = importances.sort_values(ascending=False)

    headers = ['Rank', 'Feature', 'Importance']
    rows = []
    for rank, (feat, imp) in enumerate(importances.items(), 1):
        rows.append([rank, feat, f"{imp:.4f}"])

    report += md_table(headers, rows) + '\n'

    # RF accuracy
    predictions = rf.predict(X)
    accuracy = (predictions == y).mean()
    report += f"\nRandom Forest accuracy: {accuracy:.1%} (in-sample)\n\n"

    return report


def _extract_paths(dt, feature_names, tree, node_id, current_path, all_paths):
    """Recursively extract decision paths from a fitted tree."""
    if tree.children_left[node_id] == -1:  # Leaf node
        total = tree.n_node_samples[node_id]
        values = tree.value[node_id][0]
        win_rate = values[1] / total if total > 0 else 0

        all_paths.append({
            'conditions': list(current_path),
            'win_rate': win_rate,
            'samples': int(total),
        })
        return

    feature = feature_names[tree.feature[node_id]]
    threshold = tree.threshold[node_id]

    # Left child (<=)
    left_path = current_path + [(feature, '<=', threshold)]
    _extract_paths(dt, feature_names, tree, tree.children_left[node_id], left_path, all_paths)

    # Right child (>)
    right_path = current_path + [(feature, '>', threshold)]
    _extract_paths(dt, feature_names, tree, tree.children_right[node_id], right_path, all_paths)


def _rule_based_analysis(df: pd.DataFrame, labels: pd.Series, ind: IndicatorConfig) -> str:
    """Fallback analysis when sklearn is not available."""
    report = md_header("Rule-Based Feature Analysis", 3)
    report += "\n*Using manual feature importance (correlation with next-bar return).*\n\n"

    close = df['Close'] if 'Close' in df.columns else df['Last']
    next_return = close.pct_change().shift(-1) * 10000

    feature_cols = []
    for col in df.columns:
        if col in [ind.rsi_col, 'StochRSI_K', 'RVOL', 'Price_vs_VWAP',
                    f'Price_vs_EMA{ind.ema_fast_period}', f'Price_vs_EMA{ind.ema_mid_period}',
                    'EMA_Cross', 'ORB_30m_Trend', 'Order_Block_Position',
                    'BB_Pct', 'MACD_Histogram']:
            feature_cols.append(col)

    correlations = {}
    for col in feature_cols:
        valid = df[col].notna() & next_return.notna()
        if valid.sum() > 100:
            correlations[col] = abs(df[col][valid].corr(next_return[valid]))

    sorted_corr = sorted(correlations.items(), key=lambda x: x[1], reverse=True)

    headers = ['Rank', 'Feature', 'Abs Correlation']
    rows = []
    for rank, (feat, corr) in enumerate(sorted_corr, 1):
        rows.append([rank, feat, f"{corr:.4f}"])

    report += md_table(headers, rows) + '\n'
    return report


# ---------------------------------------------------------------------------
# 4C. Per-Ticker Feature Importance (computed in 4B)
# ---------------------------------------------------------------------------

# Feature importance is already included in the decision tree analysis above.


# ---------------------------------------------------------------------------
# 4D. Sample Size Analysis
# ---------------------------------------------------------------------------

def analyze_sample_sizes(ticker: str, results_df: pd.DataFrame) -> str:
    """Analyze sample size distribution of discovered setups."""
    report = md_header(f"4D. Sample Size Analysis — {ticker}", 2)

    if results_df.empty:
        return report + "No setups to analyze.\n\n"

    report += "\n**Setup Distribution by Confidence Level:**\n\n"

    buckets = [
        ('Low (n < 30)', results_df[results_df['trades'] < 30]),
        ('Moderate (30-99)', results_df[(results_df['trades'] >= 30) & (results_df['trades'] < 100)]),
        ('Good (100-499)', results_df[(results_df['trades'] >= 100) & (results_df['trades'] < 500)]),
        ('High (500+)', results_df[results_df['trades'] >= 500]),
    ]

    headers = ['Confidence Level', 'Setups', 'Best WR', 'Avg WR', 'Action']
    rows = []
    actions = {
        'Low (n < 30)': 'Monitor only',
        'Moderate (30-99)': 'Paper trade first',
        'Good (100-499)': 'Small size trading',
        'High (500+)': 'Full conviction',
    }

    for label, bucket_df in buckets:
        if bucket_df.empty:
            rows.append([label, '0', 'N/A', 'N/A', actions[label]])
        else:
            rows.append([
                label,
                fmt_num(len(bucket_df)),
                fmt_pct(bucket_df['win_rate'].max() * 100),
                fmt_pct(bucket_df['win_rate'].mean() * 100),
                actions[label],
            ])

    report += md_table(headers, rows) + '\n'

    # Top setups per confidence level
    for label, bucket_df in buckets:
        if bucket_df.empty or len(bucket_df) == 0:
            continue

        report += f"\n**Top 5 {label} Setups:**\n\n"
        top = bucket_df.head(5)
        headers = ['Setup', 'WR', 'Trades', 'Direction']
        rows = []
        for _, r in top.iterrows():
            rows.append([r['setup'], fmt_pct(r['win_rate'] * 100),
                        fmt_num(r['trades']), r['direction']])
        report += md_table(headers, rows) + '\n'

    return report


# ---------------------------------------------------------------------------
# 4A-HTF: Multi-Timeframe Combinatorial Scan (Forward Return Win Condition)
# ---------------------------------------------------------------------------

def run_combinatorial_scan_fwd(
    df: pd.DataFrame,
    labels: pd.Series,
    groups: Dict[str, Dict[str, pd.Series]],
    fwd_return: pd.Series,
    min_samples: int = 50,
    min_win_rate: float = 0.60,
    max_combos: int = 3,
) -> pd.DataFrame:
    """Scan combinations using forward multi-bar return as win condition.

    Instead of 'next bar is 2U', uses 'positive forward return over N bars'.
    This is less noisy than single-bar Strat classification.
    """
    group_names = list(groups.keys())
    results = []

    for direction, dir_label in [('CALL', 'Bullish'), ('PUT', 'Bearish')]:
        if direction == 'CALL':
            win_mask = fwd_return > 0
            return_signed = fwd_return
        else:
            win_mask = fwd_return < 0
            return_signed = -fwd_return

        # 2-way combinations
        for i, g1_name in enumerate(group_names):
            for g2_name in group_names[i + 1:]:
                for f1_name, f1_mask in groups[g1_name].items():
                    for f2_name, f2_mask in groups[g2_name].items():
                        combined = f1_mask & f2_mask
                        valid = combined & fwd_return.notna()
                        n = valid.sum()
                        if n < min_samples:
                            continue

                        wins = (valid & win_mask).sum()
                        wr = wins / n
                        avg_ret = return_signed[valid].mean()

                        if wr >= min_win_rate:
                            results.append({
                                'direction': dir_label,
                                'combo_size': 2,
                                'setup': f"{f1_name} + {f2_name}",
                                'win_rate': wr,
                                'trades': int(n),
                                'avg_return_bps': float(avg_ret),
                                'confidence': sample_size_label(int(n)),
                            })

        # 3-way combinations
        if max_combos >= 3 and len(group_names) >= 3:
            for combo_groups in combinations(range(len(group_names)), 3):
                g1, g2, g3 = [group_names[i] for i in combo_groups]

                for f1_name, f1_mask in groups[g1].items():
                    for f2_name, f2_mask in groups[g2].items():
                        for f3_name, f3_mask in groups[g3].items():
                            combined = f1_mask & f2_mask & f3_mask
                            valid = combined & fwd_return.notna()
                            n = valid.sum()
                            if n < min_samples:
                                continue

                            wins = (valid & win_mask).sum()
                            wr = wins / n
                            avg_ret = return_signed[valid].mean()

                            if wr >= min_win_rate:
                                results.append({
                                    'direction': dir_label,
                                    'combo_size': 3,
                                    'setup': f"{f1_name} + {f2_name} + {f3_name}",
                                    'win_rate': wr,
                                    'trades': int(n),
                                    'avg_return_bps': float(avg_ret),
                                    'confidence': sample_size_label(int(n)),
                                })

    if not results:
        return pd.DataFrame()

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('win_rate', ascending=False)
    return results_df


# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------

def run_phase4(tickers: list = None):
    """Run full Phase 4 analysis for all tickers.

    Enhanced to scan on 5m and 15m bars in addition to 1m,
    using multi-bar forward return as win condition for HTF scans.
    """
    if tickers is None:
        tickers = TICKERS

    all_setups = {}

    for ticker in tickers:
        progress(f"Starting Phase 4 analysis", ticker)

        # Load and enrich 1m data
        progress("Loading and enriching 1m data...", ticker)
        df_1m = load_ticker_1m(ticker)
        if df_1m.empty:
            progress("No data, skipping.", ticker)
            continue

        df = enrich_with_indicators(df_1m)
        labels = df['strat_candle'] if 'strat_candle' in df.columns else classify_strat_series(df)
        progress(f"Enriched {len(df):,} bars", ticker)

        # Build report
        report = md_header(f"Phase 4: High-Probability Setup Discovery — {ticker}", 1)
        report += f"\nGenerated: {timestamp_str()}\n"
        report += f"Data: {df.index.min()} to {df.index.max()} ({len(df):,} bars)\n\n"

        # ---- 4A: Combinatorial scan on 1m (original) ----
        progress("Running 1m combinatorial feature scan...", ticker)
        groups = define_feature_groups(df, labels)
        progress(f"  Defined {len(groups)} feature groups, scanning combinations...", ticker)
        results_df = run_combinatorial_scan(df, labels, groups, min_samples=30, min_win_rate=0.65)
        report += format_scan_results(ticker, results_df)

        # ---- 4A-HTF: Combinatorial scan on 5m and 15m ----
        all_tf_results = [results_df] if not results_df.empty else []

        for htf in ['5m', '15m']:
            progress(f"Running {htf} combinatorial feature scan...", ticker)
            try:
                df_htf = resample_to_timeframe(df_1m, htf)
                df_htf = enrich_with_indicators(df_htf)
                labels_htf = df_htf['strat_candle'] if 'strat_candle' in df_htf.columns else classify_strat_series(df_htf)
                groups_htf = define_feature_groups(df_htf, labels_htf)

                # Use 5-bar forward return as win condition
                close_htf = df_htf['Close'] if 'Close' in df_htf.columns else df_htf['Last']
                fwd_5_ret = close_htf.pct_change(5).shift(-5) * 10000

                results_htf = run_combinatorial_scan_fwd(
                    df_htf, labels_htf, groups_htf, fwd_5_ret,
                    min_samples=50, min_win_rate=0.60,
                )

                if not results_htf.empty:
                    results_htf['timeframe'] = htf
                    all_tf_results.append(results_htf)

                    report += md_header(f"4A-{htf.upper()}: Combinatorial Scan on {htf} Bars", 2)
                    report += f"\nWin condition: positive return over next 5 {htf} bars.\n"
                    report += f"Threshold: 60%+ WR with 50+ trades.\n\n"
                    report += format_scan_results(f"{ticker} ({htf})", results_htf)

                progress(f"  {htf}: found {len(results_htf)} setups", ticker)
            except Exception as e:
                progress(f"  {htf} scan failed: {e}", ticker)

        # Combine all results
        if all_tf_results:
            combined_results = pd.concat(all_tf_results, ignore_index=True)
            combined_results = combined_results.sort_values('win_rate', ascending=False)
        else:
            combined_results = results_df

        all_setups[ticker] = combined_results

        # ---- 4B: Decision tree analysis ----
        progress("Running decision tree analysis...", ticker)
        report += md_header(f"4B. Decision Tree / Random Forest — {ticker}", 2)
        report += run_decision_tree_analysis(df, labels)

        # ---- 4D: Sample size analysis ----
        if not combined_results.empty:
            progress("Analyzing sample sizes...", ticker)
            report += analyze_sample_sizes(ticker, combined_results)

        save_report(report, f'phase4_setup_discovery_{ticker.lower()}.md')

        # Save CSV of all setups
        if not combined_results.empty:
            csv_dir = REPORTS_DIR / 'data'
            csv_dir.mkdir(parents=True, exist_ok=True)
            combined_results.to_csv(csv_dir / f'high_prob_setups_{ticker.lower()}.csv', index=False)

        progress("Phase 4 complete!", ticker)

    # Cross-ticker comparison
    if len(all_setups) >= 2:
        progress("Generating cross-ticker setup comparison...")
        comparison = md_header("Phase 4: Cross-Ticker Setup Comparison", 1)
        comparison += f"\nGenerated: {timestamp_str()}\n\n"

        comparison += md_header("Universal vs Ticker-Specific Setups", 2)

        all_setup_names = {}
        for ticker, df_setups in all_setups.items():
            if not df_setups.empty:
                for _, r in df_setups.iterrows():
                    name = r['setup']
                    if name not in all_setup_names:
                        all_setup_names[name] = {}
                    all_setup_names[name][ticker] = r['win_rate']

        universal = {k: v for k, v in all_setup_names.items() if len(v) >= 2}
        if universal:
            comparison += "Setups found in multiple tickers (potential universal edges):\n\n"
            headers = ['Setup'] + TICKERS + ['Avg WR', 'Universal?']
            rows = []
            for setup, ticker_wrs in sorted(universal.items(), key=lambda x: np.mean(list(x[1].values())), reverse=True)[:20]:
                row = [setup]
                for t in TICKERS:
                    row.append(fmt_pct(ticker_wrs.get(t, 0) * 100) if t in ticker_wrs else 'N/A')
                avg = np.mean(list(ticker_wrs.values()))
                row.append(fmt_pct(avg * 100))
                row.append('Yes' if len(ticker_wrs) == len(TICKERS) else 'Partial')
                rows.append(row)

            comparison += md_table(headers, rows) + '\n'
        else:
            comparison += "**No universal setups found across tickers.** All high-probability setups "
            comparison += "are ticker-specific, confirming that each ticker requires its own playbook.\n\n"

        comparison += md_header("Per-Ticker Best Setups", 2)
        for ticker, df_setups in all_setups.items():
            if df_setups.empty:
                comparison += f"**{ticker}:** No setups found.\n\n"
                continue
            comparison += f"**{ticker}** ({len(df_setups)} setups):\n"
            for _, r in df_setups.head(5).iterrows():
                tf_note = f" [{r['timeframe']}]" if 'timeframe' in r.index and pd.notna(r.get('timeframe')) else ""
                comparison += f"- {r['setup']}{tf_note} — WR: {fmt_pct(r['win_rate'] * 100)}, "
                comparison += f"n={int(r['trades'])}, {r['direction']}\n"
            comparison += '\n'

        save_report(comparison, 'phase4_setup_comparison.md')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Phase 4: Setup Discovery')
    parser.add_argument('--tickers', nargs='+', default=TICKERS)
    args = parser.parse_args()
    run_phase4(tickers=args.tickers)
