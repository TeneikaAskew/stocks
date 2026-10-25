"""Tests for the NYSE session functions in lib/eastern_time.py (FEAT-DATA-001).

One calendar for every job, script and the API, backed by
``pandas_market_calendars`` and cached per process. These tests run against
the real library (spec § Testing 1-4); the only fakes are the failure cases,
where the point is what happens when the library cannot answer:

  1. Known dates, including half days, observed holidays and a datetime that
     is still the previous day in New York.
  2. Parity with the library's own schedule: every calendar day 2020-2027 for
     the date functions, every session 2000-2027 for the open/close times
     (2002-09-11 opened at 12:00 ET).
  3. Fails loud: no library, ``get_calendar`` raising, ``schedule`` raising,
     and an empty schedule (which must not be cached) all raise from every one
     of the nine functions. There is no weekday-only fallback (CLAUDE.md 3.7).
  4. Cache: one build for repeated calls, one build for 16 concurrent cold
     calls, concurrent extensions in opposite directions both kept, and true
     neighbours at both edges of the cached range.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from bisect import bisect_left, bisect_right
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pandas_market_calendars as mcal
import pytest

from lib import eastern_time
from lib.eastern_time import (
    holidays_in,
    is_session,
    latest_session_on_or_before,
    next_session,
    previous_session,
    session_close,
    session_count,
    session_schedule,
    sessions_between,
)

REPO = Path(__file__).resolve().parents[2]

# One call of each of the nine functions, for the fail-loud tests.
ALL_NINE = {
    "is_session": lambda: is_session("2026-10-19"),
    "previous_session": lambda: previous_session("2026-10-19"),
    "next_session": lambda: next_session("2026-10-19"),
    "latest_session_on_or_before": lambda: latest_session_on_or_before("2026-10-18"),
    "sessions_between": lambda: sessions_between("2026-10-01", "2026-10-19"),
    "session_count": lambda: session_count("2026-10-16", "2026-10-19"),
    "session_close": lambda: session_close("2026-10-19"),
    "holidays_in": lambda: holidays_in(2026),
    "session_schedule": lambda: session_schedule("2026-10-01", "2026-10-19"),
}


@pytest.fixture(autouse=True)
def _fresh_cache():
    """Every test starts cold and leaves nothing behind for the next file."""
    eastern_time._reset_session_cache()
    yield
    eastern_time._reset_session_cache()


@pytest.fixture
def frozen_2026(monkeypatch):
    """Pin the clock the default cache range reads, so it is 2000 to 2028."""
    monkeypatch.setattr(eastern_time, "market_today", lambda: date(2026, 10, 19))


class _ScheduleCounter(list):
    """A list of schedule calls that also carries the injected delay."""

    state: dict


@pytest.fixture
def schedule_calls(monkeypatch):
    """Count schedule builds: every calendar handed out wraps ``schedule``.

    ``delay`` widens the race window for the concurrency tests.
    """
    real_get_calendar = mcal.get_calendar
    calls = _ScheduleCounter()
    calls.state = state = {"delay": 0.0}

    def counting_get_calendar(name, *args, **kwargs):
        cal = real_get_calendar(name, *args, **kwargs)
        real_schedule = type(cal).schedule.__get__(cal)

        def schedule(*s_args, **s_kwargs):
            calls.append((s_args, s_kwargs))
            if state["delay"]:
                time.sleep(state["delay"])
            return real_schedule(*s_args, **s_kwargs)

        cal.schedule = schedule
        return cal

    monkeypatch.setattr(mcal, "get_calendar", counting_get_calendar)
    return calls


# -- 1. known dates -----------------------------------------------------------


def test_known_dates():
    assert previous_session("2026-10-19") == date(2026, 10, 16)
    assert is_session("2026-06-19") is False  # Juneteenth
    assert is_session("2026-11-27") is True  # day after Thanksgiving, half day
    assert session_close("2026-11-27") == datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc)
    assert is_session("2027-01-18") is False  # Martin Luther King Jr. Day
    assert next_session("2027-12-24") == date(2027, 12, 27)
    assert holidays_in(2027) == [
        date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26),
        date(2027, 5, 31), date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6),
        date(2027, 11, 25), date(2027, 12, 24),
    ]


def test_session_close_is_utc():
    close = session_close(date(2026, 10, 19))
    assert close.tzinfo is timezone.utc
    assert close == datetime(2026, 10, 19, 20, 0, tzinfo=timezone.utc)  # 16:00 EDT


def test_session_count_and_between():
    assert session_count("2026-10-16", "2026-10-19") == 1
    assert session_count("2026-10-19", "2026-10-19") == 0
    assert session_count("2026-10-19", "2026-10-16") == 0
    assert sessions_between("2026-06-17", "2026-06-23") == [
        date(2026, 6, 17), date(2026, 6, 18), date(2026, 6, 22), date(2026, 6, 23),
    ]
    assert sessions_between("2026-06-23", "2026-06-17") == []
    assert latest_session_on_or_before("2026-10-18") == date(2026, 10, 16)
    assert latest_session_on_or_before("2026-10-16") == date(2026, 10, 16)


def test_session_close_rejects_non_session():
    with pytest.raises(ValueError):
        session_close("2026-06-19")


def test_datetime_inputs_use_eastern_date():
    # 02:00Z on Monday 10-19 is 22:00 on Sunday 10-18 in New York.
    assert is_session(datetime(2026, 10, 19, 2, 0, tzinfo=timezone.utc)) is False
    assert is_session(datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)) is True


def test_naive_datetime_rejected():
    # market_date refuses to guess the zone of a naive datetime.
    with pytest.raises(ValueError):
        is_session(datetime(2026, 10, 19, 12, 0))  # noqa: DTZ001 -- naive on purpose


# -- 2. parity with the library -------------------------------------------------


def test_parity_2020_2027():
    # The oracle reaches past both ends so 2020-01-01's previous session and
    # 2027-12-31's next session are in it.
    valid = sorted(
        d.date() for d in mcal.get_calendar("NYSE").valid_days("2019-12-01", "2028-01-31")
    )
    valid_set = set(valid)
    d = date(2020, 1, 1)
    while d <= date(2027, 12, 31):
        assert is_session(d) == (d in valid_set), d
        assert previous_session(d) == valid[bisect_left(valid, d) - 1], d
        assert next_session(d) == valid[bisect_right(valid, d)], d
        d += timedelta(days=1)


def test_schedule_open_close_parity_2000_2027():
    got = session_schedule("2000-01-03", "2027-12-31")
    want = mcal.get_calendar("NYSE").schedule("2000-01-03", "2027-12-31")[
        ["market_open", "market_close"]
    ]
    pd.testing.assert_frame_equal(got, want)
    row = got.loc[pd.Timestamp("2002-09-11")]
    assert row["market_open"] == pd.Timestamp("2002-09-11 16:00", tz="UTC")
    assert row["market_close"] == pd.Timestamp("2002-09-11 20:00", tz="UTC")


def test_session_schedule_is_a_copy():
    got = session_schedule("2026-10-01", "2026-10-19")
    got.iloc[0, 0] = pd.Timestamp("1999-01-01", tz="UTC")
    assert session_schedule("2026-10-01", "2026-10-19").iloc[0, 0] != got.iloc[0, 0]


# -- 3. fails loud ----------------------------------------------------------------


def test_fails_loud_without_library(monkeypatch):
    monkeypatch.setitem(sys.modules, "pandas_market_calendars", None)
    for name, call in ALL_NINE.items():
        with pytest.raises(ImportError):
            call()
            pytest.fail(f"{name} answered without the library")


def test_fails_loud_on_lookup_error(monkeypatch):
    class Boom:
        def schedule(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(mcal, "get_calendar", lambda name, *a, **k: Boom())
    for name, call in ALL_NINE.items():
        with pytest.raises(RuntimeError, match="boom"):
            call()
            pytest.fail(f"{name} swallowed a schedule error")


def test_fails_loud_when_get_calendar_raises(monkeypatch):
    def no_cal(name, *args, **kwargs):
        raise RuntimeError("no cal")

    monkeypatch.setattr(mcal, "get_calendar", no_cal)
    for name, call in ALL_NINE.items():
        with pytest.raises(RuntimeError, match="no cal"):
            call()
            pytest.fail(f"{name} swallowed a get_calendar error")


def test_empty_schedule_rejected_and_not_cached(monkeypatch):
    class Empty:
        def schedule(self, *args, **kwargs):
            return pd.DataFrame(
                {"market_open": pd.Series(dtype="datetime64[ns, UTC]"),
                 "market_close": pd.Series(dtype="datetime64[ns, UTC]")},
                index=pd.DatetimeIndex([]),
            )

    with monkeypatch.context() as m:
        m.setattr(mcal, "get_calendar", lambda name, *a, **k: Empty())
        for name, call in ALL_NINE.items():
            with pytest.raises(RuntimeError):
                call()
                pytest.fail(f"{name} answered from an empty schedule")
    # Real calendar back, cache NOT reset: the empty build was never kept.
    assert is_session("2026-10-19") is True


def test_library_not_imported_at_module_import():
    code = (
        "import sys, lib.eastern_time; "
        "assert 'pandas_market_calendars' not in sys.modules, 'imported eagerly'"
    )
    subprocess.run([sys.executable, "-c", code], cwd=REPO, check=True)


# -- 4. cache -----------------------------------------------------------------------


def test_schedule_built_once(schedule_calls):
    start = date(2005, 1, 1)
    for i in range(1000):
        d = start + timedelta(days=(i * 37) % 7000)
        match i % 5:
            case 0:
                is_session(d)
            case 1:
                previous_session(d)
            case 2:
                next_session(d)
            case 3:
                session_count(d, d + timedelta(days=30))
            case 4:
                latest_session_on_or_before(d)
    assert len(schedule_calls) == 1


def test_cache_boundaries_find_neighbours(schedule_calls, frozen_2026):
    assert is_session("2000-01-01") is False  # first build
    assert previous_session(date(2000, 1, 1)) == date(1999, 12, 31)

    eastern_time._reset_session_cache()
    is_session("2026-10-19")  # built 2000-01-01 through 2028-12-31
    del schedule_calls[:]
    assert next_session(date(2028, 12, 29)) == date(2029, 1, 2)
    assert len(schedule_calls) == 1  # one extension past the edge


def test_concurrent_first_calls_build_once(schedule_calls):
    schedule_calls.state["delay"] = 0.2
    barrier = threading.Barrier(16)

    def worker():
        barrier.wait()
        return previous_session("2026-10-19")

    # result() re-raises a worker's exception, so nothing is swallowed.
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = [f.result() for f in [pool.submit(worker) for _ in range(16)]]
    assert len(schedule_calls) == 1
    assert results == [date(2026, 10, 16)] * 16


def test_concurrent_extensions_both_kept(schedule_calls, frozen_2026):
    is_session("2026-10-19")  # cache built for 2000 through 2028
    del schedule_calls[:]
    schedule_calls.state["delay"] = 0.2
    barrier = threading.Barrier(2)

    def ask(fn, day):
        barrier.wait()
        return fn(day)

    with ThreadPoolExecutor(max_workers=2) as pool:
        prev = pool.submit(ask, previous_session, date(1995, 1, 3))
        nxt = pool.submit(ask, next_session, date(2032, 12, 31))
        assert (prev.result(), nxt.result()) == (date(1994, 12, 30), date(2033, 1, 3))

    del schedule_calls[:]
    schedule_calls.state["delay"] = 0.0
    assert previous_session(date(1995, 1, 3)) == date(1994, 12, 30)
    assert next_session(date(2032, 12, 31)) == date(2033, 1, 3)
    assert schedule_calls == []
