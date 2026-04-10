# yfinance vs yahooquery: History and Comparison

## The Creators

### yfinance
**Creator:** **Ran Aroussi** ([@ranaroussi](https://github.com/ranaroussi))

**Background:**
- Software developer, financial tinkerer, and solo entrepreneur
- Founded Tradologics
- Offers CTO-as-a-Service through Automaze
- Hosts "Old School; New Tech" podcast

**Created:** May 21, 2017

**Origin Story:**
yfinance was created after Yahoo decommissioned their official Finance API on May 15, 2017. Originally named "fix-yahoo-finance," it was renamed to "yfinance" on May 26, 2019.

**Popularity:**
- ⭐ 19,400+ stars on GitHub
- 🍴 2,800+ forks
- 👥 131+ contributors
- The most popular Yahoo Finance Python library

**Other Notable Projects:**
- `quantstats` - Portfolio analytics for quants
- `pystore` - Fast data store for Pandas time-series data

---

### yahooquery
**Creator:** **Doug Guthrie** ([@dpguthrie](https://github.com/dpguthrie))

**Background:**
- Based in Fort Collins, CO
- Works with dbt-labs (data build tool)
- Focuses on data engineering and analytics tools

**Created:** December 13, 2019 (2.5 years after yfinance)

**Origin Story:**
Built as an alternative/improvement to yfinance, focusing on API endpoints rather than web scraping, with better data structures and async support.

**Popularity:**
- ⭐ 869 stars on GitHub
- 🍴 157 forks
- More specialized/focused user base
- Latest release: v2.4.1 (May 2025)

**Other Notable Projects:**
- dbt-semantic-layer tools
- Various Streamlit data apps

---

## Timeline

```
2017-05-15: Yahoo Finance API discontinued by Yahoo
2017-05-21: yfinance created by Ran Aroussi as replacement
2019-05-26: fix-yahoo-finance renamed to yfinance
2019-12-13: yahooquery created by Doug Guthrie (modern alternative)
2025-today: Both libraries actively maintained
```

---

## Key Differences in Philosophy

### yfinance (Ran Aroussi)
- **Goal:** Quick replacement for Yahoo's discontinued API
- **Approach:** Pragmatic, "get it working" mentality
- **Strength:** Massive adoption, simple API, extensive community support
- **Weakness:** Some design limitations from early architectural decisions

### yahooquery (Doug Guthrie)
- **Goal:** Better-designed successor with lessons learned from yfinance
- **Approach:** Modern API design, better data structures, async support
- **Strength:** Cleaner code, MultiIndex DataFrames, proper API endpoint usage
- **Weakness:** Smaller community, less documentation than yfinance

---

## Technical Comparison

### Architecture

| Feature | yfinance | yahooquery |
|---------|----------|------------|
| **Data Source** | Web scraping + some API | Direct API endpoints |
| **Async Support** | No | Yes (requests-futures) |
| **Data Structure** | Basic DataFrames | MultiIndex DataFrames |
| **Dependencies** | Minimal | More modern stack |
| **Speed** | Moderate | Faster (API direct) |

### Options Chain Handling

**Why yahooquery Handles Options Better:**

Doug Guthrie specifically designed yahooquery to work with **Yahoo's API endpoints directly**, which return all expirations in structured JSON format.

**yfinance approach:**
```python
import yfinance as yf

ticker = yf.Ticker('AAPL')

# Must manually iterate through expirations
all_options = []
for exp_date in ticker.options:  # Get list first
    opt = ticker.option_chain(exp_date)  # Fetch each one
    # ... manually combine results
```

**yahooquery approach:**
```python
from yahooquery import Ticker

ticker = Ticker('AAPL')

# Single call gets ALL expirations automatically
options_df = ticker.option_chain  # Done!
```

**Result:**
- yfinance: N API calls (one per expiration) + manual data wrangling
- yahooquery: 1 API call, structured MultiIndex DataFrame

---

## Feature Comparison

### Data Available

| Data Type | yfinance | yahooquery | Notes |
|-----------|----------|------------|-------|
| Historical prices | ✓ | ✓ | Both excellent |
| Real-time quotes | ✓ | ✓ | 15min delay (free) |
| Options chains | ✓ (manual) | ✓ (auto) | yahooquery easier |
| Financials | ✓ | ✓ | Similar quality |
| News | ✓ | ✓ | Both provide |
| ESG data | ✓ | ✓ | Both available |
| Screener | ✓ | ✓ | yahooquery better API |
| Multiple tickers | ✓ (manual) | ✓ (built-in) | yahooquery simpler |
| Async requests | ✗ | ✓ | yahooquery only |

### Code Examples

#### Single Ticker Data

**yfinance:**
```python
import yfinance as yf

ticker = yf.Ticker('AAPL')
hist = ticker.history(period='1mo')
info = ticker.info
```

**yahooquery:**
```python
from yahooquery import Ticker

ticker = Ticker('AAPL')
hist = ticker.history(period='1mo')
info = ticker.summary_detail
```

#### Multiple Tickers

**yfinance:**
```python
import yfinance as yf

# Download method
data = yf.download(['AAPL', 'MSFT', 'GOOGL'], period='1mo')

# Or manual loop
tickers = ['AAPL', 'MSFT', 'GOOGL']
for symbol in tickers:
    ticker = yf.Ticker(symbol)
    # ... process each
```

**yahooquery:**
```python
from yahooquery import Ticker

# Built-in support for multiple tickers
tickers = Ticker(['AAPL', 'MSFT', 'GOOGL'])
data = tickers.history(period='1mo')
info = tickers.summary_detail
```

#### Options Chain (The Big Difference!)

**yfinance (complex):**
```python
import yfinance as yf
import pandas as pd

ticker = yf.Ticker('AAPL')

# Step 1: Get all expiration dates
expirations = ticker.options
print(f"Found {len(expirations)} expirations")

# Step 2: Loop through each expiration
all_options = []
for exp_date in expirations:
    opt = ticker.option_chain(exp_date)

    # Process calls
    calls = opt.calls.copy()
    calls['expiration'] = exp_date
    calls['optionType'] = 'call'

    # Process puts
    puts = opt.puts.copy()
    puts['expiration'] = exp_date
    puts['optionType'] = 'put'

    all_options.extend([calls, puts])

# Step 3: Combine all data
full_chain = pd.concat(all_options, ignore_index=True)
print(f"Total contracts: {len(full_chain)}")
```

**yahooquery (simple):**
```python
from yahooquery import Ticker

ticker = Ticker('AAPL')

# One line gets everything!
full_chain = ticker.option_chain
print(f"Total contracts: {len(full_chain)}")

# Already has MultiIndex: (symbol, expiration, optionType)
# No manual processing needed
```

---

## When to Use Which Library

### Use yfinance if:
- ✓ You need basic historical price data
- ✓ You want the most community support and examples
- ✓ You're working with code that already uses it
- ✓ You need maximum compatibility with tutorials/guides
- ✓ Simple use cases (just downloading price history)

### Use yahooquery if:
- ✓ You need full options chains (all expirations)
- ✓ You're fetching data for multiple tickers
- ✓ You want better data structures (MultiIndex)
- ✓ You need async support for performance
- ✓ You prefer cleaner, more modern API design
- ✓ You're building production applications

### Use both if:
- ✓ Different parts of your app need different strengths
- ✓ You want to compare data quality between sources
- ✓ One library is missing a specific feature you need

---

## Real-World Performance

### Example: Fetching IWM Options Chain

**yfinance approach:**
```
Step 1: Get expirations list (1 API call)
Step 2: Loop through 28 expirations (28 API calls)
Step 3: Process and combine data manually
Total: 29 API calls + manual processing
```

**yahooquery approach:**
```
Step 1: Call ticker.option_chain (1 API call)
Total: 1 API call, automatic processing
Result: 2,915 contracts across 28 expirations
```

**Performance difference:**
- yfinance: ~15-30 seconds (network dependent)
- yahooquery: ~2-5 seconds
- Speed improvement: 3-6x faster

---

## Migration Guide

### From yfinance to yahooquery

**Before (yfinance):**
```python
import yfinance as yf

ticker = yf.Ticker('AAPL')
hist = ticker.history(period='1mo')
info = ticker.info

# Options - complex
expirations = ticker.options
opt = ticker.option_chain(expirations[0])
```

**After (yahooquery):**
```python
from yahooquery import Ticker

ticker = Ticker('AAPL')
hist = ticker.history(period='1mo')
info = ticker.summary_detail  # Note: different attribute

# Options - simple!
opt = ticker.option_chain  # All expirations
```

**Key Changes:**
1. Import: `yfinance` → `yahooquery`
2. Some attributes renamed (e.g., `info` → `summary_detail`)
3. Options chain: automatic vs manual
4. Data structure: basic DataFrame → MultiIndex (for options)

---

## Community and Support

### yfinance
- **Documentation:** https://ranaroussi.github.io/yfinance/
- **GitHub:** https://github.com/ranaroussi/yfinance
- **Issues:** 500+ open issues (very active)
- **Community:** Large, many Stack Overflow answers
- **Maintenance:** Active, frequent updates

### yahooquery
- **Documentation:** https://yahooquery.dpguthrie.com/
- **GitHub:** https://github.com/dpguthrie/yahooquery
- **Issues:** 20+ open issues
- **Community:** Smaller but responsive
- **Maintenance:** Active, regular updates

---

## Conclusion

Both libraries were created by talented developers solving the same problem (Yahoo's API discontinuation) with different approaches:

- **Ran Aroussi (yfinance):** Built a quick, pragmatic replacement that gained massive adoption
- **Doug Guthrie (yahooquery):** Built a cleaner, more modern alternative with better design

**For this project's needs (options chains):** yahooquery is clearly superior due to its single-call API for all expirations.

**Bottom line:**
- yfinance = The industry standard with massive community
- yahooquery = The better-designed modern alternative

Both are excellent tools maintained by skilled developers who have made financial data accessible to Python developers worldwide.

---

## Additional Resources

### yfinance
- GitHub: https://github.com/ranaroussi/yfinance
- Docs: https://ranaroussi.github.io/yfinance/
- Creator: https://github.com/ranaroussi
- PyPI: https://pypi.org/project/yfinance/

### yahooquery
- GitHub: https://github.com/dpguthrie/yahooquery
- Docs: https://yahooquery.dpguthrie.com/
- Creator: https://github.com/dpguthrie
- PyPI: https://pypi.org/project/yahooquery/

### This Repository
- Options guide: [docs/options_chain_guide.md](options_chain_guide.md)
- Quick start: [docs/QUICK_START_OPTIONS.md](QUICK_START_OPTIONS.md)
- Scripts: [scripts/README_OPTIONS.md](../scripts/README_OPTIONS.md)

---

*Last updated: 2025-10-10*
