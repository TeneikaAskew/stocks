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
import time
from datetime import date as date_type, datetime, timezone
from typing import Any, Callable, Optional, Type

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

    def add(self, usage: Usage) -> None:
        self.calls += 1
        try:
            self.total_cost += usage.cost_usd()
        except KeyError:
            logger.warning(
                "no price table entry for %s:%s — cost not tracked",
                usage.provider,
                usage.model,
            )


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
    tracker.add(result.usage)
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
                k: bundle.get(k, {}).get("available") for k in ("market", "strat", "options", "catalysts", "sentiment")
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
    analyst_sections = ("market", "strat", "options", "catalyst", "sentiment")
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
    for section, result in zip(analyst_sections, raw_analyst_results):
        if isinstance(result, Exception):
            logger.warning("analyst %s failed: %s", section, result)
            if section not in failed_sections:
                failed_sections.append(section)
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
    signals_refs = _build_signal_refs(bundle.get("signals", {}))

    # Flatten all risk flags from all personas
    all_flags: list[RiskFlag] = []
    for r in risk_outputs:
        all_flags.extend(r.flags)

    similar: list[JournalRef] = []
    if query_embedding:
        try:
            similar = retrieve_similar_journal(ticker, query_embedding, k=5)
        except Exception as e:
            logger.warning("similar-journal lookup failed: %s", e)

    # Respect any explicit block from the risk debate
    blocked = any(f.severity == "block" for f in all_flags)
    direction = "flat" if blocked else pm.direction

    report = InsightReport(
        ticker=ticker.upper(),
        as_of=datetime.now(timezone.utc) if as_of is None else _as_datetime(as_of),
        direction=direction,
        conviction=pm.conviction,
        thesis=pm.thesis,
        entry_zone=pm.entry_zone,
        stop=pm.stop,
        targets=pm.targets,
        invalidation=pm.invalidation,
        time_horizon=pm.time_horizon,
        key_levels=pm.key_levels,
        strat_status=strat_status,
        catalysts=catalysts,
        bull_case=pm.bull_case,
        bear_case=pm.bear_case,
        risk_flags=all_flags,
        supporting_signals=signals_refs,
        similar_past_trades=similar,
        confidence_score=pm.confidence_score,
        failed_sections=failed_sections,
        model_versions=snapshot.model_versions(),
        run_cost_usd=round(tracker.total_cost, 6),
        run_latency_ms=int((time.monotonic() - start) * 1000),
    )
    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _analyst_section_key(section: str) -> str:
    """Map prompt section name to bundle key. Catalysts live under
    `catalysts` (plural) in the bundle but the analyst prompt uses
    `catalyst` (role name) — keep them in sync."""
    return "catalysts" if section == "catalyst" else section


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
            out.append(
                Catalyst(
                    name=e["name"],
                    date=str(e["date"]),
                    impact=e.get("impact") or "medium",
                    kind=e.get("kind") or "economic",
                )
            )
        except Exception as exc:
            logger.debug("skipping malformed catalyst: %s", exc)
    return out


def _build_signal_refs(section: dict) -> list[SignalRef]:
    if not section or not section.get("available"):
        return []
    out: list[SignalRef] = []
    for r in section.get("recent", []) or []:
        try:
            out.append(
                SignalRef(
                    alert_ts=str(r["alert_ts"]),
                    direction=r["direction"],
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
