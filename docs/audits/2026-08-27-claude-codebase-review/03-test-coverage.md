# 03 — Test Coverage Gaps (whole repo, ranked by blast radius)

## 0. The review brief's assumptions about the test layout were wrong — and the mismatch is itself a finding

| Assumed | Actual |
|---|---|
| Playwright E2E at `tests/e2e/*.spec.ts` via `make test-e2e` | `make test-e2e` runs `pytest tests/e2e/test_e2e.py` — a **static-HTML smoke test** for `success-report-site`/`website`, unrelated to the trading platform. The real Playwright suite (**29 specs**: `signals.spec.ts`, `dashboard.spec.ts`, `admin.spec.ts`, …) lives at `platform/tests/`, run via `npm run e2e`. **No Makefile target, no CI workflow runs it.** |
| CLI tests at `tests/test_scripts_*.py` (18 files) | One file, `tests/scripts/test_scripts.py` (268 lines). |
| "No frontend unit tests exist" | False — **16 Vitest files** under `platform/src/**/*.test.{ts,tsx}` (`"test": "vitest run"`), including `expectedMove.test.ts`, which tests position-sizing and risk-hint math. **Not wired into any Makefile target or CI workflow.** |
| ~339 tests | **~3,692 tests across 226 files.** |
| (not mentioned) | A fourth suite exists: `tests/integration/` (`make test-integration`), real-Postgres contract tests, wired into CI as a separate `integration-tests` job. This is the tier that actually satisfies Rule 0 §3 — but covers a fraction of `schema.sql`'s 62 tables. |

**Practical implication: 45 frontend test files run only if a developer
manually invokes them.** Nothing in CI enforces it.

> **VERIFIED BY CLAUDE:** `.github/workflows/backtest-pipeline.yml`
> contains no `npm`/`vitest`/`playwright` job (its only playwright
> reference is installing Chromium for the Python `tests/e2e/test_e2e.py`);
> `Makefile:24-25` confirms `test-e2e` → `pytest tests/e2e/test_e2e.py`;
> counts confirmed at 16 Vitest + 29 Playwright.

## Ranked gaps

### G1 — `gcp/trade_logger.py::log_trade` — zero coverage, on the fire path, same bug class as a shipped incident
Called on **every alert fire** (`signal_monitor.py:1189-1203`) and by
the weekly `weekend-review` job. `trade_logger.py:52-57` carries an
in-line comment: *"Calling `json.dumps(...)` here was the bug that
produced JSONB-string-of-array rows in the `trades` table; same root
cause as `signal_alerts.conditions_met`."* That bug (G.P0.6) shipped and
needed a live backfill. A regression test exists for the
`signal_alerts` side (`test_signal_monitor_persist.py:156-163`) — **the
identical field written into `trades` by `log_trade` has never had
one**, and `tests/integration/test_schema_query_contract.py` never
references the `trades` table at all. Both call sites swallow with
`except Exception: log.warning(...)`, hiding failure from Cloud Run exit
codes.

### G2 — No end-to-end test of fire path ↔ EOD resolver (direct answer: **none exists**)
`test_signal_monitor_eod_resolver.py` builds `EODResolver` with
`resolver.loader = MagicMock()` and hand-authored `pd.Series` fixtures;
`test_signal_monitor*.py` exercise the fire path but never hand the row
to the resolver. `resolver.persist()` *does* have a good I/O-shape
assertion (`conn.execute.call_count == 2` against literal
`'UPDATE signal_alerts'`/`'UPDATE trades'`) — but its inputs are
synthetic. Would catch field-name/type drift between what
`_persist_signal_alert` writes and what `find_open_alerts`/`resolve_one`
read — the class that already hit twice (`alert_time` vs `alert_ts`;
`disabled_directions`, `docs/incidents/2026-05-09-*`).

### G3 — `gcp/fetchers/fetch_fred_rates.py` — scheduled daily, feeds the Greeks risk-free rate, zero tests
`fred-rates-daily`, `30 6 * * *`, writes `daily_rates.DGS3MO`. Rule 3.7
names `_DEFAULT_RISK_FREE` explicitly as forbidden-to-fabricate. No test
verifies fail-loud behaviour or FRED-shape parsing. `daily_rates` is
low-traffic and nobody eyeballs it daily.

