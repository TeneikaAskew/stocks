// Heatseeker dealer-gamma mock — typed TS port of the design's heatseeker-data.js.
//
// This is the data backbone for the SwingMode "dealer-gamma cockpit". There is
// NO per-expiration dealer-exposure backend endpoint, so the 2D Strike ×
// Expiration grid, tactical read, drill-in detail and pivot-build all come from
// this clearly-labeled mock. The Legend chips + NodeList can be overlaid with
// real values from /api/options/{ticker}/{date}/levels (see SwingMode).
//
// DETERMINISTIC by construction — the per-expiration `detail` rows are derived
// from the GEX/VEX/ROC grids with an index-based pseudo-noise (NO Math.random,
// NO Date.now at module scope) so builds and snapshots stay stable.

export type SpotMethod = 'parity' | 'delta' | 'median';
export type DataSource = 'realtime' | 'eod_fallback' | 'stale_fallback' | 'unavailable';
export type NodeRole = 'king' | 'gate' | 'spot' | 'flip' | 'midpoint' | 'hedge' | 'opex';

export interface HSSpot {
  price: number;
  method: SpotMethod;
  note: string;
}

export interface HSExpiration {
  iso: string;
  label: string;
  dte: number;
  tags: string[];
}

export interface HSCollapsed {
  strike: number;
  role: NodeRole | null;
  netGex: number;
  callOi: number;
  putOi: number;
  pull: number;
  pullDir: 'up' | 'dn';
}

export interface HSKing {
  strike: number;
  gex: number;
  callOi: number;
  putOi: number;
  distancePct: number;
  dominantSide: string;
}
export interface HSGate {
  strike: number;
  side: 'above' | 'below';
  gex: number;
  distancePct: number;
  dominantSide: string;
}
export interface HSSimpleNode {
  strike: number;
  gex: number;
  distancePct: number;
}
export interface HSHedge {
  strike: number;
  gex: number;
  distancePct: number;
  linkedEvent: string;
  persistenceDays: number;
}
export interface HSOpexNode {
  strike: number;
  expIso: string;
  dte: number;
  gex: number;
}

export interface HSNodes {
  king: HSKing;
  gates: HSGate[];
  spot: { strike: number; gex: number; distancePct: number };
  flip: HSSimpleNode;
  midpoints: HSSimpleNode[];
  hedge: HSHedge[];
  opex: HSOpexNode[];
}

export interface HSTactical {
  currentState: string;
  longSetup: string;
  shortSetup: string;
  invalidation: string;
  vexNote: string;
  confidence: number;
}

export interface HSGlossaryTerm {
  name: string;
  short: string;
  long?: string;
  math?: string;
}

export interface HSDetailRow {
  strike: number;
  gex: number;
  vex: number;
  roc: number;
  callOi: number;
  putOi: number;
  callVol: number;
  putVol: number;
  totalVol: number;
  iv: number;
  ivRank: number;
  netOi: number;
  pcVolRatio: number;
  pcOiRatio: number;
}

export interface HeatseekerData {
  ticker: string;
  asOf: string;
  dataSource: DataSource;
  regime: string;
  spot: HSSpot;
  flip: number;
  totalGex: number;
  totalVex: number;
  totalGexPctChg1h: number;
  totalVexPctChg1h: number;
  strikes: number[];
  expirations: HSExpiration[];
  gexGrid: number[][];
  vexGrid: number[][];
  rocGrid: number[][];
  collapsed: HSCollapsed[];
  nodes: HSNodes;
  tactical: HSTactical;
  glossary: Record<string, HSGlossaryTerm>;
  detail: Record<string, HSDetailRow[]>;
}

const ticker = 'SPY';

const strikes = [605, 602, 600, 598, 596, 595, 594, 593, 591, 589, 588, 587, 585, 580];

const expirations: HSExpiration[] = [
  { iso: '2026-05-23', label: '0DTE', dte: 0, tags: ['0dte'] },
  { iso: '2026-05-24', label: '1DTE', dte: 1, tags: [] },
  { iso: '2026-05-30', label: 'Wk', dte: 7, tags: ['weekly'] },
  { iso: '2026-06-06', label: 'Wk+1', dte: 14, tags: ['weekly'] },
  { iso: '2026-06-20', label: 'OPEX', dte: 28, tags: ['monthly', 'opex'] },
  { iso: '2026-07-18', label: 'Mo', dte: 56, tags: ['monthly'] },
  { iso: '2026-09-19', label: 'Q', dte: 119, tags: ['quarterly'] },
];

