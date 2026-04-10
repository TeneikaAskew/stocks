# Adding Historical Levels, ORB, and Order Blocks to Criteria Analysis

## Problem

The trade analysis pipeline currently only includes **basic technical indicators** (RSI, VWAP, RVOL, ATR, EMAs, StochRSI, OBV) when enriching trades and generating criteria analysis.

The **195 new feature columns** (Historical Levels, ORB, Order Blocks) are calculated by `iwm_analysis.py` and exist in the `historical_iwm_*_with_indicators.csv` file, but they are **NOT being joined** into the trade analysis pipeline.

---

## Where Changes Are Needed

### File: `trade_analysis_pipeline.py`

#### 1. **Step 3: Join with Indicators** (Lines 197-279)

**Current Code** (lines 226-228):
```python
entry_cols = ['Last', 'Volume', 'ATR14_W', 'RSI14_W', 'EMA9', 'EMA20', 'EMA50',
              'VWAP', 'RVOL20', 'RVOL_MOD', 'RVOL_MOD_EXCL', 'OBV',
              'StochRSI_K', 'StochRSI_D']
```

**Add New Columns**:
```python
entry_cols = ['Last', 'Volume', 'ATR14_W', 'RSI14_W', 'EMA9', 'EMA20', 'EMA50',
              'VWAP', 'RVOL20', 'RVOL_MOD', 'RVOL_MOD_EXCL', 'OBV',
              'StochRSI_K', 'StochRSI_D',

              # Historical Levels (Previous Day)
              'Prev_Day_High', 'Prev_Day_Low', 'Prev_Day_Open', 'Prev_Day_Close',
              'Prev_Day_HL_Mid', 'Prev_Day_OC_Mid',
              'Prev_Day_High_Pct', 'Prev_Day_Low_Pct',
              'Broke_Prev_Day_High', 'Broke_Prev_Day_Low',
              'At_Prev_Day_High', 'At_Prev_Day_Low', 'At_Prev_Day_HL_Mid',

              # Historical Levels (Previous Week)
              'Prev_Week_High', 'Prev_Week_Low', 'Prev_Week_Open', 'Prev_Week_Close',
              'Prev_Week_HL_Mid', 'Prev_Week_OC_Mid',
              'Prev_Week_High_Pct', 'Prev_Week_Low_Pct',
              'Broke_Prev_Week_High', 'Broke_Prev_Week_Low',
              'At_Prev_Week_High', 'At_Prev_Week_Low', 'At_Prev_Week_HL_Mid',

              # Historical Levels (Previous Month)
              'Prev_Month_High', 'Prev_Month_Low', 'Prev_Month_Open', 'Prev_Month_Close',
              'Prev_Month_HL_Mid', 'Prev_Month_OC_Mid',
              'Prev_Month_High_Pct', 'Prev_Month_Low_Pct',
              'Broke_Prev_Month_High', 'Broke_Prev_Month_Low',
              'At_Prev_Month_High', 'At_Prev_Month_Low', 'At_Prev_Month_HL_Mid',

              # ORB 5-minute
              'ORB_5m_High', 'ORB_5m_Low', 'ORB_5m_Mid', 'ORB_5m_Range',
              'ORB_5m_Trend', 'ORB_5m_Broke_High', 'ORB_5m_Broke_Low',
              'ORB_5m_Within_Range', 'ORB_5m_Distance_High', 'ORB_5m_Distance_Low',

              # ORB 15-minute
              'ORB_15m_High', 'ORB_15m_Low', 'ORB_15m_Mid', 'ORB_15m_Range',
              'ORB_15m_Trend', 'ORB_15m_Broke_High', 'ORB_15m_Broke_Low',
              'ORB_15m_Within_Range', 'ORB_15m_Distance_High', 'ORB_15m_Distance_Low',

              # ORB 30-minute
              'ORB_30m_High', 'ORB_30m_Low', 'ORB_30m_Mid', 'ORB_30m_Range',
              'ORB_30m_Trend', 'ORB_30m_Broke_High', 'ORB_30m_Broke_Low',
              'ORB_30m_Within_Range', 'ORB_30m_Distance_High', 'ORB_30m_Distance_Low',

              # Order Blocks
              'Order_Block_High', 'Order_Block_Low', 'Order_Block_Mid',
              'Order_Block_Position', 'Order_Block_Test', 'Order_Block_Distance'
]
```

