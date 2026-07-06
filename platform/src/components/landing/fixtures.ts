/**
 * MARKETING FIXTURES — a representative sample trading day for the Solyra
 * landing page. These are STATIC illustrations of the product's real visual
 * language (spec §5/§6), NOT live data and NOT performance claims. The proof
 * tile's number IS real: trade-weighted avg_win_rate across the latest
 * selected walk_forward_results combo per ticker (queried 2026-07-05 via
 * db-query: 50% over 2,980 out-of-sample trades, 3 tickers). Re-run that
 * query and update hitRatePct + caption when republishing.
 */
export const AGENT_LINES: { tag: string; text: string }[] = [
  { tag: '', text: '06:58:12 · waking 7 agents for SPY, QQQ, IWM…' },
  { tag: 'brief', text: 'daily bias LONG — full-timeframe continuity 3/4 aligned' },
  { tag: 'gamma', text: 'dealer wall at 592 · flip zone 585 · dealers short gamma' },
  { tag: 'flow', text: '3× sweep clusters on 590C 0DTE, $4.2M premium, ask-side' },
  { tag: 'council', text: 'bull 6.2 / bear 3.8 → verdict: LONG above 588' },
  { tag: 'catalyst', text: 'CPI 8:30a — expect widened range; plan sized at ½R' },
  { tag: '', text: '07:00:00 · your brief is ready. read it →' },
];

export const SPOT_LABEL = 'spot 590.61';

export const GAMMA_LADDER: {
  strike: string; side: 'pos' | 'neg'; pct: number; marker?: 'king' | 'gate' | 'flip';
}[] = [
  { strike: '596', side: 'neg', pct: 18 },
  { strike: '594', side: 'pos', pct: 34 },
  { strike: '592', side: 'pos', pct: 96, marker: 'king' },
  { strike: '591', side: 'pos', pct: 46 },
  { strike: '590', side: 'pos', pct: 40, marker: 'gate' },
  { strike: '589', side: 'neg', pct: 22 },
  { strike: '588', side: 'neg', pct: 64 },
  { strike: '586', side: 'neg', pct: 38 },
  { strike: '585', side: 'neg', pct: 52, marker: 'flip' },
  { strike: '583', side: 'neg', pct: 20 },
];

export const BENTO = {
  verdict: { dir: 'LONG', bullScore: 6.2, bearScore: 3.8 },
  catalysts: [
    { when: '08:30', label: 'CPI', impact: 'HIGH' },
    { when: 'Thu', label: 'NVDA earnings' },
    { when: 'Fri', label: 'OpEx · $2.1T' },
  ],
  movementRead:
    '"SPY held the Gate at 588, reclaimed VWAP on the 10:05 bar, and dealers chased it back toward the King…"',
  signals: [
    { state: 'fired' as const, text: 'fired 10:07 · gate-hold LONG +1.4R' },
    { state: 'armed' as const, text: 'armed · vwap-reclaim' },
    { state: 'armed' as const, text: 'armed · king-reject fade' },
  ],
  proof: {
    hitRatePct: 50 as number | null,
    caption: 'trade-weighted win rate · walk-forward validated · 2,980 out-of-sample trades',
  },
};

/** 24 five-minute candles in SVG y-space (viewBox 0 0 720 280). */
export const CANDLES: {
  bodyTop: number; bodyH: number; wickTop: number; wickBot: number; up: boolean;
}[] = [
  { bodyTop: 225, bodyH: 14, wickTop: 218, wickBot: 246, up: true },
  { bodyTop: 208, bodyH: 17, wickTop: 202, wickBot: 228, up: true },
  { bodyTop: 206, bodyH: 10, wickTop: 198, wickBot: 222, up: false },
  { bodyTop: 188, bodyH: 18, wickTop: 182, wickBot: 212, up: true },
  { bodyTop: 168, bodyH: 16, wickTop: 162, wickBot: 192, up: true },
  { bodyTop: 148, bodyH: 18, wickTop: 142, wickBot: 172, up: true },
  { bodyTop: 150, bodyH: 12, wickTop: 140, wickBot: 168, up: false },
  { bodyTop: 128, bodyH: 20, wickTop: 122, wickBot: 152, up: true },
  { bodyTop: 106, bodyH: 20, wickTop: 100, wickBot: 130, up: true },
  { bodyTop: 88, bodyH: 16, wickTop: 82, wickBot: 110, up: true },
  { bodyTop: 74, bodyH: 12, wickTop: 50, wickBot: 92, up: true },
  { bodyTop: 76, bodyH: 16, wickTop: 48, wickBot: 96, up: false },
  { bodyTop: 94, bodyH: 18, wickTop: 88, wickBot: 118, up: false },
  { bodyTop: 114, bodyH: 18, wickTop: 108, wickBot: 138, up: false },
  { bodyTop: 112, bodyH: 12, wickTop: 104, wickBot: 132, up: true },
  { bodyTop: 122, bodyH: 22, wickTop: 116, wickBot: 158, up: false },
  { bodyTop: 144, bodyH: 16, wickTop: 138, wickBot: 166, up: false },
  { bodyTop: 150, bodyH: 10, wickTop: 144, wickBot: 170, up: true },
  { bodyTop: 152, bodyH: 10, wickTop: 146, wickBot: 176, up: false },
  { bodyTop: 138, bodyH: 16, wickTop: 132, wickBot: 162, up: true },
  { bodyTop: 118, bodyH: 18, wickTop: 112, wickBot: 142, up: true },
  { bodyTop: 100, bodyH: 16, wickTop: 94, wickBot: 124, up: true },
  { bodyTop: 84, bodyH: 14, wickTop: 78, wickBot: 108, up: true },
  { bodyTop: 72, bodyH: 10, wickTop: 64, wickBot: 94, up: true },
];

