---
feat_id: FEAT-STRAT-001
req_ids: [REQ-PLAYBOOK-001, REQ-DATA-001, REQ-REL-001]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01]
done_when:
  - "Policy: the level_param_policy seed row entry_cutoff_et (method_id policy, effective 2015-01-02) in gcp/schema.sql holds extra {\"time_et\": \"16:00\"} with ON CONFLICT DO NOTHING and a note saying a first cross anywhere in the regular session is an entry; no other level_param_policy row changes; git diff origin/main --stat on the implementation head lists no file under lib/ or gcp/ other than gcp/schema.sql and gcp/premarket_playbook_resolver.py (Design 3); tests/gcp/test_level_params_consumers.py asserts the basis records entry_cutoff_et extra {\"time_et\": \"16:00\"}, and a test in tests/lib/test_level_params_loader.py loads the seeded policy from gcp/schema.sql and asserts policy_wide_param gives entry_cutoff_et status ok and value 960 (minutes after midnight); both fail on origin/main, where the seed is 10:00 and the value 600"
  - "Resolver: tests/gcp/test_premarket_playbook_resolver.py passes a test that builds PlanInputs through plan_inputs from a v2 row with the policy loaded from gcp/schema.sql (as test_level_params_behaviour does) for a call with trigger 100.00, stop 99.00, targets 101.00, 102.00, 103.00: on synthetic 1-minute RTH bars whose first cross of the trigger is the 10:00 bar it gives plan_entry_status entered and plan_fill_price 100.00, and with the first cross in the 15:59 bar it gives entered; on origin/main the 10:00 case gives late_cross; the existing TestPlanOutcome cases that pass an explicit cutoff of 10:00 still give late_cross for a 10:00 first cross and entered for a 09:59 one, so the cutoff mechanism is unchanged and only the seeded value moves; a resolve_one test with a stubbed engine on a half day (2026-11-27, close 13:00 ET) whose bars include prints from 13:00 to 15:59 gives a first cross at 13:30 plan_entry_status no_cross and no plan R, a trade entered at 09:45 that is open at the close books its close legs at the 12:59 bar's close, not a later print, and the existing columns (trigger_hit_ts, t1_hit_ts to t3_hit_ts, stop_hit_ts, eod_pnl_pct) are bound exactly as on origin/main for the same bars; on origin/main the plan's close legs take the last print, and on a head without Design 3 the 13:30 cross would be entered"
  - "Brief copy: the exits spec's Design 8 golden strings in tests/lib/test_strat_levels.py (D8_CALLS, D8_PUTS) read 'new entries 09:30 to 16:00 ET' on both sides and are otherwise byte-identical to origin/main's; the brief's generated test fixtures that record the seeded cutoff (tests/fixtures/atr_levels_brief_base.json, tests/fixtures/atr_levels_display_only_base.json) differ from origin/main only in entry_cutoff_et values and the window text"
  - "Stored briefs keep their cutoff: tests/gcp/test_level_basis.py passes a test where SessionLevels.from_basis on a stored basis recording entry_cutoff_et 10:00 rebuilds a plan with entry_cutoff_et 10:00 after the policy row is changed to 16:00, and the resolver scores a 10:00 first cross on that stored row as late_cross; a basis built after the change records 16:00"
  - "Unchanged, each pinned by an existing test that passes on origin/main and on the implementation head: the trigger, stop, gate targets, plan targets, skipped list, exit_legs and the thirds, the opened-through rule, the ATR rungs line, the signal monitor's fire decisions and put re-anchor, the movement statement, persona plans, the CALL/PUT pick and the resolver's existing outcome columns; LEVEL_RULE_VERSION does not change (the cutoff is recorded in level_basis as a value, so the rule that reads it is the same); RESOLVER_VERSION moves past 2026-11-12.v3 because Design 3 changes plan columns on half days"
  - "Experiment through the production paths, before any production change: the implementation PR body shows, for SPY, QQQ and IWM over 2022-01-03 to 2026-11-10 on the same ticker-days as this spec's Experiment (one trade per ticker-day, the first side to cross its trigger, a same-bar tie is no trade, half days cut at the exchange close, SPY 2025-04-09 and IWM 2026-06-26 left out), plan R from gcp.premarket_playbook_resolver.resolve_plan with the cutoff read from the seeded policy on origin/main and on the head, per ticker and per six-month block, with the 90% day-resampled range of head minus origin/main (seed 7, 2,000 draws); the totals match this spec's Experiment to 0.1 R (+164.6 and +172.3); this is a reproduction for the record, not a gate, since the owner decided on these numbers"
  - "Source identity (DASHBOARD-01): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-STRAT-001, DASHBOARD-01) note row carries that source_identity_sha256 with implementation and test prose for this PR"
  - "The FEAT-STRAT-001 catalog record and the PR traceability entry are updated; python3 scripts/gate/spec_gate.py --pr origin/main passes; the production entry_cutoff_et row is changed only after the owner's yes, by the statement in Design 2, and recorded separately"
