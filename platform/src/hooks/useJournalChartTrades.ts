import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { TradeDirection, TradeEntry } from '@/types';

// ── Server row shape ──────────────────────────────────────────────────────
// GET /api/journal/trades/{ticker} (platform/api/routers/journal.py). Every
// field beyond id/ticker/direction/entry_ts/entry_price is optional because
// legacy local-dev rows (pre-Phase-2 schema) may lack the newer columns
// entirely — journalRowToTradeEntry below defaults those with optional
// chaining, never `?? 0` on a financial value.
export interface JournalRow {
  id: string;
  ticker: string;
  direction: string; // 'CALL' | 'PUT'
  entry_ts: string;
  exit_ts: string | null;
  entry_price: number;
  exit_price: number | null;
  return_pct: number | null; // PERCENT, already sign-corrected for direction
  notes?: string;
  take_profits?: number[];
  stop_loss?: number | null;
  status?: string;
  source?: string;
  session_id?: string | null;
  created_at?: string;
}

interface JournalTradesResponse {
  ticker: string;
  source: 'cloud_sql' | 'local';
  count: number;
  trades: JournalRow[];
}

interface JournalMutationResponse {
  source: 'cloud_sql' | 'local';
  id: string;
  return_pct: number | null;
  status: string;
}

interface JournalDeleteResponse {
  source: 'cloud_sql' | 'local';
  deleted: string;
}

// ── Seed layer (Task 2.4) ────────────────────────────────────────────────
// GET /api/journal/seed/{ticker}?date= (platform/api/routers/journal.py
// seed_trades). Read-only admin pull from the automated pipeline `trades`
// table — a teaching layer overlaid on the user's own journal, never
// editable from the chart. return_pct here is already TRUE PERCENT
// (server converts the pipeline's raw fraction ×100 — see the router's
// in-line comment), same units as journal_entries.return_pct.
export interface SeedTradeRow {
  id: string;
  direction: string; // 'CALL' | 'PUT'
  entry_time: string | null;
  entry_price: number | null;
  exit_time: string | null;
  exit_price: number | null;
  return_pct: number | null; // PERCENT
  strat_combo: string | null;
  exit_reason: string | null;
}

interface SeedTradesOk {
  ticker: string;
  date: string;
  count: number;
  trades: SeedTradeRow[];
}

interface SeedTradesUnavailable {
  status: 'unavailable';
  reason: string;
}

export type SeedTradesResponse = SeedTradesOk | SeedTradesUnavailable;

export function isSeedTradesUnavailable(resp: SeedTradesResponse): resp is SeedTradesUnavailable {
  return 'status' in resp && resp.status === 'unavailable';
}

// ── Pure mappers (exported, unit-tested in journalChartTrades.test.ts) ────

/**
 * Chart epoch-seconds encode naive-ET wall clock (main.py convention).
 * Render the wall-clock fields WITHOUT timezone conversion.
 */
export function epochToJournalDateTime(epochSec: number): { date: string; time: string } {
  const d = new Date(epochSec * 1000);
  const p = (n: number) => String(n).padStart(2, '0');
  return {
    date: `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}`,
    time: `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`,
  };
}

/**
 * Reverse of epochToJournalDateTime. The journal API returns entry_ts/exit_ts
 * as ISO-ish strings that encode the SAME naive-ET wall clock (never real
 * UTC) — but the exact separator/offset varies by storage backend:
 *   - local-fallback rows: "2026-07-02T13:35:00"       ('T', no offset —
 *     built as `${date}T${time}:00` in journal.py's create_trade)
 *   - Cloud SQL rows:      "2026-07-02 13:35:00+00:00"  (space + offset,
 *     from the `entry_ts AT TIME ZONE 'UTC'` cast in journal.py's SELECT)
 * `new Date(isoString)` is forbidden here (local-tz dependent, per project
 * convention) — instead pull the y/m/d/h/mi/s digits out with a regex and
 * rebuild the epoch via Date.UTC, which reproduces the exact wall-clock
 * value regardless of separator or trailing offset.
 */
export function isoNaiveToEpoch(iso: string): number {
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/.exec(iso);
  if (!m) return NaN;
  const [y, mo, d, h, mi, s] = m.slice(1).map(Number);
  return Math.floor(Date.UTC(y, mo - 1, d, h, mi, s) / 1000);
}