**Location**: Around line 226-228

---

#### 2. **Step 6: Criteria Analysis** (Lines 651-898)

Add new criteria after the existing criteria sections. Insert **after line 853** (after StochRSI criteria):

##### A. Historical Levels - Breakout/Breakdown Criteria

```python
# Historical Levels - Breakout/Breakdown flags
print("Adding Historical Levels criteria...")

# Previous Day breakouts
new_columns['Entry_Broke_Prev_Day_High'] = (
    base_df.get('Entry_Broke_Prev_Day_High', pd.Series([0]*len(base_df)))
).astype(int)
new_columns['Entry_Broke_Prev_Day_Low'] = (
    base_df.get('Entry_Broke_Prev_Day_Low', pd.Series([0]*len(base_df)))
).astype(int)

# Previous Week breakouts
new_columns['Entry_Broke_Prev_Week_High'] = (
    base_df.get('Entry_Broke_Prev_Week_High', pd.Series([0]*len(base_df)))
).astype(int)
new_columns['Entry_Broke_Prev_Week_Low'] = (
    base_df.get('Entry_Broke_Prev_Week_Low', pd.Series([0]*len(base_df)))
).astype(int)

# Previous Month breakouts
new_columns['Entry_Broke_Prev_Month_High'] = (
    base_df.get('Entry_Broke_Prev_Month_High', pd.Series([0]*len(base_df)))
).astype(int)
new_columns['Entry_Broke_Prev_Month_Low'] = (
    base_df.get('Entry_Broke_Prev_Month_Low', pd.Series([0]*len(base_df)))
).astype(int)
```

##### B. Historical Levels - At Level Criteria

```python
# Historical Levels - At level flags (within 0.1% of key levels)
new_columns['Entry_At_Prev_Day_High'] = (
    base_df.get('Entry_At_Prev_Day_High', pd.Series([0]*len(base_df)))
).astype(int)
new_columns['Entry_At_Prev_Day_Low'] = (
    base_df.get('Entry_At_Prev_Day_Low', pd.Series([0]*len(base_df)))
).astype(int)
new_columns['Entry_At_Prev_Day_HL_Mid'] = (
    base_df.get('Entry_At_Prev_Day_HL_Mid', pd.Series([0]*len(base_df)))
).astype(int)

new_columns['Entry_At_Prev_Week_High'] = (
    base_df.get('Entry_At_Prev_Week_High', pd.Series([0]*len(base_df)))
).astype(int)
new_columns['Entry_At_Prev_Week_Low'] = (
    base_df.get('Entry_At_Prev_Week_Low', pd.Series([0]*len(base_df)))
).astype(int)
new_columns['Entry_At_Prev_Week_HL_Mid'] = (
    base_df.get('Entry_At_Prev_Week_HL_Mid', pd.Series([0]*len(base_df)))
).astype(int)

new_columns['Entry_At_Prev_Month_High'] = (
    base_df.get('Entry_At_Prev_Month_High', pd.Series([0]*len(base_df)))
).astype(int)
new_columns['Entry_At_Prev_Month_Low'] = (
    base_df.get('Entry_At_Prev_Month_Low', pd.Series([0]*len(base_df)))
).astype(int)
new_columns['Entry_At_Prev_Month_HL_Mid'] = (
    base_df.get('Entry_At_Prev_Month_HL_Mid', pd.Series([0]*len(base_df)))
).astype(int)
```

##### C. Historical Levels - Price Position Criteria

```python
# Historical Levels - Price position relative to previous levels
if 'Entry_Prev_Day_High_Pct' in base_df.columns:
    # Price within X% of previous day high
    day_high_pct_levels = [-2, -1, 0, 1, 2]  # % from level
    for level in day_high_pct_levels:
        new_columns[f'Entry_Within_{abs(level)}pct_Prev_Day_High'] = (
            (base_df['Entry_Prev_Day_High_Pct'] >= level - 0.5) &
            (base_df['Entry_Prev_Day_High_Pct'] <= level + 0.5)
        ).astype(int)

    # Price within X% of previous day low
    day_low_pct_levels = [-2, -1, 0, 1, 2]
    for level in day_low_pct_levels:
        new_columns[f'Entry_Within_{abs(level)}pct_Prev_Day_Low'] = (
            (base_df['Entry_Prev_Day_Low_Pct'] >= level - 0.5) &
            (base_df['Entry_Prev_Day_Low_Pct'] <= level + 0.5)
        ).astype(int)
```

