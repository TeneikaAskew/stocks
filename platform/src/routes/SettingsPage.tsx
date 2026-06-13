/**
 * Settings — appearance & display preferences.
 *
 * Home for the theme / navigation / density / accent controls that used to
 * live in the global header popover (`SettingsMenu`). Moved here so the
 * dashboard and every other page keep a clean utility bar; only a quick
 * dark/light toggle remains in the header. All state is the same Zustand
 * stores (persisted to localStorage), so changes apply app-wide instantly.
 */
import type { Key } from 'react';
import { Moon, Sun, PanelLeft, LayoutGrid } from 'lucide-react';
import { ToggleButton, ToggleButtonGroup } from '@heroui/react';
import { useThemeStore } from '@/stores/themeStore';
import {
  useSettingsStore, ACCENTS, type Density, type NavPattern, type Accent,
} from '@/stores/settingsStore';

/** Accent swatch colors (match index.css .accent-* palettes; blue = brand). */
const ACCENT_SWATCH: Record<Accent, string> = {
  blue: '#8bceff', amber: '#ffb86b', violet: '#b58bff', cyan: '#5ee3e1',
  teal: '#14b8a6', pink: '#ff7eb9', magenta: '#e879f9', orange: '#fb923c',
  yellow: '#facc15', indigo: '#818cf8', rose: '#f472b6',
};

/** First key of a single-selection change, ignoring empty sets. */
function firstKey(keys: Set<Key>): Key | undefined {
  for (const k of keys) return k;
  return undefined;
}

function Section({ title, desc, children }: { title: string; desc: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl bg-[var(--surface-1)] p-5">
      <div className="mb-3">
        <h2 className="text-sm font-semibold text-[var(--on-surface)]">{title}</h2>
        <p className="mt-0.5 text-[12px] text-[var(--on-surface-muted)]">{desc}</p>
      </div>
      {children}
    </section>
  );
}

export default function SettingsPage() {
  const { theme, setTheme } = useThemeStore();
  const { navPattern, setNavPattern, density, setDensity, accent, setAccent } = useSettingsStore();

  const densities: Density[] = ['comfy', 'default', 'dense'];
  const navs: { value: NavPattern; icon: typeof PanelLeft; label: string }[] = [
    { value: 'top-tabs', icon: LayoutGrid, label: 'Tabs' },
    { value: 'sidebar', icon: PanelLeft, label: 'Sidebar' },
  ];

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <header>
        <h1 className="text-2xl font-semibold text-[var(--on-surface)]">Settings</h1>
        <p className="mt-1 text-sm text-[var(--on-surface-muted)]">
          Appearance &amp; display preferences. Saved to this device.
        </p>
      </header>

      <Section title="Theme" desc="Light or dark color scheme (also toggleable from the header).">
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
          <ToggleButton id="dark"><Moon size={13} /> Dark</ToggleButton>
          <ToggleButton id="light"><Sun size={13} /> Light</ToggleButton>
        </ToggleButtonGroup>
      </Section>

      <Section title="Navigation" desc="Top tab bar or a left sidebar for the primary nav.">
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
            <ToggleButton key={value} id={value}><Icon size={13} /> {label}</ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Section>

      <Section title="Density" desc="Spacing and sizing across tables and cards.">
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
            <ToggleButton key={d} id={d}>{d[0].toUpperCase() + d.slice(1)}</ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Section>

      <Section title="Accent" desc="Highlight color for active state, links, and charts.">
        <div className="flex flex-wrap gap-2">
          {ACCENTS.map((a) => (
            <ToggleButton
              key={a}
              isIconOnly
              size="sm"
              aria-label={a}
              isSelected={accent === a}
              onChange={() => setAccent(a)}
              className="h-7 w-7 min-w-0 rounded-full p-0"
              style={{ background: ACCENT_SWATCH[a] }}
            />
          ))}
        </div>
      </Section>
    </div>
  );
}
