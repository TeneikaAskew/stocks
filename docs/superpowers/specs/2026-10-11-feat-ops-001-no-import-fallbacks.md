---
feat_id: FEAT-OPS-001
req_ids: [REQ-DATA-001]
issues: []
canvases: []
done_when:
  - "tests/meta/test_no_import_fallbacks.py::test_no_unlisted_import_fallbacks, run against origin/main's lib/, gcp/, platform/api/ and scripts/, fails listing exactly the 21 handlers in this spec's Sites removed table as path:line qualname, and passes on the PR head"
  - "tests/meta/test_no_import_fallbacks.py keys ALLOWED, PART2 and KNOWN_BROAD by (path, qualified function name), each mapping to a handler count and a reason; ALLOWED's keys are exactly the 19 in this spec's Allowlist table, PART2's exactly the 24 keys (25 handlers) in its Part 2 table, and the scan fails when any key covers more or fewer unaccepted handlers than its count"
  - "tests/meta/test_no_import_fallbacks.py runs its detector on inline snippets and asserts it refuses: except Exception, except BaseException and a bare except: around a try body of only imports, and around a body calling __import__ or importlib.import_module; except ImportError and except ModuleNotFoundError each alone, in a tuple, as an attribute and through a module-level alias tuple; except* ImportError; with contextlib.suppress(ImportError) around an import; a conditional raise; a raise only inside a nested try or handler; a handler that returns, yields, continues or breaks before its final raise, including a return inside a nested try within the handler; a handler that calls sys.exit before its raise or ends in raise SystemExit; an otherwise accepted handler whose try has a finally that returns; an otherwise accepted handler wrapped in the same function by an outer try whose first handler able to catch what it raises returns, or by a with contextlib.suppress(Exception); and a second handler in a key listed with count 1. It accepts a handler whose last top-level statement is a raise when no return, yield, continue, break or exit call appears in it outside nested function, lambda and class bodies, including an except ImportError: raise placed ahead of an outer except Exception"
  - "tests/meta/test_no_import_fallbacks.py pins the 14 broad import guards in this spec's Broad guards table in KNOWN_BROAD with a handler count each, and fails on any other bare except:, except Exception or except BaseException whose try body is only imports or calls __import__ or importlib.import_module"
  - "tests/lib/test_silent_fallback_fixes.py asserts that with pandas_market_calendars blocked, lib.strat_levels._trading_days_between(2026-10-05 23:00 UTC, 2026-10-08 13:30 UTC) raises ImportError, or an exception chained from an ImportError, instead of returning a count"
  - "With the import made to fail (monkeypatch.setitem(sys.modules, 'gcp.database', None) unless this item names another), pytest.raises(ImportError) holds for: gcp.signal_monitor.SignalMonitor._persist_signal_alert and SignalMonitor._persist_exit in tests/gcp/test_signal_monitor_persist.py; lib.strategies.exit_config_overrides.get_disabled_directions in tests/lib/test_exit_config_overrides.py, whose autouse fixture clears the lru_cache; lib.strategies.brief_bias.get_premarket_bias, its cache cleared, in tests/gcp/test_signal_monitor_brief_bias.py; gcp.premarket_brief.load_earnings_for_brief, load_economic_events, _delete_null_close_rows, load_yesterday_amc_reactions, persist_to_cloud_sql and fetch_premarket_analysis_row, and _playability_lines both with lib.earnings_reactions blocked and with only DEFAULT_LOOKBACK_QUARTERS removed from it, in tests/gcp/test_premarket_brief.py; and lib.earnings_reactions.get_calibration_options_metrics, get_earnings_calibration (cache cleared), query_reaction_stats, query_typical_daily_return and query_conditional_reactions in tests/lib/test_lib_earnings_reactions.py"
  - "tests/api/test_admin_users_datasources.py asserts that GET /api/admin/strat-engine/state answers 503, not 200 with cells: [], when google.cloud.storage cannot be imported (None in sys.modules and the storage attribute removed from google.cloud) and when storage.Client() raises"
  - "For each of the 14 rows of this spec's Caller catches table, a test makes that row's callee raise ModuleNotFoundError and asserts with pytest.raises(ImportError) that it propagates out of the function holding the catch; against origin/main's code each of the 14 fails, because the catch logs and carries on"
  - "Tests drive each job run in this spec's Entry points table end to end, hermetically, with that row's import made to fail and its stubs: gcp.premarket_brief.main(['--no-discord']), gcp.premarket_brief.main(['--post-existing', 'SPY', '2026-10-08']), gcp.signal_monitor.main() in loop mode for one poll, gcp.refresh_earnings_views.main(['--mode', 'daily']) and gcp.insight_pipeline_job.main for one ticker. On the PR head each run raises ImportError, or exits 1 having logged it, and that ImportError's traceback passes through the function in the row's Reaches column; against origin/main's code no run produces such a traceback"
  - "Tests assert that GET /api/catalysts/events?refresh=true, GET /api/catalysts/ticker/{ticker} and POST /api/backtest/replay-trades answer 5xx under TestClient(..., raise_server_exceptions=False) with the import in this spec's Entry points table made to fail, where origin/main's code answers 200"
  - "The PR body shows test_no_unlisted_import_fallbacks run against origin/main's code and FAILED naming the 21 removed handlers, and each test of items 5 to 10 run against origin/main's code and FAILED. The detector self-tests and table checks of items 2 to 4 pass on any tree and are exempt. The Backtest Pipeline jobs Run Tests, Research Tests (heavy ML stack) and Integration Tests (ephemeral Postgres) are green on the PR head"
  - "git diff --numstat origin/main...HEAD -- tests/ shows 0 deleted lines in every existing test file except tests/api/test_route_coverage.py, whose one deleted line is its GET /api/admin/strat-engine/state expectation of 200, now 503"
  - "The PR body links a new issue that lists: the 14 broad import guards, lib/gamma.py:722, lib/infra_errors.py:196, :200, :204, :208, :212, :216, :220 and :643, platform/api/routers/catalysts.py:347, platform/api/routers/dashboard.py:47 and :55, scripts/backfill_watchlist_data.py:85 and :189, each with the value its handler substitutes; the 25 handlers of this spec's Part 2 table; and the 19 Allowlist keys with their reasons. It also references #1274 for the MARKET_HOLIDAYS_2026 = set() fallback at platform/api/routers/dashboard.py:40-59"
  - "The FEAT-OPS-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists the PR under FEAT-OPS-001"
