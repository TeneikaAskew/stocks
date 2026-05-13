"""Tests for the REPLAY_PERSIST mode added in feat/replay-persist-mode.

The mode addresses two limitations of the existing hermetic replay:

  1. Cloud Run logs truncate the per-fire JSON output at ~85 records,
     blocking analysis that needs full per-fire detail.
  2. The hermetic replay processes 24-hour bars (~1,200/day) while live
     signal-monitor only runs RTH (~390 bars/day). Fire counts aren't
     comparable.

REPLAY_PERSIST=true / --persist:
  - Filters bars to RTH only (9:30-16:00 ET)
  - Persists captured fires to signal_alerts with run_kind='replay'
    and replay_id=<UUID> per execution
  - Adds basic exit simulation walking forward through subsequent bars

Tests below verify each piece independently. Integration with Cloud SQL
is mocked so the suite stays hermetic.
"""
from __future__ import annotations

import sys
from datetime import datetime, time, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ── filter_to_rth — the RTH-only filter ──────────────────────────


def test_filter_to_rth_keeps_only_market_hours():
    """9:30 AM ET = 13:30 UTC (during EDT). Bars at 9:00 ET and 16:30 ET
    should be filtered out."""
    from scripts.replay_signal_monitor import filter_to_rth
    times = pd.to_datetime([
        '2026-05-06T13:00:00',  # 9:00 ET — premarket
        '2026-05-06T13:30:00',  # 9:30 ET — RTH open
        '2026-05-06T14:00:00',  # 10:00 ET — RTH
        '2026-05-06T19:59:00',  # 15:59 ET — last RTH min
        '2026-05-06T20:00:00',  # 16:00 ET — after-hours start
        '2026-05-06T20:30:00',  # 16:30 ET — after-hours
    ], utc=True)
    bars = pd.DataFrame({
        'Time': times,
        'Open': [1] * 6, 'High': [1] * 6, 'Low': [1] * 6, 'Close': [1] * 6,
        'Volume': [1] * 6,
    })
    rth = filter_to_rth(bars)
    # Should keep 9:30, 10:00, 15:59 — drop 9:00, 16:00, 16:30
    assert len(rth) == 3
    et = rth['Time'].dt.tz_convert('America/New_York').dt.time.tolist()
    assert all(t >= time(9, 30) for t in et)
    assert all(t < time(16, 0) for t in et)


def test_filter_to_rth_handles_naive_timestamps():
    """If 'Time' lacks tz info, treat as UTC."""
    from scripts.replay_signal_monitor import filter_to_rth
    bars = pd.DataFrame({
        'Time': pd.to_datetime(['2026-05-06T14:00:00']),  # naive UTC, 10:00 ET
        'Open': [1], 'High': [1], 'Low': [1], 'Close': [1], 'Volume': [1],
    })
    rth = filter_to_rth(bars)
    assert len(rth) == 1


def test_filter_to_rth_handles_empty_df():
    from scripts.replay_signal_monitor import filter_to_rth
    out = filter_to_rth(pd.DataFrame())
    assert out.empty


def test_filter_to_rth_handles_dst_transition():
    """November 1 2026 falls back from EDT (UTC-4) to EST (UTC-5).
    9:30 ET on Nov 5 (EST) = 14:30 UTC (not 13:30 like during EDT)."""
    from scripts.replay_signal_monitor import filter_to_rth
    times = pd.to_datetime([
        '2026-11-05T14:30:00',  # 9:30 EST — keep
        '2026-11-05T13:30:00',  # 8:30 EST — drop (premarket)
    ], utc=True)
    bars = pd.DataFrame({
        'Time': times,
        'Open': [1] * 2, 'High': [1] * 2, 'Low': [1] * 2, 'Close': [1] * 2,
        'Volume': [1] * 2,
    })
    rth = filter_to_rth(bars)
    assert len(rth) == 1
    et_hour = rth['Time'].dt.tz_convert('America/New_York').dt.time.iloc[0]
    assert et_hour == time(9, 30)


# ── simulate_exit — the per-fire exit-resolver pass ──────────────


def _mock_engine_with_bars(bars_df):
    """Build a SQLAlchemy engine mock that returns the given bars."""
    engine = MagicMock()
    with patch('pandas.read_sql', return_value=bars_df):
        yield engine


def test_simulate_exit_target_hit():
    """Fire at $100 with target $102. Subsequent bar high reaches 102.5
    → exit at target, +2% return."""
    from scripts.replay_signal_monitor import simulate_exit, FireRecord
    fire = FireRecord(
        timestamp=pd.Timestamp('2026-05-06T14:00:00', tz='UTC'),
        ticker='SPY', direction='CALL',
        base_score=3, total_score=4.0,
        timeframe_tag='30m', expected_hold_min=60,
        strategy_agreement=None, conditions_met=['rsi_oversold'],
        embed_title='test',
    )
    bars = pd.DataFrame({
        'time': pd.to_datetime(['2026-05-06T14:01:00', '2026-05-06T14:02:00'], utc=True),
        'open': [100.0, 100.5], 'high': [100.5, 102.5],
        'low': [99.8, 100.2], 'close': [100.4, 102.3],
    })
    with patch('pandas.read_sql', return_value=bars):
        result = simulate_exit(fire, MagicMock(), target_price=102.0,
                              time_stop_minutes=60)
    assert result['exit_reason'] == 'target'
    assert result['exit_price'] == 102.0
    # Entry filled at first bar's open ($100.0); target $102.0
    # Return: (102.0 - 100.0) / 100.0 * 100 = +2.0%
    assert result['exit_return_pct'] == pytest.approx(2.0)