##### D. ORB (Opening Range Breakout) Criteria

```python
# ORB - Trend direction
print("Adding ORB criteria...")

# ORB 5-minute
new_columns['Entry_ORB_5m_Bullish'] = (
    base_df.get('Entry_ORB_5m_Trend', pd.Series([0]*len(base_df))) == 1
).astype(int)
new_columns['Entry_ORB_5m_Bearish'] = (
    base_df.get('Entry_ORB_5m_Trend', pd.Series([0]*len(base_df))) == -1
).astype(int)
new_columns['Entry_ORB_5m_Neutral'] = (
    base_df.get('Entry_ORB_5m_Trend', pd.Series([0]*len(base_df))) == 0
).astype(int)

# ORB 5-minute breakouts
new_columns['Entry_ORB_5m_Broke_High'] = (
    base_df.get('Entry_ORB_5m_Broke_High', pd.Series([0]*len(base_df)))
).astype(int)
new_columns['Entry_ORB_5m_Broke_Low'] = (
    base_df.get('Entry_ORB_5m_Broke_Low', pd.Series([0]*len(base_df)))
).astype(int)
new_columns['Entry_ORB_5m_Within_Range'] = (
    base_df.get('Entry_ORB_5m_Within_Range', pd.Series([0]*len(base_df)))
).astype(int)

# ORB 15-minute
new_columns['Entry_ORB_15m_Bullish'] = (
    base_df.get('Entry_ORB_15m_Trend', pd.Series([0]*len(base_df))) == 1
).astype(int)
new_columns['Entry_ORB_15m_Bearish'] = (
    base_df.get('Entry_ORB_15m_Trend', pd.Series([0]*len(base_df))) == -1
).astype(int)
new_columns['Entry_ORB_15m_Neutral'] = (
    base_df.get('Entry_ORB_15m_Trend', pd.Series([0]*len(base_df))) == 0
).astype(int)

new_columns['Entry_ORB_15m_Broke_High'] = (
    base_df.get('Entry_ORB_15m_Broke_High', pd.Series([0]*len(base_df)))
).astype(int)
new_columns['Entry_ORB_15m_Broke_Low'] = (
    base_df.get('Entry_ORB_15m_Broke_Low', pd.Series([0]*len(base_df)))
).astype(int)
new_columns['Entry_ORB_15m_Within_Range'] = (
    base_df.get('Entry_ORB_15m_Within_Range', pd.Series([0]*len(base_df)))
).astype(int)

# ORB 30-minute
new_columns['Entry_ORB_30m_Bullish'] = (
    base_df.get('Entry_ORB_30m_Trend', pd.Series([0]*len(base_df))) == 1
).astype(int)
new_columns['Entry_ORB_30m_Bearish'] = (
    base_df.get('Entry_ORB_30m_Trend', pd.Series([0]*len(base_df))) == -1
).astype(int)
new_columns['Entry_ORB_30m_Neutral'] = (
    base_df.get('Entry_ORB_30m_Trend', pd.Series([0]*len(base_df))) == 0
).astype(int)

new_columns['Entry_ORB_30m_Broke_High'] = (
    base_df.get('Entry_ORB_30m_Broke_High', pd.Series([0]*len(base_df)))
).astype(int)
new_columns['Entry_ORB_30m_Broke_Low'] = (
    base_df.get('Entry_ORB_30m_Broke_Low', pd.Series([0]*len(base_df)))
).astype(int)
new_columns['Entry_ORB_30m_Within_Range'] = (
    base_df.get('Entry_ORB_30m_Within_Range', pd.Series([0]*len(base_df)))
).astype(int)
```

##### E. ORB - Distance Criteria

