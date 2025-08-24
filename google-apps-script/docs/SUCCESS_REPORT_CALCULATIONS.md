# Success Report Calculations and Metrics Guide

## Overview

This document explains all the calculations and metrics used in the Success Report analysis.

## Core Metrics

### 1. Total Trades
**Definition**: The total number of trade entries across all strategies in the spreadsheet.

**Calculation**: 
```javascript
totalTrades = allTrades.length
```

### 2. Hit Rate
**Definition**: The percentage of trades where the strike price was reached at any point during the holding period.

**Calculation**:
```javascript
hitTrades = trades.filter(t => t.wasHit).length
hitRate = (hitTrades / totalTrades * 100) + '%'

// Where wasHit is determined by:
wasHit = strikeHit.some(hit => hit !== "NO" && hit !== null && parseFloat(hit) > 0)
```

**Interpretation**: 
- A 70% hit rate means 70 out of 100 trades reached their strike price
- Higher is generally better, but must be considered alongside profitability

### 3. Profitable Rate
**Definition**: The percentage of trades that were profitable when they hit the strike price.

**Calculation**:
```javascript
profitableTrades = trades.filter(t => {
  if (!t.wasHit) return false;
  
  // Find the first day it was hit
  const hitIndex = t.strikeHit.findIndex(hit => hit !== null && hit !== "NO" && parseFloat(hit) > 0);
  if (hitIndex === -1) return false;
  
  // Compare favorable vs unfavorable at that day
  const favorable = parseFloat(t.maxFavorable[hitIndex]) || 0;
  const unfavorable = parseFloat(t.minUnfavorable[hitIndex]) || 0;
  
  return favorable > unfavorable;
}).length

profitableRate = (profitableTrades / totalTrades * 100) + '%'
```

**Key Points**:
- Only considers trades that actually hit their strike
- Compares max favorable move vs max unfavorable move on the hit day
- A trade with 5% favorable and 2% unfavorable = profitable
- A trade with 2% favorable and 5% unfavorable = not profitable

### 4. Average Risk/Reward Ratio
**Definition**: The average ratio of maximum profit to maximum loss across all trades.

**Calculation**:
```javascript
avgRiskReward = trades.reduce((sum, t) => sum + (t.riskReward || 0), 0) / totalTrades

// Where riskReward for each trade is:
riskReward = maxFavorable / maxUnfavorable
```

**Interpretation**:
- RR of 2.0 means average trade has 2x potential profit vs loss
- Higher is better (typical targets: 2:1 or 3:1)

### 5. Average Days to Hit
**Definition**: The average number of trading days it takes for winning trades to reach their strike price.

**Calculation**:
```javascript
avgDaysToHit = trades
  .filter(t => t.daysToHit !== undefined)
  .reduce((sum, t) => sum + t.daysToHit, 0) / hitTrades

// Where daysToHit is calculated as:
daysToHit = Math.floor((firstHitDate - runDate) / (1000 * 60 * 60 * 24))
```

**Uses**:
- Helps optimize holding period
- Identifies strategies with faster payoffs

## Multi-Day Profitability Analysis

### Purpose
Tracks how trades perform over their 6-day holding period to identify optimal exit timing.

### Key Metrics

#### 1. Sustained Profitability
**Definition**: Trades that remain profitable for multiple consecutive days.

**Calculation**:
```javascript
// For each trade, check consecutive profitable days
let consecutiveDays = 0;
for (let i = 0; i < trade.maxFavorable.length; i++) {
  const favorable = parseFloat(trade.maxFavorable[i]) || 0;
  const unfavorable = parseFloat(trade.minUnfavorable[i]) || 0;
  
  if (favorable > unfavorable) {
    consecutiveDays++;
  } else {
    break; // Stop counting at first unprofitable day
  }
}
```

#### 2. Profitability by Day
**Definition**: Statistics for each day (0-5) across all trades.

**For each day**:
- Total trades active
- Number profitable that day
- Average profit percentage
- Profitability rate

**Example Output**:
```
Day 0: 1000 trades, 45% profitable, avg profit 2.3%
Day 1: 980 trades, 52% profitable, avg profit 3.1%
Day 2: 950 trades, 48% profitable, avg profit 2.8%
```

#### 3. Best Holding Period
**Definition**: Identifies which day typically offers the best risk/reward.

**Analysis**:
- Peak profitability day (highest average profit)
- Most consistent day (highest profitable rate)
- Optimal exit day (best profit/risk ratio)

