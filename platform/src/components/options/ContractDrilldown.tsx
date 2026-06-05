import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { AlertTriangle } from 'lucide-react';
import { CONTRACT_DRILLDOWN, type TimeBucket } from '@/data/contractDrilldownMock';

// ContractDrilldown — Flowseeker "Contract Drilldown": a contract header, a
// stats strip, a Bid↔Ask chain-ratio bar, a volume-over-time chart (bars) with
// an overlaid average-fill price line, and a per-time-bucket detail table.
// Built from a clearly-labeled mock (src/data/contractDrilldownMock.ts) — there
// is NO backend contract-tape endpoint. A persistent demo banner makes that
// explicit.

function money(n: number): string {
  const a = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(0)}K`;
  return `${sign}$${a.toFixed(0)}`;
}

function num(n: number): string {
  return n.toLocaleString();
}

interface TooltipPayloadItem {
  dataKey?: string | number;
  value?: number | string;
  color?: string;
  name?: string;
  payload?: TimeBucket;
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: string | number;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const b = payload[0]?.payload;
  return (
    <div className="rounded-md border border-[var(--outline-variant)] bg-[var(--surface-3)] px-3 py-2 text-[11px]">
      <div className="mb-1 font-semibold text-[var(--on-surface)]">{label}</div>
      {b && (
        <div className="space-y-0.5 font-mono text-[var(--on-surface-variant)]">
          <div>Volume {num(b.volume)}</div>
          <div>Avg fill {b.avgFill.toFixed(2)}</div>
          <div>Price {b.price.toFixed(2)}</div>
          <div>RVOL {b.rvol.toFixed(1)}x</div>
        </div>
      )}
    </div>
  );
}

export default function ContractDrilldown() {
  const { header, stats, chainRatio, buckets } = CONTRACT_DRILLDOWN;

  const contractId = `${header.sym} ${header.strike} ${header.cp} ${header.expiry}`;
  const midPct = Math.max(0, 100 - chainRatio.bidPct - chainRatio.askPct);

  const statCells: { label: string; value: string }[] = [
    { label: 'Volume', value: num(stats.volume) },
    { label: 'Open Int', value: num(stats.openInterest) },
    { label: 'Avg Fill', value: `$${stats.avgFill.toFixed(2)}` },
    { label: 'Total Premium', value: money(stats.totalPremium) },
    { label: 'OTM %', value: `${stats.otmPct >= 0 ? '+' : ''}${stats.otmPct.toFixed(1)}%` },
    { label: 'Multi %', value: `${stats.multiPct}%` },
  ];

  // Bid/Mid/Ask/No-Side breakdown across the whole session (legend totals).
  const totals = buckets.reduce(
    (acc, b) => {
      acc.bid += b.bidCount;
      acc.mid += b.midCount;
      acc.ask += b.askCount;
      acc.noSide += b.noSideCount;
      return acc;
    },
    { bid: 0, mid: 0, ask: 0, noSide: 0 },
  );

  return (
    <div className="space-y-4">
      {/* Demo banner */}
      <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-[var(--warn)]">
        <AlertTriangle size={14} className="shrink-0" />
        <span className="font-semibold">Demo data — no contract-tape endpoint connected.</span>
        <span className="text-[var(--warn)]/80">Placeholder drilldown until a per-contract tape exists.</span>
      </div>

      {/* Header row */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl bg-[var(--surface-2)] px-4 py-3">
        <span className="font-mono text-lg font-bold text-[var(--on-surface)]">{header.sym}</span>
        <span className="font-mono text-lg font-semibold text-[var(--on-surface)]">${header.strike}</span>
        <span
          className="rounded px-2 py-0.5 text-xs font-bold"
          style={{
            background: header.cp === 'CALL' ? 'rgba(34,197,94,0.14)' : 'rgba(239,68,68,0.14)',
            color: header.cp === 'CALL' ? 'var(--bull)' : 'var(--bear)',
          }}
        >
          {header.cp}
        </span>
        <span className="font-mono text-sm text-[var(--on-surface-variant)]">{header.expiry}</span>
        <span className="rounded bg-[var(--surface-3)] px-2 py-0.5 font-mono text-[11px] text-[var(--on-surface-variant)]">
          {header.dte} DTE
        </span>
        <span className="ml-auto font-mono text-[10px] text-[var(--on-surface-muted)]">{contractId}</span>
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {statCells.map((s) => (
          <div key={s.label} className="rounded-xl bg-[var(--surface-2)] p-3">
            <div className="label-micro mb-1">{s.label}</div>
            <div className="font-mono text-base font-semibold text-[var(--on-surface)]">{s.value}</div>
          </div>
        ))}
      </div>

      {/* Chain ratio bar — Bid% ↔ Ask% with $ on each side */}
      <div className="rounded-xl bg-[var(--surface-2)] p-4">
        <div className="mb-2 flex items-center justify-between text-[11px]">
          <span className="font-semibold" style={{ color: 'var(--bear)' }}>
            Bid {chainRatio.bidPct}% · {money(chainRatio.bidPremium)}
          </span>
          <span className="label-micro">Chain ratio</span>
          <span className="font-semibold" style={{ color: 'var(--bull)' }}>
            {money(chainRatio.askPremium)} · {chainRatio.askPct}% Ask
          </span>
        </div>
        <div className="flex h-3 overflow-hidden rounded-full">
          <div style={{ width: `${chainRatio.bidPct}%`, background: 'var(--bear)' }} />
          <div style={{ width: `${midPct}%`, background: 'var(--surface-3)' }} title={`Mid ${midPct}%`} />
          <div style={{ width: `${chainRatio.askPct}%`, background: 'var(--bull)' }} />
        </div>
      </div>

      {/* Volume-over-time chart (bars) + overlaid avg-fill / price line */}
      <div className="rounded-xl bg-[var(--surface-2)] p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-[var(--on-surface)]">Volume over time · avg fill overlay</h3>
          <div className="flex flex-wrap gap-3 text-[10px] text-[var(--on-surface-muted)]">
            <span style={{ color: 'var(--bear)' }}>■ Bid {totals.bid}</span>
            <span style={{ color: 'var(--on-surface-muted)' }}>■ Mid {totals.mid}</span>
            <span style={{ color: 'var(--bull)' }}>■ Ask {totals.ask}</span>
            <span style={{ color: 'var(--warn)' }}>■ No-side {totals.noSide}</span>
          </div>
        </div>
        {/* Recharts needs a fixed-height parent. */}
        <div style={{ height: 280 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={buckets} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
              <CartesianGrid stroke="var(--outline-variant)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: 'var(--on-surface-muted)' }} stroke="var(--outline-variant)" />
              <YAxis
                yAxisId="vol"
                tick={{ fontSize: 10, fill: 'var(--on-surface-muted)' }}
                stroke="var(--outline-variant)"
                tickFormatter={(v: number) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v))}
              />
              <YAxis
                yAxisId="price"
                orientation="right"
                tick={{ fontSize: 10, fill: 'var(--on-surface-muted)' }}
                stroke="var(--outline-variant)"
                domain={['auto', 'auto']}
              />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
              <Bar yAxisId="vol" dataKey="askCount" stackId="side" fill="var(--bull)" fillOpacity={0.6} name="Ask" />
              <Bar yAxisId="vol" dataKey="midCount" stackId="side" fill="var(--on-surface-muted)" fillOpacity={0.45} name="Mid" />
              <Bar yAxisId="vol" dataKey="bidCount" stackId="side" fill="var(--bear)" fillOpacity={0.6} name="Bid" />
              <Bar yAxisId="vol" dataKey="noSideCount" stackId="side" fill="var(--warn)" fillOpacity={0.5} name="No-side" />
              <Line yAxisId="price" type="monotone" dataKey="avgFill" stroke="var(--brand)" strokeWidth={2} dot={false} name="Avg fill" />
              <Line yAxisId="price" type="monotone" dataKey="price" stroke="#ffb800" strokeWidth={1.5} strokeDasharray="4 2" dot={false} name="Price" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Time-bucket detail table */}
      <div className="overflow-hidden rounded-xl bg-[var(--surface-2)]">
        <div className="px-4 py-3">
          <h3 className="text-sm font-semibold text-[var(--on-surface)]">Time-bucket detail</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs" style={{ minWidth: 760 }}>
            <thead>
              <tr className="border-b border-[var(--outline-variant)] text-[10px] uppercase tracking-wider text-[var(--on-surface-label)]">
                <th className="px-2 py-2 text-left font-semibold">Time</th>
                <th className="px-2 py-2 text-right font-semibold">Bid</th>
                <th className="px-2 py-2 text-right font-semibold">Mid</th>
                <th className="px-2 py-2 text-right font-semibold">Ask</th>
                <th className="px-2 py-2 text-right font-semibold">Avg Fill</th>
                <th className="px-2 py-2 text-right font-semibold">IV</th>
                <th className="px-2 py-2 text-right font-semibold">RVOL</th>
                <th className="px-2 py-2 text-right font-semibold">Volume</th>
                <th className="px-2 py-2 text-right font-semibold">Bid $</th>
                <th className="px-2 py-2 text-right font-semibold">Mid $</th>
                <th className="px-2 py-2 text-right font-semibold">Ask $</th>
              </tr>
            </thead>
            <tbody>
              {buckets.map((b) => (
                <tr key={b.time} className="border-b border-[var(--outline-variant)]/50">
                  <td className="px-2 py-1.5 font-mono text-[var(--on-surface-muted)]">{b.time}</td>
                  <td className="px-2 py-1.5 text-right font-mono" style={{ color: 'var(--bear)' }}>{b.bidCount}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-[var(--on-surface-muted)]">{b.midCount}</td>
                  <td className="px-2 py-1.5 text-right font-mono" style={{ color: 'var(--bull)' }}>{b.askCount}</td>
                  <td className="px-2 py-1.5 text-right font-mono">{b.avgFill.toFixed(2)}</td>
                  <td className="px-2 py-1.5 text-right font-mono">{(b.iv * 100).toFixed(1)}%</td>
                  <td className="px-2 py-1.5 text-right font-mono">{b.rvol.toFixed(1)}x</td>
                  <td className="px-2 py-1.5 text-right font-mono">{num(b.volume)}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-[var(--on-surface-muted)]">{money(b.bidPremium)}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-[var(--on-surface-muted)]">{money(b.midPremium)}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-[var(--on-surface-muted)]">{money(b.askPremium)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
