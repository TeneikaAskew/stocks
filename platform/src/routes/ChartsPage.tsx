import { useState, useMemo, useEffect, useRef } from 'react';
import { useTickerStore } from '@/stores/tickerStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useReviewDateStore } from '@/stores/reviewDateStore';
import { useMarketData, useAvailableDates, useReferenceLevels } from '@/hooks/useMarketData';
import { useGammaLevels } from '@/hooks/useGammaLevels';
import {
  useJournalChartTrades,
  useCreateChartTrade,
  useCloseChartTrade,
  useReplayTrades,
  formatEdgeBps,
  type ReplayTradeCard,
  type ReplayAggregate,
} from '@/hooks/useJournalChartTrades';
import {
  TradeMarkingChart,
  type TradeMarkingChartHandle,
  type PriceLineConfig,
} from '@/components/journal/TradeMarkingChart';
import type { DrawingStep } from '@/hooks/useTradeMarking';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { Modal } from '@/components/shared/Modal';
import BacktesterSection from '@/components/backtest/BacktesterSection';
import { StrategyConditionsCard } from '@/components/charts/StrategyConditionsCard';
import { SimilarSetupsCard } from '@/components/charts/SimilarSetupsCard';
import { ReplaySessionControls } from '@/components/charts/ReplaySessionControls';
import { useReplaySession } from '@/hooks/useReplaySession';
import { useLiveIndicators, useSignalSeries } from '@/hooks/useLiveIndicators';
import { EMPTY_INDICATORS, type Bar } from '@/lib/indicators';
import type { Timeframe, TradeDirection, ChartVoter } from '@/types';
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
  Zap,
  AlertTriangle,
} from 'lucide-react';

// Tickers for which we have an options chain in Cloud SQL (matches
// VALID_TICKERS in platform/api/routers/options.py). The Gamma toggle
// is hidden for any other ticker because the /levels endpoint will 400.
const GAMMA_LEVELS_TICKERS = new Set(['SPY', 'IWM', 'QQQ', 'SPX']);

// Pre-fetch/no-data fallback for the chart_voter slice of useLiveIndicators'
// response (July-6 5-condition teaching voter, lib/chart_voter.py). "No
// setup" + zero counts is an honest empty state, not a fabricated result —
// StrategyConditionsCard only renders it before the query resolves.
const EMPTY_CHART_VOTER: ChartVoter = {
  call: { direction: 'CALL', conditions: [], met_count: 0, total_count: 5, fires: false },
  put: { direction: 'PUT', conditions: [], met_count: 0, total_count: 5, fires: false },
  firing: null,
};

