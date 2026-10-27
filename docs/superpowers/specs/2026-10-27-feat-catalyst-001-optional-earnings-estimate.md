---
feat_id: FEAT-CATALYST-001
req_ids: [REQ-DATA-001, REQ-REL-001]
issues: [1269]
canvases: []
site_source_notes: [CATALYSTS-04]
status: draft
supersedes: null
done_when:
  - "tests/api/test_catalyst_earnings_estimate_numbers.py exercises the real _db_catalyst_events adapter and actual /api/catalysts/events response: pandas float64 NULL/NaN, nullable pd.NA, nonfinite numbers/strings and malformed optional estimates retain the event without emitting a numeric suffix or raising, while finite zero/negative/positive and supported numeric strings retain their exact existing two-decimal formatting; negative controls fail unchanged MAIN. All real provider/SQL boundaries are forbidden in these tests."
  - "A local-PostgreSQL fixture reads a nullable numeric earnings_calendar projection through the actual pandas/SQL query path before invoking the adapter; NULL plus a valid finite sibling reproduces the old NaN title and passes the repaired contract, without new production tables, migrations or writes."
  - "Tests preserve source, ticker, event/date/earnings-time identity, event counts, dedup and unrelated news/SEC/insider results; invalid optional estimates never become zero and legitimate finite values are not clamped. No changes to score, source clocks, financial formulas or API retrieval/refresh behavior."
  - "Normal unique delivery plan, own product/source-note records, matched current-MAIN no-new audit, bounded committed source verification, independent review and required current-head CODE/checks pass before protected source merge. Post-merge exact deployed revision and parent-owned rendered checks are recorded separately, not prematurely certified by local tests."
---

# Nullable finite earnings estimates at the shared catalyst API boundary

## Problem and evidence chain

Source d78201b0846c1fa1cc2f80b0fe1d106661a2eb2b (unchanged formatter from16757231). Existing fetch-earnings-calendar job runs scripts/fetch_earnings_calendar.py; its optional EPS feeds public.earnings_calendar.eps_estimate. The producer's persist adapter scrubs NaN to SQL NULL. gcp.database.query_to_dataframe uses pandas.read_sql, whose numeric nullable result can again materialize NULL as float NaN. platform/api/routers/catalysts.py::_db_catalyst_events currently checks only None/empty then float(est):.2f. A valid missing EPS can therefore become the semantic title `est nan`, even if the provider returned a legitimate blank and SQL correctly stores NULL. This is a numeric missing-value contract defect in the shared API adapter, not evidence of a vendor/network fault or corrupt production rows.

The actual extracted adapter reproduced7 negative cases and5 existing-correct controls offline, including mixed NULL/finite dtype, pd.NA TypeError and malformed ValueError. It preserves the finite sibling in the mixed case. The existing CatalystsPage.eventTitle renders this supplied title verbatim; no frontend string suppression is proposed. The parent observed624 such titles in current rendered data, but exact deployed image/source and stored offending EPS remain to be proved through existing legitimate evidence. Source reproduction is not deployed-equivalence proof.

## Approaches considered

1. Frontend string suppression: rejected; leaves incorrect API semantics, nullable crashes and other API callers unchanged.
2. Producer-only cleanup: rejected; SQLNULL can legitimately rematerialize as pandasNaN.
3. Finite nullable producer/API contract with shared literal conformance vectors: selected; preserves missingness and valid financial values at both existing boundaries.

## Smallest correct shared-layer repair

Coordinate two existing boundaries under ONE finite nullable scalar contract: calendar producer scripts/fetch_earnings_calendar.py::_safe_num and platform/api/routers/catalysts.py's earnings estimate normalization/formatting, plus conformance tests. The API consumer must tolerate legitimate SQL NULL regardless of producer validation; producer validation alone cannot prevent pandas NULL→NaN on read. Establish a small explicit optional finite numeric conversion before comparison/formatting: reject missing sentinels, booleans, malformed scalars and nonfinite float/Decimal/string representations; return unavailable rather than a default. Preserve supported finite numeric/string conversion, zero, negative EPS and existing formatting/rounding. Do not rely on truthiness, string replacement in a completed title, or pandas dtype alone. Catch only expected numeric conversion errors; do not swallow source/query failures in a new generic exception handler. Keep an event with unavailable optional EPS and omit its estimate suffix, matching the existing legitimate None behavior. Preserve all other event fields, date filtering, source identities and function call/query shape.

