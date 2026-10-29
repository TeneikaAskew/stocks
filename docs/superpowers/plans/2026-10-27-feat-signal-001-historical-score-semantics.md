---
feat_id: FEAT-SIGNAL-001
spec: docs/superpowers/specs/2026-10-27-feat-signal-001-historical-score-semantics.md
branch: feature/feat-signal-001-historical-score-semantics
pr: 1620
status: ready
---

# Historical score semantics implementation plan

> For agentic workers: use superpowers:executing-plans. Existing sole backend SCORE author executes in the isolated existing worktree.

**Goal:** Explain native historical scores prospectively without changing financial decisions or reconstructing unsupported legacy components.

**Architecture:** Capture metadata in native producer branches; a pure helper validates a bounded versioned explanation. Preserve it in existing extra JSONB and expose it through real SQL/parquet reads. No new persistence or queries.

**Tech Stack:** Python, pandas, FastAPI/Pydantic, pytest; existing PostgreSQL JSONB.

**Spec:** docs/superpowers/specs/2026-10-27-feat-signal-001-historical-score-semantics.md (MAIN 377789974ab150c34fd7d5387921de0059d43769).

## Global constraints
- Financial counters, thresholds, admissions, numeric outputs and historical outcomes unchanged.
- Existing extras preserved; no tables/columns, SQL execution, replay, provider calls or backdating.
- Unknown legacy maxima/components remain null; explanation at most 2048 UTF-8 bytes.
- Existing two CODE-round allowance applies to this implementation PR, separately from the merged specification's exhausted two rounds. No review requested yet.
- Shared SignalRow/OpenAPI edits require root's serialized handoff. No overlap with earnings, options/news or gate owners.
- No MAIN landing during the parent's quota queue without announcement.

## Review focus
- Forged/unknown/oversized metadata must not become a qualified explanation (Task 1).
- Source provenance and strategy mismatch must remain unavailable, never invented (Tasks 1/3).
- Existing nested JSONB extras and reserved-key collisions must be preserved or explicitly refused (Task 2).
- Mixed legacy parquet/SQL and malformed metadata must preserve raw scores and row counts (Task 3).
- Native score six and invalid similar parameters must exercise the actual route without changing SQL or query counts (Task 3).

## Task 1: Native producer description and pure validation
Spec: Design sections 1/2/5; advances done_when[0].
- [x] Add tests/lib/test_signal_score_contract.py exercising actual momentum six/seven, negative controls, actual historical mean reversion and generic native bonus; install zero-external-I/O tripwires.
- [x] Run focused tests RED on prior source.
- [x] In lib/signals.py implement pure versioned descriptor/validator and producer-definition/provenance helpers; finite integral counts, unique known IDs, total consistency and 2KiB limit.
- [x] In lib/trading_analysis.py capture matched condition IDs in existing increment branches; preserve numeric decisions and label new momentum rows using actual seven-condition maximum.
- [x] Run focused tests GREEN; preserve source/input identity and refusal evidence.

## Task 2: Existing historical mapping and serializer boundary
Spec: Design sections 1/3/5; advances done_when[1].
- [x] Add RED tests in tests/scripts/test_run_historical_signals_strategy.py for native MR descriptors and extras/nested values/reserved collisions; stub only existing catalyst persistence seam.
- [x] Update scripts/run_historical_signals.py native MR output and mapping; merge into existing extra, preserve prior values; no calls added.
- [x] Test existing tests/gcp/test_historical_signals.py serializer and idempotency boundary without real SQL; edit gcp/historical_signals.py only on demonstrated necessity.
- [x] Run focused GREEN suites and record unchanged numeric outcomes.

## Task 3: Real API, typed responses and transport acceptance
Spec: Design sections 2/4/5; advances done_when[2]/[3].
- [x] Add tests/api/test_signal_score_contract.py using producer-derived records at real persistence seams; prove SQL/parquet, legacy unknown/invalid and exact similar score six acceptance RED.
- [x] Update platform/api/routers/signals.py to project existing fields and bounded metadata; retain query count/order/windows and remove only guessed score upper bound.
- [x] After serialized handoff, implement `platform/api/gcs_reader.py::download_parquet(..., optional_columns=None)` with exactly one existing byte read and optional-name intersection from the downloaded parquet schema; test old missing optional fields and unchanged ordinary callers in `tests/api/test_signal_score_contract.py`.
- [x] After serialized handoff, add owned typed models/SignalRow fields in platform/api/schemas.py and regenerate shared OpenAPI only with parent authorization.
- [x] Preserve the existing 50000-row contract on configured Uvicorn HTTP1 using route-only StreamingResponse after full SignalsResponse validation/serialization before headers; <=65536-byte chunks, no Content-Length, unchanged JSON/auth/error behavior. ASGI body parity and preheader refusal controls pass; no global middleware or deploy configuration changes. The earlier51.7MB non-streamed result is wire-RED against32MiB, separately from passing local RSS/time.
- [x] GREEN actual router serialization tests and invalid-param controls; no live data or provider requests.

## Task 4: Capacity, proof and normal delivery
Spec: Capacity and Files/serialized delivery; advances done_when[4].
- [x] Measure actual 50000-row serialization wall/memory/bytes within API 2GiB/300s; metadata bound 2KiB per row.
- [x] Update only FEAT-SIGNAL-001 catalog/traceability and declared CHARTS-06/DASHBOARD-05/SIGNALS-04 implementation-source notes, with truthful rollout-pending evidence.
- [x] Produce/verify committed-source proof with trusted MAIN, compare actual branch/main docs audits and run spec gate.
- [ ] Open one draft PR, record number, complete focused validation, then normal current-head reviews/checks under two-round limit.
- [ ] Root announces any normal eligible merge; actual staging/frontend receipts and rollback remain separate close-out, not inferred from local fixtures.

## Authorized aggregate 6 / CODE4 repair (October 29)

Owner approved one additional cycle at 00:33:55 UTC, with fresh SEC. Previous five aggregate cohorts and runtime CODE1–CODE3 remain consumed. Scope: concurrent response memory safety, catalog date, full PR-context validation, required checks. No additional review registered yet.

- [x] Reproduce concurrent allocations before repair.
- [x] Admit one signals response per configured single-worker process before any SQL/parquet allocation; explicitly return 503/Retry-After to competing requests and retain admission until streaming completes or disconnects.
- [x] Preserve 50000-row/typed wire contract and test concurrent maximum-size responses, query/validation failures and stream lifetime; focused API/producer suites 68 passed.
- [x] Correct only FEAT-SIGNAL-001 Last reviewed to current head date (October 29).
- [ ] Current MAIN integration, final source proof/audit and full PR-input gate.
- [ ] Authorized CODE4/current SEC, required checks and protected merge/deployment verification.
