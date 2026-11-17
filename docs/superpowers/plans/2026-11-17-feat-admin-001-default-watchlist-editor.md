---
feat_id: FEAT-ADMIN-001
spec: docs/superpowers/specs/2026-11-16-feat-admin-001-default-watchlist-editor-r2.md
branch: feature/feat-admin-001-default-watchlist-editor
pr: null
status: ready
---

# An admin edits the default watchlist (r2): implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the order of the spec's frontmatter, [0] to [13].

**Goal:** Five admin-only API routes edit the default watchlist through one shared writer that Discord and `backfill-ticker` also use; an added ticker's as-traded daily and 1-minute history starts at once on two existing Cloud Run jobs and is read back from their executions and the stored bars; Discord's write subcommands require the Administrator permission and are hidden from other members.

**Architecture:** `gcp/fetchers/_watchlist.py` gains the writer (`add_default_ticker`, `remove_default_ticker`, `set_default_flags`, under one advisory lock, the history lease in the add's transaction) and the history functions (`plan_history`, `start_history_fetch`, `cancel_history_fetch`, `history_status`, `BUILDERS_NOT_COVERING`). `lib/ticker_info.check_symbol` tells an unlisted symbol from an unavailable check. `platform/api/routers/admin.py` adds the five routes with declared response models; `gcp/discord_interactions/main.py` routes `/watchlist add` and `remove` through the same writer as deferred replies behind an Administrator check; `scripts/discord/register_commands.py` hides `/watchlist` and adds `/watchlist-show`.

**Tech Stack:** Python 3, FastAPI and pydantic, SQLAlchemy `text()` through `gcp.database.get_engine`, `google.cloud.run_v2` (faked in tests through `sys.modules`, as `tests/gcp/test_discord_interactions.py:256-268` does), requests, pytest.

**Spec:** `docs/superpowers/specs/2026-11-16-feat-admin-001-default-watchlist-editor-r2.md` (approved, PR #1999; supersedes the #1981 spec). Read it beside this plan: Design 1 to 5 are the interfaces, the Capacity table the PR body's numbers, Close-out the deploy, IAM and live checks that follow the merge.

## Global Constraints

- Line anchors are `origin/main` 90c41e6d (2026-11-17); the spec's 060c89a0 anchors hold there for every file it cites outside `gcp/deploy.sh`. This branch is cut after the SPY/QQQ/IWM-only and no-adjusted implementations merge (Task 1), both of which edit `gcp/backfill_ticker.py`, `gcp/fetchers/_watchlist.py` and `gcp/fetchers/fetch_alphavantage_intraday.py`: re-read every anchor on the fork commit and locate edits by quoted content.
- Not in the PR's diff (done_when[12]): `gcp/deploy.sh`, `gcp/schema.sql`, `platform/deploy.sh`. No schema change, no IAM change, no deploy, no Discord registration call from this branch (Close-out).
- Exact values: ticker shape `^[A-Z0-9.]{1,10}$`; list cap 25 (`historical-signals-watchlist`, `scripts/run_historical_signals.py:91`); advisory lock `SELECT pg_advisory_xact_lock(hashtext('watchlists:default'))`; lease key `watchlist-history:<T>`, 60 s, the upsert statement of `_acquire_refresh_lease` (`platform/api/routers/admin.py:1449-1462`); sources `admin`, `discord-slash`, `discord-replay`; `HISTORY_FIRST_MONTH = '2015-01'`; `HISTORY_DAILY_FROM = '2016-05-02'`; symbol check: one `GLOBAL_QUOTE`, one attempt, 10 s timeout, dot sent as dash; execution listing `page_size=100`, at most 10 pages (1,000 executions) a job; Administrator bit `0x8`; refusal text `Only a server administrator can change the watchlist. /watchlist-show shows it.`; registration `default_member_permissions: "8"`.
- CLAUDE.md 3.7: a database error raises; a symbol-check outage is `unavailable`, never "not a symbol"; an execution listing error raises and is never `not_started`; a start that fails after the commit is reported `started: false` with its reason, never as a failed add.
- CLAUDE.md 3.10: every new route is a plain `def`.
- The render step, after any task that changes a file under `gcp/`, `lib/`, `scripts/` or `platform/api`:
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate -q` (expect 1 passed); stage whichever of the three changed.
- Before every commit: `python3 scripts/gate/spec_gate.py --commit`. Conventional commits, imperative, no AI attribution. Every new test has a red then green record in the PR body.

## done_when map

| done_when | What | Task |
|---|---|---|
| [0] | the shared writer, its errors, lock and lease | 3 |
| [1] | `check_symbol` | 2 |
| [2] | both history jobs send the dashed vendor symbol | 2 |
| [3] | `plan_history`, `start_history_fetch`, `cancel_history_fetch` | 4 |
| [4] | `history_status`, `BUILDERS_NOT_COVERING` | 5 |
| [5] | the five routes | 6 |
| [6] | Discord on the writer, the Administrator check | 7, 8 |
| [7] | the command registration | 8 |
| [8] | `backfill-ticker`: history from, partial today, the writer | 9 |
| [9] | the readers and writers inventory | 10 |
| [10] | the stage B wording | 11 |
| [11] | OpenAPI, route coverage, the operations in the PR body | 12 |
| [12] | `make test`, inventory, files not in the diff | 13 |
| [13] | catalog, traceability, two SITE notes, snapshot, docs audit, gate | 14 |

## Review Focus

- **Two adds of one ticker at once (a double press, or the panel and Discord).** The advisory lock serialises them and the lease is taken in the add's transaction, so one starts the history and the other answers `already_active` (or `lease held`). `test_concurrent_adds_start_one_history`, Task 3 (two threads over a recording engine whose lock blocks the second until the first commits).
- **The vendor's spelling of a share class.** `brk.b` is stored `BRK.B`, checked as `BRK-B`, and fetched as `BRK-B` by both jobs; the history status and the cancel read executions whose overrides name `BRK.B`. Tasks 2 and 4.
- **A Discord payload from outside a server or without permissions.** No `member`, `member.permissions` missing, `""`, `"8.0"`, `"-8"` or `"0x8"`: refused with the ephemeral reply, nothing called. Task 8.
- **Removing a ticker whose history is still running, and then the last one.** The remove cancels only that ticker's running executions and reports a cancel failure per execution; removing the last active row is 409 and writes nothing. Tasks 3, 4 and 6.
- **A status poll while a listing passes 1,000 executions, or after a re-add.** `unknown`, never `not_started`; an execution older than the latest add is ignored. Task 5.

## File map

| File | Change | Task |
|---|---|---|
| `lib/ticker_info.py` | `SymbolCheck`, `check_symbol` (beside `get_quote`, `:449`) | 2 |
| `gcp/backfill_ticker.py` | `av_daily_full` `:102-108`; `run` `:600`, `:615-627`; `add_to_watchlist` `:278-307` removed | 2, 9 |
| `gcp/fetchers/fetch_alphavantage_intraday.py` | `fetch_month` `:123-145` | 2 |
| `gcp/fetchers/_watchlist.py` | writer, errors, `WatchlistWrite`; history functions and types | 3, 4, 5 |
| `platform/api/routers/admin.py` | five routes and their models | 6 |
| `gcp/discord_interactions/main.py` | `/watchlist` handlers `:604-705`, dispatch `:948-954`, `/watchlist-show`, the Administrator check | 7, 8 |
| `scripts/discord/register_commands.py` | `COMMANDS` `:141-190` | 8 |
| `tests/gcp/test_watchlist_default_writes.py`, `tests/gcp/test_watchlist_history.py`, `tests/api/test_admin_default_watchlist.py`, `tests/scripts/test_discord_register_commands.py` | new | 2 to 8 |
| `tests/gcp/test_backfill_ticker.py`, `tests/gcp/test_intraday_as_traded.py`, `tests/gcp/test_discord_interactions.py` | new and updated cases | 2, 7, 8, 9 |
| `tests/meta/test_production_writers.py` | `test_no_code_dispatches_backfill_ticker` (`:2489-2503`), `INTRADAY_WRITER_JOB_NAME_FILES` (`:1889-1893`) | 4 |
| `tests/gcp/test_watchlist_readers_default_owner.py` | `WRITERS` (`:105-110`), `OWN_SQL_PINS` Discord entry (`:93-98`) | 10 |
| `tests/api/test_watchlist_default_lock.py`, `platform/api/routers/insights.py` | the 410 detail, only if #1937 is on `main` | 11 |
| `platform/api/openapi.json`, `tests/api/test_route_coverage.py` | regenerated; five `Req` rows | 12 |
| `docs/product/02`, `03`, `12`, `docs/review-evidence/site-source-snapshot.json`, 05-a/c/e inventory blocks | close and render | 14 |

## Capacity (CLAUDE.md rule 0; spec Capacity)

Copy into the PR body's Capacity section:

- **Volume:** one watchlist row per add; at SPY's depth (Decision 1) about 2,650 daily rows (about 1.9 MB) and up to about 2.2 million 1-minute rows (about 0.8 GB) for a ticker as liquid as SPY; 24-month bounded depth about 0.4 million rows (0.15 GB). At most 25 active tickers.
- **Velocity:** `POST` add: 1 vendor call, 4 SQL statements in one transaction (lock, count, INSERT, lease), 1 index read, 2 job starts. `GET` history (polled every 15 s while fetching): 2 execution listings (one page of 100 today, 8 and 5 executions; at most 10 pages each) and 3 index reads (latest add, daily min and max, 1-minute min and max; no count). History runs: 1 daily request; 143 monthly 1-minute requests at SPY's depth (24 bounded), one upsert each, paced at 0.4 s.
- **Wall-clock:** add 2 to 5 s (vendor at most 10 s; reads about 10 ms, the 1-minute bounds 9.9 ms, `db-query-tcjwr`; a job start not measured). Daily history about 1 minute (600 s task timeout). 1-minute history about 24 minutes at 10 s a month, at most about 69 minutes at 29 s (`intraday-bulk-backfill`, 86,400 s timeout, 20 x the high estimate).
- **Cost:** 145 vendor calls an add at SPY's depth (26 bounded), against 600 RPM purchased and 150 RPM a process; Cloud Run about $0.03 to $0.08 an add plus about $0.002 for the daily job, under $0.50 a month at 5 adds; Cloud SQL about 0.8 GB a liquid ticker, about $0.14 a month (list prices, not re-read).

---

### Task 1: Preconditions and the order of the three specs

Spec: § Order against work in progress; § Split and separate specs (FEAT-DEPLOY-001); § Close-out steps 1 and 2. Advances no done_when item; guards [2], [8] and [12].

**Files:** none on this branch.

- [ ] **Step 1: Code order (precondition).** The no-adjusted implementation (`docs/superpowers/specs/2026-11-16-feat-data-001-no-adjusted-prices-r2.md`) and the SPY/QQQ/IWM-only implementation (`docs/superpowers/specs/2026-11-16-feat-data-001-spy-qqq-iwm-only-r2.md`) are both on `main`, in that order (their plans' Task 1). Check on `origin/main`: `gcp/backfill_ticker.av_daily_full` sends `TIME_SERIES_DAILY`; `gcp.fetchers._watchlist` defines `price_fetch_universe` and `require_tracked`; `backfill_ticker.run` writes its watchlist row before `require_tracked`; `fetch_alphavantage_intraday.main` refuses an untracked `--symbol`. If not, stop: Tasks 2, 4 and 9 edit those lines.
- [ ] **Step 2: The DEFAULT partition is kept.** `gcp/schema.sql` on `origin/main` still declares `market_data_intraday_other PARTITION OF market_data_intraday DEFAULT` (`:164-165` today). If a spec B has dropped it, stop: an add needs a partition per ticker (spec Order).
- [ ] **Step 3: Stage B.** Record in the PR body whether #1937 (the 410 routes) is on `main` when this branch is cut; Task 11 depends on it.
- [ ] **Step 4: Close-out order, recorded in the PR body.** Deploy after the two FEAT-DATA-001 deploys; IAM (Close-out step 2, an owner step) before spec G's deploy; the FEAT-DEPLOY-001 follow-up adds `backfill-ticker` and `intraday-bulk-backfill` to `SETUP_IAM` in `platform/deploy.sh`, and #1977's spec C keeps `intraday-bulk-backfill` (Decision 2).
- [ ] **Step 5: Draft PR** after Task 2's commit: title `FEAT-ADMIN-001: an admin edits the default watchlist (API, one shared writer, history start)`, body with spec and plan paths, each done_when item as a `- [ ]` line starting with its text, the Capacity section above. Set `pr:` here in the next commit.

### Task 2: the symbol check and the vendor's spelling

Spec: § Design 2; § Design 3 (the dotted ticker bullet). Advances done_when[1], [2].

**Files:**
- Modify: `lib/ticker_info.py` (new beside `get_quote`, `:449-499`); `gcp/backfill_ticker.py:102-108`; `gcp/fetchers/fetch_alphavantage_intraday.py:123-145`
- Create: `tests/gcp/test_watchlist_default_writes.py`
- Test: `tests/gcp/test_backfill_ticker.py`, `tests/gcp/test_intraday_as_traded.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class SymbolCheck: status: str; price: float | None; latest_trading_day: str | None; reason: str | None` with `status` in `('listed', 'not_listed', 'unavailable')`; `check_symbol(ticker: str) -> SymbolCheck`: one `requests.get(_AV_BASE, params={'function': 'GLOBAL_QUOTE', 'symbol': ticker.upper().replace('.', '-'), 'apikey': key}, timeout=10)`, no retry; no API key configured is `unavailable` with that reason.

- [ ] **Step 1: Write the failing tests.**
  - `test_symbol_check_tells_unlisted_from_unavailable` (patch `requests.get` on `lib.ticker_info`): a filled quote (`{"Global Quote": {"01. symbol": "NVDA", "05. price": "162.85", "07. latest trading day": "2026-11-13"}}`) is `listed`, `price == 162.85`, `latest_trading_day == '2026-11-13'`; `{"Global Quote": {}}` is `not_listed`; `unavailable` with a non-empty reason for `{"Note": "x"}`, `{"Information": "x"}`, `{}` (no `Global Quote`), an `HTTPError` from `raise_for_status`, and `requests.Timeout`. `check_symbol('brk.b')` sends `symbol == 'BRK-B'`, makes exactly one call with `timeout == 10`. `get_quote`, `search_tickers` and `fetch_ticker_overview` keep their main behaviour: their existing tests run unchanged.
  - `tests/gcp/test_backfill_ticker.py::test_vendor_symbol_is_dashed`: over a recording `requests.get` answering a `TIME_SERIES_DAILY` reply, `av_daily_full('BRK.B', 'k')` sends `symbol == 'BRK-B'` and `av_daily_full('SPY', 'k')` sends `'SPY'`; `run()` with `BACKFILL_TICKER=BRK.B` (stubs as `test_run_fetches_and_writes_no_one_minute_bars`, the universe stub holding `BRK.B`) records daily rows keyed `ticker == 'BRK.B'`.
  - `tests/gcp/test_intraday_as_traded.py::test_vendor_symbol_is_dashed`: `fetch_month('BRK.B', 2015, 1, 'k')` sends `symbol == 'BRK-B'` and returns a frame with `ticker == 'BRK.B'`; `'SPY'` is sent as `'SPY'`.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_watchlist_default_writes.py tests/gcp/test_backfill_ticker.py tests/gcp/test_intraday_as_traded.py -k "symbol" -q`. Expected: FAIL (`check_symbol` missing; both jobs send `BRK.B`).
- [ ] **Step 3: Implement** `check_symbol`. In `av_daily_full` and `fetch_month`, the request's `symbol` is `fetch_market_data.av_listed_symbol(ticker)`; `fetch_month` imports it inside the function (`fetch_market_data` imports this module at load), and keeps `df['ticker'] = symbol` (`:178`), the dotted input. Nothing else changes spelling.
- [ ] **Step 4: Run** the Step 2 command and `python3 -m pytest tests/lib -q -k ticker_info` (expect all pass). Render step.
- [ ] **Step 5: Commit:** `feat(admin): check a symbol with the vendor and send share classes dashed`

### Task 3: one writer for the default list

Spec: § Design 1; § Design 4 (the lease inside the add's transaction); Decisions 4, 5, 9. Advances done_when[0].

**Files:**
- Modify: `gcp/fetchers/_watchlist.py` (new section after `remove_from_watchlist`, `:585`)
- Test: `tests/gcp/test_watchlist_default_writes.py`

**Interfaces:**
- Consumes: `lib.ticker_info.check_symbol`, `SymbolCheck` (Task 2).
- Produces: errors `InvalidTicker`, `SymbolNotListed`, `SymbolCheckUnavailable` (with `.check`), `WatchlistFull`, `LastActiveTicker` (all `ValueError` subclasses but `SymbolCheckUnavailable`, a `RuntimeError`); `@dataclass(frozen=True) class WatchlistWrite: action: str; ticker: str; in_brief: bool | None; in_insight: bool | None; signals: bool | None; source: str | None; added_at: datetime | None; removed_at: datetime | None; lease_acquired: bool = False`; `MAX_ACTIVE = 25`; `HISTORY_LEASE_PREFIX = 'watchlist-history:'`; `HISTORY_LEASE_COOLDOWN_S = 60`;
  - `add_default_ticker(ticker, *, source, in_brief=None, in_insight=None, signals=None, check=check_symbol) -> WatchlistWrite`: shape, then `check(ticker)`, then one `get_engine().begin()` transaction: the lock; `SELECT count(*) AS n, bool_or(ticker = :t) AS present FROM watchlists WHERE user_id = 'default' AND removed_at IS NULL`; `present` gives `already_active` (no further statement); `n >= MAX_ACTIVE` raises `WatchlistFull` (message names `historical-signals-watchlist`); else `INSERT INTO watchlists (user_id, ticker, source[, flags given]) VALUES ('default', ...) ON CONFLICT (user_id, ticker) DO UPDATE SET removed_at = NULL, source = EXCLUDED.source[, given flags] WHERE watchlists.removed_at IS NOT NULL RETURNING (xmax = 0) AS inserted, ticker, in_brief, in_insight, signals, source, added_at, removed_at`, then the lease upsert keyed `watchlist-history:<T>` (`added` or `reactivated`, with `lease_acquired` from its `RETURNING`).
  - `remove_default_ticker(ticker, *, source) -> WatchlistWrite`: the lock; the same count read; the ticker the only active row raises `LastActiveTicker`; `UPDATE watchlists SET removed_at = NOW(), source = :source WHERE user_id = 'default' AND ticker = :t AND removed_at IS NULL RETURNING ...`: `removed` or `not_active`.
  - `set_default_flags(ticker, *, source, in_brief=None, in_insight=None, signals=None) -> WatchlistWrite`: the lock; `SELECT ... FOR UPDATE` of the active row (`not_active` when none); every given flag equal to the stored one gives `unchanged` with no write; else one `UPDATE` of the given flags and `source`: `flags_set`.

- [ ] **Step 1: Write the failing tests** over a recording engine (`begin()` yields a connection that records each statement's text and parameters, answers by statement kind, and records commit or rollback by whether the block exited with an exception), patched as `gcp.database.get_engine`:
  - `test_writes_go_through_one_function`: `add_default_ticker('nvda', source='admin', in_brief=True, in_insight=False, signals=False, check=<stub answering listed>)` records, in order, the advisory lock, the count, one `INSERT ... ON CONFLICT (user_id, ticker) DO UPDATE ... WHERE watchlists.removed_at IS NOT NULL RETURNING` with `user_id 'default'`, `ticker 'NVDA'`, `source 'admin'` and the three flags, and the `admin_refresh_leases` upsert with `job == 'watchlist-history:NVDA'` and `cooldown == 60`, all in one `begin()`; returns `action == 'added'` and `lease_acquired` True; with `inserted` False it is `reactivated`; with `present` True it is `already_active`, no INSERT and no lease. A lease statement that raises after the INSERT: the block exits with the error (rollback; the recorder holds no commit) and the error propagates. `remove_default_ticker('NVDA', source='admin')`: one `UPDATE ... SET removed_at = NOW(), source = ...`, `removed`; no active row gives `not_active`. `set_default_flags('NVDA', source='discord-slash', in_brief=False)`: updates `in_brief` and `source` only, `flags_set`; the same value stored gives `unchanged` and no UPDATE; no active row gives `not_active`. Each of these raises before any recorded statement: `'BAD TICKER'`, `'TOOLONGTICKER1'`, `'BRK/B'` (`InvalidTicker`); a check answering `not_listed` (`SymbolNotListed`) or `unavailable` (`SymbolCheckUnavailable`). `WatchlistFull` (count 25, not present) and `LastActiveTicker` (count 1, the ticker present) are raised after the reads and before any write.
  - `test_concurrent_adds_start_one_history`: two threads add `NVDA` against a recording engine whose lock statement blocks the second thread until the first block exits; exactly one result has `lease_acquired` True and the other is `already_active`.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_watchlist_default_writes.py -q`. Expected: FAIL (`ImportError: add_default_ticker`).
- [ ] **Step 3: Implement** the names above. `add_to_watchlist` and `remove_from_watchlist` stay for the two web write routes (spec Design 1, last bullet). No function catches a database error.
- [ ] **Step 4: Run** the same command. Expected: all pass. Render step.
- [ ] **Step 5: Commit:** `feat(admin): one writer for the default watchlist, its lock and its history lease`

### Task 4: starting and cancelling a ticker's history

Spec: § Design 3 (`plan_history`, `start_history_fetch`, `cancel_history_fetch`); Decisions 1 to 3. Advances done_when[3].

**Files:**
- Modify: `gcp/fetchers/_watchlist.py`; `tests/meta/test_production_writers.py:2489-2503`, `:1889-1893`
- Create: `tests/gcp/test_watchlist_history.py`

**Interfaces:**
- Produces: `HISTORY_FIRST_MONTH = '2015-01'`; `HISTORY_DAILY_FROM = '2016-05-02'`; `HISTORY_JOBS = ('backfill-ticker', 'intraday-bulk-backfill')`; `MINUTE_BOUNDS_SQL = "SELECT min(ts) AS first_ts, max(ts) AS last_ts FROM market_data_intraday WHERE ticker = :t AND interval = '1min'"`; `@dataclass(frozen=True) class HistoryPlan: minute_from: str; daily_from: str` (`'YYYY-MM'`, `'YYYY-MM-DD'`); `@dataclass(frozen=True) class HistoryStart: job: str; started: bool; execution: str | None = None; reason: str | None = None`;
  - `plan_history(ticker, minute_bounds: tuple) -> HistoryPlan`: no first bar, or a first bar after `HISTORY_FIRST_MONTH`, plans from `HISTORY_FIRST_MONTH`; else from the month of the last bar (Eastern, `lib.eastern_time.market_date`); daily always `HISTORY_DAILY_FROM`.
  - `execution_names_ticker(execution, ticker) -> bool`: an env `BACKFILL_TICKER == ticker` or an arg `--symbol=<ticker>` in the execution's container template.
  - `start_history_fetch(ticker, plan, *, jobs_client=None, executions_client=None) -> list[HistoryStart]`, one entry per job in `HISTORY_JOBS` order; per job: list its executions (Task 5's reader) and skip with `started=False, reason='running: <name>'` when one running execution names the ticker; else one `run_job(request=RunJobRequest(name=..., overrides=...))`: `backfill-ticker` with env `BACKFILL_TICKER=<T>`, `BACKFILL_HISTORY_FROM=<plan.daily_from>`, `BACKFILL_INCLUDE_NEWS=false`, `BACKFILL_ADD_TO_WATCHLIST=false`; `intraday-bulk-backfill` with args `--symbol=<T>`, `--start-date=<plan.minute_from>-01`, `--force` and `task_count=1`. The execution is the last path segment of `op.metadata.name`; a missing one, or any dispatch error, is that job's `started=False` with the reason, and does not stop the other job.
  - `cancel_history_fetch(ticker, *, executions_client=None) -> tuple[list[str], list[dict]]`: cancels each running execution of the two jobs naming the ticker; returns the cancelled names and `{execution, reason}` per failure.

- [ ] **Step 1: Write the failing test** `test_plan_and_start` (a fake `google.cloud.run_v2` in `sys.modules`, the pattern of `tests/gcp/test_discord_interactions.py:256-268`, whose clients record requests):
  - `plan_history('NVDA', (None, None))` and `plan_history('NVDA', (<2024-01-02 14:30 UTC>, <2026-11-13 21:00 UTC>))` give `minute_from == '2015-01'`, `daily_from == '2016-05-02'`; a first bar `2015-01-02 14:05 UTC` and a last bar `2026-11-14 01:00 UTC` give `minute_from == '2026-11'`.
  - `start_history_fetch('NVDA', plan)` with no execution listed sends exactly two `RunJobRequest`s: `.../jobs/backfill-ticker` with the four env values above, and `.../jobs/intraday-bulk-backfill` with args `['--symbol=NVDA', '--start-date=2015-01-01', '--force']` and `task_count == 1`; returns both execution names.
  - A running `intraday-bulk-backfill` execution whose args name `--symbol=NVDA`: one request (the daily job's) and the intraday entry `started False` with a reason naming that execution.
  - A `run_job` raising, or an operation whose `metadata.name` is empty: that job's typed failure, and the other job's execution still returned.
  - `cancel_history_fetch('NVDA')` cancels the two running executions naming NVDA and no running execution naming SPY or any finished one; a cancel that raises is reported per execution.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_watchlist_history.py -k plan_and_start -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the names above (project and region read as `admin.py:1500-1509` reads them).
- [ ] **Step 4: Update the two dispatch guards** of `tests/meta/test_production_writers.py`, as their docstrings ask of a spec that adds a dispatcher: `test_no_code_dispatches_backfill_ticker` allows `gcp/fetchers/_watchlist.py` beside the job's own file (a constant naming the allowed dispatchers, with this spec's path in its comment); `INTRADAY_WRITER_JOB_NAME_FILES` gains `gcp/fetchers/_watchlist.py` (it names `intraday-bulk-backfill` and dispatches it). Say so in the PR body: the spec did not name these guards.
- [ ] **Step 5: Run** `python3 -m pytest tests/gcp/test_watchlist_history.py tests/meta/test_production_writers.py -q`. Expected: all pass. Render step.
- [ ] **Step 6: Commit:** `feat(admin): start and cancel an added ticker's daily and 1-minute history`

### Task 5: reading a ticker's history status

Spec: § Design 3 (`history_status`, `builders_not_covering`); Decision 10. Advances done_when[4].

**Files:**
- Modify: `gcp/fetchers/_watchlist.py`
- Test: `tests/gcp/test_watchlist_history.py`

**Interfaces:**
- Produces: `LATEST_ADD_SQL` (`SELECT max(effective_at) AS added_at FROM watchlist_history WHERE user_id = 'default' AND ticker = :t AND action = 'add'`); `DAILY_BOUNDS_SQL` (`SELECT min(date) AS first_date, max(date) AS last_date FROM market_data_daily WHERE ticker = :t`); `MAX_LISTED_EXECUTIONS = 1000`; `BUILDERS_NOT_COVERING: tuple[str, ...]`, the eight paths `gcp/research/strat_engine/strat_data_builder.py`, `gcp/research/p2_build_gamma_levels.py`, `gcp/research/p2_outcomes_grid.py`, `gcp/research/p7_build_multi_tf_features.py`, `gcp/build_intraday_flow.py`, `gcp/build_intraday_gex.py`, `gcp/build_options_daily_greeks.py`, `gcp/build_realtime_gex.py`; `@dataclass(frozen=True) class HistoryJobState: job: str; state: str; execution: str | None; created_at: datetime | None; reason: str | None`; `@dataclass(frozen=True) class HistoryStatus: ticker; on_watchlist: bool; plan: HistoryPlan; jobs: list[HistoryJobState]; daily: dict; minute: dict; state: str; builders_not_covering: tuple[str, ...]; as_of: datetime`;
  - `list_ticker_executions(job, ticker, since, *, executions_client=None) -> tuple[list, bool]` (the executions naming the ticker created at or after `since`, and whether the listing was read to its end), reading every page of `page_size=100` up to `MAX_LISTED_EXECUTIONS`;
  - `history_status(ticker, *, query=None, executions_client=None) -> HistoryStatus`; job states `not_started`, `running`, `succeeded`, `failed`, `cancelled`, `unknown` from the newest naming execution by `create_time`; combined `state` the first of `fetching`, `failed`, `unknown`, `incomplete`, `done_without_minute_bars`, `done` that applies (spec Design 3, verbatim rules); reads through `query_to_dataframe_strict`.

- [ ] **Step 1: Write the failing test** `test_status_reads_executions_and_bars`:
  - Execution listings stubbed per job in pages of 10: the ticker's execution followed by 25 of other tickers is still found and its state read (`succeeded`, `failed`, `cancelled`, `running` by the execution's counts and completion time); an execution of the ticker older than the latest add (`LATEST_ADD_SQL` stub) is ignored; a listing longer than 1,000 executions reads `unknown`, never `not_started`; a listing error raises.
  - The recorded SQL holds `min(` and `max(` reads and no `count(` over `market_data_intraday` or `market_data_daily`.
  - Combined state: one job running gives `fetching`; one failed gives `failed`; one dispatch made no execution (`not_started`) and no stored bars of that kind gives `incomplete` while the other job has `succeeded`; both `not_started` and no bars gives `incomplete`, never `done`; the 1-minute job `succeeded` with no 1-minute bar gives `done_without_minute_bars`; both succeeded with bars covering the plan gives `done`.
  - `BUILDERS_NOT_COVERING` has the eight paths, and for each the test reads, with `ast`, a module-level `TICKERS_DEFAULT` or `TICKERS` assigned a list or tuple literal of exactly `{'SPY', 'QQQ', 'IWM'}`.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_watchlist_history.py -k status -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the names above. `start_history_fetch` (Task 4) reads running executions through `list_ticker_executions`.
- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_watchlist_history.py -q`. Expected: all pass. Render step.
- [ ] **Step 5: Commit:** `feat(admin): read an added ticker's history from its executions and stored bars`

### Task 6: the five admin routes

Spec: § Design 4; Decisions 3, 4, 9. Advances done_when[5].

**Files:**
- Modify: `platform/api/routers/admin.py` (after the data-source refresh route, which ends the file at `:1580`)
- Create: `tests/api/test_admin_default_watchlist.py`

**Interfaces:**
- Consumes: Tasks 3 to 5; `_require_admin` (`:52-66`), `_acquire_refresh_lease` (`:1437-1463`), `_release_refresh_lease` (`:1466-1486`).
- Produces (pydantic, all declared as `response_model`): `AdminWatchlistAddRequest {ticker: str, in_brief: bool, in_insight: bool, signals: bool}`; `AdminWatchlistFlagsRequest {in_brief: bool | None, in_insight: bool | None, signals: bool | None}`; `AdminWatchlistRow`; `AdminSymbolCheck`; `AdminHistoryPlan`; `AdminHistoryStart {job, started, execution, reason}`; `AdminWatchlistAddResponse {row, symbol_check, plan, history: list[AdminHistoryStart]}`; `AdminWatchlistRowResponse {row}`; `AdminWatchlistRemoveResponse {row, cancelled: list[str], cancel_failures: list[{execution, reason}]}`; `AdminHistoryJobState`; `AdminWatchlistHistoryResponse {ticker, on_watchlist, plan, jobs, daily: {first_date, last_date}, minute: {first_ts, last_ts}, state, builders_not_covering, as_of}`; `AdminWatchlistHistoryStartResponse {ticker, plan, history}`.
- Routes, each a plain `def` calling `_require_admin(request)` first: `POST /api/admin/watchlist/default` (201), `PATCH /api/admin/watchlist/default/{ticker}`, `DELETE /api/admin/watchlist/default/{ticker}`, `GET /api/admin/watchlist/default/{ticker}/history`, `POST /api/admin/watchlist/default/{ticker}/history` (202). Answers as the spec's route table; the `POST` add runs `check_symbol` itself and passes its result to `add_default_ticker` through `check`, so the response carries the check.

- [ ] **Step 1: Write the failing tests** in `tests/api/test_admin_default_watchlist.py`, with the admin helpers of `tests/api/test_admin_users_datasources.py:62-90` and recorders patched over `gcp.fetchers._watchlist` (every route must reach them) and under `gcp.database.get_engine`:
  - every route answers 401 without sign-in and 403 for a non-admin;
  - `POST`: 201 with `row`, `symbol_check`, `plan` and two `history` entries; 409 when `already_active`, 409 on `WatchlistFull`; 422 for a missing boolean, 422 for `not_listed`; 503 for an unavailable check, for a database error, and for a lease statement failing after the INSERT in the same transaction, each with nothing committed, after which a retry answers 201 (not 409); a start failing after the commit is a 201 whose entry says `started False` with the reason, and the same with `_release_refresh_lease` then failing;
  - `DELETE`: 200 with `removed_at`, `cancelled` and `cancel_failures`; 404 not active; 409 last active ticker;
  - `PATCH`: 200, 404;
  - `GET .../history`: 200 (and `state == 'unknown'` when a listing passes 1,000), 503 when the executions read raises;
  - `POST .../history`: 202; 429 inside the lease (`_acquire_refresh_lease` False); 404 not active.
- [ ] **Step 2: Run** `python3 -m pytest tests/api/test_admin_default_watchlist.py -q`. Expected: FAIL (404 for every route).
- [ ] **Step 3: Implement** the models and routes. Each write logs `admin watchlist: <action> <ticker> flags=<...> by <email>`, each start or cancel its execution names.
- [ ] **Step 4: Run** the same command. Expected: all pass. Render step (05-e gains five routes).
- [ ] **Step 5: Commit:** `feat(admin): admin routes to add, remove and reflag default watchlist tickers`

### Task 7: Discord `/watchlist add` and `remove` on the shared writer

Spec: § Design 5 (the writer bullet, one history fetch per ticker, deferred replies, reply texts); Decision 6. Advances done_when[6] (writer half).

**Files:**
- Modify: `gcp/discord_interactions/main.py:604-705` (handlers), `:948-954` (dispatch)
- Test: `tests/gcp/test_discord_interactions.py:498-660`

**Interfaces:**
- Consumes: `add_default_ticker`, `set_default_flags`, `remove_default_ticker`, `start_history_fetch`, `cancel_history_fetch`, `plan_history`, `check_symbol`.
- Produces: `watchlist_write_in_background(sub: str, opts: dict, app_id: str, token: str) -> None`, which does the work and edits the deferred reply through `edit_deferred_reply` (`:208`).

- [ ] **Step 1: Rewrite the watchlist cases** of `tests/gcp/test_discord_interactions.py` (`:498-660`) over patched recorders: a signed `/watchlist add NVDA` from an administrator (Task 8 adds the check; this task's payloads already carry `member.permissions '8'`) answers type 5 and the background edit names NVDA, its flags and the two execution names; `add_default_ticker`, `set_default_flags` (on `already_active` with flags given) and `remove_default_ticker` are called with `source='discord-slash'`; `remove` also calls `cancel_history_fetch`. Reply texts for added, already present, removed and not in the list stay as on main; `not_listed` gets a reply naming the vendor's answer and nothing is written; an unavailable check gets its own text. A repeat add while a history execution naming NVDA runs (listing stubbed) starts nothing and the reply names that execution. `/watchlist list` stays an immediate type 4 reply.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_discord_interactions.py -k watchlist -q`. Expected: FAIL.
- [ ] **Step 3: Implement:** `add` and `remove` return `DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE` and queue `watchlist_write_in_background` (the `/replay-signals` pattern, `:930-944`); the handler's own `INSERT` and `UPDATE` go; `_watchlist_list` stays (its `OWN_SQL` pin, Task 10).
- [ ] **Step 4: Run** the same command. Expected: all pass. Render step.
- [ ] **Step 5: Commit:** `feat(admin): Discord watchlist writes go through the shared writer and start the history`

### Task 8: Administrator only, and the registration

Spec: § Design 5 (authorization, hidden from non-admins); Decisions 11, 12. Advances done_when[6] (`TestWatchlistAdminOnly`), [7].

**Files:**
- Modify: `gcp/discord_interactions/main.py` (constant beside `:60-70`; the `watchlist` arm `:948-954`; a `watchlist-show` arm); `scripts/discord/register_commands.py:141-190`
- Test: `tests/gcp/test_discord_interactions.py` (class `TestWatchlistAdminOnly`); create `tests/scripts/test_discord_register_commands.py`

**Interfaces:**
- Produces: `ADMINISTRATOR = 0x8`; `is_administrator(payload: dict) -> bool` (False when `member` is absent, `member.permissions` absent, empty or not `str.isdecimal()`; else `int(...) & ADMINISTRATOR != 0`); `WATCHLIST_ADMIN_REFUSAL = "Only a server administrator can change the watchlist. /watchlist-show shows it."`.

- [ ] **Step 1: Write the failing tests.**
  - `TestWatchlistAdminOnly`: signed `/watchlist add` and `/watchlist remove` with `member.permissions` `'8'` and `'2147483656'` proceed (type 5); with `'0'`, `'2147483648'`, no `member` (a DM, `user` only), `permissions` missing, `''`, `'8.0'`, `'-8'` and `'0x8'` each get `{"type": 4, "data": {"content": WATCHLIST_ADMIN_REFUSAL, "flags": 64}}` and call no `check_symbol`, writer, start or cancel (recorders). The source of `gcp/discord_interactions/main.py` names none of `DISCORD_ALLOWED_GUILD_ID`, `DISCORD_WATCHLIST_ROLE_ID`, `DISCORD_WATCHLIST_USER_IDS`, and the check passes with none in the environment. `/watchlist list` and `/watchlist-show` answer the list (type 4) for a member without the bit and for a DM.
  - `tests/scripts/test_discord_register_commands.py`: in `COMMANDS` the `watchlist` command has `default_member_permissions == "8"` (a `str`) and its `add`, `remove` and `list` subcommands equal main's (literal copies in the test); a top-level `watchlist-show` with no `options` and no `default_member_permissions`; no other command has the field; `register()` with `requests.put` recorded sends exactly `COMMANDS`.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_discord_interactions.py -k AdminOnly tests/scripts/test_discord_register_commands.py -q`. Expected: FAIL (a non-admin add writes on main; no field, no command).
- [ ] **Step 3: Implement.** The `watchlist` arm checks `is_administrator(payload)` for `add` and `remove` before anything else and returns `_ephemeral_reply(WATCHLIST_ADMIN_REFUSAL)`; `list` is not checked; `watchlist-show` answers `_watchlist_list()` immediately. Registration as above.
- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_discord_interactions.py tests/scripts/test_discord_register_commands.py -q`. Expected: all pass. Render step.
- [ ] **Step 5: Commit:** `feat(admin): only a Discord administrator changes the watchlist; /watchlist-show reads it`

### Task 9: `backfill-ticker`: history from a date, no partial session, the shared writer

Spec: § Design 6. Advances done_when[8].

**Files:**
- Modify: `gcp/backfill_ticker.py:278-307` (removed), `:600`, `:615-627`, the watchlist step the SPY/QQQ/IWM-only PR moved before `require_tracked`
- Test: `tests/gcp/test_backfill_ticker.py`

- [ ] **Step 1: Write the failing test** `test_history_from_and_partial_today` (stubs as `test_run_fetches_and_writes_no_one_minute_bars`, the daily reply spanning 2016-04-28 to today): with `BACKFILL_HISTORY_FROM=2016-05-02` the recorded daily frame's first date is 2016-05-02 and no row is earlier; unset, `BACKFILL_HISTORY_DAYS=800` keeps the last 800 rows as on main; with the clock patched to 15:00 ET on a session day no row for that day is written, at 16:30 ET it is; `BACKFILL_ADD_TO_WATCHLIST=true` calls `add_default_ticker` with `source='discord-replay'` (recorder) and no `INSERT INTO watchlists` text is left in the file.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_backfill_ticker.py -k history_from -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** `BACKFILL_HISTORY_FROM` (validated `YYYY-MM-DD`, else exit 1 before any request) selects `daily[daily.date >= from]`; unset keeps `tail(history_days)`. Before the write, `fetch_market_data._exclude_partial_today(frame, market_today(), eastern_now().time())`. The watchlist step calls `add_default_ticker(ticker, source='discord-replay')`; the local `add_to_watchlist` goes.
- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_backfill_ticker.py -q`. Expected: all pass. Render step.
- [ ] **Step 5: Commit:** `feat(data): backfill-ticker takes a history start date and never stores a partial session`

### Task 10: the readers and writers inventory

Spec: § Design 7. Advances done_when[9].

**Files:**
- Modify: `tests/gcp/test_watchlist_readers_default_owner.py:105-110` (`WRITERS`), `:93-98` (the Discord `OWN_SQL_PINS` entry, if Task 7 moved its text)

- [ ] **Step 1:** Set `WRITERS = {"gcp/fetchers/_watchlist.py", "gcp/schema.sql"}` and keep `/watchlist list`'s pins. Add an assertion that `gcp/discord_interactions/main.py` and `gcp/backfill_ticker.py` hold no `INSERT INTO watchlists` or `UPDATE watchlists` (the module's `WRITE_STATEMENT` regex).
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_watchlist_readers_default_owner.py -q`. Expected: pass (it fails on the merge base, where both files write; record that run).
- [ ] **Step 3: Commit:** `test(admin): the shared writer and the schema are the only watchlist writers`

### Task 11: the stage B wording

Spec: § Design 8; Decision 8. Advances done_when[10].

**Files:**
- Modify (only if #1937 is on `main`): `platform/api/routers/insights.py` (the two 410 details); `tests/api/test_watchlist_default_lock.py`

- [ ] **Step 1:** If the two web write routes answer 410 on this branch's base, change both details to `The default watchlist is edited on the Admin page (Default watchlist tab) or in Discord (/watchlist add, /watchlist remove); the web app keeps per-user lists at /api/me/watchlist.` and assert that exact text in `tests/api/test_watchlist_default_lock.py`; run it (expect FAIL before, PASS after). If they do not, change nothing and record in the PR body that #1937 is to be re-cut with this wording (Decision 8, the owner's call).
- [ ] **Step 2: Run** `python3 -m pytest tests/api/test_watchlist_default_lock.py -q`. Expected: pass.
- [ ] **Step 3: Commit** (only when Step 1 changed code): `fix(api): the 410 detail names the Admin page beside Discord`

### Task 12: OpenAPI, route coverage, the operations for solyra

Spec: § Design 4 (declared models, the regenerated document). Advances done_when[11].

**Files:**
- Modify: `platform/api/openapi.json` (regenerated); `tests/api/test_route_coverage.py` (the admin block, `:352-362`)

- [ ] **Step 1:** Add five `Req` rows for the new operations; against the coverage harness's dead backend each answers 503 (the symbol check or the database unavailable) with a note saying which; request bodies valid for the models.
- [ ] **Step 2:** `python3 scripts/export_openapi.py`; `python3 -m pytest tests/api/test_openapi_snapshot.py tests/api/test_route_coverage.py -q`. Expected: all pass (the snapshot test fails before the export; record it).
- [ ] **Step 3:** PR body: the five operations with their response models, for solyra's `npm run contract:sync`.
- [ ] **Step 4: Commit:** `chore(api): regenerate the OpenAPI document for the default watchlist routes`

### Task 13: `make test`, the inventory, the files left alone

Spec: done_when[12]. Advances done_when[12].

- [ ] **Step 1:** `make test`. Expected: exit 0.
- [ ] **Step 2:** Render step; `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` passes; commit any changed block: `docs(admin): re-render the inventory for the default watchlist routes`.
- [ ] **Step 3:** `git diff --name-only origin/main...HEAD -- gcp/deploy.sh gcp/schema.sql platform/deploy.sh` prints nothing.

### Task 14: close

Spec: § Design 9; done_when[13]. Closes done_when[13].

- [ ] **Step 1: Catalog.** FEAT-ADMIN-001 record (`docs/product/02-FEATURE-CATALOG.md:444`): Status gains "default watchlist editable by an admin through the API and Discord; history start and status (#<PR>), deploy and IAM pending", Last reviewed the head commit's date. No other record.
- [ ] **Step 2: Traceability.** This PR under `### FEAT-ADMIN-001` of `docs/product/12-PR-ISSUE-TRACEABILITY.md` (`:708`).
- [ ] **Step 3: Site notes.** `produce` once to read the identity (`python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`, then `git checkout -- docs/review-evidence/site-source-snapshot.json`). Add `(FEAT-ADMIN-001, ADMIN-01)` and `(FEAT-ADMIN-001, INSIGHTS-09)` rows to `## Implementation-source notes` of `docs/product/03-SITE-TRACEABILITY.md`, each `source_identity_sha256=<hash>; ` then what the source now does (ADMIN-01: five admin routes in `platform/api/routers/admin.py` add, remove and reflag the default list and start and read an added ticker's history; INSIGHTS-09: the default list is written by one writer in `gcp/fetchers/_watchlist.py`, a symbol is checked by `lib/ticker_info.check_symbol`), claiming no deployed change. Commit; `produce` again; commit the sidecar; `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 16777216 --max-entries 20000`. Expected: exit 0, `identity-matched`, route `declared-note`.
- [ ] **Step 4: Canvas.** The spec lists `https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN`, which `docs/product/canvases.yml:53-55` marks `mode: report-only`: add `Canvas check pending (report-only): https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN` to the PR body.
- [ ] **Step 5: Docs audit.** `python3 scripts/maintenance/docs_audit.py --issues-snapshot <capture under a day old> --no-owning-job-check --json` on the head and on `origin/main` with one capture, diffed by (check, document, severity, detail). Expected: nothing new on the head.
- [ ] **Step 6: Gate.** `python3 scripts/gate/spec_gate.py --pr origin/main`. Expected: `spec gate ok`.
- [ ] **Step 7: Ready.** Tick each done_when line with its evidence, then mark the PR ready.

## Choices this plan makes where the spec leaves one open

- Order: this branch is cut after the no-adjusted and SPY/QQQ/IWM-only implementations are on `main` (spec Order; Task 1 checks it).
- The add's count read also answers whether the ticker is active (`bool_or(ticker = :t)`), so `already_active` issues no INSERT and no lease.
- `set_default_flags` reads the active row `FOR UPDATE` under the lock and writes nothing when every given flag already holds (`unchanged`).
- `check_symbol` without a configured API key is `unavailable` with that reason (the add answers 503), not an exception.
- The run API clients are injectable keywords (`jobs_client`, `executions_client`) and tests fake `google.cloud.run_v2` through `sys.modules`, since the package is not in every test environment.
- An execution's state is read from its counts and completion time: no completion time is `running`; then `cancelled`, `failed`, `succeeded` by count.
- The two dispatch guards of `tests/meta/test_production_writers.py` admit `gcp/fetchers/_watchlist.py` as a dispatcher of `backfill-ticker` and a holder of `intraday-bulk-backfill` (Task 4); the spec did not name them.
- `fetch_month` imports `av_listed_symbol` inside the function to avoid the import cycle with `fetch_market_data`.
- `BACKFILL_HISTORY_FROM` that is not a date exits 1 before any request.
