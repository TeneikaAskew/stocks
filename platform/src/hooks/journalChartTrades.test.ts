import { describe, it, expect } from 'vitest';
import {
  epochToJournalDateTime,
  isoNaiveToEpoch,
  journalRowToTradeEntry,
  type JournalRow,
} from './useJournalChartTrades';

describe('epochToJournalDateTime', () => {
  it('renders the naive-ET wall clock without timezone conversion', () => {
    // 1751463300 is minute-aligned (mod 60 === 0). Computing
    // `new Date(1751463300 * 1000)`'s UTC getters (the naive-ET convention
    // main.py encodes chart epochs with) gives 2025-07-02 13:35 — the plan
    // brief's illustrative fixture said "2026-07-02" but the actual epoch
    // resolves to 2025; the wall-clock time (13:35) is what matters and is
    // pinned exactly here.
    expect(epochToJournalDateTime(1751463300)).toEqual({ date: '2025-07-02', time: '13:35' });
  });

  it('pads single-digit month/day/hour/minute', () => {
    // 2025-01-02T03:04:00Z
    const epoch = Date.UTC(2025, 0, 2, 3, 4, 0) / 1000;
    expect(epochToJournalDateTime(epoch)).toEqual({ date: '2025-01-02', time: '03:04' });
  });
});

describe('isoNaiveToEpoch', () => {
  const expected = Math.floor(Date.UTC(2026, 6, 2, 13, 35, 0) / 1000);

  it('parses the local-fallback format ("T", no offset)', () => {
    expect(isoNaiveToEpoch('2026-07-02T13:35:00')).toBe(expected);
  });

  it('parses the Cloud SQL format (space separator + offset)', () => {
    expect(isoNaiveToEpoch('2026-07-02 13:35:00+00:00')).toBe(expected);
  });

  it('ignores everything past the first 19 characters (offset/micros)', () => {
    expect(isoNaiveToEpoch('2026-07-02T13:35:00.123456+00:00')).toBe(expected);
  });

  it('returns NaN for an unparseable string', () => {
    expect(Number.isNaN(isoNaiveToEpoch('not-a-date'))).toBe(true);
  });
});

describe('journalRowToTradeEntry', () => {
  const baseRow: JournalRow = {
    id: 'abc-123',
    ticker: 'IWM',
    direction: 'CALL',
    entry_ts: '2026-07-02T13:35:00',
    exit_ts: null,
    entry_price: 220.5,
    exit_price: null,
    return_pct: null,
    notes: 'breakout',
    take_profits: [222, 224, 226],
    stop_loss: 218,
    status: 'active',
    source: 'chart',
    session_id: null,
    created_at: '2026-07-02T13:35:01',
  };

  it('maps an active trade with no exit', () => {
    const t = journalRowToTradeEntry(baseRow);
    expect(t.id).toBe('abc-123');
    expect(t.ticker).toBe('IWM');
    expect(t.optionType).toBe('CALL');
    expect(t.entryTime).toBe(isoNaiveToEpoch(baseRow.entry_ts));
    expect(t.entryPrice).toBe(220.5);
    expect(t.exitTime).toBeUndefined();
    expect(t.exitPrice).toBeUndefined();
    expect(t.takeProfits).toEqual([
      { price: 222, size: 0 },
      { price: 224, size: 0 },
      { price: 226, size: 0 },
    ]);
    expect(t.stopLoss).toEqual({ price: 218 });
    expect(t.status).toBe('active');
    expect(t.pnl).toBeUndefined();
    expect(t.pnlPercent).toBeUndefined();
  });

  it('derives pnl/pnlPercent for a closed CALL from server return_pct, sign preserved', () => {
    const row: JournalRow = {
      ...baseRow,
      exit_ts: '2026-07-02T13:40:00',
      exit_price: 224.5,
      return_pct: 1.814512, // (224.5-220.5)/220.5*100
      status: 'win',
    };
    const t = journalRowToTradeEntry(row);
    expect(t.status).toBe('win');
    expect(t.pnlPercent).toBeCloseTo(1.814512, 6);
    expect(t.pnl).toBeCloseTo(220.5 * (1.814512 / 100), 6);
  });

  it('derives pnl/pnlPercent for a closed PUT (return_pct already negated server-side)', () => {
    const row: JournalRow = {
      ...baseRow,
      direction: 'PUT',
      exit_ts: '2026-07-02T13:40:00',
      exit_price: 224.5,
      return_pct: -1.814512, // PUT: price rose against the position
      status: 'loss',
    };
    const t = journalRowToTradeEntry(row);
    expect(t.optionType).toBe('PUT');
    expect(t.status).toBe('loss');
    expect(t.pnlPercent).toBeCloseTo(-1.814512, 6);
    // pnl-in-dollars stays negative too — entry_price * return_pct/100
    // preserves the sign without re-deriving direction on the client.
    expect(t.pnl).toBeCloseTo(220.5 * (-1.814512 / 100), 6);
  });

  it('defaults missing take_profits/stop_loss/notes/status/session_id on a legacy row', () => {
    const legacyRow: JournalRow = {
      id: 'legacy-1',
      ticker: 'SPY',
      direction: 'PUT',
      entry_ts: '2026-07-02T09:31:00',
      exit_ts: null,
      entry_price: 500,
      exit_price: null,
      return_pct: null,
      // take_profits, stop_loss, notes, status, source, session_id, created_at
      // all omitted — pre-Phase-2 local-dev rows never had these columns.
    };
    const t = journalRowToTradeEntry(legacyRow);
    expect(t.takeProfits).toEqual([]);
    expect(t.stopLoss).toBeUndefined();
    expect(t.notes).toBe('');
    expect(t.status).toBe('active');
    expect(typeof t.createdAt).toBe('number');
  });

  it('derives status from exit_ts + return_pct sign when status is absent but the trade is closed', () => {
    const row: JournalRow = {
      id: 'legacy-2',
      ticker: 'QQQ',
      direction: 'CALL',
      entry_ts: '2026-07-02T09:31:00',
      exit_ts: '2026-07-02T09:45:00',
      entry_price: 400,
      exit_price: 396,
      return_pct: -1.0,
    };
    const t = journalRowToTradeEntry(row);
    expect(t.status).toBe('loss');
  });

  it('round-trips: epochToJournalDateTime -> create body -> journalRowToTradeEntry recovers the same minute-aligned epoch', () => {
    const originalEntryTime = 1751463300; // minute-aligned (mod 60 === 0)
    const { date, time } = epochToJournalDateTime(originalEntryTime);
    // Mirrors the local-fallback entry_ts format journal.py's create_trade
    // builds: `f"{entry_date}T{entry_time}:00"`.
    const row: JournalRow = {
      ...baseRow,
      entry_ts: `${date}T${time}:00`,
    };
    const t = journalRowToTradeEntry(row);
    expect(t.entryTime).toBe(originalEntryTime);
  });
});
