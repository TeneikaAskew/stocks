import { useMemo } from 'react';
import type { TradeEntry } from '@/types';

interface TradeStats {
  totalTrades: number;
  closedTrades: number;
  activeTrades: number;
  winCount: number;
  lossCount: number;
  winRate: number;
  totalPnL: number;
  avgPnL: number;
  maxWin: number;
  maxLoss: number;
  profitFactor: number;
  callCount: number;
  putCount: number;
}

export function useTradeAnalytics(trades: TradeEntry[]): TradeStats {
  return useMemo(() => {
    const closed = trades.filter((t) => t.status !== 'active');
    const wins = closed.filter((t) => t.status === 'win');
    const losses = closed.filter((t) => t.status === 'loss');
    const pnls = closed.map((t) => t.pnl ?? 0);
    const winPnls = wins.map((t) => t.pnl ?? 0);
    const lossPnls = losses.map((t) => Math.abs(t.pnl ?? 0));

    const totalWins = winPnls.reduce((a, b) => a + b, 0);
    const totalLosses = lossPnls.reduce((a, b) => a + b, 0);

    return {
      totalTrades: trades.length,
      closedTrades: closed.length,
      activeTrades: trades.filter((t) => t.status === 'active').length,
      winCount: wins.length,
      lossCount: losses.length,
      winRate: closed.length > 0 ? (wins.length / closed.length) * 100 : 0,
      totalPnL: pnls.reduce((a, b) => a + b, 0),
      avgPnL: pnls.length > 0 ? pnls.reduce((a, b) => a + b, 0) / pnls.length : 0,
      maxWin: winPnls.length > 0 ? Math.max(...winPnls) : 0,
      maxLoss: lossPnls.length > 0 ? Math.max(...lossPnls) : 0,
      profitFactor: totalLosses > 0 ? totalWins / totalLosses : totalWins > 0 ? Infinity : 0,
      callCount: trades.filter((t) => t.optionType === 'CALL').length,
      putCount: trades.filter((t) => t.optionType === 'PUT').length,
    };
  }, [trades]);
}
