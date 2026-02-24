import { create } from 'zustand';
import type { Ticker } from '@/types';

interface MarketData {
  price: number;
  change: number;
  changePct: number;
  high: number;
  low: number;
  volume: number;
  lastUpdate: number;
}

interface MarketState {
  data: Partial<Record<Ticker, MarketData>>;
  isMarketOpen: boolean;
  updateMarketData: (ticker: Ticker, data: MarketData) => void;
  setMarketOpen: (open: boolean) => void;
}

export const useMarketStore = create<MarketState>((set) => ({
  data: {},
  isMarketOpen: false,
  updateMarketData: (ticker, data) =>
    set((s) => ({ data: { ...s.data, [ticker]: data } })),
  setMarketOpen: (isMarketOpen) => set({ isMarketOpen }),
}));
