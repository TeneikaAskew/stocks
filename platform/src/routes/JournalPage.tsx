import { useMemo, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTickerStore } from '@/stores/tickerStore';
import { useSettingsStore } from '@/stores/settingsStore';
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
  Crosshair,
  ArrowUpCircle,
  ArrowDownCircle,
  X,
  Eye,
  EyeOff,
  Clock,
  Upload,
} from 'lucide-react';
import { KpiTile, Card, CardHeader } from '@/components/primitives';
import { TickerCombobox } from '@/components/shared/TickerCombobox';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { PriceAreaChart } from '@/components/charts/PriceAreaChart';
import {
  TradeMarkingChart,
  type TradeMarkingChartHandle,
} from '@/components/journal/TradeMarkingChart';
import { TradeRailCard } from '@/components/journal/TradeRailCard';
import { ImportTradesModal } from '@/components/journal/ImportTradesModal';
import type { DrawingStep } from '@/hooks/useTradeMarking';
import { useMarketData, useAvailableDates } from '@/hooks/useMarketData';
import {
  useJournalTradesFull,
  useJournalExamples,
  useCreateChartTrade,
  useCloseChartTrade,
  useDeleteChartTrade,
  journalRowToTradeEntry,
  epochToJournalDateTime,
  resolveJournalView,
  chartTradesKey,
  type JournalRow,
  type JournalView,
} from '@/hooks/useJournalChartTrades';
import { fmtPct, NA } from '@/lib/format';
import { computeJournalStats } from '@/lib/journalStats';
import { riskReward } from '@/lib/risk';
import { todayET } from '@/lib/dates';
import type { Timeframe } from '@/types';

// ── Utility (exported, unit-tested in journalNullSafety.test.ts) ───────────

export function tsToDisplay(ts: string | null): { date: string; time: string } {
  if (ts == null) return { date: '—', time: '—' };
  const d = new Date(ts.replace('T', ' ').replace(' ', 'T'));
  return {
    date: isNaN(d.getTime()) ? ts.slice(0, 10) : d.toISOString().slice(0, 10),
    time: isNaN(d.getTime()) ? ts.slice(11, 16) : d.toISOString().slice(11, 16),
  };
}

