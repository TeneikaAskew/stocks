/**
 * Obsidian Analyst shared primitives — ported pixel-for-pixel from the Claude
 * Design prototype (`components/atoms.jsx`) into typed React + Tailwind v4,
 * styled with the CSS-var token system in `index.css`. Every redesigned page
 * composes these; keep them dumb and presentational.
 */
import type { ReactNode } from 'react';

// ── Tone system ──────────────────────────────────────────────────────────────
export type Tone = 'default' | 'bull' | 'bear' | 'warn' | 'brand';

const PILL_TONE: Record<Tone, string> = {
  default: 'bg-[var(--surface-3)] text-[var(--on-surface-variant)]',
  bull: 'bg-[rgba(34,197,94,0.14)] text-[var(--bull)]',
  bear: 'bg-[rgba(239,68,68,0.14)] text-[var(--bear)]',
  warn: 'bg-[rgba(255,184,107,0.14)] text-[var(--warn)]',
  brand: 'bg-[rgba(139,206,255,0.14)] text-[var(--brand)]',
};

const METRIC_TONE: Record<Tone, string> = {
  default: 'text-[var(--on-surface)]',
  bull: 'text-[var(--bull)]',
  bear: 'text-[var(--bear)]',
  warn: 'text-[var(--warn)]',
  brand: 'text-[var(--brand)]',
};

// ── Pill ─────────────────────────────────────────────────────────────────────
export function Pill({
  tone = 'default',
  dot = false,
  pulse = false,
  children,
  className = '',
  title,
}: {
  tone?: Tone;
  dot?: boolean;
  pulse?: boolean;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-[5px] rounded-full px-[9px] py-[3px] text-[10.5px] font-semibold tracking-[0.04em] ${PILL_TONE[tone]} ${className}`}
    >
      {dot && (
        <span
          className={`h-1.5 w-1.5 rounded-full bg-current ${pulse ? 'animate-pulse' : ''}`}
        />
      )}
      {children}
    </span>
  );
}

// ── MicroLabel (uppercase caption above values) ──────────────────────────────
export function MicroLabel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`flex items-center gap-[5px] text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--on-surface-label)] ${className}`}
    >
      {children}
    </div>
  );
}

// ── Metric (KPI value) ───────────────────────────────────────────────────────
export type MetricSize = 'kpi' | 'lg' | 'display';
const METRIC_SIZE: Record<MetricSize, string> = {
  kpi: 'text-[length:var(--metric-size,28px)]',
  lg: 'text-[28px]',
  display: 'text-[48px]',
};

export function Metric({
  value,
  tone = 'default',
  size = 'kpi',
  sub,
  className = '',
}: {
  value: ReactNode;
  tone?: Tone;
  size?: MetricSize;
  sub?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`font-display font-bold leading-none tracking-[-0.025em] tabular-nums ${METRIC_SIZE[size]} ${METRIC_TONE[tone]} ${className}`}
    >
      {value}
      {sub != null && (
        <span className="ml-1 text-[0.5em] font-medium text-[var(--on-surface-muted)]">{sub}</span>
      )}
    </div>
  );
}

// ── Delta (signed change) ────────────────────────────────────────────────────
export function Delta({
  value,
  pct,
  prefix = '',
  className = '',
}: {
  value?: number | null;
  pct?: number | null;
  prefix?: string;
  className?: string;
}) {
  const basis = value ?? pct ?? 0;
  const up = basis >= 0;
  const sign = up ? '+' : '';
  const hasVal = typeof value === 'number' && Number.isFinite(value);
  const hasPct = typeof pct === 'number' && Number.isFinite(pct);
  return (
    <span
      className={`text-xs font-semibold tabular-nums ${up ? 'text-[var(--bull)]' : 'text-[var(--bear)]'} ${className}`}
    >
      {hasVal && `${prefix}${sign}${value!.toFixed(2)}`}
      {hasVal && hasPct && ' '}
      {hasPct && `${hasVal ? '(' : ''}${sign}${pct!.toFixed(2)}%${hasVal ? ')' : ''}`}
    </span>
  );
}

// ── KpiTile ──────────────────────────────────────────────────────────────────
export function KpiTile({
  label,
  value,
  delta,
  tone = 'default',
  sub,
  onClick,
}: {
  label: ReactNode;
  value: ReactNode;
  delta?: number | null;
  tone?: Tone;
  sub?: ReactNode;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={`flex flex-col gap-1.5 rounded-xl border border-transparent bg-[var(--surface-2)] p-[var(--card-pad,14px)] transition-colors ${
        onClick ? 'cursor-pointer hover:border-[var(--outline)] hover:bg-[var(--surface-3)]' : ''
      }`}
    >
      <MicroLabel>{label}</MicroLabel>
      <div className="flex items-baseline gap-2">
        <Metric value={value} tone={tone} />
        {delta != null && Number.isFinite(delta) && (
          <Delta pct={delta} />
        )}
      </div>
      {sub != null && <div className="text-[11px] text-[var(--on-surface-muted)]">{sub}</div>}
    </div>
  );
}

// ── ScoreStars (0–5) ─────────────────────────────────────────────────────────
export function ScoreStars({ value, of = 5 }: { value: number; of?: number }) {
  return (
    <span className="inline-flex items-center gap-px">
      {Array.from({ length: of }, (_, i) => {
        const on = i < value;
        return (
          <svg
            key={i}
            width="11"
            height="11"
            viewBox="0 0 24 24"
            fill={on ? 'var(--brand)' : 'none'}
            stroke={on ? 'var(--brand)' : 'var(--on-surface-muted)'}
            strokeWidth="1.5"
          >
            <path d="M12 2l3 7h7l-5.5 4.5L18.5 21 12 17 5.5 21 7.5 13.5 2 9h7z" />
          </svg>
        );
      })}
    </span>
  );
}

// ── RangeBar (bear → brand → bull gradient + marker) ─────────────────────────
export function RangeBar({
  marker = 50,
  lo = 'Bear',
  hi = 'Bull',
}: {
  marker?: number;
  lo?: string;
  hi?: string;
}) {
  const clamped = Math.max(0, Math.min(100, marker));
  return (
    <div>
      <div className="relative h-2 rounded-full bg-[linear-gradient(90deg,var(--warn),var(--brand),var(--bull))]">
        <div
          className="absolute -top-1 h-4 w-1 -translate-x-1/2 rounded-[2px] bg-[var(--on-surface)] shadow-[0_0_0_3px_var(--surface-2)]"
          style={{ left: `${clamped}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-[var(--on-surface-muted)]">
        <span>{lo}</span>
        <span>{hi}</span>
      </div>
    </div>
  );
}

