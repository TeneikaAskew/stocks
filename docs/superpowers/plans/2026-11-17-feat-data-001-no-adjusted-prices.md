---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-11-16-feat-data-001-no-adjusted-prices-r2.md
branch: feature/feat-data-001-no-adjusted-prices
pr: null
status: ready
---

# Nothing fetches, stores or reads an adjusted price: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the order of the spec's frontmatter, [0] to [14].

**Goal:** Every daily price request asks for `TIME_SERIES_DAILY`, no code writes, reads or relabels an adjusted close, the earnings reaction gate admits as-traded windows only after an explicit AlphaVantage `SPLITS` check, and one test keeps it so.

**Architecture:** Six daily writers switch endpoint and volume key (`'5. volume'`) and drop `adjusted_close`. Two unused adjusted sources are deleted. `lib/data_loader.py` holds the four adjusted column names once (`ADJUSTED_CLOSE_COLUMNS`) and refuses or drops them. `compute_earnings_reactions` fetches each ticker's splits once per run, holds them in memory, refuses an event whose loaded window straddles a split, and passes the evidence to `lib.earnings_reactions.database_daily_price_evidence`, whose receipt becomes `av-as-traded-no-split-v1`. `tests/gcp/test_no_adjusted_prices.py` holds the request tests and an `ast` guard over `gcp/`, `lib/`, `scripts/` and `platform/`.

**Tech Stack:** Python 3, pandas, requests, `ast`, pytest (`monkeypatch`, `caplog`, `unittest.mock.patch`).

