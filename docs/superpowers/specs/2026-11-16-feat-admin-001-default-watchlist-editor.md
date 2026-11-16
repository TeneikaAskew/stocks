---
feat_id: FEAT-ADMIN-001
req_ids: [REQ-AUTHZ-001, REQ-CAP-001, REQ-DATA-001, REQ-OBS-001]
issues: []
canvases:
  - https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN
site_source_notes: [ADMIN-01, INSIGHTS-09]
done_when:
  - "tests/gcp/test_watchlist_default_writes.py::test_writes_go_through_one_function passes: over a recording engine, gcp.fetchers._watchlist.add_default_ticker('nvda', source='admin', in_brief=True, in_insight=False, signals=False, check=<stub answering listed>) takes pg_advisory_xact_lock for the default list, reads the active count and writes one INSERT ... ON CONFLICT (user_id, ticker) DO UPDATE ... WHERE watchlists.removed_at IS NOT NULL RETURNING for user_id 'default', ticker 'NVDA', source 'admin' and the three flags, all in one transaction, and returns action 'added' ('reactivated' for a removed row; 'already_active' and no write for an active one); remove_default_ticker sets removed_at and source in one UPDATE of an active row and returns 'removed' or 'not_active'; set_default_flags updates only the flags it is given, and source, on an active row and returns 'flags_set', 'unchanged' or 'not_active'; a ticker not matching ^[A-Z0-9.]{1,10}$ raises InvalidTicker, a check answering not_listed raises SymbolNotListed, a check answering unavailable raises SymbolCheckUnavailable, an add that would make the active list longer than 25 raises WatchlistFull naming historical-signals-watchlist, and removing the last active row raises LastActiveTicker, each before any write (on main none of these functions exists)"
  - "tests/gcp/test_watchlist_default_writes.py::test_symbol_check_tells_unlisted_from_unavailable passes: lib.ticker_info.check_symbol over stubbed GLOBAL_QUOTE replies answers listed, with the price and the latest trading day, for a filled 'Global Quote'; not_listed for {'Global Quote': {}}; and unavailable, with the reason, for a reply holding Note or Information, a reply without 'Global Quote', an HTTP error and a timeout; it requests BRK.B as BRK-B and makes one attempt with a 10 s timeout; get_quote, search_tickers and fetch_ticker_overview answer as on main"
  - "tests/gcp/test_watchlist_history.py::test_plan_and_start passes: plan_history with no stored 1-minute bar, or with a first bar later than 2015-01, plans 1-minute months from 2015-01 and daily rows from 2016-05-02, and with a first bar in 2015-01 plans 1-minute months from the month of the latest stored bar; start_history_fetch, over a recorded run_v2 client, sends exactly two RunJobRequests: backfill-ticker with env BACKFILL_TICKER, BACKFILL_HISTORY_FROM=2016-05-02, BACKFILL_INCLUDE_NEWS=false and BACKFILL_ADD_TO_WATCHLIST=false, and intraday-bulk-backfill with args --symbol=<ticker>, --start-date=<first day of the planned month> and --force and task_count 1; it returns both execution names; a dispatch error, or an operation whose metadata names no execution, is that job's typed start failure and does not hide the other job's execution; cancel_history_fetch cancels only running executions whose overrides name the ticker"
  - "tests/gcp/test_watchlist_history.py::test_status_reads_executions_and_bars passes: history_status over stubbed execution listings and stubbed reads reports each job as not_started, running, succeeded, failed or cancelled from the newest execution whose overrides name the ticker, the daily first and last date and the 1-minute first and last bar from min and max reads (its SQL holds no count over market_data_intraday or market_data_daily), and the combined state fetching, done, done_without_minute_bars or failed; a listing error raises and is never reported as not_started; builders_not_covering names exactly the eight files whose ticker constant is fixed in code (strat_data_builder.py, p2_build_gamma_levels.py, p2_outcomes_grid.py, p7_build_multi_tf_features.py, build_intraday_flow.py, build_intraday_gex.py, build_options_daily_greeks.py, build_realtime_gex.py), which the test reads with ast from those files"
  - "tests/api/test_admin_default_watchlist.py passes: POST /api/admin/watchlist/default, PATCH and DELETE /api/admin/watchlist/default/{ticker}, and GET and POST /api/admin/watchlist/default/{ticker}/history answer 401 without sign-in and 403 for a non-admin; POST answers 201 with the row, the symbol check and the two history starts, 409 for an active ticker and for a full list, 422 for a bad shape and for an unlisted symbol, 503 when the symbol check or the database is unavailable, and writes nothing in each refusal (recorders under gcp.database.get_engine); a history start that fails is a 201 whose start entry says so with its reason; DELETE answers 200 with removed_at and the cancelled executions, 404 for a ticker that is not active and 409 for the last active ticker; PATCH answers 200 or 404; GET history answers 200, or 503 when the executions read fails; POST history answers 202, or 429 inside the 60 s lease; each route reaches the shared function of gcp.fetchers._watchlist (patched recorders)"
  - "tests/gcp/test_discord_interactions.py passes with /watchlist add and /watchlist remove answered as deferred replies whose edit names the ticker, its flags and, for an add, the two history executions; both call add_default_ticker, set_default_flags and remove_default_ticker with source 'discord-slash' (patched recorders); the existing reply texts for added, already present, removed and not in the list are kept; an unlisted symbol gets a reply naming the vendor's answer and nothing is written"
  - "tests/gcp/test_backfill_ticker.py::test_history_from_and_partial_today passes: with BACKFILL_HISTORY_FROM=2016-05-02 the job writes only daily rows dated on or after it (BACKFILL_HISTORY_DAYS applies when it is unset, as on main); run before 16:15 ET it writes no row for the current session; BACKFILL_ADD_TO_WATCHLIST=true writes through add_default_ticker with source 'discord-replay'"
  - "tests/gcp/test_watchlist_readers_default_owner.py passes with WRITERS equal to gcp/fetchers/_watchlist.py and gcp/schema.sql: gcp/discord_interactions/main.py and gcp/backfill_ticker.py hold no INSERT INTO or UPDATE watchlists statement of their own (on main both do)"
  - "tests/api/test_watchlist_default_lock.py passes; when the stage B routes answer 410 on the PR's base (stocks #1937), their detail names the Default watchlist tab of the Admin page beside Discord /watchlist and the test asserts that text"
  - "platform/api/openapi.json is regenerated by scripts/export_openapi.py and tests/api/test_openapi_snapshot.py passes; tests/api/test_route_coverage.py requests each of the five new operations; the PR body lists the five operations and their response models for solyra's npm run contract:sync"
  - "make test passes on the PR head; the generated inventory blocks are re-rendered with scripts/maintenance/doc_inventory.py and tests/scripts/test_check_generated_docs.py passes; gcp/deploy.sh, gcp/schema.sql and platform/deploy.sh are not in the PR's diff"
  - "The FEAT-ADMIN-001 catalog record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the implementation-source notes of 03-SITE-TRACEABILITY.md hold a (FEAT-ADMIN-001, ADMIN-01) row and a (FEAT-ADMIN-001, INSIGHTS-09) row each beginning with the current source hash, docs/review-evidence/site-source-snapshot.json is regenerated and scripts/maintenance/doc_source_snapshot.py verify accepts it, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing that origin/main does not, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: draft
