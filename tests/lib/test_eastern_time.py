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
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from lib import eastern_time
from lib.eastern_time import (
    ET,
    ET_NAME,
    UTC,
    as_eastern_time,
    eastern_bounds_utc,
    eastern_index_to_utc,
    as_utc_instant,
    localize_assuming_eastern,
    localize_assuming_utc,
    market_date,
    market_date_sql,
    market_today,
    market_today_sql,
    require_aware,
    utc_to_eastern_naive,
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


# -- pandas boundaries: the conversion market_data_intraday writers use ------


def test_vendor_eastern_bars_become_utc_instants_in_both_seasons():
    """09:30 Eastern is 13:30Z under EDT and 14:30Z under EST. The writers used
    to store 09:30 as 09:30Z (Eastern wall time stamped UTC, CLAUDE.md 3.9)."""
    naive = pd.DatetimeIndex(["2026-09-24 09:30", "2026-01-15 09:30"])
    out = eastern_index_to_utc(naive)
    assert str(out.tz) == "UTC"
    assert list(out) == [
        pd.Timestamp("2026-09-24 13:30", tz="UTC"),
        pd.Timestamp("2026-01-15 14:30", tz="UTC"),
    ]


def test_eastern_index_to_utc_keeps_series_shape():
    s = pd.Series(pd.to_datetime(["2026-07-06 04:00", "2026-07-06 19:59"]), name="ts")
    out = eastern_index_to_utc(s)
    assert isinstance(out, pd.Series) and out.name == "ts"
    assert list(out) == [pd.Timestamp("2026-07-06 08:00", tz="UTC"),
                         pd.Timestamp("2026-07-06 23:59", tz="UTC")]


def test_eastern_index_to_utc_refuses_to_relabel_an_instant():
    aware = pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC")
    with pytest.raises(ValueError, match="aware"):
        eastern_index_to_utc(aware)


def test_eastern_index_to_utc_raises_on_impossible_and_repeated_wall_times():
    with pytest.raises(Exception):
        eastern_index_to_utc(pd.DatetimeIndex(["2026-03-08 02:30"]))
    with pytest.raises(Exception):
        eastern_index_to_utc(pd.DatetimeIndex(["2026-11-01 01:30"]))


def test_utc_to_eastern_naive_round_trips_and_rejects_naive():
    naive = pd.DatetimeIndex(["2026-09-24 09:30", "2026-01-15 16:00"])
    assert list(utc_to_eastern_naive(eastern_index_to_utc(naive))) == list(naive)
    with pytest.raises(ValueError, match="aware"):
        utc_to_eastern_naive(naive)


# -- market dates and session windows ---------------------------------------


def test_market_today_is_the_eastern_date(monkeypatch):
    # 2026-07-04 01:30Z is still 2026-07-03 on the exchange's clock.
    monkeypatch.setattr(
        eastern_time, "eastern_now",
        lambda: datetime(2026, 7, 4, 1, 30, tzinfo=UTC).astimezone(ET),
    )
    assert market_today() == date(2026, 7, 3)


def test_eastern_bounds_utc_follow_dst():
    assert eastern_bounds_utc(date(2026, 7, 6), time(4), time(9, 30)) == (
        datetime(2026, 7, 6, 8, 0, tzinfo=UTC), datetime(2026, 7, 6, 13, 30, tzinfo=UTC))
    assert eastern_bounds_utc(date(2026, 1, 15), time(9, 30), time(16)) == (
        datetime(2026, 1, 15, 14, 30, tzinfo=UTC), datetime(2026, 1, 15, 21, 0, tzinfo=UTC))


# -- SQL fragments -------------------------------------------------------------


def test_market_date_sql_frames_the_column_in_eastern():
    assert market_date_sql("ts") == "(ts AT TIME ZONE 'America/New_York')::date"
    assert market_date_sql("a.alert_ts") == "(a.alert_ts AT TIME ZONE 'America/New_York')::date"


@pytest.mark.parametrize("bad", ["ts; DROP TABLE x", "ts)", "1ts", "", "a.b.c"])
def test_market_date_sql_refuses_non_identifiers(bad):
    with pytest.raises(ValueError, match="identifier"):
        market_date_sql(bad)


def test_market_today_sql_is_eastern_not_current_date():
    sql = market_today_sql()
    assert "CURRENT_DATE" not in sql
    assert sql == "(now() AT TIME ZONE 'America/New_York')::date"
