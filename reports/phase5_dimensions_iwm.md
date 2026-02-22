# Phase 5: Additional Dimensions — IWM

Generated: 2026-02-22 06:45:06
Data: 2015-01-02 09:30:00 to 2025-11-14 16:00:00 (1,067,154 bars)

## 5A. Market Regime Analysis — IWM

Performance segmented by ATR-based volatility regime.

### Volatility Regime Performance
| Regime | Bars | % of Data | Avg Next Return (bps) | 2U Freq | 2D Freq | Type 3 Freq | Suggested Target Adj |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Low Vol** | 292,619 | 27.4% | +0.1 bps | 38.7% | 36.5% | 7.1% | 0.5x |
| **Normal** | 480,654 | 45.0% | +0.0 bps | 38.4% | 37.5% | 7.4% | 1x |
| **High Vol** | 293,881 | 27.5% | -0.1 bps | 37.7% | 38.9% | 7.9% | 2x |

### Trend Regime Performance
| Regime | Days | % of Data | Avg Next Return (bps) | 2U Freq | 2D Freq | CALL Edge | PUT Edge |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Trending Up** | 509,088 | 47.7% | +0.1 bps | 38.6% | 36.7% | +0.0 bps | -0.1 bps |
| **Range-Bound** | 328,868 | 30.8% | -0.0 bps | 38.2% | 37.9% | -0.0 bps | +0.0 bps |
| **Trending Down** | 229,198 | 21.5% | -0.1 bps | 37.7% | 39.0% | -0.1 bps | +0.0 bps |

### Suggested Regime-Adaptive Targets

**Low Vol:** Avg move = +2.9 bps, P75 = +3.7 bps, P90 = +6.2 bps

**Normal:** Avg move = +3.7 bps, P75 = +4.7 bps, P90 = +7.9 bps

**High Vol:** Avg move = +5.5 bps, P75 = +6.9 bps, P90 = +11.7 bps

## 5B. Time-of-Day Analysis — IWM

Performance by intraday time window.

| Window | Bars | % of Data | Avg Return (bps) | Std (bps) | 2U % | 2D % | 3 % | CALL Edge | PUT Edge |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Open (9:30-10:00)** | 81,981 | 7.7% | -0.0 bps | +9.5 bps | 39.5% | 39.0% | 7.7% | +6.8 bps | +6.9 bps |
| **Mid-Morning (10:00-11:00)** | 164,075 | 15.4% | -0.0 bps | +7.1 bps | 38.7% | 38.3% | 7.9% | +5.0 bps | +5.1 bps |
| **Midday (11:00-13:00)** | 328,192 | 30.8% | +0.0 bps | +5.1 bps | 38.4% | 37.5% | 7.4% | +3.6 bps | +3.7 bps |
| **Afternoon (13:00-15:00)** | 326,973 | 30.6% | +0.0 bps | +5.1 bps | 37.8% | 36.9% | 7.1% | +3.3 bps | +3.3 bps |
| **Close (15:00-16:00)** | 163,210 | 15.3% | -0.0 bps | +5.7 bps | 37.9% | 37.8% | 7.6% | +3.6 bps | +3.7 bps |

### Optimal Entry Windows
Current config: CALL 9:30-10:00, PUT 9:30-14:00


**CALL by half-hour window:**

| Window | Bars | CALL Next Return | Win Rate |
| :--- | :--- | :--- | :--- |
| 09:30-10:00 | 81,981 | -0.0 bps | 48.6% |
| 10:00-10:30 | 82,026 | -0.0 bps | 48.7% |
| 10:30-11:00 | 82,049 | -0.0 bps | 48.3% |
| 11:00-11:30 | 82,047 | +0.0 bps | 48.2% |
| 11:30-12:00 | 82,048 | +0.0 bps | 48.1% |
| 12:00-12:30 | 82,050 | -0.0 bps | 47.8% |
| 12:30-13:00 | 82,047 | +0.0 bps | 47.5% |
| 13:00-13:30 | 81,910 | -0.0 bps | 47.4% |
| 13:30-14:00 | 81,761 | +0.0 bps | 47.4% |
| 14:00-14:30 | 81,675 | +0.0 bps | 47.6% |
| 14:30-15:00 | 81,627 | +0.0 bps | 47.7% |
| 15:00-15:30 | 81,583 | -0.0 bps | 47.4% |
| 15:30-16:00 | 81,627 | -0.0 bps | 47.7% |


