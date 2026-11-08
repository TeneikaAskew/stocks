"""Deterministic per-persona trade-plan calculator.

Replaces LLM-generated entry/stop/targets/sizing with explicit, auditable
math so the same bundle always produces the same plan. The LLM still
generates the qualitative narrative (thesis, bull/bear case, risk
flags) but it does NOT roll the numbers any more — that removes the
run-to-run drift the user observed across two AVGO Apr-7 invocations
(targets shifted from $336/$349/$361 → $329/$341/$354 with no
underlying data change).

Three recipes, one per risk persona. Every distance is the ticker's own
calibrated parameter (FEAT-STRAT-001, lib.strat_levels.LevelParams, read
from ticker_level_params and recorded in the session's level_basis):

  * entry zone: entry_buffer_{persona}_lo_atr / _hi_atr beyond the trigger,
    quantiles of the ticker's follow-through after past breaks;
  * stop: stop_{persona}_atr from the entry midpoint, quantiles of the
    adverse excursion the persona's filled breaks that held survived; the
    conservative persona still anchors at the closest structure inside it;
    min_stop_atr is the floor;
  * targets: target_{persona}_{k}_r in the persona's own R, the excursion a
    stated share of its filled breaks reached before the stop;
  * sizing, the catalyst damper and the FTFC gates are allocation policy,
    unchanged: aggressive the largest size, conservative the smallest and
    standing aside against the 200-SMA or weak FTFC alignment.

A parameter that is not ok gives the persona a plan with no entry, stop,
targets or risk metrics, and a rationale naming the parameter.

The math is documented inline so a future reader (or the user reading
the persona-plan card) can see exactly why each number came out the way
it did. No magic constants without a comment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Optional

from lib.strat_levels import (
    MIN_STOP_KEY, PARAMS_BASIS_MISMATCH, LevelParam, LevelParams, SessionLevels,
    share_text, entry_buffer_key, orb_only_text, stop_key, target_key,
)

from .schema import EntryZone, PersonaPlan

logger = logging.getLogger(__name__)


Direction = Literal["long", "short", "flat"]
Conviction = Literal["low", "medium", "high"]
Regime = Literal["normal", "extended", "orb_only"]


@dataclass
class PlanContext:
    """Inputs the planner needs to size a trade.

    All fields are deterministic. The trigger, stop anchor and orb_only
    reason come from ``levels`` (a lib.strat_levels.SessionLevels built by
    build_session_levels or read from the session's level_basis); the
    planner holds no level walk of its own (FEAT-STRAT-001).
    """

    direction: Direction          # 'long' / 'short' / 'flat' from the PM
    conviction: Conviction        # 'low' / 'medium' / 'high'
    close: float                  # most recent close (yesterday's close at as_of)
    atr: Optional[float]          # ATR(14) from market_data_daily (context only)
    levels: Optional[SessionLevels] = None
    sma_200: Optional[float] = None
    prior_swing_low: Optional[float] = None
    prior_swing_high: Optional[float] = None
    ftfc_score: float = 0.0       # -1.0 (bearish) to +1.0 (bullish)
    high_impact_catalyst_in_window: bool = False
    analog_median_day_5_pct: Optional[float] = None  # %
    gap_pct: Optional[float] = None

    # ---- Derived helpers ----
    def reference_price(self) -> float:
        """The builder's reference: the session premarket's pre_vwap when
        the snapshot is present, else the prior close."""
        if self.levels is not None and self.levels.reference is not None:
            return float(self.levels.reference)
        return float(self.close)

    @property
    def params(self) -> Optional[LevelParams]:
        """The ticker's level parameters, carried on the session's levels
        (recorded in its level_basis)."""
        return self.levels.params if self.levels is not None else None

    def plan_atr(self) -> float:
        """The ATR every persona offset is measured in: the session levels'
        ATR in the policy's basis. A side with a trigger always has one (the
        builder returns atr_unavailable otherwise), so a trigger without it
        is a bug and raises."""
        atr = self.levels.atr if self.levels is not None else None
        if atr is None or not atr > 0:
            raise PlanContextUnavailable(
                "a side has a trigger but the session levels carry no positive ATR")
        return float(atr)

    def orb_only_reason(self, direction: Direction) -> Optional[str]:
        if self.levels is None:
            return "no_levels"
        return self.levels.side(direction).reason


# ───────────────────────────────────────────────────────────────────────────
# Trigger + regime: read from the one level builder
# ───────────────────────────────────────────────────────────────────────────


def select_trigger_and_regime(
    ctx: PlanContext, direction: Direction,
) -> tuple[Regime, Optional[float], Optional[float], Optional[float], bool]:
    """The side's pick from ``ctx.levels`` (lib.strat_levels.SessionLevels).

    Returns ``(regime, trigger, stop_anchor, distance_atr, is_blue_sky)``.
    ``trigger`` and ``distance_atr`` are None on an orb_only side; the reason
    is ``ctx.orb_only_reason(direction)``. ``stop_anchor`` is the builder's
    stop for the side (the nearest in-window level on the other side of the
    reference). ``is_blue_sky`` is always False (no level is synthesized).
    """
    if direction not in ("long", "short"):
        return ("normal", None, None, None, False)
    if ctx.levels is None:
        return ("orb_only", None, None, None, False)
    side = ctx.levels.side(direction)
    if side.trigger is None:
        return ("orb_only", None, None, None, False)
    stop_anchor = float(side.stop["price"]) if side.stop else None
    return ("normal", float(side.trigger["price"]), stop_anchor, side.distance_atr, False)


# ─── Allocation policy (not ticker distances) ─────────────────────────────

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

    On a side where ``select_trigger_and_regime`` returns ``orb_only``
    (no trigger: see lib.strat_levels.ORB_ONLY_REASONS), each persona's
    plan is a no-trigger ``orb_only`` PersonaPlan with null entry and stop
    whose rationale is the side's ORB_ONLY_COPY line.
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

    When ``regime == 'orb_only'`` (no trigger on this side), returns a
    plan with zero sizing, entry_zone, stop and risk_metrics null and no
    targets, and the side's orb_only copy as the rationale.
    """
    if regime == "orb_only":
        return _orb_only_plan(ctx, persona)

    if trigger is None:
        # No level, no plan: never a synthesized trigger.
        return _orb_only_plan(ctx, persona)
    sign = 1.0 if ctx.direction == "long" else -1.0
    params = ctx.params
    if params is None:
        return _params_unavailable_plan(ctx, persona, None)
    target_keys = _persona_target_keys(params, persona)
    needed = [entry_buffer_key(persona, "lo"), entry_buffer_key(persona, "hi"),
              stop_key(persona), MIN_STOP_KEY] + target_keys[:1]
    blocked = params.first_not_ok(needed)
    if blocked is not None:
        return _params_unavailable_plan(ctx, persona, blocked)
    r_multiples: list[float] = []
    truncated_at = None
    for key in target_keys:
        p = params.param(key)
        if p.ok:
            r_multiples.append(p.value)
            continue
        if p.status == "no_positive_target":
            truncated_at = p
            break
        return _params_unavailable_plan(ctx, persona, p)
    atr = ctx.plan_atr()

    # ── 1. Entry zone ──────────────────────────────────────────────
    buf_lo_mult = params.value(entry_buffer_key(persona, "lo"))
    buf_hi_mult = params.value(entry_buffer_key(persona, "hi"))
    entry_lo = trigger + sign * buf_lo_mult * atr
    entry_hi = trigger + sign * buf_hi_mult * atr
    if entry_lo > entry_hi:  # short side flips the order
        entry_lo, entry_hi = entry_hi, entry_lo
    midpoint = (entry_lo + entry_hi) / 2

    # ── 2. Stop ────────────────────────────────────────────────────
    raw_stop = midpoint - sign * params.value(stop_key(persona)) * atr

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

    # Floor: no stop closer to the entry midpoint than the ticker's
    # min_stop_atr (the median adverse excursion of held breaks).
    min_distance = params.value(MIN_STOP_KEY) * atr
    if abs(midpoint - stop) < min_distance:
        stop = midpoint - sign * min_distance

    # ── 3. Targets ─────────────────────────────────────────────────
    risk_per_unit = abs(midpoint - stop)
    targets: list[float] = []
    for r_mult in r_multiples:
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
                                 trigger=trigger, is_blue_sky=is_blue_sky,
                                 r_multiples=r_multiples, truncated_at=truncated_at)

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
    """The plan for an orb_only side: no level, so no entry, no stop, no
    targets and no risk metrics. Nothing is synthesized (FEAT-STRAT-001)."""
    reason = ctx.orb_only_reason(ctx.direction)
    window = ctx.levels.side(ctx.direction).window if ctx.levels is not None else None
    return PersonaPlan(
        persona=persona,  # type: ignore[arg-type]
        entry_zone=None,
        stop=None,
        targets=[],
        position_size_pct=0.0,
        rationale="ORB-only: " + orb_only_text(reason, ctx.direction, window),
        regime="orb_only",
        risk_metrics=None,
    )


