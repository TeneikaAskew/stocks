a# Data Dictionary: Earnings Options Analytics System

**Version:** 2.0
**Last Updated:** 2025-10-10
**Purpose:** Comprehensive reference for all data fields in the earnings options tracking and analytics system

---

## Table of Contents

1. [Overview](#overview)
2. [Core Trade Information](#core-trade-information)
3. [Pricing & Strike Data](#pricing--strike-data)
4. [Earnings Data](#earnings-data)
5. [Tracking Arrays (Day 0-5)](#tracking-arrays-day-0-5)
6. [Day Check Columns](#day-check-columns)
7. [Technical Indicators - Entry](#technical-indicators---entry)
8. [Technical Indicators - Hit (Arrays)](#technical-indicators---hit-arrays)
9. [OHLC Data](#ohlc-data)
10. [Risk/Reward Metrics](#riskreward-metrics)
11. [Result Columns](#result-columns)
12. [GoogleFinance Columns](#googlefinance-columns)
13. [Metadata & Timestamps](#metadata--timestamps)
14. [Strategy-Specific Columns](#strategy-specific-columns)

---

## Overview

This system tracks options trading strategies around earnings announcements. Data flows from Google Apps Script (fetching from EarningsWhispers API and Yahoo Finance) to Google Sheets, then exports to CSV for Python analytics.

### Key Concepts

- **Day 0-5 Indexing**: All arrays represent 6 trading days starting from entry (Run Date)
  - Day 0 = Entry day
  - Day 1 = 1 trading day after entry
  - Day 5 = 5 trading days after entry

- **Array Storage**: Arrays are stored as JSON strings in CSV: `[val0, val1, val2, val3, val4, val5]`

- **Bullish vs Bearish**:
  - Bullish strategies: Profit when price rises above strike
  - Bearish strategies: Profit when price falls below strike
  - Calculations adjust accordingly

---

## Core Trade Information

### Run Date
- **Type:** Date (YYYY-MM-DD)
- **Source:** Automated timestamp when trade is added
- **Purpose:** Entry date for the position
- **Example:** `2024-03-15`
- **Note:** Always the first column in sheets

### Strategy
- **Type:** String
- **Source:** Manual/API categorization
- **Purpose:** Identifies the options strategy type
- **Possible Values:**
  - `Long Calls`
  - `Bull Spreads`
  - `Covered Calls`
  - `Bear Spreads`
  - `Long Puts`
  - `Short Calls`
  - `Strangles`
  - `Straddles`
  - `Short Puts`
- **Example:** `Bull Spreads`

### company
- **Type:** String
- **Source:** API (EarningsWhispers)
- **Purpose:** Company name for the underlying stock
- **Example:** `Apple Inc.`

### ticker
- **Type:** String
- **Source:** API (EarningsWhispers)
- **Purpose:** Stock ticker symbol
- **Example:** `AAPL`
- **Note:** Used as key for price lookups

---

## Pricing & Strike Data

### strike
- **Type:** Number (decimal)
- **Source:** API (EarningsWhispers)
- **Purpose:** Option strike price for single-leg strategies
- **Example:** `175.00`
- **Strategies:** Long Calls, Long Puts, Covered Calls, Short Calls, Short Puts
- **Note:** For spreads, see `longStrike` and `shortStrike`

### longStrike
- **Type:** Number (decimal)
- **Source:** API (EarningsWhispers)
- **Purpose:** Long leg strike price for spread strategies
- **Example:** `170.00`
- **Strategies:** Bull Spreads, Bear Spreads
- **Note:** The strike you buy

### shortStrike
- **Type:** Number (decimal)
- **Source:** API (EarningsWhispers)
- **Purpose:** Short leg strike price for spread strategies
- **Example:** `175.00`
- **Strategies:** Bull Spreads, Bear Spreads
- **Note:** The strike you sell

### price
- **Type:** Number (decimal)
- **Source:** API (EarningsWhispers)
- **Purpose:** Stock price at time of recommendation
- **Example:** `168.50`
- **Strategies:** Long Calls, Long Puts

### lastTrade
- **Type:** Number (decimal)
- **Source:** API (EarningsWhispers)
- **Purpose:** Last traded option premium
- **Example:** `3.50`

### bid
- **Type:** Number (decimal)
- **Source:** API (EarningsWhispers)
- **Purpose:** Option bid price
- **Example:** `3.40`

### ask
- **Type:** Number (decimal)
- **Source:** API (EarningsWhispers)
- **Purpose:** Option ask price
- **Example:** `3.60`

### breakeven
- **Type:** Number (decimal)
- **Source:** API (EarningsWhispers)
- **Purpose:** Breakeven price for the strategy
- **Calculation:** Varies by strategy
  - Long Call: `strike + premium`
  - Bull Spread: `longStrike + netDebit`
  - Covered Call: `stockPrice - premium`
- **Example:** `178.50`

---

## Earnings Data

### nextEPSDate
- **Type:** Date (YYYY-MM-DD)
- **Source:** API (EarningsWhispers)
- **Purpose:** Next earnings announcement date
- **Example:** `2024-03-20`
- **Note:** Key for timing analysis

### releaseTime
- **Type:** String
- **Source:** API (EarningsWhispers)
- **Purpose:** Earnings release timing
- **Possible Values:**
  - `beforeOpen`
  - `afterClose`
  - `during`
  - Empty/unknown
- **Example:** `afterClose`

### lastEPSTime
- **Type:** String
- **Source:** API (EarningsWhispers)
- **Purpose:** Previous earnings release timing
- **Example:** `beforeOpen`
- **Strategies:** Long Calls, Long Puts

### confirmDate
- **Type:** Date (YYYY-MM-DD)
- **Source:** API (EarningsWhispers)
- **Purpose:** Date earnings date was confirmed
- **Example:** `2024-03-10`
- **Strategies:** Bull Spreads, Bear Spreads

### avgEPSMove
- **Type:** Number (percentage)
- **Source:** API (EarningsWhispers)
- **Purpose:** Average stock movement on earnings
- **Example:** `5.2` (means 5.2%)

### epsImpact
- **Type:** Number (percentage)
- **Source:** API (EarningsWhispers)
- **Purpose:** Expected earnings impact magnitude
- **Example:** `4.8`

---

## Tracking Arrays (Day 0-5)

All tracking arrays use JSON format: `[day0, day1, day2, day3, day4, day5]`

### Strike_Hit
- **Type:** Array of Numbers (decimals)
- **Source:** Calculated from Yahoo OHLC data
- **Purpose:** Percentage move from strike to day's extreme
- **Calculation:**
  - **Bullish strategies:** `(dayHigh - strike) / strike`
    - Positive = strike exceeded (profitable)
    - Negative = strike not reached
  - **Bearish strategies:** `(strike - dayLow) / strike`
    - Positive = strike breached (profitable)
    - Negative = strike not reached
- **Example:** `[-0.012, 0.005, 0.018, 0.023, 0.015, 0.008]`
- **Interpretation:** Day 0: -1.2% below strike, Day 1: +0.5% above strike, Day 2: +1.8% above strike
- **Storage Format:** 6-decimal precision in array
- **Note:** This is the PRIMARY profit tracking metric

### Max_Favorable
- **Type:** Array of Numbers (decimals)
- **Source:** Calculated from Yahoo OHLC data
- **Purpose:** Maximum favorable price movement each day
- **Calculation:**
  - **Bullish:** `(dayHigh - strike) / strike`
  - **Bearish:** `(strike - dayLow) / strike`
- **Example:** `[0.002, 0.015, 0.028, 0.035, 0.022, 0.018]`
- **Storage Format:** 6-decimal precision
- **Use Case:** Peak profit potential each day

### Min_Unfavorable
- **Type:** Array of Numbers (decimals)
- **Source:** Calculated from Yahoo OHLC data
- **Purpose:** Minimum unfavorable price movement each day
- **Calculation:**
  - **Bullish:** `(strike - dayLow) / strike` (negative when below strike)
  - **Bearish:** `(dayHigh - strike) / strike` (negative when above strike)
- **Example:** `[-0.008, -0.005, -0.002, 0.001, -0.003, -0.006]`
- **Storage Format:** 6-decimal precision
- **Use Case:** Worst case movement, risk assessment

---

## Day Check Columns

These columns store individual daily price checks (not arrays).

### Day0_Check
- **Type:** Number (price)
- **Source:** Yahoo Finance or OHLC close price
- **Purpose:** Stock price on Day 0 (entry)
- **Example:** `168.50`

### Day1_Check
- **Type:** Number (price)
- **Source:** Yahoo Finance or OHLC close price
- **Purpose:** Stock price on Day 1
- **Example:** `170.25`

### Day2_Check
- **Type:** Number (price)
- **Source:** Yahoo Finance or OHLC close price
- **Purpose:** Stock price on Day 2
- **Example:** `172.80`

### Day3_Check
- **Type:** Number (price)
- **Source:** Yahoo Finance or OHLC close price
- **Purpose:** Stock price on Day 3
- **Example:** `171.50`

### Day4_Check
- **Type:** Number (price)
- **Source:** Yahoo Finance or OHLC close price
- **Purpose:** Stock price on Day 4
- **Example:** `173.20`

### Day5_Check
- **Type:** Number (price)
- **Source:** Yahoo Finance or OHLC close price
- **Purpose:** Stock price on Day 5
- **Example:** `174.10`

**Note:** These are populated by active tracking (for current positions) or backfill (for expired positions)

---

## Technical Indicators - Entry

Entry indicators are calculated at trade entry (Day 0) for baseline conditions.

### Entry_RSI
- **Type:** Number (0-100)
- **Source:** Calculated from Yahoo historical data
- **Purpose:** Relative Strength Index at entry
- **Calculation:** 14-period RSI
- **Example:** `58.5`
- **Interpretation:**
  - < 30: Oversold
  - 30-70: Neutral
  - > 70: Overbought

### Entry_SMA20
- **Type:** Number (price)
- **Source:** Calculated from Yahoo historical data
- **Purpose:** 20-day Simple Moving Average at entry
- **Example:** `167.80`

### Entry_SMA50
- **Type:** Number (price)
- **Source:** Calculated from Yahoo historical data
- **Purpose:** 50-day Simple Moving Average at entry
- **Example:** `165.20`

### Entry_EMA9
- **Type:** Number (price)
- **Source:** Calculated from Yahoo historical data
- **Purpose:** 9-day Exponential Moving Average at entry
- **Example:** `168.90`

### Entry_EMA21
- **Type:** Number (price)
- **Source:** Calculated from Yahoo historical data
- **Purpose:** 21-day Exponential Moving Average at entry
- **Example:** `167.50`

### Entry_VWAP
- **Type:** Number (price)
- **Source:** Calculated from Yahoo historical data
- **Purpose:** Volume Weighted Average Price at entry
- **Example:** `168.25`

### Entry_RVOL
- **Type:** Number (ratio)
- **Source:** Calculated from Yahoo historical data
- **Purpose:** Relative Volume at entry
- **Calculation:** `currentVolume / 10dayAvgVolume`
- **Example:** `1.45` (means 145% of normal volume)

### Entry_ATR
- **Type:** Number (price)
- **Source:** Calculated from Yahoo historical data
- **Purpose:** Average True Range (14-period) at entry
- **Example:** `3.25`
- **Use Case:** Volatility measurement

### Entry_PriceVsSMA20
- **Type:** Number (percentage)
- **Source:** Calculated
- **Purpose:** Price position relative to 20-day SMA at entry
- **Calculation:** `(price - SMA20) / SMA20 * 100`
- **Example:** `0.42` (price is 0.42% above SMA20)

### Entry_PriceVsVWAP
- **Type:** Number (percentage)
- **Source:** Calculated
- **Purpose:** Price position relative to VWAP at entry
- **Calculation:** `(price - VWAP) / VWAP * 100`
- **Example:** `0.15`

---

## Technical Indicators - Hit (Arrays)

Hit indicators are arrays showing indicator values for Day 0 through Day 5.

### Hit_RSI
- **Type:** Array of Numbers (0-100)
- **Source:** Calculated from Yahoo historical data
- **Purpose:** Daily RSI values
- **Example:** `[58.5, 62.3, 65.8, 61.2, 59.7, 57.4]`
- **Storage:** JSON array, 2-decimal precision

### Hit_SMA20
- **Type:** Array of Numbers (prices)
- **Source:** Calculated from Yahoo historical data
- **Purpose:** Daily 20-day SMA values
- **Example:** `[167.80, 168.10, 168.45, 168.90, 169.20, 169.55]`

### Hit_SMA50
- **Type:** Array of Numbers (prices)
- **Source:** Calculated from Yahoo historical data
- **Purpose:** Daily 50-day SMA values
- **Example:** `[165.20, 165.35, 165.50, 165.68, 165.85, 166.02]`

### Hit_EMA9
- **Type:** Array of Numbers (prices)
- **Source:** Calculated from Yahoo historical data
- **Purpose:** Daily 9-day EMA values
- **Example:** `[168.90, 169.50, 170.20, 170.80, 171.20, 171.50]`

### Hit_EMA21
- **Type:** Array of Numbers (prices)
- **Source:** Calculated from Yahoo historical data
- **Purpose:** Daily 21-day EMA values
- **Example:** `[167.50, 167.85, 168.22, 168.60, 168.95, 169.28]`

### Hit_VWAP
- **Type:** Array of Numbers (prices)
- **Source:** Calculated from Yahoo historical data
- **Purpose:** Daily VWAP values
- **Example:** `[168.25, 169.10, 169.85, 170.20, 170.45, 170.60]`

### Hit_RVOL
- **Type:** Array of Numbers (ratios)
- **Source:** Calculated from Yahoo historical data
- **Purpose:** Daily relative volume
- **Example:** `[1.45, 1.62, 1.88, 1.35, 1.15, 1.08]`

### Hit_ATR
- **Type:** Array of Numbers (prices)
- **Source:** Calculated from Yahoo historical data
- **Purpose:** Daily 14-period ATR values
- **Example:** `[3.25, 3.42, 3.58, 3.48, 3.35, 3.28]`
- **Storage:** 4-decimal precision

### Hit_PriceVsSMA20
- **Type:** Array of Numbers (percentages)
- **Source:** Calculated
- **Purpose:** Daily price vs SMA20 percentage
- **Calculation:** `(dayPrice - SMA20) / SMA20 * 100`
- **Example:** `[0.42, 1.28, 2.59, 1.54, 2.37, 2.70]`
- **Note:** No % sign in storage

### Hit_PriceVsVWAP
- **Type:** Array of Numbers (percentages)
- **Source:** Calculated
- **Purpose:** Daily price vs VWAP percentage
- **Calculation:** `(dayPrice - VWAP) / VWAP * 100`
- **Example:** `[0.15, 0.67, 1.74, 0.77, 1.64, 2.05]`
- **Note:** No % sign in storage

---

## OHLC Data

### OHLC_Volume
- **Type:** Array of Objects
- **Source:** Yahoo Finance historical data
- **Purpose:** Complete daily OHLC and volume data
- **Structure:** Each array element is an object:
  ```json
  {
    "o": "168.50",   // Open price
    "h": "172.80",   // High price
    "l": "167.20",   // Low price
    "c": "171.50",   // Close price
    "v": 45200000,   // Volume
    "src": "BACKFILL" // Data source
  }
  ```
- **Example:**
  ```json
  [
    {"o":"168.50","h":"172.80","l":"167.20","c":"171.50","v":45200000,"src":"BACKFILL"},
    {"o":"171.60","h":"174.20","l":"170.80","c":"173.90","v":38500000,"src":"BACKFILL"},
    ...
  ]
  ```
- **Array Length:** 6 elements (Day 0-5)
- **Source Values:**
  - `BACKFILL`: Historical backfill
  - `ACTIVE`: Active position tracking
  - `YAHOO`: Direct Yahoo API
- **Note:** Primary source for Max_Favorable and Min_Unfavorable calculations

---

## Risk/Reward Metrics

### Risk_Reward
- **Type:** Number (ratio)
- **Source:** Calculated from Max_Favorable and Min_Unfavorable arrays
- **Purpose:** Risk/reward ratio for the position
- **Calculation:** `max(Max_Favorable) / max(Min_Unfavorable)`
- **Example:** `2.35` (reward is 2.35x the risk)
- **Interpretation:**
  - < 1.0: Risk exceeds reward
  - 1.0-2.0: Moderate risk/reward
  - 2.0-3.0: Good risk/reward
  - > 3.0: Excellent risk/reward

### maxProfit
- **Type:** Number (decimal or percentage)
- **Source:** API (EarningsWhispers)
- **Purpose:** Maximum theoretical profit for the strategy
- **Strategies:** Bull Spreads, Bear Spreads, Covered Calls
- **Example:** `5.00` (for spreads) or `25%` (for covered calls)

### maxLoss
- **Type:** Number (decimal)
- **Source:** API (EarningsWhispers)
- **Purpose:** Maximum theoretical loss for the strategy
- **Strategies:** Bull Spreads, Bear Spreads
- **Example:** `2.50`

### maxReturn
- **Type:** Number (percentage)
- **Source:** API (EarningsWhispers)
- **Purpose:** Maximum return percentage
- **Strategies:** Bull Spreads, Bear Spreads
- **Example:** `65.5%`

### maxRisk
- **Type:** Number (percentage)
- **Source:** API (EarningsWhispers)
- **Purpose:** Maximum risk percentage
- **Strategies:** Bull Spreads, Bear Spreads
- **Example:** `34.5%`

---

## Result Columns

### Hit_Date
- **Type:** String or Number
- **Source:** Calculated from Strike_Hit array
- **Purpose:** Day number when strike was first hit
- **Possible Values:** `0`, `1`, `2`, `3`, `4`, `5`, or empty
- **Example:** `2` (strike first hit on Day 2)
- **Note:** Derived from first positive value in Strike_Hit array

### Exp_Result
- **Type:** Number (price)
- **Source:** Price at expiration
- **Purpose:** Final stock price at option expiration
- **Example:** `174.50`
- **Note:** Only populated for expired positions

### Success_Score
- **Type:** Number (0-100+)
- **Source:** Calculated formula
- **Purpose:** Composite success score
- **Calculation Components:**
  - Hit score (0-60): Based on Ever_Hit_Strike
  - Time score (0-30): Based on Days_To_Exp
  - Volume score (0-10): Based on RVOL
  - Consistency score (0-20): Based on Total_Hit_Days
- **Example:** `78.5`
- **Interpretation:**
  - ≥ 70: HIGH CONFIDENCE
  - 50-69: MODERATE
  - 30-49: LOW CONFIDENCE
  - < 30: POOR PERFORMANCE

### Days_To_Exp
- **Type:** Number (integer)
- **Source:** Calculated
- **Purpose:** Days until option expiration
- **Calculation:** `expDate - Run Date` (at entry), or `expDate - TODAY()` (current)
- **Example:** `15`

### Historical_High
- **Type:** Number (price)
- **Source:** GoogleFinance formula (continuously updated)
- **Purpose:** Highest price reached since entry
- **Example:** `175.80`
- **Note:** Never resets, captures lifetime high

### Historical_Low
- **Type:** Number (price)
- **Source:** GoogleFinance formula (continuously updated)
- **Purpose:** Lowest price reached since entry
- **Example:** `166.20`
- **Note:** Never resets, captures lifetime low

### Ever_Hit_Strike
- **Type:** String
- **Source:** GoogleFinance formula
- **Purpose:** Whether strike was ever reached
- **Possible Values:**
  - `TRUE`: Strike hit (bullish/bearish)
  - `FALSE`: Strike never hit
  - `FAVORABLE`: Favorable for short positions
  - `UNFAVORABLE`: Unfavorable for short positions
- **Example:** `TRUE`

### First_Hit_Date
- **Type:** Date (YYYY-MM-DD)
- **Source:** GoogleFinance formula
- **Purpose:** First date strike was hit
- **Example:** `2024-03-17`
- **Note:** Permanent, never changes once set

### Last_Update
- **Type:** Timestamp (YYYY-MM-DD HH:MM:SS)
- **Source:** GoogleFinance formula
- **Purpose:** Last time formulas recalculated
- **Example:** `2024-03-20 16:30:45`

### Total_Hit_Days
- **Type:** Number (integer)
- **Source:** GoogleFinance formula
- **Purpose:** Count of days strike was favorable
- **Example:** `4`
- **Note:** Increments each day strike is hit

---

## GoogleFinance Columns

These columns use `=GOOGLEFINANCE()` formulas for real-time data.

### GF_Name
- **Type:** String
- **Source:** `=GOOGLEFINANCE(ticker, "name")`
- **Purpose:** Company name from Google Finance
- **Example:** `Apple Inc.`

### GF_Price
- **Type:** Number (price)
- **Source:** `=GOOGLEFINANCE(ticker, "price")`
- **Purpose:** Current stock price
- **Example:** `174.25`

### GF_ChangePct
- **Type:** Number (percentage)
- **Source:** `=GOOGLEFINANCE(ticker, "changepct")`
- **Purpose:** Percent change for the day
- **Example:** `1.25`

### GF_High
- **Type:** Number (price)
- **Source:** `=GOOGLEFINANCE(ticker, "high")`
- **Purpose:** Today's high price
- **Example:** `175.50`

### GF_Low
- **Type:** Number (price)
- **Source:** `=GOOGLEFINANCE(ticker, "low")`
- **Purpose:** Today's low price
- **Example:** `173.20`

### GF_High52
- **Type:** Number (price)
- **Source:** `=GOOGLEFINANCE(ticker, "high52")`
- **Purpose:** 52-week high price
- **Example:** `182.50`

### GF_Low52
- **Type:** Number (price)
- **Source:** `=GOOGLEFINANCE(ticker, "low52")`
- **Purpose:** 52-week low price
- **Example:** `145.80`

### GF_Volume
- **Type:** Number (shares)
- **Source:** `=GOOGLEFINANCE(ticker, "volume")`
- **Purpose:** Today's volume
- **Example:** `42500000`

### GF_AvgVol10
- **Type:** Number (shares)
- **Source:** Calculated from `GOOGLEFINANCE(ticker, "volume", TODAY()-30, TODAY())`
- **Purpose:** 10-day average volume
- **Calculation:** Average of last 10 days of volume
- **Example:** `38200000`

### GF_MktCap
- **Type:** Number (dollars)
- **Source:** `=GOOGLEFINANCE(ticker, "marketcap")`
- **Purpose:** Market capitalization
- **Example:** `2850000000000` (2.85 trillion)

### GF_PE
- **Type:** Number (ratio)
- **Source:** `=GOOGLEFINANCE(ticker, "pe")`
- **Purpose:** Price-to-Earnings ratio
- **Example:** `28.5`

### GF_Beta
- **Type:** Number (coefficient)
- **Source:** `=GOOGLEFINANCE(ticker, "beta")`
- **Purpose:** Beta coefficient (market correlation)
- **Example:** `1.25`

### HV_30D
- **Type:** Number (percentage)
- **Source:** Calculated from 30 days of GOOGLEFINANCE price data
- **Purpose:** 30-day historical volatility (annualized)
- **Calculation:** `STDEV(daily_returns) * SQRT(252) * 100`
- **Example:** `24.5%`

### RVOL_10
- **Type:** Number (ratio)
- **Source:** Calculated from GOOGLEFINANCE volume data
- **Purpose:** Relative volume (10-day)
- **Calculation:** `current_volume / 10day_avg_volume`
- **Example:** `1.35`

### Ret_5D
- **Type:** Number (percentage)
- **Source:** Calculated from GOOGLEFINANCE price data
- **Purpose:** 5-day return
- **Calculation:** `(today_price / price_5days_ago - 1) * 100`
- **Example:** `3.2%`

### Ret_20D
- **Type:** Number (percentage)
- **Source:** Calculated from GOOGLEFINANCE price data
- **Purpose:** 20-day return
- **Calculation:** `(today_price / price_20days_ago - 1) * 100`
- **Example:** `8.5%`

### GapPct
- **Type:** Number (percentage)
- **Source:** Calculated from GOOGLEFINANCE data
- **Purpose:** Today's gap percentage
- **Calculation:** `(price - priceopen) / priceopen * 100`
- **Example:** `0.85%`

---

## Metadata & Timestamps

### expDate
- **Type:** Date (YYYY-MM-DD)
- **Source:** API (EarningsWhispers)
- **Purpose:** Option expiration date
- **Example:** `2024-03-29`

### optionDate
- **Type:** Date (YYYY-MM-DD)
- **Source:** API (EarningsWhispers)
- **Purpose:** Date option data was generated
- **Example:** `2024-03-15`
- **Strategies:** Long Calls, Long Puts

### openInterest
- **Type:** Number (contracts)
- **Source:** API (EarningsWhispers)
- **Purpose:** Open interest for the option
- **Example:** `8500`
- **Strategies:** Long Calls, Long Puts

### volume
- **Type:** Number (contracts)
- **Source:** API (EarningsWhispers)
- **Purpose:** Option volume
- **Example:** `1250`
- **Strategies:** Long Calls, Long Puts

### avgVolume
- **Type:** Number (shares)
- **Source:** API (EarningsWhispers)
- **Purpose:** Average stock volume
- **Example:** `38500000`
- **Strategies:** Long Calls, Long Puts

### score
- **Type:** Number
- **Source:** API (EarningsWhispers)
- **Purpose:** Proprietary EW rating score
- **Example:** `85`
- **Strategies:** Long Calls, Long Puts

---

## Strategy-Specific Columns

### Bull Spreads / Bear Spreads

#### shortBid
- **Type:** Number (decimal)
- **Source:** API (EarningsWhispers)
- **Purpose:** Bid price for short strike option
- **Example:** `2.15`

#### longAsk
- **Type:** Number (decimal)
- **Source:** API (EarningsWhispers)
- **Purpose:** Ask price for long strike option
- **Example:** `4.80`

#### totRatings
- **Type:** Number (integer)
- **Source:** API (EarningsWhispers)
- **Purpose:** Total analyst ratings
- **Example:** `25`

#### netRatings
- **Type:** Number (integer)
- **Source:** API (EarningsWhispers)
- **Purpose:** Net analyst ratings (buy - sell)
- **Example:** `15`

#### ewRating
- **Type:** String or Number
- **Source:** API (EarningsWhispers)
- **Purpose:** EarningsWhispers proprietary rating
- **Example:** `A+` or `95`

### Covered Calls

#### cushion
- **Type:** Number (percentage)
- **Source:** API (EarningsWhispers)
- **Purpose:** Cushion below current price to strike
- **Calculation:** `(currentPrice - strike) / currentPrice * 100`
- **Example:** `5.5%`

#### upTarget
- **Type:** Number (price)
- **Source:** API (EarningsWhispers)
- **Purpose:** Upside target price
- **Example:** `180.00`

#### callAway
- **Type:** Number (price)
- **Source:** API (EarningsWhispers)
- **Purpose:** Price at which shares are called away
- **Example:** `175.00`

#### downTarget
- **Type:** Number (price)
- **Source:** API (EarningsWhispers)
- **Purpose:** Downside target price
- **Example:** `165.00`

#### callAwayReturn
- **Type:** Number (percentage)
- **Source:** API (EarningsWhispers)
- **Purpose:** Return if shares called away
- **Example:** `8.5%`

#### exDivDate
- **Type:** Date (YYYY-MM-DD)
- **Source:** API (EarningsWhispers)
- **Purpose:** Ex-dividend date
- **Example:** `2024-03-25`

#### payout
- **Type:** Number (decimal)
- **Source:** API (EarningsWhispers)
- **Purpose:** Dividend payout amount
- **Example:** `0.95`

---

## Data Flow Diagram

```
EarningsWhispers API
         ↓
Google Apps Script (04_Code.js)
         ↓
Google Sheets
    ↓           ↓
Yahoo API   GoogleFinance
    ↓           ↓
Backfill    Real-time Updates
    ↓           ↓
CSV Export
    ↓
Python Analytics (data_loader.py)
    ↓
Reports & Dashboards
```

---

## Array Index Reference

All arrays follow this indexing:

| Index | Day | Description |
|-------|-----|-------------|
| `[0]` | Day 0 | Entry day (Run Date) |
| `[1]` | Day 1 | 1 trading day after entry |
| `[2]` | Day 2 | 2 trading days after entry |
| `[3]` | Day 3 | 3 trading days after entry |
| `[4]` | Day 4 | 4 trading days after entry |
| `[5]` | Day 5 | 5 trading days after entry |

**Note:** Null values indicate no data for that day (position not yet reached that day or data unavailable)

---

## Calculation Examples

### Example 1: Bullish Strategy (Long Call)

```
Ticker: AAPL
Strike: 170.00
Run Date: 2024-03-15
Strategy: Long Calls

OHLC Data (Day 0-2):
Day 0: O:168.50, H:172.80, L:167.20, C:171.50
Day 1: O:171.60, H:174.20, L:170.80, C:173.90
Day 2: O:173.95, H:175.50, L:172.50, C:174.80

Strike_Hit Calculation:
Day 0: (172.80 - 170.00) / 170.00 = 0.016471 (1.65% above strike)
Day 1: (174.20 - 170.00) / 170.00 = 0.024706 (2.47% above strike)
Day 2: (175.50 - 170.00) / 170.00 = 0.032353 (3.24% above strike)

Strike_Hit Array: [0.016471, 0.024706, 0.032353, null, null, null]

Max_Favorable (same as Strike_Hit for bullish):
[0.016471, 0.024706, 0.032353, null, null, null]

Min_Unfavorable (using lows):
Day 0: (170.00 - 167.20) / 170.00 = 0.016471
Day 1: (170.00 - 170.80) / 170.00 = -0.004706 (low is above strike)
Day 2: (170.00 - 172.50) / 170.00 = -0.014706 (low is above strike)

Min_Unfavorable Array: [0.016471, -0.004706, -0.014706, null, null, null]
```

### Example 2: Bearish Strategy (Long Put)

```
Ticker: TSLA
Strike: 180.00
Run Date: 2024-03-15
Strategy: Long Puts

OHLC Data (Day 0-2):
Day 0: O:182.00, H:183.50, L:179.20, C:180.50
Day 1: O:180.40, H:181.80, L:177.50, C:178.20
Day 2: O:178.10, H:179.80, L:175.30, C:176.50

Strike_Hit Calculation (bearish):
Day 0: (180.00 - 179.20) / 180.00 = 0.004444 (0.44% below strike)
Day 1: (180.00 - 177.50) / 180.00 = 0.013889 (1.39% below strike)
Day 2: (180.00 - 175.30) / 180.00 = 0.026111 (2.61% below strike)

Strike_Hit Array: [0.004444, 0.013889, 0.026111, null, null, null]

Max_Favorable (using lows for bearish):
[0.004444, 0.013889, 0.026111, null, null, null]

Min_Unfavorable (using highs for bearish):
Day 0: (183.50 - 180.00) / 180.00 = 0.019444
Day 1: (181.80 - 180.00) / 180.00 = 0.010000
Day 2: (179.80 - 180.00) / 180.00 = -0.001111 (high is below strike)

Min_Unfavorable Array: [0.019444, 0.010000, -0.001111, null, null, null]
```

---

## Python Analytics Integration

The Python `data_loader.py` module processes these columns:

### Parsing Operations

1. **JSON Arrays**: Parses Strike_Hit, Max_Favorable, Min_Unfavorable, OHLC_Volume, and all Hit_* indicator arrays
2. **Daily Profits**: Extracts `Day0_Profit_Pct` through `Day5_Profit_Pct` from Strike_Hit array
3. **Peak Analysis**: Calculates `Peak_Profit_Pct` and `Peak_Profit_Day`
4. **Time to Hit**: Determines `Time_To_Hit_Days` from Strike_Hit array
5. **Strategy Classification**: Categorizes as Bullish/Bearish/Neutral

### Derived Metrics

From `config.py` TRACKING_COLUMNS:

```python
'entry': ['Run Date', 'Strategy', 'company', 'ticker', 'strike',
          'expDate', 'nextEPSDate', 'releaseTime']

'daily_checks': ['Day0_Check', 'Day1_Check', 'Day2_Check',
                 'Day3_Check', 'Day4_Check', 'Day5_Check']

'arrays': ['Strike_Hit', 'Max_Favorable', 'Min_Unfavorable', 'OHLC_Volume']

'indicators': ['Hit_RSI', 'Hit_SMA20', 'Hit_SMA50', 'Hit_EMA9', 'Hit_EMA21',
               'Hit_VWAP', 'Hit_RVOL', 'Hit_ATR',
               'Hit_PriceVsSMA20', 'Hit_PriceVsVWAP']

'metrics': ['Risk_Reward', 'Days_To_Exp', 'Success_Score',
            'avgEPSMove', 'epsImpact']
```

---

## Common Data Issues & Solutions

### Issue 1: Empty Arrays
- **Symptom:** `[]` or `null` in array columns
- **Cause:** Position not yet backfilled or data unavailable
- **Solution:** Run backfill for expired positions, wait for active tracking for current positions

### Issue 2: Partial Arrays
- **Symptom:** `[val, val, null, null, null, null]`
- **Cause:** Position hasn't reached later days yet
- **Solution:** Normal for active positions, will fill as days progress

### Issue 3: Mismatched Day Checks
- **Symptom:** Day2_Check exists but no Day2 data in arrays
- **Cause:** Different population methods (formulas vs. scripts)
- **Solution:** Ensure both backfill and active tracking are running

### Issue 4: NO_DATA in Arrays
- **Symptom:** `["NO_DATA", "NO_DATA", ...]` in OHLC
- **Cause:** Yahoo API returned no historical data for that period
- **Solution:** Check ticker symbol, verify trading dates (no weekends/holidays)

---

## Version History

- **v2.0** (2025-10-10): Complete array-based tracking system with OHLC integration
- **v1.5** (2024-12): Added technical indicator arrays
- **v1.0** (2024-11): Initial GoogleFinance formula implementation

---

## References

- **Google Apps Script Files:**
  - `04_Code.js`: Main data fetching and sheet management
  - `08_TrackingUpdates.js`: Tracking column updates
  - `13_ArrayBuilders.js`: Array construction functions
  - `15_AddTrackingColumns.js`: Column definitions
  - `05_TechnicalIndicators.js`: Indicator calculations
  - `19_OHLCUtilities.js`: OHLC data handling
  - `09_HistoricalBackfill.js`: Backfill operations
  - `11_ActivePositionTracking.js`: Real-time tracking

- **Python Files:**
  - `config.py`: Column mappings and configuration
  - `modules/data_loader.py`: CSV parsing and processing

- **Data Sources:**
  - EarningsWhispers API: Trade recommendations, earnings data
  - Yahoo Finance API: Historical OHLC and technical data
  - GoogleFinance: Real-time quotes and metrics

---

## Contact & Support

For questions about this data dictionary or the analytics system, refer to the project README or codebase documentation.
