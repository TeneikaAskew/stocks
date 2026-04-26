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
  it('fires CALL when all 5 conditions are met (PUT should be silent)', () => {
    const { call, put, firing } = computeStrategySignals(
      upRunBars,
      ind({ rsi: 35, stochK: 50, ema9: 99 }),
      99, // VWAP — last close (103) > VWAP
    );
    expect(call.metCount).toBe(5);
    expect(call.fires).toBe(true);
    // Directional conditions are exclusive — only StochRSI 50 (∈ 20..80) is
    // true on both sides, so PUT can be at most 1/5 here.
    expect(put.metCount).toBe(1);
    expect(put.fires).toBe(false);
    expect(firing).toBe('CALL');
  });

  it('fires CALL with exactly 3/5 met (minimum to fire)', () => {
    // 3 ups, RSI in band, price > EMA9 → 3 met; StochRSI 90 + price < VWAP → 2 unmet
    const { call, put, firing } = computeStrategySignals(
      upRunBars,
      ind({ rsi: 35, stochK: 90, ema9: 99 }),
      999, // VWAP way above price → c_p_vwap unmet
    );
    expect(call.metCount).toBe(3);
    expect(call.fires).toBe(true);
    // PUT: 0 downs, RSI not in band, StochRSI 90 > 20 ✓, price 103 < VWAP 999 ✓,
    // price 103 > EMA9 99 (PUT wants <) ✗ → 2/5
    expect(put.metCount).toBe(2);
    expect(put.fires).toBe(false);
    expect(firing).toBe('CALL');
  });

  it('CALL does not fire when conditions favor PUT', () => {
    // Sideways bars (no consecutive run either way), RSI=80, stoch=90,
    // EMA9 and VWAP above price. CALL gets 0/5; PUT gets 3/5
    // (stoch>20, price<VWAP, price<EMA9) and fires.
    const flat: Bar[] = [bar(100), bar(100, 100), bar(100, 100), bar(100, 100)];
    const { call, put, firing } = computeStrategySignals(
      flat,
      ind({ rsi: 80, stochK: 90, ema9: 999 }),
      999,
    );
    expect(call.metCount).toBe(0);
    expect(call.fires).toBe(false);
    expect(put.metCount).toBe(3);
    expect(put.fires).toBe(true);
    expect(firing).toBe('PUT');
  });
});

describe('computeStrategySignals — PUT voter', () => {
  it('fires PUT when all 5 conditions are met (CALL should be silent)', () => {
    const { call, put, firing } = computeStrategySignals(
      downRunBars,
      ind({ rsi: 60, stochK: 50, ema9: 100 }),
      100, // VWAP above last close (97)
    );
    expect(put.metCount).toBe(5);
    expect(put.fires).toBe(true);
    // Mirror of the CALL-side test: only StochRSI 50 overlaps (50 < 80), so
    // CALL is capped at 1/5 here.
    expect(call.metCount).toBe(1);
    expect(call.fires).toBe(false);
    expect(firing).toBe('PUT');
  });
});

describe('computeStrategySignals — tie / no-fire scenarios', () => {
  it('does not fire when neither side reaches the 3/5 threshold', () => {
    // A 3-3 tie is mathematically impossible with this voter — the
    // directional conditions (run, RSI band, price-vs-VWAP, price-vs-EMA9)
    // are mutually exclusive between CALL and PUT. Only StochRSI can be
    // true on both sides simultaneously. So the tie-break case to test is
    // "neither side reaches 3", not "both at 3".
    //
    // Inputs: sideways bars (no run), RSI 60 (PUT band), price = VWAP =
    // EMA9 (strict inequalities → both miss).
    //   CALL: 0 ups + RSI not in 25–50 + stoch ✓ + 0 + 0 = 1
    //   PUT:  0 downs + RSI ∈ 50–75 ✓ + stoch ✓ + 0 + 0 = 2
    const flat: Bar[] = [bar(100), bar(100, 100), bar(100, 100), bar(100, 100)];
    const { call, put, firing } = computeStrategySignals(flat, ind({ rsi: 60 }), 100);
    expect(call.metCount).toBe(1);
    expect(put.metCount).toBe(2);
    expect(call.fires).toBe(false);
    expect(put.fires).toBe(false);
    expect(firing).toBeNull();
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

  it('does not fire with too few bars to evaluate a run', () => {
    // Single bar — the consecutive-direction count needs at least 4 bars
    // (3 transitions). Other conditions still evaluate against the
    // default indicator block (rsi=50, vwap=100, ema9=100, stochK=50) but
    // the strict band/price comparisons all miss at exactly 100/50/100.
    //
    //   CALL: 0 ups + RSI 50 ∉ (25,50) + stoch 50 < 80 ✓ + 100 > 100 ✗ + 100 > 100 ✗ = 1
    //   PUT:  0 downs + RSI 50 ∉ (50,75) + stoch 50 > 20 ✓ + 100 < 100 ✗ + 100 < 100 ✗ = 1
    const { call, put, firing } = computeStrategySignals([bar(100)], ind(), 100);
    expect(call.metCount).toBe(1);
    expect(put.metCount).toBe(1);
    expect(call.fires).toBe(false);
    expect(put.fires).toBe(false);
    expect(firing).toBeNull();
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
