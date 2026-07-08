import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { useTickerStore } from '@/stores/tickerStore';
import { FileText, AlertTriangle } from 'lucide-react';

interface ReportEntry {
  filename: string;
  phase: string;
  path: string;
}

function phaseLabel(phase: string): string {
  // "phase1_strat_mining_iwm" → "Phase 1: Strat Mining"
  // "phase6_playbook" → "Phase 6: Playbook"
  return phase
    .replace(/^phase(\d+)/, 'Phase $1:')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

interface ReportListResponse {
  ticker: string;
  reports: ReportEntry[];
}

function useReportList(ticker: string) {
  return useQuery<ReportListResponse>({
    queryKey: ['report-list', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/reports/list/${ticker}`);
      if (!r.ok) throw new Error('Failed to fetch report list');
      return r.json();
    },
    staleTime: 60_000,
  });
}

function useReportContent(ticker: string, phase: string, enabled: boolean) {
  return useQuery<string>({
    queryKey: ['report-content', ticker, phase],
    queryFn: async () => {
      const r = await fetch(`/api/reports/${ticker}/${phase}`);
      if (!r.ok) throw new Error('Report not found');
      return r.text();
    },
    enabled: enabled && !!ticker && !!phase,
    staleTime: 300_000,
  });
}

// Configure marked for GFM (tables, strikethrough, etc.)
marked.setOptions({ gfm: true, breaks: false });

/** Markdown -> sanitized HTML. Reports are pipeline-generated, but embedded
 * third-party text (news headlines etc.) must never execute in the app. */
export function renderReportHtml(markdown: string): string {
  return DOMPurify.sanitize(marked.parse(markdown) as string);
}

function ReportViewer({ ticker, phase }: { ticker: string; phase: string }) {
  const { data: content, isLoading, isError } = useReportContent(ticker, phase, true);

  const html = useMemo(() => {
    if (!content) return '';
    return renderReportHtml(content);
  }, [content]);

  if (isLoading) {
    return (
      <div className="p-8 text-center text-sm text-[var(--color-text-muted)]">
        Loading report…
      </div>
    );
  }

  if (isError || !content) {
    return (
      <div className="flex items-center gap-2 p-4 text-sm text-[var(--warn)]">
        <AlertTriangle size={16} />
        Report not available.
      </div>
    );
  }

  return (
    <div
      className="prose-report max-w-none p-4"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export default function ReportsPage() {
  const { activeTicker } = useTickerStore();
  const [selectedPhase, setSelectedPhase] = useState<string>('');

  const { data: listData, isLoading: listLoading, isError: listError } = useReportList(activeTicker);
  const reports = listData?.reports ?? [];
  const activePhase = selectedPhase || (reports[0]?.phase ?? '');

  return (
    <div className="flex h-full gap-4">
      {/* Sidebar: report list */}
      <div className="w-52 shrink-0 space-y-1">
        <h2 className="px-2 pb-1 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
          Reports — {activeTicker}
        </h2>

        {listError && (
          <div className="px-2 text-xs text-[var(--warn)]">No reports found</div>
        )}
        {listLoading && (
          <div className="px-2 text-xs text-[var(--color-text-muted)]">Loading…</div>
        )}

        {reports.map(r => (
          <button
            key={r.phase}
            onClick={() => setSelectedPhase(r.phase)}
            className={`flex w-full items-center gap-2 rounded px-2 py-2 text-left text-xs ${
              activePhase === r.phase
                ? 'bg-[var(--color-accent-blue)]/10 text-[var(--color-accent-blue)]'
                : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]'
            }`}
          >
            <FileText size={12} className="shrink-0" />
            <span className="truncate">{phaseLabel(r.phase)}</span>
          </button>
        ))}

        {!listLoading && !listError && reports.length === 0 && (
          <div className="px-2 text-xs text-[var(--color-text-muted)]">
            No reports yet. Run the analysis pipeline to generate them.
          </div>
        )}
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1 overflow-y-auto rounded-xl bg-[var(--surface-2)]">
        {activePhase ? (
          <ReportViewer ticker={activeTicker} phase={activePhase} />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-[var(--color-text-muted)]">
            Select a report from the sidebar
          </div>
        )}
      </div>
    </div>
  );
}
