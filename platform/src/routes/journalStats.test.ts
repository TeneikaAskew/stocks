import { describe, expect, it } from 'vitest';
import { computeJournalStats } from '@/lib/journalStats';

const E = (ret: number | null, ts: string) =>
  ({ return_pct: ret, entry_ts: ts, exit_ts: ts });

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
});
