// ---------------------------------------------------------------------------
// Structure Brief — dev-only readout of the strat-engine type model.
//
// The strat-engine type model is a STRUCTURE predictor: for each
// (ticker, timeframe), it estimates the probability that the next bar
// is type 1, 2U, 2D, or 3. The probabilities are calibrated under the
// production config (calibration=none — native LightGBM softmax, which
// the 24-fold walk-forward showed is regime-stable on raw ECE).
//
// This component is DEV-ONLY. It is mounted behind the admin auth gate
// (IAP email OR X-Admin-Token), and is NOT linked from any user-facing
// route or nav. It does NOT run via any scheduler.
//
// The deploy gate is blocked until Tracks B (execution-system backtest)
// and C (direction features R&D) report verdicts.
//
// Self-mute: if the rolling live ECE for a cell exceeds the per-cell
// ceiling, the prediction is hidden and a mute reason is shown instead.
// ---------------------------------------------------------------------------

import { Loader2 } from 'lucide-react';
import {
  useStructureBrief,
  type StructureBriefCell,
  type StructureBriefResponse,
} from '@/hooks/useAdmin';

// Verbatim scope statement that MUST appear above the cells. Do not
// reword. The language audit asserts this string is rendered exactly.
export const SCOPE_STATEMENT =
  'Calibrated structure prediction. Not a directional or P&L edge. Use with discretion.';

// Order shown to the reviewer. 3 tickers × 3 timeframes = 9 cells.
const TICKERS_ORDER = ['IWM', 'SPY', 'QQQ'] as const;
const TFS_ORDER = ['5m', '15m', '30m'] as const;
const CLASSES_ORDER: Array<'1' | '2U' | '2D' | '3'> = ['1', '2U', '2D', '3'];

// ---------------------------------------------------------------------------
// Pure logic — exported for unit tests.
// ---------------------------------------------------------------------------

export interface MuteDecision {
  muted: boolean;
  reason: string | null;
}

/**
 * Pure mute decision. Mute when live_ece > ece_ceiling.
 * No mute when live_ece is null (no reading yet — surface the prediction
 * as-is; the snapshot writer hasn't reported a recent calibration check).
 */
export function decideMute(
  live_ece: number | null | undefined,
  ece_ceiling: number,
): MuteDecision {
  if (live_ece == null) return { muted: false, reason: null };
  if (live_ece > ece_ceiling) {
    return {
      muted: true,
      reason: `model muted, ECE breach (live ECE ${live_ece.toFixed(3)} > ceiling ${ece_ceiling.toFixed(3)})`,
    };
  }
  return { muted: false, reason: null };
}

/**
 * Apply the mute decision to a cell — strip top_class / top_prob /
 * distribution if muted so the component cannot accidentally render a
 * prediction we said we'd hide.
 */
export function applyMute(cell: StructureBriefCell): StructureBriefCell {
  const decision = decideMute(cell.live_ece, cell.ece_ceiling);
  if (!decision.muted) return cell;
  return {
    ...cell,
    muted: true,
    mute_reason: cell.mute_reason ?? decision.reason,
    top_class: null,
    top_prob: null,
    distribution: [],
  };
}

// Banned words / phrases that MUST NOT appear in the brief or design
// doc. The language audit unit test asserts the brief's source text
// does not contain any of these.
export const BANNED_WORDS: readonly string[] = [
  'entry',
  'buy',
  'sell',
  'trade signal',
  'trade this',
  'predicts upside',
  'predicts downside',
  'buy at',
  'sell at',
  'directional edge',
];


export function StructureBrief({ enabled }: { enabled: boolean }) {
  const { data, isLoading, error } = useStructureBrief(enabled);

  if (!enabled) {
    return null;
  }
  if (isLoading) {
    return (
      <div className="flex items-center gap-2 p-4 text-[var(--color-text-muted)]">
        <Loader2 size={16} className="animate-spin" />
        <span>Loading structure prediction snapshot…</span>
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4 text-sm text-[var(--color-text-muted)]">
        Structure brief unavailable: {error?.message ?? 'no data'}
      </div>
    );
  }
  return <StructureBriefView data={data} />;
}


