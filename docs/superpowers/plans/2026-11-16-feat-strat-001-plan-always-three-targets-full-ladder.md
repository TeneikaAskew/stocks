---
feat_id: FEAT-STRAT-001
spec: docs/superpowers/specs/2026-11-16-feat-strat-001-plan-always-three-targets-full-ladder.md
branch: feature/feat-strat-001-plan-always-three-targets
pr: null
status: ready
---

# The exit plan always names three targets, close levels are one target, and the brief shows the full ladder: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the order of the spec's frontmatter, [0] to [11]. The map below names each.

**Goal:** Behind five policy rows seeded to reproduce today's plan, a side's close levels become one target zone, a leg with no target inside the window can be filled from an ordered list of sources, every side records and prints its whole ladder with roles, ATR strength notes and reach counts, and the resolver stores one number a side from which those counts come.

**Architecture:** All of it sits on the one level builder, `lib.strat_levels.build_session_levels`, behind a basis marker (`plan_ladder_status`), the pattern of `atr_rung_status` and `plan_target_level_types_status`. `_plan_targets` walks zones, then runs the fill steps, then `_plan_ladder` lists the ladder. The brief reads the reach history in one query and hands it to the builder as an input, recorded in `level_basis` like the premarket snapshot. `resolve_plan` gains one output, `mfe_atr`. Nothing changes a target until a later policy row does, and that row is the owner's.

**Tech Stack:** Python, pandas, numpy, SQLAlchemy `text()` through `gcp.database`, pytest (`monkeypatch`, SQLite `ParamsDb`), Postgres 15 (`pgvector/pgvector:pg15`) for the local copy of the Experiment.

