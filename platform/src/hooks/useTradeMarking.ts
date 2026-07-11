import { useCallback, useEffect, useState } from 'react';
import type { TradeDirection, TradeEntry } from '@/types';
import type { CreateChartTradeVars, CloseChartTradeVars } from '@/hooks/useJournalChartTrades';

/**
 * Trade-marking state machine — extracted verbatim from ChartsPage.tsx
 * (the DrawingStep type + drawing state + handleChartClick/ESC handling
 * that used to live at ChartsPage.tsx:78, ~600-700). Any component that
 * hosts a mark-entry chart experience (ChartsPage today; the Journal page
 * in a later phase) calls this ONE hook instance and wires its returned
 * handlers into both the chart's click handler AND any sibling "exit"
 * trigger (e.g. a trade rail card's Exit button) — the two need to share
 * the same drawingStep/tempTrade/exitingTradeId state, so this hook must
 * be called exactly once per page and its pieces threaded down, not
 * re-instantiated inside each consumer.
 */
export type DrawingStep = 'idle' | 'entry' | 'option-type' | 'tp1' | 'tp2' | 'tp3' | 'sl' | 'exit';

export interface TempTradeData {
  entryTime: number;
  entryPrice: number;
  optionType?: TradeDirection;
  takeProfits: { price: number; size: number }[];
  stopLoss?: { price: number };
}

export interface UseTradeMarkingParams {
  /** Ticker the new/closed trade should be tagged with (POST/PATCH body). */
  ticker: string;
  /** Trades currently loaded for this ticker/date — only used to confirm an
   *  exit-in-progress trade still exists before firing onTradeExited (mirrors
   *  the original inline `trades.find(...)` guard). */
  trades: TradeEntry[];
  /** Bar-replay-trainer session state (Task 5.2). While active, entry/exit
   *  epochs are pinned to the last REVEALED bar's time rather than wherever
   *  on the chart the user clicked — the click still picks the PRICE, but the
   *  time is clamped so a mid-playback trade can never carry a future-bar
   *  epoch. Mirrors ChartsPage's original replay-leakage guard verbatim. */
  replayActive: boolean;
  replayRevealedBars: { time: number }[];
  replaySessionId: string | null;
  /** Fires with the exact same payload shape ChartsPage used to pass
   *  directly to useCreateChartTrade().mutate(...). */
  onTradeCreated: (vars: CreateChartTradeVars) => void;
  /** Fires with the exact same payload shape ChartsPage used to pass
   *  directly to useCloseChartTrade().mutate(...). */
  onTradeExited: (vars: CloseChartTradeVars) => void;
}

export interface UseTradeMarkingResult {
  drawingStep: DrawingStep;
  tempTrade: TempTradeData | null;
  exitingTradeId: string | null;
  /** Mirrors ChartsPage's original `drawingActive` derivation — gates
   *  whether the chart's onChartClick prop should be wired up at all. */
  drawingActive: boolean;
  handleChartClick: (data: { time: number; price: number }) => void;
  /** `() => setDrawingStep('entry')` — the Mark Entry button's onClick. */
  startDrawing: () => void;
  selectOptionType: (type: TradeDirection) => void;
  skipToSL: () => void;
  skipSL: () => void;
  startExitMode: (tradeId: string) => void;
  cancelDrawing: () => void;
}

export function useTradeMarking(params: UseTradeMarkingParams): UseTradeMarkingResult {
  const {
    ticker,
    trades,
    replayActive,
    replayRevealedBars,
    replaySessionId,
    onTradeCreated,
    onTradeExited,
  } = params;

  // Drawing mode state
  const [drawingStep, setDrawingStep] = useState<DrawingStep>('idle');
  const [tempTrade, setTempTrade] = useState<TempTradeData | null>(null);
  const [exitingTradeId, setExitingTradeId] = useState<string | null>(null);

  const cancelDrawing = () => {
    setDrawingStep('idle');
    setTempTrade(null);
    setExitingTradeId(null);
  };

  const completeTrade = (data: TempTradeData) => {
    if (!data.optionType) return;
    onTradeCreated({
      ticker,
      direction: data.optionType,
      entryTime: data.entryTime,
      entryPrice: data.entryPrice,
      stopLoss: data.stopLoss?.price,
      takeProfits: data.takeProfits.map((tp) => tp.price),
      // Trades drawn during a bar-replay trainer session (Task 5.2) are
      // tagged `source: 'replay'` + the session's UUID so Task 5.3's
      // post-session review can group them apart from ordinary chart trades.
      source: replayActive ? 'replay' : 'chart',
      sessionId: replayActive ? (replaySessionId ?? undefined) : undefined,
    });
    cancelDrawing();
  };

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
          replayActive && replayRevealedBars.length > 0
            ? replayRevealedBars[replayRevealedBars.length - 1].time
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
            replayActive && replayRevealedBars.length > 0
              ? replayRevealedBars[replayRevealedBars.length - 1].time
              : data.time;
          // PATCH persists the exit; return_pct/status come back from the
          // server (journal.py's _return_pct/_derive_status) — no client-side
          // pnl math here, the query invalidation refetches the closed row.
          onTradeExited({
            id: exitingTradeId,
            ticker,
            exitTime,
            exitPrice: data.price,
          });
        }
        cancelDrawing();
      }
    },
    [drawingStep, tempTrade, exitingTradeId, trades, onTradeExited, replayActive, replayRevealedBars]
  );

  const startDrawing = () => setDrawingStep('entry');

  const selectOptionType = (type: TradeDirection) => {
    if (!tempTrade) return;
    setTempTrade({ ...tempTrade, optionType: type });
    setDrawingStep('tp1');
  };

  const skipToSL = () => setDrawingStep('sl');
  const skipSL = () => {
    if (tempTrade) completeTrade(tempTrade);
  };

  const startExitMode = (tradeId: string) => {
    setExitingTradeId(tradeId);
    setDrawingStep('exit');
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawingStep, tempTrade]);

  const drawingActive = drawingStep !== 'idle' && drawingStep !== 'option-type';

  return {
    drawingStep,
    tempTrade,
    exitingTradeId,
    drawingActive,
    handleChartClick,
    startDrawing,
    selectOptionType,
    skipToSL,
    skipSL,
    startExitMode,
    cancelDrawing,
  };
}
