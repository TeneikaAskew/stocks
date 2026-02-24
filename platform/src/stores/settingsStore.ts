import { create } from 'zustand';
import type { Timeframe } from '@/types';

interface SettingsState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  timeframe: Timeframe;
  setTimeframe: (tf: Timeframe) => void;
  soundEnabled: boolean;
  toggleSound: () => void;
}

export const useSettingsStore = create<SettingsState>((set) => ({
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  timeframe: '5',
  setTimeframe: (timeframe) => set({ timeframe }),
  soundEnabled: true,
  toggleSound: () => set((s) => ({ soundEnabled: !s.soundEnabled })),
}));
