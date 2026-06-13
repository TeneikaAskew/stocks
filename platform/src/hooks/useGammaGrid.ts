import { useQuery } from '@tanstack/react-query';
import type { SpotEstimate, GammaRegime } from './useGammaLevels';

// ── Shapes returned by GET /api/options/{ticker}/grid (and /{date}/grid) ─────
//
// Server-side 2-D strike × expiration gamma grid: Cloud SQL chain →
// lib.gamma.build_grid_summary[_with_change](). One source of truth for the
// GEX/VEX math — the frontend only renders. `pct_change`/`abs_change` are the
// intraday rate-of-change vs the session-open snapshot (realtime path only;
// null on EOD/historical, just-opened sessions, or near-zero open).

export interface GammaGridCell {
  strike: number;
  expiration: string; // ISO YYYY-MM-DD
  dte: number;
  net_gamma: number;
  call_gamma: number;
  put_gamma: number;
  net_vega: number;
  call_vega: number;
  put_vega: number;
  gex: number;
  call_gex: number;
  put_gex: number;
  vex: number;
  call_vex: number;
  put_vex: number;
  call_oi: number;
  put_oi: number;
  call_volume: number;
  put_volume: number;
  distance_pct: number;
  pct_change: number | null;
  abs_change: number | null;
}

export type GridDataSource =
  | 'realtime'
  | 'eod_fallback'
  | 'stale_fallback'
  | 'unavailable';

export interface GammaGridSummary {
  ticker: string;
  snapshot_date: string | null;
  snapshot_ts: string | null;
  data_source: GridDataSource;
  spot: SpotEstimate;
  gamma_balance: number | null;
  gamma_flip: number | null;
  regime: GammaRegime;
  total_gex: number;
  total_vex: number;
  cells: GammaGridCell[];
  expirations: string[]; // ascending — column headers
  strikes: number[]; // ascending — row headers
  window_pct: number;
  warnings: string[];
  reason?: string; // present on the unavailable envelope
}

async function parseError(r: Response, fallback: string): Promise<string> {
  try {
    const body = await r.json();
    if (typeof body?.detail === 'string') return body.detail;
  } catch {
    /* not JSON */
  }
  return `${fallback} (HTTP ${r.status})`;
}

export function useGammaGrid(
  ticker: string,
  date: string,
  opts?: {
    windowPct?: number;
    /** When true, hit the live endpoint (session-open %-change overlay).
     *  When false, hit the historical /{date}/grid endpoint. */
    live?: boolean;
    enabled?: boolean;
  },
) {
  const { windowPct, live = true, enabled = true } = opts ?? {};
  return useQuery<GammaGridSummary>({
    queryKey: ['gamma-grid', ticker, date, windowPct ?? null, live],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (windowPct !== undefined) {
        params.set('strike_window_pct', String(windowPct));
      }
      const qs = params.toString();
      const url = live
        ? `/api/options/${ticker}/grid${qs ? `?${qs}` : ''}`
        : `/api/options/${ticker}/${date}/grid${qs ? `?${qs}` : ''}`;
      const r = await fetch(url);
      if (!r.ok) throw new Error(await parseError(r, 'Failed to fetch gamma grid'));
      return r.json();
    },
    enabled: enabled && !!ticker && (live || !!date),
    // Live: stay under the 60s server cache and refetch to match its cadence.
    // Historical: EOD snapshots are immutable.
    staleTime: live ? 50_000 : 3_600_000,
    refetchInterval: live ? 60_000 : false,
    retry: false,
  });
}
