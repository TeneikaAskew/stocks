# Quick Start: Getting Full Options Chains

## TL;DR

**Problem:** Only seeing today's options with your API
**Solution:** Use `yahooquery` instead of `yfinance`

```python
# Install
pip install yahooquery

# Use (ONE LINE!)
from yahooquery import Ticker
options = Ticker('AAPL').option_chain  # All expirations!
```

---

## The Difference

### ❌ yfinance (What you're probably doing)

```python
import yfinance as yf

ticker = yf.Ticker('AAPL')
options = ticker.option_chain()  # Only gets ONE expiration (today/nearest)
```

**To get all expirations with yfinance, you need to:**
```python
all_options = []
for exp_date in ticker.options:  # Get list of dates
    opt = ticker.option_chain(exp_date)  # Fetch each date
    # ... combine manually
```

### ✅ yahooquery (The better way)

```python
from yahooquery import Ticker

ticker = Ticker('AAPL')
options = ticker.option_chain  # Automatically gets ALL expirations!
```

---

## Demo Results (AAPL on 2025-10-10)

### yfinance
- ❌ Manual work required
- ❌ 21 separate API calls needed (one per expiration)
- ❌ Must loop and combine results yourself

### yahooquery
- ✅ **2,099 total contracts** (all expirations)
- ✅ **21 expiration dates** (all available)
- ✅ **1 API call** (automatic)
- ✅ **Clean MultiIndex DataFrame**

---

## Example Output Structure

```
yahooquery returns:
Total contracts: 2,099
├── Calls: 1,087
└── Puts: 1,012

Across 21 expiration dates
MultiIndex levels:
  Level 0: symbol ('AAPL')
  Level 1: expiration (21 dates from 2025-10-10 to 2027-01-15)
  Level 2: optionType ('calls' or 'puts')

Columns:
  contractSymbol, strike, lastPrice, bid, ask,
  volume, openInterest, impliedVolatility, inTheMoney, etc.
```

---

## Common Filtering

```python
from yahooquery import Ticker

# Get data
ticker = Ticker('AAPL')
df = ticker.option_chain

# All calls only
calls = df.xs('calls', level=2)

# All puts only
puts = df.xs('puts', level=2)

# Specific expiration
exp_df = df.loc['AAPL', '2025-10-17']

# In-the-money only
itm = df[df['inTheMoney'] == True]

# High volume (>1000)
high_vol = df.xs('calls', level=2)
high_vol = high_vol[high_vol['volume'] > 1000]

# Reset index for easier pandas operations
flat_df = df.reset_index()
```

---

## Try It Now

**1. Run the demo:**
```bash
python scripts/demo_options_chain.py
```

**2. Launch Streamlit app:**
```bash
streamlit run scripts/streamlit_options_example.py
```

**3. Read the full guide:**
- [docs/options_chain_guide.md](options_chain_guide.md)

---

## Why This Matters for Your Streamlit App

The dpguthrie/yahooquery repository's Streamlit app works so well because:

1. **Single call** gets complete data → Fast initial load
2. **MultiIndex structure** → Easy to filter by expiration/type
3. **All expirations available** → Users can explore any date
4. **Consistent data format** → Simpler code, fewer bugs

Your app was likely only showing today's options because without the expiration parameter, `yfinance.option_chain()` defaults to the nearest/current expiration only.

---

## Next Steps

1. ✅ Installed yahooquery
2. ✅ Ran demo script
3. → Try the Streamlit example
4. → Build your own options analyzer
5. → Integrate with your existing trading system

---

*Last updated: 2025-10-10*



