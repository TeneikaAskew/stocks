import { useState, useCallback, useMemo, useEffect } from 'react';
import { useTickerStore } from '@/stores/tickerStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useTradeStore } from '@/stores/tradeStore';
import { useReviewDateStore } from '@/stores/reviewDateStore';
import { useMarketData, useAvailableDates, useReferenceLevels } from '@/hooks/useMarketData';
import { useTradeAnalytics } from '@/hooks/useTradeAnalytics';
import { CandlestickChart } from '@/components/charts/CandlestickChart';
import { MetricCard } from '@/components/shared/MetricCard';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import BacktesterSection from '@/components/backtest/BacktesterSection';
import { StrategyConditionsCard } from '@/components/charts/StrategyConditionsCard';
import { SimilarSetupsCard } from '@/components/charts/SimilarSetupsCard';
import { computeIndicators, calculateVWAP, computeStrategySignals, computeStrategySignalsForSeries, type Bar } from '@/lib/indicators';
import type { Timeframe, TradeEntry, TradeDirection } from '@/types';
import type { CandlestickBar } from '@/hooks/useMarketData';
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
} from 'lucide-react';

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

function calculatePnL(entry: number, exit: number, direction: TradeDirection): number {
  return direction === 'CALL' ? exit - entry : entry - exit;
}

function calculatePnLPercent(entry: number, exit: number, direction: TradeDirection): number {
  const pnl = calculatePnL(entry, exit, direction);
  return (pnl / entry) * 100;
}

