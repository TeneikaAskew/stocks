/**
 * Overview — the briefing-first home page (Obsidian Analyst redesign).
 *
 * Ported from the Claude Design prototype's `PageOverview`. Layout:
 *   1. Briefing strip — pre-market brief + hero ticker + Top setup
 *   2. Live signals · Today's catalysts
 *   3. Sector rotation · AI take · News feed
 *
 * Everything is keyed to the active ticker (the app's existing per-ticker
 * model — the sidebar/⌘K ticker switcher drives the brief, setup, signals
 * and AI take); catalysts/news are market-wide. Per CLAUDE.md Rule 3.7 a
 * missing value renders an explicit "unavailable" state — never a fabricated 0.
 */
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Button } from '@heroui/react';
import {
  Bell, Calendar, Sparkles, Newspaper, Grid3x3, Check,
  AlertTriangle, RefreshCw,
} from 'lucide-react';
import { useTickerStore } from '@/stores/tickerStore';
import { useReviewDateStore } from '@/stores/reviewDateStore';
import { useLiveStatus } from '@/hooks/useLiveStatus';
import { useLiveQuote } from '@/hooks/useLiveQuote';
import { useReviewQuote } from '@/hooks/useReviewQuote';
import { useInsightReport } from '@/hooks/useInsights';
import {
  Pill, Metric, MicroLabel, Delta, ScoreStars, DirTag, Card, CardHeader, KpiTile,
} from '@/components/primitives';
import { TickerSelect } from '@/components/shared/TickerSelect';
import { MovementRead } from '@/components/dashboard/MovementRead';
import { SetupCardDetails, type SetupHorizon } from '@/components/playbook/SetupCardDetails';
import { PriceAreaChart, type PricePoint } from '@/components/charts/PriceAreaChart';
import { CandlestickChart } from '@/components/charts/CandlestickChart';
import { fmtPrice, fmtPct, fmtNum, NA } from '@/lib/format';
import type { Tone } from '@/components/primitives';

// ── Response shapes (mirror the existing API contracts) ──────────────────────
interface DailyIndicators {
  date?: string; close?: number; rsi_14?: number; rvol?: number;
  strat_candle?: string; strat_combo?: string;
  ftfc_score?: number; ftfc_direction?: string;
}
interface BriefResponse {
  ticker: string; source: string; bias: string; reason?: string;
  rsi?: number; strat_candle?: string; strat_combo?: string;
  ftfc_score?: number; ftfc_direction?: string; signal_status?: string;
  daily_indicators: DailyIndicators;
  live?: { price: number; session: string };
}
interface PlaybookCard {
  id: string; name: string; direction: string; win_rate: number;
  avg_return: number; conditions: string[]; description: string;
  target_pct?: number | null; stop_pct?: number | null;
  horizons?: SetupHorizon[];
  best_horizon_min?: number | null; best_horizon_win_rate?: number | null; best_horizon_avg_bps?: number | null;
}
interface PlaybookResponse { ticker: string; cards: PlaybookCard[] }
interface SignalEntry {
  time: string; direction: string; score: number;
  conditions_met: string; return_pct: number;
}
interface SignalsResponse { ticker: string; count: number; signals: SignalEntry[] }

interface ReferenceResponse {
  ticker: string; date: string; close: number; high: number; low: number;
  week?: { high: number; low: number; avg_close?: number } | null;
}
interface MarketDataResponse {
  candlestick: Array<{ time: number; open: number; high: number; low: number; close: number }>;
  volume: Array<{ time: number; value: number }>;
}

interface CatalystEvent {
  date: string; ticker: string; title?: string; event?: string;
  catalyst_type?: string; impact?: string; expected_impact?: string;
  sentiment_label?: string; sentiment_score?: number;
}
interface CatalystsResponse { events_by_date: Record<string, CatalystEvent[]> }

// ── Small fetch helper ───────────────────────────────────────────────────────
function useFetch<T>(key: unknown[], url: string, enabled = true, refetchInterval: number | false = false) {
  return useQuery<T>({
    queryKey: key,
    queryFn: async () => {
      const r = await fetch(url);
      if (!r.ok) throw new Error(`${r.status}`);
      return r.json();
    },
    enabled,
    staleTime: 60_000,
    refetchInterval,
  });
}

