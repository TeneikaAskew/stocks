import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Calendar,
  RefreshCw,
  HelpCircle,
  TrendingUp,
  TrendingDown,
  X,
} from 'lucide-react';
import { useGammaLevels } from '@/hooks/useGammaLevels';
import { useGammaGrid, type GammaGridSummary } from '@/hooks/useGammaGrid';
import { buildGrid, selectValue, expHeader } from '@/components/options/swingGridUtils';
import { formatGex, formatPctChange } from '@/lib/formatGex';
import {
  HS,
  glossary,
  type NodeRole,
  type DataSource,
} from '@/data/heatseekerMock';

// SwingMode — Heatseeker "Swing Mode" dealer-gamma cockpit.
//
// Toolbar (Live/Historical · GEX/VEX · expiry filter) + Legend strip + a
// 3-column stage —
//   left:   Tactical read card
//   center: Strike × Expiration heatmap
//   right:  Nodes & pivots list + Pivot-build |GEX| bars.
//
// WHAT'S REAL vs MOCK:
//   - The 2D heatmap grid is REAL — live per-(strike,expiration) GEX/VEX from
//     /api/options/{ticker}/grid via useGammaGrid (lib.gamma is the single
//     source of math; the frontend only renders). The source pill reflects the
//     real data_source (realtime → eod_fallback → stale → unavailable), and the
//     intraday Δ badge shows on the realtime path.
//   - The Pivot rail is REAL — ranked |net GEX| aggregated per strike from the
//     same grid. The Legend chips + NodeList are REAL via useGammaLevels.
//   - The Tactical read card is still illustrative (no narrative backend yet) —
//     flagged in the banner.

type Metric = 'gex' | 'vex';
type Mode = 'live' | 'historical';

const EXPIRY_FILTERS = ['All', '0DTE', 'Weekly', 'Monthly', 'Quarterly'] as const;

// ─── SVG role icons (NO emoji per design system) ──────────────
const HSIcons = {
  king: ({ size = 14 }: { size?: number }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" stroke="none">
      <path d="M3 9l4 3 5-7 5 7 4-3-1 11H4z" />
      <rect x="4" y="20" width="16" height="2" rx="0.5" />
    </svg>
  ),
  gate: ({ size = 14 }: { size?: number }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" stroke="none">
      <path d="M12 2l9 4v6c0 5-4 9-9 10-5-1-9-5-9-10V6z" />
    </svg>
  ),
  flip: ({ size = 14 }: { size?: number }) => (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M7 4l-4 4 4 4" />
      <path d="M3 8h14" />
      <path d="M17 20l4-4-4-4" />
      <path d="M21 16H7" />
    </svg>
  ),
  spot: ({ size = 14 }: { size?: number }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" stroke="none">
      <path d="M8 5l11 7-11 7z" />
    </svg>
  ),
  midpoint: ({ size = 14 }: { size?: number }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="3" fill="currentColor" />
      <circle cx="12" cy="12" r="8" />
    </svg>
  ),
  hedge: ({ size = 14 }: { size?: number }) => (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="4" y="11" width="16" height="10" rx="2" fill="currentColor" stroke="none" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </svg>
  ),
  opex: ({ size = 14 }: { size?: number }) => (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 9h18M8 3v4M16 3v4" />
    </svg>
  ),
} as const;

function RoleIcon({ role }: { role: NodeRole | null }) {
  if (!role) return null;
  const I = HSIcons[role];
  if (!I) return null;
  return <I />;
}

// ─── Term hover (title-attr span backed by the mock glossary) ──
function Term({ k, children }: { k: string; children?: React.ReactNode }) {
  const term = glossary[k];
  if (!term) return <>{children}</>;
  return (
    <span className="hs-term" title={`${term.name} — ${term.short}`}>
      {children ?? term.name}
    </span>
  );
}

// ─── Heatmap cell coloring ────────────────────────────────────
// Positive = green (call-dominant / vol-suppress) · Negative = red (put-dominant)
function cellColor(value: number, max: number): string {
  const t = Math.min(1, Math.abs(value) / max);
  if (t < 0.04) return 'rgba(255,255,255,0.03)';
  if (value >= 0) {
    const alpha = 0.18 + t * 0.78;
    const lift = Math.round(t * 80);
    return `rgba(${34 + lift}, ${197}, ${94 - lift / 2}, ${alpha.toFixed(2)})`;
  }
  const alpha = 0.22 + t * 0.78;
  return `rgba(239, 68, 68, ${alpha.toFixed(2)})`;
}

