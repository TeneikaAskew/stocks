import type { Bar } from '@/lib/indicators';
import type { LiveQuote } from '@/hooks/useLiveQuote';

/** Review-mode quote shares the live-quote shape so both surfaces render
 * through the same components. `change`/`change_pct`/`prev_close` are
 * nullable — review mode is honest when the prior session close can't be
 * resolved (see buildReviewQuote below), so this type has to be too. */
export type Quote = LiveQuote;

/**
 * Synthetic quote for historical review mode, reconstructed from that
 * day's 1-minute bars (already sliced to the review cutoff by the caller).
 *
 * `change`/`change_pct` are computed vs PRIOR SESSION CLOSE — the exact
 * same baseline live quotes use (CLAUDE.md: review mode must mean the same
 * thing "change" means live). If the prior close is unknown, the fields
 * are `null` (rendered as "—" by the caller) — never silently rebased to
 * the day's open, which would misrepresent the number as a same-basis
 * comparison when it isn't (CLAUDE.md §3.7, no silent fallbacks).
 */
export function buildReviewQuote(
  bars: Bar[],
  prevClose: number | null,
  ticker: string,
  lastUpdated: string,
): Quote | undefined {
  if (bars.length === 0) return undefined;
  const first = bars[0];
  const last = bars[bars.length - 1];
  return {
    ticker,
    price: last.close,
    open: first.open,
    high: Math.max(...bars.map((b) => b.high)),
    low: Math.min(...bars.map((b) => b.low)),
    volume: bars.reduce((s, b) => s + b.volume, 0),
    change: prevClose != null ? last.close - prevClose : null,
    change_pct: prevClose != null ? ((last.close - prevClose) / prevClose) * 100 : null,
    prev_close: prevClose,
    last_updated: lastUpdated,
  };
}
