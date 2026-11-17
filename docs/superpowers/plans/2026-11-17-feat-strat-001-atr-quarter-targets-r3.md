---
feat_id: FEAT-STRAT-001
spec: docs/superpowers/specs/2026-11-17-feat-strat-001-atr-quarter-targets-r3.md
branch: feature/feat-strat-001-atr-quarters-r3
pr: null
status: ready
---

# The exit plan sells a quarter at 25, 50, 75 and 100 percent of ATR from the entry, the levels are waypoints, and thirds leave the data: implementation plan (r3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the order of the spec's frontmatter, [0] (Policy rows) to [14] (catalog, gate and the owner's yeses). The map below names each.

**Goal:** Seed the four quarters as the plan of every session, so a side takes its targets at the entry trigger plus or minus mark x ATR, sells a quarter at each, prints the session's levels between them as waypoints with the hit-rates reach counts, and every reader (resolver, signal monitor, movement statement, explanations, the analysis and validation scripts) reads four targets in `t1..t4`; ship and test, without running it on production, the tooling that rebuilds every stored brief row on the quarters; and run the Experiment again on this builder before the owner's yes to merge.

**Architecture:** One builder, `lib.strat_levels.build_session_levels`. A fresh build records the marks version `feat-strat-001.v6` unless the marks row in force is an empty list (arm A, a local or test input only). `_pick_side` keeps today's trigger and stop and asks `plan_target_rule(version)` which rule picks the targets: the level walk (unchanged) or the mark walk `_plan_mark_targets` plus the waypoint builder `_plan_waypoints`. For a marks side `gate_targets` are its targets, so the `t1..t4` columns, the resolver, the monitor's T1 and the movement statement read the quarters. `entry_rule_version` (from #2062) maps v6 to the level-rule version it is built on, or to the `rebuilt_from_rule_version` a rebuilt basis records, so reach counts and rates pool by entry. `rebuild_on_marks` reruns only the mark walk and the waypoints on a stored basis's recorded entry; `SessionLevels.from_basis` returns it for a rebuilt basis; `scripts/maintenance/rebuild_quarter_history.py` drives it in six modes.

**Tech Stack:** Python, pandas, numpy, SQLAlchemy `text()` through `gcp.database`, pytest (`monkeypatch`, the SQLite `ParamsDb` of `tests/lib/level_params_fixtures.py`), Postgres 15 (`pgvector/pgvector:pg15`) for CI's integration job, the rebuild tests and the Experiment's local copy.

**Spec:** docs/superpowers/specs/2026-11-17-feat-strat-001-atr-quarter-targets-r3.md (r3: approved, stocks #2053, on `origin/main` d35d9ce23). It supersedes r2 (`docs/superpowers/specs/2026-11-16-feat-strat-001-atr-quarter-targets-r2.md`, now `superseded`). The hit-rates r2 spec and plan (`docs/superpowers/specs/2026-11-17-feat-strat-001-target-hit-rates-r2.md`, `docs/superpowers/plans/2026-11-17-feat-strat-001-target-hit-rates-r2.md`) define the interfaces Tasks 3, 6, 7, 11 and 13 consume; read them beside this plan.

## Global Constraints

- Base: `origin/main` after the hit-rates r2 build (stocks PR #2062) has merged (Merge order, Decision 9; see "Order, and the #2062 dependency"). Branch `feature/feat-strat-001-atr-quarters-r3`. This plan is committed alone on `docs/plan-feat-strat-001-quarters-r3` and merged before the code branch opens.
- The owner's rule, exact values: targets are `[0.25, 0.5, 0.75, 1.0]` x ATR(14) from the entry trigger, calls above and puts below, a quarter sold at each, the levels printed by name as waypoints between them, no snapping. IWM 2026-11-16, ATR 4.874951, offsets 122, 244, 366 and 487 cents: calls 280.14, 281.36, 282.58, 283.79 from 278.92; puts 274.64, 273.42, 272.20, 270.99 from 275.86. IWM calls T4 283.79 is on PWH; IWM puts T1 is 274.64, never 274.67.
- The seed: `gcp/schema.sql` seeds exactly one new `level_param_policy` row, `plan_target_marks_atr`, method `policy`, extra `{"marks": [0.25, 0.5, 0.75, 1.0]}`, `effective_from` `'2015-01-02'`, under `ON CONFLICT (param_key, effective_from) DO NOTHING`. No existing row changes. `exit_legs` `{"legs": 3}` and `plan_target_level_types` are read only for a level-rule basis. No `ladder_history_sessions` key and no swap rows.
- A marks side's leg count is its number of marks; `exit_legs` is never read for it; `resolve_plan` never cuts one of its targets.
- Rule versions: the marks version is `feat-strat-001.v6`; v3, v4 and v5 are the level-rule versions. A basis built under the empty list records the merge base's `LEVEL_RULE_VERSION`. No file under `lib/`, `gcp/` or `platform/` compares a value with a rule version constant outside `is_current_pick_rule`, `entry_rule_version`, `plan_target_rule` and the population lines of `lib/movement_statement.py`.
- Storage: nine nullable columns, no `plan_t4_price`: `calls_t4_price`, `puts_t4_price` on `premarket_analysis` and on `premarket_analysis_history`; `calls_t4_hit_ts`, `puts_t4_hit_ts`, `calls_plan_t4_hit_ts`, `puts_plan_t4_hit_ts`, `puts_reanchor_t4` on `premarket_analysis`. A marks side writes its targets to `t1..t4` and no `plan_t` price. One new table, `premarket_targets_archive`.
- Reach counts are read, not stored here: no reach column, no reach key. The brief reads them in #2062's one `lib.target_reach` query a run, filtered to `entry_rule_version` of the basis being built; a line `d` cents past the trigger counts the trades whose `excursion_atr` (the seeded `touch_atr` measure) is at least `d / (ATR x 100)`.
- No silent fallback (CLAUDE.md 3.7). A key that is not ok publishes no target and records its status; there is no fallback to the level walk; a failed reach read raises inside `lib.target_reach` and the brief prints #2062's unavailable line, never `no history yet`; a missing value is `None` and prints as words, never 0.
- Distances are compared in cents through `price_cents`. An offset is rounded to the cent once and added to the trigger's cents.
- No number and no name in the level code (done_when[10]): on the `build_session_levels` walk `lib/strat_levels.py` holds no numeric literal but 0, 1, -1, 2, -2 and 100 (`tests/lib/test_level_params_structure.py`) and no new numeric module constant; the count of string literals containing `25%`, `50%`, `75%`, `100%`, `1/4` or `quarter` equals the merge base's; percents and shares are formatted from the policy values.
- Unchanged (done_when[11]): the trigger and stop rule, the opened-through rule, the entry cutoff, the ATR rungs and their thinning, the NEXT LEVELS Calls and Puts lines, PMG zones, the signal monitor's fire decisions apart from the T1 its level state reads, persona plans, the CALL/PUT pick, and, for a basis built under a local empty marks list or a stored level-rule basis, the level rule's spaced walk, thirds, gap-edge targets, gate targets and the `t1..t3` columns.
- Not in this PR: any insight risk rule, `gcp/insight_discord_push.py`, `lib/agents/schema.py`, any solyra file (Decision 8), `gcp/deploy.sh` (FEAT-DEPLOY-001), the Design 13 drop.
- **The merge is a production change.** `apply-schema-on-change` applies `gcp/schema.sql` on the merge, and the seeded row puts the quarters in every brief built by the new image. Auto-merge is never enabled; the merge waits for the Experiment in the body and the owner's yes recorded on the PR, and for Decision 7 (the conviction change deployed, or the owner accepting the N2 warning) and Decision 8 (the insight's Discord line and solyra's target fields changed under their own work).
- Production access. No task writes to production. Each production read is marked **Ask the owner once before running**: Task 14 Step 1 (one read-only export, one bucket download, the `count` read and the job timeout read). No `--commit`, no deploy, no schema apply, no policy row change and no `--persist` run from this branch.
- Replays go through production code (CLAUDE.md 3.5, 3.6): bases built by `gcp.premarket_brief.main` with `BRIEF_AS_OF`, scored by `gcp.premarket_playbook_resolver.plan_inputs` and `resolve_plan`, excursions by #2062's `plan_excursion`. No driver walks bars, computes an indicator or a level, or replaces `targets` or `legs` on a `PlanInputs`.
- Tests are hermetic. CI's Run Tests job checks out one commit with no `origin/main`: no test runs a git command; "equal to origin/main's" is pinned by a literal or a fixture file recorded from the base. `.gitignore` ignores `*.csv`: prefer JSON or `.txt` fixtures.
- **The render step.** Every commit that moves lines in `gcp/`, `lib/` or `scripts/` ends with `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`, then `python3 -m pytest tests/scripts/test_check_generated_docs.py tests/meta/test_model_registry_consistency.py -q` (expect all passed), staging whichever docs changed.
- `tests/lib/test_movement_statement.py` patches `gcp.research.strat_engine.strat_pred_serve`: run it with `requirements-research.txt` installed (CI's `research-test` job) and report both jobs; a local skip is not a pass.
- The source-snapshot verifier runs with its fixed ceilings (`--max-seconds 5 --max-input-bytes 16777216 --max-entries 20000`). If it refuses on size, stop, post the measured size and ask the owner; never raise a ceiling, never edit the verifier.
- Commits: conventional `type(scope): description`, imperative, no AI attribution. Every new test has a red then green record in the PR body. No em or en dashes in code comments, copy or docs written for this change.

## Review Focus

Inputs the spec implies and no done_when test pins, most likely first. Each has a test in the task that owns the code.

- **Archive run twice, or run again after rebuild.** A second `archive` while an unrestored archive of the same key exists refuses and writes nothing, so `restore` always returns the first, pre-rebuild row; `restore` stamps `restored_at`, after which a key may be archived again. Task 11.
- **A row whose one side has no trigger.** A side that published no trigger (orb_only, any reason) is kept exactly as recorded with no target; only a side with a trigger and no stop, or a basis with no ATR, refuses the row. A reasonable person expects a one-sided morning to be rebuilt, not refused. Task 7.
- **Derived builds of a rebuilt basis.** `with_reference` (the put re-anchor) and `with_premarket` (the planner) on a session that `from_basis` returned through `rebuild_on_marks` raise nothing, keep the recorded ATR and place the marks from the new trigger; on a rebuilt basis that recorded no params the side carries `params_unavailable` and no target. Task 7.
- **The longer playbook in Discord.** The IWM After text through `_playbook_code_fields` gives fields that rejoin to the same lines in order, none over the field limit and none cut (the spec did not check the split). Task 6.
- **A rebuild that fails part way.** One ticker's transaction failing leaves the other tickers rebuilt and the failed one byte-equal to its archive; `restore` after it returns the pre-archive snapshot. Task 11.

---

## Order, and the #2062 dependency

**This plan does not start until #2062 is on `main`.** Task 1 Step 1 checks it before the branch is cut. If the hit-rates build has not merged: no branch, no cherry-pick, no copy of its code here, and no work on its branch (another session owns it). The code branch is cut only from a `main` that holds it, so the PR is never stacked and never opened before its base exists.

Already on `main` d35d9ce23 (run 2026-11-17): the brief build (#2010, `BRIEF_NO_PERSIST`), the unknown rule version refusal (#2043, `rule_version_status`, `REFUSED_RULE_VERSION_STATUSES`), the prior-close prints (#2046, `LEVEL_RULE_VERSION = 'feat-strat-001.v5'` at `lib/strat_levels.py:1542`, `PICK_RULE_VERSIONS = (LEVEL_RULE_V3, LEVEL_RULE_V4, LEVEL_RULE_VERSION)` at `:1543`). So the marks version is `feat-strat-001.v6`.

What this plan uses from #2062, read on its head 03aeefe43 (2026-11-17); Task 1 Step 2 re-reads each on the merge base and the base's names win:

| #2062 interface | Where | Used by |
|---|---|---|
| `entry_rule_version(version) -> Optional[str]`: its argument for every `is_current_pick_rule` version, else None | `lib/strat_levels.py` (after `is_current_pick_rule`) | Task 3 extends it to v6 and to rebuilt bases |
| `TARGET_REACH_RATE_KEY` in `POLICY_WIDE_KEYS`; `REACH_UNAVAILABLE = 'input_unavailable'` | `lib/strat_levels.py` | Task 6 |
| `format_levels_for_brief(..., reach=None, reach_min_sample=None)` and `_plan_block(..., reach=None, reach_min_sample=None)`, printing nothing from `reach` today | `lib/strat_levels.py` | Task 6 prints the counts on the marks lines |
| `load_target_reach(query_fn, tickers, session_date, param, rule_version) -> Dict[str, ReachTable]`; `ReachTable(ticker, n, first, last, values)` with `count_at_least(d)`, `count_text(d, min_sample)`, `header_text()`; `unavailable_text(status)`, `NO_STOP_TEXT`, `NO_HISTORY_TEXT`, `TargetReachUnavailable` | `lib/target_reach.py` | Tasks 6, 7 |
| `_load_reach_for_brief(level_params, tickers, analysis_date)` calling `entry_rule_version(LEVEL_RULE_VERSION)` | `gcp/premarket_brief.py` | Task 6 keys it by the version being built |
| `plan_excursion(direction, plan, bars, atr) -> ExcursionResult`, `basis_atr(basis)`, `trade_of_day`, `excursion_statement`; `resolve_one` writes the day's row keyed `entry_rule_version(basis['rule_version'])`; `RESOLVER_VERSION = '2026-11-17.v5'` | `gcp/premarket_playbook_resolver.py` | Tasks 3, 8, 13 |
| `score_session` and `run` keyed by `entry_rule_version(...)` | `gcp/backfill_plan_excursions.py` | Task 3 |
| `plan_excursions` table, `target_reach_rate` seed row | `gcp/schema.sql` | Tasks 6, 11, 14 |

## The r2 plan, the branch, and the local r2 build

**Choice: (a), a new plan bound to r3 with a new branch.** (b), amending the r2 plan, is refused by the gate either way it could be made, and the r2 plan cannot move off `status: ready`. Run on `origin/main` d35d9ce23 in a scratch worktree, each edit staged and reverted afterwards (`python3 scripts/gate/spec_gate.py --commit`, exit 1 each):

| Edit | Gate's answer | Code |
|---|---|---|
| r2 plan's `spec:` set to r3, on its own branch (`SPEC_GATE_BRANCH=feature/feat-strat-001-atr-quarter-targets`) | "names spec docs/superpowers/specs/2026-11-16-feat-strat-001-atr-quarter-targets-r2.md on the base; a plan binds one spec" | `plan_stays_bound`, `:1682-1684` |
| the same edit from this docs branch | "only the plan's own branch edits it, except the close after merge, which sets status: done and changes nothing else" | `check_changed_plans`, `:2127-2129` |
| r2 plan `status: ready` to `done`, from this docs branch | "closes a plan whose PR #None is not yet in the base's record for FEAT-STRAT-001; the close follows the merge, so the lineage or the row names the PR first" | `:2130-2132`, `pr_recorded_on_base` |
| r2 plan `status: ready` to `superseded` | "only the plan's own branch edits it, except the close after merge ..." | `:2127-2129`; `PLAN_STATUSES = ("ready", "done")`, `:1351` |
| a code change on the r2 branch, plan untouched | "...-r2.md is status: superseded; point the plan at the spec that replaced it" and "...-r2.md is superseded by ...-r3.md; point the plan at the current spec" | `:2515-2525` |

So the only value the gate accepts for the r2 plan is the one it holds: `status: ready`, unchanged. It authorizes nothing (the last row), it is not edited here, and it stays as the record, as the hit-rates r1 plan and the three-targets plan did. **This differs from the r3 spec**, which says the r2 plan "is pointed at this file by its own change before any code PR opens": the gate refuses that (first row). Reported to the owner with this plan.

The new branch `feature/feat-strat-001-atr-quarters-r3` (38 characters) is named by no other plan. With this plan staged in the same scratch worktree, a code change committed for that branch passes: `spec gate ok (branch=feature/feat-strat-001-atr-quarters-r3, 2 changed file(s))` (run 2026-11-17). On this docs branch, `--commit` and `--pr origin/main` both pass.

**The local r2 build** at `/tmp/build-quarters` (branch `feature/feat-strat-001-atr-quarter-targets`, head feca59809, merge base 862c5e2ea, never pushed) did r2 Tasks 1 to 13 and the site note of Task 15. Its commits are reachable from this repository's object store. It is read only; it is never pushed (the gate refuses its branch). Each task below names the commit it carries and lists what r3 changes against it. **Carry by `git cherry-pick -n <sha>` at the start of the task**, not by merging the r2 branch: that branch holds two commits r3 drops and a site note r3 redoes, and its merge of `main` (924df4a96) predates #2062, so its files conflict with #2062's in `lib/strat_levels.py`, `gcp/premarket_brief.py`, `gcp/premarket_playbook_resolver.py`, `gcp/schema.sql` and their tests. Resolve conflicts toward #2062's code, apply the task's r3 changes, then commit once with the task's message and the body line `Carries <sha> from the local r2 build.` Record the red by running the task's new tests on the branch head before the task, in a second worktree.

| r2 build commit | r2 task | r3 |
|---|---|---|
| 4cde10efb pin today's plan on the three stored bases | 1 | carried, Task 1 |
| 1b0df27b3 seed the marks and reach history rows | 2 | carried with changes, Task 2 |
| fedcce438 name the marks rule version and its target rule | 3 | carried with changes, Task 3 |
| ac31be4c0 place plan targets at ATR marks | 4 | carried with changes, Task 4 |
| 5b819ea67 list levels as waypoints | 5 | carried with changes, Task 5 |
| e0c568e40 print mark targets, waypoints and reach counts | 6 | carried in part, Task 6 |
| c8142d518 pin stored briefs and the marks basis rebuild | 7 | carried with changes, Task 7 |
| 67aacca2e store and score a fourth plan target | 8 | carried with changes, Task 8 |
| da339c071 store the plan's reach before the stop in ATR (`*_plan_mfe_atr`) | 9 | **dropped**: r3 reads `plan_excursions` (What changed from r2, item 1) |
| b0f6891fc read the plan reach history in one query | 10 | **dropped** but for one API test carried in Task 9 |
| 9469a4d6c the marks schema on the ephemeral Postgres | 11 | carried with changes, Task 11 |
| a8603c7a7 reach the mark walk from the no-numbers walk | 12 | carried with changes, Task 12 |
| 66826a4d6, 79342753c the Experiment's driver | 13 | carried with changes, Task 13 |
| feca59809 the DASHBOARD-01 site note | 15 | **redone**, Task 15 (new hash, new prose) |

## Capacity (CLAUDE.md Rule 0; spec Designs 10 and 12), copied into the PR body

- **Volume:** one policy row; nine nullable columns; one archive table; each new `level_basis` gains a waypoint list of about 3 to 10 entries a side (IWM 2026-11-16: 5 and 3) and loses the skipped list; no reach values in the basis.
- **Velocity:** no new query in the brief or the resolver: the counts come from #2062's one read a run (about 3,500 rows for three tickers). The rebuild tool, per run: `count` one statement; `archive` one `INSERT ... SELECT` per table and ticker (6) plus one for `plan_excursions` per ticker (3); `rebuild` one read and one batched `UPDATE ... FROM (VALUES ...)` per table and ticker (12), plus one `load_level_params` read per distinct session date whose basis recorded no parameters (count reports how many); `resolve` the production `resolve_one` per session, about 3 round trips each (bars read, the row's UPDATE, the excursion upsert), about 3,700 sessions.
- **Wall-clock:** brief and resolver unchanged. `resolve` at 0.5 to 2 s a round trip is about 1.5 to 6 h in all, 0.5 to 2 h a ticker, so it runs per ticker; `rebuild` is seconds a ticker. Measured on the local copy (Task 14 Step 6) for one ticker's real count and shown with the job timeout that FEAT-DEPLOY-001's entry will carry (at least 4x the measured run).
- **Cost:** $0 scheduled; no new job, schedule or image in this PR. The Experiment and the rebuild measurement run locally. Each production dry run after the merge costs one brief's model calls and is the owner's step.
- **I/O shape tests:** Task 6 (one reach read for N tickers, #2062's), Task 11 (archive and rebuild statements a ticker and table).

## Choices this plan makes where the spec leaves one open (each reported to the owner with the plan)

1. **New plan, new branch** (above).
2. **Test inputs keep the level rule.** With the quarters seeded, every test that builds through `fixture_params` or `legacy_db` would build v6. Those helpers gain a `marks` argument whose default is the empty list (arm A, test input only), so the existing level-rule pins keep passing unedited (spec Design 5, last rows of the table); `seeded_policy()` and `ParamsDb()` stay the schema's own, so the seed is what they read. Marks cases pass `marks=` explicitly.
3. **`entry_rule_version(version, rebuilt_from_rule_version=None)`** extends #2062's helper, and `basis_entry_rule_version(basis)` reads both keys of a basis; a live v6 basis maps to `LEVEL_RULE_MARKS_ENTRY`, typed as the literal the merge base's `LEVEL_RULE_VERSION` holds, so a later level rule that moves `LEVEL_RULE_VERSION` cannot relabel stored v6 rows.
4. **`rebuild_on_marks(...)` returns a `SessionLevels`**, whose `to_basis()` is the rebuilt basis, so `from_basis` can return it and the tool can store it. A rebuilt basis records `rebuilt_from_rule_version` and `rebuilt_marks`.
5. **Counts in the copy.** `reach=None` (any caller but the brief, and the rebuild tool) prints no `Reached before the stop` line and no count; a `ReachTable` with `n == 0` prints no header line and `no history yet` on each line. The rebuilt playbook of a stored row therefore carries no counts (its counts would be as of a date the history job reads differently).
6. **Batched rebuild writes** (Capacity), where the spec says "one read and one UPDATE a row": one transaction a ticker and table either way.
7. **A row with no `level_basis`** is rebuilt in its columns only: `t1..t4` at the marks from its stored trigger and the ATR `derive_level_map_from_daily` gives, NULL plan prices, outcomes and `llm_playbook`, its playbook's plan blocks re-rendered; `level_basis` stays NULL and `verify` reports such rows on their own line. The spec names no rule version for them.
8. **The archive adds `restored_at`**, and `archive` refuses a key with an unrestored archive (Review Focus 1).
9. **Writing modes roll back unless `--commit`** is given, as `scripts/db_query_cr.sh` does; `count` and `verify` never write.
10. **The rebuild tool's Postgres cases live in `tests/integration/test_rebuild_quarter_history_pg.py`**, which CI runs on pg15 with `gcp/schema.sql` applied; `tests/scripts/test_rebuild_quarter_history.py` (the spec's file) holds its hermetic cases. A Postgres case under `tests/scripts/` would skip in CI's Run Tests job.
11. **`count`'s SQL is one statement in `gcp/queries/quarter_history_count.sql`**, which the tool runs and `./scripts/db_query_cr.sh -f` can run read-only from a session.

## Where the spec cannot be met as written, or is stale (reported to the owner, not resolved silently)

1. **Pointing the r2 plan at r3**: refused by the gate (table above). This plan names a new branch instead.
2. **`docs/product/infrastructure/05-h-DATA_DICTIONARY.md` in the implementation PR** (done_when[7]): `check_product_scope` refuses any `docs/product/` file but the catalog, traceability, model registry and the three rendered inventory docs on a feature branch ("changes in this feature change; under docs/product/ only the FEAT's own catalog ...", `scripts/gate/spec_gate.py:4403-4408`; run 2026-11-17 in PR mode with `PR_HEAD_REF=feature/feat-strat-001-atr-quarters-r3` on a scratch commit of this plan plus one 05-h row: exit 1 with that message; the same probe with an `ERD.drawio` edit instead passes). Task 10 makes that edit on its own `docs/` branch, merged before the implementation PR is marked ready; its done_when tick cites that PR. `ERD.drawio` (repository root) is allowed and changes in the implementation PR.
3. **Design 11 "Deploy order"** says an image that does not know v6 rebuilds it under the v2 rule. Since #2043 (on `main`), `SessionLevels.from_basis` first refuses a version above the newest it knows (`rule_version_status`, `rule_version_newer`, `LevelRuleVersionUnknown`). Readers first is still the order; the cost of the wrong order is a refused row (the resolver leaves it pending and exits 1; the monitor and the API refuse it), not a v6 row scored on v2 targets.
4. **done_when[10]'s counts** were 0, 0, 0, 0, 0 and 5 on d410174b2 and are so on d35d9ce23 (run), but #2062's head 03aeefe43 gives `quarter` 6 (run, by `ast`). The pins are the merge base's (Task 1 Step 3).
5. "the policy fixture gains the two new keys" (Design 5) is r2's wording: r3 adds one key; `target_reach_rate` comes with #2062.
6. done_when[12] names "the new outcome field mfe_atr", which r3 no longer adds; the baseline mode needs neither it nor #2062's excursion, and measures 5 to 8 read `plan_excursion` (Task 13).
7. Design 12 clears `llm_playbook` on every rebuilt row, including a marks-version row built live, whose text already explains the quarters. The plan follows the spec (verify demands it).

## done_when map

| done_when | What | Task |
|---|---|---|
| [0] | Policy rows | 2 |
| [1] | ATR marks are the targets | 4 |
| [2] | Waypoints and the stronger case | 5 |
| [3] | Brief copy | 6 |
| [4] | Rule version and stored briefs | 3, 7 |
| [5] | The fourth target is stored and scored | 8, 11 |
| [6] | Alerts and the movement statement read the quarters | 9 |
| [7] | Thirds leave the analysis code and the docs | 10 |
| [8] | History rebuild tooling | 7, 11, 14 |
| [9] | Reach counts read, not stored here | 3, 6 |
| [10] | No numbers and no names | 1, 12 |
| [11] | Unchanged | 1, 12 |
| [12] | Experiment through the production paths | 13, 14 |
| [13] | Source identity (DASHBOARD-01) | 15 |
| [14] | Catalog, traceability, gate; production only on the owner's yes | 15, Close-out |

## File map

| File | Change | Task |
|---|---|---|
| `tests/fixtures/level_basis_2026-11-16/` | `<T>.main.json`, `<T>.main.txt`, `sources.json` (carried, re-recorded on the base) | 1 |
| `tests/fixtures/plan_excursions_iwm_2026-10-23_2026-11-13.json` | new: Design 7's sixteen rows | 6 |
| `tests/lib/session_levels_helpers.py` | `stored_1116`, `main_1116`, `main_text_1116`, `stored_text_1116`, `marks_basis`, `reach_1116`, `v2_basis_off_pick` | 1, 4, 6, 7 |
| `tests/lib/level_params_fixtures.py` | `marks` argument of `fixture_params` and `legacy_db` | 2 |
| `gcp/schema.sql` | the marks row; nine columns; `premarket_targets_archive` | 2, 8, 11 |
| `lib/strat_levels.py` | key, versions, helpers, mark walk, waypoints, copy, `rebuild_on_marks`, `from_basis` | 2 to 7 |
| `gcp/premarket_brief.py` | `_load_reach_for_brief` key; `structured_playbook_columns`; `build_persist_rows` | 6, 8 |
| `gcp/premarket_playbook_resolver.py` | excursion key; `LegOutcome`, `PlanOutcome`, `resolve_leg`, `resolve_one`, self-heal, `RESOLVER_VERSION` | 3, 8 |
| `gcp/backfill_plan_excursions.py` | `score_session` key | 3 |
| `gcp/signal_monitor.py`, `lib/movement_statement.py`, `platform/api/schemas.py`, `gcp/brief_explanations.py` | the quarters on alerts, rates and the prompt | 7, 9 |
| `scripts/analysis/honest_scoring_experiment.py`, `scripts/validation/validate_brief_accuracy.py`, `gcp/queries/nan_triage.sql`, `ERD.drawio` | thirds out; four targets | 10 |
| `docs/product/infrastructure/05-h-DATA_DICTIONARY.md` | on its own `docs/` branch | 10 |
| `scripts/maintenance/rebuild_quarter_history.py`, `gcp/queries/quarter_history_count.sql` | new | 11 |
| `scripts/analysis/atr_marks_experiment.py`, `tests/fixtures/atr_marks_spike_2026-11-16/` | carried, changed | 13 |
| `tests/meta/test_level_rule_version_readers.py`, `tests/meta/test_production_writers.py` | allowed sites and writers | 3, 11, 13 |
| tests: `tests/lib/test_strat_levels.py`, `test_level_params_loader.py`, `test_level_params_structure.py`, `test_level_params_copy.py`, `test_movement_statement.py`; `tests/gcp/test_level_basis.py`, `test_premarket_playbook_resolver.py`, `test_premarket_brief.py`, `test_backfill_plan_excursions.py`, `test_signal_monitor.py`, `test_signal_monitor_level_state.py`, `test_brief_explanations.py` (new), `test_premarket_filter_params.py`; `tests/api/test_movement_statement_router.py`; `tests/scripts/test_validate_brief_accuracy.py`, `test_rebuild_quarter_history.py` (new), `test_atr_marks_experiment.py`; `tests/integration/test_atr_marks_schema_pg.py`, `test_rebuild_quarter_history_pg.py` (new) | as each task says | 1 to 13 |
| `docs/product/02`, `12`, `03` (DASHBOARD-01 row only), `docs/review-evidence/site-source-snapshot.json`, rendered `05-a`, `05-c`, `05-e` | close; render step | 15 |

---

### Task 1: Preconditions, the carry, and today's plan pinned on the stored bases

Spec: Merge order (What changed from r2, item 6; Decision 9); Design 6 ("Which number the marks version is"); Design 7 ("Fixtures"). Advances done_when[11]; supplies done_when[1] to [4] and [10].

**Files:**
- Create (carried from 4cde10efb): `tests/fixtures/level_basis_2026-11-16/{IWM,SPY,QQQ}.main.json`, `{IWM,SPY,QQQ}.main.txt`, `sources.json`
- Modify: `tests/lib/session_levels_helpers.py`
- Test: `tests/lib/test_strat_levels.py` (`TestStored20261116`)

**Interfaces:**
- Produces: `stored_1116(ticker: str) -> dict` (the `level_basis` of `tests/fixtures/premarket_2026_11_16/brief_rows.json`, a v3 basis, a fresh copy each call); `main_1116(ticker) -> dict`; `main_text_1116(ticker) -> str`; new in r3, `stored_text_1116(ticker) -> str` (the `playbook` of `tests/fixtures/premarket_2026_11_16/brief_rows_text.json`).

- [ ] **Step 1: Precondition check on `origin/main`, before the branch is cut.** Paste each output into the PR body:
  - `git log --oneline origin/main | grep '(#2062)'` names the hit-rates build; on `origin/main`, `grep -n "^def entry_rule_version" lib/strat_levels.py`, `ls lib/target_reach.py`, `grep -n "CREATE TABLE IF NOT EXISTS plan_excursions" gcp/schema.sql` and `grep -n "^def plan_excursion\|^def basis_atr\|^RESOLVER_VERSION" gcp/premarket_playbook_resolver.py` each find their line.
  - `grep -n "^LEVEL_RULE_VERSION\|^PICK_RULE_VERSIONS\|^def is_current_pick_rule\|^def rule_version_status" lib/strat_levels.py` shows `'feat-strat-001.v5'` and `(LEVEL_RULE_V3, LEVEL_RULE_V4, LEVEL_RULE_VERSION)`. Record the literal: Task 3 types it as `LEVEL_RULE_MARKS_ENTRY`.
  - `grep -n "^status" docs/superpowers/specs/2026-11-17-feat-strat-001-atr-quarter-targets-r3.md` reads `approved`.
  If #2062 is not on `main`, **stop**: no branch, no cherry-pick, nothing of #2062 copied here; report and wait.
- [ ] **Step 2: Cut the branch and re-read every line.** `git worktree add -b feature/feat-strat-001-atr-quarters-r3 <dir> origin/main`. Record in the PR body the base's line of every function this plan names (`grep -n "^def \|^class \|^    def " lib/strat_levels.py lib/target_reach.py lib/movement_statement.py gcp/premarket_playbook_resolver.py gcp/premarket_brief.py gcp/signal_monitor.py gcp/backfill_plan_excursions.py`) and #2062's interfaces as they landed; where one differs from "Order, and the #2062 dependency", the base's name is used and the difference listed.
- [ ] **Step 3: The six counts of done_when[10], on the merge base**, before any code: `python3 -c "import ast;t=ast.parse(open('lib/strat_levels.py').read());c=[n for n in ast.walk(t) if isinstance(n,ast.Constant) and isinstance(n.value,str)];[print(repr(s),len(h),h) for s in ('25%','50%','75%','100%','1/4','quarter') for h in [sorted(n.lineno for n in c if s in n.value)]]"`. d35d9ce23 gives 0, 0, 0, 0, 0 and 5; #2062's head gives `quarter` 6. Paste the output with its line numbers; Task 12 types these six into its test.
- [ ] **Step 4: Carry 4cde10efb:** `git cherry-pick -n 4cde10efb`.
- [ ] **Step 5: Re-record what the base gives.** Run the r2 build's one-off record again on the merge base (not committed): per ticker, `sl = SessionLevels.from_basis(stored_1116(t))`; per side `trigger`, `stop`, `targets`, `skipped`, `gate_targets`, `target_status`, `plan` from `sl.to_basis()`, and `plan_inputs` for both sides, into `<T>.main.json`; `format_levels_for_brief(sl.to_level_map(), 'bearish')` into `<T>.main.txt`. If a byte differs from the carried file, the base's file is committed, `sources.json`'s `base_commit` names the merge base, and the diff is listed in the PR body.
- [ ] **Step 6: Tests** in `TestStored20261116`: the carried four (`test_sources_json_matches_the_files`, `test_iwm_trigger_and_stop`, `test_main_records_match`, `test_iwm_text_is_the_specs_today_block`, the last now against r3's Design 7 "Today" block, spec lines 594 to 608) and `test_stored_text_is_main_on_the_plan_blocks`: the CALLS and PUTS blocks of `stored_text_1116('IWM')` equal those of `main_text_1116('IWM')`.
- [ ] **Step 7: Run:** `python3 -m pytest tests/lib/test_strat_levels.py -k TestStored20261116 -q` (expect all passed: this task pins the base, so there is no red). A failure is a finding about the stored row or the spec's text, reported on the PR, never a changed expectation.
- [ ] **Step 8: Commit:** `test(strat): pin today's plan on the three stored 2026-11-16 bases`

### Task 2: The marks row, seeded with the quarters

Spec: Design 2 (first paragraph), Design 8, Decision 1; done_when "Policy rows". Closes done_when[0].

Carries 1b0df27b3. r3 changes against it: (1) the seed is `{"marks": [0.25, 0.5, 0.75, 1.0]}`, not `[]`; (2) no `ladder_history_sessions`: drop `LADDER_HISTORY_KEY`, `ladder_history_sessions()`, its `policy_wide_param` branch, its seed row and its tests; (3) the test helpers gain `marks` (Choices, item 2); (4) the seed comment names r3.

**Files:**
- Modify: `gcp/schema.sql` (the seed `INSERT`, after `plan_target_level_types`), `lib/strat_levels.py`, `tests/lib/level_params_fixtures.py`, `tests/gcp/test_premarket_filter_params.py` (the schema hash pin), `tests/gcp/test_level_params_consumers.py` (as carried)
- Test: `tests/lib/test_level_params_loader.py`

**Interfaces:**
- Produces, in `lib/strat_levels.py`: `PLAN_TARGET_MARKS_KEY = 'plan_target_marks_atr'`, named once, in `POLICY_WIDE_KEYS`; `plan_target_marks(extra) -> Optional[tuple]` (the list as floats; empty for `[]`; None for a missing or non-list value, a non-number or bool entry, an entry at or below zero, or one not above the one before); `policy_wide_param` gives value `float(len(marks))`, status ok, when that is not None, else `input_unavailable`; `LevelParams.plan_target_marks(self) -> Optional[tuple]`.
- Produces, in `tests/lib/level_params_fixtures.py`: `LEVEL_RULE_MARKS_EXTRA = {"marks": []}`; `fixture_params(..., marks: Optional[Sequence[float]] = None)` (None: the empty list); `legacy_db(..., marks: Optional[Sequence[float]] = None)` writes a `plan_target_marks_atr` policy row with that extra effective 2015-01-03; `install_level_params` passes `marks` through.

- [ ] **Step 1: Write the failing tests** (`seeded_policy`, `ParamsDb`):
  - `test_schema_seeds_the_quarters_row`: one row in force from 2015-01-02, method `policy`, extra `{"marks": [0.25, 0.5, 0.75, 1.0]}`; `exit_legs` extra `{"legs": 3}`; the seeded policy without this key equals a literal dict of the base's rows (typed from the base).
  - `test_marks_key_is_policy_wide_and_named_once`: in `POLICY_WIDE_KEYS`; the string appears in exactly one string literal of `lib/strat_levels.py` (by `ast`).
  - `test_marks_param_status` (parametrised, `ParamsDb.set_policy` at a later date): `[]` ok 0.0; the quarters ok 4.0; `[0.25]` ok 1.0; `input_unavailable` for `{}`, `{"marks": null}`, `{"marks": "0.25"}`, `[0.25, "0.5"]`, `[true]`, `[0.0, 0.5]`, `[-0.25]`, `[0.25, 0.25]`, `[0.5, 0.25]`.
  - `test_seeded_marks_are_ok_with_value_four`: `ParamsDb().load(['IWM'], date(2026, 11, 16))['IWM']` gives the key ok, value 4.0, and `plan_target_marks() == (0.25, 0.5, 0.75, 1.0)`.
  - `test_fixture_params_default_is_the_level_rule`: `fixture_params().plan_target_marks() == ()`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_level_params_loader.py -q` (expect FAIL: no `PLAN_TARGET_MARKS_KEY` on the base).
- [ ] **Step 3: Implement** the row (note: `'plan targets at these distances past the entry trigger, in ATR, nearest first; one sale a mark'`), the key, the reader, the branch, the accessor and the two helper arguments; re-pin `SCHEMA_SHA256` with the old and new hash in the PR body.
- [ ] **Step 4: Run again** (expect PASS), then `python3 -m pytest tests/lib tests/gcp tests/api tests/meta -q` (expect no failure the base does not have).
- [ ] **Step 5: Render step, then commit:** `feat(strat): seed the four quarter marks as the plan policy`

### Task 3: The marks version, its target rule and its entry rule

Spec: Design 6; Design 4 (second paragraph); hit-rates r2 Design 4. Advances done_when[4] (the version clauses) and done_when[9] (the entry version).

Carries fedcce438. r3 changes against it: (1) #2062's `entry_rule_version` is extended and `basis_entry_rule_version` added; (2) `LEVEL_RULE_MARKS_ENTRY`; (3) #2062's two writers key by the basis's entry version; (4) r2's swap-row test is replaced by `test_a_past_session_builds_the_quarters`; (5) the meta test also watches `LEVEL_RULE_MARKS_ENTRY`.

**Files:**
- Modify: `lib/strat_levels.py`, `gcp/premarket_playbook_resolver.py` (`resolve_one`'s excursion key), `gcp/backfill_plan_excursions.py` (`score_session`'s key), `tests/meta/test_level_rule_version_readers.py`
- Test: `tests/lib/test_strat_levels.py`, `tests/gcp/test_level_basis.py`, `tests/gcp/test_premarket_playbook_resolver.py`, `tests/gcp/test_backfill_plan_excursions.py`

**Interfaces:**
- Produces, in `lib/strat_levels.py`, beside the version constants:
  - `LEVEL_RULE_MARKS = 'feat-strat-001.v6'`; `LEVEL_RULE_MARKS_ENTRY = '<the literal Task 1 Step 1 recorded>'`; `LEVEL_PICK_RULE_VERSIONS = (LEVEL_RULE_V3, LEVEL_RULE_V4, LEVEL_RULE_VERSION)`; `PICK_RULE_VERSIONS = LEVEL_PICK_RULE_VERSIONS + (LEVEL_RULE_MARKS,)`. `is_current_pick_rule`, `rule_version_status` and `newest_pick_rule_version` are unchanged and now know v6.
  - `TARGET_RULE_V2 = 'v2'`, `TARGET_RULE_LEVELS = 'levels'`, `TARGET_RULE_ATR_MARKS = 'atr_marks'`; `plan_target_rule(version) -> Optional[str]` (v2, a level-rule version, v6; None otherwise, a non-str included).
  - `build_rule_version(params: LevelParams) -> str`: `LEVEL_RULE_VERSION` when the marks row is ok with value 0, else `LEVEL_RULE_MARKS`.
  - `entry_rule_version(version, rebuilt_from_rule_version=None) -> Optional[str]`: a level-rule version with nothing rebuilt gives itself; v6 with nothing rebuilt gives `LEVEL_RULE_MARKS_ENTRY`; v6 rebuilt from v2 or a level-rule version gives that version; anything else None.
  - `basis_entry_rule_version(basis: Optional[dict]) -> Optional[str]`: `entry_rule_version(basis.get('rule_version'), basis.get('rebuilt_from_rule_version'))`; None for no basis.
  - `build_session_levels` records `build_rule_version(params)`; `_pick_side` routes by `plan_target_rule(rule_version)` (the `atr_marks` branch publishes no target with `input_unavailable` until Task 4) and raises `LevelRuleVersionUnknown` for None.
  - `resolve_one` and `score_session` key the `plan_excursions` row by `basis_entry_rule_version(basis)`.

- [ ] **Step 1: Write the failing tests:**
  - `test_plan_target_rule` (meta file): the four answers by literal version strings `'feat-strat-001.v2'` to `'.v6'`; None for `'feat-strat-001.v1'`, `'feat-strat-001.v7'`, None and 6.
  - `test_marks_version_is_a_known_pick_rule`: `is_current_pick_rule('feat-strat-001.v6')`; `rule_version_status` of it is `RULE_VERSION_KNOWN`; `newest_pick_rule_version() == 'feat-strat-001.v6'`; `'feat-strat-001.v7'` is `RULE_VERSION_NEWER`.
  - `test_entry_rule_version` (parametrised): (v3) v3; (v4) v4; (v5) v5; (v6) the merge base's literal; (v6, v2) v2; (v6, v3) v3; (v6, v5) v5; (v6, v6), (v6, `'x'`), (v5, v2), (v2), (None), (`'feat-strat-001.v7'`) None; and `basis_entry_rule_version` on the same pairs as dicts, and on None.
  - meta: `WATCHED` gains `LEVEL_RULE_MARKS`, `LEVEL_RULE_MARKS_ENTRY`, `LEVEL_PICK_RULE_VERSIONS`; `ALLOWED` gains `('lib/strat_levels.py', 'plan_target_rule')`; `entry_rule_version` stays allowed; the scan passes only if no other site compares with a watched name.
  - `test_fresh_build_version_follows_the_marks_row` (`tests/gcp/test_level_basis.py`): `ParamsDb()` (the seed) builds v6; a later empty-list row builds `LEVEL_RULE_VERSION`; `{"marks": "x"}` builds v6 with both sides `target_status == 'input_unavailable'` and no target; the key absent (its seed row deleted) builds v6 with `params_unavailable`.
  - `test_a_past_session_builds_the_quarters`: `ParamsDb().load` for 2016-03-01 builds v6 (spec Design 8: a `BRIEF_AS_OF` replay of any past session builds the quarters).
  - `test_resolve_one_keys_the_excursion_by_entry_version` (the writer stand-in of #2062's tests): a live v6 basis writes `rule_version` equal to the merge base's literal; a v6 basis with `rebuilt_from_rule_version` v2 writes v2.
  - `test_history_job_keys_by_entry_version`: `score_session` on a live v6 basis writes the merge base's literal.
- [ ] **Step 2: Run:** `python3 -m pytest tests/meta/test_level_rule_version_readers.py tests/lib/test_strat_levels.py tests/gcp/test_level_basis.py tests/gcp/test_premarket_playbook_resolver.py tests/gcp/test_backfill_plan_excursions.py -k "rule or version or entry or quarters" -q` (expect FAIL: no `plan_target_rule`; #2062's helper maps v6 to None).
- [ ] **Step 3: Implement.** No other comparison with a version constant anywhere.
- [ ] **Step 4: Run again** (expect PASS), then `python3 -m pytest tests/lib tests/gcp tests/api tests/meta -q`. A test that builds through `ParamsDb()` and pins level targets now builds v6 with no target: give it the level rule with `db.set_policy(PLAN_TARGET_MARKS_KEY, effective_from=date(2015, 1, 3), extra='{"marks": []}')`, never a changed expectation and never a fallback in code; list each in the PR body.
- [ ] **Step 5: Render step, then commit:** `feat(strat): name the quarter marks rule version and its entry rule`

### Task 4: The marks are the targets, and the gate targets

Spec: Design 2; Design 11 ("Gate targets"). Closes done_when[1].

Carries ac31be4c0. r3 changes against it: (1) the leg count is the number of marks and `exit_legs` is not read: the keys checked are `PLAN_TARGET_MARKS_KEY` then `ENTRY_CUTOFF_KEY` (r2 also checked `EXIT_LEGS_KEY` and refused more marks than legs; both go); (2) `gate_targets` are the side's targets (r2 kept `rungs[1:4]`), so `_legacy_trigger_dict`'s `targets` and `room_to_first_target` are T1; (3) `marks_basis` loses its `legs` argument; (4) `test_seeded_empty_list_is_the_base` becomes `test_local_empty_list_is_the_base` (arm A) and also compares `gate_targets`.

**Files:**
- Modify: `lib/strat_levels.py`, `tests/lib/session_levels_helpers.py`
- Test: `tests/lib/test_strat_levels.py` (`TestAtrMarkTargets`)

**Interfaces:**
- Consumes: `plan_target_rule`, `LevelParams.plan_target_marks`, `stored_1116`, `main_1116`, `main_text_1116`.
- Produces:
  - `mark_prices(trigger: float, atr: float, marks: Sequence[float], sign: int) -> list[float]`: `(price_cents(trigger) + sign * price_cents(m * atr)) / 100` each; the one place the arithmetic lives (Tasks 9 and 11 reuse it).
  - `_plan_mark_targets(out: SideLevels, trig: dict, ref: float, atr: float, params: LevelParams, prior_close: Optional[float]) -> None`, called from `_pick_side` for `TARGET_RULE_ATR_MARKS`. The first of the two keys not ok publishes no target and sets `target_status` to its status.
  - `out.plan` for a marks side: `{'rule': 'atr_marks', 'marks': [...], 'mark_prices': [...], 'atr', 'atr_basis', 'legs': len(marks), 'entry_cutoff_et', 'entry_cutoff_status', 'gap_fill_flag_atr', 'gap_fill_flag_status'}`; no spacing key.
  - each target `{'price', 'cents', 'name': 'T{k}', 'timeframe': '', 'mark', 'share': '1/{legs}', 'source': 'atr_mark'}`; `out.skipped == []`; `out.gate_targets` a copy of `out.targets`.
  - `target_status` `'input_unavailable'` and no target when two marks land on one cent, an offset is zero cents, a puts target is at or below zero cents, or the list is empty.
  - `marks_basis(basis: dict, marks: Sequence[float], *, marks_extra: Optional[dict] = None) -> dict` (test helper): a copy whose recorded `plan_target_marks_atr` param is the given one (built with `policy_wide_param(...).to_basis()`), `rule_version` v6, `long` and `short` removed.

- [ ] **Step 1: Write the failing tests**, each on `SessionLevels.from_basis(marks_basis(stored_1116(t), ...))`:
  - `test_iwm_quarters`: calls `[280.14, 281.36, 282.58, 283.79]`, puts `[274.64, 273.42, 272.20, 270.99]`.
  - `test_every_side_is_trigger_plus_or_minus_the_offset` (SPY, QQQ, IWM x two sides): each target's cents equal `price_cents(trigger) + sign * price_cents(mark * atr)` with `atr = fixture[fixture['atr_basis']]`, the arithmetic done in the test.
  - `test_each_target_records_mark_share_and_source`: marks in order, `share == '1/4'`, `source == 'atr_mark'`.
  - `test_gate_targets_are_the_four_targets` (six sides), and the level map's `calls_trigger['room_to_first_target']` is measured to T1.
  - `test_trigger_and_stop_are_the_bases` (six sides): equal `main_1116(t)`; IWM calls 278.92 `PMK_H`, stop 275.86 `PMK_L`; IWM puts 275.86 `PMK_L`, stop 277.41 `PQL`.
  - `test_no_target_is_moved_onto_a_level`: IWM puts T1 is 274.64 and no target is 274.67.
  - `test_skipped_is_empty` (six sides).
  - `test_three_marks_three_legs`: marks `[0.25, 0.5, 0.75]`: the first three prices of `test_iwm_quarters` and `plan['legs'] == 3`.
  - `test_no_target_cases` (parametrised, each `targets == []`): a marks record `input_unavailable` (`{"marks": "x"}`) and one `params_basis_mismatch` (status carried); `[0.25, 0.2501]` on an ATR of 1.0; `[0.0001]` on the IWM ATR; a puts trigger 1.00 with `[1.0]` on an ATR of 2.0. The last three on `d8_basis`-style synthetic bases.
  - `test_local_empty_list_is_the_base` (three tickers, arm A): `stored_1116(t)` with a recorded `{"marks": []}` and `exit_legs` 3, its own `rule_version` kept: `targets`, `skipped`, `target_status`, `gate_targets` and the text equal `main_1116(t)` and `main_text_1116(t)`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_strat_levels.py -k TestAtrMarkTargets -q` (expect FAIL on every marks case; `test_local_empty_list_is_the_base` passes already and is recorded so).
- [ ] **Step 3: Implement** `mark_prices` and `_plan_mark_targets`; the share text is formatted from the leg count.
- [ ] **Step 4: Run again** (expect PASS) and `python3 -m pytest tests/lib/test_strat_levels.py -q`.
- [ ] **Step 5: Render step, then commit:** `feat(strat): place the plan and gate targets at the quarter marks`

### Task 5: Levels are waypoints, and a target on a level is the stronger case

Spec: Design 3. Closes done_when[2].

Carries 5b819ea67. r3 changes against it: `test_derived_builds` expects `gate_targets` equal to the new targets placed from the new trigger (r2 expected the level rule's gate targets).

**Files:**
- Modify: `lib/strat_levels.py`
- Test: `tests/lib/test_strat_levels.py` (`TestPlanWaypoints`)

**Interfaces:**
- Produces: `SideLevels.plan_waypoints: Optional[list] = None`, `SideLevels.waypoint_zone_status: Optional[str] = None` (`to_dict` adds both only when `plan_waypoints is not None`, so a level-rule side's record is byte-equal to the base's); `_pick_side(..., levels: Optional[list] = None)` passed by `_assemble`; `_plan_waypoints(out, levels, ref, atr, params, window, prior_close) -> None` after `_plan_mark_targets` when the side has targets; an entry `{'price', 'cents', 'names': [...], 'segment', 'distance_atr'}` plus `'zone': {'far_price', 'members': [{'price', 'names'}, ...]}` for a zone; `segment` is `before_t1`, `t{i}_t{i+1}` or `beyond`, formatted from the target index; a target on a level's cent gains `'on_level': [names]` and that level is no waypoint; a prior close as waypoint or `on_level` carries the gap fill keys by `_plan_targets`'s rule. Range: strictly past the trigger, to the last target, past it only while `_within_staleness_window(price, ref, atr, window)`. Zones: within one segment, a level joins the open group when its cents from the group's nearest member are at most `price_cents(level_cluster_atr * atr)`, equal joins; `LEVEL_CLUSTER_KEY` not ok gives one entry a cent and that status.

- [ ] **Step 1: Write the failing tests** (the carried ones), on the quarters:
  - `test_waypoints_are_the_fixtures_levels` (six sides): the expected list computed in the test from the fixture's `levels`, trigger, targets, window and `level_cluster_atr` record, with its own grouping loop.
  - `test_iwm_calls_by_name` (PDO 278.95, PDH 279.17, PMC 279.33 `before_t1`; CMO 281.64 `t2_t3`; PMH 285.26 `beyond`) and `test_iwm_puts_by_name` (PDL 274.67 `before_t1`; `11/9 Gap Low` 274.55 `t1_t2`; PML 269.88 `beyond`).
  - `test_a_target_on_a_level_is_the_stronger_case`: IWM calls T4 283.79 `on_level` contains `PWH`; no waypoint at 28379 cents.
  - `test_one_cent_away_is_a_waypoint`, `test_zones` (PDO and PDH one entry with `far_price` 279.17, PMC alone; a level exactly at the cluster distance joins, a cent farther does not; never across a target), `test_cluster_not_ok`, `test_level_rule_side_has_no_waypoint_key`.
  - `test_derived_builds`: on the IWM marks session, `with_reference(277.00)` and `with_premarket({...})` give targets at their new trigger plus the offsets, waypoints rebuilt against it, and `gate_targets` equal to those targets.
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_strat_levels.py -k TestPlanWaypoints -q` (expect FAIL: no `plan_waypoints`).
- [ ] **Step 3: Implement.** A fixture level in range that the owner's example does not name keeps the by-name tests as "contains" and is reported on the PR.
- [ ] **Step 4: Run again** (expect PASS).
- [ ] **Step 5: Render step, then commit:** `feat(strat): list levels as waypoints between the quarter marks`

### Task 6: What the brief prints, with the hit-rates counts

Spec: Design 7; Design 4; Decision 6; hit-rates r2 Design 5. Closes done_when[3] and done_when[9].

Carries from e0c568e40: `_mark_plan_lines`, `_leg_sale_text`, `_gap_fill_text`, `_atr_levels_line` giving None for a marks session, `_legacy_trigger_dict` carrying `mark`, `share`, `on_level`, the gap fill keys, `plan_waypoints` and `waypoint_zone_status`, and the Discord split test. r3 changes against it: (1) drop `plan_reach_history`, the `reach_history` argument, `_reach_history_record`, `REACH_HISTORY_NOT_READ`, `reach_count`, `_plan_reach`, the `reached` keys and the `reach history unavailable (...)` text; (2) the counts come from #2062's `ReachTable` handed to `format_levels_for_brief(reach=..., reach_min_sample=...)`; (3) the header line after the stop line and the percent from `min_sample`; (4) the brief keys its one read by the version being built. b0f6891fc is not carried.

**Files:**
- Modify: `lib/strat_levels.py`, `gcp/premarket_brief.py` (`_load_reach_for_brief`), `tests/lib/session_levels_helpers.py`
- Create: `tests/fixtures/plan_excursions_iwm_2026-10-23_2026-11-13.json`
- Test: `tests/lib/test_strat_levels.py` (`TestAtrMarkCopy`), `tests/gcp/test_premarket_brief.py`

**Interfaces:**
- Consumes: #2062's `ReachTable`, `load_target_reach`, `unavailable_text`, `NO_STOP_TEXT`, `REACH_UNAVAILABLE`; `build_rule_version`, `entry_rule_version`.
- Produces:
  - `_mark_plan_lines(trig: dict, plan: dict, atr_basis: Optional[str], reach, min_sample: Optional[int]) -> list`, called by `_plan_block` when `plan.get('rule') == TARGET_RULE_ATR_MARKS` and the status is ok. It imports `lib.target_reach` inside the function (that module imports `lib.strat_levels`). After the stop line: `reach.header_text()` for a `ReachTable` with `n > 0`; `unavailable_text(reach)` when `reach` is a status string; `NO_STOP_TEXT` for a side with no stop; nothing for `reach=None` or `n == 0`. Each target and waypoint line ends `, ` plus `reach.count_text(d, min_sample)` with `d = abs(cents - trigger cents) / (atr * 100)` (a zone's from its nearest member), or nothing when no count prints.
  - `gcp.premarket_brief._load_reach_for_brief` passes `entry_rule_version(build_rule_version(first))` instead of `entry_rule_version(LEVEL_RULE_VERSION)`.
  - `reach_1116(rows=None) -> ReachTable` (test helper): `load_target_reach` over the fixture through a recording `query_fn`, IWM, session 2026-11-16, the seeded `target_reach_rate` param, entry version the merge base's literal.
- Fixture: sixteen IWM rows, `rule_version` the merge base's literal, one a session from 2026-10-23 to 2026-11-13, `excursion_atr` in date order 0.1, 0.3, 0.4, 0.7, 1.1, 1.2, 1.6, 2.4, 0.05, 0.2, 0.3, 0.6, 0.9, 1.3, 1.5, 2.1.

- [ ] **Step 1: Write the failing tests** in `TestAtrMarkCopy`, IWM, bias `bearish`, `reach=reach_1116()`, `reach_min_sample=30`:
  - `test_quarters_print_the_after_text`: the CALLS and PUTS blocks equal the spec's Design 7 "After" block (r3 lines 615 to 642) character for character, among them `Reached before the stop: IWM trades 2026-10-23 to 2026-11-13 (16)`, `T1: 280.14 (25% of ATR), sell 1/4, reached 13 of 16`, `T4: 283.79 (100% of ATR, on PWH: the stronger case), sell the last 1/4, or hold to the close or the stop, reached 7 of 16` and `269.88 (PML): level beyond T4, 1.23 ATR past the trigger, reached 5 of 16`.
  - `test_local_empty_list_prints_main` (arm A) and `test_stored_level_rule_basis_prints_main`: the blocks equal `main_text_1116('IWM')`'s, with and without the table.
  - `test_three_marks`: the share reads `1/3`; the T3 line contains `sell the last 1/3, or hold to the close or the stop`.
  - `test_no_rows_prints_no_history_yet`: a table with `n == 0`: every target and waypoint line ends `no history yet`; no `0 of 0`, no `None`, no header line.
  - `test_min_sample_rows_print_a_percent`: forty rows: a line reads `reached k of 40 (p%)`, p rounded half up.
  - `test_unavailable_prints_one_line_and_no_count`: `reach=REACH_UNAVAILABLE` prints `Reached before the stop: unavailable (input_unavailable).` and no line contains `reached ` or `no history yet`.
  - `test_reach_none_prints_no_count` (Choices, item 5).
  - `test_no_skipped_and_no_atr_levels_line`: neither `Skipped, closer than` nor `ATR levels`; the `Calls (up):`, `Puts (down):` and `PMG ZONES` lines equal the base text's.
  - `test_marks_not_ok_prints_the_existing_line`: `Targets unavailable (input_unavailable): no exit plan for this side.` and no `    T1:` line.
  - done_when[9]: `test_marks_brief_counts_level_rule_rows`: a v6 build's read binds `rule_version` to the merge base's literal and, with rows only of that version, prints counts, not `no history yet`; `test_a_failed_read_raises`: a raising `query_fn` makes `load_target_reach` raise `TargetReachUnavailable`, and the brief's playbook holds the unavailable line and never `no history yet`.
  - `tests/gcp/test_premarket_brief.py`: `test_marks_brief_as_of_reads_only_earlier_rows` (`BRIEF_AS_OF=2026-11-10`: one read, bound `session_date` 2026-11-10, SQL `session_date < :session_date`, entry version the literal); `test_every_ticker_gets_a_table` (never `reach=None` from the brief); **Review Focus 4,** `test_the_longer_playbook_splits_whole` (the IWM marks playbook through `_playbook_code_fields`: bodies rejoin to the lines in order, none over the limit).
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_strat_levels.py -k TestAtrMarkCopy tests/gcp/test_premarket_brief.py -k "reach or splits or as_of" -q` (expect FAIL on every marks case).
- [ ] **Step 3: Implement.** If the fixture holds a level the owner's example does not name, the golden is the fixture's text, recorded in the test and reported line by line on the PR.
- [ ] **Step 4: Run again** (expect PASS).
- [ ] **Step 5: Render step, then commit:** `feat(strat): print the quarter targets, waypoints and reach counts`

### Task 7: Stored briefs keep their plan; `rebuild_on_marks` keeps the recorded entry

Spec: Design 6 ("Every reader keeps that entry", "Rates never mix rule versions"); Design 12 (first paragraph). Closes done_when[4]; advances done_when[8] (the function).

Carries c8142d518's tests. r3 changes against it: (1) the marks basis rebuild test renders with the same `ReachTable` both times (no reach in the basis); (2) new: `rebuild_on_marks`, `from_basis` on a rebuilt basis, and the readers that follow it; (3) the movement statement pools a marks session by version and entry version.

**Files:**
- Modify: `lib/strat_levels.py`, `lib/movement_statement.py` (`_reach_rate_sql`, `_fetch_reach_rates` and their caller), `tests/lib/session_levels_helpers.py`
- Test: `tests/gcp/test_level_basis.py`, `tests/lib/test_strat_levels.py`, `tests/lib/test_movement_statement.py`, `tests/gcp/test_premarket_playbook_resolver.py`

**Interfaces:**
- Produces:
  - `class RebuildRefused(ValueError)` with `reason: str`.
  - `rebuild_on_marks(basis: dict, marks: Sequence[float], params: Optional[LevelParams] = None) -> SessionLevels`: the basis's recorded levels, ATRs, `atr_basis`, prior close, premarket, PMG zones, ATR rungs, cleared marks and each side's recorded `trigger`, `stop`, `window`, `ladder`, `regime`, `room_pct`, `reason`, `candidates`; then `_plan_mark_targets` and `_plan_waypoints` per side with a trigger; `gate_targets` its targets; `rule_version` v6; `rebuilt_from_rule_version` the basis's own when present, else `LEVEL_RULE_MARKS_ENTRY` for a live v6 basis, else its `rule_version` when it is v2 or a level-rule version; `rebuilt_marks` the marks used. `params` is read only for keys the basis did not record. Raises `RebuildRefused` for no ATR on the basis's `atr_basis`, a side with a trigger and no stop, or a recorded version outside v2 to v6. A side with no trigger is kept as recorded. `_assemble` is never called.
  - `SessionLevels.rebuilt_from_rule_version: Optional[str] = None`, `SessionLevels.rebuilt_marks: Optional[tuple] = None`; `to_basis` records both when set; `from_basis` returns `rebuild_on_marks(basis, basis['rebuilt_marks'])` for a basis recording `rebuilt_from_rule_version`.
  - `v2_basis_off_pick() -> dict` (test helper): `d8_basis()` relabelled `feat-strat-001.v2` with its recorded calls and puts triggers moved to another candidate, so each differs to the cent from the level rule's pick on the same levels.
  - `lib/movement_statement.py`: for a marks-version session the population adds `AND COALESCE(level_basis->>'rebuilt_from_rule_version', :live_marks_entry) = :entry_rule_version`, bound in `_fetch_reach_rates` from `LEVEL_RULE_MARKS_ENTRY` and `basis_entry_rule_version` of the session row's basis.

- [ ] **Step 1: Write the failing tests:**
  - (a) `test_a_level_rule_basis_rebuilds_as_main` (three tickers x two shapes: params with neither new key, and with the marks key recorded as the quarters, never checked): `from_basis` gives `targets`, `skipped`, `target_status` and text equal to `main_1116` and `main_text_1116`.
  - (b) `test_a_marks_basis_rebuilds_from_what_it_recorded`: the IWM v6 session's `to_basis()` rebuilt with params whose marks are `[0.5, 1.0]`: the four targets, the waypoints and the text (`reach=reach_1116()` both times) are the first build's.
  - `test_marks_and_level_basis_share_trigger_and_stop`: one session, the same inputs, the quarters and the empty list: both sides' trigger and stop equal.
  - (c) `test_plan_inputs_on_a_marks_basis`: `(280.14, 281.36, 282.58, 283.79)`, `legs == 4`, `plan_available`, with a `policy_fn` that raises if called; on the level-rule basis what `<T>.main.json` recorded.
  - `test_rebuild_on_marks_keeps_the_entry`: on v2 (`v2_basis_off_pick`), v3 (`stored_1116`) and v5 (`d8_basis`) bases: trigger, stop and ATR kept to the cent; targets are `mark_prices` of them; `rebuilt_from_rule_version` v2, v3, v5; on a live v6 basis it is the merge base's literal, never v6; on a basis already rebuilt from v2 it stays v2 with the same targets, waypoints and text.
  - `test_every_reader_keeps_the_rebuilt_entry` (`_assemble` monkeypatched to raise): the `v2_basis_off_pick` rebuilt basis through `from_basis` gives the recorded triggers, stops and names on both sides and the same targets, waypoints and text as `rebuild_on_marks`; through `plan_inputs` the same trigger, stop, four prices in order and legs 4.
  - `test_rebuild_refuses` (no ATR; a side with a trigger and no stop; `rule_version` `'feat-strat-001.v1'`), and **Review Focus 2,** `test_a_side_with_no_trigger_is_kept`.
  - **Review Focus 3,** `test_derived_builds_of_a_rebuilt_basis`: `with_reference` and `with_premarket` raise nothing, keep the recorded ATR and place the marks from the new trigger; without recorded params the side is `params_unavailable` with no target.
  - `test_reach_rates_pool_by_version_and_entry` (`tests/lib/test_movement_statement.py`, the file's `_VersionedRows` case): with resolved rows of v5, of live v6, of v6 rebuilt from v5 and of v6 rebuilt from v2: a live v6 session counts the live v6 and rebuilt-from-v5 rows only; a session rebuilt from v2 counts the rebuilt-from-v2 rows only; a v5 session its own rows only.
  - `test_new_rule_mark_reads_a_marks_basis`: `_new_rule_mark` returns `cleared_above` for a v6 basis.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_level_basis.py tests/lib/test_strat_levels.py tests/gcp/test_premarket_playbook_resolver.py -k "rebuild or marks_basis or entry" -q` and, with the research stack, `python3 -m pytest tests/lib/test_movement_statement.py -q` (expect FAIL: no `rebuild_on_marks`).
- [ ] **Step 3: Implement.** Share `from_basis`'s input reading with `rebuild_on_marks` through one private helper rather than a second copy.
- [ ] **Step 4: Run again** (expect PASS), and `python3 -m pytest tests/meta/test_level_rule_version_readers.py -q` (expect PASS with no new allowed site).
- [ ] **Step 5: Render step, then commit:** `feat(strat): rebuild a stored basis on the quarters at its recorded entry`

### Task 8: The fourth target is stored and scored

Spec: Design 5; Design 11 ("Resolver"). Closes done_when[5].

Carries 67aacca2e. r3 changes against it: (1) columns: `calls_t4_price`, `puts_t4_price` (both tables), `calls_t4_hit_ts`, `puts_t4_hit_ts`, `calls_plan_t4_hit_ts`, `puts_plan_t4_hit_ts`, `puts_reanchor_t4` (`premarket_analysis`); no `plan_t4_price` (r2 added it); (2) a marks side writes its targets to `t1..t4` and no `plan_t` price (r2 wrote `plan_t1..t4` and `t1..t3`); `TARGET_COLUMN_SLOTS` goes; (3) `LegOutcome.t4_hit_ts`, `resolve_leg`, `resolve_one`'s SELECT and UPDATE and the self-heal take four; (4) `RESOLVER_VERSION` moves past #2062's.

**Files:**
- Modify: `gcp/schema.sql`, `gcp/premarket_brief.py`, `gcp/premarket_playbook_resolver.py`, `tests/gcp/test_premarket_filter_params.py`, `tests/lib/atr_levels_display_only.py` (as carried)
- Test: `tests/gcp/test_premarket_brief.py`, `tests/gcp/test_premarket_playbook_resolver.py` (`TestFourLegs`)

**Interfaces:**
- Produces: the nine `ADD COLUMN IF NOT EXISTS` (types `DOUBLE PRECISION` and `TIMESTAMPTZ`), with one comment naming r3; `structured_playbook_columns(level_map) -> dict`: every key `{side}_t1_price..{side}_t4_price` and `{side}_plan_t1_price..{side}_plan_t3_price`, values from one loop over the side's `targets` (gate) and, for a level-rule side, one over its `plan_targets`; None elsewhere; `build_persist_rows` takes its target keys from that function, on both rows; `LegOutcome.t4_hit_ts`, `PlanOutcome.t4_hit_ts`; `_PLAN_HIT_FIELDS = ('t1_hit_ts', 't2_hit_ts', 't3_hit_ts', 't4_hit_ts')`; `_PLAN_FIELDS` uses it; `resolve_leg(direction, trigger_price, stop_price, target_prices: list, bars, notional)` sets `t1..t4_hit_ts` for up to four prices; `resolve_one` reads `{side}_t4_price`, passes four and updates `{side}_t4_hit_ts` and the plan columns; the self-heal's structured inputs and UPDATE carry `{side}_t4_price`; `RESOLVER_VERSION` the next dated version with a comment naming r3.

- [ ] **Step 1: Write the failing tests:**
  - `TestFourLegs` (carried): a call, trigger 100.00, stop 99.00, targets `(100.50, 101.00, 101.50, 102.00)`, `legs=4`, cutoff 960: all four gives `'t1,t2,t3,t4'`, R 1.25, `t4_hit_ts` the bar that reached 102.00; the stop after T2 gives `'t1,t2,stop,stop'`, R -0.125; the put mirrors (trigger 100.00, stop 101.00, targets 99.50, 99.00, 98.50, 98.00); three legs leave `t4_hit_ts` None.
  - `test_resolve_leg_sets_t1_to_t4` on the same four targets, and `test_traded_exit_sells_at_the_first_quarter`: `exit_reason == 't1'` at 100.50.
  - `test_resolve_one_update_sets_every_t4_column`: the UPDATE text holds `calls_t4_hit_ts`, `puts_t4_hit_ts`, `calls_plan_t4_hit_ts`, `puts_plan_t4_hit_ts`; the SELECT reads `calls_t4_price` and `puts_t4_price`.
  - `test_self_heal_writes_four_prices`.
  - `test_structured_columns_of_a_marks_side`: IWM marks map: `calls_t1_price..calls_t4_price` 280.14 to 283.79, `puts_*` 274.64 to 270.99, every `plan_t` None; the level-rule map gives a literal dict equal to the base's output plus `calls_t4_price` and `puts_t4_price` None.
  - `test_persisted_rows_carry_t4` (canonical and history) and `test_schema_declares_the_nine_columns`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_premarket_playbook_resolver.py -k "FourLegs or t4 or first_quarter or self_heal" tests/gcp/test_premarket_brief.py -k "t4 or structured" -q` (expect FAIL: no `t4_hit_ts`; the R and exit assertions of `TestFourLegs` pass already and are recorded so).
- [ ] **Step 3: Implement.** `targets[:plan.legs]` is not changed.
- [ ] **Step 4: Run again** (expect PASS); the whole resolver file passes, every existing three-leg case unchanged; re-pin `SCHEMA_SHA256`.
- [ ] **Step 5: Render step, then commit:** `feat(strat): store and score four targets in the t1 to t4 columns`

### Task 9: Alerts, the movement statement and the explanations read the quarters

Spec: Design 11 ("Signal monitor", "Movement statement", "Brief explanations"); Decision 12. Closes done_when[6].

New in r3, but for one test carried from b0f6891fc: `test_endpoint_serves_a_marks_session_of_2026_11_16_iwm` (`tests/api/test_movement_statement_router.py`, with its `extra_policy` argument in `tests/gcp/run_brief_2026_11_16.py`), changed: no swap rows (the seed builds v6), four target slots, and the population by version and entry version of Task 7.

**Files:**
- Modify: `gcp/signal_monitor.py` (`_reanchor_put_leg`, `_persist_put_reanchor`), `lib/movement_statement.py`, `platform/api/schemas.py` (`ReachRate.slot`'s comment), `gcp/brief_explanations.py`, `tests/gcp/run_brief_2026_11_16.py`
- Create: `tests/gcp/test_brief_explanations.py`
- Test: `tests/gcp/test_signal_monitor.py`, `tests/gcp/test_signal_monitor_level_state.py`, `tests/lib/test_movement_statement.py`, `tests/api/test_movement_statement_router.py`

**Interfaces:**
- Produces: the re-anchor's `out` gains `'t4'` from `put_side.gate_targets` (the marks from the re-anchored trigger and the recorded ATR); its UPDATE sets `puts_reanchor_t4 = :t4`; the comment "alert targets keep their pre-spacing meaning" goes. `LegStateTracker` code is unchanged (its T1 is the row's `calls_t1_price` or `puts_t1_price`). `reach_slots(n_targets: int) -> tuple`: `('trigger',)` plus `t1..t{n}`; `_reach_rate_sql(side, slots)`, `_fetch_tracked_levels` reading `t1..t4`, a marks-version row's slots `reach_slots(4)`, a level-rule row's `reach_slots(3)`. `playbook_prompt(target_count: int) -> str` replaces `_PLAYBOOK_PROMPT`'s `T1/T2/T3` with `T1 to T{n}` (n the larger side's count of non-None `{side}_t{k}_price` in the brief's `data`); `explain_playbook` passes it.

- [ ] **Step 1: Write the failing tests:**
  - `test_signal_monitor_level_state.py`: `test_t1_is_the_first_quarter`: a tracker from the IWM marks row's `calls_t1_price` turns `post_t1` on a bar touching 280.14 and not on one touching 279.17 (PDH, the first level past the trigger).
  - `test_signal_monitor.py`: `test_reanchor_writes_four_quarters`: on a v6 session re-anchored at an open, `t1..t4` each equal the re-anchored trigger minus `price_cents(mark * ATR)` with the recorded ATR, and the UPDATE binds `t4`.
  - `test_movement_statement.py`: `test_reach_slots_follow_the_target_count` (`reach_slots(4)`, `reach_slots(3)`) and `test_a_marks_row_tracks_four_targets` (`_fetch_tracked_levels` on a v6 row gives slots `t1..t4` at the quarters).
  - the carried endpoint test, changed as above.
  - `tests/gcp/test_brief_explanations.py`: `test_prompt_names_four_targets` (four-target data: `T1 to T4` in the prompt, `T1/T2/T3` absent) and `test_prompt_names_three_targets` (`T1 to T3`).
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_signal_monitor.py tests/gcp/test_signal_monitor_level_state.py tests/gcp/test_brief_explanations.py tests/api/test_movement_statement_router.py -k "quarter or reanchor or prompt or marks" -q` and the movement statement file with the research stack (expect FAIL).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run again** (expect PASS), then both signal monitor files whole (every fire decision unchanged).
- [ ] **Step 5: Render step, then commit:** `feat(strat): alerts, rates and the playbook prompt read the quarter targets`

### Task 10: Thirds leave the analysis code and the docs

Spec: Design 11 ("Not thirds, and kept"); Design 5 (the "Other readers" row); Design 12 ("Readers of the stored text"). Closes done_when[7].

New in r3.

**Files:**
- Modify: `scripts/analysis/honest_scoring_experiment.py` (`thirds_rule`, its call and its `a third at each` report lines, its docstring's mention), `scripts/validation/validate_brief_accuracy.py` (`fetch_brief`, the scoring), `gcp/queries/nan_triage.sql` (both tables' sums gain `calls_t4_price` and `puts_t4_price`), `ERD.drawio` (the `premarket_analysis` outcome row reads `t1 · t2 · t3 · t4`, plus one line: `plan_t1..t3_price retired by the quarter targets (Design 13); a marks row writes NULL`)
- On its own branch `docs/data-dictionary-quarter-targets` (Where the spec cannot be met, item 2): `docs/product/infrastructure/05-h-DATA_DICTIONARY.md`, the nine columns in the two table sections, `plan_t1..t3_price` marked retired by Design 13, and a `premarket_targets_archive` section
- Test: `tests/scripts/test_validate_brief_accuracy.py`, `tests/scripts/test_honest_scoring_experiment.py` (create if the base has none)

**Interfaces:**
- Produces: `validate_brief_accuracy.fetch_brief` selects `{side}_t1_price..{side}_t4_price` and `{side}_t1_hit_ts..{side}_t4_hit_ts`; the scorecard scores T1 to T4 from those columns (T4 absent when NULL); `parse_playbook` is no longer used for targets.

- [ ] **Step 1: Write the failing tests:** `test_scores_four_targets_from_columns` (a row with four prices and hit times scores four, and a playbook text naming other prices changes nothing); `test_a_level_row_scores_three`; `test_no_thirds_rule` (by `ast`: no function `thirds_rule`, no string containing `a third at each`); `test_nan_triage_lists_the_t4_columns` (text check of both lines).
- [ ] **Step 2: Run:** `python3 -m pytest tests/scripts/test_validate_brief_accuracy.py tests/scripts/test_honest_scoring_experiment.py -q` (expect FAIL).
- [ ] **Step 3: Implement**, and edit `ERD.drawio`.
- [ ] **Step 4: Run again** (expect PASS).
- [ ] **Step 5: Render step, then commit:** `refactor(strat): retire the thirds rule from the analysis and validation scripts`
- [ ] **Step 6: The data dictionary.** From a fresh `origin/main`, branch `docs/data-dictionary-quarter-targets`: the 05-h edit, its text saying the columns arrive with this implementation PR (named by number); `python3 scripts/gate/spec_gate.py --commit` and `--pr origin/main` pass; the docs audit reports nothing new. Commit `docs(infra): describe the quarter target columns and the archive table`. Push and open that PR only when this PR is about to be marked ready; it merges before that, and done_when[7]'s tick cites it.

### Task 11: The DDL on a real Postgres, and the history rebuild tooling

Spec: Design 12; Design 5 ("The schema change applies itself"); Decision 13; done_when "History rebuild tooling". Closes done_when[8] (with Tasks 7 and 14); supports done_when[0] and [5].

Carries 9469a4d6c as `tests/integration/test_atr_marks_schema_pg.py`. r3 changes against it: one seeded row (the quarters) instead of two; the nine columns instead of eight; the archive table; no swap-row test, no reach-history query test, no `plan_mfe_atr`. The rebuild tool is new.

**Files:**
- Modify: `gcp/schema.sql` (`premarket_targets_archive`), `tests/meta/test_production_writers.py` (only if the tool trips a writer list; the reason names this spec)
- Create: `scripts/maintenance/rebuild_quarter_history.py`, `gcp/queries/quarter_history_count.sql`, `tests/scripts/test_rebuild_quarter_history.py`, `tests/integration/test_rebuild_quarter_history_pg.py`
- Modify (carried): `tests/integration/test_atr_marks_schema_pg.py`

**Interfaces:**
- Consumes: `rebuild_on_marks`, `RebuildRefused`, `mark_prices`, `basis_entry_rule_version`, `load_level_params`, `resolve_one`, `derive_level_map_from_daily`, `_plan_block`, `stored_text_1116`.
- Produces:
  - `premarket_targets_archive (archive_id BIGSERIAL PRIMARY KEY, run_id UUID NOT NULL, source_table VARCHAR(40) NOT NULL CHECK (source_table IN ('premarket_analysis', 'premarket_analysis_history', 'plan_excursions', 'level_param_policy')), source_key JSONB NOT NULL, ticker VARCHAR(10), date DATE, run_kind VARCHAR(16), archived_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), restored_at TIMESTAMPTZ, old_row JSONB NOT NULL)`, `CREATE TABLE IF NOT EXISTS`, an index on `(source_table, source_key)`.
  - The tool: `python3 -m scripts.maintenance.rebuild_quarter_history MODE [--tickers SPY,QQQ,IWM] [--run-id UUID] [--commit]`, modes `count`, `archive`, `rebuild`, `resolve`, `verify`, `restore`. Writing modes roll back unless `--commit`; every mode logs `ticker=%s table=%s processed=%d/%d`. The marks come from the policy row in force today, never from an argument.
  - `count(engine) -> dict` runs `gcp/queries/quarter_history_count.sql`, one statement with a `section` column: rows by table, `run_kind`, recorded `rule_version` and whether a basis exists, with earliest and latest date and average `pg_column_size`; `plan_excursions` rows by `rule_version`; per ticker, sessions with and without 1-minute bars in `market_data_intraday`; rows whose basis recorded no parameters.
  - `archive(engine, run_id, tickers) -> dict`: one `INSERT ... SELECT to_jsonb(t)` per table and ticker, plus the `plan_excursions` rows of the same tickers and dates; refuses (writes nothing) when any key has an unrestored archive; stops unless its counts equal `count`'s per table.
  - `replace_plan_blocks(stored_text: str, sl: SessionLevels) -> str`: each side with a trigger keeps its stored header line and gets the body `_plan_block` renders for the rebuilt side (`reach=None`); the NEXT LEVELS `ATR levels` line goes; every other line byte-equal; raises when a side's header is not found exactly once.
  - `rebuild(engine, run_id, tickers) -> dict`: one read and one `UPDATE ... FROM (VALUES ...)` per table and ticker, one transaction each; writes `t1..t4_price`, NULL `plan_t1..t3_price`, `level_basis` (`rebuild_on_marks(...).to_basis()`), `playbook` (`replace_plan_blocks`), NULL `llm_playbook`, and on `premarket_analysis` NULL every resolver outcome column and `outcome_resolved_at`, and `puts_reanchor_t1..t4` from `puts_reanchor_trigger` and the row's ATR by `mark_prices` where a re-anchor was recorded; refuses (lists, writes nothing for) a row whose trigger or stop would change by a cent, or that raises `RebuildRefused`; rebuilds a no-basis row in its columns only (Choices, item 7).
  - `resolve(engine, tickers) -> dict`: `resolve_one(..., force=True)` over every rebuilt `premarket_analysis` row, per ticker; a `no_bars` session keeps its NULL outcomes.
  - `verify(engine, run_id) -> dict` (read only): zero rows with a basis whose `rule_version` is not v6; zero non-NULL `plan_t1..t3_price`; zero triggers or stops that differ from the archive; archived equals rebuilt plus refused, each refused row listed; resolved counts by status with the no-bars rows equal to `count`'s gap; zero `playbook` texts containing `sell 1/3` or `the last 1/3`; zero non-NULL `llm_playbook` on a rebuilt row; no-basis rows on their own line.
  - `restore(engine, run_id) -> dict`: every archived row back whole by its key, the `plan_excursions` rows `resolve` added for those keys deleted and the archived ones written back, `restored_at` stamped.

- [ ] **Step 1: Write the failing tests.** Hermetic, `tests/scripts/test_rebuild_quarter_history.py`, with a recording engine: `test_archive_is_one_statement_a_table_and_ticker`; `test_rebuild_is_one_read_and_one_update_a_table_and_ticker` (N rows of K tickers: exactly 2K statements a table, CLAUDE.md rule 0); `test_writing_modes_roll_back_without_commit`; `test_replace_plan_blocks_on_the_stored_iwm_text` (`stored_text_1116('IWM')` with the rebuilt IWM session: the CALLS and PUTS blocks equal Design 7's After blocks without the count line and count suffixes, no `ATR levels` line, every other line byte-equal); `test_replace_plan_blocks_refuses_a_missing_or_doubled_header`; `test_marks_come_from_the_policy` (no CLI argument names a mark). Postgres, `tests/integration/test_rebuild_quarter_history_pg.py` (fixtures of `tests/integration/conftest.py`), fixture rows in both tables of v2, v3 and v5 bases, one v6 row built live, one row already rebuilt from v2, one `premarket_analysis` row with no basis, one with a put re-anchor, one session with no 1-minute bars, bars for the rest, and `plan_excursions` rows for the fixture dates; a snapshot of both tables and `plan_excursions` taken first:
  - `test_count`: rows by version and the no-bars session.
  - `test_archive_stores_whole_rows_and_excursions`, `test_archive_stops_on_a_count_mismatch`, **Review Focus 1,** `test_a_second_archive_refuses`.
  - `test_rebuild_writes_the_quarters`: four targets, the re-rendered playbook, `puts_reanchor_t1..t4`, NULL outcomes and `llm_playbook`; refuses a row whose trigger would change; the live v6 row and the already rebuilt row keep `basis_entry_rule_version` v5 and v2 as read before; a second rebuild over every row changes no column.
  - `test_resolve_reads_only_the_bars_table`: the no-bars row keeps NULL outcomes; the others' four-leg outcomes and `plan_excursions` rows are written under their entry versions.
  - `test_verify_is_clean_and_lists_the_refused`.
  - `test_restore_returns_the_snapshot`: both tables and `plan_excursions` equal the snapshot row for row and column for column; **Review Focus 5,** `test_a_failed_ticker_rolls_back_alone` (a fault injected on the second ticker), then restore equals the snapshot.
  - carried and changed: `test_the_quarters_row_is_seeded`, `test_the_nine_columns_exist_and_are_nullable`, `test_the_archive_table_exists`, `test_the_schema_applies_twice`, `test_a_past_session_loads_the_quarters` (`load_level_params` on 2016-03-01 through the real engine), `test_resolve_one_writes_the_t4_columns`.
- [ ] **Step 2: Run** hermetic `python3 -m pytest tests/scripts/test_rebuild_quarter_history.py -q`; Postgres as CI starts it: `docker run -d -e POSTGRES_USER=trading_user -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=trading -p 5432:5432 pgvector/pgvector:pg15`, `psql ... -v ON_ERROR_STOP=1 -f gcp/schema.sql`, then `DB_HOST=localhost DB_PORT=5432 DB_USER=trading_user DB_PASS=testpass DB_NAME=trading python3 -m pytest tests/integration/test_atr_marks_schema_pg.py tests/integration/test_rebuild_quarter_history_pg.py -q` (expect FAIL: no module, no columns). Record the red of the column tests on a second container from the base's `gcp/schema.sql`.
- [ ] **Step 3: Implement.** Then `python3 -m pytest tests/meta -q`.
- [ ] **Step 4: Run again** (expect PASS), timing each mode on the fixture; paste the timings.
- [ ] **Step 5: Render step, then commit:** `feat(strat): add the quarter history rebuild tool and its archive`

### Task 12: No numbers, no names, and nothing else moved

Spec: done_when "No numbers and no names", "Unchanged". Closes done_when[10] and done_when[11].

Carries a8603c7a7. r3 changes against it: the pins are Task 1 Step 3's merge-base counts (`quarter` 6 if #2062 landed as at 03aeefe43); the unchanged list is r3's.

**Files:**
- Test: `tests/lib/test_level_params_structure.py`, `tests/lib/test_level_params_copy.py` (added assertions only)

- [ ] **Step 1: Add the assertions:** in `test_the_walk_reaches_the_rules_it_must_cover`, `{"_plan_mark_targets", "_plan_waypoints"} <= reach`; in `tests/lib/test_level_params_copy.py`, `MERGE_BASE_COUNTS` (the six numbers, with a comment naming the merge base's sha and each hit's line) and `test_no_new_mark_share_or_quarter_text`, parametrised over the six strings, over every `str` `ast.Constant` of `lib/strat_levels.py` (the file's `_strings` walker). Docstrings name the marks and shares by where they are read from, never by their values.
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_level_params_structure.py tests/lib/test_level_params_copy.py -q` (expect passed, `ALLOWED_VALUES` unchanged). Record the red: a literal `0.25` in `_plan_mark_targets` fails `test_no_numbers_on_the_level_and_plan_path[lib/strat_levels.py]`; `'sell 1/4'` in `lib/strat_levels.py` fails `[1/4]`; a docstring "a quarter at each mark" fails `[quarter]`. Revert each.
- [ ] **Step 3: Run the unchanged pins,** each file unmodified but for edits this plan names: `python3 -m pytest tests/lib/test_strat_levels.py -k "TestTargetSpacing or TestExitPlanCopy or TestAtrRungs or TestAtrRungsDisplayOnly or TestAtrLevelsCopy or TestPlanGapEdges or TestNextLevelsLadder or TestSessionPicks" tests/lib/test_session_levels_rules.py tests/lib/test_movement_statement_level_basis.py tests/gcp/test_signal_monitor_level_state.py tests/gcp/test_signal_monitor_level_refresh.py tests/gcp/test_premarket_playbook_resolver.py tests/gcp/test_level_params_consumers.py tests/gcp/test_premarket_brief_late_slot.py tests/gcp/test_brief_channel_routing.py tests/api/test_movement_statement_exit_plan.py -q` on the merge base and on the head (expect passed on both; a class name the base lacks is replaced by the base's and noted).
- [ ] **Step 4: Run:** `make test` (expect no failure the base does not have); `git diff <merge base> --stat -- tests/ | cat`, and list in the PR body each existing test file with removed lines and why (expected: `tests/lib/level_params_fixtures.py`, `tests/meta/test_level_rule_version_readers.py`, `tests/gcp/test_premarket_filter_params.py`, and each Task 3 fixture call).
- [ ] **Step 5: Commit:** `test(strat): reach the mark walk and waypoints from the no-numbers walk`

### Task 13: The Experiment's driver, committed and tested

Spec: Experiment ("Arms", "Method", "Arm A is checked twice", "Reported, per arm"); CLAUDE.md 3.6. Advances done_when[12].

Carries 66826a4d6 and 79342753c. r3 changes against them: (1) `arm_policy_sql`: A inserts `plan_target_marks_atr` `{"marks": []}` effective 2015-01-03 (the seed is now Q); Q inserts nothing; Q3 inserts `{"marks": [0.25, 0.5, 0.75]}` effective 2015-01-03; no arm inserts `exit_legs`; (2) `mfe_atr` goes: `score` computes #2062's `plan_excursion(direction, plan, bars, basis_atr(basis)).excursion_atr` on the bars it already holds and writes it as `excursion_atr`; measures 5 to 8 read it; `plan_excursion` and `basis_atr` are imported inside `score`, since 97190ef41 has neither; (3) `score` asserts every Q and Q3 basis records v6 with `legs` equal to its number of marks, and every A basis the merge base's `LEVEL_RULE_VERSION`.

**Files:**
- Create (carried): `scripts/analysis/atr_marks_experiment.py`, `tests/scripts/test_atr_marks_experiment.py`, `tests/fixtures/atr_marks_spike_2026-11-16/report_v1_side.txt`, `report_followup.txt`
- Modify (carried): `tests/meta/test_production_writers.py`, `tests/gcp/test_export_intraday_bars.py`

**Interfaces:**
- As carried: `ARMS = {'A': ((), 3), 'Q': ((0.25, 0.5, 0.75, 1.0), 4), 'Q3': ((0.25, 0.5, 0.75), 3)}` (labels and expected legs, read by `score`'s assertion and `report`, never applied to a plan); `LEFT_OUT = {('SPY', '2025-04-09'), ('IWM', '2026-06-26')}`; `require_local_db()`; `pick_trade(calls, puts)`; subcommands `load`, `placeholder`, `replay`, `score`, `report`, `baseline`, `compare`; `trigger_changed(base_days, head_days) -> dict`; `report(csv) -> str` with the eleven measures and the spike's figures beside them; the baseline mode reads no `excursion_atr`, `t4_hit_ts` or rule version, opens no database but `DB_NAME`'s, prints the worktree's HEAD sha and the three module paths, and raises if one is outside the working directory.

- [ ] **Step 1: Write the failing tests:** the carried ones, with `test_arm_policy_sql` (A the empty list, Q None, Q3 three marks, none naming `exit_legs`), `test_reach_share_uses_excursion_atr` (excursions 0.1, 0.3, 0.5, 0.8, 1.2: marks 0.25, 0.5, 0.75, 1.0 give 4, 3, 2 and 1 of 5), `test_baseline_imports_only_what_97190ef41_has` (the literal set without `plan_excursion` and `basis_atr`), `test_baseline_reads_no_new_field` (adds `excursion_atr`), `test_score_asserts_the_arm_versions` (a Q basis recording v5 raises), and `test_the_driver_walks_no_bars_and_replaces_no_plan`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/scripts/test_atr_marks_experiment.py -q` (expect FAIL on the changed cases); implement; run again (expect PASS); `python3 -m pytest tests/meta/test_production_writers.py -q` (expect PASS).
- [ ] **Step 3: Render step, then commit:** `feat(strat): run the quarter marks experiment on the seeded policy`

### Task 14: The Experiment, through the production paths, into local databases

Spec: Experiment; done_when "Experiment through the production paths"; Design 12 ("Capacity"). Closes done_when[12] when both arm A checks hold; supplies done_when[8]'s production count and wall-clock. Nothing here writes to production.

- [ ] **Step 1: The inputs. Ask the owner once before running** (read only, no `--commit`): the spike's two statements through `./scripts/db_query_cr.sh -q "SELECT d.*, d.pre_filter_params::text AS pfp_text FROM market_data_daily d WHERE ticker IN ('SPY','QQQ','IWM') ORDER BY ticker, date; SELECT c.* FROM ticker_calibration c WHERE ticker IN ('SPY','QQQ','IWM') ORDER BY 1"`, saved from `result_001.csv` and `result_002.csv`; the bars with `gsutil -m cp -r gs://<GCS_BUCKET>/intraday-bars/v1/1min/{SPY,QQQ,IWM} <dir>` (a missing month stops the task; no vendor refetch); `./scripts/db_query_cr.sh -f gcp/queries/quarter_history_count.sql` (count, read from production); `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud run jobs describe premarket-playbook-resolver --region=us-east1 --format='value(spec.template.spec.template.spec.timeoutSeconds)'`. Record each execution id and file sha256.
- [ ] **Step 2: The template and the three arms.** Postgres 15 as CI starts it; the PR head's `gcp/schema.sql` into `arm_template`; then with `DB_HOST=127.0.0.1 CLOUD_SQL_CONNECTION_NAME=local-experiment-not-cloud BRIEF_LLM_DISABLE=1 BRIEF_AMC_REACTIONS=0` and `DISCORD_WEBHOOK_URL`, the model keys and `CLOUDSDK_AUTH_ACCESS_TOKEN` unset:

```bash
python3 -m scripts.analysis.atr_marks_experiment load <export dir> <bars dir>
python3 -m gcp.calibrate_level_params --history 2022-01-03 2026-11-10 --tickers SPY,QQQ,IWM
python3 -m scripts.analysis.atr_marks_experiment placeholder 2022-01-03 2026-11-10
python3 -m gcp.fetchers.fetch_market_data --recompute-premarket --from 2022-01-03 --to 2026-11-10 --commit --report-dir <dir>
psql -c "CREATE DATABASE arm_a TEMPLATE arm_template" -c "CREATE DATABASE arm_q TEMPLATE arm_template" -c "CREATE DATABASE arm_q3 TEMPLATE arm_template"
python3 -m scripts.analysis.atr_marks_experiment replay A 2022-01-03 2026-11-10    # DB_NAME=arm_a, after arm_policy_sql('A')
python3 -m scripts.analysis.atr_marks_experiment replay Q 2022-01-03 2026-11-10    # DB_NAME=arm_q, the seed
python3 -m scripts.analysis.atr_marks_experiment replay Q3 2022-01-03 2026-11-10   # DB_NAME=arm_q3, after arm_policy_sql('Q3')
```

  Check each tool's flags against `--help` on the base first. Expect: calibration exits 0 for three tickers; the recompute logs `candidates=3657` with `refused=0`; each replay ends with no failure and 3,657 `premarket_analysis` rows. State the two limits of the r2 plan's Task 14 (the placeholder sentinel `pre_vwap = -1`, checked gone after the recompute; the 04:00 to 09:30 ET premarket window against the live 08:20 refresh) in the PR body as limits.
- [ ] **Step 3: Score the head:** `python3 -m scripts.analysis.atr_marks_experiment score 2022-01-03 2026-11-10 --out atr_marks_arms.csv --days-out arm_a_head_days.csv`. No figure of any arm is read until Step 4 (a) holds.
- [ ] **Step 4: Arm A is checked twice; both are required. No arm, the head's A included, is read if (a) fails.**
  - (a) Harness check, the committed driver run as a file against 97190ef41's modules, into a database built and prepared by that commit's tools from the same inputs:

```bash
git worktree add --detach <wt> 97190ef41
git -C <wt> rev-parse HEAD     # expect 97190ef4120085207f988a7ee942317e2a1b5fd3
psql -c "CREATE DATABASE arm_base" && psql -d arm_base -v ON_ERROR_STOP=1 -f <wt>/gcp/schema.sql
cd <wt> && export PYTHONPATH=<wt> DB_NAME=arm_base
python3 <head>/scripts/analysis/atr_marks_experiment.py load <export dir> <bars dir>
python3 -m gcp.calibrate_level_params --history 2022-01-03 2026-11-10 --tickers SPY,QQQ,IWM
python3 <head>/scripts/analysis/atr_marks_experiment.py placeholder 2022-01-03 2026-11-10
python3 -m gcp.fetchers.fetch_market_data --recompute-premarket --from 2022-01-03 --to 2026-11-10 --commit --report-dir <dir>
python3 <head>/scripts/analysis/atr_marks_experiment.py replay A 2022-01-03 2026-11-10
python3 <head>/scripts/analysis/atr_marks_experiment.py baseline 2022-01-03 2026-11-10 --days-out arm_a_base_days.csv
```

    **Pass:** within 0.1 R of +176.8 over 3,463 trades. Paste the total, the trade count, the per-ticker totals beside +64.2, +114.0 and -1.4, the worktree's HEAD sha and the three module paths. If it fails, stop: post those figures and nothing of any arm; a driver cause is fixed there (tests first) and (a) rerun; an input cause gets a fresh Step 1 export on the owner's yes; with no cause found, done_when[12] stays unticked and the PR stays a draft.
  - (b) Arm A on the head, reported beside the spike's +176.75 R over 3,463 trades, then `python3 -m scripts.analysis.atr_marks_experiment compare arm_a_base_days.csv arm_a_head_days.csv`: trigger-changed ticker-days, arm A's R and trade count in each run on them and on the rest, and every ticker-day of the rest whose R differs, with its cause, attributed to the brief build (#2010) and the prior-close rule.
  - Then `python3 -m scripts.analysis.atr_marks_experiment report atr_marks_arms.csv`; Q and Q3 are read against the head's A only.
- [ ] **Step 5: The PR body shows** (a) and (b), then per arm the eleven measures with the spike's figures beside them, never in their place (A +176.75 over 3,463; Q +152.49; Q3 +129.72; Q minus A -24.3, range -71.8 to +21.8; Q3 minus A -47.0, range -109.1 to +12.4; Q's T1 to T4 shares 52.3%, 27.1%, 12.8%, 6.2%), every difference explained, the measures the spike did not produce (5, 6, 7, 8 at `level_cluster_atr`, 9's average win and loss), the driver's and the csv's sha256, the commands and the limits. An arm whose 90% range against A lies wholly below zero overall, or for two of three tickers, is reported as failing, and the PR does not merge with the quarter seed without the owner's decision recorded on the PR.
- [ ] **Step 6: The rebuild's wall-clock on real counts** (Design 12 "Capacity"): `psql -c "CREATE DATABASE rebuild_probe TEMPLATE arm_a"`, delete arm A's local marks row there, then with `DB_NAME=rebuild_probe` run `count`, `archive --commit`, `rebuild --commit`, `resolve --commit`, `verify` and `restore --commit` for IWM, timing each. Paste the timings, Step 1's production count and job timeout, the archive size estimate (count's rows times average row size), and the timeout the FEAT-DEPLOY-001 entry needs (at least 4x the measured `resolve` a ticker).

### Task 15: Close: product record, site note and the gate

Spec: "Source identity and close-out"; done_when "Source identity" and the last item. Closes done_when[13] and done_when[14] but for the owner's steps. Once the site-note steps start, no file under `gcp/`, `lib/`, `scripts/` or `tests/` changes without redoing them.

r3 changes against feca59809: a new `source_identity_sha256` and new prose; the earlier prose is kept after ` Earlier: `.

- [ ] Push `git push -u origin feature/feat-strat-001-atr-quarters-r3` and open a **draft** PR titled `FEAT-STRAT-001: ...`. **Never enable auto-merge.** Body: the spec's and this plan's paths; the 15 done_when items as `- [ ]` lines; `Red then green`; the Capacity section; Task 1's precondition outputs and line table; `LEVEL_RULE_VERSION` and `PICK_RULE_VERSIONS` read on the merge base and the marks version `feat-strat-001.v6`; the carried r2 build commits and what changed in each; Task 14's results; the choices and the spec points of this plan; and "Merging applies gcp/schema.sql to production through apply-schema-on-change, and the seeded row puts the quarters in every brief the new image builds; merge only on the owner's recorded yes."
- [ ] Set `pr:` in this plan to the PR's number.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, `### FEAT-STRAT-001` (`:233` on d35d9ce23): Status and Last reviewed (implementation under review, not deployed; the merge changes the live plan). `docs/product/12-PR-ISSUE-TRACEABILITY.md`, `### FEAT-STRAT-001` (`:547`): this PR in the lineage, naming spec PRs #2013, #2019 and #2053. Commit with the plan: `docs(product): record the quarter targets under FEAT-STRAT-001`.
- [ ] Site note, step 1: clean tree, `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`; copy `source_identity_sha256`.
- [ ] Site note, step 2: the `| FEAT-STRAT-001 | DASHBOARD-01 |` row of `docs/product/03-SITE-TRACEABILITY.md` and no other byte: the new hash, this change's prose (backend source and local tests only: the plan block prints four targets at 25, 50, 75 and 100 percent of ATR with waypoints and reach counts; the `t1..t4` columns, resolver, monitor and movement statement read them; the rebuild tool is tested locally and not run; tests named), then ` Earlier: ` and the earlier prose. Commit `docs(site): note the quarter targets on DASHBOARD-01`.
- [ ] Site note, steps 3 and 4: `produce` again, commit `docs(site): regenerate the source snapshot`; `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 16777216 --max-entries 20000` (expect exit 0). If `origin/main` moved, merge it in (never a rebase), re-render and redo the four steps.
- [ ] Render step once more and its two tests (expect pass).
- [ ] Docs audit, branch against main: `LC_ALL=C python3 scripts/maintenance/docs_audit.py | grep -E '^\s*\[P' | sed -E 's/:[0-9]+//g; s/^\s+//' | sort` on the branch and on a detached `origin/main` worktree; `comm -23 branch main` is empty.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` (expect exit 0).
- [ ] Task 10 Step 6's docs PR is merged; push; tick each done_when box with its evidence (test names, execution ids, sha256 prefixes); done_when[12] only as Task 14 Step 4 allows; only then mark the PR ready. Gate files are not touched, so no red-team pass is owed.
- [ ] **Ask the owner once before merging:** "Merging applies the quarter marks row, nine nullable columns and premarket_targets_archive to production through apply-schema-on-change, and from the deploy every new brief, alert and outcome is on the quarters. The Experiment is in the body; the conviction change (Decision 7) and the insight and site target changes (Decision 8) are <state>. Yes?" Merge only on that yes, recorded on the PR.

## Close-out (not tasks; the owner's steps, each yes recorded on the PR)

From the spec's "Source identity and close-out", Designs 11 and 12, and Decisions 7, 8, 11 and 13.

1. **The merge**, on the owner's yes: confirm by one read that the marks row, the nine columns and `premarket_targets_archive` exist.
2. **Deploy, readers first** (Design 11): the resolver, the signal monitor, the API and the insight pipeline, then the brief. Confirm by a dry run of five stored sessions with `BRIEF_NO_PERSIST=true` (Decision 11, each a spend on its own yes), then on the next live brief, that each side prints four targets at the marks with counts, records v6, and the monitor's T1 state reads the 25 percent mark.
3. **The rebuild job's deploy entry** for `scripts.maintenance.rebuild_quarter_history`, through its FEAT-DEPLOY-001 change, with Task 14 Step 6's timeout.
4. **Design 12, each writing mode on its own yes**, in order: `count`, `archive --commit`, `rebuild --commit`, `resolve --commit` per ticker, `verify`; `restore --commit` only if the owner asks. Then the alerts replay, `scripts/replay_signal_monitor.py` over 2022-01-03 to the deploy date on the rebuilt rows with `--persist` (`run_kind` `replay`, one `replay_id`), on its own yes; its fires by `level_state` beside the live rows', posted on the PR. Live `signal_alerts` rows are not rewritten.
5. **Design 13**, a spec of its own once `verify` reads clean and every refused row is settled; its PR merges on the owner's explicit yes to the drop.
6. On a `docs/` branch after the merge: this plan's `status: done`, the DASHBOARD-01 close-out; the three other approved FEAT-STRAT-001 specs that describe the level rule are updated after the Experiment and the implementation, as the owner said (spec Conflicts, item 1).
