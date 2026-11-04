---
feat_id: FEAT-OPTION-001
spec: docs/superpowers/specs/2026-10-29-feat-option-001-collector-source-declaration.md
branch: fix/feat-option-001-realtime-incident-1562
pr: 1565
status: ready
---

# Narrow scheduled collector isolation integration

Author-only integration authorized October29; root sole publisher. Starts from mergedMAIN5c488c4e, not unmerged#1565. Preserves #1565 CODE1-3 and LOCAL1-2; explicit unused CODE4 is not a reset. No new review triggered during this preparation.

## Task 1: preserved source integration
Spec: Files and source identity; done_when[0,1]. Apply exact isolation patch4ee7afa9 and immutable accepted transportaf238d07 from5cf08e29. Preserve API fetch and normalizer; no new tables/journal/cache. Retarget accepted collector tests to isolated module; record source hashes and adaptation.

- [x] Preserve exact source/dependency hashes and prove API function ASTs unchanged except main.
- [x] Integrate preserved patch and retarget collector tests.

## Task 2: deterministic entry and persistence validation
Spec: Contract and source window; done_when[0..3]. Exercise actual scheduled entry, threaded API path, classification/attempt cap, deadline, safe telemetry, session/DB admission and ACK controls. Keep historical9realPGreceipts separate from current-head tests; require actual new localPG verification before claiming complete admission. No provider or productionSQL.

- [x] Run current isolated collector/transport/entry tests:153passed.
- [x] Complete exact named spec controls and fresh actual localPostgreSQL acceptance: 174 collector/integration tests pass with separate-connection committed readback, five private negative controls fail; owned network-none fixture only. Current API/config tests:50passed/1existing skip. New collector consumer was added to the exact config inventory after a RED failure; runtime configuration remains MAIN-owned unchanged.

## Task 3: publication closure
Spec: Rollout/evidence; done_when[4]. Preserve lineage; no review allowance inferred from stage/PR change. Reconcile final MAIN before CODE4, actual source proof/docs/catalog/traceability, draft identity, currentSEC and requiredchecks. Parent controls admission and sole remote writes; GCPowner qualifies immutable job image/rollback. No deployment or restored historicalsnapshot claim.

- [ ] Complete own sourceproof/docs/catalog/traceability and actual PR metadata.
- [ ] Root reserves final review within inherited CODE4 grant and preserves prior history.

## Preserved publication lineage

This continues existing PR1565 by an ordinary MAIN-first two-parent merge retaining5cf08e29 ancestry. The isolated c40bba6c source remains preserved unchanged. Old task statements below are historical receipt, not current broad acceptance. LOCAL1/2 and CODE1/2/3 remain consumed. Existing explicitly approved runtime CODE4 is the complete independent final integrated-source review, alongside currentSEC and requiredchecks; no LOCAL3 or allowance reset is registered. Specification1636 aggregate4/CODE4 is separate and merged before this runtime.

```text
 owner-approved bounded second-review closeout
Spec: A10 typed source errors / REQ-OBS-001, plus AGENTS browser-proof API contract. Owner approved the exact TLS/API findings and ONE additional LOCAL fix/review pass plus ONE additional external CODE round in Sentinel_b12daf6284248191b5a58a25f79a9b3c (October26). This extends counts, never resets them: local fix/review1→2; external CODE2→3. No Ready transition or full A1–A15 certification follows from these fixes.
- [x] Reproduce P2 using actual urllib3 HTTPResponse translating synthetic ssl.SSLError; write failing process_ticker regression (json_error instead of transport_error), then add only explicit urllib3 SSL classification. Preserve one request, terminal failure, zero writes, redaction, cleanup and signal restoration.
- [x] Add three real HTTP API route tests using the actual fetcher with mocked provider and database tripwires for missing/null/non-list data. They pass the repaired source and fail all3 against the unchanged-main fetcher; no fetcher/route substitute or provider/SQL request. The standard local thread bridge requires the proven per-command local execution context; no persistent permission or settings change.
- [x] Directly affected schema/transport/API suites:123passed/1existing pandas warning in2.50seconds; no accepted349-test rerun.
- [x] Complete the ONE authorized additional LOCAL review of this exact batch: no introduced actionable finding, four independently executed new cases pass0.49s/0skip/0warning and fixed-limit source proof passes. Preserve both old external findings as first-review-missed and all predecessor/source history; local fix/review total is2, no further pass authorized.
- [ ] Refresh exact current-main source proof/audit under unchanged ceilings, then request only the ONE authorized external CODE round when authentication and normal publication gates permit. Broad contract and actual deployed/data/API/UI acceptance remain incomplete; seven future tables excluded. #1602's separately approved scheduled-entry acceptance does not activate its specification before MAIN.

```
