# Earnings Options Analytics

Comprehensive Python analytics system for analyzing options trading strategies around earnings events.

## 📋 Overview

This system analyzes your Google Sheets options trading data to provide:
- **Strategy Performance Comparison** - Which strategies work best
- **Indicator Effectiveness** - Most predictive technical indicators
- **Earnings Timing Analysis** - Optimal entry windows relative to earnings
- **Risk/Reward Analysis** - Position sizing and risk management
- **Top Plays Identification** - Pattern recognition for winning trades
- **Holding Period Optimization** - Best days to exit positions
- **Predictive Models** - ML-based trade scoring (optional)

## 🚀 Quick Start

### 1. Installation

```bash
cd earnings_options_analytics
pip install -r requirements.txt
```

### 2. Prepare Data

Export your Google Sheets data as CSV files and place them in:
```
../google-apps-script/data/
```

Expected files (at least one):
- Long Calls.csv
- Bull Spreads.csv
- Covered Calls.csv
- Long Puts.csv
- Bear Spreads.csv
- etc.

### 3. Run Analysis

**Full Analysis** (recommended for first run):
```bash
python earnings_options_analytics.py --full --export-csv --export-charts
```

**Quick Analysis** (faster, skips ML):
```bash
python earnings_options_analytics.py --quick
```

**Specific Strategies Only**:
```bash
python earnings_options_analytics.py --strategies "Long Calls" "Bull Spreads"
```

## 📊 Outputs

All outputs are saved to `outputs/` directory:

### CSV Reports (`outputs/csv_reports/`)
**Strategy Analysis:**
- `overall.csv` - Overall performance metrics
- `strategy_breakdown.csv` - Performance by strategy
- `holding_period.csv` - Day 0-5 profitability
- `risk_reward.csv` - Risk/reward distribution
- `strategy_type.csv` - Performance by strategy type

**Earnings Timing Analysis (NEW):**
- `earnings_timing_entry_window.csv` - Performance by entry window (0-2, 3-5 days, etc.)
- `earnings_timing_release_time.csv` - Before/after market impact
- `earnings_timing_pre_vs_post.csv` - Pre vs post earnings performance
- `earnings_timing_optimal_days.csv` - Best specific entry days
- `earnings_timing_time_to_hit.csv` - Strike hit speed by window
- `earnings_timing_recommendations.csv` - Actionable trading insights

**Future Reports:**
- `indicator_effectiveness.csv` - Predictive power ranking (coming soon)
- `top_winners.csv` - Best 50 trades with full profiles (coming soon)

### Charts (`outputs/charts/`)
- `strategy_comparison.png` - Multi-metric strategy comparison
- `holding_period_curves.png` - Day 0-5 profit evolution
- `indicator_heatmaps.png` - Indicator impact grids
- `earnings_timing.png` - Optimal entry windows
- `risk_reward_distribution.png` - R/R buckets analysis

### Dashboard (`outputs/dashboards/`)
- `interactive_dashboard.html` - Interactive Plotly dashboard

### Master Report (`outputs/`)
- `earnings_options_master_report.pdf` - Comprehensive PDF report

## 📁 Project Structure

```
earnings_options_analytics/
├── earnings_options_analytics.py    # Main script
├── config.py                         # Configuration settings
├── requirements.txt                  # Python dependencies
├── README.md                         # This file
│
├── modules/
│   ├── data_loader.py               # CSV loading and preprocessing
│   ├── strategy_analyzer.py         # Strategy performance analysis
│   ├── indicator_analyzer.py        # Indicator effectiveness
│   ├── earnings_timing.py           # Earnings window analysis
│   ├── risk_analyzer.py             # Risk/reward analysis
│   ├── visualizations.py            # Chart generation
│   ├── predictive_model.py          # ML models (optional)
│   └── report_generator.py          # PDF report generation
│
└── outputs/
    ├── csv_reports/                 # CSV exports
    ├── charts/                      # PNG/PDF charts
    ├── dashboards/                  # Interactive HTML
    └── master_report.pdf            # Final report
```

## 🔧 Configuration

Edit `config.py` to customize:

- **Data paths** - Where to find CSV files
- **Analysis thresholds** - Minimum trades, profit thresholds
- **Indicator ranges** - RSI, RVOL, etc. winning ranges
- **Chart settings** - Style, DPI, colors
- **ML parameters** - Train/test split, random state

## 📈 Key Metrics Explained

