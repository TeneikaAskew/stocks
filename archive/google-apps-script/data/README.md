# Data Directory

This directory contains CSV exports from Google Sheets for earnings options trading analysis.

## 📁 Purpose

CSV files in this directory are automatically processed by the earnings options analytics system to generate comprehensive trading insights.

## 📊 Expected Files

### Strategy-Based CSV Files

Place CSV exports for each trading strategy:

- `Long Calls.csv` - Long call option trades
- `Bull Spreads.csv` - Bull spread trades
- `Covered Calls.csv` - Covered call trades
- `Long Puts.csv` - Long put option trades
- `Bear Spreads.csv` - Bear spread trades
- `Short Calls.csv` - Short call trades
- `Strangles.csv` - Strangle option trades
- `Straddles.csv` - Straddle option trades
- `Short Puts.csv` - Short put trades

### Required Columns

Each CSV file should contain these columns:

**Entry Data:**
- `Run Date` - Trade entry date
- `Strategy` - Strategy name (must match file name)
- `company` - Company name
- `ticker` - Stock ticker symbol
- `strike` (or `longStrike`/`shortStrike` for spreads) - Strike price
- `expDate` - Option expiration date
- `nextEPSDate` - Next earnings date
- `releaseTime` - Earnings release time (beforeOpen/afterClose)

**Daily Tracking:**
- `Day0_Check` through `Day5_Check` - Daily check indicators
- `Strike_Hit` - JSON array of daily strike hit percentages
- `Hit_Date` - Date strike was first hit
- `Max_Favorable` - JSON array of maximum favorable movement
- `Min_Unfavorable` - JSON array of maximum adverse movement
- `OHLC_Volume` - JSON array of OHLC and volume data

**Technical Indicators** (JSON arrays):
- `Hit_RSI` - RSI values
- `Hit_SMA20` - SMA20 values
- `Hit_SMA50` - SMA50 values
- `Hit_EMA9` - EMA9 values
- `Hit_EMA21` - EMA21 values
- `Hit_VWAP` - VWAP values
- `Hit_RVOL` - Relative volume
- `Hit_ATR` - Average True Range
- `Hit_PriceVsSMA20` - Price vs SMA20 percentage
- `Hit_PriceVsVWAP` - Price vs VWAP percentage

**Additional Metrics:**
- `Risk_Reward` - Risk/reward ratio
- `Days_To_Exp` - Days to expiration
- `avgEPSMove` - Average earnings move
- `epsImpact` - EPS impact percentage

## 🔄 How to Export

### From Google Sheets

1. Open your strategy tracking sheet
2. Go to **File** → **Download** → **Comma-separated values (.csv)**
3. Save with strategy name (e.g., "Long Calls.csv")
4. Place in this directory

### Automated Export (Recommended)

Use the Google Sheets download workflow:

```bash
# Trigger via GitHub Actions
# Go to Actions → Download Google Sheets → Run workflow
```

Or use the Python script:

```bash
cd scripts
python download_google_sheets.py
```

## 🚀 Usage

Once CSV files are in place:

### Local Analysis

```bash
cd earnings_options_analytics

# Run tests
python test_system.py

# Run analysis
python earnings_options_analytics.py --quick
```

### GitHub Actions

The workflow automatically detects CSV files and runs analysis:

- **Automatic**: Triggers on push to main (if data files changed)
- **Scheduled**: Runs daily at 2 AM UTC
- **Manual**: Via GitHub Actions UI

## ✅ Data Quality

The system checks data quality and reports:

- **Strike_Hit completeness**: Should be >90%
- **Daily checks coverage**: Day 0 should be >90%, degrades to ~50% by Day 5
- **Indicator availability**: Should be >90%
- **Overall quality score**: Target >80% (Good)

## ⚠️ Important Notes

### JSON Array Format

Arrays must be valid JSON strings:

```csv
Strike_Hit
"[0.0, 5.2, 8.1, 10.3, 12.5, 11.8]"
"[-2.1, 0.5, 3.2, 6.8, 9.1, 8.4]"
```

### Special Values

- `NO_DATA` - Indicates missing data point
- `null` or empty - Also treated as missing
- Arrays can have variable length

### File Naming

- File names must match strategy names exactly
- Use spaces as shown (e.g., "Long Calls.csv" not "LongCalls.csv")
- Case-sensitive on some systems

## 🔍 Troubleshooting

**Problem:** Analytics shows "No data loaded"
**Solution:**
- Check CSV files are in this directory
- Verify file names match strategy names
- Ensure files have .csv extension

**Problem:** Low data quality score
**Solution:**
- Review Google Sheets exports
- Check for missing Strike_Hit data
- Verify indicator arrays are populated

**Problem:** JSON parsing errors
**Solution:**
- Validate JSON array format
- Check for unescaped quotes
- Ensure proper array brackets

## 📈 Expected Outputs

After placing data here and running analysis, you'll get:

- **CSV Reports**: `earnings_options_analytics/outputs/csv_reports/`
- **Charts**: `earnings_options_analytics/outputs/charts/`
- **HTML Report**: `earnings_options_analytics/outputs/earnings_options_report.html`

## 🔗 Related Documentation

- [Analytics README](../../earnings_options_analytics/README.md)
- [Project Summary](../../earnings_options_analytics/PROJECT_SUMMARY.md)
- [GitHub Actions Guide](../../earnings_options_analytics/GITHUB_ACTIONS_GUIDE.md)

---

**Last Updated:** 2025-10-09
