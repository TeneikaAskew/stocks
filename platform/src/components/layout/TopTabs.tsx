import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Search, Menu, X, Moon, Sun, ChevronDown } from 'lucide-react';
import { Button, Kbd } from '@heroui/react';
import { Brand } from './Brand';
import { MarketSessionBadge } from './MarketSessionBadge';
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

const MENU_WIDTH = 208; // w-52

/**
 * Top-tabs navigation shell (default nav pattern).
 *
 * Desktop (≥640px): groups render IN ORDER — non-`menu` groups as inline
 * tabs, `menu` groups (Live Market, Learn, Support) as dropdown triggers.
 * Dropdown panels use `position: fixed` (anchored to the trigger's rect on
 * open) because `.top-tabs` is an `overflow-x: auto` container: an
 * absolutely-positioned panel inside it gets CLIPPED to the 48px bar (the
 * exact bug this replaced). Fixed panels escape the clip and stack above
 * the utility header below the bar. Outside-click / Escape closes; switching
 * menus is one click.
 *
 * Mobile (<640px): the horizontal tab list is hidden and replaced by a
 * hamburger that opens a grouped pop-up menu. The menu closes on selection
 * or an outside tap.
 */
export function TopTabs({ onOpenSearch }: TopTabsProps) {
  const { isAdmin } = useUser();
  const { theme, toggleTheme } = useThemeStore();
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const [menuPos, setMenuPos] = useState<{ top: number; left: number } | null>(null);
  const menusRef = useRef<HTMLElement>(null);

  // Close the open dropdown on outside click / Escape. A listener (rather
  // than a full-screen overlay) keeps sibling triggers clickable, so
  // switching menus is one click, not two.
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

  const groupIsActive = (g: NavGroup) =>
    g.items.some((it) => {
      const base = itemBase(it);
      return base !== null && (pathname === base || pathname.startsWith(`${base}/`));
    });

  const toggleMenu = (g: NavGroup) => (e: ReactMouseEvent<HTMLButtonElement>) => {
    if (openGroup === g.group) {
      setOpenGroup(null);
      return;
    }
    const rect = e.currentTarget.getBoundingClientRect();
    setMenuPos({
      top: rect.bottom + 6,
      left: Math.min(rect.left, window.innerWidth - MENU_WIDTH - 12),
    });
    setOpenGroup(g.group);
  };

  return (
    <div className="top-tabs relative">
      <div className="mr-2 shrink-0">
        <Brand />
      </div>

      {/* Desktop: groups in order — inline tabs or dropdown triggers. */}
      <nav
        ref={menusRef}
        className="hidden min-w-0 flex-1 items-center gap-1 overflow-x-auto [scrollbar-width:none] sm:flex [&::-webkit-scrollbar]:hidden"
      >
        {NAV_GROUPS.map((g) => {
          const groupItems = g.items.filter(visible);
          if (groupItems.length === 0) return null;

          if (!g.menu) {
            return groupItems.map(({ path, label, icon: Icon, badge }) => (
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
            ));
          }

          const open = openGroup === g.group;
          const testId = `nav-menu-${g.group.toLowerCase().replace(/\s+/g, '-')}`;
          return (
            <div key={g.group} className="shrink-0">
              <button
                type="button"
                onClick={toggleMenu(g)}
                aria-expanded={open}
                aria-haspopup="menu"
                className={`top-tab${groupIsActive(g) ? ' active' : ''}`}
                data-testid={testId}
              >
                <span>{g.menuLabel ?? g.group}</span>
                {g.liveBadge && <MarketSessionBadge />}
                <ChevronDown size={12} className={`transition-transform${open ? ' rotate-180' : ''}`} />
              </button>
              {open && menuPos && (
                <nav
                  style={{ position: 'fixed', top: menuPos.top, left: menuPos.left, width: MENU_WIDTH }}
                  className="z-50 rounded-xl border border-[var(--surface-3)] bg-[var(--surface-1)] p-1.5 shadow-2xl"
                >
                  {groupItems.map(({ path, label, icon: Icon, badge, liveBadge }) => (
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
                      {liveBadge && <MarketSessionBadge />}
                      {badge && <span className={`nav-badge${badge.tone === 'live' ? ' live' : ''}`}>{badge.text}</span>}
                    </NavLink>
                  ))}
                </nav>
              )}
            </div>
          );
        })}
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
                  {groupItems.map(({ path, label, icon: Icon, badge, liveBadge }) => (
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
                      {liveBadge && <MarketSessionBadge />}
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
