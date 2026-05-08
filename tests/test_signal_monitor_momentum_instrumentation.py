"""Tests for the momentum instrumentation counters in gcp/signal_monitor.py.

Track D audit § 6 / G.P0.11: Tracks C, D, and E independently surfaced
that the momentum strategy has fired 0 times in 50 days. PR 6 added two
counters per ticker so the cross-track sync (issue #304) can read the
diagnostic counts from Cloud Logging:

  self.momentum_evaluated_count[ticker]  # incremented on every MOMENTUM.evaluate call
  self.momentum_fired_count[ticker]      # incremented when mom_signal is not None

These tests lock in the wiring:
  1. Counters initialize to {ticker: 0} in __init__ for each watchlist ticker
  2. Every successful call to _evaluate_strategies_for_bar bumps `evaluated` by 1
  3. `fired` only bumps when MOMENTUM.evaluate returns a non-None Signal
  4. mr-doesn't-fire path returns early WITHOUT touching either counter
     (so evaluated count = "bars where mr fired and momentum was checked")
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pandas as pd
import pytest


def _make_monitor():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    return monitor


def _bar(close=720.0, rsi=35.0):
    return pd.Series({
        "Close": close, "Last": close,
        "RSI14": rsi, "RSI14_W": rsi,
        "VWAP": close + 3.0, "EMA9": close + 2.0, "EMA20": close + 3.5,
        "StochRSI_K": 25.0,
        "Price_vs_VWAP": -0.42, "Price_vs_EMA9": -0.28, "Price_vs_EMA20": -0.49,
        "Consecutive_Down": 4, "Consecutive_Up": 0,
        "RVOL": 1.4, "ATR14": 1.2,
        "Broke_Prev_Day_Low": 0, "Broke_Prev_Day_High": 0,
        "Time": pd.Timestamp("2026-05-08 14:00:00"),
    })


# ── 1) __init__ initializes both counter dicts to {ticker: 0} ────────

def test_counters_initialized_to_zero_per_ticker():
    """SignalMonitor.__init__ must create per-ticker entries for both
    counters so first-fire access doesn't KeyError."""
    monitor = _make_monitor()
    for t in monitor.tickers:
        assert monitor.momentum_evaluated_count[t] == 0, (
            f"momentum_evaluated_count[{t}] should start at 0"
        )
        assert monitor.momentum_fired_count[t] == 0, (
            f"momentum_fired_count[{t}] should start at 0"
        )


# ── 2) Both counters bump when momentum fires ────────────────────────

def test_counters_bump_when_momentum_fires():
    """When MOMENTUM.evaluate returns a Signal (non-None), both
    `evaluated` AND `fired` increment by 1."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    starting_eval = monitor.momentum_evaluated_count[ticker]
    starting_fired = monitor.momentum_fired_count[ticker]

    # Stub: mr fires, momentum fires
    fake_mr_sig = {
        "direction": "CALL", "base_score": 4,
        "conditions_met": ["consecutive_down", "rsi_oversold_zone", "below_vwap"],
    }
    from lib.strategies.base import Signal
    fake_mom_signal = Signal(
        strategy="momentum",
        direction="CALL",
        timestamp=pd.Timestamp("2026-05-08 14:00:00"),
        entry_price=720.0,
        base_score=5.0,
        weighted_score=5.0,
        conditions_met=["rsi_thrust_3", "rvol_recent_20", "atr_expansion"],
    )
    with patch("gcp.signal_monitor.evaluate_signal", return_value=fake_mr_sig), \
         patch("gcp.signal_monitor.MOMENTUM.evaluate", return_value=fake_mom_signal):
        monitor._evaluate_strategies_for_bar(_bar(), 720.0, ticker)

    assert monitor.momentum_evaluated_count[ticker] == starting_eval + 1, (
        f"evaluated should bump by 1 when MOMENTUM.evaluate runs; "
        f"got {monitor.momentum_evaluated_count[ticker]}"
    )
    assert monitor.momentum_fired_count[ticker] == starting_fired + 1, (
        f"fired should bump by 1 when mom_signal is not None; "
        f"got {monitor.momentum_fired_count[ticker]}"
    )


# ── 3) Only `evaluated` bumps when momentum returns None ─────────────

def test_only_evaluated_bumps_when_momentum_returns_none():
    """When MOMENTUM.evaluate returns None (gate not satisfied),
    `evaluated` increments but `fired` stays. This is the diagnostic
    case the cross-track sync wants to count."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    starting_eval = monitor.momentum_evaluated_count[ticker]
    starting_fired = monitor.momentum_fired_count[ticker]

    fake_mr_sig = {
        "direction": "CALL", "base_score": 4,
        "conditions_met": ["consecutive_down", "rsi_oversold_zone", "below_vwap"],
    }
    with patch("gcp.signal_monitor.evaluate_signal", return_value=fake_mr_sig), \
         patch("gcp.signal_monitor.MOMENTUM.evaluate", return_value=None):
        monitor._evaluate_strategies_for_bar(_bar(), 720.0, ticker)

    assert monitor.momentum_evaluated_count[ticker] == starting_eval + 1
    assert monitor.momentum_fired_count[ticker] == starting_fired, (
        "fired must NOT bump when mom_signal is None — locks in the "
        "diagnostic semantics for the cross-track sync (#304)"
    )


