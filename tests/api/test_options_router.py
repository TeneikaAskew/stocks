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

REPO = Path(__file__).resolve().parent.parent.parent
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
                _opt("put",  90,  oi=1,     gamma=0.05),  # both sides present
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
        assert resp["metrics"]["total_gex"] is None
        assert resp["reason"] == "empty_chain"
        assert resp["nodes"]["kingNode"] is None

    def test_zero_spot_returns_empty_payload(self):
        req = _GreeksRequest(
            options=[_opt("call", 100), _opt("put", 100)], spot_price=0.0,
        )
        resp = compute_options_greeks(req)
        assert resp["aggregated"] == []
        assert resp["metrics"]["total_gex"] is None
        assert resp["reason"] == "spot_unavailable"
        assert resp["nodes"]["kingNode"] is None

    def test_negative_spot_treated_as_zero(self):
        req = _GreeksRequest(
            options=[_opt("call", 100), _opt("put", 100)], spot_price=-1.0,
        )
        resp = compute_options_greeks(req)
        assert resp["metrics"]["total_gex"] is None
        assert resp["reason"] == "spot_unavailable"


# ─── Snapshot provenance on the chain cache entry and the levels route ──────
# (FEAT-OPTION-001, spec 2026-10-24-feat-option-001-legacy-snapshot-labels.)
#
# The chain HTTP response keeps its origin/main shape: the provenance lives in
# the `_CHAIN_CACHE` wrapper `{"payload", "provenance"}` and is copied onto
# `/levels` with a fresh observation. Publishing it on the chain response is a
# separate decision (X1) and is not asserted here.

import threading
from datetime import date, datetime, timedelta, timezone

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.options as options_router

FIX_DATE = date(2026, 6, 1)
FIX_INSTANT = datetime(2026, 6, 1, 15, 55, tzinfo=timezone.utc)
CLOCK_T0 = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
EXPECTED_AGE_T0 = int((CLOCK_T0 - FIX_INSTANT).total_seconds())

# origin/main baselines for the fixture below (captured from the unchanged routes).
BASELINE_CHAIN_KEYS = sorted(["cached", "chain_state", "date", "metadata", "options", "snapshot_timestamp", "ticker"])
BASELINE_CHAIN_METADATA = {"source": "cloud_sql", "data_source": "alphavantage", "row_count": 6, "sides_present": "both"}
BASELINE_LEVELS = {
    "snapshot_timestamp": "2026-06-01T15:55:00+00:00",
    "chain_size": 6,
    "total_gex": 600.60015,
    "regime": "positive_gamma",
    "gamma_flip": None,          # hermetic: no risk-free rate source
    "gamma_balance": 98.33333333333333,
    "spot": {"price": 100.05, "method": "parity", "note": "K=100.0 C=2.55 P=2.50 exp=2026-06-19"},
    "gates": [],
    "warnings": [],
}
BASELINE_LEVELS_KINGS = [(95.0, -600.60015, 0.49905496145237505), (100.0, 1201.2003, 0.9960415635823852)]
BASELINE_LEVELS_N = 2
BASELINE_NAIVE_SNAPSHOT_TIMESTAMP = "2026-06-01T15:55:00"


def _chain_frame(snapshot_date: date = FIX_DATE, market_session="REALTIME", tz="UTC") -> pd.DataFrame:
    """Same six-contract chain the grid tests use (two strikes × two
    expirations × two sides, parity spot ≈ 100), as `etf_options_snapshots`
    rows with the projected `market_session` column."""
    ts = pd.Timestamp(f"{snapshot_date.isoformat()}T15:55:00")
    if tz is not None:
        ts = ts.tz_localize(tz)
    base = {"bid": 2.50, "ask": 2.60, "mark": 2.55, "last_price": 2.55, "volume": 100,
            "implied_volatility": 0.20, "theta": -0.02, "vega": 0.20, "rho": 0.04}
    rows = [
        {**base, "contract_symbol": "X1", "option_type": "calls", "strike": 95.0, "expiration": date(2026, 6, 19),
         "bid": 5.50, "ask": 5.60, "mark": 5.55, "last_price": 5.55, "open_interest": 500, "delta": 0.85, "gamma": 0.02,
         "implied_volatility": 0.18, "theta": -0.01, "vega": 0.10, "rho": 0.05},
        {**base, "contract_symbol": "X2", "option_type": "puts", "strike": 95.0, "expiration": date(2026, 6, 19),
         "bid": 0.50, "ask": 0.60, "mark": 0.55, "last_price": 0.55, "volume": 80, "open_interest": 800, "delta": -0.15,
         "gamma": 0.02, "theta": -0.01, "vega": 0.10, "rho": -0.01},
        {**base, "contract_symbol": "X3", "option_type": "calls", "strike": 100.0, "expiration": date(2026, 6, 19),
         "volume": 250, "open_interest": 1000, "delta": 0.50, "gamma": 0.05},
        {**base, "contract_symbol": "X4", "option_type": "puts", "strike": 100.0, "expiration": date(2026, 6, 19),
         "bid": 2.45, "ask": 2.55, "mark": 2.50, "last_price": 2.50, "volume": 220, "open_interest": 800, "delta": -0.50,
         "gamma": 0.05, "rho": -0.04},
        {**base, "contract_symbol": "X5", "option_type": "calls", "strike": 100.0, "expiration": date(2026, 9, 18),
         "bid": 3.50, "ask": 3.60, "mark": 3.55, "last_price": 3.55, "volume": 50, "open_interest": 400, "delta": 0.50,
         "gamma": 0.04, "implied_volatility": 0.22, "theta": -0.01, "vega": 0.35, "rho": 0.08},
        {**base, "contract_symbol": "X6", "option_type": "puts", "strike": 100.0, "expiration": date(2026, 9, 18),
         "bid": 3.45, "ask": 3.55, "mark": 3.50, "last_price": 3.50, "volume": 40, "open_interest": 350, "delta": -0.50,
         "gamma": 0.04, "implied_volatility": 0.22, "theta": -0.01, "vega": 0.35, "rho": -0.08},
    ]
    df = pd.DataFrame(rows)
    df["snapshot_ts"] = ts
    df["market_session"] = market_session
    return df


