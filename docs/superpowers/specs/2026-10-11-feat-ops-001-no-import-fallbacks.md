---
feat_id: FEAT-OPS-001
req_ids: [REQ-DATA-001]
issues: []
canvases: []
done_when:
  - "tests/meta/test_no_import_fallbacks.py, run against origin/main's lib/, gcp/, platform/api/ and scripts/, fails listing exactly the 40 handlers in this spec's Sites removed table, and passes on the PR head"
  - "tests/meta/test_no_import_fallbacks.py keys ALLOWED by (path, qualified function name) with a handler count and a reason; its keys are exactly the 25 in this spec's Allowlist table, and it fails when a key covers more or fewer unaccepted handlers than its count"
  - "tests/meta/test_no_import_fallbacks.py runs its detector on inline snippets and asserts it flags except Exception around a try body of only imports, a bare except: around one, a raise that is conditional, a raise only inside a nested try or handler, a second handler in a function listed with count 1, and except ImportError and except ModuleNotFoundError each alone and in a tuple, and accepts a handler whose last top-level statement is a raise"
  - "tests/meta/test_no_import_fallbacks.py pins the 13 broad import guards in this spec's Broad guards table in KNOWN_BROAD with a handler count each, and fails on any other bare except: or except Exception or BaseException whose try body is only imports"
  - "tests/lib/test_silent_fallback_fixes.py asserts that with pandas_market_calendars blocked, lib.strat_levels._trading_days_between(2026-10-05 23:00 UTC, 2026-10-08 13:30 UTC) raises ImportError, or an exception chained from an ImportError, instead of returning a count"
  - "With monkeypatch.setitem(sys.modules, 'gcp.database', None), pytest.raises(ImportError) holds for gcp.signal_monitor.SignalMonitor._persist_signal_alert and gcp.signal_monitor.SignalMonitor._persist_exit in tests/gcp/test_signal_monitor_persist.py, lib.strategies.exit_config_overrides.get_disabled_directions in tests/lib/test_exit_config_overrides.py whose autouse fixture clears the lru_cache, gcp.premarket_brief.load_earnings_for_brief and gcp.premarket_brief.load_economic_events in tests/gcp/test_premarket_brief.py, and lib.earnings_reactions.get_calibration_options_metrics in tests/lib/test_lib_earnings_reactions.py"
  - "tests/api/test_admin_users_datasources.py asserts that GET /api/admin/strat-engine/state answers 503, not 200 with cells: [], when google.cloud.storage cannot be imported (None in sys.modules and the storage attribute removed from google.cloud) and when storage.Client() raises"
  - "The PR body shows each new test run against origin/main's code and FAILED, and the Backtest Pipeline jobs Run Tests, Research Tests (heavy ML stack) and Integration Tests (ephemeral Postgres) are green on the PR head"
  - "git diff --numstat origin/main...HEAD -- tests/ shows 0 deleted lines in every existing test file except tests/api/test_route_coverage.py, whose one deleted line is its GET /api/admin/strat-engine/state expectation of 200, now 503"
  - "The PR body links a new issue that lists the 13 broad import guards, lib/gamma.py:722, lib/infra_errors.py:196, :200, :204, :208, :212, :216 and :220, platform/api/routers/catalysts.py:347, platform/api/routers/dashboard.py:47 and :55, scripts/backfill_watchlist_data.py:85 and :189, each with the value its handler substitutes, and references #1274 for the MARKET_HOLIDAYS_2026 = set() fallback at platform/api/routers/dashboard.py:40-59"
  - "The FEAT-OPS-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists the PR under FEAT-OPS-001"
status: approved
supersedes: null
---

# Fail loud when a required import is missing

## Problem

`lib/strat_levels.py:1722-1728`, `_trading_days_between`, catches `ImportError` for
`pandas_market_calendars` and returns `int(calendar_days / 1.4)`. The count is too low, so it switches
off the staleness guard it feeds: with the library blocked, a source bar from Monday 23:00 UTC read on
Thursday 13:30 counts 1 trading day against a threshold of 2 and the stale row is written; with the
library, it counts 3 and `StaleSourceDataError` is raised (run 2026-10-11). Four tests in
`tests/lib/test_strat_levels_freshness.py` fail in any environment without the library, and six more
pass only because the approximation lands on the right side of the threshold.

