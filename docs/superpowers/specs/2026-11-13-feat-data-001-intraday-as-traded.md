---
feat_id: FEAT-DATA-001
req_ids: [REQ-DATA-001, REQ-DATA-003]
issues: []
canvases: []
done_when:
  - "tests/gcp/test_intraday_as_traded.py passes: the AlphaVantage TIME_SERIES_INTRADAY request built by fetch_alphavantage_intraday.fetch_month, fetch_market_data.fetch_minute_bars called without an adjusted argument, and backfill_ticker.av_intraday_month each carries adjusted=false"
  - "tests/gcp/test_intraday_as_traded.py::test_every_intraday_writer_requests_as_traded passes: every module under gcp/ that builds a TIME_SERIES_INTRADAY request and writes market_data_intraday sets adjusted to false, found by AST over gcp/, so a new writer without it fails"
  - "make test passes on the PR head, with the existing tests/gcp/test_evaluate_ew_strikes.py, tests/gcp/test_intraday_replace_months.py and tests/gcp/test_intraday_writers_utc.py unchanged"
  - "02-FEATURE-CATALOG FEAT-DATA-001 record shows Status and Last reviewed for this PR, and 12-PR-ISSUE-TRACEABILITY lists it"
status: draft
supersedes: null
---

# market_data_intraday stores as-traded prices

## Problem
`market_data_intraday` holds two price bases, and the nightly refetch keeps
making more of the second one.

- AlphaVantage's TIME_SERIES_INTRADAY returns split- and dividend-adjusted
  prices unless the request says `adjusted=false`. The adjustment is
  computed as of the call: every bar before an ex-dividend date is scaled
  down once the date passes.
- `gcp/fetchers/fetch_alphavantage_intraday.fetch_month` does not set the
  parameter, `fetch_market_data.fetch_minute_bars` defaults it to true, and
  `backfill_ticker.av_intraday_month` sets it to true. All three upsert
  into `market_data_intraday`.
- So every stored bar sits at the basis of its last fetch. Measured on
  2026-11-13 against AV's `adjusted=false` series, bar by bar, same volumes:
  SPY 2025-04 and 2025-05 are stored at 0.99430 of the traded price (the
  June and September 2025 dividends), SPY 2025-06 steps from 0.99430 to
  0.99725 at the June ex-dividend date, QQQ 2025-01 is at 0.99629, and
  SPY, QQQ and IWM 2025-11 are at exactly 1.00000. Those months were
  fetched in mid-November 2025, between the September and December
  ex-dividend dates (2025-11 ends at 11-14 in all three tickers), and
  bulk-loaded into Cloud SQL on 2026-02-23.
- Rows written by the nightly carry the basis of their last refetch. SPY
  2026-08-31 15:59 ET is 765.053 in the table and 766.95 as traded (ratio
  0.99753, the September 2026 dividend). `av-intraday-nightly` refetches
  the previous month with `--force` every night, so a month is rewritten
  at a new basis whenever an ex-dividend date falls inside that window.
- The daily table's open, high, low and close are as-traded
  (TIME_SERIES_DAILY_ADJUSTED, with `adjusted_close` in its own column), and
  live quotes, strikes and trade plans are as-traded (`platform/api/routers/live.py`
  and `gcp/fetchers/evaluate_ew_strikes.py` already ask for `adjusted=false`,
  #1151). A 1-min bar stored at an adjusted price is up to about 1% below
  the price it traded at for SPY, and steps at every month boundary where
  two bases meet.
- A backfill of the 2025-11-17..2025-12-31 gap on today's code would
  write those two months 1.07% low for SPY and overwrite the as-traded
  rows of 2025-11-03..11-14 with adjusted ones.

## Non-goals
- No data is written. Re-basing months already stored at an adjusted
  basis, and backfilling the missing sessions, are separate production
  runs that wait for the owner's yes on their exact scope (the PR body
  carries the measured plan).
- The live trigger check in `signal_monitor` keeps its request: it reads
  only today's bars, which no dividend has adjusted yet, and stores none.
- No change to the daily table, to `adjusted_close`, or to how any reader
  uses intraday prices.
- No change to which months the nightly fetches, or to the
  `--replace-months` / `--verify-months` migration.

## Approaches considered
1. As-traded everywhere (chosen): every writer requests `adjusted=false`.
   It matches the daily OHLC, live quotes and strikes, and a refetch can
   never move a stored bar again.
2. Adjusted everywhere: every bar would have to be rewritten after every
   ex-dividend date, for every ticker, forever, and stored bars would no
   longer compare with live or daily prices.
3. Store both: a second set of columns doubles the table's price data for
   one consumer that does not exist.

## Design
- `fetch_alphavantage_intraday.fetch_month` adds `'adjusted': 'false'` to
  its request. That one function serves the nightly, the bulk backfill and
  `replace_month`.
- `fetch_market_data.fetch_minute_bars` and `fetch_minute_data` change the
  default of `adjusted` to False. Every caller then gets as-traded bars
  (`write_intraday_to_sql`, `fetch_premarket_refresh`); the EW strikes
  caller already passes False.
- `backfill_ticker.av_intraday_month` sends `"adjusted": "false"`.
- A new test file `tests/gcp/test_intraday_as_traded.py` captures the
  request parameters of each of the three functions with a stubbed
  `requests.get`, and walks every `gcp/**/*.py` with `ast` for a dict
  holding `'function': 'TIME_SERIES_INTRADAY'`. Each one must carry an
  `adjusted` key whose value is the literal `'false'`, or an expression
  on a parameter whose default is False (the `fetch_minute_bars` form).
  Two requests that never feed the table are listed with their reason:
  `signal_monitor.fetch_latest_bar` (today's last 100 bars for the live
  trigger check, not stored) and `fetch_cross_asset` (VIX, its own table).
- Capacity: no change. The same AV calls, rows and writes per run; one
  extra query-string parameter.

## Risks
- A consumer that relied on adjusted intraday prices. None found: readers
  compare intraday bars with live, daily OHLC and strike prices, all
  as-traded. Covered by the unchanged suites in done_when item 3.
- Until the re-basing run, the table keeps its mixed months. The nightly
  re-bases the previous month as it refetches it, so new mixing stops on
  the first night after the deploy.
