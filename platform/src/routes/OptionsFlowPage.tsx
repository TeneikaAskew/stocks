import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTickerStore } from '@/stores/tickerStore';
import { MetricCard } from '@/components/shared/MetricCard';
import { useGammaGrid } from '@/hooks/useGammaGrid';
import { GammaGrid } from '@/components/options/GammaGrid';
import { formatGex } from '@/lib/formatGex';
import {
  useGammaLevels,
  spotMethodLabel,
  regimeLabel,
} from '@/hooks/useGammaLevels';
import { ChevronLeft, ChevronRight, AlertTriangle, Info, Minus, Plus } from 'lucide-react';

type Metric = 'gex' | 'vex';
type Filter = 'net' | 'calls' | 'puts';

interface AvailableDatesResponse {
  ticker: string;
  dates: string[];
}

async function parseApiError(r: Response, fallback: string): Promise<string> {
  try {
    const body = await r.json();
    if (typeof body?.detail === 'string') return body.detail;
    if (Array.isArray(body?.detail)) return body.detail.map((d: { msg?: string }) => d.msg ?? '').join('; ');
  } catch {
    // body wasn't JSON
  }
  return `${fallback} (HTTP ${r.status})`;
}

function useOptionsDates(ticker: string) {
  return useQuery<AvailableDatesResponse>({
    queryKey: ['options-dates', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/options/dates/${ticker}`);
      if (!r.ok) throw new Error(await parseApiError(r, 'Failed to fetch options dates'));
      return r.json();
    },
    staleTime: 300_000,
    retry: false,
  });
}

const MIN_WINDOW = 1;
const MAX_WINDOW = 15;
// Show the nearest N expiration columns by default (LEAPS out to 2028 add noise).
const GRID_MAX_EXPIRATIONS = 12;

// ── Main Page ─────────────────────────────────────────────────────────────
export default function OptionsFlowPage() {
  const { activeTicker } = useTickerStore();
  const [metric, setMetric] = useState<Metric>('gex');
  const [filter, setFilter] = useState<Filter>('net');
  const [dateIdx, setDateIdx] = useState(0);
  // Tighter default than the old ±15% so the spot region is visible without
  // scrolling. The grid endpoint clamps to [0.5, 50].
  const [windowPct, setWindowPct] = useState(4);

  const {
    data: datesData,
    isLoading: datesLoading,
    isError: datesError,
    error: datesErrorObj,
  } = useOptionsDates(activeTicker);
  // Reset to the most-recent date when the ticker changes (React-recommended
  // "adjust state during render" pattern — avoids a setState-in-effect cascade).
  const [prevTicker, setPrevTicker] = useState(activeTicker);
  if (prevTicker !== activeTicker) {
    setPrevTicker(activeTicker);
    setDateIdx(0);
  }

  const dates = datesData?.dates ?? [];
  const selectedDate = dates[dateIdx] ?? '';
  // dateIdx 0 = most recent snapshot → live endpoint (carries the session-open
  // %-change overlay). Older dates → immutable historical EOD grid (no change).
  const isLive = dateIdx === 0;

  const gridQuery = useGammaGrid(activeTicker, selectedDate, {
    windowPct,
    live: isLive,
    enabled: dates.length > 0,
  });
  const summary = gridQuery.data;
  const finalSpot = summary?.spot?.price ?? 0;
  const hasGrid = !!summary && summary.cells.length > 0 && finalSpot > 0;

  // King/Gate/Flip taxonomy badges come from the chain-source-aware /levels
  // endpoint (server-side put-call-parity spot + classified levels).
  const levelsQuery = useGammaLevels(activeTicker, selectedDate, {
    windowPct: 8,
    enabled: dates.length > 0 && !!selectedDate,
  });
  const gammaLevels = levelsQuery.data;

  const regime = summary?.regime ?? 'unknown';
  const gammaFlip = summary?.gamma_flip ?? null;
  const gammaBalance = summary?.gamma_balance ?? null;
  const spotMethod = summary?.spot?.method;
  const dataSource = summary?.data_source;

  const displayMetricGex = metric === 'gex' ? (summary?.total_gex ?? 0) : (summary?.total_vex ?? 0);
  const kingStrike = gammaLevels?.kings?.[0]?.strike;

  // Put/Call OI ratio from the visible grid cells.
  const { callOI, putOI } = (summary?.cells ?? []).reduce(
    (acc, c) => ({ callOI: acc.callOI + (c.call_oi || 0), putOI: acc.putOI + (c.put_oi || 0) }),
    { callOI: 0, putOI: 0 },
  );
  const pcRatio = callOI > 0 ? putOI / callOI : 0;

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Metric toggle */}
        <div className="flex rounded border border-[var(--color-border)] overflow-hidden">
          {(['gex', 'vex'] as Metric[]).map(m => (
            <button
              key={m}
              onClick={() => setMetric(m)}
              className={`px-3 py-1.5 text-xs font-medium ${
                metric === m
                  ? 'bg-[var(--color-accent-blue)] text-[var(--on-brand)]'
                  : 'bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)]'
              }`}
            >
              {m.toUpperCase()}
            </button>
          ))}
        </div>

        {/* Filter toggle */}
        <div className="flex rounded border border-[var(--color-border)] overflow-hidden">
          {(['net', 'calls', 'puts'] as Filter[]).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 text-xs font-medium capitalize ${
                filter === f
                  ? 'bg-[var(--color-accent-blue)] text-[var(--on-brand)]'
                  : 'bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)]'
              }`}
            >
              {f}
            </button>
          ))}
        </div>

        {/* Date navigation */}
        <div className="flex items-center gap-1 rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-2">
          <button
            onClick={() => setDateIdx(i => Math.min(dates.length - 1, i + 1))}
            disabled={dateIdx >= dates.length - 1}
            className="p-1 disabled:opacity-40"
            title="Older snapshot"
          >
            <ChevronLeft size={14} />
          </button>
          <span className="min-w-[90px] text-center text-xs font-mono">
            {selectedDate || 'No dates'}
          </span>
          <button
            onClick={() => setDateIdx(i => Math.max(0, i - 1))}
            disabled={dateIdx <= 0}
            className="p-1 disabled:opacity-40"
            title="Newer snapshot"
          >
            <ChevronRight size={14} />
          </button>
        </div>

        {/* Strike window stepper */}
        <div className="flex items-center gap-1 rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-2">
          <span className="text-xs text-[var(--color-text-muted)]">Range</span>
          <button
            onClick={() => setWindowPct(w => Math.max(MIN_WINDOW, w - 1))}
            disabled={windowPct <= MIN_WINDOW}
            className="p-1 disabled:opacity-40"
          >
            <Minus size={12} />
          </button>
          <span className="min-w-[34px] text-center text-xs font-mono">±{windowPct}%</span>
          <button
            onClick={() => setWindowPct(w => Math.min(MAX_WINDOW, w + 1))}
            disabled={windowPct >= MAX_WINDOW}
            className="p-1 disabled:opacity-40"
          >
            <Plus size={12} />
          </button>
        </div>

        {/* Spot (read-only, server-estimated) */}
        {finalSpot > 0 && (
          <div className="flex items-center gap-1 text-xs">
            <span className="text-[var(--color-text-muted)]">Spot</span>
            <span className="font-mono font-semibold text-[var(--color-text-primary)]">
              ${finalSpot.toFixed(2)}
            </span>
            {spotMethod && (
              <span
                className="ml-0.5 rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-1.5 py-0.5 text-[10px] text-[var(--color-text-muted)]"
                title={spotMethodLabel(spotMethod)}
              >
                {spotMethod}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Error surfacing */}
      {datesError && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-[var(--warn)]">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">No options dates available for {activeTicker}</div>
            <div className="mt-1 text-xs text-[var(--warn)]/90">
              {(datesErrorObj as Error | undefined)?.message ?? 'Unknown error'}
            </div>
          </div>
        </div>
      )}

      {gridQuery.isError && !datesError && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-[var(--warn)]">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">Gamma grid unavailable</div>
            <div className="mt-1 text-xs text-[var(--warn)]/90">
              {(gridQuery.error as Error | undefined)?.message ?? 'Unknown error'}
            </div>
          </div>
        </div>
      )}

      {(datesLoading || gridQuery.isLoading) && (
        <div className="rounded-xl bg-[var(--surface-2)] p-8 text-center text-sm text-[var(--color-text-muted)]">
          {datesLoading ? 'Loading available dates…' : 'Loading gamma grid…'}
        </div>
      )}

      {/* Data-source / freshness chip */}
      {summary && dataSource && dataSource !== 'unavailable' && (
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--color-text-muted)]">
          <span
            className={`rounded border px-2 py-0.5 font-medium ${
              dataSource === 'realtime'
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
                : 'border-[var(--color-border)] bg-[var(--surface-2)] text-[var(--color-text-muted)]'
            }`}
          >
            {dataSource === 'realtime'
              ? 'Live · intraday'
              : 'EOD snapshot — intraday change unavailable'}
          </span>
          {summary.snapshot_ts && (
            <span>as of {summary.snapshot_ts.slice(0, 16).replace('T', ' ')} UTC</span>
          )}
        </div>
      )}

      {/* Server-side warnings */}
      {summary?.warnings && summary.warnings.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-blue-500/30 bg-blue-500/10 p-3 text-xs text-blue-300">
          <Info size={14} className="mt-0.5 shrink-0" />
          <div>
            {summary.warnings.map((w, i) => <div key={i}>{w}</div>)}
          </div>
        </div>
      )}

      {/* Metrics bar */}
      {hasGrid && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <MetricCard
            label={`Total ${metric.toUpperCase()}`}
            value={formatGex(displayMetricGex)}
            change={displayMetricGex >= 0 ? 1 : -1}
            changeLabel={displayMetricGex >= 0 ? 'Positive' : 'Negative'}
          />
          <MetricCard
            label="Gamma Flip"
            value={gammaFlip ? `$${gammaFlip.toFixed(2)}` : '--'}
            changeLabel={gammaFlip ? regimeLabel(regime).description : undefined}
          />
          <MetricCard
            label="Gamma Balance"
            value={gammaBalance ? `$${gammaBalance.toFixed(2)}` : '--'}
            changeLabel={gammaBalance ? 'Cumulative-gamma balance' : undefined}
          />
          <MetricCard
            label="Put/Call OI"
            value={pcRatio > 0 ? pcRatio.toFixed(2) : '--'}
            change={pcRatio > 1 ? -1 : 1}
            changeLabel={pcRatio > 1 ? 'Bearish skew' : 'Bullish skew'}
          />
        </div>
      )}

      {/* Regime + Levels taxonomy (King/Gate/Flip) */}
      {gammaLevels && hasGrid && (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {regime !== 'unknown' && (
            <span
              className={`rounded border px-2 py-1 font-semibold ${
                regimeLabel(regime).tone === 'positive'
                  ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
                  : regimeLabel(regime).tone === 'negative'
                  ? 'border-rose-500/30 bg-rose-500/10 text-rose-400'
                  : 'border-[var(--color-border)] bg-[var(--surface-2)] text-[var(--color-text-muted)]'
              }`}
              title={regimeLabel(regime).description}
            >
              {regimeLabel(regime).label}
            </span>
          )}
          {gammaLevels.kings.map(k => (
            <span
              key={`king-${k.strike}`}
              className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-amber-400"
              title={`Net GEX ${formatGex(k.gex)} · OI ${k.call_oi}c / ${k.put_oi}p`}
            >
              ★ King ${k.strike.toFixed(2)}{' '}
              <span className="text-[10px] opacity-70">
                ({k.distance_pct >= 0 ? '+' : ''}{k.distance_pct.toFixed(1)}%)
              </span>
            </span>
          ))}
          {gammaLevels.gates.map(g => (
            <span
              key={`gate-${g.strike}`}
              className="rounded border border-blue-500/30 bg-blue-500/10 px-2 py-1 text-blue-400"
              title={`Net GEX ${formatGex(g.gex)} · OI ${g.call_oi}c / ${g.put_oi}p`}
            >
              ◆ Gate ${g.strike.toFixed(2)}
            </span>
          ))}
          {gammaLevels.gamma_balance_levels.map(f => (
            <span
              key={`gamma-balance-${f.strike}`}
              className="rounded border border-violet-500/30 bg-violet-500/10 px-2 py-1 text-violet-400"
              title={`Adjacent to gamma balance @ ${gammaBalance?.toFixed(2) ?? '--'}`}
            >
              ⇅ Flip ${f.strike.toFixed(2)}
            </span>
          ))}
        </div>
      )}

      {/* 2-D Grid */}
      {hasGrid && (
        <div className="rounded-xl bg-[var(--surface-2)] p-3">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-[var(--color-text-muted)]">
              {metric.toUpperCase()} by Strike × Expiration — {filter === 'net' ? 'Net' : filter === 'calls' ? 'Calls' : 'Puts'} — ±{windowPct}% range ({summary!.strikes.length} strikes × {Math.min(GRID_MAX_EXPIRATIONS, summary!.expirations.length)} of {summary!.expirations.length} expirations)
            </span>
            <div className="flex flex-wrap gap-3 text-[10px] text-[var(--color-text-muted)]">
              <span className="text-[var(--bull)]">■ Positive</span>
              <span className="text-[var(--brand)]">■ Negative</span>
              <span className="text-[var(--color-accent-amber)]">★ King</span>
              <span className="text-[var(--bear)]">▬ Spot row</span>
              {dataSource === 'realtime' && <span>% = intraday Δ vs open</span>}
            </div>
          </div>
          <GammaGrid summary={summary!} metric={metric} filter={filter} kingStrike={kingStrike} maxExpirations={GRID_MAX_EXPIRATIONS} />
        </div>
      )}

      {/* Empty state */}
      {!gridQuery.isLoading && !gridQuery.isError && !datesError && summary && summary.cells.length === 0 && selectedDate && (
        <div className="rounded-xl bg-[var(--surface-2)] p-8 text-center text-sm text-[var(--color-text-muted)]">
          <div className="font-semibold">No gamma grid data for {activeTicker} on {selectedDate}</div>
          <div className="mt-2 text-xs">
            {summary.reason ?? 'Try a different date or widen the strike range.'}
          </div>
        </div>
      )}
    </div>
  );
}
