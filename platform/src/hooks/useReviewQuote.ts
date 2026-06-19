import { useQuery } from '@tanstack/react-query';
import type { LiveQuote } from '@/hooks/useLiveQuote';

// ---------------------------------------------------------------------------
// Synthetic "as-of" quote for historical review mode.
//
// In review mode the page must show the price AS OF the selected date+time,
// not the live quote. There is no historical point-in-time quote endpoint, so
// we reconstruct one from that day's 1-minute bars sliced to the review time:
//   open  = first bar's open
//   price = last (<= cutoff) bar's close
//   high  = max high, low = min low, volume = sum over the window
// This is the same reconstruction LiveMarketPage uses for its hero quote;
// it lives here so both surfaces share one implementation (CLAUDE.md §5).
//
// No silent fallback (§3.7): when the day has no intraday bars the hook
// returns `undefined` so the caller renders "no intraday for <date>" rather
// than a fabricated price.
// ---------------------------------------------------------------------------

export interface OhlcBar {
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/**
 * Aggregate an ordered list of OHLCV bars (already sliced to the review
 * cutoff) into a single synthetic quote. Returns undefined for an empty list.
 */
export function synthQuoteFromBars(
  bars: OhlcBar[],
  ticker: string,
  lastUpdated: string,
): LiveQuote | undefined {
  if (bars.length === 0) return undefined;
  const first = bars[0];
  const last = bars[bars.length - 1];
  const high = Math.max(...bars.map((b) => b.high));
  const low = Math.min(...bars.map((b) => b.low));
  const volume = bars.reduce((s, b) => s + b.volume, 0);
  return {
    ticker,
    price: last.close,
    open: first.open,
    high,
    low,
    volume,
    change: last.close - first.open,
    change_pct: ((last.close - first.open) / first.open) * 100,
    prev_close: first.open,
    last_updated: lastUpdated,
  };
}

interface HistoricalDayResponse {
  candlestick: Array<{ time: number; open: number; high: number; low: number; close: number }>;
  volume: Array<{ time: number; value: number }>;
}

// Bars are AlphaVantage ET-wall-clock labeled as UTC unix seconds, so the
// cutoff is built with Date.UTC against the review wall-clock (matches the
// DashboardPage pricePoints / LiveMarketPage reviewTs convention).
function reviewCutoffTs(reviewDate: string, reviewTime: string | null): number {
  const [y, m, d] = reviewDate.split('-').map(Number);
  const [hh, mm] = (reviewTime ?? '16:00').split(':').map(Number);
  return Math.floor(Date.UTC(y, m - 1, d, hh, mm) / 1000);
}

/**
 * Fetch the review day's 1-minute bars and reconstruct a synthetic quote
 * as-of `reviewTime` (defaults to the 16:00 ET close). Disabled when
 * `reviewDate` is null (live mode).
 */
export function useReviewQuote(
  ticker: string,
  reviewDate: string | null,
  reviewTime: string | null,
): LiveQuote | undefined {
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

  if (reviewDate === null || !data) return undefined;
  const cutoff = reviewCutoffTs(reviewDate, reviewTime);
  // Map BEFORE filtering so the volume array (1:1 aligned with candlestick by
  // index from the same endpoint) stays aligned; filtering first would shift
  // the index and misattribute volume.
  const bars: OhlcBar[] = data.candlestick
    .map((c, i) => ({
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      // volume[i] is structurally present (equal-length arrays from one
      // response); the ?? guards an impossible gap, not a missing financial value.
      volume: data.volume[i]?.value ?? 0,
      time: c.time,
    }))
    .filter((b) => b.time <= cutoff)
    .map(({ time, ...b }) => b);
  const label = reviewTime ? `${reviewDate} ${reviewTime} ET` : reviewDate;
  return synthQuoteFromBars(bars, ticker, label);
}
