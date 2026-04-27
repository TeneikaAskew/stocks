"""Unit tests for the incremental (`--since-last`) fetch path.

Three cases the resolver must handle correctly:

  1. Cold start  — no rows for ticker → 48h lookback floor
  2. Normal      — last article < 7d old → last_ts minus 30-min overlap
  3. Stale cap   — last article > 7d old → 7d floor regardless

Plus the integration shape: ``fetch_by_tickers(..., incremental=True)``
resolves a per-ticker ``time_from`` and passes it as the AV
``time_from`` query parameter when no explicit window was pinned.
The actual AV HTTP call is monkey-patched out so the test stays
hermetic.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gcp.fetchers import fetch_news_sentiment as fns


# ---------------------------------------------------------------------------
# _last_published_ts — DB read helper
# ---------------------------------------------------------------------------


def test_last_published_ts_none_on_empty(monkeypatch):
    """Cold start: empty result frame → None (caller falls back to 48h)."""
    monkeypatch.setattr(fns, "query_to_dataframe", lambda *_a, **_kw: pd.DataFrame())
    assert fns._last_published_ts("AVGO") is None


def test_last_published_ts_none_on_db_error(monkeypatch):
    """DB read fails → None (degrade to cold start, don't crash the fetch)."""
    def boom(*_a, **_kw):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(fns, "query_to_dataframe", boom)
    assert fns._last_published_ts("AVGO") is None


def test_last_published_ts_returns_max(monkeypatch):
    last = datetime(2026, 4, 27, 14, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(
        fns, "query_to_dataframe",
        lambda *_a, **_kw: pd.DataFrame({"max_ts": [last]}),
    )
    out = fns._last_published_ts("AVGO")
    assert out == last


def test_last_published_ts_naive_treated_as_utc(monkeypatch):
    """Some DB drivers return naive datetimes — must coerce to UTC."""
    naive = datetime(2026, 4, 27, 14, 30)  # no tzinfo
    monkeypatch.setattr(
        fns, "query_to_dataframe",
        lambda *_a, **_kw: pd.DataFrame({"max_ts": [naive]}),
    )
    out = fns._last_published_ts("AVGO")
    assert out is not None
    assert out.tzinfo is not None
    assert out.utcoffset() == timedelta(0)


# ---------------------------------------------------------------------------
# _resolve_incremental_time_from — three branches
# ---------------------------------------------------------------------------


def test_resolve_incremental_cold_start_uses_48h_lookback():
    now = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    out = fns._resolve_incremental_time_from("NEWTKR", now, last_ts=None)
    expected = (now - timedelta(hours=fns.COLD_START_LOOKBACK_HOURS)).strftime("%Y%m%dT%H%M")
    assert out == expected
    # 48h before 2026-04-27 12:00 UTC = 2026-04-25 12:00 UTC
    assert out == "20260425T1200"


def test_resolve_incremental_normal_subtracts_safety_overlap():
    now = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    last = datetime(2026, 4, 27, 11, 30, tzinfo=timezone.utc)  # 30min ago
    out = fns._resolve_incremental_time_from("AVGO", now, last_ts=last)
    expected = (last - timedelta(minutes=fns.SAFETY_OVERLAP_MINUTES)).strftime("%Y%m%dT%H%M")
    assert out == expected
    # 11:30 minus 30 min overlap = 11:00
    assert out == "20260427T1100"


def test_resolve_incremental_stale_caps_at_7d():
    now = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    # Last article 30 days ago — should NOT result in time_from = 30d ago.
    very_old = now - timedelta(days=30)
    out = fns._resolve_incremental_time_from("THINTKR", now, last_ts=very_old)
    expected = (now - timedelta(hours=fns.MAX_INCREMENTAL_HOURS)).strftime("%Y%m%dT%H%M")
    assert out == expected
    # 7d before 2026-04-27 12:00 = 2026-04-20 12:00
    assert out == "20260420T1200"


def test_resolve_incremental_just_under_stale_threshold_uses_normal():
    """Boundary: at 6d 23h since last, we still use normal (not the cap)."""
    now = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=6 * 24 + 23)  # 6d 23h ago
    out = fns._resolve_incremental_time_from("AVGO", now, last_ts=last)
    # Should be `last - 30min`, NOT `now - 7d`
    expected = (last - timedelta(minutes=fns.SAFETY_OVERLAP_MINUTES)).strftime("%Y%m%dT%H%M")
    assert out == expected


def test_resolve_incremental_just_over_stale_threshold_uses_cap():
    """Boundary: at 7d 1m since last, the cap kicks in."""
    now = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=fns.MAX_INCREMENTAL_HOURS, minutes=1)
    out = fns._resolve_incremental_time_from("THINTKR", now, last_ts=last)
    expected = (now - timedelta(hours=fns.MAX_INCREMENTAL_HOURS)).strftime("%Y%m%dT%H%M")
    assert out == expected


