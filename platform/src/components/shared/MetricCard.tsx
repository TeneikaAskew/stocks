import { TrendingUp, TrendingDown } from 'lucide-react';
import type { MetricCardData } from '@/types';

export function MetricCard({ label, value, change, changeLabel }: MetricCardData) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
      <p className="text-xs text-[var(--color-text-muted)]">{label}</p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
      {change !== undefined && (
        <div className="mt-1 flex items-center gap-1">
          {change >= 0 ? (
            <TrendingUp size={14} className="text-[var(--color-accent-green)]" />
          ) : (
            <TrendingDown size={14} className="text-[var(--color-accent-red)]" />
          )}
          <span
            className={`text-xs font-medium ${
              change >= 0 ? 'text-[var(--color-accent-green)]' : 'text-[var(--color-accent-red)]'
            }`}
          >
            {change >= 0 ? '+' : ''}{change}%
            {changeLabel && <span className="text-[var(--color-text-muted)]"> {changeLabel}</span>}
          </span>
        </div>
      )}
    </div>
  );
}
