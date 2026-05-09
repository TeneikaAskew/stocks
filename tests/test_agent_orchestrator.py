"""Integration-style test for the end-to-end orchestrator.

Uses a mocked LLMClient factory so no provider SDK is touched, and
monkey-patches `lib.agents.summarizers._query` to return canned
DataFrames. Exercises:
- Full 14-call topology succeeds with valid outputs (6 analysts +
  2 researchers + 1 judge + 1 trader + 3 risk personas + 1 PM)
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
                    if section in (
                        "market", "strat", "options", "gamma",
                        "catalyst", "sentiment",
                    )
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
        # Cross-ticker analog matcher pulls every other ticker; return
        # empty so the same-ticker matches are sufficient and we don't
        # have to fake a multi-ticker fixture.
        if "ticker <> :ticker" in sql:
            return pd.DataFrame()
        if "market_data_daily" in sql:
            # The orchestrator now has three consumers of market_data_daily
            # with different SQL shapes. Dispatch by sniffing the query so
            # each gets a row layout it can actually use.
            #
            #   - summarize_backtest_metrics (analog matcher) needs ≥60
            #     rows in ASCENDING date order (it does iloc[-1] for "today").
            #   - summarize_strat_status uses ORDER BY date DESC LIMIT 2.
            #   - summarize_market_context uses ORDER BY date DESC LIMIT 1.
            recent = [
                {
                    "date": date(2026, 4, 15),
                    "open": 500.0, "high": 505.0, "low": 499.0, "close": 504.0,
                    "volume": 75_000_000, "sma_200": 480.0, "ema_20": 500.0,
                    "ema_50": 495.0, "rsi_14": 62.0, "macd": 0.8,
                    "macd_signal": 0.5, "macd_histogram": 0.3,
                    "bb_upper": 510.0, "bb_lower": 490.0, "bb_pct": 0.75,
                    "atr_14": 4.2, "rvol": 1.2, "volatility_20d": 0.15,
                    "price_vs_ema20": 0.008,
                    "strat_candle": "2U", "strat_combo": "212_bull_reversal",
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
            ]
            if "ORDER BY date ASC" in sql:
                # Analog backtest: synthesize ~420 weekday bars in a
                # mean-reverting band so close_vs_sma200_pct stays
                # close to zero across the series and the matcher
                # always finds historical matches. Need >=220 rows so
                # sma_200 has non-NaN values inside the iloc[:-20]
                # history window.
                #
                # We don't override the last bar to match strat's
                # "today" — strat uses a separate ORDER BY date DESC
                # LIMIT 2 SQL shape, and an out-of-distribution
                # override here would put close_vs_sma200_pct out of
                # match range against the rest of the series.
                import math
                from datetime import timedelta
                rows = []
                d = date(2024, 1, 1)
                anchor = 500.0
                for i in range(420):
                    while d.weekday() >= 5:
                        d = d + timedelta(days=1)
                    open_px = anchor * (1 + 0.005 * math.sin(i * 0.13))
                    close_px = anchor * (1 + 0.005 * math.sin(i * 0.13 + 0.5))
                    high_px = max(open_px, close_px) * 1.002
                    low_px = min(open_px, close_px) * 0.998
                    rows.append({
                        "date": d, "open": open_px, "high": high_px,
                        "low": low_px, "close": close_px,
                        "volume": 50_000_000,
                    })
                    d = d + timedelta(days=1)
                return pd.DataFrame(rows)
            return pd.DataFrame(recent)
        if "FROM news_sentiment" in sql:
            # summarize_news_sentiment (sentiment summary) and
            # signal-style queries; either consumer is happy with a
            # short list of bullish-leaning recent articles.
            return pd.DataFrame([
                {"published_ts": "2026-04-15T13:30:00Z",
                 "title": "Bullish breakout above prior-day high",
                 "topics": ["earnings"],
                 "overall_sentiment_score": 0.4,
                 "overall_sentiment_label": "Bullish",
                 "relevance_score": 0.85,
                 "sentiment_score": 0.4},
                {"published_ts": "2026-04-15T11:10:00Z",
                 "title": "Volume surge on supportive catalyst flow",
                 "topics": ["mergers_and_acquisitions"],
                 "overall_sentiment_score": 0.3,
                 "overall_sentiment_label": "Somewhat-Bullish",
                 "relevance_score": 0.78,
                 "sentiment_score": 0.3},
            ])
        if "etf_options_snapshots" in sql:
            # The orchestrator now has two consumers of etf_options_snapshots
            # with different SQL shapes — both filter by data_source =
            # 'alphavantage' so we discriminate by the SELECT columns:
            #   - summarize_options_flow selects volume/OI/IV/delta.
            #   - summarize_gamma_levels selects expiration/gamma/vega/bid/
            #     ask/mark/last_price (no `volume` column).
            # Dispatch on the gamma-only column "gamma" so each consumer
            # gets the columns it needs and the gamma summarizer's
            # `min(expiration)` doesn't blow up.
            if "gamma, vega" in sql:
                from datetime import timedelta
                near_exp = (date(2026, 4, 15) + timedelta(days=14)).strftime("%Y-%m-%d")
                far_exp = (date(2026, 4, 15) + timedelta(days=45)).strftime("%Y-%m-%d")
                rows = []
                for strike in (490, 495, 500, 505, 510):
                    for opt_type in ("calls", "puts"):
                        for exp in (near_exp, far_exp):
                            rows.append({
                                "option_type": opt_type,
                                "strike": float(strike),
                                "expiration": exp,
                                "open_interest": 10_000 if opt_type == "calls" else 8_000,
                                "gamma": 0.02,
                                "vega": 0.15,
                                "delta": 0.5 if opt_type == "calls" else -0.45,
                                "bid": 1.10, "ask": 1.20, "mark": 1.15,
                                "last_price": 1.15,
                            })
                return pd.DataFrame(rows)
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

    # `summarize_strat_status` calls `lib.strat.compute_strat_status`, which
    # loads bars via `DataLoader.load_daily` rather than the `_query` shim
    # patched above. Without an override the real loader returns no bars,
    # the strat section reports `available: False`, and the orchestrator
    # marks 'strat' as a failed_section — making the green-path test red.
    # Inject a canned snapshot that matches the OHLCV fixture above so the
    # strat block looks like a normal bullish 2U trigger day.
    def fake_compute_strat_status(ticker, *args, **kwargs):
        return {
            "available": True,
            "ticker": ticker.upper(),
            "date": "2026-04-15",
            "last_candle": "2U",
            "in_force_combo": "212_bull_reversal",
            "strat_setup": True,
            "ftfc_score": 0.6,
            "ftfc_direction": "bullish",
            "trigger_high": 502.5,
            "trigger_low": 497.0,
        }

    import lib.strat as _lib_strat
    monkeypatch.setattr(_lib_strat, "compute_strat_status", fake_compute_strat_status)

    # Audit 2026-05-08 G.P2.12: orchestrator now auto-embeds the bundle
    # for reflection-memory retrieval. Stub the Vertex call with a
    # zero-vector so tests don't hit real Vertex (~0.4s per call ×
    # 26 tests = 10s of unnecessary network I/O).
    async def fake_embed(text):
        return [0.0] * 768

    import lib.agents.embeddings as _emb
    monkeypatch.setattr(_emb, "embed_text", fake_embed)


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
    # #349 deterministic conviction: canned bundle has 6 bullish analysts
    # (≥4), FTFC 0.6 (≥0.5), confidence 0.72 (≥0.7), no warn/block →
    # calibrates to 'high' regardless of what the LLM mock returned.
    assert report.conviction == "high"
    assert report.run_cost_usd > 0
    assert report.run_latency_ms >= 0
    # Full topology = 6 analysts (market, strat, options, gamma,
    # catalyst, sentiment) + 2 researchers + 1 judge + 1 trader +
    # 3 risk personas + 1 PM = 14 calls. The gamma analyst was added
    # to align with `lib/gamma.py` as the single source of truth for
    # gamma analytics (per CLAUDE.md "Architectural rules").
    assert len(mock.calls) == 14
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


@pytest.mark.parametrize("failing_section", [
    "gamma",       # Added in PR #80; lib/gamma.py SoT consolidation
    "sentiment",   # Added in PR #80; news_sentiment topic-based scoring
    "catalyst",
    "strat",
    "market",
])
def test_pipeline_isolates_individual_analyst_failures(
    canned_bundle, seven_role_snapshot, failing_section
):
    """A single analyst section raising must not abort the pipeline.
    The orchestrator records the failure in `failed_sections` and the
    downstream tier (researchers, judge, trader, risk, PM) continues
    to synthesize from whichever analysts succeeded.

    Covers each of the 6 analyst sections individually so we don't
    silently regress when adding a new section."""
    mock = _MockLLM(failing_analyst_sections=frozenset({failing_section}))
    report = asyncio.run(
        orchestrator.run_insight_pipeline(
            "SPY",
            snapshot=seven_role_snapshot,
            llm_factory=_mock_factory_ctor(mock),
        )
    )
    # The failed section is recorded
    assert failing_section in report.failed_sections
    # Pipeline still produced a directional report (didn't abort)
    assert report.direction in ("long", "short", "flat")
    # All 14 LLM calls are still attempted (the mock raises *during*
    # the call, after `self.calls.append(...)`); the orchestrator
    # records the failed section but downstream nodes proceed.
    assert len(mock.calls) == 14
    # Cost still accumulates from the surviving 13 successful responses
    assert report.run_cost_usd > 0


# ──────────────────────────────────────────────────────────────────────
# Helper-builder unit tests — cover the bundle-payload extraction
# helpers directly so wrong AI prompts don't slip through with no
# error surface.
# ──────────────────────────────────────────────────────────────────────


def test_derive_key_levels_extracts_strat_market_options():
    from lib.agents.orchestrator import _derive_key_levels

    bundle = {
        "strat":   {"available": True, "trigger_high": 510.0, "trigger_low": 495.0},
        "market":  {"available": True, "sma_200": 480.0, "ema_20": 500.0},
        "options": {"available": True, "max_pain_strike_proxy": 505.0},
    }
    levels = _derive_key_levels(bundle)
    assert levels == {
        "Prev High": 510.0, "Prev Low": 495.0,
        "SMA 200": 480.0, "EMA 20": 500.0,
        "Max Pain": 505.0,
    }


def test_derive_key_levels_skips_unavailable_sections():
    from lib.agents.orchestrator import _derive_key_levels

    # Only market is available — strat/options are dropped without error
    bundle = {
        "strat":   {"available": False, "trigger_high": 999, "trigger_low": 0},
        "market":  {"available": True, "sma_200": 480.0, "ema_20": 500.0},
        "options": None,  # missing entirely
    }
    levels = _derive_key_levels(bundle)
    assert levels == {"SMA 200": 480.0, "EMA 20": 500.0}


def test_derive_key_levels_drops_non_numeric_values():
    """A summarizer that emits a string for `trigger_high` (because of
    a SQL coercion bug) must NOT be included — wrong levels would feed
    the AI prompt silently."""
    from lib.agents.orchestrator import _derive_key_levels

    bundle = {
        "strat": {"available": True,
                  "trigger_high": "510.0",  # str, not number
                  "trigger_low": None},
    }
    assert _derive_key_levels(bundle) == {}


def test_derive_key_levels_empty_bundle_returns_empty_dict():
    from lib.agents.orchestrator import _derive_key_levels

    assert _derive_key_levels({}) == {}


def test_build_strat_snapshot_default_when_unavailable():
    from lib.agents.orchestrator import _build_strat_snapshot

    snap = _build_strat_snapshot({"available": False})
    assert snap.last_candle == "1"
    assert snap.in_force_combo is None
    assert snap.ftfc_score == 0.0
    assert snap.ftfc_direction == "mixed"


def test_build_strat_snapshot_populates_from_section():
    from lib.agents.orchestrator import _build_strat_snapshot

    snap = _build_strat_snapshot({
        "available": True,
        "last_candle": "2U",
        "in_force_combo": "212_bull_reversal",
        "ftfc_score": 0.75,
        "ftfc_direction": "bullish",
        "trigger_high": 510.0,
        "trigger_low": 500.0,
    })
    assert snap.last_candle == "2U"
    assert snap.in_force_combo == "212_bull_reversal"
    assert snap.ftfc_score == 0.75
    assert snap.ftfc_direction == "bullish"
    assert snap.trigger_high == 510.0
    assert snap.trigger_low == 500.0


def test_build_strat_snapshot_coerces_falsy_strings_to_defaults():
    """The summarizer can emit `last_candle=''` when classification
    fails. Don't propagate a blank — fall back to '1' (mixed)."""
    from lib.agents.orchestrator import _build_strat_snapshot

    snap = _build_strat_snapshot({
        "available": True,
        "last_candle": "",
        "ftfc_score": None,
        "ftfc_direction": None,
    })
    assert snap.last_candle == "1"
    assert snap.ftfc_score == 0.0
    assert snap.ftfc_direction == "mixed"


