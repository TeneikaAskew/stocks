import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  InsightHistoryResponse,
  InsightReportEnvelope,
  RefreshResponse,
  RunStatus,
} from '@/types/insights';

// Brief direction surface — the premarket-brief's view of the same
// ticker, fetched alongside the insight report so the UI can flag
// when the two house views diverge. Audit 2026-05-08 G.P1.8.
export interface BriefDirection {
  ticker: string;
  bias: 'bullish' | 'bearish' | 'neutral';
  signal_status: string | null;
  ftfc_direction: 'bullish' | 'bearish' | 'mixed' | null;
}

export function useBriefDirection(ticker: string) {
  return useQuery<BriefDirection | null>({
    queryKey: ['brief-direction', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/dashboard/brief/${ticker}`);
      if (r.status === 404) return null;
      if (!r.ok) throw new Error(`brief ${r.status}`);
      const json = await r.json();
      return {
        ticker,
        bias: json.bias ?? 'neutral',
        signal_status: json.premarket?.signal_status ?? null,
        ftfc_direction:
          json.premarket?.ftfc_direction ?? json.daily?.ftfc_direction ?? null,
      };
    },
    enabled: !!ticker,
    staleTime: 60_000,
  });
}

// ---------------------------------------------------------------------------
// GET latest report for ticker. 404 means the pipeline has never run for
// this ticker — the UI shows a "Generate Report" CTA in that case.
// ---------------------------------------------------------------------------

// `asOf` (ISO date, YYYY-MM-DD) selects the latest report dated on or before
// that cutoff — used by the dashboard's historical "view as of" mode. Omitted
// → latest live report.
export function useInsightReport(ticker: string, asOf?: string) {
  return useQuery<InsightReportEnvelope | null>({
    queryKey: ['insight-report', ticker, asOf ?? 'live'],
    queryFn: async () => {
      const qs = asOf ? `?as_of=${encodeURIComponent(asOf)}` : '';
      const r = await fetch(`/api/insights/report/${ticker}${qs}`);
      if (r.status === 404) return null;
      if (!r.ok) throw new Error(`insights ${r.status}`);
      return r.json();
    },
    enabled: !!ticker,
    staleTime: 60_000,
  });
}

// ---------------------------------------------------------------------------
// GET a specific past report by its row id — used by the History tab
// to open an older report in the full card view.
// ---------------------------------------------------------------------------

export function useInsightReportById(reportId: string | null) {
  return useQuery<InsightReportEnvelope>({
    queryKey: ['insight-report-by-id', reportId],
    queryFn: async () => {
      if (!reportId) throw new Error('no report id');
      const r = await fetch(`/api/insights/reports/${reportId}`);
      if (!r.ok) throw new Error(`insights by-id ${r.status}`);
      return r.json();
    },
    enabled: !!reportId,
    staleTime: 5 * 60_000,
  });
}

// ---------------------------------------------------------------------------
// GET history — used by the History view to render a scannable list.
// ---------------------------------------------------------------------------

export function useInsightHistory(ticker: string, limit = 20) {
  return useQuery<InsightHistoryResponse>({
    queryKey: ['insight-history', ticker, limit],
    queryFn: async () => {
      const r = await fetch(`/api/insights/report/${ticker}/history?limit=${limit}`);
      if (!r.ok) throw new Error(`insights history ${r.status}`);
      return r.json();
    },
    enabled: !!ticker,
    staleTime: 60_000,
  });
}

// ---------------------------------------------------------------------------
// POST refresh — enqueues a run and returns a run_id. The UI then polls
// useRunStatus until status transitions to 'done' or 'failed'.
// ---------------------------------------------------------------------------

// Variables accepted by the refresh mutation. ``asOf`` is optional —
// when omitted the pipeline runs against live data.
export interface RefreshVars {
  ticker: string;
  asOf?: string; // ISO date (YYYY-MM-DD) or ISO datetime
}

export function useRefreshInsight() {
  const qc = useQueryClient();
  return useMutation<RefreshResponse, Error, RefreshVars | string>({
    mutationFn: async (vars: RefreshVars | string) => {
      // Backwards compatible: accept a bare ticker string for callers
      // that don't yet pass an as_of cutoff.
      const { ticker, asOf } =
        typeof vars === 'string' ? { ticker: vars, asOf: undefined } : vars;
      const qs = asOf ? `?as_of=${encodeURIComponent(asOf)}` : '';
      const r = await fetch(`/api/insights/report/${ticker}/refresh${qs}`, {
        method: 'POST',
      });
      if (!r.ok) {
        const text = await r.text().catch(() => '');
        throw new Error(`refresh failed: ${r.status} ${text}`);
      }
      return r.json();
    },
    onSuccess: (_data, vars) => {
      // Nothing to invalidate yet — the run is still queued. The
      // run-status poll handles invalidation when it completes.
      const ticker = typeof vars === 'string' ? vars : vars.ticker;
      qc.invalidateQueries({ queryKey: ['insight-history', ticker] });
    },
  });
}

// ---------------------------------------------------------------------------
// GET run status — polled every 3s while enabled. The caller stops
// polling by setting enabled=false once status becomes terminal.
// ---------------------------------------------------------------------------

export function useRunStatus(runId: string | null, ticker: string) {
  const qc = useQueryClient();
  return useQuery<RunStatus>({
    queryKey: ['run-status', runId],
    queryFn: async () => {
      if (!runId) throw new Error('no run id');
      const r = await fetch(`/api/insights/runs/${runId}`);
      if (!r.ok) throw new Error(`run-status ${r.status}`);
      const data: RunStatus = await r.json();
      // Side-effect: when the run finishes, invalidate the report
      // and history so the UI swaps in the new data automatically.
      if (data.status === 'done') {
        qc.invalidateQueries({ queryKey: ['insight-report', ticker] });
        qc.invalidateQueries({ queryKey: ['insight-history', ticker] });
      }
      return data;
    },
    enabled: !!runId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || status === 'queued' || status === 'running') return 3_000;
      return false;
    },
  });
}
