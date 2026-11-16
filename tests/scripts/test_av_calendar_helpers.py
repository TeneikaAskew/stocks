"""The AlphaVantage download scripts' calendar helpers delegate to lib.eastern_time.

Both scripts used to keep a module-level `pandas_market_calendars` import and
answered weekday-only when it, or any lookup, failed (CLAUDE.md 3.7). They are
thin calls to the shared NYSE calendar now, so a missing library raises.
Real library, no calendar mocks except the unimportable case.
"""
from __future__ import annotations

import sys
from datetime import date

import pytest

pytest.importorskip("pandas_market_calendars")

from lib import eastern_time


@pytest.fixture
def options_script(monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    from scripts import fetch_alphavantage_options
    return fetch_alphavantage_options


@pytest.fixture
def intraday_script(monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    from scripts import fetch_alphavantage_intraday
    return fetch_alphavantage_intraday


@pytest.fixture
def no_calendar_library(monkeypatch):
    eastern_time._reset_session_cache()
    monkeypatch.setitem(sys.modules, "pandas_market_calendars", None)
    yield
    monkeypatch.undo()
    eastern_time._reset_session_cache()


def test_is_trading_day_false_on_juneteenth(options_script):
    assert options_script.is_trading_day(date(2026, 6, 19)) is False


def test_is_trading_day_true_on_an_ordinary_weekday(options_script):
    assert options_script.is_trading_day(date(2026, 6, 18)) is True


def test_is_trading_day_false_on_a_weekend(options_script):
    assert options_script.is_trading_day(date(2026, 6, 20)) is False


def test_get_trading_days_skips_juneteenth_and_the_weekend(options_script):
    assert options_script.get_trading_days("2026-06-17", "2026-06-23") == [
        date(2026, 6, 17), date(2026, 6, 18), date(2026, 6, 22), date(2026, 6, 23)]


def test_get_trading_days_accepts_dates_and_ignores_skip_weekends(options_script):
    days = options_script.get_trading_days(
        date(2026, 6, 17), date(2026, 6, 23), skip_weekends=False)
    assert days == [date(2026, 6, 17), date(2026, 6, 18),
                    date(2026, 6, 22), date(2026, 6, 23)]


def test_is_trading_day_raises_without_calendar(options_script, no_calendar_library):
    with pytest.raises(ImportError):
        options_script.is_trading_day(date(2026, 6, 19))


def test_get_trading_days_raises_without_calendar(options_script, no_calendar_library):
    with pytest.raises(ImportError):
        options_script.get_trading_days("2026-06-17", "2026-06-23")


def test_a_month_with_sessions_is_not_all_non_trading(intraday_script):
    assert intraday_script.is_month_all_non_trading_days("2026-06") is False


def test_month_check_raises_without_calendar(intraday_script, no_calendar_library):
    with pytest.raises(ImportError):
        intraday_script.is_month_all_non_trading_days("2026-06")
