import { describe, it, expect } from 'vitest';
import {
  evalCondition,
  evalConditions,
  computeORB,
  minutesSinceOpen,
  type MarketSnapshot,
} from './playbookEvaluator';
import type { Indicators, Bar } from './indicators';

function makeIndicators(overrides: Partial<Indicators> = {}): Indicators {
  return {
    ema9: 200, ema20: 198, ema50: 195, rsi: 55,
    stochK: 60, stochD: 58, atr: 3.5, vwap: 199,
    ...overrides,
  };
}

function makeSnapshot(overrides: Partial<MarketSnapshot> = {}): MarketSnapshot {
  return {
    price: 201,
    prevClose: 198,
    prevHigh: 203,
    prevLow: 196,
    volumeToday: 15_000_000,
    avgVolume20d: 12_000_000,
    orbHigh: 202,
    orbLow: 199,
    lastBar: { time: '2026-04-10 10:15:00', open: 200.5, high: 201.5, low: 200, close: 201, volume: 50000 },
    minutesSinceOpen: 45,
    stochKPrev: 55,
    indicators: makeIndicators(),
    ...overrides,
  };
}

// ── RSI conditions ────────────────────────────────────────────────────────

describe('RSI conditions', () => {
  it('RSI between range — met', () => {
    const r = evalCondition('RSI between 40-65 (not overbought yet)', makeSnapshot());
    expect(r.status).toBe('met');
  });

  it('RSI between range — unmet (too high)', () => {
    const s = makeSnapshot({ indicators: makeIndicators({ rsi: 70 }) });
    const r = evalCondition('RSI between 40-65 (not overbought yet)', s);
    expect(r.status).toBe('unmet');
  });

  it('RSI between range — unmet (too low)', () => {
    const s = makeSnapshot({ indicators: makeIndicators({ rsi: 30 }) });
    const r = evalCondition('RSI between 35-60 (not oversold yet)', s);
    expect(r.status).toBe('unmet');
  });

  it('RSI between with en-dash separator', () => {
    const r = evalCondition('RSI between 40\u201365', makeSnapshot());
    expect(r.status).toBe('met');
  });

  it('RSI < threshold — met', () => {
    const s = makeSnapshot({ indicators: makeIndicators({ rsi: 40 }) });
    const r = evalCondition('RSI < 45 (was oversold from the 2D move)', s);
    expect(r.status).toBe('met');
  });

  it('RSI < threshold — unmet', () => {
    const r = evalCondition('RSI < 45', makeSnapshot()); // RSI 55
    expect(r.status).toBe('unmet');
  });

  it('RSI > threshold — met', () => {
    const r = evalCondition('RSI > 50', makeSnapshot()); // RSI 55
    expect(r.status).toBe('met');
  });

  it('RSI not overbought — met', () => {
    const r = evalCondition('RSI not overbought (< 70)', makeSnapshot()); // RSI 55
    expect(r.status).toBe('met');
  });

  it('RSI not overbought — unmet', () => {
    const s = makeSnapshot({ indicators: makeIndicators({ rsi: 75 }) });
    const r = evalCondition('RSI not overbought (< 70)', s);
    expect(r.status).toBe('unmet');
  });

  it('RSI null → unknown', () => {
    const s = makeSnapshot({ indicators: makeIndicators({ rsi: null }) });
    const r = evalCondition('RSI between 40-65', s);
    expect(r.status).toBe('unknown');
  });
});

// ── Price vs VWAP ─────────────────────────────────────────────────────────

describe('Price vs VWAP', () => {
  it('Price above VWAP — met', () => {
    const r = evalCondition('Price above VWAP', makeSnapshot()); // price 201 > vwap 199
    expect(r.status).toBe('met');
  });

  it('Price above VWAP — unmet', () => {
    const s = makeSnapshot({ price: 197 });
    const r = evalCondition('Price above VWAP', s);
    expect(r.status).toBe('unmet');
  });

  it('Price below VWAP — met', () => {
    const s = makeSnapshot({ price: 197 });
    const r = evalCondition('Price below VWAP', s);
    expect(r.status).toBe('met');
  });

  it('Price below VWAP — unmet', () => {
    const r = evalCondition('Price below VWAP', makeSnapshot());
    expect(r.status).toBe('unmet');
  });
});

