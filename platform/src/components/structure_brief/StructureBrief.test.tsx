/// <reference types="node" />
// Vitest unit tests for the Structure Brief.
//
// Two responsibilities tested:
//   1. Mute logic — when live ECE exceeds the cell's ceiling, the
//      prediction is hidden and a mute reason is produced. Tested as a
//      pure function (`decideMute`, `applyMute`).
//   2. Scope statement — the verbatim language constant matches the
//      spec character-for-character, and is free of disallowed words.
//
// Tests follow the existing pure-logic style of the platform's other
// test files (no DOM rendering, no @testing-library/react). The
// language-audit test reads the brief's source file and asserts no
// disallowed word appears anywhere in it.

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';
import {
  decideMute,
  applyMute,
  SCOPE_STATEMENT,
  BANNED_WORDS,
} from './StructureBrief';
import type { StructureBriefCell } from '@/hooks/useAdmin';


function buildCell(overrides: Partial<StructureBriefCell> = {}): StructureBriefCell {
  return {
    ticker: 'IWM',
    timeframe: '15m',
    available: true,
    top_class: '2U',
    top_prob: 0.62,
    distribution: [
      { cls: '1', prob: 0.10 },
      { cls: '2U', prob: 0.62 },
      { cls: '2D', prob: 0.23 },
      { cls: '3', prob: 0.05 },
    ],
    live_ece: 0.025,
    ece_ceiling: 0.05,
    muted: false,
    mute_reason: null,
    refreshed_at: '2026-05-27T13:00:00Z',
    note: null,
    ...overrides,
  };
}


// ── 1. SCOPE STATEMENT ─────────────────────────────────────────────────────

describe('SCOPE_STATEMENT', () => {
  it('matches the spec verbatim', () => {
    expect(SCOPE_STATEMENT).toBe(
      'Calibrated structure prediction. Not a directional or P&L edge. Use with discretion.'
    );
  });

  it('contains no disallowed term', () => {
    const lower = SCOPE_STATEMENT.toLowerCase();
    for (const word of BANNED_WORDS) {
      expect(lower).not.toContain(word.toLowerCase());
    }
  });
});


// ── 2. MUTE LOGIC ──────────────────────────────────────────────────────────

describe('decideMute', () => {
  it('does not mute when live ECE is within ceiling', () => {
    const d = decideMute(0.025, 0.05);
    expect(d.muted).toBe(false);
    expect(d.reason).toBeNull();
  });

  it('does not mute when live ECE exactly equals ceiling', () => {
    const d = decideMute(0.05, 0.05);
    expect(d.muted).toBe(false);
  });

  it('mutes when live ECE strictly exceeds ceiling', () => {
    const d = decideMute(0.07, 0.05);
    expect(d.muted).toBe(true);
    expect(d.reason).toContain('model muted, ECE breach');
    expect(d.reason).toContain('0.070');
    expect(d.reason).toContain('0.050');
  });

  it('does not mute when live ECE is null (no reading yet)', () => {
    const d = decideMute(null, 0.05);
    expect(d.muted).toBe(false);
    expect(d.reason).toBeNull();
  });

  it('does not mute when live ECE is undefined', () => {
    const d = decideMute(undefined, 0.05);
    expect(d.muted).toBe(false);
  });
});

describe('applyMute', () => {
  it('passes through unchanged when ECE is in band', () => {
    const cell = buildCell({ live_ece: 0.03, ece_ceiling: 0.05 });
    const out = applyMute(cell);
    expect(out.muted).toBe(false);
    expect(out.top_class).toBe('2U');
    expect(out.top_prob).toBeCloseTo(0.62);
    expect(out.distribution).toHaveLength(4);
  });

  it('strips top_class, top_prob, and distribution when muted', () => {
    const cell = buildCell({ live_ece: 0.08, ece_ceiling: 0.05 });
    const out = applyMute(cell);
    expect(out.muted).toBe(true);
    expect(out.top_class).toBeNull();
    expect(out.top_prob).toBeNull();
    expect(out.distribution).toEqual([]);
    expect(out.mute_reason).toContain('model muted, ECE breach');
  });

  it('preserves a server-supplied mute reason if present', () => {
    const cell = buildCell({
      live_ece: 0.08,
      ece_ceiling: 0.05,
      mute_reason: 'server-side reason',
    });
    const out = applyMute(cell);
    expect(out.muted).toBe(true);
    expect(out.mute_reason).toBe('server-side reason');
  });

  it('does not mute when live_ece is null even if other fields suggest mute', () => {
    const cell = buildCell({ live_ece: null });
    const out = applyMute(cell);
    expect(out.muted).toBe(false);
    expect(out.top_class).toBe('2U');
  });
});


// ── 3. LANGUAGE AUDIT (source-level static check) ──────────────────────────
//
// The brief's source MUST NOT contain any disallowed word. This static
// scan covers the whole component file — strings, comments, JSX
// labels. The BANNED_WORDS literal itself is excluded from the scan
// (the list must enumerate the disallowed words for the audit to work).

describe('Language audit (source-level)', () => {
  const filesToAudit = [
    'StructureBrief.tsx',
  ];

  const SINGLE_WORD_DISALLOWED = [
    'entry',
    'buy',
    'sell',
  ];
  const PHRASE_DISALLOWED = [
    'trade signal',
    'trade this',
    'predicts upside',
    'predicts downside',
    'buy at',
    'sell at',
    'directional edge',
  ];

  for (const fname of filesToAudit) {
    const path = resolve(__dirname, fname);
    const source = readFileSync(path, 'utf8');

    // Strip (a) the BANNED_WORDS list literal — the list must enumerate
    // the disallowed words for the audit to work — and (b) any line
    // mentioning the audit by name (comments documenting it are OK).
    const lines = source.split('\n');
    let inBannedList = false;
    const kept: string[] = [];
    for (const line of lines) {
      if (/export\s+const\s+BANNED_WORDS/.test(line)) {
        inBannedList = true;
        continue;
      }
      if (inBannedList) {
        if (/^\s*\];?\s*$/.test(line)) {
          inBannedList = false;
        }
        continue;
      }
      // Lines that mention the audit are allowed to use the audit term.
      if (line.toLowerCase().includes('disallowed')) continue;
      if (line.toLowerCase().includes('banned')) continue;
      kept.push(line);
    }
    const auditableLines = kept.join('\n').toLowerCase();

    it(`${fname}: no single-word disallowed term (word-boundary)`, () => {
      for (const word of SINGLE_WORD_DISALLOWED) {
        const re = new RegExp(`\\b${word}`, 'i');
        const match = auditableLines.match(re);
        expect(match, `disallowed word "${word}" appears in ${fname}: "${match?.[0]}"`).toBeNull();
      }
    });

    it(`${fname}: no disallowed multi-word phrase`, () => {
      for (const phrase of PHRASE_DISALLOWED) {
        expect(auditableLines, `phrase "${phrase}" appears in ${fname}`).not.toContain(phrase.toLowerCase());
      }
    });
  }
});
