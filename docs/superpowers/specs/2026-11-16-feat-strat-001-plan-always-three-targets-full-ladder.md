---
feat_id: FEAT-STRAT-001
req_ids: [REQ-PLAYBOOK-001, REQ-DATA-001, REQ-REL-001]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01]
done_when:
  - "Policy and calibration: gcp/schema.sql seeds five new level_param_policy rows, each effective 2015-01-02 with ON CONFLICT DO NOTHING and each reproducing today's plan: target_merge_atr (method_id policy_seed, extra {\"seed\": 0.0}), target_fill_sources (policy, extra {\"sources\": []}), target_fill_reach_long_atr and target_fill_reach_short_atr (daily_excursion_quantile, statistic_q 1.0, lookback_sessions 750, min_sample 250, extra side long and short) and ladder_history_sessions (policy, extra {\"sessions\": 250}); no existing row changes; lib/strat_levels.py names each key once, target_merge_atr joins POLICY_SEEDED_KEYS and target_fill_sources and ladder_history_sessions join POLICY_WIDE_KEYS; policy_wide_param gives target_fill_sources status ok with value equal to the number of listed steps when every step is one of level_beyond_window, atr_rung_beyond, atr_rung_between and none repeats (ok with value 0 for an empty list) and input_unavailable for a missing list, an unknown step or a repeat, and gives ladder_history_sessions ok for a whole number of at least 1 and input_unavailable otherwise; lib.level_calibration.calibrate and HistoryCalibrator write, per ticker, target_merge_atr at the seed in force and the two reach keys as the largest daily excursion of the lookback in ATR (the trigger window's own samples, quantile 1.0), with insufficient_history under min_sample; tests in tests/lib/test_level_params_loader.py and tests/lib/test_level_calibration.py assert all of it on the seeded policy loaded from gcp/schema.sql, and that a reach value is never below the same side's trigger window computed from the same samples; they fail on origin/main, which has none of the keys"
  - "Zones: tests/lib/test_strat_levels.py passes a TestTargetZones class on the three stored 2026-11-16 bases (Design 8 fixtures) rebuilt with target_merge_atr 0.10, no fill and the marker: IWM calls give one zone 279.17 to 279.33 (PDH, PMC) that is too close (its far edge is 41 cents past the trigger, spacing 122) and targets 283.79, 285.26; IWM puts give T1 as the zone 274.67 to 274.55 (PDL, 11/9 Gap Low) priced 274.67 (far edge 131 cents past the trigger, at least the 122 spacing; on origin/main T1 is 274.55 and 274.67 is skipped) and T2 269.88; SPY calls give T1 760.12 and T2 as the zone 762.63 to 763.04 (PQC, PWH) priced 762.63 (on origin/main T2 is 763.04); QQQ puts give T1 as the zone 662.02 to 661.14 (PWL, PQL) priced 662.02 and T2 637.01; at 0.10 QQQ calls keep T1 688.75 with 690.49 too close, and at 0.15 T1 is the zone 688.75 to 690.49 (PDH, PMC) priced 688.75; a level exactly the merge distance in cents from the zone's nearest level joins and one cent more does not; a zone is never wider than the merge distance; the next target is measured from the zone's far edge; with target_merge_atr 0.0 every case equals origin/main's targets and skipped list; a target_merge_atr at or above the ticker's target_min_spacing_atr, or not ok, publishes no target with target_status input_unavailable or that status; each zone target records price (the nearest edge), name (the nearest level's) and zone (far_price and every member's name and price); the cases at 0.10 and 0.15 fail on origin/main"
  - "Always three targets: tests/lib/test_strat_levels.py passes a TestTargetFill class on the same bases with both reach keys 3.0 and target_merge_atr 0.0: with target_fill_sources [level_beyond_window] SPY calls T3 is 779.37 (PQH, source level_beyond_window), QQQ calls T3 is 711.62 (GAP_H_2026-10-30), and IWM calls and puts, SPY puts and QQQ puts keep two targets with fill_status no_candidate_in_reach; with [atr_rung_beyond, atr_rung_between] IWM calls T3 is 286.48 (PDH+1.5ATR, exactly the 122 cent spacing past 285.26, equal kept), IWM puts T3 268.55 (PMK_L-1.5ATR), SPY calls T3 769.95 (PDL+2ATR), SPY puts T3 725.88 (PMK_L-2ATR), QQQ calls T3 700.98 (PMK_L+2ATR), and QQQ puts, which have no rung past 637.01 in reach, take the between step: targets 662.02, 647.17 (PDL-1.5ATR, the farthest kept rung between at least the spacing from the trigger and from both neighbours), 637.01, numbered in price order; with the three steps in the order level_beyond_window, atr_rung_beyond, atr_rung_between SPY calls T3 is 779.37 and IWM calls T3 is 286.48; a level or rung farther from the reference than the side's reach is never a target (IWM PQH 305.18 at 5.91 x ATR is not); a fill target is always at least the spacing from the trigger and from every other target; every fill target records its source and the in-window level targets are the ones origin/main publishes, in the same order; with atr_rung_status not ok the rung steps add nothing and fill_status says why; with the seeded empty list every side equals origin/main; a reach key that is not ok publishes no target with that status; the fill cases fail on origin/main; and the fill adds more than one target from one step: on a basis written in the test whose calls side has no in-window target and three unbroken levels past the window, each at least the spacing apart and inside the reach, [level_beyond_window] alone gives T1, T2 and T3 from that step in price order; the same side starting with one in-window target takes two; with only one such level past the window the side ends with two targets and fill_status no_candidate_in_reach, never a third from nowhere"
  - "Full ladder: on the same bases each side records plan_ladder, every unbroken candidate and listed plan level type past the trigger and every kept ATR rung past the trigger, within the side's reach, in price order outward, each entry with price, far_price for a zone, names, kind (level or atr_rung), role (t1, t2, t3, too_close or none), in_window, distance_atr from the trigger and strength (the labels of every ATR rung, kept or dropped by thinning, within the ticker's level_cluster_atr x ATR in cents of any of the entry's levels, equal counted): IWM calls 283.79 (PWH) has strength [PMK_H+1, PDH+1], the zone 279.17 to 279.33 has [PDL+1], 285.26 (PMH) has none, and IWM puts 269.88 (PML) has [PDL-1]; a rung entry has no strength; a level beyond the window and inside the reach is listed with in_window false and a level beyond the reach is not listed; the tests fail on origin/main (no plan_ladder)"
  - "Brief copy: tests/lib/test_strat_levels.py passes two golden-string tests on the stored IWM 2026-11-16 basis with the Design 8 reach histories and bias bearish: with the seeded policy the CALLS and PUTS blocks are exactly Design 8's 'Seeded' text (targets and every other line as origin/main prints them for that basis, the Skipped line replaced by the ladder lines), and with target_merge_atr 0.10 and the three fill steps they are exactly Design 8's 'After' text; a side whose reach history is empty prints 'no history yet' on each ladder line and never '0 of 0'; a side short of targets with a non-empty fill list ends its last target line with '(no level or ATR level in reach for a further target)'; the D8_CALLS and D8_PUTS goldens change only in the Skipped line, which becomes the ladder lines of Design 7 for that fixture, and D8_NEXT_LEVELS and D8_ATR_LINE are unchanged; and on a basis written in the test whose fill runs out early, a side with one target prints the hold line for the remaining 2/3 and a side with no target prints it for the whole position, each as origin/main words that count (lib/strat_levels.py:3213) followed by the no-candidate reason, never 'the last 1/3'; the new goldens fail on origin/main"
  - "Stored briefs keep their plan: tests/gcp/test_level_basis.py passes tests on stored bases with no plan_ladder_status key, (a) params that record none of the five keys and (b) params that record them (as the loader records every policy key once the rows exist): each rebuilds through SessionLevels.from_basis with targets, skipped list, target_status and brief text equal to origin/main's for that basis, and the five keys are never checked for it; a basis built on the head records plan_ladder_status and rebuilds the same zones, fill targets and ladder after the policy and ticker rows change; gcp.premarket_playbook_resolver.plan_inputs on each gives the matching target prices (a zone's nearest edge) and plan_available true; LEVEL_RULE_VERSION does not change"
  - "Reach history stored and read: gcp/schema.sql adds nullable calls_plan_mfe_atr and puts_plan_mfe_atr to premarket_analysis; tests/gcp/test_premarket_playbook_resolver.py passes a TestPlanMfe class on synthetic 1-minute bars for a call with trigger 100.00, stop 99.00 and basis ATR 2.00: entered, a high of 103.00 before a later stop gives 1.5; the bar that hits the stop does not count (its high of 104.00 is ignored, stop first); a high reached only on the fill bar does not count; never above the trigger after the fill gives 0.0; a side not entered, or a basis with no ATR, gives NULL; a stop-less entered side is measured to the close; the mirrored put cases pass with trigger 100.00, stop 101.00 and ATR 2.00: a low of 97.00 before a later stop gives 1.5 (the trigger minus the lowest low, never a negative distance floored to 0), the stop bar's low of 96.00 is ignored, a low reached only on the fill bar does not count, and never below the trigger after the fill gives 0.0; on a half day (2025-11-28, close 13:00 ET) a call whose high is 101.00 before 13:00 and 105.00 at 14:30 gives 0.5, since the measure reads the resolver's plan_bars, cut at session_close; resolve_one's UPDATE sets both columns and RESOLVER_VERSION changes; tests/gcp/test_premarket_brief.py passes a test that the brief reads the reach history for all its tickers in one query, bounded to ladder_history_sessions analysis dates before the session date and to rows whose value is not NULL, never a date on or after the session (a BRIEF_AS_OF run sees only earlier rows), and that a failed read raises instead of printing 'no history yet'; the tests fail on origin/main"
  - "No numbers and no names: tests/lib/test_level_params_structure.py passes unchanged (no new literal or module constant on the build_session_levels walk) and test_the_walk_reaches_the_rules_it_must_cover also asserts that the zone walk, the fill walk and the ladder builder are reached from build_session_levels; tests/lib/test_level_params_copy.py asserts that no string literal in lib/strat_levels.py contains '0.1 x ATR', '0.15 x ATR' or '3 x ATR'; the merge distance, the reach, the fill order and the history length are read only from LevelParams and level_param_policy"
  - "Unchanged, each pinned by an existing test that passes on origin/main and on the implementation head: the trigger and stop rule, gate_targets and the t1..t3 columns, the opened-through rule, the entry cutoff, exit_legs and the thirds, the spacing value and its walk between single levels, the gap-edge rule, the ATR rungs and their thinning (TestAtrRungs, and TestAtrRungsDisplayOnly under the seeded empty fill list), the NEXT LEVELS lines and the ATR levels line, PMG zones, the signal monitor's fire decisions and put re-anchor, the movement statement, persona plans, the CALL/PUT pick and the resolver's existing outcome and plan columns"
  - "Experiment through the production paths, before any production change: the implementation PR body shows, for SPY, QQQ and IWM over 2022-01-03 to 2026-11-10 on the gap-edges spec's ticker-days (one trade per ticker-day, the first side to cross its trigger, a same-bar tie is no trade, a day that opens past a trigger is no trade, half days cut at the exchange close, SPY 2025-04-09 and IWM 2026-06-26 left out), plan R from gcp.premarket_playbook_resolver.resolve_plan with inputs from plan_inputs on bases built by gcp/premarket_brief.py (BRIEF_AS_OF) into a local copy of the schema, never production, for the arms of the Experiment section: A today, B level_beyond_window, C atr_rung_beyond then atr_rung_between, D10 and D15 and DC (merge at 0.10, 0.15 and each ticker's level_cluster_atr), and S the Design 9 rows; per arm the total R, per ticker, per six-month block, the 90% day-resampled range of arm minus A (seed 7, 2,000 draws), the hit rate before the stop of T1, T2 and T3, the count of traded sides with fewer than three targets and the count whose targets differ from A; arm A matches the gap-edges spec's +176.8 R over 3,463 trades to 0.1 R; and, once the dry run of docs/superpowers/specs/2026-11-16-feat-playbook-001-brief-says-what-the-data-says.md is on main, arm A's targets for the sample sessions the owner allows, built by the deployed job with BRIEF_NO_PERSIST=true, equal the local build's and the run's level_basis shows the seeded policy rows were the ones read (the deployed job loads its policy from production for the analysis date, gcp/premarket_brief.py:950-980, so it cannot be handed another arm's rows without a production write; the other arms are compared on the local copy only); an arm whose range against A lies wholly below zero overall, or for two of the three tickers, is not proposed, and if no fill arm and no merge arm passes the seeded rows stay and the PR says so"
  - "Source identity (DASHBOARD-01): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-STRAT-001, DASHBOARD-01) note row carries that source_identity_sha256 with implementation and test prose for this PR"
  - "The FEAT-STRAT-001 catalog record and the PR traceability entry are updated; python3 scripts/gate/spec_gate.py --pr origin/main passes; the five seeded rows, the calibration run for the three per-ticker keys and the two new columns are applied to production only after the owner's yes, in the order of the Close-out section, and the Design 9 rows that change the plan are inserted only after a second yes given on the Experiment's results, each recorded separately"
