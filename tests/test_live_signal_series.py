"""POST /api/live/signal-series — server-side per-bar signal fires (spec 0.12).

Replaces the client-side TS voter so the 5-condition logic exists in
exactly one place (lib/). Uses a synthetic ramp so at least the shape
contract is enforced without depending on signal-firing specifics.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLATFORM_DIR = PROJECT_ROOT / "platform"
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))


@pytest.fixture(scope="module")
def client():
    """Create a TestClient for the FastAPI app (no live server needed).

    Mirrors tests/test_backtest_router_units.py's import pattern: chdir
    into platform/ so the app's relative asset paths resolve, then import
    api.main once sys.path has the platform dir.
    """
    original_cwd = os.getcwd()
    platform_dir = str(PLATFORM_DIR)
    if platform_dir not in sys.path:
        sys.path.insert(0, platform_dir)
    os.chdir(platform_dir)

    from starlette.testclient import TestClient
    from api.main import app
    with TestClient(app) as c:
        yield c

    os.chdir(original_cwd)


def _bars(n=40):
    out = []
    px = 100.0
    for i in range(n):
        px *= 1.001
        out.append({
            "time": f"2026-07-02 10:{i:02d}:00",
            "open": px / 1.001, "high": px * 1.001, "low": px * 0.999,
            "close": px, "volume": 10_000 + i,
        })
    return out


def test_signal_series_contract(client):
    r = client.post("/api/live/signal-series", json={"bars": _bars()})
    assert r.status_code == 200
    body = r.json()
    assert "fires" in body and isinstance(body["fires"], list)
    for f in body["fires"]:
        assert set(f) >= {"time", "direction"}
        assert f["direction"] in ("CALL", "PUT")


def test_signal_series_rejects_short_series(client):
    r = client.post("/api/live/signal-series", json={"bars": _bars(5)})
    assert r.status_code == 422  # need >= 14 bars for RSI; loud, not empty-success


def _epoch_bars(n=40, base=1751882400):
    """Same synthetic ramp as _bars(), but times are epoch-second digit
    strings — what the frontend's /api/market unix-timestamp feed sends,
    as opposed to the naive-ET datetime strings the production fetch
    path sends."""
    out = []
    px = 100.0
    for i in range(n):
        px *= 1.001
        out.append({
            "time": str(base + i * 60),
            "open": px / 1.001, "high": px * 1.001, "low": px * 0.999,
            "close": px, "volume": 10_000 + i,
        })
    return out


def test_signal_series_accepts_epoch_second_times(client):
    """Epoch-second digit-string bar times (frontend /api/market feed) must
    not 500 inside pd.to_datetime(...) in lib.indicators._add_vwap — see
    CRITICAL-1. Every fire's echoed time must be one of the REQUEST's
    original (unnormalized) time strings, with an in-range bar_index."""
    bars = _epoch_bars()
    request_times = {b["time"] for b in bars}
    r = client.post("/api/live/signal-series", json={"bars": bars})
    assert r.status_code == 200
    body = r.json()
    assert "fires" in body and isinstance(body["fires"], list)
    for f in body["fires"]:
        assert set(f) >= {"time", "direction", "bar_index"}
        assert f["time"] in request_times
        assert isinstance(f["bar_index"], int)
        assert 0 <= f["bar_index"] < len(bars)


def test_indicators_endpoint_vwap_sessionizes_epoch_times(client):
    """CRITICAL-2: epoch-second bar times must not each become their own
    single-bar VWAP "session" (lib.indicators._add_vwap groups by calendar
    date). With 20 epoch-string bars all in the same ET calendar date and
    strictly rising prices, a correctly-sessionized cumulative VWAP lags
    the last bar's typical price. A per-bar reset would instead make VWAP
    equal the last bar's own typical price exactly."""
    bars = _epoch_bars(n=20)
    r = client.post("/api/live/indicators", json={"bars": bars})
    assert r.status_code == 200
    body = r.json()
    vwap = body["indicators"]["vwap"]
    assert vwap is not None

    last = bars[-1]
    last_typical = (last["high"] + last["low"] + last["close"]) / 3
    assert abs(vwap - last_typical) > 1e-6
