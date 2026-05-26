"""Per-class discrimination diagnostic — answers the gate the reviewer
flagged: "When the actual bar is class c, is P(c) systematically higher
than when it isn't?"

If YES (mean(P(c) | actual=c) >> mean(P(c) | actual≠c)) and the relationship
is calibrated, the model HAS information about class c — even if argmax
never picks it. The four-probability product surface works through the
probabilities, not through argmax. So a class can be "never argmax-predicted"
and still be a useful predictable signal.

If NO, the class carries no signal and forcing argmax coverage via
class_weight='balanced' would inject noise, not information.

Output:
  - Per-class lift: mean(P(c)|positive) / mean(P(c)|negative)
  - Per-class Brier score (lower = better calibrated 1-vs-rest probability)
  - Per-class one-vs-rest reliability bins (where does this class's
    probability go wrong?)
  - Class-conditioned ECE

Run:
  python -m gcp.research.strat_engine.strat_pred_per_class --ticker IWM --tf 15m
"""
from __future__ import annotations
import argparse
import json
import os
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gcp.database import get_engine
from gcp.research.strat_engine.strat_config import (
    GCS_BUCKET_DEFAULT, gcs_model_prefix, LABEL_CLASSES, LABEL_TO_IDX,
    DEFAULT_CALIBRATION,
)
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
from gcp.research.strat_engine.strat_pred_train import featurize
from google.cloud import storage as gcs
from lib.logging_config import setup_logging
from sklearn.metrics import brier_score_loss

setup_logging()
import logging
log = logging.getLogger(__name__)


def _load_model(ticker: str, tf: str, model_file: str = "model.pkl"):
    bucket = gcs.Client().bucket(os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT))
    prefix = gcs_model_prefix(ticker, tf)
    blob = bucket.blob(f"{prefix}/{model_file}")
    if not blob.exists():
        raise RuntimeError(f"No {model_file} at gs://.../{prefix}/")
    return pickle.loads(blob.download_as_bytes())


def _load_features(ticker: str, tf: str) -> list[str]:
    bucket = gcs.Client().bucket(os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT))
    prefix = gcs_model_prefix(ticker, tf)
    return bucket.blob(f"{prefix}/features.txt").download_as_bytes().decode().strip().split("\n")


def per_class_discrimination(engine, ticker: str, tf: str,
                              train_until: str = "2026-01-01",
                              model_file: str = "model.pkl") -> dict:
    log.info("=" * 70)
    log.info("PER-CLASS DISCRIMINATION  %s %s  model=%s", ticker, tf, model_file)
    log.info("=" * 70)

    model = _load_model(ticker, tf, model_file)
    features = _load_features(ticker, tf)
    log.info("loaded model + %d features", len(features))

    test_df = load_labeled_dataset(engine, ticker, tf, since=train_until)
    X = featurize(test_df)[0]
    for c in features:
        if c not in X.columns: X[c] = 0
    X = X[features].astype(np.float32)
    log.info("scored %d OOS bars", len(X))

    proba = model.predict_proba(X.values)
    # Map model.classes_ to LABEL_CLASSES order
    cls_to_col = {LABEL_CLASSES[c]: i for i, c in enumerate(model.classes_)}
    y_true = test_df["next_bar_type"].values

    results = {"ticker": ticker, "tf": tf, "n_test": int(len(X)), "per_class": {}}

    log.info("")
    log.info("%-4s %5s %8s %8s %5s %8s %8s",
             "class", "n_pos", "P(c)|+", "P(c)|-", "lift", "Brier", "max_diff")
    log.info("-" * 60)

    for cls in LABEL_CLASSES:
        col = cls_to_col.get(cls)
        if col is None:
            log.info("  %s — class not in model.classes_", cls)
            continue
        p_c = proba[:, col]
        actual_c = (y_true == cls).astype(int)
        n_pos = int(actual_c.sum())
        if n_pos == 0:
            log.info("  %s — no positive cases in OOS", cls)
            continue
        p_when_pos = float(p_c[actual_c == 1].mean())
        p_when_neg = float(p_c[actual_c == 0].mean())
        lift = p_when_pos / p_when_neg if p_when_neg > 0 else float("inf")
        brier = float(brier_score_loss(actual_c, p_c))
        # Per-class one-vs-rest reliability (10 bins)
        bin_edges = np.linspace(0, 1, 11)
        bins = np.digitize(p_c, bin_edges[1:-1])
        per_bin = []
        max_diff = 0.0
        for b in range(10):
            mask = bins == b
            n_in_bin = int(mask.sum())
            if n_in_bin < 5:
                per_bin.append({"bin": b, "n": n_in_bin})
                continue
            avg_conf = float(p_c[mask].mean())
            avg_acc = float(actual_c[mask].mean())
            diff = abs(avg_conf - avg_acc)
            max_diff = max(max_diff, diff)
            per_bin.append({
                "bin": b, "n": n_in_bin,
                "lo": float(bin_edges[b]), "hi": float(bin_edges[b+1]),
                "avg_conf": avg_conf, "avg_acc": avg_acc, "diff": diff,
            })
        results["per_class"][cls] = {
            "n_pos": n_pos,
            "p_when_actual": p_when_pos,
            "p_when_not_actual": p_when_neg,
            "lift": lift,
            "brier": brier,
            "max_bin_diff": max_diff,
            "reliability_bins": per_bin,
        }
        verdict = "HAS SIGNAL" if lift > 1.20 else ("WEAK" if lift > 1.05 else "NO SIGNAL")
        log.info("  %-3s %5d  %.3f    %.3f    %.2f  %.4f   %.3f  %s",
                 cls, n_pos, p_when_pos, p_when_neg, lift, brier, max_diff, verdict)

    log.info("")
    log.info("INTERPRETATION:")
    log.info("  lift > 1.20 = model meaningfully distinguishes this class")
    log.info("  Brier near (1 - p_when_neg) = uninformative; near 0 = perfect")
    log.info("  max_bin_diff = worst per-bin calibration miss for this class")
    log.info("")
    log.info("VERDICT for class_weight='balanced' decision:")
    has_signal = {c: r['lift'] > 1.20 for c, r in results['per_class'].items()}
    if has_signal.get('1', False) or has_signal.get('3', False):
        log.info("  Classes 1/3 HAVE signal in the probabilities (lift > 1.20).")
        log.info("  → class_weight='balanced' would DEGRADE the working signal.")
        log.info("  → DO NOT use balanced. The 4-prob product surface already works.")
    else:
        log.info("  Classes 1/3 do NOT have meaningful discrimination.")
        log.info("  → class_weight='balanced' would force noisy argmax coverage.")
        log.info("  → Also DO NOT use balanced. Need different feature signals, not reweighting.")
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", required=True)
    p.add_argument("--tf", required=True)
    p.add_argument("--train-until", default="2026-01-01")
    p.add_argument("--model-file", default="model.pkl",
                   help="Which model variant to load; e.g. model.pkl (default), "
                        "model_sigmoid_cv3_balanced.pkl, model_isotonic_cv5_natural.pkl")
    args = p.parse_args()
    engine = get_engine()
    per_class_discrimination(engine, args.ticker, args.tf,
                              args.train_until, args.model_file)


if __name__ == "__main__":
    main()
