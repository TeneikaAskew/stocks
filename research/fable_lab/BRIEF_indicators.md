# Lane: indicators

Read prior_studies/trading_analysis/README.md first (pct_profitable claimed ~88% vs ~48% real; exit_rsi leaks
the future; in-sample R2 0.64-0.69 went negative out of sample).
Owner (Nov 11): "I'm trying to get the indicators and insights that show the market is moving, when it's moving,
where it's going. When the market starts at 9:30 and by 9:45 it went, say, a call from 250 to 275, what were the
indicators that showed it was moving that way? Vice versa 250 to 225. Look at how pct profitable was done and see
if you can ascertain the intent and what the fixes are." Also: "you said indicators may need work, so let me know."
1. Read lib/trading_analysis.py, its callers, and its git history (git log -p, specs/docs mentioning
   pct_profitable). Write its intent in plain words and every bug with its line.
2. Define a move per ticker in its own ATR (e.g. >= 0.5 x ATR from the open within 15/30/60 min, held 5 min); label
   each session up/down/none with the start time.
3. Indicators known at or before the move's start, no look-ahead: premarket range/trend, gap, opening range break
   (5/15 min), VWAP side and slope, relative volume vs 20-day same-minute volume, 1/5-min RSI and slope, EMA 9/21,
   MACD, prior close location, Strat bar types and FTFC on 5m/15m/60m/daily, the brief's levels, VIX if available.
   Hit rate, lead time, false alarms, lift over base rate, per ticker, with ranges.
4. Simple honest models only (rules or logistic, walk-forward by month) on the primary window; freeze; score the
   holdout. Report out-of-sample as the result.
5. Fixed pct_profitable (real exits, regular hours, no future data), recomputed per ticker by week, old vs new.
Deliver README.md with a real up day and a real down day charted ("which indicators lit up and when"),
results.csv, code/, commands, and indicator changes for the brief and Insights, each marked held out of sample or not.
