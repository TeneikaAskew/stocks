import { NavLink } from 'react-router-dom';
import { Search } from 'lucide-react';
import { Button, Kbd } from '@heroui/react';
import { Brand } from './Brand';
import { FLAT_NAV } from './navConfig';
import { useUser } from '@/hooks/useUser';

interface TopTabsProps {
  onOpenSearch: () => void;
}

/**
 * Top-tabs navigation shell (default nav pattern).
 *
 * Layout contract: Brand and Search are pinned (shrink-0); only the tab list
 * scrolls. The tabs live in a `flex-1 min-w-0` region with its own horizontal
 * scroll, so a full nav can never push the Search button off the right edge.
 * (The prior single-flex layout with an `ml-auto` search cut the button off
 * once the 12 tabs exceeded the viewport.)
 */
export function TopTabs({ onOpenSearch }: TopTabsProps) {
  const { isAdmin } = useUser();
  const items = FLAT_NAV.filter((it) => !it.adminOnly || isAdmin);

  return (
    <div className="top-tabs">
      <div className="mr-2 shrink-0">
        <Brand />
      </div>

      {/* Scrollable tab region — absorbs overflow so Brand + Search stay pinned. */}
      <nav className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
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
    </div>
  );
}
