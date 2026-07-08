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

export interface SignalSeriesFire {
  time: string;
  direction: 'CALL' | 'PUT';
  score: number;
  bar_index: number;
}

export interface SignalSeriesResponse {
  fires: SignalSeriesFire[];
}

/**
 * Server-side per-bar signal fires for the Charts page "Sig" overlay.
 *
 * Backed by POST /api/live/signal-series, which runs lib.signals'
 * production mean-reversion voter (the SAME per-bar logic
 * gcp/signal_monitor.py fires live alerts from) over the supplied bar
 * series — there is no client-side re-derivation of the voter.
 *
 * Keyed on `keyId` (caller passes `${ticker}:${selectedDate}`) plus bar
 * count + first-bar time + last-bar time so the query only refetches when
 * the underlying series actually changes. keyId is load-bearing: two
 * tickers can share the same bar count and last-bar timestamp (e.g. both
 * loaded to the same review date), which without a ticker-scoped key
 * would serve one ticker's cached fires under the other ticker's chart.
 */
export function useSignalSeries(bars: Bar[], keyId: string, enabled: boolean) {
  const firstBar = bars.length > 0 ? bars[0] : null;
  const lastBar = bars.length > 0 ? bars[bars.length - 1] : null;
  const key = ['live-signal-series', keyId, bars.length, firstBar?.time ?? null, lastBar?.time ?? null];
  return useQuery<SignalSeriesResponse>({
    queryKey: key,
    queryFn: async () => {
      const r = await fetch('/api/live/signal-series', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bars }),
      });
      if (!r.ok) throw new Error(`live-signal-series ${r.status}`);
      return r.json();
    },
    enabled: enabled && bars.length >= 14,
    staleTime: 10_000,
  });
}
