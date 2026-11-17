---
feat_id: FEAT-STRAT-001
spec: docs/superpowers/specs/2026-11-17-feat-strat-001-target-hit-rates-r2.md
branch: feature/feat-strat-001-target-hit-rates-r2
pr: null
status: ready
---

# Each quarter-target line can say how often price reached it before the stop: implementation plan (r2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the order of the spec's frontmatter, [0] (Policy) to [14] (catalog, gate and production yeses).

**Goal:** Store, for every ticker-day since 2022-01-03, how far price went past the trigger before the stop, in stop distances and in ATR, keyed by the rule version that sets the trigger and stop; and give the brief one reader that turns those rows into "reached k of n (p%)" for any distance. This change prints nothing new: a basis whose targets the level rule picked prints exactly what main prints. The quarter-target change (spec r3, its Designs 4 and 7) prints the counts on its target and waypoint lines through this reader.

**Architecture:** `resolve_plan`'s entry walk moves into one private helper that `resolve_plan` and a pure `plan_excursion` both call. `plan_excursion` returns one side's fill bar, stop bar and four excursions (touch and held 5, each in stop distances and in ATR). `trade_of_day` keeps the side that filled first. `entry_rule_version` in `lib/strat_levels.py` names the version whose trigger and stop rule a basis uses. `resolve_one` upserts or deletes the day's `plan_excursions` row in the transaction that updates `premarket_analysis`. `lib/target_reach.py` reads every row of the run's tickers in one query, filtered to the entry version, and formats the count text. `format_levels_for_brief` takes the reach table and passes it on without printing it. `gcp/backfill_plan_excursions.py` replays the brief's level build per session with its writes switched off and upserts history rows.

**Tech Stack:** Python, pandas, numpy, SQLAlchemy `text()` through `gcp.database`, argparse, pytest (`monkeypatch`), Postgres 15 in CI for `tests/integration/`.

