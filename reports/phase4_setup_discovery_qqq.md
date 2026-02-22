# Phase 4: High-Probability Setup Discovery — QQQ

Generated: 2026-02-22 07:00:08
Data: 2015-01-02 09:30:00 to 2025-11-14 16:00:00 (1,067,740 bars)

## 4A. Combinatorial Feature Scan — QQQ

High-probability setups from 2-way and 3-way indicator combinations.

### QQQ — Bearish Setups (WR >= 65%, n >= 30)
| Rank | Setup | WR | Trades | Avg Return | Combo Size | Confidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | RSI > 70 + Below EMA9 + StochRSI Neutral | 69.4% | 36 | +1.2 bps | 3 | Moderate |
| 2 | RSI < 30 + StochRSI Overbought + Strat 3 | 67.6% | 34 | -0.5 bps | 3 | Moderate |


Total setups found: 2
Best win rate: 69.4% (RSI > 70 + Below EMA9 + StochRSI Neutral)

## 4B. Decision Tree / Random Forest — QQQ

*sklearn not available — using rule-based analysis instead.*

### Rule-Based Feature Analysis

*Using manual feature importance (correlation with next-bar return).*

| Rank | Feature | Abs Correlation |
| :--- | :--- | :--- |
| 1 | Price_vs_EMA9 | 0.0229 |
| 2 | Price_vs_EMA20 | 0.0227 |
| 3 | MACD_Histogram | 0.0118 |
| 4 | RSI14 | 0.0044 |
| 5 | RVOL | 0.0042 |
| 6 | StochRSI_K | 0.0040 |
| 7 | BB_Pct | 0.0039 |
| 8 | Price_vs_VWAP | 0.0027 |
| 9 | EMA_Cross | 0.0018 |
| 10 | ORB_30m_Trend | 0.0010 |
| 11 | Order_Block_Position | 0.0001 |

## 4D. Sample Size Analysis — QQQ

**Setup Distribution by Confidence Level:**

| Confidence Level | Setups | Best WR | Avg WR | Action |
| :--- | :--- | :--- | :--- | :--- |
| Low (n < 30) | 0 | N/A | N/A | Monitor only |
| Moderate (30-99) | 2 | 69.4% | 68.5% | Paper trade first |
| Good (100-499) | 0 | N/A | N/A | Small size trading |
| High (500+) | 0 | N/A | N/A | Full conviction |


**Top 5 Moderate (30-99) Setups:**

| Setup | WR | Trades | Direction |
| :--- | :--- | :--- | :--- |
| RSI > 70 + Below EMA9 + StochRSI Neutral | 69.4% | 36 | Bearish |
| RSI < 30 + StochRSI Overbought + Strat 3 | 67.6% | 34 | Bearish |