// ── Price vs EMA ──────────────────────────────────────────────────────────

describe('Price vs EMA', () => {
  it('Price above EMA9 — met', () => {
    const r = evalCondition('Price above EMA9', makeSnapshot()); // 201 > 200
    expect(r.status).toBe('met');
  });

  it('Price below EMA9 — met', () => {
    const s = makeSnapshot({ price: 199 });
    const r = evalCondition('Price below EMA9', s); // 199 < 200
    expect(r.status).toBe('met');
  });

  it('Price above EMA20 — met', () => {
    const r = evalCondition('Price above EMA20', makeSnapshot()); // 201 > 198
    expect(r.status).toBe('met');
  });

  it('Price above EMA50 — met', () => {
    const r = evalCondition('Price above EMA50', makeSnapshot()); // 201 > 195
    expect(r.status).toBe('met');
  });

  it('unsupported EMA period → unknown', () => {
    const r = evalCondition('Price above EMA200', makeSnapshot());
    expect(r.status).toBe('unknown');
  });
});

// ── EMA cross ─────────────────────────────────────────────────────────────

describe('EMA cross', () => {
  it('EMA9 > EMA20 (bullish cross) — met', () => {
    const r = evalCondition('EMA9 > EMA20 (bullish cross)', makeSnapshot()); // 200 > 198
    expect(r.status).toBe('met');
  });

  it('EMA9 < EMA20 (bearish cross) — unmet', () => {
    const r = evalCondition('EMA9 < EMA20 (bearish cross)', makeSnapshot()); // 200 < 198 = false
    expect(r.status).toBe('unmet');
  });

  it('EMA9 < EMA20 (bearish cross) — met', () => {
    const s = makeSnapshot({ indicators: makeIndicators({ ema9: 196, ema20: 198 }) });
    const r = evalCondition('EMA9 < EMA20 (bearish cross)', s);
    expect(r.status).toBe('met');
  });
});

// ── RVOL ──────────────────────────────────────────────────────────────────

describe('RVOL', () => {
  it('RVOL > 1.0 — met (volume 15M vs avg 12M = 1.25)', () => {
    const r = evalCondition('Volume confirming (RVOL > 1.0)', makeSnapshot());
    expect(r.status).toBe('met');
  });

  it('RVOL > 1.2 — met', () => {
    const r = evalCondition('Volume above average (RVOL > 1.2)', makeSnapshot());
    expect(r.status).toBe('met');
  });

  it('RVOL > 1.5 — unmet', () => {
    const r = evalCondition('RVOL > 1.5', makeSnapshot()); // 1.25 < 1.5
    expect(r.status).toBe('unmet');
  });

  it('RVOL with null volume → unknown', () => {
    const s = makeSnapshot({ volumeToday: null });
    const r = evalCondition('RVOL > 1.0', s);
    expect(r.status).toBe('unknown');
  });
});

// ── StochRSI ──────────────────────────────────────────────────────────────

describe('StochRSI', () => {
  it('oversold turning up — met', () => {
    const s = makeSnapshot({
      stochKPrev: 15, // was oversold (< 20)
      indicators: makeIndicators({ stochK: 25 }), // now turning up (25 > 15)
    });
    const r = evalCondition('StochRSI was oversold (< 20), now turning up', s);
    expect(r.status).toBe('met');
  });

  it('oversold turning up — unmet (not oversold)', () => {
    const s = makeSnapshot({
      stochKPrev: 30, // not oversold
      indicators: makeIndicators({ stochK: 35 }),
    });
    const r = evalCondition('StochRSI was oversold (< 20), now turning up', s);
    expect(r.status).toBe('unmet');
  });

  it('overbought turning down — met', () => {
    const s = makeSnapshot({
      stochKPrev: 85,
      indicators: makeIndicators({ stochK: 75 }),
    });
    const r = evalCondition('StochRSI was overbought (> 80), now turning down', s);
    expect(r.status).toBe('met');
  });

  it('StochK null → unknown', () => {
    const s = makeSnapshot({ indicators: makeIndicators({ stochK: null }), stochKPrev: null });
    const r = evalCondition('StochRSI was oversold (< 20), now turning up', s);
    expect(r.status).toBe('unknown');
  });
});