// ── DirTag (direction → pill) ────────────────────────────────────────────────
export function DirTag({ dir }: { dir: string | null | undefined }) {
  const d = (dir || '').toLowerCase();
  if (d === 'call' || d === 'bull' || d === 'bullish') return <Pill tone="bull" dot>CALL</Pill>;
  if (d === 'put' || d === 'bear' || d === 'bearish') return <Pill tone="bear" dot>PUT</Pill>;
  if (d === 'warn' || d === 'watch') return <Pill tone="warn" dot>WATCH</Pill>;
  return <Pill dot>NEUT</Pill>;
}

// ── Card + CardHeader ────────────────────────────────────────────────────────
export function Card({
  children,
  className = '',
  interactive = false,
  onClick,
}: {
  children: ReactNode;
  className?: string;
  interactive?: boolean;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={`rounded-xl bg-[var(--surface-2)] p-[var(--card-pad,14px)] ${
        interactive
          ? 'cursor-pointer border border-transparent transition-colors hover:border-[var(--outline)] hover:bg-[var(--surface-3)]'
          : ''
      } ${className}`}
    >
      {children}
    </div>
  );
}

export function CardHeader({ title, meta }: { title: ReactNode; meta?: ReactNode }) {
  return (
    <div className="mb-2.5 flex items-baseline justify-between">
      <h3 className="text-[13px] font-semibold tracking-[-0.01em] text-[var(--on-surface)]">{title}</h3>
      {meta != null && <span className="text-[11px] tracking-[0.04em] text-[var(--on-surface-muted)]">{meta}</span>}
    </div>
  );
}
