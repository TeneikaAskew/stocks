import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface TickerState {
  activeTicker: string;
  /** The app's core, always-instrumented tickers — shown as one-tap chips. */
  quickPicks: string[];
  /** Most-recently-selected tickers (typed via the combobox), newest first, capped at 8. */
  recentTickers: string[];
  setTicker: (ticker: string) => void;
  pushRecent: (ticker: string) => void;
}

export const useTickerStore = create<TickerState>()(
  persist(
    (set) => ({
      activeTicker: 'IWM',
      quickPicks: ['IWM', 'SPY', 'QQQ'],
      recentTickers: [],
      setTicker: (ticker) => set({ activeTicker: ticker.toUpperCase() }),
      pushRecent: (ticker) =>
        set((s) => ({
          recentTickers: [
            ticker.toUpperCase(),
            ...s.recentTickers.filter((t) => t !== ticker.toUpperCase()),
          ].slice(0, 8),
        })),
    }),
    {
      name: 'ticker-store',
      partialize: (s) => ({ activeTicker: s.activeTicker, recentTickers: s.recentTickers }),
    },
  ),
);
