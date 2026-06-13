import { describe, it, expect } from 'vitest';
import { selectValue, cellColor } from './gammaGridUtils';
import { formatGex, formatPctChange } from '@/lib/formatGex';
import type { GammaGridCell } from '@/hooks/useGammaGrid';

const cell = (over: Partial<GammaGridCell> = {}): GammaGridCell => ({
  strike: 720, expiration: '2026-06-19', dte: 7,
  net_gamma: 0, call_gamma: 0, put_gamma: 0,
  net_vega: 0, call_vega: 0, put_vega: 0,
  gex: 1_000_000, call_gex: 1_500_000, put_gex: -500_000,
  vex: -200_000, call_vex: -120_000, put_vex: -80_000,
  call_oi: 100, put_oi: 50, call_volume: 0, put_volume: 0,
  distance_pct: 0, pct_change: null, abs_change: null,
  ...over,
});

describe('selectValue', () => {
  it('maps gex × net/calls/puts to the right field', () => {
    const c = cell();
    expect(selectValue(c, 'gex', 'net')).toBe(1_000_000);
    expect(selectValue(c, 'gex', 'calls')).toBe(1_500_000);
    expect(selectValue(c, 'gex', 'puts')).toBe(-500_000);
  });
  it('maps vex × net/calls/puts to the right field', () => {
    const c = cell();
    expect(selectValue(c, 'vex', 'net')).toBe(-200_000);
    expect(selectValue(c, 'vex', 'calls')).toBe(-120_000);
    expect(selectValue(c, 'vex', 'puts')).toBe(-80_000);
  });
});

describe('cellColor', () => {
  it('uses the empty-cell fill for zero value or zero scale', () => {
    expect(cellColor(0, 100)).toBe('#0e0c1a');
    expect(cellColor(100, 0)).toBe('#0e0c1a');
  });
  it('returns a green-ish rgb for positive, purple-ish for negative', () => {
    const pos = cellColor(100, 100);
    const neg = cellColor(-100, 100);
    expect(pos).toMatch(/^rgb/);
    expect(neg).toMatch(/^rgb/);
    expect(pos).not.toBe(neg);
  });
});

describe('formatGex', () => {
  it('formats millions, thousands, and units with sign', () => {
    expect(formatGex(1_200_000)).toBe('+1.2M');
    expect(formatGex(-48_000)).toBe('-48K');
    expect(formatGex(312)).toBe('+312');
  });
});

describe('formatPctChange', () => {
  it('signs and rounds', () => {
    expect(formatPctChange(12.4)).toBe('+12%');
    expect(formatPctChange(-8.6)).toBe('-9%');
  });
  it('clamps the displayed magnitude and marks overflow', () => {
    expect(formatPctChange(11000)).toBe('+999+%');
    expect(formatPctChange(-2500)).toBe('-999+%');
  });
});