status: approved
supersedes: null
---

# The exit plan always names three targets, close levels are one target, and the brief shows the full ladder

## Authority

T, 2026-11-16, on the brief for 2026-11-16, where SPY, QQQ and IWM each printed two targets a side:

> "Why did we decide to do this vs a t3 level? There should still be a t3 and anything after is a hold to close."

> "The levels are always targets and the ATR levels enhance them (like state if its more powerful/stronger because of ATR)."

Shown the 2026-11-15 experiment results:

> "Yes, keep thirds, show the full ladder, test T3."

> "thirds with t3 and atr insights"

On two levels a few cents apart:

> "This is where I believe atr would help, I would think 1 target. Most cents seem like .10 or .15 atr."

Those words approve the direction, and `status: approved` records that. They do not approve a
production change of the plan: the Experiment below gates it, and the rows that change the plan
(Design 9) are inserted only after the owner's yes on its results.

Rulings still in force: values are never hard-coded and are tailored per ticker through calibration
(2026-11-08); a change is tested against its hypothesis before it is swapped in; R is the stock's move
after the fill measured in stop distances, never money.

The values named here (a merge distance of 0.10 or 0.15, the largest excursion of 750 sessions as the
reach, 250 sessions of history) are this delivery lane's proposals. The merge distances are the owner's
stated intuition, to be calibrated.

