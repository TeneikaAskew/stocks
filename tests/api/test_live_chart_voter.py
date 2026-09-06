"""/api/live/indicators exposes the July-6 chart voter (additively).

Task 2 of the July-6 Charts-UI restoration: lib/chart_voter.py's
evaluate_chart_voter (Task 1) is surfaced as an additive "chart_voter"
key on POST /api/live/indicators. The existing "indicators" and
"signals" keys must remain byte-identical to before.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PLATFORM_DIR = PROJECT_ROOT / "platform"
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))


@pytest.fixture(scope="module")
def client():
    """Create a TestClient for the FastAPI app (no live server needed).

    Mirrors tests/api/test_live_signal_series.py's import pattern: chdir
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


def _bars(closes):
    return [
        {"time": str(1_700_000_000 + i * 60), "open": c - 0.05,
         "high": c + 0.01, "low": c - 0.06, "close": c, "volume": 100_000}
        for i, c in enumerate(closes)
    ]


def test_indicators_response_includes_chart_voter(client):
    closes = [220.0 + i * 0.05 for i in range(30)]  # steady up-run
    resp = client.post("/api/live/indicators", json={"bars": _bars(closes)})
    assert resp.status_code == 200
    body = resp.json()
    assert "signals" in body                      # legacy key untouched
    cv = body["chart_voter"]
    assert cv["call"]["total_count"] == 5
    labels = [c["label"] for c in cv["call"]["conditions"]]
    assert labels[0] == "3 consecutive up moves"
    assert cv["call"]["conditions"][0]["met"] is True   # 3 rising closes
    assert isinstance(cv["firing"], (str, type(None)))


def test_empty_bars_returns_empty_voter(client):
    resp = client.post("/api/live/indicators", json={"bars": []})
    assert resp.status_code == 200
    cv = resp.json()["chart_voter"]
    assert cv["firing"] is None
    assert cv["call"]["met_count"] == 0
