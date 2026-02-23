# Phase 6: The Beginner's Playbook — All Tickers

Generated: 2026-02-22 23:45:09

12 decision cards per ticker, each with specific entry/exit rules.

## Quick Reference: Which Ticker Should I Trade Right Now?

**Decision Tree:**

1. Check daily Strat for all 3 tickers
2. If IWM shows 2-1-2 reversal setup -> **IWM** (strongest mean reversion)
3. If SPY has cleanest FTFC alignment -> **SPY** (strongest trend following)
4. If QQQ has score 6+ signal -> **QQQ** (highest per-trade return at 6+)
5. If all 3 tickers signal the same direction -> **Highest conviction day**
6. If tickers conflict -> **Reduce size or sit out**

**Ticker Personality Summary:**

| Trait | IWM | SPY | QQQ |
|-------|-----|-----|-----|
| Character | Volatile Mean Reverter | Steady Grinder | Momentum Runner |
| Best For | Reversal setups | Trend following | High-conviction momentum |
| Base WR | ~42% | ~43.5% | ~40% |
| PUT lean | Strong (72%) | Balanced (50/50) | Moderate |
| Best combo | 1m+15m | 1m+30m | 1m+15m |
| Target width | Widest | Tightest | Medium |
| Stop speed | 8 min | Moderate | 7 min (fastest) |
| Risk level | Medium | Low | High |


---


---

### IWM CARD 1: Bullish Continuation (2U-2U-2U)
**WHAT YOU SEE ON THE CHART:**
  * Daily bar is 2U (higher high, higher low)
  * 15m bar is 2U
  * 1m shows: 2U -> 2U -> 2U (three consecutive bullish bars)

**WHAT TO CHECK:**
  - [ ] RSI between 40-65 (not overbought yet)
  - [ ] Price above VWAP
  - [ ] Price above EMA9
  - [ ] ORB 30m trend is bullish
  - [ ] EMA9 > EMA20 (bullish cross)

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=91,353)
  - Historical win rate: 47.9%
  - Avg return: -0.1 bps
  - Target: +0.30%
  - Stop: -0.15%
  - Expected hold: 10-15 min
  - Avg MFE: +19.9 bps
  - Avg MAE: -20.8 bps

**REVERSAL WARNING SIGNS (exit early):**
  - RSI crosses above 75 -> take profit
  - 1m bar prints 2D -> tighten stop to breakeven
  - RVOL drops below 0.8 -> momentum fading
  - Price hits prev day/week high -> resistance

**IWM-SPECIFIC NOTES:**
  - IWM mean-reverts more than SPY/QQQ — continuation is less reliable
  - If RSI > 70, reversal risk is ELEVATED — IWM reverses hard
  - Best combo: 1m+15m (Sharpe 9.31)
  - IWM has widest targets but also widest stops


---

### IWM CARD 2: Bearish Continuation (2D-2D-2D)
**WHAT YOU SEE ON THE CHART:**
  * Daily bar is 2D (lower high, lower low)
  * 15m bar is 2D
  * 1m shows: 2D -> 2D -> 2D (three consecutive bearish bars)

**WHAT TO CHECK:**
  - [ ] RSI between 35-60 (not oversold yet)
  - [ ] Price below VWAP
  - [ ] Price below EMA9
  - [ ] ORB 30m trend is bearish
  - [ ] EMA9 < EMA20 (bearish cross)

**IF ALL CONFIRMED -> PUT ENTRY**
  - Confidence: High (n=87,545)
  - Historical win rate: 47.4%
  - Avg return: -0.1 bps
  - Target: +0.38%
  - Stop: -0.20%
  - Expected hold: 10-15 min
  - Avg MFE: +21.8 bps
  - Avg MAE: -22.0 bps

**REVERSAL WARNING SIGNS (exit early):**
  - RSI crosses below 25 -> take profit
  - 1m bar prints 2U -> tighten stop to breakeven
  - RVOL drops below 0.8 -> selling pressure fading
  - Price hits prev day/week low -> support

**IWM-SPECIFIC NOTES:**
  - IWM PUTs win more often (43.4%) than CALLs (38.5%)
  - 72% of IWM trades are PUTs — natural bearish lean
  - Losers fail fast: 8 min median to stop
  - Highest per-trade return on target hits (+41 bps avg)


---

### IWM CARD 3: Bullish Reversal (2D-1-2U)
**WHAT YOU SEE ON THE CHART:**
  * Previous bars: 2D (bearish) -> 1 (inside bar compression)
  * Current bar: Breaking above the inside bar's high (2U)

**WHAT TO CHECK:**
  - [ ] RSI < 45 (was oversold from the 2D move)
  - [ ] Price at or near support level (prev day low, VWAP, order block)
  - [ ] StochRSI was oversold (< 20), now turning up
  - [ ] Volume confirming (RVOL > 1.0)

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=29,412)
  - Historical win rate: 47.8%
  - Avg return: +0.0 bps
  - Target: +0.30%
  - Stop: -0.15%
  - Expected hold: 10-15 min
  - Avg MFE: +18.3 bps
  - Avg MAE: -18.6 bps

**REVERSAL WARNING SIGNS (exit early):**
  - If breakout fails and price drops back inside the 1 bar -> exit immediately
  - RSI fails to cross above 50 -> weak reversal
  - No volume on breakout -> likely false breakout

**IWM-SPECIFIC NOTES:**
  - IWM is the BEST ticker for mean-reversion setups
  - 2-1-2 reversals work particularly well on small caps
  - Look for reversals at prev week lows


---

### IWM CARD 4: Bearish Reversal (2U-1-2D)
**WHAT YOU SEE ON THE CHART:**
  * Previous bars: 2U (bullish) -> 1 (inside bar compression)
  * Current bar: Breaking below the inside bar's low (2D)

**WHAT TO CHECK:**
  - [ ] RSI > 55 (was overbought from the 2U move)
  - [ ] Price at or near resistance (prev day high, upper BB)
  - [ ] StochRSI was overbought (> 80), now turning down
  - [ ] Volume confirming (RVOL > 1.0)

