import { useQuery } from '@tanstack/react-query';

export interface LiveQuote {
  ticker: string;
  price: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  // Nullable: review mode reconstructs this quote from historical bars and
  // is honest when the prior session close can't be resolved (see
  // lib/reviewQuote.ts buildReviewQuote) rather than silently rebasing to
  // the day's open (CLAUDE.md §3.7).
  change: number | null;
  change_pct: number | null;
  prev_close: number | null;
  last_updated: string;
  market_session?: string;
  market_open?: boolean;
}

export function useLiveQuote(ticker: string, enabled: boolean = true) {
  return useQuery<LiveQuote>({
    queryKey: ['live-quote', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/live/quote/${ticker}`);
      if (!r.ok) throw new Error(`live-quote ${r.status}`);
      return r.json();
    },
    enabled: enabled && !!ticker,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
}
