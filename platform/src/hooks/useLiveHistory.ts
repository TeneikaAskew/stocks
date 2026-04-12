import { useQuery } from '@tanstack/react-query';
import type { Bar } from '@/lib/indicators';

export interface LiveHistory {
  ticker: string;
  interval: string;
  count: number;
  market_session?: string;
  market_open?: boolean;
  bars: Bar[];
}

export function useLiveHistory(ticker: string, enabled: boolean = true) {
  return useQuery<LiveHistory>({
    queryKey: ['live-history', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/live/history/${ticker}`);
      if (!r.ok) throw new Error(`live-history ${r.status}`);
      return r.json();
    },
    enabled: enabled && !!ticker,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

export interface AvgVolume {
  ticker: string;
  avg_volume_20d: number;
  sample_size: number;
  last_date: string | null;
  source: string;
}

export function useAvgVolume(ticker: string) {
  return useQuery<AvgVolume>({
    queryKey: ['avg-volume', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/live/avg-volume/${ticker}`);
      if (!r.ok) throw new Error(`avg-volume ${r.status}`);
      return r.json();
    },
    enabled: !!ticker,
    staleTime: 3_600_000,
  });
}
