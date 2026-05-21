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
    """Pull all earnings_reactions sorted by (ticker, reported_date).

    Pulls the full multi-horizon return ladder so the calibration sweep
    can compute dollar P&L on each prediction (1d / 3d / 5d / 10d holds)
    in addition to the hit/miss ranking metric.
    """
    sql = """
        SELECT ticker, reported_date, fiscal_date_ending,
               reaction_gap_pct,
               direction_consistent_5d,
               is_reversal_5d,
               sustain_3d_pct,
               sustain_5d_pct,
               sustain_10d_pct,
               reaction_max_run_pct,
               reaction_max_drawdown_pct
        FROM earnings_reactions
        WHERE reaction_gap_pct IS NOT NULL
          AND reported_date IS NOT NULL
        ORDER BY ticker, reported_date
    """
    df = query_to_dataframe(sql)
    return df


def _reactions_stats_from_past(
    past: pd.DataFrame, lookback: int | None = None,
) -> dict | None:
    """Compute archetype/score inputs from a ticker's PAST reaction rows.

    Mirrors lib.earnings_reactions.query_reaction_stats but in-memory,
    walk-forward — only uses rows strictly before the target reported_date.

    When `lookback` is given (> 0), only the most recent `lookback` past
    rows are used — a bounded window rather than all history. This is one
    of the two knobs the earnings calibration sweep tunes.
    """
    if past.empty:
        return None
    if lookback is not None and lookback > 0:
        past = past.tail(lookback)
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


def compute_quintile_spread(predictions: pd.DataFrame) -> dict:
    """Reduce a run_backtest() predictions frame to the calibration
    sweep's ranking metrics.

    Returns {n_predictions, overall_hit_rate, quintile_spread}, where
    quintile_spread is the hit-rate of the highest-score quintile minus
    the lowest. A high spread means the playability score orders
    earnings plays in a way that tracks real outcomes — the property
    the sweep maximises. Zeros on an empty/degenerate frame.
    """
    zero = {'n_predictions': 0, 'overall_hit_rate': 0.0, 'quintile_spread': 0.0}
    if predictions is None or predictions.empty:
        return zero
    df = predictions.dropna(subset=['hit', 'score']).copy()
    if df.empty:
        return zero
    df['hit'] = df['hit'].astype(bool)
    df['score'] = df['score'].astype(float)
    n = len(df)
    overall = float(df['hit'].mean())
    spread = 0.0
    if df['score'].nunique() >= 5:
        try:
            df['q'] = pd.qcut(df['score'], q=5, labels=False, duplicates='drop')
            by_q = df.groupby('q')['hit'].mean().sort_index()
            spread = float(by_q.iloc[-1] - by_q.iloc[0])
        except (ValueError, IndexError):
            spread = 0.0
    return {'n_predictions': n, 'overall_hit_rate': overall,
            'quintile_spread': spread}


# Dollar conversion: per_trade_pct (e.g. 3.4 means +3.4%) × $10 = $34
# per $1k notional. Centralised here so any rendering layer can do the
# same conversion without re-deriving the factor.
_DOLLARS_PER_PCT_PER_1K = 10.0

# Hold horizons evaluated for best_hold_horizon_days. 1 = day-of
# reaction (uses actual_gap_pct); 3/5/10 = sustain_*_pct.
_HOLD_HORIZONS_DAYS = (1, 3, 5, 10)


def _archetype_directional_return(archetype: str | None,
                                  actual_gap_pct: float | None,
                                  hold_return_pct: float | None) -> float | None:
    """Realised return of the archetype's directional bet for one hold.

    Sign convention: positive = the prediction made money.
      bullish_trend: long position over the hold horizon → +hold_return
      bearish_trend: short position over the hold horizon → -hold_return
      reversal_play: fade the initial gap; long if gap < 0, short if > 0
                     → -sign(actual_gap) × hold_return
      mixed / quiet / unknown: None (no single-direction stock trade).
    """
    if hold_return_pct is None or archetype is None:
        return None
    if archetype == 'bullish_trend':
        return float(hold_return_pct)
    if archetype == 'bearish_trend':
        return -float(hold_return_pct)
    if archetype == 'reversal_play':
        if actual_gap_pct is None or actual_gap_pct == 0:
            return None
        return -float(hold_return_pct) if actual_gap_pct > 0 else float(hold_return_pct)
    return None


