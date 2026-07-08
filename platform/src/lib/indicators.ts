/**
 * Shared types for indicator & signal data.
 *
 * The actual math lives in lib/indicators.py (Python) and is exposed via
 * POST /api/live/indicators. The frontend never recomputes these — that
 * was the source of drift between TS and Python implementations.
 */

export interface Bar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Indicators {
  ema9: number | null;
  ema20: number | null;
  ema50: number | null;
  rsi: number | null;
  stochK: number | null;
  stochD: number | null;
  atr: number | null;
  vwap: number | null;
  stochKPrev: number | null;
}

export interface SignalCondition {
  id: string;
  label: string;
  met: boolean;
  current: number | null;
  threshold: number | null;
  operator: '>' | '<';
}

export interface Signal {
  direction: 'CALL' | 'PUT';
  conditions: SignalCondition[];
  strength: number;
  fired: boolean;
}

export const EMPTY_INDICATORS: Indicators = {
  ema9: null,
  ema20: null,
  ema50: null,
  rsi: null,
  stochK: null,
  stochD: null,
  atr: null,
  vwap: null,
  stochKPrev: null,
};

export const EMPTY_SIGNALS: { call: Signal; put: Signal } = {
  call: { direction: 'CALL', conditions: [], strength: 0, fired: false },
  put: { direction: 'PUT', conditions: [], strength: 0, fired: false },
};
