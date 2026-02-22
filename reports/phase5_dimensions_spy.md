# Phase 5: Additional Dimensions — SPY

Generated: 2026-02-22 06:45:41
Data: 2015-01-02 09:30:00 to 2025-11-14 16:00:00 (1,068,448 bars)

## 5A. Market Regime Analysis — SPY

Performance segmented by ATR-based volatility regime.

### Volatility Regime Performance
| Regime | Bars | % of Data | Avg Next Return (bps) | 2U Freq | 2D Freq | Type 3 Freq | Suggested Target Adj |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Low Vol** | 308,964 | 28.9% | +0.1 bps | 38.1% | 35.0% | 7.3% | 0.5x |
| **Normal** | 464,013 | 43.4% | +0.0 bps | 38.0% | 36.5% | 7.6% | 1x |
| **High Vol** | 295,471 | 27.7% | -0.0 bps | 37.5% | 38.6% | 8.1% | 2x |

### Trend Regime Performance
| Regime | Days | % of Data | Avg Next Return (bps) | 2U Freq | 2D Freq | CALL Edge | PUT Edge |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Trending Up** | 661,980 | 62.0% | +0.0 bps | 38.1% | 35.7% | +0.0 bps | -0.1 bps |
| **Range-Bound** | 259,964 | 24.3% | -0.0 bps | 37.7% | 37.9% | -0.0 bps | -0.0 bps |
| **Trending Down** | 146,504 | 13.7% | -0.0 bps | 37.3% | 39.1% | -0.1 bps | -0.0 bps |

### Suggested Regime-Adaptive Targets

**Low Vol:** Avg move = +1.7 bps, P75 = +2.2 bps, P90 = +3.8 bps

**Normal:** Avg move = +2.5 bps, P75 = +3.1 bps, P90 = +5.3 bps

**High Vol:** Avg move = +4.1 bps, P75 = +5.1 bps, P90 = +8.9 bps

## 5B. Time-of-Day Analysis — SPY

Performance by intraday time window.

| Window | Bars | % of Data | Avg Return (bps) | Std (bps) | 2U % | 2D % | 3 % | CALL Edge | PUT Edge |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Open (9:30-10:00)** | 81,981 | 7.7% | +0.0 bps | +5.8 bps | 39.3% | 37.5% | 7.7% | +3.8 bps | +3.9 bps |
| **Mid-Morning (10:00-11:00)** | 164,075 | 15.4% | -0.0 bps | +4.8 bps | 38.1% | 37.3% | 8.0% | +3.1 bps | +3.2 bps |
| **Midday (11:00-13:00)** | 328,192 | 30.7% | +0.0 bps | +3.7 bps | 38.1% | 36.5% | 7.6% | +2.4 bps | +2.5 bps |
| **Afternoon (13:00-15:00)** | 327,886 | 30.7% | +0.0 bps | +3.8 bps | 37.5% | 36.2% | 7.3% | +2.3 bps | +2.4 bps |
| **Close (15:00-16:00)** | 163,583 | 15.3% | -0.0 bps | +4.7 bps | 37.4% | 37.0% | 8.1% | +2.9 bps | +2.9 bps |

### Optimal Entry Windows
Current config: CALL 9:30-10:00, PUT 9:30-14:00


**CALL by half-hour window:**

| Window | Bars | CALL Next Return | Win Rate |
| :--- | :--- | :--- | :--- |
| 09:30-10:00 | 81,981 | +0.0 bps | 49.5% |
| 10:00-10:30 | 82,026 | +0.0 bps | 49.2% |
| 10:30-11:00 | 82,049 | -0.0 bps | 49.1% |
| 11:00-11:30 | 82,047 | +0.0 bps | 49.1% |
| 11:30-12:00 | 82,048 | +0.0 bps | 49.0% |
| 12:00-12:30 | 82,050 | -0.0 bps | 48.9% |
| 12:30-13:00 | 82,047 | +0.0 bps | 48.9% |
| 13:00-13:30 | 82,032 | -0.0 bps | 48.5% |
| 13:30-14:00 | 82,027 | +0.0 bps | 48.5% |
| 14:00-14:30 | 81,966 | +0.0 bps | 48.5% |
| 14:30-15:00 | 81,861 | +0.0 bps | 48.7% |
| 15:00-15:30 | 81,778 | -0.0 bps | 48.5% |
| 15:30-16:00 | 81,805 | -0.0 bps | 48.5% |


**PUT by half-hour window:**

