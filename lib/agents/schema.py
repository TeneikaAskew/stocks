"""
Pydantic models for the AI Insights agent pipeline.

Every agent boundary emits a structured output validated against one
of these models. No prose-parsing, no regex extraction. The top-level
InsightReport is what lands in the `insight_reports` Cloud SQL table
as a JSONB payload.

Type choices are driven by cross-provider structured-output support:
no tuples (OpenAI Structured Outputs rejects them), no unions with
defaults, Literal enums everywhere an enum is expected.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Role identifiers — these are the keys into the model_routing table and
# drive per-role provider selection.
# ---------------------------------------------------------------------------

AgentRole = Literal[
    "analyst",
    "bull",
    "bear",
    "judge",
    "trader",
    "risk",
    "portfolio_manager",
]

ALL_ROLES: tuple[AgentRole, ...] = (
    "analyst",
    "bull",
    "bear",
    "judge",
    "trader",
    "risk",
    "portfolio_manager",
)


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------


class EntryZone(BaseModel):
    """Entry price range. Replaces `tuple[float, float]` so OpenAI strict
    mode and Anthropic tool-use forced-choice accept the schema."""

    model_config = ConfigDict(extra="forbid")

    low: float = Field(..., description="Lower bound of the entry zone")
    high: float = Field(..., description="Upper bound of the entry zone")


class StratSnapshot(BaseModel):
    """Rob Smith strat state for the ticker. Emitted by
    summarize_strat_status."""

    model_config = ConfigDict(extra="forbid")

    last_candle: Literal["1", "2U", "2D", "3"] = Field(
        ..., description="Strat candle type of the most recent closed bar"
    )
    in_force_combo: Optional[str] = Field(
        None,
        description="In-force combo pattern, e.g. '212_bull_reversal' or null",
    )
    ftfc_score: float = Field(
        ..., description="Full-timeframe-continuity weighted score, -1.0 to +1.0"
    )
    ftfc_direction: Literal["bullish", "bearish", "mixed"]
    trigger_high: Optional[float] = None
    trigger_low: Optional[float] = None


class Catalyst(BaseModel):
    """A surfaced catalyst — economic event, scheduled earnings, recent
    high-relevance news, or material SEC filing."""

    model_config = ConfigDict(extra="forbid")

    name: str
    date: str = Field(..., description="ISO date (YYYY-MM-DD)")
    impact: Literal["high", "medium", "low"]
    kind: Literal["economic", "earnings", "news_topic", "sec_8k"]
    sentiment_score: Optional[float] = Field(
        default=None,
        description=(
            "AlphaVantage overall_sentiment_score for news_topic items "
            "(range -1 to +1; >+0.15 bullish, <-0.15 bearish). None for "
            "non-news kinds (economic / earnings / sec_8k) where "
            "directional sentiment doesn't apply. Discord embed renders "
            "🟢/🟡/🔴 from this when present, defaults to 🟡 otherwise."
        ),
    )


class RiskFlag(BaseModel):
    """Single risk concern emitted by one of the three risk debate personas."""

    model_config = ConfigDict(extra="forbid")

    persona: Literal["aggressive", "conservative", "neutral"]
    severity: Literal["info", "warn", "block"]
    message: str


class RiskMetrics(BaseModel):
    """Pre-computed deterministic distances on a PersonaPlan.

    Empirical validation (docs/audits/2026-05-10-risk-reviewer-validation.md)
    found that LLM-computed risk distances (e.g. "stop < 1 ATR") had
    44.4% precision and 22.2% recall. The math itself is simple but
    the LLM hallucinates the comparison. So all distances are computed
    deterministically here and persisted; the LLM reviewer reads these
    columns and applies threshold rules WITHOUT recomputing.

    Empirically-validated thresholds (per the same audit, 36-day SPY/IWM/QQQ
    sample):
      * stop_distance_atr < 1.0       → -31.1pp win-rate signal (warn)
      * stop_distance_pct > 1.0       → -24.9pp signal           (warn)
      * entry_vs_sma200_pct > 10.0    → -21.8pp signal at >10%   (warn)
      * any t_r_multiple < 1.5        → -18.8pp signal           (warn)
    """

    model_config = ConfigDict(extra="forbid")

    stop_distance_atr: Optional[float] = Field(
        None,
        description=(
            "abs(entry_mid - stop) / atr_14 — how many ATRs of room "
            "the stop has before it triggers. < 1.0 typically warns."
        ),
    )
    stop_distance_pct: Optional[float] = Field(
        None,
        description=(
            "abs(entry_mid - stop) / entry_mid * 100 — stop distance as "
            "% of entry price. > 1.0 typically warns on indices."
        ),
    )
    target_r_multiples: list[float] = Field(
        default_factory=list,
        description=(
            "For each target, (target - entry_mid) / risk_per_unit, "
            "signed by direction (positive = good R:R). Empty when "
            "no targets or risk_per_unit == 0."
        ),
    )
    entry_vs_sma200_pct: Optional[float] = Field(
        None,
        description=(
            "(entry_mid - sma_200) / sma_200 * 100. Positive = entry "
            "above 200 SMA (typical for trend-following longs)."
        ),
    )
    entry_vs_sma200_atr: Optional[float] = Field(
        None,
        description="(entry_mid - sma_200) / atr_14 — same in ATR units.",
    )
    ftfc_aligned: Optional[bool] = Field(
        None,
        description=(
            "True if direction matches FTFC sign (long+bullish or "
            "short+bearish AND |ftfc_score| >= 0.5). Already deterministic "
            "via _calibrate_conviction; surfaced here for reviewer prompts."
        ),
    )
    invalidation_distance_atr: Optional[float] = Field(
        None,
        description=(
            "abs(invalidation_level - stop) / atr_14 when invalidation "
            "is a price-level (Optional). None when invalidation is "
            "narrative-only."
        ),
    )


class PersonaPlan(BaseModel):
    """Concrete trade plan emitted by one of the three risk-debate personas.

    Each persona returns the same plan shape (entry, stop, targets,
    sizing) but with different price levels reflecting their risk
    tolerance:

      * aggressive   — wider stops, further targets, higher sizing,
                       OK with tighter entries on momentum.
      * conservative — tighter stops at structural levels, closer
                       targets, halved sizing into catalyst windows.
      * neutral      — base case, ~1 ATR stop, balanced sizing.

    Rendered as a side-by-side table in the UI so the user can pick
    which persona's plan matches their own risk profile.
    """

    model_config = ConfigDict(extra="forbid")

    persona: Literal["aggressive", "conservative", "neutral"]
    entry_zone: EntryZone
    stop: float
    targets: list[float] = Field(
        default_factory=list,
        description="Up to 3 price targets, ordered T1 → T3.",
    )
    position_size_pct: float = Field(
        ..., ge=0.0, le=2.0,
        description="Sizing as a fraction of normal allocation (1.0 = normal).",
    )
    rationale: str = Field(
        ..., description="One-sentence justification for these levels."
    )
    regime: Literal["normal", "extended", "orb_only"] = Field(
        default="normal",
        description=(
            "Trigger regime classification. 'normal' = next structural "
            "level within 3 ATR (standard breakout). 'extended' = next "
            "level >= 3 ATR away (recommend ORB confirmation). "
            "'orb_only' = no unbroken structural trigger; wait for the "
            "opening range to establish before entering."
        ),
    )
    risk_metrics: Optional[RiskMetrics] = Field(
        default=None,
        description=(
            "Pre-computed deterministic risk distances. Optional during "
            "transition — rendered None when the bundle lacks atr_14 or "
            "sma_200. Reviewer prompts read these fields directly; they "
            "do NOT recompute the math (LLM math hallucinates ~55% of "
            "the time per the 2026-05-10 validation audit)."
        ),
    )


class SignalRef(BaseModel):
    """Reference to a signal_alerts row that supports the thesis."""

    model_config = ConfigDict(extra="forbid")

    alert_ts: str
    direction: Literal["CALL", "PUT"]
    strength: str
    score: float


class JournalRef(BaseModel):
    """Reference to a journal_entries row retrieved by reflection memory."""

    model_config = ConfigDict(extra="forbid")

    id: str
    ticker: str
    direction: Literal["CALL", "PUT"]
    return_pct: Optional[float] = None
    cosine_distance: float = Field(
        ..., description="Lower is more similar. 0.0 = identical embedding."
    )


# ---------------------------------------------------------------------------
# InsightReport — the final pipeline output
# ---------------------------------------------------------------------------


class InsightReport(BaseModel):
    """Top-level structured report persisted per (ticker, as_of)."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    as_of: datetime
    direction: Literal["long", "short", "flat"]
    conviction: Literal["low", "medium", "high"]
    thesis: str = Field(
        ..., description="2-3 sentence plain-English trade thesis"
    )
    regime: Literal["normal", "extended", "orb_only"] = Field(
        default="normal",
        description=(
            "Trigger regime for this setup. 'normal' = standard "
            "breakout entry at the next structural level. 'extended' = "
            "next level is >= 3 ATR away; 15-min ORB confirmation "
            "recommended. 'orb_only' = pre-market cleared every "
            "structural level in the trade direction (extreme gap day); "
            "wait for the opening range to establish before entering. "
            "Brief / Discord push render different copy per regime."
        ),
    )
    entry_zone: EntryZone
    stop: float
    targets: list[float] = Field(default_factory=list)
    invalidation: str = Field(
        ..., description="What observable condition would kill this trade"
    )
    time_horizon: Literal["intraday", "swing", "position"]
    key_levels: dict[str, float] = Field(
        default_factory=dict,
        description="Named levels (support, resistance, pivot, etc.)",
    )
    strat_status: StratSnapshot
    catalysts: list[Catalyst] = Field(default_factory=list)
    bull_case: str
    bear_case: str
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    persona_plans: list[PersonaPlan] = Field(
        default_factory=list,
        description="Per-persona concrete trade plans (entry, stop, targets, sizing).",
    )
    supporting_signals: list[SignalRef] = Field(default_factory=list)
    similar_past_trades: list[JournalRef] = Field(default_factory=list)
    confidence_score: float = Field(..., ge=0.0, le=1.0)

    # Run metadata
    failed_sections: list[str] = Field(
        default_factory=list,
        description="Analyst section names that failed and were degraded",
    )
    failed_section_reasons: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Per-section failure reason (only populated for entries in "
            "failed_sections). Captured from the summarizer's "
            "`reason` field or the exception message — gives operators "
            "diagnostic visibility without scraping Cloud Logs. Audit "
            "2026-05-08 G.P2.13."
        ),
    )
    model_versions: dict[str, str] = Field(
        default_factory=dict,
        description="Per-role provider:model snapshot for reproducibility",
    )
    run_cost_usd: float = 0.0
    run_latency_ms: int = 0
    per_role_cost: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "USD cost per role (analyst tiers split by section: "
            "'analyst:market', 'analyst:strat', ...; risk tier split by "
            "persona: 'risk:aggressive', etc.). Sum equals run_cost_usd "
            "within rounding."
        ),
    )


