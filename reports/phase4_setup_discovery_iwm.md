# Phase 4: High-Probability Setup Discovery — IWM

Generated: 2026-02-22 06:57:17
Data: 2015-01-02 09:30:00 to 2025-11-14 16:00:00 (1,067,154 bars)

## 4A. Combinatorial Feature Scan — IWM

High-probability setups from 2-way and 3-way indicator combinations.

### IWM — Bullish Setups (WR >= 65%, n >= 30)
| Rank | Setup | WR | Trades | Avg Return | Combo Size | Confidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | RSI < 30 + Above EMA9 + ATR High (>1.5x) | 67.7% | 31 | +1.1 bps | 3 | Moderate |
| 2 | RSI < 30 + Above EMA9 + StochRSI Neutral | 67.6% | 34 | +0.9 bps | 3 | Moderate |


Total setups found: 2
Best win rate: 67.7% (RSI < 30 + Above EMA9 + ATR High (>1.5x))

### IWM — Bearish Setups (WR >= 65%, n >= 30)
| Rank | Setup | WR | Trades | Avg Return | Combo Size | Confidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Below EMA20 + EMA9 > EMA20 + StochRSI Overbought | 65.9% | 754 | +0.3 bps | 3 | High |
| 2 | Below VWAP + Above EMA9 + ATR Low (<0.5x) | 65.9% | 41 | +0.8 bps | 3 | Moderate |


Total setups found: 2
Best win rate: 65.9% (Below EMA20 + EMA9 > EMA20 + StochRSI Overbought)
Best reliable (n>=100): 65.9% with 754 trades (Below EMA20 + EMA9 > EMA20 + StochRSI Overbought)

## 4B. Decision Tree / Random Forest — IWM

*sklearn not available — using rule-based analysis instead.*

### Rule-Based Feature Analysis

*Using manual feature importance (correlation with next-bar return).*

| Rank | Feature | Abs Correlation |
| :--- | :--- | :--- |
| 1 | Price_vs_EMA20 | 0.0164 |
| 2 | Price_vs_EMA9 | 0.0157 |
| 3 | MACD_Histogram | 0.0109 |
| 4 | RVOL | 0.0088 |
| 5 | Price_vs_VWAP | 0.0086 |
| 6 | RSI14 | 0.0048 |
| 7 | StochRSI_K | 0.0037 |
| 8 | BB_Pct | 0.0036 |
| 9 | EMA_Cross | 0.0033 |
| 10 | ORB_30m_Trend | 0.0005 |
| 11 | Order_Block_Position | 0.0004 |

## 4D. Sample Size Analysis — IWM

**Setup Distribution by Confidence Level:**

| Confidence Level | Setups | Best WR | Avg WR | Action |
| :--- | :--- | :--- | :--- | :--- |
| Low (n < 30) | 0 | N/A | N/A | Monitor only |
| Moderate (30-99) | 3 | 67.7% | 67.1% | Paper trade first |
| Good (100-499) | 0 | N/A | N/A | Small size trading |
| High (500+) | 1 | 65.9% | 65.9% | Full conviction |


**Top 5 Moderate (30-99) Setups:**

| Setup | WR | Trades | Direction |
| :--- | :--- | :--- | :--- |
| RSI < 30 + Above EMA9 + ATR High (>1.5x) | 67.7% | 31 | Bullish |
| RSI < 30 + Above EMA9 + StochRSI Neutral | 67.6% | 34 | Bullish |
| Below VWAP + Above EMA9 + ATR Low (<0.5x) | 65.9% | 41 | Bearish |


**Top 5 High (500+) Setups:**

| Setup | WR | Trades | Direction |
| :--- | :--- | :--- | :--- |
| Below EMA20 + EMA9 > EMA20 + StochRSI Overbought | 65.9% | 754 | Bearish |