| Window | Bars | PUT Next Return | Win Rate |
| :--- | :--- | :--- | :--- |
| 09:30-10:00 | 81,981 | -0.0 bps | 48.1% |
| 10:00-10:30 | 82,026 | -0.0 bps | 48.1% |
| 10:30-11:00 | 82,049 | +0.0 bps | 48.0% |
| 11:00-11:30 | 82,047 | -0.0 bps | 47.6% |
| 11:30-12:00 | 82,048 | -0.0 bps | 47.4% |
| 12:00-12:30 | 82,050 | +0.0 bps | 47.2% |
| 12:30-13:00 | 82,047 | -0.0 bps | 47.0% |
| 13:00-13:30 | 82,032 | +0.0 bps | 47.2% |
| 13:30-14:00 | 82,027 | -0.0 bps | 47.3% |
| 14:00-14:30 | 81,966 | -0.0 bps | 47.6% |
| 14:30-15:00 | 81,861 | -0.0 bps | 47.4% |
| 15:00-15:30 | 81,778 | +0.0 bps | 47.8% |
| 15:30-16:00 | 81,805 | +0.0 bps | 48.4% |

## 5C. Day-of-Week Analysis — SPY

Performance by trading day.

| Day | Bars | Avg Return (bps) | Volatility (bps) | 2U % | 2D % | 3 % | CALL WR | PUT WR |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Monday** | 199,268 | +0.0 bps | +5.5 bps | 37.6% | 36.3% | 7.7% | 48.8% | 47.5% |
| **Tuesday** | 219,976 | +0.0 bps | +5.2 bps | 37.8% | 36.7% | 7.6% | 48.8% | 47.7% |
| **Wednesday** | 218,894 | +0.0 bps | +5.5 bps | 37.8% | 36.7% | 7.7% | 48.8% | 47.7% |
| **Thursday** | 216,053 | +0.0 bps | +5.5 bps | 38.1% | 36.8% | 7.7% | 49.0% | 47.7% |
| **Friday** | 214,257 | +0.0 bps | +6.4 bps | 38.0% | 36.8% | 7.5% | 48.9% | 47.6% |

## 5E. Drawdown & Streak Analysis — SPY

Worst-case scenarios and streak analysis.

### Losing Streak Distribution
| Metric | Value |
| :--- | :--- |
| Max consecutive losses | 20 |
| Avg losing streak length | 2.1 |
| Median losing streak | 2 |
| Streaks of 3+ | 54,669 |
| Streaks of 5+ | 14,901 |
| Streaks of 7+ | 4,074 |
| Total losing streaks | 200,514 |


**Streak Length Distribution:**

| Streak Length | Occurrences | % of Streaks |
| :--- | :--- | :--- |
| 1 | 95,840 | 47.8% |
| 2 | 50,005 | 24.9% |
| 3 | 26,129 | 13.0% |
| 4 | 13,639 | 6.8% |
| 5 | 7,065 | 3.5% |
| 6 | 3,762 | 1.9% |
| 7 | 1,977 | 1.0% |
| 8 | 1,050 | 0.5% |
| 9 | 513 | 0.3% |
| 10 | 256 | 0.1% |

### Cumulative P&L Drawdown
| Metric | Value |
| :--- | :--- |
| Max drawdown (bps) | -23355.2 bps |
| Max drawdown duration (trades) | 796,365 |
| Total P&L (bps) | -23154.2 bps |
| Total trades | 796,701 |
| Win rate | 47.3% |

### Psychological Preparation
> "This system wins 47% of the time on SPY, but you should expect 3+ consecutive losses about 1.4x per month. The max consecutive loss streak in the data was 20."

## 5F. Options P/L Translation — SPY

Translating underlying moves to options P/L estimates.

### Actual Options Chain Data Available
**Typical ATM Options Greeks (recent snapshots):**

- **delta**: mean=-0.0566
- **gamma**: mean=0.0092
- **theta**: mean=-0.1845
- **vega**: mean=1.7230
- **implied_volatility**: mean=0.1982

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

## 5G. Walk-Forward Validation — SPY

Testing pattern stability over rolling windows.