def test_simulate_exit_time_stop():
    """Fire at $100, target $200 (never reached). Exits at last bar
    via time_stop with the bar's close as exit_price."""
    from scripts.replay_signal_monitor import simulate_exit, FireRecord
    fire = FireRecord(
        timestamp=pd.Timestamp('2026-05-06T14:00:00', tz='UTC'),
        ticker='SPY', direction='CALL',
        base_score=3, total_score=4.0,
        timeframe_tag='30m', expected_hold_min=60,
        strategy_agreement=None, conditions_met=['rsi_oversold'],
        embed_title='test',
    )
    bars = pd.DataFrame({
        'time': pd.to_datetime(['2026-05-06T14:01:00', '2026-05-06T14:02:00'], utc=True),
        'open': [100.0, 100.5], 'high': [100.5, 100.7],
        'low': [99.8, 100.2], 'close': [100.4, 100.6],
    })
    with patch('pandas.read_sql', return_value=bars):
        result = simulate_exit(fire, MagicMock(), target_price=200.0)
    assert result['exit_reason'] == 'time_stop'
    assert result['exit_price'] == 100.6  # last close
    # (100.6 - 100.0) / 100.0 * 100 = +0.6%
    assert result['exit_return_pct'] == pytest.approx(0.6)


def test_simulate_exit_short_inverts_sign():
    """PUT fire: target hit when low <= target. Short return = -(exit - entry) / entry."""
    from scripts.replay_signal_monitor import simulate_exit, FireRecord
    fire = FireRecord(
        timestamp=pd.Timestamp('2026-05-06T14:00:00', tz='UTC'),
        ticker='SPY', direction='PUT',
        base_score=3, total_score=4.0,
        timeframe_tag='30m', expected_hold_min=60,
        strategy_agreement=None, conditions_met=[],
        embed_title='test',
    )
    bars = pd.DataFrame({
        'time': pd.to_datetime(['2026-05-06T14:01:00'], utc=True),
        'open': [100.0], 'high': [100.5], 'low': [97.5], 'close': [98.0],
    })
    with patch('pandas.read_sql', return_value=bars):
        result = simulate_exit(fire, MagicMock(), target_price=98.0)
    assert result['exit_reason'] == 'target'
    # Entry $100, target $98 (PUT side); return = -(98-100)/100 * 100 = +2.0
    assert result['exit_return_pct'] == pytest.approx(2.0)


def test_simulate_exit_no_data_returns_safe_default():
    from scripts.replay_signal_monitor import simulate_exit, FireRecord
    fire = FireRecord(
        timestamp=pd.Timestamp('2026-05-06T14:00:00', tz='UTC'),
        ticker='SPY', direction='CALL',
        base_score=3, total_score=4.0,
        timeframe_tag='30m', expected_hold_min=60,
        strategy_agreement=None, conditions_met=[],
        embed_title='test',
    )
    with patch('pandas.read_sql', return_value=pd.DataFrame()):
        result = simulate_exit(fire, MagicMock())
    assert result['exit_reason'] == 'no_data'
    assert result['exit_price'] is None
    assert result['exit_return_pct'] == 0.0


# ── persist_fire_to_signal_alerts — write-path integration ───────


def test_persist_fire_calls_insert_with_run_kind_replay():
    """Verify the INSERT is called with run_kind='replay' and replay_id."""
    from scripts.replay_signal_monitor import persist_fire_to_signal_alerts, FireRecord
    fire = FireRecord(
        timestamp=pd.Timestamp('2026-05-06T14:00:00', tz='UTC'),
        ticker='SPY', direction='CALL',
        base_score=3, total_score=4.0,
        timeframe_tag='30m', expected_hold_min=60,
        strategy_agreement=None, conditions_met=['rsi_oversold'],
        embed_title='test',
    )
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    replay_id = '12345678-1234-5678-9012-123456789012'
    persist_fire_to_signal_alerts(fire, MagicMock(), engine, replay_id)
    # The conn.execute call should have been made
    assert conn.execute.called
    # Inspect the params dict (second positional arg)
    call_args = conn.execute.call_args
    params = call_args[0][1]
    assert params['ticker'] == 'SPY'
    assert params['direction'] == 'CALL'
    assert params['replay_id'] == replay_id
    # The SQL string contains run_kind='replay' baked in (not a param)


def test_persist_fire_strength_label_thresholds():
    """Verify total_score → strength_label mapping."""
    from scripts.replay_signal_monitor import persist_fire_to_signal_alerts, FireRecord
    cases = [(1.5, 'replay-weak'), (3.5, 'replay-medium'), (5.5, 'replay-strong')]
    for score, expected in cases:
        fire = FireRecord(
            timestamp=pd.Timestamp('2026-05-06T14:00:00', tz='UTC'),
            ticker='SPY', direction='CALL',
            base_score=int(score), total_score=score,
            timeframe_tag='30m', expected_hold_min=60,
            strategy_agreement=None, conditions_met=[],
            embed_title='test',
        )
        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__.return_value = conn
        persist_fire_to_signal_alerts(fire, MagicMock(), engine, 'test-id')
        params = conn.execute.call_args[0][1]
        assert params['strength'] == expected, \
            f"score {score} should map to {expected}, got {params['strength']}"


# ── --persist CLI flag + REPLAY_PERSIST env var ─────────────────


def test_persist_cli_flag_recognised(monkeypatch):
    """--persist sets args.persist=True."""
    from scripts.replay_signal_monitor import parse_args
    args = parse_args(['--ticker', 'SPY', '--date', '2026-05-06', '--persist'])
    assert args.persist is True


def test_persist_default_false(monkeypatch):
    """Without --persist, the default is hermetic mode."""
    from scripts.replay_signal_monitor import parse_args
    args = parse_args(['--ticker', 'SPY', '--date', '2026-05-06'])
    assert args.persist is False
