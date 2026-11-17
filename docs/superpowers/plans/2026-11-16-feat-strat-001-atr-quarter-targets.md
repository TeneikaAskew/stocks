---
feat_id: FEAT-STRAT-001
spec: docs/superpowers/specs/2026-11-16-feat-strat-001-atr-quarter-targets-r2.md
branch: feature/feat-strat-001-atr-quarter-targets
pr: null
status: ready
---

# The exit plan sells a quarter at 25, 50, 75 and 100 percent of ATR from the entry, and the levels are waypoints: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the order of the spec's frontmatter, [0] to [11]. The map below names each.

**Goal:** Behind two policy rows seeded to reproduce today's plan, a side built under a non-empty marks list takes its targets at the entry trigger plus or minus mark x ATR, prints the session's levels between those targets as waypoints with reach counts, records a new rule version, stores a fourth target and one reach number a side, and the Experiment is run again on the marks builder itself.

**Architecture:** One builder, `lib.strat_levels.build_session_levels`. `_pick_side` asks a new helper, `plan_target_rule(version)`, which rule picks the targets and calls the level walk (`_plan_targets`, unchanged) or a new mark walk (`_plan_mark_targets`) followed by a waypoint builder (`_plan_waypoints`). A fresh build takes its version from the marks row in force; a stored basis rebuilds under the version and the values it recorded. The brief reads the reach history in one query and hands it to the builder as an input the basis records. `resolve_plan` gains two outputs, `t4_hit_ts` and `mfe_atr`. No target changes until later-dated policy rows exist, and those are the owner's.

**Tech Stack:** Python, pandas, numpy, SQLAlchemy `text()` through `gcp.database`, pytest (`monkeypatch`, the SQLite `ParamsDb` of `tests/lib/level_params_fixtures.py`), Postgres 15 (`pgvector/pgvector:pg15`) for the integration job and for the local copy of the Experiment.

