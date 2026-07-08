import { describe, it, expect } from 'vitest';
import { reviewCutoffTs } from './useReviewQuote';

// The bar-aggregation math (open/high/low/volume + prior-close-based
// change/change_pct) now lives in buildReviewQuote (lib/reviewQuote.ts,
// covered by routes/reviewQuote.test.ts) so both LiveMarketPage and this
// hook share one implementation instead of two divergent builders. What's
// left here is the piece that's genuinely local to this hook: turning a
// review date/time into the unix-seconds cutoff used to slice bars.
describe('reviewCutoffTs', () => {
  it('defaults to the 16:00 ET close when no reviewTime is given', () => {
    const ts = reviewCutoffTs('2026-06-12', null);
    expect(ts).toBe(Math.floor(Date.UTC(2026, 5, 12, 16, 0) / 1000));
  });

  it('honors an explicit reviewTime', () => {
    const ts = reviewCutoffTs('2026-06-12', '12:30');
    expect(ts).toBe(Math.floor(Date.UTC(2026, 5, 12, 12, 30) / 1000));
  });
});
