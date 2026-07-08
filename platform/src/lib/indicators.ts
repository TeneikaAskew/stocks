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

export function computeSignals(
  price: number | null,
  vwap: number | null,
  ind: Indicators,
  volume: number | null,
  avgVolume: number | null,
): { call: Signal; put: Signal } {
  const rvol = volume && avgVolume && avgVolume > 0 ? volume / avgVolume : null;

  function cond(id: string, label: string, met: boolean, current: number | null, threshold: number | null, op: '>' | '<'): SignalCondition {
    return { id, label, met: current !== null && threshold !== null ? met : false, current, threshold, operator: op };
  }

  const callConds: SignalCondition[] = [
    cond('c_p_ema9', 'Price > EMA9', (price ?? 0) > (ind.ema9 ?? Infinity), price, ind.ema9, '>'),
    cond('c_p_ema20', 'Price > EMA20', (price ?? 0) > (ind.ema20 ?? Infinity), price, ind.ema20, '>'),
    cond('c_p_ema50', 'Price > EMA50', (price ?? 0) > (ind.ema50 ?? Infinity), price, ind.ema50, '>'),
    cond('c_p_vwap', 'Price > VWAP', (price ?? 0) > (vwap ?? Infinity), price, vwap, '>'),
    cond('c_rsi50', 'RSI > 50', (ind.rsi ?? 0) > 50, ind.rsi, 50, '>'),
    cond('c_rsi60', 'RSI > 60', (ind.rsi ?? 0) > 60, ind.rsi, 60, '>'),
    cond('c_stoch70', 'StochRSI > 70', (ind.stochK ?? 0) > 70, ind.stochK, 70, '>'),
    cond('c_rvol', 'RVOL > 1.0', (rvol ?? 0) > 1.0, rvol, 1.0, '>'),
    cond('c_cross', 'EMA9 > EMA20', (ind.ema9 ?? 0) > (ind.ema20 ?? Infinity), ind.ema9, ind.ema20, '>'),
    cond('c_atr', 'ATR > 2.0', (ind.atr ?? 0) > 2.0, ind.atr, 2.0, '>'),
  ];

  const putConds: SignalCondition[] = [
    cond('p_p_ema9', 'Price < EMA9', (price ?? Infinity) < (ind.ema9 ?? 0), price, ind.ema9, '<'),
    cond('p_p_ema20', 'Price < EMA20', (price ?? Infinity) < (ind.ema20 ?? 0), price, ind.ema20, '<'),
    cond('p_p_ema50', 'Price < EMA50', (price ?? Infinity) < (ind.ema50 ?? 0), price, ind.ema50, '<'),
    cond('p_p_vwap', 'Price < VWAP', (price ?? Infinity) < (vwap ?? 0), price, vwap, '<'),
    cond('p_rsi50', 'RSI < 50', (ind.rsi ?? 100) < 50, ind.rsi, 50, '<'),
    cond('p_rsi40', 'RSI < 40', (ind.rsi ?? 100) < 40, ind.rsi, 40, '<'),
    cond('p_stoch30', 'StochRSI < 30', (ind.stochK ?? 100) < 30, ind.stochK, 30, '<'),
    cond('p_rvol', 'RVOL > 1.0', (rvol ?? 0) > 1.0, rvol, 1.0, '>'),
    cond('p_cross', 'EMA9 < EMA20', (ind.ema9 ?? Infinity) < (ind.ema20 ?? 0), ind.ema9, ind.ema20, '<'),
    cond('p_atr', 'ATR > 2.0', (ind.atr ?? 0) > 2.0, ind.atr, 2.0, '>'),
  ];

  const callStrength = Math.round((callConds.filter(c => c.met).length / callConds.length) * 100);
  const putStrength = Math.round((putConds.filter(c => c.met).length / putConds.length) * 100);

  return {
    call: { direction: 'CALL', conditions: callConds, strength: callStrength, fired: callStrength >= 70 },
    put: { direction: 'PUT', conditions: putConds, strength: putStrength, fired: putStrength >= 70 },
  };
}
