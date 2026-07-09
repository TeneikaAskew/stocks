import { useCallback, useEffect, useMemo, useState } from 'react';

export type ReplaySpeed = 1 | 5 | 20;

export interface ReplaySessionState {
  active: boolean;
  revealedCount: number;
  playing: boolean;
  speed: ReplaySpeed;
  sessionId: string | null;
}

/** Snapshot returned by `stop()` — the seam Task 5.3's post-session review
 *  reads from. `completed` distinguishes "played through to the last bar"
 *  from "stopped mid-day", which Task 5.3 will render differently. */
export interface ReplaySessionSummary {
  sessionId: string;
  revealedCount: number;
  total: number;
  completed: boolean;
}

/**
 * Bars of warm context revealed the instant a session starts. Chosen so the
 * Strategy Conditions panel's indicators (RSI/EMA/etc — ChartsPage gates
 * those on `chartBars.length >= 14`) have something meaningful to show on
 * the very first frame, without pre-revealing so much of the day that the
 * "trainer" part of bar-by-bar replay is defeated.
 */
export const REPLAY_WARM_START_BARS = 15;

export const REPLAY_IDLE_STATE: ReplaySessionState = {
  active: false,
  revealedCount: 0,
  playing: false,
  speed: 1,
  sessionId: null,
};

// ── Pure reducer helpers ────────────────────────────────────────────────
// Extracted so the reveal boundaries (start/step/pause/never-exceeds/stop)
// are unit-testable without @testing-library/react — this repo's established
// frontend test style (see useDebouncedValue.ts's scheduleDebounce,
// tickerCombobox.test.ts's header comment). Covered in replaySession.test.ts.

export function clampCount(count: number, total: number): number {
  if (total <= 0) return 0;
  return Math.max(0, Math.min(count, total));
}

export function startState(total: number, sessionId: string): ReplaySessionState {
  return {
    active: true,
    revealedCount: clampCount(REPLAY_WARM_START_BARS, total),
    playing: false,
    speed: 1,
    sessionId,
  };
}

/**
 * Advances the reveal by exactly one bar, clamped to `total` — the hard
 * "never exceeds allBars.length" boundary. Auto-pauses (`playing -> false`)
 * the instant the reveal reaches the end, satisfying "auto-pause at end" in
 * the same step as the clamp. Drives BOTH the manual step() action and the
 * playback timer's per-tick advance. No-op when the session isn't active.
 */
export function advanceState(state: ReplaySessionState, total: number): ReplaySessionState {
  if (!state.active) return state;
  const revealedCount = clampCount(state.revealedCount + 1, total);
  const playing = state.playing && revealedCount < total;
  if (revealedCount === state.revealedCount && playing === state.playing) return state;
  return { ...state, revealedCount, playing };
}

/** Resumes playback. No-op if the session isn't active or the reveal has
 *  already reached the end — there's nothing left to auto-advance into. */
export function playState(state: ReplaySessionState, total: number): ReplaySessionState {
  if (!state.active || state.revealedCount >= total) return state;
  return { ...state, playing: true };
}

export function pauseState(state: ReplaySessionState): ReplaySessionState {
  if (!state.playing) return state;
  return { ...state, playing: false };
}

/** Builds the `stop()` snapshot from the state as it stood right before
 *  resetting to idle. `null` when no session ever started (idle state has
 *  no sessionId to attach a summary to). */
export function buildSummary(state: ReplaySessionState, total: number): ReplaySessionSummary | null {
  if (!state.sessionId) return null;
  return {
    sessionId: state.sessionId,
    revealedCount: state.revealedCount,
    total,
    completed: state.revealedCount >= total,
  };
}

// ── Hook ─────────────────────────────────────────────────────────────────

interface TimedBar {
  time: number;
}

export interface UseReplaySessionResult<T extends TimedBar> {
  active: boolean;
  revealedCount: number;
  total: number;
  playing: boolean;
  speed: ReplaySpeed;
  sessionId: string | null;
  /** `allBars.slice(0, revealedCount)` — the ONLY slice of the day's data
   *  anything downstream of this hook should ever see while a session is
   *  active. This is where the leakage-free constraint lives. */
  revealedBars: T[];
  /** Set by `stop()`; cleared by the next `start()`. Feeds Task 5.3's
   *  post-session review. */
  summary: ReplaySessionSummary | null;
  start: () => void;
  play: () => void;
  pause: () => void;
  step: () => void;
  stop: () => void;
  setSpeed: (speed: ReplaySpeed) => void;
}

/**
 * Bar-replay trainer session (Task 5.2). Drives a `revealedCount` cursor
 * over `allBars` bar-by-bar via a `setInterval` timer (one bar every
 * `1000/speed` ms) so ChartsPage can feed the chart / indicators / signal
 * overlay ONLY `revealedBars`, never the full array.
 */
export function useReplaySession<T extends TimedBar>(allBars: T[]): UseReplaySessionResult<T> {
  const [state, setState] = useState<ReplaySessionState>(REPLAY_IDLE_STATE);
  const [summary, setSummary] = useState<ReplaySessionSummary | null>(null);
  const total = allBars.length;

  // Playback timer. Cleaned up on pause/stop/speed-change/unmount via the
  // effect's own cleanup function — never a dangling interval outliving the
  // condition that started it.
  useEffect(() => {
    if (!state.playing) return;
    const id = setInterval(() => {
      setState((s) => advanceState(s, total));
    }, 1000 / state.speed);
    return () => clearInterval(id);
  }, [state.playing, state.speed, total]);

  const start = useCallback(() => {
    setSummary(null);
    setState(startState(total, crypto.randomUUID()));
  }, [total]);

  const play = useCallback(() => {
    setState((s) => playState(s, total));
  }, [total]);

  const pause = useCallback(() => {
    setState((s) => pauseState(s));
  }, []);

  const step = useCallback(() => {
    setState((s) => advanceState(pauseState(s), total));
  }, [total]);

  const stop = useCallback(() => {
    setSummary(buildSummary(state, total));
    setState(REPLAY_IDLE_STATE);
  }, [state, total]);

  const setSpeed = useCallback((speed: ReplaySpeed) => {
    setState((s) => ({ ...s, speed }));
  }, []);

  const revealedBars = useMemo(() => allBars.slice(0, state.revealedCount), [allBars, state.revealedCount]);

  return {
    active: state.active,
    revealedCount: state.revealedCount,
    total,
    playing: state.playing,
    speed: state.speed,
    sessionId: state.sessionId,
    revealedBars,
    summary,
    start,
    play,
    pause,
    step,
    stop,
    setSpeed,
  };
}
