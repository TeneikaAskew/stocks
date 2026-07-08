import { afterEach, describe, expect, it, vi } from 'vitest';
import { relativeDayLabel } from './DashboardPage';

afterEach(() => vi.useRealTimers());

describe('relativeDayLabel', () => {
  it('labels today at day granularity', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-08T15:00:00Z'));
    expect(relativeDayLabel('2026-07-08')).toBe('today');
  });

  it('labels yesterday at day granularity', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-08T15:00:00Z'));
    expect(relativeDayLabel('2026-07-07')).toBe('yesterday');
  });

  it('falls back to "Mon D" for older dates without fabricating hours', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-08T15:00:00Z'));
    expect(relativeDayLabel('2026-07-01')).toBe('Jul 1');
  });

  it('passes through an unparseable date unchanged', () => {
    expect(relativeDayLabel('')).toBe('');
  });

  it('is ET-correct at 22:30 ET when UTC has rolled to the next day', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-08T02:30:00Z')); // 2026-07-07 22:30 ET
    expect(relativeDayLabel('2026-07-07')).toBe('today');
    expect(relativeDayLabel('2026-07-06')).toBe('yesterday');
  });
});
