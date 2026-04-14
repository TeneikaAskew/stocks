import { create } from 'zustand';
import type { Ticker } from '@/types';

interface TickerState {
  activeTicker: Ticker;
  setTicker: (ticker: Ticker) => void;
  availableTickers: Ticker[];
}

export const useTickerStore = create<TickerState>((set) => ({
  activeTicker: 'IWM',
  availableTickers: ['IWM', 'SPY', 'QQQ', 'SPX'],
  setTicker: (ticker) => set({ activeTicker: ticker }),
}));
