---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-10-25-feat-data-001-news-log-source-proof.md
branch: fix/feat-data-001-news-log-delivery
pr: 1607
status: ready
---

# Credential safe news logger implementation plan

> For agentic workers: root remains sole writer, existing isolated worktree; execute with TDD and one independent final code review.

**Goal:** Remove secret-bearing warning arguments while preserving existing fetch behavior.
**Architecture:** Two constant warning messages in the actual fetcher; no sanitizer/classifier/retry or response-policy rewrite.
**Tech Stack:** Python logging, requests mocked, pytest real module.
**Spec:** docs/superpowers/specs/2026-10-25-feat-data-001-news-log-source-proof.md, approved successor MAIN b5bb0155; original three runtime criteria unchanged.

## Global constraints

Only the two unsafe warning sites and unused exception binding change. Endpoint/complete parameters/timeout30/one attempt and legacy feed/error semantics remain. No provider/SQL/key retrieval, schema, access or production changes. Typed-news producer1600 is separate; this repair does not validate error-as-empty behavior or native connector account binding. Existing349-test components untouched.

## Review focus

Exception args/traceback cannot retain fake keys; malicious Information objects must never stringify; complete outgoing request stays unchanged; nonempty Information+feed preserves current return; malformed nonmapping payload still fails rather than silently returning success.

## Task 1: logging boundary regressions and minimal repair

Spec: Design/Regression; done_when[0,1]. Files:gcp/fetchers/fetch_news_sentiment.py,tests/gcp/test_news_sentiment_log_redaction.py.
- [x] Actual-module tests mock dotenv/HTTP/DB. Dispatch,HTTP-status,JSON exceptions contain synthetic key/URL/header/response content; inspect LogRecord msg,args,exc_info,stack_info and rendered text. Include malicious Information scalar/dict/poison-stringifier, both empty and nonempty feeds.
- [x] Test exact endpoint/complete fake-key params/timeout30/one call and ordinary missing/null/empty/nonempty returns, malformed payload remains failure. Run named suite RED before editing fetcher; expect unsafe-log tests fail and behavior controls pass.
- [x] Replace caught-exception warning and Information warning with constants, remove unused exception binding; no other runtime behavior changes.
- [x] Run new suite plus existing news args/incremental/explode and phase2 news tests, all mocked. Expect green, record exact counts and preserve failure-versus-empty limitation. Commit only after staging plan/tests/source and normal commit gate/whitespace pass.

## Task 2: independent review and normal draft closeout

Spec: Regression/Capacity; done_when[2].
- [ ] One independent full-diff review; no repeat accepted suites. Draft implementation PR, own plan/product/traceability records and no-new docs audit; respect exact immutable source-note/provenance gate, no SITE/governance bypass.
- [ ] Current-head required Codex/CI before merge. Capture logger-hardened immutable image as later typed-news rollback target. Source-trigger effects reviewed; only intended job image updates, unchanged retries for logger-only rollout, no manual replay. No production outcome/persistence claims from unit tests or ACK.

## Preserved delivery lineage

Non-stacked replacement for draft #1605 from actual MAIN b5bb0155. The immutable old plan cannot rebind its spec. The runtime and test blobs exactly match reviewed89ad9523; the53-test author receipt and independent code review remain preserved component evidence, not a new-head run. Original drafts/branches/first-review/spent-effort history stay available and no review allowance resets. No accepted options component or unchanged suite is recreated/rerun. Current source-note proof, full no-new audit and final current-head required review/CI still apply. Initial logger deployment must not automatically roll back to the known unsafe warning behavior; capture a hardened image for later typed-news rollback, and stop unexpected functional/security regression for a safe forward correction or explicit owner decision.
