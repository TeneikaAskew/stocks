---
feat_id: FEAT-DATA-001
req_ids: [REQ-CAP-001, REQ-CAP-002, REQ-DATA-001]
issues: [1980]
canvases: []
site_source_notes: [ADMIN-06, CATALYSTS-01, CHARTS-01, CHARTS-03, DASHBOARD-01, DASHBOARD-04, INSIGHTS-01, JOURNAL-01, JOURNAL-04, LIVE-04, LIVE-08, PLAYBOOK-05]
done_when:
  - "tests/gcp/test_price_fetch_universe.py::test_universe_is_the_active_default_watchlist passes: gcp.fetchers._watchlist.price_fetch_universe(query) makes one strict read of the active rows of the default watchlist (user_id 'default', removed_at NULL, ordered by added_at then ticker) and returns their tickers; a reader raising ConnectionError propagates; an empty result raises EmptyFetchUniverse; require_tracked(['SPY', 'NVDA', 'AMD'], ('SPY', 'QQQ', 'IWM'), job='x') raises UntrackedTickers whose message names NVDA and AMD in that order, and require_tracked(['SPY'], ...) returns; gcp.calibrate_level_params.WATCHLIST_SQL is the same text as the shared one (on main neither function exists)"
  - "tests/gcp/test_price_fetch_universe.py::test_daily_fetcher_follows_the_watchlist passes: fetch_market_data.main() with --tickers ALL and EARNINGS_WINDOW_DAYS=7, over stubbed readers whose watchlist holds IWM, QQQ and SPY and whose earnings window holds NVDA, calls process_ticker for exactly IWM, QQQ and SPY and calls fetch_and_upsert_vix once; with --tickers NVDA it exits 2, logs a line holding UNTRACKED and NVDA, and makes no vendor request; --earnings-window-days is no longer an argument (on main the first run processes the 15 names of TICKERS plus NVDA, and the second fetches NVDA)"
  - "tests/gcp/test_price_fetch_universe.py::test_backfill_targets_follow_the_watchlist passes: fetch_market_data._run_backfill() with BACKFILL_ALL_HISTORY=true, over stubbed readers whose earnings_history and market_data_daily hold NVDA and AMD and whose watchlist holds IWM, QQQ and SPY, plans exactly IWM, QQQ and SPY; _run_backfill(['NVDA']) and _run_backfill(['NVDA'], outputsize='compact', data_source='av_watched_backfill') each raise UntrackedTickers before any vendor request; fetch_watched_tickers excludes the shared universe (not fetch_market_data.TICKERS, which no longer exists) and, with NVDA in its watched set, makes no vendor request for NVDA and exits non-zero (on main the targets are every earnings_history and market_data_daily ticker)"
  - "tests/gcp/test_price_fetch_universe.py::test_premarket_refresh_follows_the_watchlist passes: fetch_premarket_refresh.resolve_universe(target_date), over stubbed readers whose watchlist holds IWM, QQQ and SPY and whose earnings_calendar holds optionable reporters for the day and postmarket reporters for the prior session, returns exactly IWM, QQQ and SPY, and a watchlist read raising ConnectionError propagates; and fetch_premarket_refresh.main with --tickers NVDA exits 2 naming NVDA before any vendor request or database write (on main the reporters are added up to 50, a failed watchlist read is logged and skipped, and --tickers bypasses resolve_universe, fetch_premarket_refresh.py:423-425)"
  - "tests/gcp/test_price_fetch_universe.py::test_intraday_fetch_follows_the_watchlist passes: fetch_alphavantage_intraday.resolve_all_symbols() returns the shared universe; main() with --symbol NVDA, with --symbols-file holding SPY and NVDA, and with --replace-months over a list holding NVDA,2025-01 each exits 2, logs a line holding UNTRACKED and NVDA, and makes no vendor request; --verify-months and --verify-basis read no universe and behave as on main (on main the three runs request NVDA)"
  - "tests/gcp/test_price_fetch_universe.py::test_hand_run_fetchers_follow_the_watchlist passes: gcp.backfill_ticker.main() with BACKFILL_TICKER=NVDA exits 2 before any vendor request; with BACKFILL_ADD_TO_WATCHLIST=true the watchlist row is written before the check and the run proceeds; with BACKFILL_TICKER=SPY it proceeds; gcp.migrate_to_gcp.migrate_market_data_daily_av refuses SPX before any vendor request while the watchlist holds IWM, QQQ and SPY (on main both fetch the ticker they are given)"
  - "tests/gcp/test_price_fetch_universe.py::test_reactions_fetch_without_storing passes: compute_earnings_reactions run on Sunday 2026-12-06, over stubbed earnings_history and earnings_reactions rows, every report of known timing (BMO or AMC), and a stubbed vendor answering TIME_SERIES_DAILY: NVDA (reported Tuesday 2026-12-01, no stored reaction, its D+1 session closed: first pass), AMD (stored reaction whose d_plus_10_close is NULL, its tenth NYSE session after the report closed 3 days before the run: second pass), ORCL (reported 2026-10-20, stored reaction whose d_plus_10_close is still NULL, its tenth session closed weeks before the run: second pass), MSFT (stored reaction, its tenth session not yet closed), IBM (stored reaction whose d_plus_10_close is set), AAPL (reported 75 days before the run, no stored reaction) and CSCO (reported 61 days before the run, stored reaction whose d_plus_10_close is NULL); it selects the reports with one query, makes exactly three daily-series requests, for ORCL, AMD and NVDA in that order (oldest report first), each with function TIME_SERIES_DAILY and outputsize compact, computes their reactions from those series with ATR-14 taken from the same series, issues no read of and no write to market_data_daily, leaves the stored rows of MSFT, IBM, AAPL and CSCO untouched, and commits each ticker's reaction before the next ticker's request (the stub's second request finds the first ticker's row committed); a vendor failure for NVDA is logged with the ticker, writes no reaction row for NVDA and makes the run exit non-zero after the other reporters (on main the job reads market_data_daily for every earnings_history ticker and requests no vendor)"
  - "tests/gcp/test_price_fetch_universe.py::test_friday_report_gets_both_passes passes: for a report on Friday 2026-11-13, the run on Sunday 2026-11-15 makes no request for it and writes no row (its D+1 session, Monday 2026-11-16, has not closed), the run on Sunday 2026-11-22 requests it and writes its reaction (first pass, 9 calendar days after the report), the run on Sunday 2026-11-29 makes no request for it (Thanksgiving puts its tenth session on Monday 2026-11-30), and the run on Sunday 2026-12-06 requests it and sets its d_plus_10_close (on main the weekly scope reads [today, today + 7] and the report is never in it)"
  - "tests/gcp/test_price_fetch_universe.py::test_failed_fetch_is_retried_next_sunday passes: a run whose vendor fails for NVDA on its first pass and for AMD on its second pass exits non-zero, writes no NVDA row and leaves AMD's d_plus_10_close NULL; the run of the next Sunday, with a working vendor, requests both, writes NVDA's reaction and sets AMD's d_plus_10_close; the same retry with AMD reported 61 days before the run makes no request for AMD and logs AMD as past the 60-day bound"
  - "tests/gcp/test_fetch_earnings_history.py::test_weekly_run_refreshes_last_weeks_reporters passes: with earnings_history holding only NVDA's previous quarter and earnings_calendar showing NVDA reported 3 days before a Sunday run, a weekly-scope run makes one EARNINGS request for NVDA and upserts its new quarter, and compute_earnings_reactions then run over the same test database gives NVDA its first-pass reaction (on main the weekly window starts today and NVDA is skipped)"
  - "tests/gcp/test_fetch_top_movers_intraday.py::test_runs_keep_only_the_latest_day passes: fetch_top_movers.main() over a stubbed vendor and a test database holding yesterday's top_movers_daily rows writes today's list and leaves no row of an earlier snapshot_date, in one transaction (a failure after the upsert leaves yesterday's rows in place); main(['--intraday-snapshot']) appends today's hourly snapshot and leaves no top_movers_intraday row of an earlier snapshot_date; an empty vendor answer writes and deletes nothing (on main both tables keep every earlier day)"
  - "tests/scripts/test_backfill_watchlist_data.py::test_untracked_ticker_is_refused passes: scripts.backfill_watchlist_data.main() with --tickers NVDA, over a stubbed watchlist holding IWM, QQQ and SPY, exits 2, logs a line holding UNTRACKED and NVDA, and makes no vendor request, no subprocess call, no freshness read and no database write; with --tickers SPY it proceeds; a failed read of the universe raises; scripts.deep_backfill_ticker.main() with NVDA, and with no argument (its default list MSFT, META, MRVL, HIMS, CRCL), exits 2 before any vendor request or write (on main the first upserts NVDA's daily history into market_data_daily and the second does the same for its default list)"
  - "tests/scripts/test_backfill_watchlist_data.py::test_fetcher_subprocess_contract passes: with _run stubbed to record its argument lists, scripts.backfill_watchlist_data.backfill_intraday('SPY') builds only command lines that gcp.fetchers.fetch_market_data.build_parser().parse_args accepts after the module name, none holding --earnings-window-days; the case fails when the driver passes an option the fetcher's parser does not define (on main the driver passes --earnings-window-days 0 to every call)"
  - "tests/gcp/test_price_fetch_universe.py::test_every_price_request_is_listed passes: walking every *.py under gcp/ and scripts/ with ast, the files holding a dict literal whose 'function' value is the constant TIME_SERIES_INTRADAY, TIME_SERIES_DAILY, TIME_SERIES_DAILY_ADJUSTED or GLOBAL_QUOTE are exactly gcp/backfill_ticker.py, gcp/fetchers/compute_earnings_reactions.py, gcp/fetchers/fetch_alphavantage_intraday.py, gcp/fetchers/fetch_market_data.py, gcp/migrate_to_gcp.py, gcp/signal_monitor.py, scripts/analysis/strat_combo_miner.py, scripts/backfill_watchlist_data.py, scripts/deep_backfill_ticker.py, scripts/fetch_alphavantage_intraday.py and scripts/fetch_market_data.py; each file that writes to the database is covered by a refusal test above, gcp/fetchers/compute_earnings_reactions.py by test_reactions_fetch_without_storing (it fetches the week's reporters and stores no bar), and gcp/signal_monitor.py and the three scripts that write no database row (scripts/analysis/strat_combo_miner.py, scripts/fetch_alphavantage_intraday.py, scripts/fetch_market_data.py: local files only) are each named with that reason; the guard's own cases show that a new file under either directory holding such a request fails it"
  - "tests/gcp/test_price_fetch_universe.py::test_truncate_file_names_only_the_default_partition passes: gcp/queries/truncate_intraday_untracked.sql is one DO block that sets lock_timeout to 5s locally and truncates market_data_intraday_other and no other relation, and gcp/queries/drop_adjusted_close.sql sets the same lock_timeout and drops only market_data_daily.adjusted_close (on main neither file exists)"
  - "make test passes on the PR head; the cases changed in tests/gcp that pinned the removed earnings augmentation of fetch_market_data and the removed earnings targets of _backfill_targets are listed in the PR body each with the line it pinned; gcp/deploy.sh, gcp/schema.sql, platform/api and docs/product/01-PRODUCT-REQUIREMENTS.md are not in the PR's diff"
  - "The PR body gives, read-only through scripts/db_query_cr.sh on the day the PR opens and each pasted with its execution id, the counts of the Close-out tables (the active default watchlist, user_watchlists and watched_tickers rows; the market_data_daily rows outside the keep list by year; the untracked rows of historical_signals, signal_metrics, premarket_analysis, premarket_analysis_history, strat_levels, ticker_level_params, insight_reports, insight_reports_history, earnings_reactions, earnings_options_strategy_winners, top_movers_daily and top_movers_intraday) and the latest object of gs://adept-mountain-474619-d4-trading-data/sql-dumps/ with its size and time"
  - "02-FEATURE-CATALOG FEAT-DATA-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the implementation-source notes of 03-SITE-TRACEABILITY.md hold a (FEAT-DATA-001, component) row for each of the twelve declared components that begins with the current source hash (a row an earlier change left is extended: the new hash and this change's prose first, then 'Earlier:' and the earlier prose unchanged), docs/review-evidence/site-source-snapshot.json is regenerated and scripts/maintenance/doc_source_snapshot.py verify accepts it, the generated inventory blocks are re-rendered with scripts/maintenance/doc_inventory.py and tests/scripts/test_check_generated_docs.py passes, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing that origin/main does not, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: draft
