# Options Chain Fetching Guide

## Problem: Only Getting Today's Options

If you're only seeing options for the current day, it's likely because:

1. You're using `yfinance` without specifying expiration dates
2. You're not looping through all available expirations
3. You haven't discovered the `yahooquery` library yet

## Solution: Two Approaches

### Approach 1: Use yahooquery (Recommended ✓)

**Why yahooquery?**
- ✓ Single API call gets ALL expiration dates
- ✓ Better data structure (MultiIndex DataFrame)
- ✓ Cleaner, more intuitive API
- ✓ Less code, fewer errors

**Installation:**
```bash
pip install yahooquery
```

**Basic Usage:**
```python
from yahooquery import Ticker

# Create ticker
ticker = Ticker('AAPL')

# Get FULL options chain (all expirations!)
options_df = ticker.option_chain

# That's it! You now have ALL options
print(f"Total contracts: {len(options_df)}")
print(f"Expirations: {len(options_df.index.get_level_values(1).unique())}")
```

**Data Structure:**
```
MultiIndex DataFrame:
├── Level 0: symbol (e.g., 'AAPL')
├── Level 1: expiration (e.g., '2024-12-20')
└── Level 2: optionType ('calls' or 'puts')

Columns: contractSymbol, strike, lastPrice, bid, ask,
         volume, openInterest, impliedVolatility, inTheMoney, etc.
```

**Filtering Examples:**

```python
# Get all calls
all_calls = options_df.xs('calls', level=2)

# Get all puts
all_puts = options_df.xs('puts', level=2)

# Get specific expiration
options_df.loc['AAPL', '2024-12-20']

# Get specific expiration, only calls
options_df.loc['AAPL', '2024-12-20', 'calls']

# In-the-money options
itm = options_df[options_df['inTheMoney'] == True]

# High volume options
high_vol = options_df[options_df['volume'] > 1000]

# Reset index for easier manipulation
flat_df = options_df.reset_index()
```

**Multiple Tickers:**
```python
# Fetch multiple tickers at once
tickers = Ticker(['AAPL', 'MSFT', 'GOOGL'])
all_options = tickers.option_chain

# Filter by symbol
aapl_options = all_options.xs('AAPL', level=0)
```

---

### Approach 2: Use yfinance (More Work)

If you must use `yfinance`, here's how to get all expirations:

**The Problem:**
```python
import yfinance as yf

ticker = yf.Ticker('AAPL')

# This only gets ONE expiration date
opt = ticker.option_chain()  # ❌ Only returns nearest expiration
```

**The Solution:**
```python
import yfinance as yf
import pandas as pd

ticker = yf.Ticker('AAPL')

# Step 1: Get list of ALL expiration dates
expirations = ticker.options
print(f"Available expirations: {len(expirations)}")

# Step 2: Loop through each expiration
all_options = []

for exp_date in expirations:
    # Fetch options for this expiration
    opt = ticker.option_chain(exp_date)

    # Process calls
    calls = opt.calls.copy()
    calls['expiration'] = exp_date
    calls['optionType'] = 'call'

    # Process puts
    puts = opt.puts.copy()
    puts['expiration'] = exp_date
    puts['optionType'] = 'put'

    # Combine
    all_options.append(calls)
    all_options.append(puts)

# Step 3: Combine all into single DataFrame
full_chain = pd.concat(all_options, ignore_index=True)

print(f"Total contracts: {len(full_chain)}")
print(f"Unique expirations: {full_chain['expiration'].nunique()}")
```

---

## Comparison Table

