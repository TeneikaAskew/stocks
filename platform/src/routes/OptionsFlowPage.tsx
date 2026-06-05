import { useState } from 'react';
import type { Key } from 'react-aria-components';
import { Tabs } from '@heroui/react';
import { Layers, Activity, BarChart3 } from 'lucide-react';
import { useTickerStore } from '@/stores/tickerStore';
import { TickerSelect } from '@/components/shared/TickerSelect';
import HeatseekerSection from '@/components/options/HeatseekerSection';
import FlowseekerSection from '@/components/options/FlowseekerSection';
import ProfilesTab from '@/components/options/ProfilesTab';

// Options Flow — restructured to Skylit's real IA. Three TOP tabs, each with an
// inner mode toggle where applicable:
//
//   Heatseeker → Swing Mode (mock 2D strikes×expirations heatmap)
//                Trinity Mode (REAL data — SPX/SPY/QQQ strike ladders)
//   Flowseeker → Live Feed (mock flow tape)
//                Contract Drilldown (mock per-contract tape)
//   Profiles   → original Options Flow body, verbatim (REAL data).
//
// The shared <TickerSelect /> in the toolbar drives symbol focus across tabs;
// the global header no longer pins a ticker.

const TABS = [
  { id: 'heatseeker', label: 'Heatseeker', icon: Layers },
  { id: 'flowseeker', label: 'Flowseeker', icon: Activity },
  { id: 'profiles', label: 'Profiles', icon: BarChart3 },
] as const;

export default function OptionsFlowPage() {
  const { activeTicker } = useTickerStore();
  const [tab, setTab] = useState<string>('heatseeker');

  return (
    <div className="flex flex-col gap-4">
      {/* Page toolbar — shared symbol focus across tabs */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--on-surface-label)]">
          Symbol
        </span>
        <TickerSelect />
      </div>

      <Tabs
        selectedKey={tab}
        onSelectionChange={(key: Key) => setTab(String(key))}
        className="flex flex-col gap-4"
      >
        <Tabs.List
          aria-label="Options Flow views"
          className="flex flex-wrap gap-1 border-b border-[var(--outline-variant)]"
        >
          {TABS.map(({ id, label, icon: Icon }) => (
            <Tabs.Tab
              key={id}
              id={id}
              className="flex cursor-pointer items-center gap-1.5 border-b-2 border-transparent px-4 py-2 text-sm font-medium text-[var(--on-surface-variant)] outline-none transition-colors hover:text-[var(--on-surface)] data-[selected=true]:border-[var(--brand)] data-[selected=true]:text-[var(--brand)]"
            >
              <Icon size={14} />
              {label}
            </Tabs.Tab>
          ))}
        </Tabs.List>

        <Tabs.Panel id="heatseeker">
          <HeatseekerSection focusSymbol={activeTicker} />
        </Tabs.Panel>
        <Tabs.Panel id="flowseeker">
          <FlowseekerSection />
        </Tabs.Panel>
        <Tabs.Panel id="profiles">
          <ProfilesTab activeTicker={activeTicker} />
        </Tabs.Panel>
      </Tabs>
    </div>
  );
}
