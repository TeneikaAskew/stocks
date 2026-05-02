"""Phase 1 follow-up — empirical timeframe heuristic from signal_metrics.

The placeholder `assign_timeframe_for_backfill` in lib/strategies/timeframe.py
was shipped with documented "approximate" defaults: high-vol+strong → 15m,
mean-rev → 30m, momentum → 15m, default → 30m. Phase 0.5 has now produced
a 91k-row signal_metrics dataset that lets us check those defaults
empirically — for every historical fire, which timeframe ACTUALLY
classified CLEAN_HIT, and what conditions correlate with that outcome?

This script:
  1. Loads signal_metrics joined with historical_signals.
  2. Splits 80/20 random (seed=42).
  3. Bucketize features (strategy, signal_strength, atr_5m_pct, entry_rsi)
     and build an empirical lookup table on the train set: per-bucket
     mode of `best_tf`.
  4. Apply the empirical heuristic to the holdout — for each row predict
     a timeframe, then check `cls_<predicted_tf>` against the actual
     classification.
  5. Compare against the placeholder heuristic's predictions on the same
     holdout — same metric (% of predictions that classify CLEAN_HIT).

Outputs to stdout:
  * Bucket-level lookup table (CSV-like)
  * Holdout clean-hit rate: empirical vs placeholder
  * Coverage breakdown — how many holdout rows had a bucket the train
    set didn't see (cold-start fallback)

NO heuristic changes in this PR. Output is the basis for a follow-up
PR that integrates the validated mapping into the production
`assign_timeframe_for_backfill`.

Usage:
    python -m scripts.analyze_timeframe_heuristic
    python -m scripts.analyze_timeframe_heuristic --holdout-pct 0.30 --seed 7
    python -m scripts.analyze_timeframe_heuristic --strategy momentum
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.strategies.timeframe import (  # noqa: E402
    HIGH_ATR_5M_PCT,
    STRONG_CONFIRMATION,
    assign_timeframe_for_backfill,
)

logger = logging.getLogger(__name__)


VALID_TFS: tuple[str, ...] = ("5m", "15m", "30m", "60m", "90m", "120m", "240m")


# ── Pure helpers (no I/O) ─────────────────────────────────────────────


@dataclass(frozen=True)
class Bucket:
    """The (strategy, signal_strength, atr_bucket, rsi_bucket) feature
    cell. Used as a dict key into the empirical lookup table —
    `frozen=True` synthesizes `__hash__` so the bucket is hashable.
    """
    strategy: str
    signal_strength: int
    atr_bucket: str    # 'high' | 'avg' | 'low' | 'unknown'
    rsi_bucket: str    # 'low' | 'mid' | 'high' | 'unknown'


def bucket_atr(atr_5m_pct: Optional[float]) -> str:
    """Bucketize ATR into 3 tiers + an unknown sentinel.

    Thresholds align with the live heuristic in lib/strategies/timeframe.py:
      * high:    atr_5m_pct >= HIGH_ATR_5M_PCT/100 (= 0.4%)
      * avg:     0.001 < atr_5m_pct < 0.004
      * low:     atr_5m_pct <= 0.001 (very quiet)
      * unknown: ATR not available
    """
    if atr_5m_pct is None or pd.isna(atr_5m_pct):
        return "unknown"
    a = float(atr_5m_pct)
    if a >= HIGH_ATR_5M_PCT / 100.0:
        return "high"
    if a <= 0.001:
        return "low"
    return "avg"


def bucket_rsi(rsi: Optional[float]) -> str:
    """Bucketize RSI into 3 zones + unknown.

    The strategy logic uses RSI 25-50 as the actionable zone for both
    CALL (oversold-recovery) and PUT (overbought-recovery, mirrored).
    Three bins line up with that:
      * low:     0..30  (deep oversold)
      * mid:     30..70 (the actionable zone)
      * high:    70..100 (deep overbought)
      * unknown: RSI not available
    """
    if rsi is None or pd.isna(rsi):
        return "unknown"
    r = float(rsi)
    if r < 30:
        return "low"
    if r > 70:
        return "high"
    return "mid"


def make_bucket(row: dict) -> Bucket:
    """Per-row feature bucket. Used by both train and predict paths."""
    return Bucket(
        strategy=str(row.get("strategy") or "unknown"),
        signal_strength=int(row.get("signal_strength") or 0),
        atr_bucket=bucket_atr(row.get("atr_5m_pct")),
        rsi_bucket=bucket_rsi(row.get("entry_rsi")),
    )


def build_lookup_table(
    train_df: pd.DataFrame,
    target: str = "mode_best_tf",
) -> dict[Bucket, str]:
    """Empirical mapping bucket → predicted TF on the train set.

    Three target methodologies:

    * 'mode_best_tf' (DEFAULT, naive): per-bucket mode of best_tf.
      Found in #218 to underperform the placeholder by 12.6pp because
      best_tf is biased toward shortest clean TF (5m everywhere).

    * 'max_clean_rate': per-bucket pick the TF that has the highest
      CLEAN_HIT rate ACROSS ALL ROWS IN THE BUCKET. Methodologically
      correct: optimizes the metric we evaluate on.

    * 'max_clean_rate_min_15m': same as max_clean_rate but EXCLUDES
      5m from the candidate set. The 5m bucket has structurally
      noisy returns and the live monitor's exit logic isn't built
      around 5m holds. Restricting to 15m+ floors the predictions
      at a tradeable horizon.

    Rows where best_tf is NULL (no timeframe classified CLEAN_HIT)
    naturally have low cls_<tf> across all timeframes — the
    max_clean_rate target picks the LEAST BAD tf for those buckets.
    """
    lookup: dict[Bucket, str] = {}
    train = train_df.copy()
    train["_bucket"] = train.apply(lambda r: make_bucket(r.to_dict()), axis=1)

    if target == "mode_best_tf":
        train["_mode_target"] = train["best_tf"].fillna("none")
        for bucket, group in train.groupby("_bucket", sort=False):
            counts = Counter(group["_mode_target"])
            ranked = [tf for tf, _ in counts.most_common() if tf != "none"]
            lookup[bucket] = ranked[0] if ranked else "30m"
        return lookup

    if target in ("max_clean_rate", "max_clean_rate_min_15m"):
        candidate_tfs = (
            VALID_TFS if target == "max_clean_rate"
            else tuple(t for t in VALID_TFS if t != "5m")
        )
        for bucket, group in train.groupby("_bucket", sort=False):
            best_tf_pick = "30m"
            best_rate = -1.0
            for tf in candidate_tfs:
                col = f"cls_{tf}"
                if col not in group.columns:
                    continue
                # Exclude INSUFFICIENT_DATA from the denominator —
                # consistent with how evaluate_predictions scores
                eligible = group[col].notna() & (group[col] != "INSUFFICIENT_DATA")
                n = int(eligible.sum())
                if n == 0:
                    continue
                clean = int((group.loc[eligible, col] == "CLEAN_HIT").sum())
                rate = clean / n
                if rate > best_rate:
                    best_rate = rate
                    best_tf_pick = tf
            lookup[bucket] = best_tf_pick
        return lookup

    raise ValueError(
        f"unknown target {target!r}; expected one of "
        "{'mode_best_tf', 'max_clean_rate', 'max_clean_rate_min_15m'}"
    )


def predict_with_lookup(row: dict, lookup: dict[Bucket, str],
                        cold_start_default: str = "30m") -> str:
    """Apply the empirical lookup table to one row.

    Cold-start fallback: a holdout row whose bucket the train set didn't
    see returns the cold_start_default (30m by design — it's the most
    common bucket overall in the placeholder).
    """
    bucket = make_bucket(row)
    return lookup.get(bucket, cold_start_default)


def predict_with_placeholder(row: dict) -> str:
    """The current placeholder heuristic — for direct comparison."""
    tag, _ = assign_timeframe_for_backfill(
        strategy=row.get("strategy"),
        signal_strength=int(row.get("signal_strength") or 0),
        atr_5m_pct=row.get("atr_5m_pct"),
    )
    return tag


def evaluate_predictions(holdout: pd.DataFrame, predicted_tfs: list[str]) -> dict:
    """For each holdout row, check whether the predicted timeframe
    actually classified CLEAN_HIT (using the cls_<tf> column).

    Returns aggregate metrics:
      * n_total: holdout size
      * n_clean: predictions where cls_<tf> == 'CLEAN_HIT'
      * n_insufficient: predictions where cls_<tf> is INSUFFICIENT_DATA
        (the predicted tf's window hadn't closed yet — this rarely
        happens for status='final' rows but is possible for '240m'
        on edge-case end-of-day fires)
      * clean_rate_pct: 100 * n_clean / (n_total - n_insufficient)
    """
    n_total = len(holdout)
    n_clean = 0
    n_insufficient = 0
    n_wrong = 0
    n_noise = 0
    n_mixed = 0
    tf_counts: Counter = Counter()

    for (_, row), tf in zip(holdout.iterrows(), predicted_tfs):
        col = f"cls_{tf}"
        cls = row.get(col)
        tf_counts[tf] += 1
        if cls is None or pd.isna(cls) or cls == "INSUFFICIENT_DATA":
            n_insufficient += 1
        elif cls == "CLEAN_HIT":
            n_clean += 1
        elif cls == "WRONG_DIRECTION":
            n_wrong += 1
        elif cls == "NOISE":
            n_noise += 1
        elif cls == "MIXED":
            n_mixed += 1

    denom = n_total - n_insufficient
    clean_rate = (100.0 * n_clean / denom) if denom > 0 else 0.0
    return {
        "n_total":        n_total,
        "n_clean":        n_clean,
        "n_wrong":        n_wrong,
        "n_noise":        n_noise,
        "n_mixed":        n_mixed,
        "n_insufficient": n_insufficient,
        "clean_rate_pct": clean_rate,
        "tf_distribution": dict(tf_counts),
    }


# ── DB I/O ────────────────────────────────────────────────────────────


def load_joined(engine, strategy_filter: Optional[str] = None) -> pd.DataFrame:
    """Pull historical_signals × signal_metrics on the composite key."""
    from sqlalchemy import text

    where = ["m.status = 'final'"]
    params: dict = {}
    if strategy_filter:
        where.append("h.strategy = :strategy")
        params["strategy"] = strategy_filter

    sql = text(f"""
        SELECT h.ticker,
               h.entry_time,
               h.strategy,
               h.signal_strength,
               h.entry_rsi,
               m.atr_5m_pct,
               m.best_tf,
               m.cls_5m, m.cls_15m, m.cls_30m, m.cls_60m,
               m.cls_90m, m.cls_120m, m.cls_240m
          FROM historical_signals h
          JOIN signal_metrics m
            ON m.ticker = h.ticker
           AND m.entry_time = h.entry_time
           AND m.strategy = h.strategy
         WHERE {' AND '.join(where)}
    """)
    return pd.read_sql(sql, engine, params=params)


# ── CLI orchestrator ──────────────────────────────────────────────────


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--holdout-pct", type=float, default=0.20,
                   help="Holdout fraction (default 0.20 = 80/20 split)")
    p.add_argument("--seed", type=int, default=42,
                   help="Random seed for the split (default 42)")
    p.add_argument("--strategy", default=None,
                   choices=("momentum", "mean_reversion"),
                   help="Filter to one strategy (default: both)")
    p.add_argument("--top-buckets", type=int, default=20,
                   help="How many of the most-populated buckets to print (default 20)")
    p.add_argument(
        "--target", default="mode_best_tf",
        choices=("mode_best_tf", "max_clean_rate", "max_clean_rate_min_15m"),
        help=(
            "Lookup-table target methodology: "
            "'mode_best_tf' (per-bucket mode of best_tf — naive, biased to 5m), "
            "'max_clean_rate' (per-bucket pick TF with highest clean-hit rate), "
            "'max_clean_rate_min_15m' (same but excludes 5m to floor at "
            "tradeable horizon). Default is mode_best_tf for backward compat."
        ),
    )
    return p.parse_args(argv)


def split_train_holdout(df: pd.DataFrame, holdout_pct: float,
                         seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Random 80/20 split with a fixed seed."""
    rng = np.random.default_rng(seed)
    n = len(df)
    idx = np.arange(n)
    rng.shuffle(idx)
    n_holdout = int(n * holdout_pct)
    holdout_idx = idx[:n_holdout]
    train_idx = idx[n_holdout:]
    return df.iloc[train_idx].reset_index(drop=True), df.iloc[holdout_idx].reset_index(drop=True)


