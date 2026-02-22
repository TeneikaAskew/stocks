# Timeframe Entry + Filter Combination Analysis

**Date**: 2026-02-22 (full 2015–2026 dataset)
**Question**: Can 5m or 15m entries (with higher-TF filters) match or beat 1m+15m?

## TL;DR

With the **full 2015–2026 dataset** (10+ years, ~11,000 RTH bars/ticker), the picture is
clearer and more conservative than earlier partial-dataset results:

- **1m+30m is consistently #1 on Sharpe** across all three tickers (11.1 / 9.5 / 10.2)
- **5m+15m wins on win rate** (~62–63% vs 57–59% for 1m+30m), with very low drawdown
- **15m+30m has the highest win rate** (62–63%) but lower Sharpe due to fewer trades
- Full-dataset win rates are ~5–10pp **lower** than previously reported (the partial dataset
  through Nov 2025 over-represented the 2022–2025 bull run)

---

## What Was Tested

**Phase 1**: Single timeframes (1m, 5m, 15m, 30m, 1h) — no trend filter
**Phase 2**: 1m entries + higher-TF trend filter (1m+15m, 1m+30m, 1m+1h)
**Phase 3 (NEW)**: All entry+filter combos: 5m+15m, 5m+30m, 5m+1h, 15m+30m, 15m+1h, 30m+1h

All results use the complete dataset: 2015-01-02 through 2026-02-20 (RTH only).

---

## IWM Results (Full Ranking by Sharpe)

| Rank | Setup       | Trades | Win Rate  | PF   | Expectancy  | Max DD  | Sharpe    |
|------|-------------|--------|-----------|------|-------------|---------|-----------|
| 1    | **1m+30m**  | 11,143 | 56.7%     | 2.04 | **+0.087%** | -0.70%  | **11.05** |
| 2    | 1m+15m      | 11,773 | 55.8%     | 1.98 | +0.081%     | -0.65%  | 10.34     |
| 3    | 1m+1h       | 10,759 | 54.0%     | 1.81 | +0.073%     | -1.47%  | 8.85      |
| 4    | **5m+15m**  |  9,314 | **62.6%** | 2.37 | +0.062%     | -0.71%  | 8.34      |
| 5    | 5m+30m      |  9,194 | 59.8%     | 2.03 | +0.053%     | **-0.61%** | 7.29   |
| 6    | 5m+1h       |  9,094 | 57.7%     | 1.73 | +0.043%     | -0.61%  | 5.81      |
| 7    | **15m+30m** |  4,929 | **62.9%** | 2.53 | +0.075%     | -1.36%  | 5.40      |
| 8    | 15m+1h      |  5,342 | 59.2%     | 1.90 | +0.054%     | -1.28%  | 4.27      |
| 9    | 30m+1h      |  3,386 | 59.2%     | 1.79 | +0.063%     | -1.60%  | 3.15      |
| —    | 15m alone   | 11,407 | 49.3%     | 1.04 | +0.003%     | -5.30%  | 0.36      |
| —    | 1m alone    | 13,946 | 41.0%     | 1.01 | +0.001%     | -7.95%  | 0.18      |

**IWM Key Finding**: 1m+30m edges out 1m+15m on Sharpe (11.05 vs 10.34). 5m+15m delivers
a 62.6% win rate at the cost of ~2 Sharpe points and ~20% fewer trades.

---

## SPY Results (Full Ranking by Sharpe)

| Rank | Setup       | Trades | Win Rate  | PF   | Expectancy  | Max DD  | Sharpe   |
|------|-------------|--------|-----------|------|-------------|---------|----------|
| 1    | **1m+30m**  | 10,420 | 58.8%     | 2.05 | **+0.059%** | -0.64%  | **9.46** |
| 2    | 1m+15m      | 11,307 | 56.4%     | 1.90 | +0.051%     | **-0.51%** | 8.47  |
| 3    | **5m+15m**  |  9,752 | **62.2%** | 2.34 | +0.039%     | -0.61%  | 7.65     |
| 4    | 1m+1h       |  9,652 | 56.9%     | 1.81 | +0.051%     | -0.93%  | 7.55     |
| 5    | 5m+30m      |  9,377 | 59.4%     | 1.89 | +0.031%     | -0.58%  | 6.26     |
| 6    | **15m+30m** |  5,682 | **63.2%** | 2.30 | +0.043%     | -1.00%  | 5.28     |
| 7    | 5m+1h       |  8,904 | 56.8%     | 1.57 | +0.023%     | -0.92%  | 4.41     |
| 8    | 15m+1h      |  5,780 | 59.5%     | 1.74 | +0.031%     | -1.47%  | 3.71     |
| 9    | 30m+1h      |  4,010 | 57.5%     | 1.61 | +0.034%     | -1.23%  | 2.74     |
| —    | 5m alone    | 13,788 | 48.8%     | 1.02 | +0.001%     | -3.56%  | 0.35     |
| —    | 1m alone    | 13,832 | 44.6%     | 1.01 | +0.001%     | -5.18%  | 0.09     |

