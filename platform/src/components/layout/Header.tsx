import { Moon, Sun } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { useThemeStore } from '@/stores/themeStore';
import { DateSelector } from '@/components/shared/DateSelector';
import { SignOutButton } from '@/components/auth/SignOutButton';

/** Routes where the global historical DateSelector is functional. */
const REVIEW_AWARE_ROUTES = ['/dashboard', '/live', '/charts', '/signals'];

/**
 * Thin global utility bar: review-date control + a quick dark/light toggle.
 * Full appearance config (theme, accent, density, nav pattern) lives on the
 * dedicated Settings page (/settings) — not in this bar — so every page keeps
 * a clean header. The ticker is intentionally NOT shown here — symbol focus
 * lives in a per-page <TickerSelect> dropdown.
 */
export function Header() {
  const { pathname } = useLocation();
  const showDateSelector = REVIEW_AWARE_ROUTES.includes(pathname);
  const { theme, toggleTheme } = useThemeStore();

  return (
    <header className="flex min-h-12 flex-wrap items-center justify-end gap-2 bg-[var(--surface-1)] px-5 py-1.5 sm:h-12 sm:flex-nowrap sm:gap-3 sm:py-0">
      <SignOutButton />
      {showDateSelector && <DateSelector />}
      <button
        type="button"
        onClick={toggleTheme}
        aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
        className="hidden h-8 w-8 items-center justify-center rounded-full text-[var(--on-surface-variant)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--on-surface)] sm:flex"
        title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      >
        {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
      </button>
    </header>
  );
}
