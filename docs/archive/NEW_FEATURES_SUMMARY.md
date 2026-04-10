# IWM Analysis New Features Summary

## Overview

Major enhancements have been added to `iwm_analysis.py` to provide comprehensive support/resistance analysis, trend identification, and pattern recognition.

## Features Added (December 2024)

### 1. Historical Levels Feature
- **Documentation**: [HISTORICAL_LEVELS_FEATURE.md](HISTORICAL_LEVELS_FEATURE.md)
- **Columns Added**: 80
- **Test Script**: `test_historical_levels.py`

Tracks previous period levels (day, week, month, year) including:
- High, Low, Open, Close for each period
- 50% midpoint levels (HL_Mid, OC_Mid)
- Price position relative to each level (% distance)
- Breakout/breakdown flags
- At-level indicators (within 0.1% tolerance)

### 2. Opening Range Breakout (ORB) Feature
- **Documentation**: [ORB_AND_ORDER_BLOCKS_FEATURE.md](ORB_AND_ORDER_BLOCKS_FEATURE.md)
- **Columns Added**: 108
- **Timeframes**: 5min, 15min, 30min

Calculates opening range and tracks:
- ORB high, low, mid for each timeframe
- Price position relative to ORB
- Breakout/breakdown flags
- Trend direction (bullish/bearish/neutral)
- Distance from ORB range

### 3. Order Blocks Feature
- **Documentation**: [ORB_AND_ORDER_BLOCKS_FEATURE.md](ORB_AND_ORDER_BLOCKS_FEATURE.md)
- **Columns Added**: 7

Identifies consolidation zones that act as support/resistance:
- Order block boundaries (high, low, mid)
- Price position relative to block
- Block test indicators
- Distance from block

## Total Impact

### Data File Enhancements
- **195 new columns** in enhanced data file:
  - 80 Historical Levels
  - 108 ORB (36 per timeframe × 3)
  - 7 Order Blocks

### Signal Export Enhancements
- **117 new columns** in signals CSV:
  - 48 Historical Level columns
  - 63 ORB columns (21 per timeframe × 3)
  - 6 Order Block columns

### Processing Steps
Updated from 9 to **11 steps**:
1. ATR
2. RSI
3. EMAs
4. VWAP
5. RVOL
6. OBV
7. Stochastic RSI
8. **Historical Levels** (NEW)
9. **ORB & Order Blocks** (NEW)
10. Validation
11. Complete

## Quick Start

### Running Enhanced Analysis

```bash
# Run full analysis with all new features
python iwm_analysis.py

# Test historical levels only
python test_historical_levels.py

# Run with time limit (recommended for testing)
python iwm_analysis.py -months 2
```

### Output Files

1. **data/historical_iwm_0824_0825_with_indicators.csv**
   - Contains all 195 new feature columns
   - Use for custom analysis and visualization

2. **data/historical_iwm_0824_0825_signals.csv**
   - Contains all 117 new signal columns
   - Ready for machine learning and pattern analysis

## Analysis Opportunities

### 1. Level-Based Analysis

```python
import pandas as pd

signals = pd.read_csv('data/historical_iwm_0824_0825_signals.csv')

# Find CALL signals that broke previous day high
day_high_breakouts = signals[
    (signals['trade_type'] == 'call') &
    (signals['entry_broke_prev_day_high'] == 1)
]

# Calculate win rate
win_rate = (day_high_breakouts['return_pct'] > 0).mean()
print(f"Day high breakout CALLs win rate: {win_rate:.2%}")
```

### 2. ORB Trend Analysis

```python
# Bullish ORB days vs Bearish ORB days
bullish_orb = signals[signals['entry_orb_30m_trend'] == 1]
bearish_orb = signals[signals['entry_orb_30m_trend'] == -1]
neutral_orb = signals[signals['entry_orb_30m_trend'] == 0]

print(f"Bullish ORB win rate: {(bullish_orb['return_pct'] > 0).mean():.2%}")
print(f"Bearish ORB win rate: {(bearish_orb['return_pct'] > 0).mean():.2%}")
print(f"Neutral ORB win rate: {(neutral_orb['return_pct'] > 0).mean():.2%}")
```

### 3. Confluence Analysis

```python
# Find signals with multiple confirmations
confluence = signals[
    (signals['entry_broke_prev_day_high'] == 1) &  # Broke prev day high
    (signals['entry_orb_30m_trend'] == 1) &  # ORB bullish
    (signals['entry_order_block_position'] == 1)  # Above order block
]

print(f"High confluence signals: {len(confluence)}")
print(f"Win rate: {(confluence['return_pct'] > 0).mean():.2%}")
print(f"Avg return: {confluence['return_pct'].mean():.2f}%")
```

### 4. Support/Resistance Testing

```python
# Signals at previous week 50% retracement
week_mid_tests = signals[signals['entry_at_prev_week_hl_mid'] == 1]

# Signals testing order blocks
ob_tests = signals[signals['entry_order_block_test'] == 1]

# Compare win rates
print(f"Week mid tests: {len(week_mid_tests)} ({(week_mid_tests['return_pct'] > 0).mean():.2%})")
print(f"Order block tests: {len(ob_tests)} ({(ob_tests['return_pct'] > 0).mean():.2%})")
```

### 5. Feature Correlation Analysis

