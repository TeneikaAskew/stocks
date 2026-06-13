import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Lock, Loader2, ShieldCheck } from 'lucide-react';
import { Brand } from '@/components/layout/Brand';

/**
 * Staging sign-in screen — shown only when the server reports
 * `auth_bypass_allowed` (i.e. the public, no-IAP staging service). The user
 * enters the shared staging passcode; on success the server sets an HttpOnly
 * cookie and we refetch `/api/me`, which flips the gate to "rendered".
 *
 * Production never renders this: IAP authenticates before the app loads, so
 * `/api/me` already carries an email and the gate passes straight through.
 */
export function SignInScreen() {
  const qc = useQueryClient();
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!value.trim() || checking) return;
    setChecking(true);
    setError(null);
    try {
      const r = await fetch('/api/auth/bypass', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passcode: value.trim() }),
      });
      if (r.status === 401) {
        setError('Invalid passcode.');
        return;
      }
      if (r.status === 503) {
        setError('Staging passcode is not configured on the server.');
        return;
      }
      if (!r.ok) {
        setError(`Sign-in failed (${r.status}).`);
        return;
      }
      // Cookie is set — re-probe identity so the gate re-renders as authed.
      await qc.invalidateQueries({ queryKey: ['me'] });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setChecking(false);
    }
  };

  return (
    <div
      data-testid="signin-screen"
      className="flex min-h-screen items-center justify-center bg-[var(--surface-0)] px-4"
    >
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm rounded-2xl bg-[var(--surface-1)] p-7 shadow-2xl ring-1 ring-[var(--outline,rgba(255,255,255,0.06))]"
      >
        <div className="mb-6 flex items-center justify-between">
          <Brand tag="staging" />
          <span className="inline-flex items-center gap-1 rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--on-surface-variant)]">
            <ShieldCheck size={11} /> Staging
          </span>
        </div>

        <h1 className="text-[18px] font-bold tracking-[-0.02em] text-[var(--on-surface)]">
          Staging access
        </h1>
        <p className="mb-5 mt-1 text-[13px] leading-relaxed text-[var(--on-surface-variant)]">
          Enter the staging passcode to continue. Production requires Google
          sign-in.
        </p>

        <label
          htmlFor="staging-passcode"
          className="mb-1.5 flex items-center gap-1.5 text-[12px] font-medium text-[var(--on-surface)]"
        >
          <Lock size={13} /> Passcode
        </label>
        <input
          id="staging-passcode"
          type="password"
          autoFocus
          autoComplete="off"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          data-testid="staging-passcode-input"
          placeholder="••••••••"
          className="w-full rounded-lg bg-[var(--surface-2)] px-3 py-2.5 text-sm text-[var(--on-surface)] outline-none ring-1 ring-transparent transition focus:ring-[var(--brand)] placeholder:text-[var(--on-surface-muted)]"
        />

        {error && (
          <div data-testid="staging-error" className="mt-3 text-[12px] text-[var(--bear)]">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={checking || !value.trim()}
          data-testid="staging-submit"
          className="mt-5 flex w-full items-center justify-center gap-2 rounded-lg bg-[var(--brand)] px-4 py-2.5 text-sm font-semibold text-[var(--on-brand)] transition hover:opacity-90 disabled:opacity-50"
        >
          {checking ? <Loader2 size={15} className="animate-spin" /> : null}
          Continue
        </button>
      </form>
    </div>
  );
}