status: approved
supersedes: null
---

# Fail loud when a required import is missing: the ratchet, the signal and brief paths, and the API

## Problem

`lib/strat_levels.py:1722-1728`, `_trading_days_between`, catches `ImportError` for `pandas_market_calendars` and
returns `int(calendar_days / 1.4)`. The count is too low, so it switches off the staleness guard it feeds. Run on
2026-10-11 with the library blocked:

- a source bar from Monday 23:00 UTC, read on Thursday 13:30, counts 1 trading day against a threshold of 2, and
  the stale row is written;
- with the library, it counts 3 and raises `StaleSourceDataError`.

Four tests in `tests/lib/test_strat_levels_freshness.py` fail in any environment without the library. Six more
pass only because the approximation lands on the right side of the threshold.

An audit covered every `except ImportError` and `except ModuleNotFoundError` handler under `lib/`, `gcp/`,
`platform/api/` and `scripts/`.

- It found 69 handlers, at snapshot `2a108675`. Those directories and `tests/` are unchanged on origin/main
  `089f271e` and `17bbacd3`.
- It was run on 2026-10-11, and each substitute value was reproduced by calling the function with the import
  blocked.
- It found 38 handlers that return a value a caller cannot tell from a real result.

Two more join those 38:

- the `strat_levels` handler above;
- `platform/api/routers/admin.py:486`, which the audit left UNSURE and the Design settles.

Review of this spec found six more among the 29 the audit had accepted:

- **Three Yahoo handlers:** `gcp/fetchers/fetch_earnings_history.py:119`, and
  `scripts/fetch_earnings_calendar.py:833` and `:1082`.
  - `yfinance` is declared for the image that runs them: `requirements-gcp.txt:18`, with
    `requirements-gcp.lock:223` pinning 1.2.0, which `gcp/Dockerfile:12-16` installs.
  - So their empty DataFrame reads as "Yahoo reported nothing" when the image is broken.
- **Three internal-module guards on production paths:**
  - `lib/strategies/brief_bias.py:69` returns `bias='UNAVAILABLE'`. The signal monitor then scores the bar with
    `ftfc_score = 0.0` (`gcp/signal_monitor.py:1297`), so the FTFC penalty is silently off.
  - `gcp/premarket_brief.py:3474` makes the `/replay` cache-hit job report "no row" for what is an import
    failure.
  - `gcp/indicator_correlation_job.py:507` makes the deployed job (`gcp/deploy.sh:814`) skip its signal target
    and exit 0.

That makes 46 handlers in all.

Removing a handler is not enough when its caller catches `Exception`, because the import error lands one level
up and is swallowed again. For example, `load_earnings_for_brief` logs "playability enrichment skipped" and goes on
(`gcp/premarket_brief.py:605`). The Design traces every caller.

The 46 handlers are split across two specs, by the entry points they reach:

- **This spec (part 1)** covers the decision paths:
  - it removes 21 handlers on the signal-monitor, kill-switch, brief-bias, premarket-brief, earnings-reaction,
    strat-levels, admin and catalysts paths;
  - it fixes the 14 caller catches above them;
  - it lands the ratchet.
- **Part 2** covers the ingestion and analytics jobs:
  - its spec is `docs/superpowers/specs/2026-10-11-feat-ops-001-no-import-fallbacks-jobs.md`;
  - it removes the other 25 handlers;
  - until it lands, the ratchet lists them in `PART2`.

Seven of this spec's handlers change an alert, a recommendation or a risk control:

- `gcp/signal_monitor.py:1650` and `:2403`, `SignalMonitor._persist_signal_alert` and `SignalMonitor._persist_exit`,
  return silently after the Discord alert has gone out. The fire or the exit never reaches `signal_alerts`.
- `lib/strategies/exit_config_overrides.py:108`, `_latest_overrides`, reads as "no row".
  `get_disabled_directions` then returns an empty set, and the direction kill switch fails open. Executed on
  2026-10-11: with `gcp.database` unimportable, `lib.signals.evaluate_signal(row, min_conditions=3,
  ticker="QQQ")` fires a PUT.
