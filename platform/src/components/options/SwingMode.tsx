import { useState } from 'react';
import { ToggleButtonGroup, ToggleButton } from '@heroui/react';
import type { Key } from 'react-aria-components';
import { AlertTriangle } from 'lucide-react';
import {
  surfaceFor,
  SWING_SYMBOLS,
  type SwingMetric,
} from '@/data/heatseekerSwingMock';

// SwingMode — Heatseeker "Swing Mode": a 2D dealer-exposure heatmap, strikes as
// ROWS × expiration dates as COLUMNS, GEX/VEX toggle. Driven entirely by a
// clearly-labeled mock (src/data/heatseekerSwingMock.ts) because there is NO
// per-expiration backend endpoint. A persistent demo pill makes that explicit.

function firstKey(keys: Set<Key>): Key | undefined {
  for (const k of keys) return k;
  return undefined;
}

function money(n: number): string {
  const a = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(0)}K`;
  return `${sign}$${a.toFixed(0)}`;
}

function shortExp(iso: string): string {
  // 2026-01-16 → 01/16
  const [, m, d] = iso.split('-');
  return `${m}/${d}`;
}

// Color semantics per Skylit's Heatseeker node system (docs.skylit.ai):
//   positive exposure → "Pika" (yellow): dealer positioning SUPPRESSES vol →
//     pinning / mean-reversion zones.
//   negative exposure → "Barney" (purple): dealer positioning AMPLIFIES vol →
//     acceleration / breakout zones.
//   near-zero → muted teal/cyan base.
// Intensity scales with |value|.
function cellColor(value: number, maxAbs: number): { bg: string; fg: string } {
  const t = Math.max(0, Math.min(1, Math.abs(value) / maxAbs));
  if (t < 0.04) return { bg: 'rgba(24,52,60,0.55)', fg: 'var(--on-surface-muted)' };
  if (value > 0) {
    // Pika — yellow/gold
    return { bg: `rgba(250,204,21,${0.16 + t * 0.72})`, fg: t > 0.4 ? '#191500' : 'var(--on-surface)' };
  }
  // Barney — purple
  return { bg: `rgba(168,85,247,${0.16 + t * 0.72})`, fg: t > 0.4 ? '#ffffff' : 'var(--on-surface)' };
}

interface SwingModeProps {
  /** Focus symbol from the page toolbar; maps onto a mock surface. */
  focusSymbol: string;
}

export default function SwingMode({ focusSymbol }: SwingModeProps) {
  const [metric, setMetric] = useState<SwingMetric>('gex');
  // Local symbol tabs mirror Skylit's All/SPY/TSLA/QQQ/SPXW row. Defaults to the
  // page focus symbol when it has a surface, else SPY.
  const initial = (SWING_SYMBOLS as readonly string[]).includes(focusSymbol)
    ? focusSymbol
    : 'SPY';
  const [sym, setSym] = useState<string>(initial);

  // Adjust the local symbol when the page focus changes (React's documented
  // "adjust state during render" pattern — no setState-in-effect).
  const [prevFocus, setPrevFocus] = useState<string>(focusSymbol);
  if (prevFocus !== focusSymbol) {
    setPrevFocus(focusSymbol);
    if ((SWING_SYMBOLS as readonly string[]).includes(focusSymbol)) {
      setSym(focusSymbol);
    }
  }

  const surface = surfaceFor(sym);
  const matrix = metric === 'gex' ? surface.gex : surface.vex;
  const maxAbs =
    matrix.reduce((m, row) => Math.max(m, ...row.map(Math.abs)), 0) || 1;

  // Nearest strike to spot → highlight that row.
  const spotRowIdx = surface.strikes.reduce(
    (best, s, i) =>
      Math.abs(s - surface.spot) < Math.abs(surface.strikes[best] - surface.spot)
        ? i
        : best,
    0,
  );

  return (
    <div className="space-y-4">
      {/* Persistent demo pill */}
      <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-[var(--warn)]">
        <AlertTriangle size={14} className="shrink-0" />
        <span className="font-semibold">
          Demo data — per-expiration dealer exposure pending backend.
        </span>
      </div>

      {/* Toolbar: GEX/VEX toggle + symbol tabs */}
      <div className="flex flex-wrap items-center gap-3">
        <ToggleButtonGroup
          size="sm"
          selectionMode="single"
          disallowEmptySelection
          selectedKeys={[metric]}
          onSelectionChange={(keys) => {
            const k = firstKey(keys);
            if (k === 'gex' || k === 'vex') setMetric(k);
          }}
        >
          <ToggleButton id="gex">GEX</ToggleButton>
          <ToggleButton id="vex">VEX</ToggleButton>
        </ToggleButtonGroup>

        <div className="flex flex-wrap gap-1.5">
          {SWING_SYMBOLS.map((s) => (
            <button
              key={s}
              onClick={() => setSym(s)}
              className={`rounded px-2.5 py-[3px] text-[11px] font-semibold ${
                sym === s
                  ? 'bg-[var(--brand)] text-[var(--on-brand)]'
                  : 'bg-[var(--surface-3)] text-[var(--on-surface-variant)]'
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        <span className="font-mono text-xs text-[var(--on-surface-muted)]">
          spot {surface.spot.toLocaleString()} · King {surface.king.toLocaleString()}
        </span>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-3 text-[10px] text-[var(--on-surface-muted)]">
        <span className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded-sm" style={{ background: 'rgba(34,200,90,0.7)' }} />
          call-dominant (+)
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded-sm" style={{ background: 'rgba(160,55,150,0.7)' }} />
          put-dominant (−)
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded-sm" style={{ background: 'rgba(250,204,21,0.8)' }} />
          extreme
        </span>
        <span style={{ color: '#ffb800' }}>♔ King row</span>
        <span style={{ color: 'var(--brand)' }}>▸ spot row</span>
      </div>

      {/* 2D heatmap — strikes (rows) × expirations (cols) */}
      <div className="overflow-x-auto rounded-xl bg-[var(--surface-2)] p-2">
        <div className="hs-swing-grid" style={{ minWidth: 720 }}>
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 bg-[var(--surface-2)] px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wider text-[var(--on-surface-label)]">
                  Strike
                </th>
                {surface.expirations.map((e) => (
                  <th
                    key={e}
                    className="px-1.5 py-1.5 text-center text-[10px] font-semibold text-[var(--on-surface-label)]"
                  >
                    {shortExp(e)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {surface.strikes.map((strike, r) => {
                const isKing = strike === surface.king;
                const isSpot = r === spotRowIdx;
                const strikeColor = isKing
                  ? '#ffb800'
                  : isSpot
                  ? 'var(--brand)'
                  : 'var(--on-surface-variant)';
                return (
                  <tr key={strike}>
                    <td
                      className="hs-swing-strike sticky left-0 z-10 bg-[var(--surface-2)] px-2 py-[3px] text-right font-mono text-[11px] font-bold"
                      style={{
                        color: strikeColor,
                        borderLeft: isKing
                          ? '2px solid #ffb800'
                          : isSpot
                          ? '2px solid var(--brand)'
                          : '2px solid transparent',
                      }}
                    >
                      {isKing ? '♔ ' : isSpot ? '▸ ' : ''}
                      {strike.toLocaleString()}
                    </td>
                    {matrix[r].map((value, c) => {
                      const { bg, fg } = cellColor(value, maxAbs);
                      return (
                        <td
                          key={c}
                          className="hs-swing-cell px-1 py-[3px] text-center font-mono text-[10px]"
                          style={{
                            background: bg,
                            color: fg,
                            outline: isSpot ? '1px solid rgba(139,206,255,0.4)' : undefined,
                          }}
                          title={`${sym} ${strike} · ${shortExp(surface.expirations[c])} · ${metric.toUpperCase()} ${money(value)}`}
                        >
                          {money(value)}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
