import numpy as np
import pandas as pd

from gcp.research.magnitude_engine.binary_research import (
    BaseRateModel, choose_threshold, chronological_partitions, metrics,
)


def test_partitions_are_chronological_and_disjoint():
    ts = pd.date_range("2024-01-01", periods=100, freq="h")
    parts = chronological_partitions(ts[::-1])
    assert tuple(map(len, (parts.train, parts.validation, parts.test))) == (60, 20, 20)
    series = pd.Series(ts[::-1])
    assert series.iloc[parts.train].max() < series.iloc[parts.validation].min()
    assert series.iloc[parts.validation].max() < series.iloc[parts.test].min()


def test_threshold_maximizes_declared_validation_utility():
    chosen = choose_threshold([1, 0, 0], [.8, .7, .1])
    assert chosen["threshold"] == .8
    assert chosen["validation_expected_net_utility"] == 5 / 3


def test_metrics_include_rare_event_and_operating_measures():
    result = metrics([1, 0, 1, 0], [.9, .8, .7, .1], .75, ["a", "a", "b", "b"])
    assert result["confusion"] == {"tp": 1, "fp": 1, "fn": 1, "tn": 1}
    assert result["false_alerts_per_session"] == .5
    assert result["expected_net_utility"] == 1.0
    assert 0 <= result["pr_auc"] <= 1
    assert len(result["calibration_curve"]) == 10


def test_base_rate_learns_training_partition_only():
    model = BaseRateModel().fit(np.zeros((4, 1)), [0, 0, 0, 1])
    assert np.all(model.predict_proba(np.zeros((2, 1)))[:, 1] == .25)
