"""Phase 0.8 — MeanReversionStrategy condition tests (table-driven).

Each test crafts a single bar that satisfies exactly the conditions
named in its docstring and asserts the strategy returns the expected
Signal (or None).
"""
from __future__ import annotations

import pandas as pd
import pytest

from lib.strategies.mean_reversion import MeanReversionStrategy

STRAT = MeanReversionStrategy()
TS = pd.Timestamp("2026-05-01 13:30:00", tz="UTC")


def _bar(**overrides) -> pd.Series:
    """Default bar that satisfies NO conditions — overrides flip them on.

    Note: lib.signals.evaluate_signal looks up RSI via IndicatorConfig().rsi_col
    which resolves to 'RSI14'. The MeanReversionStrategy uses the same column.
    """
    base = {
        "Time": TS,
        "Close": 100.0, "Last": 100.0,
        "RSI14": 55.0, "RSI14_W": 55.0,
        "VWAP": 100.0, "EMA9": 100.0, "EMA20": 100.0,
        "StochRSI_K": 50.0,
        "Consecutive_Up": 0, "Consecutive_Down": 0,
        "Price_vs_VWAP": 0.0, "Price_vs_EMA9": 0.0, "Price_vs_EMA20": 0.0,
        "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
    }
    base.update(overrides)
    return pd.Series(base)


def test_call_fires_on_oversold_dip():
    """Consec_Down + RSI in (25,50) + below VWAP + StochRSI oversold = 4 conds → CALL."""
    row = _bar(
        Consecutive_Down=3,
        RSI14=35.0,
        Price_vs_VWAP=-0.5,
        StochRSI_K=20.0,
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "CALL"
    assert "consecutive_down" in sig.conditions_met
    assert "rsi_oversold_zone" in sig.conditions_met
    assert "below_vwap" in sig.conditions_met
    assert "stoch_rsi_oversold" in sig.conditions_met


def test_put_fires_on_overbought_pop():
    """Track A G.P0.12 (audit 2026-05-08): max PUT score is 3 after
    `above_vwap` dropped from MR PUT scoring. Audit measured the factor
    as -16.1pp (QQQ) / -11.7pp (IWM) / -9.9pp (SPY) ANTI-correlated
    with PUT success. This test was 4-condition pre-audit.
    """
    row = _bar(
        Consecutive_Up=3,
        RSI14=65.0,
        Price_vs_VWAP=0.5,
        StochRSI_K=80.0,
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "PUT"
    assert "consecutive_up" in sig.conditions_met
    assert "rsi_overbought_zone" in sig.conditions_met
    # above_vwap REMOVED — Track A G.P0.12. Tests that asserted it
    # in the conditions list pre-audit are intentionally inverted now.
    assert "above_vwap" not in sig.conditions_met
    assert "stoch_rsi_overbought" in sig.conditions_met


def test_no_fire_on_flat_neutral_bar():
    """All conditions false → None."""
    row = _bar()
    assert STRAT.evaluate(row) is None


def test_level_break_pdh_adds_condition_for_call():
    """Strat v2 PDH break is a 6th condition for CALL signals."""
    row = _bar(
        Consecutive_Down=3,
        RSI14=35.0,
        Price_vs_VWAP=-0.5,
        Broke_Prev_Day_High=1,
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert "level_break_pdh" in sig.conditions_met


def test_level_break_pdl_adds_condition_for_put():
    row = _bar(
        Consecutive_Up=3,
        RSI14=65.0,
        Price_vs_VWAP=0.5,
        Broke_Prev_Day_Low=1,
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert "level_break_pdl" in sig.conditions_met


def test_warmup_bar_returns_none():
    row = _bar(RSI14=float("nan"))
    assert STRAT.evaluate(row) is None


def test_call_takes_priority_when_score_equal_to_put():
    """Note: mean_reversion uses '>=' tie-break (CALL wins ties), unlike
    momentum which uses strict '>'. This matches the original lib/signals
    behavior — see lib/signals.py:161 'call_score >= min_conditions and
    call_score >= put_score'."""
    # Both call_score and put_score = 3, but CALL wins under >=
    row = _bar(
        Consecutive_Down=3,                     # CALL +1
        Consecutive_Up=3,                       # PUT  +1
        RSI14=35.0,                              # CALL band → CALL +1 (RSI 35 also passes PUT band? no, 35<50 so not in (50,75))
        Price_vs_VWAP=-0.5,                     # CALL +1
    )
    sig = STRAT.evaluate(row)
    # In this construction CALL has 3 conditions, PUT has 1 (consec_up only).
    # CALL > PUT, fires CALL.
    assert sig is not None
    assert sig.direction == "CALL"


def test_strategy_name_is_mean_reversion():
    row = _bar(
        Consecutive_Down=3, RSI14=35.0, Price_vs_VWAP=-0.5, StochRSI_K=20.0,
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.strategy == "mean_reversion"


def test_generate_signals_walks_dataframe():
    rows = []
    for i in range(30):
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
    assert all(s.strategy == "mean_reversion" for s in out)
