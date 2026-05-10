"""Tests for `persist_level_map` freshness guard (PR #381).

Pre-2026-05-10 the writer accepted any LevelMap and persisted it
unconditionally. The 5/6 production failure showed why this matters:
when the daily fetcher was latched at 4/27 (Track A G.P0.2 freeze),
the brief built levels off 4/27-stale data and silently wrote them
into rows stamped `as_of=5/6`. Every downstream consumer
(signal_monitor, insight pipeline, dashboard) then trusted the
poisoned level cache.

The guard uses NYSE business-days, not calendar-days, because the
semantic intent is "no more than N trading sessions behind." The
sibling freshness guards (#323 audit watchdog, #325 DataLoader
on_stale) currently use calendar-days; a follow-up PR should convert
all three for consistency.

These tests lock in the v2 contract:
  1. None source_data_as_of → write succeeds (back-compat).
  2. Fresh source (≤ max_age_business_days NYSE days behind) → write
     succeeds, column populated.
  3. Stale source (> max_age_business_days) → StaleSourceDataError.
  4. NYSE market holidays correctly skipped.
  5. tz-aware vs tz-naive timestamps both work.
  6. The new `source_data_as_of` parameter is bound into every row.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from lib.strat_levels import (
    LevelMap, StratLevel,
    persist_level_map, StaleSourceDataError,
    _trading_days_between,
)


def _level_map():
    return LevelMap(
        ticker="SPY",
        as_of="2026-05-10T13:30:00+00:00",
        current_price=720.0,
        levels=[
            StratLevel(name="PDH", price=722.12, timeframe="day",
                       level_type="high", strat_class="2D",
                       is_current=False, period_label="2026-05-09"),
            StratLevel(name="PDL", price=714.99, timeframe="day",
                       level_type="low", strat_class="2D",
                       is_current=False, period_label="2026-05-09"),
        ],
        pmg_zones=[],
    )


def _mock_conn():
    """Mock psycopg2/pg8000 conn that captures executemany rows."""
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


# ── 1) None source → back-compat: write succeeds ──────────────────────


def test_persist_with_none_source_writes():
    """Legacy caller path: no freshness param, write proceeds."""
    lm = _level_map()
    conn, cur = _mock_conn()
    n = persist_level_map(lm, conn, source_data_as_of=None)
    assert n == 2
    assert cur.executemany.called
    sql, rows = cur.executemany.call_args[0]
    assert "INSERT INTO strat_levels" in sql
    assert "source_data_as_of" in sql
    for row in rows:
        assert row[-1] is None


# ── 2) Fresh source — same trading day → write succeeds ───────────────


def test_persist_same_trading_day_writes():
    """Mon brief reading Fri close = 1 NYSE trading day = within default 2."""
    lm = _level_map()
    conn, cur = _mock_conn()
    # Mon 5/11 13:30 UTC (= Mon morning brief in ET)
    today = datetime(2026, 5, 11, 13, 30, tzinfo=timezone.utc)
    # Fri 5/8 23:00 UTC (= Fri evening close)
    src = datetime(2026, 5, 8, 23, 0, tzinfo=timezone.utc)
    n = persist_level_map(lm, conn, source_data_as_of=src, today=today)
    assert n == 2
    rows = cur.executemany.call_args[0][1]
    for row in rows:
        assert row[-1] == src


# ── 3) Stale source — multi-day freeze → raises ───────────────────────


def test_persist_with_stale_source_raises_5x6_scenario():
    """The actual 5/6 production failure: 4/27 source vs 5/6 brief =
    6 NYSE trading days (4/28 + 4/29 + 4/30 + 5/1 + 5/4 + 5/5 + 5/6).
    Well past default threshold of 2."""
    lm = _level_map()
    conn, cur = _mock_conn()
    today = datetime(2026, 5, 6, 13, 30, tzinfo=timezone.utc)
    src = datetime(2026, 4, 27, 23, 0, tzinfo=timezone.utc)
    with pytest.raises(StaleSourceDataError, match="trading days behind"):
        persist_level_map(lm, conn, source_data_as_of=src, today=today)
    assert not cur.executemany.called


def test_persist_at_business_day_threshold_boundary():
    """Exactly max_age_business_days behind → still allowed (inclusive).

    Thu 5/22 close → Tue 5/27 morning (post-Memorial-Day Mon 5/26):
    valid_days(Fri 5/23 → Tue 5/27) = [Fri 5/23, Tue 5/27] = 2.
    With threshold 2, this should be allowed.
    """
    lm = _level_map()
    conn, cur = _mock_conn()
    today = datetime(2026, 5, 27, 13, 30, tzinfo=timezone.utc)  # Tue
    src = datetime(2026, 5, 22, 23, 0, tzinfo=timezone.utc)     # Thu
    n = persist_level_map(lm, conn, source_data_as_of=src,
                          max_age_business_days=2, today=today)
    assert n == 2  # 2 trading days, at threshold → allowed


def test_persist_just_past_business_day_threshold_raises():
    """3 trading days back with threshold=2 → refused."""
    lm = _level_map()
    conn, cur = _mock_conn()
    # Wed 5/14 → Mon 5/19 = Thu/Fri/Mon = 3 trading days
    today = datetime(2026, 5, 19, 13, 30, tzinfo=timezone.utc)
    src = datetime(2026, 5, 13, 23, 0, tzinfo=timezone.utc)
    with pytest.raises(StaleSourceDataError):
        persist_level_map(lm, conn, source_data_as_of=src,
                          max_age_business_days=2, today=today)


# ── 4) NYSE holidays correctly skipped ────────────────────────────────


def test_trading_days_skips_memorial_day_and_weekends():
    """Memorial Day 2026 = Mon 5/25. Trading days from Thu 5/21 (excl)
    to Tue 5/26 (incl) should be: Fri 5/22 + Tue 5/26 = 2 days."""
    src = pd.Timestamp("2026-05-21 23:00:00", tz="UTC")
    today = pd.Timestamp("2026-05-26 13:30:00", tz="UTC")
    n = _trading_days_between(src, today)
    assert n == 2, f"expected 2 NYSE trading days (Fri+Tue, skipping weekend+Memorial-Day), got {n}"


def test_trading_days_skips_july_4_observed():
    """July 4, 2026 is Saturday; NYSE observes the holiday on Friday 7/3.
    Trading days from Wed 7/1 (excl) to Mon 7/6 (incl) = Thu 7/2, Mon 7/6 = 2."""
    src = pd.Timestamp("2026-07-01 23:00:00", tz="UTC")
    today = pd.Timestamp("2026-07-06 13:30:00", tz="UTC")
    n = _trading_days_between(src, today)
    assert n == 2, f"expected 2 NYSE trading days (Thu+Mon, skipping observed-July-4), got {n}"


def test_trading_days_zero_when_source_after_today():
    """source_ts > ref_ts → zero (don't underflow)."""
    src = pd.Timestamp("2026-05-10 13:30:00", tz="UTC")
    today = pd.Timestamp("2026-05-09 13:30:00", tz="UTC")
    assert _trading_days_between(src, today) == 0


# ── 5) tz handling ────────────────────────────────────────────────────


def test_persist_naive_source_treated_as_utc():
    lm = _level_map()
    conn, cur = _mock_conn()
    today = datetime(2026, 5, 11, 13, 30, tzinfo=timezone.utc)
    src = pd.Timestamp("2026-05-08 23:00")  # naive Fri 5/8
    n = persist_level_map(lm, conn, source_data_as_of=src, today=today)
    assert n == 2


def test_persist_pandas_timestamp_source_works():
    lm = _level_map()
    conn, cur = _mock_conn()
    today = pd.Timestamp("2026-05-11 13:30:00", tz="UTC")
    src = pd.Timestamp("2026-05-08 23:00:00", tz="UTC")
    n = persist_level_map(lm, conn, source_data_as_of=src, today=today)
    assert n == 2


# ── 6) Stricter caller can tighten the threshold ──────────────────────


def test_persist_stricter_caller_can_set_zero_business_days():
    """Intraday re-runs may want 'must be today's data' enforcement
    via max_age_business_days=0."""
    lm = _level_map()
    conn, cur = _mock_conn()
    today = datetime(2026, 5, 12, 13, 30, tzinfo=timezone.utc)  # Tue
    src = datetime(2026, 5, 11, 23, 0, tzinfo=timezone.utc)     # Mon
    # default of 2 → 1 trading day = OK
    n = persist_level_map(lm, conn, source_data_as_of=src, today=today)
    assert n == 2
    # stricter zero → 1 trading day past 0 = REFUSED
    with pytest.raises(StaleSourceDataError):
        persist_level_map(lm, conn, source_data_as_of=src,
                          max_age_business_days=0, today=today)


# ── 7) Empty level map short-circuits before freshness check ──────────


def test_persist_empty_level_map_short_circuits():
    lm = LevelMap(ticker="SPY", as_of="2026-05-10", current_price=720.0,
                   levels=[], pmg_zones=[])
    conn, cur = _mock_conn()
    today = datetime(2026, 5, 10, 13, 30, tzinfo=timezone.utc)
    src = today - timedelta(days=30)
    n = persist_level_map(lm, conn, source_data_as_of=src, today=today)
    assert n == 0
    assert not cur.executemany.called


# ── 8) Error message points at the runbook + uses trading-day units ───


def test_stale_error_message_references_runbook_and_uses_trading_days():
    lm = _level_map()
    conn, cur = _mock_conn()
    today = datetime(2026, 5, 6, 13, 30, tzinfo=timezone.utc)
    src = datetime(2026, 4, 27, 23, 0, tzinfo=timezone.utc)
    try:
        persist_level_map(lm, conn, source_data_as_of=src, today=today)
        pytest.fail("expected StaleSourceDataError")
    except StaleSourceDataError as e:
        msg = str(e)
        assert "RUNBOOK_BACKFILL.md" in msg
        assert "daily fetcher" in msg.lower()
        assert "trading days" in msg, "should communicate the unit explicitly"
