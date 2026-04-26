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

export function useGammaLevels(
  ticker: string,
  date: string,
  opts?: { windowPct?: number; spotOverride?: number; enabled?: boolean },
) {
  const { windowPct, spotOverride, enabled = true } = opts ?? {};
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
    staleTime: 3_600_000, // 1 hour — EOD snapshots are immutable once written
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
