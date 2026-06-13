import type { Key } from 'react';
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectPopover,
  ListBox,
  ListBoxItem,
} from '@heroui/react';
import { useTickerStore } from '@/stores/tickerStore';
import type { Ticker } from '@/types';

interface TickerSelectProps {
  className?: string;
}

/**
 * Per-page ticker dropdown. The global header no longer pins a single ticker;
 * instead, pages that focus on one symbol render this and read/write the shared
 * `tickerStore`. Keeps one cross-page selection without making it omnipresent.
 */
export function TickerSelect({ className }: TickerSelectProps) {
  const { activeTicker, setTicker, availableTickers } = useTickerStore();

  return (
    <Select
      aria-label="Active ticker"
      selectedKey={activeTicker}
      onSelectionChange={(key: Key | null) => {
        if (key != null) setTicker(key as Ticker);
      }}
      className={className}
    >
      <SelectTrigger className="min-w-24 font-display font-semibold tracking-wide">
        <SelectValue />
      </SelectTrigger>
      <SelectPopover>
        <ListBox>
          {availableTickers.map((t) => (
            <ListBoxItem key={t} id={t}>
              {t}
            </ListBoxItem>
          ))}
        </ListBox>
      </SelectPopover>
    </Select>
  );
}
