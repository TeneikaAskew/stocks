# Trading System Technical Architecture

> **Project:** adept-mountain-474619-d4
> **Region:** us-east1
> **Last updated:** 2026-02-22

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Directory Structure](#2-directory-structure)
3. [Configuration System](#3-configuration-system)
4. [Indicator Engine](#4-indicator-engine)
5. [Signal Generation](#5-signal-generation)
6. [Strat Classification System](#6-strat-classification-system)
7. [Backtesting Engine](#7-backtesting-engine)
8. [Data Layer](#8-data-layer)
9. [Cloud Infrastructure](#9-cloud-infrastructure)
10. [Cloud Run Jobs](#10-cloud-run-jobs)
11. [Cloud SQL Schema](#11-cloud-sql-schema)
12. [Data Migration](#12-data-migration)
13. [Deployment](#13-deployment)
14. [Environment Variables & Secrets](#14-environment-variables--secrets)
15. [GitHub Actions Cutover](#15-github-actions-cutover)
16. [Monitoring & Operations](#16-monitoring--operations)
17. [Cost Estimate](#17-cost-estimate)
18. [Troubleshooting](#18-troubleshooting)

---

## 1. System Overview

### Purpose

An event-driven options trading intelligence system that:

1. **Detects** intraday CALL/PUT signals using a 3-of-5 indicator scoring model on SPY, IWM, QQQ, and SPX
2. **Classifies** market context using Rob Smith's Strat (candle type, combo pattern, FTFC multi-timeframe alignment)
3. **Scores** signals 0–8 (base conditions + Strat bonus) and maps to position size
4. **Alerts** via Discord in real time during market hours
5. **Fetches** options snapshots with Black-Scholes Greeks 9×/day
6. **Backtests** strategies with walk-forward validation, MAE/MFE tracking, and Sharpe metrics
7. **Persists** all structured data to Cloud SQL (PostgreSQL 15) with GCS Parquet backups

### High-Level Architecture

```
+-----------------------------------------------------------+
|                     Cloud Scheduler                        |
|  premarket 8:30 AM · market-data 5 PM · etf-opts 9x/day  |
|  earnings-opts 6x/day · alphavantage 1st/month · weekend  |
+-----------------------------+-----------------------------+
                              | HTTP POST triggers
+-----------------------------v-----------------------------+
|                      Cloud Run Jobs                        |
|                                                            |
|   FETCHERS                   ANALYSIS                      |
|   fetch_market_data.py       premarket_brief.py            |
|   fetch_etf_options.py       weekend_review.py             |
|   fetch_earnings_options.py                                |
|   fetch_alphavantage_intraday.py                           |
|                                                            |
|                      Cloud Run Service                     |
|   signal_monitor.py  (real-time, 60s poll, market hours)  |
+------------+-------------------------------------+---------+
             | reads/writes                        | raw backup
+------------v-----------+         +--------------v----------+
|    Cloud SQL            |         |  Cloud Storage (GCS)    |
|    PostgreSQL 15        |         |  gs://PROJECT-trading   |
|    instance: trading-db |         |                         |
|    database: trading    |         |  raw/{ticker}/daily/    |
|    ─────────────────    |         |  raw/{ticker}/intraday/ |
|    8 tables (see §11)   |         |  raw/options/etfs/      |
+------------+-----------+         |  raw/options/earnings/  |
             | queried by          |  sheets/*.csv           |
+------------v-----------+         +-------------------------+
|   lib/data_loader.py   |
|   (Cloud SQL mode when  |
|   CLOUD_SQL_CONNECTION  |
|   _NAME env var is set) |
|                         |
|   gcp/trade_logger.py  |
|   (dual write: SQL +    |
|   local Parquet)        |
+------------+-----------+
             | signal results
+------------v-----------+
|   Discord Webhook       |
|   premarket embed       |
|   real-time alerts      |
|   weekend summary       |
+-------------------------+
```

### Key Technologies

| Component | Technology | Purpose |
|-----------|------------|---------|
| Signal Scoring | Custom 3-of-5 scoring (lib/signals.py) | CALL/PUT detection |
| Strat Classification | Rob Smith's Strat (lib/strat.py) | Candle type, combos, FTFC |
| Backtesting | Event-driven engine (lib/backtest.py) | Historical validation, walk-forward |
| Indicators | Vectorized (lib/indicators.py) | RSI, EMA, ATR, VWAP, StochRSI, ORB, Order Blocks |
| Market Data (live) | yfinance | Intraday 1-min bars |
| Market Data (historical) | AlphaVantage API | 1-min bars up to 2 years |
| Options Data | yahooquery | Full options chains |
| Greeks | py_vollib (Black-Scholes) | Delta, Gamma, Theta, Vega, Rho |
| Data Storage | Cloud SQL (PostgreSQL 15) | Primary structured data store |
| Backup Storage | Google Cloud Storage | Raw Parquet archives |
| Scheduled Jobs | Cloud Run Jobs | All data fetching + analysis |
| Real-time Monitor | Cloud Run Job | Intraday signal polling (scheduled 9:25 AM ET) |
| Scheduling | Cloud Scheduler | 21 cron triggers |
| Alerts | Discord Webhooks | Real-time trade alerts |
| Secrets | Secret Manager | API keys, DB credentials, webhook URLs |
| Container Build | Cloud Build | Docker image CI |
| Container Registry | Artifact Registry | `trading/trading-system` image |
| Configuration | alert_config.json + lib/config.py | Typed dataclass hierarchy |
| DB Connector | cloud-sql-python-connector[pg8000] | Cloud SQL Python client |
| ORM / Upserts | SQLAlchemy + ON CONFLICT DO UPDATE | Idempotent batch writes |

### Current Data Statistics

*As of 2026-02-22*

| Dataset | Coverage | Est. Size |
|---------|----------|-----------|
| SPY daily OHLCV + indicators | 2021–present | ~5 years |
| IWM daily OHLCV + indicators | 2021–present | ~5 years |
| QQQ daily OHLCV + indicators | 2021–present | ~5 years |
| SPY/IWM/QQQ 1-min intraday | 2023–present | ~16 GB local Parquet |
| ETF options snapshots | 9×/day live | GCS + Cloud SQL |
| Earnings options snapshots | 6×/day live | GCS + Cloud SQL |

---

## 2. Directory Structure

```
stocks/
│
├── alert_config.json              # Master config (risk, signals, indicators, strat)
├── requirements.txt               # Python dependencies
├── Makefile                       # make test / make test-e2e / make test-scripts
│
├── lib/                           # Core trading library
│   ├── config.py                  # Typed dataclass config loader
│   ├── data_loader.py             # Cloud SQL + Parquet unified data access
│   ├── indicators.py              # 25+ vectorized technical indicators
│   ├── signals.py                 # 3-of-5 condition scoring (CALL/PUT)
│   ├── strat.py                   # Strat candle classification + FTFC
│   ├── backtest.py                # Event-driven backtesting engine
│   ├── walk_forward.py            # Walk-forward validation
│   └── insights.py                # Post-backtest analysis helpers
│
├── gcp/                           # Google Cloud Platform modules
│   ├── Dockerfile                 # Container image (python:3.11-slim + psycopg2)
│   ├── deploy.sh                  # Single entry point: setup/build/deploy
│   ├── setup_cloud_sql.sh         # One-time infrastructure provisioning
│   ├── schema.sql                 # PostgreSQL 15 schema (8 tables, indexes)
│   ├── database.py                # Cloud SQL connection pool + upsert utilities
│   ├── gcs_utils.py               # GCS upload/download/list helpers
│   ├── migrate_to_gcp.py          # Parquet → GCS + Cloud SQL migration
│   ├── trade_logger.py            # Dual-write: Cloud SQL + local Parquet
│   ├── premarket_brief.py         # 8:30 AM weekday analysis → Discord
│   ├── signal_monitor.py          # Real-time 60s poll service → Discord
│   ├── weekend_review.py          # Saturday performance review → Discord
│   └── fetchers/
│       ├── fetch_market_data.py       # yfinance daily OHLCV + indicators → SQL
│       ├── fetch_etf_options.py       # 9×/day ETF options + Greeks → SQL
│       ├── fetch_earnings_options.py  # 6×/day earnings options → SQL
│       └── fetch_alphavantage_intraday.py  # Monthly 1-min backfill → SQL
│
├── scripts/                       # CLI entry points
│   ├── run_backtest.py            # Run backtests for a ticker/date range
│   ├── run_pipeline.py            # Full analysis pipeline
│   ├── run_timeframe_sweep.py     # Sweep entry/filter timeframe combos
│   ├── fetch_market_data.py       # Local data fetch (GitHub Actions)
│   ├── analyze_market_data.py     # Local market analysis
│   ├── validate_market_data.py    # Data quality checks
│   └── analysis/
│       ├── phase1_strat_mining.py     # Strat pattern analysis
│       ├── phase2_indicator_confirmation.py
│       ├── phase3_orb_strategies.py
│       ├── phase4_setup_discovery.py
│       ├── phase5_additional_dimensions.py
│       ├── phase6_playbook.py
│       └── phase7_feedback_loop.py
│
├── data/                          # Local Parquet cache (~16 GB)
│   ├── spy/
│   │   ├── spy_2024.parquet           # Annual daily OHLCV + indicators
│   │   └── intraday/
│   │       └── spy_av_1min_combined.parquet
│   ├── iwm/ (same structure)
│   ├── qqq/ (same structure)
│   ├── spx/ (same structure)
│   ├── options/
│   │   ├── etfs/                      # ETF options snapshots
│   │   └── earnings/                  # Earnings options snapshots
│   ├── trades/                        # Local trade logs (daily Parquet)
│   └── signals/                       # Signal archive Parquets
│
├── docs/
│   ├── GCP_IMPLEMENTATION_GUIDE.md    # This document
│   └── GCP_IMPLEMENTATION_STATUS.md   # Live implementation tracker
│
├── .claude/
│   └── commands/
│       └── gcp-deploy.md              # /gcp-deploy slash command
│
├── tests/                         # 339 unit/integration tests
│   ├── test_backtest.py
│   ├── test_data_loader.py
│   ├── test_indicators.py
│   ├── test_signals.py
│   ├── test_strat.py
│   ├── test_e2e.py                # Playwright E2E (28 tests)
│   └── test_scripts.py            # CLI regression (18 tests)
│
├── website/                       # Trading dashboard web app (port 8104)
├── chart-viewer/                  # Chart viewer web app (port 8103)
├── options-heatseeker/            # Options heatseeker (port 8101)
├── success-report-site/           # Success report (port 8102)
│
└── google-apps-script/            # Google Sheets automation (33 JS files)
    ├── src/                       # Apps Script source files
    └── data/                      # Strategy CSVs (LongCalls, ShortPuts, etc.)
```

---

## 3. Configuration System

### Overview

All trading parameters are defined in `alert_config.json` and loaded into a typed dataclass hierarchy via `lib/config.py`. Per-ticker overrides allow symbol-specific tuning without changing base config.

### Configuration Hierarchy

```
AppConfig
├── RiskConfig              — position sizing, daily limits, loss thresholds
├── ExitConfig              — profit targets, stops, time exits, RSI exits
├── SignalConfig            — condition thresholds, entry windows, RVOL min
├── StratConfig             — Strat bonuses, FTFC weights, filter toggles
├── IndicatorConfig         — periods for all indicators (RSI, EMA, ATR, etc.)
├── MarketConfig            — tickers, market hours, data directories
├── MonitorConfig           — poll interval, rolling window, Discord timeout
├── BacktestConfig          — min bars, starting equity, annualization
└── WalkForwardConfig       — train/test split months, minimum bar requirements
```

### RiskConfig Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_daily_trades` | 5 | Maximum trades per day per ticker |
| `max_concurrent_positions` | 1 | Simultaneous open positions |
| `daily_loss_limit` | -2% | Stop trading for the day |
| `daily_profit_target` | +3% | Optional profit target for day |
| `max_score` | 8 | Maximum possible signal score |
| `score_thresholds` | (4, 5, 6) | Bucket boundaries for position sizing |

### Position Sizing

Signal score maps to position size (fraction of allocated capital):

| Score | Label | Position Size |
|-------|-------|--------------|
| ≤ 4 | Weak | 25% |
| 5 | Medium | 50% |
| 6 | Strong | 75% |
| 7–8 | Perfect | 100% |

### ExitConfig Parameters

| Parameter | CALL | PUT |
|-----------|------|-----|
| Profit target | +0.30% | +0.38% |
| Stop loss | -0.15% | -0.20% |
| Time stop | 30 min | 35 min |
| Extreme RSI exit | RSI > 80 | RSI < 20 |

### SignalConfig Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_conditions` | 3 | Conditions required to fire signal |
| `consecutive_periods` | 3 | Bars of consecutive up/down for condition |
| `call_rsi_range` | (25, 50) | RSI oversold zone for CALL entry |
| `put_rsi_range` | (50, 75) | RSI overbought zone for PUT entry |
| `rvol_minimum` | 1.5 | Minimum relative volume for signal |
| `stoch_rsi_threshold_call` | 30 | StochRSI K below this = oversold |
| `stoch_rsi_threshold_put` | 70 | StochRSI K above this = overbought |
| `premarket_signal_threshold` | 3 | Score at which "SETUP" is declared premarket |
| `premarket_building_threshold` | 2 | Score at which "BUILDING" is declared |

### StratConfig Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `enabled` | true | Master toggle for Strat bonus system |
| `combo_bonus` | 1 | Score bonus for matching combo pattern |
| `ftfc_bonus` | 1 | Score bonus for aligned FTFC |
| `orb_alignment_bonus` | 1 | Score bonus for ORB alignment |
| `ftfc_threshold` | 0.6 | Min FTFC score to add bonus |
| `ftfc_direction_threshold` | 0.3 | Min FTFC to reject contradicted signals |
| `ftfc_filter_enabled` | true | Reject signals that contradict FTFC |
| `orb_filter_enabled` | true | Reject signals that contradict ORB trend |

### FTFC Weights

| Timeframe | Weight | Rationale |
|-----------|--------|-----------|
| 5m | 10% | Noise-heavy, low weight |
| 15m | 20% | Entry confirmation |
| 1h | 25% | Intraday trend |
| D | 35% | Primary trend (dominant) |
| W | 10% | Macro context |

### Alert Config — Example Structure

```json
{
  "risk_parameters": {
    "max_daily_trades": 5,
    "daily_loss_limit": -0.02,
    "position_sizing": { "weak_signal": 0.25, "medium_signal": 0.50,
                         "strong_signal": 0.75, "perfect_signal": 1.00 },
    "score_thresholds": [4, 5, 6],
    "max_score": 8
  },
  "signal": {
    "min_conditions": 3, "consecutive_periods": 3,
    "call_rsi_range": [25, 50], "put_rsi_range": [50, 75],
    "rvol_minimum": 1.5
  },
  "strat": {
    "enabled": true, "combo_bonus": 1, "ftfc_bonus": 1,
    "ftfc_threshold": 0.6, "ftfc_filter_enabled": true,
    "ftfc_weights": { "5m": 0.10, "15m": 0.20, "1h": 0.25, "D": 0.35, "W": 0.10 }
  },
  "market": {
    "tickers": ["IWM", "SPY", "QQQ"],
    "market_open": "09:30", "market_close": "16:00",
    "data_dir": "data", "trades_dir": "data/trades"
  },
  "ticker_overrides": {
    "SPY": { "exit": { "call_target": 0.0035, "put_target": 0.0040 } }
  }
}
```

### Loading Config

```python
from lib.config import load_config, get_position_size, get_signal_strength_label

# Load with optional ticker overrides
config = load_config('alert_config.json', ticker='SPY')

# Helper utilities
size = get_position_size(score=6)          # → 'strong' → 0.75
label = get_signal_strength_label(score=7) # → 'perfect'
```

---

## 4. Indicator Engine

### Module: `lib/indicators.py`

All indicators are vectorized on pandas Series/DataFrame. The master function `add_all_indicators()` computes every indicator in one pass and returns an enriched DataFrame.

### Indicator Functions

| Category | Function | Output Columns |
|----------|----------|----------------|
| **Moving Averages** | `calculate_sma(prices, period)` | `SMA_N` |
| | `calculate_ema(prices, period)` | `EMA_N` |
| | `wilder_moving_average(values, period)` | (internal, used for RSI/ATR) |
| **Momentum** | `calculate_rsi(prices, period=14)` | `RSI_14` |
| | `calculate_stoch_rsi(rsi)` | `StochRSI_K`, `StochRSI_D` |
| | `calculate_macd(prices, fast=12, slow=26, signal=9)` | `MACD`, `MACD_Signal`, `MACD_Hist` |
| **Volatility** | `calculate_atr(high, low, close, period=14)` | `ATR_14` |
| | `calculate_bollinger_bands(prices, period=20)` | `BB_Upper`, `BB_Mid`, `BB_Lower` |
| | `calculate_true_range(high, low, close)` | `True_Range` |
| **Volume** | `calculate_rvol(volume, period=20)` | `RVOL` |
| | `calculate_rvol_minute_of_day(ts, volume)` | `RVOL_MOD` |
| | `calculate_obv(close, volume)` | `OBV` |
| | `calculate_vwap(high, low, close, volume, dates)` | `VWAP` |
| **Derived** | `calculate_consecutive_moves(price_change, periods=3)` | `Consecutive_Up`, `Consecutive_Down` |
| | Price vs VWAP | `Price_vs_VWAP` |
| | Price vs EMA | `Price_vs_EMA_9`, `Price_vs_EMA_20` |
| **Levels** | `calculate_historical_levels(df)` | support/resistance levels |
| | `calculate_order_blocks(df, lookback=20)` | order block zones |
| | `calculate_orb(df, minutes=5)` | `ORB_5m_High`, `ORB_5m_Low` |
| | `calculate_all_orb(df)` | `ORB_{5m,15m,30m}_High/Low` |
| **Master** | `add_all_indicators(df, close_col='Close')` | All columns above |

### IndicatorConfig Defaults

```python
rsi_period      = 14
rsi_fast        = 9
ema_periods     = [9, 20, 50]
sma_periods     = [5, 10, 20, 50, 200]
atr_period      = 14
rvol_period     = 20
stoch_rsi       = 14  (period), 3 (K smooth), 3 (D smooth)
bb_period       = 20,  bb_std_mult = 2.0
macd_fast       = 12,  macd_slow = 26,  macd_signal = 9
consecutive_periods = 3
orb_windows     = [5, 15, 30]   # minutes
```

### Indicator Warmup & Spec Alignment

All indicators return `NaN` during the warmup period (i.e., until `min_periods` bars are available). This matches TradingView, Alpha Vantage, and TA-Lib behaviour:

| Indicator | Smoothing / Spec | Warmup |
|-----------|-----------------|--------|
| `EMA(period)` | `min_periods=period` | `period` bars |
| `SMA(period)` | `min_periods=period` | `period` bars |
| `StochRSI %K/%D` | SMA (not Wilder's RMA) — per Chande & Kroll spec | `rsi_period + k_period + d_period` bars |
| `MACD` | `min_periods=slow` for both fast/slow EMAs | `slow` bars for MACD, `+signal` for signal line |
| `Bollinger Bands` | Population std (`ddof=0`) — per John Bollinger spec | `period` bars |

---

## 5. Signal Generation

### Module: `lib/signals.py`

### Scoring Model (3-of-5)

Each direction is evaluated independently on 5 binary conditions. Scoring is additive (0–5). A score ≥ `min_conditions` (default: 3) triggers the signal.

**CALL Conditions** (contrarian bounce from oversold):

```
1. Consecutive_Down >= 3 bars      → exhaustion selling
2. RSI in (25, 50)                 → oversold zone without panic
3. Price_vs_VWAP < 0               → below VWAP (supports bounce)
4. Price near/below EMA_fast or EMA_mid  → mean-reversion proximity
5. StochRSI_K < 30                 → momentum oversold
```

**PUT Conditions** (contrarian fade from overbought):

```
1. Consecutive_Up >= 3 bars        → exhaustion buying
2. RSI in (50, 75)                 → overbought zone
3. Price_vs_VWAP > 0               → above VWAP (supports fade)
4. Price near/above EMA_fast or EMA_mid  → mean-reversion proximity
5. StochRSI_K > 70                 → momentum overbought
```

### Signal API

```python
from lib.signals import check_call_conditions, check_put_conditions, evaluate_signal

# Per-condition detail
call_score, call_conditions = check_call_conditions(
    row,
    consecutive_periods=3,
    rsi_range=(25, 50),
    ema_proximity=0.001,    # 0.1% proximity threshold
    stoch_rsi_threshold=30
)

put_score, put_conditions = check_put_conditions(
    row,
    consecutive_periods=3,
    rsi_range=(50, 75),
    ema_proximity=0.001,
    stoch_rsi_threshold=70
)

# Unified signal evaluation
result = evaluate_signal(row, min_conditions=3, ...)
# Returns:
# {
#   'direction': 'CALL' | 'PUT',
#   'base_score': 0-5,
#   'conditions_met': ['Consecutive_Down >= 3', 'RSI in (25, 50)', ...]
# }
```

### Total Score Composition

```
base_score   (0–5)  from conditions
+ combo_bonus (0–1)  if Strat combo aligns with direction
+ ftfc_bonus  (0–1)  if FTFC score > threshold and aligned
+ orb_bonus   (0–1)  if ORB trend aligns with direction
= total_score (0–8)  → mapped to position size label
```

---

## 6. Strat Classification System

### Module: `lib/strat.py`

Implements Rob Smith's The Strat candle classification, combo detection, and Full Timeframe Continuity (FTFC) scoring.

### Candle Types

| Code | Name | Condition |
|------|------|-----------|
| `1` | Inside Bar | `high < prev_high AND low > prev_low` |
| `2U` | Up Bar | `high > prev_high AND low >= prev_low` |
| `2D` | Down Bar | `low < prev_low AND high <= prev_high` |
| `3` | Outside Bar | `high > prev_high AND low < prev_low` |

### Combo Patterns

| Pattern | Description | Signal Implication |
|---------|-------------|-------------------|
| `2-1-2U` | Up bar, inside, up bar breakout | Continuation CALL setup |
| `2-1-2D` | Down bar, inside, down bar breakout | Continuation PUT setup |
| `3-1-2U` | Outside, inside, up breakout | Reversal CALL setup |
| `3-1-2D` | Outside, inside, down breakout | Reversal PUT setup |

### FTFC Score Calculation

```
ftfc_score = Σ(weight_tf × direction_tf)  for each timeframe

direction_tf:  +1 if bullish (2U candle)
               -1 if bearish (2D candle)
                0 if inside (1) or outside (3)

ftfc_score range: [-1.0, +1.0]
+1.0 = all timeframes bullish
-1.0 = all timeframes bearish
 0.0 = mixed / conflicted
```

### StratClassifier API

```python
from lib.strat import StratClassifier

clf = StratClassifier(config=config.strat)

# Single candle
label = clf.classify_candle(curr_high, curr_low, prev_high, prev_low)
# Returns: '1' | '2U' | '2D' | '3'

# Series (vectorized)
df['strat_candle'] = clf.classify_series(df)

# Trigger levels (prior bar H/L)
trigger_high, trigger_low = clf.get_trigger_levels(df)

# Combo detection
df = clf.detect_combos(df)
# Adds: df['strat_combo'], df['strat_setup']

# FTFC (requires dict of timeframe DataFrames)
ftfc_score, direction, labels = clf.calculate_ftfc({
    '5m': df_5m, '15m': df_15m, '1h': df_1h, 'D': df_daily, 'W': df_weekly
})

# Strat bonus for signal
bonus = clf.get_strat_bonus(
    signal_direction='CALL',
    combo=df['strat_combo'].iloc[-1],
    ftfc_score=ftfc_score,
    orb_trend='BULLISH'
)
# Returns: 0, 1, 2, or 3
```

---

## 7. Backtesting Engine

### Module: `lib/backtest.py`

Event-driven backtester that processes bars sequentially, applying all signal, Strat, and risk logic identically to the live monitor.

### Data Structures

**Trade Dataclass:**

```python
@dataclass
Trade:
    entry_time:     datetime
    entry_price:    float
    direction:      str                  # 'CALL' | 'PUT'
    base_score:     int                  # 0–5 from conditions
    strat_bonus:    int                  # 0–3 from Strat
    total_score:    int                  # 0–8 total
    position_size:  float                # 0.25 | 0.50 | 0.75 | 1.00
    indicators_at_entry: Dict[str, float]
    ftfc_score:     float
    ftfc_direction: str
    orb_trend:      str
    conditions_met: List[str]
    strat_combo:    str
    # Filled at exit:
    exit_time:      datetime
    exit_price:     float
    exit_reason:    str          # 'profit_target' | 'stop_loss' | 'time_stop' | 'rsi_exit'
    return_pct:     float
    mae:            float        # Max Adverse Excursion
    mfe:            float        # Max Favorable Excursion
```

**BacktestResult:**

```python
@dataclass
BacktestResult:
    trades:         List[Trade]
    daily_pnl:      List[Dict]
    equity_curve:   pd.Series
    filter_counts:  Dict           # ftfc_rejected, orb_rejected, signals_evaluated

    # Computed properties
    total_trades:   int
    winners:        int
    losers:         int
    win_rate:       float
    avg_win:        float
    avg_loss:       float
    profit_factor:  float
    sharpe_ratio:   float          # annualized
    max_drawdown:   float
    avg_mae:        float
    avg_mfe:        float
```

### Backtest Execution Flow

```
1. Load OHLCV data
   └─ DataLoader.load_intraday() OR load_daily()
   └─ add_all_indicators()

2. Build multi-timeframe DataFrames (if FTFC enabled)
   └─ aggregate_to_timeframe() for 5m, 15m, 1h, D, W

3. Process bars sequentially:
   For each bar in time series:
     a. Update ORB levels (5m, 15m, 30m tracking)
     b. evaluate_signal(row) → base_score, conditions
     c. If signal:
        - calculate_ftfc(tf_dfs) → ftfc_score, direction
        - get_strat_bonus() → strat_bonus
        - total_score = base_score + strat_bonus
        - Check FTFC filter (reject if score contradicts direction)
        - Check ORB filter (reject if ORB trend contradicts)
        - Check daily limits (max_daily_trades, daily_loss_limit)
        - Enter trade: Trade(entry_time, entry_price, direction, ...)
     d. For all open trades:
        - Check profit target exit
        - Check stop loss exit
        - Check time stop exit (30min/35min)
        - Check extreme RSI exit (>80 / <20)
        - Update trade.exit_* fields when exit triggered

4. Compute BacktestResult metrics
   └─ Sharpe = (mean_daily_return / std_daily_return) × √252
   └─ Max drawdown = max((peak - trough) / peak) across equity curve
```

### Walk-Forward Validation

```python
from lib.walk_forward import WalkForwardEngine

wf = WalkForwardEngine(config=config.walk_forward)
results = wf.run(
    ticker='IWM',
    train_months=6,
    test_months=1,
    overlap=False
)
# Returns list of (train_period, test_period, test_result) tuples
```

---

## 8. Data Layer

### Module: `lib/data_loader.py`

Unified data access with automatic Cloud SQL / Parquet fallback. Setting `CLOUD_SQL_CONNECTION_NAME` switches to Cloud SQL; omitting it uses local Parquet (zero code changes for local dev).

### DataLoader Class

```python
class DataLoader:
    def __init__(self, data_dir='data')

    # Primary load methods
    def load_intraday(ticker, start_date=None, end_date=None) → DataFrame
    def load_daily(ticker, year=None) → DataFrame
    def load_options(ticker, start_date=None, end_date=None,
                     option_type=None, source='etf') → DataFrame
    def load_trades(start_date=None, end_date=None, ticker=None) → DataFrame
    def load_best_available(ticker, start_date=None, end_date=None,
                            prefer_intraday=True) → DataFrame

    # Aggregation
    def aggregate_to_timeframe(df, timeframe) → DataFrame
        # timeframe: '5m' | '15m' | '30m' | '1h' | 'D' | 'W' | 'M'
    def build_multi_timeframe(df, timeframes=['5m','15m','1h','D','W']) → Dict[str, DataFrame]

    # Utilities
    def normalize_columns(df) → DataFrame   # canonical OHLCV names
    def load_summary(ticker) → dict          # latest summary JSON
```

### Load Priority Order

**`load_intraday()`:**

```
0. Cloud SQL: market_data_intraday   (when CLOUD_SQL_CONNECTION_NAME set)
1. Local: {ticker}/intraday/{ticker}_av_1min_combined.parquet
2. Local: {ticker}/intraday/{ticker}_av_1min_YYYYMM.parquet (monthly files)
3. Local: {ticker}/minute/{ticker}_minute_YYYYMMDD.parquet  (daily minute files)
4. Empty DataFrame
```

**`load_daily()`:**

```
0. Cloud SQL: market_data_daily      (when CLOUD_SQL_CONNECTION_NAME set)
1. Local: {ticker}/{ticker}_{year}.parquet
2. Empty DataFrame
```

### Column Normalization

All sources are normalized to canonical names before returning:

| Source Column | Canonical Name |
|---------------|----------------|
| `Last`, `last`, `Adj Close`, `adj_close` | `Close` |
| `open`, `high`, `low`, `close`, `volume` | `Open`, `High`, `Low`, `Close`, `Volume` |
| `timestamp` | `Time` |

### Resampling Rules

| Timeframe Key | Pandas Rule |
|---------------|-------------|
| `1m` | `1min` |
| `5m` | `5min` |
| `15m` | `15min` |
| `30m` | `30min` |
| `1h` | `1h` |
| `D` | `1D` |
| `W` | `W-FRI` |
| `M` | `ME` |

---

## 9. Cloud Infrastructure

### Component Summary

| Component | Service | Name | Config |
|-----------|---------|------|--------|
| Relational DB | Cloud SQL | `trading-db` | PostgreSQL 15, `db-g1-small`, 20 GB, us-east1 |
| Object Storage | Cloud Storage | `PROJECT-trading-data` | Standard, us-east1, 730-day raw/ lifecycle |
| Scheduled Jobs | Cloud Run Jobs | 7 jobs | 1–2 Gi memory, max-retries 1–2 |
| Real-time Monitor | Cloud Run Job | `signal-monitor` | 2 Gi, 8h timeout, 0 retries, scheduled 9:25 AM ET |
| Cron Triggers | Cloud Scheduler | 21 triggers | All America/New_York timezone |
| Container Images | Artifact Registry | `trading/trading-system` | us-east1 |
| Build | Cloud Build | (default) | `gcloud builds submit` |
| Secrets | Secret Manager | 6 secrets | See §14 |
| Identity | IAM Service Account | `trading-runner@PROJECT.iam` | Least-privilege roles |

### Service Account Roles

```
roles/cloudsql.client            → connect to trading-db
roles/storage.objectAdmin        → read/write GCS bucket
roles/run.invoker                → Cloud Scheduler → Cloud Run
roles/secretmanager.secretAccessor → read secrets at container startup
```

### Container Image

**`gcp/Dockerfile`:**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# psycopg2 + lxml system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc g++ curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY lib/ lib/
COPY gcp/ gcp/
COPY scripts/ scripts/
COPY alert_config.json .

CMD ["python", "-m", "gcp.premarket_brief"]   # overridden per-job at deploy time
```

**Artifact Registry path:** `us-east1-docker.pkg.dev/adept-mountain-474619-d4/trading/trading-system`

---

## 10. Cloud Run Jobs

### Job Overview

| Job Name | Module | Memory | CPU | Timeout | Max Retries |
|----------|--------|--------|-----|---------|-------------|
| `premarket-brief` | `gcp.premarket_brief` | 1 Gi | 1 | 300s | 1 |
| `signal-monitor` | `gcp.signal_monitor` | 2 Gi | 1 | 28800s (8h) | 0 |
| `weekend-review` | `gcp.weekend_review` | 1 Gi | 1 | 300s | 1 |
| `fetch-market-data` | `gcp.fetchers.fetch_market_data` | 1 Gi | 1 | 600s | 1 |
| `fetch-etf-options` | `gcp.fetchers.fetch_etf_options` | 1 Gi | 1 | 300s | 2 |
| `fetch-earnings-options` | `gcp.fetchers.fetch_earnings_options` | 1 Gi | 1 | 300s | 2 |
| `fetch-alphavantage-intraday` | `gcp.fetchers.fetch_alphavantage_intraday` | 2 Gi | 1 | 3600s | 1 |

### Cloud Scheduler Triggers (21 total)

| Trigger Name | Cron (ET) | Target Job |
|-------------|-----------|------------|
| `premarket-brief-daily` | `30 8 * * 1-5` | premarket-brief |
| `weekend-review-saturday` | `0 9 * * 6` | weekend-review |
| `fetch-market-data-daily` | `0 17 * * 1-5` | fetch-market-data |
| `etf-options-open` | `30 9 * * 1-5` | fetch-etf-options |
| `etf-options-open-2` | `35 9 * * 1-5` | fetch-etf-options |
| `etf-options-open-3` | `40 9 * * 1-5` | fetch-etf-options |
| `etf-options-mid-morning` | `0 10 * * 1-5` | fetch-etf-options |
| `etf-options-late-morning` | `30 11 * * 1-5` | fetch-etf-options |
| `etf-options-afternoon-1` | `0 13 * * 1-5` | fetch-etf-options |
| `etf-options-afternoon-2` | `30 14 * * 1-5` | fetch-etf-options |
| `etf-options-power-hour` | `30 15 * * 1-5` | fetch-etf-options |
| `etf-options-close` | `5 16 * * 1-5` | fetch-etf-options |
| `earnings-options-preopen` | `0 9 * * 1-5` | fetch-earnings-options |
| `earnings-options-open` | `35 9 * * 1-5` | fetch-earnings-options |
| `earnings-options-mid` | `0 10 * * 1-5` | fetch-earnings-options |
| `earnings-options-noon` | `0 12 * * 1-5` | fetch-earnings-options |
| `earnings-options-close-1` | `50 15 * * 1-5` | fetch-earnings-options |
| `earnings-options-close-2` | `30 16 * * 1-5` | fetch-earnings-options |
| `alphavantage-intraday-monthly` | `0 21 1 * *` | fetch-alphavantage-intraday |
| `analyze-market-data-daily` | `0 18 * * 1-5` | (future) |
| `run-pipeline-daily` | `30 18 * * 1-5` | (future) |

### Data Flow: Pre-Market Brief

```
Cloud Scheduler (8:30 AM ET)
    ↓
Cloud Run Job: premarket-brief
    ↓
For each ticker [SPY, IWM, QQQ]:
  ├─ DataLoader.load_daily(ticker)          → Cloud SQL market_data_daily
  ├─ add_all_indicators()                   → RSI, EMA, consecutive, etc.
  ├─ StratClassifier.classify_series()      → candle labels
  ├─ StratClassifier.detect_combos()        → strat_combo, strat_setup
  ├─ DataLoader.build_multi_timeframe()     → {D, W, M} aggregated DataFrames
  ├─ StratClassifier.calculate_ftfc()       → ftfc_score, direction
  ├─ check_call/put_conditions()            → premarket signal status
  └─ Compile: price, RSI, strat, FTFC, signal_status, prev H/L
    ↓
Format Discord embed (per-ticker sections)
    ↓
POST to DISCORD_WEBHOOK_URL
    ↓
INSERT premarket_analysis row → Cloud SQL
```

### Data Flow: Real-Time Signal Monitor

```
Cloud Run Job: signal-monitor (scheduled 9:25 AM ET, exits at 16:00 ET)

Every 60 seconds:
    ↓
For each ticker [SPY, IWM, QQQ]:
  ├─ yfinance.download(ticker, period='1d', interval='1m')
  ├─ Append new bar to rolling_window (keep 200 bars)
  ├─ add_all_indicators(rolling_window)
  ├─ Track ORB levels (update if within first 5/15/30 min)
  ├─ evaluate_signal(latest_row)            → base_score, conditions
  ├─ StratClassifier.detect_combos()        → strat_combo
  ├─ get_strat_bonus()                      → strat_bonus
  ├─ total_score = base_score + strat_bonus
  ├─ Check daily limits (max_daily_trades, daily_loss_limit)
  └─ If signal fires:
       ├─ fire_discord_alert() with:
       │    direction, price, total score, strength label
       │    base/strat breakdown, conditions, target, stop, RSI, RVOL, ORB
       └─ trade_logger.log_trade() → Cloud SQL trades + Parquet backup
    ↓
Sleep 60 seconds
```

### Data Flow: ETF Options (9x/day)

```
Cloud Scheduler (one of 9 daily triggers)
    ↓
Cloud Run Job: fetch-etf-options
    ↓
For each ticker [SPY, IWM, QQQ, SPX]:
  ├─ get_market_session()           → OPEN_VOLATILE | MORNING | MIDDAY |
  │                                    AFTERNOON | POWER_HOUR | CLOSE
  ├─ yahooquery.Ticker(ticker).option_chain  → full options chain DataFrame
  ├─ Fetch underlying price (spot)
  ├─ enrich_with_greeks(df)          → Black-Scholes via py_vollib
  │    delta, gamma, theta, vega, rho per contract
  └─ normalize_for_sql(df, snapshot_ts, market_session)
    ↓
UPSERT etf_options_snapshots         → Cloud SQL
    (ON CONFLICT (ticker, snapshot_ts, option_type, expiration, strike))
    ↓
Upload parquet backup               → GCS raw/options/etfs/{TICKER}_{ts}.parquet
```

### Data Flow: AlphaVantage Intraday (monthly)

```
Cloud Scheduler (1st of month, 9 PM ET)
    ↓
Cloud Run Job: fetch-alphavantage-intraday --symbol ALL
    ↓
For each symbol [SPY, IWM, QQQ]:
  └─ For each month in range:
       ├─ parquet_exists_in_gcs(bucket, path)?  → skip if found
       ├─ Rate limit: sleep 13s between calls (5 calls/min free tier)
       ├─ Rotate API key if needed (up to 5 keys: ALPHA_VANTAGE_API_KEY, _2-_5)
       ├─ GET AlphaVantage TIME_SERIES_INTRADAY (1min, full outputsize)
       ├─ Parse JSON → DataFrame with ts, open, high, low, close, volume
       ├─ Localize timestamps: America/New_York → UTC
       ├─ BULK INSERT market_data_intraday   → Cloud SQL
       └─ Upload parquet                    → GCS raw/{ticker}/intraday/{ticker}_av_1min_YYYYMM.parquet
```

---

## 11. Cloud SQL Schema

**Instance:** `trading-db` (PostgreSQL 15, `db-g1-small`, `us-east1`)
**Database:** `trading`
**Schema file:** [gcp/schema.sql](../gcp/schema.sql)

### Tables

| Table | Primary Purpose | Unique Key | Est. Rows |
|-------|----------------|------------|-----------|
| `market_data_daily` | OHLCV + 40 indicators per day | `(ticker, date)` | ~10K/ticker/yr |
| `market_data_intraday` | 1-min bars (partitioned) | `(ticker, interval, ts)` | ~500K/ticker/yr |
| `etf_options_snapshots` | ETF options chains + Greeks | `(ticker, snapshot_ts, option_type, expiration, strike)` | ~50K/day |
| `earnings_options_snapshots` | Earnings strategy options | `(symbol, snapshot_ts, option_type, expiration, strike)` | ~100K/day |
| `signal_alerts` | Fired signals with conditions | auto-id | ~50/day |
| `trades` | Logged trades (entry/exit) | `(ticker, entry_time)` | ~10/week |
| `premarket_analysis` | Daily pre-market brief data | `(analysis_date, ticker)` | 4/day |
| `economic_events` | Economic calendar | `(event_date, event_name)` | ~20/week |

### market_data_daily Columns

```sql
ticker          VARCHAR(10)
date            DATE
open, high, low, close  DECIMAL(10,4)
volume          BIGINT
-- Indicators
rsi_14          DECIMAL(8,4)
ema_9, ema_21   DECIMAL(10,4)
atr_14          DECIMAL(10,4)
vwap            DECIMAL(10,4)
rvol            DECIMAL(8,4)
obv             BIGINT
stoch_rsi_k, stoch_rsi_d        DECIMAL(8,4)
consecutive_up, consecutive_down INTEGER
price_vs_vwap   DECIMAL(10,6)
-- Strat
strat_candle    VARCHAR(5)       -- '1' | '2U' | '2D' | '3'
strat_combo     VARCHAR(20)      -- '2-1-2U', '3-1-2D', etc.
strat_setup     BOOLEAN
ftfc_score      DECIMAL(6,4)
ftfc_direction  VARCHAR(10)
inserted_at     TIMESTAMPTZ DEFAULT NOW()
updated_at      TIMESTAMPTZ DEFAULT NOW()
```

### market_data_intraday (partitioned)

```sql
-- Parent table (LIST partitioned by ticker); no surrogate id column
ticker          VARCHAR(10)
ts              TIMESTAMPTZ
interval        VARCHAR(10)     -- '1min' | '5min' | '15min'
open, high, low, close  DECIMAL(10,4)
volume          BIGINT
data_source     VARCHAR(20)     -- 'alphavantage' | 'yfinance'
inserted_at     TIMESTAMPTZ DEFAULT NOW()

PRIMARY KEY (ticker, interval, ts)  -- composite PK; deduplication on upsert

-- Partitions
market_data_intraday_spy   WHERE ticker = 'SPY'
market_data_intraday_iwm   WHERE ticker = 'IWM'
market_data_intraday_qqq   WHERE ticker = 'QQQ'
market_data_intraday_spx   WHERE ticker = 'SPX'
market_data_intraday_other WHERE ticker NOT IN ('SPY','IWM','QQQ','SPX')
```

### etf_options_snapshots Columns

```sql
ticker           VARCHAR(10)
snapshot_ts      TIMESTAMPTZ
snapshot_date    DATE
market_session   VARCHAR(20)     -- 'OPEN_VOLATILE' | 'MORNING' | 'MIDDAY' | etc.
option_type      VARCHAR(5)      -- 'calls' | 'puts'
expiration       DATE
strike           DECIMAL(10,2)
contract_symbol  VARCHAR(30)
bid, ask, last_price  DECIMAL(10,4)
volume           INTEGER
open_interest    INTEGER
implied_volatility DECIMAL(10,6)
-- Greeks
delta, gamma, theta, vega, rho  DECIMAL(10,6)
in_the_money     BOOLEAN
inserted_at      TIMESTAMPTZ DEFAULT NOW()
```

### Useful Queries

```sql
-- Latest daily bars
SELECT date, close, rsi_14, ema_9, rvol, strat_candle, ftfc_score
FROM market_data_daily
WHERE ticker = 'IWM' ORDER BY date DESC LIMIT 10;

-- All-time signal history
SELECT ticker, direction, base_score + strat_bonus AS total_score,
       signal_time, entry_price, conditions
FROM signal_alerts ORDER BY signal_time DESC LIMIT 50;

-- ETF options flow by session
SELECT market_session,
       count(*) AS contracts,
       avg(implied_volatility) AS avg_iv,
       avg(delta) AS avg_delta
FROM etf_options_snapshots
WHERE ticker = 'SPY' AND snapshot_date = CURRENT_DATE
GROUP BY market_session ORDER BY market_session;

-- Weekly trade performance
SELECT direction, count(*) AS trades,
       round(avg(return_pct) * 100, 2) AS avg_return_pct,
       sum(CASE WHEN return_pct > 0 THEN 1 ELSE 0 END) AS winners
FROM trades
WHERE entry_time >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY direction;

-- Row counts across all tables
SELECT 'market_data_daily' AS tbl, count(*) FROM market_data_daily
UNION ALL SELECT 'market_data_intraday', count(*) FROM market_data_intraday
UNION ALL SELECT 'etf_options_snapshots', count(*) FROM etf_options_snapshots
UNION ALL SELECT 'trades', count(*) FROM trades;
```

### Connecting to Cloud SQL

```bash
# Cloud SQL Auth Proxy (local dev)
cloud-sql-proxy adept-mountain-474619-d4:us-east1:trading-db &
psql -h 127.0.0.1 -U trading_user -d trading

# One-off via gcloud
gcloud sql connect trading-db --user=trading_user --database=trading
```

---

## 12. Data Migration

### Module: `gcp/migrate_to_gcp.py`

Migrates all local Parquet files to GCS (raw backup) and Cloud SQL (structured query).

### Migration Scope

```
data/
  spy/spy_2024.parquet               → market_data_daily  (ticker='SPY', year=2024)
  spy/spy_2025.parquet               → market_data_daily  (ticker='SPY', year=2025)
  spy/intraday/spy_av_1min_combined.parquet → market_data_intraday (bulk insert, 10K rows/chunk)
  iwm/...                            → (same pattern)
  qqq/...                            → (same pattern)
  options/etfs/*.parquet             → etf_options_snapshots
  options/earnings/earnings_options_YYYYMMDD.parquet → earnings_options_snapshots
  trades/*.parquet                   → trades
  ALL *.parquet                      → gs://PROJECT-trading-data/raw/{relative_path}
```

### Column Normalization (Migration)

The migration script maps local DataFrame column names to Cloud SQL snake_case names:

| Local DataFrame | Cloud SQL Column |
|-----------------|-----------------|
| `Close` | `close` |
| `RSI_14` | `rsi_14` |
| `EMA9` | `ema_9` |
| `EMA21` | `ema_21` |
| `ATR_14` | `atr_14` |
| `RVOL` | `rvol` |
| `OBV` | `obv` |
| `StochRSI_K` | `stoch_rsi_k` |
| `Consecutive_Up` | `consecutive_up` |
| `Price_vs_VWAP` | `price_vs_vwap` |
| `contractSymbol` | `contract_symbol` |
| `optionType` | `option_type` |

### Migration Commands

```bash
# Dry run — shows what will be migrated without writing
python gcp/migrate_to_gcp.py --dry-run

# Full migration
python gcp/migrate_to_gcp.py

# Individual tables
python gcp/migrate_to_gcp.py --table market_data_daily
python gcp/migrate_to_gcp.py --table market_data_intraday
python gcp/migrate_to_gcp.py --table etf_options_snapshots

# Skip GCS (SQL only)
python gcp/migrate_to_gcp.py --skip-gcs --table market_data_daily

# Via deploy.sh
./gcp/deploy.sh migrate
./gcp/deploy.sh migrate --dry-run
```

**Note:** Intraday migration is large (~5M+ rows per ticker). Run from GCP Cloud Shell (co-located with Cloud SQL) to avoid timeouts and bandwidth costs.

---

## 13. Deployment

### Prerequisites

```bash
# Verify authenticated and correct project
gcloud auth list
gcloud config get-value project
# Expected: adept-mountain-474619-d4
# ✅ Done — authenticated as teneika@bictech.org, project confirmed

# Verify Python deps installed
python -c "from gcp.database import is_cloud_sql_configured; print('OK')"
python -c "from google.cloud import storage; print('OK')"
```

### Step-by-Step Deployment

**Step 0 — Enable APIs (already done ✅)**

All required APIs were enabled on 2026-02-22:
`sqladmin`, `run`, `cloudscheduler`, `storage`, `artifactregistry`,
`cloudbuild`, `secretmanager`, `iam`, `iamcredentials`, `logging`, `monitoring`.

**Step 1 — Provision infrastructure (run once)**

```bash
chmod +x gcp/setup_cloud_sql.sh gcp/deploy.sh
./gcp/deploy.sh setup
```

Creates: Cloud SQL instance `trading-db` (~5 min), database, user, GCS bucket, service account, Artifact Registry repo, applies schema, stores 4 secrets.

**Step 2 — Store remaining secrets**

```bash
echo -n 'https://discord.com/api/webhooks/YOUR_ID/TOKEN' | \
  gcloud secrets create discord-webhook --data-file=- --replication-policy=automatic

echo -n 'YOUR_AV_KEY' | \
  gcloud secrets create av-api-key --data-file=- --replication-policy=automatic
```

**Step 3 — Migrate existing data**

```bash
./gcp/deploy.sh migrate --dry-run   # preview
./gcp/deploy.sh migrate             # full migration (~30-60 min)
```

**Step 4 — Build Docker image**

```bash
./gcp/deploy.sh build
# Copies only lib/, gcp/, scripts/, requirements-gcp.txt, alert_config.json to a temp dir,
# then runs: gcloud builds submit --tag IMAGE <tmpdir>
# Avoids uploading the 4 GB data/ directory to Cloud Build (~86 files / ~1.3 MB context)
# Expected: 2-3 minutes
```

**Step 5 — Deploy Cloud Run jobs**

```bash
./gcp/deploy.sh fetchers    # all 4 data-fetching jobs
./gcp/deploy.sh premarket
./gcp/deploy.sh weekend
./gcp/deploy.sh monitor     # signal-monitor job (Cloud Run Job, not Service)
```

**Step 6 — Create Cloud Scheduler triggers**

```bash
./gcp/deploy.sh schedulers  # creates all 21 cron triggers
```

**Step 7 — Full deploy (steps 4-6)**

```bash
./gcp/deploy.sh all
```

**Step 8 — Validate**

```bash
# Manual test
gcloud run jobs execute fetch-market-data --region us-east1

# Verify data
gcloud sql connect trading-db --user=trading_user --database=trading
# > SELECT count(*), max(date) FROM market_data_daily;

# Check GCS
gcloud storage ls gs://adept-mountain-474619-d4-trading-data/raw/
```

### Deploy Script Commands Summary

```bash
./gcp/deploy.sh setup       # Provision all infrastructure
./gcp/deploy.sh migrate     # Parquet → GCS + Cloud SQL
./gcp/deploy.sh build       # Build + push Docker image
./gcp/deploy.sh premarket   # Deploy premarket-brief job
./gcp/deploy.sh monitor     # Deploy signal-monitor service
./gcp/deploy.sh weekend     # Deploy weekend-review job
./gcp/deploy.sh fetchers    # Deploy all 4 fetch jobs
./gcp/deploy.sh schedulers  # Create 21 Cloud Scheduler triggers
./gcp/deploy.sh all         # build + fetchers + premarket + monitor + weekend + schedulers
```

---

## 14. Environment Variables & Secrets

### Secret Manager Secrets

| Secret Name | Content | Used By |
|-------------|---------|---------|
| `cloud-sql-connection-name` | `adept-mountain-474619-d4:us-east1:trading-db` | All Cloud Run jobs |
| `db-trading-user` | `trading_user` | All Cloud Run jobs |
| `db-trading-pass` | (generated at setup) | All Cloud Run jobs |
| `gcs-trading-bucket` | `adept-mountain-474619-d4-trading-data` | All Cloud Run jobs |
| `discord-webhook` | Discord webhook URL | premarket, signal-monitor, weekend |
| `av-api-key` | AlphaVantage API key | fetch-alphavantage-intraday |

### Cloud Run Environment Variables

All jobs receive these via `--set-env-vars`:

```
CLOUD_SQL_CONNECTION_NAME  adept-mountain-474619-d4:us-east1:trading-db
DB_USER                    trading_user
DB_PASS                    (from secret)
DB_NAME                    trading
GCS_BUCKET                 adept-mountain-474619-d4-trading-data
DISCORD_WEBHOOK_URL        (from secret, optional)
```

### Local Development (`.env`)

```bash
# .env — never commit this file
CLOUD_SQL_CONNECTION_NAME=adept-mountain-474619-d4:us-east1:trading-db
DB_USER=trading_user
DB_PASS=YOUR_DB_PASSWORD
DB_NAME=trading
GCS_BUCKET=adept-mountain-474619-d4-trading-data
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
ALPHA_VANTAGE_API_KEY=YOUR_KEY
```

Activate for local testing:

```bash
export $(grep -v '^#' .env | xargs)
python -m gcp.premarket_brief    # runs against Cloud SQL
```

### Cloud SQL Mode Detection

```python
# lib/data_loader.py and gcp/
def _cloud_sql_active() -> bool:
    return bool(os.environ.get('CLOUD_SQL_CONNECTION_NAME'))
```

When not set: all data access uses local Parquet files (no changes required for local backtesting).

---

## 15. GitHub Actions Cutover

### Workflows to Move to Cloud Run

Once GCP jobs are validated with 1 week of parallel operation, disable the equivalent workflows:

| Cloud Run Job | GitHub Action to Disable | Command |
|--------------|--------------------------|---------|
| `fetch-market-data` | `fetch-market-data.yml` | `gh workflow disable fetch-market-data.yml` |
| `fetch-etf-options` | `fetch_etf_options.yml` | `gh workflow disable fetch_etf_options.yml` |
| `fetch-earnings-options` | `fetch-earnings-options.yml` | `gh workflow disable fetch-earnings-options.yml` |
| `fetch-alphavantage-intraday` | `fetch-alphavantage-intraday-monthly.yml` | `gh workflow disable fetch-alphavantage-intraday-monthly.yml` |

```bash
# Disable (keeps file, stops running)
gh workflow disable fetch-market-data.yml

# Re-enable if needed
gh workflow enable fetch-market-data.yml
```

### Workflows to Keep in GitHub Actions

| Workflow | Reason |
|----------|--------|
| `handle-workflow-failure.yml` | GitHub-native issue/PR creation |
| `backtest-pipeline.yml` | Manual, produces GitHub artifacts |
| `validate-market-data.yml` | PR quality gate |
| `deploy-trading-apps.yml` | Web app deployment |
| `download-google-sheets.yml` | Sheets-specific integration |

---

## 16. Monitoring & Operations

### Cloud Logging Queries

```bash
# All logs for a specific job
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="fetch-etf-options"' \
  --limit 100 --format="value(timestamp,textPayload)"

# Errors across all jobs
gcloud logging read \
  'resource.type="cloud_run_job" AND severity>=ERROR' \
  --limit 50

# Signal alerts fired today
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="signal-monitor" \
   AND textPayload=~"SIGNAL"' --limit 20
```

### Job Execution Status

```bash
# List recent executions
gcloud run jobs executions list \
  --region us-east1 \
  --format="table(name,createTime,completionTime,status.condition)"

# Manually trigger a job
gcloud run jobs execute fetch-etf-options --region us-east1

# Stream logs for an execution
gcloud run jobs executions logs fetch-etf-options-xxxxx --region us-east1
```

### Data Freshness Check

```bash
gcloud sql connect trading-db --user=trading_user --database=trading
```

```sql
-- Per-ticker data freshness
SELECT ticker, max(date) AS latest_date, count(*) AS total_rows
FROM market_data_daily
GROUP BY ticker ORDER BY ticker;

-- Latest options snapshot
SELECT ticker, max(snapshot_ts) AS latest_snapshot
FROM etf_options_snapshots
GROUP BY ticker;

-- Trade log activity
SELECT date_trunc('week', entry_time) AS week,
       count(*) AS trades,
       avg(return_pct) AS avg_return
FROM trades
GROUP BY 1 ORDER BY 1 DESC LIMIT 8;
```

### Upload Strategy CSVs to GCS

The `fetch-earnings-options` job reads active tickers from strategy CSVs in GCS:

```bash
for f in google-apps-script/data/*.csv; do
  gsutil cp "$f" gs://adept-mountain-474619-d4-trading-data/sheets/
done
```

---

## 17. Cost Estimate

*Based on `us-east1` pricing, February 2026.*

| Service | Configuration | Est. Monthly Cost |
|---------|--------------|------------------|
| Cloud SQL | `db-g1-small`, 20 GB SSD, daily backups | ~$25/mo |
| Cloud Run Jobs | 7 jobs × ~50 executions/day avg × 1-2 min | ~$3/mo |
| Cloud Run Job | signal-monitor, 8h timeout, 0 retries, scheduled daily | ~$3/mo |
| Cloud Storage | ~50 GB + 15 write ops/day | ~$2/mo |
| Cloud Scheduler | 21 triggers × ~20 weekdays/mo | ~$0.21/mo |
| Secret Manager | 6 secrets × ~100 accesses/day | ~$0.06/mo |
| Artifact Registry | ~1 GB images | ~$0.10/mo |
| Cloud Build | ~1 build/week × 5 min | ~$0.25/mo |
| **Total** | | **~$38/mo** |

Cloud SQL dominates cost. For dev/staging: `db-f1-micro` costs ~$7/mo.

---

## 18. Troubleshooting

### "Cloud SQL not configured" in logs

`CLOUD_SQL_CONNECTION_NAME` is not injected into the container. Check:

```bash
# Verify secret exists
gcloud secrets versions access latest --secret=cloud-sql-connection-name

# Verify service account IAM binding
gcloud projects get-iam-policy adept-mountain-474619-d4 \
  --flatten="bindings[].members" \
  --filter="bindings.members:trading-runner"
```

### `pg8000` import error

```bash
grep "cloud-sql-python-connector" requirements.txt
./gcp/deploy.sh build   # Rebuild image with latest requirements
```

### "Unable to connect to Cloud SQL"

```bash
# Confirm instance is running
gcloud sql instances describe trading-db --format="value(state)"
# Expected: RUNNABLE
```

### ETF options fetch returns "No data"

Yahoo Finance / yahooquery rate limits. Job has `max-retries 2`. If persistent:

```bash
python -c "from yahooquery import Ticker; t = Ticker('IWM'); print(type(t.option_chain))"
```

### `struct.pack` / pg8000 parameter count crash during migration

pg8000 uses a 16-bit unsigned short for the parameter count, so any single INSERT
statement with more than 65 535 parameters causes a `struct.pack('H', ...)` overflow.
The `bulk_insert_dataframe` function now uses SQLAlchemy Core (not `pandas.to_sql`)
with `chunksize=2000` (safe for tables up to 32 columns: 2000 × 32 = 64 000 params).
`migrate_to_gcp.py` uses `chunksize=5000` for `market_data_intraday` (9 columns → 45 000
params per batch, well within the limit). If you see this crash, reduce the chunksize.

### Migration OOM / timeout

For large intraday files, run from GCP Cloud Shell (co-located with Cloud SQL):

```bash
# Skip GCS backup to speed up (run separately)
python gcp/migrate_to_gcp.py --table market_data_intraday --skip-gcs
```

### signal-monitor not running

`signal-monitor` is a **Cloud Run Job** (not a Service) scheduled at 9:25 AM ET. It exits at 16:00 ET via Python `is_market_hours()` check. To trigger manually:

```bash
gcloud run jobs execute signal-monitor --region us-east1
# View execution status:
gcloud run jobs executions list --job signal-monitor --region us-east1
```

### AlphaVantage rate limit errors

Check how many API keys are configured:

```bash
gcloud secrets list --filter="name:av-api-key" --format="value(name)"
# Should show av-api-key, av-api-key-2, av-api-key-3 etc.
```

Add backup keys to Secret Manager and set `ALPHA_VANTAGE_API_KEY_2`, `_3`, etc. as env vars.

### Tests failing after changes

```bash
make test           # 339 unit/integration tests (~70s)
make test-e2e       # 28 Playwright tests (~15s)
make test-scripts   # 18 CLI regression tests (~40s)
```

All test suites must pass before submitting a build.
