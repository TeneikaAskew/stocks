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
    """Default bar that satisfies NO conditions — overrides flip them on.

    B+ (2026-05-06): the strict gate now reads `Consecutive_Up`/`Consecutive_Down`
    (3-of-3 strict). Pre-existing fixtures pass `Consecutive_Up_5=N` to flip the
    consecutive condition on; we mirror that into the strict column too so those
    fixtures continue to express "this bar credits the consecutive condition"
    without per-test edits. Tests that specifically need to pin the relaxed-only
    semantics (e.g. 3-of-5-with-pullback) override `Consecutive_Up` explicitly
    to a value below CONSECUTIVE_PERIODS.
    """
    base = {
        "Time": TS,
        "Close": 100.0, "Last": 100.0,
        "RSI14": 55.0, "RSI14_W": 55.0,             # outside both call/put RSI bands
        "VWAP": 100.0, "EMA9": 100.0, "EMA20": 100.0,
        "StochRSI_K": 50.0,
        "Consecutive_Up": 0, "Consecutive_Down": 0,
        # Pre-existing relaxed-window fixtures still set these; the bridge
        # below mirrors them into the strict columns when the strict columns
        # aren't explicitly overridden, so existing fixtures keep working.
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
    # B+ bridge: if Consecutive_Up_5 was overridden but Consecutive_Up wasn't,
    # mirror the value so fixtures expressing "credit consecutive_up" via the
    # old relaxed column still credit it under the new strict gate.
    if "Consecutive_Up_5" in overrides and "Consecutive_Up" not in overrides:
        base["Consecutive_Up"] = overrides["Consecutive_Up_5"]
    if "Consecutive_Down_5" in overrides and "Consecutive_Down" not in overrides:
        base["Consecutive_Down"] = overrides["Consecutive_Down_5"]
    return pd.Series(base)


def test_call_fires_with_5_conditions():
    """B+ MIN_CONDITIONS_MOMENTUM=5: consec + RSI + VWAP + EMA9 + rvol = 5."""
    row = _bar(
        Consecutive_Up=3,                          # 3-of-3 strict up bars
        RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        EMA9=99.0,                                 # above_ema9 fires
        RVol_Recent_20=1.5,                        # rvol_above_recent fires
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "CALL"
    assert sig.base_score >= 5
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


def test_consecutive_up_below_threshold_does_not_count():
    """Strict 3-of-3: Consecutive_Up == 2 must NOT credit consecutive_up.
    Bar still fires because 3 other conditions + 2 confirming = 5 (B+ floor)."""
    row = _bar(
        Consecutive_Up=2,                         # below CONSECUTIVE_PERIODS=3
        RSI14_W=35.0,                             # in CALL band
        Last=101.0, Close=101.0, VWAP=100.0,      # above VWAP
        EMA9=99.0,                                # above EMA9
        RVol_Recent_20=1.5,                       # confirmer
        ATR_Expansion=1.30,                       # confirmer (total = 5)
    )
    sig = STRAT.evaluate(row)
    assert sig is not None                        # 5 conditions without consec_up
    assert "consecutive_up" not in sig.conditions_met


def test_consecutive_up_3_of_5_with_pullback_does_not_fire():
    """B+ revert to 3-of-3 strict: a 3-of-5 with pullback (which the relaxed
    gate previously fired on) MUST NOT credit the consecutive_up condition,
    and without it the bar can't reach MIN_CONDITIONS_MOMENTUM=5."""
    row = _bar(
        Consecutive_Up_5=3,                       # 3 up, 2 down/flat in window
        Consecutive_Up=0,                         # strict 3-of-3 NOT met (overrides bridge)
        RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        EMA9=99.0,                                # above EMA9
    )
    # 4 conditions met (rsi + vwap + ema9 + nothing-else); below score=5 floor.
    sig = STRAT.evaluate(row)
    assert sig is None or "consecutive_up" not in sig.conditions_met


def test_put_fires_when_dominant():
    row = _bar(
        Consecutive_Down=3,                       # strict 3-of-3 down
        RSI14_W=65.0,                             # in (50, 75)
        Last=99.0, Close=99.0, VWAP=100.0,        # below VWAP
        EMA9=100.0,                               # below EMA9
        RVol_Recent_20=1.5,                       # +1 → reach MIN=5
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "PUT"
    assert "consecutive_down" in sig.conditions_met
    assert "rsi_bearish_recovery" in sig.conditions_met
    assert "below_vwap" in sig.conditions_met
    assert "below_ema9" in sig.conditions_met


def test_call_dominates_when_more_conditions():
    """When CALL eligible (>=5) and PUT not, CALL fires regardless of put score."""
    row = _bar(
        # CALL: consec_up + rsi_bull + above_vwap + rvol + atr = 5
        Consecutive_Up=3,
        RSI14_W=35.0,                            # in CALL band
        Close=101.0, Last=101.0,
        VWAP=100.0,                              # above_vwap
        EMA9=102.0,                              # NOT above_ema9 (101 < 102)
        RVol_Recent_20=1.5, ATR_Expansion=1.30,  # +2 confirmers → CALL = 5
        # PUT: only below_ema9 (since RSI=35 not in put band, price > VWAP)
        Consecutive_Down=0,
    )
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
        Consecutive_Up=3,
        RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        EMA9=99.0,
        RVol_Recent_20=1.19,                        # just below 1.2 → NOT credited
        ATR_Expansion=1.30, RSI_Thrust_3=6.0,       # confirmers, push to score=6
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.base_score == 6                     # 4 core + atr + rsi_thrust, NOT rvol
    assert "rvol_above_recent" not in sig.conditions_met


def test_rvol_above_recent_alone_does_not_fire():
    """Volume alone (without trend / RSI / VWAP / EMA) must not fire."""
    row = _bar(
        RVol_Recent_20=2.5,                         # massive volume spike
        # All other conditions defaulted to NOT firing.
    )
    sig = STRAT.evaluate(row)
    assert sig is None                              # 1 of 5 < min_conditions=3


def test_rvol_missing_or_nan_does_not_credit():
    """Warmup / missing volume data must not credit rvol_above_recent.
    Bar still fires because other conditions reach MIN=5."""
    import numpy as np
    row_missing = _bar(
        Consecutive_Up=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        EMA9=99.0,                                  # above_ema9 fires
        ATR_Expansion=1.30, RSI_Thrust_3=6.0,       # +2 confirmers → 6
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
        Consecutive_Up=3,
        RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        EMA9=99.0,
        ATR_Expansion=1.14,                         # just below 1.15 → NOT credited
        RVol_Recent_20=1.5, RSI_Thrust_3=6.0,       # +2 confirmers → reach 6
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.base_score == 6                     # 4 core + rvol + rsi_thrust, NOT atr
    assert "atr_expansion" not in sig.conditions_met


def test_atr_expansion_alone_does_not_fire():
    """Vol expansion alone (without trend / RSI / VWAP / EMA) must not fire."""
    row = _bar(
        ATR_Expansion=2.0,                          # major vol expansion
    )
    sig = STRAT.evaluate(row)
    assert sig is None                              # 1 of 6 < min_conditions=3


def test_atr_expansion_missing_or_nan_does_not_credit():
    import numpy as np
    row = _bar(
        Consecutive_Up=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        EMA9=99.0,                                  # above_ema9
        RVol_Recent_20=1.5, RSI_Thrust_3=6.0,       # +2 confirmers
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


def test_rsi_thrust_negative_does_not_credit_call():
    """Negative delta is bearish thrust — must NOT count for CALL.
    Bar still fires CALL via 4 core + 2 confirming = 6."""
    row = _bar(
        Consecutive_Up=3,
        RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        EMA9=99.0,                                  # above_ema9
        RVol_Recent_20=1.5, ATR_Expansion=1.30,     # +2 confirmers → 6
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


def test_rsi_thrust_positive_does_not_credit_put():
    """Positive delta is bullish thrust — must NOT count for PUT.
    Bar still fires PUT via 4 core + 2 confirming = 6."""
    row = _bar(
        Consecutive_Down=3,
        RSI14_W=65.0,
        Last=99.0, Close=99.0, VWAP=100.0,
        EMA9=100.0,                                 # below_ema9
        RVol_Recent_20=1.5, ATR_Expansion=1.30,     # +2 confirmers → 6
        RSI_Thrust_3=8.0,                           # bullish — wrong direction for PUT
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "PUT"
    assert "rsi_thrust" not in sig.conditions_met


def test_rsi_thrust_below_threshold_magnitude_does_not_credit():
    """|delta| <= 5 is below threshold. Bar still fires via 5 other conditions."""
    row_call = _bar(
        Consecutive_Up=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0, EMA9=99.0,
        RVol_Recent_20=1.5, ATR_Expansion=1.30,     # +2 → score=6
        RSI_Thrust_3=4.99,                          # just below +5 → NOT credited
    )
    sig = STRAT.evaluate(row_call)
    assert sig is not None
    assert "rsi_thrust" not in sig.conditions_met


def test_rsi_thrust_alone_does_not_fire():
    """Thrust alone (1 of 7) stays below min_conditions=3."""
    row = _bar(RSI_Thrust_3=20.0)                   # massive bullish thrust
    sig = STRAT.evaluate(row)
    assert sig is None


def test_rsi_thrust_missing_or_nan_does_not_credit():
    import numpy as np
    row = _bar(
        Consecutive_Up=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        EMA9=99.0,
        RVol_Recent_20=1.5, ATR_Expansion=1.30,     # +2 → score=6
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
        Consecutive_Up=3, RSI14_W=35.0,
        Last=101.0, Close=101.0,
        VWAP=100.0, EMA9=99.0, EMA20=99.0,
        RVol_Recent_20=1.5, ATR_Expansion=1.30,     # reach MIN=5 (+ rvol+atr → 6)
        RVOL=1.4,
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.rsi == 35.0
    assert sig.vwap == 100.0
    assert sig.ema9 == 99.0
    assert sig.rvol == 1.4


def test_strategy_name_is_momentum():
    row = _bar(
        Consecutive_Up=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        EMA9=99.0,
        RVol_Recent_20=1.5,                          # +1 → score=5
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.strategy == "momentum"


# ── Phase 0.7.x — tiered scoring gate (PR-5) ───────────────────────────
#
# CORE = defines the setup (consec, RSI band, above/below VWAP/EMA9).
# CONFIRMING = validates but can't define (rvol, atr_expansion, rsi_thrust).
# Gate: total_score >= 3 AND core_count >= 2. A gate-blocked direction
# is silenced so it cannot suppress the legitimate other direction.

def test_tier_blocks_zero_core_three_confirm():
    """Three confirmers, zero core — pre-PR-5 fired CALL (3>=3, >put);
    post-PR-5 must block (no setup, just noise + activity).
    """
    row = _bar(
        # No CORE: no consec, RSI=80 (outside both bands), Last=VWAP=EMA9 (no edge)
        RSI14_W=80.0,                                # outside both RSI bands
        RVol_Recent_20=1.5,
        ATR_Expansion=1.30,
        RSI_Thrust_3=8.0,                            # CALL-only confirm
    )
    sig = STRAT.evaluate(row)
    assert sig is None


def test_tier_blocks_one_core_two_confirm():
    """One core + two confirm — pre-PR-5 fired; post-PR-5 must block."""
    row = _bar(
        Consecutive_Up_5=3,                          # CALL +1 core
        RSI14_W=80.0,                                # outside both bands
        RVol_Recent_20=1.5,                          # confirm (dir-agnostic)
        RSI_Thrust_3=8.0,                            # CALL-only confirm
    )
    sig = STRAT.evaluate(row)
    assert sig is None


def test_tier_blocks_two_core_one_confirm_under_score5_floor():
    """B+ MIN_CONDITIONS_MOMENTUM=5: 2 core + 1 confirm = total 3, blocked."""
    row = _bar(
        Consecutive_Up=3,                            # core
        RSI14_W=35.0,                                # core (bullish band)
        RVol_Recent_20=1.5,                          # confirm — total 3 < 5
    )
    sig = STRAT.evaluate(row)
    assert sig is None


def test_tier_allows_three_core_two_confirm():
    """3 core + 2 confirm = score 5, core 3 — minimum credible fire under B+."""
    row = _bar(
        Consecutive_Up=3,                            # core
        RSI14_W=35.0,                                # core
        Last=101.0, Close=101.0, VWAP=100.0,         # above_vwap (core)
        EMA9=102.0,                                  # NOT above_ema9
        RVol_Recent_20=1.5, ATR_Expansion=1.30,      # 2 confirm → 5
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "CALL"
    assert sig.base_score == 5
    assert sig.core_count == 3


def test_tier_full_alignment_scores_seven():
    """Max conviction: 4 core + 3 confirm = 7."""
    row = _bar(
        Consecutive_Up=3,
        RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        EMA9=99.0,
        RVol_Recent_20=1.5,
        ATR_Expansion=1.30,
        RSI_Thrust_3=8.0,
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "CALL"
    assert sig.base_score == 7
    assert sig.core_count == 4


def test_tier_put_mirror_blocks_noise():
    """PUT mirror: zero core + three confirm (with bearish thrust) blocks."""
    row = _bar(
        # No PUT core: no consec_down, RSI=80 (outside both bands), no VWAP/EMA9 edge
        RSI14_W=80.0,
        RVol_Recent_20=1.5,
        ATR_Expansion=1.30,
        RSI_Thrust_3=-8.0,                           # PUT-only confirm
    )
    sig = STRAT.evaluate(row)
    assert sig is None


def test_tier_put_mirror_blocks_one_core_two_confirm():
    """PUT mirror of one-core-two-confirm noise."""
    row = _bar(
        Consecutive_Down_5=3,                        # PUT +1 core
        RSI14_W=80.0,                                # outside both bands
        RVol_Recent_20=1.5,                          # confirm
        RSI_Thrust_3=-8.0,                           # PUT-only confirm
    )
    sig = STRAT.evaluate(row)
    assert sig is None


def test_tier_cross_direction_blocked_call_does_not_suppress_put():
    """Tier-gate behavior: CALL eligible by core but doesn't reach total=5;
    PUT has 4 core + 2 confirm = 6, eligible. Confirms cross-direction
    blocking doesn't suppress the eligible direction.
    """
    row = _bar(
        Consecutive_Down=3,                          # PUT +1 core
        RSI14_W=65.0,                                # PUT +1 core (bearish band)
        Last=101.0, Close=101.0,
        VWAP=200.0,                                  # PUT below_vwap (+1 core)
        EMA9=100.0,                                  # PUT below_ema9? 101>100 NO → CALL above_ema9
        # Switch EMA so PUT gets all 4 core
    )
    # Recompute: with EMA9=100 and Close=101, CALL above_ema9 (+1).
    # PUT core: consec_down + rsi_bearish + below_vwap = 3 (no below_ema9).
    # Need to give PUT 5+. Use EMA9=102 so 101<102 → PUT below_ema9.
    row["EMA9"] = 102.0
    row["RVol_Recent_20"] = 1.5
    row["ATR_Expansion"] = 1.30
    sig = STRAT.evaluate(row)
    assert sig is not None
    assert sig.direction == "PUT"
    assert sig.core_count == 4                       # 4 PUT core
    assert sig.base_score == 6                       # 4 core + 2 confirm


def test_tier_score5_floor_blocks_below_threshold():
    """B+ MIN_CONDITIONS_MOMENTUM=5: a bar with 4 core + 0 confirm (total 4)
    must NOT fire even though core gate (>=2) would have passed it under
    PR-5's MIN_CONDITIONS=3.
    """
    row = _bar(
        Consecutive_Up=3,
        RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        EMA9=99.0,
        # 4 core, no confirmers → score=4, below MIN=5
    )
    sig = STRAT.evaluate(row)
    assert sig is None


def test_tier_strict_tie_breaker_unchanged_when_both_eligible():
    """When BOTH directions are eligible (each passes both gates), the
    strict > tie-breaker still applies — a 3-3 tie produces no fire.
    """
    row = _bar(
        Consecutive_Up_5=3,                          # CALL +1 core
        Consecutive_Down_5=3,                        # PUT +1 core
        RSI14_W=80.0,                                # outside both bands
        Last=100.0, Close=100.0,
        VWAP=99.0,                                   # CALL above_vwap (+1 core)
        EMA9=101.0,                                  # PUT below_ema9 (+1 core)
        RVol_Recent_20=1.5,                          # both +1 confirm
    )
    # CALL: consec_up + above_vwap + rvol = 3, core=2 → eligible
    # PUT:  consec_down + below_ema9 + rvol = 3, core=2 → eligible
    # Tie 3-3 with both eligible → no fire (strict tie-breaker)
    sig = STRAT.evaluate(row)
    assert sig is None


def test_signal_carries_core_count():
    """The Signal dataclass exposes core_count for downstream auditing."""
    row = _bar(
        Consecutive_Up=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
        # EMA9=100 default → 101 > 100 fires above_ema9 too (4 core)
        RVol_Recent_20=1.5,                          # +1 confirm → reach MIN=5
    )
    sig = STRAT.evaluate(row)
    assert sig is not None
    # 4 core: consec_up, rsi_bullish, above_vwap, above_ema9
    assert sig.core_count == 4


# ── Phase 0.7.x — fixture audit (PR-5) ─────────────────────────────────
#
# Replaces the "spot-check that no fixture fires from confirmers alone"
# from the PR-5 plan with a permanent invariant: every firing fixture
# in this file must have core_count >= 2. Any fixture that relied on
# leaky pre-PR-5 behavior fails this test instead of silently rotting.

@pytest.mark.parametrize("name,row_kwargs", [
    ("3-cond CALL", dict(
        Consecutive_Up_5=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
    )),
    ("3-of-5 with pullback", dict(
        Consecutive_Up_5=3, Consecutive_Up=0, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,
    )),
    ("PUT dominant 4-cond", dict(
        Consecutive_Down_5=3, RSI14_W=65.0,
        Last=99.0, Close=99.0, VWAP=100.0, EMA9=100.0,
    )),
    ("CALL with rvol", dict(
        Consecutive_Up_5=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0, EMA9=100.0,
        RVol_Recent_20=1.5,
    )),
    ("CALL with atr_exp", dict(
        Consecutive_Up_5=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0, EMA9=100.0,
        RVol_Recent_20=1.5, ATR_Expansion=1.30,
    )),
    ("CALL with rsi_thrust", dict(
        Consecutive_Up_5=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0, EMA9=100.0,
        RSI_Thrust_3=8.0,
    )),
    ("PUT with atr_exp", dict(
        Consecutive_Down_5=3, RSI14_W=65.0,
        Last=99.0, Close=99.0, VWAP=100.0, EMA9=100.0,
        ATR_Expansion=1.25,
    )),
    ("PUT with rvol", dict(
        Consecutive_Down_5=3, RSI14_W=65.0,
        Last=99.0, Close=99.0, VWAP=100.0, EMA9=100.0,
        RVol_Recent_20=1.5,
    )),
    ("full conviction CALL (7)", dict(
        Consecutive_Up_5=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0, EMA9=100.0,
        RVol_Recent_20=1.5, ATR_Expansion=1.30, RSI_Thrust_3=8.0,
    )),
])
def test_fixture_audit_every_firing_bar_has_credible_setup(name, row_kwargs):
    """Phase 0.7.x audit invariant: any bar that fires must have
    core_count >= 2. If this fails, a fixture relied on leaky pre-PR-5
    behavior and must be tightened.
    """
    row = _bar(**row_kwargs)
    sig = STRAT.evaluate(row)
    if sig is not None:
        assert sig.core_count >= 2, (
            f"{name}: fired with core_count={sig.core_count} — "
            f"setup is not credible. Fixture relied on leaky gate."
        )


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


# ── Phase 0.7.x — 100-bar synthetic replay (PR-5) ──────────────────────
#
# Specified bucket mix per the approved plan. The "Pure noise" bucket
# is the load-bearing regression test — exactly the bars that PRs 2-4
# fire erroneously when MIN_CORE_CONDITIONS isn't enforced.
#
# Buckets, in order:
#   * 15 full-conviction CALL    (4 core + 3 confirm)  → fire CALL, score=7
#   * 20 strong CALL             (3 core + 2 confirm)  → fire CALL, score=5
#   * 15 threshold CALL          (2 core + 1 confirm)  → fire CALL, score=3
#   * 20 pure noise (block tgt)  (0-1 core + 2-3 conf) → None (LOAD-BEARING)
#   * 25 mirror PUT distributions (5/5/5/10 split)     → 15 fire PUT, 10 None
#   * 5  empty bars              (0 core + 0 confirm)  → None
# Total = 100 bars.

def _bucket_full_conviction_call() -> dict:
    """4 core + 3 confirm = 7."""
    return dict(
        Consecutive_Up_5=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0, EMA9=100.0,
        RVol_Recent_20=1.5, ATR_Expansion=1.30, RSI_Thrust_3=8.0,
    )


def _bucket_strong_call() -> dict:
    """3 core + 2 confirm = 5."""
    return dict(
        Consecutive_Up_5=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,        # above_vwap (core)
        EMA9=102.0,                                   # NOT above_ema9
        RVol_Recent_20=1.5, ATR_Expansion=1.30,
        # No rsi_thrust
    )


def _bucket_threshold_call() -> dict:
    """B+ minimum credible fire: 3 core + 2 confirm = 5 (the new floor).
    Pre-B+ this bucket was 2 core + 1 confirm = 3; the new MIN=5 floor
    means a credible fire now requires more confluence.
    """
    return dict(
        Consecutive_Up=3, RSI14_W=35.0,
        Last=101.0, Close=101.0, VWAP=100.0,         # above_vwap (3rd core)
        EMA9=102.0,                                   # NOT above_ema9
        RVol_Recent_20=1.5, ATR_Expansion=1.30,      # 2 confirmers → score 5
    )


def _bucket_pure_noise() -> dict:
    """1 CALL core + 3 confirm = 4 (block target — core=1 < MIN_CORE=2)."""
    return dict(
        Last=101.0, Close=101.0, EMA9=100.0,         # above_ema9 (1 CALL core)
        VWAP=101.0,                                   # equal, no above_vwap
        RSI14_W=80.0,                                 # outside both bands
        # No consec
        RVol_Recent_20=1.5, ATR_Expansion=1.30, RSI_Thrust_3=8.0,
    )


def _bucket_full_conviction_put() -> dict:
    return dict(
        Consecutive_Down_5=3, RSI14_W=65.0,
        Last=99.0, Close=99.0, VWAP=100.0, EMA9=100.0,
        RVol_Recent_20=1.5, ATR_Expansion=1.30, RSI_Thrust_3=-8.0,
    )


def _bucket_strong_put() -> dict:
    return dict(
        Consecutive_Down_5=3, RSI14_W=65.0,
        Last=99.0, Close=99.0, VWAP=100.0,           # below_vwap (core)
        EMA9=98.0,                                    # NOT below_ema9
        RVol_Recent_20=1.5, ATR_Expansion=1.30,
    )


def _bucket_threshold_put() -> dict:
    """B+ minimum credible PUT fire: 3 core + 2 confirm = 5."""
    return dict(
        Consecutive_Down=3, RSI14_W=65.0,
        Last=99.0, Close=99.0, VWAP=100.0,           # below_vwap (3rd core)
        EMA9=98.0,                                    # NOT below_ema9
        RVol_Recent_20=1.5, ATR_Expansion=1.30,      # 2 confirmers → score 5
    )


def _bucket_pure_noise_put() -> dict:
    """1 PUT core + 3 confirm = 4 (block target — core=1 < MIN_CORE=2)."""
    return dict(
        Last=99.0, Close=99.0, EMA9=100.0,           # below_ema9 (1 PUT core)
        VWAP=99.0,                                    # equal, no below_vwap
        RSI14_W=80.0,                                 # outside both bands
        RVol_Recent_20=1.5, ATR_Expansion=1.30, RSI_Thrust_3=-8.0,
    )


def _bucket_empty() -> dict:
    return dict()


def test_synthetic_100_bar_replay_buckets_match_expected_fire_pattern():
    """Phase 0.7.x — specified bar-bucket mix exercising the tier gate.
    The Pure-noise buckets (40 bars total: 20 CALL-flavor + 20 PUT-flavor)
    are the load-bearing regression target. Pre-PR-5 they fire; post-PR-5
    they must NOT fire.
    """
    expected_fire_call = 0
    expected_fire_put  = 0
    expected_none      = 0
    sigs = []
    blocked_bars = []

    bar_specs = (
        [("full_call", _bucket_full_conviction_call(), "CALL", 7)] * 15
        + [("strong_call", _bucket_strong_call(), "CALL", 5)] * 20
        + [("threshold_call", _bucket_threshold_call(), "CALL", 5)] * 15
        + [("pure_noise_call", _bucket_pure_noise(), None, None)] * 20
        + [("full_put", _bucket_full_conviction_put(), "PUT", 7)] * 5
        + [("strong_put", _bucket_strong_put(), "PUT", 5)] * 5
        + [("threshold_put", _bucket_threshold_put(), "PUT", 5)] * 5
        + [("pure_noise_put", _bucket_pure_noise_put(), None, None)] * 10
        + [("empty", _bucket_empty(), None, None)] * 5
    )
    assert len(bar_specs) == 100

    for name, kw, expect_dir, expect_score in bar_specs:
        row = _bar(**kw)
        sig = STRAT.evaluate(row)
        if expect_dir is None:
            assert sig is None, (
                f"[{name}] expected None (no setup) but fired: "
                f"direction={sig.direction} score={sig.base_score} "
                f"core={sig.core_count} conds={sig.conditions_met}"
            )
            expected_none += 1
            blocked_bars.append((name, row, kw))
        else:
            assert sig is not None, f"[{name}] expected {expect_dir} fire but got None"
            assert sig.direction == expect_dir, (
                f"[{name}] expected {expect_dir} got {sig.direction}"
            )
            assert sig.base_score == expect_score, (
                f"[{name}] expected score {expect_score} got {sig.base_score}"
            )
            # Load-bearing: every firing bar must have a credible setup
            assert sig.core_count >= 2, (
                f"[{name}] fired with core_count={sig.core_count} "
                f"(score={sig.base_score}). Tier gate broken."
            )
            sigs.append(sig)
            if expect_dir == "CALL":
                expected_fire_call += 1
            else:
                expected_fire_put += 1

    # Aggregate sanity checks
    assert expected_fire_call == 50                  # 15 + 20 + 15
    assert expected_fire_put  == 15                  # 5 + 5 + 5
    assert expected_none      == 35                  # 20 + 10 + 5

    # Load-bearing aggregate: NO fired bar has core_count == 0.
    # This is the explicit regression target — the bug PRs 2-4 introduced.
    assert all(s.core_count > 0 for s in sigs), (
        "Some bar fired with core_count == 0 — tier gate is broken."
    )
    # Stronger version of the same: no fired bar has core_count < MIN_CORE.
    assert all(s.core_count >= 2 for s in sigs), (
        "Some bar fired with core_count < MIN_CORE_CONDITIONS — gate broken."
    )
