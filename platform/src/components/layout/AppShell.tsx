import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopTabs } from './TopTabs';
import { Header } from './Header';
import { CommandPalette } from './CommandPalette';
import { MostActiveBar } from '@/components/shared/MostActiveBar';
import { useSettingsStore } from '@/stores/settingsStore';

// Routes the most-active marquee mounts on: the MARKET nav group
// (/live, /charts, /options, /signals — see navConfig.ts) plus /journal,
// called out explicitly in the design (design mockup "Most-active ticker
// bar" section). Mounted ONCE here in the shared route layout rather than
// per-page — AppShell wraps every app route via <Outlet/> and persists
// across navigation within the group, so this also avoids an unmount/
// remount (and refetch) when moving between e.g. /live and /charts.
const MOST_ACTIVE_BAR_ROUTES = ['/live', '/charts', '/options', '/signals', '/journal'];

function showMostActiveBar(pathname: string): boolean {
  return MOST_ACTIVE_BAR_ROUTES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export function AppShell() {
  const { navPattern } = useSettingsStore();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const { pathname } = useLocation();

  // Global ⌘K / Ctrl-K toggles the command palette.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const openSearch = () => setPaletteOpen(true);
  const isSidebar = navPattern === 'sidebar';

  return (
    <div className={`flex h-screen overflow-hidden bg-[var(--surface-0)] ${isSidebar ? 'flex-row' : 'flex-col'}`}>
      {isSidebar ? <Sidebar onOpenSearch={openSearch} /> : <TopTabs onOpenSearch={openSearch} />}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Top-tabs mode folds the utility bar (replay, search, sign-out,
            theme) into the single nav row; only the sidebar pattern still
            needs the separate header strip. */}
        {isSidebar && <Header />}
        {showMostActiveBar(pathname) && <MostActiveBar />}
        <main className="flex-1 overflow-x-hidden overflow-y-auto">
          <div className="mx-auto max-w-[1600px] px-4 py-6 sm:px-8 sm:py-8">
            <Outlet />
          </div>
        </main>
      </div>
      <CommandPalette key={paletteOpen ? 'open' : 'closed'} open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