def _summary_stats_pct(returns: pd.Series) -> dict:
    """Win/loss decomposition + payoff/expectancy/profit-factor/sharpe
    from a Series of per-trade percent returns. NaNs dropped. Empty
    input returns NaN-filled dict so downstream INSERT writes SQL NULL.
    Caller passes returns in chronological order for path-dependent
    max-drawdown to be meaningful.
    """
    s = returns.dropna()
    n = int(len(s))
    if n == 0:
        nan = float('nan')
        return {
            'n': 0, 'win_rate': nan, 'avg_win_pct': nan, 'avg_loss_pct': nan,
            'payoff_ratio': nan, 'expectancy_pct': nan, 'profit_factor': nan,
            'max_drawdown_pct': nan, 'sharpe_per_trade': nan,
        }
    wins = s[s > 0]
    losses = s[s < 0]
    win_rate = float(len(wins)) / n
    avg_win_pct  = float(wins.mean())   if len(wins)   > 0 else 0.0
    avg_loss_pct = float(losses.mean()) if len(losses) > 0 else 0.0  # negative
    payoff_ratio = (
        abs(avg_win_pct / avg_loss_pct) if avg_loss_pct < 0 else float('inf')
    )
    expectancy_pct = float(s.mean())
    gross_win  = float(wins.sum())   if len(wins)   > 0 else 0.0
    gross_loss = float(losses.sum()) if len(losses) > 0 else 0.0  # negative
    profit_factor = (
        gross_win / abs(gross_loss) if gross_loss < 0 else float('inf')
    )
    # Equity curve starts at 0 (no trades). Prepend 0 so the first
    # trade's drawdown is measured relative to initial equity, not to
    # itself (a series of all losses must report total cumulative loss
    # as the max drawdown, not zero).
    equity = pd.concat([pd.Series([0.0]), s.cumsum()], ignore_index=True)
    peak = equity.cummax()
    drawdown = equity - peak
    max_dd_pct = float(drawdown.min()) if len(drawdown) > 0 else 0.0
    std = float(s.std(ddof=1)) if n > 1 else 0.0
    sharpe = float(expectancy_pct / std) if std > 0 else 0.0
    return {
        'n': n,
        'win_rate': win_rate,
        'avg_win_pct': avg_win_pct,
        'avg_loss_pct': avg_loss_pct,
        'payoff_ratio': float(payoff_ratio),
        'expectancy_pct': expectancy_pct,
        'profit_factor': float(profit_factor),
        'max_drawdown_pct': max_dd_pct,
        'sharpe_per_trade': sharpe,
    }


def compute_dollar_metrics(predictions: pd.DataFrame) -> dict:
    """Dollar P&L attribution on top-quintile predictions.

    Restricts to the top-score quintile (Q5) and the directional
    archetypes (bullish_trend / bearish_trend / reversal_play) because
    those map to clean stock-only trade structures. Mixed and quiet rows
    are excluded — see _archetype_directional_return.

    For each of {1d, 3d, 5d, 10d} hold horizons computes win_rate,
    avg_win/loss, payoff_ratio, expectancy, profit_factor, max
    drawdown, and per-trade sharpe. Picks best_hold_horizon_days by
    payoff_ratio (ties broken by expectancy_pct), excluding horizons
    with n<50 or zero-loss (inf payoff) noise.

    Returns dict with keys for the 5d-hold canonical metrics plus
    best_hold_horizon_days + n_q5_directional. All values NaN-safe.
    """
    nan_safe = {
        'n_q5_directional': 0,
        'avg_win_pct': float('nan'),
        'avg_loss_pct': float('nan'),
        'payoff_ratio': float('nan'),
        'expectancy_pct': float('nan'),
        'expectancy_dollars_per_1k': float('nan'),
        'profit_factor': float('nan'),
        'max_drawdown_pct': float('nan'),
        'sharpe_per_trade': float('nan'),
        'best_hold_horizon_days': None,
    }
    if predictions is None or predictions.empty:
        return nan_safe
    df = predictions.dropna(subset=['score']).copy()
    if df.empty or df['score'].nunique() < 5:
        return nan_safe

    df['q'] = pd.qcut(df['score'], q=5, labels=False, duplicates='drop')
    q5 = df[df['q'] == df['q'].max()].copy()
    q5 = q5[q5['archetype'].isin(
        ['bullish_trend', 'bearish_trend', 'reversal_play'])]
    if q5.empty:
        return nan_safe
    q5 = q5.sort_values('reported_date').reset_index(drop=True)

    horizon_to_col = {
        1:  'actual_gap_pct',
        3:  'sustain_3d_pct',
        5:  'sustain_5d_pct',
        10: 'sustain_10d_pct',
    }
    per_horizon: dict[int, dict] = {}
    for h in _HOLD_HORIZONS_DAYS:
        col = horizon_to_col[h]
        if col not in q5.columns:
            continue
        returns = q5.apply(
            lambda r: _archetype_directional_return(
                r['archetype'], r.get('actual_gap_pct'), r.get(col)),
            axis=1,
        )
        per_horizon[h] = _summary_stats_pct(pd.Series(returns, dtype='float64'))

    if not per_horizon:
        return nan_safe

    eligible = {
        h: m for h, m in per_horizon.items()
        if m['n'] >= 50 and m['payoff_ratio'] != float('inf')
    }
    if eligible:
        best_h = max(
            eligible.keys(),
            key=lambda h: (eligible[h]['payoff_ratio'],
                           eligible[h]['expectancy_pct']),
        )
    else:
        best_h = max(per_horizon.keys(),
                     key=lambda h: per_horizon[h]['n'])

    # Canonical reported metrics: 5d hold (matches the existing
    # backtest's hit definition's time window).
    canon = per_horizon.get(5) or per_horizon[best_h]
    exp_pct = canon['expectancy_pct']
    exp_dollars = (
        exp_pct * _DOLLARS_PER_PCT_PER_1K
        if exp_pct == exp_pct  # not NaN
        else float('nan')
    )
    return {
        'n_q5_directional':        canon['n'],
        'avg_win_pct':             canon['avg_win_pct'],
        'avg_loss_pct':            canon['avg_loss_pct'],
        'payoff_ratio':            canon['payoff_ratio'],
        'expectancy_pct':          exp_pct,
        'expectancy_dollars_per_1k': exp_dollars,
        'profit_factor':           canon['profit_factor'],
        'max_drawdown_pct':        canon['max_drawdown_pct'],
        'sharpe_per_trade':        canon['sharpe_per_trade'],
        'best_hold_horizon_days':  int(best_h),
    }


