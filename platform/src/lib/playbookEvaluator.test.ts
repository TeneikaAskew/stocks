import { describe, it, expect } from 'vitest';
import { computeORB, minutesSinceOpen } from './playbookEvaluator';
import type { Bar } from './indicators';

// The regex-based condition evaluator (evalCondition / evalConditions) was
// moved to platform/api/routers/playbook.py — see the header comment in
// playbookEvaluator.ts. Only the pure client-side helpers remain here.

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
