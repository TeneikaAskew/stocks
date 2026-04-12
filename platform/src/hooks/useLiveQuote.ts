import { useQuery } from '@tanstack/react-query';

export interface LiveQuote {
  ticker: string;
  price: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  change: number;
  change_pct: number;
  prev_close: number;
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
