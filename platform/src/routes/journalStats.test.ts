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
});
