import { describe, expect, it } from 'vitest';
import { defaultPriceTick } from './PriceAreaChart';

describe('defaultPriceTick', () => {
  it('keeps whole dollars for wide price ranges', () => {
    expect(defaultPriceTick(298.4, 8)).toBe('$298');
  });
  it('adds decimals for sub-dollar ranges so ticks never repeat', () => {
    expect(defaultPriceTick(1.012, 0.08)).toBe('$1.01');
    expect(defaultPriceTick(0.981, 0.08)).toBe('$0.98');
  });
});
