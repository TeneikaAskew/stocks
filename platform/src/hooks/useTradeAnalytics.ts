import { useQuery } from '@tanstack/react-query';
import type { TradeEntry } from '@/types';

// Stats are computed server-side (platform/api/routers/analytics.py) so the
// app never duplicates financial math. ChartsPage passes its in-memory
// annotation trades to POST /api/analytics/trade-stats; the Dashboard pulls
// real backtest trades from GET /api/analytics/summary/{ticker}.

export interface TradeStats {
  totalTrades: number;
  closedTrades: number;
  activeTrades: number;
  winCount: number;
  lossCount: number;
  winRate: number;
  totalPnL: number;
  avgPnL: number;
  maxWin: number;
  maxLoss: number;
  profitFactor: number | null;
  callCount: number;
  putCount: number;
}

/**
 * Compute stats for an ad-hoc trades array (typically ChartsPage annotation
 * trades). Posts to the server so the aggregation matches the DB-backed
 * summary endpoint — no duplicate TS math.
 *
 * Returns `stats: null` while loading OR on error — never a zero-filled
 * object (Rule 3.7: a fabricated "Trades 0" tile is indistinguishable from
 * a genuinely empty journal). `isError` lets the caller render an explicit
 * "analytics unavailable" state instead.
 */
export function useTradeAnalytics(trades: TradeEntry[]): {
  stats: TradeStats | null;
  isError: boolean;
} {
  // Include a compact signature in the queryKey so React Query refetches
  // when the user adds/removes/updates a trade without posting on every render.
  const signature = trades
    .map((t) => `${t.id}:${t.status}:${t.pnl ?? ''}`)
    .join('|');
  const query = useQuery<TradeStats>({
    queryKey: ['trade-stats', signature],
    queryFn: async () => {
      const r = await fetch('/api/analytics/trade-stats', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trades: trades.map((t) => ({
            status: t.status,
            pnl: t.pnl ?? null,
            optionType: t.optionType ?? null,
          })),
        }),
      });
      if (!r.ok) throw new Error(`trade-stats ${r.status}`);
      return r.json();
    },
    enabled: true,
    staleTime: 60_000,
  });
  return { stats: query.data ?? null, isError: query.isError };
}

/**
 * Server-computed stats for a ticker's backtested trades (from the DB).
 * Default lookback is 90 days.
 */
export function useTradeSummary(ticker: string, days = 90) {
  return useQuery<TradeStats>({
    queryKey: ['trade-summary', ticker, days],
    queryFn: async () => {
      const r = await fetch(`/api/analytics/summary/${ticker}?days=${days}`);
      if (!r.ok) throw new Error(`trade-summary ${r.status}`);
      return r.json();
    },
    enabled: !!ticker,
    staleTime: 5 * 60_000,
  });
}
