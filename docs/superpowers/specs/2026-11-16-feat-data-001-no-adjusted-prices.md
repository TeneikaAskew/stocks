---
feat_id: FEAT-DATA-001
req_ids: [REQ-CAP-001, REQ-DATA-001, REQ-DATA-003]
issues: []
canvases: []
site_source_notes: [ADMIN-06, CATALYSTS-01, CHARTS-01, CHARTS-03, DASHBOARD-01, DASHBOARD-21, INSIGHTS-01, INSIGHTS-07, JOURNAL-01, JOURNAL-04, LIVE-04, PLAYBOOK-05]
done_when:
  - "tests/gcp/test_no_adjusted_prices.py::test_daily_writers_request_as_traded passes: with requests.get captured and every upsert_dataframe call recorded, fetch_market_data.fetch_daily_from_av, fetch_market_data._av_get_full_daily_series, backfill_ticker.av_daily_full with backfill_ticker.run, migrate_to_gcp.migrate_market_data_daily_av for SPY, scripts.backfill_watchlist_data.backfill_daily and scripts.fetch_market_data.fetch_historical_daily_data each send function TIME_SERIES_DAILY and read volume from the reply's '5. volume'; no recorded market_data_daily frame and no returned frame or dict holds adjusted_close or 'Adj Close' (on main each sends TIME_SERIES_DAILY_ADJUSTED, and four of them carry adjusted_close)"
  - "tests/gcp/test_no_adjusted_prices.py::test_no_writer_emits_adjusted_close passes: fetch_market_data.process_ticker for one ticker over stubbed 1-minute and TIME_SERIES_DAILY replies, and fetch_market_data.fetch_and_upsert_vix over a stubbed Yahoo reply, record market_data_daily frames none of which holds an adjusted_close column (on main the first carries it through build_daily_row, fetch_market_data.py:248 and :288, and the second sets it at :731)"
  - "scripts/deep_backfill_ticker.py and gcp/fetchers/fetch_av_indicators.py do not exist on the PR head (Decisions 2 and 3), and tests/lib/test_av_account_allowance.py::test_direct_consumer_inventory_is_complete_and_does_not_load_consumers passes with gcp/fetchers/fetch_av_indicators.py removed from CONSUMERS and gcp/fetchers/compute_earnings_reactions.py added"
  - "tests/gcp/test_compute_earnings_reactions.py::test_price_basis_is_as_traded_and_split_checked passes: lib.earnings_reactions.database_daily_price_evidence over a window with no adjusted_close column, data_source alphavantage_daily and split evidence holding no split returns available with price_basis_id av-as-traded-no-split-v1 and a source_id that changes when the split evidence changes; the same window carrying a stored adjusted_close shaded by a dividend is admitted with the same receipt; a split effective after the first and on or before the last required session refuses with split_in_window; unavailable split evidence refuses with split_status_unavailable; a NULL or yfinance data_source refuses with unrecognized_database_price_writer (on main the first window refuses with missing_database_price_basis_metadata and the dividend window with unresolved_adjustment_or_corporate_action)"
  - "tests/gcp/test_compute_earnings_reactions.py::test_split_in_loaded_window_skips_the_event passes: populate_for_tickers over stubbed earnings_history rows, daily windows and fetch_splits calls fetch_splits once per ticker; an event whose loaded window holds a split effective after its first bar and on or before its last writes no row and emits a write_skipped receipt with reason split_in_window; a SPLITS reply holding Information makes every event of that ticker write_skipped with split_status_unavailable while another ticker's events are written, and the run logs splits_unavailable=1; an event with no split in its window is written with daily_path_v1 basis_id av-as-traded-no-split-v1; and test_native_pre10_prefix_is_qualified_by_actual_producer_not_short_path passes with adjusted_close removed from its rows and fetch_splits stubbed to no split (on main fetch_splits does not exist)"
  - "tests/gcp/test_compute_earnings_reactions.py::test_every_splits_request_failing_fails_the_run passes: the job entry point (compute_earnings_reactions.main) over two tickers with events, both of whose SPLITS replies hold Information, writes no reaction, logs splits_unavailable=2 and exits non-zero; the same run with one ticker's reply valid writes that ticker's events and exits 0 (on main the entry point prints the returned count and exits 0 when nothing was written)"
  - "tests/gcp/test_compute_earnings_reactions.py::test_fetch_splits_request_and_reply passes: compute_earnings_reactions.fetch_splits('BF.B', key) sends function SPLITS and symbol BF-B, parses a reply shaped {symbol, data: [{effective_date, split_factor}]} into dated factors with a digest, reads an empty data list as no split, and raises SplitsUnavailable for an Information, Note or Error Message reply, a reply without a data list, an HTTP error, and an unparseable date or factor"
  - "tests/lib/test_data_loader.py::TestNormalizeColumns::test_an_adjusted_close_is_never_a_close passes: a frame holding Adj Close, adj_close, adjusted_close or adjclose and no raw close makes normalize_columns raise ValueError naming that column; a frame holding close and Adj Close returns Close equal to the raw close and no adjusted column; COLUMN_MAP holds no adjusted key; the SQL of DataLoader._load_daily_from_sql names no adjusted_close (on main the first returns the adjusted close as Close)"
  - "tests/gcp/test_intraday_as_traded.py passes with test_asking_for_adjusted_minute_bars_is_refused asserting TypeError for adjusted=True on fetch_minute_bars and fetch_minute_data (the keyword is gone), test_daily_fetcher_requests_as_traded_through_both_functions calling fetch_minute_bars without it, and gcp/fetchers/evaluate_ew_strikes.py calling fetch_minute_bars without it; tests/gcp/test_evaluate_ew_strikes.py passes"
  - "tests/lib/test_strat_history.py::test_actual_source_basis_unavailable_before_loader passes with price_basis av-adjusted-daily-v1 refused as an unsupported basis by lib.strat._history_contract before any loader is built, and synthetic_coherent the only basis it admits"
  - "tests/gcp/test_no_adjusted_prices.py::test_nothing_in_the_repo_fetches_stores_or_reads_an_adjusted_price passes: an ast walk of every .py under gcp/, lib/, scripts/ and platform/ (tests and node_modules excluded, docstrings exempt) finds no string naming a vendor function that ends in _ADJUSTED, no string matching adjusted close, adj close, adjclose, adjusted daily or daily adjusted in any spacing or case outside the one allowed assignment ADJUSTED_CLOSE_COLUMNS in lib/data_loader.py, and no dict key or call keyword adjusted or auto_adjust whose value is not the literal false or False; a text scan of every .sql under gcp/ finds those names only on the two lines of gcp/schema.sql that define market_data_daily.adjusted_close; on main the same walk reports 34 locations in 14 files; and ::test_the_guard_tells_adjusted_from_everything_else passes on its seeded cases (each rule's violation, a pandas ewm(adjust=False), the basis verdict string ADJUSTED, an intraday request with adjusted 'false', a docstring naming the old endpoint, the ADJUSTED_CLOSE_COLUMNS assignment in lib/data_loader.py allowed, and the same tuple assigned in any other file or a subscript df['Adj Close'] refused)"
  - "grep -n -E 'TIME_SERIES_DAILY_ADJUSTED|dividend-adjusted|split-adjusted' gcp/fetchers/fetch_market_data.py gcp/backfill_ticker.py gcp/migrate_to_gcp.py gcp/fetchers/fetch_alphavantage_intraday.py lib/earnings_reactions.py scripts/backfill_watchlist_data.py scripts/fetch_market_data.py scripts/analysis/brief_rsi_band_experiment.py returns nothing on the PR head (on main it returns 22 lines)"
  - "The implementation PR body lists every Cloud Run job and service whose entrypoint, deployed by gcp/deploy.sh, reaches lib/data_loader.py, lib/strat.py or a module naming adjusted_close through its imports (an ast walk of the import graph, its output pasted), each with its deploy target; Close-out steps 1 and 2 deploy and verify exactly that list"
  - "make test passes on the PR head, and the generated inventory blocks are re-rendered with scripts/maintenance/doc_inventory.py with tests/scripts/test_check_generated_docs.py passing"
  - "02-FEATURE-CATALOG FEAT-DATA-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the implementation-source notes of 03-SITE-TRACEABILITY.md hold a (FEAT-DATA-001, component) row for each of the twelve declared components beginning with the current source hash (a row an earlier change left is extended: the new hash and this change's prose first, then 'Earlier:' and the earlier prose unchanged), docs/review-evidence/site-source-snapshot.json is regenerated and scripts/maintenance/doc_source_snapshot.py verify accepts it, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing that origin/main does not, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: draft