// GEX grid ($K dealer GEX per 1% spot move). rows=strikes high→low, cols=exps short→long
const gexGrid: number[][] = [
  [84, 54, 42, 28, 60, 22, 6], // 605
  [140, 92, 72, 54, 150, 38, 10], // 602
  [680, 340, 220, 120, 240, 88, 28], // 600
  [90, 60, 42, 28, 78, 24, 8], // 598
  [220, 140, 120, 84, 220, 60, 18], // 596
  [240, 160, 120, 88, 200, 58, 16], // 595
  [280, 180, 140, 100, 220, 62, 18], // 594
  [580, 340, 220, 130, 280, 90, 24], // 593 *spot
  [120, 80, 62, 42, 88, 32, 10], // 591
  [90, 60, 48, 32, 72, 24, 8], // 589
  [-30, -20, -16, -12, -20, -8, -4], // 588 *flip
  [-240, -180, -120, -90, -180, -60, -18], // 587
  [-20, -16, -14, -10, -18, -8, -4], // 585
  [-180, -120, -160, -90, -160, -90, -30], // 580 *hedge
];

const vexGrid: number[][] = [
  [8, 6, 8, 6, 14, 4, 2],
  [16, 12, 18, 14, 28, 10, 4],
  [42, 28, 48, 32, 60, 18, 8],
  [10, 8, 12, 8, 16, 6, 2],
  [28, 20, 34, 22, 42, 14, 4],
  [24, 18, 32, 20, 38, 12, 4],
  [28, 20, 36, 22, 42, 14, 4],
  [38, 28, 42, 28, 52, 18, 6],
  [10, 8, 16, 10, 20, 6, 2],
  [8, 6, 12, 8, 16, 5, 2],
  [-4, -2, -6, -3, -6, -2, -1],
  [-18, -14, -22, -16, -28, -8, -3],
  [-2, -2, -4, -2, -5, -2, -1],
  [-12, -8, -16, -10, -22, -8, -3],
];

const rocGrid: number[][] = [
  [8, 4, 2, 1, 3, 1, 0],
  [14, 8, 6, 4, 12, 3, 1],
  [86, 42, 28, 14, 32, 10, 4],
  [10, 6, 4, 2, 8, 3, 1],
  [18, 12, 10, 7, 20, 6, 2],
  [20, 14, 12, 8, 18, 6, 2],
  [28, 18, 14, 10, 22, 7, 2],
  [142, 72, 38, 18, 42, 14, 4],
  [8, 4, 2, 1, 4, 1, 0],
  [4, 2, 1, 1, 3, 1, 0],
  [-3, -2, -1, -1, -2, 0, 0],
  [-88, -42, -22, -12, -28, -8, -3],
  [-6, -4, -3, -2, -4, -2, -1],
  [14, 8, 12, 8, 20, 8, 3],
];

const collapsed: HSCollapsed[] = [
  { strike: 605, role: null, netGex: 159000, callOi: 1043, putOi: 31, pull: 1, pullDir: 'up' },
  { strike: 602, role: null, netGex: 750000, callOi: 3210, putOi: 8, pull: 2, pullDir: 'up' },
  { strike: 600, role: 'king', netGex: 1400000, callOi: 14420, putOi: 1010, pull: 3, pullDir: 'up' },
  { strike: 598, role: null, netGex: 201000, callOi: 837, putOi: 225, pull: 1, pullDir: 'up' },
  { strike: 596, role: null, netGex: 542000, callOi: 2240, putOi: 119, pull: 2, pullDir: 'up' },
  { strike: 595, role: null, netGex: 600000, callOi: 3010, putOi: 59, pull: 2, pullDir: 'up' },
  { strike: 594, role: 'gate', netGex: 726000, callOi: 2120, putOi: 105, pull: 3, pullDir: 'up' },
  { strike: 593, role: 'spot', netGex: 1200000, callOi: 16200, putOi: 4080, pull: 4, pullDir: 'up' },
  { strike: 591, role: 'midpoint', netGex: 273000, callOi: 2150, putOi: 2010, pull: 1, pullDir: 'up' },
  { strike: 589, role: 'gate', netGex: 689000, callOi: 5210, putOi: 2025, pull: 2, pullDir: 'up' },
  { strike: 588, role: 'flip', netGex: -77000, callOi: 401, putOi: 938, pull: 0, pullDir: 'dn' },
  { strike: 587, role: null, netGex: -629000, callOi: 13420, putOi: 16020, pull: 3, pullDir: 'dn' },
  { strike: 585, role: null, netGex: -42000, callOi: 122, putOi: 725, pull: 1, pullDir: 'dn' },
  { strike: 580, role: 'hedge', netGex: -880000, callOi: 4220, putOi: 21400, pull: 2, pullDir: 'dn' },
];

