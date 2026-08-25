"""Feature-importance / SHAP audit for the DIRECTION and SIZE walk-forward
engines.

Answers: of the ~75-143 columns the baseline rides, which ones actually carry
the edge — and which are dead weight diluting it?

Production-faithful (CLAUDE.md Rule 3.6 — no throwaway harness): this reuses
the EXACT production feature path that produced the baseline —
  DIRECTION: strat_dataset.load_labeled_dataset -> strat_pred_train.featurize
             -> make_direction_lgbm, target (next_close > next_open)
  SIZE     : mag_dataset.load_magnitude_dataset(phase0) -> mag_pred_train.featurize
             -> make_lgbm(class_weight=resolve_class_weight), bucketed magnitude
and the SAME anchored expanding cutoffs and the SAME train/test masking as each
engine's train_and_evaluate_fold. Per fold we fit the identical model, then read
LightGBM gain importance and mean|SHAP| over the test slice, and average across
folds. It does NOT re-implement featurization, labels, or model config.
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
from gcp.research.strat_engine.strat_walk_forward import (
    DEFAULT_CUTOFFS, MIN_TEST_BARS, _gcs_upload,
)

log = logging.getLogger("direction.importance")

TICKERS = ("IWM", "SPY", "QQQ")


# ── Pure aggregation (unit-tested) ────────────────────────────────────────────
def aggregate_importance(feature_cols, per_fold_gain, per_fold_shap):
    """Average gain and mean|SHAP| across folds; return ranked by mean gain desc.

    per_fold_gain: list (folds) of list (features) of gain floats.
    per_fold_shap: list (folds) of {list (features) of mean|shap| floats, or None
                   for a fold whose SHAP failed}. May be empty for gain-only.
    Missing SHAP is reported as None, never as 0 (Rule 3.7 — no fabricated value).
    """
    G = np.asarray(per_fold_gain, dtype=float)          # (folds, features)
    mean_gain = G.mean(axis=0)

    shap_rows = [s for s in (per_fold_shap or []) if s is not None]
    if shap_rows:
        mean_shap = np.asarray(shap_rows, dtype=float).mean(axis=0)
    else:
        mean_shap = np.full(len(feature_cols), np.nan)

    order = np.argsort(mean_gain)[::-1]
    out = []
    for rank, i in enumerate(order, start=1):
        ms = mean_shap[i]
        out.append({
            "feature": feature_cols[i],
            "mean_gain": float(mean_gain[i]),
            "mean_abs_shap": (None if np.isnan(ms) else float(ms)),
            "rank": rank,
        })
    return out


def _fold_masks(bar_dates: np.ndarray, train_end: str, test_end: str):
    """Mirror train_and_evaluate_fold's split exactly (anchored expanding)."""
    tr = bar_dates < np.datetime64(train_end)
    te = (bar_dates >= np.datetime64(train_end)) & (bar_dates < np.datetime64(test_end))
    return tr, te


def _reduce_shap_to_features(sv, nfeat: int) -> np.ndarray:
    """Collapse any SHAP output to a length-nfeat mean|SHAP| vector.

    shap.TreeExplainer.shap_values returns different shapes by model/version:
      - binary      -> ndarray (n_samples, n_features)
      - multiclass  -> ndarray (n_samples, n_features, n_classes)  [newer]
                       OR list of n_classes arrays each (n_samples, n_features)
    We take |shap|, find the feature axis by matching nfeat, and average over
    every other axis (samples and, for multiclass, classes). Rank-preserving.
    """
    if isinstance(sv, list):
        sv = np.stack([np.asarray(a) for a in sv])       # (k, n, f)
    absv = np.abs(np.asarray(sv, dtype=float))
    feat_ax = next((ax for ax in reversed(range(absv.ndim))
                    if absv.shape[ax] == nfeat), absv.ndim - 1)
    return np.moveaxis(absv, feat_ax, -1).reshape(-1, nfeat).mean(axis=0)


def _mean_abs_shap(model, X: np.ndarray):
    """Length-nfeat mean|SHAP| for this fold. Returns None (logged) if SHAP
    raises — never a fabricated zero (Rule 3.7)."""
    try:
        import shap
        expl = shap.TreeExplainer(model.booster_)
        sv = expl.shap_values(X)
        return _reduce_shap_to_features(sv, X.shape[1]).tolist()
    except Exception as e:                       # analysis enrichment — log loud, don't fabricate
        log.warning("SHAP failed for this fold, recording None: %s", e)
        return None


