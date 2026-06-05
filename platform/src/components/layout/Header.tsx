import { Moon, Sun } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { useTickerStore } from '@/stores/tickerStore';
import { useReviewDateStore } from '@/stores/reviewDateStore';
import { useThemeStore } from '@/stores/themeStore';
import { useLiveQuote } from '@/hooks/useLiveQuote';
import { DateSelector } from '@/components/shared/DateSelector';
import { SettingsMenu } from './SettingsMenu';

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
    <header className="flex h-14 items-center justify-between bg-[var(--surface-1)] px-5 gap-3">
      <div className="flex items-center gap-4 min-w-0">
        <span className="font-display text-lg font-bold text-[var(--on-surface)]">{activeTicker}</span>
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
        <SettingsMenu />
      </div>
    </header>
  );
}
