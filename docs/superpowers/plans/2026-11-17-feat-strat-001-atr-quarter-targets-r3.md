---
feat_id: FEAT-STRAT-001
spec: docs/superpowers/specs/2026-11-17-feat-strat-001-atr-quarter-targets-r3.md
branch: feature/feat-strat-001-atr-quarter-targets-r3
pr: null
status: ready
---

# The exit plan sells a quarter at 25, 50, 75 and 100 percent of ATR from the entry, thirds leave everything, and history is rebuilt on the quarters: implementation plan (r3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the order of the spec's frontmatter, [0] (Policy rows) to [14] (catalog, gate and the owner's yeses). The map below names each.

**Goal:** One policy row, seeded with the four quarters for every date, makes every side with a trigger take its targets at the trigger plus or minus mark x ATR, sell a quarter at each, print the session's levels between the targets as waypoints with "reached k of n" counts read from `plan_excursions`, and record the marks version `feat-strat-001.v6`. The fourth target is stored in `t1..t4` and scored; the alerts' T1, the put re-anchor and the movement statement read the quarters; thirds leave the analysis code and the docs; and the tooling that rebuilds every stored brief row on the quarters ships tested, with no production write by this PR. The Experiment is run again on the marks builder itself.

**Architecture:** One builder, `lib.strat_levels.build_session_levels`. `_pick_side` keeps the trigger and the stop exactly as today and asks a new helper, `plan_target_rule(version)`, which rule picks the targets: the level walk (`_plan_targets`, unchanged, for a stored level-rule basis and for arm A's local empty list) or a new mark walk (`_plan_mark_targets`) followed by a waypoint builder (`_plan_waypoints`). A marks side's `gate_targets` are its targets. A new `rebuild_on_marks(basis, marks)` runs only the mark walk and the waypoint builder on a stored basis's recorded trigger, stop, ATR and levels; `SessionLevels.from_basis` returns it for a basis that records `rebuilt_from_rule_version`. The counts come from the hit-rates build's `lib.target_reach` table, which `format_levels_for_brief` already carries. `scripts/maintenance/rebuild_quarter_history.py` holds the six modes of Design 12 over a new `premarket_targets_archive` table.

**Tech Stack:** Python, pandas, numpy, SQLAlchemy `text()` through `gcp.database`, argparse, pytest (`monkeypatch`, the SQLite `ParamsDb` of `tests/lib/level_params_fixtures.py`), Postgres 15 (`pgvector/pgvector:pg15`) for `tests/integration/` and for the local copies of the Experiment.

**Spec:** docs/superpowers/specs/2026-11-17-feat-strat-001-atr-quarter-targets-r3.md (approved, stocks #2053, merged to `main` at d35d9ce2 on 2026-11-17). It supersedes r2, whose plan (`docs/superpowers/plans/2026-11-16-feat-strat-001-atr-quarter-targets.md`, branch `feature/feat-strat-001-atr-quarter-targets`) cannot be re-pointed: `plan_stays_bound` refuses a plan already on the base that changes its `spec` ("a plan binds one spec", `scripts/gate/spec_gate.py:1684`), and `check_changed_plans` refuses any edit from another branch but the close to `done` after its PR merged (`:2127-2129`), and it has no PR. So, as the hit-rates r2 plan did (#2056), this plan names a new branch, and the r2 plan stays on main as the record, authorizing nothing: the gate refuses every commit on its branch because its spec is superseded (`:2515-2516`). No code was written on r2.

## Order and bases

1. **The hit-rates build first** (spec Decision 9 as widened by r3, Conflicts item 9; done_when[9]). Build PR #2062, branch `feature/feat-strat-001-target-hit-rates-r2`, head c740ba95 when this plan was written, still a draft. It brings `plan_excursions`, `entry_rule_version`, `lib/target_reach.py`, the reach argument of `format_levels_for_brief`, `plan_excursion` and the `target_reach_rate` policy row. **The code branch of this plan opens only after #2062 has merged.** Task 1 checks it.
2. **Line numbers.** `lib/strat_levels.py`, `gcp/premarket_playbook_resolver.py`, `gcp/premarket_brief.py` and `gcp/schema.sql` are cited at c740ba95 and marked `@2062`, because #2062 moves them; every other file is cited at `origin/main` d35d9ce2. Code-wise d35d9ce2 equals 128ebdfd (d35d9ce2 adds only the spec), and c740ba95 has 128ebdfd merged. Every file:line is re-read on the merge base when the code branch opens (Task 1 Step 2).
3. **The rule versions on the base.** `LEVEL_RULE_VERSION = 'feat-strat-001.v5'` and `PICK_RULE_VERSIONS = (LEVEL_RULE_V3, LEVEL_RULE_V4, LEVEL_RULE_VERSION)` (`lib/strat_levels.py:1586-1587` @2062), `is_current_pick_rule` (`:1590`), `entry_rule_version` (`:1597`, returns `version` for every pick-rule version and None otherwise). So the marks version is `feat-strat-001.v6` (Design 6).

## Scope

One plan, one branch, one PR, 19 tasks. Every done_when item, [0] to [14], is in it; nothing is split off. Design 13 (the drop of the thirds columns and policy rows, and of the level walk) is not in this PR; it gets a spec of its own once verify reads clean in production (spec Design 13, What changed item 13).

Where the plan cannot close an item alone, it says so in the task:

- **done_when[8] and [12] need production reads.** The PR body shows `count` read from production (read-only), and the Experiment needs exported inputs. Each read is asked of the owner once before it runs. On PR #2062 the owner's account asked for no new vendor fetch, production query or history dispatch, and the offline inputs for a basis rebuild (premarket snapshots, `ticker_level_params`, the premarket cutoffs and filter parameters) are still being located there. Tasks 17 and 18 use whatever authorized input path that work settles; until one exists, done_when[12] stays unticked and the PR stays a draft.
- **done_when[14]:** the merge, the deploy and each Design 12 mode that writes production are the owner's steps (Close-out).

## Merge is the swap, and a production schema change

`gcp/cloudbuild/apply-schema-cloudbuild.yaml:1-5`: the `apply-schema-on-change` trigger fires on a push to main touching `gcp/schema.sql` and applies it (read; the live trigger was not read). This PR adds one policy row seeded with the quarters for every date, nine nullable columns and the `premarket_targets_archive` table. So its merge changes production, and from the deploy every new brief prints the quarters.

- **Auto-merge is never enabled on the implementation PR.** Its merge is asked of the owner once, after the Experiment is shown in its body, and the yes is recorded on the PR (done_when[14]).
- The merge also waits for the under 1.5R rule (spec Decision 7): the conviction spec's change to N2 deployed, or the owner accepting a warning on nearly every plan when giving the yes.
- Rows before code: the merge applies the row before any deploy. A job still on the old image reads the new key as a ticker key with status `params_unavailable`, records it and ignores it (`lib/strat_levels.py:1454-1496` on 97190ef4, per the spec; re-read in Task 1).
- Deploy order (Design 11): every reader of a stored `level_basis` (the playbook resolver, the signal monitor, the API, the insight pipeline) is deployed from the implementation before or with the brief job, because an image that does not list v6 in `PICK_RULE_VERSIONS` rebuilds a v6 basis under the v2 rule (`lib/strat_levels.py:2118` @2062).

## Global Constraints

- Base: `origin/main` after #2062 has merged, re-read in Task 1. Branch `feature/feat-strat-001-atr-quarter-targets-r3`. This plan is committed alone on `docs/plan-feat-strat-001-atr-quarter-targets-r3` and merged before the code branch opens. Merge `origin/main` into the branch when it moves; never rebase a pushed branch.
- The owner's rule, exact values: marks `[0.25, 0.5, 0.75, 1.0]` of the basis ATR from the entry trigger, calls above and puts below, a quarter sold at each, levels printed as waypoints, no snapping. IWM 2026-11-16, ATR 4.874951, offsets 122, 244, 366 and 487 cents: calls 280.14, 281.36, 282.58, 283.79 from 278.92; puts 274.64, 273.42, 272.20, 270.99 from 275.86.
- Policy: `gcp/schema.sql` seeds exactly one new `level_param_policy` row, `plan_target_marks_atr`, method `policy`, extra `{"marks": [0.25, 0.5, 0.75, 1.0]}`, `effective_from` `'2015-01-02'`, under `ON CONFLICT (param_key, effective_from) DO NOTHING`. No existing row changes. No `ladder_history_sessions` key and no swap rows (Design 8). `exit_legs` `{"legs": 3}` and `plan_target_level_types` are read only for a level-rule basis.
- Rule versions: `LEVEL_RULE_MARKS = 'feat-strat-001.v6'`, named once, joins `PICK_RULE_VERSIONS`. `LEVEL_RULE_VERSION` stays `'feat-strat-001.v5'`. No file under `lib/`, `gcp/` or `platform/` compares a value with a rule version constant outside `is_current_pick_rule`, `entry_rule_version`, `plan_target_rule` and the population lines of `lib/movement_statement.py` (done_when[4]; the meta test `tests/meta/test_level_rule_version_readers.py`).
- **The version of a fresh build** (a silence of the spec this plan fills, as the r2 plan did; the spec's r2 notes name it a silence the plan may fill): the marks row ok with a non-empty list records v6; ok with an empty list (arm A's local copy only) records `LEVEL_RULE_VERSION`; missing or not ok records v6, and the mark walk publishes no target with the row's status. A row that cannot be read never falls back to the level walk (CLAUDE.md 3.7).
- **A marks side's leg count is its number of marks** (Design 2); `exit_legs` is not read for it. So `resolve_plan`'s `targets[:plan.legs]` (`gcp/premarket_playbook_resolver.py:583` @2062) never cuts a target.
- No number and no name in the level code (done_when[10]). The marks, the leg count and the reach window are read only from `LevelParams` and `level_param_policy`; the percent and share texts are formatted from those values. On the `build_session_levels` walk no numeric literal other than those `tests/lib/test_level_params_structure.py` allows and no new numeric module constant.
- Distances are compared in cents through `price_cents` (`lib/strat_levels.py:921`). An offset is rounded to the cent once and added to the trigger's cents.
- No silent fallback (CLAUDE.md 3.7). A key that is not ok publishes no target and says which status; a failed reach read raises, and the brief prints the hit-rates spec's unavailable line; a missing value is `None` and prints as words, never 0. `no history yet` is printed only for a ticker with zero rows.
- Exact strings. From Design 7 (the plan block of a marks side, after the stop line):
  - `    Reached before the stop: {ticker} trades {first} to {last} ({n})`
  - `    Targets at {p1}, {p2}, ... and {pn} of ATR({n}) = {atr} past {trigger}, sell {1/legs} at each`
  - `      {price or "near to far"} ({names}): level on the way, {d} ATR past the trigger, {count}`
  - `    T{i}: {price} ({p}% of ATR[, on {names}: the stronger case]), sell {1/legs}, {count}`
  - the last target: `sell the last {1/legs}, or hold to the close or the stop`
  - `      {price} ({names}): level beyond T{last}, {d} ATR past the trigger, {count}`
  - not ok: `    Targets unavailable ({status}): no exit plan for this side.` (`lib/strat_levels.py:3374` @2062)

  `{count}` is `lib.target_reach`'s text, as the hit-rates build produces it: `reached {k} of {n} ({p}%)` at or above `min_sample`, `reached {k} of {n}` below it, `no history yet` with no rows, never `0 of 0`. No `Skipped, closer than` line and no `ATR levels` line for a marks side (Decision 6). The After block of Design 7 is the golden, character for character.
- 1-minute bars are as-traded and come only from `market_data_intraday`. The rebuild's resolve mode reads nothing else. The Experiment reads them from the bucket export of that table (`gcp/fetchers/export_intraday_bars.py`, which only reads `market_data_intraday`), never from a vendor.
- R is the stock's move after the fill in stop distances; distances are in ATR. No copy, comment, log line or test name speaks of money or of trading costs.
- Unchanged (done_when[11]): the trigger and stop rule, the opened-through rule, the entry cutoff, the ATR rungs and their thinning, the NEXT LEVELS Calls and Puts lines, PMG zones, the signal monitor's fire decisions apart from the T1 its level state reads, persona plans, the CALL/PUT pick, and for a basis built under a local empty marks list the level rule's spaced walk, thirds, gap-edge targets, gate targets and the `t1..t3` columns.
- Production access. Tasks 2 to 17 touch no production system. Each step that does is marked **Ask the owner once before running** and is never assumed approved: Task 1 Step 4 (export of three stored bases), Task 15 Step 6 (`count` read-only), Task 18 Step 1 (the Experiment's inputs). No `--commit`, deploy, schema apply, policy change, rebuild mode that writes, or alerts replay with `--persist` is run from this branch.
- Replays go through production code (CLAUDE.md 3.5, 3.6): bases are built by `gcp.premarket_brief.main` with `BRIEF_AS_OF`, scored by `gcp.premarket_playbook_resolver.plan_inputs` and `resolve_plan`, and measured by `plan_excursion`. The Experiment's driver walks no bar, computes no indicator or level, and never replaces `targets` or `legs` on a `PlanInputs`.
- Tests are hermetic in the Run Tests job (no `origin/main` in its checkout, no git command in a test). Postgres cases live in `tests/integration/`, which the `integration-tests` job runs on a database loaded from `gcp/schema.sql` (`.github/workflows/backtest-pipeline.yml:90-163`).
- `.gitignore` ignores `*.csv` (`:109`): prefer JSON or `.txt` fixtures; a CSV fixture is added with `git add -f`.
- **The render step** ends every commit that moves lines in `gcp/`, `lib/` or `scripts/`: `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md README.md docs/product/infrastructure/05-e-API.md`, then `python3 scripts/maintenance/check_generated_docs.py --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json` (exit 0). Generated docs change only inside their inventory blocks and the renderer's own prose counts (REQ-GOV-004); the "Strat and signals" group row is never hand-edited.
- `tests/lib/test_movement_statement.py` patches `gcp.research.strat_engine.strat_pred_serve`, which CI runs in the `research-test` job with `requirements-research.txt` (`.github/workflows/backtest-pipeline.yml:56-83`). Run it with that stack and report both jobs; a local skip is not a pass.
- Commits: conventional `type(scope): description`, imperative. The PR opens as a draft and stays one until every done_when line in its body is ticked with evidence. Every new test has a red then green record in the PR body.
- No em or en dashes in code comments, copy or docs written for this change.

### Capacity (CLAUDE.md Rule 0; spec Design 10 and Design 12), copied into the PR body

- **Volume:** one policy row; nine nullable columns; each new `level_basis` gains a waypoint list of about 3 to 10 entries a side (IWM 2026-11-16: 5 and 3) and loses the skipped list. `premarket_targets_archive`: `count`'s rows times its average `pg_column_size`, shown before archive runs (about 3,700 `premarket_analysis` rows plus the history rows, by the spec's estimate).
- **Velocity:** no new query in the brief: the counts come from the hit-rates build's one read a run (about 3,500 rows for three tickers). No new query in the resolver. Rebuild tooling: archive one `INSERT ... SELECT` per table and ticker; rebuild one read and one UPDATE a row; resolve one 1-minute bar read a session and one UPDATE plus its `plan_excursions` upsert.
- **Wall-clock:** none in the brief beyond the hit-rates read. The rebuild modes are measured on the local run over the fixture and on one ticker's real count, and the PR body states them against the job's task timeout read from its configuration (four times or more).
- **Cost:** no new job, schedule or image; no model call. The Experiment runs on local copies. Each production dry run of the brief after the deploy uses one brief's model calls and is the owner's step.

## done_when map

| done_when | What | Task |
|---|---|---|
| [0] | Policy row | 2 |
| [1] | ATR marks are the targets | 1, 4 |
| [2] | Waypoints and the stronger case | 5 |
| [3] | Brief copy | 7 |
| [4] | Rule version and stored briefs | 3, 8 |
| [5] | The fourth target stored and scored | 9, 10 |
| [6] | Alerts and the movement statement read the quarters | 11, 12 |
| [7] | Thirds leave the analysis code and the docs | 13 |
| [8] | History rebuild tooling | 14, 15 |
| [9] | Reach counts read, not stored here | 6 |
| [10] | No numbers and no names | 1, 16 |
| [11] | Unchanged | 1, 16 |
| [12] | Experiment through the production paths | 17, 18 |
| [13] | Source identity (DASHBOARD-01) | 19 |
| [14] | Catalog, traceability, gate; merge only on the owner's yes | 19, Close-out |

## Review Focus

Inputs the spec implies and no done_when test pins, most likely first. Each has a test in the task that owns the code.

- **Derived builds of a marks session.** `with_premarket` (`lib/strat_levels.py:1924` @2062) and `with_reference` (`:1938`, the signal monitor's put re-anchor) place the marks from the new trigger, rebuild the waypoints and keep the reach table. Task 5.
- **A rebuilt basis read through every path.** A v2 basis rebuilt by `rebuild_on_marks` keeps its recorded trigger through `from_basis`, `plan_inputs`, the brief text and the re-anchor. Task 14.
- **The re-anchor's ATR.** It uses the row's recorded ATR for the basis's `atr_basis`, never a fresh one. Task 11.
- **The longer playbook in Discord.** The IWM After text through `_playbook_code_fields` (`gcp/premarket_brief.py:3115` @2062) rejoins to the same lines in order, none over the field limit and none cut. Task 7.
- **Entry versions of rebuilt rows.** A row rebuilt from v2 writes `plan_excursions` keyed v2 on resolve, beside the history job's v5 rows for the same date (`PRIMARY KEY (ticker, session_date, rule_version)`, `gcp/schema.sql:2358` @2062). The brief's read filters to one version, so the two never pool; Task 15's test shows both rows present and the read counting only its own.

## File map

| File | Change | Task |
|---|---|---|
| `tests/fixtures/level_basis_2026-11-16/` | new: `IWM.json`, `SPY.json`, `QQQ.json`, `sources.json`, per ticker `<T>.main.json`, `<T>.main.txt`; `iwm_plan_excursions.json` (Design 7's sixteen rows) | 1, 6 |
| `tests/fixtures/level_basis_rebuild/` | new: v2, v3 and v5 bases, a live v6 basis, a basis rebuilt from v2 | 14 |
| `tests/lib/session_levels_helpers.py` | `stored_1116`, `main_1116`, `main_text_1116`, `marks_policy`, `reach_1116` | 1, 4, 6 |
| `gcp/schema.sql` | the policy row beside `target_reach_rate` (`:2325` @2062); `calls_t4_price`, `puts_t4_price` beside `:1890`, `:1897` and `:2158`, `:2165`; `calls_t4_hit_ts`, `puts_t4_hit_ts` beside `:1931`, `:1944`; `calls_plan_t4_hit_ts`, `puts_plan_t4_hit_ts` beside `:1994`, `:2003`; `puts_reanchor_t4` beside `:1924`; `premarket_targets_archive` after `plan_excursions` (`:2340`) | 2, 9, 15 |
| `lib/strat_levels.py` | key and `POLICY_WIDE_KEYS` (`:1024` @2062); `policy_wide_param` (`:1391`); `LEVEL_RULE_MARKS`, `plan_target_rule`, `entry_rule_version` (`:1583-1604`); `SideLevels` (`:1819`), `SessionLevels` (`:1866`: `to_basis` `:2015`, `from_basis` `:2078`, `_atr_levels_line` `:1979`); `_pick_side` (`:2876`, gate targets `:2957`, plan call `:2967`); new `_plan_mark_targets`, `_plan_waypoints`, `rebuild_on_marks`, `_mark_plan_lines`; `_plan_block` (`:3347`) | 2 to 8, 14 |
| `tests/lib/level_params_fixtures.py` | the new key in the fixture policy | 2 |
| `tests/meta/test_level_rule_version_readers.py` | `LEVEL_RULE_MARKS` in `WATCHED`; `plan_target_rule` in `ALLOWED` | 3 |
| `gcp/premarket_playbook_resolver.py` | `RESOLVER_VERSION` (`:107` @2062), `LegOutcome` (`:121`), `PlanOutcome` (`:144`), `resolve_leg` (`:280`), `_traded_exit` (`:406`), `resolve_plan` (`:530`), `plan_inputs` (`:734`), `resolve_one` (`:786`), `_PLAN_FIELDS` (`:1113`) | 8, 10 |
| `gcp/premarket_brief.py` | `structured_playbook_columns` (`:1892` @2062), `build_persist_rows` (`:3903`); the reach read (`:1021-1039`) | 6, 9 |
| `gcp/signal_monitor.py`, `lib/strategies/brief_bias.py` | `_reanchor_put_leg` (`:471`), `_persist_put_reanchor` (`:564`); T1 reads (`:652-678`; `brief_bias.py:81-113`) | 11 |
| `lib/movement_statement.py`, `platform/api/schemas.py`, `gcp/brief_explanations.py` | `_REACH_SLOTS` (`:251`), `_reach_rate_sql` (`:286`), `_fetch_reach_rates` (`:352`), `_fetch_tracked_levels` (`:412`), `_new_rule_mark` (`:521`); `ReachRate.slot` (`:528-537`); `_PLAYBOOK_PROMPT` (`:567-570`) | 8, 12 |
| `scripts/analysis/honest_scoring_experiment.py`, `scripts/validation/validate_brief_accuracy.py`, `gcp/queries/nan_triage.sql`, `docs/product/infrastructure/05-h-DATA_DICTIONARY.md`, `ERD.drawio` | thirds out; T1 to T4 from the structured columns; `t4` columns listed | 13 |
| `scripts/maintenance/rebuild_quarter_history.py` | new | 15 |
| `scripts/analysis/atr_marks_experiment.py`, `tests/fixtures/atr_marks_spike_2026-11-16/` | new | 17 |
| tests | `tests/lib/test_strat_levels.py` (`TestStored20261116`, `TestAtrMarkTargets`, `TestPlanWaypoints`, `TestMarkReachCounts`, `TestAtrMarkCopy`, `TestRebuildOnMarks`), `tests/lib/test_level_params_loader.py`, `tests/gcp/test_level_basis.py`, `tests/lib/test_movement_statement.py`, `tests/gcp/test_premarket_brief.py`, `tests/gcp/test_premarket_playbook_resolver.py` (`TestFourLegs`), `tests/gcp/test_signal_monitor.py`, `tests/gcp/test_signal_monitor_level_state.py`, new `tests/gcp/test_brief_explanations.py`, `tests/scripts/test_validate_brief_accuracy.py`, new `tests/scripts/test_rebuild_quarter_history.py` and `tests/integration/test_rebuild_quarter_history_pg.py`, new `tests/integration/test_quarter_targets_schema_pg.py`, `tests/lib/test_level_params_structure.py`, `tests/lib/test_level_params_copy.py`, new `tests/scripts/test_atr_marks_experiment.py` | 1 to 18 |
| `docs/product/02-FEATURE-CATALOG.md`, `12-PR-ISSUE-TRACEABILITY.md`, `03-SITE-TRACEABILITY.md`, `docs/review-evidence/site-source-snapshot.json`, `docs/product/infrastructure/05-a`, `05-c`, `05-e`, `README.md` | the record; inventory by the render step | 19, 2 to 17 |

---

### Task 1: Preconditions, the three stored bases, and today's plan pinned on them

Spec: Decision 9 (merge order); Design 6 ("Which number the marks version is"); Design 7 ("Fixtures"). Advances done_when[10] and [11]; supplies done_when[1] to [4].

**Files:** create `tests/fixtures/level_basis_2026-11-16/{IWM,SPY,QQQ}.json`, `sources.json`, `{IWM,SPY,QQQ}.main.json`, `{IWM,SPY,QQQ}.main.txt`; modify `tests/lib/session_levels_helpers.py`; test `tests/lib/test_strat_levels.py`.

- [ ] **Step 1: Preconditions on `origin/main`, before the branch is cut.** Paste each output into the PR body:
  - `gh api repos/TeneikaAskew/stocks/pulls/2062 --jq '.merged_at'` is a time, and `ls lib/target_reach.py` and `grep -n "CREATE TABLE IF NOT EXISTS plan_excursions\|'target_reach_rate'" gcp/schema.sql` find both.
  - `grep -n "^LEVEL_RULE_VERSION\|^PICK_RULE_VERSIONS\|^def is_current_pick_rule\|^def entry_rule_version" lib/strat_levels.py` shows v5, the tuple of v3, v4 and v5, and both helpers.
  - `grep -n "^status" docs/superpowers/specs/2026-11-17-feat-strat-001-atr-quarter-targets-r3.md` reads `approved`.
  If #2062 has not merged, **stop**: do not open the branch, and do not bring its code here.
- [ ] **Step 2: Re-read every line number.** `grep -n "^def \|^class \|^    def " lib/strat_levels.py gcp/premarket_playbook_resolver.py gcp/premarket_brief.py gcp/signal_monitor.py lib/movement_statement.py` and the `grep` of each schema line in the File map; record a table of name, plan line and base line in the PR body.
- [ ] **Step 3: The six counts of done_when[10] on the merge base:** `python3 -c "import ast;t=ast.parse(open('lib/strat_levels.py').read());c=[n for n in ast.walk(t) if isinstance(n,ast.Constant) and isinstance(n.value,str)];[print(repr(s),len(h),h) for s in ('25%','50%','75%','100%','1/4','quarter') for h in [sorted(n.lineno for n in c if s in n.value)]]"`. Run 2026-11-17: on d35d9ce2 it gives 0, 0, 0, 0, 0 and 5 (`quarter` at `:258`, `:340` twice, `:347`, `:3341`); on c740ba95 0, 0, 0, 0, 0 and 6 (`:258`, `:340` twice, `:347`, `:3245`, `:3412`), the sixth being #2062's docstring and comment that name the quarter change. Paste the merge base's output with its lines; those are Task 16's pins, and the PR body names the commit that moved any count from the spec's five.
- [ ] **Step 4: Export the three bases. Ask the owner once before running** (read-only, `scripts/db_query_cr.sh` without `--commit`): one statement a ticker selecting `level_basis` from `premarket_analysis_history` (falling back to `premarket_analysis`) for `analysis_date = '2026-11-16'` and the ticker, where `level_basis->>'built_at'` starts `2026-11-16T08:31:19`. Save each JSON verbatim. `sources.json` names, per file, the execution id, the SQL and the file's sha256. If the owner says no, stop: Tasks 4 to 7 have no fixture.
- [ ] **Step 5: Record what the base gives**, before any code changes, with a one-off run that is not committed: for each ticker `sl = SessionLevels.from_basis(stored_1116(t))`; `<T>.main.json` holds per side `trigger`, `stop`, `targets`, `skipped`, `gate_targets`, `target_status` and `plan` from `sl.to_basis()`, plus `plan_inputs` (trigger, stop, targets, legs, cutoff, status) for both sides; `<T>.main.txt` holds `format_levels_for_brief(sl.to_level_map(), 'bearish')`.
- [ ] **Step 6: Tests** in `TestStored20261116`: `test_sources_json_matches_the_files`; `test_iwm_trigger_and_stop` (IWM calls 278.92 `PMK_H`, stop 275.86 `PMK_L`; puts 275.86 `PMK_L`, stop 277.41 `PQL`; ATR 4.874951 for `atr_14`); `test_main_records_match` (three tickers, record and text); `test_iwm_text_is_the_specs_today_block` (the spec's Design 7 "Today" CALLS and PUTS blocks, character for character).
- [ ] **Step 7: Run** `python3 -m pytest tests/lib/test_strat_levels.py -k TestStored20261116 -q` (all pass: this pins the base). A failure is a finding about the spec's text or the stored row, reported on the PR, never a changed expectation.
- [ ] **Step 8: Commit:** `test(strat): pin today's plan on the three stored 2026-11-16 bases`

### Task 2: The marks policy row and its key

Spec: Design 2 ("New policy-wide key"); Design 8. Advances done_when[0].

**Files:** `gcp/schema.sql`, `lib/strat_levels.py`, `tests/lib/level_params_fixtures.py`, `tests/lib/test_level_params_loader.py`, `tests/gcp/test_premarket_filter_params.py` (the schema hash pin).

- [ ] **Step 1: Failing tests** in `tests/lib/test_level_params_loader.py`, class `TestPlanTargetMarks`: `ok` with value 4 on the seeded policy loaded from `gcp/schema.sql`; `ok` with value 3 for `[0.25, 0.5, 0.75]`; `ok` with value 0 for `[]`; `input_unavailable` for a missing `marks`, a string entry, `0`, `-0.25`, `[0.5, 0.5]` and `[0.5, 0.25]`; the key is in `POLICY_WIDE_KEYS`. Run: `python3 -m pytest tests/lib/test_level_params_loader.py -k TestPlanTargetMarks -q` (expect FAIL: no such key).
- [ ] **Step 2:** `lib/strat_levels.py`: `PLAN_TARGET_MARKS_KEY = 'plan_target_marks_atr'` beside `PLAN_TARGET_LEVEL_TYPES_KEY` (`:1012` @2062), added to `POLICY_WIDE_KEYS` (`:1024`); `policy_wide_param` (`:1391`) gives `ok` with value `len(marks)` when every entry is a number (not a bool), above zero and above the one before, `input_unavailable` otherwise, and keeps the list in the param's `extra`. A `marks(params)` accessor returns the tuple only when ok.
- [ ] **Step 3:** `gcp/schema.sql`: the row of Global Constraints, inside the same `INSERT ... ON CONFLICT DO NOTHING` as `target_reach_rate` (`:2325` @2062). `tests/lib/level_params_fixtures.py`: the key in the fixture policy, seeded as `gcp/schema.sql` seeds it. Re-pin `SCHEMA_SHA256` in `tests/gcp/test_premarket_filter_params.py` once the schema is final (Task 15), the old and new hash in the PR body.
- [ ] **Step 4:** Run again (expect PASS), plus `python3 -m pytest tests/lib tests/gcp/test_level_params_consumers.py -q`: list every failure with its cause; a test that pins three legs on a level-rule basis is fixed by giving it a local empty marks list (Task 4 adds `marks_policy`), never by editing its expectation.
- [ ] **Step 5:** Render step. Commit: `feat(levels): seed the four ATR quarter marks as a policy row`

### Task 3: The marks version, which rule picks the targets, and the entry version

Spec: Design 6. Advances done_when[4].

**Files:** `lib/strat_levels.py`, `tests/meta/test_level_rule_version_readers.py`, `tests/lib/test_strat_levels.py`.

- [ ] **Step 1: Failing tests:** `plan_target_rule` gives `v2` for `LEVEL_RULE_V2`, `levels` for v3, v4 and v5, `atr_marks` for v6 and None for anything else; `is_current_pick_rule('feat-strat-001.v6')` is true; `rule_version_status('feat-strat-001.v6')` is `known` and `newest_pick_rule_version()` is v6; `entry_rule_version('feat-strat-001.v6')` is `LEVEL_RULE_VERSION`, `entry_rule_version('feat-strat-001.v6', rebuilt_from='feat-strat-001.v2')` is v2, v3 to v5 map to themselves, and v2, None and an unknown string map to None.
- [ ] **Step 2:** `LEVEL_RULE_MARKS = 'feat-strat-001.v6'` after `LEVEL_RULE_VERSION` (`:1586` @2062), added to `PICK_RULE_VERSIONS` (`:1587`). `plan_target_rule(version)` beside `is_current_pick_rule` (`:1590`). `entry_rule_version(version, rebuilt_from=None)` (`:1597`): for the marks version, `rebuilt_from` when it is v2 or a level-rule version, else `LEVEL_RULE_VERSION`; for a level-rule version, itself; else None. Its callers pass the basis's `rebuilt_from_rule_version`: `gcp/premarket_playbook_resolver.py:947` and `gcp/backfill_plan_excursions.py:164` @2062. `gcp/premarket_brief.py:1039` keeps `entry_rule_version(LEVEL_RULE_VERSION)`, which is the entry version of a live marks build.
- [ ] **Step 3:** `tests/meta/test_level_rule_version_readers.py`: `LEVEL_RULE_MARKS` joins `WATCHED`; `('lib/strat_levels.py', 'plan_target_rule')` joins `ALLOWED`. No other site is added.
- [ ] **Step 4:** Run `python3 -m pytest tests/meta/test_level_rule_version_readers.py tests/lib/test_strat_levels.py -q` (expect PASS). Render step. Commit: `feat(levels): name the marks rule version and the helper that picks the target rule`

### Task 4: The marks are the targets

Spec: Design 1, Design 2. Advances done_when[1].

**Files:** `lib/strat_levels.py`, `tests/lib/session_levels_helpers.py`, `tests/lib/test_strat_levels.py`.

- [ ] **Step 1: `marks_policy(marks, legs=3)`** in `tests/lib/session_levels_helpers.py`: a `LevelParams` copy of the fixture's with the marks row replaced (and `exit_legs` for arm A), so tests build arm A (`[]`, 3), Q (the seed) and Q3 (`[0.25, 0.5, 0.75]`).
- [ ] **Step 2: Failing tests**, class `TestAtrMarkTargets`, on the three stored bases rebuilt under the seeded policy (a fresh `build_session_levels` from the basis's recorded inputs, or `from_basis` with the seeded params where the basis is v6):
  - IWM calls targets 280.14, 281.36, 282.58, 283.79; IWM puts 274.64, 273.42, 272.20, 270.99.
  - For every side of SPY, QQQ and IWM, each target equals the trigger's cents plus (calls) or minus (puts) `price_cents(mark * atr)`, with `atr` the basis's own value for its `atr_basis`, computed in the test from the fixture.
  - Each target records `mark`, its share label and `source` `atr_mark`; `gate_targets` are the four targets in order; trigger and stop equal `<T>.main.json`'s; IWM puts T1 is 274.64, never 274.67; `skipped` is empty; the basis records `rule_version` v6.
  - Q3: each side has the first three targets and legs 3.
  - Not ok marks row, two marks on one cent (a tiny ATR), an offset of zero cents, a puts target at or below zero cents: no target, `target_status` carries `input_unavailable` or the row's status, and `rule_version` is v6.
  - Arm A (`marks_policy([], 3)`): targets, skipped, `target_status`, `gate_targets` and text equal `<T>.main.json` and `<T>.main.txt`, and `rule_version` is v5.
  Run `python3 -m pytest tests/lib/test_strat_levels.py -k TestAtrMarkTargets -q` (expect FAIL).
- [ ] **Step 3:** `build_session_levels` (`:2477` @2062) reads the marks param and passes the fresh build's version (Global Constraints) down; `_pick_side` (`:2876`) keeps everything up to `out.trigger` and the stop unchanged and, by `plan_target_rule(version)`, calls `_plan_targets` as today (`:2967`) or the new `_plan_mark_targets(out, trig, atr, atr_basis, params, side)`, which checks `plan_target_marks_atr` and `entry_cutoff_et` first, places each target from the trigger's cents, sets `out.targets`, `out.gate_targets = list(out.targets)`, `out.skipped = []`, and `out.plan` with the marks, each mark's price, the ATR and its basis, `legs = len(marks)` and the cutoff. `exit_legs`, `target_min_spacing_atr` and `plan_target_level_types` are not read for a marks side. A level-rule side keeps `out.gate_targets = rungs[1:4]` (`:2957`).
- [ ] **Step 4:** Run again (expect PASS), then `python3 -m pytest tests/lib tests/gcp -q`; each failure that pins the level rule gets `marks_policy([], 3)` and its old expectation, listed in the PR body.
- [ ] **Step 5:** Render step. Commit: `feat(levels): place the targets at the ATR marks from the trigger`

### Task 5: Levels are waypoints, and a target on a level is the stronger case

Spec: Design 3. Advances done_when[2].

**Files:** `lib/strat_levels.py`, `tests/lib/test_strat_levels.py`.

- [ ] **Step 1: Failing tests**, class `TestPlanWaypoints`:
  - On the three bases, `plan_waypoints` equals a list the test computes from the fixture's `levels` alone: every level strictly past the trigger on the side's own side, one entry a cent with every name on that cent, price order outward, out to the last target and past it only inside the side's trigger window (`_within_staleness_window`, `:889`), each with `price`, `names`, `segment` (`before_t1`, `t1_t2`, `t2_t3`, `t3_t4` or `beyond`), `distance_atr`, and where grouped `zone`, `far_price`, `members`.
  - By name and price: IWM calls PDO 278.95, PDH 279.17, PMC 279.33 before T1, CMO 281.64 in `t2_t3`, PMH 285.26 `beyond`; IWM puts PDL 274.67 before T1, 11/9 Gap Low 274.55 in `t1_t2`, PML 269.88 `beyond`.
  - IWM calls T4 283.79 records `on_level` PWH, and PWH is not a waypoint; a level one cent from a target is a waypoint and the target records no `on_level`.
  - Zones: levels within `price_cents(level_cluster_atr * atr)` of the group's nearest level join (equal joins); a zone never spans a target; with `level_cluster_atr` not ok every level is its own entry and `waypoint_zone_status` carries the status.
  - A prior-close waypoint keeps the gap fill note by `gap_fill_flag_atr`, as a prior-close target has it today.
  - Derived builds: `with_premarket` and `with_reference` of a marks session place the marks from the new trigger and rebuild the waypoints.
  Run (expect FAIL: no `plan_waypoints`).
- [ ] **Step 2:** `_plan_waypoints(out, levels, trig, atr, params, side, window)` after `_plan_mark_targets`; `SideLevels` (`:1819` @2062) gains `waypoints` and `waypoint_zone_status`; `to_basis` and `from_basis` carry them; the segment names are formatted from the number of marks.
- [ ] **Step 3:** Run again (expect PASS). Render step. Commit: `feat(levels): print the levels between the targets as waypoints`

### Task 6: The reach counts are read through lib.target_reach

Spec: Design 4. Advances done_when[9].

**Files:** `lib/strat_levels.py`, `gcp/premarket_brief.py`, `tests/fixtures/level_basis_2026-11-16/iwm_plan_excursions.json`, `tests/lib/session_levels_helpers.py`, `tests/lib/test_strat_levels.py`, `tests/gcp/test_premarket_brief.py`.

- [ ] **Step 1: The fixture:** sixteen IWM `plan_excursions` rows of the level-rule entry version, one a session from 2026-10-23 to 2026-11-13, `excursion_atr` in date order 0.1, 0.3, 0.4, 0.7, 1.1, 1.2, 1.6, 2.4, 0.05, 0.2, 0.3, 0.6, 0.9, 1.3, 1.5, 2.1 (spec Design 7), and `reach_1116()` building the `ReachTable` from it through `lib.target_reach.load_target_reach` with a fake `query_fn`.
- [ ] **Step 2: Failing tests**, class `TestMarkReachCounts`: each target and waypoint's count is the rows whose `excursion_atr` is at least that line's distance in cents over the basis ATR (IWM calls T1 13 of 16, T4 7 of 16; puts T1 13 of 16); a marks-version build with rows only of the level-rule version prints counts, not `no history yet`; a ticker with no rows prints `no history yet` on each line; a ticker with at least `min_sample` rows prints `reached k of n (p%)`; a raising read gives the hit-rates spec's unavailable line and never `no history yet`. In `tests/gcp/test_premarket_brief.py`: a marks-version `BRIEF_AS_OF` run reads only rows before the session date, in one read for SPY, QQQ and IWM, filtered to `entry_rule_version(LEVEL_RULE_VERSION)`. Run (expect FAIL).
- [ ] **Step 3:** The count of each line is `ReachTable.count_text(d, min_sample)` with `d = cents distance / 100 / atr`; `format_levels_for_brief` (`:3232` @2062) already carries `reach` and `reach_min_sample` to each side's plan block. No reach column, no `ladder_history_sessions` key, no new query: the brief's read stays the one at `gcp/premarket_brief.py:1021-1039` @2062.
- [ ] **Step 4:** Run again (expect PASS). Render step. Commit: `feat(brief): count each quarter and waypoint from the reach history`

### Task 7: What the brief prints

Spec: Design 7; Decision 6. Advances done_when[3].

**Files:** `lib/strat_levels.py`, `tests/lib/test_strat_levels.py`, `tests/gcp/test_premarket_brief.py`.

- [ ] **Step 1: Failing golden tests**, class `TestAtrMarkCopy`, on the stored IWM basis, the Task 6 fixture and bias `bearish`:
  - seeded policy: the CALLS and PUTS blocks equal Design 7's After text exactly. If the fixture holds a level in range the owner's example does not name, the golden is the fixture's, and the difference is reported on the PR.
  - arm A (`marks_policy([], 3)`): the text equals `IWM.main.txt`.
  - Q3: the share reads `1/3` and the last target line reads `sell the last 1/3, or hold to the close or the stop`.
  - a ticker with no rows: every count reads `no history yet`, never `0 of 0`.
  - a marks side prints no `Skipped, closer than` line and no `ATR levels` line; NEXT LEVELS Calls and Puts and PMG ZONES equal `IWM.main.txt`'s.
  - a marks row not ok: the existing `Targets unavailable ({status}): no exit plan for this side.` line and no target.
  - Discord: the After text through `_playbook_code_fields` rejoins to the same lines in order, none over the field limit.
  Run (expect FAIL).
- [ ] **Step 2:** `_plan_block` (`:3347` @2062) branches on the side's plan source: a marks side prints the header line, the counts line, and the target and waypoint lines in price order by `_mark_plan_lines`, the share `1/{legs}` and the last-leg text built as `:3383-3394` builds them today; a level-rule side prints exactly what it prints today. `SessionLevels._atr_levels_line` (`:1979`) returns None for a marks side. Percents are formatted from the marks.
- [ ] **Step 3:** Run again (expect PASS), and every existing golden of `tests/lib/test_strat_levels.py` unchanged. Render step. Commit: `feat(brief): print the quarter targets and the levels on the way`

### Task 8: Stored briefs keep their plan; readers and rates by version

Spec: Design 6. Advances done_when[4].

**Files:** `lib/strat_levels.py`, `gcp/premarket_playbook_resolver.py`, `lib/movement_statement.py`, `tests/gcp/test_level_basis.py`, `tests/lib/test_movement_statement.py`.

- [ ] **Step 1: Failing tests** in `tests/gcp/test_level_basis.py`:
  - (a) a stored level-rule basis, with params that record neither new key and with params that record both, rebuilds through `SessionLevels.from_basis` with targets, skipped list, `target_status` and text equal to `<T>.main.*`, and the marks key is never checked for it (a params object whose marks row is not ok changes nothing);
  - (b) a v6 basis rebuilds the same four targets, waypoints and text from the marks it recorded after the policy row changes;
  - (c) `plan_inputs` (`gcp/premarket_playbook_resolver.py:734` @2062) on a v6 basis returns the four target prices in order, legs 4 and `plan_available` true, and on a level-rule basis what `<T>.main.json` records;
  - (a) and (b) also assert that a v6 basis and a level-rule basis built on the same session with the same inputs have the same trigger and stop on both sides.
  In `tests/lib/test_movement_statement.py`: with resolved rows of v5 and v6 in the population, a v6 session's rates count v6 rows of its own entry version only (a row rebuilt from v2 never pools with one built live from v5) and a v5 session's count v5 only; `_new_rule_mark` (`lib/movement_statement.py:521`) returns the cleared mark for a v6 basis. Run (expect FAIL).
- [ ] **Step 2:** `from_basis` (`:2078` @2062) keeps a v6 basis's version and rebuilds it by the mark walk from its recorded marks; `_assemble`'s `keeps` (`:2588`) holds for v6 through `is_current_pick_rule`. `plan_inputs` reads a v6 side's `plan` like a current-rule side (`legs = len(marks)`). `_reach_rate_sql` (`:286`) and `_fetch_reach_rates` (`:352`) bind the session row's version as today and, for the marks version, also its entry version, compared with `COALESCE(level_basis->>'rebuilt_from_rule_version', :live_entry)`, `:live_entry` bound from `entry_rule_version(LEVEL_RULE_MARKS)`.
- [ ] **Step 3:** Run again (expect PASS), with `research-test`'s stack for `tests/lib/test_movement_statement.py`. Render step. Commit: `feat(levels): stored briefs keep the rule they were built under`

### Task 9: The fourth target is stored

Spec: Design 5; Design 11 ("Gate targets"). Advances done_when[5].

**Files:** `gcp/schema.sql`, `gcp/premarket_brief.py`, `lib/strat_levels.py` (`_legacy_trigger_dict`), `tests/gcp/test_premarket_brief.py`, new `tests/integration/test_quarter_targets_schema_pg.py`.

- [ ] **Step 1: Failing tests:** for a marks side `structured_playbook_columns` (`gcp/premarket_brief.py:1892` @2062) gives `calls_t1_price` to `calls_t4_price` (and puts) equal to its four targets and no `plan_t1..t3` price key; the persisted row of `build_persist_rows` (`:3903`) carries `calls_t4_price` and `puts_t4_price`; for a level-rule basis both give exactly what they give on the base. `tests/integration/test_quarter_targets_schema_pg.py`: the nine columns exist with their types and are nullable, in both tables where Design 5 names both; the policy row is present once; a second apply of `gcp/schema.sql` changes nothing. Run (expect FAIL).
- [ ] **Step 2:** `gcp/schema.sql`: `calls_t4_price`, `puts_t4_price` (both tables), `calls_t4_hit_ts`, `puts_t4_hit_ts`, `calls_plan_t4_hit_ts`, `puts_plan_t4_hit_ts`, `puts_reanchor_t4` (`premarket_analysis`), each `ADD COLUMN IF NOT EXISTS` beside its `t3` sibling (File map). No `plan_t4_price`.
- [ ] **Step 3:** `structured_playbook_columns`: the loop at `:1906` runs over the side's targets, not `(1, 2, 3)`; a marks side writes `t1..t4` and no `plan_t` price. `build_persist_rows`: the target keys come from that loop (`:3998-4013`). `_legacy_trigger_dict` (`lib/strat_levels.py:3048` @2062) gives a marks side's `targets` and `room_to_first_target` from its four targets.
- [ ] **Step 4:** Run again (expect PASS), with the integration test on a local Postgres. Render step. Commit: `feat(brief): store the fourth target in the t1 to t4 columns`

### Task 10: The fourth target is scored

Spec: Design 5; Design 11 ("Resolver"). Advances done_when[5].

**Files:** `gcp/premarket_playbook_resolver.py`, `tests/gcp/test_premarket_playbook_resolver.py`.

- [ ] **Step 1: Failing tests**, class `TestFourLegs`, synthetic 1-minute bars, a call with trigger 100.00, stop 99.00, targets 100.50, 101.00, 101.50, 102.00 and four legs: all four reached gives exit `'t1,t2,t3,t4'`, `plan_r` 1.25 and `t4_hit_ts` set; the stop after T2 gives `'t1,t2,stop,stop'` and `plan_r` -0.125; the mirrored put cases pass; `resolve_leg` on those four targets sets `t1_hit_ts` to `t4_hit_ts`; `_traded_exit` on a marks row exits at the 25 percent mark; `resolve_one`'s UPDATE sets every `t4` column. Every existing three-leg case passes unchanged. Run (expect FAIL: neither `PlanOutcome` nor `LegOutcome` has `t4_hit_ts`).
- [ ] **Step 2:** `LegOutcome` (`:121` @2062) and `PlanOutcome` (`:144`) gain `t4_hit_ts`; `resolve_leg` (`:280`) takes the side's target list and sets one hit a target (`:377` today sets three); `resolve_plan` (`:530`) walks every target, not `targets[:3]` (`:588-591`); `_PLAN_FIELDS` (`:1113`) gains `t4_hit_ts`; the SELECT (`:819-821`), the self-heal (`:899-909`) and the UPDATE (`:955-1043`) read and write four prices and four hit times; `RESOLVER_VERSION` (`:107`, `'2026-11-17.v5'` @2062) moves to the next dated version on the merge base.
- [ ] **Step 3:** Run again (expect PASS). Render step. Commit: `feat(resolver): score the fourth target and its hit times`

### Task 11: The alerts' T1 and the put re-anchor read the quarters

Spec: Design 11 ("Signal monitor"). Advances done_when[6].

**Files:** `gcp/signal_monitor.py`, `lib/strategies/brief_bias.py`, `tests/gcp/test_signal_monitor.py`, `tests/gcp/test_signal_monitor_level_state.py`.

- [ ] **Step 1: Failing tests:** on a v6 row the `LegStateTracker` (`lib/strat_levels.py:109`) turns `post_t1` at the 25 percent mark (`calls_t1_price`, `puts_t1_price`) and not at the first level past the trigger; the put re-anchor writes `puts_reanchor_t1` to `puts_reanchor_t4`, each equal to the re-anchored trigger minus `price_cents(mark * atr)` with the row's recorded ATR for its `atr_basis`; on a level-rule row both behave as on the base. Run (expect FAIL).
- [ ] **Step 2:** `_reanchor_put_leg` (`gcp/signal_monitor.py:471`) takes the targets of `session.with_reference(open_px).short`, which on a v6 basis are the marks from the new trigger (Task 5); the comment at `:541` ("alert targets keep their pre-spacing meaning") goes; `_persist_put_reanchor` (`:564`, the UPDATE at `:579-582`) writes `puts_reanchor_t4`. The T1 reads (`:652-678`; `lib/strategies/brief_bias.py:81-113`) are unchanged in code: the column now holds the 25 percent mark. The TARGET HIT watcher's percent target is not touched.
- [ ] **Step 3:** Run again (expect PASS), and the whole of both files. Render step. Commit: `feat(monitor): the alerts' T1 and the put re-anchor read the quarters`

### Task 12: The movement statement's slots and the model's playbook prompt

Spec: Design 11 ("Movement statement", "Brief explanations"). Advances done_when[6].

**Files:** `lib/movement_statement.py`, `platform/api/schemas.py`, `gcp/brief_explanations.py`, `tests/lib/test_movement_statement.py`, new `tests/gcp/test_brief_explanations.py`.

- [ ] **Step 1: Failing tests:** on a v6 row the slots are `trigger`, `t1`, `t2`, `t3`, `t4`, named from the number of marks (a three-mark row gives three target slots); `_fetch_tracked_levels` and `_reach_rate_sql` read the four columns; a v5 row keeps `trigger`, `t1` to `t3`. `tests/gcp/test_brief_explanations.py`: the playbook prompt holds no `T1/T2/T3` and lists the targets the plan lists, on a four-target and on a three-target basis. Run (expect FAIL).
- [ ] **Step 2:** `_REACH_SLOTS` (`lib/movement_statement.py:251`) becomes a function of the row's target count; `_reach_rate_sql` (`:286`), `_fetch_reach_rates` (`:352`) and `_fetch_tracked_levels` (`:412`, `:424`) use it. `ReachRate.slot` (`platform/api/schemas.py:534`) documents `t4`. `_PLAYBOOK_PROMPT` (`gcp/brief_explanations.py:567-570`) names the targets as the plan lists them.
- [ ] **Step 3:** Run again (expect PASS), with the research stack. Render step. Commit: `feat(movement): read one slot a target, four on the quarters`

### Task 13: Thirds leave the analysis code and the docs

Spec: Design 5 ("Other readers of the columns"); Design 11 ("Not thirds, and kept"); Design 12 ("Readers of the stored text"). Advances done_when[7].

**Files:** `scripts/analysis/honest_scoring_experiment.py`, `scripts/validation/validate_brief_accuracy.py`, `tests/scripts/test_validate_brief_accuracy.py`, `gcp/queries/nan_triage.sql`, `docs/product/infrastructure/05-h-DATA_DICTIONARY.md`, `ERD.drawio`.

- [ ] **Step 1: Failing tests** in `tests/scripts/test_validate_brief_accuracy.py`: a row with `t1..t4` prices and hit columns scores T1 to T4 from those columns; a row whose playbook text names other prices is scored from the columns, never parsed from `playbook` or `llm_playbook`. Run (expect FAIL).
- [ ] **Step 2:** `validate_brief_accuracy.py`: replace `parse_playbook` (`:392`) as the source of T prices (`:471`) with the structured columns, selected beside `playbook` (`:350`). `honest_scoring_experiment.py`: remove `thirds_rule` (`:403`), its call (`:472`) and its "a third at each" report lines (`:537`); the module docstring (`:29`) says git history keeps the rule for a one-off score. `nan_triage.sql` (`:35-36`): add the `t4` price columns to both statements. `05-h-DATA_DICTIONARY.md` (`premarket_analysis` `:1269`, `premarket_analysis_history` `:2355`) and `ERD.drawio`: the nine columns and `premarket_targets_archive`, and `plan_t1_price` to `plan_t3_price` marked retired by Design 13.
- [ ] **Step 3:** Run again (expect PASS). Render step. Commit: `refactor(analysis): retire thirds from the analysis scripts and the data docs`

### Task 14: rebuild_on_marks, and every reader keeps the rebuilt entry

Spec: Design 12 ("A rebuild keeps the entry"); Design 6 ("Every reader keeps that entry"). Advances done_when[8].

**Files:** `lib/strat_levels.py`, `tests/fixtures/level_basis_rebuild/`, `tests/lib/test_strat_levels.py`, `tests/gcp/test_level_basis.py`.

- [ ] **Step 1: Fixtures:** v2, v3 and v5 bases (from the existing stored fixtures `tests/fixtures/atr_levels_brief_base.json`, `tests/fixtures/iwm_2025_10_22_level_basis.json` and Task 1's bases; each file's origin and sha256 in a `sources.json`), a live v6 basis from Task 4, and a basis already rebuilt from v2. One v2 basis whose recorded trigger differs to the cent from what the level rule picks on the same levels (recorded in the fixture, checked by the test).
- [ ] **Step 2: Failing tests**, class `TestRebuildOnMarks`: on v2, v3 and v5 each trigger, stop and ATR is kept to the cent, targets equal the trigger plus or minus `price_cents(mark * atr)`, and `rebuilt_from_rule_version` is v2, v3 and v5; on a live v6 basis it is `LEVEL_RULE_VERSION`, never v6; on a basis already rebuilt from v2 it stays v2 and targets, waypoints and text are equal; a basis with no trigger, stop or ATR raises. In `tests/gcp/test_level_basis.py`: on the moved-trigger v2 basis, the basis `rebuild_on_marks` returns gives through `from_basis` the recorded trigger, stop and names on both sides and the same targets, waypoints and text, and through `plan_inputs` the same trigger, stop, four prices and legs 4; a spy on `_assemble` records no call. Run (expect FAIL).
- [ ] **Step 3:** `rebuild_on_marks(basis, marks)`: reads the recorded trigger, stop, ATR, `atr_basis` and levels, runs `_plan_mark_targets` and `_plan_waypoints` only, and returns a basis with `rule_version` v6, `rebuilt_from_rule_version = entry_rule_version(recorded, rebuilt_from=basis.get('rebuilt_from_rule_version'))` (with v2 kept as v2), the four targets, `plan_waypoints` and `plan`. `from_basis` returns `rebuild_on_marks(basis, recorded marks)` when the basis records `rebuilt_from_rule_version`, before any `_assemble`.
- [ ] **Step 4:** Run again (expect PASS). Render step. Commit: `feat(levels): rebuild a stored basis on the quarters keeping its entry`

### Task 15: The history rebuild tool and its archive

Spec: Design 12 (modes 1 to 6, "Capacity"); Decision 13 (the model's stored text is cleared, owner 2026-11-17: "The AI written text is based on the last numbers / stale data now right? If so then I would say clear it."). Advances done_when[8].

**Files:** `gcp/schema.sql`, new `scripts/maintenance/rebuild_quarter_history.py`, new `tests/scripts/test_rebuild_quarter_history.py`, new `tests/integration/test_rebuild_quarter_history_pg.py`.

- [ ] **Step 1:** `gcp/schema.sql`: `premarket_targets_archive` (`archive_id`, `run_id`, `source_table`, `source_key` JSONB, `ticker`, `date`, `run_kind`, `archived_at`, `old_row` JSONB), `CREATE TABLE IF NOT EXISTS`, after `plan_excursions`.
- [ ] **Step 2: The script**, modes in Design 12's order, each a subcommand with `--tickers`, `--from`, `--to` and `--run-id`. `count` and `verify` are read-only. `archive`, `rebuild`, `resolve` and `restore` write only with `--commit`; without it they print what they would write. Work is one transaction a ticker and table.
  - `count`: per table and `run_kind`, rows by recorded `rule_version` and by whether a basis exists, earliest and latest date, average `pg_column_size`; `plan_excursions` by `rule_version`; per ticker the sessions with and without bars in `market_data_intraday`.
  - `archive`: `INSERT ... SELECT to_jsonb(t)` for every row rebuild or resolve may write, and every `plan_excursions` row of those tickers and dates; stops unless the archived counts equal `count`'s, per table.
  - `rebuild`: `rebuild_on_marks` on each archived row under the seeded marks (read by `load_level_params` for the row's date); writes `t1..t4_price`, NULL `plan_t1..t3_price`, `level_basis`, `playbook` re-rendered by `format_levels_for_brief` from the rebuilt basis and the row's stored inputs, `puts_reanchor_t1..t4` from `puts_reanchor_trigger` and the row's ATR where a re-anchor was recorded (the other re-anchor columns untouched), NULL in every outcome column the resolver writes and in `outcome_resolved_at`, and NULL `llm_playbook` (its old text is in the archive); `llm_analysis` untouched. A row is refused, and listed, when its trigger or stop would change by a cent, when it has no basis and its stored trigger, stop or the ATR of `derive_level_map_from_daily` (`gcp/premarket_playbook_resolver.py:176` @2062) is missing, or when re-rendering its own basis under its own rule does not give its stored `playbook` byte for byte (the inputs are incomplete).
  - `resolve`: `resolve_one` forced over every rebuilt `premarket_analysis` row on `market_data_intraday` bars only; a no-bars session keeps the NULLs rebuild left.
  - `verify`: zero rows not v6, zero non-NULL `plan_t1..t3_price`, zero triggers or stops that differ from the archive, archived = rebuilt + refused with each refused row named, resolved counts by status with the no-bars rows equal to `count`'s gap, zero playbook texts that sell a third and zero non-NULL `llm_playbook` on a rebuilt row.
  - `restore`: every archived row written back whole by `archive_id`; the `plan_excursions` rows resolve added for those keys deleted and the archived ones written back.
- [ ] **Step 3: Failing tests.** `tests/scripts/test_rebuild_quarter_history.py` holds the cases, which need a Postgres loaded from `gcp/schema.sql` (`DB_HOST` set; without it each case skips with a reason that names the integration job); `tests/integration/test_rebuild_quarter_history_pg.py` imports and runs the same cases so CI's `integration-tests` job runs them. Fixture rows: v2, v3 and v5 bases in both tables, one live v6 row, one row already rebuilt from v2, one `premarket_analysis` row with no basis, one with a put re-anchor, one session with no 1-minute bars, and `plan_excursions` rows for the fixture dates. Cases, as done_when[8] lists them: `count` by version and the no-bars session; `archive` stores every row whole and every `plan_excursions` row, and stops on a count mismatch; `rebuild` writes the four targets, the re-rendered playbook, the four re-anchor prices, NULL outcomes and NULL `llm_playbook`, and refuses a row whose trigger or stop would change; `resolve` reads only `market_data_intraday` and leaves the no-bars row NULL; the live v6 row and the row rebuilt from v2 keep entry versions v5 and v2, as their `entry_rule_version` read before rebuild; a second rebuild changes no column; `verify` reads zero of each and names the refused rows; `restore` returns both tables and `plan_excursions` equal, row for row and column for column, to a snapshot taken before archive; and a v2-keyed `plan_excursions` row written by resolve sits beside the history job's v5 row for the same date while the brief's read counts only its own version. Without `--commit` no mode writes (a statement spy). Run locally against Postgres 15 (expect FAIL).
- [ ] **Step 4:** Implement until they pass; paste the local run with each mode's wall-clock over the fixture.
- [ ] **Step 5:** Re-pin `SCHEMA_SHA256` (Task 2 Step 3). Render step. Commit: `feat(maintenance): rebuild stored briefs on the quarters with an archive and a restore`
- [ ] **Step 6: `count` from production. Ask the owner once before running** (read-only, through `scripts/db_query_cr.sh` without `--commit`, the `count` SQL printed by the script's `count --print-sql`). Paste it, the archive size it implies, and the job task timeout read from its configuration into the PR body. No other mode runs against production from this branch, and no alerts replay with `--persist`; live `signal_alerts` rows are not rewritten.

### Task 16: No numbers, no names, and nothing else moved

Spec: done_when "No numbers and no names" and "Unchanged". Advances done_when[10] and [11].

**Files:** `tests/lib/test_level_params_structure.py`, `tests/lib/test_level_params_copy.py`.

- [ ] **Step 1:** `tests/lib/test_level_params_structure.py` passes with no edit to its literal allowance; `test_the_walk_reaches_the_rules_it_must_cover` (`:185`) also asserts that `_plan_mark_targets` and `_plan_waypoints` are reached from `build_session_levels`.
- [ ] **Step 2:** `tests/lib/test_level_params_copy.py`: over every `ast.Constant` str of `lib/strat_levels.py`, the count of literals containing each of `'25%'`, `'50%'`, `'75%'`, `'100%'`, `'1/4'` and `'quarter'` equals the pins of Task 1 Step 3, typed into the test; a share or percent typed into the level code fails it.
- [ ] **Step 3:** done_when[11]: list in the PR body the existing test that pins each unchanged behavior (the trigger and stop rule, opened-through, the entry cutoff, `TestAtrRungs`, `TestAtrRungsDisplayOnly`, NEXT LEVELS, PMG zones, the monitor's fire decisions, persona plans, the CALL/PUT pick, and the level rule on an arm A basis); run them on `origin/main` and on the head and paste both results.
- [ ] **Step 4:** Commit: `test(levels): pin the literal counts and the walk's reach`

### Task 17: The Experiment's driver, committed and tested

Spec: Experiment ("Method", "Arm A is checked twice", "Reported, per arm"); CLAUDE.md 3.6. Advances done_when[12].

**Files:** create `scripts/analysis/atr_marks_experiment.py`, `tests/scripts/test_atr_marks_experiment.py`, `tests/fixtures/atr_marks_spike_2026-11-16/report_v1_side.txt`, `report_followup.txt`.

- [ ] **Step 1: The spike's reports**, verbatim from the local branch `spike/atr-quarter-targets` (21612e698) if it still exists; otherwise from the spec's "Result as run" quotations only, said so in the PR body.
- [ ] **Step 2: The driver**, as the r2 plan's Task 13 specified it, with these r3 changes:
  - `ARMS`: A is a local `plan_target_marks_atr` row `[]` dated 2015-01-03 (with `exit_legs` 3 as seeded); Q is the seeded policy, no added row; Q3 a local row `[0.25, 0.5, 0.75]` dated 2015-01-03. `arm_policy_sql(arm)` returns the statement or None for Q.
  - `require_local_db()` first in every subcommand: `DB_HOST` is `127.0.0.1` or `localhost`, `CLOUD_SQL_CONNECTION_NAME == 'local-experiment-not-cloud'`, `BRIEF_LLM_DISABLE == '1'`.
  - `pick_trade` as the spike's `side` variant (one trade per ticker-day, the first side to fill, a same-bar tie is no trade, a side that opened through is never the pick).
  - `score`: per trade and arm, from `plan_inputs` and `resolve_plan`, and the reach measure from `plan_excursion` (`gcp/premarket_playbook_resolver.py:662` @2062) on the same bars, cut at the exchange close; asserts every Q and Q3 basis is v6, every A basis v5, and the three arms trade the same ticker-days with equal trigger, stop and fill.
  - `report`: the eleven measures per arm, with the spike's figures beside, measures 5 to 8 from `excursion_atr` against each mark's and waypoint's distance; the range by `numpy.random.default_rng(7)`, whole days, 2,000 draws, percentiles 5 and 95.
  - `baseline` (done_when[12] (a)): arm A alone from the one database `DB_NAME` names, no `plan_excursion`, `mfe_atr`, `t4_hit_ts` or rule version read; prints the total, the trade count, per-ticker totals, `git -C <cwd> rev-parse HEAD` and `__file__` of `gcp.premarket_brief`, `gcp.premarket_playbook_resolver` and `lib.strat_levels`, and raises before scoring if any is not under the working directory. Module-level imports name only what 97190ef41 has.
  - `compare BASE_DAYS HEAD_DAYS`: trigger-changed ticker-days, as done_when[12] (b) defines them.
- [ ] **Step 3: Tests:** `test_refuses_a_database_that_is_not_local`; `test_pick_trade`; `test_arm_policy_sql`; `test_the_driver_walks_no_bars_and_replaces_no_plan` (by `ast`: no `replace`, no keyword `targets` or `legs`, no `iterrows`/`itertuples` on bars, the production names imported); `test_spike_figures_parse`; `test_the_range_is_seeded`; `test_reach_share_uses_excursion_atr` (five trades at 0.1, 0.3, 0.5, 0.8, 1.2 give 4, 3, 2, 1 of 5 at the four marks); `test_baseline_imports_only_what_97190ef41_has`; `test_baseline_reads_no_new_field`; `test_baseline_prints_sha_and_module_paths`; `test_trigger_changed`. Run (expect FAIL: no module), implement, run (expect PASS).
- [ ] **Step 4:** Render step. Commit: `feat(strat): add the ATR marks experiment driver`

### Task 18: The Experiment, through the production paths, into local databases

Spec: Experiment; done_when "Experiment through the production paths". Closes done_when[12] when both arm A checks of Step 4 hold. Nothing here writes to production.

- [ ] **Step 1: The inputs. Ask the owner once before running.** The same inputs the hit-rates Experiment (#2062, its done_when 11) settles on, by the path the owner authorizes there: the daily rows and calibration a local brief replay needs, the premarket inputs, `ticker_level_params` and the premarket cutoffs and filter parameters, and the 1-minute bars exported from `market_data_intraday`. No vendor fetch. Record each source and file's sha256. If no authorized path exists yet, stop here: done_when[12] stays unticked, the PR stays a draft, and the PR body says what is missing.
- [ ] **Step 2: The template and the arms.** Postgres 15; `gcp/schema.sql` from the head into `arm_template`; load the inputs, calibrate and recompute the premarket fields with the production tools (their flags checked against `--help` on the base), as the r2 plan's Task 14 Step 2 sets out, with its two stated limits (the placeholder and the premarket window); `CREATE DATABASE arm_a|arm_q|arm_q3 TEMPLATE arm_template`; `arm_policy_sql` in `arm_a` and `arm_q3`; `replay` each arm over 2022-01-03 to 2026-11-10 (`BRIEF_TICKERS=SPY,QQQ,IWM`, `BRIEF_AS_OF` per session, `gcp.premarket_brief.main([])`, nothing else). Expect one `premarket_analysis` row a ticker-session in each.
- [ ] **Step 3: Score the head:** `score ... --out atr_marks_arms.csv --days-out arm_a_head_days.csv`. No figure of any arm is read until Step 4 (a) holds.
- [ ] **Step 4: Arm A is checked twice, and both are required.**
  - **(a)** `git worktree add --detach <wt> 97190ef41`; a database `arm_base` from `<wt>/gcp/schema.sql`, prepared by that commit's tools from the same inputs; with the working directory and `PYTHONPATH` at `<wt>`, run `python3 <head>/scripts/analysis/atr_marks_experiment.py` `load`, `placeholder`, `replay A` and `baseline ... --days-out arm_a_base_days.csv`. **Pass:** within 0.1 R of +176.8 over 3,463 trades. Paste the total, the trade count, per-ticker totals beside +64.2, +114.0 and -1.4, the worktree's HEAD sha and the three module paths. If it fails, stop, post those figures and nothing of any arm; a cause in the driver is fixed there (tests first), a cause in the inputs by a fresh Step 1 on the owner's yes. This proves the harness and its data, not the new code.
  - **(b)** The head's arm A, with its trade count, beside the spike's +176.75 over 3,463; `compare arm_a_base_days.csv arm_a_head_days.csv`; the PR body attributes the difference to the premarket rules merged since 97190ef41 (the brief build, #2010, and the prior-close print rule, `docs/superpowers/specs/2026-11-16-feat-playbook-001-prior-close-prints-r2.md`) by trigger-changed ticker-days, arm A's R and trade count in each run on those days and on the rest, and every day of the rest whose R differs, with its cause.
  - **Then** `report atr_marks_arms.csv`. Q and Q3 are read against the head's arm A.
- [ ] **Step 5: The PR body shows** (a) and (b); per arm the eleven measures; the spike's figures beside, never in their place (A +176.75 over 3,463; Q +152.49; Q3 +129.72; Q minus A -24.3, range -71.8 to +21.8; Q3 minus A -47.0, range -109.1 to +12.4; arm Q's T1 to T4 shares 52.3%, 27.1%, 12.8%, 6.2%); every difference with its explanation; the measures the spike did not produce (5, 6, 7, 8 at `level_cluster_atr`, 9's average win and loss); the driver's and the csv's sha256; the commands; the two limits.
- [ ] **Step 6: The reading rule** ("What keeps today's plan"): an arm whose 90% range against A lies wholly below zero overall, or for two of the three tickers, is reported as failing, and the PR is not merged with it without the owner's explicit decision recorded on the PR. An arm whose range spans zero is put to the owner as "no worse, by this test".

### Task 19: Close: product record, site note, the gate and the merge question

Spec: "Source identity and close-out"; done_when "Source identity" and the last item. Closes done_when[13] and [14] but for the owner's steps. Once the site-note steps start, no file under `gcp/`, `lib/`, `scripts/` or `tests/` changes without redoing them.

- [ ] Push with `git push -u origin feature/feat-strat-001-atr-quarter-targets-r3` and open a **draft** PR (REST). **Do not enable auto-merge.** Body: the PR template; the spec's and this plan's paths; the 15 done_when lines as `- [ ]`, copied from the spec byte for byte (escaped quotes included); Red then green; the Capacity section, each value starting with a figure; Task 1's outputs and line table; both version constants read on the merge base; Task 15's local run and production `count`; Task 18's results; the choices this plan made (the version of a fresh build, the playbook self-check of rebuild, the `--commit` guard, the test file split of Task 15); and "Merging applies gcp/schema.sql to production through apply-schema-on-change and puts the quarters in every new brief once deployed; merge only on the owner's recorded yes".
- [ ] Set `pr:` in this plan to the PR's number.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, `### FEAT-STRAT-001` (`:233`): the quarter targets, waypoints, the fourth column set and the rebuild tool, under review and not deployed; Last reviewed. `docs/product/12-PR-ISSUE-TRACEABILITY.md`, `### FEAT-STRAT-001` (`:547`): the PR in its lineage, naming spec PRs #2013, #2019 and #2053. Commit: `docs(product): record the ATR quarter targets under FEAT-STRAT-001`.
- [ ] Site note, four steps: (1) clean tree, `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`; (2) in `docs/product/03-SITE-TRACEABILITY.md`, the `| FEAT-STRAT-001 | DASHBOARD-01 |` row (`:1358`) and no other byte: the new `source_identity_sha256`, this change's prose (backend source and local tests only), then ` Earlier: ` and the earlier prose; commit `docs(site): note the ATR quarter targets on DASHBOARD-01`; (3) `produce` again and commit `docs(site): regenerate the source snapshot`; (4) `verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json` with the fixed ceilings (exit 0, identity-matched). If `origin/main` moved, merge it, re-render and redo all four.
- [ ] Render step once more and `check_generated_docs.py` (exit 0). `python3 scripts/gate/spec_gate.py --pr origin/main` (exit 0), and the same with `PR_TITLE`, `PR_BODY`, `PR_NUMBER` and `PR_DRAFT=true` set to check the body.
- [ ] Tick each done_when box with its evidence (test names, execution ids, sha256 prefixes; no promise); only then mark the PR ready. done_when[12] is ticked only as Task 18 Step 4 allows, and done_when[8] only with the production `count` shown.
- [ ] **Ask the owner once before merging:** "Merging applies the quarter marks row, nine nullable columns and the archive table to production through apply-schema-on-change; from the deploy every new brief sells a quarter at each of 25, 50, 75 and 100 percent of ATR. The Experiment is in the body. The insight's under 1.5R rule [is deployed on the average of the targets | still judges T1 alone, so nearly every plan will carry its warning]. Yes?" Merge only on that yes, recorded on the PR. Never by auto-merge.

## Close-out, after the merge (never a pre-merge box; each the owner's step, recorded on the PR)

1. **The merge** applies the row, the nine columns and the archive table. Confirm by one read that the row exists once and the columns and table are present.
2. **Deploy on the owner's yes, readers first** (Design 11, done_when[14]): the playbook resolver, the signal monitor, the API and the insight pipeline, then the brief job. Confirm by a dry run of a stored session (Decision 11, five sessions, each using one brief's model calls and approved when run), then on the next live brief, that each side prints four targets at the marks with their counts and records `feat-strat-001.v6`, and that the monitor's T1 state reads the 25 percent mark.
3. **Design 12's run,** each writing mode on the owner's yes when it runs: `count` again, then `archive`, `rebuild`, `resolve`, `verify` (clean), with `restore` available until Design 13. Then the alerts replay, `scripts/replay_signal_monitor.py --persist` over 2022-01-03 to the deploy date as `run_kind` `replay`, on its own yes. The refused rows verify lists are put to the owner one by one.
4. **Design 13's own spec and PR,** written once verify reads clean, merged only on the owner's explicit yes to the drop.
5. Outside this PR, under their own capabilities (Decision 8): `gcp/insight_discord_push.py:221` prints four targets; solyra's two target fields and the chart's three lines take four. The three other approved FEAT-STRAT-001 specs that describe the level rule are updated after the Experiment and the swap (spec Conflicts, item 1).
6. On a `docs/` branch after the merge: this plan's `status: done` and the DOC close-out the product-delivery skill prescribes.