const nodes: HSNodes = {
  king: { strike: 600, gex: 1.4e9, callOi: 14420, putOi: 1010, distancePct: 1.1, dominantSide: 'call' },
  gates: [
    { strike: 594, side: 'above', gex: 726000e3, distancePct: 0.1, dominantSide: 'call' },
    { strike: 589, side: 'below', gex: 689000e3, distancePct: -0.74, dominantSide: 'call' },
  ],
  spot: { strike: 593, gex: 1.2e9, distancePct: 0.0 },
  flip: { strike: 588.5, gex: -77000e3, distancePct: -0.83 },
  midpoints: [{ strike: 591, gex: 273000e3, distancePct: -0.41 }],
  hedge: [
    { strike: 580, gex: -880000e3, distancePct: -2.26, linkedEvent: 'FOMC 2026-06-12', persistenceDays: 4 },
  ],
  opex: [
    { strike: 600, expIso: '2026-06-20', dte: 28, gex: 240e6 },
    { strike: 593, expIso: '2026-06-20', dte: 28, gex: 280e6 },
  ],
};

const tactical: HSTactical = {
  currentState:
    'Pinning between Flip 588.50 and Anchor 600. Spot 593.42 holding above Gate 589 with rising Δ GEX in the 0–7DTE band.',
  longSetup:
    'Reclaim Gate 594 → target Anchor 600. Stop tight under Spot 593 — invalid if 5m closes below 593.',
  shortSetup:
    'Fade Anchor 600 / fail at Gate 594 → target Flip 588.50. Add on break with target Trigger 587 (largest negative GEX).',
  invalidation:
    'Close below 588 = Flip lost; regime risk shifts to trending. Expect Trigger 587 break and trend to Hedge 580.',
  vexNote:
    'VEX is mildly negative ($–84M total); a 2% IV crush implies dealer-sell pressure of ~$1.7M / 1% drop.',
  confidence: 72,
};

export const glossary: Record<string, HSGlossaryTerm> = {
  king: {
    name: 'King',
    short: 'Strike where |Net GEX| ≥ 50% of max in window — primary dealer magnet / pin.',
    long: 'First touches of a King react ~80% of the time in positive gamma regime.',
    math: 'Σ (call_gamma×call_oi − put_gamma×put_oi) × spot² · max in window',
  },
  gate: {
    name: 'Gate',
    short: 'Secondary high-|GEX| strike (≥20% of max) between current spot and the King — must break before price can reach the King.',
    long: 'Failed test of a Gate frequently precedes a trend shift; persistent rejection is a continuation signal.',
  },
  spot: {
    name: 'Spot',
    short: 'The strike row currently inhabited by price (within 0.2%).',
    long: 'Tagged when within 0.2% of estimated underlying spot.',
  },
  flip: {
    name: 'Flip',
    short: 'Cumulative GEX zero crossing nearest spot. Above = positive gamma regime (pinning, low vol). Below = negative gamma regime (trending, high vol).',
    long: 'Critical regime divider. Crossing the Flip changes dealer hedging mechanics and expected intraday range.',
  },
  midpoint: {
    name: 'Midpoint',
    short: 'Range middle — historically worst R:R as MMs trap orders in both directions.',
    long: 'Often the chop zone where intraday counter-trend trades go to die. Better to wait for Gate or Spot.',
  },
  hedge: {
    name: 'Hedge',
    short: 'Far-from-spot persistent node tied to a macro event (FOMC, CPI, NFP). Insurance, not magnet.',
    long: 'Hedge nodes unwind slowly across multiple sessions as the event passes; intraday traders can ignore them.',
  },
  opex: {
    name: 'OPEX',
    short: 'Strike tied to third-Friday monthly expiration. Loses weight as contracts expire.',
    long: 'Monthly OI concentration; gravitational pull is strongest in the final week before OPEX.',
  },
  gex: {
    name: 'GEX',
    short: 'Gamma Exposure. Dollar dealer-hedge flow per 1% spot move.',
    math: 'Σ (γ × OI × spot² × 100), dealer perspective',
  },
  vex: {
    name: 'VEX',
    short: 'Vanna Exposure. Dollar dealer-hedge flow per 1% change in implied volatility.',
    long: 'Critical on event days when IV crushes (FOMC, CPI). Positive VEX = dealer-buying on vol crush.',
    math: 'Σ (ν × OI × spot × 100), dealer perspective',
  },
  pull: {
    name: 'Pull',
    short: 'Composite magnetism — combination of |GEX|, OI density, and proximity to spot.',
  },
  parity: {
    name: 'Spot method: parity',
    short: 'Put-call parity at smallest |C−P| pair on the nearest expiration. Most accurate.',
  },
  delta: {
    name: 'Spot method: delta proxy',
    short: 'Strike of the call whose |delta| is closest to 0.5. Fragile if delta is missing.',
  },
  median: {
    name: 'Spot method: median strike',
    short: 'Last resort — chain too thin to derive spot. Treat the chart with caution.',
  },
};

