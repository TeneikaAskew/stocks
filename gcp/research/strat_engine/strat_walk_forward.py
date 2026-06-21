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
  3. Full retrain per fold. Default calibration="none" (production config
     since 2026-05-27) fits a bare LightGBM and reports its native softmax —
     no post-hoc calibrator, because the 24-fold study proved the sigmoid
     wrapper HURT ECE in every fold. The diagnostic calibration="sigmoid"/
     "isotonic" path refits the base LGBM 3x AND learns a fresh calibrator on
     each held-out fold. When a calibrator IS fit, NEVER reuse the map from
     one walk-forward fold in another — that's the classic harness leak.
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


def _train_holdout_split_by_date(bar_dates: np.ndarray, train_mask: np.ndarray,
                                 calib_frac: float = 0.2):
    """Carve a post-hoc-calibration validation slice from the TRAIN block ONLY,
    by DATE (never random, never the test fold). The newest ``calib_frac`` of
    distinct train DATES become the calibration slice; the rest fit the base
    model. Splitting by date (not row) prevents same-day bars straddling the
    split (within-day autocorrelation leak).

    Returns (fit_mask, calib_mask) over the full row index. If the train block
    has < 5 distinct dates, returns (train_mask, all-False) so the caller falls
    back to raw (uncalibrated) rather than fitting on a handful of bars.
    """
    tr_dates = np.unique(bar_dates[train_mask])
    if len(tr_dates) < 5:
        return train_mask.copy(), np.zeros_like(train_mask)
    n_calib = max(1, int(np.ceil(len(tr_dates) * calib_frac)))
    cut_date = tr_dates[-n_calib]
    calib_mask = train_mask & (bar_dates >= cut_date)
    fit_mask = train_mask & (bar_dates < cut_date)
    if int(fit_mask.sum()) == 0 or int(calib_mask.sum()) == 0:
        return train_mask.copy(), np.zeros_like(train_mask)
    return fit_mask, calib_mask


def _isotonic_oos_proba(model, X_calib, y_calib, X_test, n_classes):
    """Post-hoc MULTICLASS isotonic calibration fit on an out-of-train-but-
    in-fold validation slice (NOT sklearn's per-fold-CV CalibratedClassifierCV
    that E-20 found hurt ECE — this is a different, untried lever).

    For each class k: fit a 1-D IsotonicRegression mapping the base model's
    raw P(class=k) on the calibration slice → the realized 0/1 indicator of
    class k. Apply to the test probabilities, then renormalize rows to sum to
    1 (one-vs-rest isotonic is not inherently normalized).

    A class absent from the calibration slice (single-value indicator) keeps
    its raw probability for that column — calibrating a one-class column is
    undefined, and fabricating a value would be a silent fallback (Rule 3.7).
    Returns the calibrated, renormalized test probability matrix.
    """
    from sklearn.isotonic import IsotonicRegression
    classes = list(model.classes_)
    raw_calib = model.predict_proba(X_calib)
    raw_test = model.predict_proba(X_test)
    cal_test = np.empty_like(raw_test)
    for j, cls in enumerate(classes):
        ind = (y_calib == cls).astype(float)
        if ind.min() == ind.max():
            # class never (or always) appears in the calib slice — cannot fit
            # an honest isotonic map; keep the raw column for this class.
            cal_test[:, j] = raw_test[:, j]
            continue
        ir = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        ir.fit(raw_calib[:, j], ind)
        cal_test[:, j] = np.clip(ir.predict(raw_test[:, j]), 1e-9, 1.0)
    # Renormalize each row to a proper distribution. Rows that underflow to ~0
    # everywhere fall back to the raw row (cannot normalize a zero vector).
    row_sums = cal_test.sum(axis=1, keepdims=True)
    bad = (row_sums[:, 0] <= 1e-12)
    cal_test[~bad] = cal_test[~bad] / row_sums[~bad]
    cal_test[bad] = raw_test[bad]
    # Map model-class order back to canonical 0..n_classes-1 column order.
    if classes != list(range(n_classes)):
        out = np.zeros((len(X_test), n_classes))
        for j, cls in enumerate(classes):
            out[:, int(cls)] = cal_test[:, j]
        # renormalize again after the (possibly sparse) remap
        s = out.sum(axis=1, keepdims=True)
        s[s <= 1e-12] = 1.0
        return out / s
    return cal_test


