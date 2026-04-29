"""Unit tests for the deterministic trade planner.

These exist *because* the goal of trade_planner is reproducibility —
the same inputs must always produce the same numbers. So every recipe
is exercised against a known-good output, and the math is verified
end-to-end (entry -> stop -> R -> targets).
"""

from __future__ import annotations

import pytest

from lib.agents.trade_planner import (
    PlanContext,
    compute_persona_plans,
    context_from_bundle,
)


# ───────────────────────────────────────────────────────────────────────────
# A representative "AVGO Apr 7" context — the canonical trade we've been
# benchmarking. close=$334, ATR=$12.6, trigger above the prior day high.
# ───────────────────────────────────────────────────────────────────────────


def _avgo_apr7_ctx(direction: str = "long", conviction: str = "medium") -> PlanContext:
    return PlanContext(
        direction=direction,  # type: ignore[arg-type]
        conviction=conviction,  # type: ignore[arg-type]
        close=333.97,
        atr=12.6,
        trigger_high=316.40,
        trigger_low=310.28,
        sma_200=328.59,
        prior_swing_low=310.28,
        ftfc_score=1.0,
        high_impact_catalyst_in_window=True,
        analog_median_day_5_pct=1.97,
    )


# ─── Aggressive recipe ────────────────────────────────────────────────────


def test_aggressive_uses_2_atr_stop_and_5R_top_target():
    ctx = _avgo_apr7_ctx()
    plans = compute_persona_plans(ctx)
    agg = next(p for p in plans if p.persona == "aggressive")
    # Entry: trigger to trigger + 0.5 ATR
    assert agg.entry_zone.low == pytest.approx(316.40, abs=0.01)
    assert agg.entry_zone.high == pytest.approx(316.40 + 0.5 * 12.6, abs=0.01)
    midpoint = (agg.entry_zone.low + agg.entry_zone.high) / 2
    # Stop: 2 ATR below midpoint
    assert agg.stop == pytest.approx(midpoint - 2.0 * 12.6, abs=0.01)
    risk = midpoint - agg.stop
    # Targets: 2R, 3.5R, 5R (last may be stretched by analog)
    assert agg.targets[0] == pytest.approx(midpoint + 2.0 * risk, abs=0.01)
    assert agg.targets[1] == pytest.approx(midpoint + 3.5 * risk, abs=0.01)
    assert agg.targets[2] >= midpoint + 5.0 * risk - 0.05
    # Size: 1.2× on medium conviction
    assert agg.position_size_pct == pytest.approx(1.2, abs=0.01)
    # Sane ordering
    assert agg.targets[0] < agg.targets[1] < agg.targets[2]
    assert agg.stop < agg.entry_zone.low


def test_aggressive_size_scales_with_conviction():
    high = compute_persona_plans(_avgo_apr7_ctx(conviction="high"))
    med = compute_persona_plans(_avgo_apr7_ctx(conviction="medium"))
    low = compute_persona_plans(_avgo_apr7_ctx(conviction="low"))
    sizes = [next(p for p in plans if p.persona == "aggressive").position_size_pct
             for plans in (high, med, low)]
    assert sizes == [1.5, 1.2, 0.8]


# ─── Neutral recipe ───────────────────────────────────────────────────────


def test_neutral_is_canonical_1R_2R_3R():
    ctx = _avgo_apr7_ctx()
    plans = compute_persona_plans(ctx)
    neut = next(p for p in plans if p.persona == "neutral")
    # Entry: trigger to trigger + 0.25 ATR
    assert neut.entry_zone.low == pytest.approx(316.40, abs=0.01)
    assert neut.entry_zone.high == pytest.approx(316.40 + 0.25 * 12.6, abs=0.01)
    midpoint = (neut.entry_zone.low + neut.entry_zone.high) / 2
    # Stop: ~1 ATR below midpoint (allow rounding wobble — the planner
    # rounds stop and entry to 2 decimals, so the recomputed risk
    # drifts a penny or two)
    assert neut.stop == pytest.approx(midpoint - 12.6, abs=0.05)
    risk = midpoint - neut.stop
    # Targets: 1R / 2R / 3R
    assert neut.targets[0] == pytest.approx(midpoint + 1.0 * risk, abs=0.05)
    assert neut.targets[1] == pytest.approx(midpoint + 2.0 * risk, abs=0.05)
    assert neut.targets[2] == pytest.approx(midpoint + 3.0 * risk, abs=0.05)
    assert neut.position_size_pct == 1.0


