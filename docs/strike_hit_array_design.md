# Strike_Hit Array Conversion Design

## Current Implementation
- Strike_Hit is a single cell containing percentage move from Day0 to strike (e.g., "2.8%")
- Updated once when position is tracked
- Formula: `(strike - day0Price) / day0Price * 100` for bullish strategies

## New Array Implementation

### Data Structure
Strike_Hit will contain an array of daily decimal moves:
```
["0.028000", "0.031000", "0.029000", "0.035000", "0.027000", "0.032000"]
```
- Index 0: Day0 decimal move to strike
- Index 1: Day1 decimal move to strike
- etc.
- To convert to percentage, multiply by 100

### Storage Format
Google Sheets doesn't natively support arrays in cells, so we'll use:
1. **JSON format**: `["0.028000", "0.031000", "0.029000", "0.035000", "0.027000", "0.032000"]`
2. **Alternative**: Comma-separated: `0.028000,0.031000,0.029000,0.035000,0.027000,0.032000`

### Indicator Recalculation Logic
Indicators will only be recalculated when:
1. Current day's closing price > previous day's closing price
2. This creates a "high water mark" approach

Example 1: `200.34, 198.64, 199.95, 197.77, 195.29, 199.91`
- Day0: Calculate indicators (first day)
- Day1: 198.64 < 200.34 - NO recalculation
- Day2: 199.95 > 198.64 but < 200.34 - NO recalculation
- Day3-5: All < 200.34 - NO recalculation

Example 2: `281.12, 281.51, 281.82, 286.98, 276.92, 282.89`
- Day0: Calculate indicators (first day)
- Day1: 281.51 > 281.12 - RECALCULATE
- Day2: 281.82 > 281.51 - RECALCULATE
- Day3: 286.98 > 281.82 - RECALCULATE
- Day4: 276.92 < 286.98 - NO recalculation
- Day5: 282.89 > 276.92 but < 286.98 - NO recalculation

## Implementation Plan

### 1. Update Data Structure
- Modify Strike_Hit to store JSON array
- Update all write operations to append to array
- Update all read operations to parse array

### 2. Track Price History
- Store daily closing prices to determine when to recalculate
- Track "high water mark" for indicator updates

### 3. Update Functions
- `EW_updateStrategyActiveStrikes()`: Append to array instead of overwriting
- `EW_processHistoricalPosition()`: Build array for all days
- `EW_calculateIndicatorsFromYahoo()`: Only run when price increases

### 4. Backward Compatibility
- Check if Strike_Hit contains array or single value
- Convert single values to array format during updates

## Impact Analysis

### Files to Update:
1. **09_HistoricalBackfill.js**
   - Line 169: Change from single setValue to array append
   - Add price tracking for indicator logic

2. **11_ActivePositionTracking.js**
   - Line 212: Change from single setValue to array append
   - Add logic to track daily prices
   - Update indicator calculation conditions

3. **04_Code.js**
   - Update formulas that reference Strike_Hit
   - May need helper functions to extract from array

4. **08_TrackingUpdates.js**
   - Line 95: Update to handle array format
   - Parse array when reading Strike_Hit

5. **02_HelperFunctions.js**
   - Add helper functions for array manipulation
   - Add price comparison logic

### New Helper Functions Needed:
```javascript
// Parse Strike_Hit array from cell
function EW_parseStrikeHitArray(value) {
  if (!value) return [];
  if (typeof value === 'string' && value.startsWith('[')) {
    return JSON.parse(value);
  }
  // Handle legacy single value
  return [value];
}

// Append to Strike_Hit array
function EW_appendStrikeHit(currentValue, newValue) {
  const array = EW_parseStrikeHitArray(currentValue);
  array.push(newValue);
  return JSON.stringify(array);
}

// Check if should recalculate indicators
function EW_shouldRecalculateIndicators(priceHistory) {
  if (priceHistory.length < 2) return true;
  const currentPrice = priceHistory[priceHistory.length - 1];
  const highWaterMark = Math.max(...priceHistory.slice(0, -1));
  return currentPrice > highWaterMark;
}
```

## Testing Requirements
1. Test array storage and retrieval
2. Test indicator recalculation logic with both examples
3. Test backward compatibility with existing data
4. Test reporting functions with array format