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

import lightgbm as lgb

log = logging.getLogger(__name__)


def featurize(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """One-hot categoricals; numeric otherwise. Drops forward-looking +
    label columns. Returns (X, feature_cols)."""
    # Only one-hot the categoricals that ACTUALLY exist in this frame.
    # phase1+ datasets may not have all of them (4h is dropped from scope
    # so no schema mismatch, but defensive coding is cheap).
    cat_present = [c for c in CATEGORICAL_FEATURES if c in df.columns]
    enc = pd.get_dummies(df, columns=cat_present, dummy_na=False, dtype=np.int8)

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
    return (
        enc[cols].replace([np.inf, -np.inf], np.nan).fillna(0).astype(np.float32),
        cols,
    )


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
               random_state: int | None = None) -> lgb.LGBMClassifier:
    """Base LightGBM classifier — same hyperparameters as strat_engine so
    a phase-pass is attributable to feature signal, not hyperparameter
    differences.

    `random_state` override is provided so replication runs can vary the
    seed without changing any other config. Default reads MAG_SEED env
    var; falls back to 42 (the locked production seed). Replication runs
    set MAG_SEED=<other> at dispatch time and never call this with an
    explicit value — the override path is reserved for unit tests.
    """
    import os
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