function deriveStatus(row: JournalRow): TradeEntry['status'] {
  if (row.status === 'win' || row.status === 'loss' || row.status === 'breakeven' || row.status === 'active') {
    return row.status;
  }
  // Legacy local-dev rows (pre-Phase-2) or an unrecognized server value:
  // re-derive the same win/loss/breakeven/active split the server's own
  // `_derive_status` uses (journal.py), keyed off exit_ts + return_pct sign.
  // This is a structural fallback for a possibly-absent key, not the
  // "financial ?? 0" pattern CLAUDE.md Rule 3.7 forbids.
  if (!row.exit_ts) return 'active';
  if (row.return_pct == null) return 'breakeven';
  if (row.return_pct > 0) return 'win';
  if (row.return_pct < 0) return 'loss';
  return 'breakeven';
}

/** GET /api/journal/trades/{ticker} row -> the chart's TradeEntry shape. */
export function journalRowToTradeEntry(row: JournalRow): TradeEntry {
  const entryTime = isoNaiveToEpoch(row.entry_ts);
  const exitTime = row.exit_ts ? isoNaiveToEpoch(row.exit_ts) : undefined;

  // take_profits/stop_loss/notes/status may be entirely absent on legacy
  // local-dev rows (pre-Phase-2 schema) — structural defaults for a
  // possibly-missing key, not a fabricated financial value.
  const takeProfits = (row.take_profits ?? []).map((price) => ({ price, size: 0 }));
  const stopLoss = row.stop_loss != null ? { price: row.stop_loss } : undefined;

  // return_pct is already sign-corrected server-side (_return_pct in
  // journal.py: CALL = (exit-entry)/entry*100, PUT = negated). Deriving
  // pnl-in-dollars as entry_price * return_pct/100 preserves that sign
  // without re-deriving direction-aware math on the client. Both stay
  // `undefined` (never 0) for an active trade with no return yet.
  const pnlPercent = row.return_pct ?? undefined;
  const pnl = row.return_pct != null ? row.entry_price * (row.return_pct / 100) : undefined;

  return {
    id: row.id,
    ticker: row.ticker,
    optionType: row.direction as TradeDirection,
    entryTime,
    entryPrice: row.entry_price,
    exitTime,
    exitPrice: row.exit_price ?? undefined,
    stopLoss,
    takeProfits,
    notes: row.notes ?? '',
    tags: [],
    status: deriveStatus(row),
    pnl,
    pnlPercent,
    createdAt: row.created_at ? isoNaiveToEpoch(row.created_at) * 1000 : Date.now(),
  };
}

// ── Hooks ──────────────────────────────────────────────────────────────────

const chartTradesKey = (ticker: string) => ['journal-chart-trades', ticker] as const;

/**
 * Chart-marked trades for one ticker, filtered client-side to `date`
 * (YYYY-MM-DD, same format epochToJournalDateTime produces). The GET route
 * has no server-side date filter, so this pulls the ticker's full journal
 * and slices it with `select` — cheap, and keeps a single cache entry per
 * ticker so switching the chart's selected date doesn't refetch.
 */
export function useJournalChartTrades(ticker: string, date: string) {
  return useQuery<JournalTradesResponse, Error, TradeEntry[]>({
    queryKey: chartTradesKey(ticker),
    queryFn: async () => {
      const r = await fetch(`/api/journal/trades/${ticker}`);
      if (!r.ok) throw new Error(`journal trades ${r.status}`);
      return r.json();
    },
    select: (resp) =>
      resp.trades
        .map(journalRowToTradeEntry)
        .filter((t) => epochToJournalDateTime(t.entryTime).date === date),
    enabled: !!ticker && !!date,
    staleTime: 10_000,
  });
}

export interface CreateChartTradeVars {
  ticker: string;
  direction: TradeDirection;
  entryTime: number; // epoch seconds, naive-ET
  entryPrice: number;
  stopLoss?: number;
  takeProfits?: number[];
}

