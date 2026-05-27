"""Strat Engine — walk-forward with ADAPTIVE recalibration.

The static walk-forward (strat_walk_forward.py) discovered that the
ranking signal is regime-robust (+14 to +22pp accuracy beat across 16
folds spanning 2019-2024) but the calibration map is NOT regime-stable
(3 ECE passes out of 16 folds; one catastrophic 5m 2022 fold at ECE
0.227 with logloss beat -0.024). Reviewer 2026-05-26: the catastrophe
was extreme calibration staleness, not model collapse — accuracy was
still +20pp in that fold. The frozen 2016-2021 sigmoid map was simply
wrong for the Fed bear regime.

Live, you would never run with a frozen calibration map. This script
tests the ADAPTIVE alternative: train the base LGBM the same way
(anchored expanding window), then fit the calibration sigmoid on a
ROLLING RECENT slice of train data — the K most-recent days — and
apply it to test. Optionally key the calibration map on VIX tercile so
high-vol regimes use a high-vol-fit sigmoid.

Modes:
  --calibration-mode=rolling
      Fit sigmoid on last K train days (default K=120, ~6 months).

  --calibration-mode=vix-tercile
      Fit 3 separate sigmoids — one per VIX tercile in train — and at
      inference, apply the sigmoid that matches the test bar's
      vix_tercile. Falls back to overall-train sigmoid if a tercile
      has < MIN_CAL_BARS.

  --calibration-mode=rolling-vix
      Combine: per-VIX-tercile sigmoids fit on each tercile's most
      recent K bars in train. The "what would a daily-recalibrated
      live system look like" mode.

The base LGBM is identical across modes — only the post-hoc calibration
differs. This isolates the calibration question from the model
question. If adaptive passes ECE in regimes where static failed, the
probability product is rescued. If not, fall back to ranks-only.

Run:
  python -m gcp.research.strat_engine.strat_walk_forward_adaptive \\
      --ticker IWM --tf 30m --calibration-mode rolling --rolling-days 120
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
    DEFAULT_CV, DEFAULT_ECE_CEILING,
    GCS_BUCKET_DEFAULT, gcs_model_prefix,
)
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
from gcp.research.strat_engine.strat_pred_train import (
    featurize, make_lgbm, expected_calibration_error,
)
from gcp.research.strat_engine.strat_walk_forward import (
    DEFAULT_CUTOFFS, MIN_TEST_BARS, base_rate_logloss, _gcs_upload,
)
from google.cloud import storage as gcs
from lib.logging_config import setup_logging
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

setup_logging()
log = logging.getLogger(__name__)


# Minimum bars to fit a per-segment calibration sigmoid. Below this we
# fall back to the overall-train sigmoid so the per-segment map isn't
# fit on noise.
MIN_CAL_BARS = 300

# Default rolling-window length for rolling and rolling-vix modes.
# 120 trading days ≈ 6 calendar months, long enough to fit a stable
# sigmoid (~6k bars for 30m, ~24k bars for 5m) and short enough to
# track regime drift.
DEFAULT_ROLLING_DAYS = 120


def _fit_sigmoid_multiclass(logits_or_proba: np.ndarray,
                              y_idx: np.ndarray) -> dict:
    """Fit a per-class one-vs-rest sigmoid (Platt) on uncalibrated probs.

    Returns a dict of {class_idx: (a, b)} where calibrated_p_class_i =
    sigmoid(a * raw_p_class_i + b). At inference, apply per-class and
    renormalize so probabilities sum to 1.

    This mirrors what CalibratedClassifierCV(method='sigmoid') does
    internally but lets us fit it on an arbitrary slice (rolling-recent
    or VIX-tercile-conditional) of the train set.
    """
    if len(y_idx) < MIN_CAL_BARS:
        return None
    n_classes = logits_or_proba.shape[1]
    calibrators = {}
    for k in range(n_classes):
        y_k = (y_idx == k).astype(int)
        if y_k.sum() == 0 or y_k.sum() == len(y_k):
            calibrators[k] = None  # degenerate; skip
            continue
        # Use raw probabilities as input features to a single-feature LR
        X_k = logits_or_proba[:, k].reshape(-1, 1)
        lr = LogisticRegression(C=1.0, solver="lbfgs")
        lr.fit(X_k, y_k)
        calibrators[k] = lr
    return calibrators


def _apply_sigmoid_multiclass(calibrators: dict,
                                raw_proba: np.ndarray) -> np.ndarray:
    """Apply per-class sigmoid map then renormalize so rows sum to 1."""
    if calibrators is None:
        return raw_proba
    n_rows, n_classes = raw_proba.shape
    cal = np.zeros_like(raw_proba)
    for k in range(n_classes):
        lr = calibrators.get(k)
        if lr is None:
            cal[:, k] = raw_proba[:, k]
        else:
            cal[:, k] = lr.predict_proba(raw_proba[:, k].reshape(-1, 1))[:, 1]
    # Renormalize — sigmoid maps are independent so columns won't sum to 1
    row_sums = cal.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    return cal / row_sums


def _get_calibration_slice(df_train: pd.DataFrame,
                             X_train: np.ndarray, y_train: np.ndarray,
                             vix_terciles: np.ndarray,
                             mode: str, rolling_days: int,
                             vix_tercile_target: str | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Return (X_cal, y_cal) — the slice of train used to fit the sigmoid.

    static: returns full train.
    rolling: last `rolling_days` of train.
    vix-tercile: only rows where vix_tercile == vix_tercile_target.
    rolling-vix: last `rolling_days` of train, filtered to vix_tercile_target.
    """
    train_dates = df_train["bar_date"].values
    if mode == "static":
        return X_train, y_train

    if mode == "rolling":
        if len(train_dates) == 0:
            return X_train, y_train
        cutoff = pd.Timestamp(train_dates.max()) - pd.Timedelta(days=rolling_days)
        cutoff_d = cutoff.date()
        mask = np.array([d >= cutoff_d for d in train_dates])
        return X_train[mask], y_train[mask]

    if mode == "vix-tercile":
        if vix_tercile_target is None:
            return X_train, y_train
        mask = vix_terciles == vix_tercile_target
        return X_train[mask], y_train[mask]

    if mode == "rolling-vix":
        if vix_tercile_target is None:
            return X_train, y_train
        cutoff = pd.Timestamp(train_dates.max()) - pd.Timedelta(days=rolling_days)
        cutoff_d = cutoff.date()
        date_mask = np.array([d >= cutoff_d for d in train_dates])
        vix_mask = vix_terciles == vix_tercile_target
        mask = date_mask & vix_mask
        return X_train[mask], y_train[mask]

    raise ValueError(f"unknown calibration mode: {mode}")


