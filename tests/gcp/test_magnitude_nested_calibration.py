import numpy as np
import pytest

from gcp.research.magnitude_engine.mag_pred_train import (
    CALIBRATION_METHODS,
    MIN_ISOTONIC_SAMPLES_PER_CLASS,
    ProbabilityCalibrator,
    calibration_metrics,
)


def _probabilities(n=160):
    rng = np.random.default_rng(7)
    logits = rng.normal(size=(n, 4))
    probabilities = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    y = np.tile(np.arange(4), n // 4)
    return probabilities, y


@pytest.mark.parametrize("method", CALIBRATION_METHODS)
def test_all_calibration_methods_produce_multiclass_probabilities(method):
    probabilities, y = _probabilities()
    calibrated = ProbabilityCalibrator(method, 4).fit(probabilities, y).transform(probabilities)
    assert calibrated.shape == probabilities.shape
    assert np.all(calibrated >= 0)
    assert calibrated.sum(axis=1) == pytest.approx(np.ones(len(y)))


def test_isotonic_refuses_thin_classes_instead_of_falling_back():
    probabilities, _ = _probabilities(40)
    y = np.array([0] * 37 + [1, 2, 3])
    with pytest.raises(ValueError, match=f"{MIN_ISOTONIC_SAMPLES_PER_CLASS} samples per class"):
        ProbabilityCalibrator("isotonic", 4).fit(probabilities, y)


def test_calibration_metrics_report_complete_diagnostics_and_bin_counts():
    probabilities, y = _probabilities()
    metrics = calibration_metrics(y, probabilities)
    assert {"ece", "adaptive_ece", "classwise_ece", "brier_score", "log_loss",
            "reliability_bins", "calibration_slope", "calibration_intercept"} <= metrics.keys()
    assert len(metrics["classwise_ece"]) == 4
    assert sum(item["n"] for item in metrics["reliability_bins"]) == len(y)
    assert sum(item["n"] for item in metrics["adaptive_reliability_bins"]) == len(y)