def test_build_catalysts_filters_malformed_events():
    """A catalyst row missing `name` or `date` must be dropped without
    aborting the whole list (raised inside the loop, caught by `except`)."""
    from lib.agents.orchestrator import _build_catalysts

    out = _build_catalysts({
        "available": True,
        "events": [
            {"name": "FOMC", "date": "2026-04-30", "impact": "high",
             "kind": "economic"},
            {"name": "AAPL Earnings"},  # missing date — dropped
            {"date": "2026-05-01"},      # missing name — dropped
            {"name": "GDP Q1", "date": "2026-05-15"},  # impact/kind defaults
        ],
    })
    names = [c.name for c in out]
    assert names == ["FOMC", "GDP Q1"]
    # Defaults applied to the second
    assert out[1].impact == "medium"
    assert out[1].kind == "economic"


def test_build_catalysts_unavailable_returns_empty():
    from lib.agents.orchestrator import _build_catalysts

    assert _build_catalysts({"available": False}) == []
    assert _build_catalysts({}) == []


def test_build_signal_refs_skips_malformed_rows():
    """A signal row missing `alert_ts` or `direction` is dropped silently
    — the rest of the list still surfaces."""
    from lib.agents.orchestrator import _build_signal_refs

    out = _build_signal_refs({
        "available": True,
        "recent": [
            {"alert_ts": "2026-04-25 14:30:00", "direction": "CALL",
             "strength": "strong", "score": 4.5},
            {"direction": "PUT"},  # no alert_ts — dropped
            {"alert_ts": "x", "direction": "CALL", "score": "not-a-number"},
        ],
    })
    # Last row drops because float('not-a-number') raises
    assert len(out) == 1
    assert out[0].direction == "CALL"