def train_and_evaluate_fold_adaptive(
        X_full: np.ndarray, y_full: np.ndarray,
        bar_dates: np.ndarray, vix_terciles: np.ndarray,
        df_full: pd.DataFrame,
        train_end: str, test_end: str,
        mode: str, rolling_days: int,
        lgbm_n_jobs: int) -> dict:
    """ONE fold with adaptive recalibration.

    Pipeline:
      1. Train base LGBM on full anchored window (same as static).
      2. Generate uncalibrated probs on train.
      3. Per mode, fit sigmoid(s) on a selected SLICE of train.
      4. Apply calibration to test predictions.
    """
    train_end_dt = np.datetime64(train_end)
    test_end_dt = np.datetime64(test_end)
    train_mask = bar_dates < train_end_dt
    test_mask = (bar_dates >= train_end_dt) & (bar_dates < test_end_dt)
    n_train = int(train_mask.sum())
    n_test = int(test_mask.sum())
    if n_test < MIN_TEST_BARS:
        return {"fold": f"{train_end}..{test_end}",
                "n_test": n_test, "n_train": n_train,
                "mode": mode, "status": "SKIP_THIN"}

    X_tr = X_full[train_mask]
    X_te = X_full[test_mask]
    y_tr = y_full[train_mask]
    y_te = y_full[test_mask]
    df_tr = df_full.iloc[np.where(train_mask)[0]].reset_index(drop=True)
    vix_te = vix_terciles[test_mask]
    vix_tr = vix_terciles[train_mask]

    # 1. Base model — exactly the same training as static walk-forward,
    # WITHOUT internal calibration. We do calibration manually below so
    # we control which slice fits the sigmoid.
    base = make_lgbm(class_weight=None, n_jobs=lgbm_n_jobs)
    base.fit(X_tr, y_tr)

    # 2. Uncalibrated probs on train + test
    raw_tr = base.predict_proba(X_tr)
    raw_te = base.predict_proba(X_te)

    # 3. Fit calibrator(s) per mode
    if mode == "none":
        # No post-hoc calibration — production-config under the "drop the
        # sigmoid" finding. The reported "ECE" is identical to raw_ECE; this
        # mode exists to verify the production code path (no
        # CalibratedClassifierCV wrapper) reproduces the raw column we
        # measured under the other modes.
        proba = raw_te
        y_cal_aligned = y_tr  # for n_cal_slice reporting consistency
    elif mode in ("vix-tercile", "rolling-vix"):
        # Per-tercile sigmoids — fit one per VIX tercile present in train.
        # Sample-starvation watch: high-VIX is the rare regime that motivates
        # these modes — so a tight rolling-vix window in a calm pre-stress
        # period (e.g. Sep-Dec 2021 before the Feb 2022 vol expansion) may
        # have very few HIGH bars. Log per-tercile sample counts so a
        # downstream pass/fail isn't read from a 60-bar fit.
        cal_maps = {}
        unique_terciles = pd.Series(vix_tr).dropna().unique().tolist()
        tercile_sample_counts = {}
        for tercile in unique_terciles:
            X_cal, y_cal = _get_calibration_slice(
                df_tr, X_tr, y_tr, vix_tr, mode, rolling_days,
                vix_tercile_target=tercile)
            tercile_sample_counts[tercile] = int(len(y_cal))
            if len(y_cal) < MIN_CAL_BARS:
                log.warning("  tercile=%s: n_cal=%d < MIN_CAL_BARS=%d — SKIP, will fall back to overall sigmoid",
                            tercile, len(y_cal), MIN_CAL_BARS)
                continue
            log.info("  tercile=%s: fitting sigmoid on n_cal=%d bars",
                     tercile, len(y_cal))
            # Use base.predict_proba on the calibration slice — need raw
            # probabilities aligned with the slice
            # Map the slice back to indices in X_tr
            if mode == "vix-tercile":
                slice_mask = vix_tr == tercile
            else:  # rolling-vix
                train_dates_arr = df_tr["bar_date"].values
                cutoff_d = (pd.Timestamp(train_dates_arr.max())
                            - pd.Timedelta(days=rolling_days)).date()
                date_mask = np.array([d >= cutoff_d for d in train_dates_arr])
                slice_mask = (vix_tr == tercile) & date_mask
            raw_cal = raw_tr[slice_mask]
            cal_maps[tercile] = _fit_sigmoid_multiclass(raw_cal, y_tr[slice_mask])

        # Overall fallback for test bars whose vix_tercile has no map
        overall_cal = _fit_sigmoid_multiclass(raw_tr, y_tr)

        # Apply per test row
        proba = np.zeros_like(raw_te)
        for tercile, cal in cal_maps.items():
            row_mask = vix_te == tercile
            if row_mask.sum() == 0 or cal is None:
                continue
            proba[row_mask] = _apply_sigmoid_multiclass(cal, raw_te[row_mask])
        # Rows whose tercile has no fitted map (e.g. NaN vix or rare tercile)
        # → overall fallback
        unfilled = (proba.sum(axis=1) == 0)
        if unfilled.any():
            proba[unfilled] = _apply_sigmoid_multiclass(overall_cal, raw_te[unfilled])
    else:
        # static / rolling — one sigmoid for the whole test slice
        X_cal, y_cal = _get_calibration_slice(
            df_tr, X_tr, y_tr, vix_tr, mode, rolling_days)
        # Need raw probs aligned with X_cal — easiest is to recompute
        # the slice mask
        if mode == "static":
            raw_cal = raw_tr
            y_cal_aligned = y_tr
        else:  # rolling
            train_dates_arr = df_tr["bar_date"].values
            if len(train_dates_arr) == 0:
                raw_cal = raw_tr
                y_cal_aligned = y_tr
            else:
                cutoff_d = (pd.Timestamp(train_dates_arr.max())
                            - pd.Timedelta(days=rolling_days)).date()
                date_mask = np.array([d >= cutoff_d for d in train_dates_arr])
                raw_cal = raw_tr[date_mask]
                y_cal_aligned = y_tr[date_mask]

        cal = _fit_sigmoid_multiclass(raw_cal, y_cal_aligned)
        proba = _apply_sigmoid_multiclass(cal, raw_te)

    # 4. Metrics
    ll = float(log_loss(y_te, proba, labels=list(range(len(LABEL_CLASSES)))))
    base_ll = base_rate_logloss(y_tr, y_te)
    pred = np.argmax(proba, axis=1)
    acc = float((pred == y_te).mean())
    base_acc = float((y_te == int(np.bincount(y_tr, minlength=len(LABEL_CLASSES)).argmax())).mean())
    ece, ece_bins = expected_calibration_error(y_te, proba, n_bins=10)

    # Also compute raw (uncalibrated) ECE for comparison — tells us how
    # much calibration is helping vs the base model alone.
    raw_ece, _ = expected_calibration_error(y_te, raw_te, n_bins=10)

    return {
        "fold": f"{train_end}..{test_end}",
        "mode": mode,
        "n_train": n_train,
        "n_test": n_test,
        "n_cal_slice": int(len(y_cal_aligned)) if mode in ("static", "rolling", "none") else None,
        "tercile_sample_counts": tercile_sample_counts if mode in ("vix-tercile", "rolling-vix") else None,
        "logloss": ll,
        "base_logloss": base_ll,
        "beat": base_ll - ll,
        "accuracy": acc,
        "base_accuracy": base_acc,
        "accuracy_beat_pp": (acc - base_acc) * 100,
        "ece": float(ece),
        "raw_ece": float(raw_ece),
        "ece_bins": ece_bins,
        "status": "OK",
    }


