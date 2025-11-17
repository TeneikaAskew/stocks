# Options Contract Matching & P/L Analysis

## Overview

The Trading Chart Viewer now includes a sophisticated options analysis system that matches your marked trades with actual options contracts from AlphaVantage data and calculates realistic P/L based on real contract prices.

## How It Works

### 1. Trade Entry Data Captured

When you mark a trade on the chart, the system captures:
- **Entry Time**: Unix timestamp of when you entered
- **Entry Price**: The underlying stock price at entry
- **Option Type**: CALL or PUT
- **Take Profit Levels**: Up to 3 TP levels with sizes
- **Stop Loss**: SL price level
- **Ticker**: Symbol (IWM, SPY, QQQ)

### 2. Contract Matching Algorithm

The `optionsAnalyzer.js` module finds the best matching contract using:

**Step 1: Filter by Type**
- Filters contracts to match CALL or PUT

**Step 2: Filter by Date**
- Matches contracts from the exact trading day

**Step 3: Find Closest Strike**
Uses a weighted scoring system:
- **Strike Proximity (70%)**: How close the strike is to the underlying price
- **Delta Proximity (30%)**: Targets delta ~0.40 for realistic ATM/slightly OTM options

The algorithm looks for:
- **Calls**: Strike near or slightly above stock price, delta ~0.40
- **Puts**: Strike near or slightly below stock price, delta ~-0.40

### 3. P/L Calculation

**Entry Price**:
```javascript
entryOptionPrice = contract.mark || (contract.bid + contract.ask) / 2
```

**Exit Price** (if trade closed):
- Uses the same matching algorithm for the exit timestamp
- Calculates actual option price at exit

**Actual P/L**:
```javascript
actualPnL = exitOptionPrice - entryOptionPrice
actualPnLPercent = (actualPnL / entryOptionPrice) * 100
```

**Take Profit Estimation**:
For each TP level, estimates option price using delta:
```javascript
underlyingMove = tpPrice - entryPrice
optionPriceChange = underlyingMove * Math.abs(entryContract.delta)
estimatedOptionPrice = entryOptionPrice + optionPriceChange
```

### 4. Data Structure

Enhanced trade object includes:
```json
{
  "id": "trade_123...",
  "ticker": "IWM",
  "optionType": "CALL",
  "entryTime": 1763117220,
  "entryPrice": 234.77,
  "exitTime": 1763119620,
  "exitPrice": 237.44,
  "optionsAnalysis": {
    "status": "analyzed",
    "entryContract": {
      "contractID": "IWM251114C00235000",
      "strike": 235.00,
      "expiration": "2025-11-14",
      "delta": 0.45,
      "gamma": 0.032,
      "theta": -0.15,
      "vega": 0.08,
      "impliedVolatility": 0.25
    },
    "entryOptionPrice": 2.50,
    "exitOptionPrice": 4.20,
    "actualPnL": 1.70,
    "actualPnLPercent": 68.0,
    "takeProfitAnalysis": [
      {
        "level": 1,
        "targetPrice": 237.44,
        "size": 0.5,
        "estimatedOptionPrice": 3.70,
        "estimatedPnL": 1.20,
        "estimatedPnLPercent": 48.0
      }
    ],
    "stopLossAnalysis": {
      "targetPrice": 236.48,
      "estimatedOptionPrice": 2.10,
      "estimatedPnL": -0.40,
      "estimatedPnLPercent": -16.0
    },
    "originalPnL": 2.67,  // Stock-based P/L
    "originalPnLPercent": 1.14
  }
}
```

## API Endpoints

### Get Options Contracts

```
GET /api/options/{ticker}/{date}
```

**Example**:
```
GET /api/options/IWM/20251114
```

