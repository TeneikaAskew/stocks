---
feat_id: FEAT-OPS-001
req_ids: [REQ-DATA-001, REQ-GOV-004]
issues: [1316, 928, 1335, 1047]
canvases: [https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN]
done_when:
  - "tests/meta/test_no_import_fallbacks.py::test_no_unlisted_import_fallbacks, run against origin/main's lib/, gcp/, platform/api/ and scripts/, fails listing exactly the 20 handlers in this spec's Sites removed table as path:line qualname, with no pin mismatch, and passes on the PR head"
  - "tests/meta/test_no_import_fallbacks.py keys ALLOWED, PART2 and KNOWN_BROAD by (path, qualified function name), each mapping to a reason and to the guards that function may hold, each guard pinned as its handler types, the modules its try body imports and the value it substitutes; ALLOWED's keys are exactly the 16 in this spec's Allowlist table, PART2's exactly the 24 keys (25 guards) in its Part 2 table and KNOWN_BROAD's exactly the 7 keys (14 guards) in its Broad guards table, and self-tests assert that the scan fails when a listed function holds a guard its entry does not pin or lacks one it pins: a one-for-one swap to another module, a new substitute for the same import, a widened handler type, a second guard, and a pinned guard that is gone"
  - "tests/meta/test_no_import_fallbacks.py runs its detector on inline snippets and asserts it refuses: except Exception, except BaseException and a bare except: around a try body of only imports, and around a body calling __import__ or importlib.import_module; except ImportError and except ModuleNotFoundError each alone, in a tuple, as an attribute and through a module-level alias tuple; a handler type it cannot resolve to a builtin exception around an imports-only body (a function-local alias, a class attribute, a concatenated tuple, an imported name); an imports-only body that also assigns constants (HAVE_YAML = True) under a broad or import handler; except* ImportError; with contextlib.suppress(ImportError) around an import; a conditional raise; a raise only inside a nested try or handler; a handler that returns, yields, continues or breaks before its final raise, including a return inside a nested try within the handler; a handler that calls sys.exit, os._exit or os.abort before its raise, also through import sys as s and from sys import exit as e; a raise of another type anywhere in the handler (RuntimeError, HTTPException, SystemExit, KeyboardInterrupt), including inside an if before a final bare raise and after marking a status; a handler that rebinds or deletes the name it bound; an except ImportError: raise placed after a sibling handler of the same try that catches Exception or everything and returns; an otherwise accepted handler whose try has a finally that returns; an otherwise accepted handler wrapped in the same function by an outer try whose first handler able to catch an ImportError returns or wraps it, or by a with contextlib.suppress(Exception); an outer or earlier sibling handler whose type it cannot resolve (a function-local alias) that returns; an outer handler of an imported type that re-raises, followed by except Exception: return []; a finally that raises another type; an assert in the handler before its final bare raise, alone or inside an if, and an assert in the finally of its own try or of an enclosing try; a try with no handler, or with only handlers that cannot catch an ImportError (except ValueError), whose finally returns, breaks or continues out of the finally, asserts, calls sys.exit, os._exit or os.abort, or raises another type around an import (try: import x then finally: return []); suppress imported under another name (from contextlib import suppress as quiet); and a module-level alias tuple bound with an annotation (_E: tuple = (ImportError, OSError)) around work. It accepts a handler that ends in a raise when every raise in it is a bare raise, a raise of the name it bound, or a raise of ImportError or ModuleNotFoundError, and no return, yield, continue, break, assert or exit call appears in it outside nested function, lambda and class bodies, including an except ImportError: raise placed ahead of an outer except Exception"
  - "tests/meta/test_no_import_fallbacks.py pins the 14 broad import guards in this spec's Broad guards table in KNOWN_BROAD, and fails on any other bare except:, except Exception or except BaseException, written as the scan resolves it (a name or attribute, alone, in a tuple or through a module-level alias), whose try body is only imports, or imports beside constant assignments, or calls a function named __import__ or import_module; and it fails on every try, whatever its handlers, whose finally holds a return, a break or continue that leaves the finally, an assert, an exit call (sys.exit, os._exit, os.abort, exit or quit, under the names the file's imports give them) or a raise of another type while its body holds an import or calls __import__ or import_module, of which origin/main's code has none"
  - "tests/meta/test_no_import_fallbacks.py pins each of the 11 rows of this spec's Caller catches table by its path, its qualified function name and a callee, and locates the row's try as the one try in that function whose own body, outside nested try statements and nested function, lambda and class bodies, calls the callee (a row that matches no try or more than one fails); it asserts that on the PR head the first handler of that try able to catch an ImportError (a type that includes ImportError, a subclass of it, Exception or BaseException, a bare except, or a type that does not resolve to a builtin exception) has as its type exactly the name ImportError, alone (not ModuleNotFoundError, a tuple or an alias), and ends in a bare raise, so it precedes the row's broad handler and, at :1685, except StaleSourceDataError; the check fails on origin/main's code, which has no such handler, and its self-tests refuse except ModuleNotFoundError: raise, except (ImportError, TypeError): raise, and except ImportError: raise placed after except StaleSourceDataError"
  - "With the import made to fail (monkeypatch.setitem(sys.modules, 'gcp.database', None) unless this item names another), pytest.raises(ImportError) holds for: gcp.signal_monitor.SignalMonitor._persist_signal_alert and SignalMonitor._persist_exit in tests/gcp/test_signal_monitor_persist.py; lib.strategies.exit_config_overrides.get_disabled_directions in tests/lib/test_exit_config_overrides.py, whose autouse fixture clears the lru_cache; lib.strategies.brief_bias.get_premarket_bias, its cache cleared, in tests/gcp/test_signal_monitor_brief_bias.py; gcp.premarket_brief.load_earnings_for_brief, load_economic_events, _delete_null_close_rows, load_yesterday_amc_reactions, persist_to_cloud_sql and fetch_premarket_analysis_row, and _playability_lines both with lib.earnings_reactions blocked and with only DEFAULT_LOOKBACK_QUARTERS removed from it, in tests/gcp/test_premarket_brief.py; and lib.earnings_reactions.get_calibration_options_metrics, get_earnings_calibration (cache cleared), query_reaction_stats, query_typical_daily_return and query_conditional_reactions in tests/lib/test_lib_earnings_reactions.py"
  - "tests/api/test_admin_users_datasources.py asserts that GET /api/admin/strat-engine/state, under TestClient(..., raise_server_exceptions=False), answers 500 when google.cloud.storage cannot be imported (None in sys.modules and the storage attribute removed from google.cloud), 503 when storage.Client() raises google.auth.exceptions.DefaultCredentialsError, 500 when storage.Client() raises TypeError, and 200 with nine cells, none available, when the client works and no model.pkl exists; origin/main's code answers 200 with cells: [] to the first three"
  - "For each of the 11 rows of this spec's Caller catches table, a test makes that row's callee raise a plain ImportError (the class a missing name raises, not ModuleNotFoundError) and asserts with pytest.raises(ImportError) that it propagates out of the function holding the catch; against origin/main's code each of the 11 fails, because the catch logs and carries on. The :1685 row has a second import test: with gcp.database.get_engine removed, ImportError leaves generate_premarket_brief. For the 7 rows marked pinned here, a second test makes the callee raise RuntimeError and asserts the row's handling today (its logged line, or the ticker's status and error, and the result it carries on with); each passes on origin/main and on the PR head, and fails when that row's new handler is widened to catch every exception. Item 5 holds each row's handler to exactly except ImportError"
  - "Tests drive each of the four job runs in this spec's Entry points table end to end, hermetically, with that row's import made to fail and its stubs: gcp.premarket_brief.main(['--no-discord']) with gcp.database blocked, gcp.premarket_brief.main(['--post-existing', 'SPY', '2026-10-08']), gcp.signal_monitor.main() in loop mode for one poll and gcp.refresh_earnings_views.main(['--mode', 'daily']). On the PR head each run raises ImportError, or exits 1 having logged it, and that ImportError's traceback passes through the function in the row's Reaches column; against origin/main's code no run produces such a traceback"
  - "Tests assert that GET /api/catalysts/events?refresh=true, GET /api/catalysts/ticker/{ticker} and POST /api/backtest/replay-trades answer 500 under TestClient(..., raise_server_exceptions=False) with the import in this spec's Entry points table made to fail, where origin/main's code answers 200; and tests/api/test_catalysts_news_filter.py's package-path test asserts that, with BENZINGA_API_KEY set, scripts.fetch_catalyst_calendar's fetch_all_catalysts and save_catalysts stubbed and the bare module name fetch_catalyst_calendar blocked, _fetch_live_events returns the stubbed events, on origin/main's code and on the PR head"
  - "The PR body shows test_no_unlisted_import_fallbacks run against origin/main's code and FAILED naming the 20 removed handlers, and each test of items 5 to 10 that asserts the change's new behaviour run against origin/main's code and FAILED. The pins (item 7's 200 case, item 8's seven RuntimeError tests and item 10's package-path test) are shown passing on both trees, and the detector self-tests and table checks of items 2 to 4, and item 5's self-tests, pass on any tree and are exempt. The Backtest Pipeline jobs Run Tests, Research Tests (heavy ML stack) and Integration Tests (ephemeral Postgres) are green on the PR head"
  - "git diff --numstat origin/main...HEAD -- tests/ shows 0 deleted lines in every existing test file except tests/api/test_route_coverage.py, whose one deleted line is its GET /api/admin/strat-engine/state expectation of 200, now 503"
  - "The PR body links a new issue that lists: the 14 broad import guards, lib/gamma.py:722, lib/infra_errors.py:196, :200, :204, :208, :212, :216, :220 and :643, platform/api/routers/catalysts.py:360, platform/api/routers/dashboard.py:47 and :54, scripts/backfill_watchlist_data.py:85 and :189, each with the value its handler substitutes; the 25 handlers of this spec's Part 2 table; the 16 Allowlist keys with their reasons, naming platform/api/main.py:374's misattributed cause; and the two broad handlers that still swallow the database layer's own ImportError, gcp/database.py:239-241 (query_to_dataframe) and lib/strategies/brief_bias.py:93-96, with the outcomes this spec's Risks lists. Lines are at 16b3fabd, each given with its function name. It also references #1047 for the two swallowing handlers"
  - "The PR carries the inventory blocks of docs/product/infrastructure/05-a-ARCHITECTURE.md, 05-c-DATA_DEPENDENCIES.md and 05-e-API.md exactly as python -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --insert, given those three paths, renders them on the PR head, and changes no other line of those documents than that render changes; the spec gate's REQ-GOV-004 check (check_product_scope, on main since stocks#1538), which re-renders the three documents from the PR's committed tree, refuses none of them, and tests/scripts/test_check_generated_docs.py passes on the PR head"
  - "Every pointer in docs/models/MODEL-*.md into a file this change edits, path:line, symbol-anchored, and bare :N whose file the same table row, sentence or paragraph names, names the same statement on the PR head as on origin/main. The PR body shows the check that maps each pointer's origin/main line to the head through the diff and compares the statement: it reports 0 stale pointers on the PR head, and run against the documents as they stand on origin/main it reports the stale ones. tests/meta/test_model_registry_consistency.py passes on the PR head"
  - "Each of the 13 fallbacks listed in this spec's AUDIT markers table carries an AUDIT-2026-05-13 comment, as the first line of its handler's body or, for the inline fallback, on the line above it, naming what it substitutes; and of the 11 broad handlers that a Caller catches row's new except ImportError handler is placed before, each carries such a comment except the two playbook catches, gcp/premarket_brief.py:1685 and :1713, which mark the ticker PLAYBOOK_FAILED with its error"
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
code under this spec was unchanged at `d0231901`, origin/main when r3 was cut. Codex reviewed r3 once, as
stocks#1424 at `b299246c`. This revision, r4, answers its four findings and reads every line again on main
`16b3fabd` (Bases, and What main changed since r3).