# ---------------------------------------------------------------------------
# fetch_by_tickers integration with incremental=True
# ---------------------------------------------------------------------------


def _captured_params(captured: list[dict]):
    """Return a stub for `_fetch` that records params and yields no rows."""
    def _stub(params):
        captured.append(dict(params))
        return []  # empty feed → fetch_by_tickers continues to next ticker
    return _stub


def test_fetch_by_tickers_incremental_resolves_per_ticker(monkeypatch):
    """Two tickers with different last_ts values → two distinct
    time_from query strings, one per ticker."""
    captured: list[dict] = []
    monkeypatch.setattr(fns, "_fetch", _captured_params(captured))

    # AVGO has fresh data (1h ago), IWM is cold-start.
    last_ts_map = {
        "AVGO": datetime.now(timezone.utc) - timedelta(hours=1),
        "IWM": None,
    }
    monkeypatch.setattr(
        fns, "_last_published_ts", lambda tk: last_ts_map.get(tk.upper()),
    )

    fns.fetch_by_tickers(
        ["AVGO", "IWM"], api_key="stub", limit=1000,
        incremental=True,
    )
    assert len(captured) == 2
    assert all("time_from" in c for c in captured), captured
    assert "sort" in captured[0] and captured[0]["sort"] == "EARLIEST"
    # Two different time_from strings — proves per-ticker resolution.
    assert captured[0]["time_from"] != captured[1]["time_from"]


def test_fetch_by_tickers_incremental_ignored_when_explicit_window_set(monkeypatch):
    """Explicit --time-from must override incremental — backfills are
    the caller's responsibility, not the resolver's."""
    captured: list[dict] = []
    monkeypatch.setattr(fns, "_fetch", _captured_params(captured))
    # Resolver should NOT be called even though incremental=True.
    sentinel = {"called": False}
    def trap(*_a, **_kw):
        sentinel["called"] = True
        return None
    monkeypatch.setattr(fns, "_last_published_ts", trap)

    fns.fetch_by_tickers(
        ["AVGO"], api_key="stub", limit=1000,
        time_from="20260406T0000", time_to="20260411T2359",
        incremental=True,
    )
    assert sentinel["called"] is False
    assert len(captured) == 1
    assert captured[0]["time_from"] == "20260406T0000"
    assert captured[0]["time_to"] == "20260411T2359"


def test_fetch_by_tickers_no_incremental_omits_time_from(monkeypatch):
    """Default path (incremental=False, no explicit window) must keep
    the historical behaviour: no time_from, AV returns its latest."""
    captured: list[dict] = []
    monkeypatch.setattr(fns, "_fetch", _captured_params(captured))

    fns.fetch_by_tickers(
        ["AVGO"], api_key="stub", limit=1000,
        incremental=False,
    )
    assert len(captured) == 1
    assert "time_from" not in captured[0]
    assert "time_to" not in captured[0]
    # `sort` is only added when a window is set, so it shouldn't be here.
    assert "sort" not in captured[0]
