"""/api/market/dates caches until the next ingestion, not for a fixed TTL.

The query behind that endpoint is a Parallel Seq Scan of the whole per-ticker
partition (measured 2026-09-06: 2,003,580 rows scanned to return 3,278 dates,
1,716 ms), so it has to be cached. But a fixed 12h TTL anchored to request
time hides newly ingested data: `fetch-market-data` writes
market_data_intraday at 23:00 UTC (docs/PIPELINE.md), so an entry populated at
22:00 UTC would serve the pre-ingestion date list until 10:00 the next
morning, and the current trading day would be missing from the Charts picker
all evening.

Expiry is therefore anchored to the ingestion boundary. These tests pin that,
because an off-by-one-day expiry is invisible in normal use — the endpoint
still returns plausible dates, just stale ones.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "platform"))

pytest.importorskip("fastapi")

from api.main import (  # noqa: E402
    _INGEST_GRACE,
    _INGEST_HOUR_UTC,
    _next_ingest_boundary,
)


def _utc(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def test_boundary_is_after_todays_run_when_asked_before_it():
    """22:00 UTC, an hour before the run → expire tonight, not tomorrow.

    This is the exact case that motivated the change: a fixed TTL here would
    span the ingestion and serve yesterday's list all evening.
    """
    got = _next_ingest_boundary(_utc(2026, 9, 6, 22))
    assert got == _utc(2026, 9, 6, _INGEST_HOUR_UTC) + _INGEST_GRACE
    assert got - _utc(2026, 9, 6, 22) < timedelta(hours=2)


def test_boundary_rolls_to_tomorrow_once_todays_run_has_passed():
    got = _next_ingest_boundary(_utc(2026, 9, 6, 23, 45))
    assert got == _utc(2026, 9, 7, _INGEST_HOUR_UTC) + _INGEST_GRACE


def test_boundary_is_always_in_the_future():
    """A boundary at or before `now` would make the cache useless (or, if the
    comparison were flipped, never expire)."""
    start = _utc(2026, 9, 6, 0)
    for minutes in range(0, 24 * 60, 7):
        now = start + timedelta(minutes=minutes)
        assert _next_ingest_boundary(now) > now


def test_grace_window_covers_the_write():
    """The job needs time to finish writing before we re-read."""
    assert _INGEST_GRACE > timedelta(0)
    boundary = _next_ingest_boundary(_utc(2026, 9, 6, 12))
    assert boundary.hour == _INGEST_HOUR_UTC
    assert boundary.minute == int(_INGEST_GRACE.total_seconds() // 60)


def test_default_now_is_utc_aware():
    """A naive datetime here would raise on the comparison in the handler."""
    got = _next_ingest_boundary()
    assert got.tzinfo is not None
    assert got > datetime.now(timezone.utc)
