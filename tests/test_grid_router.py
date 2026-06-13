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
        assert data["data_source"] == "realtime"
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
