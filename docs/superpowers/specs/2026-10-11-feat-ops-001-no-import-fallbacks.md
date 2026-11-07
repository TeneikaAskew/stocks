---
feat_id: FEAT-OPS-001
req_ids: [REQ-DATA-001, REQ-GOV-004]
issues: [1316, 928, 1335, 1047]
canvases: [https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN]
done_when:
  - "tests/meta/test_no_import_fallbacks.py::test_no_unlisted_import_fallbacks, run against origin/main's lib/, gcp/, platform/api/ and scripts/, fails listing exactly the 21 handlers in this spec's Sites removed table as path:line qualname, with no pin mismatch, and passes on the PR head"
  - "tests/meta/test_no_import_fallbacks.py keys ALLOWED, PART2 and KNOWN_BROAD by (path, qualified function name), each mapping to a reason and to the guards that function may hold, each guard pinned as its handler types, the modules its try body imports and the value it substitutes; ALLOWED's keys are exactly the 21 in this spec's Allowlist table, PART2's exactly the 24 keys (25 guards) in its Part 2 table and KNOWN_BROAD's exactly the 7 keys (14 guards) in its Broad guards table, and self-tests assert that the scan fails when a listed function holds a guard its entry does not pin or lacks one it pins: a one-for-one swap to another module, a new substitute for the same import, a widened handler type, a second guard, and a pinned guard that is gone"
  - "tests/meta/test_no_import_fallbacks.py runs its detector on inline snippets and asserts it refuses: except Exception, except BaseException and a bare except: around a try body of only imports, and around a body calling __import__ or importlib.import_module; except ImportError and except ModuleNotFoundError each alone, in a tuple, as an attribute and through a module-level alias tuple; a handler type it cannot resolve to a builtin exception around an imports-only body (a function-local alias, a class attribute, a concatenated tuple, an imported name); an imports-only body that also assigns constants (HAVE_YAML = True) under a broad or import handler; except* ImportError; with contextlib.suppress(ImportError) around an import; a conditional raise; a raise only inside a nested try or handler; a handler that returns, yields, continues or breaks before its final raise, including a return inside a nested try within the handler; a handler that calls sys.exit, os._exit or os.abort before its raise, also through import sys as s and from sys import exit as e; a raise of another type anywhere in the handler (RuntimeError, HTTPException, SystemExit, KeyboardInterrupt), including inside an if before a final bare raise and after marking a status; a handler that rebinds or deletes the name it bound; an except ImportError: raise placed after a sibling handler of the same try that catches Exception or everything and returns; an otherwise accepted handler whose try has a finally that returns; an otherwise accepted handler wrapped in the same function by an outer try whose first handler able to catch an ImportError returns or wraps it, or by a with contextlib.suppress(Exception); an outer or earlier sibling handler whose type it cannot resolve (a function-local alias) that returns; an outer handler of an imported type that re-raises, followed by except Exception: return []; a finally that raises another type; suppress imported under another name (from contextlib import suppress as quiet); and a module-level alias tuple bound with an annotation (_E: tuple = (ImportError, OSError)) around work. It accepts a handler that ends in a raise when every raise in it is a bare raise, a raise of the name it bound, or a raise of ImportError or ModuleNotFoundError, and no return, yield, continue, break or exit call appears in it outside nested function, lambda and class bodies, including an except ImportError: raise placed ahead of an outer except Exception"
  - "tests/meta/test_no_import_fallbacks.py pins the 14 broad import guards in this spec's Broad guards table in KNOWN_BROAD, and fails on any other bare except:, except Exception or except BaseException, written as the scan resolves it (a name or attribute, alone, in a tuple or through a module-level alias), whose try body is only imports, or imports beside constant assignments, or calls a function named __import__ or import_module"
  - "tests/lib/test_silent_fallback_fixes.py asserts pytest.raises(ImportError) for lib.strat_levels._trading_days_between(2026-10-05 23:00 UTC, 2026-10-08 13:30 UTC) with pandas_market_calendars blocked, so neither a returned count nor an error of another type passes"
  - "With the import made to fail (monkeypatch.setitem(sys.modules, 'gcp.database', None) unless this item names another), pytest.raises(ImportError) holds for: gcp.signal_monitor.SignalMonitor._persist_signal_alert and SignalMonitor._persist_exit in tests/gcp/test_signal_monitor_persist.py; lib.strategies.exit_config_overrides.get_disabled_directions in tests/lib/test_exit_config_overrides.py, whose autouse fixture clears the lru_cache; lib.strategies.brief_bias.get_premarket_bias, its cache cleared, in tests/gcp/test_signal_monitor_brief_bias.py; gcp.premarket_brief.load_earnings_for_brief, load_economic_events, _delete_null_close_rows, load_yesterday_amc_reactions, persist_to_cloud_sql and fetch_premarket_analysis_row, and _playability_lines both with lib.earnings_reactions blocked and with only DEFAULT_LOOKBACK_QUARTERS removed from it, in tests/gcp/test_premarket_brief.py; and lib.earnings_reactions.get_calibration_options_metrics, get_earnings_calibration (cache cleared), query_reaction_stats, query_typical_daily_return and query_conditional_reactions in tests/lib/test_lib_earnings_reactions.py"
  - "tests/api/test_admin_users_datasources.py asserts that GET /api/admin/strat-engine/state, under TestClient(..., raise_server_exceptions=False), answers 500 when google.cloud.storage cannot be imported (None in sys.modules and the storage attribute removed from google.cloud), 503 when storage.Client() raises google.auth.exceptions.DefaultCredentialsError, 500 when storage.Client() raises TypeError, and 200 with nine cells, none available, when the client works and no model.pkl exists; origin/main's code answers 200 with cells: [] to the first three"
  - "For each of the 14 rows of this spec's Caller catches table, a test makes that row's callee raise ModuleNotFoundError and asserts with pytest.raises(ImportError) that it propagates out of the function holding the catch; against origin/main's code each of the 14 fails, because the catch logs and carries on. The :1652 row has a second import test: with gcp.database.get_engine removed, ImportError leaves generate_premarket_brief. For the 9 rows marked pinned here, a second test makes the callee raise RuntimeError and asserts the row's handling today (its logged line, or the ticker's status and error, and the result it carries on with); each passes on origin/main and on the PR head, and fails when that row's new handler is widened to catch every exception"
  - "Tests drive each of the six job runs in this spec's Entry points table end to end, hermetically, with that row's import made to fail and its stubs: gcp.premarket_brief.main(['--no-discord']) with gcp.database blocked, the same with pandas_market_calendars blocked, gcp.premarket_brief.main(['--post-existing', 'SPY', '2026-10-08']), gcp.signal_monitor.main() in loop mode for one poll, gcp.refresh_earnings_views.main(['--mode', 'daily']) and gcp.insight_pipeline_job.main for one ticker. On the PR head each run raises ImportError, or exits 1 having logged it, and that ImportError's traceback passes through the function in the row's Reaches column; against origin/main's code no run produces such a traceback"
  - "Tests assert that GET /api/catalysts/events?refresh=true, GET /api/catalysts/ticker/{ticker} and POST /api/backtest/replay-trades answer 500 under TestClient(..., raise_server_exceptions=False) with the import in this spec's Entry points table made to fail, where origin/main's code answers 200"
  - "The PR body shows test_no_unlisted_import_fallbacks run against origin/main's code and FAILED naming the 21 removed handlers, and each test of items 5 to 10 that asserts the change's new behaviour run against origin/main's code and FAILED. The pins (item 7's 200 case, item 8's nine RuntimeError tests and tests/api/test_catalysts_news_filter.py's package-path test) are shown passing on both trees, and the detector self-tests and table checks of items 2 to 4 pass on any tree and are exempt. The Backtest Pipeline jobs Run Tests, Research Tests (heavy ML stack) and Integration Tests (ephemeral Postgres) are green on the PR head"
  - "git diff --numstat origin/main...HEAD -- tests/ shows 0 deleted lines in every existing test file except tests/api/test_route_coverage.py, whose one deleted line is its GET /api/admin/strat-engine/state expectation of 200, now 503"
  - "The PR body links a new issue that lists: the 14 broad import guards, lib/gamma.py:722, lib/infra_errors.py:196, :200, :204, :208, :212, :216, :220 and :643, platform/api/routers/catalysts.py:347 (:339 on the PR head), platform/api/routers/dashboard.py:47 and :55, scripts/backfill_watchlist_data.py:85 and :189, each with the value its handler substitutes; the 25 handlers of this spec's Part 2 table; the 21 Allowlist keys with their reasons, naming platform/api/main.py:346's misattributed cause; and the two broad handlers that still swallow the database layer's own ImportError, gcp/database.py:239-241 (query_to_dataframe) and lib/strategies/brief_bias.py:93-96, with the outcomes this spec's Risks lists. Lines are at 17bbacd3 unless marked. It also references #1274 for the MARKET_HOLIDAYS_2026 = set() fallback at platform/api/routers/dashboard.py:40-59 and #1047 for the two swallowing handlers"
  - "The PR is opened after stocks#1383 is merged into main, and carries the inventory blocks of docs/product/infrastructure/05-a-ARCHITECTURE.md, 05-c-DATA_DEPENDENCIES.md and 05-e-API.md exactly as python -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --insert, given those three paths, renders them on the PR head, with no other line of those documents changed; tests/scripts/test_check_generated_docs.py passes on the PR head"
  - "Every pointer in docs/models/MODEL-*.md into a file this change edits, path:line, symbol-anchored, and bare :N whose file the same table row, sentence or paragraph names, names the same statement on the PR head as on origin/main. The PR body shows the check that maps each pointer's origin/main line to the head through the diff and compares the statement: it reports 0 stale pointers on the PR head, and run against the documents as they stand on origin/main it reports the stale ones. tests/meta/test_model_registry_consistency.py passes on the PR head"
  - "Each of the 12 fallbacks listed in this spec's AUDIT markers table carries an AUDIT-2026-05-13 comment, as the first line of its handler's body or, for the inline fallback, on the line above it, naming what it substitutes"
  - "The PR body carries this spec's Product documents table: for each line of docs/product/03-SITE-TRACEABILITY.md, docs/product/07-MODEL-REGISTRY.md and solyra docs/UI-SCREENS.md that the change makes false, the sentence as it stands, its replacement and the branch that corrects it, and the counts, measured on the PR head, of the citations into the changed files that the change moves in each document; the PR itself corrects only 07-MODEL-REGISTRY.md:490, the one moved line the gate lets it change, with docs/product/generated/model-registry.json regenerated"
  - "The FEAT-OPS-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists the PR under FEAT-OPS-001"
status: approved
supersedes: null
---

# Fail loud when a required import is missing: the ratchet, the signal and brief paths, and the API

## Why this re-cut

This spec re-cuts stocks#1386 (head `ace5427e`, the same repository path), which was approved and never merged.
Codex's first review of stocks#1386 found four problems. An independent pre-review of the first draft of this
re-cut then found 1 P1, 4 P2 and 8 P3 more, and a second pre-review, of the draft that fixed those, found 3 P2 and
8 P3, and a third, of that draft, found 3 P2 and 7 P3. Each was checked against stocks main `17bbacd3`, and the
code under this spec is unchanged at `d0231901`, origin/main when this revision was cut (Bases).

### Codex's review of stocks#1386

1. **The route's documents (P2).** The change turns `GET /api/admin/strat-engine/state` from a 200 with no cells
   into an error, and `docs/product/03-SITE-TRACEABILITY.md` says the route swallows storage failures and is
   pinned at 200. The gate refuses that file on this branch. Answered by the Product documents table and done_when
   item 17 (ruling in Product documents).