const spot: HSSpot = { price: 593.42, method: 'parity', note: 'K=593 nearest |C−P| pair, exp 2026-05-23' };

// Deterministic [0,1) pseudo-noise from two integer indices. Replaces Math.random
// so the detail rows are stable across builds/snapshots. Hash-based, no module-scope
// non-determinism.
function noise(a: number, b: number): number {
  const h = Math.sin(a * 127.1 + b * 311.7 + 13.37) * 43758.5453;
  return h - Math.floor(h);
}

// Per-strike, per-expiration detail rows. Each row is the contributing slice for
// that expiration, derived from the grids with deterministic secondary metrics.
function buildDetail(): Record<string, HSDetailRow[]> {
  const out: Record<string, HSDetailRow[]> = {};
  expirations.forEach((exp, ei) => {
    out[exp.iso] = strikes.map((k, si) => {
      const gex = gexGrid[si][ei];
      const vex = vexGrid[si][ei];
      const roc = rocGrid[si][ei];
      const absG = Math.abs(gex);
      const callBias = gex >= 0 ? 1 : 0.25;
      const putBias = gex >= 0 ? 0.25 : 1;
      const callOi = Math.round(absG * 14 * callBias + noise(si, ei) * 80);
      const putOi = Math.round(absG * 14 * putBias + noise(si + 7, ei + 3) * 80);
      const callVol = Math.round(callOi * (0.18 + noise(si + 11, ei + 5) * 0.45));
      const putVol = Math.round(putOi * (0.18 + noise(si + 17, ei + 9) * 0.45));
      const distFromSpot = Math.abs(k - spot.price);
      const iv = +(11 + distFromSpot * 0.4 + (28 - exp.dte) * 0.08 + (gex < 0 ? 1.5 : 0)).toFixed(1);
      const ivRank = Math.min(100, Math.round(iv * 3.2 + (k === Math.round(spot.price) ? 8 : 0)));
      return {
        strike: k,
        gex,
        vex,
        roc,
        callOi,
        putOi,
        callVol,
        putVol,
        totalVol: callVol + putVol,
        iv,
        ivRank,
        netOi: callOi - putOi,
        pcVolRatio: +(putVol / Math.max(1, callVol)).toFixed(2),
        pcOiRatio: +(putOi / Math.max(1, callOi)).toFixed(2),
      };
    });
  });
  return out;
}

export const HS: HeatseekerData = {
  ticker,
  asOf: '2026-05-23T15:55:00-04:00',
  dataSource: 'realtime',
  regime: 'positive_gamma',
  spot,
  flip: 588.5,
  totalGex: 4.2e9,
  totalVex: -8.4e7,
  totalGexPctChg1h: 12.4,
  totalVexPctChg1h: -4.2,
  strikes,
  expirations,
  gexGrid,
  vexGrid,
  rocGrid,
  collapsed,
  nodes,
  tactical,
  glossary,
  detail: buildDetail(),
};
