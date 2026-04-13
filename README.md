# Stock Market Analysis System

## Overview
This repository contains tools for analyzing stock market data (IWM, SPY, QQQ, SPX), calculating technical indicators, generating trading signals, backtesting strategies, and fetching real-time market data. The system implements a **contrarian mean-reversion strategy** with **The Strat** candle classification and **Full Timeframe Continuity (FTFC)** filtering.

A unified React/FastAPI **Platform** lives under [`platform/`](platform/) and reads all data from Cloud SQL + GCS on demand (no pre-pull required).

## Platform Quickstart

Run both the FastAPI backend (port 8000) and the Vite dev server (port 5173) with a single command:

```bash
make dev
```

This starts both servers in parallel with interleaved logs prefixed `[api]` and `[web]`. `.env` is sourced automatically. Press `Ctrl+C` to stop both cleanly.

### Individual targets

| Command | What it does |
|---|---|
| `make dev` | Start FastAPI + Vite together (recommended) |
| `make api` | Start only the FastAPI backend on port 8000 |
| `make web` | Start only the Vite dev server on port 5173 |
| `make stop` | Kill any running dev servers |

### Requirements

- Python deps: `make install`
- Node deps: `cd platform && npm install` (once per fresh codespace)
- `.env` at project root with `GOOGLE_APPLICATION_CREDENTIALS` pointing to `.gcp-key.json`
- `.gcp-key.json` at project root for Cloud SQL + GCS auth

### Where data comes from

**No data is stored in git.** The platform reads everything on demand:
- **Cloud SQL** (`adept-mountain-474619-d4:us-east1:trading-db`) — market_data_daily, market_data_intraday, etf_options_snapshots, journal_entries, premarket_analysis
- **GCS** (`gs://adept-mountain-474619-d4-trading-data/raw/`) — backtest CSVs, signals parquets, phase reports, historical parquets

The API caches GCS reads in memory with a TTL (1h for backtest/signals, 24h for markdown reports). First request per resource is slower; subsequent requests are <50ms. See [data/README.md](data/README.md) for the full philosophy.

### Accessing the platform

Once `make dev` is running, VS Code's **Ports** tab (bottom panel) will auto-forward:
- **Vite**: `https://<codespace>-5173.app.github.dev` — the UI
- **API**: `https://<codespace>-8000.app.github.dev` — FastAPI with `/docs` endpoint

Routes available at the Vite URL: `/` Dashboard, `/live` Live Market, `/charts`, `/options` Options Flow, `/playbook`, `/backtest`, `/reports`, `/signals`, `/journal`, `/insights`.

### Troubleshooting

- **"Failed to fetch dynamically imported module"** — Vite isn't running. Run `make dev`.
- **Ports don't appear in VS Code Ports tab** — ports opened by a different terminal session may not be auto-detected. Click "Forward a Port" in the Ports tab and enter `5173` / `8000`.
- **API returns 500 "GCS auth failed"** — Check `.gcp-key.json` exists at project root or run `gcloud auth application-default login`.
- **Dev server crashed after restart** — Codespace sleep kills both processes. Just `make dev` again.

---

## Main Components

### 1. IWM Analysis (`iwm_analysis.py`)
Comprehensive stock analysis tool with **195 feature columns** that:
- **Combines CSV data**: Merges multiple CSV files containing historical stock price data
- **Calculates technical indicators**:
  - ATR (Average True Range) with Wilder smoothing
  - RSI (Relative Strength Index) with Wilder's smoothing
  - EMAs (9, 20, 50 period) using standard exponential weighting
  - VWAP (Volume Weighted Average Price)
  - RVOL (Relative Volume - both 20-period and minute-of-day)
  - OBV (On-Balance Volume) with continuous accumulation
  - Stochastic RSI (momentum oscillator measuring RSI relative to its range)
- **NEW: Historical Levels** (80 columns):
  - Previous day, week, month, year: High, Low, Open, Close
  - 50% midpoint levels (HL_Mid, OC_Mid)
  - Breakout/breakdown flags
  - At-level indicators (within 0.1% tolerance)
  - Price position percentages
- **NEW: Opening Range Breakout - ORB** (108 columns):
  - 5-minute, 15-minute, 30-minute opening ranges
  - Trend direction (bullish/bearish/neutral)
  - Breakout/breakdown/within-range flags
  - Shows if stock trended above/below ORB or stayed sideways
  - Distance from ORB levels
