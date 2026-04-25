/**
 * Shared chart theme for lightweight-charts and Recharts instances.
 *
 * Reads CSS variables from :root / [data-theme="light"] (defined in
 * src/index.css) so charts swap with the global theme rather than
 * showing the dark palette over a light surface (a WCAG hazard:
 * the previous static `textMuted: '#bdc8d2'` collapsed to ~1.6:1
 * contrast on the light surface-2).
 *
 * Use `useChartTheme()` inside React components — it subscribes to
 * the theme store so the chart re-renders on toggle. The static
 * `chartTheme` export is preserved for non-reactive callers and is
 * a Proxy that resolves CSS vars at every property access.
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
  useThemeStore((s) => s.theme);
  return buildChartTheme();
}

/**
 * Non-reactive accessor preserved for backwards compatibility. Each
 * property read resolves the current CSS-var value, so initial chart
 * setup picks up the right palette even if the component does not
 * subscribe to the theme store.
 */
export const chartTheme = new Proxy({} as ChartTheme, {
  get(_t, prop: string) {
    return buildChartTheme()[prop as keyof ChartTheme];
  },
}) as ChartTheme;
