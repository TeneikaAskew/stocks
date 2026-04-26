// Types that mirror the deterministic ranker API at
// GET /api/insights/watchlist  →  lib.agents.ranker.rank_tickers(...)

export type CatalystType =
  | 'earnings'
  | 'sec_8k'
  | 'insider'
  | 'top_mover'
  | 'economic_event'
  | 'manual';

export interface SignalContribution {
  name: string;
  available: boolean;
  score_0_to_1: number;
  weight: number;
  points: number;
  reason: string;
  raw: Record<string, unknown>;
}

export interface RankedTicker {
  ticker: string;
  score: number;
  pct_of_max: number;
  catalyst_types: CatalystType[];
  catalyst_metadata: Partial<Record<CatalystType, Record<string, unknown>[]>>;
  score_breakdown: SignalContribution[];
}

export interface WatchlistResponse {
  run_id: string;
  as_of: string;          // ISO timestamp
  candidate_count: number;
  excluded_count: number;
  ranked: RankedTicker[];
  weights_used: Record<string, number>;
  duration_ms: number;
}