// ── Helpers ──────────────────────────────────────────────────────────────────
const IMPACT_RANK: Record<string, number> = { 'very high': 3, high: 3, medium: 2, med: 2, low: 1 };
function eventTitle(e: CatalystEvent): string {
  return e.title || e.event || `${e.ticker} ${e.catalyst_type ?? 'event'}`;
}
function impactTone(e: CatalystEvent): Tone {
  const r = IMPACT_RANK[(e.impact || e.expected_impact || 'medium').toLowerCase()] ?? 2;
  return r === 3 ? 'bear' : r === 2 ? 'warn' : 'default';
}
function impactLabel(e: CatalystEvent): string {
  const r = IMPACT_RANK[(e.impact || e.expected_impact || 'medium').toLowerCase()] ?? 2;
  return r === 3 ? 'high' : r === 2 ? 'med' : 'low';
}
function rsiZone(v: number): { label: string; tone: Tone } {
  if (v >= 70) return { label: 'overbought', tone: 'bear' };
  if (v <= 30) return { label: 'oversold', tone: 'bull' };
  return { label: 'neutral', tone: 'warn' };
}

// Build the brief bullet list from real brief fields (never fabricated).
function briefBullets(b: BriefResponse): { text: string; tone: Tone }[] {
  const di = b.daily_indicators ?? {};
  const out: { text: string; tone: Tone }[] = [];
  const biasTone: Tone = b.bias === 'bullish' ? 'bull' : b.bias === 'bearish' ? 'bear' : 'brand';
  out.push({
    text: `Daily bias ${(b.bias || 'neutral').toUpperCase()}${
      b.live ? ` · live ${fmtPrice(b.live.price)} (${b.live.session})` : di.date ? ` · ${di.date} close` : ''
    }`,
    tone: biasTone,
  });
  const ftfcDir = b.ftfc_direction ?? di.ftfc_direction;
  const ftfcScore = b.ftfc_score ?? di.ftfc_score;
  if (ftfcDir || ftfcScore != null) {
    out.push({
      text: `FTFC ${ftfcDir ?? '—'} · score ${fmtNum(ftfcScore, 2)}`,
      tone: ftfcDir === 'bullish' ? 'bull' : ftfcDir === 'bearish' ? 'bear' : 'warn',
    });
  }
  const candle = b.strat_candle ?? di.strat_candle;
  const combo = b.strat_combo ?? di.strat_combo;
  if (candle) out.push({ text: `Strat ${candle}${combo ? ` · ${combo}` : ''}`, tone: 'brand' });
  const rsi = b.rsi ?? di.rsi_14;
  if (rsi != null) {
    const z = rsiZone(rsi);
    out.push({ text: `RSI(14) ${fmtNum(rsi, 1)} · ${z.label}`, tone: z.tone });
  }
  if (b.signal_status) out.push({ text: `Signal status — ${b.signal_status}`, tone: 'brand' });
  return out.slice(0, 5);
}

