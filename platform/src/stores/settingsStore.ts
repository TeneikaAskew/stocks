import { create } from 'zustand';
import type { Timeframe } from '@/types';

export type NavPattern = 'top-tabs' | 'sidebar';
export type Density = 'comfy' | 'default' | 'dense';
export type Accent =
  | 'blue'
  | 'amber'
  | 'violet'
  | 'cyan'
  | 'teal'
  | 'pink'
  | 'magenta'
  | 'orange'
  | 'yellow'
  | 'indigo'
  | 'rose';

export const ACCENTS: Accent[] = [
  'blue',
  'amber',
  'violet',
  'cyan',
  'teal',
  'pink',
  'magenta',
  'orange',
  'yellow',
  'indigo',
  'rose',
];

const STORAGE_KEY = 'platform-shell-settings';

interface Persisted {
  navPattern: NavPattern;
  density: Density;
  accent: Accent;
}

// Dense is the product default (Bloomberg-terminal information density); users
// can switch to default/comfy in Settings, which persists over this.
const DEFAULTS: Persisted = { navPattern: 'top-tabs', density: 'dense', accent: 'blue' };

function loadPersisted(): Persisted {
  if (typeof window === 'undefined') return DEFAULTS;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    return { ...DEFAULTS, ...(JSON.parse(raw) as Partial<Persisted>) };
  } catch {
    return DEFAULTS;
  }
}

/** Density + accent ride on <body> classes so CSS variables cascade globally. */
function applyShellClasses(density: Density, accent: Accent) {
  if (typeof document === 'undefined') return;
  const body = document.body;
  body.classList.forEach((c) => {
    if (c.startsWith('density-') || c.startsWith('accent-')) body.classList.remove(c);
  });
  body.classList.add(`density-${density}`, `accent-${accent}`);
}

function persist(next: Persisted) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    /* storage unavailable — non-fatal */
  }
}

interface SettingsState extends Persisted {
  // Pre-existing fields (preserved)
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  timeframe: Timeframe;
  setTimeframe: (tf: Timeframe) => void;
  soundEnabled: boolean;
  toggleSound: () => void;
  // Shell chrome
  setNavPattern: (p: NavPattern) => void;
  setDensity: (d: Density) => void;
  setAccent: (a: Accent) => void;
}

const initial = loadPersisted();
applyShellClasses(initial.density, initial.accent);

export const useSettingsStore = create<SettingsState>((set, get) => ({
  ...initial,

  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  timeframe: '5',
  setTimeframe: (timeframe) => set({ timeframe }),
  soundEnabled: true,
  toggleSound: () => set((s) => ({ soundEnabled: !s.soundEnabled })),

  setNavPattern: (navPattern) => {
    const { density, accent } = get();
    persist({ navPattern, density, accent });
    set({ navPattern });
  },
  setDensity: (density) => {
    const { navPattern, accent } = get();
    applyShellClasses(density, accent);
    persist({ navPattern, density, accent });
    set({ density });
  },
  setAccent: (accent) => {
    const { navPattern, density } = get();
    applyShellClasses(density, accent);
    persist({ navPattern, density, accent });
    set({ accent });
  },
}));