export default function ChartsPage() {
  const { activeTicker } = useTickerStore();
  const { timeframe, setTimeframe } = useSettingsStore();
  const { trades, addTrade, updateTrade, removeTrade } = useTradeStore();
  const { reviewDate, reviewTime } = useReviewDateStore();
  const isReview = reviewDate !== null;

  const [localSelectedDate, setLocalSelectedDate] = useState('');
  const [showVolume, setShowVolume] = useState(true);
  const [rthOnly, setRthOnly] = useState(true);
  const [showRefLevels, setShowRefLevels] = useState(false);
  const [showSignals, setShowSignals] = useState(false);
  const [activeTab, setActiveTab] = useState<'trades' | 'analytics'>('trades');

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

  // Auto-select first date (for local state)
  if (!localSelectedDate && dates.length > 0) {
    setLocalSelectedDate(dates[0]);
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

  // Reference levels (prev day OHLC)
  const { data: refLevels } = useReferenceLevels(activeTicker, selectedDate);

  // Trades for current date/ticker — filter out trades after reviewTs in review mode
  const reviewCutoffTs = useMemo(() => {
    if (!isReview || !reviewDate) return null;
    const [y, m, d] = reviewDate.split('-').map(Number);
    const [hh, mm] = (reviewTime ?? '23:59').split(':').map(Number);
    return Math.floor(Date.UTC(y, m - 1, d, hh, mm) / 1000);
  }, [isReview, reviewDate, reviewTime]);

  const currentTrades = useMemo(() => {
    let filtered = trades.filter((t) => t.ticker === activeTicker);
    if (reviewCutoffTs !== null) {
      filtered = filtered.filter(t => (t.exitTime ?? t.entryTime) <= reviewCutoffTs);
    }
    return filtered;
  }, [trades, activeTicker, reviewCutoffTs]);

  const hiddenTradesCount = useMemo(() => {
    if (reviewCutoffTs === null) return 0;
    return trades.filter(t => t.ticker === activeTicker && (t.exitTime ?? t.entryTime) > reviewCutoffTs).length;
  }, [trades, activeTicker, reviewCutoffTs]);
  const stats = useTradeAnalytics(currentTrades);

  // Strategy condition evaluation: build a Bar[] from the candlestick + volume
  // arrays the API returns and compute indicators + VWAP. Need ≥14 bars before
  // RSI is meaningful, so dependent UI hides itself below that threshold.
  const strategyState = useMemo(() => {
    if (!marketData || marketData.candlestick.length < 14) return null;
    const bars: Bar[] = marketData.candlestick.map((c, i) => ({
      time: String(c.time),
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      volume: marketData.volume[i]?.value ?? 0,
    }));
    const indicators = computeIndicators(bars);
    const vwap = calculateVWAP(bars);
    return { bars, indicators, vwap };
  }, [marketData]);

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
  // for PUT fires. Computed client-side from the loaded bars via the same
  // 5-condition voter as trading_analysis.py. Toggled by the Sig button.
  const signalMarkers: SeriesMarker<Time>[] = useMemo(() => {
    if (!showSignals || !strategyState) return [];
    const fires = computeStrategySignalsForSeries(strategyState.bars);
    return fires.map((s) => ({
      time: Number(s.time) as Time,
      position: s.direction === 'CALL' ? 'belowBar' : 'aboveBar',
      color: s.direction === 'CALL' ? '#22c55e' : '#ef4444',
      shape: s.direction === 'CALL' ? 'arrowUp' : 'arrowDown',
      text: `${s.direction} ${s.metCount}/5`,
    }));
  }, [showSignals, strategyState]);

  // Trade markers on top of signal markers so user trades win the visual
  // priority (and re-render last in the chart's marker plugin).
  const markers: SeriesMarker<Time>[] = useMemo(
    () => [...signalMarkers, ...tradeMarkers],
    [signalMarkers, tradeMarkers],
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

    return lines;
  }, [currentTrades, showRefLevels, refLevels]);

  // Chart click handler
  const handleChartClick = useCallback(
    (data: { time: number; price: number }) => {
      if (drawingStep === 'entry') {
        setTempTrade({
          entryTime: data.time,
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
          const pnl = calculatePnL(trade.entryPrice, data.price, trade.optionType);
          const pnlPct = calculatePnLPercent(trade.entryPrice, data.price, trade.optionType);
          updateTrade(exitingTradeId, {
            exitTime: data.time,
            exitPrice: data.price,
            pnl,
            pnlPercent: pnlPct,
            status: pnl > 0 ? 'win' : pnl < 0 ? 'loss' : 'breakeven',
          });
        }
        cancelDrawing();
      }
    },
    [drawingStep, tempTrade, exitingTradeId, trades, updateTrade]
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
    const trade: TradeEntry = {
      id: `trade_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      ticker: activeTicker,
      optionType: data.optionType,
      entryTime: data.entryTime,
      entryPrice: data.entryPrice,
      takeProfits: data.takeProfits.length > 0 ? data.takeProfits : [],
      stopLoss: data.stopLoss,
      notes: '',
      tags: [],
      status: 'active',
      createdAt: Date.now(),
    };
    addTrade(trade);
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

          <button
            onClick={() => setShowSignals(!showSignals)}
            title="Overlay 5-condition voter signals on the chart"
            className={`flex items-center gap-1 rounded px-2 py-1.5 text-xs ${
              showSignals ? 'bg-[var(--color-bg-hover)] text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'
            }`}
          >
            <Activity size={14} />
            Sig
          </button>

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
              candlestick={marketData.candlestick}
              volume={marketData.volume}
              showVolume={showVolume}
              rthOnly={rthOnly}
              markers={markers}
              priceLines={priceLines}
              onChartClick={drawingActive ? handleChartClick : undefined}
              onCrosshairMove={setCrosshairData}
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
                    onDelete={removeTrade}
                  />
                ))
              )}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="Trades" value={stats.totalTrades} />
              <MetricCard label="Win Rate" value={stats.closedTrades > 0 ? `${stats.winRate.toFixed(0)}%` : '--'} />
              <MetricCard label="Total P&L" value={stats.closedTrades > 0 ? `$${stats.totalPnL.toFixed(2)}` : '--'} />
              <MetricCard label="Profit Factor" value={stats.closedTrades > 0 ? stats.profitFactor === Infinity ? '---' : stats.profitFactor.toFixed(2) : '--'} />
              <MetricCard label="CALL" value={stats.callCount} />
              <MetricCard label="PUT" value={stats.putCount} />
              <MetricCard label="Max Win" value={stats.maxWin > 0 ? `$${stats.maxWin.toFixed(2)}` : '--'} />
              <MetricCard label="Max Loss" value={stats.maxLoss > 0 ? `-$${stats.maxLoss.toFixed(2)}` : '--'} />
            </div>
          )}
        </div>
      </div>
    </div>

    {/* Live strategy conditions — actionable readout matching trading_analysis.py voter */}
    {strategyState && (
      <StrategyConditionsCard
        bars={strategyState.bars}
        indicators={strategyState.indicators}
        vwap={strategyState.vwap}
      />
    )}

    {/* Like-this-bar similar past setups — only meaningful once the voter
        has fired; the card itself renders a "waits for setup" state when
        firing is null so the slot stays in the layout. */}
    {strategyState && (() => {
      const v = computeStrategySignals(strategyState.bars, strategyState.indicators, strategyState.vwap);
      const score = v.firing === 'CALL' ? v.call.metCount : v.firing === 'PUT' ? v.put.metCount : null;
      return (
        <SimilarSetupsCard
          ticker={activeTicker}
          direction={v.firing}
          rsi={strategyState.indicators.rsi}
          score={score}
        />
      );
    })()}

    {/* Backtester section (merged from former /backtest page) */}
    <BacktesterSection ticker={activeTicker} />
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
