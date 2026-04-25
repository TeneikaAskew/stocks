import { useState, useEffect, useRef, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTickerStore } from '@/stores/tickerStore';
import { useReviewDateStore } from '@/stores/reviewDateStore';
import { useLiveStatus } from '@/hooks/useLiveStatus';
import { useLiveQuote, type LiveQuote } from '@/hooks/useLiveQuote';
import { useLiveHistory, useAvgVolume } from '@/hooks/useLiveHistory';
import { useLiveIndicators } from '@/hooks/useLiveIndicators';
import { MetricCard } from '@/components/shared/MetricCard';
import { EMPTY_INDICATORS, EMPTY_SIGNALS } from '@/lib/indicators';
import type { Bar } from '@/lib/indicators';
import { to12h } from '@/lib/time';
import {
  Activity,
  TrendingUp,
  TrendingDown,
  Volume2,
  VolumeX,
  RefreshCw,
  Circle,
} from 'lucide-react';

type Quote = LiveQuote;

interface HistoricalData {
  candlestick: Array<{ time: number; open: number; high: number; low: number; close: number }>;
  volume: Array<{ time: number; value: number }>;
}

function useHistoricalDay(ticker: string, date: string | null) {
  return useQuery<HistoricalData>({
    queryKey: ['hist-day', ticker, date],
    queryFn: async () => {
      const compact = date!.replace(/-/g, '');
      const r = await fetch(`/api/market/data/${ticker}/${compact}?timeframe=1`);
      if (!r.ok) throw new Error('Historical fetch failed');
      return r.json();
    },
    enabled: date !== null,
    staleTime: 3_600_000,
  });
}

