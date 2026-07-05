import { COUNCIL, FLOW_ROWS, HEAT_EXPIRIES, HEAT_ROWS } from './fixtures';

/** Section 05 — Gamma Map deep-dive: the Swing-Mode strike×expiry grid (spec §5). */
function GammaMapDive() {
  return (
    <section className="sl-sec sl-2col">
      <div style={{ flex: 1 }}>
        <div className="sl-kicker">Gamma Map · dealer positioning</div>
        <h3 style={{ fontSize: 22, fontWeight: 800, margin: '8px 0' }}>See the wall before price hits it.</h3>
        <p className="sl-mut" style={{ fontSize: 14, lineHeight: 1.6 }}>
          A strike-by-expiry grid of net dealer gamma, refreshed all session — green where calls
          dominate and dealers pin, red where puts dominate and moves accelerate. The gold cell is
          the King: the strike dealers defend hardest.
        </p>
        <div className="sl-dim" style={{ fontSize: 12, marginTop: 8 }}>
          ↳ replaces guesswork S/R lines · SPY · QQQ · IWM · SPX at launch
        </div>
      </div>
      <div className="sl-panel" style={{ flex: 1, padding: 16, width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 10 }}>
          <span className="sl-mut">net GEX · strike × expiry · sample session</span>
        </div>
        <div className="sl-mono" style={{ display: 'grid', gridTemplateColumns: '44px repeat(7, 1fr)', gap: 3, fontSize: 9.5 }}>
          {HEAT_ROWS.map((row) => {
            const rgb = row.kind === 'pos' ? '34,197,94' : '239,68,68';
            const labelClass = row.marker === 'king' ? 'sl-gold' : row.marker === 'flip' ? 'sl-viol' : 'sl-dim';
            const prefix = row.marker === 'king' ? '★' : row.marker === 'flip' ? '⇅' : '';
            return [
              <div key={`${row.strike}-l`} className={labelClass} style={{ alignSelf: 'center' }}>
                {prefix}{row.strike}
              </div>,
              ...row.alphas.map((a, i) => (
                <div
                  key={`${row.strike}-${i}`}
                  style={{
                    height: 22, borderRadius: 3, background: `rgba(${rgb},${a})`,
                    border:
                      row.marker === 'king' && i === 0 ? '1.5px solid #ffb800'
                      : row.marker === 'flip' ? '1px dashed rgba(167,139,250,.7)'
                      : undefined,
                    borderBottom: row.marker === 'spot' ? '1.5px dashed rgba(248,113,113,.8)' : undefined,
                    boxShadow: row.marker === 'king' && i === 0 ? '0 0 10px rgba(255,184,0,.5)' : undefined,
                  }}
                />
              )),
            ];
          })}
        </div>
        <div className="sl-dim sl-mono" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginTop: 8, paddingLeft: 47 }}>
          {HEAT_EXPIRIES.map((e) => <span key={e}>{e}</span>)}
        </div>
        <div className="sl-mono" style={{ display: 'flex', gap: 10, fontSize: 9.5, marginTop: 8, flexWrap: 'wrap' }}>
          <span className="sl-bull">■ call-dominant · pin</span>
          <span className="sl-bear">■ put-dominant · accelerate</span>
          <span className="sl-gold">★ King</span>
          <span className="sl-bear">┄ spot</span>
          <span className="sl-viol">┄ flip</span>
        </div>
      </div>
    </section>
  );
}