## Strategy-Specific Breakdown

Each strategy type gets its own analysis:

### Metrics by Strategy
1. **Total Trades**: Count for that strategy
2. **Hit Rate**: Percentage reaching strike
3. **Profitable Rate**: Percentage profitable when hit
4. **Average Risk/Reward**: Mean RR ratio
5. **Average Days to Hit**: Mean time to strike
6. **Profit Factor**: Total profits / Total losses

### Example:
```
Long Calls:
- Total: 500 trades
- Hit Rate: 72%
- Profitable: 65%
- Avg RR: 2.3
- Days to Hit: 2.1

Bull Call Spreads:
- Total: 300 trades
- Hit Rate: 68%
- Profitable: 71%
- Avg RR: 1.8
- Days to Hit: 2.5
```

## Earnings Timing Analysis

### Purpose
Analyzes how earnings announcements affect trade performance.

### Key Fields Used
- **nextEPSDate**: The earnings announcement date
- **releaseTime**: 
  - 1 = Before market open (< 9:30 AM)
  - 3 = After market close (> 4:00 PM)
- **runDate**: Trade entry date
- **firstHitDate**: When strike was first reached

### Calculations

#### 1. Pre vs Post Earnings Classification
```javascript
// Determine if earnings occur during market hours
const epsDate = new Date(trade.nextEPSDate);
const isPreMarket = trade.releaseTime === 1;
const isAfterMarket = trade.releaseTime === 3;

// Adjust effective earnings time
if (isPreMarket) {
  // Earnings before open affect that day's trading
  epsDate.setHours(9, 30, 0, 0);
} else if (isAfterMarket) {
  // Earnings after close affect next day's trading
  epsDate.setDate(epsDate.getDate() + 1);
  epsDate.setHours(9, 30, 0, 0);
}

// Classify the hit
const hitBeforeEarnings = firstHitDate < epsDate;
```

#### 2. Days to Earnings
```javascript
const daysToEarnings = Math.floor((epsDate - runDate) / (1000 * 60 * 60 * 24));
```

#### 3. Key Metrics
- **Pre-Earnings Hit Rate**: % of trades hitting before earnings
- **Post-Earnings Hit Rate**: % of trades hitting after earnings
- **Avg Days to Hit (Pre)**: Average time for pre-earnings hits
- **Avg Days to Hit (Post)**: Average time for post-earnings hits

### Example Analysis
```
Total Trades with Earnings Data: 850
Pre-Earnings Hits: 450 (52.9%)
Post-Earnings Hits: 400 (47.1%)
Avg Days to Hit Pre-Earnings: 1.8 days
Avg Days to Hit Post-Earnings: 3.2 days
Recommendation: Enter positions 3-5 days before earnings for faster hits
```

## Risk/Reward Pattern Analysis

### By Risk/Reward Ratio Groups
Trades grouped by RR ratio:
- 0-1: Low RR
- 1-2: Moderate RR  
- 2-3: Good RR
- 3+: Excellent RR

For each group:
- Count of trades
- Hit rate
- Average max profit
- Success rate

### Exit Timing Analysis
Identifies optimal exit points based on:
- Day with highest average profit
- Day with best profit/risk ratio
- Most consistent profitable day

## Top Performing Plays

### Selection Criteria
1. Trade must have hit strike price
2. Maximum favorable move > 5% (0.05 in decimal)
3. Sorted by highest profit potential

### Information Captured
- Ticker and strategy
- Entry date and strike price
- Maximum profit achieved
- Days to hit
- Number of profitable days
- Risk/reward ratio
- Key indicator values at entry
- Multi-day profit profile

## Data Quality Considerations

### Array Data Format
All array data (Strike_Hit, Max_Favorable, etc.) stored as JSON strings:
```
["0.025", "0.031", "0.028", "0.022", "0.018", "0.015"]
```

### Decimal vs Percentage
- Internal calculations use decimals (0.05 = 5%)
- Display values converted to percentages (0.05 → 5%)

### Missing Data Handling
- Empty arrays default to []
- Null values filtered before calculations
- "NO_DATA" entries excluded from analysis

## Performance Benchmarks

### Good Performance Indicators
- Hit Rate > 65%
- Profitable Rate > 55%
- Avg Risk/Reward > 2.0
- Avg Days to Hit < 3

### Warning Signs
- Hit Rate < 50%
- Profitable Rate < 45%
- Avg Risk/Reward < 1.5
- Many trades with "NO_DATA"