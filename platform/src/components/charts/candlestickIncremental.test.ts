import { describe, expect, it } from 'vitest';
import { isAppendExtension } from './CandlestickChart';

const bar = (time: number, close: number) => ({
  time,
  open: close - 1,
  high: close + 1,
  low: close - 2,
  close,
});

describe('isAppendExtension', () => {
  it('returns true when next is prev plus one or more new tail bars', () => {
    const prev = [bar(1, 10), bar(2, 11)];
    const next = [bar(1, 10), bar(2, 11), bar(3, 12)];
    expect(isAppendExtension(prev, next)).toBe(true);
  });

  it('returns true when next appends multiple new tail bars', () => {
    const prev = [bar(1, 10)];
    const next = [bar(1, 10), bar(2, 11), bar(3, 12)];
    expect(isAppendExtension(prev, next)).toBe(true);
  });

  it('returns false when a shared leading bar diverges (OHLC mismatch)', () => {
    const prev = [bar(1, 10), bar(2, 11)];
    const next = [bar(1, 10), bar(2, 999), bar(3, 12)];
    expect(isAppendExtension(prev, next)).toBe(false);
  });

  it('returns false when a shared leading bar diverges (time mismatch)', () => {
    const prev = [bar(1, 10), bar(2, 11)];
    const next = [bar(1, 10), bar(99, 11), bar(3, 12)];
    expect(isAppendExtension(prev, next)).toBe(false);
  });

  it('returns false when next is shorter than prev (shrink)', () => {
    const prev = [bar(1, 10), bar(2, 11), bar(3, 12)];
    const next = [bar(1, 10), bar(2, 11)];
    expect(isAppendExtension(prev, next)).toBe(false);
  });

  it('returns false when next is identical to prev (no-op, not an extension)', () => {
    const prev = [bar(1, 10), bar(2, 11)];
    const next = [bar(1, 10), bar(2, 11)];
    expect(isAppendExtension(prev, next)).toBe(false);
  });

  it('returns false for two empty arrays (identical, no-op)', () => {
    expect(isAppendExtension([], [])).toBe(false);
  });

  it('returns true when prev is empty and next has bars (initial reveal is an extension of nothing)', () => {
    expect(isAppendExtension([], [bar(1, 10)])).toBe(true);
  });
});
