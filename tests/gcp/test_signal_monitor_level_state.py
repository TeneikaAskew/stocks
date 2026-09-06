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
from unittest.mock import MagicMock, patch
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


def test_gap_through_open_is_post_t1_open():
    # Audit §16.1: the opening bar OPENED past the trigger and cleared T1
    # — price never traded on the near side (2026-08-27 QQQ). Tagged
    # distinctly so the two routes into post_t1 are separable in shadow
    # data; enforce still suppresses both (see the enforce test).
    t = LegStateTracker(direction='call', trigger=100.0, t1=100.5, stop=99.0)
    t.update(100.8, 100.2, opening_price=100.6, bar_key='09:30')
    assert t.state == 'post_t1_open'
    assert t.opened_through


def test_first_minute_rally_is_not_a_gap_through():
    # Codex review (PR #803): a call that OPENS BELOW the trigger and
    # rallies through both inside the 09:30 minute is intraday
    # progression that merely happened in minute one. Keying on the bar
    # high alone conflated the two; the open price separates them.
    t = LegStateTracker(direction='call', trigger=100.0, t1=100.5, stop=99.0)
    t.update(100.8, 99.4, opening_price=99.5, bar_key='09:30')
    assert t.state == 'post_t1'
    assert not t.opened_through


def test_put_gap_through_mirrors():
    t = LegStateTracker(direction='put', trigger=100.0, t1=99.5, stop=101.0)
    t.update(99.8, 99.4, opening_price=99.9, bar_key='09:30')
    assert t.state == 'post_t1_open'
    assert t.opened_through


def test_put_first_minute_selloff_is_not_a_gap_through():
    t = LegStateTracker(direction='put', trigger=100.0, t1=99.5, stop=101.0)
    t.update(100.6, 99.4, opening_price=100.5, bar_key='09:30')
    assert t.state == 'post_t1'
    assert not t.opened_through


def test_redelivered_opening_snapshot_keeps_the_gap_through_tag():
    # Codex review (PR #803): the live monitor re-folds the still-forming
    # watermark bar every poll. A 09:30 snapshot crossing only the
    # trigger, then a later 09:30 snapshot reaching T1, must still be ONE
    # bar — otherwise the tag depends on poll timing and live diverges
    # from replay.
    t = LegStateTracker(direction='call', trigger=100.0, t1=100.5, stop=99.0)
    t.update(100.2, 100.1, opening_price=100.1, bar_key='09:30')
    assert t.state == 'triggered'
    t.update(100.8, 100.1, opening_price=100.1, bar_key='09:30')
    assert t.state == 'post_t1_open', "re-delivered snapshot is not a new bar"
    assert t.opened_through


def test_new_bar_key_ends_the_opening_bar():
    t = LegStateTracker(direction='call', trigger=100.0, t1=100.5, stop=99.0)
    t.update(100.2, 100.1, opening_price=100.1, bar_key='09:30')
    t.update(100.8, 100.1, opening_price=100.3, bar_key='09:31')
    assert t.state == 'post_t1'
    assert not t.opened_through


def test_missing_opening_price_never_guesses_gap_through():
    # Without the open we cannot prove a gap-through, so the leg reports
    # the conservative plain post_t1 rather than a guess.
    t = LegStateTracker(direction='call', trigger=100.0, t1=100.5, stop=99.0)
    t.update(100.8, 99.9, bar_key='09:30')
    assert t.state == 'post_t1'
    assert not t.opened_through


def test_opened_through_still_invalidates_on_stop():
    t = LegStateTracker(direction='call', trigger=100.0, t1=100.5, stop=99.0)
    t.update(100.8, 100.2, opening_price=100.6, bar_key='09:30')
    assert t.state == 'post_t1_open'
    t.update(100.0, 98.9, opening_price=100.0, bar_key='09:31')
    assert t.state == 'invalidated'


def test_stop_after_trigger_invalidates_and_outranks_post_t1():
    t = LegStateTracker(direction='call', trigger=100.0, t1=100.5, stop=99.0)
    t.update(99.9, 99.6, opening_price=99.7, bar_key='09:30')
    t.update(100.9, 100.0, opening_price=99.9, bar_key='09:31')
    assert t.state == 'post_t1'
    t.update(100.1, 98.9, opening_price=100.5, bar_key='09:32')
    assert t.state == 'invalidated'


