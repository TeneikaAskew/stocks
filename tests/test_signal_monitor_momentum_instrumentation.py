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


# ── 4) Counter bumps on every bar (#369 — pre-fix this only happened
#       when mr fired, biasing the fired/evaluated denominator)

def test_counters_bump_every_bar_post_369():
    """Post-#369 the counter is moved BEFORE the mr-fires branch, so
    every bar reaching `_evaluate_strategies_for_bar` increments
    `momentum_evaluated_count`. The fired/evaluated ratio now has a
    meaningful denominator (every bar where momentum was checkable),
    not the pre-#369 mr-fires intersection.

    This was the intentional scope change in #369 — the previous
    semantics structurally biased the counter and made it answer the
    wrong question (Tracks C/D/E couldn't tell whether momentum was
    reachable or just unhitting).
    """
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    starting_eval = monitor.momentum_evaluated_count[ticker]
    starting_fired = monitor.momentum_fired_count[ticker]

    with patch("gcp.signal_monitor.evaluate_signal", return_value=None), \
         patch("gcp.signal_monitor.MOMENTUM.evaluate", return_value=None) as mock_mom:
        monitor._evaluate_strategies_for_bar(_bar(), 720.0, ticker)

    assert mock_mom.called, (
        "MOMENTUM.evaluate must run on every bar post-#369 — the "
        "pre-fix short-circuit at line 381 is intentionally removed"
    )
    assert monitor.momentum_evaluated_count[ticker] == starting_eval + 1
    assert monitor.momentum_fired_count[ticker] == starting_fired


# ── 4b) Codex P1 on #320: main() must configure INFO logging ────────

