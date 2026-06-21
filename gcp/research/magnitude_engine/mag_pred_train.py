"""Magnitude Engine — model + featurize + ECE.

Parallels strat_engine.strat_pred_train. Same LightGBM hyperparameters,
same calibration default (none — raw softmax), same ECE measurement.
Differs ONLY in the target column and the feature drop set.

The DEFAULT_CALIBRATION decision is preserved because the underlying
model class (LightGBM multiclass with cross-entropy) is the same; the
target being different does not change whether Platt-on-top is double-
calibration. We will still measure ECE per fold and switch if the new
target breaches the per-tf ceiling (per the spec).
"""
from __future__ import annotations
import logging

import numpy as np
import pandas as pd

from gcp.research.magnitude_engine.mag_config import (
    LABEL_COL, LABEL_CLASSES,
)
from gcp.research.strat_engine.strat_config import (
    CATEGORICAL_FEATURES, LABEL_COL as STRAT_LABEL_COL,
)

# lightgbm is a heavy dep installed only in the research Cloud Run image
# (requirements-research.txt), not in requirements.txt that CI uses.
# Lazy-import inside make_lgbm() so tests that only exercise the gate
# functions (expected_calibration_error / decisive_call_hit_rate /
# explosive_lift) can import this module without LightGBM installed.

log = logging.getLogger(__name__)


