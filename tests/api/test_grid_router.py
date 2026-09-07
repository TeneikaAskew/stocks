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

REPO = Path(__file__).resolve().parent.parent.parent
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
    # B2 caches — same rationale
    grid_router._TIMESERIES_CACHE.clear()
    grid_router._ONDEMAND_RATE_CACHE.clear()

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
        """Neither REALTIME nor EOD rows AND on-demand opted out →
        typed unavailable envelope.

        Critical: HTTP 200 (not 404) so the UI can render the
        unavailable footer gracefully. Cells empty, no synthetic
        numbers. Mirrors Track 1 contract.

        Phase B2 added on-demand AV dispatch for off-list tickers, so
        this test passes `?allow_on_demand=false` to exercise the
        original envelope behavior. The on-demand path itself has its
        own coverage in TestOnDemand.
        """
        _install_query_router(monkeypatch, realtime_df=None, eod_df=None)

        r = client.get("/api/options/RANDOM/grid?allow_on_demand=false")
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
        assert "gamma_balance" in data
        assert "gamma_flip" in data

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
        """`/nodes` doesn't yet support on-demand fallback (Phase B2
        scoped the on-demand path to /grid only — adding it to /nodes
        is a one-line lift in a follow-up). For now an off-list ticker
        with no Cloud SQL data returns the unavailable envelope
        directly."""
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


class TestRoutingOrder:
    """Regression test for the path-collision bug Codex caught on PR #541.

    The existing `options.router` has a greedy
    `GET /api/options/{ticker}/{date_str}` route. If `grid.router` is
    registered AFTER `options.router`, FastAPI's first-match-wins
    routing greedily binds `/api/options/SPY/grid` to the options
    handler with `date_str='grid'`, which then 400s in date validation.

    `main.py` registers `grid.router` BEFORE `options.router` to prevent
    this. This test asserts the production-order app actually routes
    `/grid` and `/nodes` to the grid handlers, not the options handler.
    """

    @pytest.fixture
    def combined_client(self, monkeypatch):
        """Mount grid AND options in the production order from main.py."""
        import gcp.database
        monkeypatch.setattr(gcp.database, "is_cloud_sql_configured", lambda: True)

        grid_router._LIVE_GRID_CACHE.clear()
        grid_router._HIST_GRID_CACHE.clear()
        grid_router._NODES_CACHE.clear()
        grid_router._HIST_NODES_CACHE.clear()

        # Empty REALTIME + EOD — exercise the routing, not the data path
        def fake_query(sql, params=None):
            return pd.DataFrame()
        monkeypatch.setattr(gcp.database, "query_to_dataframe", fake_query)

        from routers import options as options_router
        options_router._CHAIN_CACHE.clear()

        app = FastAPI()
        # Same order as main.py — `grid` BEFORE `options`
        app.include_router(grid_router.router)
        app.include_router(options_router.router)
        return TestClient(app)

    def test_grid_route_resolves_to_grid_handler(self, combined_client):
        """`/api/options/SPY/grid` must NOT be 400 from date validation —
        the grid router has to win the routing battle."""
        r = combined_client.get("/api/options/SPY/grid")
        # No data → unavailable envelope; the key thing is we got HERE
        # (200 from the grid handler) instead of a 400 from options'
        # date validation rejecting date_str='grid'.
        assert r.status_code == 200, (
            f"Expected 200 (grid handler), got {r.status_code} — likely "
            f"the greedy options.router path shadowed the new endpoint. "
            f"Response: {r.json()}"
        )
        body = r.json()
        # The grid handler always returns this key; the options handler
        # never does.
        assert "data_source" in body
        assert "cells" in body

    def test_nodes_route_resolves_to_grid_handler(self, combined_client):
        """Same routing check for `/api/options/SPY/nodes`."""
        r = combined_client.get("/api/options/SPY/nodes")
        assert r.status_code == 200, (
            f"Expected 200 (nodes handler), got {r.status_code}. "
            f"Response: {r.json()}"
        )
        body = r.json()
        # Nodes-specific shape — proves we landed in _build_nodes_payload
        # / unavailable envelope, NOT the options chain handler.
        assert "king" in body
        assert "gates" in body
        assert "opex_nodes" in body

    def test_historical_grid_route_resolves(self, combined_client):
        """Historical mode lives at `/api/options/{ticker}/{date}/grid` —
        three path segments, so it doesn't collide with the two-segment
        options route. Sanity check that it routes correctly."""
        r = combined_client.get("/api/options/SPY/2026-05-22/grid")
        assert r.status_code == 200
        assert "data_source" in r.json()

    def test_options_two_segment_route_still_works(self, combined_client):
        """The pre-existing `/api/options/{ticker}/{date_str}` must still
        route to the options handler — our reordering can't break it.
        Empty fixtures → options handler 404s (no data). Status code
        is the routing proof: 404 from options, NOT 200 from grid."""
        r = combined_client.get("/api/options/SPY/2026-05-22")
        # Could be 404 (no data — options handler's behavior) or 200
        # (cached empty result). What it CANNOT be is anything from
        # the grid handler (no `data_source` field, no `cells`).
        if r.status_code == 200:
            body = r.json()
            # Options chain handler returns `options` key, not `cells`
            assert "options" in body, (
                "Pre-existing /api/options/{ticker}/{date} should route "
                "to options.get_options, not grid handler. "
                f"Got: {list(body.keys())}"
            )


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


