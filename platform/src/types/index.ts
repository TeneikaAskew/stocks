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
}
