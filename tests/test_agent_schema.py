"""Unit tests for lib.agents.schema Pydantic models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from lib.agents.schema import (
    ALL_ROLES,
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _minimal_strat() -> StratSnapshot:
    return StratSnapshot(
        last_candle="2U",
        in_force_combo="2D-1-2U_reversal",
        ftfc_score=0.6,
        ftfc_direction="bullish",
        trigger_high=505.0,
        trigger_low=498.0,
    )


def _minimal_report(**overrides) -> InsightReport:
    base = dict(
        ticker="SPY",
        as_of=datetime(2026, 4, 15, 14, 30, tzinfo=timezone.utc),
        direction="long",
        conviction="medium",
        thesis="Breakout above yesterday's high with supportive FTFC.",
        entry_zone=EntryZone(low=500.0, high=502.0),
        stop=497.0,
        targets=[506.0, 510.0],
        invalidation="Close below 497 on the 1-hour chart.",
        time_horizon="intraday",
        key_levels={"pivot": 500.0, "resistance": 506.0, "support": 497.0},
        strat_status=_minimal_strat(),
        catalysts=[],
        bull_case="Volume expansion + FTFC bullish.",
        bear_case="Stop is tight; a fakeout risks the whole R:R.",
        risk_flags=[],
        supporting_signals=[],
        similar_past_trades=[],
        confidence_score=0.72,
        failed_sections=[],
        model_versions={"analyst": "vertex:gemini-2.0-flash"},
        run_cost_usd=0.015,
        run_latency_ms=12_500,
    )
    base.update(overrides)
    return InsightReport(**base)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_all_roles_tuple_is_canonical():
    assert ALL_ROLES == (
        "analyst",
        "bull",
        "bear",
        "judge",
        "trader",
        "risk",
        "portfolio_manager",
    )


def test_minimal_insight_report_roundtrip():
    r = _minimal_report()
    data = r.model_dump()
    restored = InsightReport.model_validate(data)
    assert restored.ticker == "SPY"
    assert restored.entry_zone.low == 500.0
    assert restored.entry_zone.high == 502.0
    assert restored.strat_status.ftfc_direction == "bullish"


def test_entry_zone_is_structured_not_tuple():
    # Regression guard for audit fix #6 — no tuples in cross-provider schemas.
    fields = EntryZone.model_fields
    assert set(fields.keys()) == {"low", "high"}
    assert fields["low"].annotation is float
    assert fields["high"].annotation is float


def test_json_schema_has_no_prefix_items():
    """Pydantic emits `prefixItems` for tuple types (OpenAPI draft 2020).
    Cross-provider structured output is fragile with prefixItems; make sure
    no field resolved to a tuple."""

    def _walk(node):
        if isinstance(node, dict):
            assert "prefixItems" not in node, f"tuple type leaked into schema: {node}"
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(InsightReport.model_json_schema())


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_confidence_score_out_of_range_rejected():
    with pytest.raises(ValidationError):
        _minimal_report(confidence_score=1.5)
    with pytest.raises(ValidationError):
        _minimal_report(confidence_score=-0.1)


def test_invalid_direction_rejected():
    with pytest.raises(ValidationError):
        _minimal_report(direction="BUY")  # not in Literal


def test_invalid_ftfc_direction_rejected():
    bad_strat = dict(
        last_candle="1",
        in_force_combo=None,
        ftfc_score=0.0,
        ftfc_direction="sideways",  # not in Literal
    )
    with pytest.raises(ValidationError):
        StratSnapshot(**bad_strat)


def test_extra_fields_forbidden_on_report():
    # extra='forbid' catches accidental provider-injected fields.
    data = _minimal_report().model_dump()
    data["unexpected_field"] = True
    with pytest.raises(ValidationError):
        InsightReport.model_validate(data)


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


def test_catalyst_and_risk_flag():
    c = Catalyst(name="CPI", date="2026-04-22", impact="high", kind="economic")
    assert c.impact == "high"

    rf = RiskFlag(persona="conservative", severity="warn", message="tight stop")
    assert rf.severity == "warn"


def test_analyst_output_sections():
    for section in ("market", "strat", "options", "catalyst"):
        a = AnalystOutput(
            section=section,  # type: ignore[arg-type]
            summary="test",
            bullets=["a", "b"],
            bias="neutral",
            confidence=0.5,
        )
        assert a.section == section


def test_researcher_output_stance():
    r = ResearcherOutput(
        stance="bull",
        case="Breakout confirmed by volume.",
        key_points=["A", "B"],
    )
    assert r.stance == "bull"
    assert r.rebuttal_to_opponent is None


def test_judge_and_trader_output():
    j = JudgeOutput(
        verdict="long",
        thesis="Bulls carried the day.",
        weight_bull=0.65,
        weight_bear=0.35,
        rationale="FTFC + volume + OR high break.",
    )
    assert j.weight_bull + j.weight_bear == pytest.approx(1.0)

    t = TraderOutput(
        direction="long",
        entry_zone=EntryZone(low=500.0, high=501.0),
        stop=498.0,
        targets=[503.0, 505.0],
        time_horizon="swing",
        invalidation="Close below 497.",
        confidence=0.6,
    )
    assert t.direction == "long"


def test_risk_persona_output_aggregates_flags():
    r = RiskPersonaOutput(
        persona="aggressive",
        flags=[
            RiskFlag(persona="aggressive", severity="info", message="ok"),
            RiskFlag(persona="aggressive", severity="warn", message="tight"),
        ],
        overall_severity="warn",
    )
    assert len(r.flags) == 2
    assert r.overall_severity == "warn"


def test_portfolio_manager_output_shape():
    pm = PortfolioManagerOutput(
        direction="long",
        conviction="high",
        thesis="Aligned bullish setup.",
        entry_zone=EntryZone(low=500.0, high=501.0),
        stop=498.0,
        targets=[503.0, 505.0],
        invalidation="Close below 497.",
        time_horizon="intraday",
        bull_case="...",
        bear_case="...",
        confidence_score=0.8,
    )
    assert pm.conviction == "high"


def test_signal_ref_and_journal_ref():
    s = SignalRef(
        alert_ts="2026-04-15T14:30:00Z",
        direction="CALL",
        strength="strong",
        score=4.2,
    )
    assert s.direction == "CALL"

    j = JournalRef(
        id="00000000-0000-0000-0000-000000000001",
        ticker="SPY",
        direction="CALL",
        return_pct=2.4,
        cosine_distance=0.12,
    )
    assert j.cosine_distance == pytest.approx(0.12)
