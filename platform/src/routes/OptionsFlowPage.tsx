import { useState } from 'react';
import { Layers, Activity, BarChart3 } from 'lucide-react';
import { useTickerStore } from '@/stores/tickerStore';
import { TickerCombobox } from '@/components/shared/TickerCombobox';
import HeatseekerSection from '@/components/options/HeatseekerSection';
import FlowseekerSection from '@/components/options/FlowseekerSection';
import ProfilesTab from '@/components/options/ProfilesTab';

// Options Flow — restructured to Skylit's real IA. Three TOP views switched by a
// single-row segmented control, each with an inner mode toggle where applicable:
//
//   Heatseeker → Swing Mode (mock 2D strikes×expirations heatmap)
//                Trinity Mode (REAL data — SPX/SPY/QQQ strike ladders)
//   Flowseeker → Live Feed (mock flow tape)
//                Contract Drilldown (mock per-contract tape)
//   Profiles   → original Options Flow body, verbatim (REAL data).
//
// The shared <TickerCombobox /> drives symbol focus across views; the global
// header no longer pins a ticker.

type TabId = 'heatseeker' | 'flowseeker' | 'profiles';

const TABS: { id: TabId; label: string; icon: typeof Layers }[] = [
  { id: 'heatseeker', label: 'Heatseeker', icon: Layers },
  { id: 'flowseeker', label: 'Flowseeker', icon: Activity },
  { id: 'profiles', label: 'Profiles', icon: BarChart3 },
];

export default function OptionsFlowPage() {
  const { activeTicker } = useTickerStore();
  const [tab, setTab] = useState<TabId>('heatseeker');

  return (
    <div className="flex flex-col gap-4">
      {/* Page toolbar — symbol focus + view switcher, all on one row */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--on-surface-label)]">
          Symbol
        </span>
        <TickerCombobox />

        {/* View switcher — single horizontal segmented control */}
        <div className="ml-auto inline-flex gap-0.5 rounded-lg bg-[var(--surface-2)] p-1 ring-1 ring-[var(--outline-variant)]">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                tab === id
                  ? 'bg-[rgba(139,206,255,0.10)] text-[var(--brand)] shadow-[inset_0_0_0_1px_var(--outline)]'
                  : 'text-[var(--on-surface-variant)] hover:text-[var(--on-surface)]'
              }`}
            >
              <Icon size={14} />
              {label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'heatseeker' && <HeatseekerSection focusSymbol={activeTicker} />}
      {tab === 'flowseeker' && <FlowseekerSection />}
      {tab === 'profiles' && <ProfilesTab activeTicker={activeTicker} />}
    </div>
  );
}
