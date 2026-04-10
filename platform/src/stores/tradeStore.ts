import { create } from 'zustand';
import type { TradeEntry } from '@/types';

interface TradeState {
  trades: TradeEntry[];
  addTrade: (trade: TradeEntry) => void;
  updateTrade: (id: string, update: Partial<TradeEntry>) => void;
  removeTrade: (id: string) => void;
  loadTrades: (trades: TradeEntry[]) => void;
}

export const useTradeStore = create<TradeState>((set) => ({
  trades: [],
  addTrade: (trade) => set((s) => ({ trades: [...s.trades, trade] })),
  updateTrade: (id, update) =>
    set((s) => ({
      trades: s.trades.map((t) => (t.id === id ? { ...t, ...update } : t)),
    })),
  removeTrade: (id) => set((s) => ({ trades: s.trades.filter((t) => t.id !== id) })),
  loadTrades: (trades) => set({ trades }),
}));
