import { useTickerStore } from '@/stores/tickerStore';
import { useMarketStore } from '@/stores/marketStore';

export function Header() {
  const { activeTicker } = useTickerStore();
  const { data, isMarketOpen } = useMarketStore();
  const marketData = data[activeTicker];

  return (
    <header className="flex h-14 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-4">
      <div className="flex items-center gap-4">
        <span className="text-lg font-bold">{activeTicker}</span>
        {marketData && (
          <>
            <span className="text-lg font-mono">${marketData.price.toFixed(2)}</span>
            <span
              className={`text-sm font-medium ${
                marketData.change >= 0 ? 'text-[var(--color-accent-green)]' : 'text-[var(--color-accent-red)]'
              }`}
            >
              {marketData.change >= 0 ? '+' : ''}
              {marketData.change.toFixed(2)} ({marketData.changePct.toFixed(2)}%)
            </span>
          </>
        )}
      </div>
      <div className="flex items-center gap-3">
        <div
          className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
            isMarketOpen
              ? 'bg-green-500/10 text-green-400'
              : 'bg-red-500/10 text-red-400'
          }`}
        >
          <div
            className={`h-2 w-2 rounded-full ${isMarketOpen ? 'bg-green-400' : 'bg-red-400'}`}
          />
          {isMarketOpen ? 'Market Open' : 'Market Closed'}
        </div>
      </div>
    </header>
  );
}