```python
import numpy as np

# Correlations with returns
features = [
    'entry_vs_prev_day_high_pct',
    'entry_vs_prev_week_high_pct',
    'entry_orb_30m_distance',
    'entry_order_block_distance'
]

print("Feature Correlations with Returns:")
for feat in features:
    if feat in signals.columns:
        corr = np.corrcoef(
            signals[feat].fillna(0),
            signals['return_pct']
        )[0, 1]
        print(f"  {feat}: {corr:.3f}")
```

## Key Questions to Answer

### Historical Levels
1. Do profitable trades happen more at level breakouts or level tests?
2. Which period (day/week/month) levels are most predictive?
3. Are 50% retracement levels meaningful?
4. Does breaking multiple levels indicate stronger moves?

### ORB Analysis
1. Which ORB timeframe (5m/15m/30m) is most reliable?
2. Do ORB breakouts or fades work better for your strategy?
3. Is there an optimal ORB range size?
4. Do multi-timeframe confirmations improve win rate?

### Order Blocks
1. Are order block tests good entry points?
2. Do breakouts from order blocks predict larger moves?
3. Should order blocks be combined with other indicators?

### Confluence
1. What combination of features gives highest win rate?
2. Are there diminishing returns with too many confirmations?
3. Which confluence patterns have best risk/reward?

## Integration with Existing Analysis

These new features complement existing technical indicators:

### For CALL Signals, Look For:
- RSI 25-50 (oversold to neutral)
- Price > VWAP (strength)
- Price > EMA9 (short-term uptrend)
- **Broke previous day high** (NEW - breakout)
- **ORB 30m trend = 1** (NEW - bullish session)
- **At previous week low** (NEW - bouncing off support)
- **Above order block** (NEW - cleared resistance)

### For PUT Signals, Look For:
- RSI 50-75 (overbought)
- Price < VWAP (weakness)
- Price < EMA9 (short-term downtrend)
- **Broke previous day low** (NEW - breakdown)
- **ORB 30m trend = -1** (NEW - bearish session)
- **At previous week high** (NEW - rejection at resistance)
- **Below order block** (NEW - failed support test)

## Machine Learning Applications

The 195 new features enable:

### 1. Classification Models
```python
from sklearn.ensemble import RandomForestClassifier

# Prepare features
feature_cols = [col for col in signals.columns
                if col.startswith('entry_')
                and col not in ['entry_time', 'entry_price']]

X = signals[feature_cols].fillna(0)
y = (signals['return_pct'] > 0).astype(int)  # Binary: profitable or not

# Train model
model = RandomForestClassifier(n_estimators=100)
model.fit(X, y)

# Feature importance
importances = pd.DataFrame({
    'feature': feature_cols,
    'importance': model.feature_importances_
}).sort_values('importance', ascending=False)

print("Top 10 Most Important Features:")
print(importances.head(10))
```

### 2. Regression Models
```python
from sklearn.ensemble import GradientBoostingRegressor

# Predict return magnitude
y_return = signals['return_pct']

model = GradientBoostingRegressor(n_estimators=100)
model.fit(X, y_return)

# Predict on new data
predictions = model.predict(X)
```

### 3. Clustering Analysis
```python
from sklearn.cluster import KMeans

# Find pattern clusters
kmeans = KMeans(n_clusters=5)
signals['cluster'] = kmeans.fit_predict(X)

# Analyze each cluster
for i in range(5):
    cluster_data = signals[signals['cluster'] == i]
    print(f"\nCluster {i}:")
    print(f"  Count: {len(cluster_data)}")
    print(f"  Win rate: {(cluster_data['return_pct'] > 0).mean():.2%}")
    print(f"  Avg return: {cluster_data['return_pct'].mean():.2f}%")
```

## Documentation

- **[iwm_analysis_overview.md](iwm_analysis_overview.md)**: Overview of all analysis scripts
- **[HISTORICAL_LEVELS_FEATURE.md](HISTORICAL_LEVELS_FEATURE.md)**: Historical levels documentation
- **[ORB_AND_ORDER_BLOCKS_FEATURE.md](ORB_AND_ORDER_BLOCKS_FEATURE.md)**: ORB and Order Blocks documentation
- **[NEW_FEATURES_SUMMARY.md](NEW_FEATURES_SUMMARY.md)**: This file

## Performance Notes

- Full analysis with all features takes longer (expect 2-3x processing time)
- Use `-months 2` flag for faster testing iterations
- Order block calculation uses loop (could be optimized further)
- ORB calculation is per-day, scales linearly with data size

## Next Steps

1. **Run Analysis**: `python iwm_analysis.py -months 2`
2. **Explore Data**: Load CSV and examine new columns
3. **Test Hypotheses**: Use provided code examples to test patterns
4. **Iterate**: Refine features based on findings
5. **Integrate**: Update `iwm_trading_alerts.py` with best patterns

## Future Enhancements

Potential additions:
1. **Fibonacci Levels**: Retracements and extensions
2. **Volume Profile**: High volume nodes as support/resistance
3. **Pivot Points**: Traditional, Fibonacci, Camarilla
4. **Market Structure**: Higher highs/lows, swing points
5. **Session Analysis**: Asia/London/NY session levels
6. **Multi-Asset Correlation**: SPY/QQQ levels impact on IWM

## Summary

You now have **195 new feature columns** providing comprehensive analysis of:
- ✓ Support and resistance levels (multiple timeframes)
- ✓ Breakout/breakdown events
- ✓ Trend direction (intraday and multi-day)
- ✓ Consolidation zones
- ✓ Price positioning relative to key levels
- ✓ Level confluence and confirmations

These features should significantly enhance your ability to identify predictive patterns and improve trading signal accuracy!
