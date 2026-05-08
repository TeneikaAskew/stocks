// Types that mirror lib.agents.schema InsightReport on the backend.
// Keep these in sync with lib/agents/schema.py when fields change.

export type Direction = 'long' | 'short' | 'flat';
export type Conviction = 'low' | 'medium' | 'high';
export type TimeHorizon = 'intraday' | 'swing' | 'position';
export type RiskSeverity = 'info' | 'warn' | 'block';
export type RiskPersona = 'aggressive' | 'conservative' | 'neutral';

export interface EntryZone {
  low: number;
  high: number;
}

export interface StratSnapshot {
  last_candle: '1' | '2U' | '2D' | '3';
  in_force_combo: string | null;
  ftfc_score: number;
  ftfc_direction: 'bullish' | 'bearish' | 'mixed';
  trigger_high: number | null;
  trigger_low: number | null;
}

export interface Catalyst {
  name: string;
  date: string;
  impact: 'high' | 'medium' | 'low';
  kind: 'economic' | 'earnings' | 'news_topic' | 'sec_8k';
}

export interface RiskFlag {
  persona: RiskPersona;
  severity: RiskSeverity;
  message: string;
}

export interface PersonaPlan {
  persona: RiskPersona;
  entry_zone: EntryZone;
  stop: number;
  targets: number[];
  position_size_pct: number;
  rationale: string;
}

export interface SignalRef {
  alert_ts: string;
  direction: 'CALL' | 'PUT';
  strength: string;
  score: number;
}

export interface JournalRef {
  id: string;
  ticker: string;
  direction: 'CALL' | 'PUT';
  return_pct: number | null;
  cosine_distance: number;
}

export interface InsightReport {
  ticker: string;
  as_of: string;
  direction: Direction;
  conviction: Conviction;
  thesis: string;
  entry_zone: EntryZone;
  stop: number;
  targets: number[];
  invalidation: string;
  time_horizon: TimeHorizon;
  key_levels: Record<string, number>;
  strat_status: StratSnapshot;
  catalysts: Catalyst[];
  bull_case: string;
  bear_case: string;
  risk_flags: RiskFlag[];
  persona_plans: PersonaPlan[];
  supporting_signals: SignalRef[];
  similar_past_trades: JournalRef[];
  confidence_score: number;
  failed_sections: string[];
  model_versions: Record<string, string>;
  run_cost_usd: number;
  run_latency_ms: number;
  // Per-role USD spend (e.g. "analyst:market", "risk:neutral", "judge").
  // Sum equals run_cost_usd within rounding. Persisted to
  // insight_reports.per_role_cost on the backend.
  per_role_cost: Record<string, number>;
}

// GET /api/insights/report/{ticker}
export interface InsightReportEnvelope {
  ticker: string;
  as_of: string;
  report: InsightReport;
  model_versions: Record<string, string>;
  cost_usd: number | null;
  latency_ms: number | null;
}

// GET /api/insights/report/{ticker}/history
export interface InsightHistoryRow {
  id: string;
  as_of: string;
  direction: Direction;
  conviction: Conviction;
  thesis: string;
  cost_usd: number | null;
}

export interface InsightHistoryResponse {
  ticker: string;
  count: number;
  reports: InsightHistoryRow[];
}

// POST /api/insights/report/{ticker}/refresh
export interface RefreshResponse {
  run_id: string;
  ticker: string;
  status: 'queued' | 'running' | 'done' | 'failed';
}

// GET /api/insights/runs/{run_id}
export interface RunStatus {
  id: string;
  ticker: string;
  status: 'queued' | 'running' | 'done' | 'failed';
  trigger: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  report_id: string | null;
}