def train_and_evaluate_fold(X_full: np.ndarray, y_full: np.ndarray,
                             bar_dates: np.ndarray,
                             train_end: str, test_end: str,
                             lgbm_n_jobs: int,
                             calibration: str = DEFAULT_CALIBRATION,
                             calib_frac: float = 0.2) -> dict:
    """ONE fold of walk-forward. Full retrain (+ optional recalibrate) from scratch.

    Inputs are pre-featurized arrays + a bar_date array for slicing — the
    featurize() call has been hoisted out of the loop to avoid 16 redundant
    one-hot rebuilds across 8 folds. Per-fold work is now O(numpy slice +
    LGBM fit), not O(featurize + pandas concat + column align).

    `calibration`:
      - "none" (production default since 2026-05-27): fit a bare LightGBM and
        use its native softmax — NO post-hoc calibration. The 24-fold study
        proved the sigmoid wrapper HURT ECE in every fold, so the shipped
        model carries no calibrator. This branch mirrors
        strat_pred_train.run_train's calibration=="none" path so the
        walk-forward validates the EXACT artifact production serves.
        Reviewer-flagged 2026-06-04: previously this function unconditionally
        wrapped in CalibratedClassifierCV(method=DEFAULT_CALIBRATION); once
        DEFAULT_CALIBRATION flipped to "none", sklearn rejected
        method="none" and the canonical walk-forward crashed (no
        walk_forward_<epoch>.json artifact was ever produced — the only
        surviving evidence came from the adaptive harness's mode=none path).
      - "sigmoid"/"isotonic" (diagnostic): refit base + calibrator from
        scratch per fold via CalibratedClassifierCV. Kept so the
        sigmoid-hurts comparison stays reproducible.
      - "isotonic_oos" (principled thin-sample fix): post-hoc per-class
        isotonic fit on a DATE-carved validation slice of THIS fold's train
        block, NOT the sklearn CV-refit. Designed for the 30m cells whose ECE
        misses the 0.05 ceiling on thin sample. Whether it actually HELPS is
        an empirical question (E-20 found the CV path hurt); this branch lets
        the walk-forward TEST it honestly. The ECE gate is NOT loosened — a
        30m cell that still exceeds 0.05 after this stays FAILing.

        ``calib_frac`` (default 0.2) governs how many of the newest DISTINCT
        TRAIN dates are carved into that calibration slice. It is a research
        knob, NOT a per-cell tuning dial — see the honest finding below.

    ── 2026-06-21: QQQ-30m calib_frac sweep (do NOT re-chase this) ──────────
    After #646, QQQ-30m sits 7/8 under isotonic_oos@0.2 (the 2025 fold ECE
    0.0567, just over 0.05). A full calib_frac sweep was run through THIS
    production harness (8 regime folds × IWM/SPY/QQQ):

        QQQ-30m:  cf0.20 7/8 (2025=.0567) · cf0.30 7/8 (2020=.0545)
                  cf0.35 7/8 (2020=.0557) · cf0.40 8/8 · cf0.45 8/8
        IWM-30m:  cf0.20 8/8 (worst .0483) · cf0.40 7/8 (2023=.0569) ← REGRESS
        SPY-30m:  cf0.20 8/8            · cf0.40 8/8

    QQQ only reaches 8/8 at frac >= 0.40, but at 0.40 IWM-30m REGRESSES to
    7/8 — and the QQQ failing fold hops (2025 -> 2020 -> 2020) as frac moves,
    so the 8/8 is the frac hyperparameter being curve-fit to the gate, not a
    robust calibration win. There is NO single calib_frac that clears QQQ-30m
    8/8 without breaking IWM-30m. Honest verdict: the production default stays
    calib_frac=0.2 (IWM/SPY-30m 8/8 preserved) and QQQ-30m STAYS HIDDEN/GATED
    until more data accrues. The gate was NOT loosened to force a pass.

    Critical: when a calibrator IS fit, it is constructed FRESH inside this
    function. NEVER reuse a calibrator from a different fold — that leaks
    future data into past test windows.
    """
    calib_status = calibration
    train_end_dt = np.datetime64(train_end)
    test_end_dt = np.datetime64(test_end)
    train_mask = bar_dates < train_end_dt
    test_mask = (bar_dates >= train_end_dt) & (bar_dates < test_end_dt)
    n_train = int(train_mask.sum())
    n_test = int(test_mask.sum())
    if n_test < MIN_TEST_BARS:
        return {"fold": f"{train_end}..{test_end}",
                "n_test": n_test, "n_train": n_train,
                "status": "SKIP_THIN"}

    X_tr = X_full[train_mask]
    X_te = X_full[test_mask]
    y_tr = y_full[train_mask]
    y_te = y_full[test_mask]

    if calibration == "none":
        # PRODUCTION CONFIG — bare LightGBM, raw native softmax, no wrapper.
        # No CV, so the base LGBM gets all the threads the caller granted.
        model = make_lgbm(class_weight=None, n_jobs=lgbm_n_jobs)
        model.fit(X_tr, y_tr)
        proba = model.predict_proba(X_te)
    elif calibration == "isotonic_oos":
        # PRINCIPLED post-hoc isotonic, fit on a DATE-carved validation slice
        # of THIS fold's train block (never the test fold). Distinct from the
        # CV-refit CalibratedClassifierCV path E-20 rejected. This is the
        # untried lever for the thin-sample 30m cells. Falls back to raw (and
        # records it) when the train block is too thin to carve a slice — never
        # silently fabricates a calibrated number (Rule 3.7).
        fit_mask, calib_mask = _train_holdout_split_by_date(
            bar_dates, train_mask, calib_frac=calib_frac)
        if int(calib_mask.sum()) == 0:
            model = make_lgbm(class_weight=None, n_jobs=lgbm_n_jobs)
            model.fit(X_tr, y_tr)
            proba = model.predict_proba(X_te)
            calib_status = "RAW_calib_unavailable"
        else:
            model = make_lgbm(class_weight=None, n_jobs=lgbm_n_jobs)
            model.fit(X_full[fit_mask], y_full[fit_mask])
            proba = _isotonic_oos_proba(
                model, X_full[calib_mask], y_full[calib_mask], X_te,
                len(LABEL_CLASSES))
            calib_status = "isotonic_oos"
    else:
        # DIAGNOSTIC — FRESH calibrated classifier; refit base + calibrator
        # from scratch. Untangled parallelism: CalibratedClassifierCV(n_jobs=cv)
        # parallelizes the cv inner folds; each LGBM is given n_jobs =
        # cores // cv so total threads ≤ core count. Previous nested -1
        # created 24 threads on 8 cores.
        calibrated = CalibratedClassifierCV(
            estimator=make_lgbm(class_weight=None, n_jobs=lgbm_n_jobs),
            method=calibration, cv=DEFAULT_CV, n_jobs=DEFAULT_CV,
        )
        calibrated.fit(X_tr, y_tr)
        proba = calibrated.predict_proba(X_te)
    ll = float(log_loss(y_te, proba, labels=list(range(len(LABEL_CLASSES)))))
    base_ll = base_rate_logloss(y_tr, y_te)
    pred = np.argmax(proba, axis=1)
    acc = float((pred == y_te).mean())
    base_acc = float((y_te == int(np.bincount(y_tr, minlength=len(LABEL_CLASSES)).argmax())).mean())
    ece, ece_bins = expected_calibration_error(y_te, proba, n_bins=10)

    return {
        "fold": f"{train_end}..{test_end}",
        "n_train": n_train,
        "n_test": n_test,
        "logloss": ll,
        "base_logloss": base_ll,
        "beat": base_ll - ll,
        "accuracy": acc,
        "base_accuracy": base_acc,
        "accuracy_beat_pp": (acc - base_acc) * 100,
        "ece": float(ece),
        "ece_bins": ece_bins,
        "calib_status": calib_status,
        "status": "OK",
    }


