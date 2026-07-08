import { describe, expect, it } from 'vitest';
import { sectorBarWidthPct } from './DashboardPage';

describe('sectorBarWidthPct', () => {
  it('scales a positive change relative to the period max', () => {
    expect(sectorBarWidthPct(2, 4)).toBe(50);
  });
  it('scales a negative change by magnitude (sign handled by CSS, not width)', () => {
    expect(sectorBarWidthPct(-4, 4)).toBe(100);
  });
  it('returns 0 (never NaN) when maxAbs is 0', () => {
    expect(sectorBarWidthPct(3, 0)).toBe(0);
    expect(Number.isNaN(sectorBarWidthPct(3, 0))).toBe(false);
  });
});
