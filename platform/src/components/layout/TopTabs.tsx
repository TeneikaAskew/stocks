import { NavLink } from 'react-router-dom';
import { Search } from 'lucide-react';
import { Button, Kbd } from '@heroui/react';
import { Brand } from './Brand';
import { FLAT_NAV } from './navConfig';
import { useUser } from '@/hooks/useUser';

interface TopTabsProps {
  onOpenSearch: () => void;
}

/** Top-tabs navigation shell (default nav pattern). */
export function TopTabs({ onOpenSearch }: TopTabsProps) {
  const { isAdmin } = useUser();
  const items = FLAT_NAV.filter((it) => !it.adminOnly || isAdmin);

  return (
    <div className="top-tabs">
      <div className="mr-4 shrink-0">
        <Brand />
      </div>
      {items.map(({ path, label, icon: Icon, badge }) => (
        <NavLink
          key={path}
          to={path}
          end={path === '/'}
          className={({ isActive }) => `top-tab${isActive ? ' active' : ''}`}
          title={label}
        >
          <Icon size={path === '/' ? 15 : 13} />
          {path !== '/' && <span>{label}</span>}
          {badge && <span className={`nav-badge${badge.tone === 'live' ? ' live' : ''}`}>{badge.text}</span>}
        </NavLink>
      ))}
      <Button
        variant="ghost"
        size="sm"
        onPress={onOpenSearch}
        className="search-trigger ml-auto w-[200px] shrink-0"
      >
        <Search size={13} />
        <span>Search</span>
        <Kbd>⌘K</Kbd>
      </Button>
    </div>
  );
}
