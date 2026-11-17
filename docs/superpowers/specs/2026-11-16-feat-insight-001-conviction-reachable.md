---
feat_id: FEAT-INSIGHT-001
req_ids: [REQ-DATA-001, REQ-DATA-003, REQ-LLM-001, REQ-REPLAY-001, REQ-VALID-001]
issues: []
canvases: []
done_when:
  - "V1 the measurement is code that can be run again: tests/agents/test_rule_evidence.py passes: measure_sides(rows) builds stop_distance_atr, stop_distance_pct, the first target's R multiple, the mean of the side's target R multiples (rule N2's measure by the owner's decision of 2026-11-16, V11) and entry_vs_sma200_pct for each brief side by calling lib.agents.trade_planner.compute_risk_metrics (a stand-in that raises makes the test fail, so the measurement cannot carry its own formula); a side with a null stop, ATR or outcome keeps null and is counted under unmeasurable, never as 0; a side that did not fill is counted under coverage and left out of the outcome; outcome_r is eod_pnl_pct divided by stop_distance_pct; summarize_rule(sides, rule, threshold) returns n_flagged, n_unflagged, sessions per group, the difference in mean R and a 95 percent range from a session-clustered bootstrap with a fixed seed, equal to the values typed in the test for a fixture of 12 sides; a group under the floor returns verdict 'insufficient' and no effect number; fails on origin/main, where the module does not exist"
  - "V2 the evidence is a file a reviewer can open: docs/audits/<run date>-conviction-rule-evidence.md and tests/agents/fixtures/conviction_evidence.json exist in the PR; the file names the db-query execution id of every read, the SQL file gcp/queries/conviction_rule_evidence.sql, the rule version of the brief rows read, and holds the five tables of Design 2 and Design 3 (sample, per-rule grid, the N1 and C1 candidates, the ladder candidates, the outcome by level) with every cell either a number with its n or the words 'insufficient' or 'not measurable from stored data'; every outcome column of the file's tables, and every result and evidence record in the JSON, names its outcome 'cross-fill-t1-v1', the first-target surrogate of Design 1, and none of them is labelled as the performance of the exit plan in thirds or of the four-quarter exit plan; tests/agents/test_rule_evidence.py::test_evidence_file_matches_its_json passes (the numbers in the markdown tables equal the JSON)"
  - "V3 the owner's choice is on record and the code equals it: the evidence file's section 'Owner decision' names, for each rule and each ladder question of Design 4, the chosen row, who chose and the date; the JSON holds the same under 'decision'; tests/agents/test_trade_planner.py::TestRuleTable::test_table_equals_the_decision_record and tests/agents/test_agent_orchestrator.py::TestConvictionLadder::test_ladder_equals_the_decision_record pass (RISK_RULES and CONVICTION_LADDER equal the 'decision' block field for field); with the 'decision' block absent both tests fail, so the code cannot merge ahead of the choice"
  - "V4 a rule counts only when its evidence allows it: tests/agents/test_trade_planner.py::TestRuleTable passes: compute_rule_flags(plan, direction) reads unit, comparison, threshold and severity from RISK_RULES (replacing a rule's threshold in the table under monkeypatch moves the step at which it fires); each rule is tested one step either side of the threshold the table holds, parametrised from the table and not typed; rule_may_warn(evidence) is true only when both groups meet the floors of Design 4 and the range lies wholly below zero on the fitting sessions and the holdout sessions; test_every_warn_rule_passes_its_own_evidence fails for a table holding a warn rule whose evidence does not pass; a rule with severity info is published with its number and is not counted by _calibrate_conviction; fails on the predecessor's main, where the thresholds are literals in compute_rule_flags"
  - "V5 the stop rules cannot contradict each other: tests/agents/test_trade_planner.py::TestRuleTable::test_some_stop_is_free_of_stop_warnings passes: for every ATR from 0.5 to 3.0 percent of price in steps of 0.05 (the 250-day range read was 0.78 to 2.42) there is a stop distance for which no stop-distance rule of RISK_RULES fires; run against the thresholds of lib/agents/prompts.py on origin/main 133717b1a (stop under 1.0 ATR, stop over 1.0 percent) the same check fails for every ATR above 1.0 percent of price"
  - "V6 a more confident call never scores lower: tests/agents/test_agent_orchestrator.py::TestConvictionLadder::test_monotone passes: over confidence 0.00 to 1.00 in steps of 0.01, agreement 0 to 6, warns 0 to 4 and FTFC aligned or not, raising confidence, raising agreement, aligning FTFC or removing a warning never lowers the level; ::test_flat_and_block_stay_low passes; fails on origin/main 133717b1a, where confidence 0.71 with one warning returns low and 0.70 returns medium (run for this spec)"
  - "V7 the report says how its conviction was reached: tests/agents/test_agent_orchestrator.py::TestConvictionLadder::test_inputs_are_stored passes on the real run_insight_pipeline with only the model stubbed: report.conviction_inputs holds analyst_agreement_count, warn_count, block_count, confidence_score, ftfc_score, ftfc_aligned, rule_ids_fired, rule_table_version and ladder_version; _calibrate_conviction called with those stored values returns report.conviction; a brief row whose ftfc_score is null stores null, the level is computed as not aligned, and 0.0 appears nowhere; fails on origin/main, where the field does not exist and a missing score becomes 0.0 (lib/agents/orchestrator.py:554)"
  - "V8 no message quotes an effect the evidence does not hold: tests/agents/test_trade_planner.py::TestRuleTable::test_messages_cite_only_recorded_effects passes: no file under lib/agents/ holds '-31.1pp', '-24.9pp', '-18.8pp' or '-21.8pp'; a rule's message states its measured number (the stop distance, the R multiple) and, when the rule is a warn, the effect and n from its own evidence record"
  - "V9 the changed API response is tested: tests/api/test_insight_report_conviction_inputs.py passes, built as tests/api/test_insight_report_conservative_short.py is (canned bundle, the real run_insight_pipeline with only the model stubbed, the real _upsert_report into a captured connection, then the real router): GET /api/insights/report/IWM returns conviction and conviction_inputs, and the level recomputed from the returned inputs equals the returned conviction; a report stored before this change, without the field, is served unchanged; no network and no database"
  - "V11 rule N2 judges the average of the plan's targets (owner decision, 2026-11-16): tests/agents/test_trade_planner.py::TestRuleTable::test_n2_reads_the_average_of_the_targets passes: the N2 record of RISK_RULES names the metric mean_target_r, the mean of risk_metrics.target_r_multiples over every target the plan holds, and compute_rule_flags compares that mean with the threshold the table holds, never target_r_multiples[0]; with the table's N2 threshold set to 1.5 under monkeypatch, a short with entry 275.86, stop 277.41, ATR 4.874951 and targets 274.64, 273.42, 272.20 and 270.99 (IWM puts of 2026-11-16 at four quarters of ATR) has multiples 0.787, 1.574, 2.361 and 3.142 from compute_risk_metrics, a mean of 1.966, and no N2 flag although its first target is under 1.5R; a long with entry 278.92, stop 275.86 and targets 280.14, 281.36, 282.58 and 283.79 has a mean of 0.996 and N2 fires with a message that states the mean and the number of targets; a plan with one target has a mean equal to that target's multiple; a plan with no target or a null stop gives no N2 and is counted as unmeasurable, never 0; no file under lib/agents/ compares target_r_multiples[0] with a threshold; fails on the predecessor's main, where N2 reads the first target"
  - "V10 the product record: docs/product/02-FEATURE-CATALOG.md FEAT-INSIGHT-001 record shows Status and Last reviewed moved and docs/product/12-PR-ISSUE-TRACEABILITY.md lists this PR under FEAT-INSIGHT-001"
