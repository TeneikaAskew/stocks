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
import os

import numpy as np
import pandas as pd

from gcp.research.magnitude_engine.mag_config import (
    DECISION_LIFT_MIN,
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

    # Raw gamma LEVEL columns are non-stationary dollar prices (IWM ~$130
    # in 2019 → ~$230 in 2026): a tree split learned on them is a time
    # proxy that cannot generalize out-of-fold. Verified 2026-08-26: after
    # the #771 gamma rebuild densified these columns (22-60% → ~100%
    # non-null), the phase0 15m/30m log-loss beat collapsed from ~+0.01
    # (6-8/8 folds) to ~-0.10 (0/8) on identical fold windows, while 5m
    # (where the columns carried no weight) was unchanged. Only NORMALIZED
    # distances transfer across years: derive dist_to_balance_pct here
    # (mirror of the persisted dist_to_gamma_flip_pct) and drop the raw
    # levels via the set below. NaN where balance is missing or close<=0
    # (§3.7); the matrix-level fillna(0) then treats it like every other
    # sparse feature.
    # MAG_ABLATE — experiment knob, MAG_FEATURES-style env plumbing.
    # "gamma_dist" additionally removes the normalized gamma distance
    # features (and skips the dist_to_balance derivation) so a phase0 run
    # can measure the no-gamma-distance baseline: the 2026-08-26 ablation
    # showed dropping only the raw levels left the 15m/30m collapse
    # intact, implicating the rebuilt dist_to_gamma_flip_pct values.
    # Unset (production) leaves standard behavior untouched.
    _ablate = set(filter(None, os.environ.get("MAG_ABLATE", "").split(",")))

    if ("gamma_dist" not in _ablate
            and "gamma_balance_price" in enc.columns and "close" in enc.columns):
        _close = pd.to_numeric(enc["close"], errors="coerce")
        _gbp = pd.to_numeric(enc["gamma_balance_price"], errors="coerce")
        enc["dist_to_balance_pct"] = pd.Series(
            np.where((_close > 0) & _gbp.notna(),
                     (_close - _gbp) / _close * 100.0, np.nan),
            index=enc.index, dtype=np.float64)

    drop = {
        # Raw gamma dollar levels — see the derivation comment above.
        "gamma_balance_price", "gamma_flip",
        *(("dist_to_gamma_flip_pct", "dist_to_balance_pct")
          if "gamma_dist" in _ablate else ()),
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


def decide_bucket(y_proba: np.ndarray, class_priors: np.ndarray,
                  lift_min: float = DECISION_LIFT_MIN) -> np.ndarray:
    """The served decision: the highest bucket whose probability is at least
    `lift_min` times its class prior, else TIGHT (index 0).

    This replaces argmax everywhere a bucket is NAMED (gate 4, the promotion
    verdict, the per-bar CSV, and mag_inference's pred_bucket) so that the
    gate measures the same decision the consumer sees. On a 64%-TIGHT label
    set the argmax of a calibrated model is TIGHT on ~97% of bars, which made
    gate 4 a test on a dozen bars per fold and the promotion gate a test the
    calibrated model failed by construction (2026-09-14; see mag_config's
    DECISION_LIFT_MIN for the measured operating curve).

    Buckets are walked from the top down and the first that clears wins, so
    a bar that clears both EXPANDED and EXPLOSIVE is EXPLOSIVE. The bar is
    inclusive: exactly lift_min * prior names the bucket. A prior of zero
    for a bucket (a training slice with no examples of it) makes that bucket
    un-nameable rather than always-named: 0 * lift is 0, and a `>=` against
    0 would fire on every bar, so that case is guarded explicitly.
    """
    proba = np.asarray(y_proba, dtype=float)
    priors = np.asarray(class_priors, dtype=float)
    if proba.ndim != 2 or proba.shape[1] != len(LABEL_CLASSES):
        raise ValueError(
            f"y_proba must be (n, {len(LABEL_CLASSES)}); got {proba.shape}")
    if priors.shape != (len(LABEL_CLASSES),):
        raise ValueError(
            f"class_priors must have one entry per class; got {priors.shape}")
    if not np.isfinite(lift_min) or lift_min <= 1.0:
        raise ValueError(f"lift_min must be a finite number above 1.0; got {lift_min!r}")
    decision = np.zeros(len(proba), dtype=np.int64)
    for b in range(len(LABEL_CLASSES) - 1, 0, -1):
        if priors[b] <= 0.0:
            continue
        clears = proba[:, b] >= lift_min * priors[b]
        # only rows not already claimed by a HIGHER bucket
        decision = np.where((decision == 0) & clears, b, decision)
    return decision


def explosive_lift(y_true_idx: np.ndarray, y_proba: np.ndarray,
                    explosive_idx: int,
                    class_priors: np.ndarray,
                    lift_min: float = DECISION_LIFT_MIN) -> dict:
    """Lift of the EXPLOSIVE bucket = P(true=EXPLOSIVE | named EXPLOSIVE)
    / P(true=EXPLOSIVE).  Spec gate 4 wants this >= 1.5.

    "Named" is decide_bucket(), not argmax (2026-09-14). `class_priors` are
    the TRAINING-fold class frequencies, because that is what the model was
    fitted against and what the served decision will scale; the base rate in
    the denominator is still the TEST fold's, because that is what the lift
    is realised against.
    """
    pred = decide_bucket(y_proba, class_priors, lift_min)
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
        "decision_lift_min": float(lift_min),
    }


def make_lgbm(class_weight: str | None = "balanced", n_jobs: int = -1,
               random_state: int | None = None):
    """Base LightGBM classifier — same hyperparameters as strat_engine so
    a phase-pass is attributable to feature signal, not hyperparameter
    differences.

    `class_weight` defaults to "balanced". The magnitude labels are imbalanced
    (~66/25/6/2 TIGHT/NORMAL/EXPANDED/EXPLOSIVE); with class_weight=None the
    learner minimised log-loss by predicting TIGHT ~99% of the time and
    abandoning the NORMAL/EXPANDED/EXPLOSIVE bars (the collapse of the
    magnitude-engine-rmcwj production model). "balanced" reweights the loss by
    inverse class frequency so the minority buckets are learned. Pass None only
    for a deliberate unweighted baseline.

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


MAG_CLASS_WEIGHT_POWER_DEFAULT = 0.75


def resolve_class_weight(y):
    """Class weight for training, tuned by the MAG_CLASS_WEIGHT_POWER env var
    (alpha, default 0.75). alpha>=1 → 'balanced'; alpha<=0 → None (unweighted);
    otherwise a tempered dict. Single seam so all four walk-forward training
    sites stay consistent and alpha is tunable without a code change.

    Default 0.75 was validated on IWM 5m: alpha=0.5 under-predicted tails
    (85/12/2/1), alpha=1.0 over-predicted them (47/27/19/7), alpha=0.75 tracked
    the true base rates (68/21/7/4 vs true 66/25/6/2)."""
    alpha = class_weight_power()
    if alpha >= 1.0:
        return "balanced"
    if alpha <= 0.0:
        return None
    return tempered_class_weight(y, alpha)


def class_weight_power() -> float:
    """The class-weight exponent in effect, as a number.

    Split out of resolve_class_weight so the walk-forward summary can record
    the value the training actually used. Until 2026-09-14 no run record
    carried it, and the exponent turned out to be the hyperparameter the
    whole promotion trade-off turns on: the same cell goes from beating the
    class-prior baseline in 8 of 8 folds at alpha=0 to losing in 8 of 8 at
    alpha=0.75. The run that was serving production at the time (c49qf) had
    no record of its own alpha and the code that produced it predates this
    repository, so its setting is unrecoverable. This makes the next one
    recoverable.

    A malformed MAG_CLASS_WEIGHT_POWER RAISES rather than falling back to the
    default: silently training under a different exponent than the one the
    operator named is the exact kind of unrecorded configuration this exists
    to end.
    """
    import os
    raw = os.environ.get("MAG_CLASS_WEIGHT_POWER", "").strip()
    if raw == "":
        return float(MAG_CLASS_WEIGHT_POWER_DEFAULT)
    try:
        alpha = float(raw)
    except ValueError as e:
        raise ValueError(
            f"MAG_CLASS_WEIGHT_POWER={raw!r} is not a number") from e
    if not np.isfinite(alpha):
        raise ValueError(f"MAG_CLASS_WEIGHT_POWER={raw!r} is not finite")
    return alpha


def tempered_class_weight(y, alpha: float = 0.5) -> dict:
    """LightGBM class_weight dict = (balanced_weight) ** alpha.

    balanced_weight[c] = n / (k * count_c)  — the sklearn 'balanced' formula.
    alpha=1.0 → full 'balanced'; alpha=0.0 → uniform (equivalent to None).

    Full 'balanced' de-collapsed the magnitude model but OVER-corrected —
    predicting the minority buckets too often (IWM 5m: 47/27/19/7 vs true
    66/25/6/2). Isotonic calibration over-corrected the other way (re-collapse
    to 100% TIGHT). Tempering with 0 < alpha < 1 is the tunable middle ground:
    minority buckets are still learned, but the correction is damped so the
    predicted distribution tracks the true base rates. walk_forward reads alpha
    from MAG_CLASS_WEIGHT_POWER so it can be tuned without a code change.
    """
    import numpy as np
    y = np.asarray(y)
    classes, counts = np.unique(y, return_counts=True)
    n = len(y)
    k = len(classes)
    return {int(c): float((n / (k * cnt)) ** alpha)
            for c, cnt in zip(classes, counts)}
