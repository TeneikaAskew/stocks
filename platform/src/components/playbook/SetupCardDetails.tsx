/**
 * Shared playbook-card detail block: TRADE LEVELS (entry/target/stop in
 * $/%/bps off the live price) + win rate / avg return BY hold window with the
 * best-avg-return hold highlighted.
 *
 * Move magnitudes (target_pct/stop_pct as % of price) and the historical
 * horizon sweep come from the backend (playbook_cards via /api/playbook). The
 * only client-side math is the trivial display arithmetic
 * price × (1 ± pct/100), applied per direction — no financial logic is
 * duplicated here (CLAUDE.md "one source of truth for math").
 */

export interface SetupHorizon {
  minutes: number;
  win_rate: number | null;        // percent (0-100)
  avg_return_bps: number | null;  // basis points
  sample_n?: number | null;
}

export interface SetupCardStats {
  direction?: string;
  target_pct?: number | null;     // move magnitude, % of price
  stop_pct?: number | null;
  horizons?: SetupHorizon[];
  best_horizon_min?: number | null;
  best_horizon_win_rate?: number | null;
  best_horizon_avg_bps?: number | null;
}

function fmtBps(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
}

function LevelRow({ label, sub, px, cls, divider }: {
  label: string; sub: string; px: number; cls: string; divider?: boolean;
}) {
  return (
    <div className={`flex items-center px-3 py-2 text-[11px] ${divider ? 'border-y border-[var(--color-border)]' : ''}`}>
      <span className={`font-semibold ${cls}`}>{label}</span>
      <span className="ml-auto mr-3 text-[10px] text-[var(--color-text-muted)] tabular-nums">{sub}</span>
      <span className={`font-mono font-bold tabular-nums ${cls}`}>${px.toFixed(2)}</span>
    </div>
  );
}

export function SetupCardDetails({ card, price }: {
  card: SetupCardStats;
  price?: number | null;
}) {
  const isPut = (card.direction ?? 'CALL').toUpperCase() === 'PUT';
  const t = card.target_pct;
  const s = card.stop_pct;
  const hasLevels = price != null && price > 0 && t != null && s != null;

  // Direction-aware: CALL targets up / stops down; PUT is the mirror.
  const targetPx = hasLevels ? (isPut ? price! * (1 - t! / 100) : price! * (1 + t! / 100)) : null;
  const stopPx = hasLevels ? (isPut ? price! * (1 + s! / 100) : price! * (1 - s! / 100)) : null;
  const targetUsd = hasLevels ? (price! * t!) / 100 : null;
  const stopUsd = hasLevels ? (price! * s!) / 100 : null;

  const horizons = card.horizons ?? [];
  if (!hasLevels && horizons.length === 0) return null;

  return (
    <div className="mt-3 space-y-3">
      {hasLevels && (
        <div>
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Trade levels · at ${price!.toFixed(2)}
          </div>
          <div className="overflow-hidden rounded-lg border border-[var(--color-border)]">
            <LevelRow
              label="▲ Target"
              sub={`+${t!.toFixed(2)}% · ${(t! * 100).toFixed(0)} bps · +$${targetUsd!.toFixed(2)}`}
              px={targetPx!}
              cls="text-[var(--bull)]"
            />
            <LevelRow label="● Entry" sub="live price" px={price!} cls="text-[var(--color-text-primary)]" divider />
            <LevelRow
              label="▼ Stop"
              sub={`-${s!.toFixed(2)}% · ${(s! * 100).toFixed(0)} bps · -$${stopUsd!.toFixed(2)}`}
              px={stopPx!}
              cls="text-[var(--bear)]"
            />
          </div>
          <div className="mt-1 text-[9px] text-[var(--color-text-muted)] opacity-80">
            Price-only, no fees. Win rate = how often target hits before stop — not the move size.
          </div>
        </div>
      )}

      {horizons.length > 0 && (
        <div>
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Win rate / avg bps by hold window
          </div>
          <div className="grid grid-cols-4 gap-1.5">
            {horizons.map((h) => {
              const best = card.best_horizon_min === h.minutes;
              const ar = h.avg_return_bps;
              return (
                <div
                  key={h.minutes}
                  className={`rounded-lg px-1.5 py-1.5 text-center ${best ? 'border' : 'bg-[var(--color-bg-tertiary)]'}`}
                  style={best ? { borderColor: 'var(--bull)', background: 'color-mix(in oklab, var(--bull) 12%, transparent)' } : undefined}
                >
                  <div className="text-[9px] text-[var(--color-text-muted)]">{h.minutes}m{best ? ' ★' : ''}</div>
                  <div className="text-xs font-bold text-[var(--color-text-primary)]">
                    {h.win_rate == null ? '—' : `${h.win_rate.toFixed(0)}%`}
                  </div>
                  <div className={`text-[9px] font-semibold ${ar != null && ar >= 0 ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}`}>
                    {fmtBps(ar)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