**PUT by half-hour window:**

| Window | Bars | PUT Next Return | Win Rate |
| :--- | :--- | :--- | :--- |
| 09:30-10:00 | 81,981 | +0.0 bps | 48.5% |
| 10:00-10:30 | 82,026 | +0.0 bps | 48.0% |
| 10:30-11:00 | 82,049 | +0.0 bps | 47.8% |
| 11:00-11:30 | 82,047 | -0.0 bps | 47.4% |
| 11:30-12:00 | 82,048 | -0.0 bps | 47.1% |
| 12:00-12:30 | 82,050 | +0.0 bps | 46.8% |
| 12:30-13:00 | 82,047 | -0.0 bps | 46.8% |
| 13:00-13:30 | 81,910 | +0.0 bps | 46.8% |
| 13:30-14:00 | 81,761 | -0.0 bps | 46.5% |
| 14:00-14:30 | 81,675 | -0.0 bps | 46.8% |
| 14:30-15:00 | 81,627 | -0.0 bps | 46.5% |
| 15:00-15:30 | 81,583 | +0.0 bps | 47.2% |
| 15:30-16:00 | 81,627 | +0.0 bps | 47.5% |

## 5C. Day-of-Week Analysis — IWM

Performance by trading day.

| Day | Bars | Avg Return (bps) | Volatility (bps) | 2U % | 2D % | 3 % | CALL WR | PUT WR |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Monday** | 199,000 | +0.0 bps | +7.4 bps | 38.2% | 37.6% | 7.5% | 47.8% | 47.1% |
| **Tuesday** | 219,826 | +0.0 bps | +7.0 bps | 38.4% | 37.5% | 7.4% | 47.9% | 47.1% |
| **Wednesday** | 218,815 | -0.0 bps | +7.4 bps | 38.2% | 37.5% | 7.6% | 48.0% | 47.2% |
| **Thursday** | 215,933 | +0.0 bps | +7.9 bps | 38.3% | 37.7% | 7.5% | 47.9% | 47.4% |
| **Friday** | 213,580 | +0.0 bps | +8.2 bps | 38.2% | 37.6% | 7.3% | 47.9% | 47.2% |

## 5E. Drawdown & Streak Analysis — IWM

Worst-case scenarios and streak analysis.

### Losing Streak Distribution
| Metric | Value |
| :--- | :--- |
| Max consecutive losses | 19 |
| Avg losing streak length | 2.1 |
| Median losing streak | 2 |
| Streaks of 3+ | 55,603 |
| Streaks of 5+ | 15,394 |
| Streaks of 7+ | 4,345 |
| Total losing streaks | 201,942 |


**Streak Length Distribution:**

| Streak Length | Occurrences | % of Streaks |
| :--- | :--- | :--- |
| 1 | 96,137 | 47.6% |
| 2 | 50,202 | 24.9% |
| 3 | 26,342 | 13.0% |
| 4 | 13,867 | 6.9% |
| 5 | 7,190 | 3.6% |
| 6 | 3,859 | 1.9% |
| 7 | 2,054 | 1.0% |
| 8 | 1,096 | 0.5% |
| 9 | 559 | 0.3% |
| 10 | 299 | 0.1% |

### Cumulative P&L Drawdown
| Metric | Value |
| :--- | :--- |
| Max drawdown (bps) | -14434.8 bps |
| Max drawdown duration (trades) | 554,461 |
| Total P&L (bps) | -7955.4 bps |
| Total trades | 809,677 |
| Win rate | 47.5% |

### Psychological Preparation
> "This system wins 47% of the time on IWM, but you should expect 3+ consecutive losses about 1.4x per month. The max consecutive loss streak in the data was 19."

## 5F. Options P/L Translation — IWM

Translating underlying moves to options P/L estimates.

### Actual Options Chain Data Available
**Typical ATM Options Greeks (recent snapshots):**