- **NEW: Order Blocks** (7 columns):
  - Consolidation zone detection
  - Support/resistance identification
  - Block test indicators
- **Generates trading signals**: Creates PUT/CALL signals based on:
  - Consecutive price movements (3+ periods)
  - RSI levels (bullish: 25-50, bearish: 50-75)
  - Price position relative to VWAP and EMAs
  - Stochastic RSI conditions
  - Historical level interactions
  - ORB trend alignment
  - Order block tests
  - Requires at least 3 out of 5 conditions to be met
- **Outputs**:
  - Combined historical data CSV
  - Enhanced data with all technical indicators (195 new columns)
  - Trading signals with entry/exit points, performance metrics, and level data (117 new columns per signal)

### 2. Trade Analysis Pipeline (`trade_analysis_pipeline.py`)
Analyzes your trading history and finds patterns:
- Reads your trades from CSV
- Calculates trade durations
- Enriches trades with technical indicators
- Identifies profitable patterns
- Finds similar historical trades

## Getting Started

### Step 1: Run IWM Analysis
```bash
# Default: Analyze last 2 months
python3 iwm_analysis.py

# Analyze all available data
python3 iwm_analysis.py -all

# Analyze specific number of months (e.g., 6 months)
python3 iwm_analysis.py -months 6
```

### Step 2: Run Trade Analysis Pipeline
After indicators are calculated, analyze your trades:

```bash
# Default: Search last 1 month for similar trades
python3 trade_analysis_pipeline.py

# Search all available data for similar trades
python3 trade_analysis_pipeline.py -all

# Search specific number of months (e.g., 2 months)
python3 trade_analysis_pipeline.py -months 2
```

## Key Files

### Input Data
- `data/stock_prices/` - Historical IWM price data (CSV files)
- `data/iwm/intraday/` - AlphaVantage Parquet data (up to 5 years of 1-minute bars)
- `data/signals/trade_examples/trade_tracker.csv` - Your trade entries

**Note**: The pipeline automatically loads and merges both CSV and Parquet data sources. No conversion needed!

### Output Files
- `data/historical_iwm_*_with_indicators.csv` - Data with calculated indicators
- `data/historical_iwm_*_signals.csv` - Generated trading signals
- `data/trade_tracker_updated.csv` - Trades with durations
- `data/trades_enriched.csv` - Trades with entry/exit indicators
- `data/trade_patterns.csv` - Analyzed trading patterns
- `data/similar_trades_pipeline.csv` - Similar profitable trades found

## Market Data Scripts (scripts/)

### 1. Fetch Market Data (`fetch_market_data.py`)
Fetches minute-level and daily data from Yahoo Finance:
- **Supports**: IWM, SPY, QQQ, SPX (S&P 500 Index)
- **IMPORTANT**: Minute-level data is only available for the past 7 days due to Yahoo Finance limitations
- **Features**:
  - Fetches 1-minute bars for recent trading days (last 7 days)
  - Calculates true daily OHLCV from minute data
  - Computes comprehensive technical indicators
  - Stores data in efficient Parquet format
  - Saves minute data for future reference

```bash
# Fetch all tickers
python3 scripts/fetch_market_data.py

# Fetch specific tickers
python3 scripts/fetch_market_data.py --tickers IWM SPY
```

### 1b. Fetch Historical Intraday Data (`fetch_alphavantage_intraday.py`)
**Fetch up to 5 years of 1-minute historical data from AlphaVantage:**
- **Overcomes Yahoo Finance 7-day limit**
- **Supports**: Any ticker symbol
- **Features**:
  - Fetches historical 1-minute bars (up to 5 years)
  - Stores data in efficient Parquet format
  - Automatically integrated with `iwm_analysis.py`
  - Month-by-month fetching with progress tracking
  - API rate limit handling (5 calls/minute)
  - **Auto-combines all monthly files** at end of every fetch

```bash
# Fetch 5 years of IWM data
python3 scripts/fetch_alphavantage_intraday.py --symbol IWM --years 5

# Fetch specific date range
python3 scripts/fetch_alphavantage_intraday.py --symbol IWM \
  --start-date 2020-01-01 --end-date 2025-11-16

# Fetch SPY data
python3 scripts/fetch_alphavantage_intraday.py --symbol SPY --years 2
```

**Output**: `data/{symbol}/intraday/{symbol}_av_1min_combined.parquet`

