# Phase 7 — Trader's Playbook (the "where it works" guide)

**Date:** 2026-05-24
**Last updated:** 2026-05-25 — per-ticker model results landed; IWM is the new top priority
**Purpose:** Translate the Phase 7 audit data into specific, actionable rules a trader can use tomorrow.

---

## ⭐ NEW HIGHEST-PRIORITY FINDING (per `P7_PER_TICKER_COMPARISON.md`):

**IWM with LightGBM at 30m TF: Sharpe +3.24 across 5 walk-forward folds, 59% win rate, +15.8 bps/day after costs.**

This is the single strongest signal in the entire 6-phase audit. Per-ticker training revealed it (was hidden by pooling). **Deploy IWM 30m LGBM first** — the cell-level trades below are still valid as confirmation signals.

Secondary: IWM 15m LGBM Sharpe +3.15. QQQ 15m LGBM +2.48. SPY weakest at short TFs.

**Avoid** ALL linear models on SPY/QQQ at 15-30m horizons — they have negative Sharpe.

---

---

## How to read the dealer-positioning regime in real-time

Before each session, check three numbers from `gamma_levels_eod` for the previous trading day:

1. **VIX close** → categorize: LOW (<14.65), MID (14.65-19.40), HIGH (≥19.40)
2. **Total GEX** for the ticker → tercile per the 10-year distribution:
   - SPY: LOW (<-$26M), MID, HIGH (>+$31M)
   - IWM: LOW (<-$10.5M), MID, HIGH (>-$3M)
   - QQQ: LOW (<-$8.8M), MID, HIGH (>+$2.8M)
3. **Total VEX** for the ticker → tercile:
   - SPY: LOW (<-$2.9B), MID, HIGH (>-$1.35B)
   - IWM: LOW (<-$390M), MID, HIGH (>-$118M)
   - QQQ: LOW (<-$1.36B), MID, HIGH (>-$220M)

Combine GEX × VEX into one of 9 dealer-regime labels: `GEX_X_VEX_Y`.

### What the dealer regimes FEEL like in the market

| regime | what's happening | typical market action |
|---|---|---|
| GEX_HIGH × VEX_LOW | Dealers very long gamma + short vega | **PINNING regime** — price gets locked, low realized vol, options-sellers winning. Range-bound day. |
| GEX_HIGH × VEX_MID | Long gamma, neutral vega | Pinning but not extreme — small range, slow drift |
| GEX_HIGH × VEX_HIGH | Long gamma, long vega | Rare — usually after big vol expansion + dealers got hedged. **Reversal-prone** |
| GEX_MID × VEX_LOW | Neutral gamma, short vega | Quiet trending — small moves but persistent direction |
| GEX_MID × VEX_MID | Balanced | Normal day — everything matters equally |
| GEX_MID × VEX_HIGH | Neutral gamma, long vega | Vol expansion brewing — choppy |
| GEX_LOW × VEX_LOW | Short gamma + short vega | **AMPLIFY regime** — moves accelerate, no pinning. Trend-friendly. |
| GEX_LOW × VEX_MID | Short gamma | Trending with vol slowly expanding |
| GEX_LOW × VEX_HIGH | Short gamma + long vega | **VOL BREAKOUT regime** — sharp directional moves, volatile |

---

## The 7 highest-conviction trades from the audit (60m TF)

### 1. SPY `322_bull_continuation` × `GEX_MID × VEX_LOW`
- **Setup**: SPY at 60m makes a 3-bar pattern outside→2up→2up, AND today is in MID-GEX × LOW-VEX dealer regime
- **Hit rate**: 80% on N=30 events over 10 years
- **Expected move**: +20 bps over next 5 bars (5 hours)
- **Trade**: Long SPY/SPY-call after the 322 confirms. Target +0.20%. Stop at the trigger_low of the 322.
- **Why it works**: Dealers neutral on price + quiet on vol → continuation isn't fought by dealer hedging
- **N=30 is small** — bootstrap CI is 63-93%, so worst case 63% hit. Still tradeable.

### 2. SPY `322_bull_continuation` × `GEX_MID × VEX_MID`
- **Hit rate**: 77.8% on N=45
- **Expected move**: +30 bps over 5 hours
- Same pattern, different dealer state. Even larger sample.

### 3. IWM `11_inside_compression` × `GEX_HIGH × VEX_MID`
- **Setup**: IWM makes 2 consecutive inside bars at 60m AND dealers are heavily long gamma
- **Hit rate**: 73.3% on N=30
- **Expected move**: +47 bps over 5 hours (large!)
- **Why**: Inside bars in pinning regime → when they finally break, the break is sharp because vol-suppression releases
- **Trade**: Wait for break, take direction of break

### 4. QQQ `322_bull_continuation` × `GEX_HIGH × VEX_LOW`
- **Hit rate**: 71.7% on N=53
- **Expected move**: +20 bps
- The pinning regime + 322 bull combo works on QQQ too.

### 5. QQQ `212_bear_continuation` × `GEX_HIGH × VEX_HIGH`
- **Setup**: QQQ makes 2up→1→2down→2down at 60m AND dealers are long gamma + long vega
- **Hit rate**: 70% on N=30 (going DOWN)
- **Expected move**: +14 bps in bear direction (so short)
- **Why**: Long-vega dealers ALLOW the down move because they want vol; not actively hedging against it.

