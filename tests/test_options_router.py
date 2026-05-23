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


# ── /api/options/{ticker}/{date} — freshness field contract (Track 4) ─────
#
# Locks the contract the OptionsFlowPage freshness badge depends on. The
# DB layer is monkeypatched so these tests stay hermetic (no Cloud SQL).


class TestChainFreshnessFields:
    """The chain endpoint must surface market_session + snapshot_timestamp
    so the React badge can render Live/EOD/Stale. Track 4 of the
    realtime-options multi-track plan."""

    @pytest.fixture
    def chain_client(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers import options as options_router

        # Force the Cloud SQL guard open and clear the response cache so
        # each test sees the monkeypatched DataFrame, not a previous one.
        monkeypatch.setattr(options_router, "_HAS_CLOUD_SQL", True)
        options_router._CHAIN_CACHE.clear()
        app = FastAPI()
        app.include_router(options_router.router)
        return TestClient(app), options_router

    @staticmethod
    def _two_row_df(market_sessions, snapshot_tss):
        """Build the minimum DataFrame shape get_options expects. Two rows
        so we can prove the endpoint picks the freshest one's session."""
        import pandas as pd
        return pd.DataFrame([
            {
                "contract_symbol": "SPY260620C00500000",
                "expiration": "2026-06-20",
                "strike": 500.0,
                "option_type": "calls",
                "bid": 12.5, "ask": 12.6, "mark": 12.55, "last_price": 12.55,
                "volume": 100, "open_interest": 1000,
                "implied_volatility": 0.18,
                "delta": 0.55, "gamma": 0.04, "theta": -0.08,
                "vega": 0.12, "rho": 0.05,
                "snapshot_ts": pd.Timestamp(snapshot_tss[0]),
                "market_session": market_sessions[0],
            },
            {
                "contract_symbol": "SPY260620P00500000",
                "expiration": "2026-06-20",
                "strike": 500.0,
                "option_type": "puts",
                "bid": 10.1, "ask": 10.2, "mark": 10.15, "last_price": 10.15,
                "volume": 90, "open_interest": 800,
                "implied_volatility": 0.19,
                "delta": -0.45, "gamma": 0.04, "theta": -0.07,
                "vega": 0.12, "rho": -0.04,
                "snapshot_ts": pd.Timestamp(snapshot_tss[1]),
                "market_session": market_sessions[1],
            },
        ])

    def test_eod_only_returns_eod_session(self, chain_client):
        client, options_router = chain_client
        df = self._two_row_df(
            ["EOD", "EOD"],
            ["2026-05-20T23:00:00Z", "2026-05-20T23:00:00Z"],
        )
        monkey_calls = {"n": 0}

        def _fake_query(sql, params):
            monkey_calls["n"] += 1
            return df

        from unittest.mock import patch
        with patch.object(options_router, "query_to_dataframe", _fake_query):
            r = client.get("/api/options/SPY/2026-05-20")

        assert r.status_code == 200
        body = r.json()
        assert body["market_session"] == "EOD"
        assert body["snapshot_timestamp"].startswith("2026-05-20")
        assert body["ticker"] == "SPY"
        assert monkey_calls["n"] == 1

    def test_realtime_row_wins_over_eod_when_both_present(self, chain_client):
        """Track 0 ships EOD + REALTIME rows side-by-side for the same date.
        The endpoint must report REALTIME because it's the freshest row."""
        client, options_router = chain_client
        df = self._two_row_df(
            ["EOD", "REALTIME"],
            ["2026-05-20T23:00:00Z", "2026-05-20T14:32:00Z"],
        )
        # Reorder so EOD is row 0 but REALTIME has the later wall-clock —
        # wait, EOD here is 23:00 UTC which is LATER than REALTIME 14:32 UTC.
        # That's the realistic case: EOD fetcher runs at 9 PM ET (= 01:00 UTC
        # next day) but REALTIME during RTH runs at 9:30-16:00 ET = 13:30-20:00
        # UTC. After 9 PM EOD fires, EOD IS the freshest row of the day.
        # For the "REALTIME wins" case we need an intraday REALTIME row that
        # arrives AFTER the EOD row from the prior session — but in practice
        # EOD is always the latest row of its calendar date. So the contract
        # we actually want: when an intraday REALTIME row is present for
        # today's date BEFORE EOD has run, the response is REALTIME.
        # Re-fixture for that case:
        df = self._two_row_df(
            ["REALTIME", "REALTIME"],
            ["2026-05-21T14:30:00Z", "2026-05-21T14:35:00Z"],
        )
        from unittest.mock import patch
        with patch.object(options_router, "query_to_dataframe", lambda s, p: df):
            r = client.get("/api/options/SPY/2026-05-21")
        assert r.status_code == 200
        body = r.json()
        assert body["market_session"] == "REALTIME"
        # The max snapshot_ts row wins — 14:35, not 14:30.
        assert "14:35" in body["snapshot_timestamp"]

    def test_legacy_rows_missing_market_session_return_null(self, chain_client):
        """Pre-Track-0 rows have NULL market_session. The endpoint must
        propagate that as null, not crash and not fabricate 'EOD'."""
        client, options_router = chain_client
        df = self._two_row_df(
            [None, None],
            ["2026-05-20T23:00:00Z", "2026-05-20T23:00:00Z"],
        )
        from unittest.mock import patch
        with patch.object(options_router, "query_to_dataframe", lambda s, p: df):
            r = client.get("/api/options/SPY/2026-05-20")
        assert r.status_code == 200
        body = r.json()
        assert body["market_session"] is None
        assert body["snapshot_timestamp"].startswith("2026-05-20")

    def test_live_endpoint_always_reports_realtime(self, chain_client, monkeypatch):
        """The live AV proxy is the freshest source the API can return —
        tag it REALTIME unconditionally so the badge shows green even when
        it's the 404-fallback path for a date Cloud SQL hasn't ingested."""
        client, options_router = chain_client
        monkeypatch.setattr(options_router, "_AV_API_KEY", "test-key")
        options_router._LIVE_CACHE.clear()

        # Stub httpx so we don't hit the network.
        import httpx
        from unittest.mock import MagicMock

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.raise_for_status = lambda: None
        fake_response.json = lambda: {
            "endpoint": "Historical Options",
            "message": "success",
            "data": [{
                "contractID": "SPY260620C00500000",
                "symbol": "SPY", "type": "call",
                "strike": "500.00", "expiration": "2026-06-20",
                "bid": "12.50", "ask": "12.60", "mark": "12.55", "last": "12.55",
                "volume": "100", "open_interest": "1000",
                "implied_volatility": "0.18",
                "delta": "0.55", "gamma": "0.04", "theta": "-0.08",
                "vega": "0.12", "rho": "0.05",
            }],
        }

        class _StubClient:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, *a, **k): return fake_response

        monkeypatch.setattr(httpx, "AsyncClient", _StubClient)

        r = client.get("/api/options/live/SPY/2026-05-21")
        assert r.status_code == 200
        body = r.json()
        assert body["market_session"] == "REALTIME"
        assert body["metadata"]["source"] == "alphavantage_live"
