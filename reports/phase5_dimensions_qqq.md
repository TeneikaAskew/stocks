# Phase 5: Additional Dimensions — QQQ

Generated: 2026-02-22 23:44:24
Data: 2015-01-02 09:30:00 to 2026-02-20 16:00:00 (1,081,034 bars)

## 5A. Market Regime Analysis — QQQ

Performance segmented by ATR-based volatility regime.

### Volatility Regime Performance
| Regime | Bars | % of Data | Avg Next Return (bps) | 2U Freq | 2D Freq | Type 3 Freq | Suggested Target Adj |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Low Vol** | 296,358 | 27.4% | +0.1 bps | 38.7% | 35.2% | 7.5% | 0.5x |
| **Normal** | 476,034 | 44.0% | +0.0 bps | 38.6% | 36.6% | 7.7% | 1x |
| **High Vol** | 308,642 | 28.6% | -0.1 bps | 37.7% | 38.6% | 8.0% | 2x |

### Trend Regime Performance
| Regime | Days | % of Data | Avg Next Return (bps) | 2U Freq | 2D Freq | CALL Edge | PUT Edge |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Trending Up** | 650,300 | 60.2% | +0.1 bps | 38.7% | 35.9% | +0.0 bps | -0.1 bps |
| **Range-Bound** | 279,621 | 25.9% | -0.0 bps | 38.0% | 37.8% | -0.0 bps | +0.0 bps |
| **Trending Down** | 151,113 | 14.0% | -0.0 bps | 37.6% | 39.0% | -0.1 bps | +0.0 bps |

### Suggested Regime-Adaptive Targets

**Low Vol:** Avg move = +2.3 bps, P75 = +3.0 bps, P90 = +5.1 bps

**Normal:** Avg move = +3.2 bps, P75 = +4.1 bps, P90 = +7.0 bps

**High Vol:** Avg move = +5.1 bps, P75 = +6.5 bps, P90 = +11.2 bps

## 5B. Time-of-Day Analysis — QQQ

Performance by intraday time window.

| Window | Bars | % of Data | Avg Return (bps) | Std (bps) | 2U % | 2D % | 3 % | CALL Edge | PUT Edge |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Open (9:30-10:00)** | 83,001 | 7.7% | +0.0 bps | +8.2 bps | 39.9% | 37.9% | 7.7% | +5.7 bps | +5.8 bps |
| **Mid-Morning (10:00-11:00)** | 166,115 | 15.4% | -0.0 bps | +6.2 bps | 38.7% | 37.4% | 7.9% | +4.3 bps | +4.4 bps |
| **Midday (11:00-13:00)** | 332,277 | 30.7% | +0.0 bps | +4.6 bps | 38.6% | 36.6% | 7.7% | +3.1 bps | +3.2 bps |
| **Afternoon (13:00-15:00)** | 331,434 | 30.7% | +0.0 bps | +4.8 bps | 38.1% | 36.3% | 7.5% | +2.9 bps | +3.0 bps |
| **Close (15:00-16:00)** | 165,450 | 15.3% | -0.0 bps | +5.4 bps | 37.6% | 37.0% | 8.1% | +3.4 bps | +3.5 bps |

### Optimal Entry Windows
Current config: CALL 9:30-10:00, PUT 9:30-14:00


**CALL by half-hour window:**

| Window | Bars | CALL Next Return | Win Rate |
| :--- | :--- | :--- | :--- |
| 09:30-10:00 | 83,001 | +0.0 bps | 49.5% |
| 10:00-10:30 | 83,046 | +0.0 bps | 49.2% |
| 10:30-11:00 | 83,069 | -0.0 bps | 48.8% |
| 11:00-11:30 | 83,070 | +0.0 bps | 49.1% |
| 11:30-12:00 | 83,070 | +0.0 bps | 48.7% |
| 12:00-12:30 | 83,070 | -0.0 bps | 48.5% |
| 12:30-13:00 | 83,067 | +0.0 bps | 48.4% |
| 13:00-13:30 | 82,982 | -0.0 bps | 48.1% |
| 13:30-14:00 | 82,889 | +0.0 bps | 48.2% |
| 14:00-14:30 | 82,802 | +0.0 bps | 48.2% |
| 14:30-15:00 | 82,761 | +0.0 bps | 48.5% |
| 15:00-15:30 | 82,720 | -0.0 bps | 48.1% |
| 15:30-16:00 | 82,730 | +0.0 bps | 48.4% |


