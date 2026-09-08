"""Tests for SignalMonitor's replay-clock override.

The replay-clock override fixes a contamination bug: during
`scripts/replay_signal_monitor.py` execution, the monitor's
`_resolve_brief_bias` and catalyst-proximity lookups used
`datetime.now()` — i.e., real wall-clock-today, not the replay date.
For a replay against 2026-05-06 run on 2026-05-10, this meant the
brief lookup queried `premarket_analysis WHERE analysis_date = 2026-05-10`,
which is empty → `ftfc_score=None` → defaults to 0.0 → PR #379's
FTFC fix becomes architecturally inert during replay.

These tests prove the bar's timestamp drives both lookups when the
replay harness sets `monitor.replay_clock_ts`.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd

from lib.strategies.brief_bias import get_premarket_bias


_ET = ZoneInfo("America/New_York")


# ── _now() — pure clock-source override ────────────────────────────


def test_now_falls_through_to_datetime_now_when_clock_not_set():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    assert monitor.replay_clock_ts is None
    before = datetime.now()
    out = monitor._now()
    after = datetime.now()
    assert before <= out <= after


def test_now_returns_replay_clock_when_set():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    # Replay bar at 2026-05-06 14:30 UTC
    bar_ts = pd.Timestamp("2026-05-06T14:30:00", tz="UTC")
    monitor.replay_clock_ts = bar_ts
    out = monitor._now()
    assert out.year == 2026 and out.month == 5 and out.day == 6
    assert out.hour == 14 and out.minute == 30


def test_now_converts_to_requested_tz():
    """ET ≠ UTC — the conversion must produce 5/6 09:30 ET when given
    5/6 13:30 UTC (= RTH open)."""
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    monitor.replay_clock_ts = pd.Timestamp("2026-05-06T13:30:00", tz="UTC")
    et = monitor._now(_ET)
    assert et.tzinfo is not None
    # ET in May is EDT = UTC-4
    assert et.year == 2026 and et.month == 5 and et.day == 6
    assert et.hour == 9 and et.minute == 30


def test_now_treats_naive_timestamp_as_utc():
    """Some pandas Timestamps may arrive without tz; treat as UTC."""
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    monitor.replay_clock_ts = pd.Timestamp("2026-05-06T13:30:00")  # naive
    et = monitor._now(_ET)
    assert et.hour == 9 and et.minute == 30, \
        "naive timestamp should be treated as UTC then converted to ET"


# ── _resolve_brief_bias respects replay clock ──────────────────────


def test_resolve_brief_bias_uses_replay_clock_date():
    """The premarket-brief lookup must use the replay bar's date, not
    wall-clock-today. Without this fix, replay against a historical
    date queried today's (empty) brief and got ftfc_score=None → 0.0,
    silently disabling the PR #379 FTFC alignment branch."""
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    monitor._brief_bias_cache.clear()
    get_premarket_bias.cache_clear()

    # Bar from 2026-05-06 13:30 UTC = 5/6 09:30 ET
    monitor.replay_clock_ts = pd.Timestamp("2026-05-06T13:30:00", tz="UTC")

    fake_bias = {'bias': 'CALL', 'alignment': None, 'setup_count': 4,
                 'ftfc_direction': 'bullish', 'ftfc_score': 0.75,
                 'reason': 'aligned'}
    with patch('gcp.signal_monitor.get_premarket_bias',
               return_value=fake_bias) as mock_get:
        bias = monitor._resolve_brief_bias('QQQ')
    assert bias['ftfc_score'] == 0.75
    # The crucial assertion: the date passed to get_premarket_bias is 5/6,
    # NOT wall-clock-today.
    mock_get.assert_called_once()
    called_with_date = mock_get.call_args[0][1]
    assert called_with_date.isoformat() == "2026-05-06", \
        f"expected 2026-05-06 (replay bar date); got {called_with_date}"


