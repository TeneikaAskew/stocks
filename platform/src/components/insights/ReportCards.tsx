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
  RiskFlag,
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
    long: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
    short: 'bg-rose-500/20 text-rose-400 border-rose-500/40',
    flat: 'bg-zinc-500/20 text-zinc-400 border-zinc-500/40',
  };
  const Icon = direction === 'long' ? TrendingUp : direction === 'short' ? TrendingDown : Minus;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${colors[direction]}`}
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
    <div
      className={`rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4 ${className}`}
    >
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
        {title}
      </h3>
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
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-5">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-bold text-[var(--color-text-primary)]">{report.ticker}</h2>
          <DirectionBadge direction={report.direction} conviction={report.conviction} />
        </div>
        <div className="text-right text-xs text-[var(--color-text-muted)]">
          <div>{asOfDate.toLocaleString()}</div>
          {costUsd !== null && (
            <div className="mt-0.5">
              ${costUsd.toFixed(4)} · {latencyMs !== null ? `${Math.round(latencyMs / 1000)}s` : '—'}
            </div>
          )}
        </div>
      </div>
      <p className="text-sm leading-relaxed text-[var(--color-text-primary)]">{report.thesis}</p>
      <div className="mt-3 flex items-center gap-4 text-xs text-[var(--color-text-muted)]">
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
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-[10px] uppercase text-[var(--color-text-muted)]">Entry Zone</div>
          <div className="font-mono text-[var(--color-text-primary)]">
            {fmt(report.entry_zone.low)} – {fmt(report.entry_zone.high)}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase text-[var(--color-text-muted)]">Stop</div>
          <div className="font-mono text-rose-400">{fmt(report.stop)}</div>
        </div>
        <div className="col-span-2">
          <div className="text-[10px] uppercase text-[var(--color-text-muted)]">Targets</div>
          <div className="flex items-center gap-3 font-mono text-emerald-400">
            {report.targets.length === 0 ? (
              <span className="text-[var(--color-text-muted)]">—</span>
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
          <div className="text-[10px] uppercase text-[var(--color-text-muted)]">Invalidation</div>
          <div className="text-xs text-[var(--color-text-secondary)]">{report.invalidation}</div>
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
      ? 'text-emerald-400'
      : strat.ftfc_direction === 'bearish'
      ? 'text-rose-400'
      : 'text-zinc-400';
  return (
    <Card title="Strat Status">
      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <div className="text-[10px] uppercase text-[var(--color-text-muted)]">Candle</div>
          <div className="font-mono text-sm text-[var(--color-text-primary)]">
            {strat.last_candle}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase text-[var(--color-text-muted)]">FTFC</div>
          <div className={`font-mono text-sm ${dirColor}`}>
            {strat.ftfc_direction} · {fmt(strat.ftfc_score, 2)}
          </div>
        </div>
        {strat.in_force_combo && (
          <div className="col-span-2">
            <div className="text-[10px] uppercase text-[var(--color-text-muted)]">Combo</div>
            <div className="font-mono text-[var(--color-text-primary)]">{strat.in_force_combo}</div>
          </div>
        )}
        {(strat.trigger_high !== null || strat.trigger_low !== null) && (
          <div className="col-span-2">
            <div className="text-[10px] uppercase text-[var(--color-text-muted)]">Triggers</div>
            <div className="font-mono text-[var(--color-text-primary)]">
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
        <div className="text-xs text-[var(--color-text-muted)]">No key levels supplied.</div>
      ) : (
        <div className="grid grid-cols-2 gap-2 text-xs">
          {entries.map(([name, value]) => (
            <div key={name} className="flex items-center justify-between">
              <span className="uppercase text-[var(--color-text-muted)]">{name}</span>
              <span className="font-mono text-[var(--color-text-primary)]">{fmt(value)}</span>
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
    <div className="grid gap-3 md:grid-cols-2">
      <Card title="Bull Case" className="border-emerald-500/30">
        <p className="text-xs leading-relaxed text-[var(--color-text-primary)]">{bullCase}</p>
      </Card>
      <Card title="Bear Case" className="border-rose-500/30">
        <p className="text-xs leading-relaxed text-[var(--color-text-primary)]">{bearCase}</p>
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
        <div className="text-xs text-[var(--color-text-muted)]">No upcoming events flagged.</div>
      ) : (
        <ul className="space-y-2 text-xs">
          {catalysts.map((c, i) => (
            <li key={i} className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span
                  className={`inline-block h-2 w-2 rounded-full ${
                    c.impact === 'high'
                      ? 'bg-rose-400'
                      : c.impact === 'medium'
                      ? 'bg-amber-400'
                      : 'bg-zinc-400'
                  }`}
                />
                <span className="text-[var(--color-text-primary)]">{c.name}</span>
              </div>
              <span className="font-mono text-[var(--color-text-muted)]">{c.date}</span>
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
        <div className="text-xs text-[var(--color-text-muted)]">No risk flags raised.</div>
      </Card>
    );
  }
  return (
    <Card title="Risk Review">
      <ul className="space-y-1.5 text-xs">
        {flags.map((f, i) => (
          <li key={i} className="flex items-start gap-2">
            <AlertTriangle
              size={12}
              className={`mt-0.5 flex-shrink-0 ${
                f.severity === 'block'
                  ? 'text-rose-400'
                  : f.severity === 'warn'
                  ? 'text-amber-400'
                  : 'text-zinc-400'
              }`}
            />
            <div>
              <span className="text-[10px] uppercase text-[var(--color-text-muted)]">
                {f.persona}
              </span>
              <span className="ml-1 text-[var(--color-text-primary)]">{f.message}</span>
            </div>
          </li>
        ))}
      </ul>
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
        <div className="text-xs text-[var(--color-text-muted)]">
          No recent signal alerts supporting this thesis.
        </div>
      ) : (
        <ul className="space-y-1 text-xs">
          {signals.map((s, i) => (
            <li key={i} className="flex items-center justify-between">
              <span
                className={`font-mono ${
                  s.direction === 'CALL' ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                {s.direction}
              </span>
              <span className="text-[var(--color-text-muted)]">{s.strength}</span>
              <span className="font-mono text-[var(--color-text-primary)]">
                {fmt(s.score, 1)}
              </span>
              <span className="text-[10px] text-[var(--color-text-muted)]">
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
        <div className="text-xs text-[var(--color-text-muted)]">
          No similar journal entries found.
        </div>
      ) : (
        <ul className="space-y-1 text-xs">
          {trades.map((t) => (
            <li key={t.id} className="flex items-center justify-between">
              <span
                className={`font-mono ${
                  t.direction === 'CALL' ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                {t.ticker} {t.direction}
              </span>
              <span className="font-mono text-[var(--color-text-primary)]">
                {t.return_pct !== null ? `${fmt(t.return_pct, 2)}%` : '—'}
              </span>
              <span className="text-[10px] text-[var(--color-text-muted)]">
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
    <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
      <AlertTriangle size={12} className="mr-1 inline" />
      Partial report — the following sections were unavailable:{' '}
      <span className="font-mono">{failedSections.join(', ')}</span>
    </div>
  );
}
