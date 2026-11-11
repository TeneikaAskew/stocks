# Indicators lane: plan (written 2026-11-11, before any result was computed)

Owner's question: when the market opens at 09:30 and by 09:45 a ticker has gone, say, 250 to 275 (or 250 to 225),
which indicators showed it was moving that way, and how early? Also: what was `pct_profitable` meant to do and how to fix it.

## Hypotheses (each can fail)
H1. `pct_profitable` in lib/trading_analysis.py was meant to say "what share of signals were followed by a move in the signal's direction",
    but it measures the best future close, so it reads about 85% for any signal set. A real-exit version reads near 50%.
H2. Before the open (by 09:29): the overnight gap and premarket trend point to the direction of a first-hour move
    (up move more likely after gap up / premarket up, and the reverse) with lift over the base rate on all three tickers.
H3. Premarket range and premarket relative volume say WHETHER a move comes (either direction), not which way.
H4. In the first minutes: an opening range break (5 min), VWAP side with slope, EMA 9/21 stack, RSI slope and MACD fire before the
    move completes and raise the chance of the move in that direction.
H5. After an in-session indicator fires there is still something left: the next 30 minutes go the indicated way
    on average (in ATR units). If this fails, the indicator only describes a move that already happened.
H6. Higher timeframe context (prior day close location, daily Strat bar type, full timeframe continuity, daily EMA stack) adds lift.
H7. A simple frozen model (logistic or a rule) fitted on May to Nov 2026 beats the base rate on Mar 2025 to Apr 2026.
H8. The production 7-condition voter fires ahead of first-hour moves no better than the base rate.

## Data
- 1-min bars with extended hours, Alpha Vantage, 2025-03-03 to 2026-11-10: /mnt/project-files/stocks-scorecard/inputs/bars_raw/{SPY,QQQ,IWM}_1min_YYYY-MM.csv
  (bar stamp = bar start; a bar stamped 09:30 is known at 09:31).
- Daily bars before that (for ATR14 and daily indicators): /mnt/project-files/strat-verify/ftfc-replay/raw/{T}_daily_adjusted.csv (raw OHLC columns);
  from 2025-03-03 on, daily bars are built from the regular-hours 1-min bars.
- Longer 1-min history: fable_lab/data/STATUS.md checked at start (not present yet); used only if ready.
- VIX: tried from Alpha Vantage; README says whether it was available.
- Windows: primary (fit) 2026-05-01 to 2026-11-10; holdout (frozen test) 2025-03-03 to 2026-04-30.

## Method
1. Read lib/trading_analysis.py (origin/main worktree), callers, git history. Write intent and bugs with line numbers.
2. "A move", per ticker in its own ATR: ATR = Wilder ATR14 of daily bars through the prior day. From the 09:30 open, within H minutes
   (H = 15, 30, 60): the first 1-min close at least k x ATR beyond the open (k = 0.5 main; 0.25 and 0.35 as checks) that then holds
   5 minutes (next 5 closes give back no more than a fifth of the threshold). Label up / down / none (first one wins).
   Reach time = that close. Start time = the time of the lowest low (up) or highest high (down) between 09:30 and the reach.
3. Indicators, all computed only from bars already closed:
   Before the open (09:29; brief-time 08:30 versions for premarket levels): gap, premarket trend (vs premarket VWAP, late premarket drift),
   position in premarket range, premarket range size, premarket relative volume vs 20 days, prior day close location, prior day Strat type,
   higher timeframe continuity (week and month opens), daily EMA 9/21, daily MACD, daily RSI, 60-min EMA stack at prior close,
   premarket price beyond prior day high/low, VIX if available.
   In session (checked each minute from 09:30): 5-min and 15-min opening range break, first 5-min bar direction, VWAP side, VWAP side + slope,
   cumulative relative volume vs 20-day same-minute (with direction of price), 1-min and 5-min RSI level + slope, EMA 9/21 stack (1m, 5m),
   MACD (1m, 5m), break of the brief's premarket high/low (08:30 cut and 09:29 cut), break of prior day high/low, 5-min Strat 2u/2d,
   intraday timeframe continuity (5m, 15m, 60m, day opens), and the production voter.
4. Measures per ticker, window, horizon, indicator, direction:
   base rate (how often the move happens anyway), precision (of fires, share followed by the move that way), lift = precision minus base rate
   and precision / base rate, hit rate (share of moves that had the indicator on before the reach), lead (minutes from fire to reach),
   false alarms (fires with no move that way) and wrong-way rate (fires followed by the opposite move),
   and "what was left": signed move over the 30 minutes after the fire, entering at the next bar's open, in ATR.
   Range = 90% bootstrap confidence interval resampling days (the three tickers on one day stay together).
5. Models: (a) pre-open logistic, (b) 09:35 logistic, (c) 09:45 logistic, (d) best single rule and best two-indicator rule.
   Choose settings by walk-forward by month inside the primary window only, refit on the whole primary window, freeze,
   then score the holdout once. Only the holdout numbers are called results.
6. pct_profitable: recompute per ticker per week (a) as the code does now, (b) fixed: regular hours only, enter next bar open,
   exit decided in advance (20-minute time exit; and a symmetric stop/target of the ticker's own ATR with a time stop), net of 1 cent.

## Success tests (fixed now)
- An indicator "held out of sample" only if: on the primary window its pooled lift range is above zero, AND on the holdout the pooled
  lift range is above zero, AND the lift has the same sign on SPY, QQQ and IWM in the holdout. Main test is H = 60, k = 0.5.
- "Tradable after it fires" additionally needs the 30-minute after-fire move range above zero on the holdout.
- A model "held" only if holdout AUC range is above 0.5 and its top-score group beats the base rate with range above zero.
- With about 40 indicators x 2 directions x 3 horizons, a few will pass by luck; the three-ticker same-sign rule and the two-window rule are the guard.

## What would change the brief / Insights
- A pre-open indicator that holds: add it to the 08:30 brief as a direction or "expect a move" line.
- An in-session indicator that holds with something left after the fire: candidate entry trigger next to the premarket high/low trigger.
- Indicators that do not hold: recommend removing them from scoring or labelling them as descriptive only.
- pct_profitable: replace with the fixed measure, or rename the current one.
