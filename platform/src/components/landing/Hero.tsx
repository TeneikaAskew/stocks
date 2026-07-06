import { AGENT_LINES } from './fixtures';
import { useTypingLines } from './useTypingLines';

/** Section 02 — hero with the live agent terminal (spec §4.2). */
export function Hero() {
  const visible = useTypingLines(AGENT_LINES.length);

  return (
    <header
      className="sl-sec sl-2col"
      style={{
        borderTop: 'none', paddingTop: 44, paddingBottom: 56,
        background:
          'radial-gradient(ellipse 70% 55% at 72% 30%, rgba(255,150,70,.13), transparent), ' +
          'radial-gradient(ellipse 40% 40% at 20% 80%, rgba(110,195,242,.05), transparent)',
      }}
    >
      <div style={{ flex: 1.1 }}>
        <div className="sl-kicker" style={{ color: 'var(--sl-amber)', marginBottom: 14 }}>
          The AI analyst desk for market movement
        </div>
        <h1 style={{ fontSize: 'clamp(30px, 4.5vw, 44px)', lineHeight: 1.12, fontWeight: 800, margin: 0 }}>
          Know why the market moves.
          <br />
          <span
            style={{
              background: 'linear-gradient(90deg, #ffd9a0, #ff8a4d)',
              WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent',
            }}
          >
            Before it moves.
          </span>
        </h1>
        <p className="sl-mut" style={{ fontSize: 16, lineHeight: 1.55, margin: '18px 0 24px', maxWidth: 440 }}>
          Solyra&rsquo;s agents read dealer positioning, options flow, and every catalyst on the
          calendar — then hand you a plain-language brief, live signals, and the reason behind
          every move. Learn it. Trade it. Review it.
        </p>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <a href="#waitlist" className="sl-cta">Join the waitlist</a>
          <a href="#learn" className="sl-cta2">See a live day ↓</a>
        </div>
        <div className="sl-dim" style={{ fontSize: 12, marginTop: 14 }}>
          Early access · no card required · built on institutional options &amp; 1-minute market data
        </div>
      </div>

      <div className="sl-panel" style={{ flex: 1, overflow: 'hidden', boxShadow: '0 20px 60px rgba(0,0,0,.5), 0 0 40px rgba(255,150,70,.06)' }}>
        <div
          style={{
            display: 'flex', justifyContent: 'space-between', padding: '10px 14px',
            borderBottom: '1px solid rgba(255,255,255,.07)', fontSize: 11,
          }}
        >
          <span className="sl-mut">solyra · agent desk</span>
          <span className="sl-bull">● sample premarket session</span>
        </div>
        <div className="sl-mono" style={{ padding: '14px 16px', fontSize: 12, lineHeight: 1.85, minHeight: 200 }}>
          {AGENT_LINES.slice(0, visible).map((line, i) => (
            <div key={i} className={line.tag ? undefined : 'sl-dim'}>
              {line.tag && <span className="sl-gold">{line.tag}</span>}
              {line.tag ? ' · ' : ''}
              {line.text}
            </div>
          ))}
          {visible >= AGENT_LINES.length && (
            <div style={{ marginTop: 8 }}>
              <span
                className="sl-bull"
                style={{
                  background: 'rgba(52,211,153,.1)', border: '1px solid rgba(52,211,153,.3)',
                  borderRadius: 6, padding: '3px 10px', fontSize: 11,
                }}
              >
                3 signals armed · watching every 1-min bar
              </span>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
