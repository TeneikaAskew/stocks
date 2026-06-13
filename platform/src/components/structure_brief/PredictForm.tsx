// ---------------------------------------------------------------------------
// On-Demand Predict — admin form that hits POST /api/admin/strat-engine/predict.
//
// Dev-only. Sits under /admin alongside the Structure Brief. Lets the
// admin manually invoke the model for one (ticker, timeframe, as_of_ts)
// triple and view the response in the same card visual language the
// Structure Brief uses.
//
// Language audit applies: no banned trade-edge words anywhere in this
// component's copy. The verbatim scope statement is rendered next to
// the response.
// ---------------------------------------------------------------------------

import { useState } from 'react';
import { Loader2, Play } from 'lucide-react';
import { usePredictMutation, type StratPredictRequest, type StratPredictResponse } from '@/hooks/useAdmin';
import { SCOPE_STATEMENT, formatRefreshed } from './StructureBrief';

const TICKERS = ['IWM', 'SPY', 'QQQ'] as const;
const TIMEFRAMES = ['5m', '15m', '30m'] as const;
const CLASSES_ORDER: Array<'1' | '2U' | '2D' | '3'> = ['1', '2U', '2D', '3'];

const CLASS_COLOR_VAR: Record<'1' | '2U' | '2D' | '3', string> = {
  '1': 'var(--color-text-muted)',
  '2U': 'var(--color-bull)',
  '2D': 'var(--color-bear)',
  '3': 'var(--color-warn)',
};


export function PredictForm({ enabled }: { enabled: boolean }) {
  const [ticker, setTicker] = useState<(typeof TICKERS)[number]>('IWM');
  const [timeframe, setTimeframe] = useState<(typeof TIMEFRAMES)[number]>('15m');
  const [asOf, setAsOf] = useState<string>('');
  const mutation = usePredictMutation();

  if (!enabled) return null;

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const body: StratPredictRequest = { ticker, timeframe };
    if (asOf.trim()) body.as_of_timestamp = asOf.trim();
    mutation.mutate(body);
  };

  return (
    <div className="space-y-3">
      <form
        onSubmit={onSubmit}
        className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4"
      >
        <h3 className="mb-3 text-sm font-medium text-[var(--color-text-primary)]">
          Run a structure prediction
        </h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <label className="block">
            <span className="mb-1 block text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">Ticker</span>
            <select
              value={ticker}
              onChange={(e) => setTicker(e.target.value as (typeof TICKERS)[number])}
              className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-2 py-1.5 text-sm text-[var(--color-text-primary)] focus:border-[var(--color-brand)] focus:outline-none"
              data-testid="predict-ticker"
            >
              {TICKERS.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">Timeframe</span>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value as (typeof TIMEFRAMES)[number])}
              className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-2 py-1.5 text-sm text-[var(--color-text-primary)] focus:border-[var(--color-brand)] focus:outline-none"
              data-testid="predict-timeframe"
            >
              {TIMEFRAMES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
              Bar timestamp (optional)
            </span>
            <input
              type="datetime-local"
              value={asOf}
              onChange={(e) => setAsOf(e.target.value)}
              className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-2 py-1.5 text-sm text-[var(--color-text-primary)] focus:border-[var(--color-brand)] focus:outline-none"
              data-testid="predict-as-of"
            />
          </label>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <button
            type="submit"
            disabled={mutation.isPending}
            data-testid="predict-submit"
            className="flex items-center gap-1.5 rounded bg-[var(--color-brand)] px-3 py-1.5 text-sm font-medium text-[var(--on-brand)] disabled:opacity-50"
          >
            {mutation.isPending ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Predicting…
              </>
            ) : (
              <>
                <Play size={14} />
                Predict
              </>
            )}
          </button>
          {mutation.error && (
            <span className="text-xs text-[var(--color-bear)]">
              {(mutation.error as Error).message}
            </span>
          )}
        </div>
      </form>

      {mutation.data && <PredictResultCard result={mutation.data} />}
    </div>
  );
}


function PredictResultCard({ result }: { result: StratPredictResponse }) {
  if (!result.available) {
    return (
      <div className="rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4 text-xs text-[var(--color-text-muted)]">
        <div className="mb-1 flex items-center justify-between">
          <span className="font-medium text-[var(--color-text-secondary)]">
            {result.ticker} · {result.timeframe}
          </span>
          <span className="text-[10px]">unavailable</span>
        </div>
        <div>{result.note ?? 'No model artifact available.'}</div>
        <div className="mt-3 text-[10px] italic">{result.scope_statement}</div>
      </div>
    );
  }
  return (
    <div
      className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4 text-xs"
      data-testid="predict-result"
    >
      <div className="mb-3 flex items-baseline justify-between">
        <h4 className="text-sm font-medium text-[var(--color-text-primary)]">
          {result.ticker} · {result.timeframe}
        </h4>
        <span className="text-[10px] text-[var(--color-text-muted)]">
          based on bar @ {result.ts ?? '—'}
        </span>
      </div>

      {result.muted ? (
        <div className="rounded border border-[var(--color-warn)] bg-[var(--color-bg-secondary)] p-2 text-[var(--color-warn)]">
          {result.mute_reason ?? 'model muted, ECE breach'}
        </div>
      ) : (
        <>
          <div className="mb-3 text-[var(--color-text-primary)]">
            next bar{' '}
            <span
              className="font-semibold"
              style={{ color: result.top_class ? CLASS_COLOR_VAR[result.top_class] : 'inherit' }}
            >
              {result.top_prob != null ? `${(result.top_prob * 100).toFixed(0)}%` : '—'}
            </span>{' '}
            likely to be type{' '}
            <span
              className="font-semibold"
              style={{ color: result.top_class ? CLASS_COLOR_VAR[result.top_class] : 'inherit' }}
            >
              {result.top_class ?? '—'}
            </span>
          </div>
          <div className="space-y-1">
            {CLASSES_ORDER.map((cls) => {
              const p = result.class_probs?.[cls] ?? 0;
              return (
                <div key={cls} className="flex items-center gap-2">
                  <span
                    className="w-10 text-right text-[10px] font-medium"
                    style={{ color: CLASS_COLOR_VAR[cls] }}
                  >
                    {cls}
                  </span>
                  <div className="flex-1 overflow-hidden rounded bg-[var(--color-bg-muted)]">
                    <div
                      className="h-2.5 rounded"
                      style={{
                        width: `${(p * 100).toFixed(1)}%`,
                        backgroundColor: CLASS_COLOR_VAR[cls],
                        opacity: 0.85,
                      }}
                    />
                  </div>
                  <span className="w-12 text-right text-[10px] tabular-nums text-[var(--color-text-muted)]">
                    {(p * 100).toFixed(0)}%
                  </span>
                </div>
              );
            })}
          </div>
        </>
      )}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--color-border-subtle)] pt-2 text-[10px] text-[var(--color-text-muted)]">
        <span>
          live ECE{' '}
          <span className="tabular-nums">{result.live_ece != null ? result.live_ece.toFixed(3) : '—'}</span>
        </span>
        <span>model {result.model_version ?? '—'}</span>
        <span>trained {formatRefreshed(result.last_train_date)}</span>
      </div>

      <div className="mt-3 text-[10px] italic text-[var(--color-text-muted)]">
        {result.scope_statement ?? SCOPE_STATEMENT}
      </div>
    </div>
  );
}
