# Phase 3: ORB-Based Strategies — IWM

Generated: 2026-02-22 05:50:09
Data: 2015-01-02 09:30:00 to 2025-11-14 16:00:00 (1,067,154 bars)

## 3D. ORB Width Analysis — IWM

ORB characteristics, breakout frequency, and timing.

### IWM: 5m ORB
**ORB Range Statistics:**

| Metric | Value |
| :--- | :--- |
| Mean Range (bps) | +43.2 bps |
| Median Range (bps) | +37.6 bps |
| P10 Range (bps) | +21.1 bps |
| P25 Range (bps) | +27.9 bps |
| P75 Range (bps) | +52.3 bps |
| P90 Range (bps) | +70.1 bps |
| Trading Days | 2,734 |

**Breakout Frequency:**

| Outcome | Frequency |
| :--- | :--- |
| Broke ORB High | 77.4% |
| Broke ORB Low | 79.6% |
| Stayed Within ORB | 0.0% |

**Breakout Timing (minutes after ORB close):**

| Metric | Value |
| :--- | :--- |
| Median first breakout | 4 min |
| Mean first breakout | 8 min |
| P25 (fast breakout) | 2 min |
| P75 (slow breakout) | 9 min |


**ORB Range vs Daily Range Correlation:** 0.633

### IWM: 15m ORB
**ORB Range Statistics:**

| Metric | Value |
| :--- | :--- |
| Mean Range (bps) | +60.9 bps |
| Median Range (bps) | +53.4 bps |
| P10 Range (bps) | +30.7 bps |
| P25 Range (bps) | +39.6 bps |
| P75 Range (bps) | +73.4 bps |
| P90 Range (bps) | +97.0 bps |
| Trading Days | 2,735 |

**Breakout Frequency:**

| Outcome | Frequency |
| :--- | :--- |
| Broke ORB High | 69.9% |
| Broke ORB Low | 70.9% |
| Stayed Within ORB | 0.0% |

**Breakout Timing (minutes after ORB close):**

| Metric | Value |
| :--- | :--- |
| Median first breakout | 7 min |
| Mean first breakout | 18 min |
| P25 (fast breakout) | 3 min |
| P75 (slow breakout) | 18 min |


**ORB Range vs Daily Range Correlation:** 0.665

### IWM: 30m ORB
**ORB Range Statistics:**

| Metric | Value |
| :--- | :--- |
| Mean Range (bps) | +77.5 bps |
| Median Range (bps) | +67.7 bps |
| P10 Range (bps) | +37.9 bps |
| P25 Range (bps) | +50.0 bps |
| P75 Range (bps) | +93.1 bps |
| P90 Range (bps) | +124.9 bps |
| Trading Days | 2,735 |

**Breakout Frequency:**

| Outcome | Frequency |
| :--- | :--- |
| Broke ORB High | 63.9% |
| Broke ORB Low | 63.6% |
| Stayed Within ORB | 0.0% |

**Breakout Timing (minutes after ORB close):**

| Metric | Value |
| :--- | :--- |
| Median first breakout | 12 min |
| Mean first breakout | 32 min |
| P25 (fast breakout) | 4 min |
| P75 (slow breakout) | 34 min |


**ORB Range vs Daily Range Correlation:** 0.713

## 3A-3C. ORB Strategy Backtests — IWM

Comparing ORB breakout, failure, and range-bound strategies.

### IWM: 5m ORB Results
| Strategy | Trades | Win Rate | Profit Factor | Sharpe | Expectancy (bps) | Avg Win | Avg Loss |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 8,169 | 41.1% | 1.01 | 0.12 | +0.1 bps | +26.1 bps | -18.0 bps |
| Failure | 1,074 | 39.7% | 0.94 | -0.48 | -0.6 bps | +23.7 bps | -16.6 bps |
| Range Bound | 3,578 | 41.3% | 0.93 | -0.67 | -0.6 bps | +20.7 bps | -15.6 bps |

### IWM: 15m ORB Results
| Strategy | Trades | Win Rate | Profit Factor | Sharpe | Expectancy (bps) | Avg Win | Avg Loss |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 8,054 | 42.5% | 1.03 | 0.35 | +0.3 bps | +23.8 bps | -17.1 bps |
| Failure | 958 | 39.5% | 0.90 | -0.79 | -1.0 bps | +22.4 bps | -16.2 bps |
| Range Bound | 4,359 | 42.3% | 0.95 | -0.56 | -0.5 bps | +20.3 bps | -15.7 bps |

### IWM: 30m ORB Results
| Strategy | Trades | Win Rate | Profit Factor | Sharpe | Expectancy (bps) | Avg Win | Avg Loss |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 7,824 | 42.8% | 1.00 | 0.01 | +0.0 bps | +21.6 bps | -16.2 bps |
| Failure | 902 | 41.0% | 0.90 | -0.72 | -0.9 bps | +20.8 bps | -16.1 bps |
| Range Bound | 4,978 | 41.7% | 0.91 | -0.92 | -0.8 bps | +19.6 bps | -15.3 bps |


**Best strategy for IWM:** breakout with 15m ORB (Sharpe 0.35, WR 42.5%, n=8054)

#### Exit Reason Breakdown — breakout/15m
| Exit Reason | Trades | Win Rate | Avg Return (bps) |
| :--- | :--- | :--- | :--- |
| eod | 22 | 55.0% | +1.8 bps |
| stop | 3,912 | 0.0% | -19.2 bps |
| target | 1,845 | 100.0% | +34.5 bps |
| time_stop | 2,275 | 69.0% | +6.0 bps |