@pytest.fixture
def chain_client(monkeypatch):
    """Clean app with only the options router; Cloud SQL mocked; chain cache cleared."""
    import gcp.database
    monkeypatch.setattr(gcp.database, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(options_router, "_require_cloud_sql", lambda: None)
    options_router._CHAIN_CACHE.clear()
    app = FastAPI()
    app.include_router(options_router.router)
    return TestClient(app)


@pytest.fixture
def chain_clock(monkeypatch):
    state = {"now": CLOCK_T0}
    monkeypatch.setattr(options_router, "_now_utc", lambda: state["now"])
    return state


def _install_chain_query(monkeypatch, df):
    calls: list[str] = []

    def fake_query(sql, params=None):
        calls.append(sql)
        return df

    monkeypatch.setattr(options_router, "query_to_dataframe", fake_query)
    return calls


def _expected_prov(session="REALTIME", observed=CLOCK_T0, age=EXPECTED_AGE_T0):
    return {
        "provider": "alphavantage",
        "market_session": session,
        "snapshot_ts": "2026-06-01T15:55:00+00:00",
        "observed_at": observed.isoformat(),
        "snapshot_age_seconds": age,
        "freshness_status": "unknown",
        "completeness_status": "unknown",
        "reason": "legacy_snapshot_unqualified",
    }


class TestChainAndLevelsProvenance:
    def test_chain_http_shape_unchanged_no_provenance_key(self, chain_client, chain_clock, monkeypatch):
        _install_chain_query(monkeypatch, _chain_frame())
        first = chain_client.get("/api/options/SPY/2026-06-01")
        assert first.status_code == 200, first.text
        body = first.json()
        assert sorted(body) == BASELINE_CHAIN_KEYS
        assert "snapshot_provenance" not in body
        assert body["cached"] is False
        assert body["metadata"] == BASELINE_CHAIN_METADATA
        assert body["snapshot_timestamp"] == "2026-06-01T15:55:00+00:00"
        second = chain_client.get("/api/options/SPY/2026-06-01").json()
        assert sorted(second) == BASELINE_CHAIN_KEYS and second["cached"] is True

    def test_chain_cache_entry_retains_provenance_internally(self, chain_client, chain_clock, monkeypatch):
        _install_chain_query(monkeypatch, _chain_frame())
        assert chain_client.get("/api/options/SPY/2026-06-01").status_code == 200
        entry = options_router._CHAIN_CACHE[("SPY", "2026-06-01")]
        assert set(entry) == {"payload", "provenance"}
        assert entry["provenance"] == _expected_prov()
        assert "snapshot_provenance" not in entry["payload"]
        assert "cached" not in entry["payload"]

    def test_levels_carries_chain_provenance_and_baseline_numerics(self, chain_client, chain_clock, monkeypatch):
        _install_chain_query(monkeypatch, _chain_frame())
        r = chain_client.get("/api/options/SPY/2026-06-01/levels")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["snapshot_provenance"] == _expected_prov()
        for key, expected in BASELINE_LEVELS.items():
            assert body[key] == expected, key
        assert [(k["strike"], k["gex"], k["score"]) for k in body["kings"]] == BASELINE_LEVELS_KINGS
        assert len(body["levels"]) == BASELINE_LEVELS_N

    def test_direct_levels_call_returns_key(self, chain_client, chain_clock, monkeypatch):
        _install_chain_query(monkeypatch, _chain_frame())
        out = options_router.get_gamma_levels("SPY", "2026-06-01")
        assert out["snapshot_provenance"] == _expected_prov()
        assert out["chain_size"] == 6

    def test_chain_warm_hit_unchanged_shape_and_zero_queries(self, chain_client, chain_clock, monkeypatch):
        calls = _install_chain_query(monkeypatch, _chain_frame())
        first = chain_client.get("/api/options/SPY/2026-06-01").json()
        n = len(calls)
        assert n == 1
        chain_clock["now"] = CLOCK_T0 + timedelta(seconds=45)
        second = chain_client.get("/api/options/SPY/2026-06-01").json()
        assert len(calls) == n, "a warm chain hit ran a query"
        assert second["cached"] is True and sorted(second) == sorted(first) == BASELINE_CHAIN_KEYS
        assert options_router._CHAIN_CACHE[("SPY", "2026-06-01")]["provenance"] == _expected_prov()

    def test_levels_warm_hit_rides_chain_cache_and_advances_observation(self, chain_client, chain_clock, monkeypatch):
        calls = _install_chain_query(monkeypatch, _chain_frame())
        first = chain_client.get("/api/options/SPY/2026-06-01/levels").json()
        n = len(calls)
        chain_clock["now"] = CLOCK_T0 + timedelta(seconds=45)
        second = chain_client.get("/api/options/SPY/2026-06-01/levels").json()
        assert len(calls) == n, "levels has no cache of its own; the second call rides the chain entry"
        p1, p2 = first["snapshot_provenance"], second["snapshot_provenance"]
        assert p2["observed_at"] == (CLOCK_T0 + timedelta(seconds=45)).isoformat()
        assert p2["snapshot_age_seconds"] == p1["snapshot_age_seconds"] + 45
        assert p2["snapshot_ts"] == p1["snapshot_ts"]
        assert second["snapshot_timestamp"] == first["snapshot_timestamp"]
        assert options_router._CHAIN_CACHE[("SPY", "2026-06-01")]["provenance"] == _expected_prov()

    def test_levels_naive_rows_are_timestamp_invalid(self, chain_client, chain_clock, monkeypatch):
        _install_chain_query(monkeypatch, _chain_frame(tz=None))
        chain = chain_client.get("/api/options/SPY/2026-06-01").json()
        assert chain["snapshot_timestamp"] == BASELINE_NAIVE_SNAPSHOT_TIMESTAMP, "legacy string unchanged"
        levels = chain_client.get("/api/options/SPY/2026-06-01/levels").json()
        prov = levels["snapshot_provenance"]
        assert (prov["snapshot_ts"], prov["snapshot_age_seconds"], prov["reason"]) == (
            None, None, "timestamp_invalid")
        assert prov["market_session"] == "REALTIME"
        assert levels["snapshot_timestamp"] == BASELINE_NAIVE_SNAPSHOT_TIMESTAMP

    def test_levels_future_then_aged_and_null_sessions(self, chain_client, chain_clock, monkeypatch):
        _install_chain_query(monkeypatch, _chain_frame(market_session=None))
        chain_clock["now"] = FIX_INSTANT - timedelta(seconds=600)
        prov = chain_client.get("/api/options/SPY/2026-06-01/levels").json()["snapshot_provenance"]
        assert prov["market_session"] is None
        assert prov["snapshot_ts"] == "2026-06-01T15:55:00+00:00"
        assert prov["snapshot_age_seconds"] is None and prov["reason"] == "timestamp_future"
        chain_clock["now"] = FIX_INSTANT + timedelta(seconds=100)
        later = chain_client.get("/api/options/SPY/2026-06-01/levels").json()["snapshot_provenance"]
        assert later["snapshot_age_seconds"] == 100 and later["reason"] == "legacy_snapshot_unqualified"
        assert options_router._CHAIN_CACHE[("SPY", "2026-06-01")]["provenance"]["reason"] == "timestamp_future"

    def test_concurrent_levels_readers_keep_own_observation(self, chain_client, monkeypatch):
        _install_chain_query(monkeypatch, _chain_frame())
        local = threading.local()
        monkeypatch.setattr(options_router, "_now_utc",
                            lambda: CLOCK_T0 + timedelta(seconds=getattr(local, "offset", 0)))
        assert chain_client.get("/api/options/SPY/2026-06-01").status_code == 200
        before = dict(options_router._CHAIN_CACHE[("SPY", "2026-06-01")]["provenance"])
        results: dict[int, dict] = {}
        barrier = threading.Barrier(8)

        def reader(i):
            local.offset = 10 * i
            barrier.wait()
            results[i] = options_router.get_gamma_levels("SPY", "2026-06-01")["snapshot_provenance"]

        threads = [threading.Thread(target=reader, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for i in range(8):
            assert results[i]["observed_at"] == (CLOCK_T0 + timedelta(seconds=10 * i)).isoformat()
        assert options_router._CHAIN_CACHE[("SPY", "2026-06-01")]["provenance"] == before
