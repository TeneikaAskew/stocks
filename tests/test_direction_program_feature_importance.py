"""Hermetic tests for gcp.research.direction_program.feature_importance's pure
aggregation function.

Regression coverage for issue #704 (direction-importance Cloud Run Job,
2026-07-08): a length-mismatched per-fold row made `aggregate_importance`
crash inside `np.isnan(ms)` with "the truth value of an array with more
than one element is ambiguous" instead of naming the bad shape. These tests
pin the well-formed behavior and assert the malformed-shape path now raises
a diagnosable RuntimeError instead of that bare numpy crash.

NO Cloud SQL, NO LightGBM training — pure-numpy inputs, pure-python outputs.
"""
from __future__ import annotations

import math

import pytest

from gcp.research.direction_program.feature_importance import (
    aggregate_importance,
)

FEATURE_COLS = ["f0", "f1", "f2"]


def test_ranks_by_mean_gain_desc_and_averages_shap():
    per_fold_gain = [[1.0, 5.0, 3.0], [3.0, 3.0, 5.0]]   # mean: f0=2, f1=4, f2=4
    per_fold_shap = [[0.1, 0.2, 0.3], [0.3, 0.4, 0.5]]   # mean: f0=.2, f1=.3, f2=.4

    out = aggregate_importance(FEATURE_COLS, per_fold_gain, per_fold_shap)

    assert [r["feature"] for r in out] == ["f2", "f1", "f0"]
    assert [r["rank"] for r in out] == [1, 2, 3]
    f2 = next(r for r in out if r["feature"] == "f2")
    assert f2["mean_gain"] == pytest.approx(4.0)
    assert f2["mean_abs_shap"] == pytest.approx(0.4)


def test_missing_shap_reported_as_none_not_zero():
    per_fold_gain = [[1.0, 2.0, 3.0]]
    out = aggregate_importance(FEATURE_COLS, per_fold_gain, per_fold_shap=[])

    assert all(r["mean_abs_shap"] is None for r in out)


def test_partial_shap_folds_average_only_the_present_ones():
    per_fold_gain = [[1.0, 1.0, 1.0], [1.0, 1.0, 1.0]]
    per_fold_shap = [[0.2, 0.2, 0.2], None]   # one fold's SHAP failed

    out = aggregate_importance(FEATURE_COLS, per_fold_gain, per_fold_shap)

    for r in out:
        assert r["mean_abs_shap"] == pytest.approx(0.2)


def test_ragged_gain_rows_raise_diagnosable_error_not_bare_numpy_crash():
    # One fold reports 3 features, the other reports 2 — a caller bug, not
    # a legitimate empty-SHAP case.
    per_fold_gain = [[1.0, 2.0, 3.0], [1.0, 2.0]]

    with pytest.raises(RuntimeError, match="inconsistent lengths"):
        aggregate_importance(FEATURE_COLS, per_fold_gain, per_fold_shap=[])


def test_wrong_length_gain_rows_raise_diagnosable_error_not_bare_numpy_crash():
    # Every fold consistently reports 2 values, not 3 — e.g. the caller's
    # feature_cols drifted from what actually got scored. Uniform-but-wrong
    # shape doesn't trip numpy's own ragged-array check, so this exercises
    # our explicit shape assertion.
    per_fold_gain = [[1.0, 2.0], [3.0, 4.0]]

    with pytest.raises(RuntimeError, match="per_fold_gain has shape"):
        aggregate_importance(FEATURE_COLS, per_fold_gain, per_fold_shap=[])


def test_ragged_shap_rows_raise_diagnosable_error_not_bare_numpy_crash():
    per_fold_gain = [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]]
    per_fold_shap = [[0.1, 0.2, 0.3], [0.1, 0.2]]

    with pytest.raises(RuntimeError, match="inconsistent lengths"):
        aggregate_importance(FEATURE_COLS, per_fold_gain, per_fold_shap)


def test_wrong_length_shap_rows_raise_diagnosable_error_not_bare_numpy_crash():
    per_fold_gain = [[1.0, 2.0, 3.0]]
    # Reproduces issue #704: every fold's shap row is consistently shorter
    # than len(feature_cols) (e.g. an axis-collapse bug upstream in
    # _reduce_shap_to_features), which used to make `mean_shap` end up
    # multi-dimensional and crash inside `np.isnan(ms)` with an opaque
    # "ambiguous truth value" error instead of naming the bad shape.
    per_fold_shap = [[0.1, 0.2]]

    with pytest.raises(RuntimeError, match="per_fold_shap has shape"):
        aggregate_importance(FEATURE_COLS, per_fold_gain, per_fold_shap)


def test_all_nan_shap_column_reported_as_none():
    per_fold_gain = [[1.0, 2.0, 3.0]]
    out = aggregate_importance(FEATURE_COLS, per_fold_gain, per_fold_shap=[])
    for r in out:
        assert r["mean_abs_shap"] is None
        assert not (isinstance(r["mean_abs_shap"], float) and math.isnan(r["mean_abs_shap"]))
