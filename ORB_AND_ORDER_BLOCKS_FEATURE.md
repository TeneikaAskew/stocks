# ORB and Order Blocks Feature Documentation

## Overview

Added Opening Range Breakout (ORB) and Order Block features to `iwm_analysis.py` to identify intraday trend direction, support/resistance levels, and consolidation zones that may be predictive of successful trade setups.

## Features Added

### 1. Opening Range Breakout (ORB) - 3 Timeframes

Calculates the opening range (high and low) for the first N minutes after market open (9:30 AM), then tracks price behavior relative to that range throughout the day.

#### Timeframes:
- **5-minute ORB** (9:30-9:35 AM)
- **15-minute ORB** (9:30-9:45 AM)
- **30-minute ORB** (9:30-10:00 AM)

#### For Each Timeframe, Calculates:

**Base Levels (4 columns per timeframe = 12 total)**:
- `ORB_{5m/15m/30m}_High`: Highest price during opening range
- `ORB_{5m/15m/30m}_Low`: Lowest price during opening range
- `ORB_{5m/15m/30m}_Mid`: 50% level (High + Low) / 2
- `ORB_{5m/15m/30m}_Range`: Range size (High - Low)

**Price Position (3 columns per timeframe = 9 total)**:
- `ORB_{5m/15m/30m}_High_Pct`: % distance from ORB high
- `ORB_{5m/15m/30m}_Low_Pct`: % distance from ORB low
- `ORB_{5m/15m/30m}_Mid_Pct`: % distance from ORB midpoint

**Trend Indicators (5 columns per timeframe = 15 total)**:
- `ORB_{5m/15m/30m}_Broke_High`: 1 if price broke above ORB high (bullish breakout)
- `ORB_{5m/15m/30m}_Broke_Low`: 1 if price broke below ORB low (bearish breakdown)
- `ORB_{5m/15m/30m}_Within_Range`: 1 if price is within ORB (sideways/neutral)
- `ORB_{5m/15m/30m}_Trend`: 1 = bullish, -1 = bearish, 0 = neutral
- `ORB_{5m/15m/30m}_Distance`: Distance from ORB range (0 if within range)

**Total ORB Columns**: 36 columns per timeframe × 3 = **108 total ORB columns**

### 2. Order Blocks

Order blocks are consolidation zones (low volatility areas) that often act as support/resistance. They're identified by detecting periods of low volatility followed by breakouts.

#### Detection Logic:
1. Calculate volatility using ATR (or price range if ATR not available)
2. Identify zones where volatility < 30% of rolling average (consolidation)
3. Track 3-bar consolidation patterns
4. Forward-fill blocks for next 20 bars (blocks remain relevant)

#### Order Block Columns (7 total):
- `Order_Block_Zone`: 1 if currently in low volatility consolidation
- `Order_Block_High`: Upper boundary of order block
- `Order_Block_Low`: Lower boundary of order block
- `Order_Block_Mid`: 50% level of order block
- `Order_Block_Position`: 1 = above block, 0 = within, -1 = below
- `Order_Block_Distance`: Distance from block (0 if within)
- `Order_Block_Test`: 1 if price is testing the block (within 0.1%)

**Total Order Block Columns**: **7 columns**

## Total New Columns Added

- **115 new columns** in enhanced data file (108 ORB + 7 Order Blocks)
- **69 columns** added to signal data export:
  - 21 ORB columns (7 per timeframe × 3 timeframes)
  - 6 Order Block columns

## Use Cases

### 1. ORB Trend Analysis

Identify if successful trades correlate with:
- **Bullish ORB breakouts** (price above opening range)
- **Bearish ORB breakdowns** (price below opening range)
- **Neutral/ranging** days (price stays within opening range)
- **False breakouts** (broke range but reversed)

### 2. Multi-Timeframe Confirmation

Find patterns where multiple ORB timeframes align:
- 5m, 15m, and 30m all show bullish trend = strong conviction
- Conflicting signals (5m bullish but 30m bearish) = choppy conditions
- Widening ORB ranges across timeframes = increasing volatility

### 3. ORB Support/Resistance

