# Options Historical Backfill Guide

## Overview

The Options Historical Backfill script (`26_OptionsHistoricalBackfill.js`) calculates daily profit/loss (P/L) for options positions in the "Long Calls" sheet based on historical stock prices.

**Important Note:** This script calculates **intrinsic value P/L**, not actual options premium P/L, because historical options premium data is not readily available from free APIs like Yahoo Finance.

## How It Works

### Intrinsic Value Calculation

For each trading day, the script calculates the intrinsic value of the option:

- **Call Options:** `Intrinsic Value = max(0, stock_price - strike) × 100`
- **Put Options:** `Intrinsic Value = max(0, strike - stock_price) × 100`

The multiplier of 100 represents the per-contract value (standard options contracts control 100 shares).

### Daily P/L Calculation

- **Daily P/L:** Change in intrinsic value from previous day
- **Cumulative P/L:** Total change from entry date to current date
- **Percent Return:** (Cumulative P/L / Entry Intrinsic Value) × 100

## Prerequisites

### Required Sheet Columns

Your "Long Calls" sheet must have these columns:

1. **ticker** - Stock symbol (e.g., "PFE")
2. **strike** - Strike price (e.g., 24)
3. **expDate** - Expiration date (e.g., "2025-11-07")
4. **runDate** - Entry date (when position was opened)

### Optional Column

- **optionType** - 'C' for calls, 'P' for puts (defaults to 'C' for Long Calls sheet)

## Setup

### Step 1: Add P/L Tracking Columns

Before running the backfill, add the necessary P/L columns to your sheet:

```javascript
// In Google Apps Script editor, run:
EW_addOptionsPnLColumns()
```

This adds the following columns:
- `Entry_Intrinsic` - Intrinsic value at entry
- `Current_Intrinsic` - Current intrinsic value
- `Cumulative_PnL` - Total P/L from entry
- `Max_PnL` - Best P/L achieved
- `Min_PnL` - Worst P/L experienced
- `Percent_Return` - Percentage return
- `Daily_PnL_Array` - JSON array with daily details

## Usage

### Full Backfill (All Incomplete Positions)

Run this to process all positions that don't have P/L data:

```javascript
EW_backfillOptionsHistorical()
```

**Features:**
- Processes all rows with missing P/L data
- Skips rows that already have data (idempotent)
- Includes continuation support for large datasets (automatically resumes if time limit reached)
- Logs progress to execution log

**When to use:**
- Initial setup after adding P/L columns
- Daily automated backfill via triggers
- After adding new positions

### Selected Rows Only

To process specific positions:

1. Select the rows you want to update in the sheet
2. Run the function:

```javascript
EW_backfillOptionsSelected()
```

**When to use:**
- Testing on specific positions
- Updating a handful of positions
- Re-calculating after data corrections

### Test Single Position

To test the calculation on one position:

1. Click on any cell in the row you want to test
2. Run:

```javascript
EW_testOptionsBackfill()
```

This displays:
- Entry intrinsic value
- Final P/L
- Max/Min P/L
- Daily breakdown in execution log

**When to use:**
- Verifying calculations
- Troubleshooting specific positions
- Understanding the data before full backfill

## Understanding the Results

### Column Values

| Column | Description | Example |
|--------|-------------|---------|
| Entry_Intrinsic | Option value at entry | $150.00 |
| Current_Intrinsic | Current option value | $275.00 |
| Cumulative_PnL | Total profit/loss | $125.00 |
| Max_PnL | Best P/L achieved | $200.00 |
| Min_PnL | Worst P/L experienced | -$50.00 |
| Percent_Return | Percentage gain/loss | 83.33% |
| Daily_PnL_Array | JSON with daily data | [see below] |

### Daily P/L Array Format

The `Daily_PnL_Array` column contains a JSON array with detailed daily data:

```json
[
  {
    "date": "2025-10-15",
    "price": 25.50,
    "intrinsic": 150.00,
    "dailyPnL": 0.00,
    "cumPnL": 0.00,
    "pctChange": 0.00
  },
  {
    "date": "2025-10-16",
    "price": 26.25,
    "intrinsic": 225.00,
    "dailyPnL": 75.00,
    "cumPnL": 75.00,
    "pctChange": 50.00
  }
]
```

**Fields:**
- `date` - Trading date
- `price` - Stock closing price
- `intrinsic` - Option intrinsic value
- `dailyPnL` - P/L change from previous day
- `cumPnL` - Cumulative P/L from entry
- `pctChange` - Percentage change from entry

## Example Calculation

### Scenario

- **Position:** PFE $24 Call
- **Entry Date:** 2025-10-15
- **Strike:** $24.00
- **Entry Stock Price:** $25.50

### Day-by-Day Calculation

| Date | Stock Price | Intrinsic Value | Daily P/L | Cumulative P/L |
|------|-------------|----------------|-----------|----------------|
| 10/15 | $25.50 | $150.00 | $0.00 | $0.00 |
| 10/16 | $26.25 | $225.00 | +$75.00 | +$75.00 |
| 10/17 | $25.75 | $175.00 | -$50.00 | +$25.00 |
| 10/18 | $27.00 | $300.00 | +$125.00 | +$150.00 |

