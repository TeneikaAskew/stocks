"""Regression tests for the per-ticker risk caps in signal_monitor.

Track D audit § 8.3 / § 8.7 found that `self.daily_trades` and
`self.daily_pnl` were initialized to 0 in `SignalMonitor.__init__` and
read at `evaluate_ticker` lines 437-440 to short-circuit, but **never
incremented anywhere** — IWM blew through the 5-fire/day cap by 22× on
2026-05-07 because the cap check was reading a frozen 0.

These tests lock in the post-fix behavior:
  1. `fire_alert` bumps `daily_trades[ticker]` by 1 per fire
  2. `_check_exits` bumps `daily_pnl[ticker]` on every exit
  3. `evaluate_ticker` short-circuits at the cap and does NOT call
     `fire_alert` once `daily_trades[ticker] >= max_daily_trades`
  4. Same short-circuit happens once `daily_pnl[ticker] <=
     daily_loss_limit`

If anyone reverts the increment (or moves the cap check after fire_alert
instead of before), these tests fail before the change ships.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest


def _make_monitor():
    """Construct a SignalMonitor with stubbed Discord."""
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""  # silence Discord side-effect
    return monitor


def _mr_call_bar():
    """A bar that wouldn't naturally fire — fire_alert is called directly."""
    return pd.Series({
        "Close": 720.0, "Last": 720.0,
        "RSI14": 35.0, "RSI14_W": 35.0,
        "VWAP": 723.0, "EMA9": 722.0, "EMA20": 723.5,
        "StochRSI_K": 25.0,
        "Price_vs_VWAP": -0.42, "Price_vs_EMA9": -0.28, "Price_vs_EMA20": -0.49,
        "Consecutive_Down": 4, "Consecutive_Up": 0,
        "RVOL": 1.4, "ATR14": 1.2,
        "Broke_Prev_Day_Low": 0, "Broke_Prev_Day_High": 0,
    })


def _exit_bar(close, rsi=50.0):
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


# ── 1) fire_alert increments daily_trades ───────────────────────────

