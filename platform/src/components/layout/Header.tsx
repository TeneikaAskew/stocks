import { Moon, Sun } from 'lucide-react';
import { useThemeStore } from '@/stores/themeStore';
import { ReplayControl } from '@/components/shared/ReplayControl';
import { SignOutButton } from '@/components/auth/SignOutButton';

/**
 * Thin global utility bar — SIDEBAR nav pattern only (top-tabs folds these
 * controls into its single row): replay control + sign-out + a quick
 * dark/light toggle. Full appearance config lives on /settings. The ticker
 * is intentionally NOT shown here — symbol focus lives in a per-page
 * <TickerSelect> dropdown. ReplayControl gates itself to review-aware routes.
 */
export function Header() {
  const { theme, toggleTheme } = useThemeStore();

  return (
    <header className="flex min-h-12 flex-wrap items-center justify-end gap-2 bg-[var(--surface-1)] px-5 py-1.5 sm:h-12 sm:flex-nowrap sm:gap-3 sm:py-0">
      <SignOutButton />
      <ReplayControl />
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
