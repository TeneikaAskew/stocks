#!/usr/bin/env python3
"""
Walk-forward backtest of the playability_score formula.

For each (ticker, fiscal_date_ending) row in earnings_reactions, we:
  1. As of just-before this report, compute playability_score + archetype
     using ONLY past rows for the same ticker (reported_date < this_row).
  2. Note the actual outcome at this row: reaction_gap_pct, is_reversal_5d.
  3. Score the archetype's directional prediction against the actual:
       bullish_trend  hit if reaction_gap_pct > 0
       bearish_trend  hit if reaction_gap_pct < 0
       reversal_play  hit if is_reversal_5d = True
       mixed          hit if |reaction_gap_pct| > MIXED_HIT_THRESHOLD
       quiet          skipped (no prediction)
  4. Bucket by score quintile + archetype, aggregate hit rate.

Output: BACKTEST_PLAYABILITY_RESULTS.md with quintile + archetype tables.

Usage:
    python -m scripts.backtest_playability
    python -m scripts.backtest_playability --min-nq 12
    python -m scripts.backtest_playability --output BACKTEST.md
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcp.database import query_to_dataframe
from lib.earnings_reactions import (
    compute_playability_score,
    classify_archetype,
)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)


# Threshold for the "mixed" archetype hit definition: actual move > this means
# the "big move" call was right. Same scale as reaction_gap_pct (percent).
MIXED_HIT_THRESHOLD = 3.0


def fetch_reactions_for_backtest(min_nq: int = 12) -> pd.DataFrame:
    """Pull all earnings_reactions sorted by (ticker, reported_date)."""
    sql = """
        SELECT ticker, reported_date, fiscal_date_ending,
               reaction_gap_pct,
               direction_consistent_5d,
               is_reversal_5d,
               sustain_5d_pct
        FROM earnings_reactions
        WHERE reaction_gap_pct IS NOT NULL
          AND reported_date IS NOT NULL
        ORDER BY ticker, reported_date
    """
    df = query_to_dataframe(sql)
    return df


def _reactions_stats_from_past(past: pd.DataFrame) -> dict | None:
    """Compute archetype/score inputs from a ticker's PAST reaction rows.

    Mirrors lib.earnings_reactions.query_reaction_stats but in-memory,
    walk-forward — only uses rows strictly before the target reported_date.
    """
    if past.empty:
        return None
    gaps = past['reaction_gap_pct'].dropna()
    if gaps.empty:
        return None
    n_q = len(past)
    move_magnitude_pct = gaps.abs().mean()
    directional_bias_pct = gaps.mean()
    dir_consistency = past['direction_consistent_5d'].mean()  # bool → 0..1
    reversal_rate = past['is_reversal_5d'].mean()
    return {
        'n_q': n_q,
        'move_magnitude_pct': float(move_magnitude_pct),
        'directional_bias_pct': float(directional_bias_pct),
        'dir_consistency': float(dir_consistency) if pd.notna(dir_consistency) else None,
        'reversal_rate':   float(reversal_rate)   if pd.notna(reversal_rate)   else None,
    }


def hit_for_archetype(archetype: str | None,
                      reaction_gap_pct: float,
                      is_reversal_5d: bool | None) -> bool | None:
    """Was this archetype's directional prediction correct for the actual?

    Returns None when no prediction is made (archetype='quiet' or None).
    """
    if archetype is None:
        return None
    if archetype == 'bullish_trend':
        return reaction_gap_pct > 0
    if archetype == 'bearish_trend':
        return reaction_gap_pct < 0
    if archetype == 'reversal_play':
        return bool(is_reversal_5d) if is_reversal_5d is not None else None
    if archetype == 'mixed':
        return abs(reaction_gap_pct) > MIXED_HIT_THRESHOLD
    return None  # 'quiet' or unknown


def run_backtest(min_nq: int) -> pd.DataFrame:
    """Walk forward, return DataFrame of predictions with hit flags."""
    log.info("Fetching earnings_reactions for backtest…")
    all_reactions = fetch_reactions_for_backtest()
    log.info("  loaded %d rows across %d tickers",
             len(all_reactions), all_reactions['ticker'].nunique())

    # Typical daily return baseline — used by compute_playability_score's
    # move_magnitude_norm. We don't have per-ticker per-date typical
    # daily return at hand here, so we use a constant proxy (median
    # daily return on a broad index). The score's *relative* ordering
    # is preserved as long as this is consistent across rows.
    TYPICAL_DAILY_RETURN_PCT = 1.0

    predictions: list[dict] = []
    by_ticker = all_reactions.groupby('ticker', sort=False)
    n_tickers = all_reactions['ticker'].nunique()
    skipped_low_nq = 0
    skipped_quiet = 0

    for i, (ticker, grp) in enumerate(by_ticker, 1):
        # Sort by reported_date asc for walk-forward
        grp_sorted = grp.sort_values('reported_date').reset_index(drop=True)
        for idx in range(len(grp_sorted)):
            row = grp_sorted.iloc[idx]
            past = grp_sorted.iloc[:idx]  # strictly before
            if len(past) < min_nq:
                skipped_low_nq += 1
                continue

            stats = _reactions_stats_from_past(past)
            if stats is None:
                continue

            archetype = classify_archetype(
                move_magnitude_pct=stats['move_magnitude_pct'],
                directional_bias_pct=stats['directional_bias_pct'],
                dir_consistency=stats['dir_consistency'],
                reversal_rate=stats['reversal_rate'],
            )
            if archetype == 'quiet':
                skipped_quiet += 1
                continue

            # options_volume is unknown for this walk-forward (we don't
            # have it at-time on the historical row). Use a constant
            # 10000 as a proxy — preserves relative ordering across
            # rows since log(opt_vol + 1) scales the same.
            score = compute_playability_score(
                move_magnitude_pct=stats['move_magnitude_pct'],
                typical_daily_return_pct=TYPICAL_DAILY_RETURN_PCT,
                dir_consistency=stats['dir_consistency'],
                reversal_rate=stats['reversal_rate'],
                options_volume=10000.0,
            )

            actual_gap = float(row['reaction_gap_pct'])
            actual_reversal = (
                bool(row['is_reversal_5d'])
                if pd.notna(row['is_reversal_5d']) else None
            )
            hit = hit_for_archetype(archetype, actual_gap, actual_reversal)

            predictions.append({
                'ticker': ticker,
                'reported_date': row['reported_date'],
                'archetype': archetype,
                'score': score,
                'nQ_past': len(past),
                'move_mag_pct': stats['move_magnitude_pct'],
                'dir_consistency': stats['dir_consistency'],
                'reversal_rate': stats['reversal_rate'],
                'actual_gap_pct': actual_gap,
                'actual_reversal_5d': actual_reversal,
                'hit': hit,
            })

        if i % 100 == 0:
            log.info("  %d/%d tickers processed; %d predictions, %d skipped (low_nq=%d, quiet=%d)",
                     i, n_tickers, len(predictions), skipped_low_nq + skipped_quiet,
                     skipped_low_nq, skipped_quiet)

    log.info("Done: %d predictions; skipped %d low_nq, %d quiet",
             len(predictions), skipped_low_nq, skipped_quiet)
    return pd.DataFrame(predictions)


def write_report(df: pd.DataFrame, output: Path, min_nq: int) -> None:
    """Write BACKTEST_PLAYABILITY_RESULTS.md from predictions DataFrame."""
    if df.empty:
        output.write_text("# Backtest: no predictions produced\n")
        return

    # Drop rows where hit is None (no prediction made)
    df = df.dropna(subset=['hit']).copy()
    df['hit'] = df['hit'].astype(bool)
    df = df.dropna(subset=['score'])  # quiet rows already dropped above
    df['score'] = df['score'].astype(float)

    total = len(df)
    overall_hit_rate = df['hit'].mean()

    # By archetype
    archetype_table = (
        df.groupby('archetype', sort=False)
        .agg(n=('hit', 'count'),
             hit_rate=('hit', 'mean'),
             avg_score=('score', 'mean'),
             avg_actual_move=('actual_gap_pct', lambda s: s.abs().mean()))
        .sort_values('hit_rate', ascending=False)
        .reset_index()
    )

    # By score quintile
    df['quintile'] = pd.qcut(df['score'], q=5, labels=['Q1 (lowest)', 'Q2', 'Q3', 'Q4', 'Q5 (highest)'])
    quintile_table = (
        df.groupby('quintile', observed=True)
        .agg(n=('hit', 'count'),
             hit_rate=('hit', 'mean'),
             avg_score=('score', 'mean'),
             avg_actual_move=('actual_gap_pct', lambda s: s.abs().mean()))
        .reset_index()
    )

    # By archetype × quintile (the headline table)
    cross_table = (
        df.groupby(['archetype', 'quintile'], observed=True)
        .agg(n=('hit', 'count'), hit_rate=('hit', 'mean'))
        .reset_index()
    )
    pivot = cross_table.pivot(index='archetype', columns='quintile', values='hit_rate')

    md_lines = []
    md_lines.append("# Playability Score Backtest — Walk-Forward Validation\n")
    md_lines.append(f"Walks forward through `earnings_reactions` ({total:,} predictions, ")
    md_lines.append(f"min_nq={min_nq}). For each prediction the score & archetype were ")
    md_lines.append("computed using **only** past reaction rows for that ticker. The ")
    md_lines.append("'hit' column is whether the archetype's directional call matched the ")
    md_lines.append("actual outcome on that earnings event.\n\n")

    md_lines.append("## Overall\n")
    md_lines.append(f"- **Predictions made:** {total:,}\n")
    md_lines.append(f"- **Overall hit rate:** {overall_hit_rate:.1%}\n")
    md_lines.append(f"- **Random baseline:** ~50% (directional) / ~25% (mixed: |move| > {MIXED_HIT_THRESHOLD}%)\n\n")

    md_lines.append("## Hit rate by archetype\n\n")
    md_lines.append("| Archetype | n | Hit rate | Avg score | Avg |move| |\n")
    md_lines.append("|---|---:|---:|---:|---:|\n")
    for _, row in archetype_table.iterrows():
        md_lines.append(
            f"| {row['archetype']} | {row['n']:,} | {row['hit_rate']:.1%} | "
            f"{row['avg_score']:.2f} | {row['avg_actual_move']:.2f}% |\n"
        )
    md_lines.append("\n")

    md_lines.append("## Hit rate by score quintile\n\n")
    md_lines.append("Higher quintile = higher computed playability_score. If the formula works, ")
    md_lines.append("Q5 hit rate should be meaningfully above Q1.\n\n")
    md_lines.append("| Quintile | n | Hit rate | Avg score | Avg |move| |\n")
    md_lines.append("|---|---:|---:|---:|---:|\n")
    for _, row in quintile_table.iterrows():
        md_lines.append(
            f"| {row['quintile']} | {row['n']:,} | {row['hit_rate']:.1%} | "
            f"{row['avg_score']:.2f} | {row['avg_actual_move']:.2f}% |\n"
        )
    md_lines.append("\n")

    md_lines.append("## Hit rate by archetype × score quintile\n\n")
    md_lines.append("Cell values are hit rates. NaN means no predictions in that bucket.\n\n")
    md_lines.append(pivot.to_markdown(floatfmt='.1%'))
    md_lines.append("\n\n")

    md_lines.append("## Interpretation\n")
    md_lines.append("- **Archetype hit rate > 50%** for directional types (bullish/bearish) ")
    md_lines.append("means the directional prediction beats coin flip.\n")
    md_lines.append("- **Archetype hit rate > MIXED_HIT_THRESHOLD baseline** for 'mixed' means ")
    md_lines.append(f"the score's identification of vol-rich names is meaningful.\n")
    md_lines.append("- **Q5 > Q1** in the quintile table = the score formula is producing ")
    md_lines.append("ordered predictions that translate to actual outcomes.\n")
    md_lines.append("- **Q5 ≈ Q1** = the formula isn't separating signal from noise; redesign needed.\n\n")

    output.write_text("".join(md_lines))
    log.info("Wrote %s (%d predictions, overall hit rate %.1f%%)",
             output, total, overall_hit_rate * 100)


def main():
    parser = argparse.ArgumentParser(
        description="Walk-forward backtest of the playability_score formula"
    )
    parser.add_argument('--min-nq', type=int, default=12,
                        help="Minimum quarters of past history required to "
                             "score a prediction (default: 12, matches brief).")
    parser.add_argument('--output', type=str, default='BACKTEST_PLAYABILITY_RESULTS.md',
                        help="Output report path (default: BACKTEST_PLAYABILITY_RESULTS.md)")
    args = parser.parse_args()

    output = Path(args.output)
    if not output.is_absolute():
        output = Path(__file__).resolve().parent.parent / output

    df = run_backtest(min_nq=args.min_nq)
    write_report(df, output, args.min_nq)
    print(f"\nReport written to: {output}\n")


if __name__ == '__main__':
    main()
