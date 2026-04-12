import { useQuery } from '@tanstack/react-query';

export type MarketSession = 'regular' | 'pre-market' | 'after-hours' | 'closed';

export interface LiveStatus {
  is_open: boolean;
  session: MarketSession | string;
  next_open: string | null;
  current_time_et: string;
}

export function useLiveStatus() {
  return useQuery<LiveStatus>({
    queryKey: ['live-status'],
    queryFn: async () => {
      const r = await fetch('/api/live/status');
      if (!r.ok) throw new Error(`live-status ${r.status}`);
      return r.json();
    },
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}
