---
feat_id: FEAT-STRAT-001
spec: docs/superpowers/specs/2026-11-16-feat-strat-001-target-hit-rates.md
branch: feature/feat-strat-001-target-hit-rates
pr: null
status: ready
---

# Each target in the brief shows how often price has reached it before the stop: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the order of the spec's frontmatter, [0] (Policy) to [12] (catalog, gate and production yeses).

**Goal:** Under each side's exit plan, the brief prints the combined ladder (the current-rule targets plus the plan's targets, one rung per cent, up to six, nearest the trigger first), each rung with its distance from the trigger in stop distances and the share of that ticker's past trades whose move past the trigger reached that distance before the stop, with the trade count. The rates come from a new table, `plan_excursions`, that the resolver fills each day and a one-off history job fills back to 2022-01-03. Nothing the brief trades, alerts or scores changes.

**Architecture:** `resolve_plan`'s entry walk moves into one private helper that `resolve_plan` and a new pure `plan_excursion` both call. `plan_excursion` returns one side's fill bar, stop bar and the two excursions (touch and held 5). `trade_of_day` keeps the side that filled first. `resolve_one` upserts or deletes that day's `plan_excursions` row in the transaction that updates `premarket_analysis`. A new `lib/target_reach.py` reads every row of the run's tickers in one query and answers "what share reached at least d stop distances". `format_levels_for_brief` takes an optional reach table and, only when given one, adds the ladder lines to `_plan_block`. `generate_premarket_brief` reads the table once per run and passes it in. `gcp/backfill_plan_excursions.py` replays the brief's level build per session with its writes switched off, scores each session on the stored 1-minute bars and upserts history rows.

**Tech Stack:** Python, pandas, numpy, SQLAlchemy `text()` through `gcp.database`, argparse, pytest (`monkeypatch`), Postgres 15 in CI for `tests/integration/`.

