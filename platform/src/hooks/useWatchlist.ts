import { useQuery } from '@tanstack/react-query';
import type { CatalystType, WatchlistResponse } from '@/types/watchlist';

interface UseWatchlistOpts {
  catalystFilter?: CatalystType[];   // empty / undefined = no filter
  limit?: number;
  enabled?: boolean;
}

// ---------------------------------------------------------------------------
// GET /api/insights/watchlist — deterministic ranker output.
// Cached for 5min by default; the ranker itself is cheap (~5s) but the
// data behind it (catalyst tables) refreshes on a 30-min granularity at
// most, so revalidating more often is wasted I/O.
// ---------------------------------------------------------------------------

export function useWatchlist(opts: UseWatchlistOpts = {}) {
  const { catalystFilter, limit = 10, enabled = true } = opts;
  const filterStr = (catalystFilter ?? []).filter(Boolean).join(',');
  const params = new URLSearchParams();
  if (filterStr) params.set('catalyst', filterStr);
  if (limit) params.set('limit', String(limit));

  return useQuery<WatchlistResponse>({
    queryKey: ['watchlist', filterStr, limit],
    queryFn: async () => {
      const r = await fetch(`/api/insights/watchlist?${params.toString()}`);
      if (!r.ok) throw new Error(`watchlist ${r.status}`);
      return r.json();
    },
    enabled,
    staleTime: 5 * 60_000,
  });
}
