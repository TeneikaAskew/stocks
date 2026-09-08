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
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from lib import eastern_time
from lib.eastern_time import ET, ET_NAME, verify_eastern_is_dst_correct


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