def test_put_direction_mirrors():
    t = LegStateTracker(direction='put', trigger=100.0, t1=99.5, stop=101.0)
    t.update(100.8, 100.2, opening_price=100.6, bar_key='09:30')
    assert t.state == 'fresh'
    t.update(100.5, 99.4, opening_price=100.3, bar_key='09:31')
    assert t.state == 'post_t1'
    t.update(101.2, 100.0, opening_price=99.6, bar_key='09:32')
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
    assert own == 'post_t1'       # bar 2 swept trigger 100.0 + t1 100.5
    assert opp == 'fresh'         # puts trigger 98.5 never touched


def test_shadow_mode_fires_and_tags_states():
    monitor = _make_monitor()
    monitor.signal_cfg.level_gate_mode = 'shadow'
    _feed(monitor, 'QQQ', [(99.8, 99.5), (100.6, 99.9)])
    with patch.object(monitor, '_persist_signal_alert') as mock_persist:
        monitor.fire_alert('QQQ', _sig(), 4.0, 'medium', 0.5, 0, _bar())
    assert mock_persist.called, "shadow mode must never suppress a fire"
    assert monitor._latest_level_state == 'post_t1'
    assert monitor._latest_opp_level_state == 'fresh'


def test_enforce_mode_suppresses_late_state_fire():
    monitor = _make_monitor()
    monitor.signal_cfg.level_gate_mode = 'enforce'
    # leading bar first, so T1 is reached by intraday progression rather
    # than the opening print -> plain 'post_t1', which enforce targets.
    _feed(monitor, 'QQQ', [(99.8, 99.5), (100.6, 99.9)])
    before = dict(monitor.daily_trades)
    with patch.object(monitor, '_persist_signal_alert') as mock_persist:
        monitor.fire_alert('QQQ', _sig(), 4.0, 'medium', 0.5, 0, _bar())
    assert not mock_persist.called, "enforce+post_t1 must not persist"
    assert monitor.daily_trades.get('QQQ', 0) == before.get('QQQ', 0), \
        "suppressed fire must not consume the daily-trades cap"


def test_enforce_mode_still_suppresses_gap_through_open():
    # Audit §16.1: the gap-through route is tagged separately for
    # measurement, but enforce still suppresses it. 2026-08-27 was a live
    # counterexample (n=5 winners); Jun-Aug has n=197 of these with fwd30
    # -0.077% (t=-2.81), and carving them out turns the historical result
    # from +8.20pct back to -0.70pct. The tag exists so the question can
    # be reopened on live data — not so one session can decide it.
    monitor = _make_monitor()
    monitor.signal_cfg.level_gate_mode = 'enforce'
    # opens at 100.4 (mid of 100.6/100.2), above the 100.0 trigger, and
    # the same bar clears T1 100.5 -> a genuine gap-through.
    _feed(monitor, 'QQQ', [(100.6, 100.2)])
    with patch.object(monitor, '_persist_signal_alert') as mock_persist:
        monitor.fire_alert('QQQ', _sig(), 4.0, 'medium', 0.5, 0, _bar())
    assert not mock_persist.called, \
        "enforce must still suppress the gap-through route (n=191, t=-3.01)"
    assert monitor._latest_level_state == 'post_t1_open', \
        "but the route must be tagged distinctly so it can be re-evaluated"


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
    # _rth_bars synthesises Open as the mid of high/low, so (100.6, 99.2)
    # opens at 99.9 — below the 100.0 trigger, and the 99.2 low stays
    # above the 99.0 stop. The final state is therefore plain post_t1:
    # not a gap-through, not invalidated.
    monitor = _make_monitor()
    _feed(monitor, 'QQQ', [(99.8, 99.5)])          # forming: nothing crossed
    assert monitor._resolve_level_state('QQQ', 'CALL')[0] == 'fresh'
    _feed(monitor, 'QQQ', [(100.6, 99.2)])         # same minute, final form
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


# ── fire spacing measurement (audit §16.3) ──────────────────────────

