/**
 * LeverageCard — translates a stock-price movement into the option-equivalent
 * return so users don't read "+0.41%" and assume the option moved that little.
 *
 * Phase 1 of the insights pipeline shows three numbers side-by-side:
 *   1. Stock move %        — what the strat actually measures (real)
 *   2. Slightly-OTM option % — same move at delta ~0.35 (linear estimate)
 *   3. $ per single option  — only rendered when a real contract premium is
 *                             supplied; in Phase 2 this comes from the actual
 *                             5–10-strike-OTM contract at trade time
 *
 * Wording rules: never "underlying", never "bps". Always single-option terms.
 */

import { TrendingUp, TrendingDown, Info } from 'lucide-react';

interface LeverageCardProps {
  /** Stock-price movement as a fraction (e.g. 0.0041 = +0.41%). */
  stockMovePct: number;
  /** Optional label above the row (e.g. "Avg Win", "Avg Loss"). */
  label?: string;
  /**
   * Per-share contract premium at entry. When provided, the card shows
   * the $ P&L on a single option contract (premium × 100 × option return).
   * Phase 2 wires this in from the real chain snapshot; until then it's
   * optional and the card cleanly omits the $ column when missing.
   */
  contractPremium?: number;
  /**
   * Default delta anchor for the option translation. 0.35 corresponds to a
   * slightly-OTM contract roughly 5–7 strikes from spot, the practical
   * intraday default.
   */
  delta?: number;
}

const DEFAULT_DELTA = 0.35;

export function LeverageCard({
  stockMovePct,
  label,
  contractPremium,
  delta = DEFAULT_DELTA,
}: LeverageCardProps) {
  const isUp = stockMovePct >= 0;
  const Icon = isUp ? TrendingUp : TrendingDown;
  const tone = isUp ? 'text-[var(--bull)]' : 'text-[var(--bear)]';

  const optionPct = stockMovePct * delta;
  const dollars =
    contractPremium !== undefined ? optionPct * contractPremium * 100 : null;

  const fmtPct = (v: number) =>
    `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`;
  const fmtDollars = (v: number) =>
    `${v >= 0 ? '+' : '−'}$${Math.abs(v).toFixed(2)}`;

  return (
    <div className="rounded-xl bg-[var(--surface-2)] p-5">
      {label && (
        <div className="mb-3 flex items-center gap-2">
          <span className="label-micro">{label}</span>
          <Icon size={14} className={tone} />
        </div>
      )}
      <div className="grid grid-cols-3 gap-4">
        <Stat
          caption="Stock price movement"
          value={fmtPct(stockMovePct)}
          tone={tone}
          subtitle="What the strat measures"
        />
        <Stat
          caption="Slightly-OTM option"
          value={fmtPct(optionPct)}
          tone={tone}
          subtitle={`At ~${delta.toFixed(2)}Δ — linear estimate`}
        />
        <Stat
          caption="$ per single option"
          value={dollars !== null ? fmtDollars(dollars) : '—'}
          tone={tone}
          subtitle={
            dollars !== null
              ? `On a $${contractPremium?.toFixed(2)} premium contract`
              : 'Real contract math coming in Phase 2'
          }
        />
      </div>
      <div className="mt-3 flex items-start gap-1.5 text-[10px] text-[var(--on-surface-muted)]">
        <Info size={10} className="mt-0.5 shrink-0" />
        <span>
          The strat predicts stock-price movement. Option returns are
          approximated via delta; theta and IV crush over the hold period are
          not modeled here. Phase 2 replaces this estimate with real option
          premium from a 5–10-strike-OTM contract at trade time.
        </span>
      </div>
    </div>
  );
}

function Stat({
  caption,
  value,
  tone,
  subtitle,
}: {
  caption: string;
  value: string;
  tone: string;
  subtitle: string;
}) {
  return (
    <div>
      <div className="label-micro mb-1">{caption}</div>
      <div className={`font-mono text-2xl font-semibold ${tone}`}>{value}</div>
      <div className="mt-1 text-[10px] text-[var(--on-surface-muted)]">
        {subtitle}
      </div>
    </div>
  );
}
