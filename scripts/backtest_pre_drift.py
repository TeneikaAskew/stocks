#!/usr/bin/env python3
"""
Walk-forward backtest of the pre_drift_score formula.

Symmetric with scripts/backtest_playability.py — for each
(ticker, fiscal_date_ending) row in earnings_reactions:

  1. As-of just before this report, compute pre_drift_score +
     pre_drift_archetype using ONLY past rows for the same ticker.
  2. Note the actual outcome at this row: drift_5d_pct.
  3. Score the archetype's directional prediction against the actual:
       pre_bullish_run  hit if drift_5d_pct > 0
       pre_bearish_fade hit if drift_5d_pct < 0
       pre_choppy       hit if |drift_5d_pct| > MIXED_HIT_THRESHOLD
       pre_quiet        skipped
  4. Bucket by score quintile + archetype, aggregate hit rate.

Output:
  - BACKTEST_PRE_DRIFT_RESULTS.md with quintile + archetype tables
  - stdout block bracketed by BEGIN_BACKTEST_REPORT / END_BACKTEST_REPORT
    so a Cloud Run Job can capture it via gcloud beta run jobs
    executions logs read.

The output is used to calibrate _PRE_DRIFT_QUINTILE_BOUNDARIES in
lib/earnings_reactions.py. If Q1 → Q5 is flat or inverted, the
formula needs redesign before shipping the pre-drift action tags.

Usage:
    python -m scripts.backtest_pre_drift
    python -m scripts.backtest_pre_drift --min-nq 12
    python -m scripts.backtest_pre_drift --output BACKTEST.md
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcp.database import query_to_dataframe
from lib.earnings_reactions import (
    compute_pre_drift_score,
    classify_pre_drift_archetype,
)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)


# Hit threshold for the 'pre_choppy' archetype. Same scale as drift_5d_pct
# (percent). Pre-drift baseline magnitudes are smaller than post-earnings
# reactions so this threshold is lower than backtest_playability's 3.0.
MIXED_HIT_THRESHOLD = 1.5


def fetch_pre_drift_for_backtest() -> pd.DataFrame:
    """Pull all earnings_reactions rows with drift_5d_pct populated."""
    sql = """
        SELECT ticker, reported_date, fiscal_date_ending,
               drift_5d_pct,
               drift_3d_pct,
               pre_drift_consistent_5d,
               pre_drift_reverses_into_gap,
               reaction_gap_pct
        FROM earnings_reactions
        WHERE drift_5d_pct IS NOT NULL
          AND reported_date IS NOT NULL
        ORDER BY ticker, reported_date
    """
    return query_to_dataframe(sql)


def _pre_drift_stats_from_past(past: pd.DataFrame) -> dict | None:
    """Compute pre_drift archetype/score inputs from a ticker's past rows.

    Mirrors lib.earnings_reactions.query_pre_drift_stats but in-memory
    and walk-forward — only uses rows strictly before the target date.
    """
    if past.empty:
        return None
    drifts = past['drift_5d_pct'].dropna()
    if drifts.empty:
        return None
    return {
        'n_q': len(past),
        'drift_magnitude_pct': float(drifts.abs().mean()),
        'directional_drift_pct': float(drifts.mean()),
        'pre_dir_consistency':
            float(past['pre_drift_consistent_5d'].mean())
            if past['pre_drift_consistent_5d'].notna().any() else None,
        'pre_reversal_rate':
            float(past['pre_drift_reverses_into_gap'].mean())
            if past['pre_drift_reverses_into_gap'].notna().any() else None,
    }


def hit_for_archetype(archetype: str | None, drift_5d_pct: float) -> bool | None:
    """Was the archetype's directional prediction right for the actual drift?"""
    if archetype is None:
        return None
    if archetype == 'pre_bullish_run':
        return drift_5d_pct > 0
    if archetype == 'pre_bearish_fade':
        return drift_5d_pct < 0
    if archetype == 'pre_choppy':
        return abs(drift_5d_pct) > MIXED_HIT_THRESHOLD
    return None  # 'pre_quiet' or unknown