### Strategy Performance
- **Hit Rate**: % of trades where strike was hit
- **Win Rate**: % of trades with positive profit
- **Profit Factor**: Total profit / Total loss ratio
- **Avg Days to Hit**: Average days until strike reached

### Holding Period
- **Day 0-5 Analysis**: Profitability if held 0-5 days
- **Best Holding Day**: Day with highest average profit
- **Multi-Day Winners**: Trades profitable across multiple days

### Risk/Reward
- **R/R Distribution**: Win rate by risk/reward bucket
- **Expected Value**: Probabilistic profit calculation
- **Position Sizing**: Kelly criterion recommendations

### Earnings Timing
- **0-2 Days Window**: Trades entered 0-2 days before earnings
- **Pre vs Post**: Before vs after earnings performance
- **Release Time**: beforeOpen vs afterClose impact

## 🎯 Typical Workflow

1. **Export Data** from Google Sheets to CSV
2. **Run Full Analysis** with all flags
3. **Review Master Report** PDF for key insights
4. **Drill Down** into specific metrics using CSV reports
5. **Explore Interactive Dashboard** for custom filtering
6. **Refine Strategy** based on findings
7. **Re-run Analysis** with new data monthly

## 💡 Tips for Best Results

### Data Quality
- Ensure at least **30+ trades per strategy** for statistical significance
- Verify all tracking columns are filled (Strike_Hit, Day0-5_Check, etc.)
- Check that indicator arrays are properly populated

### Analysis Focus
1. Start with **strategy comparison** to identify winners
2. Use **indicator analysis** to refine entry criteria
3. Apply **earnings timing** insights for optimal entry
4. Implement **risk management** based on R/R analysis

### Iterative Improvement
- Track performance monthly
- Compare periods to identify trends
- Adjust strategy selection based on results
- Refine indicator thresholds

## 🔍 Troubleshooting

### No Data Loaded
- Check CSV files are in correct path
- Verify filenames contain strategy names
- Ensure files have proper headers

### Missing Columns Error
- Some strategies may lack spread columns (longStrike, shortStrike)
- Indicator columns might not be populated
- Run backfill in Google Sheets first

### Low Confidence Warnings
- Increase minimum trades threshold in config
- Combine similar strategies for analysis
- Collect more historical data

## 📚 Understanding the Reports

### Executive Summary
- **Overall Metrics**: Cross-strategy averages
- **Best Strategy**: Highest profit factor
- **Optimal Entry**: Days before earnings
- **Key Indicators**: Most predictive signals

### Strategy Deep Dive
- Individual strategy performance
- When to use each strategy
- Strike selection guidelines
- Spread width recommendations

### Indicator Playbook
- **Entry Checklists**: Indicator ranges for setup
- **Red Flags**: Warning signals to avoid
- **Confirmation**: Multiple indicator alignment
- **Exit Signals**: When to close positions

### Earnings Calendar
- **Timeline**: Day-by-day performance
- **Best Windows**: Optimal entry dates
- **Release Time**: Before/after market impact
- **Post-Earnings**: Recovery opportunities

## 🤝 Integration with Google Sheets

This system works seamlessly with your existing Google Apps Script system:

1. **Data Sync**: Export sheets to CSV (can be automated)
2. **Analysis**: Run Python analytics
3. **Insights**: Import results back to Sheets if desired
4. **Trading**: Use insights for strategy selection

## 📊 Sample Insights (from reports)

Based on provided sample data:
- **Best Strategy**: Bull Spreads (4.42 profit factor)
- **Optimal Entry**: 0-2 days before earnings
- **Best Holding Day**: Day 3
- **Winning RSI Range**: 38.3 - 78.6
- **Winning Price vs SMA20**: -0.41% to +1.51%
- **High RVOL Impact**: >1.5 shows higher success

## 🔄 Future Enhancements

Potential additions:
- Real-time data integration
- Automated daily reports
- Slack/email alerts for setup matches
- Backtesting engine
- Portfolio optimization
- Multi-timeframe analysis

## 📝 Version History

**v1.0.0** - Initial Release
- Core analytics modules
- Strategy comparison
- Indicator analysis
- Earnings timing
- Risk metrics
- PDF reports

## 📧 Support

For issues or questions:
1. Check configuration in `config.py`
2. Review CSV column mappings
3. Verify data quality scores
4. Run with `--quick` flag for faster debugging

## 📄 License

This is a proprietary analytics system for personal trading use.

---

**Last Updated**: 2025-10-09