### Codex's review of stocks#1386

1. **The route's documents (P2).** The change turns `GET /api/admin/strat-engine/state` from a 200 with no cells
   into an error, and `docs/product/03-SITE-TRACEABILITY.md` says the route swallows storage failures and is
   pinned at 200. The gate refuses that file on this branch. Answered by the Product documents table and done_when
   item 17 (ruling in Product documents).
2. **A wrapped import error (P2).** stocks#1386 let `_trading_days_between` end in
   `raise RuntimeError(...) from exc`. Executed with that variant and `pandas_market_calendars` blocked,
   `gcp.premarket_brief.main(['--no-discord'])` returned normally with every ticker marked `PLAYBOOK_FAILED`: the
   new `except ImportError` at `gcp/premarket_brief.py:1652` cannot see a `RuntimeError`, so the broad handler
   under it swallowed it. From r1 every removed handler let the ImportError itself propagate. r3's item 5
   asserted `ImportError` alone and its item 9 drove the brief with the calendar library blocked; r4 dropped
   both (What main changed since r3), and the ratchet still refuses a wrapper.
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

  REQ-GOV-004 says the PR carries the re-rendered blocks, and main's gate then refused that until stocks#1383
  merged. So r1 to r3 opened the PR only after stocks#1383 was on main, carrying the re-render (item 14); r4
  relies on stocks#1538 instead (What main changed since r3, fact A). The PR also re-points the model documents'
  pointers, which sit outside `docs/product/` (item 15). Generated and model documents explains both.
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

### Codex's review of stocks#1424 (r3)

Codex reviewed r3 at `b299246c` and left four findings. Each was confirmed against r3's text and by running the
Python behaviour it names (Python 3.11.18, a snippet per shape), and each is answered in the Design and in
done_when together.

1. **Assertions that replace the import error (P2).** r3's acceptance rule let `assert condition` stand before
   the final bare `raise`: an `Assert` was neither a refused raise nor a listed exit. Executed: with the
   condition false, the handler raises `AssertionError` instead of the `ModuleNotFoundError`, and a caller's
   `except ImportError: raise` followed by `except Exception: return []` returns `[]`. An `assert` in the
   handler's own `finally` replaces the error the same way. The rule now refuses an `assert` in the handler
   and in the `finally` of its own or an enclosing `try`, and item 3 names a self-test for each place.
   On `16b3fabd` no import handler holds an `assert` (Bases).
2. **Markers for every catch the fix edits beside (P2).** The Design puts an `except ImportError: raise` ahead of
   each Caller catches row's broad handler, and r3's AUDIT markers table left two of those out:
   `lib/signals.py:316`, which returns `None`, as a bar with no signal does (executed on `16b3fabd`), and
   `gcp/signal_monitor.py:1155` (`:1160` on `16b3fabd`), which returns `(None, None)`, as for no fire. Both are in
   the table now, and item 16 also requires a marker on every broad handler a row's new handler precedes, except
   the two playbook catches, which mark the ticker `PLAYBOOK_FAILED` with its error (AUDIT markers). The third
   location, `scripts/generate_historical_report.py:125`, is no longer edited: on `16b3fabd` no removed site
   reaches it (fact C below), so it leaves the Caller catches table.
3. **Each caller guard pinned to exactly `ImportError` (P2).** r3's item 8 raised `ModuleNotFoundError`,
   which `except ModuleNotFoundError: raise` also passes, while a missing name raises a plain `ImportError`
   that such a handler lets through to the broad handler beneath (executed: the row returned its fallback).
   And `except (ImportError, TypeError): raise` passed every test while sending a `TypeError` out of the
   function (executed). Item 8's first tests now raise a plain `ImportError`, and item 5, which held the
   `_trading_days_between` test that main made redundant (fact B), now checks each row's handler by its
   shape: the first handler of the row's try able to catch an `ImportError` has as its type exactly the name
   `ImportError`, alone, and ends in a bare `raise` (Design, Handler shape).
4. **Import suppression by a bare `try`/`finally` (P2).** No guard kind covered `try: import x` with
   `finally: return []`. Executed: it returns `[]`; `finally: raise RuntimeError(...)` replaces the error, and
   `finally: break` inside a loop discards it. Kind 4 now covers every `try` whose `finally` exits, asserts or
   raises another type while its body holds an import, whatever its handlers, and is never accepted. Item 3
   names the self-tests and item 4 the scan, which finds no such `try` on `16b3fabd` (Bases).

### What main changed since r3

r3 read its lines on `17bbacd3`. Main is `16b3fabd` now, 249 commits later, and three of its changes reach this
spec. Each was checked by running the command named here:

- **A. stocks#1383 closed unmerged on 2026-10-14.** The allowance it carried, that a feature branch may carry
  the re-rendered inventory blocks of `05-a`, `05-c` and `05-e`, landed through stocks#1538 (`a5749d4c`):
  `git show origin/main:scripts/gate/spec_gate.py | grep -n REQ-GOV-004` finds it, and `check_product_scope`
  re-renders the three documents from a pull request's committed tree and refuses any that differ
  (`generated_doc_refusals`). Item 14 no longer waits on stocks#1383 (Generated and model documents, Risks).
- **B. stocks#1546 (`3ab668a9`) removed six of the 69 import handlers.** One is
  `lib/strat_levels.py::_trading_days_between`, which now calls `lib.eastern_time.session_count`. Executed on
  `16b3fabd`: with `pandas_market_calendars` blocked and the session cache reset it raises
  `ModuleNotFoundError`, with the cache warm it still returns 3, and main's
  `tests/lib/test_silent_fallback_fixes.py::test_strat_levels_raises_without_calendar` asserts the raise. So
  Sites removed lists 20 handlers in 18 functions and item 5's old test is dropped. The other five were
  allowlisted calendar guards, so ALLOWED has 16 keys. An AST walk of the 19 functions r3 listed finds 20
  import handlers on `16b3fabd`, none of them in `_trading_days_between`.
- **C. Lines moved, and one call went away.** Every table's lines are at `16b3fabd` now (Bases). stocks#1746
  (`15fc6368`) removed `context_from_bundle`'s call of `get_blue_sky_atr_offset`, so no removed site reaches
  `lib/agents/trade_planner.py:835` (gone), `lib/agents/orchestrator.py:592`,
  `scripts/generate_historical_report.py:125` or the insight-pipeline job. The Caller catches table has 11
  rows, Entry points loses the insight row, and Capacity loses the insight job's retry. And the brief now
  reads the shared calendar in `compute_strat_status` before its playbook block: executed on `16b3fabd` with
  `pandas_market_calendars` blocked, `generate_premarket_brief` raises `ModuleNotFoundError` through
  `compute_strat_status`, uncaught, so the calendar row of Entry points no longer tells the trees apart and is
  dropped.

## Bases

`16b3fabd` is origin/main when r4 was cut (2026-11-09), and every code and document line in this spec is at
`16b3fabd` unless it is marked otherwise. r1 to r3 read their lines on `17bbacd3`; the runs they record were
executed on `17bbacd3`, or on `d0231901`, which holds the same code, and say so. They were not re-run on
`16b3fabd` unless this revision says it re-ran them.

r4 moved the lines with these scans, each run against both commits:

- **Line mapping.** Each cited line was mapped from `17bbacd3` to `16b3fabd` through
  `git diff -U0 17bbacd3 16b3fabd -- <file>`, and the statement at both lines compared: every one held its
  text, except `lib/strat_levels.py:1722-1728` and `lib/agents/trade_planner.py:835`, which sit in changed
  hunks (What main changed since r3), and the end of `platform/api/routers/dashboard.py:40-59` (Broad guards).
- **Guard inventory.** An AST scan of every `.py` under `lib/`, `gcp/`, `platform/api/` and `scripts/` for
  kinds 1 to 3 as The ratchet defines them, written for r4 (the r3 draft detector is not in this workspace).
  It reproduces r3's count on `17bbacd3`: 67 kind-1 guards not accepted, 2 accepted, 14 of kind 2. On
  `16b3fabd` it finds 61 not accepted (20 + 16 + 25), the same 2 accepted and the same 14 of kind 2, no
  kind-3 guard and no type it cannot resolve. Compared by (path, function, types, modules), the only
  difference is the six handlers stocks#1546 removed; no guard was added.
- **Kind 4 and assertions.** A second scan for a `try` whose `finally` exits, asserts or raises another type
  around a body holding an import, and for an `assert` in an import handler, finds none on `16b3fabd`; on
  r4's probe snippets it finds each shape.