export const HEAT_ROWS: {
  strike: string; kind: 'pos' | 'neg'; alphas: number[]; marker?: 'king' | 'spot' | 'flip';
}[] = [
  { strike: '596', kind: 'pos', alphas: [0.25, 0.35, 0.2, 0.15, 0.25, 0.12, 0.1] },
  { strike: '592', kind: 'pos', alphas: [0.85, 0.6, 0.45, 0.3, 0.45, 0.22, 0.15], marker: 'king' },
  { strike: '590', kind: 'pos', alphas: [0.4, 0.5, 0.3, 0.22, 0.15, 0.25, 0.1], marker: 'spot' },
  { strike: '588', kind: 'neg', alphas: [0.55, 0.4, 0.48, 0.25, 0.32, 0.18, 0.12] },
  { strike: '585', kind: 'neg', alphas: [0.5, 0.35, 0.42, 0.28, 0.2, 0.24, 0.12], marker: 'flip' },
  { strike: '583', kind: 'neg', alphas: [0.3, 0.22, 0.26, 0.15, 0.18, 0.12, 0.08] },
];

export const HEAT_EXPIRIES = ['0DTE', '1d', '2d', '1w', '2w', '3w', '30d'];

export const FLOW_ROWS: {
  time: string; contract: string; size: string; prem: string;
  side: 'ask' | 'bid'; sideLabel: string; read: string; flag?: boolean;
}[] = [
  { time: '10:06:52', contract: 'SPY 590C 0DTE', size: '2,400', prem: '$1.9M', side: 'ask', sideLabel: 'ASK sweep', read: '⚑ cluster 3/3', flag: true },
  { time: '10:06:41', contract: 'SPY 590C 0DTE', size: '1,850', prem: '$1.4M', side: 'ask', sideLabel: 'ASK sweep', read: 'cluster 2/3' },
  { time: '10:05:58', contract: 'QQQ 512C 2d', size: '900', prem: '$0.8M', side: 'ask', sideLabel: 'ASK', read: '—' },
  { time: '10:05:13', contract: 'SPY 585P 0DTE', size: '3,100', prem: '$0.9M', side: 'bid', sideLabel: 'BID (closing)', read: 'puts sold ↓' },
  { time: '10:04:47', contract: 'IWM 218C 1w', size: '1,200', prem: '$0.5M', side: 'ask', sideLabel: 'ASK', read: '—' },
];

export const COUNCIL = {
  bull: { score: 6.2, quote: '"Timeframes aligned long, dealers short gamma above 588 — rallies get chased, not sold."' },
  bear: { score: 3.8, quote: '"CPI at 8:30 can flip the tape; RSI is stretched into the King."' },
  verdict: 'LONG above 588 · target 592 · invalidated below 585 · half size until CPI prints',
  personas: ['scalper plan', 'swing plan', 'income plan'],
};

export const RHYTHM = [
  {
    time: '07:00', phase: 'LEARN', title: 'The Brief',
    body: `Bias, the three levels that matter, today’s catalysts, and the setup the playbook likes — in plain language, with every term one tap from its glossary definition. Five minutes, coffee in hand.`,
  },
  {
    time: '09:30', phase: 'DO', title: 'The open — signals live',
    body: 'Agents watch every 1-minute bar. When a playbook setup triggers, you get the alert with entry, target, stop, and the win rate that earned it a place in the book. No chart-staring required.',
  },
  {
    time: '16:00', phase: 'ACT', title: 'The close — review & compound',
    body: `Movement Read explains the day in one paragraph. Your journal auto-grades the signals you took against the ones you skipped. Tomorrow’s you starts smarter.`,
  },
];

export const FAQ = [
  {
    q: 'Is this financial advice?',
    a: `No — Solyra is an analytics and education platform. It shows you what’s happening and what has historically followed; decisions stay yours.`,
  },
  {
    q: 'Do I need options experience?',
    a: 'No. Every brief links each concept to a plain-language explainer. Learn is a first-class module, not a help page.',
  },
  {
    q: 'Where does the data come from?',
    a: 'Institutional options chains, 1-minute market data, and a validated signal engine — every signal graded daily against reality.',
  },
];
