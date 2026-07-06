import {
  LayoutDashboard,
  Activity,
  CandlestickChart,
  Layers,
  BookOpen,
  BarChart3,
  Search,
  NotebookPen,
  BrainCircuit,
  Zap,
  Settings,
  SlidersHorizontal,
  HelpCircle,
  Info,
  type LucideIcon,
} from 'lucide-react';

export interface NavItem {
  path: string;
  label: string;
  icon: LucideIcon;
  badge?: { text: string; tone?: 'live' };
  /** Render the truthful market-session chip (LIVE/PRE/AH/CLOSED) next to
   *  this item instead of a static badge. */
  liveBadge?: boolean;
  adminOnly?: boolean;
}

export interface NavGroup {
  group: string;
  /** Human label for the group's dropdown trigger in TopTabs. */
  menuLabel?: string;
  /** When true, TopTabs collapses this group into a dropdown instead of
   *  rendering its items inline (Sidebar and the mobile menu ignore this —
   *  they always show grouped items). */
  menu?: boolean;
  /** Render the truthful market-session chip on the dropdown trigger. */
  liveBadge?: boolean;
  items: NavItem[];
}

/**
 * Single source of truth for navigation, shared by the Sidebar and TopTabs
 * shells. Grouped per the Obsidian Analyst redesign; every path maps to a real
 * route so no link is dead. (Strat / Backtests arrive in later phases.)
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    group: 'TRADING',
    items: [
      { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    ],
  },
  {
    group: 'MARKET',
    menuLabel: 'Market',
    menu: true,
    liveBadge: true,
    items: [
      { path: '/live', label: 'Live', icon: Activity, liveBadge: true },
      { path: '/charts', label: 'Charts', icon: CandlestickChart },
      { path: '/options', label: 'Options Flow', icon: Layers },
      { path: '/signals', label: 'Signals', icon: Search },
    ],
  },
  {
    group: 'INTELLIGENCE',
    items: [
      { path: '/insights', label: 'AI Insights', icon: BrainCircuit },
      { path: '/catalysts', label: 'Catalysts', icon: Zap },
    ],
  },
  {
    group: 'LEARN',
    menuLabel: 'Learn',
    menu: true,
    items: [
      { path: '/playbook', label: 'Playbook', icon: BookOpen },
      { path: '/reports', label: 'Reports', icon: BarChart3 },
      { path: '/journal', label: 'Journal', icon: NotebookPen },
    ],
  },
  {
    group: 'SUPPORT',
    menuLabel: 'Support',
    menu: true,
    items: [
      { path: '/admin', label: 'Admin', icon: Settings, adminOnly: true },
      { path: '/settings', label: 'Settings', icon: SlidersHorizontal },
      { path: '/help', label: 'Help & Glossary', icon: HelpCircle },
      { path: '/#faq', label: 'FAQ', icon: Info },
    ],
  },
];

export const FLAT_NAV: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);