**PUT by half-hour window:**

| Window | Bars | PUT Next Return | Win Rate |
| :--- | :--- | :--- | :--- |
| 09:30-10:00 | 83,001 | -0.0 bps | 48.0% |
| 10:00-10:30 | 83,046 | -0.0 bps | 47.8% |
| 10:30-11:00 | 83,069 | +0.0 bps | 47.8% |
| 11:00-11:30 | 83,070 | -0.0 bps | 47.1% |
| 11:30-12:00 | 83,070 | -0.0 bps | 47.1% |
| 12:00-12:30 | 83,070 | +0.0 bps | 47.0% |
| 12:30-13:00 | 83,067 | -0.0 bps | 46.8% |
| 13:00-13:30 | 82,982 | +0.0 bps | 46.8% |
| 13:30-14:00 | 82,889 | -0.0 bps | 46.8% |
| 14:00-14:30 | 82,802 | -0.0 bps | 47.2% |
| 14:30-15:00 | 82,761 | -0.0 bps | 46.8% |
| 15:00-15:30 | 82,720 | +0.0 bps | 47.6% |
| 15:30-16:00 | 82,730 | -0.0 bps | 47.7% |

## 5C. Day-of-Week Analysis — QQQ

Performance by trading day.

| Day | Bars | Avg Return (bps) | Volatility (bps) | 2U % | 2D % | 3 % | CALL WR | PUT WR |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Monday** | 201,146 | +0.1 bps | +6.8 bps | 38.4% | 36.5% | 7.7% | 48.6% | 47.0% |
| **Tuesday** | 222,633 | +0.0 bps | +6.4 bps | 38.3% | 36.7% | 7.7% | 48.7% | 47.3% |
| **Wednesday** | 221,583 | +0.0 bps | +6.9 bps | 38.3% | 36.8% | 7.7% | 48.7% | 47.3% |
| **Thursday** | 218,700 | +0.0 bps | +6.8 bps | 38.5% | 37.1% | 7.7% | 48.6% | 47.4% |
| **Friday** | 216,972 | -0.0 bps | +8.0 bps | 38.3% | 36.8% | 7.7% | 48.5% | 47.2% |

## 5E. Drawdown & Streak Analysis — QQQ

Worst-case scenarios and streak analysis.

### Losing Streak Distribution
| Metric | Value |
| :--- | :--- |
| Max consecutive losses | 20 |
| Avg losing streak length | 2.1 |
| Median losing streak | 2 |
| Streaks of 3+ | 56,201 |
| Streaks of 5+ | 15,299 |
| Streaks of 7+ | 4,217 |
| Total losing streaks | 204,237 |


**Streak Length Distribution:**

| Streak Length | Occurrences | % of Streaks |
| :--- | :--- | :--- |
| 1 | 97,270 | 47.6% |
| 2 | 50,766 | 24.9% |
| 3 | 26,800 | 13.1% |
| 4 | 14,102 | 6.9% |
| 5 | 7,257 | 3.6% |
| 6 | 3,825 | 1.9% |
| 7 | 1,934 | 0.9% |
| 8 | 1,065 | 0.5% |
| 9 | 540 | 0.3% |
| 10 | 351 | 0.2% |

### Cumulative P&L Drawdown
| Metric | Value |
| :--- | :--- |
| Max drawdown (bps) | -22100.0 bps |
| Max drawdown duration (trades) | 812,212 |
| Total P&L (bps) | -10535.4 bps |
| Total trades | 812,518 |
| Win rate | 47.2% |

