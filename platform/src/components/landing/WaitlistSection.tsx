import { useState, type FormEvent } from 'react';
import { submitWaitlist, validateEmail } from './waitlist';

type Status = 'idle' | 'submitting' | 'done';

/** Section 09 — waitlist capture. Errors are always VISIBLE (Rule 3.7). */
export function WaitlistSection() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!validateEmail(email)) {
      setError('Enter a valid email address.');
      return;
    }
    setStatus('submitting');
    try {
      await submitWaitlist(email, 'landing');
      setStatus('done');
    } catch (err) {
      setStatus('idle');
      setError((err as Error).message);
    }
  }

  return (
    <section
      className="sl-sec"
      id="waitlist"
      style={{ textAlign: 'center', background: 'radial-gradient(ellipse 60% 80% at 50% 100%, rgba(255,150,70,.1), transparent)' }}
    >
      <div
        aria-hidden
        style={{
          width: 74, height: 37, margin: '6px auto 14px', borderRadius: '74px 74px 0 0',
          background: 'radial-gradient(ellipse at 50% 100%, #ffd9a0, #ff8a4d 60%, transparent 78%)',
        }}
      />
      <h2 style={{ fontSize: 'clamp(22px, 3vw, 28px)', fontWeight: 800, margin: 0 }}>Be there at first light.</h2>
      <p className="sl-mut" style={{ fontSize: 15, margin: '10px auto 20px', maxWidth: 480 }}>
        Early access opens in small cohorts. Founding members shape the modules — and keep
        founder pricing for life.
      </p>
      {status === 'done' ? (
        <div className="sl-bull" style={{ fontSize: 15, fontWeight: 600 }} data-testid="waitlist-success">
          You&rsquo;re on the list. One email when your cohort opens.
        </div>
      ) : (
        <form onSubmit={onSubmit} noValidate style={{ display: 'inline-flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@email.com"
            aria-label="Email address"
            data-testid="waitlist-email"
            style={{
              border: '1px solid rgba(255,255,255,.15)', background: 'var(--sl-panel)',
              borderRadius: 8, padding: '10px 18px', fontSize: 13, color: 'var(--sl-text)', minWidth: 240,
            }}
          />
          <button type="submit" className="sl-cta" disabled={status === 'submitting'} data-testid="waitlist-submit">
            {status === 'submitting' ? 'Joining…' : 'Join the waitlist'}
          </button>
        </form>
      )}
      {error && (
        <div className="sl-bear" role="alert" data-testid="waitlist-error" style={{ fontSize: 13, marginTop: 10 }}>
          {error}
        </div>
      )}
      <div className="sl-dim" style={{ fontSize: 12, marginTop: 12 }}>No spam. One email when your cohort opens.</div>
    </section>
  );
}