Code references are to stocks `main` 060c89a0 (2026-11-16). "Read" means read from the code or a
production row; "derived" means worked out by this spec from a stored row by the rule it states;
anything else says "not checked". Production was read on 2026-11-16 through `scripts/db_query_cr.sh`
without `--commit`.

## How this relates to the three approved specs

It supersedes none of them and edits none. It adds to their walk behind policy rows, as the gap-edges
spec did.

- **Exits in thirds** (`docs/superpowers/specs/2026-11-11-feat-strat-001-brief-exits-in-thirds.md`):
  kept whole. Thirds, the spacing value, the stop, the opened-through rule and the resolver's plan
  scoring do not change. Two of its sentences get a policy-controlled addition: Design 2's "when fewer
  targets pass the spacing, the unassigned legs are held to the close or the stop" (Design 2 and 3 here
  can fill them) and Design 1's "skipped" list (Design 1 here turns close levels into one zone). The
  brief's `Skipped, closer than ...` line is replaced by the ladder (Design 7).
- **ATR levels** (`docs/superpowers/specs/2026-11-11-feat-strat-001-brief-atr-levels.md`): its rungs,
  thinning and line are unchanged. It made rungs display only. Under the seeded rows they still are.
  A rung becomes a target only when `target_fill_sources` lists a rung step, which is a production
  change the owner makes after the Experiment. Its `TestAtrRungsDisplayOnly` keeps passing under the
  seeded rows.
- **Gap edges** (`docs/superpowers/specs/2026-11-15-feat-strat-001-plan-targets-gap-edges.md`): kept
  whole. Gap edges are levels in every rule below, exactly as they are in the spaced walk today.

## Problem

### 1. Two targets a side on 2026-11-16, and the third leg had no price

`_plan_targets` (`lib/strat_levels.py:2821-2890`) walks the side's rungs past the trigger, keeps one
only when it is at least `target_min_spacing_atr` x ATR (seed 0.25, `gcp/schema.sql`
`level_param_policy`) past the trigger or the target before it, and stops at `exit_legs` (3). The rungs
it walks are the side's unbroken candidates inside the side's own window (`_pick_side`,
`lib/strat_levels.py:2721-2818`; the window rule is `_within_staleness_window`, `:889-910`), plus gap
edges in the window. When fewer than three pass, the brief prints "hold the last 1/3 to the close or
the stop" (`_plan_block`, `:3214-3219`).

The stored rows for 2026-11-16 (`premarket_analysis`, `level_basis` built 08:31 ET, rule
`feat-strat-001.v3`; read):

| Side | Trigger | Passed over for the spacing | T1 | T2 | Next level past the window |
|---|---|---|---|---|---|
| IWM calls | 278.92 PMK_H | 279.17 PDH, 279.33 PMC | 283.79 PWH | 285.26 PMH | 305.18 PQH, 5.91 x ATR from the reference |
| IWM puts | 275.86 PMK_L | 274.67 PDL | 274.55 11/9 Gap Low | 269.88 PML | 258.20 PYH, 3.73 x ATR |
| SPY calls | 754.38 PMK_H | 755.72 PMC, 762.63 PQC | 760.12 PDH | 763.04 PWH | 779.37 PQH, 2.64 x ATR |
| SPY puts | 747.95 PMK_L | 747.88 PDL | 741.03 PWL | 729.10 PQL | 691.66 PYH, 5.31 x ATR |
| QQQ calls | 681.02 PMK_H | 683.45 PML, 690.49 PMC, 698.63 10/30 Gap Low | 688.75 PDH | 695.57 PWH | 711.62 10/30 Gap High, 2.42 x ATR |
| QQQ puts | 668.30 PMK_L | 661.14 PQL | 662.02 PWL | 637.01 PYH | 614.31 PYC, 3.54 x ATR |

ATR(14): IWM 4.87, SPY 11.04, QQQ 16.34. Windows in ATR, long and short: IWM 2.17 and 2.27, SPY 1.99
and 2.77, QQQ 1.89 and 2.47. All six sides have two targets and no third.

The window that removes the third target was never tested. It is the 0.99 quantile of the ticker's
daily excursion from the prior close over 750 sessions (`level_param_policy` rows
`trigger_window_long_atr` and `trigger_window_short_atr`, method `daily_excursion_quantile`; read), a
rule made for triggers and reused for targets.

### 2. Two levels a few cents apart are printed as two things

IWM calls: 279.17 (PDH) and 279.33 (PMC) are 16 cents apart, 0.03 x ATR, and print as two skipped
levels. IWM puts: 274.67 (PDL) is 119 cents past the trigger and skipped by 3 cents, while 274.55
(11/9 Gap Low), 12 cents farther, is T1. SPY calls: 762.63 (PQC) is skipped and 763.04 (PWH), 41 cents
on, is T2. A trader reads each pair as one place.

### 3. The brief does not show the whole ladder

The plan block lists up to three targets and a skipped line; NEXT LEVELS lists the trigger and one rung
(`_format_next_levels`, `:3230-3256`); the ATR levels sit on a separate line with no link to the levels
they land on. On IWM the rung PMK_H+1 is on PWH's own cent, 283.79, and the brief does not say so: the
thinning drops it as `structural` and records it only in `atr_rungs_dropped` (read from the stored
basis).

### 4. No stored outcome can give a rung its hit rate