def run_backtest(min_nq: int) -> pd.DataFrame:
    """Walk forward, return DataFrame of predictions with hit flags."""
    log.info("Fetching earnings_reactions for pre-drift backtest…")
    all_rows = fetch_pre_drift_for_backtest()
    log.info("  loaded %d rows across %d tickers",
             len(all_rows), all_rows['ticker'].nunique())

    # Same baseline + liquidity proxies as backtest_playability so the
    # quintile boundaries are directly comparable.
    TYPICAL_DAILY_RETURN_PCT = 1.0
    OPT_VOL_PROXY = 10000.0

    predictions: list[dict] = []
    by_ticker = all_rows.groupby('ticker', sort=False)
    skipped_low_nq = 0
    skipped_quiet = 0

    for ticker, grp in by_ticker:
        grp_sorted = grp.sort_values('reported_date').reset_index(drop=True)
        for idx in range(len(grp_sorted)):
            row = grp_sorted.iloc[idx]
            past = grp_sorted.iloc[:idx]
            if len(past) < min_nq:
                skipped_low_nq += 1
                continue

            stats = _pre_drift_stats_from_past(past)
            if stats is None:
                continue

            archetype = classify_pre_drift_archetype(
                drift_magnitude_pct=stats['drift_magnitude_pct'],
                directional_drift_pct=stats['directional_drift_pct'],
                pre_dir_consistency=stats['pre_dir_consistency'],
                pre_reversal_rate=stats['pre_reversal_rate'],
            )
            if archetype == 'pre_quiet':
                skipped_quiet += 1
                continue

            score = compute_pre_drift_score(
                drift_magnitude_pct=stats['drift_magnitude_pct'],
                typical_daily_return_pct=TYPICAL_DAILY_RETURN_PCT,
                pre_dir_consistency=stats['pre_dir_consistency'],
                pre_reversal_rate=stats['pre_reversal_rate'],
                options_volume=OPT_VOL_PROXY,
            )

            actual_drift = float(row['drift_5d_pct'])
            hit = hit_for_archetype(archetype, actual_drift)

            predictions.append({
                'ticker': ticker,
                'reported_date': row['reported_date'],
                'archetype': archetype,
                'score': score,
                'actual_drift_5d_pct': actual_drift,
                'hit': hit,
            })

    log.info("  predictions=%d  skipped_low_nq=%d  skipped_quiet=%d",
             len(predictions), skipped_low_nq, skipped_quiet)
    return pd.DataFrame(predictions)