- **Callers.** A name-based caller trace over the same directories, seeded with the 18 removed functions and,
  separately, with `_trading_days_between` and `persist_level_map` (r3's route to its playbook rows), listing
  the `except Exception`, `except BaseException` and bare handlers each call sits under. It over-approximates
  (any function of the same name counts). Compared with the same trace on `17bbacd3`, it loses only the
  `get_blue_sky_atr_offset` chain (fact C) and a same-name match in `dashboard.py`. From the 18 removed
  functions it reaches nine of the 11 Caller catches rows on `16b3fabd`, not `:1685` or `:1713` (Caller
  catches).

## Problem

The class surfaced at `lib/strat_levels.py:1722-1728` on `17bbacd3`: `_trading_days_between` caught
`ImportError` for `pandas_market_calendars` and returned `int(calendar_days / 1.4)`. The count was too low, so it
switched off the staleness guard it feeds. Run on 2026-10-11 on `17bbacd3` with the library blocked:

- a source bar from Monday 23:00 UTC, read on Thursday 13:30, counted 1 trading day against a threshold of 2,
  and the stale row was written;
- with the library, it counted 3 and raised `StaleSourceDataError`.

Four tests in `tests/lib/test_strat_levels_freshness.py` failed in any environment without the library. Six
more passed only because the approximation landed on the right side of the threshold.

stocks#1546 has since fixed that site on main (What main changed since r3, fact B). On `16b3fabd` the same
file's 14 tests pass with the library, and with it blocked 12 fail, each with `ModuleNotFoundError` instead of
a wrong count (executed). This spec no longer edits `lib/strat_levels.py`. The class remains at the other sites.

An audit on 2026-10-11 covered every `except ImportError` and `except ModuleNotFoundError` handler under
`lib/`, `gcp/`, `platform/api/` and `scripts/`:

- It found 69 handlers. Those directories and `tests/` are unchanged from the audit's snapshot `2a108675` to
  `17bbacd3`, which is origin/main on 2026-10-12. On `16b3fabd` 63 remain: stocks#1546 removed the
  `strat_levels` handler and five the audit had accepted (Bases).
- Each substitute value was reproduced by calling the function with the import blocked.
- 38 handlers return a value a caller cannot tell from a real result.

Two more join those 38:

- the `strat_levels` handler above;
- `platform/api/routers/admin.py:486`, which the audit left UNSURE and the Design settles.

Review found six more among the 29 the audit had accepted:

- **Three Yahoo handlers.** `gcp/fetchers/fetch_earnings_history.py:119`, and
  `scripts/fetch_earnings_calendar.py:834` and `:1083`.
  - `yfinance` is declared for the image that runs them: `requirements-gcp.txt:18`, with
    `requirements-gcp.lock:223` pinning 1.2.0, which `gcp/Dockerfile:12-16` installs.
  - So their empty DataFrame reads as "Yahoo reported nothing" when the image is broken.
- **Three internal-module guards on production paths.**
  - `lib/strategies/brief_bias.py:69` returns `bias='UNAVAILABLE'`. The signal monitor then scores the bar with
    `ftfc_score = 0.0` (`gcp/signal_monitor.py:1302`), so the FTFC penalty is silently off.
  - `gcp/premarket_brief.py:3565` makes the `/replay` cache-hit job report "no row" for what is an import
    failure.
  - `gcp/indicator_correlation_job.py:507` makes the deployed job (`gcp/deploy.sh:809`) skip its signal target
    and exit 0.

That made 46 on `17bbacd3`. With the `strat_levels` handler gone from main, 45 remain on `16b3fabd`.

Removing a handler is not enough when its caller catches `Exception`, because the import error lands one level
up and is swallowed again. For example, `load_earnings_for_brief` logs "playability enrichment skipped" and goes
on (`gcp/premarket_brief.py:606`). The Design traces every caller.

The 45 handlers are split across two specs, by the entry points they reach:

- **This spec (part 1)** covers the decision paths. It:
  - removes 20 handlers on the signal-monitor, kill-switch, brief-bias, premarket-brief, earnings-reaction,
    admin and catalysts paths;
  - fixes the 9 caller catches above them, and the 2 playbook catches whose own try imports internal modules
    under a broad handler (Caller catches);
  - lands the ratchet.
- **Part 2** covers the ingestion and analytics jobs and removes the other 25 handlers. It is a draft, not yet on
  any branch; its repository path will be
  `docs/superpowers/specs/2026-10-11-feat-ops-001-no-import-fallbacks-jobs.md`. Until it is approved and lands,
  the ratchet lists its handlers in `PART2`, and the issue done_when item 13 files tracks them.

Seven of this spec's handlers change an alert, a recommendation or a risk control:

- `gcp/signal_monitor.py:1655` and `:2408` (`SignalMonitor._persist_signal_alert` and
  `SignalMonitor._persist_exit`) return silently after the Discord alert has gone out, so the fire or the exit
  never reaches `signal_alerts`.
- `lib/strategies/exit_config_overrides.py:108` (`_latest_overrides`) reads as "no row". Then
  `get_disabled_directions` returns an empty set, and the direction kill switch fails open. Executed on
  2026-10-11 on `17bbacd3`: with `gcp.database` unimportable, `lib.signals.evaluate_signal(row, min_conditions=3,
  ticker="QQQ")` fires a PUT. stocks#928 tracks the wider resolver contract; this spec closes only the import
  path.
- `lib/strategies/brief_bias.py:69` turns the FTFC penalty off, as above.
- `gcp/premarket_brief.py:327` and `:895` make the brief say "No earnings scheduled" and "No major events
  today", and the ORB window recommendation follows from the empty list.
- `lib/earnings_reactions.py:425` silently turns the calibration override off.

## Non-goals

- **The 14 broad import guards.** These are import guards caught by a bare or broad `except` (Broad guards
  table), such as `platform/api/routers/dashboard.py:41-57`, which sets `_is_market_open`, `get_live_quote` and
  `ET_TZ` to `None` (on `17bbacd3` it also set `MARKET_HOLIDAYS_2026 = set()`). This change does not fix them.
  The ratchet pins them so no new one lands, and the PR files an issue listing them.
- **The other broad handlers.** Their try body does work besides a static import, a dynamic import call
  (`__import__`, `import_module`) or a constant assignment. That is the general §3.7 data-access shape, not an
  import guard. Those this change edits beside get an `AUDIT-2026-05-13` marker (AUDIT markers table). The one
  exception is the brief's two playbook catches, whose own try imports internal modules (Caller catches).
  - Two near the admin change keep their handling, both lines of stocks#1316 and stocks#1335: the per-cell
    reads in `_strat_engine_state_cells` (`platform/api/routers/admin.py:516-522`, `:567-568`), where any storage
    error marks a cell unavailable and which get markers, and `_load_structure_brief_snapshot` (`:262-283`),
    which answers `None` for any error, a missing `google.cloud.storage` included, and which this change does not
    edit.
  - So this change settles the client half of stocks#1316, and the PR says on that issue what remains.
- **Handlers the audit accepted, beyond the six above.** The audit classed 29 handlers as acceptable, and the
  six above leave. Of the other 23, stocks#1546 removed five on main: the calendar guards of
  `gcp/fetchers/fetch_av_historical_options.py::_trading_days`, of
  `gcp/research/magnitude_engine/evaluation_windows.py::last_expected_session` and `::expected_session_bars`,
  and of the module code of `scripts/fetch_alphavantage_intraday.py` and `scripts/fetch_alphavantage_options.py`
  (Bases). Of the 18 on `16b3fabd`:
  - Two end in a raise that keeps the import error and need no entry: `lib/features/fracdiff.py:172` and
    `gcp/database.py:191`.
  - One ends in a raise of another type and is allowlisted with its callers traced:
    `platform/api/routers/health.py:134`.
  - The other 15 are allowlisted too.

  Every allowlist entry has a reason with evidence for why it is not a production path that must fail loud
  (Allowlist table).
- **Failures other than an import error.** Each caller-catch fix re-raises `ImportError` alone. A database or
  vendor failure at the same catch keeps today's handling. Item 8 pins that with tests of its own at seven
  catches, the two playbook catches `gcp/premarket_brief.py:1685` and `:1713` among them: the `PLAYBOOK_FAILED`
  tests call `persist_to_cloud_sql` with built dicts and never reach either catch. Existing tests pin it at the
  other four, each failing when its catch is widened (the second pre-review, executed on `17bbacd3`; each test
  is still on `16b3fabd`):
  - `lib/signals.py:316` (`test_resolver_failure_fails_closed`);
  - `gcp/signal_monitor.py:1160` (the `kill_switch_failure_count` tests) and `:2057`
    (`test_resolve_brief_bias_handles_lookup_exception`);
  - `gcp/premarket_brief.py:2503` (`test_empty_dict_still_propagates_after_failure`).
- **Behaviour in a healthy image.** With the import present, every code path runs the same statements as
  today, with one exception. In `platform/api/routers/admin.py:494`, `storage.Client()` fails although the
  package is installed. Today that answers 200 with `cells: []`. After this change it answers 503 when
  `is_infrastructure_error` calls the failure an outage, and 500 otherwise (Design, admin section).

## Approaches considered

1. **Fix `strat_levels` alone.** Rejected on 2026-10-11: the same defect was in 45 more places, and the review
   guideline this repository adopts says a class is fixed once, with each location.
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
6. **Chosen: split by caller closure, and carry the re-rendered blocks.** Each spec removes a set of handlers,
   fixes every catch above them, and drives every entry point they reach. The ratchet lands with part 1 and holds
   part 2's handlers in `PART2`, and the PR carries the re-rendered blocks under REQ-GOV-004, which main's gate
   accepts since stocks#1538 (r3 waited on stocks#1383 for it).

Chosen on 2026-10-11 under the owner's instruction to bring both repositories to a clean, closed-out state. The
four failing tests surfaced it. Codex's reviews of stocks#1379 and stocks#1386, and the pre-review of this
re-cut, shaped the split, the ratchet's rules, the admin statuses and the documents the PR carries.

## Design

### The fix, per handler

Each of the 20 handlers in the Sites removed table loses its substitute, and no handler takes its place: the
ImportError itself propagates. They guard either an internal module (`gcp.*`, `lib.*`, `scripts.*`) or
`google-cloud-storage`, which both images install.

A lazy import stays lazy, inside its function; it is simply not caught. The handler is deleted, except where
noted:

- `gcp/premarket_brief.py:2435` and `:2450` lose their stub copies of `lib.earnings_reactions` helpers and import
  them.
- `platform/api/routers/catalysts.py`, `_fetch_live_events`, keeps
  `from scripts.fetch_catalyst_calendar import ...`.
  - That import resolves because `catalysts.py:34` puts the repository root on `sys.path`, and the API image
    copies `scripts/` to `/app/scripts`.
  - The function drops the second-chance `sys.path` import at `:148-149` with both handlers. Item 10's
    package-path test pins the first import. Executed on `16b3fabd` with the bare name `fetch_catalyst_calendar`
    blocked and the two functions stubbed: `_fetch_live_events` returned the stubbed events, with `scripts/`
    itself not on `sys.path`.
- `platform/api/routers/admin.py`: see the next section.

A wrapper is not allowed at any of these sites: a caller's new `except ImportError` handler cannot see a
`RuntimeError` raised in the error's place, so the broad handler beneath it swallows the wrapper. Executed on
`17bbacd3`, with `raise RuntimeError(...) from exc` at `_trading_days_between`: the brief's playbook catch
marked every ticker and the run went on (Codex's finding 2 on stocks#1386).

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
The trace was executed on 2026-10-11 on `17bbacd3`: a call graph over `lib/`, `gcp/`, `platform/api/` and
`scripts/`, resolved through each file's imports, plus the instance callers of `BacktestEngine.run`. r4 ran a
name-based caller trace on `16b3fabd` and on `17bbacd3` (Bases): the only catches it no longer reaches are r3's
`lib/agents/trade_planner.py:835`, `lib/agents/orchestrator.py:592` and
`scripts/generate_historical_report.py:125`, since stocks#1746 removed the one call that led there (What main
changed since r3, fact C), and it reaches no catch on `16b3fabd` that it did not reach on `17bbacd3`.

That trace, seeded with the 18 removed functions, reaches nine of the 11 rows below. It does not reach `:1685` or
`:1713`, and on `17bbacd3` it reached `:1652` and `:1680` only through `_trading_days_between`, a site that is
no longer removed (fact B); seeded also with `_trading_days_between` and `persist_level_map`, it reaches both.
The two playbook rows stay for their own try: try@1636 imports `get_engine` from `gcp.database` and
`persist_level_map` and `StaleSourceDataError` from `lib.strat_levels`, and calls `get_engine()`, which raises
`ImportError` when the Cloud SQL connector is missing (executed on `16b3fabd` with
`google.cloud.sql.connector` blocked and Cloud SQL variables set), all under a broad handler. They are the one
exception to the Non-goals bullet on broad handlers around work: their import errors are this spec's class,
and r3 already pinned their order and handling.

The 11 catches below catch `Exception` and carry on, so each would swallow an import error: nine the error this
spec stops substituting, and the two playbook catches their own try's.

- **The default fix.** Each gets `except ImportError: raise` as the first handler of its try able to catch an
  `ImportError`, so ahead of its broad handler (immediately ahead of it at every row but `:1685`, where it also
  comes before `except StaleSourceDataError`): the type exactly the name `ImportError`, alone, which also catches
  its subclass `ModuleNotFoundError` and the plain `ImportError` a missing name raises.
  `except ModuleNotFoundError` would let that plain one through to the broad handler, and a tuple such as
  `(ImportError, TypeError)` would change the handling of a non-import failure (executed as snippets, Codex's
  review of stocks#1424, finding 3), so item 5 checks each row's handler by its shape. A database or vendor
  failure at the same catch keeps today's handling. Item 8's second tests pin that at the seven rows marked
  pinned.
- **Two exceptions.** At `gcp/premarket_brief.py:1685` and `:1713`, the new handler sets
  `d['status'] = 'PLAYBOOK_FAILED'` and `d['playbook_error']` and then ends in a bare `raise`. The existing
  structural test
  `tests/lib/test_silent_fallback_fixes.py::test_a_strat_levels_persist_failure_marks_the_ticker` (`:1041`)
  requires every handler on a `try` around `persist_level_map` to set the status, and a bare re-raise alone
  fails it (executed on `17bbacd3`).
  - At `:1685` the new handler is the try's first, ahead of `except StaleSourceDataError` (`:1676`), and the
    order is required. The try imports `get_engine` from `gcp.database` before it imports
    `StaleSourceDataError`, so when that first import fails, evaluating `except StaleSourceDataError` raises
    `UnboundLocalError`, which the playbook block's broad handler swallows. Item 8's second import test removes
    `gcp.database.get_engine`: it passes with this order and fails with the two handlers swapped and on
    origin/main (executed on `17bbacd3`). The ratchet refuses the swapped order too (executed on `17bbacd3`,
    where it read `gcp/premarket_brief.py:1652 generate_premarket_brief substitutes raise`).
  - Their pins drive `generate_premarket_brief` with one ticker failing and assert that ticker's status and
    error and that the other tickers carry on. At `:1685`, `persist_level_map` raises `RuntimeError` for SPY and
    the error reads "strat_levels persist failed: RuntimeError: ..."; widened, the outer handler writes a
    different error. At `:1713`, `build_level_map` raises for SPY; widened, the brief raises.
  - With `pandas_market_calendars` missing, `_trading_days_between` would raise inside `persist_level_map`, but
    on `16b3fabd` the brief raises first, uncaught, in `compute_strat_status` (executed; What main changed since
    r3, fact C). So `:1685` meets an import error from its own imports of `gcp.database` and
    `lib.strat_levels`, or from `get_engine()`.
- **Every one of these handlers ends in a bare `raise`**, which the ratchet accepts (executed on `17bbacd3`).

| Catch | In | Callee that now raises | What the catch does today | Non-import pin |
|---|---|---|---|---|
| `gcp/premarket_brief.py:606` | `load_earnings_for_brief` | `enrich_with_playability`, reaching `query_reaction_stats` (`:523`), `query_typical_daily_return` (`:582`), `get_earnings_calibration` (`:101`) | WARNING "playability enrichment skipped"; rows go unscored | pinned (item 8) |
| `gcp/premarket_brief.py:636` | `load_earnings_for_brief` | `get_earnings_calibration` (`:101`) | WARNING; `min_nq = 12` | pinned (item 8) |
| `gcp/premarket_brief.py:883` | `load_yesterday_amc_reactions` | `conditional_lean_summary`, reaching `query_conditional_reactions` (`:682`) | WARNING; the lean is omitted | pinned (item 8) |
| `gcp/premarket_brief.py:1383` | `generate_premarket_brief` | `load_yesterday_amc_reactions` (`:810`) | WARNING; the AMC section is omitted | pinned (item 8) |
| `gcp/premarket_brief.py:1685` | `generate_premarket_brief` | the try's own imports of `gcp.database` and `lib.strat_levels`, and `get_engine()` (no removed site) | ticker marked `PLAYBOOK_FAILED`; the run continues | pinned (item 8) |
| `gcp/premarket_brief.py:1713` | `generate_premarket_brief` | the playbook block holding `:1685`, once that re-raises (no removed site) | ticker marked `PLAYBOOK_FAILED`; the run continues | pinned (item 8) |
| `gcp/premarket_brief.py:2503` | `_build_earnings_embed` | `get_calibration_options_metrics` (`:425`) | `logger.exception`; `_BRIEF_CAL_OPTS = {}`, so the Q5 override is off | existing test |
| `lib/signals.py:316` | `evaluate_signal` | `_latest_overrides` (`exit_config_overrides.py:108`), `get_disabled_directions` | logged; `None`, no signal this bar (fail closed); the poll continues | existing test |
| `gcp/signal_monitor.py:1160` | `SignalMonitor._evaluate_strategies_for_bar` | `get_disabled_directions`, reaching `_latest_overrides` | counted and logged; `(None, None)` | existing tests |
| `gcp/signal_monitor.py:2057` | `SignalMonitor._resolve_brief_bias` | `get_premarket_bias` (`brief_bias.py:69`) | DEBUG log; `bias='UNAVAILABLE'`, so `ftfc_score = 0.0` (`:1302`) | existing test |
| `gcp/signal_monitor.py:700` | `SignalMonitor._update_leg_trackers` | `_resolve_brief_bias` (`:615`), once `:2057` re-raises | WARNING "leg-state update skipped"; the poll continues | pinned (item 8) |

These callers were traced and stay unchanged. Each was read on `17bbacd3` and again on `16b3fabd`:

- **The signal monitor's loop.** `SignalMonitor.run_loop` (`gcp/signal_monitor.py:2472-2518`) has no catch, and
  neither has the call to `evaluate_signal` (`:1112`) nor the one to `_evaluate_strategies_for_bar` (`:1257`).
  So an import error that leaves any of the monitor's catches ends the run.
- **The monitor's replay mode.** `gcp.signal_monitor.main` with `REPLAY_DATE` (`:2618-2670`) runs
  `scripts/replay_signal_monitor.py`. Its `replay_ticker` catches `Exception` around `evaluate_ticker` per bar
  (`:209`), logs a WARNING and goes on. That catch cannot see this spec's import errors alone:
  - replay `main` imports `gcp.database.get_engine` before any bar (`:765`), and `signal_monitor.main` imports
    `is_cloud_sql_configured` at `:2632`;
  - every guard this spec removes on that path imports `get_engine` from `gcp.database`.

  So an unimportable `gcp.database` ends the replay before the loop.
- **The live signals route.** `generate_signals` (`lib/signals.py:358`) has no ticker parameter, so
  `platform/api/routers/live.py:640` and `scripts/run_historical_signals.py:401` never read the override store.
- **The backtest engine.** `BacktestEngine.run` sets `_current_ticker` to its `ticker` argument
  (`lib/backtest.py:510`), and no caller passes one (for example `lib/walk_forward.py:358`,
  `scripts/run_backtest.py:218`), so it is `None` there. Only `replay_labeled_trades` sets a ticker
  (`lib/backtest.py:1258`), and its route has no catch.
- **The override defaults.** `_latest_overrides_or_default` (`exit_config_overrides.py:164-169`) catches only
  `OverridesUnavailable`.
- **The cache-hit job.** `render_existing_brief_to_discord` calls `fetch_premarket_analysis_row`
  (`premarket_brief.py:3611`) outside any try.

### AUDIT markers

CLAUDE.md §3.7 asks for an `AUDIT-2026-05-13` marker on a silent fallback beside a touched line. The table marks:

- every broad handler that a Caller catches row's new `except ImportError: raise` is placed ahead of, when what
  it carries on with is a value its caller cannot tell from a real result: nine of the eleven. The two
  playbook catches, `gcp/premarket_brief.py:1685` and `:1713`, get none. Each sets `status = 'PLAYBOOK_FAILED'`
  and `playbook_error` on the ticker, and `persist_to_cloud_sql` writes such a row to the history table only,
  a state a reader can tell from a real playbook (`test_playbook_failed_writes_to_history_only` and its two
  neighbours in `tests/gcp/test_premarket_brief.py` pass on `16b3fabd`, executed). Item 16 checks this rule
  against the Caller catches table, so a row added there cannot leave its handler unmarked;
- the three admin reads after the client handler this change edits;
- one inline fallback.

It does not mark swallows a few lines from an edited handler, such as `gcp/premarket_brief.py:267` and
`lib/earnings_reactions.py:107` and `:431`. Each marked handler keeps substituting for non-import failures. The
thirteenth is not a handler: a few lines below the imports this change edits in `_playability_lines`
(`gcp/premarket_brief.py:2433-2451`), `or 0` and `.get(..., 0)` at `:2456-2459` print a missing value as
"gap 0.0% · cons dir 0% · rev 0%". stocks#1047 already tracks that site.

Each handler gets a comment as the first line of its body, and the inline fallback a comment on the line above
it, in the shape of the existing markers (`lib/data_loader.py:766`): the marker tag, then what is substituted and
when it is reached (item 16).

| File | Handler | What it substitutes |
|---|---|---|
| `gcp/premarket_brief.py` | `:606` | rows left unscored (no playability) |
| `gcp/premarket_brief.py` | `:636` | `min_nq = 12`, unannounced |
| `gcp/premarket_brief.py` | `:883` | the lean omitted for every reporter |
| `gcp/premarket_brief.py` | `:1383` | the AMC-reaction section dropped |
| `gcp/premarket_brief.py` | `:2503` | `_BRIEF_CAL_OPTS = {}`, so the Q5 IC override is off |
| `lib/signals.py` | `:316` | `None` for the bar, the value a bar with no signal also returns |
| `gcp/signal_monitor.py` | `:1160` | `(None, None)` for the bar, as when nothing fires; counted in `kill_switch_failure_count` |
| `gcp/signal_monitor.py` | `:2057` | bias `UNAVAILABLE`, so `ftfc_score = 0.0` |
| `gcp/signal_monitor.py` | `:700` | the leg-state update skipped for any failure, not only a bad batch |
| `platform/api/routers/admin.py` | `:497-504` | no live ECE for any cell |
| `platform/api/routers/admin.py` | `:516-522` | a cell unavailable on any read error |
| `platform/api/routers/admin.py` | `:567-568` | a cell's version and date from `model.pkl` alone |
| `gcp/premarket_brief.py` | `_playability_lines`, `:2456-2459` | a missing move magnitude, direction consistency, reversal rate or quarter count printed as 0 |

### The ratchet (`tests/meta/test_no_import_fallbacks.py`)

The test parses every `.py` under `lib/`, `gcp/`, `platform/api/` and `scripts/` with `ast`. An imports-only
body below is one of import statements, beside which it may only assign constants (`HAVE_YAML = True`). The test
checks four kinds of guard:

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
4. **Kind 4:** a `try` or `try*`, whatever its handlers, whose `finally` holds a `return`, a `break` or
   `continue` that leaves the `finally` (not one belonging to a loop inside it), an `assert`, an exit call (as
   below) or a raise other than a bare one or one of an import type, while its own body holds an import
   statement or calls `__import__` or `import_module`, outside nested function, lambda and class bodies. Python
   discards or replaces an error in flight when such a `finally` runs: `try: import x` with `finally: return []`
   returns `[]` (executed, Codex's review of stocks#1424, finding 4). That covers a `try` with no handler and
   one whose handlers cannot catch an `ImportError` (`except ValueError`). A kind 4 guard is never accepted,
   and a `try` that is a kind 1 or 2 guard as well is reported as both.

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
- **No assertion inside it.** No `assert` appears in its body, by the same walk, alone or inside an `if`. An
  `assert` whose condition is false raises `AssertionError` in the import error's place, which a caller's
  `except ImportError: raise` cannot see (executed, Codex's review of stocks#1424, finding 1).
- **No exit from its own `finally`.** Its own try's `finally` holds no such early exit, no `assert`, and no raise
  other than a bare one or one of an import type, each of which would discard or replace the error. A bare
  `raise` in a `finally` re-raises the error in flight (executed, Python 3.11.18).
- **No earlier sibling takes the error.** No earlier handler of the same `try` can catch an `ImportError` while
  failing these same tests. A handler can catch one when its types include an import type, `Exception` or
  `BaseException`, when it is bare, or when its types do not all resolve to builtin exception names (a local or
  imported alias, an imported exception class). `except Exception: return []` followed by
  `except ImportError: raise` is refused: Python picks the first.
- **No enclosing swallow.** In the same function:
  - no handler of an enclosing `try` that is able to catch an `ImportError` (as above) fails these same tests,
    reading its handlers in order and stopping at the first that certainly catches one (an import type,
    `Exception`, `BaseException` or bare);
  - no enclosing `try` has a `finally` with an early exit, an `assert` or a raise of another type;
  - no enclosing `with` suppresses `ImportError`, `Exception` or `BaseException`.

On `17bbacd3` the rule accepts two handlers, `lib/features/fracdiff.py:172` and `gcp/database.py:191`. It finds
no kind-3 guard, no aliased or unresolvable type, and no constant-assigning imports-only body (executed: the
tightened rule finds the same 81 guards as the first draft's). On `16b3fabd` r4's inventory scan (Bases) finds
the same two accepted handlers and 75 guards not accepted (61 of kind 1, 14 of kind 2), no kind-3 or kind-4
guard, and no `assert` in either accepted handler or a `finally` around it, so r4's two additions find nothing
new on main.

**The tables.** A guard that is not accepted passes only if its (path, qualified function name) key is in one of
three dicts:

- `ALLOWED` (kind 1) holds the 16 Allowlist keys.
- `PART2` (kind 1) holds the 24 keys (25 guards) of the Part 2 table. Each reason cites the issue done_when
  item 13 files, and part 2 deletes the dict.
- `KNOWN_BROAD` (kinds 2 and 3) holds the 7 keys (14 guards) of the Broad guards table. Each reason cites the
  same issue.

No dict holds a kind 4 guard: there is none on `16b3fabd`, and a new one fails the scan.

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
guard, the `with` line; for a kind 4 guard, the `finally` statement that exits, asserts or raises).

- `_handler_returns` comes from `scripts/audit_silent_fallbacks.py`, loaded with `importlib` as `_scanner()` in
  `tests/lib/test_silent_fallback_fixes.py` does. It names nothing for 7 of the 20 removed handlers (executed on
  `16b3fabd`).
- A pin mismatch fails as `path qualname: found <guards>; listed <guards>`.

Executed on 2026-10-12, on r3's rule and tables. r4's two additions (no `assert`, kind 4) and the counts that
moved with main were not run on that draft, which is not in this workspace: items 1 to 4 hold the
implementation to them, and the inventory scan above gives the counts on `16b3fabd`.

- **On `d0231901`** (the code of `17bbacd3`), a draft of exactly r3's rule, with r3's tables:
  - passes its 93 self-tests (61 refused shapes, 19 accepted, 13 table and helper tests);
  - fails the class test listing the 21 handlers in r3's Sites removed table and no other, with no pin
    mismatch;
  - finds 67 kind-1 guards unaccepted (21 + 21 + 25) and 14 of kind 2.
- **On a scratch tree holding r3's changes,** it passes 94 of 94. It accepts the 14 new caller-catch
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

- **Handler shape (done_when item 5).** The ratchet's test file keeps the 11 Caller catches rows as data, each
  found by its path, its qualified function name and a callee (`enrich_with_playability`,
  `get_earnings_calibration`, `conditional_lean_summary`, `load_yesterday_amc_reactions`, `persist_level_map`,
  `build_level_map`, `get_calibration_options_metrics`, `get_disabled_directions` twice, `get_premarket_bias`,
  `_resolve_brief_bias`), not by line. The row's try is the one try in the function whose own body, outside
  nested try statements and nested function, lambda and class bodies, calls the callee; a row that matches no
  try or more than one fails. That keeps `:1685` apart from `:1713`: both tries reach `persist_level_map`, but
  only try@1636 calls it in its own body (try@1425 holds it inside try@1636). For each row the check reads the
  first handler of the try able to catch an `ImportError` (a type that includes `ImportError`, a subclass of it,
  `Exception` or `BaseException`, a bare `except`, or a type that does not resolve to a builtin exception, such
  as the imported `StaleSourceDataError`) and requires its type to be the bare name `ImportError` and its body to
  end in a bare `raise`.
  - Executed on 2026-11-09 with a model of this check (scratchpad, not the plan's test): on `16b3fabd` each of
    the 11 rows matches exactly one try (`:1685` try@1636, `:1713` try@1425) and fails, its first catching
    handler being the broad one, or `StaleSourceDataError@1676` at `:1685`. On copies of the three files with the
    Design's handlers inserted, all 11 pass, `:1685` with handlers `ImportError`, `StaleSourceDataError`,
    `Exception`. With the `:1685` handlers swapped it fails (first catching handler `StaleSourceDataError`), and
    on a one-row snippet it fails `except ModuleNotFoundError: raise`, `except (ImportError, TypeError): raise`
    and `except builtins.ImportError: raise`. On the reviewer's model of the `:1685` try, the Design order passes
    and raises `ModuleNotFoundError`, and the swapped order fails and returns normally.
- **Helpers (done_when item 6).** Each test blocks the import and asserts `pytest.raises(ImportError)` in
  the test file of the module's own area.
  - `monkeypatch.setitem(sys.modules, 'gcp.database', None)` reaches every `from gcp.database import X`, even
    after `gcp.database` is imported.
  - `_playability_lines:2450` is reached only when `:2435` imports, so its test removes just
    `DEFAULT_LOOKBACK_QUARTERS` from `lib.earnings_reactions`, and `from ... import` then raises.
  - Three of the functions are cached. `_latest_overrides` is `@lru_cache(maxsize=64)`
    (`exit_config_overrides.py:86`), `get_earnings_calibration` is `@lru_cache(maxsize=1)`
    (`earnings_reactions.py:84`), and `get_premarket_bias` is `@lru_cache(maxsize=128)` (`brief_bias.py:45`).
    After an earlier call each returns its cached value instead of raising, so each test clears the cache.
- **Catches (done_when item 8).** Each row's first test makes its callee raise a plain `ImportError`, the class
  a missing name raises, and asserts that it leaves the function holding the catch; `except ImportError` catches
  it, and `except ModuleNotFoundError` would not. Each pinned row's second test makes the callee raise
  `RuntimeError` and asserts the logged line and the carried-on result: the scored rows, `min_nq` defaulting,
  the reactions without a lean, the brief without its AMC section, and `None` from `_update_leg_trackers`. The
  two playbook pins assert the failing ticker's status and error, and the other tickers' run (Caller catches).
- **Entry points (done_when items 7, 9 and 10).** Each row drives its entry point as the row says. In every test
  above, the module under test is imported before the import is blocked.

Each behaviour item fails against a named broken implementation. Executed on 2026-10-12 on scratch copies of
`17bbacd3` with r3's tests, except where marked; r3's line numbers are given as the `16b3fabd` lines of the same
statements:

- **origin/main's code,** with every handler in place and every catch unfixed, fails each test of items 6,
  9 and 10, item 8's first tests, and item 7's three error cases. The pins item 11 names pass there. Item 5
  fails there too, since no row has the handler it reads (follows from the check; not executed).
- **An unfixed catch** fails its item 8 first test. Those tests stub the callee, so they are indifferent to the
  handler.
- **A catch that re-raises every exception** fails item 8's second tests (7 failed on `17bbacd3`, five of them
  rows that remain on `16b3fabd`), and widening the new `:1685` or `:1713` handler to `except Exception` fails
  its playbook pin (1 failed each).
- **`except ModuleNotFoundError: raise` at a row** fails its item 8 first test, whose plain `ImportError` it
  lets through to the broad handler, and item 5. **`except (ImportError, TypeError): raise`** fails item 5. The
  Python behaviour under each was executed as a snippet on 2026-11-09 (Codex's review of stocks#1424, finding
  3); the tests themselves are the plan's.
- **The `:1685` handlers swapped** (`except StaleSourceDataError` first) fail item 8's `get_engine` test (1 failed;
  origin/main fails it too).
- **A `RuntimeError` raised in place of the import error at a removed site** fails that site's item 6 test, which
  asserts `ImportError`. Executed on `17bbacd3` at `_trading_days_between`, where it failed r3's item 5 and the
  calendar row of item 9 (2 failed); both left with stocks#1546.
- **stocks#1386's admin shape,** `except Exception` answering 503 at the client and a 503 for the import, fails
  item 7's defect and import cases (2 failed).
- **A 503 for an import error at a route** fails item 10, whose tests assert `== 500` (not executed; it follows
  from the assertion).

### Entry points

Each job and route that one of this spec's handlers reaches is driven end to end, with sockets refused and the
stubs its row names.

Some modules import `gcp.database` unguarded at module scope or in `main` (`gcp/signal_monitor.py:2632`,
`gcp/refresh_earnings_views.py:46`), and blocking the whole module fails those rows on both trees. So those rows
remove the one name only the removed site imports, or block the module after import.

A row passes only when the `ImportError` traceback passes through the function in its Reaches column. Every row
was executed on `17bbacd3` and on a scratch copy of it holding this spec's changes. On `16b3fabd` r4 re-ran the
first row's origin/main side through `generate_premarket_brief` with `gcp.database` blocked after import: it
returns normally, and `load_earnings_for_brief` returns no earnings (executed). r4 did not re-run the other
rows; item 9's tests run each against origin/main's code. Two r3 rows are gone (What main changed since r3,
fact C): the calendar row, since main's brief now raises `ModuleNotFoundError` in `compute_strat_status` before
it reaches `_trading_days_between`, and the insight-pipeline row, which no removed site reaches.

| Entry point | Reaches | Import made to fail; stubs | origin/main | PR head |
|---|---|---|---|---|
| `gcp.premarket_brief.main(['--no-discord'])`, job premarket-brief | `load_earnings_for_brief` | `gcp.database` blocked after import; `BRIEF_AS_OF` a weekday; `DataLoader.load_daily` returns a fixture with a `Time` column | returns normally | `ModuleNotFoundError` through `load_earnings_for_brief` |
| `gcp.premarket_brief.main(['--post-existing', 'SPY', '2026-10-08'])`, the `/replay` cache-hit job | `fetch_premarket_analysis_row` | `gcp.database` blocked after import; `DISCORD_WEBHOOK_URL` set | `SystemExit(1)` after logging "no row" | `ModuleNotFoundError` through `fetch_premarket_analysis_row` |
| `gcp.signal_monitor.main()` in loop mode, one poll, job signal-monitor | `_persist_signal_alert` | `gcp.database.upsert_dataframe` removed and `is_cloud_sql_configured` true; `ALPHA_VANTAGE_API_KEY` set; watchlist `['SPY']`; a fixture bar window for the fetch and the indicators; the ORB, exit and level-map steps stubbed; the strategy step returns a CALL fire, and `fire_alert` runs | the poll completes; the fire is never persisted | `ImportError` through `_persist_signal_alert` |
| `gcp.refresh_earnings_views.main(['--mode', 'daily'])`, job refresh-earnings-views | `get_calibration_options_metrics` | `gcp.database` blocked after import; module-level `is_cloud_sql_configured` true, and `query_to_dataframe`, `execute_sql` and `upsert_dataframe` stubbed with one upcoming reporter | returns 0 (returns 1 without the `is_cloud_sql_configured` stub, on both trees) | `ModuleNotFoundError` through `get_calibration_options_metrics` |
| `GET /api/admin/strat-engine/state` | `_strat_engine_state_cells` | `google.cloud.storage` blocked; or `Client()` raising `DefaultCredentialsError`; or `Client()` raising `TypeError` | 200 with `cells: []` for each | 500; 503; 500 |
| `GET /api/catalysts/events?refresh=true`, `GET /api/catalysts/ticker/{ticker}` | `_fetch_live_events` | `BENZINGA_API_KEY` set; `scripts.fetch_catalyst_calendar` and `fetch_catalyst_calendar` blocked; a cached event file | 200; the events route labels its cache "Benzinga" | 500 |
| `POST /api/backtest/replay-trades` | `_latest_overrides`, through `get_call_target` (`lib/backtest.py:890`) | `gcp.database` blocked; journal query and bar loader stubbed as `tests/lib/test_replay_labeled_trades.py` does; `TestClient(app, raise_server_exceptions=False)` | 200 | 500 |

Two groups of catches have no entry-point row: the kill-switch catches (`lib/signals.py:316`,
`gcp/signal_monitor.py:1160`) and the brief-bias catches (`gcp/signal_monitor.py:2057`, `:700`). Done_when items
6 and 8 pin them instead. Both imports they guard are `from gcp.database import get_engine, ...`, and a monitor
run cannot isolate them. Executed on both trees of `17bbacd3`:

- with `get_engine` removed, a poll already raises earlier, at the unguarded import in
  `lib/strategies/calibration.py:71`;
- with all of `gcp.database` blocked, `main` raises at `:2624` (`:2632` on `16b3fabd`).

### Generated and model documents

**The generated documents (REQ-GOV-004).** `docs/product/infrastructure/05-a-ARCHITECTURE.md`,
`05-c-DATA_DEPENDENCIES.md` and `05-e-API.md` cite lines in 7 of the 8 source files this change edits, all but
`lib/signals.py` (grep on `16b3fabd`). REQ-GOV-004 (`docs/product/01-PRODUCT-REQUIREMENTS.md:31`) says their
blocks SHALL equal a fresh render on main, and that a PR which changes what they cite SHALL carry the re-rendered
blocks, the whole document equal to the renderer's output from main's prose and the PR's committed sources.
`tests/scripts/test_check_generated_docs.py` enforces the render in the lean Run Tests job.

r3 waited on stocks#1383 for the gate to accept those documents on a feature branch. stocks#1383 was closed
unmerged on 2026-10-14, and the allowance reached main through stocks#1538 (`a5749d4c`). On `16b3fabd`,
`check_product_scope` hands each changed generated document to `generated_doc_refusals`
(`scripts/gate/spec_gate.py:4257`), which re-renders it in a fenced child process from main's prose and the
pull request's committed tree and refuses it when any byte differs, block or renderer-owned count alike. So:

- the implementation PR waits on nothing outside it (item 14);
- the plan's re-render task, after the last code change, runs `python -m scripts.maintenance.doc_inventory --snapshot
  tests/fixtures/live_gcp_snapshot_2026-09-07.json --insert` with the three documents' paths, as the monthly
  refresh workflow does (`refresh-architecture-docs.yml:491`), and commits the result. `--insert` renders with
  the same counts setting as the gate's child (`insert_blocks(..., counts=True)`, read on `16b3fabd`). Run with no
  paths, it renders only 05-a and 05-c (`scripts/maintenance/doc_inventory.py:4419-4420`);
- the documents' prose outside the blocks holds no citation the change moves. Executed on `17bbacd3`: 2
  citations into the changed files, in 05-a, neither moved. stocks#1372 covers the prose of these three
  documents.

Executed on r3's scratch implementation of `17bbacd3` with the markers in, which then edited 12 source files:

- **Before the re-render,** the two docs-test files gave 3 failed and 205 passed, the three tests named in Why
  this re-cut. Main gave 208 passed.
- **The render** updated all three documents, 52 rows, every changed line inside a block (05-a 13, 05-c 26,
  05-e 13). A second run reported all three unchanged.
- **After it,** the same files gave 208 passed.
- **The gate of stocks#1383.** The second pre-review committed the r3b change onto a scratch clone at stocks#1383's
  head `f552ec59` and ran its `check_product_scope("FEAT-OPS-001", ...)`: `[]`. Rerun on a commit of r3's change
  in a separate clone: see Product documents. Main's gate of stocks#1538 was not run on an implementation here;
  item 14 holds the PR to it in CI.

**The model documents.** `docs/models/` lies outside `docs/product/`, so the gate lets this PR change it. Every
pointer in `docs/models/MODEL-*.md` into a changed file is re-pointed to the same statement (item 15): `path:line`,
symbol-anchored (`` `sym` (`:N`) ``) and bare `:N` whose file the same row, sentence or paragraph names.

`tests/meta/test_model_registry_consistency.py` cannot hold that. Its symbol check allows 3 lines of slack, its
explicit-path check is bounds-only, and its docstring counts 93 bare ranges it cannot gate. So item 15 asks for a
statement check, in the PR body:

- every explicit pointer resolves by its path, or a base name unique in the repository;
- every bare pointer the change could move is resolved to its file by reading, in a list the plan keeps beside
  the check. On `17bbacd3`, 119 candidates were read for the 12 files r3 changed (each bare `:N` in a document
  that names a changed file, and that would move if it pointed there): 35 resolve into a changed file, and the
  rest name other files, such as `gcp/refresh_earnings_views.py`, `gcp/earnings_reactions_brief.py`,
  `lib/strategies/calibration.py` and `scripts/backtest_playability.py`;
- each pointer's origin/main line is mapped to the head through the diff, and the check compares the statement
  the head pointer names with the one origin/main's names.

Executed on 2026-10-12 on `17bbacd3` with r3's 12 files, 70 pointers (35 explicit, 35 bare); the PR head
re-runs the check over the 8 files this change edits (item 15):

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
spec names (`check_registry_rows`): of the 11 lines whose citations moved on r3's scratch head, only `:490`
(MODEL-MR-001) is one.

**Ruling.** This PR corrects 07 `:490` and regenerates `docs/product/generated/model-registry.json`, whose
`--check` fails otherwise (executed). Every other line below is corrected, and 03 is re-stamped, on the
close-out's after-merge `docs/` branch, the one step `SKILL.md` places after the merge (Phase 5 step 7): stocks'
for 03 and 07, solyra's for UI-SCREENS. That branch is cut from main, not from this branch, so nothing stacks.
done_when cannot hold the edit itself, because CI requires every box ticked before the merge. So item 17 puts this
table in the PR body, where review sees the replacement text before the merge.

The ruling rests on these runs:

- **The gate, against an edit of `:1120`.** On `feature/feat-ops-001-no-import-fallbacks`, `17bbacd3`'s
  `check_product_scope` answered "docs/product/03-SITE-TRACEABILITY.md changes in this feature change; under
  docs/product/ only the FEAT's own catalog and traceability records, the model registry and its generated files
  may change here". On `docs/ops-001-admin-state-traceability` it answered no errors. On `16b3fabd` the same
  refusal also names the re-rendered inventory blocks among what may change
  (`scripts/gate/spec_gate.py:4325-4329`, read); 03 is still not among them.
- **stocks#1383's gate, on r3's change.** In a separate clone, r3's change was committed over a scratch commit of
  this spec and plan on stocks#1383's head `f552ec59`. Its `check_product_scope("FEAT-OPS-001", ...)` returned
  `[]` (121.6 s; the re-rendered blocks, `docs/models/`, 07 `:490` and the registry JSON included), and
  `check_registry_rows` returned `[]`. With 07 `:299` also re-pointed, `check_registry_rows` answered
  "docs/product/07-MODEL-REGISTRY.md: changes '`get_call_rsi_range` / ...', a line naming none of
  docs/superpowers/specs/2026-10-11-feat-ops-001-no-import-fallbacks.md's models".
- **The docs audit, on a commit of r3's change over `d0231901`** in a separate clone, with the re-rendered
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
| 03, every citation into the changed files | measured on r3's scratch implementation of `17bbacd3`, then 12 changed files: 353 citations (each link's `file:line` text and `#L` anchor, and bare `file:line` prose), 254 moved and 6 inside a changed hunk, on 53 lines (`:131` to `:1280`); of them the `../../<path>#L<n>` anchors are 134, 95 moved, 2 inside a hunk and 37 unchanged | each re-pointed to the same statement on the merged code |
| solyra `docs/UI-SCREENS.md:11397`, Admin purpose | "a storage outage reads as an empty shelf" | a storage outage of the state's client reads as the panel's error line; a failed read of a cell still reads as `no artifact` |
| solyra `:11416` | "a storage outage reads as no cells" | a storage outage answers 503 and the panel shows `Model state unavailable:` |
| solyra `:11446`, ADMIN-10 | "`0 / 0 models trained` in the state, which is also how a storage outage reads" | that empty state no longer comes from this route; an outage is ADMIN-11's error line |
| solyra `:11675-11676` | "a state answer with no cells reads `0 / 0 models trained` ..., which is how a storage outage reaches the page" | an outage reaches the page as `Model state unavailable: state 503` |
| solyra `:11688-11689` | "Given the brief and state routes with the storage client failing, then each answers 200 and the page shows an unavailable brief and an empty state" | the brief answers 200 with unavailable cells; the state answers 503 and the panel shows its error line |
| solyra `:11696-11697` | the sweep pins "the brief and state routes at 200 with the storage client failing, which is the swallowed read" | the brief at 200 and the state at 503 |
| solyra `:12147-12150` | "That is how a storage outage reaches the page: `_strat_engine_state_cells` returns no cells when the storage client cannot be built (`admin.py:486-495`, executed: 200 ...)" | the empty-answer reading stays for an empty answer; a client that cannot be built answers 503 or 500; the per-cell clause stays |
| solyra `:12157-12158` | "a storage outage reads as an empty shelf" | a storage outage of the client reads as an error; a failed read of a cell still reads as `no artifact` |
| solyra `:12167-12168` | "Given the storage client failing, then the brief and the state routes answer 200 ... and the page reads as above" | the brief answers 200; the state answers 503, and the panel shows its error line |
| solyra `:12170-12171` | stocks' sweep "pins ... `GET /api/admin/strat-engine/state` at 200 with the storage client failing, which is the swallowed read" | pins it at 503 |
| 07 `:490`, DOC-23 (MODEL-MR-001) | `gcp/signal_monitor.py:1107`, `lib/signals.py:311-344`; on `16b3fabd` the `evaluate_signal` call it names is at `:1112` | each statement's line on the PR head, in this PR, with the registry JSON regenerated (r3's scratch head of `17bbacd3` read `:1110` and `:311-346`) |
| 07, the other moved lines (`:299`, `:371`, `:489`, `:505`, `:506`, `:517`, `:518`, `:522`, `:579`, `:581`) | on r3's scratch head, 27 citations into the changed files on 11 lines, 16 moved, none inside a changed hunk (`:490` included) | each re-pointed on the stocks `docs/` branch; the gate refuses them here, as above |
| solyra, every stocks citation into the changed files | measured on r3's scratch implementation of `17bbacd3`: 141 citations (`admin.py:1391`-style text and stocks blob links), 85 moved and 2 inside a changed hunk, on 45 lines | each re-pointed on the same solyra `docs/` branch |

Line numbers are 03 and 07 at `16b3fabd`, where each named line holds the text it held at `17bbacd3` (mapped
through the diff and compared), and solyra `docs/UI-SCREENS.md` at solyra `origin/main` `a656114` as this
workspace holds it, where each named line holds its `5fbdbb9` text 9 lines higher. Counts are re-measured on the
PR head (item 17). r3's rows for 03 `:755` and `:798` and solyra `:9838` are dropped: they described
`lib/agents/orchestrator.py` and `lib/agents/trade_planner.py`, which this change no longer edits (What main
changed since r3, fact C).

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
- **Citations already stale on main.** `CLAUDE.md:503` (`gcp/premarket_brief.py:617`),
  `docs/STRAT_METHODOLOGY.md:464` and `:470`, `docs/premarket_brief_cards.md:20` and
  `.claude/commands/resolve-issue.md:3742` and `:3779` name other statements than the ones they describe (read on
  `d0231901`, and again on `16b3fabd`, where these are their lines). Re-pointing them through the diff would keep
  them wrong, so they are left.

### Environment

The four `test_strat_levels_freshness.py` failures r1 met came from this sandbox lacking the library, which CI
installs (`requirements.txt:90`). Executed on `17bbacd3` with the library blocked:

- origin/main gave 4 failed and 9 passed;
- with the handler removed, 10 failed and 3 passed, all 10 with `ModuleNotFoundError` instead of a wrong count;
- with the library installed, both gave 13 passed.

On `16b3fabd`, after stocks#1546, the file holds 14 tests: with the library blocked 12 fail, all with
`ModuleNotFoundError`, and with it all 14 pass (executed). This change does not touch that file.

The full suite stalls in `tests/lib/test_combo_mining.py` when two runs share the machine's threads. It finishes
with `OMP_NUM_THREADS=1`, which the plan sets.

Capacity: with the import present, no job reads or writes more rows, makes more calls or runs longer, because each
function runs the same statements (CLAUDE.md rule 0.2). In a broken image a job that took a fallback now ends
early, and none is run again for it: the jobs a removed site reaches (Entry points), premarket-brief,
signal-monitor and refresh-earnings-views, are created with `--max-retries 0`, which their updates restate or
leave as it is (`gcp/deploy.sh:1384` and `:1393`, `:1469`, `:3065` and `:3075`, read on `16b3fabd`; the live
jobs read `0` on 2026-10-12, executed then and not re-read here). r3 counted one extra run of insight-pipeline
(`--max-retries 1`) for each failing ticker; no removed site reaches that job on `16b3fabd` (What main changed
since r3, fact C), so that cost is gone.

- Volume: 0 more rows; a run that ends early writes fewer.
- Velocity: 0 more queries or calls; no retry repeats a failing run.
- Wall-clock: 0 s more; a failing run ends sooner than one that carried on with a fallback.
- $/run x runs/day x 30: $0 more.

The retry policy is each job's own and is not changed here. Rule 0.3's evidence beyond the hermetic tests is
done_when item 9: each job's own `main` driven end to end.

### Sites removed (20 handlers in 18 functions)

Lines in this table and the three below are at `16b3fabd`, from the inventory scan in Bases; the ratchet pins
functions and guards, not lines. r3's `lib/strat_levels.py::_trading_days_between` row is gone (What main
changed since r3, fact B).
Severity is the audit's:

- H changes an alert, a recommendation or a risk control;
- M is a silent job no-op or a hidden section;
- L is wasted work, a hidden cause, or a branch dead in a healthy image.

| Path | Function | Lines | Handlers | Reason (what it substitutes today) |
|---|---|---|---|---|
| `gcp/premarket_brief.py` | `_delete_null_close_rows` | 252 | 1 | L: `0`; cleanup skipped, no log |
| `gcp/premarket_brief.py` | `load_earnings_for_brief` | 327 | 1 | H: empty earnings; the brief says "No earnings scheduled" |
| `gcp/premarket_brief.py` | `load_yesterday_amc_reactions` | 810 | 1 | M: `[]`; the AMC-reaction section is omitted |
| `gcp/premarket_brief.py` | `load_economic_events` | 895 | 1 | H: empty events; "No major events today" and a 5m ORB window |
| `gcp/premarket_brief.py` | `_playability_lines` | 2435, 2450 | 2 | L: stub copies of `lib.earnings_reactions` helpers (blank hint, fixed 12Q lookback) |
| `gcp/premarket_brief.py` | `persist_to_cloud_sql` | 3316 | 1 | M: `0`; `premarket_analysis` never written |
| `gcp/premarket_brief.py` | `fetch_premarket_analysis_row` | 3565 | 1 | M: `None`; the `/replay` cache-hit job logs "no row" and exits 1, hiding the cause |
| `gcp/signal_monitor.py` | `SignalMonitor._persist_signal_alert` | 1655 | 1 | H: returns after the Discord post; the fire never reaches `signal_alerts` |
| `gcp/signal_monitor.py` | `SignalMonitor._persist_exit` | 2408 | 1 | H: returns after the exit alert; the exit is never recorded |
| `lib/earnings_reactions.py` | `get_earnings_calibration` | 101 | 1 | M: Tier-B env defaults with no tier flag, no log |
| `lib/earnings_reactions.py` | `get_calibration_options_metrics` | 425 | 1 | H: `{}`; the Q5 IC override is silently off |
| `lib/earnings_reactions.py` | `query_reaction_stats` | 523 | 1 | M: `{}`; playability vanishes for every ticker |
| `lib/earnings_reactions.py` | `query_typical_daily_return` | 582 | 1 | M: `{}`, no log |
| `lib/earnings_reactions.py` | `query_conditional_reactions` | 682 | 1 | M: `{}`; only the docstring discloses it |
| `lib/strategies/exit_config_overrides.py` | `_latest_overrides` | 108 | 1 | H: `None` ("no row"); the direction kill switch fails open |
| `lib/strategies/brief_bias.py` | `get_premarket_bias` | 69 | 1 | H: `bias='UNAVAILABLE'`; the monitor scores `ftfc_score = 0.0`, so counter-FTFC fires escape the penalty |
| `platform/api/routers/admin.py` | `_strat_engine_state_cells` | 486 | 1 | UNSURE: `cells: []` with HTTP 200; the import goes uncaught and the client handler beneath classifies (Design) |
| `platform/api/routers/catalysts.py` | `_fetch_live_events` | 146, 150 | 2 | M: `None` plus ERROR; the cache is served labelled "Benzinga" |

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
| `scripts/fetch_earnings_calendar.py` | `_load_existing_options_from_db` | 348 | `gcp.database` |
| `scripts/fetch_earnings_calendar.py` | `_fetch_yahoo_bulk` | 834 | `yfinance` |
| `scripts/fetch_earnings_calendar.py` | `fetch_yahoo_earnings` | 1083 | `yfinance` |
| `scripts/fetch_earnings_calendar.py` | `persist_to_cloud_sql` | 1107 | `gcp.database` |

### Allowlist (16 keys, 16 handlers)

Each key pins one guard. Each reason gives the evidence for why the handler is not a production path that must
fail loud. Five of the rows guard an internal module: `options_greeks:186`, `options_intraday:160` and `:588`,
`options_pnl_translation:253`, and `premarket_brief:1891`. One ends in a raise of another type, and its callers
were traced: `health:134`. r3's five calendar rows are gone, the guards removed by stocks#1546 (Non-goals):
`fetch_av_historical_options.py::_trading_days`, `evaluation_windows.py::last_expected_session` and
`::expected_session_bars`, and the `<module>` guards of `scripts/fetch_alphavantage_intraday.py` and
`scripts/fetch_alphavantage_options.py`.

| Path | Function | Line | Guards | Reason |
|---|---|---|---|---|
| `gcp/fetchers/fetch_rss_news.py` | `main` | 726 | `dotenv` | optional dotenv; Cloud Run supplies the environment; no data effect |
| `gcp/indicator_correlation_job.py` | `_class_mutual_info` | 217 | `sklearn.feature_selection` | `mutual_info` is `None`/NULL, never 0 |
| `gcp/insight_tasks.py` | `enqueue_insight_task` | 148 | `google.api_core`, `google.cloud` | returns `EnqueueOutcome.NOT_ENQUEUED` plus ERROR, and each of its three callers acts on it. The insight job runs the ticker in-process and logs the count (`gcp/insight_pipeline_job.py:619-644`). `gcp/auto_refresh_top_n.py:294-313` marks the run failed. The insights route runs it in-process with BackgroundTasks (`platform/api/routers/insights.py:876-882`). The API image installs no `google-cloud-tasks` (`platform/Dockerfile:24-37`, `platform/api/requirements.txt`), so the route always takes the in-process path; whether that is intended is not checked here |
| `gcp/premarket_brief.py` | `empirical_fallback_footer` | 1891 | `lib.options_intraday` | internal module, but the substitute is the imported constant's own value (`lib/options_intraday.py:100`), so no caller can observe the difference |
| `gcp/queries/run_query.py` | `main` | 412 | none (a tuple handler around work) | writes a `system_error` result row and exits 1 |
| `lib/options_greeks.py` | `get_rate_and_yield` | 186 | `gcp.database` | internal module, but never a value in production: it raises `RateLookupError` naming the import failure ("gcp.database unavailable (...)") unless `allow_defaults=True`, which no caller passes (only `lib/options_greeks.py` itself names it) |
| `lib/options_intraday.py` | `load_realtime_theta_curve` | 160 | `gcp.database` | internal module, but no production caller: only `lib/options_intraday.py` itself and `scripts/analysis/` call it, and nothing under `gcp/` or `platform/api/` imports the module's functions; the curve is stamped `data_source='empirical_fallback'` |
| `lib/options_intraday.py` | `_load_intraday_bars` | 588 | `gcp.database` | internal module, but no production caller (as `:160`); the caller WARNs and returns a typed empty timeline |
| `platform/api/main.py` | `_strat_engine_state` | 374 | `google.cloud` | `[]` renders the `/dev` line "strat-engine artifact state unavailable" followed by "GCS unreachable" (`main.py:505-506`), so a missing `google.cloud.storage`, which this spec treats as a defect in `admin.py`, shows as a storage outage there; the item 13 issue names that misattributed cause. Listed because no data value reaches a caller, only the dev page's HTML, and `main.py` is left to FEAT-DEPLOY-001's open stocks#1384 |
| `platform/api/routers/health.py` | `_run_audit_and_cache` | 134 | `audit_data_freshness` | answers HTTP 500 at the route boundary, the status `lib/infra_errors.py` gives a defect; no value reaches a caller |
| `platform/api/routers/insights.py` | `_stream_gemini` | 1053 | `google.genai` | streams the explicit error text to the user; no data produced |
| `scripts/analysis/options_pnl_translation.py` | `load_realtime_marks` | 253 | `gcp.database` | internal module, but an analysis CLI that no job or workflow runs (no reference in `gcp/deploy.sh` or `.github/workflows/`); every row stamped `data_source='empirical_fallback'` |
| `scripts/analysis/phase4_setup_discovery.py` | `run_decision_tree_analysis` | 381 | `sklearn.ensemble`, `sklearn.tree` | the report prints "sklearn not available, using rule-based analysis instead" |
| `scripts/fetch_earnings_calendar.py` | `_fetch_yahoo_one` | 958 | `yfinance` | no production caller: only tests call it (no reference in `lib/`, `gcp/`, `platform/api/` or `scripts/`) |
| `scripts/gate/spec_gate.py` | `valid_yaml` | 837 | `yaml` | returns the reason string; its one caller (`:2090-2091`) returns it as a refusal, so the gate fails closed |
| `scripts/validation/validate_brief_accuracy.py` | `_connect` | 252 | `google.cloud.sql.connector`, `pg8000.dbapi` | guards the external Cloud SQL Connector and falls through to a direct connection to the same database; any failure raises |

### Broad guards (7 keys, 14 handlers)

Pinned in `KNOWN_BROAD`, not fixed here; the issue in done_when item 13 lists them.

| Path | Function | Lines | Handlers | Guards | Substitutes |
|---|---|---|---|---|---|
| `lib/gamma.py` | `compute_gamma_flip_bs` | 722 | 1 | `lib.options_greeks`, `scipy.stats` | `None` plus WARNING |
| `lib/infra_errors.py` | `<module>` | 196, 200, 204, 208, 212, 216, 220 | 7 | `psycopg2`, `pg8000.exceptions`, `aiohttp`, `google.auth`, `requests`, `urllib3`, `google.api_core` | each alias bound to `None` |
| `lib/infra_errors.py` | `_storage_response_types` | 643 | 1 | `__import__` of a variable name (`<dynamic>`): `google.cloud.storage.exceptions`, `google.resumable_media` | `pass`; the type is left out of `_STORAGE_RESPONSE_TYPES` |
| `platform/api/routers/catalysts.py` | `_db_catalyst_events` | 360 | 1 | `gcp.database` | `[]` plus WARNING |
| `platform/api/routers/dashboard.py` | `<module>` | 47, 54 | 2 | `platform.api.routers.live`, then `api.routers.live` | `:47` retries; `:54` sets three names to `None` (on `17bbacd3` also `MARKET_HOLIDAYS_2026 = set()`) |
| `scripts/backfill_watchlist_data.py` | `_scalar` | 85 | 1 | `gcp.database` | `None` plus WARNING |
| `scripts/backfill_watchlist_data.py` | `backfill_daily` | 189 | 1 | `requests`, `pandas`, `gcp.database`, `gcp.fetchers.fetch_market_data` | `False` plus WARNING |

## Risks

- **The generated documents must equal main's render exactly.** Without the re-rendered blocks the lean Run
  Tests job fails `test_check_generated_docs.py` (executed on `17bbacd3`), and with a hand-edited one main's gate
  refuses the document (stocks#1538). r3's wait on stocks#1383 is gone: it closed unmerged and stocks#1538 landed
  the allowance (What main changed since r3, fact A). What remains is order: a code change after the re-render
  moves cited lines again, so the plan re-renders after the last code change, and item 14 checks the head.
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
  around such a body, or `suppress` reached through a variable or given `*_E`. Nor does it see a statement in an
  accepted handler that raises by accident, such as a failing log call or a `KeyError` while setting a status,
  which would also replace the import error: the rule refuses the constructs whose purpose is to raise, assert
  or exit, not every expression that can fail. Review catches those.
- **The database layer's own ImportError is still swallowed on most of these paths.** `gcp/database.py:191`
  raises `ImportError` from inside `get_engine()` when `cloud-sql-python-connector` cannot be imported. Two broad
  handlers around work catch it before any site this spec fixes can:
  - `query_to_dataframe`'s `except Exception` (`gcp/database.py:239-241`) logs a WARNING and returns an empty
    frame;
  - `get_premarket_bias`' query `try` (`lib/strategies/brief_bias.py:93-96`) returns `_unavailable('query_failed')`.

  Executed on 2026-10-12 with the connector made unimportable, Cloud SQL variables set and sockets refused (the
  second pre-review's `connector_probe.py`), with the same output on `17bbacd3` and on r3's change; not re-run on
  `16b3fabd`, where `gcp/database.py` and `lib/strategies/brief_bias.py` are unchanged:
  `fetch_premarket_analysis_row` returned `None` (the `/replay` "no row" symptom), `load_earnings_for_brief`
  returned no earnings ("No earnings scheduled"), `load_yesterday_amc_reactions` returned `[]`,
  `get_earnings_calibration` returned the Tier B defaults, `get_calibration_options_metrics` and
  `query_reaction_stats` returned `{}` (the Q5 override off, no playability), `get_premarket_bias` returned
  `UNAVAILABLE` with reason `query_failed` (the FTFC penalty off), and `get_disabled_directions` raised
  `OverridesUnavailable` (the kill switch fails closed; the exit-target getters use Tier B with a WARNING).
  - So this change makes a missing `gcp.database`, `google.cloud.storage` or fetcher module fail loud (no
    import guard of `pandas_market_calendars` is left on `16b3fabd` after stocks#1546, Bases), but not a missing
    Cloud SQL connector below `gcp.database`, except where a fixed catch's own try calls `get_engine()`: the
    brief's playbook persist at `:1685` (Caller catches). The brief job already fails on a missing connector on
    `16b3fabd`: `main()` reaches `persist_to_cloud_sql`, whose `bulk_insert_dataframe` calls `get_engine()`
    unguarded, and that raised `ImportError` (executed with the connector blocked) before any row is written or
    any Discord post is sent. So at `:1685` this change moves that failure earlier, to the first ticker's
    playbook block, rather than adding one; the job runs with `--max-retries 0` either way.
  - The two handlers are pre-existing §3.7 data-access swallows around work, outside this spec (Non-goals).
    stocks#1047 tracks `query_to_dataframe` (its C-01 row). Item 13's issue lists both with these outcomes, and
    every image that runs these jobs installs the connector (`requirements-gcp.txt:50`, `platform/Dockerfile:29`).
- **A job that has been running on a fallback now fails loud.** That is the intent, and only for an import that
  genuinely fails in its image.
  - In an image without `gcp.database`, signal-monitor already raises in `main` (`:2632`). If only one name is
    missing (a renamed `upsert_dataframe`), the exit comes at the first fire. That is after the fire's Discord
    post (`:1618`) and before the `daily_trades` bump (`:1638`). After an exit alert, the daily P&L bump
    (`:2138`) does not run.
  - With the kill-switch and brief-bias catches re-raising `ImportError`, an unimportable override or bias store
    ends the monitor run, because `run_loop` has no catch, instead of scoring neutral or suppressing each fire.
- **The brief's per-ticker isolation ends for import errors.**
  - The new handlers at `:1685` and `:1713` mark the ticker and then re-raise, which ends the brief.
  - A missing module fails every ticker alike, so isolation buys nothing there. A missing
    `pandas_market_calendars` already ends the brief on `16b3fabd`, in `compute_strat_status`, before either
    handler (executed).
- **The admin route's statuses.** A storage outage now reads as an error on the Model State card instead of an
  empty shelf. Product documents lists the lines of 03 and of solyra's UI-SCREENS that say otherwise, and when
  they change.
- **One existing test line changes.** It is the route sweep's expectation for
  `GET /api/admin/strat-engine/state` (Design, admin section). done_when item 12 names it as the only deleted
  line under `tests/`.
- **No gate file changes.** The ratchet reads `scripts/gate/spec_gate.py` (its `valid_yaml` handler is
  allowlisted) but changes no gate file, so the gate red-team pass does not apply.
- **Overlap with FEAT-DEPLOY-001.** The sibling FEAT-DEPLOY-001 work (stocks#1384, an open draft; its branch at
  `2215223a`, merge base `16b3fabd`, fetched on 2026-11-09) edits `platform/api/main.py:557` and
  `tests/api/test_dev_page_auth.py`, near the allowlisted `main.py:374`. No line overlaps. Its `main.py` and
  `platform/api/routers/earnings.py` edits replace lines one for one (1 for 1 at `:557`, 3 for 3 at `:329-331`,
  `git diff -U0`), so they move no line the inventory blocks cite. Its other source edits,
  `scripts/maintenance/refresh_architecture_drawio.py` (+83/-34) and `scripts/maintenance/render_doc_prompts.py`
  (+4/-3), are in files no line of 05-a, 05-c or 05-e cites (grep), and it changes no render input. Whichever
  merges second runs its CI, `test_check_generated_docs.py` included, on a main that holds the first.
- **Part 2 depends on part 1.** Part 2 is a draft and cannot start before this spec's PR merges, because its plan
  deletes `PART2`. Until then its 25 handlers keep substituting, as they do today, and the item 13 issue tracks
  them.
