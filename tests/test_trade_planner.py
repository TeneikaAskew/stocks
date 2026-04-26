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