def test_fire_alert_increments_daily_trades():
    """Every successful fire bumps the per-ticker daily_trades counter
    by exactly 1, so the cap at evaluate_ticker line 437 can short-circuit
    once `daily_trades[ticker] >= max_daily_trades`."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    starting = monitor.daily_trades.get(ticker, 0)
    sig = {
        "direction": "CALL", "base_score": 4,
        "conditions_met": ["consecutive_down", "rsi_oversold_zone", "below_vwap"],
    }
    latest = _mr_call_bar()

    with patch.object(monitor, '_persist_signal_alert'):
        monitor.fire_alert(ticker, sig, total_score=4.0,
                           strength="STRONG", size=0.10, strat_bonus=0,
                           latest=latest)
    assert monitor.daily_trades[ticker] == starting + 1, (
        f"daily_trades[{ticker}] should bump from {starting} to {starting + 1}, "
        f"got {monitor.daily_trades[ticker]}"
    )

    # Second fire — counter goes to starting + 2
    with patch.object(monitor, '_persist_signal_alert'):
        monitor.fire_alert(ticker, sig, total_score=4.0,
                           strength="STRONG", size=0.10, strat_bonus=0,
                           latest=latest)
    assert monitor.daily_trades[ticker] == starting + 2


# ── 2) _check_exits increments daily_pnl ──────────────────────────

def test_check_exits_increments_daily_pnl_on_target_hit():
    """Every exit bumps daily_pnl by realized fractional return × size.

    The cap at evaluate_ticker line 439 compares against
    `risk.daily_loss_limit` which is normalized to a fraction in
    `lib/config.py` (e.g. -0.02 = -2%). The backtest path accumulates
    `return_pct * position_size` fractional (lib/backtest.py:522).
    This test locks in the same units in the live monitor."""
    monitor = _make_monitor()
    ticker = 'QQQ'  # exit-watcher tests use QQQ
    size = 0.10
    monitor.active_positions.setdefault(ticker, []).append({
        'ticker': ticker,
        'alert_ts': datetime.utcnow() - timedelta(minutes=5),
        'direction': 'CALL',
        'entry_price': 677.63,
        'target_price': 679.66,
        'time_stop_minutes': 30,
        'score': 4.0,
        'strength': 'medium',
        'size': size,
    })
    starting = monitor.daily_pnl.get(ticker, 0.0)

    with patch.object(monitor, '_fire_exit_alert'), \
         patch.object(monitor, '_persist_exit'):
        # Bar @ 679.70 hits the 679.66 target → +0.31% raw, +0.000305 sized
        monitor._check_exits(ticker, _exit_bar(679.70), 679.70)

    expected_frac = (679.70 - 677.63) / 677.63 * size
    delta = monitor.daily_pnl[ticker] - starting
    assert delta == pytest.approx(expected_frac, abs=1e-9), (
        f"daily_pnl[{ticker}] should bump by FRACTIONAL sized return "
        f"~{expected_frac:.6f}, got {delta:.6f}"
    )
    # Sanity: must be a fraction, not a percent — never exceed 1.0 for
    # a single trade with size <= 1.0
    assert abs(delta) < 1.0, (
        f"daily_pnl bump must be in fractional units to compare against "
        f"daily_loss_limit (fraction); got {delta} which looks like a "
        f"percent. See lib/config.py:207 / lib/backtest.py:522."
    )


def test_check_exits_increments_daily_pnl_negative_on_put_loss():
    """A PUT that exits via time_stop above entry is a loss; daily_pnl
    bumps NEGATIVE in fractional units."""
    monitor = _make_monitor()
    ticker = 'IWM'
    alert_ts = datetime.utcnow() - timedelta(minutes=40)
    size = 0.20
    monitor.active_positions.setdefault(ticker, []).append({
        'ticker': ticker,
        'alert_ts': alert_ts,
        'direction': 'PUT',
        'entry_price': 200.00,
        'target_price': 197.50,
        'time_stop_minutes': 30,  # already elapsed → time_stop will fire
        'score': 4.0,
        'strength': 'medium',
        'size': size,
    })
    starting = monitor.daily_pnl.get(ticker, 0.0)

    with patch.object(monitor, '_fire_exit_alert'), \
         patch.object(monitor, '_persist_exit'):
        # Price went UP to 201.00 → PUT is a loss
        monitor._check_exits(ticker, _exit_bar(201.00, rsi=50.0), 201.00)

    # PUT P&L fractional sized = (entry - exit) / entry * size
    expected_frac = (200.00 - 201.00) / 200.00 * size
    delta = monitor.daily_pnl[ticker] - starting
    assert delta == pytest.approx(expected_frac, abs=1e-9), (
        f"PUT loss should bump daily_pnl by fractional {expected_frac:+.6f}, "
        f"got {delta:+.6f}"
    )
    assert delta < 0, "loss should bump daily_pnl in the negative direction"


def test_daily_pnl_units_match_daily_loss_limit_units():
    """Direct unit-mismatch regression: a sequence of small losses
    must NOT trip `daily_loss_limit=-0.02` until the accumulated
    fractional sized P&L actually reaches the limit. Pre-Codex-fix,
    `_check_exits` accumulated *percent* values (-0.5 for -0.5%) and
    one such loss tripped the -0.02 (-2%) limit on the next eval."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    monitor.risk.daily_loss_limit = -0.02   # canonical -2% fraction
    # One -0.5% sized@10% loss = -0.0005 fractional. Three of these
    # = -0.0015. Limit is -0.02 → must NOT trip yet.
    starting = monitor.daily_pnl.get(ticker, 0.0)
    for _ in range(3):
        monitor.active_positions.setdefault(ticker, []).append({
            'ticker': ticker,
            'alert_ts': datetime.utcnow() - timedelta(minutes=40),
            'direction': 'PUT',
            'entry_price': 200.00,
            'target_price': 197.50,
            'time_stop_minutes': 30,
            'score': 4.0,
            'strength': 'medium',
            'size': 0.10,
        })
        with patch.object(monitor, '_fire_exit_alert'), \
             patch.object(monitor, '_persist_exit'):
            # +0.5% PUT loss: price goes 200 -> 201
            monitor._check_exits(ticker, _exit_bar(201.00), 201.00)

    # Accumulated -0.0015, well above -0.02 limit → must NOT trip
    assert monitor.daily_pnl[ticker] > monitor.risk.daily_loss_limit, (
        f"3 × -0.5%@10% losses should sum to ~-0.0015 fractional, "
        f"NOT trip -0.02 limit. daily_pnl={monitor.daily_pnl[ticker]} "
        f"vs limit={monitor.risk.daily_loss_limit}. If this fails, the "
        f"unit-mismatch (percent vs fraction) regression is back."
    )
    delta = monitor.daily_pnl[ticker] - starting
    assert delta == pytest.approx(-0.0015, abs=1e-9)


