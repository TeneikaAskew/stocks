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

from dataclasses import dataclass
from typing import Literal, Optional

from .schema import EntryZone, PersonaPlan


Direction = Literal["long", "short", "flat"]
Conviction = Literal["low", "medium", "high"]


@dataclass
class PlanContext:
    """Inputs the planner needs to size a trade.

    All fields are deterministic — pulled from market_data_daily,
    summarize_strat_status, summarize_catalysts, and
    summarize_backtest_metrics. No LLM judgement.
    """

    direction: Direction          # 'long' / 'short' / 'flat' from the PM
    conviction: Conviction        # 'low' / 'medium' / 'high'
    close: float                  # most recent close
    atr: float                    # ATR(14) from market_data_daily
    trigger_high: Optional[float] # prior day high (long breakout level)
    trigger_low: Optional[float]  # prior day low (short breakdown level)
    sma_200: Optional[float] = None
    prior_swing_low: Optional[float] = None
    prior_swing_high: Optional[float] = None
    ftfc_score: float = 0.0       # -1.0 (bearish) to +1.0 (bullish)
    high_impact_catalyst_in_window: bool = False
    analog_median_day_5_pct: Optional[float] = None  # %

    # ---- Derived helpers ----
    def trigger_for(self, direction: Direction) -> float:
        """Return the structural trigger level for this direction.
        Falls back to the last close ± a small buffer if the strat
        section didn't populate triggers (e.g. a thinly-traded ticker
        where summarize_strat_status got <2 daily bars)."""
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

# minimum FTFC alignment for conservative to take a trade at all
_CONSERVATIVE_MIN_FTFC = 0.30


# ───────────────────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────────────────


def compute_persona_plans(ctx: PlanContext) -> list[PersonaPlan]:
    """Return the three persona plans (aggressive, neutral, conservative)
    for the given context. Order is fixed so the UI renders consistently.

    Returns an empty list if `ctx.direction == 'flat'` — there is no
    trade to size. The caller (orchestrator) should still emit risk
    flags but the plan card just hides itself."""
    if ctx.direction == "flat":
        return []
    return [
        _plan(ctx, "aggressive"),
        _plan(ctx, "neutral"),
        _plan(ctx, "conservative"),
    ]


def _plan(ctx: PlanContext, persona: str) -> PersonaPlan:
    """Compute one persona's plan. Long and short are mirror images of
    each other — for short, we flip the sign on the offsets so the
    entry/stop/targets land below the trigger instead of above."""
    sign = 1.0 if ctx.direction == "long" else -1.0
    atr = ctx.safe_atr()
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
        # real swing low or the 200-SMA sits between the ATR stop and
        # the entry. Only candidates on the correct side of entry
        # qualify (a long stop must be BELOW the entry midpoint, even
        # if SMA200 happens to sit above it after a recent breakout).
        candidates = [raw_stop]
        for level in (ctx.prior_swing_low, ctx.sma_200):
            if level is None or ctx.direction != "long":
                continue
            if level < midpoint:   # only below-entry levels are valid stops
                candidates.append(level)
        for level in (ctx.prior_swing_high, ctx.sma_200):
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
    if persona == "conservative" and ctx.ftfc_score < _CONSERVATIVE_MIN_FTFC:
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
                                 risk_per_unit, size)

    return PersonaPlan(
        persona=persona,  # type: ignore[arg-type]
        entry_zone=EntryZone(low=round(entry_lo, 2), high=round(entry_hi, 2)),
        stop=round(stop, 2),
        targets=[round(t, 2) for t in targets],
        position_size_pct=round(size, 2),
        rationale=rationale,
    )


def _build_rationale(
    persona: str, ctx: PlanContext, atr: float,
    midpoint: float, stop: float, risk: float, size: float,
) -> str:
    """One-sentence explanation of the recipe — references the actual
    inputs so it changes when the inputs change."""
    if size == 0.0:
        if persona == "conservative":
            if ctx.ftfc_score < _CONSERVATIVE_MIN_FTFC:
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

    stop_atr = abs(midpoint - stop) / atr
    if persona == "aggressive":
        return (
            f"{stop_atr:.1f}× ATR stop, R = ${risk:.2f}, targets at 2R/3.5R/5R; "
            f"{size:.2f}× size on {ctx.conviction} conviction."
        )
    if persona == "neutral":
        return (
            f"~1× ATR stop (${atr:.2f}), R = ${risk:.2f}, targets at 1R/2R/3R; "
            f"{size:.2f}× size on {ctx.conviction} conviction (canonical base case)."
        )
    if persona == "conservative":
        damper_note = (
            " (catalyst damper applied)"
            if ctx.high_impact_catalyst_in_window else ""
        )
        return (
            f"{stop_atr:.1f}× ATR stop anchored at structure, R = ${risk:.2f}, "
            f"targets at 1R/1.75R; {size:.2f}× size{damper_note}."
        )
    return ""


# ───────────────────────────────────────────────────────────────────────────
# Construction helper used by the orchestrator
# ───────────────────────────────────────────────────────────────────────────


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
    close = float(market.get("close") or market.get("last_close") or 0.0)
    atr = float(market.get("atr_14") or market.get("atr") or 0.0)

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
        ftfc_score=float(strat.get("ftfc_score") or 0.0),
        high_impact_catalyst_in_window=high_impact_in_window,
        analog_median_day_5_pct=_maybe_float(analog_d5),
    )


def _maybe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
