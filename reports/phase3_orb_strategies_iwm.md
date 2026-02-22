# Phase 3: ORB-Based Strategies — IWM

Generated: 2026-02-22 22:14:10
Data: 2015-01-02 09:30:00 to 2026-02-20 16:00:00 (1,089,011 bars)

## 3D. ORB Width Analysis — IWM

ORB characteristics, breakout frequency, and timing.

### IWM: 5m ORB
**ORB Range Statistics:**

| Metric | Value |
| :--- | :--- |
| Mean Range (bps) | +43.2 bps |
| Median Range (bps) | +37.8 bps |
| P10 Range (bps) | +21.2 bps |
| P25 Range (bps) | +27.9 bps |
| P75 Range (bps) | +52.3 bps |
| P90 Range (bps) | +70.2 bps |
| Trading Days | 2,790 |

**Breakout Frequency:**

| Outcome | Frequency |
| :--- | :--- |
| Broke ORB High | 77.2% |
| Broke ORB Low | 79.4% |
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
| Mean Range (bps) | +61.0 bps |
| Median Range (bps) | +53.5 bps |
| P10 Range (bps) | +30.8 bps |
| P25 Range (bps) | +39.8 bps |
| P75 Range (bps) | +73.3 bps |
| P90 Range (bps) | +97.0 bps |
| Trading Days | 2,791 |

**Breakout Frequency:**

| Outcome | Frequency |
| :--- | :--- |
| Broke ORB High | 69.8% |
| Broke ORB Low | 70.7% |
| Stayed Within ORB | 0.0% |

**Breakout Timing (minutes after ORB close):**

| Metric | Value |
| :--- | :--- |
| Median first breakout | 7 min |
| Mean first breakout | 18 min |
| P25 (fast breakout) | 3 min |
| P75 (slow breakout) | 18 min |


**ORB Range vs Daily Range Correlation:** 0.666

### IWM: 30m ORB
**ORB Range Statistics:**

| Metric | Value |
| :--- | :--- |
| Mean Range (bps) | +77.5 bps |
| Median Range (bps) | +67.9 bps |
| P10 Range (bps) | +38.1 bps |
| P25 Range (bps) | +50.1 bps |
| P75 Range (bps) | +93.1 bps |
| P90 Range (bps) | +124.6 bps |
| Trading Days | 2,791 |

**Breakout Frequency:**

| Outcome | Frequency |
| :--- | :--- |
| Broke ORB High | 63.8% |
| Broke ORB Low | 63.4% |
| Stayed Within ORB | 0.0% |

**Breakout Timing (minutes after ORB close):**

| Metric | Value |
| :--- | :--- |
| Median first breakout | 12 min |
| Mean first breakout | 31 min |
| P25 (fast breakout) | 4 min |
| P75 (slow breakout) | 33 min |


**ORB Range vs Daily Range Correlation:** 0.716

## 3A-3C. ORB Strategy Backtests — IWM

Comparing ORB breakout, failure, and range-bound strategies.

### IWM: 5m ORB Results
| Strategy | Trades | Win Rate | Profit Factor | Sharpe | Expectancy (bps) | Avg Win | Avg Loss |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 8,337 | 41.0% | 1.01 | 0.11 | +0.1 bps | +26.1 bps | -18.0 bps |
| Failure | 1,092 | 39.7% | 0.94 | -0.51 | -0.6 bps | +23.6 bps | -16.6 bps |
| Range Bound | 3,638 | 41.3% | 0.93 | -0.68 | -0.6 bps | +20.7 bps | -15.6 bps |

### IWM: 15m ORB Results
| Strategy | Trades | Win Rate | Profit Factor | Sharpe | Expectancy (bps) | Avg Win | Avg Loss |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 8,222 | 42.5% | 1.03 | 0.37 | +0.3 bps | +23.8 bps | -17.1 bps |
| Failure | 973 | 39.5% | 0.90 | -0.79 | -1.0 bps | +22.4 bps | -16.2 bps |
| Range Bound | 4,440 | 42.3% | 0.95 | -0.53 | -0.5 bps | +20.3 bps | -15.7 bps |

### IWM: 30m ORB Results
| Strategy | Trades | Win Rate | Profit Factor | Sharpe | Expectancy (bps) | Avg Win | Avg Loss |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 7,989 | 42.9% | 1.00 | 0.03 | +0.0 bps | +21.6 bps | -16.2 bps |
| Failure | 919 | 40.9% | 0.90 | -0.76 | -1.0 bps | +20.8 bps | -16.1 bps |
| Range Bound | 5,064 | 41.8% | 0.92 | -0.88 | -0.7 bps | +19.6 bps | -15.3 bps |


**Best strategy for IWM:** breakout with 15m ORB (Sharpe 0.37, WR 42.5%, n=8222)

#### Exit Reason Breakdown — breakout/15m
| Exit Reason | Trades | Win Rate | Avg Return (bps) |
| :--- | :--- | :--- | :--- |
| eod | 22 | 55.0% | +1.8 bps |
| stop | 3,995 | 0.0% | -19.2 bps |
| target | 1,889 | 100.0% | +34.5 bps |
| time_stop | 2,316 | 69.0% | +6.0 bps |

