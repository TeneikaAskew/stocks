import numpy as np
import pytest

# feature_importance imports strat_walk_forward -> lightgbm at module load, so
# skip cleanly on the lightweight test runner (lightgbm is only in the research
# image / "Research Tests" CI job).
pytest.importorskip("lightgbm")

from gcp.research.direction_program.feature_importance import (
    aggregate_importance, _reduce_shap_to_features,
)


def test_reduce_shap_binary_2d():
    # binary: (n_samples=5, n_features=3)
    sv = np.arange(15, dtype=float).reshape(5, 3)
    out = _reduce_shap_to_features(sv, nfeat=3)
    assert out.shape == (3,)
    assert np.allclose(out, np.abs(sv).mean(axis=0))


def test_reduce_shap_multiclass_3d():
    # newer SHAP multiclass: (n_samples=5, n_features=3, n_classes=4)
    sv = np.random.default_rng(0).normal(size=(5, 3, 4))
    out = _reduce_shap_to_features(sv, nfeat=3)
    assert out.shape == (3,)                      # collapsed to per-feature, no crash


def test_reduce_shap_multiclass_list():
    # older SHAP multiclass: list of 4 arrays, each (n_samples=5, n_features=3)
    sv = [np.random.default_rng(i).normal(size=(5, 3)) for i in range(4)]
    out = _reduce_shap_to_features(sv, nfeat=3)
    assert out.shape == (3,)


def test_aggregate_ranks_by_mean_gain_and_averages_shap():
    cols = ["a", "b", "c"]
    # two folds of gain: a strongest, c weakest
    per_fold_gain = [[10.0, 5.0, 1.0], [20.0, 3.0, 1.0]]
    per_fold_shap = [[0.4, 0.2, 0.05], [0.6, 0.1, 0.05]]
    ranked = aggregate_importance(cols, per_fold_gain, per_fold_shap)

    # ranked by mean gain, descending: a (15) > b (4) > c (1)
    assert [r["feature"] for r in ranked] == ["a", "b", "c"]
    assert [r["rank"] for r in ranked] == [1, 2, 3]
    assert ranked[0]["mean_gain"] == 15.0
    assert abs(ranked[0]["mean_abs_shap"] - 0.5) < 1e-9


def test_aggregate_handles_missing_shap_as_none():
    cols = ["a", "b"]
    per_fold_gain = [[3.0, 1.0], [5.0, 1.0]]
    # no SHAP available (e.g. all folds failed shap) -> mean_abs_shap None, gain still ranks
    ranked = aggregate_importance(cols, per_fold_gain, [])
    assert [r["feature"] for r in ranked] == ["a", "b"]
    assert ranked[0]["mean_abs_shap"] is None


def test_aggregate_skips_none_shap_folds():
    cols = ["a", "b"]
    per_fold_gain = [[3.0, 1.0], [5.0, 1.0]]
    # one fold's shap failed (None) -> average over the surviving fold only
    per_fold_shap = [None, [0.8, 0.2]]
    ranked = aggregate_importance(cols, per_fold_gain, per_fold_shap)
    top = next(r for r in ranked if r["feature"] == "a")
    assert abs(top["mean_abs_shap"] - 0.8) < 1e-9


def test_aggregate_drops_malformed_shap_row_instead_of_crashing():
    """GCP job failure (issue #704): a fold whose SHAP vector didn't
    reduce to a flat length-nfeat row (e.g. a shape bug in the SHAP
    reduction upstream) made `np.asarray(shap_rows).mean(axis=0)`
    produce a >1D `mean_shap`, so `mean_shap[i]` was itself an array
    and `np.isnan(ms)` raised "The truth value of an array with more
    than one element is ambiguous." aggregate_importance must drop the
    malformed row (same contract as a None/failed-SHAP fold) rather
    than let it corrupt the aggregate or crash."""
    cols = ["a", "b", "c"]
    per_fold_gain = [[3.0, 2.0, 1.0], [4.0, 2.0, 1.0]]
    per_fold_shap = [
        [0.9, 0.5, 0.1],          # well-formed fold
        [[0.9, 0.5, 0.1], [0.9, 0.5, 0.1]],  # malformed: (2, 3) not (3,)
    ]
    ranked = aggregate_importance(cols, per_fold_gain, per_fold_shap)
    top = next(r for r in ranked if r["feature"] == "a")
    # Only the well-formed fold contributes -> mean_abs_shap == that fold's value
    assert abs(top["mean_abs_shap"] - 0.9) < 1e-9


def test_aggregate_all_shap_rows_malformed_falls_back_to_none():
    """If every fold's SHAP row is malformed, mean_abs_shap must be
    None (Rule 3.7 — never a fabricated value), not a crash."""
    cols = ["a", "b"]
    per_fold_gain = [[3.0, 1.0]]
    per_fold_shap = [[[0.9, 0.5], [0.9, 0.5]]]  # malformed: (2, 2) not (2,)
    ranked = aggregate_importance(cols, per_fold_gain, per_fold_shap)
    assert all(r["mean_abs_shap"] is None for r in ranked)
