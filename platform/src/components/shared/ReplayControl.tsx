import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Calendar, ChevronDown, History, X } from 'lucide-react';
import { useReviewDateStore } from '@/stores/reviewDateStore';

/** Routes where historical replay is functional. */
const REPLAY_ROUTES = ['/dashboard', '/live', '/charts', '/signals'];

function fmtReplay(date: string, time: string): string {
  const d = new Date(`${date}T${time}`);
  if (Number.isNaN(d.getTime())) return `${date} ${time}`;
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

/**
 * Compact replay ("time travel") control for the top bar. Replaces the old
 * two-input Live-Mode/DateSelector row: live state is a quiet "Replay"
 * button (the Market chip already tells the session story); active replay
 * is an amber chip showing the pinned moment with an inline ✕ back-to-live.
 * The popover holds ONE datetime-local input (step=60 keeps the seconds
 * slot away) — draft-only until Apply, so the screen never flips modes
 * mid-edit. Times are Eastern.
 */
export function ReplayControl() {
  const { pathname } = useLocation();
  const { reviewDate, reviewTime, setReviewDate, setReviewTime, clearReviewDate } = useReviewDateStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const isLive = reviewDate === null;

  // Draft follows the committed store value when it changes externally —
  // render-time state adjustment (no effect → no cascading-render lint).
  const committed = reviewDate ? `${reviewDate}T${reviewTime ?? '16:00'}` : '';
  const [lastCommitted, setLastCommitted] = useState(committed);
  const [draft, setDraft] = useState(committed);
  if (committed !== lastCommitted) {
    setLastCommitted(committed);
    setDraft(committed);
  }

  // Outside click / Escape closes the popover.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!REPLAY_ROUTES.includes(pathname)) return null;

  // No future moments.
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  const maxLocal = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;

  const canApply = draft !== '' && draft !== committed;

  const apply = () => {
    if (!canApply) return;
    const [d, t] = draft.split('T');
    if (!d || !t) return;
    setReviewDate(d);
    setReviewTime(t.slice(0, 5));
    setOpen(false);
  };

  const clear = () => {
    clearReviewDate();
    setDraft('');
    setOpen(false);
  };

  return (
    <div ref={ref} className="relative shrink-0">
      <div
        className={`flex items-center gap-1 rounded-lg border px-1 py-0.5 ${
          isLive
            ? 'border-transparent'
            : 'border-amber-500/40 bg-amber-500/10'
        }`}
      >
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-haspopup="dialog"
          data-testid="replay-toggle"
          title="Replay a past session (view as of a date/time)"
          className={`flex items-center gap-1.5 rounded px-1.5 py-1 text-xs transition-colors ${
            isLive
              ? 'text-[var(--on-surface-variant)] hover:bg-[var(--surface-2)] hover:text-[var(--on-surface)]'
              : 'font-semibold text-[var(--warn)]'
          }`}
        >
          {isLive ? <History size={13} /> : <Calendar size={13} />}
          <span className="whitespace-nowrap">
            {isLive ? 'Replay' : `Replay · ${fmtReplay(reviewDate, reviewTime ?? '16:00')}`}
          </span>
          <ChevronDown size={11} className={`transition-transform${open ? ' rotate-180' : ''}`} />
        </button>
        {!isLive && (
          <button
            type="button"
            onClick={clear}
            aria-label="Back to live"
            title="Back to live"
            data-testid="replay-clear"
            className="rounded p-1 text-[var(--warn)] hover:bg-amber-500/20"
          >
            <X size={12} />
          </button>
        )}
      </div>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-72 rounded-xl border border-[var(--surface-3)] bg-[var(--surface-1)] p-3 shadow-2xl">
          <label className="text-[11px] font-medium uppercase tracking-wide text-[var(--on-surface-muted)]">
            Replay as of (ET)
          </label>
          <input
            type="datetime-local"
            step={60}
            value={draft}
            max={maxLocal}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && canApply) {
                e.preventDefault();
                apply();
              }
            }}
            data-testid="replay-datetime"
            className="mt-1.5 w-full rounded border border-[var(--outline-variant)] bg-[var(--surface-lowest)] px-2 py-1.5 text-xs text-[var(--on-surface)] focus:border-[var(--brand)] focus:outline-none"
          />
          <div className="mt-2.5 flex items-center justify-end gap-2">
            {!isLive && (
              <button
                type="button"
                onClick={clear}
                className="rounded px-2.5 py-1 text-xs font-medium text-[var(--warn)] hover:bg-amber-500/15"
              >
                Back to live
              </button>
            )}
            <button
              type="button"
              onClick={apply}
              disabled={!canApply}
              data-testid="replay-apply"
              className="rounded bg-[var(--brand)] px-3 py-1 text-xs font-semibold text-[var(--on-brand)] hover:bg-[var(--brand-glow)] disabled:cursor-not-allowed disabled:opacity-30"
            >
              Apply
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