**SPY Key Finding**: 1m+30m leads on Sharpe (9.46). 1m+15m has the lowest drawdown
(-0.51%) of all filtered combos. 5m+15m is #3 with 62.2% win rate.

---

## QQQ Results (Full Ranking by Sharpe)

| Rank | Setup       | Trades | Win Rate  | PF   | Expectancy  | Max DD  | Sharpe    |
|------|-------------|--------|-----------|------|-------------|---------|-----------|
| 1    | **1m+30m**  | 10,656 | 57.5%     | 2.05 | **+0.079%** | -1.23%  | **10.21** |
| 2    | 1m+15m      | 11,394 | 56.1%     | 1.99 | +0.073%     | -0.93%  | 9.63      |
| 3    | **5m+15m**  |  9,198 | **62.6%** | 2.43 | +0.056%     | **-0.52%** | 8.42   |
| 4    | 1m+1h       |  9,940 | 54.9%     | 1.79 | +0.066%     | -1.48%  | 7.81      |
| 5    | 5m+30m      |  8,965 | 59.7%     | 1.98 | +0.046%     | -0.92%  | 6.89      |
| 6    | **15m+30m** |  5,031 | **63.4%** | 2.64 | +0.067%     | -0.99%  | 6.12      |
| 7    | 5m+1h       |  8,542 | 57.0%     | 1.66 | +0.036%     | -0.72%  | 5.04      |
| 8    | 15m+1h      |  5,249 | 59.7%     | 1.89 | +0.047%     | -0.91%  | 4.47      |
| 9    | 30m+1h      |  3,504 | 59.5%     | 1.76 | +0.055%     | -1.24%  | 3.06      |
| —    | 15m alone   | 11,688 | 49.0%     | 1.00 | 0.000%      | -4.99%  | 0.07      |
| —    | 1m alone    | 13,831 | 42.2%     | 0.98 | -0.002%     | -8.59%  | -0.26     |

**QQQ Key Finding**: 1m+30m leads (10.21 Sharpe). 5m+15m has the lowest drawdown
(-0.52%) of any combo with a 62.6% win rate. 15m+30m has the highest win rate (63.4%).

---

## Head-to-Head: 1m+30m vs 1m+15m

| Metric        | 1m+15m (IWM) | 1m+30m (IWM) | Winner     |
|---------------|-------------|-------------|------------|
| Trades        | **11,773**  | 11,143      | 1m+15m     |
| Win Rate      | 55.8%       | **56.7%**   | 1m+30m     |
| Expectancy    | +0.081%     | **+0.087%** | 1m+30m     |
| Profit Factor | 1.98        | **2.04**    | 1m+30m     |
| Max Drawdown  | **-0.65%**  | -0.70%      | 1m+15m     |
| Sharpe        | 10.34       | **11.05**   | 1m+30m     |

| Metric        | 1m+15m (SPY) | 1m+30m (SPY) | Winner     |
|---------------|-------------|-------------|------------|
| Trades        | **11,307**  | 10,420      | 1m+15m     |
| Win Rate      | 56.4%       | **58.8%**   | 1m+30m     |
| Expectancy    | +0.051%     | **+0.059%** | 1m+30m     |
| Profit Factor | 1.90        | **2.05**    | 1m+30m     |
| Max Drawdown  | **-0.51%**  | -0.64%      | 1m+15m     |
| Sharpe        | 8.47        | **9.46**    | 1m+30m     |

| Metric        | 1m+15m (QQQ) | 1m+30m (QQQ) | Winner     |
|---------------|-------------|-------------|------------|
| Trades        | **11,394**  | 10,656      | 1m+15m     |
| Win Rate      | 56.1%       | **57.5%**   | 1m+30m     |
| Expectancy    | +0.073%     | **+0.079%** | 1m+30m     |
| Profit Factor | 1.99        | **2.05**    | 1m+30m     |
| Max Drawdown  | -0.93%      | **-1.23%**  | 1m+15m     |
| Sharpe        | 9.63        | **10.21**   | 1m+30m     |

**1m+30m beats 1m+15m on Sharpe and expectancy across all tickers.** 1m+15m wins on
drawdown and marginally more trades. Both are excellent; the gap is small.

---

## Head-to-Head: 5m+15m vs 1m+15m

