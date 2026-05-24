import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Loader2, RefreshCw, History as HistoryIcon, FileText, MessageCircle, Send, ListChecks } from 'lucide-react';
import { useTickerStore } from '@/stores/tickerStore';
import {
  useBriefDirection,
  useInsightHistory,
  useInsightReport,
  useInsightReportById,
  useRefreshInsight,
  useRunStatus,
} from '@/hooks/useInsights';
import {
  BriefVsInsightsCard,
  CatalystsCard,
  DebateCard,
  DegradationBanner,
  HeaderCard,
  KeyLevelsCard,
  PersonaPlansCard,
  RiskFlagsCard,
  SignalsCard,
  SimilarTradesCard,
  StratCard,
  TradePlanCard,
} from '@/components/insights/ReportCards';
import { WatchlistPanel } from '@/components/insights/WatchlistPanel';

type Tab = 'report' | 'history' | 'chat' | 'watchlist';

export default function InsightsPage() {
  const { activeTicker, setTicker } = useTickerStore();
  const [tab, setTab] = useState<Tab>('report');
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  // Track which ticker the in-flight refresh was for so the watchlist
  // row can show its spinner only for the row the user clicked.
  const [refreshingTicker, setRefreshingTicker] = useState<string | null>(null);
  // When non-null, the Report tab shows a past report instead of latest.
  const [viewingHistoricalId, setViewingHistoricalId] = useState<string | null>(null);
  // Optional point-in-time cutoff. When set, the next Re-analyze runs
  // the pipeline against historical data only — every summarizer is
  // frozen to what was visible at this date/time.
  const [asOf, setAsOf] = useState<string>('');

  const reportQuery = useInsightReport(activeTicker);
  const historyQuery = useInsightHistory(activeTicker, 20);
  const historicalQuery = useInsightReportById(viewingHistoricalId);
  // G.P1.8 — fetch brief alongside the insight report so the divergence
  // card can compare the two house views.
  const briefQuery = useBriefDirection(activeTicker);
  const refreshMut = useRefreshInsight();
  const runStatus = useRunStatus(currentRunId, activeTicker);

  // Reset historical view when ticker changes — a saved SPY report id
  // shouldn't linger into an IWM selection.
  useEffect(() => {
    setViewingHistoricalId(null);
  }, [activeTicker]);

  // Clear run tracking once the run finishes so the spinner stops.
  useEffect(() => {
    if (runStatus.data && (runStatus.data.status === 'done' || runStatus.data.status === 'failed')) {
      // Keep the id for a beat so the banner can show the final state,
      // then clear.
      const t = setTimeout(() => {
        setCurrentRunId(null);
        setRefreshingTicker(null);
      }, 1500);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [runStatus.data]);

  const refreshFor = async (ticker: string, asOfOverride?: string) => {
    try {
      setRefreshingTicker(ticker);
      const cutoff = asOfOverride ?? asOf;
      const res = await refreshMut.mutateAsync(
        cutoff ? { ticker, asOf: cutoff } : ticker,
      );
      setCurrentRunId(res.run_id);
    } catch (e) {
      console.error('refresh failed', e);
      setRefreshingTicker(null);
    }
  };

  const onRefresh = () => refreshFor(activeTicker);

  // Watchlist row click: switch the active ticker, jump to Report tab,
  // and trigger a refresh on the selected ticker. The cast widens the
  // strict Ticker union ('IWM'|'SPY'|'QQQ') to accept any ticker the
  // ranker surfaces — the Sidebar's typed `availableTickers` list is
  // unaffected; downstream consumers of activeTicker treat it as a
  // string anyway.
  const onWatchlistGenerate = async (ticker: string) => {
    setTicker(ticker as import('@/types').Ticker);
    setTab('report');
    setViewingHistoricalId(null);
    // Watchlist generations always run live — point-in-time is an
    // explicit Report-tab opt-in, not a default.
    await refreshFor(ticker, '');
  };

  const isRunning = !!currentRunId && runStatus.data?.status !== 'done' && runStatus.data?.status !== 'failed';

  return (
    <div className="flex h-full flex-col gap-6" style={{ maxHeight: 'calc(100vh - 180px)' }}>
      {/* Page header */}
      <div>
        <h1 className="text-4xl font-bold tracking-tight text-[var(--color-brand)]">
          {activeTicker}
        </h1>
        <p className="label-micro mt-2">AI Insights</p>
      </div>

      {/* Tab bar */}
      <div className="flex items-center gap-2">
        <TabButton
          active={tab === 'report'}
          onClick={() => {
            setTab('report');
            // Returning to the Report tab via the tab button clears
            // the historical view — the user explicitly asked for
            // "the current report".
            setViewingHistoricalId(null);
          }}
          icon={<FileText size={14} />}
        >
          Report
        </TabButton>
        <TabButton active={tab === 'history'} onClick={() => setTab('history')} icon={<HistoryIcon size={14} />}>
          History
        </TabButton>
        <TabButton active={tab === 'watchlist'} onClick={() => setTab('watchlist')} icon={<ListChecks size={14} />}>
          Watchlist
        </TabButton>
        <TabButton active={tab === 'chat'} onClick={() => setTab('chat')} icon={<MessageCircle size={14} />}>
          Chat
        </TabButton>

        <div className="ml-auto flex items-center gap-3">
          {isRunning && (
            <span className="flex items-center gap-1 text-xs text-[var(--on-surface-muted)]">
              <Loader2 size={12} className="animate-spin" />
              {runStatus.data?.status ?? 'queued'}…
            </span>
          )}
          <label className="flex items-center gap-1.5 text-xs text-[var(--on-surface-muted)]">
            <span title="Point-in-time replay — runs the pipeline against data available at this date/time">
              Replay as of
            </span>
            <input
              type="datetime-local"
              value={asOf}
              onChange={(e) => setAsOf(e.target.value)}
              max={new Date().toISOString().slice(0, 16)}
              className="rounded-md border border-[var(--outline)] bg-transparent px-2 py-1 text-xs"
              aria-label="Point-in-time cutoff"
            />
            {asOf && (
              <button
                type="button"
                onClick={() => setAsOf('')}
                className="text-[var(--on-surface-muted)] hover:text-[var(--on-surface)]"
                aria-label="Clear cutoff"
                title="Clear cutoff (run live)"
              >
                ×
              </button>
            )}
          </label>
          <button
            onClick={onRefresh}
            disabled={refreshMut.isPending || isRunning}
            className="flex items-center gap-1.5 rounded-lg bg-[var(--brand-container)] px-3 py-1.5 text-xs font-medium text-[var(--on-brand)] hover:brightness-110 disabled:opacity-50"
          >
            {refreshMut.isPending || isRunning ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <RefreshCw size={14} />
            )}
            {asOf ? 'Replay' : 'Re-analyze'}
          </button>
        </div>
      </div>

      {/* Tab body */}
      <div className="flex-1 overflow-y-auto">
        {tab === 'report' ? (
          <ReportView
            loading={
              viewingHistoricalId ? historicalQuery.isLoading : reportQuery.isLoading
            }
            envelope={
              viewingHistoricalId
                ? historicalQuery.data ?? null
                : reportQuery.data ?? null
            }
            error={
              viewingHistoricalId
                ? (historicalQuery.error as Error | null)
                : (reportQuery.error as Error | null)
            }
            onRefresh={onRefresh}
            refreshing={refreshMut.isPending || isRunning}
            historical={!!viewingHistoricalId}
            onBackToLatest={() => setViewingHistoricalId(null)}
            ticker={activeTicker}
            brief={briefQuery.data ?? null}
          />
        ) : tab === 'history' ? (
          <HistoryView
            loading={historyQuery.isLoading}
            data={historyQuery.data}
            onSelect={(id) => {
              setViewingHistoricalId(id);
              setTab('report');
            }}
          />
        ) : tab === 'watchlist' ? (
          <WatchlistPanel
            onSelectTicker={onWatchlistGenerate}
            refreshing={refreshMut.isPending || isRunning}
            refreshingTicker={refreshingTicker}
          />
        ) : (
          <ChatView ticker={activeTicker} />
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
      className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
        active
          ? 'bg-[var(--brand)]/15 text-[var(--brand)]'
          : 'bg-[var(--surface-2)] text-[var(--on-surface-variant)] hover:text-[var(--on-surface)] hover:bg-[var(--surface-3)]'
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
  historical,
  onBackToLatest,
  ticker,
  brief,
}: {
  loading: boolean;
  envelope: import('@/types/insights').InsightReportEnvelope | null;
  error: Error | null;
  onRefresh: () => void;
  refreshing: boolean;
  historical: boolean;
  onBackToLatest: () => void;
  ticker: string;
  brief: import('@/hooks/useInsights').BriefDirection | null;
}) {
  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 size={24} className="animate-spin text-[var(--on-surface-muted)]" />
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-xl border border-[var(--bear)]/40 bg-[var(--bear)]/10 p-6 text-sm text-[var(--bear)]">
        Failed to load report: {error.message}
      </div>
    );
  }
  if (!envelope) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <FileText size={32} className="text-[var(--on-surface-muted)]" />
        <div>
          <div className="text-sm font-medium text-[var(--on-surface)]">No report yet</div>
          <div className="mt-1 text-xs text-[var(--on-surface-muted)]">
            Generate the first AI insight report for this ticker.
          </div>
        </div>
        <button
          onClick={onRefresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 rounded-lg bg-[var(--brand-container)] px-4 py-2 text-xs font-medium text-[var(--on-brand)] hover:brightness-110 disabled:opacity-50"
        >
          {refreshing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Generate Report
        </button>
      </div>
    );
  }
  const report = envelope.report;
  return (
    <div className="space-y-4">
      {historical && (
        <div className="flex items-center justify-between rounded-lg border border-[var(--warn)]/40 bg-[var(--warn)]/10 px-4 py-2.5 text-xs text-[var(--warn)]">
          <span>Viewing historical report — not the current latest.</span>
          <button
            onClick={onBackToLatest}
            className="flex items-center gap-1 rounded border border-[var(--warn)]/40 px-2 py-0.5 text-[10px] text-[var(--warn)] hover:bg-[var(--warn)]/10"
          >
            <ArrowLeft size={10} /> Back to latest
          </button>
        </div>
      )}
      <DegradationBanner failedSections={report.failed_sections} />
      <HeaderCard
        report={report}
        asOf={envelope.as_of}
        costUsd={envelope.cost_usd}
        latencyMs={envelope.latency_ms}
      />
      <BriefVsInsightsCard
        ticker={ticker}
        brief={brief}
        insightDirection={report.direction}
      />
      <div className="grid gap-4 md:grid-cols-2">
        <TradePlanCard report={report} />
        <KeyLevelsCard levels={report.key_levels} />
        <StratCard strat={report.strat_status} />
        <CatalystsCard catalysts={report.catalysts} />
      </div>
      <DebateCard bullCase={report.bull_case} bearCase={report.bear_case} />
      <PersonaPlansCard plans={report.persona_plans ?? []} />
      <div className="grid gap-4 md:grid-cols-2">
        <RiskFlagsCard flags={report.risk_flags} />
        <SignalsCard signals={report.supporting_signals} />
      </div>
      <SimilarTradesCard trades={report.similar_past_trades} />
      <div className="text-center text-[10px] text-[var(--on-surface-muted)]">
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
  onSelect,
}: {
  loading: boolean;
  data: import('@/types/insights').InsightHistoryResponse | undefined;
  onSelect: (reportId: string) => void;
}) {
  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 size={24} className="animate-spin text-[var(--on-surface-muted)]" />
      </div>
    );
  }
  if (!data || data.reports.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-[var(--on-surface-muted)]">
        No history yet.
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {data.reports.map((r) => (
        <button
          key={r.id}
          onClick={() => onSelect(r.id)}
          className="block w-full rounded-xl bg-[var(--surface-2)] p-4 text-left transition-colors hover:bg-[var(--surface-3)]"
        >
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span
                className={`rounded-lg border px-2 py-0.5 text-[10px] font-semibold uppercase ${
                  r.direction === 'long'
                    ? 'border-[var(--bull)]/40 bg-[var(--bull)]/20 text-[var(--bull)]'
                    : r.direction === 'short'
                    ? 'border-[var(--bear)]/40 bg-[var(--bear)]/20 text-[var(--bear)]'
                    : 'border-[var(--outline-variant)] bg-[var(--surface-3)] text-[var(--on-surface-muted)]'
                }`}
              >
                {r.direction} · {r.conviction}
              </span>
              <span className="text-xs text-[var(--on-surface-muted)]">
                {new Date(r.as_of).toLocaleString()}
              </span>
            </div>
            {r.cost_usd !== null && (
              <span className="text-[10px] text-[var(--on-surface-muted)]">
                ${r.cost_usd.toFixed(4)}
              </span>
            )}
          </div>
          <p className="text-xs leading-relaxed text-[var(--on-surface-variant)]">{r.thesis}</p>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chat view — streaming Gemini chat
// ---------------------------------------------------------------------------

type ChatMsg = { role: 'user' | 'assistant'; content: string };

const CHAT_MODES = ['chat', 'market', 'strategy', 'trade'] as const;

function ChatView({ ticker }: { ticker: string }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState('');
  const [mode, setMode] = useState<(typeof CHAT_MODES)[number]>('chat');
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput('');

    const userMsg: ChatMsg = { role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setStreaming(true);

    try {
      const resp = await fetch('/api/insights/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          mode,
          ticker,
          history: messages.slice(-6).map((m) => ({ role: m.role, content: m.content })),
        }),
      });

      if (!resp.ok || !resp.body) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: `Error: ${resp.status} ${resp.statusText}` },
        ]);
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let assistantContent = '';

      setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        assistantContent += decoder.decode(value, { stream: true });
        setMessages((prev) => {
          const copy = [...prev];
          copy[copy.length - 1] = { role: 'assistant', content: assistantContent };
          return copy;
        });
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Error: ${err instanceof Error ? err.message : String(err)}` },
      ]);
    } finally {
      setStreaming(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* Mode selector */}
      <div className="mb-3 flex items-center gap-2">
        {CHAT_MODES.map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`rounded-lg px-2.5 py-1 text-[10px] font-medium uppercase tracking-wide transition-colors ${
              mode === m
                ? 'bg-[var(--brand)]/15 text-[var(--brand)]'
                : 'bg-[var(--surface-2)] text-[var(--on-surface-muted)] hover:text-[var(--on-surface-variant)] hover:bg-[var(--surface-3)]'
            }`}
          >
            {m}
          </button>
        ))}
      </div>

      {/* Messages */}
      <div className="flex-1 flex flex-col gap-3 overflow-y-auto rounded-xl bg-[var(--surface-1)] p-4">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center text-xs text-[var(--on-surface-muted)]">
            Ask a question about {ticker} in {mode} mode.
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm leading-relaxed ${
              msg.role === 'user'
                ? 'ml-auto bg-[var(--brand)]/10 text-[var(--on-surface)]'
                : 'mr-auto bg-[var(--surface-2)] text-[var(--on-surface-variant)]'
            }`}
          >
            <div className="prose-report whitespace-pre-wrap">{msg.content}</div>
          </div>
        ))}
        {streaming && (
          <Loader2 size={14} className="animate-spin text-[var(--on-surface-muted)]" />
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="mt-3 flex items-center gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={`Ask about ${ticker}...`}
          disabled={streaming}
          className="flex-1 rounded-lg border border-[var(--outline-variant)] bg-[var(--surface-lowest)] px-3 py-2 text-sm text-[var(--on-surface)] placeholder:text-[var(--on-surface-muted)] focus:border-[var(--brand)] focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!input.trim() || streaming}
          className="flex items-center gap-1 rounded-lg bg-[var(--brand-container)] px-3 py-2 text-xs font-medium text-[var(--on-brand)] hover:brightness-110 disabled:opacity-50"
        >
          <Send size={12} />
        </button>
      </form>
    </div>
  );
}