status: approved
supersedes: null
---

# The exits plan drops its 10:00 ET entry cutoff: a first cross of the trigger anywhere in the regular session is an entry

## Authority

The owner's ruling, 2026-11-15 (UTC), after seeing the Experiment below: "Drop it." It answers Open
question 1 of `docs/superpowers/specs/2026-11-11-feat-strat-001-brief-exits-in-thirds.md` (the exits
spec), which asked whether the 10:00 cutoff should stay for every ticker. That spec's Design 4 says the
cutoff "is one row, so the owner can move or drop it without a code change"; this spec is that change,
plus the one guard that dropping it needs: the plan's bars end at the exchange's close (Design 3), so a
print after a half day's early close never becomes an entry.

Rulings still in force: values are never hard-coded and come from policy or per-ticker parameter rows
(2026-11-08); a change is tested against its hypothesis before it is swapped in; R is the stock's move
after the fill measured in stop distances, never money, and comparisons are like for like.

This spec is written by a FEAT-STRAT-001 delivery lane and is not self-approved: it takes effect only
when the owner merges the spec-only PR that adds it, and that merge is the approval its `status`
records. No implementation is written before that merge.

Not in this spec: whether IWM should keep today's rule (all out at the brief's T1) instead of the exits
plan. The owner has not decided that; it stays a separate question.

## Problem

The exits spec's Design 4 bans a new entry when a side's first cross of its trigger comes in a bar
starting at or after `entry_cutoff_et` (seed 10:00 ET). The evidence for it was the lab's primary and
holdout windows; over 2016 to 2025 the lab already found the cutoff's effect on the plan across zero
(-39.2 R, range -131.3 to +52.7).

