# Phase 3: ORB-Based Strategies — SPY

Generated: 2026-02-22 06:05:33
Data: 2015-01-02 09:30:00 to 2025-11-14 16:00:00 (1,068,448 bars)

## 3D. ORB Width Analysis — SPY

ORB characteristics, breakout frequency, and timing.

### SPY: 5m ORB
**ORB Range Statistics:**

| Metric | Value |
| :--- | :--- |
| Mean Range (bps) | +22.4 bps |
| Median Range (bps) | +18.3 bps |
| P10 Range (bps) | +9.9 bps |
| P25 Range (bps) | +13.0 bps |
| P75 Range (bps) | +26.5 bps |
| P90 Range (bps) | +39.1 bps |
| Trading Days | 2,734 |

**Breakout Frequency:**

| Outcome | Frequency |
| :--- | :--- |
| Broke ORB High | 83.3% |
| Broke ORB Low | 81.1% |
| Stayed Within ORB | 0.0% |

**Breakout Timing (minutes after ORB close):**

| Metric | Value |
| :--- | :--- |
| Median first breakout | 4 min |
| Mean first breakout | 7 min |
| P25 (fast breakout) | 2 min |
| P75 (slow breakout) | 9 min |


**ORB Range vs Daily Range Correlation:** 0.683

### SPY: 15m ORB
**ORB Range Statistics:**

| Metric | Value |
| :--- | :--- |
| Mean Range (bps) | +33.2 bps |
| Median Range (bps) | +26.7 bps |
| P10 Range (bps) | +14.1 bps |
| P25 Range (bps) | +18.5 bps |
| P75 Range (bps) | +39.0 bps |
| P90 Range (bps) | +57.4 bps |
| Trading Days | 2,735 |

**Breakout Frequency:**

| Outcome | Frequency |
| :--- | :--- |
| Broke ORB High | 77.6% |
| Broke ORB Low | 74.1% |
| Stayed Within ORB | 0.0% |

**Breakout Timing (minutes after ORB close):**

| Metric | Value |
| :--- | :--- |
| Median first breakout | 8 min |
| Mean first breakout | 16 min |
| P25 (fast breakout) | 3 min |
| P75 (slow breakout) | 18 min |


**ORB Range vs Daily Range Correlation:** 0.735

### SPY: 30m ORB
**ORB Range Statistics:**

| Metric | Value |
| :--- | :--- |
| Mean Range (bps) | +43.6 bps |
| Median Range (bps) | +34.4 bps |
| P10 Range (bps) | +17.8 bps |
| P25 Range (bps) | +23.9 bps |
| P75 Range (bps) | +51.6 bps |
| P90 Range (bps) | +77.3 bps |
| Trading Days | 2,735 |

**Breakout Frequency:**

| Outcome | Frequency |
| :--- | :--- |
| Broke ORB High | 72.7% |
| Broke ORB Low | 67.1% |
| Stayed Within ORB | 0.0% |

**Breakout Timing (minutes after ORB close):**

| Metric | Value |
| :--- | :--- |
| Median first breakout | 12 min |
| Mean first breakout | 27 min |
| P25 (fast breakout) | 4 min |
| P75 (slow breakout) | 30 min |


**ORB Range vs Daily Range Correlation:** 0.764

## 3A-3C. ORB Strategy Backtests — SPY

Comparing ORB breakout, failure, and range-bound strategies.

### SPY: 5m ORB Results
| Strategy | Trades | Win Rate | Profit Factor | Sharpe | Expectancy (bps) | Avg Win | Avg Loss |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 8,201 | 45.6% | 1.00 | 0.01 | +0.0 bps | +16.1 bps | -13.5 bps |
| Failure | 1,114 | 46.2% | 1.01 | 0.07 | +0.1 bps | +15.1 bps | -12.9 bps |
| Range Bound | 3,363 | 45.6% | 0.97 | -0.25 | -0.2 bps | +13.5 bps | -11.6 bps |

### SPY: 15m ORB Results
| Strategy | Trades | Win Rate | Profit Factor | Sharpe | Expectancy (bps) | Avg Win | Avg Loss |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 8,166 | 45.8% | 1.00 | -0.03 | -0.0 bps | +15.2 bps | -12.9 bps |
| Failure | 989 | 46.5% | 1.01 | 0.06 | +0.1 bps | +14.3 bps | -12.4 bps |
| Range Bound | 4,136 | 46.0% | 0.95 | -0.49 | -0.3 bps | +13.2 bps | -11.9 bps |

### SPY: 30m ORB Results
| Strategy | Trades | Win Rate | Profit Factor | Sharpe | Expectancy (bps) | Avg Win | Avg Loss |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Breakout | 8,058 | 46.4% | 1.00 | 0.05 | +0.0 bps | +14.1 bps | -12.1 bps |
| Failure | 912 | 45.8% | 0.93 | -0.50 | -0.5 bps | +13.5 bps | -12.3 bps |
| Range Bound | 4,782 | 44.8% | 0.92 | -0.81 | -0.5 bps | +13.2 bps | -11.6 bps |


**Best strategy for SPY:** failure with 5m ORB (Sharpe 0.07, WR 46.2%, n=1114)

#### Exit Reason Breakdown — failure/5m
| Exit Reason | Trades | Win Rate | Avg Return (bps) |
| :--- | :--- | :--- | :--- |
| eod | 37 | 54.0% | +3.4 bps |
| stop | 353 | 0.0% | -18.4 bps |
| target | 131 | 100.0% | +34.5 bps |
| time_stop | 593 | 61.0% | +3.2 bps |