# ─── Phase B2 — on-demand dispatch, rate limit, BSM, timeseries ────────────


class TestOnDemandDispatch:
    """On-demand AV fetch for off-list tickers when Cloud SQL has no data."""

    @pytest.fixture(autouse=True)
    def _reset_rate_limit(self):
        """Each test starts with a clean rate-limit cache so a noisy
        prior test can't bleed in."""
        grid_router._ONDEMAND_RATE_CACHE.clear()
        yield

    def test_on_demand_fires_for_off_list_ticker(self, client, monkeypatch):
        """When ticker isn't SPY/IWM/QQQ and Cloud SQL is empty, the
        router fires the AV fetcher. Tests this by stubbing
        `fetch_av_realtime_options` to return a fixture chain."""
        _install_query_router(monkeypatch)  # empty Cloud SQL

        # Stub the AV fetcher to return a chain. The router uses a lazy
        # import (`from gcp.fetchers.fetch_av_realtime_options import
        # fetch_av_realtime_options`); patch the source module so the
        # lazy import sees the stub.
        import gcp.fetchers.fetch_av_realtime_options as fetcher_mod

        def fake_fetch(ticker, api_key, snapshot_ts):
            df = _chain_df(snapshot_ts.date(), "REALTIME")
            df["ticker"] = ticker.upper()
            df["market_session"] = "REALTIME"
            df["data_source"] = "alphavantage"
            return df

        monkeypatch.setattr(fetcher_mod, "fetch_av_realtime_options", fake_fetch)
        # Force API key to non-empty so the 503 short-circuit doesn't fire.
        monkeypatch.setattr(grid_router, "_AV_API_KEY", "test-key")
        # No-op upsert — we don't want to write to a real DB in the test.
        import gcp.database
        monkeypatch.setattr(gcp.database, "upsert_dataframe",
                            lambda df, table, cols: None)

        r = client.get("/api/options/NVDA/grid")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["data_source"] == "realtime"
        assert len(data["cells"]) > 0
        assert data["ticker"] == "NVDA"

    def test_on_demand_503_when_av_key_missing(self, client, monkeypatch):
        """No AV key → 503 (typed signal, not silent fallback)."""
        _install_query_router(monkeypatch)
        monkeypatch.setattr(grid_router, "_AV_API_KEY", "")

        r = client.get("/api/options/NVDA/grid")
        assert r.status_code == 503
        assert "on-demand" in r.json()["detail"].lower()

    def test_on_demand_503_when_av_returns_unavailable(self, client, monkeypatch):
        """AV's RealtimeOptionsUnavailable (sample data / tier downgrade /
        empty) bubbles up as a 503 to the client."""
        _install_query_router(monkeypatch)
        monkeypatch.setattr(grid_router, "_AV_API_KEY", "test-key")

        import gcp.fetchers.fetch_av_realtime_options as fetcher_mod

        def fake_fetch(ticker, api_key, snapshot_ts):
            raise fetcher_mod.RealtimeOptionsUnavailable(
                f"AV returned sample data for {ticker}"
            )

        monkeypatch.setattr(fetcher_mod, "fetch_av_realtime_options", fake_fetch)

        r = client.get("/api/options/NVDA/grid")
        assert r.status_code == 503
        assert "sample data" in r.json()["detail"].lower() or \
               "unavailable" in r.json()["detail"].lower()

    def test_allow_on_demand_false_skips_av_call(self, client, monkeypatch):
        """`?allow_on_demand=false` short-circuits to the envelope
        WITHOUT firing AV. The opt-out is critical for B1-era tests
        and for callers who want a hard 'is data ready?' check."""
        _install_query_router(monkeypatch)
        monkeypatch.setattr(grid_router, "_AV_API_KEY", "test-key")

        # If on-demand fired this would either succeed or 503; with
        # allow_on_demand=false neither should happen — straight to envelope.
        import gcp.fetchers.fetch_av_realtime_options as fetcher_mod

        def fake_fetch(*a, **kw):
            raise AssertionError("AV fetcher must NOT be called when "
                                 "allow_on_demand=false")
        monkeypatch.setattr(fetcher_mod, "fetch_av_realtime_options", fake_fetch)

        r = client.get("/api/options/NVDA/grid?allow_on_demand=false")
        assert r.status_code == 200
        assert r.json()["data_source"] == "unavailable"

    def test_scheduled_tickers_never_hit_on_demand_path(self, client, monkeypatch):
        """SPY/IWM/QQQ falls back to envelope when Cloud SQL is empty —
        on-demand is reserved for off-list tickers because Track 0's
        scheduler keeps the scheduled list current."""
        _install_query_router(monkeypatch)
        monkeypatch.setattr(grid_router, "_AV_API_KEY", "test-key")

        import gcp.fetchers.fetch_av_realtime_options as fetcher_mod

        def fake_fetch(*a, **kw):
            raise AssertionError("AV fetcher must NOT be called for "
                                 "scheduled tickers — they're served from "
                                 "Cloud SQL only")
        monkeypatch.setattr(fetcher_mod, "fetch_av_realtime_options", fake_fetch)

        # SPY is a scheduled ticker; no Cloud SQL data; no on-demand.
        # Expect the envelope.
        r = client.get("/api/options/SPY/grid")
        assert r.status_code == 200
        assert r.json()["data_source"] == "unavailable"


