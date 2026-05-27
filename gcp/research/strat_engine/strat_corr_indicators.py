"""Stage 3 — Correlation — `strat_corr_indicators.py`.

Per next_bar_type (one-vs-rest), rank indicators by mutual information,
report the direction of the relationship (sign of point-biserial as a
linear sanity check), and produce indicator-value-vs-P(class) curves
(binned, with empirical class rate per bin).

This is the explainability layer the PRD says was missing from p7b: the
classifier outputs a probability, this layer says WHY.

Outputs:
  - Ranked driver list per class (DataFrame + JSON to GCS)
  - Binned curves per indicator x class (JSON, charts can be added later)
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
    TICKERS, TIMEFRAMES, LABEL_COL, LABEL_CLASSES,
    DEFAULT_TRAIN_UNTIL, GCS_BUCKET_DEFAULT, gcs_model_prefix,
)
from gcp.research.strat_engine.strat_dataset import (
    load_labeled_dataset, discover_numeric_features,
)
from google.cloud import storage as gcs
from lib.logging_config import setup_logging
from sklearn.feature_selection import mutual_info_classif
from scipy import stats as sps

setup_logging()
log = logging.getLogger(__name__)


def _upload(content: bytes, blob_path: str, ctype="application/json"):
    bucket_name = os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT)
    gcs.Client().bucket(bucket_name).blob(blob_path).upload_from_string(
        content, content_type=ctype)
    return f"gs://{bucket_name}/{blob_path}"


def rank_features_per_class(df: pd.DataFrame, target_class: str,
                             features: list[str]) -> pd.DataFrame:
    """One-vs-rest MI ranking + sign-of-correlation direction.

    Returns DataFrame: feature, mi, direction (+/-), abs_pointbiserial, rank.
    """
    y_binary = (df[LABEL_COL] == target_class).astype(int).values
    sub = df[features].copy()
    # MI requires no NaNs / infs. Median-fill, then final 0-fill for all-NaN
    # columns (e.g. a feature that's NaN for the full training window).
    sub = sub.replace([np.inf, -np.inf], np.nan)
    for c in features:
        if sub[c].isna().any():
            med = sub[c].median()
            sub[c] = sub[c].fillna(med if pd.notna(med) else 0.0)
    sub = sub.fillna(0.0).astype(float)

    mi = mutual_info_classif(sub.values, y_binary, random_state=42)

    # Direction via point-biserial correlation
    directions = []
    abs_pbs = []
    for i, feat in enumerate(features):
        x = sub[feat].values
        if x.std() < 1e-9:
            directions.append("flat")
            abs_pbs.append(0.0)
            continue
        try:
            r, _ = sps.pointbiserialr(y_binary, x)
            directions.append("+" if r > 0 else "-")
            abs_pbs.append(abs(float(r)))
        except Exception:
            directions.append("?")
            abs_pbs.append(0.0)

    out = pd.DataFrame({
        "feature": features,
        "mi": mi,
        "direction": directions,
        "abs_pointbiserial": abs_pbs,
    }).sort_values("mi", ascending=False).reset_index(drop=True)
    out["rank"] = np.arange(1, len(out) + 1)
    out["target_class"] = target_class
    return out


def binned_curve(df: pd.DataFrame, feature: str, target_class: str,
                 n_bins: int = 10) -> dict:
    """For one feature, bin into n_bins by quantile and report empirical
    P(target_class) per bin."""
    sub = df[[feature, LABEL_COL]].dropna()
    if len(sub) < 100:
        return {}
    try:
        sub["bin"] = pd.qcut(sub[feature], q=n_bins, labels=False, duplicates="drop")
    except Exception:
        return {}
    sub["is_target"] = (sub[LABEL_COL] == target_class).astype(int)
    grp = sub.groupby("bin").agg(
        n=("is_target", "size"),
        bin_low=(feature, "min"),
        bin_high=(feature, "max"),
        p_target=("is_target", "mean"),
    ).reset_index()
    return {
        "feature": feature,
        "target_class": target_class,
        "bins": grp.to_dict(orient="records"),
    }


def run_corr(engine, ticker: str, tf: str, train_until: str,
             top_n_curves: int = 5) -> dict:
    log.info("=" * 70)
    log.info("Stage 3 CORR  ticker=%s  tf=%s  train_until=%s",
             ticker, tf, train_until)
    log.info("=" * 70)

    # TRAIN-only data (avoid OOS leakage in ranking)
    df = load_labeled_dataset(engine, ticker, tf, until=train_until)
    feats = discover_numeric_features(df)
    log.info("training rows: %d  features: %d  (includes ORB/levels/order_blocks "
             "from strat_features_levels_%s)", len(df), len(feats), tf)

    rankings = {}
    curves = {}
    for cls in LABEL_CLASSES:
        ranked = rank_features_per_class(df, cls, feats)
        rankings[cls] = ranked.to_dict(orient="records")
        log.info("Top-10 drivers of next_bar_type=%s:", cls)
        for _, r in ranked.head(10).iterrows():
            log.info("  %2d  %-26s  MI=%.4f  dir=%s  |pbs|=%.3f",
                     int(r["rank"]), r["feature"], r["mi"],
                     r["direction"], r["abs_pointbiserial"])
        # Binned curves for the top-N drivers of this class
        cls_curves = []
        for _, r in ranked.head(top_n_curves).iterrows():
            c = binned_curve(df, r["feature"], cls, n_bins=10)
            if c:
                cls_curves.append(c)
        curves[cls] = cls_curves

    result = {
        "ticker": ticker, "tf": tf, "train_until": train_until,
        "n_train": int(len(df)),
        "rankings": rankings,
        "binned_curves": curves,
        "computed_at": pd.Timestamp.utcnow().isoformat(),
    }
    blob = f"{gcs_model_prefix(ticker, tf)}/corr_{int(time.time())}.json"
    uri = _upload(json.dumps(result, indent=2, default=str).encode(), blob)
    log.info("saved: %s", uri)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--train-until", default=DEFAULT_TRAIN_UNTIL)
    args = p.parse_args()
    engine = get_engine()
    run_corr(engine, args.ticker, args.tf, args.train_until)


if __name__ == "__main__":
    main()
