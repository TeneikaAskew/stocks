// Pure logic for the Expected-Move card affordances. No React, no fetches —
// unit-tested in expectedMove.test.ts. p_tail thresholds are base-rate grounded
// (see docs/superpowers/specs/2026-07-13-expected-move-affordances-design.md).
export const SIZE_LIGHT_GREEN = 0.2;
export const SIZE_LIGHT_AMBER = 0.1;

export type SizeLevel = 'big' | 'elevated' | 'tight' | 'unknown';
export type Tone = 'green' | 'amber' | 'red' | 'muted';

export function sizeLight(
  pTail: number | null | undefined,
): { level: SizeLevel; label: string; tone: Tone } {
  if (pTail == null || Number.isNaN(pTail)) {
    return { level: 'unknown', label: '—', tone: 'muted' };
  }
  if (pTail >= SIZE_LIGHT_GREEN) return { level: 'big', label: 'big move likely', tone: 'green' };
  if (pTail >= SIZE_LIGHT_AMBER) return { level: 'elevated', label: 'elevated', tone: 'amber' };
  return { level: 'tight', label: 'tight', tone: 'red' };
}

const _ATR_LABEL: Record<string, string> = {
  TIGHT: '≈ < 0.5× ATR',
  NORMAL: '≈ 0.5–1.0× ATR',
  EXPANDED: '≈ 1.0–1.5× ATR',
  EXPLOSIVE: '≈ ≥ 1.5× ATR',
};
export function bucketToAtrLabel(sizeClass: string | null | undefined): string {
  return (sizeClass && _ATR_LABEL[sizeClass]) || '—';
}

export function riskHint(sizeClass: string | null | undefined): string | null {
  if (sizeClass === 'EXPANDED' || sizeClass === 'EXPLOSIVE')
    return 'bigger move likely — consider wider stops / smaller size';
  if (sizeClass === 'TIGHT') return 'quiet — tighter stops OK';
  return null;
}

export const OPTIONS_IDEA_MIN_P_EXPLOSIVE = 0.1;
export function showOptionsIdea(pExplosive: number | null | undefined): boolean {
  return (
    pExplosive != null && !Number.isNaN(pExplosive) && pExplosive >= OPTIONS_IDEA_MIN_P_EXPLOSIVE
  );
}

// Bucket upper edge (mag_config MAGNITUDE_THRESHOLDS); EXPLOSIVE's top bucket is
// open-ended, so 2.0 is a capped proxy for a stop-distance suggestion.
const _BUCKET_K: Record<string, number> = {
  TIGHT: 0.5,
  NORMAL: 1.0,
  EXPANDED: 1.5,
  EXPLOSIVE: 2.0,
};
export function sizeCalc(args: {
  sizeClass: string | null | undefined;
  atr20: number | null | undefined;
  account: number;
  riskPct: number;
}): { stop: number; shares: number } | null {
  const { sizeClass, atr20, account, riskPct } = args;
  const k = sizeClass ? _BUCKET_K[sizeClass] : undefined;
  if (k == null) return null;
  if (atr20 == null || Number.isNaN(atr20) || atr20 <= 0) return null;
  if (!(account > 0) || !(riskPct > 0)) return null;
  const stop = k * atr20;
  const shares = Math.floor((account * (riskPct / 100)) / stop);
  return { stop, shares };
}
