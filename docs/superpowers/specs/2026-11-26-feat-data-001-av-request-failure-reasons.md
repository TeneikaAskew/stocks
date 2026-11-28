---
feat_id: FEAT-DATA-001
req_ids: [REQ-SECRET-001]
issues: [2085]
canvases:
  - https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN
done_when:
  - "tests/gcp/test_av_request_failure_reasons.py drives each of the eight request-failure sites listed in Design through its real function, with requests.get stubbed to raise an HTTPError (status 503), a ConnectionError and a Timeout whose text carries a request URL holding a sentinel key; no captured LogRecord's formatted message, msg, args, exc_info or exc_text holds the sentinel, and each logged reason names the HTTP status or the exception class. The same tests fail on base f181f37f."
  - "The same tests assert each function's return value for those failures equals base behaviour (the empty frame, the empty dict, or FETCH_REQUEST_ERROR), and that the outgoing request parameters, timeout and attempt count are unchanged; the existing suites for the six modules and tests/gcp/test_compute_earnings_reactions*.py pass with no test deleted, skipped or loosened."
  - "tests/lib/test_api_client.py covers lib.api_client.request_failure_reason for an HTTPError with a response, a transport error with none, a JSON decode error, and a non-request exception, and compute_earnings_reactions._request_failure delegates to it with byte-identical output for a RequestException."
  - "02-FEATURE-CATALOG FEAT-DATA-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, docs_audit.py reports no finding over origin/main, and spec_gate.py --pr origin/main passes."
status: superseded
supersedes: null
---

# Name AlphaVantage request failures without the request URL

## Problem

`requests` puts the full request URL in the text of an `HTTPError` and of most transport errors, and every AlphaVantage request here carries `apikey` in its query string. Code that logs the exception object writes the key into Cloud Logging, where anyone with log read access on the project can read it.

This is happening now. A read-only Cloud Logging query on 2026-11-26 (`textPayload:"apikey="`, last 30 days) returned 13 entries, all from job `fetch-earnings-history`: 2 on 2026-11-24 (`fetch-earnings-history-ftvdv`) and 11 on 2026-11-26 (`fetch-earnings-history-58gjf`). Each reads `AV daily fetch failed for <TICKER>: 503 Server Error: ... for url: https://www.alphavantage.co/query?...&apikey=<the key>`. The line is `gcp/fetchers/fetch_market_data.py:261`. Issue #2085 records the earlier 2026-10-22 exposure from another job.

PR #2091 (open, specification only) covers `fetch_alphavantage_intraday.py`, the legacy `fetch_av_realtime_options.py` and the grid route. It does not cover the file leaking today or the other fetchers below.

#2047 already fixed this class for SPLITS: `compute_earnings_reactions._request_failure` names a failure by its HTTP status or exception class only. This spec applies that pattern everywhere else it is missing.

## Non-goals

- No change to the three files PR #2091 owns: `gcp/fetchers/fetch_alphavantage_intraday.py`, `gcp/fetchers/fetch_av_realtime_options.py`, `platform/api/routers/grid.py`.
- No change to request parameters, timeouts, retries, pacing, return values, `FETCH_*` reasons, or which failures are caught.
- Provider reply text (`Information`, `Note`, `Error Message`) stays as logged today. It is vendor prose, not the request URL, and it is #2091's concern for its files.
- No global logging filter or regex redaction. A key-pattern scrubber misses encoded or reshaped values; not stringifying the exception is the fix.
- No key rotation, log deletion, or log-access change. Those are owner actions under #2085.
- Scripts under `scripts/` that are not scheduled jobs are out of scope.

## Approaches considered

1. Regex-scrub `apikey=` from log text with a logging filter. Rejected: misses encoded forms and leaves exception objects with the URL in `args` and `exc_info`.
2. Wrap every AV call in a shared client that never raises request text. Rejected for now: it changes call shapes across six modules and their tests.
3. Log a fixed reason built from the HTTP status or exception class, through one shared helper. Chosen: smallest change, already proven by #2047, and it keeps operators' distinction between a 503, a timeout and a reset.

## Design

Add `request_failure_reason(exc) -> str` to `lib/api_client.py`, the existing HTTP client module:

- an exception whose `response` has a `status_code`: `request_failed: HTTP <status>`;
- any other `requests.RequestException`, a JSON decode error included: `request_failed: <ExceptionClass>`;
- any other exception, which can only come from parsing a reply already received: `<ExceptionClass>: <message>`, truncated to 160 characters.

`compute_earnings_reactions._request_failure` becomes a call to it. Its output for a `RequestException` is unchanged.

Replace the exception object with that reason at each of these sites (base `f181f37f`):

| File | Line | Function |
|---|---|---|
| `gcp/fetchers/fetch_market_data.py` | 159 | `fetch_minute_bars` |
| `gcp/fetchers/fetch_market_data.py` | 261 | `fetch_daily_from_av` |
| `gcp/fetchers/fetch_market_data.py` | 1056 | the daily-series backfill fetch |
| `gcp/fetchers/fetch_earnings_history.py` | 167 | AV `EARNINGS` fetch |
| `gcp/fetchers/fetch_insider_transactions.py` | 68 | `fetch_for_ticker` |
| `gcp/fetchers/fetch_av_historical_options.py` | 75 | `fetch_av_options` |
| `gcp/fetchers/fetch_top_movers.py` | 74 | `fetch_top_movers` |
| `gcp/fetchers/fetch_av_earnings_options_backfill.py` | 314, 324, 329 | the backfill driver's three request-failure logs |

The backfill row counts as one site with three log calls. No `exc_info`, `log.exception` or traceback is added at any site.

Before implementing, repeat the search on the implementation base for log calls that pass an exception from a block containing an AV request. A newly found site in these six files is added; one in another file is reported on #2085, not silently fixed.

## Capacity

- Volume: no new data. One short string per failed request, as today.
- Velocity: zero added vendor calls, SQL statements, retries, jobs or schedules.
- Wall-clock: unchanged. The helper is two attribute reads.
- Cost: zero added.

## Risks

- A test that asserted on the old log text breaks. The existing suites run unchanged; any assertion on the leaked text is rewritten to the new reason, never deleted.
- An operator loses the vendor's URL in the log. The ticker, function and status are still logged, which is what triage uses.
- A future site reintroduces the pattern. Not prevented mechanically by this spec; #2085 stays open for the remaining files and for rotation.

## Admission

The owner asked on 2026-11-26 to "Fix most urgent", in reply to a triage summary naming #2085 as the most urgent item. That instruction is recorded here as approval of this scope. It does not authorize key rotation, deployment outside the normal close-out, or any change to #2091.

## Close-out (after merge, not a done_when item)

1. Deploy the jobs that run these modules, respecting the `fetchers` deploy hold on #2060.
2. Re-run the read-only Cloud Logging query for `textPayload:"apikey="` after the next run of each deployed job and record the count on #2085.
3. Key rotation and log-access narrowing remain owner actions on #2085.