export function StructureBriefView({ data }: { data: StructureBriefResponse }) {
  const cellsByKey = new Map<string, StructureBriefCell>();
  for (const c of data.cells) {
    cellsByKey.set(`${c.ticker}_${c.timeframe}`, c);
  }
  return (
    <div className="space-y-4">
      <ScopeStatement statement={data.scope_statement} />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {TICKERS_ORDER.map((ticker) => (
          <div key={ticker} className="space-y-2">
            <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">{ticker}</h3>
            {TFS_ORDER.map((tf) => {
              const cell = cellsByKey.get(`${ticker}_${tf}`);
              if (!cell) return null;
              return <Cell key={`${ticker}_${tf}`} cell={cell} />;
            })}
          </div>
        ))}
      </div>
    </div>
  );
}


// Renders the verbatim scope statement. The vitest test asserts this
// string is present in the DOM, character-for-character.
export function ScopeStatement({ statement }: { statement: string }) {
  return (
    <div
      data-testid="structure-brief-scope"
      className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-muted)] p-3 text-xs text-[var(--color-text-muted)]"
    >
      {statement}
    </div>
  );
}


export function Cell({ cell }: { cell: StructureBriefCell }) {
  if (!cell.available) {
    return (
      <div
        data-testid={`cell-${cell.ticker}-${cell.timeframe}`}
        className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3 text-xs text-[var(--color-text-muted)]"
      >
        <div className="mb-1 font-medium text-[var(--color-text-secondary)]">{cell.timeframe}</div>
        <div>{cell.note ?? 'unavailable'}</div>
      </div>
    );
  }
  if (cell.muted) {
    return (
      <div
        data-testid={`cell-${cell.ticker}-${cell.timeframe}`}
        data-muted="true"
        className="rounded-md border border-[var(--color-warning)] bg-[var(--color-bg-card)] p-3 text-xs"
      >
        <div className="mb-1 font-medium text-[var(--color-text-secondary)]">{cell.timeframe}</div>
        <div className="text-[var(--color-warning)]">{cell.mute_reason ?? 'model muted, ECE breach'}</div>
      </div>
    );
  }
  return (
    <div
      data-testid={`cell-${cell.ticker}-${cell.timeframe}`}
      className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3 text-xs"
    >
      <div className="mb-2 flex items-baseline justify-between">
        <span className="font-medium text-[var(--color-text-secondary)]">{cell.timeframe}</span>
        <span className="text-[var(--color-text-primary)]">
          next bar {cell.top_prob != null ? `${(cell.top_prob * 100).toFixed(0)}%` : '—'} likely to be type {cell.top_class ?? '—'}
        </span>
      </div>
      <DistributionBars cell={cell} />
      <FooterMetrics cell={cell} />
    </div>
  );
}


function DistributionBars({ cell }: { cell: StructureBriefCell }) {
  const byCls = new Map<string, number>();
  for (const d of cell.distribution) {
    byCls.set(d.cls, d.prob);
  }
  return (
    <div className="space-y-1">
      {CLASSES_ORDER.map((cls) => {
        const p = byCls.get(cls) ?? 0;
        return (
          <div key={cls} className="flex items-center gap-2">
            <span className="w-6 text-right text-[10px] text-[var(--color-text-muted)]">{cls}</span>
            <div className="flex-1 overflow-hidden rounded bg-[var(--color-bg-muted)]">
              <div
                className="h-2 rounded bg-[var(--color-text-secondary)]"
                style={{ width: `${(p * 100).toFixed(1)}%` }}
              />
            </div>
            <span className="w-10 text-right text-[10px] tabular-nums text-[var(--color-text-muted)]">
              {(p * 100).toFixed(0)}%
            </span>
          </div>
        );
      })}
    </div>
  );
}


function FooterMetrics({ cell }: { cell: StructureBriefCell }) {
  return (
    <div className="mt-2 flex justify-between text-[10px] text-[var(--color-text-muted)]">
      <span>
        live ECE {cell.live_ece != null ? cell.live_ece.toFixed(3) : '—'} / ceiling {cell.ece_ceiling.toFixed(3)}
      </span>
      <span>{cell.refreshed_at ? new Date(cell.refreshed_at).toLocaleString() : 'no refresh'}</span>
    </div>
  );
}
