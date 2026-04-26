import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { MetricCardData } from '@/types';

const toneAccent: Record<NonNullable<MetricCardData['tone']>, string> = {
  default: '',
  brand: 'before:bg-[var(--brand)]',
  bull: 'before:bg-[var(--bull)]',
  bear: 'before:bg-[var(--bear)]',
  warn: 'before:bg-[var(--warn)]',
};

/**
 * KPI card — Obsidian Analyst style.
 *
 * Layout (matches NVDA reference):
 *   MAR 24 CLOSE                ← label-micro, uppercase, 11px, tracking-wider
 *   $175.31                     ← metric-value, Space Grotesk 28px bold
 *   Regular market close        ← 11px, on-surface-variant
 *
 * No border — separation comes from surface-2 tonal shift against surface-0.
 */
export function MetricCard({
  label,
  value,
  direction,
  subtitle,
  change,
  changeLabel,
  tone = 'default',
}: MetricCardData) {
  // Resolve direction: prefer new `direction` prop, fall back to legacy `change` number
  const dir = direction ?? (change !== undefined ? (change >= 0 ? 'up' : 'down') : undefined);
  const hasAccent = tone !== 'default';

  // Accent tone draws a 2px top bar via ::before pseudo element (no visible border otherwise)
  const accentClass = hasAccent
    ? `relative before:absolute before:left-0 before:right-0 before:top-0 before:h-[2px] before:rounded-t-xl ${toneAccent[tone]}`
    : '';

  // Subtitle text color follows direction: bull (green) when up, bear (red)
  // when down, muted gray otherwise. Matches the style of the directional
  // arrow icon rendered next to it.
  const subtitleColor =
    dir === 'up'
      ? 'text-[var(--bull)]'
      : dir === 'down'
      ? 'text-[var(--bear)]'
      : 'text-[var(--on-surface-variant)]';

  return (
    <div
      className={`rounded-xl bg-[var(--surface-2)] p-6 transition-colors ${accentClass}`}
    >
      <p className="label-micro truncate">{label}</p>
      <p className="metric-value mt-3 truncate">{value}</p>
      {(dir || subtitle || changeLabel) && (
        <div className="mt-2 flex items-center gap-1.5">
          {dir === 'up' && <TrendingUp size={12} className="text-[var(--bull)] shrink-0" />}
          {dir === 'down' && <TrendingDown size={12} className="text-[var(--bear)] shrink-0" />}
          {dir === 'neutral' && <Minus size={12} className="text-[var(--on-surface-muted)] shrink-0" />}
          {subtitle && (
            <span className={`text-[11px] truncate ${subtitleColor}`}>{subtitle}</span>
          )}
          {changeLabel && (
            <span className={`text-[11px] truncate ${subtitleColor}`}>{changeLabel}</span>
          )}
        </div>
      )}
    </div>
  );
}