### Psychological Preparation
> "This system wins 47% of the time on QQQ, but you should expect 3+ consecutive losses about 1.4x per month. The max consecutive loss streak in the data was 20."

## 5F. Options P/L Translation — QQQ

Translating underlying moves to options P/L estimates.

### Actual Options Chain Data Available
**Typical ATM Options Greeks (recent snapshots):**

- **delta**: mean=-0.0450
- **gamma**: mean=0.0082
- **theta**: mean=-0.2383
- **vega**: mean=1.5275
- **implied_volatility**: mean=0.2510

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

## 5G. Walk-Forward Validation — QQQ

Testing pattern stability over rolling windows.

### Pattern: 2U continuation
| Window | Period | Occurrences | Next=2U Rate | Avg Fwd Return (bps) | Stable? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Window 1 | 2015-01-2015-07 | 7,723 | 41.2% | -0.1 bps | Yes |
| Window 2 | 2015-07-2016-01 | 8,356 | 43.4% | -0.1 bps | Yes |
| Window 3 | 2016-01-2016-07 | 8,311 | 44.3% | -0.1 bps | Yes |
| Window 4 | 2016-07-2017-01 | 7,693 | 40.9% | +0.0 bps | Yes |
| Window 5 | 2017-01-2017-07 | 7,751 | 40.9% | -0.0 bps | Yes |
| Window 6 | 2017-07-2018-01 | 7,658 | 40.9% | +0.0 bps | Yes |
| Window 7 | 2018-01-2018-07 | 8,762 | 44.9% | -0.1 bps | Yes |
| Window 8 | 2018-07-2019-01 | 8,548 | 43.9% | -0.2 bps | Yes |
| Window 9 | 2019-01-2019-07 | 8,516 | 44.0% | -0.0 bps | Yes |
| Window 10 | 2019-07-2020-01 | 8,463 | 44.1% | +0.1 bps | Yes |
| Window 11 | 2020-01-2020-07 | 9,377 | 46.0% | -0.2 bps | Yes |
| Window 12 | 2020-07-2021-01 | 9,368 | 45.7% | +0.0 bps | Yes |
| Window 13 | 2021-01-2021-07 | 9,048 | 45.9% | +0.1 bps | Yes |
| Window 14 | 2021-07-2022-01 | 9,138 | 46.1% | +0.1 bps | Yes |
| Window 15 | 2022-01-2022-07 | 8,687 | 44.8% | -0.3 bps | Yes |
| Window 16 | 2022-07-2023-01 | 9,136 | 46.7% | +0.0 bps | Yes |
| Window 17 | 2023-01-2023-07 | 9,479 | 47.4% | +0.2 bps | Yes |
| Window 18 | 2023-07-2024-01 | 9,177 | 46.8% | +0.0 bps | Yes |
| Window 19 | 2024-01-2024-07 | 9,506 | 47.5% | +0.1 bps | Yes |
| Window 20 | 2024-07-2025-01 | 9,362 | 46.1% | -0.0 bps | Yes |
| Window 21 | 2025-01-2025-07 | 9,226 | 47.6% | +0.1 bps | Yes |
| Window 22 | 2025-07-2026-01 | 7,186 | 47.5% | -0.1 bps | Yes |
| Window 23 | 2026-01-2026-02 | 2,333 | 45.3% | -0.1 bps | Yes |

Coefficient of variation: 0.05 (STABLE)
Mean rate: 44.9%, Std: 2.1%

