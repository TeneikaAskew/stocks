"""The max_daily_trades cap must engage in replay too (#818).

`scripts/replay_signal_monitor.py` replaces `SignalMonitor.fire_alert`
wholesale with a capturing stub. Production increments the per-ticker fire
counter inside `fire_alert`, so the stub silently dropped it: `daily_trades`
stayed 0 for the whole replay and the cap check in `evaluate_ticker` never
engaged.

That matters beyond replay fidelity. Per Codex's review of #816, the daily cap
is currently the *only* thing bounding concurrent exposure, so a replay in
which it never binds cannot reproduce today's behaviour as a baseline for any
shadow-control analysis.
"""
import pandas as pd
import pytest

from gcp.signal_monitor import SignalMonitor
from scripts.replay_signal_monitor import make_capturing_fire_alert


def _monitor():
    m = SignalMonitor()
    m.webhook_url = ""
    return m


def _install_stub(monitor, captured):
    fn = make_capturing_fire_alert(captured, monitor)
    monitor.fire_alert = fn.__get__(monitor, type(monitor))


_SIG = {'direction': 'CALL', 'base_score': 5, 'conditions_met': ['x']}
_LATEST = {'Close': 100.0, 'Time': pd.Timestamp('2026-08-28 10:00:00')}


def _fire(monitor, ticker='SPY'):
    monitor.fire_alert(ticker, dict(_SIG), 6.0, 'strong', 0.75, 0.0,
                       dict(_LATEST))


def test_replay_fire_increments_the_daily_cap_counter():
    """Pre-fix this stayed 0 no matter how many times replay fired."""
    m = _monitor()
    captured = []
    _install_stub(m, captured)
    for _ in range(3):
        _fire(m)
    assert len(captured) == 3
    assert m.daily_trades.get('SPY') == 3, (
        "replay fires must consume daily-trade cap the way production does")


def test_replay_cap_predicate_engages_at_the_configured_cap():
    """The exact predicate evaluate_ticker uses must become True in replay."""
    m = _monitor()
    m.risk.max_daily_trades = 2
    captured = []
    _install_stub(m, captured)
    for _ in range(2):
        _fire(m)
    assert (m.daily_trades.get('SPY', 0) >= m.risk.max_daily_trades), (
        "cap gate would still not engage in replay")


def test_level_gate_suppressed_fire_does_not_consume_cap():
    """Ordering parity: production increments AFTER the level-gate return,
    so a suppressed fire must not count against the cap."""
    m = _monitor()
    m.signal_cfg.level_gate_mode = 'enforce'
    captured = []
    _install_stub(m, captured)

    def _late(_ticker, _direction):
        return 'post_t1', 'fresh'
    m._resolve_level_state = _late

    _fire(m)
    assert captured == [], "enforce mode should suppress a post_t1 fire"
    assert m.daily_trades.get('SPY', 0) == 0, (
        "a suppressed fire must not consume cap")
