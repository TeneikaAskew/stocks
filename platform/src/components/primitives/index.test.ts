// Vitest unit tests for the shared primitives — currently just <Delta>'s
// text-content logic. Follows the platform's established pure-logic test
// style (no DOM rendering, no @testing-library/react — see
// MovementRead.test.tsx / StructureBrief.test.tsx): the load-bearing
// behavior is extracted into a pure `deltaText` helper so the Rule 3.7
// "never render a fabricated/blank value" contract is testable without
// mounting the component.

import { describe, expect, it } from 'vitest';
import { deltaText } from './index';

const EM_DASH = '—';

describe('deltaText', () => {
  it('renders an em-dash when both value and pct are null (never a blank string)', () => {
    expect(deltaText(null, null)).toBe(EM_DASH);
  });

  it('renders an em-dash when both are undefined', () => {
    expect(deltaText(undefined, undefined)).toBe(EM_DASH);
  });

  it('renders an em-dash when both are NaN', () => {
    expect(deltaText(NaN, NaN)).toBe(EM_DASH);
  });

  it('renders an em-dash when called with no arguments at all', () => {
    expect(deltaText()).toBe(EM_DASH);
  });

  it('renders the value only when pct is null', () => {
    expect(deltaText(1.234, null)).toBe('+1.23');
  });

  it('renders the pct only when value is null', () => {
    expect(deltaText(null, -2.5)).toBe('-2.50%');
  });

  it('renders value + parenthesized pct when both are present, sharing one sign', () => {
    expect(deltaText(1.2, 0.5)).toBe('+1.20 (+0.50%)');
  });

  it('applies a prefix only to the value portion', () => {
    expect(deltaText(1.5, 2.0, '$')).toBe('$+1.50 (+2.00%)');
  });

  it('a negative basis renders a bare "-" sign, never "+-"', () => {
    expect(deltaText(-3.1, -1.2)).toBe('-3.10 (-1.20%)');
  });
});