def _persona_target_keys(params: LevelParams, persona: str) -> list[str]:
    """The persona's target keys T1, T2, ... in order: as many as the
    policy defines for it."""
    keys = []
    k = 1
    while target_key(persona, k) in params.params:
        keys.append(target_key(persona, k))
        k += 1
    return keys


def param_unavailable_text(persona: str, param: Optional[LevelParam]) -> str:
    """The rationale for a persona plan whose parameter is not ok: names the
    parameter, its status, its sample and the minimum."""
    if param is None:
        return (f"No {persona} plan: the session's level parameters were not "
                f"recorded, so no entry, stop or target is published.")
    ticker = param.ticker or "the ticker"
    if param.status == "no_positive_target":
        return (f"No {persona} plan: no target met the persona's reach share on "
                f"{ticker}'s filled breaks ({param.key}, sample {param.sample_n}).")
    if param.status == "insufficient_history":
        return (f"No {persona} plan: {param.key} needs {param.min_sample} samples of "
                f"{ticker}'s history and has {param.sample_n}.")
    if param.status == PARAMS_BASIS_MISMATCH:
        return (f"No {persona} plan: {ticker}'s values are being recalibrated for the "
                f"new ATR basis ({param.key}).")
    return (f"No {persona} plan: {param.key} is {param.status} for {ticker} "
            f"(sample {param.sample_n}, minimum {param.min_sample}).")


