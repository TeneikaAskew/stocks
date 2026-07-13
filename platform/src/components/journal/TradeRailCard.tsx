import { LogOut, Trash2 } from 'lucide-react';
import type { TradeEntry } from '@/types';
import { riskReward, stopDisplayText } from '@/lib/risk';

export interface TradeRailCardProps {
  trade: TradeEntry;
  /** Marks this card as a read-only teaching/example row rather than the
   *  user's own trade — renders the muted `EX` badge and suppresses the
   *  exit/delete controls (an example trade isn't the caller's to manage). */
  example?: boolean;
  onExit?: (id: string) => void;
  onDelete?: (id: string) => void;
  onHover?: (id: string | null) => void;
  /** True when this card's trade is the one currently hovered (host tracks
   *  a single hoveredTradeId and compares it against `trade.id`) — renders a
   *  visible ring so the hover→chart-highlight link (design spec Option B,
   *  Task 5 gap) is confirmable from the rail side, not just the chart. */
  highlighted?: boolean;
}

/**
 * One trade's card in the side-rail trade list — extracted from ChartsPage's
 * inline `TradeCard` (Task 4), restyled for the Journal one-stop cockpit
 * (Task 5, user-refined layout): top row = direction badge (+ EX badge for
 * examples) left, return % CENTERED and PROMINENT (largest text on the
 * card), time right; line 2 = Entry → Exit; line 3 = TP · SL · R:R, each
 * segment rendering "—" when its plan leg is missing (Rule 3.7 — never a
 * fabricated value). task-alerts-enrichment (2026-07-12): the SL segment
 * renders a pipeline row's OWN `timeStopMinutes` as "<N>m time-stop" when
 * there is no stop PRICE (`stopLoss` undefined) — never a fixed label.
 */
export function TradeRailCard({
  trade,
  example = false,
  onExit,
  onDelete,
  onHover,
  highlighted = false,
}: TradeRailCardProps) {
  const isCall = trade.optionType === 'CALL';
  const formatTime = (ts: number) => {
    const d = new Date(ts * 1000);
    return `${d.getUTCHours().toString().padStart(2, '0')}:${d.getUTCMinutes().toString().padStart(2, '0')}`;
  };

  const ret = trade.pnlPercent;
  const rr = riskReward(
    trade.entryPrice,
    trade.takeProfits[0]?.price ?? null,
    trade.stopLoss?.price ?? null,
  );

  return (
    <div
      data-testid="trade-rail-card"
      data-highlighted={highlighted ? 'true' : undefined}
      className={`rounded border bg-[var(--color-bg-tertiary)] p-2 transition-shadow ${
        highlighted
          ? 'border-[var(--color-accent-blue)] ring-2 ring-[var(--color-accent-blue)]'
          : 'border-[var(--color-border)]'
      }`}
      onMouseEnter={() => onHover?.(trade.id)}
      onMouseLeave={() => onHover?.(null)}
    >
      {/* Top row — direction (+EX) | return % centered+largest | time+actions */}
      <div className="grid grid-cols-3 items-center">
        <div className="flex items-center gap-1 justify-self-start">
          <span
            className={`rounded px-1.5 py-0.5 text-xs font-bold ${
              isCall ? 'bg-green-500/20 text-[var(--bull)]' : 'bg-red-500/20 text-[var(--bear)]'
            }`}
          >
            {trade.optionType}
          </span>
          {example && (
            <span
              data-testid="ex-badge"
              title="Example — read-only teaching trade"
              className="rounded bg-[var(--color-bg-hover)] px-1 py-0.5 text-[9px] font-semibold tracking-wide text-[var(--color-text-muted)]"
            >
              EX
            </span>
          )}
          {/* task-examples-union: origin badge for a pipeline-sourced
             (automated signal-engine) example row, distinguishing it from
             an admin-authored one — same muted weight as the EX badge
             above, shown alongside it (a pipeline row is always also an
             example row). */}
          {trade.source === 'pipeline' && (
            <span
              data-testid="pipeline-badge"
              title="Pipeline — automated signal-engine trade"
              className="rounded bg-[var(--color-bg-hover)] px-1 py-0.5 text-[9px] font-semibold tracking-wide text-[var(--color-text-muted)]"
            >
              pipeline
            </span>
          )}
        </div>
        <span
          data-testid="rail-return"
          className={`justify-self-center text-base font-bold ${
            ret == null
              ? 'text-[var(--on-surface-muted)]'
              : ret >= 0
                ? 'text-[var(--bull)]'
                : 'text-[var(--bear)]'
          }`}
        >
          {ret == null ? '—' : `${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%`}
        </span>
        <div className="flex items-center gap-1 justify-self-end">
          <span data-testid="rail-entry-time" className="text-xs text-[var(--color-text-muted)]">
            {formatTime(trade.entryTime)}
          </span>
          {!example && trade.status === 'active' && (
            <button
              onClick={() => onExit?.(trade.id)}
              className="rounded p-0.5 text-[var(--color-text-muted)] hover:text-[var(--color-accent-amber)]"
              title="Mark exit"
            >
              <LogOut size={12} />
            </button>
          )}
          {!example && (
            <button
              onClick={() => onDelete?.(trade.id)}
              className="rounded p-0.5 text-[var(--color-text-muted)] hover:text-[var(--color-accent-red)]"
              title="Delete trade"
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Line 2 — Entry → Exit */}
      <div className="mt-1 text-center text-xs text-[var(--color-text-secondary)]">
        <span className="font-mono">${trade.entryPrice.toFixed(2)}</span>
        {' → '}
        <span className="font-mono">
          {trade.exitPrice != null ? `$${trade.exitPrice.toFixed(2)}` : '—'}
        </span>
      </div>

      {/* Line 3 — TP · SL · R:R (each "—" when missing) */}
      <div className="mt-0.5 text-center text-[10px] text-[var(--color-text-muted)]">
        <span className="text-[var(--color-accent-green)]">
          TP{' '}
          {trade.takeProfits.length > 0
            ? trade.takeProfits.map((tp) => tp.price.toFixed(2)).join(' / ')
            : '—'}
        </span>
        {' · '}
        <span data-testid="rail-sl" className="text-[var(--color-accent-red)]">
          SL {stopDisplayText(trade.stopLoss?.price ?? null, trade.timeStopMinutes ?? null)}
        </span>
        {' · '}
        <span>R:R {rr != null ? rr.toFixed(2) : '—'}</span>
      </div>
    </div>
  );
}