2. **A wrapped import error (P2).** stocks#1386 let `_trading_days_between` end in
   `raise RuntimeError(...) from exc`. Executed with that variant and `pandas_market_calendars` blocked,
   `gcp.premarket_brief.main(['--no-discord'])` returned normally with every ticker marked `PLAYBOOK_FAILED`: the
   new `except ImportError` at `gcp/premarket_brief.py:1652` cannot see a `RuntimeError`, so the broad handler
   under it swallowed it. Every removed handler now lets the ImportError itself propagate. Item 5 asserts
   `ImportError` alone, item 9 drives the brief with the calendar library blocked, and the ratchet refuses a
   wrapper.
3. **The allowlist keys (P2).** A listed function could drop its justified handler and add a different silent one
   with the same count. Executed: swapping `lib/options_greeks.py:186`'s `gcp.database` guard for a `scipy.stats`
   guard that returns `(0.045, 0.0)` left stocks#1386's ratchet passing, 55 of 55. Each table entry now pins its
   guards, and the same edit fails the scan.
4. **500 for a defect (P1).** stocks#1386's `except Exception` around `storage.Client()` answered 503 for a
   `TypeError` too. The handler now asks `lib.infra_errors.is_infrastructure_error`, as every other admin handler
   does, and re-raises what it does not classify.
   - Codex also put the import failure among the 503s. This spec does not: `lib/infra_errors.py:58-64` leaves
     `ImportError` out of the outages, and `OPTIONAL_DEPENDENCIES` (`:143-144`) does not name
     `google.cloud.storage`.
   - Executed: `is_infrastructure_error` is False for `ModuleNotFoundError(name='google.cloud.storage')` and for
     `TypeError`, and True for `DefaultCredentialsError`.

### The pre-review of the first draft

- **P1, the generated documents.** The change moves lines that the inventory blocks of `05-a-ARCHITECTURE.md`,
  `05-c-DATA_DEPENDENCIES.md` and `05-e-API.md` cite, and lines that `docs/models/` cites. Three existing tests
  then fail in the lean Run Tests job:
  - `tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate`;
  - `test_a_model_edited_block_is_restored_from_the_fresh_render_by_name`;
  - `tests/meta/test_model_registry_consistency.py::test_symbol_anchored_line_pointers_resolve`.

  REQ-GOV-004 says the PR carries the re-rendered blocks, and main's gate refuses that until stocks#1383 merges.
  So the PR opens after stocks#1383 is on main and carries the re-render (item 14). It also re-points the model
  documents' pointers, which sit outside `docs/product/` (item 15). Generated and model documents explains both.
- **P2, the acceptance rule.** The ratchet still accepted a wrapper or `raise SystemExit` inside an `if` before
  the final raise, `sys.exit` through an alias, a rebound caught name, and an `except ImportError: raise` behind
  a broad sibling handler. Each is refused now, with a self-test per shape (item 3).
- **P2, the non-import handling.** Item 8 passed a catch that re-raises every exception, and seven catches had no
  test of the Non-goal that a database or vendor failure keeps today's handling. Item 8 now pins those seven.
- **P2, item 11.** Item 11 asked every test of items 5 to 10 to fail on main, but item 7's 200 case is a pin that
  passes there. Item 11 now names the pins and shows them passing on both trees.
- **P2, Product documents.** The table missed 03 `:1162`, six solyra ranges and solyra's prose citations into the
  changed files. All are added, with measured counts.
- **P3, smaller fixes.**
  - `issues` names stocks#1316 and stocks#928.
  - The allowlist reason for `gcp/insight_tasks.py:148` names its three callers.
  - The replay harness's per-bar catch is in the caller trace.
  - The ratchet treats an unresolvable handler type and the `HAVE_X = True` idiom as guards.
  - The eleven broad handlers this change edits beside carry `AUDIT-2026-05-13` markers (item 16).
  - The anchor counts and the broken-implementation claims are worded as measured.
  - Part 2 is named as a draft.
  - The plan's test count, `## Capacity` heading and tick evidence now match what the gate accepts.

### The second pre-review

- **P2, the playbook catches.** `gcp/premarket_brief.py:1652` and `:1680` had no non-import pin: no existing test
  runs `generate_premarket_brief`, so a new handler widened to `except Exception` turned a per-ticker database or
  build failure into a dead brief and passed every item. Item 8 now pins nine rows, these two included, and the
  Non-goals sentence that said existing tests pinned them is corrected. Each new pin fails when its handler is
  widened (executed).
- **P2, the model pointers.** About 25 pointers in `docs/models/` still named another statement on the scratch
  head, bare `:N` pointers and two explicit ones (`MODEL-BRIEF-001.md:109`, `MODEL-MR-001.md:93`), and
  `test_model_registry_consistency.py` cannot see them (3-line slack, bounds-only, no gate on bare ranges). Item 15
  now covers bare pointers whose file the row, sentence or paragraph names, and asks for a statement check that
  can fail. Measured with that check: 31 stale on the old head, 0 now.
- **P2, the database layer's own ImportError.** Risks named one benign path. With the Cloud SQL connector missing,
  `query_to_dataframe` (`gcp/database.py:239-241`) and the brief-bias query (`lib/strategies/brief_bias.py:93-96`)
  swallow `gcp/database.py:191`'s ImportError under most of this spec's sites. Risks now says what runs, and item
  13's issue lists both handlers. No code change here: the swallowing is pre-existing and stocks#1047 tracks it.
- **P3, smaller fixes.**
  - Product documents adds 03 `:798`, solyra `:9838` and `07-MODEL-REGISTRY.md`'s moved citations, each with the
    branch the gate lets correct it, and scopes the stocks#1372 sentence.
  - `canvases` names the backend architecture canvas, which maps to FEAT-OPS-001 in `canvases.yml`.
  - `issues` adds stocks#1335 and stocks#1047.
  - Capacity states the insight job's retry on the failure path, with its cost.
  - The ratchet closes four gaps (an unresolvable outer or sibling type, a finally that raises another type,
    `suppress` imported under another name, an annotated alias), each with a self-test that failed first.
  - The `platform/api/main.py:346` reason quotes the page in full and says why it stays.
  - `_playability_lines`' `or 0` fallbacks beside the edited imports get a marker (item 16 now counts 12).
  - Line numbers name their commit: `catalysts.py:339` on the head, `spec_gate.py` after stocks#1383, solyra main
    `5fbdbb9`.

### The third pre-review

- **P2.** The enclosing-swallow rule stopped at the first handler able to catch; it now reads every handler in
  order (item 3). The `:1652` handler order is required at run time, not neutral, and item 8 tests it. The
  Capacity text failed main's gate; it now gives a figure first in each value.
- **P3.** Item 4 is narrowed to what the scan resolves, and Risks names what it cannot see. The AUDIT markers
  table and the "left as they are" list say what they cover. The base, moved lines and audit counts are at
  `d0231901`. Four small statements are corrected (Entry points, Caller catches, Capacity, the plan).

## Bases

`17bbacd3` is the commit every code line in this spec was read on. origin/main is `d0231901` when this revision
was cut, and `git diff 17bbacd3 d0231901 -- lib gcp platform scripts tests docs/models docs/product/03-SITE-TRACEABILITY.md docs/product/07-MODEL-REGISTRY.md docs/product/infrastructure`
is empty, so every line still holds there. Where a document outside those paths moved, the line given is at
`d0231901`.

## Problem

`lib/strat_levels.py:1722-1728`, `_trading_days_between`, catches `ImportError` for `pandas_market_calendars`
and returns `int(calendar_days / 1.4)`. The count is too low, so it switches off the staleness guard it feeds.
Run on 2026-10-11 with the library blocked:

- a source bar from Monday 23:00 UTC, read on Thursday 13:30, counts 1 trading day against a threshold of 2,
  and the stale row is written;
- with the library, it counts 3 and raises `StaleSourceDataError`.

Four tests in `tests/lib/test_strat_levels_freshness.py` fail in any environment without the library. Six more
pass only because the approximation lands on the right side of the threshold.

An audit on 2026-10-11 covered every `except ImportError` and `except ModuleNotFoundError` handler under
`lib/`, `gcp/`, `platform/api/` and `scripts/`:

- It found 69 handlers. Those directories and `tests/` are unchanged from the audit's snapshot `2a108675` to
  `17bbacd3`, which is origin/main on 2026-10-12.
- Each substitute value was reproduced by calling the function with the import blocked.
- 38 handlers return a value a caller cannot tell from a real result.

Two more join those 38:

- the `strat_levels` handler above;
- `platform/api/routers/admin.py:486`, which the audit left UNSURE and the Design settles.

Review found six more among the 29 the audit had accepted:

- **Three Yahoo handlers.** `gcp/fetchers/fetch_earnings_history.py:119`, and
  `scripts/fetch_earnings_calendar.py:833` and `:1082`.
  - `yfinance` is declared for the image that runs them: `requirements-gcp.txt:18`, with
    `requirements-gcp.lock:223` pinning 1.2.0, which `gcp/Dockerfile:12-16` installs.
  - So their empty DataFrame reads as "Yahoo reported nothing" when the image is broken.
- **Three internal-module guards on production paths.**
  - `lib/strategies/brief_bias.py:69` returns `bias='UNAVAILABLE'`. The signal monitor then scores the bar with
    `ftfc_score = 0.0` (`gcp/signal_monitor.py:1297`), so the FTFC penalty is silently off.
  - `gcp/premarket_brief.py:3474` makes the `/replay` cache-hit job report "no row" for what is an import
    failure.
  - `gcp/indicator_correlation_job.py:507` makes the deployed job (`gcp/deploy.sh:809`) skip its signal target
    and exit 0.

That makes 46.

Removing a handler is not enough when its caller catches `Exception`, because the import error lands one level
up and is swallowed again. For example, `load_earnings_for_brief` logs "playability enrichment skipped" and goes
on (`gcp/premarket_brief.py:605`). The Design traces every caller.

The 46 handlers are split across two specs, by the entry points they reach:

- **This spec (part 1)** covers the decision paths. It:
  - removes 21 handlers on the signal-monitor, kill-switch, brief-bias, premarket-brief, earnings-reaction,
    strat-levels, admin and catalysts paths;
  - fixes the 14 caller catches above them;
  - lands the ratchet.
- **Part 2** covers the ingestion and analytics jobs and removes the other 25 handlers. It is a draft, not yet on
  any branch; its repository path will be
  `docs/superpowers/specs/2026-10-11-feat-ops-001-no-import-fallbacks-jobs.md`. Until it is approved and lands,
  the ratchet lists its handlers in `PART2`, and the issue done_when item 13 files tracks them.

Seven of this spec's handlers change an alert, a recommendation or a risk control:

- `gcp/signal_monitor.py:1650` and `:2403` (`SignalMonitor._persist_signal_alert` and
  `SignalMonitor._persist_exit`) return silently after the Discord alert has gone out, so the fire or the exit
  never reaches `signal_alerts`.
- `lib/strategies/exit_config_overrides.py:108` (`_latest_overrides`) reads as "no row". Then
  `get_disabled_directions` returns an empty set, and the direction kill switch fails open. Executed on
  2026-10-11: with `gcp.database` unimportable, `lib.signals.evaluate_signal(row, min_conditions=3,
  ticker="QQQ")` fires a PUT. stocks#928 tracks the wider resolver contract; this spec closes only the import
  path.
- `lib/strategies/brief_bias.py:69` turns the FTFC penalty off, as above.
- `gcp/premarket_brief.py:326` and `:894` make the brief say "No earnings scheduled" and "No major events
  today", and the ORB window recommendation follows from the empty list.
- `lib/earnings_reactions.py:425` silently turns the calibration override off.

## Non-goals

- **The 14 broad import guards.** These are import guards caught by a bare or broad `except` (Broad guards
  table), such as `platform/api/routers/dashboard.py:40-59`, which sets `MARKET_HOLIDAYS_2026 = set()`. This
  change does not fix them. The ratchet pins them so no new one lands, and the PR files an issue listing them.