Identify if profitable signals occur when:
- Price tests ORB high as resistance, then breaks through (continuation)
- Price tests ORB low as support and bounces (reversal)
- Price hits ORB midpoint (50% retracement level)

### 4. Order Block Analysis

Find patterns where:
- Signals occur during order block tests (price testing support/resistance)
- Breakouts from order blocks lead to strong moves
- Failed tests of order blocks indicate reversals

### 5. Combining ORB + Order Blocks

Powerful confluence areas:
- ORB high/low aligns with order block boundary
- Price breaks ORB and reaches next order block
- Order block within ORB range acts as pivot

## Example Analysis Queries

```python
import pandas as pd

# Load signals with ORB and Order Block data
signals = pd.read_csv('data/historical_iwm_0824_0825_signals.csv')

# 1. Find CALL signals on bullish ORB breakouts (30m)
orb_bullish_calls = signals[
    (signals['trade_type'] == 'call') &
    (signals['entry_orb_30m_trend'] == 1) &  # Above 30m ORB
    (signals['entry_orb_30m_broke_high'] == 1)  # Broke ORB high
]
print(f"ORB bullish breakout calls: {len(orb_bullish_calls)}")
print(f"Win rate: {(orb_bullish_calls['return_pct'] > 0).mean():.2%}")
print(f"Avg return: {orb_bullish_calls['return_pct'].mean():.2f}%")

# 2. Find PUT signals on bearish ORB breakdowns
orb_bearish_puts = signals[
    (signals['trade_type'] == 'put') &
    (signals['entry_orb_30m_trend'] == -1) &  # Below 30m ORB
    (signals['entry_orb_30m_broke_low'] == 1)  # Broke ORB low
]
print(f"\nORB bearish breakdown puts: {len(orb_bearish_puts)}")
print(f"Win rate: {(orb_bearish_puts['return_pct'] > 0).mean():.2%}")

# 3. Find signals within ORB range (neutral/ranging days)
neutral_signals = signals[signals['entry_orb_30m_within_range'] == 1]
print(f"\nNeutral (within ORB) signals: {len(neutral_signals)}")
print(f"Win rate: {(neutral_signals['return_pct'] > 0).mean():.2%}")

# 4. Multi-timeframe ORB alignment
all_bullish = signals[
    (signals['entry_orb_5m_trend'] == 1) &
    (signals['entry_orb_15m_trend'] == 1) &
    (signals['entry_orb_30m_trend'] == 1)
]
print(f"\nAll timeframes bullish: {len(all_bullish)}")
print(f"Win rate: {(all_bullish['return_pct'] > 0).mean():.2%}")

# 5. Order block tests
ob_test_signals = signals[signals['entry_order_block_test'] == 1]
print(f"\nOrder block test signals: {len(ob_test_signals)}")
print(f"Win rate: {(ob_test_signals['return_pct'] > 0).mean():.2%}")
print(f"Avg return: {ob_test_signals['return_pct'].mean():.2f}%")

# 6. Order block + ORB confluence
confluence_signals = signals[
    (signals['entry_order_block_test'] == 1) &
    (signals['entry_orb_30m_broke_high'] == 1)
]
print(f"\nConfluence signals (OB test + ORB breakout): {len(confluence_signals)}")

# 7. Analyze ORB range size vs profitability
import numpy as np
correlation = np.corrcoef(
    signals['entry_orb_30m_range'].fillna(0),
    signals['return_pct']
)[0, 1]
print(f"\nCorrelation: ORB range size vs returns: {correlation:.3f}")

# 8. Compare ORB timeframes
print("\n=== ORB Timeframe Comparison ===")
for tf in ['5m', '15m', '30m']:
    bullish = signals[signals[f'entry_orb_{tf}_trend'] == 1]
    bearish = signals[signals[f'entry_orb_{tf}_trend'] == -1]
    neutral = signals[signals[f'entry_orb_{tf}_trend'] == 0]

    print(f"\n{tf} ORB:")
    print(f"  Bullish: {len(bullish)} signals, "
          f"{(bullish['return_pct'] > 0).mean():.1%} win rate")
    print(f"  Bearish: {len(bearish)} signals, "
          f"{(bearish['return_pct'] > 0).mean():.1%} win rate")
    print(f"  Neutral: {len(neutral)} signals, "
          f"{(neutral['return_pct'] > 0).mean():.1%} win rate")
```

