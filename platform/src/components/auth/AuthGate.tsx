import type { ReactNode } from 'react';
import { useUser } from '@/hooks/useUser';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { SignInScreen } from './SignInScreen';

/**
 * Top-level auth gate.
 *
 * Only `firebase` mode (the public app-login service) ever shows a login page.
 * In `iap` mode the edge already authenticated the request; in `open`/local
 * mode there's no auth — both render the app directly, unchanged. This keeps
 * the existing E2E specs (open mode) rendering as before.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { authMode, isSignedIn, isLoading } = useUser();

  if (authMode !== 'firebase') return <>{children}</>;

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--surface-0)]">
        <LoadingSpinner size={28} />
      </div>
    );
  }

  if (!isSignedIn) return <SignInScreen />;

  return <>{children}</>;
}