def run_backtest(min_nq: int, lookback: int | None = None) -> pd.DataFrame:
    """Walk forward, return DataFrame of predictions with hit flags.

    `lookback` caps how many recent past quarters feed each prediction's
    stats (None / 0 = all history). It and `min_nq` are the two knobs
    the earnings calibration sweep tunes.
    """
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

            stats = _reactions_stats_from_past(past, lookback)
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

            def _f(col: str) -> float | None:
                v = row.get(col)
                return float(v) if pd.notna(v) else None

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
                # Multi-horizon return ladder for dollar P&L attribution.
                # 1d return = the close-to-close reaction itself; 3/5/10d
                # are cumulative returns from anchor through hold horizon.
                'sustain_3d_pct':  _f('sustain_3d_pct'),
                'sustain_5d_pct':  _f('sustain_5d_pct'),
                'sustain_10d_pct': _f('sustain_10d_pct'),
                'max_run_pct':     _f('reaction_max_run_pct'),
                'max_dd_pct':      _f('reaction_max_drawdown_pct'),
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
    # Render pivot table manually (avoids tabulate dep)
    col_headers = ["archetype"] + [str(c) for c in pivot.columns]
    md_lines.append("| " + " | ".join(col_headers) + " |\n")
    md_lines.append("|" + "|".join(["---"] * len(col_headers)) + "|\n")
    for archetype, row in pivot.iterrows():
        cells = [archetype]
        for col in pivot.columns:
            v = row[col]
            cells.append(f"{v:.1%}" if pd.notna(v) else "—")
        md_lines.append("| " + " | ".join(cells) + " |\n")
    md_lines.append("\n")

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
    # Also print to stdout so the report is captured in Cloud Logging
    # when run via Cloud Run Job (container fs is ephemeral).
    print("\n" + "=" * 70)
    print("BEGIN_BACKTEST_REPORT")
    print("=" * 70)
    print("".join(md_lines))
    print("=" * 70)
    print("END_BACKTEST_REPORT")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Walk-forward backtest of the playability_score formula"
    )
    parser.add_argument('--min-nq', type=int, default=12,
                        help="Minimum quarters of past history required to "
                             "score a prediction (default: 12, matches brief).")
    parser.add_argument('--lookback', type=int, default=0,
                        help="Cap recent past quarters per prediction "
                             "(0 = use all history; default: 0).")
    parser.add_argument('--output', type=str, default='BACKTEST_PLAYABILITY_RESULTS.md',
                        help="Output report path (default: BACKTEST_PLAYABILITY_RESULTS.md)")
    args = parser.parse_args()

    output = Path(args.output)
    if not output.is_absolute():
        output = Path(__file__).resolve().parent.parent / output

    df = run_backtest(min_nq=args.min_nq, lookback=(args.lookback or None))
    write_report(df, output, args.min_nq)
    print(f"\nReport written to: {output}\n")


if __name__ == '__main__':
    main()
