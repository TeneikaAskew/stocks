// ---------------------------------------------------------------------------
// Movement Read — PHASE 3 of the movement-statement build plan.
//
// Renders the assembled movement statement from GET /api/movement-statement
// (lib/movement_statement.py, behind the MOVEMENT_STATEMENT_ENABLED flag).
//
// This component RENDERS ONLY — it recomputes nothing. Every number shown
// (headline probability, reach-rates, expected-move, regime) comes straight
// from the backend. ALL math lives in lib/ (one source of truth).
//
// Visibility contract:
//   - Flag OFF (default): the endpoint 404s → the hook reports `absent` →
//     this component returns null. The card is genuinely ABSENT; nothing
//     user-visible changes until the flag is flipped on.
//   - Flag ON: the card renders the headline statement, the levels ladder
//     (with reach-rate % + sample size + a low-sample badge), the muted
//     "context" modifiers, and the scope disclaimer.
//
// Rule 3.7 (the ONLY allowed fallback is display-layer null → "—"): for any
// field whose status is UNAVAILABLE (or value is null) we render an em-dash
// "—" plus a small "data unavailable" badge. We NEVER fabricate a number.
// ---------------------------------------------------------------------------

import { AlertTriangle, Activity } from 'lucide-react';
import { Card, CardHeader } from '@/components/primitives';
import { useMovementStatement } from '@/hooks/useMovementStatement';
import type {
  MovementStatement,
  MovementLevelEntry,
  MovementExpectedMove,
  MovementRegime,
  ReachRate,
} from '@/types';

const EM_DASH = '—';

// ---------------------------------------------------------------------------
// Pure helpers — exported for unit tests (vitest, pure-logic style).
// ---------------------------------------------------------------------------

/** A block is OK only when its status is exactly "OK". Anything else (incl.
 *  UNAVAILABLE, REJECTED, or an unexpected status) is treated as not-OK so
 *  the unavailable rendering kicks in — never a fabricated value. */
export function isOk(block: { status?: string } | null | undefined): boolean {
  return !!block && block.status === 'OK';
}

/** Format a 0..1 probability as a whole-percent string, or "—" when null.
 *  Never coerces null to 0 (Rule 3.7) — null renders as the em-dash. */
export function fmtProbPct(p: number | null | undefined): string {
  if (p == null || Number.isNaN(p)) return EM_DASH;
  return `${(p * 100).toFixed(0)}%`;
}

/** Reach-rate display: "48% (n=50)" when OK, "—" when UNAVAILABLE/null. */
export function fmtReachRate(rr: ReachRate | null | undefined): string {
  if (!isOk(rr) || rr?.reach_rate == null) return EM_DASH;
  const pct = (rr.reach_rate * 100).toFixed(0);
  const n = rr.sample_n != null ? `n=${rr.sample_n}` : 'n=?';
  return `${pct}% (${n})`;
}

/** Whether a reach-rate should show the low-confidence badge. */
export function isLowSample(rr: ReachRate | null | undefined): boolean {
  return isOk(rr) && rr?.low_sample === true;
}

// ---------------------------------------------------------------------------
// Small shared badges.
// ---------------------------------------------------------------------------

export function UnavailableBadge({ reason }: { reason?: string | null }) {
  return (
    <span
      data-testid="unavailable-badge"
      title={reason ?? 'data unavailable'}
      className="inline-flex items-center gap-1 rounded bg-[var(--surface-3)] px-1.5 py-0.5 text-[10px] text-[var(--on-surface-muted)]"
    >
      <AlertTriangle size={10} /> data unavailable
    </span>
  );
}

export function LowSampleBadge({ sampleN }: { sampleN?: number | null }) {
  return (
    <span
      data-testid="low-sample-badge"
      className="inline-flex items-center rounded bg-[var(--surface-3)] px-1.5 py-0.5 text-[10px] text-[var(--color-warn,#caa24a)]"
    >
      low confidence (n={sampleN ?? '?'})
    </span>
  );
}

/** An em-dash + unavailable badge — the ONLY allowed Rule 3.7 fallback
 *  (display-layer null → "—"). Used wherever a field is UNAVAILABLE. */
export function UnavailableValue({ reason }: { reason?: string | null }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-[var(--on-surface-muted)]">{EM_DASH}</span>
      <UnavailableBadge reason={reason} />
    </span>
  );
}

// ---------------------------------------------------------------------------
// The card.
// ---------------------------------------------------------------------------

/**
 * Movement Read card. Renders only when the endpoint returns data (flag ON).
 * When the endpoint 404s (flag OFF), the hook reports `absent` and this
 * returns null — the card is hidden by default.
 */
export function MovementRead({
  ticker,
  timeframe = '15m',
  enabled = true,
}: {
  ticker: string;
  timeframe?: '5m' | '15m';
  enabled?: boolean;
}) {
  const { data, isLoading, error } = useMovementStatement(ticker, timeframe, enabled);

  // Hidden while the flag is OFF (404 → absent) or before data arrives.
  if (!enabled) return null;
  if (data?.absent) return null;
  if (isLoading) return null;
  // A genuine transport error (not a 404): render a quiet unavailable note
  // rather than fabricating content. Still additive — small and unobtrusive.
  if (error || !data?.statement) {
    return null;
  }
  return <MovementReadView statement={data.statement} />;
}