**Spec:** docs/superpowers/specs/2026-11-16-feat-strat-001-target-hit-rates.md (approved, PR #1996, merged to `main` at 468e048 on 2026-11-16). The owner approved its five picks as written: rate by distance, touch, every trade since 2022-01-03, per ticker, the count always printed with "too few" under 30.

## Global Constraints

- Base: `origin/main` at or after 468e048. Line numbers below are from 468e048; recheck them on the base actually used. Branch `feature/feat-strat-001-target-hit-rates`. This plan is committed alone on `docs/plan-feat-strat-001-target-hit-rates` and merged before the code branch opens.
- Values are never hard-coded. The window (`since` or `lookback_sessions`), the measure (`touch` or `held_5m`) and the minimum sample come only from the `target_reach_rate` policy row. 6 (the ladder's length) is the spec's display cap, named once as a module constant `LADDER_MAX_RUNGS = 6`.
- R and every distance are the stock's move in stop distances. No copy, comment, log line or test name speaks of money, profit or cost.
- 1-minute bars are as-traded and come only from `market_data_intraday` (the store the nightly fills). The history job reads nothing else for bars.
- Unchanged, and kept so (done_when[9]): the trigger and stop rule, gate targets and the `*_t1..t3` columns, the plan's targets, spacing, thirds, entry cutoff and gap edges, the ATR levels line, the signal monitor, the movement statement, persona plans, every `premarket_analysis` column the resolver writes today and `LEVEL_RULE_VERSION` (`'feat-strat-001.v3'`, `lib/strat_levels.py:1516`).
- No `try` that turns a failed read into a number. A failed or missing reach read prints `    Hit rates unavailable (input_unavailable).` for each ticker (CLAUDE.md 3.7). The brief still writes every ticker's row.
- Exact strings, copied from the spec's Design 5:
  - header: `    Hit rates, {TICKER} trades {first} to {last} that reached each price before the stop ({n} trades):`
  - rung: `      {price:.2f} ({name}), {d:.2f} stop distances: {pct}%`, with `, plan T{k}` after the distance for a plan exit
  - thin: `    Hit rates: too few {TICKER} trades so far ({n}, at least {min} needed).`
  - unavailable: `    Hit rates unavailable (input_unavailable).`
  - no stop: `    Hit rates unavailable (no stop to measure from).`
  - The percent is the share rounded half up to a whole number. The distance is printed to two places.
- `RESOLVER_VERSION` moves from `'2026-11-15.v4'` (`gcp/premarket_playbook_resolver.py:100`) to `'2026-11-16.v5'`.

## Task 1: The policy row and its key
Spec: § Design 1. Advances done_when[0].
- [ ] `gcp/schema.sql`: add after the `plan_target_level_types` seed (`:2318`), inside the same `INSERT ... ON CONFLICT DO NOTHING`, the row of Design 1 exactly: `('target_reach_rate', 'plan_excursion_share', NULL, NULL, 30, '{"since": "2022-01-03", "measure": "touch"}', '2015-01-02', '...')`. No other seed changes.
- [ ] `lib/strat_levels.py`: `TARGET_REACH_RATE_KEY = 'target_reach_rate'` next to `PLAN_TARGET_LEVEL_TYPES_KEY` (`:1012`), added to `POLICY_WIDE_KEYS` (`:1014`).
- [ ] `policy_wide_param` (`:1365`): for this key, `value = float(min_sample)` when `pol['min_sample']` is a positive int (not bool), `pol['lookback_sessions']` is None or a positive int, `extra['since']` parses with `date.fromisoformat`, and `extra['measure']` is `'touch'` or `'held_5m'`; otherwise `input_unavailable`. Carry `min_sample` and `lookback_sessions` on the returned `LevelParam` (its fields `:1119`, `:1121`) so the reader needs nothing else.
- [ ] `tests/lib/test_level_params_loader.py`: the policy loaded from `gcp/schema.sql` gives `ok`, value 30, `extra == {"since": "2022-01-03", "measure": "touch"}`; each unusable field (min_sample 0, None or True; lookback_sessions 0 or -1; since `"2022-13-01"` or missing; measure `"close"` or missing) gives `input_unavailable`.
- [ ] Run `pytest tests/lib tests/gcp -q`. A policy-wide key enters every `LevelParams` and so every recorded `level_basis['params']`. Expect exactly the tests that enumerate the recorded params to need the new key, as the gap-edge change did; today that is `tests/lib/test_strat_levels.py:1408-1427` (the ATR display-only brief test). Edit that test only to pop `target_reach_rate` the way it pops `plan_target_level_types`, and list every other test that fails in the PR body before touching it.
- [ ] Commit: `feat(levels): seed the target_reach_rate policy row`.

## Task 2: The table
Spec: § Design 2. Advances done_when[1].
- [ ] `gcp/schema.sql`: add Design 2's `CREATE TABLE IF NOT EXISTS plan_excursions (...)` exactly, next to the other playbook tables.
- [ ] New `tests/gcp/test_schema_plan_excursions.py`, modeled on `tests/gcp/test_schema_style_tables.py` (`_table_body`): the table exists with IF NOT EXISTS; every column of Design 2 with its type and nullability; `PRIMARY KEY (ticker, session_date, rule_version)`; the CHECKs `side IN ('calls', 'puts')` and `source IN ('resolver', 'history')`.
- [ ] `tests/integration/`: on the CI Postgres, `gcp/schema.sql` applies twice in a row without error (the apply-schema build runs it on every push to main), and an insert with `source = 'other'` is refused.
- [ ] Commit: `feat(resolver): add the plan_excursions table`.

## Task 3: One entry walk and the excursion
Spec: § Design 3. Advances done_when[2].
- [ ] In `gcp/premarket_playbook_resolver.py`, move the entry block of `resolve_plan` (`:517-539`, from the `o`, `h`, `lo`, `c`, `times`, `reached` arrays through `out.fill_ts`) into `_entry(is_call, plan, bars) -> _Entry(status, i, fill, arrays)`. `resolve_plan` calls it and keeps every other line. No second copy of the walk exists anywhere.
- [ ] Prove the move changed nothing before going on: `pytest tests/gcp/test_premarket_playbook_resolver.py -q` passes with no test edited.
- [ ] Add `ExcursionResult` (fill_i, fill_price, fill_ts, stop_i, stop_ts, excursion_r, excursion_held5_r) and `plan_excursion(direction, plan, bars) -> Optional[ExcursionResult]`:
  - None unless `_entry` gives `entered` and `_valid_stop(is_call, plan.stop_price, fill)` holds.
  - The stop bar: the first bar from the fill bar on whose low (calls) or high (puts) touches the stop.
  - `excursion_r`: the most the high (calls) or low (puts) went past the **trigger** on bars `fill_i + 1 .. stop_i - 1` (to the last bar when there is no stop bar), divided by `abs(trigger - stop)`. None when that range is empty.
  - `excursion_held5_r`: the same over the furthest price that five consecutive closes all stayed at or beyond, all five inside that range. None when there is none.
- [ ] `tests/gcp/test_premarket_playbook_resolver.py`, class `TestPlanExcursion`, hand-built calls and puts sessions:
  - a rung touched only on the fill bar is not reached;
  - a bar touching the stop and a rung counts the stop first;
  - no bar between the fill bar and the stop bar gives None for both;
  - five closes beyond a level that end on the stop bar do not count as held;
  - a cross bar that opened beyond the trigger is still measured from the trigger;
  - the gap-fill fixture of done_when[2] (trigger 100, stop 99, cross bar opening at 102, a later high of 102.9): `excursion_r == 2.9`, rungs 101 and 102 reached, rung 103 not;
  - a property over every fixture: a rung beyond the fill is reached (`excursion_r >= d`) exactly when `resolve_plan`'s exit walk sells a leg at it.
  - `test_a_gap_fill_past_t1_and_t2_holds_every_leg_to_the_close` (`:732`) still passes unchanged.
- [ ] Commit: `feat(resolver): measure each trade's move past the trigger before the stop`.

## Task 4: One trade per ticker-day
Spec: § Design 2 (one row per ticker-day). Advances done_when[3].
- [ ] `trade_of_day(calls: Optional[ExcursionResult], puts: Optional[ExcursionResult]) -> Optional[tuple[str, ExcursionResult]]`: the side with the earlier `fill_i`; None when both are None or both filled on the same bar.
- [ ] Tests for the four cases: calls only, puts only, both with calls first, the same-bar tie (and both None).
- [ ] Commit: `feat(resolver): keep the side that filled first`.

## Task 5: The resolver writes the day's row
Spec: § Design 4 ("Every resolved day"). Advances done_when[4].
- [ ] In `resolve_one` (`:643`), after `calls_plan` and `puts_plan` (`:766-767`), compute both sides' `plan_excursion` on the same `plan_bars` and the same `plan_inputs`, then `trade_of_day`.
- [ ] Inside the existing `with engine.begin() as conn:` (`:869`), after the `premarket_analysis` UPDATE: when the basis has a `rule_version` and there is a trade, `INSERT ... ON CONFLICT (ticker, session_date, rule_version) DO UPDATE` with `source = 'resolver'` and `resolver_version = RESOLVER_VERSION`; when there is no trade, `DELETE` the row for that ticker, session and rule version. A basis with no `rule_version` writes and deletes nothing.
- [ ] `RESOLVER_VERSION = '2026-11-16.v5'`.
- [ ] Writer tests: resolve a trade, then force-resolve the same session to no trade and see the row deleted in the same transaction; a basis with no rule version writes nothing; every existing resolver test still passes, with the `premarket_analysis` update dict byte-identical to `origin/main`'s apart from `outcome_resolver_version`.
- [ ] Commit: `feat(resolver): store each resolved day's excursion`.

## Task 6: The reader
Spec: § Design 1, § Design 5 (one query per run). Advances done_when[6].
- [ ] New `lib/target_reach.py`:
  - `load_target_reach(query_fn, tickers, session_date, param) -> dict[str, ReachTable]` runs ONE query for all tickers: `rule_version = LEVEL_RULE_VERSION`, `session_date < :session`, and `session_date >= :since`, or, when `lookback_sessions` is set, the ticker's last that many distinct sessions before the brief's (a window function in the same query).
  - It selects `excursion_r` or `excursion_held5_r` from the policy's `measure`.
  - A raised query error or missing table propagates as `TargetReachUnavailable`. An unusable `param` raises the same.
- [ ] `ReachTable(ticker, n, first, last, values)` with `share_at_least(d)`: the share of the n trades whose excursion is at least d. A None excursion counts as reaching nothing and still counts in n.
- [ ] Tests (`tests/lib/test_target_reach.py`): the since window, the lookback window, the point-in-time cut (a row on the brief's own session is never read), the measure switch, the NULL rule, one query for three tickers, a raising `query_fn`.
- [ ] Commit: `feat(levels): read the past trades' reach per ticker`.

## Task 7: The ladder in the brief's copy
Spec: § Design 5. Advances done_when[7].
- [ ] `lib/strat_levels.py`: `combined_ladder(trig) -> list[Rung]`: the side's gate targets (`trig['targets']`) and plan targets (`trig['plan_targets']`), one rung per `price_cents` (`:921`). When both lists hold the same cent, it is one rung, marked as plan T{k}. Rungs run from the trigger outward, at most `LADDER_MAX_RUNGS`.
- [ ] `format_levels_for_brief` (`:3068`) gains `reach: Optional[Mapping] = None`, where None means print no ladder, and `reach_params` (min_sample). `_plan_block` (`:3173`) prints the ladder after the Skipped line and before `Room to trigger` for a side with a plan:
  - the header and rung lines when n is at least min_sample;
  - the thin line when n is below it;
  - the unavailable line when the read failed;
  - the no-stop line when the side has no stop, or a stop not on the losing side of the trigger.
  - A side with no plan prints no ladder.
- [ ] The golden: commit the IWM 2025-10-22 basis as `tests/fixtures/iwm_2025_10_22_level_basis.json`. Build it on the branch's base with the brief path, and check its puts side against Design 5 (trigger 245.66 PMK_L, stop 246.99 PDC, plan T1 to T3 at 243.41, 241.96 and 240.36). The research copy at `/mnt/project-files/stocks-scorecard/research/worked_day/IWM_2025-10-22_level_basis.json` is a cross-check only. The reach table is fixed from the 906 IWM rows of `rung_rows_trades.csv` dated before 2025-10-22. The puts lines must equal Design 5 byte for byte.
- [ ] Pin the thin, unavailable and no-stop lines, each with the rest of the side's block unchanged and no percent printed. With `reach=None`, the output equals `origin/main`'s on every existing D8 golden, so those goldens are not edited.
- [ ] Commit: `feat(brief): print each target's hit rate under the plan`.

## Task 8: Wired into the brief
Spec: § Design 5. Advances done_when[8].
- [ ] `gcp/premarket_brief.py`:
  - add `_target_reach_query(sql, params)`, a strict reader shaped like `_level_params_query` (`:950`);
  - in `generate_premarket_brief`, right after `load_level_params` (`:980`), call `load_target_reach` once for all tickers, with the `target_reach_rate` param of the first ticker (the policy is the same for every ticker);
  - on `TargetReachUnavailable` (or that param not ok), keep a marker so every ticker prints the unavailable line;
  - pass the ticker's table and min_sample to `format_levels_for_brief` (`:1400`).
- [ ] `tests/lib/strat_2026_11_06.py` (`run_brief`) stubs `_target_reach_query` the way it stubs the level-param read, so the brief-path tests stay offline.
- [ ] A new test in `tests/gcp/test_premarket_brief.py` on `generate_premarket_brief` (BRIEF_AS_OF, stubbed database):
  - the reach read is issued once for SPY, QQQ and IWM;
  - each stored playbook carries Design 5's ladder lines;
  - a raising reach read leaves every ticker's brief written with the unavailable line, no `PLAYBOOK_FAILED` and no percent.
- [ ] The ATR display-only brief test (`tests/lib/test_strat_levels.py:1394`) compares the brief path's playbook to a stored base with exactly one line added. Teach it to drop the ladder lines from the head playbook before that comparison and to pop the new param (Task 1). It must keep checking that the ATR line is the only other addition. Do not regenerate `tests/fixtures/atr_levels_brief_base.json`.
- [ ] Commit: `feat(brief): read the hit rates once per run`.

## Task 9: The history job
Spec: § Design 4 ("History, once"), § Design 6. Advances done_when[5].
- [ ] `generate_premarket_brief` gains the keyword-only `persist_levels: bool = True`. With False it skips `persist_level_map` (`:1440-1500`) and `_delete_null_close_rows` and changes nothing else. Every current caller keeps the default, so the live brief and `/replay` are unchanged.
- [ ] New `gcp/backfill_plan_excursions.py` (`--tickers`, `--start` defaulting to the policy row's `since`, `--end`). For each session and ticker:
  - run `generate_premarket_brief` with BRIEF_AS_OF set to the session, BRIEF_TICKERS set to the ticker, `persist_levels=False` and `BRIEF_AMC_REACTIONS=0`, and take `level_basis` from the returned entry. It never writes `premarket_analysis`, `premarket_analysis_history` or `strat_levels`.
  - Read one ticker-month of `market_data_intraday` 1-minute bars per query and cut each session at `session_close`.
  - Score both sides with `plan_inputs` (v3 basis) and `plan_excursion`, then pick with `trade_of_day`.
  - Upsert `source = 'history'` rows with `ON CONFLICT ... DO UPDATE ... WHERE plan_excursions.source = 'history'`, so a resolver row is never replaced.
  - Delete its own history row for a session that now gives no trade.
  - Resume from the last session written per ticker.
  - Print per ticker the sessions read, rows written, rows deleted and the wall-clock.
- [ ] Tests:
  - resume skips written sessions;
  - a session that now gives no trade deletes only a history row;
  - a resolver row is never replaced;
  - a re-run over the same span writes the same rows;
  - one bar query per ticker-month;
  - nothing is written outside `plan_excursions`, checked by recording every SQL statement issued.
- [ ] `gcp/deploy.sh`: a `deploy_backfill_plan_excursions` function beside `deploy_premarket_playbook_resolver` (`:1532`), creating a Cloud Run job `backfill-plan-excursions` (`python -m gcp.backfill_plan_excursions`) with no schedule. Its `--task-timeout` is Task 10's measured wall-clock per ticker times four or more. `gcp/deploy.sh` is not run in this PR.
- [ ] Commit: `feat(resolver): add the plan excursions history job`.

## Task 10: Experiment through the production paths
Spec: § Experiment, § Capacity and cost. Advances done_when[10].
- [ ] On a local Postgres built like the spec's Experiment, run the history job for SPY, QQQ and IWM:
  - as-traded bars from `/mnt/project-files/stocks-scorecard/research/fable_lab/data/bars_1min/` (to 2025-02) and `/mnt/project-files/stocks-scorecard/inputs/bars_raw/` (from 2025-03);
  - 2022-01-03 to 2026-11-10, with SPY 2025-04-09 and IWM 2026-06-26 left out.
- [ ] Show in the PR body:
  - the same 3,463 trades (ticker, date, side, stop);
  - on every trade filled at the trigger, excursions within 1e-6 of `rung_rows_trades.csv` (sha256 prefix 148e8dff);
  - the count of trades filled beyond the trigger, where the job measures from the trigger and the Experiment from the fill (Risks);
  - Tables 3 and 4 reproduced from the job's rows;
  - the measured wall-clock per ticker.
- [ ] This is a reproduction for the record, not a gate. A mismatch is reported with its rows, never tuned away.
- [ ] Cite the local scripts and inputs by path and sha256 in the PR body; none of them is committed.

## Task 11: Unchanged, source identity and the record
Spec: § Source identity and close-out, Done when. Advances done_when[9], done_when[11], done_when[12].
- [ ] done_when[9]: list in the PR body the existing tests that pin each unchanged behavior in Global Constraints. Run them on `origin/main` and on the head, and show both passing.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, `### FEAT-STRAT-001` (`:233`): append to its Status cell the hit-rate ladder under each plan, read from `plan_excursions` (written by the resolver and a one-off history job), with the PR link; note it is under review and not deployed. Set Last reviewed to the head commit's date.
- [ ] `docs/product/12-PR-ISSUE-TRACEABILITY.md`, `### FEAT-STRAT-001` (`:547`): append the PR to its `**PR lineage:**` line, naming spec PR #1996.
- [ ] Site note, step 1: with a clean tree, `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`.
- [ ] Site note, step 2: in `docs/product/03-SITE-TRACEABILITY.md`, the `| FEAT-STRAT-001 | DASHBOARD-01 |` row (`:1350`) and no other byte: the new `source_identity_sha256`, then this change's prose (backend source and local tests only), then ` Earlier: ` and the earlier prose unchanged.
- [ ] Site note, steps 3 and 4: `produce` again, then `verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` (exit 0). Once these start, any change under `gcp/`, `lib/`, `scripts/` or `tests/` means redoing them.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` passes. The PR body says that the owner's merge is the yes for the table and the policy row (apply-schema creates both on that merge), and that the deploy and the history run each wait for their own yes.

## Close-out, after the merge (never a pre-merge box)

1. Confirm the apply-schema build created `plan_excursions` (0 rows) and exactly one `target_reach_rate` policy row; record both counts.
2. On the owner's yes: deploy the resolver and the brief. Until step 3, the brief prints "too few".
3. On a second yes: run the history job per ticker; record the rows written per ticker.
4. Confirm the next live brief prints the ladder with the trade count, then mark this plan `status: done` and complete the DOC close-out the product-delivery skill prescribes.
