# Indicator Array Implementation Example

## Overview
All indicator columns now store arrays of daily values (Day0-Day5) instead of single values at strike hit or peak profit.

## Data Format

### Strike_Hit Array
```json
["0.013823", "0.012456", "0.011234", "-0.006912", "0.029178", "0.007523"]
```
Each value shows the decimal move from that day's closing price to the strike (not percentage).
To convert to percentage, multiply by 100.

### Indicator Arrays

#### Hit_RSI
```json
["65.23", "68.45", "71.12", "69.87", "58.34", "62.15"]
```

#### Hit_SMA20
```json
["281.45", "281.67", "281.89", "282.34", "282.11", "282.05"]
```

#### Hit_SMA50
```json
["278.23", "278.45", "278.67", "278.91", "279.12", "279.34"]
```

#### Hit_EMA9
```json
["282.11", "282.34", "282.78", "283.45", "281.23", "281.89"]
```

#### Hit_EMA21
```json
["280.56", "280.78", "281.01", "281.45", "281.23", "281.34"]
```

#### Hit_VWAP
```json
["281.78", "282.01", "282.34", "283.12", "280.45", "281.23"]
```

#### Hit_RVOL
```json
["1.23", "1.45", "1.67", "2.01", "1.89", "1.56"]
```

#### Hit_ATR
```json
["2.3456", "2.4567", "2.5678", "2.8901", "3.0123", "2.9012"]
```

#### Hit_PriceVsSMA20
```json
["0.23%", "0.45%", "0.67%", "1.23%", "-1.45%", "0.34%"]
```

#### Hit_PriceVsVWAP
```json
["-0.12%", "-0.23%", "-0.34%", "1.45%", "-1.23%", "0.56%"]
```

## How It Works

### Historical Backfill
1. For each day (Day0-Day5), calculates all indicators
2. Builds arrays with values for each day
3. Stores as JSON arrays in the cells

### Active Position Tracking
1. Daily 5PM update appends current day's indicators
2. Arrays grow day by day
3. Maximum 6 values (Day0-Day5)

## Benefits

1. **Complete History**: See how indicators evolved over the 6-day period
2. **Better Analysis**: Identify patterns in indicator movements
3. **Flexibility**: Can analyze any specific day's indicators
4. **Consistency**: Same format as Strike_Hit array

## Example Usage

To get Day 3 RSI value:
```javascript
const rsiArray = EW_parseIndicatorArray(row[hdrMap.hitRSICol - 1]);
const day3RSI = rsiArray[3]; // "69.87"
```

To check if RSI increased from Day 2 to Day 3:
```javascript
const increased = parseFloat(rsiArray[3]) > parseFloat(rsiArray[2]); // false (69.87 < 71.12)
```

## Migration from Single Values
The system handles legacy single values by converting them to arrays:
- Single value "65.23" → Array ["65.23"]
- This ensures backward compatibility