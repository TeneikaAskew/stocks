/**
 * LeverageCurveChart — visual answer to "why does +0.41% matter?".
 *
 * Plots stock-price movement (x) against option gain/loss (y) at three
 * strike-distance anchors so users can see at a glance how a small stock
 * move translates into a meaningful option return. The middle line
 * (slightly-OTM, ~0.35Δ) is the default highlight; ATM and deep-OTM
 * bracket it.
 *
 * Linear-delta approximation only — real option math (gamma curvature,
 * theta drag) lands in Phase 2 via lib/contract_metrics.py.
 */

import { useMemo } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  Legend,
} from 'recharts';
import { useChartTheme } from '@/lib/chartTheme';

interface LeverageCurveChartProps {
  /**
   * Optional marker for the user's actual avg-win or avg-loss to overlay on
   * the curve as a vertical reference line. Fractional (e.g. 0.0041).
   */
  highlightStockMovePct?: number;
  /** Chart height in px. Defaults to 220 for a compact card embed. */
  height?: number;
}

const DELTAS = [
  { name: 'ATM (~0.50Δ, 1 strike)', delta: 0.5, color: 'bull' as const },
  { name: 'Slightly OTM (~0.35Δ, 5–7 strikes)', delta: 0.35, color: 'brand' as const },
  { name: 'OTM (~0.20Δ, ~10 strikes)', delta: 0.2, color: 'warn' as const },
];

const X_RANGE_PCT = 0.6; // -0.6% to +0.6%
const POINTS = 25;

interface Row {
  stock: number;
  atm: number;
  slightOtm: number;
  otm: number;
}

function buildSeries(): Row[] {
  const rows: Row[] = [];
  const step = (X_RANGE_PCT * 2) / (POINTS - 1);
  for (let i = 0; i < POINTS; i += 1) {
    const stock = -X_RANGE_PCT + i * step;
    rows.push({
      stock: Number(stock.toFixed(3)),
      atm: Number((stock * 0.5).toFixed(4)),
      slightOtm: Number((stock * 0.35).toFixed(4)),
      otm: Number((stock * 0.2).toFixed(4)),
    });
  }
  return rows;
}

export function LeverageCurveChart({
  highlightStockMovePct,
  height = 220,
}: LeverageCurveChartProps) {
  const theme = useChartTheme();
  const data = useMemo(buildSeries, []);

  const lineColors: Record<typeof DELTAS[number]['color'], string> = {
    bull: theme.bull,
    brand: theme.brand,
    warn: theme.warn,
  };

  const fmtAxis = (v: number) =>
    `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`;
  const fmtTooltipPct = (v: number) =>
    `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`;

  return (
    <div className="rounded-xl bg-[var(--surface-2)] p-5">
      <div className="mb-1 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--on-surface)]">
          How a stock move turns into option profit
        </h3>
        <span className="text-[10px] text-[var(--on-surface-muted)]">
          Linear delta estimate · real contract math in Phase 2
        </span>
      </div>
      <p className="mb-3 text-xs text-[var(--on-surface-muted)]">
        Each line is a strike distance from spot. A +0.41% stock move with a
        slightly-OTM option (~0.35Δ, 5–7 strikes from spot) translates to
        roughly +0.14% on the contract — small as a percent of premium, but
        every contract is 100 shares so dollar P&amp;L scales fast.
      </p>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart
          data={data}
          margin={{ top: 8, right: 16, bottom: 4, left: 0 }}
        >
          <CartesianGrid stroke={theme.grid} strokeDasharray="3 3" />
          <XAxis
            dataKey="stock"
            tick={{ fill: theme.axis, fontSize: theme.axisSize }}
            tickFormatter={fmtAxis}
            label={{
              value: 'Stock price movement',
              position: 'insideBottom',
              offset: -2,
              fill: theme.textLabel,
              fontSize: 10,
            }}
          />
          <YAxis
            tick={{ fill: theme.axis, fontSize: theme.axisSize }}
            tickFormatter={fmtAxis}
            label={{
              value: 'Option gain / loss',
              angle: -90,
              position: 'insideLeft',
              fill: theme.textLabel,
              fontSize: 10,
            }}
          />
          <Tooltip
            contentStyle={{
              background: theme.tooltipBg,
              border: `1px solid ${theme.border}`,
              borderRadius: 8,
              color: theme.tooltipText,
              fontSize: 11,
            }}
            labelFormatter={(v) => `Stock move: ${fmtTooltipPct(Number(v))}`}
            formatter={(v: number, name: string) => [fmtTooltipPct(v), name]}
          />
          <Legend
            iconType="plainline"
            wrapperStyle={{ fontSize: 10, color: theme.textMuted }}
          />
          <ReferenceLine x={0} stroke={theme.border} />
          <ReferenceLine y={0} stroke={theme.border} />
          {highlightStockMovePct !== undefined && (
            <ReferenceLine
              x={highlightStockMovePct}
              stroke={theme.brandGlow}
              strokeDasharray="4 4"
              label={{
                value: `your avg: ${fmtTooltipPct(highlightStockMovePct)}`,
                fill: theme.brandGlow,
                fontSize: 10,
                position: 'top',
              }}
            />
          )}
          <Line
            type="linear"
            dataKey="atm"
            name={DELTAS[0].name}
            stroke={lineColors.bull}
            strokeWidth={1.5}
            dot={false}
          />
          <Line
            type="linear"
            dataKey="slightOtm"
            name={DELTAS[1].name}
            stroke={lineColors.brand}
            strokeWidth={2.25}
            dot={false}
          />
          <Line
            type="linear"
            dataKey="otm"
            name={DELTAS[2].name}
            stroke={lineColors.warn}
            strokeWidth={1.5}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
