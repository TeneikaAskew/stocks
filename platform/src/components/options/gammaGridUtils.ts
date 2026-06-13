import { interpolateRgb } from 'd3';
import type { GammaGridCell } from '@/hooks/useGammaGrid';

export type Metric = 'gex' | 'vex';
export type Filter = 'net' | 'calls' | 'puts';

// Map the metric/filter toggles to the right per-cell scalar. `put_gex`/`put_vex`
// are already sign-negated server-side, so the color convention holds uniformly.
export function selectValue(cell: GammaGridCell, metric: Metric, filter: Filter): number {
  if (metric === 'vex') {
    return filter === 'calls' ? cell.call_vex : filter === 'puts' ? cell.put_vex : cell.vex;
  }
  return filter === 'calls' ? cell.call_gex : filter === 'puts' ? cell.put_gex : cell.gex;
}

// Dark, saturated ramps so bright-white values stay legible at every
// magnitude. Positive (call-dominant) GEX → teal; negative (put) → violet —
// the violet matches the competitor's signature look, both dark enough for
// AA-contrast white text. The bright end is intentionally capped mid-tone.
const POS = interpolateRgb('#06281d', '#0f9b6c'); // deep → teal
const NEG = interpolateRgb('#241452', '#6d28d9'); // deep → violet

// Empty cell (no contracts at that strike × expiration) — a near-black fill
// instead of blank, so the grid reads as a solid dense matrix, not a sieve.
export const EMPTY_CELL = '#0e0c1a';

export function cellColor(value: number, maxAbs: number): string {
  if (!value || maxAbs <= 0) return EMPTY_CELL;
  // floor t so even small non-zero cells get a clearly visible tint
  const t = 0.32 + 0.68 * Math.min(Math.abs(value) / maxAbs, 1);
  return value >= 0 ? POS(t) : NEG(t);
}

export function expHeader(iso: string, dte: number): { date: string; dte: string } {
  const [, m, d] = iso.split('-');
  return { date: `${m}/${d}`, dte: dte <= 0 ? '0DTE' : `${dte}d` };
}