# ---------------------------------------------------------------------------
# Per-agent intermediate outputs. These exist so each node's LLM call
# can return a schema smaller than the full InsightReport.
# ---------------------------------------------------------------------------


class AnalystOutput(BaseModel):
    """Generic analyst section — one per parallel analyst."""

    model_config = ConfigDict(extra="forbid")

    section: Literal["market", "strat", "options", "catalyst", "sentiment", "gamma"]
    summary: str
    bullets: list[str] = Field(default_factory=list)
    bias: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(..., ge=0.0, le=1.0)


class ResearcherOutput(BaseModel):
    """Bull or Bear researcher output."""

    model_config = ConfigDict(extra="forbid")

    stance: Literal["bull", "bear"]
    case: str = Field(..., description="The adversarial argument")
    key_points: list[str] = Field(default_factory=list)
    rebuttal_to_opponent: Optional[str] = None


class JudgeOutput(BaseModel):
    """Research-manager verdict over the bull/bear debate."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["long", "short", "flat"]
    thesis: str
    weight_bull: float = Field(..., ge=0.0, le=1.0)
    weight_bear: float = Field(..., ge=0.0, le=1.0)
    rationale: str


class TraderOutput(BaseModel):
    """Trader turns the judge's thesis into a concrete trade plan."""

    model_config = ConfigDict(extra="forbid")

    direction: Literal["long", "short", "flat"]
    entry_zone: EntryZone
    stop: float
    targets: list[float]
    time_horizon: Literal["intraday", "swing", "position"]
    invalidation: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class RiskPersonaOutput(BaseModel):
    """One of three risk debate personas.

    Persona returns *qualitative* flags only. The concrete numbers
    (entry / stop / targets / sizing) used to live here too but are
    now computed deterministically by lib.agents.trade_planner using
    explicit per-persona recipes — this gives reproducible plans
    across runs while the LLM still owns the narrative review.
    """

    model_config = ConfigDict(extra="forbid")

    persona: Literal["aggressive", "conservative", "neutral"]
    flags: list[RiskFlag] = Field(default_factory=list)
    overall_severity: Literal["info", "warn", "block"]


class PortfolioManagerOutput(BaseModel):
    """Final merge. Same shape as InsightReport minus run metadata."""

    model_config = ConfigDict(extra="forbid")

    direction: Literal["long", "short", "flat"]
    conviction: Literal["low", "medium", "high"]
    thesis: str
    entry_zone: EntryZone
    stop: float
    targets: list[float]
    invalidation: str
    time_horizon: Literal["intraday", "swing", "position"]
    key_levels: dict[str, float] = Field(default_factory=dict)
    bull_case: str
    bear_case: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
