"""
Async orchestrator for the AI Insights pipeline.

Graph topology (11 nodes):

    parallel analyst tier
    ┌──────────────────────────┐
    │ market_analyst           │
    │ strat_analyst            │
    │ options_analyst          │──┐
    │ catalyst_analyst         │  │
    └──────────────────────────┘  │
                                  ▼
             bull_researcher  bear_researcher   (parallel)
                       │      │
                       └──┬───┘
                          ▼
                  research_manager (judge)
                          │
                          ▼
                        trader
                          │
      ┌───────────────────┼───────────────────┐
      ▼                   ▼                   ▼
 aggressive risk    conservative risk    neutral risk   (parallel)
      └───────────────────┼───────────────────┘
                          ▼
                  portfolio_manager
                          │
                          ▼
                   InsightReport

Design notes (all driven by the audit):

- Routes are snapshotted at pipeline start (RouteSnapshot). No
  mid-run lookups — `model_versions` in the final report is
  consistent.
- `asyncio.gather(*, return_exceptions=True)` on the analyst and
  risk tiers so one failure doesn't kill the run. Failed analysts
  are recorded in `failed_sections` and downstream agents continue
  with what's available.
- A pluggable LLMClient factory so tests can inject a mock adapter.
- The orchestrator measures end-to-end latency and totals per-call
  cost from every `Usage.cost_usd()`.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import date as date_type, datetime, timezone
from typing import Any, Callable, Literal, Optional, Type

from pydantic import BaseModel

from .llm_client import CompletionResult, LLMClient, Message, RouteSnapshot, get_adapter
from .pricing import Usage
from .prompts import get_prompt
from .schema import (
    ALL_ROLES,
    AgentRole,
    AnalystOutput,
    Catalyst,
    EntryZone,
    InsightReport,
    JournalRef,
    JudgeOutput,
    PortfolioManagerOutput,
    ResearcherOutput,
    RiskFlag,
    RiskPersonaOutput,
    SignalRef,
    StratSnapshot,
    TraderOutput,
)
from .summarizers import build_context_bundle, retrieve_similar_journal

logger = logging.getLogger(__name__)

# Types for the injectable LLM factory used in tests
LLMFactory = Callable[[str], LLMClient]


def _default_factory(provider: str) -> LLMClient:
    """Default factory resolves via the adapter registry."""
    return get_adapter(provider)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tracker — accumulates cost and usage across all nodes in one run
# ---------------------------------------------------------------------------


class _Tracker:
    def __init__(self) -> None:
        self.total_cost: float = 0.0
        self.calls: int = 0
        # Per-role accumulator. Keys are role identifiers — analyst and
        # risk subdivide further (e.g. "analyst:market", "risk:neutral")
        # so dashboards can attribute spend to specific personas. Audit
        # 2026-05-08 G.P3.2.
        self.per_role_cost: dict[str, float] = {}

    def add(self, usage: Usage, *, role_key: str) -> None:
        self.calls += 1
        try:
            cost = usage.cost_usd()
        except KeyError:
            logger.warning(
                "no price table entry for %s:%s — cost not tracked",
                usage.provider,
                usage.model,
            )
            return
        self.total_cost += cost
        self.per_role_cost[role_key] = self.per_role_cost.get(role_key, 0.0) + cost


# ---------------------------------------------------------------------------
# Node runners — each returns the parsed Pydantic output of one step
# ---------------------------------------------------------------------------


async def _run_node(
    *,
    role: AgentRole,
    sub: Optional[str],
    snapshot: RouteSnapshot,
    factory: LLMFactory,
    system: str,
    user_payload: str,
    response_model: Type[BaseModel],
    tracker: _Tracker,
    temperature: float = 0.3,
    max_output_tokens: int = 1800,
) -> BaseModel:
    provider, model = snapshot.get(role)
    client = factory(provider)
    result: CompletionResult = await client.complete(
        model=model,
        system=system,
        messages=[Message(role="user", content=user_payload)],
        response_model=response_model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    role_key = f"{role}:{sub}" if sub else role
    tracker.add(result.usage, role_key=role_key)
    return result.parsed


def _analyst_payload(bundle: dict, section: str) -> str:
    """Isolate one section's context into a compact JSON blob for the
    analyst prompt. `section` is the prompt-facing name (market, strat,
    options, catalyst) — the bundle may store data under a slightly
    different key (e.g. `catalysts`); we resolve that via
    _analyst_section_key."""
    import json

    data_key = _analyst_section_key(section)
    return json.dumps(
        {
            "ticker": bundle["ticker"],
            "as_of": bundle.get("as_of"),
            "section": section,
            "data": bundle.get(data_key, {"available": False}),
        },
        default=str,
    )


def _debate_payload(bundle: dict, analyst_reports: dict[str, AnalystOutput]) -> str:
    """Bull/bear researchers see the full analyst tier output."""
    import json

    return json.dumps(
        {
            "ticker": bundle["ticker"],
            "analysts": {
                name: report.model_dump() if report else None
                for name, report in analyst_reports.items()
            },
            "raw_bundle": {
                k: v for k, v in bundle.items() if k not in ("failed_sections",)
            },
        },
        default=str,
    )


def _judge_payload(bull: ResearcherOutput, bear: ResearcherOutput) -> str:
    import json

    return json.dumps(
        {"bull": bull.model_dump(), "bear": bear.model_dump()},
        default=str,
    )


def _trader_payload(
    bundle: dict,
    judge: JudgeOutput,
    analyst_reports: dict[str, AnalystOutput],
) -> str:
    import json

    return json.dumps(
        {
            "ticker": bundle["ticker"],
            "verdict": judge.model_dump(),
            "strat": bundle.get("strat", {}),
            "market": bundle.get("market", {}),
            "analysts": {
                k: (v.model_dump() if v else None) for k, v in analyst_reports.items()
            },
        },
        default=str,
    )


def _risk_payload(bundle: dict, trader: TraderOutput) -> str:
    import json

    return json.dumps(
        {
            "ticker": bundle["ticker"],
            "trade_plan": trader.model_dump(),
            "strat": bundle.get("strat", {}),
            "catalysts": bundle.get("catalysts", {}),
            "market": bundle.get("market", {}),
        },
        default=str,
    )


def _portfolio_payload(
    bundle: dict,
    judge: JudgeOutput,
    trader: TraderOutput,
    risk_outputs: list[RiskPersonaOutput],
    bull: ResearcherOutput,
    bear: ResearcherOutput,
) -> str:
    import json

    return json.dumps(
        {
            "ticker": bundle["ticker"],
            "verdict": judge.model_dump(),
            "trade_plan": trader.model_dump(),
            "risk_reviews": [r.model_dump() for r in risk_outputs],
            "bull_case": bull.case,
            "bear_case": bear.case,
            "failed_sections": bundle.get("failed_sections", []),
            "summaries": {
                k: bundle.get(k, {}).get("available") for k in ("market", "strat", "options", "gamma", "catalysts", "sentiment")
            },
        },
        default=str,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_insight_pipeline(
    ticker: str,
    as_of: Optional[date_type] = None,
    *,
    snapshot: Optional[RouteSnapshot] = None,
    llm_factory: LLMFactory = _default_factory,
    query_embedding: Optional[list[float]] = None,
) -> InsightReport:
    """Run the full pipeline and return a validated InsightReport.

    Parameters
    ----------
    ticker : symbol to analyze
    as_of  : historical date cutoff; defaults to latest
    snapshot :
        Optional pre-loaded route snapshot. Tests inject a stub; the
        Cloud Run job loads from Cloud SQL via load_routes_snapshot().
    llm_factory :
        Function (provider:str) -> LLMClient instance. Tests inject
        a mock so no provider SDK is called.
    query_embedding :
        Optional pre-computed query vector for reflection memory. When
        omitted, reflection memory is skipped (the orchestrator does
        not embed the bundle itself to keep this module free of
        Vertex dependencies).
    """

    start = time.monotonic()
    tracker = _Tracker()

    # 1. Build the grounded context bundle (no LLM yet)
    bundle = build_context_bundle(ticker, as_of)

    # 2. Resolve route snapshot (frozen for the whole run)
    if snapshot is None:
        from .model_routing import load_routes_snapshot

        snapshot = load_routes_snapshot()

    # 3. Parallel analyst tier — one per section
    analyst_sections = ("market", "strat", "options", "gamma", "catalyst", "sentiment")
    analyst_tasks = [
        _run_node(
            role="analyst",
            sub=section,
            snapshot=snapshot,
            factory=llm_factory,
            system=get_prompt("analyst", sub=section),
            user_payload=_analyst_payload(bundle, section),
            response_model=AnalystOutput,
            tracker=tracker,
        )
        for section in analyst_sections
    ]
    raw_analyst_results = await asyncio.gather(*analyst_tasks, return_exceptions=True)

    analyst_reports: dict[str, AnalystOutput] = {}
    failed_sections: list[str] = list(bundle.get("failed_sections", []))
    failed_reasons: dict[str, str] = dict(
        bundle.get("failed_section_reasons", {})
    )
    for section, result in zip(analyst_sections, raw_analyst_results):
        if isinstance(result, Exception):
            logger.warning("analyst %s failed: %s", section, result)
            if section not in failed_sections:
                failed_sections.append(section)
            failed_reasons[section] = (
                f"analyst-llm: {type(result).__name__}: {result}"
            )
            analyst_reports[section] = None  # type: ignore[assignment]
        else:
            analyst_reports[section] = result  # type: ignore[assignment]

    if all(r is None for r in analyst_reports.values()):
        raise RuntimeError(
            f"all analyst nodes failed for {ticker} — aborting pipeline"
        )

    # 4. Bull and bear researchers (parallel)
    debate_user = _debate_payload(bundle, analyst_reports)
    bull_task = _run_node(
        role="bull",
        sub=None,
        snapshot=snapshot,
        factory=llm_factory,
        system=get_prompt("bull"),
        user_payload=debate_user,
        response_model=ResearcherOutput,
        tracker=tracker,
    )
    bear_task = _run_node(
        role="bear",
        sub=None,
        snapshot=snapshot,
        factory=llm_factory,
        system=get_prompt("bear"),
        user_payload=debate_user,
        response_model=ResearcherOutput,
        tracker=tracker,
    )
    raw_bull_bear = await asyncio.gather(bull_task, bear_task, return_exceptions=True)
    bull, bear = raw_bull_bear
    if isinstance(bull, Exception):
        logger.warning("bull researcher failed: %s", bull)
        bull = ResearcherOutput(
            stance="bull", case="Analysis unavailable due to LLM error.", key_points=[]
        )
    if isinstance(bear, Exception):
        logger.warning("bear researcher failed: %s", bear)
        bear = ResearcherOutput(
            stance="bear", case="Analysis unavailable due to LLM error.", key_points=[]
        )

    # 5. Research manager (judge)
    judge: JudgeOutput = await _run_node(  # type: ignore[assignment]
        role="judge",
        sub=None,
        snapshot=snapshot,
        factory=llm_factory,
        system=get_prompt("judge"),
        user_payload=_judge_payload(bull, bear),
        response_model=JudgeOutput,
        tracker=tracker,
    )

    # 6. Trader
    try:
        trader: TraderOutput = await _run_node(  # type: ignore[assignment]
            role="trader",
            sub=None,
            snapshot=snapshot,
            factory=llm_factory,
            system=get_prompt("trader"),
            user_payload=_trader_payload(bundle, judge, analyst_reports),
            response_model=TraderOutput,
            tracker=tracker,
        )
    except Exception as exc:
        logger.warning("trader node failed: %s — using flat default", exc)
        trader = TraderOutput(
            direction="flat",
            entry_zone=EntryZone(low=0.0, high=0.0),
            stop=0.0,
            targets=[],
            time_horizon="swing",
            invalidation="Trade plan unavailable due to LLM error.",
            confidence=0.0,
        )

    # 7. Risk debate (3 personas in parallel)
    risk_user = _risk_payload(bundle, trader)
    risk_sub_names = ("aggressive", "conservative", "neutral")
    risk_tasks = [
        _run_node(
            role="risk",
            sub=sub,
            snapshot=snapshot,
            factory=llm_factory,
            system=get_prompt("risk", sub=sub),
            user_payload=risk_user,
            response_model=RiskPersonaOutput,
            tracker=tracker,
        )
        for sub in risk_sub_names
    ]
    raw_risk_results = await asyncio.gather(*risk_tasks, return_exceptions=True)
    risk_outputs: list[RiskPersonaOutput] = []
    for sub, result in zip(risk_sub_names, raw_risk_results):
        if isinstance(result, Exception):
            logger.warning("risk %s failed: %s", sub, result)
            continue
        risk_outputs.append(result)  # type: ignore[arg-type]

    # 8. Portfolio manager (final merge)
    try:
        pm: PortfolioManagerOutput = await _run_node(  # type: ignore[assignment]
            role="portfolio_manager",
            sub=None,
            snapshot=snapshot,
            factory=llm_factory,
            system=get_prompt("portfolio_manager"),
            user_payload=_portfolio_payload(
                bundle, judge, trader, risk_outputs, bull, bear
            ),
            response_model=PortfolioManagerOutput,
            tracker=tracker,
        )
    except Exception as exc:
        logger.warning("portfolio_manager failed: %s — assembling from trader output", exc)
        pm = PortfolioManagerOutput(
            direction=trader.direction,
            conviction="low",
            thesis=trader.invalidation,
            entry_zone=trader.entry_zone,
            stop=trader.stop,
            targets=trader.targets,
            invalidation=trader.invalidation,
            time_horizon=trader.time_horizon,
            key_levels={},
            bull_case=bull.case,
            bear_case=bear.case,
            confidence_score=0.3,
        )

    # 9. Assemble final InsightReport
    strat_section = bundle.get("strat", {})
    strat_status = _build_strat_snapshot(strat_section)
    catalysts = _build_catalysts(bundle.get("catalysts", {}))

    # Deterministic key_levels — sourced directly from the context bundle
    # so the report always shows the FULL multi-timeframe level map
    # (PDH/PDL/PWH/PWL/PMH/PML/PQH/PQL/PYH/PYL + effective_PDH/PDL +
    # gamma flip/kings/gates + EMA 20/SMA 200 + Max Pain), not just
    # whichever subset the PM LLM happened to surface. Previously this
    # was a fallback-only path that ran when pm.key_levels was empty,
    # which is why QQQ 5/6 reports showed only "Prev High / Prev Low"
    # and hid PWH/PMH/PQH/PYH from the user even though the trade
    # planner's blue-sky classification depended on them.
    pm.key_levels = _derive_key_levels(bundle)

    # Flatten all risk flags from all personas. The numeric `plan` field
    # the LLM personas may emit is intentionally IGNORED here — it's
    # replaced below with a deterministic per-persona calculation so the
    # entry/stop/targets/sizing math is reproducible and auditable.
    all_flags: list[RiskFlag] = []
    for r in risk_outputs:
        all_flags.extend(r.flags)

    # Reflection memory (audit G.P2.12): build a query embedding from
    # the bundle and retrieve the 5 nearest historical journal entries.
    # If the caller injected an embedding (tests / replay), use that
    # directly. Otherwise generate one inline from a compact summary
    # of today's setup. Any failure (Vertex creds missing, network
    # blip, table missing) degrades to no similar-trade context — the
    # rest of the report still ships.
    if query_embedding is None:
        try:
            from .embeddings import embed_text
            query_text = _build_embedding_query_text(ticker, bundle)
            query_embedding = await embed_text(query_text)
            logger.info(
                "reflection_memory ticker=%s query_text=%r embedded=true",
                ticker, query_text,
            )
        except Exception as e:
            logger.warning(
                "reflection_memory: embedding failed for %s (%s: %s) — "
                "skipping similar-trade lookup",
                ticker, type(e).__name__, e,
            )
            query_embedding = None

    similar: list[JournalRef] = []
    if query_embedding:
        try:
            similar = retrieve_similar_journal(ticker, query_embedding, k=5)
        except Exception as e:
            logger.warning("similar-journal lookup failed: %s", e)

    # Respect any explicit block from the risk debate
    blocked = any(f.severity == "block" for f in all_flags)
    direction = "flat" if blocked else pm.direction

    # Deterministic conviction calibration (#349). Replaces the LLM's
    # `pm.conviction` with a math-from-inputs computation. Audit
    # 2026-05-08 G.P3.1's prompt-only fix didn't take — 21/21 reports
    # still showed 'medium' post-PR-A. The data needed to compute
    # conviction is already deterministic at this point in the
    # pipeline (analyst agreement count, FTFC, risk flags,
    # confidence_score) so there's no analytical reason to keep
    # asking the LLM to do this 4-input threshold check.
    analyst_agreement = _count_analyst_agreement(
        analyst_reports, direction
    )
    ftfc_score = float((bundle.get("strat") or {}).get("ftfc_score") or 0.0)
    risk_severities = [f.severity for f in all_flags]
    conviction = _calibrate_conviction(
        direction=direction,
        confidence_score=float(pm.confidence_score),
        analyst_agreement_count=analyst_agreement,
        ftfc_score=ftfc_score,
        risk_severities=risk_severities,
    )
    if conviction != pm.conviction:
        logger.info(
            "conviction_calibrated ticker=%s direction=%s llm=%s "
            "deterministic=%s analyst_agreement=%d ftfc=%.2f "
            "warns=%d blocks=%d confidence=%.2f",
            ticker, direction, pm.conviction, conviction,
            analyst_agreement, ftfc_score,
            sum(1 for s in risk_severities if s == "warn"),
            sum(1 for s in risk_severities if s == "block"),
            float(pm.confidence_score),
        )

    # Filter supporting_signals by trade direction so the report doesn't
    # cite contradictory alerts (e.g. PUT signals under a long thesis).
    # Audit 2026-05-08 G.P2.14: QQQ 5/7 long report cited 5 PUT signals.
    signals_refs = _build_signal_refs(
        bundle.get("signals", {}), direction=direction
    )

    # ── Deterministic persona plans ────────────────────────────────
    # Compute entry/stop/targets/sizing from the same bundle the LLMs
    # saw, using the recipes documented in lib/agents/trade_planner.py.
    # This replaces the LLM's free-form plan — the LLM still narrates
    # (thesis, bull/bear case, risk flags) but the numbers are now
    # reproducible across runs.
    from .trade_planner import compute_persona_plans, context_from_bundle
    try:
        plan_ctx = context_from_bundle(bundle, direction, conviction)
        persona_plans = compute_persona_plans(plan_ctx)
    except Exception as exc:
        logger.warning("deterministic plan compute failed: %s", exc)
        persona_plans = []

    # Surface the trigger regime at the top level so brief / Discord
    # consumers can render different copy without iterating into
    # persona_plans. All three personas share the same regime (it's
    # determined per-context, not per-persona). If plans failed to
    # compute, default to 'normal' — the LLM's plan is the only source.
    regime = persona_plans[0].regime if persona_plans else "normal"

    # Use the deterministic persona plan as the source of truth for the
    # headline entry/stop/targets. The LLM PM is allowed to *suggest*
    # numbers in its response but those are replaced here with the
    # audit-able math from `trade_planner.compute_persona_plans`. The
    # neutral persona is the canonical "headline" version (1 ATR stop,
    # 1R/2R/3R targets); aggressive and conservative remain available
    # as alternatives in `report.persona_plans`.
    #
    # This closes the LLM-hallucination surface that produced ARM 4/20's
    # $237.68 entry zone (a number sourced from outside the bundle —
    # see docs/plans/INSIGHT_ZONE_HALLUCINATION_PLAN.md). On orb_only
    # regimes the persona plan publishes placeholder bracketing levels
    # and the rationale tells the trader to wait for the opening range.
    if persona_plans:
        canonical = next(
            (p for p in persona_plans if p.persona == "neutral"),
            persona_plans[0],
        )
        headline_entry_zone = canonical.entry_zone
        headline_stop = canonical.stop
        headline_targets = canonical.targets
    else:
        # Deterministic plan compute failed — fall back to the LLM's
        # numbers so the report still has actionable fields. Degraded
        # but better than emitting an empty plan.
        headline_entry_zone = pm.entry_zone
        headline_stop = pm.stop
        headline_targets = pm.targets

    report = InsightReport(
        ticker=ticker.upper(),
        as_of=datetime.now(timezone.utc) if as_of is None else _as_datetime(as_of),
        direction=direction,
        conviction=conviction,  # deterministic calibration (#349)
        thesis=pm.thesis,
        regime=regime,
        entry_zone=headline_entry_zone,
        stop=headline_stop,
        targets=headline_targets,
        invalidation=pm.invalidation,
        time_horizon=pm.time_horizon,
        key_levels=pm.key_levels,
        strat_status=strat_status,
        catalysts=catalysts,
        bull_case=pm.bull_case,
        bear_case=pm.bear_case,
        risk_flags=all_flags,
        persona_plans=persona_plans,
        supporting_signals=signals_refs,
        similar_past_trades=similar,
        confidence_score=pm.confidence_score,
        failed_sections=failed_sections,
        failed_section_reasons=failed_reasons,
        model_versions=snapshot.model_versions(),
        run_cost_usd=round(tracker.total_cost, 6),
        run_latency_ms=int((time.monotonic() - start) * 1000),
        per_role_cost={k: round(v, 6) for k, v in tracker.per_role_cost.items()},
    )

    # Audit 2026-05-08 G.P1.9 safety-net: warn (don't block) if the LLM
    # named price levels in `thesis` that don't appear in the structured
    # fields. The prompt already forbids this, but LLM compliance varies;
    # the warning surfaces non-compliance so we can measure how often it
    # happens after deploy.
    _validate_thesis_consistency(
        report.thesis,
        ticker=report.ticker,
        entry_zone=report.entry_zone,
        stop=report.stop,
        targets=report.targets,
        key_levels=report.key_levels,
        invalidation=report.invalidation,
    )
    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Match standalone numerals with at least one decimal place (so we don't
# false-positive on "200 SMA" or "RSI 70" which are reference numbers,
# not prices), AND dollar-prefixed prices ("$278.13"). Captures the
# numeric portion only so we can compare against structured fields.
#
# Examples that match:
#   "above 278.13"       → 278.13
#   "$691.09"            → 691.09
#   "targeting 704.38"   → 704.38
#
# Examples that don't:
#   "200 SMA"            (no decimal)
#   "RSI 70"             (no decimal)
#   "+0.20%"             (percentage)
_PRICE_PATTERN = re.compile(r"\$?(\d{2,5}\.\d{1,2})\b")


def _validate_thesis_consistency(
    thesis: str,
    *,
    ticker: str,
    entry_zone,
    stop: float,
    targets: list[float],
    key_levels: dict,
    invalidation: str,
) -> list[float]:
    """Scan `thesis` for price-like numerals and warn on any that don't
    match a structured field value within tolerance.

    Audit 2026-05-08 G.P1.9: LLM thesis text named target levels in
    prose that didn't appear in JSON `targets[]` (e.g. QQQ 5/7 thesis
    said 'targeting 677.8, 691.09 and 704.38' but `targets=[]`
    because the deterministic planner overrode them). PR-C closes
    that decoupling on the prompt side; this validator is the
    safety-net that catches LLM non-compliance after the fact.

    Returns the list of orphan numbers found (mainly for testing —
    the function logs a warning for each but never raises, so the
    pipeline keeps shipping reports).

    Tolerance: 0.5 % absolute distance. Allows for LLM-introduced
    rounding ("around 278.13" matching key_level 278.135) without
    accepting genuinely different numbers (677.8 vs 738.13 is 8 %
    apart — clearly orphan).
    """
    if not thesis:
        return []

    matched_numbers: list[float] = []
    for m in _PRICE_PATTERN.finditer(thesis):
        try:
            matched_numbers.append(float(m.group(1)))
        except (TypeError, ValueError):
            continue
    if not matched_numbers:
        return []

    structured: list[float] = []
    if entry_zone is not None:
        structured.extend([float(entry_zone.low), float(entry_zone.high)])
    if stop is not None:
        try:
            structured.append(float(stop))
        except (TypeError, ValueError):
            pass
    if targets:
        structured.extend(float(t) for t in targets if t is not None)
    if key_levels:
        structured.extend(
            float(v) for v in key_levels.values()
            if isinstance(v, (int, float))
        )
    # Also pull any numerals from the invalidation prose — those are
    # legitimately referenced in the thesis (e.g. "thesis kills below
    # 712.29" matches invalidation "Price closes below 712.29").
    if invalidation:
        for m in _PRICE_PATTERN.finditer(invalidation):
            try:
                structured.append(float(m.group(1)))
            except (TypeError, ValueError):
                continue

    orphans: list[float] = []
    for num in matched_numbers:
        # Within 0.5 % of any structured value → matched
        matched = any(
            abs(num - s) / max(abs(s), 1.0) <= 0.005
            for s in structured
        )
        if not matched:
            orphans.append(num)

    if orphans:
        logger.warning(
            "thesis_validator ticker=%s orphan_count=%d orphans=%s "
            "structured=%s thesis=%r",
            ticker, len(orphans), orphans,
            sorted(set(round(s, 4) for s in structured))[:10],
            thesis[:240],
        )
    return orphans
def _build_embedding_query_text(ticker: str, bundle: dict) -> str:
    """Compose a short natural-language description of today's setup
    for reflection-memory retrieval.

    Captures the same fields that semantically determine "is this trade
    similar to a past one": ticker, strat candle/combo, FTFC direction,
    market regime, gap %, vol tag, position vs 200-SMA. Cosine
    similarity over text-embedding-005 vectors clusters days with
    similar setups together — so a today=2U+bullish-FTFC+gap+0.3% on
    SPY retrieves prior journal entries with similar bar profiles.

    Audit 2026-05-08 G.P2.12: this is the production input that turns
    the dormant reflection-memory infrastructure on.
    """
    strat = bundle.get("strat") or {}
    market = bundle.get("market") or {}
    parts: list[str] = [ticker.upper()]
    if strat.get("last_candle"):
        parts.append(f"strat candle {strat['last_candle']}")
    if strat.get("in_force_combo"):
        parts.append(f"combo {strat['in_force_combo']}")
    if strat.get("ftfc_direction"):
        parts.append(f"FTFC {strat['ftfc_direction']}")
    if market.get("regime"):
        parts.append(f"regime {market['regime']}")
    premarket = market.get("premarket") or {}
    gap_pct = premarket.get("gap_pct")
    if isinstance(gap_pct, (int, float)):
        parts.append(f"gap {gap_pct:+.2f}%")
    if market.get("vol_tag"):
        parts.append(f"vol {market['vol_tag']}")
    above = market.get("above_sma_200")
    if above is True:
        parts.append("above 200-SMA")
    elif above is False:
        parts.append("below 200-SMA")
    return " ".join(parts)


def _count_analyst_agreement(
    analyst_reports: dict, direction: str,
) -> int:
    """Count how many of the 6 analyst sections produced a `bias` that
    matches the report `direction`. Used by `_calibrate_conviction`.

    Mapping: long → bullish, short → bearish, flat → neutral. None or
    failed analysts (value is None in the dict) don't count.
    """
    target_bias = {
        "long": "bullish",
        "short": "bearish",
        "flat": "neutral",
    }.get(direction)
    if target_bias is None:
        return 0
    n = 0
    for analyst in analyst_reports.values():
        if analyst is None:
            continue
        if getattr(analyst, "bias", None) == target_bias:
            n += 1
    return n


def _calibrate_conviction(
    *,
    direction: str,
    confidence_score: float,
    analyst_agreement_count: int,
    ftfc_score: float,
    risk_severities: list[str],
) -> Literal["low", "medium", "high"]:
    """Deterministic conviction calibration. Replaces the LLM's
    pm.conviction with a math-from-inputs threshold check.

    Audit 2026-05-08 G.P3.1 + #349: prompt-only intervention failed
    (21/21 reports stuck on 'medium' post-PR-A). Conviction is a
    4-input threshold check; the LLM adds no judgment value here, so
    derive it deterministically.

    Decision tree:
      * direction == 'flat'                          → 'low'
      * any 'block' in risk_severities               → 'low'
      * ≥4 of 6 analyst sections agree              ┐
        AND |FTFC| ≥ 0.5                            │
        AND zero 'warn' flags                       ├ → 'high'
        AND confidence_score ≥ 0.7                  ┘
      * 2-3 of 6 analyst sections agree             ┐
        AND ≤1 'warn' flag                          ├ → 'medium'
        AND 0.4 ≤ confidence_score ≤ 0.7            ┘
      * everything else                              → 'low'
    """
    if direction == "flat":
        return "low"
    if any(s == "block" for s in risk_severities):
        return "low"
    warn_count = sum(1 for s in risk_severities if s == "warn")
    # FTFC is signed (-1.0 bearish to +1.0 bullish). For high conviction,
    # the sign must MATCH the trade direction — `abs(ftfc_score) >= 0.5`
    # would let a contradicting FTFC count as agreement (e.g. long with
    # ftfc_score=-0.8). Codex review on PR #351 caught this.
    ftfc_aligned = (
        (direction == "long" and ftfc_score >= 0.5)
        or (direction == "short" and ftfc_score <= -0.5)
    )
    if (
        analyst_agreement_count >= 4
        and ftfc_aligned
        and warn_count == 0
        and confidence_score >= 0.7
    ):
        return "high"
    if (
        analyst_agreement_count >= 2
        and warn_count <= 1
        and 0.4 <= confidence_score <= 0.7
    ):
        return "medium"
    return "low"


def _analyst_section_key(section: str) -> str:
    """Map prompt section name to bundle key. Catalysts live under
    `catalysts` (plural) in the bundle but the analyst prompt uses
    `catalyst` (role name) — keep them in sync."""
    return "catalysts" if section == "catalyst" else section


def _derive_key_levels(bundle: dict) -> dict[str, float]:
    """Populate key_levels deterministically from the context bundle.

    The PM agent frequently leaves ``key_levels`` empty. Rather than adding
    a new SQL query, synthesize the levels from data the bundle already
    carries: prior day high/low (strat section), 200 SMA and 20 EMA
    (market section), max-pain proxy (options section), and gamma flip /
    king / gate strikes (gamma section — issue #359).
    """
    levels: dict[str, float] = {}

    strat = bundle.get("strat", {}) or {}
    if strat.get("available"):
        # Full multi-timeframe level map populated by
        # summarize_strat_status → compute_previous_levels. Surface every
        # timeframe (day/week/month/quarter/year + mother-bar walk-back)
        # so users can audit which level the trade-planner classified
        # against. "Prev High/Low" alone hid PWH/PMH/PQH/PYH/effective_*
        # from the report even though the planner's blue-sky / extended /
        # normal regime classification depended on them.
        # Label map: short codes -> human-readable. Order matters only
        # for readability — Python 3.7+ dicts preserve insertion.
        _LEVEL_LABEL_MAP = (
            ("PDH", "Prev Day High"),
            ("PDL", "Prev Day Low"),
            ("PWH", "Prev Week High"),
            ("PWL", "Prev Week Low"),
            ("PMH", "Prev Month High"),
            ("PML", "Prev Month Low"),
            ("PQH", "Prev Quarter High"),
            ("PQL", "Prev Quarter Low"),
            ("PYH", "Prev Year High"),
            ("PYL", "Prev Year Low"),
            ("effective_PDH", "Effective PDH"),
            ("effective_PDL", "Effective PDL"),
        )
        strat_levels = strat.get("levels") or {}
        for code, label in _LEVEL_LABEL_MAP:
            v = strat_levels.get(code)
            if isinstance(v, (int, float)):
                levels[label] = float(v)

        # Legacy "Prev High/Low" kept for any consumer that still keys
        # off those exact labels (admin dashboard, divergence card).
        # When the full level map is present these are duplicates of
        # PDH/PDL but with the older naming.
        th = strat.get("trigger_high")
        tl = strat.get("trigger_low")
        if isinstance(th, (int, float)) and "Prev Day High" not in levels:
            levels["Prev High"] = float(th)
        if isinstance(tl, (int, float)) and "Prev Day Low" not in levels:
            levels["Prev Low"] = float(tl)

    market = bundle.get("market", {}) or {}
    if market.get("available"):
        sma_200 = market.get("sma_200")
        ema_20 = market.get("ema_20")
        if isinstance(sma_200, (int, float)):
            levels["SMA 200"] = float(sma_200)
        if isinstance(ema_20, (int, float)):
            levels["EMA 20"] = float(ema_20)

    options = bundle.get("options", {}) or {}
    if options.get("available"):
        mp = options.get("max_pain_strike_proxy")
        if isinstance(mp, (int, float)):
            levels["Max Pain"] = float(mp)

    # Gamma section — issue #359. The LLM thesis frequently mentions
    # "the gamma flip at $X" or "King strike at $Y"; without surfacing
    # those numbers in `key_levels`, PR-C's thesis_validator flagged
    # them as orphans (8/21 reports during 2026-05-09 validation).
    # Pull the flip price + the closest King strike + the closest Gates
    # above and below spot, when the gamma section ran successfully.
    gamma = bundle.get("gamma", {}) or {}
    if gamma.get("available"):
        # Track 5: namespace the gamma-derived key_level keys with
        # ' (EOD)' when the underlying chain is from a fallback path
        # (data_source ∈ {'eod_fallback','stale_fallback'} or missing).
        # The downstream trader / judge / risk-reviewer prompts read
        # these keys and emit prose like "target the Gamma Flip at
        # 502" — without the suffix they'd reference a stale Tuesday
        # close as if it were live. Bundles that predate Track 1
        # (no data_source field) default to suffixed, matching the
        # pre-Track-0 reality where every gamma read was EOD.
        # See docs/plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md Track 5.
        _ds = gamma.get("data_source")
        _gsfx = "" if _ds == "realtime" else " (EOD)"

        flip = gamma.get("flip")
        if isinstance(flip, (int, float)):
            levels[f"Gamma Flip{_gsfx}"] = float(flip)
        # Kings — `summary.kings` preserves classify_levels()/strike order,
        # not nearest-to-spot order, so `kings[0]` could surface the
        # lowest king while the gamma analyst is prompted to call out the
        # king above OR below spot. To prevent the validator from
        # orphaning a king reference, surface the closest king above spot
        # AND the closest king below spot when both exist (per Codex P2
        # review on PR #362). Keys are namespaced (above/below) so
        # downstream consumers can render both.
        spot_for_kings = gamma.get("spot")
        kings = gamma.get("kings") or []
        king_strikes: list[float] = []
        for k in kings:
            if not isinstance(k, dict):
                continue
            ks = k.get("strike")
            if isinstance(ks, (int, float)):
                king_strikes.append(float(ks))
        if king_strikes and isinstance(spot_for_kings, (int, float)):
            spot_f = float(spot_for_kings)
            below = [s for s in king_strikes if s < spot_f]
            above = [s for s in king_strikes if s > spot_f]
            if below:
                levels[f"Gamma King Below{_gsfx}"] = max(below)
            if above:
                levels[f"Gamma King Above{_gsfx}"] = min(above)
        elif king_strikes:
            # No spot to compare — keep legacy first-king behaviour so
            # callers aren't broken on bundles missing `gamma.spot`.
            levels[f"Gamma King{_gsfx}"] = king_strikes[0]
        # For the gates, surface the closest one above and below spot.
        # The dealer-positioning analyst typically calls these out in
        # prose; populating the structured field closes the loop.
        spot = gamma.get("spot")
        gates = gamma.get("gates") or []
        if isinstance(spot, (int, float)) and gates:
            above_strikes = sorted(
                float(g["strike"]) for g in gates
                if isinstance(g, dict)
                and isinstance(g.get("strike"), (int, float))
                and g["strike"] > spot
            )
            below_strikes = sorted(
                (
                    float(g["strike"]) for g in gates
                    if isinstance(g, dict)
                    and isinstance(g.get("strike"), (int, float))
                    and g["strike"] < spot
                ),
                reverse=True,
            )
            if above_strikes:
                levels[f"Gamma Gate Above{_gsfx}"] = above_strikes[0]
            if below_strikes:
                levels[f"Gamma Gate Below{_gsfx}"] = below_strikes[0]

    return levels


def _build_strat_snapshot(section: dict) -> StratSnapshot:
    if not section or not section.get("available"):
        return StratSnapshot(
            last_candle="1",
            in_force_combo=None,
            ftfc_score=0.0,
            ftfc_direction="mixed",
        )
    return StratSnapshot(
        last_candle=section.get("last_candle", "1") or "1",
        in_force_combo=section.get("in_force_combo"),
        ftfc_score=float(section.get("ftfc_score") or 0.0),
        ftfc_direction=section.get("ftfc_direction", "mixed") or "mixed",
        trigger_high=section.get("trigger_high"),
        trigger_low=section.get("trigger_low"),
    )


def _build_catalysts(section: dict) -> list[Catalyst]:
    if not section or not section.get("available"):
        return []
    out: list[Catalyst] = []
    for e in section.get("events", []) or []:
        try:
            sentiment = e.get("sentiment_score")
            out.append(
                Catalyst(
                    name=e["name"],
                    date=str(e["date"]),
                    impact=e.get("impact") or "medium",
                    kind=e.get("kind") or "economic",
                    sentiment_score=(
                        float(sentiment) if sentiment is not None else None
                    ),
                )
            )
        except Exception as exc:
            logger.debug("skipping malformed catalyst: %s", exc)
    return out


_DIRECTION_TO_OPTION: dict[str, str] = {"long": "CALL", "short": "PUT"}


def _build_signal_refs(
    section: dict,
    *,
    direction: Optional[str] = None,
) -> list[SignalRef]:
    """Convert the signals summarizer section to SignalRef rows.

    When ``direction`` is ``"long"`` or ``"short"``, only signals
    matching the corresponding option side (CALL / PUT respectively)
    are surfaced. ``"flat"`` and ``None`` keep the full set so flat
    reports still contextualize against the prior alert stream.
    """
    if not section or not section.get("available"):
        return []
    keep = _DIRECTION_TO_OPTION.get(direction or "")
    out: list[SignalRef] = []
    for r in section.get("recent", []) or []:
        try:
            row_direction = r["direction"]
            if keep is not None and row_direction != keep:
                continue
            out.append(
                SignalRef(
                    alert_ts=str(r["alert_ts"]),
                    direction=row_direction,
                    strength=r.get("strength") or "unknown",
                    score=float(r.get("score") or 0.0),
                )
            )
        except Exception:
            continue
    return out


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, date_type):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    return datetime.now(timezone.utc)
