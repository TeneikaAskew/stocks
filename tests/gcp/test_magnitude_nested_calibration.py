import numpy as np
import pytest

from gcp.research.magnitude_engine.mag_pred_train import (
    CALIBRATION_METHODS,
    MIN_ISOTONIC_SAMPLES_PER_CLASS,
    ProbabilityCalibrator,
    calibration_metrics,
)
from gcp.research.magnitude_engine.mag_walk_forward import (
    AUTO_CALIBRATION,
    _fit_and_select_calibrators,
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


def test_method_selection_uses_disjoint_chronological_subwindow():
    probabilities, y = _probabilities()
    chosen, fitted, selection, omitted, window = _fit_and_select_calibrators(
        probabilities, y, AUTO_CALIBRATION)
    assert chosen in fitted
    assert set(selection) == set(fitted)
    assert window == {"n_fit": 79, "n_selection": 80, "embargoed_rows": 1}
    assert omitted == {
        "isotonic": "requires 25 samples per class in calibrator-fit and full "
                    "calibration windows; got fit=[20, 20, 20, 19], "
                    "full=[40, 40, 40, 40]"
    }


def test_forced_method_is_honored_and_absent_class_sigmoid_is_ineligible():
    probabilities, y = _probabilities()
    chosen, *_ = _fit_and_select_calibrators(probabilities, y, "temperature")
    assert chosen == "temperature"

    thin_y = np.zeros(len(y), dtype=int)
    with pytest.raises(ValueError, match="requested calibration 'sigmoid' is ineligible"):
        _fit_and_select_calibrators(probabilities, thin_y, "sigmoid")
