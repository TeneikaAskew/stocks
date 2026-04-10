# Pine Script Upgrades — Backtest-Driven Enhancements

## Context

Your 5 TradingView Pine scripts work well individually, but the backtest reports (10+ years, IWM/SPY/QQQ) reveal a critical insight: **Strat patterns alone win ~47% — indicator confirmation adds 5-21 percentage points to win rate**. Your scripts are currently missing the exact indicator combinations that the backtests proved most effective. The goal is to make each script catch winning setups **earlier and with higher confidence**.

**Guiding principle**: Every addition below is backed by specific backtest data with sample sizes (1,000+ trades minimum for high-confidence findings). No speculative features — only proven indicators with measured win rate lift.

### The 5 Proven Confirmation Indicators (from `lib/signals.py`)
| Indicator | Win Rate Lift | Status Across Scripts |
|-----------|--------------|----------------------|
| Price vs EMA9 | **+20pp** | Only in iwm-scalping |
| RSI extremes (<30 / >70) | **+12-15pp** | Only in iwm-scalping (as lane) |
| Price vs EMA20 | **+10pp** | Only in iwm-scalping |
| StochRSI extremes (<20 / >80) | **+9-10pp** | Only in iwm-scalping (as lane) |
| OBV / RVOL trend | **+2-3pp** | RVOL in iwm-scalping only |

The scalping script has the indicators but no composite score. The other 4 scripts are missing most of these entirely.

---

## Upgrade Plan (ordered by impact / complexity)

### 1. IWM-Scalping — Add Composite Score + 30m Timeframe
**File**: `tradingview-pine-scripts/iwm-scalping`

Currently 24 lanes of dots with **zero signal generation** — the trader manually counts dots. Upgrades:

- **Composite CALL/PUT score** (count active lanes, display as number, alert when score >= 7 CALL or >= 6 PUT). This is the single biggest UX improvement — turns passive display into active signals
- **Add 30-minute timeframe lanes** (EMA9>EMA20 on 30m, 30m breakout direction). The 1m+30m combo has **Sharpe 11.05** vs ~8.5 for current 1m+5m
- **Add OBV lane** (+2-3pp lift, easy win — `ta.obv` vs its 20-SMA)
- **Add Strat pattern lane** (detect 2-1-2 reversals — IWM's best pattern at 66%+ WR when confirmed)
- **Morning momentum weighting** — 9:30-10:30 gets +2 bonus points in score (backtest peak hours)

### 2. IWM-BSVP — Add the Top 3 Missing Indicators
**File**: `tradingview-pine-scripts/iwm-bsvp`

Entry quality score (lines 228-248) is purely volume-based. Missing the three strongest indicators:

- **EMA9/EMA20 cross** into entry quality formula (+20pp — strongest single indicator). Add as 5th scoring factor (20pts) alongside existing trend/momentum/divergence/volume
- **RSI extreme zones** — flag "EXTREME SETUP" when RSI <30 or >70 aligns with volume pressure direction (+12-15pp). RSI extremes often precede VPO shifts by 1-3 bars = **earlier signal**
- **StochRSI leading signal** — StochRSI K/D cross when oversold fires BEFORE the VPO crossover by 1-5 bars. New "early warning" alert pathway (+9-10pp)
- **Time-of-day quality multiplier** — morning prime (9:30-10:30) = 1.2x, afternoon = 0.7x
- **Volatility regime label** — ATR vs 50-SMA(ATR): high/normal/low in info table

### 3. Strat Assistant — Port to v6 + Add Indicator Grades
**File**: `tradingview-pine-scripts/strat-assistant`

Currently **Pine v4** (deprecated). Patterns fire without quality context.

- **Port to Pine v6** (prerequisite) — `study()`→`indicator()`, `security()`→`request.security()`, typed inputs, etc. Mechanical but necessary
- **Indicator confirmation grade per pattern** — when a combo fires (e.g., 212 reversal), score it A/B/C based on RSI zone + EMA9 position + StochRSI extreme + EMA cross + RVOL. Display grade next to pattern flag
- **Rich tooltips** (v6 feature) — on hover show: pattern name, grade breakdown, backtest win rate, suggested stop/target, volatility regime
- **High-probability IWM alert conditions** — the two best setups from backtests:
  - Below EMA20 + EMA9>EMA20 + StochRSI>80 → 66.2% WR (1,382 trades)
  - Above EMA9 + Below EMA20 + StochRSI<20 → 65.3% WR (2,429 trades)

### 4. Session Levels + Trends — Indicator Confirmation at Levels
**File**: `tradingview-pine-scripts/session-levels-trends`

Session levels are static — they show WHERE but not WHEN. Upgrades:

- **RSI/StochRSI confirmation at levels** — when price is within 0.3% of PDH/PDL/PWH/PWL, check RSI+StochRSI. Display "Oversold at Support" (green) or "Overbought at Resistance" (red) dots (+15-20pp on level trades)
- **ORB quality score (0-4)** — ORB range vs ATR, Supertrend alignment, RSI positioning, RVOL at break
- **ORB failure detection** — if price returns inside ORB within 3-5 bars after breakout, label "ORB FAIL" (reversal trade signal)
- **Adaptive Supertrend** — multiply ATR factor by 1.3x in high-vol, 0.7x in low-vol (reduces whipsaws)

### 5. ORB-30 — Contextual Filtering
**File**: `tradingview-pine-scripts/orb-30`

Currently fires alerts for ALL breakouts regardless of quality. Upgrades:

- **Quality context in alerts** — ATR regime + RSI + ORB tightness. Alert becomes: "ORB Buy: SPY [Quality: A, Vol: High, RSI: 62]"
- **ORB failure detection** — track if price returns inside ORB within 5 bars, fire reversal alert
- **Time-of-day cutoff** — suppress alerts after 14:00 ET (afternoon win rate drops 2-3pp)

---

## Unified Signal Grading (all scripts)

| Grade | Indicators Confirmed | Expected WR | Color |
|-------|---------------------|-------------|-------|
| A+ | 5/5 + Strat + morning | 70%+ | Bright green |
| A | 4-5/5 | 62-70% | Green |
| B | 2-3/5 | 52-58% | Yellow |
| C | 0-1/5 | 45-50% | Gray |

---

## File Strategy — v2 Copies (originals preserved)

All upgrades go into new v2 files. Original scripts remain untouched for side-by-side comparison.

| Original File | v2 File |
|--------------|---------|
| `tradingview-pine-scripts/iwm-scalping` | `tradingview-pine-scripts/iwm-scalping-v2` |
| `tradingview-pine-scripts/iwm-bsvp` | `tradingview-pine-scripts/iwm-bsvp-v2` |
| `tradingview-pine-scripts/strat-assistant` | `tradingview-pine-scripts/strat-assistant-v2` |
| `tradingview-pine-scripts/session-levels-trends` | `tradingview-pine-scripts/session-levels-trends-v2` |
| `tradingview-pine-scripts/orb-30` | `tradingview-pine-scripts/orb-30-v2` |

Each v2 file starts as a copy of the original, then gets the upgrades applied. The `.md` documentation files will be updated to reference both versions.

## Step 0: Save This Plan
Save this document as `tradingview-pine-scripts/UPGRADE-PLAN.md` in the project for reference.

## Implementation Order

| # | Script | Upgrade | Impact | Complexity |
|---|--------|---------|--------|------------|
| 1 | iwm-scalping-v2 | Composite score + alerts | Turns passive → active | Medium |
| 2 | iwm-scalping-v2 | 30m timeframe lanes + OBV + Strat + morning weight | Sharpe 8.5 → 11.0 | Low |
| 3 | iwm-bsvp-v2 | EMA9/20 into entry quality | +20pp lift | Low |
| 4 | iwm-bsvp-v2 | RSI extremes + StochRSI early warning + time/vol | +12-15pp + earlier signals | Low-Med |
| 5 | strat-assistant-v2 | Port to Pine v6 | Unlocks all upgrades | Medium-High |
| 6 | strat-assistant-v2 | Indicator grades + tooltips + alerts | +15-20pp on patterns | High |
| 7 | session-levels-trends-v2 | RSI/StochRSI at levels + adaptive Supertrend | +15-20pp on level trades | Medium |
| 8 | session-levels-trends-v2 | ORB quality + failure detection | +8-12pp on ORBs | Medium |
| 9 | orb-30-v2 | Quality context + failure + time filter | +8-12pp on alerts | Medium |

## Verification
- Each v2 script will be syntactically valid Pine Script (v6 for all except strat-assistant which ports from v4→v6)
- Original scripts remain unchanged — user can load both v1 and v2 side-by-side in TradingView
- Compare signal output between v1/v2 to confirm new grades and scores appear
- Run `make test` to ensure no Python backend regressions from any shared logic references
