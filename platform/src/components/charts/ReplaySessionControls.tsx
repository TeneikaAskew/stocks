import { History, Pause, Play, SkipForward, Square } from 'lucide-react';
import type { ReplaySpeed } from '@/hooks/useReplaySession';

const SPEEDS: ReplaySpeed[] = [1, 5, 20];

interface ReplaySessionControlsProps {
  active: boolean;
  playing: boolean;
  speed: ReplaySpeed;
  revealedCount: number;
  total: number;
  onStart: () => void;
  onPlay: () => void;
  onPause: () => void;
  onStep: () => void;
  onStop: () => void;
  onSpeedChange: (speed: ReplaySpeed) => void;
}

/**
 * Bar-replay trainer session controls (Task 5.2) — joins the /charts toolbar
 * row beside the timeframe buttons and view toggles. Idle state is a single
 * "Start replay" button; once active, swaps to play/pause + step + a speed
 * segmented control + stop + a revealedCount/total readout.
 *
 * Purely presentational — all reveal-boundary logic (start/step/pause/
 * never-exceeds/auto-pause/stop) lives in useReplaySession + its pure
 * reducer helpers (replaySession.test.ts).
 */
export function ReplaySessionControls({
  active,
  playing,
  speed,
  revealedCount,
  total,
  onStart,
  onPlay,
  onPause,
  onStep,
  onStop,
  onSpeedChange,
}: ReplaySessionControlsProps) {
  if (!active) {
    return (
      <button
        onClick={onStart}
        disabled={total === 0}
        data-testid="replay-start-btn"
        title={total === 0 ? 'Load a trading day before starting a replay' : 'Start bar-replay trainer session'}
        className="flex items-center gap-1 rounded px-2 py-1.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)] disabled:cursor-not-allowed disabled:opacity-40"
      >
        <History size={14} />
        Start replay
      </button>
    );
  }

  const atEnd = revealedCount >= total;

  return (
    <div
      data-testid="replay-controls"
      className="flex items-center gap-1 rounded border border-[var(--color-border)] px-1 py-0.5"
    >
      <button
        onClick={playing ? onPause : onPlay}
        disabled={!playing && atEnd}
        title={playing ? 'Pause replay' : 'Play replay'}
        data-testid="replay-play-pause-btn"
        className="flex items-center rounded px-1.5 py-1 text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)] disabled:cursor-not-allowed disabled:opacity-40"
      >
        {playing ? <Pause size={14} /> : <Play size={14} />}
      </button>

      <button
        onClick={onStep}
        disabled={atEnd}
        title="Step one bar"
        data-testid="replay-step-btn"
        className="flex items-center rounded px-1.5 py-1 text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)] disabled:cursor-not-allowed disabled:opacity-40"
      >
        <SkipForward size={14} />
      </button>

      <div className="flex rounded border border-[var(--color-border)]">
        {SPEEDS.map((s) => (
          <button
            key={s}
            onClick={() => onSpeedChange(s)}
            data-testid={`replay-speed-${s}x`}
            title={`${s}x speed`}
            className={`px-1.5 py-1 text-xs font-medium transition-colors ${
              speed === s
                ? 'bg-[var(--color-accent-blue)] text-[var(--on-brand)]'
                : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]'
            }`}
          >
            {s}x
          </button>
        ))}
      </div>

      <button
        onClick={onStop}
        title="Stop replay"
        data-testid="replay-stop-btn"
        className="flex items-center rounded px-1.5 py-1 text-[var(--color-accent-red)] hover:bg-[var(--color-bg-hover)]"
      >
        <Square size={14} />
      </button>

      <span data-testid="replay-revealed-count" className="px-1 text-xs text-[var(--color-text-muted)]">
        {revealedCount}/{total}
      </span>
    </div>
  );
}