- `lib/strategies/brief_bias.py:69` turns the FTFC penalty off, as above.
- `gcp/premarket_brief.py:326` and `:894` make the brief say "No earnings scheduled" and "No major events today",
  and the ORB window recommendation follows from the empty list.
- `lib/earnings_reactions.py:425` silently turns the calibration override off.

## Non-goals

- **The 14 broad import guards.** These are import guards caught by a bare or broad `except` (Broad guards
  table), such as `platform/api/routers/dashboard.py:40-59`, which sets `MARKET_HOLIDAYS_2026 = set()`. This
  change does not fix them. The ratchet pins them so no new one lands, and the PR files an issue listing them.
- **The other broad handlers.** Their try body does work besides a static import or a dynamic import call
  (`__import__`, `import_module`). That is the general §3.7 data-access shape, not an import guard.
- **Handlers the audit accepted, beyond the six above.**
  - The audit classed 29 handlers as acceptable. The six above leave.
  - Four already end in a `raise` with no early exit and need no entry: `lib/features/fracdiff.py:172`,
    `gcp/database.py:191`, `gcp/research/magnitude_engine/evaluation_windows.py:160` and
    `platform/api/routers/health.py:134`.
  - The other 19 go in the allowlist (Allowlist table). Each has a reason with evidence for why it is not a
    production path that should fail loud. Five of them guard an internal module, and their reasons say why each
    stays.
- **Failures other than an import error.** Each caller-catch fix re-raises `ImportError` alone, so a database or
  vendor failure keeps today's handling at that catch.
- **Behaviour in a healthy image.** With the import present, every code path runs the same statements as today,
  with one exception. `platform/api/routers/admin.py:494`, where `storage.Client()` fails although the package is
  installed, now answers 503 instead of 200 with `cells: []` (Design, admin section).

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
5. **Chosen: split by caller closure.** Each spec removes a set of handlers, fixes every catch above them, and
   drives every entry point they reach. The ratchet lands with part 1 and holds part 2's handlers in `PART2`.

Chosen on 2026-10-11 under the owner's instruction to bring both repositories to a clean, closed-out state. The
four failing tests surfaced it. Codex's review of the first cut (stocks#1379) and a pre-review of the second led
to the split and to the rule below.

## Design

### The fix, per handler

Each of the 21 handlers in the Sites removed table loses its substitute. They guard either an internal module
(`gcp.*`, `lib.*`, `scripts.*`) or a package every image that runs them installs:

- `pandas_market_calendars` in the jobs image, through `requirements-gcp.lock`;
- `google-cloud-storage` in both images.

A lazy import stays lazy, inside its function; it is simply not caught. The handler is deleted, except where
noted:

- `gcp/premarket_brief.py:2351` and `:2366` lose their stub copies of `lib.earnings_reactions` helpers and import
  them.
- `platform/api/routers/catalysts.py`, `_fetch_live_events`, keeps
  `from scripts.fetch_catalyst_calendar import ...`. That import resolves because `catalysts.py:32` puts the
  repository root on `sys.path`, and the API image copies `scripts/` to `/app/scripts`. The function drops the
  second-chance `sys.path` import at `:146-147` with both handlers.
- `_trading_days_between` may instead end in `raise RuntimeError(...) from exc`, as
  `evaluation_windows.py:160` does.
- `platform/api/routers/admin.py`: see the next section.

### admin.py (pre-review option A)

`_strat_engine_state_cells` ends two handlers in
`raise HTTPException(status_code=503, detail=...) from exc`: its `ImportError` handler (`:486`) and its
`storage.Client()` handler (`:494`). `GET /api/admin/strat-engine/state` then answers 503.

Solyra's Model State card (`ModelStateSnapshot.tsx:29-35`; `useAdmin.ts:179` throws on a non-ok status) then
shows "Model state unavailable: state 503". Today it shows "0 / 0 models trained" with a green "0 muted".

Fixing `:486` alone would fix a dead branch: `platform/Dockerfile` installs `google-cloud-storage`. `:494` is the
reachable twin, returning the same `cells: []` with HTTP 200, so this is the one change in a healthy image (see
Non-goals).

`tests/api/test_route_coverage.py:339` declares 200 for this request while its harness patches `storage.Client`
to fail; that 200 is the swallow. It becomes 503, as `/api/admin/routes` did ("was a bare 500"). The new tests go
in `tests/api/test_admin_users_datasources.py`, which runs in the lean Run Tests job.

Blocking the import takes two steps, because `from google.cloud import storage` reads the `storage` attribute of
`google.cloud` when it is set. `None` in `sys.modules` alone left the import working; deleting the attribute as
well raised `ModuleNotFoundError`.

Executed on a scratch copy of origin/main on 2026-10-11:

- Both new assertions fail on origin/main with `(200, '{"cells":[],"ece_ceiling":0.05}')` and pass with the
  change.
- With the change and the old route-sweep expectation, the sweep fails: "answered 503, the table says 200".
- With 503 in the table, 121 sweep tests pass. The one failure is
  `test_infrastructure_errors_are_classified_by_type`, which needs `aiohttp` (absent from that sandbox) and fails
  on unmodified main too.
- `scripts/export_openapi.py --check` reports `openapi.json` up to date.

### Caller catches

