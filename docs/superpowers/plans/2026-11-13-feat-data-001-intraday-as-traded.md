---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-11-13-feat-data-001-intraday-as-traded.md
branch: fix/feat-data-001-intraday-as-traded
pr: null
status: ready
---

# Every AlphaVantage 1-min request asks for as-traded prices implementation plan

> For agentic workers: use superpowers:executing-plans; one writer, four small tasks.
> Every task cites a spec section and the done_when item it advances.

**Goal:** Every TIME_SERIES_INTRADAY request in the repo sends `adjusted=false`, and a test fails any request that does not.
**Architecture:** Change the request literal at each of the seven sites that ask for adjusted prices. No new module, no new job, no schema change. One new test file holds the request-capture tests and an AST guard over `gcp/`, `scripts/` and `platform/`.
**Tech Stack:** Python, pytest, `ast`.
**Spec:** docs/superpowers/specs/2026-11-13-feat-data-001-intraday-as-traded.md

## Global constraints

- Base: `main` 6e04eb53. The spec's line numbers are for that commit.
- `adjusted` is the string literal `'false'` in every request dict, never an expression.
- `fetch_minute_bars` and `fetch_minute_data` keep the `adjusted` keyword (the EW strikes caller passes False). Both default to False; `fetch_minute_bars` raises `ValueError` when it is True.
- `tests/gcp/test_evaluate_ew_strikes.py`, `tests/gcp/test_intraday_replace_months.py` and `tests/gcp/test_intraday_writers_utc.py` are not edited.
- No production write, no deploy. The deploy is the spec's close-out, on the owner's yes.
- No trading cost anywhere.

## Review focus