function ConditionRow({ label, met, current, threshold, operator, direction }: {
  label: string;
  met: boolean;
  current: number | null;
  threshold: number | null;
  operator: string;
  direction: 'CALL' | 'PUT';
}) {
  const isCall = direction === 'CALL';
  const metBg = isCall ? 'bg-green-500/10' : 'bg-red-500/10';
  const metDot = isCall ? 'bg-green-400' : 'bg-red-400';
  const metText = isCall ? 'text-[var(--bull)]' : 'text-[var(--bear)]';
  return (
    <div className={`flex items-center justify-between rounded px-2 py-1 text-xs ${met ? metBg : 'bg-[var(--color-bg-tertiary)]'}`}>
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${met ? metDot : 'bg-[var(--color-text-muted)]'}`} />
        <span className={met ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'}>{label}</span>
      </div>
      <span className={`font-mono text-[10px] ${met ? metText : 'text-[var(--color-text-muted)]'}`}>
        {current !== null ? current.toFixed(2) : '--'} {operator} {threshold !== null ? threshold.toFixed(2) : '--'}
      </span>
    </div>
  );
}

function SignalCard({ direction, strength, conditions, fired }: {
  direction: 'CALL' | 'PUT';
  strength: number;
  conditions: import('@/lib/indicators').SignalCondition[];
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
            ? <TrendingUp size={16} className="text-[var(--bull)]" />
            : <TrendingDown size={16} className="text-[var(--bear)]" />
          }
          <span className={`font-bold text-sm ${isCall ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}`}>
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
            direction={direction}
          />
        ))}
      </div>
    </div>
  );
}

function reviewTimestamp(date: string, time: string | null): number | null {
  if (!date) return null;
  const t = time ?? '23:59';
  const [y, m, d] = date.split('-').map(Number);
  const [hh, mm] = t.split(':').map(Number);
  return Math.floor(Date.UTC(y, m - 1, d, hh, mm) / 1000);
}

export default function LiveMarketPage() {
  const { activeTicker } = useTickerStore();
  const { reviewDate, reviewTime } = useReviewDateStore();
  const isReview = reviewDate !== null;
  const reviewTs = isReview ? reviewTimestamp(reviewDate, reviewTime) : null;

  const [soundEnabled, setSoundEnabled] = useState(false);
  const [polling, setPolling] = useState(true);
  const [lastFired, setLastFired] = useState<{ direction: string; time: string } | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const lastFiredRef = useRef<{ direction: string; ts: number } | null>(null);

  const livePolling = polling && !isReview;

  const { data: status } = useLiveStatus();
  const { data: liveQuote, isError: quoteError, dataUpdatedAt } = useLiveQuote(activeTicker, livePolling);
  const { data: liveHistory } = useLiveHistory(activeTicker, livePolling);
  const { data: histDay } = useHistoricalDay(activeTicker, reviewDate);
  const { data: avgVolData } = useAvgVolume(activeTicker);

  // Bars: live → last 100 1-min bars; review → bars from historical day, sliced to review time
  const bars: Bar[] = useMemo(() => {
    if (isReview) {
      const all = (histDay?.candlestick ?? []).map((c, i) => ({
        time: c.time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: histDay?.volume[i]?.value ?? 0,
      }));
      return reviewTs !== null ? all.filter(b => b.time <= reviewTs) : all;
    }
    return liveHistory?.bars ?? [];
  }, [isReview, histDay, liveHistory, reviewTs]);

  // Quote: live → live quote; review → synthetic quote from historical bars
  const quote: Quote | undefined = useMemo(() => {
    if (!isReview) return liveQuote;
    if (bars.length === 0) return undefined;
    const first = bars[0];
    const last = bars[bars.length - 1];
    const high = Math.max(...bars.map(b => b.high));
    const low = Math.min(...bars.map(b => b.low));
    const volume = bars.reduce((s, b) => s + b.volume, 0);
    return {
      ticker: activeTicker,
      price: last.close,
      open: first.open,
      high,
      low,
      volume,
      change: last.close - first.open,
      change_pct: ((last.close - first.open) / first.open) * 100,
      prev_close: first.open,
      last_updated: reviewTime ? `${reviewDate} ${reviewTime} ET` : (reviewDate ?? ''),
    };
  }, [isReview, bars, liveQuote, activeTicker, reviewDate, reviewTime]);

  // Indicators and signals are computed server-side (lib/indicators.py).
  // The app never duplicates this math — there is no client-side fallback.
  const indicatorsQuery = useLiveIndicators(
    {
      bars,
      current_price: quote?.price ?? null,
      current_volume: quote?.volume ?? null,
      avg_volume_20d: avgVolData?.avg_volume_20d ?? null,
    },
    bars.length > 0,
  );
  const indicators = indicatorsQuery.data?.indicators ?? EMPTY_INDICATORS;
  const signals = indicatorsQuery.data?.signals ?? EMPTY_SIGNALS;

  // Sound alert on signal (disabled in review mode)
  useEffect(() => {
    if (!soundEnabled || isReview) return;
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
  }, [signals.call.fired, signals.put.fired, soundEnabled, isReview]);

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
    status?.session === 'regular' ? 'text-[var(--bull)]' :
    status?.session === 'pre' || status?.session === 'after' ? 'text-[var(--warn)]' : 'text-[var(--bear)]';

  return (
    <div className="space-y-4">
      {/* Top bar (DateSelector is in Header) */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-1.5">
          <Circle size={8} className={`fill-current ${isReview ? 'text-[var(--warn)]' : sessionColor}`} />
          <span className="text-xs text-[var(--color-text-secondary)]">
            {isReview
              ? `Historical: ${reviewDate}${reviewTime ? ` @ ${reviewTime} ET` : ''}`
              : sessionLabel}
          </span>
          {status && !isReview && (
            <span className="text-xs text-[var(--color-text-muted)]">{to12h(status.current_time_et)} ET</span>
          )}
        </div>

        <button
          onClick={() => setPolling(p => !p)}
          disabled={isReview}
          className={`flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-semibold disabled:opacity-40 disabled:cursor-not-allowed ${
            livePolling
              ? 'bg-[var(--brand)] text-[var(--on-brand)]'
              : 'bg-[var(--surface-2)] text-[var(--on-surface-variant)]'
          }`}
          title={isReview ? 'Disabled in historical view' : undefined}
        >
          <RefreshCw size={12} className={livePolling ? 'animate-spin' : ''} />
          {isReview ? 'Historical' : livePolling ? 'Live (15s)' : 'Paused'}
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
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-[var(--warn)]">
          Live data unavailable — API key not configured or rate limited. Indicators will populate once history loads.
        </div>
      ) : quote ? (
        <div className="rounded-xl bg-[var(--surface-2)] p-4">
          <div className="flex flex-wrap items-center gap-6">
            <div>
              <div className="text-xs text-[var(--color-text-muted)]">{activeTicker}</div>
              <div className="text-3xl font-bold font-mono text-[var(--color-text-primary)]">
                ${quote.price.toFixed(2)}
              </div>
              <div className={`text-sm font-mono ${quote.change >= 0 ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}`}>
                {quote.change >= 0 ? '+' : ''}{quote.change.toFixed(2)}
                {' '}({quote.change_pct >= 0 ? '+' : ''}{quote.change_pct.toFixed(2)}%)
              </div>
            </div>
            <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-xs">
              <span className="text-[var(--color-text-muted)]">
                Open: <span className="font-mono text-[var(--color-text-primary)]">${quote.open.toFixed(2)}</span>
              </span>
              <span className="text-[var(--color-text-muted)]">
                High: <span className="font-mono text-[var(--bull)]">${quote.high.toFixed(2)}</span>
              </span>
              <span className="text-[var(--color-text-muted)]">
                Prev: <span className="font-mono text-[var(--color-text-primary)]">${quote.prev_close.toFixed(2)}</span>
              </span>
              <span className="text-[var(--color-text-muted)]">
                Low: <span className="font-mono text-[var(--bear)]">${quote.low.toFixed(2)}</span>
              </span>
            </div>
            <div className="text-xs text-[var(--color-text-muted)]">
              Vol: <span className="font-mono">{(quote.volume / 1_000_000).toFixed(2)}M</span>
            </div>
          </div>
        </div>
      ) : polling ? (
        <div className="flex items-center gap-2 rounded-xl bg-[var(--surface-2)] p-4 text-sm text-[var(--color-text-muted)]">
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

      {bars.length === 0 && (polling || isReview) && (
        <div className="text-center text-xs text-[var(--color-text-muted)]">
          {isReview ? `Loading ${reviewDate} intraday bars…` : 'Loading historical bars for indicators…'}
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
            ? 'border-green-500/30 bg-green-500/10 text-[var(--bull)]'
            : 'border-red-500/30 bg-red-500/10 text-[var(--bear)]'
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
