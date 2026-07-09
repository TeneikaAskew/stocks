import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTickerStore } from '@/stores/tickerStore';
import {
  PlusCircle,
  Trash2,
  Download,
  TrendingUp,
  TrendingDown,
  FileDown,
  Database,
  HardDrive,
  AlertCircle,
} from 'lucide-react';
import { KpiTile, Card, CardHeader } from '@/components/primitives';
import { TickerCombobox } from '@/components/shared/TickerCombobox';
import { PriceAreaChart } from '@/components/charts/PriceAreaChart';
import { fmtPct, NA } from '@/lib/format';
import { computeJournalStats } from '@/lib/journalStats';

// ── Types ──────────────────────────────────────────────────────────────────

interface JournalEntry {
  id: string;
  ticker: string;
  direction: 'CALL' | 'PUT';
  entry_ts: string;          // ISO datetime
  exit_ts: string | null;    // null for active (unexited) trades
  entry_price: number;
  exit_price: number | null; // null for active (unexited) trades
  return_pct: number | null; // null for active (unexited) trades
  notes: string;
  created_at?: string;
  // Structural optionality — present on chart-marked trades, absent on
  // manually-logged ones. Not yet rendered beyond the status chip.
  take_profits?: number[];
  stop_loss?: number | null;
  status?: string;
  source?: string;
  session_id?: string | null;
}

interface JournalResponse {
  ticker: string;
  source: 'cloud_sql' | 'local';
  count: number;
  trades: JournalEntry[];
}

// ── localStorage cache helpers ─────────────────────────────────────────────
// Used ONLY as a placeholder while the API call is in flight (stale-while-revalidate).
const CACHE_KEY = (t: string) => `platform_journal_cache_${t}`;

function loadCache(ticker: string): JournalEntry[] {
  try { return JSON.parse(localStorage.getItem(CACHE_KEY(ticker)) ?? '[]'); }
  catch { return []; }
}
function saveCache(ticker: string, entries: JournalEntry[]) {
  try { localStorage.setItem(CACHE_KEY(ticker), JSON.stringify(entries)); }
  catch { /* ignore quota errors */ }
}

// ── Utility ────────────────────────────────────────────────────────────────

export function tsToDisplay(ts: string | null): { date: string; time: string } {
  if (ts == null) return { date: '—', time: '—' };
  const d = new Date(ts.replace('T', ' ').replace(' ', 'T'));
  return {
    date: isNaN(d.getTime()) ? ts.slice(0, 10) : d.toISOString().slice(0, 10),
    time: isNaN(d.getTime()) ? ts.slice(11, 16) : d.toISOString().slice(11, 16),
  };
}

export function tradesToCsv(entries: JournalEntry[]): string {
  const header = 'ID,Time,Trade_Type,Exit_Time,Stop_Loss_Time,Runner_Time\n';
  const rows = entries.map((e, i) => {
    const entry = tsToDisplay(e.entry_ts);
    // Active (null-exit) trades serialize as empty CSV cells, not "—"/"null".
    const exitCell = e.exit_ts == null ? '' : (() => {
      const exit = tsToDisplay(e.exit_ts);
      return `${exit.date} ${exit.time}:00`;
    })();
    return `${i + 1},${entry.date} ${entry.time}:00,${e.direction},${exitCell},,`;
  });
  return header + rows.join('\n');
}

