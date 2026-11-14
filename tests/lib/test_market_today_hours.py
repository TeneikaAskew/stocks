"""The hours at which the exchange's date and the container's UTC date differ.

FEAT-DATA-001, stage 1 of the market-time sweep. The jobs and services run
with no TZ, so their clock is UTC. This pins exactly when ``date.today()``
there is not the market date: it is what makes "a site whose job never runs
in those hours returns the same value after the change" a measured statement.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import lib.eastern_time as eastern_time
from lib.eastern_time import market_today
from tests.fixtures.market_clock import freeze_market_clock


def test_the_exchange_date_differs_from_the_utc_date_at_1587_hours_of_2026(monkeypatch):
    hour = datetime(2026, 1, 1, tzinfo=timezone.utc)
    last = datetime(2026, 12, 31, 23, tzinfo=timezone.utc)
    total = 0
    differing = 0
    hours_by_offset: dict[timedelta, set[int]] = defaultdict(set)
    while hour <= last:
        total += 1
        freeze_market_clock(monkeypatch, hour.isoformat())
        if market_today() != hour.date():
            differing += 1
            hours_by_offset[eastern_time.eastern_now().utcoffset()].add(hour.hour)
        hour += timedelta(hours=1)

    assert total == 8760
    assert differing == 1587
    assert dict(hours_by_offset) == {
        timedelta(hours=-4): {0, 1, 2, 3},
        timedelta(hours=-5): {0, 1, 2, 3, 4},
    }


def test_the_two_clock_change_days(monkeypatch):
    # Clocks go back on 2026-11-01: 05:30Z is 01:30 EDT, 04:59Z the next day is 23:59 EST.
    freeze_market_clock(monkeypatch, "2026-11-01T05:30:00Z")
    assert market_today() == date(2026, 11, 1)
    freeze_market_clock(monkeypatch, "2026-11-02T04:59:00Z")
    assert market_today() == date(2026, 11, 1)
    # Clocks go forward on 2026-03-08: 06:30Z is 01:30 EST.
    freeze_market_clock(monkeypatch, "2026-03-08T06:30:00Z")
    assert market_today() == date(2026, 3, 8)