| Metric        | 1m+15m (IWM) | 5m+15m (IWM) | Winner     |
|---------------|-------------|-------------|------------|
| Trades        | **11,773**  | 9,314       | 1m+15m     |
| Win Rate      | 55.8%       | **62.6%**   | 5m+15m     |
| Expectancy    | **+0.081%** | +0.062%     | 1m+15m     |
| Profit Factor | 1.98        | **2.37**    | 5m+15m     |
| Max Drawdown  | -0.65%      | -0.71%      | ~Tie       |
| Sharpe        | **10.34**   | 8.34        | 1m+15m     |

| Metric        | 1m+15m (SPY) | 5m+15m (SPY) | Winner     |
|---------------|-------------|-------------|------------|
| Trades        | **11,307**  | 9,752       | 1m+15m     |
| Win Rate      | 56.4%       | **62.2%**   | 5m+15m     |
| Expectancy    | **+0.051%** | +0.039%     | 1m+15m     |
| Profit Factor | 1.90        | **2.34**    | 5m+15m     |
| Max Drawdown  | **-0.51%**  | -0.61%      | 1m+15m     |
| Sharpe        | **8.47**    | 7.65        | 1m+15m     |

| Metric        | 1m+15m (QQQ) | 5m+15m (QQQ) | Winner     |
|---------------|-------------|-------------|------------|
| Trades        | **11,394**  | 9,198       | 1m+15m     |
| Win Rate      | 56.1%       | **62.6%**   | 5m+15m     |
| Expectancy    | **+0.073%** | +0.056%     | 1m+15m     |
| Profit Factor | 1.99        | **2.43**    | 5m+15m     |
| Max Drawdown  | -0.93%      | **-0.52%**  | 5m+15m     |
| Sharpe        | **9.63**    | 8.42        | 1m+15m     |

**With the full 10-year dataset: 1m+15m wins on Sharpe and expectancy; 5m+15m wins on
win rate and profit factor.** A partial dataset through Nov 2025 made 5m+15m look equal or
better on Sharpe — that reflected a period unusually favorable for coarser entries. Over
the full cycle, 1m entries capture more edge.

---

## Note on Dataset Differences from Previous Report

Earlier results (partial dataset through Nov 2025) showed notably higher win rates:

| Setup | Previous WR | Full-Dataset WR | Delta |
|-------|------------|-----------------|-------|
| IWM 5m+15m  | 70.6% | 62.6% | -8.0pp |
| IWM 15m+30m | 73.1% | 62.9% | -10.2pp |
| IWM 1m+15m  | 57.7% | 55.8% | -1.9pp |
| SPY 5m+15m  | 67.3% | 62.2% | -5.1pp |
| QQQ 5m+15m  | 70.0% | 62.6% | -7.4pp |

The inflated win rates in the partial dataset reflected the 2022–2025 bull run where
trend-following setups (especially coarser entry timeframes) were unusually effective.
The full 10-year dataset spanning multiple market regimes gives more realistic expectations.

---

## Practical Implications

### For maximum Sharpe (risk-adjusted returns):
- **1m+30m** — Sharpe 11.1 / 9.5 / 10.2 across IWM / SPY / QQQ
- Marginally beats 1m+15m on Sharpe while accepting slightly higher drawdown

### For most trades with high Sharpe:
- **1m+15m** — slightly more trades than 1m+30m, lower drawdown on SPY/QQQ
- Both 1m+15m and 1m+30m are excellent; run both in parallel to compare live

### For highest win rate (psychological comfort):
- **15m+30m** — 62.9% / 63.2% / 63.4% WR — about 3 in 5 trades win
- **5m+15m** — 62.6% / 62.2% / 62.6% WR with better Sharpe and more trades

### For lowest drawdown:
- **5m+15m** — -0.71% / -0.61% / -0.52% max DD (lowest on QQQ)
- Best for traders who are drawdown-sensitive

### For highest expectancy per trade:
- **1m+30m** — +0.087% / +0.059% / +0.079% per trade
- Better for larger position sizes

---

## Conclusion

**1m+30m** is the strongest setup over the full 10-year dataset — consistently #1 on
Sharpe and expectancy across all three tickers. The 30m filter is less whippy than the
15m filter, producing slightly better entry quality.

**1m+15m** remains excellent and generates more trades — a good alternative or complement
to 1m+30m.

**5m+15m** is a strong choice for traders who prioritize win rate (~62%) and low drawdown.
It sacrifices ~2 Sharpe points vs 1m entries but gains ~7pp in win rate and nearly 2x
profit factor.

**Recommendation**: Primary model should be **1m+30m** (highest Sharpe) with **1m+15m**
as close second. Run both and compare live performance. Use **5m+15m** when you want
fewer but higher-conviction entries, or when drawdown is a constraint.

---

## Raw Data Files

- `data/backtest_results/timeframe_sweep_IWM_20260222_221023.csv`
- `data/backtest_results/timeframe_sweep_SPY_20260222_221023.csv`
- `data/backtest_results/timeframe_sweep_QQQ_20260222_221023.csv`
