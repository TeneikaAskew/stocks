import { useEffect, useState } from 'react';
import { Loader2, RefreshCw, History as HistoryIcon, FileText } from 'lucide-react';
import { useTickerStore } from '@/stores/tickerStore';
import {
  useInsightHistory,
  useInsightReport,
  useRefreshInsight,
  useRunStatus,
} from '@/hooks/useInsights';
import {
  CatalystsCard,
  DebateCard,
  DegradationBanner,
  HeaderCard,
  KeyLevelsCard,
  RiskFlagsCard,
  SignalsCard,
  SimilarTradesCard,
  StratCard,
  TradePlanCard,
} from '@/components/insights/ReportCards';

type Tab = 'report' | 'history';

export default function InsightsPage() {
  const { activeTicker } = useTickerStore();
  const [tab, setTab] = useState<Tab>('report');
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);

  const reportQuery = useInsightReport(activeTicker);
  const historyQuery = useInsightHistory(activeTicker, 20);
  const refreshMut = useRefreshInsight();
  const runStatus = useRunStatus(currentRunId, activeTicker);

  // Clear run tracking once the run finishes so the spinner stops.
  useEffect(() => {
    if (runStatus.data && (runStatus.data.status === 'done' || runStatus.data.status === 'failed')) {
      // Keep the id for a beat so the banner can show the final state,
      // then clear.
      const t = setTimeout(() => setCurrentRunId(null), 1500);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [runStatus.data]);

  const onRefresh = async () => {
    try {
      const res = await refreshMut.mutateAsync(activeTicker);
      setCurrentRunId(res.run_id);
    } catch (e) {
      console.error('refresh failed', e);
    }
  };

  const isRunning = !!currentRunId && runStatus.data?.status !== 'done' && runStatus.data?.status !== 'failed';

  return (
    <div className="flex h-full flex-col gap-3" style={{ maxHeight: 'calc(100vh - 120px)' }}>
      {/* Tab bar */}
      <div className="flex items-center gap-2">
        <TabButton active={tab === 'report'} onClick={() => setTab('report')} icon={<FileText size={14} />}>
          Report
        </TabButton>
        <TabButton active={tab === 'history'} onClick={() => setTab('history')} icon={<HistoryIcon size={14} />}>
          History
        </TabButton>

        <div className="ml-auto flex items-center gap-3">
          {isRunning && (
            <span className="flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
              <Loader2 size={12} className="animate-spin" />
              {runStatus.data?.status ?? 'queued'}…
            </span>
          )}
          <button
            onClick={onRefresh}
            disabled={refreshMut.isPending || isRunning}
            className="flex items-center gap-1.5 rounded-lg bg-[var(--color-accent-blue)] px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
          >
            {refreshMut.isPending || isRunning ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <RefreshCw size={14} />
            )}
            Re-analyze
          </button>
        </div>
      </div>

      {/* Tab body */}
      <div className="flex-1 overflow-y-auto">
        {tab === 'report' ? (
          <ReportView
            loading={reportQuery.isLoading}
            envelope={reportQuery.data ?? null}
            error={reportQuery.error ?? null}
            onRefresh={onRefresh}
            refreshing={refreshMut.isPending || isRunning}
          />
        ) : (
          <HistoryView loading={historyQuery.isLoading} data={historyQuery.data} />
        )}
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors ${
        active
          ? 'bg-[var(--color-accent-blue)] text-white'
          : 'border border-[var(--color-border)] bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
      }`}
    >
      {icon}
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Report view
// ---------------------------------------------------------------------------

function ReportView({
  loading,
  envelope,
  error,
  onRefresh,
  refreshing,
}: {
  loading: boolean;
  envelope: import('@/types/insights').InsightReportEnvelope | null;
  error: Error | null;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 size={24} className="animate-spin text-[var(--color-text-muted)]" />
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-300">
        Failed to load report: {error.message}
      </div>
    );
  }
  if (!envelope) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <FileText size={32} className="text-[var(--color-text-muted)]" />
        <div>
          <div className="text-sm font-medium text-[var(--color-text-primary)]">No report yet</div>
          <div className="mt-1 text-xs text-[var(--color-text-muted)]">
            Generate the first AI insight report for this ticker.
          </div>
        </div>
        <button
          onClick={onRefresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 rounded-lg bg-[var(--color-accent-blue)] px-4 py-2 text-xs font-medium text-white disabled:opacity-50"
        >
          {refreshing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Generate Report
        </button>
      </div>
    );
  }
  const report = envelope.report;
  return (
    <div className="space-y-3">
      <DegradationBanner failedSections={report.failed_sections} />
      <HeaderCard
        report={report}
        asOf={envelope.as_of}
        costUsd={envelope.cost_usd}
        latencyMs={envelope.latency_ms}
      />
      <div className="grid gap-3 md:grid-cols-2">
        <TradePlanCard report={report} />
        <KeyLevelsCard levels={report.key_levels} />
        <StratCard strat={report.strat_status} />
        <CatalystsCard catalysts={report.catalysts} />
      </div>
      <DebateCard bullCase={report.bull_case} bearCase={report.bear_case} />
      <div className="grid gap-3 md:grid-cols-2">
        <RiskFlagsCard flags={report.risk_flags} />
        <SignalsCard signals={report.supporting_signals} />
      </div>
      <SimilarTradesCard trades={report.similar_past_trades} />
      <div className="text-center text-[10px] text-[var(--color-text-muted)]">
        {Object.entries(report.model_versions)
          .map(([role, v]) => `${role}: ${v}`)
          .join(' · ')}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// History view — scannable list of recent runs
// ---------------------------------------------------------------------------

function HistoryView({
  loading,
  data,
}: {
  loading: boolean;
  data: import('@/types/insights').InsightHistoryResponse | undefined;
}) {
  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 size={24} className="animate-spin text-[var(--color-text-muted)]" />
      </div>
    );
  }
  if (!data || data.reports.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-[var(--color-text-muted)]">
        No history yet.
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {data.reports.map((r) => (
        <div
          key={r.id}
          className="rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-3"
        >
          <div className="mb-1 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span
                className={`rounded border px-2 py-0.5 text-[10px] font-semibold uppercase ${
                  r.direction === 'long'
                    ? 'border-emerald-500/40 bg-emerald-500/20 text-emerald-400'
                    : r.direction === 'short'
                    ? 'border-rose-500/40 bg-rose-500/20 text-rose-400'
                    : 'border-zinc-500/40 bg-zinc-500/20 text-zinc-400'
                }`}
              >
                {r.direction} · {r.conviction}
              </span>
              <span className="text-xs text-[var(--color-text-muted)]">
                {new Date(r.as_of).toLocaleString()}
              </span>
            </div>
            {r.cost_usd !== null && (
              <span className="text-[10px] text-[var(--color-text-muted)]">
                ${r.cost_usd.toFixed(4)}
              </span>
            )}
          </div>
          <p className="text-xs leading-relaxed text-[var(--color-text-secondary)]">{r.thesis}</p>
        </div>
      ))}
    </div>
  );
}