- **The other broad handlers.** Their try body does work besides a static import, a dynamic import call
  (`__import__`, `import_module`) or a constant assignment. That is the general §3.7 data-access shape, not an
  import guard. Those this change edits beside get an `AUDIT-2026-05-13` marker (AUDIT markers table).
  - Two near the admin change keep their handling, both lines of stocks#1316 and stocks#1335: the per-cell
    reads in `_strat_engine_state_cells` (`platform/api/routers/admin.py:516-522`, `:567-568`), where any storage
    error marks a cell unavailable and which get markers, and `_load_structure_brief_snapshot` (`:262-283`),
    which answers `None` for any error, a missing `google.cloud.storage` included, and which this change does not
    edit.
  - So this change settles the client half of stocks#1316, and the PR says on that issue what remains.
- **Handlers the audit accepted, beyond the six above.** The audit classed 29 handlers as acceptable, and the
  six above leave. Of the other 23:
  - Two end in a raise that keeps the import error and need no entry: `lib/features/fracdiff.py:172` and
    `gcp/database.py:191`.
  - Two end in a raise of another type and are allowlisted with their callers traced:
    `gcp/research/magnitude_engine/evaluation_windows.py:160` and `platform/api/routers/health.py:134`.
  - The other 19 are allowlisted too.

  Every allowlist entry has a reason with evidence for why it is not a production path that must fail loud
  (Allowlist table).
- **Failures other than an import error.** Each caller-catch fix re-raises `ImportError` alone. A database or
  vendor failure at the same catch keeps today's handling. Item 8 pins that at the nine catches no existing test
  covers, the two playbook catches `gcp/premarket_brief.py:1652` and `:1680` among them: the `PLAYBOOK_FAILED`
  tests call `persist_to_cloud_sql` with built dicts and never reach either catch. Existing tests pin it at the
  other five, each failing when its catch is widened (the second pre-review, executed):
  - `lib/signals.py:316` (`test_resolver_failure_fails_closed`);
  - `gcp/signal_monitor.py:1155` (the `kill_switch_failure_count` tests) and `:2052`
    (`test_resolve_brief_bias_handles_lookup_exception`);
  - `lib/agents/orchestrator.py:592` (`test_pipeline_marks_persona_plans_when_the_deterministic_plan_fails`);
  - `gcp/premarket_brief.py:2419` (`test_empty_dict_still_propagates_after_failure`).
- **Behaviour in a healthy image.** With the import present, every code path runs the same statements as
  today, with one exception. In `platform/api/routers/admin.py:494`, `storage.Client()` fails although the
  package is installed. Today that answers 200 with `cells: []`. After this change it answers 503 when
  `is_infrastructure_error` calls the failure an outage, and 500 otherwise (Design, admin section).

## Approaches considered

1. **Fix `strat_levels` alone.** Rejected: the same defect is in 45 more places, and the review guideline this
   repository adopts says a class is fixed once, with each location.
2. **Install the missing libraries everywhere.** Rejected: the images already have them. The defect is what
   happens when an import fails, not which image runs.
3. **Make `scripts/audit_silent_fallbacks.py`, the existing tested handler scanner, the gate.** Rejected:
   - it is an inventory that exits 0 by design; its docstring says that failing CI on 255 known sites would
     teach people to skip it;
   - it keys on the substituted value, not on the guarded import.

   The ratchet reuses its `_handler_returns` for the failure lines. It does not reuse its `_own_nodes` for the
   acceptance rule, which must see inside nested handlers.
4. **Remove all 46 handlers and the caller catches above them in one change.** Rejected for size: more than 20
   entry points need an end-to-end test, which is more than one plan of about 15 tasks.
5. **Keep every cited line in place**, so no generated or model document needs re-rendering. Rejected:
   `gcp/premarket_brief.py` alone loses lines above dozens of cited lines, and padding the files to hold line
   numbers would itself be a change no reviewer could check.
6. **Chosen: split by caller closure, and open the PR after stocks#1383.** Each spec removes a set of handlers,
   fixes every catch above them, and drives every entry point they reach. The ratchet lands with part 1 and holds
   part 2's handlers in `PART2`, and the PR carries the re-rendered blocks under REQ-GOV-004.

Chosen on 2026-10-11 under the owner's instruction to bring both repositories to a clean, closed-out state. The
four failing tests surfaced it. Codex's reviews of stocks#1379 and stocks#1386, and the pre-review of this
re-cut, shaped the split, the ratchet's rules, the admin statuses and the documents the PR carries.

## Design

### The fix, per handler

Each of the 21 handlers in the Sites removed table loses its substitute, and no handler takes its place: the
ImportError itself propagates. They guard either an internal module (`gcp.*`, `lib.*`, `scripts.*`) or a package
every image that runs them installs:

- `pandas_market_calendars` in the jobs image, through `requirements-gcp.lock`;
- `google-cloud-storage` in both images.

A lazy import stays lazy, inside its function; it is simply not caught. The handler is deleted, except where
noted:

- `gcp/premarket_brief.py:2351` and `:2366` lose their stub copies of `lib.earnings_reactions` helpers and import
  them.
- `platform/api/routers/catalysts.py`, `_fetch_live_events`, keeps
  `from scripts.fetch_catalyst_calendar import ...`.
  - That import resolves because `catalysts.py:32` puts the repository root on `sys.path`, and the API image
    copies `scripts/` to `/app/scripts`.
  - The function drops the second-chance `sys.path` import at `:146-147` with both handlers.
- `platform/api/routers/admin.py`: see the next section.

A wrapper is not allowed at any of these sites. `raise RuntimeError(...) from exc` at `_trading_days_between`
reaches `gcp/premarket_brief.py:1652`, whose new `except ImportError` handler cannot see it, so the broad handler
beneath marks the ticker and the run goes on (executed).

### admin.py

`_strat_engine_state_cells` changes in two places:

- **The import.** The `ImportError` handler at `:486` goes. `from google.cloud import storage as _gcs` stays
  as the function's first import, uncaught.
- **The client.** The `storage.Client()` handler at `:494` takes the shape every other admin handler uses
  (`:147-153`, `:659-668`). When `is_infrastructure_error(exc)` is true, it logs at ERROR and raises
  `HTTPException(status_code=503, detail="strat-engine state temporarily unavailable") from exc`. Otherwise it
  logs with `logger.exception` and re-raises.

So `GET /api/admin/strat-engine/state` answers:

- 503 for an outage the classifier names (`DefaultCredentialsError`, a refused connection);
- 500 for a defect (`TypeError`, `AttributeError`);
- 500 for a missing `google.cloud.storage`, which the classifier reads as a defect, not an optional package.

A client that works and a cell with no `model.pkl` still answer 200 with nine cells, none available. The three
swallowed reads after the client (`:497-504`, `:516-522`, `:567-568`) stay and get `AUDIT-2026-05-13` markers.

Solyra's Model State card (`ModelStateSnapshot.tsx:29-35`; `useAdmin.ts:179` throws on a non-ok status) then
shows "Model state unavailable: state 503" or "state 500". Today it shows "0 / 0 models trained".

Fixing `:486` alone would fix a dead branch: `platform/Dockerfile` installs `google-cloud-storage`. `:494` is the
reachable twin, returning the same `cells: []` with HTTP 200, so this is the one change in a healthy image (see
Non-goals).

`tests/api/test_route_coverage.py:339` declares 200 for this request. Its harness makes `storage.Client` raise
`_BackendDown`, a `ConnectionError` (`tests/api/test_route_coverage.py:446`), which the classifier calls an
outage. So that 200 is the swallow, and it becomes 503, as `/api/admin/routes` did ("was a bare 500"). The new
tests go in `tests/api/test_admin_users_datasources.py`, which runs in the lean Run Tests job.

Blocking the import takes two steps, because `from google.cloud import storage` reads the `storage` attribute of
`google.cloud` when it is set. `None` in `sys.modules` alone left the import working; deleting the attribute as
well raised `ModuleNotFoundError`.

Executed on scratch copies of `17bbacd3`, with and without `google-cloud-storage` installed:

- The four new assertions:
  - on origin/main, the three error cases fail with 200 and the no-model case passes;
  - on the change, all four pass;
  - on stocks#1386's implementation, the import case and the defect case fail, with 503.
- The route sweep, with `google-cloud-storage` and `aiohttp` installed:
  - with the change and the old line 339, 1 failed and 121 passed. The failure is "GET
    /api/admin/strat-engine/state answered 503, the table says 200";
  - with 503 on that line, it and the admin test file give 152 passed, the four new tests included.
- `scripts/export_openapi.py --check` reports `openapi.json` up to date.

### Caller catches

Every production caller of each removed function was traced up to its entry point, a job `main` or an API route.
The trace was executed on 2026-10-11: a call graph over `lib/`, `gcp/`, `platform/api/` and `scripts/`, resolved
through each file's imports, plus the instance callers of `BacktestEngine.run`.

The 14 catches below catch `Exception` and carry on, so each would swallow the error this spec stops
substituting.

- **The default fix.** Each gets `except ImportError: raise` immediately ahead of its broad handler.
  `ModuleNotFoundError` is a subclass. A database or vendor failure at the same catch keeps today's handling.
  Item 8's second tests pin that at the nine rows marked pinned.
- **Two exceptions.** At `gcp/premarket_brief.py:1652` and `:1680`, the new handler sets
  `d['status'] = 'PLAYBOOK_FAILED'` and `d['playbook_error']` and then ends in a bare `raise`. The existing
  structural test
  `tests/lib/test_silent_fallback_fixes.py::test_a_strat_levels_persist_failure_marks_the_ticker` (`:1015`)
  requires every handler on a `try` around `persist_level_map` to set the status, and a bare re-raise alone
  fails it (executed).
  - At `:1652` the new handler is the try's first, ahead of `except StaleSourceDataError` (`:1643`), and the
    order is required. The try imports `get_engine` from `gcp.database` before it imports
    `StaleSourceDataError`, so when that first import fails, evaluating `except StaleSourceDataError` raises
    `UnboundLocalError`, which the playbook block's broad handler swallows. Item 8's second import test removes
    `gcp.database.get_engine`: it passes with this order and fails with the two handlers swapped and on
    origin/main (executed). The ratchet refuses the swapped order too (executed:
    `gcp/premarket_brief.py:1652 generate_premarket_brief substitutes raise`).
  - Their pins drive `generate_premarket_brief` with one ticker failing and assert that ticker's status and
    error and that the other tickers carry on. At `:1652`, `persist_level_map` raises `RuntimeError` for SPY and
    the error reads "strat_levels persist failed: RuntimeError: ..."; widened, the outer handler writes a
    different error. At `:1680`, `build_level_map` raises for SPY; widened, the brief raises.
- **Every one of these handlers ends in a bare `raise`**, which the ratchet accepts (executed).

