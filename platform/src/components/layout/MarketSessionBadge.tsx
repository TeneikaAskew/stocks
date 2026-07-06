import { useLiveStatus } from '@/hooks/useLiveStatus';

const SESSION_CHIP: Record<string, { text: string; live?: boolean }> = {
  regular: { text: 'LIVE', live: true },
  'pre-market': { text: 'PRE' },
  'after-hours': { text: 'AH' },
  closed: { text: 'CLOSED' },
};

/**
 * Truthful market-session chip for the Market nav entry. Green LIVE only
 * while the regular session is actually open; PRE / AH / CLOSED otherwise.
 * Renders nothing while status is loading or unavailable — no fabricated
 * state (CLAUDE.md Rule 3.7). Source: GET /api/live/status via
 * useLiveStatus (60s refetch).
 */
export function MarketSessionBadge() {
  const { data } = useLiveStatus();
  const chip = data ? SESSION_CHIP[data.session] : undefined;
  if (!chip) return null;
  return (
    <span data-testid="market-session-badge" className={`nav-badge${chip.live ? ' live' : ''}`}>
      {chip.text}
    </span>
  );
}