def test_build_signal_refs_filters_by_long_direction():
    """Audit 2026-05-08 G.P2.14: a long report should only cite CALL alerts."""
    from lib.agents.orchestrator import _build_signal_refs

    section = {
        "available": True,
        "recent": [
            {"alert_ts": "2026-05-07 14:00", "direction": "CALL",
             "strength": "strong", "score": 4.0},
            {"alert_ts": "2026-05-07 13:00", "direction": "PUT",
             "strength": "moderate", "score": 3.0},
            {"alert_ts": "2026-05-07 12:00", "direction": "PUT",
             "strength": "strong", "score": 4.5},
            {"alert_ts": "2026-05-07 11:00", "direction": "CALL",
             "strength": "weak", "score": 2.0},
        ],
    }
    out = _build_signal_refs(section, direction="long")
    assert len(out) == 2
    assert all(r.direction == "CALL" for r in out)


def test_build_signal_refs_filters_by_short_direction():
    from lib.agents.orchestrator import _build_signal_refs

    section = {
        "available": True,
        "recent": [
            {"alert_ts": "2026-05-07 14:00", "direction": "CALL",
             "strength": "strong", "score": 4.0},
            {"alert_ts": "2026-05-07 13:00", "direction": "PUT",
             "strength": "moderate", "score": 3.0},
        ],
    }
    out = _build_signal_refs(section, direction="short")
    assert len(out) == 1
    assert out[0].direction == "PUT"


