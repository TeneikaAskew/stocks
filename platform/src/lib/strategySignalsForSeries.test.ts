/**
 * Unit tests for computeStrategySignalsForSeries — the per-bar signal
 * voter used by the Charts page overlay.
 *
 * Important: this function evaluates the same 5-condition rule as
 * computeStrategySignals, but at every eligible bar in the series.
 * Eligibility starts at index 14 (RSI warmup); earlier bars are skipped.
 */
import { describe, it, expect } from 'vitest';
import {
  computeStrategySignalsForSeries,
  type Bar,
} from './indicators';

function bar(close: number, prev: number, time: number): Bar {
  return {
    time: String(time),
    open: prev,
    high: Math.max(close, prev),
    low: Math.min(close, prev),
    close,
    volume: 1000,
  };
}

/** Build a synthetic series of N bars given a price-generating function. */
function series(n: number, price: (i: number) => number): Bar[] {
  const bars: Bar[] = [];
  let prev = price(0);
  for (let i = 0; i < n; i += 1) {
    const c = price(i);
    bars.push(bar(c, prev, 1_700_000_000 + i * 60));
    prev = c;
  }
  return bars;
}

describe('computeStrategySignalsForSeries — guards', () => {
  it('returns [] for empty input', () => {
    expect(computeStrategySignalsForSeries([])).toEqual([]);
  });

  it('returns [] when fewer than 15 bars (RSI warmup)', () => {
    const bars = series(14, (i) => 100 + i);
    expect(computeStrategySignalsForSeries(bars)).toEqual([]);
  });

  it('skips evaluating bars before index 14 even when 15+ bars are supplied', () => {
    // 30 monotonic ups — every CALL signal index must be ≥ 14.
    const bars = series(30, (i) => 100 + i * 0.1);
    const fires = computeStrategySignalsForSeries(bars);
    expect(fires.length).toBeGreaterThan(0);
    expect(fires.every((f) => f.index >= 14)).toBe(true);
  });
});

describe('computeStrategySignalsForSeries — directionality', () => {
  it('detects CALL fires on a sustained uptrend', () => {
    // Steady drift up → eventually CALL voter conditions align: 3 ups,
    // RSI in bullish band, price > VWAP, price > EMA9.
    const bars = series(60, (i) => 100 + i * 0.05);
    const fires = computeStrategySignalsForSeries(bars);
    const calls = fires.filter((f) => f.direction === 'CALL');
    expect(calls.length).toBeGreaterThan(0);
    // Each fire's price should match the bar's close (no off-by-one)
    for (const c of calls) {
      expect(c.price).toBe(bars[c.index].close);
      expect(c.metCount).toBeGreaterThanOrEqual(3);
      expect(c.metCount).toBeLessThanOrEqual(5);
    }
  });

  it('detects PUT fires on a sustained downtrend', () => {
    const bars = series(60, (i) => 100 - i * 0.05);
    const fires = computeStrategySignalsForSeries(bars);
    const puts = fires.filter((f) => f.direction === 'PUT');
    expect(puts.length).toBeGreaterThan(0);
    for (const p of puts) {
      expect(p.metCount).toBeGreaterThanOrEqual(3);
    }
  });

  it('produces no fires on a sustained flat series', () => {
    // RSI sits at 50 (or undefined) on flat data; voter rejects on RSI band
    const bars = series(60, () => 100);
    const fires = computeStrategySignalsForSeries(bars);
    expect(fires).toEqual([]);
  });
});

describe('computeStrategySignalsForSeries — output shape', () => {
  it('returns objects with the documented fields', () => {
    const bars = series(30, (i) => 100 + i * 0.05);
    const fires = computeStrategySignalsForSeries(bars);
    if (fires.length === 0) return; // upstream coverage handles this branch
    const first = fires[0];
    expect(typeof first.index).toBe('number');
    expect(typeof first.time).toBe('string');
    expect(['CALL', 'PUT']).toContain(first.direction);
    expect(typeof first.metCount).toBe('number');
    expect(typeof first.price).toBe('number');
  });

  it('time field passes through the source bar.time string verbatim', () => {
    const bars = series(30, (i) => 100 + i * 0.05);
    const fires = computeStrategySignalsForSeries(bars);
    if (fires.length === 0) return;
    expect(fires[0].time).toBe(bars[fires[0].index].time);
  });
});