class TestOnDemandRateLimit:
    """Per-IP per-60s cap of 10 unique tickers on the on-demand path."""

    @pytest.fixture(autouse=True)
    def _reset_rate_limit(self):
        grid_router._ONDEMAND_RATE_CACHE.clear()
        yield

    def test_under_limit_passes(self):
        """First 10 unique tickers from one IP — all allowed."""
        for i in range(grid_router._ONDEMAND_MAX_TICKERS_PER_WINDOW):
            grid_router._check_ondemand_rate_limit("1.2.3.4", f"T{i}")
            # No exception = allowed

    def test_repeat_ticker_does_not_count_again(self):
        """Same ticker from same IP repeats freely — only DISTINCT
        tickers consume the budget."""
        for _ in range(50):
            grid_router._check_ondemand_rate_limit("1.2.3.4", "NVDA")
            # No exception even after 50 repeats

    def test_11th_unique_ticker_raises_429(self):
        """Crossing the cap → 429 with Retry-After header."""
        from fastapi import HTTPException
        for i in range(grid_router._ONDEMAND_MAX_TICKERS_PER_WINDOW):
            grid_router._check_ondemand_rate_limit("1.2.3.4", f"T{i}")
        # 11th unique ticker — cap exceeded
        with pytest.raises(HTTPException) as excinfo:
            grid_router._check_ondemand_rate_limit("1.2.3.4", "TBLOCKED")
        assert excinfo.value.status_code == 429
        assert "Retry-After" in excinfo.value.headers

    def test_different_ips_have_independent_budgets(self):
        """A noisy IP doesn't block other IPs."""
        for i in range(grid_router._ONDEMAND_MAX_TICKERS_PER_WINDOW):
            grid_router._check_ondemand_rate_limit("1.1.1.1", f"T{i}")
        # 2.2.2.2 should still be at zero — independent budget
        grid_router._check_ondemand_rate_limit("2.2.2.2", "FRESH1")
        grid_router._check_ondemand_rate_limit("2.2.2.2", "FRESH2")
        # No exceptions


