"""Unit tests for the live AlphaVantage options proxy endpoint
(`GET /api/options/live/{ticker}/{date_str}`) that replaces the
decommissioned Cloudflare Worker.

These tests exercise the endpoint via FastAPI's TestClient with httpx
calls patched at the AsyncClient level — no network, no Cloud SQL.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "platform" / "api"))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import options as options_router
except ModuleNotFoundError as exc:  # pragma: no cover - import-time guard
    pytest.skip(f"options router unavailable: {exc}", allow_module_level=True)


@pytest.fixture
def client(monkeypatch):
    """A clean FastAPI app wired only to the options router, with the AV
    API key forced on so the 503 short-circuit doesn't fire by default."""
    monkeypatch.setattr(options_router, "_AV_API_KEY", "test-key")
    options_router._LIVE_CACHE.clear()
    app = FastAPI()
    app.include_router(options_router.router)
    return TestClient(app)


# ── happy path ──────────────────────────────────────────────────────────


_FAKE_AV_OK = {
    "endpoint": "Historical Options",
    "message": "success",
    "data": [
        {
            "contractID": "SPY250117C00500000",
            "symbol": "SPY",
            "type": "call",
            "strike": "500.00",
            "expiration": "2025-01-17",
            "bid": "12.50",
            "ask": "12.60",
            "mark": "12.55",
            "last": "12.55",
            "volume": "1500",
            "open_interest": "8000",
            "implied_volatility": "0.18",
            "delta": "0.55",
            "gamma": "0.04",
            "theta": "-0.08",
            "vega": "0.12",
            "rho": "0.05",
        },
        {
            "contractID": "SPY250117P00500000",
            "symbol": "SPY",
            "type": "put",
            "strike": "500.00",
            "expiration": "2025-01-17",
            "bid": "10.10",
            "ask": "10.20",
            "mark": "10.15",
            "last": "10.15",
            "volume": "900",
            "open_interest": "6500",
            "implied_volatility": "0.19",
            "delta": "-0.45",
            "gamma": "0.04",
            "theta": "-0.07",
            "vega": "0.12",
            "rho": "-0.04",
        },
    ],
}


class _FakeResponse:
    """Minimal stand-in for httpx.Response; only the bits the router uses."""

    def __init__(self, status_code: int = 200, body: dict | None = None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("err", request=None, response=None)


def _patch_av(monkeypatch, response: _FakeResponse):
    """Patch httpx.AsyncClient so the router's `await client.get(...)`
    returns our stub instead of hitting the network."""
    import httpx

    class _StubClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **kw):
            return response

    monkeypatch.setattr(httpx, "AsyncClient", _StubClient)


def test_happy_path_returns_normalized_chain(client, monkeypatch):
    _patch_av(monkeypatch, _FakeResponse(200, _FAKE_AV_OK))

    r = client.get("/api/options/live/SPY/2025-01-15")
    assert r.status_code == 200
    body = r.json()

    assert body["ticker"] == "SPY"
    assert body["date"] == "2025-01-15"
    assert len(body["options"]) == 2
    assert body["metadata"]["source"] == "alphavantage_live"
    assert body["metadata"]["row_count"] == 2
    assert body["cached"] is False

    # Strings → floats; key names match the Cloud SQL endpoint contract.
    call = next(o for o in body["options"] if o["type"] == "call")
    assert call["strike"] == 500.0
    assert call["last"] == 12.55
    assert call["gamma"] == 0.04
    assert call["open_interest"] == 8000  # int not str

    # Cache-Control header is set so a CDN / browser can re-use the response.
    assert "max-age=300" in r.headers.get("cache-control", "")


def test_response_shape_matches_cloud_sql_endpoint_keys(client, monkeypatch):
    """Lock the contract: live and Cloud SQL endpoints must emit the same
    contract keys so the React page handles them with one code path."""
    _patch_av(monkeypatch, _FakeResponse(200, _FAKE_AV_OK))
    r = client.get("/api/options/live/SPY/2025-01-15")
    contract = r.json()["options"][0]
    expected_keys = {
        "contract_symbol", "expiration", "strike", "type",
        "bid", "ask", "mark", "last", "volume", "open_interest",
        "implied_volatility", "delta", "gamma", "theta", "vega", "rho",
    }
    assert set(contract.keys()) == expected_keys


