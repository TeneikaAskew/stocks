import { useQuery } from '@tanstack/react-query';

// ── Shape returned by GET /api/glossary/gamma ──────────────────────────────
//
// The public glossary payload is the UI-safe subset of lib.gamma_glossary —
// canonical name + definitions + math only. The cross-framework aliases
// (Stratalyst / Heatseeker / SqueezeMetrics / SpotGamma) live server-side
// in Python and are stripped before serialization. The public UI speaks
// our canonical vocabulary only — see Phase 0 of
// docs/plans/HEATSEEKER_STYLE_GAMMA_PLAN.md §1.7.5.

export interface GammaTerm {
  canonical: string;
  short_definition: string;
  long_definition: string;
  math: string | null;
}

export interface GammaGlossary {
  terms: Record<string, GammaTerm>;
  version: string;
}

async function parseError(r: Response, fallback: string): Promise<string> {
  try {
    const body = await r.json();
    if (typeof body?.detail === 'string') return body.detail;
  } catch {
    /* fall through */
  }
  return fallback;
}

/**
 * Fetch the gamma term glossary once at app boot.
 *
 * The endpoint serves a module constant that only changes on deploy, so
 * we cache it indefinitely via React Query's `staleTime: Infinity`. The
 * server already returns `Cache-Control: public, max-age=3600` so even
 * a hard refresh hits the browser cache for an hour.
 *
 * The `<TermHover>` component (shared/TermHover.tsx) calls this hook
 * once at app boot via the layout root; individual term hovers read
 * from the React Query cache, so there's exactly one network call per
 * session.
 */
export function useGammaGlossary() {
  return useQuery<GammaGlossary>({
    queryKey: ['gamma-glossary'],
    queryFn: async () => {
      const r = await fetch('/api/glossary/gamma');
      if (!r.ok) throw new Error(await parseError(r, 'Failed to fetch glossary'));
      return r.json();
    },
    staleTime: Infinity,
    gcTime: Infinity,
    retry: 1,
  });
}

/**
 * Synchronous lookup for a single term from the cached glossary.
 * Returns null when the glossary hasn't loaded yet or the key is
 * unknown — callers render the wrapped text plain (no tooltip)
 * rather than blocking or surfacing an error.
 */
export function useGammaTerm(termKey: string): GammaTerm | null {
  const { data } = useGammaGlossary();
  return data?.terms[termKey] ?? null;
}