**Spec:** docs/superpowers/specs/2026-11-16-feat-strat-001-atr-quarter-targets-r2.md (r2: approved, PR #2019, on `origin/main` f8f6c6996). It supersedes `docs/superpowers/specs/2026-11-16-feat-strat-001-atr-quarter-targets.md` (r1: approved in PR #2013, now `status: superseded`), against which this plan was first written; r1 in turn superseded the three-targets spec. r2 carries r1 word for word except two done_when items, the word 'quarter' ([7]) and arm A's pin ([9]), the Experiment's Method paragraph that matches the second, and one Authority paragraph (r2, "What changed from r1"). Its code references are r1's, to `main` 97190ef4; `git diff --stat 97190ef4 1cb36eace -- lib gcp tests scripts platform` shows only the verifier ceiling (`scripts/maintenance/doc_source_snapshot.py`, `tests/scripts/test_doc_source_snapshot.py`), run 2026-11-16, and `git diff --stat 1cb36eace f8f6c6996 -- lib gcp tests scripts platform` is empty, run 2026-11-17 after merging `origin/main` into this branch.

## Order and bases

This plan is written on `origin/main` 1cb36eace and built later, after two other changes are on main. Task 1 is the check that they are.

1. **The brief build**, PR #2010, branch `origin/feature/feat-playbook-001-brief-says-what-the-data-says`, head 8cd5e6859 when this plan was written (merge base with main 133717b1a) and still moving. Code this plan touches that main does not have yet, read at 8cd5e6859:
   - `lib/strat_levels.py:1519-1529`: `LEVEL_RULE_V2`, `LEVEL_RULE_V3`, `LEVEL_RULE_VERSION = 'feat-strat-001.v4'`, `PICK_RULE_VERSIONS = (LEVEL_RULE_V3, LEVEL_RULE_VERSION)`, `is_current_pick_rule(version) -> bool`.
   - its four readers: `SessionLevels.from_basis` (`lib/strat_levels.py:1982-1983`), `_assemble` (`:2448-2449`), `plan_inputs` (`gcp/premarket_playbook_resolver.py:611`), `_new_rule_mark` (`lib/movement_statement.py:508-511`).
   - the reach population binds the session row's own version: `lib/movement_statement.py:348` (`_reach_rate_sql`), `:371-374` (`_fetch_reach_rates`).
   - `tests/meta/test_level_rule_version_readers.py`: `WATCHED` (`:15`), `ALLOWED` (`:18-22`).
   - the dry run with no write: `generate_premarket_brief(..., no_persist: bool = False, ...)` (`gcp/premarket_brief.py:1174-1203`), `build_persist_rows` (`:3856`, the plan target prices at `:3961-3966`), `_resolve_no_persist` (`:4536-4538`, `--no-persist` or `BRIEF_NO_PERSIST=true`).
   - line numbers that moved against main: `build_session_levels` `:2342` (main `:2328`), `_pick_side` `:2736` (`:2721`), `_plan_targets` `:2836` (`:2821`), `_plan_block` `:3197` (`:3173`), `structured_playbook_columns` `gcp/premarket_brief.py:1845` (`:1549`), the brief's `build_session_levels` call `:1650` (`:1372`), `load_level_params` call `:1218` (`:980`).
2. **The prior-close print rule**, spec `docs/superpowers/specs/2026-11-16-feat-playbook-001-prior-close-prints.md` (approved, PR #2016, on main). Its PC6 fixes the bump in every case: "LEVEL_RULE_VERSION is 'feat-strat-001.v5' ... PICK_RULE_VERSIONS holds v3, v4 and v5". Its build is not on main and has no plan on main yet (run: `ls docs/superpowers/plans`).

So **the marks version here is `feat-strat-001.v6`** (spec Design 6, second case), and v3, v4 and v5 are the level-rule versions.

**Every file:line in this plan must be re-read at the merge base when the implementation branch opens.** A task that cites a line cites it as of 1cb36eace or 8cd5e6859 and says which; neither is the base the code will be written on.

## Scope: what is in this plan

One plan, one branch, one PR, 15 tasks. Every done_when item, [0] to [11], is in it. Nothing is split off and nothing is dropped. 15 is the product-delivery skill's rough limit; the report that accompanies this plan says where a split would cut if the owner wants one. No task was merged to fit the number.

One thing the implementer cannot close alone, written where it sits:

- **done_when[11], the two yeses.** The merge and the swap rows are the owner's steps (Close-out).

Two items of r1 could not be met as written; r2 replaces both, and neither now waits on the owner before code:

- **done_when[7], the word 'quarter'.** r1 forbade it in any string literal of `lib/strat_levels.py`, where five literals already hold it for the quarter timeframe. r2 asks instead that, for each of '25%', '50%', '75%', '100%', '1/4' and 'quarter', the count of string literals of that file containing it equals a number pinned from the merge base. On main d410174b2 and f8f6c6996 the counts are 0, 0, 0, 0, 0 and 5 (run 2026-11-17, by `ast` over every string constant: `quarter` at `:258`, `:340` twice, `:347` and `:3231`). Task 1 Step 3 records the counts on the merge base; Task 12 pins them.
- **done_when[9], arm A's pin.** r1 required arm A to reproduce +176.8 R over 3,463 trades on the implementation base, which the brief build's premarket rules (`lib/indicators.py`, `gcp/fetchers/fetch_market_data.py` change on its branch, run: `git diff --stat origin/main...8cd5e6859`) and the prior-close rule may move. r2 makes it two checks, both required: (a) a harness check at 97190ef41, the spike's base, which must reproduce that figure to 0.1 R, and (b) arm A on the head, reported as it comes out, with the difference attributed by trigger-changed ticker-days. Task 13 adds the driver's baseline-only mode and the measure; Task 14 Step 4 runs both checks.

## Merge is a production schema change

`gcp/cloudbuild/apply-schema-cloudbuild.yaml:1-5`: the `apply-schema-on-change` trigger "Fires: push to main touching gcp/schema.sql" and applies that revision's schema (read; the live trigger was not read). This PR adds two policy rows and eight nullable columns to `gcp/schema.sql`, so its merge writes to production.

- **Auto-merge is never enabled on the implementation PR**, whatever the standing instruction for other PRs. Its merge is the owner's first yes of done_when[11], asked once and recorded on the PR.
- The seeded rows change no target. A job still on the old image reads a policy key it does not know as a ticker key with status `params_unavailable`, records it and ignores it (`lib/strat_levels.py:1454-1496`, main).
- Rows before code: the merge applies the rows before any deploy. Code deployed against a database without the marks row publishes no target for that run (Global Constraints, "the version of a fresh build").

## The old plan on main

`docs/superpowers/plans/2026-11-16-feat-strat-001-plan-always-three-targets-full-ladder.md` is on main with `status: ready`, `pr: null`, `branch: feature/feat-strat-001-plan-always-three-targets`, and names the superseded spec. What `scripts/gate/spec_gate.py` at 1cb36eace allows, each run on this branch with the edit staged and reverted afterwards:

| Edit | Gate's answer (`python3 scripts/gate/spec_gate.py --commit`, exit 1) | Code |
|---|---|---|
| `status: ready` to `status: done`, from a docs branch | "closes a plan whose PR #None is not yet in the base's record for FEAT-STRAT-001; the close follows the merge, so the lineage or the row names the PR first" | `check_changed_plans` `:2130-2132`, `pr_recorded_on_base` `:2054-2063` |
| any other edit, from a docs branch | "only the plan's own branch edits it, except the close after merge, which sets status: done and changes nothing else" | `:2127-2129` |
| deleting it | "a plan is not deleted; a finished plan is marked status: done and stays as the record" | `:2080-2083` |
| editing it on its own branch `feature/feat-strat-001-plan-always-three-targets` | refused there too: "... is status: superseded; point the plan at the spec that replaced it" (`:2515-2516`), and the plan cannot be re-pointed: "a plan binds one spec" (`plan_stays_bound`, `:1682-1684`) | not run on that branch; read |

A plan has only `ready` and `done` (`PLAN_STATUSES`, `:1351`). So the gate allows **no edit** of the old plan: it has no PR to record, it cannot be deleted, and its own branch is refused for its superseded spec. It is not edited in this commit. It authorizes nothing: the gate refuses every commit on its branch. **Recommendation: leave it as it is.** Marking it `done` would need a gate change that lets a plan whose spec is superseded close without a PR, which is gate-file work under FEAT-CICD-001 with its red-team pass, and is not worth doing for one file. This plan's branch name differs from the old plan's, so the two never meet in the gate's lookup (`:2481-2487`).

## Global Constraints

- Base: `origin/main` when the code branch opens, after Task 1's check. Branch `feature/feat-strat-001-atr-quarter-targets`. This plan is committed alone on `docs/plan-feat-strat-001-atr-quarter-targets` and merged before the code branch opens.
- The owner's rule, exact values: marks `[0.25, 0.5, 0.75, 1.0]` of ATR(14) from the entry trigger, calls above and puts below, four sales of 1/4, levels printed as waypoints, no snapping. IWM 2026-11-16, ATR 4.874951, offsets 122, 244, 366 and 487 cents: calls 280.14, 281.36, 282.58, 283.79 from 278.92; puts 274.64, 273.42, 272.20, 270.99 from 275.86 (run for this plan with `lib.strat_levels.price_cents`).
- Seeded to today's plan. `gcp/schema.sql` seeds exactly two new `level_param_policy` rows, each `effective_from` `'2015-01-02'` under `ON CONFLICT (param_key, effective_from) DO NOTHING`, no existing row changed, `exit_legs` stays `{"legs": 3}`:
  - `plan_target_marks_atr`: `policy`, extra `{"marks": []}`
  - `ladder_history_sessions`: `policy`, extra `{"sessions": 250}`
- The swap rows of Design 8 (`{"marks": [0.25, 0.5, 0.75, 1.0]}` and `{"legs": 4}` on one later date) are **not** in this PR. They exist only in tests and in the Experiment's local databases.
- Rule versions: the marks version is `feat-strat-001.v6`, named once as `LEVEL_RULE_MARKS`. `LEVEL_RULE_VERSION` does not move in this PR. No file under `lib/`, `gcp/` or `platform/` compares a value with a rule version constant outside `is_current_pick_rule`, `plan_target_rule` and the two population lines of `lib/movement_statement.py`.
- **The version of a fresh build** (a choice this plan makes; the spec names only the non-empty and the empty list): a fresh build records the level rule's version only when the marks row in force is ok with an empty list; in every other case (non-empty, or a row that is missing or not ok) it records the marks version and the mark walk publishes no target with the row's status. A row that cannot be read never falls back to the level walk (CLAUDE.md 3.7; spec Risks, "Deploy order").
- No number and no name in the level code (done_when[7]). On the `build_session_levels` walk `lib/strat_levels.py` holds no numeric literal other than 0, 1, -1, 2, -2 and 100 (`tests/lib/test_level_params_structure.py:32`) and no new numeric module constant. The marks, the leg count and the history length are read only from `LevelParams`; the percent and the share texts are formatted from those values.
- No silent fallback (CLAUDE.md 3.7). A key that is not ok publishes no target and says which status; a failed reach-history read raises; a missing value is `None` and prints as words, never 0. The only display fallback is `no history yet` for a side with zero rows.
- Distances are compared in cents through `price_cents`. An offset is rounded to the cent once and added to the trigger's cents.
- Unchanged (done_when[8]): the trigger and stop rule, `gate_targets` and the `t1..t3` columns, the opened-through rule, the entry cutoff, the level rule's spaced walk and thirds for every basis not built under the marks, the gap-edge rule for those bases, the ATR rungs and their thinning, the NEXT LEVELS Calls and Puts lines, PMG zones, the signal monitor, the movement statement's four slots, persona plans, the CALL/PUT pick and the resolver's existing outcome columns. No insight risk rule, no `gcp/insight_discord_push.py`, no solyra file.
- **`gcp/schema.sql` merges to production.** See "Merge is a production schema change". The PR never has auto-merge enabled and merges only on the owner's recorded yes.
- Production access. Tasks 2 to 13 touch no production system. Each step that does is marked **Ask the owner once before running** and is never assumed approved: Task 1 Step 4 (a read-only export of three stored rows), Task 14 Step 1 (one read-only export and one bucket download), the merge, and every Close-out step. No `--commit`, no deploy, no schema apply and no policy row change is run from this branch.
- Replays go through production code (CLAUDE.md 3.5, 3.6): bases are built by `gcp.premarket_brief.main` with `BRIEF_AS_OF`, scored by `gcp.premarket_playbook_resolver.plan_inputs` and `resolve_plan`. The Experiment's driver walks no bar, computes no indicator and no level, and never replaces `targets` or `legs` on a `PlanInputs`.
- Tests are hermetic. **CI's Run Tests job checks out one commit with no `origin/main`**, so no test runs `git show origin/main:...` or any other git command. "Equal to origin/main's" is pinned by a literal in the test or by a fixture file Task 1 records from the base and commits.
- **`.gitignore` ignores `*.csv`** (`:109`). A fixture that must be a CSV is added with `git add -f`; prefer JSON or `.txt` fixtures, which are not ignored.
- **The render step.** Every commit that moves lines in `gcp/`, `lib/` or `scripts/` ends with it, because the generated inventory cites line numbers:
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py tests/meta/test_model_registry_consistency.py -q` (expect all passed), and stage whichever docs changed with the code. The command is the one the old plan on main records; re-read it at the base.
- **`tests/lib/test_movement_statement.py` locally** needs the research test set alongside it: it patches `gcp.research.strat_engine.strat_pred_serve` (`:157`), which CI runs in the `research-test` job with `requirements-research.txt` (`.github/workflows/backtest-pipeline.yml:56-78`). Run it with that stack installed and report both jobs' results; a local skip is not a pass.
- **The source-snapshot verifier's ceiling.** On main 1cb36eace `scripts/maintenance/doc_source_snapshot.py:35` is `MAX_BYTES = 16777216` (PR #2011, merged as b1ce1b8f0); main's input was 12,233,575 bytes on 2026-11-16 against the earlier 12 MiB ceiling (handed to this plan, not measured for it). Task 15 runs the verifier with its default ceilings. If it still refuses on size, stop: post the measured size on the PR and ask the owner; never pass a larger `--max-input-bytes`, and never edit the verifier from this branch (it is FEAT-CICD-001's file).
- Commits: conventional `type(scope): description`, imperative, no AI attribution. The PR opens as a draft and stays one until every done_when line in its body is ticked with evidence. Every new test has a red then green record in the PR body.
- No em or en dashes in code comments, copy or docs written for this change.

### Capacity (CLAUDE.md Rule 0; spec Design 10), copied into the PR body

- **Volume:** two policy rows; eight nullable columns; each new marks-version `level_basis` gains a waypoint list of about 3 to 10 entries a side (IWM 2026-11-16: 5 and 3) and, by this plan's choice below, the reach values the brief read, at most `ladder_history_sessions` numbers a side (250 x 2 floats, about 4 kB of JSON), and loses the skipped list.
- **Velocity:** one new query a brief run for all tickers, returning at most `ladder_history_sessions` x tickers rows (250 x 3 = 750) of two numbers. No new query in the resolver: `mfe_atr` is computed on the bars `resolve_one` already holds and written by the UPDATE it already runs.
- **Wall-clock:** one more round trip a brief run, about 0.5 to 2 s at the connector's speed. Task 11 reads `EXPLAIN (ANALYZE, BUFFERS)` for the query on the ephemeral Postgres and Task 14 on the local copy (3,657 rows); production's plan and latency are not measured before the merge and are a Close-out read.
- **Cost:** $0 scheduled; no new job, schedule or image. The Experiment runs locally: four replays of 1,219 sessions (arm A at 97190ef41 for the harness check, and A, Q and Q3 on the head) (the spike's took about 30 minutes each on four processes, read in its logs) and one history calibration (about 6 minutes a ticker). Each production dry run after the merge costs one brief's model calls and is the owner's step.
- **I/O shape test:** Task 10, one query for N tickers.

### Choices this plan makes where the spec leaves one open (each reported to the owner with the plan)

- **The reach history is an input the basis records.** done_when[4] asks that a marks-version basis "rebuilds the same four targets, waypoints and text". The text holds `reached k of n`, which cannot be rebuilt from counts alone, so a marks-version basis records `plan_reach_history` (`{"status", "sessions", "rule_version", "long": [...], "short": [...]}`) and each target and waypoint also carries its `reached` pair. This is more than Design 10's Volume line names.
- **The reach span** is each ticker's last `ladder_history_sessions` rows by `analysis_date` before the session, then filtered to the rule version and to a non-NULL value. No `run_kind` filter: the spec names none.
- **The version of a fresh build**, above.
- **The Experiment's three arms are three local databases** cloned from one loaded and calibrated template, differing only in the two policy rows, each replayed by the production brief. No arm is derived from another arm's rows. The harness check's database is a fourth, built from 97190ef41's schema and prepared by that commit's tools from the same exported inputs (Task 14 Step 4).
- **The harness is committed**, as `scripts/analysis/atr_marks_experiment.py` with `tests/scripts/test_atr_marks_experiment.py`. CLAUDE.md 3.6 forbids throwaway harnesses that hand-roll bar iteration, indicators or scoring; this one loops over dates and calls `gcp.premarket_brief.main`, `plan_inputs` and `resolve_plan`, and a test fails it if it ever does more. `scripts/analysis/` already holds its like (`honest_scoring_experiment.py`, `brief_rsi_band_experiment.py`). Committed, the run is reproducible from the repo, which the spike's is not.

## done_when map

| done_when | What | Task |
|---|---|---|
| [0] | Policy rows | 2, 11 |
| [1] | ATR marks are the targets | 4 |
| [2] | Waypoints and the stronger case | 5 |
| [3] | Brief copy | 6 |
| [4] | Rule version and stored briefs | 3, 7 |
| [5] | The fourth target is stored and scored | 8, 11 |
| [6] | Reach history stored and read | 9, 10, 11 |
| [7] | No numbers and no names | 1, 12 |
| [8] | Unchanged | 1, 12 |
| [9] | Experiment through the production paths | 13, 14 |
| [10] | Source identity (DASHBOARD-01) | 15 |
| [11] | Catalog, traceability, gate; production only on the owner's yes | 15, Close-out |

## Review Focus

Inputs the spec implies and no done_when test pins, most likely first. Each has a test in the task that owns the code.

- **A replay of a session before the swap, run after the swap rows exist.** With the seeded rows and later-dated swap rows in one policy table, a build for a session before the swap date records the level rule's version and today's targets, and a build on or after it records v6 and the marks. A reader expects an old morning to replay as it was. Task 3.
- **Derived builds.** `with_premarket` (the planner's newer snapshot) and `with_reference` (the signal monitor's put re-anchor) of a marks-version session place the marks from the new trigger, rebuild the waypoints, carry the reach history and leave `gate_targets` as the level rule gives them. Task 5.
- **A fill bar with nothing after it.** A side entered on the last bar before the close has no later bar: `mfe_atr` is 0.0, not NULL and not an error. Task 9.
- **The longer playbook in Discord.** The IWM After text passed through `_playbook_code_fields` gives fields that rejoin to the same lines in order, none over the field limit and none cut (the spec did not check the split). Task 6.
- **A reach history with a bad value, or for one ticker only.** A NaN or negative stored value is not counted as a session and is logged with its date; a ticker with no rows prints `no history yet` while the others print counts; the read is still one query. Task 10.

## File map

| File | Change | Task |
|---|---|---|
| `tests/fixtures/level_basis_2026-11-16/` | new: `IWM.json`, `SPY.json`, `QQQ.json`, `sources.json`, per ticker `<T>.main.json` and `<T>.main.txt` | 1 |
| `tests/lib/session_levels_helpers.py` | `stored_1116`, `main_1116`, `main_text_1116`, `marks_basis`, the two golden reach histories | 1, 4 |
| `gcp/schema.sql` | two policy rows after the `plan_target_level_types` row (`:2318-2320`, main); `plan_t4_price` x2 beside `:1900-1905` and `:2166-2171`; `plan_t4_hit_ts` x2 and `plan_mfe_atr` x2 beside `:1992-2004` | 2, 8, 9 |
| `lib/strat_levels.py` | keys beside `:1012-1015`; `policy_wide_param` (`:1365`); version constants and helpers beside the brief build's `:1519-1529`; `SideLevels`, `SessionLevels` (`to_basis`, `from_basis`, `to_level_map`, `_atr_levels_line`), `build_session_levels`, `_assemble`, `_pick_side`, `_legacy_trigger_dict`, `_plan_block`; new `_plan_mark_targets`, `_plan_waypoints`, `reach_count`, `_mark_plan_lines` | 2 to 7 |
| `tests/lib/level_params_fixtures.py` | the two new keys in the fixture policy | 2 |
| `tests/meta/test_level_rule_version_readers.py` | `LEVEL_RULE_MARKS` and `LEVEL_PICK_RULE_VERSIONS` in `WATCHED`; `plan_target_rule` in `ALLOWED` | 3 |
| `gcp/premarket_playbook_resolver.py` | `RESOLVER_VERSION`, `PlanOutcome`, `PlanInputs`, `resolve_plan`, `plan_inputs`, `_PLAN_FIELDS` | 8, 9 |
| `gcp/premarket_brief.py` | `structured_playbook_columns`, `build_persist_rows`; new `read_plan_reach_history`; `generate_premarket_brief` | 8, 10 |
| `scripts/analysis/atr_marks_experiment.py` | new: the Experiment's driver | 13 |
| `tests/fixtures/atr_marks_spike_2026-11-16/` | new: the spike's two report texts, verbatim | 13 |
| `tests/lib/test_strat_levels.py` | `TestStored20261116`, `TestAtrMarkTargets`, `TestPlanWaypoints`, `TestAtrMarkCopy` | 1, 4, 5, 6 |
| `tests/lib/test_level_params_loader.py` | the two keys; the key-set pin | 2 |
| `tests/gcp/test_level_basis.py`, `tests/lib/test_movement_statement.py` | stored-brief and version tests | 3, 7 |
| `tests/gcp/test_premarket_playbook_resolver.py` | `TestFourLegs`, `TestPlanMfe` | 8, 9 |
| `tests/gcp/test_premarket_brief.py` | `plan_t4` columns; the reach-history read | 8, 10 |
| `tests/integration/test_atr_marks_schema_pg.py` | new | 11 |
| `tests/lib/test_level_params_structure.py`, `tests/lib/test_level_params_copy.py` | added assertions only | 12 |
| `tests/scripts/test_atr_marks_experiment.py` | new | 13 |
| `docs/product/02`, `03`, `12`, `docs/review-evidence/site-source-snapshot.json`, `docs/product/infrastructure/05-a`, `05-c`, `05-e` | close; inventory by the render step | 15, 2 to 13 |

---

### Task 1: Preconditions, the three stored bases, and today's plan pinned on them

Spec: Decision 9 (merge order); Design 6 ("Which number the marks version is"); Design 7 ("Fixtures"). Advances done_when[8]; supplies done_when[1] to [4].

**Files:**
- Create: `tests/fixtures/level_basis_2026-11-16/{IWM,SPY,QQQ}.json`, `sources.json`, `{IWM,SPY,QQQ}.main.json`, `{IWM,SPY,QQQ}.main.txt`
- Modify: `tests/lib/session_levels_helpers.py`
- Test: `tests/lib/test_strat_levels.py`

**Interfaces:**
- Produces: `stored_1116(ticker: str) -> dict` (the stored basis, a fresh copy each call); `main_1116(ticker: str) -> dict`; `main_text_1116(ticker: str) -> str`; `CALLS_REACH_D7 = (0.1, 0.3, 0.4, 0.7, 1.1, 1.2, 1.6, 2.4)`; `PUTS_REACH_D7 = (0.05, 0.2, 0.3, 0.6, 0.9, 1.3, 1.5, 2.1)`.

- [ ] **Step 1: Precondition check, before the branch is cut.** On `origin/main`, all of these must hold; paste each output into the PR body:
  - `grep -n "^LEVEL_RULE_VERSION\|^PICK_RULE_VERSIONS\|^def is_current_pick_rule" lib/strat_levels.py` shows `LEVEL_RULE_VERSION = 'feat-strat-001.v5'`, a `PICK_RULE_VERSIONS` holding v3, v4 and v5, and the helper.
  - `grep -n "no_persist\|BRIEF_NO_PERSIST" gcp/premarket_brief.py` finds the dry run.
  - `ls tests/meta/test_level_rule_version_readers.py` exists.
  - `grep -n "^status" docs/superpowers/specs/2026-11-16-feat-strat-001-atr-quarter-targets-r2.md` reads `approved`.
  If the brief build (PR #2010) or the prior-close build is not on main, **stop**: do not open the branch, do not add the helpers here, and report which is missing. The spec's alternative order (this change first) is not this plan.
- [ ] **Step 2: Re-read every line number.** For each file:line in the File map and the tasks, find the named function on the base and record the base's line in a table in the PR body (`grep -n "^def \|^class \|^    def " lib/strat_levels.py gcp/premarket_playbook_resolver.py gcp/premarket_brief.py lib/movement_statement.py`). Record the names the prior-close build gave the v4 and v5 constants; Task 3 uses them as they are.
- [ ] **Step 3: The six counts of done_when[7], on the merge base,** before any code: `python3 -c "import ast;t=ast.parse(open('lib/strat_levels.py').read());c=[n for n in ast.walk(t) if isinstance(n,ast.Constant) and isinstance(n.value,str)];[print(repr(s),len(h),h) for s in ('25%','50%','75%','100%','1/4','quarter') for h in [sorted(n.lineno for n in c if s in n.value)]]"`. On main d410174b2 and f8f6c6996 it prints 0, 0, 0, 0, 0 and 5, the five being `quarter` at `:258`, `:340` (two), `:347` and `:3231` (run 2026-11-17). Paste the output, with its line numbers, into the PR body; Task 12 types the six counts into its test. If the merge base gives other numbers, those are the pins, and the PR body names the commit that moved them.
- [ ] **Step 4: Export the three bases. Ask the owner once before running** (read-only, `scripts/db_query_cr.sh` without `--commit`): one statement a ticker selecting `level_basis` from `premarket_analysis_history` (falling back to `premarket_analysis`) for `analysis_date = '2026-11-16'` and the ticker, where `level_basis->>'built_at'` starts `2026-11-16T08:31:19`. The copy is taken by build time because the prior-close change's close-out may overwrite the canonical row. Save each JSON verbatim. `sources.json` names, per file, the db-query execution id, the SQL and the file's sha256. If the owner says no, stop: Tasks 4 to 7 have no fixture.
- [ ] **Step 5: Record what the base gives**, before any code changes, with a one-off run that is not committed: for each ticker, `sl = SessionLevels.from_basis(stored_1116(t))`; write `<T>.main.json` holding, per side, `trigger`, `stop`, `targets`, `skipped`, `gate_targets`, `target_status` and `plan` from `sl.to_basis()`, plus `plan_inputs` (trigger, stop, targets, legs, cutoff, status) for both sides; write `<T>.main.txt` holding `format_levels_for_brief(sl.to_level_map(), 'bearish')`.
- [ ] **Step 6: Write the tests** in `TestStored20261116`:
  - `test_sources_json_matches_the_files`: each basis file's sha256 equals its `sources.json` entry.
  - `test_iwm_trigger_and_stop`: IWM calls trigger 278.92 named `PMK_H`, stop 275.86 `PMK_L`; IWM puts trigger 275.86 `PMK_L`, stop 277.41 `PQL`; `atr` 4.874951 for `atr_basis` `atr_14`.
  - `test_main_records_match` (three tickers): each side's rebuilt record equals `<T>.main.json`, and the rendered text equals `main_text_1116(t)`.
  - `test_iwm_text_is_the_specs_today_block`: `main_text_1116('IWM')` contains the spec's Design 7 "Today" block (r2 lines 520 to 536), CALLS and PUTS, character for character.
- [ ] **Step 7: Run:** `python3 -m pytest tests/lib/test_strat_levels.py -k TestStored20261116 -q` (expect all passed: this task pins the base, so there is no red). A failure is a finding about the spec's text or the stored row, reported to the owner on the PR, never a changed expectation.
- [ ] **Step 8: Commit:** `test(strat): pin today's plan on the three stored 2026-11-16 bases`

### Task 2: The two policy rows and their keys

Spec: Design 2 (first paragraph), Design 4 (`ladder_history_sessions`); done_when "Policy rows". Advances done_when[0].

**Files:**
- Modify: `gcp/schema.sql`, `lib/strat_levels.py`, `tests/lib/level_params_fixtures.py`
- Test: `tests/lib/test_level_params_loader.py`

**Interfaces:**
- Produces, in `lib/strat_levels.py`:
  - `PLAN_TARGET_MARKS_KEY = 'plan_target_marks_atr'`, `LADDER_HISTORY_KEY = 'ladder_history_sessions'`, each named once, both appended to `POLICY_WIDE_KEYS`.
  - `plan_target_marks(extra) -> Optional[tuple]`: the `marks` list as a tuple of floats (empty for an empty list); `None` when `marks` is missing or not a list, an entry is not an int or float (a bool is not a number), an entry is at or below zero, or an entry is not above the one before it.
  - `ladder_history_sessions(extra) -> Optional[int]`: `sessions` when it is an int, not a bool, of at least 1; else `None`.
  - `policy_wide_param`: for `PLAN_TARGET_MARKS_KEY` the value is `float(len(marks))` and the status ok when `plan_target_marks(extra)` is not `None`; for `LADDER_HISTORY_KEY` the value is `float(sessions)`. Otherwise `input_unavailable`, as the function gives every other key.
  - `LevelParams.plan_target_marks(self) -> Optional[tuple]`, beside `plan_target_level_types` (`:1214`).

- [ ] **Step 1: Write the failing tests**, on the policy loaded from `gcp/schema.sql` (`seeded_policy`, `ParamsDb`):
  - `test_schema_seeds_the_two_rows`: both keys in force on 2015-01-02 with method `policy`, extras `{"marks": []}` and `{"sessions": 250}`; `exit_legs` extra is `{"legs": 3}`; the seeded policy minus the two new keys equals a literal dict of the base's rows (read from the base, typed into the test).
  - `test_both_keys_are_policy_wide`: `{PLAN_TARGET_MARKS_KEY, LADDER_HISTORY_KEY} <= set(POLICY_WIDE_KEYS)`; each key's string appears in exactly one string literal of `lib/strat_levels.py` (by `ast`).
  - `test_marks_param_status` (parametrised, through `ParamsDb.set_policy` with a later `effective_from`): `[]` gives ok, value 0.0; `[0.25, 0.5, 0.75, 1.0]` ok, 4.0; `[0.25]` ok, 1.0; and `input_unavailable` for `{}`, `{"marks": null}`, `{"marks": "0.25"}`, `[0.25, "0.5"]`, `[true]`, `[0.0, 0.5]`, `[-0.25]`, `[0.25, 0.25]`, `[0.5, 0.25]`.
  - `test_history_sessions_param_status`: `{"sessions": 250}` ok, 250.0; `{"sessions": 1}` ok; `input_unavailable` for `0`, `-1`, `2.5`, `"250"`, `true` and `{}`.
  - `test_seeded_marks_accessor`: `fixture_params().plan_target_marks() == ()`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_level_params_loader.py -q` (expect FAIL: the keys do not exist).
- [ ] **Step 3: Implement.** In `gcp/schema.sql`, add the two rows to the existing seed `INSERT` (before its `ON CONFLICT`), under a comment naming this spec, with notes `'targets at these distances from the entry trigger / ATR, nearest first; empty keeps the level rule'` and `'analysis dates of reach history the brief reads for a plan line'`. Add the keys, the two readers, the two `policy_wide_param` branches and the accessor. Add both keys to the fixture policy of `tests/lib/level_params_fixtures.py` and update the key-set pin of `tests/lib/test_level_params_loader.py`.
- [ ] **Step 4: Run again** (expect PASS), then `python3 -m pytest tests/lib tests/gcp -q -x` (expect no failure the base does not have).
- [ ] **Step 5: Render step, then commit:** `feat(strat): seed the ATR marks and reach history policy rows`

### Task 3: The marks rule version and which rule picks the targets

Spec: Design 6. Advances done_when[4] (the version clauses).

**Files:**
- Modify: `lib/strat_levels.py`, `tests/meta/test_level_rule_version_readers.py`
- Test: `tests/gcp/test_level_basis.py`, `tests/meta/test_level_rule_version_readers.py`

**Interfaces:**
- Produces, in `lib/strat_levels.py`, beside the version constants:
  - `LEVEL_RULE_MARKS = 'feat-strat-001.v6'`.
  - `LEVEL_PICK_RULE_VERSIONS`: the tuple `PICK_RULE_VERSIONS` holds on the base (v3, v4, v5), renamed; `PICK_RULE_VERSIONS = LEVEL_PICK_RULE_VERSIONS + (LEVEL_RULE_MARKS,)`. `is_current_pick_rule` is unchanged and now answers true for v6.
  - `TARGET_RULE_V2 = 'v2'`, `TARGET_RULE_LEVELS = 'levels'`, `TARGET_RULE_ATR_MARKS = 'atr_marks'`.
  - `plan_target_rule(version) -> Optional[str]`: `TARGET_RULE_V2` for `LEVEL_RULE_V2`, `TARGET_RULE_LEVELS` for a member of `LEVEL_PICK_RULE_VERSIONS`, `TARGET_RULE_ATR_MARKS` for `LEVEL_RULE_MARKS`, `None` for anything else (a non-string included).
  - `build_rule_version(params: LevelParams) -> str`: `LEVEL_RULE_VERSION` when `params.param(PLAN_TARGET_MARKS_KEY)` is ok with value 0; else `LEVEL_RULE_MARKS`.
  - `build_session_levels` constructs its `SessionLevels` with `rule_version=build_rule_version(params)`; `_pick_side` replaces its `rule_version == LEVEL_RULE_V2` test (`:2803`, main) with `plan_target_rule(rule_version)`. In this task the `atr_marks` branch publishes no target with `target_status` `'input_unavailable'`; Task 4 fills it.

- [ ] **Step 1: Write the failing tests:**
  - `test_plan_target_rule` (meta file): the four answers above, by literal version strings `'feat-strat-001.v2'` to `'.v6'`, and `None` for `'feat-strat-001.v1'`, `None` and `6`.
  - `test_marks_version_is_a_pick_rule`: `is_current_pick_rule('feat-strat-001.v6')` is true; `LEVEL_RULE_VERSION` equals the literal Task 1 Step 1 recorded.
  - in the meta test: `WATCHED` gains `'LEVEL_RULE_MARKS'` and `'LEVEL_PICK_RULE_VERSIONS'`; `ALLOWED` gains `('lib/strat_levels.py', 'plan_target_rule')`; the existing scan test then passes only if no other site compares with any watched name.
  - `test_fresh_build_version_follows_the_marks_row` (`tests/gcp/test_level_basis.py`, on `d8_session`-style inputs with `ParamsDb`): seeded policy gives `LEVEL_RULE_VERSION`; a later marks row `[0.25, 0.5, 0.75, 1.0]` with legs 4 gives `'feat-strat-001.v6'`; a later marks row `{"marks": "x"}` gives v6 with both sides' `target_status` `'input_unavailable'` and no target; a policy with the marks row dropped (`ParamsDb.drop`-style, key absent) gives v6 and `params_unavailable`.
  - **Review Focus 1,** `test_a_session_before_the_swap_replays_under_the_level_rule`: with the seeded rows and swap rows dated 2026-12-01, `ParamsDb.load` for session 2026-11-16 builds `LEVEL_RULE_VERSION` with the base's targets, and for 2026-12-01 builds v6.
- [ ] **Step 2: Run:** `python3 -m pytest tests/meta/test_level_rule_version_readers.py tests/gcp/test_level_basis.py -q` (expect FAIL: no `plan_target_rule`).
- [ ] **Step 3: Implement** the constants and the two helpers; route `_pick_side` and `build_session_levels` through them. No other comparison with a version constant is added anywhere.
- [ ] **Step 4: Run again** (expect PASS), then `python3 -m pytest tests/lib tests/gcp tests/api tests/meta -q` (expect no failure the base does not have). A fixture that builds fresh params without the seeded policy now builds v6 with no target: add the two keys to that fixture, never a fallback to the code, and list each such fixture in the PR body.
- [ ] **Step 5: Render step, then commit:** `feat(strat): name the ATR marks rule version and its target rule`

### Task 4: The marks are the targets

Spec: Design 2. Closes done_when[1].

**Files:**
- Modify: `lib/strat_levels.py`, `tests/lib/session_levels_helpers.py`
- Test: `tests/lib/test_strat_levels.py`

**Interfaces:**
- Consumes: `plan_target_rule`, `LevelParams.plan_target_marks`, `stored_1116`, `main_1116`.
- Produces:
  - `marks_basis(basis: dict, marks, legs: int, *, marks_extra: Optional[dict] = None) -> dict` (test helper): a copy whose `params` records for `plan_target_marks_atr` and `exit_legs` are the given ones (built with `policy_wide_param(...).to_basis()`), whose `rule_version` is `'feat-strat-001.v6'`, with the `long` and `short` records removed so nothing stored is trusted.
  - `_plan_mark_targets(out: SideLevels, trig: dict, ref: float, atr: float, params: LevelParams, prior_close: Optional[float]) -> None`, called from `_pick_side` for `TARGET_RULE_ATR_MARKS`. Keys checked first, in this order: `PLAN_TARGET_MARKS_KEY`, `EXIT_LEGS_KEY`, `ENTRY_CUTOFF_KEY`; the first not ok publishes no target and sets `target_status` to its status.
  - `out.plan` for a marks side: `{'rule': 'atr_marks', 'marks': [...], 'mark_prices': [...], 'atr': atr, 'atr_basis': ..., 'legs': int | None, 'entry_cutoff_et', 'entry_cutoff_status', 'gap_fill_flag_atr', 'gap_fill_flag_status'}`. No `spacing_atr` and no `spacing_price` key.
  - each target: `{'price': float, 'cents': int, 'name': 'T{k}', 'timeframe': '', 'mark': float, 'share': '1/{legs}', 'source': 'atr_mark'}`; `out.skipped == []`.
  - `target_status` `'input_unavailable'` with no target when: more marks than legs; two marks on one cent; an offset of zero cents; a puts target at or below zero cents.

- [ ] **Step 1: Write the failing tests** in `TestAtrMarkTargets`, each on `SessionLevels.from_basis(marks_basis(stored_1116(t), ...))`:
  - `test_iwm_quarters`: marks `[0.25, 0.5, 0.75, 1.0]`, legs 4: calls prices `[280.14, 281.36, 282.58, 283.79]`, puts `[274.64, 273.42, 272.20, 270.99]`.
  - `test_every_side_is_trigger_plus_or_minus_the_offset` (SPY, QQQ, IWM x two sides): each target's cents equal `price_cents(trigger) + sign * price_cents(mark * atr)`, with `atr = fixture[fixture['atr_basis']]` read from the fixture JSON in the test and the arithmetic done in the test.
  - `test_each_target_records_mark_share_and_source`: `mark` in `[0.25, 0.5, 0.75, 1.0]`, `share == '1/4'`, `source == 'atr_mark'`.
  - `test_trigger_stop_and_gate_targets_are_the_bases` (six sides): equal to `main_1116(t)`; IWM calls 278.92 `PMK_H`, stop 275.86 `PMK_L`; IWM puts 275.86 `PMK_L`, stop 277.41 `PQL`.
  - `test_no_target_is_moved_onto_a_level`: IWM puts T1 is 274.64, and no target price equals 274.67.
  - `test_skipped_is_empty` (six sides).
  - `test_three_marks_three_legs`: marks `[0.25, 0.5, 0.75]`, legs 3: each side has the first three prices of `test_iwm_quarters`.
  - `test_no_target_cases` (parametrised; each gives `targets == []`): four marks with legs 3 (`input_unavailable`); a marks record whose status is `input_unavailable` (`marks_extra={"marks": "x"}`) and one whose status is `params_basis_mismatch` (the row's status is carried); marks `[0.25, 0.2501]` on an ATR of 1.0 (one cent twice); marks `[0.0001]` on the IWM ATR (zero cents); a puts side with trigger 1.00 and marks `[1.0]` on an ATR of 2.0 (at or below zero). The last three use `d8_basis`-style synthetic bases.
  - `test_seeded_empty_list_is_the_base` (three tickers): `stored_1116(t)` with a `plan_target_marks_atr` record of `{"marks": []}` added to its params, its own `rule_version` kept: each side's `targets`, `skipped`, `target_status` and the rendered text equal `main_1116(t)` and `main_text_1116(t)`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_strat_levels.py -k TestAtrMarkTargets -q` (expect FAIL on every non-empty case: Task 3's branch publishes no target; `test_seeded_empty_list_is_the_base` passes already and is recorded as such).
- [ ] **Step 3: Implement `_plan_mark_targets`.** The offset is `price_cents(mark * atr)`, added to `trig['cents']` with the side's sign; the share text is formatted from the leg count. The prior-close gap fill note is Task 5's, with `on_level`.
- [ ] **Step 4: Run again** (expect PASS) and `python3 -m pytest tests/lib/test_strat_levels.py -q`.
- [ ] **Step 5: Render step, then commit:** `feat(strat): place plan targets at ATR marks from the trigger`

### Task 5: Levels are waypoints, and a target on a level is the stronger case

Spec: Design 3. Closes done_when[2].

**Files:**
- Modify: `lib/strat_levels.py`
- Test: `tests/lib/test_strat_levels.py`

**Interfaces:**
- Produces:
  - `SideLevels.plan_waypoints: Optional[list] = None` and `SideLevels.waypoint_zone_status: Optional[str] = None`; `to_dict` adds both keys only when `plan_waypoints is not None`, so a level-rule side's record is byte-equal to the base's.
  - `_pick_side(..., levels: Optional[list] = None)`: the session's `StratLevel` list, passed by `_assemble` (`out.levels`).
  - `_plan_waypoints(out: SideLevels, levels: list, ref: float, atr: float, params: LevelParams, window: Optional[float], prior_close: Optional[float]) -> None`, called after `_plan_mark_targets` when the side has targets.
  - a waypoint entry: `{'price': float, 'cents': int, 'names': [str, ...], 'segment': str, 'distance_atr': float}` and, for a zone of two or more cents, `'zone': {'far_price': float, 'members': [{'price', 'names'}, ...]}`. `segment` is `before_t1`, `t{i}_t{i+1}` or `beyond`, formatted from the target index. `distance_atr` is `cents past the trigger / (atr * 100)`, unrounded in the record.
  - a target on a level's cent gains `'on_level': [names]`; that level is not a waypoint. The prior close as a waypoint or `on_level` level carries `gap_fill_atr` or `gap_fill_status` by the rule of `_plan_targets` (`:2875-2888`, main).
  - Range: levels strictly past the trigger on the side's own side, out to the last target, and past it only while `_within_staleness_window(price, ref, atr, window)`.
  - Zones: within one segment, a level joins the open group when its cents from the group's first member (the one nearest the trigger) are at most `price_cents(level_cluster_atr * atr)`, equal joins. `LEVEL_CLUSTER_KEY` not ok: every level its own entry and `waypoint_zone_status` is the status; ok: `waypoint_zone_status` is `'ok'`.

- [ ] **Step 1: Write the failing tests** in `TestPlanWaypoints`, on the bases of Task 4 with marks `[0.25, 0.5, 0.75, 1.0]` and legs 4:
  - `test_waypoints_are_the_fixtures_levels` (six sides): the expected list is computed in the test from the fixture's `levels`, its trigger, targets, window and `level_cluster_atr` record, with its own grouping loop, and equals `plan_waypoints`.
  - `test_iwm_calls_by_name`: PDO 278.95, PDH 279.17 and PMC 279.33 in `before_t1`; CMO 281.64 in `t2_t3`; PMH 285.26 in `beyond`.
  - `test_iwm_puts_by_name`: PDL 274.67 in `before_t1`; `11/9 Gap Low` 274.55 in `t1_t2`; PML 269.88 in `beyond`.
  - `test_a_target_on_a_level_is_the_stronger_case`: IWM calls T4 283.79 has `on_level` containing `PWH`, and no waypoint has 28379 cents.
  - `test_one_cent_away_is_a_waypoint`: a synthetic base with a level one cent before a target: it is a waypoint and the target has no `on_level`.
  - `test_zones`: PDO and PDH are one entry with `zone.far_price` 279.17 and PMC is alone; a level exactly `price_cents(cluster * atr)` cents from the group's first member joins and one a cent farther does not; two levels either side of a target are never one zone.
  - `test_cluster_not_ok`: with the `level_cluster_atr` record's status `params_unavailable`, every level is its own entry and `waypoint_zone_status == 'params_unavailable'`.
  - `test_level_rule_side_has_no_waypoint_key`: `'plan_waypoints' not in` each side of `SessionLevels.from_basis(stored_1116(t)).to_basis()`.
  - **Review Focus 2,** `test_derived_builds`: on the IWM marks session, `with_reference(277.00)` and `with_premarket({...a later snapshot...})` give targets equal to their new trigger plus the offsets, waypoints rebuilt against it, and `gate_targets` equal to what the same call gives on the level-rule session.
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_strat_levels.py -k TestPlanWaypoints -q` (expect FAIL: no `plan_waypoints`).
- [ ] **Step 3: Implement** `_plan_waypoints` and the two fields; pass `levels` from `_assemble`. If the fixture holds a level in range that the owner's example does not name, the by-name tests still hold as "contains"; report the extra level on the PR.
- [ ] **Step 4: Run again** (expect PASS).
- [ ] **Step 5: Render step, then commit:** `feat(strat): list levels as waypoints between the ATR marks`

### Task 6: What the brief prints, with reach counts

Spec: Design 7; Design 4 (the count rule and the three texts); Decision 6. Closes done_when[3].

**Files:**
- Modify: `lib/strat_levels.py`
- Test: `tests/lib/test_strat_levels.py`, `tests/gcp/test_premarket_brief.py`

**Interfaces:**
- Produces:
  - `build_session_levels(..., reach_history: Optional[dict] = None)`. `SessionLevels.plan_reach_history: Optional[dict]`: `{'status': str, 'sessions': Optional[int], 'rule_version': str, 'long': [float, ...], 'short': [float, ...]}`. Recorded by `to_basis` only for a marks-version session; read back by `from_basis`; carried by `_assemble`, `with_premarket` and `with_reference`. A marks-version build handed `None` records status `'reach_history_not_read'`.
  - `reach_count(values, distance_cents: int, atr: float) -> tuple[int, int]`: `(k, n)` with `n = len(values)` and `k` the values at least `distance_cents / (atr * 100)`.
  - each marks target and waypoint gains `'reached': [k, n]` when the history status is ok, else no such key.
  - `_legacy_trigger_dict` carries, for a marks side, `plan_targets` with `mark`, `share`, `on_level`, `reached` and the gap fill keys, plus `plan_waypoints`, `waypoint_zone_status` and `reach_status`.
  - `_mark_plan_lines(side: str, trig: dict, plan: dict, atr_basis: Optional[str]) -> list`, called by `_plan_block` when `plan.get('rule') == TARGET_RULE_ATR_MARKS` and the status is ok; the stop line, the unavailable line and the room line stay `_plan_block`'s.
  - `SessionLevels._atr_levels_line` returns `None` for a marks-version session, so NEXT LEVELS prints no `ATR levels` line; the rungs stay in `level_basis`.
  - Texts: `reached {k} of {n}`; `no history yet` when `n == 0`; `reach history unavailable ({status})` when the status is not ok. Percent text is `f"{mark * 100:g}%"`; the ATR is printed to two places; a waypoint's distance as `f"{distance_atr:.2f} ATR past the trigger"`; a zone as `{near:.2f} to {far:.2f}` with its names nearest first.

- [ ] **Step 1: Write the failing tests** in `TestAtrMarkCopy`, on the IWM basis, bias `bearish`, reach history `{'status': 'ok', 'sessions': 250, 'rule_version': 'feat-strat-001.v6', 'long': CALLS_REACH_D7, 'short': PUTS_REACH_D7}`:
  - `test_seeded_policy_prints_the_base`: the CALLS and PUTS blocks equal those of `main_text_1116('IWM')`.
  - `test_after_text_is_the_specs`: with marks `[0.25, 0.5, 0.75, 1.0]`, legs 4, the CALLS and PUTS blocks equal the spec's Design 7 "After" block (r2 lines 541 to 568) character for character. It includes, for example, `T1: 280.14 (25% of ATR), sell 1/4, reached 7 of 8`, `T4: 283.79 (100% of ATR, on PWH: the stronger case), sell the last 1/4, or hold to the close or the stop, reached 4 of 8`, `278.95 to 279.17 (PDO, PDH): level on the way, 0.01 ATR past the trigger, reached 8 of 8` and `269.88 (PML): level beyond T4, 1.23 ATR past the trigger, reached 3 of 8`.
  - `test_three_marks_three_legs`: the share reads `1/3`; the T3 line contains `sell the last 1/3, or hold to the close or the stop`.
  - `test_fewer_marks_than_legs`: marks `[0.25, 0.5]`, legs 3: the T2 line contains `sell 1/3, hold the last 1/3 to the close or the stop` and the block never contains `sell the last 1/3`; marks `[0.25]`, legs 4: the T1 line contains `sell 1/4, hold the last 3/4 to the close or the stop`.
  - `test_empty_history_prints_no_history_yet`: with `'long': []`, every calls line ends `no history yet` and the block never contains `0 of 0`.
  - `test_history_not_ok`: status `input_unavailable` prints `reach history unavailable (input_unavailable)` on each line and the targets are unchanged.
  - `test_no_skipped_and_no_atr_levels_line`: the marks text contains neither `Skipped, closer than` nor `ATR levels`; the `Calls (up):` and `Puts (down):` lines and the `PMG ZONES` block equal the base text's.
  - `test_marks_not_ok_prints_the_existing_line`: `Targets unavailable (input_unavailable): no exit plan for this side.` and no line starting `    T1:`.
  - **Review Focus 4,** `test_the_longer_playbook_splits_whole` (`tests/gcp/test_premarket_brief.py`): the full IWM marks playbook through `_playbook_code_fields('IWM', text)`: the fields' code-block bodies joined give the text's lines in order, and no field value is over the function's field limit.
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_strat_levels.py -k TestAtrMarkCopy -q` (expect FAIL on every marks case).
- [ ] **Step 3: Implement.** If the fixture's text differs from the spec's After block because the fixture holds a level the owner's example does not name, the golden is the fixture's: record the built text in the test, and report the difference line by line on the PR.
- [ ] **Step 4: Run again** (expect PASS).
- [ ] **Step 5: Render step, then commit:** `feat(strat): print ATR mark targets, waypoints and reach counts`

### Task 7: Stored briefs keep their plan, and a marks basis rebuilds its own

Spec: Design 6. Closes done_when[4].

**Files:**
- Test: `tests/gcp/test_level_basis.py`, `tests/lib/test_movement_statement.py`, `tests/gcp/test_premarket_playbook_resolver.py` (code changes only if a test finds a defect)

- [ ] **Step 1: Write the tests:**
  - `test_a_level_rule_basis_rebuilds_as_the_base` (three tickers x two shapes): the stored basis as it is (its params record neither new key), and the same basis with both new keys recorded in its params, the marks record non-empty (`[0.25, 0.5, 0.75, 1.0]`) to show it is never checked: `SessionLevels.from_basis` gives `targets`, `skipped`, `target_status` and text equal to `main_1116` and `main_text_1116`.
  - `test_a_marks_basis_rebuilds_from_what_it_recorded`: build the IWM marks session, take `to_basis()`, and rebuild it with `from_basis(basis, params=<a LevelParams whose marks are [0.5, 1.0] and legs 2>)`: the four targets, the waypoints and the text are the first build's.
  - `test_plan_inputs_on_a_marks_basis`: `plan_inputs('calls', row, basis, policy_fn)` returns targets `(280.14, 281.36, 282.58, 283.79)`, `legs == 4`, `plan_available` true, with a `policy_fn` that raises if called; on the level-rule basis it returns what `<T>.main.json` recorded.
  - `test_reach_rates_do_not_mix_the_marks_version` (extend the file's `_VersionedRows` case, `tests/lib/test_movement_statement.py`, brief build `:1308-1372`): with resolved rows of the base's level rule and of v6 in the population, a v6 session binds `'feat-strat-001.v6'` and reads v6 counts only; a level-rule session binds its own.
  - `test_new_rule_mark_reads_a_marks_basis`: `_new_rule_mark` returns `cleared_above` for a v6 basis.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_level_basis.py tests/gcp/test_premarket_playbook_resolver.py -k "rebuilds or marks_basis" -q` and, with the research stack installed, `python3 -m pytest tests/lib/test_movement_statement.py -q`. Record the red for each from the commit before Task 3 (`git stash` is not used; check out that commit in a second worktree).
- [ ] **Step 3: Run the meta test:** `python3 -m pytest tests/meta/test_level_rule_version_readers.py -q` (expect PASS with the two `ALLOWED` additions of Task 3 and no other).
- [ ] **Step 4: Commit:** `test(strat): pin stored level-rule briefs and the marks basis rebuild`

### Task 8: The fourth target is stored and scored

Spec: Design 5. Closes done_when[5].

**Files:**
- Modify: `gcp/schema.sql`, `gcp/premarket_brief.py`, `gcp/premarket_playbook_resolver.py`
- Test: `tests/gcp/test_premarket_brief.py`, `tests/gcp/test_premarket_playbook_resolver.py`

**Interfaces:**
- Produces: `PlanOutcome.t4_hit_ts: Optional[datetime] = None`; `_PLAN_FIELDS` gains `'t4_hit_ts'` after `'t3_hit_ts'`; `structured_playbook_columns` writes `plan_t1` to `plan_t4` and `t1` to `t3`; `build_persist_rows` carries `calls_plan_t4_price` and `puts_plan_t4_price`.
- Schema, each `ADD COLUMN IF NOT EXISTS ... ` nullable: `calls_plan_t4_price`, `puts_plan_t4_price DOUBLE PRECISION` on `premarket_analysis` and on `premarket_analysis_history`; `calls_plan_t4_hit_ts`, `puts_plan_t4_hit_ts TIMESTAMPTZ` on `premarket_analysis`.

- [ ] **Step 1: Write the failing tests:**
  - `TestFourLegs`, on synthetic 1-minute bars, a call with trigger 100.00, stop 99.00, targets `(100.50, 101.00, 101.50, 102.00)`, `legs=4`, cutoff 960: `test_all_four_reached`: `exit == 't1,t2,t3,t4'`, `r == 1.25`, `t4_hit_ts` is the bar that reached 102.00; `test_stop_after_t2`: `exit == 't1,t2,stop,stop'`, `r == -0.125`, `t4_hit_ts is None`; `test_put_mirror_all_four` (trigger 100.00, stop 101.00, targets 99.50, 99.00, 98.50, 98.00: `'t1,t2,t3,t4'`, 1.25) and `test_put_mirror_stop_after_t2` (-0.125); `test_three_legs_leave_t4_null` (three targets, `legs=3`).
  - `test_resolve_one_update_sets_both_t4_columns`: the UPDATE text built by `resolve_one` (the file's existing engine stand-in) contains `calls_plan_t4_hit_ts = :calls_plan_t4_hit_ts` and the puts twin.
  - `test_structured_columns_write_four_plan_targets` (`tests/gcp/test_premarket_brief.py`): for the IWM marks level map, `calls_plan_t4_price == 283.79`, `puts_plan_t4_price == 270.99`, `calls_t1_price` to `calls_t3_price` equal the gate targets, and no `calls_t4_price` key exists; for the level-rule map `calls_plan_t4_price is None`.
  - `test_persisted_row_carries_plan_t4`: the canonical row of `build_persist_rows` holds both keys.
  - `test_schema_declares_the_t4_columns`: the six statements appear in `schema_statements()`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_premarket_playbook_resolver.py -k "TestFourLegs or t4" tests/gcp/test_premarket_brief.py -k "plan_t4 or four_plan" -q` (expect FAIL: `PlanOutcome` has no `t4_hit_ts`; the R and exit assertions of `TestFourLegs` pass already and are recorded as such).
- [ ] **Step 3: Implement.** The hit walk in `resolve_plan` covers the first four targets (`:550-553`, main); the `for k in (1, 2, 3)` of `structured_playbook_columns` takes its range from the prefix (three for `t`, four for `plan_t`), from a module tuple in `gcp/premarket_brief.py`. `targets[:plan.legs]` (`:545`) is not changed.
- [ ] **Step 4: Run again** (expect PASS); run the whole resolver file (every existing three-leg case passes unchanged).
- [ ] **Step 5: Render step, then commit:** `feat(strat): store and score a fourth plan target`

### Task 9: The resolver stores how far price went before the stop

Spec: Design 4 (first two paragraphs). Advances done_when[6] (the stored half).

**Files:**
- Modify: `gcp/schema.sql`, `gcp/premarket_playbook_resolver.py`
- Test: `tests/gcp/test_premarket_playbook_resolver.py`

**Interfaces:**
- Produces: `PlanInputs.atr: Optional[float] = None`, set by `plan_inputs` from the rebuilt session's `atr` for a pick-rule basis and left `None` on the v2 and no-basis paths; `PlanOutcome.mfe_atr: Optional[float] = None`; `_PLAN_FIELDS` gains `'mfe_atr'`, so the columns are `calls_plan_mfe_atr` and `puts_plan_mfe_atr` (nullable `DOUBLE PRECISION` on `premarket_analysis`); `RESOLVER_VERSION = '2026-11-16.v5'` with a comment line naming this spec (re-read the base's value first; the prior-close build may have moved it, and then this is the next one).
- Rule: for an `entered` side with a finite positive `plan.atr`: over the bars after the fill bar, up to and not including the bar in which the stop is hit, or to the last bar when no stop is hit or the side has no valid stop: calls `max(high) - trigger`, puts `trigger - min(low)`, floored at 0, divided by `plan.atr`. A fill bar that also touches the stop gives 0.0. No bar after the fill gives 0.0. Not entered, or no ATR: `None`. It is computed whatever `plan_available` says, since it reads only the trigger, the stop and the ATR.

- [ ] **Step 1: Write the failing tests** in `TestPlanMfe`, a call with trigger 100.00, stop 99.00, `atr=2.00`, entered on the first cross:
  - `test_high_before_a_later_stop`: a high of 103.00 two bars after the fill, the stop later: 1.5.
  - `test_the_stop_bar_does_not_count`: the bar that hits the stop has a high of 104.00; with an earlier high of 103.00 the value is 1.5.
  - `test_the_fill_bar_does_not_count`: 103.00 only on the fill bar, then bars under the trigger: 0.0.
  - `test_never_above_the_trigger_after_the_fill`: 0.0.
  - `test_not_entered_is_null` (`no_cross` and `opened_through`) and `test_no_atr_is_null` (`atr=None`).
  - `test_stop_less_side_is_measured_to_the_close`: `stop_price=None`, a high of 102.00 in the last bar: 1.0.
  - `test_fill_bar_touching_the_stop_is_zero`: 0.0 whatever follows.
  - `test_put_mirror`: trigger 100.00, stop 101.00, `atr=2.00`, a low of 97.00 before a later stop: 1.5; and the put twins of the stop-bar and fill-bar cases.
  - `test_half_day_is_cut_at_the_close`: through `resolve_one` for 2025-11-28 (close 13:00 ET) with bars to 16:00: a high of 101.00 before 13:00 and 105.00 at 14:30 gives `calls_plan_mfe_atr == 0.5`.
  - **Review Focus 3,** `test_entered_on_the_last_bar`: 0.0, not `None`.
  - `test_resolve_one_update_sets_both_mfe_columns` and `test_resolver_version_moved` (the constant differs from the literal the base holds).
  - `test_level_rule_row_gets_a_value`: a three-leg level-rule basis entered and stopped has `mfe_atr` set and `t4_hit_ts` `None`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_premarket_playbook_resolver.py -k TestPlanMfe -q` (expect FAIL: no `mfe_atr`).
- [ ] **Step 3: Implement** in `resolve_plan`, after the fill is known and before the `plan_available` return, on the arrays the function already holds; no second read of bars and no new query.
- [ ] **Step 4: Run again** (expect PASS); run the whole file.
- [ ] **Step 5: Render step, then commit:** `feat(strat): store the plan's reach before the stop in ATR`

### Task 10: The brief reads the reach history in one query

Spec: Design 4 (last paragraph); Design 6 ("Rates never mix rule versions"). Advances done_when[6] (the read half).

**Files:**
- Modify: `gcp/premarket_brief.py`
- Test: `tests/gcp/test_premarket_brief.py`

**Interfaces:**
- Consumes: `build_rule_version`, `LADDER_HISTORY_KEY`, `build_session_levels(reach_history=...)`.
- Produces:
  - `PLAN_REACH_HISTORY_SQL`: one statement over a `VALUES` list of the run's tickers, `CROSS JOIN LATERAL` the ticker's rows of `premarket_analysis` with `analysis_date < :session_date`, `ORDER BY analysis_date DESC LIMIT :sessions`, selecting `analysis_date`, `calls_plan_mfe_atr`, `puts_plan_mfe_atr` and `level_basis->>'rule_version'`; the outer `WHERE` keeps `rule_version = :rule_version` and rows where either value is not NULL.
  - `read_plan_reach_history(query_fn, tickers, session_date, level_params: dict) -> dict`: per upper-case ticker the dict Task 6 names. It makes no query and returns `None` for every ticker when the version to be built is not the marks version; returns status of the `ladder_history_sessions` row with empty lists, and makes no query, when that row is not ok; otherwise runs the one query through `query_fn` (the brief passes `_strict_read`) and lets any exception out.
  - `generate_premarket_brief` calls it once, after `load_level_params`, and passes each ticker's entry to `build_session_levels`.

- [ ] **Step 1: Write the failing tests**, with a recording `query_fn`:
  - `test_one_query_for_all_tickers`: three tickers, marks policy: exactly one call; its params hold `session_date`, `sessions == 250`, `rule_version == 'feat-strat-001.v6'` and the three tickers.
  - `test_the_sql_bounds_what_it_reads`: the statement contains `analysis_date < :session_date`, `LIMIT :sessions`, `level_basis->>'rule_version' = :rule_version` and both `IS NOT NULL` tests, and contains no `<=` on `analysis_date`.
  - `test_values_split_by_side`: rows with a NULL on one side count for the other side only; the lists are in date order.
  - `test_a_brief_as_of_run_sees_only_earlier_rows`: with `BRIEF_AS_OF=2026-11-10`, the bound `session_date` is `2026-11-10`.
  - `test_a_failed_read_raises`: a `query_fn` that raises: the exception leaves `read_plan_reach_history`, and `generate_premarket_brief` does not build a playbook containing `no history yet`.
  - `test_level_rule_run_makes_no_query`: seeded policy: zero calls.
  - `test_history_sessions_not_ok`: zero calls, status `input_unavailable`, and the playbook prints `reach history unavailable (input_unavailable)` with the targets unchanged.
  - **Review Focus 5,** `test_bad_values_and_a_ticker_with_no_rows`: a NaN and a negative value are left out of the lists and logged with ticker and date; a ticker with no rows gets `{'status': 'ok', ..., 'long': [], 'short': []}` while the others get their values.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_premarket_brief.py -k "reach_history or one_query or as_of_run" -q` (expect FAIL: no `read_plan_reach_history`).
- [ ] **Step 3: Implement.** A NaN or negative stored value is an internal defect of the resolver: it is logged at error level and not counted; it is never coerced to 0.
- [ ] **Step 4: Run again** (expect PASS); run the brief's dry-run tests of the brief build (its recording stand-in fails any statement that is not a SELECT; this one is a SELECT).
- [ ] **Step 5: Render step, then commit:** `feat(brief): read the plan reach history in one query`

### Task 11: The DDL and the reach query on a real Postgres

Spec: Design 5 ("The schema change applies itself"); Design 10. Supports done_when[0], [5] and [6]; this is the test of what the merge applies to production.

**Files:**
- Create: `tests/integration/test_atr_marks_schema_pg.py` (runs in CI's `integration-tests` job, `.github/workflows/backtest-pipeline.yml`, on `pgvector/pgvector:pg15` with `gcp/schema.sql` applied; excluded from `make test`)

- [ ] **Step 1: Write the tests** (fixtures `db_engine`, `clean_db`, `seed` of `tests/integration/conftest.py`):
  - `test_the_two_policy_rows_are_seeded`: one row a key, effective 2015-01-02, extras `{"marks": []}` and `{"sessions": 250}`; `exit_legs` is `{"legs": 3}`.
  - `test_the_eight_columns_exist_and_are_nullable`: `information_schema.columns` shows the four `plan_t4_price` columns (two tables), the two `plan_t4_hit_ts` and the two `plan_mfe_atr`, each `is_nullable = 'YES'`, with types `double precision` and `timestamp with time zone`.
  - `test_the_schema_applies_twice`: executing the two-row `INSERT` and the `ALTER TABLE` statements lifted from `gcp/schema.sql` a second time raises nothing and leaves one row a key.
  - `test_swap_rows_take_force_on_their_date`: inserting Design 8's rows dated 2026-12-01, `load_level_params` through the real engine gives marks `()` and legs 3 on 2026-11-30 and `(0.25, 0.5, 0.75, 1.0)` and legs 4 on 2026-12-01. The transaction is rolled back.
  - `test_reach_history_query_runs_and_is_bounded`: seed 300 dated rows a ticker for three tickers (v6 basis JSON, `plan_mfe_atr` values, some NULL, some another version); `read_plan_reach_history` through the real engine returns at most 250 values a side a ticker, none on or after the session date and none of another version; `EXPLAIN (ANALYZE, BUFFERS)` of the statement is printed into the test log and the test asserts the inner scan's actual rows a ticker loop are at most 250.
  - `test_resolve_one_writes_the_new_columns`: one seeded row and its bars resolved by `resolve_one` with the real engine: the four new outcome columns are written (`plan_t4_hit_ts` NULL for a three-leg row, `plan_mfe_atr` a number for an entered side).
- [ ] **Step 2: Run** against a local container started as CI starts it (`docker run -d -e POSTGRES_USER=trading_user -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=trading -p 5432:5432 pgvector/pgvector:pg15`, then `psql ... -v ON_ERROR_STOP=1 -f gcp/schema.sql`, then `DB_HOST=localhost DB_PORT=5432 DB_USER=trading_user DB_PASS=testpass DB_NAME=trading python3 -m pytest tests/integration/test_atr_marks_schema_pg.py -q`). Expect passed. Record the red by applying the base's `gcp/schema.sql` to a second container (the column and row tests fail there). Paste the EXPLAIN output into the PR body, reading `rows=` on the scan node (CLAUDE.md 3.8).
- [ ] **Step 3: Commit:** `test(strat): apply the ATR marks schema on the ephemeral Postgres`

### Task 12: No numbers, no names, and nothing else moved

Spec: done_when "No numbers and no names", "Unchanged". Closes done_when[7] and done_when[8].

**Files:**
- Test: `tests/lib/test_level_params_structure.py`, `tests/lib/test_level_params_copy.py` (added assertions only)

- [ ] **Step 1: Add the assertions:**
  - in `test_the_walk_reaches_the_rules_it_must_cover` (`:169-179`, main): `{"_plan_mark_targets", "_plan_waypoints"} <= reach`.
  - in `tests/lib/test_level_params_copy.py`: `MERGE_BASE_COUNTS = {"25%": 0, "50%": 0, "75%": 0, "100%": 0, "1/4": 0, "quarter": 5}`, the six numbers Task 1 Step 3 printed on the merge base, typed in with a comment naming the merge base's sha and the lines of each hit; and `test_no_new_mark_share_or_quarter_text`, parametrised over the six strings: over every `ast.Constant` of `lib/strat_levels.py` whose value is a `str` (the file's existing `_strings` walker, so docstrings and the constant parts of f-strings are included), the count of literals containing the string equals `MERGE_BASE_COUNTS[s]`. The test runs no git command; the pins are literals. A share or percent text typed into the level code raises a count and fails, and so does a new docstring or message that says 'quarter', '1/4' or a percent: the implementation's docstrings name the marks and shares by where they are read from (the policy row and the leg count), never by their values. The percent and share texts are formatted from the policy values (Task 6's `f"{mark * 100:g}%"` and the `1/{legs}` share), whose constant parts hold none of the six.
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_level_params_structure.py tests/lib/test_level_params_copy.py -q` (expect passed, with no change to `ALLOWED_VALUES` or the allowed names). Record the red: a literal `0.25` typed into `_plan_mark_targets` fails `test_no_numbers_on_the_level_and_plan_path[lib/strat_levels.py]`; the string `'sell 1/4'` added to `lib/strat_levels.py` fails `test_no_new_mark_share_or_quarter_text[1/4]`; a docstring reading "a quarter at each mark" fails it for `quarter`. Revert each.
- [ ] **Step 3: Run the unchanged pins,** each file unmodified but for the edits this plan names: `python3 -m pytest tests/lib/test_strat_levels.py -k "TestTargetSpacing or TestExitPlanCopy or TestAtrRungs or TestAtrRungsDisplayOnly or TestAtrLevelsCopy or TestPlanGapEdges or TestNextLevelsLadder or TestSessionPicks" tests/lib/test_session_levels_rules.py tests/lib/test_movement_statement_level_basis.py tests/gcp/test_signal_monitor_level_state.py tests/gcp/test_signal_monitor_level_refresh.py tests/gcp/test_premarket_playbook_resolver.py tests/gcp/test_level_params_consumers.py tests/gcp/test_premarket_brief_late_slot.py tests/gcp/test_brief_channel_routing.py tests/api/test_movement_statement_exit_plan.py -q` (expect passed; a class name that does not exist on the base is replaced by the base's name and noted).
- [ ] **Step 4: Run:** `make test` (expect no failure the base does not have), and `git diff <base> --stat -- tests/ | cat`: the only existing test files with removed lines are `tests/lib/test_level_params_loader.py` (the key-set pin) and `tests/meta/test_level_rule_version_readers.py` (the two tables).
- [ ] **Step 5: Commit:** `test(strat): reach the mark walk and waypoints from the no-numbers walk`

### Task 13: The Experiment's driver, committed and tested

Spec: Experiment ("Method", "Arm A is checked twice", "Reported, per arm"); CLAUDE.md 3.6. Advances done_when[9].

**Files:**
- Create: `scripts/analysis/atr_marks_experiment.py`, `tests/scripts/test_atr_marks_experiment.py`, `tests/fixtures/atr_marks_spike_2026-11-16/report_v1_side.txt`, `report_followup.txt`

**Interfaces:**
- Consumes: `gcp.premarket_brief.main`; `gcp.premarket_playbook_resolver.plan_inputs`, `resolve_plan`, `PlanOutcome`; `lib.strat_levels.SessionLevels`, `parse_level_basis`; `lib.eastern_time.session_close`, `sessions_between`; `gcp.fetchers.export_intraday_bars.read_bars`; `gcp.database.get_engine`.
- Produces:
  - `ARMS = {'A': ((), 3), 'Q': ((0.25, 0.5, 0.75, 1.0), 4), 'Q3': ((0.25, 0.5, 0.75), 3)}`; `LEFT_OUT = {('SPY', '2025-04-09'), ('IWM', '2026-06-26')}`; `LOCAL_SQL_NAME = 'local-experiment-not-cloud'`.
  - `require_local_db() -> None`: raises unless `DB_HOST` is `127.0.0.1` or `localhost`, `CLOUD_SQL_CONNECTION_NAME == LOCAL_SQL_NAME` and `BRIEF_LLM_DISABLE == '1'`. Every subcommand calls it first. The dummy connection name is needed because `lib.data_loader._cloud_sql_active` (`:146-148`) looks at that variable alone, while `gcp.database._direct_db_url` (`:70-89`) lets `DB_HOST` win for the engine.
  - `arm_policy_sql(arm: str) -> Optional[str]`: `None` for A; for Q and Q3 the Design 8 `INSERT` with `effective_from` `'2015-01-03'` (one day after the seed, so it is in force for every replayed session and does not collide with the seeded key), the leg row only for Q.
  - `pick_trade(calls: PlanOutcome, puts: PlanOutcome) -> tuple[Optional[str], Optional[str]]`: `(side, None)` or `(None, reason)`. The rule that matched +176.75 R over 3,463 trades in the spike (its `score_arms.py` and `report.py`, variant `side`): each side is judged alone; a side whose own first bar opens at or beyond its trigger is `opened_through` and never the pick; if one side is `entered` it is the trade; if both are, the earlier `fill_ts`; equal `fill_ts` is `(None, 'same_bar_tie')`; none entered is `(None, 'no_entry')`. The stricter variant, no trade on a day when either side opened through, gave 3,453 trades and +178.6 R and did not match.
  - subcommands `load` (daily export and bucket bars into the template database), `placeholder`, `replay`, `score`, `report`, `baseline` and `compare` (the last two below). `score` reads each arm's database, cuts bars at `session_close` as `resolve_one` does, and writes one row a trade and arm: `ticker, date, arm, side, trigger, stop, fill, fill_ts, atr, r, exit, mfe_atr, targets, n_targets, legs, rule_version, on_level, past_level, waypoints`. It asserts the three arms pick the same ticker-days with equal trigger, stop and fill, and that every Q and Q3 basis has `rule_version` `'feat-strat-001.v6'` and every A basis the level rule's.
  - `report(csv) -> str`: the eleven measures of the spec's Reported list, each arm, with the spike's figure beside each total and reach share it has one for, parsed from the two fixture files. The range is `numpy.random.default_rng(7)`, whole days, 2,000 draws, percentiles 5 and 95. A measure the spike did not produce prints `spike: not produced`.
  - Measures 5 to 8 use the stored reach rule and no bar: a mark or waypoint is reached when the trade's `mfe_atr` is at least its distance in ATR. Measures 4 and 9 use the exit labels of `resolve_plan`.
  - **The baseline-only mode** (done_when[9] (a)): subcommand `baseline FROM TO --days-out PATH`. It scores arm A alone from the one database `DB_NAME` names: per ticker-day, `plan_inputs` and `resolve_plan` on the stored basis for both sides, then `pick_trade`, and writes one row a ticker-day: `ticker, date, calls_trigger, puts_trigger, calls_stop, puts_stop, side, reason, r, exit, targets` (a trigger or stop the basis lacks is empty, never 0). It prints the total R, the trade count, the per-ticker totals, `git -C <working directory> rev-parse HEAD`, and `__file__` of `gcp.premarket_brief`, `gcp.premarket_playbook_resolver` and `lib.strat_levels` as imported, and raises before scoring if any of the three files is not under the working directory, so a run whose imports resolved to the head cannot pass as the harness check. It needs neither `mfe_atr` nor the Q and Q3 databases: it reads no `mfe_atr`, `t4_hit_ts` or rule version and opens no database but `DB_NAME`'s.
  - **Runs as a file against 97190ef41.** Task 14 Step 4 runs `python3 <head>/scripts/analysis/atr_marks_experiment.py ...` with the working directory and `PYTHONPATH` set to a detached worktree of 97190ef41, so every `gcp` and `lib` import is that commit's. So `require_local_db`, `load`, `placeholder`, `replay` and `baseline` import at module level only names 97190ef41 has, all found there (run 2026-11-17): `gcp.premarket_brief.main`, `gcp.premarket_playbook_resolver.plan_inputs`, `resolve_plan`, `PlanOutcome`, `lib.strat_levels.SessionLevels`, `parse_level_basis`, `price_cents`, `lib.eastern_time.session_close`, `sessions_between`, `gcp.fetchers.export_intraday_bars.read_bars`, `gcp.database.get_engine`; `plan_inputs(side, row, basis, policy_fn)` and `resolve_plan(direction, plan, bars)` have the same signatures there as on main f8f6c6996. Nothing is imported from `scripts`, which under the worktree is that commit's package. What only the head has (the marks columns, `mfe_atr`, the v6 check) is read inside `score` and `report`.
  - `score` also writes `--days-out PATH` for arm A, in the `baseline` shape, from the head's `arm_a`.
  - `trigger_changed(base_days, head_days) -> dict` and subcommand `compare BASE_DAYS HEAD_DAYS`: the measure r2 names, **trigger-changed ticker-days**. A ticker-day is trigger-changed when its calls trigger or its puts trigger differs to the cent (`price_cents`) between the two files, or exists in one file only (one side's trigger present in one file and empty in the other, or the ticker-day in one file only). It prints the count; arm A's R and trade count in each run on those ticker-days and on the rest; and every ticker-day of the rest whose R differs between the runs, with both runs' side, stop, targets, exit and R, so its cause can be written beside it in the PR body.

- [ ] **Step 1: Copy the spike's reports** verbatim from the local branch `spike/atr-quarter-targets` (21612e698, `docs/superpowers/spikes/2026-11-16-atr-quarter-targets/report.txt` and `report_followup.txt`; never pushed, so they may be gone). If they are gone, write the two fixture files from the spec's "Result as run" quotations only, and say in the PR body that they are the spec's quotations and not the files.
- [ ] **Step 2: Write the failing tests:**
  - `test_refuses_a_database_that_is_not_local` (three environments: a remote host, a real-looking connection name, the model switch unset).
  - `test_pick_trade` (on `PlanOutcome` literals): one entered; both entered, calls earlier; both entered, same `fill_ts`; calls `opened_through` and puts `entered` gives `('puts', None)`; none entered.
  - `test_arm_policy_sql`: A is `None`; Q inserts both keys dated 2015-01-03; Q3 inserts the marks key only.
  - `test_the_driver_walks_no_bars_and_replaces_no_plan` (by `ast` over the driver): no call named `replace`; no keyword argument named `targets` or `legs`; no attribute named `iterrows` or `itertuples` applied to a bars frame; the names `resolve_plan`, `plan_inputs` and `main` are imported from the two production modules.
  - `test_spike_figures_parse`: from the fixture, A is +176.75 over 3,463 trades, Q +152.49, Q3 +129.72, Q minus A -24.3 with range (-71.8, +21.8), arm Q's T1 share 52.3%.
  - `test_the_range_is_seeded`: two calls on a 30-day frame give the same pair.
  - `test_reach_share_uses_mfe_atr`: a five-trade frame with `mfe_atr` 0.1, 0.3, 0.5, 0.8, 1.2: marks 0.25, 0.5, 0.75, 1.0 give 4, 3, 2 and 1 of 5.
  - `test_baseline_imports_only_what_97190ef41_has` (by `ast` over the driver): the module-level imports name only the modules and names listed above, typed into the test as a literal set, and none is from `scripts`.
  - `test_baseline_reads_no_new_field` (by `ast` over `baseline` and every function of the module it calls): no attribute, key or string `mfe_atr`, `t4_hit_ts` or `rule_version`, and no database name but `DB_NAME`'s.
  - `test_baseline_prints_sha_and_module_paths` (with `subprocess.run`, the three modules' `__file__` and the scorer monkeypatched): the output holds the sha, the three paths, the total and the trade count; with one module path outside the working directory it raises before scoring.
  - `test_trigger_changed` on two small day files: a calls trigger one cent apart, a puts trigger in one file only, a ticker-day in one file only, and an unchanged day whose R differs: the count is 3, each partition's R and trade count in each run are the frame's, and the unchanged day is the one listed.
- [ ] **Step 3: Run:** `python3 -m pytest tests/scripts/test_atr_marks_experiment.py -q` (expect FAIL: no module); implement; run again (expect PASS).
- [ ] **Step 4: Render step, then commit:** `feat(strat): add the ATR marks experiment driver`

### Task 14: The Experiment, through the production paths, into local databases

Spec: Experiment ("Method", "Arm A is checked twice"); done_when "Experiment through the production paths". Closes done_when[9] when both arm A checks of Step 4 hold. Nothing here writes to production and no production policy row changes.

- [ ] **Step 1: The inputs. Ask the owner once before running** (one read-only dispatch and one bucket download; no `--commit`):
  - `./scripts/db_query_cr.sh -q "SELECT d.*, d.pre_filter_params::text AS pfp_text FROM market_data_daily d WHERE ticker IN ('SPY','QQQ','IWM') ORDER BY ticker, date; SELECT c.* FROM ticker_calibration c WHERE ticker IN ('SPY','QQQ','IWM') ORDER BY 1"` (the spike's statements; 7,956 and 13 rows on 2026-11-16), saved from the execution's `result_001.csv` and `result_002.csv`. Whether the brief needs `ticker_calibration` was not checked for this plan; the spike loaded it.
  - the 1-minute bars: `gsutil -m cp -r gs://<GCS_BUCKET>/intraday-bars/v1/1min/{SPY,QQQ,IWM} <dir>` for 2015-01 to 2026-11, read by `read_bars`. If a month is missing, stop and report; do not refetch from the vendor.
  Record the execution id and each file's sha256.
- [ ] **Step 2: The template database and the three arms.** Postgres 15 as CI starts it; `psql -v ON_ERROR_STOP=1 -f gcp/schema.sql` from the PR head into database `arm_template`; then, with `DB_HOST=127.0.0.1 CLOUD_SQL_CONNECTION_NAME=local-experiment-not-cloud BRIEF_LLM_DISABLE=1 BRIEF_AMC_REACTIONS=0` and `DISCORD_WEBHOOK_URL`, the model keys and `CLOUDSDK_AUTH_ACCESS_TOKEN` unset:

```bash
python3 -m scripts.analysis.atr_marks_experiment load <export dir> <bars dir>
python3 -m gcp.calibrate_level_params --history 2022-01-03 2026-11-10 --tickers SPY,QQQ,IWM
python3 -m scripts.analysis.atr_marks_experiment placeholder 2022-01-03 2026-11-10
python3 -m gcp.fetchers.fetch_market_data --recompute-premarket --from 2022-01-03 --to 2026-11-10 --commit --report-dir <dir>
psql -c "CREATE DATABASE arm_a TEMPLATE arm_template" -c "CREATE DATABASE arm_q TEMPLATE arm_template" -c "CREATE DATABASE arm_q3 TEMPLATE arm_template"
python3 -m scripts.analysis.atr_marks_experiment replay A 2022-01-03 2026-11-10    # DB_NAME=arm_a
python3 -m scripts.analysis.atr_marks_experiment replay Q 2022-01-03 2026-11-10    # DB_NAME=arm_q, after arm_policy_sql('Q')
python3 -m scripts.analysis.atr_marks_experiment replay Q3 2022-01-03 2026-11-10   # DB_NAME=arm_q3
```

  `replay` sets `BRIEF_TICKERS=SPY,QQQ,IWM` and `BRIEF_AS_OF` per session and calls `gcp.premarket_brief.main([])`, nothing else. Check the flags of the two production tools against their `--help` on the base before running. Expect: the calibration exits 0 for three tickers; the recompute logs `candidates=3657` (the spike's count) with `refused=0`; each replay ends with no failure and one `premarket_analysis` row a ticker-session (3,657). Paste each.
  **Two known limits of this reproduction, stated in the PR body as limits, not hidden:**
  1. *The placeholder.* `--recompute-premarket` selects only sessions that already hold a premarket value (`PREMARKET_ROWS_SQL`, `gcp/fetchers/fetch_market_data.py:1323-1332`, main), and the daily export holds one for only the recent sessions (the spike's first run found 438 candidates, its second 3,657). The `placeholder` subcommand writes, in the local template only, a sentinel no real session can hold (`pre_vwap = -1`) on each session of the range that has none, so the tool selects every session. After the recompute the subcommand's check must find no row still holding the sentinel; one left means that session was refused and it is listed, not traded. The spike's own placeholder statement is not in its scripts or notes (searched), so this one is this plan's.
  2. *The premarket window.* The recompute reads the 04:00 to 09:30 ET bars (`gcp/fetchers/fetch_market_data.py:384`, `:573`, main), while the live brief is built from the 08:20 ET refresh (as relayed in the spec; not read here). The replay's triggers know up to 70 minutes of premarket the live brief does not. Every arm shares them.
- [ ] **Step 3: Score the head.** `python3 -m scripts.analysis.atr_marks_experiment score 2022-01-03 2026-11-10 --out atr_marks_arms.csv --days-out arm_a_head_days.csv`. Run `EXPLAIN (ANALYZE, BUFFERS)` of `PLAN_REACH_HISTORY_SQL` on `arm_q` for 2026-11-10 and paste it. `report` is not run, and no figure of any arm is read, until Step 4's check (a) holds.
- [ ] **Step 4: Gate: arm A is checked twice, and both checks are required** (r2, Experiment, "Arm A is checked twice"). No arm, the head's arm A included, is read if (a) fails.
  - **(a) The harness check.** The committed driver, run as a file from the PR head, against 97190ef41's production modules and a local database built from that commit's schema and prepared by that commit's tools from the same exported inputs as Steps 1 and 2. Same environment as Step 2, never production, no production write (`require_local_db` first in every subcommand):

```bash
git worktree add --detach <wt> 97190ef41
git -C <wt> rev-parse HEAD     # expect 97190ef4120085207f988a7ee942317e2a1b5fd3
psql -c "CREATE DATABASE arm_base"
psql -d arm_base -v ON_ERROR_STOP=1 -f <wt>/gcp/schema.sql
cd <wt> && export PYTHONPATH=<wt> DB_NAME=arm_base
python3 <head>/scripts/analysis/atr_marks_experiment.py load <export dir> <bars dir>
python3 -m gcp.calibrate_level_params --history 2022-01-03 2026-11-10 --tickers SPY,QQQ,IWM
python3 <head>/scripts/analysis/atr_marks_experiment.py placeholder 2022-01-03 2026-11-10
python3 -m gcp.fetchers.fetch_market_data --recompute-premarket --from 2022-01-03 --to 2026-11-10 --commit --report-dir <dir>
python3 <head>/scripts/analysis/atr_marks_experiment.py replay A 2022-01-03 2026-11-10
python3 <head>/scripts/analysis/atr_marks_experiment.py baseline 2022-01-03 2026-11-10 --days-out arm_a_base_days.csv
```

  `python3 -m` from the worktree runs that commit's calibration and recompute; check their flags against `--help` there, as Step 2 does on the head. The `--commit` of the recompute writes to the local `arm_base` only. **Pass:** the total is within 0.1 R of +176.8 over 3,463 trades (the gap-edges spec's figure; the spike gave +176.75). Paste into the PR body the total, the trade count, the per-ticker totals beside the gap-edges spec's (+64.2, +114.0, -1.4), the worktree's HEAD sha and the three module file paths the run printed. This proves the harness and its data, not the new code. **If it fails, stop:** post those figures and nothing of any arm. A cause found in the driver is fixed there (Task 13's tests first) and (a) is run again; a cause found in the inputs is fixed by a fresh Step 1 export, on the owner's yes, and (a) is run again. If no cause is found, the search is posted on the PR, done_when[9] stays unticked and the PR stays a draft. The figure is r2's pin and is not moved from this branch.
  - **(b) Arm A on the head.** From Step 3: arm A is whatever the head's rules give, with no pinned total. Report its total and trade count beside the spike's +176.75 R over 3,463 trades. Then `python3 -m scripts.analysis.atr_marks_experiment compare arm_a_base_days.csv arm_a_head_days.csv`, and in the PR body attribute the difference to the premarket rule changes merged since 97190ef41 (the brief build, PR #2010, and the prior-close print rule, `docs/superpowers/specs/2026-11-16-feat-playbook-001-prior-close-prints.md`) by the one measure r2 names, **trigger-changed ticker-days**: the count of ticker-days on which the calls trigger or the puts trigger of the head's basis differs to the cent from the basis of the (a) run or exists in one run only; arm A's R and trade count in each run on those ticker-days and on the rest; and every ticker-day of the rest whose arm A R differs between the two runs, listed with its cause.
  - **Then the other arms.** Only once (a) holds: `python3 -m scripts.analysis.atr_marks_experiment report atr_marks_arms.csv`. Arms Q and Q3 are read against the head's arm A, never against the (a) run's.
- [ ] **Step 5: The PR body shows** Step 4's (a) and (b) as above, then, per arm: the eleven measures; beside them the spike's figures (A +176.75 over 3,463; Q +152.49; Q3 +129.72; Q minus A -24.3, range -71.8 to +21.8; Q3 minus A -47.0, range -109.1 to +12.4; arm Q's T1 to T4 shares 52.3%, 27.1%, 12.8%, 6.2%), never in place of the new ones; every difference in a total, a trade count or a reach share with its explanation; the five measures the spike did not produce (5, 6, 7, 8 at `level_cluster_atr`, 9's average win and loss); the driver's and the csv's sha256; the commands above; the two limits.
- [ ] **Step 6: Which arm may be proposed** (spec, "What keeps today's plan"): an arm whose 90% range against A lies wholly below zero overall, or for two of the three tickers, is reported as failing, and the swap rows are not proposed for it without the owner's explicit decision recorded on the PR. An arm whose range spans zero is put to the owner as "no worse, by this test". The PR proposes; it changes no production row.

### Task 15: Close: product record, site note and the gate

Spec: "Source identity and close-out"; done_when "Source identity", and the last item. Closes done_when[10] and done_when[11] (but for the owner's steps). Once the site-note steps start, no file under `gcp/`, `lib/`, `scripts/` or `tests/` changes without redoing them.

- [ ] Push with `git push -u origin feature/feat-strat-001-atr-quarter-targets` and open a **draft** PR. **Do not enable auto-merge.** Body: the spec's and this plan's paths; the 12 done_when items as `- [ ]` lines; `Red then green`; the Capacity section; Task 1's precondition outputs and line table; which version case held (`LEVEL_RULE_VERSION` and `PICK_RULE_VERSIONS` on the merge base, and the marks version `feat-strat-001.v6`); Task 14's results; the choices this plan made; and the sentence "Merging applies gcp/schema.sql to production through apply-schema-on-change; merge only on the owner's recorded yes".
- [ ] Set `pr:` in this plan to the PR's number.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, the `### FEAT-STRAT-001` record (`:233`, main): Status and Last reviewed for this PR (seeded rows change no target; implementation under review, not deployed).
- [ ] `docs/product/12-PR-ISSUE-TRACEABILITY.md`, `### FEAT-STRAT-001` (`:547`, main): add the PR to its lineage, naming spec PR #2019 (r2, which superseded r1 of PR #2013). Commit both and the plan: `docs(product): record the ATR mark targets under FEAT-STRAT-001`.
- [ ] Site note, step 1: with a clean tree, `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`; copy its `source_identity_sha256`.
- [ ] Site note, step 2: in `docs/product/03-SITE-TRACEABILITY.md`, the `| FEAT-STRAT-001 | DASHBOARD-01 |` row (`:1350`, main) and no other byte: the new hash, then this change's prose (backend source and local tests only: the brief's plan block can print ATR mark targets, waypoints and reach counts; targets unchanged under the seeded rows; tests named), then ` Earlier: ` and the earlier prose unchanged. Commit: `docs(site): note the ATR mark targets on DASHBOARD-01`.
- [ ] Site note, steps 3 and 4: run `produce` again and commit `docs(site): regenerate the source snapshot`; then `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json` with the default ceilings (expect exit 0). If it refuses on size, follow Global Constraints: stop, post the measured size, ask the owner. If `origin/main` moved, merge it into the branch (never a rebase of a pushed branch), re-render and redo the four steps.
- [ ] Render step once more and `python3 -m pytest tests/scripts/test_check_generated_docs.py tests/meta/test_model_registry_consistency.py -q` (expect all pass).
- [ ] Docs audit: `python3 scripts/maintenance/docs_audit.py` on the branch and on a detached `origin/main` worktree; the branch reports nothing `main` does not.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` (expect exit 0).
- [ ] Push; tick each done_when box with its evidence (test names, execution ids, sha256 prefixes; no promise); only then mark the PR ready. done_when[9] is ticked only as Task 14 Step 4 allows. Gate files are not touched, so no red-team pass is owed.
- [ ] **Ask the owner once before merging:** "Merging applies the two seeded policy rows and the eight nullable columns to production through apply-schema-on-change. The seeded rows change no target. Yes?" Merge only on that yes, recorded on the PR. Never by auto-merge.

## Close-out (not tasks; the owner's steps)

From the spec's "Source identity and close-out" and Decisions 7, 8, 10 and 11. None is done by the implementer without the owner's own yes, read-only checks included, and each yes is recorded separately on the PR or a new issue.

1. **First yes (the merge):** the two seeded rows and the eight columns reach production. Confirm by one read that the rows exist and the columns are present.
2. **Deploy** the brief and the resolver, after step 1's read. Confirm the next live brief's targets and text equal what the previous image gives for the same basis (the seeded rows change none), that re-resolving the latest sessions fills the two reach columns for entered sides, and read `EXPLAIN (ANALYZE, BUFFERS)` of the reach query on production once marks-version rows exist.
3. **Before the swap, under their own work:** the insight judges reward on the average of the plan's targets (the conviction spec, FEAT-INSIGHT-001), `gcp/insight_discord_push.py:221` prints four targets, and solyra's two target fields and the chart's three lines take four (Decisions 7 and 8). Or the owner accepts, when giving the second yes, a warning on nearly every plan.
4. **Second yes, on the Experiment's results:** the Design 8 swap rows go into `gcp/schema.sql` through their own small PR (Decision 10), dated by the owner, both rows on one date, never auto-merged; its merge applies them.
5. **The dry-run sample** (Decision 11): five stored sessions by the deployed job with `BRIEF_NO_PERSIST=true` for arm A, and one dry run of the first session the swap rows cover; each spends a brief's model calls and is approved when it is run. Then confirm on the next live brief that each side prints its targets at the marks and records `feat-strat-001.v6`.
6. On a `docs/` branch after the merge: the DASHBOARD-01 note and this plan's `status: done`. The three other approved FEAT-STRAT-001 specs that describe the level rule are updated after the Experiment and the swap, as the owner said (spec Conflicts, item 1).