**Spec:** docs/superpowers/specs/2026-11-17-feat-strat-001-target-hit-rates-r2.md (approved, stocks #2051, merged to `main` at b9d00cd78 on 2026-11-17). It supersedes r1, whose plan (`docs/superpowers/plans/2026-11-16-feat-strat-001-target-hit-rates.md`, branch `feature/feat-strat-001-target-hit-rates`) binds the superseded spec and its branch for good, so this plan names a new branch. That r1 branch was never pushed and never opened as a PR; its commits are carried onto this branch (Task 0) and changed here where r2 differs.

## Global Constraints

- Base: `origin/main` at or after b9d00cd78. Line numbers below are from that commit; recheck them on the base actually used. Branch `feature/feat-strat-001-target-hit-rates-r2`. This plan is committed alone on `docs/plan-feat-strat-001-target-hit-rates-r2` and merged before the code branch opens.
- Values are never hard-coded. The window (`since` or `lookback_sessions`), the measure (`touch_atr`, `held_5m_atr`, `touch` or `held_5m`) and the minimum sample come only from the `target_reach_rate` policy row.
- R and every distance are the stock's move in stop distances or in ATR. No copy, comment, log line or test name speaks of money, profit or cost.
- 1-minute bars are as-traded and come only from `market_data_intraday` (the store the nightly fills). The history job reads nothing else for bars.
- No separate ladder and no count on a thirds line: r1's `combined_ladder`, `hit_rate_lines`, `LADDER_MAX_RUNGS` and the ladder block of `_plan_block` are not on this branch (spec What changed item 1).
- Unchanged, and kept so (done_when[10]): the trigger and stop rule, gate targets and the `*_t1..t3` columns, the plan's targets, spacing, thirds, entry cutoff and gap edges, the ATR levels line, the signal monitor, the movement statement, persona plans, every `premarket_analysis` column the resolver writes today, every brief's playbook text, and `LEVEL_RULE_VERSION` (`'feat-strat-001.v5'`, `lib/strat_levels.py:1542`).
- No `try` that turns a failed read into a number. A failed or missing reach read marks the ticker's table unavailable (CLAUDE.md 3.7). The brief still writes every ticker's row.
- Exact strings, copied from the spec's Design 5, produced by `lib/target_reach.py` for the quarter change to print:
  - count, at or above min_sample: `reached {k} of {n} ({p}%)`, p the share rounded half up to a whole number;
  - count, below min_sample: `reached {k} of {n}`;
  - no trades: `no history yet`, never `0 of 0`;
  - header: `Reached before the stop: {ticker} trades {first} to {last} ({n})`;
  - unavailable: `Reached before the stop: unavailable ({status}).`;
  - no stop: `Reached before the stop: unavailable (no stop to measure from).`
- `RESOLVER_VERSION` moves from `'2026-11-15.v4'` (`gcp/premarket_playbook_resolver.py:104`) to the next dated version on the merge base.

## Task 0: Carry the r1 commits onto the r2 branch
Spec: § What changed from r1. Advances done_when[0] to done_when[9] (the r1 work they rest on).
- [ ] Create `feature/feat-strat-001-target-hit-rates-r2` from `origin/main` and bring over the r1 branch's commits (0663e350 to df4361d7, and the merge 9533a444), keeping their messages. Merge `origin/main` into it; never rebase a pushed branch.
- [ ] Remove the ladder: `combined_ladder`, `hit_rate_lines`, `LADDER_MAX_RUNGS`, the ladder lines of `_plan_block` and their tests and golden lines. Commit: `refactor(brief): drop the separate hit-rate ladder (spec r2)`.
- [ ] Run `pytest tests/gcp tests/lib tests/api tests/meta -q` and list every failure with its cause before changing anything else. Known on the r1 branch at 9533a444, all from this work: `tests/gcp/test_premarket_brief_no_discord.py::TestDryRunDecides` (four tests: the dry run issues one more statement, the reach read), `tests/gcp/test_premarket_filter_params.py::test_schema_is_unchanged` (the schema hash pin) and `tests/gcp/test_level_basis.py::test_a_reader_that_knows_fewer_versions_refuses_then_recovers` (a return-shape mismatch at `:768`). Fix each at its cause in the task that owns it, and list the old and new expectation of every changed test in the PR body. A failure that is red on `origin/main` too, or a missing package such as `lightgbm`, is not this branch's and is shown as such.

## Task 1: The policy row and its key
Spec: § Design 1. Advances done_when[0].
- [ ] `gcp/schema.sql`: the `target_reach_rate` row of Design 1 exactly, `extra` `{"since": "2022-01-03", "measure": "touch_atr"}`, inside the same `INSERT ... ON CONFLICT DO NOTHING` as the gap-edge row. No other seed changes.
- [ ] `lib/strat_levels.py`: `TARGET_REACH_RATE_KEY` in `POLICY_WIDE_KEYS` (`:1014`); `policy_wide_param` (`:1381`) accepts `measure` in `touch_atr`, `held_5m_atr`, `touch`, `held_5m`, and gives `input_unavailable` for anything else.
- [ ] `tests/lib/test_level_params_loader.py`: the seeded row gives `ok` and value 30 with `measure` `touch_atr`; each of the four measures is accepted; each unusable field gives `input_unavailable`.
- [ ] Commit: `feat(levels): the target_reach_rate row reads in ATR by default`.

## Task 2: The table
Spec: § Design 2. Advances done_when[1].
- [ ] `gcp/schema.sql`: Design 2's `plan_excursions` exactly, with `atr`, `excursion_atr` and `excursion_held5_atr` and the CHECK `atr IS NULL OR atr > 0`.
- [ ] `tests/gcp/test_schema_plan_excursions.py`: every column with its type and nullability, the key, the `side`, `source` and `atr` CHECKs; `tests/integration/`: the schema applies twice in a row, and an insert with `source = 'other'` or `atr = 0` is refused.
- [ ] Re-pin `SCHEMA_SHA256` in `tests/gcp/test_premarket_filter_params.py` once the schema is final, the old and new hash in the PR body.
- [ ] Commit: `feat(resolver): plan_excursions stores the ATR and the excursions in ATR`.

## Task 3: The excursion in stop distances and in ATR
Spec: § Design 3. Advances done_when[2].
- [ ] `ExcursionResult` gains `atr`, `excursion_atr`, `excursion_held5_atr`; `plan_excursion(direction, plan, bars, atr)` divides the same two distances by the ATR, NULL when the ATR is missing or not positive or the distance is NULL. The entry walk stays the one helper `resolve_plan` calls.
- [ ] `tests/gcp/test_premarket_playbook_resolver.py`, `TestPlanExcursion`, adds: a call with trigger 100.00, stop 99.00, ATR 2.00 and a high of 103.00 before a later stop gives `excursion_r` 3.0 and `excursion_atr` 1.5; the mirrored put (stop 101.00, low 97.00) gives the same; no ATR gives NULL for both ATR values and the stop-distance values unchanged. Every r1 case still passes, and so does `test_a_gap_fill_past_t1_and_t2_holds_every_leg_to_the_close`.
- [ ] Commit: `feat(resolver): measure the excursion in ATR as well`.

## Task 4: One trade per ticker-day
Spec: § Design 2. Advances done_when[3].
- [ ] `trade_of_day` as on the r1 branch; its four tests pass unchanged.

## Task 5: The entry rule version
Spec: § Design 4. Advances done_when[4].
- [ ] `lib/strat_levels.py`: `entry_rule_version(version)` returns `version` when `is_current_pick_rule(version)` (`:1546`) and None otherwise.
- [ ] Add it to the allowed sites of the rule-version meta test; add no other comparison with a rule version.
- [ ] `tests/lib/test_strat_levels.py`: v3, v4 and v5 each map to themselves; v2, None and an unknown string map to None.
- [ ] Commit: `feat(levels): name the rule version a basis's entry comes from`.

## Task 6: The resolver writes the day's row
Spec: § Design 4 ("Every resolved day"). Advances done_when[5].
- [ ] `resolve_one` keys the row by `entry_rule_version(basis['rule_version'])` and writes the basis's ATR for its `atr_basis` with the four excursions; a basis with no `rule_version`, or whose entry version is None, writes and deletes nothing.
- [ ] `RESOLVER_VERSION` to the next dated version on the merge base.
- [ ] Writer tests: resolve a trade, then force-resolve the same session to no trade and see the row deleted in the same transaction; an unknown version writes nothing; the `premarket_analysis` update dict is byte-identical to `origin/main`'s apart from `outcome_resolver_version`.
- [ ] Fix `tests/gcp/test_level_basis.py::test_a_reader_that_knows_fewer_versions_refuses_then_recovers` at its cause (Task 0's list).
- [ ] Commit: `feat(resolver): key each day's excursion by its entry rule version`.

## Task 7: The reader and its count text
Spec: § Design 1, § Design 5. Advances done_when[7].
- [ ] `lib/target_reach.py`: `load_target_reach(query_fn, tickers, session_date, param, rule_version)` runs ONE query for all tickers with `rule_version = :entry_version` (the argument, never a constant), `session_date < :session`, and the since or lookback window; it selects the column the policy's measure names.
- [ ] `ReachTable` gives `n`, `first`, `last`, `count_at_least(d)` (NULL reaching nothing) and `count_text(d, min_sample)` with the exact strings of Global Constraints; `header_text()`, `unavailable_text(status)` and the no-stop text are module functions.
- [ ] `tests/lib/test_target_reach.py`: the since and lookback windows, the point-in-time cut, each of the four measures, the version filter, the NULL rule, one query for three tickers, a raising `query_fn`, and each text at n 0, below min_sample and at or above it (the percent rounded half up).
- [ ] Commit: `feat(levels): read reach by entry version and format the counts`.

## Task 8: The brief passes the table on and prints nothing new
Spec: § Design 5. Advances done_when[8].
- [ ] `format_levels_for_brief` (`:3178`) keeps the `reach` argument and passes the ticker's table into the side records it builds, so the quarter change can print from it; `_plan_block` (`:3283`) prints nothing from it.
- [ ] `tests/lib/test_strat_levels.py`: on `tests/fixtures/iwm_2025_10_22_level_basis.json` with a table of the Experiment's 906 IWM trades, both sides' output with the table equals the output without one, which equals `origin/main`'s; the same on every existing D8 golden, none edited.
- [ ] Commit: `feat(brief): carry the reach table without printing it`.

## Task 9: Wired into the brief
Spec: § Design 5. Advances done_when[9].
- [ ] `generate_premarket_brief` reads the table once for all tickers through `_target_reach_query`, with the entry version of the basis being built, and passes each ticker's table to `format_levels_for_brief`; a failed read marks every ticker's table unavailable and writes every brief.
- [ ] `tests/gcp/test_premarket_brief.py`: one read for SPY, QQQ and IWM; a raising read leaves every brief written with no `PLAYBOOK_FAILED`; the stored playbook text of a level-rule basis is unchanged either way.
- [ ] `tests/gcp/test_premarket_brief_no_discord.py`: raise `DRY_RUN_STATEMENTS` by the one reach read and assert that the added statement is that read, its old and new value in the PR body.
- [ ] Commit: `feat(brief): read the reach table once per run`.

## Task 10: The history job
Spec: § Design 4 ("History, once per entry version"). Advances done_when[6].
- [ ] `gcp/backfill_plan_excursions.py` as on the r1 branch, with rows keyed by `entry_rule_version` of the rebuilt basis's version, the basis's ATR written, and the four excursions. It writes nothing but `plan_excursions` and calls no model.
- [ ] No `gcp/deploy.sh` change on this branch (FEAT-DEPLOY-001 owns it; the r1 deploy entry is saved as `deploy-entry.diff` in the task notes for that change).
- [ ] Tests as on the r1 branch (resume, the explicit-range delete, never replacing a resolver row, a repeat run writes the same rows, one bar query per ticker-month, statements recorded, no model call), plus a row's `rule_version` is the entry version and its `atr` the basis's.
- [ ] Commit: `feat(resolver): the history job keys rows by entry version and stores ATR`.

## Task 11: Experiment through the production paths
Spec: § Experiment, § Capacity and cost. Advances done_when[11].
- [ ] On a local Postgres built like the spec's Experiment, run the history job for SPY, QQQ and IWM over 2022-01-03 to 2026-11-10 on as-traded bars (`/mnt/project-files/stocks-scorecard/research/fable_lab/data/bars_1min/` to 2025-02, `/mnt/project-files/stocks-scorecard/inputs/bars_raw/` from 2025-03), SPY 2025-04-09 and IWM 2026-06-26 left out.
- [ ] Show in the PR body: the same 3,463 trades; on every trade filled at the trigger, excursions in stop distances and in ATR within 1e-6 of the spec's rows; Tables 3, 4, 6 and 7 reproduced from the job's rows; the measured wall-clock per ticker, which sets the job's timeout at four times or more for the FEAT-DEPLOY-001 change.
- [ ] A reproduction for the record, not a gate. A mismatch is reported with its rows, never tuned away. Scripts and inputs are cited by path and sha256 and not committed.

## Task 12: Unchanged, source identity and the record
Spec: § Source identity and close-out, Done when. Advances done_when[10], done_when[12], done_when[13], done_when[14].
- [ ] done_when[10]: list in the PR body the existing tests that pin each unchanged behavior in Global Constraints; run them on `origin/main` and on the head and show both passing.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, `### FEAT-STRAT-001`: append the reach history (`plan_excursions`, written by the resolver and a one-off history job, read by `lib/target_reach.py` for the quarter lines) with the PR link, under review and not deployed; Last reviewed to the head commit's date.
- [ ] `docs/product/12-PR-ISSUE-TRACEABILITY.md`, `### FEAT-STRAT-001`: append the PR to `**PR lineage:**`, naming spec PRs #1996 and #2051.
- [ ] Site note, steps 1 to 4 as the r1 plan's Task 11 gives them: `produce`, the `| FEAT-STRAT-001 | DASHBOARD-01 |` row only, `produce` again and commit the record, then `verify` with `--max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` (exit 0). Any later change under `gcp/`, `lib/`, `scripts/` or `tests/`, or a move of `origin/main`, means redoing all four.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` passes. The PR body says the owner's merge is the yes for the table and the policy row (apply-schema creates both on that merge), and that the deploy and the history run each wait for their own yes.

## Close-out, after the merge (never a pre-merge box)

1. Confirm the apply-schema build created `plan_excursions` (0 rows) and exactly one `target_reach_rate` row; record both counts.
2. On the owner's yes: the history job's deploy entry through its FEAT-DEPLOY-001 change, then deploy the resolver and the brief. The brief prints nothing new.
3. On its own yes: run the history job per ticker; record the rows written per ticker. This is done before the quarter targets go live, so their lines never read `no history yet`.
4. Mark the r1 plan's work as carried here in this plan's PR body, mark this plan `status: done`, and complete the DOC close-out the product-delivery skill prescribes.
