import { RHYTHM } from './fixtures';

/** Section 08 — Learn → Do → Act, one market day (spec §4.8). */
export function DailyRhythm() {
  return (
    <section className="sl-sec" id="learn" style={{ background: 'linear-gradient(180deg, transparent, rgba(255,150,70,.03))' }}>
      <h2 className="sl-h2">One market day with Solyra.</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 14, marginTop: 20 }}>
        {RHYTHM.map((card) => (
          <div
            key={card.phase}
            className="sl-tile"
            style={{ padding: 18, borderColor: card.phase === 'DO' ? 'rgba(255,184,92,.3)' : undefined }}
          >
            <div className="sl-gold sl-mono" style={{ fontSize: 12 }}>{card.time} · {card.phase}</div>
            <h3 style={{ fontSize: 16, margin: '8px 0' }}>{card.title}</h3>
            <p className="sl-mut" style={{ fontSize: 13, lineHeight: 1.55, margin: 0 }}>{card.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
