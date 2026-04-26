import { useMemo, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { useWatchlist } from '@/hooks/useWatchlist';
import type {
  CatalystType,
  RankedTicker,
  SignalContribution,
} from '@/types/watchlist';

const CATALYST_TYPES: CatalystType[] = [
  'earnings',
  'sec_8k',
  'insider',
  'top_mover',
  'economic_event',
  'manual',
];

const CATALYST_LABEL: Record<CatalystType, string> = {
  earnings: 'Earnings',
  sec_8k: '8-K',
  insider: 'Insider',
  top_mover: 'Top mover',
  economic_event: 'Macro',
  manual: 'Watchlist',
};

const CATALYST_BADGE_CLASS: Record<CatalystType, string> = {
  earnings: 'border-amber-500/40 bg-amber-500/15 text-amber-300',
  sec_8k: 'border-purple-500/40 bg-purple-500/15 text-purple-300',
  insider: 'border-cyan-500/40 bg-cyan-500/15 text-cyan-300',
  top_mover: 'border-pink-500/40 bg-pink-500/15 text-pink-300',
  economic_event: 'border-blue-500/40 bg-blue-500/15 text-blue-300',
  manual: 'border-zinc-500/40 bg-zinc-500/15 text-zinc-300',
};

interface Props {
  onSelectTicker: (ticker: string) => Promise<void> | void;
  refreshing: boolean;
  refreshingTicker: string | null;
}

export function WatchlistPanel({
  onSelectTicker,
  refreshing,
  refreshingTicker,
}: Props) {
  const [activeFilters, setActiveFilters] = useState<Set<CatalystType>>(
    new Set(),
  );
  const [limit, setLimit] = useState(10);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const filterArray = useMemo(() => Array.from(activeFilters), [activeFilters]);
  const watchlist = useWatchlist({ catalystFilter: filterArray, limit });

  const toggleFilter = (type: CatalystType) => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const toggleExpand = (ticker: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  };

  return (
    <div className="space-y-3">
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Catalyst:
        </span>
        {CATALYST_TYPES.map((type) => {
          const active = activeFilters.has(type);
          return (
            <button
              key={type}
              onClick={() => toggleFilter(type)}
              className={`rounded border px-2 py-0.5 text-[10px] font-medium transition-colors ${
                active
                  ? CATALYST_BADGE_CLASS[type]
                  : 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
              }`}
            >
              {CATALYST_LABEL[type]}
            </button>
          );
        })}

        <div className="ml-auto flex items-center gap-2 text-[10px] text-[var(--color-text-muted)]">
          <label htmlFor="watchlist-limit">Limit:</label>
          <select
            id="watchlist-limit"
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-1 py-0.5 text-[10px] text-[var(--color-text-primary)]"
          >
            {[5, 10, 20, 50].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Body */}
      {watchlist.isLoading ? (
        <div className="flex h-40 items-center justify-center">
          <Loader2 size={20} className="animate-spin text-[var(--color-text-muted)]" />
        </div>
      ) : watchlist.error ? (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-300">
          Failed to load watchlist:{' '}
          {watchlist.error instanceof Error
            ? watchlist.error.message
            : String(watchlist.error)}
        </div>
      ) : !watchlist.data || watchlist.data.ranked.length === 0 ? (
        <div className="flex h-40 flex-col items-center justify-center gap-2 text-center text-xs text-[var(--color-text-muted)]">
          <Sparkles size={20} />
          <div>No candidates ranked.</div>
          <div className="text-[10px]">
            Either no catalyst tickers met the liquidity gate, or the
            catalyst data tables are empty. Once Phase 2 fetchers have
            run a full day, this list will populate.
          </div>
        </div>
      ) : (
        <>
          {/* Run summary */}
          <div className="flex items-center justify-between text-[10px] text-[var(--color-text-muted)]">
            <span>
              {watchlist.data.ranked.length} ranked of{' '}
              {watchlist.data.candidate_count} candidates ·{' '}
              {watchlist.data.excluded_count} excluded by liquidity gate
            </span>
            <span>{watchlist.data.duration_ms}ms · run {watchlist.data.run_id.slice(0, 8)}</span>
          </div>

          {/* Table */}
          <div className="space-y-2">
            {watchlist.data.ranked.map((row) => (
              <RankedRow
                key={row.ticker}
                row={row}
                expanded={expanded.has(row.ticker)}
                onToggleExpand={() => toggleExpand(row.ticker)}
                onGenerate={() => onSelectTicker(row.ticker)}
                isGenerating={refreshing && refreshingTicker === row.ticker}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// One row per ranked ticker — collapsible breakdown
// ---------------------------------------------------------------------------

function RankedRow({
  row,
  expanded,
  onToggleExpand,
  onGenerate,
  isGenerating,
}: {
  row: RankedTicker;
  expanded: boolean;
  onToggleExpand: () => void;
  onGenerate: () => Promise<void> | void;
  isGenerating: boolean;
}) {
  const pct = Math.round(row.pct_of_max * 100);

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
      <div className="flex items-center gap-3 px-3 py-2">
        <button
          onClick={onToggleExpand}
          className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
          aria-label={expanded ? 'Collapse breakdown' : 'Expand breakdown'}
        >
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>

        <div className="font-mono text-sm font-semibold text-[var(--color-text-primary)]">
          {row.ticker}
        </div>

        {/* Score chip */}
        <div className="flex items-baseline gap-1">
          <span className="text-sm font-bold text-[var(--color-text-primary)]">
            {row.score.toFixed(2)}
          </span>
          <span className="text-[10px] text-[var(--color-text-muted)]">
            ({pct}%)
          </span>
        </div>

        {/* Catalyst tags */}
        <div className="flex flex-wrap gap-1">
          {row.catalyst_types.map((c) => (
            <span
              key={c}
              className={`rounded border px-1.5 py-0.5 text-[9px] font-medium ${CATALYST_BADGE_CLASS[c]}`}
            >
              {CATALYST_LABEL[c]}
            </span>
          ))}
        </div>

        <button
          onClick={() => void onGenerate()}
          disabled={isGenerating}
          className="ml-auto flex items-center gap-1 rounded bg-[var(--color-accent-blue)] px-2 py-1 text-[10px] font-medium text-[var(--on-brand)] disabled:opacity-50"
        >
          {isGenerating ? (
            <Loader2 size={10} className="animate-spin" />
          ) : (
            <RefreshCw size={10} />
          )}
          Generate report
        </button>
      </div>

      {expanded && <ScoreBreakdown breakdown={row.score_breakdown} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Per-signal breakdown — every contribution is shown so the ranking is auditable
// ---------------------------------------------------------------------------

function ScoreBreakdown({ breakdown }: { breakdown: SignalContribution[] }) {
  // Sort by points contributed (largest first), then by name for stable ordering
  const sorted = [...breakdown].sort((a, b) => {
    if (b.points !== a.points) return b.points - a.points;
    return a.name.localeCompare(b.name);
  });

  return (
    <div className="border-t border-[var(--color-border)] px-3 py-2">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        Score breakdown
      </div>
      <table className="w-full text-[11px]">
        <thead>
          <tr className="text-[10px] text-[var(--color-text-muted)]">
            <th className="text-left">Signal</th>
            <th className="text-right">0–1</th>
            <th className="text-right">×weight</th>
            <th className="text-right">= points</th>
            <th className="pl-3 text-left">Reason</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((c) => (
            <tr
              key={c.name}
              className={
                c.available
                  ? 'text-[var(--color-text-secondary)]'
                  : 'text-[var(--color-text-muted)]'
              }
            >
              <td className="py-0.5 font-mono">{c.name}</td>
              <td className="py-0.5 text-right tabular-nums">
                {c.available ? c.score_0_to_1.toFixed(2) : '—'}
              </td>
              <td className="py-0.5 text-right tabular-nums">
                {c.weight.toFixed(1)}
              </td>
              <td className="py-0.5 text-right font-semibold tabular-nums">
                {c.available ? c.points.toFixed(2) : '—'}
              </td>
              <td className="py-0.5 pl-3">{c.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