### 6. **FADE THIS**: QQQ `clean_2d_bear` × `GEX_LOW × VEX_MID`
- **Setup**: QQQ makes a clean 2D bear bar at 60m in short-gamma + mid-vega regime
- **Hit rate**: 33.3% on N=39 (i.e. price went UP 67% of the time after a bear bar)
- **Expected move**: -61 bps in bear direction (so +61 bps if you fade the bear and go LONG)
- **Why**: Short-gamma regime amplifies moves, but the 2D bear bar was a flush — exhausted sellers, dealers chase to rebalance.

### 7. **HIGHEST SINGLE EDGE**: QQQ `322_bull_continuation` × HIGH-VIX (any GEX/VEX)
- **Hit rate**: 65.7% on N=99
- **Expected move**: +35 bps over 5 hours
- The "buy panic" trade — when VIX is high but a bullish 3-bar pattern fires, very strong continuation.

---

## The 3 things to AVOID (anti-predictive cells)

### Avoid 1: IWM `212_bear_reversal` × `GEX_HIGH × VEX_LOW`
- N=68, hit_pct = 39.7% (anti)
- If IWM makes a 212 bear reversal in pinning regime, **don't trade the reversal** — the pinning regime kills it 60% of the time.

### Avoid 2: IWM `clean_2u_bull` × `GEX_HIGH × VEX_HIGH`
- N=43, hit_pct = 39.5% (anti)
- After a clean 2U bull in long-gamma + long-vega regime, IWM reverses 60% of the time.

### Avoid 3: SPY/QQQ `322_bull_continuation` UNCONDITIONALLY
- The pooled finding from P3 says this signal is anti-predictive at 5d horizon
- P7 shows it works ONLY in specific dealer regimes (Trade 1, 2, 4 above)
- **Production rule**: Only fire 322_bull_continuation if dealer_regime ∈ {GEX_MID_VEX_LOW, GEX_MID_VEX_MID, GEX_HIGH_VEX_LOW}

---

## How to USE this in the existing signal_monitor

### Augment mode (recommended first step)
For every existing strat alert that signal_monitor fires:
1. Look up today's dealer regime for that ticker (joining `gamma_levels_eod` for D-1)
2. Check if (alert_combo × dealer_regime) is in the "7 trades" table above:
   - YES → fire with **"HIGH-CONVICTION"** label + the historical hit_pct from the audit
   - YES with anti-edge → **suppress** the alert (or fire with "AVOID" label)
   - NO (not in table) → fire as normal (no special handling)

This is **~50 lines of code** in `gcp/signal_monitor.py`. Conservative — doesn't change which alerts fire, just labels them with audit-derived confidence.

### Filter mode (more aggressive)
Modify `lib/strategies/gamma_proximity.py` and the strat-combo evaluator to **only fire** when the (combo × dealer_regime) cell has audit hit_pct ≥ 60%. This drops alert volume by ~80% but raises per-alert quality.

### Model-driven mode (Phase 7c — the BIG play)
Deploy the 60m PLS-10 model as a daily prediction service:
1. After market close, run inference for each of SPY/IWM/QQQ for the next session's first ~7 bars
2. Surface predictions in the premarket brief
3. Optionally, auto-fire trades if `predicted_return > +1σ` AND `dealer_regime` matches a top-7 cell

---

## The "tomorrow morning" routine

Before the market opens tomorrow:

1. **Check the dealer regime** for SPY / IWM / QQQ:
   ```sql
   SELECT ticker, total_gex, total_vex, vix_close
   FROM strat_features_60m
   WHERE bar_date = (SELECT max(bar_date) FROM strat_features_60m WHERE ticker='SPY')
   ORDER BY ticker;
   ```
   Map to one of 9 GEX×VEX labels per ticker.

2. **Look up which trades are armed**:
   - SPY in `GEX_MID_VEX_LOW`? Watch for 322_bull_continuation pattern → high-conviction long
   - IWM in `GEX_HIGH_VEX_MID`? Watch for 11_inside_compression → big breakout coming
   - QQQ in HIGH-VIX? Watch for 322_bull_continuation → buy-the-dip trade

3. **Set price alerts on the strat trigger levels** for the watched patterns.

4. **During the session**: when a 60m bar closes that matches a trade in the playbook, take the position with the audit-defined target/stop.

5. **Track outcomes** — if you take 30+ trades on this playbook over a quarter, you'll have enough N to validate the audit's hit_pct estimates against your live data.

---

## Summary in one sentence

**The signal isn't a single "buy or sell" indicator — it's a 9-cell dealer-regime grid where specific strat patterns have 70-80% hit rates in 3-4 specific cells, and ~40% (anti-edge) in 3-4 others. The trader's job is to know which cell today is in, and only act on patterns whose (combo × cell) historically wins.**

That's where it works. The audit narrowed your trade universe from "any strat alert" (50% hit, breakeven) to "this specific combo in this specific regime" (70-80% hit, tradeable).
