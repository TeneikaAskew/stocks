/**
 * "Like-this-bar" historical setups pane.
 *
 * Surfaces every prior occurrence of a setup matching the live/review
 * bar's bucket (same direction + signal_strength + RSI ±band) along with
 * a stats summary. Hidden until the voter has actually fired — there's
 * no useful reading on a "no setup" bar.
 */
import { TrendingUp, TrendingDown, Loader2 } from 'lucide-react';
import { useSimilarSetups, type SimilarMatch } from '@/hooks/useSimilarSetups';

interface Props {
  ticker: string;
  /** The voter's verdict on the latest bar */
  direction: 'CALL' | 'PUT' | null;
  /** RSI of the latest bar — used as the bucket center */
  rsi: number | null;
  /** Signal strength (3–5) of the latest bar's voter result */
  score: number | null;
}

export function SimilarSetupsCard({ ticker, direction, rsi, score }: Props) {
  const query = useSimilarSetups({ ticker, direction, rsi, score });

  // Hidden when voter says "no setup" — there's no useful question to ask.
  if (!direction || rsi == null || score == null) {
    return (
      <div className="rounded-lg bg-[var(--surface-2)] p-3">
        <div className="text-sm font-semibold text-[var(--color-text-primary)]">
          Similar Past Setups
        </div>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">
          Waits for the voter to fire — no setup currently active.
        </p>
      </div>
    );
  }

  const isLoading = query.isLoading || query.isFetching;
  const data = query.data;
  const tone = direction === 'CALL' ? 'var(--bull)' : 'var(--bear)';
  const Icon = direction === 'CALL' ? TrendingUp : TrendingDown;

  return (
    <div className="rounded-lg bg-[var(--surface-2)] p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
          Similar Past Setups
        </h3>
        <span
          className="inline-flex items-center gap-1 text-[10px] font-bold"
          style={{ color: tone }}
        >
          <Icon size={11} />
          {direction} · score {score} · RSI ~{rsi.toFixed(1)} (±5)
        </span>
      </div>

      {isLoading && !data && (
        <div className="flex items-center gap-2 py-3 text-xs text-[var(--color-text-muted)]">
          <Loader2 size={12} className="animate-spin" />
          Querying historical signals…
        </div>
      )}

      {data && (
        <>
          {data.stats.count === 0 ? (
            <p className="py-2 text-xs text-[var(--color-text-muted)]">
              No historical matches in this bucket yet. Try widening the
              RSI band or wait for the backfill to finish for this ticker.
            </p>
          ) : (
            <>
              <Stats data={data.stats} />
              <RecentMatches matches={data.matches} />
            </>
          )}
        </>
      )}

      {query.isError && (
        <p className="text-xs text-[var(--bear)]">
          {(query.error as Error).message}
        </p>
      )}
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────────────────────

function Stats({ data }: { data: NonNullable<ReturnType<typeof useSimilarSetups>['data']>['stats'] }) {
  const fmtPct = (v: number | null | undefined) =>
    v == null || !Number.isFinite(v) ? '--' : `${(v * 100).toFixed(2)}%`;

  // MFE returns are stored as percent (already × 100 in the python script),
  // so they don't need another × 100. pct_profitable IS a 0..1 fraction.
  const fmtMFE = (v: number | null | undefined) =>
    v == null || !Number.isFinite(v) ? '--' : `${v >= 0 ? '+' : ''}${v.toFixed(3)}%`;

  return (
    <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Tile label="Matches" value={data.count.toLocaleString()} />
      <Tile label="% profitable" value={fmtPct(data.pct_profitable)} />
      <Tile label="Median MFE" value={fmtMFE(data.median_mfe_pct)} />
      <Tile label="IQR (p25–p75)" value={`${fmtMFE(data.p25_mfe_pct)} → ${fmtMFE(data.p75_mfe_pct)}`} />
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-2">
      <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
        {label}
      </div>
      <div className="mt-0.5 font-mono text-xs font-semibold text-[var(--color-text-primary)]">
        {value}
      </div>
    </div>
  );
}

function RecentMatches({ matches }: { matches: SimilarMatch[] }) {
  if (matches.length === 0) return null;
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
        Most recent matches
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
              <th className="py-1 text-left">When</th>
              <th className="py-1 text-right">RSI</th>
              <th className="py-1 text-right">MFE</th>
              <th className="py-1 text-right">+5 min</th>
              <th className="py-1 text-right">+20 min</th>
            </tr>
          </thead>
          <tbody>
            {matches.map((m) => (
              <tr key={m.time} className="border-t border-[var(--color-border)]">
                <td className="py-1 font-mono text-[10px] text-[var(--color-text-secondary)]">
                  {m.time.slice(0, 16)}
                </td>
                <td className="py-1 text-right font-mono text-[var(--color-text-secondary)]">
                  {m.rsi.toFixed(1)}
                </td>
                <td className="py-1 text-right font-mono">
                  <ReturnCell v={m.return_pct} />
                </td>
                <td className="py-1 text-right font-mono">
                  <ReturnCell v={m.return_5min} />
                </td>
                <td className="py-1 text-right font-mono">
                  <ReturnCell v={m.return_20min} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ReturnCell({ v }: { v: number | null }) {
  if (v == null || !Number.isFinite(v)) return <span className="text-[var(--color-text-muted)]">--</span>;
  const tone = v > 0 ? 'var(--bull)' : v < 0 ? 'var(--bear)' : 'var(--color-text-muted)';
  return (
    <span style={{ color: tone }}>
      {v >= 0 ? '+' : ''}
      {v.toFixed(3)}%
    </span>
  );
}
