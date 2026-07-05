export type Ticker = 'IWM' | 'SPY' | 'QQQ';

export type Timeframe = '1' | '5' | '15' | '30' | '60';

export type TradeDirection = 'CALL' | 'PUT';

export interface OHLCV {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface TradeEntry {
  id: string;
  ticker: Ticker;
  optionType: TradeDirection;
  entryTime: number;
  entryPrice: number;
  exitTime?: number;
  exitPrice?: number;
  stopLoss?: { price: number };
  takeProfits: { price: number; size: number }[];
  notes: string;
  tags: string[];
  status: 'active' | 'win' | 'loss' | 'breakeven';
  pnl?: number;
  pnlPercent?: number;
  createdAt: number;
}

export interface Signal {
  time: string;
  direction: TradeDirection;
  score: number;
  indicators: Record<string, number>;
}

export interface BacktestResult {
  entry_time: string;
  exit_time: string;
  direction: TradeDirection;
  entry_price: number;
  exit_price: number;
  exit_reason: string;
  return_pct: number;
  base_score: number;
}

export interface PlaybookCard {
  id: string;
  ticker: Ticker;
  name: string;
  conditions: { label: string; met: boolean }[];
  entryRules: string[];
  warnings: string[];
  winRate: number;
  avgReturn: number;
}

export interface MetricCardData {
  label: string;
  value: string | number;
  direction?: 'up' | 'down' | 'neutral';
  subtitle?: string;
  /** @deprecated Use direction instead */
  change?: number;
  changeLabel?: string;
  /** Accent tone for a subtle left-border highlight. Defaults to neutral (no accent). */
  tone?: 'default' | 'brand' | 'bull' | 'bear' | 'warn';
}

// ---------------------------------------------------------------------------
// Movement Statement — PHASE 3 of the movement-statement build plan.
//
// Mirrors the shape produced by lib/movement_statement.py
// (assemble_movement_statement). The frontend RENDERS this output and
// recomputes nothing — ALL math (headline probability, reach-rates,
// modifiers) lives in the Python backend (one source of truth).
//
// Every nested block carries a `status` discriminator. Per CLAUDE.md
// Rule 3.7, an UNAVAILABLE block has NO fabricated value: the display
// layer renders "—" + a "data unavailable" badge from the status, never
// a synthetic number. `status` is widened to `string` (not a literal
// union) so an unexpected backend status can still render the
// unavailable state rather than break type-narrowing.
// ---------------------------------------------------------------------------

/** Generic per-field envelope discriminator. */
export type MovementFieldStatus = 'OK' | 'UNAVAILABLE' | string;

/** Population reach-rate for a single levels-to-go tier. */
export interface ReachRate {
  status: MovementFieldStatus;
  reason?: string | null;
  /** Fraction of triggered+resolved instances that reached this tier. */
  reach_rate?: number | null;
  hits?: number | null;
  sample_n?: number | null;
  /** True when sample_n is below the low-sample threshold. */
  low_sample?: boolean | null;
}

/** One rung of the levels-to-go ladder with its annotated reach-rate. */
export interface MovementLevelEntry {
  price?: number | null;
  name?: string | null;
  period?: string | null;
  level_type?: string | null;
  distance_pct?: number | null;
  reach_rate: ReachRate;
}

/** The levels block — calls/puts ladders, each with per-tier reach-rates. */
export interface MovementLevels {
  status: MovementFieldStatus;
  reason?: string | null;
  calls?: MovementLevelEntry[];
  puts?: MovementLevelEntry[];
  current_price?: number | null;
  reach_rate_note?: string | null;
}

/** The headline — the calibrated continuation probability ONLY. */
export interface MovementHeadline {
  status: MovementFieldStatus;
  current_type?: string | null;
  /** The ONLY load-bearing probability — equals continuation_prob. */
  probability?: number | null;
  probability_source?: string | null;
  timeframe?: string | null;
  /** Human-readable one-liner (candle type + continuation %). */
  statement?: string | null;
  reason?: string | null;
}

/** Expected-move (magnitude) modifier — CONTEXT / sizing only. */
export interface MovementExpectedMove {
  status: MovementFieldStatus;
  reason?: string | null;
  role?: string | null;
  size_class?: string | null;
  pred_bucket?: number | null;
  probabilities?: {
    p_tight: number; p_normal: number; p_expanded: number; p_explosive: number;
  } | null;
  max_proba?: number | null;
  model_version?: string | null;
  ts?: string | null;
  usage_guidance?: string | null;
}

/** Gamma regime modifier — CONTEXT only (pinning vs trending). */
export interface MovementRegime {
  status: MovementFieldStatus;
  reason?: string | null;
  role?: string | null;
  regime?: string | null;
  mood?: string | null;
  gamma_flip?: number | null;
  total_gex?: number | null;
  data_source?: string | null;
  snapshot_ts?: string | null;
}

/** The context block — modifiers that MUST NOT move the headline. */
export interface MovementConfidenceModifiers {
  note: string;
  expected_move: MovementExpectedMove;
  regime: MovementRegime;
}

/** Full continuation envelope (transparency / debugging). */
export interface MovementContinuation {
  status: MovementFieldStatus;
  current_type?: string | null;
  continuation_prob?: number | null;
  timeframe?: string | null;
  reason?: string | null;
  [key: string]: unknown;
}

/** The assembled movement statement returned by GET /api/movement-statement. */
export interface MovementStatement {
  status: MovementFieldStatus;
  ticker: string;
  timeframe: string;
  as_of?: string | null;
  scope_statement: string;
  headline: MovementHeadline;
  continuation: MovementContinuation;
  levels: MovementLevels;
  confidence_modifiers: MovementConfidenceModifiers;
}
