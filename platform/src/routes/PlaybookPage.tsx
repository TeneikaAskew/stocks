import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTickerStore } from '@/stores/tickerStore';
import { useLiveStatus } from '@/hooks/useLiveStatus';
import { useLiveQuote } from '@/hooks/useLiveQuote';
import { useLiveHistory, useAvgVolume } from '@/hooks/useLiveHistory';
import { useLiveIndicators } from '@/hooks/useLiveIndicators';
import {
  buildSnapshot,
  type MarketSnapshot,
  type EvalResult,
} from '@/lib/playbookEvaluator';
import { usePlaybookBatch } from '@/hooks/usePlaybookEvaluation';
import { CheckCircle, Circle, HelpCircle, TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react';

interface PlaybookCard {
  id: string;
  name: string;
  description: string;
  direction: 'CALL' | 'PUT' | 'NEUTRAL';
  conditions: string[];
  win_rate: number | null;
  avg_return: number | null;
}

interface PlaybookResponse {
  ticker: string;
  cards: PlaybookCard[];
}

interface ReferenceResponse {
  ticker: string;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

function usePlaybook(ticker: string) {
  return useQuery<PlaybookResponse>({
    queryKey: ['playbook', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/playbook/${ticker}`);
      if (!r.ok) throw new Error('Failed to fetch playbook');
      return r.json();
    },
    staleTime: 3_600_000,
  });
}

function useReference(ticker: string) {
  const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  return useQuery<ReferenceResponse | null>({
    queryKey: ['reference', ticker, today],
    queryFn: async () => {
      const r = await fetch(`/api/market/reference/${ticker}/${today}`);
      if (!r.ok) return null;
      return r.json();
    },
    staleTime: 3_600_000,
  });
}

// ── Card UI ────────────────────────────────────────────────────────────────

function dirColors(dir: PlaybookCard['direction']) {
  if (dir === 'CALL') {
    return {
      text: 'text-[var(--bull)]',
      bg: 'bg-green-500/20',
      bgSoft: 'bg-green-500/5',
      border: 'border-green-500/40',
      borderIdle: 'border-green-500/10',
      bar: 'bg-green-400',
      icon: 'text-[var(--bull)]',
    };
  }
  if (dir === 'PUT') {
    return {
      text: 'text-[var(--bear)]',
      bg: 'bg-red-500/20',
      bgSoft: 'bg-red-500/5',
      border: 'border-red-500/40',
      borderIdle: 'border-red-500/10',
      bar: 'bg-red-400',
      icon: 'text-[var(--bear)]',
    };
  }
  return {
    text: 'text-[var(--color-accent-blue)]',
    bg: 'bg-[var(--color-accent-blue)]/20',
    bgSoft: 'bg-[var(--color-accent-blue)]/5',
    border: 'border-[var(--color-accent-blue)]/40',
    borderIdle: 'border-[var(--color-accent-blue)]/10',
    bar: 'bg-[var(--color-accent-blue)]',
    icon: 'text-[var(--color-accent-blue)]',
  };
}

function ConditionRow({ condition, result, color }: {
  condition: string;
  result: EvalResult;
  color: ReturnType<typeof dirColors>;
}) {
  const isMet = result.status === 'met';
  const isUnknown = result.status === 'unknown';

  return (
    <div className="flex w-full items-start gap-2 text-left">
      {isMet ? (
        <CheckCircle size={14} className={`mt-0.5 shrink-0 ${color.icon}`} />
      ) : isUnknown ? (
        <HelpCircle size={14} className="mt-0.5 shrink-0 text-[var(--color-text-muted)] opacity-60" />
      ) : (
        <Circle size={14} className="mt-0.5 shrink-0 text-[var(--color-text-muted)]" />
      )}
      <div className="flex-1 min-w-0">
        <div
          className={`text-xs leading-relaxed ${
            isMet
              ? 'text-[var(--color-text-primary)]'
              : 'text-[var(--color-text-muted)]'
          }`}
        >
          {condition}
        </div>
        {result.status !== 'unknown' && 'detail' in result && (
          <div className="font-mono text-[10px] text-[var(--color-text-muted)]">{result.detail}</div>
        )}
        {isUnknown && (
          <div className="font-mono text-[10px] text-[var(--color-text-muted)] opacity-70">{result.reason}</div>
        )}
      </div>
    </div>
  );
}

function PlaybookCardUI({ card, results, hasLiveData }: {
  card: PlaybookCard;
  results: EvalResult[];
  hasLiveData: boolean;
}) {
  const color = dirColors(card.direction);
  const total = card.conditions.length;
  const metCount = results.filter(r => r.status === 'met').length;
  const unknownCount = results.filter(r => r.status === 'unknown').length;
  const autoEvaluable = total - unknownCount;
  const pct = total > 0 ? Math.round((metCount / total) * 100) : 0;

  // Tint strength: idle until something is met, brighter as more fill in.
  // "Fully lit" = every auto-evaluable condition is met AND at least one was auto-evaluable.
  const allAutoMet = autoEvaluable > 0 && metCount === autoEvaluable;
  const tintClass =
    !hasLiveData ? 'border-[var(--color-border)] bg-[var(--color-bg-secondary)]' :
    metCount === 0 ? `${color.borderIdle} bg-[var(--color-bg-secondary)]` :
    allAutoMet ? `${color.border} ${color.bgSoft}` :
    `${color.borderIdle} ${color.bgSoft}`;

  const isCall = card.direction === 'CALL';
  const isPut = card.direction === 'PUT';

  return (
    <div className={`rounded-lg border p-4 transition-colors ${tintClass}`}>
      {/* Header */}
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {isCall && <TrendingUp size={14} className="text-[var(--bull)] shrink-0" />}
            {isPut && <TrendingDown size={14} className="text-[var(--bear)] shrink-0" />}
            <span className="text-sm font-semibold text-[var(--color-text-primary)]">
              {card.name}
            </span>
          </div>
          {card.description && (
            <p className="mt-0.5 text-xs text-[var(--color-text-muted)] leading-relaxed">
              {card.description}
            </p>
          )}
        </div>
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${color.bg} ${color.text}`}>
          {card.direction}
        </span>
      </div>

      {/* Progress bar */}
      {total > 0 && (
        <div className="mb-3">
          <div className="mb-1 flex justify-between text-[10px] text-[var(--color-text-muted)]">
            <span>
              {hasLiveData
                ? <>
                    {metCount}/{total} conditions met
                    {unknownCount > 0 && (
                      <span className="opacity-70"> · {unknownCount} subjective</span>
                    )}
                  </>
                : <>{total} conditions (no live data)</>}
            </span>
            <span>{hasLiveData ? `${pct}%` : '—'}</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-bg-tertiary)]">
            <div
              className={`h-full rounded-full transition-all duration-300 ${color.bar}`}
              style={{ width: `${hasLiveData ? pct : 0}%` }}
            />
          </div>
        </div>
      )}

      {/* Conditions */}
      <div className="space-y-1.5">
        {card.conditions.map((cond, i) => (
          <ConditionRow key={i} condition={cond} result={results[i]} color={color} />
        ))}
      </div>

      {/* Stats */}
      <div className="mt-3 flex items-center justify-between border-t border-[var(--color-border)] pt-2">
        <div className="flex gap-4 text-[10px] text-[var(--color-text-muted)]">
          {card.win_rate !== null && (
            <span>
              Win Rate: <span className="text-[var(--color-text-primary)]">{card.win_rate.toFixed(0)}%</span>
            </span>
          )}
          {card.avg_return !== null && (
            <span>
              Avg Return: <span className={card.avg_return >= 0 ? 'text-[var(--bull)]' : 'text-[var(--bear)]'}>
                {card.avg_return >= 0 ? '+' : ''}{card.avg_return.toFixed(1)}%
              </span>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function PlaybookPage() {
  const { activeTicker } = useTickerStore();

  const { data, isLoading, isError } = usePlaybook(activeTicker);
  const { data: status } = useLiveStatus();
  const isMarketOpenish = !!status?.is_open || status?.session === 'pre-market' || status?.session === 'after-hours';

  const { data: history } = useLiveHistory(activeTicker, isMarketOpenish);
  const { data: quote } = useLiveQuote(activeTicker, isMarketOpenish);
  const { data: avgVol } = useAvgVolume(activeTicker);
  const { data: reference } = useReference(activeTicker);
  // Indicators computed server-side — lib/indicators.py is the single source of truth.
  const indicatorsQuery = useLiveIndicators(
    {
      bars: history?.bars ?? [],
      current_price: quote?.price ?? null,
      current_volume: quote?.volume ?? null,
      avg_volume_20d: avgVol?.avg_volume_20d ?? null,
    },
    !!history?.bars && history.bars.length > 0,
  );

  const snapshot = useMemo<MarketSnapshot | null>(
    () =>
      buildSnapshot({
        bars: history?.bars,
        quote,
        avgVolume20d: avgVol?.avg_volume_20d ?? null,
        reference: reference ?? undefined,
        indicators: indicatorsQuery.data?.indicators,
      }),
    [history, quote, avgVol, reference, indicatorsQuery.data],
  );

  const cards = data?.cards ?? [];
  const hasLiveData = snapshot !== null;

  // Server-side evaluation (platform/api/routers/playbook.py). One batched
  // POST per snapshot/card-set combination, results keyed by card id.
  const batches = useMemo<Record<string, string[]> | undefined>(() => {
    if (cards.length === 0) return undefined;
    const b: Record<string, string[]> = {};
    for (const card of cards) b[card.id] = card.conditions;
    return b;
  }, [cards]);
  const batchQuery = usePlaybookBatch(batches, snapshot);
  const cardResults = batchQuery.data ?? new Map<string, EvalResult[]>();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[22px] font-bold tracking-[-0.02em] text-[var(--on-surface)]">
            {activeTicker} Playbook
          </h1>
          <p className="text-xs text-[var(--color-text-muted)]">
            {hasLiveData
              ? 'Cards light up as live market conditions are met'
              : 'No live data — evaluation paused'}
          </p>
        </div>
        {data && (
          <span className="text-xs text-[var(--color-text-muted)]">
            {cards.length} setups
          </span>
        )}
      </div>

      {isError && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-[var(--warn)]">
          <AlertTriangle size={16} />
          Playbook not found — run the phase 6 playbook generation for {activeTicker} first.
        </div>
      )}

      {isLoading && (
        <div className="rounded-xl bg-[var(--surface-2)] p-8 text-center text-sm text-[var(--color-text-muted)]">
          Loading playbook…
        </div>
      )}

      {!isLoading && !isError && cards.length === 0 && (
        <div className="rounded-xl bg-[var(--surface-2)] p-8 text-center text-sm text-[var(--color-text-muted)]">
          No playbook cards found for {activeTicker}.
          Generate a playbook by running <code className="font-mono">scripts/run_pipeline.py</code>.
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {cards.map(card => (
          <PlaybookCardUI
            key={card.id}
            card={card}
            results={cardResults.get(card.id) ?? card.conditions.map(() => ({ status: 'unknown', reason: 'no data' }))}
            hasLiveData={hasLiveData}
          />
        ))}
      </div>
    </div>
  );
}
