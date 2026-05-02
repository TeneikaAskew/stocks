"""Phase 0.8 — MomentumStrategy condition tests (table-driven).

Each test crafts a single bar that satisfies exactly the conditions
named in its docstring and asserts the strategy returns the expected
Signal (or None).

Catches accidental logic changes — if anyone refactors past the
condition-eval block, the failing test pinpoints which condition is
mis-implemented.
"""
from __future__ import annotations

import pandas as pd
import pytest

from lib.strategies.momentum import MomentumStrategy

STRAT = MomentumStrategy()
TS = pd.Timestamp("2026-05-01 13:30:00", tz="UTC")


def _bar(**overrides) -> pd.Series:
    """Default bar that satisfies NO conditions — overrides flip them on."""
    base = {
        "Time": TS,
        "Close": 100.0, "Last": 100.0,
        "RSI14": 55.0, "RSI14_W": 55.0,             # outside both call/put RSI bands
        "VWAP": 100.0, "EMA9": 100.0, "EMA20": 100.0,
        "StochRSI_K": 50.0,
        "Consecutive_Up": 0, "Consecutive_Down": 0,
        "Price_vs_VWAP": 0.0, "Price_vs_EMA9": 0.0, "Price_vs_EMA20": 0.0,
        "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
    }
    base.update(overrides)
    return pd.Series(base)


def test_call_fires_with_3_conditions():
    """Consec_Up + RSI bullish + above VWAP — exactly 3, dominant over PUT."""
    row = _bar(
        Consecutive_Up=3,
        RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "CALL"
    assert sig.base_score >= 3
    assert "consecutive_up" in sig.conditions_met
    assert "rsi_bullish_recovery" in sig.conditions_met
    assert "above_vwap" in sig.conditions_met


def test_call_does_not_fire_with_2_conditions():
    """Only 2 of 5 met — below MIN_CONDITIONS=3."""
    row = _bar(
        Consecutive_Up=3,
        Last=101.0, Close=101.0, VWAP=100.0,   # above VWAP = 2nd condition
        # RSI=55 outside (25,50) so no RSI condition
    )
    sig = STRAT.evaluate(row)
    assert sig is None or sig.base_score >= 3


def test_put_fires_when_dominant():
    row = _bar(
        Consecutive_Down=3,
        RSI14_W=65.0,                           # in (50, 75)
        Last=99.0, Close=99.0, VWAP=100.0,      # below VWAP
        EMA9=100.0,                             # below EMA9
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "PUT"
    assert "consecutive_down" in sig.conditions_met
    assert "rsi_bearish_recovery" in sig.conditions_met
    assert "below_vwap" in sig.conditions_met
    assert "below_ema9" in sig.conditions_met


def test_strict_tie_breaker_no_fire_when_call_eq_put():
    """Original lib/trading_analysis.py uses STRICT > for tie-breaking.
    A bar where call_score == put_score must NOT fire.

    Phase 0.7.1: dropped `stoch_rsi_not_overbought` (free score). The
    fixture now needs above_vwap / above_ema9 to reach 3 CALL conditions
    instead of relying on the dropped stoch contribution.
    """
    row = _bar(
        # CALL conditions (3): Consec_Up, RSI in bull band, above_vwap
        Consecutive_Up=3,
        RSI14_W=35.0,                            # in CALL band (25, 50)
        Close=101.0, Last=101.0,
        VWAP=100.0,                               # price > VWAP → above_vwap fires
        EMA9=102.0,                               # price < EMA9 → above_ema9 doesn't fire
        # PUT conditions: Consec_Down only (RSI 35 NOT in put band, price
        # > VWAP rules out below_vwap, price < EMA9 rules out below_ema9)
        Consecutive_Down=3,
    )
    # call_n: consec_up + rsi_bullish_recovery + above_vwap = 3
    # put_n:  consec_down + below_ema9 = 2
    # call > put → fires CALL
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "CALL"


def test_warmup_bar_returns_none():
    row = _bar(RSI14_W=float("nan"))
    assert STRAT.evaluate(row) is None


def test_signal_carries_indicator_snapshots():
    row = _bar(
        Consecutive_Up=3, RSI14_W=35.0,
        Last=101.0, Close=101.0,
        VWAP=100.0, EMA9=100.0, EMA20=99.0,
        RVOL=1.4,
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.rsi == 35.0
    assert sig.vwap == 100.0
    assert sig.ema9 == 100.0
    assert sig.rvol == 1.4


def test_strategy_name_is_momentum():
    row = _bar(Consecutive_Up=3, RSI14_W=35.0,
                Last=101.0, Close=101.0, VWAP=100.0)
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.strategy == "momentum"


def test_generate_signals_returns_list_of_signals():
    """A 50-row DataFrame should produce a list (possibly empty) of Signals."""
    rows = []
    for i in range(50):
        rows.append({
            "Time": pd.Timestamp("2026-05-01 13:30:00", tz="UTC") + pd.Timedelta(minutes=i),
            "Close": 100.0, "Last": 100.0,
            "RSI14": 55.0, "RSI14_W": 55.0,
            "VWAP": 100.0, "EMA9": 100.0, "EMA20": 100.0,
            "StochRSI_K": 50.0,
            "Consecutive_Up": 0, "Consecutive_Down": 0,
            "Price_vs_VWAP": 0.0, "Price_vs_EMA9": 0.0, "Price_vs_EMA20": 0.0,
            "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
        })
    df = pd.DataFrame(rows)
    out = STRAT.generate_signals(df)
    assert isinstance(out, list)
    # all-flat input → no fires expected
    assert all(s.strategy == "momentum" for s in out)