def _load_axis(engine, axis: str, ticker: str, tf: str):
    """Return (X_full float32, y int64, bar_dates datetime64[D], feature_cols,
    make_model(y_tr)->estimator) using the axis's production path."""
    if axis == "direction":
        from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
        from gcp.research.strat_engine.strat_pred_train import featurize
        from gcp.research.strat_engine.strat_dir_walk_forward import make_direction_lgbm
        df = load_labeled_dataset(engine, ticker, tf, include_next_bar_ohlc=True)
        df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
        df = df[df["next_close"] != df["next_open"]].copy()   # drop flat (as engine does)
        X_df, cols = featurize(df)
        y = (df["next_close"] > df["next_open"]).astype(np.int64).values
        make = lambda y_tr: make_direction_lgbm(n_jobs=-1)
    elif axis == "size":
        from gcp.research.magnitude_engine.mag_dataset import load_magnitude_dataset
        from gcp.research.magnitude_engine.mag_pred_train import (
            featurize, make_lgbm, resolve_class_weight,
        )
        from gcp.research.magnitude_engine.mag_config import LABEL_COL, LABEL_TO_IDX
        df = load_magnitude_dataset(engine, ticker, tf, "phase0")
        df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
        X_df, cols = featurize(df)
        y = df[LABEL_COL].map(LABEL_TO_IDX).values.astype(np.int64)
        make = lambda y_tr: make_lgbm(class_weight=resolve_class_weight(y_tr), n_jobs=-1)
    else:
        raise ValueError(f"unknown axis {axis!r}")

    X_full = X_df.values.astype(np.float32, copy=False)
    bar_dates = pd.DatetimeIndex(df["bar_date"]).values.astype("datetime64[D]")
    return X_full, y, bar_dates, list(cols), make


def importance_for_axis(engine, axis: str, ticker: str, tf: str,
                        cutoffs=None) -> dict:
    cutoffs = cutoffs or DEFAULT_CUTOFFS
    X_full, y_full, bar_dates, cols, make = _load_axis(engine, axis, ticker, tf)
    log.info("[%s %s %s] %d rows × %d cols", axis, ticker, tf, X_full.shape[0], len(cols))

    per_fold_gain, per_fold_shap, n_ok = [], [], 0
    for i, cut in enumerate(cutoffs):
        test_end = cutoffs[i + 1] if i + 1 < len(cutoffs) else \
            str(pd.Timestamp(bar_dates.max()) + pd.Timedelta(days=1))[:10]
        tr, te = _fold_masks(bar_dates, cut, test_end)
        if int(te.sum()) < MIN_TEST_BARS:
            log.info("  fold %d SKIP_THIN (n_test=%d)", i + 1, int(te.sum()))
            continue
        model = make(y_full[tr])
        model.fit(X_full[tr], y_full[tr])
        gain = model.booster_.feature_importance(importance_type="gain")
        per_fold_gain.append(np.asarray(gain, dtype=float).tolist())
        per_fold_shap.append(_mean_abs_shap(model, X_full[te]))
        n_ok += 1
        log.info("  fold %d OK (n_train=%d n_test=%d)", i + 1, int(tr.sum()), int(te.sum()))

    if not per_fold_gain:
        raise RuntimeError(f"no usable folds for {axis} {ticker} {tf}")

    ranking = aggregate_importance(cols, per_fold_gain, per_fold_shap)
    return {"axis": axis, "ticker": ticker, "tf": tf,
            "n_folds_ok": n_ok, "n_features": len(cols), "ranking": ranking}


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Feature-importance/SHAP audit of the "
                                            "direction & size engines.")
    p.add_argument("--axes", default="direction,size")
    p.add_argument("--tickers", default="IWM,SPY,QQQ")
    p.add_argument("--tf", default="5m")
    p.add_argument("--top", type=int, default=25, help="rows to log per cell")
    args = p.parse_args()

    engine = get_engine()
    axes = [a.strip() for a in args.axes.split(",") if a.strip()]
    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]

    results = []
    for axis in axes:
        for tk in tickers:
            try:
                res = importance_for_axis(engine, axis, tk, args.tf)
            except Exception as e:
                log.exception("importance failed for %s %s: %s", axis, tk, e)
                continue
            results.append(res)
            log.info("=== TOP %d  %s %s %s  (%d folds, %d feats) ===",
                     args.top, axis, tk, args.tf, res["n_folds_ok"], res["n_features"])
            for r in res["ranking"][:args.top]:
                shap_s = "n/a" if r["mean_abs_shap"] is None else f"{r['mean_abs_shap']:.4f}"
                log.info("  %2d. gain=%12.1f shap=%8s  %s",
                         r["rank"], r["mean_gain"], shap_s, r["feature"])

    payload = json.dumps({"tf": args.tf, "results": results}, default=str)
    blob = f"direction-program/importance/importance_{args.tf}_{int(time.time())}.json"
    try:
        _gcs_upload(payload.encode(), blob)
        log.info("saved: gs://%s/%s",
                 os.environ.get("GCS_BUCKET", "adept-mountain-474619-d4-trading-data"), blob)
    except Exception as e:
        log.warning("GCS upload failed (results still in logs): %s", e)
    log.info("IMPORTANCE_DONE axes=%s tickers=%s cells=%d", axes, tickers, len(results))
    return results


if __name__ == "__main__":
    main()
