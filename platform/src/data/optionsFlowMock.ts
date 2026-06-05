// ─────────────────────────────────────────────────────────────────────────
// MOCK PLACEHOLDER DATA — NOT LIVE.
//
// There is currently NO backend flow-tape / sweeps / live-options-feed
// endpoint in this platform. The Flowseeker tab is built against this typed
// placeholder dataset so the UI can ship ahead of the data pipeline. Replace
// every consumer of this module with a real `/api/options/flow/...` hook once
// a flow-tape endpoint exists, and delete this file.
//
// The FlowseekerTab renders a persistent "Demo data — no live flow feed
// connected" banner so this is never mistaken for real market data.
// ─────────────────────────────────────────────────────────────────────────

export type FlowSide = 'ASK' | 'BID' | 'MID';
export type FlowSentiment = 'BULLISH' | 'BEARISH' | 'NEUTRAL';
export type FlowCP = 'CALL' | 'PUT';
export type ChainSide = 'Ask' | 'Bid' | 'Mid';
export type PremTone = 'gold' | 'brand' | 'default';

export interface FlowRow {
  time: string;
  sym: string;
  strike: number;
  cp: FlowCP;
  otm: number; // percent, +OTM / −ITM
  exp: string;
  dte: number;
  bid: number;
  ask: number;
  mark: number;
  side: FlowSide;
  sent: FlowSentiment;
  size: number;
  chainSide: ChainSide;
  chainPct: number;
  prem: number;
  sweep?: boolean;
  premTone?: PremTone;
}

export interface ScannerBucket {
  id: string;
  label: string;
  count: number;
  prem: number;
  tone: 'brand' | 'bull' | 'warn' | 'gold' | 'default';
}

export interface FlowSentimentSummary {
  bullPrem: number;
  bearPrem: number;
  callPutRatio: number;
  netDelta: string;
}

export interface TopTicker {
  sym: string;
  prem: number;
  dir: 'bull' | 'bear';
  cp: number; // fraction of premium on calls (0..1)
}