class TestGridTimeseries:
    """GET /api/options/{ticker}/grid/timeseries — realtime rate-of-change."""

    def _multi_snapshot_df(self) -> pd.DataFrame:
        """Three snapshots 5 minutes apart, two strikes, one expiration."""
        snapshots = [
            pd.Timestamp("2026-05-23T15:45:00", tz="UTC"),
            pd.Timestamp("2026-05-23T15:50:00", tz="UTC"),
            pd.Timestamp("2026-05-23T15:55:00", tz="UTC"),
        ]
        rows = []
        for snap in snapshots:
            for strike, gamma_v in [(100.0, 0.05), (105.0, 0.04)]:
                rows.append({
                    "snapshot_ts": snap,
                    "snapshot_date": snap.date(),
                    "expiration": date(2026, 6, 19),
                    "strike": strike,
                    "option_type": "calls",
                    "open_interest": 1000,
                    "gamma": gamma_v,
                    "vega": 0.20,
                })
                rows.append({
                    "snapshot_ts": snap,
                    "snapshot_date": snap.date(),
                    "expiration": date(2026, 6, 19),
                    "strike": strike,
                    "option_type": "puts",
                    "open_interest": 800,
                    "gamma": gamma_v,
                    "vega": 0.20,
                })
        return pd.DataFrame(rows)

    def test_basic_shape(self, client, monkeypatch):
        df = self._multi_snapshot_df()
        import gcp.database
        monkeypatch.setattr(gcp.database, "query_to_dataframe",
                            lambda sql, params=None: df.copy())

        r = client.get("/api/options/SPY/grid/timeseries")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ticker"] == "SPY"
        # This fixture carries no quotes or deltas, so the spot is the
        # chain's median strike. Since #825 that is served but labelled:
        # `realtime_degraded` with a warning naming the method, never a
        # bare `realtime` as if a $102.50 spot had come from the market.
        assert data["data_source"] == "realtime_degraded"
        assert data["spot_method"] == "median_strike"
        assert any("median strike" in w for w in data["warnings"])
        assert data["expiration"] is not None
        assert isinstance(data["series"], list)
        assert len(data["series"]) > 0
        # Each row has the expected fields
        for row in data["series"]:
            assert "snapshot_ts" in row
            assert "strike" in row
            assert "gex" in row
            assert "delta_from_prev" in row

    def test_delta_from_prev_null_on_first_snapshot(self, client, monkeypatch):
        df = self._multi_snapshot_df()
        import gcp.database
        monkeypatch.setattr(gcp.database, "query_to_dataframe",
                            lambda sql, params=None: df.copy())

        r = client.get("/api/options/SPY/grid/timeseries?strikes=100")
        data = r.json()
        # The first snapshot for strike 100 should have null delta
        strike_100_rows = [r for r in data["series"] if r["strike"] == 100.0]
        assert strike_100_rows[0]["delta_from_prev"] is None
        # Subsequent rows should have a numeric delta
        assert all(r["delta_from_prev"] is not None for r in strike_100_rows[1:])

    def test_unavailable_when_no_realtime_rows(self, client, monkeypatch):
        import gcp.database
        monkeypatch.setattr(gcp.database, "query_to_dataframe",
                            lambda sql, params=None: pd.DataFrame())

        r = client.get("/api/options/SPY/grid/timeseries")
        assert r.status_code == 200
        data = r.json()
        assert data["data_source"] == "unavailable"
        assert data["series"] == []
        assert "warnings" in data

    def test_invalid_lookback_returns_400(self, client, monkeypatch):
        r = client.get("/api/options/SPY/grid/timeseries?lookback_hours=0")
        assert r.status_code == 422  # FastAPI's Query(ge=0.0833) rejects this

    def test_explicit_strikes_filter(self, client, monkeypatch):
        df = self._multi_snapshot_df()
        import gcp.database
        monkeypatch.setattr(gcp.database, "query_to_dataframe",
                            lambda sql, params=None: df.copy())

        r = client.get("/api/options/SPY/grid/timeseries?strikes=105")
        data = r.json()
        assert data["strikes_resolved"] == [105.0]
        for row in data["series"]:
            assert row["strike"] == 105.0

    def test_malformed_strikes_returns_400(self, client, monkeypatch):
        """`?strikes=abc` must surface a typed 4xx, not an internal 500.

        Regression test for the Codex review on PR #544 — earlier
        version did `{float(s) for s in strikes.split(',')}` which
        would raise ValueError → 500 on bad input.
        """
        df = self._multi_snapshot_df()
        import gcp.database
        monkeypatch.setattr(gcp.database, "query_to_dataframe",
                            lambda sql, params=None: df.copy())

        r = client.get("/api/options/SPY/grid/timeseries?strikes=abc")
        assert r.status_code == 400
        assert "strikes" in r.json()["detail"].lower()

    def test_partially_malformed_strikes_returns_400(self, client, monkeypatch):
        """One bad token in a comma list also raises — we don't silently
        skip bad tokens (that would mask typos)."""
        df = self._multi_snapshot_df()
        import gcp.database
        monkeypatch.setattr(gcp.database, "query_to_dataframe",
                            lambda sql, params=None: df.copy())

        r = client.get("/api/options/SPY/grid/timeseries?strikes=100,xyz,105")
        assert r.status_code == 400

    def test_empty_strikes_param_returns_400(self, client, monkeypatch):
        """`?strikes=,,` (only commas) → empty set → typed 4xx, not a
        silent fallback to top-10 defaults."""
        df = self._multi_snapshot_df()
        import gcp.database
        monkeypatch.setattr(gcp.database, "query_to_dataframe",
                            lambda sql, params=None: df.copy())

        r = client.get("/api/options/SPY/grid/timeseries?strikes=,,")
        assert r.status_code == 400


