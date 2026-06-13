import { useState } from 'react';
import { ToggleButtonGroup, ToggleButton } from '@heroui/react';
import type { Key } from 'react-aria-components';
import { LayoutGrid, Columns3 } from 'lucide-react';
import SwingMode from '@/components/options/SwingMode';
import TrinityTab from '@/components/options/TrinityTab';

// HeatseekerSection — top-level "Heatseeker" tab with an inner mode toggle:
//   Swing   — 2D strikes×expirations exposure heatmap (MOCK; no per-expiration
//             backend endpoint yet).
//   Trinity — 3 synced index-proxy strike ladders (REAL data via useGammaLevels).

type Mode = 'swing' | 'trinity';

function firstKey(keys: Set<Key>): Key | undefined {
  for (const k of keys) return k;
  return undefined;
}

interface HeatseekerSectionProps {
  /** Page focus symbol — feeds the Swing surface selection. */
  focusSymbol: string;
}

export default function HeatseekerSection({ focusSymbol }: HeatseekerSectionProps) {
  const [mode, setMode] = useState<Mode>('swing');

  return (
    <div className="space-y-4">
      <ToggleButtonGroup
        size="sm"
        selectionMode="single"
        disallowEmptySelection
        selectedKeys={[mode]}
        onSelectionChange={(keys) => {
          const k = firstKey(keys);
          if (k === 'swing' || k === 'trinity') setMode(k);
        }}
      >
        <ToggleButton id="swing">
          <LayoutGrid size={13} /> Swing Mode
        </ToggleButton>
        <ToggleButton id="trinity">
          <Columns3 size={13} /> Trinity Mode
        </ToggleButton>
      </ToggleButtonGroup>

      {mode === 'swing' ? <SwingMode focusSymbol={focusSymbol} /> : <TrinityTab />}
    </div>
  );
}