**IF ALL CONFIRMED -> PUT ENTRY**
  - Confidence: High (n=29,301)
  - Historical win rate: 47.4%
  - Avg return: +0.1 bps
  - Target: +0.38%
  - Stop: -0.20%
  - Expected hold: 10-15 min
  - Avg MFE: +19.2 bps
  - Avg MAE: -18.5 bps

**REVERSAL WARNING SIGNS (exit early):**
  - If price recovers back above inside bar's low -> exit immediately
  - RSI fails to cross below 50 -> weak reversal
  - No volume on breakdown -> likely false breakdown

**IWM-SPECIFIC NOTES:**
  - Bearish reversals strongest when RSI > 70 on IWM
  - Small caps overshoot — look for exhaustion at resistance


---

### IWM CARD 5: Outside Bar Breakout (Type 3 Bullish)
**WHAT YOU SEE ON THE CHART:**
  * Current bar is Type 3 (higher high AND lower low than prev bar)
  * Close is above previous bar's close (bullish resolution)

**WHAT TO CHECK:**
  - [ ] RSI between 40-60 (room to run)
  - [ ] Close in upper half of the bar's range
  - [ ] Volume above average (RVOL > 1.2)
  - [ ] Higher timeframe supports the direction

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=39,619)
  - Historical win rate: 47.6%
  - Avg return: +0.1 bps
  - Target: +0.30%
  - Stop: -0.15%
  - Expected hold: 10-15 min
  - Avg MFE: +21.3 bps
  - Avg MAE: -21.2 bps

**REVERSAL WARNING SIGNS (exit early):**
  - If next bar is Type 1 (inside) -> tighten stop
  - Price drops below midpoint of the 3 bar -> exit
  - Outside bars often exhaust moves -> be ready for reversal

**IWM-SPECIFIC NOTES:**
  - IWM has MORE Type 3 bars than SPY (higher volatility)
  - Outside bars on IWM often lead to sharp continuation


---

### IWM CARD 6: ORB Breakout — Bullish
**WHAT YOU SEE ON THE CHART:**
  * Price has broken above 30m Opening Range High
  * Current Strat bar confirms: 2U or 3

**WHAT TO CHECK:**
  - [ ] RSI not overbought (< 70)
  - [ ] Price above VWAP
  - [ ] EMA9 > EMA20
  - [ ] RVOL > 1.0 (volume confirming breakout)
  - [ ] At least 30 min after market open

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=147,071)
  - Historical win rate: 47.5%
  - Avg return: -0.0 bps
  - Target: +0.30%
  - Stop: -0.15%
  - Expected hold: 10-15 min
  - Avg MFE: +18.2 bps
  - Avg MAE: -18.2 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price returns inside ORB range -> failed breakout, exit
  - Declining volume on continuation -> fade risk
  - Approaching prev day/week high -> resistance ahead

**IWM-SPECIFIC NOTES:**
  - IWM has the WIDEST opening ranges — breakouts are more decisive
  - Once IWM breaks ORB, it tends to run further than SPY


---

### IWM CARD 7: ORB Breakout — Bearish
**WHAT YOU SEE ON THE CHART:**
  * Price has broken below 30m Opening Range Low
  * Current Strat bar confirms: 2D or 3

**WHAT TO CHECK:**
  - [ ] RSI not oversold (> 30)
  - [ ] Price below VWAP
  - [ ] EMA9 < EMA20
  - [ ] RVOL > 1.0
  - [ ] At least 30 min after market open

**IF ALL CONFIRMED -> PUT ENTRY**
  - Confidence: High (n=139,347)
  - Historical win rate: 48.0%
  - Avg return: -0.0 bps
  - Target: +0.38%
  - Stop: -0.20%
  - Expected hold: 10-15 min
  - Avg MFE: +22.2 bps
  - Avg MAE: -22.0 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price returns inside ORB range -> failed breakdown, exit
  - RSI reaching extreme oversold -> bounce risk
  - Approaching prev day/week low -> support ahead

**IWM-SPECIFIC NOTES:**
  - IWM bearish ORB breakdowns are particularly strong
  - Small caps sell off harder — bigger moves on downside


---

### IWM CARD 8: ORB Failure / Mean Reversion
**WHAT YOU SEE ON THE CHART:**
  * Price broke above ORB high, then FAILED and returned inside range
  * Current Strat shows 2D (confirming the failure)

**WHAT TO CHECK:**
  - [ ] RSI was elevated (> 60) at breakout
  - [ ] Volume declining on the failed breakout
  - [ ] Strat shows reversal (2D after 2U or 3)
  - [ ] VWAP is nearby (target)

**IF ALL CONFIRMED -> PUT ENTRY**
  - Confidence: High (n=6,675)
  - Historical win rate: 47.9%
  - Avg return: +0.2 bps
  - Target: +0.38%
  - Stop: -0.20%
  - Expected hold: 8-15 min
  - Avg MFE: +21.9 bps
  - Avg MAE: -20.5 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price re-breaks ORB high -> failure of the failure, exit
  - Price hits ORB mid and stalls -> take partial profit
  - RSI crosses below 40 -> full reversal, let it run

**IWM-SPECIFIC NOTES:**
  - IWM has fewer ORB failures but LARGER moves when they happen
  - Mean reversion works well after failed breakouts on IWM


---

### IWM CARD 9: Support Bounce (at Historical Level)
**WHAT YOU SEE ON THE CHART:**
  * Price is at previous day's low (support level)
  * Current bar is 2U (bouncing off support)

**WHAT TO CHECK:**
  - [ ] RSI < 40 (oversold at support)
  - [ ] StochRSI crossed above 20 (turning up)
  - [ ] Order block nearby (institutional interest)
  - [ ] Volume increasing on bounce

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=22,077)
  - Historical win rate: 47.4%
  - Avg return: -0.0 bps
  - Target: +0.30%
  - Stop: -0.15%
  - Expected hold: 10-15 min
  - Avg MFE: +17.6 bps
  - Avg MAE: -18.6 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price breaks below prev day low -> support failed, exit immediately
  - No follow-through (next bar is 1 or 2D) -> tighten stop
  - RSI fails to clear 50 -> weak bounce

