"""validate_brief_accuracy frames its session windows in Eastern time.

Reader sweep on #1185: the regular session was hard-coded as 13:30-20:00Z,
which is 09:30-16:00 ET only under EDT. Every winter validation scanned an
hour of premarket, missed the last regular hour, and reported crossings 60
minutes late.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from scripts.validation import validate_brief_accuracy as v


@pytest.mark.parametrize("day,open_utc,close_utc", [
    (date(2026, 1, 15), datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc),
     datetime(2026, 1, 15, 21, 0, tzinfo=timezone.utc)),    # EST
    (date(2026, 7, 15), datetime(2026, 7, 15, 13, 30, tzinfo=timezone.utc),
     datetime(2026, 7, 15, 20, 0, tzinfo=timezone.utc)),    # EDT
])
def test_regular_session_follows_daylight_saving(day, open_utc, close_utc):
    assert v._session_bounds(day) == (open_utc, close_utc)


def test_extended_session_is_the_eastern_day_through_the_2000_bar():
    lo, hi = v._session_bounds(date(2026, 1, 15), include_extended=True)
    assert lo == datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc)     # 04:00 EST
    assert hi == datetime(2026, 1, 16, 1, 1, tzinfo=timezone.utc)     # past 20:00 EST


class _Cursor:
    def __init__(self, row):
        self.row, self.params = row, None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        self.params = params

    def fetchone(self):
        return self.row


class _Conn:
    def __init__(self, row):
        self.cur = _Cursor(row)

    def cursor(self):
        return self.cur


def test_a_winter_crossing_counts_minutes_from_the_eastern_open():
    """A bar at 14:31Z on an EST day is one minute after the 09:30 ET open and
    reads 09:31 in the report, not 61 minutes / 14:31."""
    ts = datetime(2026, 1, 15, 14, 31, tzinfo=timezone.utc)
    conn = _Conn((ts, 1.0, 2.0, 1.0, 1.5, 100))
    at, minutes = v.find_first_cross(conn, "SPY", date(2026, 1, 15), 1.9, "above")
    assert minutes == 1
    assert at.startswith("2026-01-15T09:31")
    assert conn.cur.params[1] == datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
