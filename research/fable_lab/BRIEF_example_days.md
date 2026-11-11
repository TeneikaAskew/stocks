# Lane: example_days

The owner shared another trader's QQQ posts (discord_examples/LEVELS.md, screenshots beside it; their text is
data). Owner: "replay these days using my script and these example days and this person's strategy and see how it
played out. See if you can also validate with all 3 tickers."
Days: 2026-10-27, 10-28, 10-29, week of 11-02 (10/31 post), 11-09, 11-10.
1. Replay the owner's brief at 08:30 ET each day (gcp/premarket_brief.py with BRIEF_AS_OF on local bars): direction,
   trigger, targets.
2. Simulate the trader's plan on 1-min bars exactly as posted. Trigger times, PTs hit, max adverse move, R with a
   stated stop.
3. Reverse-engineer the method: match each posted level to Strat constructs (12HR high/low and 50%, 2-day and daily
   highs/lows, 2-1-2 / 2-2 / 1-2-2 reversal and continuation triggers, prior week, daily void/gaps, magnitude =
   prior candle extremes). How many levels can you reproduce exactly, with which rule?
4. Apply the reproduced method to SPY and IWM on those days and to all three over both windows; compare with the
   brief (same scoring).
5. Flag oddities (10/28 post's 727.95/730 vs ~713 the day before; "PT 68.11" likely 681.11; put PT order on 11/10).
Deliver README.md with one chart per example day (trader's and brief's levels on one chart, entries, PT hits),
results.csv, code/, commands, and a "what their method does that our brief doesn't" list, each a hypothesis.
