import { forwardRef, useEffect, useImperativeHandle, useMemo } from 'react';
import type { SeriesMarker, Time, LineWidth } from 'lightweight-charts';
import { CandlestickChart } from '@/components/charts/CandlestickChart';
import { useTradeMarking, type DrawingStep } from '@/hooks/useTradeMarking';
import type { CreateChartTradeVars, CloseChartTradeVars } from '@/hooks/useJournalChartTrades';
import type { TradeEntry } from '@/types';
import type { CandlestickBar, VolumeBar } from '@/hooks/useMarketData';

export interface PriceLineConfig {
  price: number;
  color: string;
  title: string;
  lineStyle?: number;
  lineWidth?: LineWidth;
}

// Muted color for the read-only Examples teaching layer (Task 5) —
// deliberately gray, never the bull/bear green/red the user's own trades
// use, matching ChartsPage's SEED_MARKER_COLOR convention for the same
// "two layers must be unmistakable at a glance" reason.
const EXAMPLE_MARKER_COLOR = '#8a8f98';

// Rail-card hover → chart highlight (design spec Option B, Task 5 gap):
// "Hovering a card highlights its markers on the chart." Markers/price-lines
// keep their base hex color for the highlighted trade and drop to this
// reduced opacity for every other trade's artifacts, so the hovered trade
// visually pops without changing hue (colors stay bull/bear-meaningful).
const DIMMED_ALPHA = 0.25;