**IWM-SPECIFIC NOTES:**
  - IWM bounces harder off support (mean reversion character)
  - Previous week low is a strong support level for IWM


---

### IWM CARD 10: Resistance Rejection (at Historical Level)
**WHAT YOU SEE ON THE CHART:**
  * Price is at previous day's high (resistance level)
  * Current bar is 2D (rejecting off resistance)

**WHAT TO CHECK:**
  - [ ] RSI > 60 (overbought at resistance)
  - [ ] StochRSI crossed below 80 (turning down)
  - [ ] Volume declining on approach to resistance
  - [ ] Bearish divergence (price higher, RSI lower)

**IF ALL CONFIRMED -> PUT ENTRY**
  - Confidence: High (n=26,193)
  - Historical win rate: 45.8%
  - Avg return: -0.0 bps
  - Target: +0.38%
  - Stop: -0.20%
  - Expected hold: 10-15 min
  - Avg MFE: +16.6 bps
  - Avg MAE: -15.8 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price breaks above prev day high -> resistance cleared, exit
  - No follow-through on rejection -> tighten stop
  - RSI fails to drop below 50 -> weak rejection

**IWM-SPECIFIC NOTES:**
  - IWM rejections at resistance tend to be sharp
  - Look for RSI > 70 at resistance for highest probability


---

### IWM CARD 11: Order Block Test (Institutional Zone)
**WHAT YOU SEE ON THE CHART:**
  * Price is testing an identified order block zone
  * Current bar is 2U (bouncing off the institutional zone)

**WHAT TO CHECK:**
  - [ ] Price is at order block high or low boundary
  - [ ] RSI between 35-55 (not extreme)
  - [ ] Volume increasing at the zone
  - [ ] Strat shows reversal or continuation with direction

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: Moderate (n=92)
  - Historical win rate: 34.8%
  - Avg return: +0.3 bps
  - Target: +0.30%
  - Stop: -0.15%
  - Expected hold: 10-15 min
  - Avg MFE: +15.7 bps
  - Avg MAE: -13.5 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price slices through the order block cleanly -> zone invalidated, exit
  - No bounce within 5 bars -> zone may be broken
  - Multiple tests weaken the zone -> less reliable each time

**IWM-SPECIFIC NOTES:**
  - Institutional order blocks may be less defined on IWM (small cap)
  - Use with other confirmation for better results


---

### IWM CARD 12: FTFC Maximum Conviction (All Aligned)
**WHAT YOU SEE ON THE CHART:**
  * ALL timeframes showing the same direction
  * EMAs bullish, ORB bullish, Strat 2U, RSI healthy
  * This is the STRONGEST possible setup

**WHAT TO CHECK:**
  - [ ] EMA9 > EMA20 (bullish cross)
  - [ ] ORB 30m trend is bullish
  - [ ] Current Strat bar is 2U
  - [ ] RSI between 40-65 (healthy, not overbought)
  - [ ] Price above VWAP
  - [ ] RVOL > 1.0 (volume confirms)

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=55,635)
  - Historical win rate: 47.6%
  - Avg return: -0.0 bps
  - Target: +0.30%
  - Stop: -0.15%
  - Expected hold: 10-15 min
  - Avg MFE: +17.5 bps
  - Avg MAE: -17.4 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Any single alignment breaks -> reduce size
  - RSI > 75 -> take profit regardless
  - RVOL drops below 0.8 -> conviction weakening
  - Losing money after 5 min in this setup -> something's wrong, exit

**IWM-SPECIFIC NOTES:**
  - When all aligned, IWM provides the BEST risk/reward
  - Sharpe 9.64 on 1m+15m — strongest of all tickers
  - But these setups are RARE (492 trades in 10 years)


---


---

### SPY CARD 1: Bullish Continuation (2U-2U-2U)
**WHAT YOU SEE ON THE CHART:**
  * Daily bar is 2U (higher high, higher low)
  * 15m bar is 2U
  * 1m shows: 2U -> 2U -> 2U (three consecutive bullish bars)

**WHAT TO CHECK:**
  - [ ] RSI between 40-65 (not overbought yet)
  - [ ] Price above VWAP
  - [ ] Price above EMA9
  - [ ] ORB 30m trend is bullish
  - [ ] EMA9 > EMA20 (bullish cross)

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=83,480)
  - Historical win rate: 46.9%
  - Avg return: -0.1 bps
  - Target: +0.15%
  - Stop: -0.10%
  - Expected hold: 12-18 min
  - Avg MFE: +13.9 bps
  - Avg MAE: -14.3 bps

**REVERSAL WARNING SIGNS (exit early):**
  - RSI crosses above 75 -> take profit
  - 1m bar prints 2D -> tighten stop to breakeven
  - RVOL drops below 0.8 -> momentum fading
  - Price hits prev day/week high -> resistance

**SPY-SPECIFIC NOTES:**
  - SPY trends more cleanly — continuation IS more likely than IWM
  - VWAP is the #1 indicator for SPY (institutional reference)
  - Most balanced CALL/PUT distribution of all tickers
  - Best combo: 1m+30m (Sharpe 5.54, WR 54.5%)


---

### SPY CARD 2: Bearish Continuation (2D-2D-2D)
**WHAT YOU SEE ON THE CHART:**
  * Daily bar is 2D (lower high, lower low)
  * 15m bar is 2D
  * 1m shows: 2D -> 2D -> 2D (three consecutive bearish bars)

**WHAT TO CHECK:**
  - [ ] RSI between 35-60 (not oversold yet)
  - [ ] Price below VWAP
  - [ ] Price below EMA9
  - [ ] ORB 30m trend is bearish
  - [ ] EMA9 < EMA20 (bearish cross)

**IF ALL CONFIRMED -> PUT ENTRY**
  - Confidence: High (n=77,799)
  - Historical win rate: 46.4%
  - Avg return: -0.1 bps
  - Target: +0.20%
  - Stop: -0.12%
  - Expected hold: 12-18 min
  - Avg MFE: +15.9 bps
  - Avg MAE: -15.9 bps

**REVERSAL WARNING SIGNS (exit early):**
  - RSI crosses below 25 -> take profit
  - 1m bar prints 2U -> tighten stop to breakeven
  - RVOL drops below 0.8 -> selling pressure fading
  - Price hits prev day/week low -> support

