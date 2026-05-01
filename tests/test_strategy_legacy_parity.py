"""Phase 0.8 — Behavioral parity between new strategy classes and the
legacy generators they replace.

These tests guarantee the refactor doesn't change WHICH bars fire — it
only changes the OUTPUT SCHEMA (Signal dataclass instead of dict /
DataFrame). Crucial for shipping the refactor without changing live
signal_alerts behavior on the next deploy.

Two parities tested:
  1. MeanReversionStrategy vs lib.signals.evaluate_signal — same bars
     fire, same direction, same conditions_met.
  2. MomentumStrategy vs MarketAnalyzer's inline momentum block — same
     bars fire (count + direction); conditions_met list is new in
     the refactor (legacy only stored "{score}/5" string), so we
     can't compare condition labels — only the score.
"""
from __future__ import annotations

import pandas as pd
import pytest

from lib.strategies.mean_reversion import MeanReversionStrategy
from lib.strategies.momentum import MomentumStrategy
from lib.signals import evaluate_signal as legacy_mr_evaluate

MR_NEW = MeanReversionStrategy()
MOM_NEW = MomentumStrategy()


def _bar(**overrides) -> pd.Series:
    base = {
        "Time": pd.Timestamp("2026-05-01 13:30:00", tz="UTC"),
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


# ── Mean-reversion parity ───────────────────────────────────────────────

@pytest.mark.parametrize("name,row_kwargs", [
    ("oversold dip CALL", dict(
        Consecutive_Down=3, RSI14=35.0, Price_vs_VWAP=-0.5, StochRSI_K=20.0,
    )),
    ("overbought pop PUT", dict(
        Consecutive_Up=3, RSI14=65.0, Price_vs_VWAP=0.5, StochRSI_K=80.0,
    )),
    ("PDH break CALL", dict(
        Consecutive_Down=3, RSI14=35.0, Price_vs_VWAP=-0.5, Broke_Prev_Day_High=1,
    )),
    ("flat bar — no fire", dict()),
    ("only 2 conditions — no fire", dict(
        Consecutive_Down=3, RSI14=35.0,
    )),
])
def test_mean_reversion_matches_legacy_evaluate_signal(name, row_kwargs):
    """Run both old (lib.signals.evaluate_signal) and new on the same row,
    assert same direction + same base_score + same conditions_met."""
    row = _bar(**row_kwargs)
    legacy = legacy_mr_evaluate(row)
    new = MR_NEW.evaluate(row)

    if legacy is None:
        assert new is None, (
            f"[{name}] new fires but legacy doesn't — "
            f"new={new}"
        )
        return

    assert new is not None, (
        f"[{name}] legacy fires but new doesn't — legacy={legacy}"
    )
    assert legacy["direction"] == new.direction, (
        f"[{name}] direction mismatch — legacy={legacy['direction']} new={new.direction}"
    )
    # Legacy 'base_score' is the raw int condition count
    assert legacy["base_score"] == new.base_score, (
        f"[{name}] score mismatch — legacy={legacy['base_score']} new={new.base_score}"
    )
    # conditions_met set parity (order may differ if logic ever reorders)
    assert set(legacy["conditions_met"]) == set(new.conditions_met), (
        f"[{name}] conditions mismatch — "
        f"legacy={set(legacy['conditions_met'])} "
        f"new={set(new.conditions_met)}"
    )


# ── Momentum parity ─────────────────────────────────────────────────────
# The legacy momentum generator (MarketAnalyzer.generate_technical_signals)
# is an internal scoring loop with no public single-bar entry point. We
# replicate its exact condition-check inline below to avoid coupling the
# parity test to internal MarketAnalyzer state.

def _legacy_momentum_score(row: pd.Series) -> tuple[int, int, str | None]:
    """Replicate lib/trading_analysis.py:801-836 condition logic.

    Returns (call_score, put_score, signal_direction).
    """
    rsi = row.get("RSI14_W", row.get("RSI14", 50.0))
    if pd.isna(rsi) or pd.isna(row.get("StochRSI_K")):
        return (0, 0, None)

    call_n = 0
    if row.get("Consecutive_Up", 0) >= 3:
        call_n += 1
    if 25 < rsi < 50:
        call_n += 1
    if row.get("StochRSI_K", 50.0) < 80:
        call_n += 1
    last = row.get("Close", row.get("Last", 0.0))
    if last > row.get("VWAP", last):
        call_n += 1
    if last > row.get("EMA9", last):
        call_n += 1

    put_n = 0
    if row.get("Consecutive_Down", 0) >= 3:
        put_n += 1
    if 50 < rsi < 75:
        put_n += 1
    if row.get("StochRSI_K", 50.0) > 20:
        put_n += 1
    if last < row.get("VWAP", last):
        put_n += 1
    if last < row.get("EMA9", last):
        put_n += 1

    direction = None
    if call_n >= 3 and call_n > put_n:
        direction = "CALL"
    elif put_n >= 3 and put_n > call_n:
        direction = "PUT"
    return (call_n, put_n, direction)


@pytest.mark.parametrize("name,row_kwargs", [
    ("strong uptrend CALL", dict(
        Consecutive_Up=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0, EMA9=100.0,
        StochRSI_K=50.0,
    )),
    ("weak signal — no fire", dict(
        Consecutive_Up=3, RSI14_W=55.0,   # RSI 55 outside (25,50)
        StochRSI_K=50.0,
    )),
    ("strong downtrend PUT", dict(
        Consecutive_Down=3, RSI14_W=65.0,
        Last=99.0, Close=99.0, VWAP=100.0, EMA9=100.0,
        StochRSI_K=50.0,
    )),
    ("flat — no fire", dict(
        StochRSI_K=50.0,
    )),
])
def test_momentum_matches_legacy_inline_logic(name, row_kwargs):
    row = _bar(**row_kwargs)
    legacy_call_n, legacy_put_n, legacy_dir = _legacy_momentum_score(row)
    new_sig = MOM_NEW.evaluate(row)

    if legacy_dir is None:
        assert new_sig is None, (
            f"[{name}] new fires but legacy doesn't — new={new_sig}"
        )
        return

    assert new_sig is not None, (
        f"[{name}] legacy fires {legacy_dir} but new doesn't — "
        f"call_n={legacy_call_n} put_n={legacy_put_n}"
    )
    assert new_sig.direction == legacy_dir, (
        f"[{name}] direction mismatch — legacy={legacy_dir} new={new_sig.direction}"
    )
    legacy_score = legacy_call_n if legacy_dir == "CALL" else legacy_put_n
    assert new_sig.base_score == legacy_score, (
        f"[{name}] score mismatch — legacy={legacy_score} new={new_sig.base_score}"
    )


# ── Cross-strategy: same bar, opposite directions ───────────────────────

def test_complementary_strategies_fire_opposite_on_overbought_pop():
    """The §3.9 finding documented in the test plan: when both strategies
    fire on the same bar, they fire in OPPOSITE directions ~78.6% of the
    time. Lock that property in as a regression test."""
    row = _bar(
        Consecutive_Up=3, RSI14_W=65.0, RSI14=65.0,
        Last=101.0, Close=101.0,
        VWAP=100.5, EMA9=100.5, EMA20=100.5,
        StochRSI_K=80.0,
        Price_vs_VWAP=0.5, Price_vs_EMA9=0.5, Price_vs_EMA20=0.5,
    )
    mom = MOM_NEW.evaluate(row)
    mr  = MR_NEW.evaluate(row)

    # Both should fire on this bar
    assert mom is not None, "MOMENTUM should fire — Consec_Up=3 + above VWAP/EMA9"
    assert mr  is not None, "MEAN_REVERSION should fire — Consec_Up=3 + above VWAP + RSI 65"

    # And in opposite directions
    assert mom.direction == "CALL", "momentum: ride the strength"
    assert mr.direction  == "PUT",  "mean-reversion: fade the pop"
    assert mom.direction != mr.direction
