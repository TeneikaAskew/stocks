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

/**
 * Stop-column display text — shared by JournalPage's table Stop cell and
 * TradeRailCard's SL segment (task-alerts-enrichment, 2026-07-12) so the two
 * surfaces can never drift on the fallback rule.
 *
 * Priority: a real stop PRICE always wins ("$123.45"). When there is no
 * price but a pipeline row's matched alert carries a time-based exit rule
 * (`timeStopMinutes`), render EACH row's OWN value as "<N>m time-stop" —
 * USER REQUIREMENT (verbatim, task-alerts-enrichment-brief.md): the stop is
 * NOT always a fixed number of minutes; never render a hardcoded label.
 * Neither leg present -> "—" (Rule 3.7 — never a fabricated value).
 */
export function stopDisplayText(
  stopPrice: number | null | undefined,
  timeStopMinutes: number | null | undefined,
): string {
  if (stopPrice != null) return `$${stopPrice.toFixed(2)}`;
  if (timeStopMinutes != null) return `${timeStopMinutes}m time-stop`;
  return '—';
}
