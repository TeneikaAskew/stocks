import { describe, expect, it } from 'vitest';
import { formatCompactVolume, formatChangePct, sparklinePoints, isBullishSpark } from './MostActiveBar';

describe('formatCompactVolume', () => {
  it('formats hundreds of millions with an M suffix', () => {
    expect(formatCompactVolume(312_000_000)).toBe('312M');
  });
  it('rounds to the nearest whole million', () => {
    expect(formatCompactVolume(44_100_000)).toBe('44M');
  });
  it('formats sub-million volume with a K suffix', () => {
    expect(formatCompactVolume(981_000)).toBe('981K');
  });
  it('renders an em dash for missing volume — never a fabricated 0 (Rule 3.7)', () => {
    expect(formatCompactVolume(null)).toBe('—');
    expect(formatCompactVolume(undefined)).toBe('—');
  });
  it('formats billions with a B suffix', () => {
    expect(formatCompactVolume(2_300_000_000)).toBe('2B');
  });
  it('formats sub-thousand volume as a plain integer', () => {
    expect(formatCompactVolume(420)).toBe('420');
  });
});

describe('formatChangePct', () => {
  it('prefixes positive change with a plus sign', () => {
    expect(formatChangePct(2.31)).toBe('+2.31%');
  });
  it('keeps the minus sign for negative change', () => {
    expect(formatChangePct(-1.5)).toBe('-1.50%');
  });
  it('renders an em dash for null change — never a fabricated 0 (Rule 3.7)', () => {
    expect(formatChangePct(null)).toBe('—');
    expect(formatChangePct(undefined)).toBe('—');
  });
});

describe('sparklinePoints', () => {
  it('maps the min value to the bottom and the max value to the top', () => {
    const points = sparklinePoints([1, 2, 3], 56, 18);
    expect(points).toHaveLength(3);
    expect(points[0]).toEqual([0, 18]);
    expect(points[2]).toEqual([56, 0]);
    expect(points[1][0]).toBeCloseTo(28);
    expect(points[1][1]).toBeCloseTo(9);
  });
  it('renders a flat mid-height line when every value is identical', () => {
    const points = sparklinePoints([5, 5, 5], 56, 18);
    expect(points.every(([, y]) => y === 9)).toBe(true);
  });
  it('returns an empty array for empty input', () => {
    expect(sparklinePoints([], 56, 18)).toEqual([]);
  });
});

describe('isBullishSpark', () => {
  it('is bullish when the last point is at or above the first', () => {
    expect(isBullishSpark([181.2, 181.9, 182.4])).toBe(true);
    expect(isBullishSpark([1, 1])).toBe(true);
  });
  it('is bearish when the last point is below the first', () => {
    expect(isBullishSpark([182.4, 181.9, 181.2])).toBe(false);
  });
});
