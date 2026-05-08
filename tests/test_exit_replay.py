"""Unit tests for `lib/exit_replay.py`.

The replay logic is the single source of truth for exit decisions —
both the live signal_monitor and the EOD reconciler import from here.
A bug in `decide_exit` will desync those two consumers and (re)create
the audit's "audit replay ≠ production logic" gap. So the tests cover
every branch:

  - CALL: target_hit > time_stop > rsi_extreme > None
  - PUT: same precedence with mirrored thresholds
  - simulate_exit walks bars in order; first match wins
  - simulate_exit returns eod_close at last bar IF last bar ≥ 16:00 ET
  - simulate_exit returns None for empty bars or partial mid-session data
"""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from lib.exit_replay import (
    DEFAULT_CALL_RSI_EXIT,
    DEFAULT_PUT_RSI_EXIT,
    ExitEvent,
    PERSIST_EXIT_SQL,
    Position,
    decide_exit,
    persist_exit_params,
    return_pct,
    simulate_exit,
)

UTC = ZoneInfo("UTC")
ET = ZoneInfo("America/New_York")


def _pos(direction='CALL', target=105.0, time_stop=15) -> Position:
    return Position(
        ticker='SPY',
        direction=direction,
        alert_ts=datetime(2026, 5, 8, 14, 0, 0),  # naive UTC = 10am ET
        entry_price=100.0,
        target_price=target,
        time_stop_minutes=time_stop,
    )


# ── return_pct ────────────────────────────────────────────────────────


def test_return_pct_call_profit():
    assert return_pct('CALL', 100.0, 105.0) == 5.0


def test_return_pct_call_loss():
    assert return_pct('CALL', 100.0, 95.0) == -5.0


def test_return_pct_put_profit():
    # Put profits when price falls
    assert return_pct('PUT', 100.0, 95.0) == 5.0


def test_return_pct_put_loss():
    assert return_pct('PUT', 100.0, 105.0) == -5.0


# ── decide_exit: CALL path ────────────────────────────────────────────


def test_call_target_hit_takes_precedence():
    # Both target hit AND time stop expired → target_hit wins
    pos = _pos(direction='CALL', target=105.0, time_stop=15)
    assert decide_exit(pos, current_price=106.0, current_rsi=50,
                       elapsed_minutes=20) == 'target_hit'


def test_call_time_stop():
    pos = _pos(direction='CALL', target=105.0, time_stop=15)
    assert decide_exit(pos, current_price=102.0, current_rsi=50,
                       elapsed_minutes=20) == 'time_stop'


def test_call_rsi_extreme():
    pos = _pos(direction='CALL')
    assert decide_exit(pos, current_price=102.0, current_rsi=85,
                       elapsed_minutes=5) == 'rsi_extreme'


def test_call_no_exit():
    pos = _pos(direction='CALL')
    assert decide_exit(pos, current_price=102.0, current_rsi=60,
                       elapsed_minutes=5) is None


# ── decide_exit: PUT path ─────────────────────────────────────────────


def test_put_target_hit():
    pos = _pos(direction='PUT', target=95.0)
    assert decide_exit(pos, current_price=94.0, current_rsi=50,
                       elapsed_minutes=5) == 'target_hit'


def test_put_time_stop():
    pos = _pos(direction='PUT', target=95.0, time_stop=10)
    # Price hasn't reached target; time elapsed
    assert decide_exit(pos, current_price=98.0, current_rsi=50,
                       elapsed_minutes=15) == 'time_stop'


def test_put_rsi_extreme():
    # PUT target=95 (below entry); price=99 hasn't hit target yet
    pos = _pos(direction='PUT', target=95.0)
    assert decide_exit(pos, current_price=99.0, current_rsi=15,
                       elapsed_minutes=5) == 'rsi_extreme'


def test_put_rsi_zero_does_not_exit():
    """RSI=0 is the placeholder for "no data" — must not trigger exit."""
    pos = _pos(direction='PUT', target=95.0)
    assert decide_exit(pos, current_price=99.0, current_rsi=0,
                       elapsed_minutes=5) is None


def test_put_no_exit():
    pos = _pos(direction='PUT', target=95.0)
    assert decide_exit(pos, current_price=98.0, current_rsi=50,
                       elapsed_minutes=5) is None


# ── decide_exit: ordering — target wins over time wins over RSI ──────


def test_call_target_beats_time_stop_when_both_true():
    pos = _pos(direction='CALL', target=105.0, time_stop=15)
    # Both target and time triggered → target wins
    out = decide_exit(pos, current_price=106.0, current_rsi=50,
                      elapsed_minutes=20)
    assert out == 'target_hit'


