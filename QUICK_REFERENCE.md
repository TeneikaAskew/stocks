# Stock Market Analysis - Quick Reference Guide

## Backtesting & Strat Commands

### Run Backtests
```bash
# Single ticker backtest
python scripts/run_backtest.py --ticker IWM --use-strat

# Multi-timeframe sweep (tests 1m/5m/15m/30m/1h + combo filters)
python scripts/run_timeframe_sweep.py --ticker IWM --use-strat

# All tickers
for ticker in IWM SPY QQQ; do
    python scripts/run_timeframe_sweep.py --ticker $ticker --use-strat
done

# Run tests
python -m pytest tests/ -v  # 297 tests
```

### Strat Candle Types
```
Type 1 (Inside):  curr_high <= prev_high AND curr_low >= prev_low
Type 2U (Up):     curr_high > prev_high AND curr_low >= prev_low
Type 2D (Down):   curr_high <= prev_high AND curr_low < prev_low
Type 3 (Outside): curr_high > prev_high AND curr_low < prev_low
```

### FTFC Weights
```
Daily: 0.35, 1h: 0.25, 15m: 0.20, 5m: 0.10, Weekly: 0.10
Score > 0.6 = aligned (trade allowed + bonus)
Score contradicts signal at 0.3 threshold = trade REJECTED
```

### Signal Scoring (with Strat)
```
Base: 3-of-5 conditions (consecutive moves, RSI, VWAP, EMA, StochRSI)
+1 Strat combo bonus (reversal confirms direction)
+1 FTFC alignment bonus (score >= 0.6)
+1 ORB alignment bonus (ORB trend matches direction)
Max: 8 points → 100% position size
```

---

## Indicator Reference

### New Features at a Glance

### Historical Levels (80 columns)
```python
# Previous period levels
Prev_Day_High, Prev_Day_Low, Prev_Day_HL_Mid
Prev_Week_High, Prev_Week_Low, Prev_Week_HL_Mid
Prev_Month_High, Prev_Month_Low, Prev_Month_HL_Mid
Prev_Year_High, Prev_Year_Low, Prev_Year_HL_Mid

# Price position (%)
Prev_Day_High_Pct, Prev_Day_Low_Pct
Prev_Week_High_Pct, Prev_Week_Low_Pct
# ... etc

# Breakout flags (1 or 0)
Broke_Prev_Day_High, Broke_Prev_Day_Low
Broke_Prev_Week_High, Broke_Prev_Week_Low
# ... etc

# At level flags (1 or 0)
At_Prev_Day_High, At_Prev_Day_Low
At_Prev_Week_HL_Mid
# ... etc
```

### ORB - Opening Range Breakout (108 columns)
```python
# For each timeframe (5m, 15m, 30m)
ORB_{5m/15m/30m}_High, _Low, _Mid, _Range

# Price position
ORB_{5m/15m/30m}_High_Pct, _Low_Pct, _Mid_Pct

# Trend indicators
ORB_{5m/15m/30m}_Trend  # 1=bullish, -1=bearish, 0=neutral
ORB_{5m/15m/30m}_Broke_High  # 1 if broke above
ORB_{5m/15m/30m}_Broke_Low   # 1 if broke below
ORB_{5m/15m/30m}_Within_Range  # 1 if sideways
ORB_{5m/15m/30m}_Distance  # Distance from range
```

### Order Blocks (7 columns)
```python
Order_Block_High, Order_Block_Low, Order_Block_Mid
Order_Block_Position  # 1=above, 0=within, -1=below
Order_Block_Distance  # Distance from block
Order_Block_Test  # 1 if testing the block
Order_Block_Zone  # 1 if in consolidation
```

## Common Analysis Patterns

### 1. Breakout Confirmation
```python
# CALL on bullish breakout with multiple confirmations
signals[
    (signals['trade_type'] == 'call') &
    (signals['entry_broke_prev_day_high'] == 1) &  # Broke resistance
    (signals['entry_orb_30m_trend'] == 1) &  # Bullish session
    (signals['entry_rsi'] < 70)  # Not overbought
]
```

### 2. Support Bounce
```python
# CALL at previous week low (support test)
signals[
    (signals['trade_type'] == 'call') &
    (signals['entry_at_prev_week_low'] == 1) &  # At support
    (signals['entry_rsi'] < 50)  # Oversold
]
```

### 3. Resistance Rejection
```python
# PUT at previous day high (resistance test)
signals[
    (signals['trade_type'] == 'put') &
    (signals['entry_at_prev_day_high'] == 1) &  # At resistance
    (signals['entry_rsi'] > 50)  # Overbought
]
```

