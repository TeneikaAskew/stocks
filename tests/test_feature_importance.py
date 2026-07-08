import numpy as np

from gcp.research.direction_program.feature_importance import aggregate_importance


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
