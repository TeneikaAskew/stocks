# Phase 6: SPY Playbook

Generated: 2026-02-22 06:50:42
Data: 2015-01-02 09:30:00 to 2025-11-14 16:00:00 (1,068,448 bars)

12 decision cards for real-time trading.

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
  - Confidence: High (n=82,362)
  - Historical win rate: 46.9%
  - Avg return: -0.1 bps
  - Target: +0.15%
  - Stop: -0.10%
  - Expected hold: 12-18 min
  - Avg MFE: +13.9 bps
  - Avg MAE: -14.4 bps

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
  - Confidence: High (n=76,706)
  - Historical win rate: 46.3%
  - Avg return: -0.1 bps
  - Target: +0.20%
  - Stop: -0.12%
  - Expected hold: 12-18 min
  - Avg MFE: +15.9 bps
  - Avg MAE: -16.0 bps

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
  - Confidence: High (n=30,708)
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
  - Confidence: High (n=30,836)
  - Historical win rate: 46.6%
  - Avg return: -0.0 bps
  - Target: +0.20%
  - Stop: -0.12%
  - Expected hold: 12-18 min
  - Avg MFE: +13.0 bps
  - Avg MAE: -12.9 bps

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
  - Confidence: High (n=39,877)
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
  - Confidence: High (n=163,572)
  - Historical win rate: 48.1%
  - Avg return: -0.0 bps
  - Target: +0.15%
  - Stop: -0.10%
  - Expected hold: 12-18 min
  - Avg MFE: +12.5 bps
  - Avg MAE: -12.4 bps

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
  - Confidence: High (n=134,259)
  - Historical win rate: 47.8%
  - Avg return: -0.1 bps
  - Target: +0.20%
  - Stop: -0.12%
  - Expected hold: 12-18 min
  - Avg MFE: +17.3 bps
  - Avg MAE: -16.8 bps

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
  - Confidence: High (n=7,331)
  - Historical win rate: 45.3%
  - Avg return: -0.1 bps
  - Target: +0.20%
  - Stop: -0.12%
  - Expected hold: 8-15 min
  - Avg MFE: +14.3 bps
  - Avg MAE: -13.9 bps

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
  - Confidence: High (n=29,650)
  - Historical win rate: 47.7%
  - Avg return: +0.0 bps
  - Target: +0.15%
  - Stop: -0.10%
  - Expected hold: 12-18 min
  - Avg MFE: +12.5 bps
  - Avg MAE: -12.4 bps

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
  - Confidence: High (n=45,660)
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
  - Confidence: High (n=62,013)
  - Historical win rate: 48.2%
  - Avg return: -0.0 bps
  - Target: +0.15%
  - Stop: -0.10%
  - Expected hold: 12-18 min
  - Avg MFE: +11.7 bps
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

