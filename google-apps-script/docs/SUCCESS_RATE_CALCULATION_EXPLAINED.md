# Success Rate Calculation Explained

## Overview
This document explains how success rates are calculated in the Success Report, addressing common issues and clarifying the logic.

## Key Concepts

### 1. Strike_Hit Array Values
The Strike_Hit array contains values for each day (0-5) that indicate whether and how the strike price was reached:

- **"NO"**: Strike was not hit on this day
- **"HIT"**: Strike was hit (used when no percentage calculation is needed)
- **Numeric value**: Percentage move when strike was hit (e.g., "2.5" means 2.5% move)
- **null or empty**: Day not yet reached or no data available

### 2. Hit Rate Calculation

**Definition**: Percentage of trades where the strike price was reached at any point during the 6-day holding period.

**Logic**:
```javascript
// A trade is considered "hit" if ANY day in Strike_Hit array has:
// - "HIT" value
// - A numeric percentage value (not 0)
// - Any value that's not "NO", null, or empty

trade.wasHit = trade.strikeHit && trade.strikeHit.length > 0 && 
  trade.strikeHit.some(hit => {
    if (!hit || hit === "NO") return false;
    if (hit === "HIT") return true;
    const numValue = parseFloat(hit);
    return !isNaN(numValue) && numValue !== 0;
  });

hitRate = (hitTrades / totalTrades * 100) + '%'
```

### 3. Profitable Rate (Success Rate) Calculation

**Definition**: Percentage of trades that were profitable when they hit the strike price.

**Logic**:
```javascript
// A trade is profitable if:
// 1. It was hit (strike reached)
// 2. On the day it hit, favorable movement > unfavorable movement

const profitableTrades = trades.filter(trade => {
  if (!trade.wasHit) return false;
  
  // Find first day it hit
  const hitIndex = trade.strikeHit.findIndex(hit => 
    hit !== null && hit !== "NO" && parseFloat(hit) > 0
  );
  
  // Compare favorable vs unfavorable on hit day
  const favorable = parseFloat(trade.maxFavorable[hitIndex]) || 0;
  const unfavorable = parseFloat(trade.minUnfavorable[hitIndex]) || 0;
  
  return favorable > unfavorable;
});

profitableRate = (profitableTrades / totalTrades * 100) + '%'
```

## Common Issues and Solutions

### Issue 1: Low Hit Rate (e.g., 8% when majority should be hit)

**Possible Causes**:
1. **Empty Strike_Hit arrays**: If backfill hasn't run, arrays might be empty
2. **All "NO" values**: If strikes weren't reached, all days show "NO"
3. **Data type issues**: String vs numeric comparisons
4. **Incorrect strike prices**: If strikes are unrealistic, they won't be hit

**Solutions**:
- Run backfill to populate Strike_Hit arrays
- Verify strike prices are reasonable
- Check that data is being parsed correctly

### Issue 2: Mixed Data Types in Profitable Column

**Problem**: Column showing mix of percentages, numbers, and dates

**Solution**: Format all values consistently:
```javascript
// Before: profitableCount (raw number like 45)
// After: `${profitableCount} trades` (formatted like "45 trades")
```

### Issue 3: Strike Values in Top Plays

**Problem**: Strike column showing percentages or invalid values

**Solution**: Parse and format strikes properly:
```javascript
strike: trade.strike > 0 ? 
  parseFloat(trade.strike).toFixed(2) : 
  (trade.longStrike > 0 ? parseFloat(trade.longStrike).toFixed(2) : 'N/A')
```

## Strategy-Specific Calculations

### Long Calls
- Hit when: Current price >= Strike price
- Favorable: (High - Strike) / Strike
- Unfavorable: (Strike - Low) / Strike

### Long Puts
- Hit when: Current price <= Strike price
- Favorable: (Strike - Low) / Strike
- Unfavorable: (High - Strike) / Strike

### Bull Call Spreads
- Hit when: Current price >= Long strike
- Max profit capped at: (Short strike - Long strike) / Long strike
- Favorable capped at spread width

### Bear Put Spreads
- Hit when: Current price <= Long strike
- Max profit capped at: (Long strike - Short strike) / Long strike
- Favorable capped at spread width

## Verification Steps

1. **Check Data Population**:
   ```javascript
   // Log to verify arrays are populated
   console.log(`Strike_Hit array: ${JSON.stringify(trade.strikeHit)}`);
   console.log(`Was hit: ${trade.wasHit}`);
   ```

2. **Verify Strike Prices**:
   ```javascript
   // Ensure strikes are numeric
   const strike = parseFloat(trade.strike);
   console.log(`Strike: ${strike}, Type: ${typeof strike}`);
   ```

3. **Debug Hit Detection**:
   ```javascript
   // Add logging in hit detection
   trade.strikeHit.forEach((hit, idx) => {
     console.log(`Day ${idx}: ${hit} - Is hit: ${hit !== "NO" && hit !== null}`);
   });
   ```

## Best Practices

1. **Always Run Backfill**: Ensure historical data is populated before generating reports
2. **Validate Data Types**: Use parseFloat() for numeric comparisons
3. **Handle Edge Cases**: Check for null, empty, and "NO" values
4. **Use Consistent Formatting**: Format display values for readability
5. **Add Debug Logging**: Include console.log statements for troubleshooting

## Summary

The success rate calculation depends on:
1. Properly populated Strike_Hit arrays
2. Correct parsing of array values
3. Accurate favorable/unfavorable calculations
4. Proper handling of strategy-specific logic

By following the logic documented here and implementing the suggested fixes, the Success Report should accurately reflect trading performance.