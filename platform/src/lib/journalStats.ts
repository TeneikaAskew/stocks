import type { PricePoint } from '@/components/charts/PriceAreaChart';

export interface JournalStatEntry {
  return_pct?: number | null;
  entry_ts: string;
  exit_ts?: string | null;
  /** 'chart' | 'manual' | 'replay' (server's journal_entries.source column).
   *  Absent on legacy rows — treated as non-practice, same as 'chart'/'manual'. */
  source?: string | null;
}

export interface JournalStatsOptions {
  /** Practice (bar-replay-trainer) trades are EXCLUDED from every aggregate
   *  by default (Task 5.3) — a mined "win rate" that's secretly half replay
   *  drills isn't the user's real trading performance. Pass true (wired to
   *  the "Include practice sessions" toggle) to fold them back in. */
  includeReplay?: boolean;
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
  const replayExcludedCount = includeReplay
    ? 0
    : entries.filter((e) => e.source === 'replay').length;
  const scoped = includeReplay ? entries : entries.filter((e) => e.source !== 'replay');

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
  };
}
