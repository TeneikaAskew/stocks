import { useQuery } from '@tanstack/react-query';

const ADMIN_EMAIL = 'teneika@bictech.org';

/** Guest identity returned by /api/me after a staging passcode bypass.
 *  Must match GUEST_EMAIL in platform/api/auth_bypass.py. */
export const GUEST_EMAIL = 'guest@staging.local';

interface MeResponse {
  email: string | null;
  /** Server flag — true only on the staging service (ALLOW_AUTH_BYPASS=1). */
  auth_bypass_allowed?: boolean;
}

export function useUser() {
  const query = useQuery<MeResponse>({
    queryKey: ['me'],
    queryFn: async () => {
      const r = await fetch('/api/me');
      // A non-OK /api/me means "not authenticated and bypass not offered" —
      // the gate treats that as local/open (prod can't reach this state
      // because IAP authenticates before the app loads).
      if (!r.ok) return { email: null, auth_bypass_allowed: false };
      return r.json();
    },
    staleTime: 5 * 60_000,
  });

  const email = query.data?.email ?? null;
  const isAdmin = email?.toLowerCase() === ADMIN_EMAIL;
  const authBypassAllowed = query.data?.auth_bypass_allowed === true;

  return { email, isAdmin, authBypassAllowed, isLoading: query.isLoading };
}
