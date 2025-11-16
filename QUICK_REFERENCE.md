# IWM Analysis - Quick Reference Guide

## New Features at a Glance

### Historical Levels (80 columns)
```python
# Previous period levels
Prev_Day_High, Prev_Day_Low, Prev_Day_HL_Mid
Prev_Week_High, Prev_Week_Low, Prev_Week_HL_Mid
Prev_Month_High, Prev_Month_Low, Prev_Month_HL_Mid
Prev_Year_High, Prev_Year_Low, Prev_Year_HL_Mid

# Price position (%)
Prev_Day_High_Pct, Prev_Day_Low_Pct
Prev_Week_High_Pct, Prev_Week_Low_Pct
# ... etc

# Breakout flags (1 or 0)
Broke_Prev_Day_High, Broke_Prev_Day_Low
Broke_Prev_Week_High, Broke_Prev_Week_Low
# ... etc

# At level flags (1 or 0)
At_Prev_Day_High, At_Prev_Day_Low
At_Prev_Week_HL_Mid
# ... etc
```

### ORB - Opening Range Breakout (108 columns)
```python
# For each timeframe (5m, 15m, 30m)
ORB_{5m/15m/30m}_High, _Low, _Mid, _Range

# Price position
ORB_{5m/15m/30m}_High_Pct, _Low_Pct, _Mid_Pct

# Trend indicators
ORB_{5m/15m/30m}_Trend  # 1=bullish, -1=bearish, 0=neutral
ORB_{5m/15m/30m}_Broke_High  # 1 if broke above
ORB_{5m/15m/30m}_Broke_Low   # 1 if broke below
ORB_{5m/15m/30m}_Within_Range  # 1 if sideways
ORB_{5m/15m/30m}_Distance  # Distance from range
```

### Order Blocks (7 columns)
```python
Order_Block_High, Order_Block_Low, Order_Block_Mid
Order_Block_Position  # 1=above, 0=within, -1=below
Order_Block_Distance  # Distance from block
Order_Block_Test  # 1 if testing the block
Order_Block_Zone  # 1 if in consolidation
```

## Common Analysis Patterns

### 1. Breakout Confirmation
```python
# CALL on bullish breakout with multiple confirmations
signals[
    (signals['trade_type'] == 'call') &
    (signals['entry_broke_prev_day_high'] == 1) &  # Broke resistance
    (signals['entry_orb_30m_trend'] == 1) &  # Bullish session
    (signals['entry_rsi'] < 70)  # Not overbought
]
```

### 2. Support Bounce
```python
# CALL at previous week low (support test)
signals[
    (signals['trade_type'] == 'call') &
    (signals['entry_at_prev_week_low'] == 1) &  # At support
    (signals['entry_rsi'] < 50)  # Oversold
]
```

### 3. Resistance Rejection
```python
# PUT at previous day high (resistance test)
signals[
    (signals['trade_type'] == 'put') &
    (signals['entry_at_prev_day_high'] == 1) &  # At resistance
    (signals['entry_rsi'] > 50)  # Overbought
]
```

### 4. ORB Trend Following
```python
# Trade with ORB trend
bullish_orb = signals[
    (signals['entry_orb_30m_trend'] == 1) &  # Bullish
    (signals['entry_orb_30m_broke_high'] == 1)  # Broke ORB
]

bearish_orb = signals[
    (signals['entry_orb_30m_trend'] == -1) &  # Bearish
    (signals['entry_orb_30m_broke_low'] == 1)  # Broke ORB
]
```

### 5. Order Block Tests
```python
# Signals testing order blocks
signals[signals['entry_order_block_test'] == 1]

# Above order block (cleared resistance)
signals[signals['entry_order_block_position'] == 1]

# Below order block (failed support)
signals[signals['entry_order_block_position'] == -1]
```

### 6. Multi-Timeframe ORB
```python
# All ORB timeframes bullish
signals[
    (signals['entry_orb_5m_trend'] == 1) &
    (signals['entry_orb_15m_trend'] == 1) &
    (signals['entry_orb_30m_trend'] == 1)
]

# ORB conflict (choppy)
signals[
    (signals['entry_orb_5m_trend'] == 1) &
    (signals['entry_orb_30m_trend'] == -1)
]
```

### 7. Level Confluence
```python
# Previous day high near previous week high
signals[
    (signals['entry_at_prev_day_high'] == 1) &
    (abs(signals['entry_vs_prev_week_high_pct']) < 0.5)  # Within 0.5%
]
```

## Win Rate Analysis Template

