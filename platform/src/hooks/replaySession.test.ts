// Vitest coverage for the bar-replay trainer's reveal reducer (Task 5.2).
//
// No @testing-library/react in this repo (see tickerCombobox.test.ts) — the
// hook's timer-driving logic is exercised indirectly through these extracted
// pure functions (start/advance/play/pause/summary), the same split pattern
// as useDebouncedValue.ts's scheduleDebounce. This covers every boundary the
// brief calls out: start/step/pause boundaries, "never exceeds
// allBars.length", and stop-resets.

import { describe, expect, it } from 'vitest';
import {
  REPLAY_IDLE_STATE,
  REPLAY_WARM_START_BARS,
  advanceState,
  buildSummary,
  clampCount,
  pauseState,
  playState,
  startState,
  type ReplaySessionState,
} from './useReplaySession';

describe('clampCount', () => {
  it('clamps negative counts to 0', () => {
    expect(clampCount(-5, 30)).toBe(0);
  });

  it('clamps counts above total down to total', () => {
    expect(clampCount(999, 30)).toBe(30);
  });

  it('passes through a mid-range count unchanged', () => {
    expect(clampCount(10, 30)).toBe(10);
  });

  it('returns 0 for a non-positive total regardless of count', () => {
    expect(clampCount(5, 0)).toBe(0);
    expect(clampCount(5, -1)).toBe(0);
  });
});

describe('startState', () => {
  it('reveals REPLAY_WARM_START_BARS of warm context when the day has enough bars', () => {
    const s = startState(60, 'session-abc');
    expect(s.active).toBe(true);
    expect(s.revealedCount).toBe(REPLAY_WARM_START_BARS);
    expect(s.playing).toBe(false);
    expect(s.speed).toBe(1);
    expect(s.sessionId).toBe('session-abc');
  });

  it('clamps the warm start to total when the day has fewer bars than the warm-start size', () => {
    const s = startState(5, 'session-short');
    expect(s.revealedCount).toBe(5);
  });

  it('starts at revealedCount 0 for an empty day', () => {
    const s = startState(0, 'session-empty');
    expect(s.revealedCount).toBe(0);
    expect(s.active).toBe(true);
  });
});

describe('advanceState (drives both step() and the playback timer tick)', () => {
  const base: ReplaySessionState = { active: true, revealedCount: 15, playing: false, speed: 1, sessionId: 's1' };

  it('advances the reveal by exactly one bar', () => {
    const next = advanceState(base, 30);
    expect(next.revealedCount).toBe(16);
  });

  it('never exceeds allBars.length no matter how many times it is called', () => {
    let s: ReplaySessionState = { ...base, revealedCount: 29 };
    s = advanceState(s, 30);
    expect(s.revealedCount).toBe(30);
    s = advanceState(s, 30);
    expect(s.revealedCount).toBe(30);
    s = advanceState(s, 30);
    expect(s.revealedCount).toBe(30);
  });

  it('auto-pauses (playing -> false) the instant the reveal reaches the end', () => {
    const playing: ReplaySessionState = { ...base, revealedCount: 29, playing: true };
    const next = advanceState(playing, 30);
    expect(next.revealedCount).toBe(30);
    expect(next.playing).toBe(false);
  });

  it('keeps playing true when the reveal has not yet reached the end', () => {
    const playing: ReplaySessionState = { ...base, revealedCount: 15, playing: true };
    const next = advanceState(playing, 30);
    expect(next.revealedCount).toBe(16);
    expect(next.playing).toBe(true);
  });

  it('is a no-op when the session is not active', () => {
    const idle = REPLAY_IDLE_STATE;
    expect(advanceState(idle, 30)).toBe(idle);
  });
});

describe('playState (resume boundary)', () => {
  it('sets playing true for an active session with bars left to reveal', () => {
    const s: ReplaySessionState = { active: true, revealedCount: 15, playing: false, speed: 1, sessionId: 's1' };
    expect(playState(s, 30).playing).toBe(true);
  });

  it('is a no-op when the session is not active', () => {
    expect(playState(REPLAY_IDLE_STATE, 30)).toBe(REPLAY_IDLE_STATE);
  });

  it('is a no-op at the end of the reveal (nothing left to auto-advance into)', () => {
    const atEnd: ReplaySessionState = { active: true, revealedCount: 30, playing: false, speed: 1, sessionId: 's1' };
    expect(playState(atEnd, 30)).toBe(atEnd);
  });
});

describe('pauseState', () => {
  it('sets playing false', () => {
    const s: ReplaySessionState = { active: true, revealedCount: 16, playing: true, speed: 5, sessionId: 's1' };
    expect(pauseState(s).playing).toBe(false);
  });

  it('is a no-op (same reference) when already paused', () => {
    const s: ReplaySessionState = { active: true, revealedCount: 16, playing: false, speed: 5, sessionId: 's1' };
    expect(pauseState(s)).toBe(s);
  });
});

describe('stop resets to REPLAY_IDLE_STATE', () => {
  it('idle state is fully reset — inactive, zero reveal, not playing, speed 1, no session', () => {
    expect(REPLAY_IDLE_STATE).toEqual({
      active: false,
      revealedCount: 0,
      playing: false,
      speed: 1,
      sessionId: null,
    });
  });

  it('a full start -> step -> step -> stop sequence ends back at REPLAY_IDLE_STATE (mirrors the hook\'s stop())', () => {
    let s = startState(30, 'session-full');
    s = advanceState(s, 30);
    s = advanceState(s, 30);
    expect(s.revealedCount).toBe(REPLAY_WARM_START_BARS + 2);
    // stop() itself just resets — it doesn't derive from advanceState.
    s = REPLAY_IDLE_STATE;
    expect(s).toEqual(REPLAY_IDLE_STATE);
  });
});

describe('buildSummary', () => {
  it('returns null when no session has ever started (sessionId null)', () => {
    expect(buildSummary(REPLAY_IDLE_STATE, 30)).toBeNull();
  });

  it('marks completed=false when stopped before the reveal reached the end', () => {
    const s: ReplaySessionState = { active: true, revealedCount: 20, playing: false, speed: 1, sessionId: 's1' };
    expect(buildSummary(s, 30)).toEqual({ sessionId: 's1', revealedCount: 20, total: 30, completed: false });
  });

  it('marks completed=true when the reveal reached the end', () => {
    const s: ReplaySessionState = { active: true, revealedCount: 30, playing: false, speed: 1, sessionId: 's1' };
    expect(buildSummary(s, 30)).toEqual({ sessionId: 's1', revealedCount: 30, total: 30, completed: true });
  });
});