**SPY-SPECIFIC NOTES:**
  - SPY CALL WR (43.5%) nearly identical to PUT WR (43.7%)
  - SPY has tightest targets (+0.15% CALL, +0.20% PUT)
  - Time stops produce 55% win rate on SPY


---

### SPY CARD 3: Bullish Reversal (2D-1-2U)
**WHAT YOU SEE ON THE CHART:**
  * Previous bars: 2D (bearish) -> 1 (inside bar compression)
  * Current bar: Breaking above the inside bar's high (2U)

**WHAT TO CHECK:**
  - [ ] RSI < 45 (was oversold from the 2D move)
  - [ ] Price at or near support level (prev day low, VWAP, order block)
  - [ ] StochRSI was oversold (< 20), now turning up
  - [ ] Volume confirming (RVOL > 1.0)

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=31,012)
  - Historical win rate: 48.7%
  - Avg return: +0.0 bps
  - Target: +0.15%
  - Stop: -0.10%
  - Expected hold: 12-18 min
  - Avg MFE: +12.4 bps
  - Avg MAE: -12.6 bps

**REVERSAL WARNING SIGNS (exit early):**
  - If breakout fails and price drops back inside the 1 bar -> exit immediately
  - RSI fails to cross above 50 -> weak reversal
  - No volume on breakout -> likely false breakout

**SPY-SPECIFIC NOTES:**
  - SPY reversals are subtler — less dramatic than IWM
  - VWAP reclaim is the strongest confirmation for SPY reversals


---

### SPY CARD 4: Bearish Reversal (2U-1-2D)
**WHAT YOU SEE ON THE CHART:**
  * Previous bars: 2U (bullish) -> 1 (inside bar compression)
  * Current bar: Breaking below the inside bar's low (2D)

**WHAT TO CHECK:**
  - [ ] RSI > 55 (was overbought from the 2U move)
  - [ ] Price at or near resistance (prev day high, upper BB)
  - [ ] StochRSI was overbought (> 80), now turning down
  - [ ] Volume confirming (RVOL > 1.0)

**IF ALL CONFIRMED -> PUT ENTRY**
  - Confidence: High (n=31,131)
  - Historical win rate: 46.6%
  - Avg return: -0.0 bps
  - Target: +0.20%
  - Stop: -0.12%
  - Expected hold: 12-18 min
  - Avg MFE: +13.0 bps
  - Avg MAE: -12.8 bps

**REVERSAL WARNING SIGNS (exit early):**
  - If price recovers back above inside bar's low -> exit immediately
  - RSI fails to cross below 50 -> weak reversal
  - No volume on breakdown -> likely false breakdown

**SPY-SPECIFIC NOTES:**
  - SPY trend following works better than reversal
  - Be more selective with bearish reversals on SPY


---

### SPY CARD 5: Outside Bar Breakout (Type 3 Bullish)
**WHAT YOU SEE ON THE CHART:**
  * Current bar is Type 3 (higher high AND lower low than prev bar)
  * Close is above previous bar's close (bullish resolution)

**WHAT TO CHECK:**
  - [ ] RSI between 40-60 (room to run)
  - [ ] Close in upper half of the bar's range
  - [ ] Volume above average (RVOL > 1.2)
  - [ ] Higher timeframe supports the direction

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=40,493)
  - Historical win rate: 49.0%
  - Avg return: +0.1 bps
  - Target: +0.15%
  - Stop: -0.10%
  - Expected hold: 12-18 min
  - Avg MFE: +14.9 bps
  - Avg MAE: -15.0 bps

**REVERSAL WARNING SIGNS (exit early):**
  - If next bar is Type 1 (inside) -> tighten stop
  - Price drops below midpoint of the 3 bar -> exit
  - Outside bars often exhaust moves -> be ready for reversal

**SPY-SPECIFIC NOTES:**
  - SPY has FEWER Type 3 bars — they're rarer but meaningful
  - Outside bars on SPY often signal trend change


---

### SPY CARD 6: ORB Breakout — Bullish
**WHAT YOU SEE ON THE CHART:**
  * Price has broken above 30m Opening Range High
  * Current Strat bar confirms: 2U or 3

**WHAT TO CHECK:**
  - [ ] RSI not overbought (< 70)
  - [ ] Price above VWAP
  - [ ] EMA9 > EMA20
  - [ ] RVOL > 1.0 (volume confirming breakout)
  - [ ] At least 30 min after market open

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=165,852)
  - Historical win rate: 48.1%
  - Avg return: -0.0 bps
  - Target: +0.15%
  - Stop: -0.10%
  - Expected hold: 12-18 min
  - Avg MFE: +12.4 bps
  - Avg MAE: -12.3 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price returns inside ORB range -> failed breakout, exit
  - Declining volume on continuation -> fade risk
  - Approaching prev day/week high -> resistance ahead

**SPY-SPECIFIC NOTES:**
  - SPY has tightest opening ranges — false breakouts MORE common
  - Wait for confirmation before entering SPY ORB breakouts


---

### SPY CARD 7: ORB Breakout — Bearish
**WHAT YOU SEE ON THE CHART:**
  * Price has broken below 30m Opening Range Low
  * Current Strat bar confirms: 2D or 3

**WHAT TO CHECK:**
  - [ ] RSI not oversold (> 30)
  - [ ] Price below VWAP
  - [ ] EMA9 < EMA20
  - [ ] RVOL > 1.0
  - [ ] At least 30 min after market open

**IF ALL CONFIRMED -> PUT ENTRY**
  - Confidence: High (n=136,061)
  - Historical win rate: 47.9%
  - Avg return: -0.1 bps
  - Target: +0.20%
  - Stop: -0.12%
  - Expected hold: 12-18 min
  - Avg MFE: +17.3 bps
  - Avg MAE: -16.7 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price returns inside ORB range -> failed breakdown, exit
  - RSI reaching extreme oversold -> bounce risk
  - Approaching prev day/week low -> support ahead

**SPY-SPECIFIC NOTES:**
  - SPY bearish ORB breaks tend to be more measured
  - Tighter targets appropriate (-0.12% stop, +0.20% target)


