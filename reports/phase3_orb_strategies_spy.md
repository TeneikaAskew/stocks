# Phase 3: ORB-Based Strategies — SPY

Generated: 2026-02-22 21:44:01
Data: 2023-01-03 09:30:00 to 2026-02-20 16:00:00 (295,205 bars)

## 3D. ORB Width Analysis — SPY

ORB characteristics, breakout frequency, and timing.

### SPY: 5m ORB
**ORB Range Statistics:**

| Metric | Value |
| :--- | :--- |
| Mean Range (bps) | +19.4 bps |
| Median Range (bps) | +17.2 bps |
| P10 Range (bps) | +10.2 bps |
| P25 Range (bps) | +13.0 bps |
| P75 Range (bps) | +23.1 bps |
| P90 Range (bps) | +31.1 bps |
| Trading Days | 755 |

**Breakout Frequency:**

| Outcome | Frequency |
| :--- | :--- |
| Broke ORB High | 85.2% |
| Broke ORB Low | 81.6% |
| Stayed Within ORB | 0.0% |

**Breakout Timing (minutes after ORB close):**

| Metric | Value |
| :--- | :--- |
| Median first breakout | 4 min |
| Mean first breakout | 7 min |
| P25 (fast breakout) | 2 min |
| P75 (slow breakout) | 9 min |


**ORB Range vs Daily Range Correlation:** 0.557

### SPY: 15m ORB
**ORB Range Statistics:**

| Metric | Value |
| :--- | :--- |
| Mean Range (bps) | +28.8 bps |
| Median Range (bps) | +24.9 bps |
| P10 Range (bps) | +14.0 bps |
| P25 Range (bps) | +17.8 bps |
| P75 Range (bps) | +34.1 bps |
| P90 Range (bps) | +47.5 bps |
| Trading Days | 755 |

**Breakout Frequency:**

| Outcome | Frequency |
| :--- | :--- |
| Broke ORB High | 78.1% |
| Broke ORB Low | 74.3% |
| Stayed Within ORB | 0.0% |

**Breakout Timing (minutes after ORB close):**

| Metric | Value |
| :--- | :--- |
| Median first breakout | 7 min |
| Mean first breakout | 14 min |
| P25 (fast breakout) | 3 min |
| P75 (slow breakout) | 17 min |


**ORB Range vs Daily Range Correlation:** 0.651

### SPY: 30m ORB
**ORB Range Statistics:**

| Metric | Value |
| :--- | :--- |
| Mean Range (bps) | +39.1 bps |
| Median Range (bps) | +33.7 bps |
| P10 Range (bps) | +17.8 bps |
| P25 Range (bps) | +23.9 bps |
| P75 Range (bps) | +47.2 bps |
| P90 Range (bps) | +66.1 bps |
| Trading Days | 755 |

**Breakout Frequency:**

| Outcome | Frequency |
| :--- | :--- |
| Broke ORB High | 72.7% |
| Broke ORB Low | 67.9% |
| Stayed Within ORB | 0.0% |

**Breakout Timing (minutes after ORB close):**

| Metric | Value |
| :--- | :--- |
| Median first breakout | 10 min |
| Mean first breakout | 23 min |
| P25 (fast breakout) | 3 min |
| P75 (slow breakout) | 26 min |


**ORB Range vs Daily Range Correlation:** 0.661

## 3A-3C. ORB Strategy Backtests — SPY

Comparing ORB breakout, failure, and range-bound strategies.

### SPY: 5m ORB Results
| Strategy | Trades | Win Rate | Profit Factor | Sharpe | Expectancy (bps) | Avg Win | Avg Loss |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 2,265 | 47.6% | 1.04 | 0.44 | +0.3 bps | +15.6 bps | -13.7 bps |
| Failure | 306 | 44.8% | 1.03 | 0.20 | +0.2 bps | +16.0 bps | -12.6 bps |
| Range Bound | 874 | 45.4% | 0.99 | -0.06 | -0.0 bps | +13.3 bps | -11.1 bps |

### SPY: 15m ORB Results
| Strategy | Trades | Win Rate | Profit Factor | Sharpe | Expectancy (bps) | Avg Win | Avg Loss |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 2,262 | 48.9% | 1.10 | 1.04 | +0.6 bps | +14.8 bps | -12.9 bps |
| Failure | 280 | 42.1% | 0.81 | -1.45 | -1.4 bps | +14.4 bps | -12.9 bps |
| Range Bound | 1,051 | 44.6% | 1.04 | 0.31 | +0.2 bps | +14.3 bps | -11.1 bps |

### SPY: 30m ORB Results
| Strategy | Trades | Win Rate | Profit Factor | Sharpe | Expectancy (bps) | Avg Win | Avg Loss |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 2,247 | 49.8% | 1.09 | 0.90 | +0.5 bps | +13.4 bps | -12.2 bps |
| Failure | 249 | 41.0% | 0.91 | -0.62 | -0.6 bps | +14.4 bps | -11.0 bps |
| Range Bound | 1,233 | 42.7% | 0.93 | -0.72 | -0.5 bps | +13.8 bps | -11.1 bps |


**Best strategy for SPY:** breakout with 15m ORB (Sharpe 1.04, WR 48.9%, n=2262)

#### Exit Reason Breakdown — breakout/15m
| Exit Reason | Trades | Win Rate | Avg Return (bps) |
| :--- | :--- | :--- | :--- |
| eod | 1 | 100.0% | +9.0 bps |
| stop | 687 | 0.0% | -17.9 bps |
| target | 233 | 100.0% | +33.3 bps |
| time_stop | 1,341 | 65.0% | +4.5 bps |