What the resolver stores per side (`gcp/schema.sql:1928-2004`, read): `{side}_trigger_hit_ts`,
`{side}_t1_hit_ts` to `_t3_hit_ts` for the gate targets, `{side}_mfe_pct` (the farthest price after the
trigger over the rest of the session, whether or not the stop was hit first), and the plan columns
`{side}_plan_entry_status`, `_plan_r`, `_plan_exit` and `_plan_t1_hit_ts` to `_plan_t3_hit_ts`. Nothing
is stored for a level that was not one of those six slots, and nothing says how far price went before
the stop.

Production holds 175 `premarket_analysis` rows a ticker for SPY, QQQ and IWM, 2026-02-18 to 2026-11-16;
7 a ticker carry a `level_basis`; the 9 rows of rule `feat-strat-001.v3` (2026-11-14 to 2026-11-16) are
not yet resolved (read). So a per-rung hit rate cannot be read today. Design 6 says what must be stored:
one number a side.

### 5. What earlier experiments said

In the repo (gap-edges spec, Experiment): over 2022-01-03 to 2026-11-10, 3,463 trades, no costs, the
plan made +172.3 R and +176.8 R with gap edges; targets hit before the stop: T1 20% and T2 3% without
gap edges, 22% and 4% with them.

From another session's notes, handed to this spec, not in the repo and not re-run here: selling sixths
at every merged rung made +90.5 R; the spacing skip is worth about +80 R; T3 of the spaced targets is
hit 0.5% of the time; the notes give the gap-edges total as +176.7 R. They are context for the
hypotheses, not evidence this spec checked.

## Non-goals

- The trigger, the stop, the spacing value, the leg count, the opened-through rule, the entry cutoff.
- The gate targets, the t1..t3 columns, the signal monitor, the movement statement, persona plans.
- Selling in more than three parts. The owner kept thirds.
- Breakeven or trailing stops.
- New ATR rungs. The fill uses the rungs the brief already keeps (anchors, step, farthest multiple and
  thinning unchanged).
- Filling the reach history from replays. It starts with the first resolved session after deploy
  (Decision 4).
- Any solyra change. The brief's text is stored and shown as text.

## Approaches considered

1. Chosen: keep the spaced walk; first group close levels into zones; then fill any leg still without a
   target from an ordered list of sources named in policy; show every rung of the ladder with its role.
   Each part is its own policy row, seeded to today's behaviour, so the Experiment can score each alone
   and the owner turns on what passed.
2. Drop the window for targets. Rejected: IWM's next level is 5.91 x ATR away; a target needs a bound,
   and the bound should be the ticker's own (Design 3).
3. Put ATR rungs into the spaced walk in price order, like gap edges. Rejected: on IWM calls the first
   sale would move from 283.79 (PWH) to 280.73 (PMK_L+1), an ATR rung in front of the levels, against
   "the levels are always targets and the ATR levels enhance them".
4. Sell at every rung in smaller parts. Rejected by the owner ("keep thirds") and, in the other
   session's notes, the worse result.
5. Treat a zone as far enough only when its nearest edge clears the spacing. Rejected: IWM puts would
   lose their T1 by 3 cents and SPY calls their T2, each because a neighbour joined the level
   (Design 1).

## Design

### 1. Close levels are one target zone

New per-ticker key `target_merge_atr`, in the policy's ATR basis, method `policy_seed`.

The side's levels past the trigger (unbroken candidates, and the level types `plan_target_level_types`
lists), inside the side's reach (Design 3), are walked in price order outward. A level joins the open
zone when its distance in cents from the zone's nearest level is at most
`price_cents(target_merge_atr x ATR)` (equal joins); otherwise it opens a new zone. So a zone is never
wider than the merge distance and cannot chain along a run of levels. The trigger is never part of a
zone. A zone is inside the window when its nearest level is.

- **Name.** A zone of several levels is named by all of them, nearest first:
  `279.17 to 279.33 (PDH, PMC)`.
- **Price: the nearest edge.** A sale resting there fills whenever any part of the zone is reached. A
  cluster of levels is where a move tends to stall, so waiting for the far edge misses the days that
  tag the first level and turn. It is also the one price whose reach rate the stored history can state
  (Design 6).
- **Far enough: by the far edge.** In the spaced walk a zone is one rung. It is kept as a target when
  its far edge is at least the spacing past the trigger or past the far edge of the target before it;
  otherwise the whole zone is too close, once, not level by level. Measuring by the far edge means a
  zone is a target when any of it is far enough: IWM puts' 274.67 and 274.55 straddle the 122 cent
  spacing by 3 and 9 cents, and are one target sold at 274.67.
- **Merge and spacing.** The merge distance says "the same place"; the spacing says "far enough to be
  a separate sale". `target_merge_atr` must be below the ticker's `target_min_spacing_atr`; a row at or
  above it is `input_unavailable` and the side publishes no target and says why (no fallback, CLAUDE.md
  3.7). A level farther than the merge distance from a target and closer than the spacing is still too
  close, as today. Because a zone sells at its nearest edge, a sale can sit closer to the one before it
  than the spacing by at most the merge distance; the Experiment measures what that costs against the
  spacing's reported gain.
- **A zone inside the spacing of the trigger stays too close.** IWM calls' 279.17 to 279.33 is 25 to 41
  cents past the trigger, 0.05 to 0.08 x ATR. It becomes one line on the ladder, not a first sale 25
  cents after the entry: the exits spec removed close first targets on evidence, and the other
  session's notes put the spacing skip at about +80 R. Decision 1 is the owner's if that pair was meant
  to be T1.
- **Seed 0.0**, which merges nothing (one cent, one level, as today). The proposed value is 0.10; 0.15
  and the ticker's own `level_cluster_atr` are tested beside it (Experiment). `level_cluster_atr` is
  the calibrated distance PMG zones already use (IWM 0.050, read), so it is a per-ticker candidate with
  no new number.

### 2. Always a T1, a T2 and a T3: the fill

After the walk of Design 1 over the zones inside the window (today's walk when no zone has two
levels), a side with fewer than `exit_legs` targets fills the rest from the steps of a new policy-wide
row, `target_fill_sources` (extra `{"sources": [...]}`), in the order listed. Each step runs while a
leg has no target:

| Step | Takes | Order |
|---|---|---|
| `level_beyond_window` | zones past the side's window and inside its reach (Design 3) | outward from the last target; each at least the spacing past the far edge of the one before |
| `atr_rung_beyond` | the brief's kept ATR rungs past the last target and inside the reach | outward; each at least the spacing past the one before |
| `atr_rung_between` | kept ATR rungs between the trigger and the last target | farthest from the trigger first; each at least the spacing from the trigger and from every target on either side |

Then the targets are numbered in price order outward. Rules that hold for every step:

- The level targets inside the window are found first and never displaced: "the levels are always
  targets". A fill adds a target; it never removes one.
- Every fill target is labelled with its source in level_basis and in the brief (Design 7).
- `atr_rung_between` exists because a side can have nothing past its last level: QQQ puts' T2 is PYH at
  637.01 and no level or rung lies past it inside the reach, while three kept rungs lie before it. It
  is last, and farthest first, so a fill does not pull the first sale toward the entry.
- When no step finds a candidate the leg is held to the close or the stop, the side records
  `fill_status` `no_candidate_in_reach`, and the brief says so. Nothing is invented: "always" means
  whenever the ladder holds a price inside the reach. The Experiment counts the sides still short.
- When `atr_rung_status` is not ok the rung steps add nothing and `fill_status` carries that status.
- The proposed order is the table's: a level before an ATR rung. An empty list is today's plan and is
  the seed.

The target after T3 is nothing: with three targets the last third is sold at T3 "or held to the close
or the stop", the exits spec's wording, unchanged.

### 3. The reach: how far a target may sit

Two new per-ticker keys, `target_fill_reach_long_atr` and `target_fill_reach_short_atr`: the farthest
a fill target, and a ladder line, may sit from the reference, in ATR. Method `daily_excursion_quantile`
on the trigger window's own samples (`lib.level_calibration.daily_excursions`,
`lib/level_calibration.py:263-272`) with `statistic_q` 1.0, lookback 750 sessions, minimum 250: the
largest move from the prior close, in ATR, the ticker made in a session over the lookback. A level
farther than that has not been reached in a day in three years. Like the window, it is measured from
the prior close and applied from the reference; that mismatch is the window's too and is not changed
here.

It is calibrated per ticker by the nightly and history runs, from the daily frame they already load.
Its value for SPY, QQQ and IWM was not computed for this spec (What was not verified); the fixtures use
3.0.

### 4. The full ladder

Each side with a trigger records `plan_ladder`: every zone or level of Design 1 and every kept ATR rung
past the trigger, inside the side's reach, in price order outward. Each entry carries its price (and
far price for a zone), names, kind (`level` or `atr_rung`), role (`t1`, `t2`, `t3`, `too_close` or
none), whether it is inside the window, and its distance from the trigger in ATR.

Opens are not on it (they stay the FTFC reference), nor broken levels, nor rungs the thinning dropped.
A level beyond the reach is not listed; it stays in the side's `candidates`.

### 5. Strength: an ATR level on a level

A level, or any level of a zone, is marked stronger when an ATR rung lands on it: any of the session's
rungs, kept or dropped by the thinning, whose distance in cents from the level is at most
`price_cents(level_cluster_atr x ATR)` (equal counts). `level_cluster_atr` is the ticker's existing
calibrated "same place" distance (method `rth_interval_change_quantile`, the median 15-minute change
over 60 sessions in ATR; IWM 0.050, 25 cents; read), so coincidence is a policy distance with no new
row. The entry records the rungs' labels. On IWM 2026-11-16 (derived from the stored basis): PWH 283.79
carries PMK_H+1 (the same cent) and PDH+1 (284.04, 25 cents); PMH 285.26 carries none (the nearest,
PMK_L+2 at 285.61, is 35 cents away). A rung line carries no strength note.

The note is text. It changes no target and no score; whether stronger levels are reached or hold more
often is a separate question the reach history can answer later.

### 6. Reach history: what must be stored

One number a side: `{calls,puts}_plan_mfe_atr`, nullable `DOUBLE PRECISION` on `premarket_analysis`
beside the plan columns (`gcp/schema.sql:1987-2004`), written by the resolver for a side whose
`plan_entry_status` is `entered`: the distance travelled in the side's direction from the bar after
the fill bar until the bar in which the stop is hit (that bar not counted, stop first, as the plan
scores) or the last bar before the exchange's close, floored at 0 and divided by the basis ATR. For
calls the distance is the highest high minus the trigger; for puts it is the trigger minus the lowest
low. The bars are the resolver's `plan_bars`, cut at `session_close(analysis_date)`
(`gcp/premarket_playbook_resolver.py:759-765`), so on a half day nothing after 13:00 ET counts. NULL
for a side not entered or a basis with no ATR. `RESOLVER_VERSION` moves.

From it every rung's rate follows without storing rungs: a rung `d` x ATR past the trigger was reached
before the stop on the sessions whose value is at least `d`. The brief reads, in one query for all its
tickers, the values of the last `ladder_history_sessions` analysis dates before the session date
(policy-wide, extra `{"sessions": 250}`), and prints on each ladder line `reached k of n`: n the
side's entered sessions in that span, k those that went at least that far. Counts, never a percent, so
a small n reads as small. Zero rows prints `no history yet`; a failed read raises (CLAUDE.md 3.7). A
BRIEF_AS_OF run reads only earlier dates.

The measure depends on the trigger and stop rules, which this spec does not change, so the population
is every row the new resolver wrote. It is per ticker and side, not per level name: a PDH 0.05 x ATR
out and a PDH 1 x ATR out are different targets, and distance is what a small history can speak to.

### 7. What the brief prints

In each side's block, after the targets, the `Skipped, closer than ...` line is replaced by:

```
    Ladder past {trigger}: targets at least {spacing} x ATR({n}) = {price} apart[, levels within {merge} x ATR({n}) = {price} are one zone]
      {price or "near to far"} ({names}): {notes}, {d} ATR past the trigger[, stronger ({rungs} ATR level[s])], {reached k of n | no history yet}
```

