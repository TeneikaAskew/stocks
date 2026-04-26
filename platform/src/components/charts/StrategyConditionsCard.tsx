/**
 * Live strategy conditions checklist for the Charts page.
 *
 * Mirrors the 5-condition voter that `trading_analysis.py:generate_technical_signals`
 * runs over historical bars — same rules, evaluated on whatever bars are
 * currently on the chart (live during market hours, replay during review).
 *
 * Two columns: CALL conditions and PUT conditions. Each row is a checkmark
 * with a one-line "current value" so the user can see why a condition is
 * unmet without flipping panes.
 */
import { Check, X, TrendingUp, TrendingDown, MinusCircle } from 'lucide-react';
import type { Bar, Indicators } from '@/lib/indicators';
import { computeStrategySignals } from '@/lib/indicators';

interface Props {
  bars: Bar[];
  indicators: Indicators;
  vwap: number | null;
}

export function StrategyConditionsCard({ bars, indicators, vwap }: Props) {
  const { call, put, firing } = computeStrategySignals(bars, indicators, vwap);

  return (
    <div className="rounded-lg bg-[var(--surface-2)] p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
          Live Strategy Conditions
        </h3>
        <FiringBadge firing={firing} callMet={call.metCount} putMet={put.metCount} />
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {/* CALL column */}
        <SideColumn
          title="CALL"
          tone="bull"
          icon={<TrendingUp size={12} />}
          metCount={call.metCount}
          totalCount={call.totalCount}
          fires={call.fires}
          conditions={call.conditions}
        />

        {/* PUT column */}
        <SideColumn
          title="PUT"
          tone="bear"
          icon={<TrendingDown size={12} />}
          metCount={put.metCount}
          totalCount={put.totalCount}
          fires={put.fires}
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
}: {
  firing: 'CALL' | 'PUT' | null;
  callMet: number;
  putMet: number;
}) {
  if (firing === 'CALL') {
    return (
      <span className="inline-flex items-center gap-1 rounded bg-[var(--bull)] px-2 py-0.5 text-[10px] font-bold text-black">
        <TrendingUp size={11} /> CALL · {callMet}/5
      </span>
    );
  }
  if (firing === 'PUT') {
    return (
      <span className="inline-flex items-center gap-1 rounded bg-[var(--bear)] px-2 py-0.5 text-[10px] font-bold text-white">
        <TrendingDown size={11} /> PUT · {putMet}/5
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
  metCount,
  totalCount,
  fires,
  conditions,
}: {
  title: string;
  tone: 'bull' | 'bear';
  icon: React.ReactNode;
  metCount: number;
  totalCount: number;
  fires: boolean;
  conditions: { id: string; label: string; met: boolean; detail: string }[];
}) {
  const toneVar = tone === 'bull' ? 'var(--bull)' : 'var(--bear)';
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
            fires ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'
          }`}
        >
          {metCount}/{totalCount} {fires ? '✓ fires' : ''}
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
                {c.detail}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
