"""Deterministic per-persona trade-plan calculator.

Replaces LLM-generated entry/stop/targets/sizing with explicit, auditable
math so the same bundle always produces the same plan. The LLM still
generates the qualitative narrative (thesis, bull/bear case, risk
flags) but it does NOT roll the numbers any more — that removes the
run-to-run drift the user observed across two AVGO Apr-7 invocations
(targets shifted from $336/$349/$361 → $329/$341/$354 with no
underlying data change).

Three recipes, one per risk persona:

  ┌───────────────┬──────────────────────────────────────────────────────┐
  │ aggressive    │ Wide stop (2.0 × ATR), 3 stretched targets (2R / 3.5R│
  │               │ / 5R), 1.5× sizing on high conviction. Accepts vol.  │
  ├───────────────┼──────────────────────────────────────────────────────┤
  │ neutral       │ 1 ATR stop, 1R / 2R / 3R targets, 1.0× sizing       │
  │               │ (0.7× on low conviction). Canonical base case.       │
  ├───────────────┼──────────────────────────────────────────────────────┤
  │ conservative  │ Tightest structural stop (prior swing low / SMA200), │
  │               │ 1R / 1.75R targets, 0.5× sizing into catalyst window.│
  │               │ Blocks (size=0) when trade is against SMA200 or FTFC │
  │               │ alignment is too weak.                               │
  └───────────────┴──────────────────────────────────────────────────────┘

All three share the same entry-zone anchor: the strat trigger_high (for
longs) or trigger_low (for shorts) plus a small ATR-scaled buffer. The
buffer differs by persona — aggressive enters slightly above the
breakout, conservative waits for confirmation, neutral splits the diff.

The math is documented inline so a future reader (or the user reading
the persona-plan card) can see exactly why each number came out the way
it did. No magic constants without a comment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Optional

from lib.strat_levels import (
    MAX_TRIGGER_DISTANCE_ATR,
    MAX_TRIGGER_DISTANCE_PCT,
    _within_staleness_window,
)

from .schema import EntryZone, PersonaPlan

logger = logging.getLogger(__name__)


Direction = Literal["long", "short", "flat"]
Conviction = Literal["low", "medium", "high"]
Regime = Literal["normal", "extended", "orb_only"]


# Threshold (in ATRs) above which the next unbroken structural level is
# considered "too far" for a clean breakout entry. Past this distance
# we recommend ORB confirmation rather than firing a trigger-based plan.
# 3.0 ATR was picked empirically: most healthy gap-and-go setups have
# the next level <2 ATR away; anything past 3 ATR is in "extended" /
# "blue-sky" territory where R:R is already compressed.
_EXTENDED_DISTANCE_ATR = 3.0

# A level that pre-market only TOUCHED (pre_low or pre_high equal to the
# level, to the cent) is not broken: price never traded through it. Without
# this tolerance an exact tie (QQQ 2026-11-06: pre_low 647.05 == PDL 647.05,
# from an extended-hours print at the prior close) counted the level as
# cleared and the walk skipped to the 2025 yearly low 15 ATR away.
_TOUCH_TOLERANCE = 0.005


@dataclass
class PlanContext:
    """Inputs the planner needs to size a trade.

    All fields are deterministic — pulled from market_data_daily,
    summarize_strat_status, summarize_catalysts, and
    summarize_backtest_metrics. No LLM judgement.
    """

    direction: Direction          # 'long' / 'short' / 'flat' from the PM
    conviction: Conviction        # 'low' / 'medium' / 'high'
    close: float                  # most recent close (yesterday's close at as_of)
    atr: float                    # ATR(14) from market_data_daily
    trigger_high: Optional[float] # prior day high (legacy single-level fallback)
    trigger_low: Optional[float]  # prior day low (legacy single-level fallback)
    sma_200: Optional[float] = None
    prior_swing_low: Optional[float] = None
    prior_swing_high: Optional[float] = None
    ftfc_score: float = 0.0       # -1.0 (bearish) to +1.0 (bullish)
    high_impact_catalyst_in_window: bool = False
    analog_median_day_5_pct: Optional[float] = None  # %

    # ── Multi-timeframe levels (PR α) ─────────────────────────────────
    # Populated from summarize_strat_status.levels. The level walk
    # below uses these to pick the next unbroken trigger when price has
    # already cleared PDH/PDL overnight.
    pwh: Optional[float] = None
    pwl: Optional[float] = None
    pmh: Optional[float] = None
    pml: Optional[float] = None
    pqh: Optional[float] = None
    pql: Optional[float] = None
    pyh: Optional[float] = None
    pyl: Optional[float] = None

    # Mother-bar walk-back for inside-of-inside compressions. When the
    # prior bar was a strat '1', price has been trading inside an outer
    # mother bar — these fields hold the OUTER bar's H/L. On a normal
    # (non-inside) prior bar these equal the regular PDH/PDL.
    effective_pdh: Optional[float] = None
    effective_pdl: Optional[float] = None

    # Pre-market context (PR #134 surfaced this in summarize_market_context).
    # The level walk uses pre_vwap as the "where price is sitting now"
    # reference instead of yesterday's close, so we correctly identify
    # which structural levels overnight action has already cleared.
    pre_high: Optional[float] = None
    pre_low: Optional[float] = None
    pre_vwap: Optional[float] = None
    gap_pct: Optional[float] = None

    # ---- Derived helpers ----
    def reference_price(self) -> float:
        """The "where price is sitting" anchor for the level walk.

        Uses pre_vwap when pre-market context is available — pre_vwap
        reflects whether overnight action held the gap or faded back
        below the prior close. Falls back to yesterday's close when
        pre-market data is missing (weekends, thinly-traded names, or
        bars before the pre-market context backfill).
        """
        if self.pre_vwap is not None and self.pre_vwap > 0:
            return float(self.pre_vwap)
        return float(self.close)

    def trigger_for(self, direction: Direction) -> float:
        """Return the structural trigger level for this direction.

        Legacy single-level fallback retained for callers that haven't
        adopted ``select_trigger_and_regime``. New code should use the
        regime-aware selector instead — it walks the multi-timeframe
        level hierarchy and tags gap-extended setups for ORB-only
        execution.
        """
        if direction == "long":
            return self.trigger_high or self.close * 1.005
        if direction == "short":
            return self.trigger_low or self.close * 0.995
        return self.close

    def safe_atr(self) -> float:
        """Sanity-bounded ATR. If the upstream value is missing or
        zero (which would collapse all stop distances to zero), fall
        back to 1% of the last close — a reasonable mid-volatility
        default that keeps the math well-formed."""
        if self.atr is None or self.atr <= 0:
            return self.close * 0.01
        return float(self.atr)


# ───────────────────────────────────────────────────────────────────────────
# Level-aware trigger + regime selection (PR α)
# ───────────────────────────────────────────────────────────────────────────


def select_trigger_and_regime(
    ctx: PlanContext, direction: Direction,
) -> tuple[Regime, Optional[float], Optional[float], Optional[float], bool]:
    """Pick the next unbroken structural level as the trigger; classify regime.

    Walks the multi-timeframe level hierarchy in the trade direction
    (longs walk above, shorts walk below the reference price) and
    returns the closest UNBROKEN level. Three outcomes:

    * ``normal``    — the next level is within ``_EXTENDED_DISTANCE_ATR``
                      of the reference price. Standard trigger-based plan.
                      The trigger is always a real level from the
                      level map; none is synthesized.
    * ``extended``  — the trigger is far away
                      (>= ``_EXTENDED_DISTANCE_ATR``). The plan still
                      uses that trigger but the rationale recommends
                      15-min ORB confirmation before entering.
    * ``orb_only``  — no unbroken level lies inside the distance window
                      (every level cleared by pre-market, or the next
                      one too far), or multi-timeframe levels were never
                      populated. No trigger emitted; the brief tells the
                      trader to wait for the ORB.

    The "level cleared" logic uses the larger of (reference_price,
    pre_high/pre_low) so a pre-market spike that touched a level still
    counts as cleared — gap-up wicks above PDH push trigger to PWH.

    Returns ``(regime, trigger, stop_anchor, distance_atr, is_blue_sky)``.
    ``trigger`` and ``distance_atr`` are ``None`` when ``regime ==
    'orb_only'``. ``stop_anchor`` is the closest level on the OPPOSITE
    side of price (used by the conservative persona to tighten stops).
    ``is_blue_sky`` is always ``False`` since 2026-11-07 (synthesized
    triggers were removed); the slot stays so callers keep unpacking
    five values.
    """
    if direction not in ("long", "short"):
        return ("normal", None, None, None, False)

    ref = ctx.reference_price()
    atr = ctx.safe_atr()

    # Backwards-compat: when NO multi-timeframe levels and no pre-market
    # context are populated (legacy callers / unit-test fixtures that
    # set only trigger_high/trigger_low), use the original single-level
    # trigger directly and skip the level walk. This preserves the
    # deterministic plan math for callers that haven't adopted the
    # multi-tf level surface — the new gap-aware behaviour activates
    # once `context_from_bundle` populates pwh / pmh / pre_high / etc.
    has_multi_tf = any(lv is not None for lv in (
        ctx.pwh, ctx.pwl, ctx.pmh, ctx.pml,
        ctx.pqh, ctx.pql, ctx.pyh, ctx.pyl,
        ctx.pre_high, ctx.pre_low,
        ctx.effective_pdh, ctx.effective_pdl,
    ))
    if not has_multi_tf:
        legacy_trigger = ctx.trigger_high if direction == "long" else ctx.trigger_low
        if legacy_trigger is None:
            return ("orb_only", None, None, None, False)
        distance = abs(float(legacy_trigger) - ref) / atr
        regime = "normal" if distance < _EXTENDED_DISTANCE_ATR else "extended"
        return (regime, float(legacy_trigger), None, distance, False)

    # For longs, "cleared above" means pre_high reached the level, even
    # if pre-market subsequently faded below it. For shorts, "cleared
    # below" means pre_low touched the level. This catches the case
    # where overnight action wicked through a level then settled back —
    # the level is now resistance/support, not a fresh trigger.
    cleared_above = max(ref, ctx.pre_high or ref) if direction == "long" else None
    cleared_below = min(ref, ctx.pre_low or ref) if direction == "short" else None

    # Backwards-compat: if effective_pdh/pdl weren't populated (legacy
    # caller built the PlanContext directly without going through
    # context_from_bundle), fall back to the single-level trigger_high
    # / trigger_low. Tests written before PR α exercise this path and
    # should keep producing the same plans.
    eff_pdh = ctx.effective_pdh if ctx.effective_pdh is not None else ctx.trigger_high
    eff_pdl = ctx.effective_pdl if ctx.effective_pdl is not None else ctx.trigger_low
    long_levels = (eff_pdh, ctx.pwh, ctx.pmh, ctx.pqh, ctx.pyh, ctx.pre_high)
    short_levels = (eff_pdl, ctx.pwl, ctx.pml, ctx.pql, ctx.pyl, ctx.pre_low)
    # `structural_*` excludes pre_high/pre_low: the multi-timeframe
    # history levels (PDH/PWH/PMH/PQH/PYH) that the touch tolerance
    # applies to.
    structural_long = (eff_pdh, ctx.pwh, ctx.pmh, ctx.pqh, ctx.pyh)
    structural_short = (eff_pdl, ctx.pwl, ctx.pml, ctx.pql, ctx.pyl)

    if direction == "long":
        # Levels strictly ABOVE the cleared mark (price hasn't broken them yet)
        # Structural levels tied with the cleared mark count as unbroken
        # (_TOUCH_TOLERANCE). pre_high itself keeps the strict compare: it
        # IS the cleared mark, so it is never its own trigger.
        candidates = sorted([
            float(lv) for lv in structural_long
            if lv is not None and float(lv) > cleared_above - _TOUCH_TOLERANCE
        ] + [
            float(ctx.pre_high) for _ in (0,)
            if ctx.pre_high is not None and float(ctx.pre_high) > cleared_above
        ])
        # Stop anchor: closest level BELOW the reference price
        below_ref = sorted([
            float(lv) for lv in (eff_pdl, ctx.pwl, ctx.pml,
                                 ctx.pql, ctx.pyl, ctx.pre_low)
            if lv is not None and float(lv) < ref
        ], reverse=True)
        stop_anchor = below_ref[0] if below_ref else None
    else:  # short
        candidates = sorted([
            float(lv) for lv in structural_short
            if lv is not None and float(lv) < cleared_below + _TOUCH_TOLERANCE
        ] + [
            float(ctx.pre_low) for _ in (0,)
            if ctx.pre_low is not None and float(ctx.pre_low) < cleared_below
        ], reverse=True)
        above_ref = sorted([
            float(lv) for lv in (eff_pdh, ctx.pwh, ctx.pmh,
                                 ctx.pqh, ctx.pyh, ctx.pre_high)
            if lv is not None and float(lv) > ref
        ])
        stop_anchor = above_ref[0] if above_ref else None

    # Distance cap (FEAT-INSIGHT-001, 2026-11-07): an unbroken level is a
    # trigger only when it sits within the brief's staleness window of
    # THIS ticker's reference price, i.e. within MAX_TRIGGER_DISTANCE_ATR
    # x this ticker's ATR(14) and MAX_TRIGGER_DISTANCE_PCT of price (the
    # same rule lib.strat_levels applies to the brief's levels). Without
    # it the walk kept going until it found any unbroken level, so on
    # 2026-11-06 IWM's short trigger was the 2025 yearly low 171.73
    # (about 22 ATR below 272) and QQQ's was 402.39. Levels past the
    # window fall through to the no-candidate branch below: orb_only.
    in_window = [lv for lv in candidates if _within_staleness_window(lv, ref, atr)]
    if candidates and not in_window:
        logger.info(
            "trade_planner stale_levels_dropped direction=%s ref=%.4f atr=%.4f "
            "max_atr=%.1f max_pct=%.2f dropped=%s",
            direction, ref, atr, MAX_TRIGGER_DISTANCE_ATR,
            MAX_TRIGGER_DISTANCE_PCT, [round(lv, 4) for lv in candidates],
        )
    candidates = in_window

    if not candidates:
        # No real level inside the window: wait for the 15-min opening
        # range. Until 2026-11-07 this branch projected a "blue-sky"
        # trigger (nearest cleared level +/- 0.15 to 0.20 ATR) when the
        # gap was at most 1.5 ATR. The owner ruled that no level may be
        # synthesized: every trigger is a real level from the level map,
        # or there is no trigger. The 2015-2026 entry replay found the
        # synthesized triggers filled often but averaged slightly below
        # 0R (n=734, neutral persona), so nothing measurable is lost.
        same_side_levels = long_levels if direction == "long" else short_levels
        same_side_structural = (
            structural_long if direction == "long" else structural_short
        )
        cleared = cleared_above if direction == "long" else cleared_below
        gap_atr = abs(cleared - ctx.close) / atr if cleared is not None else None
        logger.info(
            "trade_planner orb_only direction=%s ref=%.4f atr=%.4f "
            "cleared=%s gap_atr=%s structural_populated=%s pre_only=%s",
            direction, ref, atr,
            f"{cleared:.4f}" if cleared is not None else None,
            f"{gap_atr:.3f}" if gap_atr is not None else None,
            any(lv is not None for lv in same_side_structural),
            # True iff only pre_high/pre_low populated, no PDH/PWH/PMH/PQH/PYH
            # (the sub-case C codex review caught).
            any(lv is not None for lv in same_side_levels)
            and not any(lv is not None for lv in same_side_structural),
        )
        return ("orb_only", None, stop_anchor, None, False)

    trigger = candidates[0]
    distance_atr = abs(trigger - ref) / atr
    # Every candidate here passed the window (distance <= 3 x ATR,
    # inclusive), so a multi-timeframe trigger is always `normal`; a level
    # exactly 3 ATR away is a normal trigger, not an extended one.
    # `extended` is reached only through the legacy single-level path.
    return ("normal", trigger, stop_anchor, distance_atr, False)


# ─── Recipe constants — central so they're easy to audit + tune ────────────

# entry-zone width as a fraction of ATR
_ENTRY_BUFFER = {
    "aggressive":   (0.00, 0.50),  # buy-strength: enter at trigger up to +0.5 ATR
    "neutral":      (0.00, 0.25),  # canonical: at trigger up to +0.25 ATR
    "conservative": (0.10, 0.40),  # wait for follow-through, 0.1-0.4 ATR above
}

# stop distance from entry midpoint, in ATR units
_STOP_ATR_MULT = {
    "aggressive":   2.00,   # accept ~2 ATR of noise
    "neutral":      1.00,   # canonical 1-ATR stop
    "conservative": 0.70,   # tight-but-not-stop-fishing
}

# target distances in R-multiples of risk (where R = midpoint - stop for long)
_TARGET_R_MULTIPLES = {
    "aggressive":   [2.0, 3.5, 5.0],
    "neutral":      [1.0, 2.0, 3.0],
    "conservative": [1.0, 1.75],
}

# sizing as a fraction of normal allocation, by conviction
_SIZE_BY_CONVICTION = {
    "aggressive":   {"high": 1.5, "medium": 1.2, "low": 0.8},
    "neutral":      {"high": 1.0, "medium": 1.0, "low": 0.7},
    "conservative": {"high": 0.7, "medium": 0.5, "low": 0.3},
}

# how much to scale conservative size when a high-impact catalyst
# falls inside the holding window (e.g. CPI/FOMC mid-trade)
_CONSERVATIVE_CATALYST_DAMPER = 0.6

# minimum FTFC alignment for conservative to take a trade at all: a long
# needs ftfc_score >= +0.30, a short ftfc_score <= -0.30
_CONSERVATIVE_MIN_FTFC = 0.30

# |ftfc_score| at or beyond which a trade counts as FTFC-aligned
_FTFC_ALIGNED_MIN = 0.5
# Floating-point slack for the aligned comparison only. The legacy weighted
# vote (1d 0.30, 1w 0.10) scores a 2U daily with a 2D weekly as
# (0.3 - 0.1) / 0.4 = 0.49999999999999994, which summarize_strat_status rounds
# to 0.5; without the slack the raw score and its 2 dp snapshot disagree.
# Stored scores are not changed (the FEAT-STRAT-001 legacy controls pin them).
_FTFC_ALIGNED_TOLERANCE = 1e-9


def is_ftfc_aligned(direction: str, ftfc_score: float) -> bool:
    """True when the signed FTFC score agrees with the trade direction by at
    least 0.5: long needs >= +0.5, short <= -0.5, flat is never aligned.
    Shared by compute_risk_metrics and the orchestrator's conviction
    calibration so every path gives the same answer for the same score."""
    if direction == "long":
        return ftfc_score >= _FTFC_ALIGNED_MIN - _FTFC_ALIGNED_TOLERANCE
    if direction == "short":
        return ftfc_score <= -_FTFC_ALIGNED_MIN + _FTFC_ALIGNED_TOLERANCE
    return False


def _fails_conservative_ftfc(ctx: "PlanContext") -> bool:
    """The conservative persona's FTFC minimum, in the trade's direction:
    a long stands aside below +0.30, a short above -0.30."""
    if ctx.direction == "short":
        return ctx.ftfc_score > -_CONSERVATIVE_MIN_FTFC
    return ctx.ftfc_score < _CONSERVATIVE_MIN_FTFC


# ───────────────────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────────────────


def compute_persona_plans(ctx: PlanContext) -> list[PersonaPlan]:
    """Return the three persona plans (aggressive, neutral, conservative)
    for the given context. Order is fixed so the UI renders consistently.

    Returns an empty list if `ctx.direction == 'flat'` — there is no
    trade to size. The caller (orchestrator) should still emit risk
    flags but the plan card just hides itself.

    On gap-extended setups where ``select_trigger_and_regime`` returns
    ``orb_only`` (price has cleared every structural level in the trade
    direction), each persona's plan is replaced with a no-trigger
    ``orb_only`` PersonaPlan whose rationale tells the trader to wait
    for the 15-min ORB. This is the AMD 4/24 +12% gap case — the move
    happened overnight; RTH needs its own setup.
    """
    if ctx.direction == "flat":
        return []
    regime, trigger, stop_anchor, distance_atr, is_blue_sky = select_trigger_and_regime(
        ctx, ctx.direction,
    )
    return [
        _plan(ctx, "aggressive", regime, trigger, stop_anchor, distance_atr, is_blue_sky),
        _plan(ctx, "neutral", regime, trigger, stop_anchor, distance_atr, is_blue_sky),
        _plan(ctx, "conservative", regime, trigger, stop_anchor, distance_atr, is_blue_sky),
    ]


def _plan(
    ctx: PlanContext, persona: str,
    regime: Regime = "normal",
    trigger: Optional[float] = None,
    stop_anchor: Optional[float] = None,
    distance_atr: Optional[float] = None,
    is_blue_sky: bool = False,
) -> PersonaPlan:
    """Compute one persona's plan. Long and short are mirror images of
    each other — for short, we flip the sign on the offsets so the
    entry/stop/targets land below the trigger instead of above.

    When ``regime == 'orb_only'`` (no structural trigger available),
    returns a placeholder plan with zero sizing and a rationale that
    tells the trader to wait for the opening-range breakout. The
    canonical fields (entry_zone, stop, targets) are still populated
    with reasonable placeholders derived from the reference price ±
    1 ATR so downstream consumers (the brief embed, the persona-plan
    card) don't have to special-case None.
    """
    if regime == "orb_only":
        return _orb_only_plan(ctx, persona)

    sign = 1.0 if ctx.direction == "long" else -1.0
    atr = ctx.safe_atr()
    if trigger is None:
        # Backwards-compat: caller didn't go through compute_persona_plans
        # (e.g. legacy fixture). Fall back to the single-level trigger.
        trigger = ctx.trigger_for(ctx.direction)

    # ── 1. Entry zone ──────────────────────────────────────────────
    buf_lo_mult, buf_hi_mult = _ENTRY_BUFFER[persona]
    entry_lo = trigger + sign * buf_lo_mult * atr
    entry_hi = trigger + sign * buf_hi_mult * atr
    if entry_lo > entry_hi:  # short side flips the order
        entry_lo, entry_hi = entry_hi, entry_lo
    midpoint = (entry_lo + entry_hi) / 2

    # ── 2. Stop ────────────────────────────────────────────────────
    raw_stop = midpoint - sign * _STOP_ATR_MULT[persona] * atr

    if persona == "conservative":
        # Conservative anchors the stop at the *closest* structural
        # support to entry — tighter than the ATR floor whenever a
        # real swing low, the 200-SMA, or a multi-timeframe level
        # (PR α: stop_anchor) sits between the ATR stop and the
        # entry. Only candidates on the correct side of entry qualify
        # (a long stop must be BELOW the entry midpoint, even if
        # SMA200 happens to sit above it after a recent breakout).
        candidates = [raw_stop]
        for level in (ctx.prior_swing_low, ctx.sma_200, stop_anchor):
            if level is None or ctx.direction != "long":
                continue
            if level < midpoint:   # only below-entry levels are valid stops
                candidates.append(level)
        for level in (ctx.prior_swing_high, ctx.sma_200, stop_anchor):
            if level is None or ctx.direction != "short":
                continue
            if level > midpoint:   # only above-entry levels are valid stops
                candidates.append(level)
        # Tightest valid stop = closest to entry on the correct side
        if ctx.direction == "long":
            stop = max(candidates)
        else:
            stop = min(candidates)
    else:
        stop = raw_stop

    # Sanity: never let stop == entry midpoint or cross it
    min_distance = 0.5 * atr
    if abs(midpoint - stop) < min_distance:
        stop = midpoint - sign * min_distance

    # ── 3. Targets ─────────────────────────────────────────────────
    risk_per_unit = abs(midpoint - stop)
    targets: list[float] = []
    for r_mult in _TARGET_R_MULTIPLES[persona]:
        targets.append(midpoint + sign * r_mult * risk_per_unit)

    # Optional: stretch the aggressive top target up to the analog
    # day-5 median move if that's larger than 5R — analog data is the
    # most empirical anchor we have.
    if persona == "aggressive" and ctx.analog_median_day_5_pct is not None:
        analog_target = midpoint * (1 + sign * abs(ctx.analog_median_day_5_pct) / 100.0)
        if (sign > 0 and analog_target > targets[-1]) or (
            sign < 0 and analog_target < targets[-1]
        ):
            targets[-1] = analog_target

    # ── 4. Sizing ──────────────────────────────────────────────────
    size = _SIZE_BY_CONVICTION[persona][ctx.conviction]
    if persona == "conservative" and ctx.high_impact_catalyst_in_window:
        size *= _CONSERVATIVE_CATALYST_DAMPER
    if persona == "conservative" and _fails_conservative_ftfc(ctx):
        # Trade fails the conservative trend-alignment gate; flat-zero size
        size = 0.0
    if persona == "conservative" and ctx.direction == "long" and \
            ctx.sma_200 is not None and ctx.close < ctx.sma_200:
        # Long taken below the 200-SMA — conservative refuses
        size = 0.0

    # ── 5. Rationale: spell out exactly why the numbers landed where
    # they did so a future reader (and the LLM rendering the report)
    # never has to guess. ──────────────────────────────────────────
    rationale = _build_rationale(persona, ctx, atr, midpoint, stop,
                                 risk_per_unit, size,
                                 regime=regime, distance_atr=distance_atr,
                                 trigger=trigger, is_blue_sky=is_blue_sky)

    risk_metrics = compute_risk_metrics(
        entry_lo=round(entry_lo, 2),
        entry_hi=round(entry_hi, 2),
        stop=round(stop, 2),
        targets=[round(t, 2) for t in targets],
        direction=ctx.direction,
        atr=atr,
        sma_200=ctx.sma_200,
        ftfc_score=ctx.ftfc_score,
    )

    return PersonaPlan(
        persona=persona,  # type: ignore[arg-type]
        entry_zone=EntryZone(low=round(entry_lo, 2), high=round(entry_hi, 2)),
        stop=round(stop, 2),
        targets=[round(t, 2) for t in targets],
        position_size_pct=round(size, 2),
        rationale=rationale,
        regime=regime,
        risk_metrics=risk_metrics,
    )


def compute_risk_metrics(
    entry_lo: float,
    entry_hi: float,
    stop: float,
    targets: list[float],
    direction: Direction,
    atr: float,
    sma_200: Optional[float] = None,
    ftfc_score: Optional[float] = None,
    invalidation_level: Optional[float] = None,
) -> "RiskMetrics":
    """Compute deterministic risk distances for a persona plan.

    These values populate ``PersonaPlan.risk_metrics`` and are read by
    the LLM risk reviewers in place of recomputing the math themselves
    (the LLM hallucinates ~55% of the time per the 2026-05-10 audit).

    All distances are unsigned magnitudes EXCEPT ``target_r_multiples``
    which is signed by direction (positive = good R:R, negative = target
    on the wrong side of entry).

    Returns a fully-populated RiskMetrics; fields that depend on missing
    inputs (atr=0, sma_200=None, etc.) are set to None individually.
    """
    from .schema import RiskMetrics  # local import to avoid circulars
    entry_mid = (entry_lo + entry_hi) / 2
    risk_per_unit = abs(entry_mid - stop)
    sign = 1.0 if direction == "long" else -1.0 if direction == "short" else 0.0

    metrics_kwargs: dict = {}
    if atr > 0 and risk_per_unit > 0:
        metrics_kwargs["stop_distance_atr"] = round(risk_per_unit / atr, 3)
    if entry_mid > 0:
        metrics_kwargs["stop_distance_pct"] = round(
            risk_per_unit / entry_mid * 100, 3
        )
    if risk_per_unit > 0 and sign != 0 and targets:
        metrics_kwargs["target_r_multiples"] = [
            round((t - entry_mid) / risk_per_unit * sign, 3)
            for t in targets
        ]
    if sma_200 is not None and sma_200 > 0:
        metrics_kwargs["entry_vs_sma200_pct"] = round(
            (entry_mid - sma_200) / sma_200 * 100, 3
        )
        if atr > 0:
            metrics_kwargs["entry_vs_sma200_atr"] = round(
                (entry_mid - sma_200) / atr, 3
            )
    if ftfc_score is not None:
        metrics_kwargs["ftfc_aligned"] = is_ftfc_aligned(direction, ftfc_score)
    if invalidation_level is not None and atr > 0:
        metrics_kwargs["invalidation_distance_atr"] = round(
            abs(invalidation_level - stop) / atr, 3
        )
    return RiskMetrics(**metrics_kwargs)


def _orb_only_plan(ctx: PlanContext, persona: str) -> PersonaPlan:
    """Placeholder plan for the gap-extended ``orb_only`` regime.

    Sizing is zeroed because there's no structural trigger to act on —
    the brief renders this as "wait for 15-min ORB" copy. The
    entry/stop/target placeholders bracket the reference price ± 1 ATR
    so downstream UIs that always read these fields don't crash.
    """
    sign = 1.0 if ctx.direction == "long" else -1.0
    atr = ctx.safe_atr()
    ref = ctx.reference_price()
    placeholder_lo = round(ref + sign * 0.0 * atr, 2)
    placeholder_hi = round(ref + sign * 1.0 * atr, 2)
    if placeholder_lo > placeholder_hi:
        placeholder_lo, placeholder_hi = placeholder_hi, placeholder_lo
    placeholder_stop = round(ref - sign * 1.0 * atr, 2)
    side = 'resistance' if ctx.direction == 'long' else 'support'
    rationale = (
        f"ORB-only: after pre-market ({ctx.gap_pct:+.2f}% gap) no unbroken "
        f"{side} level lies within {MAX_TRIGGER_DISTANCE_ATR:.0f}x ATR of price. "
        f"Wait for the 15-min opening range to establish before entering."
        if ctx.gap_pct is not None else
        f"ORB-only: no unbroken {side} level lies within "
        f"{MAX_TRIGGER_DISTANCE_ATR:.0f}x ATR of price. "
        "Wait for the 15-min opening range to establish before entering."
    )
    # ORB-only plans get computed risk_metrics too (the entry/stop are
    # placeholders but the math is still well-defined). The reviewer
    # rules will see the placeholder distances and fire flags as normal;
    # the regime banner already tells the trader to wait for ORB.
    risk_metrics = compute_risk_metrics(
        entry_lo=placeholder_lo,
        entry_hi=placeholder_hi,
        stop=placeholder_stop,
        targets=[],
        direction=ctx.direction,
        atr=atr,
        sma_200=ctx.sma_200,
        ftfc_score=ctx.ftfc_score,
    )
    return PersonaPlan(
        persona=persona,  # type: ignore[arg-type]
        entry_zone=EntryZone(low=placeholder_lo, high=placeholder_hi),
        stop=placeholder_stop,
        targets=[],  # ORB hasn't formed yet — no targets to publish
        position_size_pct=0.0,
        rationale=rationale,
        regime="orb_only",
        risk_metrics=risk_metrics,
    )


def _build_rationale(
    persona: str, ctx: PlanContext, atr: float,
    midpoint: float, stop: float, risk: float, size: float,
    regime: Regime = "normal",
    distance_atr: Optional[float] = None,
    trigger: Optional[float] = None,
    is_blue_sky: bool = False,
) -> str:
    """One-sentence explanation of the recipe — references the actual
    inputs so it changes when the inputs change.

    On ``regime == 'extended'`` setups (next structural level >= 3 ATR
    away), prepends an ORB-confirmation note so the trader knows the
    breakout is in extended territory. ``is_blue_sky`` is accepted for
    call compatibility and ignored.
    """
    if size == 0.0:
        if persona == "conservative":
            if _fails_conservative_ftfc(ctx):
                if ctx.direction == "short":
                    return (
                        f"Stand aside: FTFC alignment {ctx.ftfc_score:+.2f} above "
                        f"-{_CONSERVATIVE_MIN_FTFC:.2f} threshold."
                    )
                return (
                    f"Stand aside: FTFC alignment {ctx.ftfc_score:+.2f} below "
                    f"+{_CONSERVATIVE_MIN_FTFC:.2f} threshold."
                )
            if ctx.sma_200 and ctx.direction == "long" and ctx.close < ctx.sma_200:
                return (
                    f"Stand aside: long against the 200-SMA "
                    f"(close ${ctx.close:.2f} < SMA200 ${ctx.sma_200:.2f})."
                )
        return "Stand aside: trade fails persona-specific filters."

    extended_prefix = ""
    if regime == "extended" and distance_atr is not None and trigger is not None:
        extended_prefix = (
            f"Extended gap: trigger ${trigger:.2f} is {distance_atr:.1f}× ATR away — "
            f"recommend 15-min ORB confirmation before entry. "
        )

    stop_atr = abs(midpoint - stop) / atr
    if persona == "aggressive":
        return extended_prefix + (
            f"{stop_atr:.1f}× ATR stop, R = ${risk:.2f}, targets at 2R/3.5R/5R; "
            f"{size:.2f}× size on {ctx.conviction} conviction."
        )
    if persona == "neutral":
        return extended_prefix + (
            f"~1× ATR stop (${atr:.2f}), R = ${risk:.2f}, targets at 1R/2R/3R; "
            f"{size:.2f}× size on {ctx.conviction} conviction (canonical base case)."
        )
    if persona == "conservative":
        damper_note = (
            " (catalyst damper applied)"
            if ctx.high_impact_catalyst_in_window else ""
        )
        return extended_prefix + (
            f"{stop_atr:.1f}× ATR stop anchored at structure, R = ${risk:.2f}, "
            f"targets at 1R/1.75R; {size:.2f}× size{damper_note}."
        )
    return ""


# ───────────────────────────────────────────────────────────────────────────
# Construction helper used by the orchestrator
# ───────────────────────────────────────────────────────────────────────────


class PlanContextUnavailable(ValueError):
    """The bundle cannot produce a usable PlanContext.

    Distinct from an unexpected bug so a caller can mark the plan section
    degraded on the report rather than swallowing it alongside genuine
    crashes. Subclasses ValueError because that is what callers already
    catch for a malformed context.
    """


def context_from_bundle(
    bundle: dict, direction: Direction, conviction: Conviction,
) -> PlanContext:
    """Pull a PlanContext from the bundle the orchestrator already
    assembled. Falls back to neutral defaults when individual sections
    are degraded or missing."""
    market = bundle.get("market") or {}
    strat = bundle.get("strat") or {}
    catalysts = bundle.get("catalysts") or {}
    backtest = bundle.get("backtest") or {}
    ticker = bundle.get("ticker")

    catalyst_events = catalysts.get("events") or []
    high_impact_in_window = any(
        (e.get("impact") or "").lower() == "high"
        for e in catalyst_events
    )

    fr = (backtest.get("forward_returns") or {}) if isinstance(backtest, dict) else {}
    day_5 = fr.get("day_5") or {}
    analog_d5 = day_5.get("median_pct") if isinstance(day_5, dict) else None

    # summarize_market_context emits 'close' + 'atr_14'; older fixtures
    # may use 'last_close' / 'atr'.
    #
    # `close` is load-bearing and has no defensible default: every stop,
    # target and distance is measured from it, and `safe_atr()` falls back
    # to a percentage OF it. The previous `or 0.0` turned a missing price
    # into a plausible-looking zero that survived ~400 lines and then
    # surfaced as `ZeroDivisionError: float division by zero` at the first
    # `/ atr` — a message naming neither the field nor the ticker. Fail
    # here instead, where the cause is still in scope (CLAUDE.md Rule 3.7:
    # an INTERNAL failure fails loud, it does not fabricate a value).
    close_val = _maybe_float(market.get("close"))
    if close_val is None:
        close_val = _maybe_float(market.get("last_close"))
    if close_val is None or close_val <= 0:
        raise PlanContextUnavailable(
            f"cannot build a plan context for {ticker or '<unknown>'}: the "
            f"market section carries no usable close "
            f"(close={market.get('close')!r}, "
            f"last_close={market.get('last_close')!r}, "
            f"available={market.get('available')!r}, "
            f"reason={market.get('reason')!r}). Whatever "
            f"summarize_market_context read for this run has no completed "
            f"daily bar."
        )
    close = float(close_val)
    # AUDIT-2026-05-13: silent fallback — `or 0.0` on a financial field.
    # Left in place because `safe_atr()` rescues a zero ATR into
    # `close * 0.01` rather than propagating it, and unwinding that
    # fabricated default means giving every persona plan an unavailable
    # path. Tracked separately; with `close > 0` guaranteed above, it can
    # no longer produce a zero divisor.
    atr = float(market.get("atr_14") or market.get("atr") or 0.0)

    # Multi-timeframe levels (PR α). summarize_strat_status surfaces a
    # `levels` sub-dict with PDH/PDL/PWH/PWL/PMH/PML/PQH/PQL/PYH/PYL
    # plus mother-bar walk-back effective_PDH / effective_PDL.
    levels = strat.get("levels") or {}
    eff_pdh = _maybe_float(levels.get("effective_PDH")) or _maybe_float(levels.get("PDH"))
    eff_pdl = _maybe_float(levels.get("effective_PDL")) or _maybe_float(levels.get("PDL"))

    # Pre-market block from summarize_market_context (PR #134).
    premarket = market.get("premarket") or {}
    pre_high = _maybe_float(premarket.get("pre_high"))
    pre_low = _maybe_float(premarket.get("pre_low"))
    pre_vwap = _maybe_float(premarket.get("pre_vwap"))
    gap_pct = _maybe_float(premarket.get("gap_pct"))

    return PlanContext(
        direction=direction,
        conviction=conviction,
        close=close,
        atr=atr,
        trigger_high=_maybe_float(strat.get("trigger_high")),
        trigger_low=_maybe_float(strat.get("trigger_low")),
        sma_200=_maybe_float(market.get("sma_200")),
        prior_swing_low=_maybe_float(market.get("prior_swing_low")),
        prior_swing_high=_maybe_float(market.get("prior_swing_high")),
        # AUDIT-2026-05-13: silent fallback — `or 0.0` on a financial field.
        # See docs/audits/FALLBACK_AUDIT_2026-05-13.md §13, `lib/agents/` row.
        # A missing FTFC score becomes 0.0, which fails the conservative
        # persona's _CONSERVATIVE_MIN_FTFC gate and sets ftfc_aligned False:
        # "unknown" is read as "actively unaligned".
        ftfc_score=float(strat.get("ftfc_score") or 0.0),
        high_impact_catalyst_in_window=high_impact_in_window,
        analog_median_day_5_pct=_maybe_float(analog_d5),
        # Multi-timeframe levels
        pwh=_maybe_float(levels.get("PWH")),
        pwl=_maybe_float(levels.get("PWL")),
        pmh=_maybe_float(levels.get("PMH")),
        pml=_maybe_float(levels.get("PML")),
        pqh=_maybe_float(levels.get("PQH")),
        pql=_maybe_float(levels.get("PQL")),
        pyh=_maybe_float(levels.get("PYH")),
        pyl=_maybe_float(levels.get("PYL")),
        effective_pdh=eff_pdh,
        effective_pdl=eff_pdl,
        # Pre-market context
        pre_high=pre_high,
        pre_low=pre_low,
        pre_vwap=pre_vwap,
        gap_pct=gap_pct,
    )


def _maybe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
