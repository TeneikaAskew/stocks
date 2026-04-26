// Compact card components for the structured InsightReport view.
// Each one takes a slice of the report and renders it as a read-only
// block. Keep the presentation dense — the landing view should be a
// scannable briefing, not a wall of text.

import { TrendingUp, TrendingDown, Minus, AlertTriangle, Clock, Target } from 'lucide-react';
import type {
  Catalyst,
  Direction,
  InsightReport,
  JournalRef,
  PersonaPlan,
  RiskFlag,
  RiskPersona,
  SignalRef,
  StratSnapshot,
} from '@/types/insights';

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return n.toFixed(digits);
}

function DirectionBadge({ direction, conviction }: { direction: Direction; conviction: string }) {
  const colors: Record<Direction, string> = {
    long: 'bg-[var(--bull)]/20 text-[var(--bull)] border-[var(--bull)]/40',
    short: 'bg-[var(--bear)]/20 text-[var(--bear)] border-[var(--bear)]/40',
    flat: 'bg-[var(--surface-3)] text-[var(--on-surface-muted)] border-[var(--outline-variant)]',
  };
  const Icon = direction === 'long' ? TrendingUp : direction === 'short' ? TrendingDown : Minus;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${colors[direction]}`}
    >
      <Icon size={12} />
      {direction} · {conviction}
    </span>
  );
}

function Card({
  title,
  children,
  className = '',
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded-xl bg-[var(--surface-2)] p-6 ${className}`}>
      <h3 className="label-micro mb-3">{title}</h3>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Header — ticker, direction, conviction, thesis, run metadata
// ---------------------------------------------------------------------------