def test_second_call_is_cache_hit(client, monkeypatch):
    _patch_av(monkeypatch, _FakeResponse(200, _FAKE_AV_OK))
    r1 = client.get("/api/options/live/SPY/2025-01-15")
    assert r1.json()["cached"] is False

    # Replace the stub with one that would 500 — but we shouldn't hit it.
    _patch_av(monkeypatch, _FakeResponse(500, {}))
    r2 = client.get("/api/options/live/SPY/2025-01-15")
    assert r2.status_code == 200
    assert r2.json()["cached"] is True


# ── error mapping (mirrors the old Cloudflare Worker contract) ───────────


def test_missing_api_key_returns_503(client, monkeypatch):
    monkeypatch.setattr(options_router, "_AV_API_KEY", "")
    r = client.get("/api/options/live/SPY/2025-01-15")
    assert r.status_code == 503
    assert "AlphaVantage API key" in r.json()["detail"]


def test_invalid_ticker_returns_400(client):
    r = client.get("/api/options/live/AAPL/2025-01-15")
    assert r.status_code == 400


def test_invalid_date_returns_400(client):
    r = client.get("/api/options/live/SPY/2025-1-15")  # missing zero-pad
    assert r.status_code == 400


def test_av_rate_limit_note_returns_429(client, monkeypatch):
    _patch_av(monkeypatch, _FakeResponse(200, {"Note": "Thank you for using AV"}))
    r = client.get("/api/options/live/SPY/2025-01-15")
    assert r.status_code == 429


def test_av_information_envelope_returns_429(client, monkeypatch):
    _patch_av(monkeypatch, _FakeResponse(200, {"Information": "limit reached"}))
    r = client.get("/api/options/live/SPY/2025-01-15")
    assert r.status_code == 429


def test_av_error_message_returns_400(client, monkeypatch):
    _patch_av(monkeypatch, _FakeResponse(200, {"Error Message": "bad date"}))
    r = client.get("/api/options/live/SPY/2025-01-15")
    assert r.status_code == 400


def test_empty_av_data_returns_404(client, monkeypatch):
    _patch_av(monkeypatch, _FakeResponse(200, {"data": []}))
    r = client.get("/api/options/live/SPY/2099-01-15")
    assert r.status_code == 404


def test_timeout_returns_503(client, monkeypatch):
    import httpx

    class _TimeoutClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **kw):
            raise httpx.TimeoutException("slow")

    monkeypatch.setattr(httpx, "AsyncClient", _TimeoutClient)
    r = client.get("/api/options/live/SPY/2025-01-15")
    assert r.status_code == 503
    assert "timed out" in r.json()["detail"]


# ── helper unit tests ───────────────────────────────────────────────────