status: draft
supersedes: null
---

# AI Insights: a conviction level that can be reached

## Authority and status

Draft. Not approved. Nothing here is built until the owner says approved.

The owner (T) asked for this spec on 2026-11-16, after the finding below was verified, and agreed with this recommendation: build the approved insight spec as it is, and decide the conviction thresholds separately, with the numbers measured again on more data. The owner's words were relayed in the task brief and are not quoted here.

Decided by the owner on 2026-11-16, in chat, as relayed to the session that recorded it (the chat itself was not read there). The quoted words are the owner's:

- "Agree with high conviction recommendations", said earlier the same day on this spec's recommendations.
- On rule N2, after seeing the ATR quarter-target experiment: "agree with judge reward on the average of the four targets, which is what you bank if the plan completes." Design 6 and done_when V11 specify it.
- "Mark specs ready if they are ready and resolve any conflicts. Keep the work moving. Auto merge." Each numbered decision that has a recommendation is therefore decided per that recommendation, and says so in its own line. A production step stays a step the owner approves at the time it is run, exactly as written.

**Why this spec is still a draft.** Decision 4 (the two stop rules, N1 and C1) has no recommendation: the table that decides it is produced by the measurement, which has not run. The owner said the thresholds are decided separately, with the numbers measured again. So decision 4 stays open, and with it every threshold: no line, N2's included, is chosen until the measurement has run and the owner has chosen (V3). Everything else is decided.

So this spec picks no threshold. It defines how each rule is measured, the rule the owner applies to the result, and the code change that follows. Every threshold that ends up in the code comes from the measurement and the owner's choice (done_when V3).

## Scope

