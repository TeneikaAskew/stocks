import { describe, it, expect } from 'vitest';
import { selectValue, buildGrid } from './swingGridUtils';
import { formatGex, formatPctChange } from '@/lib/formatGex';
import type { GammaGridCell, GammaGridSummary } from '@/hooks/useGammaGrid';

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

const summary = (cells: GammaGridCell[]): GammaGridSummary => ({
  ticker: 'SPY', snapshot_date: '2026-06-19', snapshot_ts: '2026-06-19T15:55:00Z',
  data_source: 'realtime',
  spot: { price: 718, method: 'parity', note: '' },
  gamma_balance: null, gamma_flip: 717, regime: 'negative_gamma',
  total_gex: 0, total_vex: 0,
  cells,
  expirations: [...new Set(cells.map((c) => c.expiration))].sort(),
  strikes: [...new Set(cells.map((c) => c.strike))].sort((a, b) => a - b),
  window_pct: 6, warnings: [],
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

describe('buildGrid', () => {
  const cells = [
    cell({ strike: 715, expiration: '2026-06-19', gex: 300_000 }),
    cell({ strike: 720, expiration: '2026-06-19', gex: 900_000 }), // King
    cell({ strike: 715, expiration: '2026-07-17', gex: -200_000 }),
  ];
  const built = buildGrid(summary(cells), 'gex', 'net', 12);

  it('orders strikes descending (price-ladder)', () => {
    expect(built.strikesDesc).toEqual([720, 715]);
  });
  it('keeps expirations as columns and maps cells by strike|exp', () => {
    expect(built.columns).toEqual(['2026-06-19', '2026-07-17']);
    expect(built.cellMap.get('720|2026-06-19')?.gex).toBe(900_000);
  });
  it('identifies the King cell as the largest |net GEX|', () => {
    expect(built.kingKey).toBe('720|2026-06-19');
  });
  it('picks the strike row nearest spot (718 → 720)', () => {
    expect(built.spotStrike).toBe(720);
  });
  it('tracks max |value| for color scaling', () => {
    expect(built.maxAbs).toBe(900_000);
  });
  it('caps visible expiration columns', () => {
    const many = Array.from({ length: 20 }, (_, i) =>
      cell({ strike: 700, expiration: `2026-${String((i % 12) + 1).padStart(2, '0')}-15` }),
    );
    expect(buildGrid(summary(many), 'gex', 'net', 5).columns.length).toBeLessThanOrEqual(5);
  });
});

describe('formatGex / formatPctChange', () => {
  it('formats millions, thousands, units with sign', () => {
    expect(formatGex(1_200_000)).toBe('+1.2M');
    expect(formatGex(-48_000)).toBe('-48K');
    expect(formatGex(312)).toBe('+312');
  });
  it('signs, rounds, and clamps pct change', () => {
    expect(formatPctChange(12.4)).toBe('+12%');
    expect(formatPctChange(-8.6)).toBe('-9%');
    expect(formatPctChange(11000)).toBe('+999+%');
  });
});
