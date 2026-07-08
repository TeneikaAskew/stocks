# Alpha Vantage API Documentation

> Source: https://www.alphavantage.co/documentation/
> Captured: April 30, 2026

Alpha Vantage stock APIs are grouped into 9 categories: (1) Core Time Series Stock Data APIs, (2) Index Data APIs, (3) US Options Data APIs, (4) Alpha Intelligence™, (5) Fundamental Data, (6) Physical and Crypto Currencies, (7) Commodities, (8) Economic Indicators, and (9) Technical Indicators. Examples in this documentation are for demo purposes. Claim your free API key at https://www.alphavantage.co/support/#api-key.

---

## Table of Contents

- [Core Stock APIs](#core-stock-apis)
- [Index Data APIs (Premium)](#index-data-apis-premium)
- [Options Data APIs](#options-data-apis)
- [Alpha Intelligence™](#alpha-intelligence)
- [Fundamental Data](#fundamental-data)
- [Foreign Exchange Rates (FX)](#foreign-exchange-rates-fx)
- [Digital & Crypto Currencies](#digital--crypto-currencies)
- [Commodities](#commodities)
- [Economic Indicators](#economic-indicators)
- [Technical Indicators](#technical-indicators)

---

## Core Stock APIs

This suite of APIs provides global equity data in 4 different temporal resolutions: daily, weekly, monthly, and intraday, with 20+ years of historical depth.

---

### TIME_SERIES_INTRADAY

**Premium / Trending**

This API returns current and 20+ years of historical intraday OHLCV time series of the equity specified, covering pre-market and post-market hours where applicable (e.g., 4:00am to 8:00pm Eastern Time for the US market). You can query both raw (as-traded) and split/dividend-adjusted intraday data from this endpoint.

#### API Parameters

- **Required `function`**: `TIME_SERIES_INTRADAY`
- **Required `symbol`**: e.g., `symbol=IBM`
- **Required `interval`**: `1min`, `5min`, `15min`, `30min`, `60min`
- Optional `adjusted`: Default `true`. Set `false` for raw values.
- Optional `extended_hours`: Default `true` (includes pre/post-market). Set `false` for regular hours only.
- Optional `month`: YYYY-MM format. Any month since 2000-01.
- Optional `outputsize`: `compact` (latest 100) or `full` (trailing 30 days, or full month if `month` is set).
- Optional `datatype`: `json` (default) or `csv`.
- Optional `entitlement`: `realtime` or `delayed` (15-min).
- **Required `apikey`**

#### Examples

```
https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=5min&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=5min&outputsize=full&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=5min&month=2009-01&outputsize=full&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=5min&apikey=demo&datatype=csv
```

> Premium endpoint for realtime, 15-min delayed, and historical intraday data.

#### Language-specific guides

**Python**

```python
import requests

url = 'https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=5min&apikey=demo'
r = requests.get(url)
data = r.json()
print(data)
```

**NodeJS**

```javascript
'use strict';
var request = require('request');

var url = 'https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=5min&apikey=demo';

request.get({
    url: url,
    json: true,
    headers: {'User-Agent': 'request'}
  }, (err, res, data) => {
    if (err) {
      console.log('Error:', err);
    } else if (res.statusCode !== 200) {
      console.log('Status:', res.statusCode);
    } else {
      console.log(data);
    }
});
```

**PHP**

```php
<?php
$json = file_get_contents('https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=5min&apikey=demo');
$data = json_decode($json,true);
print_r($data);
exit;
```

**C#/.NET**

```csharp
using System;
using System.Collections.Generic;
using System.Net;
using System.Web.Script.Serialization; // .NET Framework
using System.Text.Json; // .NET Core

namespace ConsoleTests
{
    internal class Program
    {
        private static void Main(string[] args)
        {
            string QUERY_URL = "https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=5min&apikey=demo";
            Uri queryUri = new Uri(QUERY_URL);

            using (WebClient client = new WebClient())
            {
                // .NET Framework
                JavaScriptSerializer js = new JavaScriptSerializer();
                dynamic json_data = js.Deserialize(client.DownloadString(queryUri), typeof(object));

                // .NET Core
                dynamic json_data2 = JsonSerializer.Deserialize<Dictionary<string, dynamic>>(client.DownloadString(queryUri));
            }
        }
    }
}
```

---

### TIME_SERIES_DAILY

This API returns raw (as-traded) daily time series (date, daily open/high/low/close/volume) of the global equity specified, covering 20+ years of historical data. For split/dividend-adjusted data, use `TIME_SERIES_DAILY_ADJUSTED`.

#### API Parameters

- **Required `function`**: `TIME_SERIES_DAILY`
- **Required `symbol`**: e.g., `symbol=IBM`
- Optional `outputsize`: `compact` (latest 100) or `full` (20+ years; premium).
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

#### Examples

```
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=IBM&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=IBM&outputsize=full&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=TSCO.LON&outputsize=full&apikey=demo  (UK - LSE)
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=SHOP.TRT&outputsize=full&apikey=demo  (Canada - TSX)
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=GPV.TRV&outputsize=full&apikey=demo  (Canada - TSXV)
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=MBG.DEX&outputsize=full&apikey=demo  (Germany - XETRA)
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=RELIANCE.BSE&outputsize=full&apikey=demo  (India - BSE)
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=600104.SHH&outputsize=full&apikey=demo  (China - Shanghai)
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=000002.SHZ&outputsize=full&apikey=demo  (China - Shenzhen)
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=IBM&apikey=demo&datatype=csv
```

100,000+ symbols are supported. Use the [Search Endpoint](#symbol_search-search-endpoint) to look up specific symbols.

#### Language-specific guides

**Python**

```python
import requests

url = 'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=IBM&apikey=demo'
r = requests.get(url)
data = r.json()
print(data)
```

**NodeJS**

```javascript
'use strict';
var request = require('request');

var url = 'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=IBM&apikey=demo';

request.get({
    url: url,
    json: true,
    headers: {'User-Agent': 'request'}
  }, (err, res, data) => {
    if (err) console.log('Error:', err);
    else if (res.statusCode !== 200) console.log('Status:', res.statusCode);
    else console.log(data);
});
```

**PHP**

```php
<?php
$json = file_get_contents('https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=IBM&apikey=demo');
$data = json_decode($json,true);
print_r($data);
exit;
```

**C#/.NET** — same pattern as TIME_SERIES_INTRADAY with `function=TIME_SERIES_DAILY`.

---

### TIME_SERIES_DAILY_ADJUSTED

**Premium / Trending**

Returns raw daily OHLCV values, adjusted close, and historical split/dividend events for the global equity specified, covering 20+ years.

#### API Parameters

- **Required `function`**: `TIME_SERIES_DAILY_ADJUSTED`
- **Required `symbol`**
- Optional `outputsize`: `compact` (default) or `full`.
- Optional `datatype`: `json` (default) or `csv`.
- Optional `entitlement`: `realtime` or `delayed`.
- **Required `apikey`**

#### Examples

```
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=IBM&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=IBM&outputsize=full&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=TSCO.LON&outputsize=full&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=SHOP.TRT&outputsize=full&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=GPV.TRV&outputsize=full&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=MBG.DEX&outputsize=full&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=RELIANCE.BSE&outputsize=full&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=600104.SHH&outputsize=full&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=000002.SHZ&outputsize=full&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=IBM&apikey=demo&datatype=csv
```

> Premium API function.

#### Language-specific guides

**Python**

```python
import requests
url = 'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=IBM&apikey=demo'
r = requests.get(url)
data = r.json()
print(data)
```

**NodeJS**

```javascript
'use strict';
var request = require('request');
var url = 'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=IBM&apikey=demo';
request.get({url: url, json: true, headers: {'User-Agent': 'request'}}, (err, res, data) => {
    if (err) console.log('Error:', err);
    else if (res.statusCode !== 200) console.log('Status:', res.statusCode);
    else console.log(data);
});
```

**PHP**

```php
<?php
$json = file_get_contents('https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=IBM&apikey=demo');
$data = json_decode($json,true);
print_r($data);
exit;
```

**C#/.NET** — same pattern as TIME_SERIES_INTRADAY with `function=TIME_SERIES_DAILY_ADJUSTED`.

---

### TIME_SERIES_WEEKLY

Returns weekly time series (last trading day of each week, weekly OHLCV) of the global equity specified, covering 20+ years.

#### API Parameters

- **Required `function`**: `TIME_SERIES_WEEKLY`
- **Required `symbol`**
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

#### Examples

```
https://www.alphavantage.co/query?function=TIME_SERIES_WEEKLY&symbol=IBM&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_WEEKLY&symbol=TSCO.LON&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_WEEKLY&symbol=IBM&apikey=demo&datatype=csv
```

#### Language-specific guides

**Python**

```python
import requests
url = 'https://www.alphavantage.co/query?function=TIME_SERIES_WEEKLY&symbol=IBM&apikey=demo'
r = requests.get(url)
data = r.json()
print(data)
```

**NodeJS**

```javascript
var request = require('request');
var url = 'https://www.alphavantage.co/query?function=TIME_SERIES_WEEKLY&symbol=IBM&apikey=demo';
request.get({url: url, json: true, headers: {'User-Agent': 'request'}}, (err, res, data) => {
    if (err) console.log('Error:', err);
    else console.log(data);
});
```

**PHP**

```php
<?php
$json = file_get_contents('https://www.alphavantage.co/query?function=TIME_SERIES_WEEKLY&symbol=IBM&apikey=demo');
$data = json_decode($json,true);
print_r($data);
```

**C#/.NET** — same pattern as TIME_SERIES_INTRADAY with `function=TIME_SERIES_WEEKLY`.

---

### TIME_SERIES_WEEKLY_ADJUSTED

Returns weekly adjusted time series (last trading day of each week, weekly OHLC, weekly adjusted close, weekly volume, weekly dividend) of the global equity specified, 20+ years.

#### API Parameters

- **Required `function`**: `TIME_SERIES_WEEKLY_ADJUSTED`
- **Required `symbol`**
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

#### Examples

```
https://www.alphavantage.co/query?function=TIME_SERIES_WEEKLY_ADJUSTED&symbol=IBM&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_WEEKLY_ADJUSTED&symbol=TSCO.LON&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_WEEKLY_ADJUSTED&symbol=IBM&apikey=demo&datatype=csv
```

Same Python/NodeJS/PHP/C# patterns as above with the appropriate URL.

---

### TIME_SERIES_MONTHLY

Returns monthly time series (last trading day of each month, monthly OHLCV) of the global equity specified, 20+ years.

#### API Parameters

- **Required `function`**: `TIME_SERIES_MONTHLY`
- **Required `symbol`**
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

#### Examples

```
https://www.alphavantage.co/query?function=TIME_SERIES_MONTHLY&symbol=IBM&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_MONTHLY&symbol=TSCO.LON&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_MONTHLY&symbol=IBM&apikey=demo&datatype=csv
```

Same code patterns as above.

---

### TIME_SERIES_MONTHLY_ADJUSTED

Returns monthly adjusted time series (last trading day of each month, monthly OHLC, monthly adjusted close, monthly volume, monthly dividend) of the equity specified, 20+ years.

#### API Parameters

- **Required `function`**: `TIME_SERIES_MONTHLY_ADJUSTED`
- **Required `symbol`**
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

#### Examples

```
https://www.alphavantage.co/query?function=TIME_SERIES_MONTHLY_ADJUSTED&symbol=IBM&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_MONTHLY_ADJUSTED&symbol=TSCO.LON&apikey=demo
https://www.alphavantage.co/query?function=TIME_SERIES_MONTHLY_ADJUSTED&symbol=IBM&apikey=demo&datatype=csv
```

Same code patterns as above.

---

### GLOBAL_QUOTE (Quote Endpoint)

**Trending**

Returns the latest price and volume information for a single ticker. For bulk quotes, see [REALTIME_BULK_QUOTES](#realtime_bulk_quotes).

#### API Parameters

- **Required `function`**: `GLOBAL_QUOTE`
- **Required `symbol`**
- Optional `datatype`: `json` (default) or `csv`.
- Optional `entitlement`: `realtime` or `delayed`.
- **Required `apikey`**

#### Examples

```
https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=IBM&apikey=demo
https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=300135.SHZ&apikey=demo
https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=IBM&apikey=demo&datatype=csv
```

> Default updates at end of trading day. Premium plan unlocks realtime/15-min delayed US data.

Same Python/NodeJS/PHP/C# patterns as above.

---

### REALTIME_BULK_QUOTES

**Premium**

Returns realtime quotes for US-traded symbols in bulk, accepting up to 100 symbols per API request, covering both regular and extended trading hours.

#### API Parameters

- **Required `function`**: `REALTIME_BULK_QUOTES`
- **Required `symbol`**: Up to 100 symbols separated by comma (e.g., `MSFT,AAPL,IBM`). Excess symbols are ignored.
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

#### Example

```
https://www.alphavantage.co/query?function=REALTIME_BULK_QUOTES&symbol=MSFT,AAPL,IBM&apikey=demo
```

> Premium API function. Requires "Realtime US Market Data" plan.

---

### SYMBOL_SEARCH (Search Endpoint)

**Utility**

Returns the best-matching symbols and market information based on keywords. Includes match scores for filtering and ranking.

#### API Parameters

- **Required `function`**: `SYMBOL_SEARCH`
- **Required `keywords`**: e.g., `keywords=microsoft`
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

#### Examples

```
https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords=tesco&apikey=demo
https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords=tencent&apikey=demo
https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords=BA&apikey=demo
https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords=SAIC&apikey=demo
https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords=BA&apikey=demo&datatype=csv
```

---

### MARKET_STATUS (Global Market Open & Close Status)

**Utility**

Returns the current market status (open vs. closed) of major trading venues for equities, forex, and cryptocurrencies worldwide.

#### API Parameters

- **Required `function`**: `MARKET_STATUS`
- **Required `apikey`**

#### Example

```
https://www.alphavantage.co/query?function=MARKET_STATUS&apikey=demo
```

---

## Index Data APIs (Premium)

This suite provides decades of history for 200+ major indices in daily, weekly, and monthly resolutions.

### Common Parameters (all index endpoints below)

- **Required `function`**: `INDEX_DATA`
- **Required `symbol`**: see each index below
- **Required `interval`**: `daily`, `weekly`, `monthly`
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

> All Index Data endpoints are premium.

---

### Dow Jones Industrial Average (DJI)

`symbol=DJI`

```
https://www.alphavantage.co/query?function=INDEX_DATA&symbol=DJI&interval=weekly&apikey=demo
https://www.alphavantage.co/query?function=INDEX_DATA&symbol=DJI&interval=weekly&apikey=demo&datatype=csv
```

#### Python

```python
import requests
url = 'https://www.alphavantage.co/query?function=INDEX_DATA&symbol=DJI&interval=weekly&apikey=demo'
r = requests.get(url)
print(r.json())
```

#### NodeJS

```javascript
var request = require('request');
var url = 'https://www.alphavantage.co/query?function=INDEX_DATA&symbol=DJI&interval=weekly&apikey=demo';
request.get({url: url, json: true, headers: {'User-Agent': 'request'}}, (err, res, data) => {
    if (err) console.log('Error:', err);
    else console.log(data);
});
```

#### PHP

```php
<?php
$json = file_get_contents('https://www.alphavantage.co/query?function=INDEX_DATA&symbol=DJI&interval=weekly&apikey=demo');
print_r(json_decode($json,true));
```

#### C#/.NET

Same pattern as previous endpoints with `symbol=DJI&interval=weekly`.

---

### S&P 500 (SPX)

`symbol=SPX`

```
https://www.alphavantage.co/query?function=INDEX_DATA&symbol=SPX&interval=weekly&apikey=demo
https://www.alphavantage.co/query?function=INDEX_DATA&symbol=SPX&interval=weekly&apikey=demo&datatype=csv
```

Same code patterns as DJI above.

---

### NASDAQ Composite (COMP)

`symbol=COMP`

```
https://www.alphavantage.co/query?function=INDEX_DATA&symbol=COMP&interval=weekly&apikey=demo
https://www.alphavantage.co/query?function=INDEX_DATA&symbol=COMP&interval=weekly&apikey=demo&datatype=csv
```

---

### NASDAQ 100 (NDX)

`symbol=NDX`

```
https://www.alphavantage.co/query?function=INDEX_DATA&symbol=NDX&interval=weekly&apikey=demo
https://www.alphavantage.co/query?function=INDEX_DATA&symbol=NDX&interval=weekly&apikey=demo&datatype=csv
```

---

### Cboe Volatility Index (VIX)

`symbol=VIX`

```
https://www.alphavantage.co/query?function=INDEX_DATA&symbol=VIX&interval=weekly&apikey=demo
https://www.alphavantage.co/query?function=INDEX_DATA&symbol=VIX&interval=weekly&apikey=demo&datatype=csv
```

---

### Russell 2000 (RUT)

`symbol=RUT`

```
https://www.alphavantage.co/query?function=INDEX_DATA&symbol=RUT&interval=weekly&apikey=demo
https://www.alphavantage.co/query?function=INDEX_DATA&symbol=RUT&interval=weekly&apikey=demo&datatype=csv
```

---

### Other Major Indices

200+ major market indices supported. See [Index Catalog](#index-catalog) for the full list.

```
https://www.alphavantage.co/query?function=INDEX_DATA&symbol=DJS&interval=weekly&apikey=demo
https://www.alphavantage.co/query?function=INDEX_DATA&symbol=DJS&interval=weekly&apikey=demo&datatype=csv
```

---

### Index Catalog

**Utility**

Returns the full list of supported index symbols and their long-form names.

#### API Parameters

- **Required `function`**: `INDEX_CATALOG`
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=INDEX_CATALOG&apikey=demo
https://www.alphavantage.co/query?function=INDEX_CATALOG&apikey=demo&datatype=csv
```

---

## Options Data APIs

Realtime and historical US options data spanning 15+ years with full market coverage. Bullish/bearish signals such as put-call ratios are also provided.

---

### REALTIME_OPTIONS

**Premium / Trending**

Returns realtime US options data with full market coverage. Sorted by expiration date, then by strike price ascending.

#### API Parameters

- **Required `function`**: `REALTIME_OPTIONS`
- **Required `symbol`**
- Optional `require_greeks`: Default `false`. Set `true` for greeks & IVs.
- Optional `contract`: Specific contract ID. Omit for entire chain.
- Optional `expiration`: YYYY-MM-DD; must be on/after today.
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

#### Examples

```
https://www.alphavantage.co/query?function=REALTIME_OPTIONS&symbol=IBM&apikey=demo
https://www.alphavantage.co/query?function=REALTIME_OPTIONS&symbol=IBM&require_greeks=true&apikey=demo
https://www.alphavantage.co/query?function=REALTIME_OPTIONS&symbol=IBM&require_greeks=true&contract=IBM270115C00390000&apikey=demo
```

> Premium. Requires 600 or 1200 req/min plan.

---

### REALTIME_PUT_CALL_RATIO

Returns realtime put-call ratios for both the entire option chain and specific expiration dates. Lower ratio (≤0.6) typically signals bullish sentiment; higher (≥1.0) bearish. Often used as a contrarian indicator at extremes.

#### API Parameters

- **Required `function`**: `REALTIME_PUT_CALL_RATIO`
- **Required `symbol`**
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=REALTIME_PUT_CALL_RATIO&symbol=IBM&apikey=demo
```

---

### REALTIME_VOLUME_OPEN_INTEREST_RATIO

Returns realtime volume-to-open-interest ratios within an option chain. High ratio suggests heavy trading activity relative to existing positions; low ratio implies positions being held rather than actively traded.

#### API Parameters

- **Required `function`**: `REALTIME_VOLUME_OPEN_INTEREST_RATIO`
- **Required `symbol`**
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=REALTIME_VOLUME_OPEN_INTEREST_RATIO&symbol=NVDA&apikey=demo
```

---

### HISTORICAL_OPTIONS

**Premium / Trending**

Returns the full historical options chain for a specific symbol on a specific date, covering 15+ years (since 2008-01-01). IV and Greeks (delta, gamma, theta, vega, rho) are returned.

#### API Parameters

- **Required `function`**: `HISTORICAL_OPTIONS`
- **Required `symbol`**
- Optional `date`: YYYY-MM-DD; defaults to previous trading session. Any date after 2008-01-01.
- Optional `contract`: Specific contract ID. Omit for entire chain.
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=HISTORICAL_OPTIONS&symbol=IBM&apikey=demo
https://www.alphavantage.co/query?function=HISTORICAL_OPTIONS&symbol=IBM&date=2017-11-15&apikey=demo
https://www.alphavantage.co/query?function=HISTORICAL_OPTIONS&symbol=IBM&date=2017-11-15&apikey=demo&datatype=csv
```

> Premium API function.

---

### HISTORICAL_PUT_CALL_RATIO

Returns historical put-call ratios. Same interpretation rules as the realtime version.

#### API Parameters

- **Required `function`**: `HISTORICAL_PUT_CALL_RATIO`
- **Required `symbol`**
- Optional `date`: YYYY-MM-DD; any date after 2008-01-01.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=HISTORICAL_PUT_CALL_RATIO&symbol=IBM&date=2026-03-12&apikey=demo
```

---

### HISTORICAL_VOLUME_OPEN_INTEREST_RATIO

Returns historical volume-to-open-interest ratios. Same interpretation as realtime.

#### API Parameters

- **Required `function`**: `HISTORICAL_VOLUME_OPEN_INTEREST_RATIO`
- **Required `symbol`**
- Optional `date`: YYYY-MM-DD; any date after 2008-01-01.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=HISTORICAL_VOLUME_OPEN_INTEREST_RATIO&symbol=NVDA&date=2026-04-06&apikey=demo
```

---

## Alpha Intelligence™

Advanced market intelligence built with AI, machine learning, and quantitative finance.

---

### NEWS_SENTIMENT (Market News & Sentiment)

**Trending**

Live and historical market news & sentiment data from premier news outlets, covering stocks, crypto, forex, and topics like fiscal policy, M&A, IPOs, etc.

#### API Parameters

- **Required `function`**: `NEWS_SENTIMENT`
- Optional `tickers`: e.g., `tickers=IBM`; multiple comma-separated (e.g., `COIN,CRYPTO:BTC,FOREX:USD`)
- Optional `topics`: comma-separated. Supported:
  - `blockchain`, `earnings`, `ipo`, `mergers_and_acquisitions`, `financial_markets`
  - `economy_fiscal`, `economy_monetary`, `economy_macro`
  - `energy_transportation`, `finance`, `life_sciences`, `manufacturing`, `real_estate`, `retail_wholesale`, `technology`
- Optional `time_from` and `time_to`: YYYYMMDDTHHMM format (e.g., `time_from=20220410T0130`)
- Optional `sort`: `LATEST` (default), `EARLIEST`, or `RELEVANCE`
- Optional `limit`: Default `50`, max `1000`
- **Required `apikey`**

#### Examples

```
https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers=AAPL&apikey=demo
https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers=COIN,CRYPTO:BTC,FOREX:USD&time_from=20220410T0130&limit=1000&apikey=demo
```

#### Python

```python
import requests
url = 'https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers=AAPL&apikey=demo'
r = requests.get(url)
print(r.json())
```

(NodeJS/PHP/C# follow the same patterns as earlier endpoints.)

---

### EARNINGS_CALL_TRANSCRIPT

**Trending**

Returns the earnings call transcript for a given company in a specific quarter, covering 15+ years of history with LLM-based sentiment signals.

#### API Parameters

- **Required `function`**: `EARNINGS_CALL_TRANSCRIPT`
- **Required `symbol`**
- **Required `quarter`**: YYYYQM format (e.g., `2024Q1`). Any quarter since 2010Q1.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=EARNINGS_CALL_TRANSCRIPT&symbol=IBM&quarter=2024Q1&apikey=demo
```

---

### TOP_GAINERS_LOSERS

Returns top 20 gainers, losers, and most active traded tickers in the US market.

#### API Parameters

- **Required `function`**: `TOP_GAINERS_LOSERS`
- Optional `entitlement`: `realtime` or `delayed`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=TOP_GAINERS_LOSERS&apikey=demo
```

> Default end-of-day. Premium plan unlocks realtime/delayed.

---

### INSIDER_TRANSACTIONS

**Trending**

Latest and historical insider transactions made by key stakeholders (founders, executives, board, etc.).

#### API Parameters

- **Required `function`**: `INSIDER_TRANSACTIONS`
- **Required `symbol`**
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=INSIDER_TRANSACTIONS&symbol=IBM&apikey=demo
```

---

### INSTITUTIONAL_HOLDINGS

Returns institutional ownership and holdings information.

#### API Parameters

- **Required `function`**: `INSTITUTIONAL_HOLDINGS`
- **Required `symbol`**
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=INSTITUTIONAL_HOLDINGS&symbol=IBM&apikey=demo
```

---

### ANALYTICS_FIXED_WINDOW

Returns advanced analytics metrics (total return, variance, autocorrelation, etc.) over a fixed temporal window.

#### API Parameters

- **Required `function`**: `ANALYTICS_FIXED_WINDOW`
- **Required `SYMBOLS`**: Comma-separated. Free: 5 max. Premium: 50 max.
- **Required `RANGE`**: Either keywords or two-bound dates.
  - Keywords: `full`, `{N}day`, `{N}week`, `{N}month`, `{N}year`
  - Intraday also: `{N}minute`, `{N}hour`
  - Bounded: `RANGE=2023-07-01&RANGE=2023-08-31` (or with minute precision: `2020-12-01T00:04:00`)
  - Full month: `2020-12`. Single intraday day: `2020-12-06`
- Optional `OHLC`: `close` (default), `open`, `high`, `low`
- **Required `INTERVAL`**: `1min`, `5min`, `15min`, `30min`, `60min`, `DAILY`, `WEEKLY`, `MONTHLY`
- **Required `CALCULATIONS`**: comma-separated metrics:
  - `MIN`, `MAX`, `MEAN`, `MEDIAN`, `CUMULATIVE_RETURN`
  - `VARIANCE` (or `VARIANCE(annualized=True)`)
  - `STDDEV` (or `STDDEV(annualized=True)`)
  - `MAX_DRAWDOWN`
  - `HISTOGRAM` (default bins=10; e.g., `HISTOGRAM(bins=20)`)
  - `AUTOCORRELATION` (default lag=1; e.g., `AUTOCORRELATION(lag=2)`)
  - `COVARIANCE` (or annualized)
  - `CORRELATION` (PEARSON default; or `CORRELATION(method=KENDALL)` / `CORRELATION(method=SPEARMAN)`)
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=ANALYTICS_FIXED_WINDOW&SYMBOLS=AAPL,MSFT,IBM&RANGE=2023-07-01&RANGE=2023-08-31&INTERVAL=DAILY&OHLC=close&CALCULATIONS=MEAN,STDDEV,CORRELATION&apikey=demo
```

Note: This endpoint uses the `alphavantageapi.co/timeseries/analytics` host in code samples.

#### Python

```python
import requests
url = 'https://alphavantageapi.co/timeseries/analytics?SYMBOLS=AAPL,MSFT,IBM&RANGE=2023-07-01&RANGE=2023-08-31&INTERVAL=DAILY&OHLC=close&CALCULATIONS=MEAN,STDDEV,CORRELATION&apikey=demo'
r = requests.get(url)
print(r.json())
```

---

### ANALYTICS_SLIDING_WINDOW

**Trending**

Same metrics as fixed window, but over sliding time windows (e.g., moving variance over 5 years with a 100-point window).

#### API Parameters

- **Required `function`**: `ANALYTICS_SLIDING_WINDOW`
- **Required `SYMBOLS`**: Free: 5 max. Premium: 50 max.
- **Required `RANGE`**: same options as fixed window.
- Optional `OHLC`: `close` default.
- **Required `INTERVAL`**: same options as fixed window.
- **Required `WINDOW_SIZE`**: integer, lower bound 10. Larger recommended for statistical significance.
- **Required `CALCULATIONS`**: Free: 1 metric. Premium: multiple. Available:
  - `MEAN`, `MEDIAN`, `CUMULATIVE_RETURN`
  - `VARIANCE` (or annualized), `STDDEV` (or annualized)
  - `COVARIANCE` (or annualized)
  - `CORRELATION` (PEARSON default; KENDALL or SPEARMAN)
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=ANALYTICS_SLIDING_WINDOW&SYMBOLS=AAPL,IBM&RANGE=2month&INTERVAL=DAILY&OHLC=close&WINDOW_SIZE=20&CALCULATIONS=MEAN,STDDEV(annualized=True)&apikey=demo
```

Code samples use `alphavantageapi.co/timeseries/running_analytics` host.

---

## Fundamental Data

Various temporal dimensions covering key financial metrics, income statements, balance sheets, cash flow, and more.

---

### OVERVIEW (Company Overview)

**Trending**

Returns company information, financial ratios, and key metrics. Refreshed on the same day a company reports earnings.

#### API Parameters

- **Required `function`**: `OVERVIEW`
- **Required `symbol`**
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=OVERVIEW&symbol=IBM&apikey=demo
```

---

### ETF_PROFILE

Returns key ETF metrics (net assets, expense ratio, turnover) along with holdings and allocations by asset type and sector.

#### API Parameters

- **Required `function`**: `ETF_PROFILE`
- **Required `symbol`**: e.g., `QQQ`
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=ETF_PROFILE&symbol=QQQ&apikey=demo
```

---

### DIVIDENDS

Returns historical and future (declared) dividend distributions.

#### API Parameters

- **Required `function`**: `DIVIDENDS`
- **Required `symbol`**
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=DIVIDENDS&symbol=IBM&apikey=demo
```

---

### SPLITS

Returns historical split events.

#### API Parameters

- **Required `function`**: `SPLITS`
- **Required `symbol`**
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=SPLITS&symbol=IBM&apikey=demo
```

---

### INCOME_STATEMENT

Annual and quarterly income statements, normalized to GAAP/IFRS taxonomies.

#### API Parameters

- **Required `function`**: `INCOME_STATEMENT`
- **Required `symbol`**
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=INCOME_STATEMENT&symbol=IBM&apikey=demo
```

---

### BALANCE_SHEET

Annual and quarterly balance sheets, normalized to GAAP/IFRS taxonomies.

#### API Parameters

- **Required `function`**: `BALANCE_SHEET`
- **Required `symbol`**
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=BALANCE_SHEET&symbol=IBM&apikey=demo
```

---

### CASH_FLOW

Annual and quarterly cash flow, normalized to GAAP/IFRS taxonomies.

#### API Parameters

- **Required `function`**: `CASH_FLOW`
- **Required `symbol`**
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=CASH_FLOW&symbol=IBM&apikey=demo
```

---

### SHARES_OUTSTANDING

Quarterly numbers of shares outstanding (diluted and basic).

#### API Parameters

- **Required `function`**: `SHARES_OUTSTANDING`
- **Required `symbol`**
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=SHARES_OUTSTANDING&symbol=MSFT&apikey=demo
```

---

### EARNINGS

Annual and quarterly earnings (EPS). Quarterly data includes analyst estimates and surprise metrics.

#### API Parameters

- **Required `function`**: `EARNINGS`
- **Required `symbol`**
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=EARNINGS&symbol=IBM&apikey=demo
```

---

### EARNINGS_ESTIMATES

**Trending**

Annual and quarterly EPS and revenue estimates with analyst count and revision history.

#### API Parameters

- **Required `function`**: `EARNINGS_ESTIMATES`
- **Required `symbol`**
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=EARNINGS_ESTIMATES&symbol=IBM&apikey=demo
```

---

### LISTING_STATUS

**Utility**

List of active or delisted US stocks and ETFs, either as of latest trading day or at a specific historical date. Useful for asset lifecycle and survivorship research.

#### API Parameters

- **Required `function`**: `LISTING_STATUS`
- Optional `date`: YYYY-MM-DD; any date after 2010-01-01.
- Optional `state`: `active` (default) or `delisted`.
- **Required `apikey`**

> CSV format only.

```
https://www.alphavantage.co/query?function=LISTING_STATUS&apikey=demo
https://www.alphavantage.co/query?function=LISTING_STATUS&date=2014-07-10&state=delisted&apikey=demo
```

#### Python

```python
import csv
import requests

CSV_URL = 'https://www.alphavantage.co/query?function=LISTING_STATUS&apikey=demo'

with requests.Session() as s:
    download = s.get(CSV_URL)
    decoded_content = download.content.decode('utf-8')
    cr = csv.reader(decoded_content.splitlines(), delimiter=',')
    my_list = list(cr)
    for row in my_list:
        print(row)
```

#### NodeJS

```javascript
const {StringStream} = require("scramjet");
const request = require("request");

request.get("https://www.alphavantage.co/query?function=LISTING_STATUS&apikey=demo")
    .pipe(new StringStream())
    .CSVParse()
    .consume(object => console.log("Row:", object))
    .then(() => console.log("success"));
```

#### PHP

```php
<?php
$data = file_get_contents("https://www.alphavantage.co/query?function=LISTING_STATUS&apikey=demo");
$rows = explode("\n",$data);
$s = array();
foreach($rows as $row) {
    $s[] = str_getcsv($row);
    print_r($s);
}
```

#### C#/.NET

```csharp
using CsvHelper;
using System;
using System.Globalization;
using System.IO;
using System.Net;

string QUERY_URL = "https://www.alphavantage.co/query?function=LISTING_STATUS&apikey=demo";
Uri queryUri = new Uri(QUERY_URL);
CultureInfo culture = CultureInfo.CreateSpecificCulture("en-US");
using (WebClient client = new WebClient())
{
    using (MemoryStream stream = new MemoryStream(client.DownloadDataTaskAsync(queryUri).Result))
    {
        stream.Position = 0;
        using (StreamReader reader = new StreamReader(stream))
        using (CsvReader csv = new CsvReader(reader, CultureInfo.InvariantCulture))
        {
            csv.Read();
            csv.ReadHeader();
            Console.WriteLine(string.Join("\t", csv.HeaderRecord));
            while (csv.Read())
                Console.WriteLine(string.Join("\t", csv.Parser.Record));
        }
    }
}
```

---

### EARNINGS_CALENDAR

List of company earnings expected in the next 3, 6, or 12 months.

#### API Parameters

- **Required `function`**: `EARNINGS_CALENDAR`
- Optional `symbol`: filter by ticker.
- Optional `horizon`: `3month` (default), `6month`, or `12month`.
- **Required `apikey`**

> CSV format only.

```
https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&horizon=3month&apikey=demo
https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&symbol=IBM&horizon=12month&apikey=demo
```

Code patterns: same as LISTING_STATUS (CSV).

---

### IPO_CALENDAR

List of IPOs expected in the next 3 months.

#### API Parameters

- **Required `function`**: `IPO_CALENDAR`
- **Required `apikey`**

> CSV format only.

```
https://www.alphavantage.co/query?function=IPO_CALENDAR&apikey=demo
```

Code patterns: same as LISTING_STATUS (CSV).

---

## Foreign Exchange Rates (FX)

Wide range of data feeds for realtime and historical forex (FX) rates.

---

### CURRENCY_EXCHANGE_RATE (FX)

**Trending**

Returns realtime exchange rate for a pair of fiat currencies. (Also accepts crypto. For gold/silver spot prices, see commodities.)

#### API Parameters

- **Required `function`**: `CURRENCY_EXCHANGE_RATE`
- **Required `from_currency`**: physical or crypto code (e.g., `USD`, `BTC`)
- **Required `to_currency`**: physical or crypto code
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=USD&to_currency=JPY&apikey=demo
https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=BTC&to_currency=EUR&apikey=demo
```

---

### FX_INTRADAY

**Premium / Trending**

Intraday time series (timestamp, OHLC) of the FX currency pair specified, updated realtime.

#### API Parameters

- **Required `function`**: `FX_INTRADAY`
- **Required `from_symbol`**: e.g., `EUR`
- **Required `to_symbol`**: e.g., `USD`
- **Required `interval`**: `1min`, `5min`, `15min`, `30min`, `60min`
- Optional `outputsize`: `compact` (default) or `full`.
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=FX_INTRADAY&from_symbol=EUR&to_symbol=USD&interval=5min&apikey=demo
https://www.alphavantage.co/query?function=FX_INTRADAY&from_symbol=EUR&to_symbol=USD&interval=5min&outputsize=full&apikey=demo
https://www.alphavantage.co/query?function=FX_INTRADAY&from_symbol=EUR&to_symbol=USD&interval=5min&apikey=demo&datatype=csv
```

> Premium API function.

---

### FX_DAILY

Daily time series (timestamp, OHLC) of the FX currency pair specified, updated realtime.

#### API Parameters

- **Required `function`**: `FX_DAILY`
- **Required `from_symbol`** and **`to_symbol`**
- Optional `outputsize`: `compact` (default) or `full`.
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=FX_DAILY&from_symbol=EUR&to_symbol=USD&apikey=demo
https://www.alphavantage.co/query?function=FX_DAILY&from_symbol=EUR&to_symbol=USD&outputsize=full&apikey=demo
https://www.alphavantage.co/query?function=FX_DAILY&from_symbol=EUR&to_symbol=USD&apikey=demo&datatype=csv
```

---

### FX_WEEKLY

Weekly time series (timestamp, OHLC). Latest data point includes current week (partial), updated realtime.

#### API Parameters

- **Required `function`**: `FX_WEEKLY`
- **Required `from_symbol`** and **`to_symbol`**
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=FX_WEEKLY&from_symbol=EUR&to_symbol=USD&apikey=demo
https://www.alphavantage.co/query?function=FX_WEEKLY&from_symbol=EUR&to_symbol=USD&apikey=demo&datatype=csv
```

---

### FX_MONTHLY

Monthly time series (timestamp, OHLC). Latest data point includes current month (partial), updated realtime.

#### API Parameters

- **Required `function`**: `FX_MONTHLY`
- **Required `from_symbol`** and **`to_symbol`**
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=FX_MONTHLY&from_symbol=EUR&to_symbol=USD&apikey=demo
https://www.alphavantage.co/query?function=FX_MONTHLY&from_symbol=EUR&to_symbol=USD&apikey=demo&datatype=csv
```

---

## Digital & Crypto Currencies

Data feeds for digital and crypto currencies such as Bitcoin.

---

### CURRENCY_EXCHANGE_RATE (Crypto)

**Trending**

Same endpoint as FX version. Returns realtime exchange rate for any pair of crypto or physical currency.

#### API Parameters

- **Required `function`**: `CURRENCY_EXCHANGE_RATE`
- **Required `from_currency`** and **`to_currency`**: physical or crypto.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=BTC&to_currency=EUR&apikey=demo
https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=USD&to_currency=JPY&apikey=demo
```

---

### CRYPTO_INTRADAY

**Premium / Trending**

Intraday time series (timestamp, OHLCV) of the cryptocurrency specified, updated realtime.

#### API Parameters

- **Required `function`**: `CRYPTO_INTRADAY`
- **Required `symbol`**: crypto from-currency (e.g., `ETH`)
- **Required `market`**: to-currency (e.g., `USD`)
- **Required `interval`**: `1min`, `5min`, `15min`, `30min`, `60min`
- Optional `outputsize`: `compact` (default) or `full`.
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=CRYPTO_INTRADAY&symbol=ETH&market=USD&interval=5min&apikey=demo
https://www.alphavantage.co/query?function=CRYPTO_INTRADAY&symbol=ETH&market=USD&interval=5min&outputsize=full&apikey=demo
https://www.alphavantage.co/query?function=CRYPTO_INTRADAY&symbol=ETH&market=USD&interval=5min&apikey=demo&datatype=csv
```

> Premium API function.

---

### DIGITAL_CURRENCY_DAILY

Daily historical time series for a cryptocurrency traded on a specific market. Refreshed at midnight UTC. Prices and volumes quoted in market-specific currency and USD.

#### API Parameters

- **Required `function`**: `DIGITAL_CURRENCY_DAILY`
- **Required `symbol`** (e.g., `BTC`) and **`market`** (e.g., `EUR`)
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=DIGITAL_CURRENCY_DAILY&symbol=BTC&market=EUR&apikey=demo
https://www.alphavantage.co/query?function=DIGITAL_CURRENCY_DAILY&symbol=BTC&market=EUR&apikey=demo&datatype=csv
```

---

### DIGITAL_CURRENCY_WEEKLY

**Trending**

Weekly historical time series for crypto. Same parameters and behavior as DAILY.

```
https://www.alphavantage.co/query?function=DIGITAL_CURRENCY_WEEKLY&symbol=BTC&market=EUR&apikey=demo
https://www.alphavantage.co/query?function=DIGITAL_CURRENCY_WEEKLY&symbol=BTC&market=EUR&apikey=demo&datatype=csv
```

---

### DIGITAL_CURRENCY_MONTHLY

**Trending**

Monthly historical time series for crypto. Same parameters as DAILY.

```
https://www.alphavantage.co/query?function=DIGITAL_CURRENCY_MONTHLY&symbol=BTC&market=EUR&apikey=demo
https://www.alphavantage.co/query?function=DIGITAL_CURRENCY_MONTHLY&symbol=BTC&market=EUR&apikey=demo&datatype=csv
```

---

## Commodities

Price data for major commodities (gold, silver, crude oil, natural gas, copper, wheat, etc.) across daily, weekly, monthly, quarterly, and annual horizons.

---

### GOLD_SILVER_SPOT

**Trending**

Live spot prices for gold and silver.

#### API Parameters

- **Required `function`**: `GOLD_SILVER_SPOT`
- **Required `symbol`**: `GOLD`/`XAU` or `SILVER`/`XAG`
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=GOLD_SILVER_SPOT&symbol=SILVER&apikey=demo
```

---

### GOLD_SILVER_HISTORY

**Trending**

Historical gold and silver prices in daily, weekly, and monthly horizons.

#### API Parameters

- **Required `function`**: `GOLD_SILVER_HISTORY`
- **Required `symbol`**: `GOLD`/`XAU` or `SILVER`/`XAG`
- **Required `interval`**: `daily`, `weekly`, `monthly`
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=GOLD_SILVER_HISTORY&symbol=SILVER&interval=daily&apikey=demo
```

---

### WTI (Crude Oil)

**Trending**

West Texas Intermediate crude oil prices in daily, weekly, and monthly horizons. Source: U.S. EIA via FRED.

#### API Parameters

- **Required `function`**: `WTI`
- Optional `interval`: `daily`, `weekly`, `monthly` (default `monthly`)
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=WTI&interval=monthly&apikey=demo
```

---

### BRENT (Crude Oil)

**Trending**

Brent (Europe) crude oil prices in daily/weekly/monthly. Source: U.S. EIA via FRED.

#### API Parameters

- **Required `function`**: `BRENT`
- Optional `interval`: `daily`, `weekly`, `monthly` (default `monthly`)
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=BRENT&interval=monthly&apikey=demo
```

---

### NATURAL_GAS

Henry Hub natural gas spot prices, daily/weekly/monthly. Source: U.S. EIA via FRED.

#### API Parameters

- **Required `function`**: `NATURAL_GAS`
- Optional `interval`: `daily`, `weekly`, `monthly` (default `monthly`)
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=NATURAL_GAS&interval=monthly&apikey=demo
```

---

### COPPER

Global price of copper, monthly/quarterly/annual. Source: IMF via FRED.

```
https://www.alphavantage.co/query?function=COPPER&interval=monthly&apikey=demo
```

Optional `interval`: `monthly` (default), `quarterly`, `annual`. Optional `datatype`: `json`/`csv`.

---

### ALUMINUM

Global price of aluminum, monthly/quarterly/annual. Source: IMF via FRED.

```
https://www.alphavantage.co/query?function=ALUMINUM&interval=monthly&apikey=demo
```

Same parameter pattern as COPPER.

---

### WHEAT

Global price of wheat, monthly/quarterly/annual. Source: IMF via FRED.

```
https://www.alphavantage.co/query?function=WHEAT&interval=monthly&apikey=demo
```

---

### CORN

Global price of corn, monthly/quarterly/annual. Source: IMF via FRED.

```
https://www.alphavantage.co/query?function=CORN&interval=monthly&apikey=demo
```

---

### COTTON

Global price of cotton, monthly/quarterly/annual. Source: IMF via FRED.

```
https://www.alphavantage.co/query?function=COTTON&interval=monthly&apikey=demo
```

---

### SUGAR

Global price of sugar (No. 11, World), monthly/quarterly/annual. Source: IMF via FRED.

```
https://www.alphavantage.co/query?function=SUGAR&interval=monthly&apikey=demo
```

---

### COFFEE

Global price of coffee (Other Mild Arabica), monthly/quarterly/annual. Source: IMF via FRED.

```
https://www.alphavantage.co/query?function=COFFEE&interval=monthly&apikey=demo
```

---

### ALL_COMMODITIES

Global Price Index of All Commodities, monthly/quarterly/annual. Source: IMF via FRED.

```
https://www.alphavantage.co/query?function=ALL_COMMODITIES&interval=monthly&apikey=demo
```

---

## Economic Indicators

Key US economic indicators frequently used for investment strategy and application development.

---

### REAL_GDP

**Trending**

Annual and quarterly Real GDP of the United States. Source: U.S. BEA via FRED.

#### API Parameters

- **Required `function`**: `REAL_GDP`
- Optional `interval`: `quarterly`, `annual` (default `annual`)
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=REAL_GDP&interval=annual&apikey=demo
```

---

### REAL_GDP_PER_CAPITA

Quarterly Real GDP per Capita of the United States. Source: U.S. BEA via FRED.

#### API Parameters

- **Required `function`**: `REAL_GDP_PER_CAPITA`
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=REAL_GDP_PER_CAPITA&apikey=demo
```

---

### TREASURY_YIELD

**Trending**

Daily/weekly/monthly US treasury yield by maturity. Source: Federal Reserve via FRED.

#### API Parameters

- **Required `function`**: `TREASURY_YIELD`
- Optional `interval`: `daily`, `weekly`, `monthly` (default `monthly`)
- Optional `maturity`: `3month`, `2year`, `5year`, `7year`, `10year` (default), `30year`
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=TREASURY_YIELD&interval=monthly&maturity=10year&apikey=demo
```

---

### FEDERAL_FUNDS_RATE

Daily/weekly/monthly federal funds (interest) rate. Source: Federal Reserve via FRED.

#### API Parameters

- **Required `function`**: `FEDERAL_FUNDS_RATE`
- Optional `interval`: `daily`, `weekly`, `monthly` (default `monthly`)
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=FEDERAL_FUNDS_RATE&interval=monthly&apikey=demo
```

---

### CPI

Monthly and semiannual Consumer Price Index. Source: U.S. BLS via FRED.

#### API Parameters

- **Required `function`**: `CPI`
- Optional `interval`: `monthly` (default), `semiannual`
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=CPI&interval=monthly&apikey=demo
```

---

### INFLATION

Annual inflation rates (consumer prices) for the United States. Source: World Bank via FRED.

#### API Parameters

- **Required `function`**: `INFLATION`
- Optional `datatype`: `json` (default) or `csv`.
- **Required `apikey`**

```
https://www.alphavantage.co/query?function=INFLATION&apikey=demo
```

---

### RETAIL_SALES

Monthly Advance Retail Sales: Retail Trade. Source: U.S. Census Bureau via FRED.

```
https://www.alphavantage.co/query?function=RETAIL_SALES&apikey=demo
```

Optional `datatype`: `json`/`csv`.

---

### DURABLES

Monthly manufacturers' new orders of durable goods. Source: U.S. Census Bureau via FRED.

```
https://www.alphavantage.co/query?function=DURABLES&apikey=demo
```

---

### UNEMPLOYMENT

Monthly unemployment rate. Source: U.S. BLS via FRED.

```
https://www.alphavantage.co/query?function=UNEMPLOYMENT&apikey=demo
```

---

### NONFARM_PAYROLL

Monthly Total Nonfarm Payroll. Source: U.S. BLS via FRED.

```
https://www.alphavantage.co/query?function=NONFARM_PAYROLL&apikey=demo
```

---

## Technical Indicators

Technical indicator APIs for a given equity or currency exchange pair, derived from underlying time series and forex data. All indicators are calculated from adjusted time series data to eliminate artificial perturbations from historical splits and dividends.

> **Common parameters across most indicators below**:
> - **Required `function`**: indicator name
> - **Required `symbol`**
> - **Required `interval`**: `1min`, `5min`, `15min`, `30min`, `60min`, `daily`, `weekly`, `monthly`
> - Optional `month`: YYYY-MM format
> - Optional `datatype`: `json` (default) or `csv`
> - Optional `entitlement`: `realtime` or `delayed`
> - **Required `apikey`**
>
> Many also require `time_period` and/or `series_type` (`close`, `open`, `high`, `low`).

---

### SMA

**Trending** — Simple Moving Average.

Required: `function=SMA`, `symbol`, `interval`, `time_period`, `series_type`, `apikey`.

```
https://www.alphavantage.co/query?function=SMA&symbol=IBM&interval=weekly&time_period=10&series_type=open&apikey=demo
https://www.alphavantage.co/query?function=SMA&symbol=USDEUR&interval=weekly&time_period=10&series_type=open&apikey=demo
```

#### Python

```python
import requests
url = 'https://www.alphavantage.co/query?function=SMA&symbol=IBM&interval=weekly&time_period=10&series_type=open&apikey=demo'
r = requests.get(url)
print(r.json())
```

(NodeJS/PHP/C# follow the same patterns as earlier endpoints.)

---

### EMA

**Trending** — Exponential Moving Average.

Required: `function=EMA`, `symbol`, `interval`, `time_period`, `series_type`, `apikey`.

```
https://www.alphavantage.co/query?function=EMA&symbol=IBM&interval=weekly&time_period=10&series_type=open&apikey=demo
https://www.alphavantage.co/query?function=EMA&symbol=USDEUR&interval=weekly&time_period=10&series_type=open&apikey=demo
```

---

### WMA

Weighted Moving Average.

Required: `function=WMA`, `symbol`, `interval`, `time_period`, `series_type`, `apikey`.

```
https://www.alphavantage.co/query?function=WMA&symbol=IBM&interval=weekly&time_period=10&series_type=open&apikey=demo
```

---

### DEMA

Double Exponential Moving Average.

Required: `function=DEMA`, `symbol`, `interval`, `time_period`, `series_type`, `apikey`.

```
https://www.alphavantage.co/query?function=DEMA&symbol=IBM&interval=weekly&time_period=10&series_type=open&apikey=demo
```

---

### TEMA

Triple Exponential Moving Average.

Required: `function=TEMA`, `symbol`, `interval`, `time_period`, `series_type`, `apikey`.

```
https://www.alphavantage.co/query?function=TEMA&symbol=IBM&interval=weekly&time_period=10&series_type=open&apikey=demo
```

---

### TRIMA

Triangular Moving Average.

Required: `function=TRIMA`, `symbol`, `interval`, `time_period`, `series_type`, `apikey`.

```
https://www.alphavantage.co/query?function=TRIMA&symbol=IBM&interval=weekly&time_period=10&series_type=open&apikey=demo
```

---

### KAMA

Kaufman Adaptive Moving Average.

Required: `function=KAMA`, `symbol`, `interval`, `time_period`, `series_type`, `apikey`.

```
https://www.alphavantage.co/query?function=KAMA&symbol=IBM&interval=weekly&time_period=10&series_type=open&apikey=demo
```

---

### MAMA

MESA Adaptive Moving Average.

Required: `function=MAMA`, `symbol`, `interval`, `series_type`, `apikey`.
Optional: `fastlimit` (default 0.01), `slowlimit` (default 0.01).

```
https://www.alphavantage.co/query?function=MAMA&symbol=IBM&interval=daily&series_type=close&fastlimit=0.02&apikey=demo
```

---

### VWAP

**Premium / Trending** — Volume Weighted Average Price (intraday only).

Required: `function=VWAP`, `symbol`, `interval` (intraday only: `1min`, `5min`, `15min`, `30min`, `60min`), `apikey`.

```
https://www.alphavantage.co/query?function=VWAP&symbol=IBM&interval=15min&apikey=demo
```

---

### T3

Tilson Moving Average.

Required: `function=T3`, `symbol`, `interval`, `time_period`, `series_type`, `apikey`.

```
https://www.alphavantage.co/query?function=T3&symbol=IBM&interval=weekly&time_period=10&series_type=open&apikey=demo
```

---

### MACD

**Premium / Trending** — Moving Average Convergence/Divergence.

Required: `function=MACD`, `symbol`, `interval`, `series_type`, `apikey`.
Optional: `fastperiod` (12), `slowperiod` (26), `signalperiod` (9).

```
https://www.alphavantage.co/query?function=MACD&symbol=IBM&interval=daily&series_type=open&apikey=demo
https://www.alphavantage.co/query?function=MACD&symbol=USDEUR&interval=weekly&series_type=open&apikey=demo
```

---

### MACDEXT

MACD with controllable moving average type.

Required: `function=MACDEXT`, `symbol`, `interval`, `series_type`, `apikey`.
Optional: `fastperiod`, `slowperiod`, `signalperiod`, `fastmatype`, `slowmatype`, `signalmatype` (each MA type 0–8: 0=SMA, 1=EMA, 2=WMA, 3=DEMA, 4=TEMA, 5=TRIMA, 6=T3, 7=KAMA, 8=MAMA).

```
https://www.alphavantage.co/query?function=MACDEXT&symbol=IBM&interval=daily&series_type=open&apikey=demo
```

---

### STOCH

**Trending** — Stochastic Oscillator.

Required: `function=STOCH`, `symbol`, `interval`, `apikey`.
Optional: `fastkperiod` (5), `slowkperiod` (3), `slowdperiod` (3), `slowkmatype` (0–8), `slowdmatype` (0–8).

```
https://www.alphavantage.co/query?function=STOCH&symbol=IBM&interval=daily&apikey=demo
https://www.alphavantage.co/query?function=STOCH&symbol=USDEUR&interval=weekly&apikey=demo
```

---

### STOCHF

Stochastic Fast.

Required: `function=STOCHF`, `symbol`, `interval`, `apikey`.
Optional: `fastkperiod` (5), `fastdperiod` (3), `fastdmatype` (0–8).

```
https://www.alphavantage.co/query?function=STOCHF&symbol=IBM&interval=daily&apikey=demo
```

---

### RSI

**Trending** — Relative Strength Index.

Required: `function=RSI`, `symbol`, `interval`, `time_period`, `series_type`, `apikey`.

```
https://www.alphavantage.co/query?function=RSI&symbol=IBM&interval=weekly&time_period=10&series_type=open&apikey=demo
https://www.alphavantage.co/query?function=RSI&symbol=USDEUR&interval=weekly&time_period=10&series_type=open&apikey=demo
```

---

### STOCHRSI

Stochastic RSI.

Required: `function=STOCHRSI`, `symbol`, `interval`, `time_period`, `series_type`, `apikey`.
Optional: `fastkperiod` (5), `fastdperiod` (3), `fastdmatype` (0–8).

```
https://www.alphavantage.co/query?function=STOCHRSI&symbol=IBM&interval=daily&time_period=10&series_type=close&fastkperiod=6&fastdmatype=1&apikey=demo
```

---

### WILLR

Williams' %R.

Required: `function=WILLR`, `symbol`, `interval`, `time_period`, `apikey`.

```
https://www.alphavantage.co/query?function=WILLR&symbol=IBM&interval=daily&time_period=10&apikey=demo
```

---

### ADX

**Trending** — Average Directional Movement Index.

Required: `function=ADX`, `symbol`, `interval`, `time_period`, `apikey`.

```
https://www.alphavantage.co/query?function=ADX&symbol=IBM&interval=daily&time_period=10&apikey=demo
https://www.alphavantage.co/query?function=ADX&symbol=USDEUR&interval=weekly&time_period=10&apikey=demo
```

---

### ADXR

Average Directional Movement Index Rating.

Required: `function=ADXR`, `symbol`, `interval`, `time_period`, `apikey`.

```
https://www.alphavantage.co/query?function=ADXR&symbol=IBM&interval=daily&time_period=10&apikey=demo
```

---

### APO

Absolute Price Oscillator.

Required: `function=APO`, `symbol`, `interval`, `series_type`, `apikey`.
Optional: `fastperiod` (12), `slowperiod` (26), `matype` (0–8).

```
https://www.alphavantage.co/query?function=APO&symbol=IBM&interval=daily&series_type=close&fastperiod=10&matype=1&apikey=demo
```

---

### PPO

Percentage Price Oscillator.

Required: `function=PPO`, `symbol`, `interval`, `series_type`, `apikey`.
Optional: `fastperiod` (12), `slowperiod` (26), `matype` (0–8).

```
https://www.alphavantage.co/query?function=PPO&symbol=IBM&interval=daily&series_type=close&fastperiod=10&matype=1&apikey=demo
```

---

### MOM

Momentum.

Required: `function=MOM`, `symbol`, `interval`, `time_period`, `series_type`, `apikey`.

```
https://www.alphavantage.co/query?function=MOM&symbol=IBM&interval=daily&time_period=10&series_type=close&apikey=demo
```

---

### BOP

Balance of Power.

Required: `function=BOP`, `symbol`, `interval`, `apikey`.

```
https://www.alphavantage.co/query?function=BOP&symbol=IBM&interval=daily&apikey=demo
```

---

### CCI

**Trending** — Commodity Channel Index.

Required: `function=CCI`, `symbol`, `interval`, `time_period`, `apikey`.

```
https://www.alphavantage.co/query?function=CCI&symbol=IBM&interval=daily&time_period=10&apikey=demo
https://www.alphavantage.co/query?function=CCI&symbol=USDEUR&interval=weekly&time_period=10&apikey=demo
```

---

### CMO

Chande Momentum Oscillator.

Required: `function=CMO`, `symbol`, `interval`, `time_period`, `series_type`, `apikey`.

```
https://www.alphavantage.co/query?function=CMO&symbol=IBM&interval=weekly&time_period=10&series_type=close&apikey=demo
```

---

### ROC

Rate of Change.

Required: `function=ROC`, `symbol`, `interval`, `time_period`, `series_type`, `apikey`.

```
https://www.alphavantage.co/query?function=ROC&symbol=IBM&interval=weekly&time_period=10&series_type=close&apikey=demo
```

---

### ROCR

Rate of Change Ratio.

Required: `function=ROCR`, `symbol`, `interval`, `time_period`, `series_type`, `apikey`.

```
https://www.alphavantage.co/query?function=ROCR&symbol=IBM&interval=daily&time_period=10&series_type=close&apikey=demo
```

---

### AROON

**Trending**

Required: `function=AROON`, `symbol`, `interval`, `time_period`, `apikey`.

```
https://www.alphavantage.co/query?function=AROON&symbol=IBM&interval=daily&time_period=14&apikey=demo
https://www.alphavantage.co/query?function=AROON&symbol=USDEUR&interval=weekly&time_period=14&apikey=demo
```

---

### AROONOSC

Aroon Oscillator.

Required: `function=AROONOSC`, `symbol`, `interval`, `time_period`, `apikey`.

```
https://www.alphavantage.co/query?function=AROONOSC&symbol=IBM&interval=daily&time_period=10&apikey=demo
```

---

### MFI

Money Flow Index.

Required: `function=MFI`, `symbol`, `interval`, `time_period`, `apikey`.

```
https://www.alphavantage.co/query?function=MFI&symbol=IBM&interval=weekly&time_period=10&apikey=demo
```

---

### TRIX

1-day rate of change of triple smooth EMA.

Required: `function=TRIX`, `symbol`, `interval`, `time_period`, `series_type`, `apikey`.

```
https://www.alphavantage.co/query?function=TRIX&symbol=IBM&interval=daily&time_period=10&series_type=close&apikey=demo
```

---

### ULTOSC

Ultimate Oscillator.

Required: `function=ULTOSC`, `symbol`, `interval`, `apikey`.
Optional: `timeperiod1` (7), `timeperiod2` (14), `timeperiod3` (28).

```
https://www.alphavantage.co/query?function=ULTOSC&symbol=IBM&interval=daily&timeperiod1=8&apikey=demo
https://www.alphavantage.co/query?function=ULTOSC&symbol=IBM&interval=weekly&apikey=demo
```

---

### DX

Directional Movement Index.

Required: `function=DX`, `symbol`, `interval`, `time_period`, `apikey`.

```
https://www.alphavantage.co/query?function=DX&symbol=IBM&interval=daily&time_period=10&apikey=demo
```

---

### MINUS_DI

Minus Directional Indicator.

Required: `function=MINUS_DI`, `symbol`, `interval`, `time_period`, `apikey`.

```
https://www.alphavantage.co/query?function=MINUS_DI&symbol=IBM&interval=weekly&time_period=10&apikey=demo
```

---

### PLUS_DI

Plus Directional Indicator.

Required: `function=PLUS_DI`, `symbol`, `interval`, `time_period`, `apikey`.

```
https://www.alphavantage.co/query?function=PLUS_DI&symbol=IBM&interval=daily&time_period=10&apikey=demo
```

---

### MINUS_DM

Minus Directional Movement.

Required: `function=MINUS_DM`, `symbol`, `interval`, `time_period`, `apikey`.

```
https://www.alphavantage.co/query?function=MINUS_DM&symbol=IBM&interval=daily&time_period=10&apikey=demo
```

---

### PLUS_DM

Plus Directional Movement.

Required: `function=PLUS_DM`, `symbol`, `interval`, `time_period`, `apikey`.

```
https://www.alphavantage.co/query?function=PLUS_DM&symbol=IBM&interval=daily&time_period=10&apikey=demo
```

---

### BBANDS

**Trending** — Bollinger Bands.

Required: `function=BBANDS`, `symbol`, `interval`, `time_period`, `series_type`, `apikey`.
Optional: `nbdevup` (2), `nbdevdn` (2), `matype` (0–8).

```
https://www.alphavantage.co/query?function=BBANDS&symbol=IBM&interval=weekly&time_period=5&series_type=close&nbdevup=3&nbdevdn=3&apikey=demo
https://www.alphavantage.co/query?function=BBANDS&symbol=USDEUR&interval=weekly&time_period=5&series_type=close&nbdevup=3&nbdevdn=3&apikey=demo
```

---

### MIDPOINT

MIDPOINT = (highest value + lowest value) / 2.

Required: `function=MIDPOINT`, `symbol`, `interval`, `time_period`, `series_type`, `apikey`.

```
https://www.alphavantage.co/query?function=MIDPOINT&symbol=IBM&interval=daily&time_period=10&series_type=close&apikey=demo
```

---

### MIDPRICE

MIDPRICE = (highest high + lowest low) / 2.

Required: `function=MIDPRICE`, `symbol`, `interval`, `time_period`, `apikey`.

```
https://www.alphavantage.co/query?function=MIDPRICE&symbol=IBM&interval=daily&time_period=10&apikey=demo
```

---

### SAR

Parabolic SAR.

Required: `function=SAR`, `symbol`, `interval`, `apikey`.
Optional: `acceleration` (default 0.01), `maximum` (default 0.20), `month`, `datatype`, `entitlement`.

```
https://www.alphavantage.co/query?function=SAR&symbol=IBM&interval=weekly&acceleration=0.01&maximum=0.20&apikey=demo
```

---

### TRANGE

True Range.

Required: `function=TRANGE`, `symbol`, `interval`, `apikey`.
Optional: `month`, `datatype`, `entitlement`.

```
https://www.alphavantage.co/query?function=TRANGE&symbol=IBM&interval=daily&apikey=demo
```

---

### ATR

Average True Range.

Required: `function=ATR`, `symbol`, `interval`, `time_period`, `apikey`.
Optional: `month`, `datatype`, `entitlement`.

```
https://www.alphavantage.co/query?function=ATR&symbol=IBM&interval=daily&time_period=14&apikey=demo
```

---

### NATR

Normalized Average True Range.

Required: `function=NATR`, `symbol`, `interval`, `time_period`, `apikey`.
Optional: `month`, `datatype`, `entitlement`.

```
https://www.alphavantage.co/query?function=NATR&symbol=IBM&interval=weekly&time_period=14&apikey=demo
```

---

### AD

**Trending** — Chaikin A/D Line (Accumulation/Distribution).

Required: `function=AD`, `symbol`, `interval`, `apikey`.
Optional: `month`, `datatype`, `entitlement`.

```
https://www.alphavantage.co/query?function=AD&symbol=IBM&interval=daily&apikey=demo
```

---

### ADOSC

Chaikin A/D Oscillator.

Required: `function=ADOSC`, `symbol`, `interval`, `apikey`.
Optional: `fastperiod` (default 3), `slowperiod` (default 10), `month`, `datatype`, `entitlement`.

```
https://www.alphavantage.co/query?function=ADOSC&symbol=IBM&interval=daily&fastperiod=5&slowperiod=10&apikey=demo
```

---

### OBV

**Trending** — On Balance Volume.

Required: `function=OBV`, `symbol`, `interval`, `apikey`.
Optional: `month`, `datatype`, `entitlement`.

```
https://www.alphavantage.co/query?function=OBV&symbol=IBM&interval=weekly&apikey=demo
```

---

### HT_TRENDLINE

Hilbert Transform — Instantaneous Trendline.

Required: `function=HT_TRENDLINE`, `symbol`, `interval`, `series_type`, `apikey`.
Optional: `month`, `datatype`, `entitlement`.

```
https://www.alphavantage.co/query?function=HT_TRENDLINE&symbol=IBM&interval=daily&series_type=close&apikey=demo
```

---

### HT_SINE

Hilbert Transform — Sine Wave.

Required: `function=HT_SINE`, `symbol`, `interval`, `series_type`, `apikey`.
Optional: `month`, `datatype`, `entitlement`.

```
https://www.alphavantage.co/query?function=HT_SINE&symbol=IBM&interval=daily&series_type=close&apikey=demo
```

---

### HT_TRENDMODE

Hilbert Transform — Trend vs. Cycle Mode.

Required: `function=HT_TRENDMODE`, `symbol`, `interval`, `series_type`, `apikey`.
Optional: `month`, `datatype`, `entitlement`.

```
https://www.alphavantage.co/query?function=HT_TRENDMODE&symbol=IBM&interval=weekly&series_type=close&apikey=demo
```

---

### HT_DCPERIOD

Hilbert Transform — Dominant Cycle Period.

Required: `function=HT_DCPERIOD`, `symbol`, `interval`, `series_type`, `apikey`.
Optional: `month`, `datatype`, `entitlement`.

```
https://www.alphavantage.co/query?function=HT_DCPERIOD&symbol=IBM&interval=daily&series_type=close&apikey=demo
```

---

### HT_DCPHASE

Hilbert Transform — Dominant Cycle Phase.

Required: `function=HT_DCPHASE`, `symbol`, `interval`, `series_type`, `apikey`.
Optional: `month`, `datatype`, `entitlement`.

```
https://www.alphavantage.co/query?function=HT_DCPHASE&symbol=IBM&interval=daily&series_type=close&apikey=demo
```

---

### HT_PHASOR

Hilbert Transform — Phasor Components.

Required: `function=HT_PHASOR`, `symbol`, `interval`, `series_type`, `apikey`.
Optional: `month`, `datatype`, `entitlement`.

```
https://www.alphavantage.co/query?function=HT_PHASOR&symbol=IBM&interval=weekly&series_type=close&apikey=demo
```

---

## Language-specific guides (general note)

For all endpoints in this document, the four supported language patterns are:

- **Python** uses `requests` library and `r.json()`
- **NodeJS** uses `request` library with `{url, json: true, headers: {'User-Agent': 'request'}}`
- **PHP** uses `file_get_contents()` and `json_decode()`
- **C#/.NET** uses `WebClient` with either `JavaScriptSerializer` (.NET Framework) or `JsonSerializer` (.NET Core)

For CSV endpoints (LISTING_STATUS, EARNINGS_CALENDAR, IPO_CALENDAR), use `csv` module in Python, `scramjet` StringStream in NodeJS, `str_getcsv()` in PHP, or `CsvHelper` in .NET.

The open-source community has 1000+ libraries for Alpha Vantage across 20+ programming languages — see https://github.com/search?q=alpha+vantage.

For LLM/AI agent integration: https://mcp.alphavantage.co/

For spreadsheet users (Excel/Google Sheets): https://www.alphavantage.co/spreadsheets/