- SPY, QQQ and IWM only.
- The five numeric risk rules (N1, N2, N3, C1, C2; N3 is informational and stays so) and the conviction ladder (`low`, `medium`, `high`).
- This spec lands after `docs/superpowers/specs/2026-11-16-feat-insight-001-insight-one-plan-one-voice.md` (approved, called "the predecessor" below) is merged and deployed. It changes two functions the predecessor leaves on `main`: `compute_rule_flags(plan, direction)` in `lib/agents/trade_planner.py` (created by the predecessor's Task 5) and `_calibrate_conviction` in `lib/agents/orchestrator.py` (moved ahead of the portfolio manager by its Task 7). It adds one optional field to the report, `conviction_inputs`.
- It does not contradict the predecessor. The predecessor's Non-goals say "No change to `_calibrate_conviction`'s rules or thresholds, to the risk rules' thresholds", and its decision 7 says to "decide the threshold in its own spec with its own evidence". This is that spec.
- Code references are to `origin/main` 133717b1a (2026-11-16). Each claim is marked **read** (the file or table was read) or **run** (code or a query was executed and the output kept). Every production read was made with `scripts/db_query_cr.sh` without `--commit`.

## In plain words, for the owner

- The report has never said `high`. In the last 180 days it said `low` 347 times, `medium` 40 times and `high` 0 times.
- The main cause is the warnings, not the ladder. One rule warns when the stop is closer than 1 ATR. Another warns when the stop is further than 1 percent of price. For IWM and QQQ, 1 ATR has been more than 1 percent of price on every one of the last 250 trading days, so every possible stop trips at least one of the two.
- It gets worse when the insight starts using the brief's plan (the approved work). The brief's stops sit at real levels and are tight: the middle stop is about 0.4 ATR away. On 750 brief plans since May, 748 would trip one of those two rules.
- The warnings quote win-rate numbers ("-31.1pp" and so on) that came from 36 days in the spring, measured on a different stop and a different kind of trade than the plan the report shows.
- There is also a plain bug: a call the model is more sure about can score lower than one it is less sure about.
- What the stored data can already say: the "stop too tight" idea looks real, but well below 1 ATR. Plans with a stop under a quarter of an ATR won 18 of 49. Plans with a stop between a quarter and a full ATR won 76 of 111. That is a first look on a small sample, not the answer.
- What this spec asks you to decide, after the measurement runs: for each rule, keep it, move its line, change its unit, or stop counting it. And for the ladder, which of three repairs to use.

## Capability

- Catalog row FEAT-INSIGHT-001 (`docs/product/02-FEATURE-CATALOG.md:25`, record `:279`), **read**.
- Requirements, **read** in `docs/product/01-PRODUCT-REQUIREMENTS.md`: REQ-DATA-001 (no silent fallback: a missing FTFC score is not 0.0), REQ-DATA-003 (a derived record names its source: `conviction_inputs`, the evidence record on each rule), REQ-LLM-001 (facts apart from interpretation: computed rules apart from reviewer notes), REQ-REPLAY-001 (outcomes come from the production resolver, no hand-built simulation), REQ-VALID-001 (no baseline frozen before the inputs are repaired: the measurement is rerun on the brief's rule version in force).

## Decisions for the owner

Decisions 1, 2, 3, 5, 7, 8 and 9 are decided per their recommendations, owner 2026-11-16: keep the work moving. Decision 6 is a production write or a spend and stays a step the owner approves when it is run. Decision 4 is open: it has no recommendation and waits for the measurement. One more decision was made by the owner and is not in this list: what rule N2 reads (Design 6). Striking a decision changes only the section named.

1. **The outcome that defines "worse"** (Design 1). Decided per the recommendation, owner 2026-11-16: keep the work moving. Recommended: R earned by the brief's own plan on the day (profit or loss divided by the distance to the stop), with win rate shown beside it. Alternative: win rate alone, as the spring audit used; a tight stop loses more often and loses less each time, so win rate alone can condemn a rule that costs nothing.
2. **How sure is sure enough** (Design 4). Decided per the recommendation, owner 2026-11-16: keep the work moving. Recommended: a rule counts as a warning only when the flagged plans did worse with a 95 percent range that stays below zero, on at least 30 filled plans from at least 20 sessions in each group, and again on the most recent third of sessions held back from the fitting. Alternative: a looser bar (90 percent, or no holdout); more rules would count, on thinner proof.
3. **What happens to a rule the data cannot judge** (Design 4). Decided per the recommendation, owner 2026-11-16: keep the work moving. Recommended: it is shown with its number and does not count toward conviction, until a rerun can judge it. Alternative: it keeps counting as today; `high` then stays out of reach.
4. **The two stop rules, N1 and C1** (Design 2, table 3). Open: no recommendation was made, and the owner decides the thresholds separately, on the numbers measured again. Choose one of: both in ATR units; both in percent of price; one band that counts as a single warning. The table that decides is produced by the measurement; the counts already read are in Design 2.
5. **The ladder repair** (Design 3). Decided per the recommendation, owner 2026-11-16: keep the work moving. That is candidate A now; B or C is a later decision, on the stored inputs. Choose one of candidates A, B, C. Recommended: A now (it is the only one the stored data can check), and B or C only once `conviction_inputs` has been stored for long enough to measure them.
6. **Growing the sample before deciding** (Design 1). Not decided here and not open as a design question: it stays a step the owner approves when it is run, exactly as written. Each is a production write or a spend, and none runs without your yes: (a) score again the 174 brief plans that an early version of the scorer left without a fill status, and the 66 never scored; (b) brief replays for sessions before 2026-05-12. Recommended: (a) first; it adds up to 240 plans for no model spend. Whether the scorer can be run for a past date range was not checked.
7. **Whether replay rows count** (Design 1). Decided per the recommendation, owner 2026-11-16: keep the work moving. `premarket_analysis` holds 135 replay rows beside the 390 live ones. Recommended: live rows only for the decision, replay rows shown as a separate line.
8. **One PR with a stop in the middle, or a note first** (Approaches). Decided per the recommendation, owner 2026-11-16: keep the work moving. The stop in the middle is where decision 4 and the thresholds are chosen. Recommended: one PR that opens as a draft with the measurement and the evidence file, waits for your choices, then adds the rule table and the ladder. Alternative: run the measurement as a spike note first and approve this spec after it.
9. **Position size follows conviction** (Risks). Decided per the recommendation, owner 2026-11-16: keep the work moving. Once `medium` and `high` occur, the published size changes (`_SIZE_BY_CONVICTION`, `lib/agents/trade_planner.py:140-144`). Recommended: accept it; that is what the levels are for. Alternative: hold sizes at the `low` row until the levels have been shown to separate outcomes.

## Problem

### 1. `high` cannot be reached, and one input alone guarantees it

The ladder, **read** at `lib/agents/orchestrator.py:912-943` and **run** over a grid of inputs for this spec:

| Level | Needs |
|---|---|
| `high` | 4 or more of 6 analysts agree, FTFC aligned with the direction, zero warnings, confidence 0.7 or more |
| `medium` | 2 or more agree, at most 1 warning, confidence from 0.4 to 0.7 inclusive |
| `low` | everything else, and always when flat or blocked |

The numeric rules, **read** at `lib/agents/prompts.py:190-232`:

| Rule | Fires when | Unit | Effect quoted in the message |
|---|---|---|---|
| N1 | stop distance under 1.0 | ATR | -31.1pp |
| C1 | stop distance over 1.0 | percent of price | -24.9pp |
| N2 | first target under 1.5 | R | -18.8pp |
| C2 | long, entry more than 10 above the 200 SMA | percent | -21.8pp |
| N3 | direction against FTFC | flag | none; severity `info`, so it never counts |

N1 and C1 together leave a stop only when 1 ATR is at most 1 percent of price. Production, 250 trading days to 2026-11-13 (**run**, db-query-6m5zv):

| Ticker | ATR as percent of price: min | median | max | Days at or under 1.0 |
|---|---|---|---|---|
| IWM | 1.08 | 1.67 | 2.42 | 0 of 250 |
| QQQ | 1.18 | 1.64 | 2.40 | 0 of 250 |
| SPY | 0.78 | 1.10 | 1.64 | 87 of 250 |

The stored reports, 180 days to 2026-11-16 (**run**, db-query-6m5zv): 387 reports over 372 ticker-days. IWM 110 low and 24 medium; QQQ 119 and 8; SPY 118 and 8. In total 347 low, 40 medium, 0 high.

Why each report landed where it did (**run**, db-query-tmj42, the same 387):

| | Count |
|---|---|
| 2 or more warnings | 306 |
| exactly 1 warning | 80 |
| no warning | 1 |
| confidence under 0.4 | 2 |
| confidence from 0.4 to under 0.7 | 383 |
| confidence exactly 0.7 | 0 |
| confidence over 0.7 | 2 |
| a block | 0 |

So `high` fails twice over: one report in 387 had no warning, and two in 387 had the confidence it needs. All 40 mediums had exactly one warning. Another 39 reports had one warning and confidence in the band and still came out low; by the code that happens only when fewer than 2 analysts agreed. That is an inference from the function, because the agreement count is not stored.

The plans inside the stored reports (**run**, db-query-tmj42): 151 of the 387 reports hold persona plans with risk metrics (236 hold an empty list, the last on 2026-09-15; why was not checked). On the neutral plan, N1 or C1 fired on 51 of 51 for IWM, 50 of 50 for QQQ and 26 of 50 for SPY. N2 fired on every neutral and every conservative plan, 302 of 302.

### 2. On the brief's plan it is close to absolute

The predecessor makes the insight publish the brief's plan. Its decision 7 already records that N1 fires on all three tickers on 2026-11-16. Measured over every live brief row that holds a trigger, a stop and an ATR (**run**, db-query-6l46h, db-query-mswnw and db-query-8b2r9): 750 plan sides over 126 sessions, 2026-05-12 to 2026-11-16.

| | IWM | QQQ | SPY | All |
|---|---|---|---|---|
| Plan sides | 252 | 250 | 248 | 750 |
| N1 only | 212 | 184 | 227 | 623 |
| C1 only | 16 | 14 | 12 | 42 |
| Both | 24 | 52 | 7 | 83 |
| Neither | 0 | 0 | 2 | 2 |
| Stop distance in ATR: 10th, 50th, 90th percentile | 0.14, 0.39, 0.76 | 0.18, 0.40, 0.83 | 0.17, 0.34, 0.72 | |
| Stop distance in percent: 10th, 50th, 90th | 0.19, 0.57, 1.10 | 0.29, 0.67, 1.63 | 0.15, 0.37, 0.84 | |

N2 would fire on 585 of the 721 sides that hold a first target. Of the 162 sides that filled, none is free of N1, C1 and N2 together. These counts use the brief's structured columns (`calls_trigger_price`, `calls_stop_price`, `calls_t1_price`, `atr14` and the put mirrors); the predecessor reads the side records inside `level_basis`, and the two were not compared.

### 3. A more confident call can score lower

**Run** on `origin/main` 133717b1a: `_calibrate_conviction(direction="long", analyst_agreement_count=4, ftfc_score=0.8, risk_severities=["warn"], confidence_score=c)` returns `medium` at c = 0.70 and `low` at c = 0.71. The same happens with no warning whenever one `high` condition is missed: agreement 3 at 0.71 is `low`, at 0.70 `medium`; agreement 6 with FTFC not aligned at 0.85 is `low`, at 0.55 `medium`. `medium` has a ceiling of 0.7 and nothing catches what falls between.

In the stored 180 days this touched at most one report: the single report with no warning had confidence over 0.7 and FTFC aligned and was published `low`. No stored report had one warning and confidence over 0.7. The bug is real in the code and rare in the data, because confidence almost never leaves 0.4 to 0.7.

### 4. What the quoted effects were measured on

`docs/audits/2026-05-10-risk-reviewer-validation.md`, **read** in full:

- Window 2026-03-19 to 2026-05-08, 36 trading days, SPY, IWM and QQQ, after replaying the brief and the insight for each day.
- The four numbers come from its section 4: the win rate of `signal_alerts` fires that were aligned with the plan's direction, on days with a flag against days without. N1: 40.4 percent of 178 alerts against 71.5 percent of 172. C1: 44.6 of 193 against 69.4 of 157. C2: 39.0 of 82 against 60.8 of 268. N2: 48.4 of 213 against 67.2 of 137.
- The flags were the model's own written flags, matched to tags by pattern. The same audit, section 3, found the model's "stop under 1 ATR" flag had 44.4 percent precision and 22.2 percent recall against the computed distance. So "-31.1pp" describes days when the model wrote that flag, and on more than half of those days the stop was not under 1 ATR.
- The outcome is intraday signal alerts, not the plan. The plan's own entry, stop and target were never followed.
- The unit is the alert: 350 aligned alerts with exits, on at most 37 ticker-days. Alerts on one day share one flag and one market. The audit gives no range. Treated as independent, the N1 difference would carry about plus or minus 10 points (arithmetic on the audit's counts); they are not independent, so the true range is wider and was not computed.
- The stop it judged was the old planner's stop (a multiple of ATR from an entry midpoint). The predecessor replaces that stop with the brief's.
- The 1.0 ATR, 1.0 percent and 1.5R lines were the lines already in the prompts; the audit did not search for them. Only C2's 10 percent came from buckets (23, 117 and 199 alerts).
- The same table shows a "stop too wide" flag with a win rate 32.5 points better on 8 alerts, marked insufficient.
- Its data files were in `/tmp` and are gone, so it cannot be rerun as it was.

### 5. The ladder's inputs are not stored

The report JSON keys (**run**, db-query-6m5zv, 591 stored reports for the three tickers): `conviction`, `confidence_score`, `direction`, `risk_flags` (persona, severity, message), `strat_status` and `persona_plans` are there. The analyst agreement count is not, in the report or in `insight_runs` (**read**, `gcp/schema.sql:1590-1602`); it is only logged. A stored flag has no rule id, so a computed rule cannot be told from a reviewer's note. The predecessor adds that the trader's confidence is not stored either.

## Non-goals

- No threshold chosen by opinion, in this document or in the code.
- Nothing the predecessor owns: the brief row as the source, the plan, the order of the tiers, the price checks, max pain, key level order.
- No change to the brief, to its stops or targets, or to `lib/strat_levels.py`.
- No change to the FTFC weights, to `is_ftfc_aligned`, or to the blocking rule (a block still makes the direction flat).
- No change to `_SIZE_BY_CONVICTION` or the conservative gates.
- No change to the signal monitor's direction gate. `lib/strategies/insight_cache.py:168-190` says its matrix does not read conviction (**read**, not run).
- No new model call, no schema change (`conviction_inputs` is a field of the report JSON), no Discord layout change, no new scheduled job.
- No tickers beyond SPY, QQQ and IWM.
- No production write from the implementation PR.

## Approaches considered

1. Measure each rule on the brief's own plans and their scored outcomes, let the result and the owner set the table, and make the ladder monotone (chosen).
2. Pick new lines now (for example N1 at 0.25 ATR): refused by the owner's decision of 2026-11-16; the first look in Design 2 is 162 fills.
3. Repeat the spring audit's method on the 3,161 live alerts now stored: it would still judge alerts and not the plan, and the predecessor changes the stop the rules look at.
4. Make every numeric rule informational and leave the ladder alone: `high` would then rest on the model's confidence, which reached 0.7 in 2 of 387 reports.
5. Fix only the ceiling on `medium`: changes at most 1 of 387 stored reports (Design 3).
6. Measure in a spike note and approve afterwards (decision 8): keeps the PR simpler; the measurement would not be rerunnable code.

## Design

### 1. The measurement

**Sample.** One row per brief plan side: ticker, session, long or short, from live `premarket_analysis` rows. Read on 2026-11-16 (**run**, db-query-6l46h, db-query-tmj42, db-query-8b2r9):

| | Count |
|---|---|
| Live brief rows, three tickers, 2026-04-12 to 2026-11-16 | 390 |
| All sides of those rows (two per row) | 780 |
| of them, scored with a fill status (scorer versions 2026-11-11.v2 and 2026-11-12.v3) | 540 |
| of them, scored by 2026-05-11.v1, no fill status | 174 |
| of them, not scored | 66 |
| Plan sides with trigger, stop and ATR | 750 over 126 sessions |
| Sides that filled | 162 over 67 sessions, 2026-05-18 to 2026-11-13 (IWM 55, QQQ 53, SPY 54) |
| Filled, long | 70 |
| Filled, FTFC aligned with the side | 51 |
| Filled, long and more than 10 percent above the 200 SMA | 43 |
| Filled, first target under 1.5R | 132 |

The decision sample today is the 162 filled sides. The exit plan in thirds (`calls_plan_r`, `puts_plan_r`) is scored `ok` on 0 live sides: 264 rows read `targets_unavailable` and 126 are unscored, so it cannot be the outcome yet. Decision 6 is how the sample grows.

Other stored outcomes, for the record: 3,161 live `signal_alerts` with exits over 366 ticker-days, 2026-05-01 to 2026-11-16, and 432 backfill alerts, 2026-03-19 to 2026-04-13 (**run**, db-query-6l46h). They are what the spring audit used and are shown as a second line only.

**Outcome.** For a filled side, the brief's traded outcome under rule cross-fill-t1-v1 (`gcp/schema.sql:1952-1963`, **read**): entry at the trigger, exit at the stop, the first target or the close. `outcome_r` is `eod_pnl_pct` divided by `stop_distance_pct`. Primary measure: mean R. Beside it: win rate (`eod_pnl_pct > 0`) and the share of exits at the stop. That `puts_eod_pnl_pct` is positive for a winning short was not checked; V1's fixture pins the sign.

**What the outcome is, and is not.** The measurement's outcome is a first-target surrogate, and it is named so wherever a result is recorded: `cross-fill-t1-v1`, the whole position out at the first of the stop or the first target, else at the close. It is not the performance of the brief's exit plan in thirds (`calls_plan_r`, `puts_plan_r`) or of the four-quarter exit plan, and no table or record of the measurement labels it so. N2's `mean_target_r` (Design 6) is a reward the plan banks only if it completes; the measurement judges it on this surrogate. Any claim about the R the plan actually earns needs a separately qualified outcome from the production resolver (`gcp/premarket_playbook_resolver.resolve_plan`) and a population matched to the brief's rule version, which this spec does not provide. Unchanged by this: the null and sign fixtures of V1, the structured-columns versus `level_basis` reconciliation (Problem 2 and What was not verified: the two were not compared) and the per-version evidence gate (V2's rule version, Design 6, close-out 5).

**Unit and range.** The unit is the side; the three tickers share a session, so the range is a bootstrap that resamples sessions, 10,000 draws, fixed seed, 95 percent. Win rates also carry a Wilson range.

**Grid, written down before the run.** Each rule is measured at its present line and at these points, and nowhere else: stop too tight in ATR at 0.25, 0.5, 0.75, 1.0; stop too wide in ATR at 1.0, 1.5, 2.0; stop too tight in percent at 0.1, 0.25, 0.5; stop too wide in percent at 0.5, 1.0, 1.5; reward against the stop (N2) on the average of the side's targets at 1.0R, 1.5R, 2.0R, with the first target's multiple at the same three points shown beside it for the record only (Design 6); above the 200 SMA at 5, 10, 15 percent. N3 is informational today and is measured at its one setting, for the record only. These are candidates to test, not answers.

**Holdout.** Sessions are split by date: the earliest two thirds fit, the latest third confirms.

**How it runs.** `gcp/queries/conviction_rule_evidence.sql` returns the side rows with no threshold in it. A new module `lib/agents/rule_evidence.py` (pure functions, V1) builds the measures through `compute_risk_metrics`, so the measurement and the report share one formula, and prints the tables. No fill is simulated: every outcome is the production scorer's (REQ-REPLAY-001). It reads; it writes nothing.

### 2. What the measurement must produce for the rules

Every outcome column the measurement writes, here and in the outcome by level of Design 3, is headed with its outcome, `cross-fill-t1-v1`, the first-target surrogate of Design 1; none is labelled as the performance of the exit plan in thirds or of the four-quarter exit plan.

Table 1, the sample, as above, with the brief's rule version per row.

Table 2, one line per rule and grid point: flagged n and sessions, unflagged n and sessions, mean R of each, the difference with its range, win rates, the holdout's difference with its range, and the verdict of Design 4.

Table 3, the N1 and C1 candidates. What each would have flagged on the 750 sides already read (**run**, db-query-mswnw); the outcome columns are filled by the measurement:

| Candidate | Line | Flagged of 750 | IWM | QQQ | SPY |
|---|---|---|---|---|---|
| Today: N1 in ATR, C1 in percent | under 1.0 ATR or over 1.0 percent | 748 (83 carry two warnings) | 252 | 250 | 246 |
| Both in ATR: too tight | under 0.25 | 191 | 65 | 51 | 75 |
| | under 0.5 | 527 | 176 | 167 | 184 |
| | under 0.75 | 674 | 226 | 220 | 228 |
| | under 1.0 | 706 | 236 | 236 | 234 |
| Both in ATR: too wide | over 1.0 | 44 | 16 | 14 | 14 |
| | over 1.5 | 12 | 2 | 6 | 4 |
| Both in percent: too tight | under 0.1 | 12 | 0 | 2 | 10 |
| | under 0.25 | 124 | 38 | 16 | 70 |
| | under 0.5 | 366 | 107 | 80 | 179 |
| Both in percent: too wide | over 0.5 | 384 | 145 | 170 | 69 |
| | over 1.0 | 125 | 40 | 66 | 19 |
| | over 1.5 | 52 | 13 | 33 | 6 |
| One band, one warning | outside the chosen pair of lines | the two lines' counts, counted once per side | | | |

A percent line treats the three tickers differently (SPY's median stop is 0.37 percent, QQQ's 0.67); an ATR line does not. That is the trade the owner weighs in decision 4.

A first look, not the measurement (**run**, db-query-8b2r9; simple ranges, sessions not clustered, no holdout):

| Stop distance | Filled | Won | Win rate, Wilson 95 percent | Mean R |
|---|---|---|---|---|
| under 0.25 ATR | 49 | 18 | 37 (25 to 51) | -0.29 |
| 0.25 to 0.5 | 70 | 47 | 67 (56 to 77) | 0.01 |
| 0.5 to 0.75 | 32 | 22 | 69 (51 to 82) | -0.02 |
| 0.75 to 1.0 | 9 | 7 | 78 (45 to 94) | -0.02 |
| 1.0 or more | 2 | 1 | 50 (10 to 91) | -0.06 |
| All | 162 | 95 | 59 (51 to 66) | -0.09 |

Two things it shows about method. N1 at 1.0 ATR cannot be tested as written: 160 of 162 fills are flagged and 2 are not. And win rate and mean R disagree in the middle rows, which is why decision 1 recommends R.

### 3. The ladder

**What the levels should mean**, in words a trader would use:

- `low`: something measured counts against the plan, or the analysts do not back it, or the model is unsure. Also flat and blocked.
- `medium`: nothing more than one measured warning, some agreement, a confident call.
- `high`: the analysts agree, the timeframes line up with the direction, no measured warning, a confident call.

Three properties are required whatever lines are chosen: every level can occur (V5 and the evidence file's reach table), more evidence never lowers the level (V6), and the report stores what it used (V7).

**Candidates for the ceiling bug.**

- A. Remove the ceiling: a level is the highest one whose floors are all met. Nothing else moves.
- B. A, and the confidence and agreement floors are set from the stored distribution of `conviction_inputs` once it exists.
- C. A, and only computed rules that passed their evidence count as warnings; a reviewer's written note is published and counts for at most one.

N3 is already informational (`lib/agents/prompts.py:234-238`, **read**), so FTFC is counted once, by the ladder. That stays.

**How the stored 387 reports would have looked** (**run**, db-query-tmj42, bounds because the agreement count is not stored):

| Candidate | Low | Medium | High |
|---|---|---|---|
| Today (actual) | 347 | 40 | 0 |
| A | 346 or 347 | 40 or 41 | 0 or 1 |
| B | not measurable from stored data: the floors need agreement and the trader's confidence, neither stored | | |
| C | not measurable from stored data: a stored flag has no rule id | | |
| Any candidate, with the warnings recomputed from a chosen rule table | not measurable from stored data for reports; measurable for the brief's 750 sides as "sides with no counted warning", which the evidence file reports per candidate as the ceiling on `high` | | |

A alone moves at most one stored report. The ladder repair is needed for correctness; reach comes from the rules.

**Do the levels separate outcomes today?** Joined to the brief side that matches the report's direction (**run**, db-query-tmj42): 80 ticker-days with a fill. `low` won 46 of 70, 66 percent (54 to 76); `medium` won 7 of 10, 70 percent (40 to 89). The ranges overlap almost wholly. Nothing is known yet, and the evidence file says so in those words.

**Stored going forward.** `InsightReport.conviction_inputs` (optional): `analyst_agreement_count`, `warn_count`, `block_count`, `confidence_score`, `ftfc_score`, `ftfc_aligned`, `rule_ids_fired`, `rule_table_version`, `ladder_version`. A null FTFC score is stored as null and treated as not aligned.

### 4. The decision rule, and the code that follows

**Per rule, applied to table 2.** Floors: at least 30 filled sides from at least 20 sessions in each group (decision 2).

| Result | Verdict | Code |
|---|---|---|
| At its present line, flagged is worse, the range is wholly below zero, on the fitting sessions and on the holdout | keep | the rule stays `warn` at that line |
| The present line fails, and exactly one grid point of the same unit passes both | change its threshold | `warn` at that point |
| The present unit has no passing point and another unit's grid has one | change its unit | `warn` in the new unit |
| More than one point or unit passes | owner chooses among the passing rows only | as chosen |
| Nothing passes, or a group is under the floor | cannot be judged | severity `info`: shown, not counted (decision 3) |
| Flagged is better, range wholly above zero | drop | removed, and reported to the owner; never turned into a bonus here |

For N1 and C1 the chosen rows must also pass V5: some stop must be free of both at every ATR the tickers have shown.

**For the ladder.** The owner picks A, B or C (decision 5). B and C can be picked only when the evidence file can fill their rows.

**Code, after the predecessor is on `main`.**

- `lib/agents/trade_planner.py`: `RISK_RULES`, a tuple of frozen records (id, metric, unit, comparison, threshold, severity, direction it applies to, evidence). The evidence record holds the outcome it was measured on (`cross-fill-t1-v1`, Design 1), the execution id, measured-on date, both group sizes and session counts, the effect and its range, the holdout result, who decided and when. `compute_rule_flags(plan, direction)` keeps its signature and return shape and reads the table; it holds no number of its own. N2's metric in the table is the mean of the plan's target R multiples (Design 6). `rule_may_warn(evidence)` is the decision rule as a pure function.
- `lib/agents/orchestrator.py`: `_calibrate_conviction` keeps its signature; it returns the highest level of `CONVICTION_LADDER` whose floors are met, counts only `warn` flags, and builds `conviction_inputs`.
- `lib/agents/schema.py`: `InsightReport.conviction_inputs`; the win-rate figures leave the field descriptions (V8).
- `lib/agents/rule_evidence.py` and `gcp/queries/conviction_rule_evidence.sql`: the measurement.
- `docs/audits/<run date>-conviction-rule-evidence.md` and `tests/agents/fixtures/conviction_evidence.json`: the evidence and the decision.
- Tests: `tests/agents/test_rule_evidence.py`, `tests/agents/test_trade_planner.py::TestRuleTable`, `tests/agents/test_agent_orchestrator.py::TestConvictionLadder`, `tests/api/test_insight_report_conviction_inputs.py`.

### 5. Capacity (CLAUDE.md rule 0)

- No Cloud Run job, schedule or model call is added or changed.
- The measurement: one read of 390 rows (about 780 sides), one round trip through the existing `db-query` job, 5 to 15 seconds as dispatched for this spec; the bootstrap is 10,000 draws over at most 126 sessions in memory.
- The report grows by one small JSON object. Cost of the measurement in model spend: none.

### 6. Rule N2 judges the average of the plan's targets (owner decision, 2026-11-16)

**The decision.** The reward is judged on the average of the plan's targets, against the stop distance: "what you bank if the plan completes". For four quarters at 25, 50, 75 and 100 percent of ATR the average target is (0.25 + 0.50 + 0.75 + 1.00) / 4 = 0.625 ATR from the trigger. The owner decided what N2 reads. The line it is compared with (1.5R today) is not decided here: like every threshold it comes from the measurement and the owner's choice (V3).

**What the code does today** (**read** on `origin/main` c9a2b984d):

- N2 is text in the neutral reviewer's prompt, `lib/agents/prompts.py:228-233`: "IF len(risk_metrics.target_r_multiples) >= 1 AND risk_metrics.target_r_multiples[0] < 1.5" gives a `warn` whose message reads "T1 only {r:.1f}R". It reads the first target alone.
- `target_r_multiples` is built by `compute_risk_metrics`, one multiple a target: the target's distance from the entry midpoint over the entry-to-stop distance, signed by direction and rounded to 3 places (`lib/agents/trade_planner.py:382-386`). No mean is stored (`lib/agents/schema.py:177`).
- `_calibrate_conviction` (`lib/agents/orchestrator.py:887-942`) reads no target and no R multiple. It counts `warn` severities (`:919`); `high` needs none (`:932`) and `medium` at most one (`:938`). The severities come from the reviewers' flags (`:504-506`, `:555`). So N2 reaches conviction only as one counted warning, and the ladder itself needs no change for this decision.
- The `RiskMetrics` docstring states the old rule as "any t_r_multiple < 1.5" (`lib/agents/schema.py:156`).
- The predecessor moves N2 into `compute_rule_flags` as "first target under 1.5R" (its Design, **read**; not on `main`).

**What changes.**

- `RISK_RULES`' N2 record names the metric `mean_target_r`: the mean of `risk_metrics.target_r_multiples` over every target the plan holds. Each leg is an equal share (`exit_legs`), so with a target for every leg that mean is the plan's R when every target is reached.
- `compute_rule_flags` computes that mean and compares it with the table's threshold. It never reads `target_r_multiples[0]` for a rule. `compute_risk_metrics` and `RiskMetrics` do not change: the multiples stay as they are and the mean is derived where the rule is applied, so the report's schema gains nothing for it.
- N2's message states the mean and the number of targets, and no longer "T1 only".
- A plan with no target, or with no stop, has no mean: no N2 flag, counted as unmeasurable, never 0 (REQ-DATA-001; the predecessor's D5b already makes the multiples empty for a null stop).
- The `RiskMetrics` docstring line is rewritten with the win-rate figures V8 removes.
- The measurement (Design 1) measures N2 on that mean, on its grid, with the first target's multiple beside it for the record. Its verdict follows Design 4 like any rule's.
- `_calibrate_conviction` is not changed by this decision beyond Design 3.

**Checked on the owner's example** (**run** for this spec with `compute_risk_metrics` on `origin/main` c9a2b984d, ATR 4.874951, the IWM targets of `docs/superpowers/specs/2026-11-16-feat-strat-001-atr-quarter-targets.md`):

| Side | Entry | Stop | Targets | R multiples | First | Mean |
|---|---|---|---|---|---|---|
| IWM puts | 275.86 | 277.41 | 274.64, 273.42, 272.20, 270.99 | 0.787, 1.574, 2.361, 3.142 | 0.787 | 1.966 |
| IWM calls | 278.92 | 275.86 | 280.14, 281.36, 282.58, 283.79 | 0.399, 0.797, 1.196, 1.592 | 0.399 | 0.996 |

Against a 1.5R line the first target fails on both sides; the mean passes on the puts and fails on the calls, whose stop is 0.628 ATR away.

**Measured context.** From the ATR quarter-target spike of 2026-11-16, 3,463 replayed trades of SPY, QQQ and IWM, 2022-01-03 to 2026-11-10. Its files are session files under `/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/atr_exp/out/`, not in the repo; the ATR targets spec records the result and its limits. Quoted from `report_v1_side.txt`:

- "from the trigger, risk = trigger to stop: under 1.5R on 93.1% of 3463 trades; under 1.0R on 76.4%; median 0.69R; quartiles 0.49 / 0.98". That is T1 at 0.25 ATR, what N2 reads today.
- "stop distance in ATR (trigger to stop): median 0.36, quartiles 0.26 / 0.51".

From those numbers: the average of four targets is 0.625 ATR, so at the median stop it is 0.625 / 0.36 = 1.74R, where T1 alone is 0.25 / 0.36 = 0.69R. At the quartile stops it is 0.625 / 0.51 = 1.23R and 0.625 / 0.26 = 2.40R. Computed trade by trade for this spec from the spike's `arms_followup.csv` (0.625 x ATR over the trigger-to-stop distance; **run**): the median is 1.74R, 1,334 of 3,463 trades (38.5%) are under 1.5R and 478 (13.8%) under 1.0R.

**Limits, stated.**

- A plan with fewer targets than legs holds an unsold leg, so the mean of its targets is not what the plan banks. In the spike's replay of today's rule most traded sides were such plans ("arm A targets published per traded side: {0: 586, 1: 1056, 2: 1051, 3: 770}"). The mean is still taken over the targets the plan holds.
- The stored rows the measurement reads are level-rule rows. Rows built under the ATR marks do not exist yet, so N2 on a four-quarter plan starts with no evidence of its own: by decision 3 it is then shown with its number and not counted, until close-out 5 reruns the measurement on the new rule version.
- The figures above are from a replay whose limits the ATR targets spec lists (premarket window, the prior-close prints in its triggers). They are context for the decision, not this spec's evidence.

## Implementation plan: size

9 tasks, one branch, one PR, opened only after the predecessor's PR has merged.

1. The side query and its fixture.
2. `rule_evidence.py`: measures, summaries, the bootstrap, the verdicts (V1), N2's mean among the measures (V11).
3. The run, the evidence file and its JSON (V2). The PR stops here as a draft for the owner's choices.
4. The decision block (V3).
5. `RISK_RULES`, `rule_may_warn`, `compute_rule_flags` on the table, N2 on the mean of the targets, the messages (V4, V5, V8, V11).
6. `CONVICTION_LADDER` and the monotone `_calibrate_conviction` (V6).
7. `conviction_inputs` (V7).
8. The API response test (V9).
9. PR-body evidence, catalog and traceability (V10).

## Close-out

None of these runs from the implementation PR, and none is a `done_when` box. Each needs the owner's own yes.

1. **Deploy**: `./gcp/deploy.sh insights`, from `main` at or after the merge.
2. **Replay** a set of sessions the owner names, through `INSIGHT_AS_OF` as the predecessor's close-out does, and read back the levels and their `conviction_inputs`. This is a model spend; its size was not read.
3. **Read the distribution**, read-only: levels by ticker over the replayed sessions, and every report's level recomputed from its stored inputs.
4. **Browser proof**: the owner's runs against the deployed site for the insights report card, as AGENTS.md defines. The API response test is in the PR (V9).
5. **Rerun the measurement** when the filled sample has doubled, or when the brief's rule version changes, and bring any changed verdict to the owner as a new decision. Until then a rule marked "cannot be judged" stays shown and uncounted.
6. On a `docs/` branch after the merge: the plan's status and `docs/product/08-AI-AGENT-ARCHITECTURE.md`.

## Risks

- **The sample is small.** 162 fills over 67 sessions, all from one half year. Most rules may come back "cannot be judged". V4 makes that an honest outcome: the rule is shown and not counted.
- **Picking a line from a grid flatters it.** The grid is fixed in this spec and the holdout must agree; a line that passes only on the fitting sessions does not count.
- **The brief's stops will change.** A separate spec covers the brief's targets (`docs/superpowers/specs/2026-11-16-feat-strat-001-atr-quarter-targets.md`: four targets at quarters of ATR, chosen by the owner on 2026-11-16), and the brief's rule version is moving. N2 has no evidence on such plans until rows exist (Design 6). The evidence records the rule version it read, and close-out 5 reruns it (REQ-VALID-001).
- **`high` may still be rare.** If the measurement keeps a tight-stop rule near where most stops sit, most plans still warn. The evidence file's reach table shows this before the owner chooses.
- **`high` may become common.** If most rules cannot be judged, few warnings count and the level rests on agreement, FTFC and confidence. Decision 3 is where the owner accepts or refuses that.
- **Sizes change with the level** (decision 9).
- **Readers of the level.** The Discord push, the API and solyra show it; the signal gate's docstring says it does not use it. A reader that treats `medium` or `high` specially was not searched for outside `lib/`, `gcp/` and `platform/api/`.
- **The trader's confidence may sit in a narrow band**, as the portfolio manager's does (383 of 387 between 0.4 and 0.7). Then no confidence floor separates anything, and candidate B has nothing to work with. `conviction_inputs` is what will show it.
- **Old reports lack `conviction_inputs`.** They are served as stored (V9).

## What was not verified

- The owner's words of 2026-11-16: relayed; the chat was not read.
- The spike's figures in Design 6: quoted from its report file and computed from its per-trade file; the spike was not run again, and its files are not in the repo.
- N2 on the mean for the 750 stored brief sides and the 162 fills: not computed; the counts in Problem 2 and Design 1 are for the first target.
- The predecessor's code: `compute_rule_flags` and the reordered `_calibrate_conviction` do not exist on `origin/main` 133717b1a. Their shapes are taken from the predecessor's spec and plan, **read**, not run.
- That the stop on `main` today is a multiple of ATR from an entry midpoint: taken from the predecessor's Problem table (`lib/agents/trade_planner.py:279-281`), not read again.
- Whether the brief's structured stop and target columns equal the side records in `level_basis` that the predecessor will read: not compared.
- The sign of `puts_eod_pnl_pct` for a winning short: not checked.
- Why 236 of the 387 stored reports hold an empty `persona_plans`: not checked.
- Why the exit plan in thirds reads `targets_unavailable` on every scored live side: not checked.
- Whether the brief's scorer can be run for past dates, and what scoring the 240 unscored or early-scored sides again would write: not checked (decision 6).
- That stored `risk_flags` and `confidence_score` are exactly the values the ladder used at the time: read at `orchestrator.py:556-562` and `:684` for confidence; the flag list was not traced to the stored field.
- The agreement count of any stored report: not stored. The "fewer than 2 analysts agreed" reading of 39 reports is an inference from the function.
- The trader's confidence: not stored; its distribution is unknown.
- A session-clustered range for any number in this spec: not computed. The ranges shown are Wilson ranges on counts, and the plus or minus 10 points on the audit's N1 figure is arithmetic that assumes independent alerts.
- The spring audit's own queries and files: gone from `/tmp`; its numbers are quoted from the document and were not reproduced.
- Whether the signal gate ignores conviction at run time: the docstring at `lib/strategies/insight_cache.py:168-190` was read; the code path was not run.
- solyra's use of the conviction level, and whether `InsightReport` is part of `platform/api/openapi.json`: not opened.
- Open GitHub issues about conviction: not searched; `issues` is empty for that reason.
- The cost of the close-out replay: not read.
- N3 and C2 on brief sides beyond the counts in Design 1: no outcome was read for them.
