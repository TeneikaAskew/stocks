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
// Self-mute: if the rolling live ECE for a cell exceeds the per-cell
// ceiling, the prediction is hidden and a mute reason is shown instead.
// ---------------------------------------------------------------------------

import { AlertTriangle, Clock, Loader2 } from 'lucide-react';
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

// Class semantics — color-coded by structural meaning. Mute drops to
// neutral grey to reinforce that no prediction is being claimed.
const CLASS_COLOR_VAR: Record<'1' | '2U' | '2D' | '3', string> = {
  '1': 'var(--color-text-muted)',
  '2U': 'var(--color-bull)',
  '2D': 'var(--color-bear)',
  '3': 'var(--color-warn)',
};

const CLASS_LABEL: Record<'1' | '2U' | '2D' | '3', string> = {
  '1': '1 (inside)',
  '2U': '2U (up)',
  '2D': '2D (down)',
  '3': '3 (outside)',
};

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

// Words / phrases that MUST NOT appear in the brief or design
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

// Format an ISO timestamp as a short relative read ("3m ago", "yesterday").
// Used in card footers. Falls back to absolute time when older than a day.
export function formatRefreshed(iso: string | null | undefined): string {
  if (!iso) return 'no refresh';
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return 'no refresh';
  const diffMs = Date.now() - ts;
  if (diffMs < 0) return new Date(ts).toLocaleString();
  const sec = Math.floor(diffMs / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}d ago`;
  return new Date(ts).toLocaleDateString();
}


export function StructureBrief({ enabled }: { enabled: boolean }) {
  const { data, isLoading, error } = useStructureBrief(enabled);

  if (!enabled) {
    return null;
  }
  if (isLoading) {
    return <SkeletonGrid />;
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
  const totalCells = TICKERS_ORDER.length * TFS_ORDER.length;
  let mutedCount = 0;
  let availableCount = 0;
  for (const c of data.cells) {
    if (c.muted) mutedCount += 1;
    if (c.available) availableCount += 1;
  }
  return (
    <div className="space-y-4">
      <ScopeStatement statement={data.scope_statement} />
      <BriefStatusBar
        totalCells={totalCells}
        availableCount={availableCount}
        mutedCount={mutedCount}
        eceCeiling={data.ece_ceiling}
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
      className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-3 text-xs text-[var(--color-text-muted)]"
    >
      {statement}
    </div>
  );
}


// Compact status strip at the top of the grid — shows aggregate health
// of all 9 cells. Lets the operator see at-a-glance whether anything
// is muted before scanning the grid.
function BriefStatusBar({
  totalCells, availableCount, mutedCount, eceCeiling,
}: {
  totalCells: number;
  availableCount: number;
  mutedCount: number;
  eceCeiling: number;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-secondary)] px-3 py-2 text-[11px] text-[var(--color-text-muted)]">
      <span>
        <span className="text-[var(--color-text-primary)]">{availableCount}</span> / {totalCells} cells available
      </span>
      <span>·</span>
      {mutedCount > 0 ? (
        <span className="flex items-center gap-1 text-[var(--color-warn)]">
          <AlertTriangle size={12} /> {mutedCount} muted
        </span>
      ) : (
        <span>0 muted</span>
      )}
      <span>·</span>
      <span>ECE ceiling {eceCeiling.toFixed(3)}</span>
    </div>
  );
}


export function Cell({ cell }: { cell: StructureBriefCell }) {
  if (!cell.available) {
    return (
      <div
        data-testid={`cell-${cell.ticker}-${cell.timeframe}`}
        className="rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-3 text-xs text-[var(--color-text-muted)]"
      >
        <div className="mb-1 flex items-center justify-between">
          <span className="font-medium text-[var(--color-text-secondary)]">{cell.timeframe}</span>
          <span className="text-[10px]">unavailable</span>
        </div>
        <div>{cell.note ?? 'No live data.'}</div>
      </div>
    );
  }
  if (cell.muted) {
    return (
      <div
        data-testid={`cell-${cell.ticker}-${cell.timeframe}`}
        data-muted="true"
        className="rounded-md border border-[var(--color-warn)] bg-[var(--color-bg-card)] p-3 text-xs"
      >
        <div className="mb-2 flex items-center justify-between">
          <span className="font-medium text-[var(--color-text-secondary)]">{cell.timeframe}</span>
          <span className="text-[10px] text-[var(--color-text-muted)]">{formatRefreshed(cell.refreshed_at)}</span>
        </div>
        <div className="flex items-start gap-2 text-[var(--color-warn)]">
          <AlertTriangle size={14} className="mt-[1px] flex-none" />
          <span>{cell.mute_reason ?? 'model muted, ECE breach'}</span>
        </div>
        <FooterMetrics cell={cell} />
      </div>
    );
  }
  return (
    <div
      data-testid={`cell-${cell.ticker}-${cell.timeframe}`}
      className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3 text-xs"
    >
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <span className="font-medium text-[var(--color-text-secondary)]">{cell.timeframe}</span>
        <span className="flex items-center gap-1 text-[10px] text-[var(--color-text-muted)]">
          <Clock size={10} /> {formatRefreshed(cell.refreshed_at)}
        </span>
      </div>
      <TopCallLine cell={cell} />
      <DistributionBars cell={cell} />
      <FooterMetrics cell={cell} />
    </div>
  );
}


function TopCallLine({ cell }: { cell: StructureBriefCell }) {
  if (cell.top_class == null || cell.top_prob == null) return null;
  const cls = cell.top_class;
  const pct = (cell.top_prob * 100).toFixed(0);
  return (
    <div className="mb-2 text-[var(--color-text-primary)]">
      next bar{' '}
      <span className="font-semibold" style={{ color: CLASS_COLOR_VAR[cls] }}>
        {pct}%
      </span>{' '}
      likely to be type{' '}
      <span className="font-semibold" style={{ color: CLASS_COLOR_VAR[cls] }}>
        {cls}
      </span>{' '}
      <span className="text-[10px] text-[var(--color-text-muted)]">({CLASS_LABEL[cls].split(' ')[1]?.replace(/[()]/g, '') ?? ''})</span>
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
            <span
              className="w-12 text-right text-[10px] font-medium"
              style={{ color: CLASS_COLOR_VAR[cls] }}
            >
              {cls}
            </span>
            <div className="flex-1 overflow-hidden rounded bg-[var(--color-bg-muted)]">
              <div
                className="h-2 rounded transition-[width] duration-200"
                style={{
                  width: `${(p * 100).toFixed(1)}%`,
                  backgroundColor: CLASS_COLOR_VAR[cls],
                  opacity: 0.85,
                }}
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
        live ECE{' '}
        <span className="tabular-nums text-[var(--color-text-secondary)]">
          {cell.live_ece != null ? cell.live_ece.toFixed(3) : '—'}
        </span>{' '}
        / ceiling {cell.ece_ceiling.toFixed(3)}
      </span>
    </div>
  );
}


function SkeletonGrid() {
  return (
    <div className="space-y-4">
      <div className="h-9 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-secondary)]" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {TICKERS_ORDER.map((ticker) => (
          <div key={ticker} className="space-y-2">
            <div className="h-4 w-12 rounded bg-[var(--color-bg-muted)]" />
            {TFS_ORDER.map((tf) => (
              <div key={tf} className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3">
                <div className="mb-2 flex items-center gap-2 text-[var(--color-text-muted)]">
                  <Loader2 size={12} className="animate-spin" />
                  <span className="text-[10px]">loading {tf}…</span>
                </div>
                <div className="space-y-1">
                  {[0, 1, 2, 3].map((i) => (
                    <div key={i} className="h-2 rounded bg-[var(--color-bg-muted)]" />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