export function HeaderCard({
  report,
  asOf,
  costUsd,
  latencyMs,
}: {
  report: InsightReport;
  asOf: string;
  costUsd: number | null;
  latencyMs: number | null;
}) {
  const asOfDate = new Date(asOf);
  return (
    <div className="rounded-xl bg-[var(--surface-2)] p-6">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-bold text-[var(--on-surface)]">{report.ticker}</h2>
          <DirectionBadge direction={report.direction} conviction={report.conviction} />
        </div>
        <div className="text-right text-xs text-[var(--on-surface-muted)]">
          <div>{asOfDate.toLocaleString()}</div>
          {costUsd !== null && (
            <div className="mt-0.5">
              ${costUsd.toFixed(4)} · {latencyMs !== null ? `${Math.round(latencyMs / 1000)}s` : '—'}
            </div>
          )}
        </div>
      </div>
      <p className="text-sm leading-relaxed text-[var(--on-surface)]">{report.thesis}</p>
      <div className="mt-4 flex items-center gap-4 text-xs text-[var(--on-surface-muted)]">
        <span className="flex items-center gap-1">
          <Clock size={12} /> {report.time_horizon}
        </span>
        <span>Confidence {fmt(report.confidence_score * 100, 0)}%</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trade Plan — entry zone, stop, targets, invalidation
// ---------------------------------------------------------------------------

export function TradePlanCard({ report }: { report: InsightReport }) {
  return (
    <Card title="Trade Plan">
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <div className="label-micro mb-1">Entry Zone</div>
          <div className="font-mono text-[var(--on-surface)]">
            {fmt(report.entry_zone.low)} – {fmt(report.entry_zone.high)}
          </div>
        </div>
        <div>
          <div className="label-micro mb-1">Stop</div>
          <div className="font-mono text-[var(--bear)]">{fmt(report.stop)}</div>
        </div>
        <div className="col-span-2">
          <div className="label-micro mb-1">Targets</div>
          <div className="flex items-center gap-3 font-mono text-[var(--bull)]">
            {report.targets.length === 0 ? (
              <span className="text-[var(--on-surface-muted)]">—</span>
            ) : (
              report.targets.map((t, i) => (
                <span key={i} className="flex items-center gap-1">
                  <Target size={12} /> {fmt(t)}
                </span>
              ))
            )}
          </div>
        </div>
        <div className="col-span-2">
          <div className="label-micro mb-1">Invalidation</div>
          <div className="text-xs text-[var(--on-surface-variant)]">{report.invalidation}</div>
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Strat snapshot
// ---------------------------------------------------------------------------

export function StratCard({ strat }: { strat: StratSnapshot }) {
  const dirColor =
    strat.ftfc_direction === 'bullish'
      ? 'text-[var(--bull)]'
      : strat.ftfc_direction === 'bearish'
      ? 'text-[var(--bear)]'
      : 'text-[var(--on-surface-muted)]';
  return (
    <Card title="Strat Status">
      <div className="grid grid-cols-2 gap-4 text-xs">
        <div>
          <div className="label-micro mb-1">Candle</div>
          <div className="font-mono text-sm text-[var(--on-surface)]">
            {strat.last_candle}
          </div>
        </div>
        <div>
          <div className="label-micro mb-1">FTFC</div>
          <div className={`font-mono text-sm ${dirColor}`}>
            {strat.ftfc_direction} · {fmt(strat.ftfc_score, 2)}
          </div>
        </div>
        {strat.in_force_combo && (
          <div className="col-span-2">
            <div className="label-micro mb-1">Combo</div>
            <div className="font-mono text-[var(--on-surface)]">{strat.in_force_combo}</div>
          </div>
        )}
        {(strat.trigger_high !== null || strat.trigger_low !== null) && (
          <div className="col-span-2">
            <div className="label-micro mb-1">Triggers</div>
            <div className="font-mono text-[var(--on-surface)]">
              H {fmt(strat.trigger_high)} · L {fmt(strat.trigger_low)}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Key levels
// ---------------------------------------------------------------------------

export function KeyLevelsCard({ levels }: { levels: Record<string, number> }) {
  const entries = Object.entries(levels);
  return (
    <Card title="Key Levels">
      {entries.length === 0 ? (
        <div className="text-xs text-[var(--on-surface-muted)]">No key levels supplied.</div>
      ) : (
        <div className="grid grid-cols-2 gap-3 text-xs">
          {entries.map(([name, value]) => (
            <div key={name} className="flex items-center justify-between">
              <span className="label-micro">{name}</span>
              <span className="font-mono text-[var(--on-surface)]">{fmt(value)}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Bull / bear split card
// ---------------------------------------------------------------------------

export function DebateCard({
  bullCase,
  bearCase,
}: {
  bullCase: string;
  bearCase: string;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card title="Bull Case" className="border border-[var(--bull)]/30">
        <p className="text-sm leading-relaxed text-[var(--on-surface)]">{bullCase}</p>
      </Card>
      <Card title="Bear Case" className="border border-[var(--bear)]/30">
        <p className="text-sm leading-relaxed text-[var(--on-surface)]">{bearCase}</p>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Catalysts
// ---------------------------------------------------------------------------

export function CatalystsCard({ catalysts }: { catalysts: Catalyst[] }) {
  return (
    <Card title="Catalysts">
      {catalysts.length === 0 ? (
        <div className="text-xs text-[var(--on-surface-muted)]">No upcoming events flagged.</div>
      ) : (
        <ul className="space-y-2 text-xs">
          {catalysts.map((c, i) => (
            <li key={i} className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span
                  className={`inline-block h-2 w-2 rounded-full ${
                    c.impact === 'high'
                      ? 'bg-[var(--bear)]'
                      : c.impact === 'medium'
                      ? 'bg-[var(--warn)]'
                      : 'bg-[var(--on-surface-muted)]'
                  }`}
                />
                <span className="text-[var(--on-surface)]">{c.name}</span>
              </div>
              <span className="font-mono text-[var(--on-surface-muted)]">{c.date}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Risk flags
// ---------------------------------------------------------------------------

export function RiskFlagsCard({ flags }: { flags: RiskFlag[] }) {
  if (flags.length === 0) {
    return (
      <Card title="Risk Review">
        <div className="text-xs text-[var(--on-surface-muted)]">No risk flags raised.</div>
      </Card>
    );
  }
  return (
    <Card title="Risk Review">
      <ul className="space-y-2 text-xs">
        {flags.map((f, i) => (
          <li key={i} className="flex items-start gap-2">
            <AlertTriangle
              size={12}
              className={`mt-0.5 flex-shrink-0 ${
                f.severity === 'block'
                  ? 'text-[var(--bear)]'
                  : f.severity === 'warn'
                  ? 'text-[var(--warn)]'
                  : 'text-[var(--on-surface-muted)]'
              }`}
            />
            <div>
              <span className="label-micro">{f.persona}</span>
              <span className="ml-1 text-[var(--on-surface)]">{f.message}</span>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Persona plans — concrete entry/stop/targets per risk persona
// ---------------------------------------------------------------------------

const PERSONA_LABELS: Record<RiskPersona, { label: string; tone: string }> = {
  aggressive:   { label: 'Aggressive',   tone: 'text-[var(--bull)] border-green-500/40 bg-green-500/10' },
  conservative: { label: 'Conservative', tone: 'text-[var(--bear)] border-red-500/40 bg-red-500/10' },
  neutral:      { label: 'Neutral',      tone: 'text-zinc-300 border-zinc-500/40 bg-zinc-500/10' },
};

function PersonaCol({ plan }: { plan: PersonaPlan }) {
  const meta = PERSONA_LABELS[plan.persona];
  const targets = plan.targets || [];
  return (
    <div className={`rounded-md border p-2.5 ${meta.tone} space-y-1.5`}>
      <div className="text-[11px] font-semibold uppercase tracking-wide">
        {meta.label}
      </div>
      <dl className="space-y-1 text-[11px] tabular-nums">
        <div className="flex justify-between gap-2">
          <dt className="text-[var(--color-text-muted)]">Entry</dt>
          <dd className="text-[var(--color-text-primary)] font-medium">
            ${fmt(plan.entry_zone.low)} – ${fmt(plan.entry_zone.high)}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-[var(--color-text-muted)]">Stop</dt>
          <dd className="text-[var(--color-text-primary)] font-medium">
            ${fmt(plan.stop)}
          </dd>
        </div>
        {targets.map((t, i) => (
          <div key={i} className="flex justify-between gap-2">
            <dt className="text-[var(--color-text-muted)]">T{i + 1}</dt>
            <dd className="text-[var(--color-text-primary)] font-medium">${fmt(t)}</dd>
          </div>
        ))}
        <div className="flex justify-between gap-2 pt-1 border-t border-zinc-700/40">
          <dt className="text-[var(--color-text-muted)]">Size</dt>
          <dd className="text-[var(--color-text-primary)] font-semibold">
            {plan.position_size_pct.toFixed(2)}× normal
          </dd>
        </div>
      </dl>
      <div className="text-[10px] leading-snug text-[var(--color-text-muted)] pt-1 border-t border-zinc-700/40">
        {plan.rationale}
      </div>
    </div>
  );
}

export function PersonaPlansCard({ plans }: { plans: PersonaPlan[] }) {
  if (!plans || plans.length === 0) {
    return (
      <Card title="Persona Plans">
        <div className="text-xs text-[var(--color-text-muted)]">
          No persona plans available — risk debate did not produce concrete trade plans.
        </div>
      </Card>
    );
  }
  // Order: aggressive → neutral → conservative
  const ordered: PersonaPlan[] = ['aggressive', 'neutral', 'conservative']
    .map(p => plans.find(x => x.persona === p))
    .filter((p): p is PersonaPlan => Boolean(p));
  return (
    <Card title="Persona Plans">
      <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
        {ordered.map(p => (
          <PersonaCol key={p.persona} plan={p} />
        ))}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Supporting signals + similar past trades
// ---------------------------------------------------------------------------

export function SignalsCard({ signals }: { signals: SignalRef[] }) {
  return (
    <Card title="Supporting Signals">
      {signals.length === 0 ? (
        <div className="flex flex-col items-start gap-1.5">
          <div className="text-xs text-[var(--on-surface-muted)]">
            No recent signal alerts for this ticker.
          </div>
          <div className="text-[10px] text-[var(--on-surface-label)]">
            Signal monitor tracks breakouts within the last 30 days.
          </div>
        </div>
      ) : (
        <ul className="space-y-2 text-xs">
          {signals.map((s, i) => (
            <li key={i} className="flex items-center justify-between gap-3">
              <span
                className={`font-mono font-semibold ${
                  s.direction === 'CALL' ? 'text-[var(--bull)]' : 'text-[var(--bear)]'
                }`}
              >
                {s.direction}
              </span>
              <span className="text-[var(--on-surface-variant)]">{s.strength}</span>
              <span className="font-mono text-[var(--on-surface)]">{fmt(s.score, 1)}</span>
              <span className="text-[10px] text-[var(--on-surface-muted)]">
                {new Date(s.alert_ts).toLocaleString()}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function SimilarTradesCard({ trades }: { trades: JournalRef[] }) {
  return (
    <Card title="Similar Past Trades">
      {trades.length === 0 ? (
        <div className="flex flex-col items-start gap-1.5">
          <div className="text-xs text-[var(--on-surface-muted)]">
            No matching journal entries yet.
          </div>
          <div className="text-[10px] text-[var(--on-surface-label)]">
            Log trades in the Journal to build similarity memory.
          </div>
        </div>
      ) : (
        <ul className="space-y-2 text-xs">
          {trades.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-3">
              <span
                className={`font-mono font-semibold ${
                  t.direction === 'CALL' ? 'text-[var(--bull)]' : 'text-[var(--bear)]'
                }`}
              >
                {t.ticker} {t.direction}
              </span>
              <span className="font-mono text-[var(--on-surface)]">
                {t.return_pct !== null ? `${fmt(t.return_pct, 2)}%` : '—'}
              </span>
              <span className="text-[10px] text-[var(--on-surface-muted)]">
                sim {(1 - t.cosine_distance).toFixed(2)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Degradation banner — shown when any analyst section failed
// ---------------------------------------------------------------------------

export function DegradationBanner({ failedSections }: { failedSections: string[] }) {
  if (failedSections.length === 0) return null;
  return (
    <div className="rounded-lg border border-[var(--warn)]/40 bg-[var(--warn)]/10 px-4 py-2.5 text-xs text-[var(--warn)]">
      <AlertTriangle size={12} className="mr-1 inline" />
      Partial report — the following sections were unavailable:{' '}
      <span className="font-mono">{failedSections.join(', ')}</span>
    </div>
  );
}