export function MovementReadView({ statement }: { statement: MovementStatement }) {
  const { levels, confidence_modifiers, scope_statement, ticker, timeframe } = statement;
  return (
    <Card className="min-w-0">
      <CardHeader
        title={
          <>
            <Activity size={13} className="mr-1.5 inline align-middle" />
            Movement Read
          </>
        }
        meta={`${ticker} · ${timeframe}`}
      />

      {/* Headline — the calibrated continuation probability ONLY. */}
      <HeadlineLine statement={statement} />

      {/* Levels ladder with per-tier reach-rates + low-sample badges. */}
      <LevelsLadder levels={levels} />

      {/* Context modifiers — visually secondary / muted. */}
      <ContextModifiers modifiers={confidence_modifiers} />

      {/* Scope disclaimer — always present. */}
      <p className="mt-3 text-[10px] leading-relaxed text-[var(--on-surface-muted)]">
        {scope_statement}
      </p>
    </Card>
  );
}

function HeadlineLine({ statement }: { statement: MovementStatement }) {
  const { headline } = statement;
  if (!isOk(headline)) {
    return (
      <div className="mb-3 text-[13px] text-[var(--on-surface)]">
        <UnavailableValue reason={headline?.reason ?? 'continuation probability unavailable'} />
      </div>
    );
  }
  return (
    <div data-testid="movement-headline" className="mb-3 text-[13px] leading-snug text-[var(--on-surface)]">
      {headline.statement}
    </div>
  );
}

function LevelsLadder({ levels }: { levels: MovementStatement['levels'] }) {
  if (!isOk(levels)) {
    return (
      <div className="mb-3">
        <div className="mb-1 text-[11px] font-semibold text-[var(--on-surface)]">Levels to go</div>
        <UnavailableValue reason={levels?.reason ?? 'level map unavailable'} />
      </div>
    );
  }
  const calls = levels.calls ?? [];
  const puts = levels.puts ?? [];
  return (
    <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
      <LevelsColumn label="Call levels" entries={calls} />
      <LevelsColumn label="Put levels" entries={puts} />
    </div>
  );
}

function LevelsColumn({ label, entries }: { label: string; entries: MovementLevelEntry[] }) {
  return (
    <div>
      <div className="mb-1 text-[11px] font-semibold text-[var(--on-surface)]">{label}</div>
      {entries.length === 0 ? (
        <UnavailableValue reason="no levels in this direction" />
      ) : (
        <ul className="space-y-1">
          {entries.map((entry, i) => (
            <LevelRow key={`${label}-${i}`} entry={entry} />
          ))}
        </ul>
      )}
    </div>
  );
}

export function LevelRow({ entry }: { entry: MovementLevelEntry }) {
  const rr = entry.reach_rate;
  const name = entry.name ?? `T${''}`;
  return (
    <li className="flex items-center justify-between gap-2 text-[11px]">
      <span className="text-[var(--on-surface-muted)]">
        {name}
        {entry.price != null && (
          <span className="ml-1 tabular-nums text-[var(--on-surface)]">{entry.price.toFixed(2)}</span>
        )}
      </span>
      <span className="flex items-center gap-1.5">
        {isOk(rr) ? (
          <span className="tabular-nums text-[var(--on-surface)]">{fmtReachRate(rr)}</span>
        ) : (
          <UnavailableValue reason={rr?.reason} />
        )}
        {isLowSample(rr) && <LowSampleBadge sampleN={rr?.sample_n} />}
      </span>
    </li>
  );
}

function ContextModifiers({
  modifiers,
}: {
  modifiers: MovementStatement['confidence_modifiers'];
}) {
  const em = modifiers?.expected_move;
  const regime = modifiers?.regime;
  return (
    <div
      data-testid="context-modifiers"
      className="mt-3 rounded-md border border-[var(--outline-variant)] bg-[var(--surface-1)] px-2.5 py-2 opacity-80"
    >
      <div className="mb-1 text-[10px] uppercase tracking-[0.04em] text-[var(--on-surface-muted)]">
        Context — does not change the probability
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-[var(--on-surface-muted)]">
        <ExpectedMoveLine em={em} />
        <RegimeLine regime={regime} />
      </div>
    </div>
  );
}

export function ExpectedMoveLine({ em }: { em: MovementExpectedMove | undefined }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-[var(--on-surface-muted)]">Expected move:</span>
      {isOk(em) && em?.size_class ? (
        <span className="text-[var(--on-surface)]">{em.size_class}</span>
      ) : (
        <UnavailableValue reason={em?.reason} />
      )}
    </span>
  );
}

export function RegimeLine({ regime }: { regime: MovementRegime | undefined }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-[var(--on-surface-muted)]">Regime:</span>
      {isOk(regime) && regime?.mood ? (
        <span className="text-[var(--on-surface)]">{regime.mood}</span>
      ) : (
        <UnavailableValue reason={regime?.reason} />
      )}
    </span>
  );
}