- **delta**: mean=-0.0519
- **gamma**: mean=0.0193
- **theta**: mean=-0.0874
- **vega**: mean=0.6063
- **implied_volatility**: mean=0.2480

**Typical Bid-Ask Spreads:**

See options chain data for exact spreads.

### Theoretical Options P/L Translation

Estimated options returns using standard delta/theta assumptions.

| Underlying Move | ATM 0DTE (~50 delta) | OTM 0DTE (~25 delta) | ATM Weekly (~50 delta) | After Spread Cost |
| :--- | :--- | :--- | :--- | :--- |
| +15 bps | 0.8% | 1.5% | 0.5% | ~1.7% cost |
| +20 bps | 1.0% | 2.0% | 0.6% | ~1.7% cost |
| +30 bps | 1.5% | 3.0% | 0.9% | ~1.7% cost |
| +40 bps | 2.0% | 4.0% | 1.2% | ~1.7% cost |
| -10 bps | -0.5% | -1.0% | -0.3% | ~1.7% cost |
| -15 bps | -0.8% | -1.5% | -0.5% | ~1.7% cost |
| -20 bps | -1.0% | -2.0% | -0.6% | ~1.7% cost |

### Break-Even Analysis

Minimum underlying move to be profitable after costs:

- ATM 0DTE: ~3 bps underlying (spread + theta)
- OTM 0DTE: ~5 bps underlying (wider spread + theta)
- ATM Weekly: ~2 bps underlying (smaller spread + theta)

> **Key Insight**: Setups with < 5 bps average return may be unprofitable
> when traded with actual options due to spread and theta costs.

## 5G. Walk-Forward Validation — IWM

Testing pattern stability over rolling windows.

### Pattern: 2U continuation
| Window | Period | Occurrences | Next=2U Rate | Avg Fwd Return (bps) | Stable? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Window 1 | 2015-01-2015-07 | 7,714 | 41.2% | -0.1 bps | Yes |
| Window 2 | 2015-07-2016-01 | 8,535 | 45.5% | +0.0 bps | Yes |
| Window 3 | 2016-01-2016-07 | 8,536 | 45.1% | +0.0 bps | Yes |
| Window 4 | 2016-07-2017-01 | 8,038 | 43.8% | +0.1 bps | Yes |
| Window 5 | 2017-01-2017-07 | 8,337 | 44.1% | -0.1 bps | Yes |
| Window 6 | 2017-07-2018-01 | 7,917 | 43.4% | +0.0 bps | Yes |
| Window 7 | 2018-01-2018-07 | 8,642 | 46.1% | -0.0 bps | Yes |
| Window 8 | 2018-07-2019-01 | 8,578 | 46.0% | -0.2 bps | Yes |
| Window 9 | 2019-01-2019-07 | 8,857 | 46.1% | -0.0 bps | Yes |
| Window 10 | 2019-07-2020-01 | 8,752 | 45.8% | +0.0 bps | Yes |
| Window 11 | 2020-01-2020-07 | 9,352 | 47.1% | -0.0 bps | Yes |
| Window 12 | 2020-07-2021-01 | 9,284 | 47.2% | +0.1 bps | Yes |
| Window 13 | 2021-01-2021-07 | 9,287 | 47.5% | +0.1 bps | Yes |
| Window 14 | 2021-07-2022-01 | 9,332 | 47.8% | -0.1 bps | Yes |
| Window 15 | 2022-01-2022-07 | 9,263 | 47.5% | -0.1 bps | Yes |
| Window 16 | 2022-07-2023-01 | 9,456 | 48.1% | +0.0 bps | Yes |
| Window 17 | 2023-01-2023-07 | 9,178 | 47.2% | +0.1 bps | Yes |
| Window 18 | 2023-07-2024-01 | 8,993 | 46.9% | -0.0 bps | Yes |
| Window 19 | 2024-01-2024-07 | 9,237 | 46.9% | -0.1 bps | Yes |
| Window 20 | 2024-07-2025-01 | 9,344 | 46.6% | -0.1 bps | Yes |
| Window 21 | 2025-01-2025-07 | 9,204 | 47.5% | +0.1 bps | Yes |
| Window 22 | 2025-07-2025-11 | 7,294 | 49.2% | -0.1 bps | Yes |

