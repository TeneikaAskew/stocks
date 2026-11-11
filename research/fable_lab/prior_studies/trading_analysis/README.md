# lib/trading_analysis.py: weekly walk-forward review (SPY, QQQ, IWM)

Research only. Nothing here touches production, the historical_signals table or the repo.
Code under review: TeneikaAskew/stocks origin/main at 300b40df (`lib/trading_analysis.py`, identical to the copy the earlier review used).

## What the script is for

It is an indicator discovery tool. It computes about 60 indicators on 1-minute bars, fires a 7-condition momentum
voter (call or put when at least 5 of 7 conditions hold and at least 2 are core), scores each signal, and then ranks
which indicator values best explain signal outcomes (RandomForest plus correlation). The "new values" it gives T are:
1. a per-signal outcome and a headline "profitable signals %" (the same number the API serves as `pct_profitable`
   through `scripts/run_historical_signals.py` into `historical_signals`, `platform/api/routers/signals.py:565`);
2. a ranking of which indicator features matter (`*_feature_importance` file).
It does not output thresholds itself; the voter thresholds (RSI 25 to 50, RVOL 1.2, ATR expansion 1.15, RSI thrust 5) are hard coded.
To test "which conditions or thresholds are worth using" this study adds a small threshold grid and simple context conditions and lets each scoring method pick from them.

## What is wrong with it (verified on this checkout)

| Problem | Where | Effect |
|---|---|---|
| Outcome is the best close in the next 20 rows, not an exit | lines 940 to 990 | 84 to 85% of signals score as "profitable" on all three tickers. It can be negative (about 15% are) only when all 20 closes are worse than entry. |
| Windows are counted in rows, bars include 04:00 to 20:00 | 816, 941 | 53 to 57% of voter signals fire in extended hours; 1.5% of 20-row windows end on another calendar day. |
| exit_rsi, exit_vwap, exit_obv (values at the best future bar) are model inputs | 1075 to 1077, exclude list 1122 | exit_rsi is the number 1 feature in 217 of 231 weekly reruns. Pure leakage. |
| Importance and R2 are in sample | 1197, 1250 | Script prints R2 about 0.64 to 0.69; on the next week the mean R2 is negative (SPY -0.86, QQQ -0.40, IWM -0.21). |
| ORB levels mapped to the whole day, RVOL by minute uses the full sample mean | 554, 283 | Look-ahead in those features. |
| Only the momentum voter is scored; no per-ticker or per-period breakdown | | Nothing tells T whether a value holds up next week. |

## Method

Data: Alpha Vantage 1-minute bars, extended hours, 2025-03-03 to 2026-11-10 (`/mnt/project-files/stocks-scorecard/inputs/bars_raw`);
daily bars from `/mnt/project-files/strat-verify/ftfc-replay/raw` before the intraday history (ATR14 and the 50-day regime need it).
Indicators are always the production `MarketAnalyzer` code, imported from the clean checkout. Every ticker is run separately.

Walk-forward: 77 eval weeks (2025-05-26 to 2026-11-09, the last one is Mon and Tue only). For each week W and lookback N in 1, 4, 12 weeks,
the method looks only at weeks W-N to W-1, picks its top condition, and that pick is traded during week W.

* ORIGINAL scoring: the script's own measure. Every condition is scored on all bars including extended hours by its average
  20-row best close move; claimed win rate = share of fires with that move above 0. Minimum 30 fires per fit week.
* FIXED scoring: regular hours only, indicators computed on regular-hours bars, entry at the next bar open, real exit, one position
  at a time per condition, net of a 1 cent per share round trip. Ranked by average net result. Minimum 3 trades per fit week.
