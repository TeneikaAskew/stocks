// Vitest unit tests for the ticker type-ahead combobox (Phase 1, Task 2).
//
// Tested as pure logic (this platform's established frontend test style —
// no DOM rendering, no @testing-library/react; see MovementRead.test.tsx).
// The component itself only renders; the load-bearing logic is the coverage
// badge mapping, the search-result merge, and the debounce scheduler.

import { describe, expect, it, vi } from 'vitest';
import { coverageBadge, mergeSuggestions } from './TickerCombobox';
import { scheduleDebounce } from '@/hooks/useDebouncedValue';

describe('coverageBadge', () => {
  it('maps coverage to badges', () => {
    expect(coverageBadge({ intraday: true, daily: true })).toBe('full');
    expect(coverageBadge({ intraday: false, daily: true })).toBe('daily');
    expect(coverageBadge({ intraday: false, daily: false })).toBe('new');
    expect(coverageBadge(undefined)).toBe('new'); // coverage still loading/unknown → honest "new"
  });

  it('treats intraday-only (no daily) as "new", never fabricating "daily"', () => {
    // intraday: true, daily: false shouldn't happen in practice (daily backfill
    // always precedes intraday), but the mapping must not silently upgrade it.
    expect(coverageBadge({ intraday: true, daily: false })).toBe('new');
  });
});

describe('mergeSuggestions', () => {
  it('attaches badges to search results by symbol', () => {
    const merged = mergeSuggestions(
      [{ symbol: 'AAPL', name: 'Apple Inc', type: 'Equity', region: 'United States', currency: 'USD', match_score: 0.9 }],
      { AAPL: { intraday: false, daily: true } },
    );
    expect(merged[0]).toMatchObject({ symbol: 'AAPL', badge: 'daily' });
  });

  it('matches coverage case-insensitively via symbol upper-casing', () => {
    const merged = mergeSuggestions(
      [{ symbol: 'aapl', name: 'Apple Inc', type: 'Equity', region: 'United States', currency: 'USD', match_score: 0.9 }],
      { AAPL: { intraday: true, daily: true } },
    );
    expect(merged[0]).toMatchObject({ symbol: 'aapl', badge: 'full' });
  });

  it('badges as "new" when a result symbol has no coverage entry (not fabricated)', () => {
    const merged = mergeSuggestions(
      [{ symbol: 'ZZZZ', name: 'Unknown Co', type: 'Equity', region: 'United States', currency: 'USD', match_score: 0.4 }],
      {},
    );
    expect(merged[0]).toMatchObject({ symbol: 'ZZZZ', badge: 'new' });
  });

  it('preserves result order and count', () => {
    const results = [
      { symbol: 'AAPL', name: 'Apple Inc', type: 'Equity', region: 'United States', currency: 'USD', match_score: 0.9 },
      { symbol: 'MSFT', name: 'Microsoft Corp', type: 'Equity', region: 'United States', currency: 'USD', match_score: 0.8 },
    ];
    const merged = mergeSuggestions(results, {});
    expect(merged.map((m) => m.symbol)).toEqual(['AAPL', 'MSFT']);
  });
});

// ── useDebouncedValue's scheduling primitive ─────────────────────────────
//
// No @testing-library/react in devDependencies (renderHook unavailable), so
// the debounce logic is tested via its extracted pure scheduler function.

describe('scheduleDebounce', () => {
  it('invokes onSettle with the value only after ms of inactivity', () => {
    vi.useFakeTimers();
    try {
      const onSettle = vi.fn();
      scheduleDebounce('abc', 300, onSettle);
      vi.advanceTimersByTime(299);
      expect(onSettle).not.toHaveBeenCalled();
      vi.advanceTimersByTime(1);
      expect(onSettle).toHaveBeenCalledExactlyOnceWith('abc');
    } finally {
      vi.useRealTimers();
    }
  });

  it('the returned cancel function prevents onSettle from firing', () => {
    vi.useFakeTimers();
    try {
      const onSettle = vi.fn();
      const cancel = scheduleDebounce('abc', 300, onSettle);
      cancel();
      vi.advanceTimersByTime(300);
      expect(onSettle).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('re-scheduling on every keystroke (each cancelling the prior, as the useEffect cleanup does) only fires the last value', () => {
    vi.useFakeTimers();
    try {
      const onSettle = vi.fn();
      let cancel = scheduleDebounce('a', 300, onSettle);
      vi.advanceTimersByTime(100);
      cancel(); // simulates the effect cleanup firing on the next keystroke
      cancel = scheduleDebounce('ap', 300, onSettle);
      vi.advanceTimersByTime(100);
      cancel();
      scheduleDebounce('app', 300, onSettle);
      vi.advanceTimersByTime(300);
      // Only the final schedule's onSettle should have fired, and only once.
      expect(onSettle).toHaveBeenCalledExactlyOnceWith('app');
    } finally {
      vi.useRealTimers();
    }
  });
});
