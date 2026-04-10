import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { MetricCardData } from '@/types';

export function MetricCard({ label, value, direction, subtitle, change, changeLabel }: MetricCardData) {
  // Resolve direction: prefer new `direction` prop, fall back to legacy `change` number
  const dir = direction ?? (change !== undefined ? (change >= 0 ? 'up' : 'down') : undefined);

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
      <p className="text-xs text-[var(--color-text-muted)]">{label}</p>
      <p className="mt-1 text-2xl font-bold font-mono">{value}</p>
      {(dir || subtitle || changeLabel) && (
        <div className="mt-1 flex items-center gap-1.5">
          {dir === 'up' && <TrendingUp size={14} className="text-[var(--color-accent-green)]" />}
          {dir === 'down' && <TrendingDown size={14} className="text-[var(--color-accent-red)]" />}
          {dir === 'neutral' && <Minus size={14} className="text-[var(--color-text-muted)]" />}
          {subtitle && (
            <span className="text-xs text-[var(--color-text-muted)]">{subtitle}</span>
          )}
          {changeLabel && (
            <span className="text-xs text-[var(--color-text-muted)]">{changeLabel}</span>
          )}
        </div>
      )}
    </div>
  );
}
