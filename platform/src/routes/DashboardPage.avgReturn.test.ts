import { describe, expect, it } from 'vitest';
import { topSetupAvgReturn } from './DashboardPage';

describe('topSetupAvgReturn', () => {
  it('renders API percent units without re-multiplying (0.29 -> +0.29%)', () => {
    expect(topSetupAvgReturn(0.29)).toBe('+0.29%');
  });
  it('renders missing as em dash', () => {
    expect(topSetupAvgReturn(null)).toBe('—');
    expect(topSetupAvgReturn(undefined)).toBe('—');
  });
});
