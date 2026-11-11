# level_hits lane: PLAN (written 2026-11-11, before any result)

## Question (owner, Nov 11)
Not "was the call right at some point" but: did price cross the level the brief said makes it a call (or put),
stay beyond it for 5 minutes or more, and then reach the brief's targets? And in Rob Smith's The Strat terms:
is price tapping the timeframe levels (prior day, 12HR, prior week), and does timeframe continuity line up when it does?

## Hypotheses (each can fail)
H1. The brief's called side crosses its trigger and holds 5+ minutes more often than the opposite side. Fails if the
    range of (call side minus opposite side) crosses zero on the holdout.
H2. After a 5 minute hold, the called side reaches T1 (and T2, T3) before its stop more often than the opposite side.
    Same failure test.
H3. A 5 minute hold filters out fakeouts: trades entered after the hold do better (R per trade) than trades entered on
    the first touch. Fails if the range of the difference crosses zero.
H4. Taps of timeframe levels (prior day high/low, 12HR high/low/50%, prior week high/low) follow through more often
    when timeframe continuity (day, week, month, quarter all the same colour) agrees with the tap direction.
H5. Taps and trigger holds that start after 10:00 follow through less often than those before 10:00.
H6. Report days (CPI, jobs, FOMC, PCE) behave differently from other days on H1, H2 (two sided; no direction assumed).

## Data
- Brief replay: gcp/premarket_brief.py + lib/strat_levels.py at origin/main, my own worktree, 08:30 ET cutoff,
  every session 2025-03-03 to 2026-11-10, SPY QQQ IWM (code/replay_day.py, the same replay tool the earlier
  direction_intraday study used; code/run_replay.py drives it). Gives call (CALL/PUT/none), both sides' trigger,
  stop, T1, T2, T3 and the ladder.
- Prices: Alpha Vantage 1 min bars, /mnt/project-files/stocks-scorecard/inputs/bars_raw. Regular session
  09:30 to 15:59 for all tests. Sessions with under 300 regular bars (half days) dropped, as before.
- Windows: primary (in sample) 2026-05-01 to 2026-11-10; holdout 2025-03-03 to 2026-04-30. Longer history only if
  fable_lab/data/STATUS.md exists when the run finishes.
- Report day calendar: code/report_days.csv (CPI, jobs report, FOMC decision, PCE), source noted in the file.

## Method
For each ticker day and each side (calls and puts), from 1 min regular session bars:
1. Touch: first bar whose high (low for puts) reaches the trigger. Hold N (N = 1, 5, 15, 30): first run of N
   consecutive 1 min closes beyond the trigger. Time = first bar of the run; "confirmed" = last bar of the run.
   Strict variant: N consecutive bars whose whole range is beyond the trigger.
2. After the 5 minute hold starts: did price reach T1, T2, T3 and the next ladder rung later that day; minutes
   to each; was the brief's stop touched first. Targets already passed at the open are flagged.
3. Trade view: enter at the close of the bar that confirms the hold, risk = entry to the brief's stop, exit at
   stop, target k, or the 15:59 close. Compared with entering on first touch (earlier study's rule).
4. Called side vs opposite side on the same ticker days; no call days reported separately.
5. Strat levels: prior day high/low, prior week high/low, 12HR candle high/low/50% (two definitions: the overnight
   candle 16:00 to 04:00 before the session, which is what the other trader posts, and the prior 04:00 to 16:00
   candle; extended hours wicks cleaned). Tap = regular session price trades through the level. After a tap:
   held 5 minutes beyond it; followed through 0.25 x the ticker's ATR beyond it before coming back 0.25 ATR inside;
   closed the day beyond it. Continuity at the tap = price vs the day, week, month and quarter opens.
   Splits: continuity aligned or not; tap before or after 10:00.
6. Report days vs other days.
All distances are in units of each ticker's own ATR (the ATR the brief row carries). No fixed dollar numbers.

## Statistics
Rates with 90% ranges from a bootstrap that resamples whole days (the three tickers on one day move together).
Differences (call side minus opposite, aligned minus not, before minus after 10:00) with the same ranges.
"If the range crosses zero, it may be luck."

## Success test
A finding counts only if it has the same sign in the primary window and the holdout and the holdout range does not
cross zero. Everything else is reported as "not shown".

## What would change the brief
- If the 5 minute hold improves trigger trades (H3): hypothesis for triggers_levels: require a hold before entry.
- If T1 is usually reached inside the hold or within minutes: T1 is too close to be a target; use T2 or an ATR floor.
- If continuity or the 10:00 split separates good taps from bad (H4, H5): hypothesis: gate triggers on them.
- If the opposite side delivers as often as the called side (H1, H2 fail): the brief should present both sides as
  conditional plans and stop presenting one as "the call".

## Deliverables
README.md (plain language, worked example days with charts), results.csv (one row per ticker day),
taps.csv (one row per level tap), summary.json, code/, exact commands.
