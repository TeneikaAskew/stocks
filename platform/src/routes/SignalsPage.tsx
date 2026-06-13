import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTickerStore } from '@/stores/tickerStore';
import { useReviewDateStore } from '@/stores/reviewDateStore';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
  type ColumnFiltersState,
} from '@tanstack/react-table';
import { ChevronUp, ChevronDown, Filter, AlertTriangle } from 'lucide-react';
import { useTradeSummary } from '@/hooks/useTradeAnalytics';
import { KpiTile, MicroLabel } from '@/components/primitives';
import { TickerSelect } from '@/components/shared/TickerSelect';
import { fmtPct, fmtNum } from '@/lib/format';

// ── Types ──────────────────────────────────────────────────────────────────
interface SignalRow {
  time: string;
  ticker: string;
  direction: string;
  score: number;
  rsi: number | null;
  ema9: number | null;
  ema20: number | null;
  close: number | null;
  volume: number | null;
  [key: string]: unknown;
}

interface SignalsResponse {
  ticker: string;
  count: number;
  signals: SignalRow[];
}

function useSignals(ticker: string, endDate: string | null, endTime: string | null) {
  return useQuery<SignalsResponse>({
    queryKey: ['signals', ticker, endDate ?? 'live', endTime ?? 'eod'],
    queryFn: async () => {
      const params = new URLSearchParams({ limit: '5000' });
      if (endDate) params.set('end_date', endDate);
      if (endTime) params.set('end_time', endTime);
      const r = await fetch(`/api/signals/${ticker}?${params.toString()}`);
      if (!r.ok) throw new Error('Failed to fetch signals');
      return r.json();
    },
    staleTime: 300_000,
  });
}

// ── Column definitions ─────────────────────────────────────────────────────
const columnHelper = createColumnHelper<SignalRow>();

const columns = [
  columnHelper.accessor('time', {
    header: 'Time',
    cell: i => <span className="font-mono text-[10px] text-[var(--color-text-muted)]">{String(i.getValue()).slice(0, 16)}</span>,
  }),
  columnHelper.accessor('direction', {
    header: 'Dir',
    cell: i => (
      <span className={`text-xs font-bold ${String(i.getValue()) === 'CALL' ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}`}>
        {String(i.getValue())}
      </span>
    ),
    filterFn: (row, _colId, filterValue) =>
      filterValue === 'ALL' || String(row.original.direction) === filterValue,
  }),
  columnHelper.accessor('score', {
    header: 'Score',
    cell: i => {
      const v = Number(i.getValue());
      return (
        <span className={`font-mono text-xs font-medium ${v >= 7 ? 'text-[var(--bull)]' : v >= 5 ? 'text-[var(--warn)]' : 'text-[var(--color-text-muted)]'}`}>
          {v.toFixed(1)}
        </span>
      );
    },
  }),
  columnHelper.accessor('close', {
    header: 'Price',
    cell: i => {
      const v = i.getValue();
      return <span className="font-mono text-xs">{v != null ? `$${Number(v).toFixed(2)}` : '--'}</span>;
    },
  }),
  columnHelper.accessor('rsi', {
    header: 'RSI',
    cell: i => {
      const v = i.getValue();
      if (v == null) return <span className="text-xs text-[var(--color-text-muted)]">--</span>;
      const n = Number(v);
      return (
        <span className={`font-mono text-xs ${n > 70 ? 'text-[var(--bear)]' : n < 30 ? 'text-[var(--bull)]' : 'text-[var(--color-text-secondary)]'}`}>
          {n.toFixed(1)}
        </span>
      );
    },
  }),
  columnHelper.accessor('ema9', {
    header: 'EMA9',
    cell: i => {
      const v = i.getValue();
      return <span className="font-mono text-xs text-[var(--color-text-muted)]">{v != null ? `$${Number(v).toFixed(2)}` : '--'}</span>;
    },
  }),
  columnHelper.accessor('volume', {
    header: 'Volume',
    cell: i => {
      const v = i.getValue();
      if (v == null) return <span className="text-xs text-[var(--color-text-muted)]">--</span>;
      const n = Number(v);
      return <span className="font-mono text-xs text-[var(--color-text-muted)]">{n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : `${(n / 1_000).toFixed(0)}K`}</span>;
    },
  }),
];

