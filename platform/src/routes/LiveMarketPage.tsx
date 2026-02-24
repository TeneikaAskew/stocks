import { useState, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTickerStore } from '@/stores/tickerStore';
import { MetricCard } from '@/components/shared/MetricCard';
import { computeIndicators, computeSignals } from '@/lib/indicators';
import type { Bar } from '@/lib/indicators';
import {
  Activity,
  TrendingUp,
  TrendingDown,
  Volume2,
  VolumeX,
  RefreshCw,
  Circle,
} from 'lucide-react';

interface Quote {
  ticker: string;
  price: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  change: number;
  change_pct: number;
  prev_close: number;
  last_updated: string;
}

interface HistoryResponse {
  ticker: string;
  bars: Bar[];
}

interface MarketStatus {
  is_open: boolean;
  session: string;
  current_time_et: string;
}

function useMarketStatus() {
  return useQuery<MarketStatus>({
    queryKey: ['market-status'],
    queryFn: () => fetch('/api/live/status').then(r => r.json()),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

function useLiveQuote(ticker: string, enabled: boolean) {
  return useQuery<Quote>({
    queryKey: ['live-quote', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/live/quote/${ticker}`);
      if (!r.ok) throw new Error('Quote fetch failed');
      return r.json();
    },
    enabled,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
}

function useLiveHistory(ticker: string, enabled: boolean) {
  return useQuery<HistoryResponse>({
    queryKey: ['live-history', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/live/history/${ticker}`);
      if (!r.ok) throw new Error('History fetch failed');
      return r.json();
    },
    enabled,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

function ConditionRow({ label, met, current, threshold, operator }: {
  label: string; met: boolean; current: number | null; threshold: number | null; operator: string;
}) {
  return (
    <div className={`flex items-center justify-between rounded px-2 py-1 text-xs ${met ? 'bg-green-500/10' : 'bg-[var(--color-bg-tertiary)]'}`}>
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${met ? 'bg-green-400' : 'bg-[var(--color-text-muted)]'}`} />
        <span className={met ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'}>{label}</span>
      </div>
      <span className={`font-mono text-[10px] ${met ? 'text-green-400' : 'text-[var(--color-text-muted)]'}`}>
        {current !== null ? current.toFixed(2) : '--'} {operator} {threshold !== null ? threshold.toFixed(2) : '--'}
      </span>
    </div>
  );
}

function SignalCard({ direction, strength, conditions, fired }: {
  direction: 'CALL' | 'PUT';
  strength: number;
  conditions: ReturnType<typeof computeSignals>['call']['conditions'];
  fired: boolean;
}) {
  const isCall = direction === 'CALL';
  const metCount = conditions.filter(c => c.met).length;

  return (
    <div className={`rounded-lg border p-3 ${fired
      ? isCall ? 'border-green-500/50 bg-green-500/10' : 'border-red-500/50 bg-red-500/10'
      : 'border-[var(--color-border)] bg-[var(--color-bg-secondary)]'
    }`}>
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isCall
            ? <TrendingUp size={16} className="text-green-400" />
            : <TrendingDown size={16} className="text-red-400" />
          }
          <span className={`font-bold text-sm ${isCall ? 'text-green-400' : 'text-red-400'}`}>
            {direction} SETUP
          </span>
          {fired && (
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold animate-pulse ${
              isCall ? 'bg-green-500 text-white' : 'bg-red-500 text-white'
            }`}>
              SIGNAL
            </span>
          )}
        </div>
        <span className="text-xs text-[var(--color-text-muted)]">{metCount}/{conditions.length} met</span>
      </div>

      {/* Strength bar */}
      <div className="mb-1 h-2 w-full overflow-hidden rounded-full bg-[var(--color-bg-tertiary)]">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            strength >= 70
              ? isCall ? 'bg-green-400' : 'bg-red-400'
              : 'bg-[var(--color-text-muted)]'
          }`}
          style={{ width: `${strength}%` }}
        />
      </div>
      <div className="mb-3 text-right text-xs font-mono text-[var(--color-text-muted)]">{strength}%</div>

      {/* Conditions */}
      <div className="space-y-1">
        {conditions.map(c => (
          <ConditionRow
            key={c.id}
            label={c.label}
            met={c.met}
            current={c.current}
            threshold={c.threshold}
            operator={c.operator}
          />
        ))}
      </div>
    </div>
  );
}

export default function LiveMarketPage() {
  const { activeTicker } = useTickerStore();
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [polling, setPolling] = useState(true);
  const [lastFired, setLastFired] = useState<{ direction: string; time: string } | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const lastFiredRef = useRef<{ direction: string; ts: number } | null>(null);

  const { data: status } = useMarketStatus();
  const { data: quote, isError: quoteError, dataUpdatedAt } = useLiveQuote(activeTicker, polling);
  const { data: history } = useLiveHistory(activeTicker, polling);

  const bars: Bar[] = history?.bars ?? [];
  const indicators = computeIndicators(bars);
  const signals = computeSignals(
    quote?.price ?? null,
    null,
    indicators,
    quote?.volume ?? null,
    null,
  );

  // Sound alert on signal
  useEffect(() => {
    if (!soundEnabled) return;
    const callFired = signals.call.fired;
    const putFired = signals.put.fired;
    if (!callFired && !putFired) return;
    const dir = callFired ? 'CALL' : 'PUT';
    const now = Date.now();
    if (lastFiredRef.current?.direction === dir && now - lastFiredRef.current.ts < 120_000) return;
    lastFiredRef.current = { direction: dir, ts: now };
    setLastFired({ direction: dir, time: new Date().toLocaleTimeString() });
    if (!audioCtxRef.current) audioCtxRef.current = new AudioContext();
    playAlert(audioCtxRef.current, callFired);
  }, [signals.call.fired, signals.put.fired, soundEnabled]);

  const toggleSound = () => {
    if (!soundEnabled && !audioCtxRef.current) {
      audioCtxRef.current = new AudioContext();
    }
    setSoundEnabled(s => !s);
  };

  const lastUpdate = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : '--';

  const sessionLabel =
    status?.session === 'regular' ? 'Market Open' :
    status?.session === 'pre' ? 'Pre-Market' :
    status?.session === 'after' ? 'After Hours' : 'Market Closed';

  const sessionColor =
    status?.session === 'regular' ? 'text-green-400' :
    status?.session === 'pre' || status?.session === 'after' ? 'text-amber-400' : 'text-red-400';

  return (
    <div className="space-y-4">
      {/* Top bar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-1.5">
          <Circle size={8} className={`fill-current ${sessionColor}`} />
          <span className="text-xs text-[var(--color-text-secondary)]">{sessionLabel}</span>
          {status && (
            <span className="text-xs text-[var(--color-text-muted)]">{status.current_time_et} ET</span>
          )}
        </div>

        <button
          onClick={() => setPolling(p => !p)}
          className={`flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium ${
            polling
              ? 'bg-[var(--color-accent-blue)] text-white'
              : 'bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)]'
          }`}
        >
          <RefreshCw size={12} className={polling ? 'animate-spin' : ''} />
          {polling ? 'Live (15s)' : 'Paused'}
        </button>

        <button
          onClick={toggleSound}
          className={`flex items-center gap-1.5 rounded px-3 py-1.5 text-xs ${
            soundEnabled ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'
          }`}
        >
          {soundEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
          Sound
        </button>

        <div className="flex-1" />
        <span className="text-xs text-[var(--color-text-muted)]">Updated: {lastUpdate}</span>
      </div>

      {/* Quote card */}
      {quoteError ? (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-400">
          Live data unavailable — API key not configured or rate limited. Indicators will populate once history loads.
        </div>
      ) : quote ? (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
          <div className="flex flex-wrap items-center gap-6">
            <div>
              <div className="text-xs text-[var(--color-text-muted)]">{activeTicker}</div>
              <div className="text-3xl font-bold font-mono text-[var(--color-text-primary)]">
                ${quote.price.toFixed(2)}
              </div>
              <div className={`text-sm font-mono ${quote.change >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {quote.change >= 0 ? '+' : ''}{quote.change.toFixed(2)}
                {' '}({quote.change_pct >= 0 ? '+' : ''}{quote.change_pct.toFixed(2)}%)
              </div>
            </div>
            <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-xs">
              <span className="text-[var(--color-text-muted)]">
                Open: <span className="font-mono text-[var(--color-text-primary)]">${quote.open.toFixed(2)}</span>
              </span>
              <span className="text-[var(--color-text-muted)]">
                High: <span className="font-mono text-green-400">${quote.high.toFixed(2)}</span>
              </span>
              <span className="text-[var(--color-text-muted)]">
                Prev: <span className="font-mono text-[var(--color-text-primary)]">${quote.prev_close.toFixed(2)}</span>
              </span>
              <span className="text-[var(--color-text-muted)]">
                Low: <span className="font-mono text-red-400">${quote.low.toFixed(2)}</span>
              </span>
            </div>
            <div className="text-xs text-[var(--color-text-muted)]">
              Vol: <span className="font-mono">{(quote.volume / 1_000_000).toFixed(2)}M</span>
            </div>
          </div>
        </div>
      ) : polling ? (
        <div className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4 text-sm text-[var(--color-text-muted)]">
          <Activity size={16} className="animate-pulse" />
          Fetching live quote…
        </div>
      ) : null}

      {/* Indicators */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <MetricCard label="EMA 9" value={indicators.ema9 !== null ? `$${indicators.ema9.toFixed(2)}` : '--'} />
        <MetricCard label="EMA 20" value={indicators.ema20 !== null ? `$${indicators.ema20.toFixed(2)}` : '--'} />
        <MetricCard label="EMA 50" value={indicators.ema50 !== null ? `$${indicators.ema50.toFixed(2)}` : '--'} />
        <MetricCard
          label="RSI (14)"
          value={indicators.rsi !== null ? indicators.rsi.toFixed(1) : '--'}
          change={indicators.rsi !== null ? (indicators.rsi > 70 ? -1 : indicators.rsi < 30 ? 1 : 0) : undefined}
          changeLabel={
            indicators.rsi !== null
              ? indicators.rsi > 70 ? 'Overbought' : indicators.rsi < 30 ? 'Oversold' : 'Neutral'
              : undefined
          }
        />
        <MetricCard label="StochRSI" value={indicators.stochK !== null ? indicators.stochK.toFixed(1) : '--'} />
        <MetricCard label="ATR (14)" value={indicators.atr !== null ? `$${indicators.atr.toFixed(2)}` : '--'} />
      </div>

      {bars.length === 0 && polling && (
        <div className="text-center text-xs text-[var(--color-text-muted)]">
          Loading historical bars for indicators…
        </div>
      )}

      {/* Signal cards */}
      <div className="grid gap-4 lg:grid-cols-2">
        <SignalCard
          direction="CALL"
          strength={signals.call.strength}
          conditions={signals.call.conditions}
          fired={signals.call.fired}
        />
        <SignalCard
          direction="PUT"
          strength={signals.put.strength}
          conditions={signals.put.conditions}
          fired={signals.put.fired}
        />
      </div>

      {lastFired && (
        <div className={`rounded border p-2 text-xs ${
          lastFired.direction === 'CALL'
            ? 'border-green-500/30 bg-green-500/10 text-green-400'
            : 'border-red-500/30 bg-red-500/10 text-red-400'
        }`}>
          Last signal: <strong>{lastFired.direction}</strong> at {lastFired.time}
        </div>
      )}
    </div>
  );
}

function playAlert(ctx: AudioContext, isCall: boolean) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.frequency.value = isCall ? 880 : 440;
  osc.type = 'sine';
  gain.gain.setValueAtTime(0.3, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
  osc.start(ctx.currentTime);
  osc.stop(ctx.currentTime + 0.5);
}