| Catch | In | Callee that now raises | What the catch does today | Non-import pin |
|---|---|---|---|---|
| `gcp/premarket_brief.py:605` | `load_earnings_for_brief` | `enrich_with_playability`, reaching `query_reaction_stats` (`:523`), `query_typical_daily_return` (`:582`), `get_earnings_calibration` (`:101`) | WARNING "playability enrichment skipped"; rows go unscored | pinned (item 8) |
| `gcp/premarket_brief.py:635` | `load_earnings_for_brief` | `get_earnings_calibration` (`:101`) | WARNING; `min_nq = 12` | pinned (item 8) |
| `gcp/premarket_brief.py:882` | `load_yesterday_amc_reactions` | `conditional_lean_summary`, reaching `query_conditional_reactions` (`:682`) | WARNING; the lean is omitted | pinned (item 8) |
| `gcp/premarket_brief.py:1350` | `generate_premarket_brief` | `load_yesterday_amc_reactions` (`:809`) | WARNING; the AMC section is omitted | pinned (item 8) |
| `gcp/premarket_brief.py:1652` | `generate_premarket_brief` | `persist_level_map`, reaching `_trading_days_between` (`strat_levels.py:1724`) | ticker marked `PLAYBOOK_FAILED`; the run continues | pinned (item 8) |
| `gcp/premarket_brief.py:1680` | `generate_premarket_brief` | the playbook block holding `:1652`, once that re-raises | ticker marked `PLAYBOOK_FAILED`; the run continues | pinned (item 8) |
| `gcp/premarket_brief.py:2419` | `_build_earnings_embed` | `get_calibration_options_metrics` (`:425`) | `logger.exception`; `_BRIEF_CAL_OPTS = {}`, so the Q5 override is off | existing test |
| `lib/signals.py:316` | `evaluate_signal` | `_latest_overrides` (`exit_config_overrides.py:108`), `get_disabled_directions` | logged; no signal this bar (fail closed); the poll continues | existing test |
| `gcp/signal_monitor.py:1155` | `SignalMonitor._evaluate_strategies_for_bar` | `get_disabled_directions`, reaching `_latest_overrides` | counted and logged; `(None, None)` | existing tests |
| `gcp/signal_monitor.py:2052` | `SignalMonitor._resolve_brief_bias` | `get_premarket_bias` (`brief_bias.py:69`) | DEBUG log; `bias='UNAVAILABLE'`, so `ftfc_score = 0.0` (`:1297`) | existing test |
| `gcp/signal_monitor.py:695` | `SignalMonitor._update_leg_trackers` | `_resolve_brief_bias` (`:610`), once `:2052` re-raises | WARNING "leg-state update skipped"; the poll continues | pinned (item 8) |
| `lib/agents/trade_planner.py:835` | `context_from_bundle` | `get_blue_sky_atr_offset`, reaching `_latest_overrides` through `_latest_overrides_or_default` | `blue_sky_offset = None` (default offset) | pinned (item 8) |
| `lib/agents/orchestrator.py:592` | `run_insight_pipeline` | `context_from_bundle`, once `:835` re-raises | `persona_plans = []`, recorded in `failed_sections` | existing test |
| `scripts/generate_historical_report.py:125` | `_generate_one` | `run_insight_pipeline`, once `:592` re-raises | logged; the manual CLI exits 0 (no job or workflow runs it) | pinned (item 8) |

These callers were traced and stay unchanged. Each was read on `17bbacd3`:

- **The signal monitor's loop.** `SignalMonitor.run_loop` (`gcp/signal_monitor.py:2467-2513`) has no catch, and
  neither has the call to `evaluate_signal` (`:1107`) nor the one to `_evaluate_strategies_for_bar` (`:1252`).
  So an import error that leaves any of the monitor's catches ends the run.
- **The monitor's replay mode.** `gcp.signal_monitor.main` with `REPLAY_DATE` (`:2610-2662`) runs
  `scripts/replay_signal_monitor.py`. Its `replay_ticker` catches `Exception` around `evaluate_ticker` per bar
  (`:209`), logs a WARNING and goes on. That catch cannot see this spec's import errors alone:
  - replay `main` imports `gcp.database.get_engine` before any bar (`:762`), and `signal_monitor.main` imports
    `is_cloud_sql_configured` at `:2624`;
  - every guard this spec removes on that path imports `get_engine` from `gcp.database`.

  So an unimportable `gcp.database` ends the replay before the loop.
- **The insight job.** `gcp/insight_pipeline_job.py:543` records the run as `failed`, with the error
  (`_transition`). A single-ticker execution then exits 1 (`:745`).
- **The insights routes.** `platform/api/routers/insights.py:484` records the run as `failed` with the error,
  shown at `GET /api/insights/runs/{run_id}`. `:909` wraps a function that already catches.
- **The live signals route.** `generate_signals` (`lib/signals.py:358`) has no ticker parameter, so
  `platform/api/routers/live.py:657` and `scripts/run_historical_signals.py:378` never read the override store.
- **The backtest engine.** `BacktestEngine.run` sets `_current_ticker` to its `ticker` argument
  (`lib/backtest.py:475`), and no caller passes one (for example `lib/walk_forward.py:358`,
  `scripts/run_backtest.py:218`), so it is `None` there. Only `replay_labeled_trades` sets a ticker
  (`lib/backtest.py:1223`), and its route has no catch.
- **The override defaults.** `_latest_overrides_or_default` (`exit_config_overrides.py:164-169`) catches only
  `OverridesUnavailable`.
- **The cache-hit job.** `render_existing_brief_to_discord` calls `fetch_premarket_analysis_row`
  (`premarket_brief.py:3512`) outside any try.

### AUDIT markers

CLAUDE.md §3.7 asks for an `AUDIT-2026-05-13` marker on a silent fallback beside a touched line. The table marks
the broad handlers whose own try statement this change edits, or whose handler sits next to an edited line, and
one inline fallback; it does not mark swallows a few lines from an edited handler, such as
`gcp/premarket_brief.py:266` and `lib/earnings_reactions.py:107` and `:431`. Each marked handler keeps substituting
for non-import failures. The twelfth is not a handler: a few lines below the imports this change edits in `_playability_lines`
(`gcp/premarket_brief.py:2349-2367`), `or 0` and `.get(..., 0)` at `:2372-2375` print a missing value as
"gap 0.0% · cons dir 0% · rev 0%". stocks#1047 already tracks that site.

Each handler gets a comment as the first line of its body, and the inline fallback a comment on the line above
it, in the shape of the existing markers (`lib/data_loader.py:660`): the marker tag, then what is substituted and
when it is reached (item 16).

| File | Handler | What it substitutes |
|---|---|---|
| `gcp/premarket_brief.py` | `:605` | rows left unscored (no playability) |
| `gcp/premarket_brief.py` | `:635` | `min_nq = 12`, unannounced |
| `gcp/premarket_brief.py` | `:882` | the lean omitted for every reporter |
| `gcp/premarket_brief.py` | `:1350` | the AMC-reaction section dropped |
| `gcp/premarket_brief.py` | `:2419` | `_BRIEF_CAL_OPTS = {}`, so the Q5 IC override is off |
| `gcp/signal_monitor.py` | `:2052` | bias `UNAVAILABLE`, so `ftfc_score = 0.0` |
| `gcp/signal_monitor.py` | `:695` | the leg-state update skipped for any failure, not only a bad batch |
| `lib/agents/trade_planner.py` | `:835` | the default blue-sky offset |
| `platform/api/routers/admin.py` | `:497-504` | no live ECE for any cell |
| `platform/api/routers/admin.py` | `:516-522` | a cell unavailable on any read error |
| `platform/api/routers/admin.py` | `:567-568` | a cell's version and date from `model.pkl` alone |
| `gcp/premarket_brief.py` | `_playability_lines`, `:2372-2375` | a missing move magnitude, direction consistency, reversal rate or quarter count printed as 0 |

### The ratchet (`tests/meta/test_no_import_fallbacks.py`)

The test parses every `.py` under `lib/`, `gcp/`, `platform/api/` and `scripts/` with `ast`. An imports-only
body below is one of import statements, beside which it may only assign constants (`HAVE_YAML = True`). The test
checks three kinds of guard:

1. **Kind 1:** a handler, in `try` or `try*`, whose type names `ImportError` or `ModuleNotFoundError`. The type
   may be a `Name` or an `Attribute`, alone or in a tuple, or a module-level name bound to such a name or tuple
   (`_E = (ImportError, OSError)`, annotated or not).
   - A handler around an imports-only body counts as kind 1 too when its type does not resolve to builtin
     exception names. That covers a function-local alias, a class attribute, a concatenated tuple and an imported
     name, which may catch an `ImportError` the scan cannot see.
2. **Kind 2:** a bare `except:`, or one whose type includes `Exception` or `BaseException` (resolved the same
   way), when the try body it guards is imports-only or calls `__import__` or `import_module`.
3. **Kind 3:** a `with` whose context is a `suppress(...)` call naming `ImportError` or `ModuleNotFoundError`, or
   naming `Exception` or `BaseException` around a body of the kind-2 shape. `suppress` is also found under the
   name `from contextlib import suppress as quiet` gives it. A kind 3 guard is never accepted.

**When a guard is accepted.** A handler is accepted when all of these hold:

- **It keeps the import error on every path.** It ends in a `raise`, and every `raise` in it is one of:
  - a bare `raise`;
  - a `raise` of the name it bound;
  - a `raise` of `ImportError` or `ModuleNotFoundError`, with or without `from`.

  A raise of any other type, anywhere in the handler, is refused: `RuntimeError`, `HTTPException`,
  `SystemExit`, `KeyboardInterrupt`, inside an `if` or not. A wrapper is a different exception to every caller,
  and a caller's `except ImportError: raise` cannot see it. The bound name may not be rebound or deleted, so
  `raise e` is the error caught.
- **No early exit inside it.** No `return`, `yield`, `yield from`, `continue` or `break` appears in its body.
  There is also no call to `sys.exit`, `os._exit`, `os.abort`, `exit` or `quit`, under the names the file's
  imports give them (`import sys as s`, `from sys import exit as bye`, `from os import _exit`).
  - The walk skips the bodies of nested functions, lambdas and classes.
  - It descends into nested `try` bodies, handlers and `finally` blocks, so it does not reuse `_own_nodes`,
    which skips nested `except` bodies.
- **No exit from its own `finally`.** Its own try's `finally` holds no such early exit, and no raise other than a
  bare one or one of an import type, which would replace the error.
- **No earlier sibling takes the error.** No earlier handler of the same `try` can catch an `ImportError` while
  failing these same tests. A handler can catch one when its types include an import type, `Exception` or
  `BaseException`, when it is bare, or when its types do not all resolve to builtin exception names (a local or
  imported alias, an imported exception class). `except Exception: return []` followed by
  `except ImportError: raise` is refused: Python picks the first.
- **No enclosing swallow.** In the same function:
  - no handler of an enclosing `try` that is able to catch an `ImportError` (as above) fails these same tests,
    reading its handlers in order and stopping at the first that certainly catches one (an import type,
    `Exception`, `BaseException` or bare);
  - no enclosing `try` has a `finally` with an early exit or a raise of another type;
  - no enclosing `with` suppresses `ImportError`, `Exception` or `BaseException`.

On `17bbacd3` the rule accepts two handlers, `lib/features/fracdiff.py:172` and `gcp/database.py:191`. It finds
no kind-3 guard, no aliased or unresolvable type, and no constant-assigning imports-only body (executed: the
tightened rule finds the same 81 guards as the first draft's).

**The tables.** A guard that is not accepted passes only if its (path, qualified function name) key is in one of
three dicts:

- `ALLOWED` (kind 1) holds the 21 Allowlist keys.
- `PART2` (kind 1) holds the 24 keys (25 guards) of the Part 2 table. Each reason cites the issue done_when
  item 13 files, and part 2 deletes the dict.
- `KNOWN_BROAD` (kinds 2 and 3) holds the 7 keys (14 guards) of the Broad guards table. Each reason cites the
  same issue.

`<module>` stands for module-level code, and `Class.method` for methods.

**The pins.** Each dict entry maps the key to a reason and to the guards that function may hold. Each guard is
pinned as:

- its handler types, sorted;
- the modules its try body imports:
  - `import a.b` gives `a.b`;
  - `from .x import y` gives `.x`;
  - `__import__` or `import_module` gives its first argument when that is a string, else `<dynamic>`;
- the value it substitutes, as the failure line prints it.

The scan fails when the guards a listed function holds differ from its pins. That covers:

- a one-for-one swap to another module;
- a new substitute for the same import;
- a widened handler type;
- a second guard;
- a pinned guard that is gone.

The pins are generated from a scan of origin/main and checked against this spec's tables. The Guards column of
the Allowlist and Part 2 tables, and the Guards and Substitutes columns of Broad guards, are those pins.

**How it fails.** The test fails listing every unlisted guard as `path:line qualname substitutes <value>`. The
value is the one `_handler_returns` names, else the first line of the handler's last statement (for a kind 3
guard, the `with` line).

