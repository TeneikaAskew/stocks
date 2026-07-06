import { useEffect, useRef, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Search, Menu, X, Moon, Sun, ChevronDown } from 'lucide-react';
import { Button, Kbd } from '@heroui/react';
import { Brand } from './Brand';
import { NAV_GROUPS, type NavGroup, type NavItem } from './navConfig';
import { useUser } from '@/hooks/useUser';
import { useThemeStore } from '@/stores/themeStore';

interface TopTabsProps {
  onOpenSearch: () => void;
}

/** Route prefix an item answers to for active-state checks ('/#faq' → never active). */
function itemBase(item: NavItem): string | null {
  const base = item.path.split('#')[0];
  return base === '/' || base === '' ? null : base;
}

/**
 * Top-tabs navigation shell (default nav pattern).
 *
 * Desktop (≥640px): Brand and Search are pinned (shrink-0); only the INLINE
 * tab list (non-`menu` groups) scrolls in a `flex-1 min-w-0` region. Groups
 * flagged `menu` in navConfig (Learn, Support) collapse into dropdown
 * triggers rendered OUTSIDE the scroll region — an absolutely-positioned
 * panel inside an `overflow-x-auto` container would be clipped, and the
 * dropdowns should stay reachable even when the inline tabs overflow.
 *
 * Mobile (<640px): the horizontal tab list is hidden and replaced by a
 * hamburger that opens a grouped pop-up menu — a 12-tab horizontal scroller is
 * unusable on a phone. The menu closes on selection or an outside tap.
 */
export function TopTabs({ onOpenSearch }: TopTabsProps) {
  const { isAdmin } = useUser();
  const { theme, toggleTheme } = useThemeStore();
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const menusRef = useRef<HTMLDivElement>(null);

  // Close the open dropdown on outside click / Escape. A listener (rather
  // than a full-screen overlay) keeps the sibling trigger clickable, so
  // switching Support → Learn is one click, not two.
  useEffect(() => {
    if (!openGroup) return;
    const onDown = (e: MouseEvent) => {
      if (!menusRef.current?.contains(e.target as Node)) setOpenGroup(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpenGroup(null);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [openGroup]);

  const visible = (it: NavItem) => !it.adminOnly || isAdmin;
  const inlineItems = NAV_GROUPS.filter((g) => !g.menu).flatMap((g) => g.items).filter(visible);
  const menuGroups = NAV_GROUPS.filter((g) => g.menu)
    .map((g) => ({ ...g, items: g.items.filter(visible) }))
    .filter((g) => g.items.length > 0);

  const groupIsActive = (g: NavGroup) =>
    g.items.some((it) => {
      const base = itemBase(it);
      return base !== null && (pathname === base || pathname.startsWith(`${base}/`));
    });

  return (
    <div className="top-tabs relative">
      <div className="mr-2 shrink-0">
        <Brand />
      </div>

      {/* Desktop: scrollable tab region — absorbs overflow so Brand + Search stay pinned. */}
      <nav className="hidden min-w-0 flex-1 items-center gap-1 overflow-x-auto [scrollbar-width:none] sm:flex [&::-webkit-scrollbar]:hidden">
        {inlineItems.map(({ path, label, icon: Icon, badge }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/dashboard'}
            className={({ isActive }) => `top-tab shrink-0${isActive ? ' active' : ''}`}
            title={label}
          >
            <Icon size={path === '/dashboard' ? 15 : 13} />
            {path !== '/dashboard' && <span>{label}</span>}
            {badge && <span className={`nav-badge${badge.tone === 'live' ? ' live' : ''}`}>{badge.text}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Desktop: collapsed group dropdowns — pinned next to Search, never scrolled away. */}
      <div ref={menusRef} className="hidden items-center gap-1 sm:flex">
        {menuGroups.map((g) => {
          const open = openGroup === g.group;
          return (
            <div key={g.group} className="relative shrink-0">
              <button
                type="button"
                onClick={() => setOpenGroup(open ? null : g.group)}
                aria-expanded={open}
                aria-haspopup="menu"
                className={`top-tab${groupIsActive(g) ? ' active' : ''}`}
                data-testid={`nav-menu-${g.group.toLowerCase()}`}
              >
                <span>{g.menuLabel ?? g.group}</span>
                <ChevronDown size={12} className={`transition-transform${open ? ' rotate-180' : ''}`} />
              </button>
              {open && (
                  <nav className="absolute right-0 top-full z-50 mt-1 w-52 rounded-xl border border-[var(--surface-3)] bg-[var(--surface-1)] p-1.5 shadow-2xl">
                    {g.items.map(({ path, label, icon: Icon, badge }) => (
                      <NavLink
                        key={path}
                        to={path}
                        onClick={() => setOpenGroup(null)}
                        className={({ isActive }) =>
                          `flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] transition-colors ${
                            isActive && itemBase({ path, label, icon: Icon }) !== null
                              ? 'bg-[var(--surface-2)] font-semibold text-[var(--brand)]'
                              : 'text-[var(--on-surface-variant)] hover:bg-[var(--surface-2)] hover:text-[var(--on-surface)]'
                          }`
                        }
                      >
                        <Icon size={15} className="shrink-0" />
                        <span className="flex-1">{label}</span>
                        {badge && <span className={`nav-badge${badge.tone === 'live' ? ' live' : ''}`}>{badge.text}</span>}
                      </NavLink>
                    ))}
                  </nav>
              )}
            </div>
          );
        })}
      </div>

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

      {/* Mobile: theme toggle, grouped with the other top-bar chrome (it lives
          in the utility Header on desktop, hidden there on mobile). */}
      <button
        type="button"
        onClick={toggleTheme}
        aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
        className="ml-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[var(--on-surface-variant)] hover:bg-[var(--surface-2)] hover:text-[var(--on-surface)] sm:hidden"
      >
        {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
      </button>

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
              const groupItems = g.items.filter(visible);
              if (groupItems.length === 0) return null;
              return (
                <div key={g.group} className="mb-1">
                  <div className="nav-group-label">{g.group}</div>
                  {groupItems.map(({ path, label, icon: Icon, badge }) => (
                    <NavLink
                      key={path}
                      to={path}
                      end={path === '/dashboard'}
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
