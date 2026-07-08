/**
 * Live strategy conditions checklist for the Charts page.
 *
 * Renders the SAME server-computed 10-condition strength readout
 * (POST /api/live/indicators, lib/indicators.py) LiveMarketPage and
 * PlaybookPage render — no client-side re-derivation of the voter.
 *
 * Two columns: CALL conditions and PUT conditions. Each row is a checkmark
 * with a one-line "current vs threshold" readout so the user can see why a
 * condition is unmet without flipping panes.
 */
import { Check, X, TrendingUp, TrendingDown, MinusCircle } from 'lucide-react';
import type { Signal, SignalCondition } from '@/lib/indicators';

interface Props {
  signals: { call: Signal; put: Signal };
}

export function StrategyConditionsCard({ signals }: Props) {
  const { call, put } = signals;
  // Independent 70%-strength thresholds per side (Signal.fired) — a firing
  // tie (both sides cross 70%) picks the stronger side for the badge.
  const firing: 'CALL' | 'PUT' | null = call.fired && (!put.fired || call.strength >= put.strength)
    ? 'CALL'
    : put.fired
      ? 'PUT'
      : null;
  const callMet = call.conditions.filter((c) => c.met).length;
  const putMet = put.conditions.filter((c) => c.met).length;

  return (
    <div className="rounded-lg bg-[var(--surface-2)] p-3">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
            Live Strategy Conditions
          </h3>
          <p className="text-[10px] text-[var(--color-text-muted)]">
            Trend framework — same conditions as the Live page
          </p>
        </div>
        <FiringBadge firing={firing} callMet={callMet} putMet={putMet} total={call.conditions.length} />
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {/* CALL column */}
        <SideColumn
          title="CALL"
          tone="bull"
          icon={<TrendingUp size={12} />}
          strength={call.strength}
          fired={call.fired}
          conditions={call.conditions}
        />

        {/* PUT column */}
        <SideColumn
          title="PUT"
          tone="bear"
          icon={<TrendingDown size={12} />}
          strength={put.strength}
          fired={put.fired}
          conditions={put.conditions}
        />
      </div>
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────────────────────

function FiringBadge({
  firing,
  callMet,
  putMet,
  total,
}: {
  firing: 'CALL' | 'PUT' | null;
  callMet: number;
  putMet: number;
  total: number;
}) {
  if (firing === 'CALL') {
    return (
      <span className="inline-flex items-center gap-1 rounded bg-[var(--bull)] px-2 py-0.5 text-[10px] font-bold text-black">
        <TrendingUp size={11} /> CALL · {callMet}/{total}
      </span>
    );
  }
  if (firing === 'PUT') {
    return (
      <span className="inline-flex items-center gap-1 rounded bg-[var(--bear)] px-2 py-0.5 text-[10px] font-bold text-white">
        <TrendingDown size={11} /> PUT · {putMet}/{total}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] text-[var(--color-text-muted)]">
      <MinusCircle size={11} /> No setup
    </span>
  );
}

function SideColumn({
  title,
  tone,
  icon,
  strength,
  fired,
  conditions,
}: {
  title: string;
  tone: 'bull' | 'bear';
  icon: React.ReactNode;
  strength: number;
  fired: boolean;
  conditions: SignalCondition[];
}) {
  const toneVar = tone === 'bull' ? 'var(--bull)' : 'var(--bear)';
  const metCount = conditions.filter((c) => c.met).length;
  const fmt = (v: number | null) => (v == null || !Number.isFinite(v) ? '--' : v.toFixed(2));

  return (
    <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-2">
      <div className="mb-2 flex items-center justify-between">
        <span
          className="inline-flex items-center gap-1 text-xs font-bold"
          style={{ color: toneVar }}
        >
          {icon} {title}
        </span>
        <span
          className={`text-[10px] font-semibold ${
            fired ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'
          }`}
        >
          {metCount}/{conditions.length} · {strength}% {fired ? '✓ fires' : ''}
        </span>
      </div>
      <ul className="space-y-1">
        {conditions.map((c) => (
          <li key={c.id} className="flex items-start gap-1.5 text-[11px]">
            {c.met ? (
              <Check size={12} className="mt-0.5 shrink-0" style={{ color: toneVar }} />
            ) : (
              <X size={12} className="mt-0.5 shrink-0 text-[var(--color-text-muted)]" />
            )}
            <span className="flex-1">
              <span
                className={
                  c.met ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'
                }
              >
                {c.label}
              </span>
              <span className="ml-1 font-mono text-[10px] text-[var(--color-text-muted)]">
                {fmt(c.current)} {c.operator} {fmt(c.threshold)}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
