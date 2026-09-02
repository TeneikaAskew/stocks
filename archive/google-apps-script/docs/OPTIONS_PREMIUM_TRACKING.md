# Options Premium Tracking - Using Real Yahoo Finance Data

## Overview

This script fetches **ACTUAL options premium data** from Yahoo Finance (not calculated intrinsic value!).

It provides complete OHLC (Open, High, Low, Close) values for options premiums to analyze profitability.

## What You Get

For each position, **TODAY's data**:

| Data Point | Description | Use Case |
|------------|-------------|----------|
| **Premium** | Current/closing option price | Your current position value |
| **Day_High** | Highest premium today | Best exit opportunity |
| **Day_Low** | Lowest premium today | Worst case scenario |
| **Day_Open** | Opening premium | Morning entry price |
| **Bid** | Current bid price | Realistic sell price |
| **Ask** | Current ask price | Realistic buy price |
| **Volume** | Contracts traded | Liquidity indicator |
| **Open Interest** | Total open contracts | Market interest |

## Profitability Analysis

If you have **Entry_Premium** in your sheet, it calculates:

- **PnL**: Current profit/loss vs entry
- **Max_Profit**: Best possible P/L using Day_High
- **Max_Loss**: Worst case P/L using Day_Low
- **Was_Profitable**: YES if Day_High > Entry_Premium

## Setup

### Step 1: Add Entry_Premium Column

Add a column called **Entry_Premium** to your "Long Calls" sheet.

This should contain the **premium you actually paid** when you bought the option.

Example:
- You bought PFE $24 Call for $2.50
- Entry_Premium = 2.50 (not $250, just the per-share premium)

### Step 2: Run Daily at 5 PM

```javascript
EW_updateOptionsPremiums()
```

This fetches today's OHLC for all active positions.

### Step 3: View Results

Check the "Long Calls Options" sheet for detailed output.

## Usage

### Update All Positions

```javascript
EW_updateOptionsPremiums()
```

Runs for all non-expired positions in "Long Calls" sheet.

### Update Selected Only

1. Select rows in "Long Calls" sheet
2. Run:

```javascript
EW_updateOptionsPremiumsSelected()
```

### Test Single Position

1. Click on any row in "Long Calls" sheet
2. Run:

```javascript
EW_testOptionPremiumFetch()
```

Shows:
- Option symbol built (e.g., ROKU251107C00060000)
- Premium, OHLC, Bid/Ask
- Volume and Open Interest

## Example Output

### Long Calls Options Sheet

| Date | Ticker | Strike | Type | Premium | Day_High | Day_Low | Entry_Premium | PnL | Max_Profit | Max_Loss | Was_Profitable |
|------|--------|--------|------|---------|----------|---------|---------------|-----|------------|----------|----------------|
| 2025-11-06 | PFE | 24 | C | $48.65 | $52.30 | $45.10 | $50.00 | -$135 | +$230 | -$490 | YES |
| 2025-11-06 | ROKU | 60 | C | $43.20 | $46.50 | $40.10 | $42.00 | +$120 | +$450 | -$190 | YES |

**Interpretation (PFE example):**

You paid $50.00 per share ($5,000 per contract) for the PFE $24 call.

**Today's movement:**
- Opened at $48.65 (down from your entry)
- Hit a high of $52.30 ← **You could have profited +$230!**
- Hit a low of $45.10 ← Worst case -$490
- Closed at $48.65 (currently down -$135)

**Was_Profitable: YES** means even though you're currently down, there WAS an opportunity to profit when it hit $52.30.

This helps you:
- Understand if you missed an exit
- Set better profit targets
- Analyze intraday volatility
- Plan future exits

## Option Symbol Format

Yahoo Finance uses this format: `TICKER + YYMMDD + C/P + 8-digit strike`

**Examples:**

| Ticker | Exp Date | Type | Strike | Symbol |
|--------|----------|------|--------|--------|
| ROKU | 2025-11-07 | Call | $60.00 | ROKU251107C00060000 |
| PFE | 2025-11-07 | Call | $24.00 | PFE251107C00024000 |
| AAPL | 2025-12-20 | Put | $150.50 | AAPL251220P00150500 |

**Breakdown:**
- **ROKU** - Ticker
- **25** - Year (2025)
- **11** - Month (November)
- **07** - Day (7th)
- **C** - Call (P = Put)
- **00060000** - Strike $60.00 (multiply by 1000, pad to 8 digits)

The script builds this automatically from your sheet data.

## Automation

### Daily Trigger (Recommended)

1. Open Apps Script editor
2. Click **Triggers** (clock icon)
3. Add trigger:
   - Function: `EW_updateOptionsPremiums`
   - Event: Time-driven
   - Type: Day timer
   - Time: **5:00 PM - 6:00 PM**

**Why 5 PM?**
- Market closes at 4:00 PM
- Gives Yahoo Finance time to finalize data
- Captures complete day's OHLC in one call

### Manual On-Demand

Run anytime to get current data:

```javascript
EW_updateOptionsPremiums()
```

Works during market hours too (gets current premium + partial day OHLC).

## Understanding the Data

### Premium vs Entry

- **Entry_Premium**: What you paid (your cost)
- **Premium**: Current/closing value
- **PnL**: Difference × 100 shares per contract

Example:
```
Entry_Premium: $2.50 per share
Premium: $2.35 per share
PnL = ($2.35 - $2.50) × 100 = -$15.00 per contract
```

### Max_Profit Analysis

Shows the **best possible exit** using today's high:

