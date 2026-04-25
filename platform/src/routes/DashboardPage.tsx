import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTickerStore } from '@/stores/tickerStore';
import { useReviewDateStore } from '@/stores/reviewDateStore';
import { useLiveStatus } from '@/hooks/useLiveStatus';
import { useLiveQuote, type LiveQuote } from '@/hooks/useLiveQuote';
import { useLiveHistory, useAvgVolume } from '@/hooks/useLiveHistory';
import { useLiveIndicators } from '@/hooks/useLiveIndicators';
import { buildSnapshot, type EvalResult } from '@/lib/playbookEvaluator';
import { usePlaybookEvaluation } from '@/hooks/usePlaybookEvaluation';
import { useIndicatorConfig, classifyRsiZone } from '@/hooks/useConfig';
import { to12h } from '@/lib/time';
import { MetricCard } from '@/components/shared/MetricCard';
import { PriceAreaChart, type PricePoint } from '@/components/charts/PriceAreaChart';
import { LeverageCard } from '@/components/insights/LeverageCard';
import { LeverageCurveChart } from '@/components/insights/LeverageCurveChart';
import {
  TrendingUp, TrendingDown, Minus, Activity, BookOpen,
  AlertTriangle, Database, CheckCircle, Circle, HelpCircle, ChevronDown,
} from 'lucide-react';

// ── Types ──────────────────────────────────────────────────────────────────

interface HealthResponse { cloud_sql: boolean; data_dir_exists: boolean }
type QuoteResponse = LiveQuote;
interface WeekRange { high: number; low: number; avg_close?: number; avg_rsi_14?: number | null; start_date: string; end_date: string; sessions: number }
interface ReferenceResponse {
  ticker: string;
  date: string;
  source?: string;
  stale_days?: number;
  open: number;
  high: number;
  low: number;
  close: number;
  week?: WeekRange | null;
}
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
    date?: string; stale_days?: number;
    close?: number; rsi_14?: number; ema_9?: number; ema_20?: number;
    sma_200?: number; macd?: number; atr?: number; rvol?: number;
    strat_candle?: string; strat_combo?: string; ftfc_score?: number; ftfc_direction?: string;
    consecutive_up?: number; consecutive_down?: number; price_vs_ema9?: number; price_vs_ema20?: number;
  };
  // Present only when the API overlaid live quote data on top of the daily snapshot
  live?: { price: number; session: string; updated_at: string; source: string };
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

function biasIcon(bias: string) {
  if (bias === 'bullish') return <TrendingUp size={28} className="text-[var(--bull)]" />;
  if (bias === 'bearish') return <TrendingDown size={28} className="text-[var(--bear)]" />;
  return <Minus size={28} className="text-[var(--color-text-muted)]" />;
}

function biasBorder(bias: string): string {
  if (bias === 'bullish') return 'border-green-500/40';
  if (bias === 'bearish') return 'border-red-500/40';
  return 'border-[var(--color-border)]';
}