## Trading Insights from ORB

### Classic ORB Strategies:

1. **ORB Breakout Strategy**:
   - Wait for price to break above/below opening range
   - Enter in direction of breakout
   - Stop loss at opposite side of range
   - Target: 1-2x ORB range size

2. **ORB Fade Strategy** (contrarian):
   - Enter when price reaches extreme of ORB
   - Bet on return to midpoint
   - Works best in ranging markets

3. **ORB Retest Strategy**:
   - Wait for breakout
   - Enter on pullback to ORB high/low (now support/resistance)
   - Reduced risk entry point

### Order Block Insights:

1. **Support/Resistance Zones**:
   - Order blocks act like institutional supply/demand zones
   - Price often respects these levels

2. **Breakout Confirmation**:
   - Clean break of order block = strong signal
   - Failed test of order block = reversal signal

3. **Entry Refinement**:
   - Enter at order block boundaries for better risk/reward
   - Tighter stops when using order blocks

## Integration with Existing Features

ORB and Order Block data works synergistically with:

- **Historical Levels**: Previous day high near 30m ORB high = strong resistance
- **RSI/Momentum**: ORB breakout + RSI < 50 (for calls) = pullback entry
- **VWAP**: Price above VWAP + ORB breakout = trending strength
- **Volume**: High RVOL on ORB breakout = institutional participation

## Performance Notes

- ORB levels are calculated per-day using time-based grouping
- Market open is hardcoded to 9:30 AM EST
- Pre-market data is ignored for ORB calculation
- Order blocks use 20-bar lookback by default (configurable)
- Forward-fill limit of 20 bars for order blocks (they expire)

## Files Modified

- `iwm_analysis.py`: Added `calculate_order_blocks_and_orb()` method
- `iwm_analysis.py`: Added `_calculate_orb()` helper method
- `iwm_analysis.py`: Added `_calculate_order_blocks()` helper method
- `iwm_analysis.py`: Integrated into `add_technical_indicators()` as step 9/11
- `iwm_analysis.py`: Enhanced signal data export with ORB and OB fields

## Output Files

When you run `python iwm_analysis.py`, enhanced files contain:

1. `data/historical_iwm_0824_0825_with_indicators.csv`:
   - All 115 ORB and Order Block columns
   - Available for custom analysis

2. `data/historical_iwm_0824_0825_signals.csv`:
   - 69 ORB/OB columns per signal
   - Ready for correlation and pattern analysis

## Testing

The features are automatically tested when running:
```bash
python iwm_analysis.py
```

Look for validation output in step 10/11:
```
ORB & Order Blocks:
    ORB_5m_High: XXX valid values
    ORB_15m_High: XXX valid values
    ORB_30m_High: XXX valid values
    Order_Block_High: XXX valid values
```

## Future Enhancements

Potential additions:
1. **Variable ORB Periods**: Make timeframes configurable (1m, 10m, 60m, etc.)
2. **ORB Extensions**: Calculate Fibonacci extensions of ORB range
3. **Volume Profile in ORB**: Identify high-volume nodes within opening range
4. **Enhanced Order Blocks**: Detect bullish vs bearish order blocks
5. **Order Block Strength**: Score blocks based on volume and duration
6. **Multi-Day ORB**: Compare current ORB to previous days

## Key Insights for Analysis

After running analysis, focus on:

1. **ORB Trend Direction**: Do your profitable trades align with ORB breakouts?
2. **Timeframe Confirmation**: Is 30m ORB more reliable than 5m?
3. **Range Size**: Do larger ORB ranges predict larger moves?
4. **Order Block Tests**: Do bounces off order blocks work better than breakouts?
5. **Confluence Areas**: What happens when ORB aligns with other levels?

## Summary

With Historical Levels (80 cols), ORB (108 cols), and Order Blocks (7 cols), you now have **195 new feature columns** providing comprehensive context about:
- Support and resistance levels
- Trend direction (intraday and multi-day)
- Consolidation zones
- Breakout/breakdown events
- Price positioning relative to key levels

These features should significantly enhance your ability to identify predictive patterns for successful trades!