supersedes: null
---

# Nothing fetches, stores or reads an adjusted price

## The owner's requirement

T, 2026-11-16: "I think adjusted close can be removed because I don't use it." Later the same day: "Yeah, I don't want anything using the adjusted anything. Nothing should be adjusted. It should be as it was traded."

On earnings, the same day: "For earnings the weekly calls are fine, the issue is that we don't need to store the data to refresh it daily." T agreed that the weekly (Sunday) earnings run fetches each reporter's as-traded daily prices only while it runs, computes the reaction, stores only the reaction and keeps no daily bars; that existing reaction rows stay; and that the weekday reaction refresh is retired.

## Scope

- **Code only.** Nothing under `gcp/`, `lib/`, `scripts/` or `platform/` requests, writes, reads or relabels a split- or dividend-adjusted price, and a test keeps it so.
- **Earnings reactions keep a price basis without an adjusted close.** The test `close == adjusted_close` is replaced by a split check against AlphaVantage `SPLITS`, fetched by the same run. A reaction whose window holds a split is refused with a named reason, never adjusted.
- **Stored data is the companion spec's.** `docs/superpowers/specs/2026-11-16-feat-data-001-spy-qqq-iwm-only.md` (draft PR #1977, branch `docs/spec-feat-data-001-as-traded-history`) clears and drops `market_data_daily.adjusted_close` in its Close-out steps 7 and 8, only after this spec's code is deployed everywhere. It also owns which tickers every price fetch covers and where the earnings run gets its prices (see "Order against work in progress").
- References are to `main` a34bbd40 (2026-11-16). "Read" means read in the source or a listing; "run" means executed, with its execution name; anything else says "not checked".

## Problem

### 1. Every adjusted site on `main`

Read (grep over `gcp/ lib/ scripts/ platform/`, then each site opened), with the guard prototype of Design 9 run over the tree: 34 locations in 14 files (run: `guard_proto.py` against the worktree at a34bbd40).

