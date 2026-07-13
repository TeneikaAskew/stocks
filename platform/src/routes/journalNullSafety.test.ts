import { afterEach, describe, expect, it } from 'vitest';
import { tsToDisplay, tradesToCsv, exportableTrades } from './JournalPage';

describe('tsToDisplay', () => {
  // Bug (2026-07-12 user acceptance): a chart-marked IWM trade at naive-ET
  // 10:05 displayed as 14:05 in the journal TABLE (this helper) while the
  // chart marker and TradeRailCard both correctly showed 10:05. Root cause:
  // this helper round-tripped through `new Date(...)`, which parses an
  // offset-less date-time string as HOST-LOCAL time (ECMA-262) — the exact
  // shape `_rows_to_trades` (platform/api/routers/journal.py) returns for
  // every journal_entries row (`entry_ts AT TIME ZONE 'UTC'` strips the tz
  // label, and pandas' `str()` on the resulting naive Timestamp yields
  // "YYYY-MM-DD HH:MM:SS", no offset). On a host running in America/New_York
  // during EDT (UTC-4), `new Date('2026-07-08T10:05:00')` is parsed as
  // 10:05 LOCAL == 14:05 UTC, and `.toISOString()` then renders "14:05".
  //
  // The correct pattern (already used by `isoNaiveToEpoch` in
  // useJournalChartTrades.ts, which is why the chart/rail card were right)
  // is pure regex digit-extraction — never a `new Date()` round-trip — so
  // host timezone cannot affect the result. These tests pin both string
  // shapes the API actually returns (space-separated no-offset from
  // `_rows_to_trades`, and offset-bearing) and set TZ to a non-UTC zone to
  // prove the fix is host-tz-independent.
  const originalTz = process.env.TZ;

  afterEach(() => {
    process.env.TZ = originalTz;
  });

  it('returns em-dash placeholders for a null timestamp (active trade)', () => {
    expect(tsToDisplay(null)).toEqual({ date: '—', time: '—' });
  });

  it('still parses a normal ISO timestamp', () => {
    // Use a 'Z'-suffixed (UTC) timestamp so the assertion is stable
    // regardless of the machine's local timezone.
    expect(tsToDisplay('2026-07-02T13:35:00Z')).toEqual({ date: '2026-07-02', time: '13:35' });
  });

  it('reads a space-separated, offset-less Cloud SQL naive-ET string (_rows_to_trades shape) correctly under a non-UTC host TZ', () => {
    process.env.TZ = 'America/New_York';
    expect(tsToDisplay('2026-07-08 10:05:00')).toEqual({ date: '2026-07-08', time: '10:05' });
  });

  it('reads a T-separated, offset-less naive-ET string (local-fallback create_trade shape) correctly under a non-UTC host TZ', () => {
    process.env.TZ = 'America/New_York';
    expect(tsToDisplay('2026-07-08T10:05:00')).toEqual({ date: '2026-07-08', time: '10:05' });
  });

  it('reads a space-separated, offset-bearing naive-ET string (+00:00) correctly under a non-UTC host TZ', () => {
    process.env.TZ = 'America/New_York';
    expect(tsToDisplay('2026-07-08 10:05:00+00:00')).toEqual({ date: '2026-07-08', time: '10:05' });
  });

  it('reads a T-separated, offset-bearing naive-ET string (+00:00) correctly under a non-UTC host TZ', () => {
    process.env.TZ = 'America/New_York';
    expect(tsToDisplay('2026-07-08T10:05:00+00:00')).toEqual({ date: '2026-07-08', time: '10:05' });
  });

  it('is stable across host TZ for the same offset-less naive-ET string', () => {
    process.env.TZ = 'Pacific/Auckland'; // UTC+12/+13 — opposite hemisphere from ET
    expect(tsToDisplay('2026-07-08 10:05:00')).toEqual({ date: '2026-07-08', time: '10:05' });
  });
});

describe('tradesToCsv', () => {
  // 'Z'-suffixed (UTC) timestamps so assertions are stable regardless of
  // the machine's local timezone.
  const closedRow = {
    id: '1',
    ticker: 'IWM',
    direction: 'CALL' as const,
    entry_ts: '2026-07-02T09:31:00Z',
    exit_ts: '2026-07-02T09:45:00Z',
    entry_price: 220.5,
    exit_price: 224.5,
    return_pct: 1.81,
    notes: '',
  };

  const activeRow = {
    id: '2',
    ticker: 'IWM',
    direction: 'PUT' as const,
    entry_ts: '2026-07-02T09:35:00Z',
    exit_ts: null,
    entry_price: 218.0,
    exit_price: null,
    return_pct: null,
    notes: '',
  };

  it('serializes a closed trade with populated exit cell', () => {
    const csv = tradesToCsv([closedRow]);
    const dataLine = csv.split('\n')[1];
    expect(dataLine).toBe('1,2026-07-02 09:31:00,CALL,2026-07-02 09:45:00,,');
  });

  it('serializes an active (null-exit) trade with an empty exit cell, not "null" or a throw', () => {
    expect(() => tradesToCsv([activeRow])).not.toThrow();
    const csv = tradesToCsv([activeRow]);
    const dataLine = csv.split('\n')[1];
    expect(dataLine).toBe('1,2026-07-02 09:35:00,PUT,,,');
    expect(dataLine).not.toContain('null');
    expect(dataLine).not.toContain('—');
  });

  it('handles a mix of closed and active rows without throwing', () => {
    expect(() => tradesToCsv([closedRow, activeRow])).not.toThrow();
  });
});

// ── #702 follow-ups Task 1, Item 1: pipeline export skips active trades ────
// `JournalTradeExportItem` on the server requires exit_date/exit_time/
// exit_price, so an active (no-exit) trade in the POSTed list 422s (see the
// pinned server-contract test in tests/test_journal_phase2.py). The fix is
// client-side: exportPipeline filters active rows out via this pure helper
// before building the export payload.
describe('exportableTrades', () => {
  const closedRow = {
    id: '1',
    ticker: 'IWM',
    direction: 'CALL' as const,
    entry_ts: '2026-07-02T09:31:00Z',
    exit_ts: '2026-07-02T09:45:00Z',
    entry_price: 220.5,
    exit_price: 224.5,
    return_pct: 1.81,
    notes: '',
  };

  const activeRow = {
    id: '2',
    ticker: 'IWM',
    direction: 'PUT' as const,
    entry_ts: '2026-07-02T09:35:00Z',
    exit_ts: null,
    entry_price: 218.0,
    exit_price: null,
    return_pct: null,
    notes: '',
    status: 'active',
  };

  it('keeps closed trades and filters out active (null-exit) trades', () => {
    expect(exportableTrades([closedRow, activeRow])).toEqual([closedRow]);
  });

  it('filters out a trade whose status is "active" even if it somehow carries an exit_ts', () => {
    const staleActive = { ...closedRow, id: '3', status: 'active' };
    expect(exportableTrades([staleActive])).toEqual([]);
  });

  it('returns an empty array when every trade is active', () => {
    expect(exportableTrades([activeRow])).toEqual([]);
  });

  it('returns all trades unchanged when every trade is closed', () => {
    const secondClosed = { ...closedRow, id: '4' };
    expect(exportableTrades([closedRow, secondClosed])).toEqual([closedRow, secondClosed]);
  });
});
