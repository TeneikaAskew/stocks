import type { Key } from 'react';
import { SlidersHorizontal, Moon, Sun, PanelLeft, LayoutGrid } from 'lucide-react';
import {
  Button,
  Popover,
  PopoverContent,
  ToggleButton,
  ToggleButtonGroup,
} from '@heroui/react';
import { useThemeStore } from '@/stores/themeStore';
import { useSettingsStore, ACCENTS, type Density, type NavPattern, type Accent } from '@/stores/settingsStore';

/** Accent swatch colors (match index.css .accent-* palettes; blue = brand). */
const ACCENT_SWATCH: Record<Accent, string> = {
  blue: '#8bceff',
  amber: '#ffb86b',
  violet: '#b58bff',
  cyan: '#5ee3e1',
  teal: '#14b8a6',
  pink: '#ff7eb9',
  magenta: '#e879f9',
  orange: '#fb923c',
  yellow: '#facc15',
  indigo: '#818cf8',
  rose: '#f472b6',
};

/** First key of a single-selection change, ignoring empty sets. */
function firstKey(keys: Set<Key>): Key | undefined {
  for (const k of keys) return k;
  return undefined;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <span className="label-micro">{label}</span>
      {children}
    </div>
  );
}

/** Gear button + popover exposing theme, nav pattern, density, and accent. */
export function SettingsMenu() {
  const { theme, setTheme } = useThemeStore();
  const { navPattern, setNavPattern, density, setDensity, accent, setAccent } = useSettingsStore();

  const densities: Density[] = ['comfy', 'default', 'dense'];
  const navs: { value: NavPattern; icon: typeof PanelLeft; label: string }[] = [
    { value: 'top-tabs', icon: LayoutGrid, label: 'Tabs' },
    { value: 'sidebar', icon: PanelLeft, label: 'Sidebar' },
  ];

  return (
    <Popover>
      <Button
        isIconOnly
        variant="ghost"
        size="sm"
        aria-label="Display settings"
      >
        <SlidersHorizontal size={16} />
      </Button>

      <PopoverContent placement="bottom end" className="w-72 p-4">
        <Row label="Theme">
          <ToggleButtonGroup
            size="sm"
            selectionMode="single"
            disallowEmptySelection
            selectedKeys={[theme]}
            onSelectionChange={(keys) => {
              const k = firstKey(keys);
              if (k === 'dark' || k === 'light') setTheme(k);
            }}
          >
            <ToggleButton id="dark">
              <Moon size={13} /> Dark
            </ToggleButton>
            <ToggleButton id="light">
              <Sun size={13} /> Light
            </ToggleButton>
          </ToggleButtonGroup>
        </Row>

        <Row label="Navigation">
          <ToggleButtonGroup
            size="sm"
            selectionMode="single"
            disallowEmptySelection
            selectedKeys={[navPattern]}
            onSelectionChange={(keys) => {
              const k = firstKey(keys);
              if (k === 'top-tabs' || k === 'sidebar') setNavPattern(k);
            }}
          >
            {navs.map(({ value, icon: Icon, label }) => (
              <ToggleButton key={value} id={value}>
                <Icon size={13} /> {label}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Row>

        <Row label="Density">
          <ToggleButtonGroup
            size="sm"
            selectionMode="single"
            disallowEmptySelection
            selectedKeys={[density]}
            onSelectionChange={(keys) => {
              const k = firstKey(keys);
              if (k === 'comfy' || k === 'default' || k === 'dense') setDensity(k);
            }}
          >
            {densities.map((d) => (
              <ToggleButton key={d} id={d}>
                {d[0].toUpperCase() + d.slice(1)}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Row>

        <div className="py-2">
          <span className="label-micro">Accent</span>
          <div className="mt-2 flex flex-wrap gap-2">
            {ACCENTS.map((a) => (
              <ToggleButton
                key={a}
                isIconOnly
                size="sm"
                aria-label={a}
                isSelected={accent === a}
                onChange={() => setAccent(a)}
                className="h-6 w-6 min-w-0 rounded-full p-0"
                style={{ background: ACCENT_SWATCH[a] }}
              />
            ))}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
