import { create } from 'zustand';

export type Theme = 'dark' | 'light';

const STORAGE_KEY = 'platform-theme';

function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'dark';
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'dark' || stored === 'light') return stored;
  // Dark is the product default (Obsidian Analyst), regardless of OS preference.
  // Users who explicitly pick light keep it via the stored value above.
  return 'dark';
}

function applyThemeToDocument(theme: Theme) {
  if (typeof document === 'undefined') return;
  document.documentElement.setAttribute('data-theme', theme);
}

interface ThemeState {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
}

const initial = getInitialTheme();
applyThemeToDocument(initial);

export const useThemeStore = create<ThemeState>((set) => ({
  theme: initial,
  setTheme: (theme) => {
    localStorage.setItem(STORAGE_KEY, theme);
    applyThemeToDocument(theme);
    set({ theme });
  },
  toggleTheme: () => {
    set((state) => {
      const next: Theme = state.theme === 'dark' ? 'light' : 'dark';
      localStorage.setItem(STORAGE_KEY, next);
      applyThemeToDocument(next);
      return { theme: next };
    });
  },
}));
