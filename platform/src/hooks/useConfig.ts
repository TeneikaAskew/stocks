import { useQuery } from '@tanstack/react-query';

// Server-sourced configuration. Whenever the frontend needs an indicator
// period, RSI zone label, or market-hours boundary, pull it from here rather
// than hardcoding. Python is the source of truth (lib/config.py); these
// endpoints just expose it.

export interface RsiZone {
  max: number;
  label: string;
}

export interface IndicatorConfig {
  rsi: {
    period: number;
    fast_period: number;
    oversold: number;
    overbought: number;
    zones: RsiZone[];
    call_range: [number, number];
    put_range: [number, number];
    call_exit: number;
    put_exit: number;
  };
  ema: { periods: number[] };
  atr: { period: number; high_threshold: number };
  rvol: { period: number; signal_threshold: number };
  stoch_rsi: {
    period: number;
    k_period: number;
    d_period: number;
    oversold: number;
    overbought: number;
  };
  signal: {
    min_conditions: number;
    consecutive_periods: number;
    premarket_threshold: number;
  };
}

export interface MarketHours {
  timezone: string;
  regular: { open: string; close: string };
  pre_market: { open: string; close: string };
  after_hours: { open: string; close: string };
  holidays_2026: string[];
}

// Static config changes rarely — stale for a day, cached forever in a session.
const HOUR = 60 * 60 * 1000;

export function useIndicatorConfig() {
  return useQuery<IndicatorConfig>({
    queryKey: ['config', 'indicators'],
    queryFn: async () => {
      const r = await fetch('/api/config/indicators');
      if (!r.ok) throw new Error(`config/indicators ${r.status}`);
      return r.json();
    },
    staleTime: 24 * HOUR,
    gcTime: 24 * HOUR,
  });
}

export function useMarketHours() {
  return useQuery<MarketHours>({
    queryKey: ['config', 'market-hours'],
    queryFn: async () => {
      const r = await fetch('/api/config/market-hours');
      if (!r.ok) throw new Error(`config/market-hours ${r.status}`);
      return r.json();
    },
    staleTime: 24 * HOUR,
    gcTime: 24 * HOUR,
  });
}

/**
 * Classify an RSI value using server-defined zones. Returns the label
 * for the first zone where `value < zone.max`.
 */
export function classifyRsiZone(value: number | null, zones: RsiZone[] | undefined): string {
  if (value === null || value === undefined || !zones || zones.length === 0) return '';
  for (const z of zones) {
    if (value < z.max) return z.label;
  }
  return zones[zones.length - 1].label;
}