---

### SPY CARD 8: ORB Failure / Mean Reversion
**WHAT YOU SEE ON THE CHART:**
  * Price broke above ORB high, then FAILED and returned inside range
  * Current Strat shows 2D (confirming the failure)

**WHAT TO CHECK:**
  - [ ] RSI was elevated (> 60) at breakout
  - [ ] Volume declining on the failed breakout
  - [ ] Strat shows reversal (2D after 2U or 3)
  - [ ] VWAP is nearby (target)

**IF ALL CONFIRMED -> PUT ENTRY**
  - Confidence: High (n=7,423)
  - Historical win rate: 45.4%
  - Avg return: -0.1 bps
  - Target: +0.20%
  - Stop: -0.12%
  - Expected hold: 8-15 min
  - Avg MFE: +14.3 bps
  - Avg MAE: -13.8 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price re-breaks ORB high -> failure of the failure, exit
  - Price hits ORB mid and stalls -> take partial profit
  - RSI crosses below 40 -> full reversal, let it run

**SPY-SPECIFIC NOTES:**
  - SPY may have the MOST ORB failures (tighter range)
  - SPY ORB failures are a good mean-reversion opportunity


---

### SPY CARD 9: Support Bounce (at Historical Level)
**WHAT YOU SEE ON THE CHART:**
  * Price is at previous day's low (support level)
  * Current bar is 2U (bouncing off support)

**WHAT TO CHECK:**
  - [ ] RSI < 40 (oversold at support)
  - [ ] StochRSI crossed above 20 (turning up)
  - [ ] Order block nearby (institutional interest)
  - [ ] Volume increasing on bounce

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=29,974)
  - Historical win rate: 47.7%
  - Avg return: +0.1 bps
  - Target: +0.15%
  - Stop: -0.10%
  - Expected hold: 12-18 min
  - Avg MFE: +12.6 bps
  - Avg MAE: -12.3 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price breaks below prev day low -> support failed, exit immediately
  - No follow-through (next bar is 1 or 2D) -> tighten stop
  - RSI fails to clear 50 -> weak bounce

**SPY-SPECIFIC NOTES:**
  - VWAP is the strongest support for SPY
  - Previous day close also acts as strong reference


---

### SPY CARD 10: Resistance Rejection (at Historical Level)
**WHAT YOU SEE ON THE CHART:**
  * Price is at previous day's high (resistance level)
  * Current bar is 2D (rejecting off resistance)

**WHAT TO CHECK:**
  - [ ] RSI > 60 (overbought at resistance)
  - [ ] StochRSI crossed below 80 (turning down)
  - [ ] Volume declining on approach to resistance
  - [ ] Bearish divergence (price higher, RSI lower)

**IF ALL CONFIRMED -> PUT ENTRY**
  - Confidence: High (n=46,153)
  - Historical win rate: 45.7%
  - Avg return: -0.0 bps
  - Target: +0.20%
  - Stop: -0.12%
  - Expected hold: 12-18 min
  - Avg MFE: +10.3 bps
  - Avg MAE: -9.2 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price breaks above prev day high -> resistance cleared, exit
  - No follow-through on rejection -> tighten stop
  - RSI fails to drop below 50 -> weak rejection

**SPY-SPECIFIC NOTES:**
  - SPY respects previous day high as resistance
  - Use VWAP crossing to confirm rejection


---

### SPY CARD 11: Order Block Test (Institutional Zone)
**WHAT YOU SEE ON THE CHART:**
  * Price is testing an identified order block zone
  * Current bar is 2U (bouncing off the institutional zone)

**WHAT TO CHECK:**
  - [ ] Price is at order block high or low boundary
  - [ ] RSI between 35-55 (not extreme)
  - [ ] Volume increasing at the zone
  - [ ] Strat shows reversal or continuation with direction

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: Good (n=157)
  - Historical win rate: 45.9%
  - Avg return: +0.1 bps
  - Target: +0.15%
  - Stop: -0.10%
  - Expected hold: 12-18 min
  - Avg MFE: +12.0 bps
  - Avg MAE: -7.7 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price slices through the order block cleanly -> zone invalidated, exit
  - No bounce within 5 bars -> zone may be broken
  - Multiple tests weaken the zone -> less reliable each time

**SPY-SPECIFIC NOTES:**
  - SPY order blocks are more defined (institutional trading)
  - SPX-derived levels also apply to SPY


---

### SPY CARD 12: FTFC Maximum Conviction (All Aligned)
**WHAT YOU SEE ON THE CHART:**
  * ALL timeframes showing the same direction
  * EMAs bullish, ORB bullish, Strat 2U, RSI healthy
  * This is the STRONGEST possible setup

**WHAT TO CHECK:**
  - [ ] EMA9 > EMA20 (bullish cross)
  - [ ] ORB 30m trend is bullish
  - [ ] Current Strat bar is 2U
  - [ ] RSI between 40-65 (healthy, not overbought)
  - [ ] Price above VWAP
  - [ ] RVOL > 1.0 (volume confirms)

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=62,878)
  - Historical win rate: 48.2%
  - Avg return: -0.0 bps
  - Target: +0.15%
  - Stop: -0.10%
  - Expected hold: 12-18 min
  - Avg MFE: +11.6 bps
  - Avg MAE: -11.7 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Any single alignment breaks -> reduce size
  - RSI > 75 -> take profit regardless
  - RVOL drops below 0.8 -> conviction weakening
  - Losing money after 5 min in this setup -> something's wrong, exit

**SPY-SPECIFIC NOTES:**
  - SPY FTFC alignment flipped Sharpe from -0.19 to +0.18
  - The BIGGEST relative improvement from Strat filtering
  - Best combo: 1m+30m (NOT 1m+15m like other tickers)


---


---

### QQQ CARD 1: Bullish Continuation (2U-2U-2U)
**WHAT YOU SEE ON THE CHART:**
  * Daily bar is 2U (higher high, higher low)
  * 15m bar is 2U
  * 1m shows: 2U -> 2U -> 2U (three consecutive bullish bars)