Re-tested on the production code path (#1832's `resolve_plan` on replayed briefs, Experiment), the
cutoff makes no clear difference over the whole stretch: it skips 986 of 3,463 trades, and those
trades average +0.008 stop distance each. The owner chose to take every first cross rather than keep a
rule that adds nothing clear overall.

## Non-goals

- The cutoff mechanism. `entry_cutoff_et` stays a policy-wide key, `resolve_plan` keeps its
  `late_cross` status, and the brief keeps printing the window it reads from the policy. Only the
  seeded value moves, so the owner can bring a cutoff back with one row.
- Per-ticker cutoffs, and IWM's rule (Authority).
- The opened-through rule (exits spec Design 3), the spacing, the thirds, the stop, the trigger, gate
  targets, the ATR rungs line, the signal monitor and the movement statement.

## Approaches considered

1. Chosen: move the seeded value to 16:00 ET, the regular session's close, and end the plan's bars at
   the exchange's own close (Design 3). The resolver's bar read stops before 16:00, so no bar is at or
   after the cutoff and no first cross in the session is `late_cross`; on a half day the bars stop at
   the early close. The only code change is that trim.
2. Make the cutoff optional in code (a policy value meaning "none", the brief printing no window, the
   resolver skipping the check). Rejected for now: more code and tests for the same plan R, and the
   window line still tells the reader the rule in force.
3. Delete the `entry_cutoff_et` row. Rejected: `plan_inputs` and `policy_wide_param` treat a missing or
   unusable cutoff as `input_unavailable`, so every side would lose its plan (`targets_unavailable`).

## Design

### 1. The seed

`gcp/schema.sql`'s `level_param_policy` seed for `entry_cutoff_et` becomes:

```sql
('entry_cutoff_et', 'policy', NULL, NULL, NULL, '{"time_et": "16:00"}', '2015-01-02',
 'last minute (ET, exclusive) a first cross of the trigger is an entry; 16:00 is the regular close, so every first cross in the session is one'),
```

`ON CONFLICT (param_key, effective_from) DO NOTHING` stays, so a fresh database and every test that
loads the seed read 16:00, while a database that already holds the 10:00 row keeps it until Design 2.

### 2. The production row

The exits spec's policy rows were applied to production on 2026-11-14 with the 10:00 seed. After the
owner's yes, the production row is changed in place:

```sql
UPDATE level_param_policy
   SET extra = '{"time_et": "16:00"}'::jsonb,
       note  = 'last minute (ET, exclusive) a first cross of the trigger is an entry; 16:00 is the regular close, so every first cross in the session is one'
 WHERE param_key = 'entry_cutoff_et'
   AND effective_from = DATE '2015-01-02'
   AND extra->>'time_et' = '10:00';
```

In place rather than a new row with a later `effective_from`, so a history replay of any session uses
the same rule as the live brief and the scores stay like for like. A brief already stored keeps the
cutoff its `level_basis` recorded (`SessionLevels.from_basis` reads the recorded value), so no stored
row or its replay changes. The statement touches one row or none; the run records which.

### 3. The plan's bars end at the exchange's close

`resolve_one` reads every 1-minute bar from 09:30 to 15:59 ET, with no early-close filter. On a half day
the stored table can hold prints after the 13:00 close (the Experiment's data check found 27 ticker-days
with them over 2022 to 2026). Under the 10:00 cutoff those prints could never be a first cross; at 16:00
they could, so a 13:30 print on a half day would become an entry. The plan's walk must stop at the close.

`resolve_one` passes `resolve_plan` only the bars that start before
`lib.eastern_time.session_close(analysis_date)` (13:00 ET on a half day, 16:00 otherwise, from the NYSE
calendar, never a literal). The existing `resolve_leg` columns keep reading the same bars as on
origin/main; trimming them is a separate change (Found while reading). A date that is not a session has
no close, and `session_close` raises for it rather than assume 16:00 (CLAUDE.md 3.7); `resolve_one`
already returns `no_bars` before this point for a holiday, which has no bars. The trim also moves a half
day's close legs from the last print to the last bar before the close, which is what the Experiment
scored. `RESOLVER_VERSION` moves so the re-resolved rows can be told apart.

### 4. What the brief will look like

On the exits spec's Design 8 fixture the only change is the window clause on each side's first line:

```
  CALLS above 252.10 (PMK_H), new entries 09:30 to 16:00 ET
  PUTS below 248.20 (PMK_L), new entries 09:30 to 16:00 ET
```

Every other line is unchanged. On a half day the line still reads 16:00; the plan's bars end at the
early close (Design 3), so no first cross in the session is late there either (Risks).

## Experiment

Hypothesis: with the exits plan's trigger, stop, spaced targets and thirds unchanged, taking a first
cross of the trigger after 10:00 ET does no worse than skipping it.

Data (read only, not in the repo): every session from 2022-01-03 to 2026-11-10 (1,212 sessions; SPY,
QQQ, IWM) replayed through #1832's `gcp/premarket_brief.py` (BRIEF_AS_OF) into a local copy of the
schema, with the as-traded 1-minute bars in
`/mnt/project-files/stocks-scorecard/inputs/bars_raw/`. A data check over the same stretch against the
NYSE calendar found no missing or thin session, no duplicate bar and no bad high, low, open or close;
bars printed after a half day's 1 PM close were cut, and SPY 2025-04-09 and IWM 2026-06-26 were left out
(last bar off the daily close by 0.96% and 0.74%).

Method: one trade per ticker-day, the first side to cross its trigger; a same-bar tie is no trade; a day
that opens past a trigger is no trade under either rule. Each trade is scored by
`gcp.premarket_playbook_resolver.resolve_plan` twice on the same bars, with the cutoff at 10:00 and with
no cutoff; a trade the cutoff skips scores 0 under the cutoff. R per trade is the stock's move after the
fill in stop distances, summed over the three legs. Ranges are 90%, resampling whole days 2,000 times,
seed 7.

Results, total R (no cutoff minus 10:00 cutoff, range):

| Window | Trades, no cutoff / cutoff | No cutoff | 10:00 cutoff | Dropping the cutoff |
|---|---|---|---|---|
| 2022-01-03 to 2026-11-10 | 3,463 / 2,477 | +172.3 | +164.6 | +7.7 (-42.1, +64.1) |
| SPY | 1,161 / 734 | +65.4 | +65.8 | -0.3 (-30.1, +32.4) |
| QQQ | 1,152 / 808 | +110.9 | +122.7 | -11.8 (-38.6, +17.6) |
| IWM | 1,150 / 935 | -4.1 | -23.9 | +19.8 (-1.4, +41.4) |
| 2022-01-03 to 2025-02-28 | 2,275 / 1,687 | +139.7 | +101.8 | +37.9 (-7.6, +81.1) |
| 2025-03-03 to 2026-04-30 | 829 / 549 | +8.5 | +24.0 | -15.5 (-40.7, +9.4) |
| 2026-05-01 to 2026-11-10 | 359 / 241 | +24.0 | +38.7 | -14.7 (-29.0, +0.3) |

The trades the cutoff skips: 986, average +0.008 each; 16% of them reached the spaced T1 before the
stop, and 26% hit the stop before any target. Per ticker within the windows, dropping the cutoff was clearly better for IWM before
2025-03 (+16.9, +0.8 to +34.2) and clearly worse for QQQ in 2025-03 to 2026-04 (-14.4, -26.7 to -1.4)
and in 2026-05 to 2026-11 (-6.8, -13.3 to -0.5).

Six-month blocks (equal blocks; the first and last are partial), dropping the cutoff minus keeping it:
Jan to Feb 2022 +2.9, Mar to Aug 2022 +3.8, Sep 2022 to Feb 2023 -9.3, Mar to Aug 2023 +2.8, Sep 2023 to
Feb 2024 -1.7, Mar to Aug 2024 +33.2 (+11.7 to +56.3), Sep 2024 to Feb 2025 +6.2, Mar to Aug 2025 -2.7,
Sep 2025 to Feb 2026 -14.1 (-27.6 to -0.5), Mar to Aug 2026 -5.5, Sep to Nov 10 2026 -7.9. Only the two
with ranges shown are clear.

Reading: over the whole stretch the cutoff makes no clear difference. Before 2025-03 dropping it leans
better; since 2025-03 keeping it leans better, clearly so for QQQ. The owner saw this split and chose to
drop it.

Commands (the replay database is the local copy described above):

```bash
LAB=/mnt/project-files/stocks-scorecard/research/rescore_1832_asis/ladder
python3 $LAB/ladder2.py 2022-01-03 2026-11-10 ladder2_all.csv   # one row per trade
python3 $LAB/cutoff_test.py ladder2_all.csv                  # the tables above
```

sha256 prefixes: ladder2.py ad126cca, cutoff_test.py ab63dfd3, ladder2_all.csv 16d138ac.

## Expected effect

Every brief side's window reads 09:30 to 16:00 ET. The resolver writes `entered` for first crosses it
wrote `late_cross` for, so more sides carry a plan R; on the Experiment's stretch that is about 40% more
scored trades with a lower average per trade (+0.050 against +0.066) and a total that is not clearly
different. Nothing else in the brief, the monitor or the movement statement changes.

## Capacity and cost

- **Volume:** no new row or column; one existing policy row's `extra` and `note` change.
- **Velocity:** no new query; the row rides the one `load_level_params` query per run.
- **Wall-clock:** unchanged; one in-memory session-close lookup per resolved row, and the resolver walks the same or fewer bars and scores more legs to the close.
- **Cost:** $0; no new job, schedule or resource.

## Source identity and close-out

`gcp/` and `tests/` are inside SITE's watched scope. DASHBOARD-01 (the brief) shows the changed window.
Only the `(FEAT-STRAT-001, DASHBOARD-01)` row of the Implementation-source notes table may describe this
implementation, as backend source and local tests only. Every other SITE byte stays unchanged.

After the merge, separately and never as a pre-merge box: on the owner's yes, run Design 2's statement
against production and record the row count; confirm the next live brief prints the 16:00 window and the
resolver writes `entered` for a first cross after 10:00; and complete the DOC close-out as the
product-delivery skill prescribes.

## Risks

- **Recent months lean the other way.** Since 2025-03 the cutoff did better (-15.5 and -14.7 R for
  dropping it, QQQ clearly). The owner chose to drop it knowing this; a cutoff comes back with one row.
- **Lower average per trade.** Late trades average about zero, so the plan's per-trade average falls
  while its total barely moves.
- **Half days.** The window line reads 16:00 on a day that closes at 13:00. Design 3 ends the plan's
  bars at the early close, so a print after it is never an entry or an exit; only the printed time is
  the regular close, not the early one.
- **A production row edited in place.** Design 2 is guarded on the 10:00 value, so it changes nothing if
  the row was already moved, and stored briefs keep their recorded cutoff.

## Found while reading (not changed by this spec)

- The resolver's existing columns (`resolve_leg`: `trigger_hit_ts`, `t1_hit_ts` to `t3_hit_ts`,
  `stop_hit_ts`, `eod_pnl_pct`) also read prints after a half day's 13:00 close. Under the 10:00 cutoff
  this was already true for them; it needs its own fix and its own owner.