export function tradesToCsv(entries: JournalRow[]): string {
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

// The `/api/journal/export/{ticker}` endpoint's `JournalTradeExportItem`
// model requires exit_date/exit_time/exit_price (server-side 422 pinned in
// tests/test_journal_phase2.py::test_export_endpoint_422s_for_active_shaped_item),
// so an active (unexited) trade has nothing to export — filter it out before
// the pipeline POST, never send a partial row and rely on the server to reject it.
export function exportableTrades(entries: JournalRow[]): JournalRow[] {
  return entries.filter((e) => e.status !== 'active' && e.exit_ts != null);
}

function downloadCsv(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

// #702 follow-ups Task 4 item 1: the form's default dates used
// `new Date().toISOString()`, which is UTC and is wrong for 4-5 hours every
// evening (see lib/dates.ts's header comment) — a trader logging a trade at
// 8pm ET would default to tomorrow's date. `todayET()` is the one source of
// truth for "today" on the market calendar; exported as a pure helper so the
// ET-alignment is testable without mounting the form.
export function defaultFormDates(): { entryDate: string; exitDate: string } {
  const d = todayET();
  return { entryDate: d, exitDate: d };
}

const emptyForm = () => {
  const { entryDate, exitDate } = defaultFormDates();
  return {
    direction: 'CALL' as 'CALL' | 'PUT',
    entryDate,
    entryTime: '09:30',
    entryPrice: '' as string | number,
    exitDate,
    exitTime: '10:00',
    exitPrice: '' as string | number,
    notes: '',
  };
};

// Date format helpers: YYYYMMDD <-> YYYY-MM-DD (same as ChartsPage).
const toInputFormat = (d: string) =>
  d ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}` : '';
const toApiFormat = (d: string) => d.replace(/-/g, '');

const TIMEFRAMES: { value: Timeframe; label: string }[] = [
  { value: '1', label: '1m' },
  { value: '5', label: '5m' },
  { value: '15', label: '15m' },
  { value: '30', label: '30m' },
  { value: '60', label: '1h' },
];

// ── Manual Add-Trade mutation ──────────────────────────────────────────────
// Invalidates chartTradesKey — the ONE cache entry the chart, rail, tiles
// and table all read from (useJournalTradesFull shares it), so a manual add
// shows up everywhere without a second fetch path that could go stale.

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
    onSuccess: () => qc.invalidateQueries({ queryKey: chartTradesKey(ticker) }),
  });
}

// ── Component ──────────────────────────────────────────────────────────────

export default function JournalPage() {
  const { activeTicker } = useTickerStore();
  const { timeframe, setTimeframe } = useSettingsStore();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm());
  const [exportStatus, setExportStatus] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);

  // ── Dates + market data (chart) ─────────────────────────────────────────
  // selectedDate === '' is the "Overview" cleared state: KPI tiles + table
  // aggregate over ALL dates; the chart still needs a concrete session, so
  // it falls back to the newest available date.
  const [selectedDate, setSelectedDate] = useState('');
  const { data: datesData } = useAvailableDates(activeTicker);
  const dates = datesData?.dates ?? []; // YYYYMMDD, sorted DESC
  const chartDate = selectedDate || (dates[0] ?? '');
  const chartIsoDate = chartDate ? toInputFormat(chartDate) : '';
  const scopeIso = selectedDate ? toInputFormat(selectedDate) : null;
  const minDate = dates.length > 0 ? toInputFormat(dates[dates.length - 1]) : '';
  const maxDate = dates.length > 0 ? toInputFormat(dates[0]) : '';

  const { data: marketData, isLoading: chartLoading, error: chartError } = useMarketData(
    activeTicker,
    chartDate,
    timeframe,
  );

  // Chart toggles (same semantics as ChartsPage's toolbar).
  const [showVolume, setShowVolume] = useState(true);
  const [rthOnly, setRthOnly] = useState(true);

  // ── Own journal + Examples (view state) ─────────────────────────────────
  const ownQuery = useJournalTradesFull(activeTicker);
  const examplesQuery = useJournalExamples(activeTicker);
  const ownRows = useMemo(() => ownQuery.data?.trades ?? [], [ownQuery.data]);
  const exampleRows = useMemo(() => examplesQuery.data?.trades ?? [], [examplesQuery.data]);
  const source = ownQuery.data?.source ?? 'local';

  // Manual toggle is sticky for the session; until the user touches it, the
  // view follows the default rule (Examples while own journal is empty).
  const [viewOverride, setViewOverride] = useState<JournalView | null>(null);
  const view = resolveJournalView(viewOverride, ownRows.length);
  const isExamples = view === 'examples';
  const viewRows: JournalRow[] = isExamples ? exampleRows : ownRows;
  const examplesUnavailable = examplesQuery.isError;

  // ── Chart/rail trades: active view's trades on the charted session ──────
  const railTrades = useMemo(
    () =>
      viewRows
        .map(journalRowToTradeEntry)
        .filter((t) => chartIsoDate && epochToJournalDateTime(t.entryTime).date === chartIsoDate),
    [viewRows, chartIsoDate],
  );

  // ── Marking flow (Task 4 extraction) — the page renders its OWN toolbar
  // (Mark Entry / CALL-PUT / step hints) and drives TradeMarkingChart's
  // internal state machine via the imperative handle; drawingStep here is a
  // mirror fed by onDrawingStepChange, same pattern as ChartsPage.
  const [drawingStep, setDrawingStep] = useState<DrawingStep>('idle');
  const tradeMarkingRef = useRef<TradeMarkingChartHandle>(null);

  // Rail-card hover → chart highlight (design spec Option B, Task 5 gap):
  // "Hovering a card highlights its markers on the chart." Single source of
  // truth shared by both rail-card lists (Examples + My journal render the
  // same railTrades array) and the chart.
  const [hoveredTradeId, setHoveredTradeId] = useState<string | null>(null);

  const createChartTrade = useCreateChartTrade();
  const closeChartTrade = useCloseChartTrade();
  const deleteChartTrade = useDeleteChartTrade();
  const addTrade = useAddTrade(activeTicker);

  // ── Stats — tiles/table scope to the selected session (Overview when
  // cleared); the equity curve is ALWAYS cumulative across all dates. ──────
  const [includeReplay, setIncludeReplay] = useState(false);
  const stats = computeJournalStats(viewRows, {
    includeReplay,
    date: scopeIso ?? undefined,
  });
  const {
    closedCount, totalCount, winRate, avgReturn, totalReturn, avgWin,
    replayExcludedCount, winCount, lossCount, avgRR, tp1HitRate,
  } = stats;
  const curveStats = computeJournalStats(viewRows, { includeReplay });

  // Table rows: the active view's raw rows, session-scoped like the tiles.
  // Plain derivation (no useMemo) — the filter is cheap and the React
  // Compiler rejects manual memoization keyed on this derived scope value.
  const tableRows = scopeIso
    ? viewRows.filter((r) => r.entry_ts.slice(0, 10) === scopeIso)
    : viewRows;

  const scopeLabel = selectedDate
    ? `Session — ${selectedDate.slice(4, 6)}/${selectedDate.slice(6, 8)}/${selectedDate.slice(0, 4)}`
    : 'Overview — all dates';

  const viewLoading = isExamples ? examplesQuery.isLoading : ownQuery.isLoading;

  const handleAdd = () => {
    const ep = parseFloat(String(form.entryPrice));
    const xp = parseFloat(String(form.exitPrice));
    if (isNaN(ep) || isNaN(xp)) return;
    addTrade.mutate(form, {
      onSuccess: () => {
        setForm(emptyForm());
        setShowForm(false);
        // Manual adds write to MY journal — flip the view so the user sees
        // where the trade went (same rule as marking on the chart).
        setViewOverride('mine');
      },
    });
  };

  const exportPipeline = async () => {
    // Active (unexited) trades have no exit_* to export and the server 422s
    // on them — filter locally so the request only ever carries closed
    // trades, and tell the user how many were left out.
    const closed = exportableTrades(ownRows);
    const skippedCount = ownRows.length - closed.length;
    const csv = tradesToCsv(closed);
    try {
      const r = await fetch(`/api/journal/export/${activeTicker}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trades: closed.map((e, i) => {
            const entry = tsToDisplay(e.entry_ts);
            const exit  = tsToDisplay(e.exit_ts);
            return {
              id: String(i + 1),
              ticker: e.ticker,
              direction: e.direction,
              entry_date: entry.date,
              entry_time: entry.time,
              entry_price: e.entry_price,
              exit_date: exit.date,
              exit_time: exit.time,
              exit_price: e.exit_price,
              notes: e.notes ?? '',
            };
          }),
        }),
      });
      if (r.ok) {
        const d = await r.json();
        const skippedNote = skippedCount > 0 ? ` · ${skippedCount} active skipped` : '';
        setExportStatus(`Exported ${d.trades_exported} closed trades${skippedNote} → ${d.filename}`);
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
    <div className="space-y-4">
      {/* ── Header row ─────────────────────────────────────────────────── */}
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
        <div className="flex flex-wrap items-center gap-2">
          <TickerCombobox />

          {/* Trading-date picker — clearable back to the Overview state. */}
          <input
            type="date"
            value={toInputFormat(selectedDate)}
            min={minDate}
            max={maxDate}
            onChange={(e) => setSelectedDate(toApiFormat(e.target.value))}
            className="rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-2 py-1.5 text-xs text-[var(--color-text-primary)]"
            title="Scope tiles + table to one session (clear for Overview)"
          />
          {selectedDate && (
            <button
              data-testid="clear-date"
              onClick={() => setSelectedDate('')}
              className="flex items-center gap-1 rounded border border-[var(--color-border)] px-2 py-1.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]"
              title="Clear the session date — back to Overview (all dates)"
            >
              <X size={11} /> Overview
            </button>
          )}

          {/* Mark-Entry flow — drives TradeMarkingChart's state machine via
              tradeMarkingRef; drawingStep is the onDrawingStepChange mirror
              (ChartsPage's exact pattern, Task 4 handoff). */}
          {drawingStep === 'idle' ? (
            <button
              onClick={() => tradeMarkingRef.current?.startDrawing()}
              className="flex items-center gap-1 rounded bg-[var(--color-accent-blue)] px-3 py-1.5 text-xs font-medium text-[var(--on-brand)] hover:bg-blue-600"
            >
              <Crosshair size={14} />
              Mark Entry
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-[var(--color-accent-amber)]">
                {drawingStep === 'entry' && 'Click chart to set entry price'}
                {drawingStep === 'option-type' && 'Select CALL or PUT'}
                {drawingStep === 'tp1' && 'Click TP1 (ESC to skip)'}
                {drawingStep === 'tp2' && 'Click TP2 (ESC to skip)'}
                {drawingStep === 'tp3' && 'Click TP3 (ESC to skip)'}
                {drawingStep === 'sl' && 'Click Stop Loss (ESC to skip)'}
                {drawingStep === 'exit' && 'Click chart to set exit price'}
              </span>
              {drawingStep === 'option-type' && (
                <div className="flex gap-1">
                  <button
                    onClick={() => tradeMarkingRef.current?.selectOptionType('CALL')}
                    className="flex items-center gap-1 rounded bg-[var(--bull)] px-2 py-1 text-xs text-black"
                  >
                    <ArrowUpCircle size={12} />
                    CALL
                  </button>
                  <button
                    onClick={() => tradeMarkingRef.current?.selectOptionType('PUT')}
                    className="flex items-center gap-1 rounded bg-[var(--bear)] px-2 py-1 text-xs text-white"
                  >
                    <ArrowDownCircle size={12} />
                    PUT
                  </button>
                </div>
              )}
              <button
                onClick={() => tradeMarkingRef.current?.cancelDrawing()}
                className="rounded p-1 text-[var(--color-text-muted)] hover:text-[var(--color-accent-red)]"
              >
                <X size={16} />
              </button>
            </div>
          )}

          <button
            onClick={() => setShowForm(s => !s)}
            className="flex items-center gap-1.5 rounded bg-[var(--color-accent-blue)] px-3 py-1.5 text-xs font-medium text-[var(--on-brand)] hover:opacity-90"
          >
            <PlusCircle size={13} /> Add Trade
          </button>

          {/* Import always writes to MY journal, visible in every view
              (design spec "Trade import"). */}
          <button
            data-testid="import-trades-btn"
            onClick={() => setImportOpen(true)}
            className="flex items-center gap-1.5 rounded border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]"
          >
            <Upload size={13} /> Import
          </button>

          {viewRows.length > 0 && (
            <button
              onClick={() => downloadCsv(tradesToCsv(viewRows), `${activeTicker.toLowerCase()}_journal.csv`)}
              className="flex items-center gap-1.5 rounded border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]"
            >
              <Download size={13} /> CSV
            </button>
          )}
          {!isExamples && ownRows.length > 0 && (
            <button
              onClick={exportPipeline}
              className="flex items-center gap-1.5 rounded border border-[var(--color-accent-blue)]/50 bg-[var(--color-accent-blue)]/10 px-3 py-1.5 text-xs text-[var(--color-accent-blue)] hover:bg-[var(--color-accent-blue)]/20"
            >
              <FileDown size={13} /> Export to Pipeline
            </button>
          )}

          {/* View toggle — right-aligned. */}
          <div className="flex rounded border border-[var(--color-border)]" data-testid="view-toggle">
            {(['examples', 'mine'] as const).map((v) => (
              <button
                key={v}
                onClick={() => setViewOverride(v)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  view === v
                    ? 'bg-[var(--color-accent-blue)] text-[var(--on-brand)]'
                    : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]'
                }`}
              >
                {v === 'examples' ? 'Examples' : 'My journal'}
              </button>
            ))}
          </div>
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

      {isExamples && examplesUnavailable && (
        <div data-testid="examples-unavailable" className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-[var(--warn)]">
          <AlertCircle size={14} /> Examples unavailable — the journal database didn't respond.
        </div>
      )}

      {/* ── Chart + rail row (layout B "Cockpit") ──────────────────────── */}
      <div className="flex gap-4">
        {/* Chart column */}
        <div className="flex min-w-0 flex-1 flex-col">
          {/* Chart mini-toolbar: timeframes + Vol/RTH toggles */}
          <div className="mb-2 flex flex-wrap items-center gap-3">
            <div className="flex rounded border border-[var(--color-border)]">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf.value}
                  onClick={() => setTimeframe(tf.value)}
                  className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                    timeframe === tf.value
                      ? 'bg-[var(--color-accent-blue)] text-[var(--on-brand)]'
                      : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]'
                  }`}
                >
                  {tf.label}
                </button>
              ))}
            </div>
            <button
              onClick={() => setShowVolume(!showVolume)}
              className={`flex items-center gap-1 rounded px-2 py-1.5 text-xs ${
                showVolume ? 'bg-[var(--color-bg-hover)] text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'
              }`}
            >
              {showVolume ? <Eye size={14} /> : <EyeOff size={14} />}
              Vol
            </button>
            <button
              onClick={() => setRthOnly(!rthOnly)}
              className={`flex items-center gap-1 rounded px-2 py-1.5 text-xs ${
                rthOnly ? 'bg-[var(--color-bg-hover)] text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'
              }`}
            >
              <Clock size={14} />
              RTH
            </button>
            <span className="text-xs text-[var(--color-text-muted)]">
              {chartIsoDate ? `Session ${chartIsoDate}` : 'No session data'}
            </span>
          </div>

          {/* Chart card — same viewport height clamp as ChartsPage. */}
          <div
            data-testid="journal-chart-card"
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-primary)]"
            style={{ height: 'clamp(400px, calc(100vh - 340px), 900px)' }}
          >
            {chartLoading ? (
              <div className="flex h-full items-center justify-center">
                <LoadingSpinner size={32} />
              </div>
            ) : chartError ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-[var(--color-text-muted)]">
                <Clock size={32} className="opacity-50" />
                <p className="text-sm">
                  {(chartError as Error).message?.includes('No data')
                    ? 'No market data available for this date'
                    : (chartError as Error).message}
                </p>
              </div>
            ) : marketData && marketData.count > 0 ? (
              <TradeMarkingChart
                ref={tradeMarkingRef}
                ticker={activeTicker}
                bars={marketData.candlestick}
                volume={marketData.volume}
                // trades={railTrades}: the exit lookup inside useTradeMarking
                // resolves against this same active-view array — Exit is only
                // reachable from own-view rail cards (example cards suppress
                // it), so the lookup only ever runs against the user's own
                // trades for the charted session.
                trades={railTrades}
                onTradeCreated={(vars) => {
                  // Marking ALWAYS writes to MY journal; flip the view so the
                  // user sees where the trade landed (design spec "Views").
                  createChartTrade.mutate(vars);
                  setViewOverride('mine');
                }}
                onTradeExited={(vars) => closeChartTrade.mutate(vars)}
                markersStyle={isExamples ? 'examples' : 'own'}
                showVolume={showVolume}
                rthOnly={rthOnly}
                minHeight={400}
                onDrawingStepChange={setDrawingStep}
                highlightedTradeId={hoveredTradeId}
              />
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-[var(--color-text-muted)]">
                <Clock size={32} className="opacity-50" />
                <p className="text-sm">No market data available for this date</p>
                <p className="text-xs opacity-70">Markets may be closed (weekend or holiday)</p>
              </div>
            )}
          </div>
        </div>

        {/* Trade rail */}
        <div className="w-[340px] shrink-0 space-y-2">
          <div className="text-xs font-semibold text-[var(--color-text-secondary)]">
            {isExamples ? 'Example trades' : 'My trades'}
            {chartIsoDate ? ` — ${chartIsoDate}` : ''}
          </div>
          {railTrades.length === 0 ? (
            <p className="rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] p-3 text-center text-xs text-[var(--color-text-muted)]">
              {isExamples
                ? 'No example trades on this session.'
                : 'No trades on this session yet. Click "Mark Entry" to start.'}
            </p>
          ) : (
            railTrades.map((trade) => (
              <TradeRailCard
                key={trade.id}
                trade={trade}
                example={isExamples}
                onExit={(id) => tradeMarkingRef.current?.startExitMode(id)}
                onDelete={(id) => deleteChartTrade.mutate({ id, ticker: activeTicker })}
                onHover={setHoveredTradeId}
                highlighted={hoveredTradeId === trade.id}
              />
            ))
          )}

          {/* Equity curve — ALWAYS cumulative across all dates. */}
          <Card>
            <CardHeader title={`${activeTicker} equity curve`} meta="cumulative P&L %" />
            {curveStats.equityPoints.length > 1 ? (
              <PriceAreaChart
                data={curveStats.equityPoints}
                seriesLabel="Cumulative P&L"
                height={180}
                valueFormatter={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`}
                tooltipFormatter={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`}
              />
            ) : (
              <p className="py-8 text-center text-xs text-[var(--color-text-muted)]">
                Close 2+ trades to see your equity curve.
              </p>
            )}
          </Card>
        </div>
      </div>

      {/* ── Scope label + KPI tiles + practice toggle + notes ──────────── */}
      {viewRows.length > 0 && (
        <>
          <div className="flex flex-wrap items-center gap-4">
            <span data-testid="scope-label" className="text-xs font-semibold text-[var(--color-text-secondary)]">
              {scopeLabel}
            </span>
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
          </div>
          <div className="grid grid-cols-2 gap-[14px] md:grid-cols-4 lg:grid-cols-7">
            <KpiTile label="Trades" value={String(totalCount)} sub={`${winCount}W / ${lossCount}L`} />
            <KpiTile label="Win rate" value={winRate !== null ? `${winRate.toFixed(0)}%` : NA} tone={(winRate ?? 0) >= 50 ? 'bull' : 'bear'} />
            <KpiTile label="Total P&L" value={fmtPct(totalReturn)} tone={(totalReturn ?? 0) >= 0 ? 'bull' : 'bear'} />
            <KpiTile label="Avg / trade" value={fmtPct(avgReturn)} tone={(avgReturn ?? 0) >= 0 ? 'bull' : 'bear'} />
            <KpiTile label="Avg win" value={fmtPct(avgWin)} tone="bull" />
            <KpiTile label="Avg R:R" value={avgRR !== null ? avgRR.toFixed(2) : NA} />
            <KpiTile label="TP1 hit" value={tp1HitRate !== null ? `${tp1HitRate.toFixed(0)}%` : NA} tone={(tp1HitRate ?? 0) >= 50 ? 'bull' : 'default'} />
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

      {/* ── Trade table (full width, session-scoped like the tiles) ─────── */}
      {viewLoading && tableRows.length === 0 ? (
        <div className="rounded-xl bg-[var(--surface-2)] p-8 text-center text-sm text-[var(--color-text-muted)]">
          Loading journal…
        </div>
      ) : viewRows.length === 0 && !showForm ? (
        <div className="rounded-xl bg-[var(--surface-2)] p-10 text-center">
          {isExamples ? (
            <p className="text-sm text-[var(--color-text-muted)]">
              {examplesUnavailable
                ? 'Examples unavailable.'
                : `No example trades for ${activeTicker} yet.`}
            </p>
          ) : (
            <>
              <p className="text-sm text-[var(--color-text-muted)]">No trades logged for {activeTicker} yet.</p>
              <button onClick={() => setShowForm(true)}
                className="mx-auto mt-3 flex items-center gap-1.5 rounded bg-[var(--color-accent-blue)] px-4 py-2 text-xs font-medium text-[var(--on-brand)] hover:opacity-90"
              >
                <PlusCircle size={13} /> Log Your First Trade
              </button>
            </>
          )}
        </div>
      ) : (
        tableRows.length === 0 ? (
          <div className="rounded-xl bg-[var(--surface-2)] p-8 text-center text-sm text-[var(--color-text-muted)]">
            No trades on this session — clear the date for the Overview.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
            <table className="w-full text-left">
              <thead className="bg-[var(--color-bg-tertiary)]">
                <tr>
                  {['Date', 'Dir', 'Entry', 'Entry $', 'Exit', 'Exit $', 'Return', 'Stop', 'TPs', 'R:R', 'Notes', ''].map(h => (
                    <th key={h} className="px-3 py-2 text-xs font-medium text-[var(--color-text-muted)]">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {tableRows.map(e => {
                  const entry = tsToDisplay(e.entry_ts);
                  const exit  = tsToDisplay(e.exit_ts ?? null);
                  const ret   = e.return_pct;
                  const isActive = e.status === 'active' || e.exit_ts == null;
                  const tp1 = e.take_profits?.[0] ?? null;
                  const rr = riskReward(e.entry_price ?? null, tp1, e.stop_loss ?? null);
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
                        {/* Task 7 carried item (T6 review, Important): a
                            practice (bar-replay-trainer) row gets the same
                            muted-badge treatment TradeRailCard's "EX" badge
                            uses — same weight as "active" above, distinct
                            (muted, not amber) color so it reads as
                            "not a real fill" rather than "still open." */}
                        {e.source === 'replay' && (
                          <span className="ml-1.5 rounded bg-[var(--color-bg-hover)] px-1.5 py-0.5 text-[9px] font-medium text-[var(--color-text-muted)]">
                            practice
                          </span>
                        )}
                        {/* task-examples-union: same muted-badge treatment
                            as "practice" above, for a row sourced from the
                            automated pipeline `trades` table rather than
                            an admin-authored journal_entries row. */}
                        {e.source === 'pipeline' && (
                          <span className="ml-1.5 rounded bg-[var(--color-bg-hover)] px-1.5 py-0.5 text-[9px] font-medium text-[var(--color-text-muted)]">
                            pipeline
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
                      {/* Risk columns — "—" when the plan leg is missing (Rule 3.7). */}
                      <td className="px-3 py-1.5 font-mono text-xs text-[var(--color-text-primary)]">
                        {e.stop_loss != null ? `$${e.stop_loss.toFixed(2)}` : <span className="text-[var(--on-surface-muted)]">—</span>}
                      </td>
                      <td className="px-3 py-1.5 font-mono text-xs text-[var(--color-text-primary)]">
                        {e.take_profits && e.take_profits.length > 0
                          ? e.take_profits.map((p) => p.toFixed(2)).join(' / ')
                          : <span className="text-[var(--on-surface-muted)]">—</span>}
                      </td>
                      <td className="px-3 py-1.5 font-mono text-xs text-[var(--color-text-primary)]">
                        {rr != null ? rr.toFixed(2) : <span className="text-[var(--on-surface-muted)]">—</span>}
                      </td>
                      <td className="max-w-[200px] truncate px-3 py-1.5 text-xs text-[var(--color-text-muted)]">{e.notes || '—'}</td>
                      <td className="px-3 py-1.5">
                        <button
                          onClick={() => deleteChartTrade.mutate({ id: e.id, ticker: activeTicker })}
                          disabled={isExamples || deleteChartTrade.isPending}
                          title={isExamples ? 'Examples are read-only teaching trades' : 'Delete trade'}
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

      {/* Broker CSV import (Task 7) — always writes to MY journal; a
          successful commit flips the view so the user sees where the
          imported trades landed, same rule as chart marking above. */}
      <ImportTradesModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => setViewOverride('mine')}
      />
    </div>
  );
}
