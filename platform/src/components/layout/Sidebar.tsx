import { NavLink } from 'react-router-dom';
import { useSettingsStore } from '@/stores/settingsStore';
import { useTickerStore } from '@/stores/tickerStore';
import { useUser } from '@/hooks/useUser';
import {
  LayoutDashboard,
  Activity,
  CandlestickChart,
  Grid3x3,
  Layers,
  BookOpen,
  BarChart3,
  Search,
  NotebookPen,
  BrainCircuit,
  Zap,
  Settings,
  HelpCircle,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import type { Ticker } from '@/types';

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/live', label: 'Live Market', icon: Activity },
  { path: '/charts', label: 'Charts', icon: CandlestickChart },
  { path: '/options', label: 'Options Flow', icon: Layers },
  { path: '/playbook', label: 'Playbook', icon: BookOpen },
  { path: '/reports', label: 'Reports', icon: BarChart3 },
  { path: '/signals', label: 'Signals', icon: Search },
  { path: '/strat', label: 'Strat History', icon: Grid3x3 },
  { path: '/journal', label: 'Journal', icon: NotebookPen },
  { path: '/insights', label: 'AI Insights', icon: BrainCircuit },
  { path: '/catalysts', label: 'Catalysts', icon: Zap },
  { path: '/admin', label: 'Admin', icon: Settings, adminOnly: true },
  { path: '/help', label: 'Help & Glossary', icon: HelpCircle },
];

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useSettingsStore();
  const { activeTicker, setTicker, availableTickers } = useTickerStore();
  const { isAdmin } = useUser();

  const visibleNavItems = navItems.filter((item) => !('adminOnly' in item && item.adminOnly) || isAdmin);

  return (
    <aside
      className={`flex flex-col bg-[var(--surface-1)] transition-all duration-200 ${
        sidebarCollapsed ? 'w-16' : 'w-56'
      }`}
    >
      {/* Logo */}
      <div className="flex h-14 items-center justify-between px-4">
        {!sidebarCollapsed && (
          <span className="font-display text-sm font-semibold tracking-wide text-[var(--brand)]">
            Trading Platform
          </span>
        )}
        <button
          onClick={toggleSidebar}
          className="rounded-md p-1 text-[var(--on-surface-variant)] hover:bg-[var(--surface-2)] hover:text-[var(--on-surface)] transition-colors"
        >
          {sidebarCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>

      {/* Ticker selector */}
      {!sidebarCollapsed && (
        <div className="flex gap-1 px-3 pb-3">
          {availableTickers.map((t: Ticker) => (
            <button
              key={t}
              onClick={() => setTicker(t)}
              className={`flex-1 rounded-md px-2 py-1.5 text-xs font-semibold transition-colors ${
                activeTicker === t
                  ? 'bg-[var(--brand)] text-[var(--on-brand)]'
                  : 'bg-[var(--surface-2)] text-[var(--on-surface-variant)] hover:bg-[var(--surface-3)] hover:text-[var(--on-surface)]'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      )}

      {/* Nav items */}
      <nav className="flex-1 overflow-y-auto py-2">
        {visibleNavItems.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 mx-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-[var(--surface-2)] text-[var(--brand)] font-semibold'
                  : 'text-[var(--on-surface-variant)] hover:bg-[var(--surface-2)] hover:text-[var(--on-surface)]'
              }`
            }
          >
            <Icon size={18} className="shrink-0" />
            {!sidebarCollapsed && <span>{label}</span>}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
