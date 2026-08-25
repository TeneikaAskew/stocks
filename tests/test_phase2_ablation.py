from gcp.research.direction_program.phase2_ablation import ABLATION_CONFIGS


def test_ladder_has_baseline_and_isolation_and_stack_per_axis():
    for axis in ("direction", "size"):
        cfgs = [c for c in ABLATION_CONFIGS if c["axis"] == axis]
        feats = [c["features"] for c in cfgs]
        assert "" in feats                       # baseline
        assert "prune" in feats                  # a family in isolation
        # cumulative stack contains multiple families
        assert any("," in f for f in feats)
