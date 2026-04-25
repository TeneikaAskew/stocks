import { useState, useEffect, useRef, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTickerStore } from '@/stores/tickerStore';
import { MetricCard } from '@/components/shared/MetricCard';
import {
  useOptionsGreeks,
  EMPTY_GREEKS,
  type OptionRecord,
  type GEXByStrike,
  type NodeResult,
} from '@/hooks/useOptionsGreeks';
import * as d3 from 'd3';
import { ChevronLeft, ChevronRight, AlertTriangle } from 'lucide-react';

type Metric = 'gex' | 'vex';
type Filter = 'net' | 'calls' | 'puts';

interface OptionsResponse {
  ticker: string;
  date: string;
  options: OptionRecord[];
  snapshot_timestamp?: string;
  metadata?: { source?: string; data_source?: string; row_count?: number };
}

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

function useOptionsData(ticker: string, date: string, enabled: boolean) {
  return useQuery<OptionsResponse>({
    queryKey: ['options', ticker, date],
    queryFn: async () => {
      const r = await fetch(`/api/options/${ticker}/${date}`);
      if (!r.ok) throw new Error(await parseApiError(r, 'Failed to fetch options data'));
      return r.json();
    },
    enabled: enabled && !!ticker && !!date,
    staleTime: 3_600_000, // 1 hour
    retry: false,
  });
}

// ── D3 Heatmap ────────────────────────────────────────────────────────────
interface HeatmapProps {
  gexData: GEXByStrike[];
  spotPrice: number;
  filter: Filter;
  nodes: NodeResult;
  atmTolerance: number;
}

