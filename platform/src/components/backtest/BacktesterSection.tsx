import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '@/components/shared/MetricCard';
import { chartTheme } from '@/lib/chartTheme';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table';
import { ChevronUp, ChevronDown, AlertTriangle } from 'lucide-react';

// ── Types (match actual API responses) ────────────────────────────────────────

interface BacktestRun {
  filename: string;
  timestamp: string;
  modified: string;
  row_count: number;
  trade_count: number;
  win_rate: number | null;
  avg_return_pct: number | null;
  has_equity_curve: boolean;
}

interface BacktestAllResponse {
  ticker: string;
  total_runs: number;
  runs: BacktestRun[];
}

interface TradeRow {
  entry_time: string;
  exit_time: string;
  direction: string;
  entry_price: number;
  exit_price: number;
  exit_reason: string;
  return_pct: number;
  base_score: number;
  strat_bonus: number;
  total_score: number;
  [key: string]: unknown;
}

interface BacktestSummary {
  total_trades: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  avg_return_pct: number;
  avg_win_pct: number | null;
  avg_loss_pct: number | null;
  total_return_pct: number;
}

interface BacktestResultsResponse {
  ticker: string;
  filename: string;
  trade_count: number;
  summary: BacktestSummary;
  trades: TradeRow[];
}

interface EquitySummary {
  start_value: number;
  end_value: number;
  peak_value: number;
  total_return_pct: number;
  max_drawdown_pct: number;
  data_points: number;
}

interface EquityResponse {
  ticker: string;
  filename: string;
  summary: EquitySummary;
  dates: string[];
  values: (number | null)[];
}

// ── Hooks ──────────────────────────────────────────────────────────────────

function useBacktestList(ticker: string) {
  return useQuery<BacktestAllResponse>({
    queryKey: ['backtest-list', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/backtest/all/${ticker}`);
      if (!r.ok) throw new Error('Failed');
      return r.json();
    },
    staleTime: 30_000,
  });
}

function useBacktestResults(ticker: string, enabled: boolean) {
  return useQuery<BacktestResultsResponse>({
    queryKey: ['backtest-results', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/backtest/results/${ticker}`);
      if (!r.ok) throw new Error('Failed');
      return r.json();
    },
    enabled,
    staleTime: 30_000,
  });
}

function useEquity(ticker: string, enabled: boolean) {
  return useQuery<EquityResponse>({
    queryKey: ['backtest-equity', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/backtest/equity/${ticker}`);
      if (!r.ok) throw new Error('Failed');
      return r.json();
    },
    enabled,
    staleTime: 30_000,
  });
}

// ── Equity Chart ──────────────────────────────────────────────────────────

function EquityCurve({ equity }: { equity: EquityResponse }) {
  const chartData = equity.dates.map((d, i) => ({
    date: String(d).slice(0, 10),
    value: equity.values[i],
  }));

  const { total_return_pct, max_drawdown_pct, peak_value } = equity.summary;

  return (
    <div className="rounded-xl bg-[var(--surface-2)] p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-medium text-[var(--color-text-primary)]">Equity Curve</h3>
        <div className="flex gap-4 text-xs">
          <span className={total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}>
            Total: {total_return_pct >= 0 ? '+' : ''}{total_return_pct.toFixed(1)}%
          </span>
          <span className="text-red-400">
            Max DD: -{Math.abs(max_drawdown_pct).toFixed(1)}%
          </span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={chartTheme.brand} stopOpacity={0.25} />
              <stop offset="95%" stopColor={chartTheme.brand} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: chartTheme.axisSize, fill: chartTheme.axis }}
            tickFormatter={d => String(d).slice(5)}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: chartTheme.axisSize, fill: chartTheme.axis }}
            tickFormatter={v => `$${Number(v).toFixed(0)}`}
          />
          <Tooltip
            contentStyle={{ background: '#0f0f1a', border: `1px solid ${chartTheme.border}`, fontSize: 11 }}
            labelStyle={{ color: '#9898b0' }}
            formatter={(v) => [`$${(Number(v) || 0).toFixed(2)}`, 'Value' as const]}
          />
          <ReferenceLine y={peak_value} stroke={chartTheme.warn} strokeDasharray="4 2" strokeWidth={1} />
          <Area
            type="monotone"
            dataKey="value"
            stroke={chartTheme.brand}
            strokeWidth={1.5}
            fill="url(#eqGrad)"
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Trade Table ────────────────────────────────────────────────────────────

const columnHelper = createColumnHelper<TradeRow>();

const columns = [
  columnHelper.accessor('entry_time', {
    header: 'Entry',
    cell: i => <span className="font-mono text-[10px]">{String(i.getValue()).slice(0, 16)}</span>,
  }),
  columnHelper.accessor('direction', {
    header: 'Dir',
    cell: i => (
      <span className={`text-xs font-bold ${String(i.getValue()) === 'CALL' ? 'text-green-400' : 'text-red-400'}`}>
        {String(i.getValue())}
      </span>
    ),
  }),
  columnHelper.accessor('entry_price', {
    header: 'Entry $',
    cell: i => <span className="font-mono text-xs">${Number(i.getValue()).toFixed(2)}</span>,
  }),
  columnHelper.accessor('exit_price', {
    header: 'Exit $',
    cell: i => <span className="font-mono text-xs">${Number(i.getValue()).toFixed(2)}</span>,
  }),
  columnHelper.accessor('return_pct', {
    header: 'Return %',
    cell: i => {
      const v = Number(i.getValue());
      return (
        <span className={`font-mono text-xs font-medium ${v >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {v >= 0 ? '+' : ''}{v.toFixed(2)}%
        </span>
      );
    },
  }),
  columnHelper.accessor('exit_reason', {
    header: 'Exit',
    cell: i => <span className="text-xs text-[var(--color-text-muted)]">{String(i.getValue())}</span>,
  }),
  columnHelper.accessor('total_score', {
    header: 'Score',
    cell: i => <span className="font-mono text-xs">{Number(i.getValue()).toFixed(1)}</span>,
  }),
];