Every production caller of each removed function was traced up to its entry point, a job `main` or an API route.
The trace was a call graph over `lib/`, `gcp/`, `platform/api/` and `scripts/`, resolved through each file's
imports, plus the instance callers of `BacktestEngine.run`. It was executed on origin/main `089f271e` on
2026-10-11.

The 14 catches below catch `Exception` and carry on, so each would swallow the error this spec stops
substituting.

- **Default fix.** Each gets `except ImportError: raise` immediately ahead of its broad handler.
  `ModuleNotFoundError` is a subclass. A database or vendor failure at the same catch keeps today's handling.
- **Two exceptions.** At `gcp/premarket_brief.py:1652` and `:1680`, the new handler sets `d['status'] =
  'PLAYBOOK_FAILED'` and `d['playbook_error']` before it raises. The existing structural test
  `tests/lib/test_silent_fallback_fixes.py::test_a_strat_levels_persist_failure_marks_the_ticker` (`:1015`)
  requires every handler on a `try` around `persist_level_map` to set the status. A bare re-raise fails it
  (executed).
- **The ratchet accepts every one of these handlers** (executed).

| Catch | In | Callee that now raises | What the catch does today |
|---|---|---|---|
| `gcp/premarket_brief.py:605` | `load_earnings_for_brief` | `enrich_with_playability`, reaching `query_reaction_stats` (`:523`), `query_typical_daily_return` (`:582`), `get_earnings_calibration` (`:101`) | WARNING "playability enrichment skipped"; rows go unscored |
| `gcp/premarket_brief.py:635` | `load_earnings_for_brief` | `get_earnings_calibration` (`:101`) | WARNING; `min_nq = 12` |
| `gcp/premarket_brief.py:882` | `load_yesterday_amc_reactions` | `conditional_lean_summary`, reaching `query_conditional_reactions` (`:682`) | WARNING; the lean is omitted |
| `gcp/premarket_brief.py:1350` | `generate_premarket_brief` | `load_yesterday_amc_reactions` (`:809`) | WARNING; the AMC section is omitted |
| `gcp/premarket_brief.py:1652` | `generate_premarket_brief` | `persist_level_map`, reaching `_trading_days_between` (`strat_levels.py:1724`) | ticker marked `PLAYBOOK_FAILED`; the run continues |
| `gcp/premarket_brief.py:1680` | `generate_premarket_brief` | the playbook block holding `:1652`, once that re-raises | ticker marked `PLAYBOOK_FAILED`; the run continues |
| `gcp/premarket_brief.py:2419` | `_build_earnings_embed` | `get_calibration_options_metrics` (`:425`) | `logger.exception`; `_BRIEF_CAL_OPTS = {}`, so the Q5 override is off |
| `lib/signals.py:316` | `evaluate_signal` | `_latest_overrides` (`exit_config_overrides.py:108`), `get_disabled_directions` | logged; no signal this bar (fail closed); the poll continues |
| `gcp/signal_monitor.py:1155` | `SignalMonitor._evaluate_strategies_for_bar` | `get_disabled_directions`, reaching `_latest_overrides` | counted and logged; `(None, None)` |
| `gcp/signal_monitor.py:2052` | `SignalMonitor._resolve_brief_bias` | `get_premarket_bias` (`brief_bias.py:69`) | DEBUG log; `bias='UNAVAILABLE'`, so `ftfc_score = 0.0` (`:1297`) |
| `gcp/signal_monitor.py:695` | `SignalMonitor._update_leg_trackers` | `_resolve_brief_bias` (`:610`), once `:2052` re-raises | WARNING "leg-state update skipped"; the poll continues |
| `lib/agents/trade_planner.py:835` | `context_from_bundle` | `get_blue_sky_atr_offset`, reaching `_latest_overrides` through `_latest_overrides_or_default` | `blue_sky_offset = None` (default offset) |
| `lib/agents/orchestrator.py:592` | `run_insight_pipeline` | `context_from_bundle`, once `:835` re-raises | `persona_plans = []`, recorded in `failed_sections` |
| `scripts/generate_historical_report.py:125` | `_generate_one` | `run_insight_pipeline`, once `:592` re-raises | logged; the manual CLI exits 0 (no job or workflow runs it) |

These callers were traced and stay unchanged. Each was read on origin/main.

- `gcp/insight_pipeline_job.py:543` records the run as `failed`, with the error (`_transition`). A single-ticker
  execution then exits 1 (`:745`).
- `platform/api/routers/insights.py:484` records the run as `failed` with the error, shown at
  `GET /api/insights/runs/{run_id}`. `:909` wraps a function that already catches.
- `generate_signals` (`lib/signals.py:358`) has no ticker parameter. So `platform/api/routers/live.py:657` and
  `scripts/run_historical_signals.py:378` never read the override store.
- No caller of `BacktestEngine.run` passes `ticker=` (for example `lib/walk_forward.py:358`,
  `scripts/run_backtest.py:218`). Only `replay_labeled_trades` sets `_current_ticker` (`lib/backtest.py:1223`),
  and its route has no catch.
- `_latest_overrides_or_default` (`exit_config_overrides.py:164-169`) catches only `OverridesUnavailable`.
- `render_existing_brief_to_discord` calls `fetch_premarket_analysis_row` (`premarket_brief.py:3512`) outside
  any try.