| Feature | yahooquery | yfinance |
|---------|-----------|----------|
| Get all expirations | ✓ Single call | ❌ Must loop |
| Code complexity | Low | High |
| API calls | 1 | N (# of expirations) |
| Data structure | MultiIndex | Separate DFs |
| Multiple tickers | ✓ Built-in | ❌ Manual |
| Performance | Fast | Slower |
| Learning curve | Easy | Moderate |

---

## Example Scripts

### 1. Basic Options Fetcher
```python
from yahooquery import Ticker
import pandas as pd

def get_full_options_chain(symbol):
    """
    Get complete options chain for a symbol.

    Returns:
        DataFrame with all options across all expirations
    """
    ticker = Ticker(symbol)
    options_df = ticker.option_chain

    # Reset index for easier manipulation
    return options_df.reset_index()

# Usage
aapl_options = get_full_options_chain('AAPL')
print(f"Total AAPL options: {len(aapl_options)}")
print(f"Expirations: {aapl_options['expiration'].nunique()}")
```

### 2. Options Screener
```python
from yahooquery import Ticker

def screen_options(symbol, min_volume=100, min_iv=0.3, max_strike=None):
    """
    Screen options based on criteria.
    """
    ticker = Ticker(symbol)
    options_df = ticker.option_chain.reset_index()

    # Apply filters
    filtered = options_df[
        (options_df['volume'] > min_volume) &
        (options_df['impliedVolatility'] > min_iv)
    ]

    if max_strike:
        filtered = filtered[filtered['strike'] <= max_strike]

    return filtered.sort_values('volume', ascending=False)

# Usage
screened = screen_options('AAPL', min_volume=500, min_iv=0.4)
print(screened[['expiration', 'strike', 'optionType', 'volume', 'impliedVolatility']])
```

### 3. Export for Analysis
```python
from yahooquery import Ticker
import pandas as pd
from datetime import datetime

def export_options_to_csv(symbol, output_dir='data/options'):
    """
    Fetch and export options chain to CSV.
    """
    ticker = Ticker(symbol)
    options_df = ticker.option_chain.reset_index()

    # Add metadata
    options_df['fetch_date'] = datetime.now()
    options_df['symbol'] = symbol

    # Save
    filename = f"{output_dir}/{symbol}_options_{datetime.now():%Y%m%d}.csv"
    options_df.to_csv(filename, index=False)

    print(f"Saved {len(options_df)} contracts to {filename}")
    return filename

# Usage
export_options_to_csv('AAPL')
```

---

## Integration with Streamlit

See [streamlit_options_example.py](../scripts/streamlit_options_example.py) for a complete example of building an options chain viewer web app.

**Quick Start:**
```bash
# Install dependencies
pip install yahooquery streamlit plotly

# Run the app
streamlit run scripts/streamlit_options_example.py
```

---

## Common Issues & Solutions

### Issue: "No options data returned"
**Cause:** Ticker doesn't have options (e.g., some ETFs, foreign stocks)
**Solution:** Verify the ticker has options on Yahoo Finance website first

### Issue: "MultiIndex is confusing"
**Cause:** yahooquery returns MultiIndex by default
**Solution:** Use `.reset_index()` to flatten:
```python
options_df = ticker.option_chain.reset_index()
```

### Issue: "Data is stale"
**Cause:** Yahoo Finance data can be delayed 15+ minutes
**Solution:** Be aware of delay; for real-time data, use paid APIs

### Issue: "Too much data, app is slow"
**Cause:** Loading thousands of options contracts
**Solution:** Filter by expiration, volume, or specific strikes:
```python
# Only get near-term expirations
near_term = options_df[options_df.index.get_level_values(1) < '2024-12-31']
```

---

## Performance Tips

1. **Cache the data:**
   ```python
   import streamlit as st

   @st.cache_data(ttl=300)  # Cache for 5 minutes
   def get_options(symbol):
       return Ticker(symbol).option_chain
   ```

2. **Fetch multiple symbols efficiently:**
   ```python
   # Good: Single API call
   tickers = Ticker(['AAPL', 'MSFT', 'GOOGL'])
   all_options = tickers.option_chain

   # Bad: Multiple API calls
   for symbol in ['AAPL', 'MSFT', 'GOOGL']:
       ticker = Ticker(symbol)
       options = ticker.option_chain  # Separate call each time
   ```

3. **Filter early:**
   ```python
   # Filter immediately after fetching
   options_df = ticker.option_chain
   high_vol = options_df[options_df['volume'] > 1000]  # Reduce size ASAP
   ```

---

## Resources

- **yahooquery Documentation:** https://yahooquery.dpguthrie.com
- **GitHub Repository:** https://github.com/dpguthrie/yahooquery
- **Yahoo Finance:** https://finance.yahoo.com
- **Options Basics:** https://www.investopedia.com/options-basics-tutorial-4583012

---

## Next Steps

1. Install yahooquery: `pip install yahooquery`
2. Run the demo script: `python scripts/demo_options_chain.py`
3. Try the Streamlit app: `streamlit run scripts/streamlit_options_example.py`
4. Build your own options analysis tools!

---

*Last updated: 2025-10-10*
