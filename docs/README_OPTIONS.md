# Options Data Fetching & Analysis Scripts

This directory contains scripts for two **distinct** use cases with different data requirements.

## 📊 Two Trading Strategies, Two Approaches

### 1. 🎯 ETF Scalping (Intraday)
**Tickers**: IWM, SPY, QQQ, SPX  
**Strategy**: Same-day entry/exit, high frequency  
**Data Need**: **Intraday snapshots** (9 times per day)

### 2. 📈 Earnings Plays (Multi-day)
**Tickers**: Individual stocks (AAPL, MSFT, MDB, etc.)  
**Strategy**: Multi-day holds around earnings (Day 0-5)  
**Data Need**: **Daily EOD snapshots** (once per day)

---

## 🚀 ETF Scalping Scripts

### `fetch_etf_options_intraday.py`

Captures options chains for ETFs **9 times per day** to track intraday price movements.

**Capture Schedule (ET):**
- `9:30 AM` - Market open (high volatility)
- `9:35 AM` - 5 mins after open
- `9:40 AM` - 10 mins after open
- `10:00 AM` - Volatility settling
- `11:30 AM` - Mid-morning
- `1:00 PM` - Post-lunch
- `2:30 PM` - Afternoon session
- `3:30 PM` - Power hour
- `4:05 PM` - After close (EOD)

**Why 9 snapshots?**
- First 3 capture critical opening volatility (9:30-9:40)
- Remaining 6 track key intraday periods
- Captures ~90% of price action for scalping analysis
- Only ~24 MB/day storage (4 ETFs × 6 MB each)

**Usage:**
```bash
# Auto-capture (checks if it's a scheduled time)
python fetch_etf_options_intraday.py

# Force capture now
python fetch_etf_options_intraday.py --force

# Analyze a completed scalping trade
python fetch_etf_options_intraday.py --analyze IWM 220 C "2025-10-11 09:35" "2025-10-11 14:00"
```

---

## 📈 Earnings Strategy Scripts

### `fetch_earnings_options_daily.py`

Captures options chains **once daily** at market close for earnings strategy stocks.

**Schedule:** Once per day at 4:15 PM ET

**Usage:**
```bash
# Auto-load tickers from strategy CSV files
python fetch_earnings_options_daily.py

# Fetch specific tickers
python fetch_earnings_options_daily.py AAPL MSFT MDB
```

---

### `match_earnings_strategy.py`

Matches strategy CSV records with live options data to calculate P/L for **earnings plays**.

**Usage:**
```bash
# Test with first 5 long calls
python match_earnings_strategy.py --strategy longcalls --limit 5

# Process all covered calls
python match_earnings_strategy.py --strategy coveredcalls
```

---

## 📋 Quick Reference

| Use Case | Frequency | Script | Data Size | Purpose |
|----------|-----------|--------|-----------|---------|
| **ETF Scalping** | 9x daily | `fetch_etf_options_intraday.py` | ~24 MB/day | Capture intraday highs/lows |
| **Earnings Plays** | 1x daily | `fetch_earnings_options_daily.py` | ~5 MB/day | Track multi-day positions |

**Last Updated:** 2025-10-11
