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
    # Relative, not a fixed date: the classification now measures cursor age
    # against now, so a hardcoded timestamp would silently flip these tests
    # from 'live' to 'backfill' as it aged.
    cursor = datetime.now(timezone.utc) - timedelta(hours=20)
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


# ── window age, not just the flags (Codex round 2 on #1098) ──────────────
#
# I argued in round 1 that a cursor resume after a week of downtime is still
# the live cursor doing its job. That was wrong for the reason Codex gave:
# the label lands on the ROW, and /api/signals discloses it per row, so a
# signal reconstructed days after its bar is mislabelled whatever code path
# produced it. `--end-date` into the past makes it plainer.


def test_stale_cursor_catch_up_is_backfill(monkeypatch):
    """After a multi-day outage the cursor resume reconstructs history."""
    stale = datetime.now(timezone.utc) - timedelta(days=9)
    monkeypatch.setattr("scripts.run_historical_signals.latest_entry_time",
                        lambda *a, **k: stale)
    _, _, kind = resolve_window(_args())
    assert kind == "backfill"


def test_fresh_cursor_resume_is_still_live(monkeypatch):
    """The ordinary daily run must not be relabelled by this rule."""
    fresh = datetime.now(timezone.utc) - timedelta(hours=20)
    monkeypatch.setattr("scripts.run_historical_signals.latest_entry_time",
                        lambda *a, **k: fresh)
    _, _, kind = resolve_window(_args())
    assert kind == "live"


def test_weekend_gap_on_the_cursor_stays_live(monkeypatch):
    """A Friday cursor read on Monday is a 3-day span and still the live
    cadence; LIVE_WINDOW_DAYS exists to keep that from flipping."""
    friday = datetime.now(timezone.utc) - timedelta(days=2, hours=20)
    monkeypatch.setattr("scripts.run_historical_signals.latest_entry_time",
                        lambda *a, **k: friday)
    _, _, kind = resolve_window(_args())
    assert kind == "live"


def test_historical_end_date_on_a_fresh_cursor_is_backfill(monkeypatch):
    """`--end-date` pointing into the past makes the window historical even
    when the cursor itself is recent."""
    fresh = datetime.now(timezone.utc) - timedelta(hours=20)
    monkeypatch.setattr("scripts.run_historical_signals.latest_entry_time",
                        lambda *a, **k: fresh)
    _, _, kind = resolve_window(_args(end_date="2024-06-01"))
    assert kind == "backfill"
