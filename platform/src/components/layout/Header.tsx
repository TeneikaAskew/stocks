import { Moon, Sun } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { useTickerStore } from '@/stores/tickerStore';
import { useReviewDateStore } from '@/stores/reviewDateStore';
import { useThemeStore } from '@/stores/themeStore';
import { useLiveQuote } from '@/hooks/useLiveQuote';
import { DateSelector } from '@/components/shared/DateSelector';

/** Routes where the global historical DateSelector is functional. */
const REVIEW_AWARE_ROUTES = ['/', '/live', '/charts', '/signals'];

export function Header() {
  const { activeTicker } = useTickerStore();
  const { reviewDate } = useReviewDateStore();
  const isReview = reviewDate !== null;
  const { pathname } = useLocation();
  const showDateSelector = REVIEW_AWARE_ROUTES.includes(pathname);

  const { data: quote } = useLiveQuote(activeTicker, !isReview);
  const { theme, toggleTheme } = useThemeStore();

  return (
    <header className="flex flex-wrap items-center justify-between gap-2 bg-[var(--surface-1)] px-5 py-2 sm:h-14 sm:flex-nowrap sm:gap-3 sm:py-0">
      <div className="flex items-center gap-4 min-w-0">
        {/* The Dashboard ('/') renders the ticker prominently in its body, so
            suppress the header copy there to avoid a duplicate. Other routes
            keep it — when the sidebar is collapsed it's the only ticker label. */}
        {pathname !== '/' && (
          <span className="font-display text-lg font-bold text-[var(--on-surface)]">{activeTicker}</span>
        )}
        {/* Live quote is only meaningful in live mode. In review mode, the
            Dashboard page body renders the historical quote prominently. */}
        {!isReview && quote && (
          <>
            <span className="font-display text-lg font-semibold text-[var(--on-surface)]">${quote.price.toFixed(2)}</span>
            <span
              className={`text-sm font-medium ${
                quote.change >= 0 ? 'text-[var(--color-bull)]' : 'text-[var(--color-bear)]'
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
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          className="flex h-8 w-8 items-center justify-center rounded-full text-[var(--on-surface-variant)] hover:bg-[var(--surface-2)] hover:text-[var(--on-surface)] transition-colors"
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      </div>
    </header>
  );
}