The zone clause prints only when the merge distance is above zero. Notes, in this order when they
apply: `T1` to `T3`; `ATR level`; `one zone`; `too close to sell`; `beyond the usual range` (past the
side's window). A zone target prints `sell 1/3 at {nearest edge}`. A fill target's name carries its
source: `(PDH+1.5 stretch, ATR level)` or `(PQH, beyond the usual range)`. A side still short with a
non-empty fill list ends with the hold line origin/main already prints for the thirds no target took
(`lib/strat_levels.py:3213`, `left = legs - len(targets)`), followed by `(no level or ATR level in
reach for a further target)`: the last 1/3 with two targets, the last 2/3 with one, and the whole
position with none. The fraction is always the count of thirds actually left, never a fixed 1/3.

NEXT LEVELS, its ATR levels line and PMG ZONES are unchanged. The ATR line repeats rungs the ladder now
shows; it stays because a side with no trigger has no ladder.

### 8. The 2026-11-16 IWM brief, before and after

Fixtures: the stored `level_basis` of `premarket_analysis` for 2026-11-16 (IWM, SPY, QQQ; built
2026-11-16T08:31:19 ET; a later replay can overwrite that row, so the copy is taken by build time), copied verbatim into `tests/fixtures/`,
with the new parameters added to its params for each case and both reach keys 3.0, rendered with bias
`bearish`, the bias of the stored row's text. Reach histories for
the goldens: calls 0.1, 0.3, 0.4, 0.7, 1.1, 1.2, 1.6, 2.4; puts 0.05, 0.2, 0.3, 0.6, 0.9, 1.3, 1.5,
2.1. IWM: reference 276.37, ATR(14) 4.874951, spacing 122 cents, merge at 0.10 49 cents,
`level_cluster_atr` 25 cents, long window to 286.94, short window to 265.31.

Today (origin/main on the stored basis; rendered by `format_levels_for_brief` with bias `bearish`, run;
its first line is the stored `playbook` column's first line, read):

```
  CALLS above 278.92 (PMK_H) -- only if bias denied, new entries 09:30 to 16:00 ET
    No entry if the open is at or above 278.92.
    Stop: 275.86 (PMK_L)
    T1: 283.79 (PWH), sell 1/3
    T2: 285.26 (PMH), sell 1/3, hold the last 1/3 to the close or the stop
    Skipped, closer than 0.25 x ATR(14) = 1.22: 279.17 (PDH), 279.33 (PMC)
    Room to trigger: 0.92%

  PUTS below 275.86 (PMK_L), new entries 09:30 to 16:00 ET
    No entry if the open is at or below 275.86.
    Stop: 277.41 (PQL)
    T1: 274.55 (11/9 Gap Low), sell 1/3
    T2: 269.88 (PML), sell 1/3, hold the last 1/3 to the close or the stop
    Skipped, closer than 0.25 x ATR(14) = 1.22: 274.67 (PDL)
    Room to trigger: 0.19%
```

Seeded (the five rows as `gcp/schema.sql` seeds them: same targets, the ladder shown; derived):

```
  CALLS above 278.92 (PMK_H) -- only if bias denied, new entries 09:30 to 16:00 ET
    No entry if the open is at or above 278.92.
    Stop: 275.86 (PMK_L)
    T1: 283.79 (PWH), sell 1/3
    T2: 285.26 (PMH), sell 1/3, hold the last 1/3 to the close or the stop
    Ladder past 278.92: targets at least 0.25 x ATR(14) = 1.22 apart
      279.17 (PDH): too close to sell, 0.05 ATR past the trigger, reached 8 of 8
      279.33 (PMC): too close to sell, 0.08 ATR past the trigger, stronger (PDL+1 ATR level), reached 8 of 8
      280.73 (PMK_L+1): ATR level, 0.37 ATR past the trigger, reached 6 of 8
      281.98 (PDL+1.5 stretch): ATR level, 0.63 ATR past the trigger, reached 5 of 8
      283.79 (PWH): T1, 1.00 ATR past the trigger, stronger (PMK_H+1, PDH+1 ATR levels), reached 4 of 8
      285.26 (PMH): T2, 1.30 ATR past the trigger, reached 2 of 8
      286.48 (PDH+1.5 stretch): ATR level, 1.55 ATR past the trigger, reached 2 of 8
      288.67 (PMK_H+2 stretch): ATR level, beyond the usual range, 2.00 ATR past the trigger, reached 1 of 8
    Room to trigger: 0.92%

  PUTS below 275.86 (PMK_L), new entries 09:30 to 16:00 ET
    No entry if the open is at or below 275.86.
    Stop: 277.41 (PQL)
    T1: 274.55 (11/9 Gap Low), sell 1/3
    T2: 269.88 (PML), sell 1/3, hold the last 1/3 to the close or the stop
    Ladder past 275.86: targets at least 0.25 x ATR(14) = 1.22 apart
      274.67 (PDL): too close to sell, 0.24 ATR past the trigger, reached 6 of 8
      274.55 (11/9 Gap Low): T1, 0.27 ATR past the trigger, stronger (PDH-1 ATR level), reached 6 of 8
      273.42 (PMK_L-0.5): ATR level, 0.50 ATR past the trigger, reached 5 of 8
      271.86 (PDH-1.5 stretch): ATR level, 0.82 ATR past the trigger, reached 4 of 8
      269.88 (PML): T2, 1.23 ATR past the trigger, stronger (PDL-1 ATR level), reached 3 of 8
      268.55 (PMK_L-1.5 stretch): ATR level, 1.50 ATR past the trigger, reached 2 of 8
      266.11 (PMK_L-2 stretch): ATR level, 2.00 ATR past the trigger, reached 1 of 8
    Room to trigger: 0.19%
```

After (`target_merge_atr` 0.10 and the three fill steps in the proposed order; derived):

```
  CALLS above 278.92 (PMK_H) -- only if bias denied, new entries 09:30 to 16:00 ET
    No entry if the open is at or above 278.92.
    Stop: 275.86 (PMK_L)
    T1: 283.79 (PWH), sell 1/3
    T2: 285.26 (PMH), sell 1/3
    T3: 286.48 (PDH+1.5 stretch, ATR level), sell the last 1/3, or hold to the close or the stop
    Ladder past 278.92: targets at least 0.25 x ATR(14) = 1.22 apart, levels within 0.1 x ATR(14) = 0.49 are one zone
      279.17 to 279.33 (PDH, PMC): one zone, too close to sell, 0.05 ATR past the trigger, stronger (PDL+1 ATR level), reached 8 of 8
      280.73 (PMK_L+1): ATR level, 0.37 ATR past the trigger, reached 6 of 8
      281.98 (PDL+1.5 stretch): ATR level, 0.63 ATR past the trigger, reached 5 of 8
      283.79 (PWH): T1, 1.00 ATR past the trigger, stronger (PMK_H+1, PDH+1 ATR levels), reached 4 of 8
      285.26 (PMH): T2, 1.30 ATR past the trigger, reached 2 of 8
      286.48 (PDH+1.5 stretch): T3, ATR level, 1.55 ATR past the trigger, reached 2 of 8
      288.67 (PMK_H+2 stretch): ATR level, beyond the usual range, 2.00 ATR past the trigger, reached 1 of 8
    Room to trigger: 0.92%

  PUTS below 275.86 (PMK_L), new entries 09:30 to 16:00 ET
    No entry if the open is at or below 275.86.
    Stop: 277.41 (PQL)
    T1: 274.67 to 274.55 (PDL, 11/9 Gap Low), sell 1/3 at 274.67
    T2: 269.88 (PML), sell 1/3
    T3: 268.55 (PMK_L-1.5 stretch, ATR level), sell the last 1/3, or hold to the close or the stop
    Ladder past 275.86: targets at least 0.25 x ATR(14) = 1.22 apart, levels within 0.1 x ATR(14) = 0.49 are one zone
      274.67 to 274.55 (PDL, 11/9 Gap Low): T1, one zone, 0.24 ATR past the trigger, stronger (PDH-1 ATR level), reached 6 of 8
      273.42 (PMK_L-0.5): ATR level, 0.50 ATR past the trigger, reached 5 of 8
      271.86 (PDH-1.5 stretch): ATR level, 0.82 ATR past the trigger, reached 4 of 8
      269.88 (PML): T2, 1.23 ATR past the trigger, stronger (PDL-1 ATR level), reached 3 of 8
      268.55 (PMK_L-1.5 stretch): T3, ATR level, 1.50 ATR past the trigger, reached 2 of 8
      266.11 (PMK_L-2 stretch): ATR level, 2.00 ATR past the trigger, reached 1 of 8
    Room to trigger: 0.19%
```

IWM's calls T3 is 286.48 because 305.18 (PQH) is 5.91 x ATR from the reference, past any reach the
fixture allows, and 286.48 is exactly the 122 cent spacing past 285.26 (equal is kept).

The other two tickers under the same "After" rows (derived from their stored bases, fixture reach 3.0):

| Side | T1 | T2 | T3 |
|---|---|---|---|
| SPY calls | 760.12 PDH | 762.63 to 763.04 (PQC, PWH), sold at 762.63 | 779.37 PQH, beyond the usual range |
| SPY puts | 741.03 PWL | 729.10 PQL | 725.88 PMK_L-2, ATR level |
| QQQ calls | 688.75 PDH | 695.57 PWH | 711.62 10/30 Gap High, beyond the usual range |
| QQQ puts | 662.02 to 661.14 (PWL, PQL), sold at 662.02 | 647.17 PDL-1.5, ATR level (between) | 637.01 PYH |

### 9. The rows that change the plan

The seeded rows change no target. After the Experiment and the owner's yes, later-dated rows turn the
parts on, so sessions before that date replay as they were:

```sql
INSERT INTO level_param_policy (param_key, method_id, statistic_q, lookback_sessions, min_sample,
                                extra, effective_from, note)
VALUES ('target_merge_atr', 'policy_seed', NULL, NULL, NULL, '{"seed": 0.10}', :swap_date,
        'levels within this of a zone''s nearest level are one target zone / ATR'),
       ('target_fill_sources', 'policy', NULL, NULL, NULL,
        '{"sources": ["level_beyond_window", "atr_rung_beyond", "atr_rung_between"]}', :swap_date,
        'where a leg with no target inside the window gets one, in order')
ON CONFLICT (param_key, effective_from) DO NOTHING;
```

The values written are the ones the Experiment supports and the owner picks; these are the proposal.
`target_merge_atr` is a `policy_seed` key, so the next calibration run writes the ticker rows.

### 10. level_basis and stored briefs

A basis built under this rule records a top-level `plan_ladder_status` (`ok`, or the first status among
the five keys that is not ok), the keys' values with status, method and effective date, each side's
`plan_ladder` and `fill_status`, zone and source on targets, and the reach counts as printed.
`SessionLevels.from_basis` applies Designs 1 to 5 and checks the new keys only when that marker is
present, the pattern of `atr_rung_status` and `plan_target_level_types_status`
(`lib/strat_levels.py:1989-1999`). A stored brief, its replay and its plan R do not change.
`LEVEL_RULE_VERSION` does not move, because the gate targets and the trigger do not.

For a basis with the marker, the five keys join the keys `_plan_targets` checks first (`:2836-2839`, the tuple gap edges already extend): a
side whose row is missing or unusable publishes no target and says why.

The resolver reads targets by price (`plan_inputs`, `gcp/premarket_playbook_resolver.py:611-625`), so a
zone (its nearest edge) and a fill target are scored by the existing code. Its only change is Design 6.

## Experiment

Run before any production row changes. It is not run by this spec.

**Hypotheses.**

- H1, fill: giving the unassigned third a price by rule does no worse than holding it to the close.
  Expected: arm B is close to A, because a level past the window is by construction past the move the
  ticker stays inside on 99 sessions in 100, so it is seldom reached and the third still rides to the
  close; arm C can differ, because a rung inside the window is reached more often and sells a third
  that would otherwise ride.
- H2, zones: one zone for close levels, sold at the nearest edge, does no worse than today.

**What keeps today's rule.** An arm whose range against A lies wholly below zero overall, or for two
of the three tickers, is not proposed. If no fill arm passes, `target_fill_sources` stays empty and the
brief keeps holding the third, saying no further target is in reach. If no merge arm passes,
`target_merge_atr` stays 0.0 and close levels stay separate lines on the ladder. An arm whose range
spans zero is put to the owner as "no worse, by this test", with the totals and blocks, since the owner
asked for a T3 and for one target.

**Arms** (policy rows in the local copy; everything else the seeded policy on main):

| Arm | `target_fill_sources` | `target_merge_atr` |
|---|---|---|
| A, today | `[]` | 0.0 |
| B, T3 by the next level | `["level_beyond_window"]` | 0.0 |
| C, T3 by ATR rung | `["atr_rung_beyond", "atr_rung_between"]` | 0.0 |
| D10, D15 | `[]` | 0.10, 0.15 |
| DC | `[]` | each ticker's `level_cluster_atr` in force |
| S, the Design 9 rows | the three steps | 0.10 |

**Method.** The gap-edges spec's: every session from 2022-01-03 to 2026-11-10 for SPY, QQQ and IWM
replayed through `gcp/premarket_brief.py` (BRIEF_AS_OF) with history-mode parameters into a local copy
of the schema; one trade per ticker-day, the first side to cross its trigger; a same-bar tie is no
trade; a day that opens past a trigger is no trade; the 16:00 cutoff on main; half days cut at the
exchange close; SPY 2025-04-09 and IWM 2026-06-26 left out; each trade scored by
`gcp.premarket_playbook_resolver.resolve_plan` on `plan_inputs` of the arm's basis. No bar walk is
written for the test (CLAUDE.md 3.6). Arm A must reproduce +176.8 R over 3,463 trades to 0.1 R before
any other arm is read.

**Reported, per arm:** total R; SPY, QQQ, IWM; the six-month blocks of the gap-edges spec (Mar to Aug
and Sep to Feb, first and last partial); the 90% range of arm minus A, resampling whole days 2,000
times, seed 7; the share of entered trades reaching T1, T2 and T3 before the stop; traded sides with
fewer than three targets; trades whose targets differ from A; for the fill arms, the source of each
T3 and its hit rate by source; for the merge arms, the trades where a zone sold closer than the
spacing and their R against A.

**The production path.** The local replay cannot read production's premarket rows and writes nothing
there. The dry run of
`docs/superpowers/specs/2026-11-16-feat-playbook-001-brief-says-what-the-data-says.md` (`--no-persist`,
`BRIEF_NO_PERSIST=true`; a draft on `origin/docs/spec-feat-playbook-001-brief-says-what-the-data-says`,
not on main) lets the deployed job build a past brief without a write. Once it is on main, arm A's
targets for a sample of stored sessions are built by the deployed job and compared with the local
build. Only arm A can be checked this way: the deployed job reads its policy rows from production for
the analysis date (`gcp/premarket_brief.py:950-980`), and the other arms' rows exist only in the local
copy. Handing the deployed job another arm would need either a production write or a new override
input, and this spec adds neither. The arm the owner picks is checked in production once, after the
owner's yes to its Design 9 rows, by a dry run of the first session those rows cover. Each dry run
still calls the model, so the sample size is the owner's (Decision 5).

## Decisions for the owner

Each is written into the text as recommended.

1. **A zone inside the spacing of the trigger stays too close** (IWM calls' 279.17 to 279.33 is one
   ladder line, not T1). Alternative: the first zone past the trigger is always T1, which sells a third
   25 cents after the entry on that day; it would be one more arm of the Experiment.
2. **Fill order: a level past the window, then an ATR rung past the last target, then an ATR rung
   between.** Alternative: rungs first, which on 2026-11-16 gives SPY calls 769.95 and QQQ calls 700.98
   as T3 in place of 779.37 and 711.62.
3. **The reach is the largest one-day move of the last 750 sessions, in ATR, per ticker.** Alternative:
   a multiple of the window, a new number with no calibration behind it.
4. **Reach history starts with the first session resolved after deploy**, plus a re-resolve of the
   sessions since 2026-11-14 that carry a v3 basis. Alternative: fill it from replays, marked as
   replays, a separate change.
5. **Dry-run sample: five stored sessions**, about five briefs' model calls. Alternative: none, relying
   on the local replay alone.
6. **This spec supersedes nothing.** Alternative: mark the ATR levels spec superseded, since a rung can
   become a target once a rung step is listed.

## Expected effect

At deploy, with the seeded rows: every side's targets, plan R and gate targets are what they are today;
each side's block lists the whole ladder with roles, strength notes and reach counts (`no history yet`
at first) where it listed skipped levels.

After the Design 9 rows, on 2026-11-16's levels: all six sides print three targets where they printed
two (Design 8), three of them with a zone.

## Capacity and cost

- **Volume:** five policy rows; three more `ticker_level_params` rows a ticker a calibration run; two
  nullable columns on `premarket_analysis`; each new `level_basis` gains a ladder of about 6 to 12
  entries a side (IWM 2026-11-16: 8 and 7).
- **Velocity:** one new query a brief run, for all tickers: at most `ladder_history_sessions` x tickers
  rows (250 x 3 = 750) of two numbers, by the `(analysis_date, ticker)` unique index. No new query in
  the resolver or the calibration; both use frames already loaded.
- **Wall-clock:** one more round trip a brief run, about 0.5 to 2 s at the connector's speed against a
  job that already makes dozens; the read's latency was not measured.
- **Cost:** $0 scheduled; no new job or schedule. The Experiment's dry runs cost one brief's model
  calls each (Decision 5).

## Source identity and close-out

`lib/`, `gcp/` and `tests/` are inside SITE's watched scope. DASHBOARD-01 (the brief) shows the new
lines. Only the `(FEAT-STRAT-001, DASHBOARD-01)` row of the Implementation-source notes table may
describe this implementation, as backend source and local tests only.

After the merge, separately and never as a pre-merge box:

1. On the owner's yes: apply the five seeded rows and the two columns; deploy the calibration job and
   run it in history mode for `target_merge_atr` and the two reach keys; confirm by a read that SPY,
   QQQ and IWM each hold the three rows with status ok. Rows first, because the code treats a missing
   row as no plan.
2. Deploy the brief and the resolver. Confirm the next live brief records `plan_ladder_status` ok,
   prints the ladder, and that its targets equal what `SessionLevels.from_basis` gives for the same
   basis with the marker removed (the seeded rows change none). Re-resolve 2026-11-14 onward and confirm the two new
   columns fill for entered sides.
3. Run the Experiment and post it on the implementation PR or, if merged, on a new issue. On the
   owner's second yes, insert the Design 9 rows with the values chosen, run the calibration, and
   confirm the next brief prints three targets where the ladder allows.
4. Complete the DOC close-out as the product-delivery skill prescribes.

## Risks

- **A zone sells closer than the spacing.** By at most the merge distance. The merge arms report those
  trades alone.
- **A T3 past the window is seldom reached.** It may read as a plan and act as a hold. Arm B's T3 hit
  rate says how often; the brief labels it "beyond the usual range".
- **An ATR rung is not a level.** Selling at one is a new behaviour; it is off until arm C or S passes
  and the owner says yes, and the brief labels it.
- **Deploy order.** Code before rows leaves every side without targets for that run (Design 10).
  Close-out step 1 puts rows first.
- **Longer briefs.** About 8 more lines a side. The brief already splits its playbook into chunks
  (`_split_playbook_embed`, `gcp/premarket_brief.py:2907`); whether the split falls well was not
  checked.
- **Small reach history.** Counts are printed as counts so 2 of 5 is not read as 40%.
- **The between step can place an ATR rung ahead of the last level.** It is the last step, farthest
  first, and the owner can leave it off the list.

## What was not verified

- Every result in "What earlier experiments said" marked as another session's notes.
- The reach values: the largest daily excursion in ATR over 750 sessions for SPY, QQQ and IWM was not
  computed; the goldens use a fixture value of 3.0.
- That the lane's bar files and local schema copy the gap-edges Experiment used still exist; this
  session could not read them. Production holds 1-minute bars for the three tickers from 2015-01-02 to
  2026-11-13 (read), which a local copy can be filled from.
- The Design 8 "Seeded" and "After" texts and the SPY and QQQ table are derived by this spec from the
  stored bases, not produced by an implementation.
- Readers of a side's `skipped` list outside `lib/strat_levels.py`: none found by a search of
  `gcp/*.py`, `lib/*.py`, `lib/agents/*.py` and `platform/api/routers/*.py`; solyra was not searched.
- The latency of the reach-history read, and how the longer playbook splits across Discord messages.
- Whether the dry-run spec will be approved as drafted; the production-path check depends on it.

## Found while reading (not changed by this spec)

- `premarket_analysis` rows dated 2026-10-01 to 2026-11-09 carry `outcome_resolver_version`
  `2026-05-11.v1` and no plan columns, while rows before them carry `2026-11-12.v3` (read). Not
  investigated.
