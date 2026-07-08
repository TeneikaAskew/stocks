"""Backtest router unit-convention tests (spec §4 items 0.2, 0.6).

The BacktestEngine writes return_pct as a raw fraction (0.003 = 0.3%).
The router must emit TRUE PERCENT units for every *_pct field so the
frontend can render `${v.toFixed(2)}%` without unit knowledge.
win_rate stays a 0-1 fraction (UI multiplies by 100).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("fastapi")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLATFORM_DIR = PROJECT_ROOT / "platform"
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

from fastapi import HTTPException
from api.routers import backtest  # noqa: E402


@pytest.fixture(scope="module")
def client():
    """Create a TestClient for the FastAPI app (no live server needed)."""
    original_cwd = os.getcwd()
    platform_dir = str(PLATFORM_DIR)
    if platform_dir not in sys.path:
        sys.path.insert(0, platform_dir)
    os.chdir(platform_dir)

    from starlette.testclient import TestClient
    from api.main import app
    with TestClient(app) as c:
        yield c

    # Restore cwd so subsequent test files aren't affected
    os.chdir(original_cwd)


def _df():
    return pd.DataFrame({
        "return_pct": [0.003, -0.002, 0.004, -0.001],  # fractions from the engine
        "entry_time": ["2026-01-02 10:00"] * 4,
    })


def test_summarize_returns_emits_percent_units():
    s = backtest._summarize_returns(_df())
    assert s["avg_return_pct"] == pytest.approx(0.1)     # mean fraction 0.001 -> 0.1%
    assert s["avg_win_pct"] == pytest.approx(0.35)       # (0.3+0.4)/2 %
    assert s["avg_loss_pct"] == pytest.approx(-0.15)     # (-0.2+-0.1)/2 %
    assert s["total_return_pct"] == pytest.approx(0.4)
    assert s["win_rate"] == pytest.approx(0.5)           # stays a fraction


def test_trade_records_emit_percent_units():
    recs = backtest._trades_to_percent_records(_df())
    assert recs[0]["return_pct"] == pytest.approx(0.3)


def test_run_pattern_accepts_specific_timestamp():
    pat = backtest._backtest_pattern("SPY", run="20260222_231417")
    assert pat == r"^backtest_SPY_20260222_231417\.csv$"


def test_validate_run_rejects_malformed():
    """_validate_run must reject malformed input with HTTPException 422."""
    # Valid format: YYYYMMDD_HHMMSS
    backtest._validate_run("20260222_231417")  # Should not raise

    # Malformed: missing the underscore
    with pytest.raises(HTTPException) as ei:
        backtest._validate_run("20260222231417")
    assert ei.value.status_code == 422

    # Malformed: bad date part
    with pytest.raises(HTTPException) as ei:
        backtest._validate_run("2026-02-22_231417")
    assert ei.value.status_code == 422

    # Malformed: missing time part
    with pytest.raises(HTTPException) as ei:
        backtest._validate_run("20260222_")
    assert ei.value.status_code == 422


def test_run_and_latest_cache_entries_do_not_collide(client):
    """Run-specific and latest cache entries never collide.

    Seed the _RESULTS_CACHE directly with both a 'latest' and a run-specific
    entry for the same ticker, then verify the endpoint returns the correct
    one for each cache_key."""
    backtest._RESULTS_CACHE.clear()
    backtest._RESULTS_CACHE["SPY:latest"] = {"marker": "latest"}
    backtest._RESULTS_CACHE["SPY:20260101_010101"] = {"marker": "run"}
    try:
        # Request without run param → should hit "SPY:latest"
        r_latest = client.get("/api/backtest/results/SPY")
        assert r_latest.status_code == 200
        assert r_latest.json()["marker"] == "latest"

        # Request with run param → should hit "SPY:20260101_010101"
        r_run = client.get("/api/backtest/results/SPY", params={"run": "20260101_010101"})
        assert r_run.status_code == 200
        assert r_run.json()["marker"] == "run"

        # Bogus run param → should reject with 422
        r_bogus = client.get("/api/backtest/results/SPY", params={"run": "bogus"})
        assert r_bogus.status_code == 422
    finally:
        backtest._RESULTS_CACHE.clear()
