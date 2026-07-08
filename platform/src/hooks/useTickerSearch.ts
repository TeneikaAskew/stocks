import { useMutation, useQuery } from '@tanstack/react-query';

export interface SearchMatch {
  symbol: string;
  name: string;
  type: string;
  region: string;
  currency: string;
  match_score: number;
}

export interface TickerInfo {
  symbol: string | null;
  name: string | null;
  exchange: string | null;
  sector: string | null;
  industry: string | null;
  market_cap: string | null;
  asset_type: string | null;
  description: string | null;
}

export interface TickerQuote {
  symbol: string;
  open: number | null;
  high: number | null;
  low: number | null;
  price: number | null;
  volume: number | null;
  latest_trading_day: string | null;
  previous_close: number | null;
  change: number | null;
  change_percent: string | null;
}

export interface WatchlistAddResult {
  ticker: string;
  added: boolean;
  info: TickerInfo | null;
  quote: TickerQuote | null;
  watchlist: string[];
}

// ---------------------------------------------------------------------------
// Search tickers by keyword (debounced in component)
// ---------------------------------------------------------------------------

export function useTickerSearch(keywords: string, enabled = true) {
  return useQuery<{ keywords: string; results: SearchMatch[] }>({
    queryKey: ['ticker-search', keywords],
    queryFn: async () => {
      const r = await fetch(
        `/api/insights/ticker/search?keywords=${encodeURIComponent(keywords)}&limit=8`,
      );
      if (!r.ok) throw new Error(`search ${r.status}`);
      return r.json();
    },
    enabled: enabled && keywords.length >= 1,
    staleTime: 60_000,
  });
}

// ---------------------------------------------------------------------------
// Data coverage per symbol (Task 1's /api/market/coverage) — drives the
// TickerCombobox full/daily/new badges.
// ---------------------------------------------------------------------------

export interface TickerCoverage {
  intraday: boolean;
  daily: boolean;
}

export function useTickerCoverage(symbolsCsv: string, enabled = true) {
  return useQuery<{ coverage: Record<string, TickerCoverage> }>({
    queryKey: ['ticker-coverage', symbolsCsv],
    queryFn: async () => {
      const r = await fetch(`/api/market/coverage?symbols=${encodeURIComponent(symbolsCsv)}`);
      if (!r.ok) throw new Error(`coverage ${r.status}`);
      return r.json();
    },
    enabled: enabled && symbolsCsv.length > 0,
    staleTime: 60_000,
  });
}

// ---------------------------------------------------------------------------
// Add ticker to watchlist (POST, returns info + quote)
// ---------------------------------------------------------------------------

export function useAddToWatchlist() {
  return useMutation<WatchlistAddResult, Error, string>({
    mutationFn: async (ticker: string) => {
      const r = await fetch('/api/insights/watchlist/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker }),
      });
      if (!r.ok) {
        // Surface the backend's actual detail (e.g. "Cloud SQL unreachable")
        // rather than a bare status code — callers (TickerCombobox's
        // auto-ingest notice) need the honest reason, not just "add 503".
        let detail = r.statusText;
        try {
          const body = await r.json();
          if (body?.detail) detail = body.detail;
        } catch {
          // response body wasn't JSON — fall back to statusText
        }
        throw new Error(`HTTP ${r.status}: ${detail}`);
      }
      return r.json();
    },
  });
}

// ---------------------------------------------------------------------------
// Remove ticker from watchlist
// ---------------------------------------------------------------------------

export function useRemoveFromWatchlist() {
  return useMutation<{ ticker: string; removed: boolean; watchlist: string[] }, Error, string>({
    mutationFn: async (ticker: string) => {
      const r = await fetch(`/api/insights/watchlist/${encodeURIComponent(ticker)}`, {
        method: 'DELETE',
      });
      if (!r.ok) throw new Error(`remove ${r.status}`);
      return r.json();
    },
  });
}
