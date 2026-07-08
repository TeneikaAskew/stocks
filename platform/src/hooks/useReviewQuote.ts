import { useQuery } from '@tanstack/react-query';
import { useReferenceLevels } from '@/hooks/useMarketData';
import { buildReviewQuote, type Quote } from '@/lib/reviewQuote';
import type { Bar } from '@/lib/indicators';

// ---------------------------------------------------------------------------
// Synthetic "as-of" quote for historical review mode.
//
// In review mode the page must show the price AS OF the selected date+time,
// not the live quote. There is no historical point-in-time quote endpoint, so
// we reconstruct one from that day's 1-minute bars sliced to the review time
// (open/price/high/low/volume) and pair it with the PRIOR SESSION CLOSE
// fetched from /api/market/reference/<ticker>/<date> (the same "prev day
// close" the live quote uses) so `change`/`change_pct` mean the same thing
// in review mode as they do live. The aggregation itself is shared with
// LiveMarketPage via `buildReviewQuote` (lib/reviewQuote.ts) — CLAUDE.md §5,
// one place, one purpose, no divergent review-quote builders.
//
// No silent fallback (§3.7): when the day has no intraday bars the hook
// returns `undefined` so the caller renders "no intraday for <date>" rather
// than a fabricated price; when the prior close can't be resolved,
// buildReviewQuote nulls out change/change_pct rather than rebasing to the
// day's open.
// ---------------------------------------------------------------------------

interface HistoricalDayResponse {
  candlestick: Array<{ time: number; open: number; high: number; low: number; close: number }>;
  volume: Array<{ time: number; value: number }>;
}

// Bars are AlphaVantage ET-wall-clock labeled as UTC unix seconds, so the
// cutoff is built with Date.UTC against the review wall-clock (matches the
// DashboardPage pricePoints / LiveMarketPage reviewTs convention). Exported
// for direct unit testing — the rest of the hook is data-fetching glue.
export function reviewCutoffTs(reviewDate: string, reviewTime: string | null): number {
  const [y, m, d] = reviewDate.split('-').map(Number);
  const [hh, mm] = (reviewTime ?? '16:00').split(':').map(Number);
  return Math.floor(Date.UTC(y, m - 1, d, hh, mm) / 1000);
}

/**
 * Fetch the review day's 1-minute bars plus the prior session close, and
 * reconstruct a synthetic quote as-of `reviewTime` (defaults to the 16:00 ET
 * close). Disabled when `reviewDate` is null (live mode).
 */
export function useReviewQuote(
  ticker: string,
  reviewDate: string | null,
  reviewTime: string | null,
): Quote | undefined {
  const { data } = useQuery<HistoricalDayResponse>({
    queryKey: ['hist-day', ticker, reviewDate],
    queryFn: async () => {
      const compact = reviewDate!.replace(/-/g, '');
      const r = await fetch(`/api/market/data/${ticker}/${compact}?timeframe=1`);
      if (!r.ok) throw new Error(`historical day ${r.status}`);
      return r.json();
    },
    enabled: reviewDate !== null && !!ticker,
    staleTime: 3_600_000,
  });

  // Prior session close — same reference endpoint ChartsPage uses for its
  // reference-levels overlay. `close` on the row keyed to `date` IS the
  // prior day's close (the endpoint returns prev-day OHLC for the date).
  const { data: refLevels } = useReferenceLevels(
    ticker,
    reviewDate ? reviewDate.replace(/-/g, '') : '',
  );

  if (reviewDate === null || !data) return undefined;
  const cutoff = reviewCutoffTs(reviewDate, reviewTime);
  // Map BEFORE filtering so the volume array (1:1 aligned with candlestick by
  // index from the same endpoint) stays aligned; filtering first would shift
  // the index and misattribute volume.
  const bars: Bar[] = data.candlestick
    .map((c, i) => ({
      time: String(c.time),
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      // volume[i] is structurally present (equal-length arrays from one
      // response); the ?? guards an impossible gap, not a missing financial value.
      volume: data.volume[i]?.value ?? 0,
    }))
    .filter((b) => Number(b.time) <= cutoff);
  const label = reviewTime ? `${reviewDate} ${reviewTime} ET` : reviewDate;
  return buildReviewQuote(bars, refLevels?.close ?? null, ticker, label);
}
