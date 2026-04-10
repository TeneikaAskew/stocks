import type { Bar, Indicators } from './indicators';

/**
 * Snapshot of live market state used to evaluate playbook condition strings.
 * Values may be null when the market is closed, history is thin, or a
 * particular indicator wasn't supplied.
 */
export interface MarketSnapshot {
  price: number | null;
  prevClose: number | null;
  prevHigh: number | null;
  prevLow: number | null;
  volumeToday: number | null;
  avgVolume20d: number | null;
  orbHigh: number | null;   // first 30 min of regular session
  orbLow: number | null;
  lastBar: Bar | null;
  minutesSinceOpen: number | null;
  stochKPrev: number | null;
  indicators: Indicators;
}

export type EvalResult =
  | { status: 'met'; detail: string }
  | { status: 'unmet'; detail: string }
  | { status: 'unknown'; reason: string };

export function evalCondition(raw: string, s: MarketSnapshot): EvalResult {
  const c = raw.trim();
  const lower = c.toLowerCase();

  // Helper: compare with null-guarding
  const cmp = (
    lhs: number | null,
    op: '>' | '<' | '>=' | '<=',
    rhs: number | null,
    label: (lv: number, rv: number) => string,
  ): EvalResult => {
    if (lhs === null || rhs === null) return { status: 'unknown', reason: 'missing data' };
    const met =
      op === '>' ? lhs > rhs :
      op === '<' ? lhs < rhs :
      op === '>=' ? lhs >= rhs :
      lhs <= rhs;
    return { status: met ? 'met' : 'unmet', detail: label(lhs, rhs) };
  };

  const ind = s.indicators;

  // RSI range: "RSI between 40-65 (not overbought yet)"
  const rsiBetween = c.match(/RSI between\s+(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)/i);
  if (rsiBetween) {
    const lo = Number(rsiBetween[1]);
    const hi = Number(rsiBetween[2]);
    if (ind.rsi === null) return { status: 'unknown', reason: 'RSI n/a' };
    const met = ind.rsi >= lo && ind.rsi <= hi;
    return { status: met ? 'met' : 'unmet', detail: `RSI ${ind.rsi.toFixed(1)} in [${lo}, ${hi}]` };
  }

  // "RSI < N", "RSI not overbought (< N)", "RSI > N"
  const rsiCmp = c.match(/RSI[^<>]*(<|>)\s*(\d+(?:\.\d+)?)/i);
  if (rsiCmp && /rsi/i.test(c)) {
    const op = rsiCmp[1] as '<' | '>';
    const n = Number(rsiCmp[2]);
    return cmp(ind.rsi, op, n, (lv) => `RSI ${lv.toFixed(1)} ${op} ${n}`);
  }

  // "Price above VWAP" / "Price below VWAP"
  if (/price\s+(above|>)\s+vwap/i.test(c)) {
    return cmp(s.price, '>', ind.vwap, (lv, rv) => `${lv.toFixed(2)} > VWAP ${rv.toFixed(2)}`);
  }
  if (/price\s+(below|<)\s+vwap/i.test(c)) {
    return cmp(s.price, '<', ind.vwap, (lv, rv) => `${lv.toFixed(2)} < VWAP ${rv.toFixed(2)}`);
  }

  // "Price above EMA9" / "Price below EMA20" / etc.
  const priceEma = c.match(/price\s+(above|below|>|<)\s+ema\s*(\d+)/i);
  if (priceEma) {
    const dir = priceEma[1].toLowerCase();
    const n = Number(priceEma[2]);
    const ema = n === 9 ? ind.ema9 : n === 20 ? ind.ema20 : n === 50 ? ind.ema50 : null;
    if (ema === null) return { status: 'unknown', reason: `EMA${n} n/a` };
    const op: '>' | '<' = (dir === 'above' || dir === '>') ? '>' : '<';
    return cmp(s.price, op, ema, (lv, rv) => `${lv.toFixed(2)} ${op} EMA${n} ${rv.toFixed(2)}`);
  }

  // "EMA9 > EMA20 (bullish cross)" / "EMA9 < EMA20 (bearish cross)"
  const emaCross = c.match(/ema\s*(\d+)\s*(>|<)\s*ema\s*(\d+)/i);
  if (emaCross) {
    const n1 = Number(emaCross[1]);
    const op = emaCross[2] as '>' | '<';
    const n2 = Number(emaCross[3]);
    const e1 = n1 === 9 ? ind.ema9 : n1 === 20 ? ind.ema20 : n1 === 50 ? ind.ema50 : null;
    const e2 = n2 === 9 ? ind.ema9 : n2 === 20 ? ind.ema20 : n2 === 50 ? ind.ema50 : null;
    return cmp(e1, op, e2, (lv, rv) => `EMA${n1} ${lv.toFixed(2)} ${op} EMA${n2} ${rv.toFixed(2)}`);
  }

  // "RVOL > X" / "Volume confirming (RVOL > X)" / "Volume above average (RVOL > X)"
  const rvol = c.match(/rvol\s*(>|<)\s*(\d+(?:\.\d+)?)/i);
  if (rvol) {
    const op = rvol[1] as '>' | '<';
    const n = Number(rvol[2]);
    const r =
      s.volumeToday !== null && s.avgVolume20d !== null && s.avgVolume20d > 0
        ? s.volumeToday / s.avgVolume20d
        : null;
    return cmp(r, op, n, (lv) => `RVOL ${lv.toFixed(2)} ${op} ${n}`);
  }

  // StochRSI oversold turning up / overbought turning down
  if (/stochrsi was oversold.*turning up/i.test(c)) {
    if (ind.stochK === null || s.stochKPrev === null) {
      return { status: 'unknown', reason: 'StochRSI n/a' };
    }
    const thr = Number((c.match(/<\s*(\d+)/) || [, '20'])[1]);
    const wasOversold = s.stochKPrev < thr;
    const turningUp = ind.stochK > s.stochKPrev;
    const met = wasOversold && turningUp;
    return { status: met ? 'met' : 'unmet', detail: `StochK ${s.stochKPrev.toFixed(0)}→${ind.stochK.toFixed(0)}` };
  }
  if (/stochrsi was overbought.*turning down/i.test(c)) {
    if (ind.stochK === null || s.stochKPrev === null) {
      return { status: 'unknown', reason: 'StochRSI n/a' };
    }
    const thr = Number((c.match(/>\s*(\d+)/) || [, '80'])[1]);
    const wasOverbought = s.stochKPrev > thr;
    const turningDown = ind.stochK < s.stochKPrev;
    const met = wasOverbought && turningDown;
    return { status: met ? 'met' : 'unmet', detail: `StochK ${s.stochKPrev.toFixed(0)}→${ind.stochK.toFixed(0)}` };
  }

  // ORB-based conditions
  if (/broken above.*opening range high|above\s+orb\s+high|orb\s+high\s+break/i.test(c)) {
    return cmp(s.price, '>', s.orbHigh, (lv, rv) => `${lv.toFixed(2)} > ORB-H ${rv.toFixed(2)}`);
  }
  if (/broken below.*opening range low|below\s+orb\s+low|orb\s+low\s+break/i.test(c)) {
    return cmp(s.price, '<', s.orbLow, (lv, rv) => `${lv.toFixed(2)} < ORB-L ${rv.toFixed(2)}`);
  }
  if (/orb\s*30m\s*trend is bullish/i.test(c)) {
    if (s.price === null || s.orbHigh === null || s.orbLow === null) {
      return { status: 'unknown', reason: 'ORB n/a' };
    }
    const mid = (s.orbHigh + s.orbLow) / 2;
    const met = s.price > mid;
    return { status: met ? 'met' : 'unmet', detail: `${s.price.toFixed(2)} ${met ? '>' : '<'} ORB-mid ${mid.toFixed(2)}` };
  }
  if (/orb\s*30m\s*trend is bearish/i.test(c)) {
    if (s.price === null || s.orbHigh === null || s.orbLow === null) {
      return { status: 'unknown', reason: 'ORB n/a' };
    }
    const mid = (s.orbHigh + s.orbLow) / 2;
    const met = s.price < mid;
    return { status: met ? 'met' : 'unmet', detail: `${s.price.toFixed(2)} ${met ? '<' : '>'} ORB-mid ${mid.toFixed(2)}` };
  }

  // "At least X min after market open"
  const sinceOpen = c.match(/at least\s+(\d+)\s*min(?:ute)?s?\s+after\s+market\s+open/i);
  if (sinceOpen) {
    const n = Number(sinceOpen[1]);
    if (s.minutesSinceOpen === null) return { status: 'unknown', reason: 'market closed' };
    const met = s.minutesSinceOpen >= n;
    return { status: met ? 'met' : 'unmet', detail: `${Math.floor(s.minutesSinceOpen)} min since open` };
  }

  // "Close in upper half of the bar's range"
  if (/close in upper half/i.test(c)) {
    if (!s.lastBar) return { status: 'unknown', reason: 'no bar' };
    const mid = (s.lastBar.high + s.lastBar.low) / 2;
    const met = s.lastBar.close > mid;
    return { status: met ? 'met' : 'unmet', detail: `close ${s.lastBar.close.toFixed(2)} vs mid ${mid.toFixed(2)}` };
  }
  if (/close in lower half/i.test(c)) {
    if (!s.lastBar) return { status: 'unknown', reason: 'no bar' };
    const mid = (s.lastBar.high + s.lastBar.low) / 2;
    const met = s.lastBar.close < mid;
    return { status: met ? 'met' : 'unmet', detail: `close ${s.lastBar.close.toFixed(2)} vs mid ${mid.toFixed(2)}` };
  }

  // Price at/near prev day support (prev day low, VWAP) / resistance (prev day high)
  if (/price at or near (support|resistance)/i.test(c)) {
    const isSupport = /support/i.test(c);
    const anchor = isSupport ? s.prevLow : s.prevHigh;
    if (s.price === null || anchor === null) return { status: 'unknown', reason: 'no reference level' };
    const pct = Math.abs(s.price - anchor) / anchor;
    const met = pct <= 0.005; // within 0.5%
    return { status: met ? 'met' : 'unmet', detail: `${(pct * 100).toFixed(2)}% from prev ${isSupport ? 'low' : 'high'}` };
  }

  // Subjective / unparseable
  if (/higher timeframe supports/i.test(lower)) {
    return { status: 'unknown', reason: 'subjective' };
  }
  if (/type\s*3|strat|outside bar|inside bar|2u-?2u|2d-?2d/i.test(lower)) {
    return { status: 'unknown', reason: 'strat pattern' };
  }

  return { status: 'unknown', reason: 'unrecognized' };
}