This fixes all callers of the existing shared DB catalyst adapter. No parallel pipeline, producer rewrite, schema field or data correction is needed to handle legitimate stored NULL. The producer `_safe_num` currently rejects NaN but admits infinity. Under an explicit serialized calendar-owner handoff, tighten that existing scalar helper to the SAME finite nullable contract with shared producer/API golden inputs: empty/None/pd.NA/NaN/±infinity/malformed/bool→None, valid zero/negative/positive unchanged. Preserve every legitimate finite field and no raw/adjusted/financial formula change. It is not proof of observed production infinity. If that file is actively calendar-owned, its owner makes the change or supplies a serialized handoff; do not copy the script, race edits, or introduce a competing COMMON helper. No additional calendar/source retrieval rewrite is included.

## Ownership and sequencing

Options/news owner proposes sole ownership of the narrow catalysts.py earnings-normalization block and new test file. Existing STRAT/frontend owner retains Solyra DashboardPage/useMarketData and score denominator; valid composite6 is never clamped. Existing calendar owner retains scripts/fetch_earnings_calendar.py and its producer `_safe_num`; producer correction is delegated to that same owner or requires an explicit serialized handoff, while this sole owner handles the nonoverlapping API adapter/test. No edit to that producer file has occurred. Before implementation confirm no overlapping actual catalysts.py writer with the event-bound earnings owner; share exact diff/section. Product/source-note edits are serialized with that owner, not concurrent whole-file rewrites.

This is a new minimal written design under already-authorized functional intent, not an expansion of logger1588, typed-news1600, availability1601, options1602 or freshness1580. Immutable broad CAT delivery remains unchanged and unfulfilled items are not marked done. Normal written design approval and actual specification MAIN precede runtime implementation. This packet is a candidate, not a silently approved specification.

## Validation and release

Baseline red matrix plus positive controls; local PG SQL-NULL to pandas to actual adapter; actual API response with provider/cache-fetch seams forbidden, not a synthetic reimplementation. Independent tests/review and normal gates. The existing API source path is the target; inspect automatic migration effects, exact immutable API image/current rollback and current metadata preflight before release. The producer/API finite guards require no business-data mutation/backfill; do not rewrite old NULLs or relabel legacy unknown values. A targeted real future writer receipt is necessary to certify producer qualification, and an observed exact deployed API image is necessary to certify the consumer fix. Postdeployment parent-owned site QA verifies titles on existing legitimately served data; do not trigger refresh/provider or new SQL solely to obtain a green screenshot. If deployed source or offending persisted rows are not available, preserve the exact remaining qualification.

Capacity: same existing queries/rows and O(1) scalar normalization per existing earnings row, no additional SQL/provider call, no new schedule/retry or storage, no migration.

## Required conformance and evidence

Producer normalization and API fixtures share literal expected inputs/results, not expectations computed by the helper under test. Require SQLNULL→pandasNaN and nullable pd.NA behavior, malformed/infinite estimates, positive finite numbers, legitimate0/negative EPS and finite numeric strings. Feed the normalized producer frame through mocked existing persistence and separately real local PostgreSQL query to prove end-to-end nullable values without runtime provider access. Keep malformed optional values unavailable, retaining ticker/date/source/as-of and successful siblings. A moving-MAIN OpenAPI schema or mocked browser pass alone is not freshness/basis/deployment proof. Pin producer/API versions and later bounded immutable-image/writer receipts.

## Risks and exclusions

Do not convert unknown EPS to0, drop the entire event, lose successful sibling sources or hide query failures. Do not change model/STRAT/Gamma math, event cutoffs, dashboard labels, chart cache policy, source clocks, ticker/date identity or producer schedule. Booleans are not valid EPS; negative finite values are valid. Very large finite values remain numeric under existing format, not arbitrary thresholds. Normal production release protects source/image identity; removing title text alone is not proof of ingestion freshness or provider correctness.
