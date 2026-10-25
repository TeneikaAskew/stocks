---
feat_id: FEAT-DATA-001
req_ids: [REQ-SECRET-001, REQ-REL-001, REQ-CAP-001]
issues: []
canvases:
  - https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN
done_when:
  - "tests/gcp/test_news_sentiment_log_redaction.py proves synthetic credentials, parameter dictionaries, request URLs, arbitrary exception text and provider Information content never reach warning messages, arguments or exception metadata in dispatch, HTTP-status and JSON failure cases."
  - "Mocked regressions prove unchanged endpoint, complete outgoing parameters including the fake key, timeout30, one HTTP attempt, exception-to-empty behavior, provider Information feed handling and ordinary successful/missing/null/empty feed returns."
  - "Directly affected existing NEWS_SENTIMENT tests, independent review, normal delivery records, documentation no-new audit and current-head required checks pass; no provider calls or actual leak/deployment claims are made."
status: approved
supersedes: null
---

# NEWS_SENTIMENT warning redaction

## Problem and scope

The user identified a source vulnerability in gcp/fetchers/fetch_news_sentiment.py at commit 7dbf31921e3ec492e332faed445fbd63dd47b019, lines78–89. Current fetched main is that exact commit. The exception warning logs the complete params dictionary, including apikey, and arbitrary exception text, which can contain a full request URL. The adjacent Information warning prints untrusted provider content. The file is blob5e8a60fc5adc69e69392e7dda2e95ff14fa8ff83 and is unchanged from previously inspected main641a93b96.

This is a code finding, not evidence that a real credential was disclosed. No secret-bearing logs or provider traffic were inspected. The native connector's premium-endpoint error bypasses this fetcher and is not attributed to these warnings.

FEAT-DATA-001 catalog row owns data-platform ingestion, storage and freshness. This new narrow specification is needed because the approved operation-metadata specification owns a different parser/terminal path and does not authorize this fetcher modification. Product-delivery Phase2 requires owner approval and approved-spec MAIN before implementation. The owner subsequently approved the bounded finish pass covering this written logger design, required Codex review, normal specification/implementation merges and scoped release on October 24, 2026 ("Do all the work needed"). This approval changes no acceptance item or logger scope and does not bypass specification MAIN or current-head checks. The fixture-owned six-minute CI implementation is now on MAIN at e7e74ccc (PR #1599). Normal current-head checks and required Codex reviews remain mandatory; this approval record does not waive them.

## Design

Change only the two unsafe warnings in _fetch. On the existing caught Exception, emit a constant NEWS_SENTIMENT request-failed warning without params, exception object, exception string/type, URL, response object, raw body, traceback or arbitrary headers. Remove the unused exception binding. On the existing Information branch, emit a constant provider-Information warning without its value. Keep warnings visible; do not remove failure signaling entirely. No shared sanitizer, classifier, dependency or additional telemetry is necessary for this minimal repair.

Leave requests.get endpoint, full params, timeout30, raise_for_status, JSON parsing, catch boundary, return values and ordering exactly as they are. Preserve an Information response's existing feed return behavior, including a nonempty feed. Preserve one physical request and no retries. Do not change parser semantics for non-mapping payloads or introduce new success/availability claims. The return-empty behavior is existing behavior preserved here, not certified as a complete ingestion-health design.

## Alternatives and risks

Masking only params.apikey is insufficient because raw exception URLs or provider Information may echo it. A general recursive sanitizer is larger and risks missed encodings or response-controlled content. Constant warnings on these two branches provide the smallest reliable boundary. Reduced textual failure detail is intentional; adding safe typed observability later needs its own reviewed scope. Tests must inspect LogRecord arguments and exception metadata as well as rendered text so deferred formatting cannot retain the fake key.

## Regression and delivery

An outside-repository acceptance probe extracts the exact unchanged _fetch AST and runs only synthetic mocked requests. Baseline result: four redaction failures and four preserved-behavior passes in0.08seconds. It performs no network, SQL, environment/credential access or persistence. This is source-level reproduction, not a full-module integration claim.

After approval and specification MAIN, create a unique ready implementation plan. Add the named regression suite against the actual imported repository function with HTTP/DB mocked. Establish the red tests, make the minimum logger edit, and prove green behavior plus the directly affected existing NEWS_SENTIMENT tests. Obtain independent diff/test review, update only this capability's required delivery records, publish a draft implementation PR and satisfy normal review/CI before any authorized rollout. Preserve accepted options source and evidence without rebuilding or rerunning unchanged suites.

## Capacity and non-goals

No new workload or request is introduced. Each existing fetch remains one request with timeout30 and unchanged feed cardinality; two warnings become constant-size. No tables, schema, storage, rate configuration, retries, schedules, credentials, IAM, security settings or provider calls change. No key rotation, actual-log inspection, native-connector change, Gamma/strategy change or broader vulnerability inventory is included. There is no claim of proven production exposure, deployed source equivalence or incident closure. Canvas check is report-only through normal closeout; no diagram topology changes.