| File | Lines | What it does | Who runs it (read) |
|---|---|---|---|
| `gcp/fetchers/fetch_market_data.py` | :203 request, :248 stores `adjusted_close`, :288 `row.update` carries it into the row, :675 logs it | `fetch_daily_from_av`: the nightly daily row | `fetch-market-data`, scheduler `fetch-market-data-daily` `0 23 * * 1-5` (`gcp/deploy.sh:4622`) |
| same | :995 request, :1012-1020 stores OHLCV only | `_av_get_full_daily_series`: the `--backfill` path | `_run_backfill`, reached from `fetch-earnings-history` (`fetch_earnings_history.py:554-561`, schedulers `gcp/deploy.sh:4774`, `:4778`), from `fetch-watched-tickers` (`fetch_watched_tickers.py:448`) and from `--backfill` |
| same | :731 | `fetch_and_upsert_vix` writes `adjusted_close = close` for `^VIX` (Yahoo chart API) | `fetch-market-data` |
| same | :179 | `fetch_minute_data` passes an `adjusted` keyword through to `fetch_minute_bars`, which refuses `True` (:96-97) | every 1-minute caller |
| `gcp/backfill_ticker.py` | :106 request, :126 parses, :621 stores | `av_daily_full` and `run` | Cloud Run job `backfill-ticker`, run by hand (`gcp/deploy.sh:1294-1312`, deployed with the `discord` target, `:5429`; nothing dispatches it, module docstring :4) |
| `gcp/migrate_to_gcp.py` | :543 request, :575 stores | `migrate_market_data_daily_av`, `--table market_data_daily_av`, symbols SPY, IWM, QQQ, SPX (:509-514) | by hand through `./gcp/deploy.sh migrate` (`:68-77`, `:5362`) |
| `scripts/backfill_watchlist_data.py` | :205 request, :231 stores | `backfill_daily` for each watchlist ticker with under 200 daily rows | `./gcp/deploy.sh backfill` (`:5399`) and the end of `./gcp/deploy.sh all` (`:5489`) |
| `scripts/deep_backfill_ticker.py` | :50 request, OHLCV only | arbitrary tickers from argv (default MSFT, META, MRVL, HIMS, CRCL) | nothing: no deploy target, workflow or caller names it (grep) |
| `scripts/fetch_market_data.py` | :314 request, :342 keeps `Adj Close`, :531 and :575 map `adj_close`/`adjclose` to `Close` | legacy local parquet fetcher (SPY, QQQ, IWM, SPX) | by hand; `.env.example` and the disabled `fetch-market-data.yml.disabled` name it |
| `lib/data_loader.py` | :46-47 | `COLUMN_MAP` turns `Adj Close` and `adj_close` into `Close` on every local parquet load (`normalize_columns`, :317-342) | every `DataLoader` parquet read |
| same | :557 | `_load_daily_from_sql` selects `adjusted_close`; nothing reads the returned column (grep for `adjusted_close` over the four trees finds no reader) | `DataLoader.load_daily` |
| `gcp/fetchers/compute_earnings_reactions.py` | :619, :678 | the two daily window SELECTs read `adjusted_close` | `compute-earnings-reactions` (`gcp/deploy.sh:4775`, `:4779`) |
| `lib/earnings_reactions.py` | :1335-1353 | `database_daily_price_evidence`: Section 4 | same |
| `lib/strat.py` | :1506 | `_history_contract` accepts the basis label `av-adjusted-daily-v1`, then refuses every non-synthetic basis at :1517 | strat history callers; it admits nothing today |
| `scripts/analysis/brief_rsi_band_experiment.py`, `scripts/analysis/honest_scoring_experiment.py` | :56; :97 | offline experiments read `{T}_daily_adjusted.csv` exports and use only the open, high, low, close and volume columns (:71-81; :97-98) | by hand, no database |
| `gcp/queries/nan_triage.sql` | :31 | a hand-run NaN audit counts `adjusted_close` | by hand |
| `gcp/schema.sql` | :110-111 | the column and its comment | the data spec drops it |
| `gcp/fetchers/fetch_av_indicators.py` | :56-65 | AlphaVantage ADX, MFI, ADOSC, AROON, ROC, BBANDS into `market_data_indicators` | not scheduled, run by hand (:28-29) |

Not found anywhere in the four trees (grep): `TIME_SERIES_WEEKLY_ADJUSTED`, `TIME_SERIES_MONTHLY_ADJUSTED`, `auto_adjust`, a `'adjusted': 'true'` request, and any read of `'7. dividend amount'` or `'8. split coefficient'`. yfinance is imported only for earnings dates (`fetch_earnings_history.py:119`, `scripts/fetch_earnings_calendar.py:599`, `:723`), not prices. `adjust=False` in the tree is the pandas `ewm` argument, not a price basis. solyra `src/` and `tests/` name no adjusted close (grep at solyra `main` 80c82c2).

### 2. The two endpoints return the same as-traded fields

- Run: AlphaVantage `TIME_SERIES_DAILY_ADJUSTED` and `TIME_SERIES_DAILY`, SPY, `outputsize=compact`, 2026-11-16. Open, high, low, close and volume are equal on every session spot-checked: 2026-06-25, 2026-07-29, 2026-08-04, 2026-09-16, 2026-09-17 (the session before the 2026-09-18 ex-dividend date, dividend 1.8888), 2026-09-18, 2026-11-05 and 2026-11-13. The adjusted close differs before the ex-dividend date (2026-09-17: close 762.6, adjusted close 760.7136). Not every one of the 100 sessions was compared by a program.
- Measured 2026-11-15 by the owner's session: stored daily OHLC equals `TIME_SERIES_DAILY` exactly on 18 sessions (`db-query-6k2lm`; not re-run here).
- The JSON keys differ for volume: `TIME_SERIES_DAILY` returns `"5. volume"` (run: IWM, JSON, 2026-11-16), the adjusted endpoint `"6. volume"` (read: every writer at `:249`, `:1019`, `backfill_ticker.py:127`, `migrate_to_gcp.py:576`, `backfill_watchlist_data.py:232`). A switch that kept `'6. volume'` would raise `KeyError`, which `fetch_daily_from_av` swallows into `{}` (:252-254, an existing silent fallback) and the nightly then builds the row from 1-minute bars. The tests of Design 1 pin the key.
- Fields 7 and 8 (dividend amount, split coefficient) are read by nothing (grep). Nothing is lost by the switch.

So stored OHLCV stays on the same basis it has always had; what goes is the adjusted close and the endpoint that serves it.

### 3. What the stored daily rows hold

Run, `db-query-xt7kj` (2026-11-16):

| `data_source` | Rows | Tickers | `adjusted_close` not NULL | of which differ from `close` | Dates |
|---|---|---|---|---|---|
| NULL | 4,770,116 | 2,035 | 0 | 0 | 1999-11-01 to 2026-08-17 |
| `av_daily_backfill` | 1,025,574 | 2,654 | 23,002 | 337 | 2016-08-29 to 2026-11-13 |
| `alphavantage_daily` | 10,015 | 11 | 10,015 | 9,939 | 2016-05-02 to 2026-08-03 |
| `alphavantage` | 1,686 | 4 | 1,686 | 1,172 | 2022-05-06 to 2026-04-07 |
| `yahoo` | 144 | 1 | 144 | 0 | 2026-04-27 to 2026-11-13 |