An audit of every `except ImportError` and `except ModuleNotFoundError` handler under `lib/`, `gcp/`,
`platform/api/` and `scripts/` (69 handlers at snapshot `2a108675`; those directories and `tests/` are
unchanged on origin/main `089f271e`; run 2026-10-11, each substitute value reproduced by calling the
function with the import blocked) found 38 more that return a value a caller cannot tell from a real
result. This change removes 40 handlers: those 38, the `strat_levels` one, and
`platform/api/routers/admin.py:486`, which the audit left UNSURE and the Design settles. The tables
below list every one. Six change an alert, a recommendation or a risk control:

- `gcp/signal_monitor.py:1650` and `:2403`: `SignalMonitor._persist_signal_alert` and
  `SignalMonitor._persist_exit` return silently after the Discord alert has gone out, so the fire or
  exit never reaches `signal_alerts`.
- `lib/strategies/exit_config_overrides.py:108`: `_latest_overrides` reads as "no row", so
  `get_disabled_directions` returns an empty set and the direction kill switch fails open.
- `gcp/premarket_brief.py:326` and `:894`: the brief says "No earnings scheduled" and "No major events
  today", and the ORB window recommendation follows from the empty list.
- `lib/earnings_reactions.py:425`: the calibration override is silently off.

Seventeen more make a job exit green having done nothing or hide a whole section. Eleven are in jobs
(`fetch_premarket_refresh` upserts 0 rows, `fetch_market_data --backfill` plans nothing); six are not:
`platform/api/routers/catalysts.py:144` and `:148` in the API, and four `lib.earnings_reactions`
readers (`:101`, `:523`, `:582`, `:682`). Fifteen waste work or hide a cause. Almost every one guards
`gcp.database` or a `lib` module, which a healthy image always holds, so the branch fires only after a
rename or a broken image, which is the failure CLAUDE.md §3.7 says must be loud.

## Non-goals

- This change does not fix the 13 import guards caught by a bare or broad `except` (Broad guards
  table), such as `platform/api/routers/dashboard.py:40-59`, which sets `MARKET_HOLIDAYS_2026 = set()`.
  The ratchet pins them so no new one lands, and the PR files an issue listing them.
- Not the other 115 broad handlers whose try body does work besides a lazy import (128 broad handlers
  have an import somewhere in their try body; 13 guard only imports). That is the general §3.7
  data-access shape, not an import guard.
- Not optional dependencies that already surface an explicit unavailable state. The audit classed 29
  handlers as acceptable. Four already end in a `raise` and need no entry (`lib/features/fracdiff.py:172`,
  `gcp/database.py:191`, `gcp/research/magnitude_engine/evaluation_windows.py:160`,
  `platform/api/routers/health.py:134`). The other 25 go in the allowlist with their reason (Allowlist
  table).
- No behaviour change in a healthy image: the code paths that run when the import succeeds are
  unchanged, and no existing success-path test is edited (done_when item 9).

## Approaches considered

1. Fix `strat_levels` alone. Rejected: the same defect is in 39 more places, and the review guideline
   this repository adopts says a class is fixed once, with each location.
2. Install the missing libraries everywhere. Rejected: the jobs image already has them; the defect is
   what happens when an import fails, not which image runs.
3. Turn `scripts/audit_silent_fallbacks.py`, the existing tested handler scanner, into the gate.
   Rejected: it is an inventory that exits 0 by design (its docstring: failing CI on 255 known sites
   would teach people to skip it), and it keys on the substituted value, not on the guarded import.
   The ratchet reuses its `_own_nodes` rather than writing a second walker (CLAUDE.md Rule 1).
4. Remove each fabricating handler named below, and add a ratchet test that fails on any new one unless
   it ends in a raise or is listed with a count and a reason. Chosen.

Chosen on 2026-10-11 under the owner's instruction to bring both repositories to a clean, closed-out
state; the four failing tests surfaced it.

## Design

