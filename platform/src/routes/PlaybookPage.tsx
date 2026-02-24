import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTickerStore } from '@/stores/tickerStore';
import { CheckCircle, Circle, TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react';


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

function ConditionChecklist({
  conditions,
  checked,
  onToggle,
}: {
  conditions: string[];
  checked: boolean[];
  onToggle: (i: number) => void;
}) {
  return (
    <div className="space-y-1.5">
      {conditions.map((cond, i) => (
        <button
          key={i}
          onClick={() => onToggle(i)}
          className="flex w-full items-start gap-2 text-left"
        >
          {checked[i] ? (
            <CheckCircle size={14} className="mt-0.5 shrink-0 text-green-400" />
          ) : (
            <Circle size={14} className="mt-0.5 shrink-0 text-[var(--color-text-muted)]" />
          )}
          <span
            className={`text-xs leading-relaxed ${
              checked[i]
                ? 'text-[var(--color-text-primary)]'
                : 'text-[var(--color-text-muted)]'
            }`}
          >
            {cond}
          </span>
        </button>
      ))}
    </div>
  );
}

function PlaybookCardUI({ card }: { card: PlaybookCard }) {
  const [checked, setChecked] = useState<boolean[]>(card.conditions.map(() => false));

  const metCount = checked.filter(Boolean).length;
  const total = card.conditions.length;
  const pct = total > 0 ? Math.round((metCount / total) * 100) : 0;

  const isCall = card.direction === 'CALL';
  const isPut = card.direction === 'PUT';

  const toggle = (i: number) => setChecked(prev => prev.map((v, j) => (j === i ? !v : v)));
  const reset = () => setChecked(card.conditions.map(() => false));

  return (
    <div
      className={`rounded-lg border p-4 ${
        metCount === total && total > 0
          ? isCall
            ? 'border-green-500/40 bg-green-500/5'
            : isPut
            ? 'border-red-500/40 bg-red-500/5'
            : 'border-[var(--color-accent-blue)]/40 bg-[var(--color-accent-blue)]/5'
          : 'border-[var(--color-border)] bg-[var(--color-bg-secondary)]'
      }`}
    >
      {/* Header */}
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            {isCall && <TrendingUp size={14} className="text-green-400" />}
            {isPut && <TrendingDown size={14} className="text-red-400" />}
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
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${
            isCall ? 'bg-green-500/20 text-green-400' :
            isPut ? 'bg-red-500/20 text-red-400' :
            'bg-[var(--color-accent-blue)]/20 text-[var(--color-accent-blue)]'
          }`}
        >
          {card.direction}
        </span>
      </div>

      {/* Progress bar */}
      {total > 0 && (
        <div className="mb-3">
          <div className="mb-1 flex justify-between text-[10px] text-[var(--color-text-muted)]">
            <span>{metCount}/{total} conditions met</span>
            <span>{pct}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-bg-tertiary)]">
            <div
              className={`h-full rounded-full transition-all duration-300 ${
                pct === 100
                  ? isCall ? 'bg-green-400' : isPut ? 'bg-red-400' : 'bg-[var(--color-accent-blue)]'
                  : 'bg-[var(--color-text-muted)]'
              }`}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {/* Conditions */}
      <ConditionChecklist conditions={card.conditions} checked={checked} onToggle={toggle} />

      {/* Stats + reset */}
      <div className="mt-3 flex items-center justify-between border-t border-[var(--color-border)] pt-2">
        <div className="flex gap-4 text-[10px] text-[var(--color-text-muted)]">
          {card.win_rate !== null && (
            <span>
              Win Rate: <span className="text-[var(--color-text-primary)]">{card.win_rate.toFixed(0)}%</span>
            </span>
          )}
          {card.avg_return !== null && (
            <span>
              Avg Return: <span className={card.avg_return >= 0 ? 'text-green-400' : 'text-red-400'}>
                {card.avg_return >= 0 ? '+' : ''}{card.avg_return.toFixed(1)}%
              </span>
            </span>
          )}
        </div>
        {metCount > 0 && (
          <button
            onClick={reset}
            className="text-[10px] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
          >
            Reset
          </button>
        )}
      </div>
    </div>
  );
}

export default function PlaybookPage() {
  const { activeTicker } = useTickerStore();
  const { data, isLoading, isError } = usePlaybook(activeTicker);

  const cards = data?.cards ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-[var(--color-text-primary)]">
            {activeTicker} Playbook
          </h1>
          <p className="text-xs text-[var(--color-text-muted)]">
            Decision cards with interactive condition checklists
          </p>
        </div>
        {data && (
          <span className="text-xs text-[var(--color-text-muted)]">
            {cards.length} setups
          </span>
        )}
      </div>

      {isError && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-400">
          <AlertTriangle size={16} />
          Playbook not found — run the phase 6 playbook generation for {activeTicker} first.
        </div>
      )}

      {isLoading && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-8 text-center text-sm text-[var(--color-text-muted)]">
          Loading playbook…
        </div>
      )}

      {!isLoading && !isError && cards.length === 0 && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-8 text-center text-sm text-[var(--color-text-muted)]">
          No playbook cards found for {activeTicker}.
          Generate a playbook by running <code className="font-mono">scripts/run_pipeline.py</code>.
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {cards.map(card => (
          <PlaybookCardUI key={card.id} card={card} />
        ))}
      </div>
    </div>
  );
}
