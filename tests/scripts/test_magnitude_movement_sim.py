"""Tests for the magnitude movement-simulation summary."""
from types import SimpleNamespace

from gcp.research.magnitude_engine.mag_config import PRODUCTION_READINESS_VERSION
from scripts.magnitude_movement_sim import _build_summary


def test_the_uploaded_summary_records_the_readiness_version():
    """The movement sim is economic evidence for a walk-forward run; without
    the version a later reader cannot tell which readiness policy governs
    it (Codex P2 on #1187)."""
    args = SimpleNamespace(ticker="IWM", tf="5m", phase="phase1", run_id="r1",
                           position="straddle", direction="both",
                           label_mode="body")
    summary = _build_summary(args, 3, 0.12345, 0.1, [])
    assert summary["production_readiness_version"] == PRODUCTION_READINESS_VERSION
    assert summary["n_bars"] == 3
    assert summary["overall_mean_payoff_atr"] == 0.1235
