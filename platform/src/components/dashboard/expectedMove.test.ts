import { describe, it, expect } from 'vitest';
import {
  sizeLight,
  bucketToAtrLabel,
  riskHint,
  showOptionsIdea,
  sizeCalc,
} from './expectedMove';

describe('sizeLight', () => {
  it('green at/above 0.20', () => {
    expect(sizeLight(0.2).level).toBe('big');
    expect(sizeLight(0.35).tone).toBe('green');
  });
  it('amber in [0.10, 0.20)', () => {
    expect(sizeLight(0.1).level).toBe('elevated');
    expect(sizeLight(0.19).tone).toBe('amber');
  });
  it('red below 0.10', () => {
    expect(sizeLight(0.06).level).toBe('tight');
    expect(sizeLight(0.0).tone).toBe('red');
  });
  it('unknown on null (never fabricated)', () => {
    expect(sizeLight(null).level).toBe('unknown');
    expect(sizeLight(undefined).tone).toBe('muted');
  });
});

describe('bucketToAtrLabel', () => {
  it('maps each bucket to its ATR range', () => {
    expect(bucketToAtrLabel('TIGHT')).toBe('≈ < 0.5× ATR');
    expect(bucketToAtrLabel('NORMAL')).toBe('≈ 0.5–1.0× ATR');
    expect(bucketToAtrLabel('EXPANDED')).toBe('≈ 1.0–1.5× ATR');
    expect(bucketToAtrLabel('EXPLOSIVE')).toBe('≈ ≥ 1.5× ATR');
    expect(bucketToAtrLabel(null)).toBe('—');
  });
});

describe('riskHint', () => {
  it('warns on big buckets, quiet on tight, silent on normal', () => {
    expect(riskHint('EXPANDED')).toMatch(/wider stops/);
    expect(riskHint('EXPLOSIVE')).toMatch(/wider stops/);
    expect(riskHint('TIGHT')).toMatch(/tighter stops/);
    expect(riskHint('NORMAL')).toBeNull();
    expect(riskHint(null)).toBeNull();
  });
});

describe('showOptionsIdea', () => {
  it('true only when p_explosive >= 0.10', () => {
    expect(showOptionsIdea(0.1)).toBe(true);
    expect(showOptionsIdea(0.09)).toBe(false);
    expect(showOptionsIdea(null)).toBe(false);
  });
});

describe('sizeCalc', () => {
  it('stop = k*ATR and shares = floor(risk$/stop)', () => {
    const r = sizeCalc({ sizeClass: 'EXPANDED', atr20: 2, account: 10000, riskPct: 1 });
    expect(r).not.toBeNull();
    expect(r!.stop).toBeCloseTo(3.0, 6);
    expect(r!.shares).toBe(33);
  });
  it('EXPLOSIVE uses capped k=2.0', () => {
    const r = sizeCalc({ sizeClass: 'EXPLOSIVE', atr20: 1, account: 1000, riskPct: 2 });
    expect(r!.stop).toBeCloseTo(2.0, 6);
    expect(r!.shares).toBe(10);
  });
  it('disabled (null) when ATR missing or inputs invalid', () => {
    expect(sizeCalc({ sizeClass: 'EXPANDED', atr20: null, account: 1000, riskPct: 1 })).toBeNull();
    expect(sizeCalc({ sizeClass: 'EXPANDED', atr20: 2, account: 0, riskPct: 1 })).toBeNull();
    expect(sizeCalc({ sizeClass: null, atr20: 2, account: 1000, riskPct: 1 })).toBeNull();
  });
});
