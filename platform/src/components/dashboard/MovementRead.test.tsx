/// <reference types="node" />
// Vitest unit tests for the Movement Read card (PHASE 3).
//
// Tested as pure logic (the platform's established frontend test style —
// no DOM rendering, no @testing-library/react). The card RENDERS ONLY and
// recomputes nothing, so the load-bearing logic is the small set of
// presentational helpers that decide OK vs. UNAVAILABLE and format the
// reach-rate / low-sample / probability strings. Those helpers encode the
// Rule 3.7 contract: a null / UNAVAILABLE field becomes "—" (em-dash),
// never a fabricated number.

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';
import {
  isOk,
  fmtProbPct,
  fmtReachRate,
  isLowSample,
} from './MovementRead';
import type { ReachRate } from '@/types';

const EM_DASH = '—';

function rr(overrides: Partial<ReachRate> = {}): ReachRate {
  return {
    status: 'OK',
    reach_rate: 0.48,
    hits: 24,
    sample_n: 50,
    low_sample: false,
    ...overrides,
  };
}

// ── isOk ───────────────────────────────────────────────────────────────────

describe('isOk', () => {
  it('is true only for status "OK"', () => {
    expect(isOk({ status: 'OK' })).toBe(true);
  });
  it('is false for UNAVAILABLE / unexpected / null', () => {
    expect(isOk({ status: 'UNAVAILABLE' })).toBe(false);
    expect(isOk({ status: 'REJECTED' })).toBe(false);
    expect(isOk(null)).toBe(false);
    expect(isOk(undefined)).toBe(false);
  });
});

// ── fmtProbPct — null must NOT coerce to 0% (Rule 3.7) ──────────────────────

describe('fmtProbPct', () => {
  it('formats a 0..1 probability as a whole percent', () => {
    expect(fmtProbPct(0.62)).toBe('62%');
    expect(fmtProbPct(0.5)).toBe('50%');
  });
  it('renders an em-dash for null / undefined / NaN — never 0%', () => {
    expect(fmtProbPct(null)).toBe(EM_DASH);
    expect(fmtProbPct(undefined)).toBe(EM_DASH);
    expect(fmtProbPct(NaN)).toBe(EM_DASH);
  });
});

// ── fmtReachRate — OK shows "% (n=…)"; UNAVAILABLE shows "—" ─────────────────

describe('fmtReachRate', () => {
  it('formats an OK reach-rate with its sample size', () => {
    expect(fmtReachRate(rr())).toBe('48% (n=50)');
  });
  it('renders an em-dash when UNAVAILABLE (never a fabricated rate)', () => {
    expect(fmtReachRate(rr({ status: 'UNAVAILABLE', reach_rate: null }))).toBe(EM_DASH);
  });
  it('renders an em-dash when the rate is null even if status looks OK', () => {
    expect(fmtReachRate(rr({ reach_rate: null }))).toBe(EM_DASH);
  });
  it('renders an em-dash for null/undefined input', () => {
    expect(fmtReachRate(null)).toBe(EM_DASH);
    expect(fmtReachRate(undefined)).toBe(EM_DASH);
  });
});

// ── isLowSample — only flags when OK AND low_sample === true ─────────────────

describe('isLowSample', () => {
  it('is true when OK and low_sample flagged', () => {
    expect(isLowSample(rr({ sample_n: 12, low_sample: true }))).toBe(true);
  });
  it('is false when low_sample is false', () => {
    expect(isLowSample(rr({ low_sample: false }))).toBe(false);
  });
  it('is false when the reach-rate is UNAVAILABLE', () => {
    expect(isLowSample(rr({ status: 'UNAVAILABLE', low_sample: true }))).toBe(false);
  });
  it('is false for null', () => {
    expect(isLowSample(null)).toBe(false);
  });
});

// ── Language audit (source-level static check) ──────────────────────────────
//
// The card is a STRUCTURE read, not a directional or P&L edge. Its source
// MUST NOT contain words that would imply a trade recommendation. Mirrors
// the StructureBrief language audit.

describe('Language audit (source-level)', () => {
  const SINGLE_WORD_DISALLOWED = ['buy', 'sell'];
  const PHRASE_DISALLOWED = [
    'trade signal',
    'trade this',
    'directional edge',
    'buy at',
    'sell at',
  ];

  const path = resolve(__dirname, 'MovementRead.tsx');
  const source = readFileSync(path, 'utf8').toLowerCase();

  it('contains no single-word disallowed term (word-boundary)', () => {
    for (const word of SINGLE_WORD_DISALLOWED) {
      const re = new RegExp(`\\b${word}\\b`, 'i');
      const match = source.match(re);
      expect(match, `disallowed word "${word}" appears: "${match?.[0]}"`).toBeNull();
    }
  });

  it('contains no disallowed multi-word phrase', () => {
    for (const phrase of PHRASE_DISALLOWED) {
      expect(source, `phrase "${phrase}" appears`).not.toContain(phrase);
    }
  });
});
