"""Stage 3b — Indicator-COMBINATION mining for next_bar_type.

The companion to Stage 3 (`strat_corr_indicators.py`), which ranks indicators
ONE AT A TIME by mutual information. Stage 3b answers the question single-feature
MI can't: which *combinations* of indicator states are jointly predictive of the
next Strat candle (1 / 2U / 2D / 3).

It reuses the shared, label-agnostic miner in `lib.combo_mining` — the SAME code
the general regime miner (Effort A) uses — so the combo math has one definition
(CLAUDE.md Rule 3.6). Out-of-sample by construction: rows up to `train_until`
are TRAIN (thresholds/medians/feature-ranking fit here); rows after are the TEST
holdout the combo hit-rates are measured on.

Output: ranked combos per class to GCS JSON (alongside the Stage 3 corr JSON).

    python -m gcp.research.strat_engine.strat_corr_combos --ticker IWM --tf 15m
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time

import pandas as pd

from gcp.database import get_engine
from gcp.research.strat_engine.strat_config import (
    TICKERS, TIMEFRAMES, LABEL_CLASSES, DEFAULT_TRAIN_UNTIL,
    GCS_BUCKET_DEFAULT, gcs_model_prefix,
)
from gcp.research.strat_engine.strat_dataset import (
    load_labeled_dataset, discover_numeric_features,
)
from google.cloud import storage as gcs
from lib.logging_config import setup_logging
from lib import combo_mining as cm

setup_logging()
log = logging.getLogger(__name__)


def _upload(content: bytes, blob_path: str, ctype="application/json"):
    bucket_name = os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT)
    gcs.Client().bucket(bucket_name).blob(blob_path).upload_from_string(
        content, content_type=ctype)
    return f"gs://{bucket_name}/{blob_path}"


def run_combos(engine, ticker: str, tf: str, train_until: str,
               *, min_support: int = 300, top_k: int = 12,
               max_order: int = 3) -> dict:
    """Mine interpretable combos per next_bar_type class, OOS at train_until."""
    log.info("=" * 70)
    log.info("Stage 3b COMBOS  ticker=%s  tf=%s  train_until=%s",
             ticker, tf, train_until)
    log.info("=" * 70)

    # Load the FULL labeled set (no `until`), then split at train_until so the
    # combo hit-rates are measured out-of-sample. `ts` is on the frame.
    df = load_labeled_dataset(engine, ticker, tf)
    if df.empty:
        raise RuntimeError(f"no labeled rows for {ticker} {tf}")
    cut = pd.Timestamp(train_until, tz="UTC")
    train_mask = (pd.to_datetime(df["ts"], utc=True) < cut).to_numpy()
    test_mask = ~train_mask
    if train_mask.sum() < 500 or test_mask.sum() < 200:
        raise RuntimeError(
            f"insufficient split for {ticker} {tf}: train={int(train_mask.sum())} "
            f"test={int(test_mask.sum())}")

    # Stationary feature whitelist out of the discovered numeric columns.
    feats = cm.stationary_feature_filter(discover_numeric_features(df))
    log.info("rows: train=%d test=%d  features=%d",
             int(train_mask.sum()), int(test_mask.sum()), len(feats))

    label = df[LABEL_COL]
    model = cm.model_lift(df, feats, label, train_mask, test_mask, "next_bar_type")
    log.info("model OOS acc=%.4f base=%.4f lift=%.3f×",
             model.oos_accuracy, model.base_rate, model.lift)

    combos_by_class = {}
    for cls in LABEL_CLASSES:
        y_bin = (label == cls).astype(int)
        top_feats = cm.select_top_features(df, feats, y_bin, train_mask, k=10,
                                           method="mutual_info")
        combos = cm.mine_combos(df, top_feats, label, cls, train_mask, test_mask,
                                max_order=max_order, min_support=min_support,
                                top_k=top_k)
        combos_by_class[cls] = [
            {"conditions": list(c.conditions), "hit_rate": c.hit_rate,
             "base_rate": c.base_rate, "lift": c.lift, "support": c.support,
             "train_support": c.train_support} for c in combos
        ]
        log.info("next=%s: %d combos (best lift %.2f×)", cls, len(combos),
                 combos[0].lift if combos else float("nan"))

    result = {
        "ticker": ticker, "tf": tf, "train_until": train_until,
        "stage": "3b_combos",
        "n_train": int(train_mask.sum()), "n_test": int(test_mask.sum()),
        "model": {"oos_accuracy": model.oos_accuracy, "base_rate": model.base_rate,
                  "lift": model.lift, "class_mix": model.class_mix,
                  "perm_importance": dict(list(model.perm_importance.items())[:15])},
        "combos": combos_by_class,
        "computed_at": pd.Timestamp.utcnow().isoformat(),
    }
    blob = f"{gcs_model_prefix(ticker, tf)}/combos_{int(time.time())}.json"
    uri = _upload(json.dumps(result, indent=2, default=str).encode(), blob)
    log.info("saved: %s", uri)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--train-until", default=DEFAULT_TRAIN_UNTIL)
    p.add_argument("--min-support", type=int, default=300)
    p.add_argument("--top-k", type=int, default=12)
    p.add_argument("--max-order", type=int, default=3)
    args = p.parse_args()
    engine = get_engine()
    run_combos(engine, args.ticker, args.tf, args.train_until,
               min_support=args.min_support, top_k=args.top_k,
               max_order=args.max_order)


if __name__ == "__main__":
    main()
