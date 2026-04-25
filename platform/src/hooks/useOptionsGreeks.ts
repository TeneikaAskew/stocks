import { useQuery } from '@tanstack/react-query';

// ── Shapes returned by POST /api/options/greeks ─────────────────────────────
//
// All Greek math (GEX, VEX, zero-gamma, max-pain, implied move, node
// detection) is computed server-side in platform/api/routers/options.py.
// The frontend never duplicates this math — if you find yourself needing
// a number the server doesn't return, add it to the endpoint instead.

export interface OptionRecord {
  type: 'call' | 'put';
  strike: number;
  open_interest: number | null;
  gamma: number | null;
  vega: number | null;
  delta: number | null;
  volume: number | null;
}

export interface AggregatedStrike {
  strike: number;
  net_gamma: number;
  call_gamma: number;
  put_gamma: number;
  call_oi: number;
  put_oi: number;
  call_volume: number;
  put_volume: number;
}

export interface GEXByStrike {
  strike: number;
  gex: number;
  call_gex: number;
  put_gex: number;
}

export interface OptionsMetrics {
  total_gex: number;
  total_vex: number;
  zero_gamma: number | null;
  max_pain: number | null;
  implied_move: number | null;
  put_call_ratio: number;
}

export interface StrikeNode {
  type: 'king' | 'gatekeeper' | 'midpoint';
  strike: number;
  gamma: number;
  distance_from_spot: number;
  distance_percent: number;
  lower_bound?: number;
  upper_bound?: number;
}

export interface NodeResult {
  kingNode: StrikeNode | null;
  gatekeepers: StrikeNode[];
  midpoints: StrikeNode[];
  allNodes: StrikeNode[];
}

export interface GreeksConfig {
  strike_range_pct: number;
  atm_tolerance: number;
  node_min_gamma: number;
}

export interface GreeksResponse {
  aggregated: AggregatedStrike[];
  gex_by_strike: GEXByStrike[];
  metrics: OptionsMetrics;
  nodes: NodeResult;
  config: GreeksConfig;
}

export function useOptionsGreeks(
  options: OptionRecord[] | undefined,
  spotPrice: number,
  strikeRangePct?: number,
) {
  const enabled = !!options && options.length > 0 && spotPrice > 0;
  return useQuery<GreeksResponse>({
    queryKey: ['options-greeks', options?.length ?? 0, spotPrice, strikeRangePct ?? null],
    queryFn: async () => {
      const r = await fetch('/api/options/greeks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          options: options ?? [],
          spot_price: spotPrice,
          strike_range_pct: strikeRangePct ?? null,
        }),
      });
      if (!r.ok) throw new Error(`options-greeks ${r.status}`);
      return r.json();
    },
    enabled,
    staleTime: 60_000,
  });
}

export const EMPTY_GREEKS: GreeksResponse = {
  aggregated: [],
  gex_by_strike: [],
  metrics: {
    total_gex: 0,
    total_vex: 0,
    zero_gamma: null,
    max_pain: null,
    implied_move: null,
    put_call_ratio: 0,
  },
  nodes: { kingNode: null, gatekeepers: [], midpoints: [], allNodes: [] },
  config: { strike_range_pct: 0.15, atm_tolerance: 0.02, node_min_gamma: 500 },
};
