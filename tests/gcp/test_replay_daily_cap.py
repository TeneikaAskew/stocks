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


# --------------------------------------------------------------------------
# Codex review of PR #934 — two defects, both reproduced before fixing.
# --------------------------------------------------------------------------

def test_rvol_enforce_below_does_not_capture_or_consume_cap():
    """Production fire_alert returns on a 'below' verdict under enforce
    BEFORE persist and before the counter — its own comment says a suppressed
    fire is "invisible to the risk caps too". The stub must match, or every
    below-threshold candidate burns cap and starves later valid signals."""
    m = _monitor()
    m.signal_cfg.rvol_gate_mode = 'enforce'
    m.signal_cfg.rvol_gate_min = 1.5
    captured = []
    _install_stub(m, captured)
    low = dict(_LATEST, RVOL=0.4)
    m.fire_alert('SPY', dict(_SIG), 6.0, 'strong', 0.75, 0.0, low)
    assert captured == [], "below-threshold fire must not be captured"
    assert m.daily_trades.get('SPY', 0) == 0, "and must not consume cap"


def test_rvol_enforce_above_still_fires_and_counts():
    m = _monitor()
    m.signal_cfg.rvol_gate_mode = 'enforce'
    m.signal_cfg.rvol_gate_min = 1.5
    captured = []
    _install_stub(m, captured)
    m.fire_alert('SPY', dict(_SIG), 6.0, 'strong', 0.75, 0.0,
                 dict(_LATEST, RVOL=2.0))
    assert len(captured) == 1 and m.daily_trades.get('SPY') == 1


def test_rvol_shadow_mode_does_not_suppress():
    """shadow is the default and must change nothing."""
    m = _monitor()
    m.signal_cfg.rvol_gate_mode = 'shadow'
    m.signal_cfg.rvol_gate_min = 1.5
    captured = []
    _install_stub(m, captured)
    m.fire_alert('SPY', dict(_SIG), 6.0, 'strong', 0.75, 0.0,
                 dict(_LATEST, RVOL=0.1))
    assert len(captured) == 1 and m.daily_trades.get('SPY') == 1


def test_multi_date_replay_rolls_the_cap_counter_over():
    """daily_trades is SESSION state — production runs one monitor per day.
    Without a rollover, date 1 exhausting the cap silently suppresses every
    later date in a --start/--end replay."""
    from scripts.replay_signal_monitor import replay_ticker
    m = _monitor()
    m.risk.max_daily_trades = 2
    captured = []
    _install_stub(m, captured)
    m.daily_trades['SPY'] = 2          # date 1 exhausted the cap

    bars = pd.DataFrame([
        {'Time': pd.Timestamp('2026-08-27 14:31:00'), 'Open': 100.0,
         'High': 100.5, 'Low': 99.5, 'Close': 100.0, 'Volume': 1000},
        {'Time': pd.Timestamp('2026-08-28 14:31:00'), 'Open': 100.0,
         'High': 100.5, 'Low': 99.5, 'Close': 100.0, 'Volume': 1000},
    ])
    replay_ticker(m, 'SPY', bars, captured)
    assert m.daily_trades.get('SPY') == 0, (
        "crossing into a new session must reset the per-day fire counter")