- A caller that goes through `fetch_minute_data` (the daily fetcher's `process_ticker`, the premarket refresh) must send `false` without passing `adjusted`: the wrapper has its own default.
- A request added later with no `adjusted` key, with `'true'`, or with an expression must fail the guard.
- The guard must find a request nested in a function, a method or a class, in a single-quoted or double-quoted dict.
- The guard must not be fooled by a dict that sets `adjusted` twice (Python keeps the last), and must flag a URL string that spells the query out. It parses every file with `SyntaxWarning` ignored, so another file's invalid escape cannot fail it.
- The compact `/api/live/history` request and the opening-window request must both send `false`; only the first changes.
- `scripts/fetch_alphavantage_intraday.fetch_intraday_month` loses its `adjusted` parameter: no caller may still pass it.

## Task 1: Request-capture tests and the guard
Spec: Design, "tests/gcp/test_intraday_as_traded.py". Advances done_when[0] and done_when[1].
- [ ] Create `tests/gcp/test_intraday_as_traded.py` with:
  - `test_nightly_and_backfill_month_fetch_requests_as_traded`: stub `requests.get`, call `fetch_alphavantage_intraday.fetch_month`, assert `params['adjusted'] == 'false'`.
  - `test_daily_fetcher_requests_as_traded_through_both_functions`: call `fetch_market_data.fetch_minute_bars` and `fetch_market_data.fetch_minute_data` with no `adjusted` argument, assert `'false'` on each captured request.
  - `test_asking_for_adjusted_minute_bars_is_refused`: `fetch_minute_bars(..., adjusted=True)` raises `ValueError`.
  - `test_backfill_ticker_month_fetch_requests_as_traded`: `backfill_ticker.av_intraday_month`, assert `'false'`.
  - `test_every_intraday_request_in_the_repo_asks_for_as_traded`: walk every `*.py` under `gcp/`, `scripts/`, `platform/` with `ast`; every use of the constant `'TIME_SERIES_INTRADAY'` outside a docstring must sit in an `ast.Dict` that holds key `'adjusted'` with the constant value `'false'`; the failure message lists `file:line` of each offender; assert the seven files of the spec's table are all found and at least 8 requests in total, so an empty walk cannot pass.
  - `test_the_guard_tells_as_traded_from_everything_else`, parametrized over nine source snippets: a dict with literal `'false'` (0 bad), a missing key (1), `'true'` (1), an `if` expression inside a function (1), the constant used outside a dict to build a URL (1), an f-string URL that spells `function=TIME_SERIES_INTRADAY` (1), a dict that sets `adjusted` twice (1), the name in a docstring and a comment only (0), a `TIME_SERIES_DAILY_ADJUSTED` request (0).
- [ ] Run: `python3 -m pytest tests/gcp/test_intraday_as_traded.py -q` (expect 5 failures on `main`: the three writers, the wrapper, the guard).

## Task 2: Change the seven requests
Spec: Design, the table. Advances done_when[0] and done_when[1].
- [ ] `gcp/fetchers/fetch_alphavantage_intraday.py` `fetch_month`: add `'adjusted': 'false'` to the params dict.
- [ ] `gcp/fetchers/fetch_market_data.py`: `fetch_minute_bars(..., *, adjusted: bool = False)` raises `ValueError("1-min bars are fetched as traded only; adjusted=True is not supported")` when True and sends the literal `'false'`; `fetch_minute_data(..., *, adjusted: bool = False)`.
- [ ] `gcp/backfill_ticker.py` `av_intraday_month`: `"adjusted": "false"`.
- [ ] `gcp/signal_monitor.py` `fetch_latest_bar`: `'adjusted': 'false'`.
- [ ] `scripts/fetch_alphavantage_intraday.py`: `fetch_intraday_month(symbol, month, interval='1min', outputsize='full')`, literal `'false'`, docstring line for `adjusted` removed.
- [ ] `scripts/fetch_market_data.py` `fetch_minute_data_for_date`: `'adjusted': 'false'`.
- [ ] `platform/api/routers/live.py` `get_live_history`: add `"adjusted": "false"` to the compact request.
- [ ] Run: `python3 -m pytest tests/gcp/test_intraday_as_traded.py -q` (expect 14 passed).
- [ ] Commit: `fix(data): request as-traded 1-min bars from AlphaVantage everywhere`

## Task 3: The live-history contract test
Spec: Design, last test bullet. Advances done_when[2] and done_when[3].
- [ ] In `tests/api/test_live_opening_window.py::test_opt_in_contract` replace `assert 'adjusted' not in client.calls[0]` with `assert client.calls[0]['adjusted']=='false'`.
- [ ] Run: `python3 -m pytest tests/api/test_live_opening_window.py tests/gcp/test_intraday_as_traded.py -q` (expect 64 passed).
- [ ] Run: `python3 -m pytest tests/gcp/test_evaluate_ew_strikes.py tests/gcp/test_intraday_replace_months.py tests/gcp/test_intraday_writers_utc.py -q` (expect all pass, files unedited: `git diff --stat origin/main -- <those three>` is empty).
- [ ] Run: `make test` (expect no failure that `origin/main` does not have).
- [ ] Commit: `test(api): require as-traded on the compact live-history request`

## Task 4: close
Spec: Done when. Closes done_when[4].
- [ ] Update the FEAT-DATA-001 record in `docs/product/02-FEATURE-CATALOG.md` (Status, Last reviewed).
- [ ] Add this PR to `docs/product/12-PR-ISSUE-TRACEABILITY.md` under FEAT-DATA-001.
- [ ] Set `pr:` in this plan to the PR's number.
- [ ] Site traceability (spec: Design, last bullet; the spec declares `site_source_notes: [LIVE-03]`): with the code committed, run `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json` as preflight to read the source identity; add the row `| FEAT-DATA-001 | LIVE-03 | source_identity_sha256=<that hash>; <backend source and tests, no deployment claim> |` to `## Implementation-source notes` in `docs/product/03-SITE-TRACEABILITY.md`, in the table's sort order, changing no other byte; commit; run `produce` again for the final body; commit the sidecar.
- [ ] Run: `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` (expect the identity to match).
- [ ] Docs audit reports nothing new over `origin/main` (`python3 scripts/maintenance/docs_audit.py`).
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`

## After the merge (not tasks; each on the owner's yes)

The spec's close-out: deploy the fetchers image, the signal monitor and the API from `main`; verify the first `av-intraday-nightly` on the new image; check again after the December 2026 ex-dividend date.