- `av_daily_backfill` rows hold an `adjusted_close` only where the nightly wrote one before the backfill re-stamped the row: the backfill upserts OHLCV and `data_source` only, and `upsert_dataframe` updates only the columns it is given (`gcp/database.py:484`, read).
- SPY, QQQ and IWM hold 7,453 rows whose `adjusted_close` differs from `close` (`db-query-grw47`).
- The writer of the NULL rows is not recorded. They are older than the AlphaVantage daily writers' tags and may come from the Yahoo era; their basis is not checked.

### 4. The earnings price gate depends on the adjusted close

`database_daily_price_evidence` (`lib/earnings_reactions.py:1310-1357`, read) admits a window only when every row is tagged `alphavantage` or `alphavantage_daily` and every `close` equals its `adjusted_close`. Its receipt is `price_basis_id='db-declared-av-raw-equal-adjusted-v1'`. When it refuses, the daily path payload carries the reason and the pre-report drift fields are set to NULL (`compute_earnings_reactions.py:803-826`, read).

- An adjusted close equals the close only when no dividend and no split followed the row up to the fetch. So every dividend payer's history fails, and every `av_daily_backfill` and NULL row fails on its tag.
- Run, `db-query-grw47` and `db-query-xt7kj`: of 67,116 reaction rows, 908 carry a `daily_path_v1` (339 tickers, reports 2016-05-04 to 2026-11-12). All 908 are `unavailable` with reason `unrecognized_database_price_writer`, and none has a pre-report drift value. No stored row carries a `basis_id`, so renaming the basis strands nothing.
- The gate never saw a split as a split: a split and a dividend both fail the same equality. The reaction fields outside the daily path are written either way. A sustain beyond 50% is nulled as "almost always" a split artifact (`SUSTAIN_ANOMALY_PCT`, `compute_earnings_reactions.py:251-257`, read), which is a threshold, not evidence.

### 5. AlphaVantage's technical indicators are computed on adjusted closes

Run, 2026-11-16: AlphaVantage `BBANDS`, SPY, daily, `time_period=20`, `series_type=close`. Its middle band (a 20-session mean of the close) against 20-session means computed from the compact daily series above:

| Session | AlphaVantage middle band | Mean of adjusted closes | Mean of as-traded closes |
|---|---|---|---|
| 2026-09-24 | 763.9202 | 763.9202 | 765.3380 |
| 2026-09-25 | 764.0281 | 764.0281 | 765.3505 |

So `gcp/fetchers/fetch_av_indicators.py` fetches indicators on the adjusted basis. Only BBANDS was measured; the other five functions it requests (ADX, MFI, ADOSC, AROON, ROC) are not checked.

## Non-goals

- No production write, deploy or job run from the implementation PR. Each production step is in Close-out and waits for the owner's yes.
- No stored row is changed. Clearing and dropping `adjusted_close` is #1977's Close-out steps 7 and 8; removing it from `gcp/schema.sql` is its spec B. No other stored row needs changing: stored OHLCV is already as traded (Section 2).
- No change to which tickers any job fetches, nor to where the weekly earnings run gets its daily prices: both are #1977's.
- No change to `gcp/deploy.sh` (FEAT-DEPLOY-001). The job flags and the weekday earnings schedulers belong to #1977's spec C.
- The 50% sustain threshold stays. With the split check it should no longer meet an AlphaVantage-listed split; whether to remove it is not decided here.
- No change to the 1-minute request parameters: every one already asks for `adjusted=false` (`docs/superpowers/specs/2026-11-13-feat-data-001-intraday-as-traded.md`).

## Approaches considered

1. **Switch every daily fetch to `TIME_SERIES_DAILY`, remove every read and write of `adjusted_close`, check splits explicitly for earnings, and guard it all with one test (chosen).** It is the owner's rule with no exception, the stored OHLCV basis does not move, and the guard keeps it.
2. **Keep the adjusted endpoint and drop only the `adjusted_close` field.** Nothing would be stored adjusted, but the code would still ask for an adjusted series, and the guard could not tell a field that is used from one that is not. Rejected by the owner's "nothing using the adjusted anything".
3. **Detect splits from the price series (an overnight gap near 2:1, 3:1, 3:2 and so on) instead of fetching `SPLITS`.** No vendor call, but it is a guess: a real 50% gap or a reverse split at an unlisted ratio defeats it, and the gate's own contract says it "never guesses a split threshold" (`lib/earnings_reactions.py:1315`). Offered as Decision 6's alternative, not recommended.

## Design

### 1. Daily requests: `TIME_SERIES_DAILY`, OHLCV only