def _params_unavailable_plan(ctx: PlanContext, persona: str,
                             param: Optional[LevelParam]) -> PersonaPlan:
    """A side with a trigger whose persona parameter is not ok: no entry,
    stop, targets or risk metrics; nothing published from a non-ok value."""
    return PersonaPlan(
        persona=persona,  # type: ignore[arg-type]
        entry_zone=None,
        stop=None,
        targets=[],
        position_size_pct=0.0,
        rationale=param_unavailable_text(persona, param),
        regime="normal",
        risk_metrics=None,
    )


def _r_text(r: float) -> str:
    return f"{r:.2f}".rstrip("0").rstrip(".") + "R"


def _entry_text(ctx: PlanContext, persona: str) -> str:
    """The entry zone's edges and the share of the ticker's past breaks that
    reached each: an edge at follow-through quantile q is reached by 1 - q
    of breaks (never the quantile stated as that share)."""
    params = ctx.params
    parts = []
    for edge in ("lo", "hi"):
        p = params.param(entry_buffer_key(persona, edge))
        if p.statistic_q is None:
            parts.append("at the trigger")
        else:
            parts.append(f"{p.value:.2f}x ATR past the trigger, reached by "
                         f"{share_text(1 - p.statistic_q)} of past breaks")
    return "entry " + " to ".join(parts)


def _build_rationale(
    persona: str, ctx: PlanContext, atr: float,
    midpoint: float, stop: float, risk: float, size: float,
    regime: Regime = "normal",
    distance_atr: Optional[float] = None,
    trigger: Optional[float] = None,
    is_blue_sky: bool = False,
    r_multiples: Optional[list] = None,
    truncated_at: Optional[LevelParam] = None,
) -> str:
    """One-sentence explanation of the recipe — references the actual
    inputs (the ticker's calibrated parameters) so it changes when they do.

    On ``regime == 'extended'`` setups, prepends an ORB-confirmation note.
    ``is_blue_sky`` is accepted for call compatibility and ignored.
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
    targets = "/".join(_r_text(r) for r in (r_multiples or []))
    tail = ""
    if truncated_at is not None:
        tail = (f" No further target met the persona's reach share on filled breaks "
                f"(sample {truncated_at.sample_n}).")
    structure = " anchored at structure" if persona == "conservative" else ""
    damper_note = (" (catalyst damper applied)"
                   if persona == "conservative" and ctx.high_impact_catalyst_in_window else "")
    return extended_prefix + (
        f"{_entry_text(ctx, persona)}; {stop_atr:.2f}x ATR stop{structure} (${atr:.2f} ATR), "
        f"R = ${risk:.2f}, targets at {targets}; {size:.2f}× size on {ctx.conviction} "
        f"conviction{damper_note}.{tail}"
    )


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
    # target and distance is measured from it. The previous `or 0.0` turned a missing price
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
    # ATR(14) for context only: every persona offset is measured in the
    # session levels' ATR in the policy's basis (PlanContext.plan_atr), so a
    # missing value stays None instead of a fabricated 0.0 or a percent of
    # the close (FEAT-STRAT-001 per-ticker parameters removed safe_atr).
    atr = _maybe_float(market.get("atr_14"))
    if atr is None:
        atr = _maybe_float(market.get("atr"))

    # The session's levels (FEAT-STRAT-001): the level_basis the bundle
    # carries, read from the session's live brief row with the planner's
    # newer premarket snapshot applied, or built by build_session_levels.
    session_levels = None
    basis = bundle.get("session_levels") or {}
    if isinstance(basis, dict) and basis.get("level_basis"):
        session_levels = SessionLevels.from_basis(basis["level_basis"])

    premarket = market.get("premarket") or {}
    gap_pct = _maybe_float(premarket.get("gap_pct"))

    return PlanContext(
        direction=direction,
        conviction=conviction,
        close=close,
        atr=atr,
        levels=session_levels,
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
        gap_pct=gap_pct,
    )


def _maybe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
