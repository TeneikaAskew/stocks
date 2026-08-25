import { describe, expect, it } from 'vitest';
import { riskReward, stopDisplayText } from './risk';

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

// task-alerts-enrichment (2026-07-12) — USER REQUIREMENT (verbatim): the
// Stop column renders each row's OWN time_stop_minutes, NEVER a fixed
// label; production data has both 20 and 25 in the first six rows of one
// ticker alone. Mutation-proof: two rows with DIFFERENT time-stop minutes
// must render DIFFERENT text, never collapse to a hardcoded value.
describe('stopDisplayText', () => {
  it('renders a real stop price when present, ignoring time_stop_minutes entirely', () => {
    expect(stopDisplayText(219, 20)).toBe('$219.00');
  });

  it('renders "<N>m time-stop" using the row\'s OWN minutes when there is no stop price', () => {
    expect(stopDisplayText(null, 20)).toBe('20m time-stop');
    expect(stopDisplayText(null, 25)).toBe('25m time-stop');
  });

  it('two different time-stop values render different text (mutation-proof — never hardcoded)', () => {
    const a = stopDisplayText(null, 20);
    const b = stopDisplayText(null, 25);
    expect(a).not.toBe(b);
    expect(a).toBe('20m time-stop');
    expect(b).toBe('25m time-stop');
  });

  it('renders an em dash when neither a stop price nor a time-stop is present (Rule 3.7)', () => {
    expect(stopDisplayText(null, null)).toBe('—');
    expect(stopDisplayText(undefined, undefined)).toBe('—');
  });
});
