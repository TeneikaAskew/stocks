import { describe, expect, it } from 'vitest';
import { fmtEquityTick, fmtRunDate } from './BacktesterSection';

describe('fmtEquityTick', () => {
  it('uses decimals on a normalized (~1.0) equity range so ticks never repeat', () => {
    // range 0.07 (e.g. 0.98..1.05): needs 3 decimals
    expect(fmtEquityTick(1.0123, 0.07)).toBe('$1.012');
    expect(fmtEquityTick(0.9871, 0.07)).toBe('$0.987');
  });
  it('uses whole dollars on account-scale ranges', () => {
    expect(fmtEquityTick(10500, 4000)).toBe('$10500');
  });
});

describe('fmtRunDate', () => {
  it('keeps the year so multi-year curves read chronologically', () => {
    expect(fmtRunDate('2023-04-21')).toBe('04/21/23');
  });
});