# ─── /grid/timeseries — #825 (fabricated $100 spot) + #826 (`or 0` on gamma/OI) ──


def _ts_chain(snapshot_ts: pd.Timestamp, *, gamma_values=None,
              with_quotes: bool = True) -> pd.DataFrame:
    """One REALTIME snapshot for the /grid/timeseries query shape
    (snapshot_ts, snapshot_date, expiration, strike, option_type,
    open_interest, gamma, vega) plus the quote columns `_df_to_contracts`
    reads for the parity spot. `with_quotes=False` blanks bid/ask/mark/
    last so `gamma.estimate_spot` has nothing to work with (method='none',
    price=0.0) — the #825 path. `gamma_values` overrides the per-row gamma
    (use None entries to simulate a vendor outage — the #826 path)."""
    exp = date(2026, 6, 19)
    base = [
        ("calls", 95.0, 500, 0.02, 5.50, 5.60),
        ("puts", 95.0, 800, 0.02, 0.50, 0.60),
        ("calls", 100.0, 1000, 0.05, 2.50, 2.60),
        ("puts", 100.0, 800, 0.05, 2.45, 2.55),
    ]
    rows = []
    for i, (ot, k, oi, g, bid, ask) in enumerate(base):
        if gamma_values is not None:
            g = gamma_values[i]
        rows.append({
            "snapshot_ts": snapshot_ts, "snapshot_date": snapshot_ts.date(),
            "expiration": exp, "strike": k, "option_type": ot,
            "open_interest": oi, "gamma": g, "vega": 0.1,
            "bid": bid if with_quotes else None,
            "ask": ask if with_quotes else None,
            "mark": (bid + ask) / 2 if with_quotes else None,
            "last_price": (bid + ask) / 2 if with_quotes else None,
        })
    return pd.DataFrame(rows)