/** Playbook avg_return arrives in PERCENT units (playbook.py _pct). Render as-is. */
export function topSetupAvgReturn(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}
function isoPlusDays(days: number): string {
  return isoPlusDaysFrom(todayISO(), days);
}
// Add `days` to an arbitrary ISO date (used so review-mode catalysts window
// is anchored to the review date, not today).
function isoPlusDaysFrom(baseISO: string, days: number): string {
  const d = new Date(`${baseISO}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

// ── Empty/unavailable state ──────────────────────────────────────────────────
function Unavailable({ msg }: { msg: string }) {
  return (
    <div className="flex items-center gap-2 py-4 text-[12px] text-[var(--on-surface-muted)]">
      <AlertTriangle size={13} className="shrink-0 text-[var(--warn)]" />
      <span>{msg}</span>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
export default function DashboardPage() {
  const { activeTicker } = useTickerStore();
  const navigate = useNavigate();

  // Intraday chart style — candlestick is the default; user-switchable on the
  // card and persisted (density/theme live in the global Settings store).
  const [chartStyle, setChartStyle] = useState<'candle' | 'area'>(
    () => (typeof localStorage !== 'undefined' && localStorage.getItem('overview-chart') === 'area' ? 'area' : 'candle'),
  );
  const pickChart = (s: 'candle' | 'area') => {
    setChartStyle(s);
    try { localStorage.setItem('overview-chart', s); } catch { /* storage unavailable — non-fatal */ }
  };

  const { data: status } = useLiveStatus();
  const { data: quote } = useLiveQuote(activeTicker, true);
  const isOpen = status?.is_open ?? false;

  // Review-date wiring: '/dashboard' is in REVIEW_AWARE_ROUTES, so the header shows a
  // historical date/time picker on this page. When a date is selected, every
  // data fetch below must resolve as-of that date instead of live.
  const { reviewDate, reviewTime } = useReviewDateStore();
  const isReview = reviewDate !== null;
  const reviewCompact = reviewDate?.replace(/-/g, '') ?? '';
  const reviewSuffix = isReview
    ? `&end_date=${reviewDate}${reviewTime ? `&end_time=${reviewTime}` : ''}`
    : '';
  // Cutoff for the intraday chart (bars are UTC-labeled ET seconds — see
  // pricePoints). Defaults to the 16:00 ET close when no review time is set.
  const reviewCutoff = useMemo(() => {
    if (!isReview || !reviewDate) return null;
    const [y, m, d] = reviewDate.split('-').map(Number);
    const [hh, mm] = (reviewTime ?? '16:00').split(':').map(Number);
    return Math.floor(Date.UTC(y, m - 1, d, hh, mm) / 1000);
  }, [isReview, reviewDate, reviewTime]);

  // Hero price: live quote normally; in review mode a synthetic quote rebuilt
  // from the review day's intraday bars up to the selected time (honors the
  // time picker). §3.7: undefined (→ "—") when the day has no intraday bars,
  // never a fabricated price.
  const reviewQuote = useReviewQuote(activeTicker, reviewDate, reviewTime);
  const heroQuote = isReview ? reviewQuote : quote;

  const { data: brief } = useFetch<BriefResponse>(
    ['brief', activeTicker, reviewDate ?? 'live'],
    isReview
      ? `/api/dashboard/brief/${activeTicker}?date=${reviewDate}`
      : `/api/dashboard/brief/${activeTicker}`,
    true,
    isOpen && !isReview ? 15_000 : false,
  );
  const { data: playbook } = useFetch<PlaybookResponse>(
    ['playbook', activeTicker, reviewDate ?? 'live'],
    isReview ? `/api/playbook/${activeTicker}?date=${reviewDate}` : `/api/playbook/${activeTicker}`,
  );
  const { data: signalsResp } = useFetch<SignalsResponse>(
    ['signals', activeTicker, reviewDate ?? 'live', reviewTime ?? 'eod'],
    `/api/signals/${activeTicker}?limit=20${reviewSuffix}`,
  );
  // Catalysts: "upcoming" is relative to the as-of day in review mode, not today.
  const catalystFrom = isReview && reviewDate ? reviewDate : todayISO();
  const catalystTo = isReview && reviewDate ? isoPlusDaysFrom(reviewDate, 7) : isoPlusDays(7);
  const { data: catalysts } = useFetch<CatalystsResponse>(
    ['catalysts-overview', catalystFrom],
    `/api/catalysts/events?date_from=${catalystFrom}&date_to=${catalystTo}`,
  );
  // AI take: in review mode fetch the report as-of the review date.
  const { data: insight } = useInsightReport(activeTicker, reviewDate ?? undefined);

  // Daily reference (prev close + week range) and intraday bars for the chart.
  // In review mode anchor to the selected date; else the brief's latest daily
  // date when available, else today. This makes reference + the hourly month
  // (monthCode) resolve as-of the review date too.
  const anchorDate = isReview
    ? reviewCompact
    : (brief?.daily_indicators?.date ?? todayISO()).replace(/-/g, '');
  const monthCode = anchorDate.slice(0, 6);
  const { data: reference } = useFetch<ReferenceResponse>(
    ['reference', activeTicker, anchorDate],
    `/api/market/reference/${activeTicker}/${anchorDate}`,
  );
  const { data: hourly } = useFetch<MarketDataResponse>(
    ['hourly', activeTicker, monthCode],
    `/api/market/data/${activeTicker}/${monthCode}?timeframe=60`,
    !!brief,
  );

  // 4 daily KPIs (prev close · latest close · 2-day change · RSI).
  const kpiCards = useMemo(() => {
    const prevClose = reference?.close;
    const latestClose = brief?.daily_indicators?.close;
    const rsi = brief?.rsi ?? brief?.daily_indicators?.rsi_14;
    if (prevClose == null || latestClose == null) return null;
    const changeAbs = latestClose - prevClose;
    return { prevClose, latestClose, changeAbs, changePct: (changeAbs / prevClose) * 100, rsi };
  }, [reference, brief]);

  // Intraday close points — AlphaVantage stores ET bars with UTC-labeled unix
  // seconds, so UTC getters give the ET wall-clock. Keep the last 2 RTH+pre
  // sessions (04:00–16:00 ET).
  const pricePoints = useMemo<PricePoint[]>(() => {
    const bars = hourly?.candlestick ?? [];
    if (!bars.length) return [];
    const dayKey = (t: number) => {
      const d = new Date(t * 1000);
      return `${d.getUTCFullYear()}-${d.getUTCMonth() + 1}-${d.getUTCDate()}`;
    };
    const inSession = bars.filter((b) => {
      if (reviewCutoff !== null && b.time > reviewCutoff) return false;  // as-of cutoff
      const h = new Date(b.time * 1000).getUTCHours();
      return h >= 4 && h <= 16;
    });
    const days: string[] = [];
    for (let i = inSession.length - 1; i >= 0 && days.length < 2; i--) {
      const k = dayKey(inSession[i].time);
      if (!days.includes(k)) days.push(k);
    }
    return inSession
      .filter((b) => days.includes(dayKey(b.time)))
      .map((b) => {
        const d = new Date(b.time * 1000);
        const p = (n: number) => String(n).padStart(2, '0');
        return {
          time: b.time,
          price: b.close,
          label: `${p(d.getUTCMonth() + 1)}/${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`,
        };
      });
  }, [hourly, reviewCutoff]);

  const sessionBoundary = useMemo(() => {
    if (pricePoints.length < 2) return null;
    const dayKey = (t: number) => {
      const d = new Date(t * 1000);
      return `${d.getUTCFullYear()}-${d.getUTCMonth() + 1}-${d.getUTCDate()}`;
    };
    const lastKey = dayKey(pricePoints[pricePoints.length - 1].time);
    const boundary = pricePoints.find((p) => dayKey(p.time) === lastKey);
    if (!boundary || boundary.time === pricePoints[0].time) return null;
    const d = new Date(boundary.time * 1000);
    return {
      time: boundary.time,
      label: new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())).toLocaleDateString('en-US', {
        month: 'short', day: 'numeric', timeZone: 'UTC',
      }),
    };
  }, [pricePoints]);

  // Top setup — best card matching the brief bias (mirrors the old dashboard logic).
  const topCard = useMemo(() => {
    const cards = playbook?.cards ?? [];
    if (!cards.length) return null;
    const biasDir = brief?.bias === 'bullish' ? 'CALL' : brief?.bias === 'bearish' ? 'PUT' : null;
    const pool = biasDir ? cards.filter((c) => c.direction === biasDir) : cards;
    return (pool.length ? pool : cards).reduce((best, c) => (c.win_rate > best.win_rate ? c : best));
  }, [playbook, brief?.bias]);

  // Most-recent first.
  const recentSignals = useMemo(
    () => [...(signalsResp?.signals ?? [])].reverse().slice(0, 5),
    [signalsResp],
  );

  // Catalyst feed — flatten upcoming events, soonest first, top 5.
  const catalystFeed = useMemo(() => {
    const byDate = catalysts?.events_by_date ?? {};
    return Object.keys(byDate)
      .sort()
      .flatMap((d) => byDate[d].map((e) => ({ ...e, date: e.date || d })))
      .slice(0, 5);
  }, [catalysts]);

  // News = catalyst events carrying a sentiment label (AlphaVantage NEWS_SENTIMENT).
  const newsFeed = useMemo(
    () => catalystFeed.filter((e) => e.sentiment_label || e.catalyst_type === 'NEWS').slice(0, 4),
    [catalystFeed],
  );

  const rep = insight?.report;
  // Header date: the review date in review mode, else today. Built in UTC from
  // the ISO date so it doesn't drift across the viewer's timezone.
  const labelDate = isReview && reviewDate ? new Date(`${reviewDate}T00:00:00Z`) : new Date();
  const dateLabel = labelDate
    .toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: isReview ? 'UTC' : undefined })
    .toUpperCase();
  // Time shown next to the date — selected review time, else the live ET clock.
  const timeLabel = isReview ? (reviewTime ?? '16:00') : status?.current_time_et;

  // Status pill: explicit "historical" state in review mode so the page is
  // never ambiguous about whether it's showing live or as-of data.
  const marketPill = isReview
    ? { tone: 'brand' as Tone, label: 'HISTORICAL', pulse: false }
    : isOpen
      ? { tone: 'bull' as Tone, label: 'OPEN', pulse: true }
      : status?.session === 'pre-market'
        ? { tone: 'warn' as Tone, label: 'PRE-MARKET', pulse: true }
        : status?.session === 'after-hours'
          ? { tone: 'warn' as Tone, label: 'AFTER HOURS', pulse: true }
          : { tone: 'bear' as Tone, label: 'CLOSED', pulse: false };

  return (
    <div className="flex flex-col gap-[14px]">
      {/* ── Page header ─────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-[22px] font-bold tracking-[-0.02em] text-[var(--on-surface)]">Overview</h1>
          <MicroLabel className="mt-1">
            {activeTicker} · {dateLabel}
            {timeLabel && ` · ${timeLabel} ET`}
          </MicroLabel>
        </div>
        <div className="flex items-center gap-2">
          <TickerSelect />
          <Button
            variant="ghost"
            size="sm"
            onPress={() => window.location.reload()}
            className="inline-flex items-center gap-1.5 rounded-md border border-[var(--outline-variant)] bg-[var(--surface-2)] px-3 py-1.5 text-[12px] font-semibold text-[var(--on-surface)] transition-colors hover:border-[var(--outline)] hover:bg-[var(--surface-3)]"
          >
            <RefreshCw size={13} /> Refresh
          </Button>
        </div>
      </div>

      {/* ── 1. Briefing strip ───────────────────────────────────────────── */}
      <div
        className="rounded-xl p-[var(--card-pad,14px)]"
        style={{
          background: 'linear-gradient(135deg, var(--surface-2), var(--surface-1))',
          border: '1px solid var(--outline-variant)',
        }}
      >
        <div className="grid grid-cols-1 items-stretch gap-4 lg:grid-cols-[1.3fr_1fr]">
          {/* Left: header + hero + bullets */}
          <div className="min-w-0">
            <div className="mb-3 flex flex-wrap items-baseline gap-3">
              <div>
                <MicroLabel>{isReview ? 'As of' : 'Today'} · {dateLabel}</MicroLabel>
                <div className="mt-1 text-[19px] font-bold tracking-[-0.02em]">Pre-market brief</div>
              </div>
              <Pill tone={marketPill.tone} dot pulse={marketPill.pulse}>{marketPill.label}</Pill>
            </div>

            {/* Hero ticker */}
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <span className="text-[15px] font-bold text-[var(--on-surface)]">{activeTicker}</span>
              <Metric value={heroQuote ? fmtPrice(heroQuote.price) : NA} size="display" />
              {heroQuote && <Delta value={heroQuote.change} pct={heroQuote.change_pct} />}
            </div>

            {/* Bullets — derived from real brief fields */}
            <div className="mt-3 flex flex-col gap-2">
              {brief && brief.source !== 'unavailable' ? (
                briefBullets(brief).map((b, i) => (
                  <div key={i} className="flex items-start gap-2.5">
                    <span
                      className="mt-[7px] h-1 w-1 shrink-0 rounded-full"
                      style={{
                        background:
                          b.tone === 'bull' ? 'var(--bull)' : b.tone === 'bear' ? 'var(--bear)' : b.tone === 'warn' ? 'var(--warn)' : 'var(--brand)',
                      }}
                    />
                    <div className="min-w-0 flex-1 text-[13px] leading-[1.45] text-[var(--on-surface-variant)]">{b.text}</div>
                  </div>
                ))
              ) : (
                <Unavailable msg={brief?.reason || 'Pre-market brief unavailable — Cloud SQL not connected or no brief for today.'} />
              )}
            </div>
          </div>

          {/* Right: Top setup */}
          <div
            className="flex min-w-0 flex-col gap-4 self-stretch rounded-xl p-[var(--card-pad,14px)]"
            style={{ background: 'rgba(139,206,255,0.05)', border: '1px solid var(--outline)' }}
          >
            {topCard ? (
              <>
                <div className="flex items-start justify-between">
                  <div>
                    <MicroLabel>Top setup</MicroLabel>
                    <div className="mt-1 text-[16px] font-bold">{topCard.name}</div>
                  </div>
                  <DirTag dir={topCard.direction} />
                </div>
                <div className="flex items-baseline gap-6">
                  <div>
                    <MicroLabel>Win rate</MicroLabel>
                    <div className="mt-1.5 flex items-center gap-2">
                      <ScoreStars value={Math.round(topCard.win_rate / 20)} />
                      <span className="tabular-nums text-[12px] text-[var(--on-surface-muted)]">{fmtNum(topCard.win_rate, 0)}%</span>
                    </div>
                  </div>
                  <div>
                    <MicroLabel>Avg return</MicroLabel>
                    <Metric value={topSetupAvgReturn(topCard.avg_return)} tone={(topCard.avg_return ?? 0) >= 0 ? 'bull' : 'bear'} />
                  </div>
                </div>
                <div className="flex flex-1 flex-col gap-1.5">
                  <MicroLabel>Conditions</MicroLabel>
                  <div className="flex flex-1 flex-col justify-around gap-2.5">
                    {topCard.conditions.slice(0, 5).map((c, i) => (
                      <div key={i} className="flex items-center gap-2.5 text-[13px]">
                        <Check size={14} className="shrink-0 text-[var(--on-surface-muted)]" />
                        <span className="text-[var(--on-surface-variant)]">{c}</span>
                      </div>
                    ))}
                  </div>
                </div>
                {/* Trade levels + win rate by hold window. Price falls back to
                    the brief's latest close so levels render when market is closed. */}
                <SetupCardDetails
                  card={topCard}
                  price={heroQuote?.price ?? brief?.live?.price ?? brief?.daily_indicators?.close ?? null}
                />
              </>
            ) : (
              <div>
                <MicroLabel>Top setup</MicroLabel>
                <Unavailable msg="No playbook setups yet — run the pipeline to populate." />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Daily KPIs ──────────────────────────────────────────────────── */}
      {kpiCards && (
        <div className="grid grid-cols-2 gap-[14px] lg:grid-cols-4">
          <KpiTile label="Prev close" value={fmtPrice(kpiCards.prevClose)} />
          <KpiTile label="Latest close" value={fmtPrice(kpiCards.latestClose)} />
          <KpiTile
            label="2-day change"
            value={fmtPct(kpiCards.changePct)}
            tone={kpiCards.changePct >= 0 ? 'bull' : 'bear'}
            sub={`${kpiCards.changeAbs >= 0 ? '+' : '-'}${fmtPrice(Math.abs(kpiCards.changeAbs))}/sh`}
          />
          <KpiTile
            label="RSI (14)"
            value={fmtNum(kpiCards.rsi, 1)}
            tone={kpiCards.rsi == null ? 'default' : kpiCards.rsi > 70 ? 'bear' : kpiCards.rsi < 30 ? 'bull' : 'warn'}
            sub={kpiCards.rsi == null ? undefined : rsiZone(kpiCards.rsi).label}
          />
        </div>
      )}

      {/* ── Movement Read (PHASE 3, feature-flagged) ───────────────────────
          Self-hiding: when MOVEMENT_STATEMENT_ENABLED is OFF the endpoint
          404s, the hook reports `absent`, and the card renders null. No
          user-visible change until the flag is flipped on. The card only
          consults 5m/15m cells (IWM/SPY/QQQ); the dashboard's tickers are
          exactly those, so the active ticker is always valid here.

          Live-only: the Movement Read is a "current read" — its hook calls the
          live /api/movement-statement (ticker/timeframe only, no as_of). In
          REVIEW/historical mode (reviewDate set) every surrounding card is
          keyed to the selected as-of date, so rendering this live card would
          show TODAY's continuation/levels next to historical data
          (point-in-time contamination). Hiding it in review mode is the
          correct, leak-proof behaviour. */}
      {!isReview && <MovementRead ticker={activeTicker} timeframe="15m" />}

      {/* ── Intraday price (candlestick default · area toggle) ──────────────── */}
      {(hourly?.candlestick?.length ?? 0) > 0 && (
        <Card>
          <div className="mb-2.5 flex items-center justify-between gap-3">
            <h3 className="text-[13px] font-semibold tracking-[-0.01em] text-[var(--on-surface)]">{activeTicker} · intraday</h3>
            <div className="flex items-center gap-3">
              <span className="hidden text-[11px] text-[var(--on-surface-muted)] sm:inline">60-min bars · last 2 sessions</span>
              <div className="segctrl">
                <button className={chartStyle === 'candle' ? 'active' : ''} onClick={() => pickChart('candle')}>Candles</button>
                <button className={chartStyle === 'area' ? 'active' : ''} onClick={() => pickChart('area')}>Area</button>
              </div>
            </div>
          </div>
          {chartStyle === 'candle' ? (
            <div data-testid="intraday-chart-slot" className="overflow-hidden" style={{ height: 260 }}>
              <CandlestickChart
                candlestick={hourly?.candlestick ?? []}
                volume={(hourly?.volume ?? []).map((v) => ({ ...v, color: 'rgba(139,206,255,0.3)' }))}
                rthOnly={false}
                showVolume={false}
              />
            </div>
          ) : (
            <PriceAreaChart
              data={pricePoints}
              seriesLabel={`${activeTicker} close`}
              sessionBoundary={sessionBoundary}
              height={260}
            />
          )}
        </Card>
      )}

      {/* ── 2. Live signals · Today's catalysts ─────────────────────────── */}
      <div className="grid grid-cols-1 gap-[14px] lg:grid-cols-[1.4fr_1fr]">
        {/* Live signals */}
        <Card interactive onClick={() => navigate('/signals')} className="min-w-0">
          <CardHeader
            title={<><Bell size={13} className="mr-1.5 inline align-middle" />Live signals</>}
            meta={`${activeTicker} · ${signalsResp?.count != null ? signalsResp.count.toLocaleString() : '—'}`}
          />
          {recentSignals.length === 0 ? (
            <Unavailable msg="No signals yet for this ticker." />
          ) : (
            <div className="overflow-x-auto">
            <table className="w-full min-w-[320px] text-[12px]">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-[var(--on-surface-label)]">
                  <th className="pb-1 font-semibold">Time</th>
                  <th className="pb-1 font-semibold">Dir</th>
                  <th className="pb-1 text-right font-semibold">Score</th>
                  <th className="pb-1 text-right font-semibold">Return</th>
                </tr>
              </thead>
              <tbody>
                {recentSignals.map((s, i) => (
                  <tr key={i} className="border-t border-[var(--outline-variant)]">
                    <td className="py-1.5 tabular-nums text-[var(--on-surface-muted)]">{s.time?.slice(5, 16)}</td>
                    <td className="py-1.5"><DirTag dir={s.direction} /></td>
                    <td className="py-1.5 text-right tabular-nums text-[var(--on-surface-variant)]">{s.conditions_met ?? `${s.score}/5`}</td>
                    <td className={`py-1.5 text-right tabular-nums font-semibold ${s.return_pct >= 0 ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}`}>
                      {fmtPct(s.return_pct * 100)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
        </Card>

        {/* Today's catalysts */}
        <Card interactive onClick={() => navigate('/catalysts')} className="min-w-0">
          <CardHeader
            title={<><Calendar size={13} className="mr-1.5 inline align-middle" />Catalysts</>}
            meta={`${catalystFeed.length} upcoming`}
          />
          {catalystFeed.length === 0 ? (
            <Unavailable msg="No catalysts in the next 7 days." />
          ) : (
            <div className="flex flex-col">
              {catalystFeed.map((c, i) => (
                <div key={i} className="flex items-center gap-3 border-t border-[var(--outline-variant)] py-2 first:border-t-0">
                  <div className="w-[52px] shrink-0 tabular-nums text-[11px] text-[var(--on-surface-muted)]">{c.date?.slice(5)}</div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[12.5px] font-semibold text-[var(--on-surface)]">{eventTitle(c)}</div>
                    <div className="text-[11px] text-[var(--on-surface-muted)]">{c.ticker}{c.catalyst_type ? ` · ${c.catalyst_type}` : ''}</div>
                  </div>
                  <Pill tone={impactTone(c)}>{impactLabel(c)}</Pill>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* ── 3. Sector rotation · AI take · News ──────────────────────────── */}
      <div className="grid grid-cols-1 gap-[14px] md:grid-cols-2 lg:grid-cols-3">
        {/* Sector rotation — no data source yet (see REDESIGN.md §1) */}
        <Card className="min-w-0">
          <CardHeader title={<><Grid3x3 size={13} className="mr-1.5 inline align-middle" />Sector rotation</>} meta="SPDRs · 1D" />
          <Unavailable msg="Sector rotation unavailable — needs AV SECTOR_PERFORMANCE (not yet fetched)." />
        </Card>

        {/* AI take */}
        <Card interactive onClick={() => navigate('/insights')} className="min-w-0">
          <CardHeader
            title={<><Sparkles size={13} className="mr-1.5 inline align-middle" />AI take</>}
            meta={rep ? `conf ${fmtNum(rep.confidence_score * 100, 0)}%` : undefined}
          />
          {rep ? (
            <div>
              <div className="mb-1.5 flex items-baseline gap-2">
                <DirTag dir={rep.direction === 'long' ? 'bull' : rep.direction === 'short' ? 'bear' : 'neut'} />
                <span className="text-[11px] capitalize text-[var(--on-surface-muted)]">{rep.conviction} conviction · {rep.time_horizon}</span>
              </div>
              <div className="line-clamp-4 text-[12px] leading-[1.5] text-[var(--on-surface-variant)]">{rep.thesis}</div>
            </div>
          ) : (
            <Unavailable msg={`No insight report for ${activeTicker} — generate one on the AI Insights page.`} />
          )}
        </Card>

        {/* News feed (from catalysts carrying sentiment) */}
        <Card interactive onClick={() => navigate('/catalysts')} className="min-w-0">
          <CardHeader title={<><Newspaper size={13} className="mr-1.5 inline align-middle" />News</>} meta={`${newsFeed.length} fresh`} />
          {newsFeed.length === 0 ? (
            <Unavailable msg="No tagged news right now." />
          ) : (
            <div className="flex flex-col">
              {newsFeed.map((n, i) => {
                const tone: Tone =
                  (n.sentiment_score ?? 0) > 0.15 ? 'bull' : (n.sentiment_score ?? 0) < -0.15 ? 'bear' : 'default';
                return (
                  <div key={i} className="flex items-start gap-2 border-t border-[var(--outline-variant)] py-2 first:border-t-0">
                    <div className="min-w-0 flex-1">
                      <div className="line-clamp-2 text-[12px] font-medium text-[var(--on-surface)]">{eventTitle(n)}</div>
                      <div className="text-[11px] text-[var(--on-surface-muted)]">{n.ticker}{n.date ? ` · ${n.date.slice(5)}` : ''}</div>
                    </div>
                    {n.sentiment_label && <Pill tone={tone}>{n.sentiment_label}</Pill>}
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
