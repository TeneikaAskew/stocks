---
feat_id: FEAT-STRAT-001
req_ids: [REQ-DATA-001, REQ-DATA-003, REQ-PLAYBOOK-001, REQ-REL-001]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01]
done_when:
  - "U1 one classifier: tests/lib/test_strat_levels.py::test_rule_version_status passes on lib.strat_levels.rule_version_status with the table of Design 1 written in the test: None and a missing key give legacy; feat-strat-001.v1 and .v2 give legacy; every member of PICK_RULE_VERSIONS gives known; newest known plus 1, plus 2 and feat-strat-001.v99 (built in the test from PICK_RULE_VERSIONS, so v5, v6 and v99 on this change's merge base) give rule_version_newer; '', 'feat-strat-001.v0', '.v05', '.vX', a trailing space, a trailing newline, upper case, 'feat-strat-002.v9', an Arabic-Indic digit, the int 5, the float 5.0 and True give rule_version_unreadable"
  - "U2 the rebuild refuses: tests/lib/test_strat_levels.py::test_from_basis_refuses_a_version_it_does_not_know passes: for newest plus 1, newest plus 2, v99 and three unreadable values SessionLevels.from_basis raises lib.strat_levels.LevelRuleVersionUnknown whose reason is the classifier's status and whose recorded is the stored value unchanged, and returns no SessionLevels; _assemble raises the same for an in-memory SessionLevels of such a version in place of relabelling it"
  - "U3 known and legacy versions are untouched: tests/gcp/test_level_basis.py::test_known_versions_round_trip passes: for each member of PICK_RULE_VERSIONS a basis produced by to_basis rebuilds to an equal dict (rule_version, both sides, targets, plan); a v2 basis keeps v2 and is equal after a second pass; a v1 basis and a basis with no rule_version rebuild under the v2 rule with the picks of the v2 rebuild; tests/gcp/test_level_basis.py::test_from_basis_v2_rebuilds_the_v2_targets and tests/gcp/test_premarket_playbook_resolver.py::TestPlanInputs::test_a_basis_other_than_v2_or_v3_has_no_plan pass with no edit"
  - "U4 the resolver writes nothing: tests/gcp/test_premarket_playbook_resolver.py::test_resolve_one_refuses_a_version_it_does_not_know passes, parametrized over newest plus 1, plus 2 and v99 (reason rule_version_newer) and over '', 'feat-strat-001.vX' and the int 5 (reason rule_version_unreadable), each on a row whose calls and puts trigger, stop and t1 to t3 columns are populated, each with force False on an unresolved row and force True on a resolved row: resolve_one returns (None, that reason), the recording engine holds zero write statements (the row's own SELECT, which classifies its version, is the one read), the bars are not read, and plan_inputs is not called; ::test_main_exits_non_zero_on_a_refused_row passes, parametrized over newest plus 1 and '': one refused row on today's date makes main() return 1 and log the ticker, the date, the stored version, its reason and the newest known"
  - "U5 every other reader refuses by name: tests/gcp/test_level_basis.py::test_each_reader_refuses_a_version_it_does_not_know passes, parametrized over the insight planner, the signal monitor, the API level map and the resolver's derive path, each over newest plus 1, plus 2 and v99, on the live QQQ 2026-11-06 basis with only rule_version changed: summarize_session_levels raises LevelRuleVersionUnknown (no section, so no report carries a relabelled basis); refresh_level_map leaves level_maps and session_levels without the ticker, adds one to level_refresh_rule_version_unknown_count and logs the status; _build_movement_level_map returns None; derive_level_map_from_daily raises; no reader returns a level, a target or a plan; and through the insight run's own path, tests/gcp/test_level_basis.py::test_the_insight_run_fails_for_the_ticker_on_a_version_it_does_not_know passes over newest plus 1 and '', with every other section stubbed available as tests/gcp/test_level_params_consumers.py does for LevelParamsUnavailable: lib.agents.summarizers.build_context_bundle raises LevelRuleVersionUnknown out of its section loop (its except Exception, lib/agents/summarizers.py:2099-2103 on main, does not turn it into an unavailable section), and gcp.insight_pipeline_job._run_one for the ticker returns False, records the run failed and calls neither _insert_report_history nor _upsert_report"
  - "U6 the movement statement says why: tests/lib/test_movement_statement_level_basis.py::test_levels_unavailable_for_a_version_the_reader_does_not_know passes: for a live row of newest plus 1, plus 2 and v99, _fetch_tracked_levels returns an UNAVAILABLE envelope whose reason starts with rule_version_newer and that carries rule_version (the stored value) and rule_version_status; assemble_movement_statement issues no reach-rate query for it and its levels block is UNAVAILABLE with that reason, whether or not a level map was passed; a v3, a v4, a v2 and a row with no basis give what they give on the merge base"
  - "U7 mixed rollout and rollback: tests/gcp/test_level_basis.py::test_a_reader_that_knows_fewer_versions_refuses_then_recovers passes with lib.strat_levels.PICK_RULE_VERSIONS patched to (v3,) so the reader is a straggler or a rolled-back image and the row is a real basis of LEVEL_RULE_VERSION written by the unpatched code: from_basis raises rule_version_newer, resolve_one returns (None, 'rule_version_newer') with zero write statements, and with the patch removed the same stored row rebuilds equal to what was written and resolve_one resolves it with its plan columns bound (r_status ok); a row resolved before the rollback is not rewritten under PLAYBOOK_RESOLVE_FORCE"
  - "U7b recovery through the scheduled path, not a direct call: tests/gcp/test_premarket_playbook_resolver.py::TestScheduledRecovery passes, each case driving main() with PLAYBOOK_RESOLVE_DATE unset and the default lookback against a recording engine, the reader made a straggler by patching lib.strat_levels.PICK_RULE_VERSIONS: (1) one refused row and one resolvable row on the same date inside the window: the resolvable row is resolved and stamped, the refused row's outcome_resolved_at, r_status and plan columns are unchanged, and main() returns non-zero; (2) the patch removed (a compatible image) and the same rows: pending_dates finds the refused row's date and main() resolves it with PLAYBOOK_RESOLVE_FORCE unset, r_status ok; (3) the lookback boundary: a row dated today minus the lookback is selected by pending_dates and a row dated one day earlier is not; (4) after age-out: the refused row dated one day before the floor is not selected by the scheduled run, and PLAYBOOK_RESOLVE_DATE set to its date resolves it with PLAYBOOK_RESOLVE_FORCE unset and PLAYBOOK_RESOLVE_LOOKBACK_DAYS unchanged; (5) a row stamped by a reader older than this change (outcome_resolved_at set, r_status targets_unavailable, plan_r NULL): pending_dates never selects it, PLAYBOOK_RESOLVE_FORCE=true alone does not reach it, and PLAYBOOK_RESOLVE_DATE with PLAYBOOK_RESOLVE_FORCE=true re-resolves it on a compatible image, while under a still-straggling image the same forced run refuses it with zero write statements and returns non-zero; (6) an unreadable version, with no patch since every image with this change refuses it: one row each of '', 'feat-strat-001.vX' and the int 5, their trigger, stop and target columns populated, on a date inside the window: the recording engine holds zero write statements, each row's outcome_resolved_at, r_status and plan columns are unchanged, and main() returns non-zero and logs each row with reason rule_version_unreadable; fails on origin/main, where nothing refuses and cases (1) and (6) stamp the refused rows targets_unavailable"
  - "U8 the brief's dry run: tests/gcp/test_premarket_brief_no_discord.py::test_premarket_from_bars_keeps_the_stored_values_for_an_unknown_rule_version passes: _premarket_from_bars on a live basis of newest plus 1 returns (None, line) with the line naming rule_version_newer and the stored high and low kept, and reads no bars"
  - "U9 the one-helper rule holds: tests/meta/test_level_rule_version_readers.py passes with its ALLOWED map unedited, and lib/, gcp/ and platform/ hold no comparison of a stored rule_version outside lib.strat_levels.rule_version_status, is_current_pick_rule, the two reach-population lines of lib/movement_statement.py, and the three legacy checks against LEVEL_RULE_V2 that keep a v2 basis's own plan (gcp/premarket_playbook_resolver.py plan_inputs, lib/strat_levels.py _assemble and _pick_side; at :625, :2448 and :2818 on 44dfa3d8c), which a test in tests/meta/test_level_rule_version_readers.py pins by file and function so a new comparison fails it"
  - "U10 close: make test passes on the PR head; the FEAT-STRAT-001 catalog record and the PR traceability entry are updated; the (FEAT-STRAT-001, DASHBOARD-01) implementation-source note carries the source identity that scripts/maintenance/doc_source_snapshot.py produce and verify prove on the committed head; python3 scripts/maintenance/docs_audit.py on the branch reports nothing origin/main does not; python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: null
