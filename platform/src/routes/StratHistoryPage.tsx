import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

// Historical Strat tape per ticker — list of tickers (left) → that ticker's
// previous Strat classification across daily/weekly/monthly/quarterly plus the
// upcoming (in-progress) break setup (right). Rules-based; feeds off
// GET /api/strat/history/{ticker} (lib.strat.compute_strat_history).

const DEFAULT_TICKERS = [
  'SPY', 'QQQ', 'IWM', 'AAPL', 'AMZN', 'NVDA', 'TSLA', 'META', 'MSFT', 'GOOGL',
  'MU', 'LLY', 'UBER', 'AMD', 'AVGO', 'NFLX', 'COIN', 'MRVL', 'ASML', 'CRCL',
];

const TF_LABEL: Record<string, string> = {
  '1d': 'Daily', '1w': 'Weekly', '1mo': 'Monthly', '1q': 'Quarterly',
};
const TF_ORDER = ['1d', '1w', '1mo', '1q'];

interface BarRecord {
  period: string; open: number | null; high: number | null;
  low: number | null; close: number | null;
  candle: string; combo: string;
  is_continuation: boolean; is_reversal: boolean;
  is_inside: boolean; is_setup: boolean;
}
interface Upcoming {
  basis_candle: string; basis_combo: string; is_inside_setup: boolean;
  trigger_high: number | null; trigger_low: number | null; mid_trigger: number | null;
  break_up: string; break_down: string;
}
interface TfBlock {
  available: boolean; reason?: string;
  history?: BarRecord[]; current?: BarRecord; upcoming?: Upcoming;
}
interface StratHistory {
  available: boolean; ticker: string; reason?: string;
  timeframes: Record<string, TfBlock>;
}

function candleColor(candle: string): string {
  if (candle === '2U') return 'text-[var(--success)]';
  if (candle === '2D') return 'text-[var(--danger)]';
  if (candle === '3') return 'text-amber-400';
  return 'text-[var(--color-text-muted)]'; // '1' / 'X'
}

function CandleBadge({ candle }: { candle: string }) {
  return (
    <span className={`inline-block w-7 text-center font-mono text-xs font-bold ${candleColor(candle)}`}>
      {candle}
    </span>
  );
}

function comboLabel(combo: string): string {
  if (!combo || combo === 'none') return '—';
  return combo.replace(/_/g, ' ');
}

function fmt(n: number | null | undefined): string {
  return n == null ? '—' : n.toFixed(2);
}

function UpcomingCard({ up }: { up: Upcoming }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--surface-2)] p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
          Upcoming setup
        </span>
        {up.is_inside_setup && (
          <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-400">
            inside / coil — pending break
          </span>
        )}
      </div>
      <div className="grid grid-cols-3 gap-2 font-mono text-xs">
        <div>
          <div className="text-[10px] text-[var(--color-text-muted)]">break ↑</div>
          <div className="text-[var(--success)]">{up.break_up}</div>
          <div className="text-[var(--color-text-muted)]">&gt; {fmt(up.trigger_high)}</div>
        </div>
        <div>
          <div className="text-[10px] text-[var(--color-text-muted)]">50% trigger</div>
          <div className="text-[var(--color-text-primary)]">{fmt(up.mid_trigger)}</div>
        </div>
        <div>
          <div className="text-[10px] text-[var(--color-text-muted)]">break ↓</div>
          <div className="text-[var(--danger)]">{up.break_down}</div>
          <div className="text-[var(--color-text-muted)]">&lt; {fmt(up.trigger_low)}</div>
        </div>
      </div>
    </div>
  );
}

function TimeframeColumn({ tf, block }: { tf: string; block: TfBlock }) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-3">
      <div className="text-sm font-bold text-[var(--color-text-primary)]">{TF_LABEL[tf] ?? tf}</div>
      {!block.available ? (
        <div className="text-xs text-[var(--color-text-muted)]">{block.reason ?? 'no data'}</div>
      ) : (
        <>
          {block.upcoming && <UpcomingCard up={block.upcoming} />}
          <div className="mt-1 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
            History (most recent last)
          </div>
          <div className="flex flex-col gap-0.5">
            {(block.history ?? []).map((b) => (
              <div
                key={b.period}
                className="flex items-center gap-2 rounded px-1 py-0.5 text-xs hover:bg-[var(--surface-2)]"
                title={`O ${fmt(b.open)}  H ${fmt(b.high)}  L ${fmt(b.low)}  C ${fmt(b.close)}`}
              >
                <span className="w-20 font-mono text-[10px] text-[var(--color-text-muted)]">{b.period}</span>
                <CandleBadge candle={b.candle} />
                <span className="flex-1 truncate text-[11px] text-[var(--color-text-primary)]">
                  {comboLabel(b.combo)}
                </span>
                {b.is_continuation && <span className="text-[10px] text-[var(--success)]">cont</span>}
                {b.is_reversal && <span className="text-[10px] text-amber-400">rev</span>}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default function StratHistoryPage() {
  const [selected, setSelected] = useState<string>('SPY');
  const [filter, setFilter] = useState('');

  const tickers = useMemo(() => {
    const f = filter.trim().toUpperCase();
    const base = f ? DEFAULT_TICKERS.filter((t) => t.includes(f)) : DEFAULT_TICKERS;
    // allow loading an arbitrary typed ticker not in the default list
    if (f && !base.includes(f) && /^[A-Z][A-Z0-9.\-]{0,9}$/.test(f)) return [f, ...base];
    return base;
  }, [filter]);

  const { data, isLoading, isError, error } = useQuery<StratHistory>({
    queryKey: ['strat-history', selected],
    queryFn: async () => {
      const r = await fetch(`/api/strat/history/${selected}?timeframes=1d,1w,1mo,1q&lookback=20`);
      if (!r.ok) throw new Error(`(${r.status}) ${(await r.json().catch(() => ({}))).detail ?? r.statusText}`);
      return r.json();
    },
  });

  return (
    <div className="flex gap-4">
      {/* Left: ticker list */}
      <aside className="w-48 shrink-0 space-y-2">
        <h1 className="text-xl font-bold text-[var(--color-text-primary)]">Strat History</h1>
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter / add ticker…"
          className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-2 py-1 text-xs text-[var(--color-text-primary)]"
        />
        <div className="flex flex-col gap-0.5">
          {tickers.map((t) => (
            <button
              key={t}
              onClick={() => setSelected(t)}
              className={`rounded px-2 py-1 text-left font-mono text-sm ${
                t === selected
                  ? 'bg-[var(--surface-2)] text-[var(--color-text-primary)] font-bold'
                  : 'text-[var(--color-text-muted)] hover:bg-[var(--surface-2)]'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </aside>

      {/* Right: per-ticker strat history across timeframes */}
      <section className="flex-1 space-y-3">
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold text-[var(--color-text-primary)]">{selected}</span>
          <span className="text-xs text-[var(--color-text-muted)]">
            Strat tape · daily / weekly / monthly / quarterly
          </span>
        </div>

        {isLoading && <div className="text-sm text-[var(--color-text-muted)]">Loading strat history…</div>}
        {isError && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-[var(--warn)]">
            Could not load strat history for {selected}: {(error as Error)?.message}
          </div>
        )}
        {data?.available && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            {TF_ORDER.filter((tf) => data.timeframes[tf]).map((tf) => (
              <TimeframeColumn key={tf} tf={tf} block={data.timeframes[tf]} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