// ── Component ──────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { activeTicker } = useTickerStore();
  const { reviewDate, reviewTime } = useReviewDateStore();
  const isReview = reviewDate !== null;

  // Server-sourced indicator config (RSI zones, thresholds, periods).
  const { data: indicatorCfg } = useIndicatorConfig();

  const { data: health } = useFetch<HealthResponse>(['health'], '/api/health', { staleTime: 300_000 });
  const { data: status } = useLiveStatus();
  const isOpen = !isReview && (status?.is_open ?? false);

  // Live quote — only when NOT in review mode
  const { data: liveQuote } = useLiveQuote(activeTicker, !isReview);

  // Historical intraday — only when in review mode. Server filters by end_time.
  const reviewDateCompact = reviewDate?.replace(/-/g, '') ?? '';
  const histUrl = `/api/market/data/${activeTicker}/${reviewDateCompact}?timeframe=1${reviewTime ? `&end_time=${reviewTime}` : ''}`;
  const { data: histData } = useFetch<MarketDataResponse>(['hist', activeTicker, reviewDateCompact, reviewTime ?? 'eod'], histUrl, {
    staleTime: 3_600_000,
    enabled: isReview,
  });

  // Derive synthetic quote from already-filtered bars (server did the end_time slice)
  const quote: QuoteResponse | undefined = useMemo(() => {
    if (!isReview) return liveQuote;
    if (!histData || histData.candlestick.length === 0) return undefined;
    const bars = histData.candlestick;
    const first = bars[0];
    const last = bars[bars.length - 1];
    const high = Math.max(...bars.map(b => b.high));
    const low = Math.min(...bars.map(b => b.low));
    const volume = histData.volume.reduce((sum, v) => sum + v.value, 0);
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
  }, [isReview, liveQuote, histData, activeTicker, reviewDate, reviewTime]);

  // Reference (prev day) — date depends on mode
  const refDate = isReview ? reviewDateCompact : new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const { data: reference } = useFetch<ReferenceResponse>(['reference', activeTicker, refDate], `/api/market/reference/${activeTicker}/${refDate}`, { staleTime: 3_600_000 });

  // Dashboard brief — pass ?date= in review mode. When the market is open the
  // API overlays live quote data on top of the daily snapshot, so refetch
  // every 15s to keep the bias card in sync with the tape.
  const briefUrl = isReview ? `/api/dashboard/brief/${activeTicker}?date=${reviewDate}` : `/api/dashboard/brief/${activeTicker}`;
  const { data: brief } = useFetch<BriefResponse>(['brief', activeTicker, reviewDate ?? 'live'], briefUrl, {
    staleTime: isOpen ? 10_000 : 300_000,
    refetchInterval: isOpen ? 15_000 : false,
  });

  // ── Market Overview: intraday bars for the last ~2 trading days ──
  // Uses the YYYYMM form of /api/market/data which returns the whole month of
  // bars in one call; we filter to regular-session hours and slice to the last 2
  // trading days client-side.
  //
  // IMPORTANT: AlphaVantage intraday bars are stored in Cloud SQL with ET times
  // labeled as UTC (e.g. an ET 09:30 bar has unix seconds corresponding to
  // 09:30 UTC). That's why we use `getUTCHours()` / `getUTCDate()` below — the
  // UTC components give us the ET wall-clock time the user expects.
  const [timeframe, setTimeframe] = useState<1 | 5 | 15 | 30 | 60>(60);
  const [tfOpen, setTfOpen] = useState(false);

  const monthCode = useMemo(() => {
    const refSource = isReview ? reviewDate : brief?.daily_indicators?.date;
    if (!refSource) return null;
    return refSource.replace(/-/g, '').slice(0, 6); // YYYYMM
  }, [isReview, reviewDate, brief?.daily_indicators?.date]);

  const hourlyUrl = monthCode ? `/api/market/data/${activeTicker}/${monthCode}?timeframe=${timeframe}` : '';
  const { data: hourlyData } = useFetch<MarketDataResponse>(
    ['hourly', activeTicker, monthCode ?? 'none', String(timeframe)],
    hourlyUrl,
    { staleTime: 3_600_000, enabled: !!monthCode },
  );

  // Transform bars into PriceAreaChart points:
  //   1) Filter to ET 04:00-16:00 (pre-market + regular hours, matches NVDA reference)
  //   2) Slice to the last 2 distinct ET calendar days
  //   3) Format labels using UTC components (= ET wall-clock)
  const pricePoints = useMemo<PricePoint[]>(() => {
    const bars = hourlyData?.candlestick ?? [];
    if (!bars.length) return [];

    // 1) filter by time-of-day (ET 04:00 inclusive → 16:00 inclusive)
    const inSession = bars.filter((b) => {
      const d = new Date(b.time * 1000);
      const h = d.getUTCHours();
      return h >= 4 && h <= 16;
    });

    // 2) slice to the last 2 distinct ET calendar days (YYYY-MM-DD from UTC)
    const dayKey = (t: number) => {
      const d = new Date(t * 1000);
      return `${d.getUTCFullYear()}-${d.getUTCMonth() + 1}-${d.getUTCDate()}`;
    };
    const uniqueDays: string[] = [];
    for (let i = inSession.length - 1; i >= 0 && uniqueDays.length < 2; i--) {
      const key = dayKey(inSession[i].time);
      if (!uniqueDays.includes(key)) uniqueDays.push(key);
    }
    const lastTwoDays = inSession.filter((b) => uniqueDays.includes(dayKey(b.time)));

    // 3) format labels
    return lastTwoDays.map((b) => {
      const d = new Date(b.time * 1000);
      const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
      const dd = String(d.getUTCDate()).padStart(2, '0');
      const hh = String(d.getUTCHours()).padStart(2, '0');
      const mi = String(d.getUTCMinutes()).padStart(2, '0');
      return {
        time: b.time,
        price: b.close,
        label: `${mm}/${dd} ${hh}:${mi}`,
      };
    });
  }, [hourlyData]);

  // Session boundary = first bar of the most recent ET day
  const sessionBoundary = useMemo<{ time: number; label: string } | null>(() => {
    if (pricePoints.length < 2) return null;
    const dayKey = (t: number) => {
      const d = new Date(t * 1000);
      return `${d.getUTCFullYear()}-${d.getUTCMonth() + 1}-${d.getUTCDate()}`;
    };
    const lastDayKey = dayKey(pricePoints[pricePoints.length - 1].time);
    const boundary = pricePoints.find((p) => dayKey(p.time) === lastDayKey);
    if (!boundary || boundary.time === pricePoints[0].time) return null;
    const d = new Date(boundary.time * 1000);
    const label = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()))
      .toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
    return { time: boundary.time, label };
  }, [pricePoints]);

  // ── 4 KPI cards (match NVDA reference: prev close, latest close, 2-day change, RSI) ──
  const kpiCards = useMemo(() => {
    const prevClose = reference?.close;
    const prevDateStr = reference?.date;
    const latestClose = brief?.daily_indicators?.close;
    const latestDateStr = brief?.daily_indicators?.date;
    const rsi = brief?.daily_indicators?.rsi_14;
    if (!prevClose || !latestClose || !prevDateStr || !latestDateStr) return null;

    const fmtCardDate = (dateStr: string) => {
      // Accept YYYYMMDD or YYYY-MM-DD
      const clean = dateStr.replace(/-/g, '');
      const year = clean.slice(0, 4);
      const month = clean.slice(4, 6);
      const day = clean.slice(6, 8);
      const dt = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
      return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }).toUpperCase();
    };

    const changeAbs = latestClose - prevClose;
    const changePct = (changeAbs / prevClose) * 100;

    const wkAvgClose = reference?.week?.avg_close;
    const wkAvgRsi = reference?.week?.avg_rsi_14 ?? undefined;
    const wkSessions = reference?.week?.sessions;
    const vsWeek = (v: number): string => {
      if (!wkAvgClose) return 'Regular market close';
      const p = ((v - wkAvgClose) / wkAvgClose) * 100;
      const label = wkSessions ? `prev ${wkSessions}d avg` : 'prev wk avg';
      return `${p >= 0 ? '+' : ''}${p.toFixed(2)}% vs ${label}`;
    };

    // Zone labels come from /api/config/indicators — the same thresholds
    // Python uses. See useIndicatorConfig. indicatorCfg is read from the
    // outer scope where the hook is called.
    const rsiZone = (v: number | undefined): string => {
      if (v === undefined) return '—';
      return classifyRsiZone(v, indicatorCfg?.rsi.zones);
    };
    const rsiTone = (v: number | undefined): 'bull' | 'bear' | 'warn' | 'default' => {
      if (v === undefined) return 'default';
      if (v < 30) return 'bull';          // oversold → likely to bounce
      if (v > 70) return 'bear';          // overbought → likely to fade
      return 'warn';                       // mid-range
    };

    return {
      prev: {
        label: `${fmtCardDate(prevDateStr)} CLOSE`,
        value: `$${prevClose.toFixed(2)}`,
        subtitle: vsWeek(prevClose),
      },
      latest: {
        label: `${fmtCardDate(latestDateStr)} CLOSE`,
        value: `$${latestClose.toFixed(2)}`,
        subtitle: vsWeek(latestClose),
      },
      change: {
        label: '2-DAY CHANGE',
        value: `${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%`,
        subtitle: `${changeAbs >= 0 ? '+' : ''}$${changeAbs.toFixed(2)} per share`,
        tone: (changePct >= 0 ? 'bull' : 'bear') as 'bull' | 'bear',
        direction: (changePct >= 0 ? 'up' : 'down') as 'up' | 'down',
      },
      rsi: {
        label: 'RSI (14) LATEST',
        value: rsi !== undefined ? rsi.toFixed(1) : '—',
        subtitle: (() => {
          const zone = rsiZone(rsi);
          if (rsi === undefined || wkAvgRsi === undefined || !wkSessions) return zone;
          const p = ((rsi - wkAvgRsi) / wkAvgRsi) * 100;
          return `${zone} · ${p >= 0 ? '+' : ''}${p.toFixed(1)}% vs ${wkSessions}d avg`;
        })(),
        tone: rsiTone(rsi),
      },
    };
  }, [reference, brief]);

  const { data: btData } = useFetch<BacktestResponse>(['bt', activeTicker], `/api/backtest/results/${activeTicker}`, { staleTime: 3_600_000 });
  const { data: eqData } = useFetch<EquityResponse>(['eq', activeTicker], `/api/backtest/equity/${activeTicker}`, { staleTime: 3_600_000 });

  // Signals URL — server-side filter when in review mode
  const sigUrl = isReview
    ? `/api/signals/${activeTicker}?limit=20&end_date=${reviewDate}${reviewTime ? `&end_time=${reviewTime}` : ''}`
    : `/api/signals/${activeTicker}?limit=20`;
  const { data: sigData } = useFetch<SignalsResponse>(
    ['sig', activeTicker, reviewDate ?? 'live', reviewTime ?? 'eod'],
    sigUrl,
    { staleTime: 300_000 }
  );

  const { data: pbData } = useFetch<PlaybookResponse>(['pb', activeTicker], `/api/playbook/${activeTicker}`, { staleTime: 3_600_000 });

  const signals = sigData?.signals ?? [];
  const cards = pbData?.cards ?? [];
  const di = brief?.daily_indicators ?? {};

  // Live data for condition evaluation (only in live mode)
  const isMarketOpenish = !isReview && (!!status?.is_open || status?.session === 'pre-market' || status?.session === 'after-hours');
  const { data: liveHistory } = useLiveHistory(activeTicker, isMarketOpenish);
  const { data: avgVol } = useAvgVolume(activeTicker);
  // Indicators computed server-side (lib/indicators.py) — never duplicated in TS.
  const indicatorsQuery = useLiveIndicators(
    {
      bars: liveHistory?.bars ?? [],
      current_price: liveQuote?.price ?? null,
      current_volume: liveQuote?.volume ?? null,
      avg_volume_20d: avgVol?.avg_volume_20d ?? null,
    },
    !isReview && !!liveHistory?.bars && liveHistory.bars.length > 0,
  );

  const snapshot = useMemo(
    () =>
      isReview
        ? null
        : buildSnapshot({
            bars: liveHistory?.bars,
            quote: liveQuote,
            avgVolume20d: avgVol?.avg_volume_20d ?? null,
            reference,
            indicators: indicatorsQuery.data?.indicators,
          }),
    [isReview, liveHistory, liveQuote, avgVol, reference, indicatorsQuery.data],
  );

  // Top playbook match: pick card matching bias with best win_rate
  const topCard = useMemo(() => {
    if (!cards.length) return null;
    const biasDir = brief?.bias === 'bullish' ? 'CALL' : brief?.bias === 'bearish' ? 'PUT' : null;
    const candidates = biasDir ? cards.filter(c => c.direction === biasDir) : cards;
    return (candidates.length ? candidates : cards).reduce((best, c) => (c.win_rate > best.win_rate ? c : best));
  }, [cards, brief?.bias]);

  // Server-evaluated conditions for the top playbook card.
  const topConditions = topCard?.conditions;
  const topEvalQuery = usePlaybookEvaluation(topConditions, snapshot);
  const topCardResults = useMemo<EvalResult[]>(() => {
    if (!topCard) return [];
    if (topEvalQuery.data) return topEvalQuery.data;
    // Placeholder while loading / when snapshot isn't ready.
    return topCard.conditions.map(() => ({
      status: 'unknown' as const,
      reason: snapshot ? 'evaluating' : 'no live data',
    }));
  }, [topCard, topEvalQuery.data, snapshot]);

  // Filter backtest trades by review date (frontend-only — trades are bounded, already fetched)
  const filteredTrades = useMemo(() => {
    const trades = (btData?.trades ?? []) as Array<{ entry_time: string; direction: string; return_pct: number; exit_reason: string }>;
    if (!isReview) return trades;
    const cutoff = `${reviewDate} ${reviewTime ?? '23:59'}:59`;
    return trades.filter(t => t.entry_time <= cutoff);
  }, [btData?.trades, isReview, reviewDate, reviewTime]);

  // Compute summary from filtered trades (guards for empty / divide-by-zero)
  const summary = useMemo(() => {
    if (!isReview) return btData?.summary;
    if (filteredTrades.length === 0) return null;
    const wins = filteredTrades.filter(t => t.return_pct > 0);
    const losses = filteredTrades.filter(t => t.return_pct <= 0);
    const total = filteredTrades.length;
    const avg_win_pct = wins.length ? wins.reduce((s, t) => s + t.return_pct, 0) / wins.length : 0;
    const avg_loss_pct = losses.length ? losses.reduce((s, t) => s + t.return_pct, 0) / losses.length : 0;
    const avg_return_pct = filteredTrades.reduce((s, t) => s + t.return_pct, 0) / total;
    const total_return_pct = filteredTrades.reduce((s, t) => s + t.return_pct, 0) * 100;
    return {
      total_trades: total,
      win_count: wins.length,
      loss_count: losses.length,
      win_rate: wins.length / total,
      avg_return_pct,
      avg_win_pct,
      avg_loss_pct,
      total_return_pct,
    };
  }, [isReview, btData?.summary, filteredTrades]);

  // Profit factor (guard against divide-by-zero)
  const profitFactor = useMemo(() => {
    if (!summary || summary.total_trades === 0) return null;
    const grossWin = Math.abs(summary.avg_win_pct * summary.win_count);
    const grossLoss = Math.abs(summary.avg_loss_pct * summary.loss_count);
    return grossLoss > 0 ? grossWin / grossLoss : null;
  }, [summary]);

  // Best/worst trades from the filtered set
  const { bestTrades, worstTrades } = useMemo(() => {
    const sorted = [...filteredTrades].sort((a, b) => b.return_pct - a.return_pct);
    return { bestTrades: sorted.slice(0, 5), worstTrades: sorted.slice(-5).reverse() };
  }, [filteredTrades]);

  const cloudSqlOk = health?.cloud_sql ?? false;

  // Market status pill — top-right of page header. Replaces the earlier
  // "Live Data via Alpha Vantage" pill per user request: the indicator should
  // clearly communicate whether the market (and therefore the data stream)
  // is live, pre/after-hours, or closed.
  const marketStatus = isReview
    ? { label: `Review ${reviewDate}`, dot: 'bg-[var(--warn)]', text: 'text-[var(--warn)]', pulse: false }
    : isOpen
      ? { label: 'Market Open', dot: 'bg-[var(--bull)]', text: 'text-[var(--bull)]', pulse: true }
      : status?.session === 'pre-market'
        ? { label: 'Pre-Market', dot: 'bg-[var(--warn)]', text: 'text-[var(--warn)]', pulse: true }
        : status?.session === 'after-hours'
          ? { label: 'After Hours', dot: 'bg-[var(--warn)]', text: 'text-[var(--warn)]', pulse: true }
          : { label: 'Market Closed', dot: 'bg-[var(--bear)]', text: 'text-[var(--bear)]', pulse: false };

  return (
    <div className="space-y-6">
      {/* ── Page header: Ticker + metadata (left) · Market status + Cloud SQL (right) ── */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-[var(--color-brand)]">{activeTicker}</h1>
          <p className="label-micro mt-2">
            Dashboard · {
              (isReview && reviewDate
                ? new Date(`${reviewDate}T00:00:00`)
                : new Date()
              ).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }).toUpperCase()
            }
            {isReview && reviewTime && ` · ${reviewTime} ET`}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          {/* Market status pill — with time when live */}
          <div className="inline-flex items-center gap-2 rounded-full bg-[var(--surface-2)] px-3 py-1.5">
            <span className={`h-1.5 w-1.5 rounded-full ${marketStatus.dot} ${marketStatus.pulse ? 'animate-pulse' : ''}`} />
            <span className={`text-xs font-medium ${marketStatus.text}`}>{marketStatus.label}</span>
            {status && !isReview && (
              <span className="text-xs text-[var(--on-surface-muted)]">
                · {to12h(status.current_time_et)} ET
              </span>
            )}
          </div>

          {/* Cloud SQL status pill — stacked under the market status */}
          <div className="inline-flex items-center gap-1.5 rounded-full bg-[var(--surface-2)] px-3 py-1.5">
            <Database size={12} className={cloudSqlOk ? 'text-[var(--color-brand)]' : 'text-[var(--warn)]'} />
            <span className={`text-xs font-medium ${cloudSqlOk ? 'text-[var(--color-brand)]' : 'text-[var(--warn)]'}`}>
              {cloudSqlOk ? 'Cloud SQL' : 'Cloud SQL Disconnected'}
            </span>
          </div>
        </div>
      </div>

      {/* Cloud SQL alert banner — prominent when disconnected */}
      {!cloudSqlOk && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-2.5">
          <AlertTriangle size={16} className="text-[var(--warn)] shrink-0" />
          <span className="text-xs text-[var(--warn)]">
            Cloud SQL not connected — premarket analysis and daily indicators unavailable. Check <code className="font-mono bg-amber-500/20 px-1 rounded">CLOUD_SQL_CONNECTION_NAME</code> env var.
          </span>
        </div>
      )}

      {/* Brief source alert — when Cloud SQL is connected but brief endpoint reports unavailable */}
      {cloudSqlOk && brief?.source === 'unavailable' && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-2.5">
          <AlertTriangle size={16} className="text-[var(--warn)] shrink-0" />
          <span className="text-xs text-[var(--warn)]">{brief.reason}</span>
        </div>
      )}

      {/* ── SECTION 2: Price + Key Levels ────────────────────────────────── */}
      <div className="rounded-xl bg-[var(--surface-2)] p-6">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          {/* Ticker + price */}
          <div>
            <h2 className="label-micro">{activeTicker}</h2>
            <p className="font-mono text-4xl font-bold text-[var(--color-text-primary)] leading-tight mt-1">
              ${quote?.price?.toFixed(2) ?? '--'}
            </p>
          </div>

          {/* Change + OHLV grouped, vertically centered against price */}
          {quote && (
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
              <div className={quote.change >= 0 ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}>
                <p className="text-xl font-bold font-mono leading-tight">
                  {quote.change >= 0 ? '+' : ''}{quote.change.toFixed(2)}
                </p>
                <p className="text-sm font-mono">
                  ({quote.change_pct >= 0 ? '+' : ''}{quote.change_pct.toFixed(2)}%)
                </p>
              </div>

              <div className="flex gap-4 text-xs">
                <span className="text-[var(--color-text-muted)]">O <span className="text-[var(--color-accent-blue)] font-mono font-semibold">${quote.open.toFixed(2)}</span></span>
                <span className="text-[var(--color-text-muted)]">H <span className="text-[var(--bull)] font-mono font-semibold">${quote.high.toFixed(2)}</span></span>
                <span className="text-[var(--color-text-muted)]">L <span className="text-[var(--warn)] font-mono font-semibold">${quote.low.toFixed(2)}</span></span>
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
              <span className="flex items-center gap-2">
                Previous Day Range
                {reference.source === 'cloud_sql' && (reference.stale_days ?? 0) > 3 && (
                  <span className="inline-flex items-center gap-0.5 text-[var(--warn)] normal-case" title="AlphaVantage unavailable — using Cloud SQL fallback which may be outdated">
                    <AlertTriangle size={10} /> stale
                  </span>
                )}
              </span>
              {quote && (
                <span>
                  {quote.price > reference.high
                    ? <span className="text-[var(--bull)]">Above prev high</span>
                    : quote.price < reference.low
                    ? <span className="text-[var(--warn)]">Below prev low</span>
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
                <span className="mt-0 font-mono text-[10px] text-[var(--warn)] whitespace-nowrap">L ${reference.low.toFixed(2)}</span>
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
                <span className="font-mono text-[10px] text-[var(--bull)] whitespace-nowrap">H ${reference.high.toFixed(2)}</span>
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

        {/* Previous Week Range — matching visual style under the Day Range */}
        {reference?.week && (
          <div className="mt-4 pt-3">
            <div className="mb-2 flex items-center justify-between text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
              <span>
                Previous Week Range ({reference.week.sessions} sessions)
              </span>
              {quote && (
                <span>
                  {quote.price > reference.week.high
                    ? <span className="text-[var(--bull)]">Above week high</span>
                    : quote.price < reference.week.low
                    ? <span className="text-[var(--warn)]">Below week low</span>
                    : `${((quote.price - reference.week.low) / (reference.week.high - reference.week.low) * 100).toFixed(0)}% of range`}
                </span>
              )}
            </div>

            <div className="relative h-8">
              {/* Full range line — slightly dimmer than the day bar to distinguish */}
              <div className="absolute inset-x-0 top-1/2 h-0.5 -translate-y-1/2 bg-gradient-to-r from-amber-400 via-[var(--color-brand)] to-green-400 opacity-40" />

              {/* Low marker */}
              <div className="absolute left-0 top-0 flex flex-col items-center">
                <div className="h-full w-0.5 bg-amber-400" />
                <span className="mt-0 font-mono text-[10px] text-[var(--warn)] whitespace-nowrap">L ${reference.week.low.toFixed(2)}</span>
              </div>

              {/* High marker */}
              <div className="absolute right-0 top-0 flex flex-col items-center">
                <div className="h-full w-0.5 bg-green-400" />
                <span className="font-mono text-[10px] text-[var(--bull)] whitespace-nowrap">H ${reference.week.high.toFixed(2)}</span>
              </div>

              {/* Current price marker (circle on line) */}
              {quote && (() => {
                const w = reference.week!;
                const pct = Math.max(0, Math.min(100, ((quote.price - w.low) / (w.high - w.low)) * 100));
                return (
                  <div
                    className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--color-text-primary)] border-2 border-[var(--color-bg-secondary)] shadow-lg"
                    style={{ left: `${pct}%` }}
                    title={`Current: $${quote.price.toFixed(2)}`}
                  />
                );
              })()}
            </div>

            {/* Date range footer */}
            <div className="mt-1 flex justify-between text-[10px] text-[var(--color-text-muted)]">
              <span>{reference.week.start_date}</span>
              <span>{reference.week.end_date}</span>
            </div>
          </div>
        )}
      </div>

      {/* ── SECTION 2B: 4 daily KPI cards (matches NVDA reference) ────────── */}
      {kpiCards && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            label={kpiCards.prev.label}
            value={kpiCards.prev.value}
            subtitle={kpiCards.prev.subtitle}
          />
          <MetricCard
            label={kpiCards.latest.label}
            value={kpiCards.latest.value}
            subtitle={kpiCards.latest.subtitle}
          />
          <MetricCard
            label={kpiCards.change.label}
            value={kpiCards.change.value}
            subtitle={kpiCards.change.subtitle}
            tone={kpiCards.change.tone}
            direction={kpiCards.change.direction}
          />
          <MetricCard
            label={kpiCards.rsi.label}
            value={kpiCards.rsi.value}
            subtitle={kpiCards.rsi.subtitle}
            tone={kpiCards.rsi.tone}
          />
        </div>
      )}

      {/* ── SECTION 2C: Price chart card with timeframe dropdown ───────────── */}
      {pricePoints.length > 0 && (
        <div className="rounded-xl bg-[var(--surface-2)] p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="label-micro">Price</h2>

            {/* Timeframe dropdown */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setTfOpen((v) => !v)}
                onBlur={() => setTimeout(() => setTfOpen(false), 120)}
                className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[10px] font-medium transition-colors text-[var(--brand)] border border-[var(--outline)]"
                style={{ background: 'color-mix(in oklab, var(--brand) 8%, transparent)' }}
              >
                {timeframe}min bars
                <ChevronDown size={12} className={tfOpen ? 'rotate-180 transition-transform' : 'transition-transform'} />
              </button>
              {tfOpen && (
                <div
                  className="absolute right-0 top-full z-20 mt-1 min-w-[120px] overflow-hidden rounded-lg py-1 text-[11px] bg-[var(--surface-lowest)] border border-[var(--outline)]"
                  style={{ backdropFilter: 'blur(8px)' }}
                >
                  {([1, 5, 15, 30, 60] as const).map((tf) => (
                    <button
                      key={tf}
                      type="button"
                      onMouseDown={(e) => { e.preventDefault(); setTimeframe(tf); setTfOpen(false); }}
                      className={`block w-full px-3 py-1.5 text-left transition-colors ${
                        tf === timeframe
                          ? 'font-semibold text-[var(--brand)]'
                          : 'text-[var(--on-surface-variant)] hover:bg-[var(--surface-3)]'
                      }`}
                      style={tf === timeframe ? { background: 'color-mix(in oklab, var(--brand) 8%, transparent)' } : undefined}
                    >
                      {tf}min bars
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
          <PriceAreaChart
            data={pricePoints}
            seriesLabel={`${activeTicker} close price`}
            sessionBoundary={sessionBoundary}
            height={280}
          />
        </div>
      )}

      {/* ── SECTION 3: Strategy Readiness ────────────────────────────────── */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Card A: Daily Bias */}
        <div className={`rounded-lg border-2 ${biasBorder(brief?.bias ?? 'neutral')} bg-[var(--color-bg-secondary)] p-6`}>
          <div className="flex items-center gap-2 mb-3">
            <Activity size={14} className="text-[var(--color-accent-blue)]" />
            <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Daily Bias</h2>
            {brief?.source === 'unavailable' && (
              <span className="ml-auto text-xs text-[var(--warn)]">Cloud SQL unavailable</span>
            )}
            {!isReview && brief?.live && (
              <span className="ml-auto inline-flex items-center gap-1.5 text-[10px] font-semibold text-[var(--bull)]" title={`Live overlay from ${brief.live.source}`}>
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75"></span>
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500"></span>
                </span>
                LIVE
              </span>
            )}
            {!isReview && !brief?.live && brief?.source === 'cloud_sql' && (di.stale_days ?? 0) >= 1 && (
              <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-[var(--warn)]" title="Cloud SQL market_data_daily backfill needed">
                <AlertTriangle size={11} /> {di.stale_days}d stale
              </span>
            )}
          </div>

          {brief?.source === 'cloud_sql' ? (
            <div className="space-y-3">
              {/* Big bias indicator */}
              <div className="flex items-center gap-3">
                {biasIcon(brief.bias)}
                <div>
                  <p className={`text-lg font-bold ${
                    brief.bias === 'bullish' ? 'text-[var(--bull)]' :
                    brief.bias === 'bearish' ? 'text-[var(--bear)]' :
                    'text-[var(--color-text-primary)]'
                  }`}>
                    {brief.bias.toUpperCase()}
                  </p>
                  <p className="text-[10px] text-[var(--color-text-muted)]">
                    {brief.live
                      ? `Live ${brief.live.session} — $${brief.live.price.toFixed(2)}`
                      : di.date ? `Based on ${di.date} daily close` : ''}
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
                    <span>vs EMA9: <span className={`font-mono font-semibold ${di.price_vs_ema9 >= 0 ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}`}>{pct(di.price_vs_ema9, 2)}</span></span>
                  )}
                  {di.price_vs_ema20 != null && (
                    <span>vs EMA20: <span className={`font-mono font-semibold ${di.price_vs_ema20 >= 0 ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}`}>{pct(di.price_vs_ema20, 2)}</span></span>
                  )}
                  {di.sma_200 != null && di.close != null && (
                    <span>vs SMA200: <span className={`font-mono font-semibold ${di.close >= di.sma_200 ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}`}>
                      {pct(((di.close - di.sma_200) / di.sma_200) * 100, 1)}
                    </span></span>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2 text-xs text-[var(--warn)]">
              <AlertTriangle size={14} />
              <span>Daily bias unavailable — Cloud SQL not connected</span>
            </div>
          )}
        </div>

        {/* Card B: Top Playbook Match */}
        <div className="rounded-xl bg-[var(--surface-2)] p-6">
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
                  ? <TrendingUp size={16} className="text-[var(--bull)]" />
                  : topCard.direction === 'PUT'
                  ? <TrendingDown size={16} className="text-[var(--bear)]" />
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
                  Avg: <span className={`font-mono font-semibold ${topCard.avg_return >= 0 ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}`}>
                    {returnPct(topCard.avg_return)}
                  </span>
                </span>
              </div>

              {topCard.conditions.length > 0 && (
                <div className="space-y-1 mt-1">
                  <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider">Conditions</p>
                  {topCard.conditions.slice(0, 5).map((c, i) => {
                    const result = topCardResults[i] ?? { status: 'unknown' as const, reason: '' };
                    const isMet = result.status === 'met';
                    const isUnknown = result.status === 'unknown';
                    return (
                      <div key={i} className="flex items-start gap-1.5 text-[11px]">
                        {isMet ? (
                          <CheckCircle size={12} className="mt-0.5 shrink-0 text-[var(--color-accent-blue)]" />
                        ) : isUnknown ? (
                          <HelpCircle size={12} className="mt-0.5 shrink-0 text-[var(--color-text-muted)] opacity-60" />
                        ) : (
                          <Circle size={12} className="mt-0.5 shrink-0 text-[var(--color-text-muted)]" />
                        )}
                        <span className={isMet ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'}>
                          {c}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-[var(--color-text-muted)]">No playbook — run phase 6 pipeline first.</p>
          )}
        </div>
      </div>

      {/* ── SECTION 4: Performance KPIs ──────────────────────────────────── */}
      {isReview && filteredTrades.length === 0 ? (
        <div className="flex items-center gap-2 rounded-xl bg-[var(--surface-2)] px-4 py-6">
          <AlertTriangle size={16} className="text-[var(--warn)] shrink-0" />
          <span className="text-sm text-[var(--color-text-muted)]">
            No backtest trades before {reviewDate}{reviewTime ? ` ${reviewTime} ET` : ''}. Earliest trade: {(btData?.trades?.[0] as { entry_time?: string } | undefined)?.entry_time ?? 'N/A'}
          </span>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricCard
            label="Direction Win Rate"
            value={summary ? `${(summary.win_rate * 100).toFixed(1)}%` : '--'}
            direction={summary ? (summary.win_rate >= 0.5 ? 'up' : summary.win_rate >= 0.4 ? 'neutral' : 'down') : undefined}
            subtitle={summary ? `Stock moved your way ${Math.round(summary.win_rate * 10)} in 10 trades${isReview ? ` (${summary.total_trades.toLocaleString()} trades)` : ''}` : undefined}
          />
          <MetricCard
            label="Avg Win / Loss (stock)"
            value={summary ? `+${(summary.avg_win_pct * 100).toFixed(2)}% / ${(summary.avg_loss_pct * 100).toFixed(2)}%` : '--'}
            direction={summary ? (Math.abs(summary.avg_win_pct) > Math.abs(summary.avg_loss_pct) ? 'up' : 'down') : undefined}
            subtitle={
              summary && summary.avg_loss_pct !== 0
                ? `Winners ${(Math.abs(summary.avg_win_pct / summary.avg_loss_pct)).toFixed(1)}x larger · ≈ ${(summary.avg_win_pct * 100 * 0.35).toFixed(2)}% on a slightly-OTM option`
                : summary ? 'No losses in period' : undefined
            }
          />
          <MetricCard
            label="Total Return"
            value={
              // In review mode use filtered summary (eqData is lifetime, misleading)
              isReview
                ? (summary ? pct(summary.total_return_pct) : '--')
                : (eqData ? pct(eqData.summary.total_return_pct) : summary ? pct(summary.total_return_pct) : '--')
            }
            direction={
              isReview
                ? ((summary?.total_return_pct ?? 0) >= 0 ? 'up' : 'down')
                : ((eqData?.summary.total_return_pct ?? summary?.total_return_pct ?? 0) >= 0 ? 'up' : 'down')
            }
            subtitle={
              isReview
                ? `Filtered sum of ${summary?.total_trades ?? 0} trades`
                : (eqData ? `Worst drawdown: ${eqData.summary.max_drawdown_pct.toFixed(1)}%` : undefined)
            }
          />
          <MetricCard
            label="Profit Factor"
            value={profitFactor !== null ? profitFactor.toFixed(2) : '--'}
            direction={profitFactor !== null ? (profitFactor >= 1 ? 'up' : 'down') : undefined}
            subtitle={
              profitFactor !== null
                ? `$1 risked → $${profitFactor.toFixed(2)} back`
                : summary ? 'Insufficient data' : undefined
            }
          />
        </div>
      )}

      {/* Leverage translation — explains how the small stock-move % above
          maps to a meaningful option return. Phase 2 will replace the linear
          delta estimate with real contract premium math. */}
      {summary && summary.total_trades > 0 && (
        <div className="grid gap-3 lg:grid-cols-2">
          <LeverageCard
            label="Avg Win"
            stockMovePct={summary.avg_win_pct}
          />
          <LeverageCard
            label="Avg Loss"
            stockMovePct={summary.avg_loss_pct}
          />
          <div className="lg:col-span-2">
            <LeverageCurveChart highlightStockMovePct={summary.avg_win_pct} />
          </div>
        </div>
      )}

      {/* ── SECTION 5: Recent Activity ───────────────────────────────────── */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Panel A: Latest Signals */}
        <div className="rounded-xl bg-[var(--surface-2)] p-6">
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
                  <span className={`text-xs font-bold ${s.direction === 'CALL' ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}`}>
                    {s.direction === 'CALL' ? '▲' : '▼'}
                  </span>
                  <span className="text-xs text-[var(--color-text-secondary)] font-mono">{s.conditions_met ?? `${s.score}/5`}</span>
                  <span className="font-mono text-[10px] text-[var(--color-text-muted)] truncate">{s.time.slice(5, 16)}</span>
                  <span className={`text-right font-mono text-xs font-semibold ${s.return_pct >= 0 ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}`}>
                    {returnPct(s.return_pct)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Panel B: Best / Worst Trades */}
        <div className="rounded-xl bg-[var(--surface-2)] p-6">
          <div className="mb-3 flex items-center gap-2">
            <BookOpen size={14} className="text-[var(--color-accent-blue)]" />
            <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Best / Worst Trades</h2>
          </div>
          {bestTrades.length === 0 ? (
            <p className="text-xs text-[var(--color-text-muted)]">
              {isReview ? `No trades before ${reviewDate}${reviewTime ? ` ${reviewTime}` : ''}` : 'No backtest trades.'}
            </p>
          ) : (
            <div className="space-y-2">
              {/* Best */}
              <div>
                <p className="text-[10px] uppercase tracking-wider text-[var(--bull)] mb-1 px-2">Top Winners</p>
                {bestTrades.map((t, i) => (
                  <div key={`w${i}`} className="flex items-center justify-between rounded px-2 py-0.5 hover:bg-[var(--color-bg-tertiary)]">
                    <div className="flex items-center gap-2 text-xs">
                      <span className={t.direction === 'CALL' ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}>
                        {t.direction === 'CALL' ? '▲' : '▼'}
                      </span>
                      <span className="font-mono text-[10px] text-[var(--color-text-muted)]">{t.entry_time.slice(5, 16)}</span>
                      <span className="text-[10px] text-[var(--color-text-muted)]">{t.exit_reason}</span>
                    </div>
                    <span className="font-mono text-xs font-semibold text-[var(--bull)]">{returnPct(t.return_pct)}</span>
                  </div>
                ))}
              </div>
              {/* Worst */}
              <div>
                <p className="text-[10px] uppercase tracking-wider text-[var(--bear)] mb-1 px-2">Worst Losers</p>
                {worstTrades.map((t, i) => (
                  <div key={`l${i}`} className="flex items-center justify-between rounded px-2 py-0.5 hover:bg-[var(--color-bg-tertiary)]">
                    <div className="flex items-center gap-2 text-xs">
                      <span className={t.direction === 'CALL' ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}>
                        {t.direction === 'CALL' ? '▲' : '▼'}
                      </span>
                      <span className="font-mono text-[10px] text-[var(--color-text-muted)]">{t.entry_time.slice(5, 16)}</span>
                      <span className="text-[10px] text-[var(--color-text-muted)]">{t.exit_reason}</span>
                    </div>
                    <span className="font-mono text-xs font-semibold text-[var(--bear)]">{returnPct(t.return_pct)}</span>
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