### 4. ORB Trend Following
```python
# Trade with ORB trend
bullish_orb = signals[
    (signals['entry_orb_30m_trend'] == 1) &  # Bullish
    (signals['entry_orb_30m_broke_high'] == 1)  # Broke ORB
]

bearish_orb = signals[
    (signals['entry_orb_30m_trend'] == -1) &  # Bearish
    (signals['entry_orb_30m_broke_low'] == 1)  # Broke ORB
]
```

### 5. Order Block Tests
```python
# Signals testing order blocks
signals[signals['entry_order_block_test'] == 1]

# Above order block (cleared resistance)
signals[signals['entry_order_block_position'] == 1]

# Below order block (failed support)
signals[signals['entry_order_block_position'] == -1]
```

### 6. Multi-Timeframe ORB
```python
# All ORB timeframes bullish
signals[
    (signals['entry_orb_5m_trend'] == 1) &
    (signals['entry_orb_15m_trend'] == 1) &
    (signals['entry_orb_30m_trend'] == 1)
]

# ORB conflict (choppy)
signals[
    (signals['entry_orb_5m_trend'] == 1) &
    (signals['entry_orb_30m_trend'] == -1)
]
```

### 7. Level Confluence
```python
# Previous day high near previous week high
signals[
    (signals['entry_at_prev_day_high'] == 1) &
    (abs(signals['entry_vs_prev_week_high_pct']) < 0.5)  # Within 0.5%
]
```

## Win Rate Analysis Template

```python
import pandas as pd

signals = pd.read_csv('data/historical_iwm_0824_0825_signals.csv')

def analyze_pattern(df, name):
    """Analyze pattern performance"""
    if len(df) == 0:
        print(f"{name}: No signals found")
        return

    win_rate = (df['return_pct'] > 0).mean()
    avg_return = df['return_pct'].mean()
    profitable = df[df['return_pct'] > 0]
    losing = df[df['return_pct'] <= 0]

    print(f"\n{name}")
    print(f"  Total signals: {len(df)}")
    print(f"  Win rate: {win_rate:.1%}")
    print(f"  Avg return: {avg_return:.2f}%")
    print(f"  Avg winner: {profitable['return_pct'].mean():.2f}%")
    print(f"  Avg loser: {losing['return_pct'].mean():.2f}%")
    print(f"  Best trade: {df['return_pct'].max():.2f}%")
    print(f"  Worst trade: {df['return_pct'].min():.2f}%")

# Example usage
calls = signals[signals['trade_type'] == 'call']
puts = signals[signals['trade_type'] == 'put']

analyze_pattern(calls, "All CALL Signals")
analyze_pattern(puts, "All PUT Signals")

# Specific patterns
day_high_breakout = calls[calls['entry_broke_prev_day_high'] == 1]
analyze_pattern(day_high_breakout, "CALL: Day High Breakout")

orb_bullish = calls[calls['entry_orb_30m_trend'] == 1]
analyze_pattern(orb_bullish, "CALL: Bullish ORB")
```

## Correlation Analysis Template

```python
import numpy as np
import pandas as pd

signals = pd.read_csv('data/historical_iwm_0824_0825_signals.csv')

# Features to analyze
features = [
    'entry_vs_prev_day_high_pct',
    'entry_vs_prev_day_low_pct',
    'entry_vs_prev_week_high_pct',
    'entry_orb_5m_distance',
    'entry_orb_15m_distance',
    'entry_orb_30m_distance',
    'entry_order_block_distance',
    'entry_rsi',
    'entry_atr',
]

print("Correlation with Returns:")
print("-" * 50)

correlations = []
for feat in features:
    if feat in signals.columns:
        # Remove NaN values
        valid_data = signals[[feat, 'return_pct']].dropna()

        if len(valid_data) > 10:
            corr = np.corrcoef(valid_data[feat], valid_data['return_pct'])[0, 1]
            correlations.append({
                'feature': feat,
                'correlation': corr,
                'abs_corr': abs(corr)
            })

# Sort by absolute correlation
corr_df = pd.DataFrame(correlations).sort_values('abs_corr', ascending=False)

for _, row in corr_df.iterrows():
    print(f"{row['feature']:35s}: {row['correlation']:+.3f}")
```

## Quick Commands

