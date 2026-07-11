import { describe, expect, it } from 'vitest';
import { computeJournalStats } from '@/lib/journalStats';

const E = (ret: number | null, ts: string, source?: string) =>
  ({ return_pct: ret, entry_ts: ts, exit_ts: ts, source });

describe('computeJournalStats', () => {
  it('excludes null-return entries from every aggregate (no fake 0% trades)', () => {
    const s = computeJournalStats([E(2, '2026-01-02'), E(null, '2026-01-03'), E(-1, '2026-01-04')]);
    expect(s.closedCount).toBe(2);
    expect(s.totalCount).toBe(3);
    expect(s.winRate).toBeCloseTo(50);
    expect(s.avgReturn).toBeCloseTo(0.5);
    expect(s.totalReturn).toBeCloseTo(1);
    expect(s.equityPoints).toHaveLength(2); // null entry contributes NO point
  });
  it('returns null stats when no entry has a return', () => {
    const s = computeJournalStats([E(null, '2026-01-02')]);
    expect(s.winRate).toBeNull();
    expect(s.avgReturn).toBeNull();
    expect(s.equityPoints).toHaveLength(0);
  });

  // Task 5.3: practice-trade (replay) analytics hygiene.
  it('excludes source:"replay" entries from every aggregate by default', () => {
    const s = computeJournalStats([
      E(2, '2026-01-02', 'manual'),
      E(5, '2026-01-03', 'replay'),
    ]);
    expect(s.totalCount).toBe(1);
    expect(s.closedCount).toBe(1);
    expect(s.winRate).toBeCloseTo(100);
    expect(s.avgReturn).toBeCloseTo(2);
    expect(s.totalReturn).toBeCloseTo(2);
    expect(s.equityPoints).toHaveLength(1);
    expect(s.replayExcludedCount).toBe(1);
  });

  it('includes source:"replay" entries when includeReplay is true', () => {
    const s = computeJournalStats(
      [E(2, '2026-01-02', 'manual'), E(4, '2026-01-03', 'replay')],
      { includeReplay: true },
    );
    expect(s.totalCount).toBe(2);
    expect(s.closedCount).toBe(2);
    expect(s.avgReturn).toBeCloseTo(3);
    expect(s.totalReturn).toBeCloseTo(6);
    expect(s.equityPoints).toHaveLength(2);
    expect(s.replayExcludedCount).toBe(0);
  });

  it('reports zero replayExcludedCount when there are no replay entries', () => {
    const s = computeJournalStats([E(2, '2026-01-02', 'manual')]);
    expect(s.replayExcludedCount).toBe(0);
  });

  // #702 follow-ups Task 4 item 3: winCount/lossCount so JournalPage's
  // Trades-tile W/L sub-label reads straight off the aggregate instead of a
  // separately-scoped recompute that could drift from it.
  describe('winCount / lossCount', () => {
    it('counts wins (>0) and losses (<=0), excluding null-return entries entirely', () => {
      const s = computeJournalStats([
        E(2, '2026-01-02'),    // win
        E(-1, '2026-01-03'),   // loss
        E(0, '2026-01-04'),    // loss — matches lib/backtest.py's `<= 0` losers convention
        E(null, '2026-01-05'), // excluded from both counts
      ]);
      expect(s.winCount).toBe(1);
      expect(s.lossCount).toBe(2);
      expect(s.winCount + s.lossCount).toBe(s.closedCount);
    });

    it('is zero/zero when no entry has a return', () => {
      const s = computeJournalStats([E(null, '2026-01-02')]);
      expect(s.winCount).toBe(0);
      expect(s.lossCount).toBe(0);
    });

    it('is scoped by the replay-exclusion filter like every other aggregate', () => {
      const s = computeJournalStats([
        E(2, '2026-01-02', 'manual'),
        E(-3, '2026-01-03', 'replay'),
      ]);
      expect(s.winCount).toBe(1);
      expect(s.lossCount).toBe(0);
    });

    it('folds replay entries back in when includeReplay is true', () => {
      const s = computeJournalStats(
        [E(2, '2026-01-02', 'manual'), E(-3, '2026-01-03', 'replay')],
        { includeReplay: true },
      );
      expect(s.winCount).toBe(1);
      expect(s.lossCount).toBe(1);
    });
  });

  // Task 5 (journal one-stop): risk aggregates + session date-scoping.
  // All additions are PURE and additive — every assertion above this block
  // is byte-identical to before Task 5.
  describe('avgRR (Task 5)', () => {
    it('averages riskReward per trade over entries where it is computable', () => {
      const s = computeJournalStats([
        // |220-222.5| / |220-219| = 2.5
        { return_pct: 1.14, entry_ts: '2026-01-02T09:31:00', exit_ts: '2026-01-02T10:00:00',
          direction: 'CALL', entry_price: 220, exit_price: 222.5, take_profits: [222.5, 224], stop_loss: 219 },
        // |218-217| / |218-220| = 0.5
        { return_pct: -0.5, entry_ts: '2026-01-03T09:31:00', exit_ts: '2026-01-03T10:00:00',
          direction: 'PUT', entry_price: 218, exit_price: 219, take_profits: [217], stop_loss: 220 },
        // no TP/SL — not computable, excluded from the average (never a fake 0)
        { return_pct: 2, entry_ts: '2026-01-04T09:31:00', exit_ts: '2026-01-04T10:00:00',
          direction: 'CALL', entry_price: 100, exit_price: 102 },
      ]);
      expect(s.avgRR).toBeCloseTo(1.5);
    });

    it('is null when no entry has a computable R:R (no fabricated ratio)', () => {
      const s = computeJournalStats([E(2, '2026-01-02')]);
      expect(s.avgRR).toBeNull();
    });

    it('is null when stop === entry (zero risk distance is undefined, not 0)', () => {
      const s = computeJournalStats([
        { return_pct: 1, entry_ts: '2026-01-02T09:31:00', exit_ts: '2026-01-02T10:00:00',
          direction: 'CALL', entry_price: 220, exit_price: 221, take_profits: [222], stop_loss: 220 },
      ]);
      expect(s.avgRR).toBeNull();
    });
  });

  describe('tp1HitRate (Task 5)', () => {
    it('rates closed trades with TP1 set whose exit reached TP1 (direction-aware)', () => {
      const s = computeJournalStats([
        // CALL exit 222.5 >= TP1 222.5 — hit
        { return_pct: 1.14, entry_ts: '2026-01-02T09:31:00', exit_ts: '2026-01-02T10:00:00',
          direction: 'CALL', entry_price: 220, exit_price: 222.5, take_profits: [222.5], stop_loss: 219 },
        // CALL exit 221 < TP1 223 — miss
        { return_pct: 0.45, entry_ts: '2026-01-03T09:31:00', exit_ts: '2026-01-03T10:00:00',
          direction: 'CALL', entry_price: 220, exit_price: 221, take_profits: [223], stop_loss: 219 },
        // PUT exit 216 <= TP1 217 — hit
        { return_pct: 0.9, entry_ts: '2026-01-04T09:31:00', exit_ts: '2026-01-04T10:00:00',
          direction: 'PUT', entry_price: 218, exit_price: 216, take_profits: [217], stop_loss: 220 },
        // TP1 set but still open (no exit) — excluded from the denominator
        { return_pct: null, entry_ts: '2026-01-05T09:31:00', exit_ts: null,
          direction: 'CALL', entry_price: 220, exit_price: null, take_profits: [225], stop_loss: 219 },
        // closed but no TP1 — never qualifies
        { return_pct: 2, entry_ts: '2026-01-06T09:31:00', exit_ts: '2026-01-06T10:00:00',
          direction: 'CALL', entry_price: 100, exit_price: 102 },
      ]);
      expect(s.tp1HitRate).toBeCloseTo((2 / 3) * 100);
    });

    it('is null when no closed trade has TP1 set (no fabricated rate)', () => {
      const s = computeJournalStats([E(2, '2026-01-02')]);
      expect(s.tp1HitRate).toBeNull();
    });
  });

  describe('date scoping (Task 5)', () => {
    const D2 = { return_pct: 2, entry_ts: '2026-01-02T09:31:00', exit_ts: '2026-01-02T10:00:00' };
    const D3 = { return_pct: -1, entry_ts: '2026-01-03T09:31:00', exit_ts: '2026-01-03T10:00:00' };

    it('scopes every aggregate to entries whose entry_ts date matches', () => {
      const s = computeJournalStats([D2, D3], { date: '2026-01-02' });
      expect(s.totalCount).toBe(1);
      expect(s.closedCount).toBe(1);
      expect(s.totalReturn).toBeCloseTo(2);
      expect(s.winCount).toBe(1);
      expect(s.lossCount).toBe(0);
      expect(s.equityPoints).toHaveLength(1);
    });

    it('omitting date keeps the all-dates behaviour byte-identical', () => {
      const all = computeJournalStats([D2, D3]);
      expect(all.totalCount).toBe(2);
      expect(all.totalReturn).toBeCloseTo(1);
    });

    it('scopes the replay-excluded count to the selected date too', () => {
      const s = computeJournalStats(
        [D2, { ...D3, source: 'replay' }],
        { date: '2026-01-03' },
      );
      expect(s.totalCount).toBe(0);
      expect(s.replayExcludedCount).toBe(1);
    });
  });
});