- `_handler_returns` comes from `scripts/audit_silent_fallbacks.py`, loaded with `importlib` as `_scanner()` in
  `tests/lib/test_silent_fallback_fixes.py` does. It names nothing for 8 of the 21 removed handlers.
- A pin mismatch fails as `path qualname: found <guards>; listed <guards>`.

Executed on 2026-10-12:

- **On `d0231901`** (the code of `17bbacd3`), a draft of exactly this rule, with these tables:
  - passes its 93 self-tests (61 refused shapes, 19 accepted, 13 table and helper tests);
  - fails the class test listing the 21 handlers in the Sites removed table and no other, with no pin
    mismatch;
  - finds 67 kind-1 guards unaccepted (21 + 21 + 25) and 14 of kind 2.
- **On a scratch tree holding this spec's changes,** it passes 94 of 94. It accepts the 14 new caller-catch
  handlers and finds 46 kind-1 guards (21 + 25) and 14 of kind 2.
- **The second pre-review's four gaps:** its five probes were accepted by the r3b rule; each now has a self-test,
  and the five failed against the r3b rule (`5 failed, 88 passed`) before the detector changed. On `17bbacd3` the
  tightened rule finds the same 81 guards. On the scratch tree it first refused the `:1652` re-raise behind
  `except StaleSourceDataError`; that handler comes first, which the run time needs as well (Caller catches).
- **The third pre-review's outer-walk probe** (an outer `except StaleSourceDataError: raise` of an imported type,
  then `except Exception: return []`) was accepted by the r3c rule; its self-test failed (`1 failed, 93 passed`)
  before the walk read every handler. Rerun with Python 3.12 on `d0231901`: main `1 failed, 93 passed`, listing the
  same 21 handlers; the change `94 passed`.
- **The pre-review's ten probe shapes:** the first draft's rule accepted six of them. This rule refuses the nine
  that lose the error. It accepts the tenth, a raise inside a loop whose `else` returns, as it should.
- **On the swap of Codex's finding 3,** applied to the scratch tree, the scan fails with the single line
  `lib/options_greeks.py get_rate_and_yield: found except ImportError around scipy.stats -> return (0.045, 0.0);
  listed except ImportError around gcp.database -> return _fallback_or_raise(f'gcp.database unavailable ({exc})')`.

### The behaviour tests

- **Helpers (done_when items 5 and 6).** Each test blocks the import and asserts `pytest.raises(ImportError)` in
  the test file of the module's own area.
  - `monkeypatch.setitem(sys.modules, 'gcp.database', None)` reaches every `from gcp.database import X`, even
    after `gcp.database` is imported.
  - `_playability_lines:2366` is reached only when `:2351` imports, so its test removes just
    `DEFAULT_LOOKBACK_QUARTERS` from `lib.earnings_reactions`, and `from ... import` then raises.
  - Three of the functions are cached. `_latest_overrides` is `@lru_cache(maxsize=64)`
    (`exit_config_overrides.py:86`), `get_earnings_calibration` is `@lru_cache(maxsize=1)`
    (`earnings_reactions.py:84`), and `get_premarket_bias` is `@lru_cache(maxsize=128)` (`brief_bias.py:45`).
    After an earlier call each returns its cached value instead of raising, so each test clears the cache.
- **Catches (done_when item 8).** Each row's first test makes its callee raise `ModuleNotFoundError`, and asserts
  that it leaves the function holding the catch. Each pinned row's second test makes the callee raise
  `RuntimeError` and asserts the logged line and the carried-on result: the scored rows, `min_nq` defaulting,
  the reactions without a lean, the brief without its AMC section, `None` from `_update_leg_trackers`, a `None`
  offset, and no upsert. The two playbook pins assert the failing ticker's status and error, and the other
  tickers' run (Caller catches).
- **Entry points (done_when items 7, 9 and 10).** Each row drives its entry point as the row says. In every test
  above, the module under test is imported before the import is blocked.

Each behaviour item fails against a named broken implementation. Executed on 2026-10-12 on scratch copies of
`17bbacd3`, except where marked:

- **origin/main's code,** with every handler in place and every catch unfixed, fails each test of items 5, 6,
  9 and 10, item 8's first tests, and item 7's three error cases. The pins item 11 names pass there.
- **An unfixed catch** fails its item 8 first test. Those tests stub the callee, so they are indifferent to the
  handler.
- **A catch that re-raises every exception** fails item 8's seven second tests (7 failed), and widening the new
  `:1652` or `:1680` handler to `except Exception` fails its playbook pin (1 failed each).
- **The `:1652` handlers swapped** (`except StaleSourceDataError` first) fail item 8's `get_engine` test (1 failed;
  origin/main fails it too).
- **`raise RuntimeError(...) from exc` at `_trading_days_between`** fails item 5 and item 9's calendar row (2
  failed).
- **stocks#1386's admin shape,** `except Exception` answering 503 at the client and a 503 for the import, fails
  item 7's defect and import cases (2 failed).
- **A 503 for an import error at a route** fails item 10, whose tests assert `== 500` (not executed; it follows
  from the assertion).

### Entry points

Each job and route that one of this spec's handlers reaches is driven end to end, with sockets refused and the
stubs its row names.

Some modules import `gcp.database` unguarded at module scope or in `main` (`gcp/signal_monitor.py:2624`,
`gcp/refresh_earnings_views.py:46`), and blocking the whole module fails those rows on both trees. So those rows
remove the one name only the removed site imports, or block the module after import.

A row passes only when the `ImportError` traceback passes through the function in its Reaches column. Every row
was executed on `17bbacd3` and on a scratch copy of it holding this spec's changes.

| Entry point | Reaches | Import made to fail; stubs | origin/main | PR head |
|---|---|---|---|---|
| `gcp.premarket_brief.main(['--no-discord'])`, job premarket-brief | `load_earnings_for_brief` | `gcp.database` blocked after import; `BRIEF_AS_OF` a weekday; `DataLoader.load_daily` returns a fixture with a `Time` column | returns normally | `ModuleNotFoundError` through `load_earnings_for_brief` |
| `gcp.premarket_brief.main(['--no-discord'])`, the calendar library missing | `_trading_days_between` | `pandas_market_calendars` blocked; `gcp.database.get_engine` returns a fake engine; the same fixture | returns normally (a `RuntimeError` wrapper there also returns normally, every ticker `PLAYBOOK_FAILED`) | `ModuleNotFoundError` through `_trading_days_between` |
| `gcp.premarket_brief.main(['--post-existing', 'SPY', '2026-10-08'])`, the `/replay` cache-hit job | `fetch_premarket_analysis_row` | `gcp.database` blocked after import; `DISCORD_WEBHOOK_URL` set | `SystemExit(1)` after logging "no row" | `ModuleNotFoundError` through `fetch_premarket_analysis_row` |
| `gcp.signal_monitor.main()` in loop mode, one poll, job signal-monitor | `_persist_signal_alert` | `gcp.database.upsert_dataframe` removed and `is_cloud_sql_configured` true; `ALPHA_VANTAGE_API_KEY` set; watchlist `['SPY']`; a fixture bar window for the fetch and the indicators; the ORB, exit and level-map steps stubbed; the strategy step returns a CALL fire, and `fire_alert` runs | the poll completes; the fire is never persisted | `ImportError` through `_persist_signal_alert` |
| `gcp.refresh_earnings_views.main(['--mode', 'daily'])`, job refresh-earnings-views | `get_calibration_options_metrics` | `gcp.database` blocked after import; module-level `is_cloud_sql_configured` true, and `query_to_dataframe`, `execute_sql` and `upsert_dataframe` stubbed with one upcoming reporter | returns 0 (returns 1 without the `is_cloud_sql_configured` stub, on both trees) | `ModuleNotFoundError` through `get_calibration_options_metrics` |
| `gcp.insight_pipeline_job.main([])` with `INSIGHT_RUN_ID` and `INSIGHT_TICKER` set, job insight-pipeline | `_latest_overrides`, through `context_from_bundle` | `gcp.database.get_engine` removed; the pipeline runs with the agent fakes of `tests/agents/test_agent_orchestrator.py`; the run-status and report writes stubbed | returns 0, run `running` then `done` | returns 1, run `running` then `failed`, the logged traceback through `context_from_bundle` |
| `GET /api/admin/strat-engine/state` | `_strat_engine_state_cells` | `google.cloud.storage` blocked; or `Client()` raising `DefaultCredentialsError`; or `Client()` raising `TypeError` | 200 with `cells: []` for each | 500; 503; 500 |
| `GET /api/catalysts/events?refresh=true`, `GET /api/catalysts/ticker/{ticker}` | `_fetch_live_events` | `BENZINGA_API_KEY` set; `scripts.fetch_catalyst_calendar` and `fetch_catalyst_calendar` blocked; a cached event file | 200; the events route labels its cache "Benzinga" | 500 |
| `POST /api/backtest/replay-trades` | `_latest_overrides`, through `get_call_target` (`lib/backtest.py:855`) | `gcp.database` blocked; journal query and bar loader stubbed as `tests/lib/test_replay_labeled_trades.py` does; `TestClient(app, raise_server_exceptions=False)` | 200 | 500 |

Three groups of catches have no entry-point row: the kill-switch catches (`lib/signals.py:316`,
`gcp/signal_monitor.py:1155`), the brief-bias catches (`gcp/signal_monitor.py:2052`, `:695`), and
`scripts/generate_historical_report.py:125`, a manual CLI no job or workflow runs. Done_when items 6 and 8 pin
them instead. For the first two groups, both imports they guard are `from gcp.database import get_engine, ...`, and a
monitor run cannot isolate them. Executed on both trees:

- with `get_engine` removed, a poll already raises earlier, at the unguarded import in
  `lib/strategies/calibration.py:71`;
- with all of `gcp.database` blocked, `main` raises at `:2624`.

### Generated and model documents

**The generated documents (REQ-GOV-004).** The inventory blocks of `docs/product/infrastructure/05-a-ARCHITECTURE.md`,
`05-c-DATA_DEPENDENCIES.md` and `05-e-API.md` cite lines in 8 of the 12 changed source files. REQ-GOV-004
(`docs/product/01-PRODUCT-REQUIREMENTS.md:31`) says they SHALL equal a fresh render on main, and that a PR which
changes what they cite SHALL carry the re-rendered blocks. `tests/scripts/test_check_generated_docs.py` enforces
the render in the lean Run Tests job.

Main's gate refuses those documents on a feature branch. stocks#1383 lets a feature branch change exactly the
blocks when main's renderer reproduces them from the PR's committed blobs. On 2026-10-12 it is open as a draft,
unmerged, and its body holds it there on its own stop condition: its `registry` CI job measured 284 s of a pinned
300 s limit, and it waits on the owner's decision about the suite's CI time. So:

- the implementation PR opens only after stocks#1383 is merged into main (item 14). If stocks#1383 changes
  shape, this item follows what it merges as;
