/**
 * Data Pipeline Status widget.
 *
 * Small row at the top of the Dashboard that surfaces `/api/health/freshness`
 * as a compact pill-row. Shows one pill per (table, ticker) with green/yellow/red.
 *
 * When everything is ok, collapses to a single-line summary.
 * When any table is stale, expands to show the full list so the user can see which.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle2, ChevronDown } from 'lucide-react';

interface FreshnessRow {
  table: string;
  ticker: string | null;
  last_row_at: string | null;
  expected_latest: string;
  lag_hours: number | null;
  expected_max_hours: number;
  status: 'ok' | 'warn' | 'stale' | 'unknown';
  row_count_recent: number;
}

interface FreshnessResponse {
  checked_at: string;
  expected_market_close: string;
  overall_status: 'ok' | 'warn' | 'stale' | 'unknown';
  tables: FreshnessRow[];
}

const STATUS_DOT: Record<FreshnessRow['status'], string> = {
  ok: 'bg-[var(--bull)]',
  warn: 'bg-[var(--warn)]',
  stale: 'bg-[var(--bear)]',
  unknown: 'bg-[var(--on-surface-muted)]',
};

const STATUS_TEXT: Record<FreshnessRow['status'], string> = {
  ok: 'text-[var(--bull)]',
  warn: 'text-[var(--warn)]',
  stale: 'text-[var(--bear)]',
  unknown: 'text-[var(--on-surface-muted)]',
};

function fmtLag(hours: number | null): string {
  if (hours === null) return '—';
  if (hours < 1) return `${(hours * 60).toFixed(0)}m`;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  const days = Math.floor(hours / 24);
  const h = Math.floor(hours % 24);
  return `${days}d ${h}h`;
}

function rowLabel(row: FreshnessRow): string {
  return row.ticker ? `${row.table} · ${row.ticker}` : row.table;
}

function statusSummary(tables: FreshnessRow[]): { ok: number; warn: number; stale: number; unknown: number } {
  const counts = { ok: 0, warn: 0, stale: 0, unknown: 0 };
  for (const t of tables) counts[t.status] += 1;
  return counts;
}

export function DataPipelineStatus() {
  const [expanded, setExpanded] = useState(false);

  const { data, isLoading, isError } = useQuery<FreshnessResponse>({
    queryKey: ['freshness'],
    queryFn: async () => {
      const r = await fetch('/api/health/freshness');
      if (!r.ok) throw new Error(`${r.status}`);
      return r.json();
    },
    staleTime: 300_000,       // 5 min — matches the API's TTL cache
    refetchInterval: 300_000,
  });

  if (isLoading || !data) {
    return null;
  }

  if (isError) {
    return (
      <div className="rounded-xl bg-[var(--surface-2)] px-4 py-3 text-xs text-[var(--on-surface-muted)]">
        Data pipeline status unavailable
      </div>
    );
  }

  const counts = statusSummary(data.tables);
  const hasProblems = counts.stale > 0 || counts.warn > 0 || counts.unknown > 0;
  const checkedAt = new Date(data.checked_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

  return (
    <div className="rounded-xl bg-[var(--surface-2)] px-5 py-3">
      {/* Top row: overall status + count badges + toggle */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between"
      >
        <div className="flex items-center gap-3 text-xs">
          {hasProblems ? (
            <AlertTriangle size={14} className={STATUS_TEXT[data.overall_status]} />
          ) : (
            <CheckCircle2 size={14} className="text-[var(--bull)]" />
          )}
          <span className="label-micro">Data pipeline</span>
          <span className={`font-semibold uppercase tracking-wider ${STATUS_TEXT[data.overall_status]}`}>
            {data.overall_status}
          </span>
          <span className="text-[var(--on-surface-muted)]">
            {counts.ok} ok
            {counts.warn > 0 && <> · <span className="text-[var(--warn)]">{counts.warn} warn</span></>}
            {counts.stale > 0 && <> · <span className="text-[var(--bear)]">{counts.stale} stale</span></>}
            {counts.unknown > 0 && <> · {counts.unknown} unknown</>}
          </span>
        </div>
        <div className="flex items-center gap-2 text-[10px] text-[var(--on-surface-muted)]">
          <span>Checked {checkedAt}</span>
          <ChevronDown size={12} className={expanded ? 'rotate-180 transition-transform' : 'transition-transform'} />
        </div>
      </button>

      {/* Expanded detail — full pill grid */}
      {expanded && (
        <div className="mt-3 grid grid-cols-1 gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
          {data.tables.map((row) => {
            const key = `${row.table}-${row.ticker ?? ''}`;
            return (
              <div
                key={key}
                className="flex items-center justify-between gap-2 rounded-lg bg-[var(--surface-3)] px-3 py-1.5 text-[11px]"
                title={row.last_row_at ? `Last row: ${row.last_row_at}` : 'No rows found'}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${STATUS_DOT[row.status]}`} />
                  <span className="truncate text-[var(--on-surface)]">{rowLabel(row)}</span>
                </div>
                <span className={`shrink-0 font-mono tabular-nums ${STATUS_TEXT[row.status]}`}>
                  {fmtLag(row.lag_hours)}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Auto-expand hint when there are problems but the user hasn't clicked yet */}
      {hasProblems && !expanded && (
        <div className="mt-1 text-[10px] text-[var(--on-surface-muted)]">
          Click for details
        </div>
      )}
    </div>
  );
}
