/**
 * Technical indicator calculations (ported from trading-dashboard.html)
 * All functions operate on arrays of close prices (most recent last).
 */

export function calculateEMA(prices: number[], period: number): number | null {
  if (prices.length < period) return null;
  const k = 2 / (period + 1);
  let ema = prices.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < prices.length; i++) {
    ema = prices[i] * k + ema * (1 - k);
  }
  return ema;
}

export function calculateRSI(prices: number[], period = 14): number | null {
  if (prices.length < period + 1) return null;
  const gains: number[] = [];
  const losses: number[] = [];
  for (let i = 1; i < prices.length; i++) {
    const change = prices[i] - prices[i - 1];
    gains.push(change > 0 ? change : 0);
    losses.push(change < 0 ? Math.abs(change) : 0);
  }
  const avgGain = gains.slice(-period).reduce((a, b) => a + b, 0) / period;
  const avgLoss = losses.slice(-period).reduce((a, b) => a + b, 0) / period;
  if (avgLoss === 0) return 100;
  return 100 - 100 / (1 + avgGain / avgLoss);
}

export function calculateStochRSI(prices: number[], period = 14): { k: number | null; d: number | null } {
  if (prices.length < period * 2) return { k: null, d: null };
  const rsiValues: number[] = [];
  for (let i = period; i < prices.length; i++) {
    const r = calculateRSI(prices.slice(i - period, i + 1));
    if (r !== null) rsiValues.push(r);
  }
  if (rsiValues.length < period) return { k: null, d: null };
  const recent = rsiValues.slice(-period);
  const cur = recent[recent.length - 1];
  const min = Math.min(...recent);
  const max = Math.max(...recent);
  if (max - min === 0) return { k: 50, d: 50 };
  const k = ((cur - min) / (max - min)) * 100;
  return { k, d: k };
}

export function calculateATR(highs: number[], lows: number[], closes: number[], period = 14): number | null {
  if (highs.length < period + 1) return null;
  const trs: number[] = [];
  for (let i = 1; i < highs.length; i++) {
    const hl = highs[i] - lows[i];
    const hc = Math.abs(highs[i] - closes[i - 1]);
    const lc = Math.abs(lows[i] - closes[i - 1]);
    trs.push(Math.max(hl, hc, lc));
  }
  return trs.slice(-period).reduce((a, b) => a + b, 0) / period;
}

/**
 * Volume-Weighted Average Price across the supplied bars.
 * Uses typical price (H+L+C)/3 × volume, summed and divided by total volume.
 * Returns null if bars are empty or total volume is zero.
 */
export function calculateVWAP(bars: Bar[]): number | null {
  if (bars.length === 0) return null;
  let pvSum = 0;
  let volSum = 0;
  for (const b of bars) {
    const typical = (b.high + b.low + b.close) / 3;
    pvSum += typical * b.volume;
    volSum += b.volume;
  }
  if (volSum === 0) return null;
  return pvSum / volSum;
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
}

export interface Bar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export function computeIndicators(bars: Bar[]): Indicators {
  if (bars.length === 0) {
    return { ema9: null, ema20: null, ema50: null, rsi: null, stochK: null, stochD: null, atr: null, vwap: null };
  }
  const closes = bars.map(b => b.close);
  const highs = bars.map(b => b.high);
  const lows = bars.map(b => b.low);
  const stoch = calculateStochRSI(closes);
  return {
    ema9: calculateEMA(closes, 9),
    ema20: calculateEMA(closes, 20),
    ema50: calculateEMA(closes, 50),
    rsi: calculateRSI(closes),
    stochK: stoch.k,
    stochD: stoch.d,
    atr: calculateATR(highs, lows, closes),
    vwap: calculateVWAP(bars),
  };
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
  strength: number; // 0–100
  fired: boolean; // true if strength >= 70
}

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
