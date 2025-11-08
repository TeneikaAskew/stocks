# Options Tracking Guide

## Overview

Two complementary scripts for tracking options P/L:

1. **Intraday Tracking** (`26_OptionsIntradayTracking.js`)
   - Captures TODAY's 1-minute data
   - Shows real-time P/L throughout the trading day
   - Writes to "{Strategy} Options" sheet (e.g., "Long Calls Options")

2. **Historical Backfill** (`26_OptionsHistoricalBackfill.js`)
   - Processes historical data across multiple days
   - Calculates daily P/L from entry date to today
   - Updates columns in the original sheet

## Quick Reference

| Need | Function | Output |
|------|----------|--------|
| Today's minute-by-minute P/L | `EW_updateOptionsIntraday()` | Long Calls Options sheet |
| Multi-day historical P/L | `EW_backfillOptionsHistorical()` | Long Calls sheet (adds columns) |
| Selected rows only (intraday) | `EW_updateOptionsIntradaySelected()` | Long Calls Options sheet |
| Selected rows only (backfill) | `EW_backfillOptionsSelected()` | Long Calls sheet |

---

# Part 1: Intraday Tracking

## What It Does

Fetches today's 1-minute stock price data and calculates how your options have moved throughout the day.

### Example Output (Long Calls Options sheet)

| Ticker | Strike | ExpDate | Timestamp | Time | Stock_Price | Intrinsic_Value | PnL_From_Open | Percent_Change | Session |
|--------|--------|---------|-----------|------|-------------|-----------------|---------------|----------------|---------|
| PFE | 24 | 2025-11-07 | 2025-11-06 09:30 | 09:30:00 | $25.50 | $150.00 | $0.00 | 0.00% | OPEN |
| PFE | 24 | 2025-11-07 | 2025-11-06 09:31 | 09:31:00 | $25.60 | $160.00 | $10.00 | 6.67% | OPEN |
| PFE | 24 | 2025-11-07 | 2025-11-06 09:32 | 09:32:00 | $25.45 | $145.00 | -$5.00 | -3.33% | OPEN |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

**Each row** = 1-minute bar showing:
- Stock price at that minute
- Intrinsic value: `max(0, stock_price - strike) × 100`
- P/L from market open
- Percent change from open
- Market session (OPEN, MORNING, MIDDAY, AFTERNOON, POWER_HOUR)

## Usage

### Update All Active Positions

Runs for all non-expired positions in "Long Calls" sheet:

```javascript
EW_updateOptionsIntraday()
```

**What it does:**
1. Reads all active positions from "Long Calls" sheet
2. Fetches today's 1-minute data (9:30 AM to now)
3. Calculates intrinsic value and P/L for each minute
4. Writes all 1-minute bars to "Long Calls Options" sheet
5. Clears previous data from today before writing new data

**Best for:**
- Daily scheduled runs (see Automation below)
- Viewing all positions at once
- End-of-day snapshots

### Update Selected Positions Only

Select specific rows in "Long Calls" sheet, then run:

```javascript
EW_updateOptionsIntradaySelected()
```

**Best for:**
- Quick updates on specific positions
- Testing with one or two positions
- High-frequency updates of active trades

### Clear Data

Reset the output sheet:

```javascript
EW_clearAllIntradayData()
```

## Automation - Schedule Intraday Updates

**Best Practice: Run ONCE per day after market close**

The script fetches the ENTIRE day's 1-minute data in one API call (like the Python script does). You don't need to run it multiple times during the day.

### Recommended: Once Daily After Close

1. Open Apps Script editor
2. Click **Triggers** (clock icon)
3. Add trigger:
   - Function: `EW_updateOptionsIntraday`
   - Event: Time-driven
   - Type: Day timer
   - Time: **5:00 PM - 6:00 PM** (after market close)

**Why 5 PM?**
- Market closes at 4:00 PM ET
- Gives 1 hour for Yahoo Finance to finalize data
- Captures complete day's 1-minute bars in one call
- Similar to Python script's 4:05 PM schedule

### Alternative: Manual On-Demand

Run manually whenever you want to capture today's data:

```javascript
EW_updateOptionsIntraday()
```

**When to run manually:**
- During market hours to see current P/L
- After market close for complete day
- Before analyzing specific trades

### Not Recommended: Multiple Daily Runs

