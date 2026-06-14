import { describe, it, expect } from 'vitest';
import { synthQuoteFromBars, type OhlcBar } from './useReviewQuote';

const bars: OhlcBar[] = [
  { open: 100, high: 101, low: 99, close: 100.5, volume: 10 },
  { open: 100.5, high: 103, low: 100, close: 102, volume: 20 },
  { open: 102, high: 102.5, low: 98, close: 101, volume: 30 },
];

describe('synthQuoteFromBars', () => {
  it('aggregates open/close/high/low/volume across the window', () => {
    const q = synthQuoteFromBars(bars, 'IWM', '2026-06-12 12:00 ET')!;
    expect(q.ticker).toBe('IWM');
    expect(q.open).toBe(100); // first bar open
    expect(q.price).toBe(101); // last bar close
    expect(q.high).toBe(103); // max high
    expect(q.low).toBe(98); // min low
    expect(q.volume).toBe(60); // summed
    expect(q.prev_close).toBe(100); // first open is the session anchor
    expect(q.last_updated).toBe('2026-06-12 12:00 ET');
  });

  it('computes change and change_pct off the session open', () => {
    const q = synthQuoteFromBars(bars, 'IWM', 'x')!;
    expect(q.change).toBeCloseTo(1, 10); // 101 - 100
    expect(q.change_pct).toBeCloseTo(1, 10); // (101-100)/100 * 100
  });

  it('returns undefined for an empty window (no fabricated price, §3.7)', () => {
    expect(synthQuoteFromBars([], 'IWM', 'x')).toBeUndefined();
  });
});