---

# A stored level basis of a rule version the code does not know is refused, never rebuilt under an older rule

## Authority and status

Draft. The owner has not approved it (handoff of 2026-11-16, section 4 item 2: "The owner has not yet
said yes"). Line numbers are as of 8250bff75, the head of
`origin/feature/feat-playbook-001-brief-says-what-the-data-says` (PR #2010, not merged), unless a
line says `main`, which is 21e4de31d. "Run" means run by this spec's author on a scratch checkout of
that commit, removed afterwards; "read" means read there. Nothing in production was read or changed.

A review comment on PR #2021 corrected an earlier statement of this problem: the resolver does not
downgrade. The Problem section is therefore written caller by caller, each one run.

## Review changes, 2026-11-17

Two Codex findings on PR #2025, each checked on main at 3a59299ba first. Changed for re-approval:
U5 and Design 3's insight planner row (the refusal must escape `build_context_bundle`'s
`except Exception`, and the ticker's run writes no report), and U4, U7b case 6 and Design 3's
resolver row (an unreadable version is refused by the resolver too, on a row with populated
trigger columns, with zero writes and a non-zero exit naming `rule_version_unreadable`). No
decision changed.

- U9: corrected after the plan found three existing comparisons against the legacy constant `LEVEL_RULE_V2` (`gcp/premarket_playbook_resolver.py:625`, `lib/strat_levels.py:2448` and `:2818` on 44dfa3d8c). They keep a v2 basis's own plan, which U3 requires, so U9 now names them as allowed and pins them, instead of saying no other comparison exists.

## Capability

FEAT-STRAT-001 (`docs/product/02-FEATURE-CATALOG.md:23`): STRAT / levels; "Candle classification,
FTFC, structural levels"; routes `/charts`, `/live`; backend "via `lib/`"; data `strat_levels`,
`strat_combo_results`, `level_param_policy`, `ticker_level_params`; status "Production but needs
remediation"; P0; phase 1. Requirements: REQ-DATA-001 (no silent substitute; unavailability is
explicit), REQ-DATA-003 (a derived record carries its rule version, so a reader must honour it),
REQ-PLAYBOOK-001 (a plan marks unavailable fields), REQ-REL-001 (live and replay read one rule).

## Problem

`level_basis.rule_version` is `feat-strat-001.vN`. The code knows v3 and v4 as the pick rule
(`lib/strat_levels.py:1519-1529`, read) and treats everything else as older. Two approved changes add
versions: the prior-close print rule always takes v5
(`2026-11-16-feat-playbook-001-prior-close-prints-r2.md` on its branch, PC6, read) and the ATR quarter
targets take v6 (`2026-11-16-feat-strat-001-atr-quarter-targets-r2.md`, read). Whenever a reader runs
an image older than the writer, forward (a straggler) or backward (a rollback after newer rows
exist), it meets a version it does not know. What each reader does then, all run on 8250bff75 with one
stored basis whose `rule_version` alone was changed to v5, v6 and v99 (v4 as the control):

| Reader | Calls `from_basis`? | Today, for v5, v6, v99 (run) |
|---|---|---|
| `SessionLevels.from_basis` (`lib/strat_levels.py:1982-1983`) | is it | Rebuilds under the v2 rule and returns `rule_version` v2. On the d8 fixture the plan targets go from 275, 280, 285 to 253, 275, 280, the plan is gone, and the brief text's T1 goes from "275.00 (PMH), sell 1/3" to "253.00 (PDH)". |
| Resolver `plan_inputs` (`gcp/premarket_playbook_resolver.py:596-640`) | no | Does not downgrade. Returns `targets_unavailable` from the row's own columns. `resolve_one` then writes one UPDATE: `calls_plan_r` NULL, `calls_plan_r_status` `targets_unavailable`, the older leg columns from the stored t1 to t3, and `outcome_resolved_at`. The stamp takes the row out of `pending_dates` (`:890-909`, read), so an upgraded resolver never fills the plan unless forced. The control (v4) wrote `plan_r` 5.0171, `ok`. |
| Resolver `derive_level_map_from_daily` (`:209`), only for a row with no stored triggers | yes | Rebuilt as v2. The structured trigger and t1 to t3 it derives were equal to the v4 control on both fixtures (they are the gating targets, which the v2 rule also produces). No changed value was observed. |
| Insight planner `summarize_session_levels` (`lib/agents/summarizers.py:603`) | yes | Section `available` True; the `level_basis` it hands the planner and the report says v2 and has no plan (`plan_legs` None against 3). The long targets equal the control's on the QQQ fixture. |
| Signal monitor `refresh_level_map` (`gcp/signal_monitor.py:980`) | yes | Session levels relabelled v2, no plan (`plan_legs` None against 3). The long targets equal the control's on the QQQ fixture. |
| API `_build_movement_level_map` (`platform/api/routers/dashboard.py:459`) | yes | A level map with no plan on the trigger; trigger targets equal the control on the QQQ fixture. |
| Movement statement `_new_rule_mark` (`lib/movement_statement.py:505-518`) | no | Returns None, so the tracked rungs are seeded the pre-v3 way (from the row's price, exclusive) and not from the basis's cleared mark. The reach population binds the row's own version string (`:1049-1051`, read), so it counts only rows of that version. |
| `_assemble` (`lib/strat_levels.py:2448-2449`) | n/a | An in-memory v5 comes back labelled v4. Not reachable from a stored row today, because `from_basis` has already relabelled it. |
| Brief (`gcp/premarket_brief.py:1650`) | no | Builds fresh and stamps its own version. Its dry run reads one field of the live basis, `premarket.fetched_at` (`:1135-1136`, read). |
| `gcp/insight_discord_push.py:155-175`, `lib/agents/orchestrator.py:990` | no | Read keys of a report's own basis; no branch on the version (read). |

None of these raises, logs or marks anything. On `main` the same line knows only v3
(`lib/strat_levels.py:1968-1969` at 21e4de31d; run: v4 and v5 both come back v2), so the window exists
for PR #2010's own deploy and this change cannot close that one: a guard only protects images that
contain it. Today the only protection is deploy order (prior-close r2, Close-out step 1).

## Non-goals

- No change to any rule, to what v3 and v4 pick, or to how v1, v2 and a missing version are read.
- No new version. `LEVEL_RULE_VERSION` and `PICK_RULE_VERSIONS` are whatever the merge base holds.
- No schema change, no stored row rewritten, no deploy tooling that orders images.
- No protection for an image that predates this change (Design 4 says what such an image does).
- The brief does not check a row's version before a replay overwrites it (decision 5).

## Decisions for the owner (recommended pick first)

Owner, 2026-11-17: approved with every decision below taking its recommended pick (the first option listed).

1. **Refuse, do not mark.** Recommended: `from_basis` raises a named exception and each reader turns
   it into its own unavailable state. The alternative, returning a `SessionLevels` with a new
   `status`, is unsafe here: the resolver's derive path falls through to building from daily bars
   when `status != 'ok'` (`gcp/premarket_playbook_resolver.py:209-212`, read), which would write
   triggers built under the reader's own older rule, and every other caller would need the same new
   check with nothing to fail if one forgot it.
2. **An unreadable version is refused too.** Recommended: yes, as `rule_version_unreadable`. Today
   `''`, `'feat-strat-001.vX'` and the int 5 rebuild as v2 (run). Whether any stored row carries such
   a value was not checked (no production access); a read-only count before the build would say. If
   one exists it stops resolving until looked at, which is the point. Alternative: treat as legacy.
3. **The resolver exits non-zero on a refused row, including today's date.** Recommended.
   `classify_date_outcome` calls "nothing resolved today" `benign_pending` (run: 0 resolved, 3 skipped
   on today's date gives `benign_pending`), so without this the first night of a skew would exit 0.
4. **The insight run fails for the ticker; it does not publish an orb-only plan.** Recommended: the
   exception propagates as `LevelParamsUnavailable` does (`lib/agents/summarizers.py:2094-2098`,
   read). The alternative, a failed section with a reason, lets the planner run with no levels, and it
   then reports `orb_only` with reason `no_levels` (`lib/agents/trade_planner.py:104-106, 128-129`,
   read), which misstates a deploy skew as an absence of levels.
5. **Replay overwrite.** A replay by an older brief image writes a row under its own older version
   over a newer one. Recommended: leave it out of this change; replays are owner-run steps, and a
   guard there needs a read before every write. Recorded under Risks.
6. **Where this lands.** Recommended: its own small PR, after PR #2010 merges and before the
   prior-close build, deployed to every reader before the first v5 writer (Design 5).

## Approaches considered

- Keep deploy order as the only protection: free, and silent the first time it is missed.
- A status on `SessionLevels`: rejected, decision 1.
- A database constraint or a version table: a schema change for a check the code can make, and it
  cannot see which image is reading.
- One classifier in `lib/strat_levels.py`, one exception, each reader's own unavailable state: chosen.

## Design

### 1. The classifier (`lib/strat_levels.py`)

`rule_version_number(version)`: for a `str` that fully matches `feat-strat-001\.v([1-9][0-9]*)`
(`re.fullmatch`, ASCII digits, no leading zero, nothing before or after), the integer; else None.

`rule_version_status(version)` returns, first match:

1. `version is None` (key absent or JSON null): `legacy`.
2. no number: `rule_version_unreadable`.
3. `is_current_pick_rule(version)`: `known`.
4. number at or below 2: `legacy`.
5. number above the largest number in `PICK_RULE_VERSIONS`: `rule_version_newer`.
6. otherwise (a number between 2 and the newest that the list does not hold): `rule_version_unreadable`.

The newest known is derived from `PICK_RULE_VERSIONS`, so a build that adds a version changes nothing
here. No watched constant sits in a comparison, so the meta test of PR #2010 keeps its ALLOWED map.
Run on a scratch prototype of exactly this text: None, v1, v2 gave `legacy`; v3, v4 `known`; v5, v6,
v10 and a 20-digit number `rule_version_newer`; `''`, `.v0`, `.v05`, `.vX`, `.v`, a trailing space, a
leading space, a trailing newline, upper case, `feat-strat-002.v9`, an Arabic-Indic digit, `.v5.1`,
`.v-5`, `5`, `5.0`, `True`, a list and `'v5'` `rule_version_unreadable`.

### 2. The refusal

`class LevelRuleVersionUnknown(RuntimeError)` with `reason` (the status) and `recorded` (the stored
value). `SessionLevels.from_basis` raises it, after the dict check and before anything is built, for
`rule_version_newer` and `rule_version_unreadable`. `_assemble` raises it where it relabels today.
Legacy keeps today's path to the v2 rule. Run on the prototype (the `from_basis` part; the
`_assemble` part was not built): v5, `.vX` and `''` raised with the right reason and the stored value; v1 and a missing key rebuilt as v2 with the v2 targets; the meta
test, `tests/gcp/test_level_basis.py` and `tests/lib/test_strat_levels.py` passed (225 tests), and a
wider selection of tests/gcp, tests/lib, tests/agents and tests/api by keyword passed (1295, 18
skipped), so no existing fixture holds a value the guard refuses.

### 3. What each reader does (visible, nothing reinterpreted, nothing written)

| Reader | On a refused version |
|---|---|
| Resolver `resolve_one` | Checks the row's basis after the already-resolved test and before the derive, the bar read and `plan_inputs`. Returns `(None, status)`, logs at ERROR the ticker, date, stored version, status and newest known, writes nothing, so the row stays pending and resolves inside the 14-day lookback (`:998`, read) once the image knows the version. `derive_level_map_from_daily` lets the exception rise; `resolve_one` returns the same reason for it. `main()` counts refused rows and returns 1 when there is one (decision 3). With `PLAYBOOK_RESOLVE_FORCE` a resolved row is still refused and left as it is. The check covers an unreadable version as well as a newer one, and it is the only guard on a row whose trigger columns are populated: such a row never reaches `from_basis`, and `plan_inputs` returns `targets_unavailable` from the row's own columns for any version other than v2 and the current one (`gcp/premarket_playbook_resolver.py:625-629` on main at 3a59299ba). Run there: `''`, `'feat-strat-001.vX'` and the int 5 each gave `resolved` with one UPDATE, both plan sides `targets_unavailable` and `outcome_resolved_at` set (U4, U7b case 6). |
| Movement statement | `_fetch_tracked_levels` returns `_unavailable("<status>: ...", rule_version=..., rule_version_status=...)`. `assemble_movement_statement` then makes no reach-rate query and `_build_levels` returns UNAVAILABLE with that reason before it looks at the level map. The headline does not depend on levels and is unchanged. |
| API `_build_movement_level_map` | Catches the exception by name, logs at ERROR, returns None (its documented unavailable state). |
| Signal monitor `refresh_level_map` | Catches it by name beside the `LevelParamsUnavailable` branch (`:959-971`): counter `level_refresh_rule_version_unknown_count`, ERROR log with the status, level map None, session levels removed, so level breaks and the put re-anchor are skipped for the ticker (`:522-526`, read) and the session summary shows why. It does not build its own levels under its own rule. |
| Insight planner | The exception propagates out of `summarize_session_levels` and out of the section loop, as `LevelParamsUnavailable` does (decision 4): `build_context_bundle` re-raises it beside `LevelParamsUnavailable` (`lib/agents/summarizers.py:2094-2098` on main at 3a59299ba), ahead of its `except Exception` (`:2099-2103`), which would otherwise turn it into an unavailable section that `context_from_bundle` reads as no levels. Run there with a stand-in exception of the same base class: the bundle came back with `session_levels` unavailable, reason `exception: ...`, and no error. The ticker's run then fails in `gcp.insight_pipeline_job._run_one` and no report is written (U5). |
| Brief dry run `_premarket_from_bars` | Returns `(None, "... rule version unavailable: <stored> is <status> ... (kept)")`, the form of its other unavailable lines. The live brief and a replay build fresh and never read a stored basis, so they are unchanged. |

Run on the prototype (classifier, `from_basis` and the resolver check only): `resolve_one` on v5, v6
and v99, with force False on an unresolved row and force True on a resolved one, returned
`(None, 'rule_version_newer')` with 0 write statements and 1 read (the row); a v1 row and a row with no
version still resolved with `targets_unavailable` as today; the existing resolver suite passed (76
with the meta test). `main()`'s exit code and the other five reader changes were not built or run;
their rows above are the contract U4's second test, U5, U6 and U8 check.

### 4. Mixed rollout and rollback

One rule covers both directions: a reader compares the stored version with what its own image knows.

| Stored row | Reader's image | Result |
|---|---|---|
| known to it | any with this change | rebuilt as recorded (U3) |
| newer than it knows | has this change (straggler, or rolled back to an image at or after this change) | refused by name, nothing written; recovers when the image knows the version (U7) |
| newer than it knows | predates this change | today's behaviour, the Problem table. Not fixable from here. |
| older (v1, v2, none) | any | legacy path, unchanged |

Run on the prototype, with `PICK_RULE_VERSIONS` patched to v3 only and a real v4 basis: `from_basis`
raised `rule_version_newer`; `resolve_one` returned `(None, 'rule_version_newer')` with 0 write statements;
with the patch removed the same row resolved, `plan_r` 5.0171, `ok`. Rows a newer writer left behind
stay refused by a rolled-back resolver each night (exit 1) until it is rolled forward or they pass the
14-day lookback, after which `PLAYBOOK_RESOLVE_DATE` reaches them.

**Recovery goes through the scheduled run, and its limits are stated (U7b).** Read from
`gcp/premarket_playbook_resolver.py` on main: `pending_dates` (`:890-909`) selects only rows with
`outcome_resolved_at IS NULL` from the floor `today - lookback` (inclusive) to today; `main`
(`:994-1003`) uses that selection whenever `PLAYBOOK_RESOLVE_DATE` is unset, also when
`PLAYBOOK_RESOLVE_FORCE=true`, and returns 0 when it is empty; `resolve_one` (`:674-677`) skips a
stamped row unless forced. So:

- A row this change refuses is left unstamped, so a compatible image finds it on its next scheduled
  run without force while the row is inside the window.
- A refused row that ages out of the window stops alarming before anyone upgrades. Recovery is one
  run with `PLAYBOOK_RESOLVE_DATE` set to its date, with the routine lookback left as it is.
- A row that a reader older than this change already stamped `targets_unavailable` is never
  selected again by the scheduled run, and `PLAYBOOK_RESOLVE_FORCE=true` alone does not reach it.
  It needs `PLAYBOOK_RESOLVE_DATE` and `PLAYBOOK_RESOLVE_FORCE=true` together, run on a compatible
  image, as a repair the owner approves separately. This change performs no such repair and no
  historical rewrite.

### 5. Order relative to the prior-close and targets builds

Recommended: PR #2010 merges; this spec is approved and merges alone; its build merges and is
deployed to every job and service that reads a stored basis (resolver, API, signal monitor, insight
pipeline, brief); only then does the prior-close build deploy its v5 writer. Reasons:

- Before PR #2010 it would edit the lines that PR rewrites, and that PR is ready with auto-merge on.
- Folded into the prior-close build it protects nothing for v5: the image that first knows the guard
  would also know v5, and every older image would still be silent. It would also need a third
  revision of an approved spec; a spec cannot widen another approved spec's contract.
- It widens neither approved spec: prior-close PC6 still adds v5 to `PICK_RULE_VERSIONS`, the targets
  spec still adds v6 there, and neither touches the classifier.

If the prior-close build merges first, this change is unchanged in text (its tests build their
versions from `PICK_RULE_VERSIONS`) and protects from v6 on.

## Capacity

No job, query, API call or table is added. Volume: one string per stored basis read. Velocity: 0 added
round-trips; the refusing paths make fewer (the resolver skips its bar read, the movement statement its
two reach queries). Wall-clock: one regex match per rebuild, not measured, against jobs whose cost is
their queries. Cost: $0 per run. A refused resolver run exits 1 once a night per skewed date until the
image is updated; that is the alarm, not a retry loop (`--max-retries` was not read; see below).

## Close-out

Deploy every reader from `main` at or after the merge, before any writer of a newer version. No
schema, scheduler or data step. Do not roll a reader back past this change once newer rows exist.

## Risks

- **A reader left on an older image** is still silent. U-tests cannot see it; the deploy step can.
- **A real stored row with an unreadable version** would stop resolving (decision 2). Not counted.
- **Louder failures during a skew**: insight runs fail and the resolver exits 1 until the images
  agree. Intended; the alternative is the Problem table.
- **A replay by an older brief** overwrites a newer row under an older version (decision 5).
- **A legacy row misread as newer or the reverse**: U1 and U3 pin both directions.
- **A row an older reader already stamped** stays stamped `targets_unavailable` until the owner
  approves an explicit-date forced repair (Design 4). Nothing here finds or counts such rows.

## What was not verified

- Production: no row, image tag, deploy state or scheduler was read. Whether any stored
  `rule_version` falls outside v1 to v4 or missing is unknown.
- The five reader changes other than the resolver's were not prototyped; only today's behaviour of
  each was run.
- `tests/lib/test_movement_statement.py` was not run (the handoff says it needs `lightgbm` locally);
  `tests/lib/test_movement_statement_level_basis.py` was (9 passed).
- How `gcp/insight_pipeline_job.py` records a failed ticker, and the resolver job's `--max-retries`,
  were not read.
- The prior-close and targets specs were read on their branches, not built; no v5 or v6 basis
  written by real code exists to test against, so the newer versions in every test are stamped.