### The ratchet (`tests/meta/test_no_import_fallbacks.py`)

The test parses every `.py` under `lib/`, `gcp/`, `platform/api/` and `scripts/` with `ast`. It checks three
kinds of guard:

1. **Kind 1:** a handler, in `try` or `try*`, whose type names `ImportError` or `ModuleNotFoundError`. The type
   may be a `Name` or an `Attribute`, alone or in a tuple, or a module-level name bound to such a name or tuple
   (`_E = (ImportError, OSError)`).
2. **Kind 2:** a bare `except:`, or one whose type includes `Exception` or `BaseException` (resolved the same
   way), when the try body it guards either consists only of import statements or calls `__import__` or
   `import_module`.
3. **Kind 3:** a `with` whose context is a `suppress(...)` call naming `ImportError` or `ModuleNotFoundError`, or
   naming `Exception` or `BaseException` around a body of the kind-2 shape. A kind 3 guard is never accepted.

**When a handler is accepted.** All of these must hold:

- **The final raise.** Its last top-level statement is a `raise`, and not a `raise` of `SystemExit`,
  `KeyboardInterrupt` or `GeneratorExit`.
- **No early exit inside it.** No `return`, `yield`, `yield from`, `continue` or `break`, and no call to
  `sys.exit`, `os._exit`, `exit` or `quit`, appears anywhere in its body.
  - The walk skips the bodies of nested functions, lambdas and classes.
  - It does descend into nested `try` bodies, handlers and `finally` blocks. So it does not reuse
    `_own_nodes`, which skips nested `except` bodies.
- **No exit from its own `finally`.** Its own try's `finally` holds no such early exit.
- **No enclosing swallow.** No enclosing `try` in the same function has, as its first handler able to catch what
  the handler raises, a handler that fails these same tests, or a `finally` with an early exit. A bare `raise`
  raises `ImportError`; `raise X(...)` raises `X`; a handler naming that type, `ImportError` or
  `ModuleNotFoundError` for an import error, `Exception`, `BaseException` or nothing catches it. No enclosing `with`
  in the same function suppresses `ImportError`, `Exception` or `BaseException`.

So `if optional: return []` ahead of the final raise is refused. So are a `sys.exit(0)` ahead of it,
`finally: return []`, an outer `except Exception: return []` around an accepted handler, and an outer
`except RuntimeError: return []` around one that raises `RuntimeError(...) from exc`. On origin/main the
rule accepts the same four handlers as before, and finds no kind-3 guard and no aliased type (executed).

**The tables.** A guard that is not accepted passes only if its (path, qualified function name) key is in one of
three dicts, each mapping that key to (handler count, reason):

- `ALLOWED` (kind 1) holds the 19 Allowlist keys.
- `PART2` (kind 1) holds the 24 keys (25 handlers) of the Part 2 table. Each reason cites the issue done_when
  item 13 files; part 2 deletes the dict.
- `KNOWN_BROAD` (kinds 2 and 3) holds the 7 keys (14 handlers) of the Broad guards table. Each reason cites the
  same issue.

`<module>` stands for module-level code, and `Class.method` for methods.

**How it fails.** The test fails listing every unaccepted guard as `path:line qualname`, with the value
`_handler_returns` names, else the first line of the handler's last statement (for a kind 3 guard, the `with`
line). `_handler_returns` comes from
`scripts/audit_silent_fallbacks.py`, loaded with `importlib` as `_scanner()` in
`tests/lib/test_silent_fallback_fixes.py` does. It names nothing for 8 of the 21 removed handlers. It also fails
when a key covers more or fewer unaccepted guards than its count.

Executed on 2026-10-11 against origin/main `089f271e`:

- A prototype of exactly this rule, with these tables, flags the 21 handlers in the Sites removed table and no
  other, with no count mismatch.
- It refuses every snippet shape in done_when item 3 and accepts the shapes that item accepts.
- On a scratch tree holding this spec's changes, it passes with the 14 new caller-catch handlers accepted.

### The behaviour tests

- **Helpers (done_when items 5 and 6).** Each test blocks the import and asserts `pytest.raises(ImportError)` in
  the test file of the module's own area. `monkeypatch.setitem(sys.modules, 'gcp.database', None)` reaches every
  `from gcp.database import X`, even after `gcp.database` is imported. Specific cases:
  - `_playability_lines:2366` is reached only when `:2351` imports. So its test removes just
    `DEFAULT_LOOKBACK_QUARTERS` from `lib.earnings_reactions`, and `from ... import` then raises.
  - Three of the functions are cached: `_latest_overrides` is `@lru_cache(maxsize=64)`
    (`exit_config_overrides.py:86`), `get_earnings_calibration` is `@lru_cache(maxsize=1)`
    (`earnings_reactions.py:84`), and `get_premarket_bias` is `@lru_cache(maxsize=128)` (`brief_bias.py:45`).
    After an earlier call, each returns its cached value instead of raising, so each test clears the cache.
- **Catches (done_when item 8).** Each row's test makes its callee raise `ModuleNotFoundError`, and asserts that
  it leaves the function holding the catch.
- **Entry points (done_when items 7, 9 and 10).** Each row drives its entry point as the row says. In every test
  above, the module under test is imported before the import is blocked.

### Entry points

