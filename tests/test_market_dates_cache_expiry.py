"""/api/market/dates caches until the next ingestion, computed in EASTERN.

The query behind that endpoint is a Parallel Seq Scan of the whole per-ticker
partition (measured 2026-09-06: 2,003,580 rows scanned to return 3,278 dates,
1,716 ms), so it has to be cached. But the expiry has to track the thing that
changes the answer, and that is the daily ingestion.

Read live from GCP rather than from docs/PIPELINE.md, which says "23:00 UTC"
and is WRONG:

    $ gcloud scheduler jobs describe fetch-market-data-daily --location=us-east1
      0 23 * * 1-5   America/New_York   ENABLED

So the job runs at 23:00 ET — 03:00 UTC under EDT, 04:00 UTC under EST, on the
NEXT calendar day. Two earlier versions of this cache were wrong in different
ways, which is why the arithmetic is pinned rather than eyeballed:

  1. a fixed 12h TTL from request time (spanned the ingestion entirely)
  2. a fixed 23:30 UTC boundary (expired hours BEFORE the job, repopulated the
     pre-ingestion list, then held it for a further day)

Both failures are invisible in normal use: the endpoint keeps returning
plausible dates, just stale ones.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "platform"))

pytest.importorskip("fastapi")

from api.main import (  # noqa: E402
    _INGEST_GRACE,
    _INGEST_HOUR_ET,
    _next_ingest_boundary,
)

ET = ZoneInfo("America/New_York")


def _et(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


def _boundary_et(now):
    return _next_ingest_boundary(now).astimezone(ET)


def test_boundary_lands_just_after_the_eastern_run():
    """Mid-afternoon ET on a Tuesday → tonight's 23:00 ET run plus grace."""
    got = _boundary_et(_et(2026, 9, 8, 14))
    assert got.hour == _INGEST_HOUR_ET
    assert got.minute == int(_INGEST_GRACE.total_seconds() // 60)
    assert got.date() == _et(2026, 9, 8, 14).date()


def test_utc_hour_alone_would_have_been_wrong():
    """The regression this replaced.

    22:00 UTC on a Tuesday is 18:00 ET — five hours BEFORE the run. A 23:30
    UTC boundary would expire at 19:30 ET, repopulate the pre-ingestion list,
    and then hold it until the next day. The ET boundary must still be ahead
    of the actual 23:00 ET job.
    """
    now = datetime(2026, 9, 8, 22, tzinfo=timezone.utc)
    boundary = _next_ingest_boundary(now)
    run_at_et = _et(2026, 9, 8, _INGEST_HOUR_ET)
    assert boundary > run_at_et.astimezone(timezone.utc), (
        "cache expires before the ingestion job it is waiting for")


def test_boundary_rolls_forward_once_the_run_has_passed():
    got = _boundary_et(_et(2026, 9, 8, 23, 45))
    assert got.date() == _et(2026, 9, 9, 0).date()


def test_friday_night_skips_the_weekend():
    """The cron is `1-5`. Nothing ingests Saturday or Sunday."""
    got = _boundary_et(_et(2026, 9, 11, 23, 45))   # Friday, after the run
    assert got.weekday() == 0, f"expected Monday, got {got:%A %Y-%m-%d}"


def test_no_boundary_ever_falls_on_a_weekend():
    start = _et(2026, 9, 7, 0)   # Monday
    for hours in range(0, 24 * 14):
        got = _boundary_et(start + timedelta(hours=hours))
        assert got.weekday() <= 4, f"weekend boundary {got:%A %Y-%m-%d %H:%M}"


def test_boundary_is_always_in_the_future():
    """A flipped comparison would either never expire or never cache."""
    start = datetime(2026, 9, 7, tzinfo=timezone.utc)
    for minutes in range(0, 14 * 24 * 60, 37):
        now = start + timedelta(minutes=minutes)
        assert _next_ingest_boundary(now) > now


def test_dst_transitions_hold_the_eastern_wall_clock():
    """The job fires at 23:00 ET on both sides of a DST change.

    Under a fixed UTC hour the boundary would drift by an hour twice a year;
    under the named zone the ET wall-clock time is invariant. 2026-11-01 is
    the US fall-back date.
    """
    before = _boundary_et(_et(2026, 10, 29, 12))   # EDT
    after = _boundary_et(_et(2026, 11, 3, 12))     # EST
    assert before.hour == after.hour == _INGEST_HOUR_ET
    assert before.utcoffset() != after.utcoffset(), (
        "expected these samples to straddle the DST change")


def test_returns_utc_aware_for_comparison_in_the_handler():
    got = _next_ingest_boundary()
    assert got.tzinfo is not None
    assert got.utcoffset() == timedelta(0), "handler compares against UTC now"
    assert got > datetime.now(timezone.utc)
