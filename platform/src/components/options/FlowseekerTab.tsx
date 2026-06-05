import { useState } from 'react';
import { Zap, AlertTriangle } from 'lucide-react';
import {
  FLOW_FEED,
  SCANNER_BUCKETS,
  FLOW_SENTIMENT,
  TOP_TICKERS,
  type FlowRow,
  type FlowSide,
  type ChainSide,
  type ScannerBucket,
} from '@/data/optionsFlowMock';

// FlowseekerTab — live-options-flow UI built entirely from clearly-labeled
// mock placeholder data (src/data/optionsFlowMock.ts). There is NO backend
// flow-tape endpoint; the demo banner makes that explicit.

const FILTERS = ['All', 'Sweeps', 'Calls', 'Puts', 'Bullish', 'Bearish', '> $100K', '0–2 DTE'] as const;
type FlowFilter = (typeof FILTERS)[number];

function money(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n}`;
}

function scannerToneColor(tone: ScannerBucket['tone']): string {
  switch (tone) {
    case 'gold': return '#ffb800';
    case 'bull': return 'var(--bull)';
    case 'brand': return 'var(--brand)';
    case 'warn': return 'var(--warn)';
    default: return 'var(--on-surface)';
  }
}

function sideColor(side: FlowSide): string {
  return side === 'ASK' ? 'var(--bull)' : side === 'BID' ? 'var(--bear)' : 'var(--on-surface-muted)';
}

function chainColor(side: ChainSide): string {
  return side === 'Ask' ? 'var(--bull)' : side === 'Bid' ? 'var(--bear)' : 'var(--on-surface-muted)';
}

// Bid / mark / ask spread micro-viz
function SpreadCell({ bid, ask, mark, side }: { bid: number; ask: number; mark: number; side: FlowSide }) {
  const range = ask - bid || 1;
  const pos = Math.max(0, Math.min(1, (mark - bid) / range));
  const tone = sideColor(side);
  return (
    <div style={{ minWidth: 92 }}>
      <div className="flex justify-between font-mono text-[9.5px] text-[var(--on-surface-muted)] mb-[3px]">
        <span>{bid.toFixed(2)}</span>
        <span style={{ color: 'var(--on-surface)' }}>{mark.toFixed(2)}</span>
        <span>{ask.toFixed(2)}</span>
      </div>
      <div className="relative h-1 rounded-sm" style={{ background: 'var(--surface-3)' }}>
        <div
          className="absolute -top-[2px] h-2 w-2 rounded-full"
          style={{ left: `${pos * 100}%`, transform: 'translateX(-50%)', background: tone }}
        />
      </div>
    </div>
  );
}

// Chain-side fill ratio bar
function ChainCell({ chainSide, chainPct }: { chainSide: ChainSide; chainPct: number }) {
  const tone = chainColor(chainSide);
  return (
    <div style={{ minWidth: 84 }}>
      <div className="mb-[3px] font-mono text-[10px] font-bold" style={{ color: tone }}>
        {chainSide} {chainPct}%
      </div>
      <div className="h-1 overflow-hidden rounded-sm" style={{ background: 'var(--surface-3)' }}>
        <div className="h-full" style={{ width: `${chainPct}%`, background: tone, opacity: 0.7 }} />
      </div>
    </div>
  );
}

function applyFilter(rows: FlowRow[], filter: FlowFilter): FlowRow[] {
  switch (filter) {
    case 'Sweeps': return rows.filter(f => f.sweep);
    case 'Calls': return rows.filter(f => f.cp === 'CALL');
    case 'Puts': return rows.filter(f => f.cp === 'PUT');
    case 'Bullish': return rows.filter(f => f.sent === 'BULLISH');
    case 'Bearish': return rows.filter(f => f.sent === 'BEARISH');
    case '> $100K': return rows.filter(f => f.prem >= 100000);
    case '0–2 DTE': return rows.filter(f => f.dte <= 2);
    default: return rows;
  }
}

export default function FlowseekerTab() {
  const [filter, setFilter] = useState<FlowFilter>('All');
  const rows = applyFilter(FLOW_FEED, filter);

  const bullTotal = FLOW_SENTIMENT.bullPrem;
  const bearTotal = FLOW_SENTIMENT.bearPrem;
  const bullPct = (bullTotal / (bullTotal + bearTotal)) * 100;

  return (
    <div className="space-y-4">
      {/* Demo banner — make it unmistakable this isn't live */}
      <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-[var(--warn)]">
        <AlertTriangle size={14} className="shrink-0" />
        <span className="font-semibold">Demo data — no live flow feed connected.</span>
        <span className="text-[var(--warn)]/80">
          Placeholder tape until an options flow-tape endpoint exists.
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_280px] lg:items-start">
        {/* Left column: scanner strip + feed */}
        <div className="min-w-0 space-y-4">
          {/* Scanner strip */}
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
            {SCANNER_BUCKETS.map(s => (
              <div key={s.id} className="rounded-xl bg-[var(--surface-2)] p-3">
                <div className="label-micro mb-1.5">{s.label}</div>
                <div className="flex items-baseline justify-between">
                  <div className="text-xl font-semibold" style={{ color: scannerToneColor(s.tone) }}>
                    {s.count}
                  </div>
                  <div className="font-mono text-xs text-[var(--on-surface-muted)]">{money(s.prem)}</div>
                </div>
              </div>
            ))}
          </div>

          {/* Live feed */}
          <div className="overflow-hidden rounded-xl bg-[var(--surface-2)]">
            <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
              <h3 className="text-sm font-semibold text-[var(--on-surface)]">Live options feed</h3>
              <div className="flex flex-wrap gap-1.5">
                {FILTERS.map(f => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={`rounded px-2.5 py-[3px] text-[11px] font-medium ${
                      filter === f
                        ? 'bg-[var(--brand)] text-[var(--on-brand)]'
                        : 'bg-[var(--surface-3)] text-[var(--on-surface-variant)]'
                    }`}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs" style={{ minWidth: 1080 }}>
                <thead>
                  <tr className="border-b border-[var(--outline-variant)] text-[10px] uppercase tracking-wider text-[var(--on-surface-label)]">
                    <th className="px-2 py-2 text-left font-semibold">Time</th>
                    <th className="px-2 py-2 text-left font-semibold">Sym</th>
                    <th className="px-2 py-2 text-right font-semibold">Strike</th>
                    <th className="px-2 py-2 text-left font-semibold">C/P</th>
                    <th className="px-2 py-2 text-right font-semibold">OTM</th>
                    <th className="px-2 py-2 text-left font-semibold">Exp</th>
                    <th className="px-2 py-2 text-right font-semibold">DTE</th>
                    <th className="px-2 py-2 text-left font-semibold">Spread</th>
                    <th className="px-2 py-2 text-left font-semibold">Side</th>
                    <th className="px-2 py-2 text-left font-semibold">Sentiment</th>
                    <th className="px-2 py-2 text-right font-semibold">Size</th>
                    <th className="px-2 py-2 text-left font-semibold">Chain</th>
                    <th className="px-2 py-2 text-right font-semibold">Premium</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((f, i) => (
                    <tr key={i} className="border-b border-[var(--outline-variant)]/50">
                      <td className="px-2 py-1.5 font-mono text-[var(--on-surface-muted)]">{f.time}</td>
                      <td className="px-2 py-1.5">
                        <span className="flex items-center gap-1 font-semibold text-[var(--on-surface)]">
                          {f.sweep ? <Zap size={11} style={{ color: '#ffb800' }} /> : null}
                          {f.sym}
                        </span>
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono">{f.strike}</td>
                      <td className="px-2 py-1.5" style={{ color: f.cp === 'CALL' ? 'var(--bull)' : 'var(--bear)' }}>
                        <strong>{f.cp[0]}</strong>
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono text-[var(--on-surface-muted)]">
                        {f.otm >= 0 ? '+' : ''}{f.otm.toFixed(1)}%
                      </td>
                      <td className="px-2 py-1.5 text-[var(--on-surface-muted)]">{f.exp}</td>
                      <td className="px-2 py-1.5 text-right">
                        <span
                          className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
                          style={
                            f.dte <= 2
                              ? { background: 'rgba(255,184,107,0.15)', color: 'var(--warn)' }
                              : { background: 'var(--surface-3)', color: 'var(--on-surface-variant)' }
                          }
                        >
                          {f.dte}
                        </span>
                      </td>
                      <td className="px-2 py-1.5">
                        <SpreadCell bid={f.bid} ask={f.ask} mark={f.mark} side={f.side} />
                      </td>
                      <td className="px-2 py-1.5">
                        <span
                          className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
                          style={{
                            background: 'var(--surface-3)',
                            color: sideColor(f.side),
                          }}
                        >
                          {f.side}
                        </span>
                      </td>
                      <td className="px-2 py-1.5">
                        <span
                          className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
                          style={{
                            background: 'var(--surface-3)',
                            color:
                              f.sent === 'BULLISH'
                                ? 'var(--bull)'
                                : f.sent === 'BEARISH'
                                ? 'var(--bear)'
                                : 'var(--on-surface-muted)',
                          }}
                        >
                          {f.sent}
                        </span>
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono">{f.size.toLocaleString()}</td>
                      <td className="px-2 py-1.5">
                        <ChainCell chainSide={f.chainSide} chainPct={f.chainPct} />
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono">
                        <strong
                          style={{
                            color:
                              f.premTone === 'gold'
                                ? '#ffb800'
                                : f.premTone === 'brand'
                                ? 'var(--brand)'
                                : 'var(--on-surface)',
                          }}
                        >
                          {money(f.prem)}
                        </strong>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right sentiment rail */}
        <div className="space-y-4">
          <div className="rounded-xl bg-[var(--surface-2)] p-4">
            <div className="label-micro mb-2.5">Flow sentiment · today</div>
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-[11px]" style={{ color: 'var(--bull)' }}>Bullish prem</span>
              <span className="font-mono text-xs font-bold" style={{ color: 'var(--bull)' }}>
                {money(bullTotal)}
              </span>
            </div>
            <div className="mb-2.5 flex items-center justify-between">
              <span className="text-[11px]" style={{ color: 'var(--bear)' }}>Bearish prem</span>
              <span className="font-mono text-xs font-bold" style={{ color: 'var(--bear)' }}>
                {money(bearTotal)}
              </span>
            </div>
            <div className="flex h-2 overflow-hidden rounded-full">
              <div style={{ width: `${bullPct}%`, background: 'var(--bull)' }} />
              <div className="flex-1" style={{ background: 'var(--bear)' }} />
            </div>
            <div className="mt-3.5 grid grid-cols-2 gap-2">
              <div>
                <div className="label-micro">C/P ratio</div>
                <div className="text-lg font-semibold text-[var(--on-surface)]">
                  {FLOW_SENTIMENT.callPutRatio}
                </div>
              </div>
              <div>
                <div className="label-micro">Net delta</div>
                <div className="text-lg font-semibold" style={{ color: 'var(--brand)' }}>
                  {FLOW_SENTIMENT.netDelta}
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-xl bg-[var(--surface-2)] p-4">
            <div className="label-micro mb-2">Top tickers · premium</div>
            {TOP_TICKERS.map(t => (
              <div
                key={t.sym}
                className="flex items-center justify-between border-b border-[var(--outline-variant)] py-[7px] last:border-b-0"
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-[var(--on-surface)]">{t.sym}</span>
                  <span
                    className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
                    style={{
                      background: 'var(--surface-3)',
                      color: t.dir === 'bull' ? 'var(--bull)' : 'var(--bear)',
                    }}
                  >
                    {(t.cp * 100).toFixed(0)}% C
                  </span>
                </div>
                <span className="font-mono text-xs font-semibold text-[var(--on-surface-variant)]">
                  {money(t.prem)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
