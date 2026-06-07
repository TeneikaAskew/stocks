"""Tests for platform.api.routers.strat_history — /api/strat/history/{ticker}.

TestClient-based; the data load (compute_strat_history) is monkeypatched so
the routing / validation / status-code contract is tested hermetically.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "platform" / "api"))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import strat_history as sh
except Exception as exc:  # pragma: no cover
    pytest.skip(f"strat_history router unavailable: {exc}", allow_module_level=True)


@pytest.fixture
def client(monkeypatch):
    def _fake(ticker, timeframes=None, lookback=20):
        if ticker == "NODATA":
            return {"available": False, "ticker": ticker, "reason": "insufficient daily bars"}
        return {
            "available": True, "ticker": ticker,
            "timeframes": {tf: {"available": True,
                                "history": [{"period": "2026-06-05", "candle": "2U",
                                             "combo": "22_bull_continuation"}],
                                "current": {"candle": "2U"},
                                "upcoming": {"trigger_high": 10.0, "trigger_low": 9.0,
                                             "mid_trigger": 9.5,
                                             "break_up": "2U continuation",
                                             "break_down": "2D reversal"}}
                           for tf in (timeframes or ["1d", "1w", "1mo", "1q"])},
        }
    monkeypatch.setattr(sh, "compute_strat_history", _fake)
    app = FastAPI()
    app.include_router(sh.router)
    return TestClient(app)


def test_happy_path_default_timeframes(client):
    r = client.get("/api/strat/history/AAPL")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True and body["ticker"] == "AAPL"
    assert set(body["timeframes"]) == {"1d", "1w", "1mo", "1q"}
    up = body["timeframes"]["1d"]["upcoming"]
    assert up["trigger_high"] == 10.0 and up["break_up"].startswith("2U")


def test_timeframe_subset(client):
    r = client.get("/api/strat/history/SPY?timeframes=1d,1w")
    assert r.status_code == 200
    assert set(r.json()["timeframes"]) == {"1d", "1w"}


def test_lowercase_ticker_normalized(client):
    assert client.get("/api/strat/history/aapl").json()["ticker"] == "AAPL"


def test_invalid_ticker_400(client):
    assert client.get("/api/strat/history/!!!").status_code == 400


def test_invalid_timeframe_400(client):
    assert client.get("/api/strat/history/SPY?timeframes=1d,9z").status_code == 400


def test_lookback_bounds_422(client):
    assert client.get("/api/strat/history/SPY?lookback=0").status_code == 422
    assert client.get("/api/strat/history/SPY?lookback=99999").status_code == 422


def test_unavailable_404(client):
    assert client.get("/api/strat/history/NODATA").status_code == 404
