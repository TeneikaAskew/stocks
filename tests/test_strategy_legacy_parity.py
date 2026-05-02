"""Phase 0.8 → 0.7.x — Strategy divergence from the legacy generators.

History:
  Phase 0.8 (#184) extracted MeanReversion + Momentum into the
  lib/strategies/ package and these tests pinned BEHAVIORAL PARITY
  (same conditions, same scoring) so the refactor didn't change live
  signal_alerts on the next deploy.

  Phase 0.7.1+0.7.2 (this PR) intentionally drops two "free score"
  conditions per the §3.10 audit:
    * Momentum: stoch_rsi_not_overbought (72.2% fire rate)
    * Mean-reversion: near_below_emas (84.6% fire rate)
  These conditions added score on bars where they didn't actually
  reflect setup quality. Tightening the score distribution is the
  whole point.

  After Phase 0.7.x, the parity assertions below are now DIVERGENCE
  assertions. For each fixture:
    * Same bars fire, same direction (still)
    * NEW score = LEGACY score - (1 if the dropped condition fired
      in legacy, else 0)
    * NEW conditions_met = LEGACY conditions_met minus the dropped one

  This is more rigorous than deleting the tests: it pins the
  intentional divergence and catches OTHER unintended behavior
  changes (anything beyond the documented drops).
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
    """Phase 0.7.2 divergence: legacy includes near_below_emas / near_above_emas;
    new omits them. Otherwise behavior is identical.

    Asserts:
      * Direction matches
      * NEW score = LEGACY score - (1 if dropped condition fired in legacy else 0)
      * NEW conditions_met = LEGACY conditions_met - {dropped_label}
    """
    row = _bar(**row_kwargs)
    legacy = legacy_mr_evaluate(row)
    new = MR_NEW.evaluate(row)

    # The Phase 0.7.2 drops, by direction:
    DROPPED_FOR_DIR = {"CALL": "near_below_emas", "PUT": "near_above_emas"}

    # Edge case: legacy fired only because the dropped condition pushed
    # it over MIN_CONDITIONS=3. In that case new won't fire at all.
    if legacy is not None:
        dropped_label = DROPPED_FOR_DIR.get(legacy["direction"])
        legacy_had_dropped = dropped_label in (legacy.get("conditions_met") or [])
        legacy_minus_dropped = legacy["base_score"] - (1 if legacy_had_dropped else 0)
        if legacy_minus_dropped < 3:
            # Legacy fired only because of the dropped condition — new
            # correctly doesn't fire (intended Phase 0.7.2 effect).
            assert new is None, (
                f"[{name}] legacy fired only via dropped condition "
                f"({dropped_label}); new must NOT fire. new={new}"
            )
            return

    if legacy is None:
        assert new is None, (
            f"[{name}] new fires but legacy doesn't — new={new}"
        )
        return

    assert new is not None, (
        f"[{name}] legacy fires but new doesn't — legacy={legacy}"
    )
    assert legacy["direction"] == new.direction, (
        f"[{name}] direction mismatch — legacy={legacy['direction']} new={new.direction}"
    )

    dropped_label = DROPPED_FOR_DIR[legacy["direction"]]
    legacy_had_dropped = dropped_label in legacy["conditions_met"]
    expected_new_score = legacy["base_score"] - (1 if legacy_had_dropped else 0)
    assert new.base_score == expected_new_score, (
        f"[{name}] score mismatch — legacy={legacy['base_score']} "
        f"dropped={dropped_label} fired_in_legacy={legacy_had_dropped} "
        f"expected_new={expected_new_score} got={new.base_score}"
    )
    expected_conditions = set(legacy["conditions_met"]) - {dropped_label}
    assert set(new.conditions_met) == expected_conditions, (
        f"[{name}] conditions mismatch beyond expected drop — "
        f"legacy={set(legacy['conditions_met'])} "
        f"new={set(new.conditions_met)} "
        f"expected={expected_conditions}"
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
    """Phase 0.7.1 divergence: legacy includes stoch_rsi_not_overbought
    (CALL) / stoch_rsi_not_oversold (PUT); new omits them.

    Asserts:
      * Direction matches (or BOTH don't fire — legacy might have only
        fired because the dropped condition pushed it over MIN_CONDITIONS)
      * NEW score = LEGACY score - 1 (the dropped condition almost always
        fires in legacy at typical StochRSI values; if the threshold
        wasn't crossed we'd be in an edge case that's tested separately).
    """
    row = _bar(**row_kwargs)
    legacy_call_n, legacy_put_n, legacy_dir = _legacy_momentum_score(row)
    new_sig = MOM_NEW.evaluate(row)

    # Determine if the dropped condition fired in legacy for the chosen
    # direction. CALL drops `StochRSI_K < 80`; PUT drops `StochRSI_K > 20`.
    stoch = row.get("StochRSI_K", 50.0)
    if legacy_dir == "CALL":
        legacy_had_dropped = stoch < 80
    elif legacy_dir == "PUT":
        legacy_had_dropped = stoch > 20
    else:
        legacy_had_dropped = False

    legacy_score = (legacy_call_n if legacy_dir == "CALL"
                     else legacy_put_n if legacy_dir == "PUT" else 0)

    # Edge case: legacy fired only via the dropped condition.
    if legacy_dir is not None:
        legacy_minus_dropped = legacy_score - (1 if legacy_had_dropped else 0)
        if legacy_minus_dropped < 3:
            assert new_sig is None, (
                f"[{name}] legacy fired only via dropped stoch condition; "
                f"new must NOT fire. new={new_sig}"
            )
            return

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
    expected_new_score = legacy_score - (1 if legacy_had_dropped else 0)
    assert new_sig.base_score == expected_new_score, (
        f"[{name}] score mismatch — legacy={legacy_score} "
        f"dropped_in_legacy={legacy_had_dropped} "
        f"expected_new={expected_new_score} got={new_sig.base_score}"
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