def walk_forward(engine, ticker: str, tf: str,
                 cutoffs: list[str] = None,
                 calibration: str = DEFAULT_CALIBRATION,
                 calib_frac: float = 0.2) -> dict:
    cutoffs = cutoffs or DEFAULT_CUTOFFS
    log.info("=" * 70)
    log.info("WALK-FORWARD  %s %s  %d cutoffs  calibration=%s  calib_frac=%.2f",
             ticker, tf, len(cutoffs), calibration, calib_frac)
    log.info("=" * 70)
    log.info("cutoffs: %s", " | ".join(cutoffs))

    df = load_labeled_dataset(engine, ticker, tf)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
    log.info("loaded full dataset: %d rows  (%s..%s)",
             len(df), df["bar_date"].min(), df["bar_date"].max())

    # FEATURIZE ONCE — hoisted out of the fold loop. Previously called per
    # fold (8 folds × train+test = 16 re-encodings), which was the main
    # walk-forward bottleneck. Now: one pd.get_dummies + one reindex; each
    # fold just numpy-slices.
    t0 = time.time()
    X_df, feature_cols = featurize(df)
    X_full = X_df.values.astype(np.float32, copy=False)
    y_full = df[LABEL_COL].map(LABEL_TO_IDX).values.astype(np.int64)
    # bar_date is a Series of Python `date` objects after load_labeled_dataset
    # → pd.DatetimeIndex first, then to day-precision datetime64.
    bar_dates_arr = pd.DatetimeIndex(df["bar_date"]).values.astype("datetime64[D]")
    log.info("featurize-once: %d rows × %d cols in %.1fs",
             X_full.shape[0], X_full.shape[1], time.time() - t0)

    # Threading. Under calibration="none" there is no CV, so the bare LGBM
    # takes all cores. Under the diagnostic calibrated path, untangle nested
    # parallelism: with cv=3 on 8 cores the outer parallelizes the 3 CV folds
    # and each LGBM gets ⌊8/3⌋ = 2 threads (total 6, under the core count).
    # Previous nested n_jobs=-1 created 24 threads on 8 cores.
    cores = max(1, os.cpu_count() or 1)
    if calibration == "none":
        lgbm_n_jobs = cores
        log.info("threading: cores=%d, lgbm n_jobs=%d (no CV — calibration=none)",
                 cores, lgbm_n_jobs)
    else:
        lgbm_n_jobs = max(1, cores // DEFAULT_CV)
        log.info("threading: cores=%d, calibrated_cv n_jobs=%d, lgbm n_jobs=%d",
                 cores, DEFAULT_CV, lgbm_n_jobs)

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
            fold_t0 = time.time()
            r = train_and_evaluate_fold(
                X_full, y_full, bar_dates_arr, cut, test_end, lgbm_n_jobs,
                calibration=calibration, calib_frac=calib_frac)
            r["fold_seconds"] = round(time.time() - fold_t0, 1)
            folds.append(r)
            if r["status"] == "OK":
                log.info("  n_train=%d  n_test=%d", r["n_train"], r["n_test"])
                log.info("  logloss=%.4f  base=%.4f  beat=%+.4f",
                         r["logloss"], r["base_logloss"], r["beat"])
                log.info("  accuracy=%.3f  base=%.3f  Δ=%+.1fpp",
                         r["accuracy"], r["base_accuracy"], r["accuracy_beat_pp"])
                log.info("  ECE=%.4f  ceiling=%.3f  %s  (calib=%s)",
                         r["ece"], DEFAULT_ECE_CEILING,
                         "PASS" if r["ece"] <= DEFAULT_ECE_CEILING else "FAIL",
                         r.get("calib_status", "none"))
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

    # Persist to GCS — one consolidated walk-forward report per (ticker, tf).
    # cv only applies on the diagnostic calibrated path; under "none" there
    # is no CV. The artifact name carries the calibration mode so a diagnostic
    # sigmoid run never overwrites the production "none" report.
    summary = {
        "ticker": ticker, "tf": tf,
        "cutoffs": cutoffs,
        "min_test_bars": MIN_TEST_BARS,
        "calibration": calibration,
        # calib_frac only governs the isotonic_oos date-carved TRAIN slice; it
        # is a no-op for none/sigmoid/isotonic. Stamped so a non-default-frac
        # run is reproducible and distinguishable in the artifact.
        "calib_frac": calib_frac if calibration == "isotonic_oos" else None,
        "cv": DEFAULT_CV if calibration != "none" else None,
        "folds": folds,
        "computed_at": pd.Timestamp.utcnow().isoformat(),
    }
    prefix = gcs_model_prefix(ticker, tf)
    # The artifact name carries the calibration mode (and, for isotonic_oos, the
    # calib_frac) so a diagnostic / larger-slice run never overwrites the
    # production "none" report or another frac's isotonic_oos report.
    frac_tag = (f"_cf{int(round(calib_frac * 100)):02d}"
                if calibration == "isotonic_oos" else "")
    blob = f"{prefix}/walk_forward_{calibration}{frac_tag}_{int(time.time())}.json"
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
    p.add_argument("--calibration", default=DEFAULT_CALIBRATION,
                   choices=["none", "sigmoid", "isotonic", "isotonic_oos"],
                   help="none=production raw-softmax (default); sigmoid/isotonic "
                        "are the diagnostic CV-refit path (the 24-fold study "
                        "proved sigmoid hurts ECE — E-20); isotonic_oos is the "
                        "principled post-hoc isotonic fit on a date-carved "
                        "TRAIN slice — the thin-sample 30m fix to TEST (the ECE "
                        "gate is NOT loosened).")
    p.add_argument("--calib-frac", dest="calib_frac", type=float, default=0.2,
                   help="Fraction of the newest DISTINCT TRAIN dates carved off "
                        "as the isotonic_oos calibration slice (default 0.2). "
                        "Only used when --calibration=isotonic_oos. The slice is "
                        "always date-carved from TRAIN — it never touches test or "
                        "the holdout, so a larger frac trades base-model training "
                        "data for a better-fit calibration map but introduces NO "
                        "leakage. The ECE gate stays 0.05.")
    args = p.parse_args()
    if not (0.0 < args.calib_frac < 1.0):
        p.error(f"--calib-frac must be in (0, 1), got {args.calib_frac}")
    cutoffs = args.cutoffs.split(",") if args.cutoffs else None
    engine = get_engine()
    walk_forward(engine, args.ticker, args.tf, cutoffs=cutoffs,
                 calibration=args.calibration, calib_frac=args.calib_frac)


if __name__ == "__main__":
    main()
