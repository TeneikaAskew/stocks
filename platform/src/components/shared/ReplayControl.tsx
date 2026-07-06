import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Calendar as CalendarIcon, ChevronDown, ChevronLeft, ChevronRight, History, X } from 'lucide-react';
import { Calendar, TimeField } from '@heroui/react';
import { CalendarDate, Time, getDayOfWeek, parseDate, today } from '@internationalized/date';
import { useReviewDateStore } from '@/stores/reviewDateStore';

/** Routes where historical replay is functional. */
const REPLAY_ROUTES = ['/dashboard', '/live', '/charts', '/signals'];

const ET = 'America/New_York';
const MARKET_CLOSE = new Time(16, 0);

const pad = (n: number) => String(n).padStart(2, '0');

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

function fmtHeading(date: CalendarDate): string {
  return date.toDate(ET).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });
}

/** Most recent weekday on/before `d` (holidays are handled by the grid, not here). */
function latestWeekday(d: CalendarDate): CalendarDate {
  let cur = d;
  while (getDayOfWeek(cur, 'en-US') === 0 || getDayOfWeek(cur, 'en-US') === 6) {
    cur = cur.subtract({ days: 1 });
  }
  return cur;
}

/** Market holidays (dates with no session) — used to gray out calendar days. */
function useMarketHolidays(): Set<string> {
  const { data } = useQuery<{ holidays_2026?: string[] }>({
    queryKey: ['market-hours'],
    queryFn: async () => {
      const r = await fetch('/api/config/market-hours');
      if (!r.ok) throw new Error(`market-hours ${r.status}`);
      return r.json();
    },
    staleTime: 24 * 60 * 60 * 1000,
  });
  return new Set(data?.holidays_2026 ?? []);
}

/**
 * Compact replay ("time travel") control for the top bar. Live state is a
 * quiet "Replay" button (the Market chip already tells the session story);
 * active replay is an amber chip showing the pinned moment with an inline
 * ✕ back-to-live. The popover is a TradingView-style picker: a VISUAL
 * calendar (weekends, market holidays, and future dates disabled) plus a
 * segmented time field — nothing is typed free-form. Draft-only until
 * Apply, so the screen never flips modes mid-edit. Times are Eastern.
 */
