import { describe, expect, it } from 'vitest';
import { buildReviewQuote } from '@/lib/reviewQuote';

const bars = [
  { time: '1', open: 100, high: 102, low: 99, close: 101, volume: 1000 },
  { time: '2', open: 101, high: 103, low: 100, close: 102, volume: 1200 },
];

describe('buildReviewQuote', () => {
  it('bases change on PRIOR SESSION CLOSE, matching live-mode semantics', () => {
    const q = buildReviewQuote(bars, 100.5, 'SPY', '2026-07-02 16:00 ET');
    expect(q!.change).toBeCloseTo(1.5);          // 102 - 100.5
    expect(q!.change_pct).toBeCloseTo(1.4925, 3);
    expect(q!.prev_close).toBeCloseTo(100.5);
  });
  it('is honest when prior close is unavailable: change is null, never open-based', () => {
    const q = buildReviewQuote(bars, null, 'SPY', 'x');
    expect(q!.change).toBeNull();
    expect(q!.change_pct).toBeNull();
  });
  it('returns undefined with no bars', () => {
    expect(buildReviewQuote([], 100, 'SPY', 'x')).toBeUndefined();
  });
});
