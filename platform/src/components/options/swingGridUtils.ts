import type { GammaGridCell, GammaGridSummary } from '@/hooks/useGammaGrid';

// Pure helpers for the real strike × expiration heatmap. Kept out of the
// component so they're unit-testable and so the GEX/VEX field-selection logic
// has one source of truth (mirrors the server-side lib.gamma convention:
// put_gex/put_vex are already sign-negated, so the color convention holds).

export type Metric = 'gex' | 'vex';
export type Filter = 'net' | 'calls' | 'puts';

export function selectValue(cell: GammaGridCell, metric: Metric, filter: Filter): number {
  if (metric === 'vex') {
    return filter === 'calls' ? cell.call_vex : filter === 'puts' ? cell.put_vex : cell.vex;
  }
  return filter === 'calls' ? cell.call_gex : filter === 'puts' ? cell.put_gex : cell.gex;
}

export function expHeader(iso: string, dte: number): { date: string; dte: string } {
  const [, m, d] = iso.split('-');
  return { date: `${m}/${d}`, dte: dte <= 0 ? '0DTE' : `${dte}d` };
}

export interface BuiltGrid {
  cellMap: Map<string, GammaGridCell>;
  strikesDesc: number[]; // descending → price-ladder orientation
  columns: string[]; // visible expirations (ascending)
  maxAbs: number; // for color scaling
  dteByExp: Map<string, number>;
  spotStrike: number | null; // strike row nearest spot
  kingKey: string | null; // `${strike}|${exp}` of the largest |net GEX| cell
}

/**
 * Reduce a grid summary to everything the heatmap needs in one pass:
 * a (strike|exp)→cell map, descending strike rows, capped expiration columns,
 * the max |value| for color scaling, the spot-nearest strike, and the King cell.
 */
export function buildGrid(
  summary: GammaGridSummary,
  metric: Metric,
  filter: Filter,
  maxExpirations = 12,
): BuiltGrid {
  const columns = summary.expirations.slice(0, maxExpirations);
  const colSet = new Set(columns);
  const cellMap = new Map<string, GammaGridCell>();
  const dteByExp = new Map<string, number>();
  let maxAbs = 0;
  let kingKey: string | null = null;
  let kingAbs = -1;
  for (const c of summary.cells) {
    if (!colSet.has(c.expiration)) continue; // skip hidden far-dated columns
    cellMap.set(`${c.strike}|${c.expiration}`, c);
    dteByExp.set(c.expiration, c.dte);
    const v = Math.abs(selectValue(c, metric, filter));
    if (v > maxAbs) maxAbs = v;
    const netAbs = Math.abs(c.gex);
    if (netAbs > kingAbs) {
      kingAbs = netAbs;
      kingKey = `${c.strike}|${c.expiration}`;
    }
  }
  const strikesDesc = [...summary.strikes].sort((a, b) => b - a);
  let spotStrike: number | null = strikesDesc[0] ?? null;
  let best = Infinity;
  const spot = summary.spot?.price ?? 0;
  for (const s of strikesDesc) {
    const d = Math.abs(s - spot);
    if (d < best) {
      best = d;
      spotStrike = s;
    }
  }
  return { cellMap, strikesDesc, columns, maxAbs, dteByExp, spotStrike, kingKey };
}
