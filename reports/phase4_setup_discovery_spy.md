# Phase 4: High-Probability Setup Discovery — SPY

Generated: 2026-02-22 06:58:42
Data: 2015-01-02 09:30:00 to 2025-11-14 16:00:00 (1,068,448 bars)

## 4A. Combinatorial Feature Scan — SPY

High-probability setups from 2-way and 3-way indicator combinations.

### SPY — Bullish Setups (WR >= 65%, n >= 30)
| Rank | Setup | WR | Trades | Avg Return | Combo Size | Confidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Above EMA20 + EMA9 < EMA20 + StochRSI Oversold | 68.0% | 696 | -0.1 bps | 3 | High |


Total setups found: 1
Best win rate: 68.0% (Above EMA20 + EMA9 < EMA20 + StochRSI Oversold)
Best reliable (n>=100): 68.0% with 696 trades (Above EMA20 + EMA9 < EMA20 + StochRSI Oversold)

### SPY — Bearish Setups (WR >= 65%, n >= 30)
| Rank | Setup | WR | Trades | Avg Return | Combo Size | Confidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | RSI > 70 + Below EMA9 + Prev 2U | 74.2% | 31 | +0.7 bps | 3 | Moderate |


Total setups found: 1
Best win rate: 74.2% (RSI > 70 + Below EMA9 + Prev 2U)

## 4B. Decision Tree / Random Forest — SPY

*sklearn not available — using rule-based analysis instead.*

### Rule-Based Feature Analysis

*Using manual feature importance (correlation with next-bar return).*

| Rank | Feature | Abs Correlation |
| :--- | :--- | :--- |
| 1 | Price_vs_EMA20 | 0.0167 |
| 2 | Price_vs_EMA9 | 0.0146 |
| 3 | MACD_Histogram | 0.0108 |
| 4 | Price_vs_VWAP | 0.0066 |
| 5 | RVOL | 0.0062 |
| 6 | StochRSI_K | 0.0061 |
| 7 | RSI14 | 0.0055 |
| 8 | BB_Pct | 0.0051 |
| 9 | EMA_Cross | 0.0019 |
| 10 | Order_Block_Position | 0.0007 |
| 11 | ORB_30m_Trend | 0.0000 |

## 4D. Sample Size Analysis — SPY

**Setup Distribution by Confidence Level:**

| Confidence Level | Setups | Best WR | Avg WR | Action |
| :--- | :--- | :--- | :--- | :--- |
| Low (n < 30) | 0 | N/A | N/A | Monitor only |
| Moderate (30-99) | 1 | 74.2% | 74.2% | Paper trade first |
| Good (100-499) | 0 | N/A | N/A | Small size trading |
| High (500+) | 1 | 68.0% | 68.0% | Full conviction |


**Top 5 Moderate (30-99) Setups:**

| Setup | WR | Trades | Direction |
| :--- | :--- | :--- | :--- |
| RSI > 70 + Below EMA9 + Prev 2U | 74.2% | 31 | Bearish |


**Top 5 High (500+) Setups:**

| Setup | WR | Trades | Direction |
| :--- | :--- | :--- | :--- |
| Above EMA20 + EMA9 < EMA20 + StochRSI Oversold | 68.0% | 696 | Bullish |