const TIMEFRAMES: { value: Timeframe; label: string }[] = [
  { value: '1', label: '1m' },
  { value: '5', label: '5m' },
  { value: '15', label: '15m' },
  { value: '30', label: '30m' },
  { value: '60', label: '1h' },
];

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
  // Task 5.3: end-of-session note when stop() found no closed trades to
  // score (so no scorecard POST/modal fires) — cleared on the next session.
  const [sessionEndNote, setSessionEndNote] = useState<string | null>(null);

  // Drawing mode state — mirrors the drawingStep owned by TradeMarkingChart's
  // useTradeMarking instance (Task 4 extraction). ChartsPage no longer owns
  // the state machine itself; it only needs the CURRENT step to drive the
  // toolbar's own Mark Entry/CALL/PUT/status UI, wired to the chart via
  // tradeMarkingRef.
  //
  // Task 6 (journal-one-stop): Charts carries ZERO general-purpose journal
  // activity — the full trade-marking experience (browsing, editing,
  // exporting) lives on /journal now. The ONE thing that survives here is
  // the bar-replay trainer's own create/score path (design spec's flagged
  // decision: "the replay trainer writes source='replay' practice rows via
  // its own path — that stays"), so this toolbar chrome block only renders
  // while `replay.active` — see the JSX below. Outside a replay session,
  // drawingStep never leaves 'idle' because nothing can trigger
  // tradeMarkingRef.current?.startDrawing().
  const [drawingStep, setDrawingStep] = useState<DrawingStep>('idle');
  const tradeMarkingRef = useRef<TradeMarkingChartHandle>(null);

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
  // Task 6 (journal-one-stop): this fetch (and createChartTrade below) is no
  // longer in service of a general trades-browsing panel — that panel is
  // gone. Both survive purely to support the ONE thing that stays on Charts:
  // the bar-replay trainer's leakage-cutoff filtering (currentTrades below)
  // and its own create/score path (Mark Entry, gated to `replay.active` in
  // the JSX). deleteChartTrade (delete from a trade rail card) had no
  // caller left once that card's panel was removed. closeChartTrade stays —
  // TradeMarkingChart's `onTradeExited` prop is required by its type even
  // though nothing on this page currently triggers startExitMode (that
  // trigger lived on the removed TradeRailCard's "Exit" button).
  const { data: trades = [] } = useJournalChartTrades(activeTicker, selectedIsoDate);
  const createChartTrade = useCreateChartTrade();
  const closeChartTrade = useCloseChartTrade();

  // Task 5.3: post-replay-session scorecard — the ONE scorecard surface that
  // survives the Task 3.3 "Backtest my trades" on-demand button removal
  // (that button lived in the now-removed side panel). Fires exactly once
  // per finished bar-replay-trainer session (guarded by scoredSessionIdRef
  // so a re-render — e.g. `trades` refetching — never double-fires) once
  // useReplaySession's stop() lands a summary: if the session tagged >=1
  // CLOSED trade (status !== 'active'), POST /api/backtest/replay-trades
  // with {ticker, session_id} and open the scorecard modal. Zero closed
  // trades -> no POST, just an end-of-session note.
  const [scorecardOpen, setScorecardOpen] = useState(false);
  const replayTrades = useReplayTrades();
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

  // #702 follow-ups Task 4 item 6 (still applicable post-Task-6): an open
  // replay-trades scorecard is a per-ticker artifact — mirror
  // BacktesterSection's `lastTicker` render-time-adjustment idiom (this
  // component is mounted unkeyed, so switching the ticker doesn't remount
  // it) so a stale prior ticker's scorecard rows never linger on screen
  // under the new symbol.
  const [lastTicker, setLastTicker] = useState(activeTicker);
  if (lastTicker !== activeTicker) {
    setLastTicker(activeTicker);
    setScorecardOpen(false);
    replayTrades.reset();
  }

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

  // Still needed by ScorecardRow (Task 5.3 scorecard modal) to show the
  // agreement badge — a trade's own labeled direction isn't part of the
  // /api/backtest/replay-trades payload (see lib/backtest.py's
  // replay_labeled_trades), so the caller looks it up client-side.
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
  // useLiveIndicators usage so the same server-computed indicators drive
  // every page. The card itself renders the July-6 5-condition
  // `chart_voter` slice of this response (lib/chart_voter.py), not the
  // 10-condition strength `signals` shape LiveMarketPage/PlaybookPage use.
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
  const chartVoter = indicatorsQuery.data?.chart_voter ?? EMPTY_CHART_VOTER;

  // Task 4 extraction: the user's own trade markers (entry/exit arrows +
  // PNL exit circle) are now built INSIDE TradeMarkingChart from its
  // `trades` prop — ChartsPage only builds the "extra" signal overlay
  // below, which TradeMarkingChart merges underneath its own.

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

  // Extra overlays merged UNDER TradeMarkingChart's own trade markers/TP-SL
  // lines (Task 4 extraction) — signal overlay for markers, reference/gamma
  // levels for price lines. Task 6 (journal-one-stop) removed the admin
  // seed-trade teaching layer (Playbook seed) from Charts — that overlay now
  // lives only inside the Journal page's Examples view.
  const extraMarkers: SeriesMarker<Time>[] = signalMarkers;

  const extraPriceLines: PriceLineConfig[] = useMemo(() => {
    const lines: PriceLineConfig[] = [];

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
  }, [showRefLevels, refLevels, showGamma, gammaLevels]);

  // Task 6 (journal-one-stop): JSON/CSV trade export moved to /journal —
  // exportTradesJSON/exportTradesCSV had no caller left once removed.

  return (
    <div className="flex flex-col gap-6">
      {/* Chart area — Task 6 (journal-one-stop) removed the Trades/Analytics
          side panel that used to sit beside this at w-72; the chart now
          takes the full row width. */}
      <div className="flex flex-1 flex-col">
        {/* Toolbar */}
        <div className="mb-3 flex flex-wrap items-center gap-3 xl:flex-nowrap">
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

          {/* Task 6 (journal-one-stop): Mark Entry + the CALL/PUT/skip
              drawing chrome is no longer general-purpose Charts UI — the
              trade-journal marking flow lives on /journal now. The ONE
              carve-out is the bar-replay trainer (design spec's flagged
              decision: "the replay trainer writes source='replay' practice
              rows via its own path — that stays"), so this block only
              renders while a replay session is active; outside a session
              there is no way to trigger tradeMarkingRef.current?.startDrawing()
              and drawingStep never leaves 'idle'. */}
          {replay.active && (
            drawingStep === 'idle' ? (
              <button
                onClick={() => tradeMarkingRef.current?.startDrawing()}
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
                      onClick={() => tradeMarkingRef.current?.selectOptionType('CALL')}
                      className="flex items-center gap-1 rounded bg-[var(--bull)] px-2 py-1 text-xs text-black"
                    >
                      <ArrowUpCircle size={12} />
                      CALL
                    </button>
                    <button
                      onClick={() => tradeMarkingRef.current?.selectOptionType('PUT')}
                      className="flex items-center gap-1 rounded bg-[var(--bear)] px-2 py-1 text-xs text-white"
                    >
                      <ArrowDownCircle size={12} />
                      PUT
                    </button>
                  </div>
                )}
                <button
                  onClick={() => tradeMarkingRef.current?.cancelDrawing()}
                  className="rounded p-1 text-[var(--color-text-muted)] hover:text-[var(--color-accent-red)]"
                >
                  <X size={16} />
                </button>
              </div>
            )
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
        <div
          data-testid="chart-card"
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-primary)]"
          style={{ height: 'clamp(400px, calc(100vh - 340px), 900px)' }}
        >
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
            <TradeMarkingChart
              ref={tradeMarkingRef}
              ticker={activeTicker}
              // Remount on session start/stop (Task 5.1 review handoff):
              // appendMode flipping false->true on an already-mounted
              // instance does NOT re-fit, so a fresh key per session (and
              // back to a stable 'live' key once stopped) forces the first
              // reveal to frame correctly. Applied only to the underlying
              // CandlestickChart (see TradeMarkingChart's chartKey doc) so
              // the in-progress marking state survives the remount exactly
              // as it did when ChartsPage owned both directly.
              chartKey={`chart-${replay.active ? replay.sessionId : 'live'}`}
              bars={replay.active ? replay.revealedBars : marketData.candlestick}
              volume={replay.active ? revealedVolume : marketData.volume}
              trades={currentTrades}
              onTradeCreated={(vars) => createChartTrade.mutate(vars)}
              onTradeExited={(vars) => closeChartTrade.mutate(vars)}
              markersStyle="own"
              extraMarkers={extraMarkers}
              extraPriceLines={extraPriceLines}
              showVolume={showVolume}
              rthOnly={rthOnly}
              onCrosshairMove={setCrosshairData}
              minHeight={400}
              appendMode={replay.active}
              replayActive={replay.active}
              replayRevealedBars={replay.revealedBars}
              replaySessionId={replay.sessionId}
              onDrawingStepChange={setDrawingStep}
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

    {/* Live strategy conditions — server-computed chart teaching voter
        (POST /api/live/indicators -> chart_voter, lib/chart_voter.py),
        the July-6 5-condition presentation restored per Task 3. */}
    {chartBars.length >= 14 && (
      <StrategyConditionsCard voter={chartVoter} />
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

    {/* Task 5.3 post-replay-session scorecard — the only remaining trigger
        for this modal after Task 6 removed the Task 3.3 on-demand
        "Backtest my trades" button (it lived in the now-removed side
        panel). Rendered at the page's top level so it survives independent
        of any tab/panel state. */}
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

/**
 * One row of the "Backtest my trades" scorecard (Task 3.3, now triggered
 * only by the Task 5.3 post-replay-session auto-scorecard). `status ==
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
