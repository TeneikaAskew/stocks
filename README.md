# stocks

# Running the Updated IWM Analysis

## Step 1: Re-calculate Indicators with Updated Methods
This will recalculate all indicators using the updated EMA and OBV methods that match Robinhood.

```bash
# Default: Analyze last 2 months
python3 iwm_analysis.py

# Analyze all available data
python3 iwm_analysis.py -all

# Analyze specific number of months (e.g., 6 months)
python3 iwm_analysis.py -months 6
```

This will:
- Process historical IWM data files
- Calculate indicators with updated methods:
  - EMA: Now uses standard exponential weighting (no SMA seeding)
  - OBV: Now uses continuous accumulation (no daily resets)
  - RSI: Already using correct Wilder's smoothing
- Generate updated indicator files in the `data/` folder
- Create signal outputs in the `analysis/outputs/` folder

## Step 2: Run Trade Analysis Pipeline
After indicators are recalculated, run the trade analysis pipeline:

```bash
# Default: Search last 1 month for similar trades
python3 trade_analysis_pipeline.py

# Search all available data for similar trades
python3 trade_analysis_pipeline.py -all

# Search specific number of months (e.g., 2 months)
python3 trade_analysis_pipeline.py -months 2
```

This will:
1. Read your trades from `data/trade_tracker.csv`
2. Calculate durations and save to `data/trade_tracker_updated.csv`
3. Pivot trades to tall format in `data/trades_pivoted.csv`
4. Join with indicators to create `data/trades_enriched.csv`
5. Analyze patterns and save to `data/trade_patterns.csv`
6. Find similar profitable trades in `data/similar_trades_pipeline.csv`

## Key Files:
- **Main Scripts:**
  - `iwm_analysis.py` - Calculates indicators and generates signals
  - `trade_analysis_pipeline.py` - Analyzes your trades and finds patterns

- **Input Data:**
  - `data/trade_examples/trade_tracker.csv` - Your trade entries
  - `data/historical_iwm_*.csv` - Historical IWM data

- **Output Files:**
  - `data/historical_iwm_*_with_indicators.csv` - Data with calculated indicators
  - `data/trade_tracker_updated.csv` - Trades with durations
  - `data/trades_enriched.csv` - Trades with entry/exit indicators
  - `data/similar_trades_pipeline.csv` - Similar profitable trades found

## Notes:
- The first run of `iwm_analysis.py` may take 2-3 minutes to process all data
- All old test files have been cleaned up
- Trade examples have been moved to `data/trade_examples/`