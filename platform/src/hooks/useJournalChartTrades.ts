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
