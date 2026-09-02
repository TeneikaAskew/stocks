# 📊 Options Strategy Automation & Success Tracking System

## Table of Contents
- [Project Overview](#project-overview)
- [Architecture & File Structure](#architecture--file-structure)
- [Core Modules](#core-modules)
  - [GlobalVars.js](#globalvarsjs)
  - [HelperFunctions.js](#helperfunctionsjs)
  - [Triggers.js](#triggersjs)
  - [Code.js](#codejs)
  - [Data Sync & Alerts](#data-sync--alerts)
  - [Historical Backfill & Analysis](#historical-backfill--analysis)
  - [Success Report & Array Builders](#success-report--array-builders)
- [Data Flow & Sources](#data-flow--sources)
- [Sheet Structure & Columns](#sheet-structure--columns)
- [Automated Triggers](#automated-triggers)
- [Success Metrics & Logic](#success-metrics--logic)
- [API Usage & Logging](#api-usage--logging)
- [Best Practices & Troubleshooting](#best-practices--troubleshooting)
- [Recent Enhancements](#recent-enhancements)

---

## Project Overview

This Google Apps Script project automates the collection, tracking, and analysis of options trading strategies from EarningsWhispers. It integrates real-time and historical market data, applies advanced tracking formulas, and generates actionable success reports to optimize trading decisions.

---

## Architecture & File Structure

```
google-apps-script/
├── src/
│   ├── 01_GlobalVars.js
│   ├── 02_HelperFunctions.js
│   ├── 03_Triggers.js
│   ├── 04_Code.js
│   ├── 05_data-sync.js
│   ├── 06_trading-alerts.js
│   ├── 07_OldCode.js
│   ├── 08_TrackingUpdates.js
│   ├── 09_HistoricalBackfill.js
│   ├── 10_YahooHistorical.js
│   ├── 11_ActivePositionTracking.js
│   ├── 12_ApiLogging.js
│   ├── 13_ArrayBuilders.js
│   ├── 15_SuccessReport.js
│   └── appsscript.json
├── data/
│   └── [Strategy CSV exports]
├── docs/
│   ├── SYSTEM_WORKFLOW.md
│   └── tracking-guide.md
```

---

## Core Modules

### 01_GlobalVars.js

- Centralizes all configuration, constants, and global objects.
- Defines strategy endpoints, trigger schedules, and system-wide settings.
- Example: `EW.STRATEGY_ENDPOINTS`, `EW_AUTO_TRACKING`, `EW_TRIGGER_FUNCTIONS`.

### 02_HelperFunctions.js

- Utility functions for environment detection, string normalization, header mapping, and formula management.
- Key functions: `EW_norm()`, `EW_headerMap()`, `EW_safeAlert()`, `EW_setGFArrayFormulas()`.

### 03_Triggers.js

- Manages all time-based and event-based triggers.
- Functions to setup, validate, and repair triggers for daily fetch, intraday updates, and end-of-day analysis.
- Example: `EW_setupAutoTracking()`, `EW_listActiveTriggers()`.

### 04_Code.js

- Main business logic for data fetching, sheet updates, and menu integration.
- Handles authentication, API communication, and orchestrates strategy runs.
- Implements menu functions: Run All, Run Single, Generate Success Report, Update Tracking Data.

### Data Sync & Alerts

- **05_data-sync.js**: Handles synchronization of data between sheets and external sources.
- **06_trading-alerts.js**: Manages alerting logic for strike hits, expirations, and performance thresholds.

### Historical Backfill & Analysis

- **09_HistoricalBackfill.js**: Backfills historical tracking for expired positions.
- **10_YahooHistorical.js**: Fetches 1-minute historical data from Yahoo Finance for precise strike hit detection.
- **11_ActivePositionTracking.js**: Monitors active positions for strike hits and updates tracking columns.

### Success Report & Array Builders

- **15_SuccessReport.js**: Generates comprehensive success analytics and recommendations.
- **13_ArrayBuilders.js**: Constructs array formulas for Google Finance and tracking columns.

---

## Data Flow & Sources

1. **EarningsWhispers API**: Fetches options strategy recommendations.
2. **Google Finance**: Real-time price, volume, and technical indicators via formulas.
3. **Yahoo Finance API**: 1-minute historical data for strike hit detection.

**Workflow:**
- 8:00 AM: Fetch strategies → Update sheets → Apply formulas.
- Every 30 min (market hours): Refresh Google Finance data.
- 5:00 PM: Check strike hits using Yahoo data → Update tracking.
- 9:00 AM: Generate success report.

---

## Sheet Structure & Columns

### Google Finance Columns
- GF_Name, GF_Price, GF_ChangePct, GF_High, GF_Low, GF_High52, GF_Low52, GF_Volume, GF_AvgVol10, GF_MktCap, GF_PE, GF_Beta

### Tracking Columns
- Days_To_Exp, Strike_Hit, Hit_Date, Max_Favorable, Min_Unfavorable, Day1_Check, Day2_Check, Day3_Check, Day5_Check, Exp_Result, Success_Score, Profit_Potential, Risk_Reward, Historical_High, Historical_Low, Ever_Hit_Strike, First_Hit_Date, Last_Update, Total_Hit_Days, Peak_Profit_Date

### Calculated Columns
- Days_To_Exp, Historical_High/Low, Success_Score, Profit_Potential, Risk_Reward

---

## Automated Triggers

- **Daily Data Fetch (8:00 AM)**: Runs `EW_runAll()` to update all strategies.
- **Success Report (9:00 AM)**: Runs `EW_generateSuccessReport()` for analytics.
- **Intraday Updates (Every 30 min, market hours)**: Runs `EW_autoUpdateTracking()` to refresh formulas.
- **Active Position Tracking (5:00 PM)**: Runs `EW_updateActiveStrikeHits()` for strike hit detection and tracking.

---

## Success Metrics & Logic

### Strike Hit Detection
- **Bullish**: Price >= Strike
- **Bearish**: Price <= Strike
- **Neutral**: Check both call and put strikes
- **Income**: Track favorable/unfavorable price movements

### Success Score (0-100)
- **Base**: Strike hit status (60 points)
- **Time Bonus**: Days to expiration (30 points)
- **Volatility Bonus**: RVOL factor (10 points)

### Performance Categories
- HIGH CONFIDENCE: ≥70%
- MODERATE: 50-69%
- LOW CONFIDENCE: 30-49%
- POOR PERFORMANCE: <30%

---

## API Usage & Logging

- **Yahoo Finance**: `/v8/finance/chart/{ticker}` for historical data.
- **API Logging**: Tracks all API calls, monitors rate limits, and generates daily usage reports.

---

## Best Practices & Troubleshooting

- Let triggers handle routine updates.
- Review the Success Report each morning.
- Use "Update Tracking Data" to force recalculation if formulas break.
- Use "Verify and Repair Triggers" weekly.
- Check API logs for errors and rate limits.

**Common Issues:**
- Missing Strike_Hit: Run manual active position check.
- Formula errors: Use Complete Sheet Repair.
- Trigger not running: Check and repair triggers.
- API errors: Review logs and rate limits.

---

## Recent Enhancements

- Consolidated 4:30 PM and 5:00 PM triggers.
- Market hours logic for intraday updates.
- Enhanced tracking columns and technical indicators.
- Spread support for bull/bear strategies.
- Improved automation and error handling.

---

## Example Workflow

1. **Run All Strategies**: Updates all sheets with latest recommendations.
2. **Update Tracking Data**: Refreshes formulas and recalculates metrics.
3. **Generate Success Report**: Analyzes performance and provides recommendations.
4. **Active Position Tracking**: Monitors strike hits and updates tracking columns.

---

## References

- [SYSTEM_WORKFLOW.md](docs/SYSTEM_WORKFLOW.md)
- [tracking-guide.md](docs/tracking-guide.md)
- [Source Code](src/)

---

This documentation provides a comprehensive, deep technical and functional overview of your options strategy automation and tracking system. For further details, see the individual module comments and referenced Markdown guides.
