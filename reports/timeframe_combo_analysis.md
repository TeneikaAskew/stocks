# Timeframe Entry + Filter Combination Analysis

**Date**: 2026-02-22
**Question**: Can 5m or 15m entries (with higher-TF filters) match or beat 1m+15m?

## TL;DR

**YES** -- 5m+15m and 15m+30m combos are highly competitive with 1m+15m. In fact,
several coarser-entry combos **beat** 1m+15m on expectancy and win rate, though with
fewer trades. The tradeoff is clear: coarser entries = higher win rate + higher
expectancy per trade, but fewer total opportunities.

---

## What Was Tested

**Phase 1**: Single timeframes (1m, 5m, 15m, 30m, 1h) -- no trend filter
**Phase 2**: 1m entries + higher-TF trend filter (original combos)
**Phase 3 (NEW)**: All entry+filter combos: 5m+15m, 5m+30m, 5m+1h, 15m+30m, 15m+1h, 30m+1h

---

## IWM Results (Full Ranking)

| Rank | Setup     | Trades | Win Rate | Expectancy | P/F  | Max DD   | Sharpe |
|------|-----------|--------|----------|------------|------|----------|--------|
| 1    | **15m+30m** | 3,418 | **73.1%** | **+0.126%** | **4.79** | -1.36% | 6.70  |
| 2    | 30m+1h    | 2,143  | 65.2%    | +0.112%    | 2.75 | -1.18%   | 4.38   |
| 3    | **5m+15m**  | 7,605 | **70.6%** | +0.096%   | **4.06** | **-0.55%** | **10.97** |
| 4    | 1m+30m    | 10,476 | 57.8%    | +0.090%    | 2.11 | -1.45%   | 10.87  |
| 5    | 1m+15m    | 10,971 | 57.7%    | +0.088%    | 2.12 | -0.61%   | 11.07  |
| 6    | 15m+1h    | 4,076  | 64.2%    | +0.078%    | 2.54 | -1.13%   | 5.39   |
| 7    | 1m+1h     | 10,126 | 54.8%    | +0.073%    | 1.82 | -1.96%   | 8.54   |
| 8    | 5m+30m    | 7,783  | 64.1%    | +0.071%    | 2.61 | -0.89%   | 8.67   |
| 9    | 5m+1h     | 7,843  | 59.3%    | +0.053%    | 1.97 | -1.08%   | 6.07   |
| 10   | 15m alone | 11,338 | 49.1%    | +0.002%    | 1.03 | -5.17%   | 0.49   |
| 11   | 1m alone  | 13,674 | 41.2%    | +0.002%    | 1.02 | -8.62%   | 0.21   |

**IWM Key Finding**: 15m+30m is #1 by expectancy (+0.126%/trade, 73.1% WR) but only 3,418 trades.
5m+15m is the sweet spot: 7,605 trades, 70.6% WR, Sharpe 10.97, lowest max DD (-0.55%).

---

## SPY Results (Full Ranking)

| Rank | Setup     | Trades | Win Rate | Expectancy | P/F  | Max DD   | Sharpe |
|------|-----------|--------|----------|------------|------|----------|--------|
| 1    | 30m+1h    | 3,160  | 62.5%    | +0.061%    | 2.39 | -0.69%   | 4.24   |
| 2    | **15m+30m** | 4,765 | **68.7%** | +0.059%   | **3.22** | -0.91% | 6.18  |
| 3    | **5m+15m**  | 8,760 | **67.3%** | +0.051%   | **3.19** | **-0.42%** | **9.80** |
| 4    | 1m+15m    | 11,414 | 57.9%    | +0.048%    | 2.04 | -0.52%   | 10.05  |
| 5    | 1m+30m    | 10,678 | 58.6%    | +0.048%    | 1.99 | -0.85%   | 9.73   |
| 6    | 15m+1h    | 4,968  | 62.6%    | +0.041%    | 2.09 | -1.43%   | 4.59   |
| 7    | 1m+1h     | 10,063 | 55.5%    | +0.038%    | 1.70 | -0.99%   | 7.35   |
| 8    | 5m+30m    | 8,569  | 62.3%    | +0.038%    | 2.21 | -0.77%   | 7.19   |
| 9    | 5m+1h     | 8,226  | 58.5%    | +0.028%    | 1.74 | -0.80%   | 5.13   |
| 10   | 15m alone | 11,876 | 49.0%    | +0.002%    | 1.04 | -3.89%   | 0.68   |
| 11   | 1m alone  | 13,675 | 43.6%    | -0.001%    | 0.99 | -5.09%   | -0.02  |

**SPY Key Finding**: 5m+15m beats 1m+15m on expectancy (+0.051% vs +0.048%), win rate
(67.3% vs 57.9%), and max DD (-0.42% vs -0.52%). Slightly lower Sharpe (9.80 vs 10.05)
due to fewer trades (8,760 vs 11,414).

---

## QQQ Results (Full Ranking)