export function ReplayControl() {
  const { pathname } = useLocation();
  const { reviewDate, reviewTime, setReviewDate, setReviewTime, clearReviewDate } = useReviewDateStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const holidays = useMarketHolidays();
  const isLive = reviewDate === null;

  // Draft follows the committed store value when it changes externally —
  // render-time state adjustment (no effect → no cascading-render lint).
  const committed = reviewDate ? `${reviewDate}T${reviewTime ?? '16:00'}` : '';
  const [lastCommitted, setLastCommitted] = useState(committed);
  const [draftDate, setDraftDate] = useState<CalendarDate | null>(reviewDate ? parseDate(reviewDate) : null);
  const [draftTime, setDraftTime] = useState<Time>(
    reviewTime ? new Time(Number(reviewTime.slice(0, 2)), Number(reviewTime.slice(3, 5))) : MARKET_CLOSE,
  );
  if (committed !== lastCommitted) {
    setLastCommitted(committed);
    setDraftDate(reviewDate ? parseDate(reviewDate) : null);
    setDraftTime(
      reviewTime ? new Time(Number(reviewTime.slice(0, 2)), Number(reviewTime.slice(3, 5))) : MARKET_CLOSE,
    );
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

  const todayET = today(ET);
  const isDateUnavailable = (d: CalendarDate) => {
    const dow = getDayOfWeek(d, 'en-US');
    return dow === 0 || dow === 6 || holidays.has(d.toString());
  };

  const draftStr = draftDate ? `${draftDate.toString()}T${pad(draftTime.hour)}:${pad(draftTime.minute)}` : '';
  const canApply = draftStr !== '' && draftStr !== committed;

  const apply = () => {
    if (!canApply || !draftDate) return;
    setReviewDate(draftDate.toString());
    setReviewTime(`${pad(draftTime.hour)}:${pad(draftTime.minute)}`);
    setOpen(false);
  };

  const cancel = () => {
    setDraftDate(reviewDate ? parseDate(reviewDate) : null);
    setDraftTime(
      reviewTime ? new Time(Number(reviewTime.slice(0, 2)), Number(reviewTime.slice(3, 5))) : MARKET_CLOSE,
    );
    setOpen(false);
  };

  const clear = () => {
    clearReviewDate();
    setOpen(false);
  };

  const jumpLatestSession = () => {
    setDraftDate(latestWeekday(todayET));
    setDraftTime(MARKET_CLOSE);
  };

  return (
    <div ref={ref} className="relative shrink-0">
      <div
        className={`flex items-center gap-1 rounded-lg border px-1 py-0.5 ${
          isLive ? 'border-transparent' : 'border-amber-500/40 bg-amber-500/10'
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
          {isLive ? <History size={13} /> : <CalendarIcon size={13} />}
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
        <div className="absolute right-0 top-full z-50 mt-2 w-80 overflow-hidden rounded-xl border border-[var(--surface-3)] bg-[var(--surface-1)] shadow-2xl">
          {/* Selected-moment header (TradingView style) */}
          <div className="bg-[var(--brand)] px-4 py-3 text-[var(--on-brand)]">
            <div className="text-[11px] font-medium opacity-80">{draftDate ? draftDate.year : 'Replay'}</div>
            <div className="text-lg font-bold leading-tight">
              {draftDate ? fmtHeading(draftDate) : 'Pick a session'}
            </div>
          </div>

          <div className="p-3">
            <Calendar
              aria-label="Replay date"
              value={draftDate}
              onChange={(d) => setDraftDate(d as CalendarDate)}
              maxValue={todayET}
              isDateUnavailable={(d) => isDateUnavailable(d as CalendarDate)}
            >
              {/* w-full + justify-between + flex-1 centered heading: HeroUI's
                  default header clusters the heading beside the left chevron. */}
              <Calendar.Header className="flex w-full items-center justify-between">
                <Calendar.NavButton slot="previous">
                  <ChevronLeft size={15} />
                </Calendar.NavButton>
                <Calendar.Heading className="flex-1 text-center" />
                <Calendar.NavButton slot="next">
                  <ChevronRight size={15} />
                </Calendar.NavButton>
              </Calendar.Header>
              <Calendar.Grid>
                <Calendar.GridHeader>
                  {(day) => <Calendar.HeaderCell>{day}</Calendar.HeaderCell>}
                </Calendar.GridHeader>
                <Calendar.GridBody>
                  {(date) => <Calendar.Cell date={date} />}
                </Calendar.GridBody>
              </Calendar.Grid>
            </Calendar>

            <button
              type="button"
              onClick={jumpLatestSession}
              className="mt-1 text-xs font-medium text-[var(--brand)] hover:underline"
            >
              Latest session close
            </button>

            {/* Time row */}
            <div className="mt-2 flex items-center justify-between border-t border-[var(--outline-variant)] pt-2.5">
              <span className="text-xs text-[var(--on-surface-variant)]">Time (ET)</span>
              <TimeField
                aria-label="Replay time"
                value={draftTime}
                onChange={(t) => t && setDraftTime(t as Time)}
                hourCycle={12}
              >
                <TimeField.Group>
                  <TimeField.InputContainer>
                    <TimeField.Input>
                      {(segment) => <TimeField.Segment segment={segment} />}
                    </TimeField.Input>
                  </TimeField.InputContainer>
                </TimeField.Group>
              </TimeField>
            </div>

            {/* Footer */}
            <div className="mt-3 flex items-center justify-end gap-2">
              {!isLive && (
                <button
                  type="button"
                  onClick={clear}
                  className="mr-auto rounded px-2.5 py-1 text-xs font-medium text-[var(--warn)] hover:bg-amber-500/15"
                >
                  Back to live
                </button>
              )}
              <button
                type="button"
                onClick={cancel}
                className="rounded px-2.5 py-1 text-xs font-medium text-[var(--on-surface-variant)] hover:bg-[var(--surface-2)]"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={apply}
                disabled={!canApply}
                data-testid="replay-apply"
                className="rounded bg-[var(--brand)] px-3.5 py-1 text-xs font-semibold text-[var(--on-brand)] hover:bg-[var(--brand-glow)] disabled:cursor-not-allowed disabled:opacity-30"
              >
                OK
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
