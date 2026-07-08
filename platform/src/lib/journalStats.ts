import type { PricePoint } from '@/components/charts/PriceAreaChart';

export interface JournalStatEntry {
  return_pct?: number | null;
  entry_ts: string;
  exit_ts?: string | null;
}

export interface JournalStats {
  closedCount: number;
  totalCount: number;
  winRate: number | null;      // percent 0-100
  avgReturn: number | null;    // percent units
  totalReturn: number | null;  // percent units
  avgWin: number | null;       // percent units
  equityPoints: PricePoint[];  // cumulative % across entries WITH returns
}

/** Aggregate journal stats. Entries with null/undefined return_pct are
 * excluded from every aggregate — a missing return is NOT a 0% trade. */
export function computeJournalStats(entries: JournalStatEntry[]): JournalStats {
  const withRet = entries.filter((e): e is JournalStatEntry & { return_pct: number } =>
    typeof e.return_pct === 'number' && !Number.isNaN(e.return_pct));
  const returns = withRet.map((e) => e.return_pct);
  const wins = returns.filter((r) => r > 0);
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
    totalCount: entries.length,
    winRate: returns.length ? (wins.length / returns.length) * 100 : null,
    avgReturn: returns.length ? sum / returns.length : null,
    totalReturn: returns.length ? sum : null,
    avgWin: wins.length ? wins.reduce((a, b) => a + b, 0) / wins.length : null,
    equityPoints,
  };
}
