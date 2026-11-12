"""/api/config/market-hours on the shared NYSE calendar (FEAT-DATA-001, Task 4).

``holidays_2026`` is kept, filled from the module, for solyra's replay picker
until Spec C moves it to ``holidays``. ``holidays`` covers the current and
next Eastern year and ``early_closes`` lists that window's half days with
their Eastern close. Every case freezes the clock (``eastern_now``, which
``market_today`` reads), so none depends on the real date (spec, Testing
item 7). The expected lists are literals, not ``holidays_in``, so a wrong
calendar fails here even when the module's own suite passes.
"""
import os
import sys
from datetime import datetime
from pathlib import Path

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
    from api.routers import live
finally:
    os.chdir(_original_cwd)

from fastapi.testclient import TestClient

from lib import eastern_time
from lib.eastern_time import ET, UTC, holidays_in

HOLIDAYS_2026 = [
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
]
HOLIDAYS_2027 = [
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
]


def _freeze(monkeypatch, instant: datetime) -> None:
    """Freeze the Eastern clock the market-hours and live-status routes read."""
    frozen = instant.astimezone(ET)
    monkeypatch.setattr(eastern_time, "eastern_now", lambda: frozen)
    monkeypatch.setattr(live, "eastern_now", lambda: frozen)


def _market_hours(monkeypatch, instant: datetime) -> dict:
    _freeze(monkeypatch, instant)
    with TestClient(main.app) as client:
        resp = client.get("/api/config/market-hours")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_market_hours_payload(monkeypatch):
    body = _market_hours(monkeypatch, datetime(2026, 10, 19, 12, 0, tzinfo=ET))

    assert body["holidays_2026"] == HOLIDAYS_2026
    # Current and next year; federal-only days (2026-10-12, 2026-11-11) and
    # Black Friday, a half-day session, are absent.
    assert body["holidays"] == HOLIDAYS_2026 + HOLIDAYS_2027
    assert "2026-11-27" not in body["holidays_2026"]
    assert body["early_closes"] == [
        {"date": "2026-11-27", "close": "13:00"},
        {"date": "2026-12-24", "close": "13:00"},
        {"date": "2027-11-26", "close": "13:00"},
    ]
    # The static windows are unchanged.
    assert body["timezone"] == "America/New_York"
    assert body["regular"] == {"open": "09:30", "close": "16:00"}
    assert body["pre_market"] == {"open": "04:00", "close": "09:30"}
    assert body["after_hours"] == {"open": "16:00", "close": "20:00"}


def test_market_hours_year_rollover(monkeypatch):
    # 23:59 ET on 2026-12-31 is already 2027 in UTC; the window follows the
    # Eastern date.
    body = _market_hours(monkeypatch, datetime(2026, 12, 31, 23, 59, tzinfo=ET))
    assert body["holidays"] == [d.isoformat() for d in holidays_in(2026) + holidays_in(2027)]

    body = _market_hours(monkeypatch, datetime(2027, 1, 1, 5, 1, tzinfo=UTC))  # 00:01 ET
    assert body["holidays"] == [d.isoformat() for d in holidays_in(2027) + holidays_in(2028)]
    assert [e["date"] for e in body["early_closes"]] == ["2027-11-26", "2028-07-03", "2028-11-24"]
    # holidays_2026 stays 2026 whatever the date, until Spec C removes it.
    assert body["holidays_2026"] == HOLIDAYS_2026


def test_black_friday_close_via_api(monkeypatch):
    _freeze(monkeypatch, datetime(2026, 11, 27, 13, 30, tzinfo=ET))
    with TestClient(main.app) as client:
        resp = client.get("/api/live/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_open"] is False
    assert body["session"] == "after-hours"
    assert body["next_open"] == "2026-11-30 09:30:00"
    assert body["current_time_et"] == "13:30:00"