> **Cross-reference:** report 08 D3 found this fetcher pinned to a
> 3.5-month-old image, and `daily_rates` is currently stale (latest
> 2026-08-25, 4 rows in 7 days — open issue #783). A fail-fast test here
> would have surfaced it.

### G4 — `build_options_daily_greeks.py`, `build_intraday_gex.py` — money-path builders, zero tests
`build_options_daily_greeks` is scheduled and feeds
`etf_options_daily_greeks`, which `lib/gamma.py` and the options router
read. `lib/gamma.py`/`lib/options_greeks.py` are well tested in
isolation; the job that populates their input is not — the exact
"hermetic passes, production I/O untested" gap Rule 0 §3 warns about.
`build_intraday_gex.py` is **not referenced in `deploy.sh` at all**
(cross-confirmed by report 08's orphan list) next to a
scheduled/tested twin `build_realtime_gex.py` — retirement candidate.

### G5 — `platform/api/routers/dashboard.py` / `analytics.py` — PARTIAL only, implicated in a real incident
`dashboard.py`'s `reference.week.prev_session_close` is the exact path
behind `docs/incidents/2026-04-14-market-data-daily-gap.md` (wrong date
on a KPI card, noticed by a human). A router test asserting "if
`market_data_daily` is missing the most recent weekday,
`prev_session_close` must not silently fall back two days" would catch
that class at the API layer even if the fetcher-level silent failure
recurs.

### G6 — The silent-success fetcher pattern was fixed in one file, never swept
The 2026-04-14 root cause was `fetch_market_data.py` logging a WARNING
on missing API key and `exit(0)` — Scheduler recorded success, the gap
sat 4 days. `tests/gcp/test_fetch_market_data_fail_fast.py` now exists.
**The pattern was never swept across the other 19 fetchers** —
`fetch_fred_rates.py`, `fetch_av_indicators.py`, `fetch_rss_news.py`
have no equivalent "missing credential / empty payload → nonzero exit"
test. (`fetch_cross_asset.py` is explicitly `SCAFFOLD ONLY`.)

### G7 — `scripts/analysis/*` — 17 of 22 files with no test reference
Research/mining tools, lower blast radius, but `shared_utils.py` is
imported by several phase scripts and a bug there propagates silently
through every downstream mining phase.

## Coverage map (summary)

- **`lib/**`** — well covered. Only gaps: `logging_config.py`, the two
  `exec_backtest` CLI wrappers, `features/experimental/*`.
- **`gcp/*.py` entrypoints (39)** — `trade_logger.py` critical (G1);
  `fetch_fred_rates`, `build_options_daily_greeks` high;
  `weekend_review`, `audit_job_runner`, `backtest_job`,
  `validate_brief_job`, `earnings_long_watchlist` medium;
  `db_maintenance`, `brief_explanations`, `build_intraday_gex`,
  `gcs_utils` unscheduled/investigate.
- **`gcp/fetchers/**` (20)** — 11 covered, 3 partial, 6 gaps.
- **`gcp/research/**`** — 3 gaps, none scheduled (manual tools).
- **`platform/api/routers/**` (18)** — 12 covered, 6 partial, no full
  gaps.

## Schema coverage

`schema.sql` declares **62 tables**;
`test_schema_query_contract.py::test_schema_core_tables_exist` checks
**8**. The `exit_config_overrides` gap that caused the 2026-05-09
incident is now closed (`tests/gcp/test_exit_config_overrides_schema.py`).
**The `trades` table has no presence check and no column contract test
anywhere** — same exposure class, unaddressed.

## Direct answer: I/O-shape (query-count) tests

Partially present and a good pattern where it exists, but not spread:
`test_intraday_cache_hits_once_per_ticker_day` asserts
`load_intraday.call_count == 1`;
`test_persist_mirrors_exit_to_trades_with_equal_values` asserts
`conn.execute.call_count == 2`; `test_database_pool_pre_ping.py` asserts
per-chunk checkout counts. 13 files total use `call_count` assertions —
**none for the fetcher/backfill jobs** that have the per-ticker loop
shape Rule 0 targets (cross-reference report 05's N+1 findings).

## Recommendation

Do **not** block merges wholesale — core signals/backtest/config math is
thoroughly tested. Priority order: (1) `trades`/`TradeLogger`
integration test, (2) one end-to-end fire→resolve test, (3) fail-fast
test for `fetch_fred_rates`, (4) wire the 45 existing frontend test
files into CI so they stop bit-rotting.