def walk_forward_adaptive(engine, ticker: str, tf: str,
                            mode: str = "rolling",
                            rolling_days: int = DEFAULT_ROLLING_DAYS,
                            cutoffs: list[str] = None) -> dict:
    cutoffs = cutoffs or DEFAULT_CUTOFFS
    log.info("=" * 70)
    log.info("ADAPTIVE WALK-FORWARD  %s %s  mode=%s  rolling_days=%d",
             ticker, tf, mode, rolling_days)
    log.info("=" * 70)
    log.info("cutoffs: %s", " | ".join(cutoffs))

    df = load_labeled_dataset(engine, ticker, tf)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
    log.info("loaded full dataset: %d rows  (%s..%s)",
             len(df), df["bar_date"].min(), df["bar_date"].max())

    # VIX tercile per row — required for vix-tercile / rolling-vix modes.
    # If absent, fall back to rolling-only.
    if "vix_tercile" not in df.columns:
        log.warning("vix_tercile column missing; VIX-keyed modes will fall back to rolling")
        df["vix_tercile"] = None
    vix_terciles = df["vix_tercile"].astype("object").values

    # Featurize once — same as static walk-forward
    t0 = time.time()
    X_df, feature_cols = featurize(df)
    X_full = X_df.values.astype(np.float32, copy=False)
    y_full = df[LABEL_COL].map(LABEL_TO_IDX).values.astype(np.int64)
    # bar_date is a Series of Python `date` objects after load_labeled_dataset
    # → pd.DatetimeIndex first, then to day-precision datetime64.
    bar_dates_arr = pd.DatetimeIndex(df["bar_date"]).values.astype("datetime64[D]")
    log.info("featurize-once: %d rows × %d cols in %.1fs",
             X_full.shape[0], X_full.shape[1], time.time() - t0)

    cores = max(1, os.cpu_count() or 1)
    # Adaptive doesn't use CV (we own the calibration), so LGBM can take
    # all cores.
    lgbm_n_jobs = cores
    log.info("threading: cores=%d, lgbm n_jobs=%d (no internal CV)",
             cores, lgbm_n_jobs)

    folds = []
    for i, cut in enumerate(cutoffs):
        test_end = cutoffs[i + 1] if i + 1 < len(cutoffs) else \
            str(pd.Timestamp(df["bar_date"].max()) + pd.Timedelta(days=1))[:10]
        log.info("─" * 70)
        log.info("fold %d/%d  train<%s  test=[%s..%s)  mode=%s",
                 i + 1, len(cutoffs), cut, cut, test_end, mode)
        try:
            fold_t0 = time.time()
            r = train_and_evaluate_fold_adaptive(
                X_full, y_full, bar_dates_arr, vix_terciles, df,
                cut, test_end, mode, rolling_days, lgbm_n_jobs)
            r["fold_seconds"] = round(time.time() - fold_t0, 1)
            folds.append(r)
            if r["status"] == "OK":
                log.info("  n_train=%d  n_test=%d  cal_slice=%s",
                         r["n_train"], r["n_test"],
                         r.get("n_cal_slice", "per-tercile"))
                log.info("  logloss=%.4f  base=%.4f  beat=%+.4f",
                         r["logloss"], r["base_logloss"], r["beat"])
                log.info("  accuracy=%.3f  base=%.3f  Δ=%+.1fpp",
                         r["accuracy"], r["base_accuracy"], r["accuracy_beat_pp"])
                log.info("  ECE=%.4f  raw_ECE=%.4f  ceiling=%.3f  %s",
                         r["ece"], r["raw_ece"], DEFAULT_ECE_CEILING,
                         "PASS" if r["ece"] <= DEFAULT_ECE_CEILING else "FAIL")
            else:
                log.info("  %s (n_test=%d < %d)", r["status"], r["n_test"], MIN_TEST_BARS)
        except Exception as e:
            log.exception("fold %s FAILED: %s", cut, e)
            folds.append({"fold": f"{cut}..{test_end}", "mode": mode,
                          "status": "ERROR", "error": str(e)})

    # Summary
    log.info("=" * 70)
    log.info("ADAPTIVE WALK-FORWARD SUMMARY  %s %s  mode=%s", ticker, tf, mode)
    log.info("=" * 70)
    log.info("%-25s %8s %8s %8s %8s %8s",
             "fold", "n_test", "beat", "acc_Δpp", "ece", "raw_ece")
    log.info("-" * 70)
    ok_folds = [f for f in folds if f.get("status") == "OK"]
    for f in folds:
        if f.get("status") == "OK":
            log.info("%-25s %8d %+8.4f %+8.1f %8.4f %8.4f",
                     f["fold"], f["n_test"], f["beat"],
                     f["accuracy_beat_pp"], f["ece"], f["raw_ece"])
        else:
            log.info("%-25s %s", f["fold"], f.get("status", "?"))
    if ok_folds:
        eces = [f["ece"] for f in ok_folds]
        raw_eces = [f["raw_ece"] for f in ok_folds]
        passes = sum(1 for f in ok_folds if f["ece"] <= DEFAULT_ECE_CEILING)
        log.info("-" * 70)
        log.info("ECE range: [%.4f .. %.4f]  median=%.4f  passes=%d/%d",
                 min(eces), max(eces), float(np.median(eces)), passes, len(ok_folds))
        log.info("raw ECE range: [%.4f .. %.4f]  median=%.4f",
                 min(raw_eces), max(raw_eces), float(np.median(raw_eces)))

    # Persist
    summary = {
        "ticker": ticker, "tf": tf,
        "calibration_mode": mode, "rolling_days": rolling_days,
        "cutoffs": cutoffs,
        "min_test_bars": MIN_TEST_BARS, "min_cal_bars": MIN_CAL_BARS,
        "folds": folds,
        "computed_at": pd.Timestamp.utcnow().isoformat(),
    }
    prefix = gcs_model_prefix(ticker, tf)
    blob = f"{prefix}/walk_forward_adaptive_{mode}_{int(time.time())}.json"
    _gcs_upload(json.dumps(summary, indent=2, default=str).encode(), blob)
    log.info("saved: gs://%s/%s",
             os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT), blob)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="30m", choices=list(TIMEFRAMES))
    p.add_argument("--calibration-mode", default="rolling",
                   choices=["none", "static", "rolling", "vix-tercile", "rolling-vix"])
    p.add_argument("--rolling-days", type=int, default=DEFAULT_ROLLING_DAYS)
    p.add_argument("--cutoffs", default=None,
                   help="Comma-separated YYYY-MM-DD cutoffs (default: regime-spanning)")
    args = p.parse_args()
    cutoffs = args.cutoffs.split(",") if args.cutoffs else None
    engine = get_engine()
    walk_forward_adaptive(engine, args.ticker, args.tf,
                            mode=args.calibration_mode,
                            rolling_days=args.rolling_days,
                            cutoffs=cutoffs)


if __name__ == "__main__":
    main()
