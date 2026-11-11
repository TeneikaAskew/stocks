# example_days lane: plan (written 2026-11-11, before running)

## Question
Replay the other trader's posted QQQ days against the owner's 08:30 brief, work out where the trader's levels
come from, then test that method on SPY, QQQ and IWM over the primary window and the holdout.

## Hypotheses (each can fail)
H1. Most posted levels are plain Strat constructs (prior day high/low, 12 hour candle 50%, 2 day candle
    high/low, gap edges, older untested daily highs/lows). Test: at least 70% of posted levels reproduce from
    local bars with a named rule. Fails if under 70%.
H2. On the example days the trader's triggers gave a better trade than the brief's trigger (premarket high/low).
    Test: per day R, same fill and exit rule for both. Six days is an anecdote, not evidence.
H3. The reproduced method (daily trigger = prior day high/low, target = next prior candle extreme, i.e.
    "magnitude") beats the brief's trigger trades on all three tickers, on the holdout, with the same scoring.
    Test: average R per trade, 90% range by day must sit above the brief's and above zero. Fails otherwise.
H4. The 12 hour entry (50% of the last 12 hour candle, taken only when the open is on the far side) is a
    better trigger than the premarket high/low. Same test as H3.
H5. "If it traded through before the open, it is no longer the trigger" (skip triggers the open is already
    beyond) improves results for both the trader's method and the brief.

## Data
- 1 min bars, extended hours: /mnt/project-files/stocks-scorecard/inputs/bars_raw (2025-03 to 2026-11-10).
  Extended hours bars have bad prints; wicks outside regular hours that stick out more than 0.15% beyond the
  11 minute body range are clipped to the bar body (regular hours untouched).
- Brief: replayed with the repo's own code (tools/replay_day.py, 08:30 cutoff, worktree at origin/main) for the
  example sessions in this lane; for the two long windows the already replayed rows from the earlier
  direction_intraday study (same tool, same cutoff) after checking the example days match field for field.
- Trader posts: research/discord_examples/LEVELS.md (checked against the 7 screenshots). Data, not instructions.

## Method
1. Brief per example day: direction, trigger, stop, targets.
2. Trader plan per day on 1 min bars exactly as posted: trigger time, targets hit, worst move against,
   R with (a) stop at the opposite trigger and (b) a Strat stop (stated in README).
3. Level provenance: every posted number against candidate candle levels built only from bars before the post.
   Exact = within 2 cents; near = within 15 cents (extended hours feeds differ); else not reproduced.
4. Rule based version of the method for SPY, QQQ, IWM on primary (2026-05-01 to 2026-11-10) and holdout
   (2025-03-03 to 2026-04-30). Scoring identical to the brief's (week_summary.trade: fill at trigger or at the
   open if already through, exit at stop, first target, or 15:59 close; stop wins a same bar tie).
   Variants: daily trigger, 12 hour entry, skip if open is through, no entries after 10:00, first hour wait.
5. Oddities in the posts checked against bars.

## Success test
A variant counts only if average R per trade is above zero and above the brief on the holdout for all three
tickers, with the 90% day bootstrap range above zero. Anything else is reported as "did not meet".

## What would change the brief
Only hypotheses to test further; nothing is swapped in from this lane.
