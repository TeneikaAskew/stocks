/**
 * Query historical_signals for setups similar to the live/review bar.
 *
 * Backed by ``GET /api/signals/{ticker}/similar`` — see signals.py.
 * Disabled until ``direction`` resolves (i.e. the voter has fired); in
 * the no-setup case there's nothing useful to query.
 */
import { useQuery } from '@tanstack/react-query';

export interface SimilarStats {
  count: number;
  avg_mfe_pct?: number | null;
  median_mfe_pct?: number | null;
  p25_mfe_pct?: number | null;
  p75_mfe_pct?: number | null;
  avg_return_5min?: number | null;
  avg_return_20min?: number | null;
  pct_profitable?: number | null;
  earliest?: string | null;
  latest?: string | null;
}

export interface SimilarMatch {
  time: string;
  direction: 'CALL' | 'PUT';
  price: number;
  score: number;
  rsi: number;
  return_pct: number;
  return_5min: number | null;
  return_20min: number | null;
}

export interface SimilarResponse {
  ticker: string;
  direction: 'CALL' | 'PUT';
  rsi: number;
  score: number;
  rsi_band: number;
  stats: SimilarStats;
  matches: SimilarMatch[];
}

interface Args {
  ticker: string;
  direction: 'CALL' | 'PUT' | null;
  rsi: number | null;
  score: number | null;
  rsiBand?: number;
  limit?: number;
}

export function useSimilarSetups({
  ticker,
  direction,
  rsi,
  score,
  rsiBand = 5,
  limit = 10,
}: Args) {
  // Round RSI to 1 decimal so query keys are stable bar-to-bar within
  // the same bucket — avoids constant refetches as RSI drifts by 0.01.
  const rsiKey = rsi == null ? null : Math.round(rsi * 10) / 10;
  return useQuery<SimilarResponse>({
    queryKey: ['similar-setups', ticker, direction, rsiKey, score, rsiBand, limit],
    queryFn: async () => {
      const params = new URLSearchParams({
        direction: direction!,
        rsi: String(rsi),
        score: String(score),
        rsi_band: String(rsiBand),
        limit: String(limit),
      });
      const r = await fetch(`/api/signals/${ticker}/similar?${params}`);
      if (!r.ok) throw new Error(`similar-setups ${r.status}`);
      return r.json();
    },
    enabled: !!ticker && !!direction && rsi != null && score != null,
    staleTime: 60_000,
  });
}