// ── Page ──────────────────────────────────────────────────────────────────
export default function SignalsPage() {
  const { activeTicker } = useTickerStore();
  const { reviewDate, reviewTime } = useReviewDateStore();
  const isReview = reviewDate !== null;

  const [sorting, setSorting] = useState<SortingState>([{ id: 'time', desc: true }]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [dirFilter, setDirFilter] = useState<'ALL' | 'CALL' | 'PUT'>('ALL');
  const [minScore, setMinScore] = useState(0);
  const [localDateFrom, setLocalDateFrom] = useState('');
  const [localDateTo, setLocalDateTo] = useState('');

  // In review mode, dateTo is controlled by the global store. dateFrom is left alone.
  const effectiveDateTo = isReview ? (reviewDate ?? '') : localDateTo;
  const dateFrom = localDateFrom;
  const dateTo = effectiveDateTo;

  // Server-side filter in review mode (faster than client on 330K rows)
  const { data, isLoading, isError } = useSignals(
    activeTicker,
    isReview ? reviewDate : null,
    isReview ? reviewTime : null
  );
  const allSignals = data?.signals ?? [];

  // 90-day backtest P&L summary (server-computed; no duplicate TS math).
  const { data: pnl } = useTradeSummary(activeTicker);

  // Client-side filtering (still used for direction/score + local date range)
  const filtered = useMemo(() => {
    let rows = allSignals;
    if (dirFilter !== 'ALL') rows = rows.filter(r => r.direction === dirFilter);
    if (minScore > 0) rows = rows.filter(r => Number(r.score) >= minScore);
    if (dateFrom) rows = rows.filter(r => String(r.time).slice(0, 10) >= dateFrom);
    if (dateTo) rows = rows.filter(r => String(r.time).slice(0, 10) <= dateTo);
    return rows;
  }, [allSignals, dirFilter, minScore, dateFrom, dateTo]);

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting, columnFilters },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  const displayRows = table.getRowModel().rows.slice(0, 500);

  return (
    <div className="space-y-5">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-[22px] font-bold tracking-[-0.02em] text-[var(--on-surface)]">Signals</h1>
          <MicroLabel className="mt-1">
            {activeTicker} ·{' '}
            {data ? `${data.count.toLocaleString()} signals` : 'signal explorer'}
            {data && filtered.length !== allSignals.length ? ` · ${filtered.length.toLocaleString()} shown` : ''}
          </MicroLabel>
        </div>
        <TickerSelect />
      </div>

      {/* ── Performance summary (90-day backtest) ───────────────────────── */}
      {pnl && pnl.closedTrades > 0 && (() => {
        const wr = pnl.winRate <= 1 ? pnl.winRate * 100 : pnl.winRate;
        return (
          <div>
            <MicroLabel className="mb-2">Performance · 90-day backtest</MicroLabel>
            <div className="grid grid-cols-2 gap-[14px] md:grid-cols-3 lg:grid-cols-5">
              <KpiTile label="Win rate" value={`${wr.toFixed(1)}%`} tone={wr >= 50 ? 'bull' : 'bear'} sub={`${pnl.winCount}W / ${pnl.lossCount}L`} />
              <KpiTile label="Total P&L" value={fmtPct(pnl.totalPnL)} tone={pnl.totalPnL >= 0 ? 'bull' : 'bear'} />
              <KpiTile label="Avg / trade" value={fmtPct(pnl.avgPnL)} tone={pnl.avgPnL >= 0 ? 'bull' : 'bear'} />
              <KpiTile label="Profit factor" value={fmtNum(pnl.profitFactor, 2)} tone={(pnl.profitFactor ?? 0) >= 1 ? 'bull' : 'bear'} />
              <KpiTile label="Closed trades" value={pnl.closedTrades.toLocaleString()} sub={`${pnl.callCount} call · ${pnl.putCount} put`} />
            </div>
          </div>
        );
      })()}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl bg-[var(--surface-2)] px-3 py-2">
        <Filter size={14} className="text-[var(--color-text-muted)]" />

        {/* Direction */}
        <div className="flex rounded border border-[var(--color-border)] overflow-hidden">
          {(['ALL', 'CALL', 'PUT'] as const).map(d => (
            <button
              key={d}
              onClick={() => setDirFilter(d)}
              className={`px-2.5 py-1 text-xs font-medium ${
                dirFilter === d
                  ? 'bg-[var(--color-accent-blue)] text-[var(--on-brand)]'
                  : 'bg-transparent text-[var(--color-text-secondary)]'
              }`}
            >
              {d}
            </button>
          ))}
        </div>

        {/* Score filter */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-[var(--color-text-muted)]">Min score:</span>
          <select
            value={minScore}
            onChange={e => setMinScore(Number(e.target.value))}
            className="rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-2 py-1 text-xs text-[var(--color-text-primary)]"
          >
            <option value={0}>Any</option>
            <option value={5}>5+</option>
            <option value={6}>6+</option>
            <option value={7}>7+</option>
            <option value={8}>8+</option>
          </select>
        </div>

        {/* Date range */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-[var(--color-text-muted)]">From:</span>
          <input
            type="date"
            value={dateFrom}
            onChange={e => setLocalDateFrom(e.target.value)}
            className="rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-2 py-1 text-xs text-[var(--color-text-primary)]"
          />
        </div>
        <div className="flex items-center gap-1">
          <span className="text-xs text-[var(--color-text-muted)]">To:</span>
          <input
            type="date"
            value={dateTo}
            disabled={isReview}
            onChange={e => setLocalDateTo(e.target.value)}
            className="rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-2 py-1 text-xs text-[var(--color-text-primary)] disabled:opacity-50 disabled:cursor-not-allowed"
            title={isReview ? 'Set by global historical mode — clear review mode to edit' : undefined}
          />
          {isReview && (
            <span className="text-[10px] text-[var(--warn)]">global</span>
          )}
        </div>

        {(dirFilter !== 'ALL' || minScore > 0 || dateFrom || (!isReview && dateTo)) && (
          <button
            onClick={() => { setDirFilter('ALL'); setMinScore(0); setLocalDateFrom(''); setLocalDateTo(''); }}
            className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
          >
            Clear
          </button>
        )}
      </div>

      {isError && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-[var(--warn)]">
          <AlertTriangle size={16} />
          Signal data not found for {activeTicker}. Run the signals generation pipeline first.
        </div>
      )}

      {isLoading && (
        <div className="rounded-xl bg-[var(--surface-2)] p-8 text-center text-sm text-[var(--color-text-muted)]">
          Loading signals…
        </div>
      )}

      {!isLoading && !isError && (
        <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
          <table className="w-full text-left">
            <thead className="bg-[var(--color-bg-tertiary)]">
              {table.getHeaderGroups().map(hg => (
                <tr key={hg.id}>
                  {hg.headers.map(h => (
                    <th
                      key={h.id}
                      onClick={h.column.getToggleSortingHandler()}
                      className="cursor-pointer select-none px-3 py-2 text-xs font-medium text-[var(--color-text-muted)]"
                    >
                      <div className="flex items-center gap-1">
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        {h.column.getIsSorted() === 'asc' && <ChevronUp size={12} />}
                        {h.column.getIsSorted() === 'desc' && <ChevronDown size={12} />}
                      </div>
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {displayRows.map(row => (
                <tr key={row.id} className="hover:bg-[var(--color-bg-tertiary)]">
                  {row.getVisibleCells().map(cell => (
                    <td key={cell.id} className="px-3 py-1.5">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div className="px-3 py-6 text-center text-xs text-[var(--color-text-muted)]">
              No signals match your filters
            </div>
          )}
          {filtered.length > 500 && (
            <div className="px-3 py-2 text-xs text-[var(--color-text-muted)]">
              Showing first 500 of {filtered.length.toLocaleString()} signals
            </div>
          )}
        </div>
      )}
    </div>
  );
}
