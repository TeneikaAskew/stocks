"""Tests for `persist_level_map` freshness guard (#TBD).

Pre-2026-05-10 the writer accepted any LevelMap and persisted it
unconditionally. The 5/6 production failure showed why this matters:
when the daily fetcher was latched at 4/27 (Track A G.P0.2 freeze),
the brief built levels off 4/27-stale data and silently wrote them
into rows stamped `as_of=5/6`. Every downstream consumer
(signal_monitor, insight pipeline, dashboard) then trusted the
poisoned level cache.

These tests lock in the v2 contract:
  1. None source_data_as_of → write succeeds (back-compat for legacy
     callers; transitional only).
  2. Fresh source_data_as_of (within max_age_days) → write succeeds,
     column populated.
  3. Stale source_data_as_of (> max_age_days) → StaleSourceDataError
     raised, no write executed.
  4. tz-aware vs tz-naive timestamps both work.
  5. The new `source_data_as_of` parameter is bound into every row.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from lib.strat_levels import (
    LevelMap, StratLevel,
    persist_level_map, StaleSourceDataError,
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
    # source_data_as_of (last column) is None on every row
    for row in rows:
        assert row[-1] is None


# ── 2) Fresh source → write succeeds, column populated ────────────────


def test_persist_with_fresh_source_writes_and_populates_column():
    """Source data 1 day behind today → within default 2-day threshold."""
    lm = _level_map()
    conn, cur = _mock_conn()
    today = datetime(2026, 5, 10, 13, 30, tzinfo=timezone.utc)
    src = today - timedelta(hours=22)  # ~1 day ago — fresh
    n = persist_level_map(lm, conn, source_data_as_of=src, today=today)
    assert n == 2
    assert cur.executemany.called
    rows = cur.executemany.call_args[0][1]
    for row in rows:
        assert row[-1] == src


# ── 3) Stale source → raises, no write ────────────────────────────────


def test_persist_with_stale_source_raises_and_does_not_write():
    """Source data 9 days behind today (the 5/6 production scenario)
    → StaleSourceDataError raised, executemany NOT called."""
    lm = _level_map()
    conn, cur = _mock_conn()
    today = datetime(2026, 5, 10, 13, 30, tzinfo=timezone.utc)
    src = today - timedelta(days=9)  # the 5/6 production gap (4/27)
    with pytest.raises(StaleSourceDataError, match="9.0 days behind"):
        persist_level_map(lm, conn, source_data_as_of=src, today=today)
    assert not cur.executemany.called, (
        "executemany must NOT be called when source is stale — the "
        "bug pre-fix was that the write happened anyway"
    )


def test_persist_at_threshold_boundary():
    """Exactly max_age_days behind → still allowed (inclusive)."""
    lm = _level_map()
    conn, cur = _mock_conn()
    today = datetime(2026, 5, 10, 13, 30, tzinfo=timezone.utc)
    src = today - timedelta(days=2)  # exactly 2 days
    n = persist_level_map(lm, conn, source_data_as_of=src,
                          max_age_days=2, today=today)
    assert n == 2  # at threshold → allowed


def test_persist_just_past_threshold_raises():
    """A hair past max_age_days → refused."""
    lm = _level_map()
    conn, cur = _mock_conn()
    today = datetime(2026, 5, 10, 13, 30, tzinfo=timezone.utc)
    src = today - timedelta(days=2, hours=1)  # 2.04 days
    with pytest.raises(StaleSourceDataError):
        persist_level_map(lm, conn, source_data_as_of=src,
                          max_age_days=2, today=today)


# ── 4) tz handling ────────────────────────────────────────────────────


def test_persist_naive_source_treated_as_utc():
    """Naive datetime is treated as UTC (consistent with how
    market_data_daily.date is stored as naive UTC date)."""
    lm = _level_map()
    conn, cur = _mock_conn()
    today = datetime(2026, 5, 10, 13, 30, tzinfo=timezone.utc)
    src = pd.Timestamp("2026-05-09 23:00")  # naive
    n = persist_level_map(lm, conn, source_data_as_of=src, today=today)
    assert n == 2


def test_persist_pandas_timestamp_source_works():
    """pandas Timestamp (which is what df.index.max() returns) → works."""
    lm = _level_map()
    conn, cur = _mock_conn()
    today = pd.Timestamp("2026-05-10 13:30:00", tz="UTC")
    src = pd.Timestamp("2026-05-09 23:00:00", tz="UTC")
    n = persist_level_map(lm, conn, source_data_as_of=src, today=today)
    assert n == 2


# ── 5) Stricter caller can tighten the threshold ──────────────────────


def test_persist_stricter_caller_can_lower_max_age_days():
    """A caller that wants weekday-strict freshness can pass
    max_age_days=1; weekend brief still has the default of 2."""
    lm = _level_map()
    conn, cur = _mock_conn()
    today = datetime(2026, 5, 10, 13, 30, tzinfo=timezone.utc)
    src = today - timedelta(days=1, hours=12)  # 1.5 days
    # default max_age_days=2 → would allow
    n = persist_level_map(lm, conn, source_data_as_of=src,
                          max_age_days=2, today=today)
    assert n == 2
    # stricter caller passes max_age_days=1 → refused
    with pytest.raises(StaleSourceDataError):
        persist_level_map(lm, conn, source_data_as_of=src,
                          max_age_days=1, today=today)


# ── 6) Empty level map short-circuits before freshness check ──────────


def test_persist_empty_level_map_short_circuits():
    """No levels → return 0 without raising even if source is stale."""
    lm = LevelMap(ticker="SPY", as_of="2026-05-10", current_price=720.0,
                   levels=[], pmg_zones=[])
    conn, cur = _mock_conn()
    today = datetime(2026, 5, 10, 13, 30, tzinfo=timezone.utc)
    src = today - timedelta(days=30)  # very stale
    n = persist_level_map(lm, conn, source_data_as_of=src, today=today)
    assert n == 0
    assert not cur.executemany.called


# ── 7) Error message points at the runbook ────────────────────────────


def test_stale_error_message_references_runbook():
    """Operator hint: the error tells you where to look."""
    lm = _level_map()
    conn, cur = _mock_conn()
    today = datetime(2026, 5, 10, 13, 30, tzinfo=timezone.utc)
    src = today - timedelta(days=10)
    try:
        persist_level_map(lm, conn, source_data_as_of=src, today=today)
        pytest.fail("expected StaleSourceDataError")
    except StaleSourceDataError as e:
        msg = str(e)
        assert "RUNBOOK_BACKFILL.md" in msg
        assert "daily fetcher" in msg.lower()
