import { useQuery } from '@tanstack/react-query';

const ADMIN_EMAIL = 'teneika@bictech.org';

interface MeResponse {
  email: string | null;
}

export function useUser() {
  const query = useQuery<MeResponse>({
    queryKey: ['me'],
    queryFn: async () => {
      const r = await fetch('/api/me');
      if (!r.ok) return { email: null };
      return r.json();
    },
    staleTime: 5 * 60_000,
  });

  const email = query.data?.email ?? null;
  const isAdmin = email?.toLowerCase() === ADMIN_EMAIL;

  return { email, isAdmin, isLoading: query.isLoading };
}
