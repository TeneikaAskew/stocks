import { useLocation } from 'react-router-dom';
import { useTickerStore } from '@/stores/tickerStore';
import { useReviewDateStore } from '@/stores/reviewDateStore';
import { useLiveStatus } from '@/hooks/useLiveStatus';
import { useLiveQuote } from '@/hooks/useLiveQuote';
import { DateSelector } from '@/components/shared/DateSelector';
import { sessionLabel, sessionPillClasses } from '@/lib/marketSession';

/** Routes where the global historical DateSelector is functional. */
const REVIEW_AWARE_ROUTES = ['/', '/live', '/charts', '/signals'];

export function Header() {
  const { activeTicker } = useTickerStore();
  const { reviewDate } = useReviewDateStore();
  const isReview = reviewDate !== null;
  const { pathname } = useLocation();
  const showDateSelector = REVIEW_AWARE_ROUTES.includes(pathname);

  const { data: status } = useLiveStatus();
  const { data: quote } = useLiveQuote(activeTicker, !isReview);

  const session = status?.session;
  const pill = sessionPillClasses(session);

  return (
    <header className="flex h-14 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-4 gap-3">
      <div className="flex items-center gap-4 min-w-0">
        <span className="text-lg font-bold">{activeTicker}</span>
        {quote && (
          <>
            <span className="text-lg font-mono">${quote.price.toFixed(2)}</span>
            <span
              className={`text-sm font-medium ${
                quote.change >= 0 ? 'text-[var(--color-accent-green)]' : 'text-[var(--color-accent-red)]'
              }`}
            >
              {quote.change >= 0 ? '+' : ''}
              {quote.change.toFixed(2)} ({quote.change_pct.toFixed(2)}%)
            </span>
          </>
        )}
      </div>

      <div className="flex items-center gap-3 shrink-0">
        {showDateSelector && <DateSelector />}
        <div
          className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${pill.pill}`}
        >
          <div className={`h-2 w-2 rounded-full ${pill.dot}`} />
          {sessionLabel(session)}
        </div>
      </div>
    </header>
  );
}
