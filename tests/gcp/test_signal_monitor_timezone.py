"""Regression tests for the noon-shutdown timezone bug.

Cloud Run runs in UTC. Before the fix at gcp/signal_monitor.py:_ET,
the monitor used naive datetime.now() and compared its UTC wall-clock
time against MarketConfig.market_close_time = 16:00, which made the
container exit at 12:00 ET (= 16:00 UTC) every day.

These tests prove the fix works regardless of the host TZ.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo


def _make_monitor():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    return monitor


# Construct synthetic 'now' values in ET so the test doesn't depend on
# wall-clock time. We patch datetime.now to return these.
class _FakeDatetime:
    """Minimal replacement that accepts a tz arg like the real thing."""
    def __init__(self, fake_et):
        self._fake_et = fake_et

    def __call__(self, tz=None):
        if tz is None:
            return self._fake_et.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
        return self._fake_et.astimezone(tz)


def _patch_now(fake_et_dt):
    """Returns a context manager patching datetime.now in signal_monitor
    to return fake_et_dt converted to the requested tz."""
    fake = _FakeDatetime(fake_et_dt)

    class _PatchedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fake(tz)
    return patch('gcp.signal_monitor.datetime', _PatchedDatetime)


def test_is_market_hours_at_9_25_et_is_false():
    """9:25 ET — 5 minutes before open."""
    fake_now = datetime(2026, 5, 5, 9, 25, 0, tzinfo=ZoneInfo('America/New_York'))
    monitor = _make_monitor()
    with _patch_now(fake_now):
        assert monitor.is_market_hours() is False


def test_is_market_hours_at_9_30_et_is_true():
    fake_now = datetime(2026, 5, 5, 9, 30, 0, tzinfo=ZoneInfo('America/New_York'))
    monitor = _make_monitor()
    with _patch_now(fake_now):
        assert monitor.is_market_hours() is True


def test_is_market_hours_at_noon_et_is_true():
    """The bug: pre-fix, this returned False because UTC wall-clock 16:00
    > market_close 16:00. Now with ET tz, 12:00 ET is mid-session."""
    fake_now = datetime(2026, 5, 5, 12, 0, 0, tzinfo=ZoneInfo('America/New_York'))
    monitor = _make_monitor()
    with _patch_now(fake_now):
        assert monitor.is_market_hours() is True


def test_is_market_hours_at_15_59_et_is_true():
    fake_now = datetime(2026, 5, 5, 15, 59, 0, tzinfo=ZoneInfo('America/New_York'))
    monitor = _make_monitor()
    with _patch_now(fake_now):
        assert monitor.is_market_hours() is True


def test_is_market_hours_at_16_00_et_is_true():
    """16:00:00 ET is INCLUSIVE of market close (the comparison is <=)."""
    fake_now = datetime(2026, 5, 5, 16, 0, 0, tzinfo=ZoneInfo('America/New_York'))
    monitor = _make_monitor()
    with _patch_now(fake_now):
        assert monitor.is_market_hours() is True


def test_is_market_hours_at_16_01_et_is_false():
    fake_now = datetime(2026, 5, 5, 16, 1, 0, tzinfo=ZoneInfo('America/New_York'))
    monitor = _make_monitor()
    with _patch_now(fake_now):
        assert monitor.is_market_hours() is False


def test_is_market_hours_on_saturday_is_false():
    """Saturday at 12:00 ET — weekend gate must trump trading-hours check."""
    fake_now = datetime(2026, 5, 9, 12, 0, 0, tzinfo=ZoneInfo('America/New_York'))
    assert fake_now.weekday() == 5  # Saturday
    monitor = _make_monitor()
    with _patch_now(fake_now):
        assert monitor.is_market_hours() is False