// Mutations below invalidate-on-success rather than doing optimistic
// onMutate/rollback pairs: ChartsPage is single-user and the round-trip
// latency to /api/journal is small, so the simpler invalidate pattern is
// enough — no rollback bookkeeping to get wrong.
export function useCreateChartTrade() {
  const qc = useQueryClient();
  return useMutation<JournalMutationResponse, Error, CreateChartTradeVars>({
    mutationFn: async (vars) => {
      const { date, time } = epochToJournalDateTime(vars.entryTime);
      const r = await fetch('/api/journal/trades', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker: vars.ticker,
          direction: vars.direction,
          entry_date: date,
          entry_time: time,
          entry_price: vars.entryPrice,
          stop_loss: vars.stopLoss,
          take_profits: vars.takeProfits && vars.takeProfits.length > 0 ? vars.takeProfits : undefined,
          source: 'chart',
        }),
      });
      if (!r.ok) throw new Error(`create trade failed: ${r.status}`);
      return r.json();
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: chartTradesKey(vars.ticker) });
    },
  });
}

export interface CloseChartTradeVars {
  id: string;
  ticker: string;
  exitTime: number; // epoch seconds, naive-ET
  exitPrice: number;
}

export function useCloseChartTrade() {
  const qc = useQueryClient();
  return useMutation<JournalMutationResponse, Error, CloseChartTradeVars>({
    mutationFn: async (vars) => {
      const { date, time } = epochToJournalDateTime(vars.exitTime);
      const r = await fetch(`/api/journal/trades/${vars.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ exit_date: date, exit_time: time, exit_price: vars.exitPrice }),
      });
      if (!r.ok) throw new Error(`close trade failed: ${r.status}`);
      return r.json();
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: chartTradesKey(vars.ticker) });
    },
  });
}

export interface DeleteChartTradeVars {
  id: string;
  ticker: string;
}

export function useDeleteChartTrade() {
  const qc = useQueryClient();
  return useMutation<JournalDeleteResponse, Error, DeleteChartTradeVars>({
    mutationFn: async (vars) => {
      const r = await fetch(`/api/journal/trades/${vars.id}?ticker=${vars.ticker}`, {
        method: 'DELETE',
      });
      if (!r.ok) throw new Error(`delete trade failed: ${r.status}`);
      return r.json();
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: chartTradesKey(vars.ticker) });
    },
  });
}

/**
 * Admin seed trades (Task 2.4) — read-only teaching overlay for one
 * ticker+day. A real backend error (503) surfaces through TanStack Query's
 * `isError`/`error` state; an honest `{status:"unavailable"}` envelope
 * (open/local dev with no Cloud SQL) comes back as a normal 200 and is
 * distinguished via `isSeedTradesUnavailable`. Neither path fabricates
 * rows or stats (CLAUDE.md Rule 3.7) — the caller renders a muted "Seed
 * layer unavailable" line for both.
 */
export function useSeedTrades(ticker: string, date: string) {
  return useQuery<SeedTradesResponse, Error>({
    queryKey: ['journal-seed-trades', ticker, date] as const,
    queryFn: async () => {
      const r = await fetch(`/api/journal/seed/${ticker}?date=${date}`);
      if (!r.ok) throw new Error(`journal seed ${r.status}`);
      return r.json();
    },
    enabled: !!ticker && !!date,
    staleTime: 10_000,
    // A 503 here is a real backend failure the UI must surface promptly as
    // "Seed layer unavailable" (Rule 3.7) rather than silently retrying —
    // matches useGammaLevels'/useGammaGrid's `retry: false` for the same
    // "unavailable is a legitimate, fast-surfacing state" reason.
    retry: false,
  });
}

// ── Backtest replay scorecard (Task 3.3) ────────────────────────────────
// POST /api/backtest/replay-trades (platform/api/routers/backtest.py) scores
// the caller's own closed journal trades against the actual bars and
// benchmarks them against the production BacktestEngine
// (lib/backtest.py::replay_labeled_trades — see that function's docstring
// for the exact per-trade/aggregate shape this mirrors).
//
// UNITS: every `*_pct` field is already TRUE PERCENT (server-side
// conversion; see backtest.py's module docstring) — render with
// `.toFixed(2)%` as-is. `win_rate`/`system_agreement_rate` are 0-1
// fractions the UI multiplies by 100 itself (matches every other `_rate`
// field already in this file, e.g. `seedBenchmark`'s `winRatePct`).
// `exit_edge_bps`/`avg_exit_edge_bps` are basis points, already signed.

export interface ReplaySystemSignal {
  direction?: string | null;
  score?: number;
  status?: 'unavailable';
}

export interface ReplaySystemExit {
  exit_reason: string | null;
  return_pct: number | null; // PERCENT
  exit_time: string | null;
}

/** A trade's `status` distinguishes two DIFFERENT meanings of "unavailable":
 * this is the replay scorecard's per-trade status (missing bars / trade
 * still open / bad data), not `TradeEntry['status']` (win/loss/active). */
export interface ReplayTradeCard {
  id: string;
  status: 'ok' | 'unavailable';
  reason?: string;
  actual_return_pct?: number; // PERCENT
  fill_check?: 'ok' | 'price_outside_bar_range';
  system_signal_at_entry?: ReplaySystemSignal;
  system_exit?: ReplaySystemExit;
  exit_edge_bps?: number | null;
}

export interface ReplayAggregate {
  n: number;
  scored_n: number;
  win_rate: number; // 0-1
  avg_return_pct: number; // PERCENT
  system_resolved_n: number;
  system_no_signal_n: number;
  system_agreement_rate: number | null; // 0-1, or null when system_resolved_n === 0 (Rule 3.7: honest null, never fabricated 0)
  avg_exit_edge_bps: number; // bps
}

export interface ReplayTradesResponse {
  trades: ReplayTradeCard[];
  aggregate: ReplayAggregate;
}

export interface ReplayTradesVars {
  ticker: string;
  tradeIds: string[];
}

/**
 * Scores the closed trades identified by `tradeIds` against the production
 * benchmark. A `useMutation` (not `useQuery`) because this is a triggered
 * analytics computation, not cached data the page reads passively — the
 * modal calls `.mutate()` on button click and renders `isPending`/`isError`/
 * `data` directly.
 */
export function useReplayTrades() {
  return useMutation<ReplayTradesResponse, Error, ReplayTradesVars>({
    mutationFn: async (vars) => {
      const r = await fetch('/api/backtest/replay-trades', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: vars.ticker, trade_ids: vars.tradeIds }),
      });
      if (!r.ok) {
        // Fail-loud (Rule 3.7): surface the server's `detail` message when
        // present so the modal's inline error banner says WHY the replay
        // failed (e.g. "journal database not configured"), not just a bare
        // status code.
        let detail = `replay-trades failed: ${r.status}`;
        try {
          const body = await r.json();
          if (body?.detail) detail = String(body.detail);
        } catch {
          // response body wasn't JSON — keep the status-code message.
        }
        throw new Error(detail);
      }
      return r.json();
    },
  });
}

/**
 * Signed basis-points formatter for `exit_edge_bps`/`avg_exit_edge_bps`.
 * `null`/`undefined` (Rule 3.7 honest-unavailable, e.g. no system exit
 * resolved) renders as an em dash, never a fabricated "0.00 bps".
 */
export function formatEdgeBps(bps: number | null | undefined): string {
  if (bps == null) return '—';
  const sign = bps >= 0 ? '+' : '';
  return `${sign}${bps.toFixed(2)} bps`;
}

export interface SeedBenchmark {
  count: number;
  winRatePct: number | null;
  avgReturnPct: number | null;
}

/**
 * Display-only aggregation of the seed layer's own server-computed
 * `return_pct` values — COUNTING, not financial math. Win = return_pct > 0
 * (0/breakeven does not count as a win). Rows with a null return_pct (no
 * exit recorded yet) are excluded from the win-rate/average but still
 * counted in `count` so the "N trades" figure matches what's rendered
 * below it. Empty input -> nulls, never a fabricated 0% (Rule 3.7).
 */
export function seedBenchmark(rows: SeedTradeRow[]): SeedBenchmark {
  const count = rows.length;
  if (count === 0) {
    return { count: 0, winRatePct: null, avgReturnPct: null };
  }
  const withReturn = rows.filter((r) => r.return_pct != null);
  if (withReturn.length === 0) {
    return { count, winRatePct: null, avgReturnPct: null };
  }
  const wins = withReturn.filter((r) => (r.return_pct as number) > 0).length;
  const sum = withReturn.reduce((acc, r) => acc + (r.return_pct as number), 0);
  return {
    count,
    winRatePct: (wins / withReturn.length) * 100,
    avgReturnPct: sum / withReturn.length,
  };
}