function withAlpha(hex: string, alpha: number): string {
  const h = hex.replace('#', '');
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * Imperative surface exposed to a host page's OWN toolbar/rail-card markup
 * (ChartsPage today; a future Journal page). The state machine lives inside
 * this component (via useTradeMarking) — the host doesn't own drawingStep
 * itself, it just needs to trigger transitions from UI it renders elsewhere
 * in its own tree (a "Mark Entry" button in a shared toolbar row, a trade
 * rail card's "Exit" button) and reflect the current step (via
 * `onDrawingStepChange`). This mirrors how e.g. downshift/react-hook-form
 * expose imperative handles instead of forcing every consumer to duplicate
 * the toolbar chrome.
 */
export interface TradeMarkingChartHandle {
  /** `() => setDrawingStep('entry')` — wire to a host "Mark Entry" button. */
  startDrawing: () => void;
  selectOptionType: (type: 'CALL' | 'PUT') => void;
  cancelDrawing: () => void;
  /** Wire to a trade rail card's "Exit" button — primes the next chart
   *  click to PATCH that trade's exit. */
  startExitMode: (tradeId: string) => void;
}

export interface TradeMarkingChartProps {
  /** Ticker the new/closed trade should be tagged with. */
  ticker: string;
  bars: CandlestickBar[];
  volume: VolumeBar[];
  /** Journal-shaped trades to render as entry/exit markers + TP/SL lines. */
  trades: TradeEntry[];
  /** Calls back with the exact payload ChartsPage used to pass directly to
   *  useCreateChartTrade().mutate(...) — the host wires its own mutation. */
  onTradeCreated: (vars: CreateChartTradeVars) => void;
  /** Calls back with the exact payload ChartsPage used to pass directly to
   *  useCloseChartTrade().mutate(...) — the host wires its own mutation. */
  onTradeExited: (vars: CloseChartTradeVars) => void;
  /** 'own' (default) draws the bull/bear arrows + PNL exit circle used for
   *  the caller's own trades. 'examples' (Task 5) draws the read-only
   *  teaching trades in the muted gray seed palette with dashed TP/SL lines
   *  and an `EX` marker prefix — visually unmistakable from own trades. */
  markersStyle?: 'own' | 'examples';
  /** Markers/price-lines computed elsewhere (signal overlay, seed-trade
   *  teaching layer, reference levels, gamma levels) that render UNDER this
   *  component's own trade markers/TP-SL lines. */
  extraMarkers?: SeriesMarker<Time>[];
  extraPriceLines?: PriceLineConfig[];
  showVolume?: boolean;
  rthOnly?: boolean;
  onCrosshairMove?: (data: { time: number; price: number; ohlc?: CandlestickBar } | null) => void;
  minHeight?: number;
  appendMode?: boolean;
  /** Forces the underlying CandlestickChart (only) to remount — e.g. on
   *  bar-replay session start/stop, per CandlestickChart's own doc comment
   *  on `appendMode`. Applied to the CandlestickChart element, NOT this
   *  wrapper, so the drawing-in-progress state machine survives a chart
   *  remount exactly like it did when ChartsPage owned both directly. */
  chartKey?: string;
  /** Bar-replay-trainer session plumbing (Task 5.2) — see useTradeMarking's
   *  doc comment. Defaults are the "no active session" case. */
  replayActive?: boolean;
  replayRevealedBars?: { time: number }[];
  replaySessionId?: string | null;
  /** Fires whenever the internal drawingStep changes — lets a host mirror
   *  it into its own state for concerns outside this component's render
   *  tree (e.g. hiding an export-trades button while marking is active, or
   *  swapping toolbar copy). Optional; omit if the host has no such need. */
  onDrawingStepChange?: (step: DrawingStep) => void;
  /** Rail-card hover → chart highlight (design spec Option B, Task 5 gap).
   *  When set, that trade's markers/price-lines render at full color and
   *  every other trade's dims to `DIMMED_ALPHA`; `null`/undefined (default)
   *  renders every trade at full color — i.e. no behavior change when
   *  nothing is hovered. The host (JournalPage) tracks a single
   *  hoveredTradeId from TradeRailCard's onHover and passes it straight
   *  through; ChartsPage doesn't pass this prop and stays unaffected. */
  highlightedTradeId?: string | null;
}

/**
 * Wraps CandlestickChart + the useTradeMarking state machine + the
 * marker/price-line construction that used to live inline in ChartsPage
 * (Task 4 extraction — see docs/... task-4-brief.md). Accepts journal-shaped
 * trades and calls back with the same payload ChartsPage currently POSTs;
 * CandlestickChart itself is untouched.
 */
export const TradeMarkingChart = forwardRef<TradeMarkingChartHandle, TradeMarkingChartProps>(
  function TradeMarkingChart(
    {
      ticker,
      bars,
      volume,
      trades,
      onTradeCreated,
      onTradeExited,
      markersStyle = 'own',
      extraMarkers,
      extraPriceLines,
      showVolume,
      rthOnly,
      onCrosshairMove,
      minHeight,
      appendMode,
      chartKey,
      replayActive = false,
      replayRevealedBars = [],
      replaySessionId = null,
      onDrawingStepChange,
      highlightedTradeId = null,
    },
    ref,
  ) {
    const marking = useTradeMarking({
      ticker,
      trades,
      replayActive,
      replayRevealedBars,
      replaySessionId,
      onTradeCreated,
      onTradeExited,
    });

    useImperativeHandle(
      ref,
      () => ({
        startDrawing: marking.startDrawing,
        selectOptionType: marking.selectOptionType,
        cancelDrawing: marking.cancelDrawing,
        startExitMode: marking.startExitMode,
      }),
      [marking.startDrawing, marking.selectOptionType, marking.cancelDrawing, marking.startExitMode],
    );

    // Mirror drawingStep out to the host via an effect (NOT during render —
    // calling a parent's setState while a child is rendering is a React
    // anti-pattern; render-time state adjustment is only for a component's
    // OWN state). One render behind is fine here: the host only uses this
    // for secondary concerns (export-button visibility), never for anything
    // that gates the marking flow itself.
    useEffect(() => {
      onDrawingStepChange?.(marking.drawingStep);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [marking.drawingStep]);

    // Build chart markers from trades — verbatim from ChartsPage's original
    // tradeMarkers useMemo for markersStyle='own'; 'examples' (Task 5) swaps
    // every color for the muted teaching gray and prefixes the label so the
    // read-only layer can't be mistaken for the caller's own trades.
    const isExamples = markersStyle === 'examples';
    const tradeMarkers: SeriesMarker<Time>[] = useMemo(() => {
      return trades.flatMap((trade) => {
        const dimmed = highlightedTradeId != null && trade.id !== highlightedTradeId;
        const tint = (hex: string) => (dimmed ? withAlpha(hex, DIMMED_ALPHA) : hex);
        const m: SeriesMarker<Time>[] = [];
        m.push({
          time: trade.entryTime as Time,
          position: trade.optionType === 'CALL' ? 'belowBar' : 'aboveBar',
          color: tint(
            isExamples
              ? EXAMPLE_MARKER_COLOR
              : trade.optionType === 'CALL'
                ? '#089981'
                : '#f23645',
          ),
          shape: trade.optionType === 'CALL' ? 'arrowUp' : 'arrowDown',
          text: `${isExamples ? 'EX ' : ''}${trade.optionType} @ $${trade.entryPrice.toFixed(2)}`,
        });
        if (trade.exitTime) {
          // AUDIT-2026-05-13: silent fallback — pre-existing; only reachable
          // via manual DB writes (server always sets return_pct on close).
          // See docs/audits/FALLBACK_AUDIT_2026-05-13.md
          const pnl = trade.pnl ?? 0;
          m.push({
            time: trade.exitTime as Time,
            position: pnl >= 0 ? 'aboveBar' : 'belowBar',
            color: tint(isExamples ? EXAMPLE_MARKER_COLOR : pnl >= 0 ? '#089981' : '#f23645'),
            shape: 'circle',
            text: `${isExamples ? 'EX ' : ''}Exit ${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`,
          });
        }
        return m;
      });
    }, [trades, isExamples, highlightedTradeId]);

    const markers: SeriesMarker<Time>[] = useMemo(
      () => [...(extraMarkers ?? []), ...tradeMarkers],
      [extraMarkers, tradeMarkers],
    );

    // Build TP/SL price lines from trades — verbatim from ChartsPage's
    // original priceLines useMemo (trade portion only; reference/gamma
    // levels are computed by the host and passed in via extraPriceLines).
    //
    // PR #728 review FIX 2: originally skipped every non-'active' trade
    // (`if (trade.status !== 'active') continue;`), so a CLOSED Examples row
    // never drew its target/stop lines — defeating the teaching purpose (the
    // whole point of an example is to SEE the target/stop it was playing
    // for). Now every trade draws its TP/SL lines; a CLOSED trade's lines
    // reuse the existing hover-dim `withAlpha`/tint pattern (reduced alpha)
    // so it visually recedes behind an ACTIVE trade's full-strength lines,
    // and the hover-highlighted trade always wins (full strength) regardless
    // of status — same "highlighted trade pops" rule the marker dimming
    // already follows.
    const tradePriceLines: PriceLineConfig[] = useMemo(() => {
      const lines: PriceLineConfig[] = [];
      for (const trade of trades) {
        const isHighlighted = highlightedTradeId != null && trade.id === highlightedTradeId;
        const dimmed =
          !isHighlighted && (trade.status !== 'active' || highlightedTradeId != null);
        const tint = (hex: string) => (dimmed ? withAlpha(hex, DIMMED_ALPHA) : hex);
        // Highlighted trade's lines get a thicker weight so the hover effect
        // is visible even for readers who don't distinguish the opacity
        // difference on the dimmed siblings; untouched (no hover) case keeps
        // the original unset lineWidth (CandlestickChart defaults to 1).
        const lineWidth = isHighlighted ? (3 as LineWidth) : undefined;
        trade.takeProfits.forEach((tp, i) => {
          lines.push({
            price: tp.price,
            color: tint(isExamples ? EXAMPLE_MARKER_COLOR : '#089981'),
            title: isExamples ? `EX TP${i + 1}` : `TP${i + 1}`,
            lineStyle: isExamples ? 1 : 2, // examples: Dashed; own: Dotted
            lineWidth,
          });
        });
        if (trade.stopLoss) {
          lines.push({
            price: trade.stopLoss.price,
            color: tint(isExamples ? EXAMPLE_MARKER_COLOR : '#f23645'),
            title: isExamples ? 'EX SL' : 'SL',
            lineStyle: isExamples ? 1 : 2,
            lineWidth,
          });
        }
      }
      return lines;
    }, [trades, isExamples, highlightedTradeId]);

    const priceLines: PriceLineConfig[] = useMemo(
      () => [...tradePriceLines, ...(extraPriceLines ?? [])],
      [tradePriceLines, extraPriceLines],
    );

    return (
      // data-highlighted-trade mirrors highlightedTradeId into the DOM so
      // the rail-card-hover → chart-highlight link (design spec Option B,
      // Task 5 gap) is e2e-testable — lightweight-charts renders to canvas,
      // which Playwright can't pixel-inspect. data-price-lines (PR #728
      // review FIX 2) mirrors the count of TP/SL price lines this render
      // computed (trade-derived only, not extraPriceLines) for the same
      // canvas-can't-be-pixel-inspected reason — the honest assertable
      // surface for "closed trades now draw their TP/SL lines" is this
      // count, not a canvas pixel read.
      <div
        data-testid="trade-marking-chart"
        data-highlighted-trade={highlightedTradeId ?? undefined}
        data-price-lines={tradePriceLines.length}
        className="h-full w-full"
      >
        <CandlestickChart
          key={chartKey}
          candlestick={bars}
          volume={volume}
          showVolume={showVolume}
          rthOnly={rthOnly}
          markers={markers}
          priceLines={priceLines}
          onChartClick={marking.drawingActive ? marking.handleChartClick : undefined}
          onCrosshairMove={onCrosshairMove}
          minHeight={minHeight}
          appendMode={appendMode}
        />
      </div>
    );
  },
);