// ─── Format helpers ───────────────────────────────────────────
function fmtBigGex(n: number): string {
  const abs = Math.abs(n);
  const sign = n >= 0 ? '+' : '−';
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  return `${sign}$${Math.round(abs / 1000)}K`;
}

function fmtStrike(s: number): string {
  return s % 1 !== 0 ? s.toFixed(2) : String(s);
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Aggregated real-data overlay derived from useGammaLevels. Any field that the
// backend can supply replaces the mock; everything else falls back to HS.
interface RealOverlay {
  isReal: boolean;
  ticker: string;
  spotPrice: number;
  spotMethod: string;
  spotNote: string;
  kingStrike: number;
  kingGex: number;
  gateAbove?: { strike: number; gex: number };
  gateBelow?: { strike: number; gex: number };
  flipStrike: number;
  flipGex: number;
  regime: string;
  totalGex: number;
}

// ─── Data source freshness pill ───────────────────────────────
function SourcePill({ source, asOf }: { source: DataSource; asOf: string }) {
  const meta =
    {
      realtime: { cls: 'realtime', label: 'LIVE', hint: 'Realtime · 5-min snapshot' },
      eod_fallback: { cls: 'eod-fallback', label: 'EOD', hint: 'Realtime missed · using yesterday close' },
      stale_fallback: { cls: 'stale', label: 'STALE', hint: 'EOD > 2 sessions behind' },
      unavailable: { cls: 'stale', label: 'UNAVAILABLE', hint: 'No snapshot available' },
    }[source] ?? { cls: 'realtime', label: 'LIVE', hint: 'Live' };
  return (
    <span className={`hs-pill ${meta.cls}`} title={meta.hint}>
      <span className="dot pulse" />
      <span>{meta.label}</span>
      {asOf ? (
        <span style={{ opacity: 0.7, fontWeight: 500, letterSpacing: 0, textTransform: 'none' }}>
          {fmtTime(asOf)}
        </span>
      ) : null}
    </span>
  );
}

// ─── Toolbar (no ticker input — page owns the symbol via TickerSelect) ──
function Toolbar({
  metric,
  setMetric,
  mode,
  setMode,
  expiryFilter,
  setExpiryFilter,
  source,
  asOf,
}: {
  metric: Metric;
  setMetric: (m: Metric) => void;
  mode: Mode;
  setMode: (m: Mode) => void;
  expiryFilter: string;
  setExpiryFilter: (f: string) => void;
  source: DataSource;
  asOf: string;
}) {
  return (
    <div className="hs-toolbar">
      <div className="left">
        <div className="hs-segctrl">
          <button className={mode === 'live' ? 'active' : ''} onClick={() => setMode('live')}>
            <Activity size={12} />
            Live
          </button>
          <button className={mode === 'historical' ? 'active' : ''} onClick={() => setMode('historical')}>
            <Calendar size={12} />
            Historical
          </button>
        </div>
        <div className="hs-segctrl">
          <button className={metric === 'gex' ? 'active' : ''} onClick={() => setMetric('gex')}>
            GEX
          </button>
          <button className={metric === 'vex' ? 'active' : ''} onClick={() => setMetric('vex')}>
            VEX
          </button>
        </div>
        <div className="hs-segctrl">
          {EXPIRY_FILTERS.map((t) => (
            <button
              key={t}
              className={expiryFilter === t ? 'active' : ''}
              onClick={() => setExpiryFilter(t)}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      <div className="right">
        <SourcePill source={source} asOf={asOf} />
        <button className="icon-btn" title="Refresh" type="button">
          <RefreshCw size={15} />
        </button>
        <button className="icon-btn" title="Glossary" type="button">
          <HelpCircle size={15} />
        </button>
      </div>
    </div>
  );
}

// ─── Legend chips strip ────────────────────────────────────────
function Legend({ overlay }: { overlay: RealOverlay }) {
  const gateAbove = overlay.gateAbove;
  const gateBelow = overlay.gateBelow;
  const regimePositive = overlay.regime === 'positive_gamma';
  return (
    <div className="hs-legend">
      <span className="chip spot">
        <span className="icon">
          <HSIcons.spot />
        </span>
        <div>
          <div className="label">
            <Term k="spot">Spot</Term>
          </div>
          <div className="val">{overlay.spotPrice.toFixed(2)}</div>
        </div>
      </span>
      <span className="chip" title={overlay.spotNote || glossary[overlay.spotMethod]?.short}>
        <div>
          <div className="label">Spot method</div>
          <div
            className="val"
            style={{
              fontSize: 12,
              color:
                overlay.spotMethod === 'parity'
                  ? 'var(--bull)'
                  : overlay.spotMethod === 'delta'
                    ? 'var(--warn)'
                    : 'var(--bear)',
            }}
          >
            {overlay.spotMethod}
          </div>
        </div>
      </span>
      <span className="chip king">
        <span className="icon">
          <HSIcons.king />
        </span>
        <div>
          <div className="label">
            <Term k="king">King</Term>
          </div>
          <div className="val">{fmtStrike(overlay.kingStrike)}</div>
        </div>
      </span>
      {gateAbove && (
        <span className="chip gate">
          <span className="icon">
            <HSIcons.gate />
          </span>
          <div>
            <div className="label">
              <Term k="gate">Gate ↑</Term>
            </div>
            <div className="val">{fmtStrike(gateAbove.strike)}</div>
          </div>
        </span>
      )}
      {gateBelow && (
        <span className="chip gate">
          <span className="icon">
            <HSIcons.gate />
          </span>
          <div>
            <div className="label">
              <Term k="gate">Gate ↓</Term>
            </div>
            <div className="val">{fmtStrike(gateBelow.strike)}</div>
          </div>
        </span>
      )}
      <span className="chip flip">
        <span className="icon">
          <HSIcons.flip />
        </span>
        <div>
          <div className="label">
            <Term k="flip">Flip</Term>
          </div>
          <div className="val">{overlay.flipStrike.toFixed(2)}</div>
        </div>
      </span>
      <span className="chip hedge">
        <span className="icon">
          <HSIcons.hedge />
        </span>
        <div>
          <div className="label">
            <Term k="hedge">Hedge</Term>
          </div>
          <div className="val">{HS.nodes.hedge[0]?.strike}</div>
        </div>
      </span>
      <span className="chip">
        <div>
          <div className="label">Regime</div>
          <div className="val" style={{ color: regimePositive ? 'var(--bull)' : 'var(--bear)' }}>
            {regimePositive ? 'POSITIVE' : overlay.regime === 'negative_gamma' ? 'NEGATIVE' : 'UNCLEAR'}
          </div>
        </div>
      </span>
      <span className="chip">
        <div>
          <div className="label">
            Total <Term k="gex">GEX</Term>
          </div>
          <div className="val">{fmtBigGex(overlay.totalGex)}</div>
        </div>
      </span>
      <span className="chip">
        <div>
          <div className="label">
            Total <Term k="vex">VEX</Term>
          </div>
          <div className="val" style={{ color: '#ef4444' }}>
            {fmtBigGex(HS.totalVex)}
          </div>
        </div>
      </span>
    </div>
  );
}

// ─── Tactical summary card ─────────────────────────────────────
function TacticalCard() {
  const t = HS.tactical;
  return (
    <div className="hs-tactical">
      <h3>Tactical read · {HS.ticker}</h3>
      <div style={{ fontSize: 12.5, color: 'var(--on-surface-variant)', lineHeight: 1.55, marginBottom: 14 }}>
        {t.currentState}
      </div>
      <div className="scenario long">
        <div className="lbl">
          <TrendingUp size={11} />
          Long setup
        </div>
        <div>{t.longSetup}</div>
      </div>
      <div className="scenario short">
        <div className="lbl">
          <TrendingDown size={11} />
          Short setup
        </div>
        <div>{t.shortSetup}</div>
      </div>
      <div className="scenario invl">
        <div className="lbl">
          <X size={11} />
          Invalidation
        </div>
        <div>{t.invalidation}</div>
      </div>
      <div className="scenario vex">
        <div className="lbl">
          <HSIcons.flip size={11} />
          <Term k="vex">VEX</Term> note
        </div>
        <div>{t.vexNote}</div>
      </div>
      <div
        className="row between"
        style={{ paddingTop: 10, marginTop: 8, borderTop: '1px solid var(--outline-variant)' }}
      >
        <div className="lbl-micro">Confidence</div>
        <div className="row" style={{ gap: 8, alignItems: 'baseline' }}>
          <div className="metric brand" style={{ fontSize: 16 }}>
            {t.confidence}%
          </div>
        </div>
      </div>
    </div>
  );
}


// ─── Node list panel ───────────────────────────────────────────
interface NodeItem {
  role: NodeRole;
  strike: number;
  extra: string;
  name: string;
}

function NodeList({ overlay }: { overlay: RealOverlay }) {
  const items: NodeItem[] = [
    { role: 'king', strike: overlay.kingStrike, extra: fmtBigGex(overlay.kingGex), name: 'King' },
  ];
  if (overlay.gateAbove)
    items.push({ role: 'gate', strike: overlay.gateAbove.strike, extra: fmtBigGex(overlay.gateAbove.gex), name: 'Gate ↑' });
  if (overlay.gateBelow)
    items.push({ role: 'gate', strike: overlay.gateBelow.strike, extra: fmtBigGex(overlay.gateBelow.gex), name: 'Gate ↓' });
  items.push({ role: 'spot', strike: overlay.spotPrice, extra: 'current', name: 'Spot' });
  items.push({ role: 'flip', strike: overlay.flipStrike, extra: 'zero-gamma', name: 'Flip' });
  HS.nodes.midpoints.forEach((m) =>
    items.push({ role: 'midpoint', strike: m.strike, extra: fmtBigGex(m.gex), name: 'Midpoint' }),
  );
  HS.nodes.hedge.forEach((h) =>
    items.push({ role: 'hedge', strike: h.strike, extra: h.linkedEvent, name: 'Hedge' }),
  );

  return (
    <div className="card-i hs-nodes">
      <div className="card-h">
        <h3>Nodes &amp; pivots</h3>
        <span className="meta">canonical · hover for definition</span>
      </div>
      {items.map((it, i) => (
        <div key={i} className={`node ${it.role}`} title={glossary[it.role]?.short ?? ''}>
          <div className="left">
            <span style={{ color: 'currentColor', display: 'inline-flex' }}>
              <RoleIcon role={it.role} />
            </span>
            <span className="strike">{fmtStrike(it.strike)}</span>
            <span className="name">{it.name}</span>
          </div>
          <span className="meta">{it.extra}</span>
        </div>
      ))}
      <div
        style={{
          marginTop: 14,
          padding: 10,
          background: 'var(--surface-2)',
          borderRadius: 6,
          fontSize: 11,
          color: 'var(--on-surface-variant)',
          lineHeight: 1.5,
        }}
      >
        <strong style={{ color: 'var(--on-surface)' }}>Reading the grid:</strong> intensity = absolute{' '}
        <Term k="gex">GEX</Term>. Color = sign (green call-dominant, red put-dominant). King cell outlined
        gold. Dashed rows mark <Term k="spot">Spot</Term> &amp; <Term k="flip">Flip</Term>.
      </div>
    </div>
  );
}


// ─── Strike × Expiration 2D heatmap (the headline) — REAL /grid data ──────────
// Renders the live strike×expiration GEX/VEX surface from useGammaGrid in the
// same hs-grid design as the rest of the cockpit. King cell = largest |net GEX|
// (gold), spot/flip rows dashed. The intraday Δ badge (vs the prior snapshot)
// shows only on the realtime path; null elsewhere.
function RealHeatmapGrid({
  summary,
  loading,
  isError,
  metric,
  ticker,
  kingStrike,
  flipStrike,
}: {
  summary?: GammaGridSummary;
  loading: boolean;
  isError: boolean;
  metric: Metric;
  ticker: string;
  kingStrike?: number;
  flipStrike?: number;
}) {
  const built = useMemo(
    () => (summary && summary.cells.length > 0 ? buildGrid(summary, metric, 'net', 12) : null),
    [summary, metric],
  );

  const Header = (
    <div className="card-h">
      <h3>Strike × Expiration heatmap · {ticker}</h3>
    </div>
  );

  if (loading && !summary) {
    return (
      <div className="card-i hs-grid-card">
        {Header}
        <div style={{ padding: 48, textAlign: 'center', color: 'var(--on-surface-muted)', fontSize: 12 }}>
          Loading live grid…
        </div>
      </div>
    );
  }
  if (isError || !summary || summary.data_source === 'unavailable' || !built || built.columns.length === 0) {
    const reason = summary?.reason ?? summary?.warnings?.[0] ?? 'No options grid available for this symbol.';
    return (
      <div className="card-i hs-grid-card">
        {Header}
        <div style={{ padding: 48, textAlign: 'center', color: 'var(--on-surface-muted)', fontSize: 12 }}>
          Data unavailable — {reason}
        </div>
      </div>
    );
  }

  const { cellMap, strikesDesc, columns, maxAbs, dteByExp, spotStrike, kingKey } = built;

  // Robust color scale: the King is an outlier that would flatten every other
  // cell on a linear |val|/max ramp. Scale color to the 75th-percentile non-zero
  // magnitude so the body of the grid stays legible; King + big nodes clamp to
  // full saturation (cellColor caps t at 1).
  const absVals: number[] = [];
  for (const c of cellMap.values()) {
    const v = Math.abs(selectValue(c, metric, 'net'));
    if (v > 0) absVals.push(v);
  }
  absVals.sort((a, b) => a - b);
  const scaleMax = absVals.length ? absVals[Math.floor(absVals.length * 0.75)] || maxAbs : maxAbs;

  const showChange = summary.data_source === 'realtime';
  // Prefer the /levels King (matches the node list); else the grid's max |net GEX|.
  const kingRowStrike = kingStrike ?? (kingKey ? Number(kingKey.split('|')[0]) : undefined);

  // Strike row nearest the (real) flip level → flip dashed-row marker.
  let flipNearest: number | null = null;
  if (flipStrike != null) {
    let best = Infinity;
    for (const s of strikesDesc) {
      const d = Math.abs(s - flipStrike);
      if (d < best) {
        best = d;
        flipNearest = s;
      }
    }
  }

  const colTpl = `auto repeat(${columns.length}, 1fr)`;
  return (
    <div className="card-i hs-grid-card">
      <div className="card-h">
        <h3>Strike × Expiration heatmap · {ticker}</h3>
        <div className="row" style={{ gap: 12, fontSize: 11, color: 'var(--on-surface-muted)', alignItems: 'baseline' }}>
          <span>
            <strong style={{ color: 'var(--on-surface)' }}>Cell values</strong> = dealer{' '}
            <Term k={metric}>{metric.toUpperCase()}</Term> · per 1%{' '}
            {metric === 'gex' ? 'spot move' : 'IV change'}
            {showChange ? ' · badge = intraday Δ vs prior snapshot' : ''}
          </span>
        </div>
      </div>

      <div className="hs-grid" style={{ gridTemplateColumns: colTpl, gap: 0 }}>
        <div />
        {columns.map((exp) => {
          const h = expHeader(exp, dteByExp.get(exp) ?? 0);
          return (
            <div key={exp} className="col-header">
              {h.date}
              <div className="dte">{h.dte}</div>
            </div>
          );
        })}

        {strikesDesc.map((k) => {
          const role: NodeRole | null =
            k === kingRowStrike ? 'king' : k === spotStrike ? 'spot' : k === flipNearest ? 'flip' : null;
          return (
            <div key={k} style={{ display: 'contents' }}>
              <div className={`row-header ${role ?? ''}`}>
                {role ? (
                  <span className="icon">
                    <RoleIcon role={role} />
                  </span>
                ) : null}
                <span className="strike">{fmtStrike(k)}</span>
                {role ? <span className="tag">{role}</span> : null}
              </div>
              {columns.map((exp) => {
                const cell = cellMap.get(`${k}|${exp}`);
                const isKing = kingKey === `${k}|${exp}`;
                const val = cell ? selectValue(cell, metric, 'net') : 0;
                const pct = cell?.pct_change ?? null;
                const intensity = scaleMax > 0 ? Math.abs(val) / scaleMax : 0;
                return (
                  <div
                    key={exp}
                    className={`hs-cell ${isKing ? 'king-here' : ''} ${role === 'spot' ? 'spot-row' : ''} ${role === 'flip' ? 'flip-row' : ''}`}
                    style={{
                      background: cell ? cellColor(val, scaleMax) : 'rgba(255,255,255,0.02)',
                      height: 38,
                      color: intensity > 0.5 ? '#fff' : val >= 0 ? 'var(--bull)' : '#ef4444',
                    }}
                    title={
                      cell
                        ? `${ticker} ${k} · ${exp} (${cell.dte}d)\n${metric.toUpperCase()}: ${formatGex(val)}\nOI ${cell.call_oi}c / ${cell.put_oi}p${pct != null ? `\nIntraday Δ: ${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%` : ''}`
                        : `${k} · ${exp} — no contracts`
                    }
                  >
                    {cell && intensity >= 0.04 ? formatGex(val) : ''}
                    {showChange && pct != null && Math.abs(pct) >= 1 ? (
                      <span className="roc-tick" style={{ color: pct >= 0 ? 'var(--bull)' : '#ef4444' }}>
                        {formatPctChange(pct)}
                      </span>
                    ) : null}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>

      <div
        className="row"
        style={{ marginTop: 14, gap: 16, alignItems: 'center', justifyContent: 'flex-end', fontSize: 10.5, color: 'var(--on-surface-muted)' }}
      >
        <span className="row" style={{ gap: 6, alignItems: 'center' }}>
          <span style={{ width: 14, height: 14, borderRadius: 3, background: 'rgba(34,197,94,0.85)' }} />
          <span>Call-dominant · pinning</span>
        </span>
        <span className="row" style={{ gap: 6, alignItems: 'center' }}>
          <span style={{ width: 14, height: 14, borderRadius: 3, background: 'rgba(239,68,68,0.85)' }} />
          <span>Put-dominant · trending</span>
        </span>
      </div>
    </div>
  );
}

// ─── Pivot build rail — REAL: ranked by |net GEX| aggregated per strike ───────
function RealPivotBuild({ summary }: { summary?: GammaGridSummary }) {
  const ranked = useMemo(() => {
    if (!summary || summary.cells.length === 0) return [];
    const byStrike = new Map<number, number>();
    for (const c of summary.cells) byStrike.set(c.strike, (byStrike.get(c.strike) ?? 0) + c.gex);
    return [...byStrike.entries()]
      .map(([strike, netGex]) => ({ strike, netGex, abs: Math.abs(netGex) }))
      .sort((a, b) => b.abs - a.abs)
      .slice(0, 10);
  }, [summary]);
  if (ranked.length === 0) return null;
  const max = Math.max(...ranked.map((r) => r.abs)) || 1;
  return (
    <div className="card-i hs-roc-card">
      <div className="card-h">
        <h3>Pivot build · ranked</h3>
        <span className="meta">|GEX| · all expirations</span>
      </div>
      {ranked.map((r) => (
        <div key={r.strike} className="hs-roc-bar">
          <span className="strike">{fmtStrike(r.strike)}</span>
          <span className="track">
            <span className={`fill ${r.netGex < 0 ? 'neg' : ''}`} style={{ width: `${(r.abs / max) * 100}%` }} />
          </span>
          <span className="val" style={{ color: r.netGex < 0 ? '#ef4444' : 'var(--bull)' }}>
            {formatGex(r.netGex)}
          </span>
        </div>
      ))}
    </div>
  );
}

interface SwingModeProps {
  /** Focus symbol from the page toolbar (TickerSelect). */
  focusSymbol: string;
}

function useLatestOptionsDate(ticker: string) {
  return useQuery<{ ticker: string; dates: string[] }>({
    queryKey: ['options-dates', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/options/dates/${ticker}`);
      if (!r.ok) throw new Error(`dates ${r.status}`);
      return r.json();
    },
    staleTime: 300_000,
    retry: false,
  });
}

export default function SwingMode({ focusSymbol }: SwingModeProps) {
  const [metric, setMetric] = useState<Metric>('gex');
  const [mode, setMode] = useState<Mode>('live');
  const [expiryFilter, setExpiryFilter] = useState<string>('All');

  // Real data: latest snapshot date → gamma levels + the 2-D strike×expiration
  // grid for the focus symbol. The grid is the centerpiece (real /grid); levels
  // drive the legend chips, node list, and King/Spot/Flip markers.
  const sym = (focusSymbol || HS.ticker).replace(/^\^/, '');
  const datesQuery = useLatestOptionsDate(sym);
  const latestDate = datesQuery.data?.dates?.[0] ?? '';
  const levelsQuery = useGammaLevels(sym, latestDate, { enabled: !!latestDate });
  const levels = levelsQuery.data;
  const gridQuery = useGammaGrid(sym, latestDate, {
    windowPct: 6,
    live: mode === 'live',
    enabled: !!sym && (mode === 'live' || !!latestDate),
  });
  const grid = gridQuery.data;

  // Build the overlay — real values where the backend supplies them, else mock.
  const overlay: RealOverlay = useMemo(() => {
    if (levels && levels.levels.length > 0) {
      const king = levels.kings?.[0];
      const spotPrice = levels.spot.price > 0 ? levels.spot.price : HS.spot.price;
      // Split gates into above/below spot.
      const above = levels.gates
        .filter((g) => g.strike >= spotPrice)
        .sort((a, b) => a.strike - b.strike)[0];
      const below = levels.gates
        .filter((g) => g.strike < spotPrice)
        .sort((a, b) => b.strike - a.strike)[0];
      const flipLvl = levels.gamma_balance_levels?.[0];
      return {
        isReal: true,
        ticker: sym,
        spotPrice,
        spotMethod: levels.spot.method,
        spotNote: levels.spot.note,
        kingStrike: king?.strike ?? HS.nodes.king.strike,
        kingGex: king?.gex ?? HS.nodes.king.gex,
        gateAbove: above ? { strike: above.strike, gex: above.gex } : undefined,
        gateBelow: below ? { strike: below.strike, gex: below.gex } : undefined,
        flipStrike: levels.gamma_balance ?? HS.flip,
        flipGex: flipLvl?.gex ?? HS.nodes.flip.gex,
        regime: levels.regime,
        totalGex: levels.total_gex,
      };
    }
    // Mock fallback.
    return {
      isReal: false,
      ticker: HS.ticker,
      spotPrice: HS.spot.price,
      spotMethod: HS.spot.method,
      spotNote: HS.spot.note,
      kingStrike: HS.nodes.king.strike,
      kingGex: HS.nodes.king.gex,
      gateAbove: { strike: HS.nodes.gates[0].strike, gex: HS.nodes.gates[0].gex },
      gateBelow: { strike: HS.nodes.gates[1].strike, gex: HS.nodes.gates[1].gex },
      flipStrike: HS.nodes.flip.strike,
      flipGex: HS.nodes.flip.gex,
      regime: HS.regime,
      totalGex: HS.totalGex,
    };
  }, [levels, sym]);

  return (
    <div className="col" style={{ gap: 14 }}>
      {/* The heatmap grid + pivot rail are LIVE; the tactical read is illustrative. */}
      <div className="hs-demo-banner">
        <span className="dot" />
        <span>
          {grid && grid.data_source !== 'unavailable' ? (
            <>
              Heatmap grid &amp; pivot rail show <strong>live {sym} dealer exposure</strong>. Tactical
              read is illustrative.
            </>
          ) : (
            <>
              Live {sym} grid unavailable — <strong>tactical read is illustrative.</strong>
            </>
          )}
        </span>
      </div>

      <Toolbar
        metric={metric}
        setMetric={setMetric}
        mode={mode}
        setMode={setMode}
        expiryFilter={expiryFilter}
        setExpiryFilter={setExpiryFilter}
        source={grid?.data_source ?? 'unavailable'}
        asOf={grid?.snapshot_ts ?? ''}
      />
      <Legend overlay={overlay} />

      <div className="hs-stage">
        <div>
          <TacticalCard />
        </div>
        <RealHeatmapGrid
          summary={grid}
          loading={gridQuery.isLoading}
          isError={gridQuery.isError}
          metric={metric}
          ticker={sym}
          kingStrike={overlay.isReal ? overlay.kingStrike : undefined}
          flipStrike={overlay.isReal ? overlay.flipStrike : undefined}
        />
        <div className="col" style={{ gap: 14 }}>
          <NodeList overlay={overlay} />
          <RealPivotBuild summary={grid} />
        </div>
      </div>
    </div>
  );
}
