import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTickerStore } from '@/stores/tickerStore';
import { useReviewDateStore } from '@/stores/reviewDateStore';
import { MetricCard } from '@/components/shared/MetricCard';
import { DateSelector } from '@/components/shared/DateSelector';
import {
  TrendingUp, TrendingDown, Minus, Activity, BookOpen,
  AlertTriangle, Database, ArrowUpRight, ArrowDownRight,
} from 'lucide-react';

// ── Types ──────────────────────────────────────────────────────────────────

interface HealthResponse { cloud_sql: boolean; data_dir_exists: boolean }
interface StatusResponse { is_open: boolean; session: string; next_open: string | null; current_time_et: string }
interface QuoteResponse {
  ticker: string; price: number; open: number; high: number; low: number;
  volume: number; change: number; change_pct: number; prev_close: number;
  last_updated: string; market_session: string; market_open: boolean;
}
interface ReferenceResponse { ticker: string; date: string; open: number; high: number; low: number; close: number }
interface MarketDataResponse {
  ticker: string; date: string; count: number;
  candlestick: Array<{ time: number; open: number; high: number; low: number; close: number }>;
  volume: Array<{ time: number; value: number; color?: string }>;
}
interface BriefResponse {
  ticker: string; source: string; bias: string; has_premarket: boolean; reason?: string;
  rsi?: number; rsi_direction?: string; strat_daily?: string; strat_combo?: string;
  ftfc_score?: number; ftfc_direction?: string; signal_status?: string;
  consecutive_up?: number; consecutive_down?: number;
  daily_indicators: {
    date?: string; close?: number; rsi_14?: number; ema_9?: number; ema_20?: number;
    sma_200?: number; macd?: number; atr?: number; rvol?: number;
    strat_candle?: string; strat_combo?: string; ftfc_score?: number; ftfc_direction?: string;
    consecutive_up?: number; consecutive_down?: number; price_vs_ema9?: number; price_vs_ema20?: number;
  };
}
interface BacktestSummary {
  total_trades: number; win_count: number; loss_count: number; win_rate: number;
  avg_return_pct: number; avg_win_pct: number; avg_loss_pct: number; total_return_pct: number;
}
interface BacktestResponse { ticker: string; summary: BacktestSummary; trades: Array<Record<string, unknown>> }
interface EquityResponse { summary: { total_return_pct: number; max_drawdown_pct: number } }
interface SignalEntry { time: string; direction: string; score: number; conditions_met: string; return_pct: number }
interface SignalsResponse { ticker: string; count: number; signals: SignalEntry[] }
interface PlaybookCard { id: string; name: string; direction: string; win_rate: number; avg_return: number; conditions: string[]; description: string }
interface PlaybookResponse { ticker: string; cards: PlaybookCard[] }

// ── Hooks ──────────────────────────────────────────────────────────────────

function useFetch<T>(key: string[], url: string, opts?: { staleTime?: number; refetchInterval?: number | false; enabled?: boolean }) {
  return useQuery<T>({
    queryKey: key,
    queryFn: async () => { const r = await fetch(url); if (!r.ok) throw new Error(`${r.status}`); return r.json(); },
    staleTime: opts?.staleTime ?? 60_000,
    refetchInterval: opts?.refetchInterval,
    enabled: opts?.enabled,
  });
}

// ── Helpers ────────────────────────────────────────────────────────────────

function returnPct(v: number | undefined): string {
  if (v === undefined || v === null) return '--';
  const p = v * 100;
  return `${p >= 0 ? '+' : ''}${p.toFixed(2)}%`;
}

function pct(v: number | undefined, digits = 1): string {
  if (v === undefined || v === null) return '--';
  return `${v >= 0 ? '+' : ''}${v.toFixed(digits)}%`;
}

function sessionLabel(session: string): string {
  const map: Record<string, string> = { regular: 'Market Open', 'pre-market': 'Pre-Market', 'after-hours': 'After Hours', closed: 'Closed' };
  return map[session] ?? session;
}

function sessionColor(session: string): string {
  if (session === 'regular') return 'bg-green-500';
  if (session === 'pre-market' || session === 'after-hours') return 'bg-amber-500';
  return 'bg-red-500';
}

