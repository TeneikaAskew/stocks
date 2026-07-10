import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { useTickerStore } from '@/stores/tickerStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useReviewDateStore } from '@/stores/reviewDateStore';
import { useMarketData, useAvailableDates, useReferenceLevels } from '@/hooks/useMarketData';
import { useTradeAnalytics } from '@/hooks/useTradeAnalytics';
import { useGammaLevels } from '@/hooks/useGammaLevels';
import {
  useJournalChartTrades,
  useCreateChartTrade,
  useCloseChartTrade,
  useDeleteChartTrade,
  useSeedTrades,
  useReplayTrades,
  useMineMyStyle,
  isoNaiveToEpoch,
  isSeedTradesUnavailable,
  isMineStyleUnavailable,
  seedBenchmark,
  formatEdgeBps,
  styleConditionLabel,
  type SeedTradeRow,
  type ReplayTradeCard,
  type ReplayAggregate,
  type MineStyleSuccess,
} from '@/hooks/useJournalChartTrades';
import { CandlestickChart } from '@/components/charts/CandlestickChart';
import { MetricCard } from '@/components/shared/MetricCard';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { Modal } from '@/components/shared/Modal';
import BacktesterSection from '@/components/backtest/BacktesterSection';
import { StrategyConditionsCard } from '@/components/charts/StrategyConditionsCard';
import { SimilarSetupsCard } from '@/components/charts/SimilarSetupsCard';
import { ReplaySessionControls } from '@/components/charts/ReplaySessionControls';
import { useReplaySession } from '@/hooks/useReplaySession';
import { useLiveIndicators, useSignalSeries } from '@/hooks/useLiveIndicators';
import { EMPTY_INDICATORS, EMPTY_SIGNALS, type Bar } from '@/lib/indicators';
import type { Timeframe, TradeEntry, TradeDirection } from '@/types';
import type { CandlestickBar, VolumeBar } from '@/hooks/useMarketData';
import type { SeriesMarker, Time, LineWidth } from 'lightweight-charts';
import {
  Eye,
  EyeOff,
  Clock,
  Crosshair,
  ArrowUpCircle,
  ArrowDownCircle,
  X,
  Ruler,
  Activity,
  LogOut,
  Download,
  Trash2,
  Zap,
  BookOpen,
  ClipboardCheck,
  AlertTriangle,
} from 'lucide-react';

// Tickers for which we have an options chain in Cloud SQL (matches
// VALID_TICKERS in platform/api/routers/options.py). The Gamma toggle
// is hidden for any other ticker because the /levels endpoint will 400.
const GAMMA_LEVELS_TICKERS = new Set(['SPY', 'IWM', 'QQQ', 'SPX']);

// Muted/distinct color for the admin seed-trade teaching layer (Task 2.4) —
// deliberately gray, never the bull/bear green/red the user's own trades use,
// so the two layers are visually unmistakable at a glance.
const SEED_MARKER_COLOR = '#8a8f98';

const TIMEFRAMES: { value: Timeframe; label: string }[] = [
  { value: '1', label: '1m' },
  { value: '5', label: '5m' },
  { value: '15', label: '15m' },
  { value: '30', label: '30m' },
  { value: '60', label: '1h' },
];

type DrawingStep = 'idle' | 'entry' | 'option-type' | 'tp1' | 'tp2' | 'tp3' | 'sl' | 'exit';

interface TempTradeData {
  entryTime: number;
  entryPrice: number;
  optionType?: TradeDirection;
  takeProfits: { price: number; size: number }[];
  stopLoss?: { price: number };
}

interface PriceLineConfig {
  price: number;
  color: string;
  title: string;
  lineStyle?: number;
  lineWidth?: LineWidth;
}

