import { useState } from 'react';
import { Loader2, Lock, LogOut, Save } from 'lucide-react';
import {
  clearAdminToken,
  getAdminToken,
  setAdminToken,
  useAdminModels,
  useAdminRoutes,
  useUpdateAdminRoute,
  type AvailableModelRow,
} from '@/hooks/useAdmin';
import { useUser } from '@/hooks/useUser';
import { StructureBrief } from '@/components/structure_brief/StructureBrief';

// ---------------------------------------------------------------------------
// Admin page — per-role model routing dashboard.
//
// Auth: If the user is the admin email (via IAP), they bypass the token gate
// entirely. Otherwise, a token must be entered per-tab (sessionStorage).
// ---------------------------------------------------------------------------

export default function AdminPage() {
  const { isAdmin, isLoading: userLoading } = useUser();
  const [token, setToken] = useState<string | null>(getAdminToken());

  if (userLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 size={18} className="animate-spin text-[var(--color-text-muted)]" />
      </div>
    );
  }

  // Admin email gets straight through — no token needed
  const authed = isAdmin || !!token;

  return (
    <div className="mx-auto max-w-5xl p-4">
      <h1 className="mb-4 text-lg font-semibold text-[var(--color-text-primary)]">Admin</h1>
      {authed ? (
        <div className="space-y-6">
          <RoutingPanel onLogout={() => { clearAdminToken(); setToken(null); }} showLogout={!isAdmin} />
          <section>
            <h2 className="mb-3 text-base font-semibold text-[var(--color-text-primary)]">
              Structure Brief
              <span className="ml-2 rounded bg-[var(--color-bg-muted)] px-2 py-0.5 text-[10px] font-normal uppercase tracking-wide text-[var(--color-text-muted)]">
                dev only · deploy blocked
              </span>
            </h2>
            <StructureBrief enabled={authed} />
          </section>
        </div>
      ) : (
        <TokenGate onAuthed={(t) => setToken(t)} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Token gate
// ---------------------------------------------------------------------------

function TokenGate({ onAuthed }: { onAuthed: (token: string) => void }) {
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!value.trim()) return;
    setChecking(true);
    setError(null);
    try {
      // Probe /api/admin/routes as the credential check — we don't
      // want to persist a bad token into sessionStorage.
      const r = await fetch('/api/admin/routes', {
        headers: { 'X-Admin-Token': value.trim() },
      });
      if (r.status === 401) {
        setError('Invalid token.');
        return;
      }
      if (r.status === 503) {
        setError('Server has no ADMIN_TOKEN configured.');
        return;
      }
      if (!r.ok) {
        setError(`Admin API returned ${r.status}.`);
        return;
      }
      setAdminToken(value.trim());
      onAuthed(value.trim());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setChecking(false);
    }
  };

  return (
    <form
      onSubmit={onSubmit}
      className="mx-auto max-w-md rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-6"
    >
      <div className="mb-3 flex items-center gap-2 text-sm text-[var(--color-text-primary)]">
        <Lock size={14} />
        Enter admin token
      </div>
      <p className="mb-4 text-xs text-[var(--color-text-muted)]">
        The token is stored in sessionStorage for this tab only. Close the tab and you'll be
        prompted again.
      </p>
      <input
        type="password"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="X-Admin-Token"
        data-testid="admin-token-input"
        className="mb-3 w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-3 py-2 text-sm text-[var(--color-text-primary)] focus:border-[var(--color-accent-blue)] focus:outline-none"
      />
      {error && <div className="mb-3 text-xs text-[var(--bear)]" data-testid="admin-error">{error}</div>}
      <button
        type="submit"
        disabled={checking}
        data-testid="admin-submit"
        className="flex w-full items-center justify-center gap-1.5 rounded bg-[var(--color-accent-blue)] px-4 py-2 text-sm font-medium text-[var(--on-brand)] disabled:opacity-50"
      >
        {checking ? <Loader2 size={14} className="animate-spin" /> : null}
        Unlock
      </button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Routing panel
//
// Audit 2026-05-08 G.P2.4 dormancy note: this dashboard is intentionally
// kept available even though all 7 roles seed at the same provider/model
// (vertex:gemini-2.0-flash) on a fresh install. The UI lets an operator
// A/B a single role without code changes — e.g. swap `judge` to
// gemini-2.5-pro for one week and compare verdict quality on
// insight_reports.report->'thesis' before deciding whether to
// permanently diversify. Until per-role evidence justifies it, this
// stays a single-model deployment by design (not a bug).
// ---------------------------------------------------------------------------

function RoutingPanel({ onLogout, showLogout = true }: { onLogout: () => void; showLogout?: boolean }) {
  const routesQuery = useAdminRoutes(true);
  const modelsQuery = useAdminModels(true);
  const updateMut = useUpdateAdminRoute();
  const [draft, setDraft] = useState<Record<string, { provider: string; model: string }>>({});

  // Log-out on any 401 (token expired / changed on server)
  if (routesQuery.error?.message === 'unauthorized') {
    clearAdminToken();
    onLogout();
    return null;
  }

  const routes = routesQuery.data?.routes ?? [];
  const models = modelsQuery.data?.models ?? [];

  const getDraft = (role: string, field: 'provider' | 'model') => {
    const row = routes.find((r) => r.role === role);
    return draft[role]?.[field] ?? row?.[field] ?? '';
  };

  const setDraftField = (role: string, field: 'provider' | 'model', value: string) => {
    setDraft((d) => {
      const row = routes.find((r) => r.role === role);
      const existing = d[role] ?? {
        provider: row?.provider ?? '',
        model: row?.model ?? '',
      };
      return { ...d, [role]: { ...existing, [field]: value } };
    });
  };

  const isDirty = (role: string) => {
    const row = routes.find((r) => r.role === role);
    if (!row) return false;
    const d = draft[role];
    if (!d) return false;
    return d.provider !== row.provider || d.model !== row.model;
  };

  const onSave = async (role: string) => {
    const d = draft[role];
    if (!d) return;
    await updateMut.mutateAsync({ role, provider: d.provider, model: d.model });
    setDraft((prev) => {
      const next = { ...prev };
      delete next[role];
      return next;
    });
  };

  if (routesQuery.isLoading || modelsQuery.isLoading) {
    return (
      <div className="flex items-center justify-center p-8 text-[var(--color-text-muted)]">
        <Loader2 size={18} className="animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-[var(--color-text-primary)]">Model Routing</h2>
        {showLogout && (
          <button
            onClick={onLogout}
            className="flex items-center gap-1 rounded border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
            data-testid="admin-logout"
          >
            <LogOut size={12} /> Sign out
          </button>
        )}
      </div>

      <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]" data-testid="admin-routes-table">
        <table className="w-full text-xs">
          <thead className="bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]">
            <tr>
              <th className="px-3 py-2 text-left">Role</th>
              <th className="px-3 py-2 text-left">Provider</th>
              <th className="px-3 py-2 text-left">Model</th>
              <th className="px-3 py-2 text-left">Updated</th>
              <th className="px-3 py-2 text-right"></th>
            </tr>
          </thead>
          <tbody>
            {routes.map((r) => {
              const selectedProvider = getDraft(r.role, 'provider');
              const selectedModel = getDraft(r.role, 'model');
              const providerOptions = Array.from(new Set(models.map((m) => m.provider)));
              const modelOptions = models.filter((m) => m.provider === selectedProvider);
              return (
                <tr key={r.role} className="border-t border-[var(--color-border)]">
                  <td className="px-3 py-2 font-mono">{r.role}</td>
                  <td className="px-3 py-2">
                    <select
                      value={selectedProvider}
                      onChange={(e) => {
                        const p = e.target.value;
                        setDraftField(r.role, 'provider', p);
                        // Reset model to first available one for that provider
                        const first = models.find((m) => m.provider === p);
                        if (first) setDraftField(r.role, 'model', first.model);
                      }}
                      data-testid={`provider-${r.role}`}
                      className="rounded border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-2 py-1 text-xs text-[var(--color-text-primary)]"
                    >
                      {providerOptions.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <ModelSelect
                      role={r.role}
                      value={selectedModel}
                      options={modelOptions}
                      onChange={(v) => setDraftField(r.role, 'model', v)}
                    />
                  </td>
                  <td className="px-3 py-2 text-[10px] text-[var(--color-text-muted)]">
                    {r.updated_at ? new Date(r.updated_at).toLocaleString() : '—'}
                    {r.updated_by ? ` · ${r.updated_by}` : ''}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => onSave(r.role)}
                      disabled={!isDirty(r.role) || updateMut.isPending}
                      data-testid={`save-${r.role}`}
                      className="inline-flex items-center gap-1 rounded bg-[var(--color-accent-blue)] px-2 py-1 text-[10px] text-[var(--on-brand)] disabled:opacity-40"
                    >
                      <Save size={11} />
                      Save
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {updateMut.error && (
        <div className="text-xs text-[var(--bear)]">
          {updateMut.error.message}
        </div>
      )}
    </div>
  );
}

function ModelSelect({
  role,
  value,
  options,
  onChange,
}: {
  role: string;
  value: string;
  options: AvailableModelRow[];
  onChange: (v: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      data-testid={`model-${role}`}
      className="rounded border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-2 py-1 text-xs text-[var(--color-text-primary)]"
    >
      {options.map((m) => (
        <option key={m.model} value={m.model} disabled={!m.has_credentials}>
          {m.model}
          {m.has_credentials ? '' : ' (no creds)'}
          {` · $${m.input_usd_per_mtok}/$${m.output_usd_per_mtok}`}
        </option>
      ))}
    </select>
  );
}
