---
feat_id: FEAT-STRAT-001
spec: docs/superpowers/specs/2026-11-16-feat-strat-001-unknown-rule-version.md
branch: feature/feat-strat-001-unknown-rule-version
pr: 2043
status: ready
---

# A stored level basis of a rule version the code does not know is refused: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are named as the spec names them, U1 to U10 with U7b.

**Goal:** Every reader of a stored `level_basis` classifies its `rule_version` through one function, and a version newer than the image knows, or one it cannot read, is refused by name in each reader's own unavailable state, never rebuilt under the v2 rule and never written over.

**Architecture:** `lib/strat_levels.py` gains `rule_version_number`, `rule_version_status`, `newest_pick_rule_version` and the exception `LevelRuleVersionUnknown`; `SessionLevels.from_basis` and `_assemble` raise it. Each reader turns it into its own state: the resolver returns a reason and writes nothing (and `main()` exits 1), the movement statement returns an UNAVAILABLE envelope, the API returns None, the signal monitor skips the ticker with a counter, the insight run fails, and the brief's dry run keeps the stored values. Nothing reads a version number anywhere else.

**Tech Stack:** Python 3, `re`, pandas, SQLAlchemy `text` (unchanged statements), pytest (`monkeypatch`, `caplog`), `ast` for the meta test.

