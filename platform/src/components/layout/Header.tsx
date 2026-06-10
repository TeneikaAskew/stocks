import { Moon, Sun } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { useThemeStore } from '@/stores/themeStore';
import { DateSelector } from '@/components/shared/DateSelector';
import { SignOutButton } from '@/components/auth/SignOutButton';
import { SettingsMenu } from './SettingsMenu';

/** Routes where the global historical DateSelector is functional. */
const REVIEW_AWARE_ROUTES = ['/', '/live', '/charts', '/signals'];

/**
 * Thin global utility bar: review-date control + theme + display settings.
 * The ticker is intentionally NOT shown here — symbol focus lives in a
 * per-page <TickerSelect> dropdown so no single ticker is omnipresent.
 */
export function Header() {
  const { pathname } = useLocation();
  const showDateSelector = REVIEW_AWARE_ROUTES.includes(pathname);
  const { theme, toggleTheme } = useThemeStore();

  return (
    <header className="flex h-12 items-center justify-end gap-3 bg-[var(--surface-1)] px-5">
      <SignOutButton />
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
    </header>
  );
}