### Pattern: 2U continuation
| Window | Period | Occurrences | Next=2U Rate | Avg Fwd Return (bps) | Stable? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Window 1 | 2015-01-2015-07 | 7,546 | 40.4% | -0.1 bps | Yes |
| Window 2 | 2015-07-2016-01 | 8,416 | 43.2% | -0.1 bps | Yes |
| Window 3 | 2016-01-2016-07 | 8,334 | 44.2% | -0.1 bps | Yes |
| Window 4 | 2016-07-2017-01 | 7,529 | 40.1% | -0.1 bps | Yes |
| Window 5 | 2017-01-2017-07 | 7,643 | 40.4% | -0.1 bps | Yes |
| Window 6 | 2017-07-2018-01 | 7,116 | 40.0% | -0.0 bps | Yes |
| Window 7 | 2018-01-2018-07 | 8,440 | 44.5% | -0.2 bps | Yes |
| Window 8 | 2018-07-2019-01 | 8,183 | 43.5% | -0.1 bps | Yes |
| Window 9 | 2019-01-2019-07 | 8,708 | 44.6% | -0.0 bps | Yes |
| Window 10 | 2019-07-2020-01 | 8,369 | 44.3% | +0.0 bps | Yes |
| Window 11 | 2020-01-2020-07 | 8,991 | 44.9% | -0.3 bps | Yes |
| Window 12 | 2020-07-2021-01 | 8,843 | 44.0% | +0.0 bps | Yes |
| Window 13 | 2021-01-2021-07 | 8,698 | 44.2% | +0.0 bps | Yes |
| Window 14 | 2021-07-2022-01 | 9,187 | 45.7% | -0.0 bps | Yes |
| Window 15 | 2022-01-2022-07 | 8,835 | 45.3% | -0.2 bps | Yes |
| Window 16 | 2022-07-2023-01 | 9,151 | 46.1% | -0.0 bps | Yes |
| Window 17 | 2023-01-2023-07 | 9,204 | 45.9% | +0.0 bps | Yes |
| Window 18 | 2023-07-2024-01 | 8,754 | 45.2% | -0.0 bps | Yes |
| Window 19 | 2024-01-2024-07 | 9,040 | 46.0% | -0.0 bps | Yes |
| Window 20 | 2024-07-2025-01 | 9,130 | 45.4% | +0.0 bps | Yes |
| Window 21 | 2025-01-2025-07 | 8,951 | 46.4% | +0.0 bps | Yes |
| Window 22 | 2025-07-2025-11 | 7,043 | 46.7% | -0.1 bps | Yes |

Coefficient of variation: 0.05 (STABLE)
Mean rate: 44.1%, Std: 2.0%

### Pattern: 2D continuation
| Window | Period | Occurrences | Next=2D Rate | Avg Fwd Return (bps) | Stable? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Window 1 | 2015-01-2015-07 | 7,504 | 40.3% | +0.1 bps | Yes |
| Window 2 | 2015-07-2016-01 | 8,348 | 43.3% | +0.2 bps | Yes |
| Window 3 | 2016-01-2016-07 | 7,958 | 42.9% | +0.2 bps | Yes |
| Window 4 | 2016-07-2017-01 | 7,483 | 40.9% | +0.1 bps | Yes |
| Window 5 | 2017-01-2017-07 | 7,110 | 40.4% | +0.1 bps | Yes |
| Window 6 | 2017-07-2018-01 | 6,553 | 38.4% | +0.1 bps | Yes |
| Window 7 | 2018-01-2018-07 | 8,317 | 45.3% | +0.1 bps | Yes |
| Window 8 | 2018-07-2019-01 | 8,362 | 44.0% | +0.2 bps | Yes |
| Window 9 | 2019-01-2019-07 | 8,143 | 43.7% | +0.1 bps | Yes |
| Window 10 | 2019-07-2020-01 | 8,103 | 43.3% | +0.1 bps | Yes |
| Window 11 | 2020-01-2020-07 | 8,766 | 45.4% | +0.2 bps | Yes |
| Window 12 | 2020-07-2021-01 | 8,194 | 43.6% | +0.1 bps | Yes |
| Window 13 | 2021-01-2021-07 | 8,131 | 44.1% | +0.1 bps | Yes |
| Window 14 | 2021-07-2022-01 | 8,736 | 44.8% | +0.1 bps | Yes |
| Window 15 | 2022-01-2022-07 | 8,939 | 45.9% | -0.1 bps | Yes |
| Window 16 | 2022-07-2023-01 | 8,813 | 45.8% | +0.0 bps | Yes |
| Window 17 | 2023-01-2023-07 | 8,082 | 43.5% | +0.1 bps | Yes |
| Window 18 | 2023-07-2024-01 | 8,132 | 43.6% | +0.0 bps | Yes |
| Window 19 | 2024-01-2024-07 | 7,805 | 42.0% | +0.0 bps | Yes |
| Window 20 | 2024-07-2025-01 | 8,211 | 43.0% | -0.0 bps | Yes |
| Window 21 | 2025-01-2025-07 | 8,399 | 45.7% | -0.1 bps | Yes |
| Window 22 | 2025-07-2025-11 | 6,329 | 44.0% | +0.1 bps | Yes |

Coefficient of variation: 0.04 (STABLE)
Mean rate: 43.4%, Std: 1.9%

