"""Tests for `platform.api.routers.grid` — the /grid + /nodes endpoints
that expose the 2-D strike × expiration heatmap (Phase B1).

All tests run via FastAPI's TestClient. Cloud SQL access is mocked by
monkey-patching `gcp.database.query_to_dataframe` so no live DB
required. Covers the tiered loader contract (realtime → EOD fallback
→ stale → unavailable), historical mode, the typed UNAVAILABLE
envelope, OPEX node tagging, and the response-shape invariants the
React app will depend on.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("fastapi")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "platform" / "api"))


try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import grid as grid_router
except ModuleNotFoundError as exc:  # pragma: no cover
    pytest.skip(f"grid router unavailable: {exc}", allow_module_level=True)


# ─── Test fixtures ──────────────────────────────────────────────────────────


def _chain_df(snapshot_date: date, market_session: str = "REALTIME") -> pd.DataFrame:
    """Build a realistic ~12-row chain DataFrame for one snapshot.

    Two strikes × two expirations × two sides — enough to exercise the
    grid math without bloating the fixture. Spot lands near 100 via
    parity at the 100 strike (call mid ≈ put mid)."""
    snapshot_ts = pd.Timestamp(f"{snapshot_date.isoformat()}T15:55:00")
    rows = []
    # Near expiration — 2026-06-20 (third Friday → OPEX)
    rows.extend([
        {"contract_symbol": "X1", "option_type": "calls", "strike": 95.0,
         "expiration": date(2026, 6, 19), "bid": 5.50, "ask": 5.60, "mark": 5.55,
         "last_price": 5.55, "volume": 100, "open_interest": 500,
         "implied_volatility": 0.18, "delta": 0.85, "gamma": 0.02,
         "theta": -0.01, "vega": 0.10, "rho": 0.05,
         "snapshot_ts": snapshot_ts, "snapshot_date": snapshot_date},
        {"contract_symbol": "X2", "option_type": "puts", "strike": 95.0,
         "expiration": date(2026, 6, 19), "bid": 0.50, "ask": 0.60, "mark": 0.55,
         "last_price": 0.55, "volume": 80, "open_interest": 800,
         "implied_volatility": 0.20, "delta": -0.15, "gamma": 0.02,
         "theta": -0.01, "vega": 0.10, "rho": -0.01,
         "snapshot_ts": snapshot_ts, "snapshot_date": snapshot_date},
        {"contract_symbol": "X3", "option_type": "calls", "strike": 100.0,
         "expiration": date(2026, 6, 19), "bid": 2.50, "ask": 2.60, "mark": 2.55,
         "last_price": 2.55, "volume": 250, "open_interest": 1000,
         "implied_volatility": 0.20, "delta": 0.50, "gamma": 0.05,
         "theta": -0.02, "vega": 0.20, "rho": 0.04,
         "snapshot_ts": snapshot_ts, "snapshot_date": snapshot_date},
        {"contract_symbol": "X4", "option_type": "puts", "strike": 100.0,
         "expiration": date(2026, 6, 19), "bid": 2.45, "ask": 2.55, "mark": 2.50,
         "last_price": 2.50, "volume": 220, "open_interest": 800,
         "implied_volatility": 0.20, "delta": -0.50, "gamma": 0.05,
         "theta": -0.02, "vega": 0.20, "rho": -0.04,
         "snapshot_ts": snapshot_ts, "snapshot_date": snapshot_date},
    ])
    # Far expiration — 2026-09-19 (third Friday → OPEX)
    rows.extend([
        {"contract_symbol": "X5", "option_type": "calls", "strike": 100.0,
         "expiration": date(2026, 9, 18), "bid": 3.50, "ask": 3.60, "mark": 3.55,
         "last_price": 3.55, "volume": 50, "open_interest": 400,
         "implied_volatility": 0.22, "delta": 0.50, "gamma": 0.04,
         "theta": -0.01, "vega": 0.35, "rho": 0.08,
         "snapshot_ts": snapshot_ts, "snapshot_date": snapshot_date},
        {"contract_symbol": "X6", "option_type": "puts", "strike": 100.0,
         "expiration": date(2026, 9, 18), "bid": 3.45, "ask": 3.55, "mark": 3.50,
         "last_price": 3.50, "volume": 40, "open_interest": 350,
         "implied_volatility": 0.22, "delta": -0.50, "gamma": 0.04,
         "theta": -0.01, "vega": 0.35, "rho": -0.08,
         "snapshot_ts": snapshot_ts, "snapshot_date": snapshot_date},
    ])
    df = pd.DataFrame(rows)
    return df


@pytest.fixture
def client(monkeypatch):
    """A clean FastAPI app with only the grid router and Cloud SQL mocked."""
    # Mock is_cloud_sql_configured() → True everywhere it's lazy-imported
    import gcp.database
    monkeypatch.setattr(gcp.database, "is_cloud_sql_configured", lambda: True)

    # Caches must be cleared between tests to avoid cross-test leakage
    grid_router._LIVE_GRID_CACHE.clear()
    grid_router._HIST_GRID_CACHE.clear()
    grid_router._NODES_CACHE.clear()
    grid_router._HIST_NODES_CACHE.clear()

    app = FastAPI()
    app.include_router(grid_router.router)
    return TestClient(app)


def _install_query_router(monkeypatch, realtime_df=None, eod_df=None):
    """Route the lazy `query_to_dataframe` import to fixture DataFrames
    based on which CTE filter the SQL contains. Reads the SQL text to
    decide which path is being exercised."""
    def fake_query(sql, params=None):
        if "market_session = 'REALTIME'" in sql:
            return realtime_df if realtime_df is not None else pd.DataFrame()
        if "market_session = 'EOD'" in sql:
            return eod_df if eod_df is not None else pd.DataFrame()
        return pd.DataFrame()
    import gcp.database
    monkeypatch.setattr(gcp.database, "query_to_dataframe", fake_query)


# ─── /grid live endpoint ────────────────────────────────────────────────────


class TestGridLive:
    """GET /api/options/{ticker}/grid"""

    def test_realtime_path_returns_data_source_realtime(self, client, monkeypatch):
        """When the realtime probe finds rows, data_source='realtime'."""
        rt = _chain_df(date(2026, 5, 23), "REALTIME")
        _install_query_router(monkeypatch, realtime_df=rt)

        r = client.get("/api/options/SPY/grid")
        assert r.status_code == 200
        data = r.json()
        assert data["ticker"] == "SPY"
        assert data["data_source"] == "realtime"
        assert data["snapshot_ts"] is not None
        assert data["snapshot_date"] == "2026-05-23"
        assert len(data["cells"]) > 0
        assert data["spot"]["price"] > 0

    def test_eod_fallback_when_no_realtime(self, client, monkeypatch):
        """No REALTIME rows → falls back to EOD with data_source='eod_fallback'."""
        eod = _chain_df(date.today() - pd.Timedelta(days=1), "EOD")
        _install_query_router(monkeypatch, realtime_df=None, eod_df=eod)

        r = client.get("/api/options/IWM/grid")
        assert r.status_code == 200
        data = r.json()
        # ≤2 trading days behind → eod_fallback (not stale)
        assert data["data_source"] == "eod_fallback"
        assert len(data["cells"]) > 0

    def test_unavailable_envelope_when_no_data(self, client, monkeypatch):
        """Neither REALTIME nor EOD rows → typed unavailable envelope.

        Critical: HTTP 200 (not 404) so the UI can render the
        unavailable footer gracefully. Cells empty, no synthetic
        numbers. Mirrors Track 1 contract."""
        _install_query_router(monkeypatch, realtime_df=None, eod_df=None)

        r = client.get("/api/options/RANDOM/grid")
        assert r.status_code == 200
        data = r.json()
        assert data["data_source"] == "unavailable"
        assert data["cells"] == []
        assert data["spot"] is None
        assert "warnings" in data

    def test_invalid_ticker_returns_400(self, client, monkeypatch):
        """Hyphen makes the ticker non-alnum — validator rejects."""
        _install_query_router(monkeypatch)
        r = client.get("/api/options/AB-CD/grid")
        assert r.status_code == 400

    def test_too_long_ticker_returns_400(self, client, monkeypatch):
        _install_query_router(monkeypatch)
        r = client.get("/api/options/ABCDEFGHIJK/grid")  # 11 chars
        assert r.status_code == 400

    def test_cache_header_60s_on_live(self, client, monkeypatch):
        rt = _chain_df(date(2026, 5, 23), "REALTIME")
        _install_query_router(monkeypatch, realtime_df=rt)
        r = client.get("/api/options/SPY/grid")
        assert r.headers["cache-control"] == "public, max-age=60"

    def test_strike_window_pct_filters_cells(self, client, monkeypatch):
        """Narrow window drops far cells."""
        rt = _chain_df(date(2026, 5, 23), "REALTIME")
        _install_query_router(monkeypatch, realtime_df=rt)

        # ±2% around spot ≈ 100 → only 100-strike cells survive
        r = client.get("/api/options/SPY/grid?strike_window_pct=2.0")
        data = r.json()
        for c in data["cells"]:
            assert 98 <= c["strike"] <= 102


# ─── /grid historical endpoint ──────────────────────────────────────────────


class TestGridHistorical:
    """GET /api/options/{ticker}/{date}/grid"""

    def test_historical_returns_eod_fallback(self, client, monkeypatch):
        """Historical mode reads EOD only. Within freshness window
        returns eod_fallback."""
        eod = _chain_df(date(2026, 5, 22), "EOD")
        _install_query_router(monkeypatch, realtime_df=None, eod_df=eod)

        r = client.get("/api/options/SPY/2026-05-22/grid")
        assert r.status_code == 200
        data = r.json()
        assert data["data_source"] == "eod_fallback"
        assert data["snapshot_date"] == "2026-05-22"
        assert len(data["cells"]) > 0

    def test_historical_invalid_date_returns_400(self, client, monkeypatch):
        _install_query_router(monkeypatch)
        r = client.get("/api/options/SPY/not-a-date/grid")
        assert r.status_code == 400

    def test_historical_unavailable_when_no_data(self, client, monkeypatch):
        _install_query_router(monkeypatch, realtime_df=None, eod_df=None)
        r = client.get("/api/options/SPY/2026-05-22/grid")
        assert r.status_code == 200
        assert r.json()["data_source"] == "unavailable"

    def test_historical_cache_12h(self, client, monkeypatch):
        eod = _chain_df(date(2026, 5, 22), "EOD")
        _install_query_router(monkeypatch, eod_df=eod)
        r = client.get("/api/options/SPY/2026-05-22/grid")
        assert r.headers["cache-control"] == "public, max-age=43200"


# ─── /nodes endpoints ───────────────────────────────────────────────────────


class TestNodesLive:
    """GET /api/options/{ticker}/nodes"""

    def test_returns_king_gate_taxonomy(self, client, monkeypatch):
        """Heavy 100 strike → King at 100 from the 1-D taxonomy."""
        rt = _chain_df(date(2026, 5, 23), "REALTIME")
        _install_query_router(monkeypatch, realtime_df=rt)

        r = client.get("/api/options/SPY/nodes")
        assert r.status_code == 200
        data = r.json()
        # Shape: king is dict OR None; gates / midpoints / hedge / opex are arrays
        assert "king" in data
        assert isinstance(data.get("gates", []), list)
        assert isinstance(data.get("midpoints", []), list)
        assert isinstance(data.get("hedge_nodes", []), list)
        assert isinstance(data.get("opex_nodes", []), list)
        assert "regime" in data
        assert "flip" in data

    def test_opex_nodes_tagged_for_third_fridays(self, client, monkeypatch):
        """Cells whose expiration is a third Friday are tagged as OPEX
        nodes. The fixture uses 2026-06-20 and 2026-09-19, both third
        Fridays."""
        rt = _chain_df(date(2026, 5, 23), "REALTIME")
        _install_query_router(monkeypatch, realtime_df=rt)

        r = client.get("/api/options/SPY/nodes")
        opex = r.json()["opex_nodes"]
        # Both fixture expirations are third Fridays → tagged
        expirations = {n["expiration"] for n in opex}
        assert "2026-06-19" in expirations
        assert "2026-09-18" in expirations
        # Every opex node carries the calendar context
        for n in opex:
            assert "dte" in n
            assert n["dte"] >= 0
            assert "strike" in n
            assert "gex" in n

    def test_hedge_nodes_empty_in_b1(self, client, monkeypatch):
        """Phase B1 doesn't yet detect hedge nodes (Phase D adds the
        economic_events join). Empty array, not missing or null."""
        rt = _chain_df(date(2026, 5, 23), "REALTIME")
        _install_query_router(monkeypatch, realtime_df=rt)
        r = client.get("/api/options/SPY/nodes")
        assert r.json()["hedge_nodes"] == []

    def test_tactical_summary_null_in_b1(self, client, monkeypatch):
        """Phase B1 returns placeholder None; Phase D wires the AI."""
        rt = _chain_df(date(2026, 5, 23), "REALTIME")
        _install_query_router(monkeypatch, realtime_df=rt)
        r = client.get("/api/options/SPY/nodes")
        assert r.json()["tactical_summary"] is None

    def test_unavailable_envelope_shape(self, client, monkeypatch):
        _install_query_router(monkeypatch, realtime_df=None, eod_df=None)
        r = client.get("/api/options/RANDOM/nodes")
        assert r.status_code == 200
        d = r.json()
        # The unavailable response still has the full shape — UI can
        # destructure without conditional guards.
        assert d["data_source"] == "unavailable"
        assert d["king"] is None
        assert d["gates"] == []
        assert d["opex_nodes"] == []
        assert d["hedge_nodes"] == []


class TestNodesHistorical:
    """GET /api/options/{ticker}/{date}/nodes"""

    def test_historical_returns_taxonomy(self, client, monkeypatch):
        eod = _chain_df(date(2026, 5, 22), "EOD")
        _install_query_router(monkeypatch, eod_df=eod)
        r = client.get("/api/options/SPY/2026-05-22/nodes")
        assert r.status_code == 200
        d = r.json()
        assert d["data_source"] == "eod_fallback"
        assert "king" in d
        assert "opex_nodes" in d


# ─── Date helpers ───────────────────────────────────────────────────────────


class TestThirdFridayDetection:
    """Mechanical OPEX tagging — third Friday of the month."""

    def test_2026_06_19_is_third_friday(self):
        assert grid_router._is_third_friday(date(2026, 6, 19))

    def test_2026_09_18_is_third_friday(self):
        assert grid_router._is_third_friday(date(2026, 9, 18))

    def test_2026_06_12_not_third_friday(self):
        # Second Friday of June 2026 — weekly expiry, NOT monthly OPEX
        assert not grid_router._is_third_friday(date(2026, 6, 12))

    def test_wednesday_never_third_friday(self):
        # Any Wednesday — not a Friday at all
        assert not grid_router._is_third_friday(date(2026, 6, 17))

    def test_day_21_friday_is_third_friday_boundary(self):
        """Latest day-of-month a third Friday can land on is 21."""
        # 2026-08-21 — Friday, day 21 → third Friday
        d = date(2026, 8, 21)
        assert d.weekday() == 4
        assert grid_router._is_third_friday(d)
