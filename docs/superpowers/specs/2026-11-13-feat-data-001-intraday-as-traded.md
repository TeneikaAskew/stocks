---
feat_id: FEAT-DATA-001
req_ids: [REQ-DATA-001, REQ-DATA-003]
issues: [1190]
canvases: []
done_when:
  - "tests/gcp/test_intraday_as_traded.py passes: the AlphaVantage TIME_SERIES_INTRADAY request built by fetch_alphavantage_intraday.fetch_month, by fetch_market_data.fetch_minute_bars and by fetch_market_data.fetch_minute_data each called without an adjusted argument, and by backfill_ticker.av_intraday_month carries adjusted=false, and fetch_minute_bars called with adjusted=True raises ValueError"
  - "tests/gcp/test_intraday_as_traded.py::test_every_intraday_request_in_the_repo_asks_for_as_traded passes: every dict literal in a Python file under gcp/, scripts/ and platform/ that holds the constant TIME_SERIES_INTRADAY carries adjusted as the string literal false, found by AST with no exemption list, and the guard's own cases show it rejects a missing key, the literal true and an expression"
  - "tests/api/test_live_opening_window.py passes with test_opt_in_contract changed to require adjusted=false on the compact /api/live/history request (it asserted the key was absent)"
  - "make test passes on the PR head with tests/gcp/test_evaluate_ew_strikes.py, tests/gcp/test_intraday_replace_months.py and tests/gcp/test_intraday_writers_utc.py unchanged"
  - "02-FEATURE-CATALOG FEAT-DATA-001 record shows Status and Last reviewed for this PR, and 12-PR-ISSUE-TRACEABILITY lists it"
status: draft
supersedes: null
---

# Every AlphaVantage 1-min request asks for as-traded prices

## Scope

- Every AlphaVantage TIME_SERIES_INTRADAY request in the repo asks for `adjusted=false`, whatever ticker it is for, and a test keeps it so.
- This spec changes requests only. The gap alarm, the basis check, the durable bucket copy, the refill of the missing sessions and the rewrite of the months already stored on an adjusted basis are a second spec (`docs/superpowers/specs/2026-11-13-feat-data-001-intraday-gaps-basis-copy.md`, on its own PR). It was split out so this change can ship first.
- No trading cost is applied or stored anywhere in this change.

## Problem

Found on 2026-11-13.

- AlphaVantage's TIME_SERIES_INTRADAY returns split- and dividend-adjusted prices unless the request says `adjusted=false`, adjusted as of the call.
- Eight requests in the repo name that endpoint. Seven ask for adjusted prices, by saying so or by leaving the parameter out (the Design lists each by file and line). Three of the seven write `market_data_intraday`.
- So every stored bar sits at the basis of its last fetch. Measured against AlphaVantage's `adjusted=false` series, bar by bar with identical volumes: SPY 2025-04 and 2025-05 are stored at 0.99430 of the traded price, SPY 2025-06 steps to 0.99725 at the June ex-dividend date, QQQ 2025-01 is at 0.99629, and SPY, QQQ and IWM 2025-11 are at exactly 1.00000.
- The nightly makes new stretches. It refetches the previous month with `--force`, so a month is rewritten at a new basis when an ex-dividend date falls in that window. SPY is stored about 0.25% low for 2026-02-02 to 03-19 (0.99724), 2026-05-01 to 06-17 (0.99746) and 2026-08-03 to 09-17 (0.99753). SPY 2026-08-31 15:59 ET is 765.053 in the table and traded at 766.95.
- Months that hold sessions on an adjusted basis, by comparing each session's 1-min regular-hours high and low with the daily table's, which is as traded:

| Ticker | From 2025-01: months | Rows in them | Whole exported history: months | Rows in them |
|---|---|---|---|---|
| SPY | 15 | 304,302 | 50 | 923,571 |
| QQQ | 15 | 314,655 | 119 | 1,983,926 |
| IWM | 16 | 317,038 | 120 | 1,737,874 |

- Readers compare these bars with as-traded numbers: the brief's levels come from the daily table, and live quotes and strikes are as traded (`platform/api/routers/live.py:403` and `evaluate_ew_strikes.py` already ask for `adjusted=false`, #1151).
- Since the September ex-dividend dates nothing new has been mixed: for 2026-09-28 to 2026-11-12 the stored SPY, QQQ and IWM bars are at factor 1.0 on all 34 sessions, none off by 3 bp (read from production on 2026-11-13, db-query-tvjtp). An adjusted fetch and an as-traded fetch return the same prices for bars after the latest ex-dividend date. The next mixing happens on the first nightly after the next ex-dividend date, in December 2026, unless the requests change first.

## Non-goals

- No production write and no deploy in this change. The deploy is a close-out step on the owner's yes.
- No stored bar is rewritten. Months already stored on an adjusted basis stay as they are until the second spec's close-out.
- No change to the daily table, to `adjusted_close`, to which tickers or months any job fetches, or to how any reader uses intraday prices.
- The legacy scripts under `scripts/` are corrected, not deleted: `.env.example`, a disabled workflow, `lib/trading_analysis.py` and `tests/fixtures/timezone_boundary_baseline.json` still name them.

## Approaches considered