**Spec:** `docs/superpowers/specs/2026-11-16-feat-data-001-no-adjusted-prices-r2.md` (approved, PR #1990; supersedes the #1978 draft). Read it beside this plan: Problem 1 is the site list, Design 1 the writer table, Design 7 the guard's exact rules.

## Global Constraints

- Line anchors are `origin/main` 90c41e6d (2026-11-17). Between the spec's 4155a10f and 90c41e6d the only changed files under `gcp/ lib/ scripts/ platform/ tests/` are `gcp/deploy.sh`, `scripts/gate/spec_gate.py`, `scripts/maintenance/doc_source_snapshot.py`, `tests/gcp/test_deploy_reachability.py`, `tests/scripts/test_doc_inventory.py`, `tests/scripts/test_doc_source_snapshot.py` and `tests/scripts/test_spec_gate.py` (run: `git diff --stat 4155a10f origin/main -- gcp lib scripts platform tests`), so every spec citation outside `gcp/deploy.sh` holds. Re-run that diff on the fork commit and locate each edit by its quoted content.
- No production write, deploy or job run from this branch (spec Non-goals). No change to `gcp/deploy.sh`, `gcp/schema.sql` (it keeps `adjusted_close` at `:110-111`), `platform/api`, solyra, or which tickers any job fetches.
- Exact values from the spec: daily endpoint `TIME_SERIES_DAILY`; volume key `'5. volume'`; `ADJUSTED_CLOSE_COLUMNS = ('Adj Close', 'adj_close', 'adjusted_close', 'adjclose')`; raw close names `Close`, `close`, `Last`, `last`; `AS_TRADED_DAILY_SOURCES = ('alphavantage', 'alphavantage_daily', 'av_daily_backfill', 'av_watched_backfill')`; `price_basis_id='av-as-traded-no-split-v1'`; `source_id = 'current-db-projection:' + <projection digest over date, open, high, low, close, data_source> + ':splits:' + <splits digest>`; reasons `split_in_window`, `split_status_unavailable`, `unrecognized_database_price_writer`; SPLITS request `{'function': 'SPLITS', 'symbol': av_listed_symbol(ticker), 'apikey': api_key}`; pacing `AlphaVantageConfig().delay_between_calls` (0.4 s); log lines `ticker=%s splits=%d processed=%d/%d` per ticker and `splits_unavailable=<n>` per run.
- CLAUDE.md 3.7: a `SPLITS` failure is EXTERNAL and is named, never turned into "no split". Nothing new returns `{}`, `[]` or `None` on a failure. The existing swallow in `fetch_daily_from_av` (`gcp/fetchers/fetch_market_data.py:252-254`) gets the AUDIT marker, not a fix.
- The guard exempts docstrings and nothing else: an error or log message added by this plan may not contain `adjusted close`, `adj close`, `adjclose`, `adjusted daily`, `daily adjusted` or a `*_ADJUSTED` name.
- The render step, after any task that changes a file under `gcp/`, `lib/` or `scripts/` (the generated inventory cites line numbers):
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate -q` (expect 1 passed); stage whichever of the three docs changed with the code.
- Before every commit: `python3 scripts/gate/spec_gate.py --commit`. Commits are conventional, imperative, with no AI attribution. Every new test has a red then green record in the PR body.
- `docs_audit.py` and `doc_source_snapshot.py` run only from a non-shallow clone.

## done_when map

| done_when | What | Task |
|---|---|---|
| [0] | six daily writers send `TIME_SERIES_DAILY`, read `'5. volume'`, carry no adjusted column | 2, 3, 4, 5 |
| [1] | `process_ticker` and `fetch_and_upsert_vix` write no `adjusted_close` | 2 |
| [2] | the two retired files are gone; CONSUMERS updated | 6, 10 |
| [3] | the gate: as traded, split checked | 11 |
| [4] | populate refuses a split in the loaded window; native test updated | 11, 12 |
| [5] | every `SPLITS` request failing fails the run | 12 |
| [6] | `fetch_splits` request and reply | 10 |
| [7] | `normalize_columns` never takes an adjusted close as a close | 8 |
| [8] | the 1-minute `adjusted` keyword is gone | 7 |
| [9] | the strat history contract refuses `av-adjusted-daily-v1` | 9 |
| [10] | the guard and its seeded cases | 13 |
| [11] | the 22-line grep returns nothing | 2, 3, 4, 5, 9 (checked in 13) |
| [12] | the reader list in the PR body | 14 |
| [13] | `make test`, inventory re-render | 14 |
| [14] | catalog, traceability, twelve SITE notes, snapshot, docs audit, gate | 15 |

## Review Focus

- **A writer that swallows the old volume key.** `fetch_daily_from_av` returns `{}` on any exception (`:252-254`) and `migrate_market_data_daily_av` logs and continues (`gcp/migrate_to_gcp.py:595-596`), so a writer still reading `'6. volume'` "passes" a test that only checks what was absent. Every case of `test_daily_writers_request_as_traded` asserts a non-empty result and `volume == 81234567`. Tasks 2 to 5.
- **A split on the window's first bar.** A split effective on the first loaded session leaves every bar post-split and must be admitted; one effective on the session after the first must be refused. Both cases in `test_split_in_loaded_window_skips_the_event`. Task 12.
- **One ticker's `SPLITS` outage in a multi-ticker run.** The other tickers are written, the run exits 0, the failed ticker's events are named `split_status_unavailable`, and its stored rows are untouched (no upsert carries its key). Tasks 11 and 12.
- **A local frame holding only an adjusted column.** `normalize_columns` raises naming the column (spec Risks); a frame holding both keeps the raw close. Parametrized over all four names. Task 8.
- **An offline experiment run against the old export.** Both experiments raise on a file holding an adjusted column instead of silently using it. `test_experiments_read_the_as_traded_export`. Task 9.

## File map

| File | Change | Task |
|---|---|---|
| `gcp/fetchers/fetch_market_data.py` | `:8`, `fetch_daily_from_av` `:182-254`, `build_daily_row` docstring `:263`, log `:674-675`, VIX row `:731`, `_av_get_full_daily_series` `:980-1025`; 1-minute keyword `:85-97`, `:175-179` | 2, 7 |
| `gcp/backfill_ticker.py` | `:7`, `av_daily_full` `:102-131`, `run` `:558`, `:616-627` | 3 |
| `gcp/migrate_to_gcp.py` | `:508`, `migrate_market_data_daily_av` `:517-599` | 4 |
| `scripts/backfill_watchlist_data.py` | `:11-13`, `backfill_daily` `:179-252` | 5 |
| `scripts/fetch_market_data.py` | `fetch_historical_daily_data` `:294-364`, `:531`, `:575` | 5 |
| `scripts/deep_backfill_ticker.py`, `gcp/fetchers/fetch_av_indicators.py` | deleted | 6 |
| `gcp/research/magnitude_engine/README.md` | `:185-188` | 6 |
| `tests/fixtures/timezone_boundary_baseline.json` | the `gcp/fetchers/fetch_av_indicators.py` entry (`:61-65`) dropped | 6 |
| `gcp/fetchers/evaluate_ew_strikes.py` | `:396-397` | 7 |
| `lib/data_loader.py` | `COLUMN_MAP` `:43-54`, `normalize_columns` `:317-342`, `_load_daily_from_sql` `:557` | 8 |
| `lib/strat.py` | `_history_contract` `:1506` | 9 |
| `gcp/queries/nan_triage.sql` | `:31` | 9 |
| `scripts/analysis/brief_rsi_band_experiment.py`, `scripts/analysis/honest_scoring_experiment.py` | `:12-13`, `:56`, `:71-74`; `:95-97` | 9 |
| `gcp/fetchers/fetch_alphavantage_intraday.py` | comments `:1170`, `:1175-1176` | 9 |
| `lib/earnings_reactions.py` | `Splits`, `SplitsUnavailable`, `AS_TRADED_DAILY_SOURCES`, `database_daily_price_evidence` `:1310-1357` | 10, 11 |
| `gcp/fetchers/compute_earnings_reactions.py` | SELECTs `:619`, `:678`; `fetch_splits`; `populate_for_tickers` `:707-878`; `main` `:978-1024`, `:1289-1290` | 10, 11, 12 |
| `tests/gcp/test_no_adjusted_prices.py` | new | 2 to 6, 9, 13, 14 |
| existing tests (spec Split, task 12) | updated in the task whose change breaks them | 2 to 12 |
| `docs/product/infrastructure/05-a`, `05-c`, `05-e` | inventory blocks, by the render step | 2 to 12 |
| `docs/product/02`, `03`, `12`, `docs/review-evidence/site-source-snapshot.json` | close | 15 |

## Capacity (CLAUDE.md rule 0; spec Design 9)

Copy into the PR body's Capacity section:

- **Volume:** daily requests unchanged in count (one per ticker), each reply two fields a session smaller. `SPLITS`: one call per ticker with events in a weekly run; with #1977's two-week reporter set, about 180 tickers in a median run and at most about 1,500 (weekly reporters over 52 weeks: median 89, mean 152.2, max 755, `db-query-2k89c`). Each reply is a short list (NVDA: six events since 2000) held in memory for the run; nothing is stored.
- **Velocity:** one `SPLITS` call per ticker per run, paced at 0.4 s (`lib/config.py`, 150 RPM local allocation); no new SQL statement per event.
- **Wall-clock:** at an assumed 1.4 s a call (pacing plus 0.5 to 1 s latency, not measured): median about 4 minutes, peak about 35 minutes. The peak exceeds today's 1,800 s task timeout (`gcp/deploy.sh:3011`), so Close-out step 1 waits for #1977's spec C to set it to at least 16,800 s (4 x the 70-minute peak once #1977's on-demand daily request is added).
- **Cost:** Cloud Run time for the peak run's split calls, about 35 minutes of 1 vCPU and 1 GiB, about $0.04 a run, under $0.20 a month (list prices, not re-read). The AlphaVantage account is a flat 600 RPM allowance; per-call billing not checked.

---

### Task 1: Preconditions and the order of the three specs

Spec: § Order against work in progress; § Close-out; § Decisions 2 and 3. Advances no done_when item; guards [13] and [14].

**Files:** none on this branch.

- [ ] **Step 1: Base.** Cut `feature/feat-data-001-no-adjusted-prices` from `origin/main` after this plan is on `main`. Run `git diff --stat 4155a10f HEAD -- gcp lib scripts platform tests` and expect only the seven files named in Global Constraints (or later ones that touch no file this plan cites). Any cited file in the output: re-read its lines before the task that edits it.
- [ ] **Step 2: Code order (precondition, this plan's decision).** This branch merges first of the three. The SPY/QQQ/IWM-only implementation (`docs/superpowers/specs/2026-11-16-feat-data-001-spy-qqq-iwm-only-r2.md`, plan branch `docs/plan-feat-data-001-spy-qqq-iwm-only`) opens its branch only after this PR is on `main`; the admin editor (`docs/superpowers/specs/2026-11-16-feat-admin-001-default-watchlist-editor-r2.md`) after both. Check `git ls-remote origin 'refs/heads/feature/feat-data-001-spy-qqq-iwm-only'`: if that branch has merged into `main` already, stop and re-plan Tasks 10 to 12 against its `populate_for_tickers` (spec Design 5: the SELECT item is then done by the guard alone, and the split evidence goes into its on-demand frame).
- [ ] **Step 3: Data order, recorded in the PR body (no code).** This spec's Close-out step 1 (deploy every reader) waits for the SPY/QQQ/IWM-only implementation on `main` and its spec C (FEAT-DEPLOY-001: weekday earnings schedulers retired, `compute-earnings-reactions` timeout at least 16,800 s). That spec's Close-out steps 7 and 8 (clear, then drop `market_data_daily.adjusted_close`) wait for this spec's Close-out step 2. Its spec B removes `gcp/schema.sql:110-111` and the guard's two-line allowance together.
- [ ] **Step 4: Records PR R, before this PR is marked ready.** Deleting the two files of Task 6 turns their citations in `docs/product/` into `dead-link` findings and fails `tests/meta/test_model_registry_consistency.py::test_known_dead_path_backlog_only_shrinks[03-SITE-TRACEABILITY.md]`, and this branch may edit neither (product-delivery, Never). Open `docs/no-adjusted-retired-sources-records` (documentation only, no plan) changing exactly:
  - `docs/product/03-SITE-TRACEABILITY.md`, the Chain rows DASHBOARD-01 `:331`, DASHBOARD-03 `:333`, DASHBOARD-15 `:345`, LIVE-04 `:426`, LIVE-06 `:428`, LIVE-08 `:430`, CHARTS-03 `:508`, CHARTS-10 `:515`, INSIGHTS-01 `:750`, INSIGHTS-04 `:753`, INSIGHTS-07 `:756`, INSIGHTS-08 `:757`, PLAYBOOK-05 `:905`, JOURNAL-04 `:1044`: the clause "`scripts/deep_backfill_ticker.py` and `gcp/migrate_to_gcp.py`" becomes "`gcp/migrate_to_gcp.py` (the deep backfill script is retired by the FEAT-DATA-001 no-adjusted change)" with no backticked path to the retired file.
  - `docs/product/infrastructure/manual/05-c-DATA_DEPENDENCIES.md` `:335`, `:691` (the two link bullets, removed) and `:879` (the path left out of the writer cell, count lowered by one); `docs/product/infrastructure/manual/05-a-ARCHITECTURE.md` `:927` (the row removed).
  This branch stays a draft until R merges; its ready push merges `main` with R in it. Until then the two `tests/meta` cases above are red on this branch by design.
- [ ] **Step 5: Open the draft PR** after Task 2's commit, titled `FEAT-DATA-001: nothing fetches, stores or reads an adjusted price`, body: spec and plan paths, each done_when item as a `- [ ]` line starting with its text, the Capacity section above. Set `pr:` in this plan to its number in the next commit.

### Task 2: `fetch_market_data`: the nightly daily row, the backfill series, the VIX row

Spec: § Design 1 (rows 1 to 3, docstrings, log, AUDIT marker). Advances done_when[0] (two writers), [1], [11].

**Files:**
- Modify: `gcp/fetchers/fetch_market_data.py:8`, `:182-254`, `:263`, `:674-675`, `:731`, `:980-1025`
- Create: `tests/gcp/test_no_adjusted_prices.py`
- Modify tests: `tests/gcp/test_fetch_market_data_backfill_sleep.py:36`, `tests/gcp/test_fetch_market_data_backfill_targets.py:231`, `tests/gcp/test_fetch_market_data_intraday_optional.py:44`, `:83-93`, `tests/gcp/test_fetch_market_data_vix.py:65-66`, `tests/gcp/test_fetch_watched_tickers.py:26`, `:699`, `tests/gcp/test_evaluate_ew_strikes.py:565-571` (`_daily`)

**Interfaces:**
- Produces (test module): `DAILY_REPLY`, a `TIME_SERIES_DAILY` reply for SPY: `{"Meta Data": {"2. Symbol": "SPY"}, "Time Series (Daily)": {"2026-11-13": {"1. open": "671.11", "2. high": "675.38", "3. low": "668.12", "4. close": "673.27", "5. volume": "81234567"}, "2026-11-12": {"1. open": "670.00", "2. high": "672.50", "3. low": "667.90", "4. close": "671.80", "5. volume": "70111222"}}}` (no fields 5 adjusted, 6, 7 or 8, so a reader of `'6. volume'` raises `KeyError`); `_recording_get(answers: dict[str, dict]) -> tuple[Callable, list[dict]]` answering by `params['function']` and recording every `params`; `ADJ = {'adjusted_close', 'Adj Close'}`.
- Produces (code): `fetch_daily_from_av(...) -> dict` with keys exactly `open, high, low, close, volume`; `_av_get_full_daily_series(...)` columns exactly `ticker, date, open, high, low, close, volume`.

- [ ] **Step 1: Write the failing tests** in `tests/gcp/test_no_adjusted_prices.py`:
  - `test_daily_writers_request_as_traded`, parametrized by writer id; this task adds `fetch_daily_from_av` and `_av_get_full_daily_series`. For the first: `fetch_daily_from_av('SPY', '2026-11-13', 'k')` under the recording `requests.get`; assert exactly one request, `function == 'TIME_SERIES_DAILY'`, and the result `== {'open': 671.11, 'high': 675.38, 'low': 668.12, 'close': 673.27, 'volume': 81234567}`. For the second: `_av_get_full_daily_series('SPY', 'k', 'full')`; `function == 'TIME_SERIES_DAILY'`, `outputsize == 'full'`, `list(frame.columns) == ['ticker', 'date', 'open', 'high', 'low', 'close', 'volume']`, `frame.volume.tolist() == [70111222, 81234567]`.
  - `test_no_writer_emits_adjusted_close`: `process_ticker('SPY', '2026-11-13', 'k')` with `requests.get` answering `TIME_SERIES_INTRADAY` (one 1-minute bar at `2026-11-13 09:30:00`) and `TIME_SERIES_DAILY` (`DAILY_REPLY`), `upsert_dataframe`, `write_intraday_to_sql` and `compute_and_upsert_daily_indicators` patched on the module to record. Assert at least one recorded `market_data_daily` frame, every one with `not (set(frame.columns) & ADJ)`, and its row `data_source == 'alphavantage_daily'`, `volume == 81234567`. Then `fetch_and_upsert_vix()` over a stubbed Yahoo chart reply (two settled closes, `{"chart": {"result": [{"timestamp": [...], "indicators": {"quote": [{"open": [...], "high": [...], "low": [...], "close": [...]}]}}]}}`) returns 2 and its recorded frame has no column in `ADJ`.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_no_adjusted_prices.py -q`. Expected: FAIL (`function == 'TIME_SERIES_DAILY_ADJUSTED'`; `fetch_daily_from_av` returns `{}` because `'5. adjusted close'` is missing; the VIX frame carries `adjusted_close`).
- [ ] **Step 3: Implement.** `fetch_daily_from_av` and `_av_get_full_daily_series` send `TIME_SERIES_DAILY` and read `'5. volume'`; no `adjusted_close`. The log at `:674-675` drops `adj=` and its argument. `fetch_and_upsert_vix` loses the `adjusted_close` key. Docstrings `:8`, `:185`, `:263`, `:982-984` say the daily row is as traded from `TIME_SERIES_DAILY`. Above the `except Exception` at `:252`, add the AUDIT marker in the form `:480` uses (`# AUDIT-2026-05-13: silent fallback`, the same separator, then: a vendor reply or parse failure returns `{}` and `process_ticker` builds the row from 1-minute bars).
- [ ] **Step 4: Update the existing tests** listed under Files: drop `adjusted_close` from their stub rows and frames, change stub replies to `TIME_SERIES_DAILY` with `'5. volume'` (`test_fetch_market_data_intraday_optional.py:83-93`, `test_evaluate_ew_strikes.py:565-571`, `test_fetch_watched_tickers.py:699`), and in `test_fetch_market_data_vix.py` replace the `:65-66` assertion with `assert "adjusted_close" not in df.columns`.
- [ ] **Step 5: Run** `python3 -m pytest tests/gcp/test_no_adjusted_prices.py tests/gcp/test_fetch_market_data_backfill_sleep.py tests/gcp/test_fetch_market_data_backfill_targets.py tests/gcp/test_fetch_market_data_intraday_optional.py tests/gcp/test_fetch_market_data_vix.py tests/gcp/test_fetch_watched_tickers.py tests/gcp/test_evaluate_ew_strikes.py -q`. Expected: all pass. Then the render step.
- [ ] **Step 6: Commit:** `fix(data): request the nightly and backfill daily series as traded`. Push and open the draft PR (Task 1, Step 5).

### Task 3: `backfill-ticker`

Spec: § Design 1 (row `gcp/backfill_ticker.py`). Advances done_when[0], [11].

**Files:**
- Modify: `gcp/backfill_ticker.py:7`, `:102-131`, `:558`, `:616-627`
- Test: `tests/gcp/test_no_adjusted_prices.py`; modify `tests/gcp/test_backfill_ticker.py:231`, `:296-319`, `:672`

**Interfaces:**
- Consumes: `DAILY_REPLY`, `_recording_get` (Task 2).
- Produces: `av_daily_full(ticker, api_key) -> pd.DataFrame` with columns `date, open, high, low, close, volume`.

- [ ] **Step 1: Add the `backfill_ticker` case** to `test_daily_writers_request_as_traded`: env `BACKFILL_TICKER=SPY`, `ALPHA_VANTAGE_API_KEY=k`, `BACKFILL_INCLUDE_NEWS=false`, `BACKFILL_ADD_TO_WATCHLIST=false`, `BACKFILL_DATES=2026-11-13`; stubs as `tests/gcp/test_backfill_ticker.py::test_run_fetches_and_writes_no_one_minute_bars` sets them (`:284-330`: `requests.get`, `gcp.database.upsert_dataframe` recorder, the indicator and per-date steps). Assert `av_daily_full('SPY', 'k')` sends `TIME_SERIES_DAILY`, its columns hold nothing in `ADJ` and `volume` equals `[70111222, 81234567]`; `run()` returns 0 and its recorded `market_data_daily` frame has no column in `ADJ`, `data_source == 'alphavantage'`, the 2026-11-13 row's `volume == 81234567`.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_no_adjusted_prices.py -k backfill_ticker -q`. Expected: FAIL (`KeyError: '5. adjusted close'` raised out of `av_daily_full`).
- [ ] **Step 3: Implement:** `TIME_SERIES_DAILY`, `'5. volume'`, no `adjusted_close` parsed (`:126`) or written (`:621`); docstrings `:7`, `:103`, `:558` say as traded.
- [ ] **Step 4: Update** `tests/gcp/test_backfill_ticker.py`: `daily_bar` (`:300-303`) without field 5 adjusted and with `'5. volume'`; the answers key and both expected lists (`:306`, `:318-319`) name `TIME_SERIES_DAILY`; the frames at `:231` and `:672` lose `adjusted_close`.
- [ ] **Step 5: Run** `python3 -m pytest tests/gcp/test_no_adjusted_prices.py tests/gcp/test_backfill_ticker.py -q`. Expected: all pass. Render step.
- [ ] **Step 6: Commit:** `fix(data): backfill-ticker requests the as-traded daily series`

### Task 4: `migrate_to_gcp`'s daily path

Spec: § Design 1 (row `gcp/migrate_to_gcp.py`). Advances done_when[0], [11].

**Files:**
- Modify: `gcp/migrate_to_gcp.py:508`, `:517-599` (docstring `:519-525`, log `:533`, request `:543`, row `:575-576`)
- Test: `tests/gcp/test_no_adjusted_prices.py`

- [ ] **Step 1: Add the `migrate_to_gcp` case:** monkeypatch `gcp.migrate_to_gcp.AV_DAILY_SYMBOLS` to `{'spy': 'SPY'}`, env `ALPHA_VANTAGE_API_KEY=k`, `time.sleep` to a no-op, `gcp.database.upsert_dataframe` to record; call `migrate_market_data_daily_av(Path('.'), dry_run=False)`. Assert one request with `function == 'TIME_SERIES_DAILY'`, exactly one recorded frame (the function logs and continues on any exception, so a missing frame is the failure), no column in `ADJ`, `data_source == 'alphavantage_daily'`, the 2026-11-13 row's `volume == 81234567`.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_no_adjusted_prices.py -k migrate -q`. Expected: FAIL (no frame recorded: the `KeyError` was logged at `:595-596`).
- [ ] **Step 3: Implement:** `TIME_SERIES_DAILY`, `'5. volume'`, no `adjusted_close`; the comment `:508` names `TIME_SERIES_DAILY`; the docstring drops "existing rows are updated with adjusted_close"; the log `:533` names `TIME_SERIES_DAILY`.
- [ ] **Step 4: Run** the same command (expect PASS), then `python3 -m pytest tests/gcp -q -k migrate`. Render step.
- [ ] **Step 5: Commit:** `fix(data): migrate_to_gcp's daily backfill requests the as-traded series`

### Task 5: the two hand-run scripts

Spec: § Design 1 (rows `scripts/backfill_watchlist_data.py`, `scripts/fetch_market_data.py`). Advances done_when[0] (last two writers), [11].

**Files:**
- Modify: `scripts/backfill_watchlist_data.py:11-13`, `:200-238`; `scripts/fetch_market_data.py:296`, `:314`, `:336-344`, `:531`, `:575`
- Test: `tests/gcp/test_no_adjusted_prices.py`; modify `tests/scripts/test_backfill_watchlist_level_params.py:25-27`, `tests/scripts/test_failure_rate_threshold.py:45`

- [ ] **Step 1: Add two cases.** `backfill_watchlist_data`: env `AV_API_KEY=k`; `requests.get` recorded; `gcp.database.upsert_dataframe` recorded; `gcp.fetchers.fetch_market_data.compute_and_upsert_daily_indicators` and `read_level_params_for_run` patched (as `tests/scripts/test_backfill_watchlist_level_params.py:48-60` does). `backfill_daily('SPY')` returns True; the request is `TIME_SERIES_DAILY`; the recorded frame has no column in `ADJ`, the 2026-11-13 row's `volume == 81234567`. `scripts_fetch_market_data`: monkeypatch `scripts.fetch_market_data.AV_API_KEY` to `'k'`; `fetch_historical_daily_data('SPY', '2026-11-01', '2026-11-30')` sends `TIME_SERIES_DAILY` and returns columns exactly `['Open', 'High', 'Low', 'Close', 'Volume']` with `Volume` `[70111222, 81234567]`.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_no_adjusted_prices.py -k "watchlist or scripts_fetch" -q`. Expected: FAIL (`backfill_daily` raises `KeyError` on field 5 adjusted; the parquet frame is missing `Volume`).
- [ ] **Step 3: Implement.** Both requests `TIME_SERIES_DAILY`. `backfill_daily` reads `'5. volume'` and writes no `adjusted_close`; module docstring `:11-13` names `TIME_SERIES_DAILY`. The rename map keeps `'5. volume': 'Volume'` and has no `Adj Close`; `:531` and `:575` map only `normalized == 'close'` to `Close`.
- [ ] **Step 4: Update** `test_backfill_watchlist_level_params.py:25-27` (stub reply: field 5 is volume, no adjusted) and `test_failure_rate_threshold.py:45` (frame without `adjusted_close`).
- [ ] **Step 5: Run** `python3 -m pytest tests/gcp/test_no_adjusted_prices.py tests/scripts/test_backfill_watchlist_level_params.py tests/scripts/test_failure_rate_threshold.py -q`. Expected: all pass, and `test_daily_writers_request_as_traded` shows its six ids passing. Render step.
- [ ] **Step 6: Commit:** `fix(data): the hand-run daily scripts request the as-traded series`

### Task 6: retire `deep_backfill_ticker.py` and `fetch_av_indicators.py`

Spec: § Design 2, § Design 3, Decisions 2 and 3. Advances done_when[2] (files and CONSUMERS removal; the addition lands in Task 10).

**Files:**
- Delete: `scripts/deep_backfill_ticker.py`, `gcp/fetchers/fetch_av_indicators.py`
- Modify: `tests/lib/test_av_account_allowance.py:16` (entry removed), `tests/fixtures/timezone_boundary_baseline.json:61-65`, `gcp/research/magnitude_engine/README.md:185-188`
- Test: `tests/gcp/test_no_adjusted_prices.py`

- [ ] **Step 1: Write the failing test** `test_retired_adjusted_sources_are_gone`: `assert not (REPO / 'scripts/deep_backfill_ticker.py').exists()` and the same for `gcp/fetchers/fetch_av_indicators.py`.
- [ ] **Step 2: Run** it. Expected: FAIL.
- [ ] **Step 3: Delete both files.** Remove `'gcp/fetchers/fetch_av_indicators.py'` from `CONSUMERS`. Drop the baseline entry with `python3 -m tests.meta.test_timezone_boundaries --write-baseline`; `git diff tests/fixtures/timezone_boundary_baseline.json` must show only the five lines of that file's entry removed (the ratchet fails on a baselined site that no longer occurs). README `:185-188`: phase 2's indicators had their fetcher retired because AlphaVantage computes them on adjusted closes (BBANDS measured, spec Problem 5); a return of phase 2 computes them in `lib/indicators.py` from as-traded bars, a research decision.
- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_no_adjusted_prices.py::test_retired_adjusted_sources_are_gone tests/lib/test_av_account_allowance.py tests/meta/test_timezone_boundaries.py -q`. Expected: all pass. `python3 -m pytest tests/meta/test_model_registry_consistency.py -q -k dead` is red for `03-SITE-TRACEABILITY.md` until R (Task 1, Step 4) is merged into this branch; after that merge, green. Render step (05-c loses its two `deep_backfill_ticker.py` bullets and a writer, 05-a its `fetch_av_indicators.py` row).
- [ ] **Step 5: Commit:** `chore(data): retire the deep backfill script and the AlphaVantage indicator fetcher`

### Task 7: the 1-minute `adjusted` keyword goes

Spec: § Design 4. Advances done_when[8].

**Files:**
- Modify: `gcp/fetchers/fetch_market_data.py:85-97`, `:175-179`; `gcp/fetchers/evaluate_ew_strikes.py:396-397`
- Test: `tests/gcp/test_intraday_as_traded.py:59-75`; `tests/gcp/test_evaluate_ew_strikes.py:96-97`, `:257`

**Interfaces:**
- Produces: `fetch_minute_bars(ticker: str, fetch_date: str, api_key: str) -> tuple[pd.DataFrame, str]`; `fetch_minute_data(ticker: str, fetch_date: str, api_key: str) -> pd.DataFrame`.

- [ ] **Step 1: Change the tests.** `test_asking_for_adjusted_minute_bars_is_refused`: for each of the two functions, `pytest.raises(TypeError)` on `fn("SPY", "2025-11-14", "key", adjusted=True)` and `get.assert_not_called()`. `test_daily_fetcher_requests_as_traded_through_both_functions`: drop the `adjusted=False` call (`:66-67`). In `test_evaluate_ew_strikes.py`, the recorder at `:97` appends `"adjusted" in kw` as its third element and `:257` asserts `calls[0][2] is False` (the call carries no `adjusted` keyword).
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_intraday_as_traded.py tests/gcp/test_evaluate_ew_strikes.py -q`. Expected: FAIL (`ValueError` where `TypeError` is expected; `evaluate_ew_strikes` passes `adjusted`).
- [ ] **Step 3: Implement:** remove the parameter and the `if adjusted: raise` block from `fetch_minute_bars`, the parameter and pass-through from `fetch_minute_data`, and `adjusted=False` from `evaluate_ew_strikes.py:396-397`. The request dict keeps `'adjusted': 'false'`.
- [ ] **Step 4: Run** the same command. Expected: all pass. Render step.
- [ ] **Step 5: Commit:** `refactor(data): drop the 1-minute adjusted switch whose only legal value was False`

### Task 8: `lib/data_loader.py`

Spec: § Design 5 (`lib/data_loader.py`). Advances done_when[7].

**Files:**
- Modify: `lib/data_loader.py:43-54`, `:317-342`, `:557`
- Test: `tests/lib/test_data_loader.py` (class `TestNormalizeColumns`, `:58`)

**Interfaces:**
- Produces: `ADJUSTED_CLOSE_COLUMNS = ('Adj Close', 'adj_close', 'adjusted_close', 'adjclose')`, a module-level assignment; Task 9 imports it.

- [ ] **Step 1: Write the failing test** `TestNormalizeColumns::test_an_adjusted_close_is_never_a_close`, parametrized over the four names: a frame `{'Open': [100], 'High': [101], 'Low': [99], <name>: [99.5], 'Volume': [1000]}` makes `loader.normalize_columns` raise `ValueError` whose message contains `<name>` (`match=re.escape(name)`); a frame `{'open': [100], 'high': [101], 'low': [99], 'close': [101.0], <name>: [99.5], 'volume': [1000]}` returns `Close == [101.0]` and no column in `ADJUSTED_CLOSE_COLUMNS`. Also: `assert not set(COLUMN_MAP) & set(ADJUSTED_CLOSE_COLUMNS)`; and with `lib.data_loader._query_cloud_sql` patched to record its SQL and return a one-row frame, `DataLoader()._load_daily_from_sql('SPY', None)` issues SQL in which `'adjusted_close' not in sql` for every recorded statement.
- [ ] **Step 2: Run** `python3 -m pytest tests/lib/test_data_loader.py -k adjusted -q`. Expected: FAIL (`ImportError: ADJUSTED_CLOSE_COLUMNS`; on main the first frame returns the adjusted close as `Close`).
- [ ] **Step 3: Implement.** Add the constant beside `COLUMN_MAP`; remove the `Adj Close` and `adj_close` keys. In `normalize_columns`, before the rename: if any column is in `ADJUSTED_CLOSE_COLUMNS` and none of `Close`, `close`, `Last`, `last` is present, raise `ValueError(f"{col}: a split- or dividend-shaded price is never taken as a close (FEAT-DATA-001)")`; otherwise drop those columns. Remove `adjusted_close` from the SELECT at `:557`.
- [ ] **Step 4: Run** `python3 -m pytest tests/lib/test_data_loader.py -q`. Expected: all pass. Render step.
- [ ] **Step 5: Commit:** `fix(lib): the data loader never takes an adjusted close as a close`

### Task 9: `lib/strat.py`, the NaN audit, the two experiments, the basis-check comment

Spec: § Design 5 (`lib/strat.py`, experiments), § Design 1 (`nan_triage.sql`, the basis-check comment), Decision 7. Advances done_when[9], [11].

**Files:**
- Modify: `lib/strat.py:1506`; `gcp/queries/nan_triage.sql:31`; `scripts/analysis/brief_rsi_band_experiment.py:12-13`, `:56`, `:71-74`; `scripts/analysis/honest_scoring_experiment.py:95-97`; `gcp/fetchers/fetch_alphavantage_intraday.py:1170`, `:1175-1176`
- Test: `tests/lib/test_strat_history.py:204-208`; `tests/gcp/test_no_adjusted_prices.py`

- [ ] **Step 1: Change and write the tests.** `test_actual_source_basis_unavailable_before_loader` keeps `price_basis='av-adjusted-daily-v1'` and the `DataLoader.__init__` trap, and matches `'unsupported or mixed history price basis'`. New `test_experiments_read_the_as_traded_export`: in `tmp_path`, `SPY_daily.csv` with columns `timestamp,open,high,low,close,volume` loads through `brief_rsi_band_experiment.load_daily(str(tmp_path), 'SPY')` to columns `Open, High, Low, Close, Volume, Time`; the same file with an `adjusted_close` column raises `ValueError` naming it, through `load_daily` and through `honest_scoring_experiment.daily_bars('SPY', bars, daily_dir=str(tmp_path))` with `bars = pd.DataFrame({'Time': pd.to_datetime([])})`.
- [ ] **Step 2: Run** `python3 -m pytest tests/lib/test_strat_history.py -k basis_unavailable tests/gcp/test_no_adjusted_prices.py -k experiments -q`. Expected: FAIL (the message says "admission unavailable"; the experiments read `{T}_daily_adjusted.csv`).
- [ ] **Step 3: Implement.** `_history_contract` admits `price_basis in ('synthetic_coherent',)` only. `nan_triage.sql:31` drops its `adjusted_close` FILTER term. Both experiments read `{T}_daily.csv` (a `TIME_SERIES_DAILY` export) and raise `ValueError` when the file holds a column in `lib.data_loader.ADJUSTED_CLOSE_COLUMNS` (imported, not spelled); docstring `:12-13` names the new export. Comment `:1170`: "Until 2026-11-13 the 1-min requests returned prices adjusted for splits and dividends"; `:1175-1176`: the daily endpoint is `TIME_SERIES_DAILY` ("2. high" / "3. low", as traded).
- [ ] **Step 4: Run** the Step 2 command (expect all pass), then the done_when[11] grep: `grep -n -E 'TIME_SERIES_DAILY_ADJUSTED|dividend-adjusted|split-adjusted' gcp/fetchers/fetch_market_data.py gcp/backfill_ticker.py gcp/migrate_to_gcp.py gcp/fetchers/fetch_alphavantage_intraday.py lib/earnings_reactions.py scripts/backfill_watchlist_data.py scripts/fetch_market_data.py scripts/analysis/brief_rsi_band_experiment.py`. Expected: no output, exit 1 (on main: 22 lines, `:1170` among them). Render step.
- [ ] **Step 5: Commit:** `fix(data): no strat basis, audit query or experiment names an adjusted series`

### Task 10: `fetch_splits` and the reaction SELECTs

Spec: § Design 6 ("Split evidence"), § Design 5 (the two SELECTs). Advances done_when[6], closes [2].

**Files:**
- Modify: `lib/earnings_reactions.py` (new types beside `database_daily_price_evidence`); `gcp/fetchers/compute_earnings_reactions.py:617-621`, `:676-680`, new `fetch_splits`
- Test: `tests/gcp/test_compute_earnings_reactions.py`; `tests/lib/test_av_account_allowance.py:10-23`

**Interfaces:**
- Produces, in `lib/earnings_reactions.py` (pure; `lib/` imports nothing from `gcp/`):
  - `@dataclass(frozen=True) class Splits: ticker: str; events: tuple[tuple[date, float], ...]; digest: str`, events sorted by date, `digest` the sha256 hex of `json.dumps([{"effective_date": d.isoformat(), "split_factor": f} for d, f in events], sort_keys=True, separators=(",", ":"))`; `Splits.of(ticker, events) -> Splits` builds both.
  - `class SplitsUnavailable(Exception)` with attribute `reason: str`.
- Produces, in `compute_earnings_reactions` (re-exporting both names): `fetch_splits(ticker: str, api_key: str) -> Splits`: one `requests.get(AV_BASE_URL, params={'function': 'SPLITS', 'symbol': av_listed_symbol(ticker), 'apikey': api_key}, timeout=30)`, no pacing inside (the caller paces); an empty `api_key` raises `ValueError` before any request (an INTERNAL misconfiguration, never a `SplitsUnavailable`).

- [ ] **Step 1: Write the failing test** `test_fetch_splits_request_and_reply` (patch `requests.get` on the module):
  - `fetch_splits('BF.B', 'k')` sends `function 'SPLITS'`, `symbol 'BF-B'`.
  - Reply `{"symbol": "NVDA", "data": [{"effective_date": "2024-06-10", "split_factor": "10.0000"}, {"effective_date": "2021-07-20", "split_factor": "4.0000"}]}` gives `events == ((date(2021, 7, 20), 4.0), (date(2024, 6, 10), 10.0))` and a 64-character hex `digest`; the same two events in the other order give the same digest; a factor of `"2.0000"` gives another.
  - `{"symbol": "SPY", "data": []}` gives `events == ()`.
  - Each of these raises `SplitsUnavailable`: `{"Information": "x"}`, `{"Note": "x"}`, `{"Error Message": "x"}`, `{"symbol": "X"}` (no `data`), a response whose `raise_for_status` raises `requests.HTTPError`, `{"data": [{"effective_date": "2024-13-40", "split_factor": "10"}]}`, `{"data": [{"effective_date": "2024-06-10", "split_factor": "ten"}]}`.
  - `fetch_splits('SPY', '')` raises `ValueError` and sends nothing.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_compute_earnings_reactions.py -k fetch_splits -q`. Expected: FAIL (`fetch_splits` does not exist).
- [ ] **Step 3: Implement** the types and `fetch_splits`. `compute_earnings_reactions` imports `av_listed_symbol` from `gcp.fetchers.fetch_market_data` and `AlphaVantageConfig` from `lib.config` (the latter used in Task 11's pacing; import it now). Remove `adjusted_close` from both SELECT lists. In `tests/lib/test_av_account_allowance.py`, add `'gcp/fetchers/compute_earnings_reactions.py'` to `CONSUMERS`.
- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_compute_earnings_reactions.py -k fetch_splits tests/lib/test_av_account_allowance.py::test_direct_consumer_inventory_is_complete_and_does_not_load_consumers -q`. Expected: pass. Render step.
- [ ] **Step 5: Commit:** `feat(data): read each reporter's splits from AlphaVantage for the reaction run`

### Task 11: the earnings price gate: as traded, split checked

Spec: § Design 6 ("The gate", items 1 to 4). Advances done_when[3], [4] (native test).

**Files:**
- Modify: `lib/earnings_reactions.py:1310-1357`; `gcp/fetchers/compute_earnings_reactions.py:805`, `:812` (the two gate calls), the per-ticker loop head (`:752-756`)
- Test: `tests/gcp/test_compute_earnings_reactions.py` (new test; `test_native_pre10_prefix_is_qualified_by_actual_producer_not_short_path`, `:1149-1194`)

**Interfaces:**
- Consumes: `Splits`, `SplitsUnavailable`, `fetch_splits` (Task 10).
- Produces: `AS_TRADED_DAILY_SOURCES = ('alphavantage', 'alphavantage_daily', 'av_daily_backfill', 'av_watched_backfill')`; `database_daily_price_evidence(event, frame, *, schedule, observed_at, splits: Splits | SplitsUnavailable, native=False) -> dict` (keyword required, no default).

- [ ] **Step 1: Write the failing test** `test_price_basis_is_as_traded_and_split_checked`. Window: `earnings_session_schedule(date(2026, 1, 1), date(2026, 2, 20))`, report `SYNTH` BMO on 2026-02-02, rows for the 18 sessions from D-12 (the shape of `:1155-1158`) with `data_source 'alphavantage_daily'` and no `adjusted_close` column. With `none = Splits.of('SYNTH', ())`:
  - returns `available` True, `receipt['price_basis_id'] == 'av-as-traded-no-split-v1'`, `receipt['source_id']` starting `'current-db-projection:'` and ending `':splits:' + none.digest`, `evidence_grade == 'current_db_writer_declaration_only'`.
  - `Splits.of('SYNTH', ((date(2010, 1, 4), 2.0),))` keeps `available` and changes `source_id`.
  - the same rows with `adjusted_close = close * 0.99` added return a receipt equal to the first (the column is outside the projection).
  - `Splits.of('SYNTH', ((date(2026, 2, 2), 2.0),))` (after the first required session, D-1, and on or before the last) returns `available` False, `reason == 'split_in_window'`; one effective 2026-01-30 (D-1, the first required session itself) is admitted with `native=False` and refused with `native=True`, whose required sessions start at D-10.
  - `SplitsUnavailable('Information')` returns `reason == 'split_status_unavailable'`.
  - `data_source` None, or `'yfinance'`, on any row returns `reason == 'unrecognized_database_price_writer'`.
  - every other case also with `native=True`, same answers.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_compute_earnings_reactions.py -k as_traded_and_split -q`. Expected: FAIL (`TypeError` on `splits=`; on main the first window refuses `missing_database_price_basis_metadata`, the dividend window `unresolved_adjustment_or_corporate_action`).
- [ ] **Step 3: Implement the gate** in the order of spec Design 6: require a `data_source` column; every required row's tag in `AS_TRADED_DAILY_SOURCES`; no read of `adjusted_close`; `SplitsUnavailable` refuses `split_status_unavailable`; a `Splits` event with `required[0] < effective_date <= required[-1]` refuses `split_in_window`; the projection is `date, open, high, low, close, data_source`. Docstring: as-traded writer tags and an explicit split check; never a guessed split threshold.
- [ ] **Step 4: Wire the producer.** In `populate_for_tickers`, per ticker group and before its events: pace with `time.sleep(AlphaVantageConfig().delay_between_calls)` between tickers, then `splits = fetch_splits(ticker, api_key)`, catching `SplitsUnavailable` as `splits = exc`. `api_key` is a new keyword of `populate_for_tickers` (default `None`, then `os.environ.get('ALPHA_VANTAGE_API_KEY', '')`). Both gate calls pass `splits=splits`. An event of a ticker whose `splits` is a `SplitsUnavailable` is skipped before `compute_reaction` with `_event_receipt(eps.to_dict(), 'price_inputs', 'split_status_unavailable', 'write_skipped')`.
- [ ] **Step 5: Update** `test_native_pre10_prefix_is_qualified_by_actual_producer_not_short_path`: rows lose `adjusted_close` (`:1158`, `:1180`, `:1187`), `module.fetch_splits` is monkeypatched to `lambda t, k: Splits.of(t, ())`; every assertion stays. Every other caller of `populate_for_tickers` gets the same `fetch_splits` stub, so no test reaches the vendor: `tests/gcp/test_compute_earnings_reactions.py:1125`, `:1143`, `:1210` and `tests/integration/test_earnings_daily_path_persistence.py:204-209` (run in CI by `.github/workflows/backtest-pipeline.yml:163`).
- [ ] **Step 6: Run** `python3 -m pytest tests/gcp/test_compute_earnings_reactions.py -q` (expect all pass) and, where a Postgres is available, `python3 -m pytest tests/integration/test_earnings_daily_path_persistence.py -q` (expect pass; otherwise CI runs it). Render step.
- [ ] **Step 7: Commit:** `feat(data): earnings price gate admits as-traded windows after a split check`

### Task 12: the event-level split refusal, progress and the run's exit code

Spec: § Design 6 ("The event-level refusal", "unavailable" bullet, Capacity log line). Advances done_when[4], [5].

**Files:**
- Modify: `gcp/fetchers/compute_earnings_reactions.py:780-792`, `:838-844`, `:978-1024`, `:1289-1290`
- Test: `tests/gcp/test_compute_earnings_reactions.py`

**Interfaces:**
- Produces: `populate_for_tickers(..., api_key=None, counts: dict | None = None) -> int`; when given, `counts` is filled with `split_tickers` (tickers whose `SPLITS` was requested) and `splits_unavailable`. `main() -> int`; the module ends `sys.exit(main())`.

- [ ] **Step 1: Write the failing tests.**
  - `test_split_in_loaded_window_skips_the_event`: two tickers, `AAA` (two BMO events, 2026-02-02 and 2025-11-03) and `BBB` (one BMO event, 2026-02-02); windows built from `earnings_session_schedule` as the native test builds them (`:1151-1158`), each from D-12 to D+5; `fetch_daily_windows_for_ticker_dates`, `fetch_earnings_history_for_tickers` and `fetch_calendar_timing_map` stubbed, `is_cloud_sql_configured` True, `_upsert_reaction_frame` recorded, `observation_ts='2026-02-20T21:01:00Z'`; `fetch_splits` recorded. Case 1: AAA's splits hold 2026-01-20, inside AAA's 2026-02-02 loaded window (after its first bar, on or before its last) and outside the gate's required sessions (D-1 to D+5), so only the event-level check can refuse it: that event writes no row and a page sent to `receipt_sink` holds `{'metric_group': 'price_inputs', 'reason': 'split_in_window', 'disposition': 'write_skipped'}` for its `event_id`; AAA's 2025 event is written with `daily_path_v1['basis_id'] == 'av-as-traded-no-split-v1'`; `fetch_splits` called exactly once per ticker (`['AAA', 'BBB']`). Case 2: a split effective on the first loaded bar is admitted. Case 3: BBB's `SPLITS` reply holds `Information` (stub raising `SplitsUnavailable('Information')`): BBB's event is `write_skipped` with `split_status_unavailable`, AAA's events are written, no upserted row carries ticker BBB, and `caplog` holds `splits_unavailable=1`.
  - `test_every_splits_request_failing_fails_the_run`: the stubs of the previous test, `sys.argv = ['compute_earnings_reactions', '--tickers', 'AAA,BBB', '--force']`, env `ALPHA_VANTAGE_API_KEY=k`, both `fetch_splits` raising `SplitsUnavailable`: `main() == 1`, the upsert recorder never called, `caplog` holds `splits_unavailable=2`. With AAA's reply valid: `main() == 0` and AAA's rows are upserted. Without `ALPHA_VANTAGE_API_KEY`: `main() == 1` before `fetch_earnings_history_for_tickers` is called.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_compute_earnings_reactions.py -k "split_in_loaded or every_splits" -q`. Expected: FAIL (the straddling event is written; `main()` returns None).
- [ ] **Step 3: Implement.** After the cut to completed sessions (`:780-792`) and before `compute_reaction`: if `isinstance(splits, Splits)` and any event has `first < effective_date <= last` over the loaded `daily['date']`, skip with `_event_receipt(eps.to_dict(), 'price_inputs', 'split_in_window', 'write_skipped')`. Log `ticker=%s splits=%d processed=%d/%d` after every ticker (replacing the every-25 line's condition, `:838-844`), and `splits_unavailable=%d` once after the loop. `main()` requires `ALPHA_VANTAGE_API_KEY` (log and return 1), passes `counts`, returns 1 when `counts['split_tickers'] > 0 and counts['splits_unavailable'] == counts['split_tickers']`, else 0; every early `return` becomes `return 0`.
- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_compute_earnings_reactions.py -q`. Expected: all pass. Render step.
- [ ] **Step 5: Commit:** `feat(data): skip a reaction whose loaded window holds a split, and fail a run with no split evidence`

### Task 13: the guard

Spec: § Design 7 (every bullet). Advances done_when[10], confirms [11].

**Files:**
- Test: `tests/gcp/test_no_adjusted_prices.py`

**Interfaces:**
- Produces: `adjusted_sites(src: str, rel: str) -> list[tuple[int, str]]` (line, rule) for one `.py` text; `sql_adjusted_lines(text: str, rel: str) -> list[int]`; `tree_sites(root: Path) -> list[tuple[str, int, str]]` over `gcp/`, `lib/`, `scripts/`, `platform/` (paths with a `tests` part, `test_*.py` files and `node_modules` excluded).

- [ ] **Step 1: Write the tests.** Rules exactly as Design 7, with these regexes: function names `\b[A-Z0-9]+(?:_[A-Z0-9]+)*_ADJUSTED\b`; names `adj(?:usted)?[\s_.\-]*close|adjclose|adjusted[\s_.\-]*daily|daily[\s_.\-]*adjusted` (case-insensitive), applied to every string constant that is not a docstring. A request parameter is a key of a dict literal holding a `'function'` key, or a keyword of a call to `requests.get`, `requests.post`, `requests.request`, any call whose root name a `yfinance` import bound, `fetch_minute_bars` or `fetch_minute_data`; its name `adjusted` or `auto_adjust` with a value other than the constant `'false'` or `False` is refused; `**{...}` keys count; `**<anything else>` is refused. The one allowance: the strings inside the value of the module-level assignment `ADJUSTED_CLOSE_COLUMNS` in `lib/data_loader.py`. `.sql` files under `gcp/` by text, allowed only on the two `gcp/schema.sql` lines whose stripped text is `-- Split/dividend-adjusted close from AlphaVantage TIME_SERIES_DAILY_ADJUSTED` and `adjusted_close      DOUBLE PRECISION,`.
  - `test_nothing_in_the_repo_fetches_stores_or_reads_an_adjusted_price`: `tree_sites(REPO) == []` and the `.sql` scan finds nothing outside the allowance.
  - `test_the_guard_tells_adjusted_from_everything_else`, parametrized `(src, rel, n)`: one violation per rule (`"f = 'TIME_SERIES_WEEKLY_ADJUSTED'"`, `"c = 'Adj Close'"`, `"p = {'function': 'X', 'adjusted': 'true'}"`, `"yf.download('SPY', auto_adjust=True)"` after `import yfinance as yf`), 1 each; `counts = {"as_traded": 0, "inferred": 0, "adjusted": 0, "odd": 0}`, 0; `{'function': 'TIME_SERIES_INTRADAY', 'adjusted': True}`, 1; `{'function': 'TIME_SERIES_INTRADAY', 'adjusted': 'false', **{'adjusted': 'true'}}`, 1; `{'function': 'TIME_SERIES_INTRADAY', **extra}`, 1; `x.ewm(span=9, adjust=False)`, 0; `verdict = 'ADJUSTED'`, 0; `{'function': 'TIME_SERIES_INTRADAY', 'adjusted': 'false'}`, 0; a docstring naming `TIME_SERIES_DAILY_ADJUSTED`, 0; `ADJUSTED_CLOSE_COLUMNS = ('Adj Close', 'adj_close', 'adjusted_close', 'adjclose')` as `lib/data_loader.py`, 0, and the same as `lib/other.py`, 4; `df['Adj Close']` as `lib/data_loader.py`, 1.
- [ ] **Step 2: Prove the guard on main.** `git worktree add /tmp/noadj-main origin/main`, then `python3 -c "from pathlib import Path; from tests.gcp.test_no_adjusted_prices import tree_sites; s = tree_sites(Path('/tmp/noadj-main')); print(len({(f, l) for f, l, _ in s}), len({f for f, _, _ in s}))"`. Expected: `31 12` (a prototype of these rules gave the same over origin/main 90c41e6d on 2026-11-17; the spec's 4155a10f figure). The `.sql` scan over that tree flags `gcp/queries/nan_triage.sql:31` only: 32 locations in 13 files. Remove the worktree.
- [ ] **Step 3: Run** `python3 -m pytest tests/gcp/test_no_adjusted_prices.py -q`. Expected: all pass on the branch. If a site is reported, it is a Problem 1 site an earlier task missed: fix it there, never widen the guard.
- [ ] **Step 4: Commit:** `test(data): guard every price request and column against an adjusted basis`

### Task 14: the reader list, `make test`, the inventory

Spec: § Close-out steps 1 and 2; § Implementation plan item 13. Advances done_when[12], [13].

**Files:**
- Test: `tests/gcp/test_no_adjusted_prices.py`

**Interfaces:**
- Consumes: `scripts.maintenance.doc_inventory.deploy_jobs(root)`, `deploy_services(root)`, `entry_module(job)`, `deploy_targets(root)` (read only).
- Produces: `adjusted_readers(root: Path) -> list[dict]`, one row per deployed job or service whose entry module reaches, through its `import` statements at any depth (absolute and relative, function-level imports included), `lib/data_loader.py`, `lib/strat.py` or a module whose text contains `adjusted_close` in `root`; each row `{kind, name, entry, reaches, target}` with `target` the `./gcp/deploy.sh` dispatcher arm whose closure calls the job's `deploy_*` function (for `solyra-api-staging`, `platform/deploy.sh`). Runnable as `python3 -m tests.gcp.test_no_adjusted_prices --readers <root>`, printing a markdown table.

- [ ] **Step 1: Write the test** `test_reader_walk_finds_the_direct_importers`: on `REPO`, the entries of the rows include `gcp/signal_monitor.py`, `gcp/signal_monitor_eod_resolver.py`, `gcp/premarket_brief.py`, `gcp/regime_combo_job.py`, `gcp/indicator_correlation_job.py` and `platform/api/main.py` (each imports `lib.data_loader` directly, `grep -rln data_loader gcp platform`), and `gcp/fetchers/fetch_market_data.py`, `gcp/fetchers/backfill_daily_indicators.py` and `gcp/backfill_ticker.py` (each imports `lib.strat`); `gcp/trade_logger.py` is listed only if the walk reaches one of the three through another module (it imports none of them directly, `gcp/trade_logger.py:21-240`).
- [ ] **Step 2: Run** it (expect FAIL: no function), implement, run again (expect PASS).
- [ ] **Step 3: Produce the list for the PR body** over the merge base, where the old images' code still names `adjusted_close`: `git worktree add /tmp/noadj-base $(git merge-base HEAD origin/main)`, `python3 -m tests.gcp.test_no_adjusted_prices --readers /tmp/noadj-base`. Paste the table under "Readers to deploy (Close-out steps 1 and 2)" with the command line; remove the worktree.
- [ ] **Step 4: Run** `make test`. Expected: exit 0 (after R is merged in; before, only the two `tests/meta` cases of Task 6 fail). Then the render step and `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect pass).
- [ ] **Step 5: Commit:** `test(data): list every deployed reader of the loader, strat and the old column`

### Task 15: close

Spec: § Done when; § Design 8 (site notes). Closes done_when[14].

- [ ] **Step 1: Catalog.** In the FEAT-DATA-001 record of `docs/product/02-FEATURE-CATALOG.md` (`:513`), Status gains "no adjusted price fetched, stored or read; earnings reactions split-checked (#<PR>), rollout pending" and Last reviewed is the head commit's date. Touch no other record.
- [ ] **Step 2: Traceability.** Add this PR under `### FEAT-DATA-001` of `docs/product/12-PR-ISSUE-TRACEABILITY.md` (`:320`), closing #1979.
- [ ] **Step 3: Site notes.** Produce once to read the source identity: `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`, then `git checkout -- docs/review-evidence/site-source-snapshot.json`. In `## Implementation-source notes` of `docs/product/03-SITE-TRACEABILITY.md`, a `(FEAT-DATA-001, <id>)` row for each of ADMIN-06, CATALYSTS-01, CHARTS-01, CHARTS-03, DASHBOARD-01, DASHBOARD-21, INSIGHTS-01, INSIGHTS-07, JOURNAL-01, JOURNAL-04, LIVE-04, PLAYBOOK-05, each cell `source_identity_sha256=<hash>; ` then what the source now does (Design 8: the daily request is `TIME_SERIES_DAILY` and nothing writes or reads the adjusted column; for DASHBOARD-21, INSIGHTS-07 and JOURNAL-04, an adjusted close is never taken as a close; for INSIGHTS-07, the history contract admits no adjusted basis), claiming no page change. The eight rows that exist (ADMIN-06, CHARTS-01, DASHBOARD-01, DASHBOARD-21, INSIGHTS-01, JOURNAL-01, LIVE-04, PLAYBOOK-05) are extended: new hash and this prose first, then `Earlier: ` and the earlier prose unchanged. Commit, then `produce` again, commit the sidecar, and `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 16777216 --max-entries 20000`. Expected: exit 0, `identity-matched`, route `declared-note`.
- [ ] **Step 4: Docs audit.** `python3 scripts/maintenance/docs_audit.py --issues-snapshot <capture under a day old> --no-owning-job-check --json` on the head and on `origin/main` with one capture, diffed by (check, document, severity, detail). Expected: nothing new on the head.
- [ ] **Step 5: Gate.** `python3 scripts/gate/spec_gate.py --pr origin/main`. Expected: `spec gate ok`.
- [ ] **Step 6: Ready.** Tick each done_when line in the PR body with its evidence (test name and output, the grep, the reader table, the verify output), confirm R is merged and the branch has merged `main`, then mark the PR ready.

## Choices this plan makes where the spec leaves one open

- Code order: this spec merges first, then SPY/QQQ/IWM-only, then the admin editor (Task 1). The SPY/QQQ/IWM-only plan adds its on-demand frame's tag to `AS_TRADED_DAILY_SOURCES`, as spec Design 6 item 1 says.
- `Splits` and `SplitsUnavailable` live in `lib/earnings_reactions.py`, so the gate in `lib/` never imports `gcp/`; `compute_earnings_reactions` re-exports them and owns `fetch_splits`.
- `fetch_splits` does no pacing; `populate_for_tickers` sleeps `delay_between_calls` between tickers. Its HTTP timeout is 30 s.
- `populate_for_tickers` keeps its `-> int` return (existing tests assert it) and reports split counts through a `counts` dict; `main()` returns an exit code.
- The run exits 1 only when every requested `SPLITS` failed (spec Design 6); a partial outage exits 0 with each refused event named.
- A records PR (Task 1, Step 4) clears the deleted files' citations from `docs/product/` before this PR is ready; the spec named only the generated inventories.
- The reader walk lives in the test module with a `--readers` entry point, so the PR-body list is reproducible; it reads `doc_inventory`'s deploy parsers rather than parsing `gcp/deploy.sh` again.
- The timezone ratchet's `fetch_av_indicators.py` entry is dropped in Task 6 (the spec does not mention the ratchet).