export default function ChartsPage() {
  const { activeTicker } = useTickerStore();
  const { timeframe, setTimeframe } = useSettingsStore();
  const { reviewDate, reviewTime } = useReviewDateStore();
  const isReview = reviewDate !== null;

  const [localSelectedDate, setLocalSelectedDate] = useState('');
  const [showVolume, setShowVolume] = useState(true);
  const [rthOnly, setRthOnly] = useState(true);
  const [showRefLevels, setShowRefLevels] = useState(false);
  const [showGamma, setShowGamma] = useState(false);
  const [showSignals, setShowSignals] = useState(false);
  const [showSeedTrades, setShowSeedTrades] = useState(true);
  const [activeTab, setActiveTab] = useState<'trades' | 'analytics'>('trades');
  // Task 5.3: Analytics tab's "Include practice sessions" toggle — default
  // excludes source==='replay' trades from what's fed to useTradeAnalytics,
  // same semantics as JournalPage's toggle of the same name/testid (one
  // shared toggle STATE per page, not shared across pages).
  const [includeReplayAnalytics, setIncludeReplayAnalytics] = useState(false);
  // Task 5.3: end-of-session note when stop() found no closed trades to
  // score (so no scorecard POST/modal fires) — cleared on the next session.
  const [sessionEndNote, setSessionEndNote] = useState<string | null>(null);

  // Drawing mode state
  const [drawingStep, setDrawingStep] = useState<DrawingStep>('idle');
  const [tempTrade, setTempTrade] = useState<TempTradeData | null>(null);
  const [exitingTradeId, setExitingTradeId] = useState<string | null>(null);

  // Crosshair info
  const [crosshairData, setCrosshairData] = useState<{
    time: number;
    price: number;
    ohlc?: CandlestickBar;
  } | null>(null);

  // Fetch dates
  const { data: datesData } = useAvailableDates(activeTicker);
  const dates = datesData?.dates ?? [];

  // Date format helpers: YYYYMMDD <-> YYYY-MM-DD
  const toInputFormat = (d: string) =>
    d ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}` : '';
  const toApiFormat = (d: string) => d.replace(/-/g, '');
  const minDate = dates.length > 0 ? toInputFormat(dates[dates.length - 1]) : '';
  const maxDate = dates.length > 0 ? toInputFormat(dates[0]) : '';

  // Auto-select first date (for local state) — render-time adjustment
  // (React docs pattern, mirroring ReplayControl's `lastCommitted` idiom):
  // adopt the newest date once per dates-list identity, without an effect.
  const [seenDates, setSeenDates] = useState<string[] | null>(null);
  if (dates.length > 0 && seenDates !== dates) {
    setSeenDates(dates);
    if (!localSelectedDate) setLocalSelectedDate(dates[0]);
  }

  // Effective date: override with reviewDate when in review mode, snapping to nearest earlier trading day
  const { selectedDate, snappedFromReview } = useMemo(() => {
    if (!isReview || !reviewDate || dates.length === 0) {
      return { selectedDate: localSelectedDate, snappedFromReview: false };
    }
    const target = toApiFormat(reviewDate);
    // dates is sorted DESC; find the first date <= target
    const exact = dates.includes(target);
    if (exact) return { selectedDate: target, snappedFromReview: false };
    // Snap to nearest earlier trading day
    const snapped = dates.find(d => d <= target);
    return {
      selectedDate: snapped ?? dates[dates.length - 1],
      snappedFromReview: snapped !== undefined && snapped !== target,
    };
  }, [isReview, reviewDate, dates, localSelectedDate]);

  // Fetch data — pass end_time only in review mode
  const { data: marketData, isLoading, error } = useMarketData(
    activeTicker,
    selectedDate,
    timeframe,
    isReview ? reviewTime : null
  );

  // Bar-replay trainer session (Task 5.2) — reveals `marketData.candlestick`
  // bar-by-bar. `revealedBars` is the ONLY slice of the day anything
  // downstream (chart, indicators, signal overlay) sees while active; that's
  // the whole leakage-free contract.
  const replay = useReplaySession<CandlestickBar>(marketData?.candlestick ?? []);

  // Volume slice for the replay reveal, bound to the SAME candle count as
  // replay.revealedBars (never a separately-tracked volume cursor). Handoff
  // from Task 5.1's review: if the natural slice comes back shorter than the
  // candle count, the two arrays /api/market/data returned aren't in
  // lockstep — a structural anomaly, not a financial one, so it's a
  // console.warn (observability) rather than a silent `?? 0` fill.
  const revealedVolume: VolumeBar[] = useMemo(() => {
    if (!marketData) return [];
    if (!replay.active) return marketData.volume;
    const candleCount = replay.revealedBars.length;
    const sliced = marketData.volume.slice(0, candleCount);
    if (sliced.length !== candleCount) {
      console.warn(
        'replay: revealed volume length (%d) does not match revealed candle count (%d); slicing volume by candle count',
        sliced.length,
        candleCount,
      );
    }
    return sliced;
  }, [marketData, replay.active, replay.revealedBars]);

  // Reference levels (prev day OHLC)
  const { data: refLevels } = useReferenceLevels(activeTicker, selectedDate);

  // selectedDate is YYYYMMDD; several endpoints (gamma, journal) want YYYY-MM-DD.
  const selectedIsoDate = selectedDate
    ? `${selectedDate.slice(0, 4)}-${selectedDate.slice(4, 6)}-${selectedDate.slice(6, 8)}`
    : '';

  // Gamma levels — King/Gate/Spot/Flip from lib.gamma. Only fetched for
  // tickers we have options chains for, and only when the user toggles
  // the overlay on.
  const gammaLevelsEnabled =
    showGamma && GAMMA_LEVELS_TICKERS.has(activeTicker.toUpperCase()) && !!selectedDate;
  const { data: gammaLevels } = useGammaLevels(activeTicker, selectedIsoDate, {
    enabled: gammaLevelsEnabled,
  });

  // Chart-marked trades persist through the journal API (POST/PATCH/DELETE
  // /api/journal/trades) instead of an in-memory zustand store — the hook
  // already filters to this ticker + selectedIsoDate.
  const { data: trades = [] } = useJournalChartTrades(activeTicker, selectedIsoDate);
  const createChartTrade = useCreateChartTrade();
  const closeChartTrade = useCloseChartTrade();
  const deleteChartTrade = useDeleteChartTrade();

  // "Backtest my trades" scorecard (Task 3.3) — scores the current view's
  // CLOSED trades against the production benchmark (POST
  // /api/backtest/replay-trades). A useMutation (triggered on click), not a
  // useQuery — the modal's isPending/isError/data states drive the UI.
  const [scorecardOpen, setScorecardOpen] = useState(false);
  const replayTrades = useReplayTrades();

  // Task 5.3: post-replay-session scorecard. Fires exactly once per finished
  // bar-replay-trainer session (guarded by scoredSessionIdRef so a re-render
  // — e.g. `trades` refetching — never double-fires) once useReplaySession's
  // stop() lands a summary: if the session tagged >=1 CLOSED trade
  // (status !== 'active', matching Task 3.3's closedTradeIds definition),
  // POST /api/backtest/replay-trades with {ticker, session_id} and reuse
  // the EXACT Task 3.3 scorecard modal (scorecardOpen + replayTrades) — no
  // duplicate UI. Zero closed trades -> no POST, just an end-of-session note.
  const scoredSessionIdRef = useRef<string | null>(null);
  useEffect(() => {
    const summary = replay.summary;
    if (!summary || scoredSessionIdRef.current === summary.sessionId) return;
    scoredSessionIdRef.current = summary.sessionId;
    const sessionClosedCount = trades.filter(
      (t) => t.sessionId === summary.sessionId && t.status !== 'active',
    ).length;
    if (sessionClosedCount === 0) {
      setSessionEndNote('Session ended — no closed trades to score');
      return;
    }
    setSessionEndNote(null);
    setScorecardOpen(true);
    replayTrades.mutate({ ticker: activeTicker, sessionId: summary.sessionId });
  }, [replay.summary, trades, activeTicker, replayTrades]);

  // Clear a stale end-of-session note the instant a NEW session starts, so
  // it doesn't linger on screen through an unrelated live replay.
  useEffect(() => {
    if (replay.active) setSessionEndNote(null);
  }, [replay.active]);

  // "My style" panel (Task 4.4) — mines the caller's own closed journal
  // trades into a condition profile and walk-forward validates it (POST
  // /api/style/mine-and-validate). A useMutation triggered from the
  // Analytics tab's "Mine my style" button, mirroring replayTrades above.
  const mineMyStyle = useMineMyStyle();

  // Admin seed-trade teaching layer (Task 2.4) — read-only pull from the
  // automated pipeline `trades` table, GET /api/journal/seed/{ticker}.
  // Kept fetching regardless of the toggle (cheap single-row/single-ticker
  // query) so flipping `showSeedTrades` back on doesn't re-trigger a fetch.
  const seedTradesQuery = useSeedTrades(activeTicker, selectedIsoDate);
  const seedUnavailable =
    seedTradesQuery.isError ||
    (seedTradesQuery.data !== undefined && isSeedTradesUnavailable(seedTradesQuery.data));
  const seedTradesData = seedTradesQuery.data;
  const seedRows: SeedTradeRow[] = useMemo(
    () => (seedTradesData && !isSeedTradesUnavailable(seedTradesData) ? seedTradesData.trades : []),
    [seedTradesData],
  );
  const seedBench = useMemo(() => seedBenchmark(seedRows), [seedRows]);

  // Trades for current date/ticker — filter out trades after reviewTs in review mode
  const reviewCutoffTs = useMemo(() => {
    if (!isReview || !reviewDate) return null;
    const [y, m, d] = reviewDate.split('-').map(Number);
    const [hh, mm] = (reviewTime ?? '23:59').split(':').map(Number);
    return Math.floor(Date.UTC(y, m - 1, d, hh, mm) / 1000);
  }, [isReview, reviewDate, reviewTime]);

  // Replay leakage guard: while a session is active, any of the user's OWN
  // historical trades timed AFTER the last revealed bar are information
  // leakage about where price goes next — hide them the same way review
  // mode hides post-cutoff trades. The last revealed bar's time IS the
  // cutoff (also what Mark Entry pins new replay trades' entry epoch to,
  // below), so a trade created during the current session always survives
  // this filter (entryTime === replayCutoffTs, not >).
  const replayCutoffTs = useMemo(() => {
    if (!replay.active || replay.revealedBars.length === 0) return null;
    return replay.revealedBars[replay.revealedBars.length - 1].time;
  }, [replay.active, replay.revealedBars]);

  const currentTrades = useMemo(() => {
    let list = trades;
    if (reviewCutoffTs !== null) {
      list = list.filter(t => (t.exitTime ?? t.entryTime) <= reviewCutoffTs);
    }
    if (replayCutoffTs !== null) {
      list = list.filter(t => (t.exitTime ?? t.entryTime) <= replayCutoffTs);
    }
    return list;
  }, [trades, reviewCutoffTs, replayCutoffTs]);

  const hiddenTradesCount = useMemo(() => {
    let cutoff: number | null = reviewCutoffTs;
    if (replayCutoffTs !== null) {
      cutoff = cutoff !== null ? Math.min(cutoff, replayCutoffTs) : replayCutoffTs;
    }
    if (cutoff === null) return 0;
    return trades.filter(t => (t.exitTime ?? t.entryTime) > cutoff).length;
  }, [trades, reviewCutoffTs, replayCutoffTs]);

  // Task 5.3: practice (bar-replay-trainer) trades are excluded from the
  // Analytics tab's stats by default — same "Include practice sessions"
  // semantics as JournalPage's toggle. Only the analytics input is scoped;
  // the Trades tab / chart markers / TP-SL lines still show every trade
  // regardless of this toggle (a session's trades stay visible/manageable).
  const analyticsTrades = useMemo(
    () => (includeReplayAnalytics ? currentTrades : currentTrades.filter((t) => t.source !== 'replay')),
    [currentTrades, includeReplayAnalytics],
  );
  const { stats, isError: statsUnavailable } = useTradeAnalytics(analyticsTrades);

  // My-style result renders at the bottom of the side panel — scroll it into
  // view once mining succeeds so the user doesn't have to know to scroll.
  const myStyleResultRef = useRef<HTMLDivElement>(null);

  // Task 3.3: "closed" = any non-active status (win/loss/breakeven) — the
  // replay endpoint requires exit_ts/exit_price to score a trade, which an
  // active TradeEntry never has.
  const closedTradeIds = useMemo(
    () => currentTrades.filter((t) => t.status !== 'active').map((t) => t.id),
    [currentTrades],
  );
  const closedTradeDirections = useMemo(
    () => new Map(currentTrades.map((t) => [t.id, t.optionType] as const)),
    [currentTrades],
  );

  // Strategy condition evaluation: build a Bar[] from the candlestick + volume
  // arrays the API returns. Indicators + signals are computed server-side
  // (lib/indicators.py, lib/signals.py) — the app never duplicates this math.
  // Need ≥14 bars before RSI is meaningful, so dependent UI hides itself
  // below that threshold.
  //
  // Replay leakage guard: while a session is active this is built from
  // ONLY replay.revealedBars (+ its lockstep revealedVolume), never the
  // full day's marketData.candlestick — the Strategy Conditions panel and
  // the Sig overlay/Similar Setups lookup below all derive from chartBars,
  // so pinning the source here is what keeps them leakage-free without
  // needing separate replay-aware branches at every call site.
  const effectiveCandlestick: CandlestickBar[] = replay.active
    ? replay.revealedBars
    : marketData?.candlestick ?? [];
  const effectiveVolume: VolumeBar[] = replay.active ? revealedVolume : marketData?.volume ?? [];
  const chartBars: Bar[] = useMemo(() => {
    if (effectiveCandlestick.length === 0) return [];
    return effectiveCandlestick.map((c, i) => ({
      time: String(c.time),
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      // Pre-existing `?? 0` on a financial field (volume), carried over
      // unchanged from before this task — not introduced or extended here,
      // just re-sourced from effectiveVolume for replay leakage-safety.
      // Flagged for remediation per CLAUDE.md Rule 3.7.
      volume: effectiveVolume[i]?.value ?? 0,
    }));
  }, [effectiveCandlestick, effectiveVolume]);

  // Live Strategy Conditions panel — mirrors LiveMarketPage.tsx's
  // useLiveIndicators usage exactly so the same 10-condition strength
  // readout (POST /api/live/indicators, lib/indicators.py) drives every
  // page in the app.
  const lastChartBar = chartBars.length > 0 ? chartBars[chartBars.length - 1] : null;
  const indicatorsQuery = useLiveIndicators(
    {
      bars: chartBars,
      current_price: lastChartBar?.close ?? null,
      current_volume: lastChartBar?.volume ?? null,
      avg_volume_20d: null,
    },
    chartBars.length >= 14,
  );
  const chartIndicators = indicatorsQuery.data?.indicators ?? EMPTY_INDICATORS;
  const chartSignals = indicatorsQuery.data?.signals ?? EMPTY_SIGNALS;

  // Build chart markers from trades
  const tradeMarkers: SeriesMarker<Time>[] = useMemo(() => {
    return currentTrades.flatMap((trade) => {
      const m: SeriesMarker<Time>[] = [];
      m.push({
        time: trade.entryTime as Time,
        position: trade.optionType === 'CALL' ? 'belowBar' : 'aboveBar',
        color: trade.optionType === 'CALL' ? '#089981' : '#f23645',
        shape: trade.optionType === 'CALL' ? 'arrowUp' : 'arrowDown',
        text: `${trade.optionType} @ $${trade.entryPrice.toFixed(2)}`,
      });
      if (trade.exitTime) {
        const pnl = trade.pnl ?? 0;
        m.push({
          time: trade.exitTime as Time,
          position: pnl >= 0 ? 'aboveBar' : 'belowBar',
          color: pnl >= 0 ? '#089981' : '#f23645',
          shape: 'circle',
          text: `Exit ${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`,
        });
      }
      return m;
    });
  }, [currentTrades]);

  // Strategy signal overlay — green up triangles for CALL fires, red down
  // for PUT fires. Computed server-side via POST /api/live/signal-series,
  // which runs the SAME production mean-reversion voter
  // (lib/signals.py:evaluate_signal) gcp/signal_monitor.py fires live
  // alerts from — no client-side re-derivation. Fetched independently of
  // the Sig toggle (below) so SimilarSetupsCard's "latest bar fired?"
  // read stays correct even while the overlay is hidden; the toggle only
  // gates whether markers are drawn on the chart.
  //
  // Replay leakage guard: `!replay.active` gates BOTH the fetch (chartBars
  // is already only revealed bars during replay, so this isn't strictly a
  // leakage vector, but the brief's hard constraint is "not fetched with
  // future bars" — the safest reading is "not fetched at all" during a
  // session) and, independently, signalMarkers below forces `[]` regardless
  // of any stale cached data from before the session started.
  const signalSeriesQuery = useSignalSeries(
    chartBars,
    `${activeTicker}:${selectedDate}`,
    chartBars.length >= 14 && !replay.active,
  );
  const signalMarkers: SeriesMarker<Time>[] = useMemo(() => {
    if (!showSignals || replay.active) return [];
    const fires = signalSeriesQuery.data?.fires ?? [];
    return fires.map((f) => ({
      time: Number(f.time) as Time,
      position: f.direction === 'CALL' ? 'belowBar' : 'aboveBar',
      color: f.direction === 'CALL' ? '#22c55e' : '#ef4444',
      shape: f.direction === 'CALL' ? 'arrowUp' : 'arrowDown',
      text: `${f.direction} ${f.score}`,
    }));
  }, [showSignals, replay.active, signalSeriesQuery.data]);

  // Seed-trade markers (Task 2.4) — muted/dashed-feel styling, distinct from
  // both the signal overlay and the user's own trades. Entry_time/exit_time
  // strings use the same naive-ET wall-clock convention as journal_entries
  // (see isoNaiveToEpoch's doc comment), so the same mapper applies as-is.
  const seedMarkers: SeriesMarker<Time>[] = useMemo(() => {
    // Replay leakage guard: seed rows carry full-day entry/exit/return data
    // from the automated pipeline — a seed exit at 15:45 would leak future
    // price action while the reveal is still at, say, 10:00. Full gate
    // (matching the Sig overlay pattern above): [] whenever `replay.active`,
    // regardless of showSeedTrades.
    if (!showSeedTrades || replay.active) return [];
    return seedRows.flatMap((row) => {
      const m: SeriesMarker<Time>[] = [];
      if (row.entry_time && row.entry_price != null) {
        const entryEpoch = isoNaiveToEpoch(row.entry_time);
        if (!Number.isNaN(entryEpoch)) {
          m.push({
            time: entryEpoch as Time,
            position: row.direction === 'CALL' ? 'belowBar' : 'aboveBar',
            color: SEED_MARKER_COLOR,
            shape: row.direction === 'CALL' ? 'arrowUp' : 'arrowDown',
            text: `SEED ${row.direction} @ $${row.entry_price.toFixed(2)}`,
          });
        }
      }
      if (row.exit_time && row.exit_price != null) {
        const exitEpoch = isoNaiveToEpoch(row.exit_time);
        if (!Number.isNaN(exitEpoch)) {
          m.push({
            time: exitEpoch as Time,
            position: 'aboveBar',
            color: SEED_MARKER_COLOR,
            shape: 'circle',
            text: `SEED exit @ $${row.exit_price.toFixed(2)}`,
          });
        }
      }
      return m;
    });
  }, [showSeedTrades, seedRows, replay.active]);

  // Trade markers on top of seed/signal markers so the user's own trades
  // win the visual priority (and re-render last in the chart's marker
  // plugin). Seed markers sit above the signal overlay but below the
  // user's trades.
  const markers: SeriesMarker<Time>[] = useMemo(
    () => [...signalMarkers, ...seedMarkers, ...tradeMarkers],
    [signalMarkers, seedMarkers, tradeMarkers],
  );

  // Build price lines from trades (TP/SL) + reference levels
  const priceLines: PriceLineConfig[] = useMemo(() => {
    const lines: PriceLineConfig[] = [];

    // Trade TP/SL lines
    for (const trade of currentTrades) {
      if (trade.status !== 'active') continue;
      trade.takeProfits.forEach((tp, i) => {
        lines.push({
          price: tp.price,
          color: '#089981',
          title: `TP${i + 1}`,
          lineStyle: 2, // Dotted
        });
      });
      if (trade.stopLoss) {
        lines.push({
          price: trade.stopLoss.price,
          color: '#f23645',
          title: 'SL',
          lineStyle: 2,
        });
      }
    }

    // Reference levels
    if (showRefLevels && refLevels) {
      lines.push(
        { price: refLevels.high, color: '#fbbf24', title: `Prev High`, lineStyle: 3, lineWidth: 2 as LineWidth },
        { price: refLevels.low, color: '#f59e0b', title: `Prev Low`, lineStyle: 3, lineWidth: 2 as LineWidth },
        { price: refLevels.open, color: '#6366f1', title: `Prev Open`, lineStyle: 3 },
        { price: refLevels.close, color: '#8b5cf6', title: `Prev Close`, lineStyle: 3 },
      );
    }

    // Gamma levels — King (gold solid), Gate (blue dashed), Flip (violet dashed).
    // Lines are clipped to the visible window of strikes so we don't pollute
    // the chart with deep OTM levels. See lib/gamma.py for the taxonomy.
    if (showGamma && gammaLevels) {
      for (const k of gammaLevels.kings) {
        lines.push({
          price: k.strike,
          color: '#f59e0b',
          title: `★ King ${k.strike.toFixed(2)}`,
          lineStyle: 0, // Solid
          lineWidth: 2 as LineWidth,
        });
      }
      for (const g of gammaLevels.gates) {
        lines.push({
          price: g.strike,
          color: '#3b82f6',
          title: `◆ Gate ${g.strike.toFixed(2)}`,
          lineStyle: 2, // Dotted
        });
      }
      if (gammaLevels.gamma_flip !== null) {
        lines.push({
          price: gammaLevels.gamma_flip,
          color: '#a78bfa',
          title: `⇅ Gamma Flip ${gammaLevels.gamma_flip.toFixed(2)}`,
          lineStyle: 1, // Dashed
          lineWidth: 2 as LineWidth,
        });
      }
      if (gammaLevels.gamma_balance !== null) {
        lines.push({
          price: gammaLevels.gamma_balance,
          color: '#c4b5fd',
          title: `≈ Gamma Balance ${gammaLevels.gamma_balance.toFixed(2)}`,
          lineStyle: 2, // Dotted
          lineWidth: 1 as LineWidth,
        });
      }
    }

    return lines;
  }, [currentTrades, showRefLevels, refLevels, showGamma, gammaLevels]);

  // Chart click handler
  const handleChartClick = useCallback(
    (data: { time: number; price: number }) => {
      if (drawingStep === 'entry') {
        // Mid-playback Mark Entry (Task 5.2): the entry EPOCH is pinned to
        // the last REVEALED bar's time, not wherever on the chart the user
        // clicked — clicking anywhere is just how the entry PRICE gets
        // chosen. Outside a replay session this is identical to before
        // (data.time from the click).
        const entryTime =
          replay.active && replay.revealedBars.length > 0
            ? replay.revealedBars[replay.revealedBars.length - 1].time
            : data.time;
        setTempTrade({
          entryTime,
          entryPrice: data.price,
          takeProfits: [],
        });
        setDrawingStep('option-type');
      } else if (drawingStep === 'tp1' || drawingStep === 'tp2' || drawingStep === 'tp3') {
        if (!tempTrade) return;
        const tps = [...tempTrade.takeProfits, { price: data.price, size: 0.33 }];
        setTempTrade({ ...tempTrade, takeProfits: tps });
        if (drawingStep === 'tp1') setDrawingStep('tp2');
        else if (drawingStep === 'tp2') setDrawingStep('tp3');
        else setDrawingStep('sl');
      } else if (drawingStep === 'sl') {
        if (!tempTrade) return;
        completeTrade({ ...tempTrade, stopLoss: { price: data.price } });
      } else if (drawingStep === 'exit' && exitingTradeId) {
        const trade = trades.find((t) => t.id === exitingTradeId);
        if (trade) {
          // Clamp exit time to the last REVEALED bar during replay (mirrors
          // the Mark Entry pin above) — a raw click time has no such clamp
          // and could otherwise persist a future-bar epoch, leaking how far
          // the reveal will eventually go.
          const exitTime =
            replay.active && replay.revealedBars.length > 0
              ? replay.revealedBars[replay.revealedBars.length - 1].time
              : data.time;
          // PATCH persists the exit; return_pct/status come back from the
          // server (journal.py's _return_pct/_derive_status) — no client-side
          // pnl math here, the query invalidation refetches the closed row.
          closeChartTrade.mutate({
            id: exitingTradeId,
            ticker: activeTicker,
            exitTime,
            exitPrice: data.price,
          });
        }
        cancelDrawing();
      }
    },
    [drawingStep, tempTrade, exitingTradeId, trades, closeChartTrade, replay.active, replay.revealedBars]
  );

  const selectOptionType = (type: TradeDirection) => {
    if (!tempTrade) return;
    setTempTrade({ ...tempTrade, optionType: type });
    setDrawingStep('tp1');
  };

  const skipToSL = () => setDrawingStep('sl');
  const skipSL = () => {
    if (tempTrade) completeTrade(tempTrade);
  };

  const completeTrade = (data: TempTradeData) => {
    if (!data.optionType) return;
    createChartTrade.mutate({
      ticker: activeTicker,
      direction: data.optionType,
      entryTime: data.entryTime,
      entryPrice: data.entryPrice,
      stopLoss: data.stopLoss?.price,
      takeProfits: data.takeProfits.map((tp) => tp.price),
      // Trades drawn during a bar-replay trainer session (Task 5.2) are
      // tagged `source: 'replay'` + the session's UUID so Task 5.3's
      // post-session review can group them apart from ordinary chart trades.
      source: replay.active ? 'replay' : 'chart',
      sessionId: replay.active ? (replay.sessionId ?? undefined) : undefined,
    });
    cancelDrawing();
  };

  const startExitMode = (tradeId: string) => {
    setExitingTradeId(tradeId);
    setDrawingStep('exit');
  };

  const cancelDrawing = () => {
    setDrawingStep('idle');
    setTempTrade(null);
    setExitingTradeId(null);
  };

  // Export trades to JSON (compatible with pipeline)
  const exportTradesJSON = () => {
    if (currentTrades.length === 0) return;
    const json = JSON.stringify(currentTrades, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${activeTicker.toLowerCase()}_trades_${selectedDate || 'all'}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Export trades to CSV
  const exportTradesCSV = () => {
    if (currentTrades.length === 0) return;
    const headers = [
      'ID', 'Ticker', 'Option Type', 'Entry Time', 'Entry Price',
      'Exit Time', 'Exit Price', 'P&L', 'P&L %', 'Status',
      'TP1 Price', 'TP2 Price', 'TP3 Price', 'Stop Loss', 'Notes',
    ];
    const formatTs = (ts: number) => {
      const d = new Date(ts * 1000);
      return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')} ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}:00`;
    };
    const rows = currentTrades.map((t) => [
      t.id, t.ticker, t.optionType,
      formatTs(t.entryTime), t.entryPrice.toFixed(2),
      t.exitTime ? formatTs(t.exitTime) : '', t.exitPrice?.toFixed(2) ?? '',
      t.pnl?.toFixed(2) ?? '', t.pnlPercent?.toFixed(2) ?? '', t.status,
      t.takeProfits[0]?.price.toFixed(2) ?? '',
      t.takeProfits[1]?.price.toFixed(2) ?? '',
      t.takeProfits[2]?.price.toFixed(2) ?? '',
      t.stopLoss?.price.toFixed(2) ?? '',
      t.notes,
    ]);
    const csv = [headers.join(','), ...rows.map((r) => r.map((c) => `"${c}"`).join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${activeTicker.toLowerCase()}_trades_${selectedDate || 'all'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Document-level ESC handler (works regardless of focus)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (drawingStep === 'entry' || drawingStep === 'option-type' || drawingStep === 'exit') {
        cancelDrawing();
      } else if (drawingStep === 'tp1' || drawingStep === 'tp2' || drawingStep === 'tp3') {
        skipToSL();
      } else if (drawingStep === 'sl') {
        skipSL();
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [drawingStep, tempTrade]);

  const drawingActive = drawingStep !== 'idle' && drawingStep !== 'option-type';

  return (
    <div className="flex flex-col gap-6">
    <div className="flex gap-4">
      {/* Main chart area */}
      <div className="flex flex-1 flex-col">
        {/* Toolbar */}
        <div className="mb-3 flex flex-wrap items-center gap-3">
          {/* Date picker — disabled when in historical review mode */}
          <input
            type="date"
            value={toInputFormat(selectedDate)}
            min={minDate}
            max={maxDate}
            disabled={isReview}
            onChange={(e) => {
              const picked = toApiFormat(e.target.value);
              if (picked) setLocalSelectedDate(picked);
            }}
            className="rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-1.5 text-sm text-[var(--color-text-primary)] disabled:opacity-50 disabled:cursor-not-allowed"
            title={isReview ? 'Controlled by global historical mode — clear review mode to edit' : undefined}
          />
          {snappedFromReview && (
            <span className="text-xs text-[var(--warn)]" title={`${reviewDate} was not a trading day`}>
              ⓘ Snapped to {toInputFormat(selectedDate)}
            </span>
          )}
          {hiddenTradesCount > 0 && (
            <span className="text-xs text-[var(--warn)]" title="Trades after review cutoff are hidden">
              {hiddenTradesCount} trade{hiddenTradesCount > 1 ? 's' : ''} hidden
            </span>
          )}
          {sessionEndNote && (
            <span data-testid="replay-session-end-note" className="text-xs text-[var(--color-text-muted)]">
              {sessionEndNote}
            </span>
          )}

          {/* Timeframe buttons */}
          <div className="flex rounded border border-[var(--color-border)]">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf.value}
                onClick={() => setTimeframe(tf.value)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  timeframe === tf.value
                    ? 'bg-[var(--color-accent-blue)] text-[var(--on-brand)]'
                    : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]'
                }`}
              >
                {tf.label}
              </button>
            ))}
          </div>

          {/* Toggles */}
          <button
            onClick={() => setShowVolume(!showVolume)}
            className={`flex items-center gap-1 rounded px-2 py-1.5 text-xs ${
              showVolume ? 'bg-[var(--color-bg-hover)] text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'
            }`}
          >
            {showVolume ? <Eye size={14} /> : <EyeOff size={14} />}
            Vol
          </button>

          <button
            onClick={() => setRthOnly(!rthOnly)}
            className={`flex items-center gap-1 rounded px-2 py-1.5 text-xs ${
              rthOnly ? 'bg-[var(--color-bg-hover)] text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'
            }`}
          >
            <Clock size={14} />
            RTH
          </button>

          <button
            onClick={() => setShowRefLevels(!showRefLevels)}
            className={`flex items-center gap-1 rounded px-2 py-1.5 text-xs ${
              showRefLevels ? 'bg-[var(--color-bg-hover)] text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'
            }`}
          >
            <Ruler size={14} />
            Ref
          </button>

          {GAMMA_LEVELS_TICKERS.has(activeTicker.toUpperCase()) && (
            <button
              onClick={() => setShowGamma(!showGamma)}
              title="Show King/Gate/Flip gamma levels for this date"
              className={`flex items-center gap-1 rounded px-2 py-1.5 text-xs ${
                showGamma
                  ? 'bg-[var(--color-bg-hover)] text-[var(--color-text-primary)]'
                  : 'text-[var(--color-text-muted)]'
              }`}
            >
              <Zap size={14} />
              Gamma
            </button>
          )}

          <button
            onClick={() => setShowSignals(!showSignals)}
            disabled={replay.active}
            title={replay.active ? 'unavailable during replay' : 'Production alert signals (lib/signals mean-reversion voter)'}
            className={`flex items-center gap-1 rounded px-2 py-1.5 text-xs ${
              showSignals ? 'bg-[var(--color-bg-hover)] text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'
            } disabled:cursor-not-allowed disabled:opacity-40`}
          >
            <Activity size={14} />
            Sig
          </button>

          <button
            onClick={() => setShowSeedTrades(!showSeedTrades)}
            data-testid="seed-toggle"
            disabled={replay.active}
            title={
              replay.active
                ? 'unavailable during replay'
                : 'Show seed trades — read-only admin trades from the automated pipeline'
            }
            className={`flex items-center gap-1 rounded px-2 py-1.5 text-xs ${
              showSeedTrades ? 'bg-[var(--color-bg-hover)] text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'
            } disabled:cursor-not-allowed disabled:opacity-40`}
          >
            <BookOpen size={14} />
            Seed
          </button>

          {/* Bar-replay trainer session controls (Task 5.2) */}
          <ReplaySessionControls
            active={replay.active}
            playing={replay.playing}
            speed={replay.speed}
            revealedCount={replay.revealedCount}
            total={replay.total}
            onStart={replay.start}
            onPlay={replay.play}
            onPause={replay.pause}
            onStep={replay.step}
            onStop={replay.stop}
            onSpeedChange={replay.setSpeed}
          />

          <div className="flex-1" />

          {/* Export buttons */}
          {currentTrades.length > 0 && drawingStep === 'idle' && (
            <div className="flex gap-1">
              <button
                onClick={exportTradesJSON}
                className="flex items-center gap-1 rounded px-2 py-1.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]"
                title="Export trades as JSON"
              >
                <Download size={14} />
                JSON
              </button>
              <button
                onClick={exportTradesCSV}
                className="flex items-center gap-1 rounded px-2 py-1.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]"
                title="Export trades as CSV"
              >
                <Download size={14} />
                CSV
              </button>
            </div>
          )}

          {/* Drawing mode */}
          {drawingStep === 'idle' ? (
            <button
              onClick={() => setDrawingStep('entry')}
              className="flex items-center gap-1 rounded bg-[var(--color-accent-blue)] px-3 py-1.5 text-xs font-medium text-[var(--on-brand)] hover:bg-blue-600"
            >
              <Crosshair size={14} />
              Mark Entry
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-[var(--color-accent-amber)]">
                {drawingStep === 'entry' && 'Click chart to set entry price'}
                {drawingStep === 'option-type' && 'Select CALL or PUT'}
                {drawingStep === 'tp1' && 'Click TP1 (ESC to skip)'}
                {drawingStep === 'tp2' && 'Click TP2 (ESC to skip)'}
                {drawingStep === 'tp3' && 'Click TP3 (ESC to skip)'}
                {drawingStep === 'sl' && 'Click Stop Loss (ESC to skip)'}
                {drawingStep === 'exit' && 'Click chart to set exit price'}
              </span>
              {drawingStep === 'option-type' && (
                <div className="flex gap-1">
                  <button
                    onClick={() => selectOptionType('CALL')}
                    className="flex items-center gap-1 rounded bg-[var(--bull)] px-2 py-1 text-xs text-black"
                  >
                    <ArrowUpCircle size={12} />
                    CALL
                  </button>
                  <button
                    onClick={() => selectOptionType('PUT')}
                    className="flex items-center gap-1 rounded bg-[var(--bear)] px-2 py-1 text-xs text-white"
                  >
                    <ArrowDownCircle size={12} />
                    PUT
                  </button>
                </div>
              )}
              <button
                onClick={cancelDrawing}
                className="rounded p-1 text-[var(--color-text-muted)] hover:text-[var(--color-accent-red)]"
              >
                <X size={16} />
              </button>
            </div>
          )}
        </div>

        {/* Crosshair info bar */}
        {crosshairData?.ohlc && (
          <div className="mb-1 flex gap-4 text-xs">
            <span className="text-[var(--color-text-muted)]">
              O <span className="text-[var(--color-text-primary)]">{crosshairData.ohlc.open.toFixed(2)}</span>
            </span>
            <span className="text-[var(--color-text-muted)]">
              H <span className="text-[var(--color-accent-green)]">{crosshairData.ohlc.high.toFixed(2)}</span>
            </span>
            <span className="text-[var(--color-text-muted)]">
              L <span className="text-[var(--color-accent-red)]">{crosshairData.ohlc.low.toFixed(2)}</span>
            </span>
            <span className="text-[var(--color-text-muted)]">
              C <span className="text-[var(--color-text-primary)]">{crosshairData.ohlc.close.toFixed(2)}</span>
            </span>
            {showRefLevels && refLevels && (
              <span className="text-[var(--color-text-muted)]">
                Prev: H {refLevels.high.toFixed(2)} / L {refLevels.low.toFixed(2)}
              </span>
            )}
          </div>
        )}

        {/* Chart */}
        <div className="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-primary)]">
          {isLoading ? (
            <div className="flex h-full items-center justify-center">
              <LoadingSpinner size={32} />
            </div>
          ) : error ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-[var(--color-text-muted)]">
              <Clock size={32} className="opacity-50" />
              <p className="text-sm">
                {(error as Error).message?.includes('No data')
                  ? 'No market data available for this date'
                  : (error as Error).message}
              </p>
              {(error as Error).message?.includes('No data') && (
                <p className="text-xs opacity-70">Markets may be closed (weekend or holiday)</p>
              )}
            </div>
          ) : marketData && marketData.count > 0 ? (
            <CandlestickChart
              // Remount on session start/stop (Task 5.1 review handoff):
              // appendMode flipping false->true on an already-mounted
              // instance does NOT re-fit, so a fresh key per session (and
              // back to a stable 'live' key once stopped) forces the first
              // reveal to frame correctly.
              key={`chart-${replay.active ? replay.sessionId : 'live'}`}
              candlestick={replay.active ? replay.revealedBars : marketData.candlestick}
              volume={replay.active ? revealedVolume : marketData.volume}
              showVolume={showVolume}
              rthOnly={rthOnly}
              markers={markers}
              priceLines={priceLines}
              onChartClick={drawingActive ? handleChartClick : undefined}
              onCrosshairMove={setCrosshairData}
              minHeight={400}
              appendMode={replay.active}
            />
          ) : marketData ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-[var(--color-text-muted)]">
              <Clock size={32} className="opacity-50" />
              <p className="text-sm">No market data available for this date</p>
              <p className="text-xs opacity-70">Markets may be closed (weekend or holiday)</p>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-[var(--color-text-muted)]">
              Select a date to load chart data
            </div>
          )}
        </div>
      </div>

      {/* Side panel */}
      <div className="w-72 shrink-0 rounded-xl bg-[var(--surface-2)]">
        {/* Tabs */}
        <div className="flex border-b border-[var(--color-border)]">
          <button
            onClick={() => setActiveTab('trades')}
            className={`flex-1 py-2 text-xs font-medium ${
              activeTab === 'trades'
                ? 'border-b-2 border-[var(--color-accent-blue)] text-[var(--color-accent-blue)]'
                : 'text-[var(--color-text-secondary)]'
            }`}
          >
            Trades ({currentTrades.length})
          </button>
          <button
            onClick={() => setActiveTab('analytics')}
            className={`flex-1 py-2 text-xs font-medium ${
              activeTab === 'analytics'
                ? 'border-b-2 border-[var(--color-accent-blue)] text-[var(--color-accent-blue)]'
                : 'text-[var(--color-text-secondary)]'
            }`}
          >
            Analytics
          </button>
        </div>

        <div className="overflow-auto p-3" style={{ maxHeight: 'calc(100vh - 200px)' }}>
          {activeTab === 'trades' ? (
            <div className="space-y-2">
              {/* Task 3.3: scores this view's CLOSED trades against the
                  production benchmark. Disabled with no closed trades yet
                  (the replay endpoint needs an exit_ts/exit_price to score
                  against) or while a replay is already in flight. */}
              <button
                data-testid="backtest-trades-btn"
                onClick={() => {
                  setScorecardOpen(true);
                  replayTrades.mutate({ ticker: activeTicker, tradeIds: closedTradeIds });
                }}
                disabled={closedTradeIds.length === 0 || replayTrades.isPending}
                title={
                  closedTradeIds.length === 0
                    ? 'Close at least one trade to backtest it'
                    : 'Score your closed trades against the production benchmark'
                }
                className="flex w-full items-center justify-center gap-1 rounded bg-[var(--color-accent-blue)] px-2 py-1.5 text-xs font-medium text-[var(--on-brand)] hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {replayTrades.isPending ? (
                  <LoadingSpinner size={12} />
                ) : (
                  <ClipboardCheck size={14} />
                )}
                Backtest my trades
              </button>

              {currentTrades.length === 0 ? (
                <p className="py-8 text-center text-xs text-[var(--color-text-muted)]">
                  No trades yet. Click "Mark Entry" to start.
                </p>
              ) : (
                currentTrades.map((trade) => (
                  <TradeCard
                    key={trade.id}
                    trade={trade}
                    onExit={startExitMode}
                    onDelete={(id) => deleteChartTrade.mutate({ id, ticker: activeTicker })}
                  />
                ))
              )}

              {/* Playbook seed (Task 2.4) — read-only teaching layer from the
                  automated pipeline. Silent while loading (non-blocking);
                  once settled, an honest muted line replaces the section
                  body on unavailable/error rather than fabricating stats. */}
              {showSeedTrades && !seedTradesQuery.isLoading && (
                <div className="mt-4 border-t border-[var(--color-border)] pt-3">
                  <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-[var(--color-text-secondary)]">
                    <BookOpen size={12} />
                    Playbook seed
                  </div>
                  {replay.active ? (
                    // Replay leakage guard: seedBench/seedRows carry full-day
                    // entry/exit/return_pct — even a partial filter would still
                    // leak the return_pct of a seed trade entered before the
                    // reveal cutoff. Full gate: no rows, no summary, honest
                    // muted line instead (matches the seedMarkers/toggle gate
                    // above).
                    <p className="text-xs text-[var(--color-text-muted)]">unavailable during replay</p>
                  ) : seedUnavailable ? (
                    <p className="text-xs text-[var(--color-text-muted)]">Seed layer unavailable</p>
                  ) : (
                    <>
                      <p className="mb-2 text-xs text-[var(--color-text-muted)]">
                        {seedBench.count === 0 ? (
                          'Seed: —'
                        ) : (
                          <>
                            Seed: {seedBench.count} trade{seedBench.count === 1 ? '' : 's'}
                            {seedBench.winRatePct != null && ` · ${seedBench.winRatePct.toFixed(0)}% win`}
                            {seedBench.avgReturnPct != null &&
                              ` · avg ${seedBench.avgReturnPct >= 0 ? '+' : ''}${seedBench.avgReturnPct.toFixed(2)}%`}
                          </>
                        )}
                      </p>
                      <div className="space-y-2">
                        {seedRows.map((row) => (
                          <SeedTradeCard key={row.id} row={row} />
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          ) : (
            <>
              <label className="mb-2 flex w-fit items-center gap-1.5 text-xs text-[var(--color-text-secondary)]">
                <input
                  type="checkbox"
                  data-testid="include-replay-toggle"
                  checked={includeReplayAnalytics}
                  onChange={(e) => setIncludeReplayAnalytics(e.target.checked)}
                  className="h-3.5 w-3.5 rounded border-[var(--color-border)]"
                />
                Include practice sessions
              </label>
              {/* stats is null while loading or on error — every tile dashes
                  out rather than fabricating "0 trades" (Rule 3.7). The note
                  distinguishes a failed stats call from a quiet load. */}
              {statsUnavailable && (
                <p data-testid="analytics-unavailable" className="mb-2 text-xs text-[var(--warn)]">
                  Analytics unavailable — the stats service didn't respond.
                </p>
              )}
              <div className="grid grid-cols-2 gap-2">
                <MetricCard label="Trades" value={stats ? stats.totalTrades : '--'} />
                <MetricCard label="Win Rate" value={stats && stats.closedTrades > 0 ? `${stats.winRate.toFixed(0)}%` : '--'} />
                <MetricCard label="Total P&L" value={stats && stats.closedTrades > 0 ? `$${stats.totalPnL.toFixed(2)}` : '--'} />
                <MetricCard label="Profit Factor" value={stats && stats.closedTrades > 0 && stats.profitFactor != null ? (stats.profitFactor === Infinity ? '---' : stats.profitFactor.toFixed(2)) : '--'} />
                <MetricCard label="CALL" value={stats ? stats.callCount : '--'} />
                <MetricCard label="PUT" value={stats ? stats.putCount : '--'} />
                <MetricCard label="Max Win" value={stats && stats.maxWin > 0 ? `$${stats.maxWin.toFixed(2)}` : '--'} />
                <MetricCard label="Max Loss" value={stats && stats.maxLoss > 0 ? `-$${stats.maxLoss.toFixed(2)}` : '--'} />
              </div>

              {/* "My style" panel (Task 4.4) — mines the user's own closed
                  journal trades into a walk-forward validated condition
                  profile (POST /api/style/mine-and-validate). */}
              <div className="mt-4 border-t border-[var(--color-border)] pt-3">
                <div className="mb-2 flex items-center justify-between">
                  <div className="flex items-center gap-1 text-xs font-semibold text-[var(--color-text-secondary)]">
                    <Zap size={12} />
                    My style
                  </div>
                  <button
                    data-testid="mine-my-style-btn"
                    onClick={() => mineMyStyle.mutate({ ticker: activeTicker })}
                    disabled={mineMyStyle.isPending}
                    className="flex items-center gap-1 rounded bg-[var(--color-accent-blue)] px-2 py-1 text-xs font-medium text-[var(--on-brand)] hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {mineMyStyle.isPending && <LoadingSpinner size={12} />}
                    {mineMyStyle.isPending ? 'Mining…' : 'Mine my style'}
                  </button>
                </div>

                {mineMyStyle.isError && (
                  <div
                    data-testid="mine-my-style-error"
                    className="rounded border border-[var(--color-accent-red)]/40 bg-red-500/10 p-2 text-xs text-[var(--color-accent-red)]"
                  >
                    {mineMyStyle.error.message}
                  </div>
                )}

                {mineMyStyle.data && (
                  isMineStyleUnavailable(mineMyStyle.data) ? (
                    <p data-testid="mine-my-style-unavailable" className="text-xs text-[var(--color-text-muted)]">
                      {mineMyStyle.data.reason}
                    </p>
                  ) : (
                    <div
                      ref={(el) => {
                        // Result lives at the bottom of a scrollable panel —
                        // bring it into view the render it first appears.
                        if (el && myStyleResultRef.current !== el) {
                          myStyleResultRef.current = el;
                          el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                        }
                      }}
                    >
                      <MyStyleResult result={mineMyStyle.data} />
                    </div>
                  )
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>

    {/* Live strategy conditions — server-computed (POST /api/live/indicators,
        lib/indicators.py), same panel LiveMarketPage/PlaybookPage render. */}
    {chartBars.length >= 14 && (
      <StrategyConditionsCard signals={chartSignals} />
    )}

    {/* Like-this-bar similar past setups — only meaningful once the
        production voter (POST /api/live/signal-series, lib/signals.py)
        has fired on the LATEST bar; the card itself renders a "waits for
        setup" state when direction is null so the slot stays in the layout. */}
    {chartBars.length >= 14 && (() => {
      // Replay leakage guard: signalSeriesQuery's `enabled` flag stops new
      // fetches during a session, but a disabled useQuery still serves
      // whatever `.data` it cached before the session started — that's
      // incidental protection, not a guarantee against a stale full-day
      // cache entry. Force fires to [] explicitly so SimilarSetupsCard
      // always falls back to its no-setup state during replay.
      const fires = replay.active ? [] : signalSeriesQuery.data?.fires ?? [];
      const lastFire = fires.find((f) => f.bar_index === chartBars.length - 1);
      return (
        <SimilarSetupsCard
          ticker={activeTicker}
          direction={lastFire?.direction ?? null}
          rsi={chartIndicators.rsi}
          score={lastFire?.score ?? null}
        />
      );
    })()}

    {/* Backtester section (merged from former /backtest page) */}
    <BacktesterSection ticker={activeTicker} />

    {/* Task 3.3: "Backtest my trades" scorecard. Rendered outside the
        tab-conditional block so switching tabs doesn't unmount it mid-replay. */}
    <Modal
      open={scorecardOpen}
      onClose={() => setScorecardOpen(false)}
      title={`Backtest my trades — ${activeTicker}`}
    >
      <div data-testid="replay-scorecard">
        {replayTrades.isPending && (
          <p className="py-4 text-center text-xs text-[var(--color-text-muted)]">
            Scoring your trades against the system benchmark…
          </p>
        )}
        {replayTrades.isError && (
          <div className="rounded border border-[var(--color-accent-red)]/40 bg-red-500/10 p-2 text-xs text-[var(--color-accent-red)]">
            Replay failed: {replayTrades.error.message}
          </div>
        )}
        {replayTrades.data && (
          <>
            <div className="space-y-2">
              {replayTrades.data.trades.map((card) => (
                <ScorecardRow
                  key={card.id}
                  card={card}
                  labeledDirection={closedTradeDirections.get(card.id) ?? null}
                />
              ))}
            </div>
            <ScorecardFooter aggregate={replayTrades.data.aggregate} />
          </>
        )}
      </div>
    </Modal>
    </div>
  );
}

function TradeCard({
  trade,
  onExit,
  onDelete,
}: {
  trade: TradeEntry;
  onExit: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const isCall = trade.optionType === 'CALL';
  const formatTime = (ts: number) => {
    const d = new Date(ts * 1000);
    return `${d.getUTCHours().toString().padStart(2, '0')}:${d.getUTCMinutes().toString().padStart(2, '0')}`;
  };

  return (
    <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] p-2">
      <div className="flex items-center justify-between">
        <span
          className={`rounded px-1.5 py-0.5 text-xs font-bold ${
            isCall ? 'bg-green-500/20 text-[var(--bull)]' : 'bg-red-500/20 text-[var(--bear)]'
          }`}
        >
          {trade.optionType}
        </span>
        <div className="flex items-center gap-1">
          <span className="text-xs text-[var(--color-text-muted)]">
            {formatTime(trade.entryTime)}
          </span>
          {trade.status === 'active' && (
            <button
              onClick={() => onExit(trade.id)}
              className="rounded p-0.5 text-[var(--color-text-muted)] hover:text-[var(--color-accent-amber)]"
              title="Mark exit"
            >
              <LogOut size={12} />
            </button>
          )}
          <button
            onClick={() => onDelete(trade.id)}
            className="rounded p-0.5 text-[var(--color-text-muted)] hover:text-[var(--color-accent-red)]"
            title="Delete trade"
          >
            <Trash2 size={12} />
          </button>
        </div>
      </div>
      <div className="mt-1 text-xs">
        <span className="text-[var(--color-text-secondary)]">Entry:</span>{' '}
        <span className="font-mono">${trade.entryPrice.toFixed(2)}</span>
      </div>
      {trade.exitPrice && (
        <div className="mt-0.5 text-xs">
          <span className="text-[var(--color-text-secondary)]">Exit:</span>{' '}
          <span className="font-mono">${trade.exitPrice.toFixed(2)}</span>
        </div>
      )}
      {trade.takeProfits.length > 0 && (
        <div className="mt-0.5 text-xs text-[var(--color-accent-green)]">
          TP: {trade.takeProfits.map((tp) => `$${tp.price.toFixed(2)}`).join(' / ')}
        </div>
      )}
      {trade.stopLoss && (
        <div className="mt-0.5 text-xs text-[var(--color-accent-red)]">
          SL: ${trade.stopLoss.price.toFixed(2)}
        </div>
      )}
      {trade.pnl !== undefined && trade.pnl !== null && (
        <div className={`mt-1 text-xs font-medium ${trade.pnl >= 0 ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}`}>
          {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)} ({trade.pnlPercent?.toFixed(2)}%)
        </div>
      )}
    </div>
  );
}

/**
 * Read-only card for one admin seed trade (Task 2.4) — dashed border + muted
 * background distinguishes it from TradeCard at a glance. No exit/delete
 * controls: this is a teaching overlay from the automated pipeline `trades`
 * table, never editable from the chart.
 */
function SeedTradeCard({ row }: { row: SeedTradeRow }) {
  const isCall = row.direction === 'CALL';
  const formatClock = (iso: string | null) => {
    if (!iso) return null;
    const epoch = isoNaiveToEpoch(iso);
    if (Number.isNaN(epoch)) return null;
    const d = new Date(epoch * 1000);
    return `${d.getUTCHours().toString().padStart(2, '0')}:${d.getUTCMinutes().toString().padStart(2, '0')}`;
  };
  const entryClock = formatClock(row.entry_time);
  const exitClock = formatClock(row.exit_time);

  return (
    <div className="rounded border border-dashed border-[var(--color-border)] bg-[var(--color-bg-tertiary)]/60 p-2">
      <div className="flex items-center justify-between">
        <span
          className={`rounded px-1.5 py-0.5 text-xs font-bold ${
            isCall ? 'bg-green-500/10 text-[var(--bull)]' : 'bg-red-500/10 text-[var(--bear)]'
          }`}
        >
          SEED {row.direction}
        </span>
        {entryClock && <span className="text-xs text-[var(--color-text-muted)]">{entryClock}</span>}
      </div>
      {row.entry_price != null && (
        <div className="mt-1 text-xs">
          <span className="text-[var(--color-text-secondary)]">Entry:</span>{' '}
          <span className="font-mono">${row.entry_price.toFixed(2)}</span>
        </div>
      )}
      {row.exit_price != null && (
        <div className="mt-0.5 text-xs">
          <span className="text-[var(--color-text-secondary)]">Exit:</span>{' '}
          <span className="font-mono">${row.exit_price.toFixed(2)}</span>
          {exitClock && <span className="ml-1 text-[var(--color-text-muted)]">({exitClock})</span>}
        </div>
      )}
      {row.strat_combo && (
        <div className="mt-1 inline-block rounded bg-[var(--color-bg-hover)] px-1.5 py-0.5 text-xs text-[var(--color-text-secondary)]">
          {row.strat_combo}
        </div>
      )}
      {row.return_pct != null && (
        <div
          className={`mt-1 text-xs font-medium ${row.return_pct >= 0 ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}`}
        >
          {row.return_pct >= 0 ? '+' : ''}
          {row.return_pct.toFixed(2)}%
        </div>
      )}
    </div>
  );
}

/**
 * One row of the "Backtest my trades" scorecard (Task 3.3). `status ==
 * "unavailable"` trades (POST /api/backtest/replay-trades — missing bars,
 * still-open trade, bad fill data) render ONLY the id + reason, never a
 * fabricated number (CLAUDE.md Rule 3.7) — no return/exit/edge fields are
 * populated on that shape.
 *
 * The scorecard payload doesn't carry the trade's own labeled direction
 * (see lib/backtest.py::replay_labeled_trades — it's stripped before
 * returning), so the caller looks it up client-side from the ticker's own
 * TradeEntry list and passes it in for the agreement badge.
 */
function ScorecardRow({
  card,
  labeledDirection,
}: {
  card: ReplayTradeCard;
  labeledDirection: TradeDirection | null;
}) {
  if (card.status === 'unavailable') {
    return (
      <div
        data-testid={`scorecard-row-${card.id}`}
        className="rounded border border-dashed border-[var(--color-border)] p-2 text-xs text-[var(--color-text-muted)]"
      >
        <span className="font-mono">{card.id}</span> — {card.reason ?? 'unavailable'}
      </div>
    );
  }

  // Agreement badge — four honest states (never collapsed into a binary
  // match/no-match, per lib/backtest.py's _aggregate_scorecards docstring):
  //   1. system_signal_at_entry.status === 'unavailable' -> indicator
  //      warm-up hadn't completed; the system never got a chance to opine.
  //   2. direction === null -> the benchmark ran but had no setup.
  //   3. direction === labeledDirection -> system-resolved AND matches.
  //   4. direction present but != labeledDirection -> system-resolved,
  //      differed from the user's call.
  const signal = card.system_signal_at_entry;
  let badgeLabel: string;
  let badgeClass: string;
  if (!signal || signal.status === 'unavailable') {
    badgeLabel = 'system unavailable';
    badgeClass = 'text-[var(--color-text-muted)]';
  } else if (signal.direction == null) {
    badgeLabel = 'no setup';
    badgeClass = 'text-[var(--color-text-muted)]';
  } else if (signal.direction === labeledDirection) {
    badgeLabel = 'match';
    badgeClass = 'text-[var(--bull)]';
  } else {
    badgeLabel = 'differed';
    badgeClass = 'text-[var(--color-accent-amber)]';
  }

  const yourReturn = card.actual_return_pct;
  const sysExit = card.system_exit;

  return (
    <div
      data-testid={`scorecard-row-${card.id}`}
      className="rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] p-2 text-xs"
    >
      <div className="flex items-center justify-between">
        <span className="font-mono text-[var(--color-text-muted)]">{card.id}</span>
        <div className="flex items-center gap-1">
          {card.fill_check === 'price_outside_bar_range' && (
            <span
              title="Entry price was outside the entry bar's high/low range"
              className="text-[var(--color-accent-amber)]"
            >
              <AlertTriangle size={12} />
            </span>
          )}
          <span className={`font-medium ${badgeClass}`}>{badgeLabel}</span>
        </div>
      </div>
      <div className="mt-1">
        <span className="text-[var(--color-text-secondary)]">Your return:</span>{' '}
        <span className={`font-medium ${yourReturn != null && yourReturn >= 0 ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}`}>
          {yourReturn != null ? `${yourReturn >= 0 ? '+' : ''}${yourReturn.toFixed(2)}%` : '—'}
        </span>
      </div>
      <div className="mt-0.5">
        <span className="text-[var(--color-text-secondary)]">System exit:</span>{' '}
        {sysExit?.exit_reason ?? '—'}{' '}
        <span className={sysExit?.return_pct != null && sysExit.return_pct >= 0 ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}>
          {sysExit?.return_pct != null ? `${sysExit.return_pct >= 0 ? '+' : ''}${sysExit.return_pct.toFixed(2)}%` : '—'}
        </span>
      </div>
      <div className="mt-0.5 text-[var(--color-text-muted)]">Edge: {formatEdgeBps(card.exit_edge_bps)}</div>
    </div>
  );
}

/**
 * Aggregate footer for the scorecard modal (Task 3.3). `n` counts every
 * requested trade; `scored_n` only the ones the replay could actually
 * price. `win_rate`/`avg_return_pct`/`avg_exit_edge_bps` are `null` when
 * `scored_n === 0` — rendered as honest em dashes (the "X / N scored"
 * context line still shows 0/N), never a fabricated "0%" (Rule 3.7,
 * #702 follow-ups Task 2 item 1). `system_agreement_rate` is `null` when
 * the system never resolved a direction on any scored entry — rendered as
 * an honest em dash with the resolved/scored counts as context, never a
 * fabricated 0% (Rule 3.7; see lib/backtest.py's `_aggregate_scorecards`
 * docstring for the exact definition this mirrors). `system_no_signal_n`
 * (Task 2 item 2) surfaces separately as "no setup on Y" so the copy
 * distinguishes "the system disagreed" from "the system never had a
 * setup" whenever Y > 0.
 */
function ScorecardFooter({ aggregate }: { aggregate: ReplayAggregate }) {
  const agreementPct =
    aggregate.system_agreement_rate != null ? `${Math.round(aggregate.system_agreement_rate * 100)}%` : '—';
  const winRatePct = aggregate.win_rate != null ? `${Math.round(aggregate.win_rate * 100)}%` : '—';
  const avgReturnDisplay =
    aggregate.avg_return_pct != null
      ? `${aggregate.avg_return_pct >= 0 ? '+' : ''}${aggregate.avg_return_pct.toFixed(2)}%`
      : '—';
  const avgReturnIsPositive = aggregate.avg_return_pct != null && aggregate.avg_return_pct >= 0;
  const noSetupClause = aggregate.system_no_signal_n > 0 ? ` · no setup on ${aggregate.system_no_signal_n}` : '';

  return (
    <div className="mt-3 space-y-1 border-t border-[var(--color-border)] pt-2 text-xs text-[var(--color-text-secondary)]">
      <div>
        {aggregate.scored_n} / {aggregate.n} scored · Win rate {winRatePct}
      </div>
      <div>
        Avg return:{' '}
        <span className={avgReturnIsPositive ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}>
          {avgReturnDisplay}
        </span>{' '}
        · Avg edge: {formatEdgeBps(aggregate.avg_exit_edge_bps)}
      </div>
      <div>
        Agreement: {agreementPct} — system had a setup on {aggregate.system_resolved_n} of {aggregate.scored_n}{' '}
        entries{noSetupClause}
      </div>
    </div>
  );
}

/**
 * "My style" panel success rendering (Task 4.4) — direction + condition
 * chips (human labels via `styleConditionLabel`), the mining support
 * fraction, and the walk-forward validated stats WITH their sample sizes
 * (total trades across folds, fold count) so a win-rate/expectancy figure
 * is never shown without the N it was computed from. `total_folds` is
 * optional on the aggregate shape — when absent, the fold-count clause is
 * dropped and only the stability percentage renders (never a fabricated
 * "0 folds").
 */
function MyStyleResult({ result }: { result: MineStyleSuccess }) {
  const { profile, aggregate_metrics: agg, stability_score } = result;
  const isCall = profile.direction === 'CALL';

  const winRatePct = agg.avg_win_rate != null ? agg.avg_win_rate * 100 : null;
  const expectancyPct = agg.avg_expectancy_pct;
  const stabilityPct = stability_score * 100;
  const totalFolds = agg.total_folds;
  const totalTrades = agg.total_trades_all_folds;

  return (
    <div data-testid="mine-my-style-result" className="space-y-2">
      <div className="flex flex-wrap items-center gap-1">
        <span
          className={`rounded px-1.5 py-0.5 text-xs font-bold ${
            isCall ? 'bg-green-500/20 text-[var(--bull)]' : 'bg-red-500/20 text-[var(--bear)]'
          }`}
        >
          {profile.direction}
        </span>
        {profile.conditions.map((c) => (
          <span
            key={c}
            className="rounded bg-[var(--color-bg-hover)] px-1.5 py-0.5 text-xs text-[var(--color-text-secondary)]"
          >
            {styleConditionLabel(c)}
          </span>
        ))}
      </div>
      <p className="text-xs text-[var(--color-text-muted)]">
        Based on {profile.support}/{profile.total} of your entries
      </p>
      <p className="text-xs text-[var(--color-text-secondary)]">
        {winRatePct != null ? `Win rate ${winRatePct.toFixed(0)}%` : 'Win rate —'}
        {expectancyPct != null &&
          ` · expectancy ${expectancyPct >= 0 ? '+' : ''}${expectancyPct.toFixed(2)}%`}
        {' · across '}
        {totalTrades} trade{totalTrades === 1 ? '' : 's'}
        {totalFolds != null && `, ${totalFolds} fold${totalFolds === 1 ? '' : 's'}`}
        {` · stability ${stabilityPct.toFixed(0)}%`}
      </p>
    </div>
  );
}