supersedes: null
---

# An admin edits the default watchlist: API routes, one shared writer, and the added ticker's history

## The owner's requirement

T, 2026-11-16, on the draft of `docs/superpowers/specs/2026-11-16-feat-data-001-spy-qqq-iwm-only.md` (stocks #1977), offered three choices (clean up and stop fetching other tickers; clean up only and keep fetching them as traded; clean up and store history for every ticker on a personal watchlist):

> "1 and in solyra the ability for an admin to adjust the default watch lists"

That spec records it as its Decision 16: the default watchlist is the one list that decides which tickers are fetched and stored (its Decision 1 and Design 1 to 8), so it gets an editor on `/admin`. Its recommendation, written into this spec: adding a ticker starts its as-traded history fetch (daily and 1-minute) at once, so it does not wait for the nightly run; removing a ticker stops its fetch from the next run and deletes nothing, since a delete cannot be undone and a re-add would otherwise refetch the whole history. Its "Split and separate specs" names this spec F (the API) and spec G (the solyra panel). Every daily fetch is as traded after the companion spec `docs/superpowers/specs/2026-11-16-feat-data-001-no-adjusted-prices.md` (stocks #1978): `TIME_SERIES_DAILY`, no adjusted close.

## Scope

- **Code (one PR):** five admin-only routes in `platform/api/routers/admin.py`; one shared writer for the default list in `gcp/fetchers/_watchlist.py` that the routes, Discord `/watchlist` and `backfill-ticker` all call; a typed symbol check in `lib/ticker_info.py`; the added ticker's history started through two existing Cloud Run jobs and read back for a status route; the regenerated OpenAPI document.
- **Not here:** the panel (spec G, solyra), IAM grants and deploy scripts (Close-out and a FEAT-DEPLOY-001 spec, below), any schema change.
- Code references are to stocks `main` a34bbd40 (2026-11-16). "Read" means read from the code or a listing; "run" means executed, with its execution name; anything else says "not checked". Every production read was made on 2026-11-16 without `--commit`.

## Problem

### 1. The default list is written in three places and edited from none on the web

Read:

| Writer | Where | What it does |
|---|---|---|
| Discord `/watchlist add` | `gcp/discord_interactions/main.py:604-678` | checks `isalnum()` only (rejects BRK.B), no vendor check; its own `INSERT ... ON CONFLICT (user_id, ticker) DO UPDATE SET removed_at = NULL` and, when given, the brief and insight flags (re-applied on an active row); source `discord-slash`; no `signals` option; starts no fetch |
| Discord `/watchlist remove` | `:681-705` | its own `UPDATE watchlists SET removed_at = NOW()`; source untouched |
| `backfill-ticker` with `BACKFILL_ADD_TO_WATCHLIST=true` | `gcp/backfill_ticker.py:278-307`, called at `:668-671` | its own INSERT with source `discord-replay`, keeping the old source on a re-add |
| `gcp.fetchers._watchlist.add_to_watchlist` and `remove_from_watchlist` | `gcp/fetchers/_watchlist.py:492-585` | through `lib.agents.model_routing.connect()`, called only by the two web write routes of `platform/api/routers/insights.py:607-713`, which write the caller's own rows (`_watchlist_owner`, `:61-75`); the approved stage B spec turns both routes into 410 (open PR #1937) |

The web reads the list only: `GET /api/insights/watchlist/default` (`platform/api/routers/insights.py:782-815`, strict read, 503 on an outage), shown in solyra's `DefaultWatchlistSection.tsx` under "Managed in Discord".

The `watchlists` table (`gcp/schema.sql:2539-2562`) has the primary key `(user_id, ticker)`, `source VARCHAR(20)` and the three flags (`signals` added at `:2612-2642`). Its trigger `trg_watchlists_membership` (`:3185-3187`, function `watchlists_record_membership` at `:2933`) writes one `watchlist_history` row (`:2775-2831`) per add, remove and flag change of an active row, carrying `user_id`, `ticker`, `action` (`add`, `remove`, `flags`), `effective_at`, the row's `source` and the three flags. It records no actor. A TRUNCATE of `watchlists` is refused (`:3343-3345`). Run, `db-query-rcftd`: 18 default rows, 3 active (IWM, QQQ, SPY, all three flags on, source `seed`); `watchlist_history` holds 9 `remove` rows with source `avgo-peer` and 3 with `discord-replay` for the removals of 2026-11-13: a remove records the source of the add, so the history cannot say who removed a ticker.

### 2. What fetches one ticker's history as traded today

Read, with runs where named:

| Job | Code | Settings (read: `gcloud run jobs describe`) | Vendor calls for one ticker |
|---|---|---|---|
| `backfill-ticker` | `gcp/backfill_ticker.py`; env `BACKFILL_TICKER`, `BACKFILL_HISTORY_DAYS` (default 800, `:600`), `BACKFILL_INCLUDE_NEWS`, `BACKFILL_ADD_TO_WATCHLIST`; one `outputsize=full` daily request (`:102-131`), keeps the last N rows (`:615-627`), computes daily indicators over them; writes no 1-minute bar (`:629-633`) | 600 s task timeout, 0 retries, 1 task, runs as `trading-runner@` | 1 daily, plus 1 news when `BACKFILL_INCLUDE_NEWS` is true. Five runs of 2026-05-04 took 22 to 35 s each (listing) |
| `intraday-bulk-backfill` | `python -m gcp.fetchers.fetch_alphavantage_intraday`, default args `--symbols-file .../earnings_universe.txt --start-date 2024-01-01` (`gcp/deploy.sh:3705-3771`) | 86,400 s, 0 retries, 4 tasks, parallelism 4 | one `TIME_SERIES_INTRADAY` month per request (`process_symbol`, `fetch_alphavantage_intraday.py:249-353`), oldest month first (`get_trading_months`, `:94-103`) |
| `fetch-alphavantage-intraday` | the same module | 3,600 s, 1 retry, 1 task | the same |

- The intraday module skips a ticker with 100,000 or more rows since 2024-01-01 unless `--force` (`:210-246`, `:285-288`). A ticker whose every month is refused by the vendor is a "dead ticker": logged, a GitHub issue filed, and the run exits 0 (`:1650-1695`); only a raised error exits 1 (`:1707-1709`).
- `backfill-ticker` writes the vendor's current-day bar during the session: unlike `fetch_market_data._run_backfill` it has no `_exclude_partial_today` (`fetch_market_data.py:1029-1045`, read).
- An execution keeps its overrides: `backfill-ticker-z8s7h` (2026-05-04) shows env `BACKFILL_TICKER=MCK`, `BACKFILL_HISTORY_DAYS=1000`, `BACKFILL_INCLUDE_NEWS=false`, and `intraday-bulk-backfill-bdl7p` shows its override args (run: `gcloud run jobs executions describe`). So the executions of a ticker can be found from the jobs alone.

### 3. How deep SPY's history goes

Run, `db-query-rcftd`:

| | First | Last | Rows |
|---|---|---|---|
| SPY 1-minute | 2015-01-02 09:05 UTC | 2026-11-14 01:00 UTC | `market_data_intraday_spy` about 2.50 million (`pg_class`), 911,294,464 bytes with indexes, so about 364 bytes a row |
| QQQ, IWM 1-minute | 2015-01-02 | 2026-11-14 | about 2.33 and 2.03 million |
| SPY, QQQ, IWM daily | 2016-05-02 | 2026-11-13 | 2,651 each |
| SPY 1-minute, October 2026 | | | 21,130 |

So SPY's 1-minute history is 143 months (2015-01 to 2026-11). Its daily history starts 2016-05-02, which matches the 10-year write cap of `_run_backfill` (`BACKFILL_LOOKBACK_DAYS`, `fetch_market_data.py:849`). A ticker outside SPY, QQQ and IWM lands in the DEFAULT partition `market_data_intraday_other` (`gcp/schema.sql:164-165`); NVDA's rows there start 2024-01-02 (`db-query-tcjwr`), the start date of the old bulk backfill.

### 4. What fills an added ticker going forward, and what does not

Read. Once a ticker is an active default row:

- **Fetched each night from the list:** `fetch-market-data` (the day's daily and 1-minute bars; after #1977 its universe is the list), `fetch-alphavantage-intraday` via `av-intraday-nightly` (the previous and current month; `resolve_all_symbols`, `:57-64`), `fetch-premarket-refresh` (premarket fields; capped at 50 tickers, `fetch_premarket_refresh.py:53`, `:129-131`), and the news, SEC, insider, RSS and historical options fetchers (`load_watchlist()` callers, `tests/gcp/test_watchlist_readers_default_owner.py` READERS). After #1977 the Sunday earnings chain's `_run_backfill` also targets the list and pulls a full daily series for a ticker with under 1,500 bars (`_pick_backfill_outputsize`, `:946-977`).
- **Built from stored bars, from the list:** `historical-signals-watchlist` (01:00 ET Tue to Sat) bootstraps 30 days of signals for a ticker with none (`BOOTSTRAP_DAYS`, `scripts/run_historical_signals.py:168`) and refuses to run over more than 25 tickers (`DEFAULT_MAX_TICKERS = 25`, `:91`; exit 1 at `:542-547`; the job passes no `--override-max`, `gcp/deploy.sh:664-690`). `calibrate_level_params` reads the list (`gcp/calibrate_level_params.py:96`, `:280`; its schedule not checked).
- **By flag:** the premarket brief (`in_brief`, `gcp/premarket_brief.py:937`), the insight pipeline (`in_insight`, `gcp/insight_pipeline_job.py:780`), the live signal monitor (`signals`, `gcp/signal_monitor.py:307`), which requests `TIME_SERIES_INTRADAY` once a poll per ticker (`:339-346`) with a 60 s poll (`lib/config.py:208`).
- **Fixed to SPY, QQQ and IWM in code, so never built for an added ticker:** strat features (`gcp/research/strat_engine/strat_data_builder.py:85`), gamma levels (`gcp/research/p2_build_gamma_levels.py:77`), the outcomes grid (`p2_outcomes_grid.py:63`), multi-timeframe features (`p7_build_multi_tf_features.py:62`), intraday flow and GEX (`gcp/build_intraday_flow.py:51`, `gcp/build_intraday_gex.py:49`), realtime GEX (`gcp/build_realtime_gex.py:51`) and options daily Greeks (`gcp/build_options_daily_greeks.py:49`).
- **Needs a history run:** the stored daily and 1-minute history itself. The nightly windows are 100 sessions (daily `compact`) and two months (1-minute); historical signals then have only those two months to bootstrap from.

### 5. The API cannot start those jobs today

Run (`gcloud run services describe`, `gcloud projects get-iam-policy`, `gcloud run jobs get-iam-policy`):

- `solyra-api-staging` runs as `trading-platform-svc@`, whose project roles are `roles/aiplatform.user`, `roles/cloudsql.client` and `roles/firebaseauth.admin`.
- On jobs, it holds `roles/run.invoker` on `fetch-market-data` only (granted by `platform/deploy.sh:28-67`, `SETUP_IAM=1`). `backfill-ticker`, `intraday-bulk-backfill` and `fetch-alphavantage-intraday` have empty policies.
- `roles/run.invoker` holds `run.jobs.run` but not `run.jobs.runWithOverrides`, which a per-ticker run needs; `roles/run.jobsExecutorWithOverrides` holds `run.jobs.run`, `run.jobs.runWithOverrides` and `run.executions.cancel`; `run.executions.get` and `run.executions.list` are in `roles/run.viewer` (run: `gcloud iam roles describe`).
- Discord's service `discord-interactions` runs as `trading-runner@`, which holds `roles/run.developer` at project level (read), so Discord can already start both jobs with overrides.

### 6. Validating a symbol

Run, through the vendor's tool, 2026-11-16, three calls: `GLOBAL_QUOTE` for `ZZQXJ` answers `{"Global Quote":{}}`; for NVDA it answers the quote (price 162.85, latest trading day 2026-11-13); `TIME_SERIES_DAILY` for `ZZQXJ` answers "Invalid API call". The existing helpers lose that difference: `get_quote` returns None for an empty quote, a throttle note and a transport error alike (`lib/ticker_info.py:449-499`), `fetch_ticker_overview` does the same (`:266-297`; `OVERVIEW` also covers no ETF, not re-checked here), and `search_tickers` returns `[]` on any failure (`:403-446`). Reusing any of them as is would turn a vendor outage into "not a symbol" (CLAUDE.md 3.7).

## Non-goals

- No schema change: no actor column, no history-runs table, no partition per ticker.
- No change to `gcp/deploy.sh`, `platform/deploy.sh` (FEAT-DEPLOY-001) or the solyra panel (spec G).
- No delete of any stored bar on removal (Decision 16 of #1977), and no refetch of a removed ticker's stored months on re-add beyond the gap rule of Design 4.
- No change to the per-user list (`/api/me/watchlist`), the two web write routes beyond the 410 wording of Design 8, or the builders fixed to SPY, QQQ and IWM.

## Approaches considered

1. **Admin routes over one shared writer in `_watchlist.py`, history started through the two existing jobs with per-run overrides, status read from the jobs' executions and the stored bars (chosen).** No new job, no schema change, one writer for the list, and the status survives a page reload because nothing is held in the API process.
2. **Reuse `_run_refresh_job` and `_DATA_SOURCES` (`admin.py:1489-1521`, `:1261-1279`).** It starts a job without overrides and returns None when it cannot read the execution id, so it cannot start a per-ticker run or report one. Not taken; ADMIN-06 is left as it is.
3. **Let the nightly runs fill the history.** Two months of 1-minute bars and 100 daily sessions; the owner asked for history at once.
4. **A history-runs table recording each start.** A schema change for what the executions already record (Problem 2). Offered as Decision 10's alternative.

## Design

### 1. One writer for the default list (`gcp/fetchers/_watchlist.py`)

- `add_default_ticker(ticker, *, source, in_brief=None, in_insight=None, signals=None, check=check_symbol) -> WatchlistWrite`, `remove_default_ticker(ticker, *, source) -> WatchlistWrite` and `set_default_flags(ticker, *, source, in_brief=None, in_insight=None, signals=None) -> WatchlistWrite`. `WatchlistWrite` holds `action` and the row as written (ticker, the three flags, source, added_at, removed_at).
- Order inside `add_default_ticker`: upper-case and match `^[A-Z0-9.]{1,10}$` (the `watched_tickers` check, `gcp/schema.sql:2647`) or raise `InvalidTicker`; then `check(ticker)`: `not_listed` raises `SymbolNotListed`, `unavailable` raises `SymbolCheckUnavailable`; then one transaction through `gcp.database.get_engine().begin()`: `SELECT pg_advisory_xact_lock(hashtext('watchlists:default'))`, the active count, and the INSERT. More than 25 active rows after the add raises `WatchlistFull` naming `historical-signals-watchlist` (Decision 4). On conflict the row is reactivated only when removed (`WHERE watchlists.removed_at IS NOT NULL`, as `_watchlist.py:538-547` does), with the given flags and source; an active row is left untouched and the action is `already_active`. A flag left None takes the column default on insert and the stored value on reactivation.
- `remove_default_ticker`: the same lock, refuses the last active row with `LastActiveTicker` (an empty list makes every price job exit, #1977 Design 1), then `UPDATE watchlists SET removed_at = NOW(), source = :source WHERE user_id = 'default' AND ticker = :t AND removed_at IS NULL RETURNING ...`.
- `set_default_flags`: the same lock, updates only the given flags and `source` on an active row; the trigger records a `flags` event when a flag changed.
- `source` is the writer on every write: `admin`, `discord-slash`, `discord-replay`. The trigger copies it into `watchlist_history`, so a remove and a flag change name who made them (Decision 5). The admin's email goes to the API log line, as `admin refresh` logs its caller today (`admin.py:1578-1579`).
- A database error raises. No function returns an empty or default row.
- The old `add_to_watchlist` and `remove_from_watchlist` stay for the two web write routes until stage B removes those callers.

### 2. The symbol check (`lib/ticker_info.py`)

- `check_symbol(ticker) -> SymbolCheck` with `status` `listed`, `not_listed` or `unavailable`, plus the price, the latest trading day and a reason. One `GLOBAL_QUOTE` request for the vendor's spelling (a dot becomes a dash, as `av_listed_symbol` does, `fetch_market_data.py:76-82`), one attempt, 10 s timeout. A filled `Global Quote` is `listed`; an empty one is `not_listed`; a `Note`, an `Information`, a missing key, an HTTP error or a timeout is `unavailable` with the reason.
- `get_quote`, `search_tickers` and `fetch_ticker_overview` are not changed.

### 3. History start (`gcp/fetchers/_watchlist.py`)

- `plan_history(ticker, minute_bounds) -> HistoryPlan`: `minute_bounds` is one read, `SELECT min(ts), max(ts) FROM market_data_intraday WHERE ticker = :t AND interval = '1min'`, two index descents (9.9 ms for NVDA on the 72.7 GB DEFAULT partition, EXPLAIN ANALYZE, `db-query-tcjwr`). No stored bar, or a first bar after `HISTORY_FIRST_MONTH`: plan from `HISTORY_FIRST_MONTH`. Otherwise plan from the month of the last stored bar (a re-add fills the gap, Decision 16 of #1977). Daily always from `HISTORY_DAILY_FROM`: it is one request either way.
- `HISTORY_FIRST_MONTH = '2015-01'` and `HISTORY_DAILY_FROM = '2016-05-02'`, SPY's measured depth (Problem 3; Decision 1). They are depths, not a ticker list.
- `start_history_fetch(ticker, plan) -> list[HistoryStart]`: two `run_v2.JobsClient().run_job(request=RunJobRequest(name=..., overrides=...))` calls, the shape `gcp/discord_interactions/main.py:229-274` uses:
  - `backfill-ticker`, env `BACKFILL_TICKER=<T>`, `BACKFILL_HISTORY_FROM=<plan daily from>`, `BACKFILL_INCLUDE_NEWS=false`, `BACKFILL_ADD_TO_WATCHLIST=false` (the row already exists; the news fetchers read the list nightly).
  - `intraday-bulk-backfill`, args `--symbol=<T>`, `--start-date=<first day of the planned month>`, `--force`, and `task_count=1` (Decision 2).
  - Each start returns `{job, execution, started: true}` with the execution name from the operation's metadata, or `{job, started: false, reason}`. A missing execution name is a failure with that reason, never a null id.
- `cancel_history_fetch(ticker)`: cancels each running execution of the two jobs whose overrides name the ticker (Decision 3) and returns the cancelled names; a cancel error is returned per execution.
- `history_status(ticker) -> HistoryStatus`: for each job, the newest execution among the last 20 (`list_executions`) whose env `BACKFILL_TICKER` or arg `--symbol=` names the ticker, with its state (`running`, `succeeded`, `failed`, `cancelled`) or `not_started`; the daily first and last date (`SELECT min(date), max(date) FROM market_data_daily WHERE ticker = :t`, the `(ticker, date)` index) and the 1-minute first and last bar (the read above). No count: a count over one ticker's daily rows took 1,420 ms cold (`db-query-tcjwr`). Combined `state`: `fetching` while either runs; `failed` when either failed or was cancelled; `done_without_minute_bars` when both succeeded and no 1-minute bar is stored (the vendor lists no minute bars for the symbol, as for BF-B, `fetch_market_data.py:80-81`); `done` otherwise. A listing error raises.
- `builders_not_covering`: the eight builder files whose ticker constant is fixed in code (Problem 4), returned with every status so the panel can say which views the ticker will not get.

### 4. Routes (`platform/api/routers/admin.py`)

Every route calls `_require_admin` first (`:52-66`; 401 without sign-in, 403 without the admin role). All are plain `def` (blocking I/O, stocks CLAUDE.md 3.10).

| Route | Body | Answers |
|---|---|---|
| `POST /api/admin/watchlist/default` | `{ticker, in_brief, in_insight, signals}` (booleans required) | 201 `AdminWatchlistAddResponse`: `row`, `symbol_check`, `plan`, `history: [HistoryStart]`; 409 active, 409 full; 422 shape, 422 not listed; 503 symbol check or database unavailable |
| `PATCH /api/admin/watchlist/default/{ticker}` | `{in_brief?, in_insight?, signals?}` | 200 `AdminWatchlistRowResponse`; 404 not active; 503 database |
| `DELETE /api/admin/watchlist/default/{ticker}` | | 200 `AdminWatchlistRemoveResponse`: `row`, `cancelled: [str]`, `cancel_failures: [ {execution, reason} ]`; 404 not active; 409 last active ticker; 503 database |
| `GET /api/admin/watchlist/default/{ticker}/history` | | 200 `AdminWatchlistHistoryResponse`: `ticker`, `on_watchlist`, `plan`, `jobs: [HistoryJobState]`, `daily: {first_date, last_date}`, `minute: {first_ts, last_ts}`, `state`, `builders_not_covering`, `as_of`; 503 executions or database unavailable |
| `POST /api/admin/watchlist/default/{ticker}/history` | | 202 `AdminWatchlistHistoryStartResponse` (a retry, the same plan rule); 404 not active; 429 inside the lease; 503 |

- Add order: symbol check, write, lease, start. The jobs check the list before their first vendor request (#1977 Designs 6 and 7), so the row is written first. A start that fails after the write is a 201 whose `history` entry carries `started: false` and the reason: the ticker is on the list and the nightly runs fetch it, and the panel offers a retry. It is not a 503, which would read as an add that did not happen.
- The lease is `admin_refresh_leases` (`gcp/schema.sql:5418-5421`, `admin.py:1437-1486`) keyed `watchlist-history:<T>`, 60 s, taken before a start and given back after a failed start, so a double press starts one fetch.
- The list itself is read from the existing `GET /api/insights/watchlist/default`; no second list route.
- Every response model is declared, so the OpenAPI document carries their schemas and solyra's contract test validates against them. `platform/api/openapi.json` is regenerated by `scripts/export_openapi.py`.
- Logging: one line per write, `admin watchlist: <action> <ticker> flags=<...> by <email>`, and one per start or cancel with the execution names.

### 5. Discord on the same writer (`gcp/discord_interactions/main.py`)

- `/watchlist add` calls `add_default_ticker(source='discord-slash')`, and on `already_active` with flags given, `set_default_flags`, which keeps today's "flags updated if passed" behaviour (`:647-650`, `:675`). It then calls `start_history_fetch`, as the API does (Decision 6). `/watchlist remove` calls `remove_default_ticker` and `cancel_history_fetch`.
- Both become deferred replies (`DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE`, `:68`, edited through `edit_deferred_reply`, `:208`), the pattern of `/replay-signals` (`:930-944`): a vendor check and two job starts do not fit the 3 s acknowledgement window the synchronous handler relies on (`:597-599`). `/watchlist list` stays synchronous.
- The reply texts for added, already present, removed and not in the list are kept; an unlisted symbol and an unavailable check get their own texts; the add's edit names the two executions.

### 6. `backfill-ticker` (`gcp/backfill_ticker.py`)

- `BACKFILL_HISTORY_FROM=YYYY-MM-DD` keeps the daily rows dated on or after it; `BACKFILL_HISTORY_DAYS` applies when it is unset, as today.
- Before 16:15 ET the current session's row is dropped before the write, with the rule `fetch_market_data._exclude_partial_today` already applies to the backfill path (`fetch_market_data.py:1029-1045`), so an add during the session never stores a partial bar as final.
- `BACKFILL_ADD_TO_WATCHLIST=true` writes through `add_default_ticker(source='discord-replay')`; the local `add_to_watchlist` (`:278-307`) goes.
- The as-traded request (`TIME_SERIES_DAILY`) and the watchlist refusal are #1978's and #1977's changes to the same file; this spec's PR opens after both are on main (Order).

### 7. The readers and writers inventory

`tests/gcp/test_watchlist_readers_default_owner.py` lists `gcp/discord_interactions/main.py` and `gcp/backfill_ticker.py` among WRITERS (read). After this change only `gcp/fetchers/_watchlist.py` and `gcp/schema.sql` hold an `INSERT INTO` or `UPDATE watchlists`; the inventory is updated to say so, and `/watchlist list`'s own read keeps its `own-sql` entry.

### 8. The stage B wording

The approved stage B spec makes the two web write routes answer 410 with a detail naming Discord as the only writer (`2026-11-14-feat-insight-001-watchlist-write-routes-410-r2.md`, Design; open PR #1937). After this change that text is no longer true. If #1937 is on main when this PR opens, this PR changes the detail to `The default watchlist is edited on the Admin page (Default watchlist tab) or in Discord (/watchlist add, /watchlist remove); the web app keeps per-user lists at /api/me/watchlist.` and its test asserts it. If it is not, the owner decides whether #1937 is re-cut with the same wording (Decision 8).

### 9. Site traceability

`site_source_notes` names one Chain row per page this change serves, read from `docs/product/03-SITE-TRACEABILITY.md` at a34bbd40: ADMIN-01 (`:1118`), the first ADMIN Chain row whose backend cell names `platform/api/routers/admin.py`, since the new tab has no element yet; and INSIGHTS-09 (`:758`), the element for adding or removing watchlist tickers, whose backend cell names `gcp/fetchers/_watchlist.py` and `lib/ticker_info.py`. Each note says what the source now does and claims no deployed change. The element for the new tab is added to solyra's `docs/UI-SCREENS.md` by spec G and to the SITE document on a docs branch after G merges.

## Capacity

| Step | Volume | Velocity | Wall-clock | Bound |
|---|---|---|---|---|
| `POST` add | one row | 1 vendor call, 3 SQL statements in one transaction, 1 index read, 1 lease upsert, 2 job starts | vendor at most 10 s (the timeout); the reads about 10 ms (`db-query-tcjwr`); a job start not measured. Estimate 2 to 5 s | the 10 s vendor timeout; Cloud Run's request timeout (not re-read) |
| `GET` history, polled by the panel every 15 s while fetching | | 2 execution listings of 20, 2 index reads | the 1-minute read 9.9 ms; the daily min and max and the listings not measured | |
| daily history (`backfill-ticker`) | about 2,650 sessions since 2016-05-02, at about 720 bytes a row (`market_data_daily`, 4,173,815,808 bytes over 5,807,535 rows in #1977) about 1.9 MB | 1 vendor call, 1 upsert, the indicator pass over the range | 22 to 35 s for 800 sessions with news (May runs); about 1 minute estimated for 2,650 | 600 s task timeout, about 10 times the estimate |
| 1-minute history (`intraday-bulk-backfill`, one task) at SPY's depth | 143 months; up to about 2.2 million rows for a ticker as liquid as SPY (about 21,000 a month now, about 10,000 in 2015), about 0.8 GB at 364 bytes a row | 143 vendor calls, one upsert each, paced at 0.4 s locally (`lib/config.py:121-143`) | measured per month: vendor 0.8 to 19.5 s and upsert 3.1 to 8.2 s (nightly `fetch-alphavantage-intraday-xxmp5`, 2026-11-15); the replace-months runs of 2026-11-14 20:05 to 21:02 UTC (one is `fetch-alphavantage-intraday-slsb2`), which also delete and rewrite derived rows, took a median 28.8 to 29.5 s a month. So about 24 minutes at 10 s a month, at most about 69 minutes at 29 s | 86,400 s task timeout, 20 times the high estimate. `fetch-alphavantage-intraday`'s 3,600 s would be under 4 times even the 24-minute estimate (Decision 2) |
| the same at the bounded depth of Decision 1 | 24 months, about 0.4 million rows, about 0.15 GB | 24 calls | about 4 to 12 minutes | as above |
| each night after, per added ticker | | `fetch-market-data` 2 calls, `av-intraday-nightly` 2, `fetch-premarket-refresh` 1; with `signals` on, the monitor about 390 a session (60 s poll over 6.5 hours, estimate) | | the list cap of 25 (Decision 4) |

- Vendor: 145 calls for one added ticker at SPY's depth (1 quote, 1 daily, 143 months), 26 at the bounded depth, against the purchased 600 RPM and a local allocation of 150 RPM a process (`lib/config.py:113-124`). A history run beside the nightly runs adds a second process at 150 RPM: 300 RPM, under the 600 purchased. Whether calls are billed one by one was not checked (as in #1977).
- Cloud Run: 1 vCPU and 1 GiB for both jobs (read). At $0.000018 a vCPU-second and $0.000002 a GiB-second (list prices, not re-read): one add at SPY's depth about $0.03 (24 minutes) to $0.08 (69 minutes); the daily job about $0.002. At a pace of 5 adds a month, under $0.50 a month.
- Cloud SQL storage: about 0.8 GB a liquid ticker at SPY's depth, 20 GB for 25 such tickers; at about $0.17 a GB-month for SSD (list price, not re-read) about $0.14 a month a ticker. The disk auto-resizes and does not shrink (#1977, Capacity).
- API: one admin; a handful of requests an add, about 4 a minute per fetching ticker while the panel is open.

## Decisions for the owner

Each is written into the text as recommended. Striking one changes only the sections named.

1. **Depth of an added ticker's history: the same as SPY** (1-minute from 2015-01, daily from 2016-05-02; Design 3). 145 vendor calls and up to about 0.8 GB for a liquid ticker, about 24 to 69 minutes. Alternative: a bounded depth of 24 months of 1-minute bars and 10 years of daily bars, 26 calls and about 0.15 GB, at the cost of charts and signals that reach back two years for that ticker.
2. **The 1-minute history runs on `intraday-bulk-backfill` with one task** (86,400 s, 0 retries). `fetch-alphavantage-intraday` has a 3,600 s timeout, under 4 times the estimate (stocks CLAUDE.md 0.5), and 1 retry, which would repeat up to 143 calls after a failure. This keeps `intraday-bulk-backfill`, which #1977's spec C would otherwise retire. Alternative: `fetch-alphavantage-intraday` with a per-run timeout override.
3. **Removal deletes nothing and cancels the ticker's running history executions**, so no vendor call continues for a ticker the admin removed; rows already stored stay. Alternative: let a running history finish. (#1977 Decision 16's own alternative, removal also deleting stored data, stays open there.)
4. **The list holds at most 25 active tickers**: the 26th add is refused with 409, because `historical-signals-watchlist` refuses more than 25 and would fail every night (Problem 4). Alternative: a FEAT-DEPLOY-001 change passing `--max-tickers` with a higher value, sized for that job's 1,800 s timeout.
5. **Every write sets `source` to its writer** (`admin`, `discord-slash`, `discord-replay`), so `watchlist_history` names who added, removed or reflagged a ticker; the admin's email is in the API log only. Alternative: an actor column on `watchlist_history`, a schema change of its own.
6. **Discord `/watchlist add` takes the same path**: symbol check, write, history start, as a deferred reply. Alternative: Discord keeps writing only, and a ticker added there waits for the nightly windows and the Sunday daily backfill.
7. **The symbol check is one `GLOBAL_QUOTE` request**: an empty quote means not listed, measured. Alternative: `SYMBOL_SEARCH` with an exact match, a fuzzy search whose empty answer was not measured.
8. **The stage B 410 detail names the Admin page beside Discord** (Design 8). Alternative: keep "Discord only" and accept a detail that is no longer true.
9. **SPY, QQQ and IWM can be removed like any other ticker, after the panel's confirmation**, because the owner's list decides; only the last active row is refused. Alternative: refuse removing any ticker that the eight fixed builders read, taken from their constants rather than a new list.
10. **History status is read from the jobs' executions and the stored bars**, with no new table (Design 3). Alternative: a history-runs table recording each start, a schema change.

## Order against work in progress

- This spec's implementation PR opens after the implementation PRs of #1977 (fetch universe and refusals) and #1978 (as-traded daily) are on main: both edit `gcp/backfill_ticker.py`, and #1977's refusal is what keeps the jobs to listed tickers.
- It depends on #1977 Decision 14 (keep the DEFAULT intraday partition): an added ticker's 1-minute bars land there. If spec B drops that partition, an add needs a partition per ticker, a schema change.
- Spec G (solyra) merges only after this spec's PR is merged and deployed, and syncs its contract from stocks main.

## Split and separate specs

This spec's implementation is one PR of 11 tasks:

1. `check_symbol`.
2. The shared writer: `add_default_ticker`, `remove_default_ticker`, `set_default_flags`, their errors and lock.
3. `plan_history`, `start_history_fetch`, `cancel_history_fetch`, `history_status`, `builders_not_covering`.
4. The five routes and their response models.
5. Discord on the shared writer, deferred replies.
6. `backfill_ticker`: `BACKFILL_HISTORY_FROM`, the partial-day rule, the shared writer.
7. The readers and writers inventory.
8. The stage B wording, when #1937 is on main.
9. OpenAPI regeneration and the route coverage entries.
10. Site notes, snapshot, inventories, catalog, traceability, docs audit, gate.
11. PR body: capacity numbers and the five operations for solyra.

Changes this spec does not make:

- **FEAT-DEPLOY-001:** add `backfill-ticker` and `intraday-bulk-backfill` to `SETUP_IAM` in `platform/deploy.sh` with `roles/run.jobsExecutorWithOverrides` and `roles/run.viewer`, with its test in `tests/gcp/test_platform_deploy_service_config.py`, so the grants of Close-out step 2 are reproducible; and in #1977's spec C, keep `intraday-bulk-backfill` (Decision 2) and point its default args at nothing but the list.
- **G (FEAT-ADMIN-001, solyra):** the panel.

## Close-out

None runs from the implementation PR, and none is a `done_when` box. Each step waits for the owner's yes, names its check, and is recorded on the PR.

1. **Deploy.** The API from main by its trigger; `./gcp/deploy.sh discord` (the Discord service and `backfill-ticker`) and `./gcp/deploy.sh intraday-bulk-backfill`, after #1977's and #1978's own deploys. Check: each image is the build's digest (`gcloud run jobs describe`, `gcloud run services describe`).
2. **IAM, an owner step** (`claude-web@` holds no `setIamPolicy`, stocks CLAUDE.md). For each of `backfill-ticker` and `intraday-bulk-backfill`: `gcloud run jobs add-iam-policy-binding <job> --region=us-east1 --project=adept-mountain-474619-d4 --member=serviceAccount:trading-platform-svc@adept-mountain-474619-d4.iam.gserviceaccount.com --role=roles/run.jobsExecutorWithOverrides`, then the same with `--role=roles/run.viewer`. Check: `gcloud run jobs get-iam-policy <job>` lists both roles for that member.
3. **One add on the live system, the owner's ticker.** Through Discord `/watchlist add <T>` (Discord's identity can already run both jobs) and, once G is deployed, through the panel (the API's identity). Check, read-only: `gcloud run jobs executions list --job=backfill-ticker` and `--job=intraday-bulk-backfill` show an execution naming `<T>` that succeeds; `SELECT min(ts), max(ts) FROM market_data_intraday WHERE ticker = '<T>' AND interval = '1min'` and `SELECT min(date), max(date) FROM market_data_daily WHERE ticker = '<T>'` reach the planned depth; `SELECT action, source FROM watchlist_history WHERE ticker = '<T>' ORDER BY id DESC LIMIT 3` shows `add` with the writer's source. The ticker is then fetched every night; removing it afterwards deletes nothing.
4. **SITE element.** After G merges, a docs branch adds the new tab's element to `docs/product/03-SITE-TRACEABILITY.md`.

## Risks

- **A vendor refusal mid-run leaves a month missing.** The intraday job logs a refused month and goes on (`process_symbol`); the status shows the first and last bar, not holes, and the gap rule fills only after the last stored month. Measuring holes needs per-month counts, not designed here.
- **A dead ticker reads as success to Cloud Run.** The intraday job exits 0 when every month is refused (Problem 2). The status turns that into `done_without_minute_bars` from the stored bars, not from the exit code.
- **The 25-ticker cap may surprise.** The 409 names the job that sets it.
- **IAM not granted.** Every API start fails with the run API's refusal; the add still writes the row and the 201 says the history did not start. Step 2 comes before G's deploy.
- **The added ticker stays out of strat features, gamma levels and flow.** The status names those builders on every response, so the panel says so.
- **A removal of SPY, QQQ or IWM** stops their fetch while the fixed builders keep reading their stored bars, which then go stale until re-added. Decision 9 and the panel's confirmation cover it.
- **Run API latency on each add and poll** was not measured.

## What was not verified

- Whether a job-level `roles/run.viewer` grant lets the API list and read that job's executions, and whether running with overrides needs `iam.serviceAccounts.actAs` on `trading-runner@`: not checked. Close-out step 3 through the panel shows it.
- Whether `op.metadata.name` carries the execution name on the client version the API ships: the existing code says it does and falls back to None (`admin.py:1514-1521`); no log of a past admin refresh was found in 60 days (run: log read).
- The vendor's raw HTTP body for an invalid `TIME_SERIES_DAILY` symbol: only the tool's wrapped answer was seen.
- The latency of a job start, an execution listing and the daily min and max read.
- `backfill-ticker`'s wall-clock over 2,650 sessions; the 1-minute history's wall-clock for a ticker outside SPY, QQQ and IWM.
- `calibrate_level_params`'s schedule, and how each news and filings fetcher sizes its per-ticker calls.