# ─── Conservative recipe ──────────────────────────────────────────────────


def test_conservative_anchors_stop_at_structure():
    ctx = _avgo_apr7_ctx()  # prior_swing_low=310.28, sma_200=328.59
    plans = compute_persona_plans(ctx)
    cons = next(p for p in plans if p.persona == "conservative")
    # Entry: trigger + 0.1 ATR up to trigger + 0.4 ATR
    assert cons.entry_zone.low == pytest.approx(316.40 + 0.1 * 12.6, abs=0.01)
    assert cons.entry_zone.high == pytest.approx(316.40 + 0.4 * 12.6, abs=0.01)
    midpoint = (cons.entry_zone.low + cons.entry_zone.high) / 2
    # SMA200 ($328.59) sits ABOVE the entry midpoint ($319.55), so it's
    # not a valid LONG stop — the planner filters it out. Of the
    # remaining candidates (ATR floor at midpoint − 0.7×ATR, prior
    # swing low at 310.28), prior_swing_low is the higher one and wins.
    raw_atr_stop = midpoint - 0.7 * 12.6  # ≈ 310.73
    expected = max(raw_atr_stop, 310.28)  # SMA200 excluded — above entry
    assert cons.stop == pytest.approx(expected, abs=0.05)
    # Targets: 1R / 1.75R only (no T3)
    risk = midpoint - cons.stop
    assert len(cons.targets) == 2
    assert cons.targets[0] == pytest.approx(midpoint + 1.0 * risk, abs=0.05)
    assert cons.targets[1] == pytest.approx(midpoint + 1.75 * risk, abs=0.05)


def test_conservative_catalyst_damper_applied():
    """A high-impact catalyst inside the window should reduce size by
    the damper factor (0.6×). Same context with no catalyst should
    keep the unmultiplied size."""
    with_cat = _avgo_apr7_ctx()
    with_cat.high_impact_catalyst_in_window = True
    no_cat = _avgo_apr7_ctx()
    no_cat.high_impact_catalyst_in_window = False
    cons_with = next(p for p in compute_persona_plans(with_cat) if p.persona == "conservative")
    cons_no = next(p for p in compute_persona_plans(no_cat) if p.persona == "conservative")
    # Damper = 0.6, base medium-conviction = 0.5 → 0.3 vs 0.5
    assert cons_with.position_size_pct == pytest.approx(0.5 * 0.6, abs=0.01)
    assert cons_no.position_size_pct == pytest.approx(0.5, abs=0.01)


def test_conservative_blocks_when_ftfc_too_weak():
    ctx = _avgo_apr7_ctx()
    ctx.ftfc_score = 0.10  # below 0.30 threshold
    cons = next(p for p in compute_persona_plans(ctx) if p.persona == "conservative")
    assert cons.position_size_pct == 0.0
    assert "FTFC" in cons.rationale


def test_conservative_blocks_long_below_sma_200():
    ctx = _avgo_apr7_ctx()
    ctx.close = 320.0   # below SMA200 of 328.59
    cons = next(p for p in compute_persona_plans(ctx) if p.persona == "conservative")
    assert cons.position_size_pct == 0.0
    assert "200-SMA" in cons.rationale


# ─── Edge cases ───────────────────────────────────────────────────────────


def test_flat_direction_returns_no_plans():
    ctx = _avgo_apr7_ctx(direction="flat")
    plans = compute_persona_plans(ctx)
    assert plans == []


def test_missing_atr_falls_back_to_one_pct():
    ctx = _avgo_apr7_ctx()
    ctx.atr = 0.0  # broken upstream
    plans = compute_persona_plans(ctx)
    neut = next(p for p in plans if p.persona == "neutral")
    # stop should still be a legitimate distance from midpoint —
    # roughly 1% × close = ~$3.34
    midpoint = (neut.entry_zone.low + neut.entry_zone.high) / 2
    assert neut.stop < midpoint
    assert (midpoint - neut.stop) >= 1.5  # at least 1.5 USD with $334 close


