"""Integration tests for the exit-watcher in gcp/signal_monitor.py.

Replaces the 4-hour-noon-shutdown / no-exit-alerts gap. These tests
exercise the *real* SignalMonitor methods (not Python replicas of the
trigger logic) with mocked Discord + Cloud SQL deps.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


def _make_monitor():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""  # silence Discord
    return monitor


def _bar(close, rsi):
    return pd.Series({
        "Close": close, "Last": close,
        "RSI14": rsi, "RSI14_W": rsi,
        "VWAP": close, "EMA9": close, "EMA20": close,
        "StochRSI_K": 50.0,
        "Price_vs_VWAP": 0.0, "Price_vs_EMA9": 0.0, "Price_vs_EMA20": 0.0,
        "Consecutive_Up": 0, "Consecutive_Down": 0,
        "RVOL": 1.0, "ATR14": 1.0,
        "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
    })


def _seed_position(monitor, ticker, direction, entry_price, target_price,
                   time_stop_minutes=30, alert_ts=None, score=4.0,
                   strength='medium'):
    monitor.active_positions.setdefault(ticker, []).append({
        'ticker': ticker,
        'alert_ts': alert_ts or datetime.utcnow() - timedelta(minutes=5),
        'direction': direction,
        'entry_price': entry_price,
        'target_price': target_price,
        'time_stop_minutes': time_stop_minutes,
        'score': score,
        'strength': strength,
    })


# ── _check_exits behavior ───────────────────────────────────────────

def test_check_exits_noop_when_no_positions():
    monitor = _make_monitor()
    # Should not raise
    monitor._check_exits('QQQ', _bar(680.0, 50.0), 680.0)
    assert monitor.active_positions['QQQ'] == []


def test_check_exits_call_target_hit_removes_position():
    monitor = _make_monitor()
    _seed_position(monitor, 'QQQ', 'CALL', entry_price=677.63,
                   target_price=679.66)
    with patch.object(monitor, '_fire_exit_alert') as mock_fire, \
         patch.object(monitor, '_persist_exit') as mock_persist:
        monitor._check_exits('QQQ', _bar(679.70, 50.0), 679.70)
    assert mock_fire.called, "exit alert MUST fire when CALL target hit"
    assert mock_persist.called, "exit MUST persist when CALL target hit"
    args, _ = mock_fire.call_args
    assert args[2] == 'target_hit', f"expected target_hit, got {args[2]}"
    assert monitor.active_positions['QQQ'] == [], \
        "position MUST be removed after target hit"


def test_check_exits_put_target_hit():
    monitor = _make_monitor()
    _seed_position(monitor, 'QQQ', 'PUT', entry_price=678.00,
                   target_price=675.00, time_stop_minutes=35)
    with patch.object(monitor, '_fire_exit_alert') as mock_fire, \
         patch.object(monitor, '_persist_exit'):
        monitor._check_exits('QQQ', _bar(674.50, 50.0), 674.50)
    args, _ = mock_fire.call_args
    assert args[2] == 'target_hit'


def test_check_exits_call_just_under_target_does_not_fire():
    monitor = _make_monitor()
    _seed_position(monitor, 'QQQ', 'CALL', entry_price=677.63,
                   target_price=679.66)
    with patch.object(monitor, '_fire_exit_alert') as mock_fire:
        monitor._check_exits('QQQ', _bar(679.50, 50.0), 679.50)
    assert not mock_fire.called, \
        "must NOT fire when 14 cents short of target"
    assert len(monitor.active_positions['QQQ']) == 1, \
        "position must remain open"


def test_check_exits_time_stop():
    monitor = _make_monitor()
    # Backdate alert to be exactly 30 minutes ago
    old_ts = datetime.utcnow() - timedelta(minutes=31)
    _seed_position(monitor, 'QQQ', 'CALL', entry_price=677.63,
                   target_price=685.00, alert_ts=old_ts)
    with patch.object(monitor, '_fire_exit_alert') as mock_fire, \
         patch.object(monitor, '_persist_exit'):
        monitor._check_exits('QQQ', _bar(678.00, 50.0), 678.00)
    args, _ = mock_fire.call_args
    assert args[2] == 'time_stop'


def test_check_exits_call_rsi_extreme():
    monitor = _make_monitor()
    _seed_position(monitor, 'QQQ', 'CALL', entry_price=677.63,
                   target_price=685.00)  # not at target
    with patch.object(monitor, '_fire_exit_alert') as mock_fire, \
         patch.object(monitor, '_persist_exit'):
        monitor._check_exits('QQQ', _bar(683.00, 81.0), 683.00)
    args, _ = mock_fire.call_args
    assert args[2] == 'rsi_extreme'


def test_check_exits_put_rsi_extreme_with_zero_rsi_does_not_fire():
    """Defensive: RSI=0 (uninitialized) should NOT trigger PUT rsi_exit."""
    monitor = _make_monitor()
    _seed_position(monitor, 'QQQ', 'PUT', entry_price=678.00,
                   target_price=670.00)
    with patch.object(monitor, '_fire_exit_alert') as mock_fire:
        monitor._check_exits('QQQ', _bar(676.00, 0.0), 676.00)
    assert not mock_fire.called, \
        "RSI=0 must NOT trigger PUT rsi_exit (would be a false positive on init)"


def test_check_exits_handles_multiple_positions_per_ticker():
    monitor = _make_monitor()
    # Two open positions on QQQ
    _seed_position(monitor, 'QQQ', 'CALL', 677, 680)  # will hit target
    _seed_position(monitor, 'QQQ', 'CALL', 678, 685)  # will not
    with patch.object(monitor, '_fire_exit_alert') as mock_fire, \
         patch.object(monitor, '_persist_exit'):
        monitor._check_exits('QQQ', _bar(680.50, 50.0), 680.50)
    assert mock_fire.call_count == 1
    assert len(monitor.active_positions['QQQ']) == 1, \
        "only the position that hit target should be removed"


def test_check_exits_target_takes_precedence_over_time_stop():
    """If price hits target on the SAME tick that time_stop expires,
    we record it as target_hit (the better outcome)."""
    monitor = _make_monitor()
    old_ts = datetime.utcnow() - timedelta(minutes=31)  # past time stop
    _seed_position(monitor, 'QQQ', 'CALL', entry_price=677.63,
                   target_price=679.66, alert_ts=old_ts)
    with patch.object(monitor, '_fire_exit_alert') as mock_fire, \
         patch.object(monitor, '_persist_exit'):
        monitor._check_exits('QQQ', _bar(680.00, 50.0), 680.00)
    args, _ = mock_fire.call_args
    assert args[2] == 'target_hit', \
        f"target should win when both true; got {args[2]}"


# ── _exit_return_pct math ──────────────────────────────────────────

def test_exit_return_pct_call_profit():
    from gcp.signal_monitor import SignalMonitor
    assert SignalMonitor._exit_return_pct('CALL', 100.0, 100.30) == pytest.approx(0.30)


def test_exit_return_pct_put_profit():
    from gcp.signal_monitor import SignalMonitor
    assert SignalMonitor._exit_return_pct('PUT', 100.0, 99.62) == pytest.approx(0.38)


def test_exit_return_pct_call_loss():
    from gcp.signal_monitor import SignalMonitor
    assert SignalMonitor._exit_return_pct('CALL', 100.0, 99.85) == pytest.approx(-0.15)


def test_exit_return_pct_put_loss():
    from gcp.signal_monitor import SignalMonitor
    assert SignalMonitor._exit_return_pct('PUT', 100.0, 100.20) == pytest.approx(-0.20)


# ── persist row contains is_open=True for new fires ─────────────────

def test_persist_row_includes_is_open_true():
    """New entries MUST be flagged is_open=True so the exit-watcher
    knows they're tracked. Without this, _persist_exit would have no
    row to update and exit alerts would never persist."""
    monitor = _make_monitor()
    sig = {"direction": "CALL", "base_score": 3,
           "conditions_met": ["rsi_oversold_zone", "below_vwap", "stoch_rsi_oversold"]}
    latest = _bar(677.63, 35.0)
    latest['Consecutive_Down'] = 4
    latest['VWAP'] = 678.0
    with patch("gcp.database.upsert_dataframe") as mock_upsert, \
         patch("gcp.database.is_cloud_sql_configured", return_value=True):
        mock_upsert.return_value = 1
        monitor._persist_signal_alert(
            ticker='QQQ', sig=sig, total_score=2.25, strength='weak',
            size=0.05, strat_bonus=0, latest=latest,
            target=679.66, time_stop=30,
        )
    df = mock_upsert.call_args[0][0]
    assert 'is_open' in df.columns, "persist row MUST set is_open"
    assert bool(df.iloc[0]['is_open']) is True


def test_persist_appends_to_active_positions():
    """A successful entry persist MUST register the position in
    active_positions so the exit-watcher can monitor it."""
    monitor = _make_monitor()
    sig = {"direction": "CALL", "base_score": 3,
           "conditions_met": ["rsi_oversold_zone", "below_vwap", "stoch_rsi_oversold"]}
    latest = _bar(677.63, 35.0)
    initial_len = len(monitor.active_positions.get('QQQ', []))

    with patch("gcp.database.upsert_dataframe") as mock_upsert, \
         patch("gcp.database.is_cloud_sql_configured", return_value=True):
        mock_upsert.return_value = 1
        monitor._persist_signal_alert(
            ticker='QQQ', sig=sig, total_score=2.25, strength='weak',
            size=0.05, strat_bonus=0, latest=latest,
            target=679.66, time_stop=30,
        )
    positions = monitor.active_positions['QQQ']
    assert len(positions) == initial_len + 1, \
        "new position MUST be appended to active_positions for exit-watcher to track"
    pos = positions[-1]
    assert pos['direction'] == 'CALL'
    assert pos['target_price'] == 679.66
    assert pos['time_stop_minutes'] == 30
    assert pos['entry_price'] == 677.63