class TestAvToContracts:
    def test_drops_rows_missing_core_fields(self):
        rows = [
            {"type": "call", "strike": "100", "expiration": "2025-01-15"},
            {"type": "call", "strike": None, "expiration": "2025-01-15"},  # drop
            {"type": "", "strike": "100", "expiration": "2025-01-15"},     # drop
            {"type": "put", "strike": "100", "expiration": ""},            # drop
        ]
        out = options_router._av_to_contracts(rows)
        assert len(out) == 1

    def test_normalizes_plural_types(self):
        rows = [
            {"type": "calls", "strike": "100", "expiration": "2025-01-15"},
            {"type": "PUTS", "strike": "100", "expiration": "2025-01-15"},
        ]
        out = options_router._av_to_contracts(rows)
        assert {o["type"] for o in out} == {"call", "put"}

    def test_string_numerics_become_floats(self):
        rows = [{
            "type": "call", "strike": "123.45", "expiration": "2025-01-15",
            "gamma": "0.05", "open_interest": "1000",
        }]
        out = options_router._av_to_contracts(rows)
        assert out[0]["strike"] == 123.45
        assert out[0]["gamma"] == 0.05
        assert out[0]["open_interest"] == 1000

    def test_empty_string_becomes_none(self):
        rows = [{
            "type": "call", "strike": "100", "expiration": "2025-01-15",
            "delta": "", "vega": None,
        }]
        out = options_router._av_to_contracts(rows)
        assert out[0]["delta"] is None
        assert out[0]["vega"] is None

    def test_empty_input(self):
        assert options_router._av_to_contracts([]) == []

    # ── Rule 3.7 happy-path companions ───────────────────────────────────
    # These exercise the REAL parser against a realistically-shaped AV row
    # and assert the financial-data invariants from CLAUDE.md §3.7:
    # a missing/blank price or Greek must surface as None, NEVER a silent 0.

    def test_full_realistic_av_row_parses_all_fields(self):
        """A complete, realistically-shaped AlphaVantage HISTORICAL_OPTIONS
        row (all values arrive as strings) must round-trip every field through
        the production string→float/int coercion with the exact observed
        value — not a fabricated number fed through a mock."""
        rows = [{
            "contractID": "SPY250117P00480000",
            "symbol": "SPY",
            "type": "put",
            "strike": "480.00",
            "expiration": "2025-01-17",
            "bid": "7.35",
            "ask": "7.45",
            "mark": "7.40",
            "last": "7.38",
            "volume": "2750",
            "open_interest": "13219",
            "implied_volatility": "0.2034",
            "delta": "-0.3812",
            "gamma": "0.0061",
            "theta": "-0.1149",
            "vega": "0.4377",
            "rho": "-0.0732",
        }]
        out = options_router._av_to_contracts(rows)
        assert len(out) == 1
        c = out[0]
        # String numerics coerced to real floats/ints.
        assert c["strike"] == 480.0 and isinstance(c["strike"], float)
        assert c["bid"] == 7.35
        assert c["ask"] == 7.45
        assert c["mark"] == 7.40
        assert c["last"] == 7.38
        assert c["volume"] == 2750 and isinstance(c["volume"], int)
        assert c["open_interest"] == 13219 and isinstance(c["open_interest"], int)
        assert c["implied_volatility"] == 0.2034
        # Put delta in the valid [-1, 0] range (mathematical invariant).
        assert -1.0 <= c["delta"] <= 0.0
        assert c["delta"] == -0.3812
        assert c["gamma"] == 0.0061  # gamma is non-negative for long options
        assert c["gamma"] >= 0.0
        assert c["theta"] == -0.1149  # long-option theta is negative
        assert c["vega"] == 0.4377
        assert c["rho"] == -0.0732
        assert c["type"] == "put"

    def test_missing_numeric_fields_become_none_not_zero(self):
        """CLAUDE.md §3.7: when AV omits price/Greek keys entirely, the
        parser must emit None for each — a silent 0 would be
        indistinguishable from a real zero quote and would poison every
        downstream GEX/Greeks computation."""
        rows = [{
            "contractID": "IWM250117C00200000",
            "symbol": "IWM",
            "type": "call",
            "strike": "200.00",
            "expiration": "2025-01-17",
            "bid": "1.10",
            "ask": "1.20",
            # mark, last, volume, open_interest, IV and ALL Greeks absent.
        }]
        out = options_router._av_to_contracts(rows)
        assert len(out) == 1
        c = out[0]
        # Core fields still present.
        assert c["strike"] == 200.0
        assert c["bid"] == 1.10
        # Every absent numeric/Greek field is None — NOT 0 / 0.0.
        for field in ("mark", "last", "volume", "open_interest",
                      "implied_volatility", "delta", "gamma", "theta",
                      "vega", "rho"):
            assert c[field] is None, f"{field} should be None when missing, got {c[field]!r}"

    def test_blank_and_nan_string_greeks_become_none_not_zero(self):
        """AV sometimes returns empty strings or the literal 'nan' for Greeks
        it couldn't compute. Those must map to None, never 0 (§3.7)."""
        rows = [{
            "type": "call", "strike": "100", "expiration": "2025-01-15",
            "bid": "2.00", "ask": "2.10",
            "delta": "", "gamma": "nan", "theta": "NaN", "vega": None,
            "implied_volatility": "",
        }]
        out = options_router._av_to_contracts(rows)
        assert len(out) == 1
        c = out[0]
        for field in ("delta", "gamma", "theta", "vega", "implied_volatility"):
            assert c[field] is None, f"{field} should be None, got {c[field]!r}"
