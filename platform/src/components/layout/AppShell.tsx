import { useEffect, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopTabs } from './TopTabs';
import { Header } from './Header';
import { CommandPalette } from './CommandPalette';
import { useSettingsStore } from '@/stores/settingsStore';

export function AppShell() {
  const { navPattern } = useSettingsStore();
  const [paletteOpen, setPaletteOpen] = useState(false);

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
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto">
          <div className="mx-auto max-w-[1600px] px-8 py-8">
            <Outlet />
          </div>
        </main>
      </div>
      <CommandPalette key={paletteOpen ? 'open' : 'closed'} open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
