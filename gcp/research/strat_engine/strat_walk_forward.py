"""Strat Engine — anchored walk-forward stability check.

The gate that decides whether ANY of this scales. Leakage has been ruled
out across all 6 TFs (audit 2026-05-26), so regime-specificity is the
only remaining threat to the +0.11 to +0.16 log-loss beat we observe in
the Jan-May 2026 OOS window. Walk-forward tests whether the beat holds
in OTHER regimes (low-vol 2017-19, COVID 2020, bull 2021, bear 2022,
recovery 2023-24).

Design (per reviewer 2026-05-26):
  1. Per-fold reporting labeled by date range, NOT a stability scalar.
     "held in 2018, 2021, 2023, collapsed in the 2022 bear" beats a
     variance number that averages a regime failure into looking fine.
  2. Track BOTH log-loss beat AND ECE per fold. Calibration can degrade
     out-of-regime even while log-loss holds. Overconfident-in-new-regime
     is a worse failure than just-noisier.
  3. Full retrain AND recalibrate per fold. The CalibratedClassifierCV
     `model.fit()` inside the loop refits the base LGBM 3x and learns a
     fresh sigmoid on each held-out fold. NEVER reuse the calibration map
     from one walk-forward fold in another. That's the classic harness
     leak.
  4. Run on 15m, 30m, AND 5m. 4h and 60m have too few bars per fold to
     trust. 1m is dropped (FTFC_WEIGHTS=0; pathological probs).

Cutoffs span deliberate regimes:
  2019-01-01  → test 2019 (recovery bull)   ← FIRST fold; trains on 2016-2018 (3yr)
  2020-01-01  → test 2020 (COVID crash + V-recovery)
  2021-01-01  → test 2021 (bull)
  2022-01-01  → test 2022 (bear, Fed tightening)
  2023-01-01  → test 2023 (bull recovery)
  2024-01-01  → test 2024 (bull continuation)
  2025-01-01  → test 2025 (current regime up to OOS cut)
  2026-01-01  → test Jan-May 2026 (our locked OOS cell)

NOTE on the dropped 2018 fold:
An anchored expanding window means the earliest folds train on the least
data. A 2018 fold would train on just 2016-2017 (~2 years), confounding
"weak fold = regime change" with "weak fold = thin training." Reviewer
2026-05-26: start the first OOS fold at 2019 so every fold has ≥3 years
of training behind it.

Run:
  python -m gcp.research.strat_engine.strat_walk_forward \\
      --ticker IWM --tf 15m
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
    TICKERS, TIMEFRAMES, LABEL_COL, LABEL_CLASSES, LABEL_TO_IDX,
    DEFAULT_CALIBRATION, DEFAULT_CV,
    DEFAULT_BASE_RATE_BEAT_PP, DEFAULT_ECE_CEILING,
    GCS_BUCKET_DEFAULT, gcs_model_prefix,
)
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
from gcp.research.strat_engine.strat_pred_train import (
    featurize, make_lgbm, expected_calibration_error,
)
from google.cloud import storage as gcs
from lib.logging_config import setup_logging
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import log_loss

setup_logging()
log = logging.getLogger(__name__)


# Anchored / expanding-window cutoffs spanning distinct market regimes.
# Each fold trains on EVERYTHING before its cutoff and tests on the slice
# up to the next cutoff. NOT evenly spaced — placed to span regimes.
DEFAULT_CUTOFFS = [
    # First fold trains on 2016-2018 (3yr) to avoid confounding thin-training
    # with regime change. 2018 OOS deliberately dropped — only 2yr of training
    # behind it would make a weak fold ambiguous between regime and undertraining.
    "2019-01-01",  # test 2019 (recovery)
    "2020-01-01",  # test 2020 (COVID)
    "2021-01-01",  # test 2021 (bull)
    "2022-01-01",  # test 2022 (bear, Fed tightening)
    "2023-01-01",  # test 2023 (recovery)
    "2024-01-01",  # test 2024 (bull continuation)
    "2025-01-01",  # test 2025
    "2026-01-01",  # test Jan-May 2026 (our locked OOS)
]

# Minimum test-set size to report a fold. Below this, the fold is noise.
MIN_TEST_BARS = 200


def _gcs_upload(content: bytes, blob_path: str, ctype: str = "application/json"):
    bucket_name = os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT)
    gcs.Client().bucket(bucket_name).blob(blob_path).upload_from_string(
        content, content_type=ctype)
    return f"gs://{bucket_name}/{blob_path}"


def base_rate_logloss(y_train_idx: np.ndarray, y_test_idx: np.ndarray) -> float:
    """log-loss of predicting the train-set class prior on every test bar.
    Uses TRAIN priors to avoid any peek at test."""
    prior = np.bincount(y_train_idx, minlength=len(LABEL_CLASSES)) / len(y_train_idx)
    proba = np.tile(prior, (len(y_test_idx), 1))
    return float(log_loss(
        y_test_idx, proba, labels=list(range(len(LABEL_CLASSES)))))


def train_and_evaluate_fold(df: pd.DataFrame, train_end: str, test_end: str) -> dict:
    """ONE fold of walk-forward. Full retrain + recalibrate from scratch.

    Critical: the CalibratedClassifierCV is constructed FRESH inside this
    function. NEVER reuse a calibrator from a different fold — that
    leaks future data into past test windows.
    """
    train_df = df[df["bar_date"] < pd.Timestamp(train_end).date()]
    test_df = df[(df["bar_date"] >= pd.Timestamp(train_end).date())
                 & (df["bar_date"] < pd.Timestamp(test_end).date())]
    if len(test_df) < MIN_TEST_BARS:
        return {"fold": f"{train_end}..{test_end}",
                "n_test": len(test_df), "n_train": len(train_df),
                "status": "SKIP_THIN"}

    # Featurize independently then align columns (one-hot categoricals may
    # differ between train and test slices).
    X_tr, tr_cols = featurize(train_df)
    X_te, te_cols = featurize(test_df)
    all_cols = sorted(set(tr_cols) | set(te_cols))
    for X in (X_tr, X_te):
        for c in all_cols:
            if c not in X.columns: X[c] = 0
    X_tr, X_te = X_tr[all_cols].astype(np.float32), X_te[all_cols].astype(np.float32)
    y_tr = train_df[LABEL_COL].map(LABEL_TO_IDX).values
    y_te = test_df[LABEL_COL].map(LABEL_TO_IDX).values

    # FRESH calibrated classifier — refit base + sigmoid from scratch.
    # The retrain-and-recalibrate happens inside this single fit() call:
    # CalibratedClassifierCV(cv=3) trains the base LGBM on each of 3 folds
    # of train data, fits the sigmoid on each held-out third, then averages.
    calibrated = CalibratedClassifierCV(
        estimator=make_lgbm(class_weight=None),
        method=DEFAULT_CALIBRATION, cv=DEFAULT_CV, n_jobs=-1,
    )
    calibrated.fit(X_tr.values, y_tr)

    # Evaluate on the test slice
    proba = calibrated.predict_proba(X_te.values)
    ll = float(log_loss(y_te, proba, labels=list(range(len(LABEL_CLASSES)))))
    base_ll = base_rate_logloss(y_tr, y_te)
    pred = np.argmax(proba, axis=1)
    acc = float((pred == y_te).mean())
    base_acc = float((y_te == int(np.bincount(y_tr, minlength=len(LABEL_CLASSES)).argmax())).mean())
    ece, ece_bins = expected_calibration_error(y_te, proba, n_bins=10)

    return {
        "fold": f"{train_end}..{test_end}",
        "n_train": int(len(train_df)),
        "n_test": int(len(test_df)),
        "logloss": ll,
        "base_logloss": base_ll,
        "beat": base_ll - ll,
        "accuracy": acc,
        "base_accuracy": base_acc,
        "accuracy_beat_pp": (acc - base_acc) * 100,
        "ece": float(ece),
        "ece_bins": ece_bins,
        "status": "OK",
    }


def walk_forward(engine, ticker: str, tf: str,
                 cutoffs: list[str] = None) -> dict:
    cutoffs = cutoffs or DEFAULT_CUTOFFS
    log.info("=" * 70)
    log.info("WALK-FORWARD  %s %s  %d cutoffs", ticker, tf, len(cutoffs))
    log.info("=" * 70)
    log.info("cutoffs: %s", " | ".join(cutoffs))

    df = load_labeled_dataset(engine, ticker, tf)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
    log.info("loaded full dataset: %d rows  (%s..%s)",
             len(df), df["bar_date"].min(), df["bar_date"].max())

    folds = []
    for i, cut in enumerate(cutoffs):
        if i + 1 < len(cutoffs):
            test_end = cutoffs[i + 1]
        else:
            # Final fold goes to dataset end
            test_end = str(pd.Timestamp(df["bar_date"].max())
                            + pd.Timedelta(days=1))[:10]
        log.info("─" * 70)
        log.info("fold %d/%d  train<%s  test=[%s..%s)",
                 i + 1, len(cutoffs), cut, cut, test_end)
        try:
            r = train_and_evaluate_fold(df, cut, test_end)
            folds.append(r)
            if r["status"] == "OK":
                log.info("  n_train=%d  n_test=%d", r["n_train"], r["n_test"])
                log.info("  logloss=%.4f  base=%.4f  beat=%+.4f",
                         r["logloss"], r["base_logloss"], r["beat"])
                log.info("  accuracy=%.3f  base=%.3f  Δ=%+.1fpp",
                         r["accuracy"], r["base_accuracy"], r["accuracy_beat_pp"])
                log.info("  ECE=%.4f  ceiling=%.3f  %s",
                         r["ece"], DEFAULT_ECE_CEILING,
                         "PASS" if r["ece"] <= DEFAULT_ECE_CEILING else "FAIL")
            else:
                log.info("  %s (n_test=%d < %d)", r["status"], r["n_test"], MIN_TEST_BARS)
        except Exception as e:
            log.exception("fold %s FAILED: %s", cut, e)
            folds.append({"fold": f"{cut}..{test_end}", "status": "ERROR",
                          "error": str(e)})

    # Summary table
    log.info("=" * 70)
    log.info("WALK-FORWARD SUMMARY  %s %s", ticker, tf)
    log.info("=" * 70)
    log.info("%-25s %8s %8s %8s %8s %8s",
             "fold", "n_test", "logloss", "base", "beat", "ece")
    log.info("-" * 70)
    ok_folds = [f for f in folds if f.get("status") == "OK"]
    for f in folds:
        if f.get("status") == "OK":
            log.info("%-25s %8d %8.4f %8.4f %+8.4f %8.4f",
                     f["fold"], f["n_test"], f["logloss"], f["base_logloss"],
                     f["beat"], f["ece"])
        else:
            log.info("%-25s %s", f["fold"], f.get("status", "?"))

    if ok_folds:
        beats = [f["beat"] for f in ok_folds]
        eces = [f["ece"] for f in ok_folds]
        log.info("-" * 70)
        log.info("beat range: [%.4f .. %.4f]  median=%.4f  min=%.4f",
                 min(beats), max(beats), float(np.median(beats)), min(beats))
        log.info("ece  range: [%.4f .. %.4f]  median=%.4f",
                 min(eces), max(eces), float(np.median(eces)))
        regime_failures = [f for f in ok_folds if f["beat"] < 0.05]
        if regime_failures:
            log.info("⚠️  %d fold(s) with beat < +0.05 (regime weakness):", len(regime_failures))
            for f in regime_failures:
                log.info("    %s  beat=%+.4f  ece=%.4f", f["fold"], f["beat"], f["ece"])
        else:
            log.info("✅ Every fold beats base log-loss by >= +0.05.")

    # Persist to GCS — one consolidated walk-forward report per (ticker, tf)
    summary = {
        "ticker": ticker, "tf": tf,
        "cutoffs": cutoffs,
        "min_test_bars": MIN_TEST_BARS,
        "calibration": DEFAULT_CALIBRATION, "cv": DEFAULT_CV,
        "folds": folds,
        "computed_at": pd.Timestamp.utcnow().isoformat(),
    }
    prefix = gcs_model_prefix(ticker, tf)
    blob = f"{prefix}/walk_forward_{int(time.time())}.json"
    _gcs_upload(json.dumps(summary, indent=2, default=str).encode(), blob)
    log.info("saved: gs://%s/%s",
             os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT), blob)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--cutoffs", default=None,
                   help="Comma-separated YYYY-MM-DD cutoffs (default: regime-spanning)")
    args = p.parse_args()
    cutoffs = args.cutoffs.split(",") if args.cutoffs else None
    engine = get_engine()
    walk_forward(engine, args.ticker, args.tf, cutoffs=cutoffs)


if __name__ == "__main__":
    main()
