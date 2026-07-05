// ---------------------------------------------------------------------------
// useMovementStatement — PHASE 3 data hook for the "Movement Read" card.
//
// Fetches GET /api/movement-statement?ticker=…&timeframe=…. The endpoint is
// behind the MOVEMENT_STATEMENT_ENABLED feature flag on the server:
//
//   - Flag OFF (default): the endpoint returns 404. We surface that as
//     `absent: true` (NOT an error) so the card renders nothing — the
//     feature stays hidden from users until the flag is flipped on.
//   - Flag ON: the endpoint returns the assembled statement, which the card
//     renders verbatim (UNAVAILABLE envelopes included — the card never
//     fabricates a value, per Rule 3.7).
//
// The hook recomputes nothing; it is a thin transport. All math lives in
// lib/movement_statement.py (one source of truth).
// ---------------------------------------------------------------------------
import { useQuery } from '@tanstack/react-query';
import type { MovementStatement } from '@/types';

export interface MovementStatementResult {
  /** The assembled statement, or null when absent (flag OFF / 404). */
  statement: MovementStatement | null;
  /** True when the endpoint 404'd — the feature is OFF and the card hides. */
  absent: boolean;
}

/**
 * Fetch the movement statement for a ticker/timeframe.
 *
 * A 404 (flag OFF) resolves to `{ statement: null, absent: true }` and is
 * NOT retried — it is the expected "feature hidden" state, not a failure.
 * Any other non-OK status throws so the card can show an unavailable note.
 */
export function useMovementStatement(
  ticker: string,
  timeframe: '5m' | '15m' = '15m',
  enabled: boolean = true,
) {
  return useQuery<MovementStatementResult>({
    queryKey: ['movement-statement', ticker, timeframe],
    queryFn: async () => {
      const r = await fetch(
        `/api/movement-statement?ticker=${encodeURIComponent(ticker)}&timeframe=${encodeURIComponent(timeframe)}`,
      );
      if (r.status === 404) {
        // Flag OFF — the endpoint behaves as if it doesn't exist. The card
        // renders nothing; no user-visible change while the flag is OFF.
        return { statement: null, absent: true };
      }
      if (!r.ok) {
        const text = await r.text().catch(() => '');
        throw new Error(`movement-statement ${r.status} ${text}`);
      }
      const statement = (await r.json()) as MovementStatement;
      return { statement, absent: false };
    },
    enabled: enabled && !!ticker,
    staleTime: 30_000,
    // Don't hammer the endpoint when the flag is OFF; a 404 is terminal.
    retry: (failureCount, error) => {
      if (error instanceof Error && /\b404\b/.test(error.message)) return false;
      return failureCount < 2;
    },
  });
}
