from gcp.research.direction_program.phase2_features import prune_feature_cols
from gcp.research.direction_program.phase2_prune_sets import NEAR_DEAD


def test_prune_removes_drop_set_preserves_order():
    cols = ["a", "b", "c", "d"]
    assert prune_feature_cols(cols, {"b", "d"}) == ["a", "c"]


def test_prune_noop_when_empty_drop_set():
    cols = ["a", "b"]
    assert prune_feature_cols(cols, set()) == ["a", "b"]


def test_near_dead_has_both_axes_and_is_nonempty():
    assert set(NEAR_DEAD) == {"direction", "size"}
    assert len(NEAR_DEAD["direction"]) > 50
    assert len(NEAR_DEAD["size"]) > 50
    # spot-check known dead columns from the 2026-07-08 audit
    assert "gamma_regime_unknown" in NEAR_DEAD["direction"]