**WHAT TO CHECK:**
  - [ ] RSI between 40-65 (not overbought yet)
  - [ ] Price above VWAP
  - [ ] Price above EMA9
  - [ ] ORB 30m trend is bullish
  - [ ] EMA9 > EMA20 (bullish cross)

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=86,713)
  - Historical win rate: 47.1%
  - Avg return: -0.0 bps
  - Target: +0.25%
  - Stop: -0.12%
  - Expected hold: 10-15 min
  - Avg MFE: +17.9 bps
  - Avg MAE: -18.1 bps

**REVERSAL WARNING SIGNS (exit early):**
  - RSI crosses above 75 -> take profit
  - 1m bar prints 2D -> tighten stop to breakeven
  - RVOL drops below 0.8 -> momentum fading
  - Price hits prev day/week high -> resistance

**QQQ-SPECIFIC NOTES:**
  - QQQ CALLS only win 37.6% — be EXTRA selective
  - Momentum matters MORE here — StochRSI is more predictive
  - Score 6/8 signals hit 52.0% with +3.5 bps — quality over quantity
  - Best combo: 1m+15m (Sharpe 6.67, WR 52.0%)


---

### QQQ CARD 2: Bearish Continuation (2D-2D-2D)
**WHAT YOU SEE ON THE CHART:**
  * Daily bar is 2D (lower high, lower low)
  * 15m bar is 2D
  * 1m shows: 2D -> 2D -> 2D (three consecutive bearish bars)

**WHAT TO CHECK:**
  - [ ] RSI between 35-60 (not oversold yet)
  - [ ] Price below VWAP
  - [ ] Price below EMA9
  - [ ] ORB 30m trend is bearish
  - [ ] EMA9 < EMA20 (bearish cross)

**IF ALL CONFIRMED -> PUT ENTRY**
  - Confidence: High (n=78,289)
  - Historical win rate: 46.0%
  - Avg return: -0.1 bps
  - Target: +0.25%
  - Stop: -0.12%
  - Expected hold: 10-15 min
  - Avg MFE: +20.6 bps
  - Avg MAE: -20.3 bps

**REVERSAL WARNING SIGNS (exit early):**
  - RSI crosses below 25 -> take profit
  - 1m bar prints 2U -> tighten stop to breakeven
  - RVOL drops below 0.8 -> selling pressure fading
  - Price hits prev day/week low -> support

**QQQ-SPECIFIC NOTES:**
  - QQQ has the MOST stops hit (49.2%)
  - Fastest failures: 7 min median to stop
  - QQQ momentum means 2D sequences may accelerate


---

### QQQ CARD 3: Bullish Reversal (2D-1-2U)
**WHAT YOU SEE ON THE CHART:**
  * Previous bars: 2D (bearish) -> 1 (inside bar compression)
  * Current bar: Breaking above the inside bar's high (2U)

**WHAT TO CHECK:**
  - [ ] RSI < 45 (was oversold from the 2D move)
  - [ ] Price at or near support level (prev day low, VWAP, order block)
  - [ ] StochRSI was oversold (< 20), now turning up
  - [ ] Volume confirming (RVOL > 1.0)

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=30,665)
  - Historical win rate: 48.2%
  - Avg return: +0.0 bps
  - Target: +0.25%
  - Stop: -0.12%
  - Expected hold: 10-15 min
  - Avg MFE: +16.5 bps
  - Avg MAE: -16.8 bps

**REVERSAL WARNING SIGNS (exit early):**
  - If breakout fails and price drops back inside the 1 bar -> exit immediately
  - RSI fails to cross above 50 -> weak reversal
  - No volume on breakout -> likely false breakout

**QQQ-SPECIFIC NOTES:**
  - QQQ needs MORE consecutive bars before reversal than IWM
  - Momentum character means reversals are harder to time


---

### QQQ CARD 4: Bearish Reversal (2U-1-2D)
**WHAT YOU SEE ON THE CHART:**
  * Previous bars: 2U (bullish) -> 1 (inside bar compression)
  * Current bar: Breaking below the inside bar's low (2D)

**WHAT TO CHECK:**
  - [ ] RSI > 55 (was overbought from the 2U move)
  - [ ] Price at or near resistance (prev day high, upper BB)
  - [ ] StochRSI was overbought (> 80), now turning down
  - [ ] Volume confirming (RVOL > 1.0)

**IF ALL CONFIRMED -> PUT ENTRY**
  - Confidence: High (n=30,424)
  - Historical win rate: 46.7%
  - Avg return: +0.0 bps
  - Target: +0.25%
  - Stop: -0.12%
  - Expected hold: 10-15 min
  - Avg MFE: +17.1 bps
  - Avg MAE: -16.7 bps

**REVERSAL WARNING SIGNS (exit early):**
  - If price recovers back above inside bar's low -> exit immediately
  - RSI fails to cross below 50 -> weak reversal
  - No volume on breakdown -> likely false breakdown

**QQQ-SPECIFIC NOTES:**
  - QQQ bullish-to-bearish exhaustion CAN be profitable
  - Look for RSI divergence on QQQ (price higher, RSI lower)


---

### QQQ CARD 5: Outside Bar Breakout (Type 3 Bullish)
**WHAT YOU SEE ON THE CHART:**
  * Current bar is Type 3 (higher high AND lower low than prev bar)
  * Close is above previous bar's close (bullish resolution)

**WHAT TO CHECK:**
  - [ ] RSI between 40-60 (room to run)
  - [ ] Close in upper half of the bar's range
  - [ ] Volume above average (RVOL > 1.2)
  - [ ] Higher timeframe supports the direction

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=40,401)
  - Historical win rate: 48.2%
  - Avg return: +0.0 bps
  - Target: +0.25%
  - Stop: -0.12%
  - Expected hold: 10-15 min
  - Avg MFE: +19.2 bps
  - Avg MAE: -19.4 bps

**REVERSAL WARNING SIGNS (exit early):**
  - If next bar is Type 1 (inside) -> tighten stop
  - Price drops below midpoint of the 3 bar -> exit
  - Outside bars often exhaust moves -> be ready for reversal

**QQQ-SPECIFIC NOTES:**
  - QQQ outside bars often reflect gap-and-go momentum
  - Post-gap Type 3 bars have different characteristics


