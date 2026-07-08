import { useEffect, useRef } from 'react';
import { chartTheme, useChartTheme } from '@/lib/chartTheme';
import { useMarketHours } from '@/hooks/useConfig';
import {
  createChart,
  createSeriesMarkers,
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type CandlestickData,
  type HistogramData,
  type Time,
  type LineWidth,
  CrosshairMode,
  LineStyle,
  type SeriesMarker,
} from 'lightweight-charts';
import type { CandlestickBar, VolumeBar } from '@/hooks/useMarketData';

interface ChartClickData {
  time: number;
  price: number;
}

interface PriceLineConfig {
  price: number;
  color: string;
  title: string;
  lineStyle?: number;
  lineWidth?: LineWidth;
}

interface CandlestickChartProps {
  candlestick: CandlestickBar[];
  volume: VolumeBar[];
  showVolume?: boolean;
  rthOnly?: boolean;
  markers?: SeriesMarker<Time>[];
  priceLines?: PriceLineConfig[];
  onChartClick?: (data: ChartClickData) => void;
  onCrosshairMove?: (data: { time: number; price: number; ohlc?: CandlestickBar } | null) => void;
  /** Optional minimum height (px) for the chart container. Undefined = no
   *  floor, so the caller's own wrapper controls sizing (e.g. a dashboard
   *  card that must clip at a fixed height). Callers that need a chart to
   *  never shrink below a comfortable reading height (e.g. /charts) should
   *  pass an explicit value. */
  minHeight?: number;
}

// RTH window comes from /api/config/market-hours via useMarketHours().
// We accept `rthStart`/`rthEnd` as injected minute-of-day values so the
// component stays presentational and we don't issue an extra fetch here.
function filterRTH(
  bars: CandlestickBar[],
  rthStart: number,
  rthEnd: number,
): CandlestickBar[] {
  return bars.filter((bar) => {
    const d = new Date(bar.time * 1000);
    const minutes = d.getUTCHours() * 60 + d.getUTCMinutes();
    return minutes >= rthStart && minutes < rthEnd;
  });
}

// Parse "HH:MM" → minutes-of-day. Falls back to standard NYSE hours if
// the server response is missing.
function parseMinutes(s: string | undefined, fallback: number): number {
  if (!s) return fallback;
  const m = s.match(/^(\d{1,2}):(\d{2})/);
  if (!m) return fallback;
  return Number(m[1]) * 60 + Number(m[2]);
}

function filterRTHVolume(bars: VolumeBar[], rthTimes: Set<number>): VolumeBar[] {
  return bars.filter((bar) => rthTimes.has(bar.time));
}

