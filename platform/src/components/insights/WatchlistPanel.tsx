import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { useWatchlist } from '@/hooks/useWatchlist';
import {
  useTickerSearch,
  useAddToWatchlist,
  useRemoveFromWatchlist,
  type SearchMatch,
  type WatchlistAddResult,
} from '@/hooks/useTickerSearch';
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
  const [showSearch, setShowSearch] = useState(false);

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
      {/* Filter bar + Add button */}
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
          <button
            onClick={() => setShowSearch((v) => !v)}
            className="flex items-center gap-1 rounded border border-[var(--color-border)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
          >
            <Plus size={10} />
            Add Ticker
          </button>
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

      {/* Ticker search panel */}
      {showSearch && (
        <TickerSearchPanel
          onClose={() => setShowSearch(false)}
          onAdded={() => {
            watchlist.refetch();
          }}
        />
      )}

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
// Ticker search & add panel
// ---------------------------------------------------------------------------

function TickerSearchPanel({
  onClose,
  onAdded,
}: {
  onClose: () => void;
  onAdded: () => void;
}) {
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [addedResult, setAddedResult] = useState<WatchlistAddResult | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Debounce search queries
  const handleInputChange = useCallback((value: string) => {
    setQuery(value);
    setAddedResult(null);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedQuery(value.trim());
    }, 300);
  }, []);

  const searchQuery = useTickerSearch(debouncedQuery, debouncedQuery.length >= 1);
  const addMutation = useAddToWatchlist();

  const handleAdd = async (match: SearchMatch) => {
    try {
      const result = await addMutation.mutateAsync(match.symbol);
      setAddedResult(result);
      setQuery('');
      setDebouncedQuery('');
      onAdded();
    } catch {
      // error handled by mutation state
    }
  };

  const handleDirectAdd = async () => {
    if (!query.trim()) return;
    try {
      const result = await addMutation.mutateAsync(query.trim().toUpperCase());
      setAddedResult(result);
      setQuery('');
      setDebouncedQuery('');
      onAdded();
    } catch {
      // error handled by mutation state
    }
  };

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-3 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-[var(--color-text-primary)]">
          Add Ticker to Watchlist
        </span>
        <button
          onClick={onClose}
          className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
        >
          <X size={14} />
        </button>
      </div>

      {/* Search input */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => handleInputChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleDirectAdd();
              if (e.key === 'Escape') onClose();
            }}
            placeholder="Search by name or symbol (e.g. broadcom, INTC)..."
            className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-primary)] pl-7 pr-3 py-1.5 text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-accent-blue)] focus:outline-none"
          />
        </div>
        <button
          onClick={handleDirectAdd}
          disabled={!query.trim() || addMutation.isPending}
          className="flex items-center gap-1 rounded bg-[var(--color-accent-blue)] px-2.5 py-1.5 text-[10px] font-medium text-[var(--on-brand)] disabled:opacity-50"
        >
          {addMutation.isPending ? (
            <Loader2 size={10} className="animate-spin" />
          ) : (
            <Plus size={10} />
          )}
          Add
        </button>
      </div>

      {/* Search results dropdown */}
      {searchQuery.isLoading && debouncedQuery && (
        <div className="flex items-center gap-2 py-2 text-[10px] text-[var(--color-text-muted)]">
          <Loader2 size={10} className="animate-spin" />
          Searching...
        </div>
      )}

      {searchQuery.data && searchQuery.data.results.length > 0 && !addedResult && (
        <div className="max-h-48 overflow-y-auto rounded border border-[var(--color-border)] divide-y divide-[var(--color-border)]">
          {searchQuery.data.results.map((m) => (
            <button
              key={`${m.symbol}-${m.region}`}
              onClick={() => handleAdd(m)}
              disabled={addMutation.isPending}
              className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-[var(--color-bg-primary)] transition-colors disabled:opacity-50"
            >
              <span className="font-mono text-xs font-semibold text-[var(--color-text-primary)] min-w-[60px]">
                {m.symbol}
              </span>
              <span className="flex-1 truncate text-[11px] text-[var(--color-text-secondary)]">
                {m.name}
              </span>
              <span className="text-[9px] text-[var(--color-text-muted)]">
                {m.type} · {m.region}
              </span>
              <span className="text-[9px] tabular-nums text-[var(--color-text-muted)]">
                {(m.match_score * 100).toFixed(0)}%
              </span>
            </button>
          ))}
        </div>
      )}

      {searchQuery.data && searchQuery.data.results.length === 0 && debouncedQuery && !addedResult && (
        <div className="py-2 text-center text-[10px] text-[var(--color-text-muted)]">
          No matches for "{debouncedQuery}". Press Enter or Add to add it directly.
        </div>
      )}

      {/* Added result card */}
      {addedResult && <AddedTickerCard result={addedResult} />}

      {/* Error */}
      {addMutation.isError && (
        <div className="rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-[10px] text-red-300">
          Failed to add: {addMutation.error.message}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card shown after adding a ticker — shows info + quote from AV
// ---------------------------------------------------------------------------

function AddedTickerCard({ result }: { result: WatchlistAddResult }) {
  const { ticker, added, info, quote } = result;

  const fmtCap = (cap: string | null | undefined): string => {
    if (!cap) return '—';
    const n = Number(cap);
    if (isNaN(n)) return cap;
    if (n >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
    if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
    if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
    return `$${n.toLocaleString()}`;
  };

  const changeColor =
    quote?.change && quote.change > 0
      ? 'text-emerald-400'
      : quote?.change && quote.change < 0
      ? 'text-red-400'
      : 'text-[var(--color-text-secondary)]';

  return (
    <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3 space-y-2">
      <div className="flex items-center gap-2">
        <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-400">
          {added ? 'ADDED' : 'ALREADY ON WATCHLIST'}
        </span>
        <span className="font-mono text-sm font-bold text-[var(--color-text-primary)]">
          {ticker}
        </span>
        {info?.name && (
          <span className="text-xs text-[var(--color-text-secondary)]">
            {info.name}
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-4 text-[11px]">
        {info && (
          <>
            {info.exchange && (
              <div>
                <span className="text-[var(--color-text-muted)]">Exchange </span>
                <span className="text-[var(--color-text-secondary)]">{info.exchange}</span>
              </div>
            )}
            {info.sector && (
              <div>
                <span className="text-[var(--color-text-muted)]">Sector </span>
                <span className="text-[var(--color-text-secondary)]">{info.sector}</span>
              </div>
            )}
            {info.industry && (
              <div>
                <span className="text-[var(--color-text-muted)]">Industry </span>
                <span className="text-[var(--color-text-secondary)]">{info.industry}</span>
              </div>
            )}
            {info.market_cap && (
              <div>
                <span className="text-[var(--color-text-muted)]">Cap </span>
                <span className="text-[var(--color-text-secondary)]">{fmtCap(info.market_cap)}</span>
              </div>
            )}
            {info.asset_type && (
              <div>
                <span className="text-[var(--color-text-muted)]">Type </span>
                <span className="text-[var(--color-text-secondary)]">{info.asset_type}</span>
              </div>
            )}
          </>
        )}

        {quote && quote.price != null && (
          <>
            <div>
              <span className="text-[var(--color-text-muted)]">Price </span>
              <span className="font-mono font-semibold text-[var(--color-text-primary)]">
                ${quote.price.toFixed(2)}
              </span>
            </div>
            <div>
              <span className="text-[var(--color-text-muted)]">Change </span>
              <span className={`font-mono font-semibold ${changeColor}`}>
                {quote.change != null && quote.change > 0 ? '+' : ''}
                {quote.change?.toFixed(2)} ({quote.change_percent})
              </span>
            </div>
            <div>
              <span className="text-[var(--color-text-muted)]">Vol </span>
              <span className="text-[var(--color-text-secondary)]">
                {quote.volume?.toLocaleString()}
              </span>
            </div>
            <div>
              <span className="text-[var(--color-text-muted)]">Date </span>
              <span className="text-[var(--color-text-secondary)]">
                {quote.latest_trading_day}
              </span>
            </div>
          </>
        )}
      </div>

      {info?.description && (
        <p className="text-[10px] leading-relaxed text-[var(--color-text-muted)] line-clamp-2">
          {info.description}
        </p>
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
            <th className="text-right">0-1</th>
            <th className="text-right">x weight</th>
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