Coefficient of variation: 0.04 (STABLE)
Mean rate: 46.2%, Std: 1.8%

### Pattern: 2D continuation
| Window | Period | Occurrences | Next=2D Rate | Avg Fwd Return (bps) | Stable? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Window 1 | 2015-01-2015-07 | 7,418 | 40.9% | +0.0 bps | Yes |
| Window 2 | 2015-07-2016-01 | 8,505 | 44.9% | -0.0 bps | Yes |
| Window 3 | 2016-01-2016-07 | 8,264 | 44.8% | +0.0 bps | Yes |
| Window 4 | 2016-07-2017-01 | 7,756 | 42.2% | +0.1 bps | Yes |
| Window 5 | 2017-01-2017-07 | 7,956 | 43.1% | +0.1 bps | Yes |
| Window 6 | 2017-07-2018-01 | 7,819 | 43.1% | +0.0 bps | Yes |
| Window 7 | 2018-01-2018-07 | 8,715 | 46.6% | +0.1 bps | Yes |
| Window 8 | 2018-07-2019-01 | 9,107 | 46.6% | +0.0 bps | Yes |
| Window 9 | 2019-01-2019-07 | 8,413 | 45.5% | +0.0 bps | Yes |
| Window 10 | 2019-07-2020-01 | 8,642 | 45.5% | -0.0 bps | Yes |
| Window 11 | 2020-01-2020-07 | 9,147 | 47.0% | +0.2 bps | Yes |
| Window 12 | 2020-07-2021-01 | 8,782 | 46.2% | +0.0 bps | Yes |
| Window 13 | 2021-01-2021-07 | 8,529 | 46.1% | +0.0 bps | Yes |
| Window 14 | 2021-07-2022-01 | 9,346 | 47.7% | +0.0 bps | Yes |
| Window 15 | 2022-01-2022-07 | 9,480 | 48.7% | -0.1 bps | Yes |
| Window 16 | 2022-07-2023-01 | 9,055 | 48.3% | -0.2 bps | Yes |
| Window 17 | 2023-01-2023-07 | 8,587 | 45.6% | +0.1 bps | Yes |
| Window 18 | 2023-07-2024-01 | 8,765 | 46.2% | +0.0 bps | Yes |
| Window 19 | 2024-01-2024-07 | 8,626 | 44.9% | +0.1 bps | Yes |
| Window 20 | 2024-07-2025-01 | 8,942 | 46.0% | +0.1 bps | Yes |
| Window 21 | 2025-01-2025-07 | 8,717 | 46.6% | +0.1 bps | Yes |
| Window 22 | 2025-07-2025-11 | 6,661 | 46.3% | +0.2 bps | Yes |

Coefficient of variation: 0.04 (STABLE)
Mean rate: 45.6%, Std: 1.9%

