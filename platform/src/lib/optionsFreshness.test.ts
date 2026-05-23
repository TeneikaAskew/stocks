import { describe, it, expect } from 'vitest';
import {
  freshnessFromSnapshot,
  freshnessBadgeClasses,
  tradingDaysBetween,
} from './optionsFreshness';

// Helper: build an ISO timestamp from a YYYY-MM-DD plus HH:MM in ET.
// All test fixtures are in May (EDT, UTC-4); rolling Date math handles the
// hour-overflow case (e.g. 21:00 ET = 01:00 UTC next day).
function et(date: string, hhmm: string): string {
  const [h, m] = hhmm.split(':').map(Number);
  const [yyyy, mm, dd] = date.split('-').map(Number);
  // 21:00 EDT = 01:00 UTC next day. Date constructor handles the rollover.
  const utc = new Date(Date.UTC(yyyy, mm - 1, dd, h + 4, m, 0));
  return utc.toISOString();
}

describe('tradingDaysBetween', () => {
  it('returns 0 for same-day timestamps', () => {
    const d = new Date('2026-05-13T12:00:00Z');
    expect(tradingDaysBetween(d, d)).toBe(0);
  });

  it('returns 0 when `to` is before `from`', () => {
    const earlier = new Date('2026-05-13T12:00:00Z');
    const later = new Date('2026-05-14T12:00:00Z');
    expect(tradingDaysBetween(later, earlier)).toBe(0);
  });

  it('counts one trading day for Mon → Tue', () => {
    // 2026-05-11 is Monday, 2026-05-12 is Tuesday
    const mon = new Date('2026-05-11T16:00:00Z');
    const tue = new Date('2026-05-12T16:00:00Z');
    expect(tradingDaysBetween(mon, tue)).toBe(1);
  });

  it('skips the weekend: Fri close → Mon morning = 1 trading day', () => {
    // 2026-05-15 is Friday, 2026-05-18 is Monday
    const fri = new Date('2026-05-15T20:00:00Z');
    const mon = new Date('2026-05-18T13:30:00Z');
    expect(tradingDaysBetween(fri, mon)).toBe(1);
  });

  it('skips the weekend: Fri close → Tue morning = 2 trading days', () => {
    const fri = new Date('2026-05-15T20:00:00Z');
    const tue = new Date('2026-05-19T13:30:00Z');
    expect(tradingDaysBetween(fri, tue)).toBe(2);
  });

  it('counts full week: Mon → next Mon = 5 trading days', () => {
    const mon1 = new Date('2026-05-11T16:00:00Z');
    const mon2 = new Date('2026-05-18T16:00:00Z');
    expect(tradingDaysBetween(mon1, mon2)).toBe(5);
  });
});

describe('freshnessFromSnapshot — REALTIME', () => {
  it('renders green Live badge with HH:MM ET', () => {
    const badge = freshnessFromSnapshot(
      'REALTIME',
      et('2026-05-13', '14:32'),
      new Date(et('2026-05-13', '14:33')),
    );
    expect(badge.tone).toBe('live');
    expect(badge.label).toBe('Live · 14:32 ET');
    expect(badge.title).toContain('Realtime');
  });

  it('renders Live without time when snapshot_ts is missing', () => {
    const badge = freshnessFromSnapshot('REALTIME', null);
    expect(badge.tone).toBe('live');
    expect(badge.label).toBe('Live');
  });

  it('renders Live even if snapshot_ts is days old (REALTIME wins)', () => {
    // If a row is tagged REALTIME we trust the tag — staleness only
    // applies to EOD-tagged rows.
    const badge = freshnessFromSnapshot(
      'REALTIME',
      et('2026-05-08', '15:00'),
      new Date(et('2026-05-13', '10:00')),
    );
    expect(badge.tone).toBe('live');
  });
});

describe('freshnessFromSnapshot — EOD', () => {
  it('renders amber EOD badge for fresh (≤2 trading days) data', () => {
    // 2026-05-11 Mon EOD viewed on 2026-05-12 Tue → 1 trading day elapsed
    const badge = freshnessFromSnapshot(
      'EOD',
      et('2026-05-11', '21:00'),
      new Date(et('2026-05-12', '10:00')),
    );
    expect(badge.tone).toBe('eod');
    expect(badge.label).toMatch(/^EOD · Mon 21:00 ET$/);
  });

  it('renders amber EOD for Fri viewed on Mon (1 trading day, skips weekend)', () => {
    const badge = freshnessFromSnapshot(
      'EOD',
      et('2026-05-15', '21:00'),
      new Date(et('2026-05-18', '08:00')),
    );
    expect(badge.tone).toBe('eod');
    expect(badge.label).toMatch(/^EOD · Fri 21:00 ET$/);
  });

  it('renders amber EOD at exactly 2 trading days (the boundary stays fresh)', () => {
    // Mon EOD viewed Wed morning → 2 trading days elapsed → still EOD
    const badge = freshnessFromSnapshot(
      'EOD',
      et('2026-05-11', '21:00'),
      new Date(et('2026-05-13', '10:00')),
    );
    expect(badge.tone).toBe('eod');
  });

  it('flips to red Stale when EOD data is >2 trading days old', () => {
    // Mon EOD viewed Thu → 3 trading days elapsed → stale
    const badge = freshnessFromSnapshot(
      'EOD',
      et('2026-05-11', '21:00'),
      new Date(et('2026-05-14', '10:00')),
    );
    expect(badge.tone).toBe('stale');
    expect(badge.label).toBe('Stale · 3d old');
  });
});

describe('freshnessFromSnapshot — unknown / null', () => {
  it('renders red Stale · unknown when snapshot_ts is null', () => {
    const badge = freshnessFromSnapshot('EOD', null);
    expect(badge.tone).toBe('stale');
    expect(badge.label).toBe('Stale · unknown');
  });

  it('renders red Stale · unknown when snapshot_ts is an invalid date', () => {
    const badge = freshnessFromSnapshot('EOD', 'not-a-date');
    expect(badge.tone).toBe('stale');
    expect(badge.label).toBe('Stale · unknown');
  });

  it('treats unknown market_session strings as not-EOD (falls through to stale)', () => {
    // Legacy values like 'OPEN_VOLATILE' from the old session-classification
    // system aren't REALTIME or EOD — bucket them as stale so the user gets
    // a visible signal that the data isn't actively maintained.
    const badge = freshnessFromSnapshot(
      'OPEN_VOLATILE',
      et('2026-05-11', '14:00'),
      new Date(et('2026-05-12', '10:00')),
    );
    expect(badge.tone).toBe('stale');
  });

  it('treats undefined market_session as stale', () => {
    const badge = freshnessFromSnapshot(
      undefined,
      et('2026-05-11', '14:00'),
      new Date(et('2026-05-12', '10:00')),
    );
    expect(badge.tone).toBe('stale');
  });
});

describe('freshnessBadgeClasses', () => {
  it('returns emerald for live', () => {
    expect(freshnessBadgeClasses('live')).toContain('emerald');
  });
  it('returns amber for eod', () => {
    expect(freshnessBadgeClasses('eod')).toContain('amber');
  });
  it('returns rose for stale', () => {
    expect(freshnessBadgeClasses('stale')).toContain('rose');
  });
});
