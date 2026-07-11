import { LogOut, Trash2 } from 'lucide-react';
import type { TradeEntry } from '@/types';

export interface TradeRailCardProps {
  trade: TradeEntry;
  /** Marks this card as a read-only teaching/example row rather than the
   *  user's own trade — reserved for a future presentation (Journal phase);
   *  renders identically to the default until that phase defines its own
   *  styling. When true, exit/delete controls are suppressed (an example
   *  trade isn't the caller's own to manage). */
  example?: boolean;
  onExit?: (id: string) => void;
  onDelete?: (id: string) => void;
  onHover?: (id: string | null) => void;
}

/**
 * One trade's card in the side-rail trade list — extracted verbatim from
 * ChartsPage.tsx's inline `TradeCard` (Task 4 extraction; renamed
 * `TradeRailCard` per the docs/... task-4-brief.md deliverable list). Layout
 * is preserved as-is for this task; a later Journal-page task restyles it.
 */
export function TradeRailCard({ trade, example = false, onExit, onDelete, onHover }: TradeRailCardProps) {
  const isCall = trade.optionType === 'CALL';
  const formatTime = (ts: number) => {
    const d = new Date(ts * 1000);
    return `${d.getUTCHours().toString().padStart(2, '0')}:${d.getUTCMinutes().toString().padStart(2, '0')}`;
  };

  return (
    <div
      className="rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] p-2"
      onMouseEnter={() => onHover?.(trade.id)}
      onMouseLeave={() => onHover?.(null)}
    >
      <div className="flex items-center justify-between">
        <span
          className={`rounded px-1.5 py-0.5 text-xs font-bold ${
            isCall ? 'bg-green-500/20 text-[var(--bull)]' : 'bg-red-500/20 text-[var(--bear)]'
          }`}
        >
          {trade.optionType}
        </span>
        <div className="flex items-center gap-1">
          <span className="text-xs text-[var(--color-text-muted)]">
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
      <div className="mt-1 text-xs">
        <span className="text-[var(--color-text-secondary)]">Entry:</span>{' '}
        <span className="font-mono">${trade.entryPrice.toFixed(2)}</span>
      </div>
      {trade.exitPrice && (
        <div className="mt-0.5 text-xs">
          <span className="text-[var(--color-text-secondary)]">Exit:</span>{' '}
          <span className="font-mono">${trade.exitPrice.toFixed(2)}</span>
        </div>
      )}
      {trade.takeProfits.length > 0 && (
        <div className="mt-0.5 text-xs text-[var(--color-accent-green)]">
          TP: {trade.takeProfits.map((tp) => `$${tp.price.toFixed(2)}`).join(' / ')}
        </div>
      )}
      {trade.stopLoss && (
        <div className="mt-0.5 text-xs text-[var(--color-accent-red)]">
          SL: ${trade.stopLoss.price.toFixed(2)}
        </div>
      )}
      {trade.pnl !== undefined && trade.pnl !== null && (
        <div className={`mt-1 text-xs font-medium ${trade.pnl >= 0 ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}`}>
          {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)} ({trade.pnlPercent?.toFixed(2)}%)
        </div>
      )}
    </div>
  );
}
