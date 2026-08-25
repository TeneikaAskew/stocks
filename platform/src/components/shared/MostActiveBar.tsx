import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

/**
 * Most-active ticker bar (marquee), mounted under the top nav on
 * Market-section routes (/live, /charts, /options, /signals) and /journal —
 * see AppShell.tsx for the route gate. Fed by GET /api/market/most-active
 * (hourly AlphaVantage TOP_GAINERS_LOSERS snapshots, gcp/fetchers/fetch_top_movers.py).
 *
 * Rule 3.7 discipline: `change_pct` / `volume` render "—" when null (never a
 * fabricated 0), and the sparkline only draws when the API supplied a real
 * ≥2-point `spark` series — it's never synthesized client-side.
 */

export interface MostActiveItem {
  ticker: string;
  rank: number;
  price: number | null;
  change_pct: number | null;
  volume: number | null;
  spark?: number[];
}

export interface MostActiveResponse {
  snapshot_ts: string | null;
  snapshot_date: string | null;
  label: string | null;
  items: MostActiveItem[];
}

const SPARK_WIDTH = 56;
const SPARK_HEIGHT = 18;

/** 312_000_000 -> "312M", 44_100_000 -> "44M", 981_000 -> "981K", null -> "—". */
export function formatCompactVolume(volume: number | null | undefined): string {
  if (volume === null || volume === undefined || !Number.isFinite(volume)) return '—';
  const abs = Math.abs(volume);
  if (abs >= 1_000_000_000) return `${Math.round(volume / 1_000_000_000)}B`;
  if (abs >= 1_000_000) return `${Math.round(volume / 1_000_000)}M`;
  if (abs >= 1_000) return `${Math.round(volume / 1_000)}K`;
  return String(Math.round(volume));
}

/** TRUE PERCENT convention: 2.31 -> "+2.31%", -1.5 -> "-1.50%", null -> "—". */
export function formatChangePct(pct: number | null | undefined): string {
  if (pct === null || pct === undefined || !Number.isFinite(pct)) return '—';
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
}

/**
 * Maps a price series onto a `width` x `height` canvas: min value -> bottom
 * (y = height), max value -> top (y = 0). Flat series render a mid-height
 * line rather than dividing by a zero range.
 */
export function sparklinePoints(values: number[], width: number, height: number): Array<[number, number]> {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min;
  const n = values.length;
  return values.map((v, i) => {
    const x = n === 1 ? 0 : (i / (n - 1)) * width;
    const y = range === 0 ? height / 2 : height - ((v - min) / range) * height;
    return [x, y];
  });
}

/** Bull/bear tone by first-vs-last point (matches the plan's "single stroke, bull/bear by first-vs-last"). */
export function isBullishSpark(values: number[]): boolean {
  return values[values.length - 1] >= values[0];
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
  useEffect(() => {
    const mql = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = () => setReduced(mql.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);
  return reduced;
}

function useMostActive() {
  return useQuery<MostActiveResponse>({
    queryKey: ['most-active'],
    queryFn: async () => {
      const r = await fetch('/api/market/most-active');
      if (!r.ok) throw new Error(`most-active ${r.status}`);
      return r.json();
    },
    staleTime: 10 * 60 * 1000,
    refetchInterval: 15 * 60 * 1000,
  });
}

function Sparkline({ values }: { values: number[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = SPARK_WIDTH * dpr;
    canvas.height = SPARK_HEIGHT * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, SPARK_WIDTH, SPARK_HEIGHT);

    const points = sparklinePoints(values, SPARK_WIDTH, SPARK_HEIGHT);
    if (points.length < 2) return;

    const rootStyle = getComputedStyle(document.documentElement);
    const bullColor = rootStyle.getPropertyValue('--bull').trim() || '#22c55e';
    const bearColor = rootStyle.getPropertyValue('--bear').trim() || '#ef4444';

    ctx.strokeStyle = isBullishSpark(values) ? bullColor : bearColor;
    ctx.lineWidth = 1.5;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.beginPath();
    points.forEach(([x, y], i) => {
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }, [values]);

  return (
    <canvas
      ref={canvasRef}
      width={SPARK_WIDTH}
      height={SPARK_HEIGHT}
      className="mab-spark"
      style={{ width: SPARK_WIDTH, height: SPARK_HEIGHT }}
      data-testid="most-active-spark"
    />
  );
}

function MostActiveItemChip({ item }: { item: MostActiveItem }) {
  const changeTone = item.change_pct == null ? '' : item.change_pct >= 0 ? ' text-bull' : ' text-bear';
  return (
    <div className="mab-item">
      <span className="mab-ticker">{item.ticker}</span>
      <span className="mab-price">{item.price != null ? `$${item.price.toFixed(2)}` : '—'}</span>
      <span className={`mab-change${changeTone}`}>{formatChangePct(item.change_pct)}</span>
      <span className="mab-volume">{formatCompactVolume(item.volume)} vol</span>
      {item.spark && item.spark.length >= 2 && <Sparkline values={item.spark} />}
    </div>
  );
}

export function MostActiveBar() {
  const { data } = useMostActive();
  const reducedMotion = usePrefersReducedMotion();
  const items = data?.items ?? [];

  // Decorative and Rule-3.7-honest: no skeleton flash, just hidden until
  // there's real data to show.
  if (items.length === 0) return null;

  // CSS marquee loops by translating the duplicated strip by -50%; a
  // single (non-duplicated) strip is used under reduced-motion so the
  // static overflow-x-auto fallback doesn't show every ticker twice.
  const renderItems = reducedMotion ? items : [...items, ...items];

  return (
    <div className="most-active-bar" data-testid="most-active-bar">
      <div className="mab-label">
        <span className="mab-label-title">Most Active</span>
        {data?.label && <span className="mab-label-sub">{data.label === 'live' ? 'Live' : data.label}</span>}
      </div>
      <div className={`mab-track-wrap${reducedMotion ? ' mab-track-wrap--static' : ''}`}>
        <div
          className={`mab-track${reducedMotion ? '' : ' mab-track--animate'}`}
          data-testid="most-active-track"
        >
          {renderItems.map((item, idx) => (
            <MostActiveItemChip key={`${item.ticker}-${item.rank}-${idx}`} item={item} />
          ))}
        </div>
      </div>
    </div>
  );
}
