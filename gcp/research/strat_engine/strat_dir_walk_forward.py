"""Strat Engine — DIRECTION-target walk-forward.

Trains a binary LightGBM classifier with target = (next_close > next_open).
Same features, same hyperparameters, same anchored expanding cutoffs,
same featurize-once-then-slice harness as the TYPE walk-forward. No
post-hoc calibration (the TYPE study showed sigmoid hurt in 24/24 folds).

The question this answers: does the strat-engine's feature set carry a
regime-stable edge on next-bar BODY direction (close vs open), separate
from the structure edge the TYPE model already validated?

Run:
  python -m gcp.research.strat_engine.strat_dir_walk_forward \\
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

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gcp.database import get_engine
from gcp.research.strat_engine.strat_config import (
    TICKERS, TIMEFRAMES,
    DEFAULT_ECE_CEILING,
    GCS_BUCKET_DEFAULT, gcs_model_prefix,
)
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
from gcp.research.strat_engine.strat_pred_train import (
    featurize, expected_calibration_error,
)
from gcp.research.strat_engine.strat_walk_forward import (
    DEFAULT_CUTOFFS, MIN_TEST_BARS, _gcs_upload,
)
from gcp.research.direction_program.phase2_features import (
    build_family_columns, prune_feature_cols, _load_peers,
)
from gcp.research.direction_program.phase2_prune_sets import NEAR_DEAD
from google.cloud import storage as gcs
from lib.logging_config import setup_logging
from sklearn.metrics import log_loss

setup_logging()
log = logging.getLogger(__name__)

AXIS = "direction"


def make_direction_lgbm(n_jobs: int = -1) -> lgb.LGBMClassifier:
    """Binary LightGBM. Same hyperparameters as the TYPE model except
    objective=binary instead of multiclass."""
    return lgb.LGBMClassifier(
        objective="binary",
        n_estimators=300, learning_rate=0.05, max_depth=6,
        num_leaves=31, min_child_samples=100,
        random_state=42, verbose=-1, n_jobs=n_jobs,
    )


def base_rate_logloss_binary(y_train: np.ndarray, y_test: np.ndarray) -> float:
    """Log-loss of always-predicting-train-class-prior on test bars."""
    prior_up = float(y_train.mean()) if len(y_train) else 0.5
    prior_up = max(min(prior_up, 0.9999), 0.0001)  # avoid log(0)
    p = np.full(len(y_test), prior_up)
    return float(log_loss(y_test, np.vstack([1 - p, p]).T, labels=[0, 1]))


def train_and_evaluate_fold(X_full: np.ndarray, y_full: np.ndarray,
                              bar_dates: np.ndarray,
                              train_end: str, test_end: str,
                              lgbm_n_jobs: int) -> dict:
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

    model = make_direction_lgbm(n_jobs=lgbm_n_jobs)
    model.fit(X_tr, y_tr)

    proba = model.predict_proba(X_te)  # shape (n, 2): [:, 1] is P(up)
    p_up = proba[:, 1]
    pred = (p_up >= 0.5).astype(int)

    ll = float(log_loss(y_te, proba, labels=[0, 1]))
    base_ll = base_rate_logloss_binary(y_tr, y_te)
    acc = float((pred == y_te).mean())
    base_acc = float(max(y_tr.mean(), 1 - y_tr.mean()))
    # Use the binary ECE — confidence is max(p_up, 1-p_up)
    ece, _ = expected_calibration_error(y_te, proba, n_bins=10)

    # Decisive-call hit rate at confidence thresholds
    thresh_rates = {}
    for thresh in [0.55, 0.60, 0.65, 0.70]:
        decisive = np.maximum(p_up, 1 - p_up) >= thresh
        n_dec = int(decisive.sum())
        if n_dec > 0:
            thresh_rates[thresh] = {
                "n": n_dec, "hit_rate": float((pred[decisive] == y_te[decisive]).mean())
            }
        else:
            thresh_rates[thresh] = {"n": 0, "hit_rate": None}

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
        "thresh_rates": thresh_rates,
        "up_share_train": float(y_tr.mean()),
        "up_share_test": float(y_te.mean()),
        "status": "OK",
    }


def walk_forward_direction(engine, ticker: str, tf: str,
                              cutoffs: list[str] = None,
                              features: str = "") -> dict:
    cutoffs = cutoffs or DEFAULT_CUTOFFS
    log.info("=" * 70)
    log.info("DIRECTION WALK-FORWARD  %s %s  %d cutoffs", ticker, tf, len(cutoffs))
    log.info("=" * 70)
    log.info("cutoffs: %s", " | ".join(cutoffs))

    df = load_labeled_dataset(engine, ticker, tf, include_next_bar_ohlc=True)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
    # Drop bars with flat-close (ambiguous direction)
    flat_mask = df["next_close"] == df["next_open"]
    n_flat = int(flat_mask.sum())
    if n_flat > 0:
        log.info("dropping %d bars with next_close == next_open (ambiguous direction)", n_flat)
        df = df[~flat_mask].copy()
    log.info("loaded full dataset: %d rows (%s..%s)",
             len(df), df["bar_date"].min(), df["bar_date"].max())

    t0 = time.time()
    X_df, feature_cols = featurize(df)

    # ── Phase-2 feature families (CLAUDE.md Rule 3.7: NaN, never fillna(0),
    # on the new columns) — attached AFTER featurize so they never hit its
    # .fillna(0). features="" reproduces the baseline byte-for-byte: fams
    # is empty, no prune, add is empty, build_family_columns is never
    # called, X_df/feature_cols pass through unchanged. ──
    fams = set(features.split(",")) - {""}
    if "prune" in fams:
        keep = prune_feature_cols(feature_cols, NEAR_DEAD[AXIS])
        X_df = X_df[keep]; feature_cols = keep
    add = fams - {"prune"}
    peers = None
    if "cross_asset" in add:
        peers = _load_peers(engine, ticker, tf)
    if add:
        new_df, new_cols = build_family_columns(
            df, add, AXIS, ticker, tf, engine, peers)
        X_df = pd.concat([X_df.reset_index(drop=True), new_df.reset_index(drop=True)], axis=1)
        feature_cols = feature_cols + new_cols
    if fams:
        log.info("phase2 features active: %s  (n_cols=%d)",
                 ",".join(sorted(fams)), len(feature_cols))

    X_full = X_df.values.astype(np.float32, copy=False)
    y_full = (df["next_close"] > df["next_open"]).astype(np.int64).values
    bar_dates_arr = pd.DatetimeIndex(df["bar_date"]).values.astype("datetime64[D]")
    log.info("featurize-once: %d rows × %d cols in %.1fs",
             X_full.shape[0], X_full.shape[1], time.time() - t0)
    log.info("global up-share: %.3f  (down-share: %.3f)",
             float(y_full.mean()), float(1 - y_full.mean()))

    cores = max(1, os.cpu_count() or 1)
    lgbm_n_jobs = cores
    log.info("threading: cores=%d, lgbm n_jobs=%d (no internal CV — calibration=none)",
             cores, lgbm_n_jobs)

    folds = []
    for i, cut in enumerate(cutoffs):
        test_end = cutoffs[i + 1] if i + 1 < len(cutoffs) else \
            str(pd.Timestamp(df["bar_date"].max()) + pd.Timedelta(days=1))[:10]
        log.info("─" * 70)
        log.info("fold %d/%d  train<%s  test=[%s..%s)",
                 i + 1, len(cutoffs), cut, cut, test_end)
        try:
            fold_t0 = time.time()
            r = train_and_evaluate_fold(
                X_full, y_full, bar_dates_arr, cut, test_end, lgbm_n_jobs)
            r["fold_seconds"] = round(time.time() - fold_t0, 1)
            folds.append(r)
            if r["status"] == "OK":
                log.info("  n_train=%d  n_test=%d  up_share(train/test)=%.3f/%.3f",
                         r["n_train"], r["n_test"], r["up_share_train"], r["up_share_test"])
                log.info("  logloss=%.4f  base=%.4f  beat=%+.4f",
                         r["logloss"], r["base_logloss"], r["beat"])
                log.info("  accuracy=%.3f  base=%.3f  Δ=%+.1fpp",
                         r["accuracy"], r["base_accuracy"], r["accuracy_beat_pp"])
                log.info("  ECE=%.4f  ceiling=%.3f  %s",
                         r["ece"], DEFAULT_ECE_CEILING,
                         "PASS" if r["ece"] <= DEFAULT_ECE_CEILING else "FAIL")
                # Decisive-call hit rates
                for thresh, d in r["thresh_rates"].items():
                    if d["n"] > 0:
                        log.info("  decisive ≥%.2f: n=%d hit_rate=%.3f",
                                 thresh, d["n"], d["hit_rate"])
            else:
                log.info("  %s (n_test=%d)", r["status"], r["n_test"])
        except Exception as e:
            log.exception("fold %s FAILED: %s", cut, e)
            folds.append({"fold": f"{cut}..{test_end}", "status": "ERROR", "error": str(e)})

    # Summary
    log.info("=" * 70)
    log.info("DIRECTION WALK-FORWARD SUMMARY  %s %s", ticker, tf)
    log.info("=" * 70)
    ok = [f for f in folds if f.get("status") == "OK"]
    log.info("%-25s %8s %8s %8s %8s %8s",
             "fold", "n_test", "beat", "acc_Δpp", "ece", "dec≥0.60")
    log.info("-" * 70)
    for f in folds:
        if f.get("status") == "OK":
            dec60 = f["thresh_rates"].get(0.60, {}).get("hit_rate")
            dec60_str = f"{dec60:.3f}" if dec60 is not None else "—"
            log.info("%-25s %8d %+8.4f %+8.1f %8.4f %8s",
                     f["fold"], f["n_test"], f["beat"], f["accuracy_beat_pp"],
                     f["ece"], dec60_str)
        else:
            log.info("%-25s %s", f["fold"], f.get("status", "?"))

    if ok:
        beats = [f["beat"] for f in ok]
        accs = [f["accuracy_beat_pp"] for f in ok]
        eces = [f["ece"] for f in ok]
        ece_passes = sum(1 for f in ok if f["ece"] <= DEFAULT_ECE_CEILING)
        acc_positives = sum(1 for f in ok if f["accuracy_beat_pp"] > 0)
        log.info("-" * 70)
        log.info("logloss beat: median %+.4f  range [%+.4f .. %+.4f]",
                 float(np.median(beats)), min(beats), max(beats))
        log.info("accuracy beat: median %+.1fpp  positive %d/%d folds",
                 float(np.median(accs)), acc_positives, len(ok))
        log.info("ECE: median %.4f  passes %d/%d",
                 float(np.median(eces)), ece_passes, len(ok))

    # Persist
    summary = {
        "ticker": ticker, "tf": tf,
        "target": "direction (next_close > next_open)",
        "cutoffs": cutoffs,
        "calibration": "none",
        "min_test_bars": MIN_TEST_BARS,
        "folds": folds,
        "computed_at": pd.Timestamp.utcnow().isoformat(),
    }
    prefix = gcs_model_prefix(ticker, tf)
    blob = f"{prefix}/dir_walk_forward_{int(time.time())}.json"
    _gcs_upload(json.dumps(summary, indent=2, default=str).encode(), blob)
    log.info("saved: gs://%s/%s",
             os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT), blob)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--cutoffs", default=None)
    p.add_argument("--features", default="",
                   help="Comma-separated phase2 family names (prune, "
                        "options_iv, positioning, cross_asset, calendar). "
                        "Default empty = baseline (no phase2 change).")
    args = p.parse_args()
    cutoffs = args.cutoffs.split(",") if args.cutoffs else None
    engine = get_engine()
    walk_forward_direction(engine, args.ticker, args.tf, cutoffs=cutoffs,
                            features=args.features)


if __name__ == "__main__":
    main()
