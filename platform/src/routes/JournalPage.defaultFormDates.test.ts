import { afterEach, describe, expect, it, vi } from 'vitest';
import { defaultFormDates } from './JournalPage';
import { todayET } from '@/lib/dates';

// #702 follow-ups Task 4 item 1: emptyForm() used `new Date().toISOString()`
// (UTC) for its default entry/exit dates — wrong for 4-5 hours every evening
// ET (see lib/dates.ts's header comment). defaultFormDates() must mirror
// todayET() exactly, at any wall-clock time.

afterEach(() => vi.useRealTimers());

describe('defaultFormDates', () => {
  it('mirrors todayET() when UTC has rolled past midnight but it is still "today" in ET', () => {
    // 2026-07-08T02:30:00Z == 2026-07-07 22:30 ET
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-08T02:30:00Z'));
    const d = defaultFormDates();
    expect(d.entryDate).toBe(todayET());
    expect(d.exitDate).toBe(todayET());
    expect(d.entryDate).toBe('2026-07-07');
  });

  it('matches UTC date during the overlapping hours', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-07T15:00:00Z'));
    const d = defaultFormDates();
    expect(d.entryDate).toBe('2026-07-07');
    expect(d.exitDate).toBe('2026-07-07');
  });

  it('entryDate and exitDate are always equal (both default to today)', () => {
    const d = defaultFormDates();
    expect(d.entryDate).toBe(d.exitDate);
  });
});
