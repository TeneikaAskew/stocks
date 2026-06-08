import type { ReactNode } from 'react';
import { useUser } from '@/hooks/useUser';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { SignInScreen } from './SignInScreen';

/**
 * Top-level auth gate.
 *
 * The only environment that ever shows a sign-in screen is the public staging
 * service, where the server reports `auth_bypass_allowed: true`. Everywhere
 * else the app renders straight through:
 *
 *   - Production: IAP authenticates before the app loads, so `/api/me`
 *     carries an email → render.
 *   - Local dev / tests: `/api/me` returns `auth_bypass_allowed: false`
 *     (or fails), so the gate is inert → render. This is what keeps the
 *     existing E2E specs (which mock `{ email: null }`) rendering as before.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { email, authBypassAllowed, isLoading } = useUser();

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--surface-0)]">
        <LoadingSpinner size={28} />
      </div>
    );
  }

  // Authenticated (prod IAP, or staging after a successful passcode), or any
  // environment that doesn't offer a bypass → render the app.
  if (email || !authBypassAllowed) {
    return <>{children}</>;
  }

  // Staging, not yet through the passcode.
  return <SignInScreen />;
}