def test_fire_seq_and_spacing_are_recorded():
    """91% of ticker-days burn the 5-fire cap in ~17 minutes (§16.3).
    These columns measure that; no rule reads them."""
    monitor = _make_monitor()
    monitor.signal_cfg.level_gate_mode = 'off'
    captured = []
    with patch.object(monitor, '_persist_signal_alert',
                      side_effect=lambda *a, **k: captured.append(
                          (monitor.daily_trades.get('QQQ', 0) + 1,
                           monitor._last_fire_ts.get('QQQ')))):
        monitor.fire_alert('QQQ', _sig(), 4.0, 'medium', 0.5, 0, _bar())
        monitor.fire_alert('QQQ', _sig(), 4.0, 'medium', 0.5, 0, _bar())
    assert [c[0] for c in captured] == [1, 2], "seq must advance per fire"


def test_minutes_since_prev_fire_is_none_on_first_fire():
    monitor = _make_monitor()
    assert monitor._minutes_since_prev_fire('SPY') is None
    second = monitor._minutes_since_prev_fire('SPY')
    assert second is not None and second >= 0.0


def test_fire_spacing_is_tracked_per_ticker():
    monitor = _make_monitor()
    assert monitor._minutes_since_prev_fire('SPY') is None
    assert monitor._minutes_since_prev_fire('QQQ') is None, \
        "each ticker's clock is independent"
    assert monitor._minutes_since_prev_fire('SPY') is not None


# ── Put-side 9:31 re-anchor (audit §15.5) ──────────────────────────


def _level_map(prices):
    """A LevelMap carrying only structural levels at the given prices."""
    from lib.strat_levels import LevelMap, StratLevel
    levels = [StratLevel(name=n, price=p, timeframe='daily', level_type='high')
              for n, p in prices.items()]
    return LevelMap(
        ticker='QQQ', as_of='2026-08-28T09:31:00-04:00',
        current_price=100.0, levels=levels, pmg_zones=[],
        calls_trigger=None, puts_trigger=None,
        room_to_run_up=0.0, room_to_run_down=0.0,
        call_levels=[], put_levels=[],
    )


def _feed_reanchor(monitor, ticker, highs_lows, level_map, mode='shadow'):
    monitor.signal_cfg.put_reanchor_mode = mode
    monitor.level_maps[ticker] = level_map
    with patch.object(monitor, '_resolve_brief_bias', return_value=_BRIEF), \
         patch.object(monitor, '_persist_put_reanchor') as persist:
        monitor.update_window(ticker, _rth_bars(highs_lows))
    return persist


def test_reanchor_picks_nearest_structural_level_below_the_open():
    """The re-anchored put trigger is the nearest fresh structural level BELOW
    the session open — not the 8:31-anchored one from the brief."""
    monitor = _make_monitor()
    # Open of the first bar is the mid of (100.6, 99.4) = 100.0.
    lm = _level_map({'PDL': 99.6, 'PWL': 98.5, 'PDH': 101.0})
    _feed_reanchor(monitor, 'QQQ', [(100.6, 99.4)], lm)
    r = monitor.leg_trackers['QQQ']['reanchor']
    assert r is not None
    assert r['open'] == 100.0
    assert r['trigger'] == 99.6        # nearest below the OPEN, not 98.5
    assert r['trigger_name'] == 'PDL'
    assert r['t1'] == 98.5             # next level down becomes T1
    assert r['stop'] == 101.0          # opposite-side fresh level


def test_shadow_mode_leaves_the_published_put_leg_driving_the_tracker():
    """Shadow computes and persists the counterfactual but must not change
    what the monitor actually tracks — otherwise the comparison is against a
    leg that already moved."""
    monitor = _make_monitor()
    lm = _level_map({'PDL': 99.6, 'PWL': 98.5, 'PDH': 101.0})
    persist = _feed_reanchor(monitor, 'QQQ', [(100.6, 99.4)], lm, mode='shadow')
    assert persist.called, "shadow still records the measurement"
    # Tracker keeps the BRIEF's put trigger (98.5), not the re-anchor (99.6).
    assert monitor.leg_trackers['QQQ']['put'].trigger == 98.5


def test_enforce_mode_swaps_the_put_leg_only():
    """Enforce moves the put leg to the re-anchored trigger. Calls are a wash
    in the study (t=+0.17) and must be left alone."""
    monitor = _make_monitor()
    lm = _level_map({'PDL': 99.6, 'PWL': 98.5, 'PDH': 101.0})
    _feed_reanchor(monitor, 'QQQ', [(100.6, 99.4)], lm, mode='enforce')
    assert monitor.leg_trackers['QQQ']['put'].trigger == 99.6
    assert monitor.leg_trackers['QQQ']['put'].t1 == 98.5
    assert monitor.leg_trackers['QQQ']['put'].stop == 101.0
    # CALL leg untouched — still the brief's published values.
    assert monitor.leg_trackers['QQQ']['call'].trigger == 100.0
    assert monitor.leg_trackers['QQQ']['call'].t1 == 100.5