❌ Don't run every 30 minutes or hourly
- Each run fetches the entire day's data anyway
- Wastes API quota
- No benefit over single end-of-day run
- Yahoo Finance returns same 1-minute bars whether you call at 10 AM or 4 PM

## Understanding Intraday Data

### Intrinsic Value Calculation

**Call Options:**
```
Stock Price: $25.50
Strike: $24.00
Intrinsic Value = max(0, $25.50 - $24.00) × 100 = $150.00
```

**Put Options:**
```
Stock Price: $25.50
Strike: $27.00
Intrinsic Value = max(0, $27.00 - $25.50) × 100 = $150.00
```

### P/L From Open

Shows how much the intrinsic value has changed since market open (9:30 AM):

```
9:30 AM: Stock = $25.50, Intrinsic = $150.00 (baseline)
10:00 AM: Stock = $26.25, Intrinsic = $225.00
PnL From Open = $225.00 - $150.00 = +$75.00 (50% gain)
```

### Market Sessions

The script classifies each minute into market sessions:

- **OPEN** (9:30-10:00 AM) - High volatility period
- **MORNING** (10:00 AM-12:00 PM) - Morning trading
- **MIDDAY** (12:00-2:00 PM) - Lunch period
- **AFTERNOON** (2:00-3:30 PM) - Afternoon session
- **POWER_HOUR** (3:30-4:00 PM) - Final 30 minutes
- **PRE_MARKET** (before 9:30 AM) - Pre-market if data available
- **AFTER_HOURS** (after 4:00 PM) - After-hours if data available

Use this to analyze which sessions are most profitable for your trades.

---

# Part 2: Historical Backfill

## What It Does

Calculates daily P/L across multiple days from position entry to today (or expiration).

### Example Output (Columns added to Long Calls sheet)

| Ticker | Strike | RunDate | ExpDate | Entry_Intrinsic | Cumulative_PnL | Max_PnL | Min_PnL | Percent_Return | Daily_PnL_Array |
|--------|--------|---------|---------|----------------|----------------|---------|---------|----------------|-----------------|
| PFE | 24 | 2025-10-15 | 2025-11-07 | $150.00 | $125.00 | $200.00 | -$50.00 | 83.33% | [JSON array] |

**Columns:**
- `Entry_Intrinsic` - Intrinsic value at entry
- `Cumulative_PnL` - Current total P/L
- `Max_PnL` - Best P/L achieved
- `Min_PnL` - Worst P/L experienced
- `Percent_Return` - Percentage return
- `Daily_PnL_Array` - JSON with daily values

## Usage

### Setup (One-Time)

Add the necessary columns:

```javascript
EW_addOptionsPnLColumns()
```

This adds 7 columns to your "Long Calls" sheet.

### Backfill All Incomplete Positions

Process all rows that don't have P/L data yet:

```javascript
EW_backfillOptionsHistorical()
```

**Features:**
- Automatically skips rows that already have data
- Processes from entry date to today (or expiration if sooner)
- Uses daily closing prices
- Includes continuation support for large datasets

**Best for:**
- Initial setup
- Daily automated backfill
- After adding new positions

### Backfill Selected Rows

Select specific rows, then run:

```javascript
EW_backfillOptionsSelected()
```

**Best for:**
- Updating specific positions
- Re-calculating after corrections
- Testing on a few rows

### Test Single Position

Click on any row, then run:

```javascript
EW_testOptionsBackfill()
```

Shows detailed calculation in the log and a summary popup.

## Automation - Daily Backfill

To automatically update historical P/L daily:

1. Open Apps Script editor
2. Click **Triggers**
3. Add trigger:
   - Function: `EW_backfillOptionsHistorical`
   - Event: Time-driven
   - Type: Day timer
   - Time: 6 PM - 7 PM (after market close)

This ensures positions are updated with the latest closing prices every day.

## Understanding Daily P/L Array

The `Daily_PnL_Array` column contains detailed daily data in JSON format:

```json
[
  {
    "date": "2025-10-15",
    "price": "25.50",
    "intrinsic": "150.00",
    "dailyPnL": "0.00",
    "cumPnL": "0.00",
    "pctChange": "0.00"
  },
  {
    "date": "2025-10-16",
    "price": "26.25",
    "intrinsic": "225.00",
    "dailyPnL": "75.00",
    "cumPnL": "75.00",
    "pctChange": "50.00"
  }
]
```

