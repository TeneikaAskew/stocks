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


def test_aggregate_end_to_end_multiclass_shap_no_crash():
    """Regression for issue #704 / direction-importance-28djr.

    Production crash: the SIZE axis (4-class magnitude-bucket LightGBM model)
    hit 'ValueError: truth value of an array with more than one element is
    ambiguous' inside aggregate_importance. Root cause: the per-fold SHAP
    reducer only collapsed the samples axis, leaving a (features, classes)
    matrix instead of one scalar per feature; averaging that across folds and
    indexing by feature returned a length-n_classes array, and np.isnan(ms)
    raised on it. DIRECTION (binary) never hit this because SHAP's 2D binary
    output has no leftover class axis.

    This reproduces the real SHAP shape family (confirmed empirically against
    the pinned shap/lightgbm versions: multiclass shap_values() returns
    (n_samples, n_features, n_classes)) through the actual production
    reducer (_reduce_shap_to_features) into aggregate_importance, and asserts
    the result is sane scalars -- not just "didn't crash".
    """
    nfeat, n_classes, n_samples = 5, 4, 50
    cols = [f"f{i}" for i in range(nfeat)]
    rng = np.random.default_rng(1)

    per_fold_gain, per_fold_shap, raw_per_fold = [], [], []
    for _ in range(3):
        sv = rng.normal(size=(n_samples, nfeat, n_classes))  # multiclass SHAP shape
        reduced = _reduce_shap_to_features(sv, nfeat)
        assert reduced.shape == (nfeat,)
        per_fold_shap.append(reduced.tolist())
        raw_per_fold.append(reduced)
        per_fold_gain.append(rng.uniform(1, 100, size=nfeat).tolist())

    ranking = aggregate_importance(cols, per_fold_gain, per_fold_shap)

    manual_mean = np.mean(raw_per_fold, axis=0)
    got = {r["feature"]: r["mean_abs_shap"] for r in ranking}
    for i, c in enumerate(cols):
        assert isinstance(got[c], float)          # scalar, never an array
        assert not np.isnan(got[c])
        assert abs(got[c] - manual_mean[i]) < 1e-9


def test_aggregate_rejects_unreduced_per_class_shap_rows():
    """If a producer regresses to the pre-fix shape (per-fold row is a
    (features, classes) matrix instead of a scalar-per-feature vector),
    aggregate_importance must fail loud with a clear diagnostic -- not the
    cryptic 'ambiguous truth value' from np.isnan on an array."""
    cols = ["a", "b", "c"]
    per_fold_gain = [[3.0, 2.0, 1.0]]
    # pre-fix shape: each row is (n_features, n_classes), never collapsed
    per_fold_shap = [[[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]]
    with pytest.raises(AssertionError, match="scalar-per-feature"):
        aggregate_importance(cols, per_fold_gain, per_fold_shap)
