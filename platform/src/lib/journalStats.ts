import type { PricePoint } from '@/components/charts/PriceAreaChart';
import { riskReward } from '@/lib/risk';

export interface JournalStatEntry {
  return_pct?: number | null;
  entry_ts: string;
  exit_ts?: string | null;
  /** 'chart' | 'manual' | 'replay' (server's journal_entries.source column).
   *  Absent on legacy rows — treated as non-practice, same as 'chart'/'manual'. */
  source?: string | null;
  // Task 5 (journal one-stop) risk fields — all optional/additive so every
  // pre-Task-5 caller (which passes only the four fields above) is untouched.
  /** 'CALL' | 'PUT' — needed for the direction-aware TP1-reached test. */
  direction?: string | null;
  entry_price?: number | null;
  exit_price?: number | null;
  take_profits?: number[] | null;
  stop_loss?: number | null;
}

export interface JournalStatsOptions {
  /** Practice (bar-replay-trainer) trades are EXCLUDED from every aggregate
   *  by default (Task 5.3) — a mined "win rate" that's secretly half replay
   *  drills isn't the user's real trading performance. Pass true (wired to
   *  the "Include practice sessions" toggle) to fold them back in. */
  includeReplay?: boolean;
  /** Task 5 session scoping — 'YYYY-MM-DD'. When set, every aggregate
   *  (including replayExcludedCount) is computed over entries whose
   *  entry_ts falls on this date. Omit for the all-dates "Overview" scope;
   *  omitted behaviour is byte-identical to pre-Task-5. */
  date?: string;
}

export interface JournalStats {
  closedCount: number;
  totalCount: number;
  winRate: number | null;      // percent 0-100
  avgReturn: number | null;    // percent units
  totalReturn: number | null;  // percent units
  avgWin: number | null;       // percent units
  equityPoints: PricePoint[];  // cumulative % across entries WITH returns
  /** Count of source==='replay' entries filtered out of the aggregates
   *  above. Always 0 when includeReplay is true. Drives the "N practice
   *  trade(s) excluded from stats" note, kept separate from the existing
   *  open/unreturned-trade exclusion note. */
  replayExcludedCount: number;
  /** Closed (return_pct != null) entries with return_pct > 0. Scoped the
   *  same as every other aggregate here (replay-excluded unless
   *  includeReplay). winCount + lossCount === closedCount always. */
  winCount: number;
  /** Closed entries with return_pct <= 0 — matches the `<=0`-is-loss
   *  convention in platform/api/routers/analytics.py::_compute_stats
   *  (`"win" if pnl > 0 else "loss"`), the primary source for this
   *  convention. lib/backtest.py's `BacktestResult.losers` now agrees too
   *  (fixed in #702 to use `return_pct is not None and return_pct <= 0`
   *  instead of a falsy-zero `and` check that silently dropped exact-0.0
   *  breakeven trades from both winners and losers). */
  lossCount: number;
  /** Task 5 — mean riskReward(entry, TP1, stop) over scoped entries where it
   *  is computable (lib/risk.ts: null on any missing leg or stop === entry).
   *  Null when no entry qualifies — the "Avg R:R" tile renders "—", never a
   *  fabricated ratio (Rule 3.7). */
  avgRR: number | null;
  /** Task 5 — percent (0-100) of CLOSED (exit_price set) scoped entries with
   *  TP1 set whose exit price reached TP1 (CALL: exit >= TP1, PUT: exit <=
   *  TP1). Null when no closed entry has TP1 set — "—", no fabricated rate. */
  tp1HitRate: number | null;
}

/** Aggregate journal stats. Entries with null/undefined return_pct are
 * excluded from every aggregate — a missing return is NOT a 0% trade.
 * Entries with source==='replay' (bar-replay-trainer practice trades) are
 * ALSO excluded by default — pass {includeReplay: true} to fold them in. */
export function computeJournalStats(
  entries: JournalStatEntry[],
  options: JournalStatsOptions = {},
): JournalStats {
  const includeReplay = options.includeReplay ?? false;
  // Task 5 session scoping — applied BEFORE the replay filter so the
  // "N practice trade(s) excluded" note counts within the visible scope.
  // With options.date omitted, inScope === entries and everything below is
  // byte-identical to the pre-Task-5 behaviour.
  const inScope = options.date
    ? entries.filter((e) => e.entry_ts.slice(0, 10) === options.date)
    : entries;
  const replayExcludedCount = includeReplay
    ? 0
    : inScope.filter((e) => e.source === 'replay').length;
  const scoped = includeReplay ? inScope : inScope.filter((e) => e.source !== 'replay');

  const withRet = scoped.filter((e): e is JournalStatEntry & { return_pct: number } =>
    typeof e.return_pct === 'number' && !Number.isNaN(e.return_pct));
  const returns = withRet.map((e) => e.return_pct);
  const wins = returns.filter((r) => r > 0);
  const losses = returns.filter((r) => r <= 0);
  const sum = returns.reduce((a, b) => a + b, 0);
  const sorted = [...withRet].sort((a, b) =>
    (a.exit_ts || a.entry_ts).localeCompare(b.exit_ts || b.entry_ts));
  let cum = 0;
  const equityPoints: PricePoint[] = sorted.map((e, i) => {
    cum += e.return_pct;
    return { time: i, price: cum, label: (e.exit_ts || e.entry_ts).slice(0, 10) };
  });

  // Task 5 — Avg R:R: per-trade riskReward over every scoped entry where the
  // full plan (entry, TP1, stop) is present; lib/risk.ts returns null for any
  // missing leg or stop === entry, and those entries simply don't count.
  const rrValues = scoped
    .map((e) => riskReward(e.entry_price ?? null, e.take_profits?.[0] ?? null, e.stop_loss ?? null))
    .filter((rr): rr is number => rr != null);
  const avgRR = rrValues.length ? rrValues.reduce((a, b) => a + b, 0) / rrValues.length : null;

  // Task 5 — TP1 hit rate: closed (exit_price set) entries with TP1 set whose
  // exit reached TP1, direction-aware. Entries with an unrecognized direction
  // can't be judged and are excluded from BOTH sides (never guessed).
  const tp1Eligible = scoped.filter(
    (e) =>
      e.exit_price != null &&
      e.take_profits?.[0] != null &&
      (e.direction === 'CALL' || e.direction === 'PUT'),
  );
  const tp1Hits = tp1Eligible.filter((e) =>
    e.direction === 'CALL'
      ? (e.exit_price as number) >= (e.take_profits as number[])[0]
      : (e.exit_price as number) <= (e.take_profits as number[])[0],
  );
  const tp1HitRate = tp1Eligible.length ? (tp1Hits.length / tp1Eligible.length) * 100 : null;

  return {
    closedCount: withRet.length,
    totalCount: scoped.length,
    winRate: returns.length ? (wins.length / returns.length) * 100 : null,
    avgReturn: returns.length ? sum / returns.length : null,
    totalReturn: returns.length ? sum : null,
    avgWin: wins.length ? wins.reduce((a, b) => a + b, 0) / wins.length : null,
    equityPoints,
    replayExcludedCount,
    winCount: wins.length,
    lossCount: losses.length,
    avgRR,
    tp1HitRate,
  };
}
