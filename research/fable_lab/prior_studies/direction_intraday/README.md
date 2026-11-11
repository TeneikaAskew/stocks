# Was the 08:30 brief's direction right at any point in the day?

Research only (stocks repo, read only). Built Nov 11 2026.

## Question

The brief's CALL/PUT direction was right 209 of 448 times (46.7%) on the holdout (Mar 3 2025 to Apr 30 2026) when "right" means the close finished beyond the prior close in the call's direction. Was the call right at some point during the session, or only wrong at the close? If price reached a level in the call's direction at any point, could that still be tradable?

## Data and method

* Calls: the replayed 08:30 brief (main code, 08:30 cutoff) for every session Mar 3 2025 to Nov 10 2026: 427 sessions, 1,281 ticker sessions, 658 CALL or PUT calls (448 holdout, 210 in sample May 1 to Nov 10 2026). Same rows the earlier scoring used (`hscore.py`); the 209 of 448 figure reproduces exactly.
* Prices: 1 minute bars, unadjusted, regular session 09:30 to 15:59 ET. Half day sessions are kept as the earlier scoring kept them (bars after the early close are extended hours prints, for example Dec 24 2025).
* ATR: the ATR the replay row carries (`level_basis.atr`, else `atr14`). Every row with a call had one.
* From the 09:30 open, for each ticker session and each direction: max favorable excursion (MFE) and max adverse excursion (MAE) in ATR, the time of each, whether price reached 0.25, 0.5 and 1.0 ATR in that direction before 16:00, whether it got there before reaching the same distance the other way (same minute counted as not first; no ties occurred), close vs prior close and close vs open.
* Baselines on the same 658 ticker sessions: the opposite of the brief's call, a fair coin (average of both directions), and always CALL.
* Trigger test: did price touch the brief's own trigger in the call direction (`calls_trigger_price` for CALL, `puts_trigger_price` for PUT), and the trade from that touch using the same rule as `hscore.py` (`week_summary.trade`: fill at trigger or open if already through, exit at stop, T1, or the 15:59 close; stop wins a same bar tie).
* 90% intervals are day clustered bootstraps (the three tickers on one day are not independent).
* The rows do not mark 8:30 economic releases (the replay stubs the catalyst feed). As a stand in, `shock proxy` marks the top third of days by SPY 08:30 to 08:44 range relative to its 07:00 to 08:29 range.

## Headline (all 658 calls, Mar 2025 to Nov 2026)

| Measure | Brief | Opposite of brief | Coin flip | Always CALL |
|---|---|---|---|---|
| Reached 0.25 ATR in call direction | 63.5% | 61.2% | 62.4% | 63.5% |
| Reached 0.5 ATR | 34.7% | 32.1% | 33.4% | 31.8% |
| Reached 1.0 ATR | 10.5% | 6.8% | 8.7% | 7.1% |
| Reached 0.5 ATR before 0.5 against | 33.1% | 30.7% | 31.9% | 30.2% |
| Close beyond prior close | 50.5% | 49.5% | 50.0% | 56.2% |
| Median MFE / MAE (ATR) | 0.38 / 0.33 | 0.33 / 0.38 | 0.35 / 0.35 | 0.35 / 0.34 |

Holdout only (448 calls, the honest test):

| Measure | Brief | Opposite | Always CALL |
|---|---|---|---|
| Reached 0.25 ATR | 60.0% | 63.6% | 64.5% |
| Reached 0.5 ATR | 33.3% | 35.0% | 32.8% |
| Reached 1.0 ATR | 10.0% | 7.4% | 7.6% |
| 0.5 ATR before 0.5 against | 31.7% | 33.7% | 31.0% |
| Close beyond prior close | 46.7% | 53.3% | 56.5% |
| Close beyond open | 45.8% | 54.2% | 53.3% |

Brief minus opposite on the holdout, 90% interval: reached 0.5 ATR -1.8 points [-9.6, +6.0]; 0.5 first -2.0 [-9.7, +5.7]; 1.0 ATR +2.7 [-1.1, +6.9]; close -6.7 [-17.4, +4.0]. Brief minus always CALL on close: -9.8 points [-17.5, -1.3].

In sample (210 calls, the window the brief was tuned on) the brief does separate: 0.5 ATR reached 37.6% vs 25.7% opposite, close right 58.6%. That did not carry over to the holdout.

## Reading it