```python
import pandas as pd

signals = pd.read_csv('data/historical_iwm_0824_0825_signals.csv')

def analyze_pattern(df, name):
    """Analyze pattern performance"""
    if len(df) == 0:
        print(f"{name}: No signals found")
        return

    win_rate = (df['return_pct'] > 0).mean()
    avg_return = df['return_pct'].mean()
    profitable = df[df['return_pct'] > 0]
    losing = df[df['return_pct'] <= 0]

    print(f"\n{name}")
    print(f"  Total signals: {len(df)}")
    print(f"  Win rate: {win_rate:.1%}")
    print(f"  Avg return: {avg_return:.2f}%")
    print(f"  Avg winner: {profitable['return_pct'].mean():.2f}%")
    print(f"  Avg loser: {losing['return_pct'].mean():.2f}%")
    print(f"  Best trade: {df['return_pct'].max():.2f}%")
    print(f"  Worst trade: {df['return_pct'].min():.2f}%")

# Example usage
calls = signals[signals['trade_type'] == 'call']
puts = signals[signals['trade_type'] == 'put']

analyze_pattern(calls, "All CALL Signals")
analyze_pattern(puts, "All PUT Signals")

# Specific patterns
day_high_breakout = calls[calls['entry_broke_prev_day_high'] == 1]
analyze_pattern(day_high_breakout, "CALL: Day High Breakout")

orb_bullish = calls[calls['entry_orb_30m_trend'] == 1]
analyze_pattern(orb_bullish, "CALL: Bullish ORB")
```

## Correlation Analysis Template

```python
import numpy as np
import pandas as pd

signals = pd.read_csv('data/historical_iwm_0824_0825_signals.csv')

# Features to analyze
features = [
    'entry_vs_prev_day_high_pct',
    'entry_vs_prev_day_low_pct',
    'entry_vs_prev_week_high_pct',
    'entry_orb_5m_distance',
    'entry_orb_15m_distance',
    'entry_orb_30m_distance',
    'entry_order_block_distance',
    'entry_rsi',
    'entry_atr',
]

print("Correlation with Returns:")
print("-" * 50)

correlations = []
for feat in features:
    if feat in signals.columns:
        # Remove NaN values
        valid_data = signals[[feat, 'return_pct']].dropna()

        if len(valid_data) > 10:
            corr = np.corrcoef(valid_data[feat], valid_data['return_pct'])[0, 1]
            correlations.append({
                'feature': feat,
                'correlation': corr,
                'abs_corr': abs(corr)
            })

# Sort by absolute correlation
corr_df = pd.DataFrame(correlations).sort_values('abs_corr', ascending=False)

for _, row in corr_df.iterrows():
    print(f"{row['feature']:35s}: {row['correlation']:+.3f}")
```

## Quick Commands

```bash
# Run full analysis (all data)
python iwm_analysis.py -all

# Run limited analysis (last 2 months)
python iwm_analysis.py -months 2

# Test historical levels
python test_historical_levels.py

# Analyze signals
python -c "
import pandas as pd
signals = pd.read_csv('data/historical_iwm_0824_0825_signals.csv')
print(f'Total signals: {len(signals)}')
print(f'CALL signals: {len(signals[signals[\"trade_type\"]==\"call\"])}')
print(f'PUT signals: {len(signals[signals[\"trade_type\"]==\"put\"])}')
print(f'Win rate: {(signals[\"return_pct\"] > 0).mean():.1%}')
"
```

## Column Naming Convention

### Entry Columns (in signals CSV)
- `entry_*`: Values at signal entry time
- `entry_broke_*`: Binary flags (1 or 0)
- `entry_at_*`: At-level flags (1 or 0)
- `entry_vs_*_pct`: Percentage distance from level
- `entry_orb_*_trend`: Trend direction (1, 0, -1)
- `entry_order_block_*`: Order block data

### Historical Level Columns
- `Prev_*`: Previous period data
- `Broke_*`: Breakout/breakdown flags
- `At_*`: At-level flags
- `*_Pct`: Percentage distance

### ORB Columns
- `ORB_5m_*`: 5-minute ORB data
- `ORB_15m_*`: 15-minute ORB data
- `ORB_30m_*`: 30-minute ORB data

## Documentation Files

- [iwm_analysis_overview.md](iwm_analysis_overview.md) - Complete overview
- [HISTORICAL_LEVELS_FEATURE.md](HISTORICAL_LEVELS_FEATURE.md) - Historical levels docs
- [ORB_AND_ORDER_BLOCKS_FEATURE.md](ORB_AND_ORDER_BLOCKS_FEATURE.md) - ORB/OB docs
- [NEW_FEATURES_SUMMARY.md](NEW_FEATURES_SUMMARY.md) - Feature summary
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - This file

## Tips

1. **Start Small**: Use `-months 2` for faster iterations
2. **Combine Features**: Look for confluence (multiple confirmations)
3. **Test Patterns**: Use `analyze_pattern()` function for each pattern
4. **Check Correlations**: Find which features matter most
5. **Validate**: Test patterns on different time periods
6. **Document**: Keep track of what works in your trading journal

## Next Steps

1. Run: `python iwm_analysis.py -months 2`
2. Load signals: `signals = pd.read_csv('data/historical_iwm_0824_0825_signals.csv')`
3. Test patterns using examples above
4. Find your edge: Which patterns have best win rate?
5. Integrate into live trading: Update `iwm_trading_alerts.py`