function biasIcon(bias: string) {
  if (bias === 'bullish') return <ArrowUpRight size={28} className="text-green-400" />;
  if (bias === 'bearish') return <ArrowDownRight size={28} className="text-red-400" />;
  return <Minus size={28} className="text-[var(--color-text-muted)]" />;
}

function biasBorder(bias: string): string {
  if (bias === 'bullish') return 'border-green-500/40';
  if (bias === 'bearish') return 'border-red-500/40';
  return 'border-[var(--color-border)]';
}

// ── Component ──────────────────────────────────────────────────────────────

/** Convert a review date+time (ET) to a Unix timestamp matching the bar format (ET-as-UTC). */
function reviewTimestamp(date: string, time: string | null): number | null {
  if (!date) return null;
  const t = time ?? '23:59';
  const [y, m, d] = date.split('-').map(Number);
  const [hh, mm] = t.split(':').map(Number);
  return Math.floor(Date.UTC(y, m - 1, d, hh, mm) / 1000);
}

export default function DashboardPage() {
  const { activeTicker } = useTickerStore();
  const { reviewDate, reviewTime } = useReviewDateStore();
  const isReview = reviewDate !== null;
  const reviewTs = isReview ? reviewTimestamp(reviewDate, reviewTime) : null;

  const { data: health } = useFetch<HealthResponse>(['health'], '/api/health', { staleTime: 300_000 });
  const { data: status } = useFetch<StatusResponse>(['live-status'], '/api/live/status', { refetchInterval: 60_000 });
  const isOpen = !isReview && (status?.is_open ?? false);

  // Live quote — only when NOT in review mode
  const { data: liveQuote } = useFetch<QuoteResponse>(['quote', activeTicker], `/api/live/quote/${activeTicker}`, {
    staleTime: isOpen ? 10_000 : 300_000,
    refetchInterval: isOpen ? 15_000 : false,
    enabled: !isReview,
  });

  // Historical intraday — only when in review mode, used to derive a synthetic quote
  const reviewDateCompact = reviewDate?.replace(/-/g, '') ?? '';
  const { data: histData } = useFetch<MarketDataResponse>(['hist', activeTicker, reviewDateCompact], `/api/market/data/${activeTicker}/${reviewDateCompact}?timeframe=1`, {
    staleTime: 3_600_000,
    enabled: isReview,
  });

  // Derive a quote-like object for historical mode: last bar = close, first bar = open, etc.
  // When a time is set, slice bars to only those at or before the selected minute.
  const quote: QuoteResponse | undefined = useMemo(() => {
    if (!isReview) return liveQuote;
    if (!histData || histData.candlestick.length === 0) return undefined;
    const allBars = histData.candlestick;
    const bars = reviewTs !== null ? allBars.filter(b => b.time <= reviewTs) : allBars;
    if (bars.length === 0) return undefined;
    const first = bars[0];
    const last = bars[bars.length - 1];
    const high = Math.max(...bars.map(b => b.high));
    const low = Math.min(...bars.map(b => b.low));
    // Sum volume only for included bars
    const cutoffIdx = bars.length;
    const volume = histData.volume.slice(0, cutoffIdx).reduce((sum, v) => sum + v.value, 0);
    const label = reviewTime ? `${reviewDate} ${reviewTime} ET` : (reviewDate ?? '');
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
      last_updated: label,
      market_session: 'closed',
      market_open: false,
    };
  }, [isReview, liveQuote, histData, activeTicker, reviewDate, reviewTime, reviewTs]);

  // Reference (prev day) — date depends on mode
  const refDate = isReview ? reviewDateCompact : new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const { data: reference } = useFetch<ReferenceResponse>(['reference', activeTicker, refDate], `/api/market/reference/${activeTicker}/${refDate}`, { staleTime: 3_600_000 });

  // Dashboard brief — pass ?date= in review mode
  const briefUrl = isReview ? `/api/dashboard/brief/${activeTicker}?date=${reviewDate}` : `/api/dashboard/brief/${activeTicker}`;
  const { data: brief } = useFetch<BriefResponse>(['brief', activeTicker, reviewDate ?? 'live'], briefUrl, {
    staleTime: 300_000,
    refetchInterval: isOpen ? 300_000 : false,
  });

  const { data: btData } = useFetch<BacktestResponse>(['bt', activeTicker], `/api/backtest/results/${activeTicker}`, { staleTime: 3_600_000 });
  const { data: eqData } = useFetch<EquityResponse>(['eq', activeTicker], `/api/backtest/equity/${activeTicker}`, { staleTime: 3_600_000 });
  const { data: sigData } = useFetch<SignalsResponse>(['sig', activeTicker], `/api/signals/${activeTicker}?limit=20`, { staleTime: 300_000 });
  const { data: pbData } = useFetch<PlaybookResponse>(['pb', activeTicker], `/api/playbook/${activeTicker}`, { staleTime: 3_600_000 });

  const summary = btData?.summary;
  const signals = sigData?.signals ?? [];
  const cards = pbData?.cards ?? [];
  const di = brief?.daily_indicators ?? {};

  // Top playbook match: pick card matching bias with best win_rate
  const topCard = useMemo(() => {
    if (!cards.length) return null;
    const biasDir = brief?.bias === 'bullish' ? 'CALL' : brief?.bias === 'bearish' ? 'PUT' : null;
    const candidates = biasDir ? cards.filter(c => c.direction === biasDir) : cards;
    return (candidates.length ? candidates : cards).reduce((best, c) => (c.win_rate > best.win_rate ? c : best));
  }, [cards, brief?.bias]);

  // Profit factor
  const profitFactor = useMemo(() => {
    if (!summary) return null;
    const grossWin = Math.abs(summary.avg_win_pct * summary.win_count);
    const grossLoss = Math.abs(summary.avg_loss_pct * summary.loss_count);
    return grossLoss > 0 ? grossWin / grossLoss : null;
  }, [summary]);

  // Best/worst trades
  const { bestTrades, worstTrades } = useMemo(() => {
    const trades = (btData?.trades ?? []) as Array<{ entry_time: string; direction: string; return_pct: number; exit_reason: string }>;
    const sorted = [...trades].sort((a, b) => b.return_pct - a.return_pct);
    return { bestTrades: sorted.slice(0, 5), worstTrades: sorted.slice(-5).reverse() };
  }, [btData?.trades]);

  const cloudSqlOk = health?.cloud_sql ?? false;

  return (
    <div className="space-y-4">
      {/* ── Unified control bar: Date selector · Market status · Cloud SQL ── */}
      <div className="flex flex-wrap items-center gap-3">
        <DateSelector />

        {/* Market status pill */}
        <div className="inline-flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-1.5">
          <span className={`h-2 w-2 rounded-full ${isReview ? 'bg-amber-500' : sessionColor(status?.session ?? 'closed')}`} />
          <span className="text-xs font-medium text-[var(--color-text-primary)]">
            {isReview
              ? `As of ${reviewDate}${reviewTime ? ` ${reviewTime}` : ''}`
              : sessionLabel(status?.session ?? 'closed')}
          </span>
          {status && !isReview && (
            <span className="text-xs text-[var(--color-text-muted)]">
              · {status.current_time_et} ET
            </span>
          )}
        </div>

        {/* Cloud SQL status pill */}
        <div className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-1.5">
          <Database size={12} className={cloudSqlOk ? 'text-green-400' : 'text-amber-400'} />
          <span className={`text-xs font-medium ${cloudSqlOk ? 'text-green-400' : 'text-amber-400'}`}>
            {cloudSqlOk ? 'Cloud SQL' : 'Cloud SQL Disconnected'}
          </span>
        </div>
      </div>

      {/* Cloud SQL alert banner — prominent when disconnected */}
      {!cloudSqlOk && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-2.5">
          <AlertTriangle size={16} className="text-amber-400 shrink-0" />
          <span className="text-xs text-amber-300">
            Cloud SQL not connected — premarket analysis and daily indicators unavailable. Check <code className="font-mono bg-amber-500/20 px-1 rounded">CLOUD_SQL_CONNECTION_NAME</code> env var.
          </span>
        </div>
      )}

      {/* Brief source alert — when Cloud SQL is connected but brief endpoint reports unavailable */}
      {cloudSqlOk && brief?.source === 'unavailable' && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-2.5">
          <AlertTriangle size={16} className="text-amber-400 shrink-0" />
          <span className="text-xs text-amber-300">{brief.reason}</span>
        </div>
      )}

      {/* ── SECTION 2: Price + Key Levels ────────────────────────────────── */}
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          {/* Ticker + price */}
          <div>
            <h2 className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">{activeTicker}</h2>
            <p className="font-mono text-4xl font-bold text-[var(--color-text-primary)] leading-tight">
              ${quote?.price?.toFixed(2) ?? '--'}
            </p>
          </div>

          {/* Change + OHLV grouped, vertically centered against price */}
          {quote && (
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
              <div className={quote.change >= 0 ? 'text-green-400' : 'text-red-400'}>
                <p className="text-xl font-bold font-mono leading-tight">
                  {quote.change >= 0 ? '+' : ''}{quote.change.toFixed(2)}
                </p>
                <p className="text-sm font-mono">
                  ({quote.change_pct >= 0 ? '+' : ''}{quote.change_pct.toFixed(2)}%)
                </p>
              </div>

              <div className="flex gap-4 text-xs">
                <span className="text-[var(--color-text-muted)]">O <span className="text-[var(--color-accent-blue)] font-mono font-semibold">${quote.open.toFixed(2)}</span></span>
                <span className="text-[var(--color-text-muted)]">H <span className="text-green-400 font-mono font-semibold">${quote.high.toFixed(2)}</span></span>
                <span className="text-[var(--color-text-muted)]">L <span className="text-amber-400 font-mono font-semibold">${quote.low.toFixed(2)}</span></span>
                <span className="text-[var(--color-text-muted)]">Vol <span className="text-[var(--color-text-secondary)] font-mono font-semibold">{(quote.volume / 1e6).toFixed(1)}M</span></span>
              </div>
            </div>
          )}

          {/* Timestamp (pushed right) */}
          {quote && (isReview || !isOpen) && (
            <span className="ml-auto text-xs text-[var(--color-text-muted)]">
              {isReview ? 'Close of' : 'As of'} {quote.last_updated}
            </span>
          )}
        </div>

        {/* Previous Day Levels — inline visual range bar */}
        {reference && (
          <div className="mt-4 border-t border-[var(--color-border)] pt-3">
            <div className="mb-2 flex items-center justify-between text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
              <span>Previous Day Range</span>
              {quote && (
                <span>
                  {quote.price > reference.high
                    ? <span className="text-green-400">Above prev high</span>
                    : quote.price < reference.low
                    ? <span className="text-amber-400">Below prev low</span>
                    : `${((quote.price - reference.low) / (reference.high - reference.low) * 100).toFixed(0)}% of range`}
                </span>
              )}
            </div>

            {/* Visual range bar */}
            <div className="relative h-8">
              {/* Full range line */}
              <div className="absolute inset-x-0 top-1/2 h-0.5 -translate-y-1/2 bg-gradient-to-r from-amber-400 via-[var(--color-accent-blue)] to-green-400 opacity-60" />

              {/* Low marker */}
              <div className="absolute left-0 top-0 flex flex-col items-center">
                <div className="h-full w-0.5 bg-amber-400" />
                <span className="mt-0 font-mono text-[10px] text-amber-400 whitespace-nowrap">L ${reference.low.toFixed(2)}</span>
              </div>

              {/* Close marker */}
              <div
                className="absolute top-0 flex flex-col items-center"
                style={{
                  left: `${((reference.close - reference.low) / (reference.high - reference.low)) * 100}%`,
                  transform: 'translateX(-50%)',
                }}
              >
                <div className="h-full w-0.5 bg-[var(--color-accent-blue)]" />
                <span className="font-mono text-[10px] text-[var(--color-accent-blue)] whitespace-nowrap">C ${reference.close.toFixed(2)}</span>
              </div>

              {/* High marker */}
              <div className="absolute right-0 top-0 flex flex-col items-center">
                <div className="h-full w-0.5 bg-green-400" />
                <span className="font-mono text-[10px] text-green-400 whitespace-nowrap">H ${reference.high.toFixed(2)}</span>
              </div>

              {/* Current price marker (circle on line) */}
              {quote && (() => {
                const pct = Math.max(0, Math.min(100, ((quote.price - reference.low) / (reference.high - reference.low)) * 100));
                return (
                  <div
                    className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--color-text-primary)] border-2 border-[var(--color-bg-secondary)] shadow-lg"
                    style={{ left: `${pct}%` }}
                    title={`Current: $${quote.price.toFixed(2)}`}
                  />
                );
              })()}
            </div>
          </div>
        )}
      </div>

      {/* ── SECTION 3: Strategy Readiness ────────────────────────────────── */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Card A: Daily Bias */}
        <div className={`rounded-lg border-2 ${biasBorder(brief?.bias ?? 'neutral')} bg-[var(--color-bg-secondary)] p-4`}>
          <div className="flex items-center gap-2 mb-3">
            <Activity size={14} className="text-[var(--color-accent-blue)]" />
            <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Daily Bias</h2>
            {brief?.source === 'unavailable' && (
              <span className="ml-auto text-xs text-amber-400">Cloud SQL unavailable</span>
            )}
          </div>

          {brief?.source === 'cloud_sql' ? (
            <div className="space-y-3">
              {/* Big bias indicator */}
              <div className="flex items-center gap-3">
                {biasIcon(brief.bias)}
                <div>
                  <p className={`text-lg font-bold ${
                    brief.bias === 'bullish' ? 'text-green-400' :
                    brief.bias === 'bearish' ? 'text-red-400' :
                    'text-[var(--color-text-primary)]'
                  }`}>
                    {brief.bias.toUpperCase()}
                  </p>
                  <p className="text-[10px] text-[var(--color-text-muted)]">
                    {di.date ? `Based on ${di.date} daily close` : ''}
                  </p>
                </div>
              </div>

              {/* Key indicators grid */}
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-lg bg-[var(--color-bg-tertiary)] p-3">
                  <span className="text-xs text-[var(--color-text-muted)]">RSI</span>
                  <p className="font-mono text-2xl font-bold text-[var(--color-text-primary)]">
                    {brief.rsi ?? di.rsi_14 ?? '--'}
                  </p>
                </div>
                <div className="rounded-lg bg-[var(--color-bg-tertiary)] p-3">
                  <span className="text-xs text-[var(--color-text-muted)]">RVOL</span>
                  <p className="font-mono text-2xl font-bold text-[var(--color-text-primary)]">
                    {di.rvol?.toFixed(1) ?? '--'}x
                  </p>
                </div>
                <div className="rounded-lg bg-[var(--color-bg-tertiary)] p-3">
                  <span className="text-xs text-[var(--color-text-muted)]">Streak</span>
                  <p className="font-mono text-2xl font-bold text-[var(--color-text-primary)]">
                    {(di.consecutive_up ?? brief?.consecutive_up ?? 0) > 0
                      ? `${di.consecutive_up ?? brief?.consecutive_up}↑`
                      : (di.consecutive_down ?? brief?.consecutive_down ?? 0) > 0
                      ? `${di.consecutive_down ?? brief?.consecutive_down}↓`
                      : '0'}
                  </p>
                </div>
              </div>

              {/* Strat & FTFC */}
              <div className="flex gap-2 text-sm">
                {(brief.strat_daily || di.strat_candle) && (
                  <span className="rounded-lg bg-[var(--color-bg-tertiary)] px-3 py-1.5 font-medium text-[var(--color-text-secondary)]">
                    Strat: <span className="text-[var(--color-text-primary)]">{brief.strat_daily || di.strat_candle}</span>
                  </span>
                )}
                {(brief.strat_combo || di.strat_combo) && (
                  <span className="rounded-lg bg-[var(--color-bg-tertiary)] px-3 py-1.5 font-medium text-[var(--color-text-secondary)]">
                    Combo: <span className="text-[var(--color-text-primary)]">{brief.strat_combo || di.strat_combo}</span>
                  </span>
                )}
                {(brief.ftfc_score != null || di.ftfc_score != null) && (
                  <span className="rounded-lg bg-[var(--color-bg-tertiary)] px-3 py-1.5 font-medium text-[var(--color-text-secondary)]">
                    FTFC: <span className="text-[var(--color-text-primary)]">{(brief.ftfc_score ?? di.ftfc_score ?? 0).toFixed(2)}</span>
                  </span>
                )}
              </div>

              {/* Price vs EMAs */}
              {(di.price_vs_ema9 != null || di.price_vs_ema20 != null) && (
                <div className="flex gap-4 text-xs text-[var(--color-text-muted)]">
                  {di.price_vs_ema9 != null && (
                    <span>vs EMA9: <span className={`font-mono font-semibold ${di.price_vs_ema9 >= 0 ? 'text-green-400' : 'text-red-400'}`}>{pct(di.price_vs_ema9, 2)}</span></span>
                  )}
                  {di.price_vs_ema20 != null && (
                    <span>vs EMA20: <span className={`font-mono font-semibold ${di.price_vs_ema20 >= 0 ? 'text-green-400' : 'text-red-400'}`}>{pct(di.price_vs_ema20, 2)}</span></span>
                  )}
                  {di.sma_200 != null && di.close != null && (
                    <span>vs SMA200: <span className={`font-mono font-semibold ${di.close >= di.sma_200 ? 'text-green-400' : 'text-red-400'}`}>
                      {pct(((di.close - di.sma_200) / di.sma_200) * 100, 1)}
                    </span></span>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2 text-xs text-amber-400">
              <AlertTriangle size={14} />
              <span>Daily bias unavailable — Cloud SQL not connected</span>
            </div>
          )}
        </div>

        {/* Card B: Top Playbook Match */}
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
          <div className="flex items-center gap-2 mb-3">
            <BookOpen size={14} className="text-[var(--color-accent-blue)]" />
            <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Top Setup</h2>
            {cards.length > 0 && (
              <a href="/playbook" className="ml-auto text-[10px] text-[var(--color-accent-blue)] hover:underline">
                All {cards.length} setups →
              </a>
            )}
          </div>

          {topCard ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                {topCard.direction === 'CALL'
                  ? <TrendingUp size={16} className="text-green-400" />
                  : topCard.direction === 'PUT'
                  ? <TrendingDown size={16} className="text-red-400" />
                  : <Minus size={16} className="text-[var(--color-text-muted)]" />
                }
                <span className="text-sm font-semibold text-[var(--color-text-primary)] truncate">
                  {topCard.name}
                </span>
              </div>

              <p className="text-xs text-[var(--color-text-muted)] line-clamp-2">
                {topCard.description}
              </p>

              <div className="flex gap-3 text-xs">
                <span className="text-[var(--color-text-muted)]">
                  Win rate: <span className="font-mono font-semibold text-[var(--color-text-primary)]">{topCard.win_rate}%</span>
                </span>
                <span className="text-[var(--color-text-muted)]">
                  Avg: <span className={`font-mono font-semibold ${topCard.avg_return >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {returnPct(topCard.avg_return)}
                  </span>
                </span>
              </div>

              {topCard.conditions.length > 0 && (
                <div className="space-y-1 mt-1">
                  <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider">Conditions</p>
                  {topCard.conditions.slice(0, 5).map((c, i) => (
                    <div key={i} className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-secondary)]">
                      <span className="h-1 w-1 rounded-full bg-[var(--color-accent-blue)]" />
                      {c}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-[var(--color-text-muted)]">No playbook — run phase 6 pipeline first.</p>
          )}
        </div>
      </div>

      {/* ── SECTION 4: Performance KPIs ──────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard
          label="Win Rate"
          value={summary ? `${(summary.win_rate * 100).toFixed(1)}%` : '--'}
          direction={summary ? (summary.win_rate >= 0.5 ? 'up' : summary.win_rate >= 0.4 ? 'neutral' : 'down') : undefined}
          subtitle={summary ? `${Math.round(summary.win_rate * 10)} in 10 trades win` : undefined}
        />
        <MetricCard
          label="Avg Win / Loss"
          value={summary ? `+${(summary.avg_win_pct * 100).toFixed(2)}% / ${(summary.avg_loss_pct * 100).toFixed(2)}%` : '--'}
          direction={summary ? (Math.abs(summary.avg_win_pct) > Math.abs(summary.avg_loss_pct) ? 'up' : 'down') : undefined}
          subtitle={summary ? `Winners are ${(Math.abs(summary.avg_win_pct / summary.avg_loss_pct)).toFixed(1)}x larger than losers` : undefined}
        />
        <MetricCard
          label="Total Return"
          value={eqData ? pct(eqData.summary.total_return_pct) : summary ? pct(summary.total_return_pct) : '--'}
          direction={
            (eqData?.summary.total_return_pct ?? summary?.total_return_pct ?? 0) >= 0 ? 'up' : 'down'
          }
          subtitle={eqData ? `Worst drawdown: ${eqData.summary.max_drawdown_pct.toFixed(1)}%` : undefined}
        />
        <MetricCard
          label="Profit Factor"
          value={profitFactor ? profitFactor.toFixed(2) : '--'}
          direction={profitFactor ? (profitFactor >= 1 ? 'up' : 'down') : undefined}
          subtitle={profitFactor ? `$1 risked → $${profitFactor.toFixed(2)} back` : undefined}
        />
      </div>

      {/* ── SECTION 5: Recent Activity ───────────────────────────────────── */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Panel A: Latest Signals */}
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
          <div className="mb-3 flex items-center gap-2">
            <Activity size={14} className="text-[var(--color-accent-blue)]" />
            <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Latest Signals</h2>
            {sigData && (
              <span className="ml-auto text-[10px] text-[var(--color-text-muted)]">
                {sigData.count.toLocaleString()} total · through {signals[0]?.time?.slice(0, 10) ?? 'N/A'}
              </span>
            )}
          </div>
          {signals.length === 0 ? (
            <p className="text-xs text-[var(--color-text-muted)]">No signal data — run the signals pipeline first.</p>
          ) : (
            <div className="space-y-0.5">
              <div className="grid grid-cols-[40px_60px_1fr_70px] gap-1 px-2 py-1 text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider border-b border-[var(--color-border)]">
                <span>Dir</span><span>Score</span><span>Time</span><span className="text-right">Result</span>
              </div>
              {[...signals].reverse().slice(0, 10).map((s, i) => (
                <div key={i} className="grid grid-cols-[40px_60px_1fr_70px] gap-1 items-center rounded px-2 py-1 hover:bg-[var(--color-bg-tertiary)]">
                  <span className={`text-xs font-bold ${s.direction === 'CALL' ? 'text-green-400' : 'text-red-400'}`}>
                    {s.direction === 'CALL' ? '▲' : '▼'}
                  </span>
                  <span className="text-xs text-[var(--color-text-secondary)] font-mono">{s.conditions_met ?? `${s.score}/5`}</span>
                  <span className="font-mono text-[10px] text-[var(--color-text-muted)] truncate">{s.time.slice(5, 16)}</span>
                  <span className={`text-right font-mono text-xs font-semibold ${s.return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {returnPct(s.return_pct)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Panel B: Best / Worst Trades */}
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
          <div className="mb-3 flex items-center gap-2">
            <BookOpen size={14} className="text-[var(--color-accent-blue)]" />
            <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Best / Worst Trades</h2>
          </div>
          {bestTrades.length === 0 ? (
            <p className="text-xs text-[var(--color-text-muted)]">No backtest trades.</p>
          ) : (
            <div className="space-y-2">
              {/* Best */}
              <div>
                <p className="text-[10px] uppercase tracking-wider text-green-400 mb-1 px-2">Top Winners</p>
                {bestTrades.map((t, i) => (
                  <div key={`w${i}`} className="flex items-center justify-between rounded px-2 py-0.5 hover:bg-[var(--color-bg-tertiary)]">
                    <div className="flex items-center gap-2 text-xs">
                      <span className={t.direction === 'CALL' ? 'text-green-400' : 'text-red-400'}>
                        {t.direction === 'CALL' ? '▲' : '▼'}
                      </span>
                      <span className="font-mono text-[10px] text-[var(--color-text-muted)]">{t.entry_time.slice(5, 16)}</span>
                      <span className="text-[10px] text-[var(--color-text-muted)]">{t.exit_reason}</span>
                    </div>
                    <span className="font-mono text-xs font-semibold text-green-400">{returnPct(t.return_pct)}</span>
                  </div>
                ))}
              </div>
              {/* Worst */}
              <div>
                <p className="text-[10px] uppercase tracking-wider text-red-400 mb-1 px-2">Worst Losers</p>
                {worstTrades.map((t, i) => (
                  <div key={`l${i}`} className="flex items-center justify-between rounded px-2 py-0.5 hover:bg-[var(--color-bg-tertiary)]">
                    <div className="flex items-center gap-2 text-xs">
                      <span className={t.direction === 'CALL' ? 'text-green-400' : 'text-red-400'}>
                        {t.direction === 'CALL' ? '▲' : '▼'}
                      </span>
                      <span className="font-mono text-[10px] text-[var(--color-text-muted)]">{t.entry_time.slice(5, 16)}</span>
                      <span className="text-[10px] text-[var(--color-text-muted)]">{t.exit_reason}</span>
                    </div>
                    <span className="font-mono text-xs font-semibold text-red-400">{returnPct(t.return_pct)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