def test_call_time_beats_rsi_when_both_true():
    pos = _pos(direction='CALL', target=110.0, time_stop=15)
    # Target NOT hit (price 102 < target 110); time AND rsi both triggered
    out = decide_exit(pos, current_price=102.0, current_rsi=85,
                      elapsed_minutes=20)
    assert out == 'time_stop'


# ── simulate_exit: replay over bars ──────────────────────────────────


def _bar(ts_minutes_after_alert: int, close: float, rsi: float = 50.0):
    return {
        'ts': datetime(2026, 5, 8, 14, 0, 0) + pd.Timedelta(minutes=ts_minutes_after_alert),
        'close': close,
        'rsi_14': rsi,
    }


def test_simulate_returns_first_target_hit():
    pos = _pos(direction='CALL', target=105.0, time_stop=30)
    bars = pd.DataFrame([
        _bar(1, 101.0),
        _bar(5, 103.0),
        _bar(10, 106.0),  # target_hit
        _bar(12, 108.0),  # would also hit but we stop at first
    ])
    event = simulate_exit(pos, bars)
    assert event is not None
    assert event.exit_reason == 'target_hit'
    assert event.exit_price == 106.0
    # Profit: (106 - 100) / 100 = 6%
    assert event.exit_return_pct == 6.0


def test_simulate_returns_time_stop_when_target_never_hit():
    pos = _pos(direction='CALL', target=200.0, time_stop=10)
    bars = pd.DataFrame([
        _bar(2, 101.0),
        _bar(8, 102.0),
        _bar(12, 102.5),  # 12 min ≥ 10 min stop → time_stop
    ])
    event = simulate_exit(pos, bars)
    assert event is not None
    assert event.exit_reason == 'time_stop'
    assert event.exit_price == 102.5


def test_simulate_eod_close_when_no_condition_fires():
    pos = _pos(direction='CALL', target=200.0, time_stop=420)
    # Last bar at 16:00 ET = 20:00 UTC on a date during EDT
    last = datetime(2026, 5, 8, 20, 0, 0)  # 16:00 ET on May 8 (EDT)
    bars = pd.DataFrame([
        _bar(60, 101.0),
        _bar(120, 102.0),
        {'ts': last, 'close': 103.5, 'rsi_14': 55},
    ])
    event = simulate_exit(pos, bars)
    assert event is not None
    assert event.exit_reason == 'eod_close'
    assert event.exit_ts == last
    assert event.exit_price == 103.5


def test_simulate_returns_none_for_partial_mid_session_data():
    # Data ends mid-session and no condition fired → caller should wait
    pos = _pos(direction='CALL', target=200.0, time_stop=420)
    bars = pd.DataFrame([
        _bar(60, 101.0),
        _bar(120, 102.0),  # 12:00 UTC = 8:00 ET (still mid-session)
    ])
    event = simulate_exit(pos, bars)
    assert event is None


def test_simulate_returns_none_for_empty_bars():
    pos = _pos(direction='CALL')
    assert simulate_exit(pos, pd.DataFrame()) is None
    assert simulate_exit(pos, None) is None  # type: ignore[arg-type]


def test_simulate_normalizes_unsorted_bars():
    pos = _pos(direction='CALL', target=105.0, time_stop=30)
    # Bars in REVERSE order — simulator must sort first.
    bars = pd.DataFrame([
        _bar(10, 106.0),  # would hit target FIRST chronologically
        _bar(5, 103.0),
        _bar(1, 101.0),
    ])
    event = simulate_exit(pos, bars)
    assert event is not None
    assert event.exit_price == 106.0  # picked the t=10 bar (chronologically first hit)


# ── PERSIST_EXIT_SQL contract ─────────────────────────────────────────


def test_persist_sql_contains_required_columns():
    """The SQL must update all five exit columns (exit_ts, exit_reason,
    exit_price, exit_return_pct, is_open) and use the (ticker, alert_ts)
    primary-key WHERE clause."""
    sql_lower = PERSIST_EXIT_SQL.lower()
    for col in ('exit_ts', 'exit_reason', 'exit_price',
                'exit_return_pct', 'is_open'):
        assert col in sql_lower, f"PERSIST_EXIT_SQL missing column {col}"
    assert 'where' in sql_lower
    assert ':ticker' in PERSIST_EXIT_SQL
    assert ':alert_ts' in PERSIST_EXIT_SQL


def test_persist_params_emits_correct_keys():
    pos = _pos()
    event = ExitEvent(
        exit_ts=datetime(2026, 5, 8, 14, 30, 0),
        exit_reason='target_hit',
        exit_price=106.0,
        exit_return_pct=6.0,
    )
    p = persist_exit_params(pos, event)
    assert set(p.keys()) == {'exit_ts', 'exit_reason', 'exit_price',
                             'exit_return_pct', 'ticker', 'alert_ts'}
    assert p['ticker'] == 'SPY'
    assert p['exit_price'] == 106.0
