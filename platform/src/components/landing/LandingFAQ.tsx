import { FAQ } from './fixtures';

/** Section 10 — FAQ + footer. */
export function LandingFAQ() {
  return (
    <section className="sl-sec" id="faq">
      <div style={{ display: 'flex', gap: 40, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 280 }}>
          {FAQ.map((item) => (
            <div key={item.q} style={{ borderTop: '1px solid rgba(255,255,255,.07)', padding: '13px 0', fontSize: 13 }}>
              <b>{item.q}</b>
              <div className="sl-mut" style={{ marginTop: 4 }}>{item.a}</div>
            </div>
          ))}
        </div>
        <div className="sl-dim" style={{ width: 220 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <div className="sl-sun" style={{ width: 16, height: 16 }} />
            <span style={{ fontWeight: 800, letterSpacing: '2px', color: 'var(--sl-text)' }}>SOLYRA</span>
          </div>
          <div style={{ fontSize: 12, lineHeight: 2 }}>
            <a href="#modules" style={{ color: 'inherit', textDecoration: 'none' }}>Modules</a> ·{' '}
            <a href="#learn" style={{ color: 'inherit', textDecoration: 'none' }}>Learn</a> ·{' '}
            <a href="#faq" style={{ color: 'inherit', textDecoration: 'none' }}>FAQ</a>
            <br />Privacy · Terms · Disclosures
            <br />© 2026 Solyra
          </div>
        </div>
      </div>
    </section>
  );
}
