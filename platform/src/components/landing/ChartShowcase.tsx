import { CANDLES } from './fixtures';

const GREEN = '#34d399';
const RED = '#f87171';

/**
 * Section 04 — SPY sample chart with gamma levels in the app's EXACT
 * Charts-page line styles (spec §5): King solid gold #f59e0b w2,
 * Gate dotted blue #3b82f6, Flip dashed violet #a78bfa.
 */
export function ChartShowcase() {
  return (
    <section className="sl-sec">
      <h2 className="sl-h2">
        Charts that show the <em style={{ color: 'var(--sl-amber)' }}>why</em>.
      </h2>
      <p className="sl-mut" style={{ margin: '0 0 18px', fontSize: 14, maxWidth: 560 }}>
        Every level on a Solyra chart exists because dealers put it there. King, Gate, and Flip
        are drawn from live options positioning — not trendline art.
      </p>
      <div className="sl-panel" style={{ padding: '18px 20px', overflowX: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 10 }}>
          <span><b>SPY</b> <span className="sl-dim">· 5-min · gamma overlay · sample session</span></span>
          <span className="sl-mono sl-bull">590.61 ▲ +0.9%</span>
        </div>
        <svg viewBox="0 0 720 280" style={{ width: '100%', height: 'auto', display: 'block', minWidth: 560 }}>
          {[70, 140, 210].map((y) => (
            <line key={y} x1="0" y1={y} x2="720" y2={y} stroke="rgba(255,255,255,.04)" />
          ))}

          {/* KING — solid gold, width 2 (ChartsPage lineStyle 0) */}
          <line x1="0" y1="42" x2="640" y2="42" stroke="#f59e0b" strokeWidth="2" />
          <rect x="640" y="32" width="80" height="20" rx="4" fill="rgba(245,158,11,.12)" stroke="#f59e0b" strokeWidth=".7" />
          <text x="680" y="46" fill="#f59e0b" fontSize="11" textAnchor="middle" fontFamily="Consolas">★ KING 592</text>

          {/* GATE — dotted blue (ChartsPage lineStyle 2) */}
          <line x1="0" y1="154" x2="640" y2="154" stroke="#3b82f6" strokeWidth="1.2" strokeDasharray="2 4" />
          <rect x="640" y="144" width="80" height="20" rx="4" fill="rgba(59,130,246,.1)" stroke="#3b82f6" strokeWidth=".7" />
          <text x="680" y="158" fill="#60a5fa" fontSize="11" textAnchor="middle" fontFamily="Consolas">◆ GATE 588</text>

          {/* FLIP — dashed violet (ChartsPage lineStyle 1) */}
          <line x1="0" y1="238" x2="640" y2="238" stroke="#a78bfa" strokeWidth="2" strokeDasharray="8 5" />
          <rect x="640" y="228" width="80" height="20" rx="4" fill="rgba(167,139,250,.1)" stroke="#a78bfa" strokeWidth=".7" />
          <text x="680" y="242" fill="#a78bfa" fontSize="11" textAnchor="middle" fontFamily="Consolas">⇅ FLIP 585</text>

          {/* VWAP */}
          <path
            d="M 14 220 C 120 200, 200 150, 300 120 S 480 130, 560 100 S 640 80, 660 76"
            stroke="#6ec3f2" strokeWidth="1.3" fill="none" opacity=".75"
          />

          {/* candles */}
          {CANDLES.map((c, i) => {
            const x = 14 + i * 27;
            const color = c.up ? GREEN : RED;
            return (
              <g key={i} strokeWidth="1.4">
                <line x1={x + 7.5} y1={c.wickTop} x2={x + 7.5} y2={c.wickBot} stroke={color} />
                <rect x={x} y={c.bodyTop} width="15" height={c.bodyH} fill={color} />
              </g>
            );
          })}

          {/* signal marker */}
          <circle cx="487.5" cy="176" r="5" fill="none" stroke={GREEN} strokeWidth="1.5" />
          <line x1="487.5" y1="181" x2="487.5" y2="196" stroke={GREEN} strokeWidth="1" />
          <rect x="420" y="196" width="135" height="22" rx="5" fill="rgba(52,211,153,.1)" stroke="rgba(52,211,153,.4)" strokeWidth=".8" />
          <text x="487" y="211" fill={GREEN} fontSize="10.5" textAnchor="middle" fontFamily="Consolas">SIGNAL · gate-hold LONG</text>

          {/* rejection annotation */}
          <rect x="255" y="18" width="150" height="20" rx="5" fill="rgba(245,158,11,.08)" stroke="rgba(245,158,11,.35)" strokeWidth=".8" />
          <text x="330" y="32" fill="#f59e0b" fontSize="10.5" textAnchor="middle" fontFamily="Consolas">King rejection — dealers sell</text>
        </svg>
      </div>
    </section>
  );
}
