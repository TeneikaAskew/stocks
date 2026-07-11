import { describe, expect, it } from 'vitest';
import { riskReward } from './risk';

describe('riskReward', () => {
  it('computes an exact 2:1 ratio', () => {
    // entry 100, tp1 110 (+10), stop 95 (-5) -> 10/5 = 2.0
    expect(riskReward(100, 110, 95)).toBe(2.0);
  });

  it('is direction-agnostic (PUT-style: tp1 below entry, stop above)', () => {
    // entry 100, tp1 90 (-10), stop 105 (+5) -> 10/5 = 2.0
    expect(riskReward(100, 90, 105)).toBe(2.0);
  });

  it('returns null when entry is null', () => {
    expect(riskReward(null, 110, 95)).toBeNull();
  });

  it('returns null when tp1 is null', () => {
    expect(riskReward(100, null, 95)).toBeNull();
  });

  it('returns null when stop is null', () => {
    expect(riskReward(100, 110, null)).toBeNull();
  });

  it('returns null when stop === entry (zero risk distance)', () => {
    expect(riskReward(100, 110, 100)).toBeNull();
  });
});