- **The fix, per handler.** Each of the 40 handlers in the Sites removed table loses its substitute.
  They guard an internal module (`gcp.*`, `lib.*`, `scripts.*`) or a package every image that runs them
  installs (`pandas_market_calendars`, `requests`, `numpy` and `scipy` in the jobs image through
  `requirements-gcp.lock`; `google-cloud-storage` in both images). A lazy import stays lazy (inside the
  function); it simply is not caught. The handler is deleted, except where noted:
  - `gcp/premarket_brief.py:2351` and `:2366` lose their stub copies of `lib.earnings_reactions`
    helpers and import them.
  - `platform/api/routers/catalysts.py` `_fetch_live_events` keeps
    `from scripts.fetch_catalyst_calendar import ...`, which resolves because `catalysts.py:32` puts
    the repository root on `sys.path` (the API image copies `scripts/` to `/app/scripts`), and drops
    the second-chance `sys.path` import at `:146-147` with both handlers.
  - `_trading_days_between` may instead end in `raise RuntimeError(...) from exc`, as
    `evaluation_windows.py:160` does.
  - `platform/api/routers/admin.py`: see the next bullet.

  Internal-module guards in the Allowlist table stay, because each already surfaces an explicit
  unavailable state (reasons in the table). Both callers of the kill-switch reader
  (`gcp/signal_monitor.py:1150-1165` and `lib/signals.py:261-329`) catch `Exception` and fail closed,
  so the import failure now suppresses the fire for that bar with a logged traceback, the path a
  database read failure already takes.
