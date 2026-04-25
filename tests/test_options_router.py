"""Unit tests for platform.api.routers.options — the /api/options/greeks
endpoint after refactoring to import lib/gamma.

These tests exercise the endpoint function directly with synthetic chains
so they don't require Cloud SQL or googleapis dependencies. They lock in
the API response contract so future tweaks to lib/gamma.py don't silently
change the JSON shape the React app consumes.
"""
import pytest

# Skip the whole module if the FastAPI deps aren't available.
pytest.importorskip("fastapi")
pytest.importorskip("pydantic")

# Import lazily after the importorskip so collection errors are clean
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "platform" / "api"))

# The router module pulls in cachetools / google packages at import time.
# Skip if they're missing instead of erroring across the whole suite.
try:
    from routers.options import (
        compute_options_greeks,
        _OptionRecord,
        _GreeksRequest,
    )
except ModuleNotFoundError as exc:
    pytest.skip(f"options router unavailable: {exc}", allow_module_level=True)


# ── helpers ─────────────────────────────────────────────────────────────


def _opt(type_, strike, oi=100, gamma=0.05, vega=0.10, delta=0.5, volume=10):
    return _OptionRecord(
        type=type_, strike=strike, open_interest=oi,
        gamma=gamma, vega=vega, delta=delta, volume=volume,
    )


# ── tests ────────────────────────────────────────────────────────────────


class TestGreeksContractShape:
    """The response keys must stay stable — the React app destructures them."""

    def test_response_has_all_top_level_keys(self):
        req = _GreeksRequest(
            options=[_opt("call", 100), _opt("put", 100)],
            spot_price=100.0,
        )
        resp = compute_options_greeks(req)
        for key in ("aggregated", "gex_by_strike", "metrics", "nodes", "config"):
            assert key in resp, f"missing top-level key: {key}"

    def test_metrics_has_all_keys(self):
        req = _GreeksRequest(
            options=[_opt("call", 100), _opt("put", 100)],
            spot_price=100.0,
        )
        resp = compute_options_greeks(req)
        for key in ("total_gex", "total_vex", "zero_gamma", "max_pain",
                    "implied_move", "put_call_ratio"):
            assert key in resp["metrics"]

    def test_nodes_has_all_keys(self):
        req = _GreeksRequest(
            options=[_opt("call", 100), _opt("put", 100)],
            spot_price=100.0,
        )
        resp = compute_options_greeks(req)
        for key in ("kingNode", "gatekeepers", "midpoints", "allNodes"):
            assert key in resp["nodes"]

    def test_config_returned(self):
        req = _GreeksRequest(
            options=[_opt("call", 100)], spot_price=100.0,
        )
        resp = compute_options_greeks(req)
        assert "strike_range_pct" in resp["config"]
        assert "atm_tolerance" in resp["config"]
        assert "node_min_gamma" in resp["config"]


class TestGreeksMath:
    """Verify the refactored endpoint produces correct values."""

    def test_total_gex_consistent_with_per_strike_sum(self):
        """Critical: total_gex must equal sum(gex_by_strike[i].gex).

        This was previously broken: the old _total_gex used dealer-gamma
        unconditional negation, while _aggregate_by_strike used calls-add /
        puts-subtract. They had opposite signs. Now both come from
        lib.gamma so they're guaranteed consistent.
        """
        req = _GreeksRequest(
            options=[
                _opt("call", 100, oi=500, gamma=0.04),
                _opt("put",  100, oi=800, gamma=0.04),
                _opt("call", 105, oi=200, gamma=0.03),
                _opt("put",  95,  oi=600, gamma=0.03),
            ],
            spot_price=100.0,
        )
        resp = compute_options_greeks(req)
        per_strike_total = sum(s["gex"] for s in resp["gex_by_strike"])
        assert resp["metrics"]["total_gex"] == pytest.approx(per_strike_total)

    def test_call_dominant_strike_has_positive_gex(self):
        """Sign convention regression: call-heavy strike → positive net GEX."""
        req = _GreeksRequest(
            options=[
                _opt("call", 100, oi=10000, gamma=0.05),
                _opt("put",  100, oi=100,   gamma=0.05),
            ],
            spot_price=100.0,
        )
        resp = compute_options_greeks(req)
        strike_100 = next(s for s in resp["gex_by_strike"] if s["strike"] == 100)
        assert strike_100["gex"] > 0

    def test_put_dominant_strike_has_negative_gex(self):
        req = _GreeksRequest(
            options=[
                _opt("call", 100, oi=100,   gamma=0.05),
                _opt("put",  100, oi=10000, gamma=0.05),
            ],
            spot_price=100.0,
        )
        resp = compute_options_greeks(req)
        strike_100 = next(s for s in resp["gex_by_strike"] if s["strike"] == 100)
        assert strike_100["gex"] < 0

    def test_king_node_at_max_abs_gamma_strike(self):
        req = _GreeksRequest(
            options=[
                _opt("call", 95,  oi=100,   gamma=0.05),
                _opt("call", 100, oi=10000, gamma=0.05),  # huge
                _opt("call", 105, oi=100,   gamma=0.05),
            ],
            spot_price=100.0,
        )
        resp = compute_options_greeks(req)
        king = resp["nodes"]["kingNode"]
        assert king is not None
        assert king["strike"] == 100

    def test_put_call_ratio(self):
        """Put OI / Call OI."""
        req = _GreeksRequest(
            options=[
                _opt("call", 100, oi=500),
                _opt("put",  100, oi=1000),
            ],
            spot_price=100.0,
        )
        resp = compute_options_greeks(req)
        assert resp["metrics"]["put_call_ratio"] == pytest.approx(2.0)


class TestGreeksDegenerateInputs:
    def test_empty_options_returns_empty_payload(self):
        req = _GreeksRequest(options=[], spot_price=100.0)
        resp = compute_options_greeks(req)
        assert resp["aggregated"] == []
        assert resp["gex_by_strike"] == []
        assert resp["metrics"]["total_gex"] == 0.0
        assert resp["nodes"]["kingNode"] is None

    def test_zero_spot_returns_empty_payload(self):
        req = _GreeksRequest(
            options=[_opt("call", 100)], spot_price=0.0,
        )
        resp = compute_options_greeks(req)
        assert resp["aggregated"] == []
        assert resp["nodes"]["kingNode"] is None

    def test_negative_spot_treated_as_zero(self):
        req = _GreeksRequest(
            options=[_opt("call", 100)], spot_price=-1.0,
        )
        resp = compute_options_greeks(req)
        assert resp["metrics"]["total_gex"] == 0.0
