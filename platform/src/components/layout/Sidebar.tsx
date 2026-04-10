import { NavLink } from 'react-router-dom';
import { useSettingsStore } from '@/stores/settingsStore';
import { useTickerStore } from '@/stores/tickerStore';
import {
  LayoutDashboard,
  Activity,
  CandlestickChart,
  Layers,
  BookOpen,
  FlaskConical,
  BarChart3,
  Search,
  NotebookPen,
  BrainCircuit,
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
  { path: '/backtest', label: 'Backtester', icon: FlaskConical },
  { path: '/reports', label: 'Reports', icon: BarChart3 },
  { path: '/signals', label: 'Signals', icon: Search },
  { path: '/journal', label: 'Journal', icon: NotebookPen },
  { path: '/insights', label: 'AI Insights', icon: BrainCircuit },
];

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useSettingsStore();
  const { activeTicker, setTicker, availableTickers } = useTickerStore();

  return (
    <aside
      className={`flex flex-col border-r border-[var(--color-border)] bg-[var(--color-bg-secondary)] transition-all duration-200 ${
        sidebarCollapsed ? 'w-16' : 'w-56'
      }`}
    >
      {/* Logo */}
      <div className="flex h-14 items-center justify-between border-b border-[var(--color-border)] px-3">
        {!sidebarCollapsed && (
          <span className="text-sm font-semibold tracking-wide text-[var(--color-accent-blue)]">
            Trading Platform
          </span>
        )}
        <button
          onClick={toggleSidebar}
          className="rounded p-1 text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-text-primary)]"
        >
          {sidebarCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>

      {/* Ticker selector */}
      {!sidebarCollapsed && (
        <div className="flex gap-1 border-b border-[var(--color-border)] p-2">
          {availableTickers.map((t: Ticker) => (
            <button
              key={t}
              onClick={() => setTicker(t)}
              className={`flex-1 rounded px-2 py-1 text-xs font-medium transition-colors ${
                activeTicker === t
                  ? 'bg-[var(--color-accent-blue)] text-white'
                  : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      )}

      {/* Nav items */}
      <nav className="flex-1 overflow-y-auto py-2">
        {navItems.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 mx-1 rounded text-sm transition-colors ${
                isActive
                  ? 'bg-[var(--color-bg-hover)] text-[var(--color-accent-blue)] font-medium'
                  : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-text-primary)]'
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
