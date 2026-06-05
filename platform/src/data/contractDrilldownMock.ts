// ─────────────────────────────────────────────────────────────────────────
// MOCK PLACEHOLDER DATA — NOT LIVE. Real source TBD.
//
// Flowseeker "Contract Drilldown" needs per-contract intraday tape: a stats
// strip, a bid/ask chain-ratio split, volume-over-time bars with an overlaid
// average-fill line, and a Bid/Mid/Ask/No-Side time-bucket breakdown. There is
// NO backend contract-tape endpoint today, so this typed mock drives the view.
// The drilldown renders a persistent "Demo data" banner so this is never
// mistaken for live market data. Replace with a real
// `/api/options/contract/{id}/tape` hook once it exists, and delete this file.
// ─────────────────────────────────────────────────────────────────────────

export interface ContractHeader {
  sym: string;
  strike: number;
  cp: 'CALL' | 'PUT';
  expiry: string; // ISO date
  dte: number;
}

export interface ContractStats {
  volume: number;
  openInterest: number;
  avgFill: number;
  totalPremium: number;
  otmPct: number;
  multiPct: number; // % of volume in multi-leg / sweep prints
}

export interface ChainRatio {
  bidPct: number; // 0..100
  askPct: number; // 0..100 (bid+ask need not sum to 100; remainder = mid)
  bidPremium: number;
  askPremium: number;
}

export interface TimeBucket {
  time: string; // HH:MM
  bidCount: number;
  midCount: number;
  askCount: number;
  noSideCount: number;
  avgFill: number;
  iv: number; // implied vol, fraction
  rvol: number; // relative volume multiple
  volume: number;
  bidPremium: number;
  midPremium: number;
  askPremium: number;
  price: number; // contract price at bucket (for the overlaid line)
}

export interface ContractDrilldown {
  header: ContractHeader;
  stats: ContractStats;
  chainRatio: ChainRatio;
  buckets: TimeBucket[];
}

// SPY 605C — a representative liquid 0–1 DTE contract from the Flowseeker tape.
export const CONTRACT_DRILLDOWN: ContractDrilldown = {
  header: { sym: 'SPY', strike: 605, cp: 'CALL', expiry: '2026-01-17', dte: 1 },
  stats: {
    volume: 48_213,
    openInterest: 31_905,
    avgFill: 1.42,
    totalPremium: 6_846_246,
    otmPct: 0.3,
    multiPct: 34,
  },
  chainRatio: {
    bidPct: 28,
    askPct: 62,
    bidPremium: 1_916_949,
    askPremium: 4_244_672,
  },
  buckets: [
    { time: '09:30', bidCount: 18, midCount: 22, askCount: 61, noSideCount: 4, avgFill: 1.21, iv: 0.142, rvol: 2.4, volume: 5210, bidPremium: 138_000, midPremium: 196_000, askPremium: 642_000, price: 1.24 },
    { time: '10:00', bidCount: 24, midCount: 19, askCount: 48, noSideCount: 6, avgFill: 1.28, iv: 0.138, rvol: 1.9, volume: 4380, bidPremium: 162_000, midPremium: 154_000, askPremium: 521_000, price: 1.29 },
    { time: '10:30', bidCount: 31, midCount: 26, askCount: 39, noSideCount: 8, avgFill: 1.33, iv: 0.135, rvol: 1.5, volume: 3620, bidPremium: 201_000, midPremium: 188_000, askPremium: 402_000, price: 1.31 },
    { time: '11:00', bidCount: 27, midCount: 21, askCount: 52, noSideCount: 5, avgFill: 1.38, iv: 0.133, rvol: 1.7, volume: 4015, bidPremium: 174_000, midPremium: 161_000, askPremium: 488_000, price: 1.37 },
    { time: '11:30', bidCount: 19, midCount: 24, askCount: 58, noSideCount: 3, avgFill: 1.41, iv: 0.131, rvol: 1.6, volume: 3890, bidPremium: 138_000, midPremium: 182_000, askPremium: 502_000, price: 1.40 },
    { time: '12:00', bidCount: 22, midCount: 18, askCount: 44, noSideCount: 7, avgFill: 1.44, iv: 0.129, rvol: 1.3, volume: 3120, bidPremium: 151_000, midPremium: 132_000, askPremium: 398_000, price: 1.43 },
    { time: '12:30', bidCount: 16, midCount: 20, askCount: 66, noSideCount: 4, avgFill: 1.46, iv: 0.128, rvol: 2.1, volume: 4720, bidPremium: 121_000, midPremium: 158_000, askPremium: 612_000, price: 1.45 },
    { time: '13:00', bidCount: 29, midCount: 23, askCount: 41, noSideCount: 6, avgFill: 1.43, iv: 0.130, rvol: 1.4, volume: 3340, bidPremium: 188_000, midPremium: 171_000, askPremium: 392_000, price: 1.42 },
    { time: '13:30', bidCount: 33, midCount: 25, askCount: 36, noSideCount: 9, avgFill: 1.39, iv: 0.132, rvol: 1.2, volume: 2980, bidPremium: 214_000, midPremium: 182_000, askPremium: 348_000, price: 1.38 },
    { time: '14:00', bidCount: 21, midCount: 19, askCount: 55, noSideCount: 5, avgFill: 1.45, iv: 0.131, rvol: 1.8, volume: 4180, bidPremium: 149_000, midPremium: 142_000, askPremium: 528_000, price: 1.44 },
    { time: '14:30', bidCount: 17, midCount: 22, askCount: 63, noSideCount: 4, avgFill: 1.49, iv: 0.130, rvol: 2.2, volume: 4910, bidPremium: 126_000, midPremium: 168_000, askPremium: 642_000, price: 1.48 },
    { time: '15:00', bidCount: 14, midCount: 18, askCount: 71, noSideCount: 3, avgFill: 1.53, iv: 0.129, rvol: 2.6, volume: 5640, bidPremium: 108_000, midPremium: 142_000, askPremium: 738_000, price: 1.52 },
    { time: '15:30', bidCount: 12, midCount: 16, askCount: 78, noSideCount: 2, avgFill: 1.58, iv: 0.127, rvol: 3.1, volume: 6210, bidPremium: 96_000, midPremium: 128_000, askPremium: 812_000, price: 1.57 },
    { time: '16:00', bidCount: 9, midCount: 13, askCount: 69, noSideCount: 2, avgFill: 1.55, iv: 0.126, rvol: 1.9, volume: 4090, bidPremium: 72_000, midPremium: 104_000, askPremium: 561_000, price: 1.54 },
  ],
};
