"""Integration-style test for the end-to-end orchestrator.

Uses a mocked LLMClient factory so no provider SDK is touched, and
monkey-patches `lib.agents.summarizers._query` to return canned
DataFrames. Exercises:
- Full 11-node topology succeeds with valid outputs
- Model version snapshot lands in the report
- Cost is accumulated across every call
- Analyst failures are captured in failed_sections but the pipeline
  continues (audit fix #11)
- A `block` severity risk flag forces direction='flat' in the final
  report
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any, Type

import pandas as pd
import pytest
from pydantic import BaseModel

from lib.agents import orchestrator, summarizers
from lib.agents.llm_client import CompletionResult, LLMClient, Message, RouteSnapshot
from lib.agents.pricing import Usage
from lib.agents.schema import (
    ALL_ROLES,
    AnalystOutput,
    InsightReport,
    JudgeOutput,
    PortfolioManagerOutput,
    ResearcherOutput,
    RiskFlag,
    RiskPersonaOutput,
    TraderOutput,
)


# ---------------------------------------------------------------------------
# Mock LLM — returns pre-baked Pydantic instances per response_model
# ---------------------------------------------------------------------------


class _MockLLM(LLMClient):
    provider = "vertex"

    def __init__(
        self,
        *,
        risk_block: bool = False,
        failing_analyst_sections: frozenset[str] = frozenset(),
    ) -> None:
        self.calls: list[tuple[str, Type[BaseModel]]] = []
        self.risk_block = risk_block
        self.failing_analyst_sections = failing_analyst_sections
        self._risk_persona_turn = 0

    async def count_tokens(self, *, model: str, text: str) -> int:
        return len(text) // 4

    async def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[Message],
        response_model: Type[BaseModel],
        temperature: float = 0.7,
        max_output_tokens: int = 2048,
        enable_cache: bool = False,
    ) -> CompletionResult:
        self.calls.append((model, response_model))

        user_content = messages[-1].content if messages else ""

        if response_model is AnalystOutput:
            import json

            section = None
            try:
                payload = json.loads(user_content)
                section = payload.get("section")
            except Exception:
                section = None
            if section in self.failing_analyst_sections:
                raise RuntimeError(f"mock analyst {section} deliberately failed")
            parsed = AnalystOutput(
                section=(
                    section
                    if section in ("market", "strat", "options", "catalyst")
                    else "market"
                ),
                summary=f"Mock {section} summary.",
                bullets=["observation 1", "observation 2"],
                bias="bullish",
                confidence=0.7,
            )
        elif response_model is ResearcherOutput:
            stance = "bull" if "bull" in system.lower() else "bear"
            parsed = ResearcherOutput(
                stance=stance,
                case=f"The {stance} case with three specific points.",
                key_points=["point A", "point B", "point C"],
                rebuttal_to_opponent=None,
            )
        elif response_model is JudgeOutput:
            parsed = JudgeOutput(
                verdict="long",
                thesis="The bulls carry more evidence — FTFC + volume + trigger break.",
                weight_bull=0.65,
                weight_bear=0.35,
                rationale="Bullish weight of evidence from analyst tier.",
            )
        elif response_model is TraderOutput:
            from lib.agents.schema import EntryZone

            parsed = TraderOutput(
                direction="long",
                entry_zone=EntryZone(low=500.0, high=501.5),
                stop=497.5,
                targets=[504.0, 508.0],
                time_horizon="swing",
                invalidation="Close below 497.",
                confidence=0.72,
            )
        elif response_model is RiskPersonaOutput:
            # Cycle through the three personas
            persona_list = ["aggressive", "conservative", "neutral"]
            persona = persona_list[self._risk_persona_turn % 3]
            self._risk_persona_turn += 1
            severity = (
                "block" if (self.risk_block and persona == "conservative") else "info"
            )
            parsed = RiskPersonaOutput(
                persona=persona,  # type: ignore[arg-type]
                flags=[
                    RiskFlag(
                        persona=persona,  # type: ignore[arg-type]
                        severity=severity,  # type: ignore[arg-type]
                        message=f"Mock {persona} flag.",
                    )
                ],
                overall_severity=severity,  # type: ignore[arg-type]
            )
        elif response_model is PortfolioManagerOutput:
            from lib.agents.schema import EntryZone

            parsed = PortfolioManagerOutput(
                direction="long",
                conviction="medium",
                thesis="Bullish structure aligned with FTFC and strat trigger break.",
                entry_zone=EntryZone(low=500.0, high=501.5),
                stop=497.5,
                targets=[504.0, 508.0],
                invalidation="Close below 497.",
                time_horizon="swing",
                key_levels={"pivot": 500.0, "resistance": 504.0, "support": 497.5},
                bull_case="Trigger break + FTFC + rising volume.",
                bear_case="Tight stop, catalyst risk mid-window.",
                confidence_score=0.72,
            )
        else:
            raise NotImplementedError(f"mock missing for {response_model}")

        usage = Usage(
            provider="vertex",
            model="gemini-2.0-flash",
            input_tokens=1000,
            output_tokens=200,
        )
        return CompletionResult(parsed=parsed, usage=usage, raw_text="")


def _mock_factory_ctor(mock: _MockLLM):
    def factory(provider):
        return mock

    return factory


@pytest.fixture
def canned_bundle(monkeypatch):
    """Install summarizer fixtures matching what the orchestrator needs."""

    def fake_query(sql: str, params=None):
        if "market_data_daily" in sql:
            # Covers both summarize_market_context (1 row) and
            # summarize_strat_status (2 rows)
            return pd.DataFrame([
                {
                    "date": date(2026, 4, 15),
                    "open": 500.0, "high": 505.0, "low": 499.0, "close": 504.0,
                    "volume": 75_000_000, "sma_200": 480.0, "ema_20": 500.0,
                    "ema_50": 495.0, "rsi_14": 62.0, "macd": 0.8,
                    "macd_signal": 0.5, "macd_histogram": 0.3,
                    "bb_upper": 510.0, "bb_lower": 490.0, "bb_pct": 0.75,
                    "atr_14": 4.2, "rvol": 1.2, "volatility_20d": 0.15,
                    "price_vs_ema20": 0.008,
                    "strat_candle": "2U", "strat_combo": "2D-1-2U_reversal",
                    "strat_setup": True, "ftfc_score": 0.6,
                    "ftfc_direction": "bullish",
                },
                {
                    "date": date(2026, 4, 14),
                    "open": 498.0, "high": 502.5, "low": 497.0, "close": 500.0,
                    "volume": 60_000_000, "sma_200": 479.0, "ema_20": 499.0,
                    "ema_50": 494.0, "rsi_14": 58.0, "macd": 0.5,
                    "macd_signal": 0.4, "macd_histogram": 0.1,
                    "bb_upper": 508.0, "bb_lower": 488.0, "bb_pct": 0.60,
                    "atr_14": 4.0, "rvol": 1.0, "volatility_20d": 0.14,
                    "price_vs_ema20": 0.002,
                    "strat_candle": "1", "strat_combo": None,
                    "strat_setup": False, "ftfc_score": 0.3,
                    "ftfc_direction": "mixed",
                },
            ])
        if "etf_options_snapshots" in sql:
            return pd.DataFrame([
                {"option_type": "calls", "strike": 500, "volume": 10_000,
                 "open_interest": 50_000, "implied_volatility": 0.18, "delta": 0.5},
                {"option_type": "puts", "strike": 495, "volume": 8_000,
                 "open_interest": 40_000, "implied_volatility": 0.22, "delta": -0.45},
            ])
        if "signal_alerts" in sql:
            return pd.DataFrame([
                {"alert_ts": "2026-04-15 14:30:00", "direction": "CALL",
                 "strength_label": "strong", "total_score": 4.5},
            ])
        if "trades" in sql:
            return pd.DataFrame([
                {"return_pct": 2.0, "direction": "CALL", "exit_reason": "target"},
                {"return_pct": -1.0, "direction": "CALL", "exit_reason": "stop"},
            ])
        if "economic_events" in sql:
            return pd.DataFrame([
                {"event_date": "2026-04-18", "event_name": "FOMC", "importance": "high"},
            ])
        if "earnings_calendar" in sql:
            return pd.DataFrame()
        if "journal_entries" in sql:
            return pd.DataFrame()
        return pd.DataFrame()

    monkeypatch.setattr(summarizers, "_query", fake_query)


@pytest.fixture
def seven_role_snapshot() -> RouteSnapshot:
    return RouteSnapshot(routes={role: ("vertex", "gemini-2.0-flash") for role in ALL_ROLES})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_pipeline_end_to_end_green(canned_bundle, seven_role_snapshot):
    mock = _MockLLM()
    report = asyncio.run(
        orchestrator.run_insight_pipeline(
            "SPY",
            snapshot=seven_role_snapshot,
            llm_factory=_mock_factory_ctor(mock),
        )
    )
    assert isinstance(report, InsightReport)
    assert report.ticker == "SPY"
    assert report.direction == "long"
    assert report.conviction == "medium"
    assert report.run_cost_usd > 0
    assert report.run_latency_ms >= 0
    # Full topology = 4 analysts + 2 researchers + 1 judge + 1 trader + 3 risk + 1 PM = 12 calls
    # (But orchestrator counts 11 distinct node roles; the mock records every call.)
    assert len(mock.calls) == 12
    assert report.model_versions["trader"] == "vertex:gemini-2.0-flash"
    # No analyst failures in the happy path
    assert report.failed_sections == []


def test_pipeline_marks_failed_analysts(canned_bundle, seven_role_snapshot):
    mock = _MockLLM(failing_analyst_sections=frozenset({"options"}))
    report = asyncio.run(
        orchestrator.run_insight_pipeline(
            "SPY",
            snapshot=seven_role_snapshot,
            llm_factory=_mock_factory_ctor(mock),
        )
    )
    # Options analyst failed but the pipeline still returned a report
    assert "options" in report.failed_sections
    assert report.direction == "long"


def test_pipeline_blocks_direction_when_risk_blocks(canned_bundle, seven_role_snapshot):
    mock = _MockLLM(risk_block=True)
    report = asyncio.run(
        orchestrator.run_insight_pipeline(
            "SPY",
            snapshot=seven_role_snapshot,
            llm_factory=_mock_factory_ctor(mock),
        )
    )
    # PM said "long" but the conservative risk reviewer issued "block"
    assert report.direction == "flat"
    # The block flag is preserved in risk_flags
    assert any(f.severity == "block" for f in report.risk_flags)


def test_pipeline_aborts_when_all_analysts_fail(canned_bundle, seven_role_snapshot):
    mock = _MockLLM(
        failing_analyst_sections=frozenset({"market", "strat", "options", "catalyst"})
    )
    with pytest.raises(RuntimeError, match="all analyst nodes failed"):
        asyncio.run(
            orchestrator.run_insight_pipeline(
                "SPY",
                snapshot=seven_role_snapshot,
                llm_factory=_mock_factory_ctor(mock),
            )
        )


def test_pipeline_model_versions_snapshot_is_frozen(canned_bundle):
    """Verify that mid-run route changes do NOT leak into the report —
    the orchestrator must snapshot at start."""
    snapshot = RouteSnapshot(routes={
        role: ("vertex", "gemini-2.0-flash") for role in ALL_ROLES
    })
    mock = _MockLLM()

    # Mutate the snapshot AFTER pipeline submission won't happen in real
    # code, but to prove the orchestrator uses the passed snapshot and
    # never re-reads model_routing, we build a report and check that
    # the snapshot fields match regardless of anything else.
    report = asyncio.run(
        orchestrator.run_insight_pipeline(
            "SPY",
            snapshot=snapshot,
            llm_factory=_mock_factory_ctor(mock),
        )
    )
    for role in ALL_ROLES:
        assert report.model_versions[role] == "vertex:gemini-2.0-flash"
