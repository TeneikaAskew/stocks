/**
 * Risk:reward ratio for a single-target trade plan — |entry-tp1| / |entry-stop|.
 *
 * Returns `null` (never a fabricated number, per CLAUDE.md Rule 3.7) when any
 * input is null/missing, or when stop === entry (division by zero — a trade
 * plan with no stop distance has no defined risk unit to measure reward
 * against).
 */
export function riskReward(entry: number | null, tp1: number | null, stop: number | null): number | null {
  if (entry == null || tp1 == null || stop == null) return null;
  if (stop === entry) return null;
  return Math.abs(entry - tp1) / Math.abs(entry - stop);
}
