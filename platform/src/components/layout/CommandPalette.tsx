import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { Input, Kbd } from '@heroui/react';
import { FLAT_NAV } from './navConfig';
import { useTickerStore } from '@/stores/tickerStore';

interface PaletteItem {
  label: string;
  hint: string;
  to: string;
  /** Optional side-effect run on select (e.g. set active ticker). */
  onSelect?: () => void;
}

interface PaletteGroup {
  group: string;
  items: PaletteItem[];
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

/** ⌘K / Ctrl-K command palette — jump to any page, ticker, or action. */
export function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const navigate = useNavigate();
  const { availableTickers, setTicker } = useTickerStore();
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const groups = useMemo<PaletteGroup[]>(() => {
    const base: PaletteGroup[] = [
      {
        group: 'Jump to',
        items: FLAT_NAV.map((n) => ({ label: n.label, hint: 'page', to: n.path })),
      },
      {
        group: 'Tickers',
        items: availableTickers.map((t) => ({
          label: `${t} · open in Charts`,
          hint: 'chart',
          to: '/charts',
          onSelect: () => setTicker(t),
        })),
      },
      {
        group: 'Actions',
        items: [
          { label: 'New journal entry', hint: 'create', to: '/journal' },
          { label: "Open today's brief", hint: 'view', to: '/insights' },
          { label: 'Dealer gamma — Options Flow', hint: 'view', to: '/options' },
        ],
      },
    ];
    const needle = q.toLowerCase();
    return base
      .map((g) => ({ ...g, items: g.items.filter((i) => i.label.toLowerCase().includes(needle)) }))
      .filter((g) => g.items.length > 0);
  }, [q, availableTickers, setTicker]);

  // Flatten for keyboard selection. Clamp the highlighted index to the current
  // result set so a shrinking list can never leave `sel` out of range.
  const flat = useMemo(() => groups.flatMap((g) => g.items), [groups]);
  const safeSel = Math.min(sel, Math.max(0, flat.length - 1));

  if (!open) return null;

  const choose = (item: PaletteItem) => {
    item.onSelect?.();
    navigate(item.to);
    onClose();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSel((s) => Math.min(s + 1, flat.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSel((s) => Math.max(s - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (flat[safeSel]) choose(flat[safeSel]);
    }
  };

  let runningIndex = -1;

  return (
    <div className="cmdk-overlay" onClick={onClose}>
      <div className="cmdk" onClick={(e) => e.stopPropagation()}>
        <Input
          className="cmdk-input"
          placeholder="Search pages, tickers, actions…"
          autoFocus
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setSel(0);
          }}
          onKeyDown={onKeyDown}
        />
        <div className="cmdk-list" ref={listRef}>
          {groups.map((g) => (
            <div key={g.group}>
              <div className="cmdk-group">{g.group}</div>
              {g.items.map((it) => {
                runningIndex += 1;
                const isSel = runningIndex === safeSel;
                return (
                  <div
                    key={`${g.group}-${it.label}`}
                    className={`cmdk-item${isSel ? ' sel' : ''}`}
                    onClick={() => choose(it)}
                  >
                    <ArrowRight size={14} />
                    <span>{it.label}</span>
                    <Kbd className="kbd-mini">{it.hint}</Kbd>
                  </div>
                );
              })}
            </div>
          ))}
          {groups.length === 0 && (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--on-surface-muted)', fontSize: 12 }}>
              No results
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
