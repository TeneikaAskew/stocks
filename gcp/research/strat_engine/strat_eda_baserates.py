"""Stage 2 — EDA — `strat_eda_baserates.py`.

Describes the labeled dataset BEFORE any modeling, so the model's accuracy
has a benchmark to beat (PRD §"How we know it works" / Stage 4 acceptance).

Outputs (per ticker × TF):
  - Base rate of each next_bar_type (the bar Stage 4 must beat by +5pp)
  - 1-bar transition matrix P(next | current)
  - 3-bar transition matrix P(next | prev2 -> prev1 -> current)
  - Per-class indicator distributions (mean/median/p25/p75 per next_bar_type)
  - Class balance + data quality summary

All to GCS under research/strat_engine/{ticker}_{tf}/eda_*.json.
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gcp.database import get_engine
from gcp.research.strat_engine.strat_config import (
    TICKERS, TIMEFRAMES, NUMERIC_FEATURES, LABEL_COL, LABEL_CLASSES,
    GCS_BUCKET_DEFAULT, GCS_PREFIX, gcs_model_prefix,
)
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset, base_rate
from google.cloud import storage as gcs
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)


def _upload(content: bytes, blob_path: str, ctype="application/json"):
    bucket_name = os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT)
    gcs.Client().bucket(bucket_name).blob(blob_path).upload_from_string(
        content, content_type=ctype)
    return f"gs://{bucket_name}/{blob_path}"


def compute_base_rate(df: pd.DataFrame) -> dict:
    """Class frequencies. This IS the benchmark Stage 4 must beat by +5pp."""
    br = base_rate(df[LABEL_COL])
    return {
        "counts": df[LABEL_COL].value_counts().reindex(LABEL_CLASSES, fill_value=0).to_dict(),
        "rates": {c: float(br[c]) for c in LABEL_CLASSES},
        "majority_class": br.idxmax(),
        "majority_rate": float(br.max()),
        "n_total": int(len(df)),
    }


def compute_transition_matrix(df: pd.DataFrame, condition_cols: list[str]) -> dict:
    """P(next_bar_type | condition_cols). Returns nested dict.

    condition_cols=['strat_candle'] -> P(next | current)
    condition_cols=['prev2_candle','prev1_candle','strat_candle'] -> 3-bar
    """
    valid = df.dropna(subset=condition_cols + [LABEL_COL]).copy()
    # group by condition tuple, count next types
    grp = (valid.groupby(condition_cols + [LABEL_COL])
                 .size()
                 .unstack(fill_value=0))
    # ensure all 4 classes present
    for c in LABEL_CLASSES:
        if c not in grp.columns:
            grp[c] = 0
    grp = grp[list(LABEL_CLASSES)]
    # row-normalize -> probabilities
    row_sum = grp.sum(axis=1).replace(0, np.nan)
    probs = grp.div(row_sum, axis=0).fillna(0.0)
    out = {}
    for idx, row in probs.iterrows():
        key = idx if isinstance(idx, str) else " -> ".join(str(x) for x in idx)
        n = int(grp.loc[idx].sum())
        if n < 10:  # min-sample filter for stat sanity
            continue
        out[key] = {
            "n": n,
            "probs": {c: float(row[c]) for c in LABEL_CLASSES},
            "top_class": str(row.idxmax()),
        }
    return out


def compute_indicator_distributions(df: pd.DataFrame) -> dict:
    """Per next_bar_type, distribution stats for each numeric feature.
    Stage 3 will use these as a sanity-cross-check against MI rankings."""
    out = {}
    for cls in LABEL_CLASSES:
        sub = df[df[LABEL_COL] == cls]
        if len(sub) < 30:
            continue
        cls_stats = {"n": int(len(sub)), "features": {}}
        for feat in NUMERIC_FEATURES:
            if feat not in sub.columns: continue
            col = sub[feat].dropna()
            if len(col) < 30: continue
            cls_stats["features"][feat] = {
                "mean": float(col.mean()),
                "median": float(col.median()),
                "p25": float(col.quantile(0.25)),
                "p75": float(col.quantile(0.75)),
                "std": float(col.std()),
            }
        out[cls] = cls_stats
    return out


def data_quality(df: pd.DataFrame) -> dict:
    """Null counts per feature, warmup detection, ts span."""
    null_counts = {}
    for feat in NUMERIC_FEATURES:
        if feat in df.columns:
            n_null = int(df[feat].isna().sum())
            if n_null > 0:
                null_counts[feat] = n_null
    return {
        "n_rows": int(len(df)),
        "ts_min": str(df["ts"].min()),
        "ts_max": str(df["ts"].max()),
        "bar_date_min": str(df["bar_date"].min()),
        "bar_date_max": str(df["bar_date"].max()),
        "null_features": null_counts,
    }


def run_eda(engine, ticker: str, tf: str, since: str | None = None,
            until: str | None = None) -> dict:
    log.info("=" * 70)
    log.info("Stage 2 EDA  ticker=%s  tf=%s  since=%s  until=%s",
             ticker, tf, since, until)
    log.info("=" * 70)

    df = load_labeled_dataset(engine, ticker, tf, since=since, until=until)

    br = compute_base_rate(df)
    log.info("Base rate (Stage 4 must beat by +5pp):")
    for cls in LABEL_CLASSES:
        log.info("  %-3s  %6.2f%%  (n=%d)",
                 cls, br["rates"][cls] * 100, br["counts"][cls])
    log.info("  majority class: %s  @  %.2f%%",
             br["majority_class"], br["majority_rate"] * 100)

    tm1 = compute_transition_matrix(df, ["strat_candle"])
    log.info("1-bar transition matrix P(next | current):")
    for curr, row in tm1.items():
        log.info("  curr=%-3s  n=%-6d  ->  %s",
                 curr, row["n"],
                 "  ".join(f"{c}:{row['probs'][c]:.2%}" for c in LABEL_CLASSES))

    tm3 = compute_transition_matrix(
        df, ["prev2_candle", "prev1_candle", "strat_candle"])
    log.info("3-bar transition matrix: %d sequences with n>=10", len(tm3))
    # top-5 by n
    top5 = sorted(tm3.items(), key=lambda kv: kv[1]["n"], reverse=True)[:5]
    for seq, row in top5:
        log.info("  %s  n=%-5d  ->  %s",
                 seq, row["n"],
                 "  ".join(f"{c}:{row['probs'][c]:.2%}" for c in LABEL_CLASSES))

    ind_dist = compute_indicator_distributions(df)
    log.info("Indicator distributions computed for %d classes", len(ind_dist))

    dq = data_quality(df)
    log.info("Data quality: n=%d  span=%s..%s  features-with-nulls=%d",
             dq["n_rows"], dq["bar_date_min"], dq["bar_date_max"],
             len(dq["null_features"]))

    result = {
        "ticker": ticker, "tf": tf,
        "since": since, "until": until,
        "base_rate": br,
        "transition_1bar": tm1,
        "transition_3bar": tm3,
        "indicator_distributions": ind_dist,
        "data_quality": dq,
        "computed_at": pd.Timestamp.utcnow().isoformat(),
    }

    blob = f"{gcs_model_prefix(ticker, tf)}/eda_{int(time.time())}.json"
    uri = _upload(json.dumps(result, indent=2, default=str).encode(), blob)
    log.info("saved: %s", uri)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--since", default=None,
                   help="YYYY-MM-DD inclusive (default: full history)")
    p.add_argument("--until", default=None,
                   help="YYYY-MM-DD exclusive (default: now)")
    args = p.parse_args()
    engine = get_engine()
    run_eda(engine, args.ticker, args.tf, since=args.since, until=args.until)


if __name__ == "__main__":
    main()