```
Entry_Premium: $2.50
Day_High: $2.80
Max_Profit = ($2.80 - $2.50) × 100 = +$30.00

This means: If you had sold at the high,
you would have made $30 profit.
```

### Was_Profitable Flag

- **YES**: Day_High > Entry_Premium (profit opportunity existed)
- **NO**: Day_High < Entry_Premium (no profit opportunity)

Even if currently losing, "YES" means you could have profited.

## Comparison with Other Scripts

This project now has **THREE** options tracking scripts:

### 1. Premium Tracking (THIS SCRIPT) ⭐ BEST

**File:** `27_OptionsPremiumTracking.js`

**Uses:** Actual options premium data from Yahoo

**Output:** Daily OHLC for options premiums

**Profitability:** YES - compares actual premiums

**Best for:** Real P/L tracking with actual market prices

### 2. Intraday Tracking

**File:** `26_OptionsIntradayTracking.js`

**Uses:** Stock 1-minute data → calculates intrinsic value

**Output:** Minute-by-minute intrinsic values for today

**Profitability:** Approximation only (intrinsic value)

**Best for:** Intraday stock movement analysis

### 3. Historical Backfill

**File:** `26_OptionsHistoricalBackfill.js`

**Uses:** Daily stock prices → calculates intrinsic value

**Output:** Multi-day summary from entry to expiration

**Profitability:** Approximation only (intrinsic value)

**Best for:** Long-term position tracking

## Recommendation

**Use Premium Tracking (THIS SCRIPT) for:**
- ✅ Accurate profit/loss analysis
- ✅ Real market prices (not calculated)
- ✅ Daily OHLC to find best exits
- ✅ Bid/ask spreads and liquidity
- ✅ Actual premiums you can trade at

**Schedule it daily at 5 PM for best results.**

## Limitations

### 1. Daily Data Only

Yahoo provides daily OHLC for options, not 1-minute bars.

- You get: Open, High, Low, Close for the day
- You don't get: Exact time when high/low occurred
- This is still very useful for profitability analysis

### 2. Delayed Quotes

Yahoo Finance provides 15-20 minute delayed quotes for options.

- For end-of-day tracking (5 PM), this is fine
- For real-time trading, use your broker's platform

### 3. Option Symbol Format

Must exactly match Yahoo's format or API returns no data.

- Script auto-builds the symbol
- Verify with test function if issues

### 4. No Greeks

This API doesn't provide Greeks (delta, gamma, theta, vega).

For Greeks, you'd need:
- Paid API (e.g., TDAmeritrade, IBKR)
- Or calculate using Black-Scholes model

## Troubleshooting

### "No data returned"

**Causes:**
- Option symbol incorrect
- Option doesn't trade on that expiration
- Ticker/strike/date mismatch

**Solutions:**
1. Run `EW_testOptionPremiumFetch()` on the row
2. Check execution log for the built symbol
3. Verify expiration date is correct
4. Try manually building symbol and testing in browser:
   ```
   https://query1.finance.yahoo.com/v7/finance/quote?symbols=ROKU251107C00060000
   ```

### Wrong Strike Format

Strike must be padded correctly:

- $60.00 → 00060000 ✅
- $125.50 → 00125500 ✅
- $9.50 → 00009500 ✅

Script handles this automatically.

### Entry_Premium Column Missing

Add it manually or run:

```javascript
// Add Entry_Premium column
const sheet = SpreadsheetApp.getActive().getSheetByName('Long Calls');
const lastCol = sheet.getLastColumn();
sheet.insertColumnAfter(lastCol);
sheet.getRange(1, lastCol + 1).setValue('Entry_Premium').setFontWeight('bold');
```

### Expired Options

Script automatically skips expired positions.

If you want to track expired options, remove this check in `EW_readOptionsPositions()`:

```javascript
// Comment out this line:
// if (expDate < today) continue;
```

## Advanced Usage

### Export for Analysis

Download the "Long Calls Options" sheet as CSV:

1. File → Download → CSV
2. Import into Python/R/Excel for analysis
3. Analyze best exit times, volatility patterns, etc.

### Extend to Other Strategies

To track Long Puts:

1. Duplicate script
2. Change source sheet: `'Long Puts'`
3. Change option type: `optionType: 'P'`
4. Change output sheet: `'Long Puts Options'`

### Historical Premium Data

Unfortunately, Yahoo doesn't provide historical options OHLC via free API.

For historical premium analysis, you'd need:
- Paid data provider (e.g., CBOE DataShop, IVolatility)
- Scrape Yahoo Finance web pages (against ToS)
- Use brokerage historical data export

## Real Example

Here's a real response from Yahoo Finance for ROKU:

```json
{
  "regularMarketPrice": 48.65,
  "regularMarketDayHigh": 48.65,
  "regularMarketDayLow": 48.65,
  "regularMarketOpen": 48.65,
  "bid": 43.25,
  "ask": 46.90,
  "strike": 60.0,
  "regularMarketVolume": 1,
  "openInterest": 2,
  "expireDate": 1762473600,
  "underlyingSymbol": "ROKU"
}
```

**This is ACTUAL market data** - the real premium you could buy/sell at!

Much better than calculated intrinsic value.

## Summary

This script provides **real options premium data** with:

✅ Actual market prices (not calculated)
✅ Daily OHLC to analyze best exits
✅ Profitability analysis (Was there profit opportunity?)
✅ Bid/ask spreads for liquidity
✅ Volume and open interest
✅ Works with any ticker/strike/expiration

**Run daily at 5 PM** for best results.

**Use `EW_testOptionPremiumFetch()`** to verify it works for your positions.

This is the most accurate way to track options P/L using free APIs! 🎯
