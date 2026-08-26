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
        # Production _check_exits computes elapsed against naive
        # datetime.now() (== UTC on Cloud Run). Backdate with the same
        # clock so elapsed math is machine-timezone independent.
        'alert_ts': alert_ts or datetime.now() - timedelta(minutes=5),
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
    old_ts = datetime.now() - timedelta(minutes=31)  # same clock as _check_exits
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
    old_ts = datetime.now() - timedelta(minutes=31)  # past time stop; same clock as _check_exits
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


# ── _persist_exit mirrors exit onto the trades table ────────────────
#
# Forensics (.superpowers/sdd/p-exit-writing-forensics.md): nothing ever
# wrote exits to `trades` — the watcher wrote signal_alerts only, so
# every live pipeline trades row since 2026-05-01 is permanently open.
# These tests pin the forward-fix: one exit event issues BOTH updates
# with equal values, warns (never silently no-ops) when no open trades
# row matches, and the trades UPDATE is idempotent via `exit_time IS
# NULL` so a real exit is never overwritten by a different one.
#
# Linkage evidence: `_persist_signal_alert` writes signal_alerts.alert_ts
# and trades.entry_time from the SAME `now` value, and (ticker,
# entry_time) is the trades upsert conflict key — verified 2071/2071
# post-2026-05-01 rows join exactly on (ticker, entry_time = alert_ts).

def _mock_exit_engine(rowcounts):
    """Engine mock whose conn.execute returns the given rowcounts in order."""
    conn = MagicMock()
    conn.execute.side_effect = [MagicMock(rowcount=rc) for rc in rowcounts]
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    engine.begin.return_value.__exit__.return_value = False
    return engine, conn


def _exit_pos(direction='CALL', entry_price=677.63, target_price=679.66):
    return {
        'ticker': 'QQQ',
        'alert_ts': datetime(2026, 7, 10, 14, 30, 0),
        'direction': direction,
        'entry_price': entry_price,
        'target_price': target_price,
        'time_stop_minutes': 30,
        'score': 4.0,
        'strength': 'medium',
        'size': 0.05,
    }


def test_persist_exit_writes_signal_alerts_and_trades_with_equal_values():
    """One exit event → UPDATE signal_alerts AND UPDATE trades, carrying
    the same exit_ts / exit_price / exit_reason / return_pct, with the
    trades row matched on (ticker, entry_time == alert_ts)."""
    from gcp.signal_monitor import SignalMonitor
    monitor = _make_monitor()
    pos = _exit_pos()
    exit_ts = datetime(2026, 7, 10, 15, 0, 0)
    engine, conn = _mock_exit_engine([1, 1])

    with patch('gcp.database.is_cloud_sql_configured', return_value=True), \
         patch('gcp.database.get_engine', return_value=engine):
        monitor._persist_exit(pos, 679.70, 'target_hit', exit_ts)

    assert conn.execute.call_count == 2, \
        "exit persist MUST issue exactly two UPDATEs (signal_alerts + trades)"
    alert_stmt, alert_params = conn.execute.call_args_list[0].args
    trade_stmt, trade_params = conn.execute.call_args_list[1].args
    assert 'UPDATE signal_alerts' in str(alert_stmt)
    assert 'UPDATE trades' in str(trade_stmt)

    # Row correspondence: trades.entry_time == signal_alerts.alert_ts
    assert trade_params['ticker'] == pos['ticker']
    assert trade_params['entry_time'] == pos['alert_ts']
    assert alert_params['alert_ts'] == pos['alert_ts']

    # Equal computed values across both tables
    expected_ret = SignalMonitor._exit_return_pct('CALL', 677.63, 679.70)
    for params in (alert_params, trade_params):
        assert params['exit_ts'] == exit_ts
        assert params['reason'] == 'target_hit'
        assert params['price'] == pytest.approx(679.70)
        assert params['ret'] == pytest.approx(expected_ret)


def test_persist_exit_trades_update_is_idempotent_and_never_overwrites():
    """The trades UPDATE must carry `exit_time IS NULL` so a re-run
    converges and a real recorded exit is never silently replaced."""
    monitor = _make_monitor()
    engine, conn = _mock_exit_engine([1, 1])
    with patch('gcp.database.is_cloud_sql_configured', return_value=True), \
         patch('gcp.database.get_engine', return_value=engine):
        monitor._persist_exit(_exit_pos(), 679.70, 'target_hit',
                              datetime(2026, 7, 10, 15, 0, 0))
    trade_stmt = str(conn.execute.call_args_list[1].args[0])
    assert 'exit_time IS NULL' in trade_stmt, \
        "trades exit mirror MUST guard on exit_time IS NULL (idempotence)"


def test_persist_exit_warns_when_no_trades_row_matches(caplog):
    """Rowcount 0 on the trades mirror MUST log a WARNING (Rule 3.7 — no
    silent no-ops) while the signal_alerts write still goes through."""
    import logging
    monitor = _make_monitor()
    engine, conn = _mock_exit_engine([1, 0])  # alerts row hit, trades miss
    with patch('gcp.database.is_cloud_sql_configured', return_value=True), \
         patch('gcp.database.get_engine', return_value=engine), \
         caplog.at_level(logging.WARNING, logger='gcp.signal_monitor'):
        monitor._persist_exit(_exit_pos(), 679.70, 'target_hit',
                              datetime(2026, 7, 10, 15, 0, 0))
    assert conn.execute.call_count == 2, \
        "signal_alerts UPDATE must still be issued when trades row is missing"
    warnings = [r for r in caplog.records
                if r.levelno >= logging.WARNING and 'trades' in r.getMessage()]
    assert warnings, \
        "missing/already-closed trades row MUST produce a WARNING, not a silent no-op"


