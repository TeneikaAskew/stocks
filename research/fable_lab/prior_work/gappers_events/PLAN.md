# gappers_events lane: plan (written 2026-11-11, before any run)

Owner's ask: "I do this as a human, checking if there was a large gap and probability. I want that
incorporated and in the brief too." and "For the 9:20, did we experiment with how it works on report days?
... Levels, next levels? I'm not convinced there is nothing we can do on these days."

## Words used
- Gap = 09:30 open minus the prior regular-session close. "Indicated gap" = last premarket price before the
  brief's cutoff (08:30 or 09:20) minus prior close; this is the only gap the brief can know when it runs.
- ATR = the ticker's own 14 day average true range known before the session (same value the brief row carries).
- Gap fill = price trades back to the prior close during the regular session.
- R = profit in units of the trade's risk (entry to stop). Range = 90% bootstrap interval resampling whole
  days (the three tickers on one day move together). If the range crosses zero it may be luck.
- Primary window 2026-05-01 to 2026-11-10 (the window the brief was tuned on). Holdout 2025-03-03 to
  2026-04-30. Long daily check 2010-01-04 to 2025-02-28 (daily bars only, gap/fill/close base rates).
  The data lane's longer 1 minute history is used if fable_lab/data/STATUS.md says it is ready when I finish.

## A warning to test first (H0)
The "139 of 208 vs 70 of 240" score counts a call as right when the close is beyond the PRIOR close.
The gap itself is already part of that move, so a gap in the call's direction is a head start.
H0: measured from the 09:30 open (close vs open), calls with the gap are not right more often than calls
against it. If H0 holds, the gap is information about where price already is, not about where it goes next,
and the brief should use it for levels and targets rather than as a direction signal.

## Hypotheses (each falsifiable, tested separately on both windows, per ticker and combined)
Experiment 1, base rates
- H1a Small gaps (under 0.25 ATR) fill the same day more than 60% of the time; large gaps (over 0.75 ATR) fill
  less than 35% of the time. Bucket by |gap|/ATR and by gap %.
- H1b Gaps that open outside the prior day's range (above high / below low) fill less often and continue more
  often than gaps that open inside it.
- H1c After a gap, the first 15/30/60 minutes move in the gap direction more than 50% of the time (continuation),
  or less (fade). Split by size bucket.
- H1d Price reaches the next ladder level in the gap direction (first brief level beyond the open, at least
  0.1 ATR away) before filling the gap more often for large gaps than small ones.
- H1e High premarket volume (over 1.5x the ticker's own 20 day median premarket volume) lowers the fill rate.
- H1f A premarket trend in the gap direction (08:30 to 09:29 move with the gap) lowers the fill rate.
- H1g The gap known at 08:29 has the same sign as the 09:30 gap at least 85% of the time when |gap| >= 0.25 ATR.
Experiment 2, ways into the brief (scored with the brief's own trigger/stop/T1 and with ladder targets)
- H2a Direction override: taking the gap direction when |gap| >= X ATR beats the brief's own call, scored
  from the open (close vs open, 0.5 ATR first) and on the brief's own trigger trades in R.
- H2b Confidence modifier: brief trigger trades taken with the gap earn more R per trade than against the gap.
- H2c Gap-fill target: when the trigger on the fill side is hit, using the prior close as the target earns
  more R than the brief's T1.
- H2d Skip gap-against days: dropping trigger trades whose direction is against the gap (|gap| >= X ATR)
  raises total R.
- H2e Gap-and-go / gap-fade keyed on the first 5 or 15 minutes: if the first bar closes in the gap direction,
  go with the gap (stop = other end of that bar, target = next ladder level or 2R); if it closes against,
  fade to the prior close (target = fill). Each beats zero R and beats trading every gap blindly.
Experiment 3, report days
- H3a On report days (CPI, jobs, PCE, FOMC; second tier PPI, retail sales, GDP) the 08:30 brief's trigger
  trades do worse than on normal days, because its premarket high/low were set before the release.
- H3b The 09:20 rerun fixes this: on report days 09:20 triggers earn more R than 08:30 triggers; on normal
  days the two are the same within the range.
- H3c A rerun after the open (09:35 or 09:45, opening-range high/low as triggers) beats the 09:20 rerun on
  report days.
- H3d Levels set after the release (high/low of 08:30 to 09:29) work better as triggers on report days than
  the full premarket high/low, under one common exit rule (stop 0.25 ATR, target 0.5 ATR, else close).
Experiment 4, other ideas for these days (stated before testing)
- H4a On 08:30 report days, the release reaction (08:29 to 09:29 move) continues: close vs open has the same
  sign as the reaction more than 55% of the time.
- H4b On FOMC days the morning is dead: range 09:30 to 13:59 in ATR is smaller than on normal days, and
  morning trigger trades lose; a trade keyed on the 14:00 to 14:30 range break does better.
- H4c "No new triggers after 10:00" (the one earlier rule that held) also holds on report days.
- H4d Triggers that sit within 0.1 ATR of a higher-timeframe ladder level (confluence) do better than lone
  premarket levels.

## Data
- 1 minute bars, extended hours: /mnt/project-files/stocks-scorecard/inputs/bars_raw/{T}_1min_YYYY-MM.csv
- Daily bars: /mnt/project-files/strat-verify/ftfc-replay/raw/{T}_daily_adjusted.csv (unadjusted OHLC columns)
- Brief replays (brief's own code, main, cutoffs 08:30 and 09:20), one JSON per session, made by the STRAT
  thread with tools/replay_day.py: <scratch>/hist/{oos,out}/main0830_*.json and main0920_*.json. I copy the
  fields I use into this lane (brief_rows.csv) so a rerun does not depend on the scratch folder.
- New replays at 09:35 and 09:45 from my own worktree of origin/main if the replay tool supports a cutoff
  after the open; otherwise the opening range is modelled directly from the 1 minute bars and labelled so.
- Report calendar: built from the agencies' published schedules (BLS, BEA, Federal Reserve); source and
  fetch date recorded in calendar/SOURCES.md; each 08:30 date is cross-checked against the 08:30 volume
  spike in SPY premarket bars.

## Method
1. code/build_days.py: one row per ticker session (gap features, premarket features, outcomes). -> days.csv
2. code/exp1_base_rates.py: tables for H0, H1a to H1g. code/exp1_daily_long.py: long daily check.
3. code/exp2_brief_rules.py: H2a to H2e in R with day-clustered bootstrap ranges.
4. code/exp3_report_days.py: H3a to H3d, H4a to H4d.
5. code/charts.py: example-day charts.
All results appended to results.csv (experiment, hypothesis, variant, window, ticker, n, value, lo, hi).

## Success test (same for every hypothesis)
A rule "works" only if (1) it has the same sign on primary and holdout, (2) the holdout range excludes zero
(or excludes the baseline it claims to beat), and (3) it is not carried by one ticker (at least two of three
tickers agree in sign on the holdout). Thresholds are picked on the primary window only and then read on the
holdout untouched. Anything less is reported as "not proven" or "did not work".

## What would change the brief / Insights
Only rules that pass the test go into the recommendation, with the exact value in ATR units per ticker.
Base-rate tables that are stable on both windows can be shown as probabilities in the brief even when no
trading rule passes (that is what the owner does by eye).

## Limits
No pushes, no PRs, no production access, no paid calls. I never message the owner.