function downloadCsv(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

const emptyForm = () => ({
  direction: 'CALL' as 'CALL' | 'PUT',
  entryDate: new Date().toISOString().slice(0, 10),
  entryTime: '09:30',
  entryPrice: '' as string | number,
  exitDate: new Date().toISOString().slice(0, 10),
  exitTime: '10:00',
  exitPrice: '' as string | number,
  notes: '',
});

// ── API hooks ──────────────────────────────────────────────────────────────

function useJournalTrades(ticker: string) {
  return useQuery<JournalResponse>({
    queryKey: ['journal', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/journal/trades/${ticker}`);
      if (!r.ok) throw new Error('Failed to fetch journal');
      const data: JournalResponse = await r.json();
      saveCache(ticker, data.trades);    // keep localStorage in sync
      return data;
    },
    placeholderData: () => ({
      ticker,
      source: 'local' as const,
      count: 0,
      trades: loadCache(ticker),         // show cached data while fetching
    }),
    staleTime: 30_000,
  });
}

function useAddTrade(ticker: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (form: ReturnType<typeof emptyForm>) => {
      const r = await fetch('/api/journal/trades', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker,
          direction: form.direction,
          entry_date: form.entryDate,
          entry_time: form.entryTime,
          entry_price: parseFloat(String(form.entryPrice)),
          exit_date: form.exitDate,
          exit_time: form.exitTime,
          exit_price: parseFloat(String(form.exitPrice)),
          notes: form.notes,
        }),
      });
      if (!r.ok) throw new Error('Failed to save trade');
      return r.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['journal', ticker] }),
  });
}

function useDeleteTrade(ticker: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const r = await fetch(`/api/journal/trades/${id}?ticker=${ticker}`, { method: 'DELETE' });
      if (!r.ok) throw new Error('Failed to delete');
      return r.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['journal', ticker] }),
  });
}

// ── Component ──────────────────────────────────────────────────────────────

export default function JournalPage() {
  const { activeTicker } = useTickerStore();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm());
  const [exportStatus, setExportStatus] = useState<string | null>(null);

  const { data, isLoading } = useJournalTrades(activeTicker);
  const addTrade = useAddTrade(activeTicker);
  const deleteTrade = useDeleteTrade(activeTicker);

  const entries = data?.trades ?? [];
  const source = data?.source ?? 'local';

  // Practice (bar-replay-trainer) trades are excluded from every stats
  // aggregate by default (Task 5.3) — "Include practice sessions" folds
  // them back in. Same scoping predicate as computeJournalStats internally
  // uses, so the Trades-tile win count below stays in lockstep with
  // closedCount/totalCount rather than drifting from a separately-scoped
  // filter.
  const [includeReplay, setIncludeReplay] = useState(false);
  const scopedEntries = includeReplay ? entries : entries.filter((e) => e.source !== 'replay');

  const stats = computeJournalStats(entries, { includeReplay });
  const { closedCount, totalCount, winRate, avgReturn, totalReturn, avgWin, equityPoints, replayExcludedCount } = stats;
  // Compute closed wins count for the Trades tile sub-label
  const wins = scopedEntries
    .filter((e): e is JournalEntry & { return_pct: number } =>
      typeof e.return_pct === 'number' && !Number.isNaN(e.return_pct) && e.return_pct > 0)
    .length;

  const handleAdd = () => {
    const ep = parseFloat(String(form.entryPrice));
    const xp = parseFloat(String(form.exitPrice));
    if (isNaN(ep) || isNaN(xp)) return;
    addTrade.mutate(form, {
      onSuccess: () => { setForm(emptyForm()); setShowForm(false); },
    });
  };

  const exportPipeline = async () => {
    const csv = tradesToCsv(entries);
    try {
      const r = await fetch(`/api/journal/export/${activeTicker}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trades: entries.map((e, i) => {
            const entry = tsToDisplay(e.entry_ts);
            // Active (null-exit) trades send null, never a fabricated "—" date.
            const exit  = e.exit_ts == null ? null : tsToDisplay(e.exit_ts);
            return {
              id: String(i + 1),
              ticker: e.ticker,
              direction: e.direction,
              entry_date: entry.date,
              entry_time: entry.time,
              entry_price: e.entry_price,
              exit_date: exit?.date ?? null,
              exit_time: exit?.time ?? null,
              exit_price: e.exit_price,
              notes: e.notes,
            };
          }),
        }),
      });
      if (r.ok) {
        const d = await r.json();
        setExportStatus(`Exported ${d.trades_exported} trades → ${d.filename}`);
      } else {
        downloadCsv(csv, `${activeTicker.toLowerCase()}_journal.csv`);
        setExportStatus('API unavailable — downloaded CSV locally');
      }
    } catch {
      downloadCsv(csv, `${activeTicker.toLowerCase()}_journal.csv`);
      setExportStatus('API unavailable — downloaded CSV locally');
    }
    setTimeout(() => setExportStatus(null), 5000);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-[22px] font-bold tracking-[-0.02em] text-[var(--on-surface)]">
            {activeTicker} Trade Journal
          </h1>
          <div className="mt-0.5 flex items-center gap-1.5 text-xs text-[var(--color-text-muted)]">
            {source === 'cloud_sql'
              ? <><Database size={11} className="text-[var(--bull)]" /> Persisted in Cloud SQL</>
              : <><HardDrive size={11} className="text-[var(--warn)]" /> Local storage (set CLOUD_SQL_CONNECTION_NAME for persistence)</>
            }
          </div>
        </div>
        <div className="flex items-center gap-2">
          <TickerCombobox />
          {entries.length > 0 && (
            <>
              <button
                onClick={() => downloadCsv(tradesToCsv(entries), `${activeTicker.toLowerCase()}_journal.csv`)}
                className="flex items-center gap-1.5 rounded border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]"
              >
                <Download size={13} /> CSV
              </button>
              <button
                onClick={exportPipeline}
                className="flex items-center gap-1.5 rounded border border-[var(--color-accent-blue)]/50 bg-[var(--color-accent-blue)]/10 px-3 py-1.5 text-xs text-[var(--color-accent-blue)] hover:bg-[var(--color-accent-blue)]/20"
              >
                <FileDown size={13} /> Export to Pipeline
              </button>
            </>
          )}
          <button
            onClick={() => setShowForm(s => !s)}
            className="flex items-center gap-1.5 rounded bg-[var(--color-accent-blue)] px-3 py-1.5 text-xs font-medium text-[var(--on-brand)] hover:opacity-90"
          >
            <PlusCircle size={13} /> Add Trade
          </button>
        </div>
      </div>

      {exportStatus && (
        <div className="flex items-center gap-2 rounded-lg border border-green-500/30 bg-green-500/10 p-3 text-xs text-[var(--bull)]">
          <AlertCircle size={14} /> {exportStatus}
        </div>
      )}

      {addTrade.isError && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-[var(--bear)]">
          <AlertCircle size={14} /> Failed to save trade — check API connection.
        </div>
      )}

      {/* Summary KPIs */}
      {entries.length > 0 && (
        <>
          <label className="flex w-fit items-center gap-1.5 text-xs text-[var(--color-text-secondary)]">
            <input
              type="checkbox"
              data-testid="include-replay-toggle"
              checked={includeReplay}
              onChange={(e) => setIncludeReplay(e.target.checked)}
              className="h-3.5 w-3.5 rounded border-[var(--color-border)]"
            />
            Include practice sessions
          </label>
          <div className="grid grid-cols-2 gap-[14px] md:grid-cols-3 lg:grid-cols-5">
            <KpiTile label="Trades" value={String(totalCount)} sub={`${wins}W / ${closedCount - wins}L`} />
            <KpiTile label="Win rate" value={winRate !== null ? `${winRate.toFixed(0)}%` : NA} tone={(winRate ?? 0) >= 50 ? 'bull' : 'bear'} />
            <KpiTile label="Total P&L" value={fmtPct(totalReturn)} tone={(totalReturn ?? 0) >= 0 ? 'bull' : 'bear'} />
            <KpiTile label="Avg / trade" value={fmtPct(avgReturn)} tone={(avgReturn ?? 0) >= 0 ? 'bull' : 'bear'} />
            <KpiTile label="Avg win" value={fmtPct(avgWin)} tone="bull" />
          </div>
          {closedCount < totalCount && (
            <p className="text-[11px] text-[var(--on-surface-muted)]">
              {totalCount - closedCount} open/unreturned trade(s) excluded from stats
            </p>
          )}
          {!includeReplay && replayExcludedCount > 0 && (
            <p data-testid="replay-exclusion-note" className="text-[11px] text-[var(--on-surface-muted)]">
              {replayExcludedCount} practice trade{replayExcludedCount === 1 ? '' : 's'} excluded from stats — toggle
              "Include practice sessions" to include them.
            </p>
          )}
        </>
      )}

      {/* Equity curve — cumulative P&L across closed trades */}
      {equityPoints.length > 1 && (
        <Card>
          <CardHeader title={`${activeTicker} equity curve`} meta="cumulative P&L %" />
          <PriceAreaChart
            data={equityPoints}
            seriesLabel="Cumulative P&L"
            height={240}
            valueFormatter={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`}
            tooltipFormatter={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`}
          />
        </Card>
      )}

      {/* Add Trade Form */}
      {showForm && (
        <div className="rounded-xl bg-[var(--surface-2)] p-4">
          <h3 className="mb-3 text-sm font-semibold text-[var(--color-text-primary)]">
            New Trade — {activeTicker}
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Direction</label>
              <div className="flex gap-2">
                {(['CALL', 'PUT'] as const).map(d => (
                  <button
                    key={d}
                    onClick={() => setForm(f => ({ ...f, direction: d }))}
                    className={`flex items-center gap-1.5 rounded border px-4 py-1.5 text-sm font-bold transition-colors ${
                      form.direction === d
                        ? d === 'CALL'
                          ? 'border-green-500 bg-green-500/20 text-[var(--bull)]'
                          : 'border-red-500 bg-red-500/20 text-[var(--bear)]'
                        : 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:bg-[var(--color-bg-tertiary)]'
                    }`}
                  >
                    {d === 'CALL' ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                    {d}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Entry Date</label>
              <input type="date" value={form.entryDate}
                onChange={e => setForm(f => ({ ...f, entryDate: e.target.value }))}
                className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-2 py-1.5 text-xs text-[var(--color-text-primary)]"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Entry Time</label>
              <input type="time" value={form.entryTime}
                onChange={e => setForm(f => ({ ...f, entryTime: e.target.value }))}
                className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-2 py-1.5 text-xs text-[var(--color-text-primary)]"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Entry Price ($)</label>
              <input type="number" step="0.01" placeholder="0.00" value={form.entryPrice}
                onChange={e => setForm(f => ({ ...f, entryPrice: e.target.value }))}
                className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-2 py-1.5 text-xs font-mono text-[var(--color-text-primary)]"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Exit Date</label>
              <input type="date" value={form.exitDate}
                onChange={e => setForm(f => ({ ...f, exitDate: e.target.value }))}
                className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-2 py-1.5 text-xs text-[var(--color-text-primary)]"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Exit Time</label>
              <input type="time" value={form.exitTime}
                onChange={e => setForm(f => ({ ...f, exitTime: e.target.value }))}
                className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-2 py-1.5 text-xs text-[var(--color-text-primary)]"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Exit Price ($)</label>
              <input type="number" step="0.01" placeholder="0.00" value={form.exitPrice}
                onChange={e => setForm(f => ({ ...f, exitPrice: e.target.value }))}
                className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-2 py-1.5 text-xs font-mono text-[var(--color-text-primary)]"
              />
            </div>

            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">Notes (optional)</label>
              <textarea rows={2} placeholder="Setup rationale, conditions met, what you noticed..."
                value={form.notes}
                onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                className="w-full resize-none rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-2 py-1.5 text-xs text-[var(--color-text-primary)]"
              />
            </div>
          </div>

          <div className="mt-3 flex justify-end gap-2">
            <button onClick={() => setShowForm(false)}
              className="rounded px-3 py-1.5 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-bg-tertiary)]"
            >
              Cancel
            </button>
            <button onClick={handleAdd}
              disabled={!form.entryPrice || !form.exitPrice || addTrade.isPending}
              className="rounded bg-[var(--color-accent-blue)] px-4 py-1.5 text-xs font-medium text-[var(--on-brand)] hover:opacity-90 disabled:opacity-40"
            >
              {addTrade.isPending ? 'Saving…' : 'Save Trade'}
            </button>
          </div>
        </div>
      )}

      {/* Trade table */}
      {isLoading && entries.length === 0 ? (
        <div className="rounded-xl bg-[var(--surface-2)] p-8 text-center text-sm text-[var(--color-text-muted)]">
          Loading journal…
        </div>
      ) : entries.length === 0 && !showForm ? (
        <div className="rounded-xl bg-[var(--surface-2)] p-10 text-center">
          <p className="text-sm text-[var(--color-text-muted)]">No trades logged for {activeTicker} yet.</p>
          <button onClick={() => setShowForm(true)}
            className="mx-auto mt-3 flex items-center gap-1.5 rounded bg-[var(--color-accent-blue)] px-4 py-2 text-xs font-medium text-[var(--on-brand)] hover:opacity-90"
          >
            <PlusCircle size={13} /> Log Your First Trade
          </button>
        </div>
      ) : (
        entries.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
            <table className="w-full text-left">
              <thead className="bg-[var(--color-bg-tertiary)]">
                <tr>
                  {['Date', 'Dir', 'Entry', 'Entry $', 'Exit', 'Exit $', 'Return', 'Notes', ''].map(h => (
                    <th key={h} className="px-3 py-2 text-xs font-medium text-[var(--color-text-muted)]">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {entries.map(e => {
                  const entry = tsToDisplay(e.entry_ts);
                  const exit  = tsToDisplay(e.exit_ts);
                  const ret   = e.return_pct;
                  const isActive = e.status === 'active' || e.exit_ts == null;
                  return (
                    <tr key={e.id} className="hover:bg-[var(--color-bg-tertiary)]">
                      <td className="px-3 py-1.5 font-mono text-[10px] text-[var(--color-text-secondary)]">{entry.date}</td>
                      <td className="px-3 py-1.5">
                        <span className={`text-xs font-bold ${e.direction === 'CALL' ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}`}>
                          {e.direction}
                        </span>
                        {isActive && (
                          <span className="ml-1.5 rounded bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-medium text-amber-500/70">
                            active
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-1.5 font-mono text-[10px] text-[var(--color-text-muted)]">{entry.time}</td>
                      <td className="px-3 py-1.5 font-mono text-xs text-[var(--color-text-primary)]">${e.entry_price.toFixed(2)}</td>
                      <td className="px-3 py-1.5 font-mono text-[10px] text-[var(--color-text-muted)]">{exit.time}</td>
                      <td className="px-3 py-1.5 font-mono text-xs text-[var(--color-text-primary)]">
                        {e.exit_price == null ? (
                          <span className="text-[var(--on-surface-muted)]">—</span>
                        ) : (
                          `$${e.exit_price.toFixed(2)}`
                        )}
                      </td>
                      <td className="px-3 py-1.5">
                        {ret == null ? (
                          <span className="text-[var(--on-surface-muted)]">—</span>
                        ) : (
                          <span className={`font-mono text-xs font-medium ${ret >= 0 ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}`}>
                            {ret >= 0 ? '+' : ''}{ret.toFixed(2)}%
                          </span>
                        )}
                      </td>
                      <td className="max-w-[200px] truncate px-3 py-1.5 text-xs text-[var(--color-text-muted)]">{e.notes || '—'}</td>
                      <td className="px-3 py-1.5">
                        <button
                          onClick={() => deleteTrade.mutate(e.id)}
                          disabled={deleteTrade.isPending}
                          className="text-[var(--color-text-muted)] hover:text-[var(--bear)] disabled:opacity-40"
                        >
                          <Trash2 size={12} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  );
}
