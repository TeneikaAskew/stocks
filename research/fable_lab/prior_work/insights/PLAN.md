# Insights lane: plan (written 2026-11-11, before any run)

Owner's ask (Nov 11): Insights should follow the same systems as the brief; review it, experiment, and do
not swap Gemini out for Claude. This lane tests the rule side of Insights on local bars. No production
access, no paid model calls, no pushes.

## What is being tested

The Insight report has two halves:
* **Model decided** (Gemini 3.1 flash lite, 14 calls): direction (long, short, flat), the prose, risk flags,
  confidence score. This cannot be replayed here without paying for model calls.
* **Rule decided** (plain code): which level is the trigger, the entry zone, the stop, the targets and the
  size for each of the three personas (aggressive, neutral, conservative), and the conviction label.

This lane rebuilds the rule half for every session in the local 1 minute bars and scores it. For the model
half it uses stand-ins for direction (the 08:30 brief's call, the gap, both sides) and the 30 stored model
calls from the earlier study.

## Hypotheses (each can fail)

* H1 Persona ranking. Conservative beats neutral beats aggressive in R per trade on the day rule, in both
  windows. Fails if the order changes between windows or every range crosses zero.
* H2 Aggressive on a day hold. Aggressive's 2R first target (4 ATR away) is reached on fewer than 5% of
  filled day trades, so on a day hold it is just "hold to the close with a wide stop".
* H3 Per ticker multiples. Stop and first target multiples picked per ticker on the primary window beat one
  shared set of multiples on the holdout. Fails if the per ticker pick does not beat the shared pick out of
  sample (range above zero).
* H4 Ladder targets. Taking profit at the next ladder level beyond the trigger (instead of a fixed R
  multiple) raises total R in both windows. Fails if the difference range crosses zero or flips sign.
* H5 Gap rule. Trades whose direction agrees with the premarket gap do better than trades against it, in
  both windows; and skipping trades against the gap raises total R.
* H6 Direction source. The brief's call adds R over its opposite and over "take whichever side triggers
  first". Fails if brief minus opposite has a range that crosses zero in the holdout.
* H7 Persona stop and target multiples. Some stop and first target pair beats production's (1 ATR, 1R) for
  the neutral plan in the primary window and still beats it in the holdout.
* H8 Entry cut off. No new fills after 10:00 ET (the one earlier rule that held) also helps the persona
  plans in both windows.
* H9 Conservative's stand aside gate (FTFC below 0.30 in the trade direction, or a long under the 200 day
  average). Gated out trades do worse than the ones it lets through. Fails if skipped trades do as well.

## Data

* 1 minute bars, extended hours, `/mnt/project-files/stocks-scorecard/inputs/bars_raw/{SPY,QQQ,IWM}_1min_*.csv`.
* Daily bars as traded (not dividend adjusted): `/mnt/project-files/strat-verify/ftfc-replay/raw/*_daily_adjusted.csv`
  through Nov 4 2026, later days built from the 1 minute regular session bars.
* Brief direction per session: `research/direction_intraday/session_stats.csv` (658 calls).
* Stored model direction: `research/insights/persona_outcomes.csv` (30 ticker days).
* Windows: primary 2026-05-01 to 2026-11-10 (tune here), holdout 2025-03-03 to 2026-04-30 (test here).
  Note the holdout is the earlier period; nothing in the holdout is used to pick a value.

## Method

1. Worktree of origin/main. For each ticker and session call the production code itself:
   `lib.indicators.calculate_premarket_context` (premarket bars 04:00 to 08:20, the time the premarket
   refresh job writes), `lib.strat_levels.build_session_levels`, `lib.strat.compute_strat_status` (FTFC),
   `lib.agents.trade_planner.compute_persona_plans`, for both long and short. ATR is the prior session's
   ATR(14) of that ticker.
2. Save the ingredients (trigger, the next ladder levels, the stop anchor, ATR, gap, FTFC, 200 day average)
   so variants can be recomputed; check my recomputed baseline equals the production planner to the cent.
3. Score with the earlier study's rule: fill when a regular session bar touches the entry zone; stop
   checked before target inside one bar; day rule exits at the 15:59 close; swing rule holds up to 5
   sessions. R = profit in units of the trade's own risk (fill to stop).
4. Each experiment changes one thing against the baseline. Report trades, win rate, total R, R per trade,
   and a 90% range from a bootstrap by day (2,000 resamples). If the range crosses zero it may be luck.
5. Pick values on the primary window only; then report the same pick on the holdout.

## Variants

* E0 baseline: production personas, both sides, day and swing rules, by ticker.
* E1 per ticker multiples: grid of stop (0.35, 0.5, 0.7, 1.0, 1.5, 2.0 ATR) and first target (0.5R, 1R,
  1.5R, 2R, 3R, none) per ticker vs shared.
* E2 ladder targets: T1 = next ladder level past the entry; variants with a minimum distance (0.25 or 0.5 of
  the ticker's ATR, skip to the next level if closer), fall back to the R target when no level exists.
* E3 gap rule: with the gap, against the gap, small gap; gap measured in the ticker's own ATR.
* E4 direction: brief, opposite of brief, gap direction, FTFC sign, always long, both sides, first side to
  trigger; stored model calls on the 30 ticker days.
* E5 persona multiples: the shared grid from E1.
* E6 entry cut off at 10:00, 10:30, 11:00.
* E7 conservative gate: gated vs allowed trades.

## Success test

A change is "held out of sample" only if it is better than baseline in the primary window, the same sign in
the holdout, and the holdout 90% range of the difference is above zero. "Same sign but range crosses zero"
is reported as "leans, not proven". Anything else is "did not hold".

## What would change Insights

Results feed a list of recommended changes, each marked tested and held, tested and did not hold, or
untested (needs production data or model calls). Production data needs go into `needs_gcp.sql` as read only
SELECTs for the owner's GCP session.

## Not in scope

Changing the model, calling any model, writing to production, editing the repo checkout, opening PRs.