def write_report(df: pd.DataFrame, output: Path, min_nq: int) -> None:
    """Render the standard quintile + archetype tables.

    Wraps the report between BEGIN/END markers so a Cloud Run Job can
    sed/grep the result out of the execution logs.
    """
    if df.empty:
        log.warning("No predictions — nothing to report.")
        print("BEGIN_BACKTEST_REPORT")
        print("(no predictions — earnings_reactions has insufficient data)")
        print("END_BACKTEST_REPORT")
        return

    overall_hit = df['hit'].dropna().mean()
    lines: list[str] = []
    lines.append("# Pre-Drift Score Backtest — Walk-Forward Validation")
    lines.append(
        f"Walks forward through `earnings_reactions` ({len(df):,} predictions, "
        f"min_nq={min_nq}). For each prediction the score & archetype were "
        "computed using **only** past drift_5d rows for that ticker. The "
        "'hit' column is whether the archetype's directional call matched "
        "the actual drift_5d_pct outcome that quarter."
    )
    lines.append("## Overall")
    lines.append(f"- **Predictions made:** {len(df):,}")
    lines.append(f"- **Overall hit rate:** {overall_hit:.1%}")
    lines.append(
        "- **Random baseline:** ~50% (directional) / ~25% "
        f"(pre_choppy: |drift| > {MIXED_HIT_THRESHOLD:.1f}%)"
    )

    # By archetype
    lines.append("## Hit rate by archetype")
    lines.append("| Archetype | n | Hit rate | Avg score | Avg |drift| |")
    lines.append("|---|---:|---:|---:|---:|")
    arch_grouped = df.groupby('archetype').agg(
        n=('hit', 'size'),
        hit_rate=('hit', 'mean'),
        avg_score=('score', 'mean'),
        avg_abs_drift=('actual_drift_5d_pct', lambda s: s.abs().mean()),
    ).sort_values('hit_rate', ascending=False)
    for arch, row in arch_grouped.iterrows():
        lines.append(
            f"| {arch} | {int(row['n']):,} | {row['hit_rate']:.1%} | "
            f"{row['avg_score']:.2f} | {row['avg_abs_drift']:.2f}% |"
        )

    # By quintile
    lines.append("## Hit rate by score quintile")
    lines.append(
        "Higher quintile = higher computed pre_drift_score. If the formula "
        "works, Q5 hit rate should be meaningfully above Q1."
    )
    df_with_q = df.copy()
    df_with_q['quintile'] = pd.qcut(
        df_with_q['score'], q=5,
        labels=['Q1 (lowest)', 'Q2', 'Q3', 'Q4', 'Q5 (highest)'],
        duplicates='drop',
    )
    lines.append("| Quintile | n | Hit rate | Avg score | Avg |drift| |")
    lines.append("|---|---:|---:|---:|---:|")
    for q, grp in df_with_q.groupby('quintile', observed=True):
        lines.append(
            f"| {q} | {len(grp):,} | {grp['hit'].mean():.1%} | "
            f"{grp['score'].mean():.2f} | "
            f"{grp['actual_drift_5d_pct'].abs().mean():.2f}% |"
        )

    # Cross-table
    lines.append("## Hit rate by archetype × quintile")
    lines.append(
        "Cell values are hit rates. NaN = no predictions in that bucket."
    )
    pivot = df_with_q.pivot_table(
        index='archetype', columns='quintile', values='hit', aggfunc='mean',
        observed=True,
    )
    header = "| archetype | " + " | ".join(str(c) for c in pivot.columns) + " |"
    sep = "|" + "|".join(["---"] * (len(pivot.columns) + 1)) + "|"
    lines.append(header)
    lines.append(sep)
    for arch in pivot.index:
        cells = []
        for col in pivot.columns:
            v = pivot.loc[arch, col]
            cells.append(f"{v:.1%}" if pd.notna(v) else 'NaN')
        lines.append(f"| {arch} | " + " | ".join(cells) + " |")

    # Calibration hint for lib/earnings_reactions.py
    lines.append("## Calibration — proposed _PRE_DRIFT_QUINTILE_BOUNDARIES")
    bounds = df_with_q.groupby('quintile', observed=True)['score'].mean()
    cuts = []
    for a, b in zip(bounds.iloc[:-1], bounds.iloc[1:]):
        cuts.append((a + b) / 2)
    lines.append(f"```python")
    lines.append(f"_PRE_DRIFT_QUINTILE_BOUNDARIES = "
                 f"({', '.join(f'{c:.1f}' for c in cuts)})")
    lines.append(f"```")
    lines.append(
        "_Midpoints between adjacent quintile-avg scores. Paste into "
        "lib/earnings_reactions.py if Q1 → Q5 is monotonic._"
    )

    # Interpretation
    lines.append("## Interpretation")
    lines.append(
        "- Directional archetypes (`pre_bullish_run`, `pre_bearish_fade`) "
        "should beat the 50% baseline.\n"
        "- Q5 > Q1 (monotonic) = score formula has predictive power.\n"
        "- Q5 ≈ Q1 or inverted = redesign before shipping action tags."
    )

    # Stdout + file
    report = "\n".join(lines)
    print("BEGIN_BACKTEST_REPORT")
    print("=" * 70)
    print(report)
    print("=" * 70)
    print("END_BACKTEST_REPORT")
    output.write_text(report)
    log.info("Wrote %s", output)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--min-nq', type=int, default=12,
                   help='Minimum past quarters before scoring (default 12)')
    p.add_argument('--output', type=Path,
                   default=Path('BACKTEST_PRE_DRIFT_RESULTS.md'),
                   help='Markdown report path')
    args = p.parse_args()

    df = run_backtest(min_nq=args.min_nq)
    write_report(df, args.output, args.min_nq)


if __name__ == '__main__':
    main()
