# Phase 6: IWM Playbook

Generated: 2026-02-22 06:48:30
Data: 2015-01-02 09:30:00 to 2025-11-14 16:00:00 (1,067,154 bars)

12 decision cards for real-time trading.

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
  - Confidence: High (n=89,377)
  - Historical win rate: 47.9%
  - Avg return: -0.1 bps
  - Target: +0.30%
  - Stop: -0.15%
  - Expected hold: 10-15 min
  - Avg MFE: +20.0 bps
  - Avg MAE: -20.9 bps

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
  - Confidence: High (n=85,526)
  - Historical win rate: 47.4%
  - Avg return: -0.1 bps
  - Target: +0.38%
  - Stop: -0.20%
  - Expected hold: 10-15 min
  - Avg MFE: +21.9 bps
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
  - Confidence: High (n=28,943)
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
  - Confidence: High (n=28,845)
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
  - Confidence: High (n=38,542)
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
  - Confidence: High (n=143,569)
  - Historical win rate: 47.5%
  - Avg return: -0.0 bps
  - Target: +0.30%
  - Stop: -0.15%
  - Expected hold: 10-15 min
  - Avg MFE: +18.3 bps
  - Avg MAE: -18.3 bps

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
  - Confidence: High (n=136,006)
  - Historical win rate: 47.9%
  - Avg return: -0.0 bps
  - Target: +0.38%
  - Stop: -0.20%
  - Expected hold: 10-15 min
  - Avg MFE: +22.4 bps
  - Avg MAE: -22.1 bps

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
  - Confidence: High (n=6,550)
  - Historical win rate: 47.9%
  - Avg return: +0.2 bps
  - Target: +0.38%
  - Stop: -0.20%
  - Expected hold: 8-15 min
  - Avg MFE: +22.0 bps
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
  - Confidence: High (n=21,436)
  - Historical win rate: 47.5%
  - Avg return: -0.0 bps
  - Target: +0.30%
  - Stop: -0.15%
  - Expected hold: 10-15 min
  - Avg MFE: +17.8 bps
  - Avg MAE: -18.7 bps

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
  - Confidence: High (n=25,776)
  - Historical win rate: 45.7%
  - Avg return: -0.0 bps
  - Target: +0.38%
  - Stop: -0.20%
  - Expected hold: 10-15 min
  - Avg MFE: +16.6 bps
  - Avg MAE: -15.7 bps

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
  - Confidence: High (n=54,357)
  - Historical win rate: 47.6%
  - Avg return: -0.0 bps
  - Target: +0.30%
  - Stop: -0.15%
  - Expected hold: 10-15 min
  - Avg MFE: +17.6 bps
  - Avg MAE: -17.5 bps

**REVERSAL WARNING SIGNS (exit early):**
  - Any single alignment breaks -> reduce size
  - RSI > 75 -> take profit regardless
  - RVOL drops below 0.8 -> conviction weakening
  - Losing money after 5 min in this setup -> something's wrong, exit

**IWM-SPECIFIC NOTES:**
  - When all aligned, IWM provides the BEST risk/reward
  - Sharpe 9.64 on 1m+15m — strongest of all tickers
  - But these setups are RARE (492 trades in 10 years)

