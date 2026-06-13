import { useState } from 'react';
import { ToggleButtonGroup, ToggleButton } from '@heroui/react';
import type { Key } from 'react-aria-components';
import { Activity, Search } from 'lucide-react';
import FlowseekerTab from '@/components/options/FlowseekerTab';
import ContractDrilldown, { type SelectedContract } from '@/components/options/ContractDrilldown';

// FlowseekerSection — top-level "Flowseeker" tab with an inner mode toggle:
//   Live Feed          — dense flow tape (MOCK; no live flow-tape endpoint).
//   Contract Drilldown — per-contract tape view (MOCK; no contract-tape endpoint).

type Mode = 'live' | 'drilldown';

function firstKey(keys: Set<Key>): Key | undefined {
  for (const k of keys) return k;
  return undefined;
}

export default function FlowseekerSection() {
  const [mode, setMode] = useState<Mode>('live');
  const [selected, setSelected] = useState<SelectedContract | null>(null);

  const drillInto = (c: SelectedContract) => {
    setSelected(c);
    setMode('drilldown');
  };

  return (
    <div className="space-y-4">
      <ToggleButtonGroup
        size="sm"
        selectionMode="single"
        disallowEmptySelection
        selectedKeys={[mode]}
        onSelectionChange={(keys) => {
          const k = firstKey(keys);
          if (k === 'live' || k === 'drilldown') setMode(k);
        }}
      >
        <ToggleButton id="live">
          <Activity size={13} /> Live Feed
        </ToggleButton>
        <ToggleButton id="drilldown">
          <Search size={13} /> Contract Drilldown
        </ToggleButton>
      </ToggleButtonGroup>

      {mode === 'live' ? (
        <FlowseekerTab onSelectContract={drillInto} />
      ) : (
        <ContractDrilldown selected={selected ?? undefined} />
      )}
    </div>
  );
}