```bash
# Run full analysis (all data)
python trading_analysis.py -all

# Run limited analysis (last 2 months)
python trading_analysis.py -months 2

# Run analysis for specific symbol
python trading_analysis.py -symbol SPY

# Run trade analysis pipeline (validates real trades)
python trade_analysis_pipeline.py

# Run backtests
python scripts/run_backtest.py --ticker IWM --use-strat
python scripts/run_timeframe_sweep.py --ticker IWM --use-strat

# Run all tickers
for ticker in IWM SPY QQQ; do
    python scripts/run_timeframe_sweep.py --ticker $ticker --use-strat
done

# Run Phase analysis (7-phase statistical system)
python scripts/analysis/phase1_strat_mining.py --ticker IWM
python scripts/analysis/phase2_indicator_confirmation.py --ticker IWM
python scripts/analysis/phase3_orb_strategies.py --ticker IWM
python scripts/analysis/phase4_setup_discovery.py --ticker IWM
python scripts/analysis/phase5_dimensions.py --ticker IWM
python scripts/analysis/phase6_playbook.py --ticker IWM
python scripts/analysis/phase7_feedback_loop.py --ticker IWM

# Run tests
python -m pytest tests/ -v
```

## Column Naming Convention

### Entry Columns (in signals CSV)
- `entry_*`: Values at signal entry time
- `entry_broke_*`: Binary flags (1 or 0)
- `entry_at_*`: At-level flags (1 or 0)
- `entry_vs_*_pct`: Percentage distance from level
- `entry_orb_*_trend`: Trend direction (1, 0, -1)
- `entry_order_block_*`: Order block data

### Historical Level Columns
- `Prev_*`: Previous period data
- `Broke_*`: Breakout/breakdown flags
- `At_*`: At-level flags
- `*_Pct`: Percentage distance

### ORB Columns
- `ORB_5m_*`: 5-minute ORB data
- `ORB_15m_*`: 15-minute ORB data
- `ORB_30m_*`: 30-minute ORB data

---

## Phase Analysis System (7-Phase Statistical Foundation)

The Phase system provides probability-calibrated statistics for every pattern, indicator, and setup.

### Phase Reports (in `reports/`)
| Phase | Report | What It Provides |
|-------|--------|-----------------|
| 1 | `phase1_strat_mining_{ticker}.md` | Transition probabilities, 3-bar sequences, consecutive move analysis, FTFC alignment |
| 2 | `phase2_indicator_confirmation_{ticker}.md` | Indicator predictive lift, reversal early warning scorecard |
| 3 | `phase3_orb_strategies_{ticker}.md` | ORB breakout/failure/range-bound strategy backtests |
| 4 | `phase4_setup_discovery_{ticker}.md` | High-probability indicator combos (65%+ WR, 30+ trades), decision tree paths |
| 5 | `phase5_dimensions_{ticker}.md` | Regime analysis, time-of-day, day-of-week, options P/L, walk-forward validation |
| 6 | `phase6_playbook_{ticker}.md` | 12 actionable decision cards per ticker with entry/exit rules |
| 7 | `phase7_feedback_loop.md` | Trade tracker template, weekly review, pre-market regime check |

### Cross-Ticker Reports
- `phase1_strat_mining_combined.md` — Divergence analysis across IWM/SPY/QQQ
- `phase4_setup_comparison.md` — Universal vs. ticker-specific setups
- `phase5d_cross_ticker.md` — Correlation and confirmation effects
- `phase6_playbook_combined.md` — All 36 cards + quick reference

### Key Backtest Results (10-Year: 2015-2025)

| Ticker | Config | Trades | Win Rate | Sharpe | Expectancy |
|--------|--------|--------|----------|--------|------------|
| IWM | Base | 13,674 | 41.2% | 0.30 | +0.002% |
| IWM | +Strat/FTFC/ORB | 11,664 | 42.1% | 0.51 | +0.004% |
| **IWM** | **1m+15m combo** | **492** | **57.1%** | **9.31** | **+0.078%** |
| SPY | +Strat/FTFC/ORB | 11,359 | 43.6% | 0.18 | +0.001% |
| **SPY** | **1m+30m combo** | **9,528** | **54.5%** | **5.54** | **+0.036%** |
| QQQ | +Strat/FTFC/ORB | 11,402 | 39.9% | -0.06 | -0.000% |
| **QQQ** | **1m+15m combo** | **9,607** | **52.0%** | **6.67** | **+0.055%** |

### Playbook Cards Quick Reference (12 per ticker)
1. Bullish Continuation (2U-2U-2U) — CALL
2. Bearish Continuation (2D-2D-2D) — PUT
3. Bullish Reversal (2D-1-2U) — CALL
4. Bearish Reversal (2U-1-2D) — PUT
5. Outside Bar Breakout (Type 3) — Direction of close
6. ORB Breakout Bullish — CALL
7. ORB Breakout Bearish — PUT
8. ORB Failure / Mean Reversion — Fade the false breakout
9. Support Bounce — CALL at prev day/week low
10. Resistance Rejection — PUT at prev day/week high
11. Order Block Test — Direction of bounce
12. FTFC Maximum Conviction — Highest position size