- the plan's re-render task, after the last code change, runs `python -m scripts.maintenance.doc_inventory --snapshot
  tests/fixtures/live_gcp_snapshot_2026-09-07.json --insert` with the three documents' paths, as the monthly
  refresh workflow does (`refresh-architecture-docs.yml:491`), and commits the result. Run with no paths, it
  renders only 05-a and 05-c (executed);
- the documents' prose outside the blocks holds no citation the change moves. Executed: 2 citations into the
  changed files, in 05-a, neither moved. stocks#1372 covers the prose of these three documents.

Executed on the scratch implementation of `17bbacd3` with the markers in:

- **Before the re-render,** the two docs-test files gave 3 failed and 205 passed, the three tests named in Why
  this re-cut. Main gave 208 passed.
- **The render** updated all three documents, 52 rows, every changed line inside a block (05-a 13, 05-c 26,
  05-e 13). A second run reported all three unchanged.
- **After it,** the same files gave 208 passed.
- **The gate of stocks#1383.** The second pre-review committed the r3b change onto a scratch clone at stocks#1383's
  head `f552ec59` and ran its `check_product_scope("FEAT-OPS-001", ...)`: `[]`. Rerun on a commit of this change
  in a separate clone: see Product documents.

**The model documents.** `docs/models/` lies outside `docs/product/`, so the gate lets this PR change it. Every
pointer in `docs/models/MODEL-*.md` into a changed file is re-pointed to the same statement (item 15): `path:line`,
symbol-anchored (`` `sym` (`:N`) ``) and bare `:N` whose file the same row, sentence or paragraph names.

`tests/meta/test_model_registry_consistency.py` cannot hold that. Its symbol check allows 3 lines of slack, its
explicit-path check is bounds-only, and its docstring counts 93 bare ranges it cannot gate. So item 15 asks for a
statement check, in the PR body:

- every explicit pointer resolves by its path, or a base name unique in the repository;
- every bare pointer the change could move is resolved to its file by reading, in a list the plan keeps beside
  the check. 119 candidates were read for the 12 changed files (each bare `:N` in a document that names a changed
  file, and that would move if it pointed there): 35 resolve into a changed file, and the rest name other files,
  such as `gcp/refresh_earnings_views.py`, `gcp/earnings_reactions_brief.py`, `lib/strategies/calibration.py` and
  `scripts/backtest_playability.py`;
- each pointer's origin/main line is mapped to the head through the diff, and the check compares the statement
  the head pointer names with the one origin/main's names.

Executed on 2026-10-12, 70 pointers (35 explicit, 35 bare):

- the documents as they stand on origin/main, against the changed code: 59 stale;
- the first draft's re-pointed documents: 31 stale, among them `MODEL-BRIEF-001.md:109` and `MODEL-MR-001.md:93`;
- this change's documents: 0 stale. They differ from origin/main on 55 lines in 9 documents, 87 numbers counting
  range ends, none inside a changed hunk;
- `tests/meta/test_model_registry_consistency.py`: 68 passed on the head; before any re-pointing it failed
  `test_symbol_anchored_line_pointers_resolve` on `MODEL-BRIEF-001.md:104`.

### Product documents

This change makes some lines of three documents false: `docs/product/03-SITE-TRACEABILITY.md`, solyra's
`docs/UI-SCREENS.md` and `docs/product/07-MODEL-REGISTRY.md`. The product-delivery gate refuses the first on this
branch, and solyra runs its own gate. In 07 the gate lets this branch change only lines that name a model this
spec names (`check_registry_rows`): of the 11 lines whose citations move, only `:490` (MODEL-MR-001) is one.

**Ruling.** This PR corrects 07 `:490` and regenerates `docs/product/generated/model-registry.json`, whose
`--check` fails otherwise (executed). Every other line below is corrected, and 03 is re-stamped, on the
close-out's after-merge `docs/` branch, the one step `SKILL.md` places after the merge (Phase 5 step 7): stocks'
for 03 and 07, solyra's for UI-SCREENS. That branch is cut from main, not from this branch, so nothing stacks.
done_when cannot hold the edit itself, because CI requires every box ticked before the merge. So item 17 puts this
table in the PR body, where review sees the replacement text before the merge.

The ruling rests on these runs:

- **The gate, against an edit of `:1120`.** On `feature/feat-ops-001-no-import-fallbacks`, `check_product_scope`
  answered "docs/product/03-SITE-TRACEABILITY.md changes in this feature change; under docs/product/ only the
  FEAT's own catalog and traceability records, the model registry and its generated files may change here". On
  `docs/ops-001-admin-state-traceability` it answered no errors.
- **stocks#1383's gate, on this change.** In a separate clone, the change was committed over a scratch commit of
  this spec and plan on stocks#1383's head `f552ec59`. Its `check_product_scope("FEAT-OPS-001", ...)` returned
  `[]` (121.6 s; the re-rendered blocks, `docs/models/`, 07 `:490` and the registry JSON included), and
  `check_registry_rows` returned `[]`. With 07 `:299` also re-pointed, `check_registry_rows` answered
  "docs/product/07-MODEL-REGISTRY.md: changes '`get_call_rsi_range` / ...', a line naming none of
  docs/superpowers/specs/2026-10-11-feat-ops-001-no-import-fallbacks.md's models".
- **The docs audit, on a commit of this change over `d0231901`** in a separate clone, with the re-rendered
  blocks, the model pointers, 07 `:490` and the markers in. `scripts/maintenance/docs_audit.py --json
  --no-owning-job-check` reported 280 findings against 279 on `d0231901` (executed on 2026-10-12). The one finding the
  base does not have is `changed-since` on `docs/product/03-SITE-TRACEABILITY.md`; it lost nothing. SKILL Phase 5
  step 5 asks that the branch report no finding that main does not. This one is the exception stocks#1383's body
  records the same way: the audit counts every commit since 03's stamp (`303b66a3`) by ancestry, a feature branch
  may not edit 03, and the after-merge re-stamp clears it. The PR body says so.
- **Solyra.** It runs its own gate. Its lines are corrected on a solyra `docs/` branch at the same step.

| Document and line | Says now | Becomes |
|---|---|---|
| 03 `:1120`, ADMIN-03 Backend | `_strat_engine_state_cells` reads each cell "with every storage error swallowed" | a storage client the classifier calls an outage answers 503, a client defect or a missing `google.cloud.storage` answers 500, and a cell whose `model.pkl` cannot be read reads unavailable |
| 03 `:1120`, ADMIN-03 Tests | `test_route_coverage.py` pins `GET /api/admin/strat-engine/state` "at 200 with the storage client failing" | at 503 with the storage client failing; plus the four `test_admin_users_datasources.py` state tests (500, 503, 500, and 200 with nine unavailable cells) |
| 03 `:1127`, ADMIN-10 | "an empty `cells` list when the storage client fails, admin.py:486-495"; the solyra card's `0 / 0 models trained` on an empty list; the sweep "at 200 with the storage client failing, which is the swallowed read" | nine unavailable cells when no model is served; the route no longer answers an empty list, so `0 / 0 models trained` is unreachable from it; the sweep pins the 503 |
| 03 `:1128`, ADMIN-11 | `admin.py:342` and `admin.py:577` "both swallow a storage error into a 200 answer, so the page's error branches for them fire on a 401, a 403 or an unhandled 500" | `:342` still swallows; the state route answers 503 for a storage outage and 500 for a defect, so `Model state unavailable:` shows its status |
| 03 `:1143`, Admin Gaps | "A storage outage reads as an empty shelf", with the probe's `{"cells": [], "ece_ceiling": 0.05}` | a failed client is a 503 or 500; a denied or failing read of each cell still reads `no artifact` (stocks#1316, stocks#1335) |
| 03 `:1158`, Admin Backend notes | "No `AUDIT-2026-05-13` marker sits in `platform/api/routers/admin.py` ..., though `_load_structure_brief_snapshot` and `_strat_engine_state_cells` swallow storage errors" | three `AUDIT-2026-05-13` markers sit in `admin.py`, on the state's three reads after the client, which still swallow storage errors; `_load_structure_brief_snapshot` swallows them with no marker |
| 03 `:1162`, the rows left unticked | for ADMIN-03, "a storage outage read as `0 / 0 models trained`" | a storage outage reads as the panel's error line with its status |
| 03 `:798`, Insights backend notes | "`AUDIT-2026-05-13` markers on this page's paths: `lib/agents/summarizers.py:285` ..., `lib/agents/trade_planner.py:874` (`or 0.0` on `atr`) and `:906` (`or 0.0` on `ftfc_score`)" | adds `lib/agents/trade_planner.py:838` (`context_from_bundle`, the default blue-sky offset), and the other two move to `:877` and `:909` (head lines) |
| 03 `:755`, INSIGHTS row | `persona_plans` is recorded "when the planner raises" | when the planner raises anything but an `ImportError`, which fails the run (`insight_runs` `failed`) |
| 03, every citation into the changed files | measured on the scratch implementation: 353 citations (each link's `file:line` text and `#L` anchor, and bare `file:line` prose), 254 moved and 6 inside a changed hunk, on 53 lines (`:131` to `:1280`); of them the `../../<path>#L<n>` anchors are 134, 95 moved, 2 inside a hunk and 37 unchanged | each re-pointed to the same statement on the merged code |
| solyra `docs/UI-SCREENS.md:9838`, Insights | "`persona_plans` when the deterministic planner raised (`:592-604`)" | when the planner raised anything but an `ImportError`, which fails the run; the range moves to `:594-606`, with the new `except ImportError` at `:592-593` (head lines) |
| solyra `:11406`, Admin purpose | "a storage outage reads as an empty shelf" | a storage outage of the state's client reads as the panel's error line; a failed read of a cell still reads as `no artifact` |
| solyra `:11425` | "a storage outage reads as no cells" | a storage outage answers 503 and the panel shows `Model state unavailable:` |
| solyra `:11455`, ADMIN-10 | "`0 / 0 models trained` in the state, which is also how a storage outage reads" | that empty state no longer comes from this route; an outage is ADMIN-11's error line |
| solyra `:11684-11685` | "a state answer with no cells reads `0 / 0 models trained` ..., which is how a storage outage reaches the page" | an outage reaches the page as `Model state unavailable: state 503` |
| solyra `:11697-11698` | "Given the brief and state routes with the storage client failing, then each answers 200 and the page shows an unavailable brief and an empty state" | the brief answers 200 with unavailable cells; the state answers 503 and the panel shows its error line |
| solyra `:11705-11706` | the sweep pins "the brief and state routes at 200 with the storage client failing, which is the swallowed read" | the brief at 200 and the state at 503 |
| solyra `:12156-12159` | "That is how a storage outage reaches the page: `_strat_engine_state_cells` returns no cells when the storage client cannot be built (`admin.py:486-495`, executed: 200 ...)" | the empty-answer reading stays for an empty answer; a client that cannot be built answers 503 or 500; the per-cell clause stays |
| solyra `:12166-12167` | "a storage outage reads as an empty shelf" | a storage outage of the client reads as an error; a failed read of a cell still reads as `no artifact` |
| solyra `:12176-12177` | "Given the storage client failing, then the brief and the state routes answer 200 ... and the page reads as above" | the brief answers 200; the state answers 503, and the panel shows its error line |
| solyra `:12179-12180` | stocks' sweep "pins ... `GET /api/admin/strat-engine/state` at 200 with the storage client failing, which is the swallowed read" | pins it at 503 |
| 07 `:490`, DOC-23 (MODEL-MR-001) | `gcp/signal_monitor.py:1107`, `lib/signals.py:311-344` | `:1110` and `:311-346`, in this PR, with the registry JSON regenerated |
| 07, the other moved lines (`:299`, `:371`, `:489`, `:505`, `:506`, `:517`, `:518`, `:522`, `:579`, `:581`) | 27 citations into the changed files on 11 lines, 16 moved, none inside a changed hunk (`:490` included) | each re-pointed on the stocks `docs/` branch; the gate refuses them here, as above |
| solyra, every stocks citation into the changed files | measured on the scratch implementation: 141 citations (`admin.py:1391`-style text and stocks blob links), 85 moved and 2 inside a changed hunk, on 45 lines | each re-pointed on the same solyra `docs/` branch |

Line numbers are 03 and 07 at `17bbacd3`, and solyra `docs/UI-SCREENS.md` at solyra main `5fbdbb9`, which changed
only that file's line-11 stamp since `3492237`. Counts are re-measured on the PR head (item 17).

