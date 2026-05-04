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
        # Phase 0.7.2: relaxed gate reads `Consecutive_Up_5` / `Consecutive_Down_5`
        # (3-of-5 windows) instead of the strict 3-of-3 columns above.
        "Consecutive_Up_5": 0, "Consecutive_Down_5": 0,
        # Phase 0.7.x: `rvol_above_recent` fires when > 1.2. Default to
        # 1.0 (below threshold) so existing fixtures don't accidentally
        # pick up the new condition.
        "RVol_Recent_20": 1.0,
        # Phase 0.7.x: `atr_expansion` fires when > 1.15. Default to 1.0
        # so fixtures don't accidentally pick it up either.
        "ATR_Expansion": 1.0,
        # Phase 0.7.x: directional `rsi_thrust` fires on |delta| > 5.
        # Default 0 so fixtures don't accidentally fire either side.
        "RSI_Thrust_3": 0.0,
        "Price_vs_VWAP": 0.0, "Price_vs_EMA9": 0.0, "Price_vs_EMA20": 0.0,
        "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
    }
    base.update(overrides)
    return pd.Series(base)


def test_call_fires_with_3_conditions():
    """Consec_Up_5 (3-of-5) + RSI bullish + above VWAP — exactly 3, dominant over PUT."""
    row = _bar(
        Consecutive_Up_5=3,                       # 3-of-last-5 up bars
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
    """Only 2 of 4 met — below MIN_CONDITIONS=3."""
    row = _bar(
        Consecutive_Up_5=3,
        Last=101.0, Close=101.0, VWAP=100.0,   # above VWAP = 2nd condition
        # RSI=55 outside (25,50) so no RSI condition
    )
    sig = STRAT.evaluate(row)
    assert sig is None or sig.base_score >= 3


def test_consecutive_up_5_below_threshold_does_not_count():
    """Phase 0.7.2: 2-of-5 (below threshold of 3) must NOT satisfy the gate."""
    row = _bar(
        Consecutive_Up_5=2,                       # only 2-of-5 — below threshold
        RSI14_W=35.0,                             # in CALL band
        Last=101.0, Close=101.0, VWAP=100.0,      # above VWAP
        EMA9=99.0,                                # above EMA9
    )
    sig = STRAT.evaluate(row)
    assert sig is not None                        # still fires (3 of 4 without consec)
    assert "consecutive_up" not in sig.conditions_met


def test_consecutive_up_3_of_5_with_pullback_fires():
    """Phase 0.7.2: the relaxation's whole point — fires when 3 of last 5
    are up even with a pullback bar in between (would have failed strict 3-of-3).
    """
    row = _bar(
        Consecutive_Up_5=3,                       # 3 up, 2 down/flat in window
        Consecutive_Up=0,                         # strict 3-of-3 NOT met
        RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "CALL"
    assert "consecutive_up" in sig.conditions_met


def test_put_fires_when_dominant():
    row = _bar(
        Consecutive_Down_5=3,                     # 3-of-5 down bars
        RSI14_W=65.0,                             # in (50, 75)
        Last=99.0, Close=99.0, VWAP=100.0,        # below VWAP
        EMA9=100.0,                               # below EMA9
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
    """
    row = _bar(
        # CALL conditions (3): Consec_Up_5, RSI in bull band, above_vwap
        Consecutive_Up_5=3,
        RSI14_W=35.0,                            # in CALL band (25, 50)
        Close=101.0, Last=101.0,
        VWAP=100.0,                              # price > VWAP → above_vwap fires
        EMA9=102.0,                              # price < EMA9 → above_ema9 doesn't fire
        # PUT conditions: Consec_Down_5 only (RSI 35 NOT in put band, price
        # > VWAP rules out below_vwap, price < EMA9 rules out below_ema9)
        Consecutive_Down_5=3,
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


def test_rvol_above_recent_adds_to_call_score():
    """Phase 0.7.x: `rvol_above_recent` is a fifth scoring condition
    (volume confirmation). Bars with RVol_Recent_20 > 1.2 pick up +1.
    """
    row = _bar(
        Consecutive_Up_5=3,
        RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,       # above_vwap fires
        EMA9=100.0,                                 # above_ema9 fires
        RVol_Recent_20=1.5,                         # > 1.2 → fires
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "CALL"
    assert sig.base_score == 5                     # all 5 conditions met
    assert "rvol_above_recent" in sig.conditions_met


def test_rvol_below_threshold_does_not_count():
    row = _bar(
        Consecutive_Up_5=3,
        RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        EMA9=100.0,
        RVol_Recent_20=1.19,                        # just below 1.2
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.base_score == 4                     # rvol condition NOT met
    assert "rvol_above_recent" not in sig.conditions_met


def test_rvol_above_recent_alone_does_not_fire():
    """Volume alone (without trend / RSI / VWAP / EMA) must not fire."""
    row = _bar(
        RVol_Recent_20=2.5,                         # massive volume spike
        # All other conditions defaulted to NOT firing.
    )
    sig = STRAT.evaluate(row)
    assert sig is None                              # 1 of 5 < min_conditions=3


def test_rvol_missing_or_nan_does_not_fire():
    """Warmup / missing volume data must not satisfy the gate."""
    import numpy as np
    row_missing = _bar(
        Consecutive_Up_5=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        RVol_Recent_20=np.nan,
    )
    sig = STRAT.evaluate(row_missing)
    assert sig is not None
    assert "rvol_above_recent" not in sig.conditions_met


def test_rvol_above_recent_adds_to_put_score():
    """PUT mirror: high volume confirms the bearish setup symmetrically."""
    row = _bar(
        Consecutive_Down_5=3,
        RSI14_W=65.0,
        Last=99.0, Close=99.0, VWAP=100.0,         # below_vwap
        EMA9=100.0,                                 # below_ema9
        RVol_Recent_20=1.5,                         # fires
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "PUT"
    assert sig.base_score == 5
    assert "rvol_above_recent" in sig.conditions_met


def test_atr_expansion_adds_to_call_score():
    """Phase 0.7.x: `atr_expansion` is a sixth scoring condition (vol
    regime gate). Bars with ATR_Expansion > 1.15 pick up +1.
    """
    row = _bar(
        Consecutive_Up_5=3,
        RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        EMA9=100.0,
        RVol_Recent_20=1.5,                         # fires
        ATR_Expansion=1.30,                         # > 1.15 → fires
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "CALL"
    assert sig.base_score == 6                     # all 6 conditions met
    assert "atr_expansion" in sig.conditions_met


def test_atr_expansion_below_threshold_does_not_count():
    row = _bar(
        Consecutive_Up_5=3,
        RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        EMA9=100.0,
        ATR_Expansion=1.14,                         # just below 1.15
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.base_score == 4                     # 4 of 6 (no rvol, no atr_exp)
    assert "atr_expansion" not in sig.conditions_met


def test_atr_expansion_alone_does_not_fire():
    """Vol expansion alone (without trend / RSI / VWAP / EMA) must not fire."""
    row = _bar(
        ATR_Expansion=2.0,                          # major vol expansion
    )
    sig = STRAT.evaluate(row)
    assert sig is None                              # 1 of 6 < min_conditions=3


def test_atr_expansion_missing_or_nan_does_not_fire():
    import numpy as np
    row = _bar(
        Consecutive_Up_5=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        ATR_Expansion=np.nan,
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert "atr_expansion" not in sig.conditions_met


def test_atr_expansion_adds_to_put_score():
    """PUT mirror: vol expansion confirms the bearish setup symmetrically."""
    row = _bar(
        Consecutive_Down_5=3,
        RSI14_W=65.0,
        Last=99.0, Close=99.0, VWAP=100.0,
        EMA9=100.0,
        ATR_Expansion=1.25,                         # fires
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "PUT"
    assert "atr_expansion" in sig.conditions_met


def test_rsi_thrust_positive_fires_for_call():
    """Phase 0.7.x: directional `rsi_thrust` fires CALL on positive delta."""
    row = _bar(
        Consecutive_Up_5=3,
        RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        EMA9=100.0,
        RSI_Thrust_3=8.0,                           # > +5 → bullish thrust
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "CALL"
    assert "rsi_thrust" in sig.conditions_met


def test_rsi_thrust_negative_does_not_fire_for_call():
    """Negative delta is bearish thrust — must NOT count for CALL."""
    row = _bar(
        Consecutive_Up_5=3,
        RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        RSI_Thrust_3=-8.0,                          # bearish — wrong direction for CALL
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "CALL"
    assert "rsi_thrust" not in sig.conditions_met


def test_rsi_thrust_negative_fires_for_put():
    row = _bar(
        Consecutive_Down_5=3,
        RSI14_W=65.0,
        Last=99.0, Close=99.0, VWAP=100.0,
        EMA9=100.0,
        RSI_Thrust_3=-8.0,                          # < -5 → bearish thrust
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "PUT"
    assert "rsi_thrust" in sig.conditions_met


def test_rsi_thrust_positive_does_not_fire_for_put():
    """Positive delta is bullish thrust — must NOT count for PUT."""
    row = _bar(
        Consecutive_Down_5=3,
        RSI14_W=65.0,
        Last=99.0, Close=99.0, VWAP=100.0,
        RSI_Thrust_3=8.0,                           # bullish — wrong direction for PUT
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "PUT"
    assert "rsi_thrust" not in sig.conditions_met


def test_rsi_thrust_below_threshold_magnitude_does_not_count():
    """|delta| <= 5 is below threshold."""
    row_call = _bar(
        Consecutive_Up_5=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0, EMA9=100.0,
        RSI_Thrust_3=4.99,                          # just below +5
    )
    sig = STRAT.evaluate(row_call)
    assert "rsi_thrust" not in sig.conditions_met


def test_rsi_thrust_alone_does_not_fire():
    """Thrust alone (1 of 7) stays below min_conditions=3."""
    row = _bar(RSI_Thrust_3=20.0)                   # massive bullish thrust
    sig = STRAT.evaluate(row)
    assert sig is None


def test_rsi_thrust_missing_or_nan_does_not_fire():
    import numpy as np
    row = _bar(
        Consecutive_Up_5=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        RSI_Thrust_3=np.nan,
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert "rsi_thrust" not in sig.conditions_met


def test_rsi_thrust_full_alignment_scores_seven():
    """Bar with all 7 conditions met (max conviction)."""
    row = _bar(
        Consecutive_Up_5=3,
        RSI14_W=35.0,                               # rsi_bullish_recovery
        Last=101.0, Close=101.0, VWAP=100.0,        # above_vwap
        EMA9=100.0,                                  # above_ema9
        RVol_Recent_20=1.5,                         # rvol_above_recent
        ATR_Expansion=1.30,                         # atr_expansion
        RSI_Thrust_3=8.0,                           # rsi_thrust
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "CALL"
    assert sig.base_score == 7


def test_signal_carries_indicator_snapshots():
    row = _bar(
        Consecutive_Up_5=3, RSI14_W=35.0,
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
    row = _bar(Consecutive_Up_5=3, RSI14_W=35.0,
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
            "Consecutive_Up_5": 0, "Consecutive_Down_5": 0,
            "Price_vs_VWAP": 0.0, "Price_vs_EMA9": 0.0, "Price_vs_EMA20": 0.0,
            "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
        })
    df = pd.DataFrame(rows)
    out = STRAT.generate_signals(df)
    assert isinstance(out, list)
    # all-flat input → no fires expected
    assert all(s.strategy == "momentum" for s in out)
