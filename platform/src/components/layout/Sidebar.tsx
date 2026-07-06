import { NavLink } from 'react-router-dom';
import { Search, PanelLeft } from 'lucide-react';
import { Button, Kbd } from '@heroui/react';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUser } from '@/hooks/useUser';
import { Brand } from './Brand';
import { MarketSessionBadge } from './MarketSessionBadge';
import { NAV_GROUPS } from './navConfig';

interface SidebarProps {
  onOpenSearch: () => void;
}

export function Sidebar({ onOpenSearch }: SidebarProps) {
  const { sidebarCollapsed, toggleSidebar } = useSettingsStore();
  const { isAdmin } = useUser();

  return (
    <aside
      className={`flex flex-col bg-[var(--surface-1)] transition-all duration-200 ${
        sidebarCollapsed ? 'w-16' : 'w-56'
      }`}
    >
      {/* Brand + collapse */}
      <div className="flex h-12 items-center justify-between px-3">
        {!sidebarCollapsed && <Brand />}
        <button
          onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="rounded-md p-1 text-[var(--on-surface-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--on-surface)] transition-colors"
        >
          <PanelLeft size={16} />
        </button>
      </div>

      {/* Search trigger */}
      {!sidebarCollapsed && (
        <Button
          variant="ghost"
          size="sm"
          fullWidth
          onPress={onOpenSearch}
          className="search-trigger mx-2.5 mb-2"
        >
          <Search size={13} />
          <span>Search</span>
          <Kbd>⌘K</Kbd>
        </Button>
      )}

      {/* Grouped nav */}
      <nav className="flex-1 overflow-y-auto py-1">
        {NAV_GROUPS.map((g) => {
          const items = g.items.filter((it) => !it.adminOnly || isAdmin);
          if (items.length === 0) return null;
          return (
            <div key={g.group}>
              {!sidebarCollapsed && <div className="nav-group-label">{g.group}</div>}
              {items.map(({ path, label, icon: Icon, badge, liveBadge }) => (
                <NavLink
                  key={path}
                  to={path}
                  end={path === '/dashboard'}
                  title={label}
                  className={({ isActive }) =>
                    `mx-2 flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                      isActive
                        ? 'bg-[var(--surface-2)] font-semibold text-[var(--brand)]'
                        : 'text-[var(--on-surface-variant)] hover:bg-[var(--surface-2)] hover:text-[var(--on-surface)]'
                    } ${sidebarCollapsed ? 'justify-center' : ''}`
                  }
                >
                  <Icon size={18} className="shrink-0" />
                  {!sidebarCollapsed && <span className="flex-1">{label}</span>}
                  {!sidebarCollapsed && liveBadge && <MarketSessionBadge />}
                  {!sidebarCollapsed && badge && (
                    <span className={`nav-badge${badge.tone === 'live' ? ' live' : ''}`}>{badge.text}</span>
                  )}
                </NavLink>
              ))}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}
