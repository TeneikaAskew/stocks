---
feat_id: FEAT-PLAYBOOK-001
spec: docs/superpowers/specs/2026-11-16-feat-playbook-001-prior-close-prints-r2.md
branch: feature/feat-playbook-001-prior-close-prints
pr: 2046
status: done
---

# Premarket extremes, a print at the prior close inside a bar that traded elsewhere (rule prior-close-print-v1): implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are named as the spec names them: PC1, PC1b, PC2 to PC8.

**Goal:** A premarket bar that prints the prior session's close while the rest of the bar traded more than 0.25% away gives none of its prices within 5 cents of that close to the premarket high and low, the three premarket writers record the rule, and every level basis built from then on is rule `feat-strat-001.v5`.

**Architecture:** One mask inside `lib.indicators.calculate_premarket_context`, between the shipped `stale-close-report-v1` and `thin-bar-v1`, reading the bar's own raw four prices and the prior close only. Its record is one more key of the existing `confirmed` block, so `premarket_rule_record` and the three writers carry it with no edit. `LEVEL_RULE_VERSION` moves to v5 and v4 joins v3 in `PICK_RULE_VERSIONS`, so a stored v3 or v4 basis reads as it does today and reach rates count one version at a time.

**Tech Stack:** Python, pandas, numpy, pytest (`monkeypatch`), `ast` for the one meta test, pyarrow only for the PC7 read of the exported bars.

**Spec:** docs/superpowers/specs/2026-11-16-feat-playbook-001-prior-close-prints-r2.md (r2, approved and merged in PR #2021, a7306899f on `origin/main`) governs this plan. It supersedes docs/superpowers/specs/2026-11-16-feat-playbook-001-prior-close-prints.md (r1, approved and merged in PR #2016, marked `superseded` by PR #2021), which stays as history: r2 is r1 with PC1 (ii), PC1b, PC2 and PC4 corrected from findings 1, 2, 3 and 7 below and the deploy order of finding 6 added to its Close-out step 1 (r2's "What changed from r1"). This plan was written on 5ba313612, committed on d410174b2 against r1, and bound to r2 before it merges.

**Where the line numbers come from.** PR #2010 (the brief spec's implementation) was not merged when this plan was written. Every `file:line` below was read on `origin/feature/feat-playbook-001-brief-says-what-the-data-says` at **8cd5e6859** (marked "read, 8cd5e6859"); the spec's citations carried from r1 are to 610c1ae4d, three commits earlier on the same branch, and those r2 added are to 8cd5e6859. This plan cites no line of the spec itself. More commits will land before #2010 merges. **Line numbers are as of 8cd5e6859 and must be re-read at the merge base when the implementation branch opens** (Task 1 Step 4). A cited name that no longer exists there is a stop, not a guess.

**How the claims in this plan were checked.** "read" means the file was read at the sha named. "run on a prototype" means the rule of Task 2 Step 5 and the version change of Task 6 were applied to a scratch checkout of 8cd5e6859 (not in the repo, not committed anywhere) and the command named was run there on 2026-11-16; those results are a guide for the implementer, who repeats every one on the real code. Nothing here was run against production.

## What is in this plan and what is not

8 tasks, one branch, one PR. The spec's size list has 5; here the precondition check is its own task (Task 1), the calibrated-filter case is split from the rule (Task 3), and the measurement (Task 7) is split from the records (Task 8).

In scope: PC1, PC1b, PC2, PC3, PC4, PC5, PC6, PC7, PC8.

Out of this plan:

- **The spec's Close-out.** The deploy, the one-time replay and overwrite of the 2026-11-16 row, the first-morning check and any recompute of past sessions are the owner's steps after the merge. They are listed at the end and are not tasks.
- **Anything PR #2010 owns.** This plan edits no file to make #2010 pass and opens no branch before #2010 is on main.
- **The isolated-print rule** (spec Design 5 limit 2; FEAT-DATA-001, PR #2001) and a bar wholly at the prior close (limit 1).
- **The brief's run times** (the owner's "820 and 920 with updates"): the spec leaves it as an open item for its own spec.

## Findings on the spec, reported with this plan

Each was checked as marked, on r1. None changes a decision. Findings 1, 2, 3 and 7 changed what an r1 done_when item said, and finding 6 an order r1 did not state; r2 (PR #2021) adopts all five, as PC2, PC1 (ii), PC1b, PC4 and Close-out step 1, so the tasks below build r2's text as written. Findings 4 and 5 stand as they were. Each finding keeps what was found on r1 and says what r2 made of it.

1. **r1's PC2 said one test changes expectation; more do** (run on a prototype on 8cd5e6859: the 45 test files that name the rule version, the premarket context, its record or a level basis, 22 failed and 1,809 passed; a run of the whole suite was stopped at its time limit at about 85% and is not a result). Besides `TestStaleCloseReport::test_a_bar_that_opens_or_closes_there_keeps_it`, these fail once the rule exists: `TestStaleCloseReport::test_a_cent_away_is_kept` (277.55 and 277.53 are within 5 cents of 277.54 and the bar's other prices are about a dollar away, so the rule drops them); `TestConfirmedExtremes::test_a_lone_wick_sets_no_extreme` (it asserts the exact key set of `confirmed`); `test_raw_extremes_without_an_atr[QQQ]` (the 2026-11-06 fixture: `RAW_CONFIRMED["QQQ"]` low 647.05 is the prior close, and the rule gives 649.62); four tests in `tests/gcp/test_recompute_premarket.py` through the one literal `RULE_BLOCKS` (`:50-57`, read, 8cd5e6859); and `tests/lib/test_level_params_structure.py::test_no_numbers_on_the_level_and_plan_path[lib/indicators.py]`, which fails on any module-level number `calculate_premarket_context` reads unless the name is on an allow-list (finding 7). r2's PC2 names each of these, says what `test_a_cent_away_is_kept` must still assert of the shipped rule, and names the rule-version literals of PC6 among them; Task 2 Step 7 builds it.
2. **r1's PC1 (ii) gave SPY's prior close as 754.3759; the measurement used 754.37.** `lib.strat_levels.price_cents` puts 754.3759, 754.3772 and 754.3759 on the same cent, 75438 (run on a prototype). So with 754.3759 the bar's high IS on the prior close's cent, and the sentence "within 5 cents of the prior close and not on its cent" is true only for 754.37 (cent 75437), which is what the measurement's `item5.py` passed and what the stored 2026-11-16 SPY brief row records as `prior_close` (`lb_SPY.json` in the measurement's scratch folder, read; not read from production here). r2's PC1 (ii) takes 754.37 and adds a second bar three cents away (high and close 754.40); Task 2 runs both bars at 754.37, and the case at 754.3759 is not required (r2: that value is the bar's own close, not the prior close).
3. **r1's PC1b said the merge base gives the prior close "in both" with the calibrated filter on. On the bars it named it does not** (run on a prototype against the unchanged function, thresholds of the size recorded for 2026-11-16). QQQ: rule (a) already drops the 679.89 values of the 07:35 and 07:39 bars (their open-close midpoints are 4.97 and 4.82 away, the threshold is about 0.61), so the unchanged code gives 675.30 on the written bars, and this rule counts nothing. The bar that defeats rule (a) is the 07:40 one (open and close both at 679.89, midpoint at the prior close), which is PC1 (vi)'s bar, and it is the bar the measurement names as setting the shipped value. SPY: at 754.3759 rule (a) drops the 07:00 high and close (exact cent, midpoint 1.63 away, threshold about 0.40); at 754.37 it drops neither and the unchanged code gives 754.3759. r2's PC1b names the two cases that fail on the merge base (QQQ with the 07:40 bar, SPY at 754.37) and keeps the 07:35 and 07:39 bars without the 07:40 one as a case that must stay correct; Task 3 builds those three.
4. **PC5's fixture is not on the #2010 branch.** `git ls-tree -r origin/feature/feat-playbook-001-brief-says-what-the-data-says tests/fixtures` at 8cd5e6859 lists `premarket_2026-11-06/` only. Task 1 checks it at the real merge base.
5. **The branch name.** The spec's size section says `fix/feat-playbook-001-prior-close-prints`. This plan names `feature/feat-playbook-001-prior-close-prints`, as the request for this plan stated. The gate accepts both shapes and finds the plan by the one it names.
6. **An order r1 did not state, for the Close-out.** An image that knows only v3 and v4 reads a v5 basis as "not the pick rule": `SessionLevels.from_basis` then rebuilds it with the v2 rule (`lib/strat_levels.py:1982-1983`, read, 8cd5e6859) and `plan_inputs` in the playbook resolver takes its other branch (`gcp/premarket_playbook_resolver.py:611`). Every image that reads `level_basis` needs this PR's `PICK_RULE_VERSIONS` before the first v5 brief. Read from the code, not tested against a deployed image. r2 states it as a constraint on its Close-out step 1 (not a done_when item), with a run on the unchanged code of 8cd5e6859 (a basis stamped v5 came back from `from_basis` as v2), and adds a Risks line; the Close-out below follows r2.
7. **PC4's two constants trip the "no numbers on the level path" test, which r1 did not name.** `tests/lib/test_level_params_structure.py` (`:32-51`, `:134-150`, read, 8cd5e6859) walks `calculate_premarket_context` and reports every module numeric constant it reads that is not allow-listed; `PM_MIN_EXTREME_VOLUME` is there under `ALLOWED_VOLUME` with a comment naming its spec. With the prototype it reported `PM_PRIOR_CLOSE_TOL_CENTS` and `PM_PRIOR_CLOSE_MIN_DISTANCE` (4 reads). Decision 2 chose module constants over calibrated parameters with the owner's 2026-11-08 directive in front of it, so Task 2 adds the two names to a new allow-list in that test with a comment naming decision 2. That is one more changed test and a widening of a guard the directive stands behind, so it is said here and in the PR body, not done silently. r2's PC4 now requires it (the two names beside `ALLOWED_VOLUME`, a comment naming decision 2 and the measurement, no other name added and no check removed), and r2's Risks records the widened guard.

