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
    """Serves a stored session: filters rows by the query's raw bounds."""

    def __init__(self, rows):
        self.rows, self.params = rows, None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        self.params = params

    def fetchall(self):
        _, lo, hi = self.params
        return [r for r in self.rows if lo <= r[0] < hi]


class _Conn:
    def __init__(self, rows):
        self.cur = _Cursor(rows)

    def cursor(self):
        return self.cur


def _stored(day: str, stored: str, spike_at: str, spike_price: float):
    """A full AV session in one stored convention; flat at 1.0 except one
    bar whose high is ``spike_price`` at Eastern wall time ``spike_at``."""
    import pandas as pd
    wall = pd.date_range(f"{day} 04:00", f"{day} 20:00", freq="1min")
    ts = (wall.tz_localize("UTC") if stored == "et_label"
          else wall.tz_localize("America/New_York").tz_convert("UTC"))
    minute = wall.hour * 60 + wall.minute
    rows = []
    for w, t, m in zip(wall, ts, minute):
        hi = spike_price if w == pd.Timestamp(f"{day} {spike_at}") else 1.0
        rows.append((t.to_pydatetime(), 1.0, hi, 1.0, 1.0, 5000 if 570 <= m < 600 else 1000))
    return rows


@pytest.mark.parametrize("day,stored", [("2026-01-15", "utc"), ("2026-01-15", "et_label"),
                                        ("2026-07-15", "utc"), ("2026-07-15", "et_label")])
def test_a_crossing_is_found_and_timed_in_either_stored_convention(day, stored):
    """A 10:31 ET crossing reads as 10:31 ET, 61 minutes after the open, in
    both seasons and both conventions (Codex P2 on #1185: a legacy row stored
    at 14:31+00 is 14:31 ET, not 10:31)."""
    conn = _Conn(_stored(day, stored, "10:31", 1.02))
    at, minutes = v.find_first_cross(conn, "SPY", date.fromisoformat(day), 1.01, "above",
                                     filter_outliers=False)
    assert at[11:16] == "10:31"
    assert minutes == 61


@pytest.mark.parametrize("stored", ["utc", "et_label"])
def test_session_stats_cover_the_regular_session_in_either_convention(stored):
    conn = _Conn(_stored("2026-01-15", stored, "15:59", 1.5))
    st = v.fetch_intraday(conn, "SPY", date(2026, 1, 15), filter_outliers=False)
    assert st.bar_count == 390
    assert st.high == 1.5
    assert st.session_start.startswith("2026-01-15T14:30")
