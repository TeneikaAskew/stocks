/**
 * AI Insights → Agents tab.
 *
 * The multi-agent pipeline view, sourced entirely from the DB:
 *   - per-run cost + latency and the per-role cost breakdown come from
 *     `insight_reports` (per_role_cost / run_cost_usd / run_latency_ms /
 *     model_versions), via the report envelope.
 *   - the configured per-agent provider/model roster comes from `model_routing`
 *     via `/api/admin/routes` (admin-gated; editing lives on the Admin page).
 */
import { Network, Coins } from 'lucide-react';
import { useAdminRoutes } from '@/hooks/useAdmin';
import type { InsightReportEnvelope } from '@/types/insights';
import { Card, CardHeader, KpiTile, Pill } from '@/components/primitives';

const fmtUsd = (v?: number | null) =>
  typeof v === 'number' && Number.isFinite(v) ? `$${v.toFixed(v < 1 ? 4 : 2)}` : '—';
const fmtSecs = (ms?: number | null) =>
  typeof ms === 'number' && Number.isFinite(ms) ? `${(ms / 1000).toFixed(1)}s` : '—';
const titleCase = (s: string) => s.replace(/[_:]/g, ' ');

export function AgentsPanel({ envelope }: { envelope: InsightReportEnvelope | null }) {
  const routesQ = useAdminRoutes(true);
  const routes = routesQ.data?.routes ?? [];

  const rep = envelope?.report;
  const perRole = rep?.per_role_cost ?? {};
  const models = rep?.model_versions ?? {};
  const roleCosts = Object.entries(perRole).sort((a, b) => b[1] - a[1]);
  const maxCost = roleCosts.reduce((m, [, c]) => Math.max(m, c), 0) || 1;
  const totalCost = rep?.run_cost_usd ?? envelope?.cost_usd ?? null;
  const latency = rep?.run_latency_ms ?? envelope?.latency_ms ?? null;

  return (
    <div className="flex flex-col gap-[14px]">
      {/* Run summary (from insight_reports) */}
      <div className="grid grid-cols-2 gap-[14px] md:grid-cols-4">
        <KpiTile label="Run cost" value={fmtUsd(totalCost)} />
        <KpiTile label="Latency" value={fmtSecs(latency)} />
        <KpiTile label="Agent calls" value={roleCosts.length ? String(roleCosts.length) : '—'} />
        <KpiTile label="As of" value={envelope?.as_of?.slice(0, 10) ?? '—'} />
      </div>

      {/* Per-agent cost trace for this run */}
      <Card>
        <CardHeader
          title={<><Network size={13} className="mr-1.5 inline align-middle" />Multi-agent pipeline</>}
          meta={rep ? 'this run · cost by role' : undefined}
        />
        {roleCosts.length === 0 ? (
          <div className="py-4 text-[12px] text-[var(--on-surface-muted)]">
            No per-agent breakdown yet — generate an insight report for this ticker.
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {roleCosts.map(([key, cost]) => {
              const role = key.split(':')[0];
              const model = models[role] ?? models[key] ?? '—';
              return (
                <div key={key} className="flex items-center gap-3">
                  <div className="w-[150px] shrink-0">
                    <div className="text-[12.5px] font-semibold capitalize text-[var(--on-surface)]">{titleCase(key)}</div>
                    <div className="truncate text-[10.5px] text-[var(--on-surface-muted)]">{model}</div>
                  </div>
                  <div className="h-2 min-w-0 flex-1 rounded-full bg-[var(--surface-1)]">
                    <div className="h-2 rounded-full bg-[var(--brand)]" style={{ width: `${Math.max(4, (cost / maxCost) * 100)}%` }} />
                  </div>
                  <div className="w-[64px] shrink-0 text-right tabular-nums text-[12px] text-[var(--on-surface-variant)]">{fmtUsd(cost)}</div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* Configured routing roster (from model_routing) */}
      <Card>
        <CardHeader
          title={<><Coins size={13} className="mr-1.5 inline align-middle" />Model routing</>}
          meta="model_routing · edit in Admin"
        />
        {routesQ.isError ? (
          <div className="py-4 text-[12px] text-[var(--on-surface-muted)]">
            Admin access required to view per-agent routing.
          </div>
        ) : routes.length === 0 ? (
          <div className="py-4 text-[12px] text-[var(--on-surface-muted)]">Loading routing…</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[320px] text-[12px]">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-[var(--on-surface-label)]">
                  <th className="pb-1 font-semibold">Role</th>
                  <th className="pb-1 font-semibold">Provider</th>
                  <th className="pb-1 font-semibold">Model</th>
                </tr>
              </thead>
              <tbody>
                {routes.map((r) => (
                  <tr key={r.role} className="border-t border-[var(--outline-variant)]">
                    <td className="py-1.5 font-semibold capitalize text-[var(--on-surface)]">{titleCase(r.role)}</td>
                    <td className="py-1.5"><Pill tone="brand">{r.provider}</Pill></td>
                    <td className="py-1.5 tabular-nums text-[var(--on-surface-variant)]">{r.model}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
