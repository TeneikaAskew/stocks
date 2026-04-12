import { Calendar, X, Radio } from 'lucide-react';
import { useReviewDateStore } from '@/stores/reviewDateStore';

/**
 * Shared date+time selector for "time travel" / historical review mode.
 * Uses a single datetime-local input (always mounted) so the browser's native
 * picker stays alive across state transitions. Time is Eastern Time.
 */
export function DateSelector() {
  const { reviewDate, reviewTime, setReviewDate, setReviewTime, clearReviewDate } = useReviewDateStore();
  const isLive = reviewDate === null;

  // Combined value for datetime-local input: "YYYY-MM-DDTHH:MM" (empty when live)
  const combinedValue = isLive ? '' : `${reviewDate}T${reviewTime ?? '16:00'}`;

  // Max = today + current time (no future)
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  const maxValue = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;

  const handleChange = (value: string) => {
    if (!value) {
      clearReviewDate();
      return;
    }
    const [datePart, timePart] = value.split('T');
    setReviewDate(datePart);
    setReviewTime(timePart || null);
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
          <Radio size={14} className="text-green-400 animate-pulse shrink-0" />
          <span className="text-xs font-medium text-[var(--color-text-secondary)]">Live Mode</span>
          <span className="text-xs text-[var(--color-text-muted)]">·</span>
          <span className="text-xs text-[var(--color-text-muted)]">View as of:</span>
        </>
      ) : (
        <>
          <Calendar size={14} className="text-amber-400 shrink-0" />
          <span className="text-xs font-semibold text-amber-400 whitespace-nowrap">HISTORICAL</span>
        </>
      )}

      {/* Single datetime-local input — always mounted so the picker isn't torn down mid-interaction */}
      <input
        type="datetime-local"
        value={combinedValue}
        max={maxValue}
        step={60}
        onChange={(e) => handleChange(e.target.value)}
        className={`min-w-[200px] rounded border bg-[var(--color-bg-primary)] px-2 py-1 text-xs focus:outline-none ${
          isLive
            ? 'border-[var(--color-border)] text-[var(--color-text-secondary)] focus:border-[var(--color-accent-blue)]'
            : 'border-amber-500/40 text-amber-300 focus:border-amber-400'
        }`}
      />
      <span className={`text-[10px] ${isLive ? 'text-[var(--color-text-muted)]' : 'text-amber-400/70'}`}>ET</span>

      {/* "Return to Live" button — only shown in historical mode */}
      {!isLive && (
        <button
          onClick={clearReviewDate}
          className="flex items-center gap-1 rounded bg-amber-500/20 px-2 py-0.5 text-xs font-medium text-amber-300 hover:bg-amber-500/30"
          title="Return to live mode"
        >
          <X size={12} />
          Live
        </button>
      )}
    </div>
  );
}