**Response**:
```json
[
  {
    "contractID": "IWM251114C00235000",
    "symbol": "IWM",
    "expiration": "2025-11-14",
    "strike": 235.0,
    "type": "call",
    "last": 2.45,
    "mark": 2.50,
    "bid": 2.40,
    "ask": 2.60,
    "volume": 1250,
    "open_interest": 5430,
    "date": "2025-11-14",
    "implied_volatility": 0.25,
    "delta": 0.45,
    "gamma": 0.032,
    "theta": -0.15,
    "vega": 0.08,
    "rho": 0.12,
    "snapshot_date": "2025-11-14"
  }
]
```

## Usage

### Analyze a Single Trade

```javascript
const analyzer = new OptionsAnalyzer();
const trade = tradeMarker.getAllTrades()[0];

const analyzedTrade = await analyzer.calculateActualPnL(trade);

console.log('Entry Contract:', analyzedTrade.optionsAnalysis.entryContract);
console.log('Actual P&L:', analyzedTrade.optionsAnalysis.actualPnL);
console.log('P&L %:', analyzedTrade.optionsAnalysis.actualPnLPercent);
```

### Analyze All Trades

```javascript
const analyzer = new OptionsAnalyzer();
const allTrades = tradeMarker.getAllTrades();

const analyzedTrades = await analyzer.analyzeAllTrades(allTrades);

// Get summary statistics
const summary = analyzer.getAnalysisSummary(analyzedTrades);

console.log('Win Rate:', summary.winRate);
console.log('Avg P&L:', summary.avgPnL);
console.log('Total P&L:', summary.totalPnL);
```

## Key Features

### 1. Real Contract Matching
- Uses actual AlphaVantage options data
- Matches based on strike, delta, and date
- Considers Greeks for realistic selection

### 2. Accurate P&L
- Uses mark prices (mid-point of bid/ask)
- Calculates option price changes, not stock price changes
- Shows the difference between stock P&L and option P&L

### 3. Take Profit Analysis
- Estimates option prices at each TP level
- Uses delta to approximate price movement
- Shows potential P&L for partial exits

### 4. Stop Loss Analysis
- Calculates risk in option premium terms
- Shows estimated loss if SL is hit

## Data Requirements

### Options Data Format
The system expects options data in parquet format at:
```
data/{ticker}/options/{ticker}_av_options_combined.parquet
```

### Required Columns
- `contractID`: Unique contract identifier
- `symbol`: Ticker symbol
- `expiration`: Contract expiration date
- `strike`: Strike price
- `type`: "call" or "put"
- `mark`: Mark price (mid-point)
- `bid`: Bid price
- `ask`: Ask price
- `delta`, `gamma`, `theta`, `vega`, `rho`: Greeks
- `implied_volatility`: IV
- `snapshot_date`: Date of the data snapshot

## Limitations

1. **Delta-based estimation**: TP/SL prices are estimated using delta, which assumes linear relationship. Real options pricing is non-linear.

2. **Same-day contracts**: Currently uses contracts from the entry date for exit calculations. Could be enhanced to load contracts from exit date.

3. **Data availability**: Requires AlphaVantage options data for the trading dates.

4. **Black-Scholes**: Doesn't implement full Black-Scholes pricing. Uses simplified delta-based approximation.

## Future Enhancements

- [ ] Full Black-Scholes pricing for TP/SL estimates
- [ ] Load contracts from exit date for more accurate exit pricing
- [ ] Support for multi-leg strategies (spreads, butterflies)
- [ ] Greeks-based risk analysis
- [ ] Implied volatility impact analysis
- [ ] Time decay (theta) visualization

## Testing

The system is ready to use! To test:

1. Start the API: `python chart-viewer/api.py`
2. Mark a trade in the chart viewer
3. Open browser console and run:
   ```javascript
   const analyzer = new OptionsAnalyzer();
   const trades = tradeMarker.getAllTrades();
   const analyzed = await analyzer.calculateActualPnL(trades[0]);
   console.log(analyzed.optionsAnalysis);
   ```

This will show you the matched contract and calculated P&L!