```python
# ORB - Distance from ORB levels
if 'Entry_ORB_5m_Distance_High' in base_df.columns:
    # Close to ORB high (within 0.1%)
    new_columns['Entry_Near_ORB_5m_High'] = (
        base_df['Entry_ORB_5m_Distance_High'].abs() <= 0.1
    ).astype(int)
    # Close to ORB low
    new_columns['Entry_Near_ORB_5m_Low'] = (
        base_df['Entry_ORB_5m_Distance_Low'].abs() <= 0.1
    ).astype(int)

if 'Entry_ORB_15m_Distance_High' in base_df.columns:
    new_columns['Entry_Near_ORB_15m_High'] = (
        base_df['Entry_ORB_15m_Distance_High'].abs() <= 0.1
    ).astype(int)
    new_columns['Entry_Near_ORB_15m_Low'] = (
        base_df['Entry_ORB_15m_Distance_Low'].abs() <= 0.1
    ).astype(int)

if 'Entry_ORB_30m_Distance_High' in base_df.columns:
    new_columns['Entry_Near_ORB_30m_High'] = (
        base_df['Entry_ORB_30m_Distance_High'].abs() <= 0.1
    ).astype(int)
    new_columns['Entry_Near_ORB_30m_Low'] = (
        base_df['Entry_ORB_30m_Distance_Low'].abs() <= 0.1
    ).astype(int)
```

##### F. Order Blocks Criteria

```python
# Order Blocks - Only keep the useful test flag
print("Adding Order Blocks criteria...")

# Order block test is the most useful criterion (indicates price is testing the block)
new_columns['Entry_Order_Block_Test'] = (
    base_df.get('Entry_Order_Block_Test', pd.Series([0]*len(base_df)))
).astype(int)

# Note: Position and Distance criteria removed as they're less useful
# The Order_Block_Position and Order_Block_Distance raw values are already
# available in the enriched data for reference if needed
```

##### G. Combined Setup Criteria (Update Existing)

**Modify the existing CALL/PUT setup criteria** (lines 799-833) to include new features:

```python
# Enhanced CALL setup with new features
new_columns['CALL_Full_Setup_Enhanced'] = (
    (new_columns['CALL_Bias_Met'] == 1) &
    (new_columns['CALL_Momentum_Met'] == 1) &
    (new_columns['Entry_RVOL_GTE_1.0'] == 1) &
    (
        (new_columns.get('Entry_ORB_30m_Bullish', pd.Series([0]*len(base_df))) == 1) |
        (new_columns.get('Entry_Broke_Prev_Day_High', pd.Series([0]*len(base_df))) == 1)
    )
).astype(int)

# Enhanced PUT setup with new features
new_columns['PUT_Full_Setup_Enhanced'] = (
    (new_columns['PUT_Bias_Met'] == 1) &
    (new_columns['PUT_Momentum_Met'] == 1) &
    (new_columns['Entry_RVOL_GTE_1.0'] == 1) &
    (
        (new_columns.get('Entry_ORB_30m_Bearish', pd.Series([0]*len(base_df))) == 1) |
        (new_columns.get('Entry_Broke_Prev_Day_Low', pd.Series([0]*len(base_df))) == 1)
    )
).astype(int)
```

---

## Summary of New Criteria Added

### Historical Levels Criteria (~30 new criteria)

1. **Breakout/Breakdown Flags** (6 criteria):
   - `Entry_Broke_Prev_Day_High`, `Entry_Broke_Prev_Day_Low`
   - `Entry_Broke_Prev_Week_High`, `Entry_Broke_Prev_Week_Low`
   - `Entry_Broke_Prev_Month_High`, `Entry_Broke_Prev_Month_Low`

2. **At Level Flags** (9 criteria):
   - `Entry_At_Prev_Day_High`, `Entry_At_Prev_Day_Low`, `Entry_At_Prev_Day_HL_Mid`
   - `Entry_At_Prev_Week_High`, `Entry_At_Prev_Week_Low`, `Entry_At_Prev_Week_HL_Mid`
   - `Entry_At_Prev_Month_High`, `Entry_At_Prev_Month_Low`, `Entry_At_Prev_Month_HL_Mid`

3. **Price Position** (~15 criteria):
   - `Entry_Within_Xpct_Prev_Day_High` (5 levels: 0%, 1%, 2%)
   - `Entry_Within_Xpct_Prev_Day_Low` (5 levels)
   - Similar for week/month levels (simplified to key levels only)

