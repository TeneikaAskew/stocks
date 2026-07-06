import { BENTO, GAMMA_LADDER, SPOT_LABEL } from './fixtures';

/** The diverging strike ladder — mirrors the app's Profiles tab (spec §5). */
function GammaLadderTile() {
  const markerLabel = { king: '★K', gate: '◆G', flip: '⇅F' } as const;
  const markerClass = { king: 'sl-gold', gate: 'sl-blue', flip: 'sl-viol' } as const;

  return (
    <div className="sl-tile" style={{ gridRow: 'span 2', position: 'relative' }}>
      <h4>Gamma Map</h4>
      <div className="sl-dim" style={{ fontSize: 11 }}>net dealer gamma by strike</div>
      <div style={{ marginTop: 12, position: 'relative' }}>
        <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, borderLeft: '1px dashed rgba(255,255,255,.18)' }} />
        {GAMMA_LADDER.map((row) => (
          <div
            key={row.strike}
            className="sl-mono"
            style={{
              display: 'grid', gridTemplateColumns: '40px 1fr 1fr 34px',
              alignItems: 'center', height: 17, fontSize: 9.5,
            }}
          >
            <span className={row.marker ? markerClass[row.marker] : 'sl-dim'}>{row.strike}</span>
            <span style={{ display: 'flex', justifyContent: 'flex-end' }}>
              {row.side === 'neg' && (
                <span style={{ height: 11, borderRadius: 2, width: `${row.pct}%`, background: row.pct > 55 ? '#8b5cf6' : '#7c5bb5' }} />
              )}
            </span>
            <span style={{ display: 'flex', justifyContent: 'flex-start' }}>
              {row.side === 'pos' && (
                <span
                  style={{
                    height: 11, borderRadius: 2, width: `${row.pct}%`,
                    background: row.marker === 'king'
                      ? 'linear-gradient(90deg,#34d399,#ffb800)'
                      : '#2bb381',
                    boxShadow: row.marker === 'king' ? '0 0 9px rgba(255,184,0,.45)' : undefined,
                  }}
                />
              )}
            </span>
            <span className={row.marker ? markerClass[row.marker] : 'sl-dim'}>
              {row.marker ? markerLabel[row.marker] : ''}
            </span>
          </div>
        ))}
        <div style={{ position: 'absolute', left: 0, right: 0, top: 79, borderTop: '1.5px dashed rgba(248,113,113,.8)' }} />
        <div className="sl-mono" style={{ position: 'absolute', right: -4, top: 70, fontSize: 9, color: 'var(--sl-bear)' }}>
          {SPOT_LABEL}
        </div>
      </div>
      <div className="sl-mono" style={{ display: 'flex', gap: 10, fontSize: 9.5, marginTop: 10 }}>
        <span className="sl-bull">■ +gamma</span>
        <span className="sl-viol">■ −gamma</span>
        <span className="sl-gold">★ King</span>
        <span className="sl-blue">◆ Gate</span>
        <span className="sl-viol">⇅ Flip</span>
      </div>
    </div>
  );
}

/** Section 03 — six real-product tiles (spec §4.3). */
export function BentoGrid() {
  const { verdict, catalysts, movementRead, signals, proof } = BENTO;
  const bullWidthPct = Math.round((verdict.bullScore / (verdict.bullScore + verdict.bearScore)) * 100);

  return (
    <section className="sl-sec" id="modules">
      <h2 className="sl-h2">Everything that moves the market. One surface.</h2>
      <p className="sl-mut" style={{ margin: '0 0 20px', fontSize: 14 }}>
        Six systems, one verdict — every tile is the real product&rsquo;s own visual, not marketing art.
      </p>
      <div
        style={{
          display: 'grid', gap: 12,
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gridAutoRows: 'minmax(118px, auto)',
        }}
      >
        <GammaLadderTile />
        <div className="sl-tile">
          <h4>Council · AI verdict</h4>
          <div className="sl-bull" style={{ fontSize: 22, fontWeight: 800, marginTop: 10 }}>{verdict.dir}</div>
          <div style={{ height: 8, borderRadius: 4, background: 'var(--sl-bear)', overflow: 'hidden', marginTop: 8 }}>
            <div style={{ width: `${bullWidthPct}%`, height: '100%', background: 'var(--sl-bull)' }} />
          </div>
          <div className="sl-dim" style={{ fontSize: 11, marginTop: 6 }}>
            bull {verdict.bullScore} · bear {verdict.bearScore} · 7 agents
          </div>
        </div>
        <div className="sl-tile">
          <h4>Catalysts · next up</h4>
          <div className="sl-mono" style={{ marginTop: 10, fontSize: 12 }}>
            {catalysts.map((c) => (
              <div key={c.label}>
                <span className={c.impact ? 'sl-gold' : 'sl-dim'}>{c.when}</span> {c.label}{' '}
                {c.impact && <span className="sl-bear">{c.impact}</span>}
              </div>
            ))}
          </div>
        </div>
        <div className="sl-tile">
          <h4>Movement Read</h4>
          <p className="sl-mut" style={{ fontSize: 12, lineHeight: 1.5, margin: '8px 0 0' }}>{movementRead}</p>
        </div>
        <div className="sl-tile">
          <h4>Signals · today</h4>
          <div className="sl-mono" style={{ marginTop: 10, fontSize: 12 }}>
            {signals.map((s) => (
              <div key={s.text} className={s.state === 'fired' ? 'sl-bull' : 'sl-dim'}>● {s.text}</div>
            ))}
          </div>
        </div>
        <div className="sl-tile">
          <h4>Proof · walk-forward</h4>
          {proof.hitRatePct !== null ? (
            <div style={{ fontSize: 20, fontWeight: 800, marginTop: 8 }}>
              {proof.hitRatePct}% <span className="sl-dim" style={{ fontSize: 11, fontWeight: 400 }}>hit rate</span>
            </div>
          ) : (
            <div style={{ fontSize: 14, fontWeight: 700, marginTop: 8 }}>Results published at launch</div>
          )}
          <div className="sl-dim" style={{ fontSize: 11, marginTop: 4 }}>{proof.caption}</div>
        </div>
      </div>
    </section>
  );
}
