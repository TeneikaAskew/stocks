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
from tests.lib.session_levels_helpers import basis, session, with_triggers


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
        levels=with_triggers(long=316.40, short=310.28, atr=12.6),
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
            "ftfc_score": 1.0,
        },
        "session_levels": {
            "available": True,
            "level_basis": basis({"PDH": 340.0, "PDL": 320.0}, prior_close=333.97, atr=12.6),
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
    assert ctx.levels.long.trigger["name"] == "PDH"
    assert ctx.levels.long.trigger["price"] == 340.0
    assert ctx.levels.short.trigger["price"] == 320.0
    assert ctx.ftfc_score == 1.0
    assert ctx.high_impact_catalyst_in_window is True
    assert ctx.analog_median_day_5_pct == 1.97


# ─── The trigger comes from the one level builder (FEAT-STRAT-001) ─────────


from lib.agents.trade_planner import select_trigger_and_regime  # noqa: E402


def _arm_levels(**premarket):
    """ARM 2026-04-20-like levels, read back through SessionLevels.from_basis."""
    return session(
        {"PDH": 168.35, "PDL": 162.73, "PDC": 165.90, "PWH": 175.0, "PWL": 147.50,
         "PMH": 180.0, "PML": 130.00, "PQH": 183.16, "PQL": 124.18},
        prior_close=166.73, atr=8.64, premarket=premarket or None,
    )


def _ctx(levels, direction="long", **kw) -> PlanContext:
    base = dict(direction=direction, conviction="medium", close=166.73, atr=8.64,
                levels=levels, ftfc_score=1.0 if direction == "long" else -1.0)
    base.update(kw)
    return PlanContext(**base)  # type: ignore[arg-type]


def test_select_trigger_reads_the_builders_long_pick():
    ctx = _ctx(_arm_levels())
    regime, trigger, stop_anchor, distance_atr, blue_sky = select_trigger_and_regime(ctx, "long")
    assert regime == "normal"
    assert trigger == pytest.approx(168.35)       # PDH, nearest at or above 166.73
    assert stop_anchor == pytest.approx(165.90)   # PDC, nearest below the reference
    assert distance_atr == pytest.approx((168.35 - 166.73) / 8.64, abs=1e-3)
    assert blue_sky is False


def test_select_trigger_reads_the_builders_short_pick():
    ctx = _ctx(_arm_levels(), direction="short")
    regime, trigger, stop_anchor, _d, _b = select_trigger_and_regime(ctx, "short")
    assert regime == "normal"
    assert trigger == pytest.approx(165.90)       # PDC: a close is a level
    assert stop_anchor == pytest.approx(168.35)


def test_select_trigger_skips_levels_premarket_broke():
    # pre_high 169.00 broke PDH 168.35: the premarket high itself is the
    # trigger and PWH 175 the first target.
    ctx = _ctx(_arm_levels(pre_high=169.0, pre_low=165.0, pre_vwap=167.0))
    _r, trigger, _s, _d, _b = select_trigger_and_regime(ctx, "long")
    assert trigger == pytest.approx(169.0)
    names = [c["name"] for c in ctx.levels.long.candidates if c["broken"]]
    assert names == ["PDH"]
    assert ctx.levels.long.targets[0]["name"] == "PWH"


def test_select_trigger_orb_only_when_every_long_level_is_broken():
    # Premarket ran to 200 through every long level up to PQH 183.16; the
    # premarket high itself is past the window (3 x ATR 8.64 is 25.92 from
    # the prior close 166.73; 200 is 33.27 away).
    ctx = _ctx(_arm_levels(pre_high=200.0, pre_low=165.0, pre_vwap=170.0))
    regime, trigger, _s, distance, _b = select_trigger_and_regime(ctx, "long")
    assert (regime, trigger, distance) == ("orb_only", None, None)
    assert ctx.orb_only_reason("long") == "all_broken_by_premarket"


def test_select_trigger_far_level_beyond_the_window_is_not_a_trigger():
    # Only a level 30 points above with ATR 2: outside 3 x ATR.
    sl = session({"PWH": 200.0, "PDL": 168.0}, prior_close=170.0, atr=2.0)
    ctx = _ctx(sl, close=170.0, atr=2.0)
    regime, trigger, _s, _d, _b = select_trigger_and_regime(ctx, "long")
    assert (regime, trigger) == ("orb_only", None)
    assert ctx.orb_only_reason("long") == "next_level_outside_window"


def test_select_trigger_atr_unavailable_gives_no_trigger_on_either_side():
    sl = session({"PDH": 171.0, "PDL": 169.0}, prior_close=170.0, atr=None)
    for direction in ("long", "short"):
        ctx = _ctx(sl, direction=direction, close=170.0, atr=2.0)
        regime, trigger, *_ = select_trigger_and_regime(ctx, direction)
        assert (regime, trigger) == ("orb_only", None)
        assert ctx.orb_only_reason(direction) == "atr_unavailable"


def test_no_levels_is_orb_only_with_reason_no_levels():
    ctx = _ctx(None)
    regime, trigger, *_ = select_trigger_and_regime(ctx, "long")
    assert (regime, trigger) == ("orb_only", None)
    assert ctx.orb_only_reason("long") == "no_levels"


def test_parent_bar_high_is_a_long_candidate():
    """The prior bar was an inside bar: the parent bar's high (172) is a
    candidate beside the prior day's tighter high (165)."""
    sl = session({"PDH": 175.0, "PDL": 150.0, "parent_bar_high": 172.0,
                  "parent_bar_low": 158.0}, prior_close=164.0, atr=8.0)
    ctx = _ctx(sl, close=164.0, atr=8.0)
    _r, trigger, *_ = select_trigger_and_regime(ctx, "long")
    assert trigger == pytest.approx(172.0)


def test_orb_only_persona_plans_carry_no_numbers():
    ctx = _ctx(_arm_levels(pre_high=200.0, pre_low=165.0, pre_vwap=170.0))
    plans = compute_persona_plans(ctx)
    assert len(plans) == 3
    for p in plans:
        assert p.regime == "orb_only"
        assert p.position_size_pct == 0.0
        assert p.entry_zone is None and p.stop is None
        assert p.targets == [] and p.risk_metrics is None
        assert p.rationale.startswith("ORB-only: ")
        assert "Blue-sky" not in p.rationale


def test_normal_plan_entry_starts_at_the_builders_trigger():
    ctx = _ctx(_arm_levels())
    neut = next(p for p in compute_persona_plans(ctx) if p.persona == "neutral")
    assert neut.regime == "normal"
    assert neut.entry_zone.low == pytest.approx(168.35, abs=0.01)


def test_context_from_bundle_reads_the_session_level_basis():
    bundle = {
        "ticker": "ARM",
        "market": {"close": 166.73, "atr_14": 8.64,
                   "premarket": {"gap_pct": -0.74}},
        "strat": {"ftfc_score": 1.0},
        "session_levels": {"available": True, "level_basis": basis(
            {"PDH": 168.35, "PDL": 162.73}, prior_close=166.73, atr=8.64,
            premarket={"pre_high": 167.0, "pre_low": 165.0, "pre_vwap": 166.0})},
        "catalysts": {"events": []},
    }
    ctx = context_from_bundle(bundle, direction="long", conviction="medium")
    assert ctx.levels is not None
    assert ctx.levels.reference == pytest.approx(166.0)   # the session pre_vwap
    assert ctx.levels.long.trigger["price"] == pytest.approx(167.0)   # premarket high
    assert ctx.levels.long.targets[0]["price"] == pytest.approx(168.35)
    assert ctx.gap_pct == -0.74


def test_context_from_bundle_without_session_levels_is_orb_only():
    bundle = {"ticker": "ARM", "market": {"close": 166.73, "atr_14": 8.64},
              "strat": {"ftfc_score": 1.0}}
    ctx = context_from_bundle(bundle, direction="long", conviction="medium")
    assert ctx.levels is None
    assert all(p.regime == "orb_only" for p in compute_persona_plans(ctx))


# ───────────────────────────────────────────────────────────────────────────
# Regression: a market section with no close must not become close=0.0.
#
# `float(market.get("close") or market.get("last_close") or 0.0)` is a
# Rule 3.7 fabricated default on a financial field. A market_data_daily
# pre-market placeholder row (every daily column NULL) made it 0.0, which
# made `safe_atr()` return `0.0 * 0.01`, which made the first `/ atr` raise
# 400 lines later. Production saw only "deterministic plan compute failed:
# float division by zero" — a message that names neither the field nor the
# reason, on every live insight run.
# ───────────────────────────────────────────────────────────────────────────


def _placeholder_bundle() -> dict:
    """What build_context_bundle returns when the day's only row is the
    8:30 ET placeholder: available, but every daily field None."""
    return {
        "ticker": "SPY",
        "market": {
            "available": True,
            "date": "2026-09-14",
            "close": None,
            "atr_14": None,
            "sma_200": None,
            "premarket": {"pre_high": 766.18, "pre_low": 757.77,
                          "pre_vwap": 759.37, "gap_pct": -0.649},
        },
        "strat": {"available": True, "trigger_high": 766.38,
                  "trigger_low": 763.6, "ftfc_score": 0.5},
        "catalysts": {"available": True, "events": []},
        "backtest": {"available": False},
    }


def test_context_from_bundle_rejects_a_market_section_with_no_close():
    """Fail with the field named, not with a ZeroDivisionError downstream."""
    with pytest.raises(ValueError, match="close"):
        context_from_bundle(
            _placeholder_bundle(), direction="long", conviction="medium",
        )


def test_context_from_bundle_error_names_the_ticker_and_the_value():
    """The orchestrator logs `%s` of this exception and nothing else, so
    the message is the entire diagnostic. It must carry the ticker, the
    offending value, and where the value came from — and must NOT guess
    at a cause it cannot see from here."""
    with pytest.raises(ValueError) as excinfo:
        context_from_bundle(
            _placeholder_bundle(), direction="long", conviction="medium",
        )
    message = str(excinfo.value)
    assert "SPY" in message
    assert "close=None" in message
    assert "summarize_market_context" in message


def test_context_from_bundle_still_accepts_a_missing_atr_with_a_real_close():
    """Only `close` is load-bearing for the context. A missing ATR stays
    None (no percent-of-close stand-in, per-ticker parameters 2026-11-08);
    with no session levels every plan is orb_only and publishes no price."""
    bundle = _placeholder_bundle()
    bundle["market"]["close"] = 764.29
    ctx = context_from_bundle(bundle, direction="long", conviction="medium")
    assert ctx.close == 764.29
    assert ctx.atr is None
    assert not hasattr(ctx, "safe_atr")
    plans = compute_persona_plans(ctx)
    assert plans and all(p.entry_zone is None and p.stop is None for p in plans)
