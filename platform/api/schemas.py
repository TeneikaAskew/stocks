"""Response models for every JSON route the frontend consumes.

Until 2026-09-07 most routes returned bare dicts, so the OpenAPI document
(platform/api/openapi.json, the cross-repo contract TeneikaAskew/solyra
validates against) described their responses as ``{}``. Every model here
was written from the router's actual ``return`` statements, not from the
frontend's types, so the schema advertises what the wire carries today.

Two deliberate choices keep the models from changing production behaviour:

* ``extra="allow"`` on every model. A key a router emits that a model does
  not name passes through instead of being dropped (Pydantic's default) or
  raising. The schema says ``additionalProperties: true``; the solyra
  contract test closes objects anyway, so a fixture may not depend on a key
  that is not declared here.
* Every route uses ``response_model_exclude_unset=True``. A key a router
  omits stays omitted and an explicit ``null`` stays ``null``, so the
  response bytes are identical to before; only validation is added. Fields
  a router can omit or null are therefore ``Optional`` with a ``None``
  default, and a value outside the declared type is a loud 500, never a
  silently coerced default (CLAUDE.md Rule 3.7).

Closed sets are ``Literal`` only where the producing code provably emits
nothing else; env-driven strings (auth mode, session names, data sources)
stay ``str`` so a mis-set variable cannot turn a working route into a 500.
"""
from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    """Base for every response model: unknown keys pass through."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ── live.py ──────────────────────────────────────────────────────────────


class LiveStatusResponse(ApiModel):
    is_open: bool
    session: str
    next_open: Optional[str] = None
    current_time_et: str


class LiveQuoteResponse(ApiModel):
    ticker: str
    price: float
    open: float
    high: float
    low: float
    volume: int
    change: float
    change_pct: float
    prev_close: float
    last_updated: str
    market_session: str
    market_open: bool


class LiveBar(ApiModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class LiveHistoryResponse(ApiModel):
    ticker: str
    interval: str
    count: int
    market_session: str
    market_open: bool
    bars: list[LiveBar]


class AvgVolumeResponse(ApiModel):
    ticker: str
    avg_volume_20d: float
    sample_size: int
    last_date: Optional[str] = None
    source: str


class IndicatorValues(ApiModel):
    ema9: Optional[float] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    rsi: Optional[float] = None
    stochK: Optional[float] = None
    stochD: Optional[float] = None
    atr: Optional[float] = None
    vwap: Optional[float] = None
    # Omitted by the zero-bar branch; present (possibly null) otherwise.
    stochKPrev: Optional[float] = None


class IndicatorCondition(ApiModel):
    id: str
    label: str
    met: bool
    current: Optional[float] = None
    threshold: Optional[float] = None
    operator: str


class IndicatorSignal(ApiModel):
    direction: str
    conditions: list[IndicatorCondition]
    strength: int
    fired: bool


class IndicatorSignals(ApiModel):
    call: IndicatorSignal
    put: IndicatorSignal


class ChartVoterCondition(ApiModel):
    id: str
    label: str
    met: bool
    detail: str


class ChartVoterSide(ApiModel):
    direction: str
    conditions: list[ChartVoterCondition]
    met_count: int
    total_count: int
    fires: bool


class ChartVoter(ApiModel):
    call: ChartVoterSide
    put: ChartVoterSide
    firing: Optional[str] = None


class IndicatorsResponse(ApiModel):
    indicators: IndicatorValues
    signals: IndicatorSignals
    chart_voter: ChartVoter


class SignalSeriesFire(ApiModel):
    time: str
    direction: str
    score: float
    bar_index: int


class SignalSeriesResponse(ApiModel):
    fires: list[SignalSeriesFire]


# ── config.py ────────────────────────────────────────────────────────────


class FirebaseWebConfig(ApiModel):
    apiKey: str
    authDomain: str
    projectId: str
    appId: str


class RuntimeConfigResponse(ApiModel):
    # Any lowercased AUTH_MODE value; a Literal here would 500 the app's boot
    # request on a mis-set environment.
    authMode: str
    firebase: Optional[FirebaseWebConfig] = None


class RsiZone(ApiModel):
    max: float
    label: str


class RsiConfig(ApiModel):
    period: int
    fast_period: int
    oversold: float
    overbought: float
    zones: list[RsiZone]
    call_range: list[float]
    put_range: list[float]
    call_exit: float
    put_exit: float


class EmaConfig(ApiModel):
    periods: list[int]


class AtrConfig(ApiModel):
    period: int
    high_threshold: float


class RvolConfig(ApiModel):
    period: int
    signal_threshold: float


class StochRsiConfig(ApiModel):
    period: int
    k_period: int
    d_period: int
    oversold: float
    overbought: float


class SignalThresholds(ApiModel):
    min_conditions: int
    consecutive_periods: int
    premarket_threshold: int


class IndicatorConfigResponse(ApiModel):
    rsi: RsiConfig
    ema: EmaConfig
    atr: AtrConfig
    rvol: RvolConfig
    stoch_rsi: StochRsiConfig
    signal: SignalThresholds


class MarketHoursWindow(ApiModel):
    open: str
    close: str


class MarketHoursResponse(ApiModel):
    timezone: str
    regular: MarketHoursWindow
    pre_market: MarketHoursWindow
    after_hours: MarketHoursWindow
    holidays_2026: list[str]


# ── main.py ──────────────────────────────────────────────────────────────


class HealthResponse(ApiModel):
    status: str
    project_root: str
    cloud_sql: bool
    gcs_bucket: str
    lib_dir_exists: bool


class MeResponse(ApiModel):
    email: Optional[str] = None
    is_admin: bool
    is_dev: bool


class MarketDatesResponse(ApiModel):
    ticker: str
    source: str
    dates: list[str]
    months: list[str]


class CandlestickBar(ApiModel):
    time: int
    open: float
    high: float
    low: float
    close: float


class VolumeBar(ApiModel):
    time: int
    value: float
    color: str


class MarketDataResponse(ApiModel):
    ticker: str
    date: str
    timeframe: int
    count: int
    candlestick: list[CandlestickBar]
    volume: list[VolumeBar]


class WeekRange(ApiModel):
    high: float
    low: float
    avg_close: float
    avg_rsi_14: Optional[float] = None
    start_date: str
    end_date: str
    sessions: int


class ReferenceResponse(ApiModel):
    ticker: str
    date: str
    open: float
    high: float
    low: float
    close: float
    # Absent on the GCS branch; present on AlphaVantage and Cloud SQL.
    source: Optional[str] = None
    # Present on the Cloud SQL branch only.
    stale_days: Optional[int] = None
    week: Optional[WeekRange] = None


class CoverageFlags(ApiModel):
    intraday: bool
    daily: bool


class CoverageResponse(ApiModel):
    coverage: dict[str, CoverageFlags]


class SectorRow(ApiModel):
    symbol: str
    name: str
    status: Literal["ok", "unavailable"]
    # Absent on the normal unavailable rows; present on ok rows and on rows
    # the data-quality check downgraded in place.
    close: Optional[float] = None
    chg_1d_pct: Optional[float] = None
    chg_5d_pct: Optional[float] = None
    reason: Optional[str] = None


class SectorsResponse(ApiModel):
    as_of: Optional[str] = None
    sectors: list[SectorRow]
    status: Literal["ok", "unavailable"]
    reason: Optional[str] = None


class MostActiveItem(ApiModel):
    ticker: str
    rank: int
    price: Optional[float] = None
    change_pct: Optional[float] = None
    volume: Optional[int] = None
    # Omitted (not null) when fewer than two finite prices exist.
    spark: Optional[list[float]] = None


class MostActiveResponse(ApiModel):
    snapshot_ts: Optional[str] = None
    snapshot_date: Optional[str] = None
    label: Optional[str] = None
    items: list[MostActiveItem]


# ── dashboard.py ─────────────────────────────────────────────────────────


class DailyIndicators(ApiModel):
    """Either every key below or an empty object when the daily query failed."""

    date: Optional[str] = None
    stale_days: Optional[int] = None
    close: Optional[float] = None
    rsi_14: Optional[float] = None
    ema_9: Optional[float] = None
    ema_20: Optional[float] = None
    sma_200: Optional[float] = None
    macd: Optional[float] = None
    atr: Optional[float] = None
    rvol: Optional[float] = None
    strat_candle: Any = None
    strat_combo: Any = None
    strat_setup: Optional[bool] = None
    ftfc_score: Optional[float] = None
    ftfc_direction: Any = None
    consecutive_up: Optional[int] = None
    consecutive_down: Optional[int] = None
    price_vs_ema9: Optional[float] = None
    price_vs_ema20: Optional[float] = None


class LiveOverlay(ApiModel):
    price: float
    session: str
    updated_at: str
    source: str


class DashboardBriefResponse(ApiModel):
    """Two branches: ``source == 'unavailable'`` carries only ``reason``; the
    ``cloud_sql`` branch spreads the premarket block flat (all of those keys
    present together or all absent) and always carries ``daily_indicators``."""

    ticker: str
    source: str
    reason: Optional[str] = None
    bias: Optional[str] = None
    has_premarket: Optional[bool] = None
    analysis_date: Optional[str] = None
    price: Optional[float] = None
    rsi: Optional[float] = None
    rsi_direction: Any = None
    consecutive_up: Optional[int] = None
    consecutive_down: Optional[int] = None
    signal_status: Any = None
    strat_candle: Any = None
    strat_combo: Any = None
    strat_setup: Optional[bool] = None
    ftfc_score: Optional[float] = None
    ftfc_direction: Any = None
    daily_indicators: Optional[DailyIndicators] = None
    live: Optional[LiveOverlay] = None


class MovementHeadline(ApiModel):
    status: str
    current_type: Optional[str] = None
    probability: Optional[float] = None
    probability_source: Optional[str] = None
    timeframe: Optional[str] = None
    reason: Optional[str] = None
    statement: Optional[str] = None


class MovementContinuation(ApiModel):
    status: str
    current_type: Optional[str] = None
    continuation_prob: Optional[float] = None
    timeframe: Optional[str] = None
    ts: Optional[str] = None
    model_version: Optional[str] = None
    last_train_date: Optional[str] = None
    live_ece: Optional[float] = None
    reason: Optional[str] = None


class ReachRate(ApiModel):
    status: str
    reach_rate: Optional[float] = None
    hits: Optional[int] = None
    sample_n: Optional[int] = None
    low_sample: Optional[bool] = None
    # Which premarket-playbook slot (trigger / t1 / t2 / t3) this rung's price
    # matched, and the analysis_date of the row it was matched against. Set on
    # every matched rung; an unmatched rung carries only the reason.
    slot: Optional[str] = None
    analysis_date: Optional[str] = None
    reason: Optional[str] = None


class MovementLevel(ApiModel):
    # select_nearest_levels emits all five keys; the endpoint passes the
    # assembler's output through unchanged, so only what every producer
    # (the router tests' stub assembler included) guarantees is required.
    price: float
    name: str
    period: Optional[str] = None
    level_type: Optional[str] = None
    distance_pct: Optional[float] = None
    reach_rate: ReachRate


class MovementLevels(ApiModel):
    status: str
    calls: Optional[list[MovementLevel]] = None
    puts: Optional[list[MovementLevel]] = None
    current_price: Optional[float] = None
    reach_rate_note: Optional[str] = None
    reason: Optional[str] = None


class Degeneracy(ApiModel):
    status: str
    degenerate: Optional[bool] = None
    modal_bucket: Optional[int] = None
    modal_share: Optional[float] = None
    n_bars: Optional[int] = None
    distinct_buckets: Optional[int] = None
    lookback_days: Optional[int] = None
    reason: Optional[str] = None


class ExpectedMoveProbabilities(ApiModel):
    p_tight: float
    p_normal: float
    p_expanded: float
    p_explosive: float


class ExpectedMove(ApiModel):
    status: str
    role: Optional[str] = None
    size_class: Optional[str] = None
    pred_bucket: Optional[int] = None
    probabilities: Optional[ExpectedMoveProbabilities] = None
    max_proba: Optional[float] = None
    model_version: Any = None
    ts: Any = None
    atr_20: Optional[float] = None
    current_price: Optional[float] = None
    usage_guidance: Optional[str] = None
    degeneracy: Optional[Degeneracy] = None
    reason: Optional[str] = None


class Regime(ApiModel):
    status: str
    role: Optional[str] = None
    regime: Optional[str] = None
    mood: Optional[str] = None
    gamma_flip: Any = None
    total_gex: Any = None
    data_source: Any = None
    snapshot_ts: Any = None
    reason: Optional[str] = None


class ConfidenceModifiers(ApiModel):
    note: str
    expected_move: ExpectedMove
    regime: Regime


class MovementStatementResponse(ApiModel):
    status: str
    ticker: str
    timeframe: str
    as_of: Optional[str] = None
    scope_statement: str
    headline: MovementHeadline
    continuation: MovementContinuation
    levels: MovementLevels
    confidence_modifiers: ConfidenceModifiers


# ── signals.py ───────────────────────────────────────────────────────────


class SignalRow(ApiModel):
    # Every key is present on the Cloud SQL branch; the parquet fallback
    # only emits the columns the file carries.
    time: Optional[str] = None
    direction: Optional[str] = None
    close: Optional[float] = None
    rsi: Optional[float] = None
    ema9: Optional[float] = None
    ema20: Optional[float] = None
    volume: Optional[float] = None
    score: Optional[float] = None
    conditions_met: Any = None
    return_pct: Optional[float] = None
    ticker: str


class SignalsResponse(ApiModel):
    ticker: str
    count: int
    returned: int
    source: str
    file: Optional[str] = None
    signals: list[SignalRow]


class SimilarStats(ApiModel):
    count: int
    avg_mfe_pct: Optional[float] = None
    median_mfe_pct: Optional[float] = None
    p25_mfe_pct: Optional[float] = None
    p75_mfe_pct: Optional[float] = None
    avg_return_5min: Optional[float] = None
    avg_return_20min: Optional[float] = None
    pct_profitable: Optional[float] = Field(default=None, description="Fraction 0..1, not a percent")
    earliest: Optional[str] = None
    latest: Optional[str] = None


class SimilarMatch(ApiModel):
    time: str
    direction: Optional[str] = None
    price: Optional[float] = None
    score: Optional[int] = None
    rsi: Optional[float] = None
    return_pct: Optional[float] = None
    return_5min: Optional[float] = None
    return_20min: Optional[float] = None


class SimilarResponse(ApiModel):
    ticker: str
    direction: str
    rsi: float
    score: int
    rsi_band: float
    stats: SimilarStats
    matches: list[SimilarMatch]


# ── playbook.py ──────────────────────────────────────────────────────────


class PlaybookHorizon(ApiModel):
    minutes: int
    win_rate: Optional[float] = None
    avg_return_bps: Optional[float] = None
    sample_n: Any = None


class PlaybookCard(ApiModel):
    id: str
    name: Optional[str] = None
    description: str
    direction: Optional[str] = None
    conditions: list[Any]
    win_rate: Optional[float] = None
    avg_return: Optional[float] = None
    target_pct: Optional[float] = None
    stop_pct: Optional[float] = None
    horizons: list[PlaybookHorizon]
    best_horizon_min: Optional[int] = None
    best_horizon_win_rate: Optional[float] = None
    best_horizon_avg_bps: Optional[float] = None


class PlaybookResponse(ApiModel):
    ticker: str
    cards: list[PlaybookCard]
    source: str
    analysis_date: str
    generated_at: Optional[str] = None
    max_age_days: int
    age_days: int
    # Present only when ?date= was supplied.
    as_of: Optional[str] = None


class ReportEntry(ApiModel):
    filename: str
    phase: str
    path: str


class ReportListResponse(ApiModel):
    ticker: str
    reports: list[ReportEntry]


class PlaybookEvalResult(ApiModel):
    status: Literal["met", "unmet", "unknown"]
    detail: Optional[str] = None
    reason: Optional[str] = None


class PlaybookEvaluateResponse(ApiModel):
    """``results`` when the request carried ``conditions``, ``results_by_key``
    when it carried ``batches``, both when it carried both."""

    results: Optional[list[PlaybookEvalResult]] = None
    results_by_key: Optional[dict[str, list[PlaybookEvalResult]]] = None


# ── options.py / grid.py ─────────────────────────────────────────────────


class OptionsDatesResponse(ApiModel):
    ticker: str
    dates: list[str]
    source: str
    # Absent on a cache hit.
    window: Optional[str] = None
    cached: bool


class OptionContract(ApiModel):
    contract_symbol: Optional[str] = None
    expiration: str
    strike: float
    type: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    mark: Optional[float] = None
    last: Optional[float] = None
    # DOUBLE PRECISION on the Cloud SQL path, int on the live path.
    volume: Optional[float] = None
    open_interest: Optional[float] = None
    implied_volatility: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None


class OptionsChainMetadata(ApiModel):
    source: str
    data_source: str
    row_count: int


class OptionsChainResponse(ApiModel):
    ticker: str
    date: str
    options: list[OptionContract]
    snapshot_timestamp: str
    metadata: OptionsChainMetadata
    cached: bool


class AggregatedStrike(ApiModel):
    strike: float
    net_gamma: float
    call_gamma: float
    put_gamma: float
    net_vega: float
    call_vega: float
    put_vega: float
    call_oi: float
    put_oi: float
    call_volume: float
    put_volume: float


class GexByStrike(ApiModel):
    strike: float
    gex: float
    call_gex: float
    put_gex: float


class OptionsMetrics(ApiModel):
    total_gex: float
    total_vex: float
    zero_gamma: Optional[float] = None
    max_pain: Optional[float] = None
    implied_move: Optional[float] = None
    put_call_ratio: float


class StrikeNode(ApiModel):
    type: str
    strike: float
    gamma: float
    distance_from_spot: float
    distance_percent: float
    # Midpoint nodes only.
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None


class NodeResult(ApiModel):
    kingNode: Optional[StrikeNode] = None
    gatekeepers: list[StrikeNode]
    midpoints: list[StrikeNode]
    allNodes: list[StrikeNode]


class GreeksConfig(ApiModel):
    strike_range_pct: float
    atm_tolerance: float
    node_min_gamma: float


class GreeksResponse(ApiModel):
    aggregated: list[AggregatedStrike]
    gex_by_strike: list[GexByStrike]
    metrics: OptionsMetrics
    nodes: NodeResult
    config: GreeksConfig


class SpotEstimate(ApiModel):
    price: float
    method: str
    note: str


class GammaLevel(ApiModel):
    strike: float
    gex: float
    net_gamma: float
    call_oi: int
    put_oi: int
    distance_pct: float
    score: float
    kind: str
    tags: list[str]


class GammaLevelsResponse(ApiModel):
    ticker: str
    snapshot_date: str
    spot: SpotEstimate
    gamma_balance: Optional[float] = None
    gamma_flip: Optional[float] = None
    regime: str
    total_gex: float
    levels: list[GammaLevel]
    kings: list[GammaLevel]
    gates: list[GammaLevel]
    gamma_balance_levels: list[GammaLevel]
    window_pct: float
    warnings: list[str]
    snapshot_timestamp: Optional[str] = None
    chain_size: int


class GammaGridCell(ApiModel):
    strike: float
    expiration: str
    dte: int
    net_gamma: float
    call_gamma: float
    put_gamma: float
    net_vega: float
    call_vega: float
    put_vega: float
    gex: float
    call_gex: float
    put_gex: float
    vex: float
    call_vex: float
    put_vex: float
    call_oi: int
    put_oi: int
    call_volume: int
    put_volume: int
    distance_pct: float


class GammaGridResponse(ApiModel):
    """The unavailable envelope nulls ``snapshot_date``/``snapshot_ts``/``spot``
    and adds ``reason``; the happy path never carries ``reason``."""

    ticker: str
    snapshot_date: Optional[str] = None
    snapshot_ts: Optional[str] = None
    data_source: str
    reason: Optional[str] = None
    spot: Optional[SpotEstimate] = None
    gamma_balance: Optional[float] = None
    gamma_flip: Optional[float] = None
    regime: str
    total_gex: float
    total_vex: float
    cells: list[GammaGridCell]
    expirations: list[str]
    strikes: list[float]
    window_pct: float
    warnings: list[str]


class NodeLevel(ApiModel):
    strike: float
    gex: float
    net_gamma: float
    call_oi: int
    put_oi: int
    distance_pct: float
    score: float
    dominant_side: str


class OpexNode(ApiModel):
    strike: float
    expiration: str
    dte: int
    gex: float
    call_oi: int
    put_oi: int


class GammaNodesResponse(ApiModel):
    ticker: str
    snapshot_ts: Optional[str] = None
    snapshot_date: Optional[str] = None
    data_source: str
    spot: Optional[SpotEstimate] = None
    gamma_balance: Optional[float] = None
    gamma_flip: Optional[float] = None
    regime: str
    total_gex: float
    total_vex: float
    king: Optional[NodeLevel] = None
    gates: list[NodeLevel]
    midpoints: list[NodeLevel]
    hedge_nodes: list[Any]
    opex_nodes: list[OpexNode]
    tactical_summary: Any = None
    warnings: list[str]


class GridSeriesRow(ApiModel):
    snapshot_ts: str
    strike: float
    gex: float
    delta_from_prev: Optional[float] = None


class GridTimeseriesResponse(ApiModel):
    """The unavailable branches omit ``strikes_resolved``, ``spot_used``,
    ``spot_method`` and ``gamma_coverage``."""

    ticker: str
    expiration: Optional[str] = None
    lookback_hours: float
    data_source: str
    strikes_resolved: Optional[list[float]] = None
    spot_used: Optional[float] = None
    spot_method: Optional[str] = None
    gamma_coverage: Optional[float] = None
    warnings: list[str]
    series: list[GridSeriesRow]


# ── journal.py ───────────────────────────────────────────────────────────


class JournalTradeRow(ApiModel):
    """Shared by /trades (has ``created_at``) and the pipeline half of
    /examples (has ``time_stop_minutes`` instead). Legacy local-file rows may
    carry fewer keys, which is why almost everything is optional."""

    id: str
    ticker: str
    direction: Optional[str] = None
    entry_ts: Optional[str] = None
    exit_ts: Optional[str] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    return_pct: Optional[float] = None
    notes: Optional[str] = None
    stop_loss: Optional[float] = None
    status: Optional[str] = None
    source: Optional[str] = None
    session_id: Optional[str] = None
    created_at: Optional[str] = None
    take_profits: Optional[list[float]] = None
    time_stop_minutes: Optional[int] = None


class JournalTradesResponse(ApiModel):
    ticker: str
    source: str
    count: int
    trades: list[JournalTradeRow]


class JournalMutationResponse(ApiModel):
    source: str
    id: str
    return_pct: Optional[float] = None
    status: str


class JournalDeleteResponse(ApiModel):
    source: str
    deleted: str


class SeedTradeRow(ApiModel):
    id: str
    direction: Optional[str] = None
    entry_time: Optional[str] = None
    entry_price: Optional[float] = None
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    return_pct: Optional[float] = None
    strat_combo: Optional[str] = None
    exit_reason: Optional[str] = None


class SeedTradesOk(ApiModel):
    ticker: str
    date: str
    count: int
    trades: list[SeedTradeRow]


class SeedTradesUnavailable(ApiModel):
    status: Literal["unavailable"]
    reason: str


SeedTradesResponse = Union[SeedTradesUnavailable, SeedTradesOk]


class JournalExportResponse(ApiModel):
    success: bool
    trades_exported: int
    output_path: str
    filename: str


class ImportPreviewTrade(ApiModel):
    ticker: str
    direction: str
    entry_ts: str
    entry_price: float
    exit_ts: Optional[str] = None
    exit_price: Optional[float] = None
    return_pct: Optional[float] = None
    quantity: int
    status: str
    duplicate: bool


class ImportSkippedRow(ApiModel):
    raw_index: int
    reason: str


class ImportPreviewResponse(ApiModel):
    broker: str
    trades: list[ImportPreviewTrade]
    skipped: list[ImportSkippedRow]


class ImportCommitResponse(ApiModel):
    imported: int
    skipped_duplicates: int


# ── backtest.py ──────────────────────────────────────────────────────────


class BacktestRunInfo(ApiModel):
    filename: str
    path: str
    timestamp: str
    modified: Optional[str] = None
    size_bytes: Optional[int] = None
    row_count: Optional[int] = None
    has_equity_curve: bool
    trade_count: Optional[int] = None
    win_rate: Optional[float] = None
    avg_return_pct: Optional[float] = None


class BacktestAllResponse(ApiModel):
    ticker: str
    total_runs: int
    runs: list[BacktestRunInfo]


class BacktestSummary(ApiModel):
    """``{}`` when the CSV has no usable ``return_pct`` column."""

    total_trades: Optional[int] = None
    win_count: Optional[int] = None
    loss_count: Optional[int] = None
    win_rate: Optional[float] = None
    avg_return_pct: Optional[float] = None
    avg_win_pct: Optional[float] = None
    avg_loss_pct: Optional[float] = None
    total_return_pct: Optional[float] = None


class BacktestResultsResponse(ApiModel):
    ticker: str
    filename: str
    trade_count: int
    summary: BacktestSummary
    # The CSV's columns verbatim; there is no fixed key set.
    trades: list[dict[str, Any]]


class EquitySummary(ApiModel):
    start_value: Optional[float] = None
    end_value: Optional[float] = None
    peak_value: Optional[float] = None
    total_return_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    data_points: Optional[int] = None


class BacktestEquityResponse(ApiModel):
    ticker: str
    filename: str
    summary: EquitySummary
    dates: list[str]
    values: list[Optional[float]]


class ReplaySystemSignal(ApiModel):
    status: Optional[str] = None
    direction: Optional[str] = None
    score: Optional[float] = None


class ReplaySystemExit(ApiModel):
    exit_reason: Optional[str] = None
    return_pct: Optional[float] = None
    exit_time: Optional[str] = None


class ReplayTradeCard(ApiModel):
    id: str
    status: str
    reason: Optional[str] = None
    actual_return_pct: Optional[float] = None
    fill_check: Optional[str] = None
    system_signal_at_entry: Optional[ReplaySystemSignal] = None
    system_exit: Optional[ReplaySystemExit] = None
    exit_edge_bps: Optional[float] = None


class ReplayAggregate(ApiModel):
    n: int
    scored_n: int
    win_rate: Optional[float] = None
    avg_return_pct: Optional[float] = None
    system_resolved_n: int
    system_no_signal_n: int
    system_agreement_rate: Optional[float] = None
    avg_exit_edge_bps: Optional[float] = None


class ReplayTradesResponse(ApiModel):
    trades: list[ReplayTradeCard]
    aggregate: ReplayAggregate


class MineStyleProfile(ApiModel):
    direction: str
    conditions: list[str]
    support: int
    total: int


class MineStyleSuccess(ApiModel):
    profile: MineStyleProfile
    # avg_*/std_* for every fold metric plus total_folds and
    # total_trades_all_folds; the key set varies per request.
    aggregate_metrics: dict[str, float]
    stability_score: float
    staged: bool


class MineStyleUnavailable(ApiModel):
    status: Literal["unavailable"]
    reason: str


MineStyleResponse = Union[MineStyleUnavailable, MineStyleSuccess]


# ── catalysts.py ─────────────────────────────────────────────────────────


class CatalystEvent(ApiModel):
    """Union of the Benzinga-cache shape (event/expected_impact/details/
    confirmed/company_name) and the five DB-sourced shapes (title/impact plus
    per-source extras). Everything is optional because no key is common to
    all producers except date/ticker/catalyst_type/source."""

    date: Optional[str] = None
    ticker: Optional[str] = None
    catalyst_type: Optional[str] = None
    source: Optional[str] = None
    company_name: Optional[str] = None
    event: Optional[str] = None
    expected_impact: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    confirmed: Optional[bool] = None
    title: Optional[str] = None
    impact: Optional[str] = None
    url: Optional[str] = None
    sentiment_label: Optional[str] = None
    sentiment_score: Optional[float] = None
    relevance_score: Optional[float] = None
    country: Optional[str] = None
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    insiders: Optional[int] = None
    total_value: Optional[float] = None
    items: Optional[list[str]] = None
    primary_doc: Optional[str] = None
    accession_number: Optional[str] = None


class CatalystDateRange(ApiModel):
    from_: str = Field(alias="from")
    to: str


class CatalystsResponse(ApiModel):
    status: str
    source: str
    date_range: CatalystDateRange
    total: int
    events_by_date: dict[str, list[CatalystEvent]]


class CatalystTypeInfo(ApiModel):
    label: str
    color: str
    icon: str


class CatalystTypesResponse(ApiModel):
    benzinga_types: dict[str, CatalystTypeInfo]
    wsh_only_types: dict[str, CatalystTypeInfo]
    upgrade_note: str


# ── insights.py ──────────────────────────────────────────────────────────


class TickerSearchMatch(ApiModel):
    symbol: str
    name: str
    type: str
    region: str
    currency: str
    match_score: float


class TickerSearchResponse(ApiModel):
    keywords: str
    results: list[TickerSearchMatch]


class SignalContribution(ApiModel):
    name: str
    available: bool
    score_0_to_1: float
    weight: float
    points: float
    reason: str
    raw: dict[str, Any]


class RankedTicker(ApiModel):
    ticker: str
    score: float
    pct_of_max: float
    catalyst_types: list[str]
    catalyst_metadata: dict[str, list[dict[str, Any]]]
    score_breakdown: list[SignalContribution]


class WatchlistResponse(ApiModel):
    run_id: str
    as_of: str
    candidate_count: int
    excluded_count: int
    ranked: list[RankedTicker]
    weights_used: dict[str, float]
    duration_ms: int


class WatchlistRemoveResponse(ApiModel):
    ticker: str
    removed: bool
    watchlist: list[str]


class InsightHistoryRow(ApiModel):
    id: str
    as_of: Optional[str] = None
    direction: Optional[str] = None
    conviction: Optional[str] = None
    thesis: Optional[str] = None
    cost_usd: Optional[float] = None


class InsightHistoryResponse(ApiModel):
    ticker: str
    count: int
    reports: list[InsightHistoryRow]


# ── waitlist.py / preferences.py / profile.py / health.py ────────────────


class WaitlistResponse(ApiModel):
    status: Literal["ok"]


class PreferencesResponse(ApiModel):
    """All four keys always present, each independently nullable; the
    columns are bare TEXT, so values stay ``str`` rather than ``Literal``."""

    theme: Optional[str] = None
    nav_pattern: Optional[str] = None
    density: Optional[str] = None
    accent: Optional[str] = None


class ProfileResponse(ApiModel):
    display_name: Optional[str] = None
    timezone: Optional[str] = None
    default_ticker: Optional[str] = None
    default_timeframe: Optional[str] = None
    account_size: Optional[float] = None
    risk_per_trade_pct: Optional[float] = None
    notify_daily_digest: Optional[bool] = None
    notify_catalyst_alerts: Optional[bool] = None
    notify_signal_alerts: Optional[bool] = None
    number_format: Optional[str] = None
    date_format: Optional[str] = None
    show_extended_hours: Optional[bool] = None


class FreshnessRow(ApiModel):
    table: str
    ticker: Optional[str] = None
    last_row_at: Optional[str] = None
    expected_latest: str
    lag_hours: Optional[float] = None
    expected_max_hours: float
    status: str
    row_count_recent: int
    writer_job: Optional[str] = None


class FreshnessResponse(ApiModel):
    checked_at: str
    expected_market_close: str
    overall_status: str
    tables: list[FreshnessRow]
    # Present ONLY when a refresh is in flight and this response is the
    # previous report served in its place. Absent on a fresh read, which is
    # what `response_model_exclude_unset` renders. They were being emitted as
    # undeclared extras, so the committed OpenAPI contract did not carry them
    # and no consumer could be expected to read them (Codex, PR #991).
    stale: Optional[bool] = None
    stale_age_seconds: Optional[int] = None
