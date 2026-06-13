// Shared GEX/VEX value formatter — single source so the options page and the
// 2-D gamma grid render identical notation. Extracted from OptionsFlowPage.tsx.
//
//   1_250_000 → "+1.2M"   -48_000 → "-48K"   312 → "+312"

export function formatGex(val: number): string {
  const abs = Math.abs(val);
  const sign = val >= 0 ? '+' : '-';
  if (abs >= 1_000_000) return `${sign}${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${sign}${(abs / 1_000).toFixed(0)}K`;
  return `${sign}${abs.toFixed(0)}`;
}

// Format the per-cell intraday %-change badge. Display magnitude is clamped so
// small-base sign-flip blowups (e.g. +11000%) don't dominate the cell; the
// exact value is preserved for the tooltip (see GammaGrid). `null` → no badge.
export const PCT_CHANGE_DISPLAY_CAP = 999;

export function formatPctChange(pct: number): string {
  const sign = pct >= 0 ? '+' : '-';
  const capped = Math.min(Math.abs(pct), PCT_CHANGE_DISPLAY_CAP);
  const suffix = Math.abs(pct) > PCT_CHANGE_DISPLAY_CAP ? '+' : '';
  return `${sign}${capped.toFixed(0)}${suffix}%`;
}