**Formula for each day:**
```
Intrinsic Value = max(0, Stock Price - Strike) × 100
Daily P/L = Today's Intrinsic - Yesterday's Intrinsic
Cumulative P/L = Sum of all Daily P/L
```

## Limitations

### 1. Intrinsic Value Only

This script calculates **intrinsic value**, not actual options premium. Real options premiums include:
- Time value (theta decay)
- Implied volatility (vega)
- Interest rates (rho)

**What this means:**
- Actual options might be worth more than calculated (due to time value)
- Deep out-of-the-money options show $0 intrinsic even if they have market value
- Best for in-the-money or at-the-money options where intrinsic is primary component

### 2. Historical Data Availability

Yahoo Finance provides:
- **1-minute data:** Last 7 days only
- **Daily data:** Several years back

**Workaround:**
- Script automatically uses daily data (`1d` interval)
- Daily close prices are used for consistency
- For very old positions, data might not be available

### 3. Weekend and Holiday Gaps

- Markets closed on weekends/holidays
- P/L only calculated for trading days
- Gaps in data are normal and expected

## Automation

### Daily Backfill Trigger

To automatically update P/L data daily:

1. Open Apps Script editor
2. Click **Triggers** (clock icon)
3. Add trigger:
   - **Function:** `EW_backfillOptionsHistorical`
   - **Event:** Time-driven
   - **Type:** Day timer
   - **Time:** 6 PM - 7 PM (after market close)

This ensures positions are updated with the latest closing prices daily.

## Troubleshooting

### No Data Returned

**Problem:** Function returns no data for a position

**Solutions:**
1. Check if ticker is valid
2. Verify dates are not in the future
3. Confirm Yahoo Finance has data for that ticker/date
4. Check execution log for error messages

### Incorrect P/L Values

**Problem:** P/L doesn't match expectations

**Solutions:**
1. Remember this is **intrinsic value**, not actual premium
2. Verify strike price is correct
3. Check entry date is accurate
4. Use `EW_testOptionsBackfill()` to see daily breakdown

### Missing Columns Error

**Problem:** "Missing required column" error

**Solutions:**
1. Run `EW_addOptionsPnLColumns()` to add P/L columns
2. Verify sheet name is exactly "Long Calls"
3. Check that ticker, strike, expDate, runDate columns exist

### Time Limit Exceeded

**Problem:** Script times out on large datasets

**Solutions:**
- Script automatically handles continuation
- Will resume from where it stopped
- Re-run the function after a few minutes
- The continuation is automatic

## Comparison with Python Code

The user's Python code (`fetch_etf_options_intraday.py`) is designed for:
- **Real-time intraday tracking** of ETF options
- **Actual options premium prices** from Yahoo
- **Greeks calculation** (delta, gamma, theta, etc.)
- **Multiple snapshots per day** for scalping

This Google Apps Script is designed for:
- **Historical backfill** of existing positions
- **Intrinsic value approximation** (not actual premiums)
- **Daily P/L tracking** for longer-term positions
- **Spreadsheet integration** for easy analysis

### Key Differences

| Feature | Python Script | Google Apps Script |
|---------|--------------|-------------------|
| Data Type | Actual options premiums | Stock-based intrinsic value |
| Frequency | 9 snapshots per day | Daily only |
| Use Case | Intraday scalping | Historical analysis |
| Greeks | Full Greeks calculation | Not included |
| Storage | Parquet files | Google Sheets |

## Next Steps

### For More Accurate Options P/L

If you need actual options premium data:

1. **Manual Entry:**
   - Add "Entry_Premium" column
   - Manually enter the premium paid
   - Compare against current intrinsic value

2. **Options Data API:**
   - Use paid API like TDAmeritrade, Interactive Brokers
   - Fetch historical options chains
   - Calculate actual premium-based P/L

3. **Black-Scholes Approximation:**
   - Calculate theoretical premium using Black-Scholes
   - Requires historical implied volatility data
   - More complex but more accurate

### Extending Functionality

Future enhancements could include:
- Support for spreads (bull/bear spreads)
- Greeks calculation at each date
- Implied volatility tracking
- Comparison against theoretical Black-Scholes prices
- Integration with brokerage APIs for actual fill prices

## Support

For issues or questions:
1. Check execution log: View → Logs
2. Test on single position: `EW_testOptionsBackfill()`
3. Verify data with manual calculation
4. Review error messages in trace logs

## References

- [Yahoo Finance API Documentation](https://www.yahoofinanceapi.com/)
- [Options Basics](https://www.investopedia.com/terms/o/option.asp)
- [Intrinsic Value Definition](https://www.investopedia.com/terms/i/intrinsicvalue.asp)
- [Google Apps Script Time-based Triggers](https://developers.google.com/apps-script/guides/triggers/installable#time-driven_triggers)