**Fields:**
- `date` - Trading date
- `price` - Stock closing price
- `intrinsic` - Option intrinsic value
- `dailyPnL` - Change from previous day
- `cumPnL` - Total P/L from entry
- `pctChange` - Percent change from entry

---

# When to Use Which Script

## Use Intraday Tracking When:

- ✅ You want to see **minute-by-minute** movement TODAY
- ✅ You're day trading or scalping options
- ✅ You want to analyze optimal entry/exit times
- ✅ You want to track intraday volatility patterns
- ✅ You want a detailed record of today's price action

## Use Historical Backfill When:

- ✅ You want **multi-day** P/L from entry to today
- ✅ You're holding positions for days or weeks
- ✅ You want summary statistics (max/min P/L)
- ✅ You want to add P/L columns to your main tracking sheet
- ✅ You want daily P/L data, not minute-by-minute

## Use Both When:

- ✅ You want detailed intraday AND historical tracking
- ✅ You want minute-by-minute for today + daily summaries for history
- ✅ You're analyzing both short-term and long-term performance

**Example workflow:**
1. Run `EW_backfillOptionsHistorical()` daily at 6 PM (historical)
2. Run `EW_updateOptionsIntraday()` every 30 minutes during market hours (intraday)
3. View "Long Calls" sheet for multi-day summary
4. View "Long Calls Options" sheet for today's detailed movements

---

# Required Sheet Columns

## Long Calls Sheet (Source)

Must have:
- **ticker** - Stock symbol (e.g., "PFE")
- **strike** - Strike price (e.g., 24)
- **expDate** - Expiration date (e.g., "2025-11-07 0:00:00")

Optional:
- **runDate** - Entry date (used for historical backfill)

## Long Calls Options Sheet (Output)

Auto-created with these columns:
- Ticker, Strike, ExpDate
- Timestamp, Time
- Stock_Price, Intrinsic_Value
- PnL_From_Open, Cumulative_PnL
- Percent_Change, Volume, Session

---

# Important Limitations

## 1. Intrinsic Value vs. Actual Premium

Both scripts calculate **intrinsic value**, not actual options premium.

**Real options premium** = Intrinsic Value + Time Value + Volatility Value

**What this means:**
- Deep ITM options: Intrinsic value ≈ actual premium (good approximation)
- ATM options: Intrinsic value < actual premium (underestimated)
- OTM options: Intrinsic value = $0, but actual premium > $0 (not captured)

**Best use case:** Track ITM and ATM options where intrinsic is the primary component.

## 2. Historical Data Availability

Yahoo Finance provides:
- **1-minute data:** Last 7 days only
- **Daily data:** Years of history

**Impact:**
- Intraday script: Works for today and last ~7 days
- Historical backfill: Can go back years using daily data

## 3. Market Hours

1-minute data is typically only available during regular market hours (9:30 AM - 4:00 PM ET).

Extended hours data may be limited or unavailable.

---

# Troubleshooting

## Intraday Script Issues

### "No intraday data available"

**Causes:**
- Market not open yet
- Weekend/holiday
- Too early in the day (before 9:30 AM)
- Yahoo Finance API issue

**Solutions:**
- Wait until market opens (9:30 AM ET)
- Check if it's a trading day
- Try running after 10 AM when data is established
- Check execution log for API errors

### Missing 1-minute bars

**Causes:**
- Low-volume stock (gaps in 1-minute data)
- API rate limiting
- Partial day (ran before market close)

**Solutions:**
- This is normal for low-volume stocks
- Run less frequently to avoid rate limits
- Wait until after 4 PM for complete data

## Historical Backfill Issues

### "No historical data returned"

**Causes:**
- Invalid ticker
- Date too far in the past
- Weekend/holiday dates
- Yahoo Finance doesn't have data

**Solutions:**
- Verify ticker is correct
- Check date range is reasonable
- Script automatically skips weekends
- Use `EW_testOptionsBackfill()` to debug

### Incorrect P/L values

**Causes:**
- Wrong strike price entered
- Incorrect entry date
- Remember: this is intrinsic value, not actual premium

**Solutions:**
- Double-check strike price in sheet
- Verify entry date is accurate
- Compare against your brokerage statements
- Understand intrinsic vs. premium difference

