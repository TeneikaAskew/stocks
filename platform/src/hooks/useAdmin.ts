import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

// ---------------------------------------------------------------------------
// Admin token lives in sessionStorage, NOT in a build-time env var. The
// server validates it via the X-Admin-Token header. See routers/admin.py.
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'admin-token';

export function getAdminToken(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setAdminToken(token: string): void {
  sessionStorage.setItem(STORAGE_KEY, token);
}

export function clearAdminToken(): void {
  sessionStorage.removeItem(STORAGE_KEY);
}

function authHeaders(): HeadersInit {
  const tok = getAdminToken();
  return tok ? { 'X-Admin-Token': tok } : {};
}

export interface RouteRow {
  role: string;
  provider: string;
  model: string;
  updated_at: string | null;
  updated_by: string | null;
}

export interface AvailableModelRow {
  provider: string;
  model: string;
  has_credentials: boolean;
  input_usd_per_mtok: number;
  output_usd_per_mtok: number;
}

export function useAdminRoutes(enabled: boolean) {
  return useQuery<{ routes: RouteRow[] }>({
    queryKey: ['admin-routes'],
    queryFn: async () => {
      const r = await fetch('/api/admin/routes', { headers: authHeaders() });
      if (r.status === 401) throw new Error('unauthorized');
      if (!r.ok) throw new Error(`admin routes ${r.status}`);
      return r.json();
    },
    enabled,
    staleTime: 30_000,
  });
}

export function useAdminModels(enabled: boolean) {
  return useQuery<{ models: AvailableModelRow[] }>({
    queryKey: ['admin-models'],
    queryFn: async () => {
      const r = await fetch('/api/admin/models', { headers: authHeaders() });
      if (r.status === 401) throw new Error('unauthorized');
      if (!r.ok) throw new Error(`admin models ${r.status}`);
      return r.json();
    },
    enabled,
    staleTime: 5 * 60_000,
  });
}

export function useUpdateAdminRoute() {
  const qc = useQueryClient();
  return useMutation<
    RouteRow,
    Error,
    { role: string; provider: string; model: string }
  >({
    mutationFn: async ({ role, provider, model }) => {
      const r = await fetch(`/api/admin/routes/${role}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(),
        },
        body: JSON.stringify({ provider, model }),
      });
      if (r.status === 401) throw new Error('unauthorized');
      if (!r.ok) {
        const text = await r.text().catch(() => '');
        throw new Error(`update route failed: ${r.status} ${text}`);
      }
      return r.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-routes'] });
    },
  });
}