def test_short_direction_mirrors_long_math():
    ctx = _avgo_apr7_ctx(direction="short")
    ctx.trigger_low = 310.28
    plans = compute_persona_plans(ctx)
    neut = next(p for p in plans if p.persona == "neutral")
    # Entry sits at-or-below the breakdown; stop is ABOVE; targets
    # are BELOW (lower numerical values for a profitable short).
    midpoint = (neut.entry_zone.low + neut.entry_zone.high) / 2
    assert neut.stop > midpoint
    assert neut.targets[0] < midpoint
    assert neut.targets[1] < neut.targets[0]
    assert neut.targets[2] < neut.targets[1]


# ─── Bundle adapter ───────────────────────────────────────────────────────


def test_context_from_bundle_picks_up_canonical_fields():
    bundle = {
        "ticker": "AVGO",
        "market": {
            "close": 333.97,
            "atr_14": 12.6,
            "sma_200": 328.59,
        },
        "strat": {
            "trigger_high": 316.40,
            "trigger_low": 310.28,
            "ftfc_score": 1.0,
        },
        "catalysts": {
            "events": [
                {"impact": "high", "name": "Broadcom rises on AI deals"},
                {"impact": "medium", "name": "Other"},
            ],
        },
        "backtest": {
            "available": True,
            "forward_returns": {"day_5": {"median_pct": 1.97, "n": 9}},
        },
    }
    ctx = context_from_bundle(bundle, direction="long", conviction="medium")
    assert ctx.close == 333.97
    assert ctx.atr == 12.6
    assert ctx.sma_200 == 328.59
    assert ctx.trigger_high == 316.40
    assert ctx.ftfc_score == 1.0
    assert ctx.high_impact_catalyst_in_window is True
    assert ctx.analog_median_day_5_pct == 1.97


# ─── Level-aware trigger + regime selection (PR α) ────────────────────────


from lib.agents.trade_planner import select_trigger_and_regime  # noqa: E402


def _level_ctx(direction="long", **overrides) -> PlanContext:
    """ARM 4/20-ish context with the multi-timeframe level fields populated."""
    base = dict(
        direction=direction,
        conviction="medium",
        close=166.73,            # 4/17 close
        atr=8.64,
        trigger_high=168.35,     # legacy fallback
        trigger_low=162.73,
        ftfc_score=1.0,
        # New multi-tf fields
        effective_pdh=168.35,
        effective_pdl=162.73,
        pwh=168.35, pwl=147.50,
        pmh=166.69, pml=130.00,
        pqh=183.16, pql=124.18,
        pyh=200.00, pyl=95.00,
        pre_high=172.80, pre_low=154.80, pre_vwap=169.28,
        gap_pct=-0.74,
    )
    base.update(overrides)
    return PlanContext(**base)  # type: ignore[arg-type]


def test_select_trigger_normal_inside_day_uses_pdh():
    """Pre-market inside prior-day range → trigger = PDH (canonical)."""
    ctx = _level_ctx(
        pre_vwap=165.0,    # below PDH
        pre_high=167.5, pre_low=164.0,
    )
    regime, trigger, stop_anchor, distance = select_trigger_and_regime(ctx, "long")
    assert regime == "normal"
    assert trigger == pytest.approx(168.35, abs=0.01)  # PDH
    assert stop_anchor is not None
    assert distance is not None and distance < 3.0


def test_select_trigger_walks_above_cleared_pdh():
    """Pre-market above PDH/PWH → trigger walks to next unbroken level."""
    # Pre-market settled at $169.28 — above PDH=$168.35 and PWH=$168.35.
    # Next unbroken level above is PMH=$170 (but we set PMH=166.69 in fixture
    # which is also below). Walking continues to PYH/PWH/etc.
    ctx = _level_ctx(
        pre_vwap=169.28,   # above PDH/PWH
        pre_high=172.80,
        pmh=166.69,        # already below pre_vwap (cleared)
        pqh=180.00,        # next unbroken above
        pyh=200.00,
    )
    regime, trigger, _, distance = select_trigger_and_regime(ctx, "long")
    # Walk skips PDH/PWH (cleared) and PMH (also cleared — pre_high>166.69
    # means this level was touched), pre_high is in candidates above
    # cleared_above=max(169.28, 172.80)=172.80, picks min above 172.80
    # which is PQH=$180 (PMH/PWH/PDH all <= 172.80 — cleared).
    assert trigger is not None
    assert trigger > 169.28  # Strictly above current price
    assert regime in ("normal", "extended")


