# Phase 6: QQQ Playbook

Generated: 2026-02-22 06:53:02
Data: 2015-01-02 09:30:00 to 2025-11-14 16:00:00 (1,067,740 bars)

12 decision cards for real-time trading.

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
  - Confidence: High (n=85,656)
  - Historical win rate: 47.0%
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
  - Confidence: High (n=77,165)
  - Historical win rate: 45.9%
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
  - Confidence: High (n=30,370)
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
  - Confidence: High (n=30,135)
  - Historical win rate: 46.7%
  - Avg return: +0.0 bps
  - Target: +0.25%
  - Stop: -0.12%
  - Expected hold: 10-15 min
  - Avg MFE: +17.2 bps
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
  - Confidence: High (n=39,775)
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
  - Confidence: High (n=158,121)
  - Historical win rate: 47.8%
  - Avg return: -0.0 bps
  - Target: +0.25%
  - Stop: -0.12%
  - Expected hold: 10-15 min
  - Avg MFE: +15.8 bps
  - Avg MAE: -15.6 bps

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
  - Confidence: High (n=125,765)
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
  - Confidence: High (n=6,967)
  - Historical win rate: 44.4%
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
  - Confidence: High (n=20,999)
  - Historical win rate: 47.3%
  - Avg return: +0.0 bps
  - Target: +0.25%
  - Stop: -0.12%
  - Expected hold: 10-15 min
  - Avg MFE: +17.5 bps
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
  - Confidence: High (n=36,497)
  - Historical win rate: 45.0%
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
  - Confidence: High (n=58,951)
  - Historical win rate: 47.8%
  - Avg return: +0.0 bps
  - Target: +0.25%
  - Stop: -0.12%
  - Expected hold: 10-15 min
  - Avg MFE: +15.1 bps
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

