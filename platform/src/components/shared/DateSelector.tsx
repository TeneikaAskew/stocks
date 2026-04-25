import { useEffect, useState } from 'react';
import { Calendar, X, Radio } from 'lucide-react';
import { useReviewDateStore } from '@/stores/reviewDateStore';

/**
 * Shared date+time selector for "time travel" / historical review mode.
 *
 * UX: the screen does NOT switch to historical mode until the user clicks
 * "Apply". While they're editing, local draft state holds the pending date
 * and time. The Apply button stays disabled until the draft differs from
 * what's already committed to the store.
 *
 * Uses two native inputs (date + time) side by side to avoid the Chrome/Edge
 * datetime-local seconds-slot bug. Time is Eastern Time.
 */
export function DateSelector() {
  const { reviewDate, reviewTime, setReviewDate, setReviewTime, clearReviewDate } = useReviewDateStore();
  const isLive = reviewDate === null;

  // Local draft — only committed on Apply
  const [draftDate, setDraftDate] = useState<string>('');
  const [draftTime, setDraftTime] = useState<string>('16:00');

  // Sync draft when store state changes externally (e.g. clearReviewDate or initial load)
  useEffect(() => {
    setDraftDate(reviewDate ?? '');
    setDraftTime(reviewTime ?? '16:00');
  }, [reviewDate, reviewTime]);

  // Max bounds (no future dates/times)
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  const todayStr = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  // Only clamp time when the drafted date is today — past dates allow any time
  const maxTime = draftDate === todayStr ? `${pad(now.getHours())}:${pad(now.getMinutes())}` : undefined;

  // Apply is enabled when the draft differs from the committed store state
  // AND the draft has at least a date set.
  const draftDiffers =
    draftDate !== (reviewDate ?? '') ||
    (draftDate !== '' && draftTime !== (reviewTime ?? '16:00'));
  const canApply = draftDate !== '' && draftDiffers;

  const handleApply = () => {
    if (!canApply) return;
    setReviewDate(draftDate);
    setReviewTime(draftTime);
  };

  const handleClear = () => {
    clearReviewDate();
    setDraftDate('');
    setDraftTime('16:00');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && canApply) {
      e.preventDefault();
      handleApply();
    }
  };

  return (
    <div
      className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 ${
        isLive
          ? 'border-[var(--color-border)] bg-[var(--color-bg-secondary)]'
          : 'border-amber-500/40 bg-amber-500/10'
      }`}
    >
      {/* Mode icon + label — toggles between live and historical */}
      {isLive ? (
        <>
          <Radio size={14} className="text-[var(--color-brand)] animate-pulse shrink-0" />
          <span className="text-xs font-medium text-[var(--color-text-secondary)]">Live Mode</span>
          <span className="text-xs text-[var(--color-text-muted)]">·</span>
          <span className="text-xs text-[var(--color-text-muted)]">View as of:</span>
        </>
      ) : (
        <>
          <Calendar size={14} className="text-[var(--warn)] shrink-0" />
          <span className="text-xs font-semibold text-[var(--warn)] whitespace-nowrap">HISTORICAL</span>
        </>
      )}

      {/* Date input — draft only, not committed until Apply */}
      <input
        type="date"
        value={draftDate}
        max={todayStr}
        onChange={(e) => setDraftDate(e.target.value)}
        onKeyDown={handleKeyDown}
        className={`rounded border bg-[var(--color-bg-primary)] px-2 py-1 text-xs focus:outline-none ${
          isLive
            ? 'border-[var(--color-border)] text-[var(--color-text-secondary)] focus:border-[var(--color-accent-blue)]'
            : 'border-amber-500/40 text-[var(--warn)] focus:border-amber-400'
        }`}
      />
      {/* Time input — disabled until a draft date is set */}
      <input
        type="time"
        value={draftTime}
        max={maxTime}
        onChange={(e) => setDraftTime(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={draftDate === ''}
        className={`rounded border bg-[var(--color-bg-primary)] px-2 py-1 text-xs focus:outline-none disabled:opacity-40 ${
          isLive
            ? 'border-[var(--color-border)] text-[var(--color-text-secondary)] focus:border-[var(--color-accent-blue)]'
            : 'border-amber-500/40 text-[var(--warn)] focus:border-amber-400'
        }`}
      />
      <span className={`text-[10px] ${isLive ? 'text-[var(--color-text-muted)]' : 'text-[var(--warn)]/70'}`}>ET</span>

      {/* Apply button — blue, commits draft to store */}
      <button
        onClick={handleApply}
        disabled={!canApply}
        className="rounded bg-[var(--brand)] px-3 py-1 text-xs font-semibold text-[var(--on-brand)] hover:bg-[var(--brand-glow)] disabled:opacity-30 disabled:cursor-not-allowed"
        title={canApply ? 'Apply the selected date/time' : 'Enter a date to apply'}
      >
        Apply
      </button>

      {/* "Return to Live" button — only shown in historical mode */}
      {!isLive && (
        <button
          onClick={handleClear}
          className="flex items-center gap-1 rounded bg-amber-500/20 px-2 py-0.5 text-xs font-medium text-[var(--warn)] hover:bg-amber-500/30"
          title="Return to live mode"
        >
          <X size={12} />
          Live
        </button>
      )}
    </div>
  );
}
