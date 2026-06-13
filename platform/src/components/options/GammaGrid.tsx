import { useMemo } from 'react';
import type { GammaGridSummary, GammaGridCell } from '@/hooks/useGammaGrid';
import { formatGex, formatPctChange } from '@/lib/formatGex';
import { selectValue, cellColor, expHeader, type Metric, type Filter } from './gammaGridUtils';

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

  const gridCols = `64px repeat(${columns.length}, minmax(76px, 1fr))`;

  return (
    <div className="overflow-auto rounded-lg border border-[var(--color-border)]" style={{ maxHeight: 620 }}>
      <div className="grid text-[11px]" style={{ gridTemplateColumns: gridCols }} data-testid="gamma-grid">
        {/* Header row */}
        <div className="sticky left-0 top-0 z-30 flex items-center justify-center border-b border-r border-[var(--color-border)] bg-[var(--surface-3)] px-1 py-1.5 font-medium text-[var(--color-text-muted)]">
          Strike
        </div>
        {columns.map((exp) => {
          const h = expHeader(exp, dteByExp.get(exp) ?? 0);
          return (
            <div
              key={exp}
              className="sticky top-0 z-20 flex flex-col items-center justify-center border-b border-[var(--color-border)] bg-[var(--surface-3)] px-1 py-1"
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
              kingRow={kingRow}
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
  kingRow,
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
  kingRow?: number;
}) {
  return (
    <>
      {/* Sticky strike label */}
      <div
        className={`sticky left-0 z-10 flex items-center justify-end gap-1 border-r border-[var(--color-border)] px-1.5 font-mono ${
          isSpotRow
            ? 'bg-[var(--color-accent-red)]/15 font-semibold text-[var(--bear)]'
            : isKingRow
            ? 'bg-[var(--color-accent-amber)]/15 text-[var(--color-accent-amber)]'
            : 'bg-[var(--surface-2)] text-[var(--color-text-secondary)]'
        }`}
      >
        {isKingRow && <span aria-hidden>★</span>}
        {strike.toFixed(strike % 1 === 0 ? 0 : 1)}
      </div>
      {columns.map((exp) => {
        const cell = cellMap.get(`${strike}|${exp}`);
        const isKingCell = isKingRow && kingRow !== undefined && strike === kingRow;
        return (
          <Cell
            key={exp}
            cell={cell}
            metric={metric}
            filter={filter}
            maxAbs={maxAbs}
            showChange={showChange}
            isKingCell={isKingCell}
            isSpotRow={isSpotRow}
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
  isSpotRow,
}: {
  cell?: GammaGridCell;
  metric: Metric;
  filter: Filter;
  maxAbs: number;
  showChange: boolean;
  isKingCell: boolean;
  isSpotRow: boolean;
}) {
  if (!cell) {
    return (
      <div
        className={`min-h-[34px] border-b border-l border-[var(--color-border-subtle)] ${
          isSpotRow ? 'bg-[var(--color-accent-red)]/5' : ''
        }`}
      />
    );
  }
  const value = selectValue(cell, metric, filter);
  const bg = cellColor(value, maxAbs);
  const pct = cell.pct_change;
  const tooltip =
    `${cell.strike} · ${cell.expiration} (${cell.dte}d)\n` +
    `${metric.toUpperCase()} ${filter}: ${formatGex(value)}\n` +
    `OI ${cell.call_oi}c / ${cell.put_oi}p` +
    (pct !== null ? `\nIntraday Δ: ${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%` : '');

  return (
    <div
      title={tooltip}
      className={`relative flex min-h-[34px] flex-col items-center justify-center border-b border-l px-0.5 py-0.5 ${
        isKingCell
          ? 'z-[1] ring-2 ring-inset ring-[var(--color-accent-amber)] border-transparent'
          : 'border-[var(--color-border-subtle)]'
      }`}
      style={{ backgroundColor: bg }}
    >
      <span className="font-medium leading-none text-white/90">{formatGex(value)}</span>
      {showChange && pct !== null && (
        <span
          className="mt-0.5 rounded px-1 text-[8.5px] font-semibold leading-tight"
          style={{
            backgroundColor: pct >= 0 ? 'rgba(16,185,129,0.22)' : 'rgba(244,63,94,0.22)',
            color: pct >= 0 ? '#34d399' : '#fb7185',
          }}
        >
          {formatPctChange(pct)}
        </span>
      )}
    </div>
  );
}