### Pattern: 2D-1-2U reversal
| Window | Period | Occurrences | Next=2U Rate | Avg Fwd Return (bps) | Stable? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Window 1 | 2015-01-2015-07 | 1,776 | 42.7% | -0.1 bps | Yes |
| Window 2 | 2015-07-2016-01 | 1,575 | 48.1% | -0.0 bps | Yes |
| Window 3 | 2016-01-2016-07 | 1,576 | 46.7% | -0.1 bps | Yes |
| Window 4 | 2016-07-2017-01 | 1,753 | 44.6% | +0.0 bps | Yes |
| Window 5 | 2017-01-2017-07 | 1,741 | 46.1% | +0.1 bps | Yes |
| Window 6 | 2017-07-2018-01 | 1,753 | 42.1% | -0.0 bps | Yes |
| Window 7 | 2018-01-2018-07 | 1,396 | 48.9% | +0.0 bps | Yes |
| Window 8 | 2018-07-2019-01 | 1,430 | 47.5% | -0.1 bps | Yes |
| Window 9 | 2019-01-2019-07 | 1,391 | 46.7% | +0.0 bps | Yes |
| Window 10 | 2019-07-2020-01 | 1,458 | 47.8% | -0.0 bps | Yes |
| Window 11 | 2020-01-2020-07 | 1,182 | 50.0% | +0.1 bps | Yes |
| Window 12 | 2020-07-2021-01 | 1,304 | 49.5% | +0.2 bps | Yes |
| Window 13 | 2021-01-2021-07 | 1,331 | 50.1% | +0.3 bps | Yes |
| Window 14 | 2021-07-2022-01 | 1,344 | 47.3% | +0.0 bps | Yes |
| Window 15 | 2022-01-2022-07 | 1,180 | 50.7% | +0.2 bps | Yes |
| Window 16 | 2022-07-2023-01 | 1,179 | 49.4% | -0.1 bps | Yes |
| Window 17 | 2023-01-2023-07 | 1,211 | 51.3% | +0.1 bps | Yes |
| Window 18 | 2023-07-2024-01 | 1,252 | 47.7% | +0.1 bps | Yes |
| Window 19 | 2024-01-2024-07 | 1,372 | 48.5% | -0.1 bps | Yes |
| Window 20 | 2024-07-2025-01 | 1,356 | 49.8% | +0.0 bps | Yes |
| Window 21 | 2025-01-2025-07 | 1,139 | 48.4% | -0.1 bps | Yes |
| Window 22 | 2025-07-2025-11 | 1,008 | 48.0% | +0.0 bps | Yes |

Coefficient of variation: 0.05 (STABLE)
Mean rate: 47.8%, Std: 2.3%

### Pattern: 2U-1-2D reversal
| Window | Period | Occurrences | Next=2D Rate | Avg Fwd Return (bps) | Stable? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Window 1 | 2015-01-2015-07 | 1,782 | 44.7% | +0.0 bps | Yes |
| Window 2 | 2015-07-2016-01 | 1,572 | 45.8% | -0.0 bps | Yes |
| Window 3 | 2016-01-2016-07 | 1,699 | 44.5% | +0.1 bps | Yes |
| Window 4 | 2016-07-2017-01 | 1,748 | 41.2% | +0.2 bps | Yes |
| Window 5 | 2017-01-2017-07 | 1,763 | 42.6% | +0.0 bps | Yes |
| Window 6 | 2017-07-2018-01 | 1,870 | 39.7% | +0.1 bps | Yes |
| Window 7 | 2018-01-2018-07 | 1,501 | 45.8% | -0.1 bps | Yes |
| Window 8 | 2018-07-2019-01 | 1,553 | 46.8% | +0.1 bps | Yes |
| Window 9 | 2019-01-2019-07 | 1,422 | 47.8% | +0.1 bps | Yes |
| Window 10 | 2019-07-2020-01 | 1,455 | 45.8% | -0.0 bps | Yes |
| Window 11 | 2020-01-2020-07 | 1,333 | 48.1% | -0.2 bps | Yes |
| Window 12 | 2020-07-2021-01 | 1,309 | 45.5% | -0.0 bps | Yes |
| Window 13 | 2021-01-2021-07 | 1,298 | 42.8% | +0.0 bps | Yes |
| Window 14 | 2021-07-2022-01 | 1,300 | 50.2% | +0.0 bps | Yes |
| Window 15 | 2022-01-2022-07 | 1,171 | 49.4% | +0.1 bps | Yes |
| Window 16 | 2022-07-2023-01 | 1,169 | 50.1% | -0.2 bps | Yes |
| Window 17 | 2023-01-2023-07 | 1,177 | 47.7% | -0.1 bps | Yes |
| Window 18 | 2023-07-2024-01 | 1,264 | 45.4% | -0.1 bps | Yes |
| Window 19 | 2024-01-2024-07 | 1,267 | 44.8% | +0.1 bps | Yes |
| Window 20 | 2024-07-2025-01 | 1,225 | 48.2% | -0.0 bps | Yes |
| Window 21 | 2025-01-2025-07 | 1,090 | 48.0% | +0.1 bps | Yes |
| Window 22 | 2025-07-2025-11 | 868 | 46.8% | +0.1 bps | Yes |

Coefficient of variation: 0.06 (STABLE)
Mean rate: 46.0%, Std: 2.7%

