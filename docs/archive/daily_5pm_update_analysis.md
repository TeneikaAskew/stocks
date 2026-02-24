# Daily 5PM Update Process Analysis

## Overview
The daily 5PM update process is triggered by `EW_updateActiveStrikeHits()` which runs at 5 PM ET after market close. This process updates tracking data for active positions across all strategy sheets.

## 1. What triggers the daily update at 5pm

From `03_Triggers.js`:
- **Function**: `EW_updateActiveStrikeHits`
- **Schedule**: Daily at 5 PM ET (17:00)
- **Trigger Setup**: Lines 71-85 in `EW_setupTriggersIfMissing()`
```javascript
ScriptApp.newTrigger('EW_updateActiveStrikeHits')
  .timeBased()
  .everyDays(1)
  .atHour(17) // 5 PM
  .inTimezone('America/New_York')
  .create();
```

## 2. Which functions are called during the daily update

The main flow:
1. **`EW_updateActiveStrikeHits()`** (11_ActivePositionTracking.js) - Main entry point
2. **`EW_updateStrategyActiveStrikes()`** - Processes each strategy sheet
3. **`EW_batchCheckStrikeHits()`** - Batch processes positions for efficiency
4. **`EW_checkStockIntraday()`** - Fetches Yahoo Finance data with fallback intervals
5. **`EW_calculateIndicatorsFromYahoo()`** - Calculates technical indicators
6. **`EW_createDailyApiReport()`** - Creates API usage report after updates

## 3. Which columns are updated during the daily process

The daily 5PM update processes **ACTIVE positions** (Days_To_Exp > -7) and updates:

### Core Strike Tracking:
- **Strike_Hit** - Updates to 'HIT' or 'NO' based on intraday data
- **Hit_Date** - Sets the date when strike was first hit

### Day Check Columns:
- **Day0_Check** through **Day5_Check** - Updates based on days since entry
- **Exp_Result** - Updates when position expires

### Price Movement Tracking:
- **Max_Favorable** - Maximum favorable price movement
- **Min_Unfavorable** - Minimum unfavorable price movement
- **Profit_Potential** - Calculated from current price vs strike

### Technical Indicators at Strike Hit:
- **Hit_RSI** - RSI value when strike was hit
- **Hit_SMA20** - 20-day SMA at strike hit
- **Hit_SMA50** - 50-day SMA at strike hit
- **Hit_EMA9** - 9-day EMA at strike hit
- **Hit_EMA21** - 21-day EMA at strike hit
- **Hit_VWAP** - VWAP at strike hit
- **Hit_RVOL** - Relative volume at strike hit
- **Hit_ATR** - Average True Range at strike hit
- **Hit_PriceVsSMA20** - Price vs SMA20 percentage
- **Hit_PriceVsVWAP** - Price vs VWAP percentage

## 4. Comparison with Historical Backfill

### Columns Updated in BOTH Daily and Historical:
✅ **Strike_Hit** - Both update this field
✅ **Hit_Date** - Both set when strike was hit
✅ **Day0_Check** through **Day5_Check** - Both update day checks
✅ **Max_Favorable** - Both calculate max favorable movement
✅ **Min_Unfavorable** - Both calculate min unfavorable movement
✅ **Exp_Result** - Both update expiration results
✅ **Profit_Potential** - Both calculate profit potential
✅ **Risk_Reward** - Historical only (lines 233-244)
✅ **Hit_RSI** - Both update RSI at strike hit
✅ **Hit_SMA20** - Both update SMA20 at strike hit
✅ **Hit_SMA50** - Both update SMA50 at strike hit
✅ **Hit_EMA9** - Both update EMA9 at strike hit
✅ **Hit_EMA21** - Both update EMA21 at strike hit
✅ **Hit_VWAP** - Both update VWAP at strike hit
✅ **Hit_RVOL** - Both update RVOL at strike hit
✅ **Hit_ATR** - Both update ATR at strike hit
✅ **Hit_PriceVsSMA20** - Both update price vs SMA20
✅ **Hit_PriceVsVWAP** - Both update price vs VWAP

### Columns Updated ONLY in Historical Backfill:
❌ **Historical_High** - Only in historical (lines 296-301)
❌ **Historical_Low** - Only in historical (lines 303-308)
❌ **Peak_Profit_Date** - Only in historical (lines 215-221)

### Key Differences:
1. **Target Positions**: 
   - Daily: Active positions (Days_To_Exp > -7)
   - Historical: Expired positions (Days_To_Exp < 0)

2. **Data Source**:
   - Daily: Real-time Yahoo Finance intraday data (1m, 5m, 1h fallbacks)
   - Historical: Yahoo Finance historical daily data

3. **Risk_Reward Calculation**:
   - Only calculated in historical backfill
   - Uses formula: Max_Favorable / Min_Unfavorable

## Recommendations

1. **Add Risk_Reward to Daily Updates**: The daily 5PM update should calculate Risk_Reward when both Max_Favorable and Min_Unfavorable are available.

2. **Historical High/Low Tracking**: Consider adding Historical_High and Historical_Low updates to the daily process for completeness.

3. **Peak_Profit_Date**: This could be valuable for active positions to track when maximum profit occurred.

## Code Locations

- **Daily Update Main Function**: `/workspace/google-apps-script/src/11_ActivePositionTracking.js` (lines 11-70)
- **Column Updates**: `/workspace/google-apps-script/src/11_ActivePositionTracking.js` (lines 174-294)
- **Historical Backfill**: `/workspace/google-apps-script/src/09_HistoricalBackfill.js` (lines 144-290)
- **Trigger Setup**: `/workspace/google-apps-script/src/03_Triggers.js` (lines 71-85)
- **Indicator Calculations**: `/workspace/google-apps-script/src/10_YahooHistorical.js` (lines 655-842)