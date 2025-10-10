# Column Quick Reference

> See [DATA_DICTIONARY.md](DATA_DICTIONARY.md) for complete documentation

## Column Count by Category

| Category | Count | Description |
|----------|-------|-------------|
| Core Trade Info | 4 | Run Date, Strategy, company, ticker |
| Pricing & Strikes | 15+ | strike, longStrike, breakeven, etc. |
| Earnings Data | 6 | nextEPSDate, releaseTime, avgEPSMove, etc. |
| Tracking Arrays | 4 | Strike_Hit, Max_Favorable, Min_Unfavorable, OHLC_Volume |
| Day Checks | 6 | Day0_Check through Day5_Check |
| Entry Indicators | 10 | Entry_RSI, Entry_SMA20, Entry_VWAP, etc. |
| Hit Indicators (Arrays) | 10 | Hit_RSI, Hit_SMA20, Hit_VWAP, etc. |
| Risk/Reward | 8+ | Risk_Reward, maxProfit, maxLoss, etc. |
| Results | 8 | Hit_Date, Exp_Result, Success_Score, etc. |
| GoogleFinance | 17 | GF_Price, GF_High, GF_Volume, etc. |
| Metadata | 5+ | expDate, Last_Update, confirmDate, etc. |

**Total: 100+ columns** (varies by strategy)

## Array Columns (Day 0-5)

All arrays store 6 values: `[day0, day1, day2, day3, day4, day5]`

### Core Tracking Arrays

| Column | Purpose | Bullish Formula | Bearish Formula |
|--------|---------|-----------------|-----------------|
| **Strike_Hit** | % move from strike to extreme | `(high - strike) / strike` | `(strike - low) / strike` |
| **Max_Favorable** | Best possible profit % | Same as Strike_Hit for bullish | Same as Strike_Hit for bearish |
| **Min_Unfavorable** | Worst possible loss % | `(low - strike) / strike` | `(strike - high) / strike` |
| **OHLC_Volume** | Full OHLC + volume data | See OHLC structure below | See OHLC structure below |

### Technical Indicator Arrays

Each stores 6 values (Day 0-5):

- **Hit_RSI**: RSI values `[RSI_day0, RSI_day1, ..., RSI_day5]`
- **Hit_SMA20**: 20-day SMA `[SMA20_day0, ..., SMA20_day5]`
- **Hit_SMA50**: 50-day SMA
- **Hit_EMA9**: 9-day EMA
- **Hit_EMA21**: 21-day EMA
- **Hit_VWAP**: Volume-weighted average price
- **Hit_RVOL**: Relative volume (vs 10-day avg)
- **Hit_ATR**: Average True Range
- **Hit_PriceVsSMA20**: Price position vs SMA20 `(price - SMA20) / SMA20`
- **Hit_PriceVsVWAP**: Price position vs VWAP `(price - VWAP) / VWAP`

## OHLC_Volume Structure

JSON array of 6 objects (Day 0-5):

```json
[
  {
    "date": "2024-03-15",
    "open": 175.20,
    "high": 177.50,
    "low": 174.80,
    "close": 176.90,
    "volume": 45000000,
    "source": "yahoo"
  },
  // ... Day 1-5
]
```

## Strategy-Specific Columns

### Bull/Bear Spreads Only
- `longStrike`, `shortStrike`
- `longAsk`, `shortBid`
- `maxProfit`, `maxLoss`, `maxReturn`, `maxRisk`
- `netRatings`, `totRatings`, `ewRating`

### Long Calls/Puts Only
- `price` (current stock price)
- `score`, `openInterest`, `volume`
- `bid`, `ask`, `optionDate`
- `lastEPSTime`

### Covered Calls Only
- `cushion` (% buffer to strike)
- `upTarget`, `downTarget`
- `callAway`, `callAwayReturn`
- `exDivDate`, `payout`

## Common Calculations

### Risk/Reward Ratio
```javascript
// Bullish strategies
riskReward = Max_Favorable[i] / abs(Min_Unfavorable[i])

// Bearish strategies
riskReward = Max_Favorable[i] / abs(Min_Unfavorable[i])
```

### Strike Hit Detection
```javascript
// Bullish: high >= strike
strikeHit = (dayHigh >= strike)

// Bearish: low <= strike
strikeHit = (dayLow <= strike)
```

### Exp_Result (WIN/LOSS)
```javascript
// Check if strike was hit on ANY day (Day 0-5)
strikeEverHit = Strike_Hit.some(val => val > 0)
expResult = strikeEverHit ? "WIN" : "LOSS"
```

## Day Index Mapping

| Array Index | Trading Day | Relative to Entry |
|-------------|-------------|-------------------|
| [0] | Day 0 | Entry day (Run Date) |
| [1] | Day 1 | 1 trading day after entry |
| [2] | Day 2 | 2 trading days after entry |
| [3] | Day 3 | 3 trading days after entry |
| [4] | Day 4 | 4 trading days after entry |
| [5] | Day 5 | 5 trading days after entry |

## Data Sources

| Source | Columns |
|--------|---------|
| **EarningsWhispers API** | company, ticker, nextEPSDate, releaseTime, avgEPSMove, epsImpact, confirmDate |
| **Yahoo Finance API** | OHLC data, indicators (RSI, SMA, EMA, VWAP, ATR) |
| **GoogleFinance** | GF_* columns (real-time prices, volume, fundamentals) |
| **Calculated (GAS)** | Strike_Hit, Max_Favorable, Min_Unfavorable, Risk_Reward, Exp_Result |
| **Manual Entry** | Strategy (sometimes), notes |

## Column Name Patterns

### Prefixes
- `Entry_*` - Indicators at entry time (single value)
- `Hit_*` - Indicators tracked Day 0-5 (arrays)
- `GF_*` - GoogleFinance real-time data
- `Day*_*` - Day-specific values (Day0_Check, Day1_Check, etc.)

### Suffixes
- `*_Date` - Date fields (Hit_Date, First_Hit_Date)
- `*_Result` - Outcome fields (Exp_Result)
- `*Pct` - Percentage values (epsImpact, changePct)
- `*Vol*` - Volume-related (avgVolume, RVOL, GF_Volume)

## Python Analytics Integration

See [config.py](config.py):

```python
TRACKING_COLUMNS = {
    'arrays': [
        'Strike_Hit', 'Max_Favorable', 'Min_Unfavorable', 'OHLC_Volume'
    ],
    'indicators': [
        'Hit_RSI', 'Hit_SMA20', 'Hit_SMA50', 'Hit_EMA9', 'Hit_EMA21',
        'Hit_VWAP', 'Hit_RVOL', 'Hit_ATR', 'Hit_PriceVsSMA20', 'Hit_PriceVsVWAP'
    ]
}
```

Arrays are automatically parsed from JSON to Python lists by `data_loader.py`.

## Finding Column Definitions

| Need to find... | Look in... |
|-----------------|------------|
| How column is calculated | `google-apps-script/src/13_ArrayBuilders.js` |
| When column is populated | `google-apps-script/src/08_TrackingUpdates.js` |
| Column initialization | `google-apps-script/src/15_AddTrackingColumns.js` |
| Indicator calculations | `google-apps-script/src/05_TechnicalIndicators.js` |
| OHLC handling | `google-apps-script/src/19_OHLCUtilities.js` |
| Python parsing | `earnings_options_analytics/modules/data_loader.py` |
| Complete documentation | `DATA_DICTIONARY.md` |

---

**For complete details on any column, see [DATA_DICTIONARY.md](DATA_DICTIONARY.md)**