### Ticker Personalities
- **IWM**: Volatile mean reverter. Reversals work best. Best combo: 1m+15m (Sharpe 9.31)
- **SPY**: Steady grinder. VWAP is #1 indicator. Best combo: 1m+30m (Sharpe 5.54)
- **QQQ**: Momentum runner. CALLs only 37.6% WR (be selective). Best combo: 1m+15m (Sharpe 6.67)

---

## TradingView PineScript Indicators

Existing indicators in `tradingview-pine-scripts/`:

| Indicator | Maturity | What It Does |
|-----------|----------|-------------|
| **session-levels-trends** | 90% | Previous D/W/M levels, ORB overlay, Supertrend, gap zones |
| **orb-30** | 80% | Multi-symbol ORB breakout scanner with aggregated alerts |
| **iwm-bsvp** | 85% | Volume pressure analysis, divergence detection, entry scoring |
| **iwm-scalping** | 75% | 27-lane multi-indicator dashboard for 0DTE scalping |

### PineScript Enhancement Priorities (from Phase analysis)
1. **Strat Candle Classifier + FTFC Overlay** — Port strat.py to Pine (biggest edge: +70-195% Sharpe)
2. **Phase 6 Playbook Alerts** — Encode 12 cards as Pine conditions with signal score
3. **Multi-TF Trend Filter** — 15m EMA20 direction overlay (the 1m+15m Sharpe 9.31 edge)
4. **Reversal Early Warning Scorecard** — Phase 2 weighted checklist as Pine panel
5. **Regime-Aware Parameters** — Auto-adjust targets/stops based on ATR regime

---

## Legacy Python Scripts

| Script | Purpose |
|--------|---------|
| `trading_analysis.py` | Primary: 195+ features, ML feature importance, signal generation |
| `trade_analysis_pipeline.py` | Validation: Matches real trades against historical patterns, tests 100+ criteria |
| `morning_checklist_analysis.ipynb` | Daily: Scores current conditions against your patterns |
| `iwm_trading_alerts.py` | Real-time: Contrarian alerts with audio notifications |

---

## Documentation Files

- [trade_analysis_overview.md](trade_analysis_overview.md) — Complete system overview + glossary
- [trade_SIGNAL_GENERATION_METHODOLOGY.md](trade_SIGNAL_GENERATION_METHODOLOGY.md) — Signal logic analysis vs. actual trades
- [TRADE_ANALYSIS_REPORT_BUILD_PROCESS.md](TRADE_ANALYSIS_REPORT_BUILD_PROCESS.md) — Pipeline build process
- [INVESTMENT_MODELS_SUMMARY.md](INVESTMENT_MODELS_SUMMARY.md) — All 5 investment models with Phase analysis
- [BACKTEST_RESULTS.md](BACKTEST_RESULTS.md) — 10-year backtest results across all tickers
- [MODEL_SUMMARY.md](MODEL_SUMMARY.md) — Model architecture summary
- [HISTORICAL_LEVELS_FEATURE.md](HISTORICAL_LEVELS_FEATURE.md) — Historical levels documentation
- [ORB_AND_ORDER_BLOCKS_FEATURE.md](ORB_AND_ORDER_BLOCKS_FEATURE.md) — ORB/Order Block documentation
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) — This file

## Tips

1. **Start Small**: Use `-months 2` for faster iterations
2. **Combine Features**: Look for confluence (multiple confirmations)
3. **Use Playbook Cards**: Reference Phase 6 cards for structured entries
4. **Check Higher TF**: The 15m EMA20 trend filter is the single biggest edge
5. **Respect FTFC**: Never trade against full timeframe continuity
6. **Know Your Ticker**: IWM = mean reversion, SPY = balanced, QQQ = momentum
7. **Validate Live**: Use Phase 7 tracker to compare real vs. backtest performance
8. **Update PineScript Constants**: Re-run Phase analysis quarterly, update Pine thresholds

## Recommended Workflow

1. **Monthly**: Re-run Phase 1-5 to update probabilities and regime parameters
2. **Weekly**: Phase 7B weekly review against your trade journal
3. **Daily (Pre-Market)**: `morning_checklist_analysis.ipynb` + Phase 7C regime check
4. **Live Trading**: PineScript indicators (with Phase-calibrated thresholds)
5. **Post-Trade**: Log in Phase 7A tracker, run `trade_analysis_pipeline.py`
6. **Quarterly**: Phase 5G walk-forward validation to check pattern stability
