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
   *  the caller's own trades. 'examples' is reserved for a future muted
   *  teaching-style render; falls back to 'own' styling until that phase
   *  defines its palette. */
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
    // tradeMarkers useMemo.
    const tradeMarkers: SeriesMarker<Time>[] = useMemo(() => {
      return trades.flatMap((trade) => {
        const m: SeriesMarker<Time>[] = [];
        m.push({
          time: trade.entryTime as Time,
          position: trade.optionType === 'CALL' ? 'belowBar' : 'aboveBar',
          color: trade.optionType === 'CALL' ? '#089981' : '#f23645',
          shape: trade.optionType === 'CALL' ? 'arrowUp' : 'arrowDown',
          text: `${trade.optionType} @ $${trade.entryPrice.toFixed(2)}`,
        });
        if (trade.exitTime) {
          // AUDIT-2026-05-13: silent fallback — pre-existing; only reachable
          // via manual DB writes (server always sets return_pct on close).
          // See docs/audits/FALLBACK_AUDIT_2026-05-13.md
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
    }, [trades]);

    const markers: SeriesMarker<Time>[] = useMemo(
      () => [...(extraMarkers ?? []), ...tradeMarkers],
      [extraMarkers, tradeMarkers],
    );

    // Build TP/SL price lines from trades — verbatim from ChartsPage's
    // original priceLines useMemo (trade portion only; reference/gamma
    // levels are computed by the host and passed in via extraPriceLines).
    const tradePriceLines: PriceLineConfig[] = useMemo(() => {
      const lines: PriceLineConfig[] = [];
      for (const trade of trades) {
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
      return lines;
    }, [trades]);

    const priceLines: PriceLineConfig[] = useMemo(
      () => [...tradePriceLines, ...(extraPriceLines ?? [])],
      [tradePriceLines, extraPriceLines],
    );

    return (
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
    );
  },
);