def test_select_trigger_orb_only_when_all_levels_cleared():
    """AMD 4/24 case: +12% gap, every structural level below pre_close."""
    ctx = _level_ctx(
        close=305.33,            # AMD 4/23 close
        atr=12.50,
        pre_vwap=345.39,         # AMD 4/24 pre-VWAP
        pre_high=352.99, pre_low=334.54,
        gap_pct=11.79,
        # Every level BELOW the pre-market range (cleared)
        effective_pdh=310.22, effective_pdl=299.76,
        pwh=281.05, pwl=242.03,
        pmh=221.33, pml=188.22,
        pqh=266.96, pql=188.22,
        pyh=267.08, pyl=91.87,
    )
    regime, trigger, stop_anchor, distance = select_trigger_and_regime(ctx, "long")
    assert regime == "orb_only"
    assert trigger is None
    assert distance is None
    # Stop anchor is the closest level BELOW the reference price
    assert stop_anchor is not None


def test_select_trigger_extended_when_next_level_far_away():
    """Distance to next unbroken level > 3 ATR → extended regime."""
    ctx = _level_ctx(
        close=170.0,
        atr=2.0,                 # tight ATR
        pre_vwap=170.0,
        pre_high=170.5, pre_low=169.5,
        # Closest level above is PQH=$180, distance=10/2=5 ATR
        effective_pdh=169.0, effective_pdl=165.0,  # cleared
        pwh=169.5, pwl=165.0,                       # cleared
        pmh=169.0, pml=160.0,                       # cleared
        pqh=180.0, pql=160.0,                       # this is the next level
        pyh=200.0, pyl=120.0,
    )
    regime, trigger, _, distance = select_trigger_and_regime(ctx, "long")
    assert regime == "extended"
    assert trigger == pytest.approx(180.0, abs=0.01)
    assert distance is not None and distance >= 3.0


def test_select_trigger_short_mirror():
    """Gap-down: short trigger walks below PDL to next unbroken support."""
    ctx = _level_ctx(
        direction="short",
        close=160.0,
        pre_vwap=159.0,
        pre_high=161.0, pre_low=157.0,
        effective_pdh=170.0, effective_pdl=160.0,
        pwh=170.0, pwl=158.0,    # both at/above pre — first unbroken below = pwl
        pmh=180.0, pml=130.0,
        pqh=190.0, pql=120.0,
        pyh=200.0, pyl=95.00,
    )
    regime, trigger, stop_anchor, distance = select_trigger_and_regime(ctx, "short")
    # Cleared_below = min(159, 157) = 157. Levels strictly < 157:
    # PML=130, PQL=120, PYL=95. Closest = PML=130.
    assert regime in ("normal", "extended")
    assert trigger == pytest.approx(130.0, abs=0.01)
    assert stop_anchor is not None and stop_anchor > 159.0


def test_orb_only_persona_plans_have_zero_size():
    """All three personas return zero size + ORB-wait rationale on orb_only."""
    ctx = _level_ctx(
        close=305.33, atr=12.50, pre_vwap=345.39,
        pre_high=352.99, pre_low=334.54, gap_pct=11.79,
        effective_pdh=310.22, effective_pdl=299.76,
        pwh=281.05, pwl=242.03,
        pmh=221.33, pml=188.22,
        pqh=266.96, pql=188.22,
        pyh=267.08, pyl=91.87,
    )
    plans = compute_persona_plans(ctx)
    assert len(plans) == 3
    for p in plans:
        assert p.regime == "orb_only"
        assert p.position_size_pct == 0.0
        assert p.targets == []
        assert "ORB" in p.rationale