def test_resolve_brief_bias_uses_wall_clock_when_no_replay():
    """Live behaviour must be unchanged."""
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    monitor._brief_bias_cache.clear()
    get_premarket_bias.cache_clear()
    assert monitor.replay_clock_ts is None

    fake_bias = {'bias': 'CALL', 'alignment': None, 'setup_count': 4,
                 'ftfc_direction': 'bullish', 'ftfc_score': 0.5,
                 'reason': 'aligned'}
    with patch('gcp.signal_monitor.get_premarket_bias',
               return_value=fake_bias) as mock_get:
        monitor._resolve_brief_bias('QQQ')
    mock_get.assert_called_once()
    called_with_date = mock_get.call_args[0][1]
    # Live: should be today's ET date.
    today_et = datetime.now(_ET).date()
    assert called_with_date == today_et, \
        f"live mode should use wall-clock-today ET; got {called_with_date}"


# ── replay clock can be cleared between executions ─────────────────


def test_replay_clock_can_be_cleared():
    """Setting then clearing replay_clock_ts to None restores live behaviour."""
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""

    monitor.replay_clock_ts = pd.Timestamp("2026-05-06T14:30:00", tz="UTC")
    replay_now = monitor._now()
    assert replay_now.year == 2026 and replay_now.day == 6

    monitor.replay_clock_ts = None
    live_now = monitor._now()
    assert abs((live_now - datetime.now()).total_seconds()) < 5, \
        "after clearing, _now() should return wall-clock time"


# ── catalyst proximity is keyed to the ET bar time ────────────────────

def test_catalyst_context_is_keyed_to_the_et_bar_time():
    """Internal review of #1022 (monitor round): evaluate_ticker handed
    get_catalyst_context a bare `_now()`, naive UTC in both live (the
    container clock is UTC) and replay (the bar stamp), and
    catalyst_proximity localises a naive timestamp AS ET, so every fire
    was scored against catalysts 4-5 hours later than the bar: a 10:31
    ET fire keyed on 14:31 ET, crossing every proximity window."""
    import inspect

    from gcp.signal_monitor import SignalMonitor

    m = SignalMonitor()
    m.webhook_url = ""
    m.replay_clock_ts = pd.Timestamp("2026-08-28 14:31:00")      # naive UTC bar
    ts = m._catalyst_as_of()
    assert ts == pd.Timestamp("2026-08-28 10:31:00", tz="America/New_York"), ts
    assert ts.tz is not None, "an aware timestamp cannot be re-localised as ET"
    src = inspect.getsource(SignalMonitor.evaluate_ticker)
    assert "get_catalyst_context(" in src
    call = src[src.index("get_catalyst_context("):]
    call = call[:call.index(")") + 1]
    assert "self._catalyst_as_of()" in call, call
    assert "pd.Timestamp(self._now())" not in src


def test_the_job_wrapper_advertises_the_same_date_contract_as_the_harness():
    """`gcp.signal_monitor --mode=replay` forwards --date/--start/--end to
    scripts.replay_signal_monitor unchanged, so the two help texts describe
    ONE contract. The wrapper still said UTC after the harness moved to
    Eastern (Codex on #1022): a documented 2026-09-01..2026-09-02 window
    would be read as 04:00Z-04:00Z under EDT rather than 00:00Z-00:00Z,
    silently changing which extended-hours bars a replay sees.

    The fix is the wrapper's WORDS, not a conversion: a session is an
    Eastern day (CLAUDE.md 3.9), and converting a UTC date here would put
    back the off-by-one the harness change removed."""
    import re
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    wrapper = (repo / "gcp/signal_monitor.py").read_text()
    harness = (repo / "scripts/replay_signal_monitor.py").read_text()

    block = wrapper[wrapper.index("'--start'"):wrapper.index("'--limit'")]
    assert "UTC" not in block, (
        "the wrapper still calls the replay window UTC; it is forwarded "
        "verbatim to an Eastern reader")
    assert re.search(r"Eastern", block), "the wrapper must say Eastern"
    for flag in ("--start", "--end"):
        assert re.search(rf'"{flag}", help="Eastern', harness) or \
            re.search(rf'"{flag}",\s*\n?\s*help="Eastern', harness) or \
            f'"{flag}", help="Eastern' in harness, \
            f"{flag} lost its Eastern wording in the harness"