def test_off_mode_computes_nothing():
    monitor = _make_monitor()
    lm = _level_map({'PDL': 99.6, 'PWL': 98.5, 'PDH': 101.0})
    persist = _feed_reanchor(monitor, 'QQQ', [(100.6, 99.4)], lm, mode='off')
    assert monitor.leg_trackers['QQQ']['reanchor'] is None
    assert not persist.called
    assert monitor.leg_trackers['QQQ']['put'].trigger == 98.5


def test_no_level_map_yields_none_not_the_published_trigger():
    """Rule 3.7: 'could not compute' must persist as NULL, never as a copy of
    the published leg — that would make the shadow comparison compare the 8:31
    leg against itself and manufacture a null result."""
    monitor = _make_monitor()
    monitor.signal_cfg.put_reanchor_mode = 'shadow'
    monitor.level_maps['QQQ'] = None
    with patch.object(monitor, '_resolve_brief_bias', return_value=_BRIEF), \
         patch.object(monitor, '_persist_put_reanchor') as persist:
        monitor.update_window('QQQ', _rth_bars([(100.6, 99.4)]))
    assert monitor.leg_trackers['QQQ']['reanchor'] is None
    assert not persist.called


def test_no_level_below_the_open_yields_none():
    """A gap-down open that leaves every structural level ABOVE it has no put
    trigger to re-anchor to; that is NULL, not the nearest level above."""
    monitor = _make_monitor()
    lm = _level_map({'PDH': 101.0, 'PWH': 102.0})
    persist = _feed_reanchor(monitor, 'QQQ', [(100.6, 99.4)], lm)
    assert monitor.leg_trackers['QQQ']['reanchor'] is None
    assert not persist.called


def test_reanchor_failure_does_not_change_what_the_monitor_tracks():
    """A broken SHADOW measurement must never alter live behavior."""
    monitor = _make_monitor()
    monitor.signal_cfg.put_reanchor_mode = 'enforce'
    monitor.level_maps['QQQ'] = _level_map({'PDL': 99.6, 'PDH': 101.0})
    with patch.object(monitor, '_resolve_brief_bias', return_value=_BRIEF), \
         patch('gcp.signal_monitor.reanchor_triggers',
               side_effect=RuntimeError("boom")):
        monitor.update_window('QQQ', _rth_bars([(100.6, 99.4)]))
    assert monitor.leg_trackers['QQQ']['reanchor'] is None
    # Falls back to the published leg rather than dropping the put tracker.
    assert monitor.leg_trackers['QQQ']['put'].trigger == 98.5


# ── Declared-but-unenforced risk controls (review T5) ──────────────


def test_risk_shadow_counts_concurrent_positions_and_marks_open_pnl():
    """max_concurrent_positions (=1) is never read by the live monitor. This
    records what it WOULD have blocked, plus the mark-to-market P&L a
    daily_loss_limit would need in order to bind intraday."""
    monitor = _make_monitor()
    monitor.risk.max_concurrent_positions = 1
    monitor.active_positions['QQQ'] = [
        {'ticker': 'QQQ', 'direction': 'CALL', 'entry_price': 100.0, 'size': 0.10},
        {'ticker': 'QQQ', 'direction': 'PUT', 'entry_price': 100.0, 'size': 0.10},
    ]
    out = monitor._risk_control_shadow('QQQ', 99.0)
    assert out['concurrent_positions'] == 2
    assert out['would_block_concurrent'] is True
    # CALL -1% and PUT +1%, both sized 0.10 → net 0.0 mark-to-market.
    assert abs(out['open_mtm_pnl']) < 1e-9


