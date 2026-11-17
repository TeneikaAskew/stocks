---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-11-16-feat-data-001-spy-qqq-iwm-only-r2.md
branch: feature/feat-data-001-spy-qqq-iwm-only
pr: null
status: ready
---

# Prices for SPY, QQQ and IWM only: fetch from the watchlist (r2): implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the order of the spec's frontmatter, [0] to [17].

**Goal:** Every job that fetches prices takes its tickers from the active rows of the default watchlist and exits 2 on any other ticker before a vendor request; the Sunday reaction run fetches each reporter's as-traded daily series for the run and stores only the reaction; top movers keep today's list only; and the Close-out SQL files exist. No production row changes from this branch.

**Architecture:** One strict reader, `gcp.fetchers._watchlist.price_fetch_universe`, and one refusal, `require_tracked`, used by the six price entry points and two hand-run scripts. `fetch_market_data` loses its hardcoded list and earnings augmentation; `_backfill_targets` reads the universe. `compute_earnings_reactions` replaces its database windows with a one-query selection of two passes over 60 days and one `TIME_SERIES_DAILY` request per selected ticker, committing each ticker before the next. An `ast` guard lists every file that holds a price request.

**Tech Stack:** Python 3, pandas, SQLAlchemy `text()` through `gcp.database`, requests, `ast`, pytest; SQLite through `tests/fixtures/earnings_calendar_sources.py` (`make_db`, `run_earnings_sql`) for the earnings readers.

