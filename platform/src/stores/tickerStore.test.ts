// Vitest unit tests for the ticker store (Phase 1, Task 2).
//
// Covers the pushRecent invariants the TickerCombobox depends on (newest
// first, deduped, capped at 8, uppercased) and the persist partialize
// contract: quickPicks are code-owned (not user state) and must NEVER be
// persisted, otherwise a stale localStorage copy would shadow future
// quick-pick changes shipped in code.

import { beforeEach, describe, expect, it, vi } from 'vitest';

// Minimal in-memory localStorage so zustand's persist middleware fully
// initialises in the node test environment. Its default storage is
// `window.localStorage`; without a window, persist bails out early and
// never attaches the `useTickerStore.persist` API that the partialize
// test below exercises.
const backing = new Map<string, string>();
const localStorageStub = {
  getItem: (k: string) => backing.get(k) ?? null,
  setItem: (k: string, v: string) => void backing.set(k, v),
  removeItem: (k: string) => void backing.delete(k),
  clear: () => backing.clear(),
} satisfies Pick<Storage, 'getItem' | 'setItem' | 'removeItem' | 'clear'>;
vi.stubGlobal('localStorage', localStorageStub);
vi.stubGlobal('window', { localStorage: localStorageStub });

const { useTickerStore } = await import('./tickerStore');

const initialState = useTickerStore.getState();

beforeEach(() => {
  useTickerStore.setState({ ...initialState, recentTickers: [], activeTicker: 'IWM' });
});

describe('setTicker', () => {
  it('uppercases the active ticker', () => {
    useTickerStore.getState().setTicker('aapl');
    expect(useTickerStore.getState().activeTicker).toBe('AAPL');
  });
});

describe('pushRecent', () => {
  it('prepends (newest first) and uppercases', () => {
    useTickerStore.getState().pushRecent('aapl');
    useTickerStore.getState().pushRecent('msft');
    expect(useTickerStore.getState().recentTickers).toEqual(['MSFT', 'AAPL']);
  });

  it('dedupes: re-pushing an existing symbol moves it to the front without duplicating', () => {
    useTickerStore.getState().pushRecent('AAPL');
    useTickerStore.getState().pushRecent('MSFT');
    useTickerStore.getState().pushRecent('AAPL');
    expect(useTickerStore.getState().recentTickers).toEqual(['AAPL', 'MSFT']);
  });

  it('dedupes case-insensitively (lowercase re-push of an uppercased entry)', () => {
    useTickerStore.getState().pushRecent('AAPL');
    useTickerStore.getState().pushRecent('MSFT');
    useTickerStore.getState().pushRecent('aapl');
    expect(useTickerStore.getState().recentTickers).toEqual(['AAPL', 'MSFT']);
  });

  it('caps the list at 8, evicting the oldest', () => {
    const symbols = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'];
    for (const s of symbols) useTickerStore.getState().pushRecent(s);
    const recents = useTickerStore.getState().recentTickers;
    expect(recents).toHaveLength(8);
    expect(recents).toEqual(['J', 'I', 'H', 'G', 'F', 'E', 'D', 'C']);
  });
});

describe('persist partialize', () => {
  it('persists activeTicker + recentTickers and omits quickPicks (code-owned, must not be shadowed by stale storage)', () => {
    const { partialize } = useTickerStore.persist.getOptions();
    expect(partialize).toBeTypeOf('function');
    const persisted = partialize!({
      ...useTickerStore.getState(),
      activeTicker: 'MSFT',
      recentTickers: ['MSFT', 'AAPL'],
    });
    expect(persisted).toEqual({ activeTicker: 'MSFT', recentTickers: ['MSFT', 'AAPL'] });
    expect(persisted).not.toHaveProperty('quickPicks');
  });
});
