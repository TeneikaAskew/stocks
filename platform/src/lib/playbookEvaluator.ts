import type { Bar, Indicators } from './indicators';

// ---------------------------------------------------------------------------
// This file used to host a regex-based condition evaluator. That logic lives
// in platform/api/routers/playbook.py now — the app just builds a snapshot
// and the server evaluates. See usePlaybookEvaluation / usePlaybookBatch in
// platform/src/hooks/usePlaybookEvaluation.ts.
// ---------------------------------------------------------------------------

/**
 * Snapshot of live market state sent to POST /api/playbook/evaluate.
 * Values may be null when the market is closed or history is thin.
 */
export interface MarketSnapshot {
  price: number | null;
  prevClose: number | null;
  prevHigh: number | null;
  prevLow: number | null;
  volumeToday: number | null;
  avgVolume20d: number | null;
  orbHigh: number | null;
  orbLow: number | null;
  lastBar: Bar | null;
  minutesSinceOpen: number | null;
  stochKPrev: number | null;
  indicators: Indicators;
}

export type EvalResult =
  | { status: 'met'; detail: string }
  | { status: 'unmet'; detail: string }
  | { status: 'unknown'; reason: string };

/** Compute ORB high/low (first 30 min of RTH) from intraday bars. */
export function computeORB(bars: Bar[]): { high: number | null; low: number | null } {
  if (bars.length === 0) return { high: null, low: null };
  const orbBars = bars.filter((b) => {
    const m = b.time.match(/\b(\d{2}):(\d{2}):/);
    if (!m) return false;
    const h = Number(m[1]);
    const min = Number(m[2]);
    const t = h * 60 + min;
    // RTH opens at 09:30; ORB window is the first 30 min.
    return t >= 9 * 60 + 30 && t < 10 * 60;
  });
  if (orbBars.length === 0) return { high: null, low: null };
  return {
    high: Math.max(...orbBars.map((b) => b.high)),
    low: Math.min(...orbBars.map((b) => b.low)),
  };
}

/** Minutes since 09:30 ET for the latest bar. Null if bars empty or pre-market. */
export function minutesSinceOpen(lastBar: Bar | null): number | null {
  if (!lastBar) return null;
  const m = lastBar.time.match(/\b(\d{2}):(\d{2}):/);
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  const t = h * 60 + min;
  const openMin = 9 * 60 + 30;
  if (t < openMin) return null;
  return t - openMin;
}

/**
 * Assemble a MarketSnapshot from the live data hooks. Pure data-shaping —
 * no math is done here; see usePlaybookEvaluation for condition checks.
 */
export function buildSnapshot(params: {
  bars: Bar[] | undefined;
  quote: { price?: number | null; volume?: number | null } | undefined;
  avgVolume20d: number | null | undefined;
  reference: { high?: number | null; low?: number | null; close?: number | null } | undefined;
  indicators: Indicators | null | undefined;
}): MarketSnapshot | null {
  const bars = params.bars;
  if (!bars || bars.length === 0) return null;
  if (!params.indicators) return null;

  const lastBar = bars[bars.length - 1];
  const orb = computeORB(bars);

  return {
    price: params.quote?.price ?? lastBar?.close ?? null,
    prevClose: params.reference?.close ?? null,
    prevHigh: params.reference?.high ?? null,
    prevLow: params.reference?.low ?? null,
    volumeToday: params.quote?.volume ?? null,
    avgVolume20d: params.avgVolume20d ?? null,
    orbHigh: orb.high,
    orbLow: orb.low,
    lastBar: lastBar ?? null,
    minutesSinceOpen: minutesSinceOpen(lastBar ?? null),
    stochKPrev: params.indicators.stochKPrev,
    indicators: params.indicators,
  };
}