**Note**: The IWM analysis pipeline automatically loads and merges this data with CSV files. No conversion needed!

### 2. Analyze Market Data (`analyze_market_data.py`)
Basic market data analysis:
- Performance metrics and statistics
- Correlation analysis between tickers
- Export to CSV format
- Technical indicator analysis

```bash
# Analyze specific ticker
python3 scripts/analyze_market_data.py --ticker IWM

# Compare all tickers
python3 scripts/analyze_market_data.py --compare

# Correlation analysis
python3 scripts/analyze_market_data.py --correlations

# Export to CSV
python3 scripts/analyze_market_data.py --export
```

### 3. Enhanced Market Analysis (`analyze_market_data_enhanced.py`)
**Comprehensive analysis with all IWM analysis features for all tickers:**
- **Calculates enhanced technical indicators**:
  - Stochastic RSI with K and D lines
  - VWAP approximation from daily data
  - Consecutive price movement detection
  - Price position relative to EMAs and VWAP
- **Generates trading signals** based on:
  - Consecutive price movements (3+ periods)
  - RSI levels (bullish: 25-50, bearish: 50-75)
  - Price position relative to VWAP and EMAs
  - Stochastic RSI conditions
  - Requires at least 3 out of 5 conditions to be met
- **Signal analysis and performance metrics**:
  - Entry/exit points with return calculations
  - Signal strength scoring (3/5, 4/5, 5/5)
  - Win rate and profitability analysis
  - Condition tracking for each signal
- **Multi-ticker comparison**: Compare signals and performance across IWM, SPY, QQQ, SPX

```bash
# Analyze all tickers with signal generation
python3 scripts/analyze_market_data_enhanced.py

# Analyze specific ticker
python3 scripts/analyze_market_data_enhanced.py --ticker SPY

# Export signals to CSV files
python3 scripts/analyze_market_data_enhanced.py --export

# Compare all tickers
python3 scripts/analyze_market_data_enhanced.py --compare
```

## Shared Library (`lib/`)

The core analysis logic is extracted into a shared Python library, eliminating duplication and providing a unified API for backtesting and signal generation.

| Module | Purpose |
|--------|---------|
| `lib/indicators.py` | All indicator functions (RSI, ATR, EMA, VWAP, RVOL, OBV, Stochastic RSI, ORB, etc.) |
| `lib/signals.py` | Signal evaluation — 3-of-5 conditions + optional Strat bonus (max score 8) |
| `lib/data_loader.py` | Unified data loading, column normalization, multi-source priority |
| `lib/config.py` | Typed config from `alert_config.json` with per-ticker overrides |
| `lib/strat.py` | The Strat classifier — candle types (1, 2U, 2D, 3), combos, FTFC scoring |
| `lib/backtest.py` | Bar-by-bar backtesting with FTFC/ORB trade filtering and risk management |
| `lib/walk_forward.py` | Walk-forward validation with expanding windows |

### Backtesting

```bash
# Run backtest for a ticker
python scripts/run_backtest.py --ticker IWM --start 2020-01-01 --end 2025-11-01

# With Strat overlay (FTFC/ORB filtering)
python scripts/run_backtest.py --ticker IWM --use-strat

# Multi-timeframe sweep
python scripts/run_timeframe_sweep.py --ticker IWM --use-strat
```

### The Strat & FTFC

- **Candle classification**: Inside (1), Up (2U), Down (2D), Outside (3) vs prior bar
- **FTFC**: Weighted alignment across 5m/15m/1h/D/W — trades contradicted by FTFC are rejected
- **ORB filtering**: Trades contradicted by Opening Range Breakout trend are rejected
- **Result**: ~90% of raw signals filtered, remaining signals have higher win rates and Sharpe ratios

### Backtest Results (Full 10-Year Data)

| Configuration | Ticker | Trades | Win Rate | PF | Sharpe | Expectancy |
|---------------|--------|--------|----------|------|--------|------------|
| Base | IWM | 13,674 | 41.2% | 1.02 | 0.30 | +0.002% |
| +Strat (FTFC/ORB) | IWM | 11,664 | 42.1% | 1.04 | 0.51 | +0.004% |
| +Strat (FTFC/ORB) | SPY | 11,359 | 43.6% | 1.01 | 0.18 | +0.001% |
| +Strat (FTFC/ORB) | QQQ | 11,402 | 39.9% | 1.00 | -0.06 | -0.000% |
| 1m+15m combo | IWM | 492 | 57.1% | 2.04 | 9.31 | +0.078% |
| 1m+30m combo | SPY | 9,528 | 54.5% | 1.68 | 5.54 | +0.036% |
| 1m+15m combo | QQQ | 9,607 | 52.0% | 1.76 | 6.67 | +0.055% |