def test_risk_shadow_mtm_sees_a_drawdown_realized_pnl_cannot():
    """The live daily_loss_limit check reads realized P&L only, which stays
    0.0 until a position exits. The mark-to-market view is what would actually
    bind — this pins that difference."""
    monitor = _make_monitor()
    monitor.risk.daily_loss_limit = -0.02
    monitor.daily_pnl['QQQ'] = 0.0            # nothing has exited yet
    monitor.active_positions['QQQ'] = [
        {'ticker': 'QQQ', 'direction': 'CALL', 'entry_price': 100.0, 'size': 1.0},
    ]
    out = monitor._risk_control_shadow('QQQ', 97.0)   # -3% open
    assert out['realized_pnl'] == 0.0
    assert out['would_block_mtm_loss'] is True, \
        "a -3% open drawdown must trip a -2% limit the realized check misses"
    assert abs(out['total_mtm_pnl'] - (-0.03)) < 1e-9


def test_risk_shadow_is_measurement_only():
    """No control is enforced. A fire that both controls would block must
    still be recorded as a fire."""
    monitor = _make_monitor()
    monitor.risk.max_concurrent_positions = 1
    monitor.active_positions['QQQ'] = [
        {'ticker': 'QQQ', 'direction': 'CALL', 'entry_price': 100.0, 'size': 1.0},
    ]
    out = monitor._risk_control_shadow('QQQ', 97.0)
    assert out['would_block_concurrent'] and out['would_block_mtm_loss']
    # The helper reports; it must not mutate any live state.
    assert len(monitor.active_positions['QQQ']) == 1
    assert monitor.daily_pnl.get('QQQ', 0.0) == 0.0


def test_risk_shadow_skips_unusable_marks_instead_of_scoring_them_zero():
    """Rule 3.7: a position with no usable entry/mark is skipped and logged,
    never folded in as a fabricated 0% leg."""
    monitor = _make_monitor()
    monitor.active_positions['QQQ'] = [
        {'ticker': 'QQQ', 'direction': 'CALL', 'entry_price': 0.0, 'size': 1.0},
        {'ticker': 'QQQ', 'direction': 'CALL', 'entry_price': 100.0, 'size': 1.0},
    ]
    out = monitor._risk_control_shadow('QQQ', 102.0)
    assert out['concurrent_positions'] == 2      # still counted for the cap
    assert abs(out['open_mtm_pnl'] - 0.02) < 1e-9  # only the usable leg marked


def test_risk_shadow_empty_book_is_zero_not_none():
    monitor = _make_monitor()
    out = monitor._risk_control_shadow('QQQ', 100.0)
    assert out['concurrent_positions'] == 0
    assert out['open_mtm_pnl'] == 0.0
    assert out['would_block_mtm_loss'] is False


# ── Codex review fixes on PR #810 ──────────────────────────────────


def test_reanchor_refreshes_level_map_on_first_poll():
    """Codex P1: run_loop calls update_window BEFORE evaluate_ticker, and
    evaluate_ticker holds the only lazy refresh_level_map call. So on the first
    RTH poll the map is None — and since the tracker is stamped with today's
    date regardless, the init block never runs again. That made the re-anchor a
    permanent no-op in live sessions.

    The map must now be refreshed on demand so the FIRST poll produces a
    re-anchor, using that poll's opening bar.
    """
    monitor = _make_monitor()
    monitor.signal_cfg.put_reanchor_mode = 'shadow'
    monitor.level_maps['QQQ'] = None          # the real first-poll state
    lm = _level_map({'PDL': 99.6, 'PWL': 98.5, 'PDH': 101.0})

    def _fake_refresh(ticker):
        monitor.level_maps[ticker] = lm

    with patch.object(monitor, '_resolve_brief_bias', return_value=_BRIEF), \
         patch.object(monitor, 'refresh_level_map', side_effect=_fake_refresh) as refresh, \
         patch.object(monitor, '_persist_put_reanchor'):
        monitor.update_window('QQQ', _rth_bars([(100.6, 99.4)]))

    assert refresh.called, "must refresh the map rather than give up on poll 1"
    r = monitor.leg_trackers['QQQ']['reanchor']
    assert r is not None, "the re-anchor must not be a permanent no-op"
    assert r['trigger'] == 99.6


def test_reanchor_gives_up_when_refresh_cannot_produce_a_map():
    """A refresh that leaves the map None (empty daily df) still yields NULL —
    it must not loop or fabricate."""
    monitor = _make_monitor()
    monitor.signal_cfg.put_reanchor_mode = 'shadow'
    monitor.level_maps['QQQ'] = None
    with patch.object(monitor, '_resolve_brief_bias', return_value=_BRIEF), \
         patch.object(monitor, 'refresh_level_map') as refresh, \
         patch.object(monitor, '_persist_put_reanchor') as persist:
        monitor.update_window('QQQ', _rth_bars([(100.6, 99.4)]))
    assert refresh.call_count == 1, "one attempt, not a retry loop"
    assert monitor.leg_trackers['QQQ']['reanchor'] is None
    assert not persist.called