# ── 3) evaluate_ticker short-circuits at max_daily_trades ─────────────

def test_evaluate_ticker_short_circuits_when_max_daily_trades_hit():
    """Once `daily_trades[ticker] >= max_daily_trades`, evaluate_ticker
    must return BEFORE invoking _evaluate_strategies_for_bar / fire_alert.
    This is the cap that IWM blew through 22× pre-fix because the counter
    was frozen at 0."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    cap = monitor.risk.max_daily_trades
    monitor.daily_trades[ticker] = cap  # at the cap

    # Synthesize one bar's worth of indicators for evaluate_ticker
    bars = pd.concat([_mr_call_bar().to_frame().T] * 50, ignore_index=True)
    bars['Time'] = pd.date_range('2026-05-08 09:30', periods=50, freq='1min')

    with patch.object(monitor, 'calculate_indicators', return_value=bars), \
         patch.object(monitor, 'check_orb'), \
         patch.object(monitor, '_check_exits'), \
         patch.object(monitor, 'refresh_level_map'), \
         patch.object(monitor, '_evaluate_strategies_for_bar') as mock_eval, \
         patch.object(monitor, 'fire_alert') as mock_fire:
        monitor.evaluate_ticker(ticker)

    assert not mock_eval.called, (
        "evaluate_ticker MUST short-circuit BEFORE _evaluate_strategies_for_bar "
        f"once daily_trades[{ticker}]={cap} hits max_daily_trades={cap}"
    )
    assert not mock_fire.called, "fire_alert MUST NOT be invoked once cap is hit"


def test_evaluate_ticker_short_circuits_when_daily_loss_limit_hit():
    """Once `daily_pnl[ticker] <= daily_loss_limit`, evaluate_ticker
    must return BEFORE invoking _evaluate_strategies_for_bar / fire_alert."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    limit = monitor.risk.daily_loss_limit  # negative threshold
    monitor.daily_pnl[ticker] = limit       # at (or worse than) the limit

    bars = pd.concat([_mr_call_bar().to_frame().T] * 50, ignore_index=True)
    bars['Time'] = pd.date_range('2026-05-08 09:30', periods=50, freq='1min')

    with patch.object(monitor, 'calculate_indicators', return_value=bars), \
         patch.object(monitor, 'check_orb'), \
         patch.object(monitor, '_check_exits'), \
         patch.object(monitor, 'refresh_level_map'), \
         patch.object(monitor, '_evaluate_strategies_for_bar') as mock_eval, \
         patch.object(monitor, 'fire_alert') as mock_fire:
        monitor.evaluate_ticker(ticker)

    assert not mock_eval.called, (
        "evaluate_ticker MUST short-circuit BEFORE _evaluate_strategies_for_bar "
        f"once daily_pnl[{ticker}]={limit} hits daily_loss_limit={limit}"
    )
    assert not mock_fire.called, "fire_alert MUST NOT be invoked once loss limit is hit"
