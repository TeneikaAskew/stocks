import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { Search, Menu, X } from 'lucide-react';
import { Button, Kbd } from '@heroui/react';
import { Brand } from './Brand';
import { FLAT_NAV, NAV_GROUPS } from './navConfig';
import { useUser } from '@/hooks/useUser';

interface TopTabsProps {
  onOpenSearch: () => void;
}

/**
 * Top-tabs navigation shell (default nav pattern).
 *
 * Desktop (≥640px): Brand and Search are pinned (shrink-0); only the tab list
 * scrolls in a `flex-1 min-w-0` region so a full nav can never push Search off
 * the right edge.
 *
 * Mobile (<640px): the horizontal tab list is hidden and replaced by a
 * hamburger that opens a grouped pop-up menu — a 12-tab horizontal scroller is
 * unusable on a phone. The menu closes on selection or an outside tap.
 */
export function TopTabs({ onOpenSearch }: TopTabsProps) {
  const { isAdmin } = useUser();
  const items = FLAT_NAV.filter((it) => !it.adminOnly || isAdmin);
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="top-tabs relative">
      <div className="mr-2 shrink-0">
        <Brand />
      </div>

      {/* Desktop: scrollable tab region — absorbs overflow so Brand + Search stay pinned. */}
      <nav className="hidden min-w-0 flex-1 items-center gap-1 overflow-x-auto [scrollbar-width:none] sm:flex [&::-webkit-scrollbar]:hidden">
        {items.map(({ path, label, icon: Icon, badge }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/'}
            className={({ isActive }) => `top-tab shrink-0${isActive ? ' active' : ''}`}
            title={label}
          >
            <Icon size={path === '/' ? 15 : 13} />
            {path !== '/' && <span>{label}</span>}
            {badge && <span className={`nav-badge${badge.tone === 'live' ? ' live' : ''}`}>{badge.text}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Mobile: spacer pushes Search + hamburger to the right. */}
      <div className="flex-1 sm:hidden" />

      <Button
        variant="ghost"
        size="sm"
        onPress={onOpenSearch}
        aria-label="Search"
        className="search-trigger ml-2 w-auto shrink-0 sm:w-[170px]"
      >
        <Search size={13} />
        <span className="hidden sm:inline">Search</span>
        <Kbd className="hidden sm:inline">⌘K</Kbd>
      </Button>

      {/* Mobile: hamburger toggle. */}
      <Button
        isIconOnly
        variant="ghost"
        size="sm"
        onPress={() => setMenuOpen((o) => !o)}
        aria-label={menuOpen ? 'Close menu' : 'Open menu'}
        aria-expanded={menuOpen}
        className="ml-1 shrink-0 sm:hidden"
      >
        {menuOpen ? <X size={18} /> : <Menu size={18} />}
      </Button>

      {/* Mobile: grouped pop-up menu. */}
      {menuOpen && (
        <>
          <div
            className="fixed inset-0 z-40 sm:hidden"
            aria-hidden="true"
            onClick={() => setMenuOpen(false)}
          />
          <nav className="fixed right-2 top-[52px] z-50 max-h-[80vh] w-60 overflow-y-auto rounded-xl border border-[var(--surface-3)] bg-[var(--surface-1)] p-2 shadow-2xl sm:hidden">
            {NAV_GROUPS.map((g) => {
              const groupItems = g.items.filter((it) => !it.adminOnly || isAdmin);
              if (groupItems.length === 0) return null;
              return (
                <div key={g.group} className="mb-1">
                  <div className="nav-group-label">{g.group}</div>
                  {groupItems.map(({ path, label, icon: Icon, badge }) => (
                    <NavLink
                      key={path}
                      to={path}
                      end={path === '/'}
                      onClick={() => setMenuOpen(false)}
                      className={({ isActive }) =>
                        `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                          isActive
                            ? 'bg-[var(--surface-2)] font-semibold text-[var(--brand)]'
                            : 'text-[var(--on-surface-variant)] hover:bg-[var(--surface-2)] hover:text-[var(--on-surface)]'
                        }`
                      }
                    >
                      <Icon size={18} className="shrink-0" />
                      <span className="flex-1">{label}</span>
                      {badge && <span className={`nav-badge${badge.tone === 'live' ? ' live' : ''}`}>{badge.text}</span>}
                    </NavLink>
                  ))}
                </div>
              );
            })}
          </nav>
        </>
      )}
    </div>
  );
}