**Spec:** docs/superpowers/specs/2026-11-16-feat-strat-001-unknown-rule-version.md (approved by the owner 2026-11-17 with every decision taking its recommended pick; PR #2025, not yet on `main` when this plan was written). This plan matches the spec as revised after review, head 2c752266e: U4 and U7b case 6 refuse an unreadable version in the resolver, U5 runs the insight run's own path, and U9 names the three legacy checks.

## Start condition

The spec's precondition is PR #2010 (the brief build, `feature/feat-playbook-001-brief-says-what-the-data-says`) on `main`: it adds `is_current_pick_rule`, `PICK_RULE_VERSIONS` and `tests/meta/test_level_rule_version_readers.py`, none of which exist on `origin/main` 3a59299ba. Do not open the build branch until `git ls-tree origin/main tests/meta/test_level_rule_version_readers.py` prints a line. The spec (PR #2025) and this plan also merge first.

**Line numbers.** Every `file:line` below is read on 44dfa3d8c, the head of PR #2010 when this plan was written, because that is what `main` will hold when the build starts. `git diff --stat 8250bff75 44dfa3d8c -- lib gcp platform tests/lib tests/gcp tests/meta` printed nothing, so the spec's line numbers (cited at 8250bff75) still hold there. First step of Task 1: `git diff --stat 44dfa3d8c origin/main -- lib gcp platform tests` on the real base, and re-find any line that moved.

## Global Constraints

- Branch `feature/feat-strat-001-unknown-rule-version` from `origin/main` once the start condition holds. One PR, title `FEAT-STRAT-001: refuse a stored level basis of a rule version the image does not know`.
- Status strings, exactly: `legacy`, `known`, `rule_version_newer`, `rule_version_unreadable`. The number pattern: `re.fullmatch(r'feat-strat-001\.v([1-9][0-9]*)', version)` on a `str` only (ASCII digits, no leading zero, nothing before or after; a trailing newline does not match `fullmatch`).
- Classifier order (spec Design 1), first match wins: `None` gives `legacy`; no number gives `rule_version_unreadable`; `is_current_pick_rule(version)` gives `known`; number at or below 2 gives `legacy`; number above the largest number in `PICK_RULE_VERSIONS` gives `rule_version_newer`; anything else gives `rule_version_unreadable`.
- The newest known is computed from `lib.strat_levels.PICK_RULE_VERSIONS` at call time (module attribute, not a copy), so a test that patches it makes the reader a straggler. No code outside `lib/strat_levels.py` imports `PICK_RULE_VERSIONS` by name.
- `LEVEL_RULE_VERSION`, `PICK_RULE_VERSIONS`, every pick, the v2 legacy path and `plan_inputs` stay as the merge base has them (spec Non-goals). No schema, deploy, scheduler or data change. No new version.
- Tests are hermetic: no network, no database, no git command against a second ref. Where a done_when item says "what they give on the merge base", run the unchanged code on the branch before the task's first edit, paste the printed value into the test as a literal, and list those literals in the PR body.
- Newer versions in every test are built from `PICK_RULE_VERSIONS` by the helper `newer_rule_versions()` (Task 1), never typed as `v5`, so the tests hold after the prior-close build adds v5 (spec Design 5, last paragraph).
- No silent fallback (CLAUDE.md 3.7): a refusal is raised or returned by name; no new `except` returns an empty value.
- The meta test `tests/meta/test_level_rule_version_readers.py` keeps its `ALLOWED` map byte for byte. A watched name (`LEVEL_RULE_VERSION`, `LEVEL_RULE_V3`, `PICK_RULE_VERSIONS`) never sits in a comparison or a dict literal's value in new code; `max(PICK_RULE_VERSIONS, key=rule_version_number)` is neither.
- The render step. A task that changes a file under `gcp/`, `lib/` or `platform/` ends with
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate -q` (expect `1 passed`), and stages whichever of the three docs changed with the code.
- Commits: conventional `type(scope): description`, imperative, no AI attribution. Every new test has a red then green record in the PR body (failing output before the code, passing output after).
- Capacity (CLAUDE.md rule 0; spec Capacity), copied into the PR body because the PR touches `gcp/`: Volume, one string per stored basis read; Velocity, 0 added round trips, and the refusing paths make fewer (the resolver skips its bar read, Task 3 asserts one read; the movement statement skips its two reach queries, Task 8 asserts none); Wall-clock, one regex match per rebuild, not measured, against jobs whose cost is their queries; Cost, $0 a run. A refused resolver run exits 1 once a night per skewed date until the image is updated: the alarm, not a retry loop. The resolver job's `--max-retries` was not read by the spec; Task 11 reads it from `gcp/deploy.sh` and states it in the PR body.

## Choices this plan makes where the spec leaves one open or does not match the code

Reported to the owner with the plan.

1. **U9's three legacy checks.** The spec as revised (2c752266e) allows and pins the three comparisons against the unwatched `LEVEL_RULE_V2` that keep a v2 basis's own plan: `gcp/premarket_playbook_resolver.py:625` (`plan_inputs`, `basis.get('rule_version') != LEVEL_RULE_V2`), `lib/strat_levels.py:2448` (`_assemble`, `base.rule_version == LEVEL_RULE_V2`) and `lib/strat_levels.py:2818` (`_pick_side`, `rule_version == LEVEL_RULE_V2`). The plan keeps all three unchanged (spec Non-goals; U3 needs `test_a_basis_other_than_v2_or_v3_has_no_plan` and the v2 fallback to pass unedited) and Task 10 pins them by file and function, so any fourth site fails.
2. **The signal monitor's state.** Design 3 says "level map None, session levels removed"; U5 says "leaves level_maps and session_levels without the ticker". The plan sets `self.level_maps[ticker] = None` (as the `LevelParamsUnavailable` branch at `gcp/signal_monitor.py:961-971` does), pops `session_levels` and `level_map_atr`, and the test asserts `monitor.level_maps.get('QQQ') is None and 'QQQ' not in monitor.session_levels`, which both readings satisfy.
3. **Refused rows in `main()`'s date outcome.** A refused row is counted in a new `n_refused`, not in `n_skipped`, so `classify_date_outcome` keeps its meaning; `main()` returns 1 when any row was refused, whatever the date's outcome (decision 3). The per-date `done` line gains `%d refused`.
4. **The insight run.** `build_context_bundle`'s section loop re-raises `LevelRuleVersionUnknown` beside `LevelParamsUnavailable` (`lib/agents/summarizers.py:2094-2098`), ahead of its `except Exception` (`:2099-2103`), which would otherwise turn it into an unavailable section. `gcp/insight_pipeline_job.py` is not edited, because U5 is met without it. Read on 44dfa3d8c: `run_insight_pipeline` calls `build_context_bundle` with no handler around it (`lib/agents/orchestrator.py:311`), and `_run_one` awaits that (`gcp/insight_pipeline_job.py:529`) before `_insert_report_history` and `_upsert_report` (`:532-533`), so the exception reaches the generic branch (`:550-553`), which records `failed` with `str(exc)` and returns False; the exception's message starts with its reason. Run on 6243496db with a stand-in `RuntimeError` subclass raised from the orchestrator's `build_context_bundle` and both writers patched to fail: `_run_one` returned False, the transitions were `running` then `failed`, and the error began with the reason (1 passed). Task 6's U5 test pins it on the real path; if it fails on Task 6's code, the fix goes in `_run_one` and the PR body says so.
5. **The resolver's check reads the row's own basis.** `resolve_one` already selects `level_basis` with the row (`:657-667`); the check parses it once with `parse_level_basis`, moved up from `:747`, and the later plan code reuses the parsed value. A refusal from the derive path (`derive_level_map_from_daily` reads the session's live basis, `:207-212`) is caught by name around the call at `:691` and returned the same way.
6. **The test clock for `main()`.** No existing test drives the resolver's `main()`. U4 and U7b patch `mod.datetime` with a subclass whose `now()` returns 2026-11-17 20:00 Eastern, `gcp.database.get_engine` and `is_cloud_sql_configured`, and route every `pd.read_sql` through an in-memory table (Task 4) that answers the four statements the job issues and applies each UPDATE back to its row. Its `pending_dates` answer is a frame of plain `date` values, so the patched clock class does not meet a `Timestamp`.

## done_when map

| done_when | What | Task |
|---|---|---|
| U1 | one classifier | 1 |
| U2 | `from_basis` and `_assemble` refuse | 2 |
| U3 | known and legacy versions untouched | 2 |
| U4 | the resolver writes nothing; `main()` exits 1 | 3, 4 |
| U5 | every other reader refuses by name | 3 (derive path), 6, 7 |
| U6 | the movement statement says why | 8 |
| U7 | mixed rollout and rollback | 5 |
| U7b | recovery through the scheduled path | 5 |
| U8 | the brief's dry run | 9 |
| U9 | the one-helper rule holds | 10 |
| U10 | close | 11 |

## Review Focus

Inputs the spec implies and no done_when test pins, most likely first. Each has a test in the task named.

- **A version between two the image knows.** With `PICK_RULE_VERSIONS` patched to `(v3, v5)`, v4 is `rule_version_unreadable`, not `known` and not `rule_version_newer` (Design 1 rule 6). Task 1.
- **A refused row on a past date with nothing else to resolve.** `main()` returns 1 and the date's `done` line names one refused; it does not read as "nothing to do". Task 4.
- **A NULL-trigger row whose live basis is newer.** The row's own basis is legacy, so the first check passes; the derive path's refusal is returned as the reason with zero writes and no bar read. Task 3.
- **The movement statement with no level map.** A refused tracked row gives the rule-version reason, not "level map unavailable". Task 8 runs it with `level_map=None` and with a map.

## File map

| File | Change | Task |
|---|---|---|
| `lib/strat_levels.py` | status constants, `rule_version_number`, `newest_pick_rule_version`, `rule_version_status`, `LevelRuleVersionUnknown`, beside `is_current_pick_rule` (`:1519-1529`) | 1 |
| `lib/strat_levels.py` | `SessionLevels.from_basis` (`:1948-1983`), `_assemble` (`:2444-2449`) | 2 |
| `gcp/premarket_playbook_resolver.py` | `resolve_one` (`:643-879`: the check after `:674-677`, the derive call `:691`, the parse at `:747`), `main` (`:971-1050`) | 3, 4 |
| `lib/agents/summarizers.py` | the section loop of `build_context_bundle` (`:2094-2098`, ahead of `except Exception` at `:2099-2103`), import at `:38` | 6 |
| `gcp/signal_monitor.py` | `refresh_level_map` (`:883-1015`, `from_basis` at `:978-980`), counters (`:185-190`), `SESSION_KEEP` (`:788-794`), session summary (`:2539-2557`), import at `:50` | 6 |
| `platform/api/routers/dashboard.py` | `_build_movement_level_map` (`:414-537`, `from_basis` at `:456-461`, handlers at `:523-537`) | 7 |
| `lib/movement_statement.py` | `_fetch_tracked_levels` (`:412-502`), `_build_levels` (`:542-552`), `assemble_movement_statement` (`:1048-1052`) | 8 |
| `gcp/premarket_brief.py` | `_premarket_from_bars` (`:1105-1164`, the basis read at `:1135-1136`) | 9 |
| `tests/lib/session_levels_helpers.py` | `newer_rule_versions()` | 1 |
| `tests/lib/test_strat_levels.py` | `test_rule_version_status`, `test_from_basis_refuses_a_version_it_does_not_know` | 1, 2 |
| `tests/gcp/test_level_basis.py` | `test_known_versions_round_trip`, `test_each_reader_refuses_a_version_it_does_not_know`, `test_the_insight_run_fails_for_the_ticker_on_a_version_it_does_not_know`, `_planner_query`, `test_a_reader_that_knows_fewer_versions_refuses_then_recovers` | 2, 5, 6, 7 |
| `tests/gcp/test_premarket_playbook_resolver.py` | `test_resolve_one_refuses_a_version_it_does_not_know`, `test_main_exits_non_zero_on_a_refused_row`, `TestScheduledRecovery`, `_ResolverTable` | 3, 4, 5 |
| `tests/lib/test_movement_statement_level_basis.py` | `test_levels_unavailable_for_a_version_the_reader_does_not_know` | 8 |
| `tests/gcp/test_premarket_brief_no_discord.py` | `test_premarket_from_bars_keeps_the_stored_values_for_an_unknown_rule_version` | 9 |
| `tests/meta/test_level_rule_version_readers.py` | `test_no_other_site_compares_a_level_rule_version` (new function; `ALLOWED` unedited) | 10 |
| `docs/product/02-FEATURE-CATALOG.md`, `docs/product/12-PR-ISSUE-TRACEABILITY.md`, `docs/product/03-SITE-TRACEABILITY.md`, `docs/review-evidence/site-source-snapshot.json` | the close | 11 |

---

## Task 1: The classifier

Spec: Design 1. Advances U1.

**Files:** Modify `lib/strat_levels.py` (after `is_current_pick_rule`, `:1525-1529`); Modify `tests/lib/session_levels_helpers.py`; Test `tests/lib/test_strat_levels.py`.

**Interfaces:**
- Produces, in `lib/strat_levels.py`:
  - `RULE_VERSION_LEGACY = 'legacy'`, `RULE_VERSION_KNOWN = 'known'`, `RULE_VERSION_NEWER = 'rule_version_newer'`, `RULE_VERSION_UNREADABLE = 'rule_version_unreadable'`, `REFUSED_RULE_VERSION_STATUSES = frozenset({RULE_VERSION_NEWER, RULE_VERSION_UNREADABLE})`.
  - `rule_version_number(version) -> Optional[int]`.
  - `newest_pick_rule_version() -> str`: the member of `PICK_RULE_VERSIONS` with the largest number, read at call time.
  - `rule_version_status(version) -> str`.
- Produces, in `tests/lib/session_levels_helpers.py`: `newer_rule_versions() -> tuple[str, str, str]`, the newest known plus 1, plus 2, and `'feat-strat-001.v99'`, built from `lib.strat_levels.PICK_RULE_VERSIONS` at call time.

- [ ] **Step 1: Check the base.** `git diff --stat 44dfa3d8c origin/main -- lib gcp platform tests`; re-find any line this plan cites that moved.
- [ ] **Step 2: Write the failing test** `test_rule_version_status`, the table of Design 1 as data:

```python
def test_rule_version_status():
    from lib.strat_levels import PICK_RULE_VERSIONS, rule_version_status
    from tests.lib.session_levels_helpers import newer_rule_versions
    assert rule_version_status(None) == 'legacy'
    assert rule_version_status({}.get('rule_version')) == 'legacy'
    for v in ('feat-strat-001.v1', 'feat-strat-001.v2'):
        assert rule_version_status(v) == 'legacy', v
    for v in PICK_RULE_VERSIONS:
        assert rule_version_status(v) == 'known', v
    assert newer_rule_versions() == ('feat-strat-001.v5', 'feat-strat-001.v6', 'feat-strat-001.v99')
    for v in newer_rule_versions():
        assert rule_version_status(v) == 'rule_version_newer', v
    for v in ('', 'feat-strat-001.v0', 'feat-strat-001.v05', 'feat-strat-001.vX',
              'feat-strat-001.v4 ', 'feat-strat-001.v4\n', 'FEAT-STRAT-001.V4',
              'feat-strat-002.v9', 'feat-strat-001.v\u0665', 5, 5.0, True):
        assert rule_version_status(v) == 'rule_version_unreadable', repr(v)
```

  The `newer_rule_versions()` literal holds on this change's merge base (v3 and v4 known); if the prior-close build merged first, change only that one literal to what the helper returns and say so in the PR body.
- [ ] **Step 3: Write the Review Focus test** `test_a_gap_in_the_known_versions_is_unreadable(monkeypatch)`: patch `lib.strat_levels.PICK_RULE_VERSIONS` to `('feat-strat-001.v3', 'feat-strat-001.v5')`; assert v4 gives `rule_version_unreadable`, v5 `known`, v6 `rule_version_newer`, and `newest_pick_rule_version() == 'feat-strat-001.v5'`.
- [ ] **Step 4: Run** `python3 -m pytest tests/lib/test_strat_levels.py -k "rule_version_status or gap_in_the_known" -q`. Expect FAIL, ImportError on `rule_version_status`.
- [ ] **Step 5: Implement** the interfaces above. `rule_version_status` follows the Global Constraints order exactly and calls `is_current_pick_rule` for rule 3; the newest number is `rule_version_number(newest_pick_rule_version())`. Add a docstring naming the four statuses and the spec.
- [ ] **Step 6: Run** the same command. Expect `2 passed`. Then `python3 -m pytest tests/meta/test_level_rule_version_readers.py tests/lib/test_strat_levels.py -q`. Expect all pass.
- [ ] **Step 7: Render step, then commit** `feat(strat): classify a stored level rule version in one place`.

## Task 2: `from_basis` and `_assemble` refuse; known and legacy versions round trip

Spec: Design 2; Design 4 rows 1 and 4. Advances U2, U3.

**Files:** Modify `lib/strat_levels.py` (`from_basis` `:1948-1983`, `_assemble` `:2444-2449`); Test `tests/lib/test_strat_levels.py`, `tests/gcp/test_level_basis.py`.

**Interfaces:**
- Consumes: Task 1's statuses and `rule_version_status`.
- Produces: `class LevelRuleVersionUnknown(RuntimeError)` beside `LevelParamsUnavailable` (`:1054`), constructed `LevelRuleVersionUnknown(reason: str, recorded)`, with attributes `reason` (the status) and `recorded` (the stored value, unchanged), and a message that begins with `reason`, then the recorded value's `repr`, then `newest_pick_rule_version()`. Every later task catches it by this name.

- [ ] **Step 1: Write the failing test** `test_from_basis_refuses_a_version_it_does_not_know` in `tests/lib/test_strat_levels.py`, parametrized over `newer_rule_versions()` plus `'feat-strat-001.vX'`, `''` and `5`: `basis = {**d8_basis(), 'rule_version': v}`; `with pytest.raises(LevelRuleVersionUnknown) as e: SessionLevels.from_basis(basis)`; assert `e.value.reason == rule_version_status(v)` and `e.value.recorded == v` (`is` for the int), and `str(e.value).startswith(e.value.reason)`. In the same test, the `_assemble` half: build `sl = SessionLevels.from_basis(d8_basis())`, set `sl.rule_version = newer_rule_versions()[0]`, and assert `sl.with_reference(250.0)` (which always goes through `_assemble`, `:1808-1813`) raises `LevelRuleVersionUnknown` with reason `rule_version_newer` and `recorded` the value set.
- [ ] **Step 2: Write the failing test** `test_known_versions_round_trip` in `tests/gcp/test_level_basis.py`:
  - for each `v` in `PICK_RULE_VERSIONS`: `first = json.loads(json.dumps(SessionLevels.from_basis({**d8_basis(), 'rule_version': v}).to_basis()))`; `second = SessionLevels.from_basis(first).to_basis()`; assert `{k: second[k] for k in ('rule_version', 'long', 'short')} == {k: first[k] for k in ('rule_version', 'long', 'short')}` and `first['rule_version'] == v`;
  - a v2 basis (as `test_from_basis_v2_rebuilds_the_v2_targets` builds it, `:578-597`) rebuilds with `rule_version` v2, and a second pass gives an equal `('rule_version', 'long', 'short')`;
  - a v1 basis and a basis with the key removed rebuild with `rule_version` `'feat-strat-001.v2'` and `_exit_picks` equal to the v2 rebuild's.
- [ ] **Step 3: Run** `python3 -m pytest tests/lib/test_strat_levels.py::test_from_basis_refuses_a_version_it_does_not_know tests/gcp/test_level_basis.py::test_known_versions_round_trip -q`. Expect the refusal cases to FAIL (no raise) and the round trip to pass already; paste both into the PR body as the red record.
- [ ] **Step 4: Implement.** `from_basis`: right after the `isinstance(basis, dict)` check (`:1958-1959`) and before `session_date` is read, compute `rule_version_status(basis.get('rule_version'))` and raise `LevelRuleVersionUnknown(status, basis.get('rule_version'))` for a status in `REFUSED_RULE_VERSION_STATUSES`; `:1982-1983` stay as they are. `_assemble`: before `keeps` (`:2448`), the same check on `base.rule_version`; `keeps` and `rule` stay as they are for the statuses that pass.
- [ ] **Step 5: Run** the Step 3 command (expect all pass), then `python3 -m pytest tests/gcp/test_level_basis.py::test_from_basis_v2_rebuilds_the_v2_targets "tests/gcp/test_premarket_playbook_resolver.py::TestPlanInputs::test_a_basis_other_than_v2_or_v3_has_no_plan" tests/meta/test_level_rule_version_readers.py -q` with neither file edited (expect all pass), then `python3 -m pytest tests/lib tests/gcp/test_level_basis.py tests/gcp/test_level_params_consumers.py -q` (expect all pass: no fixture holds a refused value, as the spec's prototype found).
- [ ] **Step 6: Render step, then commit** `feat(strat): refuse a level basis of a rule version this image does not know`.

## Task 3: The resolver refuses a row and writes nothing

Spec: Design 3, row "Resolver `resolve_one`". Advances U4 (first test) and U5 (the derive path).

**Files:** Modify `gcp/premarket_playbook_resolver.py` (`resolve_one`); Test `tests/gcp/test_premarket_playbook_resolver.py`.

**Interfaces:**
- Consumes: `rule_version_status`, `REFUSED_RULE_VERSION_STATUSES`, `LevelRuleVersionUnknown`, `newest_pick_rule_version`, `parse_level_basis`.
- Produces: `resolve_one` returns `(None, status)` with `status` in `REFUSED_RULE_VERSION_STATUSES` for a refused row; its docstring's reason list gains both. Task 4 counts exactly these.

- [ ] **Step 1: Write the failing test** `test_resolve_one_refuses_a_version_it_does_not_know`, parametrized over `(v, reason)`: each of `newer_rule_versions()` with `'rule_version_newer'`, and `''`, `'feat-strat-001.vX'` and the int `5` with `'rule_version_unreadable'`; crossed with `(False, None)` and `(True, '2026-11-16T21:00:00Z')` as `(force, outcome_resolved_at)`. The row is the one in `test_resolve_one_binds_the_plan_columns_from_a_v3_basis` (`:1001-1046`), keeping its ten populated columns (`calls_` and `puts_` `trigger_price`, `stop_price`, `t1_price` to `t3_price`), with `level_basis` `json.dumps({**d8_basis(), 'rule_version': v})` and the given `outcome_resolved_at`. The populated columns are the point: such a row never reaches `from_basis`, so this check is its only guard (spec Design 3, resolver row). Patch `mod.pd.read_sql` with a counter that returns the row on its first call and fails the test on a second; patch `mod.plan_inputs` and `mod.derive_level_map_from_daily` to fail the test. Assert `mod.resolve_one(_date(2026, 11, 16), 'tst', engine, force=force) == (None, reason)`, `engine.conn.calls == []`, one read, and (with `caplog` at ERROR) one record naming `TST`, `2026-11-16`, `repr(v)`, `reason` and `newest_pick_rule_version()`.
- [ ] **Step 2: Write the Review Focus test** `test_resolve_one_returns_the_derive_paths_refusal`: a row with both trigger columns NULL and no `level_basis`; `mod.derive_level_map_from_daily` patched to raise `LevelRuleVersionUnknown('rule_version_newer', newer_rule_versions()[0])`; `read_sql` returns the row once and fails after. Assert `(None, 'rule_version_newer')`, zero write statements, one read.
- [ ] **Step 3: Run** `python3 -m pytest tests/gcp/test_premarket_playbook_resolver.py -k "refuses_a_version or derive_paths_refusal" -q`. Expect FAIL for every version, the unreadable ones included although Task 2 already refuses them in `from_basis`: today the row resolves with `targets_unavailable` and one UPDATE (the spec ran `''`, `'feat-strat-001.vX'` and 5 on main 3a59299ba with that result).
- [ ] **Step 4: Implement** in `resolve_one`: after the already-resolved test (`:674-677`), `basis = parse_level_basis(row.get('level_basis'))` (the line at `:747` is removed and its later uses read this value); when `basis` is a dict and its status is refused, log at ERROR `"%s %s level_basis rule_version %r is %s; this image knows up to %s: not resolved, nothing written"` with ticker, date, stored version, status, `newest_pick_rule_version()`, and return `(None, status)`. Around `derive_level_map_from_daily` (`:691`), `except LevelRuleVersionUnknown as exc`: the same ERROR line from `exc.recorded` and `exc.reason`, return `(None, exc.reason)`.
- [ ] **Step 5: Run** the Step 3 command (expect pass), then `python3 -m pytest tests/gcp/test_premarket_playbook_resolver.py -q` (expect all pass, `TestPlanInputs` unedited).
- [ ] **Step 6: Render step, then commit** `fix(resolver): leave a row of an unknown level rule version unresolved`.

## Task 4: `main()` exits non-zero on a refused row

Spec: Design 3 (resolver row), decision 3. Advances U4 (second test). Builds the table U7b reuses.

**Files:** Modify `gcp/premarket_playbook_resolver.py` (`main`, `:971-1050`); Test `tests/gcp/test_premarket_playbook_resolver.py`.

**Interfaces:**
- Produces, in the test file: `_ResolverTable(rows: list[dict], bars_for: Callable[[date], pd.DataFrame])` with `read_sql(sql, engine, params=None) -> pd.DataFrame` and `engine` (an object whose `begin()` yields a connection that records each statement and applies an `UPDATE premarket_analysis` to the row its `d` and `t` name, setting every bound key except `d` and `t`). It answers: the `pending_dates` statement (rows with `outcome_resolved_at` None, `floor <= analysis_date <= today`, weekday, distinct, ascending, as plain `date`); `SELECT DISTINCT ticker ... WHERE analysis_date = :d`; the `resolve_one` row SELECT; the `market_data_intraday` bars SELECT (from `bars_for`); any other statement fails the test. `.writes` lists the statements applied. Also `_run_main(monkeypatch, table, *, pick=None, **env) -> int`: clears `PLAYBOOK_RESOLVE_*` from the environment, sets `env`, patches `gcp.database.is_cloud_sql_configured` (True), `gcp.database.get_engine` (the table's engine), `mod.pd.read_sql` (the table's), `mod.datetime` (a `datetime` subclass whose `now(tz)` returns 2026-11-17 20:00 in `tz`), and `lib.strat_levels.PICK_RULE_VERSIONS` when `pick` is given; returns `mod.main([])`.
- Produces, in the test file: `_session_bars(d: date) -> pd.DataFrame`, the four bars of the v3 plan test (`:1014-1019`) at 09:30, 09:31, 09:32 and 15:59 Eastern on `d`, placed with `lib.eastern_time.eastern_bounds_utc(d, time(9, 30), time(16, 0))[0]` plus minutes.

- [ ] **Step 1: Write the failing test** `test_main_exits_non_zero_on_a_refused_row`, parametrized over `(v, reason)` in `(newer_rule_versions()[0], 'rule_version_newer')` and `('', 'rule_version_unreadable')`: one row dated 2026-11-17 (today), ticker `TST`, the v3 plan row (its trigger, stop and target columns populated) with `level_basis` of `v`, unresolved. Assert `_run_main(monkeypatch, table) == 1`, `table.writes == []`, and an ERROR record holding `TST`, `2026-11-17`, `repr(v)`, `reason` and `newest_pick_rule_version()`.
- [ ] **Step 2: Write the Review Focus test** `test_main_exits_non_zero_on_a_refused_row_on_a_past_date`: the same row dated 2026-11-16, alone on its date. Assert 1, no writes, and an INFO `done 2026-11-16:` line holding `1 refused`.
- [ ] **Step 3: Run** `python3 -m pytest tests/gcp/test_premarket_playbook_resolver.py -k "main_exits" -q`. Expect FAIL: today the row is stamped and `main()` returns 0.
- [ ] **Step 4: Implement** in `main`: `n_refused` per date and in total; a `resolve_one` reason in `REFUSED_RULE_VERSION_STATUSES` adds to it and to neither `n_skipped` nor `n_noop`; the `done` line becomes `"done %s: %d resolved, %d already-resolved, %d skipped, %d refused (%s)"`; after the loop, when the total is above 0, log at ERROR the count and that rows were left pending for an image that knows their version, and return 1.
- [ ] **Step 5: Run** the Step 3 command (expect pass) and the whole resolver file (expect all pass).
- [ ] **Step 6: Render step, then commit** `fix(resolver): exit non-zero when a row's level rule version is unknown`.

## Task 5: Mixed rollout, rollback and recovery through the scheduled run

Spec: Design 4, including "Recovery goes through the scheduled run". Advances U7, U7b.

**Files:** Test `tests/gcp/test_level_basis.py`, `tests/gcp/test_premarket_playbook_resolver.py`. No production file changes unless a case fails for a reason Tasks 2 to 4 did not cover; then fix it in the file that owns it and say so in the PR body.

**Interfaces:** Consumes `_ResolverTable`, `_run_main`, `_session_bars` (Task 4).

- [ ] **Step 1: Write** `test_a_reader_that_knows_fewer_versions_refuses_then_recovers` in `tests/gcp/test_level_basis.py`. `written = json.loads(json.dumps(SessionLevels.from_basis(d8_basis()).to_basis()))` with the patch off (so `written['rule_version'] == LEVEL_RULE_VERSION`). With `lib.strat_levels.PICK_RULE_VERSIONS` patched to `(LEVEL_RULE_V3,)`: `from_basis(written)` raises with reason `rule_version_newer`; `resolve_one` on the v3 plan row carrying `written` returns `(None, 'rule_version_newer')` with `engine.conn.calls == []`; and a row carrying `written` already stamped (`outcome_resolved_at` set) and `force=True` gives the same with no write. With the patch undone (`monkeypatch.undo()`): `from_basis(written).to_basis()` equals `written` on `('rule_version', 'long', 'short')`, and `resolve_one` returns `'resolved'` with `calls_plan_r_status == 'ok'` bound.
- [ ] **Step 2: Write** `class TestScheduledRecovery` in `tests/gcp/test_premarket_playbook_resolver.py`, today 2026-11-17, default lookback 14 (floor 2026-11-03), `PLAYBOOK_RESOLVE_DATE` unset unless a case says so, straggler meaning `pick=('feat-strat-001.v3',)`. Rows are the v3 plan row with `d8_basis()` stamped `'feat-strat-001.v3'` (resolvable by a straggler) or `LEVEL_RULE_VERSION` (refused by it):
  1. `test_a_straggler_resolves_the_row_it_knows_and_leaves_the_other`: `AAA` v3 and `BBB` v4, both 2026-11-16. Straggler run returns 1; `AAA` has `outcome_resolved_at` set and `calls_plan_r_status == 'ok'`; `BBB`'s `outcome_resolved_at`, `calls_plan_r_status`, `puts_plan_r_status` and every `*_plan_*` column equal their values before the run.
  2. `test_a_compatible_image_resolves_it_unforced`: continue from case 1's table with no patch and no `PLAYBOOK_RESOLVE_FORCE`. The `pending_dates` read returned `[date(2026, 11, 16)]`; `BBB` is resolved, `calls_plan_r_status == 'ok'`; `main()` returns 0.
  3. `test_the_lookback_boundary`: one unresolved v4 row at 2026-11-03 and one at 2026-11-02, compatible image. The `pending_dates` answer is `[date(2026, 11, 3)]`; only the 11-03 row is written.
  4. `test_after_age_out`: a v4 row at 2026-11-02. Straggler run: `main()` returns 0 and no statement names 2026-11-02. Compatible run with `PLAYBOOK_RESOLVE_DATE=2026-11-02` and `PLAYBOOK_RESOLVE_LOOKBACK_DAYS` unset: resolved, `calls_plan_r_status == 'ok'`.
  5. `test_a_row_an_older_reader_stamped`: a v4 row at 2026-11-16 with `outcome_resolved_at` set, `calls_plan_r_status` and `puts_plan_r_status` `'targets_unavailable'`, `calls_plan_r` None. Compatible run unforced: returns 0, no write. Compatible run with `PLAYBOOK_RESOLVE_FORCE=true` alone: returns 0, no write. Compatible run with `PLAYBOOK_RESOLVE_DATE=2026-11-16` and `PLAYBOOK_RESOLVE_FORCE=true`: one write, `calls_plan_r_status == 'ok'`. Straggler run with the same two variables on a fresh copy of the stamped row: returns 1, no write.
  6. `test_an_unreadable_version_is_refused_by_every_image`: no `pick` patch, since every image with this change refuses it. Three unresolved rows dated 2026-11-16 (inside the window), `UA` with `rule_version` `''`, `UB` with `'feat-strat-001.vX'` and `UC` with the int `5`, each the v3 plan row with its ten trigger, stop and target columns populated. Run returns 1; `table.writes == []`; each row's `outcome_resolved_at`, `calls_plan_r_status`, `puts_plan_r_status` and every `*_plan_*` column equal their values before the run; three ERROR records, one per ticker, each holding the ticker and `rule_version_unreadable`.
- [ ] **Step 3: Run** `python3 -m pytest tests/gcp/test_level_basis.py::test_a_reader_that_knows_fewer_versions_refuses_then_recovers "tests/gcp/test_premarket_playbook_resolver.py::TestScheduledRecovery" -q`. Expect pass on the branch. Then show the red record U7b names: on a worktree of the merge base with this test file copied in, cases 1 and 6 fail (the merge base has no refusal, so `BBB`, `UA`, `UB` and `UC` are stamped `targets_unavailable`); paste that output into the PR body.
- [ ] **Step 4: Commit** `test(resolver): pin rollout, rollback and recovery for an unknown rule version`.

## Task 6: The insight planner and the signal monitor refuse by name

Spec: Design 3, rows "Insight planner" and "Signal monitor", decision 4. Advances U5.

**Files:** Modify `lib/agents/summarizers.py` (`:38`, `:2094-2098`), `gcp/signal_monitor.py` (`:50`, `:185-190`, `:788-794`, `:978-980`, `:2539-2557`); Test `tests/gcp/test_level_basis.py`. `gcp/insight_pipeline_job.py` is not edited (Choice 4).

**Interfaces:**
- Consumes: `LevelRuleVersionUnknown`.
- Produces: `SignalMonitor.level_refresh_rule_version_unknown_count: dict` (per ticker, initialised to 0 like `:190`), listed in `SESSION_KEEP` and printed by the session summary as `level_refresh_rule_version_unknown=%d`. Produces the test `test_each_reader_refuses_a_version_it_does_not_know` with its parameter list `reader in ('planner', 'signal_monitor', 'api', 'resolver_derive')` crossed with `newer_rule_versions()`; Task 7 fills the `api` case. Produces `_planner_query(db)` in `tests/gcp/test_level_basis.py`: the `q` that `_planner_section` (`:278-295`) builds today, factored out so `_planner_section` and the insight run test share it.

- [ ] **Step 1: Write the failing test** `test_each_reader_refuses_a_version_it_does_not_know(monkeypatch, brief_basis, reader, version)` on `db = _AnalysisDb([_row({**brief_basis, 'rule_version': version})])` (the live QQQ 2026-11-06 basis, only the version changed):
  - `planner`: `pytest.raises(LevelRuleVersionUnknown)` around `_planner_section(monkeypatch, db)`;
  - `signal_monitor`: a copy of `_monitor_session` that returns the monitor; assert `monitor.level_maps.get('QQQ') is None`, `'QQQ' not in monitor.session_levels`, `'QQQ' not in monitor.level_map_atr`, `monitor.level_refresh_rule_version_unknown_count['QQQ'] == 1`, `monitor.level_refresh_exception_count.get('QQQ', 0) == 0`, and an ERROR record holding `rule_version_newer`;
  - `resolver_derive`: `pytest.raises(LevelRuleVersionUnknown)` around `_resolver_inputs(db)`;
  - `api`: `pytest.skip('Task 7')` for now.
  In every case no level, target or plan is returned.
- [ ] **Step 2: Write the failing test** `test_the_insight_run_fails_for_the_ticker_on_a_version_it_does_not_know(monkeypatch, brief_basis, version, reason)` in `tests/gcp/test_level_basis.py`, parametrized over `(newer_rule_versions()[0], 'rule_version_newer')` and `('', 'rule_version_unreadable')`, through the real `summarize_session_levels` on `db = _AnalysisDb([_row({**brief_basis, 'rule_version': version})])`:
  - Stubs, as `_stub_other_sections` in `tests/gcp/test_level_params_consumers.py` (`:127-135`) does for `LevelParamsUnavailable`: the seven summarizers other than `summarize_session_levels` return `{"available": True}`. Unlike that helper, `_query_strict` stays on the autouse `_level_params` fixture, so the parameters read and the version is the only failure. `summarizers._query` is `_planner_query(db)`; `lib.data_loader.DataLoader` fails the test (a stored basis loads no daily bars); `_refuse_network` from that file, imported inside the test.
  - The bundle: `with pytest.raises(LevelRuleVersionUnknown) as e: summarizers.build_context_bundle('QQQ', SESSION)`; `e.value.reason == reason`.
  - The run, as `test_insight_run_records_failed_with_the_reason` (`:147-162` of that file) does: `job._transition` records, `job.load_routes_snapshot` returns an object, `job._insert_report_history` and `job._upsert_report` fail the test. `asyncio.run(job._run_one('run-1', 'QQQ', as_of=SESSION)) is False`; the transitions are `['running', 'failed']`; the failed `error` starts with `reason`.
- [ ] **Step 3: Run** `python3 -m pytest tests/gcp/test_level_basis.py::test_each_reader_refuses_a_version_it_does_not_know tests/gcp/test_level_basis.py::test_the_insight_run_fails_for_the_ticker_on_a_version_it_does_not_know -q`. Expect the planner and derive cases to pass already (Task 2 raises), and the signal monitor case and both insight run cases to FAIL: `build_context_bundle` returns a bundle with `session_levels` unavailable, reason `exception: ...`, and raises nothing (what the spec ran on main with a stand-in). Paste the output.
- [ ] **Step 4: Implement.** Summarizers: `except (LevelParamsUnavailable, LevelRuleVersionUnknown): raise` at `:2094`, ahead of `except Exception` (`:2099-2103`), with the comment naming decision 4. Signal monitor: wrap the `from_basis` call at `:980` in `try` / `except LevelRuleVersionUnknown as exc`: bump the counter, `logger.error("refresh_level_map(%s): level refresh skipped, reason=%s (stored rule_version %r)", ticker, exc.reason, exc.recorded)`, `self.level_maps[ticker] = None`, `self.session_levels.pop(ticker, None)`, `self.level_map_atr.pop(ticker, None)`, `return`. It never falls to `build_session_levels`.
- [ ] **Step 5: Run** the Step 3 command (expect pass except the `api` skips), then `python3 -m pytest tests/gcp/test_replay_daily_cap.py tests/gcp/test_signal_monitor_level_refresh.py tests/gcp/test_level_params_consumers.py tests/agents -q` (expect all pass; `test_replay_daily_cap` enumerates per-ticker dicts and needs the new one in `SESSION_KEEP`).
- [ ] **Step 6: Render step, then commit** `fix(levels): skip a level refresh or an insight run on an unknown rule version`.

## Task 7: The API returns no level map

Spec: Design 3, row "API `_build_movement_level_map`". Advances U5. (The insight run's half of U5 is Task 6.)

**Files:** Modify `platform/api/routers/dashboard.py` (`:436-441` imports, `:523-537` handlers); Test `tests/gcp/test_level_basis.py`.

- [ ] **Step 1: Replace the `api` skip** in `test_each_reader_refuses_a_version_it_does_not_know` with: `_movement_map(monkeypatch, db) is None`, and an ERROR record holding `QQQ` and `rule_version_newer` (today the broad handler logs it at WARNING).
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_level_basis.py::test_each_reader_refuses_a_version_it_does_not_know -q`. Expect the `api` cases to FAIL on the log level.
- [ ] **Step 3: Implement** in `_build_movement_level_map`: import `LevelRuleVersionUnknown`; a handler `except LevelRuleVersionUnknown as exc:` placed before `except Exception`, `logger.error("movement-statement level map for %s refused: %s (stored rule_version %r)", ticker, exc.reason, exc.recorded)`, `return None`.
- [ ] **Step 4: Run** the Step 2 command (expect all pass, no skips), then `python3 -m pytest tests/api -q -k "movement or dashboard"` (expect all pass).
- [ ] **Step 5: Render step, then commit** `fix(api): refuse an unknown level rule version in the movement level map`.

## Task 8: The movement statement says why

Spec: Design 3, row "Movement statement"; Design 2 (both refused statuses). Advances U6. U6 names newer versions only; this task also tests the three unreadable values, because `_fetch_tracked_levels` reads the basis through `_new_rule_mark` (`lib/movement_statement.py:505-518`), which reads any version it does not recognise as legacy (a review note on spec PR #2025; the plan carries it, the spec is unchanged).

**Files:** Modify `lib/movement_statement.py` (`_fetch_tracked_levels` `:412-502`, `_build_levels` `:542-552`, `assemble_movement_statement` `:1048-1052`); Test `tests/lib/test_movement_statement_level_basis.py`.

**Interfaces:**
- Consumes: `rule_version_status`, `REFUSED_RULE_VERSION_STATUSES`, `parse_level_basis`.
- Produces: for a refused row, `_fetch_tracked_levels` returns `_unavailable(f"{status}: premarket_analysis row for {TICKER} on {session_date} has level_basis rule_version {recorded!r}; this image knows up to {newest}", rule_version=recorded, rule_version_status=status)`. `_build_levels` and `assemble_movement_statement` recognise it by `tracked.get('rule_version_status') in REFUSED_RULE_VERSION_STATUSES`.

- [ ] **Step 1: Capture the merge base's answers.** Before any edit, run the end-to-end call of Step 2 for a session row whose basis is v3, v4, v2, and for a row with no basis, and print `out['levels']` for each; paste them into the test as literals and into the PR body.
- [ ] **Step 2: Write the failing test** `test_levels_unavailable_for_a_version_the_reader_does_not_know(monkeypatch, version, status, with_map)`, parametrized over `(version, status)`: each of `newer_rule_versions()` with `'rule_version_newer'`, and `''`, `'feat-strat-001.vX'` and the int `5` with `'rule_version_unreadable'`; crossed with `with_map in (True, False)`. Built on `test_each_rung_shows_its_own_slots_rate` (`:129-168`) with the session row's `level_basis` stamped `version`, and a `q` that records every statement. Assert: `ms._fetch_tracked_levels('SPY', db.query, SESSION)` has `status == 'UNAVAILABLE'`, `reason.startswith(status)`, `rule_version == version` (the stored value unchanged, the int included), `rule_version_status == status`; `assemble_movement_statement(..., level_map=lm if with_map else None, ...)` records no statement holding `outcome_resolved_at IS NOT NULL` (the reach query's `WHERE`, `:286-350`), so zero reach-rate queries, and `out['levels']` equals `{'status': 'UNAVAILABLE', 'reason': <the tracked reason>, 'rule_version': version, 'rule_version_status': status}`. A second parametrized case over v3, v4, v2 and no basis asserts `out['levels']` equals the Step 1 literal.
- [ ] **Step 3: Run** `python3 -m pytest tests/lib/test_movement_statement_level_basis.py -k "does_not_know" -q`. Expect every refused case to FAIL, the unreadable ones included (today `_new_rule_mark` returns None for them, so the row seeds from its price and both reach queries run), and the legacy and known cases to pass.
- [ ] **Step 4: Implement.** `_fetch_tracked_levels`: parse `stored` before `_side` is first called; when it is a dict with a refused status, return the envelope above. `_build_levels`: before `if level_map is None` (`:551`), return `_unavailable(tracked['reason'], rule_version=..., rule_version_status=...)` for a refused `tracked`. `assemble_movement_statement`: for a refused `tracked`, set `reach_calls` and `reach_puts` to `tracked` and skip both `_fetch_reach_rates` calls. The headline path is untouched.
- [ ] **Step 5: Run** `python3 -m pytest tests/lib/test_movement_statement_level_basis.py -q` (expect all pass) and `python3 -m pytest tests/lib/test_movement_statement.py -q` if `lightgbm` imports (the spec could not run it; record either the result or the import error in the PR body).
- [ ] **Step 6: Render step, then commit** `fix(movement): say why the levels are unavailable for an unknown rule version`.

## Task 9: The brief's dry run keeps the stored values

Spec: Design 3, row "Brief dry run". Advances U8.

**Files:** Modify `gcp/premarket_brief.py` (`_premarket_from_bars`, `:1105-1164`); Test `tests/gcp/test_premarket_brief_no_discord.py`.

- [ ] **Step 1: Write the failing test** `test_premarket_from_bars_keeps_the_stored_values_for_an_unknown_rule_version`, built like `_direct` (`:932-954`) with the basis `{'rule_version': newer_rule_versions()[0], 'premarket': {'fetched_at': BRIEF_CUTOFF}}` and the stored row `{'pre_high': 101.25, 'pre_low': 99.10, ...}`. Assert `snap is None`; the line holds `rule version unavailable`, the stored version, `rule_version_newer`, `stored high=101.2500`, `stored low=99.1000` and ends with `(kept)`; no statement in `seen` holds `BARS_SQL`.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_premarket_brief_no_discord.py -k unknown_rule_version -q`. Expect FAIL: today the bars are read and a snapshot returned.
- [ ] **Step 3: Implement** after `basis = read_live_level_basis(...)` (`:1135`): when `basis` is a dict whose status is refused, return `(None, f"{head} rule version unavailable: {recorded} is {status} {was} (kept)")`. The cutoff code that follows is unchanged.
- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_premarket_brief_no_discord.py -q`. Expect all pass.
- [ ] **Step 5: Render step, then commit** `fix(brief): keep the stored premarket values when the basis version is unknown`.

## Task 10: The one-helper rule holds

Spec: Design 1 ("No watched constant sits in a comparison"); U9 as revised, which allows and pins the three legacy checks against `LEVEL_RULE_V2` (Choice 1). Advances U9.

**Files:** Test `tests/meta/test_level_rule_version_readers.py` (a new function and its own site list; `ALLOWED`, `WATCHED`, `sites`, `scan` and both existing tests unedited).

**Interfaces:** Produces `LEVEL_RULE_COMPARISONS`, a dict `(file, function) -> why` naming exactly: `('lib/strat_levels.py', 'is_current_pick_rule')`; `('lib/strat_levels.py', '_assemble')`, `('lib/strat_levels.py', '_pick_side')` and `('gcp/premarket_playbook_resolver.py', 'plan_inputs')`, each "U9: a legacy check against LEVEL_RULE_V2 that keeps a v2 basis's own plan, unchanged (spec Non-goals; U3)". The two reach-population lines of `lib/movement_statement.py` that U9 also allows bind the version as a query parameter and hold no `Compare`, so the scan does not list them.

- [ ] **Step 1: Write the test** `test_no_other_site_compares_a_level_rule_version`: walk every `*.py` under `lib`, `gcp` and `platform` as `scan()` does; a site is an `ast.Compare` one of whose operands holds a `Name` or `Attribute` named `LEVEL_RULE_V2`, `LEVEL_RULE_V3`, `LEVEL_RULE_VERSION` or `PICK_RULE_VERSIONS`, a string constant starting `feat-strat-001.`, or a call `.get('rule_version')` or subscript `['rule_version']`, not counting what sits inside the arguments of a call to `rule_version_status` or `is_current_pick_rule` (handing the stored version to the helper is the allowed route, and `rule_version_status(basis.get('rule_version')) in REFUSED_RULE_VERSION_STATUSES` would otherwise count). Assert the set of `(file, function)` found equals the keys of `LEVEL_RULE_COMPARISONS`, and that `rule_version_status` and `newest_pick_rule_version` hold no such site. Add a shape test on a source string: `x.get('rule_version') == 'feat-strat-001.v5'`, `b['rule_version'] in VERSIONS` and `v != LEVEL_RULE_V2` are found; `self.rule_version == 'legacy-pattern-v1'` (the Strat classifier's own version, `lib/strat.py:321`) and `rule_version_status(basis.get('rule_version')) in REFUSED_RULE_VERSION_STATUSES` are not. Run on origin/main e5bd59eba, this definition found exactly the four keys (`plan_inputs` `:625`, `_assemble` `:2448`, `_pick_side` `:2818`, `is_current_pick_rule` `:1529`), and on the shape strings it gave the answers above; without the helper-argument exclusion it also counted the refusal check.
- [ ] **Step 2: Run** `python3 -m pytest tests/meta/test_level_rule_version_readers.py -q`. Expect all pass; if a site outside the list is found, it is new code from Tasks 1 to 9: route it through `rule_version_status` instead of listing it.
- [ ] **Step 3: Check the map is unedited:** `git diff origin/main -- tests/meta/test_level_rule_version_readers.py` shows added lines only, none inside `ALLOWED = {...}`.
- [ ] **Step 4: Commit** `test(meta): pin every comparison of a level rule version`.

## Task 11: Close: product record, site note and the gate

Spec: done_when U10; Capacity; Close-out; product-delivery Phase 4 and Phase 5. Closes U10. Once the site-note steps start, no file under `gcp/`, `lib/`, `platform/`, `scripts/` or `tests/` changes without redoing them: the source hash covers those paths.

- [ ] Run `make test` on the head. Expect it to finish with no failure; paste the summary line into the PR body.
- [ ] Read the resolver job's `--max-retries` in `gcp/deploy.sh` (`grep -n "premarket-playbook-resolver" -A30 gcp/deploy.sh`) and state it in the PR body's Capacity section beside the spec's figures (Global Constraints).
- [ ] Push with `git push -u origin feature/feat-strat-001-unknown-rule-version` and open a **draft** PR titled as in Global Constraints. Body: the spec's and this plan's paths; U1 to U10 with U7b as `- [ ]` lines; `Red then green` (every Step "Run ... Expect FAIL" output, Task 5's merge-base run of cases 1 and 6, Task 8 Step 1's literals); the Capacity section; this plan's "Choices" list.
- [ ] Set `pr:` in this plan to the PR's number and commit it.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, the `### FEAT-STRAT-001` record (`:233` on 44dfa3d8c): append this PR to its Status text (implementation under review, not deployed) and set Last reviewed to the date of the PR's head commit. `docs/product/12-PR-ISSUE-TRACEABILITY.md`, `### FEAT-STRAT-001` (`:547`): append the PR to its PR lineage, naming spec PR #2025. Commit: `docs(product): record the unknown rule version refusal under FEAT-STRAT-001`.
- [ ] Site note, step 1: with a clean tree, `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`; copy its `source_identity_sha256`.
- [ ] Site note, step 2: in `docs/product/03-SITE-TRACEABILITY.md`, the `| FEAT-STRAT-001 | DASHBOARD-01 |` row (`:1351` on 44dfa3d8c) and no other byte: `source_identity_sha256=<the hash>; `, then this change's prose (a stored level basis of a rule version the image does not know, or cannot read, is refused by `lib.strat_levels.rule_version_status`: the resolver leaves the row pending and exits 1, the movement statement's levels block is UNAVAILABLE with the reason, the API's level map is None, the signal monitor skips the ticker's level refresh, the insight run fails; tests named), then ` Earlier: ` and the earlier prose unchanged. Commit: `docs(site): note the unknown rule version refusal on DASHBOARD-01`.
- [ ] Site note, steps 3 and 4: run `produce` again and commit `docs(site): regenerate the source snapshot`; then `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` (expect exit 0). If `origin/main` moved, update the branch by merge (never rebase), re-render and redo the four steps.
- [ ] Render step once more and `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect all pass).
- [ ] Docs audit: `python3 scripts/maintenance/docs_audit.py` on the branch and on a detached `origin/main` worktree; the branch reports no line that `main` does not.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` (expect exit 0).
- [ ] Push; tick each done_when box with its evidence; only then mark the PR ready. No gate file is touched, so no red-team pass is owed.

## Close-out (not tasks; the owner's steps)

From the spec's Close-out and Design 5. None is done by the implementer and none is a done_when box.

- Deploy every reader of a stored basis from `main` at or after the merge: the resolver, the API, the signal monitor, the insight pipeline and the brief. Only then deploy the prior-close build's first v5 writer.
- Do not roll a reader back past this change once newer rows exist.
- A row an older reader already stamped `targets_unavailable` is repaired only by an owner-approved run with `PLAYBOOK_RESOLVE_DATE` and `PLAYBOOK_RESOLVE_FORCE=true` on a compatible image (Design 4). Nothing here finds or counts such rows.
- On a `docs/` branch after the merge: this plan's `status: done`.
