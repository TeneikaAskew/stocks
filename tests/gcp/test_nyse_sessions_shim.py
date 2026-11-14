"""New contract tests for the retained evaluate_ew_strikes NYSE shim."""
from datetime import date
import inspect
import sys

import pandas as pd
import pytest

from gcp.fetchers import evaluate_ew_strikes as ew
from lib import eastern_time


def test_holiday_week_and_early_close():
    schedule = ew.nyse_sessions(date(2026, 11, 23), date(2026, 11, 27))
    assert list(schedule.index.date) == [date(2026, 11, d) for d in (23, 24, 25, 27)]
    assert schedule.loc["2026-11-27", "market_close"] == pd.Timestamp("2026-11-27T18:00:00Z")
    pd.testing.assert_frame_equal(schedule, eastern_time.session_schedule(date(2026, 11, 23), date(2026, 11, 27)))


def test_dst_open_is_utc_correct():
    schedule = ew.nyse_sessions(date(2027, 3, 15), date(2027, 3, 15))
    assert schedule.iloc[0]["market_open"] == pd.Timestamp("2027-03-15T13:30:00Z")


def test_calendar_import_error_has_no_weekday_fallback(monkeypatch):
    eastern_time._reset_session_cache()
    try:
        with monkeypatch.context() as patcher:
            patcher.setitem(sys.modules, "pandas_market_calendars", None)
            with pytest.raises(ImportError):
                ew.nyse_sessions(date(2026, 11, 23), date(2026, 11, 27))
    finally:
        eastern_time._reset_session_cache()


def test_scorer_surface_is_removed():
    for name in ("scoring_session", "Session", "evaluate_range", "main", "_compute_verdict", "_UPDATE_SQL", "_CLEAR_SQL", "AlphaVantageConfig"):
        assert not hasattr(ew, name), name
    assert "earnings_whispers" not in inspect.getsource(ew)


def test_wrapper_source_is_unchanged():
    assert inspect.getsource(ew.nyse_sessions) == WRAPPER

WRAPPER = 'def nyse_sessions(start: date, end: date) -> pd.DataFrame:\n    """NYSE sessions in [start, end]: indexed by session date, with UTC\n    `market_open` / `market_close` (early closes included).\n\n    Read from the shared NYSE calendar (`lib.eastern_time`, FEAT-DATA-001).\n    There is no weekday fallback: a guessed session is the defect #1151\n    fixed, so a missing calendar must fail the run.\n    """\n    return session_schedule(start, end)\n'