**Spec:** docs/superpowers/specs/2026-11-16-feat-strat-001-plan-always-three-targets-full-ladder.md (approved, PR #1998, on `origin/main` 74c75923). Its code references are to `main` 060c89a0; `git diff --stat 060c89a0 74c75923 -- lib gcp tests scripts` is empty (run 2026-11-16), so its line numbers hold on the base this plan was written against. Rerun that diff against the base actually used.

## Scope: what is in this plan

One plan, one branch, one PR, 14 tasks. Every done_when item, [0] to [11], is in it. Nothing is split off and nothing is dropped.

Two clauses cannot be closed by the implementer alone, and the plan says so where they sit instead of leaving them out:

- done_when[9], the production path: "once the dry run of docs/superpowers/specs/2026-11-16-feat-playbook-001-brief-says-what-the-data-says.md is on main, arm A's targets for the sample sessions the owner allows, built by the deployed job with BRIEF_NO_PERSIST=true, equal the local build's and the run's level_basis shows the seeded policy rows were the ones read". It needs the brief spec's code merged and deployed, the owner's yes to each dry run, and the seeded rows in production. The section "done_when[9], and what is evidenced when" sets out the order (Task 13, Step 9).
- done_when[11]: "the five seeded rows, the calibration run for the three per-ticker keys and the two new columns are applied to production only after the owner's yes ... and the Design 9 rows that change the plan are inserted only after a second yes given on the Experiment's results". Those are the owner's steps (Close-out). See "Merge is a production schema change" below: on this repo the merge itself applies `gcp/schema.sql`.

## Order against the brief spec (FEAT-PLAYBOOK-001, "brief says what the data says")

What the two specs say, read on `origin/main` 74c75923:

- The brief spec's B8b moves `LEVEL_RULE_VERSION` to `feat-strat-001.v4` (`lib/strat_levels.py:1516`), adds `lib.strat_levels.is_current_pick_rule(version)` and puts it in place of the comparisons at `lib/strat_levels.py:1968` and `:2434` and `gcp/premarket_playbook_resolver.py:611`. Its `tests/meta/test_level_rule_version_readers.py` then fails any file under `lib/`, `gcp/` or `platform/` that compares a value with `LEVEL_RULE_VERSION` outside that helper.
- Its B9 passes a no-write flag into `generate_premarket_brief` and moves the row building of `persist_to_cloud_sql` into `build_persist_rows` (`gcp/premarket_brief.py`), and its recording stand-in fails the run on any statement that is not a SELECT.
- This spec says "LEVEL_RULE_VERSION does not change" (done_when[5]), adds a marker beside `lib/strat_levels.py:1995-1999` and a flag in `_assemble` beside `:2434-2450`, adds one SELECT and one keyword to `generate_premarket_brief` (`gcp/premarket_brief.py:980`, `:1372-1376`), and adds a field to `resolve_plan` and `resolve_one` (`gcp/premarket_playbook_resolver.py:476-588`, `:764-805`).

So the two branches edit neighbouring lines of `SessionLevels.from_basis`, `_assemble` and `generate_premarket_brief`, and one of them moves a constant the other pins.

**Merge order: the brief spec's branch first, then this one.** Reasons, each from the specs:

1. done_when[9] of this spec cannot be shown in full until the dry run is on main and deployed. With this branch first, that box stays open on the PR.
2. With the brief branch first, this plan's code is written once against the helper and v4, and Task 1's pin of the rule version is the literal main then holds. With this branch first, the brief branch has to resolve the conflicts at `:1968`, `:1995-1999` and `:2434-2450` and move this plan's pin.
3. The three 2026-11-16 fixtures are v3 bases. After the bump they rebuild only through the brief spec's v3 path ("SessionLevels.from_basis of a stored v3 basis returns the picks it returns on origin/main"), which this plan's tests then exercise for free.

**Which tasks depend on the brief spec's code being on main:** only Task 13, Step 9b (the production dry run) and Close-out step 3's dry-run check. Tasks 1 to 12, Task 13 Steps 1 to 8 and 9a, and Task 14's other steps need none of it.

**If the owner wants this branch first:** Task 1's base check records it, the pin is `feat-strat-001.v3`, done_when[9]'s production clause is reported on the PR as open and waiting on the brief spec, and the brief branch owns the conflict. Either way, no code in this plan compares a value with `LEVEL_RULE_VERSION`: where the brief spec's helper exists it is used, and where it does not, the existing comparisons at `:1968` and `:2434` are left exactly as they are.

## Merge is a production schema change

`gcp/cloudbuild/apply-schema-cloudbuild.yaml:1-5` says the `apply-schema-on-change` trigger "Fires: push to main touching gcp/schema.sql" and applies that revision's schema. This PR changes `gcp/schema.sql` (five policy rows, two columns). So merging it applies the seeded rows and the columns to production, which done_when[11] allows "only after the owner's yes". The live trigger was not read (no `gcloud` was run for this plan).

- **Ask the owner once before merging:** "Merging applies the five seeded policy rows and the two nullable columns to production through apply-schema-on-change. Yes?" Merge only on that yes, and record it on the PR as the first yes of done_when[11].
- The seeded rows change no target, and the deployed brief (old image) reads the two new policy-wide keys as unknown ticker keys with status `params_unavailable`, records them, and ignores them. Task 9 pins exactly that shape as case (b).
- That order is also the spec's ("Rows first, because the code treats a missing row as no plan").

## done_when[9], and what is evidenced when

The clause "the run's level_basis shows the seeded policy rows were the ones read" names rows that are in production only once `gcp/schema.sql` of this PR has been applied, and the key that records them under this PR's code, `plan_ladder_params`, is written only by a brief job built from this PR. The product-delivery skill wants every done_when box ticked with evidence before the PR is marked ready, and CI refuses a ticked line that puts its work off. So the evidence is taken in an order that has no circle, and each line says what it is:

| Evidence | When it exists | What it shows |
|---|---|---|
| The local Experiment, all arms (Task 13 Steps 1 to 8) | on the PR head | every clause of done_when[9] up to "arm A matches" |
| Arm A's targets equal the plan production already stored (Step 9a) | on the PR head, one read-only query | the seeded rows reproduce the published plan on production's own bases |
| The deployed job's dry run gives arm A's targets (Step 9b) | once the brief spec's dry run is deployed | "built by the deployed job with BRIEF_NO_PERSIST=true, equal the local build's" |
| The dry run's `level_basis.params` lists the five keys | once the seeded rows are in production | "the seeded policy rows were the ones read", as the deployed image records every policy key it reads (`lib/strat_levels.py:1441`, `:1452-1496`) |
| The next brief's `plan_ladder_params`, effective 2015-01-02 | once the brief job is built from this PR (Close-out step 2) | the same clause, under this PR's own record |

The fourth row is the one that closes the box, and it needs the seeded rows in production while the PR is still open. That is the owner's call, and done_when[11] already makes the rows the owner's first yes. **Ask the owner once, before Task 14 marks the PR ready:** "The seeded rows change no target. Apply this branch's gcp/schema.sql to production now (`./gcp/deploy.sh apply-schema` from the PR head), so the dry run can show the rows were read and done_when[9] can be evidenced on the PR? Or should that clause move to the Close-out by a revision of the spec?"

- On "apply now": run Step 9b after the apply, tick done_when[9] with the four records above, and record this as the first yes of done_when[11]. The merge then applies the same schema again, which is a no-op (`ON CONFLICT DO NOTHING`, `ADD COLUMN IF NOT EXISTS`).
- On "revise the spec": the clause is moved by a spec revision the owner approves, on its own `docs/` branch, as the skill requires for a done_when item that cannot be finished in its PR. The box is then ticked against the revised text.
- With neither answer the box stays unticked and the PR stays a draft. The box is never ticked with a note that the check will come; its line holds only the records that exist, by execution id.

The fifth row is Close-out step 2. It is a check of the deployed brief, not the evidence of any box.

## Global Constraints

- Base: `origin/main` at the time the code branch opens. Branch `feature/feat-strat-001-plan-always-three-targets`. This plan is committed alone on `docs/plan-feat-strat-001-plan-always-three-targets` and merged before the code branch opens.
- Seeded to today's plan. The five rows as `gcp/schema.sql` seeds them, each `effective_from` `'2015-01-02'`, each under `ON CONFLICT (param_key, effective_from) DO NOTHING`, no existing row changed:
  - `target_merge_atr`: `policy_seed`, extra `{"seed": 0.0}`
  - `target_fill_sources`: `policy`, extra `{"sources": []}`
  - `target_fill_reach_long_atr`, `target_fill_reach_short_atr`: `daily_excursion_quantile`, `statistic_q` 1.0, `lookback_sessions` 750, `min_sample` 250, extra `{"side": "long"}` and `{"side": "short"}`
  - `ladder_history_sessions`: `policy`, extra `{"sessions": 250}`
- Fill steps, exact names: `level_beyond_window`, `atr_rung_beyond`, `atr_rung_between`. Statuses, exact: `fill_status` `no_candidate_in_reach`; `target_status` `input_unavailable` for a merge at or above the spacing.
- No number and no name in the level code (done_when[7]). `lib/strat_levels.py` holds no literal other than 0, 1, -1, 2, -2 and 100 on the `build_session_levels` walk, and no string literal containing `0.1 x ATR`, `0.15 x ATR` or `3 x ATR`. The merge distance, the reach, the fill order and the history length are read only from `LevelParams`.
- No silent fallback (CLAUDE.md 3.7). A key that is not ok publishes no target and says which status; a failed reach-history read raises; a missing value is `None` and prints as words, never 0. The only display fallback is `no history yet` for a side with zero rows.
- Distances are compared in cents through `price_cents`, equal kept, as the spacing is today.
- `LEVEL_RULE_VERSION` does not change in this PR, and no new line compares a value with it.
- `gate_targets`, the `t1..t3` columns, the trigger, the stop, the spacing value, `exit_legs`, the opened-through rule, the entry cutoff, the ATR rungs and their thinning, NEXT LEVELS, the ATR levels line, PMG zones, the signal monitor, the movement statement and persona plans do not change (done_when[8]).
- Tests are hermetic. CI's Run Tests job checks out a single commit with no `origin/main`, so no test runs `git show origin/main:...` or any other git command. "Equal to origin/main's" is pinned by a literal in the test or by a fixture file that Task 1 records from the base and commits.
- Production access. Nothing in Tasks 2 to 12 touches production. Each step that does is marked **Ask the owner once before running** and is never assumed approved: Task 1 Step 1 (a read-only export of three stored rows), Task 13 Steps 1 and 9 (a read-only export of bars, a read-only read of stored plan prices, and the dry runs), the schema apply or the merge (above), and every Close-out step. No `--commit`, no deploy, no schema apply and no policy row change is run from this branch.
- Replays go through production code (CLAUDE.md 3.5, 3.6): bases are built by `gcp/premarket_brief.py` with `BRIEF_AS_OF`, scored by `gcp.premarket_playbook_resolver.plan_inputs` and `resolve_plan`. No bar walk, indicator or level rule is written for the Experiment.
- Capacity (CLAUDE.md Rule 0; spec "Capacity and cost"), written into the PR body: Volume, five policy rows, three more `ticker_level_params` rows a ticker a calibration run, two nullable columns, a ladder of about 6 to 12 entries a side and at most `ladder_history_sessions` reach values a side in each new `level_basis`; Velocity, one new query a brief run for all tickers, none in the resolver or the calibration; Wall-clock, one more round trip of 0.5 to 2 s a brief run; Cost, $0 scheduled. Task 11 asserts the I/O shape (one query for N tickers).
- The render step. A task that changes a file under `gcp/`, `lib/` or `scripts/` ends with it, because the generated inventory cites line numbers:
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate -q` (expect 1 passed), and stage whichever of the three docs changed with the code.
- Commits: conventional `type(scope): description`, imperative, no AI attribution. The PR opens as a draft and stays one until every done_when line in its body is ticked with evidence. Every new test has a red then green record in the PR body.
- No em or en dashes in code comments, copy or docs written for this change.

Choices this plan makes where the spec leaves one open (each is reported to the owner with the plan):

- **The reach history is an input recorded in the basis.** The spec says a basis records "the reach counts as printed". Counts alone cannot be recomputed when a basis is rebuilt, so the basis records, under `plan_reach_history`, the values the brief read (`{"sessions": n, "long": [...], "short": [...]}`, at most `ladder_history_sessions` numbers a side) and each ladder entry also carries its `reached` count. This is more than the spec's Volume line names.
- **The reach bounds the fill and the ladder, never an in-window target.** The spec does not say what a reach smaller than the window does. Targets inside the window are found first and "never displaced" (Design 2), so a reach below the window removes none of them (Review Focus 1).
- **A side with no target and a non-empty fill list** prints origin/main's own no-target line (`lib/strat_levels.py:3203-3204`) followed by the reason. The spec's done_when[4] cites `:3213` for "the whole position", but that line only runs when the side has at least one target; main has no fraction wording for zero targets.
- **`plan_ladder_status`** is `input_unavailable` when `target_merge_atr` is ok as a row but at or above the ticker's spacing, the status Design 1 gives that row. The comparison is in cents, and a merge of zero cents is exempt: Design 1 says the merge "must be below" the spacing, which read to the letter would refuse the seed 0.0 for a ticker whose spacing is 0.0.
- **The reach history population** is every row with a non-NULL value in the span, as Design 6 says ("every row the new resolver wrote"), with no `run_kind` and no rule-version filter. The brief spec's B8b keeps the movement statement's rates from mixing rule versions; this spec does not ask the same of the reach counts.
- **The Experiment's arms other than A** are scored on arm A's stored bases with the arm's parameter records put in place of the seeded ones, rebuilt by `SessionLevels.from_basis` (the way the spec's own fixtures add "the new parameters ... to its params for each case"). Replaying 1,212 sessions seven times is not needed for a rule `from_basis` rebuilds exactly. Task 13 Step 7 checks that claim against a real replay with the rows in the local copy.
- **The Experiment's driver is committed** as `scripts/research/plan_targets_experiment.py` with a hermetic test, since the lab files the gap-edges Experiment used (`/mnt/project-files/stocks-scorecard/`) are not in the repo.
- `RESOLVER_VERSION` becomes `'2026-11-16.v5'`.

## done_when map

| done_when | What | Task |
|---|---|---|
| [0] | Policy and calibration | 2, 3 |
| [1] | Zones | 5 |
| [2] | Always three targets (the fill) | 6 |
| [3] | Full ladder and strength | 7 |
| [4] | Brief copy | 8 |
| [5] | Stored briefs keep their plan | 4, 9 |
| [6] | Reach history stored and read | 10, 11 |
| [7] | No numbers and no names | 12 |
| [8] | Unchanged | 1, 12 |
| [9] | Experiment | 13 |
| [10] | Source identity (DASHBOARD-01) | 14 |
| [11] | Catalog, traceability, gate; production only on the owner's yes | 14, Close-out |

## Review Focus

Inputs the spec implies and no done_when test pins, most likely first. Each has a test in the task that owns the code.

- **A reach smaller than the window.** A later reach row, or a bad calibration, below the side's trigger window: the in-window targets are still the ones today's plan publishes (the original walk is handed every in-window candidate, never a reach-filtered list), no fill target is added past the reach, and every target still appears on the ladder. Tasks 5, 6 and 7.
- **A zone that straddles the edge of the window.** Its nearest level is inside the window and its far level is past it: it is one in-window zone, walked once, and `level_beyond_window` does not take its far level as a second target. Task 6.
- **A fill bar with nothing after it.** A side entered on the last bar before the close has no later bar: `mfe_atr` is 0.0, not NULL and not an error; a side entered with bars after it but a stop on the very next bar is 0.0 too. Task 10.
- **Derived builds.** `with_premarket` (the planner's newer snapshot) and `with_reference` (the signal monitor's put re-anchor) rebuild zones, fill and ladder against the new reference, carry the reach history, and leave `gate_targets` and the monitor's decisions as today. Task 7.
- **A merge distance that rounds to no cents, and a leg count that is not three.** `target_merge_atr` 0.0005 on a 4.87 ATR is 0 cents: nothing merges and the brief prints no zone clause. With `exit_legs` 2 the fill stops at two targets and the roles are `t1` and `t2` only. Tasks 5 and 6.

## File map

| File | Change | Task |
|---|---|---|
| `tests/fixtures/level_basis_2026-11-16/` | new: `IWM.json`, `SPY.json`, `QQQ.json`, `sources.json`, and per ticker `<T>.main.json`, `<T>.main.txt` | 1 |
| `tests/lib/session_levels_helpers.py` | `stored_1116`, `ladder_params`, the two golden reach histories | 1, 4 |
| `gcp/schema.sql` | five policy rows after `:2318-2320`; two columns after `:2004` | 2, 10 |
| `lib/strat_levels.py` | keys beside `:1012-1015`; `policy_wide_param` (`:1365`); `SideLevels` (`:1676`), `SessionLevels` (`:1723`), `to_basis` (`:1872`), `from_basis` (`:1935`), `build_session_levels` (`:2328`), `_assemble` (`:2430`), `_pick_side` (`:2721`), `_plan_targets` (`:2821`), `_legacy_trigger_dict` (`:2893`), `_plan_block` (`:3173`); new `_target_zones`, `_fill_targets`, `_plan_ladder`, `_ladder_lines` | 2, 4 to 8 |
| `lib/level_calibration.py` | `target_fill_reach`; `calibrate` (`:1046`), `HistoryCalibrator.calibrate` (`:1225`) | 3 |
| `tests/lib/level_params_fixtures.py` | new `LADDER_FIXTURE_VALUES`, read by `fixture_params` and `legacy_db`; `LEGACY_1753_VALUES` unchanged | 2 |
| `gcp/premarket_playbook_resolver.py` | `RESOLVER_VERSION` (`:100`), `PlanOutcome`, `PlanInputs`, `resolve_plan` (`:476`), `plan_inputs` (`:591`), `_PLAN_FIELDS` (`:877`) | 10 |
| `gcp/premarket_brief.py` | `read_plan_reach_history`; `generate_premarket_brief` (`:980`, `:1372-1376`) | 11 |
| `scripts/research/plan_targets_experiment.py` | new: the Experiment's driver | 13 |
| `tests/lib/test_strat_levels.py` | `TestStored20261116`, `TestTargetZones`, `TestTargetFill`, `TestPlanLadder`, `TestLadderCopy`; the Skipped line of `D8_CALLS`, `D8_PUTS` | 1, 5 to 8 |
| `tests/lib/test_level_params_loader.py`, `tests/lib/test_level_calibration.py` | new tests; the key-set pin at `test_level_params_loader.py:26-43` | 2, 3 |
| `tests/gcp/test_level_basis.py` | the stored-brief tests | 4, 9 |
| `tests/gcp/test_premarket_playbook_resolver.py` | `TestPlanMfe` | 10 |
| `tests/gcp/test_premarket_brief.py` | the reach-history read | 11 |
| `tests/lib/test_level_params_structure.py`, `tests/lib/test_level_params_copy.py` | added assertions only | 12 |
| `tests/scripts/test_plan_targets_experiment.py` | new | 13 |
| `docs/product/02`, `03`, `12`, `docs/review-evidence/site-source-snapshot.json`, `docs/product/infrastructure/05-a`, `05-c`, `05-e` | close; inventory by the render step | 14, 2 to 13 |

---

### Task 1: The three stored bases, and today's plan pinned on them

Spec: Design 8 ("Fixtures"); Problem 1 (the table). Advances done_when[8]; supplies done_when[1] to [5].

**Files:**
- Create: `tests/fixtures/level_basis_2026-11-16/{IWM,SPY,QQQ}.json`, `sources.json`, `{IWM,SPY,QQQ}.main.json`, `{IWM,SPY,QQQ}.main.txt`
- Modify: `tests/lib/session_levels_helpers.py`
- Test: `tests/lib/test_strat_levels.py`

**Interfaces:**
- Produces: `stored_1116(ticker: str) -> dict` (the stored basis, a fresh copy each call); `CALLS_REACH_D8 = (0.1, 0.3, 0.4, 0.7, 1.1, 1.2, 1.6, 2.4)`; `PUTS_REACH_D8 = (0.05, 0.2, 0.3, 0.6, 0.9, 1.3, 1.5, 2.1)`; `main_1116(ticker: str) -> dict` (the `.main.json` record) and `main_text_1116(ticker: str) -> str`.

- [ ] **Step 1: Export the three bases. Ask the owner once before running** (read-only, `scripts/db_query_cr.sh` without `--commit`): one statement a ticker selecting `level_basis` from `premarket_analysis_history` (falling back to `premarket_analysis`) for `analysis_date = '2026-11-16'` and the ticker, where `level_basis->>'built_at'` starts `2026-11-16T08:31:19`. The copy is taken by build time because a later replay can overwrite the row. Save each JSON verbatim. `sources.json` names, per file, the db-query execution id, the SQL and the file's sha256. If the owner says no, stop: Tasks 5 to 9 have no fixture.
- [ ] **Step 2: Base check.** Record in the PR body: the base sha; `git diff --stat 060c89a0 <base> -- lib gcp tests scripts`; whether `grep -n "def is_current_pick_rule" lib/strat_levels.py` finds the brief spec's helper; and the literal of `LEVEL_RULE_VERSION` on the base (`feat-strat-001.v3` today, `feat-strat-001.v4` once the brief spec merged).
- [ ] **Step 3: Record what the base gives**, before any code changes, with a one-off run that is not committed: for each ticker, `sl = SessionLevels.from_basis(stored_1116(t))`; write `<T>.main.json` holding, per side, `trigger`, `stop`, `targets`, `skipped`, `gate_targets` and `target_status` from `sl.to_basis()`; write `<T>.main.txt` holding `format_levels_for_brief(sl.to_level_map(), 'bearish')`. These two files are the pin of "origin/main" for every later task.
- [ ] **Step 4: Write the tests** in `TestStored20261116`:
  - `test_sources_json_matches_the_files`: every basis file's sha256 equals its `sources.json` entry.
  - `test_todays_targets` (parametrised over the six sides; the literals are the spec's Problem 1 table): IWM calls trigger 278.92, targets `[283.79, 285.26]`, skipped `[279.17, 279.33]`; IWM puts trigger 275.86, stop 277.41, targets `[274.55, 269.88]`, skipped `[274.67]`; SPY calls 754.38, `[760.12, 763.04]`, skipped `[755.72, 762.63]`; SPY puts 747.95, `[741.03, 729.10]`, skipped `[747.88]`; QQQ calls 681.02, `[688.75, 695.57]`, skipped `[683.45, 690.49, 698.63]`; QQQ puts 668.30, `[662.02, 637.01]`, skipped `[661.14]`.
  - `test_main_records_match`: each side's record in `<T>.main.json` equals the rebuilt side, and `main_text_1116(t)` equals the rendered text.
  - `test_iwm_text_is_the_specs_today_block`: `main_text_1116('IWM')` contains the spec's Design 8 "Today" block, CALLS and PUTS, character for character (spec lines 353 to 367).
  - `test_rule_version_is_the_bases`: `LEVEL_RULE_VERSION` equals the literal recorded in Step 2.
- [ ] **Step 5: Run:** `python3 -m pytest tests/lib/test_strat_levels.py -k TestStored20261116 -q` (expect all passed: this task pins the base, so there is no red). A failure here is a finding about the spec's table or the stored row, reported to the owner, never a changed expectation.
- [ ] **Step 6: Commit:** `test(strat): pin today's plan on the three stored 2026-11-16 bases`

### Task 2: The five policy rows and their keys

Spec: Design 1 (seed), Design 2 (the row), Design 3, Design 6 (`ladder_history_sessions`); done_when "Policy and calibration". Advances done_when[0].

**Files:**
- Modify: `gcp/schema.sql` (the policy INSERT, before `ON CONFLICT` at `:2320`), `lib/strat_levels.py` (`:1007-1015`, `:1365-1392`, `LevelParams`), `tests/lib/level_params_fixtures.py` (`:31-66`)
- Test: `tests/lib/test_level_params_loader.py`

**Interfaces:**
- Produces, each name defined once in `lib/strat_levels.py`:
  - `TARGET_MERGE_KEY = 'target_merge_atr'` (joins `POLICY_SEEDED_KEYS`)
  - `TARGET_FILL_SOURCES_KEY = 'target_fill_sources'`, `LADDER_HISTORY_KEY = 'ladder_history_sessions'` (both join `POLICY_WIDE_KEYS`)
  - `FILL_LEVEL_BEYOND = 'level_beyond_window'`, `FILL_RUNG_BEYOND = 'atr_rung_beyond'`, `FILL_RUNG_BETWEEN = 'atr_rung_between'`, `TARGET_FILL_STEPS = (FILL_LEVEL_BEYOND, FILL_RUNG_BEYOND, FILL_RUNG_BETWEEN)`
  - `target_fill_reach_key(side: str) -> str` (`'target_fill_reach_long_atr'` or `'target_fill_reach_short_atr'`)
  - `PLAN_LADDER_KEYS`: the merge key, the sources key, the two reach keys, the history key, in that order
  - `target_fill_sources(extra) -> Optional[tuple]` and `LevelParams.target_fill_sources() -> Optional[tuple]`, on the pattern of `plan_target_level_types` (`:1334`, `:1214`)

- [ ] **Step 1: Write the failing tests:**
  - `test_schema_seeds_the_five_plan_ladder_rows`: on `seeded_policy()`, each of the five rows has `effective_from == "2015-01-02"` and the method, quantile, lookback, minimum and extra of Global Constraints; the schema text holds the five inside the existing INSERT, before `ON CONFLICT (param_key, effective_from) DO NOTHING`; every other seeded row equals a literal copy of its `(method_id, statistic_q, lookback_sessions, min_sample, extra)` written in the test for the three rows named in `test_schema_seeds_the_design_2_policy_and_no_ticker_values` (`:33-38`).
  - `test_target_fill_sources_reads_its_extra` (parametrised): `{"sources": []}` gives `("ok", 0.0)`; the three steps in order `("ok", 3.0)`; `["atr_rung_beyond", "atr_rung_between"]` `("ok", 2.0)`; `{}`, `{"sources": "level_beyond_window"}`, `["level_beyond_window", "pdh"]` and `["atr_rung_beyond", "atr_rung_beyond"]` each `("input_unavailable", None)`; and `LevelParams.target_fill_sources()` returns the tuple, or `None` when not ok.
  - `test_ladder_history_sessions_reads_its_extra`: `{"sessions": 250}` gives `("ok", 250.0)`; `1` gives `("ok", 1.0)`; `0`, `-5`, `2.5`, `True`, `"250"` and `{}` give `("input_unavailable", None)`.
  - `test_the_keys_are_named_once`: `'target_merge_atr' in POLICY_SEEDED_KEYS`; both wide keys in `POLICY_WIDE_KEYS`; and each of the five key strings appears as a string literal exactly once in the AST of `lib/strat_levels.py`.
  - `test_a_ticker_with_no_row_reads_the_three_ticker_keys_as_params_unavailable`: `ParamsDb().load(["SPY"], D)` gives `params_unavailable` for the merge key and both reach keys, and `ok` for the two wide keys.
  - Change the pin at `:26-43`: the policy key set gains the five new keys beside `plan_target_level_types`; `len(DESIGN_2_KEYS) == 28` stays.
  - `test_the_legacy_fixtures_still_publish_their_targets`: `fixture_params()` holds the three ladder ticker keys ok and still holds `target_min_spacing_atr` 0.0, and a fresh `build_session_levels` on the frame of `tests/lib/test_level_params_behaviour.py`'s first case publishes the targets that test asserts (it stays red until Task 4, and is recorded so).
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_level_params_loader.py -q` (expect FAIL: `KeyError: 'target_merge_atr'` on the seeded policy, and ImportError for the new names).
- [ ] **Step 3: Implement.** The five rows in `gcp/schema.sql` with a comment naming this spec; the names; the two new branches of `policy_wide_param`; in `tests/lib/level_params_fixtures.py` a new `LADDER_FIXTURE_VALUES = {"target_merge_atr": 0.0, "target_fill_reach_long_atr": 3.0, "target_fill_reach_short_atr": 3.0}` (the spec's fixture reach), which `fixture_params` and `legacy_db` add to the values they write, so a fresh build in an existing test finds the three ticker rows. `LEGACY_1753_VALUES` itself is not changed: `DESIGN_2_KEYS` is derived from it (`tests/lib/test_level_params_loader.py:22`) and it keeps `target_min_spacing_atr` 0.0 (`tests/lib/level_params_fixtures.py:58`).
- [ ] **Step 4: Run** the same command, then `python3 -m pytest tests/lib tests/gcp/test_level_params_consumers.py tests/gcp/test_calibrate_level_params.py -q` (expect passed), then the render step.
- [ ] **Step 5: Commit:** `feat(strat): seed the plan ladder policy rows at today's plan`

### Task 3: The calibration writes the merge seed and the two reach keys

Spec: Design 3; done_when "Policy and calibration". Closes done_when[0].

**Files:**
- Modify: `lib/level_calibration.py` (beside `trigger_window`, `:275-283`; `calibrate`, `:1066-1067`; `HistoryCalibrator.calibrate`, `:1237-1238`)
- Test: `tests/lib/test_level_calibration.py`

**Interfaces:**
- Consumes: `target_fill_reach_key`, `TARGET_MERGE_KEY` (Task 2); `daily_excursions`, `_stat`, `quantile` (unchanged).
- Produces: `target_fill_reach(d: pd.DataFrame, policy: Dict[str, dict], side: str) -> Calibrated`, the trigger window's own samples (the last `lookback_sessions` rows of `d`, `daily_excursions`) under the reach row's quantile and minimum. `calibrate` and `HistoryCalibrator.calibrate` return both reach keys and, through `policy_seeds`, the merge key.

- [ ] **Step 1: Write the failing tests** (helpers `_daily` and `policy` of the file):
  - `test_reach_is_the_largest_excursion_of_the_lookback`: 300 sessions whose long excursions are 0.5 except one of 2.75 and one of 3.5 gives `target_fill_reach_long_atr` `("ok", 3.5)`, `sample_n` 300, `method_id` `"daily_excursion_quantile"`; the short side on mirrored lows the same; the session of 3.5 placed outside the last 750 gives 2.75.
  - `test_reach_is_never_below_the_window_from_the_same_samples`: on five frames written in the test, for each side, `out[reach key].value >= out[trigger_window_key(side)].value`.
  - `test_reach_under_min_sample_is_insufficient_history`: 249 sessions give `("insufficient_history", None)` for both; 250 give `ok`.
  - `test_merge_seed_and_reach_keys_through_both_paths`: `lc.calibrate` and `HistoryCalibrator(...).calibrate` on the same frame return equal `Calibrated` records for the three keys, `target_merge_atr` `("ok", 0.0, "policy_seed")`; `to_rows` writes one row for each of the three with the run's `run_id`; `target_fill_sources` and `ladder_history_sessions` are in neither result.
  - `test_a_merge_seed_change_is_a_policy_row`: `policy(target_merge_atr={"extra": {"seed": 0.10}, "effective_from": "2026-11-05"})` calibrates 0.10.
  - `test_a_policy_without_the_merge_seed_cannot_calibrate`: deleting the row raises `LevelParamsUnavailable` matching the key, on both paths.
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_level_calibration.py -q` (expect FAIL: `KeyError: 'target_fill_reach_long_atr'`).
- [ ] **Step 3: Implement** `target_fill_reach` and the two calls in each path. No number is typed: the quantile, lookback and minimum come from the policy row.
- [ ] **Step 4: Run** the same command and `python3 -m pytest tests/lib/test_level_calibration_history.py tests/lib/test_level_calibration_evidence.py tests/gcp/test_calibrate_level_params.py -q` (expect passed), then the render step.
- [ ] **Step 5: Commit:** `feat(strat): calibrate the target merge seed and the fill reach per ticker`

### Task 4: The marker, the status and the five-key check

Spec: Design 10. Advances done_when[5].

**Files:**
- Modify: `lib/strat_levels.py` (`SideLevels`, `SessionLevels`, `to_basis` `:1906-1909`, `from_basis` `:1995-1999`, `_assemble` `:2435-2450`, `_plan_targets` `:2836-2839`), `tests/lib/session_levels_helpers.py`
- Test: `tests/gcp/test_level_basis.py`

**Interfaces:**
- Consumes: `PLAN_LADDER_KEYS`, `TARGET_MERGE_KEY`, `TARGET_SPACING_KEY`.
- Produces:
  - `SessionLevels.plan_ladder_rule: bool = True`, set by `from_basis` to `'plan_ladder_status' in basis`; `SessionLevels.plan_ladder_status: Optional[str]`; `to_basis` writes `plan_ladder_status` and `plan_ladder_params` (`{key: {value, status, method_id, effective_from}}` for the five; for `target_fill_sources` the value is the list of steps) only when the rule is on.
  - `_plan_ladder_status(params: Optional[LevelParams]) -> str`: `ok`; else the status of the first of `PLAN_LADDER_KEYS` that is not ok; else `input_unavailable` when the merge distance in cents, `price_cents(merge x ATR)`, is above zero and at or above the spacing in cents. A merge of zero cents merges nothing and is always usable, whatever the spacing: the seed 0.0 must reproduce today's plan for a ticker whose spacing is 0.0 too, which is what every default test fixture holds.
  - `_pick_side(..., ladder_rule: bool = False)` and `_plan_targets(..., ladder_rule: bool = False)`: with the rule on, a status other than ok sets `target_status` to it and publishes no target, before any walk.
  - `SideLevels.plan_ladder: Optional[list] = None`, `SideLevels.fill_status: Optional[str] = None`; `to_dict` writes the two keys only when `plan_ladder` is not `None`.
  - In `tests/lib/session_levels_helpers.py`: `ladder_params(basis: dict, *, merge=0.0, fill=(), reach=3.0, history_sessions=250, statuses=None, marker=True) -> dict`, which writes the five parameter records into `basis["params"]` in `LevelParam.to_basis()` shape and, with `marker`, sets `basis["plan_ladder_status"] = None` (the idiom of `atr_rung_status` at `:57`). Legacy and ladder fixtures are separate and explicit: `basis(..., ladder: bool = False)` writes no marker by default, so every existing `basis()` and `session()` fixture stays on the markerless path and rebuilds as today, whatever its params record; `d8_basis` and `d8_session` pass `ladder=True`, because done_when[4] moves their goldens to the ladder.

- [ ] **Step 1: Write the failing tests:**
  - `test_a_basis_without_the_ladder_marker_never_checks_the_five_keys` (parametrised `recorded` in `absent`, `ok`, `params_unavailable`): `stored_1116(t)` for each ticker, its params (a) holding none of the five and (b) holding all five with that status (as the old loader records unknown policy keys): the rebuilt sides equal `main_1116(t)`, `"plan_ladder_status" not in sl.to_basis()`, and no side dict holds `plan_ladder`.
  - `test_a_marked_basis_with_a_key_not_ok_publishes_no_target` (parametrised over the five keys with `insufficient_history`): every side keeps its trigger, stop and `gate_targets` as in `main_1116`, `targets == []`, `target_status == "insufficient_history"`, and `to_basis()["plan_ladder_status"] == "insufficient_history"`.
  - `test_a_merge_at_or_above_the_spacing_publishes_no_target`: merge 0.25 and merge 0.30 against the stored spacing 0.25 give `target_status == "input_unavailable"` on every side; merge 0.24 does not.
  - `test_a_zero_merge_is_usable_at_any_spacing`: `d8_session(spacing=0.0)` (ladder on, merge 0.0, spacing 0.0) has `target_status == "ok"` and the targets `TestExitPlanCopy::test_prior_close_gap_fill_label` reads (`tests/lib/test_strat_levels.py:1171-1179`).
  - `test_a_default_basis_fixture_is_markerless`: `basis(D8_LEVELS, prior_close=247.00, atr=14.0, premarket=D8_PREMARKET)` has no `plan_ladder_status` key, and its rebuilt sides hold no `plan_ladder`.
  - `test_a_marked_seeded_basis_equals_the_bases_plan`: `ladder_params(stored_1116(t))` (merge 0.0, fill empty) rebuilds targets, skipped list, `target_status` and `gate_targets` equal to `main_1116(t)`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_level_basis.py -q` (expect FAIL on the new tests: `ladder_params` not defined, then `plan_ladder_status` absent).
- [ ] **Step 3: Implement.** No comparison with `LEVEL_RULE_VERSION` is added; the flag travels as `atr_rung_rule` and `plan_target_rule` do.
- [ ] **Step 4: Run** the same command and `python3 -m pytest tests/lib tests/gcp/test_premarket_playbook_resolver.py -q` (expect passed), then the render step.
- [ ] **Step 5: Commit:** `feat(strat): mark a basis built under the plan ladder rule and check its keys`

### Task 5: Close levels are one target zone

Spec: Design 1. Closes done_when[1].

**Files:**
- Modify: `lib/strat_levels.py` (`_pick_side` `:2806-2812`, `_plan_targets` `:2856-2890`, `_legacy_trigger_dict` `:2914-2925`)
- Test: `tests/lib/test_strat_levels.py`

**Interfaces:**
- Consumes: Task 4's flag and status; `price_cents`; the side's unbroken candidates and `_plan_extra_rungs`.
- Produces:
  - `_target_zones(rungs: list, merge_cents: int, side: str) -> list`: the rungs past the trigger in price order outward grouped into zones; a rung joins the open zone when its distance in cents from the zone's nearest level is at most `merge_cents`, else it opens a new one. A zone is `{'members': [rung, ...], 'cents': nearest, 'far_cents': farthest, 'in_window': nearest member's}`.
  - `_pick_side` passes `_plan_targets` two lists, both past the trigger. `rungs` and `extra` are exactly what it passes today (`:2781`, `:2806-2811`): every unbroken in-window candidate and listed plan level, with no reach filter, so a reach below the window removes none of them. `beyond: list` is new: the unbroken candidates and listed plan levels past the side's window, unfiltered here. The walk of this task zones and walks the first list only. The reach bound is applied in two places and nowhere else: to `beyond` and the ATR rungs when Task 6 picks fill candidates, and to the entries Task 7 lists on the ladder (a target is always listed).
  - A kept zone of two or more levels is a target `{**_rung(nearest), 'zone': {'far_price': float, 'members': [{'name', 'price'}, ...]}}`; a single level is exactly the dict today's walk gives. The next target is measured from the far edge of the one before. A too-close zone is one `skipped` entry, with `zone` when it has two or more levels.
  - `out.plan` gains `merge_atr` and `merge_price` (cents / 100) under the rule; `_legacy_trigger_dict` passes `zone` on `plan_targets` and `skipped`.

- [ ] **Step 1: Write the failing tests** in `TestTargetZones` (bases `ladder_params(stored_1116(t), merge=m)`, no fill; a helper returns `(price, names)` per target):
  - `test_iwm_calls_zone_is_too_close`: at 0.10, targets `[283.79, 285.26]`; `skipped` is one entry priced 279.17 with zone far price 279.33 and members `PDH`, `PMC`.
  - `test_iwm_puts_zone_is_t1`: at 0.10, T1 priced 274.67, name `PDL`, zone far price 274.55, members `PDL 274.67` and `GAP_L_2026-11-09 274.55`; T2 269.88; `skipped == []`.
  - `test_spy_calls_zone_is_t2`: at 0.10, T1 760.12; T2 priced 762.63, zone far price 763.04, members `PQC`, `PWH`.
  - `test_qqq_puts_zone_is_t1`: at 0.10, T1 priced 662.02, zone far price 661.14, members `PWL`, `PQL`; T2 637.01.
  - `test_qqq_calls_at_two_merge_distances`: at 0.10, T1 688.75 and 690.49 is skipped; at 0.15, T1 priced 688.75 with zone far price 690.49, members `PDH`, `PMC`, and T2 695.57.
  - `test_a_level_exactly_the_merge_distance_joins`: on a basis written in the test (ATR 10.00, merge 0.10, so 100 cents; trigger 100.00; levels at 110.00 and 111.00) the two are one zone; with the second at 111.01 they are two.
  - `test_a_zone_is_never_wider_than_the_merge_distance`: levels at 110.00, 110.60, 111.20 with 100 cents give zone 110.00 to 110.60 and a separate 111.20.
  - `test_the_next_target_is_measured_from_the_far_edge`: spacing 250 cents; zone 110.00 to 111.00 kept; a level at 113.20 (320 past the nearest edge, 220 past the far edge) is skipped, and one at 113.50 is kept.
  - `test_merge_zero_equals_the_bases_plan`: at 0.0, every side of the three tickers equals `main_1116`.
  - `test_each_zone_target_records_price_name_and_zone`.
  - `test_the_walk_is_handed_every_in_window_candidate`: on IWM with reach 1.0 and merge 0.0, calls targets `[283.79, 285.26]` and skipped `[279.17, 279.33]`, equal to `main_1116`.
  - Review Focus: `test_a_merge_that_rounds_to_no_cents_merges_nothing`: merge 0.0005 on IWM equals `main_1116('IWM')` and `plan['merge_price'] == 0.0`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_strat_levels.py -k TestTargetZones -q` (expect FAIL: the 0.10 and 0.15 cases give today's targets, for example IWM puts T1 274.55 where 274.67 is expected).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same command and `python3 -m pytest tests/lib/test_strat_levels.py tests/gcp/test_level_basis.py -q` (expect passed), then the render step.
- [ ] **Step 5: Commit:** `feat(strat): treat levels within the merge distance as one target zone`

### Task 6: The fill, so a side has a T1, a T2 and a T3 when the ladder holds them

Spec: Design 2, Design 3. Closes done_when[2].

**Files:**
- Modify: `lib/strat_levels.py` (`_plan_targets`)
- Test: `tests/lib/test_strat_levels.py`

**Interfaces:**
- Consumes: Task 5's `beyond` list, zoned by `_target_zones` and cut to the side's reach here (the `level_beyond_window` candidates; a zone is in reach when its nearest level is); `SessionLevels.atr_rungs`, `atr_rung_status` (`_pick_side` gains `atr_rungs: Optional[list]` and `atr_rung_status: Optional[str]`, passed from `_assemble`); `LevelParams.target_fill_sources()`; `target_fill_reach_key(side)`.
- Produces:
  - `_fill_targets(targets: list, zones_beyond: list, atr_rungs: list, steps: tuple, *, trigger_cents: int, ref_cents: int, reach_cents: int, spacing_cents: int, legs: int, side: str, rung_status: Optional[str]) -> tuple[list, Optional[str]]`: the targets with fill targets added, and the `fill_status`. Each step runs while a leg has no target and can add more than one. A fill target carries `source` (the step's name); a rung target also carries `label` and `stretch`.
  - Then the targets are ordered by price outward. `fill_status`: `None` when the side has `legs` targets or the list is empty; `no_candidate_in_reach` when a non-empty list left a leg empty; the rung status when a rung step was listed and `atr_rung_status` is not ok.
  - `out.plan` gains `fill_sources` (the list) and `reach_atr`.

- [ ] **Step 1: Write the failing tests** in `TestTargetFill` (bases `ladder_params(stored_1116(t), fill=steps)`, reach 3.0, merge 0.0):
  - `test_level_beyond_window`: with `["level_beyond_window"]`, SPY calls T3 is 779.37, name `PQH`, source `level_beyond_window`; QQQ calls T3 is 711.62, name `GAP_H_2026-10-30`; IWM calls, IWM puts, SPY puts and QQQ puts keep two targets with `fill_status == "no_candidate_in_reach"`.
  - `test_atr_rungs`: with `["atr_rung_beyond", "atr_rung_between"]`, IWM calls T3 286.48 (`PDH+1.5`), IWM puts T3 268.55 (`PMK_L-1.5`), SPY calls T3 769.95 (`PDL+2`), SPY puts T3 725.88 (`PMK_L-2`), QQQ calls T3 700.98 (`PMK_L+2`); QQQ puts are `[662.02, 647.17, 637.01]` with 647.17 (`PDL-1.5`) the `atr_rung_between` one, numbered in price order.
  - `test_equal_to_the_spacing_is_kept`: IWM calls' 286.48 is exactly 122 cents past 285.26.
  - `test_the_three_steps_in_order`: SPY calls T3 779.37, IWM calls T3 286.48.
  - `test_nothing_past_the_reach_is_a_target`: IWM `PQH` 305.18 is no target under any list; with reach 6.0 and `["level_beyond_window"]` it is IWM calls' T3.
  - `test_every_fill_target_is_spaced`: over the three lists and six sides, each fill target is at least the spacing from the trigger and from every other target.
  - `test_in_window_targets_are_the_bases_in_the_same_order`: with any list, the targets without a `source` equal `main_1116`'s targets, in order.
  - `test_rung_status_not_ok`: with `atr_rung_status` not ok the rung steps add nothing and `fill_status` is that status.
  - `test_the_seeded_empty_list_equals_the_base`.
  - `test_a_reach_key_not_ok_publishes_no_target`.
  - `test_one_step_fills_more_than_one_leg`, on a basis written in the test (ATR 10.00, spacing 250 cents, window 1.0, reach 5.0, reference and trigger 100.00, calls levels past the window at 115.00, 120.00 and 125.00): no in-window target and `["level_beyond_window"]` gives T1, T2, T3 at 115.00, 120.00, 125.00; with one in-window target at 105.00 the step adds 115.00 and 120.00; with only 115.00 past the window the side ends with two targets and `fill_status == "no_candidate_in_reach"`.
  - Review Focus: `test_a_reach_below_the_window_removes_no_in_window_target` (IWM, reach 1.0 against windows 2.17 and 2.27, with the three steps listed: calls targets are still `[283.79, 285.26]` and puts `[274.55, 269.88]`, equal to `main_1116`; no fill target is added; `fill_status == "no_candidate_in_reach"`). `test_a_zone_straddling_the_window_edge_is_one_target` (written basis: the zone's nearest level inside the window and its far level past it; with `["level_beyond_window"]` the far level is not a second target). `test_two_legs`: `exit_legs` 2 with one in-window target adds one fill target and no third.
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_strat_levels.py -k TestTargetFill -q` (expect FAIL: every fill case gives two targets).
- [ ] **Step 3: Implement.** `atr_rung_between` takes the farthest kept rung from the trigger first, at least the spacing from the trigger and from the targets on both sides.
- [ ] **Step 4: Run** the same command and `python3 -m pytest tests/lib/test_strat_levels.py tests/gcp/test_level_basis.py -q` (expect passed), then the render step.
- [ ] **Step 5: Commit:** `feat(strat): fill a leg with no target from the policy's ordered sources`

### Task 7: The full ladder, strength and reach counts

Spec: Design 4, Design 5, Design 6 (the count). Closes done_when[3]; supplies done_when[4] and [6].

**Files:**
- Modify: `lib/strat_levels.py` (`SessionLevels`, `to_basis`, `from_basis`, `build_session_levels`, `_assemble`, `_pick_side`)
- Test: `tests/lib/test_strat_levels.py`

**Interfaces:**
- Consumes: Tasks 5 and 6's zones and targets; `atr_rungs`, `atr_rungs_dropped`; `LEVEL_CLUSTER_KEY`.
- Produces:
  - `build_session_levels(..., reach_history: Optional[dict] = None)` and `SessionLevels.reach_history: Optional[dict]`, `{'sessions': int, 'long': [float, ...], 'short': [float, ...]}`; `to_basis` writes it as `plan_reach_history` under the rule and `from_basis` reads it back; `with_premarket` and `with_reference` carry it.
  - `_plan_ladder(zones: list, targets: list, atr_rungs: list, all_rungs: list, *, trigger_cents: int, ref_cents: int, reach_cents: int, cluster_cents: Optional[int], atr: float, side: str, history: Optional[list]) -> list`, set on `SideLevels.plan_ladder` in price order outward. An entry: `price`, `far_price` (a zone only), `names`, `kind` (`level` or `atr_rung`), `role` (`t1`, `t2`, `t3`, `too_close` or `None`), `in_window`, `distance_atr` (cents past the trigger / ATR, rounded to 3), `strength` (levels only: the labels of every rung, kept or dropped, within `cluster_cents` of any of the entry's levels, equal counted), `stretch` (rungs only), `reached` (`{'k': int, 'n': int}`; `n` the side's history length, `k` the values at or above the unrounded distance).
  - A missing `reach_history` counts as an empty one (`n` 0). A `level_cluster_atr` that is not ok gives `strength` `None` and the side records `strength_status` with that status.

- [ ] **Step 1: Write the failing tests** in `TestPlanLadder` (bases with the seeded keys unless stated):
  - `test_iwm_calls_ladder`: prices in order `[279.17, 279.33, 280.73, 281.98, 283.79, 285.26, 286.48, 288.67]`; kinds; roles `too_close, too_close, None, None, t1, t2, None, None`; `in_window` False only for 288.67; 283.79 has `strength == ["PMK_H+1", "PDH+1"]`; 285.26 has `[]`; rung entries have no `strength` key.
  - `test_iwm_calls_zone_strength`: at merge 0.10 the first entry is price 279.17, far price 279.33, `strength == ["PDL+1"]`.
  - `test_iwm_puts_ladder`: prices `[274.67, 274.55, 273.42, 271.86, 269.88, 268.55, 266.11]`; 269.88 (`PML`) has `strength == ["PDL-1"]`.
  - `test_beyond_the_window_and_beyond_the_reach`: SPY calls list 779.37 (`PQH`) with `in_window` False at reach 3.0; IWM calls never list 305.18 (`PQH`); with reach 6.0 they do.
  - `test_distance_is_from_the_trigger_in_atr`: IWM calls 283.79 has `distance_atr == 0.999`.
  - `test_reach_counts`: with `reach_history = {"sessions": 250, "long": CALLS_REACH_D8, "short": PUTS_REACH_D8}`, IWM calls counts in ladder order are `8, 8, 6, 5, 4, 2, 2, 1` of 8 and IWM puts `6, 6, 5, 4, 3, 2, 1` of 8.
  - `test_no_history_counts_zero_of_zero`: no `reach_history`, and one with an empty side, both give `{'k': 0, 'n': 0}`.
  - `test_opens_broken_levels_and_dropped_rungs_are_not_on_it`.
  - `test_the_ladder_survives_a_json_round_trip`: `from_basis(json.loads(json.dumps(sl.to_basis())))` has equal `plan_ladder` on both sides.
  - `test_a_target_past_the_reach_is_still_listed`: IWM with reach 1.0 lists 283.79 and 285.26 with roles `t1` and `t2`, and no other entry past the reach.
  - Review Focus: `test_with_reference_and_with_premarket_rebuild_the_ladder`: on IWM, `sl.with_reference(277.00)` and `sl.with_premarket({...pre_low 275.00...})` return ladders measured from the new trigger, carry `reach_history`, and leave `gate_targets` equal to what the base gives for the same call (recorded in the test from Task 1's base run of the same two calls).
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_strat_levels.py -k TestPlanLadder -q` (expect FAIL: `plan_ladder` is `None`).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same command and `python3 -m pytest tests/lib tests/gcp/test_level_basis.py tests/gcp/test_signal_monitor_level_state.py tests/gcp/test_signal_monitor_level_refresh.py -q` (expect passed), then the render step.
- [ ] **Step 5: Commit:** `feat(strat): record each side's full ladder with strength and reach counts`

### Task 8: What the brief prints

Spec: Design 7, Design 8. Closes done_when[4].

**Files:**
- Modify: `lib/strat_levels.py` (`_legacy_trigger_dict` `:2914-2925`, `_plan_block` `:3192-3224`)
- Test: `tests/lib/test_strat_levels.py`

**Interfaces:**
- Consumes: `SideLevels.plan_ladder`, `fill_status`, `plan` (`merge_atr`, `merge_price`, `fill_sources`), targets' `zone`, `source`, `label`, `stretch`.
- Produces: `_legacy_trigger_dict` passes `plan_ladder` and `fill_status`; `_ladder_lines(trig: dict, plan: dict, spacing_text: str, atr_basis: Optional[str]) -> list`; `_plan_block` prints the ladder in place of the Skipped line when `trig.get('plan_ladder')` is not `None`, and keeps the Skipped line otherwise (a stored brief).

Exact copy (Design 7), the only strings this task adds:

```
    Ladder past {trigger}: targets at least {spacing} x ATR({n}) = {price} apart[, levels within {merge} x ATR({n}) = {price} are one zone]
      {price or "near to far"} ({names}): {notes}, {d} ATR past the trigger[, stronger ({rungs} ATR level[s])], {reached k of n | no history yet}
```

Notes, in this order when they apply: `T1` to `T3`; `ATR level`; `one zone`; `too close to sell`; `beyond the usual range`. A zone target line reads `T1: 274.67 to 274.55 (PDL, 11/9 Gap Low), sell 1/3 at 274.67`. A fill target's name carries its source: `(PDH+1.5 stretch, ATR level)` or `(PQH, beyond the usual range)`. The zone clause prints only when the merge distance in cents is above zero. A side short of targets with a non-empty fill list ends its hold wording with ` (no level or ATR level in reach for a further target)`. The multiples are printed with `multiple_text` and `atr_length`, never typed.

- [ ] **Step 1: Write the failing tests** in `TestLadderCopy`:
  - `test_seeded_golden`: `ladder_params(stored_1116('IWM'))` with `plan_reach_history` of the two Design 8 histories, rendered with bias `'bearish'`: the text contains the spec's Design 8 "Seeded" CALLS and PUTS blocks, copied character for character from the spec (lines 373 to 402).
  - `test_after_golden`: the same with `merge=0.10` and the three steps: the spec's "After" blocks (lines 408 to 437).
  - `test_spy_and_qqq_after_targets`: the T lines of the Design 8 table: SPY calls `T2: 762.63 to 763.04 (PQC, PWH), sell 1/3 at 762.63` and `T3: 779.37 (PQH, beyond the usual range), sell the last 1/3, or hold to the close or the stop`; QQQ puts `T2: 647.17 (PDL-1.5 stretch, ATR level), sell 1/3`.
  - `test_no_history_yet`: an empty side prints `no history yet` on every ladder line and the text never holds `0 of 0`.
  - `test_short_of_targets_says_why`: IWM with `["level_beyond_window"]` ends T2 with `sell 1/3, hold the last 1/3 to the close or the stop (no level or ATR level in reach for a further target)`; with the seeded empty list the line ends as the base prints it.
  - `test_the_hold_line_counts_the_thirds_left`, on a basis written in the test with a non-empty fill list: a side with one target prints `sell 1/3, hold the last 2/3 to the close or the stop (no level or ATR level in reach for a further target)`; a side with none prints `No target at least 0.25 x ATR(14) = 2.50 past the trigger: hold to the close or the stop. (no level or ATR level in reach for a further target)`; neither text holds `the last 1/3`.
  - `test_a_stored_brief_keeps_its_skipped_line`: `main_text_1116(t)` is what a markerless basis still renders.
  - Change `D8_CALLS` and `D8_PUTS` (`:1109-1125`): only the `Skipped, closer than ...` line, which becomes the ladder lines of this format for that fixture, written by hand in the test from the rule (trigger 252.10 and 248.20, ATR 14.00, spacing 3.50, reach 3.0, `level_cluster_atr` 0.15 so 210 cents, no history) before the code runs. `D8_NEXT_LEVELS` and `D8_ATR_LINE` are not touched.
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_strat_levels.py -k "TestLadderCopy or TestExitPlanCopy or TestAtrLevelsCopy" -q` (expect FAIL: the text holds `Skipped, closer than` where the ladder is expected).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run:** `python3 -m pytest tests/lib/test_strat_levels.py tests/lib/test_strat_levels_playbook.py tests/gcp/test_premarket_brief.py -q` (expect passed), then `git diff <base> -- tests/lib/test_strat_levels.py | grep '^-'` shows removed lines only at the two Skipped lines of `D8_CALLS` and `D8_PUTS`; then the render step.
- [ ] **Step 5: Commit:** `feat(strat): print the ladder with roles, strength and reach in the brief`

### Task 9: Stored briefs keep their plan, and a new basis rebuilds its own

Spec: Design 10; done_when "Stored briefs keep their plan". Closes done_when[5].

**Files:**
- Test: `tests/gcp/test_level_basis.py`

**Interfaces:**
- Consumes: everything of Tasks 4 to 8; `gcp.premarket_playbook_resolver.plan_inputs` (unchanged in this task).

- [ ] **Step 1: Write the tests:**
  - `test_a_stored_brief_keeps_targets_skipped_status_and_text` (parametrised ticker by `recorded` in `absent`, `ok`, `params_unavailable`, `input_unavailable`): the markerless basis rebuilds sides equal to `main_1116(t)` and renders `main_text_1116(t)` under bias `'bearish'`; `plan_inputs('calls' and 'puts', {}, stored, policy_fn=lambda: pytest.fail("no policy read"))` gives the target prices of `main_1116(t)` and `plan_available` True.
  - `test_a_head_built_basis_rebuilds_zones_fill_and_ladder_after_the_rows_change`: build `ladder_params(stored_1116('IWM'), merge=0.10, fill=steps)`, store `json.loads(json.dumps(sl.to_basis()))`; assert `stored["plan_ladder_status"] == "ok"`; rebuild with `from_basis(stored, params=<a LevelParams with merge 0.0 and an empty list>)`: targets, `fill_status` and `plan_ladder` equal the first build's (the recorded params win, the tables are never read).
  - `test_plan_inputs_reads_a_zones_nearest_edge_and_a_fill_target`: on that stored basis `plan_inputs('puts', ...)` gives targets `(274.67, 269.88, 268.55)` and `plan_inputs('calls', ...)` `(283.79, 285.26, 286.48)`, both `plan_available`.
  - `test_the_rule_version_did_not_move`: `LEVEL_RULE_VERSION` equals Task 1's recorded literal.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_level_basis.py -q` (expect all passed; this task closes behaviour the earlier tasks built). Record the red in the PR body: with the marker line of `from_basis` changed to `True`, the `recorded="params_unavailable"` case fails with no targets. Revert.
- [ ] **Step 3: Commit:** `test(strat): show a stored brief keeps its plan and a new basis rebuilds its ladder`

### Task 10: The resolver stores how far price went before the stop

Spec: Design 6; done_when "Reach history stored and read" (first half). Advances done_when[6].

**Files:**
- Modify: `gcp/schema.sql` (after `:2004`, inside the same ALTER), `gcp/premarket_playbook_resolver.py` (`:100`, `PlanOutcome` `:137`, `PlanInputs` `:151`, `resolve_plan` `:565-588`, `plan_inputs` `:611-624`, `_PLAN_FIELDS` `:877-878`)
- Test: `tests/gcp/test_premarket_playbook_resolver.py`

**Interfaces:**
- Produces:
  - Columns `calls_plan_mfe_atr DOUBLE PRECISION` and `puts_plan_mfe_atr DOUBLE PRECISION`, nullable, no default, `ADD COLUMN IF NOT EXISTS`.
  - `PlanInputs.atr: Optional[float] = None` (set by `plan_inputs` from the basis's `atr`; `None` for a row with no basis).
  - `PlanOutcome.mfe_atr: Optional[float] = None`, set by `resolve_plan` for an `entered` side with a positive finite `atr`: the highest high (calls) or lowest low (puts) over the bars after the fill bar and before the bar in which the stop is hit, as a distance from the trigger in the side's direction, floored at 0, divided by `atr`. The stop is looked for from the fill bar itself, as the leg walk does (`:572-576`). The measure reads the bars `resolve_plan` is given, so it stops at the exchange close on a half day.
  - `_PLAN_FIELDS` gains `'mfe_atr'`, so `_plan_columns` and `_plan_updates` bind both columns with no other edit.
  - `RESOLVER_VERSION = '2026-11-16.v5'`.

- [ ] **Step 1: Write the failing tests** in `TestPlanMfe` (helpers `_plan`, `_bar`, `_bars`, `_ts` of the file; calls trigger 100.00, stop 99.00, `atr=2.00`; puts trigger 100.00, stop 101.00, `atr=2.00`; one bar before the fill bar in every case):
  - `test_call_high_before_a_later_stop`: a high of 103.00 after the fill and a stop later gives 1.5.
  - `test_the_stop_bar_does_not_count`: the bar that hits 99.00 has a high of 104.00: still 1.5.
  - `test_a_high_on_the_fill_bar_does_not_count`.
  - `test_never_above_the_trigger_after_the_fill_is_zero`: 0.0, not `None`.
  - `test_not_entered_or_no_atr_is_none`: `no_cross`, `opened_through` and `late_cross` sides, and an entered side with `atr=None`, give `None`.
  - `test_a_stopless_side_is_measured_to_the_close`.
  - `test_a_fill_bar_that_touches_the_stop_is_zero`: a call filled at 100.00 whose fill bar's low is 99.00 and whose next bar's high is 104.00 gives 0.0; the mirrored put (fill bar high 101.00, next bar low 96.00) gives 0.0.
  - `test_put_mirrors`: a low of 97.00 before a later stop gives 1.5; the stop bar's low of 96.00 is ignored; a low only on the fill bar does not count; never below the trigger gives 0.0.
  - `test_half_day`: through `resolve_one` on 2025-11-28 (close 13:00 ET) with `plan_inputs` stubbed as `_resolve_half_day` does (`:1153-1167`), a call whose high is 101.00 before 13:00 and 105.00 at 14:30 binds `calls_plan_mfe_atr == 0.5`.
  - `test_resolve_one_sets_both_columns_and_the_version`: the UPDATE's SET list holds `calls_plan_mfe_atr = :calls_plan_mfe_atr` and the puts column, both are bound, and `bound['outcome_resolver_version'] == '2026-11-16.v5'`.
  - `test_schema_adds_the_two_mfe_columns_nullable_without_default` (the regex of `:1088-1100`).
  - `test_the_plan_outcome_is_otherwise_unchanged`: for the bars of `test_resolve_one_binds_the_plan_columns_from_a_v3_basis` (`:1001-1046`) every existing plan field equals the literal that test asserts.
  - Review Focus: `test_entered_on_the_last_bar_is_zero` and `test_stopped_on_the_bar_after_the_fill_is_zero`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_premarket_playbook_resolver.py -q` (expect FAIL: `PlanOutcome` has no `mfe_atr`).
- [ ] **Step 3: Implement.** The measure is taken in the same pass over the bars as the leg exits; it does not stop when every leg has exited.
- [ ] **Step 4: Run** the same command and `python3 -m pytest tests/gcp/test_apply_schema.py tests/gcp/test_level_basis.py -q` (expect passed), then the render step.
- [ ] **Step 5: Commit:** `feat(strat): store how far a plan's entry went before its stop, in ATR`

### Task 11: The brief reads the reach history in one query

Spec: Design 6 (the read); Capacity. Closes done_when[6].

**Files:**
- Modify: `gcp/premarket_brief.py` (a reader beside `_level_params_query`, `:950-954`; the call after `:980`; the keyword at `:1372-1376`)
- Test: `tests/gcp/test_premarket_brief.py`

**Interfaces:**
- Consumes: `LADDER_HISTORY_KEY`; `build_session_levels(..., reach_history=...)` (Task 7); `gcp.database.query_to_dataframe_strict`; `lib.eastern_time.sessions_between`.
- Produces: `read_plan_reach_history(query_fn, tickers: Sequence[str], session_date: date, sessions: int) -> Dict[str, dict]`, one entry per ticker asked, `{'sessions': sessions, 'long': [...], 'short': [...]}`, oldest first, empty lists for a ticker with no row. One statement:

```sql
SELECT ticker, analysis_date, calls_plan_mfe_atr, puts_plan_mfe_atr
FROM premarket_analysis
WHERE ticker IN (:t0, :t1, ...)
  AND analysis_date >= :first AND analysis_date < :session_date
  AND (calls_plan_mfe_atr IS NOT NULL OR puts_plan_mfe_atr IS NOT NULL)
ORDER BY ticker, analysis_date
```

  `:first` is the exchange session `sessions` sessions before `session_date`, from `lib.eastern_time`, so the read is bounded by two dates and the `(analysis_date, ticker)` unique index (CLAUDE.md 3.8: no DISTINCT, no outer LIMIT).

- [ ] **Step 1: Write the failing tests:**
  - `test_reach_history_is_one_query_for_every_ticker`: a recording `query_fn` given three tickers is called once; its parameters hold the three tickers, `session_date` and `first`; the SQL holds `analysis_date < :session_date` and both `IS NOT NULL` terms and no `DISTINCT`.
  - `test_reach_history_is_bounded_to_the_policys_sessions`: with `sessions=250` and session 2026-11-16, `first` is the 250th exchange session before it (written as a literal date in the test, read once from `sessions_between`); with `sessions=5`, `2026-11-09`.
  - `test_reach_history_never_reads_the_session_or_later`: a frame holding rows dated the session and after is not returned by the SQL the test runs on SQLite; a `BRIEF_AS_OF=2026-11-10` run asks for dates before 2026-11-10 only.
  - `test_reach_history_splits_sides_and_skips_nulls`: a row with calls 1.5 and puts NULL adds to `long` only; `n` of each side is its own count.
  - `test_a_failed_reach_read_raises`: a `query_fn` raising `ConnectionError` propagates out of `generate_premarket_brief`, and no `playbook` text holding `no history yet` is produced.
  - `test_a_value_that_is_not_finite_or_is_negative_raises`: `ValueError` naming the ticker and date (the resolver floors at 0, so such a value is a defect).
  - `test_the_brief_passes_the_history_to_the_builder`: with the frame of the Design 8 histories for IWM, `d['level_basis']['plan_reach_history']['long']` equals `CALLS_REACH_D8` and the playbook text holds `reached 4 of 8`.
  - `test_a_history_key_not_ok_runs_no_read`: with `ladder_history_sessions` `input_unavailable` the reader is not called and each side says `Targets unavailable (input_unavailable)`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_premarket_brief.py -k reach -q` (expect FAIL: `read_plan_reach_history` not defined).
- [ ] **Step 3: Implement.** The read runs once per brief run, after `load_level_params`, on the strict reader; nothing around it is caught.
- [ ] **Step 4: Run:** `python3 -m pytest tests/gcp/test_premarket_brief.py tests/gcp/test_premarket_brief_late_slot.py tests/gcp/test_premarket_brief_no_discord.py tests/meta/test_production_writers.py -q` (expect passed; if the brief spec's `TestNoPersist` is on the base, its stand-in answers the new SELECT with an empty frame, the only edit to that file), then the render step.
- [ ] **Step 5: Commit:** `feat(playbook): read the plan reach history once per brief run`

### Task 12: No numbers, no names, and nothing else moved

Spec: done_when "No numbers and no names", "Unchanged". Closes done_when[7] and done_when[8].

**Files:**
- Test: `tests/lib/test_level_params_structure.py`, `tests/lib/test_level_params_copy.py` (added assertions only)

- [ ] **Step 1: Add the assertions:**
  - in `test_the_walk_reaches_the_rules_it_must_cover` (`:186-197`): `{"_target_zones", "_fill_targets", "_plan_ladder"} <= reach`.
  - in `tests/lib/test_level_params_copy.py`: `LADDER_FORBIDDEN = ("0.1 x ATR", "0.15 x ATR", "3 x ATR")` and `test_no_plan_ladder_value_in_any_string_literal`, over the string literals of `lib/strat_levels.py`; and `test_the_fill_steps_are_named_once`, each of the three step names appearing as one string literal in that file.
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_level_params_structure.py tests/lib/test_level_params_copy.py -q` (expect passed; `test_no_numbers_on_the_level_and_plan_path` passes with no change to `ALLOWED_VALUES` or the allowed names). Record the red: a literal `0.1` typed into `_target_zones` fails `test_no_numbers_on_the_level_and_plan_path[lib/strat_levels.py]`. Revert.
- [ ] **Step 3: Run the unchanged pins,** each file unmodified but for the edits this plan names: `python3 -m pytest tests/lib/test_strat_levels.py -k "TestTargetSpacing or TestExitPlanCopy or TestAtrRungs or TestAtrRungsDisplayOnly or TestAtrLevelsCopy or TestPlanGapEdges or TestNextLevelsLadder or TestSessionPicks" tests/lib/test_movement_statement_level_basis.py tests/lib/test_level_params_behaviour.py tests/gcp/test_signal_monitor_level_state.py tests/gcp/test_signal_monitor_level_refresh.py tests/gcp/test_premarket_playbook_resolver.py tests/gcp/test_level_params_consumers.py -q` (expect passed).
- [ ] **Step 4: Run:** `make test` (expect no failure the base does not have), and `git diff <base> --stat -- tests/ | cat`: the only existing test files with removed lines are `tests/lib/test_strat_levels.py` (the two Skipped lines) and `tests/lib/test_level_params_loader.py` (the key-set pin).
- [ ] **Step 5: Commit:** `test(strat): reach the zone, fill and ladder rules from the no-numbers walk`

### Task 13: The Experiment, through the production paths, into a local copy

Spec: Experiment; done_when "Experiment". Closes done_when[9], its last clause in the order "done_when[9], and what is evidenced when" sets out. Nothing here writes to production, and no production policy row changes.

**Files:**
- Create: `scripts/research/plan_targets_experiment.py`
- Test: `tests/scripts/test_plan_targets_experiment.py`

**Interfaces:**
- Consumes: `gcp.premarket_playbook_resolver.plan_inputs`, `resolve_plan`; `lib.strat_levels.SessionLevels`, `parse_level_basis`; `lib.eastern_time.session_close`, `sessions_between`; `gcp.database.get_engine`.
- Produces, in the driver:
  - `ARMS`: `A` (`[]`, 0.0), `B` (`["level_beyond_window"]`, 0.0), `C` (`["atr_rung_beyond", "atr_rung_between"]`, 0.0), `D10` (`[]`, 0.10), `D15` (`[]`, 0.15), `DC` (`[]`, the basis's own recorded `level_cluster_atr` value), `S` (the three steps, 0.10).
  - `require_local_db() -> None`: raises unless `DB_HOST` is `localhost` or `127.0.0.1` and `CLOUD_SQL_CONNECTION_NAME` is unset. Every subcommand calls it first.
  - `arm_basis(basis: dict, arm: str) -> dict`: a copy with the `target_fill_sources` and `target_merge_atr` records of `basis["params"]` replaced by the arm's.
  - `day_trade(calls: PlanOutcome, puts: PlanOutcome) -> Optional[str]`: the one trade of a ticker-day from the two sides' outcomes: `None` when either side is `opened_through`, when neither is `entered`, or when both are `entered` with equal `fill_ts`; else the side with the earlier `fill_ts`.
  - `score(first: date, last: date, tickers, out_csv) -> None`: one bar read per ticker-month, cut at `session_close` as `resolve_one` does (`:764-765`); one row per trade and arm: `ticker, date, arm, side, r, exit, t1_hit, t2_hit, t3_hit, n_targets, targets, t3_source, zone_closer_than_spacing`.
  - `legs_hit(outcome: PlanOutcome) -> tuple[bool, bool, bool]`: the source of `t1_hit`, `t2_hit`, `t3_hit`. Target k was hit before the stop exactly when the label `t{k}` is in `outcome.exit.split(',')`. The leg exits are causal (`gcp/premarket_playbook_resolver.py:572-580`): targets count only from the bar after the fill bar, and a bar touching the stop and a target counts the stop. `PlanOutcome.t1_hit_ts` to `t3_hit_ts` are never read by the driver: they scan from the first bar that reached the trigger to the end of the session and do not stop at the stop (`:546-553`).
  - `report(csv) -> str`: the tables Step 6 lists; the range by resampling whole days 2,000 times with `numpy.random.default_rng(7)`.
  - `export_daily_parquet(tickers, data_dir: Path) -> None`: per ticker, the frame `lib.data_loader.DataLoader()._load_daily_from_sql(ticker, None)` returns from the local copy, written as `<data_dir>/<ticker>/<ticker>_<year>.parquet`, the files `DataLoader.load_daily` reads when Cloud SQL is not active (`lib/data_loader.py:513-528`). `lib.data_loader._cloud_sql_active` looks at `CLOUD_SQL_CONNECTION_NAME` alone (`:146-148`), which the local copy must leave unset, so the brief's `loader.load_daily` (`gcp/premarket_brief.py:991`, `:1346`) reads these files and not the imported table. `lib/data_loader.py` is not changed.
  - Subcommands `load-daily`, `load-minutes`, `export-daily-parquet`, `replay`, `score`, `report`. `score --compare-stored <csv>` rebuilds arm A from each stored basis in the csv and fails on any side whose targets differ from the row's six stored plan prices (tested on the IWM fixture with its prices from `main_1116`). `replay` sets `DATA_DIR` (`gcp/premarket_brief.py:4323`) to the directory given and refuses to start when a ticker has no file there.

- [ ] **Step 1: The inputs. Ask the owner once before running** (two read-only exports; no `--commit`): (a) `market_data_daily` for SPY, QQQ and IWM from 2018-10-01 to 2026-11-10, every column, one `scripts/db_query_cr.sh` statement a ticker, saved from the execution's `result_001.csv`; (b) the 1-minute bars of the three tickers for 2019-01 to 2026-11 from the bucket copy `gs://<GCS_BUCKET>/intraday-bars/v1/1min/` (downloaded with `gsutil -m cp -r`). Record the execution ids and each file's sha256. If the bucket copy lacks a month, stop and report; do not refetch from the vendor.
- [ ] **Step 2: Write the driver's failing tests:** `test_refuses_a_database_that_is_not_local` (three environments); `test_the_brief_loader_reads_the_exported_daily_rows` (with `CLOUD_SQL_CONNECTION_NAME` unset and `_load_daily_from_sql` answered from a frame written in the test, `export_daily_parquet` then `DataLoader(data_dir=tmp).load_daily('SPY', on_stale='warn')` returns the same rows and columns, and `premarket_snapshot_from_daily(df, date(2026, 11, 10))` gives that row's `pre_high`, `pre_low` and `pre_vwap`); `test_replay_refuses_a_ticker_with_no_daily_file`; `test_day_trade` (the six cases of its docstring, on `PlanOutcome` literals); `test_hits_are_before_the_stop`, on synthetic bars through `resolve_plan` (call, trigger 100.00, stop 99.00, targets 101.00, 102.00, 103.00): the stop on the bar after the fill and 101.00 two bars later gives `(False, False, False)` while `outcome.t1_hit_ts` is set; 101.00 reached only on the fill bar, then a close at 100.50, gives `(False, False, False)`; one bar touching 99.00 and 101.00 gives `(False, False, False)`; 101.00 then the stop gives `(True, False, False)`; and the mirrored put cases; `test_arm_basis_changes_two_records_only` (on `ladder_params(stored_1116('IWM'))`: every other key of the basis equal; `DC` writes the basis's own recorded `level_cluster_atr` value, read from the fixture in the test); `test_arm_a_scores_the_bases_targets` (IWM 2026-11-16 with four bars written in the test: arm A's `targets` column equals `283.79|285.26`); `test_the_range_is_seeded` (two calls of the resampler on a 30-day frame give the same pair). Run: `python3 -m pytest tests/scripts/test_plan_targets_experiment.py -q` (expect FAIL: no module), implement, run again (expect passed), render step, commit `feat(strat): add the plan targets experiment driver`.
- [ ] **Step 3: The local copy.** The image and schema apply of CI's `integration-tests` job (`.github/workflows/backtest-pipeline.yml:110-150`):

```bash
docker run -d --name plan_lab -e POSTGRES_USER=trading_user -e POSTGRES_PASSWORD=testpass \
  -e POSTGRES_DB=trading -p 5432:5432 pgvector/pgvector:pg15
PGPASSWORD=testpass psql -h localhost -U trading_user -d trading -v ON_ERROR_STOP=1 -f gcp/schema.sql
export DB_HOST=localhost DB_USER=trading_user DB_PASS=testpass DB_NAME=trading
unset CLOUD_SQL_CONNECTION_NAME CLOUDSDK_AUTH_ACCESS_TOKEN
python3 -m scripts.research.plan_targets_experiment load-daily <dir of step 1a>
python3 -m scripts.research.plan_targets_experiment load-minutes <dir of step 1b>
python3 -m scripts.research.plan_targets_experiment export-daily-parquet --tickers SPY,QQQ,IWM --data-dir "$PWD/plan_lab_data"
python3 -m gcp.calibrate_level_params --history 2022-01-03 2026-11-10 --tickers SPY,QQQ,IWM
```

  Expect the calibration to exit 0 and every one of the three tickers to hold `target_merge_atr` 0.0 and both reach keys with status `ok` on 2022-01-03 and on 2026-11-10 (one `psql` read; paste it). Paste the three tickers' reach values on 2026-11-10: the spec did not compute them.
- [ ] **Step 4: Arm A's bases, by the production brief.** With the model keys unset so no model call is made (check on the first session that the run exits 0 and its log shows no model request; not verified when this plan was written):

```bash
python3 -m scripts.research.plan_targets_experiment replay 2022-01-03 2026-11-10 --tickers SPY,QQQ,IWM --data-dir "$PWD/plan_lab_data"
```

  which runs, per session, `DATA_DIR=<data dir> BRIEF_AS_OF=<date> BRIEF_TICKERS=SPY,QQQ,IWM python3 -m gcp.premarket_brief` and nothing else. Run the first session alone and read its three rows before the rest: each `level_basis` has `status` `ok`, `last_bar_date` 2021-12-31 and a `prior_close` equal to that day's close in the local `market_data_daily`. A row with status `no_data` or `stale_daily`, or a ticker with no row, means the brief did not read the imported bars: stop. Then expect one `premarket_analysis` row a ticker-session with a `level_basis` whose `plan_ladder_status` is `ok`. Paste the count, and the count of rows whose basis status is not `ok` (expect 0).
- [ ] **Step 5: Score.** `python3 -m scripts.research.plan_targets_experiment score 2022-01-03 2026-11-10 --tickers SPY,QQQ,IWM --skip SPY:2025-04-09 --skip IWM:2026-06-26 --out plan_targets_all.csv`, then `python3 -m scripts.research.plan_targets_experiment report plan_targets_all.csv`.
  **Gate: arm A must total +176.8 R over 3,463 trades, to 0.1 R, before any other arm is read.** If it does not, stop, post arm A's total, trade count and per-ticker totals beside the gap-edges spec's (+64.2, +114.0, -1.4), and ask the owner how to go on. No other arm's number is posted.
- [ ] **Step 6: The PR body shows,** per arm: total R; SPY, QQQ, IWM; the six-month blocks of the gap-edges spec (Mar to Aug and Sep to Feb, first and last partial); the 90% range of arm minus A (whole days, 2,000 draws, seed 7), overall and per ticker; the share of entered trades reaching T1, T2 and T3 before the stop; the count of traded sides with fewer than three targets; the count of trades whose targets differ from A; for B, C and S the source of each T3 and its hit rate by source; for D10, D15, DC and S the trades where a zone sold closer than the spacing and their R against A. Also the driver's and the csv's sha256 prefixes and the commands above.
- [ ] **Step 7: Check the shortcut against a real replay.** In the local copy only, insert the Design 9 rows with `:swap_date` `'2026-11-02'`, run `python3 -m gcp.calibrate_level_params --history 2026-11-02 2026-11-10 --tickers SPY,QQQ,IWM`, replay 2026-11-02 to 2026-11-10 again, and assert with the driver (`score --compare-arm S`) that each of the 21 ticker-days' rebuilt targets equal arm S's from `arm_basis`. Paste the result. A difference is a defect in the rule's rebuild, fixed before any arm is proposed.
- [ ] **Step 8: Which arm may be proposed** (spec, "What keeps today's rule"): an arm whose range against A lies wholly below zero overall, or for two of the three tickers, is not proposed. If no fill arm passes, `target_fill_sources` stays empty; if no merge arm passes, `target_merge_atr` stays 0.0; the PR says so. An arm whose range spans zero is put to the owner as "no worse, by this test", with its totals and blocks. The PR proposes; it changes no production row.
- [ ] **Step 9: The production path, arm A only, in the two parts "done_when[9], and what is evidenced when" sets out.**
  - **9a, on the PR head. Ask the owner once before running** (read-only, `scripts/db_query_cr.sh` without `--commit`): for the sample sessions the owner allows (Decision 5 recommends five) among the stored sessions that carry a `level_basis`, read `ticker, analysis_date, calls_plan_t1_price, calls_plan_t2_price, calls_plan_t3_price, puts_plan_t1_price, puts_plan_t2_price, puts_plan_t3_price, level_basis` from `premarket_analysis` where `run_kind = 'live'`. Assert with the driver (`score --compare-stored <csv>`) that arm A's targets, rebuilt by the branch from each stored basis, equal the six stored plan prices of that row: the seeded rows reproduce the plan production published. Paste the execution id and the comparison. This needs nothing of this PR in production.
  - **9b, the dry run by the deployed job. Ask the owner once before running,** and only when the brief spec's dry run is on main and deployed: for each sample session, `gcloud run jobs execute premarket-brief --region us-east1 --update-env-vars="^|^BRIEF_AS_OF=<date>|BRIEF_NO_PERSIST=true|BRIEF_TICKERS=SPY,QQQ,IWM" --wait`; each side's printed targets equal the local build's for that session. Each run calls the model. Which keys the printed `level_basis` can show depends on what production holds at that moment, and the section named above says which record is read in each case.

### Task 14: Close: product record, site note and the gate

Spec: "Source identity and close-out"; done_when "Source identity", and the last item. Closes done_when[10] and done_when[11] (but for the owner's steps). Once the site-note steps start, no file under `gcp/`, `lib/`, `scripts/` or `tests/` changes without redoing them.

- [ ] Push with `git push -u origin feature/feat-strat-001-plan-always-three-targets` and open a **draft** PR. Body: the spec's and this plan's paths; the 12 done_when items as `- [ ]` lines; `Red then green`; the Capacity section of Global Constraints; Task 1's base check; Task 13's results; the order against the brief spec and which was on main; the choices this plan made; and the sentence "Merging applies gcp/schema.sql to production through apply-schema-on-change".
- [ ] Set `pr:` in this plan to the PR's number.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, the `### FEAT-STRAT-001` record (`:233`): Status and Last reviewed for this PR (seeded rows change no target; implementation under review, not deployed).
- [ ] `docs/product/12-PR-ISSUE-TRACEABILITY.md`, `### FEAT-STRAT-001` (`:547`): add the PR to its lineage, naming spec PR #1998. Commit both and the plan: `docs(product): record the plan ladder under FEAT-STRAT-001`.
- [ ] Site note, step 1: with a clean tree, `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`; copy its `source_identity_sha256`.
- [ ] Site note, step 2: in `docs/product/03-SITE-TRACEABILITY.md`, the `| FEAT-STRAT-001 | DASHBOARD-01 |` row (`:1350`) and no other byte: the new hash, then this change's prose (backend source and local tests only: the brief's plan block lists the ladder with roles, strength and reach counts; targets unchanged under the seeded rows; tests named), then ` Earlier: ` and the earlier prose unchanged. Commit: `docs(site): note the plan ladder on DASHBOARD-01`.
- [ ] Site note, steps 3 and 4: run `produce` again and commit `docs(site): regenerate the source snapshot`; then `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` (expect exit 0). If `origin/main` moved, merge it into the branch (never a rebase of a pushed branch), re-render and redo the four steps.
- [ ] Render step once more and `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect all pass).
- [ ] Docs audit: `python3 scripts/maintenance/docs_audit.py` on the branch and on a detached `origin/main` worktree; the branch reports nothing `main` does not.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` (expect exit 0).
- [ ] Push; tick each done_when box with its evidence; only then mark the PR ready. done_when[9] is ticked only as "done_when[9], and what is evidenced when" allows, and a ticked line holds evidence that exists (test names, execution ids, sha256 prefixes) and no promise. Gate files are not touched, so no red-team pass is owed. **Ask the owner once before merging** (see "Merge is a production schema change").

## Close-out (not tasks; the owner's steps)

From the spec's "Source identity and close-out". None is done by the implementer without the owner's own yes, read-only checks included, and each yes is recorded separately on the PR or a new issue.

1. **First yes (also the merge):** the five seeded rows and the two columns reach production. Then deploy the calibration job and run it in history mode so SPY, QQQ and IWM each hold `target_merge_atr` and the two reach keys with status ok; confirm by one read. Not checked for this plan: `gcp/deploy.sh` has no target named for `gcp/calibrate_level_params.py`, and the job has no per-key mode (it writes every key for every session of the range, `gcp/calibrate_level_params.py:386-391`), so the range of that history run and how the job is deployed are read from the live job and put to the owner before the step.
2. Deploy the brief (`./gcp/deploy.sh` target for `premarket-brief`) and the resolver (`./gcp/deploy.sh playbook-resolver`), after step 1's read. Confirm the next live brief records `plan_ladder_status` ok and `plan_ladder_params` with the five rows effective 2015-01-02, prints the ladder, and that its targets equal what `SessionLevels.from_basis` gives for the same basis with the marker removed. Re-resolve 2026-11-14 onward and confirm the two columns fill for entered sides.
3. **Second yes, on the Experiment's results:** insert the Design 9 rows with the values the owner picks, run the calibration, check the first session those rows cover by one dry run, and confirm the next brief prints three targets where the ladder allows.
4. On a `docs/` branch after the merge: the DASHBOARD-01 note and this plan's `status: done`.