// ── ORB conditions ────────────────────────────────────────────────────────

describe('ORB conditions', () => {
  it('broken above ORB high — met', () => {
    const s = makeSnapshot({ price: 203, orbHigh: 202 });
    const r = evalCondition('Price has broken above 30m Opening Range High', s);
    expect(r.status).toBe('met');
  });

  it('broken above ORB high — unmet', () => {
    const s = makeSnapshot({ price: 201, orbHigh: 202 });
    const r = evalCondition('Price has broken above 30m Opening Range High', s);
    expect(r.status).toBe('unmet');
  });

  it('broken below ORB low — met', () => {
    const s = makeSnapshot({ price: 198, orbLow: 199 });
    const r = evalCondition('Price has broken below 30m Opening Range Low', s);
    expect(r.status).toBe('met');
  });

  it('ORB 30m trend bullish — met (price above midpoint)', () => {
    const s = makeSnapshot({ price: 201.5, orbHigh: 202, orbLow: 199 }); // mid 200.5
    const r = evalCondition('ORB 30m trend is bullish', s);
    expect(r.status).toBe('met');
  });

  it('ORB 30m trend bearish — met (price below midpoint)', () => {
    const s = makeSnapshot({ price: 199.5, orbHigh: 202, orbLow: 199 }); // mid 200.5
    const r = evalCondition('ORB 30m trend is bearish', s);
    expect(r.status).toBe('met');
  });

  it('ORB null → unknown', () => {
    const s = makeSnapshot({ orbHigh: null, orbLow: null });
    const r = evalCondition('ORB 30m trend is bullish', s);
    expect(r.status).toBe('unknown');
  });
});

// ── Time-based ────────────────────────────────────────────────────────────

describe('time-based conditions', () => {
  it('at least 30 min after open — met (45 min)', () => {
    const r = evalCondition('At least 30 min after market open', makeSnapshot());
    expect(r.status).toBe('met');
  });

  it('at least 30 min after open — unmet (15 min)', () => {
    const s = makeSnapshot({ minutesSinceOpen: 15 });
    const r = evalCondition('At least 30 min after market open', s);
    expect(r.status).toBe('unmet');
  });

  it('minutes since open null → unknown', () => {
    const s = makeSnapshot({ minutesSinceOpen: null });
    const r = evalCondition('At least 30 min after market open', s);
    expect(r.status).toBe('unknown');
  });
});

// ── Bar range conditions ──────────────────────────────────────────────────

describe('bar range conditions', () => {
  it('close in upper half — met', () => {
    const bar: Bar = { time: '10:00:00', open: 200, high: 202, low: 198, close: 201, volume: 1000 };
    const s = makeSnapshot({ lastBar: bar }); // mid 200, close 201 > 200
    const r = evalCondition('Close in upper half of the bar\'s range', s);
    expect(r.status).toBe('met');
  });

  it('close in lower half — met', () => {
    const bar: Bar = { time: '10:00:00', open: 200, high: 202, low: 198, close: 199, volume: 1000 };
    const s = makeSnapshot({ lastBar: bar }); // mid 200, close 199 < 200
    const r = evalCondition('Close in lower half of the bar\'s range', s);
    expect(r.status).toBe('met');
  });

  it('no bar → unknown', () => {
    const s = makeSnapshot({ lastBar: null });
    const r = evalCondition('Close in upper half of the bar\'s range', s);
    expect(r.status).toBe('unknown');
  });
});

// ── Support / resistance ──────────────────────────────────────────────────

