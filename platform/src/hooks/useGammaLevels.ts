import { useQuery } from '@tanstack/react-query';

// ── Shapes returned by GET /api/options/{ticker}/{date}/levels ──────────────
//
// Server-side gamma analytics: Cloud SQL chain → lib.gamma.build_summary()
// → King/Gate/Spot/Flip taxonomy + regime + layered spot estimation.
// Use this hook for the levels panel and chart overlay; the heatmap still
// uses POST /api/options/greeks via useOptionsGreeks.

export interface SpotEstimate {
  price: number;
  method: 'override' | 'parity' | 'delta' | 'median_strike' | 'none';
  note: string;
}

export interface GammaLevel {
  strike: number;
  gex: number;
  net_gamma: number;
  call_oi: number;
  put_oi: number;
  distance_pct: number;
  score: number;
  kind: 'king' | 'gate' | 'spot' | 'flip' | 'none';
  tags: string[];
}

export type GammaRegime = 'positive_gamma' | 'negative_gamma' | 'unknown';

export interface GammaLevelsResponse {
  ticker: string;
  snapshot_date: string;
  spot: SpotEstimate;
  flip: number | null;
  regime: GammaRegime;
  total_gex: number;
  levels: GammaLevel[];
  kings: GammaLevel[];
  gates: GammaLevel[];
  flip_levels: GammaLevel[];
  window_pct: number;
  warnings: string[];
  snapshot_timestamp?: string | null;
  // Track 4 (2026-05-22): populated by the API from etf_options_snapshots —
  // 'REALTIME' for 5-min intraday rows (drives auto-refresh below), 'EOD'
  // for nightly rows. Null when the source row predates the column.
  market_session?: 'REALTIME' | 'EOD' | string | null;
  chain_size: number;
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

// Refresh cadence for REALTIME data. AV REALTIME_OPTIONS fires every 5 min;
// 60s gives the UI 1–4 polls per source-data update without thrashing.
const REALTIME_REFRESH_MS = 60_000;

export function useGammaLevels(
  ticker: string,
  date: string,
  opts?: {
    windowPct?: number;
    spotOverride?: number;
    enabled?: boolean;
    // Track 4: default true — refetches every 60s when the last response was
    // tagged market_session='REALTIME'. EOD data never auto-refreshes.
    autoRefresh?: boolean;
  },
) {
  const {
    windowPct,
    spotOverride,
    enabled = true,
    autoRefresh = true,
  } = opts ?? {};
  return useQuery<GammaLevelsResponse>({
    queryKey: ['gamma-levels', ticker, date, windowPct ?? null, spotOverride ?? null],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (windowPct !== undefined) params.set('window_pct', String(windowPct));
      if (spotOverride !== undefined && spotOverride > 0) {
        params.set('spot', String(spotOverride));
      }
      const qs = params.toString();
      const url = `/api/options/${ticker}/${date}/levels${qs ? `?${qs}` : ''}`;
      const r = await fetch(url);
      if (!r.ok) throw new Error(await parseError(r, 'Failed to fetch gamma levels'));
      return r.json();
    },
    enabled: enabled && !!ticker && !!date,
    // EOD snapshots are immutable once written → 1h staleTime keeps the
    // cache warm. The refetchInterval below independently re-polls REALTIME
    // data without invalidating EOD entries.
    staleTime: 3_600_000,
    refetchInterval: (query) =>
      autoRefresh && query.state.data?.market_session === 'REALTIME'
        ? REALTIME_REFRESH_MS
        : false,
    retry: false,
  });
}

// Friendly label for the spot estimation method, surfaced as a chip in the UI.
export function spotMethodLabel(method: SpotEstimate['method']): string {
  switch (method) {
    case 'parity':
      return 'spot from put-call parity';
    case 'delta':
      return 'spot from delta proxy';
    case 'median_strike':
      return 'spot from median strike (last resort)';
    case 'override':
      return 'spot manually overridden';
    case 'none':
      return 'spot unavailable';
  }
}

export function regimeLabel(regime: GammaRegime): {
  label: string;
  description: string;
  tone: 'positive' | 'negative' | 'neutral';
} {
  switch (regime) {
    case 'positive_gamma':
      return {
        label: 'Positive gamma',
        description: 'Above flip — pinning / range-bound',
        tone: 'positive',
      };
    case 'negative_gamma':
      return {
        label: 'Negative gamma',
        description: 'Below flip — trending / vol-amplifying',
        tone: 'negative',
      };
    case 'unknown':
      return {
        label: 'Regime unclear',
        description: 'No flip detected in window',
        tone: 'neutral',
      };
  }
}