def print_lookup_table(lookup: dict[Bucket, str], train: pd.DataFrame,
                       limit: int = 20) -> None:
    """Print the most-populated buckets with their empirical predictions
    and the placeholder heuristic's prediction for comparison."""
    bucket_counts: Counter = Counter()
    train_with_buckets = train.copy()
    train_with_buckets["_bucket"] = train.apply(
        lambda r: make_bucket(r.to_dict()), axis=1
    )
    for b in train_with_buckets["_bucket"]:
        bucket_counts[b] += 1

    print()
    print("=" * 90)
    print(f"EMPIRICAL LOOKUP TABLE — top {limit} most-populated buckets")
    print("=" * 90)
    print(f"{'strategy':<16}{'sig_str':<8}{'atr':<8}{'rsi':<8}"
          f"{'n':<8}{'empirical':<12}{'placeholder':<12}{'agree':<6}")
    for bucket, n in bucket_counts.most_common(limit):
        emp_tf = lookup[bucket]
        # Build a synthetic row to ask the placeholder
        atr_for_plc = (HIGH_ATR_5M_PCT / 100.0 + 0.001 if bucket.atr_bucket == "high"
                       else 0.0005 if bucket.atr_bucket == "low"
                       else 0.002)
        plc_tf = predict_with_placeholder({
            "strategy":        bucket.strategy,
            "signal_strength": bucket.signal_strength,
            "atr_5m_pct":      atr_for_plc,
        })
        agree = "yes" if emp_tf == plc_tf else "no"
        print(f"{bucket.strategy:<16}{bucket.signal_strength:<8}"
              f"{bucket.atr_bucket:<8}{bucket.rsi_bucket:<8}"
              f"{n:<8}{emp_tf:<12}{plc_tf:<12}{agree:<6}")


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    args = parse_args(argv)

    from gcp.database import get_engine
    engine = get_engine()

    logger.info("loading joined signal_metrics × historical_signals (strategy=%s)",
                args.strategy or "all")
    df = load_joined(engine, strategy_filter=args.strategy)
    logger.info("loaded %d joined rows", len(df))
    if df.empty:
        logger.error("no rows to analyze — has the Phase 0.5 backfill run?")
        return 2

    # Coverage diagnostic
    logger.info("rows with best_tf set: %d (%.1f%%)",
                df["best_tf"].notna().sum(),
                100.0 * df["best_tf"].notna().sum() / len(df))

    train, holdout = split_train_holdout(df, args.holdout_pct, args.seed)
    logger.info("train=%d holdout=%d", len(train), len(holdout))

    logger.info("building lookup with target=%s", args.target)
    lookup = build_lookup_table(train, target=args.target)
    print_lookup_table(lookup, train, limit=args.top_buckets)

    # Predict + evaluate
    holdout_records = holdout.to_dict(orient="records")

    pred_emp = [predict_with_lookup(r, lookup) for r in holdout_records]
    pred_plc = [predict_with_placeholder(r) for r in holdout_records]

    metrics_emp = evaluate_predictions(holdout, pred_emp)
    metrics_plc = evaluate_predictions(holdout, pred_plc)

    n_cold = sum(1 for r in holdout_records
                 if make_bucket(r) not in lookup)

    print()
    print("=" * 90)
    print("HOLDOUT EVALUATION — clean-hit rate at the predicted timeframe")
    print("=" * 90)
    print(f"Holdout size: {metrics_emp['n_total']:,}")
    print(f"Cold-start (bucket unseen in train): {n_cold} "
          f"({100.0 * n_cold / metrics_emp['n_total']:.1f}%)")
    print()
    print(f"{'metric':<28}{'empirical':<14}{'placeholder':<14}{'delta':<10}")
    for k in ("n_clean", "n_wrong", "n_noise", "n_mixed", "n_insufficient"):
        print(f"{k:<28}{metrics_emp[k]:<14,}{metrics_plc[k]:<14,}"
              f"{metrics_emp[k] - metrics_plc[k]:+d}")
    delta = metrics_emp["clean_rate_pct"] - metrics_plc["clean_rate_pct"]
    print(f"{'clean_rate_pct':<28}{metrics_emp['clean_rate_pct']:<14.2f}"
          f"{metrics_plc['clean_rate_pct']:<14.2f}{delta:+.2f}")

    print()
    print("Empirical TF distribution:", metrics_emp["tf_distribution"])
    print("Placeholder TF distribution:", metrics_plc["tf_distribution"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