---

# Example Workflows

## Workflow 1: Day Trader / Scalper

**Goal:** Review end-of-day minute-by-minute P/L

**Setup:**
1. Daily trigger: `EW_updateOptionsIntraday()` at 5 PM (after close)
2. Or manual: Run when you want to review today's trades

**Analysis:**
- After close, check "Long Calls Options" sheet
- Review all 1-minute bars from 9:30 AM - 4:00 PM
- Identify best entry/exit times for future trades
- Analyze which sessions (OPEN, MIDDAY, POWER_HOUR) were most profitable

## Workflow 2: Swing Trader

**Goal:** Track daily P/L on multi-day positions

**Setup:**
1. One-time: Run `EW_addOptionsPnLColumns()`
2. Daily trigger: `EW_backfillOptionsHistorical()` at 6 PM

**Analysis:**
- Check "Long Calls" sheet for summary columns
- Review Max_PnL and Min_PnL
- View Daily_PnL_Array for daily breakdown

## Workflow 3: Both Day & Swing Trading

**Goal:** Detailed intraday + historical tracking

**Setup:**
1. Intraday: `EW_updateOptionsIntraday()` at **5 PM** (captures full day's 1-minute data)
2. Historical: `EW_backfillOptionsHistorical()` at **6 PM** (updates multi-day summary)

**Why this timing?**
- 5 PM = Intraday first (needs fresh data from today's close)
- 6 PM = Historical second (includes today's closing price in daily summary)
- Both run once per day, no overlap

**Analysis:**
- "Long Calls" sheet = Multi-day summary with daily P/L
- "Long Calls Options" sheet = Today's minute-by-minute detail
- Use both views for comprehensive analysis

---

# Advanced Usage

## Extending to Other Strategies

Both scripts currently work with "Long Calls" sheet. To extend to other strategies:

### Intraday Tracking

Edit `EW_updateOptionsIntraday()`:

```javascript
// Change these lines:
const sourceSheet = ss.getSheetByName('Long Puts');  // Change sheet name
const outputSheetName = 'Long Puts Options';         // Change output name

// And in position reading:
optionType: 'P',  // Change 'C' to 'P' for puts
```

### Historical Backfill

The original backfill script already supports all strategies. Just run:

```javascript
EW_backfillHistoricalTracking()  // Processes all strategy sheets
```

## Calculating Actual Premium P/L

If you track actual premiums paid, you can calculate real P/L:

1. Add "Entry_Premium" column to sheet
2. Manually enter premium you paid (e.g., $2.50 = $250)
3. Calculate: `Actual P/L = Current_Intrinsic - Entry_Premium`

Example:
```
Entry Premium: $250 (what you paid)
Current Intrinsic: $375 (current value)
Actual P/L = $375 - $250 = $125 profit
```

## Export for Analysis

To analyze the data in Python/Excel:

1. File → Download → Microsoft Excel (.xlsx)
2. Or use Google Sheets API to fetch data
3. Or copy "Long Calls Options" sheet data and paste into CSV

The minute-by-minute data is perfect for:
- Time series analysis
- Volatility studies
- Optimal entry/exit timing
- Machine learning models

---

# Support

For issues or questions:

1. **Check execution log:** View → Logs (Ctrl+Enter)
2. **Test single position:** Use test functions to debug
3. **Verify data:** Manually calculate one example
4. **Check API limits:** Yahoo Finance has rate limits
5. **Review error messages:** Look for specific error codes

## Common Error Messages

| Error | Meaning | Solution |
|-------|---------|----------|
| "Missing required column" | Sheet doesn't have ticker/strike/expDate | Check column headers match exactly |
| "No data returned" | Yahoo Finance has no data | Verify ticker is valid and market is open |
| "Long Calls sheet not found" | Sheet name doesn't match | Rename sheet to exactly "Long Calls" |
| "Time limit exceeded" | Too many positions | Script auto-continues, just wait and re-run |

---

# References

- [Yahoo Finance API](https://www.yahoofinanceapi.com/)
- [Options Intrinsic Value](https://www.investopedia.com/terms/i/intrinsicvalue.asp)
- [Google Apps Script Triggers](https://developers.google.com/apps-script/guides/triggers/installable)
- [Options Trading Basics](https://www.investopedia.com/options-basics-tutorial-4583012)
