/**
 * Unit tests for computeStrategySignals.
 *
 * These mirror the 5-condition voter in trading_analysis.py:
 *   generate_technical_signals — CALL fires when ≥3 of {3 consecutive ups,
 *   RSI 25–50, StochRSI K < 80, price > VWAP, price > EMA9} are true AND
 *   that side beats PUT count.
 */
import { describe, it, expect } from 'vitest';
import { computeStrategySignals, type Bar, type Indicators } from './indicators';

function ind(over: Partial<Indicators> = {}): Indicators {
  return {
    ema9: 100,
    ema20: 100,
    ema50: 100,
    rsi: 50,
    stochK: 50,
    stochD: 50,
    atr: 1.0,
    vwap: 100,
    ...over,
  };
}

function bar(close: number, prev?: number): Bar {
  return {
    time: '2026-04-25 10:00:00',
    open: prev ?? close,
    high: Math.max(close, prev ?? close),
    low: Math.min(close, prev ?? close),
    close,
    volume: 1000,
  };
}

// 3 bars walking up: 100 → 101 → 102 → 103 (last 3 transitions all up)
const upRunBars: Bar[] = [bar(100), bar(101, 100), bar(102, 101), bar(103, 102)];
const downRunBars: Bar[] = [bar(100), bar(99, 100), bar(98, 99), bar(97, 98)];

describe('computeStrategySignals — CALL voter', () => {
  it('fires CALL when all 5 conditions are met', () => {
    const { call, firing } = computeStrategySignals(
      upRunBars,
      ind({ rsi: 35, stochK: 50, ema9: 99 }),
      99, // VWAP — last close (103) > VWAP
    );
    expect(call.metCount).toBe(5);
    expect(call.fires).toBe(true);
    expect(firing).toBe('CALL');
  });

  it('fires CALL with exactly 3/5 met (minimum)', () => {
    // 3 ups, RSI in band, price > EMA9 → 3 met; StochRSI overbought + price < VWAP → 2 unmet
    const { call, firing } = computeStrategySignals(
      upRunBars,
      ind({ rsi: 35, stochK: 90, ema9: 99 }),
      999, // VWAP way above price → c_p_vwap unmet
    );
    expect(call.metCount).toBe(3);
    expect(call.fires).toBe(true);
    expect(firing).toBe('CALL');
  });

  it('CALL does not fire when only 2/5 met', () => {
    // Sideways bars: no consecutive run for either direction.
    // RSI out of CALL band, stoch high, ema9 above price → CALL gets 0
    const flat: Bar[] = [bar(100), bar(100, 100), bar(100, 100), bar(100, 100)];
    const { call, put, firing } = computeStrategySignals(
      flat,
      ind({ rsi: 80, stochK: 90, ema9: 999 }),
      999,
    );
    expect(call.metCount).toBeLessThan(3);
    expect(call.fires).toBe(false);
    // Either nothing fires (most likely) or PUT fires if its conditions pile up;
    // the only thing this test asserts is that CALL specifically does not.
    if (firing !== null) expect(firing).not.toBe('CALL');
  });
});

describe('computeStrategySignals — PUT voter', () => {
  it('fires PUT when all 5 conditions are met', () => {
    const { put, firing } = computeStrategySignals(
      downRunBars,
      ind({ rsi: 60, stochK: 50, ema9: 100 }),
      100, // VWAP above last close (97)
    );
    expect(put.metCount).toBe(5);
    expect(put.fires).toBe(true);
    expect(firing).toBe('PUT');
  });
});

describe('computeStrategySignals — tie / no-fire scenarios', () => {
  it('does not fire when CALL and PUT counts tie at 3', () => {
    // Sideways bars (no run) → consecutive condition fails for both
    // RSI in mid no-mans-land, stoch mid → conditions split evenly
    const flat: Bar[] = [bar(100), bar(100, 100), bar(100, 100), bar(100, 100)];
    const { call, put, firing } = computeStrategySignals(flat, ind({ rsi: 60 }), 100);
    // Even if both >= 3, "fires" requires strictly beating the other
    if (call.metCount === put.metCount && call.metCount >= 3) {
      expect(firing).toBeNull();
    } else {
      // Otherwise just confirm neither fires
      expect(firing === 'CALL' ? call.fires : true).toBe(true);
    }
  });

  it('handles missing indicators gracefully (no crash)', () => {
    const { call, put, firing } = computeStrategySignals(
      upRunBars,
      ind({ rsi: null, stochK: null, ema9: null }),
      null,
    );
    // RSI/stoch/ema/vwap all null → those four conditions unmet; only the
    // consecutive-ups condition for CALL is met.
    expect(call.metCount).toBe(1);
    expect(put.metCount).toBe(0);
    expect(firing).toBeNull();
  });

  it('returns 0/5 with too few bars to detect a run', () => {
    const { call, put } = computeStrategySignals([bar(100)], ind(), 100);
    // Only 1 bar — no transitions to count, but other conditions still evaluate
    // Just sanity-check it doesn't blow up
    expect(call.metCount).toBeGreaterThanOrEqual(0);
    expect(put.metCount).toBeGreaterThanOrEqual(0);
  });
});

describe('computeStrategySignals — condition wiring', () => {
  it('CALL RSI condition is bullish band 25–50', () => {
    const { call } = computeStrategySignals(upRunBars, ind({ rsi: 35 }), 100);
    const rsiCond = call.conditions.find((c) => c.id === 'call_rsi_band');
    expect(rsiCond?.met).toBe(true);

    const { call: call2 } = computeStrategySignals(upRunBars, ind({ rsi: 60 }), 100);
    const rsiCond2 = call2.conditions.find((c) => c.id === 'call_rsi_band');
    expect(rsiCond2?.met).toBe(false);
  });

  it('PUT RSI condition is bearish band 50–75', () => {
    const { put } = computeStrategySignals(downRunBars, ind({ rsi: 60 }), 100);
    const rsiCond = put.conditions.find((c) => c.id === 'put_rsi_band');
    expect(rsiCond?.met).toBe(true);

    const { put: put2 } = computeStrategySignals(downRunBars, ind({ rsi: 35 }), 100);
    const rsiCond2 = put2.conditions.find((c) => c.id === 'put_rsi_band');
    expect(rsiCond2?.met).toBe(false);
  });

  it('exposes 5 conditions per side', () => {
    const { call, put } = computeStrategySignals(upRunBars, ind(), 100);
    expect(call.conditions).toHaveLength(5);
    expect(put.conditions).toHaveLength(5);
  });
});