**Checked and left as they are, among others:**

- **The catalysts rows** (`:336`, `:339`, `:830` to `:841`) describe the deployed service, which sets no
  `BENZINGA_API_KEY`, so `_fetch_live_events` returns before its import there. Their claims stay true; only their
  citations move (counted above).
- **The route table of `docs/product/04-BACKEND-API.md`** states no status and cites no line.
- **The model documents' claims.** `docs/models/MODEL-MR-001.md`, `MODEL-BRIEF-001.md`, `MODEL-EWV-001.md` and
  `MODEL-CALIB-001.md` describe no import fallback; their line pointers are item 15's.
- **Dated and frozen records.** The audit, plan and replay records under `docs/audits/`, `docs/audit/`,
  `docs/plans/` and `docs/replays/`, and the hand-maintained snapshots
  `docs/product/infrastructure/manual/05-a-ARCHITECTURE.md` and `manual/05-c-DATA_DEPENDENCIES.md` ("frozen as of
  that date", 2026-09-08), describe the code as it was then. Their citations are not re-pointed.
- **Citations already stale on main.** `CLAUDE.md:488` (`gcp/premarket_brief.py:617`),
  `docs/STRAT_METHODOLOGY.md:419` and `:425`, `docs/premarket_brief_cards.md:20` and
  `.claude/commands/resolve-issue.md:3742` and `:3779` (lines at `d0231901`) name other statements than the ones
  they describe (read). Re-pointing them through the diff would keep them wrong, so they are left.

### Environment

The four `test_strat_levels_freshness.py` failures came from this sandbox lacking the library, which CI installs
(`requirements.txt:90`). Executed with the library blocked:

- origin/main gives 4 failed and 9 passed;
- with the handler removed, 10 failed and 3 passed, all 10 with `ModuleNotFoundError` instead of a wrong count;
- with the library installed, both give 13 passed.

The full suite stalls in `tests/lib/test_combo_mining.py` when two runs share the machine's threads. It finishes
with `OMP_NUM_THREADS=1`, which the plan sets.

Capacity: with the import present, no job reads or writes more rows, makes more calls or runs longer, because each
function runs the same statements (CLAUDE.md rule 0.2). One job does more on the failure path, in a broken image
only. insight-pipeline runs with `--max-retries 1` (`gcp/deploy.sh:617`; the live job reads `1`, and
premarket-brief, refresh-earnings-views and signal-monitor read `0`, executed on 2026-10-12). Every LLM call in
`run_insight_pipeline` (`lib/agents/orchestrator.py:322-519`) comes before the plan step (`:590`), so a
single-ticker execution that now exits 1 is run once more in full: one extra pipeline per failing ticker per
execution. Measured on 2026-10-12 over the last 30 days (`insight_reports_history`, 114 reports; `insight_runs`,
127 runs on 22 days):

- Volume: 0 more rows; a failed run writes no report.
- Velocity: 2x the LLM calls for each failing ticker.
- Wall-clock: 1 more task, p50 31.5 s and p90 67.5 s, against the 1800 s task timeout.
- $/run x runs/day x 30: $0.011 x 4.2 x 30, about $1.40 of LLM for an image left broken for 30 days. $0.011 is
  the p90 of the per-pipeline LLM cost ($0.0106 mean, $0.0117 max), and 4.2 is 127 runs over 30 days; at the 5.8
  a day of the 22 days that had runs, $1.90 is an upper bound. Each extra task adds about $0.002 of Cloud Run at
  list prices for 2 vCPU and 8 GiB over 31.5 s (list prices, not checked against the bill). Today the same image
  returns 0 and writes a report without persona plans.

The retry policy is the job's own and is not changed here. Rule 0.3's evidence beyond the hermetic tests is
done_when item 9: each job's own `main` driven end to end.

### Sites removed (21 handlers in 19 functions)

Lines in this table and the three below are at `17bbacd3`; the ratchet pins functions and guards, not lines.
Severity is the audit's:

- H changes an alert, a recommendation or a risk control;
- M is a silent job no-op or a hidden section;
- L is wasted work, a hidden cause, or a branch dead in a healthy image.

| Path | Function | Lines | Handlers | Reason (what it substitutes today) |
|---|---|---|---|---|
| `lib/strat_levels.py` | `_trading_days_between` | 1724 | 1 | known case: calendar days / 1.4 undercounts, so the staleness guard passes a stale row |
| `gcp/premarket_brief.py` | `_delete_null_close_rows` | 251 | 1 | L: `0`; cleanup skipped, no log |
| `gcp/premarket_brief.py` | `load_earnings_for_brief` | 326 | 1 | H: empty earnings; the brief says "No earnings scheduled" |
| `gcp/premarket_brief.py` | `load_yesterday_amc_reactions` | 809 | 1 | M: `[]`; the AMC-reaction section is omitted |
| `gcp/premarket_brief.py` | `load_economic_events` | 894 | 1 | H: empty events; "No major events today" and a 5m ORB window |
| `gcp/premarket_brief.py` | `_playability_lines` | 2351, 2366 | 2 | L: stub copies of `lib.earnings_reactions` helpers (blank hint, fixed 12Q lookback) |
| `gcp/premarket_brief.py` | `persist_to_cloud_sql` | 3232 | 1 | M: `0`; `premarket_analysis` never written |
| `gcp/premarket_brief.py` | `fetch_premarket_analysis_row` | 3474 | 1 | M: `None`; the `/replay` cache-hit job logs "no row" and exits 1, hiding the cause |
| `gcp/signal_monitor.py` | `SignalMonitor._persist_signal_alert` | 1650 | 1 | H: returns after the Discord post; the fire never reaches `signal_alerts` |
| `gcp/signal_monitor.py` | `SignalMonitor._persist_exit` | 2403 | 1 | H: returns after the exit alert; the exit is never recorded |
| `lib/earnings_reactions.py` | `get_earnings_calibration` | 101 | 1 | M: Tier-B env defaults with no tier flag, no log |
| `lib/earnings_reactions.py` | `get_calibration_options_metrics` | 425 | 1 | H: `{}`; the Q5 IC override is silently off |
| `lib/earnings_reactions.py` | `query_reaction_stats` | 523 | 1 | M: `{}`; playability vanishes for every ticker |
| `lib/earnings_reactions.py` | `query_typical_daily_return` | 582 | 1 | M: `{}`, no log |
| `lib/earnings_reactions.py` | `query_conditional_reactions` | 682 | 1 | M: `{}`; only the docstring discloses it |
| `lib/strategies/exit_config_overrides.py` | `_latest_overrides` | 108 | 1 | H: `None` ("no row"); the direction kill switch fails open |
| `lib/strategies/brief_bias.py` | `get_premarket_bias` | 69 | 1 | H: `bias='UNAVAILABLE'`; the monitor scores `ftfc_score = 0.0`, so counter-FTFC fires escape the penalty |
| `platform/api/routers/admin.py` | `_strat_engine_state_cells` | 486 | 1 | UNSURE: `cells: []` with HTTP 200; the import goes uncaught and the client handler beneath classifies (Design) |
| `platform/api/routers/catalysts.py` | `_fetch_live_events` | 144, 148 | 2 | M: `None` plus ERROR; the cache is served labelled "Benzinga" |

### Part 2 (24 keys, 25 handlers)

`PART2` holds these keys until part 2, a draft, is approved and removes them. Each key pins one guard, except
`compute_score_quality_correlation`, which pins two.

| Path | Function | Lines | Guards |
|---|---|---|---|
| `gcp/fetchers/fetch_alphavantage_intraday.py` | `_ticker_already_backfilled` | 205 | `gcp.database` |
| `gcp/fetchers/fetch_earnings_history.py` | `fetch_yahoo_timing_for_ticker` | 119 | `yfinance` |
| `gcp/fetchers/fetch_earnings_history.py` | `_earnings_calendar_tickers` | 247 | `gcp.database` |
| `gcp/fetchers/fetch_earnings_history.py` | `_tickers_reporting_in_window` | 281 | `gcp.database` |
| `gcp/fetchers/fetch_earnings_history.py` | `_filter_already_have_history` | 327 | `gcp.database` |
| `gcp/fetchers/fetch_earnings_history.py` | `_earnings_history_tickers` | 369 | `gcp.database` |
| `gcp/fetchers/fetch_economic_events.py` | `fetch_forexfactory_events` | 161 | `requests` |
| `gcp/fetchers/fetch_economic_events.py` | `fetch_fred_releases` | 258 | `requests` |
| `gcp/fetchers/fetch_insider_transactions.py` | `_earnings_calendar_tickers` | 123 | `gcp.database` |
| `gcp/fetchers/fetch_market_data.py` | `_earnings_tickers_in_window` | 663 | `gcp.database` |
| `gcp/fetchers/fetch_market_data.py` | `_backfill_targets` | 754 | `gcp.database` |
| `gcp/fetchers/fetch_news_sentiment.py` | `_fetch` | 76 | `requests` |
| `gcp/fetchers/fetch_premarket_refresh.py` | `resolve_universe` | 64 | `gcp.database` |
| `gcp/fetchers/fetch_premarket_refresh.py` | `_prev_close_from_db` | 142 | `gcp.database` |
| `gcp/fetchers/fetch_premarket_refresh.py` | `upsert_premarket` | 244 | `gcp.database` |
| `gcp/fetchers/fetch_sec_filings.py` | `_earnings_calendar_tickers` | 424 | `gcp.database` |
| `gcp/indicator_correlation_job.py` | `_load_signal_outcomes` | 507 | `gcp.database`, `sqlalchemy` |
| `gcp/signal_quality_alarm.py` | `compute_score_quality_correlation` | 263, 286 | `numpy`; `scipy.stats` |
| `lib/ticker_info.py` | `_cloud_sql_available` | 56 | `gcp.database` |
| `lib/ticker_info.py` | `refresh_watchlist_info` | 720 | `gcp.fetchers._watchlist` |
| `scripts/fetch_earnings_calendar.py` | `_load_existing_options_from_db` | 347 | `gcp.database` |
| `scripts/fetch_earnings_calendar.py` | `_fetch_yahoo_bulk` | 833 | `yfinance` |
| `scripts/fetch_earnings_calendar.py` | `fetch_yahoo_earnings` | 1082 | `yfinance` |
| `scripts/fetch_earnings_calendar.py` | `persist_to_cloud_sql` | 1106 | `gcp.database` |

### Allowlist (21 keys, 21 handlers)

Each key pins one guard. Each reason gives the evidence for why the handler is not a production path that must
fail loud. Five of the rows guard an internal module: `options_greeks:186`, `options_intraday:160` and `:588`,
`options_pnl_translation:253`, and `premarket_brief:1818`. Two end in a raise of another type, and their callers
were traced: `evaluation_windows:160` and `health:134`.

| Path | Function | Line | Guards | Reason |
|---|---|---|---|---|
| `gcp/fetchers/fetch_av_historical_options.py` | `_trading_days` | 177 | `pandas_market_calendars` | WARNING and a Mon-Fri superset; the extra day logs "No options data" and writes nothing |
| `gcp/fetchers/fetch_rss_news.py` | `main` | 726 | `dotenv` | optional dotenv; Cloud Run supplies the environment; no data effect |
| `gcp/indicator_correlation_job.py` | `_class_mutual_info` | 217 | `sklearn.feature_selection` | `mutual_info` is `None`/NULL, never 0 |
| `gcp/insight_tasks.py` | `enqueue_insight_task` | 148 | `google.api_core`, `google.cloud` | returns `EnqueueOutcome.NOT_ENQUEUED` plus ERROR, and each of its three callers acts on it. The insight job runs the ticker in-process and logs the count (`gcp/insight_pipeline_job.py:619-644`). `gcp/auto_refresh_top_n.py:294-313` marks the run failed. The insights route runs it in-process with BackgroundTasks (`platform/api/routers/insights.py:876-882`). The API image installs no `google-cloud-tasks` (`platform/Dockerfile:24-37`, `platform/api/requirements.txt`), so the route always takes the in-process path; whether that is intended is not checked here |
| `gcp/premarket_brief.py` | `empirical_fallback_footer` | 1818 | `lib.options_intraday` | internal module, but the substitute is the imported constant's own value (`lib/options_intraday.py:100`), so no caller can observe the difference |
| `gcp/queries/run_query.py` | `main` | 412 | none (a tuple handler around work) | writes a `system_error` result row and exits 1 |
| `gcp/research/magnitude_engine/evaluation_windows.py` | `last_expected_session` | 121 | `pandas_market_calendars` | previous weekday is never earlier than the true last session, so only a false refusal |
| `gcp/research/magnitude_engine/evaluation_windows.py` | `expected_session_bars` | 160 | `pandas_market_calendars` | raises `RuntimeError` naming the missing library; its one caller, `walk_forward`'s final-window preflight (`mag_walk_forward.py:1313`), has no catch on the Cloud Run task path (`:1874`), and the legacy all-cells loop records the cell as status `ERROR` with the message (`:1661-1665`) |
| `lib/options_greeks.py` | `get_rate_and_yield` | 186 | `gcp.database` | internal module, but never a value in production: it raises `RateLookupError` naming the import failure ("gcp.database unavailable (...)") unless `allow_defaults=True`, which no caller passes (only `lib/options_greeks.py` itself names it) |
| `lib/options_intraday.py` | `load_realtime_theta_curve` | 160 | `gcp.database` | internal module, but no production caller: only `lib/options_intraday.py` itself and `scripts/analysis/` call it, and nothing under `gcp/` or `platform/api/` imports the module's functions; the curve is stamped `data_source='empirical_fallback'` |
| `lib/options_intraday.py` | `_load_intraday_bars` | 588 | `gcp.database` | internal module, but no production caller (as `:160`); the caller WARNs and returns a typed empty timeline |
| `platform/api/main.py` | `_strat_engine_state` | 346 | `google.cloud` | `[]` renders the `/dev` line "strat-engine artifact state unavailable" followed by "GCS unreachable" (`main.py:477-478`), so a missing `google.cloud.storage`, which this spec treats as a defect in `admin.py`, shows as a storage outage there; the item 13 issue names that misattributed cause. Listed because no data value reaches a caller, only the dev page's HTML, and `main.py` is left to FEAT-DEPLOY-001's open stocks#1384 |
| `platform/api/routers/health.py` | `_run_audit_and_cache` | 134 | `audit_data_freshness` | answers HTTP 500 at the route boundary, the status `lib/infra_errors.py` gives a defect; no value reaches a caller |
| `platform/api/routers/insights.py` | `_stream_gemini` | 1053 | `google.genai` | streams the explicit error text to the user; no data produced |
| `scripts/analysis/options_pnl_translation.py` | `load_realtime_marks` | 253 | `gcp.database` | internal module, but an analysis CLI that no job or workflow runs (no reference in `gcp/deploy.sh` or `.github/workflows/`); every row stamped `data_source='empirical_fallback'` |
| `scripts/analysis/phase4_setup_discovery.py` | `run_decision_tree_analysis` | 381 | `sklearn.ensemble`, `sklearn.tree` | the report prints "sklearn not available, using rule-based analysis instead" |
| `scripts/fetch_alphavantage_intraday.py` | `<module>` | 26 | `pandas_market_calendars` | prints a notice; legacy manual CLI that no job or workflow runs |
| `scripts/fetch_alphavantage_options.py` | `<module>` | 34 | `pandas_market_calendars` | prints a notice and uses a weekday fallback; manual CLI |
| `scripts/fetch_earnings_calendar.py` | `_fetch_yahoo_one` | 957 | `yfinance` | no production caller: only tests call it (no reference in `lib/`, `gcp/`, `platform/api/` or `scripts/`) |
| `scripts/gate/spec_gate.py` | `valid_yaml` | 820 | `yaml` | returns the reason string; the caller (`:1842-1843`, `:1868-1869` on a main holding stocks#1383) fails the gate closed |
| `scripts/validation/validate_brief_accuracy.py` | `_connect` | 252 | `google.cloud.sql.connector`, `pg8000.dbapi` | guards the external Cloud SQL Connector and falls through to a direct connection to the same database; any failure raises |

### Broad guards (7 keys, 14 handlers)

Pinned in `KNOWN_BROAD`, not fixed here; the issue in done_when item 13 lists them.

| Path | Function | Lines | Handlers | Guards | Substitutes |
|---|---|---|---|---|---|
| `lib/gamma.py` | `compute_gamma_flip_bs` | 722 | 1 | `lib.options_greeks`, `scipy.stats` | `None` plus WARNING |
| `lib/infra_errors.py` | `<module>` | 196, 200, 204, 208, 212, 216, 220 | 7 | `psycopg2`, `pg8000.exceptions`, `aiohttp`, `google.auth`, `requests`, `urllib3`, `google.api_core` | each alias bound to `None` |
| `lib/infra_errors.py` | `_storage_response_types` | 643 | 1 | `__import__` of a variable name (`<dynamic>`): `google.cloud.storage.exceptions`, `google.resumable_media` | `pass`; the type is left out of `_STORAGE_RESPONSE_TYPES` |
| `platform/api/routers/catalysts.py` | `_db_catalyst_events` | 347 (339 on the PR head) | 1 | `gcp.database` | `[]` plus WARNING |
| `platform/api/routers/dashboard.py` | `<module>` | 47, 55 | 2 | `platform.api.routers.live`, then `api.routers.live` | `:47` retries; `:55` sets `MARKET_HOLIDAYS_2026 = set()` and three names to `None` |
| `scripts/backfill_watchlist_data.py` | `_scalar` | 85 | 1 | `gcp.database` | `None` plus WARNING |
| `scripts/backfill_watchlist_data.py` | `backfill_daily` | 189 | 1 | `requests`, `pandas`, `gcp.database`, `gcp.fetchers.fetch_market_data` | `False` plus WARNING |

## Risks

- **stocks#1383 must merge first, and it is stalled.** Until it merges, this PR cannot carry the re-rendered
  blocks, and without them the lean Run Tests job fails `test_check_generated_docs.py` (executed). stocks#1383 is
  a draft held by its own CI-time stop condition (Generated and model documents), so this PR waits on the owner's
  decision there. Item 14 makes the wait visible rather than letting the PR open red. The only route that does
  not wait is keeping every cited line in place, rejected in Approaches considered.
- **A handler the audit called acceptable may still mislead.** The allowlist puts each reason in one file,
  where review can read them together. The issue in done_when item 13 lists the allowlist too, and each entry's
  pins stop a different guard hiding in a listed function.
- **The ratchet sees one function.** A handler it accepts keeps the import error, but a caller's broad catch can
  still swallow it. This spec traced and fixed the callers of every handler it removes (Caller catches). The two
  pre-existing accepted handlers raise `ImportError` from functions this spec does not change:
  `lib/features/fracdiff.py:172` and `gcp/database.py:191`.
- **What the scan cannot see.** It resolves handler types and calls written as a name or attribute, alone, in a
  tuple or through a module-level alias. It does not see `import_module` called under another name, an
  `ImportError` alias it cannot resolve around a try body that does work, a type built by tuple concatenation
  around such a body, or `suppress` reached through a variable or given `*_E`. Review catches those.
- **The database layer's own ImportError is still swallowed on most of these paths.** `gcp/database.py:191`
  raises `ImportError` from inside `get_engine()` when `cloud-sql-python-connector` cannot be imported. Two broad
  handlers around work catch it before any site this spec fixes can:
  - `query_to_dataframe`'s `except Exception` (`gcp/database.py:239-241`) logs a WARNING and returns an empty
    frame;
  - `get_premarket_bias`' query `try` (`lib/strategies/brief_bias.py:93-96`) returns `_unavailable('query_failed')`.

  Executed on 2026-10-12 with the connector made unimportable, Cloud SQL variables set and sockets refused (the
  second pre-review's `connector_probe.py`), with the same output on `17bbacd3` and on this change:
  `fetch_premarket_analysis_row` returned `None` (the `/replay` "no row" symptom), `load_earnings_for_brief`
  returned no earnings ("No earnings scheduled"), `load_yesterday_amc_reactions` returned `[]`,
  `get_earnings_calibration` returned the Tier B defaults, `get_calibration_options_metrics` and
  `query_reaction_stats` returned `{}` (the Q5 override off, no playability), `get_premarket_bias` returned
  `UNAVAILABLE` with reason `query_failed` (the FTFC penalty off), and `get_disabled_directions` raised
  `OverridesUnavailable` (the kill switch fails closed; the exit-target getters use Tier B with a WARNING).
  - So this change makes a missing `gcp.database`, `pandas_market_calendars`, `google.cloud.storage` or fetcher
    module fail loud, but not a missing Cloud SQL connector below `gcp.database`.
  - The two handlers are pre-existing §3.7 data-access swallows around work, outside this spec (Non-goals).
    stocks#1047 tracks `query_to_dataframe` (its C-01 row). Item 13's issue lists both with these outcomes, and
    every image that runs these jobs installs the connector (`requirements-gcp.txt:50`, `platform/Dockerfile:29`).
- **A job that has been running on a fallback now fails loud.** That is the intent, and only for an import that
  genuinely fails in its image.
  - In an image without `gcp.database`, signal-monitor already raises in `main` (`:2624`). If only one name is
    missing (a renamed `upsert_dataframe`), the exit comes at the first fire. That is after the fire's Discord
    post (`:1613`) and before the `daily_trades` bump (`:1633`). After an exit alert, the daily P&L bump
    (`:2133`) does not run.
  - With the kill-switch and brief-bias catches re-raising `ImportError`, an unimportable override or bias store
    ends the monitor run, because `run_loop` has no catch, instead of scoring neutral or suppressing each fire.
- **The brief's per-ticker isolation ends for import errors.**
  - `_trading_days_between` has one caller, `persist_level_map` (`strat_levels.py:1830`). Its one caller is
    `premarket_brief.py:1634`, in the jobs image, which pins the library.
  - The new handlers at `:1652` and `:1680` mark the ticker and then re-raise, which ends the brief.
  - A missing module fails every ticker alike, so isolation buys nothing there.
- **The admin route's statuses.** A storage outage now reads as an error on the Model State card instead of an
  empty shelf. Product documents lists the lines of 03 and of solyra's UI-SCREENS that say otherwise, and when
  they change.
- **One existing test line changes.** It is the route sweep's expectation for
  `GET /api/admin/strat-engine/state` (Design, admin section). done_when item 12 names it as the only deleted
  line under `tests/`.
- **No gate file changes.** The ratchet reads `scripts/gate/spec_gate.py` (its `valid_yaml` handler is
  allowlisted) but changes no gate file, so the gate red-team pass does not apply.
- **Overlap with FEAT-DEPLOY-001.** The sibling FEAT-DEPLOY-001 work (stocks#1384) edits
  `platform/api/main.py:480` and `:529` and `tests/api/test_dev_page_auth.py`, near the allowlisted
  `main.py:346`. No line overlaps, and its source edits replace lines one for one (`main.py` 1 for 1,
  `routers/earnings.py` 3 for 3, read from its file list), so they move no line the inventory blocks cite.
  Whichever merges second runs its CI, `test_check_generated_docs.py` included, on a main that holds the first.
- **Part 2 depends on part 1.** Part 2 is a draft and cannot start before this spec's PR merges, because its plan
  deletes `PART2`. Until then its 25 handlers keep substituting, as they do today, and the item 13 issue tracks
  them.