* Realized (the same for both): the picked condition traded in week W with a real exit. ORIGINAL picks use the script's
  own flags (extended-hours indicators), traded only during regular hours.
  * Exit A: hold 20 minutes (the script's default window). Enter at the next bar open, exit at the open 20 bars later or the 15:55 open. Units: bps.
  * Exit B: stop 0.5 x prior-day ATR14, target 1.0 x ATR, else flat at the 15:55 open (stop wins if both hit in one bar). Units: R (1R = 0.5 ATR).
* VOTER: the voter exactly as written (vectorized; fire count matches `generate_technical_signals` exactly on all three tickers),
  claimed = its own `return_pct > 0` share that week (what the API shows), realized = every fire traded with the real exit.
* BASELINE: long at every bar, one position at a time. Benchmark for drift and costs.
* Conditions scored (98 per ticker): the 14 voter conditions, the voter itself, a threshold grid (RSI thrust 3 and 8, RVOL 1.5 and 2.0,
  ATR expansion 1.0 and 1.3, RSI below 30 or 40 and above 60 or 70, StochRSI K below 20 or above 80, VWAP side), and 19 context conditions
  (opening range, prior day high and low, gaps, time of day, time-of-day relative volume, 15 and 60 minute trend, streaks) each long and short.
* Improvement 1, PERSIST: only trade a condition that is net positive over the last 12 weeks AND positive in at least 3 of the last 4 weeks; otherwise sit out.
* Improvement 2, REGIME: rank separately for days when the prior close was above or below its 50-day average; trade the pick for the day's regime.

"t (weekly)" is the mean of the weekly net sums divided by its standard error. With about 100 comparisons in these tables,
a few |t| near 2 are expected by chance.

## How to rerun

```
cd /mnt/project-files/stocks-scorecard/research/trading_analysis
git -C /home/claude/stocks fetch origin main
git -C /home/claude/stocks worktree add --detach /tmp/ta2_wt origin/main      # any clean checkout
export TA_REPO=/tmp/ta2_wt                                                   # code/common2.py reads this
for T in SPY QQQ IWM; do python3 -I code/prep.py $T; done                    # about 4 min each, can run in parallel
python3 -I code/walkforward.py                                               # about 1.5 min
python3 -I code/rf_weekly.py                                                 # about 10 min
python3 -I code/summarize2.py                                                # tables and charts
```
Python 3 with pandas 2.3, numpy 2.4, scikit-learn 1.9, matplotlib 3.11, pyarrow.

## Files

* `weekly_results.csv`: one row per ticker, week, exit, method, lookback: top pick, top 3, claimed win and average, realized trades, win, average, sum, net sum.
* `weekly_rf_feature_importance.csv`: the script's feature-importance step rerun every week (4 week fit): top 5 features, exit_* rank, in-sample and next-week R2, overlap with last week.
* `summary_by_ticker.csv`, `summary.md`: aggregates (all weeks and last 26 weeks), stability.
* `charts/equity_{SPY,QQQ,IWM}.png`: cumulative realized net results, out-of-sample weeks only.
* `work/`: per ticker intermediate files (`*_orig_signals.parquet` is the script's untouched signal output).

## Results

### Claimed versus realized (all 77 weeks, 4 week fit)

| ticker | ORIGINAL claimed win | realized win, exit A / B | FIXED claimed win | realized win, exit A / B | VOTER claimed (pct_profitable) | VOTER realized win, A / B |
|---|---|---|---|---|---|---|
| SPY | 88% | 48% / 47% | 63% | 48% / 44% | 84% | 50% / 46% |
| QQQ | 88% | 49% / 42% | 62% | 47% / 47% | 85% | 50% / 48% |
| IWM | 89% | 50% / 44% | 63% | 53% / 48% | 84% | 50% / 46% |

The original claim (88 to 89%) overstates the realized win rate by about 40 points on every ticker; the fixed claim (62 to 63%)
overstates it by about 10 to 18 points, which is the usual "best of 98 in the last 4 weeks" selection effect. Across all weeks,
the rank correlation between the claimed average and next week's realized average is about 0 for both methods
(ORIGINAL 0.015 and 0.006, FIXED -0.05 and -0.07 for exits A and B): a higher score last month did not mean a better next week.

### Stability of the chosen values (4 week fit, all weeks)

| ticker | ORIGINAL: top pick same as last week | distinct top picks | FIXED: top pick same as last week, exit A / B | distinct top picks, A / B |
|---|---|---|---|---|
| SPY | 61% | 12 | 37% / 38% | 23 / 25 |
| QQQ | 61% | 9 | 32% / 29% | 19 / 30 |
| IWM | 54% | 10 | 37% / 32% | 16 / 28 |

The original looks steadier only because the 20-row best close move rewards volatility in either direction: its favourite picks are
"ATR expansion above 1.3", "first 30 minutes" and "gap of 0.3 ATR before 10:30", and it often picks both the long AND the short version
of the same condition in different weeks (IWM: first 30 minutes short 15 weeks, long 13 weeks; QQQ: gap down long 13, short 13).
It is measuring how much price moves, not which way. The fixed method's picks change most weeks (top 3 overlap with last week about a third).

### The script's feature ranking, rerun weekly (`weekly_rf_feature_importance.csv`)

| ticker | weeks | in-sample R2 (what the script prints) | next-week R2, mean / median | exit_* in top 5 | top feature |
|---|---|---|---|---|---|
| SPY | 77 | 0.64 | -0.86 / 0.25 | 100% of weeks | exit_rsi in 70 of 77 weeks |
| QQQ | 77 | 0.69 | -0.40 / 0.31 | 100% | exit_rsi in 73 of 77 |
| IWM | 77 | 0.64 | -0.21 / 0.33 | 100% | exit_rsi in 74 of 77 |

The positive median next-week R2 is the leak, not skill: exit_rsi is read at the very bar that defines the outcome.
A replica of `analyze_feature_importance` was checked to return the identical top 10 as the script's own function.

### Realized results, out of sample, per ticker

Full tables are below (`summary.md`). Headline, all 77 weeks, net of a 1 cent cost:

* Nothing beats "do nothing" reliably. No method has a weekly t above 2 on any ticker or exit. Long every bar loses
  -1,386 / -1,471 / -3,226 bps (SPY / QQQ / IWM, exit A) on costs and noise.
* VOTER as written (what fills historical_signals): exit A -525 / +216 / -2,602 bps; exit B -1.8 / +10.3 / -3.1 R. Win rate 50% / 46 to 48%.
* ORIGINAL picks (4 week fit): exit A -161 / -486 / -593 bps; exit B +9.1 / -11.8 / -12.1 R.
* FIXED picks (4 week fit): exit A -537 / -1,052 / +884 bps; exit B -24.1 / -15.5 / +3.2 R.
* Lookback 1 week ("start a week at a time"): picks change almost every week (top pick repeats 3 to 14% of the time) and results are noise
  (exit A: ORIGINAL -788 / -843 / -692, FIXED +149 / -608 / +207 bps).
* Last 26 weeks look the same: e.g. exit A FIXED 4 week +135 / -391 / +361 bps, ORIGINAL -72 / -324 / +14 bps, none with |t| above 1.

The one pocket that looks consistent is IWM with the fixed scoring and exit A (4 week fit +884 bps, persistence +593, regime +568), mostly from
opening-half-hour and gap conditions. It is t of about 1 and does not carry over to exit B or to SPY or QQQ, so treat it as a lead to test, not a finding.

### Improvements tested (experiment first, nothing swapped in)

| Change | Hypothesis | Result | Met? |
|---|---|---|---|
| Fixed scoring (real exit, regular hours, no leaked features, next-week evaluation) | Claimed win rate close to realized | Gap shrinks from about 40 points to about 10 to 18; with 12 week fit 55 to 60% claimed vs 47 to 55% realized | Yes for honesty |
| Fixed scoring | Picks make money next week | Mixed sign, all |t| below 2 | No |
| PERSIST (positive over 12 weeks and in 3 of last 4) | Positive on all tickers and better than plain 12 week fit | Exit A -134 / -1,394 / +593 bps; exit B -19.2 / +0.1 / +12.5 R. Better than plain 12 week fit on 4 of 6 ticker and exit pairs, but still negative on 3 of 6 | No |
| REGIME (rank by 50-day trend regime) | Better than unconditional | Exit A -428 / +588 / +568 bps; exit B -15.0 / -9.4 / -27.9 R (IWM t -2.05) | No |

## What improving it would take

1. Score with a real exit, in regular hours, without exit_* columns, and report only the next period (a one-line change list:
   drop exit_* from features, replace `return_pct` with a time or bracket exit, filter to 09:30 to 16:00, fit on the past and score the future).
   This makes the numbers honest; it does not create an edge.
2. Fix what the API shows: `pct_profitable` from `return_pct > 0` is about 84% for any signal set. It should be computed from a real exit
   (it would read about 46 to 50% today), or labelled as "moved in favour at some point within 20 bars".
3. Rank direction-aware: score long and short versions separately and require the sign to agree across weeks; the current measure cannot tell them apart.
4. Only promote a condition after it holds out of sample for many weeks on its own ticker and beats the long-every-bar benchmark after costs.
   On this data none of 98 conditions does that with confidence; the persistence and regime gates did not fix it.
5. If T wants to pursue it, the cheapest next test is the IWM opening-half-hour lead with a pre-registered rule, evaluated on weeks not used to find it.

## Caveats

* Alpha Vantage history may be cleaner than the live feed (production saw a QQQ Nov 10 premarket print this history lacks).
* Cost is 1 cent per share round trip; no slippage beyond that. For exit A this is about 0.14 to 0.36 bps a trade, which matters
  because the gross edges are about 0 to 2 bps.
* The ORIGINAL condition ranking applies the script's own scoring (20-row best close move, all bars) to each condition; the script itself only
  ranks features. The feature ranking is reported separately above.
* Earlier review note corrected: `return_pct` can be negative (about 15% of signals), it is just positive whenever any of the next 20 closes is better.

## Full tables

### Exit A, last 26 weeks (2026-05-11 to 2026-11-09)

| ticker | method | fit wks | trades | claimed win | realized win | realized avg bps gross | total bps net | t (weekly) | top pick same as last week |
|---|---|---|---|---|---|---|---|---|---|
| SPY | VOTER |  | 1950 | 84% | 50% | 0.14 | 8.7 | 0.02 |  |
| SPY | BASELINE |  | 2304 | % | 51% | -0.30 | -994.2 | -1.53 |  |
| SPY | ORIGINAL | 1 | 340 | 90% | 44% | -1.72 | -630.7 | -2.06 | 12% |
| SPY | ORIGINAL | 4 | 275 | 88% | 48% | -0.13 | -72.2 | -0.24 | 58% |
| SPY | ORIGINAL | 12 | 175 | 88% | 54% | 1.47 | 233.6 | 0.99 | 77% |
| SPY | FIXED | 1 | 263 | 76% | 51% | 0.81 | 178.1 | 0.50 | 12% |
| SPY | FIXED | 4 | 311 | 64% | 50% | 0.57 | 135.0 | 0.60 | 42% |
| SPY | FIXED | 12 | 147 | 56% | 52% | 0.28 | 21.2 | 0.15 | 77% |
| SPY | PERSIST | 12 | 333 | 56% | 50% | 0.25 | 40.6 | 0.17 | 38% |
| SPY | REGIME | 12 | 264 | % | 52% | -0.90 | -272.9 | -1.14 | 31% |
| QQQ | VOTER |  | 1924 | 85% | 49% | -0.14 | -539.1 | -0.74 |  |
| QQQ | BASELINE |  | 2304 | % | 51% | -0.36 | -1144.8 | -1.14 |  |
| QQQ | ORIGINAL | 1 | 190 | 93% | 51% | -0.45 | -112.4 | -0.18 | 19% |
| QQQ | ORIGINAL | 4 | 158 | 89% | 47% | -1.91 | -323.9 | -0.81 | 46% |
| QQQ | ORIGINAL | 12 | 151 | 87% | 45% | -3.53 | -554.5 | -1.24 | 69% |
| QQQ | FIXED | 1 | 250 | 79% | 50% | 0.25 | 28.4 | 0.06 | 12% |
| QQQ | FIXED | 4 | 324 | 62% | 49% | -1.06 | -390.6 | -0.78 | 23% |
| QQQ | FIXED | 12 | 184 | 60% | 55% | -4.28 | -812.9 | -1.31 | 77% |
| QQQ | PERSIST | 12 | 238 | 57% | 50% | -3.62 | -894.5 | -1.29 | 35% |
| QQQ | REGIME | 12 | 228 | % | 53% | 1.98 | 418.6 | 1.34 | 54% |
| IWM | VOTER |  | 1913 | 83% | 50% | -0.03 | -723.2 | -1.04 |  |
| IWM | BASELINE |  | 2304 | % | 49% | -0.56 | -2098.0 | -2.41 |  |
| IWM | ORIGINAL | 1 | 320 | 91% | 49% | -0.69 | -329.2 | -0.61 | 4% |
| IWM | ORIGINAL | 4 | 236 | 90% | 50% | 0.41 | 13.9 | 0.03 | 54% |
| IWM | ORIGINAL | 12 | 211 | 88% | 51% | -0.05 | -83.4 | -0.16 | 85% |
| IWM | FIXED | 1 | 352 | 72% | 50% | -0.34 | -239.4 | -0.60 | 4% |
| IWM | FIXED | 4 | 254 | 63% | 53% | 1.76 | 360.9 | 0.69 | 35% |
| IWM | FIXED | 12 | 199 | 59% | 50% | -0.65 | -197.7 | -0.69 | 65% |
| IWM | PERSIST | 12 | 452 | 57% | 52% | -0.20 | -245.8 | -0.54 | 46% |
| IWM | REGIME | 12 | 287 | % | 52% | -0.09 | -124.3 | -0.33 | 31% |

### Exit A, all 77 eval weeks (2025-05-26 to 2026-11-09)

| ticker | method | fit wks | trades | claimed win | realized win | realized avg bps gross | total bps net | t (weekly) | top pick same as last week |
|---|---|---|---|---|---|---|---|---|---|
| SPY | VOTER |  | 5510 | 84% | 50% | 0.05 | -524.7 | -0.76 |  |
| SPY | BASELINE |  | 6624 | % | 51% | -0.06 | -1386.3 | -1.30 |  |
| SPY | ORIGINAL | 1 | 890 | 91% | 46% | -0.74 | -788.2 | -1.81 | 14% |
| SPY | ORIGINAL | 4 | 701 | 88% | 48% | -0.08 | -160.7 | -0.39 | 61% |
| SPY | ORIGINAL | 12 | 541 | 88% | 51% | 1.18 | 557.3 | 1.55 | 84% |
| SPY | FIXED | 1 | 869 | 77% | 50% | 0.32 | 148.7 | 0.28 | 8% |
| SPY | FIXED | 4 | 774 | 63% | 48% | -0.55 | -537.1 | -1.34 | 37% |
| SPY | FIXED | 12 | 554 | 56% | 49% | -0.29 | -241.4 | -0.54 | 72% |
| SPY | PERSIST | 12 | 1093 | 55% | 51% | 0.02 | -133.9 | -0.26 | 42% |
| SPY | REGIME | 12 | 615 | % | 51% | -0.55 | -427.8 | -1.11 | 39% |
| QQQ | VOTER |  | 5422 | 85% | 50% | 0.20 | 216.0 | 0.20 |  |
| QQQ | BASELINE |  | 6624 | % | 51% | -0.06 | -1471.2 | -0.98 |  |
| QQQ | ORIGINAL | 1 | 777 | 93% | 51% | -0.92 | -842.8 | -1.05 | 12% |
| QQQ | ORIGINAL | 4 | 586 | 88% | 49% | -0.67 | -485.9 | -0.79 | 61% |
| QQQ | ORIGINAL | 12 | 574 | 87% | 47% | -2.33 | -1434.4 | -2.38 | 80% |
| QQQ | FIXED | 1 | 844 | 78% | 50% | -0.56 | -607.6 | -0.82 | 11% |
| QQQ | FIXED | 4 | 628 | 62% | 47% | -1.52 | -1052.1 | -1.53 | 32% |
| QQQ | FIXED | 12 | 494 | 59% | 53% | -0.29 | -220.3 | -0.28 | 66% |
| QQQ | PERSIST | 12 | 1092 | 55% | 49% | -1.11 | -1394.4 | -1.34 | 45% |
| QQQ | REGIME | 12 | 574 | % | 51% | 1.18 | 587.6 | 1.03 | 53% |
| IWM | VOTER |  | 5436 | 84% | 50% | -0.09 | -2602.1 | -2.11 |  |
| IWM | BASELINE |  | 6620 | % | 50% | -0.10 | -3226.0 | -2.09 |  |
| IWM | ORIGINAL | 1 | 859 | 92% | 47% | -0.42 | -691.9 | -0.79 | 5% |
| IWM | ORIGINAL | 4 | 536 | 89% | 50% | -0.72 | -592.5 | -0.77 | 54% |
| IWM | ORIGINAL | 12 | 451 | 89% | 51% | 0.94 | 246.4 | 0.37 | 78% |
| IWM | FIXED | 1 | 914 | 75% | 49% | 0.62 | 206.6 | 0.32 | 7% |
| IWM | FIXED | 4 | 674 | 63% | 53% | 1.70 | 883.7 | 1.19 | 37% |
| IWM | FIXED | 12 | 559 | 58% | 51% | 0.42 | 15.2 | 0.03 | 68% |
| IWM | PERSIST | 12 | 992 | 56% | 53% | 0.98 | 592.9 | 0.81 | 59% |
| IWM | REGIME | 12 | 708 | % | 51% | 1.19 | 568.2 | 0.94 | 37% |

### Exit B, last 26 weeks (2026-05-11 to 2026-11-09)

| ticker | method | fit wks | trades | claimed win | realized win | realized avg R gross | total R net | t (weekly) | top pick same as last week |
|---|---|---|---|---|---|---|---|---|---|
| SPY | VOTER |  | 367 | 84% | 46% | 0.01 | 1.2 | 0.17 |  |
| SPY | BASELINE |  | 201 | % | 48% | -0.02 | -5.5 | -0.48 |  |
| SPY | ORIGINAL | 1 | 124 | 90% | 41% | -0.07 | -9.0 | -1.08 | 12% |
| SPY | ORIGINAL | 4 | 105 | 88% | 48% | 0.06 | 5.7 | 0.71 | 58% |
| SPY | ORIGINAL | 12 | 80 | 88% | 44% | 0.01 | 0.9 | 0.12 | 77% |
| SPY | FIXED | 1 | 115 | 84% | 52% | 0.04 | 4.7 | 0.59 | 8% |
| SPY | FIXED | 4 | 127 | 64% | 45% | -0.05 | -6.8 | -0.89 | 38% |
| SPY | FIXED | 12 | 119 | 60% | 49% | 0.03 | 3.6 | 0.34 | 62% |
| SPY | PERSIST | 12 | 139 | 56% | 47% | -0.00 | -0.4 | -0.04 | 46% |
| SPY | REGIME | 12 | 86 | % | 53% | 0.01 | 0.3 | 0.04 | 31% |
| QQQ | VOTER |  | 355 | 85% | 49% | 0.02 | 6.2 | 0.93 |  |
| QQQ | BASELINE |  | 199 | % | 47% | -0.03 | -6.1 | -0.49 |  |
| QQQ | ORIGINAL | 1 | 83 | 93% | 42% | -0.01 | -0.9 | -0.09 | 19% |
| QQQ | ORIGINAL | 4 | 70 | 89% | 47% | -0.04 | -2.6 | -0.41 | 46% |
| QQQ | ORIGINAL | 12 | 69 | 87% | 49% | 0.07 | 4.7 | 0.54 | 69% |
| QQQ | FIXED | 1 | 92 | 85% | 53% | 0.10 | 8.9 | 1.56 | 4% |
| QQQ | FIXED | 4 | 122 | 62% | 57% | 0.03 | 3.5 | 0.46 | 35% |
| QQQ | FIXED | 12 | 106 | 57% | 54% | 0.05 | 5.5 | 0.72 | 65% |
| QQQ | PERSIST | 12 | 106 | 57% | 53% | 0.07 | 7.6 | 0.98 | 69% |
| QQQ | REGIME | 12 | 94 | % | 50% | 0.04 | 3.9 | 0.45 | 35% |
| IWM | VOTER |  | 382 | 83% | 47% | -0.01 | -4.6 | -0.66 |  |
| IWM | BASELINE |  | 208 | % | 45% | -0.09 | -19.1 | -1.62 |  |
| IWM | ORIGINAL | 1 | 113 | 91% | 41% | -0.10 | -12.3 | -1.48 | 4% |
| IWM | ORIGINAL | 4 | 117 | 90% | 44% | -0.06 | -7.6 | -0.71 | 54% |
| IWM | ORIGINAL | 12 | 106 | 88% | 43% | -0.07 | -7.9 | -0.72 | 85% |
| IWM | FIXED | 1 | 105 | 81% | 44% | 0.05 | 5.2 | 0.55 | 4% |
| IWM | FIXED | 4 | 93 | 67% | 49% | 0.12 | 10.3 | 1.07 | 31% |
| IWM | FIXED | 12 | 106 | 57% | 54% | 0.10 | 10.2 | 1.06 | 58% |
| IWM | PERSIST | 12 | 103 | 56% | 56% | 0.15 | 14.8 | 1.59 | 54% |
| IWM | REGIME | 12 | 116 | % | 47% | -0.02 | -2.5 | -0.27 | 50% |

### Exit B, all 77 eval weeks (2025-05-26 to 2026-11-09)

| ticker | method | fit wks | trades | claimed win | realized win | realized avg R gross | total R net | t (weekly) | top pick same as last week |
|---|---|---|---|---|---|---|---|---|---|
| SPY | VOTER |  | 1047 | 84% | 46% | 0.00 | -1.8 | -0.18 |  |
| SPY | BASELINE |  | 573 | % | 48% | -0.01 | -9.9 | -0.48 |  |
| SPY | ORIGINAL | 1 | 289 | 91% | 43% | -0.04 | -11.7 | -0.88 | 14% |
| SPY | ORIGINAL | 4 | 265 | 88% | 47% | 0.04 | 9.1 | 0.70 | 61% |
| SPY | ORIGINAL | 12 | 227 | 88% | 44% | 0.04 | 8.5 | 0.70 | 84% |
| SPY | FIXED | 1 | 320 | 82% | 47% | -0.01 | -4.1 | -0.27 | 4% |
| SPY | FIXED | 4 | 363 | 62% | 44% | -0.06 | -24.1 | -1.47 | 38% |
| SPY | FIXED | 12 | 351 | 57% | 45% | -0.04 | -16.2 | -0.94 | 63% |
| SPY | PERSIST | 12 | 372 | 54% | 46% | -0.05 | -19.2 | -1.13 | 42% |
| SPY | REGIME | 12 | 265 | % | 46% | -0.05 | -15.0 | -1.05 | 37% |
| QQQ | VOTER |  | 1030 | 85% | 48% | 0.01 | 10.3 | 0.99 |  |
| QQQ | BASELINE |  | 578 | % | 48% | 0.00 | 0.7 | 0.03 |  |
| QQQ | ORIGINAL | 1 | 254 | 93% | 40% | -0.05 | -12.8 | -0.86 | 12% |
| QQQ | ORIGINAL | 4 | 258 | 88% | 42% | -0.04 | -11.8 | -0.81 | 61% |
| QQQ | ORIGINAL | 12 | 252 | 87% | 41% | -0.06 | -16.0 | -1.07 | 80% |
| QQQ | FIXED | 1 | 319 | 83% | 49% | 0.02 | 6.6 | 0.54 | 3% |
| QQQ | FIXED | 4 | 359 | 62% | 47% | -0.04 | -15.5 | -1.06 | 29% |
| QQQ | FIXED | 12 | 336 | 55% | 47% | -0.03 | -11.6 | -0.79 | 57% |
| QQQ | PERSIST | 12 | 341 | 55% | 46% | 0.00 | 0.1 | 0.01 | 50% |
| QQQ | REGIME | 12 | 305 | % | 45% | -0.03 | -9.4 | -0.66 | 34% |
| IWM | VOTER |  | 1093 | 84% | 46% | 0.00 | -3.1 | -0.30 |  |
| IWM | BASELINE |  | 589 | % | 46% | -0.02 | -14.8 | -0.74 |  |
| IWM | ORIGINAL | 1 | 278 | 92% | 44% | 0.00 | -0.5 | -0.03 | 5% |
| IWM | ORIGINAL | 4 | 242 | 89% | 44% | -0.05 | -12.1 | -0.92 | 54% |
| IWM | ORIGINAL | 12 | 179 | 89% | 46% | -0.04 | -7.6 | -0.60 | 78% |
| IWM | FIXED | 1 | 338 | 82% | 47% | 0.02 | 6.1 | 0.37 | 5% |
| IWM | FIXED | 4 | 298 | 63% | 48% | 0.02 | 3.2 | 0.23 | 32% |
| IWM | FIXED | 12 | 336 | 57% | 47% | 0.01 | 1.4 | 0.09 | 54% |
| IWM | PERSIST | 12 | 351 | 56% | 47% | 0.04 | 12.5 | 0.86 | 45% |
| IWM | REGIME | 12 | 285 | % | 40% | -0.09 | -27.9 | -2.05 | 37% |