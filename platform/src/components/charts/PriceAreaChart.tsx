/**
 * PriceAreaChart — clean line+area chart for hourly price history.
 *
 * Matches the NVDA reference screenshot: brand-colored line, translucent
 * gradient fill beneath, subtle horizontal grid, minimal axis chrome,
 * optional session-boundary dashed vertical line.
 *
 * Used by the Dashboard's Market Overview section.
 */
import { useMemo } from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts';
import { chartTheme } from '@/lib/chartTheme';

export interface PricePoint {
  /** Unix seconds for the bar open */
  time: number;
  /** Close price for the hourly bar */
  price: number;
  /** Formatted label shown on the x-axis (e.g. "03/24 04:00") */
  label: string;
}

interface PriceAreaChartProps {
  data: PricePoint[];
  height?: number;
  /** Label shown in the legend row (e.g. "NVDA close price") */
  seriesLabel?: string;
  /**
   * Unix seconds where the session boundary falls. A vertical dashed line
   * is drawn there with a "Mar 25" style label if provided.
   */
  sessionBoundary?: { time: number; label: string } | null;
  /** Show dots at every point. Automatically disabled when data.length > 40. */
  showDots?: boolean;
}

interface TooltipEntry { value?: number | string }
interface PriceTooltipProps {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string;
}

/** Custom dark tooltip matching the Obsidian Analyst design system. */
function PriceTooltip({ active, payload, label }: PriceTooltipProps) {
  if (!active || !payload || !payload.length) return null;
  const value = payload[0].value;
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{
        background: 'rgba(10, 12, 16, 0.95)',
        border: `1px solid ${chartTheme.border}`,
        backdropFilter: 'blur(8px)',
      }}
    >
      <div style={{ color: chartTheme.textMuted, marginBottom: 2 }}>{label}</div>
      <div style={{ color: '#e2e2e8', fontWeight: 600 }}>
        ${Number(value ?? 0).toFixed(2)}
      </div>
    </div>
  );
}

export function PriceAreaChart({
  data,
  height = 280,
  seriesLabel = 'Close price',
  sessionBoundary = null,
  showDots = true,
}: PriceAreaChartProps) {
  // Compute Y-axis domain with 2% padding so the line doesn't hug the card edges
  const yDomain = useMemo<[number, number]>(() => {
    if (!data.length) return [0, 1];
    const prices = data.map((d) => d.price);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const pad = (max - min) * 0.08 || 1;
    return [min - pad, max + pad];
  }, [data]);

  // Auto-disable dots when there are too many points (would look cluttered)
  const renderDots = showDots && data.length <= 40;

  if (!data.length) {
    return (
      <div
        className="flex items-center justify-center rounded-lg text-xs"
        style={{ height, color: chartTheme.textLabel }}
      >
        No price data available
      </div>
    );
  }

  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart
          data={data}
          margin={{ top: 8, right: 24, bottom: 12, left: 0 }}
        >
          <defs>
            <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={chartTheme.brand} stopOpacity={0.35} />
              <stop offset="100%" stopColor={chartTheme.brand} stopOpacity={0} />
            </linearGradient>
          </defs>

          {/* Subtle horizontal-only grid */}
          <CartesianGrid
            vertical={false}
            stroke={chartTheme.grid}
            strokeDasharray="3 4"
          />

          <XAxis
            dataKey="label"
            tick={{
              fontSize: chartTheme.axisSize,
              fill: chartTheme.axis,
              fontFamily: 'Montserrat, sans-serif',
            }}
            axisLine={false}
            tickLine={false}
            minTickGap={48}
            angle={-30}
            textAnchor="end"
            height={40}
          />

          <YAxis
            domain={yDomain}
            orientation="left"
            tick={{
              fontSize: chartTheme.axisSize,
              fill: chartTheme.axis,
              fontFamily: 'Montserrat, sans-serif',
            }}
            axisLine={false}
            tickLine={false}
            width={56}
            tickFormatter={(v) => `$${Number(v).toFixed(0)}`}
          />

          <Tooltip
            content={<PriceTooltip />}
            cursor={{
              stroke: chartTheme.brand,
              strokeWidth: 1,
              strokeDasharray: '3 3',
            }}
          />

          {/* Session boundary (optional) */}
          {sessionBoundary && (
            <ReferenceLine
              x={data.find((d) => d.time === sessionBoundary.time)?.label}
              stroke={chartTheme.textLabel}
              strokeDasharray="4 4"
              strokeOpacity={0.6}
              label={{
                value: sessionBoundary.label,
                position: 'top',
                fill: chartTheme.textMuted,
                fontSize: 10,
                fontFamily: 'Montserrat, sans-serif',
              }}
            />
          )}

          <Area
            type="monotone"
            dataKey="price"
            stroke={chartTheme.brand}
            strokeWidth={2}
            fill="url(#priceGrad)"
            dot={
              renderDots
                ? { r: 3, fill: chartTheme.brand, stroke: chartTheme.brand, strokeWidth: 0 }
                : false
            }
            activeDot={{
              r: 5,
              fill: chartTheme.brand,
              stroke: '#0a0c10',
              strokeWidth: 2,
            }}
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Legend row under the chart — matches NVDA reference */}
      <div className="mt-2 flex items-center gap-5 text-xs">
        <span className="flex items-center gap-2" style={{ color: chartTheme.textMuted }}>
          <span
            className="inline-block"
            style={{
              width: 14,
              height: 2,
              background: chartTheme.brand,
              borderRadius: 1,
            }}
          />
          {seriesLabel}
        </span>
        {sessionBoundary && (
          <span className="flex items-center gap-2" style={{ color: chartTheme.textMuted }}>
            <span
              className="inline-block"
              style={{
                width: 14,
                borderTop: `1px dashed ${chartTheme.textLabel}`,
              }}
            />
            Session boundary
          </span>
        )}
      </div>
    </div>
  );
}