supersedes: docs/superpowers/specs/2026-11-16-feat-data-001-spy-qqq-iwm-only.md
---

# Prices for SPY, QQQ and IWM only: fetch from the watchlist, delete the rest (r2)

## Changes from the superseded spec

This revision (r2, 2026-11-16) supersedes `docs/superpowers/specs/2026-11-16-feat-data-001-spy-qqq-iwm-only.md`, merged as a draft with PR #1977. It carries that text forward whole, with these changes and no other (items 1 to 6 are the six findings of #1980, item 7 the owner's decision on the sector ETFs):

1. **A failed second-pass fetch is retried** (#1980 item 1). The second pass selects every report whose stored ten-day outcome (`d_plus_10_close`) is still NULL once its tenth NYSE session has closed, within 60 days of the report, not only the reports whose tenth session closed in the 7 days before the run. Design 8, Capacity, Risks, `test_reactions_fetch_without_storing` and the new `test_failed_fetch_is_retried_next_sunday`.
2. **A Friday report gets its reaction** (#1980 item 2). The first pass takes every report with no stored reaction once its reaction session (D+1) has closed, within the same 60 days, not only the reports of the last 7 calendar days. Design 8 and the new `test_friday_report_gets_both_passes`.
3. **The hand-run backfill scripts are refused too** (#1980 item 3). `scripts/backfill_watchlist_data.py` passes `require_tracked` before any request or write, and the price-request guard walks `scripts/` as well as `gcp/`. Walking `scripts/` also lists `scripts/deep_backfill_ticker.py`, which upserts `market_data_daily` for any ticker it is given (read); it gets the same refusal. Problem 1, Design 7a, Design 9, Split, `test_untracked_ticker_is_refused` and `test_every_price_request_is_listed` (renamed from `test_every_price_request_under_gcp_is_listed`).
4. **The Sunday consumers of the reactions run after the reaction run** (#1980 item 4). Spec C sequences `earnings-long-watchlist` (19:45), `refresh-earnings-views-weekly` (20:00) and `earnings-sweep-sunday` (20:30), and also `premarket-brief-sunday` (21:00), whose comment says it relies on that evening's reactions (found while checking this item), after the reaction run completes. Design 8, Split (spec C) and Close-out steps 1 and 6.
5. **The DEFAULT intraday partition stays** (#1980 item 5). Decision 14 is now "keep DEFAULT", with no drop alternative, and spec B does not drop it. Approaches 5, Decision 14 and Split (spec B).
6. **The backfill driver's call to the nightly fetcher is updated with the option's removal** (#1980 item 6). Design 2, Design 7a and `test_fetcher_subprocess_contract`.
7. **Sector ETFs: decided by the owner** (2026-11-16, "Fetch them live only"). Decision 2 is decided, its "store nightly" alternative is removed, and every "if Decision 2 is struck" or "if Decision 2 stands" figure and branch goes. Spec D's live sector route stays a prerequisite of Close-out step 1. The owner's requirement (item 7), Problem 3, Capacity, Decision 2 and Close-out.
8. **The companion spec is cited by its path.** It merged as a draft with #1978 after the superseded spec was written; the two places that named its branch now name `docs/superpowers/specs/2026-11-16-feat-data-001-no-adjusted-prices.md`. Problem 4 and Design 8.

The six findings of #1980 were raised by Codex's second code review of #1977 on commit 5277a9f0 after #1977's review cap was reached. Each was checked again for this revision against `origin/main` 4155a10f; the file and line of each is cited below "on main 4155a10f". No file under `gcp/`, `lib/`, `scripts/` or `platform/` changed between a34bbd40, the commit the superseded spec cites, and 4155a10f (run: `git diff --stat a34bbd40 4155a10f -- gcp lib scripts platform` is empty), so every other citation of a34bbd40 holds at 4155a10f.

This spec is a draft until the owner approves it; then the superseded spec is marked superseded on its own `docs/` branch. No code is written under either before this one is approved.

## The owner's requirement

T, 2026-11-16, in this order:

1. "Yeah, I don't want anything using the adjusted anything. Nothing should be adjusted. It should be as it was traded."
2. "Also delete any ticker bars/data outside of IWM/QQQ/SPY." Asked to scope it, T chose:
   - Delete scope: "All price data: 1-minute bars (about 270M rows, 68 GB), daily bars (about 1M+ rows over 2,650 tickers), and everything built from them for those tickers: features, levels, signals, flow/GEX, premarket fields. Keeps earnings calendars, option chains, user watchlists and journal entries."
   - Fetching: "Yes, SPY/QQQ/IWM only: limit every price fetch to SPY, QQQ and IWM in the same change, so nothing refills. Users' watchlists and earnings pages for other tickers would stop updating."
3. "Delete them from the watch list that does the fetch vs just deleting from tables."
4. "For earnings the weekly calls are fine, the issue is that we don't need to store the data to refresh it daily." Asked whether the weekly run should still produce earnings reactions, fetching each reporter's as-traded daily prices only while it runs and storing just the reaction, not the bars, T answered: "I say yes".
5. On the recommendations of the first draft (2026-11-16): "VIX, VIX3M, VVIX ... Keeping is fine here"; on the sector ETFs, "what etfs are these and does it accrue daily?"; on top movers, "these should have a table that refreshes daily, top movers change over time. Can you see how you pull in alpha vantage top movers? Is there a date filter? If so then you can have this table be an overwrite/update vs append."; on refusing a personal watchlist add and showing an unavailable state, "Why not figure out how to do this vs unavailable?"
6. Asked whether this was only a cleanup of old data, and offered three choices (clean up and stop fetching other tickers; clean up only and keep fetching them as traded; clean up and store history for every ticker on a personal watchlist), T chose the first: "1 and in solyra the ability for an admin to adjust the default watch lists" (Decision 16).
7. Asked to choose between fetching the 11 sector ETFs live for the dashboard card and keeping their daily closes stored nightly, T answered on 2026-11-16: "Fetch them live only" (Decision 2).

The owner's change of plan: an earlier draft of this spec measured every other ticker's stored 1-minute months for an adjusted basis and refetched them as traded. Item 2 replaces that. No other ticker is measured or refetched; its price data is deleted. SPY, QQQ and IWM are already as traded (every month refetched with `adjusted=false`; scan `freshness-watchdog-dq7hh`: 429 months, 0 unproven rows; records on #1943 and #1955) and are not touched here.

## Scope

- **Code (the implementation PR):** every job that fetches prices takes its tickers from the active rows of the default watchlist, and refuses any other ticker it is asked for with exit code 2 before any vendor request. One shared reader in `gcp/fetchers/_watchlist.py`; no ticker list is written into code.
- **Data (Close-out, each step its own owner's go):** a fresh, verified restore point; the watchlist check; then deletion of other tickers' 1-minute bars, daily bars and the tables built from them; then `market_data_daily.adjusted_close` cleared and dropped once the companion code spec is deployed; then the legacy GCS parquets.
- Code references are to `main` a34bbd40 (2026-11-16), unchanged at 4155a10f for every file cited; the lines added for #1980 are cited "on main 4155a10f". Every production number was read on 2026-11-16 without `--commit`, with its execution name beside it. "Read" means read from the code or a listing; "run" means executed; anything else says "not checked".

## Problem

### 1. The watchlist already holds only SPY, QQQ and IWM. Other tickers come from elsewhere.

Run, `db-query-89ccp`:

| Table | Rows | Active rows |
|---|---|---|
| `watchlists` (owner `default`) | 18 | 3: IWM, QQQ, SPY. The other 15 (AMD, ANET, ARM, ASTX, AVGO, CSCO, MCK, MRVL, MSFT, MU, NVDA, QCOM, SPX, TSM, TXN) have `removed_at` set |
| `user_watchlists` (per user, FEAT-INSIGHT-001) | 0 | 0 |
| `watched_tickers` | 0 | |
| `watchlist_history` | 33 | |

So T's mechanism, removing tickers from the watchlist, is already done for the default list. The other tickers still arrive because five fetch paths do not read the watchlist, or read it and add more:

| Job (Cloud Run) | Scheduler, America/New_York | Where its tickers come from (read) | Measured size | What removes other tickers |
|---|---|---|---|---|
| `fetch-market-data` | `fetch-market-data-daily`, `0 23 * * 1-5` | `TICKERS = ['IWM', 'SPY', 'QQQ', 'SPX'] + SECTOR_ETFS` (11 SPDR ETFs), `gcp/fetchers/fetch_market_data.py:42-43`; plus the default watchlist, `:1649-1654`; plus every optionable reporter of the next 7 days, `:1656-1673` (`EARNINGS_WINDOW_DAYS=7`, `gcp/deploy.sh:2155`). Two vendor calls per ticker, 1-minute and daily (`process_ticker`, `:657`, `:671`) | 120 to 173 tickers a night (`fetch-market-data-vdvbl` 120, `-9h488` 132, `-nhfz7` 173, `-ls4ls` 146, `-qr6w4` 166; run: their logs) | Code: the universe is the watchlist; the hardcoded list and the earnings augmentation go (Design 2) |
| `fetch-earnings-history` | `daily-earnings-refresh-history` `15 19 * * 1-5`; `weekly-earnings-refresh-history` `15 19 * * 0` | after its EPS fetch it calls `fetch_market_data._run_backfill()` (`gcp/fetchers/fetch_earnings_history.py:554-561`), whose targets with `BACKFILL_ALL_HISTORY=true` (`gcp/deploy.sh:2982`) are every `earnings_history` ticker plus every `market_data_daily` ticker (`_backfill_targets`, `fetch_market_data.py:857-944`) | "Eligible targets: 2664", "714953 bars upserted across 2643 tickers", 65 minutes of a 70-minute run (`fetch-earnings-history-nsmx7`, run: its log) | Code: the targets are the watchlist (Design 3) |
| `fetch-premarket-refresh` | `premarket-refresh-daily` `20 8 * * 1-5` | `resolve_universe`, `gcp/fetchers/fetch_premarket_refresh.py:53-133`: the watchlist, then today's optionable reporters, then yesterday's postmarket reporters, capped at 50 | 50 tickers (`fetch-premarket-refresh-c47zg`, run: its log) | Code: the universe is the watchlist (Design 5) |
| `intraday-bulk-backfill` | none; run by hand | `--symbols-file /app/gcp/fetchers/symbol_lists/earnings_universe.txt` (`gcp/deploy.sh:3763`), a list in the image | not run recently (not checked) | Code: `fetch_alphavantage_intraday` refuses a listed ticker that is not on the watchlist (Design 6) |
| `backfill-ticker` | none; run by hand, one ticker per execution | `BACKFILL_TICKER` env (`gcp/backfill_ticker.py:584`) | | Code: refused unless on the watchlist (Design 7) |

Paths that already follow the watchlist and need no change (read):

| Job | Scheduler | Source |
|---|---|---|
| `fetch-alphavantage-intraday` | `av-intraday-nightly` `0 21 * * 1-6` (`--symbol=ALL --force`); `av-intraday-monthly` `0 21 1 * *` | `resolve_all_symbols` (`fetch_alphavantage_intraday.py:57-64`): `MarketConfig.tickers` (`lib/config.py:181`), `DEFAULT_TICKERS` (`gcp/insight_pipeline_job.py:81`), both SPY, QQQ and IWM, plus the default watchlist. Today the three tickers. Design 6 makes `ALL` the watchlist itself |
| `signal-monitor` | `signal-monitor-daily` `25 9 * * 1-5`, `orb-15m-alert` `45 9 * * 1-5`, `orb-30m-alert` `0 10 * * 1-5` | `load_watchlist(surface="signals")` (`gcp/signal_monitor.py:307`); live bars, stores no bar |
| `historical-signals-watchlist` | `historical-signals-watchlist-daily` `0 1 * * 2-6` | `load_watchlist()` (`scripts/run_historical_signals.py:141`); builds from stored bars, fetches none |
| `strat-engine`, `p2-build-gamma-levels`, `phase6-playbook` | `strat-engine-daily`, `strat-enrich-daily`, `gamma-levels-daily`, `phase6-playbook-daily` | `TICKERS_DEFAULT = ["SPY", "IWM", "QQQ"]` (`strat_data_builder.py:85`, `p2_build_gamma_levels.py:77`); build from stored bars |
| `insight-pipeline`, `auto-refresh-top-n` | `insight-pipeline-daily`, `auto-refresh-top-n` | no price request in either module (searched for the price functions); the ranker keeps only watchlist tickers unless `expand_universe` (`lib/agents/ranker/candidates.py:308-310`) |
| `backfill-daily-indicators` | `backfill-indicators-daily`, `backfill-indicators-weekly` | computes from `market_data_daily`; no vendor request (searched) |
| `fetch-watched-tickers` | none on `main`; `watched-tickers-nightly` `45 23 * * 1-5` is in open PR #1963 | `watched_tickers` joined to active `user_watchlists`, minus `fetch_market_data.TICKERS` (`gcp/fetchers/fetch_watched_tickers.py:47-50`, `:415`); both tables are empty today. Design 4 |

Paths that store other tickers' prices and read no list of ours: `fetch-top-movers` (`top-movers-daily` `15 16 * * 1-5`, `top-movers-intraday-hourly` `30 9-15 * * 1-5`, `top-movers-intraday-close` `5 16 * * 1-5`) stores the vendor's `TOP_GAINERS_LOSERS` list with price, change and volume (`gcp/fetchers/fetch_top_movers.py:68`, `:95-96`, `:260`, `:290`). The vendor call takes no date: it always returns the current session's list (read: the function's only parameter is `entitlement`, in the vendor's tool schema). Both tables keep every earlier day (`top_movers_daily` keyed on `snapshot_date, ticker, category`, `top_movers_intraday` on `snapshot_ts, ticker`, `gcp/schema.sql:1018-1056`), while every reader reads only the latest day: the ranker (`lib/agents/ranker/candidates.py:168-175`, `signals.py:493-501`, `snapshot_date = CURRENT_DATE`) and the most-active bar (`platform/api/main.py:1567-1574`, the latest `snapshot_date`). Decision 8.

Two scripts run by hand write other tickers' daily bars to the database and read no list of ours (on main 4155a10f, read):

- `scripts/backfill_watchlist_data.py`, which `./gcp/deploy.sh backfill [args]` runs locally (`gcp/deploy.sh:5094-5107`, `:5399`). Its default list is `load_watchlist()` (`:60-71`), but `--tickers` overrides it with any list (`:355-358`). For each ticker `backfill_daily()` requests `TIME_SERIES_DAILY_ADJUSTED` itself (`:200-211`) and upserts every bar into `market_data_daily` (`:236`), and `backfill_intraday()` runs `gcp.fetchers.fetch_market_data --tickers <T> --date <D> --earnings-window-days 0` as a subprocess for five sessions (`:262-268`). So `./gcp/deploy.sh backfill --tickers NVDA` stores NVDA's daily history. (The companion spec, `docs/superpowers/specs/2026-11-16-feat-data-001-no-adjusted-prices.md`, #1978, switches the same request to `TIME_SERIES_DAILY`.)
- `scripts/deep_backfill_ticker.py` requests `TIME_SERIES_DAILY_ADJUSTED` with `outputsize=full` (`:42-50`) and upserts into `market_data_daily` (`:102`) for each ticker on its command line, or for MSFT, META, MRVL, HIMS and CRCL when given none (`:107-110`).

Three other scripts hold a price request and write local files only (read: no database write in them): `scripts/fetch_market_data.py` and `scripts/fetch_alphavantage_intraday.py` (parquet files), and `scripts/analysis/strat_combo_miner.py` (an analysis run). Design 7a and Design 9.

Out of scope as not price data: the option chain fetchers (`av-options-*`, the earnings options fetch), news, SEC filings, insider transactions and the EPS fetch of `fetch-earnings-history`. They keep running for the tickers they cover today.

### 2. What is stored for other tickers

Run, `db-query-f9bxp` (sizes, `pg_class` estimates), `db-query-89ccp` (partition bounds), `db-query-5bhbp` (distinct tickers by loose index scan), `db-query-szdbn` (exact counts), `db-query-bxrxg` and `db-query-2fnc5` (daily table), `db-query-mg7vx` (detail):

| Table | Untracked rows | Tickers | Size of the table | Kind |
|---|---|---|---|---|
| `market_data_intraday_other` | about 270,472,992 (estimate) | 2,629 (2,632 in the table less SPY, QQQ, IWM; `db-query-pwjql`) | 72,721,956,864 bytes | 1-minute bars. The DEFAULT partition (`gcp/schema.sql:164-165`, bound `DEFAULT`); it holds 0 SPY, QQQ, IWM or SPX rows (`db-query-mg7vx`) |
| `market_data_daily` | 5,799,582 (5,762,730 outside the keep candidates) | 2,661 | 4,173,815,808 bytes; 5,807,535 rows | daily bars |
| `historical_signals` | 211,735 | 13 (AMD 25,134, NVDA 27,067, ASTX 24,035, ARM 23,633, AVGO 17,522, MU 14,828, MRVL 13,626, TSM 12,491, MCK 12,045, QCOM 11,918, ANET 10,329, CSCO 9,866, TXN 9,241) | 4,223,180,800 bytes | signals |
| `signal_metrics` | 211,735 | 13 | 308,232,192 bytes | signal outcomes |
| `earnings_reactions` | 67,116 | 2,030 | | kept; new reactions computed each Sunday from prices fetched for the run and not stored (Decision 5) |
| `earnings_event_outcomes`, `earnings_ticker_lean` (materialized views) | 67,101; 2,030 | | | built from `earnings_reactions` (the view depends on it, `db-query-mg7vx`) |
| `earnings_options_strategy_winners` | 2,520 | 202 | | kept (Decision 5) |
| `earnings_upcoming_with_history` | 89,670 | 9,925 | | calendar rows decorated with reaction statistics; rebuilt each weekday by `refresh-earnings-views` |
| `top_movers_daily`; `top_movers_intraday` | 8,757; 14,356 | 1,828; 456 | | vendor movers with prices; kept as today's list only, overwritten each run (Decision 8) |
| `insight_reports`; `insight_reports_history` | 525; 525 | 163 | | AI reports built from prices and news (Decision 7) |
| `insight_runs` | 565 | 164 | | run log and cost (kept) |
| `strat_levels` | 457 | 7 (AMD 101, ARM 106, ASTX 13, AVGO 43, CARS 32, NVDA 38, SPX 124) | | levels |
| `ticker_level_params` | 92 | 4 (ANET, AVGO, QCOM, TXN, 23 each) | | level parameters |
| `premarket_analysis`; `premarket_analysis_history` | 11; 16 | 6; 7 (SPX 4 in the history) | | premarket fields |
| `archive_yahoo_market_data_intraday` | 12,868 SPX, plus 38,603 SPY, QQQ and IWM | 4 | 6,062,080 bytes | Yahoo era, 2026-02-23 to 2026-04-09 (Decision 11) |

No untracked rows (run, same executions): the six `strat_features_*` tables, the six `strat_features_levels_*` tables, `intraday_flow_15m`, `intraday_gex_15m`, `realtime_gex_15m`, `gamma_levels_eod`, `gamma_events`, `options_daily_features`, `etf_options_daily_greeks`, `daily_vex`, `playbook_cards`, `magnitude_per_bar_predictions`, `magnitude_walk_forward_results`, the three `*_30m_predictions` tables, `backtest_trades`, `backtest_walk_forward_folds`, `backtest_sweeps`, `walk_forward_results`, `regime_combo_results`, `signal_alerts` (3,601, all SPY, QQQ, IWM), `trades` (3,559, all three), `journal_entries` (2, both), `exit_config_overrides`, `ticker_calibration`, `bar_recompute_ledger`, `market_data_indicators` (23,922, all three). `indicator_correlation` holds 277 rows under `POOLED`, which is not a ticker: kept. `market_data_cross_asset`, `ticker_info`, `strat_combo_results`, `user_style_results`, `playbook_cards_staging` and the three other `archive_yahoo_*` tables are empty.

Kept by T's scope, untracked rows and all: `earnings_calendar` (81,852, 11,342 tickers), `earnings_history` (140,504, 2,034), `etf_options_snapshots`, `earnings_options_snapshots`, `news_sentiment` (7,196 other tickers), `sec_filings` (6,342), `insider_transactions`, the three watchlist tables, `journal_entries`, `trades`.

No foreign key references `market_data_daily`, `market_data_intraday`, its DEFAULT partition, `historical_signals`, `signal_metrics` or `earnings_reactions` (`db-query-mg7vx`).

### 3. Symbols other than SPY, QQQ and IWM that their computations read

Read, with rows from `db-query-bxrxg` and `db-query-mg7vx`:

| Symbol | Daily rows | Read by | Recommendation |
|---|---|---|---|
| `^VIX` | 2,988, 2015-01-02 to 2026-11-13 (NULL and `yahoo`) | `vix_close` and `vix_tercile` of every `strat_features_*` table (`gcp/research/strat_engine/strat_data_builder.py:227`), `strat_data_pipeline.py:128`, `p2_outcomes_grid.py:151`, `p7_build_multi_tf_features.py:114`, `lib/features/experimental/cross_asset.py:68`. Written by the Yahoo fetch in `fetch_market_data.py:696-725`, `:1712-1716` | keep, and keep its fetch (Decision 3) |
| `^VIX3M`, `^VVIX` | 2,864 and 2,856, to 2026-05-22; no writer since | `lib/features/experimental/cross_asset.py:69-70` only | keep (Decision 3) |
| 11 SPDR sector ETFs (XLB, XLC, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY) | 28,144 | `GET /api/market/sectors` (`platform/api/main.py:1439-1490`), the dashboard's sector card; no SPY, QQQ or IWM computation | delete; the card fetches them live (Decision 2, decided by the owner) |
| `SPX` | 0 daily rows; the `market_data_intraday_spx` partition is empty; 124 `strat_levels` and 4 `premarket_analysis_history` rows | the SPX option chain and Greeks, which take spot from the chain (`scripts/audit_data_freshness.py:115-121`), not from a daily row | delete its price-derived rows; keep its options |

### 4. Adjusted data that stays after the deletes

- `market_data_daily.adjusted_close` is non-NULL on 7,948 SPY, QQQ and IWM rows, 144 `^VIX` rows and 1,331 sector ETF rows (`db-query-zrwbj`). Across the whole table today: 34,847 rows (`db-query-bxrxg`). The companion code spec (`docs/superpowers/specs/2026-11-16-feat-data-001-no-adjusted-prices.md`, merged as a draft with #1978) removes every read and write of it.
- `archive_yahoo_market_data_intraday`: written in the Yahoo era, whose fetch used `auto_adjust=True` (read: commit e9ff9db2, `gcp/fetchers/fetch_market_data.py`). Read by nothing but `scripts/archive_yahoo_data.py`, the script that filled it (searched `gcp/`, `lib/`, `scripts/`, `platform/` and solyra `main` 80c82c2).
- `market_data_indicators`: 23,922 rows, SPY, QQQ and IWM only, AlphaVantage's own ADX, MFI, ADOSC, AROON, ROC and BBANDS (`gcp/fetchers/fetch_av_indicators.py:17-18`, "NOT scheduled"). Read only by the magnitude engine's phase-2 research path (`gcp/research/magnitude_engine/mag_dataset.py:395-398`); the daily inference does not read it (searched `mag_inference.py`). Whether AlphaVantage computes these on an adjusted series: not checked.
- Daily rows built from 1-minute bars (`data_source` `alphavantage_1min` or `yfinance_1min`): 0 rows. Every `data_source` value in the table: NULL 4,770,116; `av_daily_backfill` 1,025,574; `alphavantage_daily` 10,015; `alphavantage` 1,686 (4 tickers, written by `backfill_ticker.py:261`); `yahoo` 144 (`db-query-bxrxg`). Nothing to recompute. The writer that would stamp `alphavantage_1min` (`fetch_market_data.py:292-299`) is the companion spec's.

### 5. GCS `raw/`

Run, `gcloud storage du -s` and `ls` on 2026-11-16:

| Prefix | Bytes | Readers (searched `lib/ gcp/ scripts/ platform/`) |
|---|---|---|
| `raw/` in all | 12,669,779,073 | |
| `raw/data/` | 8,188,897,170 | the API's backtest CSVs (`platform/api/routers/backtest.py:19`) and its local-dev parquet reads (`platform/api/main.py:854-873`, `:1177`, `:1770`) |
| `raw/reports/` | 407,780 | the Playbook and Reports pages (`platform/api/routers/playbook.py:121`, `:400-481`) |
| `raw/signals/` | 94,935,104 | not found |
| `raw/spy/`, `raw/qqq/`, `raw/iwm/` | 623,229,270; 899,714,305; 672,597,398 | not found; yfinance-era parquets with `Adj Close` |
| `raw/spx/` | 392,818,243 | not found |
| 913 other per-ticker folders (`raw/aal/` to the end, each with `minute/` parquets) | 1,797,179,803 | `scripts/analysis/intraday_indicator_correlation.py:27` describes the layout; it is an analysis script run by hand, not a job |

CLAUDE.md "What is NOT backed up" sets three conditions before `raw/` is deleted: the weekly dump is live (it is: five dumps listed below), one dump has been verified to gunzip cleanly (not checked: Close-out step 2 does it), and nothing reads the prefix. The third fails for `raw/data/` and `raw/reports/`, so the whole prefix is never deleted. Only folders with no reader are (Decision 12). The bucket also deletes `raw/` objects 730 days after creation (`gcp/deploy.sh:3344-3367`, read).

### 6. Restore point

The latest weekly dump is `gs://adept-mountain-474619-d4-trading-data/sql-dumps/trading-20261115-090034.sql.gz`, 15,364,642,308 bytes, finished 2026-11-15 09:30:19Z (run: `gcloud storage ls -l`). It predates today. Dumps under `sql-dumps/` are deleted after 30 days (`gcp/deploy.sh:3337-3367`, read). The database is 182,307,282,279 bytes (`db-query-gvkbh`) on a 203 GB PD-SSD disk with auto-resize on, tier db-g1-small (run: `gcloud sql instances describe trading-db`).

## Non-goals

- No production write, deploy or job run from the implementation PR. Every production step is in Close-out and waits for the owner's own yes for that step.
- No hardcoded SPY, QQQ, IWM list in fetch code. The default watchlist is the switch: adding a row there is how a ticker is fetched again.
- No change to `gcp/deploy.sh` (FEAT-DEPLOY-001), `gcp/schema.sql`, `platform/api` or solyra. Each needed change there is a separate spec, listed under "Split and separate specs".
- No change to any SPY, QQQ or IWM row, to the replace, basis and recompute tools, or to option chains, earnings calendars, EPS history, news, filings, insider data, watchlists, journal entries or trades.
- No measurement or refetch of other tickers' stored bars (the earlier plan, replaced by the owner).

## Approaches considered

1. **Every price fetch reads the default watchlist and refuses other tickers (chosen).** It is T's mechanism ("the watch list that does the fetch"), it puts no universe in code, and it closes the hand-run paths as well as the scheduled ones.
2. **One SPY, QQQ, IWM constant in `lib/`.** T's last instruction rules it out while a watchlist exists, and every job has one to read.
3. **Change the schedules and job flags only** (drop `EARNINGS_WINDOW_DAYS` and `BACKFILL_ALL_HISTORY`, pause the movers). It leaves the hardcoded `TICKERS`, the premarket reporters and the two hand-run jobs fetching anything, a paused scheduler is flagged as drift by `audit-infra-drift`, and the file belongs to FEAT-DEPLOY-001. Its clean-up is still worth a separate spec.
4. **DELETE the 270 million intraday rows.** Hours of WAL and a vacuum of a 72.7 GB heap, against a TRUNCATE that drops the files. Not taken.
5. **Detach and drop the DEFAULT partition.** A later write of an untracked ticker would then fail at the database. It needs an exclusive lock on the parent (a DEFAULT partition cannot be detached concurrently) and a `gcp/schema.sql` change. Not taken (Decision 14): with the admin editor of Decision 16 a newly added ticker's 1-minute bars have no partition but DEFAULT, since `gcp/schema.sql:156-165` creates only the SPY, IWM, QQQ and SPX partitions and no add path creates one (on main 4155a10f, read: no other `PARTITION OF market_data_intraday` outside `gcp/schema.sql` and a test fixture).
6. **Measure every ticker-month's basis, then refetch the adjusted ones.** The earlier plan; replaced by the owner.

## Design

### 1. The shared reader (`gcp/fetchers/_watchlist.py`)

- `DEFAULT_WATCHLIST_SQL`: `SELECT ticker FROM watchlists WHERE user_id = 'default' AND removed_at IS NULL ORDER BY added_at, ticker`. `gcp.calibrate_level_params.WATCHLIST_SQL` becomes this constant (one text, not two). The three seed rows share one `added_at` (`db-query-89ccp`), so `ticker` breaks the tie.
- `price_fetch_universe(query=None) -> tuple[str, ...]`: one read through `gcp.database.query_to_dataframe_strict` with `timeout_s=120`, upper-cased and deduplicated in order. A failed read raises. An empty result raises `EmptyFetchUniverse`: a price job with nothing to fetch is a misconfiguration, as the signal monitor already treats it (`gcp/signal_monitor.py:307-315`). It does not use `load_watchlist`, which turns a failed read into the `INSIGHT_TICKERS` env list or `[]` (`_watchlist.py:411-470`).
- `UntrackedTickers(ValueError)` and `require_tracked(tickers, universe, job)`: raises naming every requested ticker not in `universe`, in request order, and the job.
- Each entry point catches `UntrackedTickers` in its `main`, logs `UNTRACKED job=<job> tickers=<list> watchlist=<list>`, and exits 2. Exit 2 is a configuration error, apart from 1 (a run that failed). It happens before any vendor request and any write.
- Adding a ticker back is one row in the default watchlist, through the platform or `BACKFILL_ADD_TO_WATCHLIST=true` (Design 7). The `watchlists` triggers record it in `watchlist_history` (`gcp/schema.sql:2894-3162`, read).

### 2. `fetch-market-data` (nightly)

- `--tickers ALL` means `price_fetch_universe()`. `TICKERS`, `SECTOR_ETFS` and `AV_SYMBOL_MAP`'s entries for them go, and so does the earnings augmentation with its flags (`--earnings-window-days`, `--max-earnings-tickers`, `--require-options`) and `_earnings_tickers_in_window`. A scheduler that still passed one of those flags would fail at argument parsing; none does (`gcp/deploy.sh:4622`, read). One caller does pass one: `scripts/backfill_watchlist_data.py` runs the fetcher with `--earnings-window-days 0` (`:262-268`, on main 4155a10f), so each of its calls would exit at argument parsing. That caller drops the option in the same change (Design 7a), and `test_fetcher_subprocess_contract` parses the driver's command lines with the fetcher's own `build_parser()` (`gcp/fetchers/fetch_market_data.py:1241`, on main 4155a10f). No other caller passes `--earnings-window-days`, `--max-earnings-tickers` or `--require-options` to this module (searched `gcp/`, `lib/`, `scripts/`, `platform/` and `.github/`; the options of the same names in `fetch_news_sentiment.py` and `fetch_sec_filings.py` and the `--require-options` of `fetch_earnings_history.py` are their own and unchanged). `EARNINGS_WINDOW_DAYS`, `MAX_EARNINGS_TICKERS` and `REQUIRE_OPTIONS` in the job's environment are then unread; spec C removes them.
- `--tickers A B` passes through `require_tracked`.
- The `^VIX` fetch from Yahoo stays (Decision 3).
- `--recompute-premarket` and `--revert-run` read stored bars only and are unchanged.

### 3. `_run_backfill` (the chain behind `fetch-earnings-history`, and `fetch-watched-tickers`)

- `_backfill_targets()` returns the bar count and last date of each ticker of `price_fetch_universe()`. It no longer reads `earnings_history`, the `market_data_daily` universe or `BACKFILL_ALL_HISTORY`, and it reads through the strict reader (today `query_to_dataframe`, which returns an empty frame on a database error, `fetch_market_data.py:939`).
- Explicit `tickers` pass through `require_tracked`, so a caller with an outside list raises before any vendor request.
- `fetch_earnings_history` keeps its EPS fetch and its chained call. That call wraps a failure as non-fatal (`fetch_earnings_history.py:554-561`, read); with targets taken from the watchlist it never meets `UntrackedTickers`.

### 4. `fetch-watched-tickers`

- Its set excludes `price_fetch_universe()` where it excluded `fetch_market_data.TICKERS` (`fetch_watched_tickers.py:415`, `:425`). Every ticker left is untracked, and its call into `_run_backfill` raises: the run fails loudly and fetches nothing for it.
- Both of its tables are empty today, so the job does nothing until a user adds a ticker. Decision 9 covers the per-user product and #1963.

### 5. `fetch-premarket-refresh`

- `resolve_universe` returns `price_fetch_universe()`, capped as today. The `--tickers` override, which skips `resolve_universe` (`fetch_premarket_refresh.py:423-425`, read), passes through `require_tracked` in `main()`. The two `earnings_calendar` reads go. A failed watchlist read raises, where today it is logged and skipped (`fetch_premarket_refresh.py:77-83`).

### 6. `fetch-alphavantage-intraday` (and `intraday-bulk-backfill`, which runs it)

- `resolve_all_symbols()` returns `price_fetch_universe()`. `brief_insight_watchlist_tickers` keeps its other callers' behaviour; this module stops calling it.
- `--symbol`, `--symbols-file` and every line of a `--replace-months` list pass through `require_tracked` before the first vendor request. A bulk run over `earnings_universe.txt` exits 2 at once, naming the tickers.
- `--verify-months`, `--verify-basis` and `--export-bars-from` request nothing from the vendor and are unchanged.

### 7. `backfill-ticker` and `migrate_to_gcp`, both run by hand

- `backfill_ticker.main()`: with `BACKFILL_ADD_TO_WATCHLIST=true` the watchlist row is written first (today it is the last step, `:607`, `:671`); then `require_tracked([ticker])`. A ticker not on the watchlist and not being added exits 2.
- `gcp/migrate_to_gcp.migrate_market_data_daily_av` passes its four symbols (`AV_DAILY_SYMBOLS`, `:509-514`) through `require_tracked`; SPX is refused.

### 7a. `scripts/backfill_watchlist_data.py` and `scripts/deep_backfill_ticker.py`, both run by hand

- `backfill_watchlist_data.main()`: once its ticker list is resolved, and before any freshness read, vendor request, subprocess or write, it calls `require_tracked(tickers, price_fetch_universe(), job="backfill-watchlist-data")` and exits 2 on `UntrackedTickers`, as Design 1 says. Its default list stays `load_watchlist()` through `_watchlist()` (`:60-71`), the reader `tests/gcp/test_watchlist_readers_default_owner.py:74` pins for it; the check is what keeps a `--tickers` override, or an environment fallback of that reader, from fetching an untracked ticker.
- `backfill_intraday()` stops passing `--earnings-window-days 0` (`:262-268`), since the option no longer exists (Design 2). The subprocess call is otherwise unchanged and is refused by the fetcher itself for an untracked ticker.
- `deep_backfill_ticker.main()`: the same check over its command-line tickers, or its default list, before the first request; its default list (`:109-110`) is all untracked, so a bare run exits 2.
- What `backfill_daily()` requests and stores is the companion spec's (#1978): it switches the request to `TIME_SERIES_DAILY` and drops `adjusted_close`.

### 8. `compute-earnings-reactions`: reactions without stored bars (Decision 5)

- Today it requests no vendor and rebuilds reactions from `market_data_daily` (`fetch_daily_windows_for_ticker_dates`, `compute_earnings_reactions.py:642-704`, one query per ticker over 90 calendar days before the report to 25 after; read), which the 19:15 ET earnings chain refills for about 2,660 tickers every weekday. After the daily deletes those bars are gone and are not refilled.
- After: each Sunday run selects, with one query over `earnings_history` left-joined to `earnings_reactions` on `(ticker, fiscal_date_ending)` (the reaction table's unique key, `gcp/schema.sql:866`, on main 4155a10f), the reports of known timing (BMO or AMC; `compute_reaction` returns None for any other, `compute_earnings_reactions.py:107-108`) reported in the last 60 calendar days (Eastern time) that need a pass:
  - **First pass:** every such report with no stored reaction whose reaction session has closed. The reaction session is D+1, the first NYSE session after the report's day D, for BMO as well as AMC: `compute_reaction` returns None without the D+1 bar for either timing (`:119-121`, `:139-141`, on main 4155a10f), so the code does not allow D alone for BMO. A Friday report therefore has no reaction on the Sunday after it (Monday's bar does not exist) and gets one on the next Sunday, 9 calendar days after the report, where a 7-day window would have dropped it.
  - **Second pass:** every such report whose stored `d_plus_10_close` is NULL and whose tenth NYSE session after D has closed. `d_plus_10_close` and not `sustain_10d_pct` is the test, because `sustain_at` keeps the close and nulls only the percent when the move exceeds `SUSTAIN_ANOMALY_PCT` (`:259-281`, on main 4155a10f), so a NULL close means the tenth session was never in a fetched series. A report whose second-pass fetch failed is selected again the next Sunday, and so is a first-pass failure.
  - Sessions are counted with `lib.eastern_time.sessions_between` (`lib/eastern_time.py:770`, read), the one NYSE calendar, so a holiday moves a report's pass to the next run and never skips it (a Friday 2026-11-13 report has only nine sessions after it by Sunday 2026-11-29, Thanksgiving being closed; its second pass is the run of 2026-12-06). An upcoming report has no row yet, so the run needs no look-ahead.
  - **The 60-day bound.** It keeps the first run on the new code from fetching every older report that never got a reaction, and it bounds a retry: a report still pending 60 days after it was reported is not selected again, is logged by ticker and date as past the bound, and keeps its NULL columns (no fabricated value). 60 days is about 42 sessions; with D-10 and the 14 bars before D that ATR-14 needs, the oldest report in the window reaches about 66 sessions back, inside the 100 sessions of a compact series. Reports are processed oldest first, so the reports nearest the bound go before a timeout.
  - In steady state a report is selected twice and no more: once after its D+1 session, once after its tenth session.
- For each selected ticker the run makes one `TIME_SERIES_DAILY` request (`outputsize=compact`, the last 100 sessions), computes the reactions of that ticker's selected reports from that series in memory, ATR-14 included (the inline fallback of `compute_reaction()._atr`, `:370-410`, read), upserts that ticker's reaction rows in their own transaction before the next ticker, and writes nothing to `market_data_daily`. Today `populate_for_tickers` upserts once after every ticker (`compute_earnings_reactions.py:849-872`, read), so a run stopped by its timeout would lose all of its work; per-ticker commits keep every finished ticker (CLAUDE.md rule 0.4). A vendor failure for a ticker is logged by name, writes no row for it, and fails the run after the other tickers (CLAUDE.md 3.7: no stale or fabricated reaction); the next Sunday selects it again.
- Reactions of older reports stay as stored; they are not recomputed, because their bars are gone. Their numbers were computed from as-traded closes (`market_data_daily` open, high, low and close are as traded: `db-query-6k2lm`, `db-query-mcv58`).
- This is the one price fetch outside the watchlist, by the owner's instruction 4, and it stores no bar. The basis check on the fetched series (no adjusted close; a split inside a window marks that reaction unavailable) is the companion code spec's (`docs/superpowers/specs/2026-11-16-feat-data-001-no-adjusted-prices.md`, merged as a draft with #1978).
- The Sunday `fetch-earnings-history` run must bring in last week's quarters before the reaction run reads them. Today its weekly scope force-refetches only the reporters of `[today, today + 7]` (`_tickers_reporting_in_window`, `fetch_earnings_history.py:274-300`, and `_filter_already_have_history`, `:311-341`, read), so a ticker that reported last Wednesday and already has history rows is skipped on Sunday; only the weekday 19:15 run captures it. After: the weekly scope force-refetches the reporters of `[today - 7, today + 7]` in Eastern time, so the new quarter and `eps_actual` land at 19:15 and the 19:30 reaction run finds them.
- **The Sunday consumers run after the reaction run.** Today four Sunday jobs that read the reactions, or what is built from them, start on their own crons (on main 4155a10f, read): `earnings-long-watchlist-sunday` at 19:45 (`gcp/deploy.sh:4782`), `refresh-earnings-views-weekly` at 20:00, which rebuilds the two materialized views from `earnings_reactions` (`:4805`), `earnings-sweep-sunday` at 20:30 (`:4796-4798`), and `premarket-brief-sunday` at 21:00 (`:4454`), whose comment says it runs after the refresh chain "has populated fresh AV options + history + reactions" (`:4451-4453`; it reads `earnings_reactions` through `enrich_with_playability` and `conditional_lean_summary`, `gcp/premarket_brief.py:569-570`, `:770`, whose queries read the table at `lib/earnings_reactions.py:540` and `:704`). The 19:30 reaction run's peak estimate is about 70 minutes (Capacity), ending about 20:40, after the first three have started, and its timeout is set far beyond that. Spec C starts each of the four only after the reaction execution of that evening has completed, in their present order (long watchlist, views, sweep, brief); moving them past the reaction job's timeout budget instead (about 16,800 s from 19:30, so past midnight) would move them into Monday and is not recommended. The acceptance case is spec C's and is checked again in Close-out step 6.
- The weekday schedulers `daily-earnings-refresh-history` (`15 19 * * 1-5`) and `daily-earnings-refresh-reactions` (`30 19 * * 1-5`) are retired in spec C, taking effect together with this change (Close-out step 1); the Sunday `weekly-earnings-refresh-*` runs stay. The weekday calendar run (`daily-earnings-refresh-calendar`, 19:00) stores no price and stays unless the owner says otherwise.

### 8a. `fetch-top-movers`: today's list only (Decision 8)

- The daily run upserts today's rows into `top_movers_daily` and deletes the rows of any earlier `snapshot_date` in one transaction (`gcp.database.get_engine().begin()`), so a failure leaves yesterday's list rather than none. The hourly `--intraday-snapshot` run does the same on `top_movers_intraday`, keeping every snapshot of today for the most-active bar's sparklines. An empty vendor answer returns before any write, as on main (`fetch_top_movers.py:254-257`, `:274-276`, read).
- Its tickers are the vendor's market-wide list, not a per-ticker history and not the watchlist; it stays outside the fetch universe by the owner's direction, and the guard in Design 9 does not cover `TOP_GAINERS_LOSERS`.

### 9. The guard

- `tests/gcp/test_price_fetch_universe.py` and `tests/scripts/test_backfill_watchlist_data.py` hold a refusal test for each entry point above, and one AST walk covers `gcp/` and `scripts/`: the files holding a price request (a dict literal whose `function` is `TIME_SERIES_INTRADAY`, `TIME_SERIES_DAILY`, `TIME_SERIES_DAILY_ADJUSTED` or `GLOBAL_QUOTE`) are exactly the five under `gcp/` and the five under `scripts/` that exist today (on main 4155a10f, run: `grep` of those literals over both directories) plus `compute_earnings_reactions.py` (Design 8), which fetches and stores no bar. Each file that writes to the database has a refusal test; `gcp/signal_monitor.py` and the three scripts that write local files only are named with that reason. A new fetcher in either directory fails the walk until it is added with a refusal test or a named reason.
- What it does not see: requests outside `gcp/` and `scripts/`. `platform/api/routers/live.py` (`:199`, `:403`, `:465`, `:576`) and `lib/ticker_info.py:467` answer a user's request live and store no bar (read; `get_quote` stores nothing, read at `lib/ticker_info.py:450-500`).
- A watchdog row for untracked price rows was considered. It adds a freshness row to two routes (two more site elements and an API test) for what the one-week check in Close-out step 9 shows once. Not taken.

### 10. Close-out SQL files

- `gcp/queries/truncate_intraday_untracked.sql`: `DO $$ BEGIN PERFORM set_config('lock_timeout', '5s', true); TRUNCATE TABLE market_data_intraday_other; END $$;` A DO block because the dispatcher splits inline SQL on `;` and runs each statement in its own transaction (CLAUDE.md, Database access), so a separate `SET` would not hold. A lock not granted in 5 seconds fails the run; it is not retried by the dispatcher.
- `gcp/queries/drop_adjusted_close.sql`: the same lock timeout, then `ALTER TABLE market_data_daily DROP COLUMN adjusted_close`.
- Both are sent with `-f` (one statement). Every other Close-out statement is inline.

### 11. Site traceability

`site_source_notes` follows the rule the sibling specs use (`2026-11-14-feat-data-001-replace-held-session-window-r2.md`, section 11): per page, the first Chain row of `docs/product/03-SITE-TRACEABILITY.md` whose Data cell names a changed job. Read at `main` a34bbd40 by script over the Data cells:

| Page | `fetch-market-data` | `fetch-earnings-history` | `fetch-premarket-refresh` | `fetch-alphavantage-intraday` | `backfill-ticker` |
|---|---|---|---|---|---|
| Dashboard | DASHBOARD-01 (`:331`) | DASHBOARD-01 | DASHBOARD-01 | DASHBOARD-04 (`:334`) | DASHBOARD-01 |
| Live | LIVE-04 (`:426`) | LIVE-04 | not named | LIVE-08 (`:430`) | LIVE-04 |
| Charts | CHARTS-01 (`:506`) | CHARTS-03 (`:508`) | not named | CHARTS-01 | CHARTS-01 |
| AI Insights | INSIGHTS-01 (`:750`) | INSIGHTS-01 | INSIGHTS-01 | not named | INSIGHTS-01 |
| Catalysts | not named | not named | not named | not named | CATALYSTS-01 (`:830`) |
| Playbook | PLAYBOOK-05 (`:905`) | PLAYBOOK-05 | not named | not named | PLAYBOOK-05 |
| Journal | JOURNAL-01 (`:1041`) | JOURNAL-04 (`:1044`) | not named | JOURNAL-01 | JOURNAL-01 |
| Admin | ADMIN-06 (`:1123`) | not named | not named | not named | not named |

- `fetch-watched-tickers` and `compute-earnings-reactions` are named in no Data cell.
- Each note says what the source now does: the job's tickers come from the default watchlist and any other requested ticker is refused. None claims a change on a page. What a user sees change is data, once Close-out runs, and the pages for other tickers (separate specs D and E).

### 12. Capacity

| Step | Volume | Velocity | Wall-clock | Bound |
|---|---|---|---|---|
| any fetch job, the universe read | 3 rows | one query per run | 11 to 26 ms for reads of this table (`db-query-89ccp` statements 3 to 6) | 120 s statement timeout |
| nightly `fetch-market-data` after | 3 tickers | 2 vendor calls each, 6 a night, down from 240 to 346 | 3 to 13 minutes a run today (`fetch-market-data` executions of 2026-11-14 and 15, run: listing); after, not measured | 5,400 s task timeout |
| `fetch-earnings-history` chain after | 3 targets, down from 2,664 | at most 3 vendor calls a run, 6 runs a week | today 65 of 70 minutes (`fetch-earnings-history-nsmx7`); after, the EPS fetch only, not measured | 28,800 s |
| `fetch-premarket-refresh` after | 3 tickers, down from 50 | one fetch per ticker (read: `compute_premarket_for_ticker` calls `fetch_minute_data`, `:199`) | 40 to 54 s today (`-c47zg`, `-57wmb`, `-z26xq`) | unchanged |
| Sunday `compute-earnings-reactions` after | in steady state the reporters of two weeks (those whose D+1 session closed since the last run, and those whose tenth session closed since it), plus any report a failed run left pending, within 60 days: about twice a week's count, so median about 180 and at most about 1,500 (from the weekly counts of the last 52 weeks: median 89, max 755, `db-query-2k89c`, measured for the companion spec); one daily series of 100 sessions each held in memory | one daily-series call per reporter, plus the companion spec's one split-list call, one reaction upsert per 1,000 rows | at about 1.4 s a call (the local 0.4 s pacing of `lib/config.py:124` plus latency, the companion spec's estimate): median about 8 minutes, peak about 70 minutes (estimate) | the reaction job's timeout is set in spec C to at least 4 times the peak, about 16,800 s (CLAUDE.md rule 0.5); a backlog beyond it (every run failing for weeks) is not covered: per-ticker commits keep each finished ticker and the next Sunday continues, oldest first |
| TRUNCATE of `market_data_intraday_other` | about 270 million rows, 72,721,956,864 bytes | one statement | not measured; TRUNCATE replaces the files rather than visiting rows | 5 s lock timeout |
| DELETE from `market_data_daily` | 5,790,874 rows in 12 year chunks, the largest 637,779 (2025) before the sector ETFs' rows of that year | 12 statements, each its own transaction | each chunk plans a sequential scan of the 4.17 GB heap (EXPLAIN, `db-query-2fnc5`); a full scan of it took 29.8 s (`db-query-bxrxg`). About 6 to 12 minutes in all; the delete work itself not measured | `--timeout 600` a statement, 4 times the high estimate of one chunk |
| DELETE from `historical_signals` and `signal_metrics` | 211,735 rows each, 9,241 to 27,067 a ticker | 13 statements each, one per ticker | bitmap index scans (EXPLAIN, `db-query-zrwbj`); not measured | `--timeout 300` |
| the small tables | at most 67,116 rows (`earnings_reactions`) | one statement each | not measured | `--timeout 300` |
| `adjusted_close` clear | 8,092 rows | one UPDATE | not measured | `--timeout 300` |

- Vendor calls saved: about 2,660 (chain) plus 234 to 340 (nightly) plus 47 (premarket), so about 2,940 to 3,050 a weekday and 2,660 on Sunday; the Sunday reaction run adds one call per reporter in its passes (Design 8), not measured; the dashboard's sector card adds 11 a session (Decision 2). The account is a flat purchased allowance of 600 RPM (`lib/config.py:115-124`, read); whether calls are billed one by one was not checked.
- Cloud Run time saved: about 65 minutes of 1 vCPU and 1 GiB a run, 6 runs a week: about $0.08 a run and about $2 a month at $0.000018 a vCPU-second and $0.000002 a GiB-second (list prices, not re-read).
- Disk: the deletes give back about 72.7 GB (partition) plus about 4.1 GB (daily heap and indexes, after vacuum) plus about 0.9 GB (22% of `historical_signals`) to Postgres for reuse, from a 182.3 GB database on a 203 GB disk. Cloud SQL does not shrink a disk (not re-read for this spec), so the storage bill stays; what stops is growth and the next auto-resize. `VACUUM FULL` is not run: the dispatcher wraps every statement in a transaction, where it cannot run.
- Dumps: today's are about 15.4 GB; after, smaller, not estimated.
- GCS: Decision 12 removes about 1.8 GB, or 4.4 GB with `raw/spx/`, `raw/spy/`, `raw/qqq/` and `raw/iwm/`: under $0.10 a month at $0.02 a GB-month (list price, not re-read).
- A fresh dump: the last five ran 23 to 30 minutes (object times, run: listing) on 1 vCPU and 512 MiB, about $0.04.

## Decisions for the owner

Each is written into the text as recommended. Striking one changes only the sections named.

1. **The fetch universe is the active default watchlist, read strictly; any other requested ticker exits 2** (Design 1 to 8). Alternative: drop other tickers silently with a logged count. Not recommended: a request for NVDA that quietly fetches nothing reads as success.
2. **Sector ETFs (XLB materials, XLC communication services, XLE energy, XLF financials, XLI industrials, XLK technology, XLP consumer staples, XLRE real estate, XLU utilities, XLV health care, XLY consumer discretionary): fetched live only; decided by the owner (instruction 7, "Fetch them live only", 2026-11-16).** Today the nightly fetch stores each one's 1-minute and daily bars every weekday (`fetch_market_data.py:42-43`, read), 28,144 daily rows in all, and the only reader is the dashboard sector card, which uses about the last week of daily closes (`platform/api/main.py:1439-1490`, read). The stored rows are deleted and the nightly fetch stops; the card's route fetches the 11 recent daily series from the vendor on request (`TIME_SERIES_DAILY`, compact, 11 calls) and holds them in the API's cache until the next session, storing nothing in the database (spec D). Spec D's live route is deployed before Close-out step 1. Nothing is stored for them nightly and no ticker list is written into the fetch.
3. **Keep `^VIX` (2,988 rows) and its Yahoo fetch, and keep `^VIX3M` and `^VVIX` (2,864 and 2,856 rows, no writer).** They are index levels, which carry no split or dividend adjustment, and SPY, QQQ and IWM features read them.
4. **SPX:** delete its 124 `strat_levels` and 4 `premarket_analysis_history` rows; leave the empty `market_data_intraday_spx` partition; keep the SPX option chain and Greeks.
5. **Earnings reactions: decided by the owner (instruction 4).** Keep `earnings_reactions` (67,116 rows), its two materialized views and `earnings_options_strategy_winners` (2,520). New reactions are computed each Sunday from prices fetched for the run and not stored (Design 8); the weekday earnings history and reaction runs are retired (spec C). `earnings-reactions-brief`, `earnings-long-watchlist` and `earnings-sweep` keep reading them. A report on a weekday gets its reaction the following Sunday.
6. **Signals:** delete the 211,735 untracked rows of `historical_signals` and of `signal_metrics`. `signal_alerts`, `trades` and `journal_entries` hold no untracked row, so T's keep of journal entries and trades costs nothing.
7. **Insight reports:** delete the 525 untracked rows of `insight_reports` and of `insight_reports_history`; keep `insight_runs` (565 rows) as the run and cost log. The platform's refresh can still write a report for any ticker; spec D makes it refuse untracked tickers.
8. **Top movers: keep them as today's list only, overwritten each run (the owner's direction).** The vendor call takes no date and every reader reads only the latest day (Problem 1), so the history is unused. `fetch_top_movers` writes today's daily list and deletes every earlier `snapshot_date` of `top_movers_daily` in the same transaction; the hourly run appends today's snapshot (the most-active bar draws its sparklines from the day's snapshots) and deletes every earlier `snapshot_date` of `top_movers_intraday`. An empty vendor answer (a closed day) writes and deletes nothing, so the last session's list stays. The schedulers stay. No schema change. The first run on the new code removes the stored history (8,757 and 14,356 rows less today's).
9. **Per-user watchlists (FEAT-INSIGHT-001) and PR #1963: live on request, nothing stored.** Both tables are empty today. Answering the owner's "figure out how to do this vs unavailable": a user may add any ticker; its row shows the live price, change and today's intraday chart fetched when the page asks, and nothing is stored. The API already serves a live quote (`GLOBAL_QUOTE`, `platform/api/routers/live.py:199`) and the last 100 intraday bars (`:465`) on request without storing them (read); the list view takes one `REALTIME_BULK_QUOTES` call for up to 100 symbols (the vendor's tool schema, read; whether the account's entitlement includes it was not checked). What needs stored history (signals, levels, the brief, insights) stays SPY, QQQ and IWM, and the page says so for any other ticker. Spec D adds the live list route; spec E shows it and replaces the false "data arrives after tonight's fetch" copy (solyra `src/components/insights/watchlistCopy.ts:17-24`). So the nightly per-user fetch is not needed: #1963 (open, FEAT-DEPLOY-001, adds `watched-tickers-nightly` at 23:45 ET) is held, and spec C retires `fetch-watched-tickers` (owner's call).
10. **`market_data_indicators`: TRUNCATE (23,922 rows).** Its basis is not known, nothing in production reads it, and its fetcher is not scheduled. Magnitude phase 2 returns to needing its backfill. Alternative: keep it until one AlphaVantage call compares an indicator with one computed from as-traded bars.
11. **`archive_yahoo_market_data_intraday`: TRUNCATE (51,471 rows) now; drop the table in spec B.**
12. **GCS:** delete the 913 per-ticker folders and `raw/spx/`; also `raw/spy/`, `raw/qqq/` and `raw/iwm/` (yfinance era, `Adj Close`, no reader found). Keep `raw/data/`, `raw/reports/` and `raw/signals/`.
13. **Restore point: decided by the owner.** A fresh dump right before the first delete, verified with `gzip -t`, left in `sql-dumps/`, where the bucket's 30-day rule deletes it like every weekly dump (`gcp/deploy.sh:3337-3367`, read). No copy is kept beyond that. The owner: "Yes drop it, bad data" (2026-11-16): much of the deleted data was stored adjusted, and a ticker is brought back by refetching it as traded, not by restoring it.
14. **The DEFAULT intraday partition: keep it.** It is emptied in Close-out step 4 and stays. With the admin editor (Decision 16) a ticker added to the default watchlist has its 1-minute bars written to DEFAULT, since `gcp/schema.sql:156-165` creates only the SPY, IWM, QQQ and SPX partitions and no add path creates one (on main 4155a10f, read). Spec B does not drop it. What refuses an untracked ticker's bars is the fetch universe (Design 1), not the schema.
15. **`adjusted_close`:** clear the remaining rows and drop the column after the companion spec is deployed everywhere (Close-out steps 7 and 8); its line in `gcp/schema.sql` goes in spec B.
16. **An admin edits the default watchlist in solyra: decided by the owner (instruction 6).** It is the one list that decides what is fetched and stored, so it gets an editor on `/admin`. Today it changes only through Discord `/watchlist add` and `/watchlist remove` (`gcp/discord_interactions/main.py:604-705`) and the CLI, and the web shows it read-only (solyra `src/components/insights/DefaultWatchlistSection.tsx`, "Managed in Discord"); read. Specs F and G add it. Recommended, written into F: adding a ticker starts its as-traded history fetch (daily and 1-minute) at once, so it does not wait for the nightly run; removing a ticker stops its fetch from the next run and deletes nothing, since a delete cannot be undone and a re-add would otherwise refetch the whole history. Deleting a removed ticker's stored history stays a separate step on the owner's word, as in Close-out. Discord stays a second way in; both write the same `watchlists` rows. Alternative for the owner: removing a ticker also deletes its stored price data, after a confirmation in the panel.

## Split and separate specs

This spec's implementation is one PR of 17 tasks:

1. `_watchlist.py`: the shared SQL, `price_fetch_universe`, `require_tracked`, and `calibrate_level_params` on the shared SQL.
2. `fetch_market_data` nightly: the universe, the refusal, the removed list and augmentation.
3. `_run_backfill` and `_backfill_targets`.
4. `fetch_watched_tickers`: the exclusion.
5. `fetch_premarket_refresh`.
6. `fetch_alphavantage_intraday`.
7. `backfill_ticker`.
8. `migrate_to_gcp`.
8a. `scripts/backfill_watchlist_data.py`: the refusal and the fetcher call without `--earnings-window-days` (Design 7a).
8b. `scripts/deep_backfill_ticker.py`: the refusal (Design 7a).
9. `compute_earnings_reactions`: the two passes over 60 days, the reporters fetched for the run, no bar stored.
9a. `fetch_top_movers`: today's list only, overwritten each run (Decision 8).
9b. `fetch_earnings_history`: the weekly scope refreshes the reporters of the last 7 days too (Design 8).
10. The AST guard over `gcp/` and `scripts/`.
11. The two Close-out SQL files and their test.
12. Site notes, snapshot, inventories, catalog, traceability, docs audit, gate.
13. PR-body measurements.

Changes this spec does not make, each a spec of its own:

- **B (FEAT-DATA-001, schema):** after the companion spec is deployed and Close-out step 8 has run, remove `adjusted_close` from `gcp/schema.sql:111`, drop `archive_yahoo_market_data_intraday` and its script. It keeps the DEFAULT partition of `market_data_intraday` (Decision 14).
- **C (FEAT-DEPLOY-001):** remove `EARNINGS_WINDOW_DAYS`, `BACKFILL_ALL_HISTORY` and the other unread variables from the jobs; retire `fetch-watched-tickers` (Decision 9) and `intraday-bulk-backfill` unless spec F starts it for an added ticker's 1-minute history and, per Decision 5, the weekday schedulers `daily-earnings-refresh-history` and `daily-earnings-refresh-reactions` (the Sunday runs stay), set the reaction job's task timeout to at least 4 times its peak run (Capacity: about 16,800 s), and start `earnings-long-watchlist`, `refresh-earnings-views-weekly`, `earnings-sweep-sunday` and `premarket-brief-sunday` only after that Sunday's reaction execution has completed, in that order (Design 8), all deployed before this spec's Close-out step 1; its acceptance case is a Sunday whose reaction execution runs past 20:30 ET (a stub run held for 70 minutes, or a replay) and shows from `gcloud run jobs executions list` each of the four starting after that execution's completion time; settle #1963 (Decision 9).
- **D (FEAT-INSIGHT-001, API):** a live quote list for a user's watchlist (one bulk-quote call for up to 100 symbols, nothing stored); the sector card's route fetching the 11 ETFs' daily series on request with a per-session cache (Decision 2, decided by the owner), with an API test against an empty stored sector history; it is live before this spec's Close-out step 1; the insight refresh refusing a ticker it has no stored history for, with a typed reason.
- **E (solyra):** the watchlist row and add notice show the live quote and chart for any ticker, and a plain note that history-based views (signals, levels, brief, insights) cover SPY, QQQ and IWM; the false "data arrives after tonight's fetch" copy goes. Never an empty panel.
- **F (FEAT-ADMIN-001, API):** admin-only routes on the default watchlist (Decision 16): add a ticker, remove it, and set its brief, insight and signals flags, writing the same `watchlists` rows as Discord, behind the admin check `/api/admin` already uses (`platform/api/routers/admin.py:52-66`). Adding validates the symbol with the vendor and starts the ticker's daily and 1-minute history fetch through the existing Cloud Run jobs, the way `/api/admin` already starts a job (`:1493-1511`), and returns the executions so the panel can show their progress; removing deletes nothing.
- **G (FEAT-ADMIN-001, solyra):** a "Default watchlist" tab on `/admin` with add, remove and the three flags, each added ticker's history fetch shown until it finishes; the read-only list on the insights page says where it is edited.

## Close-out

None runs from the implementation PR, and none is a `done_when` box. Each step waits for the owner's own yes for that step, names its check, and is recorded as a comment on the implementation PR. Every command runs from a checkout of `main`. `K` below is the keep list: `('SPY','QQQ','IWM','^VIX','^VIX3M','^VVIX')`.

1. **Deploy the code**, only once two other specs are live, since this deploy stops the nightly fetch of every ticker off the watchlist:
   - Spec C: `compute-earnings-reactions` runs with a task timeout of at least 16,800 s (Capacity), read with `gcloud run jobs describe compute-earnings-reactions --region=us-east1`. Its retirement of the weekday history and reaction schedulers takes effect in this same step, not earlier: until the weekly history change of Design 8 is live, only the weekday run captures last week's quarters. Today the job's timeout is 1,800 s (`gcp/deploy.sh:3008-3023`, read), under the peak run's estimate.
   - Spec C's sequencing of the four Sunday consumers after the reaction run (Design 8) is deployed, read with `gcloud scheduler jobs describe` of each of the four schedulers (or of what spec C puts in their place).
   - Spec D (Decision 2): its live sector route is deployed and its API test against an empty stored sector history passes on `main`. Today `/api/market/sectors` reads only `market_data_daily` and returns `status: unavailable` without the ETF rows (`platform/api/main.py:1456-1483`, read), so without spec D the card would go dark once the 10-day lookback runs out.
   Then `./gcp/deploy.sh fetchers` (fetch-market-data, fetch-alphavantage-intraday, fetch-earnings-history, compute-earnings-reactions, fetch-premarket-refresh among its jobs, `gcp/deploy.sh:3207-3234`), `./gcp/deploy.sh discord` (backfill-ticker) and `./gcp/deploy.sh intraday-bulk-backfill`.
   - Check: each job's image is the build's digest (`gcloud run jobs describe <job> --region=us-east1`). After one night, the `fetch-market-data` log reads `Total tickers : 3`, the `fetch-earnings-history` log reads `Eligible targets: 3`, and the next `fetch-premarket-refresh` log reads `Resolved universe: 3 tickers`.
   - Nothing below starts before this check passes: a delete before it would refill the next night.
2. **Restore point.** `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud run jobs execute cloud-sql-weekly-export --region=us-east1 --wait`.
   - Check: `gcloud storage ls -l gs://adept-mountain-474619-d4-trading-data/sql-dumps/` lists an object dated today; `gcloud storage cat <object> | gzip -t` exits 0. No copy is made (Decision 13): the dump ages out with the 30-day rule. Point-in-time recovery covers the 7 days after as a backstop.
3. **The watchlists.** Read-only: `./scripts/db_query_cr.sh -q "SELECT user_id, ticker FROM watchlists WHERE removed_at IS NULL ORDER BY 1, 2; SELECT count(*) FROM user_watchlists WHERE removed_at IS NULL; SELECT count(*) FROM watched_tickers"`.
   - Expected: `default` IWM, QQQ, SPY; 0; 0 (as in `db-query-89ccp`). Then no write is needed.
   - If another active default row has appeared, the write is `UPDATE watchlists SET removed_at = now() WHERE user_id = 'default' AND removed_at IS NULL AND ticker NOT IN ('SPY','QQQ','IWM')` with `--commit`; its trigger records the removal. The same read then returns the three rows. Rows in `user_watchlists` follow Decision 9.
4. **1-minute bars.** Dry run first: `./scripts/db_query_cr.sh -f gcp/queries/truncate_intraday_untracked.sql` (rolled back; it shows the lock was granted). Then the same with `--commit`.
   - Check: `SELECT count(*) FROM market_data_intraday_other` returns 0; `SELECT pg_total_relation_size('market_data_intraday_other')` is under 1 MB; `SELECT relname, reltuples::bigint FROM pg_class WHERE relname IN ('market_data_intraday_spy','market_data_intraday_qqq','market_data_intraday_iwm')` reads as before (about 2.50, 2.33 and 2.03 million, `db-query-f9bxp`).
5. **Daily bars.** Twelve statements in one dispatch, each its own transaction, first without and then with `--commit`, `--timeout 600`: `DELETE FROM market_data_daily WHERE date < '2016-01-01' AND ticker NOT IN K`, then for each year Y from 2016 to 2026 `DELETE FROM market_data_daily WHERE date >= 'Y-01-01' AND date < 'Y+1-01-01' AND ticker NOT IN K`.
   - Expected row counts. Measured with the 17 names of Problem 3 kept (`db-query-2fnc5`): 8,879 before 2016, then 236,701; 441,801; 466,306; 491,600; 519,839; 565,699; 594,000; 603,583; 623,337; 637,779; and 573,206 for 2026 to 2026-11-16, total 5,762,730. The sector ETFs' 28,144 rows (Decision 2) (`db-query-zrwbj`) are added across 2016 to 2026; the dry run prints each year's count with them. Total 5,790,874, plus the rows the nightly wrote before step 1 took effect.
   - Check: `SELECT count(*), count(DISTINCT ticker) FROM market_data_daily` returns 16,661 rows and 6 tickers (7,953 SPY, QQQ, IWM plus 8,708 for the three VIX symbols, plus the sessions written since 2026-11-16); `SELECT count(*) FROM market_data_daily WHERE ticker IN ('SPY','QQQ','IWM')` is unchanged.
6. **Tables built from them.** Each statement inline, dry run and then `--commit`, `--timeout 300`; each check is the same table's count of rows with `ticker NOT IN ('SPY','QQQ','IWM')` returning 0 (or, for `indicator_correlation`, untouched).
   - `DELETE FROM historical_signals WHERE ticker = '<T>'` and `DELETE FROM signal_metrics WHERE ticker = '<T>'` for each of the 13 tickers of Problem 2: 211,735 rows each.
   - `DELETE FROM premarket_analysis WHERE ticker NOT IN ('SPY','QQQ','IWM')` (11); the same on `premarket_analysis_history` (16), `strat_levels` (457), `ticker_level_params` (92).
   - Decision 7: the same on `insight_reports` (525) and `insight_reports_history` (525).
   - Decision 5: nothing is deleted from `earnings_reactions`, `earnings_options_strategy_winners` or their views. Check instead, after the first Sunday run on the new code: the `compute-earnings-reactions` log names the reporters fetched and `SELECT count(*) FROM market_data_daily WHERE ticker NOT IN K AND date >= current_date - 7` returns 0, and `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud run jobs executions list` for `earnings-long-watchlist`, `refresh-earnings-views`, `earnings-sweep` and `premarket-brief` shows each Sunday execution starting after that evening's `compute-earnings-reactions` execution completed.
   - Decision 8: no delete step. After the first runs on the new code, `SELECT count(DISTINCT snapshot_date) FROM top_movers_daily` and the same on `top_movers_intraday` each return 1.
   - Decisions 10 and 11: `TRUNCATE TABLE market_data_indicators` (23,922) and `TRUNCATE TABLE archive_yahoo_market_data_intraday` (51,471); each then counts 0.
   - Tables with no untracked row (Problem 2): the check alone.
7. **Clear `adjusted_close`**, only once the companion spec's code is deployed to every job and service and its own check has passed. `UPDATE market_data_daily SET adjusted_close = NULL WHERE adjusted_close IS NOT NULL`: 8,092 rows, dry run then `--commit`. Check: `SELECT count(adjusted_close) FROM market_data_daily` returns 0, and again the next day (no writer left).
8. **Drop the column.** `./scripts/db_query_cr.sh -f gcp/queries/drop_adjusted_close.sql --commit`. Check: `SELECT count(*) FROM information_schema.columns WHERE table_name = 'market_data_daily' AND column_name = 'adjusted_close'` returns 0; the next night's `fetch-market-data`, `fetch-earnings-history` and `backfill-daily-indicators` executions succeed. Spec B then removes it from `gcp/schema.sql`.
9. **One week later, read-only.** `SELECT count(*) FROM market_data_intraday_other` returns 0, and `SELECT ticker, count(*) FROM market_data_daily WHERE date >= current_date - 7 AND ticker NOT IN K GROUP BY ticker` returns no row. A row in either means a path this spec missed; it is recorded on the PR with the writer found from its `data_source` and `inserted_at`.
10. **GCS** (Decision 12). `gcloud storage ls gs://adept-mountain-474619-d4-trading-data/raw/`, keep the three kept prefixes out of the list, and `gcloud storage rm -r` the rest, recorded with its count (917 folders: the 913, `spx`, `spy`, `qqq`, `iwm`). Check: `gcloud storage du -s gs://adept-mountain-474619-d4-trading-data/raw/` reads 8,284,240,054 bytes, the sum of `raw/data/`, `raw/reports/` and `raw/signals/` as measured, plus anything written there since.

The site evidence for this change is the pages of other tickers, specs D and E; nothing on a SPY, QQQ or IWM page changes.

## Risks

- **A delete before the fetch change refills.** Step 1's check comes first, and step 9 looks for refills a week on.
- **A ticker removed by mistake.** The restore point of step 2 covers 30 days and point-in-time recovery 7; after that nothing is kept (Decision 13). Re-adding a ticker is one watchlist row, its history refetched as traded, and the builders rerun.
- **A consumer of other tickers' data breaks loudly.** The sector card and a user's watchlist move to live fetches (specs D and E); an untracked ticker's stored-history views (charts of past sessions, signals, insights) show their SPY, QQQ and IWM scope. Which pages already do this rather than show an empty panel was not checked page by page.
- **Live fetches spend vendor calls per page view.** The sector card's cache holds a day; the watchlist list is one bulk call per view. Not measured; the account's 600 RPM allowance is far above a single user's views (estimate).
- **Earnings reactions arrive a week later.** With only the Sunday run, a report on Monday gets its reaction six days later, and a report on Friday nine days later (its D+1 session closes the next Monday), where the weekday run gave it the next evening. The owner chose this (instruction 4).
- **A report pending past 60 days stays incomplete.** A ticker whose fetch fails every Sunday for nine weeks keeps NULL reaction columns, logged as past the bound; it is not fabricated and not retried after that.
- **The Sunday consumers start later on a long run.** Chained after the reaction run (spec C), the brief and the sweep start when it ends rather than at a fixed time; at the peak estimate the brief starts about 20:40 plus the three jobs before it.
- **TRUNCATE blocks readers.** It takes an exclusive lock on the partition; the 5-second lock timeout makes it fail rather than queue behind a long read. Whether a query on the parent that does not name a ticker waits on that lock was not checked; step 4 runs on a Sunday between 06:00 and 18:00 ET, after the weekly dump (`cloud-sql-weekly-export-sunday`, 04:00) and before the Sunday earnings chain (19:00).
- **The `_backfill_targets` read goes strict.** A database error in the chained backfill now raises inside `fetch_earnings_history`, which logs it as non-fatal (read). That is the existing behaviour for every other error there.
- **The per-user job fails nightly once a user adds a ticker** (Design 4), until spec D refuses the add or spec C retires the job.
- **A hand-run script outside both directories.** The guard walks `gcp/` and `scripts/`; a price request added elsewhere (for example under `lib/`) is not seen by it. Close-out step 9 finds a refill a week on.

## What was not verified

- The 270,472,992 rows of the partition are a `pg_class` estimate; `pg_stat_user_tables` counts 8,450,021 live tuples for it and records no autovacuum (`db-query-gvkbh`). The byte size is exact.
- The run's wall-clock on the vendor: per-call latency is the companion spec's estimate, not measured here.
- The wall-clock of the TRUNCATE, the deletes and the dump check; the WAL each delete writes.
- Whether AlphaVantage's indicator endpoints compute on adjusted prices.
- Whether vendor calls are billed per call.
- Which writer last wrote `raw/signals/` and whether anything outside this repo reads `raw/`.
- Solyra pages other than the watchlist copy were not read for their handling of an untracked ticker.
- How many reports a failed run leaves pending, and so the backlog the 60-day bound admits in practice: not measured.
- Whether `earnings-long-watchlist`, `earnings-sweep` and `premarket-brief` read anything else the reaction run writes, beyond the reads cited in Design 8: not checked file by file. The ordering of the four after the reaction run is spec C's to prove.
- The six #1980 findings were checked against code on main 4155a10f by reading it; none was executed (no test exists yet for any of them).
