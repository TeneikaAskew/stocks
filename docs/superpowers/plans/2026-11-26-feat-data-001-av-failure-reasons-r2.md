---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-11-26-feat-data-001-av-request-failure-reasons-r2.md
branch: fix/feat-data-001-av-failure-reasons-r2
pr: 2150
status: ready
---

# Name AlphaVantage request failures without the URL (r2): implementation plan

Re-cut of #2148, whose plan stayed bound to the superseded r1 spec in the gate's commit mode (#1896). Code and tests are #2148's, unchanged.

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

## Task 1: guard tests first, red on base
Spec: § Design, the site table. Advances done_when[0] and done_when[1].
- [x] Write `tests/gcp/test_av_request_failure_reasons.py`: each site driven through its real function with a real `requests.Response` 503, a `ConnectionError` and a `Timeout` whose text carries a sentinel key; every LogRecord's message, msg, args, exc_info, exc_text and stack_info checked; return value, request params, timeout and attempt count pinned
- [x] Run on base `f181f37f` (expect FAIL): 29 failed, 1 passed (the SPLITS control, unchanged by design)

## Task 2: shared helper
Spec: § Design, `request_failure_reason`. Advances done_when[2].
- [x] Add `request_failure_reason` to `lib/api_client.py`
- [x] Make `compute_earnings_reactions._request_failure` delegate to it
- [x] Helper and SPLITS-control tests pass

## Task 3: replace the exception object at each site
Spec: § Design, the site table. Advances done_when[0].
- [x] `fetch_market_data.py` 159, 261, 1056; `fetch_earnings_history.py` 167; `fetch_insider_transactions.py` 68; `fetch_av_historical_options.py` 75; `fetch_top_movers.py` 74; `fetch_av_earnings_options_backfill.py` 314, 324, 329
- [x] Repeat the site search on the implementation base: no further site in these six files
- [x] Guard tests pass on head: 30 passed

## Task 4: no regression
Spec: § Risks. Advances done_when[1].
- [x] Every existing test file importing a touched module, run on head and on base: the same 16 environment failures on both, none on head only

## Task 5: SITE note and source record
Spec: front matter `site_source_notes`. Advances done_when[3].
- [ ] Update the FEAT-DATA-001 ADMIN-06 note: new source identity and prose first, prior prose under `Earlier:`
- [ ] Produce `docs/review-evidence/site-source-snapshot.json` from the committed head, commit it, verify against origin/main

## Task 6: close
Spec: § Done when. Closes done_when[4].
- [ ] Update the FEAT-DATA-001 record (Status, Last reviewed)
- [ ] Add this PR to 12-PR-ISSUE-TRACEABILITY
- [ ] Docs audit reports nothing new over origin/main
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`
