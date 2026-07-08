import { afterEach, describe, expect, it, vi } from 'vitest';
import { todayET, toETDateString } from './dates';

afterEach(() => vi.useRealTimers());

describe('todayET', () => {
  it('is still "today" in ET when UTC has rolled past midnight', () => {
    // 2026-07-08T02:30:00Z == 2026-07-07 22:30 ET
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-08T02:30:00Z'));
    expect(todayET()).toBe('2026-07-07');
  });
  it('matches UTC date during the overlapping hours', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-07T15:00:00Z'));
    expect(todayET()).toBe('2026-07-07');
  });
});

describe('toETDateString', () => {
  it('formats an arbitrary Date in ET', () => {
    expect(toETDateString(new Date('2026-01-01T03:00:00Z'))).toBe('2025-12-31');
  });
});
