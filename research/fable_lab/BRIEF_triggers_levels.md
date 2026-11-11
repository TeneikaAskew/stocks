# Lane: triggers_levels

Owner's questions (Nov 11, condensed):
1. "Triggers can be any level, not just premarket values." Today the entry trigger is only premarket high/low.
   Test triggers from the whole ladder: nearest level above (calls) / below (puts): prior day high/low, prior
   week high/low, 12HR and 2-day candle highs/lows and 50% levels (The Strat), ATR bands at 0.5/1.0 x the
   ticker's own ATR from prior close, premarket high/low, opening range. Reuse the brief's level code.
2. Volume filter (ignore thin premarket prints) earlier: 29 of 402 ticker-days changed, +11.1R, range -8 to +29
   (unproven). Owner: "Not use another level? Did you try that?" Test falling back to the next ladder level when
   the premarket level is thin or rejected.
3. Isolated-extreme rule earlier: plans +5.9R (-0.1 to +12.1) but it threw out the real IWM Nov 10 CPI low. Test a
   guard that keeps real levels (volume- or regular-session-backed), and "if both the ATR and premarket checks
   fail, use the next level".
4. Targets ("the bigger fix"). Owner's example: price 250, levels up 275/280/285, down 225/220/215. Calls trigger at
   275, TP 280 then 285; puts trigger at 225, TP 220 then 215. If price pushes through the first trigger, the next
   trade follows the next levels aligned with momentum and indicators. Test ladder TP1/TP2/TP3 with scaling out,
   stops at the prior level or a fraction of the ticker's ATR, and re-entry on a push through.
5. Compare against the no-new-triggers-after-10:00 rule.

Method: 1-min bars; extended hours for levels, regular hours for trades. Use the brief's direction as-is and
also both sides (whichever trigger hits first) to separate level quality from direction quality. Per ticker
and combined: R/trade, win rate, avg win/loss, drawdown, by month, with ranges. Each variant alone first.
One cent per share cost each side. Include 2-3 example-day charts (price, levels, entries, targets).
Deliver README.md (plain language: which variants met their hypothesis on both windows, what to change in the
brief and Insights, what not), results.csv, code/, commands.