* "Right at some point in the day" is mostly volatility. Price reaches 0.25 ATR from the open in a random direction 62% of the time and 0.5 ATR 33% of the time. The brief's call reaches those distances at the same rate as its opposite (holdout: slightly less often).
* Why 46.7% is "no edge": a coin scores 50% and always CALL scored 56.5% on the same holdout sessions, because the market rose. The brief leaned PUT (60% of holdout calls) in a rising market. The average close move in the call direction was -0.058 ATR on the holdout, so there was nothing to harvest.
* The close vs prior close score is driven by the overnight gap. On the holdout, when the call agreed with the 09:30 gap it was right at the close 66.8% of the time (208 calls); against the gap, 29.2% (240 calls). The brief called against the gap 54% of the time.
* The one hint: reaching a full 1.0 ATR in the call direction (10.0% vs 7.4% opposite on holdout). The interval includes zero; treat as a lead to test, not an edge.
* When it does go the right way it is slow: median time of the first 0.5 ATR favorable move is 10:56; only 17% happen by 10:00, 41% by 10:30.

## Trigger level test ("if it hits a level")

| Side | Calls with a trigger | Touched in RTH | Already through at open | Trades | Win % | Total R | Avg R |
|---|---|---|---|---|---|---|---|
| Call side | 657 | 418 (63.6%) | 73 | 418 | 59.3% | -21.28 | -0.051 |
| Opposite side | 658 | 429 (65.2%) | 82 | 429 | 63.6% | +3.29 | +0.008 |
| No signal days, calls trigger | 578 | 402 (69.6%) | 82 | 402 | 58.5% | -24.11 | -0.060 |
| No signal days, puts trigger | 577 | 361 (62.6%) | 62 | 361 | 59.0% | -11.49 | -0.032 |

The call side trigger is touched about as often as the opposite trigger. The 59% win rate hides losses: the median T1 sits 0.6 R from entry, so the average win is +0.43 R against an average loss of -0.76 R (110 full stops, 219 T1 exits, 89 exits at the close). Holdout: call side -14.43 R on 279 trades, opposite side +10.38 R on 307. In sample: -6.85 R and -7.09 R.

## Splits (brief vs opposite, all calls, reached 0.5 ATR / close right)

* Ticker: SPY 35.7% vs 30.4%, close 50.2%. QQQ 35.5% vs 28.4%, close 52.1%. IWM 32.9% vs 36.7%, close 49.2% (IWM is the weakest; fading IWM triggers made +31.84 R on 167 trades, likely noise).
* Strength: 2/5 34.3% vs 35.0%; 3/5 35.6% vs 29.3%; 4/5 34.0% vs 20.8% (n=53).
* Shock proxy days: 36.6% vs 28.7%, close 48.1%; other days 33.7% vs 33.7%, close 51.6%.
* By month: see `summary.json` (`by_month`). Holdout months range from 7.5% (May 2025) to 51.6% (Aug 2025) reaching 0.5 ATR; no stable pattern.

## Why about 20 months and not full years

The 1 minute bars this test needs start in March 2025, so intraday tests cover Mar 2025 to Nov 10 2026 (in sample May to Nov 2026 is about 6 months; the holdout is the 14 months before it). The daily only direction tests went back to 2015 (`expc/signals.txt` in the scratchpad) and also found no daily signal beating always long out of sample.

## Example charts

* `ex1_2025-10-31_SPY_put_wrong_at_close_right_intraday.png`: PUT on a +0.74 ATR gap up. Fell 0.83 ATR from the open, closed 0.44 ATR below the open, but above the prior close, so it scores wrong. The puts trigger touched at 09:33 and the trade reached T1 for +2.47 R.
* `ex2_2026-06-10_QQQ_call_right_early_then_reversed.png`: CALL, reached +0.5 ATR at 09:48, then sold off and closed 0.99 ATR below the prior close; trigger trade stopped for -1.00 R.
* `ex3_2025-08-22_SPY_call_clearly_right.png`: CALL, +1.67 ATR best move, closed +1.86 ATR vs prior close. The trigger trade still made only +0.10 R because T1 sat 0.37 points above the trigger.
* `ex4_2025-08-01_SPY_call_clearly_wrong.png`: CALL on a day that opened 1.16 ATR below the prior close; never got more than 0.01 ATR above the open, closed 2.07 ATR wrong. The calls trigger was never reached, so no trade.

Premarket candles in the charts have isolated bad prints clipped to within 0.3 ATR of the 15 minute median close (the raw feed has stale prints at the prior close). Stats use regular session bars and are not clipped.

## Files

* `analyze.py`: builds the stats. `charts.py`: draws the examples.
* `session_stats.csv`: one row per call (658 rows): call, ATR, open, close, prior close, both directions' MFE and first hit times, call direction view (`call_*` columns), trigger touch, trigger trade R.
* `summary.json`: every table above plus month, window, side and strength splits.
