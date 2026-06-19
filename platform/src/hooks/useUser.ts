import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getAuthMode } from '@/lib/runtimeConfig';
import { subscribeAuth } from '@/lib/firebase';

interface MeResponse {
  email: string | null;
  is_admin?: boolean;
}

/**
 * Single identity hook for the app.
 *
 * - firebase mode: tracks Firebase auth state; once signed in, reads the
 *   server-VERIFIED identity from /api/me (so `is_admin` can't be spoofed).
 * - iap / open / local mode: polls /api/me exactly as before (IAP header gives
 *   the email in prod; null locally) — no gate, no behaviour change.
 */
export function useUser() {
  const authMode = getAuthMode();
  const firebaseMode = authMode === 'firebase';

  // In non-firebase modes there's no client auth state: "ready" + "signed in".
  const [fbReady, setFbReady] = useState(!firebaseMode);
  const [signedIn, setSignedIn] = useState(!firebaseMode);

  useEffect(() => {
    if (!firebaseMode) return;
    const unsub = subscribeAuth((user) => {
      setSignedIn(!!user);
      setFbReady(true);
    });
    return () => unsub();
  }, [firebaseMode]);

  // Only hit /api/me when it can succeed: always in non-firebase modes; in
  // firebase mode only once signed in (the token attaches via authedFetch).
  const meEnabled = !firebaseMode || signedIn;
  const query = useQuery<MeResponse>({
    queryKey: ['me', signedIn],
    enabled: meEnabled,
    queryFn: async () => {
      const r = await fetch('/api/me');
      if (!r.ok) return { email: null, is_admin: false };
      return r.json();
    },
    staleTime: 5 * 60_000,
  });

  const email = query.data?.email ?? null;
  const isAdmin = query.data?.is_admin === true;
  const isSignedIn = firebaseMode ? signedIn : true;
  const isLoading = !fbReady || (meEnabled && query.isLoading);

  return { email, isAdmin, isSignedIn, isLoading, authMode };
}