See [BACKTEST_RESULTS.md](BACKTEST_RESULTS.md) for the full auto-generated report with trade duration, exit analysis, and signal strength breakdowns.

### End-to-End Pipeline

```bash
# Full pipeline: base + strat backtests → timeframe sweeps → report
make pipeline

# Report-only (regenerate from existing backtest CSVs)
make report

# Or use the Python script directly
python scripts/run_pipeline.py
python scripts/run_pipeline.py --report-only
python scripts/run_pipeline.py --tickers IWM SPY
```

GitHub Actions (`.github/workflows/backtest-pipeline.yml`) runs tests on every push and supports manual pipeline dispatch with artifact uploads.

### Tests

```bash
# Run all 321 tests
python -m pytest tests/ -v
```

## Data Storage
- `data/` - Daily aggregated data in Parquet format
- `data/minute/` - Minute-level data (last 7 days only)
- `data/*_summary.json` - Latest statistics for each ticker
- `data/backtest_results/` - Backtest output CSVs and equity curves

## Recent Updates

### February 2025: Production Pipeline & Full-Range Backtests
- **End-to-end pipeline** (`scripts/run_pipeline.py`, `Makefile`) — single command runs backtests + sweeps + report for all tickers
- **GitHub Actions CI/CD** — tests on every push, manual pipeline dispatch with artifact uploads
- **Full 10-year backtests** — all tickers backtested across Jan 2015 – Feb 2025 (~13K+ trades each)
- **Production hardening** — division-by-zero guards, NaN handling, config parsing robustness, CSV discovery fixes
- **321 automated tests** including 24 dedicated production-readiness tests

### December 2024: Historical Levels, ORB, and Order Blocks
Three major feature sets added with **195 new columns** for enhanced pattern recognition:

1. **Historical Levels** (80 columns) — previous day/week/month/year levels, breakout flags, at-level indicators
2. **Opening Range Breakout - ORB** (108 columns) — 5m/15m/30m analysis, trend direction, momentum tracking
3. **Order Blocks** (7 columns) — institutional consolidation zone detection

### Documentation
- [INVESTMENT_MODELS_SUMMARY.md](docs/INVESTMENT_MODELS_SUMMARY.md) - Detailed summary of all 5 models, Strat/FTFC, backtest engine, and results
- [MODEL_SUMMARY.md](docs/MODEL_SUMMARY.md) - Concise model overview with backtest results
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - Quick reference guide for indicators and patterns
- [NEW_FEATURES_SUMMARY.md](docs/NEW_FEATURES_SUMMARY.md) - Complete feature overview
- [iwm_analysis_overview.md](docs/iwm_analysis_overview.md) - All analysis scripts overview
- [SIGNAL_GENERATION_METHODOLOGY.md](docs/SIGNAL_GENERATION_METHODOLOGY.md) - How trading signals are generated and validated
- [TRADE_ANALYSIS_REPORT_BUILD_PROCESS.md](docs/TRADE_ANALYSIS_REPORT_BUILD_PROCESS.md) - How the trade analysis report is built from your actual trades
- [ADD_NEW_FEATURES_TO_CRITERIA_ANALYSIS.md](docs/ADD_NEW_FEATURES_TO_CRITERIA_ANALYSIS.md) - Adding Historical Levels, ORB, and Order Blocks to trade analysis pipeline
- [TRADE_PIPELINE_FORMAT_MATCHING.md](docs/TRADE_PIPELINE_FORMAT_MATCHING.md) - Fix trade analysis pipeline to support both CSV and Parquet formats

## Notes
- **New Features**: 195 additional columns now available for analysis (80 Historical Levels + 108 ORB + 7 Order Blocks)
- **Minute Data Limitation**: Yahoo Finance only provides minute-level data for the past 7 days. Historical data beyond 7 days uses daily aggregates
- The first run of `iwm_analysis.py` may take 3-4 minutes with new features
- Indicators are calculated to match popular trading platforms (Robinhood, etc.)
- Trade examples have been moved to `data/signals/trade_examples/`
- All market data is stored in efficient Parquet format for fast loading