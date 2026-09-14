"""resolve_window decides run_kind, and only the cursor path is 'live'.

Audit 2026-09-14 (#1095) added provenance to historical_signals. The first
revision keyed it off `--force or --backfill-from`, which silently labelled
two historical paths as live: the documented `--start-date/--end-date`
window, and the 30-day bootstrap a ticker/strategy with no cursor falls
back to. Both compute signals long after the bars they describe, and
/api/signals discloses run_kind on every row, so a wrong label is served.
Caught by Codex on #1098.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

import pytest

from scripts.run_historical_signals import resolve_window


def _args(**kw):
    base = dict(symbol="IWM", strategy="momentum", start_date=None,
                end_date=None, backfill_from=None, force=False)
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.fixture
def no_cursor(monkeypatch):
    monkeypatch.setattr("scripts.run_historical_signals.latest_entry_time",
                        lambda *a, **k: None)


@pytest.fixture
def has_cursor(monkeypatch):
    cursor = datetime(2026, 9, 12, 14, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("scripts.run_historical_signals.latest_entry_time",
                        lambda *a, **k: cursor)
    return cursor


def test_cursor_resume_is_the_only_live_path(has_cursor):
    start, _, kind = resolve_window(_args())
    assert kind == "live"
    assert start == has_cursor + timedelta(minutes=1)


def test_start_date_window_is_backfill(has_cursor):
    """The regression: an explicit historical window with neither --force
    nor --backfill-from was classified 'live'."""
    _, _, kind = resolve_window(_args(start_date="2024-01-02"))
    assert kind == "backfill"


def test_first_run_bootstrap_is_backfill(no_cursor):
    """30 days of bars processed in one go is not a live cursor."""
    start, end, kind = resolve_window(_args())
    assert kind == "backfill"
    assert (end - start).days == 30


def test_backfill_from_is_backfill(has_cursor):
    _, _, kind = resolve_window(_args(backfill_from="2015-06-01"))
    assert kind == "backfill"


def test_force_is_backfill_even_on_the_cursor_path(has_cursor):
    """--force deletes the ticker's rows and reprocesses, so the cursor it
    would have resumed from is gone."""
    _, _, kind = resolve_window(_args(force=True))
    assert kind == "backfill"