Each job and route that one of this spec's handlers reaches is driven end to end, with sockets refused and the
stubs its row names. Some modules import `gcp.database` unguarded at module scope or in `main`
(`gcp/signal_monitor.py:2624`, `gcp/refresh_earnings_views.py:46`), and blocking the whole module fails those
rows on both trees. So those rows remove the one name only the removed site imports, or block the module after
import. A row passes only when the `ImportError` traceback passes through the function in its Reaches column.

| Entry point | Reaches | Import made to fail; stubs | origin/main | PR head |
|---|---|---|---|---|
| `gcp.premarket_brief.main(['--no-discord'])`, job premarket-brief | `load_earnings_for_brief` | `gcp.database` blocked after import; `BRIEF_AS_OF` a weekday; `DataLoader.load_daily` returns a fixture with a `Time` column | returns normally (executed) | `ModuleNotFoundError` through `load_earnings_for_brief` (executed) |
| `gcp.premarket_brief.main(['--post-existing', 'SPY', '2026-10-08'])`, the `/replay` cache-hit job | `fetch_premarket_analysis_row` | `gcp.database` blocked after import; `DISCORD_WEBHOOK_URL` set | `SystemExit(1)` after logging "no row" (executed) | `ModuleNotFoundError` through `fetch_premarket_analysis_row` (executed) |
| `gcp.signal_monitor.main()` in loop mode, one poll, job signal-monitor | `_persist_signal_alert` | `gcp.database.upsert_dataframe` removed and `is_cloud_sql_configured` true; `ALPHA_VANTAGE_API_KEY` set; watchlist `['SPY']`; a fixture bar window; the strategy step returns a CALL fire | the poll completes; the fire is never persisted (executed) | `ImportError` through `_persist_signal_alert` (executed) |
| `gcp.refresh_earnings_views.main(['--mode', 'daily'])`, job refresh-earnings-views | `get_calibration_options_metrics` | `gcp.database` blocked after import; module-level `is_cloud_sql_configured` true, and `query_to_dataframe`, `execute_sql` and `upsert_dataframe` stubbed with one upcoming reporter | returns 0 (executed; returns 1 without the `is_cloud_sql_configured` stub, on both trees) | `ModuleNotFoundError` through `get_calibration_options_metrics` (executed) |
| `gcp.insight_pipeline_job.main([])` with `INSIGHT_RUN_ID` and `INSIGHT_TICKER` set, job insight-pipeline | `_latest_overrides`, through `context_from_bundle` | `gcp.database.get_engine` removed; the pipeline runs with the agent fakes of `tests/agents/test_agent_orchestrator.py`; the run-status and report writes stubbed | returns 0, run `running` then `done` (executed) | returns 1, run `running` then `failed`, the logged traceback through `context_from_bundle` (executed) |
| `GET /api/admin/strat-engine/state` | `admin.py:486`, `:494` | `google.cloud.storage` blocked, or `Client()` raising | 200 with `cells: []` (executed) | 503 (executed) |
| `GET /api/catalysts/events?refresh=true`, `GET /api/catalysts/ticker/{ticker}` | `_fetch_live_events` | `BENZINGA_API_KEY` set; `scripts.fetch_catalyst_calendar` and `fetch_catalyst_calendar` blocked; a cached event file | 200; the events route labels its cache "Benzinga" (executed) | 500 (executed) |
| `POST /api/backtest/replay-trades` | `_latest_overrides`, through `get_call_target` (`lib/backtest.py:855`) | `gcp.database` blocked; journal query and bar loader stubbed as `tests/lib/test_replay_labeled_trades.py` does; `TestClient(app, raise_server_exceptions=False)` | 200 (executed) | 500 (executed) |

Three groups of catches have no entry-point row: the kill-switch catches (`lib/signals.py:316`,
`gcp/signal_monitor.py:1155`) and the brief-bias catches (`gcp/signal_monitor.py:2052`, `:695`). Done_when items 6
and 8 pin them instead. Both imports they guard are `from gcp.database import get_engine, ...`, and a monitor run
cannot isolate them; both checks were executed on origin/main:

- with `get_engine` removed, a poll already raises earlier, at the unguarded import in
  `lib/strategies/calibration.py:71`, on both trees;
- with all of `gcp.database` blocked, `main` raises at `:2624`.

### Environment

The four `test_strat_levels_freshness.py` failures came from this sandbox lacking the library, which CI installs
(`requirements.txt:90`). Executed with the library blocked:

- origin/main gives 4 failed, 9 passed;
- with the handler removed, 10 failed, 3 passed, all 10 with `ModuleNotFoundError` instead of a wrong count;
- with the library installed, both give 13 passed.

Capacity: n/a: no job reads or writes more rows, makes more calls or runs longer; with the import present each
function runs the same statements (CLAUDE.md rule 0.2). Rule 0.3's evidence beyond the hermetic tests is done_when
item 9: each job's own `main` driven end to end.

### Sites removed (21 handlers in 19 functions)

Severity from the audit:

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
| `platform/api/routers/admin.py` | `_strat_engine_state_cells` | 486 | 1 | UNSURE: `cells: []` with HTTP 200; ends in a 503 raise instead (Design) |
| `platform/api/routers/catalysts.py` | `_fetch_live_events` | 144, 148 | 2 | M: `None` plus ERROR; the cache is served labelled "Benzinga" |

