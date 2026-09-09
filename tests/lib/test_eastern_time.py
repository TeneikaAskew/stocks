"""Tests for lib/eastern_time.py — the single source of truth for ET.

The module replaces a repository-wide source scanner: instead of grepping
every file for a fixed-offset spelling, one canonical `ET` / `ET_NAME` is
imported everywhere and a boot assertion vouches for the loaded zone at
import time. These tests pin both halves of that contract:

  1. `ET` / `ET_NAME` are the named, DST-correct `America/New_York` zone.
  2. `verify_eastern_is_dst_correct` is a real gate — it passes on the true
     zone and raises on a frozen fixed offset (the slim-tzdata failure mode).
"""
from __future__ import annotations

import importlib
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from lib import eastern_time
from lib.eastern_time import (
    ET,
    ET_NAME,
    UTC,
    as_eastern_time,
    as_utc_instant,
    localize_assuming_eastern,
    localize_assuming_utc,
    market_date,
    require_aware,
    verify_eastern_is_dst_correct,
)


def test_et_name_is_the_named_zone():
    assert ET_NAME == "America/New_York"


def test_et_is_the_zoneinfo_for_that_name():
    assert ET == ZoneInfo(ET_NAME)


def test_et_tracks_dst():
    """January is EST (-05:00); July is EDT (-04:00). A fixed offset or a
    frozen zone would fail one of these."""
    assert datetime(2026, 1, 15, 12, tzinfo=ET).utcoffset() == timedelta(hours=-5)
    assert datetime(2026, 7, 15, 12, tzinfo=ET).utcoffset() == timedelta(hours=-4)


def test_verify_passes_on_the_real_zone():
    # Returns None (no raise) when the loaded zone is DST-correct.
    assert verify_eastern_is_dst_correct() is None


def test_verify_raises_on_a_frozen_fixed_offset(monkeypatch):
    """A slim image with incomplete tzdata, or a zone pinned to a single
    offset, is the failure the boot assertion exists to catch. Swap in a
    fixed -05:00 (correct in January, wrong all summer) and the check must
    raise rather than let every Eastern time silently shift."""
    frozen = timezone(timedelta(hours=-5))
    monkeypatch.setattr(eastern_time, "ET", frozen)
    with pytest.raises(RuntimeError, match="not DST-correct"):
        verify_eastern_is_dst_correct()


def test_importing_the_module_runs_the_boot_assertion():
    # Reload succeeds because the real zone passes; the import-time call is
    # what makes a broken deployment fail loudly at startup.
    importlib.reload(eastern_time)
    assert eastern_time.ET == ZoneInfo("America/New_York")


def test_require_aware_rejects_ambiguous_naive_datetime():
    with pytest.raises(ValueError, match="must be timezone-aware"):
        require_aware(datetime(2026, 7, 4, 12))


def test_explicit_localizers_do_not_relabel_aware_instants():
    naive = datetime(2026, 7, 4, 12)
    assert localize_assuming_utc(naive).tzinfo is UTC
    assert localize_assuming_eastern(naive).tzinfo is ET
    with pytest.raises(ValueError, match="already timezone-aware"):
        localize_assuming_utc(naive.replace(tzinfo=UTC))


def test_eastern_localizer_rejects_nonexistent_spring_wall_time():
    with pytest.raises(ValueError, match="does not exist"):
        localize_assuming_eastern(datetime(2026, 3, 8, 2, 30))


def test_eastern_localizer_requires_fold_for_repeated_autumn_wall_time():
    repeated = datetime(2026, 11, 1, 1, 30)
    with pytest.raises(ValueError, match="ambiguous"):
        localize_assuming_eastern(repeated)

    first = localize_assuming_eastern(repeated, fold=0)
    second = localize_assuming_eastern(repeated, fold=1)
    assert first.utcoffset() == timedelta(hours=-4)
    assert second.utcoffset() == timedelta(hours=-5)
    assert as_utc_instant(second) - as_utc_instant(first) == timedelta(hours=1)


def test_eastern_localizer_rejects_invalid_fold():
    with pytest.raises(ValueError, match="fold must be"):
        localize_assuming_eastern(datetime(2026, 7, 4, 12), fold=2)


def test_utc_and_eastern_conversion_preserve_the_instant():
    instant = datetime(2026, 7, 4, 1, 30, tzinfo=UTC)
    eastern = as_eastern_time(instant)
    assert eastern.isoformat() == "2026-07-03T21:30:00-04:00"
    assert as_utc_instant(eastern) == instant


def test_market_date_converts_before_truncating_at_utc_midnight():
    instant = datetime(2026, 7, 4, 1, 30, tzinfo=UTC)
    assert market_date(instant) == date(2026, 7, 3)
    assert market_date(date(2026, 7, 4)) == date(2026, 7, 4)
