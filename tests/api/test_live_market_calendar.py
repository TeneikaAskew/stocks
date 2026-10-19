"""Live router market status on the shared NYSE calendar (FEAT-DATA-001, Task 3).

``_is_market_open`` and ``_next_open_et`` read ``lib.eastern_time`` instead of
the removed 2026-only ``MARKET_HOLIDAYS_2026`` set, so every year's closures
are known, Juneteenth is closed, and Black Friday is a session that closes at
13:00 ET. The clock is passed in, so each case is frozen and never depends on
the real date (spec, Testing item 7).

The last two tests cover the API lifespan warm-up (#1542 item 2): the first
calendar call builds a schedule from 2000 onward, and async handlers read the
calendar on the event loop, so without the warm-up the first request after a
cold start would stall every other request for the length of that build.
"""
import asyncio
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PLATFORM_DIR = PROJECT_ROOT / "platform"
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

_original_cwd = os.getcwd()
os.chdir(str(PLATFORM_DIR))
try:
    from api import main
    from api.routers import dashboard, live
finally:
    os.chdir(_original_cwd)

from fastapi.testclient import TestClient

from lib import eastern_time
from lib.eastern_time import ET


def _et(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


# -- _is_market_open ------------------------------------------------------------


def test_juneteenth_is_closed():
    # Missing from the old hard-coded set, so it read as a regular session.
    assert live._is_market_open(_et(2026, 6, 19, 11)) == (False, "closed")


def test_black_friday_closes_at_13_et():
    # The old set listed it as a holiday ("treated as closed"); it is a
    # half day closing at 13:00 ET.
    assert live._is_market_open(_et(2026, 11, 27, 12, 59)) == (True, "regular")
    assert live._is_market_open(_et(2026, 11, 27, 13, 30)) == (False, "after-hours")


def test_2027_holiday_is_closed():
    # MLK Day 2027: the old set held 2026 only.
    assert live._is_market_open(_et(2027, 1, 18, 11)) == (False, "closed")


def test_regular_hours_unchanged():
    assert live._is_market_open(_et(2026, 10, 19, 10)) == (True, "regular")
    assert live._is_market_open(_et(2026, 10, 19, 8)) == (False, "pre-market")
    assert live._is_market_open(_et(2026, 10, 19, 17)) == (False, "after-hours")


# -- _next_open_et --------------------------------------------------------------


def test_next_open_same_day_premarket():
    assert live._next_open_et(_et(2026, 10, 19, 8)) == "2026-10-19 09:30:00"


def test_next_open_skips_holiday_monday():
    assert live._next_open_et(_et(2027, 1, 18, 8)) == "2027-01-19 09:30:00"


def test_next_open_after_early_close():
    # #1542 item 3: after Black Friday's 13:00 close the next open is Monday.
    assert live._next_open_et(_et(2026, 11, 27, 13, 30)) == "2026-11-30 09:30:00"


def test_next_open_after_friday_close():
    assert live._next_open_et(_et(2026, 10, 16, 17)) == "2026-10-19 09:30:00"


def test_next_open_is_none_while_open():
    assert live._next_open_et(_et(2026, 10, 19, 10)) is None


# -- lifespan warm-up -----------------------------------------------------------


def _brief_query_factory(daily_queried):
    """Fake Cloud SQL for /api/dashboard/brief: no premarket row, one daily row.

    Sets *daily_queried* when the daily query runs, the handler's last await
    before it reads the calendar.
    """
    def _query(sql, params=None):
        if "premarket_analysis" in sql:
            return pd.DataFrame()
        daily_queried.set()
        return pd.DataFrame([{
            "date": "2026-10-15", "close": 580.0, "rsi_14": 55.0, "ema_9": 579.0,
            "ema_20": 575.0, "sma_200": 540.0, "macd": 1.2, "bb_upper": 590.0,
            "bb_lower": 570.0, "atr_14": 6.1, "rvol": 1.1, "strat_candle": "2U",
            "strat_combo": None, "strat_setup": False, "ftfc_score": 0.5,
            "ftfc_direction": "bullish", "consecutive_up": 2, "consecutive_down": 0,
            "price_vs_ema9": 0.001, "price_vs_ema20": 0.008,
        }])
    return _query


@pytest.fixture
def cold_calendar(monkeypatch):
    """Drop the cached schedule; drop it again afterwards so no patched build leaks."""
    eastern_time._reset_session_cache()
    yield
    monkeypatch.undo()
    eastern_time._reset_session_cache()


def test_cold_calendar_does_not_stall_event_loop(monkeypatch, cold_calendar):
    """#1542 item 2. The schedule build is slowed to 1 s. The app is started
    with TestClient as a context manager, which runs the lifespan; then the
    dashboard brief (an async handler that reads the calendar on the event
    loop) and /api/health run concurrently on one loop.

    /api/health is sent once the brief has run its daily query, its last await
    before the calendar read, and its completion is timed from the common
    start: a build on the loop holds it past 1 s. The test also records, for
    every build, whether it ran on a thread with a running event loop, which
    does not depend on scheduling order at all.
    """
    real_build = eastern_time._build_session_cache
    builds = []  # True per build that ran on an event-loop thread

    def slow_build(first, last):
        try:
            asyncio.get_running_loop()
            builds.append(True)
        except RuntimeError:
            builds.append(False)
        time.sleep(1.0)
        return real_build(first, last)

    daily_queried = threading.Event()
    monkeypatch.setattr(eastern_time, "_build_session_cache", slow_build)
    monkeypatch.setattr(dashboard, "_CLOUD_SQL", True)
    monkeypatch.setattr(dashboard, "_query_fn", _brief_query_factory(daily_queried))

    async def _no_overlay(_ticker, _daily):
        return {}

    monkeypatch.setattr(dashboard, "_apply_live_overlay", _no_overlay)

    async def _concurrent():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            t0 = time.perf_counter()
            brief_task = asyncio.create_task(client.get("/api/dashboard/brief/SPY"))
            while not daily_queried.is_set():
                await asyncio.sleep(0.001)
            health = await client.get("/api/health")
            health_done = time.perf_counter() - t0
            brief = await brief_task
            return health, health_done, brief

    with TestClient(main.app):
        health, health_done, brief = asyncio.run(_concurrent())

    assert health.status_code == 200
    assert brief.status_code == 200
    # The brief did read the calendar: stale_days is a session count.
    assert brief.json()["daily_indicators"]["stale_days"] == 1
    assert health_done < 0.3, f"/api/health took {health_done:.3f}s behind a cold calendar"
    assert builds == [False], f"schedule builds (True = on the event loop): {builds}"


def test_warmup_failure_is_logged_and_raised_by_first_request(monkeypatch, cold_calendar, caplog):
    """A failed warm-up does not stop the app (so /api/health still answers),
    is logged, and is not swallowed: nothing was cached, so the first request
    that reads the calendar rebuilds it and raises the same error."""

    def failing_build(first, last):
        raise RuntimeError("calendar build failed in test")

    monkeypatch.setattr(eastern_time, "_build_session_cache", failing_build)

    with caplog.at_level("ERROR"), TestClient(main.app) as client:
        assert client.get("/api/health").status_code == 200
        with pytest.raises(RuntimeError, match="calendar build failed in test"):
            client.get("/api/live/status")

    assert any(
        "calendar" in r.getMessage().lower() and r.exc_info is not None
        for r in caplog.records
    ), [r.getMessage() for r in caplog.records]