### Part 2 (24 keys, 25 handlers)

`PART2` holds these keys until part 2 removes them. Each key's handler count is 1, except
`compute_score_quality_correlation`, which has 2.

| Path | Function | Lines |
|---|---|---|
| `gcp/fetchers/fetch_alphavantage_intraday.py` | `_ticker_already_backfilled` | 205 |
| `gcp/fetchers/fetch_earnings_history.py` | `fetch_yahoo_timing_for_ticker` | 119 |
| `gcp/fetchers/fetch_earnings_history.py` | `_earnings_calendar_tickers` | 247 |
| `gcp/fetchers/fetch_earnings_history.py` | `_tickers_reporting_in_window` | 281 |
| `gcp/fetchers/fetch_earnings_history.py` | `_filter_already_have_history` | 327 |
| `gcp/fetchers/fetch_earnings_history.py` | `_earnings_history_tickers` | 369 |
| `gcp/fetchers/fetch_economic_events.py` | `fetch_forexfactory_events` | 161 |
| `gcp/fetchers/fetch_economic_events.py` | `fetch_fred_releases` | 258 |
| `gcp/fetchers/fetch_insider_transactions.py` | `_earnings_calendar_tickers` | 123 |
| `gcp/fetchers/fetch_market_data.py` | `_earnings_tickers_in_window` | 663 |
| `gcp/fetchers/fetch_market_data.py` | `_backfill_targets` | 754 |
| `gcp/fetchers/fetch_news_sentiment.py` | `_fetch` | 76 |
| `gcp/fetchers/fetch_premarket_refresh.py` | `resolve_universe` | 64 |
| `gcp/fetchers/fetch_premarket_refresh.py` | `_prev_close_from_db` | 142 |
| `gcp/fetchers/fetch_premarket_refresh.py` | `upsert_premarket` | 244 |
| `gcp/fetchers/fetch_sec_filings.py` | `_earnings_calendar_tickers` | 424 |
| `gcp/indicator_correlation_job.py` | `_load_signal_outcomes` | 507 |
| `gcp/signal_quality_alarm.py` | `compute_score_quality_correlation` | 263, 286 |
| `lib/ticker_info.py` | `_cloud_sql_available` | 56 |
| `lib/ticker_info.py` | `refresh_watchlist_info` | 720 |
| `scripts/fetch_earnings_calendar.py` | `_load_existing_options_from_db` | 347 |
| `scripts/fetch_earnings_calendar.py` | `_fetch_yahoo_bulk` | 833 |
| `scripts/fetch_earnings_calendar.py` | `fetch_yahoo_earnings` | 1082 |
| `scripts/fetch_earnings_calendar.py` | `persist_to_cloud_sql` | 1106 |

### Allowlist (19 keys, 19 handlers)

Each key's handler count is 1. Each reason gives the evidence for why the handler is not a production path that
must fail loud. Five of the rows guard an internal module:

- `options_greeks:186`;
- `options_intraday:160` and `:588`;
- `options_pnl_translation:253`;
- `premarket_brief:1818`.

| Path | Function | Line | Handlers | Reason |
|---|---|---|---|---|
| `gcp/fetchers/fetch_av_historical_options.py` | `_trading_days` | 177 | 1 | WARNING and a Mon-Fri superset; the extra day logs "No options data" and writes nothing |
| `gcp/fetchers/fetch_rss_news.py` | `main` | 726 | 1 | optional dotenv; Cloud Run supplies the environment; no data effect |
| `gcp/indicator_correlation_job.py` | `_class_mutual_info` | 217 | 1 | `mutual_info` is `None`/NULL, never 0 |
| `gcp/insight_tasks.py` | `enqueue_insight_task` | 148 | 1 | returns `EnqueueOutcome.NOT_ENQUEUED` plus ERROR; both callers branch on it |
| `gcp/premarket_brief.py` | `empirical_fallback_footer` | 1818 | 1 | internal module, but the substitute is the imported constant's own value (`lib/options_intraday.py:100`), so no caller can observe the difference |
| `gcp/queries/run_query.py` | `main` | 412 | 1 | tuple handler; writes a `system_error` result row and exits 1 |
| `gcp/research/magnitude_engine/evaluation_windows.py` | `last_expected_session` | 121 | 1 | previous weekday is never earlier than the true last session, so only a false refusal |
| `lib/options_greeks.py` | `get_rate_and_yield` | 186 | 1 | internal module, but never a value in production: it raises `RateLookupError` naming the import failure ("gcp.database unavailable (...)") unless `allow_defaults=True`, which no caller passes (only `lib/options_greeks.py` itself names it) |
| `lib/options_intraday.py` | `load_realtime_theta_curve` | 160 | 1 | internal module, but no production caller: only `lib/options_intraday.py` itself and `scripts/analysis/` call it, and nothing under `gcp/` or `platform/api/` imports the module's functions; the curve is stamped `data_source='empirical_fallback'` |
| `lib/options_intraday.py` | `_load_intraday_bars` | 588 | 1 | internal module, but no production caller (as `:160`); the caller WARNs and returns a typed empty timeline |
| `platform/api/main.py` | `_strat_engine_state` | 346 | 1 | `[]` renders "strat-engine artifact state unavailable" on `/dev` (`main.py:477-478`) |
| `platform/api/routers/insights.py` | `_stream_gemini` | 1053 | 1 | streams the explicit error text to the user; no data produced |
| `scripts/analysis/options_pnl_translation.py` | `load_realtime_marks` | 253 | 1 | internal module, but an analysis CLI that no job or workflow runs (no reference in `gcp/deploy.sh` or `.github/workflows/`); every row stamped `data_source='empirical_fallback'` |
| `scripts/analysis/phase4_setup_discovery.py` | `run_decision_tree_analysis` | 381 | 1 | the report prints "sklearn not available, using rule-based analysis instead" |
| `scripts/fetch_alphavantage_intraday.py` | `<module>` | 26 | 1 | prints a notice; legacy manual CLI that no job or workflow runs |
| `scripts/fetch_alphavantage_options.py` | `<module>` | 34 | 1 | prints a notice and uses a weekday fallback; manual CLI |
| `scripts/fetch_earnings_calendar.py` | `_fetch_yahoo_one` | 957 | 1 | no production caller: only tests call it (no reference in `lib/`, `gcp/`, `platform/api/` or `scripts/`) |
| `scripts/gate/spec_gate.py` | `valid_yaml` | 820 | 1 | returns the reason string; the caller (`:1842-1843`) fails the gate closed |
| `scripts/validation/validate_brief_accuracy.py` | `_connect` | 252 | 1 | guards the external Cloud SQL Connector and falls through to a direct connection to the same database; any failure raises |