### Pattern: 2D-1-2U reversal
| Window | Period | Occurrences | Next=2U Rate | Avg Fwd Return (bps) | Stable? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Window 1 | 2015-01-2015-07 | 1,691 | 44.1% | -0.0 bps | Yes |
| Window 2 | 2015-07-2016-01 | 1,472 | 46.7% | +0.2 bps | Yes |
| Window 3 | 2016-01-2016-07 | 1,505 | 46.0% | -0.1 bps | Yes |
| Window 4 | 2016-07-2017-01 | 1,657 | 44.5% | +0.1 bps | Yes |
| Window 5 | 2017-01-2017-07 | 1,573 | 47.7% | +0.0 bps | Yes |
| Window 6 | 2017-07-2018-01 | 1,582 | 44.8% | -0.1 bps | Yes |
| Window 7 | 2018-01-2018-07 | 1,369 | 49.0% | +0.0 bps | Yes |
| Window 8 | 2018-07-2019-01 | 1,255 | 45.5% | -0.2 bps | Yes |
| Window 9 | 2019-01-2019-07 | 1,424 | 46.3% | +0.1 bps | Yes |
| Window 10 | 2019-07-2020-01 | 1,370 | 47.7% | +0.2 bps | Yes |
| Window 11 | 2020-01-2020-07 | 1,213 | 49.8% | -0.3 bps | Yes |
| Window 12 | 2020-07-2021-01 | 1,213 | 45.9% | +0.1 bps | Yes |
| Window 13 | 2021-01-2021-07 | 1,198 | 49.2% | +0.0 bps | Yes |
| Window 14 | 2021-07-2022-01 | 1,122 | 44.9% | -0.1 bps | Yes |
| Window 15 | 2022-01-2022-07 | 1,105 | 49.8% | +0.1 bps | Yes |
| Window 16 | 2022-07-2023-01 | 1,146 | 52.0% | +0.2 bps | Yes |
| Window 17 | 2023-01-2023-07 | 1,283 | 49.2% | -0.1 bps | Yes |
| Window 18 | 2023-07-2024-01 | 1,238 | 47.6% | -0.1 bps | Yes |
| Window 19 | 2024-01-2024-07 | 1,245 | 47.2% | -0.3 bps | Yes |
| Window 20 | 2024-07-2025-01 | 1,214 | 52.0% | +0.2 bps | Yes |
| Window 21 | 2025-01-2025-07 | 1,074 | 48.4% | -0.0 bps | Yes |
| Window 22 | 2025-07-2025-11 | 992 | 51.6% | +0.2 bps | Yes |

Coefficient of variation: 0.05 (STABLE)
Mean rate: 47.7%, Std: 2.3%

### Pattern: 2U-1-2D reversal
| Window | Period | Occurrences | Next=2D Rate | Avg Fwd Return (bps) | Stable? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Window 1 | 2015-01-2015-07 | 1,770 | 43.1% | +0.0 bps | Yes |
| Window 2 | 2015-07-2016-01 | 1,588 | 45.7% | -0.1 bps | Yes |
| Window 3 | 2016-01-2016-07 | 1,442 | 48.0% | -0.2 bps | Yes |
| Window 4 | 2016-07-2017-01 | 1,600 | 43.3% | +0.0 bps | Yes |
| Window 5 | 2017-01-2017-07 | 1,587 | 46.3% | +0.0 bps | Yes |
| Window 6 | 2017-07-2018-01 | 1,624 | 46.1% | -0.1 bps | Yes |
| Window 7 | 2018-01-2018-07 | 1,396 | 47.6% | +0.0 bps | Yes |
| Window 8 | 2018-07-2019-01 | 1,411 | 48.5% | -0.3 bps | Yes |
| Window 9 | 2019-01-2019-07 | 1,410 | 47.2% | -0.2 bps | Yes |
| Window 10 | 2019-07-2020-01 | 1,379 | 47.1% | -0.2 bps | Yes |
| Window 11 | 2020-01-2020-07 | 1,282 | 47.8% | -0.5 bps | Yes |
| Window 12 | 2020-07-2021-01 | 1,233 | 46.6% | -0.0 bps | Yes |
| Window 13 | 2021-01-2021-07 | 1,167 | 46.1% | -0.1 bps | Yes |
| Window 14 | 2021-07-2022-01 | 1,174 | 49.0% | -0.0 bps | Yes |
| Window 15 | 2022-01-2022-07 | 1,046 | 50.6% | -0.1 bps | Yes |
| Window 16 | 2022-07-2023-01 | 1,153 | 49.0% | -0.1 bps | Yes |
| Window 17 | 2023-01-2023-07 | 1,187 | 47.0% | -0.0 bps | Yes |
| Window 18 | 2023-07-2024-01 | 1,217 | 47.0% | -0.0 bps | Yes |
| Window 19 | 2024-01-2024-07 | 1,107 | 46.6% | +0.0 bps | Yes |
| Window 20 | 2024-07-2025-01 | 1,113 | 49.1% | +0.2 bps | Yes |
| Window 21 | 2025-01-2025-07 | 1,065 | 48.7% | +0.4 bps | Yes |
| Window 22 | 2025-07-2025-11 | 894 | 46.8% | +0.1 bps | Yes |

Coefficient of variation: 0.04 (STABLE)
Mean rate: 47.1%, Std: 1.7%

