import { useQuery } from '@tanstack/react-query';
import type { Timeframe } from '@/types';

interface CandlestickBar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface VolumeBar {
  time: number;
  value: number;
  color: string;
}

interface MarketDataResponse {
  ticker: string;
  date: string;
  timeframe: number;
  count: number;
  candlestick: CandlestickBar[];
  volume: VolumeBar[];
}

interface DatesResponse {
  ticker: string;
  dates: string[];
  months: string[];
}

export function useMarketData(ticker: string, date: string, timeframe: Timeframe) {
  return useQuery<MarketDataResponse>({
    queryKey: ['market-data', ticker, date, timeframe],
    queryFn: async () => {
      const res = await fetch(
        `/api/market/data/${ticker}/${date}?timeframe=${timeframe}`
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Failed to load market data');
      }
      return res.json();
    },
    enabled: !!ticker && !!date,
    staleTime: Infinity, // Historical data doesn't change
  });
}

export function useAvailableDates(ticker: string) {
  return useQuery<DatesResponse>({
    queryKey: ['market-dates', ticker],
    queryFn: async () => {
      const res = await fetch(`/api/market/dates/${ticker}`);
      if (!res.ok) throw new Error('Failed to load dates');
      return res.json();
    },
    enabled: !!ticker,
    staleTime: 5 * 60 * 1000,
  });
}

interface ReferenceLevels {
  ticker: string;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export function useReferenceLevels(ticker: string, date: string) {
  return useQuery<ReferenceLevels | null>({
    queryKey: ['reference-levels', ticker, date],
    queryFn: async () => {
      const res = await fetch(`/api/market/reference/${ticker}/${date}`);
      if (!res.ok) return null;
      return res.json();
    },
    enabled: !!ticker && !!date,
    staleTime: Infinity,
  });
}

export type { CandlestickBar, VolumeBar, MarketDataResponse, ReferenceLevels };