### Pattern: 2D continuation
| Window | Period | Occurrences | Next=2D Rate | Avg Fwd Return (bps) | Stable? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Window 1 | 2015-01-2015-07 | 7,433 | 40.2% | +0.2 bps | Yes |
| Window 2 | 2015-07-2016-01 | 8,298 | 44.3% | +0.1 bps | Yes |
| Window 3 | 2016-01-2016-07 | 8,121 | 43.5% | +0.1 bps | Yes |
| Window 4 | 2016-07-2017-01 | 7,382 | 40.2% | +0.0 bps | Yes |
| Window 5 | 2017-01-2017-07 | 6,752 | 38.6% | +0.1 bps | Yes |
| Window 6 | 2017-07-2018-01 | 6,952 | 39.4% | +0.1 bps | Yes |
| Window 7 | 2018-01-2018-07 | 8,193 | 44.5% | +0.2 bps | Yes |
| Window 8 | 2018-07-2019-01 | 8,441 | 43.7% | +0.2 bps | Yes |
| Window 9 | 2019-01-2019-07 | 7,822 | 43.1% | +0.2 bps | Yes |
| Window 10 | 2019-07-2020-01 | 8,072 | 43.5% | +0.1 bps | Yes |
| Window 11 | 2020-01-2020-07 | 8,545 | 45.7% | +0.2 bps | Yes |
| Window 12 | 2020-07-2021-01 | 8,057 | 42.5% | +0.2 bps | Yes |
| Window 13 | 2021-01-2021-07 | 8,327 | 44.3% | -0.0 bps | Yes |
| Window 14 | 2021-07-2022-01 | 8,585 | 44.7% | +0.0 bps | Yes |
| Window 15 | 2022-01-2022-07 | 9,031 | 46.1% | -0.1 bps | Yes |
| Window 16 | 2022-07-2023-01 | 8,839 | 45.8% | -0.2 bps | Yes |
| Window 17 | 2023-01-2023-07 | 8,235 | 44.1% | +0.1 bps | Yes |
| Window 18 | 2023-07-2024-01 | 8,091 | 43.4% | +0.0 bps | Yes |
| Window 19 | 2024-01-2024-07 | 8,104 | 43.7% | -0.0 bps | Yes |
| Window 20 | 2024-07-2025-01 | 8,432 | 44.3% | +0.0 bps | Yes |
| Window 21 | 2025-01-2025-07 | 8,607 | 46.9% | -0.0 bps | Yes |
| Window 22 | 2025-07-2026-01 | 6,399 | 45.6% | +0.0 bps | Yes |
| Window 23 | 2026-01-2026-02 | 2,393 | 47.0% | -0.1 bps | Yes |

Coefficient of variation: 0.05 (STABLE)
Mean rate: 43.7%, Std: 2.2%

### Pattern: 2D-1-2U reversal
| Window | Period | Occurrences | Next=2U Rate | Avg Fwd Return (bps) | Stable? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Window 1 | 2015-01-2015-07 | 1,814 | 44.1% | -0.1 bps | Yes |
| Window 2 | 2015-07-2016-01 | 1,573 | 47.8% | +0.3 bps | Yes |
| Window 3 | 2016-01-2016-07 | 1,608 | 45.9% | +0.0 bps | Yes |
| Window 4 | 2016-07-2017-01 | 1,795 | 44.2% | +0.0 bps | Yes |
| Window 5 | 2017-01-2017-07 | 1,810 | 44.8% | -0.0 bps | Yes |
| Window 6 | 2017-07-2018-01 | 1,786 | 44.0% | -0.1 bps | Yes |
| Window 7 | 2018-01-2018-07 | 1,424 | 50.1% | +0.0 bps | Yes |
| Window 8 | 2018-07-2019-01 | 1,399 | 48.0% | +0.2 bps | Yes |
| Window 9 | 2019-01-2019-07 | 1,427 | 46.4% | -0.1 bps | Yes |
| Window 10 | 2019-07-2020-01 | 1,388 | 45.9% | +0.1 bps | Yes |
| Window 11 | 2020-01-2020-07 | 1,236 | 50.0% | +0.1 bps | Yes |
| Window 12 | 2020-07-2021-01 | 1,324 | 50.0% | +0.3 bps | Yes |
| Window 13 | 2021-01-2021-07 | 1,187 | 51.4% | +0.2 bps | Yes |
| Window 14 | 2021-07-2022-01 | 1,263 | 48.3% | +0.1 bps | Yes |
| Window 15 | 2022-01-2022-07 | 1,154 | 48.5% | +0.4 bps | Yes |
| Window 16 | 2022-07-2023-01 | 1,191 | 50.7% | -0.2 bps | Yes |
| Window 17 | 2023-01-2023-07 | 1,132 | 50.1% | -0.0 bps | Yes |
| Window 18 | 2023-07-2024-01 | 1,245 | 48.3% | -0.1 bps | Yes |
| Window 19 | 2024-01-2024-07 | 1,319 | 49.0% | -0.2 bps | Yes |
| Window 20 | 2024-07-2025-01 | 1,252 | 51.1% | +0.1 bps | Yes |
| Window 21 | 2025-01-2025-07 | 1,116 | 49.8% | -0.0 bps | Yes |
| Window 22 | 2025-07-2026-01 | 927 | 52.0% | +0.1 bps | Yes |
| Window 23 | 2026-01-2026-02 | 295 | 44.7% | +0.1 bps | Yes |

