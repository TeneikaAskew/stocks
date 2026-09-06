"""Hermetic tests for the magnitude_engine gate logic.

The validation chain is now load-bearing for any future signal-research
project (it produced the magnitude FAIL verdict and the four harness
lessons in mag_config.py). Tests below pin the gate implementations
against synthetic ground-truth so a regression flips a test, not a
production-cell verdict.

NO Cloud SQL, NO GCS, NO LightGBM training — pure-numpy/pandas
inputs, pure-python outputs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gcp.research.magnitude_engine.mag_config import (
    LABEL_CLASSES, LABEL_TO_IDX, MAGNITUDE_THRESHOLDS,
    SUCCESS_BAR_GATE7_RATIO_MIN,
    SUCCESS_BAR_BOOTSTRAP_PASS_MIN,
    SUCCESS_BAR_MECHANISM_RATIO_MIN,
)
from gcp.research.magnitude_engine.mag_dataset import _bucket_magnitude
from gcp.research.magnitude_engine.mag_pred_train import (
    expected_calibration_error, decisive_call_hit_rate, explosive_lift,
)


# ─────────────────────── Target bucketing ───────────────────────

class TestBucketMagnitude:
    """The 4-class bucketing of |next_close - next_open| / atr_20."""

    def test_thresholds_are_unchanged(self):
        # If this test fires, someone moved the bucket boundaries and the
        # entire walk-forward needs re-running. Locked at (0.5, 1.0, 1.5).
        assert MAGNITUDE_THRESHOLDS == (0.5, 1.0, 1.5)

    def test_tight_bucket(self):
        move = pd.Series([0.1, 0.3, 0.49])
        atr = pd.Series([1.0, 1.0, 1.0])
        result = _bucket_magnitude(move, atr)
        assert list(result.dropna()) == ["TIGHT"] * 3

    def test_normal_bucket(self):
        move = pd.Series([0.5, 0.75, 0.99])
        atr = pd.Series([1.0, 1.0, 1.0])
        result = _bucket_magnitude(move, atr)
        assert list(result.dropna()) == ["NORMAL"] * 3

    def test_expanded_bucket(self):
        move = pd.Series([1.0, 1.25, 1.49])
        atr = pd.Series([1.0, 1.0, 1.0])
        result = _bucket_magnitude(move, atr)
        assert list(result.dropna()) == ["EXPANDED"] * 3

    def test_explosive_bucket(self):
        move = pd.Series([1.5, 2.0, 10.0])
        atr = pd.Series([1.0, 1.0, 1.0])
        result = _bucket_magnitude(move, atr)
        assert list(result.dropna()) == ["EXPLOSIVE"] * 3

    def test_nan_atr_yields_nan_bucket(self):
        # Critical: rows with NaN atr_20 (warmup, gaps) must NOT default
        # to any bucket. Caller drops them. Silent-fallback would
        # contaminate training labels.
        move = pd.Series([0.5, 1.0])
        atr = pd.Series([np.nan, np.nan])
        result = _bucket_magnitude(move, atr)
        assert result.isna().all()

    def test_zero_atr_yields_nan_bucket(self):
        # atr=0 would mean infinite ratio; must not assign a bucket.
        move = pd.Series([0.5, 1.0])
        atr = pd.Series([0.0, 0.0])
        result = _bucket_magnitude(move, atr)
        assert result.isna().all()

    def test_nan_move_yields_nan_bucket(self):
        move = pd.Series([np.nan, np.nan])
        atr = pd.Series([1.0, 1.0])
        result = _bucket_magnitude(move, atr)
        assert result.isna().all()


# ─────────────────────── ECE ───────────────────────

class TestExpectedCalibrationError:
    """Multiclass ECE — binned by max-proba confidence."""

    def test_perfectly_calibrated_gives_zero_ece(self):
        # Every prediction at 100% confidence + correct → ECE = 0
        y_true = np.array([0, 1, 2, 3, 0, 1, 2, 3])
        # One-hot probabilities matching y_true
        proba = np.eye(4)[y_true]
        ece, bins = expected_calibration_error(y_true, proba, n_bins=10)
        assert ece == pytest.approx(0.0, abs=1e-9)

    def test_completely_miscalibrated_gives_high_ece(self):
        # 100% confidence in always-wrong predictions → ECE = 1.0
        y_true = np.array([0, 0, 0, 0])
        proba = np.array([
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ])
        ece, bins = expected_calibration_error(y_true, proba, n_bins=10)
        assert ece == pytest.approx(1.0, abs=1e-9)

    def test_uniform_probabilities(self):
        # Uniform 0.25 across 4 classes; confidence = 0.25; accuracy by
        # luck is ~0.25 if y_true is random → ECE close to 0.
        rng = np.random.default_rng(42)
        n = 1000
        y_true = rng.integers(0, 4, size=n)
        proba = np.full((n, 4), 0.25)
        ece, _ = expected_calibration_error(y_true, proba, n_bins=10)
        # All confidences = 0.25 land in bin 2 (0.2-0.3); accuracy is
        # ~0.25 by random sampling. ECE = |0.25 - acc|.
        assert ece < 0.05

    def test_empty_bins_handled(self):
        # n_bins = 100; only a few predictions → most bins empty.
        # Should not raise; should return finite number.
        y_true = np.array([0, 1])
        proba = np.array([[0.6, 0.2, 0.1, 0.1], [0.1, 0.7, 0.1, 0.1]])
        ece, _ = expected_calibration_error(y_true, proba, n_bins=100)
        assert np.isfinite(ece)
        assert 0.0 <= ece <= 1.0


# ─────────────────────── Decisive-call hit rate ───────────────────────

class TestDecisiveCallHitRate:
    """gate 3 input — accuracy conditional on max-proba ≥ threshold."""

    def test_all_correct_at_high_threshold(self):
        y_true = np.array([0, 1, 2, 3])
        # All predictions correct at 100% confidence
        proba = np.eye(4)[y_true]
        result = decisive_call_hit_rate(y_true, proba, (0.50, 0.90, 0.99))
        for t in ("0.50", "0.90", "0.99"):
            assert result[t]["accuracy"] == 1.0
            assert result[t]["n"] == 4

    def test_no_bars_above_threshold(self):
        y_true = np.array([0, 1])
        # Both predictions at 0.3 max-proba — below 0.5 threshold
        proba = np.array([[0.3, 0.3, 0.2, 0.2], [0.2, 0.3, 0.3, 0.2]])
        result = decisive_call_hit_rate(y_true, proba, (0.50,))
        assert result["0.50"]["n"] == 0
        assert result["0.50"]["accuracy"] is None

    def test_monotone_accuracy_with_threshold(self):
        # As threshold rises, more confident predictions remain. Monotone
        # check: accuracy should not decrease as threshold rises if the
        # model is well-calibrated.
        rng = np.random.default_rng(0)
        n = 500
        y_true = rng.integers(0, 4, size=n)
        # Construct probabilities such that high-confidence picks are
        # systematically MORE correct than low-confidence picks.
        proba = np.zeros((n, 4))
        for i in range(n):
            if i % 3 == 0:
                # high-confidence + correct
                proba[i, y_true[i]] = 0.9
                others = [c for c in range(4) if c != y_true[i]]
                for c in others:
                    proba[i, c] = 0.1 / 3
            else:
                # low-confidence; random
                proba[i] = rng.dirichlet([1, 1, 1, 1])
        accs = []
        for t in (0.40, 0.50, 0.60, 0.70):
            r = decisive_call_hit_rate(y_true, proba, (t,))
            a = r[f"{t:.2f}"]["accuracy"]
            if a is not None:
                accs.append(a)
        # The constructed dataset is biased toward high-confidence correctness,
        # so accuracy should be monotone non-decreasing.
        assert accs == sorted(accs), f"accuracy not monotone: {accs}"


# ─────────────────────── EXPLOSIVE lift ───────────────────────

class TestExplosiveLift:
    """gate 4 input — precision of EXPLOSIVE-prediction / base-rate."""

    def test_perfect_explosive_calls_give_high_lift(self):
        # 4 bars total, 1 truly EXPLOSIVE, 1 predicted EXPLOSIVE, and it's
        # the same bar → precision = 1.0, base rate = 0.25, lift = 4.0
        y_true = np.array([0, 1, 2, 3])
        proba = np.array([
            [0.7, 0.1, 0.1, 0.1],
            [0.1, 0.7, 0.1, 0.1],
            [0.1, 0.1, 0.7, 0.1],
            [0.1, 0.1, 0.1, 0.7],
        ])
        result = explosive_lift(y_true, proba,
                                 explosive_idx=LABEL_TO_IDX["EXPLOSIVE"])
        assert result["n_predicted"] == 1
        assert result["precision"] == 1.0
        assert result["base_rate"] == 0.25
        assert result["lift"] == 4.0

    def test_no_explosive_predictions_returns_none_lift(self):
        # Architectural test — naive lookup would hit this every time
        # because it can't argmax a 3% class. Lift is None, gate fails.
        y_true = np.array([3, 3, 3, 0])  # 75% explosive
        # No prediction argmaxes EXPLOSIVE (always class 0 or 1)
        proba = np.array([
            [0.5, 0.2, 0.2, 0.1],
            [0.5, 0.2, 0.2, 0.1],
            [0.5, 0.2, 0.2, 0.1],
            [0.5, 0.2, 0.2, 0.1],
        ])
        result = explosive_lift(y_true, proba,
                                 explosive_idx=LABEL_TO_IDX["EXPLOSIVE"])
        assert result["n_predicted"] == 0
        assert result["lift"] is None

    def test_all_explosive_predictions_wrong_gives_zero_lift(self):
        # Predict EXPLOSIVE for every bar; none are actually EXPLOSIVE
        y_true = np.array([0, 1, 2, 0])
        proba = np.array([
            [0.1, 0.1, 0.1, 0.7],
            [0.1, 0.1, 0.1, 0.7],
            [0.1, 0.1, 0.1, 0.7],
            [0.1, 0.1, 0.1, 0.7],
        ])
        result = explosive_lift(y_true, proba,
                                 explosive_idx=LABEL_TO_IDX["EXPLOSIVE"])
        assert result["n_predicted"] == 4
        assert result["precision"] == 0.0
        # Base rate = 0 (no EXPLOSIVE bars in y_true) — lift undefined; impl returns None
        assert result["lift"] is None


# ─────────────────────── Gate constants live in mag_config ───────────────

class TestGateConstants:
    """Ensures all seven gates have constants in mag_config — the doc
    references them by name."""

    def test_gate_7_threshold_locked(self):
        # If this changes someone moved the gate-7 ratio after seeing
        # the actual ratios (0.83-0.92). The whole project's anti-fitting
        # rule says NO. Locked at 1.25.
        assert SUCCESS_BAR_GATE7_RATIO_MIN == 1.25

    def test_gate_5_threshold_locked(self):
        assert SUCCESS_BAR_BOOTSTRAP_PASS_MIN == 0.80

    def test_gate_6_threshold_locked(self):
        assert SUCCESS_BAR_MECHANISM_RATIO_MIN == 2.0

    def test_label_classes_unchanged(self):
        # The 4 buckets are the project's locked target. If they change,
        # walk-forward and all gate analyses need re-running.
        assert LABEL_CLASSES == ("TIGHT", "NORMAL", "EXPANDED", "EXPLOSIVE")
        assert LABEL_TO_IDX["EXPLOSIVE"] == 3
