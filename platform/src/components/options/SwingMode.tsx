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
import {
  HS,
  glossary,
  type NodeRole,
  type HSExpiration,
  type DataSource,
} from '@/data/heatseekerMock';

// SwingMode — Heatseeker "Swing Mode" dealer-gamma cockpit.
//
// A faithful port of the design's dealer-gamma.jsx: Toolbar (Live/Historical ·
// GEX/VEX · expiry filter) + Legend strip + a 3-column stage —
//   left:   Tactical read card
//   center: Strike × Expiration heatmap (click a date header to drill into a
//           per-expiration bar chart)
//   right:  Nodes & pivots list + Pivot-build |GEX| bars.
//
// WHAT'S REAL vs MOCK:
//   - The 2D grid, tactical read, drill-in detail and pivot-build are MOCK
//     (there is no per-expiration dealer-exposure backend endpoint) — flagged
//     by a persistent demo pill.
//   - The Legend chips + NodeList are overlaid with REAL values from
//     /api/options/{ticker}/{date}/levels via useGammaLevels when that data is
//     available for the focus symbol, falling back to the mock otherwise.

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
function fmtGexK(n: number): string {
  const sign = n >= 0 ? '+' : '−';
  const abs = Math.abs(n);
  if (abs >= 1000) return `${sign}${(abs / 1000).toFixed(1)}M`;
  return `${sign}${Math.round(abs)}K`;
}
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
      <span style={{ opacity: 0.7, fontWeight: 500, letterSpacing: 0, textTransform: 'none' }}>
        {fmtTime(asOf)}
      </span>
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
}: {
  metric: Metric;
  setMetric: (m: Metric) => void;
  mode: Mode;
  setMode: (m: Mode) => void;
  expiryFilter: string;
  setExpiryFilter: (f: string) => void;
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
        <SourcePill source={HS.dataSource} asOf={HS.asOf} />
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

interface GridTip {
  x: number;
  y: number;
  k: number;
  exp: HSExpiration;
  val: number;
  roc: number;
  role: NodeRole | null;
}

// ─── Strike × Expiration 2D heatmap (the headline) ────────────
function HeatmapGrid({
  metric,
  onSelectExp,
}: {
  metric: Metric;
  onSelectExp: (iso: string) => void;
}) {
  const grid = metric === 'vex' ? HS.vexGrid : HS.gexGrid;
  const rocGrid = HS.rocGrid;
  const max = Math.max(...grid.flat().map(Math.abs));

  // King cell (highest |gex|) within window.
  let kingI = 0;
  let kingJ = 0;
  let kingMag = 0;
  HS.gexGrid.forEach((row, i) =>
    row.forEach((v, j) => {
      if (Math.abs(v) > kingMag) {
        kingMag = Math.abs(v);
        kingI = i;
        kingJ = j;
      }
    }),
  );

  const roleByStrike: Record<number, NodeRole> = {};
  HS.collapsed.forEach((c) => {
    if (c.role) roleByStrike[c.strike] = c.role;
  });

  const [tip, setTip] = useState<GridTip | null>(null);

  const colTpl = `auto repeat(${HS.expirations.length}, 1fr)`;
  return (
    <div className="card-i hs-grid-card">
      <div className="card-h">
        <h3>Strike × Expiration heatmap · {HS.ticker}</h3>
        <div className="row" style={{ gap: 12, fontSize: 11, color: 'var(--on-surface-muted)', alignItems: 'baseline' }}>
          <span>
            <strong style={{ color: 'var(--on-surface)' }}>Cell values</strong> = dealer{' '}
            <Term k={metric}>{metric.toUpperCase()}</Term> in $K ·{' '}
            per 1% {metric === 'gex' ? 'spot move' : 'IV change'} ·{' '}
            <strong style={{ color: 'var(--brand)' }}>click any date header to drill in</strong>
          </span>
        </div>
      </div>

      <div className="hs-grid" style={{ gridTemplateColumns: colTpl, gap: 0 }}>
        <div />
        {HS.expirations.map((e) => (
          <div
            key={e.iso}
            className={`col-header ${e.tags.includes('opex') ? 'opex' : ''}`}
            style={{ cursor: 'pointer' }}
            onClick={() => onSelectExp(e.iso)}
            title="Click to drill in"
          >
            {e.label}
            <div className="dte">
              {e.dte}d · {new Date(e.iso).toLocaleDateString([], { month: 'short', day: 'numeric' })}
            </div>
          </div>
        ))}

        {HS.strikes.map((k, i) => {
          const role = roleByStrike[k] ?? null;
          const isSpot = role === 'spot';
          const isFlip = role === 'flip';
          return (
            <div key={k} style={{ display: 'contents' }}>
              <div className={`row-header ${role ?? ''}`}>
                {role ? (
                  <span className="icon">
                    <RoleIcon role={role} />
                  </span>
                ) : null}
                <span className="strike">{k}</span>
                {role ? <span className="tag">{role}</span> : null}
              </div>
              {HS.expirations.map((e, j) => {
                const val = grid[i][j];
                const roc = rocGrid[i][j];
                const isKing = i === kingI && j === kingJ;
                return (
                  <div
                    key={e.iso}
                    className={`hs-cell ${isKing ? 'king-here' : ''} ${isSpot ? 'spot-row' : ''} ${isFlip ? 'flip-row' : ''}`}
                    style={{
                      background: cellColor(val, max),
                      height: 38,
                      color: Math.abs(val) / max > 0.5 ? '#fff' : val >= 0 ? 'var(--bull)' : '#ef4444',
                    }}
                    onMouseEnter={(ev) => {
                      const r = ev.currentTarget.getBoundingClientRect();
                      setTip({ x: r.right + 8, y: r.top, k, exp: e, val, roc, role });
                    }}
                    onMouseLeave={() => setTip(null)}
                  >
                    {Math.abs(val) >= 40 ? (val >= 0 ? '+' : '−') + Math.round(Math.abs(val)) : ''}
                    {Math.abs(roc) >= 20 ? (
                      <span className="roc-tick" style={{ color: roc >= 0 ? 'var(--bull)' : '#ef4444' }}>
                        {roc >= 0 ? '▲' : '▼'}
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
        style={{
          marginTop: 14,
          gap: 16,
          alignItems: 'center',
          justifyContent: 'flex-end',
          fontSize: 10.5,
          color: 'var(--on-surface-muted)',
        }}
      >
        <span>Sign convention:</span>
        <span className="row" style={{ gap: 6, alignItems: 'center' }}>
          <span style={{ width: 14, height: 14, borderRadius: 3, background: 'rgba(34,197,94,0.85)' }} />
          <span>Call-dominant · pinning</span>
        </span>
        <span className="row" style={{ gap: 6, alignItems: 'center' }}>
          <span style={{ width: 14, height: 14, borderRadius: 3, background: 'rgba(239,68,68,0.85)' }} />
          <span>Put-dominant · trending</span>
        </span>
        <span style={{ marginLeft: 16 }}>▲ ▼ = Δ {metric.toUpperCase()} last hour</span>
      </div>

      {tip && (
        <div className="hs-tip" style={{ left: tip.x, top: tip.y }}>
          <h4>
            {HS.ticker} · {tip.k}
            <span className="dim" style={{ marginLeft: 8, fontWeight: 400 }}>
              {tip.exp.label} · {tip.exp.dte}d
            </span>
          </h4>
          <div className="kv">
            <span className="k">{metric.toUpperCase()}</span>
            <span className={`v ${tip.val >= 0 ? 'pos' : 'neg'}`}>{fmtGexK(tip.val)}</span>
          </div>
          <div className="kv">
            <span className="k">Δ last hr</span>
            <span className={`v ${tip.roc >= 0 ? 'pos' : 'neg'}`}>
              {tip.roc >= 0 ? '+' : ''}
              {tip.roc}K
            </span>
          </div>
          {tip.role && (
            <div className="kv">
              <span className="k">Role</span>
              <span className="v" style={{ color: 'var(--brand)' }}>
                {tip.role.toUpperCase()}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Drill-in: per-expiration bar chart ────────────────────────
function ExpirationDrillIn({
  expIso,
  metric,
  onClose,
}: {
  expIso: string;
  metric: Metric;
  onClose: () => void;
}) {
  const exp = HS.expirations.find((e) => e.iso === expIso);
  const rows = HS.detail[expIso];
  if (!exp || !rows) return null;

  const roleByStrike: Record<number, NodeRole> = {};
  HS.collapsed.forEach((c) => {
    if (c.role) roleByStrike[c.strike] = c.role;
  });

  let kingStrike: number | null = null;
  let kingMag = 0;
  rows.forEach((r) => {
    if (Math.abs(r.gex) > kingMag) {
      kingMag = Math.abs(r.gex);
      kingStrike = r.strike;
    }
  });

  const ordered = [...rows].sort((a, b) => b.strike - a.strike);
  const max = Math.max(...rows.map((r) => Math.abs(metric === 'vex' ? r.vex : r.gex)));
  const sumCallOi = rows.reduce((s, r) => s + r.callOi, 0);
  const sumPutOi = rows.reduce((s, r) => s + r.putOi, 0);
  const sumCallVol = rows.reduce((s, r) => s + r.callVol, 0);
  const sumPutVol = rows.reduce((s, r) => s + r.putVol, 0);
  const sumGex = rows.reduce((s, r) => s + (metric === 'vex' ? r.vex : r.gex), 0);
  const avgIv = +(rows.reduce((s, r) => s + r.iv, 0) / rows.length).toFixed(1);

  return (
    <div className="card-i hs-grid-card">
      <div className="card-h">
        <div className="row" style={{ gap: 12, alignItems: 'baseline' }}>
          <h3 style={{ margin: 0 }}>
            {HS.ticker} · {exp.label} drill-in
          </h3>
          <span className="meta">
            {exp.dte}d · expires{' '}
            {new Date(exp.iso).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })}
            {exp.tags.includes('opex') ? ' · OPEX' : ''}
          </span>
        </div>
        <button className="btn ghost" style={{ fontSize: 11 }} onClick={onClose} type="button">
          <X size={11} /> Back to heatmap
        </button>
      </div>

      <div className="hs-drill-summary">
        <div className="stat">
          <span className="k">Net {metric.toUpperCase()}</span>
          <span className={`v ${sumGex >= 0 ? 'pos' : 'neg'}`}>
            {sumGex >= 0 ? '+' : '−'}
            {Math.round(Math.abs(sumGex))}K
          </span>
        </div>
        <div className="stat">
          <span className="k">King strike</span>
          <span className="v" style={{ color: '#ffb800' }}>
            {kingStrike}
          </span>
        </div>
        <div className="stat">
          <span className="k">Call OI</span>
          <span className="v pos">{(sumCallOi / 1000).toFixed(1)}K</span>
        </div>
        <div className="stat">
          <span className="k">Put OI</span>
          <span className="v neg">{(sumPutOi / 1000).toFixed(1)}K</span>
        </div>
        <div className="stat">
          <span className="k">Call vol</span>
          <span className="v pos">{(sumCallVol / 1000).toFixed(1)}K</span>
        </div>
        <div className="stat">
          <span className="k">Put vol</span>
          <span className="v neg">{(sumPutVol / 1000).toFixed(1)}K</span>
        </div>
        <div className="stat">
          <span className="k">P/C vol</span>
          <span className="v">{(sumPutVol / Math.max(1, sumCallVol)).toFixed(2)}</span>
        </div>
        <div className="stat">
          <span className="k">Avg IV</span>
          <span className="v brand">{avgIv}%</span>
        </div>
      </div>

      <div className="hs-bars">
        <div className="hs-bars-head">
          <span>Strike</span>
          <span style={{ textAlign: 'center' }}>{metric.toUpperCase()} ($K) · dealer exposure</span>
          <span style={{ textAlign: 'right' }}>Call OI</span>
          <span style={{ textAlign: 'right' }}>Put OI</span>
          <span style={{ textAlign: 'right' }}>Call vol</span>
          <span style={{ textAlign: 'right' }}>Put vol</span>
          <span style={{ textAlign: 'right' }}>IV</span>
        </div>

        {ordered.map((r) => {
          const role = roleByStrike[r.strike];
          const isKing = r.strike === kingStrike;
          const val = metric === 'vex' ? r.vex : r.gex;
          const pct = max > 0 ? (Math.abs(val) / max) * 50 : 0;
          const pos = val >= 0;
          const labelTxt = val >= 0 ? `+${Math.round(val)}K` : `−${Math.round(Math.abs(val))}K`;
          const labelInside = pct > 16;
          return (
            <div className="hs-bars-row" key={r.strike}>
              <div
                className="hs-bar-strike"
                style={{
                  color:
                    role === 'spot'
                      ? 'var(--brand)'
                      : role === 'king' || isKing
                        ? '#ffb800'
                        : role === 'flip'
                          ? '#ef4444'
                          : role === 'gate'
                            ? '#ef4444'
                            : role === 'hedge'
                              ? '#6ec3f2'
                              : role === 'midpoint'
                                ? 'var(--on-surface-variant)'
                                : 'var(--on-surface)',
                }}
              >
                {role && (
                  <span className="icon">
                    <RoleIcon role={role} />
                  </span>
                )}
                {!role && isKing && (
                  <span className="icon" style={{ color: '#ffb800' }}>
                    <HSIcons.king size={12} />
                  </span>
                )}
                <span>{r.strike}</span>
                {role && <span className="role-tag">{role}</span>}
              </div>

              <div className="hs-bar-track">
                <div className="center" style={{ left: '50%' }} />
                {pos ? (
                  <div
                    className="fill pos"
                    style={{ left: '50%', width: `${pct}%`, border: isKing ? '1px solid #ffb800' : 'none' }}
                  />
                ) : (
                  <div className="fill neg" style={{ right: '50%', width: `${pct}%` }} />
                )}
                <span
                  className={`label ${labelInside ? '' : 'outside'}`}
                  style={{
                    [pos ? 'left' : 'right']: labelInside
                      ? `calc(50% + 4px)`
                      : `calc(50% + ${pct + 1}%)`,
                  }}
                >
                  {labelTxt}
                </span>
              </div>

              <div className="hs-oi-cell call" style={{ textAlign: 'right', alignItems: 'flex-end' }}>
                <span className="v">{r.callOi.toLocaleString()}</span>
                <span className="s">contracts</span>
              </div>
              <div className="hs-oi-cell put" style={{ textAlign: 'right', alignItems: 'flex-end' }}>
                <span className="v">{r.putOi.toLocaleString()}</span>
                <span className="s">contracts</span>
              </div>
              <div style={{ textAlign: 'right', fontWeight: 600, color: 'var(--bull)' }}>
                {r.callVol.toLocaleString()}
              </div>
              <div style={{ textAlign: 'right', fontWeight: 600, color: '#ef4444' }}>
                {r.putVol.toLocaleString()}
              </div>
              <div className="hs-iv-cell" style={{ justifyContent: 'flex-end' }}>
                <span className="badge">
                  <span className="fill" style={{ width: `${Math.min(100, r.iv * 3)}%` }} />
                </span>
                <span>{r.iv}%</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="row" style={{ marginTop: 14, gap: 14, fontSize: 10.5, color: 'var(--on-surface-muted)' }}>
        <span>
          <strong style={{ color: 'var(--on-surface)' }}>Reading this:</strong> each row is a strike for the{' '}
          {exp.label} expiration. Bar shows dealer {metric.toUpperCase()} (call-dominant green right ·
          put-dominant red left). Click another expiration above to switch.
        </span>
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

// ─── Pivot build / rate of change rail ─────────────────────────
function PivotBuild() {
  const ranked = [...HS.collapsed]
    .map((s) => ({ ...s, abs: Math.abs(s.netGex) }))
    .sort((a, b) => b.abs - a.abs)
    .slice(0, 10);
  const max = Math.max(...ranked.map((r) => r.abs));
  return (
    <div className="card-i hs-roc-card">
      <div className="card-h">
        <h3>Pivot build · ranked</h3>
        <span className="meta">|GEX| · all expirations</span>
      </div>
      {ranked.map((r, i) => (
        <div key={i} className="hs-roc-bar">
          <span
            className="strike"
            style={{
              color:
                r.role === 'spot'
                  ? 'var(--brand)'
                  : r.role === 'king'
                    ? '#ffb800'
                    : r.role === 'flip'
                      ? '#ef4444'
                      : 'var(--on-surface)',
            }}
          >
            {r.strike}
          </span>
          <span className="track">
            <span className={`fill ${r.netGex < 0 ? 'neg' : ''}`} style={{ width: `${(r.abs / max) * 100}%` }} />
          </span>
          <span className="val" style={{ color: r.netGex < 0 ? '#ef4444' : 'var(--bull)' }}>
            {fmtGexK(r.netGex)}
          </span>
        </div>
      ))}
    </div>
  );
}

// Expiration drill tab row (shown when an expiration is selected).
function ExpTabs({
  selExp,
  onSelect,
}: {
  selExp: string | null;
  onSelect: (iso: string) => void;
}) {
  return (
    <div className="hs-exp-tabs">
      <span className="label">Expiration</span>
      {HS.expirations.map((e) => (
        <button
          key={e.iso}
          className={`hs-exp-tab ${selExp === e.iso ? 'active' : ''} ${e.tags.includes('opex') ? 'opex' : ''}`}
          onClick={() => onSelect(e.iso)}
          type="button"
        >
          <span className="name">{e.label}</span>
          <span className="meta">
            {e.dte}d · {new Date(e.iso).toLocaleDateString([], { month: 'short', day: 'numeric' })}
          </span>
        </button>
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
  const [selExp, setSelExp] = useState<string | null>(null);

  // Real data overlay: latest snapshot date → gamma levels for the focus symbol.
  const sym = (focusSymbol || HS.ticker).replace(/^\^/, '');
  const datesQuery = useLatestOptionsDate(sym);
  const latestDate = datesQuery.data?.dates?.[0] ?? '';
  const levelsQuery = useGammaLevels(sym, latestDate, { enabled: !!latestDate });
  const levels = levelsQuery.data;

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
      const flipLvl = levels.flip_levels?.[0];
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
        flipStrike: levels.flip ?? HS.flip,
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
      {/* Persistent demo pill — the grid/tactical/drill-in/pivot remain mock. */}
      <div className="hs-demo-banner">
        <span className="dot" />
        <span>
          Demo data — per-expiration exposure pending backend.{' '}
          {overlay.isReal ? (
            <strong>Metrics chips &amp; node list show live {overlay.ticker} levels.</strong>
          ) : (
            <strong>Showing mock {HS.ticker} surface.</strong>
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
      />
      <Legend overlay={overlay} />
      {selExp && <ExpTabs selExp={selExp} onSelect={setSelExp} />}

      <div className="hs-stage">
        <div>
          <TacticalCard />
        </div>
        {selExp ? (
          <ExpirationDrillIn expIso={selExp} metric={metric} onClose={() => setSelExp(null)} />
        ) : (
          <HeatmapGrid metric={metric} onSelectExp={setSelExp} />
        )}
        <div className="col" style={{ gap: 14 }}>
          <NodeList overlay={overlay} />
          <PivotBuild />
        </div>
      </div>
    </div>
  );
}