def test_extended_regime_rationale_includes_orb_recommendation():
    """Extended regime plans should call out ORB confirmation in rationale."""
    ctx = _level_ctx(
        close=170.0, atr=2.0, pre_vwap=170.0,
        pre_high=170.5, pre_low=169.5,
        effective_pdh=169.0, effective_pdl=165.0,
        pwh=169.5, pwl=165.0,
        pmh=169.0, pml=160.0,
        pqh=180.0, pql=160.0,    # Trigger 5 ATR away
        pyh=200.0, pyl=120.0,
    )
    plans = compute_persona_plans(ctx)
    neut = next(p for p in plans if p.persona == "neutral")
    assert neut.regime == "extended"
    assert "Extended gap" in neut.rationale
    assert "15-min ORB" in neut.rationale or "ORB" in neut.rationale


def test_normal_regime_falls_back_to_legacy_trigger_when_no_multi_tf():
    """Legacy fixtures with only trigger_high should still produce normal plans."""
    ctx = PlanContext(
        direction="long", conviction="medium",
        close=314.0, atr=12.6,
        trigger_high=316.40, trigger_low=310.28,
        ftfc_score=1.0,
        # No multi-tf levels populated
    )
    regime, trigger, _, _ = select_trigger_and_regime(ctx, "long")
    assert regime == "normal"
    assert trigger == pytest.approx(316.40, abs=0.01)


def test_inside_of_inside_uses_effective_pdh_mother_bar():
    """When prior bar was a strat '1', effective_pdh = mother bar high."""
    # PDH from yesterday is $165 (an inside bar). Mother bar from D-2 is
    # $172. effective_pdh should be $172. The level walk uses effective_pdh.
    ctx = _level_ctx(
        close=160.0,
        pre_vwap=164.0,
        pre_high=164.5, pre_low=160.0,
        effective_pdh=172.0,   # mother bar high — replaces yesterday's tighter $165
        effective_pdl=158.0,
        # Other levels well above/below so they don't compete
        pwh=185.0, pwl=140.0,
        pmh=200.0, pml=120.0,
        pqh=220.0, pql=100.0,
        pyh=240.0, pyl=80.00,
    )
    regime, trigger, _, _ = select_trigger_and_regime(ctx, "long")
    assert regime == "normal"
    # Closest level above pre_vwap=164 is effective_pdh=172
    assert trigger == pytest.approx(172.0, abs=0.01)


def test_orb_only_top_level_regime_propagates_to_report():
    """Sanity: PersonaPlan.regime == 'orb_only' on the gap-extended path."""
    ctx = _level_ctx(
        close=305.33, atr=12.50, pre_vwap=345.39,
        pre_high=352.99, pre_low=334.54, gap_pct=11.79,
        effective_pdh=310.22, effective_pdl=299.76,
        pwh=281.05, pwl=242.03,
        pmh=221.33, pml=188.22,
        pqh=266.96, pql=188.22,
        pyh=267.08, pyl=91.87,
    )
    plans = compute_persona_plans(ctx)
    assert all(p.regime == "orb_only" for p in plans)


def test_context_from_bundle_pulls_level_map_and_premarket():
    """Bundle adapter reads strat.levels + market.premarket into PlanContext."""
    bundle = {
        "market": {
            "close": 305.33, "atr_14": 12.50,
            "premarket": {
                "pre_high": 352.99, "pre_low": 334.54,
                "pre_vwap": 345.39, "gap_pct": 11.79,
            },
        },
        "strat": {
            "trigger_high": 310.22, "trigger_low": 299.76,
            "ftfc_score": 1.0,
            "levels": {
                "PDH": 310.22, "PDL": 299.76,
                "PWH": 281.05, "PWL": 242.03,
                "PMH": 221.33, "PML": 188.22,
                "PQH": 266.96, "PQL": 188.22,
                "PYH": 267.08, "PYL": 91.87,
                "effective_PDH": 310.22, "effective_PDL": 299.76,
            },
        },
        "catalysts": {"events": []},
    }
    ctx = context_from_bundle(bundle, direction="long", conviction="medium")
    assert ctx.pwh == 281.05
    assert ctx.pmh == 221.33
    assert ctx.pyh == 267.08
    assert ctx.effective_pdh == 310.22
    assert ctx.pre_high == 352.99
    assert ctx.pre_vwap == 345.39
    assert ctx.gap_pct == 11.79
