import { useMemo } from 'react';
import type { GammaGridSummary, GammaGridCell } from '@/hooks/useGammaGrid';
import { formatGex, formatPctChange } from '@/lib/formatGex';
import { selectValue, cellColor, expHeader, EMPTY_CELL, type Metric, type Filter } from './gammaGridUtils';

interface Props {
  summary: GammaGridSummary;
  metric: Metric;
  filter: Filter;
  /** Strike to gold-highlight as the King node (largest |net GEX|). */
  kingStrike?: number;
  /** Cap the visible expiration columns to the nearest N (LEAPS out to 2028
   *  add noise). The rest stay reachable by widening this. Default 12. */
  maxExpirations?: number;
}

export function GammaGrid({ summary, metric, filter, kingStrike, maxExpirations = 12 }: Props) {
  const showChange = summary.data_source === 'realtime';

  const { cellMap, strikesDesc, columns, maxAbs, dteByExp, spotStrike, kingKey } =
    useMemo(() => {
      // Visible columns = nearest N expirations (ascending; already sorted).
      const cols = summary.expirations.slice(0, maxExpirations);
      const colSet = new Set(cols);
      const map = new Map<string, GammaGridCell>();
      const dte = new Map<string, number>();
      let max = 0;
      let king: string | null = null;
      let kingAbs = -1;
      for (const c of summary.cells) {
        if (!colSet.has(c.expiration)) continue; // skip hidden far-dated columns
        map.set(`${c.strike}|${c.expiration}`, c);
        dte.set(c.expiration, c.dte);
        const v = Math.abs(selectValue(c, metric, filter));
        if (v > max) max = v;
        const netAbs = Math.abs(c.gex);
        if (netAbs > kingAbs) {
          kingAbs = netAbs;
          king = `${c.strike}|${c.expiration}`;
        }
      }
      const strikes = [...summary.strikes].sort((a, b) => b - a); // descending
      // strike row nearest spot → spot highlight
      let nearest = strikes[0];
      let best = Infinity;
      const spot = summary.spot?.price ?? 0;
      for (const s of strikes) {
        const d = Math.abs(s - spot);
        if (d < best) {
          best = d;
          nearest = s;
        }
      }
      return {
        cellMap: map,
        strikesDesc: strikes,
        columns: cols,
        maxAbs: max,
        dteByExp: dte,
        spotStrike: nearest,
        kingKey: king,
      };
    }, [summary, metric, filter, maxExpirations]);

  // King strike: prefer the explicit prop (from /levels), else the largest |net GEX| cell.
  const kingRow = kingStrike ?? (kingKey ? Number(kingKey.split('|')[0]) : undefined);

  const gridCols = `56px repeat(${columns.length}, minmax(74px, 1fr))`;

  return (
    <div className="overflow-auto rounded-lg border border-[var(--color-border)]" style={{ maxHeight: 620 }}>
      {/* gap-px over a dark backdrop paints crisp 1px gridlines without per-cell borders */}
      <div
        className="grid gap-px text-[11px]"
        style={{ gridTemplateColumns: gridCols, backgroundColor: '#272233' }}
        data-testid="gamma-grid"
      >
        {/* Header row */}
        <div className="sticky left-0 top-0 z-30 flex items-center justify-center bg-[var(--surface-3)] px-1 py-1.5 font-medium text-[var(--color-text-muted)]">
          Strike
        </div>
        {columns.map((exp) => {
          const h = expHeader(exp, dteByExp.get(exp) ?? 0);
          return (
            <div
              key={exp}
              className="sticky top-0 z-20 flex flex-col items-center justify-center bg-[var(--surface-3)] px-1 py-1"
            >
              <span className="font-medium text-[var(--color-text-secondary)]">{h.date}</span>
              <span className="text-[9px] text-[var(--color-text-muted)]">{h.dte}</span>
            </div>
          );
        })}

        {/* Data rows */}
        {strikesDesc.map((strike) => {
          const isSpotRow = strike === spotStrike;
          const isKingRow = kingRow !== undefined && strike === kingRow;
          return (
            <Row
              key={strike}
              strike={strike}
              columns={columns}
              cellMap={cellMap}
              metric={metric}
              filter={filter}
              maxAbs={maxAbs}
              showChange={showChange}
              isSpotRow={isSpotRow}
              isKingRow={isKingRow}
              kingKey={kingKey}
            />
          );
        })}
      </div>
    </div>
  );
}