def test_reanchor_applies_the_briefs_atr_staleness_filter():
    """Codex P2: the brief builds its playbook with build_level_map(atr=...),
    which drops levels beyond 3xATR. Re-anchoring without that filter lets the
    shadow leg select a stale trigger the brief deliberately excluded.

    PDL sits 0.4 below the 100.0 open; with ATR=0.05 the 3xATR window is 0.15,
    so PDL is stale and must NOT become the re-anchored trigger.
    """
    monitor = _make_monitor()
    monitor.signal_cfg.put_reanchor_mode = 'shadow'
    monitor.level_maps['QQQ'] = _level_map({'PDL': 99.6, 'PDH': 101.0})
    monitor.level_map_atr['QQQ'] = 0.05
    with patch.object(monitor, '_resolve_brief_bias', return_value=_BRIEF), \
         patch.object(monitor, '_persist_put_reanchor'):
        monitor.update_window('QQQ', _rth_bars([(100.6, 99.4)]))
    assert monitor.leg_trackers['QQQ']['reanchor'] is None, \
        "a level beyond 3xATR must not be re-anchored onto"


def test_reanchor_keeps_a_level_inside_the_atr_window():
    """Same geometry, a realistic ATR — the level is fresh and is selected.
    Pins that the filter is applied, not that it rejects everything."""
    monitor = _make_monitor()
    monitor.signal_cfg.put_reanchor_mode = 'shadow'
    monitor.level_maps['QQQ'] = _level_map({'PDL': 99.6, 'PDH': 101.0})
    monitor.level_map_atr['QQQ'] = 2.0        # 3xATR = 6.0, PDL is 0.4 away
    with patch.object(monitor, '_resolve_brief_bias', return_value=_BRIEF), \
         patch.object(monitor, '_persist_put_reanchor'):
        monitor.update_window('QQQ', _rth_bars([(100.6, 99.4)]))
    r = monitor.leg_trackers['QQQ']['reanchor']
    assert r is not None and r['trigger'] == 99.6


def _daily_df(atr_values):
    """Minimal daily frame shaped like DataLoader.load_daily output."""
    n = len(atr_values)
    base = datetime(2026, 8, 20)
    return pd.DataFrame({
        'Time': [base + timedelta(days=i) for i in range(n)],
        'Open': [100.0] * n, 'High': [101.0] * n,
        'Low': [99.0] * n, 'Close': [100.0] * n,
        'ATR14': atr_values,
    })


def _capture_atr(monitor, ticker, daily):
    """Run refresh_level_map against a stubbed loader and return the ATR it kept."""
    loader = MagicMock()
    loader.load_daily.return_value = daily
    with patch('lib.data_loader.DataLoader', return_value=loader), \
         patch('lib.strat_levels.build_level_map', return_value=_level_map({'PDL': 99.6})):
        monitor.refresh_level_map(ticker)
    return monitor.level_map_atr.get(ticker)


def test_atr_comes_from_the_latest_daily_row_only():
    """Codex P2 on #811: the brief takes atr14 from the LATEST row
    (`_safe_float(latest.get('ATR14'))`) and disables the ATR axis when it is
    missing. Falling back to an older row via dropna().iloc[-1] would apply a
    staleness filter the published playbook did not, so the re-anchor could
    reject levels the brief accepted — the same non-equivalence inverted.
    """
    monitor = _make_monitor()
    # Latest row's ATR is missing; an older row has one. Must yield None.
    assert _capture_atr(monitor, 'QQQ', _daily_df([2.0, 2.1, float('nan')])) is None
    # Latest row usable -> that value, not an earlier one.
    monitor2 = _make_monitor()
    assert _capture_atr(monitor2, 'QQQ', _daily_df([2.0, 2.1, 3.5])) == 3.5


def test_non_positive_latest_atr_is_treated_as_unavailable():
    monitor = _make_monitor()
    assert _capture_atr(monitor, 'QQQ', _daily_df([2.0, 0.0])) is None