def featurize(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """One-hot categoricals; numeric otherwise. Drops forward-looking +
    label columns. Returns (X, feature_cols)."""
    # Only one-hot the categoricals that ACTUALLY exist in this frame.
    # phase1+ datasets may not have all of them (4h is dropped from scope
    # so no schema mismatch, but defensive coding is cheap).
    cat_present = [c for c in CATEGORICAL_FEATURES if c in df.columns]
    enc = pd.get_dummies(df, columns=cat_present, dummy_na=False, dtype=np.int8)

    # All-NaN columns coming from pd.read_sql arrive with dtype=object,
    # which the numeric-dtype filter below would drop. That's correct
    # at training (no signal), but BREAKS the train-vs-inference contract
    # when a column is mostly-populated at training and 100% NULL during
    # an inference window — feature_cols.txt records the column as a
    # numeric feature, but featurize at inference drops it, and the
    # mag_inference alignment check then raises 'feature drift' on every
    # cron. Pre-coerce these to float64 so the dtype filter accepts them;
    # the subsequent `.fillna(0)` produces a zero column with the same
    # semantics training would have produced for sparse-NULL rows.
    # Surfaced 2026-06-19 when mag_inference rejected vix_close=NULL on
    # the recently-backfilled strat_features_5m bars (root-cause: upstream
    # VIX join in strat_data_builder is broken for new rows; tracked
    # separately).
    for c in enc.columns:
        if enc[c].dtype == object and enc[c].isna().all():
            enc[c] = enc[c].astype(np.float64)

    drop = {
        "ticker", "ts", "tf", "bar_date",
        "open", "high", "low", "close", "volume",
        "fwd_close_5bars", "fwd_close_15bars", "fwd_close_30bars", "fwd_close_60bars",
        "fwd_ret_5bars_bps", "fwd_ret_15bars_bps", "fwd_ret_30bars_bps", "fwd_ret_60bars_bps",
        "computed_at", "trigger_high", "trigger_low",
        "is_continuation", "is_reversal", "is_inside", "strat_setup",
        "prev_strat_candle",
        "next_open", "next_close", "next_high", "next_low",
        LABEL_COL,
        STRAT_LABEL_COL,
        # Phase-1 intermediate (kept in df for debug, NOT used as a feature)
        "atr_5_simple",
        "prev_daily_range",
        # Target-construction intermediate — never a feature (would leak
        # the magnitude target's denominator directly).
        "atr_20_computed",
    }
    cols = [c for c in enc.columns
            if c not in drop and enc[c].dtype in
            (np.float64, np.int64, np.int32, np.int8, np.float32)]
    feat = enc[cols].replace([np.inf, -np.inf], np.nan)

    # Missing-data indicators (CLAUDE.md §3.7): a value imputed to 0 must
    # stay distinguishable from a genuine 0. For every feature column that
    # carries any missing/inf value, emit a companion `<col>__isna` flag
    # (1.0 where the source was NaN/inf, else 0.0) BEFORE the value column
    # is imputed to 0. The model learns from the flag wherever missingness
    # varies in the training window; fully-populated columns get no flag.
    # Indicators are appended to feature_cols so a retrain adopts them;
    # existing models simply ignore the extra columns at inference
    # (mag_inference selects enc[feature_cols]). This replaces the prior
    # behaviour where an all-NULL column (e.g. vix_close on a broken
    # upstream join, 2026-06-19) silently became an all-zero "calm market"
    # feature indistinguishable from a real reading.
    na_mask = feat.isna()
    miss_cols = [c for c in cols if bool(na_mask[c].any())]
    X = feat.fillna(0).astype(np.float32)
    if miss_cols:
        ind = pd.DataFrame(
            {f"{c}__isna": na_mask[c].astype(np.float32) for c in miss_cols},
            index=X.index,
        )
        X = pd.concat([X, ind], axis=1)
        cols = cols + list(ind.columns)
    return X, cols


def expected_calibration_error(y_true_idx: np.ndarray, y_proba: np.ndarray,
                                n_bins: int = 10) -> tuple[float, list]:
    """Multiclass ECE — bin by predicted-class confidence (max proba).
    Identical to strat_engine's implementation."""
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


def decisive_call_hit_rate(y_true_idx: np.ndarray, y_proba: np.ndarray,
                            thresholds: tuple[float, ...]) -> dict:
    """For each threshold τ, restrict to bars where max-proba >= τ and
    report (n, accuracy).  Success-bar gate 3 wants the accuracy to rise
    monotonically across τ."""
    pred = np.argmax(y_proba, axis=1)
    conf = y_proba.max(axis=1)
    out = {}
    for t in thresholds:
        mask = conf >= t
        n = int(mask.sum())
        if n == 0:
            out[f"{t:.2f}"] = {"n": 0, "accuracy": None}
        else:
            out[f"{t:.2f}"] = {
                "n": n,
                "accuracy": float((pred[mask] == y_true_idx[mask]).mean()),
            }
    return out


def explosive_lift(y_true_idx: np.ndarray, y_proba: np.ndarray,
                    explosive_idx: int) -> dict:
    """Lift of the EXPLOSIVE bucket = P(true=EXPLOSIVE | predicted=EXPLOSIVE)
    / P(true=EXPLOSIVE).  Spec gate 4 wants this >= 1.5."""
    pred = np.argmax(y_proba, axis=1)
    base_rate = float((y_true_idx == explosive_idx).mean()) if len(y_true_idx) else 0.0
    pred_explosive_mask = pred == explosive_idx
    n_pred = int(pred_explosive_mask.sum())
    if n_pred == 0:
        precision = None
        lift = None
    else:
        precision = float((y_true_idx[pred_explosive_mask] == explosive_idx).mean())
        lift = precision / base_rate if base_rate > 0 else None
    return {
        "base_rate": base_rate,
        "n_predicted": n_pred,
        "precision": precision,
        "lift": lift,
    }


def make_lgbm(class_weight: str | None = None, n_jobs: int = -1,
               random_state: int | None = None):
    """Base LightGBM classifier — same hyperparameters as strat_engine so
    a phase-pass is attributable to feature signal, not hyperparameter
    differences.

    `random_state` override is provided so replication runs can vary the
    seed without changing any other config. Default reads MAG_SEED env
    var; falls back to 42 (the locked production seed). Replication runs
    set MAG_SEED=<other> at dispatch time and never call this with an
    explicit value — the override path is reserved for unit tests.

    Returns: lightgbm.LGBMClassifier. Lazy-imported so this module can
    load in CI environments without the lightgbm package.
    """
    import os
    import lightgbm as lgb
    if random_state is None:
        try:
            random_state = int(os.environ.get("MAG_SEED", "42"))
        except ValueError:
            random_state = 42
    return lgb.LGBMClassifier(
        objective="multiclass", num_class=len(LABEL_CLASSES),
        n_estimators=300, learning_rate=0.05, max_depth=6,
        num_leaves=31, min_child_samples=100,
        class_weight=class_weight,
        random_state=random_state, verbose=-1, n_jobs=n_jobs,
    )
