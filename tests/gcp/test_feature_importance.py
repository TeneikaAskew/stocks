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


def test_reduce_shap_raises_on_axis_size_mismatch():
    # Regression test for issue #704 (direction-importance-28djr): if the
    # feature axis genuinely doesn't have size nfeat, _reduce_shap_to_features
    # must raise loudly (caught by _mean_abs_shap -> None + warning, never a
    # fabricated/garbled value) instead of silently reducing over the wrong
    # axis. Shape (n_samples=5, 4, n_classes=4) with nfeat=3: no axis actually
    # has size 3.
    sv = np.random.default_rng(0).normal(size=(5, 4, 4))
    with pytest.raises(ValueError, match="SHAP feature axis"):
        _reduce_shap_to_features(sv, nfeat=3)


def test_reduce_shap_multiclass_3d_matches_real_shap_lightgbm_shape():
    # Empirically confirmed (see PR for direction-importance-28djr): a real
    # shap.TreeExplainer(lgb_booster).shap_values(X) call for a genuine
    # multiclass LightGBM model (objective="multiclass", num_class=4),
    # tested against shap 0.45.0/0.51.0 x lightgbm 4.1.0/4.6.0, returns an
    # ndarray of exactly this shape: (n_samples, n_features, n_classes).
    n_samples, n_features, n_classes = 400, 254, 4
    sv = np.random.default_rng(1).normal(size=(n_samples, n_features, n_classes))
    out = _reduce_shap_to_features(sv, nfeat=n_features)
    assert out.shape == (n_features,)


def test_reduce_shap_multiclass_list_matches_real_older_shap_shape():
    # Empirically confirmed: shap<0.45 (still within this repo's pinned
    # shap>=0.43.0) paired with lightgbm 4.1.0 returns a list of n_classes
    # arrays, each (n_samples, n_features), for the same multiclass model.
    n_samples, n_features, n_classes = 400, 254, 4
    sv = [np.random.default_rng(i).normal(size=(n_samples, n_features))
          for i in range(n_classes)]
    out = _reduce_shap_to_features(sv, nfeat=n_features)
    assert out.shape == (n_features,)


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


def test_aggregate_drops_fold_with_mismatched_shap_length():
    # Regression test for issue #704 (direction-importance-28djr): a
    # SHAP/LightGBM version drift that makes one fold's reduced SHAP vector
    # the wrong length (e.g. a stale/corrupted per-fold result, or a future
    # regression in _reduce_shap_to_features's axis detection) must not
    # crash aggregate_importance — it must drop the offending fold (logged)
    # and average over the remaining valid folds, same contract as a None
    # (failed) fold.
    cols = ["a", "b", "c"]
    per_fold_gain = [[3.0, 1.0, 0.5], [5.0, 1.0, 0.5], [4.0, 1.0, 0.5]]
    per_fold_shap = [
        [0.4, 0.2, 0.05],       # fold 1: valid, length 3
        [0.1, 0.1, 0.1, 0.1],   # fold 2: corrupted, length 4 (!= nfeat=3)
        [0.6, 0.1, 0.05],       # fold 3: valid, length 3
    ]
    ranked = aggregate_importance(cols, per_fold_gain, per_fold_shap)
    assert [r["feature"] for r in ranked] == ["a", "b", "c"]
    top = next(r for r in ranked if r["feature"] == "a")
    # averaged over folds 1 and 3 only (fold 2 dropped): (0.4 + 0.6) / 2 = 0.5
    assert abs(top["mean_abs_shap"] - 0.5) < 1e-9


def test_aggregate_drops_fold_whose_shap_rows_are_not_flat():
    # This is the EXACT malformed shape that reproduces issue #704's
    # "ValueError: The truth value of an array with more than one element is
    # ambiguous" crash verbatim (verified against the pre-fix code): each
    # fold's SHAP entry has len(s) == nfeat (so a naive length-only check
    # would accept it) but each element is itself a length-k list rather
    # than a scalar — i.e. a (nfeat, k) shaped row, not a flat length-nfeat
    # vector. np.asarray(shap_rows, dtype=float).mean(axis=0) then produces
    # a >1-D mean_shap, and mean_shap[i] is a multi-element array — the
    # ambiguous-truth-value crash. The fix must drop such folds instead.
    cols = ["a", "b", "c"]
    per_fold_gain = [[3.0, 1.0, 0.5], [5.0, 1.0, 0.5]]
    per_fold_shap = [
        [[0.4, 0.5], [0.2, 0.1], [0.05, 0.02]],   # fold 1: not flat, shape (3, 2)
        [[0.3, 0.2], [0.15, 0.1], [0.04, 0.03]],  # fold 2: not flat, shape (3, 2)
    ]
    ranked = aggregate_importance(cols, per_fold_gain, per_fold_shap)
    assert [r["feature"] for r in ranked] == ["a", "b", "c"]
    # both folds dropped (neither is flat) -> no fabricated SHAP value, gain still ranks
    assert all(r["mean_abs_shap"] is None for r in ranked)


def test_aggregate_end_to_end_binary_and_multiclass_shap_shapes():
    # End-to-end sanity check that both the DIRECTION axis (binary SHAP,
    # ndarray (n_samples, n_features)) and the SIZE axis (multiclass SHAP,
    # ndarray (n_samples, n_features, n_classes)) reduce and aggregate
    # correctly through the full _reduce_shap_to_features -> aggregate_importance
    # path — the two axes whose divergent behavior (direction succeeds,
    # size crashes) was the original issue #704 symptom.
    nfeat = 5
    cols = [f"f{i}" for i in range(nfeat)]
    rng = np.random.default_rng(2)

    # DIRECTION: binary shap shape (n_samples, n_features)
    binary_sv = rng.normal(size=(50, nfeat))
    binary_reduced = _reduce_shap_to_features(binary_sv, nfeat=nfeat).tolist()

    # SIZE: multiclass shap shape (n_samples, n_features, n_classes)
    multiclass_sv = rng.normal(size=(50, nfeat, 4))
    multiclass_reduced = _reduce_shap_to_features(multiclass_sv, nfeat=nfeat).tolist()

    per_fold_gain = [[10.0, 8.0, 6.0, 4.0, 2.0]]
    for reduced in (binary_reduced, multiclass_reduced):
        ranked = aggregate_importance(cols, per_fold_gain, [reduced])
        assert len(ranked) == nfeat
        assert all(r["mean_abs_shap"] is not None for r in ranked)