1. As-traded on every request, with a guard test (chosen). It matches the daily table, live quotes and strikes, and a refetch can never move a stored bar again.
2. Adjusted everywhere: every bar would have to be rewritten after every ex-dividend date, forever, and stored bars would stop matching live and daily prices.
3. As-traded for the three writers and leave the requests that store nothing: rejected by the owner. One rule with no exception is the only one a guard can hold.

## Design

All eight requests, at `main` 6e04eb53. "Request" is the line that names the endpoint; "adjusted" is the line that sets the parameter.

| File | Function | Request | adjusted today | After | What it feeds |
|---|---|---|---|---|---|
| `gcp/fetchers/fetch_alphavantage_intraday.py` | `fetch_month` | :124 | not sent, so adjusted | `'false'` | `market_data_intraday`: nightly, bulk backfill, `replace_month` |
| `gcp/fetchers/fetch_market_data.py` | `fetch_minute_bars`, and `fetch_minute_data` which calls it | :96 | :101 `'true'` unless the caller passes False; both default True (:78, :165) | `'false'` | `market_data_intraday` through `process_ticker` (:587) and `write_intraday_to_sql`; the premarket refresh (`fetch_premarket_refresh.py:200`) |
| `gcp/backfill_ticker.py` | `av_intraday_month` | :138 | :140 `"true"` | `"false"` | `market_data_intraday`: on-demand ticker backfill |
| `gcp/signal_monitor.py` | `fetch_latest_bar` | :346 | :350 `'true'` | `'false'` | the live trigger check (last 100 bars); stores nothing |
| `scripts/fetch_alphavantage_intraday.py` | `fetch_intraday_month` | :122 | :127 `'true'`, default True (:107) | `'false'` | CSV files, run by hand |
| `scripts/fetch_market_data.py` | `fetch_minute_data_for_date` | :149 | :154 `'true'` | `'false'` | run by hand |
| `platform/api/routers/live.py` | `_get_opening_history` | :403 | :404 `"false"` | unchanged | the opening-window response; stores nothing |
| `platform/api/routers/live.py` | `get_live_history` | :465 | not sent, so adjusted | `"false"` | `/api/live/history` (last 100 bars); stores nothing |

- The parameter is written as the literal `'false'` in every request, never an expression.
- `fetch_minute_bars` and `fetch_minute_data` keep their `adjusted` keyword so the EW strikes caller, which passes False, is untouched. Both default to False, and `fetch_minute_bars` raises `ValueError` when it is True.
- `scripts/fetch_alphavantage_intraday.fetch_intraday_month` loses its `adjusted` parameter. Nothing passes it.
- `gcp/fetchers/fetch_cross_asset.py` names the endpoint in two comments and makes no such request.
- `tests/gcp/test_intraday_as_traded.py`:
  - captures the request of each writer with a stubbed `requests.get`, including `fetch_minute_data` called the way `process_ticker` and the premarket refresh call it, with no `adjusted` argument;
  - walks every `*.py` under `gcp/`, `scripts/` and `platform/` with `ast`. Any dict literal that holds the constant `'TIME_SERIES_INTRADAY'` must hold `adjusted` as the string literal `'false'`. There is no exemption list. The guard's own cases prove it rejects a missing key, `'true'`, and an expression.
  - What the guard does not see: a request built without a dict literal (keyword arguments to `dict()`, a key assigned later, a URL string), and files outside those three directories. All eight requests are dict literals today and none exists elsewhere, so it holds for the code as it is.
- `tests/api/test_live_opening_window.py::test_opt_in_contract` asserted that the compact request carries no `adjusted` key. It now asserts `'false'`.
- Every ticker: the fix is in the request, so whatever ticker a job fetches is fetched as traded.

### Capacity

No change: the same AlphaVantage calls, rows and writes per run. One request parameter changes.

## Close-out (after the merge, on the owner's yes)

1. **Deploy** from `main`: the fetchers image (the nightly and bulk intraday jobs, the daily fetcher, the premarket refresh, the ticker backfill), the signal monitor and the API.
2. **Verify** after the first `av-intraday-nightly` on the new image: the job's execution is on the new image digest, and the SPY, QQQ and IWM sessions it wrote have a 1-min regular-hours high and low within 3 bp of the daily table's (the query of db-query-tvjtp). This proves the run wrote sound bars; while no ex-dividend date has passed it cannot tell an adjusted fetch from an as-traded one, so the request itself is proven by the tests above.
3. **After the next ex-dividend date** (December 2026): the same query over the month before that date still reads 1.0 after the nightly has refetched it. That is the behaviour this change exists for.

## Risks

- The live trigger check and `/api/live/history` change what they read. Their last 100 bars are identical on either basis except when the window spans an ex-dividend open: adjusted bars shade the prior session down by the dividend, as-traded bars show the gap that traded. After this change they agree with the stored bars, the daily table and the levels. The ex-dividend case is not replayed here.
- `signal_monitor.fetch_latest_bar` and the two `scripts/` requests have no request-capture test; the signal monitor suites stub the fetch out. Only the AST guard covers them.
- A reader that relied on adjusted intraday prices. None found: readers compare intraday bars with live, daily and strike prices. Covered by the unchanged suites.
- Until the second spec's rewrite runs, the table keeps its mixed months. This change stops new mixing; it repairs nothing already stored.
