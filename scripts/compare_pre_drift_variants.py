#!/usr/bin/env python3
"""
Compare pre-drift feature variants A vs B against the actual outcome.

Background: PR #488 shipped Variant A — 6 columns for intraday max_high /
min_low across 3d, 5d, 10d pre-earnings windows. The user proposed Variant B
afterward — drop the 3d window (subset of 5d), keep 5d/10d, ADD
days_since_extreme columns (when did the max/min hit in the window).

This script measures which variant has more *independent* predictive power
against `reaction_gap_pct` on the actual production data. Run after
compute-earnings-reactions has populated the Variant A columns; Variant B
features are computed on the fly from `market_data_daily`.

Outputs:
  - Per-feature Pearson correlation with reaction_gap_pct
  - Per-variant aggregate predictive lift (mean |correlation|)
  - Univariate-AUC for the directional sign of reaction_gap_pct
  - A `RECOMMENDATION: variant_<X>` line so the orchestrator can branch

Usage:
    python -m scripts.compare_pre_drift_variants
    python -m scripts.compare_pre_drift_variants --min-quarters 8
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcp.database import query_to_dataframe

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)


VARIANT_A_FEATURES = [
    'max_high_pre_3d_pct', 'min_low_pre_3d_pct',
    'max_high_pre_5d_pct', 'min_low_pre_5d_pct',
    'max_high_pre_10d_pct', 'min_low_pre_10d_pct',
]

# Variant B drops 3d (subset of 5d), adds days_since_extreme columns
# computed on the fly. The 5d/10d max_high/min_low columns are shared.
VARIANT_B_FEATURES = [
    'max_high_pre_5d_pct', 'min_low_pre_5d_pct',
    'max_high_pre_10d_pct', 'min_low_pre_10d_pct',
    'days_since_max_high_5d', 'days_since_min_low_5d',
    'days_since_max_high_10d', 'days_since_min_low_10d',
]


def fetch_reactions_with_pre_window() -> pd.DataFrame:
    """Pull all reaction rows that have Variant A columns populated.

    Returns a DataFrame with one row per (ticker, reported_date) plus
    every column needed by both variants. Variant B's days_since_*
    features are computed in a second pass by joining to
    market_data_daily — kept out of this query because of the
    per-row OFFSET semantics.
    """
    sql = """
        SELECT
            ticker, reported_date,
            reaction_gap_pct,
            d_minus_5_close, d_minus_3_close, d_minus_10_close, d_minus_1_close,
            max_high_pre_3d_pct, min_low_pre_3d_pct,
            max_high_pre_5d_pct, min_low_pre_5d_pct,
            max_high_pre_10d_pct, min_low_pre_10d_pct
        FROM earnings_reactions
        WHERE max_high_pre_5d_pct IS NOT NULL
          AND reaction_gap_pct IS NOT NULL
          AND reported_date IS NOT NULL
        ORDER BY ticker, reported_date
    """
    df = query_to_dataframe(sql)
    return df


def fetch_bars_for_window(ticker: str, reported_date) -> pd.DataFrame:
    """11 trading days before reported_date — D-10..D-1. One ticker, one row."""
    sql = """
        SELECT date, high, low
        FROM market_data_daily
        WHERE ticker = :tk AND date < :rd
        ORDER BY date DESC
        LIMIT 11
    """
    df = query_to_dataframe(sql, {'tk': ticker, 'rd': reported_date})
    if df is None or df.empty:
        return pd.DataFrame()
    # Reverse to ascending so index 0 = D-11, index 10 = D-1.
    return df.iloc[::-1].reset_index(drop=True)


def add_variant_b_features(df: pd.DataFrame) -> pd.DataFrame:
    """For each reaction row, compute days_since_max_high_5d / _10d and
    days_since_min_low_5d / _10d.

    Convention: index runs D-1 (0) through D-N (N-1). So
    days_since_max_high_5d in {0,1,2,3,4}, with 0 meaning the highest
    intraday print in the 5-day window was D-1 (most recent).
    """
    log.info("Computing Variant B days_since_* for %d reaction rows…", len(df))
    rows_b = []
    skipped_5d = 0
    skipped_10d_only = 0
    for i, (_, r) in enumerate(df.iterrows(), 1):
        bars = fetch_bars_for_window(r['ticker'], r['reported_date'])
        bars_desc = (
            bars.iloc[::-1].reset_index(drop=True)
            if not bars.empty else bars
        )
        n = len(bars_desc)
        row: dict = {
            'days_since_max_high_5d':  None,
            'days_since_min_low_5d':   None,
            'days_since_max_high_10d': None,
            'days_since_min_low_10d':  None,
        }
        # 5d window — requires at least 5 bars
        if n >= 5:
            win5 = bars_desc.head(5)
            row['days_since_max_high_5d'] = int(win5['high'].astype(float).idxmax())
            row['days_since_min_low_5d']  = int(win5['low'].astype(float).idxmin())
        else:
            skipped_5d += 1
        # 10d window — requires at least 10 bars. Without this guard a row
        # with 5-9 bars would emit a "10d" feature computed over a 5-9 day
        # window, biasing the aggregate (Codex P2 #492). Null instead so
        # Variant B's 10d columns drop these rows the same way Variant A
        # does (max_high_pre_10d_pct IS NULL when D-10 is out of range).
        if n >= 10:
            win10 = bars_desc.head(10)
            row['days_since_max_high_10d'] = int(win10['high'].astype(float).idxmax())
            row['days_since_min_low_10d']  = int(win10['low'].astype(float).idxmin())
        elif n >= 5:
            skipped_10d_only += 1
        rows_b.append(row)
        if i % 500 == 0:
            log.info("  …processed %d/%d rows", i, len(df))

    log.info("  …done. skipped_5d=%d (insufficient bars); "
             "skipped_10d_only=%d (5-9 bars — 10d nulled per Codex #492)",
             skipped_5d, skipped_10d_only)
    return pd.concat([df.reset_index(drop=True),
                      pd.DataFrame(rows_b)], axis=1)


def evaluate_variant(df: pd.DataFrame, features: list[str], name: str) -> dict:
    """Compute Pearson correlation + univariate AUC for each feature vs
    reaction_gap_pct. Returns a per-feature summary dict + a single
    aggregate score (mean of |correlations|, ignoring NaNs)."""
    log.info("Evaluating %s with features=%s", name, features)
    out = []
    y = df['reaction_gap_pct'].astype(float)
    y_dir = (y > 0).astype(int)  # for AUC
    for f in features:
        if f not in df.columns:
            log.warning("  feature %s missing — skip", f)
            continue
        x = df[f].astype(float)
        mask = x.notna() & y.notna()
        if mask.sum() < 50:
            log.warning("  feature %s: only %d non-null rows — skip", f, mask.sum())
            continue
        corr = x[mask].corr(y[mask])
        # Univariate AUC via the rank approach
        try:
            from sklearn.metrics import roc_auc_score
            auc = roc_auc_score(y_dir[mask], x[mask])
            # AUC < 0.5 means inverse — flip
            auc = max(auc, 1 - auc)
        except ImportError:
            auc = None
        out.append({
            'feature': f,
            'n': int(mask.sum()),
            'corr_with_gap': float(corr) if pd.notna(corr) else None,
            'abs_corr': abs(float(corr)) if pd.notna(corr) else None,
            'auc_directional': float(auc) if auc is not None else None,
        })

    aggregate = (
        pd.DataFrame(out)['abs_corr'].dropna().mean()
        if out else None
    )
    return {'variant': name, 'features': out, 'aggregate_abs_corr': aggregate}


def render_report(results_a: dict, results_b: dict, min_q: int) -> None:
    print("BEGIN_VARIANT_COMPARISON_REPORT")
    print("=" * 70)
    print(f"Pre-Drift Feature Variant Comparison (min-quarters={min_q})")
    print("=" * 70)
    for r in (results_a, results_b):
        print(f"\n## Variant {r['variant']}\n")
        print(f"  aggregate mean |corr|: {r['aggregate_abs_corr']:.4f}"
              if r['aggregate_abs_corr'] is not None else "  (no features)")
        print(f"  {'feature':30s} {'n':>6s} {'corr_gap':>10s} {'|corr|':>8s} {'auc':>6s}")
        for f in r['features']:
            print(
                f"  {f['feature']:30s} {f['n']:6d} "
                f"{(f['corr_with_gap'] or 0.0):+10.4f} "
                f"{(f['abs_corr']      or 0.0):8.4f} "
                f"{(f['auc_directional'] or 0.0):6.3f}"
            )

    # Pick a winner
    a = results_a['aggregate_abs_corr'] or 0.0
    b = results_b['aggregate_abs_corr'] or 0.0
    if abs(a - b) < 0.005:
        rec = 'tie'
        print(f"\nVariants A ({a:.4f}) and B ({b:.4f}) are within 0.005 of each other — TIE.")
    elif b > a:
        rec = 'variant_B'
        print(f"\nVariant B (mean |corr| = {b:.4f}) beats Variant A ({a:.4f}) by {(b - a) * 100:.2f}%.")
    else:
        rec = 'variant_A'
        print(f"\nVariant A (mean |corr| = {a:.4f}) beats Variant B ({b:.4f}) by {(a - b) * 100:.2f}%.")
    print(f"\nRECOMMENDATION: {rec}")
    print("=" * 70)
    print("END_VARIANT_COMPARISON_REPORT")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--min-quarters', type=int, default=8,
                   help='Filter tickers with fewer than N reaction rows (default 8)')
    args = p.parse_args()

    df = fetch_reactions_with_pre_window()
    log.info("Loaded %d rows × %d tickers from earnings_reactions",
             len(df), df['ticker'].nunique())

    # Filter to tickers with enough history
    counts = df.groupby('ticker').size()
    keep = counts[counts >= args.min_quarters].index.tolist()
    df = df[df['ticker'].isin(keep)].reset_index(drop=True)
    log.info("After min-quarters≥%d filter: %d rows × %d tickers",
             args.min_quarters, len(df), df['ticker'].nunique())

    df_b = add_variant_b_features(df)

    results_a = evaluate_variant(df_b, VARIANT_A_FEATURES, 'A')
    results_b = evaluate_variant(df_b, VARIANT_B_FEATURES, 'B')

    render_report(results_a, results_b, args.min_quarters)


if __name__ == '__main__':
    main()
