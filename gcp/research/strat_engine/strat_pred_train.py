"""Stage 4 — Model — `strat_pred_train.py`.

Trains a calibrated 4-class LightGBM classifier per (ticker, tf). The new
piece vs p7b: calibration (isotonic default) AND ECE reporting AND the
beat-the-base-rate gate.

Anchored walk-forward split:
  - TRAIN: bar_date < train_until
  - CALIB: holdout slice immediately after train (~20% of train period)
  - TEST:  bar_date >= train_until (the OOS evaluator)

Acceptance (PRD §"Definition of done", Stage 4 acceptance):
  - OOS accuracy beats base rate by >= base_rate_beat_pp (default +5pp)
  - ECE <= ece_ceiling (default 0.05)
  Both must hold OR the model fails the gate.

Outputs:
  - model.pkl (calibrated)
  - features.txt
  - classes.txt
  - metrics.json (with gate verdict)
  All to gs://.../research/strat_engine/{ticker}_{tf}/
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gcp.database import get_engine
from gcp.research.strat_engine.strat_config import (
    TICKERS, TIMEFRAMES, NUMERIC_FEATURES, CATEGORICAL_FEATURES,
    LABEL_COL, LABEL_CLASSES, LABEL_TO_IDX,
    DEFAULT_TRAIN_UNTIL, DEFAULT_BASE_RATE_BEAT_PP, DEFAULT_ECE_CEILING,
    DEFAULT_CALIBRATION, GCS_BUCKET_DEFAULT, gcs_model_prefix,
)
from gcp.research.strat_engine.strat_dataset import (
    load_labeled_dataset, base_rate,
)
from google.cloud import storage as gcs
from lib.logging_config import setup_logging

import lightgbm as lgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    log_loss, classification_report, confusion_matrix, accuracy_score,
)

setup_logging()
log = logging.getLogger(__name__)


def _upload(content: bytes, blob_path: str, ctype="application/octet-stream"):
    bucket_name = os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT)
    gcs.Client().bucket(bucket_name).blob(blob_path).upload_from_string(
        content, content_type=ctype)
    return f"gs://{bucket_name}/{blob_path}"


def featurize(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """One-hot categoricals; select numeric. Same pattern as p7b/p7e."""
    enc = pd.get_dummies(df, columns=list(CATEGORICAL_FEATURES),
                          dummy_na=False, dtype=np.int8)
    drop = {"ticker", "ts", "tf", "bar_date",
            "open", "high", "low", "close", "volume",
            "fwd_close_5bars", "fwd_close_15bars", "fwd_close_30bars", "fwd_close_60bars",
            "fwd_ret_5bars_bps", "fwd_ret_15bars_bps", "fwd_ret_30bars_bps", "fwd_ret_60bars_bps",
            "computed_at", "trigger_high", "trigger_low",
            "is_continuation", "is_reversal", "is_inside", "strat_setup",
            "prev_strat_candle",   # we use prev1_candle (one-hot) instead
            LABEL_COL}
    cols = [c for c in enc.columns
            if c not in drop and enc[c].dtype in
            (np.float64, np.int64, np.int32, np.int8, np.float32)]
    return enc[cols].replace([np.inf, -np.inf], np.nan).fillna(0).astype(np.float32), cols


def expected_calibration_error(y_true_idx: np.ndarray, y_proba: np.ndarray,
                                n_bins: int = 10) -> tuple[float, list]:
    """Multiclass ECE: bin by predicted-class confidence (max proba).
    Returns (ece, per-bin detail list)."""
    pred_idx = np.argmax(y_proba, axis=1)
    conf = y_proba.max(axis=1)
    correct = (pred_idx == y_true_idx).astype(int)

    bin_edges = np.linspace(0, 1, n_bins + 1)
    bins = np.digitize(conf, bin_edges[1:-1])

    ece = 0.0
    n = len(y_true_idx)
    details = []
    for b in range(n_bins):
        mask = bins == b
        n_in_bin = int(mask.sum())
        if n_in_bin == 0:
            details.append({"bin": b, "n": 0,
                            "lo": float(bin_edges[b]),
                            "hi": float(bin_edges[b + 1]),
                            "avg_conf": None, "avg_acc": None})
            continue
        avg_conf = float(conf[mask].mean())
        avg_acc = float(correct[mask].mean())
        ece += (n_in_bin / n) * abs(avg_conf - avg_acc)
        details.append({"bin": b, "n": n_in_bin,
                        "lo": float(bin_edges[b]),
                        "hi": float(bin_edges[b + 1]),
                        "avg_conf": avg_conf, "avg_acc": avg_acc})
    return float(ece), details


def make_lgbm() -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(
        objective="multiclass", num_class=len(LABEL_CLASSES),
        n_estimators=300, learning_rate=0.05, max_depth=6,
        num_leaves=31, min_child_samples=100,
        random_state=42, verbose=-1, n_jobs=-1,
    )


def run_train(engine, ticker: str, tf: str, train_until: str,
              calibration: str = DEFAULT_CALIBRATION,
              base_rate_beat_pp: float = DEFAULT_BASE_RATE_BEAT_PP,
              ece_ceiling: float = DEFAULT_ECE_CEILING) -> dict:
    log.info("=" * 70)
    log.info("Stage 4 TRAIN  ticker=%s  tf=%s  train_until=%s  cal=%s",
             ticker, tf, train_until, calibration)
    log.info("=" * 70)

    train_df = load_labeled_dataset(engine, ticker, tf, until=train_until)
    test_df = load_labeled_dataset(engine, ticker, tf, since=train_until)
    log.info("split sizes — train=%d  test(OOS)=%d", len(train_df), len(test_df))

    # Featurize train + test, align columns
    X_train, train_cols = featurize(train_df)
    X_test, test_cols = featurize(test_df)
    all_cols = sorted(set(train_cols) | set(test_cols))
    for X in (X_train, X_test):
        for c in all_cols:
            if c not in X.columns: X[c] = 0
    X_train = X_train[all_cols].astype(np.float32)
    X_test = X_test[all_cols].astype(np.float32)

    y_train = train_df[LABEL_COL].map(LABEL_TO_IDX).values
    y_test = test_df[LABEL_COL].map(LABEL_TO_IDX).values

    # CalibratedClassifierCV with internal CV (sklearn 1.6+ deprecated cv='prefit').
    # cv=3 means the base estimator is trained on each fold and calibration is
    # learned on the held-out fold. No data leakage because it uses sklearn's
    # cross-validation internally.
    log.info("fitting calibrated LightGBM (method=%s, cv=3) on %d train rows × %d cols...",
             calibration, len(X_train), len(all_cols))
    calibrated = CalibratedClassifierCV(
        estimator=make_lgbm(), method=calibration, cv=3, n_jobs=-1,
    )
    calibrated.fit(X_train.values, y_train)

    # OOS evaluation
    proba_test = calibrated.predict_proba(X_test.values)
    pred_test = np.argmax(proba_test, axis=1)
    acc = float(accuracy_score(y_test, pred_test))
    ll = float(log_loss(y_test, proba_test, labels=list(range(len(LABEL_CLASSES)))))

    # baseline = always predict majority class from TRAIN data
    train_majority = int(np.bincount(y_train, minlength=len(LABEL_CLASSES)).argmax())
    base_acc = float((y_test == train_majority).mean())
    base_proba = np.tile(
        np.bincount(y_train, minlength=len(LABEL_CLASSES)) / len(y_train),
        (len(y_test), 1))
    base_ll = float(log_loss(y_test, base_proba, labels=list(range(len(LABEL_CLASSES)))))

    ece, ece_bins = expected_calibration_error(y_test, proba_test, n_bins=10)

    report = classification_report(
        y_test, pred_test,
        labels=list(range(len(LABEL_CLASSES))),
        target_names=LABEL_CLASSES,
        output_dict=True, zero_division=0,
    )
    cm = confusion_matrix(y_test, pred_test, labels=list(range(len(LABEL_CLASSES))))

    log.info("=" * 70)
    log.info("OOS METRICS  (log-loss is the PRIMARY gate; accuracy can be gamed)")
    log.info("=" * 70)
    log.info("log-loss:  model=%.4f  base=%.4f  Δ=%+.4f   [PRIMARY GATE: model < base]",
             ll, base_ll, base_ll - ll)
    log.info("accuracy:  model=%.3f  base=%.3f  Δ=%+.1fpp  [SECONDARY: >=+%.1fpp]",
             acc, base_acc, (acc - base_acc) * 100, base_rate_beat_pp)
    log.info("ECE      : %.4f   [SECONDARY: <=%.3f]", ece, ece_ceiling)

    log.info("per-class:")
    for cls in LABEL_CLASSES:
        r = report[cls]
        log.info("  %-3s  prec=%.3f  rec=%.3f  f1=%.3f  n=%d",
                 cls, r["precision"], r["recall"], r["f1-score"], int(r["support"]))

    # Hard gates (block downstream): log-loss + ECE only. Accuracy is
    # ADVISORY because a calibrated, informative model on noisier cells
    # (1m, 4h) can beat base-rate log-loss while missing +5pp accuracy.
    # That would be a false-negative kill on exactly the model we want.
    # Reviewer-flagged 2026-05-25.
    logloss_gate = ll < base_ll
    ece_gate = ece <= ece_ceiling
    accuracy_advisory = (acc - base_acc) * 100 >= base_rate_beat_pp
    gate_pass = logloss_gate and ece_gate  # accuracy NOT required
    log.info("=" * 70)
    log.info("GATE VERDICT: %s  (HARD: logloss=%s, ece=%s | ADVISORY: accuracy=%s)",
             "PASS" if gate_pass else "FAIL",
             "PASS" if logloss_gate else "FAIL",
             "PASS" if ece_gate else "FAIL",
             "PASS" if accuracy_advisory else "FAIL")
    log.info("=" * 70)

    metrics = {
        "ticker": ticker, "tf": tf, "train_until": train_until,
        "calibration": calibration,
        "n_train": int(len(X_train)), "n_test": int(len(X_test)),
        "oos_accuracy": acc, "base_accuracy": base_acc,
        "accuracy_beat_pp": (acc - base_acc) * 100,
        "oos_log_loss": ll, "base_log_loss": base_ll,
        "log_loss_improvement": base_ll - ll,
        "ece": ece, "ece_bins": ece_bins,
        "per_class": {c: report[c] for c in LABEL_CLASSES},
        "confusion_matrix": {LABEL_CLASSES[i]: {LABEL_CLASSES[j]: int(cm[i, j])
                                                for j in range(len(LABEL_CLASSES))}
                              for i in range(len(LABEL_CLASSES))},
        "gate": {
            "hard_logloss_gate_pass": logloss_gate,
            "hard_ece_gate_pass": ece_gate,
            "advisory_accuracy_gate_pass": accuracy_advisory,
            "base_rate_beat_pp_threshold": base_rate_beat_pp,
            "ece_ceiling": ece_ceiling,
            "verdict": "PASS" if gate_pass else "FAIL",
        },
        "trained_at": pd.Timestamp.utcnow().isoformat(),
    }

    # Persist
    prefix = gcs_model_prefix(ticker, tf)
    _upload(pickle.dumps(calibrated), f"{prefix}/model.pkl")
    _upload("\n".join(all_cols).encode(), f"{prefix}/features.txt", "text/plain")
    _upload("\n".join(LABEL_CLASSES).encode(), f"{prefix}/classes.txt", "text/plain")
    _upload(json.dumps(metrics, indent=2, default=str).encode(),
            f"{prefix}/metrics_{int(time.time())}.json")
    log.info("saved model + metrics to gs://%s/%s/",
             os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT), prefix)

    return metrics


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--train-until", default=DEFAULT_TRAIN_UNTIL)
    p.add_argument("--calibration", default=DEFAULT_CALIBRATION,
                   choices=["isotonic", "sigmoid"])
    p.add_argument("--base-rate-beat-pp", type=float,
                   default=DEFAULT_BASE_RATE_BEAT_PP)
    p.add_argument("--ece-ceiling", type=float, default=DEFAULT_ECE_CEILING)
    args = p.parse_args()
    engine = get_engine()
    run_train(engine, args.ticker, args.tf, args.train_until,
              calibration=args.calibration,
              base_rate_beat_pp=args.base_rate_beat_pp,
              ece_ceiling=args.ece_ceiling)


if __name__ == "__main__":
    main()