---

### QQQ CARD 6: ORB Breakout — Bullish
**WHAT YOU SEE ON THE CHART:**
  * Price has broken above 30m Opening Range High
  * Current Strat bar confirms: 2U or 3

**WHAT TO CHECK:**
  - [ ] RSI not overbought (< 70)
  - [ ] Price above VWAP
  - [ ] EMA9 > EMA20
  - [ ] RVOL > 1.0 (volume confirming breakout)
  - [ ] At least 30 min after market open

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=160,212)
  - Historical win rate: 47.8%
  - Avg return: -0.0 bps
  - Target: +0.25%
  - Stop: -0.12%
  - Expected hold: 10-15 min
  - Avg MFE: +15.8 bps
  - Avg MAE: -15.5 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price returns inside ORB range -> failed breakout, exit
  - Declining volume on continuation -> fade risk
  - Approaching prev day/week high -> resistance ahead

**QQQ-SPECIFIC NOTES:**
  - QQQ often GAPS at open — ORB sets differently
  - After gap opens, ORB breakouts may be more decisive


---

### QQQ CARD 7: ORB Breakout — Bearish
**WHAT YOU SEE ON THE CHART:**
  * Price has broken below 30m Opening Range Low
  * Current Strat bar confirms: 2D or 3

**WHAT TO CHECK:**
  - [ ] RSI not oversold (> 30)
  - [ ] Price below VWAP
  - [ ] EMA9 < EMA20
  - [ ] RVOL > 1.0
  - [ ] At least 30 min after market open

**IF ALL CONFIRMED -> PUT ENTRY**
  - Confidence: High (n=127,560)
  - Historical win rate: 47.7%
  - Avg return: -0.0 bps
  - Target: +0.25%
  - Stop: -0.12%
  - Expected hold: 10-15 min
  - Avg MFE: +22.5 bps
  - Avg MAE: -21.4 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price returns inside ORB range -> failed breakdown, exit
  - RSI reaching extreme oversold -> bounce risk
  - Approaching prev day/week low -> support ahead

**QQQ-SPECIFIC NOTES:**
  - QQQ bearish ORB breaks can accelerate fast
  - Momentum makes stops important — respect -0.12%


---

### QQQ CARD 8: ORB Failure / Mean Reversion
**WHAT YOU SEE ON THE CHART:**
  * Price broke above ORB high, then FAILED and returned inside range
  * Current Strat shows 2D (confirming the failure)

**WHAT TO CHECK:**
  - [ ] RSI was elevated (> 60) at breakout
  - [ ] Volume declining on the failed breakout
  - [ ] Strat shows reversal (2D after 2U or 3)
  - [ ] VWAP is nearby (target)

**IF ALL CONFIRMED -> PUT ENTRY**
  - Confidence: High (n=7,031)
  - Historical win rate: 44.5%
  - Avg return: -0.2 bps
  - Target: +0.25%
  - Stop: -0.12%
  - Expected hold: 8-15 min
  - Avg MFE: +19.1 bps
  - Avg MAE: -18.5 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price re-breaks ORB high -> failure of the failure, exit
  - Price hits ORB mid and stalls -> take partial profit
  - RSI crosses below 40 -> full reversal, let it run

**QQQ-SPECIFIC NOTES:**
  - QQQ ORB failures after gap opens may be especially profitable
  - Gap fills combine well with failed ORB breakouts


---

### QQQ CARD 9: Support Bounce (at Historical Level)
**WHAT YOU SEE ON THE CHART:**
  * Price is at previous day's low (support level)
  * Current bar is 2U (bouncing off support)

**WHAT TO CHECK:**
  - [ ] RSI < 40 (oversold at support)
  - [ ] StochRSI crossed above 20 (turning up)
  - [ ] Order block nearby (institutional interest)
  - [ ] Volume increasing on bounce

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=21,133)
  - Historical win rate: 47.3%
  - Avg return: +0.0 bps
  - Target: +0.25%
  - Stop: -0.12%
  - Expected hold: 10-15 min
  - Avg MFE: +17.6 bps
  - Avg MAE: -16.7 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price breaks below prev day low -> support failed, exit immediately
  - No follow-through (next bar is 1 or 2D) -> tighten stop
  - RSI fails to clear 50 -> weak bounce

**QQQ-SPECIFIC NOTES:**
  - QQQ bounces less reliably than IWM (momentum character)
  - Need STRONG volume confirmation for bounces on QQQ


---

### QQQ CARD 10: Resistance Rejection (at Historical Level)
**WHAT YOU SEE ON THE CHART:**
  * Price is at previous day's high (resistance level)
  * Current bar is 2D (rejecting off resistance)

**WHAT TO CHECK:**
  - [ ] RSI > 60 (overbought at resistance)
  - [ ] StochRSI crossed below 80 (turning down)
  - [ ] Volume declining on approach to resistance
  - [ ] Bearish divergence (price higher, RSI lower)

**IF ALL CONFIRMED -> PUT ENTRY**
  - Confidence: High (n=36,960)
  - Historical win rate: 45.1%
  - Avg return: -0.0 bps
  - Target: +0.25%
  - Stop: -0.12%
  - Expected hold: 10-15 min
  - Avg MFE: +13.2 bps
  - Avg MAE: -12.2 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price breaks above prev day high -> resistance cleared, exit
  - No follow-through on rejection -> tighten stop
  - RSI fails to drop below 50 -> weak rejection

**QQQ-SPECIFIC NOTES:**
  - QQQ tends to blow through resistance on momentum days
  - Only fade QQQ at resistance with STRONG reversal signals


---

### QQQ CARD 11: Order Block Test (Institutional Zone)
**WHAT YOU SEE ON THE CHART:**
  * Price is testing an identified order block zone
  * Current bar is 2U (bouncing off the institutional zone)

