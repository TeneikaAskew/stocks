/**
 * Central number/price formatters for the Obsidian Analyst redesign.
 *
 * Every helper is **null-safe** and renders a missing value as the em-dash
 * placeholder `—` (CLAUDE.md Rule 3.7 — no silent fallbacks: a missing price
 * or Greek must never read as `0`/`$0.00`). The display layer is the *only*
 * place a nullish financial value is allowed to render, and it renders "—",
 * not a fabricated number.
 */

/** Em-dash placeholder for unavailable data. */
export const NA = '—';

function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

/** `$1.23`, `$45.6K`, `$7.89M`, `$1.2B` — compact money. */
export function fmtMoney(v: number | null | undefined): string {
  if (!isNum(v)) return NA;
  const a = Math.abs(v);
  if (a >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${v.toFixed(2)}`;
}

/** Plain price `$123.45`. Pass `digits` to control precision. */
export function fmtPrice(v: number | null | undefined, digits = 2): string {
  if (!isNum(v)) return NA;
  return `$${v.toFixed(digits)}`;
}

/** Signed integer with thousands separators: `+1,234` / `-56`. */
export function fmtSigned(v: number | null | undefined): string {
  if (!isNum(v)) return NA;
  const s = Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
  return `${v >= 0 ? '+' : '-'}${s}`;
}

/** Signed percent: `+0.37%` / `-2.05%`. `v` is already in percent units. */
export function fmtPct(v: number | null | undefined, digits = 2): string {
  if (!isNum(v)) return NA;
  return `${v >= 0 ? '+' : ''}${v.toFixed(digits)}%`;
}

/** Signed percent from a *ratio* (0.0037 → `+0.37%`). */
export function fmtRatioPct(v: number | null | undefined, digits = 2): string {
  if (!isNum(v)) return NA;
  return fmtPct(v * 100, digits);
}

/** Compact GEX/notional in `$K`/`$M`/`$Bn` with sign — for gamma surfaces. */
export function fmtGex(v: number | null | undefined): string {
  if (!isNum(v)) return NA;
  const a = Math.abs(v);
  const sign = v < 0 ? '-' : '';
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(2)}Bn`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(0)}K`;
  return `${sign}$${a.toFixed(0)}`;
}

/** Compact count: `1.2K`, `34.5M`. Unsigned. */
export function fmtCompact(v: number | null | undefined, digits = 1): string {
  if (!isNum(v)) return NA;
  const a = Math.abs(v);
  if (a >= 1e9) return `${(v / 1e9).toFixed(digits)}B`;
  if (a >= 1e6) return `${(v / 1e6).toFixed(digits)}M`;
  if (a >= 1e3) return `${(v / 1e3).toFixed(digits)}K`;
  return v.toFixed(0);
}

/** Fixed-precision number, null-safe. */
export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (!isNum(v)) return NA;
  return v.toFixed(digits);
}

/** Bull/bear/neutral tone from a signed number (for delta coloring). */
export function toneOf(v: number | null | undefined): 'bull' | 'bear' | 'neutral' {
  if (!isNum(v) || v === 0) return 'neutral';
  return v > 0 ? 'bull' : 'bear';
}