def test_main_configures_info_logging_so_session_summary_appears():
    """Codex P1 review on PR #320 (#3211919294): without INFO-level
    logging configured for the deployed Cloud Run job, every
    `logger.info(...)` call — including session_summary — is silently
    dropped at Python's default WARNING level. The 5-day rollup at
    #304 would see no data even though the counters incremented.

    PR #391 (#386 logging fix) moved the configuration from inside main()
    to module-level (so `logger.info` calls at module-import-time also
    land, and so a handler attached by a transitively-imported module
    doesn't suppress INFO via a stale WARNING level). This test now
    asserts the BEHAVIOR — that importing gcp.signal_monitor leaves the
    root logger at INFO level with at least one handler — rather than
    parsing main()'s source for a specific function call (over-constrained
    against the implementation location).
    """
    import importlib
    import logging
    import gcp.signal_monitor
    # Reload so the module-level basicConfig + setLevel run again under
    # whatever logging state the prior test order has left in place.
    importlib.reload(gcp.signal_monitor)

    root = logging.getLogger()
    assert root.level <= logging.INFO and root.level != logging.NOTSET, (
        f"Root logger level must be INFO or DEBUG "
        f"(got {logging.getLevelName(root.level)}); "
        f"otherwise gcp.signal_monitor's logger.info calls are dropped"
    )
    assert root.handlers, (
        "Root logger must have at least one handler attached after "
        "gcp.signal_monitor is imported; otherwise INFO logs go nowhere"
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


# ── 6) max_daily_trades cap mechanism (#386) ─────────────────────────
#
# Production data shows 300+ alerts/day on a 5/ticker cap. These tests
# isolate the cap mechanism from the rest of the fire pipeline so we can
# verify the LOGIC works in pure code — if these pass and production
# still over-fires, the bug is environmental (process restarts, multiple
# instances, daily_trades-clobbering external code) rather than logic.

def test_cap_check_blocks_evaluate_ticker_when_at_limit():
    """Smoking-gun unit test: when daily_trades[ticker] == max_daily_trades,
    evaluate_ticker must short-circuit before fire_alert is reached.

    If this passes but production fires 300+/day, the cap LOGIC is fine
    and the bug is elsewhere (state reset, multiple instances, etc.).
    """
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    cap = monitor.risk.max_daily_trades
    monitor.daily_trades[ticker] = cap  # at cap

    # Wire up a minimal df so calculate_indicators path doesn't return
    # early. Stub everything between bar-fetch and the cap check.
    fake_df = pd.DataFrame([_bar() for _ in range(50)])
    fake_df['Time'] = pd.date_range('2026-05-08 13:30:00', periods=50, freq='1min')

    with patch.object(monitor, 'calculate_indicators', return_value=fake_df), \
         patch.object(monitor, 'check_orb'), \
         patch.object(monitor, '_check_exits'), \
         patch.object(monitor, 'refresh_level_map'), \
         patch.object(monitor, 'check_level_breaks', return_value=[]), \
         patch.object(monitor, 'fire_alert') as mock_fire, \
         patch.object(monitor, '_evaluate_strategies_for_bar') as mock_eval:
        monitor.evaluate_ticker(ticker)

    assert not mock_fire.called, (
        f"fire_alert was called even though daily_trades[{ticker}]={cap} "
        f"reached cap={cap}; cap check at line 608 should have short-circuited"
    )
    assert not mock_eval.called, (
        "_evaluate_strategies_for_bar should not be reached when cap is hit"
    )


def test_cap_check_allows_evaluate_when_below_limit():
    """Counter-test: when daily_trades[ticker] < max_daily_trades,
    evaluate_ticker must proceed past the cap check."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    cap = monitor.risk.max_daily_trades
    monitor.daily_trades[ticker] = cap - 1  # one shy of cap

    fake_df = pd.DataFrame([_bar() for _ in range(50)])
    fake_df['Time'] = pd.date_range('2026-05-08 13:30:00', periods=50, freq='1min')

    with patch.object(monitor, 'calculate_indicators', return_value=fake_df), \
         patch.object(monitor, 'check_orb'), \
         patch.object(monitor, '_check_exits'), \
         patch.object(monitor, 'refresh_level_map'), \
         patch.object(monitor, 'check_level_breaks', return_value=[]), \
         patch.object(monitor, '_evaluate_strategies_for_bar',
                      return_value=(None, None)) as mock_eval:
        monitor.evaluate_ticker(ticker)

    assert mock_eval.called, (
        "_evaluate_strategies_for_bar should be reached when daily_trades < cap"
    )


def test_cap_increment_runs_after_fire_alert():
    """The increment at line 894 must actually bump daily_trades.
    Direct call to fire_alert with mocked downstream side-effects
    proves the counter math works."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    monitor.daily_trades[ticker] = 0
    monitor.webhook_url = ""  # skip Discord

    sig = {
        "direction": "CALL", "base_score": 3,
        "conditions_met": ["rsi_oversold_zone", "below_vwap", "stoch_rsi_oversold"],
    }
    latest = _bar()
    monitor.orb_levels[ticker] = {"5m_high": 720.5, "5m_low": 719.5,
                                   "15m_high": 721.0, "15m_low": 718.5}

    with patch.object(monitor, '_persist_signal_alert'), \
         patch.object(monitor, '_resolve_brief_bias',
                      return_value={'bias': 'NEUTRAL', 'setup_count': 0,
                                    'ftfc_direction': None, 'reason': '-',
                                    'ftfc_score': None}):
        monitor.fire_alert(ticker, sig, total_score=3.0,
                           strength="weak", size=0.05,
                           strat_bonus=0, latest=latest)

    assert monitor.daily_trades[ticker] == 1, (
        f"daily_trades[{ticker}] should be 1 after one fire_alert; "
        f"got {monitor.daily_trades[ticker]}. The increment at line 894 "
        f"didn't run, indicating an exception path inside fire_alert."
    )


def test_cap_full_loop_5_fires_then_blocks():
    """Simulate a full loop: call evaluate_ticker N+1 times where
    fire_alert always fires. After max_daily_trades hits, the (N+1)th
    call must be blocked.

    This is the hermetic equivalent of replaying a full session — if
    the cap accumulates correctly here, the production failure is NOT
    a logic bug in the cap path.
    """
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    cap = monitor.risk.max_daily_trades
    monitor.daily_trades[ticker] = 0
    monitor.webhook_url = ""

    sig = {
        "direction": "CALL", "base_score": 3,
        "conditions_met": ["rsi_oversold_zone", "below_vwap", "stoch_rsi_oversold"],
    }
    fake_df = pd.DataFrame([_bar() for _ in range(50)])
    fake_df['Time'] = pd.date_range('2026-05-08 13:30:00', periods=50, freq='1min')
    monitor.orb_levels[ticker] = {"5m_high": 720.5, "5m_low": 719.5,
                                   "15m_high": 721.0, "15m_low": 718.5}

    # Disable strat-bonus path so fire_alert doesn't call detect_combos(df)
    # which expects High/Low cols not in the synthetic bar fixture.
    monitor.strat_cfg.enabled = False

    fire_calls = []
    with patch.object(monitor, 'calculate_indicators', return_value=fake_df), \
         patch.object(monitor, 'check_orb'), \
         patch.object(monitor, '_check_exits'), \
         patch.object(monitor, 'refresh_level_map'), \
         patch.object(monitor, 'check_level_breaks', return_value=[]), \
         patch.object(monitor, '_evaluate_strategies_for_bar',
                      return_value=(sig, None)), \
         patch.object(monitor, '_persist_signal_alert'), \
         patch.object(monitor, '_resolve_brief_bias',
                      return_value={'bias': 'NEUTRAL', 'setup_count': 0,
                                    'ftfc_direction': None, 'reason': '-'}):
        # Track fire_alert call sequence
        original_fire_alert = monitor.fire_alert
        def tracking_fire(*args, **kwargs):
            fire_calls.append((monitor.daily_trades.get(ticker, 0),))
            return original_fire_alert(*args, **kwargs)
        monitor.fire_alert = tracking_fire

        # Run cap+1 iterations of evaluate_ticker
        for _ in range(cap + 5):
            monitor.evaluate_ticker(ticker)

    assert len(fire_calls) == cap, (
        f"fire_alert should have been called exactly {cap} times "
        f"(cap=max_daily_trades), got {len(fire_calls)}. Counter values "
        f"on entry to fire_alert: {[c[0] for c in fire_calls]}"
    )
    assert monitor.daily_trades[ticker] == cap, (
        f"daily_trades[{ticker}] should be {cap} after cap fires + (cap-1) blocks; "
        f"got {monitor.daily_trades[ticker]}"
    )