**WHAT TO CHECK:**
  - [ ] Price is at order block high or low boundary
  - [ ] RSI between 35-55 (not extreme)
  - [ ] Volume increasing at the zone
  - [ ] Strat shows reversal or continuation with direction

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: Good (n=111)
  - Historical win rate: 35.1%
  - Avg return: -0.7 bps
  - Target: +0.25%
  - Stop: -0.12%
  - Expected hold: 10-15 min
  - Avg MFE: +14.5 bps
  - Avg MAE: -13.1 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Price slices through the order block cleanly -> zone invalidated, exit
  - No bounce within 5 bars -> zone may be broken
  - Multiple tests weaken the zone -> less reliable each time

**QQQ-SPECIFIC NOTES:**
  - Tech mega-caps drive QQQ — order blocks reflect their activity
  - QQQ order block tests need volume confirmation


---

### QQQ CARD 12: FTFC Maximum Conviction (All Aligned)
**WHAT YOU SEE ON THE CHART:**
  * ALL timeframes showing the same direction
  * EMAs bullish, ORB bullish, Strat 2U, RSI healthy
  * This is the STRONGEST possible setup

**WHAT TO CHECK:**
  - [ ] EMA9 > EMA20 (bullish cross)
  - [ ] ORB 30m trend is bullish
  - [ ] Current Strat bar is 2U
  - [ ] RSI between 40-65 (healthy, not overbought)
  - [ ] Price above VWAP
  - [ ] RVOL > 1.0 (volume confirms)

**IF ALL CONFIRMED -> CALL ENTRY**
  - Confidence: High (n=59,707)
  - Historical win rate: 47.8%
  - Avg return: +0.0 bps
  - Target: +0.25%
  - Stop: -0.12%
  - Expected hold: 10-15 min
  - Avg MFE: +15.0 bps
  - Avg MAE: -14.7 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Any single alignment breaks -> reduce size
  - RSI > 75 -> take profit regardless
  - RVOL drops below 0.8 -> conviction weakening
  - Losing money after 5 min in this setup -> something's wrong, exit

**QQQ-SPECIFIC NOTES:**
  - HARDEST ticker to trade — needs HIGHEST conviction entry
  - Consider ONLY taking score 5+ signals on QQQ
  - When aligned, QQQ momentum provides excellent returns

---

## Appendix: Multi-Timeframe Filtered Win Rates (Updated 2026-02-22)

The 12 decision cards above show win rates for **unfiltered Strat patterns** (~47–49% WR
from raw 1m bar sequences). The table below shows what happens when the same entries are
filtered by a higher-timeframe trend filter — this is the production-ready edge.

> **Why the gap?** Unfiltered Strat patterns catch both trend and counter-trend moves.
> Adding a higher-TF filter (e.g., only CALL when 30m trend is bullish) eliminates most
> counter-trend entries, sharply improving win rate and risk-adjusted returns.

### Win Rate Comparison: Unfiltered vs Multi-TF Filtered

| Ticker | Setup         | Trades  | Win Rate  | Expectancy | Sharpe    | Max DD  |
|--------|---------------|---------|-----------|------------|-----------|---------|
| IWM    | Unfiltered    | ~91,000 | ~47–49%   | ~0.0 bps   | ~9.0      | —       |
| IWM    | **1m+30m**    | 11,143  | **56.7%** | +0.87 bps  | **11.05** | -0.70%  |
| IWM    | 1m+15m        | 11,773  | 55.8%     | +0.81 bps  | 10.34     | -0.65%  |
| IWM    | 5m+15m        | 9,314   | **62.6%** | +0.62 bps  | 8.34      | -0.71%  |
| IWM    | 15m+30m       | 4,929   | **62.9%** | +0.75 bps  | 5.40      | -1.36%  |
| SPY    | Unfiltered    | ~83,000 | ~46–48%   | ~0.0 bps   | ~8.0      | —       |
| SPY    | **1m+30m**    | 10,420  | **58.8%** | +0.59 bps  | **9.46**  | -0.64%  |
| SPY    | 1m+15m        | 11,307  | 56.4%     | +0.51 bps  | 8.47      | -0.51%  |
| SPY    | 5m+15m        | 9,752   | **62.2%** | +0.39 bps  | 7.65      | -0.61%  |
| SPY    | 15m+30m       | 5,682   | **63.2%** | +0.43 bps  | 5.28      | -1.00%  |
| QQQ    | Unfiltered    | ~87,000 | ~46–48%   | ~0.0 bps   | ~8.5      | —       |
| QQQ    | **1m+30m**    | 10,656  | **57.5%** | +0.79 bps  | **10.21** | -1.23%  |
| QQQ    | 1m+15m        | 11,394  | 56.1%     | +0.73 bps  | 9.63      | -0.93%  |
| QQQ    | 5m+15m        | 9,198   | **62.6%** | +0.56 bps  | 8.42      | -0.52%  |
| QQQ    | 15m+30m       | 5,031   | **63.4%** | +0.67 bps  | 6.12      | -0.99%  |

*Source: Full 2015–2026 dataset (10+ years), RTH only. Results are in-sample.*

### How to Apply This in Practice

**For maximum risk-adjusted return (Sharpe)**:
- Use **1m+30m** filter: enter only when 30m trend (price vs EMA20) aligns with direction
- IWM Sharpe 11.05 | SPY Sharpe 9.46 | QQQ Sharpe 10.21
- This is the recommended primary filter for systematic 0DTE trading

**For highest win rate (psychological comfort)**:
- Use **5m+15m** entries: enter on 5m directional bar confirmed by 15m trend
- ~62% WR across all tickers — about 3 in 5 trades win
- Trades 20% less frequently than 1m entries (fewer but higher-conviction setups)

**For lowest drawdown**:
- **5m+15m** on QQQ: -0.52% max drawdown (lowest of all filtered combos)
- **1m+15m** on SPY: -0.51% max drawdown

### Important Context

1. **These are in-sample results** (2015–2026 full dataset). Walk-forward OOS validation
   is tracked in `reports/walk_forward_tf_combos_{ticker}.md`.

2. **Options costs not included**. These metrics measure underlying price moves.
   A 0DTE ATM option entry adds bid-ask spread (~1–3% of premium) + theta decay.
   Options P&L analysis is in `reports/options_pnl_{ticker}.md`.

3. **The playbook cards remain your primary guide** for setup identification and
   trade management. Use the filtered win rates above to set realistic expectations
   when those setups are confirmed by the multi-TF filter.
