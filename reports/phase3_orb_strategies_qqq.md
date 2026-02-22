# Phase 3: ORB-Based Strategies — QQQ

Generated: 2026-02-22 06:20:55
Data: 2015-01-02 09:30:00 to 2025-11-14 16:00:00 (1,067,740 bars)

## 3D. ORB Width Analysis — QQQ

ORB characteristics, breakout frequency, and timing.

### QQQ: 5m ORB
**ORB Range Statistics:**

| Metric | Value |
| :--- | :--- |
| Mean Range (bps) | +34.8 bps |
| Median Range (bps) | +29.6 bps |
| P10 Range (bps) | +16.1 bps |
| P25 Range (bps) | +21.2 bps |
| P75 Range (bps) | +42.6 bps |
| P90 Range (bps) | +57.8 bps |
| Trading Days | 2,734 |

**Breakout Frequency:**

| Outcome | Frequency |
| :--- | :--- |
| Broke ORB High | 82.1% |
| Broke ORB Low | 78.2% |
| Stayed Within ORB | 0.0% |

**Breakout Timing (minutes after ORB close):**

| Metric | Value |
| :--- | :--- |
| Median first breakout | 4 min |
| Mean first breakout | 7 min |
| P25 (fast breakout) | 1 min |
| P75 (slow breakout) | 8 min |


**ORB Range vs Daily Range Correlation:** 0.728

### QQQ: 15m ORB
**ORB Range Statistics:**

| Metric | Value |
| :--- | :--- |
| Mean Range (bps) | +50.8 bps |
| Median Range (bps) | +42.8 bps |
| P10 Range (bps) | +22.9 bps |
| P25 Range (bps) | +30.5 bps |
| P75 Range (bps) | +61.5 bps |
| P90 Range (bps) | +86.6 bps |
| Trading Days | 2,735 |

**Breakout Frequency:**

| Outcome | Frequency |
| :--- | :--- |
| Broke ORB High | 75.4% |
| Broke ORB Low | 70.8% |
| Stayed Within ORB | 0.0% |

**Breakout Timing (minutes after ORB close):**

| Metric | Value |
| :--- | :--- |
| Median first breakout | 7 min |
| Mean first breakout | 16 min |
| P25 (fast breakout) | 3 min |
| P75 (slow breakout) | 18 min |


**ORB Range vs Daily Range Correlation:** 0.762

### QQQ: 30m ORB
**ORB Range Statistics:**

| Metric | Value |
| :--- | :--- |
| Mean Range (bps) | +65.2 bps |
| Median Range (bps) | +55.0 bps |
| P10 Range (bps) | +29.0 bps |
| P25 Range (bps) | +38.8 bps |
| P75 Range (bps) | +78.7 bps |
| P90 Range (bps) | +111.1 bps |
| Trading Days | 2,735 |

**Breakout Frequency:**

| Outcome | Frequency |
| :--- | :--- |
| Broke ORB High | 69.4% |
| Broke ORB Low | 63.4% |
| Stayed Within ORB | 0.0% |

**Breakout Timing (minutes after ORB close):**

| Metric | Value |
| :--- | :--- |
| Median first breakout | 12 min |
| Mean first breakout | 30 min |
| P25 (fast breakout) | 4 min |
| P75 (slow breakout) | 31 min |


**ORB Range vs Daily Range Correlation:** 0.788

## 3A-3C. ORB Strategy Backtests — QQQ

Comparing ORB breakout, failure, and range-bound strategies.

### QQQ: 5m ORB Results
| Strategy | Trades | Win Rate | Profit Factor | Sharpe | Expectancy (bps) | Avg Win | Avg Loss |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 8,196 | 43.2% | 1.01 | 0.17 | +0.1 bps | +22.2 bps | -16.6 bps |
| Failure | 1,091 | 45.1% | 1.07 | 0.50 | +0.6 bps | +20.6 bps | -15.8 bps |
| Range Bound | 3,545 | 43.7% | 0.93 | -0.65 | -0.6 bps | +17.6 bps | -14.7 bps |

### QQQ: 15m ORB Results
| Strategy | Trades | Win Rate | Profit Factor | Sharpe | Expectancy (bps) | Avg Win | Avg Loss |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 8,126 | 43.5% | 1.02 | 0.23 | +0.2 bps | +20.6 bps | -15.6 bps |
| Failure | 1,016 | 44.3% | 1.01 | 0.05 | +0.1 bps | +19.5 bps | -15.4 bps |
| Range Bound | 4,407 | 43.7% | 0.96 | -0.35 | -0.3 bps | +17.9 bps | -14.5 bps |

### QQQ: 30m ORB Results
| Strategy | Trades | Win Rate | Profit Factor | Sharpe | Expectancy (bps) | Avg Win | Avg Loss |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 7,913 | 43.4% | 1.01 | 0.15 | +0.1 bps | +19.4 bps | -14.7 bps |
| Failure | 963 | 42.2% | 0.84 | -1.29 | -1.5 bps | +18.1 bps | -15.7 bps |
| Range Bound | 5,029 | 43.2% | 0.95 | -0.54 | -0.4 bps | +17.6 bps | -14.2 bps |


**Best strategy for QQQ:** failure with 5m ORB (Sharpe 0.50, WR 45.1%, n=1091)

#### Exit Reason Breakdown — failure/5m
| Exit Reason | Trades | Win Rate | Avg Return (bps) |
| :--- | :--- | :--- | :--- |
| eod | 28 | 54.0% | +3.5 bps |
| stop | 455 | 0.0% | -19.1 bps |
| target | 207 | 100.0% | +34.6 bps |
| time_stop | 401 | 67.0% | +5.1 bps |

