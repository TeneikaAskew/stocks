import { useQuery } from '@tanstack/react-query';
import { useTickerStore } from '@/stores/tickerStore';
import { MetricCard } from '@/components/shared/MetricCard';
import { TrendingUp, TrendingDown, BookOpen, Activity } from 'lucide-react';

interface BacktestSummary {
  total_trades: number;
  win_rate: number;
  avg_return_pct: number;
  total_return_pct: number;
}

interface BacktestResultsResponse {
  ticker: string;
  summary: BacktestSummary;
}

interface SignalsResponse {
  ticker: string;
  count: number;
  signals: Array<{ direction: string; time: string }>;
}

interface PlaybookResponse {
  ticker: string;
  cards: Array<{ id: string; name: string; direction: string }>;
}

function useBacktestSummary(ticker: string) {
  return useQuery<BacktestResultsResponse>({
    queryKey: ['dashboard-backtest', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/backtest/results/${ticker}`);
      if (!r.ok) throw new Error('No backtest data');
      return r.json();
    },
    staleTime: 60_000,
  });
}

function useRecentSignals(ticker: string) {
  return useQuery<SignalsResponse>({
    queryKey: ['dashboard-signals', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/signals/${ticker}?limit=200`);
      if (!r.ok) throw new Error('No signals data');
      return r.json();
    },
    staleTime: 60_000,
  });
}

function usePlaybook(ticker: string) {
  return useQuery<PlaybookResponse>({
    queryKey: ['dashboard-playbook', ticker],
    queryFn: async () => {
      const r = await fetch(`/api/playbook/${ticker}`);
      if (!r.ok) throw new Error('No playbook');
      return r.json();
    },
    staleTime: 3_600_000,
  });
}

export default function DashboardPage() {
  const { activeTicker } = useTickerStore();

  const { data: btData } = useBacktestSummary(activeTicker);
  const { data: sigData } = useRecentSignals(activeTicker);
  const { data: pbData } = usePlaybook(activeTicker);

  const summary = btData?.summary;
  const signals = sigData?.signals ?? [];
  const cards = pbData?.cards ?? [];

  // Today's signals (last 24h)
  const cutoff = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
  const todaySignals = signals.filter(s => s.time > cutoff);
  const todayCalls = todaySignals.filter(s => s.direction === 'CALL').length;
  const todayPuts = todaySignals.filter(s => s.direction === 'PUT').length;

  // Recent signals (last 20) for list
  const recentSignals = [...signals].reverse().slice(0, 10);

  // Playbook split
  const callCards = cards.filter(c => c.direction === 'CALL');
  const putCards = cards.filter(c => c.direction === 'PUT');


  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-[var(--color-text-primary)]">
          {activeTicker} Dashboard
        </h1>
        <p className="text-xs text-[var(--color-text-muted)]">
          Strategy overview — backtest KPIs, recent signals, playbook summary
        </p>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard
          label="Win Rate"
          value={summary ? `${(summary.win_rate * 100).toFixed(1)}%` : '--'}
          change={summary ? (summary.win_rate >= 0.5 ? 1 : -1) : undefined}
          changeLabel={summary ? `${summary.total_trades} trades` : undefined}
        />
        <MetricCard
          label="Avg Return"
          value={summary ? `${summary.avg_return_pct >= 0 ? '+' : ''}${summary.avg_return_pct.toFixed(2)}%` : '--'}
          change={summary ? (summary.avg_return_pct >= 0 ? 1 : -1) : undefined}
        />
        <MetricCard
          label="Today's Signals"
          value={todaySignals.length > 0 ? String(todaySignals.length) : '--'}
          changeLabel={todaySignals.length > 0 ? `${todayCalls}C / ${todayPuts}P` : undefined}
        />
        <MetricCard
          label="Playbook Cards"
          value={cards.length > 0 ? String(cards.length) : '--'}
          changeLabel={cards.length > 0 ? `${callCards.length}C / ${putCards.length}P` : undefined}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Recent signals */}
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
          <div className="mb-3 flex items-center gap-2">
            <Activity size={14} className="text-[var(--color-accent-blue)]" />
            <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Recent Signals</h2>
            {sigData && (
              <span className="ml-auto text-xs text-[var(--color-text-muted)]">
                {sigData.count.toLocaleString()} total
              </span>
            )}
          </div>
          {recentSignals.length === 0 ? (
            <p className="text-xs text-[var(--color-text-muted)]">No signal data — run the signals pipeline first.</p>
          ) : (
            <div className="space-y-1">
              {recentSignals.map((s, i) => (
                <div key={i} className="flex items-center justify-between rounded px-2 py-1 hover:bg-[var(--color-bg-tertiary)]">
                  <div className="flex items-center gap-2">
                    {s.direction === 'CALL'
                      ? <TrendingUp size={11} className="text-green-400" />
                      : <TrendingDown size={11} className="text-red-400" />
                    }
                    <span className={`text-xs font-bold ${s.direction === 'CALL' ? 'text-green-400' : 'text-red-400'}`}>
                      {s.direction}
                    </span>
                  </div>
                  <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
                    {String(s.time).slice(0, 16)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Playbook summary */}
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
          <div className="mb-3 flex items-center gap-2">
            <BookOpen size={14} className="text-[var(--color-accent-blue)]" />
            <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Playbook</h2>
            {cards.length > 0 && (
              <span className="ml-auto text-xs text-[var(--color-text-muted)]">{cards.length} setups</span>
            )}
          </div>
          {cards.length === 0 ? (
            <p className="text-xs text-[var(--color-text-muted)]">No playbook — run phase 6 pipeline first.</p>
          ) : (
            <div className="space-y-1">
              {cards.slice(0, 8).map(card => (
                <div key={card.id} className="flex items-center gap-2 rounded px-2 py-1 hover:bg-[var(--color-bg-tertiary)]">
                  {card.direction === 'CALL'
                    ? <TrendingUp size={11} className="text-green-400 shrink-0" />
                    : card.direction === 'PUT'
                    ? <TrendingDown size={11} className="text-red-400 shrink-0" />
                    : <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-[var(--color-text-muted)]" />
                  }
                  <span className="truncate text-xs text-[var(--color-text-secondary)]">{card.name}</span>
                  <span className={`ml-auto shrink-0 rounded px-1 py-0.5 text-[10px] font-bold ${
                    card.direction === 'CALL' ? 'bg-green-500/15 text-green-400' :
                    card.direction === 'PUT' ? 'bg-red-500/15 text-red-400' :
                    'bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]'
                  }`}>
                    {card.direction}
                  </span>
                </div>
              ))}
              {cards.length > 8 && (
                <p className="px-2 text-xs text-[var(--color-text-muted)]">+{cards.length - 8} more — see Playbook page</p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Total return banner */}
      {summary && summary.total_return_pct !== 0 && (
        <div className={`rounded-lg border p-4 ${
          summary.total_return_pct >= 0
            ? 'border-green-500/30 bg-green-500/5'
            : 'border-red-500/30 bg-red-500/5'
        }`}>
          <div className="flex items-center justify-between">
            <span className="text-sm text-[var(--color-text-secondary)]">
              Backtest total return ({summary.total_trades} trades)
            </span>
            <span className={`text-xl font-bold font-mono ${
              summary.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'
            }`}>
              {summary.total_return_pct >= 0 ? '+' : ''}{summary.total_return_pct.toFixed(2)}%
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