export function CandlestickChart({
  candlestick,
  volume,
  showVolume = true,
  rthOnly = true,
  markers,
  priceLines,
  onChartClick,
  onCrosshairMove,
  minHeight,
}: CandlestickChartProps) {
  // Server-sourced market hours so the RTH filter mirrors Python.
  // Falls back to standard NYSE 09:30-16:00 ET when the config query is
  // still loading or fails — the constants here mirror lib/config defaults.
  const { data: marketHours } = useMarketHours();
  const rthStart = parseMinutes(marketHours?.regular.open, 9 * 60 + 30);
  const rthEnd = parseMinutes(marketHours?.regular.close, 16 * 60);
  const theme = useChartTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const markersPluginRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  // Create chart once
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: chartTheme.bg },
        textColor: chartTheme.axis,
        fontSize: chartTheme.axisSize,
      },
      grid: {
        vertLines: { color: chartTheme.grid },
        horzLines: { color: chartTheme.grid },
      },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: chartTheme.border,
      },
      rightPriceScale: { borderColor: chartTheme.border },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
    });

    // v5 API: chart.addSeries(SeriesDefinition, options)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: chartTheme.bull,
      downColor: chartTheme.bear,
      borderUpColor: chartTheme.bull,
      borderDownColor: chartTheme.bear,
      wickUpColor: chartTheme.bull,
      wickDownColor: chartTheme.bear,
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });

    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    // v5: markers are a plugin
    const markersPlugin = createSeriesMarkers(candleSeries);

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    markersPluginRef.current = markersPlugin;

    // Resize observer
    const resizeObserver = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      chart.applyOptions({ width, height });
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      markersPluginRef.current = null;
    };
  }, []);

  // Update data
  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current) return;

    let displayCandles = candlestick;
    let displayVolume = volume;

    if (rthOnly) {
      displayCandles = filterRTH(candlestick, rthStart, rthEnd);
      const rthTimes = new Set(displayCandles.map((c) => c.time));
      displayVolume = filterRTHVolume(volume, rthTimes);
    }

    const candleData: CandlestickData[] = displayCandles.map((c) => ({
      time: c.time as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    const volumeData: HistogramData[] = displayVolume.map((v) => ({
      time: v.time as Time,
      value: v.value,
      color: v.color,
    }));

    candleSeriesRef.current.setData(candleData);
    volumeSeriesRef.current.setData(volumeData);
    chartRef.current?.timeScale().fitContent();
  }, [candlestick, volume, rthOnly, rthStart, rthEnd]);

  // Toggle volume visibility
  useEffect(() => {
    if (!volumeSeriesRef.current) return;
    volumeSeriesRef.current.applyOptions({
      visible: showVolume,
    });
  }, [showVolume]);

  // Re-apply theme colors when the global theme toggles. The chart and series
  // are created once; on theme change we mutate options in place rather than
  // tearing down the chart so user pan/zoom state is preserved.
  useEffect(() => {
    if (!chartRef.current || !candleSeriesRef.current) return;
    chartRef.current.applyOptions({
      layout: {
        background: { color: theme.bg },
        textColor: theme.axis,
      },
      grid: {
        vertLines: { color: theme.grid },
        horzLines: { color: theme.grid },
      },
      timeScale: { borderColor: theme.border },
      rightPriceScale: { borderColor: theme.border },
    });
    candleSeriesRef.current.applyOptions({
      upColor: theme.bull,
      downColor: theme.bear,
      borderUpColor: theme.bull,
      borderDownColor: theme.bear,
      wickUpColor: theme.bull,
      wickDownColor: theme.bear,
    });
  }, [theme.bg, theme.axis, theme.grid, theme.border, theme.bull, theme.bear]);

  // Markers (v5: use plugin API)
  useEffect(() => {
    if (!markersPluginRef.current || !markers) return;
    markersPluginRef.current.setMarkers(markers);
  }, [markers]);

  // Price lines (with cleanup)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const priceLinesRef = useRef<any[]>([]);
  useEffect(() => {
    if (!candleSeriesRef.current) return;
    const series = candleSeriesRef.current;

    // Remove old price lines
    for (const line of priceLinesRef.current) {
      series.removePriceLine(line);
    }
    priceLinesRef.current = [];

    // Add new price lines
    if (priceLines) {
      for (const pl of priceLines) {
        const line = series.createPriceLine({
          price: pl.price,
          color: pl.color,
          lineWidth: (pl.lineWidth ?? 1) as LineWidth,
          lineStyle: pl.lineStyle ?? LineStyle.Dotted,
          axisLabelVisible: true,
          title: pl.title,
        });
        priceLinesRef.current.push(line);
      }
    }
  }, [priceLines]);

  // Click handler
  useEffect(() => {
    if (!chartRef.current || !onChartClick) return;
    const chart = chartRef.current;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const handler = (param: any) => {
      if (!param.time || !param.point || !candleSeriesRef.current) return;
      const price = candleSeriesRef.current.coordinateToPrice(param.point.y);
      if (price !== null) {
        onChartClick({ time: param.time as number, price: price as number });
      }
    };
    chart.subscribeClick(handler);
    return () => chart.unsubscribeClick(handler);
  }, [onChartClick]);

  // Crosshair handler
  useEffect(() => {
    if (!chartRef.current || !onCrosshairMove) return;
    const chart = chartRef.current;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const handler = (param: any) => {
      if (!param.time || !candleSeriesRef.current) {
        onCrosshairMove(null);
        return;
      }
      const data = param.seriesData?.get(candleSeriesRef.current) as CandlestickBar | undefined;
      const price = data?.close ?? 0;
      onCrosshairMove({
        time: param.time as number,
        price,
        ohlc: data,
      });
    };
    chart.subscribeCrosshairMove(handler);
    return () => chart.unsubscribeCrosshairMove(handler);
  }, [onCrosshairMove]);

  return (
    <div
      ref={containerRef}
      className="h-full w-full"
      style={minHeight != null ? { minHeight } : undefined}
    />
  );
}