def test_build_signal_refs_flat_or_none_keeps_all_directions():
    """Flat trades retain the unfiltered alert stream so the report still
    shows what the market did. Same for direction=None (callers that
    haven't migrated)."""
    from lib.agents.orchestrator import _build_signal_refs

    section = {
        "available": True,
        "recent": [
            {"alert_ts": "2026-05-07 14:00", "direction": "CALL",
             "strength": "strong", "score": 4.0},
            {"alert_ts": "2026-05-07 13:00", "direction": "PUT",
             "strength": "moderate", "score": 3.0},
        ],
    }
    assert len(_build_signal_refs(section, direction="flat")) == 2
    assert len(_build_signal_refs(section)) == 2


def test_pipeline_isolates_multiple_partial_failures(
    canned_bundle, seven_role_snapshot
):
    """Two analysts failing simultaneously — pipeline still proceeds
    as long as at least one analyst returned (the abort gate at
    `lib/agents/orchestrator.py:327` only fires on full collapse)."""
    mock = _MockLLM(
        failing_analyst_sections=frozenset({"gamma", "sentiment"})
    )
    report = asyncio.run(
        orchestrator.run_insight_pipeline(
            "SPY",
            snapshot=seven_role_snapshot,
            llm_factory=_mock_factory_ctor(mock),
        )
    )
    assert {"gamma", "sentiment"}.issubset(set(report.failed_sections))
    assert report.direction in ("long", "short", "flat")


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
    # Orchestrator runs six analyst sections — market, strat, options,
    # gamma, catalyst, sentiment. All six have to fail to trigger the
    # abort (otherwise downstream researchers can still synthesize from
    # whichever analyst returned).
    mock = _MockLLM(
        failing_analyst_sections=frozenset(
            {"market", "strat", "options", "gamma", "catalyst", "sentiment"}
        )
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


def test_pipeline_records_per_role_cost(canned_bundle, seven_role_snapshot):
    """Audit 2026-05-08 G.P3.2: per_role_cost should split spend by role,
    with analyst and risk subdivided (e.g. 'analyst:market', 'risk:neutral').
    Sum across the dict must equal run_cost_usd within rounding."""
    mock = _MockLLM()
    report = asyncio.run(
        orchestrator.run_insight_pipeline(
            "SPY",
            snapshot=seven_role_snapshot,
            llm_factory=_mock_factory_ctor(mock),
        )
    )
    # All 6 analyst sections + 3 risk personas + 5 single-role nodes (bull,
    # bear, judge, trader, portfolio_manager) = 14 distinct keys in the
    # happy path.
    expected_analyst_keys = {
        "analyst:market", "analyst:strat", "analyst:options",
        "analyst:gamma", "analyst:catalyst", "analyst:sentiment",
    }
    expected_risk_keys = {
        "risk:aggressive", "risk:conservative", "risk:neutral",
    }
    expected_single = {"bull", "bear", "judge", "trader", "portfolio_manager"}
    expected = expected_analyst_keys | expected_risk_keys | expected_single
    assert set(report.per_role_cost.keys()) == expected
    assert all(v > 0 for v in report.per_role_cost.values())
    assert abs(sum(report.per_role_cost.values()) - report.run_cost_usd) < 1e-4


def test_pipeline_filters_supporting_signals_by_direction(
    canned_bundle, seven_role_snapshot
):
    """Audit 2026-05-08 G.P2.14: supporting_signals must not contradict
    the report direction. The canned signal_alerts fixture returns a
    single CALL row, so a long report keeps it and a short/flat report
    on the same data would drop it (covered by unit-level tests above)."""
    mock = _MockLLM()
    report = asyncio.run(
        orchestrator.run_insight_pipeline(
            "SPY",
            snapshot=seven_role_snapshot,
            llm_factory=_mock_factory_ctor(mock),
        )
    )
    # PM mock returns long; the only stubbed alert is direction=CALL.
    assert report.direction == "long"
    assert all(s.direction == "CALL" for s in report.supporting_signals)


# ─── Audit 2026-05-08 G.P1.9 — thesis-vs-targets consistency validator ───


def test_validate_thesis_flags_orphan_target_levels():
    """The QQQ 5/7 reproduction: thesis names targets 677.8/691.09/704.38
    but `targets=[]`. Validator should return all three as orphans."""
    from lib.agents.orchestrator import _validate_thesis_consistency
    from lib.agents.schema import EntryZone

    thesis = (
        "The bull case outweighs the bear case, supported by the "
        "prevailing uptrend and positive gamma regime. A long position "
        "is warranted, targeting 677.8, 691.09 and 704.38, while being "
        "mindful of the 618.15 gamma flip level."
    )
    orphans = _validate_thesis_consistency(
        thesis,
        ticker="QQQ",
        entry_zone=EntryZone(low=500.0, high=501.5),
        stop=497.5,
        targets=[],  # planner overrode to empty
        key_levels={"gamma_flip": 618.15},  # only gamma flip is structured
        invalidation="Close below 651.22",  # 651.22 NOT in thesis
    )
    # 677.8, 691.09, 704.38 should all be flagged. 618.15 should match
    # the structured key_level. 651.22 from invalidation isn't in thesis
    # so doesn't count as orphan.
    assert 677.8 in orphans
    assert 691.09 in orphans
    assert 704.38 in orphans
    assert 618.15 not in orphans  # structured match


def test_validate_thesis_clean_when_levels_match_structured():
    """Happy path — thesis numbers all map to structured fields."""
    from lib.agents.orchestrator import _validate_thesis_consistency
    from lib.agents.schema import EntryZone

    thesis = (
        "Strong setup. Enter on a break above 100.50 with stop at "
        "98.00 and first target at 102.00. Gamma flip at 99.50 "
        "anchors the support."
    )
    orphans = _validate_thesis_consistency(
        thesis,
        ticker="X",
        entry_zone=EntryZone(low=100.50, high=100.75),
        stop=98.00,
        targets=[102.00, 104.00],
        key_levels={"gamma_flip": 99.50},
        invalidation="Below 98.00",
    )
    assert orphans == []


def test_validate_thesis_tolerates_minor_rounding():
    """Audit-realistic: thesis says 'around 278.13' and the key_level
    is 278.135 (LLM rounded). 0.5% tolerance should match."""
    from lib.agents.orchestrator import _validate_thesis_consistency
    from lib.agents.schema import EntryZone

    thesis = "Trigger above 278.13 unlocks PWH continuation."
    orphans = _validate_thesis_consistency(
        thesis,
        ticker="IWM",
        entry_zone=EntryZone(low=270.0, high=271.0),
        stop=265.0,
        targets=[280.0],
        key_levels={"PWH": 278.135},
        invalidation="Below 265",
    )
    assert orphans == []


def test_validate_thesis_skips_non_price_numerics():
    """Numbers like '200 SMA' or 'RSI 70' aren't prices — they have no
    decimal so the regex doesn't match. Validator should not flag them."""
    from lib.agents.orchestrator import _validate_thesis_consistency
    from lib.agents.schema import EntryZone

    thesis = (
        "Setup is bullish above the 200 SMA with RSI 70 holding strong "
        "and ATR(14) at expanded levels."
    )
    orphans = _validate_thesis_consistency(
        thesis,
        ticker="X",
        entry_zone=EntryZone(low=100.0, high=101.0),
        stop=98.0,
        targets=[102.0],
        key_levels={},
        invalidation="X",
    )
    # 200 (no decimal), 70 (no decimal), 14 (no decimal) — none match the regex
    assert orphans == []


def test_validate_thesis_handles_dollar_prefix():
    """Thesis with '$278.13' format should be parsed the same way."""
    from lib.agents.orchestrator import _validate_thesis_consistency
    from lib.agents.schema import EntryZone

    thesis = "Enter above $278.13 targeting $300.00."
    orphans = _validate_thesis_consistency(
        thesis,
        ticker="IWM",
        entry_zone=EntryZone(low=278.13, high=278.50),
        stop=275.0,
        targets=[280.0],  # 300.00 NOT in targets
        key_levels={},
        invalidation="Below 275",
    )
    assert 300.00 in orphans
    assert 278.13 not in orphans  # entry_zone match


def test_validate_thesis_empty_returns_empty():
    """No thesis → no orphans. Defensive."""
    from lib.agents.orchestrator import _validate_thesis_consistency
    from lib.agents.schema import EntryZone

    assert _validate_thesis_consistency(
        "", ticker="X",
        entry_zone=EntryZone(low=1.0, high=2.0),
        stop=0.5, targets=[3.0], key_levels={}, invalidation="x",
    ) == []
# ─── Audit 2026-05-08 G.P2.12 — reflection memory wiring ─────────────


def test_build_embedding_query_text_includes_key_setup_fields():
    """The auto-embed query text should capture ticker + strat candle +
    combo + FTFC + regime + gap + vol tag + 200-SMA position. Same
    fields that semantically determine 'is this trade similar'."""
    from lib.agents.orchestrator import _build_embedding_query_text

    bundle = {
        "ticker": "spy",  # lowercased input → uppercased output
        "strat": {
            "available": True,
            "last_candle": "2U",
            "in_force_combo": "212_bull_reversal",
            "ftfc_direction": "bullish",
        },
        "market": {
            "available": True,
            "regime": "trending_up",
            "vol_tag": "normal",
            "above_sma_200": True,
            "premarket": {"gap_pct": 0.31},
        },
    }
    text = _build_embedding_query_text("spy", bundle)
    assert "SPY" in text
    assert "2U" in text
    assert "212_bull_reversal" in text
    assert "bullish" in text
    assert "trending_up" in text
    assert "+0.31%" in text
    assert "normal" in text
    assert "above 200-SMA" in text


def test_build_embedding_query_text_handles_missing_fields():
    """Defensive: if strat or market sections are unavailable, the text
    is just the ticker — embedding still works, retrieval just has
    less signal to work with."""
    from lib.agents.orchestrator import _build_embedding_query_text

    bundle = {"ticker": "X", "strat": {"available": False}, "market": {}}
    assert _build_embedding_query_text("X", bundle) == "X"


def test_pipeline_auto_embeds_when_query_embedding_omitted(
    canned_bundle, seven_role_snapshot, monkeypatch
):
    """Audit G.P2.12: the orchestrator should call `embed_text` on the
    bundle summary when the caller doesn't pre-supply an embedding.
    Replaces the dormant query_embedding=None hardcoded path."""
    embed_calls: list[str] = []

    async def spy_embed(text):
        embed_calls.append(text)
        return [0.1] * 768

    import lib.agents.embeddings as _emb
    monkeypatch.setattr(_emb, "embed_text", spy_embed)

    mock = _MockLLM()
    asyncio.run(
        orchestrator.run_insight_pipeline(
            "SPY",
            snapshot=seven_role_snapshot,
            llm_factory=_mock_factory_ctor(mock),
        )
    )
    assert len(embed_calls) == 1
    assert "SPY" in embed_calls[0]


def test_pipeline_uses_explicit_embedding_when_caller_supplies(
    canned_bundle, seven_role_snapshot, monkeypatch
):
    """Caller-injected embedding (replay / tests) bypasses the auto-embed
    Vertex call so deterministic offline replay stays deterministic."""
    embed_calls: list[str] = []

    async def boom_embed(text):
        embed_calls.append(text)
        raise RuntimeError("auto-embed should not have been called")

    import lib.agents.embeddings as _emb
    monkeypatch.setattr(_emb, "embed_text", boom_embed)

    mock = _MockLLM()
    asyncio.run(
        orchestrator.run_insight_pipeline(
            "SPY",
            snapshot=seven_role_snapshot,
            llm_factory=_mock_factory_ctor(mock),
            query_embedding=[0.2] * 768,
        )
    )
    assert embed_calls == []  # auto-embed was skipped


def test_pipeline_degrades_when_embedding_fails(
    canned_bundle, seven_role_snapshot, monkeypatch
):
    """Vertex creds missing / network blip → embed raises → reflection
    memory is skipped, but the rest of the report still ships. Audit
    G.P2.12: graceful degradation of opt-in features."""
    async def boom_embed(text):
        raise RuntimeError("Vertex unreachable")

    import lib.agents.embeddings as _emb
    monkeypatch.setattr(_emb, "embed_text", boom_embed)

    mock = _MockLLM()
    report = asyncio.run(
        orchestrator.run_insight_pipeline(
            "SPY",
            snapshot=seven_role_snapshot,
            llm_factory=_mock_factory_ctor(mock),
        )
    )
    # Report still produced; similar_past_trades is just empty
    assert isinstance(report, InsightReport)
    assert report.similar_past_trades == []


# ─── Audit follow-up #349 — deterministic conviction calibration ─────


def test_calibrate_conviction_flat_is_low():
    from lib.agents.orchestrator import _calibrate_conviction
    assert _calibrate_conviction(
        direction="flat", confidence_score=0.9,
        analyst_agreement_count=6, ftfc_score=1.0,
        risk_severities=["info"],
    ) == "low"


def test_calibrate_conviction_block_is_low():
    from lib.agents.orchestrator import _calibrate_conviction
    assert _calibrate_conviction(
        direction="long", confidence_score=0.9,
        analyst_agreement_count=6, ftfc_score=1.0,
        risk_severities=["info", "block"],
    ) == "low"


def test_calibrate_conviction_high_path():
    from lib.agents.orchestrator import _calibrate_conviction
    # All four conditions cleared
    assert _calibrate_conviction(
        direction="long", confidence_score=0.75,
        analyst_agreement_count=4, ftfc_score=0.5,
        risk_severities=["info", "info", "info"],
    ) == "high"


def test_calibrate_conviction_high_blocked_by_warn():
    from lib.agents.orchestrator import _calibrate_conviction
    # One warn flag prevents high. confidence=0.65 lands in medium band.
    assert _calibrate_conviction(
        direction="long", confidence_score=0.65,
        analyst_agreement_count=4, ftfc_score=0.5,
        risk_severities=["info", "warn", "info"],
    ) == "medium"


def test_calibrate_conviction_high_confidence_with_warn_falls_to_low():
    """Edge: confidence 0.75 is too high for medium band (0.4-0.7) but
    a warn flag blocks the high path. Falls all the way to low — by
    design conservative."""
    from lib.agents.orchestrator import _calibrate_conviction
    assert _calibrate_conviction(
        direction="long", confidence_score=0.75,
        analyst_agreement_count=4, ftfc_score=0.5,
        risk_severities=["info", "warn", "info"],
    ) == "low"


def test_calibrate_conviction_high_blocked_by_low_ftfc():
    from lib.agents.orchestrator import _calibrate_conviction
    # FTFC too weak → demoted; falls into medium since other conditions
    # for medium hold (≥2 agreement, ≤1 warn, conf 0.4-0.7).
    assert _calibrate_conviction(
        direction="long", confidence_score=0.65,
        analyst_agreement_count=4, ftfc_score=0.3,
        risk_severities=["info"],
    ) == "medium"


def test_calibrate_conviction_medium_path():
    from lib.agents.orchestrator import _calibrate_conviction
    assert _calibrate_conviction(
        direction="long", confidence_score=0.55,
        analyst_agreement_count=2, ftfc_score=0.3,
        risk_severities=["warn"],
    ) == "medium"


def test_calibrate_conviction_low_when_few_analysts_agree():
    from lib.agents.orchestrator import _calibrate_conviction
    assert _calibrate_conviction(
        direction="long", confidence_score=0.55,
        analyst_agreement_count=1, ftfc_score=0.3,
        risk_severities=["info"],
    ) == "low"


def test_calibrate_conviction_low_when_confidence_too_high_for_medium():
    """conf 0.8 doesn't fit medium's 0.4-0.7 band but doesn't clear
    high either (only 2 analysts) → falls back to low."""
    from lib.agents.orchestrator import _calibrate_conviction
    assert _calibrate_conviction(
        direction="long", confidence_score=0.8,
        analyst_agreement_count=2, ftfc_score=0.3,
        risk_severities=["info"],
    ) == "low"


# ─── PR #351 codex review — FTFC sign must match direction ────────────


def test_calibrate_conviction_long_with_negative_ftfc_does_not_hit_high():
    """Codex review on PR #351: `abs(ftfc_score) >= 0.5` would let a
    contradicting FTFC count as agreement. A long trade with FTFC=-0.8
    means the multi-tf bias is screaming bearish — that must NOT be
    high conviction."""
    from lib.agents.orchestrator import _calibrate_conviction
    result = _calibrate_conviction(
        direction="long", confidence_score=0.75,
        analyst_agreement_count=4, ftfc_score=-0.8,
        risk_severities=["info", "info", "info"],
    )
    # Without sign-aware fix: would return 'high' (the bug).
    # Post-fix: ftfc_aligned=False → falls to medium / low.
    assert result != "high", (
        "Negative ftfc_score must not satisfy the long-direction "
        "high-conviction gate; sign must match direction."
    )


def test_calibrate_conviction_short_with_positive_ftfc_does_not_hit_high():
    from lib.agents.orchestrator import _calibrate_conviction
    result = _calibrate_conviction(
        direction="short", confidence_score=0.75,
        analyst_agreement_count=4, ftfc_score=0.8,
        risk_severities=["info", "info", "info"],
    )
    assert result != "high"


def test_calibrate_conviction_short_with_aligned_negative_ftfc_hits_high():
    """The legitimate short path: direction=short with ftfc=-0.5 IS
    aligned (both bearish) and clears the high gate."""
    from lib.agents.orchestrator import _calibrate_conviction
    result = _calibrate_conviction(
        direction="short", confidence_score=0.75,
        analyst_agreement_count=4, ftfc_score=-0.5,
        risk_severities=["info", "info", "info"],
    )
    assert result == "high"


def test_count_analyst_agreement_counts_matching_bias():
    from lib.agents.orchestrator import _count_analyst_agreement
    from types import SimpleNamespace

    bullish = SimpleNamespace(bias="bullish")
    bearish = SimpleNamespace(bias="bearish")
    neutral = SimpleNamespace(bias="neutral")
    reports = {
        "market": bullish, "strat": bullish, "options": neutral,
        "gamma": bullish, "catalyst": bearish, "sentiment": None,
    }
    assert _count_analyst_agreement(reports, "long") == 3
    assert _count_analyst_agreement(reports, "short") == 1
    assert _count_analyst_agreement(reports, "flat") == 1
    # None analysts (failed) don't count
    assert _count_analyst_agreement({"x": None, "y": None}, "long") == 0
