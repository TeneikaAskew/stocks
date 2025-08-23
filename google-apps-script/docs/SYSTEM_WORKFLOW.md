# Options Trading System - Complete Workflow & Triggers

## System Overview
This Google Apps Script system fetches options trading data from EarningsWhispers, tracks position performance using real-time and historical market data, and generates comprehensive success reports.

## Data Sources
1. **EarningsWhispers API**: Options strategy recommendations
2. **Google Finance**: Real-time price data (formulas in sheets)
3. **Yahoo Finance API**: 1-minute historical data for precise strike hit detection

## Automated Triggers

### 1. Daily Data Fetch (8:00 AM ET)
- **Function**: `EW_runAll()`
- **Purpose**: Fetch fresh options strategy data from EarningsWhispers
- **Actions**:
  - Fetches data for all 9 strategies
  - Applies Google Finance formulas
  - Updates Days_To_Exp calculations

### 2. Success Report Generation (9:00 AM ET)
- **Function**: `EW_generateSuccessReport()`
- **Purpose**: Generate daily performance analytics
- **Actions**:
  - Calculates strategy hit rates
  - Updates success scores
  - Creates performance recommendations

### 3. 30-Minute Updates (Market Hours Only: 9 AM - 5 PM ET)
- **Function**: `EW_autoUpdateTracking()`
- **Purpose**: Refresh Google Finance data during trading hours
- **Schedule**: Every 30 minutes, Monday-Friday, 9:00 AM - 5:00 PM ET only
- **Actions**:
  - Checks if within market hours before running
  - Updates array formulas
  - Forces recalculation
  - Refreshes live prices
- **Note**: Automatically skips weekends and after-hours to conserve resources

### 4. Active Position Tracking (5:00 PM ET) - CONSOLIDATED
- **Function**: `EW_updateActiveStrikeHits()`
- **Purpose**: Check if strikes were hit using Yahoo Finance data
- **Actions**:
  - Fetches 1-minute historical data for active positions
  - Updates Strike_Hit status
  - Records Hit_Date and technical indicators when strikes are hit
  - Updates Day0_Check through Day5_Check based on trading days
  - Calculates Max_Favorable and Min_Unfavorable
  - Updates Exp_Result for expired positions
  - Updates Profit_Potential based on current prices
  - Creates daily API usage report

**Note**: This 5 PM trigger now consolidates all tracking functionality previously split between 4:30 PM and 5:00 PM triggers.

## Manual Functions

### Data Collection
- **Run All Strategies**: Fetch all strategy data
- **Run Single Strategy**: Fetch specific strategy data

### Sheet Maintenance
- **Complete Sheet Repair**: Fix headers and formulas
- **Add Missing Columns**: Add tracking columns to existing sheets
- **Update Tracking Data**: Force recalculation

### Historical Analysis
- **Backfill Historical Tracking**: Analyze expired positions
- **Backfill Selected Rows**: Process specific positions

### Trigger Management
- **Setup Auto Tracking**: Create all automated triggers
- **Stop Auto Tracking**: Remove all triggers
- **List Active Triggers**: View current automation
- **Verify and Repair Triggers**: Check trigger health

## Data Flow

### 1. Entry (8:00 AM)
```
EarningsWhispers API → Strategy Sheets → Google Finance Formulas
```

### 2. Intraday Updates (Every 30 min)
```
Google Finance → Price Updates → Formula Recalculation
```

### 3. End of Day (5:00 PM)
```
Yahoo Finance API → Strike Hit Detection → Tracking Updates → API Report
```

### 4. Morning Report (9:00 AM)
```
All Sheets → Success Calculations → Report Generation
```

## Column Categories

### Google Finance Formula Columns
- Price, Change, Change_%, MarketCap
- Volume, AvgVolume, PE, 52WeekHigh/Low
- SMA20, SMA50, RSI, VWAP

### Plain Text Tracking Columns
- Strike_Hit, Hit_Date, Ever_Hit_Strike
- Day0_Check through Day5_Check
- Max_Favorable, Min_Unfavorable
- Exp_Result, Peak_Profit_Date
- Hit_RSI, Hit_SMA20, Hit_VWAP (indicators at strike hit)

### Calculated Columns
- Days_To_Exp, Historical_High/Low
- Success_Score, Profit_Potential
- Risk_Reward

## Strike Hit Detection Logic

### Bullish Strategies (Long Calls, Bull Spreads)
- **Single Strike**: Price >= Strike
- **Spread**: Price between Long Strike and Short Strike

### Bearish Strategies (Long Puts, Bear Spreads)
- **Single Strike**: Price <= Strike
- **Spread**: Price between Short Strike and Long Strike

### Neutral Strategies (Strangles, Straddles)
- Check both call and put strikes

### Income Strategies (Short Puts, Covered Calls)
- Track favorable vs unfavorable price movements

## Performance Metrics

### Success Score (0-100)
- Base: Strike hit status (60 points max)
- Time bonus: Days to expiration (30 points max)
- Volatility bonus: RVOL factor (10 points max)

### Hit Rate Categories
- HIGH CONFIDENCE: ≥70%
- MODERATE: 50-69%
- LOW CONFIDENCE: 30-49%
- POOR PERFORMANCE: <30%

## API Usage & Limits

### Yahoo Finance
- **Endpoint**: `/v8/finance/chart/{ticker}`
- **Intervals**: 1m, 5m, 15m, 30m, 60m, 1d
- **Rate Limits**: Monitored via API logging
- **Fallback**: Progressively larger intervals if data unavailable

### API Logging
- Tracks all Yahoo Finance API calls
- Daily summary report at 5 PM
- Monitors success rates and data availability

## Best Practices

### 1. Daily Workflow
- Let automated triggers handle routine updates
- Review Success Report each morning
- Monitor API usage via logs

### 2. Position Management
- Focus on high success score setups (>80)
- Monitor Day1 performance for early signals
- Review strategies with <50% hit rates

### 3. System Maintenance
- Run "Verify and Repair Triggers" weekly
- Check API logs for errors
- Use "Complete Sheet Repair" if data issues occur

## Troubleshooting

### Common Issues
1. **Missing Strike_Hit Updates**: Run manual active position check
2. **Formula Errors**: Use Complete Sheet Repair
3. **Trigger Not Running**: Check trigger health and repair
4. **API Errors**: Review API logs, check rate limits

### Debug Functions
- `EW_testYahooData()`: Test Yahoo API connectivity
- `EW_testHistoricalBackfill()`: Test backfill logic
- `EW_testDayChecks()`: Debug day check calculations
- `EW_listActiveTriggers()`: View all triggers

## Recent Updates
- **Consolidated Triggers**: Combined 4:30 PM and 5:00 PM functionality into single 5 PM trigger
- **Enhanced Tracking**: Added Day0_Check for same-day hit detection
- **Technical Indicators**: Capture RSI, SMA, VWAP values when strikes are hit
- **Spread Support**: Improved handling of bull/bear spread strategies

This system provides comprehensive automated tracking of options strategy performance with minimal manual intervention required.