| File | Function | Change |
|---|---|---|
| `gcp/fetchers/fetch_market_data.py` | `fetch_daily_from_av` (:182-254) | function `TIME_SERIES_DAILY`; returns open, high, low, close and volume (`'5. volume'`); no `adjusted_close`. The log at :674-675 drops `adj=`. The `except Exception: return {}` at :252-254 gets the `# AUDIT-2026-05-13: silent fallback` marker (CLAUDE.md 3.7), not a fix |
| same | `_av_get_full_daily_series` (:980-1025) | function `TIME_SERIES_DAILY`; volume from `'5. volume'`. Docstring :982-984 corrected |
| same | `fetch_and_upsert_vix` (:696-736) | the `adjusted_close` key at :731 goes |
| `gcp/backfill_ticker.py` | `av_daily_full` (:102-131), `run` (:616-627) | function `TIME_SERIES_DAILY`; no `adjusted_close` parsed or written; docstrings :7, :103, :558 corrected |
| `gcp/migrate_to_gcp.py` | `migrate_market_data_daily_av` (:517-599) | function `TIME_SERIES_DAILY`; no `adjusted_close`; comment :508 and docstring :519-525 corrected (the docstring's "existing rows are updated with adjusted_close" goes) |
| `scripts/backfill_watchlist_data.py` | `backfill_daily` (:179-252) | function `TIME_SERIES_DAILY`; no `adjusted_close`; docstring :11-13 corrected |
| `scripts/fetch_market_data.py` | `fetch_historical_daily_data` (:294-364) | function `TIME_SERIES_DAILY`; the rename keeps `5. volume` as `Volume` and has no `Adj Close`; :531 and :575 map only `close` to `Close` |

- Module docstrings that call the daily rows split- or dividend-adjusted are corrected: `fetch_market_data.py:8`, `:185`, `:263`; the comment at `fetch_alphavantage_intraday.py:1175-1176` names `TIME_SERIES_DAILY` as the daily source of the basis check.
- `gcp/queries/nan_triage.sql:31` drops its `adjusted_close` term.

### 2. `scripts/deep_backfill_ticker.py`: retired (Decision 2)

It exists to pull full history for arbitrary tickers, nothing runs it, and #1977 removes the use: every price fetch covers the default watchlist only, and `fetch_market_data._run_backfill` with explicit tickers and `outputsize='full'` already serves a watchlist ticker. The file goes; its two mentions in the generated `05-c-DATA_DEPENDENCIES.md` inventory are re-rendered.

### 3. `gcp/fetchers/fetch_av_indicators.py`: retired (Decision 3)

Its BBANDS is on the adjusted basis (Problem 5). It is not scheduled. Its table is read only by the magnitude engine's phase-2 research path, and #1977's Decision 10 truncates that table. The file goes, with its entry in `tests/lib/test_av_account_allowance.py` CONSUMERS and the generated `05-a-ARCHITECTURE.md` row. The magnitude engine README's mention is corrected. If phase 2 is wanted again, its indicators are computed in `lib/indicators.py` from as-traded bars, which its own design forbids today ("do NOT compute a substitute and call it the same thing", `fetch_av_indicators.py:12-13`); that is a research decision, not this spec's.

### 4. The 1-minute `adjusted` keyword goes

`fetch_minute_bars` and `fetch_minute_data` lose their `adjusted` parameter (`fetch_market_data.py:85-97`, `:175-179`); `evaluate_ew_strikes.py:396-397` stops passing `adjusted=False`. Every 1-minute request already sends `adjusted='false'` as a literal; the keyword was a switch whose only legal value was False. Passing it now raises `TypeError`.

### 5. Readers

- `compute_earnings_reactions.py:619` and `:678`: `adjusted_close` leaves both SELECT lists. If #1977's change to where the earnings run gets its prices lands first and these queries are gone, this item is done by the guard alone.
- `lib/data_loader.py`: `COLUMN_MAP` loses `Adj Close` and `adj_close`. The four adjusted names are written once, as the module constant `ADJUSTED_CLOSE_COLUMNS = ('Adj Close', 'adj_close', 'adjusted_close', 'adjclose')`, used only to refuse or drop; it is the guard's one allowance (Design 7). `normalize_columns` raises `ValueError` naming the column when a frame holds an adjusted close (a name in `ADJUSTED_CLOSE_COLUMNS`) and no raw close (`Close`, `close`, `Last`, `last`), and drops the adjusted column when both are present. `_load_daily_from_sql` stops selecting `adjusted_close`.
- `lib/strat.py:1506`: `_history_contract` admits `synthetic_coherent` only. `av-adjusted-daily-v1` is refused as an unsupported basis at the same check that refuses every other unknown label. Nothing passes it outside tests (grep).
- The two offline experiments read `{T}_daily.csv`, a `TIME_SERIES_DAILY` export, and raise when the file holds a column named in `lib.data_loader.ADJUSTED_CLOSE_COLUMNS`, imported rather than spelled again (Decision 7).

### 6. The earnings price basis: as traded, with an explicit split check (Decision 5)

**Split evidence, held in memory for the run.** `compute_earnings_reactions.fetch_splits(ticker, api_key) -> Splits`:

- One request per ticker per run: `{'function': 'SPLITS', 'symbol': av_listed_symbol(ticker), 'apikey': api_key}`, paced by `AlphaVantageConfig().delay_between_calls` like `evaluate_ew_strikes.py:389`. The reply is `{"symbol": ..., "data": [{"effective_date": "2024-06-10", "split_factor": "10.0000"}, ...]}` (run: NVDA, 2026-11-16, six events back to 2000-06-27).
- `Splits` holds the dated factors and a sha256 of their canonical JSON. An empty `data` list is a valid answer: no split on record.
- A reply holding `Information`, `Note` or `Error Message`, an HTTP error, a reply without a `data` list, or an unparseable date or factor raises `SplitsUnavailable(reason)`. It is an EXTERNAL failure (CLAUDE.md 3.7): every event of that ticker in the run is refused with `split_status_unavailable`, the other tickers go on, and the run logs `splits_unavailable=<n>`. A run in which every ticker's split request failed exits non-zero.
- `ALPHA_VANTAGE_API_KEY` is already in the job's environment (`gcp/deploy.sh:1038-1041` through `${DB_SECRET_FLAG}` at `:3014`, read). A run without it fails before its first event.
- Why memory and not a table: the owner's rule for this run is to store only the reaction. A `stock_splits` table would need a schema change, a writer and its own freshness, and nothing else reads splits (grep: no `SPLITS` request, `split_factor` or `split_coefficient` reader). Each stored reaction still records which split evidence admitted it: the receipt's `source_id` carries the splits digest, and `daily_path_v1` keeps it as `source_identity` (`lib/earnings_reactions.py:1196`, read). If the run went back to recomputing every reporter's history each week, a table refreshed weekly would cost fewer calls; Decision 5 names that alternative.

**The event-level refusal** (`populate_for_tickers`, `compute_earnings_reactions.py:707-878`). After the window is cut to completed sessions (:780-792) and before `compute_reaction`, an event whose loaded window holds a split effective after its first bar and on or before its last is skipped: no row is written and a `write_skipped` receipt names `split_in_window` (stage `price_inputs`, the pattern of :788-789). The whole loaded window counts, not only the required sessions, because the ATR fallback and the pre-report fields read bars as far as 90 days back (:672-675). A stored row from an earlier run is left as it is (the owner keeps existing rows; the existing refusal path does the same, :767).

**The gate** (`database_daily_price_evidence`, `lib/earnings_reactions.py:1310-1357`) takes a required `splits` argument and:

1. Requires a `data_source` column, and every row's tag in `AS_TRADED_DAILY_SOURCES = ('alphavantage', 'alphavantage_daily', 'av_daily_backfill', 'av_watched_backfill')`, the AlphaVantage daily writers, each of which stored fields 1 to 4 of the daily endpoint (read: Section 1). Anything else, NULL included, refuses with `unrecognized_database_price_writer`, as today. #1977 adds the tag of its on-demand frame to this tuple in its own change.
2. Reads no `adjusted_close`. A frame that still carries the column is not refused for it, and the column is not part of the projection.
3. Refuses `split_status_unavailable` when `splits` is unavailable, and `split_in_window` when a split is effective after the first and on or before the last required session.
4. Otherwise returns the receipt with `price_basis_id='av-as-traded-no-split-v1'`, `source_id` = `current-db-projection:` + the projection digest (date, open, high, low, close, `data_source`) + `:splits:` + the splits digest. `evidence_grade` is unchanged.

Dividends need nothing: an as-traded close is the right basis for a price reaction across an ex-dividend date, which moves the price by the dividend and is a real traded move.

### 7. What the guard does not see, and what it pins

`tests/gcp/test_no_adjusted_prices.py` holds the request tests of Design 1 and the guard:

- Rules, over every `.py` under `gcp/`, `lib/`, `scripts/` and `platform/` by `ast`, tests and `node_modules` excluded, docstrings exempt: no string naming a vendor function that ends in `_ADJUSTED`; no string matching `adjusted close`, `adj close`, `adjclose`, `adjusted daily` or `daily adjusted` in any spacing or case (this covers `adjusted_close`, `Adj Close`, `'5. adjusted close'`, `av-adjusted-daily-v1` and `_daily_adjusted.csv`); no dict key or call keyword `adjusted` or `auto_adjust` whose value is not the literal `'false'` or `False`.
- One allowance: the module-level assignment `ADJUSTED_CLOSE_COLUMNS` in `lib/data_loader.py`, pinned by name and file, so that refusing or dropping an adjusted column never needs the names hidden in built strings. The same names anywhere else, a subscript or `get` included, fail.
- Over every `.sql` under `gcp/` by text: the same names only on `gcp/schema.sql:110-111`, pinned as those two lines of `market_data_daily`. #1977's spec B removes them and this allowance in the same change.
- Run on `main` by a prototype of these rules: 34 locations in 14 files, every one of them listed in Problem 1. The basis check's verdict string `ADJUSTED`, the intraday `adjusted: 'false'` dicts and pandas `ewm(adjust=False)` are not flagged.
- Not seen: a request built without a string literal for its function, files outside the four trees, and AlphaVantage functions whose names do not say adjusted but compute on adjusted closes, as the indicators of Problem 5 do. After Design 3 no file requests one of them (grep for their names as `function` values).

### 8. Site traceability

`site_source_notes` follows the rule the sibling specs use: per page, the first Chain row of `docs/product/03-SITE-TRACEABILITY.md` whose Data cell names a changed job, and for a changed library, whose Backend cell names it. Read at a34bbd40 by script over the cells:

| Page | `fetch-market-data` | `fetch-earnings-history` (its chained backfill) | `backfill-ticker` | `lib/data_loader.py` | `lib/strat.py` |
|---|---|---|---|---|---|
| Dashboard | DASHBOARD-01 (`:331`) | DASHBOARD-01 | DASHBOARD-01 | DASHBOARD-21 (`:351`) | not named |
| Live | LIVE-04 (`:426`) | LIVE-04 | LIVE-04 | not named | not named |
| Charts | CHARTS-01 (`:506`) | CHARTS-03 (`:508`) | CHARTS-01 | not named | not named |
| AI Insights | INSIGHTS-01 (`:750`) | INSIGHTS-01 | INSIGHTS-01 | INSIGHTS-07 (`:756`) | INSIGHTS-07 |
| Catalysts | not named | not named | CATALYSTS-01 (`:830`) | not named | not named |
| Playbook | PLAYBOOK-05 (`:905`) | PLAYBOOK-05 | PLAYBOOK-05 | not named | not named |
| Journal | JOURNAL-01 (`:1041`) | JOURNAL-04 (`:1044`) | JOURNAL-01 | JOURNAL-04 | not named |
| Admin | ADMIN-06 (`:1123`) | not named | not named | not named | not named |

- `compute-earnings-reactions` and `lib/earnings_reactions.py` are named in no Chain cell (read: no Chain row names reactions).
- Each note says what the source now does: the daily request is `TIME_SERIES_DAILY` and nothing writes or reads `adjusted_close`; for the loader rows, that an adjusted close is never taken as a close; for INSIGHTS-07, also that the history contract admits no adjusted basis. None claims a change on a page. Stored rows do not change, so a page shows what it showed.

### 9. Capacity

| Step | Volume | Velocity | Wall-clock | Bound |
|---|---|---|---|---|
| nightly and backfill daily requests | unchanged | one call per ticker either way; `TIME_SERIES_DAILY` replaces `TIME_SERIES_DAILY_ADJUSTED` | unchanged; the reply is smaller (two fewer fields a session) | unchanged |
| `SPLITS`, weekly earnings run | the run's reporters, which #1977 (Design 8) sets to two weeks of reports: those of the last 7 days and those of 14 to 21 days earlier, each report computed twice and no more. Weekly reporters over the last 52 weeks: median 89, mean 152.2, max 755 (`db-query-2k89c`), so about 180 in a median run and at most about 1,500 | one call per ticker per run | paced at 0.4 s (local 150 RPM, `lib/config.py:124`); per-call latency not measured, 0.5 to 1 s assumed: a median run about 4 minutes, the peak about 1,500 x 1.4 s, about 35 minutes (estimates) | today's task timeout 1,800 s (`gcp/deploy.sh:3011`) |
| `SPLITS`, if the run still covered every `earnings_history` ticker | 2,034 tickers (`db-query-xt7kj`) | one call per ticker per run, six runs a week on today's schedulers | 2,034 x 1.4 s, about 47 minutes (estimate) | exceeds 1,800 s |

- The peak run's 35 minutes of split calls already passes the 1,800 s timeout. With #1977's on-demand daily request for the same reporters the run makes two calls a reporter, about 70 minutes at the peak (estimate). The timeout belongs to the deploy surface (spec C of #1977), which sets it from both specs' numbers: at least 4 x 70 minutes, about 16,800 s (CLAUDE.md rule 0.5). Close-out step 1 waits for it.
- The run logs `ticker=%s splits=%d processed=%d/%d` per ticker (rule 0.4).
- Cost: the account is a flat 600 RPM allowance (`lib/config.py:115-124`, read); whether calls are billed one by one is not checked. Cloud Run time for the peak run's split calls, about 35 minutes of 1 vCPU and 1 GiB: about $0.04 a run at list prices (not re-read), under $0.20 a month.

## Order against work in progress

- **#1977 (draft, the universe and stored data).** It owns which tickers every price fetch covers, where the weekly earnings run gets its daily prices (fetched on demand, no bars stored), the deletes, and clearing and dropping `adjusted_close` (its Close-out steps 7 and 8). This spec owns no request or read of an adjusted price, and the split check. Both implementation PRs edit `fetch_market_data.py`, `backfill_ticker.py`, `migrate_to_gcp.py` and `compute_earnings_reactions.py`; whichever merges second rebases, and neither changes the other's lines. #1977's guard of price-request files in `gcp/` holds the same five files either way: this spec switches `backfill_ticker.py` and `migrate_to_gcp.py`, it does not remove them.
- **#1977's steps 7 and 8 wait for this spec's Close-out step 2.** Dropping the column first would break the two SELECTs of Design 5 and `DataLoader.load_daily`, which name it.
- **#1977's spec C (FEAT-DEPLOY-001)** retires the weekday earnings schedulers (`gcp/deploy.sh:4774-4775`) and sets the reaction job's timeout. The split check is deployed only after both (Close-out step 1).
- **#1977's spec B** removes `gcp/schema.sql:110-111` and the guard's two-line allowance together.
- **The approved `docs/superpowers/specs/2026-10-12-feat-data-001-av-market-data.md`** designs an adjusted daily basis (`av-adjusted-daily-v1`, `lib/price_basis.py`, `prepare_daily_basis`, adjusted reads for analytics). None of it exists (no `lib/price_basis.py`; no plan points at that spec). Decision 8 withdraws those parts.
- **The predecessor `docs/superpowers/specs/2026-11-13-feat-data-001-intraday-as-traded.md`** is extended, not replaced: its guard stays, and one of its tests changes as Design 4 says.

## Decisions for the owner

Each is written into the text as recommended. Striking one changes only the sections named.

1. **Every daily fetch uses `TIME_SERIES_DAILY`, and every writer that something still runs is switched, not retired:** the nightly and its backfill path, `backfill-ticker`, `migrate_to_gcp`'s daily path, `scripts/backfill_watchlist_data.py` and `scripts/fetch_market_data.py` (Design 1). Each serves the watchlist tickers once #1977 lands, and retiring the deployed ones would mean `gcp/deploy.sh` changes (spec C). Alternative: retire `backfill-ticker` and `backfill_watchlist_data.py` in spec C as well.
2. **Retire `scripts/deep_backfill_ticker.py`** (Design 2). Alternative: switch it; nothing runs it.
3. **Retire `gcp/fetchers/fetch_av_indicators.py`** (Design 3): its BBANDS is computed on adjusted closes (Problem 5). Alternative: keep it unscheduled, which leaves an adjusted source in the tree and one guard rule short.
4. **`adjusted_close`: code first, then deploy everywhere, then clear, then drop.** No code writes or reads it after this spec; `gcp/schema.sql` keeps the column until #1977's step 8 has dropped it and spec B removes the line. Alternative: drop it from `gcp/schema.sql` in this spec, which would let a fresh environment differ from production until step 8 runs.
5. **Earnings: an explicit split check from AlphaVantage `SPLITS`, fetched by the weekly run for its reporters and held in memory** (Design 6). A reaction whose loaded window holds a split is not written and is named `split_in_window`; unavailable split evidence is named `split_status_unavailable`; the basis is `av-as-traded-no-split-v1`. Alternative: a `stock_splits` table (ticker, effective_date, split_factor, source, fetched_at) refreshed weekly, worth it only if the run recomputes every reporter's history each week.
6. **No split guessing from price gaps.** Alternative: detect split-like overnight gaps instead of calling `SPLITS` (Approach 3): no vendor calls, but a guess.
7. **The two offline experiments read a `TIME_SERIES_DAILY` export** (`{T}_daily.csv`) and refuse a file with an adjusted close. Reproducing their recorded results needs one re-export per ticker; the columns they use are the same values (Problem 2). Alternative: leave them reading the adjusted export's raw columns, which needs a named exemption in the guard.
8. **Withdraw the adjusted-basis parts of the approved 2026-10-12 `av-market-data` spec** (`av-adjusted-daily-v1`, `lib/price_basis.py`, adjusted analytic reads): no later plan under that spec may build them. Its other parts are untouched. Alternative: mark that whole spec superseded, which also drops its registry, telemetry and capacity design.

## Implementation plan: size

One PR of 13 tasks:

1. `fetch_market_data.py`: daily requests, VIX row, log, docstrings, the AUDIT marker (Design 1).
2. `backfill_ticker.py` (Design 1).
3. `migrate_to_gcp.py` (Design 1).
4. `scripts/backfill_watchlist_data.py` and `scripts/fetch_market_data.py` (Design 1).
5. Retire `deep_backfill_ticker.py` and `fetch_av_indicators.py`, with the allowance test and the magnitude README (Designs 2, 3).
6. The 1-minute keyword (Design 4).
7. `lib/data_loader.py` (Design 5).
8. `lib/strat.py`, `nan_triage.sql`, the two experiments and the basis-check comment (Design 5, Design 1).
9. `compute_earnings_reactions.py`: the SELECTs, `fetch_splits`, the event-level refusal, progress logs (Design 6).
10. `lib/earnings_reactions.py`: the gate (Design 6).
11. `tests/gcp/test_no_adjusted_prices.py`: request tests and the guard (Designs 1, 7).
12. Existing tests updated: `tests/gcp/test_backfill_ticker.py`, `test_compute_earnings_reactions.py`, `test_evaluate_ew_strikes.py` (its `_daily` reply, :565-571), `test_fetch_market_data_backfill_sleep.py`, `test_fetch_market_data_backfill_targets.py`, `test_fetch_market_data_intraday_optional.py`, `test_fetch_market_data_vix.py`, `test_fetch_watched_tickers.py`, `test_intraday_as_traded.py`, `tests/lib/test_strat_history.py`, `tests/lib/test_data_loader.py`, `tests/lib/test_av_account_allowance.py`, `tests/scripts/test_backfill_watchlist_level_params.py`, `tests/scripts/test_failure_rate_threshold.py`. `tests/gcp/test_export_intraday_bars.py` and `tests/gcp/test_intraday_verify_basis.py` name only the basis verdict `adjusted`, a measurement of stored 1-minute bars, and stay as they are.
13. Site notes, snapshot, inventories, catalog, traceability, docs audit, gate, and the reader list for Close-out steps 1 and 2.

## Close-out (after the merge, each step on the owner's yes)

1. **Deploy every reader** from `main`, after #1977's implementation is on `main` and spec C has retired the weekday earnings schedulers and raised the reaction job's timeout. Not only the writers: until it is redeployed, a job or service on an older image still selects `adjusted_close` (`DataLoader._load_daily_from_sql`, `lib/data_loader.py:557`), and after #1977's step 8 drops the column that query fails. `signal-monitor`, for one, reads it through `refresh_level_map` (`gcp/signal_monitor.py:890`, read), and neither `fetchers` nor `discord` deploys it. So step 1 deploys every Cloud Run job and service on the reader list of the implementation PR body: each entrypoint `gcp/deploy.sh` deploys that reaches `lib/data_loader.py`, `lib/strat.py` or a module naming `adjusted_close` through its imports, walked by `ast`, with its deploy target. On main a34bbd40 the entrypoints importing the loader directly are `signal_monitor.py`, `signal_monitor_eod_resolver.py`, `premarket_brief.py`, `trade_logger.py`, `regime_combo_job.py`, `indicator_correlation_job.py` (research image), `fetchers/backfill_daily_indicators.py`, `fetchers/fetch_market_data.py`, `backfill_ticker.py` and the API (`platform/api/main.py`, `routers/backtest.py`, `routers/dashboard.py`) (grep); the walk adds those that reach it through another module.
2. **Verify every reader and the daily writer.** Every job and service on the reader list runs an image built from a `main` commit at or after this spec's merge: its image digest, read with `gcloud run jobs describe` or `gcloud run services describe`, is the digest of that build. After the first `fetch-market-data` run on the new image, `SELECT count(*) FROM market_data_daily WHERE date = '<that run date>' AND adjusted_close IS NOT NULL` returns 0 (rows of a new date are inserted without the column). Only when both hold may #1977 run its steps 7 and 8.
3. **Verify the split check.** After the first weekly reaction run on the new image: its log holds a `splits=` line per ticker and `splits_unavailable=0`, and `SELECT daily_path_v1->>'basis_id' AS basis, count(*) FROM earnings_reactions GROUP BY 1` shows `av-as-traded-no-split-v1` rows (today none carries a basis, `db-query-xt7kj`).
4. Hand off to #1977's steps 7 and 8, then spec B.

## Risks

- **A reaction near a split is no longer written.** Today such a row is written with its sustain capped by the 50% threshold. After this spec it is refused by name. The count is not measured.
- **A vendor outage on `SPLITS` stops that week's reactions for the affected tickers,** by name. Re-running the job converges (the upsert is idempotent).
- **The NULL-tagged daily rows stay refused by the gate,** as today, until #1977's on-demand fetch replaces the stored windows.
- **A local parquet file holding only an adjusted close now fails to load** where it used to load as if adjusted were traded. Which local files exist is not checked; the files in GCS `raw/spy/`, `raw/qqq/` and `raw/iwm/` carry `Adj Close` beside `Close` (#1977, Problem 4) and load with the adjusted column dropped.
- **The timeout.** On today's schedules and ticker set the split calls alone would exceed the reaction job's 1,800 s (Capacity). Close-out step 1's precondition is what prevents it.

## What was not verified

- Whether the five other indicator functions of `fetch_av_indicators.py` compute on adjusted closes (only BBANDS was measured).
- The reply of `SPLITS` for an unknown or delisted symbol (only NVDA was called).
- AlphaVantage per-call latency, and whether calls are billed one by one.
- That all 100 compact sessions of the two daily endpoints agree field by field (eight were compared).
- The basis of the 4,770,116 daily rows with no `data_source`.
- How many stored reactions sit within 90 days of a split.
