/**
 * Shared chart theme for lightweight-charts and Recharts instances.
 * Matches the Obsidian Analyst design system tokens (see docs/DESIGN_SYSTEM.md).
 * Reference this from any chart component instead of duplicating hex literals.
 */
export const chartTheme = {
  // Backgrounds
  bg: '#111318',          // surface-0
  cardBg: '#282a2e',      // surface-2 (where charts live)

  // Grid — very subtle, only where it helps readability
  grid: '#1f2127',
  gridLight: '#14141c',

  // Borders (axis, panel edges) — ghost borders, felt not seen
  border: '#2a2a3a',

  // Axis labels
  axis: '#6e7781',
  axisSize: 10,

  // Text
  textMuted: '#bdc8d2',
  textLabel: '#5a6670',

  // Directional (strictly semantic — market indicators only)
  bull: '#22c55e', // up, bullish, gains
  bear: '#ef4444', // down, bearish, losses

  // Brand (primary accent, non-directional) — Obsidian Analyst blue
  brand: '#8bceff',
  brandGlow: '#60b8ff',
  brandContainer: '#00b2ff',

  // Warning / reference lines / amber highlights
  warn: '#ffb86b',
} as const;