function GEXHeatmap({ gexData, spotPrice, filter, nodes, atmTolerance }: HeatmapProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  const renderHeatmap = useCallback(() => {
    if (!containerRef.current || gexData.length === 0) return;

    const container = containerRef.current;
    container.innerHTML = '';

    const margin = { top: 8, right: 80, bottom: 8, left: 60 };
    const width = container.clientWidth - margin.left - margin.right;
    const rowHeight = Math.max(18, Math.min(28, Math.floor(540 / gexData.length)));
    const height = gexData.length * rowHeight;

    const svg = d3
      .select(container)
      .append('svg')
      .attr('width', width + margin.left + margin.right)
      .attr('height', height + margin.top + margin.bottom);

    const g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    // Get display values based on filter
    const values = gexData.map(d =>
      filter === 'calls' ? d.call_gex : filter === 'puts' ? d.put_gex : d.gex
    );

    const maxAbs = d3.max(values.map(Math.abs)) ?? 1;
    const xScale = d3.scaleLinear().domain([-maxAbs, maxAbs]).range([0, width]);
    const yScale = d3.scaleBand()
      .domain(gexData.map(d => String(d.strike)))
      .range([0, height])
      .padding(0.15);

    const zero = xScale(0);

    // Color scales: positive = green→emerald, negative = purple
    const posColorScale = d3.scaleSequential(d3.interpolateRgb('#065f46', '#34d399'))
      .domain([0, maxAbs]);
    const negColorScale = d3.scaleSequential(d3.interpolateRgb('#4c1d95', '#a78bfa'))
      .domain([0, maxAbs]);

    // Draw bars
    gexData.forEach((d, i) => {
      const val = values[i];
      const strikeKey = String(d.strike);
      const y = yScale(strikeKey) ?? 0;
      const bh = yScale.bandwidth();
      const x = val >= 0 ? zero : xScale(val);
      const bw = Math.abs(xScale(val) - zero);
      const color = val >= 0 ? posColorScale(val) : negColorScale(Math.abs(val));

      // Node badge lookup
      const isKing = nodes.kingNode?.strike === d.strike;
      const isGatekeeper = nodes.gatekeepers.some(n => n.strike === d.strike);
      const isMidpoint = nodes.midpoints.some(
        n => n.lower_bound! <= d.strike && d.strike <= n.upper_bound!
      );

      // Background row (for readability)
      g.append('rect')
        .attr('x', 0)
        .attr('y', y)
        .attr('width', width)
        .attr('height', bh)
        .attr('fill', i % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent');

      // Bar
      if (bw > 0) {
        g.append('rect')
          .attr('x', x)
          .attr('y', y + 2)
          .attr('width', bw)
          .attr('height', bh - 4)
          .attr('fill', color)
          .attr('rx', 2);
      }

      // Strike label (left)
      g.append('text')
        .attr('x', -4)
        .attr('y', y + bh / 2)
        .attr('dy', '0.35em')
        .attr('text-anchor', 'end')
        .attr('font-size', rowHeight < 20 ? 9 : 10)
        .attr('fill', Math.abs(spotPrice - d.strike) / spotPrice < atmTolerance ? '#f59e0b' : '#6b7280')
        .text(d.strike.toFixed(0));

      // Value label (right)
      if (Math.abs(val) > maxAbs * 0.05) {
        g.append('text')
          .attr('x', width + 4)
          .attr('y', y + bh / 2)
          .attr('dy', '0.35em')
          .attr('font-size', 9)
          .attr('fill', val >= 0 ? '#34d399' : '#a78bfa')
          .text(formatGEX(val));
      }

      // Node badge
      if (isKing || isGatekeeper || isMidpoint) {
        const badge = isKing ? '★' : isGatekeeper ? '◆' : '●';
        const badgeColor = isKing ? '#f59e0b' : isGatekeeper ? '#60a5fa' : '#fb923c';
        g.append('text')
          .attr('x', zero + 4)
          .attr('y', y + bh / 2)
          .attr('dy', '0.35em')
          .attr('font-size', 10)
          .attr('fill', badgeColor)
          .text(badge);
      }
    });

    // Zero line
    g.append('line')
      .attr('x1', zero)
      .attr('x2', zero)
      .attr('y1', 0)
      .attr('y2', height)
      .attr('stroke', '#4b5563')
      .attr('stroke-width', 1)
      .attr('stroke-dasharray', '3,3');

    // Current price line
    const nearestStrike = gexData.reduce((best, d) =>
      Math.abs(d.strike - spotPrice) < Math.abs(best.strike - spotPrice) ? d : best
    );
    const priceY = (yScale(String(nearestStrike.strike)) ?? 0) + yScale.bandwidth() / 2;

    g.append('line')
      .attr('x1', 0)
      .attr('x2', width)
      .attr('y1', priceY)
      .attr('y2', priceY)
      .attr('stroke', '#ef4444')
      .attr('stroke-width', 1.5)
      .attr('stroke-dasharray', '4,2');

    g.append('text')
      .attr('x', width + 4)
      .attr('y', priceY)
      .attr('dy', '0.35em')
      .attr('font-size', 9)
      .attr('fill', '#ef4444')
      .text(`$${spotPrice.toFixed(2)}`);
  }, [gexData, spotPrice, filter, nodes, atmTolerance]);

  useEffect(() => {
    renderHeatmap();
    const observer = new ResizeObserver(renderHeatmap);
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [renderHeatmap]);

  return (
    <div
      ref={containerRef}
      className="w-full overflow-y-auto"
      style={{ minHeight: 200, maxHeight: 600 }}
    />
  );
}

function formatGEX(val: number): string {
  const abs = Math.abs(val);
  const sign = val >= 0 ? '+' : '-';
  if (abs >= 1_000_000) return `${sign}${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${sign}${(abs / 1_000).toFixed(0)}K`;
  return `${sign}${abs.toFixed(0)}`;
}

// ── Main Page ─────────────────────────────────────────────────────────────
export default function OptionsFlowPage() {
  const { activeTicker } = useTickerStore();
  const [metric, setMetric] = useState<Metric>('gex');
  const [filter, setFilter] = useState<Filter>('net');
  const [dateIdx, setDateIdx] = useState(0);
  const [spotOverride, setSpotOverride] = useState<string>('');

  const {
    data: datesData,
    isLoading: datesLoading,
    isError: datesError,
    error: datesErrorObj,
  } = useOptionsDates(activeTicker);
  const dates = datesData?.dates ?? [];
  const selectedDate = dates[dateIdx] ?? '';

  const {
    data: optionsData,
    isLoading,
    isError,
    error: optionsErrorObj,
  } = useOptionsData(activeTicker, selectedDate, dates.length > 0);

  // Reset to first date when ticker changes
  useEffect(() => setDateIdx(0), [activeTicker]);

  const options: OptionRecord[] = optionsData?.options ?? [];

  // Compute spot price (override or estimate from ATM options)
  const estimatedSpot = options.length > 0
    ? options.reduce((best, o) => {
        const delta = Math.abs((o.delta ?? 0) - (o.type === 'call' ? 0.5 : -0.5));
        const bestDelta = Math.abs((best.delta ?? 0) - (best.type === 'call' ? 0.5 : -0.5));
        return delta < bestDelta ? o : best;
      }).strike
    : 0;

  const spotPrice = spotOverride ? parseFloat(spotOverride) : estimatedSpot;

  // All Greek/node math is server-side. See lib/indicators.py discipline —
  // we never duplicate financial math in the app.
  const greeksQuery = useOptionsGreeks(options, spotPrice);
  const greeks = greeksQuery.data ?? EMPTY_GREEKS;
  const gexData = greeks.gex_by_strike;
  const metrics = greeks.metrics;
  const nodes = greeks.nodes;
  const rangePct = greeks.config.strike_range_pct;

  // Display filter — bounded by the server's declared display range config.
  const focusedGex = spotPrice > 0
    ? gexData.filter(d => Math.abs(d.strike - spotPrice) / spotPrice <= rangePct)
    : gexData;

  const totalGex = metrics.total_gex;
  const totalVex = metrics.total_vex;

  const displayMetricGex = metric === 'gex' ? totalGex : totalVex;

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
          >
            <ChevronRight size={14} />
          </button>
        </div>

        {/* Spot override */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-[var(--color-text-muted)]">Spot:</span>
          <input
            type="number"
            value={spotOverride || (estimatedSpot > 0 ? estimatedSpot.toFixed(2) : '')}
            onChange={e => setSpotOverride(e.target.value)}
            placeholder="price"
            className="w-20 rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-2 py-1 text-xs font-mono text-[var(--color-text-primary)]"
          />
        </div>
      </div>

      {/* Error surfacing — show the real message from the API when present */}
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

      {isError && !datesError && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-[var(--warn)]">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">Options chain unavailable</div>
            <div className="mt-1 text-xs text-[var(--warn)]/90">
              {(optionsErrorObj as Error | undefined)?.message ?? 'Unknown error'}
            </div>
          </div>
        </div>
      )}

      {(datesLoading || isLoading) && (
        <div className="rounded-xl bg-[var(--surface-2)] p-8 text-center text-sm text-[var(--color-text-muted)]">
          {datesLoading ? 'Loading available dates…' : 'Loading options chain…'}
        </div>
      )}

      {/* Metrics bar */}
      {spotPrice > 0 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <MetricCard
            label={`Total ${metric.toUpperCase()}`}
            value={formatGEX(displayMetricGex)}
            change={displayMetricGex >= 0 ? 1 : -1}
            changeLabel={displayMetricGex >= 0 ? 'Positive' : 'Negative'}
          />
          <MetricCard
            label="Zero Gamma"
            value={metrics.zero_gamma ? `$${metrics.zero_gamma.toFixed(2)}` : '--'}
          />
          <MetricCard
            label="Max Pain"
            value={metrics.max_pain ? `$${metrics.max_pain.toFixed(0)}` : '--'}
          />
          <MetricCard
            label="Put/Call OI"
            value={metrics.put_call_ratio.toFixed(2)}
            change={metrics.put_call_ratio > 1 ? -1 : 1}
            changeLabel={metrics.put_call_ratio > 1 ? 'Bearish skew' : 'Bullish skew'}
          />
        </div>
      )}

      {/* Node summary */}
      {nodes.kingNode && (
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[var(--warn)]">
            ★ King: ${nodes.kingNode.strike.toFixed(0)} ({nodes.kingNode.distance_percent >= 0 ? '+' : ''}{nodes.kingNode.distance_percent.toFixed(1)}%)
          </span>
          {nodes.gatekeepers.slice(0, 3).map((gk, i) => (
            <span key={i} className="rounded border border-blue-500/30 bg-blue-500/10 px-2 py-1 text-blue-400">
              ◆ GK: ${gk.strike.toFixed(0)}
            </span>
          ))}
          {nodes.midpoints.slice(0, 2).map((mp, i) => (
            <span key={i} className="rounded border border-orange-500/30 bg-orange-500/10 px-2 py-1 text-orange-400">
              ● Mid: ${mp.strike.toFixed(0)}
            </span>
          ))}
        </div>
      )}

      {/* Heatmap */}
      {focusedGex.length > 0 && spotPrice > 0 && (
        <div className="rounded-xl bg-[var(--surface-2)] p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs text-[var(--color-text-muted)]">
              {metric.toUpperCase()} by Strike — {filter === 'net' ? 'Net' : filter === 'calls' ? 'Calls Only' : 'Puts Only'} — ±{Math.round(rangePct * 100)}% range ({focusedGex.length} strikes)
            </span>
            <div className="flex gap-3 text-[10px] text-[var(--color-text-muted)]">
              <span className="text-[var(--bull)]">■ Positive</span>
              <span className="text-violet-400">■ Negative</span>
              <span className="text-[var(--bear)]">— Spot</span>
            </div>
          </div>
          <GEXHeatmap
            gexData={focusedGex}
            spotPrice={spotPrice}
            filter={filter}
            nodes={nodes}
            atmTolerance={greeks.config.atm_tolerance}
          />
        </div>
      )}

      {!isLoading && !isError && !datesError && options.length === 0 && selectedDate && (
        <div className="rounded-xl bg-[var(--surface-2)] p-8 text-center text-sm text-[var(--color-text-muted)]">
          <div className="font-semibold">No options data returned for {activeTicker} on {selectedDate}</div>
          <div className="mt-2 text-xs">
            Try navigating to a different date using the chevrons above.
          </div>
        </div>
      )}

      {/* Source footer */}
      {optionsData && options.length > 0 && (
        <div className="text-right text-[10px] text-[var(--color-text-muted)]">
          Source: AlphaVantage EOD · Cloud SQL · {options.length} contracts · snapshot {optionsData.snapshot_timestamp?.slice(0, 10) ?? selectedDate}
        </div>
      )}
    </div>
  );
}
