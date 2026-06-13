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

const POS = interpolateRgb('#0a3d2f', '#34d399'); // dark → emerald
const NEG = interpolateRgb('#3b1d6b', '#a78bfa'); // dark → violet

export function cellColor(value: number, maxAbs: number): string {
  if (!value || maxAbs <= 0) return 'transparent';
  // floor t so even small non-zero cells get a visible tint
  const t = 0.18 + 0.82 * Math.min(Math.abs(value) / maxAbs, 1);
  return value >= 0 ? POS(t) : NEG(t);
}

export function expHeader(iso: string, dte: number): { date: string; dte: string } {
  const [, m, d] = iso.split('-');
  return { date: `${m}/${d}`, dte: dte <= 0 ? '0DTE' : `${dte}d` };
}
