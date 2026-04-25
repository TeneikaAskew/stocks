import { useQuery } from '@tanstack/react-query';
import type { Bar } from '@/lib/indicators';
import type { Indicators, Signal } from '@/lib/indicators';

export interface IndicatorsRequest {
  bars: Bar[];
  current_price?: number | null;
  current_volume?: number | null;
  avg_volume_20d?: number | null;
}

export interface IndicatorsResponse {
  indicators: Indicators;
  signals: { call: Signal; put: Signal };
}

/**
 * Server-side indicator + signal computation. The app never recomputes
 * these client-side — lib/indicators.py is the single source of truth.
 *
 * Keyed on the bar count + last bar time + current price so the query
 * invalidates on every live tick without recomputing on every render.
 */
export function useLiveIndicators(req: IndicatorsRequest, enabled: boolean) {
  const lastBar = req.bars.length > 0 ? req.bars[req.bars.length - 1] : null;
  const key = [
    'live-indicators',
    req.bars.length,
    lastBar?.time ?? null,
    req.current_price ?? null,
    req.current_volume ?? null,
    req.avg_volume_20d ?? null,
  ];
  return useQuery<IndicatorsResponse>({
    queryKey: key,
    queryFn: async () => {
      const r = await fetch('/api/live/indicators', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      });
      if (!r.ok) throw new Error(`live-indicators ${r.status}`);
      return r.json();
    },
    enabled: enabled && req.bars.length > 0,
    staleTime: 10_000,
  });
}
