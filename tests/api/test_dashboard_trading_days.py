"""Dashboard staleness counted in NYSE sessions (FEAT-DATA-001, Task 5).

``_trading_days_between`` counts sessions strictly between its two dates from
the shared calendar, so holidays of any year are skipped and its old silent
empty-holiday-set fallback is gone. When that count fails, the brief reports
``stale_days: null`` instead of ``0``, which read as fresh data.
"""
import logging
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("fastapi")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PLATFORM_DIR = PROJECT_ROOT / "platform"
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

_original_cwd = os.getcwd()
os.chdir(str(PLATFORM_DIR))
try:
    from api import main
    from api.routers import dashboard
finally:
    os.chdir(_original_cwd)

from fastapi.testclient import TestClient


def test_thursday_to_monday_counts_friday_only():
    assert dashboard._trading_days_between(date(2026, 10, 15), date(2026, 10, 19)) == 1


def test_juneteenth_is_skipped():
    # Thursday 2026-06-18 to Monday 2026-06-22: Friday is Juneteenth.
    assert dashboard._trading_days_between(date(2026, 6, 18), date(2026, 6, 22)) == 0


def test_same_session_day_is_zero_not_minus_one():
    assert dashboard._trading_days_between(date(2026, 10, 19), date(2026, 10, 19)) == 0


def test_end_before_start_is_zero():
    assert dashboard._trading_days_between(date(2026, 10, 19), date(2026, 10, 16)) == 0


def test_2027_holiday_is_skipped():
    # Friday 2027-01-15 to Wednesday 2027-01-20: Monday is MLK Day, so only
    # Tuesday 2027-01-19 lies strictly between.
    assert dashboard._trading_days_between(date(2027, 1, 15), date(2027, 1, 20)) == 1


def test_end_on_a_holiday_still_excludes_only_end():
    # Thursday 2026-06-18 to Juneteenth: nothing strictly between.
    assert dashboard._trading_days_between(date(2026, 6, 18), date(2026, 6, 19)) == 0
    # Wednesday 2026-06-17 to Juneteenth: Thursday only.
    assert dashboard._trading_days_between(date(2026, 6, 17), date(2026, 6, 19)) == 1


def _brief_query(sql, params=None):
    if "premarket_analysis" in sql:
        return pd.DataFrame()
    return pd.DataFrame([{
        "date": "2026-10-15", "close": 580.0, "rsi_14": 55.0, "ema_9": 579.0,
        "ema_20": 575.0, "sma_200": 540.0, "macd": 1.2, "bb_upper": 590.0,
        "bb_lower": 570.0, "atr_14": 6.1, "rvol": 1.1, "strat_candle": "2U",
        "strat_combo": None, "strat_setup": False, "ftfc_score": 0.5,
        "ftfc_direction": "bullish", "consecutive_up": 2, "consecutive_down": 0,
        "price_vs_ema9": 0.001, "price_vs_ema20": 0.008,
    }])


def test_brief_stale_days_null_on_calendar_failure(monkeypatch, caplog):
    def _calendar_down(start, end):
        raise RuntimeError("NYSE calendar unavailable in test")

    async def _no_overlay(_ticker, _daily):
        return {}

    monkeypatch.setattr(dashboard, "_CLOUD_SQL", True)
    monkeypatch.setattr(dashboard, "_query_fn", _brief_query)
    monkeypatch.setattr(dashboard, "_apply_live_overlay", _no_overlay)
    monkeypatch.setattr(dashboard, "_trading_days_between", _calendar_down)

    with caplog.at_level(logging.ERROR), TestClient(main.app) as client:
        resp = client.get("/api/dashboard/brief/SPY")

    assert resp.status_code == 200, resp.text
    daily = resp.json()["daily_indicators"]
    assert daily["date"] == "2026-10-15"
    assert "stale_days" in daily
    assert daily["stale_days"] is None  # not 0, which reads as fresh
    assert any(
        r.exc_info is not None and "NYSE calendar unavailable in test" in str(r.exc_info[1])
        for r in caplog.records
    ), [r.getMessage() for r in caplog.records]


def test_brief_stale_days_counts_sessions(monkeypatch):
    async def _no_overlay(_ticker, _daily):
        return {}

    monkeypatch.setattr(dashboard, "_CLOUD_SQL", True)
    monkeypatch.setattr(dashboard, "_query_fn", _brief_query)
    monkeypatch.setattr(dashboard, "_apply_live_overlay", _no_overlay)

    with TestClient(main.app) as client:
        resp = client.get("/api/dashboard/brief/SPY", params={"date": "2026-10-19"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["daily_indicators"]["stale_days"] == 1
