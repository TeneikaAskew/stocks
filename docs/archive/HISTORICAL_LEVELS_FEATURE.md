# Historical Levels Feature Documentation

## Overview

The historical levels feature has been added to `iwm_analysis.py` to capture support/resistance levels from previous time periods (day, week, month, year) and their 50% midpoints. This helps identify patterns where price action interacts with key levels, which can be predictive of successful trade setups.

## New Features Added

### 1. Historical Level Calculations

The `calculate_historical_levels()` method adds the following features to each record:

#### Previous Period Levels (24 base levels)
- **Previous Day**: High, Low, Open, Close, HL_Mid, OC_Mid
- **Previous Week**: High, Low, Open, Close, HL_Mid, OC_Mid
- **Previous Month**: High, Low, Open, Close, HL_Mid, OC_Mid
- **Previous Year**: High, Low, Open, Close, HL_Mid, OC_Mid

#### Price Position Relative to Levels (24 percentage columns)
For each level above, calculates: `(Current_Price - Level) / Level * 100`

Examples:
- `Prev_Day_High_Pct`: -2.5% means price is 2.5% below previous day's high
- `Prev_Week_HL_Mid_Pct`: +1.2% means price is 1.2% above previous week's midpoint

#### Breakout/Breakdown Flags (8 binary columns)
- `Broke_Prev_Day_High`: 1 if price broke above previous day high, 0 otherwise
- `Broke_Prev_Day_Low`: 1 if price broke below previous day low, 0 otherwise
- `Broke_Prev_Week_High` / `Broke_Prev_Week_Low`
- `Broke_Prev_Month_High` / `Broke_Prev_Month_Low`
- `Broke_Prev_Year_High` / `Broke_Prev_Year_Low`

#### At-Level Indicators (24 binary columns)
Within 0.1% tolerance of key levels:
- `At_Prev_Day_High`: 1 if price is within 0.1% of previous day high
- `At_Prev_Day_Low`: 1 if price is within 0.1% of previous day low
- `At_Prev_Day_HL_Mid`: 1 if price is at 50% of previous day range
- ... and 21 more for week/month/year levels

### 2. Signal Data Enhancement

All generated trading signals now include historical level data at entry:

```python
signal_data = {
    # ... existing fields ...

    # Historical Levels at Entry
    'entry_prev_day_high': 207.29,
    'entry_prev_day_low': 200.68,
    'entry_prev_day_hl_mid': 203.99,
    'entry_prev_week_high': 209.50,
    # ... etc

    # Price Position
    'entry_vs_prev_day_high_pct': 0.20,
    'entry_vs_prev_day_low_pct': 3.50,
    # ... etc

    # Breakout Flags
    'entry_broke_prev_day_high': 1,
    'entry_broke_prev_day_low': 0,
    # ... etc

    # At Level Flags
    'entry_at_prev_day_high': 1,
    'entry_at_prev_day_low': 0,
    # ... etc
}
```

## Total New Columns Added

- **80 new columns** total in enhanced data file
- **48 columns** for signal data (exported to CSV)

## Use Cases

### 1. Breakout/Breakdown Analysis
Identify if profitable signals occur when price:
- Breaks above previous day/week/month highs
- Breaks below previous day/week/month lows
- Tests and holds previous levels

### 2. Mean Reversion Analysis
Identify if profitable signals occur when price:
- Reaches 50% retracement levels (HL_Mid, OC_Mid)
- Bounces off previous lows
- Rejects at previous highs

### 3. Level Confluence
Find patterns where multiple levels align:
- Previous day high near previous week 50% level
- Previous month low near previous week close
- Multiple timeframe support/resistance

### 4. Trend Context
Understand if signals work better when:
- Price is above all previous levels (strong uptrend)
- Price is below all previous levels (strong downtrend)
- Price is between levels (range-bound)

## Example Analysis Queries

```python
import pandas as pd

# Load signals with historical levels
signals = pd.read_csv('data/historical_iwm_0824_0825_signals.csv')

# 1. Find CALL signals that broke previous day high
breakout_calls = signals[
    (signals['trade_type'] == 'call') &
    (signals['entry_broke_prev_day_high'] == 1)
]
print(f"Breakout calls win rate: {(breakout_calls['return_pct'] > 0).mean():.2%}")

# 2. Find PUT signals near previous day 50% level
mid_level_puts = signals[
    (signals['trade_type'] == 'put') &
    (signals['entry_at_prev_day_hl_mid'] == 1)
]
print(f"Mid-level puts win rate: {(mid_level_puts['return_pct'] > 0).mean():.2%}")

# 3. Find signals at previous week lows (potential support)
support_signals = signals[signals['entry_at_prev_week_low'] == 1]
print(f"Support signals: {len(support_signals)}")
print(f"Average return: {support_signals['return_pct'].mean():.2f}%")

# 4. Analyze price position correlation with returns
import numpy as np
correlation = np.corrcoef(
    signals['entry_vs_prev_day_high_pct'].fillna(0),
    signals['return_pct']
)[0, 1]
print(f"Correlation between day high position and returns: {correlation:.3f}")
```

## Testing

Run the test script to verify the feature:

```bash
python test_historical_levels.py
```

Expected output shows:
- 80 new columns added
- Sample data with level values
- Breakout counts
- Data quality metrics

## Integration with Existing Analysis

The historical levels are automatically calculated in the `add_technical_indicators()` method as step 8/10, right before validation. This ensures all subsequent signal generation has access to level data.

## Performance Notes

- Level calculation uses pandas groupby for efficiency
- Previous year levels may have limited data in shorter datasets
- First day/week/month/year will have NaN values (no previous period)
- Week grouping uses pandas Period with 'W' frequency (ISO week starting Monday)

## Future Enhancements

Potential additions:
1. **Order Blocks**: Track consolidation zones and breakouts
2. **ORB (Opening Range Breakout)**: 5m, 15m, 30m opening ranges
3. **Fibonacci Levels**: Retracement levels between highs/lows
4. **Volume Profile Levels**: High volume nodes as support/resistance
5. **Pivot Points**: Traditional, Fibonacci, and Camarilla pivots

## Files Modified

- `iwm_analysis.py`: Added `calculate_historical_levels()` method
- `iwm_analysis.py`: Integrated into `add_technical_indicators()`
- `iwm_analysis.py`: Enhanced signal data export with level information
- `test_historical_levels.py`: Created test script for validation

## Output Files

When you run `python iwm_analysis.py`, the enhanced files will contain:

1. `data/historical_iwm_0824_0825_with_indicators.csv`:
   - All 80 historical level columns
   - Can be used for custom analysis

2. `data/historical_iwm_0824_0825_signals.csv`:
   - 48 level-related columns per signal
   - Ready for correlation analysis and pattern discovery