export const FLOW_FEED: FlowRow[] = [
  { time: '12:49:25', sym: 'DVN',  strike: 38,   cp: 'CALL', otm: 5.0,  exp: '01/23', dte: 4,  bid: 0.10, ask: 0.13, mark: 0.13, side: 'ASK', sent: 'BULLISH', size: 328,  chainSide: 'Ask', chainPct: 90, prem: 4260,   sweep: true },
  { time: '12:48:30', sym: 'SPY',  strike: 605,  cp: 'CALL', otm: 0.3,  exp: '01/17', dte: 1,  bid: 1.42, ask: 1.45, mark: 1.45, side: 'ASK', sent: 'BULLISH', size: 1000, chainSide: 'Ask', chainPct: 90, prem: 145000, sweep: true,  premTone: 'gold' },
  { time: '12:48:15', sym: 'NVDA', strike: 140,  cp: 'CALL', otm: 1.1,  exp: '01/17', dte: 1,  bid: 2.80, ask: 2.85, mark: 2.85, side: 'ASK', sent: 'BULLISH', size: 500,  chainSide: 'Ask', chainPct: 90, prem: 142500, sweep: true,  premTone: 'brand' },
  { time: '12:39:53', sym: 'TSLA', strike: 430,  cp: 'CALL', otm: 2.4,  exp: '01/24', dte: 9,  bid: 6.05, ask: 6.20, mark: 6.10, side: 'MID', sent: 'NEUTRAL', size: 140,  chainSide: 'Mid', chainPct: 50, prem: 85400,  premTone: 'brand' },
  { time: '12:39:53', sym: 'DVN',  strike: 35.5, cp: 'PUT',  otm: 2.0,  exp: '01/23', dte: 4,  bid: 0.26, ask: 0.30, mark: 0.26, side: 'BID', sent: 'BEARISH', size: 5,    chainSide: 'Bid', chainPct: 50, prem: 130 },
  { time: '12:38:02', sym: 'PLTR', strike: 80,   cp: 'CALL', otm: 1.7,  exp: '01/31', dte: 16, bid: 3.85, ask: 3.90, mark: 3.90, side: 'ASK', sent: 'BULLISH', size: 350,  chainSide: 'Ask', chainPct: 72, prem: 136500, sweep: true,  premTone: 'brand' },
  { time: '12:37:44', sym: 'QQQ',  strike: 612,  cp: 'CALL', otm: 0.3,  exp: '01/17', dte: 1,  bid: 2.05, ask: 2.12, mark: 2.10, side: 'ASK', sent: 'BULLISH', size: 620,  chainSide: 'Ask', chainPct: 88, prem: 130200, sweep: true,  premTone: 'brand' },
  { time: '12:36:18', sym: 'AAPL', strike: 220,  cp: 'PUT',  otm: -0.9, exp: '01/24', dte: 9,  bid: 3.40, ask: 3.55, mark: 3.40, side: 'BID', sent: 'BEARISH', size: 200,  chainSide: 'Bid', chainPct: 64, prem: 68000 },
  { time: '12:35:50', sym: 'META', strike: 700,  cp: 'CALL', otm: 1.2,  exp: '02/21', dte: 37, bid: 12.30,ask: 12.50,mark: 12.40, side: 'MID', sent: 'NEUTRAL', size: 60,   chainSide: 'Mid', chainPct: 50, prem: 74400 },
  { time: '12:34:22', sym: 'AMD',  strike: 175,  cp: 'CALL', otm: 1.5,  exp: '01/24', dte: 9,  bid: 4.15, ask: 4.25, mark: 4.20, side: 'ASK', sent: 'BULLISH', size: 280,  chainSide: 'Ask', chainPct: 76, prem: 117600, premTone: 'brand' },
  { time: '12:33:09', sym: 'INTC', strike: 22,   cp: 'CALL', otm: 1.5,  exp: '01/17', dte: 1,  bid: 0.42, ask: 0.45, mark: 0.45, side: 'ASK', sent: 'BULLISH', size: 2000, chainSide: 'Ask', chainPct: 91, prem: 90000,  sweep: true,  premTone: 'brand' },
  { time: '12:31:55', sym: 'UBER', strike: 70,   cp: 'PUT',  otm: -0.8, exp: '01/17', dte: 1,  bid: 0.95, ask: 1.00, mark: 0.95, side: 'BID', sent: 'BEARISH', size: 800,  chainSide: 'Bid', chainPct: 58, prem: 76000,  premTone: 'brand' },
  { time: '12:30:41', sym: 'XOM',  strike: 110,  cp: 'CALL', otm: 1.0,  exp: '02/21', dte: 37, bid: 3.10, ask: 3.15, mark: 3.15, side: 'ASK', sent: 'BULLISH', size: 220,  chainSide: 'Ask', chainPct: 54, prem: 69300 },
  { time: '12:29:30', sym: 'WMT',  strike: 95,   cp: 'CALL', otm: 0.8,  exp: '01/24', dte: 9,  bid: 2.35, ask: 2.45, mark: 2.40, side: 'MID', sent: 'NEUTRAL', size: 300,  chainSide: 'Mid', chainPct: 50, prem: 72000,  sweep: true },
  { time: '12:28:14', sym: 'MU',   strike: 105,  cp: 'CALL', otm: 1.5,  exp: '01/24', dte: 9,  bid: 4.15, ask: 4.25, mark: 4.20, side: 'MID', sent: 'NEUTRAL', size: 175,  chainSide: 'Mid', chainPct: 50, prem: 73500,  premTone: 'brand' },
  { time: '12:27:02', sym: 'LLY',  strike: 800,  cp: 'CALL', otm: 0.5,  exp: '01/31', dte: 16, bid: 28.30,ask: 28.50,mark: 28.50, side: 'ASK', sent: 'BULLISH', size: 25,   chainSide: 'Ask', chainPct: 47, prem: 71250 },
];

export const SCANNER_BUCKETS: ScannerBucket[] = [
  { id: 'sweeps',   label: 'Sweeps',           count: 142, prem: 18.4e6, tone: 'brand' },
  { id: 'blocks',   label: 'Blocks',           count: 38,  prem: 42.1e6, tone: 'bull' },
  { id: 'splits',   label: 'Splits',           count: 96,  prem: 12.8e6, tone: 'default' },
  { id: 'repeated', label: 'Repeated strikes', count: 28,  prem: 8.2e6,  tone: 'warn' },
  { id: 'golden',   label: 'Golden sweeps',    count: 6,   prem: 24.6e6, tone: 'gold' },
];

export const FLOW_SENTIMENT: FlowSentimentSummary = {
  bullPrem: 142.4e6,
  bearPrem: 48.2e6,
  callPutRatio: 2.34,
  netDelta: '+$1.2B',
};

export const TOP_TICKERS: TopTicker[] = [
  { sym: 'SPY',  prem: 28.4e6, dir: 'bull', cp: 0.78 },
  { sym: 'NVDA', prem: 22.1e6, dir: 'bull', cp: 0.71 },
  { sym: 'TSLA', prem: 14.8e6, dir: 'bear', cp: 0.42 },
  { sym: 'QQQ',  prem: 12.2e6, dir: 'bull', cp: 0.68 },
  { sym: 'PLTR', prem: 9.6e6,  dir: 'bull', cp: 0.82 },
  { sym: 'AAPL', prem: 8.1e6,  dir: 'bear', cp: 0.38 },
];