| Rank | Setup     | Trades | Win Rate | Expectancy | P/F  | Max DD   | Sharpe |
|------|-----------|--------|----------|------------|------|----------|--------|
| 1    | **15m+30m** | 3,211 | **73.7%** | **+0.116%** | **5.19** | **-0.23%** | 7.57 |
| 2    | 30m+1h    | 2,063  | 66.4%    | +0.106%    | 2.75 | -1.08%   | 4.14   |
| 3    | **5m+15m**  | 7,223 | **70.0%** | +0.083%   | **4.05** | -0.48%  | **10.21** |
| 4    | 1m+15m    | 10,830 | 55.8%    | +0.072%    | 2.03 | -0.52%   | 10.20  |
| 5    | 1m+30m    | 10,299 | 55.9%    | +0.071%    | 2.03 | -0.96%   | 9.86   |
| 6    | 15m+1h    | 3,749  | 64.3%    | +0.070%    | 2.52 | -0.61%   | 5.57   |
| 7    | 5m+30m    | 7,415  | 63.9%    | +0.061%    | 2.57 | -0.70%   | 8.15   |
| 8    | 1m+1h     | 9,654  | 52.5%    | +0.055%    | 1.72 | -0.90%   | 7.24   |
| 9    | 5m+1h     | 7,291  | 59.5%    | +0.044%    | 1.89 | -1.00%   | 5.59   |
| 10   | 30m alone | 9,828  | 48.6%    | +0.004%    | 1.04 | -4.71%   | 0.30   |
| 11   | 1m alone  | 13,674 | 40.1%    | -0.002%    | 0.97 | -10.44%  | -0.29  |

**QQQ Key Finding**: 15m+30m is the overall winner (73.7% WR, +0.116% expectancy, -0.23% max DD).
5m+15m matches 1m+15m on Sharpe (10.21 vs 10.20) but with higher expectancy and 70% WR.

---

## Head-to-Head: 5m+15m vs 1m+15m

| Metric        | 1m+15m (IWM) | 5m+15m (IWM) | Winner   |
|---------------|-------------|-------------|----------|
| Trades        | 10,971      | 7,605       | 1m+15m   |
| Win Rate      | 57.7%       | **70.6%**   | 5m+15m   |
| Expectancy    | +0.088%     | **+0.096%** | 5m+15m   |
| Profit Factor | 2.12        | **4.06**    | 5m+15m   |
| Max Drawdown  | -0.61%      | **-0.55%**  | 5m+15m   |
| Sharpe        | **11.07**   | 10.97       | ~Tie     |

| Metric        | 1m+15m (SPY) | 5m+15m (SPY) | Winner   |
|---------------|-------------|-------------|----------|
| Trades        | 11,414      | 8,760       | 1m+15m   |
| Win Rate      | 57.9%       | **67.3%**   | 5m+15m   |
| Expectancy    | +0.048%     | **+0.051%** | 5m+15m   |
| Profit Factor | 2.04        | **3.19**    | 5m+15m   |
| Max Drawdown  | -0.52%      | **-0.42%**  | 5m+15m   |
| Sharpe        | **10.05**   | 9.80        | ~Tie     |

| Metric        | 1m+15m (QQQ) | 5m+15m (QQQ) | Winner   |
|---------------|-------------|-------------|----------|
| Trades        | 10,830      | 7,223       | 1m+15m   |
| Win Rate      | 55.8%       | **70.0%**   | 5m+15m   |
| Expectancy    | +0.072%     | **+0.083%** | 5m+15m   |
| Profit Factor | 2.03        | **4.05**    | 5m+15m   |
| Max Drawdown  | -0.52%      | **-0.48%**  | 5m+15m   |
| Sharpe        | 10.20       | **10.21**   | ~Tie     |

**5m+15m wins on almost every metric except trade count.** Sharpe is essentially tied
because 5m generates fewer but higher-quality trades.

---

## Head-to-Head: 15m+30m vs 1m+15m

| Metric        | 1m+15m (IWM) | 15m+30m (IWM) | Winner    |
|---------------|-------------|--------------|-----------|
| Trades        | 10,971      | 3,418        | 1m+15m    |
| Win Rate      | 57.7%       | **73.1%**    | 15m+30m   |
| Expectancy    | +0.088%     | **+0.126%**  | 15m+30m   |
| Profit Factor | 2.12        | **4.79**     | 15m+30m   |
| Max Drawdown  | **-0.61%**  | -1.36%       | 1m+15m    |
| Sharpe        | **11.07**   | 6.70         | 1m+15m    |

15m+30m has highest expectancy per trade, but 3x fewer trades and lower Sharpe.

---

## Practical Implications

### For maximum Sharpe (risk-adjusted returns):
- **1m+15m** or **5m+15m** -- both ~10-11 Sharpe across all tickers
- 1m+15m gives more trades; 5m+15m gives higher win rate

### For maximum expectancy per trade:
- **15m+30m** -- 73% WR on IWM/QQQ, +0.12-0.13% per trade
- Fewer trades means this is better for larger position sizes

### For maximum win rate (psychological comfort):
- **15m+30m** -- 73.1% (IWM), 73.7% (QQQ), 68.7% (SPY)
- Nearly 3 out of 4 trades are winners

### The "best of both worlds" candidate:
- **5m+15m** -- 70% WR, Sharpe ~10, ~7-9K trades, lowest max DD
- Gets you the high win rate AND the high Sharpe AND decent trade count

---

## Conclusion

The original 1m+15m setup is excellent, but **5m+15m is arguably better** -- it matches
the Sharpe ratio while delivering dramatically higher win rate (70% vs 58%), higher
profit factor (4x vs 2x), and lower drawdown. The cost is ~30% fewer trades, which
in practice means fewer but higher-conviction entries.

If you're willing to take even fewer trades, **15m+30m** offers the highest expectancy
per trade with 73% win rate, but at the cost of Sharpe (due to lower trade count).

**Recommendation**: Consider testing 5m+15m as the primary entry model, or running both
1m+15m and 5m+15m in parallel and comparing live performance.

---

## Raw Data Files

- `data/backtest_results/timeframe_sweep_IWM_20260222_161854.csv`
- `data/backtest_results/timeframe_sweep_SPY_20260222_162857.csv`
- `data/backtest_results/timeframe_sweep_QQQ_20260222_162901.csv`