def test_persist_exit_put_direction_return_pct_units():
    """PUT exits carry the direction-aware underlying-% return, matching
    the April-backfill trades rows' units ((entry-exit)/entry*100)."""
    monitor = _make_monitor()
    pos = _exit_pos(direction='PUT', entry_price=100.0, target_price=99.0)
    engine, conn = _mock_exit_engine([1, 1])
    with patch('gcp.database.is_cloud_sql_configured', return_value=True), \
         patch('gcp.database.get_engine', return_value=engine):
        monitor._persist_exit(pos, 99.0, 'target_hit',
                              datetime(2026, 7, 10, 15, 0, 0))
    trade_params = conn.execute.call_args_list[1].args[1]
    assert trade_params['ret'] == pytest.approx(1.0)


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


# ── fixed_horizon exit mode (audit 2026-08-25 §10) ──────────────────
# Default mode is 'target_stop' — every test above exercises it
# unchanged. These pin the opt-in mode: nothing exits before the
# horizon (target crossed or not), everything exits at the horizon
# with reason 'fixed_horizon'.

def test_fixed_horizon_ignores_target_before_horizon():
    monitor = _make_monitor()
    monitor.exit.call_exit_mode = 'fixed_horizon'
    monitor.exit.call_fixed_horizon_minutes = 30
    _seed_position(monitor, 'QQQ', 'CALL', entry_price=677.63,
                   target_price=679.66)  # seeded 5 min ago
    with patch.object(monitor, '_fire_exit_alert') as mock_fire:
        # Price is far past the target — target_stop mode would exit here.
        monitor._check_exits('QQQ', _bar(685.00, 50.0), 685.00)
    assert not mock_fire.called, \
        "fixed_horizon must NOT exit on target before the horizon"
    assert len(monitor.active_positions['QQQ']) == 1


def test_fixed_horizon_exits_at_horizon():
    from datetime import datetime as _dt, timedelta as _td
    monitor = _make_monitor()
    monitor.exit.put_exit_mode = 'fixed_horizon'
    monitor.exit.put_fixed_horizon_minutes = 30
    _seed_position(monitor, 'QQQ', 'PUT', entry_price=677.63,
                   target_price=670.00,
                   alert_ts=_dt.now() - _td(minutes=31))
    with patch.object(monitor, '_fire_exit_alert') as mock_fire, \
         patch.object(monitor, '_persist_exit') as mock_persist:
        monitor._check_exits('QQQ', _bar(678.00, 50.0), 678.00)
    assert mock_fire.called and mock_persist.called
    args, _ = mock_fire.call_args
    assert args[2] == 'fixed_horizon', f"expected fixed_horizon, got {args[2]}"
    assert monitor.active_positions['QQQ'] == []


def test_fixed_horizon_ignores_rsi_extreme():
    monitor = _make_monitor()
    monitor.exit.call_exit_mode = 'fixed_horizon'
    monitor.exit.call_fixed_horizon_minutes = 30
    _seed_position(monitor, 'QQQ', 'CALL', entry_price=677.63,
                   target_price=685.00)  # 5 min ago
    with patch.object(monitor, '_fire_exit_alert') as mock_fire:
        monitor._check_exits('QQQ', _bar(678.00, 95.0), 678.00)  # RSI 95
    assert not mock_fire.called, \
        "fixed_horizon must NOT exit on extreme RSI before the horizon"


def test_asymmetric_modes_call_targets_while_put_holds():
    # The evidence-supported configuration (audit §12): CALLs keep the
    # quick-target machinery, PUTs hold to a fixed horizon. Both legs
    # cross their targets on this bar sequence — only the CALL may exit.
    monitor = _make_monitor()
    monitor.exit.call_exit_mode = 'target_stop'
    monitor.exit.put_exit_mode = 'fixed_horizon'
    monitor.exit.put_fixed_horizon_minutes = 30
    _seed_position(monitor, 'QQQ', 'CALL', entry_price=677.63,
                   target_price=679.66)
    _seed_position(monitor, 'QQQ', 'PUT', entry_price=690.00,
                   target_price=685.00)  # price 679.70 <= 685 → put target crossed
    with patch.object(monitor, '_fire_exit_alert') as mock_fire, \
         patch.object(monitor, '_persist_exit'):
        monitor._check_exits('QQQ', _bar(679.70, 50.0), 679.70)
    reasons = [c.args[2] for c in mock_fire.call_args_list]
    assert reasons == ['target_hit'], f"only the CALL may exit, got {reasons}"
    remaining = monitor.active_positions['QQQ']
    assert len(remaining) == 1 and remaining[0]['direction'] == 'PUT', \
        "the PUT must still be open despite its target being crossed"