### ORB Criteria (~24 new criteria)

1. **Trend Direction** (9 criteria):
   - `Entry_ORB_5m_Bullish`, `Entry_ORB_5m_Bearish`, `Entry_ORB_5m_Neutral`
   - `Entry_ORB_15m_Bullish`, `Entry_ORB_15m_Bearish`, `Entry_ORB_15m_Neutral`
   - `Entry_ORB_30m_Bullish`, `Entry_ORB_30m_Bearish`, `Entry_ORB_30m_Neutral`

2. **Breakout/Breakdown** (9 criteria):
   - `Entry_ORB_5m_Broke_High`, `Entry_ORB_5m_Broke_Low`, `Entry_ORB_5m_Within_Range`
   - `Entry_ORB_15m_Broke_High`, `Entry_ORB_15m_Broke_Low`, `Entry_ORB_15m_Within_Range`
   - `Entry_ORB_30m_Broke_High`, `Entry_ORB_30m_Broke_Low`, `Entry_ORB_30m_Within_Range`

3. **Distance from ORB** (6 criteria):
   - `Entry_Near_ORB_5m_High`, `Entry_Near_ORB_5m_Low`
   - `Entry_Near_ORB_15m_High`, `Entry_Near_ORB_15m_Low`
   - `Entry_Near_ORB_30m_High`, `Entry_Near_ORB_30m_Low`

### Order Blocks Criteria (1 new criterion)

1. **Test** (1 criterion):
   - `Entry_Order_Block_Test` - Price is testing/bouncing off the order block

**Note**: Position and distance criteria removed as they're less informative without specifying which order block. The raw `Order_Block_Position` and `Order_Block_Distance` values remain available in the enriched data.

### Enhanced Setup Criteria (2 new criteria)

1. `CALL_Full_Setup_Enhanced` - Includes ORB bullish or breakout above prev day high
2. `PUT_Full_Setup_Enhanced` - Includes ORB bearish or breakdown below prev day low

---

## Total New Criteria

- **Historical Levels**: ~30 criteria
- **ORB**: ~24 criteria
- **Order Blocks**: 1 criterion
- **Enhanced Setups**: 2 criteria

**Total**: **~57 new binary criteria** to test

Combined with existing ~100 criteria = **~157 total criteria** for effectiveness analysis

---

## Expected Benefits

After adding these criteria, the trade analysis report will show:

1. **Which historical levels matter most**:
   - Do breakouts above previous day high predict success?
   - Are entries near previous week low more profitable?

2. **ORB effectiveness**:
   - Does entering during ORB bullish trend improve CALL returns?
   - Is breaking out of ORB 30-minute range a good signal?

3. **Order block relevance**:
   - Do order block tests predict reversals/bounces?

4. **Combined pattern success**:
   - CALL + ORB bullish + high RVOL = ?% avg return
   - PUT + broke prev day low + order block test = ?% win rate

---

## Implementation Steps

1. **Modify `step3_join_indicators()`** (line 226-228):
   - Add all new column names to `entry_cols` list

2. **Modify `step6_criteria_analysis()`** (after line 853):
   - Add Historical Levels criteria
   - Add ORB criteria
   - Add Order Blocks criteria
   - Update enhanced setup criteria

3. **Re-run pipeline**:
   ```bash
   python trade_analysis_pipeline.py -all
   ```

4. **Review updated report**:
   - Check `data/trade_analysis_report.md`
   - Look for new criteria in Top 20 rankings
   - Analyze effectiveness of new features

---

## Testing

After implementation, verify:

1. ✅ New columns appear in `data/trades_enriched.csv`
2. ✅ New criteria columns appear in `data/similar_trades_pipeline.csv`
3. ✅ New criteria tested in `data/criteria_effectiveness.csv`
4. ✅ Top 20 Criteria tables include new features if effective
5. ✅ No errors during pipeline execution

---

## Next Steps

Once implemented, the criteria analysis will reveal which of the 195 new features are actually predictive of successful trades, allowing you to:

1. Update signal generation in `iwm_analysis.py` with proven criteria
2. Build data-driven entry rules based on historical validation
3. Identify which combination of features has highest win rate and returns