export function evalConditions(conditions: string[], s: MarketSnapshot): EvalResult[] {
  return conditions.map(c => evalCondition(c, s));
}

/** Compute ORB (first 30 min of regular session) high/low from intraday bars. */
export function computeORB(bars: Bar[]): { high: number | null; low: number | null } {
  if (bars.length === 0) return { high: null, low: null };
  // Regular session = 09:30 ET; first 30 min = 09:30–10:00. Bars use AV time strings like "2026-04-10 09:30:00".
  const orbBars = bars.filter(b => {
    const m = b.time.match(/\b(\d{2}):(\d{2}):/);
    if (!m) return false;
    const h = Number(m[1]);
    const min = Number(m[2]);
    const t = h * 60 + min;
    return t >= 9 * 60 + 30 && t < 10 * 60;
  });
  if (orbBars.length === 0) return { high: null, low: null };
  return {
    high: Math.max(...orbBars.map(b => b.high)),
    low: Math.min(...orbBars.map(b => b.low)),
  };
}

/** Minutes since 09:30 ET for the latest bar. Null if bars empty or pre-market. */
export function minutesSinceOpen(lastBar: Bar | null): number | null {
  if (!lastBar) return null;
  const m = lastBar.time.match(/\b(\d{2}):(\d{2}):/);
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  const t = h * 60 + min;
  const openMin = 9 * 60 + 30;
  if (t < openMin) return null;
  return t - openMin;
}
