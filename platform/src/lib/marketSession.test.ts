import { describe, it, expect } from 'vitest';
import { sessionLabel, sessionColor, sessionPillClasses } from './marketSession';

describe('sessionLabel', () => {
  it('regular → Market Open', () => expect(sessionLabel('regular')).toBe('Market Open'));
  it('pre-market → Pre-Market', () => expect(sessionLabel('pre-market')).toBe('Pre-Market'));
  it('after-hours → After Hours', () => expect(sessionLabel('after-hours')).toBe('After Hours'));
  it('closed → Market Closed', () => expect(sessionLabel('closed')).toBe('Market Closed'));
  it('undefined → Market Closed', () => expect(sessionLabel(undefined)).toBe('Market Closed'));
  it('unknown string passes through', () => expect(sessionLabel('holiday')).toBe('holiday'));
});

describe('sessionColor', () => {
  it('regular → green', () => expect(sessionColor('regular')).toBe('bg-green-500'));
  it('pre-market → amber', () => expect(sessionColor('pre-market')).toBe('bg-amber-500'));
  it('after-hours → amber', () => expect(sessionColor('after-hours')).toBe('bg-amber-500'));
  it('closed → red', () => expect(sessionColor('closed')).toBe('bg-red-500'));
  it('undefined → red', () => expect(sessionColor(undefined)).toBe('bg-red-500'));
});

describe('sessionPillClasses', () => {
  it('regular returns green pill + dot', () => {
    const { pill, dot } = sessionPillClasses('regular');
    expect(pill).toContain('green');
    expect(dot).toContain('green');
  });

  it('pre-market returns amber pill + dot', () => {
    const { pill, dot } = sessionPillClasses('pre-market');
    expect(pill).toContain('amber');
    expect(dot).toContain('amber');
  });

  it('after-hours returns amber', () => {
    const { pill, dot } = sessionPillClasses('after-hours');
    expect(pill).toContain('amber');
    expect(dot).toContain('amber');
  });

  it('closed returns red', () => {
    const { pill, dot } = sessionPillClasses('closed');
    expect(pill).toContain('red');
    expect(dot).toContain('red');
  });

  it('undefined returns red', () => {
    const { pill, dot } = sessionPillClasses(undefined);
    expect(pill).toContain('red');
    expect(dot).toContain('red');
  });
});