function TradeTable({ trades }: { trades: TradeRow[] }) {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'entry_time', desc: true }]);

  const table = useReactTable({
    data: trades,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
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
          {table.getRowModel().rows.slice(0, 200).map(row => (
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
      {trades.length > 200 && (
        <div className="px-3 py-2 text-xs text-[var(--color-text-muted)]">
          Showing first 200 of {trades.length} trades
        </div>
      )}
    </div>
  );
}

// ── Section ────────────────────────────────────────────────────────────────

export default function BacktesterSection({ ticker }: { ticker: string }) {
  const { data: listData, isLoading: listLoading, isError: listError } = useBacktestList(ticker);
  const runs = listData?.runs ?? [];
  const hasData = runs.length > 0;
  const latestRun = runs[0];

  const { data: results, isLoading: resultsLoading, isError: resultsError } = useBacktestResults(
    ticker,
    !listLoading,
  );
  const { data: equity } = useEquity(
    ticker,
    hasData && (latestRun?.has_equity_curve ?? false),
  );

  const summary = results?.summary;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-bold text-[var(--color-text-primary)]">
          {ticker} Backtester
        </h2>
        <p className="text-xs text-[var(--color-text-muted)]">
          {hasData
            ? `${runs.length} backtest run${runs.length > 1 ? 's' : ''} — most recent: ${latestRun?.timestamp ?? ''}`
            : 'No backtest results found'}
        </p>
      </div>

      {(listError || resultsError) && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-400">
          <AlertTriangle size={16} />
          No backtest results for {ticker}. Run{' '}
          <code className="font-mono">scripts/run_backtest.py --ticker {ticker}</code> first.
        </div>
      )}

      {(resultsLoading || listLoading) && !listError && !resultsError && (
        <div className="rounded-xl bg-[var(--surface-2)] p-8 text-center text-sm text-[var(--color-text-muted)]">
          Loading backtest data…
        </div>
      )}

      {summary && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          <MetricCard label="Total Trades" value={String(summary.total_trades)} />
          <MetricCard
            label="Win Rate"
            value={`${(summary.win_rate * 100).toFixed(1)}%`}
            change={summary.win_rate >= 0.5 ? 1 : -1}
          />
          <MetricCard
            label="Avg Return"
            value={`${summary.avg_return_pct >= 0 ? '+' : ''}${summary.avg_return_pct.toFixed(2)}%`}
            change={summary.avg_return_pct >= 0 ? 1 : -1}
          />
          <MetricCard
            label="Avg Win"
            value={summary.avg_win_pct != null ? `+${summary.avg_win_pct.toFixed(2)}%` : '--'}
            change={1}
          />
          <MetricCard
            label="Avg Loss"
            value={summary.avg_loss_pct != null ? `${summary.avg_loss_pct.toFixed(2)}%` : '--'}
            change={-1}
          />
        </div>
      )}

      {equity && <EquityCurve equity={equity} />}

      {results && results.trades.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-medium text-[var(--color-text-primary)]">
            Trade Log ({results.trades.length} trades)
          </h3>
          <TradeTable trades={results.trades} />
        </div>
      )}
    </div>
  );
}