# ── 4) Neither counter bumps when mean_reversion doesn't fire ───────

def test_counters_untouched_when_mr_does_not_fire():
    """When mean_reversion's `evaluate_signal` returns None, the method
    short-circuits before MOMENTUM.evaluate; neither counter should
    bump (locks in the current architecture's behaviour — this is the
    semantics that gives 'evaluated' its diagnostic meaning)."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    starting_eval = monitor.momentum_evaluated_count[ticker]
    starting_fired = monitor.momentum_fired_count[ticker]

    with patch("gcp.signal_monitor.evaluate_signal", return_value=None), \
         patch("gcp.signal_monitor.MOMENTUM.evaluate") as mock_mom:
        monitor._evaluate_strategies_for_bar(_bar(), 720.0, ticker)

    assert monitor.momentum_evaluated_count[ticker] == starting_eval, (
        "evaluated must NOT bump when mr didn't fire — momentum.evaluate "
        "was never called, so counting it would lie about reachability"
    )
    assert monitor.momentum_fired_count[ticker] == starting_fired
    assert not mock_mom.called, (
        "MOMENTUM.evaluate must not be called when mr fails — verifies "
        "the short-circuit at evaluate_strategies_for_bar line 381 is intact"
    )


# ── 5) Counters survive multiple calls per ticker ────────────────────

def test_counters_accumulate_across_multiple_calls():
    """Three back-to-back evals: 2 with momentum firing, 1 without.
    Final state: evaluated=3, fired=2."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    monitor.momentum_evaluated_count[ticker] = 0
    monitor.momentum_fired_count[ticker] = 0

    fake_mr_sig = {
        "direction": "CALL", "base_score": 4,
        "conditions_met": ["consecutive_down", "rsi_oversold_zone", "below_vwap"],
    }
    from lib.strategies.base import Signal
    fake_fire = Signal(
        strategy="momentum", direction="CALL",
        timestamp=pd.Timestamp("2026-05-08 14:00:00"),
        entry_price=720.0, base_score=5.0, weighted_score=5.0,
        conditions_met=["rsi_thrust_3"],
    )
    sequence = [fake_fire, None, fake_fire]
    with patch("gcp.signal_monitor.evaluate_signal", return_value=fake_mr_sig), \
         patch("gcp.signal_monitor.MOMENTUM.evaluate", side_effect=sequence):
        for _ in range(3):
            monitor._evaluate_strategies_for_bar(_bar(), 720.0, ticker)

    assert monitor.momentum_evaluated_count[ticker] == 3
    assert monitor.momentum_fired_count[ticker] == 2
