# Options Strategy Matcher

Matches strategy CSV files from Earnings Whisper with live options chain data from Yahoo Finance using yahooquery.

## Overview

This tool reads your strategy files (LongCalls, CoveredCalls, BullSpreads, BearSpreads) and matches them with current market options data to calculate profit/loss and track performance.

## Key Features

✓ **Automatic Matching**: Uses ticker, strike, expiration, and option type to match contracts
✓ **Dual Bid/Ask**: Shows both entry (EW) and current market bid/ask
✓ **Live P&L**: Calculates profit/loss per contract and percentage
✓ **Contract Details**: Volume, Open Interest, IV, Days to Expiration
✓ **Clean Column Names**: Strategy data uses `_EW` suffix to avoid conflicts

## Usage

### Basic Command

```bash
# Test with last 5 records from LongCalls
python scripts/match_options_strategy.py --strategy longcalls --limit 5 --tail
```

### All Options

```bash
python scripts/match_options_strategy.py \
    --strategy longcalls \     # Strategy type
    --limit 5 \                # Limit number of records
    --tail \                   # Use last N (most recent) instead of first N
    --output data/my_results.csv  # Custom output path
```

### Strategy Types

- `longcalls` - Long Calls strategy
- `coveredcalls` - Covered Calls strategy
- `bullspreads` - Bull Spreads strategy
- `bearspreads` - Bear Spreads strategy

## How It Works

### 1. Lookup Keys Created

The script creates several lookup keys for matching:

**From Strategy CSV:**
- `run_yymmdd_key`: `TICKER_YYMMDD` (e.g., `ALB_251009`)
- `exp_yymmdd_key`: `TICKER_YYMMDD` (e.g., `ALB_251107`)
- `occ_guess_call`: OCC-style symbol (e.g., `ALB251107C00091000`)
- `occ_guess_put`: OCC-style put symbol

**Join Fields:**
- `join_underlying`: Uppercase ticker
- `join_expiration`: Date-only expiration
- `join_strike_x1000`: Strike × 1000 as integer (avoids float issues)
- `join_opt_type`: `C` for calls, `P` for puts

### 2. Column Naming Convention

To avoid conflicts between strategy CSV and market data:

**Strategy CSV columns** get `_EW` suffix:
- `bid` → `bid_EW`
- `ask` → `ask_EW`
- `volume` → `volume_EW`
- `strike` → `strike_EW`
- `price` → `price_EW`

**Market data** keeps clean names:
- `bid` (current market bid)
- `ask` (current market ask)
- `volume` (current volume)
- `strike` (from options chain)
- `lastPrice` (current price)

### 3. Output Columns

| Column | Description |
|--------|-------------|
| `ticker` | Stock symbol |
| `run_date_parsed` | When strategy was created |
| `strike_used` | Strike price |
| `join_opt_type` | C or P |
| `entry_price` | Price paid (from EW) |
| `entry_bid_EW` | Entry bid (from EW) |
| `entry_ask_EW` | Entry ask (from EW) |
| `current_price` | Current last price |
| `market_bid` | Current market bid |
| `market_ask` | Current market ask |
| `pnl_per_contract` | Profit/loss per contract ($) |
| `pnl_percent` | Profit/loss percentage |
| `join_expiration` | Expiration date |
| `days_to_expiration` | Days until expiration |
| `market_volume` | Current volume |
| `market_open_interest` | Current open interest |
| `market_iv` | Implied volatility |
| `is_itm` | In the money (True/False) |
| `contractSymbol` | Full OCC symbol |

## Example Output

```
Matched Positions:
ticker  strike_used  entry_price  entry_bid_EW  entry_ask_EW  current_price  market_bid  market_ask  pnl_per_contract  pnl_percent
ALB     91.0         6.59         7.10          7.35          6.49           6.15        6.60        -10.00            -1.52%
APP     625.0        61.22        58.60         62.10         34.00          27.50       35.20       -2722.00          -44.46%
BE      87.0         13.20        12.60         13.30         13.45          10.90       14.80       25.00             1.89%

Detailed Position Analysis:

ALB - $91.0 C exp 2025-11-07
  Contract: ALB251107C00091000
  ENTRY (EW):  Price: $6.59 | Bid: $7.10 | Ask: $7.35
  MARKET (Now): Price: $6.49 | Bid: $6.15 | Ask: $6.60
  P&L: $-10.00 (-1.52%)
  Days to exp: 27
  Volume: 7 | OI: 8
  IV: 69.46% | ITM: False
```

## Matching Logic

### Successful Match Requires:
1. ✓ Ticker matches (case-insensitive)
2. ✓ Expiration date matches (exact)
3. ✓ Strike price matches (uses × 1000 integer to avoid float issues)
4. ✓ Option type matches (C or P)

### Why Matches Fail:
- ❌ Expiration already passed (options expired)
- ❌ Strike not available in market
- ❌ Option type mismatch
- ❌ Ticker doesn't have options

## Testing Results

**Test Run: Last 5 Long Calls (2025-10-11)**

```
Total records: 5
Matched: 3 (60.0%)
Unmatched: 2
  - BILL $40.0 C exp 2025-11-14 (strike not available)
  - APA $24.5 C exp 2025-11-14 (strike not available)

P&L Summary:
  Total P&L: $-2,707.00
  Avg P&L %: -14.70%
  Winners: 1
  Losers: 2
```

## File Structure

```
scripts/
  match_options_strategy.py    # Main script

google-apps-script/data/
  LongCalls.csv               # Long calls strategy
  CoveredCalls.csv            # Covered calls strategy
  BullSpreads.csv             # Bull spreads strategy
  BearSpreads.csv             # Bear spreads strategy

data/
  matched_longcalls_*.csv     # Output files (timestamped)
  options/                    # Options chain data
```

## Integration with Yahoo Query

This script leverages the yahooquery library's ability to fetch **all expiration dates in one call**:

```python
from yahooquery import Ticker

ticker = Ticker(['ALB', 'APP', 'BE'])
options_df = ticker.option_chain  # Gets ALL expirations!

# Automatically includes:
# - All strikes
# - All expirations
# - Both calls and puts
# - Real-time bid/ask
# - Volume, OI, IV
```

See [YFINANCE_VS_YAHOOQUERY.md](YFINANCE_VS_YAHOOQUERY.md) for more details.

## Common Issues

### "Unmatched records"

**Cause:** Strike price or expiration not available in market

**Solution:** Check if:
1. Options have expired
2. Strike is far OTM and not listed
3. Ticker has options trading

### "No options data returned"

**Cause:** Ticker doesn't have options

**Solution:** Verify ticker has options on Yahoo Finance

### "Match rate < 100%"

**Normal!** Some strikes/expirations may not be available or have expired.

## Next Steps

1. ✓ Test with other strategies (coveredcalls, spreads)
2. → Add historical tracking (save results daily)
3. → Create dashboard to visualize P&L over time
4. → Add alerts for significant moves
5. → Export to Google Sheets for integration

## Requirements

```bash
pip install yahooquery pandas numpy pyarrow
```

See [requirements.txt](../requirements.txt) for all dependencies.

---

*Created: 2025-10-11*
*Last Updated: 2025-10-11*
