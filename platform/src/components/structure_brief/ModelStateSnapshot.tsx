// ---------------------------------------------------------------------------
// Model State Snapshot — operator-facing health table for the strat engine.
//
// Reads from GET /api/admin/strat-engine/state. Shows per-cell model
// version, last-train timestamp, and the most recent rolling live ECE
// (when the snapshot writer has populated structure_brief_latest.json).
//
// Operator view — not consumer-facing. The language audit applies here
// too, so any new copy must avoid the banned trade-edge words.
// ---------------------------------------------------------------------------

import { AlertTriangle, CheckCircle2, Loader2, MinusCircle } from 'lucide-react';
import { useStratEngineState, type StratEngineCellState } from '@/hooks/useAdmin';
import { formatRefreshed } from './StructureBrief';


export function ModelStateSnapshot({ enabled }: { enabled: boolean }) {
  const { data, isLoading, error } = useStratEngineState(enabled);

  if (!enabled) return null;
  if (isLoading) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3 text-xs text-[var(--color-text-muted)]">
        <Loader2 size={12} className="animate-spin" />
        <span>Loading model state…</span>
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3 text-xs text-[var(--color-text-muted)]">
        Model state unavailable: {error?.message ?? 'no data'}
      </div>
    );
  }

  const totalCells = data.cells.length;
  const availableCells = data.cells.filter((c) => c.available).length;
  const mutedCells = data.cells.filter(
    (c) => c.live_ece != null && c.live_ece > data.ece_ceiling,
  ).length;
  const freshLiveEce = data.cells.some((c) => c.live_ece != null);

  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] text-xs">
      <div className="flex flex-wrap items-center gap-3 border-b border-[var(--color-border-subtle)] px-3 py-2 text-[11px]">
        <span className="font-medium text-[var(--color-text-primary)]">
          {availableCells} / {totalCells} models trained
        </span>
        <span className="text-[var(--color-text-muted)]">·</span>
        {mutedCells > 0 ? (
          <span className="flex items-center gap-1 text-[var(--color-warn)]">
            <AlertTriangle size={12} /> {mutedCells} muted
          </span>
        ) : (
          <span className="flex items-center gap-1 text-[var(--color-text-muted)]">
            <CheckCircle2 size={12} /> 0 muted
          </span>
        )}
        <span className="text-[var(--color-text-muted)]">·</span>
        <span className="text-[var(--color-text-muted)]">
          ECE ceiling {data.ece_ceiling.toFixed(3)}
        </span>
        <span className="text-[var(--color-text-muted)]">·</span>
        <span className="text-[var(--color-text-muted)]">
          {freshLiveEce ? 'live ECE snapshot present' : 'no live ECE snapshot yet'}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
            <tr className="border-b border-[var(--color-border-subtle)]">
              <th className="px-3 py-2 text-left font-medium">Ticker</th>
              <th className="px-3 py-2 text-left font-medium">TF</th>
              <th className="px-3 py-2 text-left font-medium">Status</th>
              <th className="px-3 py-2 text-left font-medium">Model Version</th>
              <th className="px-3 py-2 text-left font-medium">Last Trained</th>
              <th className="px-3 py-2 text-right font-medium">Live ECE</th>
            </tr>
          </thead>
          <tbody>
            {data.cells.map((c) => (
              <Row key={`${c.ticker}_${c.timeframe}`} cell={c} eceCeiling={data.ece_ceiling} />
            ))}
          </tbody>
        </table>
      </div>
      <div className="border-t border-[var(--color-border-subtle)] px-3 py-2 text-[10px] italic text-[var(--color-text-muted)]">
        On the shelf, no scheduler. Activation gated by{' '}
        <code className="rounded bg-[var(--color-bg-secondary)] px-1">docs/STRAT_ENGINE_OPERATIONS.md</code>{' '}
        §8.
      </div>
    </div>
  );
}


function Row({
  cell, eceCeiling,
}: {
  cell: StratEngineCellState;
  eceCeiling: number;
}) {
  const muted = cell.live_ece != null && cell.live_ece > eceCeiling;
  return (
    <tr
      className="border-b border-[var(--color-border-subtle)] last:border-b-0"
      data-testid={`state-${cell.ticker}-${cell.timeframe}`}
    >
      <td className="px-3 py-2 font-medium text-[var(--color-text-primary)]">{cell.ticker}</td>
      <td className="px-3 py-2 text-[var(--color-text-secondary)]">{cell.timeframe}</td>
      <td className="px-3 py-2">
        {!cell.available ? (
          <span className="flex items-center gap-1 text-[var(--color-text-muted)]">
            <MinusCircle size={12} /> no artifact
          </span>
        ) : muted ? (
          <span className="flex items-center gap-1 text-[var(--color-warn)]">
            <AlertTriangle size={12} /> muted
          </span>
        ) : (
          <span className="flex items-center gap-1 text-[var(--color-bull)]">
            <CheckCircle2 size={12} /> ready
          </span>
        )}
      </td>
      <td className="px-3 py-2 font-mono text-[10px] text-[var(--color-text-secondary)]">
        {cell.model_version ?? '—'}
      </td>
      <td className="px-3 py-2 text-[var(--color-text-secondary)]">
        {formatRefreshed(cell.last_train_date)}
      </td>
      <td className="px-3 py-2 text-right tabular-nums">
        {cell.live_ece == null ? (
          <span className="text-[var(--color-text-muted)]">—</span>
        ) : (
          <span className={muted ? 'text-[var(--color-warn)]' : 'text-[var(--color-text-secondary)]'}>
            {cell.live_ece.toFixed(3)}
          </span>
        )}
      </td>
    </tr>
  );
}