Coefficient of variation: 0.05 (STABLE)
Mean rate: 48.0%, Std: 2.5%

### Pattern: 2U-1-2D reversal
| Window | Period | Occurrences | Next=2D Rate | Avg Fwd Return (bps) | Stable? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Window 1 | 2015-01-2015-07 | 1,797 | 42.5% | -0.0 bps | Yes |
| Window 2 | 2015-07-2016-01 | 1,618 | 42.7% | +0.1 bps | Yes |
| Window 3 | 2016-01-2016-07 | 1,718 | 46.0% | +0.0 bps | Yes |
| Window 4 | 2016-07-2017-01 | 1,755 | 45.3% | -0.1 bps | Yes |
| Window 5 | 2017-01-2017-07 | 1,708 | 42.4% | +0.0 bps | Yes |
| Window 6 | 2017-07-2018-01 | 1,784 | 42.2% | +0.0 bps | Yes |
| Window 7 | 2018-01-2018-07 | 1,455 | 45.5% | -0.1 bps | Yes |
| Window 8 | 2018-07-2019-01 | 1,529 | 45.7% | +0.1 bps | Yes |
| Window 9 | 2019-01-2019-07 | 1,444 | 46.3% | +0.1 bps | Yes |
| Window 10 | 2019-07-2020-01 | 1,426 | 46.2% | -0.0 bps | Yes |
| Window 11 | 2020-01-2020-07 | 1,287 | 44.9% | +0.1 bps | Yes |
| Window 12 | 2020-07-2021-01 | 1,253 | 47.9% | +0.0 bps | Yes |
| Window 13 | 2021-01-2021-07 | 1,185 | 46.4% | -0.1 bps | Yes |
| Window 14 | 2021-07-2022-01 | 1,240 | 48.0% | +0.1 bps | Yes |
| Window 15 | 2022-01-2022-07 | 1,167 | 48.9% | +0.1 bps | Yes |
| Window 16 | 2022-07-2023-01 | 1,194 | 49.5% | -0.2 bps | Yes |
| Window 17 | 2023-01-2023-07 | 1,112 | 50.2% | -0.3 bps | Yes |
| Window 18 | 2023-07-2024-01 | 1,288 | 48.1% | -0.0 bps | Yes |
| Window 19 | 2024-01-2024-07 | 1,164 | 44.6% | +0.3 bps | Yes |
| Window 20 | 2024-07-2025-01 | 1,097 | 47.6% | -0.1 bps | Yes |
| Window 21 | 2025-01-2025-07 | 1,049 | 47.8% | -0.0 bps | Yes |
| Window 22 | 2025-07-2026-01 | 864 | 47.2% | -0.0 bps | Yes |
| Window 23 | 2026-01-2026-02 | 289 | 49.8% | -0.3 bps | Yes |

Coefficient of variation: 0.05 (STABLE)
Mean rate: 46.3%, Std: 2.3%