function Row({
  strike,
  columns,
  cellMap,
  metric,
  filter,
  maxAbs,
  showChange,
  isSpotRow,
  isKingRow,
  kingKey,
}: {
  strike: number;
  columns: string[];
  cellMap: Map<string, GammaGridCell>;
  metric: Metric;
  filter: Filter;
  maxAbs: number;
  showChange: boolean;
  isSpotRow: boolean;
  isKingRow: boolean;
  kingKey: string | null;
}) {
  return (
    <>
      {/* Sticky strike label */}
      <div
        className={`sticky left-0 z-10 flex items-center justify-end gap-1 px-2 font-mono text-[11px] ${
          isSpotRow
            ? 'border-l-2 border-l-[var(--bull)] bg-[#0f1b2a] font-semibold text-[var(--bull)]'
            : isKingRow
            ? 'bg-[#3a2c07] font-semibold text-[var(--color-accent-amber)]'
            : 'bg-[#15131f] text-[var(--color-text-secondary)]'
        }`}
      >
        {isKingRow && <span aria-hidden>★</span>}
        {strike.toFixed(strike % 1 === 0 ? 0 : 1)}
      </div>
      {columns.map((exp) => {
        const cell = cellMap.get(`${strike}|${exp}`);
        // Only the single dominant cell (largest |net GEX|) is gold, not the row.
        const isKingCell = kingKey === `${strike}|${exp}`;
        return (
          <Cell
            key={exp}
            cell={cell}
            metric={metric}
            filter={filter}
            maxAbs={maxAbs}
            showChange={showChange}
            isKingCell={isKingCell}
          />
        );
      })}
    </>
  );
}

function Cell({
  cell,
  metric,
  filter,
  maxAbs,
  showChange,
  isKingCell,
}: {
  cell?: GammaGridCell;
  metric: Metric;
  filter: Filter;
  maxAbs: number;
  showChange: boolean;
  isKingCell: boolean;
}) {
  if (!cell) {
    return <div className="min-h-[26px]" style={{ backgroundColor: EMPTY_CELL }} />;
  }
  const value = selectValue(cell, metric, filter);
  const bg = isKingCell ? '#f5c518' : cellColor(value, maxAbs);
  const pct = cell.pct_change;
  const tooltip =
    `${cell.strike} · ${cell.expiration} (${cell.dte}d)\n` +
    `${metric.toUpperCase()} ${filter}: ${formatGex(value)}\n` +
    `OI ${cell.call_oi}c / ${cell.put_oi}p` +
    (pct !== null ? `\nIntraday Δ: ${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%` : '');

  // King cell is gold → use dark text; all others ride dark heatmap → white.
  const textColor = isKingCell ? '#1a1505' : '#ffffff';

  return (
    <div
      title={tooltip}
      className="flex min-h-[26px] items-center justify-end gap-1 px-1.5"
      style={{ backgroundColor: bg }}
    >
      {showChange && pct !== null && (
        <span
          className="rounded-sm px-1 text-[9px] font-bold leading-tight"
          style={{
            backgroundColor: pct >= 0 ? '#059669' : '#e11d48',
            color: '#ffffff',
          }}
        >
          {formatPctChange(pct)}
        </span>
      )}
      <span className="font-mono text-[11px] font-semibold leading-none" style={{ color: textColor }}>
        {formatGex(value)}
        {isKingCell && <span className="ml-0.5">★</span>}
      </span>
    </div>
  );
}
