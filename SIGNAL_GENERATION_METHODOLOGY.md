# Signal Generation Methodology

## Overview

This document explains how trading signals are generated in `iwm_analysis.py` and how the current implementation compares to actual trade analysis from `data/trade_examples/trade_tracker.csv`.

**Created**: 2025-11-17
**Status**: Current implementation uses generic technical analysis rules that may not reflect actual trading patterns

---

## Current Signal Generation Logic

### Location
[`iwm_analysis.py:742-932`](iwm_analysis.py#L742-L932) - `generate_technical_signals()` method

### Current Approach

The current implementation generates signals based on **5 indicator conditions** that must meet a minimum threshold (3 out of 5 conditions).

#### CALL Signal Conditions (Lines 779-790)

| Condition | Threshold | Rationale |
|-----------|-----------|-----------|
| 1. Consecutive Up Moves | >= 3 periods | Momentum confirmation |
| 2. RSI Range | 25-50 | Not oversold, room to run |
| 3. StochRSI | < 80 | Not overbought |
| 4. Price vs VWAP | Above VWAP | Bullish bias |
| 5. Price vs EMA9 | Above EMA9 | Short-term uptrend |

**Signal Trigger**: At least 3/5 conditions met AND more CALL conditions than PUT conditions

#### PUT Signal Conditions (Lines 792-803)

| Condition | Threshold | Rationale |
|-----------|-----------|-----------|
| 1. Consecutive Down Moves | >= 3 periods | Momentum confirmation |
| 2. RSI Range | 50-75 | Not overbought, room to fall |
| 3. StochRSI | > 20 | Not oversold |
| 4. Price vs VWAP | Below VWAP | Bearish bias |
| 5. Price vs EMA9 | Below EMA9 | Short-term downtrend |

**Signal Trigger**: At least 3/5 conditions met AND more PUT conditions than CALL conditions

---

## Analysis of Actual Trades

### Data Source
- **File**: [`data/trade_examples/trade_tracker.csv`](data/trade_examples/trade_tracker.csv)
- **Analysis**: [`data/trade_analysis_report.md`](data/trade_analysis_report.md)
- **Period**: 2025-08-08 (single day, 12 trades)
- **Total Scenarios**: 36 (3 exit scenarios per trade: EXIT, STOP_LOSS, RUNNER)

### Actual Trade Statistics

#### CALL Trades (5 actual trades)
- **Win Rate**: 80.0%
- **Average Return**: 0.12%
- **Average Entry RSI**: 42.0
- **Average RVOL**: 4.74x (HIGH volume)
- **Price vs VWAP**: Only 1/5 (20%) above VWAP at entry

#### PUT Trades (7 actual trades)
- **Win Rate**: 85.7%
- **Average Return**: 0.20%
- **Average Entry RSI**: 55.2
- **Average RVOL**: 0.82x (NORMAL volume)
- **Price vs VWAP**: 5/7 (71%) above VWAP at entry

---

## Critical Discrepancies

### 1. CALL Signal: Price vs VWAP Contradiction

**Current Logic** (Line 787):
```python
if current['Last'] > current.get('VWAP', current['Last']):  # Price above VWAP
    call_conditions += 1
```

**Actual Trade Data**:
- Only **20% of actual CALL trades** had price above VWAP at entry
- This suggests the current logic is **backwards** or not how you actually trade

**Possible Explanation**:
- You may be buying dips (price below VWAP) for CALL entries
- The current "Price > VWAP" condition may be filtering out 80% of your actual CALL setups

### 2. PUT Signal: Price vs VWAP Pattern

**Current Logic** (Line 800):
```python
if current['Last'] < current.get('VWAP', current['Last']):  # Price below VWAP
    put_conditions += 1
```

**Actual Trade Data**:
- **71% of actual PUT trades** had price above VWAP at entry
- This suggests you take PUT trades when price is elevated (above VWAP)

**Possible Explanation**:
- You may be selling rallies (price above VWAP) for PUT entries
- The current "Price < VWAP" condition contradicts your actual trading pattern

### 3. RSI Ranges: Partially Aligned

**Current CALL Logic**: RSI 25-50
**Actual CALL Data**: RSI average 42.0 (range: 27.04 - 66.12)

**Current PUT Logic**: RSI 50-75
**Actual PUT Data**: RSI average 55.2 (range: 33.38 - 71.72)

**Assessment**: RSI ranges are **somewhat aligned** but may be too restrictive. Actual trades show wider RSI ranges than current filters.

### 4. Volume (RVOL): Major Difference for CALLs

**Current Logic**: No RVOL condition in the 5 signal conditions

**Actual CALL Data**: Average RVOL = **4.74x** (very high)
**Actual PUT Data**: Average RVOL = **0.82x** (below average)

**Implication**:
- CALL trades may require **high volume** confirmation (RVOL > 3.0x or 5.0x)
- Current logic is missing this critical filter
- Trade Analysis Report shows "Entry_RVOL_GTE_5.0" had 0.36% avg return for CALLs

---

## What the Trade Analysis Report Shows

### Top Criteria for CALL Trades (from report)

| Rank | Criterion | Trades | Win Rate | Avg Return | Current Implementation |
|------|-----------|--------|----------|------------|------------------------|
| 1 | Exit RSI > 80 | 506 | 100.0% | 0.98% | ❌ Not used |
| 2 | Return > 0.5% | 2,121 | 100.0% | 0.91% | ⚠️ Lookahead only |
| 3 | Exit RVOL >= 3.0 | 635 | 100.0% | 0.61% | ❌ Not used |
| 4 | Entry OBV Bottom 20% | 1,826 | 100.0% | 0.52% | ❌ Not used |
| 5 | Entry ATR >= 0.2 | 5,639 | 100.0% | 0.47% | ❌ Not used |
| 6 | Time 9:30-10:00 AM | 1,953 | 100.0% | 0.44% | ❌ Not used |
| 14 | Entry RVOL >= 5.0 | 145 | 100.0% | 0.36% | ❌ Not used |
| 16 | Entry RSI < 30 | 222 | 100.0% | 0.36% | ⚠️ Partial (25-50 range) |

### Top Criteria for PUT Trades (from report)

| Rank | Criterion | Trades | Win Rate | Avg Return | Current Implementation |
|------|-----------|--------|----------|------------|------------------------|
| 1 | Return > 0.5% | 3,743 | 100.0% | 0.83% | ⚠️ Lookahead only |
| 2 | Exit RSI < 20 | 691 | 100.0% | 0.69% | ❌ Not used |
| 3 | Entry OBV Bottom 20% | 1,663 | 100.0% | 0.60% | ❌ Not used |
| 5 | Entry RVOL >= 5.0 | 156 | 100.0% | 0.54% | ❌ Not used (contradicts data) |
| 6 | Entry ATR >= 0.2 | 5,149 | 100.0% | 0.54% | ❌ Not used |
| 7 | Time 9:30-10:00 AM | 1,958 | 100.0% | 0.51% | ❌ Not used |

---

## Why Current Logic May Be "Arbitrary"

### 1. Not Data-Driven
The current thresholds (RSI 25-50 for calls, 50-75 for puts, StochRSI 80/20, etc.) appear to be **generic technical analysis rules** rather than values derived from analyzing your actual trades.

### 2. Missing High-Impact Criteria
According to the trade analysis report, the following criteria had **high win rates and returns** but are **not used** in current signal generation:

**Missing from Current Logic**:
- Entry/Exit RVOL thresholds
- Entry ATR thresholds (>= 0.15, >= 0.2)
- OBV position (bottom 20%, 40%, 60% of range)
- Time-of-day filtering (9:30-10:00 AM prime time)
- Exit RSI extremes (RSI > 80 for calls, RSI < 20 for puts)

### 3. Contradictory Logic
The current VWAP conditions appear to **contradict** actual trading patterns:
- Current: CALL when price > VWAP
- Actual: 80% of CALLs entered when price < VWAP (buying dips)

---

## Recommended Approach: Data-Driven Signal Generation

### Step 1: Analyze Full Trade Dataset
The current analysis is based on **only 12 trades from a single day**. To build robust signal logic:

1. **Expand trade tracking**: Add more trades to `trade_tracker.csv` across multiple days/weeks
2. **Run comprehensive analysis**: Use `trade_analysis_pipeline.py` to find patterns
3. **Identify discriminating indicators**: Find which indicators differ most between winning/losing trades

### Step 2: Reverse-Engineer Your Actual Entry Criteria

Based on the limited data available, your **actual entry patterns** appear to be:

#### CALL Entries (Contrarian Dip-Buying)
```python
# Potential actual logic (needs validation with more data)
call_conditions = 0

# High volume confirmation (MISSING from current logic)
if current['RVOL20'] >= 3.0:  # or 5.0
    call_conditions += 1

# Price below VWAP (buying dip) - OPPOSITE of current logic
if current['Last'] < current.get('VWAP', current['Last']):
    call_conditions += 1

# RSI not too low (current logic partially correct)
if 30 < current['RSI14_W'] < 50:
    call_conditions += 1

# High volatility (ATR) - MISSING from current logic
if current.get('ATR14_W', 0) >= 0.15:
    call_conditions += 1

# OBV in bottom range (selling pressure exhausted) - MISSING
if current.get('OBV_Percentile', 50) <= 40:
    call_conditions += 1

# Prime time window - MISSING
hour = pd.to_datetime(current['Time']).hour
minute = pd.to_datetime(current['Time']).minute
if (hour == 9 and minute >= 30) or hour == 10 and minute == 0:
    call_conditions += 1
```

#### PUT Entries (Selling Rallies)
```python
# Potential actual logic (needs validation with more data)
put_conditions = 0

# Price above VWAP (selling rally) - OPPOSITE of current logic
if current['Last'] > current.get('VWAP', current['Last']):
    put_conditions += 1

# Normal/low volume - DIFFERENT from CALL logic
if current['RVOL20'] < 1.5:
    put_conditions += 1

# RSI elevated - CURRENT logic may be correct
if 50 < current['RSI14_W'] < 75:
    put_conditions += 1

# High volatility (ATR) - MISSING from current logic
if current.get('ATR14_W', 0) >= 0.15:
    put_conditions += 1

# OBV in bottom range - MISSING
if current.get('OBV_Percentile', 50) <= 40:
    put_conditions += 1

# Prime time window - MISSING
hour = pd.to_datetime(current['Time']).hour
minute = pd.to_datetime(current['Time']).minute
if (hour == 9 and minute >= 30) or (hour == 10 and minute == 0):
    put_conditions += 1
```

### Step 3: Validate with Historical Data

After updating signal logic based on actual patterns:

1. Run `iwm_analysis.py` with new logic
2. Compare generated signals to your `trade_tracker.csv` entries
3. Measure precision/recall:
   - **Precision**: What % of generated signals match your actual trades?
   - **Recall**: What % of your actual trades are detected by the signal logic?
4. Iterate and refine

---

## Data Limitations

### Current Trade Analysis Based On
- **File**: [`data/trade_examples/trade_tracker.csv`](data/trade_examples/trade_tracker.csv)
- **Trades**: 12 trades (5 CALL, 7 PUT)
- **Date**: Single day (2025-08-08)
- **Scenarios**: 36 total (3 exit scenarios per trade)

### What's Missing
1. **Multi-day data**: Only 1 day of trades analyzed
2. **Statistical significance**: 12 trades is a small sample
3. **Losing trades**: All analyzed trades show 80%+ win rate (may be survivorship bias)
4. **Market conditions**: Single day may not represent different market regimes

### Recommendation
**Expand trade tracking** to at least:
- 30+ trading days
- 100+ trades (50+ CALL, 50+ PUT)
- Include losing trades
- Various market conditions (trending up, trending down, choppy)

---

## Next Steps

### Option 1: Expand Trade Tracking (Recommended)
1. Continue logging trades in `trade_tracker.csv` for at least 1 month
2. Re-run `trade_analysis_pipeline.py` with larger dataset
3. Update signal logic based on comprehensive analysis

### Option 2: Validate Current Logic
1. Generate signals with current logic on historical data
2. Compare to your actual trades
3. Calculate precision/recall metrics
4. Identify false positives and false negatives

### Option 3: Hybrid Approach
1. Use broad filters based on generic technical analysis
2. Rank signals by "similarity to actual trades"
3. Use actual trade patterns as a scoring mechanism
4. Only alert on high-scoring signals

---

## Files Referenced

1. **[`iwm_analysis.py`](iwm_analysis.py)** - Current signal generation logic
2. **[`data/trade_examples/trade_tracker.csv`](data/trade_examples/trade_tracker.csv)** - Actual trades
3. **[`data/trade_analysis_report.md`](data/trade_analysis_report.md)** - Analysis results
4. **[`trade_analysis_pipeline.py`](trade_analysis_pipeline.py)** - Pattern matching pipeline
5. **[`iwm_analysis_overview.md`](iwm_analysis_overview.md)** - System overview

---

## Summary

### Key Findings

1. **Current signal logic uses generic technical analysis rules** that may not reflect your actual trading patterns

2. **Major contradictions identified**:
   - CALL signals require price > VWAP (current) vs. 80% of actual CALLs below VWAP
   - PUT signals require price < VWAP (current) vs. 71% of actual PUTs above VWAP
   - No RVOL filter (current) vs. CALLs average 4.74x RVOL

3. **Missing high-impact criteria**:
   - Entry RVOL thresholds
   - Entry ATR thresholds
   - OBV position relative to range
   - Time-of-day filtering
   - Exit RSI extremes

4. **Limited data**: Analysis based on only 12 trades from a single day

### Recommendation

**Before relying on generated signals**, either:
- Expand trade tracking to build a robust dataset (recommended)
- Manually adjust signal logic to match your actual entry criteria
- Use current signals as starting points but validate against your actual trades

The current implementation is **functionally correct** (generates signals and calculates returns) but may not be **strategically correct** (aligned with your actual trading patterns).
