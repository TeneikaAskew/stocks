import { useQuery } from '@tanstack/react-query';
import type { EvalResult, MarketSnapshot } from '@/lib/playbookEvaluator';

// All condition parsing + threshold logic is server-side
// (platform/api/routers/playbook.py). These hooks are thin wrappers.

interface FlatResponse {
  results: EvalResult[];
}

interface BatchResponse {
  results_by_key: Record<string, EvalResult[]>;
}

/**
 * Evaluate a flat list of conditions against the snapshot. Used by
 * DashboardPage which shows results for the top-card only.
 */
export function usePlaybookEvaluation(
  conditions: string[] | undefined,
  snapshot: MarketSnapshot | null,
) {
  const ready = !!snapshot && !!conditions && conditions.length > 0;
  return useQuery<EvalResult[]>({
    queryKey: ['playbook-eval', snapshot ? signatureForSnapshot(snapshot) : null, conditions],
    queryFn: async () => {
      const r = await fetch('/api/playbook/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ snapshot, conditions }),
      });
      if (!r.ok) throw new Error(`playbook-eval ${r.status}`);
      const data: FlatResponse = await r.json();
      return data.results;
    },
    enabled: ready,
    staleTime: 30_000,
  });
}

/**
 * Evaluate per-card batches of conditions in a single request. Returns a
 * Map keyed by the card id (same keys the caller passed in).
 */
export function usePlaybookBatch(
  batches: Record<string, string[]> | undefined,
  snapshot: MarketSnapshot | null,
) {
  const keys = batches ? Object.keys(batches) : [];
  const ready = !!snapshot && keys.length > 0;
  return useQuery<Map<string, EvalResult[]>>({
    queryKey: [
      'playbook-batch',
      snapshot ? signatureForSnapshot(snapshot) : null,
      keys,
      batches ? keys.map((k) => batches[k].length) : [],
    ],
    queryFn: async () => {
      const r = await fetch('/api/playbook/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ snapshot, batches }),
      });
      if (!r.ok) throw new Error(`playbook-batch ${r.status}`);
      const data: BatchResponse = await r.json();
      return new Map(Object.entries(data.results_by_key));
    },
    enabled: ready,
    staleTime: 30_000,
  });
}

// Short digest used in queryKey so React Query refetches when the snapshot
// changes meaningfully (price, volume, indicators) without triggering on
// every render.
function signatureForSnapshot(s: MarketSnapshot): string {
  const ind = s.indicators;
  return [
    s.price,
    s.volumeToday,
    s.orbHigh,
    s.orbLow,
    s.minutesSinceOpen,
    ind.ema9,
    ind.ema20,
    ind.ema50,
    ind.rsi,
    ind.stochK,
    ind.atr,
    ind.vwap,
  ].join('|');
}
