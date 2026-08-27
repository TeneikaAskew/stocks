"""Tests for the playbook level-state gate (audit 2026-08-26 §15).

The pure LegStateTracker carries the resolver-parity touch semantics;
the integration tests pin the behavioral contracts: shadow mode tags the
persisted row without changing fire behavior, enforce mode suppresses
late-state fires before Discord, persist, and the daily-trades counter,
and 'off' mode never even builds trackers (no brief lookup from the bar
path).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd

from lib.strat_levels import LegStateTracker

_ET = ZoneInfo('US/Eastern')


# ── pure tracker semantics (resolver parity) ────────────────────────

def test_no_setup_when_trigger_missing():
    t = LegStateTracker(direction='call', trigger=None, t1=101.0, stop=99.0)
    t.update(200.0, 50.0)  # would sweep everything if armed
    assert t.state == 'no_setup'


def test_fresh_until_trigger_crosses():
    t = LegStateTracker(direction='call', trigger=100.0, t1=101.0, stop=99.0)
    t.update(99.9, 99.5)
    assert t.state == 'fresh'
    t.update(100.0, 99.8)
    assert t.state == 'triggered'


def test_stop_touch_before_trigger_does_not_invalidate():
    # Resolver parity: resolve_leg's stop scan starts at the trigger bar.
    # A session that trades through the call stop while the leg is still
    # dormant leaves the leg 'fresh' — matching how the §15 study (and
    # the nightly resolver) classified it.
    t = LegStateTracker(direction='call', trigger=100.0, t1=101.0, stop=99.0)
    t.update(99.5, 98.0)   # through the stop, trigger never crossed
    assert t.state == 'fresh'
    assert not t.stop_hit


def test_same_bar_sweep_lands_post_t1():
    # 64.8% of T1 hits happen in the trigger's own minute (§15 sample) —
    # one bar may cross trigger AND t1 together.
    t = LegStateTracker(direction='call', trigger=100.0, t1=100.5, stop=99.0)
    t.update(100.8, 99.9)
    assert t.state == 'post_t1'


def test_stop_after_trigger_invalidates_and_outranks_post_t1():
    t = LegStateTracker(direction='call', trigger=100.0, t1=100.5, stop=99.0)
    t.update(100.9, 100.0)   # trigger + t1
    assert t.state == 'post_t1'
    t.update(100.1, 98.9)    # stop trades after trigger
    assert t.state == 'invalidated'


def test_put_direction_mirrors():
    t = LegStateTracker(direction='put', trigger=100.0, t1=99.5, stop=101.0)
    t.update(100.8, 100.2)
    assert t.state == 'fresh'
    t.update(100.5, 99.4)    # crosses trigger and t1 downward
    assert t.state == 'post_t1'
    t.update(101.2, 100.0)   # rips back up through the put stop
    assert t.state == 'invalidated'


def test_nan_bar_is_ignored():
    t = LegStateTracker(direction='call', trigger=100.0, t1=101.0, stop=99.0)
    t.update(float('nan'), float('nan'))
    assert t.state == 'fresh'


# ── monitor integration ─────────────────────────────────────────────

_BRIEF = {
    'bias': 'CALL', 'alignment': None, 'setup_count': 4,
    'ftfc_direction': 'bullish', 'ftfc_score': 0.8, 'reason': 'aligned',
    'calls_trigger_price': 100.0, 'calls_t1_price': 100.5,
    'calls_stop_price': 99.0,
    'puts_trigger_price': 98.5, 'puts_t1_price': 98.0,
    'puts_stop_price': 100.2,
}


def _make_monitor():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    return monitor


def _rth_bars(highs_lows):
    """Bars stamped today at 10:00+ ET (naive ET, live-mode convention)."""
    base = datetime.now(_ET).replace(hour=10, minute=0, second=0,
                                     microsecond=0, tzinfo=None)
    rows = []
    for i, (hi, lo) in enumerate(highs_lows):
        rows.append({'Time': base + timedelta(minutes=i),
                     'Open': (hi + lo) / 2, 'High': hi, 'Low': lo,
                     'Close': (hi + lo) / 2, 'Volume': 1000})
    return pd.DataFrame(rows)


def _feed(monitor, ticker, highs_lows):
    with patch.object(monitor, '_resolve_brief_bias', return_value=_BRIEF):
        monitor.update_window(ticker, _rth_bars(highs_lows))


def _bar(price=680.0):
    return pd.Series({
        "Close": price, "Last": price, "RSI14": 40.0, "RVOL": 1.5,
        "VWAP": 681.0, "EMA9": 680.5, "EMA20": 681.0, "ATR14": 1.0,
        "StochRSI_K": 25.0, "Consecutive_Down": 3,
    })


def _sig(direction="CALL"):
    return {"direction": direction, "base_score": 4.0,
            "conditions_met": ["rsi_in_range", "below_vwap"]}


def test_trackers_advance_through_bar_feed():
    monitor = _make_monitor()
    _feed(monitor, 'QQQ', [(99.8, 99.5), (100.6, 99.9)])
    own, opp = monitor._resolve_level_state('QQQ', 'CALL')
    assert own == 'post_t1'       # one bar swept trigger 100.0 + t1 100.5
    assert opp == 'fresh'         # puts trigger 98.5 never touched


def test_shadow_mode_fires_and_tags_states():
    monitor = _make_monitor()
    monitor.signal_cfg.level_gate_mode = 'shadow'
    _feed(monitor, 'QQQ', [(100.6, 99.9)])
    with patch.object(monitor, '_persist_signal_alert') as mock_persist:
        monitor.fire_alert('QQQ', _sig(), 4.0, 'medium', 0.5, 0, _bar())
    assert mock_persist.called, "shadow mode must never suppress a fire"
    assert monitor._latest_level_state == 'post_t1'
    assert monitor._latest_opp_level_state == 'fresh'


def test_enforce_mode_suppresses_late_state_fire():
    monitor = _make_monitor()
    monitor.signal_cfg.level_gate_mode = 'enforce'
    _feed(monitor, 'QQQ', [(100.6, 99.9)])   # call leg -> post_t1
    before = dict(monitor.daily_trades)
    with patch.object(monitor, '_persist_signal_alert') as mock_persist:
        monitor.fire_alert('QQQ', _sig(), 4.0, 'medium', 0.5, 0, _bar())
    assert not mock_persist.called, "enforce+post_t1 must not persist"
    assert monitor.daily_trades.get('QQQ', 0) == before.get('QQQ', 0), \
        "suppressed fire must not consume the daily-trades cap"


def test_enforce_mode_passes_fresh_state_fire():
    monitor = _make_monitor()
    monitor.signal_cfg.level_gate_mode = 'enforce'
    _feed(monitor, 'QQQ', [(99.8, 99.5)])    # nothing crossed
    with patch.object(monitor, '_persist_signal_alert') as mock_persist:
        monitor.fire_alert('QQQ', _sig(), 4.0, 'medium', 0.5, 0, _bar())
    assert mock_persist.called
    assert monitor._latest_level_state == 'fresh'


def test_enforce_mode_suppresses_invalidated_put_fire():
    monitor = _make_monitor()
    monitor.signal_cfg.level_gate_mode = 'enforce'
    # puts leg: trigger 98.5 crossed, then rips up through put stop 100.2
    _feed(monitor, 'QQQ', [(98.6, 98.4), (100.4, 98.9)])
    with patch.object(monitor, '_persist_signal_alert') as mock_persist:
        monitor.fire_alert('QQQ', _sig('PUT'), 4.0, 'medium', 0.5, 0, _bar())
    assert not mock_persist.called
    assert monitor._latest_level_state == 'invalidated'


def test_off_mode_never_builds_trackers_or_tags():
    monitor = _make_monitor()
    monitor.signal_cfg.level_gate_mode = 'off'
    with patch.object(monitor, '_resolve_brief_bias') as mock_bias:
        monitor.update_window('QQQ', _rth_bars([(100.6, 99.9)]))
    assert not mock_bias.called, "'off' must not trigger brief lookups from the bar path"
    own, opp = monitor._resolve_level_state('QQQ', 'CALL')
    assert own is None and opp is None


def test_overlapping_poll_snapshot_does_not_replay_pre_trigger_bars():
    # Codex P1 on PR #799: live polls re-deliver the session's last ~100
    # bars every cycle. Re-folding a pre-trigger stop touch AFTER the
    # trigger has set would falsely flip the leg 'invalidated'. Bar 1
    # touches the call stop (99.0) pre-trigger; bar 2 crosses the
    # trigger. Re-delivering the same snapshot must leave the state as
    # the first pass computed it.
    monitor = _make_monitor()
    batch = [(99.4, 98.9),    # stop touch, leg still dormant
             (100.1, 99.9)]   # trigger crosses
    _feed(monitor, 'QQQ', batch)
    assert monitor._resolve_level_state('QQQ', 'CALL')[0] == 'triggered'
    _feed(monitor, 'QQQ', batch)          # overlapping re-delivery
    assert monitor._resolve_level_state('QQQ', 'CALL')[0] == 'triggered', \
        "re-folded pre-trigger stop touch must not invalidate the leg"


def test_forming_bar_at_watermark_still_advances_state():
    # The at-watermark bar is re-folded on purpose: the current minute's
    # bar keeps widening while it forms, and its final form may carry
    # the touch. Same Time stamp, wider range on the second delivery.
    monitor = _make_monitor()
    _feed(monitor, 'QQQ', [(99.8, 99.5)])          # forming: nothing crossed
    assert monitor._resolve_level_state('QQQ', 'CALL')[0] == 'fresh'
    _feed(monitor, 'QQQ', [(100.6, 99.4)])         # same minute, final form
    assert monitor._resolve_level_state('QQQ', 'CALL')[0] == 'post_t1'


def test_unavailable_brief_tags_none_not_no_setup():
    # Codex P2 on PR #799: a failed lookup / missing playbook row must
    # tag NULL, not 'no_setup' — 'no_setup' is reserved for a real row
    # that published no trigger for the leg.
    monitor = _make_monitor()
    unavailable = {'bias': 'UNAVAILABLE', 'alignment': None,
                   'setup_count': 0, 'ftfc_direction': None,
                   'ftfc_score': None, 'reason': 'no_brief_row'}
    with patch.object(monitor, '_resolve_brief_bias',
                      return_value=unavailable) as mock_bias:
        monitor.update_window('QQQ', _rth_bars([(100.6, 99.9)]))
        monitor.update_window('QQQ', _rth_bars([(100.8, 100.0)]))
    assert mock_bias.call_count == 1, \
        "the unavailable sentinel must not re-derive the lookup per batch"
    own, opp = monitor._resolve_level_state('QQQ', 'CALL')
    assert own is None and opp is None
    with patch.object(monitor, '_persist_signal_alert') as mock_persist:
        monitor.fire_alert('QQQ', _sig(), 4.0, 'medium', 0.5, 0, _bar())
    assert mock_persist.called, "shadow mode still fires on unavailable brief"
    assert monitor._latest_level_state is None


def test_fire_with_no_bars_seen_tags_none_not_no_setup():
    # None = "we weren't looking / trackers not built"; 'no_setup' is
    # reserved for a real playbook row with no trigger on that leg.
    monitor = _make_monitor()
    monitor.signal_cfg.level_gate_mode = 'shadow'
    with patch.object(monitor, '_persist_signal_alert') as mock_persist:
        monitor.fire_alert('QQQ', _sig(), 4.0, 'medium', 0.5, 0, _bar())
    assert mock_persist.called
    assert monitor._latest_level_state is None
    assert monitor._latest_opp_level_state is None