### Broad guards (7 keys, 14 handlers)

Pinned in `KNOWN_BROAD`, not fixed here; the issue in done_when item 13 lists them.

| Path | Function | Lines | Handlers | Guards | Substitutes |
|---|---|---|---|---|---|
| `lib/gamma.py` | `compute_gamma_flip_bs` | 722 | 1 | `lib.options_greeks`, `scipy.stats` | `None` plus WARNING |
| `lib/infra_errors.py` | `<module>` | 196, 200, 204, 208, 212, 216, 220 | 7 | `psycopg2`, `pg8000.exceptions`, `aiohttp`, `google.auth`, `requests`, `urllib3`, `google.api_core` | each alias bound to `None` |
| `lib/infra_errors.py` | `_storage_response_types` | 643 | 1 | `__import__` of `google.cloud.storage.exceptions`, `google.resumable_media` | `pass`; the type is left out of `_STORAGE_RESPONSE_TYPES` |
| `platform/api/routers/catalysts.py` | `_db_catalyst_events` | 347 | 1 | `gcp.database` | `[]` plus WARNING |
| `platform/api/routers/dashboard.py` | `<module>` | 47, 55 | 2 | `platform.api.routers.live`, then `api.routers.live` | `:47` retries; `:55` sets `MARKET_HOLIDAYS_2026 = set()` and three names to `None` |
| `scripts/backfill_watchlist_data.py` | `_scalar` | 85 | 1 | `gcp.database` | `None` plus WARNING |
| `scripts/backfill_watchlist_data.py` | `backfill_daily` | 189 | 1 | `requests`, `pandas`, `gcp.database`, `gcp.fetchers.fetch_market_data` | `False` plus WARNING |

## Risks

- **A handler the audit called acceptable may still mislead.** The allowlist puts each reason in one file, where
  review can read them together. The issue in done_when item 13 lists the allowlist too, and the per-key count
  stops a new handler hiding in a listed function.
- **A job that has been running on a fallback now fails loud.** That is the intent, and only for an import that
  genuinely fails in its image.
  - In an image without `gcp.database`, signal-monitor already raises in `main` (`:2624`). If only one name is
    missing (a renamed `upsert_dataframe`), the exit comes at the first fire. That is after its Discord post
    (`:1613`) and before the `daily_trades` bump (`:1633`). After an exit alert, the daily P&L bump (`:2133`)
    does not run.
  - With the kill-switch and brief-bias catches re-raising `ImportError`, an unimportable override or bias
    store ends the poll instead of scoring it neutral or suppressing each fire.
- **The brief's per-ticker isolation ends for import errors.**
  - `_trading_days_between` has one caller, `persist_level_map` (`strat_levels.py:1830`). Its one caller is
    `premarket_brief.py:1634`, in the jobs image, which pins the library.
  - The new handlers at `:1652` and `:1680` mark the ticker and then re-raise, which ends the brief.
  - A missing module fails every ticker alike, so isolation buys nothing there.
- **One existing test line changes.** It is the route sweep's expectation for
  `GET /api/admin/strat-engine/state` (Design, admin section). done_when item 12 names it as the only deleted line
  under `tests/`.
- **No gate file changes.** The ratchet reads `scripts/gate/spec_gate.py` (its `valid_yaml` handler is
  allowlisted) but changes no gate file, so the gate red-team pass does not apply.
- **Overlap with FEAT-DEPLOY-001.** The sibling FEAT-DEPLOY-001 draft edits `platform/api/main.py:480` and
  `:529` and `tests/api/test_dev_page_auth.py`, near the allowlisted `main.py:346`. No line overlaps; whichever
  merges second runs its CI on a main that holds the first.
- **Part 2 depends on part 1.** Part 2 cannot start before this spec's PR merges, because its plan deletes
  `PART2`. Until then, its 25 handlers keep substituting, as they do today.