- **admin.py (pre-review option A).** `_strat_engine_state_cells` ends both its `ImportError` handler
  (`:486`) and its `storage.Client()` handler (`:494`) in
  `raise HTTPException(status_code=503, detail=...) from exc`. `GET /api/admin/strat-engine/state` then
  answers 503, and solyra's Model State card (`ModelStateSnapshot.tsx:29-35`; `useAdmin.ts:179` throws
  on a non-ok status) shows "Model state unavailable: state 503" instead of "0 / 0 models trained" with
  a green "0 muted". Fixing `:486` alone would fix a dead branch: `platform/Dockerfile` installs
  `google-cloud-storage`, and `:494` is the reachable twin returning the same `cells: []` with HTTP 200.
  It is a small change: four lines in `admin.py`, and one existing test line.
  `tests/api/test_route_coverage.py:339` declares 200 for this request while its harness patches
  `storage.Client` to fail, which is the swallow; it becomes 503, as `/api/admin/routes` did ("was a
  bare 500"). Executed on a scratch copy of origin/main on 2026-10-11: with the change and the old
  expectation, the sweep fails "answered 503, the table says 200"; with 503, 121 pass and the one
  failure is `test_infrastructure_errors_are_classified_by_type`, which needs `aiohttp` (absent from
  that sandbox) and fails on unmodified main too. `scripts/export_openapi.py --check` reports
  `openapi.json` up to date, so the solyra contract is unchanged. The new test goes in
  `tests/api/test_admin_users_datasources.py`, which runs in the lean Run Tests job;
  `tests/api/test_strat_engine_predict.py` skips at module level without `lightgbm`, which
  `requirements.txt` omits. Blocking needs two steps, because `from google.cloud import storage` reads
  the `storage` attribute of `google.cloud` when it is set: `None` in `sys.modules` alone left the
  import working; deleting the attribute as well raised `ModuleNotFoundError`. Executed: both new
  assertions fail on origin/main with `(200, '{"cells":[],"ece_ceiling":0.05}')` and pass with the
  change.
- **The ratchet (`tests/meta/test_no_import_fallbacks.py`).** It parses every `.py` under `lib/`,
  `gcp/`, `platform/api/` and `scripts/` with `ast` and checks two kinds of handler:
  1. one whose type names `ImportError` or `ModuleNotFoundError`, alone or in a tuple (by `Name` or
     `Attribute`);
  2. a bare `except:`, or one whose type includes `Exception` or `BaseException`, when the try body it
     guards consists only of import statements.

  A handler is accepted only if its last top-level statement is a `raise`. A `raise` that is
  conditional, or that appears only inside a nested try or handler, does not count. Otherwise the
  handler is accepted only if its (path, qualified function name) is in `ALLOWED` (kind 1) or
  `KNOWN_BROAD` (kind 2). Each is a dict mapping that key to (handler count, reason). `<module>` stands
  for module-level code, and `Class.method` for methods. The test fails listing every unaccepted
  handler as `path:line qualname`, with the value it substitutes, and fails when a key covers more or
  fewer unaccepted handlers than its count. `ALLOWED` holds the 25 keys in the Allowlist table;
  `KNOWN_BROAD` holds the 6 keys (13 handlers) in the Broad guards table, each reason citing the issue
  done_when item 10 files.

  It loads `scripts/audit_silent_fallbacks.py` with `importlib`, as `_scanner()` in
  `tests/lib/test_silent_fallback_fixes.py` does (`scripts/` has no `__init__.py`). On origin/main,
  `_own_nodes` (`:119`) yields every node in a handler's body except the bodies of nested `except`
  handlers; a nested try's protected body is still visited. The substitute value in each failure line
  comes from `_handler_returns`, which walks with `_own_nodes`, so a value set by a nested handler is
  reported against that handler, not the one around it: `catalysts.py:144` substitutes nothing itself
  and `:148` returns `None`. The acceptance rule reads only top-level statements and needs no walk.

  Executed on 2026-10-11, a prototype of exactly this rule run on origin/main `089f271e` with the 25
  Allowlist keys and the 6 Broad guards keys flags the 40 handlers in the Sites removed table and no
  other, with no count mismatch; it flags every snippet shape in done_when item 3 and accepts a handler
  ending in `raise ... from e`.
- **The behaviour tests.** For each high-severity site, block the import
  (`monkeypatch.setitem(sys.modules, 'gcp.database', None)`, which reaches every
  `from gcp.database import X` even after `gcp.database` is imported) and assert
  `pytest.raises(ImportError)`, in the test file of that module's own area (done_when item 6).
  `_latest_overrides` is `@lru_cache(maxsize=64)` (`exit_config_overrides.py:86`): after an earlier
  call, a blocked import returns the cached `set()` and does not raise, so that test lives in
  `tests/lib/test_exit_config_overrides.py`, whose autouse `_clear_cache` fixture (`:27-32`) clears the
  cache. For `_trading_days_between`, the same with `pandas_market_calendars`, in
  `tests/lib/test_silent_fallback_fixes.py` beside its sibling for the `except Exception` branch
  (`test_trading_day_count_raises_rather_than_reporting_zero`).
- **Environment.** The four `test_strat_levels_freshness.py` failures were this sandbox lacking the
  library, which CI installs (`requirements.txt:90`). Executed with the library blocked: origin/main
  gives 4 failed, 9 passed; with the handler removed, 10 failed, 3 passed, all 10 with
  `ModuleNotFoundError` instead of a wrong count. With the library installed, both give 13 passed.

Capacity: n/a: no job's I/O shape changes; with the import present each function runs the same
statements, which the existing success-path tests show unedited (done_when item 9, CLAUDE.md rule 0.3).

### Sites removed (40 handlers in 37 functions)

Severity from the audit: H changes an alert, recommendation or risk control; M is a silent job no-op or
a hidden section; L is wasted work, a hidden cause, or a branch dead in a healthy image.

| Path | Function | Lines | Handlers | Reason (what it substitutes today) |
|---|---|---|---|---|
| `lib/strat_levels.py` | `_trading_days_between` | 1724 | 1 | known case: calendar days / 1.4 undercounts, so the staleness guard passes a stale row |
| `gcp/fetchers/fetch_alphavantage_intraday.py` | `_ticker_already_backfilled` | 205 | 1 | L: `False` ("fetch again"), no log; spends AV quota |
| `gcp/fetchers/fetch_earnings_history.py` | `_earnings_calendar_tickers` | 247 | 1 | M: `[]`; job logs "No tickers to process" and exits 0 |
| `gcp/fetchers/fetch_earnings_history.py` | `_tickers_reporting_in_window` | 281 | 1 | M: `set()`; just-reported quarters are not refreshed |
| `gcp/fetchers/fetch_earnings_history.py` | `_filter_already_have_history` | 327 | 1 | L: `(tickers, 0)`; refetches everything |
| `gcp/fetchers/fetch_earnings_history.py` | `_earnings_history_tickers` | 369 | 1 | L: `[]`; the self-heal list shrinks |
| `gcp/fetchers/fetch_economic_events.py` | `fetch_forexfactory_events` | 161 | 1 | L: empty DataFrame; job exits 0 "No events loaded" |
| `gcp/fetchers/fetch_economic_events.py` | `fetch_fred_releases` | 258 | 1 | L: empty DataFrame; same exit-0 path |
| `gcp/fetchers/fetch_insider_transactions.py` | `_earnings_calendar_tickers` | 123 | 1 | L: `[]`; "No tickers to process", exit 0 |
| `gcp/fetchers/fetch_market_data.py` | `_earnings_tickers_in_window` | 663 | 1 | M: `[]`; earnings tickers drop out of the daily universe, no log |
| `gcp/fetchers/fetch_market_data.py` | `_backfill_targets` | 754 | 1 | M: `[]`; `--backfill` plans nothing and exits green |
| `gcp/fetchers/fetch_news_sentiment.py` | `_fetch` | 76 | 1 | L: `[]` plus ERROR; reads as an empty AV feed |
| `gcp/fetchers/fetch_premarket_refresh.py` | `resolve_universe` | 64 | 1 | M: `[]`; "No tickers to refresh", exit 0 |
| `gcp/fetchers/fetch_premarket_refresh.py` | `_prev_close_from_db` | 142 | 1 | L: `None`; `gap_pct` NULL for every ticker, cause hidden |
| `gcp/fetchers/fetch_premarket_refresh.py` | `upsert_premarket` | 244 | 1 | M: `0`; "Upserted 0 rows", exit 0 |
| `gcp/fetchers/fetch_sec_filings.py` | `_earnings_calendar_tickers` | 424 | 1 | L: `[]`; "No tickers to process", exit 0 |
| `gcp/premarket_brief.py` | `_delete_null_close_rows` | 251 | 1 | L: `0`; cleanup skipped, no log |
| `gcp/premarket_brief.py` | `load_earnings_for_brief` | 326 | 1 | H: empty earnings; the brief says "No earnings scheduled" |
| `gcp/premarket_brief.py` | `load_yesterday_amc_reactions` | 809 | 1 | M: `[]`; the AMC-reaction section is omitted |
| `gcp/premarket_brief.py` | `load_economic_events` | 894 | 1 | H: empty events; "No major events today" and a 5m ORB window |
| `gcp/premarket_brief.py` | `_playability_lines` | 2351, 2366 | 2 | L: stub copies of `lib.earnings_reactions` helpers (blank hint, fixed 12Q lookback) |
| `gcp/premarket_brief.py` | `persist_to_cloud_sql` | 3232 | 1 | M: `0`; `premarket_analysis` never written |
| `gcp/signal_monitor.py` | `SignalMonitor._persist_signal_alert` | 1650 | 1 | H: returns after the Discord post; the fire never reaches `signal_alerts` |
| `gcp/signal_monitor.py` | `SignalMonitor._persist_exit` | 2403 | 1 | H: returns after the exit alert; the exit is never recorded |
| `gcp/signal_quality_alarm.py` | `compute_score_quality_correlation` | 263, 286 | 2 | L (numpy), M (scipy): `None` reads as "insufficient data" |
| `lib/earnings_reactions.py` | `get_earnings_calibration` | 101 | 1 | M: Tier-B env defaults with no tier flag, no log |
| `lib/earnings_reactions.py` | `get_calibration_options_metrics` | 425 | 1 | H: `{}`; the Q5 IC override is silently off |
| `lib/earnings_reactions.py` | `query_reaction_stats` | 523 | 1 | M: `{}`; playability vanishes for every ticker |
| `lib/earnings_reactions.py` | `query_typical_daily_return` | 582 | 1 | M: `{}`, no log |
| `lib/earnings_reactions.py` | `query_conditional_reactions` | 682 | 1 | M: `{}`; only the docstring discloses it |
| `lib/strategies/exit_config_overrides.py` | `_latest_overrides` | 108 | 1 | H: `None` ("no row"); the direction kill switch fails open |
| `lib/ticker_info.py` | `_cloud_sql_available` | 56 | 1 | L: `False` ("not configured"); falls to local tiers |
| `lib/ticker_info.py` | `refresh_watchlist_info` | 720 | 1 | L: `{}` plus ERROR; "Refreshed 0 tickers" |
| `platform/api/routers/admin.py` | `_strat_engine_state_cells` | 486 | 1 | UNSURE: `cells: []` with HTTP 200; ends in a 503 raise instead (Design) |
| `platform/api/routers/catalysts.py` | `_fetch_live_events` | 144, 148 | 2 | M: `None` plus ERROR; the cache is served labelled "Benzinga" |
| `scripts/fetch_earnings_calendar.py` | `_load_existing_options_from_db` | 347 | 1 | M: `{}`; options volume and open-interest hydration skipped |
| `scripts/fetch_earnings_calendar.py` | `persist_to_cloud_sql` | 1106 | 1 | M: `0`; the job ends "Completed Successfully!" |

### Allowlist (25 keys, 25 handlers)

Each key's handler count is 1. The reason is the audit's evidence for the handler.

| Path | Function | Line | Handlers | Reason |
|---|---|---|---|---|
| `gcp/fetchers/fetch_av_historical_options.py` | `_trading_days` | 177 | 1 | WARNING and a Mon-Fri superset; the extra day logs "No options data" and writes nothing |
| `gcp/fetchers/fetch_earnings_history.py` | `fetch_yahoo_timing_for_ticker` | 119 | 1 | optional yfinance: `{}` plus INFO; `yahoo_report_time` stays NULL, AV `reportTime` kept |
| `gcp/fetchers/fetch_rss_news.py` | `main` | 726 | 1 | optional dotenv; Cloud Run supplies the environment; no data effect |
| `gcp/indicator_correlation_job.py` | `_class_mutual_info` | 217 | 1 | `mutual_info` is `None`/NULL, never 0 |
| `gcp/indicator_correlation_job.py` | `_load_signal_outcomes` | 507 | 1 | `None` plus WARNING; the caller (`:433-436`) skips the target and writes no rows |
| `gcp/insight_tasks.py` | `enqueue_insight_task` | 148 | 1 | returns `EnqueueOutcome.NOT_ENQUEUED` plus ERROR; both callers branch on it |
| `gcp/premarket_brief.py` | `empirical_fallback_footer` | 1818 | 1 | substitutes the identical literal `'empirical_fallback'` (`lib/options_intraday.py:100`) |
| `gcp/premarket_brief.py` | `fetch_premarket_analysis_row` | 3474 | 1 | `None` documented as missing; `render_existing_brief` (`:3512-3516`) reports "no row" |
| `gcp/queries/run_query.py` | `main` | 412 | 1 | tuple handler; writes a `system_error` result row and exits 1 |
| `gcp/research/magnitude_engine/evaluation_windows.py` | `last_expected_session` | 121 | 1 | previous weekday is never earlier than the true last session, so only a false refusal |
| `lib/options_greeks.py` | `get_rate_and_yield` | 186 | 1 | raises `RateLookupError` unless `allow_defaults=True`, which no caller passes |
| `lib/options_intraday.py` | `load_realtime_theta_curve` | 160 | 1 | empirical curve stamped `data_source='empirical_fallback'` |
| `lib/options_intraday.py` | `_load_intraday_bars` | 588 | 1 | `None` documented as unavailable; the caller WARNs and returns a typed empty timeline |
| `lib/strategies/brief_bias.py` | `get_premarket_bias` | 69 | 1 | `bias='UNAVAILABLE'`, `reason='import_failed'`; `signal_monitor.py:618` handles it |
| `platform/api/main.py` | `_strat_engine_state` | 346 | 1 | `[]` renders "strat-engine artifact state unavailable" on `/dev` (`main.py:477-478`) |
| `platform/api/routers/insights.py` | `_stream_gemini` | 1053 | 1 | streams the explicit error text to the user; no data produced |
| `scripts/analysis/options_pnl_translation.py` | `load_realtime_marks` | 253 | 1 | empirical path, every row stamped `data_source='empirical_fallback'`; analysis CLI |
| `scripts/analysis/phase4_setup_discovery.py` | `run_decision_tree_analysis` | 381 | 1 | the report prints "sklearn not available, using rule-based analysis instead" |
| `scripts/fetch_alphavantage_intraday.py` | `<module>` | 26 | 1 | prints a notice; legacy manual CLI that no job or workflow runs |
| `scripts/fetch_alphavantage_options.py` | `<module>` | 34 | 1 | prints a notice and uses a weekday fallback; manual CLI |
| `scripts/fetch_earnings_calendar.py` | `_fetch_yahoo_bulk` | 833 | 1 | optional Yahoo source: empty DataFrame plus INFO |
| `scripts/fetch_earnings_calendar.py` | `_fetch_yahoo_one` | 957 | 1 | no production caller (tests only) |
| `scripts/fetch_earnings_calendar.py` | `fetch_yahoo_earnings` | 1082 | 1 | optional Yahoo source: empty DataFrame plus INFO |
| `scripts/gate/spec_gate.py` | `valid_yaml` | 820 | 1 | returns the reason string; the caller (`:1842-1843`) fails the gate closed |
| `scripts/validation/validate_brief_accuracy.py` | `_connect` | 252 | 1 | falls through to a direct psycopg2 connection; any failure raises |

### Broad guards (6 keys, 13 handlers)

Pinned in `KNOWN_BROAD`, not fixed here; the issue in done_when item 10 lists them.

| Path | Function | Lines | Handlers | Guards | Substitutes |
|---|---|---|---|---|---|
| `lib/gamma.py` | `compute_gamma_flip_bs` | 722 | 1 | `lib.options_greeks`, `scipy.stats` | `None` plus WARNING |
| `lib/infra_errors.py` | `<module>` | 196, 200, 204, 208, 212, 216, 220 | 7 | `psycopg2`, `pg8000.exceptions`, `aiohttp`, `google.auth`, `requests`, `urllib3`, `google.api_core` | each alias bound to `None` |
| `platform/api/routers/catalysts.py` | `_db_catalyst_events` | 347 | 1 | `gcp.database` | `[]` plus WARNING |
| `platform/api/routers/dashboard.py` | `<module>` | 47, 55 | 2 | `platform.api.routers.live`, then `api.routers.live` | `:47` retries; `:55` sets `MARKET_HOLIDAYS_2026 = set()` and three names to `None` |
| `scripts/backfill_watchlist_data.py` | `_scalar` | 85 | 1 | `gcp.database` | `None` plus WARNING |
| `scripts/backfill_watchlist_data.py` | `backfill_daily` | 189 | 1 | `requests`, `pandas`, `gcp.database`, `gcp.fetchers.fetch_market_data` | `False` plus WARNING |

## Risks

- A handler the audit called acceptable may still mislead. The allowlist puts each reason in one file,
  where review can read them together, and the per-key count stops a new handler hiding in a listed
  function.
- A job that has been running on a fallback, with an import that genuinely fails in its image, now
  fails loud. That is the intent. In an image without `gcp.database`, signal-monitor now raises at its
  first bar with enough history: `calculate_indicators` calls `get_consecutive_periods` unguarded
  (`signal_monitor.py:729`), whose `_latest_overrides_or_default` catches only `OverridesUnavailable`,
  and `run_loop` (`:2508-2511`) has no catch, so the process exits before any fire (executed: with the
  handler removed and the import blocked, `get_consecutive_periods`, `get_call_target` and
  `get_disabled_directions` each raise `ModuleNotFoundError`; on origin/main they return 3, 0.003 and
  `set()`). If only the persist import fails (a renamed `upsert_dataframe`), the exit comes at the first
  fire, after its Discord post (`:1613`) and before the `daily_trades` bump (`:1633`); after an exit
  alert, the daily P&L bump (`:2133`) does not run.
- `_trading_days_between` has one caller, `persist_level_map` (`strat_levels.py:1830`), whose one caller
  is `premarket_brief.py:1634` in the jobs image, which pins the library. A raise there lands in the
  `except Exception` at `premarket_brief.py:1652`, which marks the ticker `PLAYBOOK_FAILED` and writes
  no `strat_levels` row.
- One existing test line changes: the route sweep's expectation for `GET /api/admin/strat-engine/state`
  (Design, admin bullet). done_when item 9 names it as the only deleted line under `tests/`.
- The ratchet reads `scripts/gate/spec_gate.py` (its `valid_yaml` handler is allowlisted) but changes
  no gate file, so the gate red-team pass does not apply.
- The sibling FEAT-DEPLOY-001 draft edits `platform/api/main.py:480` and `:529` and
  `tests/api/test_dev_page_auth.py`, near the allowlisted `main.py:346`. No line overlaps; whichever
  merges second runs its CI on a main that holds the first.