/** Section 06 — Flow deep-dive. */
function FlowDive() {
  return (
    <section className="sl-sec sl-2col">
      <div className="sl-panel" style={{ flex: 1.15, padding: '14px 16px', width: '100%', overflowX: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 8 }}>
          <span className="sl-mut">flow tape · smart-filtered · sample session</span>
        </div>
        <table className="sl-mono" style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse', minWidth: 480 }}>
          <thead>
            <tr className="sl-dim" style={{ textAlign: 'left' }}>
              <th style={{ padding: '4px 6px' }}>time</th><th>contract</th><th>size</th><th>prem</th><th>side</th><th>read</th>
            </tr>
          </thead>
          <tbody>
            {FLOW_ROWS.map((r) => (
              <tr
                key={r.time}
                style={{
                  background: r.flag ? 'rgba(52,211,153,.05)' : r.side === 'bid' ? 'rgba(248,113,113,.04)' : undefined,
                }}
              >
                <td style={{ padding: '5px 6px' }}>{r.time}</td>
                <td>{r.contract}</td>
                <td>{r.size}</td>
                <td>{r.prem}</td>
                <td className={r.side === 'ask' ? 'sl-bull' : 'sl-bear'}>{r.sideLabel}</td>
                <td className={r.flag ? 'sl-gold' : 'sl-dim'}>{r.read}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ flex: 1 }}>
        <div className="sl-kicker">Flow · the tape, filtered</div>
        <h3 style={{ fontSize: 22, fontWeight: 800, margin: '8px 0' }}>Flow without the firehose.</h3>
        <p className="sl-mut" style={{ fontSize: 14, lineHeight: 1.6 }}>
          Raw tape is noise. Solyra clusters sweeps, tags likely opens vs. closes, and only flags
          flow that agrees — or violently disagrees — with dealer positioning. When three ask-side
          sweeps hit the same strike dealers are short, you get one clear flag, not 400 rows.
        </p>
        <div className="sl-dim" style={{ fontSize: 12, marginTop: 8 }}>↳ coming to early access</div>
      </div>
    </section>
  );
}

/** Section 07 — Council deep-dive. */
function CouncilDive() {
  return (
    <section className="sl-sec sl-2col">
      <div style={{ flex: 1 }}>
        <div className="sl-kicker">Council · seven agents, one verdict</div>
        <h3 style={{ fontSize: 22, fontWeight: 800, margin: '8px 0' }}>
          Your own research desk, arguing so you don&rsquo;t have to.
        </h3>
        <p className="sl-mut" style={{ fontSize: 14, lineHeight: 1.6 }}>
          A bull and a bear debate every ticker with live evidence. A risk officer stress-tests
          the loser&rsquo;s best point. Personas — scalper, swing, income — each get their own plan.
          You read one page: verdict, levels, plan, and what would change the Council&rsquo;s mind.
        </p>
        <div className="sl-dim" style={{ fontSize: 12, marginTop: 8 }}>
          ↳ every debate archived · every verdict graded against what actually happened
        </div>
      </div>
      <div className="sl-panel" style={{ flex: 1, padding: 16, width: '100%' }}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 180, background: 'rgba(52,211,153,.06)', border: '1px solid rgba(52,211,153,.25)', borderRadius: 9, padding: 10 }}>
            <div className="sl-bull" style={{ fontSize: 10, letterSpacing: '1.5px' }}>BULL · {COUNCIL.bull.score}</div>
            <div className="sl-mut" style={{ fontSize: 11.5, lineHeight: 1.5, marginTop: 5 }}>{COUNCIL.bull.quote}</div>
          </div>
          <div style={{ flex: 1, minWidth: 180, background: 'rgba(248,113,113,.05)', border: '1px solid rgba(248,113,113,.25)', borderRadius: 9, padding: 10 }}>
            <div className="sl-bear" style={{ fontSize: 10, letterSpacing: '1.5px' }}>BEAR · {COUNCIL.bear.score}</div>
            <div className="sl-mut" style={{ fontSize: 11.5, lineHeight: 1.5, marginTop: 5 }}>{COUNCIL.bear.quote}</div>
          </div>
        </div>
        <div style={{ border: '1px solid rgba(255,184,92,.3)', background: 'rgba(255,184,92,.05)', borderRadius: 9, padding: '10px 12px' }}>
          <div className="sl-gold" style={{ fontSize: 10, letterSpacing: '1.5px' }}>VERDICT · RISK-CHECKED</div>
          <div style={{ fontSize: 12.5, marginTop: 4 }}>{COUNCIL.verdict}</div>
        </div>
        <div className="sl-dim sl-mono" style={{ display: 'flex', gap: 6, marginTop: 12, fontSize: 10, flexWrap: 'wrap' }}>
          {COUNCIL.personas.map((p) => (
            <span key={p} style={{ border: '1px solid rgba(255,255,255,.12)', borderRadius: 99, padding: '2px 9px' }}>{p}</span>
          ))}
        </div>
      </div>
    </section>
  );
}

export function ModuleDives() {
  return (
    <>
      <GammaMapDive />
      <FlowDive />
      <CouncilDive />
    </>
  );
}