**Spec:** `docs/superpowers/specs/2026-11-16-feat-data-001-spy-qqq-iwm-only-r2.md` (approved; supersedes the #1977 draft). Read it beside this plan: Problem 1 is the path inventory, Design 8 the reaction passes, Design 12 the capacity table, Close-out the data steps that follow the merge.

## Global Constraints

- Line anchors are `origin/main` 90c41e6d (2026-11-17), where every file the spec cites under `gcp/ lib/ scripts/ platform/` is unchanged since 4155a10f except `gcp/deploy.sh` (run: `git diff --stat 4155a10f origin/main -- gcp lib scripts platform`). This branch is cut after the no-adjusted implementation merges (Task 1), so re-read every anchor on the fork commit and locate edits by quoted content.
- Not in the PR's diff (done_when[15]): `gcp/deploy.sh`, `gcp/schema.sql`, `platform/api`, `docs/product/01-PRODUCT-REQUIREMENTS.md`. No production write, deploy or job run; Task 14's reads are read-only.
- No ticker list in fetch code. The default watchlist is the switch (spec Non-goals). `^VIX` keeps its Yahoo fetch (Decision 3).
- Exact values: `DEFAULT_WATCHLIST_SQL = "SELECT ticker FROM watchlists WHERE user_id = 'default' AND removed_at IS NULL ORDER BY added_at, ticker"`; strict read with `timeout_s=120`; refusal exit code 2 and the log line `UNTRACKED job=<job> tickers=<list> watchlist=<list>`; reaction window 60 calendar days (Eastern); first pass on D+1 closed; second pass on the tenth NYSE session after D closed with `d_plus_10_close` NULL; `TIME_SERIES_DAILY` with `outputsize=compact`; on-demand frame tag `av_reaction_fetch`; Close-out SQL `lock_timeout` `5s` set with `set_config('lock_timeout', '5s', true)` inside a DO block.
- CLAUDE.md 3.7: a failed universe read raises; an empty universe raises `EmptyFetchUniverse`; a vendor failure in the reaction run is named per ticker and fails the run after the others; no fabricated reaction.
- CLAUDE.md 3.9: dates come from `lib.eastern_time` (`market_today`, `next_session`, `sessions_between`, `session_close`, `latest_session_on_or_before`); `tests/meta/test_timezone_boundaries.py` fails on a new hand-rolled conversion.
- The render step, after any task that changes a file under `gcp/`, `lib/` or `scripts/`:
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate -q` (expect 1 passed); stage whichever of the three changed.
- Before every commit: `python3 scripts/gate/spec_gate.py --commit`. Conventional commits, imperative, no AI attribution. Every new test has a red then green record in the PR body. Every existing test changed because it pinned removed behaviour is listed in the PR body with the line it pinned (done_when[15]).

## done_when map

| done_when | What | Task |
|---|---|---|
| [0] | the shared reader, the refusal, one SQL text | 2 |
| [1] | the nightly fetcher follows the watchlist | 3 |
| [2] | backfill targets and the watched-ticker job | 4 |
| [3] | the premarket refresh | 5 |
| [4] | the intraday fetcher | 6 |
| [5] | `backfill-ticker` and `migrate_to_gcp` | 7 |
| [6] | reactions fetched without storing | 10 |
| [7] | a Friday report gets both passes | 9 |
| [8] | a failed fetch is retried next Sunday | 10 |
| [9] | the weekly earnings history refresh | 11 |
| [10] | top movers keep the latest day | 12 |
| [11] | the backfill driver refuses an untracked ticker; deep backfill absent | 8 |
| [12] | the driver's fetcher command lines parse | 8 |
| [13] | every price request is listed | 13 |
| [14] | the two Close-out SQL files | 13 |
| [15] | `make test`; changed cases listed; files not in the diff | 14 |
| [16] | the PR-body counts | 14 |
| [17] | catalog, traceability, twelve SITE notes, snapshot, inventory, docs audit, gate | 15 |

## Review Focus

- **A watchlist read that fails, or comes back empty, on a scheduled night.** `price_fetch_universe` raises and the job exits 1 (or `EmptyFetchUniverse`); never a run over `INSIGHT_TICKERS` or `[]`. Task 2 pins both; Tasks 3 and 5 pin that `main` does not catch them.
- **Lower-case or spaced tickers from an operator.** `--tickers spy`, `--symbol " qqq "`, a `--replace-months` line `iwm,2025-01` are the tracked ticker, not a refusal. `test_require_tracked_normalises_case_and_space`, Task 2; one CLI case each in Tasks 3 and 6.
- **A report pending past the 60-day bound.** Logged once, the week it crosses the bound, by ticker and date; never fetched, never fabricated. Task 10 (`test_failed_fetch_is_retried_next_sunday`).
- **A selected ticker whose reports straddle a split, or whose SPLITS call fails.** The no-adjusted refusals still apply on the fetched series (`split_in_window`, `split_status_unavailable`); the other tickers commit. Task 10 keeps the no-adjusted tests green on the vendor path.
- **An hourly top-movers run that repeats a `snapshot_ts`.** The upsert keys on `(snapshot_ts, ticker)` and the delete removes only earlier dates, so a repeated hour neither duplicates nor drops today's sparkline. Task 12.

## File map

| File | Change | Task |
|---|---|---|
| `gcp/fetchers/_watchlist.py` | `DEFAULT_WATCHLIST_SQL`, `EmptyFetchUniverse`, `UntrackedTickers`, `price_fetch_universe`, `require_tracked`, `exit_untracked` | 2 |
| `gcp/calibrate_level_params.py` | `WATCHLIST_SQL` (`:96-99`), `strict_watchlist` (`:280`) | 2 |
| `gcp/fetchers/fetch_market_data.py` | `:42-63` (lists), `_earnings_tickers_in_window` `:744-848`, `_backfill_targets` `:857-944`, `_run_backfill` `:1048-1100`, `build_parser` `:1249-1274`, `main` `:1611-1724` | 3, 4 |
| `gcp/fetchers/fetch_watched_tickers.py` | `:415`, `:425` | 4 |
| `gcp/fetchers/fetch_premarket_refresh.py` | `resolve_universe` `:53-133`, `main` `:423-430` | 5 |
| `gcp/fetchers/fetch_alphavantage_intraday.py` | `resolve_all_symbols` `:57-64`, `run_replace_months` `:1011-1024`, `main` `:1583-1615` | 6 |
| `gcp/backfill_ticker.py`, `gcp/migrate_to_gcp.py` | `run` `:584-607`, `:668-671`; `migrate_market_data_daily_av` `:517`, `main` `:693` | 7 |
| `scripts/backfill_watchlist_data.py` | `backfill_intraday` `:262-268`, `main` `:355-361` | 8 |
| `gcp/fetchers/compute_earnings_reactions.py` | selection, passes, vendor series, per-ticker commit, `main` | 9, 10 |
| `lib/earnings_reactions.py` | `AS_TRADED_DAILY_SOURCES` gains `av_reaction_fetch` | 10 |
| `gcp/fetchers/fetch_earnings_history.py` | `_tickers_reporting_in_window` `:274-308`, `main` `:474-476` | 11 |
| `gcp/fetchers/fetch_top_movers.py` | `main` `:242-296`, new `write_latest_day` | 12 |
| `gcp/queries/truncate_intraday_untracked.sql`, `gcp/queries/drop_adjusted_close.sql` | new | 13 |
| `tests/gcp/test_price_fetch_universe.py` | new | 2 to 10, 13 |
| `tests/scripts/test_backfill_watchlist_data.py` | new | 8 |
| `tests/gcp/test_fetch_earnings_history.py`, `tests/gcp/test_fetch_top_movers_intraday.py` | new tests | 11, 12 |
| `tests/gcp/test_no_adjusted_prices.py` (from the no-adjusted PR) | `.sql` allowance for the drop file | 13 |
| `tests/fixtures/timezone_boundary_baseline.json` | the `_earnings_tickers_in_window` entry dropped | 3 |
| existing tests named in each task | updated where they pinned removed behaviour | 2 to 12 |
| `docs/product/02`, `03`, `12`, `docs/review-evidence/site-source-snapshot.json`, 05-a/c/e inventory blocks | close and render | 15 |

## Capacity (CLAUDE.md rule 0; spec Design 12)

Copy into the PR body's Capacity section:

- **Volume:** universe read 3 rows (one query per run). Nightly `fetch-market-data`: 3 tickers, down from 120 to 173. `fetch-earnings-history` chain: 3 backfill targets, down from 2,664. `fetch-premarket-refresh`: 3 tickers, down from 50. Sunday reactions: about twice a week's reporters plus any pending, median about 180, at most about 1,500 tickers (weekly counts over 52 weeks: median 89, max 755, `db-query-2k89c`), one 100-session series each held in memory; nothing stored but reaction rows.
- **Velocity:** nightly 6 vendor calls (2 a ticker), down from 240 to 346; chain at most 3 a run; premarket 3; reactions one `TIME_SERIES_DAILY` plus one `SPLITS` per selected ticker, one selection query, one reaction upsert per ticker; top movers one transaction a run.
- **Wall-clock:** universe read 11 to 26 ms (`db-query-89ccp`) against a 120 s statement timeout. Reactions at about 1.4 s a call: median about 8 minutes, peak about 70 minutes; the reaction job's timeout is set in spec C to at least 16,800 s (4 x peak) before Close-out step 1. Nightly and chain wall-clock after the change: not measured.
- **Cost:** about 2,940 to 3,050 vendor calls saved a weekday and 2,660 on Sunday; Cloud Run time saved about 65 minutes of 1 vCPU and 1 GiB a run, 6 runs a week, about $2 a month (list prices, not re-read). The account is a flat 600 RPM allowance; per-call billing not checked.

---

### Task 1: Preconditions and the order of the three specs

Spec: § Changes from the superseded spec, item 8; § Split and separate specs; § Close-out step 1 and steps 7 and 8; no-adjusted spec § Order against work in progress. Advances no done_when item; guards [11], [13] and [15].

**Files:** none on this branch.

- [ ] **Step 1: Code order (precondition, this plan's decision).** The no-adjusted implementation (`docs/superpowers/specs/2026-11-16-feat-data-001-no-adjusted-prices-r2.md`, branch `feature/feat-data-001-no-adjusted-prices`) is on `main` before this branch is cut. Check on `origin/main`: `tests/gcp/test_no_adjusted_prices.py` exists, `scripts/deep_backfill_ticker.py` does not, `lib.earnings_reactions` defines `AS_TRADED_DAILY_SOURCES`, `Splits` and `SplitsUnavailable`, and `compute_earnings_reactions.fetch_splits` exists. If any is missing, stop: this plan's Tasks 8, 10 and 13 are written against that tree. The admin editor (`docs/superpowers/specs/2026-11-16-feat-admin-001-default-watchlist-editor-r2.md`) opens after this PR merges.
- [ ] **Step 2: Data order, recorded in the PR body.** Close-out step 1 waits for spec C (FEAT-DEPLOY-001: weekday earnings schedulers retired, reaction timeout at least 16,800 s, the four Sunday consumers chained after the reaction run) and spec D (the live sector route). The deletes (Close-out steps 4 to 6) wait for step 1's check. Clearing and dropping `market_data_daily.adjusted_close` (steps 7 and 8) wait for the no-adjusted spec's Close-out step 2 (every reader redeployed and the nightly writing NULL). Spec B removes `gcp/schema.sql:110-111` after step 8.
- [ ] **Step 3: Base.** Cut `feature/feat-data-001-spy-qqq-iwm-only` from `origin/main`. Run `python3 -m pytest tests/gcp/test_no_adjusted_prices.py tests/gcp/test_compute_earnings_reactions.py -q` and expect pass: those are the no-adjusted tests Task 10 rebases onto the vendor path.
- [ ] **Step 4: Draft PR** after Task 2's commit: title `FEAT-DATA-001: price fetches follow the default watchlist; reactions fetch without storing`, body with the spec and plan paths, each done_when item as a `- [ ]` line starting with its text, the Capacity section above, and a section "Changed tests that pinned removed behaviour" filled as tasks land. Set `pr:` here in the next commit.

### Task 2: the shared reader and the refusal

Spec: § Design 1. Advances done_when[0].

**Files:**
- Modify: `gcp/fetchers/_watchlist.py` (beside `load_watchlist`, `:411`); `gcp/calibrate_level_params.py:96-100`, `:280`
- Create: `tests/gcp/test_price_fetch_universe.py`
- Modify tests: `tests/gcp/test_watchlist_readers_default_owner.py:18`, `:47-51`, `:136`, `:324-332`; `tests/gcp/test_av_intraday_universe.py:21-29`; `tests/gcp/test_calibrate_level_params.py:449`

**Interfaces:**
- Produces, in `gcp/fetchers/_watchlist.py`: `DEFAULT_WATCHLIST_SQL: str` (the exact text above); `class EmptyFetchUniverse(RuntimeError)`; `class UntrackedTickers(ValueError)` with attributes `job: str`, `tickers: tuple[str, ...]` (the refused ones, request order), `universe: tuple[str, ...]`; `price_fetch_universe(query=None) -> tuple[str, ...]` (`query` defaults to `gcp.database.query_to_dataframe_strict`, called once as `query(DEFAULT_WATCHLIST_SQL, timeout_s=120)`; tickers stripped, upper-cased, de-duplicated in order); `require_tracked(tickers, universe, job) -> None` (compares stripped upper-case forms); `exit_untracked(err: UntrackedTickers) -> NoReturn` (logs `UNTRACKED job=%s tickers=%s watchlist=%s` at ERROR and raises `SystemExit(2)`).

- [ ] **Step 1: Write the failing tests** in `tests/gcp/test_price_fetch_universe.py`:
  - `test_universe_is_the_active_default_watchlist`: a recording `query` returning `pd.DataFrame({'ticker': ['IWM', 'QQQ', 'spy', 'SPY']})` gives `('IWM', 'QQQ', 'SPY')`, called exactly once with `DEFAULT_WATCHLIST_SQL` and `timeout_s=120`; the SQL holds `user_id = 'default'`, `removed_at IS NULL` and `ORDER BY added_at, ticker`; a `query` raising `ConnectionError('reset')` propagates; an empty frame raises `EmptyFetchUniverse`; `require_tracked(['SPY', 'NVDA', 'AMD'], ('SPY', 'QQQ', 'IWM'), job='x')` raises `UntrackedTickers` whose `str()` contains `NVDA` before `AMD` and whose `.tickers == ('NVDA', 'AMD')`; `require_tracked(['SPY'], ('SPY', 'QQQ', 'IWM'), job='x')` returns None; `gcp.calibrate_level_params.WATCHLIST_SQL == DEFAULT_WATCHLIST_SQL`.
  - `test_require_tracked_normalises_case_and_space`: `[' spy', 'qqq ']` against the three returns None.
  - `test_exit_untracked_logs_and_exits_2` (`caplog`): `SystemExit` with `code == 2`, one ERROR line holding `UNTRACKED job=x`, `NVDA` and `SPY`.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_price_fetch_universe.py -q`. Expected: FAIL (`ImportError: price_fetch_universe`).
- [ ] **Step 3: Implement** the names above. In `gcp/calibrate_level_params.py`, `WATCHLIST_SQL = DEFAULT_WATCHLIST_SQL` (imported) and `strict_watchlist` calls `query(WATCHLIST_SQL)` with no parameters; `WATCHLIST_OWNER` goes if nothing else reads it.
- [ ] **Step 4: Update the inventory tests.** `test_watchlist_readers_default_owner.py`: a tag `PRICE_UNIVERSE = "price_fetch_universe"`, and `test_inventory_is_complete` also finds files calling `price_fetch_universe(` through a second regex beside `HELPER_CALL` (`:136`), which keeps matching only the two owner-taking helpers, since the universe takes no owner and `HELPER_OWNER_POSITION` has no entry for it; `calibrate_level_params.py` leaves `OWN_SQL` (it no longer holds `FROM watchlists`) for a tag asserting `from gcp.fetchers._watchlist import DEFAULT_WATCHLIST_SQL`; the pin at `:324-332` becomes: `WATCHLIST_SQL` is that import, and the shared text names `user_id = 'default'` and `removed_at IS NULL`; the module docstring's `:18` sentence says the owner is written once, in `DEFAULT_WATCHLIST_SQL`. Later tasks move each price reader to `PRICE_UNIVERSE`. `test_av_intraday_universe.py:21-29` and `test_calibrate_level_params.py:449` compare against `DEFAULT_WATCHLIST_SQL` with no parameters. List the `:324-332` pin in the PR body: it recorded the stocks#1887 review's choice to bind the owner; spec Design 1 makes the text one constant with the owner written in it, as `GET /api/insights/watchlist/default` already does.
- [ ] **Step 5: Run** `python3 -m pytest tests/gcp/test_price_fetch_universe.py tests/gcp/test_watchlist_readers_default_owner.py tests/gcp/test_calibrate_level_params.py tests/gcp/test_av_intraday_universe.py -q`. Expected: all pass. Render step.
- [ ] **Step 6: Commit:** `feat(data): one strict reader of the price fetch universe and one refusal`

### Task 3: `fetch-market-data`, the nightly

Spec: § Design 2; Decisions 1 to 3. Advances done_when[1].

**Files:**
- Modify: `gcp/fetchers/fetch_market_data.py:42-63`, `:744-848`, `:1249-1274`, `:1611-1724`; `tests/fixtures/timezone_boundary_baseline.json` (the `_earnings_tickers_in_window` entry)
- Test: `tests/gcp/test_price_fetch_universe.py`
- Modify tests: `tests/gcp/test_fetch_market_data_universe.py:11-18`; `tests/gcp/test_premarket_filter_params.py:66`, `:108`; `tests/gcp/test_ew_fetcher_reader_retirement.py` (the `market_universe` site, `:13`, `:20`, `:79-80`); `tests/gcp/test_watchlist_readers_default_owner.py` (`fetch_market_data.py` entry)

**Interfaces:**
- Consumes: `price_fetch_universe`, `require_tracked`, `exit_untracked`, `UntrackedTickers` (Task 2).
- Produces: `fetch_market_data.av_listed_symbol(ticker) -> str` unchanged in behaviour (`ticker.replace('.', '-')`, `AV_SYMBOL_MAP` gone because every entry was the identity); `TICKERS`, `SECTOR_ETFS`, `_earnings_tickers_in_window` and the three earnings options gone.

- [ ] **Step 1: Write the failing test** `test_daily_fetcher_follows_the_watchlist`: env `EARNINGS_WINDOW_DAYS=7`, `ALPHA_VANTAGE_API_KEY=k`; `gcp.fetchers._watchlist.price_fetch_universe` stubbed to `('IWM', 'QQQ', 'SPY')`; `query_to_dataframe` answering an earnings window holding NVDA (so a surviving augmentation would add it); `process_ticker`, `fetch_and_upsert_vix`, `read_level_params_for_run`, `_verify_post_fetch_rows`, `_assert_fetch_date_fresh` and `requests.get` recorded. `sys.argv = ['x', '--tickers', 'ALL', '--date', '2026-11-13']`: `main()` processes exactly `['IWM', 'QQQ', 'SPY']` and calls `fetch_and_upsert_vix` once. With `--tickers NVDA`: `SystemExit` code 2, `caplog` holds a line with `UNTRACKED` and `NVDA`, `requests.get` and `process_ticker` never called. `build_parser().parse_args(['--earnings-window-days', '7'])` raises `SystemExit` (unknown option); the same for `--max-earnings-tickers 5` and `--require-options`. `main()` with `--tickers spy` processes `['SPY']`.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_price_fetch_universe.py -k daily_fetcher -q`. Expected: FAIL (16 names processed plus NVDA; NVDA fetched).
- [ ] **Step 3: Implement.** `--tickers ALL` is `list(price_fetch_universe())`; an explicit list passes `require_tracked(tickers, price_fetch_universe(), 'fetch-market-data')`; `main` catches `UntrackedTickers` and calls `exit_untracked` before the level-parameter read. Remove the lists (`:42-63`), `_earnings_tickers_in_window`, the three options and their help text, the `load_watchlist` union and the earnings block of `main`, and the "Earnings win" log line. Keep `--max-tickers`, `--backfill`, `--allow-stale-date`, the recompute options and the VIX fetch. Drop the baselined site: `python3 -m tests.meta.test_timezone_boundaries --write-baseline`, and `git diff` shows only the `_earnings_tickers_in_window` entry removed.
- [ ] **Step 4: Update the tests** listed under Files: `test_fetch_market_data_universe.py` asserts no `TICKERS`, `SECTOR_ETFS` or `AV_SYMBOL_MAP` attribute and `av_listed_symbol('BF.B') == 'BF-B'`; the two `test_premarket_filter_params.py` argv lists lose `--earnings-window-days 0`; the `market_universe` site leaves `test_ew_fetcher_reader_retirement.py` (`SITES`, `MODULES`, the branch at `:79-80`); `fetch_market_data.py` takes `PRICE_UNIVERSE` in the readers inventory. Record each in the PR body with the line it pinned.
- [ ] **Step 5: Run** `python3 -m pytest tests/gcp/test_price_fetch_universe.py tests/gcp/test_fetch_market_data_universe.py tests/gcp/test_premarket_filter_params.py tests/gcp/test_ew_fetcher_reader_retirement.py tests/gcp/test_watchlist_readers_default_owner.py tests/meta/test_timezone_boundaries.py -q`. Expected: all pass. Render step.
- [ ] **Step 6: Commit:** `feat(data): the nightly price fetch covers the default watchlist only`

### Task 4: `_run_backfill`, `_backfill_targets` and `fetch-watched-tickers`

Spec: § Design 3, § Design 4. Advances done_when[2].

**Files:**
- Modify: `gcp/fetchers/fetch_market_data.py:857-944`, `:1048-1100`; `gcp/fetchers/fetch_watched_tickers.py:415`, `:425`
- Test: `tests/gcp/test_price_fetch_universe.py`
- Modify tests: `tests/gcp/test_backfill_targets_orphans.py` (whole file pins `BACKFILL_ALL_HISTORY`); `tests/gcp/test_fetch_market_data_backfill_targets.py`; `tests/gcp/test_ew_fetcher_reader_retirement.py` (the `market_eligible` site, `:81-82`); `tests/gcp/test_fetch_watched_tickers.py:158-170`, `:225`, `:998`; `tests/integration/test_watched_set_sql.py:59`, `:67`; `tests/gcp/test_watchlist_readers_default_owner.py` (`OWN_SQL_PINS` entry `:86`)

**Interfaces:**
- Produces: `_backfill_targets(query=None) -> list[tuple[str, int, date | None]]`, one tuple per ticker of `price_fetch_universe()` in its order: `SELECT ticker, COUNT(*) AS bar_count, MAX(date) AS max_date FROM market_data_daily WHERE ticker = ANY(:t) GROUP BY ticker` through `query_to_dataframe_strict`, a ticker with no row as `(t, 0, None)`.

- [ ] **Step 1: Write the failing test** `test_backfill_targets_follow_the_watchlist`: env `BACKFILL_ALL_HISTORY=true`, `ALPHA_VANTAGE_API_KEY=k`; the universe stubbed to the three; `query_to_dataframe` (the old reader) answering NVDA and AMD from `earnings_history` and `market_data_daily`; `query_to_dataframe_strict` answering the bar counts; `_av_get_full_daily_series` and `upsert_dataframe` recorded. `_run_backfill()` plans exactly `IWM, QQQ, SPY`. `_run_backfill(['NVDA'])` and `_run_backfill(['NVDA'], outputsize='compact', data_source='av_watched_backfill')` each raise `UntrackedTickers` with no series request. `fetch_watched_tickers.main()` with a watched set holding NVDA (its `read_watched_set` query stubbed as `tests/gcp/test_fetch_watched_tickers.py` stubs it) receives `exclude == ['IWM', 'QQQ', 'SPY']`, makes no series request for NVDA, and returns a non-zero code.
- [ ] **Step 2: Run** it. Expected: FAIL (targets are NVDA and AMD; `fmd.TICKERS` excluded).
- [ ] **Step 3: Implement** `_backfill_targets` as above (no `earnings_history`, no `BACKFILL_ALL_HISTORY`, no `is_cloud_sql_configured` early `[]`); explicit `tickers` pass `require_tracked(tickers, price_fetch_universe(), 'fetch-market-data --backfill')` before any request. `main --backfill` catches `UntrackedTickers` with `exit_untracked`. `fetch_watched_tickers` passes `price_fetch_universe()` where it passed `fetch_market_data.TICKERS`.
- [ ] **Step 4: Update the tests** listed under Files. `test_backfill_targets_orphans.py` and the earnings and watchlist-arm cases of `test_fetch_market_data_backfill_targets.py` are replaced by one case asserting the strict SQL above; the `market_eligible` site leaves the EW test; the watched-set tests and the integration test exclude a literal `('IWM', 'QQQ', 'SPY')` standing for the universe; `fetch_market_data.py`'s `OWN_SQL_PINS` entry goes (it holds no `FROM watchlists` now). PR body lists each.
- [ ] **Step 5: Run** `python3 -m pytest tests/gcp/test_price_fetch_universe.py tests/gcp/test_fetch_market_data_backfill_targets.py tests/gcp/test_fetch_market_data_backfill_sleep.py tests/gcp/test_fetch_watched_tickers.py tests/gcp/test_ew_fetcher_reader_retirement.py tests/gcp/test_watchlist_readers_default_owner.py -q`. Expected: all pass. Render step.
- [ ] **Step 6: Commit:** `feat(data): the earnings-chain backfill and the watched-ticker job follow the watchlist`

### Task 5: `fetch-premarket-refresh`

Spec: § Design 5. Advances done_when[3].

**Files:**
- Modify: `gcp/fetchers/fetch_premarket_refresh.py:53-133`, `:423-430`
- Test: `tests/gcp/test_price_fetch_universe.py`
- Modify tests: `tests/gcp/test_ew_fetcher_reader_retirement.py` (sites `refresh_today`, `refresh_amc`); readers inventory entry

- [ ] **Step 1: Write the failing test** `test_premarket_refresh_follows_the_watchlist`: universe stubbed to the three; `query_to_dataframe` answering optionable reporters for 2026-11-16 and postmarket reporters for 2026-11-13. `resolve_universe(date(2026, 11, 16)) == ['IWM', 'QQQ', 'SPY']`; with the universe raising `ConnectionError` it propagates. `main()` with `sys.argv = ['x', '--tickers', 'NVDA']`, env `ALPHA_VANTAGE_API_KEY=k`, `compute_premarket_for_ticker`, `upsert_premarket`, `read_level_params_for_run` and `requests.get` recorded: `SystemExit` code 2 naming NVDA, nothing recorded.
- [ ] **Step 2: Run** it. Expected: FAIL (NVDA among the reporters; `--tickers` bypasses).
- [ ] **Step 3: Implement:** `resolve_universe(target_date, max_tickers=50)` returns `list(price_fetch_universe())[:max_tickers]`; the two `earnings_calendar` reads and the swallowing `try` blocks go; `main` passes an explicit list through `require_tracked(..., 'fetch-premarket-refresh')` and catches with `exit_untracked`.
- [ ] **Step 4: Update** the EW test (both `refresh_*` sites leave `SITES` and `MODULES`; the premarket refresh no longer reads `earnings_calendar`) and the readers inventory (`PRICE_UNIVERSE`). PR body lists them.
- [ ] **Step 5: Run** `python3 -m pytest tests/gcp/test_price_fetch_universe.py tests/gcp/test_ew_fetcher_reader_retirement.py tests/gcp/test_premarket_filter_params.py tests/gcp/test_watchlist_readers_default_owner.py -q`. Expected: all pass. Render step.
- [ ] **Step 6: Commit:** `feat(data): the premarket refresh covers the default watchlist only`

### Task 6: `fetch-alphavantage-intraday` (and `intraday-bulk-backfill`)

Spec: § Design 6. Advances done_when[4].

**Files:**
- Modify: `gcp/fetchers/fetch_alphavantage_intraday.py:57-64`, `:1011-1024`, `:1583-1615`
- Test: `tests/gcp/test_price_fetch_universe.py`
- Modify tests: `tests/gcp/test_av_intraday_universe.py` (`_expected`, `test_all_resolves_to_brief_insight_and_watchlist`); readers inventory entry (`STRICT_HELPER` to `PRICE_UNIVERSE`)

- [ ] **Step 1: Write the failing test** `test_intraday_fetch_follows_the_watchlist`: universe stubbed to the three; `requests.get` and `process_symbol` recorded; env `ALPHA_VANTAGE_API_KEY=k`. `resolve_all_symbols() == ['IWM', 'QQQ', 'SPY']`. Each of `['x', '--symbol', 'NVDA']`, `['x', '--symbols-file', <tmp file with SPY and NVDA>]`, `['x', '--replace-months', <tmp list holding NVDA,2025-01>]`: `SystemExit` code 2, `caplog` holds `UNTRACKED` and `NVDA`, nothing recorded. `['x', '--symbol', ' qqq ']` processes `QQQ`. `--verify-months <list>` and `--verify-basis <list>` (with `run_verify_months` and `run_verify_basis` recorded) never call the universe stub.
- [ ] **Step 2: Run** it. Expected: FAIL (NVDA requested in all three runs).
- [ ] **Step 3: Implement:** `resolve_all_symbols()` returns `list(price_fetch_universe())` (it stops calling `brief_insight_watchlist_tickers`, which keeps its other callers). `run_replace_months` calls `require_tracked` over its list's tickers after `_read_replace_list` and before `get_api_keys`; `main` checks `--symbol` and `--symbols-file` lists the same way before the date and key setup, and wraps the dispatch in one `except UntrackedTickers` that calls `exit_untracked`. `--verify-months`, `--verify-basis` and `--export-bars-from` are dispatched before any universe read.
- [ ] **Step 4: Update** `test_av_intraday_universe.py` to expect the watchlist alone and the readers inventory. PR body lists them.
- [ ] **Step 5: Run** `python3 -m pytest tests/gcp/test_price_fetch_universe.py tests/gcp/test_av_intraday_universe.py tests/gcp/test_intraday_replace_months.py tests/gcp/test_watchlist_readers_default_owner.py -q`. Expected: all pass. Render step.
- [ ] **Step 6: Commit:** `feat(data): the 1-minute fetcher refuses tickers off the default watchlist`

### Task 7: `backfill-ticker` and `migrate_to_gcp`

Spec: § Design 7. Advances done_when[5].

**Files:**
- Modify: `gcp/backfill_ticker.py:584-607` (order), `:664-671`; `gcp/migrate_to_gcp.py:517-545`, `main` `:693`
- Test: `tests/gcp/test_price_fetch_universe.py`

- [ ] **Step 1: Write the failing test** `test_hand_run_fetchers_follow_the_watchlist`: universe stubbed to the three; `requests.get`, `gcp.database.upsert_dataframe` and `add_to_watchlist` recorded (the order of calls kept in one list). `backfill_ticker.main()` with `BACKFILL_TICKER=NVDA`, `ALPHA_VANTAGE_API_KEY=k`: `SystemExit` code 2 and no request. With `BACKFILL_ADD_TO_WATCHLIST=true` and a universe stub that returns the three plus NVDA once the add was recorded: the first recorded call is the watchlist add, then the daily request, and the run proceeds. With `BACKFILL_TICKER=SPY`: proceeds. `migrate_market_data_daily_av(Path('.'), dry_run=False)` raises `UntrackedTickers` naming `SPX` with no request.
- [ ] **Step 2: Run** it. Expected: FAIL (NVDA and SPX fetched).
- [ ] **Step 3: Implement.** `run()`: when `add_watchlist`, call `add_to_watchlist(ticker)` right after the env reads (moved from `:668-671`), then `require_tracked([ticker], price_fetch_universe(), 'backfill-ticker')`; `main()` catches with `exit_untracked`. `migrate_market_data_daily_av` passes `[s.upper() for s in AV_DAILY_SYMBOLS]` through `require_tracked(..., 'migrate_to_gcp market_data_daily_av')` before its loop; `migrate_to_gcp.main` catches with `exit_untracked`.
- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_price_fetch_universe.py tests/gcp/test_backfill_ticker.py -q`. Expected: all pass (update `tests/gcp/test_backfill_ticker.py` only where a stubbed run now needs the universe stub; list each). Render step.
- [ ] **Step 5: Commit:** `feat(data): backfill-ticker and the AV daily migration refuse untracked tickers`

### Task 8: the backfill driver and the retired deep backfill

Spec: § Design 7a; § Design 2 (the driver's call). Advances done_when[11], [12].

**Files:**
- Modify: `scripts/backfill_watchlist_data.py:262-268`, `:355-361`
- Create: `tests/scripts/test_backfill_watchlist_data.py`

- [ ] **Step 1: Write the failing tests.**
  - `test_untracked_ticker_is_refused`: module imported as `tests/scripts/test_backfill_watchlist_level_params.py:32-38` imports it; `gcp.fetchers._watchlist.price_fetch_universe` stubbed to the three; every entry of `SOURCES` replaced by recorders of its freshness and backfill function, `_run`, `requests.get` and `gcp.database.upsert_dataframe` recorded. `sys.argv = ['x', '--tickers', 'NVDA']`: `SystemExit` code 2, `caplog` holds `UNTRACKED` and `NVDA`, every recorder empty. `--tickers SPY` proceeds to SPY's freshness checks. A universe stub raising `ConnectionError` raises out of `main`. `assert not (REPO / 'scripts/deep_backfill_ticker.py').exists()`.
  - `test_fetcher_subprocess_contract`: `_run` stubbed to record its argument lists and return True; `backfill_intraday('SPY')` records at least one command; for each, `cmd[cmd.index('-m') + 2:]` parses with `gcp.fetchers.fetch_market_data.build_parser().parse_args(...)` and holds no `--earnings-window-days`. A second case appends `--earnings-window-days 0` to one recorded command and asserts `parse_args` raises `SystemExit`, so the case fails when the driver passes an option the parser does not define.
- [ ] **Step 2: Run** `python3 -m pytest tests/scripts/test_backfill_watchlist_data.py -q`. Expected: FAIL (NVDA proceeds; the driver passes `--earnings-window-days 0`).
- [ ] **Step 3: Implement.** In `main`, after the list is resolved and before the max-ticker check, `require_tracked(tickers, price_fetch_universe(), 'backfill-watchlist-data')`, caught with `exit_untracked`. The default list stays `_watchlist()` (`load_watchlist`, pinned by `tests/gcp/test_watchlist_readers_default_owner.py:74`). `backfill_intraday` drops `--earnings-window-days 0`.
- [ ] **Step 4: Run** `python3 -m pytest tests/scripts/test_backfill_watchlist_data.py tests/scripts/test_backfill_watchlist_level_params.py tests/scripts/test_failure_rate_threshold.py tests/gcp/test_watchlist_readers_default_owner.py -q`. Expected: all pass. Render step.
- [ ] **Step 5: Commit:** `feat(data): the watchlist backfill driver refuses untracked tickers`

### Task 9: the reaction run's selection: two passes over 60 days

Spec: § Design 8 (first pass, second pass, sessions, the 60-day bound, steady state). Advances done_when[7].

**Files:**
- Modify: `gcp/fetchers/compute_earnings_reactions.py` (new `SELECTION_SQL`, `PassReport`, `select_pass_reports`; nothing removed yet, `main` still uses the old helpers until Task 10)
- Test: `tests/gcp/test_price_fetch_universe.py`

**Interfaces:**
- Produces: `SELECTION_SQL`, one statement: `earnings_history eh LEFT JOIN earnings_reactions r ON r.ticker = eh.ticker AND r.fiscal_date_ending = eh.fiscal_date_ending`, `WHERE eh.reported_date BETWEEN :window_start AND :run_date AND eh.reported_date IS NOT NULL AND (eh.reported_eps > 0 OR eh.reported_eps < 0)`, selecting the eight columns of `fetch_earnings_history_for_tickers` plus `r.ticker IS NOT NULL AS has_reaction` and `r.d_plus_10_close`, ordered by `eh.reported_date, eh.ticker`; plain SQL that runs on Postgres and on the SQLite of `tests/fixtures/earnings_calendar_sources.py`.
- Produces: `@dataclass(frozen=True) class PassReport: ticker: str; fiscal_date_ending: date; reported_date: date; pass_name: str` (`'first'` or `'second'`); `select_pass_reports(run_date: date, observation_ts: pd.Timestamp, *, query=None, tickers=None) -> tuple[list[PassReport], list[tuple[str, date]]]` returning the selected reports oldest first and the reports logged as past the bound. `:window_start` is `run_date - 67 days`; a report with `reported_date < run_date - 60 days` that still needs a pass is returned in the second list (logged once, the week it crosses the bound) and never selected.
- Rules: D+1 is `next_session(D)`; the tenth session is `sessions_between(next_session(D), D + 30 days)[9]`; a session is closed when `session_close(s) <= observation_ts`. First pass: no stored reaction and D+1 closed. Second pass: stored, `d_plus_10_close` NULL, tenth session closed.

- [ ] **Step 1: Write the failing test** `test_friday_report_gets_both_passes`: one report, BMO, Friday 2026-11-13; for each Sunday `run_date`, `observation_ts = session_close(latest_session_on_or_before(run_date))`, the stub query returning the report with the stored state of that week. 2026-11-15: no report selected (D+1, Monday 2026-11-16, not closed). 2026-11-22: selected, `pass_name == 'first'`. 2026-11-29: not selected (with a stored row and `d_plus_10_close` NULL; the tenth session is Monday 2026-11-30, Thanksgiving closed). 2026-12-06: selected, `'second'`. Also: the stub received exactly one statement, `SELECTION_SQL`, with `window_start == run_date - timedelta(days=67)`.
- [ ] **Step 2: Run** it. Expected: FAIL (`select_pass_reports` does not exist).
- [ ] **Step 3: Implement** the selection with the rules above, through `query_to_dataframe_strict` by default.
- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_price_fetch_universe.py -k friday tests/gcp/test_compute_earnings_reactions.py -q`. Expected: all pass.
- [ ] **Step 5: Commit:** `feat(data): select each Sunday's reaction reports by pass, within 60 days`

### Task 10: the reaction run: fetch for the run, store only the reaction

Spec: § Design 8 (the fetch, per-ticker commit, failure, nothing stored, older reactions stay). Advances done_when[6], [8].

**Files:**
- Modify: `gcp/fetchers/compute_earnings_reactions.py` (new `fetch_daily_series`, `run_reaction_passes`; `populate_for_tickers` `:707-878` becomes the per-ticker body; remove `fetch_daily_window` `:602-639`, `fetch_daily_windows_for_ticker_dates` `:642-704`, `_resolve_tickers` `:880-908`, `_tickers_reporting_in_window` `:911-936`, `_resolve_scope` `:939-947` and `_filter_already_have_reactions` `:950-975`; `main` `:978-1024`); `lib/earnings_reactions.py` (`AS_TRADED_DAILY_SOURCES` gains `'av_reaction_fetch'`)
- Test: `tests/gcp/test_price_fetch_universe.py`
- Modify tests: `tests/gcp/test_ew_fetcher_reader_retirement.py` (site `reaction_window`); `tests/gcp/test_compute_earnings_reactions.py` (`TestResolveTickersBroadScope` `:649-733`, `TestTickersReportingInWindowTimezone` `:1031-1062`, `TestFetchDailyWindowsForTickerDates` `:925-1030`; the no-adjusted cases `test_split_in_loaded_window_skips_the_event`, `test_every_splits_request_failing_fails_the_run`, `test_native_pre10_prefix_is_qualified_by_actual_producer_not_short_path`, `:1105-1146`, `:1197-1215`); `tests/integration/test_earnings_daily_path_persistence.py:204-209`

**Interfaces:**
- Consumes: `select_pass_reports`, `PassReport` (Task 9); `fetch_splits`, `Splits`, `SplitsUnavailable`, `database_daily_price_evidence(..., splits=...)` (no-adjusted PR); `av_listed_symbol`.
- Produces: `class DailySeriesUnavailable(Exception)` with `reason`; `fetch_daily_series(ticker: str, api_key: str) -> pd.DataFrame`: one `requests.get(AV_BASE_URL, params={'function': 'TIME_SERIES_DAILY', 'symbol': av_listed_symbol(ticker), 'outputsize': 'compact', 'datatype': 'json', 'apikey': api_key}, timeout=60)`, columns `date, open, high, low, close, volume, data_source` with `data_source == 'av_reaction_fetch'` and no `atr_14` (the inline ATR-14 of `compute_reaction` applies); `Note`, `Information`, `Error Message`, a missing series, an HTTP error or a parse error raise `DailySeriesUnavailable`. `run_reaction_passes(run_date, observation_ts, *, api_key, tickers=None, dry_run=False, receipt_sink=None) -> int` (exit code). `main()` gains `--as-of YYYY-MM-DD` (default `market_today()`; with it, `observation_ts = session_close(latest_session_on_or_before(as_of))`) and keeps `--tickers` (a filter on the selection) and `--dry-run`; `--force` and `--scope` go.

- [ ] **Step 1: Write the failing tests.**
  - `test_reactions_fetch_without_storing`: run 2026-12-06; the selection stub holds NVDA (BMO, reported 2026-12-01, no reaction), AMD (2026-11-18, stored, `d_plus_10_close` NULL; its tenth session 2026-12-03), ORCL (2026-10-20, stored, NULL), MSFT (2026-11-25, stored, tenth session not closed), IBM (stored, `d_plus_10_close` set), AAPL (2026-09-22, no reaction) and CSCO (2026-10-06, stored, NULL); every report of known timing. A vendor stub answers `TIME_SERIES_DAILY` with 100 sessions per ticker and `SPLITS` with no split, and records every request; a statement recorder over `query_to_dataframe_strict`, `query_to_dataframe` and `gcp.database.get_engine` records every SQL text; `_upsert_reaction_frame` records frames. Assert: one statement holds `earnings_history` (the selection); the `TIME_SERIES_DAILY` requests are exactly ORCL, AMD, NVDA in that order, each `outputsize == 'compact'`; no recorded statement names `market_data_daily`; no upserted row is MSFT, IBM, AAPL or CSCO; each upserted frame is one ticker's, and the stub's second `TIME_SERIES_DAILY` request finds ORCL's frame already recorded; each row's ATR context equals `compute_reaction` over the same series without `atr_14`; the rows carry `daily_path_v1['basis_id'] == 'av-as-traded-no-split-v1'`. A second run with NVDA's series answering `Information`: NVDA has no row, `caplog` names NVDA, ORCL and AMD rows are upserted, the exit code is 1.
  - `test_failed_fetch_is_retried_next_sunday`: run 2026-12-06 failing NVDA (first pass) and AMD (second pass): exit 1, no NVDA row, AMD's `d_plus_10_close` not written. Run 2026-12-13 with a working vendor and the stored state of the first run: both requested, NVDA's reaction and AMD's `d_plus_10_close` written. The same retry with AMD reported 61 days before the run: no request for AMD and a log line naming AMD, its date and `past the 60-day bound`.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_price_fetch_universe.py -k "without_storing or retried" -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** `run_reaction_passes`: select (Task 9), log each past-bound report, group the selected reports by ticker (oldest report first), then per ticker: `fetch_daily_series`, `fetch_splits` (both paced at `AlphaVantageConfig().delay_between_calls`), each report's window cut from the series as the old slice did (`-90` / `+25` calendar days), the existing per-event pipeline (timing, completed sessions, split refusals, `compute_reaction`, gate, native qualification), then that ticker's rows through `_upsert_reaction_frame` before the next ticker. A `DailySeriesUnavailable` is logged with the ticker and the reason, writes nothing for it, and makes the exit code 1 after the other tickers; the no-adjusted rule (every `SPLITS` failed, exit 1) is kept. Log `ticker=%s splits=%d processed=%d/%d` per ticker. Add `'av_reaction_fetch'` to `AS_TRADED_DAILY_SOURCES`.
- [ ] **Step 4: Rebase the no-adjusted tests onto the vendor path.** Each test listed under Files that stubbed `fetch_daily_windows_for_ticker_dates` stubs `fetch_daily_series` with the same frame (plus `data_source`), and drives `run_reaction_passes` or the per-ticker body; every assertion kept (`split_in_window`, `split_status_unavailable`, `splits_unavailable=<n>`, exit codes, the native identities). `test_every_splits_request_failing_fails_the_run` loses `--force` from its argv and gains `--as-of`. `TestFetchDailyWindowsForTickerDates`, `TestResolveTickersBroadScope` and `TestTickersReportingInWindowTimezone` leave with the functions they tested; the `reaction_window` site leaves the EW test. The integration test stubs `fetch_daily_series` and `fetch_splits`. PR body lists each.
- [ ] **Step 5: Run** `python3 -m pytest tests/gcp/test_price_fetch_universe.py tests/gcp/test_compute_earnings_reactions.py tests/gcp/test_no_adjusted_prices.py tests/gcp/test_ew_fetcher_reader_retirement.py -q` and, where a Postgres is available, `python3 -m pytest tests/integration/test_earnings_daily_path_persistence.py -q` (otherwise CI runs it, `.github/workflows/backtest-pipeline.yml:163`). Expected: all pass. Render step.
- [ ] **Step 6: Commit:** `feat(data): Sunday reactions fetch each reporter's daily series and store only the reaction`

### Task 11: the weekly earnings history brings in last week's quarters

Spec: § Design 8 (the Sunday `fetch-earnings-history` run). Advances done_when[9].

**Files:**
- Modify: `gcp/fetchers/fetch_earnings_history.py:274-308`, `:474-476`
- Test: `tests/gcp/test_fetch_earnings_history.py`
- Modify tests: `tests/gcp/test_ew_fetcher_reader_retirement.py` (site `history_window` calls the new signature)

**Interfaces:**
- Produces: `_tickers_reporting_in_window(window_days: int, days_back: int = 0) -> set`, the lower bound written `(NOW() AT TIME ZONE 'America/New_York')::date - (:days_back || ' days')::interval` (the shape `tests/fixtures/earnings_calendar_sources.run_earnings_sql` adapts, `tests/gcp/test_ew_fetcher_reader_retirement.py:63-65`); the weekly scope calls `(7, days_back=7)`, the daily scope `(0)`.

- [ ] **Step 1: Write the failing test** `test_weekly_run_refreshes_last_weeks_reporters`: a SQLite database from `make_db` (earnings_calendar showing NVDA reported 2026-12-03, a Thursday, three days before Sunday 2026-12-06) plus `earnings_history` holding only NVDA's previous quarter and an empty `earnings_reactions`; `query_to_dataframe` and `query_to_dataframe_strict` run through `run_earnings_sql(conn, sql, params, today=date(2026, 12, 6))`; `upsert_dataframe` inserts into the SQLite tables; the vendor stub answers `EARNINGS` for NVDA with the new quarter, `TIME_SERIES_DAILY` and `SPLITS`; `_run_backfill` stubbed (the chain is Task 4's). `main()` with `--scope weekly` makes exactly one `EARNINGS` request, for NVDA, and the new quarter is in `earnings_history`; then `compute_earnings_reactions.run_reaction_passes(date(2026, 12, 6), ...)` over the same database writes NVDA's first-pass reaction.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_fetch_earnings_history.py -k last_weeks -q`. Expected: FAIL (the weekly window starts today; NVDA is skipped).
- [ ] **Step 3: Implement** the `days_back` bound and pass 7 for the weekly scope; update the scope log line to `report-window=[today-%dd, today+%dd]`.
- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_fetch_earnings_history.py tests/gcp/test_ew_fetcher_reader_retirement.py -q`. Expected: all pass. Render step.
- [ ] **Step 5: Commit:** `feat(data): the Sunday earnings history refresh brings in last week's reporters`

### Task 12: top movers: today's list only

Spec: § Design 8a; Decision 8. Advances done_when[10].

**Files:**
- Modify: `gcp/fetchers/fetch_top_movers.py:242-296`
- Test: `tests/gcp/test_fetch_top_movers_intraday.py`

**Interfaces:**
- Produces: `write_latest_day(df: pd.DataFrame, table: str, conflict_cols: list[str], snapshot_date: date) -> int`: one `gcp.database.get_engine().begin()` transaction holding the `ON CONFLICT DO UPDATE` insert of `df` (`sqlalchemy.dialects.postgresql.insert`, reflected table as `gcp.database.upsert_dataframe` builds it) and then `DELETE FROM <table> WHERE snapshot_date < :d`; returns the rows inserted.

- [ ] **Step 1: Write the failing test** `test_runs_keep_only_the_latest_day`: a recording engine whose `begin()` yields a connection recording each statement's text and parameters and recording whether the block exited with an exception; the vendor stubbed for the daily list and for the intraday snapshot (the shapes the existing tests at `:113-140` use); `is_cloud_sql_configured` True. `main()` (no args): exactly one `begin()`, the insert into `top_movers_daily` then `DELETE FROM top_movers_daily WHERE snapshot_date < :d` with `d == market_today()`. `main()` with `--intraday-snapshot`: the same on `top_movers_intraday` with today's ET date. With the DELETE raising: the error propagates and the block exited with it (rollback), no second `begin()`. An empty vendor answer opens no transaction.
- [ ] **Step 2: Run** it. Expected: FAIL (`upsert_dataframe` is called; no delete).
- [ ] **Step 3: Implement** `write_latest_day` and call it from both branches of `main` in place of `upsert_dataframe`; the empty-answer returns stay before any write (`:254-257`, `:274-276`).
- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_fetch_top_movers_intraday.py -q`. Expected: all pass. Render step.
- [ ] **Step 5: Commit:** `feat(data): top movers keep today's list and drop earlier days in one transaction`

### Task 13: the price-request guard and the Close-out SQL files

Spec: § Design 9; § Design 10. Advances done_when[13], [14].

**Files:**
- Create: `gcp/queries/truncate_intraday_untracked.sql`, `gcp/queries/drop_adjusted_close.sql`
- Test: `tests/gcp/test_price_fetch_universe.py`; modify `tests/gcp/test_no_adjusted_prices.py` (its `.sql` allowance)

**Interfaces:**
- Produces (test module): `price_request_files(root: Path) -> set[str]`, the `.py` files under `gcp/` and `scripts/` holding a dict literal whose `'function'` value is the constant `TIME_SERIES_INTRADAY`, `TIME_SERIES_DAILY`, `TIME_SERIES_DAILY_ADJUSTED` or `GLOBAL_QUOTE`; `PRICE_REQUEST_FILES: dict[str, str]`, each listed file with the test that refuses for it or its reason.

- [ ] **Step 1: Write the tests.**
  - `test_every_price_request_is_listed`: `price_request_files(REPO) == set(PRICE_REQUEST_FILES)`, the set being exactly `gcp/backfill_ticker.py`, `gcp/fetchers/compute_earnings_reactions.py`, `gcp/fetchers/fetch_alphavantage_intraday.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/migrate_to_gcp.py`, `gcp/signal_monitor.py`, `scripts/analysis/strat_combo_miner.py`, `scripts/backfill_watchlist_data.py`, `scripts/fetch_alphavantage_intraday.py`, `scripts/fetch_market_data.py`. Writers map to their refusal tests (Tasks 3 to 8); `compute_earnings_reactions.py` to `test_reactions_fetch_without_storing` (fetches the week's reporters, stores no bar); `gcp/signal_monitor.py` to "live bars for the watchlist's `signals` rows, stores no bar"; the three scripts to "local files only, no database write". A guard case: `price_request_files` over a `tmp_path` tree holding `gcp/new_fetcher.py` with `{'function': 'TIME_SERIES_DAILY'}` returns it, so the equality fails for a new file. (A prototype of this walk over origin/main 90c41e6d on 2026-11-17 returned the ten minus `compute_earnings_reactions.py` plus `scripts/deep_backfill_ticker.py`, as the spec says.)
  - `test_truncate_file_names_only_the_default_partition`: the first file, comments stripped, is one `DO $$ ... $$;` block holding `set_config('lock_timeout', '5s', true)` and exactly one `TRUNCATE TABLE market_data_intraday_other`, and names no other relation (no `market_data_intraday_spy`, `_qqq`, `_iwm`, `_spx`, no bare `market_data_intraday` outside that name); the second sets the same lock timeout and holds exactly one `ALTER TABLE market_data_daily DROP COLUMN adjusted_close` and no other `DROP`.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_price_fetch_universe.py -k "listed or truncate" -q`. Expected: the first passes once Tasks 3 to 10 are in (it is written last so the walk sees the final tree; record its output on a tree with Task 10 reverted as the red run), the second FAILs (no files).
- [ ] **Step 3: Write the two files** as Design 10 gives them. `drop_adjusted_close.sql` names `adjusted_close`, which the no-adjusted guard's `.sql` scan refuses outside `gcp/schema.sql:110-111`: add this file's one `ALTER TABLE` line as a second pinned allowance in `tests/gcp/test_no_adjusted_prices.py`, by path and exact text, and say so in the PR body (spec B removes both allowances with the schema line).
- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_price_fetch_universe.py tests/gcp/test_no_adjusted_prices.py -q`. Expected: all pass.
- [ ] **Step 5: Commit:** `test(data): list every price request and add the Close-out SQL files`

### Task 14: `make test`, the changed cases, the PR-body counts

Spec: § Close-out (its tables); done_when[15], [16]. Advances done_when[15], [16].

- [ ] **Step 1:** `make test`. Expected: exit 0. `git diff --name-only origin/main...HEAD -- gcp/deploy.sh gcp/schema.sql platform/api docs/product/01-PRODUCT-REQUIREMENTS.md` prints nothing.
- [ ] **Step 2:** The PR body's "Changed tests that pinned removed behaviour" lists every case changed or removed in Tasks 2 to 10 with the file and line it pinned on the merge base (`git diff --stat origin/main...HEAD -- tests` is the checklist).
- [ ] **Step 3: Counts, read-only, on the day the PR opens** (CLAUDE.md, Database access; no `--commit`). One dispatch: `./scripts/db_query_cr.sh -q "SELECT user_id, ticker FROM watchlists WHERE removed_at IS NULL ORDER BY 1, 2; SELECT count(*) FROM user_watchlists WHERE removed_at IS NULL; SELECT count(*) FROM watched_tickers; SELECT extract(year FROM date)::int AS y, count(*) FROM market_data_daily WHERE ticker NOT IN ('SPY','QQQ','IWM','^VIX','^VIX3M','^VVIX') GROUP BY 1 ORDER BY 1"`, then one dispatch with `SELECT count(*) FROM <t> WHERE ticker NOT IN ('SPY','QQQ','IWM')` for each of `historical_signals`, `signal_metrics`, `premarket_analysis`, `premarket_analysis_history`, `strat_levels`, `ticker_level_params`, `insight_reports`, `insight_reports_history`, `earnings_reactions`, `earnings_options_strategy_winners`, `top_movers_daily`, `top_movers_intraday` (`--timeout 300`). Then `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud storage ls -l gs://adept-mountain-474619-d4-trading-data/sql-dumps/ | sort -k2 | tail -1`. Paste each output with its execution id under "Close-out baseline".
- [ ] **Step 4:** Render step; `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` passes. Commit any regenerated block: `docs(data): re-render the inventory for the watchlist-only fetch`.

### Task 15: close

Spec: § Design 11; done_when[17]. Closes done_when[17].

- [ ] **Step 1: Catalog.** FEAT-DATA-001 record (`docs/product/02-FEATURE-CATALOG.md:513`): Status gains "price fetches follow the default watchlist; Sunday reactions fetch without storing (#<PR>), Close-out pending", Last reviewed the head commit's date. No other record.
- [ ] **Step 2: Traceability.** This PR under `### FEAT-DATA-001` of `docs/product/12-PR-ISSUE-TRACEABILITY.md`, touching #1980.
- [ ] **Step 3: Site notes.** `produce` once to read the identity (`python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`, then `git checkout -- docs/review-evidence/site-source-snapshot.json`). In `## Implementation-source notes` of `docs/product/03-SITE-TRACEABILITY.md`, a `(FEAT-DATA-001, <id>)` row for ADMIN-06, CATALYSTS-01, CHARTS-01, CHARTS-03, DASHBOARD-01, DASHBOARD-04, INSIGHTS-01, JOURNAL-01, JOURNAL-04, LIVE-04, LIVE-08, PLAYBOOK-05, each `source_identity_sha256=<hash>; ` then: the job's tickers come from the default watchlist and any other requested ticker is refused (Design 11), claiming no page change. Rows that exist (the no-adjusted PR left rows on ten of these) are extended: new hash and this prose first, then `Earlier: ` and the earlier prose unchanged. Commit; `produce` again; commit the sidecar; `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 16777216 --max-entries 20000`. Expected: exit 0, `identity-matched`, route `declared-note`.
- [ ] **Step 4: Docs audit.** `python3 scripts/maintenance/docs_audit.py --issues-snapshot <capture under a day old> --no-owning-job-check --json` on the head and on `origin/main` with one capture, diffed by (check, document, severity, detail). Expected: nothing new on the head.
- [ ] **Step 5: Gate.** `python3 scripts/gate/spec_gate.py --pr origin/main`. Expected: `spec gate ok`.
- [ ] **Step 6: Ready.** Tick each done_when line with its evidence, then mark the PR ready.

## Choices this plan makes where the spec leaves one open

- Order: the no-adjusted implementation merges first (Task 1); this branch rebases its reaction tests onto the vendor path and adds `av_reaction_fetch` to `AS_TRADED_DAILY_SOURCES`, as that spec's Design 6 item 1 asks.
- `exit_untracked` raises `SystemExit(2)` everywhere, so one test idiom covers modules whose `main` returns a code and those that exit themselves.
- `AV_SYMBOL_MAP` goes whole: every remaining entry was the identity, and `av_listed_symbol` keeps its behaviour.
- `calibrate_level_params.WATCHLIST_SQL` becomes the shared constant with the owner in the text, replacing the readers test's bound-owner pin (stocks#1887); recorded in the PR body.
- The reaction selection reads `[run_date - 67, run_date]`, so a report pending past 60 days is logged once, the week it crosses the bound, and never re-read after.
- `--force` and `--scope` leave `compute_earnings_reactions`; `--tickers` filters the selection and `--as-of` replays a run (CLAUDE.md 3.5).
- The weekly earnings window keeps its SQL shape and gains `- (:days_back || ' days')::interval`, so the existing SQLite adapter runs it.
- Top movers write through one connection-level upsert and delete (`gcp.database.upsert_dataframe` opens its own transaction per chunk); the test uses a recording engine rather than a database.
- The drop file is a second pinned allowance of the no-adjusted `.sql` guard.