## Global Constraints

- **Base.** `origin/main` at or after the merge of PR #2010. Branch `feature/feat-playbook-001-prior-close-prints`, one PR. This plan is committed alone on `docs/plan-feat-playbook-001-prior-close-prints` and merged before the code branch opens.
- **Exact values, copied from the spec:**
  - Rule name `prior-close-print-v1`. `PM_PRIOR_CLOSE_TOL_CENTS = 5`. `PM_PRIOR_CLOSE_MIN_DISTANCE = 0.0025` (0.25%).
  - Record: `confirmed.prior_close_prints` is `{rule: 'prior-close-print-v1', tol_cents: 5, min_distance_pct: 0.25, open, high, low, close, bars, prior_close}`; `None`, never zeros, when there is no prior close.
  - Order: `stale-close-report-v1`, `prior-close-print-v1`, `thin-bar-v1`, `two-bars-or-body-v1`.
  - `LEVEL_RULE_VERSION = 'feat-strat-001.v5'`, always; `PICK_RULE_VERSIONS` holds v3, v4 and v5. No path keeps v4 for the new rule.
  - QQQ 2026-11-16, prior close 679.89: 07:35 ET (669.95, 679.89, 669.87, 679.89, 10016); 07:39 ET (679.89, 679.89, 669.8808, 670.2492, 2121); 07:40 ET (679.89, 679.89, 669.97, 679.89, 1454), each as open, high, low, close, volume.
  - SPY 2026-11-16, prior close 754.37 (r2 PC1 (ii); r1 had 754.3759, the bar's own close, finding 2): 07:00 ET (751.12, 754.3772, 750.679, 754.3759, 3259); and r2's second bar three cents away, the same open and low with high and close 754.40 (751.12, 754.40, 750.679, 754.40, 3259; the volume is this plan's choice).
  - The kept session: prior close 277.54, three consecutive bars with all four prices within 0.25%.
  - The measurement: 2,650 sessions a ticker, 2016-05-03 to 2026-11-13, ATR None; sessions changed 221 (SPY), 236 (QQQ), 301 (IWM). The 08:20 ET cut of 2026-11-16: QQQ 675.46, SPY 752.897, IWM 276.86.
- **Not changed by this PR (spec Non-goals):** `gcp/schema.sql`; `premarket_print_filter` (rules (a) and (b)) and its masks; `pm_stale_print_atr`, `pm_spike_atr` and `lib/level_calibration.py`; the bodies of `stale-close-report-v1`, `thin-bar-v1` and `two-bars-or-body-v1`; `pre_vwap`, `pre_volume`, `gap_pct`; a trigger's rule, a target, a stop, an exit plan, the level builder's picks; any stored row; any job, schedule, table or query. The three writers (`gcp/fetchers/fetch_market_data.py`, `gcp/fetchers/fetch_premarket_refresh.py`, `gcp/backfill_ticker.py`) get no edit.
- **No silent fallback (CLAUDE.md 3.7).** A dropped value is NaN in the candidates and the extreme is `None` when nothing confirms it. No count is 0 where the rule did not run. No new `except`.
- **Tests are hermetic.** CI's test job checks out one commit and has no `origin/main` at test time, so no test runs `git show origin/main:...` or any git command against a second ref. "As on the merge base" is a literal: run the unchanged code on the branch before the task's first edit, paste the printed value into the test, and say in the PR body which literals were captured that way. The values this plan prints for them were captured on 8cd5e6859 and are re-captured at the merge base.
- **`.gitignore` ignores `*.csv`.** A fixture file with that extension is added with `git add -f`, and `git status --short` is checked for it before the commit. This plan adds no CSV; it applies if Task 5 touches one.
- **The render step.** Every commit that moves lines in `gcp/`, `lib/` or `scripts/` re-runs the inventory render, because the generated docs cite line numbers:
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py tests/meta/test_model_registry_consistency.py -q` (expect all passed), and whichever of the three docs changed is staged with the code. If `test_model_registry_consistency.py` names a moved line in `docs/models/MODEL-BRIEF-001.md`, the pointer is corrected in the same commit (the #2010 build needed two such commits, c328134bf and 610c1ae4d). Read the command from the #2010 plan as merged if its text differs.
- **`tests/lib/test_movement_statement.py` alone is not a clean signal locally.** It imports `gcp.research.strat_engine.strat_pred_serve`, which needs lightgbm (`requirements-research.txt`). Run alone on 8cd5e6859 where lightgbm is not installed it gives 41 failed, 28 passed, every failure `ModuleNotFoundError: No module named 'lightgbm'` (run, unchanged code). Run it with the research-test set beside it, as `make test` does, or with lightgbm installed, and compare with the base's result from the same invocation.
- **The PC7 measurement's scripts are not in the repo.** `measure.py` and `report.py` live at `/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/pcmeasure_out/`, a session scratch folder that may be gone. Task 7 reproduces the one number PC7 asks for from the repo alone and does not need them.
- **Production access.** No task writes to production, deploys, applies a schema, executes a job or runs `--recompute-premarket`. The only reads are Task 7 Step 1 (a download of the exported bars and one read-only statement). Ask the owner once before that step, with the two commands, and run nothing until the owner says yes.
- **Capacity (CLAUDE.md Rule 0; spec Design 6), for the PR body.** Volume: the bars already in memory, at most 330 one-minute bars a ticker. Velocity: no new statement, read or write; no new job, schedule or table. Wall-clock: a few comparisons over at most 330 rows, not measurable beside the fetch. Cost: none added. Task 4 pins "no new statement" by the writers' existing statement counts staying as they are.
- **The next version is taken.** The ATR quarter targets spec (merged as PR #2013) takes the next free version after this one, v6. If its implementation reaches main first, stop and tell the owner: the two cannot claim one number, and this plan does not renumber on its own.
- **Commits.** Conventional `type(scope): description`, imperative, no AI attribution. `python3 scripts/gate/spec_gate.py --commit` before each. The PR opens as a draft and stays one until every done_when line is ticked with evidence. Every new test has a red then green record in the PR body.

## done_when map

| done_when | What | Task |
|---|---|---|
| PC1 | the rule on written bars, both sides, filter off | 2 |
| PC1b | the rule with the calibrated filter on, and through `premarket_snapshot` | 3 |
| PC2 | the shipped rules keep their names, counts and order | 2 |
| PC3 | the three writers' rows hold the block; schema unchanged | 4 |
| PC4 | the two constants, read in one place, allow-listed by name | 2 |
| PC5 | the 2026-11-16 session on the fixture | 1, 5 |
| PC6 | rule version v5; v3 and v4 read as recorded | 6 |
| PC7 | the measurement on the shipped function | 7 |
| PC8 | records, site note, audit, gate | 8 |

## Review Focus

Inputs the spec implies and no done_when test pins, most likely first. Each has a test in the task that owns the code.

- **A morning whose only candidates are prior-close prints.** Every bar opens or closes at the prior close and trades far from it. A reader expects `pre_high` and `pre_low` of `None` with `confirmed['reason'] == 'unconfirmed'` (or the far prices, if two bars confirm them), never the prior close and never 0, and the writers then clear the extreme as they do for any rejected one. Task 2.
- **A prior close that is not a usable number.** `prev_close` of 0, a negative number or NaN: the rule does not run, `prior_close_prints` is `None`, and the extremes are what the other rules give. Task 2.
- **A bar with a missing price.** A NaN open, high, low or close is neither "at the prior close" nor an "other price"; the bar is judged by the prices it has and nothing raises. Task 2.
- **A print bar that is also thin.** A 50 share bar that closes at the prior close with the rest far away: this rule counts its dropped values, `thin['bars_excluded']` still counts the bar (it counts bars by volume, as on the merge base), and neither extreme comes from it. Task 2.
- **A stored v4 basis on the first v5 morning.** `SessionLevels.from_basis(v4).with_premarket(snap)` keeps `rule_version` v4 and its spaced targets; a version this code has never seen (`feat-strat-001.v6`) is not the pick rule. Task 6.

Not a test, a line for the PR body (spec Risks, "Constants drift"): on a ticker priced under about 20 dollars, 0.25% is under 5 cents, so the tolerance is wider than the distance and the rule drops real opens and closes near the prior close. Nothing was measured outside SPY, QQQ and IWM.

## File map

| File | Change | Task |
|---|---|---|
| `lib/indicators.py` | three constants beside `:544-547`; the rule between `:716` and `:718`; `confirmed` at `:742-752`; the docstring at `:606-635` (read, 8cd5e6859) | 2 |
| `tests/lib/test_premarket_print_filter.py` | `TestPriorClosePrint` (new); changed expectations at `:59-63`, `:329-351`, `:524-525`; `TestSession20261116` if present | 2, 3, 5 |
| `tests/gcp/test_premarket_filter_params.py` | `test_written_row_holds_the_rule_blocks` (`:449-464`), a new snapshot test | 3, 4 |
| `tests/gcp/test_recompute_premarket.py` | `RULE_BLOCKS` (`:50-57`) | 4 |
| `tests/lib/test_level_params_structure.py` | `ALLOWED_PRIOR_CLOSE` (new, beside `:51`), the union at `:138` | 2 |
| `lib/strat_levels.py` | `LEVEL_RULE_V4`, `LEVEL_RULE_VERSION`, `PICK_RULE_VERSIONS`, the comment and docstring (`:1509-1529`) | 6 |
| `lib/movement_statement.py` | comment text only at `:356-358` and `:506-507`, no line added or removed | 6 |
| `tests/lib/test_strat_levels.py`, `tests/lib/test_movement_statement.py`, `tests/gcp/test_level_basis.py`, `tests/gcp/test_premarket_playbook_resolver.py`, `tests/meta/test_level_rule_version_readers.py` | v5 | 6 |
| `docs/product/infrastructure/05-a`, `05-c`, `05-e`; `docs/models/MODEL-BRIEF-001.md` | by the render step, when a line moved | 2, 6 |
| `docs/product/02`, `03`, `12`, `docs/review-evidence/site-source-snapshot.json`, this plan | close | 8 |

---

### Task 1: Preconditions (no code)

Spec: Authority and status ("implemented in its own small PR after PR #2010 is on main"); PC5's two branches. Moves no done_when item; decides which branch of PC5 Task 5 takes.

- [ ] **Step 1: #2010 is on main.** `git fetch origin && git log origin/main --oneline -30` shows the merge of PR #2010 (`FEAT-PLAYBOOK-001: ... brief says what the data says`). Not there: stop. This branch does not open.
- [ ] **Step 2: The rule constants and the version helper exist.** Run:
  `python3 -c "import lib.indicators as i, lib.strat_levels as s; print(i.PM_MIN_EXTREME_VOLUME, i.CONFIRMED_RULE, i.STALE_CLOSE_RULE, i.THIN_BAR_RULE, s.LEVEL_RULE_V3, s.LEVEL_RULE_VERSION, s.PICK_RULE_VERSIONS, s.is_current_pick_rule(s.LEVEL_RULE_VERSION), i.premarket_rule_record)"`
  Expected: `100 two-bars-or-body-v1 stale-close-report-v1 thin-bar-v1 feat-strat-001.v3 feat-strat-001.v4 ('feat-strat-001.v3', 'feat-strat-001.v4') True <function premarket_rule_record ...>`. An `AttributeError`, or a current version that is not v4: stop and tell the owner what main holds.
- [ ] **Step 3: The 2026-11-16 fixture.** `git ls-tree -r --name-only origin/main tests/fixtures/premarket_2026_11_16/` and `grep -n "class TestSession20261116" tests/lib/test_premarket_print_filter.py`. Record both outputs and the sha of `origin/main`.
  - Listed and the class exists: Task 5 takes its first branch.
  - Empty: stop and tell the owner, with the sha and the empty output. PC5 depends on the fixture. The owner chooses between waiting for it and the spec's second branch (PC5: "when the fixture is not on the merge base, the PR body says so with the merge base's sha and git ls-tree output"). Do not build the fixture here: it is the brief spec's B8 and needs a production read this plan does not hold.
- [ ] **Step 4: Open the branch and re-read the lines.** `git checkout -b feature/feat-playbook-001-prior-close-prints origin/main`. For each `file:line` in the File map, open the file and find the named thing (`grep -n "PM_MIN_EXTREME_VOLUME\|body_there\|survives = \|'stale_close_reports': stale_reports" lib/indicators.py`; `grep -n "LEVEL_RULE_V3\|LEVEL_RULE_VERSION =\|PICK_RULE_VERSIONS" lib/strat_levels.py`). Write the lines as they are now into the PR body's first note. `git diff --stat 8cd5e6859 origin/main -- lib/indicators.py lib/strat_levels.py lib/movement_statement.py tests/lib/test_premarket_print_filter.py tests/gcp/test_premarket_filter_params.py tests/gcp/test_recompute_premarket.py` says which of them moved.
- [ ] **Step 5: The base's own result.** `make test` on the untouched branch; keep the summary line and any failure the base already has. Later tasks compare with it.

### Task 2: The two constants, the rule and its record

Spec: Design 1, 2 and 3 (the record); Decisions 1 and 2. Closes PC1, PC2 and PC4.

**Files:**
- Modify: `lib/indicators.py` (constants beside `:544-547`; the rule between the end of step 1 at `:716` and the thin bar step at `:718`; `confirmed` at `:742-752`; docstring `:606-635`)
- Test: `tests/lib/test_premarket_print_filter.py`

**Interfaces:**
- Consumes: `bars`, `mirror`, `context`, `_Side`, `SIDES`, `_replace`, `STALE_HIGH_ROWS`, `PRIOR_CLOSE = 277.54` of the test module (`:215-298`, read, 8cd5e6859); `lib.strat_levels.price_cents`.
- Produces: `lib.indicators.PM_PRIOR_CLOSE_TOL_CENTS: int = 5`, `PM_PRIOR_CLOSE_MIN_DISTANCE: float = 0.0025`, `PRIOR_CLOSE_PRINT_RULE: str = 'prior-close-print-v1'`; the key `prior_close_prints` in `calculate_premarket_context(...)['confirmed']`. `calculate_premarket_context` keeps its signature. In the test module: `QQQ_PRIOR_CLOSE`, `QQQ_OTHERS`, `QQQ_0735`, `QQQ_0739`, `QQQ_0740`, `QQQ_ROWS`, `SPY_PRIOR_CLOSE`, `SPY_OTHERS`, `SPY_0700`, `SPY_0700_3C`, `SPY_ROWS`, `PCP_ZERO(prior_close) -> dict`, used by Tasks 3 and 5.

- [ ] **Step 1: Capture the literals on the unchanged code.** Before any edit, print `pre_vwap`, `pre_volume`, `gap_pct` for `QQQ_ROWS` on both sides (prior close 679.89, filter off). On 8cd5e6859 they are: high side `672.983089915549`, `34892`, `-0.6883`; low side `686.796910084451`, `34892`, `0.6883`. Re-capture at the merge base and use what it prints.
- [ ] **Step 2: Write the bars** in `tests/lib/test_premarket_print_filter.py`, after `TestStaleCloseReport`. The low side of every case is `mirror(rows, about=<that case's prior close>)`, so the prior close is the same on both sides and the mirrored morning is the gap-up one of PC1 (iii):

```python
QQQ_PRIOR_CLOSE = 679.89  # QQQ's close of Friday 2026-11-13.
QQQ_0735 = ("07:35", 669.95, 679.89, 669.87, 679.89, 10016)
QQQ_0739 = ("07:39", 679.89, 679.89, 669.8808, 670.2492, 2121)
QQQ_0740 = ("07:40", 679.89, 679.89, 669.97, 679.89, 1454)
# Bars written here, trading 668 to 676. Without the prints: highs 675.46,
# 675.30, 670.50, 670.40, 670.30 (second-highest 675.30), highest body 675.21,
# so pre_high 675.30; lowest body 668.50 under the second-lowest low 669.80,
# so pre_low 668.50.
QQQ_OTHERS = [
    ("04:26", 675.21, 675.46, 673.65, 674.11, 3755),
    ("04:27", 674.11, 675.30, 673.90, 675.00, 4000),
    ("07:34", 670.10, 670.40, 669.90, 669.95, 5000),
    ("07:36", 670.00, 670.30, 669.80, 670.20, 5000),
    ("07:41", 670.25, 670.50, 668.00, 668.50, 5000),
]
QQQ_ROWS = sorted(QQQ_OTHERS + [QQQ_0735, QQQ_0739])
SPY_PRIOR_CLOSE = 754.37  # SPY's close of Friday 2026-11-13, as production passes it (r2 PC1 (ii)).
# High 754.3772 and close 754.3759 are on cent 75438 under price_cents, one
# cent from the prior close's 75437: inside 5 cents and off its cent.
SPY_0700 = ("07:00", 751.12, 754.3772, 750.679, 754.3759, 3259)
# r2 PC1 (ii)'s second bar: the same open and low, high and close three cents away.
SPY_0700_3C = ("07:00", 751.12, 754.40, 750.679, 754.40, 3259)
# Without the print: highs 752.897, 752.60, 751.30, highest body 752.50, so
# pre_high 752.60.
SPY_OTHERS = [
    ("04:00", 752.44, 752.897, 749.70, 752.20, 10622),
    ("04:01", 752.20, 752.60, 751.90, 752.50, 5000),
    ("07:01", 751.00, 751.30, 750.50, 750.90, 5000),
]
SPY_ROWS = sorted(SPY_OTHERS + [SPY_0700])


def PCP_ZERO(prior_close):
    return {"rule": "prior-close-print-v1", "tol_cents": 5, "min_distance_pct": 0.25,
            "open": 0, "high": 0, "low": 0, "close": 0, "bars": 0, "prior_close": prior_close}
```

- [ ] **Step 3: Write the failing tests,** class `TestPriorClosePrint`, docstring "The ATR and both thresholds are None, so rules (a) and (b) do not run and the rule stands on its own." Every test is parametrised over `SIDES` with `s = _Side(side, <prior close>)`, rows through `s.rows(...)`, prices through `s.px(...)`, and the field counts through the side (`high` on the high side is `low` on the low side; `open` and `close` are the same on both). Each asserts `pm["filtered"] is False`. Values are for the high side; all were run on a prototype for both sides.

| Test | Bars, prior close | Asserts |
|---|---|---|
| `test_qqq_prints_set_no_extreme` (i) | `QQQ_ROWS`, 679.89 | `pm[s.extreme] == approx(s.px(675.30))`, and equal to the same call on `QQQ_OTHERS`; `pm[s.other] == approx(s.px(668.50))`; `prior_close_prints == {**PCP_ZERO(679.89), "open": 1, s.stale: 2, "close": 1, "bars": 2}`; `stale_close_reports == {"rule": "stale-close-report-v1", "high": 0, "low": 0, "prior_close": 679.89}` |
| `test_the_0735_bar_still_gives_its_open_and_low` (i) | `[("07:34", 670.10, 670.40, 670.05, 670.20, 5000), QQQ_0735]`, 679.89 | `pm[s.other] == approx(s.px(669.95))` (the 07:35 open is the lowest body); `pm["confirmed"]["low_bars_below" if side == "high" else "high_bars_above"] == 1` (its low 669.87 is a candidate beyond it); `pm[s.extreme] == approx(s.px(670.20))` |
| `test_spy_print_sets_no_extreme` (ii), also parametrised over `bar` in `(SPY_0700, SPY_0700_3C)` | `sorted(SPY_OTHERS + [bar])`, 754.37 | `pm[s.extreme] == approx(s.px(752.60))`; `prior_close_prints == {**PCP_ZERO(754.37), s.stale: 1, "close": 1, "bars": 1}`; `stale_close_reports == {"rule": "stale-close-report-v1", "high": 0, "low": 0, "prior_close": 754.37}`. A comment says that under `price_cents` the 07:00 bar's high and close are one cent from the prior close and the second bar's three cents, both inside the 5 cent tolerance and off the prior close's cent, where the exact-cent rules do not see them (r2 PC1 (ii); r2 ran 752.60 with the rule and 754.40 without for the second bar) |
| `test_a_session_that_sat_at_the_prior_close_is_kept` (iv) | `[("08:00", 277.20, 277.40, 277.10, 277.35, 5000), ("08:01", 277.35, 277.50, 277.30, 277.54, 5000), ("08:02", 277.50, 277.52, 277.25, 277.30, 5000)]`, 277.54 | `pm[s.extreme] == approx(277.54)`; `prior_close_prints == PCP_ZERO(277.54)` |
| `test_a_bar_wholly_at_the_prior_close_stays` (v) | `STALE_HIGH_ROWS` with 07:35 set to high 276.60, plus `("07:40", 277.54, 277.54, 277.54, 277.54, 5000)`, 277.54 | `pm[s.extreme] == approx(277.54)`; `prior_close_prints == PCP_ZERO(277.54)` |
| `test_open_and_close_there_with_a_far_wick` (vi) | `sorted(QQQ_ROWS + [QQQ_0740])`, 679.89 | `pm[s.extreme] == approx(s.px(675.30))`; counts `"open": 2, s.stale: 3, "close": 2, "bars": 3` |
| `test_five_cents_is_at_it_and_six_is_not` (vii), parametrised `(277.59, True)`, `(277.60, False)` | `_replace(STALE_HIGH_ROWS, "07:35", high=X, close=X)`, 277.54 | dropped: `pm[s.extreme] == approx(s.px(276.60))`, counts `s.stale: 1, "close": 1, "bars": 1`; not dropped: `pm[s.extreme] == approx(s.px(X))`, `PCP_ZERO` |
| `test_another_price_exactly_a_quarter_percent_away_keeps_the_bar` (vii), parametrised `(399.00, True)`, `(398.99, False)` | `[("08:00", 398.20, 398.40, 398.10, 398.30, 5000), ("08:01", 398.30, 398.50, 398.20, 398.40, 5000), ("08:02", Y, 400.00, Y, 400.00, 5000)]`, 400.00 | kept: `pm[s.extreme] == approx(400.00)`, `PCP_ZERO(400.0)`; dropped: `pm[s.extreme] == approx(s.px(398.99))`, counts `s.stale: 1, "close": 1, "bars": 1`. 400.00 is used because `0.0025 * 400.0 == 1.0` and `abs(399.0 - 400.0) == 1.0` exactly in floats |
| `test_no_prior_close_runs_nothing` (viii), parametrised `prev` in `(None, 0.0, -1.0, float("nan"))` | `QQQ_ROWS` | `pm["confirmed"]["prior_close_prints"] is None`; `pm[s.extreme] == approx(679.89)` (the print is then just a body) |
| `test_vwap_volume_gap_and_filter_masks_are_unchanged` (ix) | `QQQ_ROWS`, 679.89 | the three literals of Step 1; and `premarket_print_filter(...)` on the same bars with `atr=16.34, stale_print_atr=0.0371, spike_atr=1.0725` returns the `stale` and `spike` masks captured on the unchanged code in Step 1 (capture them there too) |
| `test_the_shipped_rule_keeps_its_name_and_count` (PC2) | `_replace(STALE_HIGH_ROWS, "07:35", open=277.20, high=277.54, low=277.10, close=277.30)`, 277.54 | `stale_close_reports == {"rule": "stale-close-report-v1", s.stale: 1, s.other_stale: 0, "prior_close": 277.54}`; `prior_close_prints == PCP_ZERO(277.54)`; `pm[s.extreme] == approx(s.px(277.30))`; `set(pm["confirmed"]["stale_close_reports"]) == {"rule", "high", "low", "prior_close"}` |
| `test_every_bar_a_print_gives_no_extreme` (Review Focus) | `[QQQ_0740, ("07:42", 679.89, 679.89, 670.10, 679.89, 2000)]`, 679.89 | `pm[s.extreme] is None`; `pm["confirmed"]["reason"] == "unconfirmed"`; `pm[s.other] == approx(s.px(670.10))` (the two far lows confirm each other); counts `"open": 2, s.stale: 2, "close": 2, "bars": 2` |
| `test_a_bar_with_a_missing_price` (Review Focus) | `QQQ_ROWS` with the 07:35 low set to `float("nan")` | no exception; `pm[s.extreme] == approx(s.px(675.30))`; counts as in (i) |
| `test_a_thin_print_bar_is_counted_by_both` (Review Focus) | `QQQ_OTHERS + [("07:35", 669.95, 679.89, 669.87, 679.89, 50)]` | `prior_close_prints` counts `s.stale: 1, "close": 1, "bars": 1`; `pm["thin"]["bars_excluded"] == 1`; `pm[s.extreme] == approx(s.px(675.30))` |
| `test_the_constants` (PC4) | none | `(PM_PRIOR_CLOSE_TOL_CENTS, PM_PRIOR_CLOSE_MIN_DISTANCE, PRIOR_CLOSE_PRINT_RULE) == (5, 0.0025, "prior-close-print-v1")` |

- [ ] **Step 4: Run:** `python3 -m pytest "tests/lib/test_premarket_print_filter.py::TestPriorClosePrint" -q`. Expected: FAIL. On the unchanged code (i) and (vi) give the prior close `679.89` and (ii) gives the print (`754.3759` for the 07:00 bar, `754.40` for the second bar), and every record assertion raises `KeyError: 'prior_close_prints'`. Keep the output for the PR body.
- [ ] **Step 5: Implement in `lib/indicators.py`.**
  - Beside `PM_MIN_EXTREME_VOLUME` (`:544`): the three constants, with a comment that the 5 cents and the 0.25% are module constants and not calibrated parameters (decision 2), and that their measurement is the Problem section of `docs/superpowers/specs/2026-11-16-feat-playbook-001-prior-close-prints-r2.md` (2,650 sessions a ticker; not sensitive to the tolerance from 2 to 10 cents, and 0.10% changes more sessions that had real trading beside them).
  - Inside `calculate_premarket_context`, after step 1 and before the thin bar step, so the existing `survives` line (`:720`) sees it. The rule, exactly:
    1. It runs only when `_positive(prev_close)`; otherwise `prior_close_prints` is `None`.
    2. For each of the four RAW series `pre_o`, `pre_h`, `pre_l`, `pre_c` (not the filter's surviving series): a value is **at** the prior close when it is a number and `abs(price_cents(value) - price_cents(prev_close)) <= PM_PRIOR_CLOSE_TOL_CENTS`; it is an **other price** when it is a number and not at.
    3. A bar is a print bar when it has at least one value at, at least one other price, and no other price with `abs(value - float(prev_close)) <= PM_PRIOR_CLOSE_MIN_DISTANCE * float(prev_close)`. Write the distance as that float expression and no other form (a ratio such as `abs(value / prev_close - 1)` fails the exact 0.25% edge test).
    4. For each field, the values this rule drops are `at & print bar & the candidate series is not NaN` (so a value rule (a), rule (b) or step 1 already dropped is not counted again). Set them NaN in `cand_o`, `cand_h`, `cand_l`, `cand_c`.
    5. The record: `{'rule': PRIOR_CLOSE_PRINT_RULE, 'tol_cents': PM_PRIOR_CLOSE_TOL_CENTS, 'min_distance_pct': PM_PRIOR_CLOSE_MIN_DISTANCE * 100, 'open': n, 'high': n, 'low': n, 'close': n, 'bars': bars with at least one value dropped here, 'prior_close': float(prev_close)}`, counts as `int`.
  - `out['confirmed']` gains `'prior_close_prints'` after `'stale_close_reports'`. Nothing else in the function changes: `h`, `l`, `c` (the VWAP's inputs), the thin bar step and the confirmed step are as they are.
  - The docstring: the rule becomes item 2 of "Extreme rules" (thin bar 3, confirmed 4), and `prior_close_prints` is added to the `confirmed` keys under Returns.
- [ ] **Step 6: Run:** the Step 4 command. Expected: PASS.
- [ ] **Step 7: The changed expectations,** each with a comment saying why and each listed in the PR body (test, old value, new value, why). r2's PC2 names three in `TestStaleCloseReport`, `TestThinBar` and `TestConfirmedExtremes` and, outside them, the QQQ fixture case below, `RULE_BLOCKS` (Task 4), the allow-list (PC4, below) and the rule-version literals (Task 6):
  - `TestStaleCloseReport::test_a_bar_that_opens_or_closes_there_keeps_it` (`:329-337`), PC2's (1). The kept case moves to a bar whose other prices are within 0.25%: `s.rows(_replace(STALE_HIGH_ROWS, "07:35", open=277.54, high=277.54, low=277.00, close=277.10))` for `field="open"` and `open=277.10, high=277.54, low=277.00, close=277.54` for `field="close"`, asserting `pm[s.extreme] == approx(277.54)`, `stale_close_reports` zeros and `prior_close_prints == PCP_ZERO(277.54)`. The dropped case is the test's old bars, `_replace(STALE_ROWS[side], "07:35", **{field: PRIOR_CLOSE})`, whose other prices are about a dollar away: `pm[s.extreme] == approx(STALE_EXPECTED[side])`, `stale_close_reports` still zeros, and this rule's counts `s.stale: 1, field: 1, "bars": 1`.
  - `TestStaleCloseReport::test_a_cent_away_is_kept` (`:339-351`), PC2's (2). It is not weakened: what it asserts of the shipped rule stays, `stale_close_reports == {"rule": "stale-close-report-v1", "high": 0, "low": 0, "prior_close": 277.54}` on its bars (`stale-close-report-v1` is exact-cent and does not drop a value one cent from the prior close), no assertion is removed, and it is not made to pass by changing `stale-close-report-v1`, its exact-cent comparison or its count. What changes is the extreme: 277.55 and 277.53 are within 5 cents and the two bars' other prices are about a dollar away, so this rule drops both values: `pm[s.extreme] == approx(STALE_EXPECTED[side])` and `prior_close_prints == {**PCP_ZERO(277.54), s.stale: 2, "bars": 2}` (r2 ran the high side: 276.60, high 2, bars 2). It also gains the case r2 adds: the same price on the same two bars (07:31 and 07:35) with their other prices within 0.25% of 277.54, `**{s.stale: price, s.other_stale: s.px(277.10), "open": s.px(277.20), "close": s.px(277.30)}`, gives `pm[s.extreme] == approx(price)` with `stale_close_reports` zeros and `prior_close_prints == PCP_ZERO(277.54)`, dropped by neither rule. Those bars are written for this plan and were not run; r2 ran the case on its own bars (277.55 and 277.53 stay the extreme, both counts zero).
  - `TestConfirmedExtremes::test_a_lone_wick_sets_no_extreme` (`:524-525`), PC2's (3): the key set gains `"prior_close_prints"`.
  - `test_raw_extremes_without_an_atr[QQQ]`, through `RAW_CONFIRMED["QQQ"]` (`:59-63`), outside those classes and, per r2's PC2, an expected effect of the rule on a fixture session, not a test nuisance: low `647.05` becomes `649.62`, and its comment no longer says the stale rule and the confirmed rule keep the prior close. It says what r2 records instead: in `tests/fixtures/premarket_2026-11-06/QQQ.csv` (prior close 647.05, ATR None) the 07:35 ET bar (open 657.44, high 657.58, low 647.05, close 647.05, volume 2839) and the 07:38 ET bar (open 657.50, high 658.27, low 647.05, close 647.05, volume 2856) close at the prior close with their open and high more than 0.25% above it, so the rule drops the close and the low of each, and the low is the second-lowest surviving low, 649.62 at 04:04 ET (the lowest, 647.535 at 08:32 ET, is one bar's lone wick; the lowest surviving body is 652.53). Read those bars in the fixture and confirm them before changing the literal.
  - `tests/lib/test_level_params_structure.py` (PC4; finding 7): add `ALLOWED_PRIOR_CLOSE = {"PM_PRIOR_CLOSE_TOL_CENTS", "PM_PRIOR_CLOSE_MIN_DISTANCE"}` beside `ALLOWED_VOLUME` (`:51`), with a comment naming decision 2 of `docs/superpowers/specs/2026-11-16-feat-playbook-001-prior-close-prints-r2.md` (the tolerance and the distance are module constants, not calibrated parameters) and its measurement (that spec's Problem section), and add it to the union in `_violations` (`:138`), so `test_no_numbers_on_the_level_and_plan_path[lib/indicators.py]` passes. No other name joins that test's allow-lists and no check of it is removed. The rule's code holds no number literal other than the `100` that turns the fraction into a percent (100 is in `ALLOWED_VALUES`); the module docstring's list of allowed names gains the two.
  - `TestConfirmedExtremes::test_rule_record_is_the_two_blocks` (`:608-614`): unchanged, and must still pass (the record is still `{"confirmed", "thin"}`).
  Anything else that fails is read, explained and listed; an expectation is never changed to make a test pass without the reason beside it.
- [ ] **Step 8: Run:** `python3 -m pytest tests/lib/test_premarket_print_filter.py tests/lib/test_premarket_filter_calibrated_2026_11_06.py tests/lib/test_indicators.py tests/lib/test_level_params_structure.py -q` (expect all passed), then `grep -rn "PM_PRIOR_CLOSE_" lib gcp platform scripts` (expect hits in `lib/indicators.py` only; the output goes in the PR body for PC4), and `git diff origin/main -- tests/lib/test_level_params_structure.py` (expect only the new set with its comment, the set added to the union and the two names added to the docstring: no other name and no removed check; PC4).
- [ ] **Step 9: The render step** (Global Constraints), then **commit:** `fix(levels): drop a print at the prior close from a bar that traded elsewhere`. `tests/gcp/test_recompute_premarket.py` is red until Task 4; say so in the commit body, or fold Task 4 Step 3 into this commit if a red commit is not acceptable on the branch.

### Task 3: The rule with the calibrated filter on, and through the snapshot

Spec: Problem ("Rule (a) ... passes"), "With the calibrated filter on"; Design 1 ("the result does not depend on whether rules (a) and (b) ran"). Closes PC1b as r2 words it: the two cases that fail on the merge base, (1) QQQ with the 07:40 bar and (2) SPY at 754.37, and the case that must stay correct, the 07:35 and 07:39 bars without the 07:40 one. Findings 2 and 3 above are why r2 words it so.

**Files:**
- Test: `tests/lib/test_premarket_print_filter.py` (in `TestPriorClosePrint`), `tests/gcp/test_premarket_filter_params.py`

**Interfaces:**
- Consumes: Task 2's bars and `PCP_ZERO`; `gcp.fetchers.fetch_market_data.premarket_snapshot(ticker, session_date, bars, prior, level_params, read_at, *, recorded_filter=None) -> dict | None` (`:385-467`, read, 8cd5e6859); `tests.lib.level_params_fixtures.legacy_db`.
- Produces: nothing later tasks use.

- [ ] **Step 1: Write `TestPriorClosePrint::test_with_calibrated_filter`,** parametrised over `SIDES` and these cases. The thresholds are of the size the 2026-11-16 brief rows record (QQQ ATR 16.338, `pm_stale_print_atr` 0.03712, `pm_spike_atr` 1.0725; SPY 11.036, 0.03593, 0.9423; read from the measurement's scratch copies of those rows, not from production here; if Task 1 found the fixture, read them from its brief rows instead and say so):

```python
QQQ_FILTER = {"atr": 16.34, "stale_print_atr": 0.0371, "spike_atr": 1.0725}
SPY_FILTER = {"atr": 11.04, "stale_print_atr": 0.0359, "spike_atr": 0.9423}
```

| Case | Bars, prior close, filter | Asserts (high side) |
|---|---|---|
| (1) the 07:40 bar, which rule (a) passes; fails on the merge base (679.89) | `sorted(QQQ_ROWS + [QQQ_0740])`, 679.89, `QQQ_FILTER` | `pm["filtered"] is True`; `pm[s.extreme] == approx(s.px(675.30))`; `prior_close_prints` counts `"open": 1, s.stale: 1, "close": 1, "bars": 1`; `pm["excluded_prior_close_prints"] == 4`; same extreme with the inputs None |
| (2) SPY at 754.37; fails on the merge base (754.3759) | `SPY_ROWS`, 754.37, `SPY_FILTER` | `pm["filtered"] is True`; `pm[s.extreme] == approx(s.px(752.60))`; counts `s.stale: 1, "close": 1, "bars": 1`; `pm["excluded_prior_close_prints"] == 0`; same extreme with the inputs None |
| must stay correct: the 07:35 and 07:39 bars without the 07:40 one; fails on the merge base only on the record key | `QQQ_ROWS`, 679.89, `QQQ_FILTER` | `pm["filtered"] is True`; `pm[s.extreme] == approx(s.px(675.30))`; `pm["excluded_prior_close_prints"] == 4` (rule (a) drops the four values first, and they are counted once, there); `prior_close_prints == PCP_ZERO(679.89)`; the same call with the three inputs None gives the same `pm[s.extreme]` |

  The case at r1's SPY value, 754.3759, is not required (r2: that value is the bar's own close, not the prior close) and is not written.

  In every case the masks `premarket_print_filter` returns for those bars and inputs equal the literals captured on the unchanged code (capture them before Task 2's edit, or from a checkout of the merge base, and paste them).
- [ ] **Step 2: Write `test_snapshot_drops_a_prior_close_print` in `tests/gcp/test_premarket_filter_params.py`:** call `fmd.premarket_snapshot("QQQ", date(2026, 11, 16), bars, {"close": 679.89, "open": 679.89, "atr_14": 16.34, "atr_5": 16.34}, lp, read_at)` where `lp = legacy_db(["QQQ"], overrides={"pm_stale_print_atr": 0.0371, "pm_spike_atr": 1.0725}).load(["QQQ"], date(2026, 11, 16))["QQQ"]` and `bars` holds `sorted(QQQ_ROWS + [QQQ_0740])` with `ts` as aware UTC instants built through `lib.eastern_time.eastern_bounds_utc`, as `tests/gcp/test_recompute_premarket.py::premarket_bars` builds its own (`:24-35`). Assert `snapshot["pre_filter_status"] == "ok"`, `snapshot["pre_high"] == pytest.approx(675.30)`, and `snapshot["pre_filter_params"]["confirmed"]["prior_close_prints"]["bars"] == 1`.
- [ ] **Step 3: Run:** `python3 -m pytest "tests/lib/test_premarket_print_filter.py::TestPriorClosePrint::test_with_calibrated_filter" tests/gcp/test_premarket_filter_params.py::test_snapshot_drops_a_prior_close_print -q`. Expected: PASS on the branch. For the red record, run the same two on a checkout of the merge base with the test file copied in: the 07:40 case, the 754.37 case and the snapshot test fail there with `pre_high` at the print (`679.89`, `754.3759`, `679.89`), and the case that must stay correct fails there only on the record key. Put that table in the PR body under PC1b and finding 3.
- [ ] **Step 4: Commit:** `test(levels): hold the prior-close print rule with the calibrated filter on`.

### Task 4: The three writers' rows hold the block

Spec: Design 3. Closes PC3.

**Files:**
- Test: `tests/gcp/test_premarket_filter_params.py` (`:449-464`), `tests/gcp/test_recompute_premarket.py` (`:50-57`)
- No source file: `premarket_rule_record` (`lib/indicators.py:775-778`) returns the whole `confirmed` block and the writers merge it at `gcp/fetchers/fetch_market_data.py:466`, `gcp/fetchers/fetch_premarket_refresh.py:272-273` and `gcp/backfill_ticker.py:549-550` (read, 8cd5e6859).

**Interfaces:**
- Consumes: `WRITERS`, `_params`, `_record`, `_session_bars`, `test_schema_is_unchanged` of the test module.

- [ ] **Step 1: Extend `test_written_row_holds_the_rule_blocks`** (parametrised over the three writers already). On the 2026-11-06 QQQ bars it runs today, add `assert rec["confirmed"]["prior_close_prints"] == {"rule": "prior-close-print-v1", "tol_cents": 5, "min_distance_pct": 0.25, "open": 0, "high": 0, "low": 0, "close": 0, "bars": 0, "prior_close": 647.05}`. Then a second row from written bars, same writer and parameters:

```python
bars = _session_bars([
    ("08:00", 655.10, 655.40, 655.00, 655.30, 5000),
    ("08:01", 655.30, 655.60, 655.20, 655.50, 5000),
    ("08:02", 647.05, 655.70, 647.05, 647.05, 5000),   # opens and closes at the prior close
    ("08:03", 655.50, 655.70, 655.30, 655.40, 5000),
])
row = writer(monkeypatch, "QQQ", lp, bars=bars)
rec = _record(row)
assert row["pre_filter_status"] == "ok"
assert row["pre_low"] == pytest.approx(655.10)          # 647.05 on the merge base
assert rec["confirmed"]["prior_close_prints"] == {
    "rule": "prior-close-print-v1", "tol_cents": 5, "min_distance_pct": 0.25,
    "open": 1, "high": 0, "low": 1, "close": 1, "bars": 1, "prior_close": 647.05}
assert rec["confirmed"]["stale_close_reports"] == {
    "rule": "stale-close-report-v1", "high": 0, "low": 0, "prior_close": 647.05}
```

  (Run on a prototype for all three writers: `pre_high` 655.70, `pre_low` 655.10, status `ok`, the counts above.)
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_premarket_filter_params.py -q`. Expected: all passed, `test_schema_is_unchanged` among them (it pins the sha256 of `gcp/schema.sql`; this PR does not touch the file). For the red record: on the merge base the new assertions fail with `KeyError: 'prior_close_prints'`.
- [ ] **Step 3: `RULE_BLOCKS` in `tests/gcp/test_recompute_premarket.py`** gains, inside `"confirmed"` after `"stale_close_reports"`, `"prior_close_prints": {"rule": "prior-close-print-v1", "tol_cents": 5, "min_distance_pct": 0.25, "open": 0, "high": 0, "low": 0, "close": 0, "bars": 0, "prior_close": 99.0}`. Four tests read that literal (`test_the_snapshot_is_the_one_place`, `test_the_nightly_keeps_a_stored_price_when_the_new_one_is_none`, `test_the_dry_run_report_equals_the_expected_table`, `test_an_unchanged_row_with_a_marker_is_already_current`; run on a prototype). List the one changed literal in the PR body.
- [ ] **Step 4: Run:** `python3 -m pytest tests/gcp/test_recompute_premarket.py tests/gcp/test_premarket_filter_callers.py tests/gcp/test_fetch_premarket_refresh.py tests/gcp/test_premarket_provenance.py -q` (expect all passed), then `git diff --stat origin/main -- gcp/` (expect empty: no writer was edited).
- [ ] **Step 5: Commit:** `test(fetchers): the three premarket writers record the prior-close print rule`.

### Task 5: The 2026-11-16 session

Spec: Problem ("What that left on 2026-11-16"), "The candidates"; Design 5 limit 2. Closes PC5 by whichever branch Task 1 Step 3 found.

**Files:**
- Test: `tests/lib/test_premarket_print_filter.py` (class `TestSession20261116`, written by #2010)

- [ ] **Step 1 (fixture on the merge base): read the extremes by hand first.** For each of SPY, QQQ and IWM, from the fixture's bars up to that ticker's recorded cutoff (the brief row's `level_basis.premarket.fetched_at`), with the row's own prior close, ATR and thresholds: list the bars this rule drops, the bars the shipped rules drop, the second-highest surviving high, the highest surviving body, and the same for the low. Write the working as a comment beside each literal. Only then run the code.
- [ ] **Step 2: Change the literals of `TestSession20261116`** that the rule moves (its confirmed highs and lows), and add `test_prior_close_prints_of_the_session`: for each ticker, `confirmed["prior_close_prints"]` equals the counts read by hand. A hand-read value the code does not return is a finding for the owner with the bars, never a changed expectation.
- [ ] **Step 3: Run:** `python3 -m pytest "tests/lib/test_premarket_print_filter.py::TestSession20261116" -q`. Expected: PASS.
- [ ] **Step 4: The PR body table.** Per ticker: the hand-read `pre_high` and `pre_low` beside the measurement's values for the 08:20 ET cut (highs QQQ 675.46, SPY 752.897, IWM 276.86), with each difference explained. Three differences to expect and check, not assume: the measurement cut the bars before 08:20:00 ET while the recorded `fetched_at` values are about 08:20:50 ET, so the fixture's cut may hold the 08:20 bar; the measurement read the vendor's bars that day while the fixture holds the stored ones (the spec's "not checked"); and SPY's prior close is 754.37 in the row (finding 2).
- [ ] **Step 5 (fixture not on the merge base, and the owner chose the spec's second branch in Task 1):** no test. The PR body says the fixture is not on the merge base, with `git merge-base HEAD origin/main` and the empty `git ls-tree -r --name-only <that sha> tests/fixtures/premarket_2026_11_16/` output.
- [ ] **Step 6: Commit** (first branch only; `git add -f` for any fixture file `.gitignore` hides): `test(levels): pin the 2026-11-16 extremes under the prior-close print rule`.

### Task 6: The level rule is v5; v3 and v4 read as recorded

Spec: Decision 3; Design 4. Closes PC6.

**Files:**
- Modify: `lib/strat_levels.py` (`:1509-1529`); `lib/movement_statement.py` (comment text at `:356-358`, `:506-507`, the same number of lines)
- Test: `tests/lib/test_strat_levels.py`, `tests/lib/test_movement_statement.py`, `tests/gcp/test_level_basis.py`, `tests/gcp/test_premarket_playbook_resolver.py`, `tests/meta/test_level_rule_version_readers.py`

**Interfaces:**
- Consumes: `is_current_pick_rule(version) -> bool` (`lib/strat_levels.py:1525-1529`), `SessionLevels.from_basis` (`:1948`), `_assemble` (`:2444-2449`), `_fetch_reach_rates(ticker, side, query_fn, rule_version=None)` (`lib/movement_statement.py:352`), all unchanged in body.
- Produces: `lib.strat_levels.LEVEL_RULE_V4 = 'feat-strat-001.v4'`; `LEVEL_RULE_VERSION = 'feat-strat-001.v5'`; `PICK_RULE_VERSIONS = (LEVEL_RULE_V3, LEVEL_RULE_V4, LEVEL_RULE_VERSION)`.

- [ ] **Step 1: Capture on the unchanged code:** `_picks_of(SessionLevels.from_basis(d8_basis()))` and both sides' `.plan` (the fixture is stamped with the current version, v4, at `tests/lib/session_levels_helpers.py:40`). On 8cd5e6859 they equal `V3_D8_PICKS` and `V3_D8_PLAN` (`tests/lib/test_strat_levels.py:1833-1843`, asserted at `:1879`). Re-capture at the merge base.
- [ ] **Step 2: Write the failing tests.**
  - `tests/lib/test_strat_levels.py`:
    - `test_v4_basis_rebuilds_as_on_the_merge_base`: `sl = SessionLevels.from_basis({**d8_basis(), 'rule_version': 'feat-strat-001.v4'})`; assert `LEVEL_RULE_VERSION != 'feat-strat-001.v4'`, `sl.rule_version == 'feat-strat-001.v4'`, `_picks_of(sl) == V3_D8_PICKS` (Step 1's capture), `sl.long.plan == sl.short.plan == V3_D8_PLAN`, `sl.to_basis()['rule_version'] == 'feat-strat-001.v4'`.
    - `test_v4_basis_keeps_its_rule_under_a_new_premarket_snapshot` (Review Focus): the v4 copy of `test_v3_basis_keeps_its_rule_under_a_new_premarket_snapshot` (`:1882-1894`), same assertions with v4.
    - `test_a_new_build_records_v5`, replacing `test_a_new_build_records_v4` (`:1871-1879`): `LEVEL_RULE_VERSION == 'feat-strat-001.v5'`; `SessionLevels(ticker='TST', session_date=None).rule_version == 'feat-strat-001.v5'`; `built = SessionLevels.from_basis(d8_basis())` has `built.rule_version == built.to_basis()['rule_version'] == 'feat-strat-001.v5'`; `_picks_of(built) == V3_D8_PICKS`.
    - `test_is_current_pick_rule` (`:1897-1908`): `LEVEL_RULE_V4 == 'feat-strat-001.v4'`, `PICK_RULE_VERSIONS == (V3, 'feat-strat-001.v4', 'feat-strat-001.v5')`, true for v3, v4 and v5, false for `None`, `''`, v1, v2 and `'feat-strat-001.v6'`.
    - The two literals at `:1448` and `:1509` become `'feat-strat-001.v5'`.
  - `tests/lib/test_movement_statement.py`: add `V5_RULE = "feat-strat-001.v5"`; `_VersionedRows.counts` (`:1316-1317`) gains `V5_RULE: {"trigger": (3, 2), "t1": (3, 1)}`; `test_reach_rates_do_not_mix_rule_versions` (`:1339-1357`) is parametrised `(V5_RULE, {"trigger": (2, 3), "t1": (1, 3)})`, `(V4_RULE, {"trigger": (1, 4), "t1": (0, 4)})`, `(V3_RULE, {"trigger": (9, 10), "t1": (8, 10)})`, body unchanged (it already asserts `q.bound == [session_rule, session_rule]`). `test_reach_rates_default_to_the_current_rule` (`:1360-1372`) binds `[LEVEL_RULE_VERSION] == [V5_RULE]` with `sample_n == 3`, and its tracked row is built with `V5_RULE`. `:1391-1392` gain the same two assertions for `V5_RULE`.
  - `tests/gcp/test_level_basis.py:462`: the literal becomes `"feat-strat-001.v5"`.
  - `tests/gcp/test_premarket_playbook_resolver.py:1211`: the parameter list becomes v3, v4 and v5.
  - `tests/meta/test_level_rule_version_readers.py:15`: `WATCHED` gains `'LEVEL_RULE_V4'`, and its docstring says v3, v4 and v5.
- [ ] **Step 3: Run:** `python3 -m pytest tests/lib/test_strat_levels.py tests/gcp/test_level_basis.py tests/gcp/test_premarket_playbook_resolver.py tests/meta/test_level_rule_version_readers.py -q`. Expected: FAIL (`ImportError: cannot import name 'LEVEL_RULE_V4'`, and `'feat-strat-001.v4' != 'feat-strat-001.v5'`).
- [ ] **Step 4: Implement in `lib/strat_levels.py`:** the three constants of Produces, a comment block for v5 in the style of v4's (`:1515-1518`): "v5 (2026-11-16 prior-close prints): the pick rule is v3's. A print at the prior close inside a bar that traded elsewhere no longer sets the premarket high or low (rule prior-close-print-v1), so v5 marks those extremes and v4 marks the ones before it." `is_current_pick_rule`'s docstring says v3, v4 or v5; its body is unchanged. In `lib/movement_statement.py` reword the two comments that say "v3 or v4" in place, adding and removing no line.
- [ ] **Step 5: Run:** Step 3's command, then `python3 -m pytest tests/ -q --ignore=tests/integration` (the whole collection, for the lightgbm constraint). Expected: no failure that Task 1 Step 5 did not record for the base. Then `grep -rn "feat-strat-001\.v4" lib gcp platform scripts` (expect one hit: the `LEVEL_RULE_V4` constant).
- [ ] **Step 6: The render step, then commit:** `feat(levels): mark the prior-close print extremes as rule v5 and read v4 as before`.

### Task 7: The measurement repeated on the shipped function, and the whole suite

Spec: Problem ("How often", "The candidates"); Risks ("The measurement used a prototype"). Closes PC7. **Read-only production access: ask the owner once before Step 1, with its two commands. Not assumed approved.**

- [ ] **Step 1: The inputs, read only, on the owner's yes.**
  - The exported bars: `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud storage cp -r gs://adept-mountain-474619-d4-trading-data/intraday-bars/v1/1min/SPY gs://adept-mountain-474619-d4-trading-data/intraday-bars/v1/1min/QQQ gs://adept-mountain-474619-d4-trading-data/intraday-bars/v1/1min/IWM <bars_dir>/` (the path `gcp/fetchers/export_intraday_bars.py:1-10` documents; confirm the bucket name from `GCS_BUCKET` in `gcp/deploy.sh` before running). `read_bars` checks every month file against the manifest's sha256.
  - The prior closes: `./scripts/db_query_cr.sh -q "SELECT ticker, date, close FROM market_data_daily WHERE ticker IN ('SPY','QQQ','IWM') AND date >= '2016-04-29' AND date <= '2026-11-13' ORDER BY ticker, date"` with no `--commit` (about 7,950 rows, under the 50,000 row cap); save the execution's `result_001.csv` (under `gs://adept-mountain-474619-d4-trading-data/query-results/<execution>/`) as `<daily_csv>`. Record the execution id.
- [ ] **Step 2: A checkout of the merge base beside the branch:** `git worktree add --detach <base_dir> $(git merge-base HEAD origin/main)`.
- [ ] **Step 3: Run this script once a ticker** (`python3 pc7.py <branch_dir> <base_dir> <bars_dir> <daily_csv> SPY`, then QQQ, then IWM). It is kept out of the repo and pasted whole into the PR body; it calls `calculate_premarket_context` only, so it replays no fire decision (CLAUDE.md 3.6). The base's function is loaded from its file and finds `price_cents` in the branch's `lib.strat_levels`, which this PR does not change.

```python
"""PC7. usage: pc7.py <head_worktree> <base_worktree> <bars_root> <daily_csv> <TICKER>
Read only: local files in, one line and a CSV text out. No database, no bucket write."""
import importlib.util
import sys

import pandas as pd

HEAD, BASE, BARS, DAILY, T = sys.argv[1:6]
sys.path.insert(0, HEAD)
import lib.indicators as head                                        # noqa: E402
from gcp.fetchers.export_intraday_bars import read_bars              # noqa: E402
from lib.eastern_time import previous_session, utc_to_eastern_naive  # noqa: E402

spec = importlib.util.spec_from_file_location("indicators_base", f"{BASE}/lib/indicators.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

daily = pd.read_csv(DAILY, usecols=["ticker", "date", "close"], low_memory=False)
close = daily[daily.ticker == T].set_index("date")["close"]
bars, months = read_bars(BARS, T, "2016-05", "2026-11")
print("inferred_rows", sum(m.get("inferred_rows") or 0 for m in months))
et = utc_to_eastern_naive(bars["ts"])
tod = et.dt.time
pre = bars[(tod >= head.PREMARKET_START) & (tod < head.REGULAR_SESSION_OPEN)].assign(day=et.dt.date)
sessions, changed = 0, []
for day, g in pre.groupby("day", sort=True):
    prev = previous_session(day).isoformat()
    if not ("2016-05-03" <= day.isoformat() <= "2026-11-13"):
        continue
    if prev not in close.index or pd.isna(close[prev]):
        continue
    g = g.reset_index(drop=True)
    kw = dict(times=g["ts"], open_=g["open"], high=g["high"], low=g["low"], close=g["close"],
              volume=g["volume"], prev_close=float(close[prev]),
              atr=None, stale_print_atr=None, spike_atr=None)
    new, old = head.calculate_premarket_context(**kw), base.calculate_premarket_context(**kw)
    sessions += 1
    if (new["pre_high"], new["pre_low"]) != (old["pre_high"], old["pre_low"]):
        changed.append((day.isoformat(), old["pre_high"], new["pre_high"], old["pre_low"], new["pre_low"]))
print(T, "sessions", sessions, "changed", len(changed),
      "high", sum(1 for c in changed if c[1] != c[2]), "low", sum(1 for c in changed if c[3] != c[4]))
pd.DataFrame(changed, columns=["date", "base_high", "head_high", "base_low", "head_low"]).to_csv(
    sys.stdout, index=False)
```

- [ ] **Step 4: Compare.** Expected, per ticker: `sessions 2650`, and `changed` beside the spec's **221 (SPY), 236 (QQQ), 301 (IWM)**. This script, run on 2026-11-16 with the prototype of Task 2 Step 5 as the head, 8cd5e6859 as the base, a local copy of the exported bars and a local export of the daily closes, printed `SPY sessions 2650 changed 221 high 84 low 137`, `QQQ sessions 2650 changed 236 high 87 low 149`, `IWM sessions 2650 changed 301 high 119 low 182`, `inferred_rows 0` for each. A different count on the shipped function is reported with the dates that differ (the CSV text says which) and explained, never rounded away; a session count other than 2,650 means the inputs differ from the measurement's (a later export, a missing daily row) and is said first. The three lines, the execution id and the script go in the PR body.
- [ ] **Step 5: The whole suite.** `make test` (expect no failure that Task 1 Step 5 did not record for the base). Then `git diff --stat origin/main -- gcp/schema.sql gcp/deploy.sh lib/level_calibration.py gcp/fetchers gcp/backfill_ticker.py gcp/signal_monitor.py lib/strategies platform/api` (expect empty).
- [ ] **Step 6: The list of changed expectations** for the PR body: every test whose expectation Tasks 2, 4 and 6 changed, with old value, new value and why (PC2's last clause). No commit: this task adds no file.

### Task 8: Close: product record, site note, generated docs and the gate

Spec: Capability; PC8; product-delivery Phase 4 and Phase 5. Closes PC8. Once the site-note steps start, no file under `gcp/`, `lib/`, `scripts/` or `tests/` changes without redoing them: the source hash covers those paths.

- [ ] Push with `git push -u origin feature/feat-playbook-001-prior-close-prints` and open a **draft** PR titled `FEAT-PLAYBOOK-001: drop a print at the prior close from the premarket extremes`. Body: the spec's and this plan's exact paths; PC1 to PC8 as `- [ ]` lines that start with each item's text; `Red then green`; the Capacity section (Volume, Velocity, Wall-clock, Cost from Global Constraints); the seven findings above with what each task did about them; Task 1 Step 4's line note; Task 2 Step 8's grep; Task 3 Step 3's table; Task 5 Step 4's table or Step 5's statement; Task 7's three lines and script; the changed-expectation list; the low-priced-ticker line from Review Focus; and the Close-out list below. The spec lists no canvas, so no canvas marker.
- [ ] Set `pr:` in this plan to the PR's number.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, the `### FEAT-PLAYBOOK-001` record (`:205` on `origin/main` d410174b2): append this PR to the Status text (implementation under review, not deployed) and set Last reviewed to the date of the PR's head commit. Touch no other record.
- [ ] `docs/product/12-PR-ISSUE-TRACEABILITY.md`, `### FEAT-PLAYBOOK-001` (`:631`): append the PR to its lineage, naming spec PR #2021 (r2, the governing spec), spec PR #2016 (r1, superseded) and the plan's PR. Commit both docs and the plan: `docs(product): record the prior-close print rule under FEAT-PLAYBOOK-001`.
- [ ] The render step once more (Global Constraints), and `python3 -m pytest tests/scripts/test_check_generated_docs.py tests/meta/test_model_registry_consistency.py -q` (expect all passed). `docs/models/MODEL-BRIEF-001.md` cites lines of `lib/movement_statement.py`, `gcp/premarket_brief.py` and `lib/config.py`; this PR is written to move none of them (Task 6 edits comment text in place). If the test names one, correct that pointer and commit `docs(models): point the brief model record at the moved lines`. `07-MODEL-REGISTRY.md` is not touched, so `export_model_registry.py` is not run.
- [ ] Site note, step 1: with a clean tree, `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`; copy its `source_identity_sha256`.
- [ ] Site note, step 2: in `docs/product/03-SITE-TRACEABILITY.md`, the `| FEAT-PLAYBOOK-001 | DASHBOARD-01 |` row (`:1334` on d410174b2; #2010 rewrites it, so re-find it) and no other byte: `source_identity_sha256=<the new hash>; `, then this change's prose (the brief's premarket high and low no longer take a print at the prior close from a bar whose other prices are all more than 0.25% away, rule `prior-close-print-v1`, recorded in `pre_filter_params.confirmed.prior_close_prints` by the three premarket writers; a level basis built under it is rule `feat-strat-001.v5` and v3 and v4 rebuild as recorded; the tests named; backend implementation and local tests only, rollout pending), then ` Earlier: ` and the earlier prose unchanged. Commit: `docs(site): note the prior-close print rule on DASHBOARD-01`.
- [ ] Site note, steps 3 and 4: run `produce` again and commit `docs(site): regenerate the source snapshot`; then `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 16777216 --max-entries 20000` (expect exit 0; 16 MiB is the ceiling since PR #2011, b1ce1b8f0). If `origin/main` moved, update the branch, re-render and redo the four steps. Use the ceilings the skill on `origin/main` states at that time if they differ.
- [ ] Docs audit: `python3 scripts/maintenance/docs_audit.py` on the branch and on a detached `origin/main` worktree; the branch reports no line that `main` does not.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` (expect exit 0).
- [ ] Push; tick each done_when box with its evidence (test name, command output, file); only then mark the PR ready. No gate file is touched, so no red-team pass is owed. After the merge, on a `docs/` branch: this plan's `status: done`.

## Close-out (not tasks; the owner's steps)

From the spec's Close-out and its decision 5. None is done by the implementer, none is a done_when box, and each starts on the owner's own yes at the time it is run.

1. **Deploy** the brief job and the fetchers from `main` at or after the merge. Deploy order (r2 Close-out step 1, a constraint on this step and not a done_when item; finding 6): every image that reads a stored `level_basis` (the playbook resolver, the API, the signal monitor, the insight pipeline) takes this change's `PICK_RULE_VERSIONS` before or with the brief job, so no reader meets a v5 basis it does not know. An image that knows only v3 and v4 does not refuse a v5 basis: it rebuilds it under the v2 rule, silently (r2 Risks), and the deploy order is the only protection.
2. **The one-time replay of 2026-11-16, after step 1.** The owner approved overwriting that row once, after the fixed brief code is deployed. It stays the owner's step when it is run: the implementer does not run it, and running it before the deploy would write QQQ 679.89 and SPY 754.3759 as the corrected values (spec decision 5). Design 5 limit 2 applies to what it writes: a late read of 2026-11-16 holds 680.399 for QQQ with or without this rule.
3. **The first scheduled morning after the deploy:** `confirmed.prior_close_prints` in that morning's `pre_filter_params` for SPY, QQQ and IWM, and the premarket high and low beside the owner's market data.
4. **Any recompute of past sessions** (spec decision 4), by range, with its own before and after counts. `pre_filter_params` gains a block, so a recompute reports every session as changed; that is expected.