describe('support / resistance proximity', () => {
  it('at support — met (price near prev low)', () => {
    const s = makeSnapshot({ price: 196.5, prevLow: 196 }); // 0.25% away
    const r = evalCondition('Price at or near support level (prev day low, VWAP, order block)', s);
    expect(r.status).toBe('met');
  });

  it('at support — unmet (price far from prev low)', () => {
    const s = makeSnapshot({ price: 201, prevLow: 196 }); // 2.5% away
    const r = evalCondition('Price at or near support level (prev day low)', s);
    expect(r.status).toBe('unmet');
  });

  it('at resistance — met', () => {
    const s = makeSnapshot({ price: 202.5, prevHigh: 203 }); // 0.25%
    const r = evalCondition('Price at or near resistance (prev day high, upper BB)', s);
    expect(r.status).toBe('met');
  });

  it('no prev levels → unknown', () => {
    const s = makeSnapshot({ prevLow: null });
    const r = evalCondition('Price at or near support level', s);
    expect(r.status).toBe('unknown');
  });
});

// ── Subjective / unrecognized ─────────────────────────────────────────────

describe('subjective and unrecognized conditions', () => {
  it('higher timeframe → unknown', () => {
    const r = evalCondition('Higher timeframe supports the direction', makeSnapshot());
    expect(r.status).toBe('unknown');
    expect((r as { reason: string }).reason).toBe('subjective');
  });

  it('strat pattern → unknown', () => {
    const r = evalCondition('Current bar is Type 3 (higher high AND lower low)', makeSnapshot());
    expect(r.status).toBe('unknown');
    expect((r as { reason: string }).reason).toBe('strat pattern');
  });

  it('completely unrecognized → unknown', () => {
    const r = evalCondition('Jupiter is in retrograde', makeSnapshot());
    expect(r.status).toBe('unknown');
    expect((r as { reason: string }).reason).toBe('unrecognized');
  });
});

// ── evalConditions batch ──────────────────────────────────────────────────

describe('evalConditions (batch)', () => {
  it('evaluates multiple conditions at once', () => {
    const conditions = [
      'Price above VWAP',
      'RSI between 40-65',
      'Higher timeframe supports the direction',
    ];
    const results = evalConditions(conditions, makeSnapshot());
    expect(results).toHaveLength(3);
    expect(results[0].status).toBe('met');
    expect(results[1].status).toBe('met');
    expect(results[2].status).toBe('unknown');
  });
});

// ── computeORB ────────────────────────────────────────────────────────────

describe('computeORB', () => {
  it('computes high/low from first 30 min bars', () => {
    const bars: Bar[] = [
      { time: '2026-04-10 09:30:00', open: 200, high: 202, low: 199, close: 201, volume: 1000 },
      { time: '2026-04-10 09:45:00', open: 201, high: 204, low: 200, close: 203, volume: 1000 },
      { time: '2026-04-10 09:59:00', open: 203, high: 203, low: 198, close: 199, volume: 1000 },
      { time: '2026-04-10 10:00:00', open: 199, high: 210, low: 190, close: 205, volume: 1000 }, // outside ORB
    ];
    const orb = computeORB(bars);
    expect(orb.high).toBe(204);
    expect(orb.low).toBe(198);
  });

  it('returns null for empty bars', () => {
    expect(computeORB([])).toEqual({ high: null, low: null });
  });

  it('returns null when no bars in 9:30-10:00 window', () => {
    const bars: Bar[] = [
      { time: '2026-04-10 10:15:00', open: 200, high: 202, low: 199, close: 201, volume: 1000 },
    ];
    expect(computeORB(bars)).toEqual({ high: null, low: null });
  });
});

// ── minutesSinceOpen ──────────────────────────────────────────────────────

describe('minutesSinceOpen', () => {
  it('calculates correctly at 10:15', () => {
    const bar: Bar = { time: '2026-04-10 10:15:00', open: 200, high: 201, low: 199, close: 200.5, volume: 1000 };
    expect(minutesSinceOpen(bar)).toBe(45);
  });

  it('returns 0 at 09:30', () => {
    const bar: Bar = { time: '2026-04-10 09:30:00', open: 200, high: 201, low: 199, close: 200.5, volume: 1000 };
    expect(minutesSinceOpen(bar)).toBe(0);
  });

  it('returns null for pre-market bar', () => {
    const bar: Bar = { time: '2026-04-10 09:15:00', open: 200, high: 201, low: 199, close: 200.5, volume: 1000 };
    expect(minutesSinceOpen(bar)).toBeNull();
  });

  it('returns null for null bar', () => {
    expect(minutesSinceOpen(null)).toBeNull();
  });
});