class TestGridTimeseriesFallbacks:
    """GET /api/options/{ticker}/grid/timeseries — Rule 3.7 on the two
    fabricated-value sites the 2026-08-27 audit found (issues #825, #826).
    The endpoint has no frontend caller today, so these pin the contract
    before anything wires it up."""

    def test_no_spot_returns_unavailable_not_100(self, client, monkeypatch):
        """#825: when `gamma.estimate_spot` has nothing to work with it
        returns price=0.0 / method='none' (empty contract list, or a chain
        with no strikes). The endpoint used to substitute a literal $100 and
        compute GEX = net_gamma × 100² on it. Pin the exact code path by
        making the estimator report 'none'."""
        from lib import gamma as g
        ts = pd.Timestamp("2026-06-01T15:55:00")
        _install_query_router(monkeypatch, realtime_df=_ts_chain(ts, with_quotes=False))
        monkeypatch.setattr(
            grid_router.gamma, "estimate_spot",
            lambda contracts: g.SpotEstimate(price=0.0, method="none", note="test"),
        )
        r = client.get("/api/options/SPY/grid/timeseries?expiration=2026-06-19")
        assert r.status_code == 200
        body = r.json()
        assert body["data_source"] == "unavailable"
        assert body["series"] == []
        assert "spot_used" not in body or body["spot_used"] is None
        assert any("spot" in w.lower() for w in body["warnings"])
        assert "100" not in str(body.get("spot_used"))

    def test_all_gamma_missing_is_unavailable_not_zero_gex(self, client, monkeypatch):
        """#826: a vendor outage that blanks gamma on every contract must
        read as UNAVAILABLE. The inline `float(r['gamma'] or 0)` math
        produced a well-formed series of GEX == 0.0 at every strike."""
        ts = pd.Timestamp("2026-06-01T15:55:00")
        df = _ts_chain(ts, gamma_values=[None, None, None, None])
        _install_query_router(monkeypatch, realtime_df=df)
        r = client.get("/api/options/SPY/grid/timeseries?expiration=2026-06-19&strikes=95,100")
        assert r.status_code == 200
        body = r.json()
        assert body["data_source"] == "unavailable"
        assert body["series"] == []
        assert any("gamma" in w.lower() for w in body["warnings"])

    def test_partial_gamma_missing_is_flagged_degraded(self, client, monkeypatch):
        """#826: partial coverage still returns a series, but the payload
        must say the GEX is understated and by how much."""
        ts = pd.Timestamp("2026-06-01T15:55:00")
        df = _ts_chain(ts, gamma_values=[0.02, None, 0.05, 0.05])
        _install_query_router(monkeypatch, realtime_df=df)
        r = client.get("/api/options/SPY/grid/timeseries?expiration=2026-06-19&strikes=95,100")
        assert r.status_code == 200
        body = r.json()
        assert body["data_source"] == "realtime_degraded"
        assert len(body["series"]) == 2
        assert body["gamma_coverage"] == pytest.approx(0.75)
        assert any("understated" in w.lower() for w in body["warnings"])

    def test_gex_uses_lib_gamma_aggregation(self, client, monkeypatch):
        """One source of truth for math: the per-strike net gamma must equal
        lib.gamma.aggregate_by_strike on the same contracts, and the GEX
        must use the parity spot, not a constant."""
        from lib import gamma as g
        ts = pd.Timestamp("2026-06-01T15:55:00")
        df = _ts_chain(ts)
        _install_query_router(monkeypatch, realtime_df=df)
        r = client.get("/api/options/SPY/grid/timeseries?expiration=2026-06-19&strikes=95,100")
        assert r.status_code == 200
        body = r.json()
        assert body["data_source"] == "realtime"
        spot = body["spot_used"]
        assert spot is not None and 90 < spot < 110 and spot != 100.0
        contracts = grid_router._df_to_contracts(df)
        expected = {row["strike"]: row["net_gamma"] * spot * spot * g.GEX_MULTIPLIER
                    for row in g.aggregate_by_strike(contracts)}
        got = {row["strike"]: row["gex"] for row in body["series"]}
        assert got.keys() == expected.keys()
        for k in expected:
            assert got[k] == pytest.approx(expected[k])

    def test_median_strike_spot_is_labelled_not_silent(self, client, monkeypatch):
        """With no quotes and no deltas `estimate_spot` falls back to the
        chain's median strike (method='median_strike'). That is not a
        market price, so the series must be labelled degraded and say so."""
        ts = pd.Timestamp("2026-06-01T15:55:00")
        _install_query_router(monkeypatch, realtime_df=_ts_chain(ts, with_quotes=False))
        r = client.get("/api/options/SPY/grid/timeseries?expiration=2026-06-19&strikes=95,100")
        assert r.status_code == 200
        body = r.json()
        assert body["spot_method"] == "median_strike"
        assert body["data_source"] == "realtime_degraded"
        assert any("median strike" in w.lower() for w in body["warnings"])

    def test_snapshot_with_no_gamma_is_omitted_not_served_as_zero(self, client, monkeypatch):
        """Codex P1 on #1005: coverage was gated over the whole window, so a
        latest snapshot with every gamma NULL slipped through when earlier
        snapshots were populated, and aggregate_by_strike turned it into a
        real-looking collapse to GEX == 0.0 as the current point. Each
        snapshot must be gated on its own: an all-missing snapshot is
        omitted (and named), never published as zero."""
        t1 = pd.Timestamp("2026-06-01T15:50:00")
        t2 = pd.Timestamp("2026-06-01T15:55:00")
        df = pd.concat([_ts_chain(t1), _ts_chain(t2, gamma_values=[None] * 4)], ignore_index=True)
        _install_query_router(monkeypatch, realtime_df=df)
        r = client.get("/api/options/SPY/grid/timeseries?expiration=2026-06-19&strikes=95,100")
        assert r.status_code == 200
        body = r.json()
        assert body["data_source"] == "realtime_degraded"
        stamps = {row["snapshot_ts"] for row in body["series"]}
        assert stamps == {t1.isoformat()}, "the zero-coverage snapshot must be omitted"
        assert all(row["gex"] != 0.0 for row in body["series"])
        assert any(t2.isoformat() in w and "omitted" in w.lower() for w in body["warnings"])
        # Auto-ranked strikes and the reference spot must come from the latest
        # snapshot that HAS gamma, not from the omitted one.
        r2 = client.get("/api/options/SPY/grid/timeseries?expiration=2026-06-19")
        assert r2.status_code == 200
        assert r2.json()["data_source"] == "realtime_degraded"
        assert r2.json()["strikes_resolved"] == [95.0, 100.0]
