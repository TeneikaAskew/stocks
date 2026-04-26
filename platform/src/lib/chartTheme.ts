/**
 * Shared chart theme for lightweight-charts and Recharts instances.
 * Reads CSS variables from :root / [data-theme="light"] so charts swap
 * with the global theme. See docs/DESIGN_SYSTEM.md.
 *
 * Use `useChartTheme()` inside components so they re-render on toggle.
 * The static `chartTheme` export remains for non-reactive callers
 * (e.g. one-time chart setup) but resolves at the time of access from
 * whatever theme is current on document.documentElement.
 */
import { useThemeStore } from '@/stores/themeStore';

interface ChartTheme {
  bg: string;
  cardBg: string;
  grid: string;
  gridLight: string;
  border: string;
  axis: string;
  axisSize: number;
  textMuted: string;
  textLabel: string;
  bull: string;
  bear: string;
  brand: string;
  brandGlow: string;
  brandContainer: string;
  warn: string;
  tooltipBg: string;
  tooltipText: string;
}

function readVar(name: string, fallback: string): string {
  if (typeof window === 'undefined' || typeof document === 'undefined') return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function buildChartTheme(): ChartTheme {
  // Fallbacks match the dark palette in case CSS vars are not yet computed
  // (e.g. during SSR or the very first paint before stylesheet load).
  return {
    bg: readVar('--surface-0', '#111318'),
    cardBg: readVar('--surface-2', '#282a2e'),
    grid: readVar('--chart-grid', '#1f2127'),
    gridLight: readVar('--surface-1', '#14141c'),
    border: readVar('--outline-variant', '#2a2a3a'),
    axis: readVar('--chart-axis', '#6e7781'),
    axisSize: 10,
    textMuted: readVar('--on-surface-variant', '#bdc8d2'),
    textLabel: readVar('--on-surface-label', '#5a6670'),
    bull: readVar('--bull', '#22c55e'),
    bear: readVar('--bear', '#ef4444'),
    brand: readVar('--brand', '#8bceff'),
    brandGlow: readVar('--brand-glow', '#60b8ff'),
    brandContainer: readVar('--brand-container', '#00b2ff'),
    warn: readVar('--warn', '#ffb86b'),
    tooltipBg: readVar('--surface-lowest', '#0c0e12'),
    tooltipText: readVar('--on-surface', '#e2e2e8'),
  };
}

/** Reactive hook — re-evaluates whenever the global theme toggles. */
export function useChartTheme(): ChartTheme {
  // Subscribe to theme so the host component re-renders on toggle.
  // The actual values still come from CSS vars (single source of truth).
  useThemeStore((s) => s.theme);
  return buildChartTheme();
}

/**
 * Non-reactive accessor. Returns the theme as it stands at call time.
 * Prefer `useChartTheme()` in React components; this is for one-time
 * setup paths where rebuilding the chart on toggle isn't desired.
 *
 * Implemented as a Proxy so existing `chartTheme.bull` access still works
 * but resolves against the current theme each read.
 */
export const chartTheme = new Proxy({} as ChartTheme, {
  get(_t, prop: string) {
    return buildChartTheme()[prop as keyof ChartTheme];
  },
}) as ChartTheme;
