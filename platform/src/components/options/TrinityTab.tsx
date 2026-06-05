import { useQuery } from '@tanstack/react-query';
import { useGammaLevels, type GammaLevel } from '@/hooks/useGammaLevels';

// TrinityTab — 3 synced index-proxy panels (SPX · SPY · QQQ). Each panel
// fetches its own latest snapshot date and gamma levels from the real
// /levels endpoint via useGammaLevels. Renders a put/call GEX strike ladder
// per the design's TrinityPanel: puts grow left (red), calls grow right
// (green), the King row is gold, the spot row is brand-tinted.
//
// The API expects the plain symbol 'SPX' (see VALID_TICKERS in
// api/routers/options.py) — not '^SPX'.

const TRINITY_SYMBOLS = ['SPX', 'SPY', 'QQQ'] as const;

interface DatesResponse {
  ticker: string;
  dates: string[];
}

function useLatestOptionsDate(ticker: string) {
  return useQuery<DatesResponse>({
    queryKey: ['options-dates', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/options/dates/${ticker}`);
      if (!r.ok) throw new Error(`dates ${r.status}`);
      return r.json();
    },
    staleTime: 300_000,
    retry: false,
  });
}

function formatGEX(val: number): string {
  const abs = Math.abs(val);
  const sign = val >= 0 ? '+' : '-';
  if (abs >= 1_000_000_000) return `${sign}$${(abs / 1_000_000_000).toFixed(1)}B`;
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

// One synced panel. Fetches its own latest date + levels.
function TrinityPanel({ symbol }: { symbol: string }) {
  const datesQuery = useLatestOptionsDate(symbol);
  const latestDate = datesQuery.data?.dates?.[0] ?? '';

  const levelsQuery = useGammaLevels(symbol, latestDate, {
    enabled: !!latestDate,
  });
  const levels = levelsQuery.data;

  const loading = datesQuery.isLoading || levelsQuery.isLoading;
  const failed = datesQuery.isError || levelsQuery.isError || (!loading && !latestDate);

  // Build the strike ladder from the classified levels, sorted high → low.
  const spot = levels?.spot.price ?? 0;
  const king = levels?.kings?.[0]?.strike;
  // Strike nearest spot — tag it as the spot row.
  const ladder: GammaLevel[] = (levels?.levels ?? [])
    .slice()
    .sort((a, b) => b.strike - a.strike);
  const spotStrike =
    spot > 0 && ladder.length > 0
      ? ladder.reduce((best, l) =>
          Math.abs(l.strike - spot) < Math.abs(best.strike - spot) ? l : best,
        ).strike
      : undefined;

  // Diverging scale — split net_gamma into a put side (negative) and call
  // side (positive) using the classified per-strike net_gamma sign.
  const maxAbs = ladder.reduce((m, l) => Math.max(m, Math.abs(l.net_gamma)), 0) || 1;

  return (
    <div className="flex flex-col overflow-hidden rounded-xl bg-[var(--surface-2)]">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 px-3.5 py-3">
        <div className="flex items-baseline gap-2.5">
          <h3 className="text-[15px] font-semibold text-[var(--on-surface)]">{symbol}</h3>
          {spot > 0 && (
            <span className="text-[15px] font-semibold text-[var(--on-surface)]">
              {spot.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </span>
          )}
        </div>
        {king !== undefined && (
          <span
            className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
            style={{ background: 'rgba(255,184,0,0.12)', color: '#ffb800' }}
          >
            King {king.toFixed(king % 1 === 0 ? 0 : 2)}
          </span>
        )}
      </div>

      {/* Body */}
      {loading && (
        <div className="px-3.5 py-10 text-center text-xs text-[var(--on-surface-muted)]">
          Loading {symbol} levels…
        </div>
      )}

      {!loading && failed && (
        <div className="px-3.5 py-10 text-center text-xs text-[var(--on-surface-muted)]">
          No gamma levels available for {symbol}.
        </div>
      )}

      {!loading && !failed && ladder.length === 0 && (
        <div className="px-3.5 py-10 text-center text-xs text-[var(--on-surface-muted)]">
          Chain too thin to build a ladder for {symbol}.
        </div>
      )}

      {!loading && !failed && ladder.length > 0 && (
        <div className="py-1">
          {/* Column header */}
          <div className="grid grid-cols-[54px_1fr_1fr] gap-1 px-3 pb-1.5 text-[9px] font-semibold uppercase tracking-wider text-[var(--on-surface-label)]">
            <span>Strike</span>
            <span className="text-right">Put GEX</span>
            <span className="text-left">Call GEX</span>
          </div>
          <div className="max-h-[520px] overflow-y-auto">
            {ladder.map(r => {
              const isKing = r.strike === king;
              const isSpot = r.strike === spotStrike;
              const net = r.net_gamma;
              const putW = net < 0 ? (Math.abs(net) / maxAbs) * 100 : 0;
              const callW = net >= 0 ? (net / maxAbs) * 100 : 0;
              const rowBg = isSpot
                ? 'rgba(139,206,255,0.10)'
                : isKing
                ? 'rgba(255,184,0,0.08)'
                : 'transparent';
              const strikeColor = isSpot ? 'var(--brand)' : isKing ? '#ffb800' : 'var(--on-surface-variant)';
              return (
                <div
                  key={r.strike}
                  className="grid grid-cols-[54px_1fr_1fr] items-center gap-1 px-3 py-[2px]"
                  style={{ background: rowBg }}
                  title={`Net GEX ${formatGEX(r.gex)} · OI ${r.call_oi}c / ${r.put_oi}p`}
                >
                  <span
                    className="of-tabnum text-[11px] font-bold"
                    style={{ color: strikeColor }}
                  >
                    {r.strike.toFixed(r.strike % 1 === 0 ? 0 : 1)}
                    {isKing ? ' ♔' : ''}
                  </span>
                  {/* put side — grows leftward */}
                  <div className="flex justify-end">
                    <div
                      className="h-3 rounded-l-sm"
                      style={{ width: `${putW}%`, background: 'var(--bear)', opacity: 0.55 }}
                    />
                  </div>
                  {/* call side — grows rightward */}
                  <div className="flex justify-start">
                    <div
                      className="h-3 rounded-r-sm"
                      style={{ width: `${callW}%`, background: 'var(--bull)', opacity: 0.55 }}
                    />
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

export default function TrinityTab() {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-2.5">
        <h3 className="text-sm font-semibold text-[var(--on-surface)]">
          Trinity · synced index gamma
        </h3>
        <span className="text-xs text-[var(--on-surface-muted)]">
          SPX · SPY · QQQ — strike ladders aligned
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {TRINITY_SYMBOLS.map(sym => (
          <TrinityPanel key={sym} symbol={sym} />
        ))}
      </div>

      <div className="rounded-xl border border-dashed border-[var(--outline-variant)] bg-transparent p-4">
        <div className="text-[11.5px] leading-relaxed text-[var(--on-surface-variant)]">
          <strong className="text-[var(--on-surface)]">Trinity</strong> aligns the three index
          proxies so you can confirm whether SPX, SPY and QQQ gamma structure agree. When all
          three Kings sit above spot, dealer positioning favors upside pinning; divergence flags a
          regime that's still resolving.
        </div>
      </div>
    </div>
  );
}
