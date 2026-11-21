---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-10-13-feat-data-001-av-operation-telemetry.md
branch: fix/feat-data-001-av-operation-telemetry
pr: null
status: ready
---

# Shared AV Operation Telemetry Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans task by task. Root owns publication and the final fresh-context review; no child agents.

**Goal:** Add explicit nullable operation labels to existing terminal telemetry without changing financial evidence or inferring authenticated origin.

**Architecture:** One standalone common schema/parser/helper contract. Existing default callers retain their original twelve-column application INSERT; explicitly typed metadata uses fourteen columns in the same application INSERT. Actual main common CODE precedes every producer adoption; this branch imports no unmerged IND worker or CAT producer.

**Tech Stack:** Python stdlib, existing SQLAlchemy/pg8000 helper, PostgreSQL, pytest and existing delivery tools.

**Spec:** docs/superpowers/specs/2026-10-13-feat-data-001-av-operation-telemetry.md, approved main544f32b, immutable SHA25676a9e6aa019081fc196ab441d95b226cc59a485f59ef58026cff0860a8fdd99f. Fresh trusted BASE3d8419194daf0c10d4f4df97974586b36071145a, never stacked on IND/CAT/DATA/OPTION CODE.

## Intake and exact ownership

CHANGE under FEAT-DATA-001. Catalog row: `Data platform | Ingestion, storage, freshness | fetcher jobs | Production but needs remediation`. Requirements: REQ-DATA-003, REQ-OBS-001, REQ-SECRET-001, REQ-CAP-001, REQ-CAP-002, REQ-GOV-004. Spec lists no issues or canvases; do not invent a closure or refresh obligation. Actual legacy caller paths are both terminal branches in gcp/fetchers/backfill_daily_indicators.py::main; actual current main has no CAT Run/direct terminal interface and no optional-timeout IND worker.

Owned: gcp/schema.sql job_runs two columns/constraint upgrade only; new gcp/av_operation_metadata.py; gcp/database.py record_job_run optional operation_metadata/fixed INSERT/controlled metadata-mode error only; tests/gcp/test_av_operation_metadata.py; tests/integration/test_av_operation_telemetry.py; own runbook/acceptance/catalog/traceability and actually authorized delivery artifacts. No execute_sql/default timeout/after_replace/financial writer/OPS algorithm edits.

## Global Constraints

- Preserve original job_runs PK, existing rows, raw NOTE bytes, execution/variant/status/counts and actual timestamps. Nullable TEXT fields have no guessed default/backfill.
- Generic both-env-absent returns None/legacy unknown. Only IND's independently owned future caller may explicitly use its approved manual-intent exception after actual common CODE main; common never infers origin.
- Exact canonical ASCII scheduler resource: projects/[A-Za-z0-9][A-Za-z0-9.:-]*/locations/[a-z][a-z0-9-]*/jobs/[A-Za-z0-9_-]+, full-match, <=2048bytes and <=500job bytes. Kind precheck<=16characters/resource precheck<=2048characters before encoding/regex; no strip/coercion/truncation.
- Metadata<=4KiB per actual terminal row, inside each caller's existing byte/runtime/SQL allowance. Zero additional application SQL queries, source/control API calls, table/index/job/Scheduler/invocation; measure existing driver/connection/dialect/TX operations rather than claiming one total cold RT or bounded default latency.
- Baseline record_job_run/execute_sql remains default-unbounded; this branch neither imports nor certifies IND's unmerged12/14 bounded worker. Actual IND adoption follows common CODE main, then its own tests/main.
- Four literal done_when items remain unticked until actual evidence. Real PostgreSQL fixtures fail on missing DB/schema; no skipped/mock persistence proof.
- Actual policy1461/verifier1462/Counter1463 compatible CODE main precedes final source-note/render/no-new readiness. Their SPEC main alone is insufficient; no bootstrap reuse, gate waiver, historical marker stamp or premature deployed/global health.

## Review Focus

- Partial pre-existing columns/wrong type/default/NOTNULL/generated/constraint/data must refuse atomically, preserving old definitions and rows; compatible partial/repeated upgrades work.
- Explicitly present empty scheduler with missing kind is invalid; absent keys differ from None/wrong types; parser reads only two keys and never echoes secrets.
- Forged typed objects cannot bypass value validation. Database error or zero typed INSERT cannot fall through to a successful twelve-column retry.
- NOTE quotes/backslashes/newlines/Unicode and source identity/counts survive actual database writes byte-exact; source metadata does not become a financial manifest.
- Cold dialect/connection/TX work and storage overhead remain visible; default API latency and runtime permissions are not certified by a local fast fixture.

## Task 1: Nullable compatible schema upgrade

Spec: Exact fields and legacy compatibility; Capacity and verification. Advances done_when[0].
Files: gcp/schema.sql job_runs section only; tests/integration/test_av_operation_telemetry.py.
Interfaces: nullable invocation_kind TEXT/scheduler_job TEXT and named ck_job_runs_av_operation_metadata; unknown NULL/NULL, manual/NULL, scheduled/canonical resource only.

- [ ] RED real PG original legacy schema/populated rows, absent/compatible partial/repeated migration and invalid pairing/resource fixtures; incompatible type/default/NOTNULL/generated/permissive-or-mismatched constraint/invalid-data upgrades must leave ALL old evidence unchanged.
- [ ] Add the owned idempotent transactional validation/upgrade: inspect pg_attribute/pg_type/pg_attrdef/pg_constraint before mutation, exact pair CASE avoiding SQLNULL pass-through, same ASCII/dot-colon/byte/component grammar as parser. No guessed evidence rewrite, new table or index.
- [ ] GREEN the actual migration fixtures, including independent unchanged row/PK/note/definition snapshots and both positive/negative boundary controls. Measure physical tuple/index/TOAST/WAL effects honestly; permanent addition is <=N*4KiB logical, not zero storage.
- [ ] Run spec gate --commit, commit this independently testable schema component and ledger exact evidence. Schema/producer/deployment readiness remains separate.

## Task 2: Stdlib immutable safe parser

Spec: Literal common parser and writer API. Advances done_when[1].
Files: new gcp/av_operation_metadata.py; tests/gcp/test_av_operation_metadata.py.
Interfaces: frozen AVOperationMetadata(invocation_kind,scheduler_job), AVOperationMetadataError and read_av_operation_metadata(env=None)->AVOperationMetadata|None.

- [ ] RED actual import/API, valid absence/manual/scheduled/ordinary/numeric/domain-scoped project controls; partial/empty/mismatched/whitespace/control/non-ASCII/type/oversize/job>500 refusal and sentinel non-disclosure. An injected mapping must prove only the two AV keys are read, no environment copy/iteration.
- [ ] Implement immutable constructor/value validation and bounded parser. Generic absent remains None; manual absent/literal-empty job becomes NULL; scheduled requires exact full resource. No CLOUD_RUN_EXECUTION inference or caller default-manual enrichment.
- [ ] GREEN full boundary/constructor/refusal controls using actual parser and fixed messages, including newline/encoded resource and forged-object validation inputs needed by the helper.
- [ ] Run spec gate --commit, commit parser component and ledger exact evidence.

## Task 3: Optional native application INSERT compatibility

Spec: Literal common parser and writer API; Ownership and four-task limit. Advances done_when[2].
Files: gcp/database.py::record_job_run only; tests/integration/test_av_operation_telemetry.py plus existing default/legacy suites as controls.
Interfaces: optional keyword-only operation_metadata: AVOperationMetadata|None=None. None uses ORIGINAL12columns; typed validates and uses reviewed14columns in SAME application INSERT. No generic enrichment or future worker import.

- [ ] RED actual helper against legacy/new PG tables: default/typed inserts, exact NOTE/count/status/execution/variant/time preservation, invalid/forged metadata, absent typed schema, real trigger/constraint failures and no successful metadata-dropping retry. Record application INSERT and actual connection/dialect/TX commands independently.
- [ ] Add only the optional typed branch, shared fixed INSERT binding and safe controlled new-branch errors. Keep existing default cleanup/positional/keyword compatibility and untouched execute_sql/after_replace. A failed typed insertion remains false; no raw supplied values/credentials or extra lookup/retry.
- [ ] GREEN real helper tests and invoke BOTH actual backfill_daily_indicators.main terminal paths, isolating only unrelated price discovery/computation while the real helper/SQL runs. Run existing helper/backfill tests; metadata adds zero application query rather than erasing driver startup work.
- [ ] Run spec gate --commit, commit helper component and ledger. Common CODE remains unmerged; no producer adopted in this branch.

## Task 4: Lawful delivery, independent review and main evidence

Spec: Lawful source-note and generated delivery prerequisites. Closes done_when[3] and all four actual acceptance items; no new executable unit here.

- [ ] Write docs/AV_OPERATION_TELEMETRY.md with actual schema/helper/legacy/typed forms, None origin limitation, source-owner adoption order and measured resource/I/O/byte/storage facts; docs/review-evidence/av-operation-telemetry-common-acceptance.json records exact tests/commits/main and genuine pending fields without secret/environment content or fabricated rollout.
- [ ] After actual policy/verifier/Counter CODE main, update ONLY own appended (FEAT-DATA-001,SHARED-07) implementation-source note and use the actually merged producer for docs/review-evidence/site-source-snapshot.json. Preserve all other SITE/marker/frontend/progress/deployment bytes and historical evidence. Missing prerequisite is a readiness blocker, not a source-only/no-new exemption.
- [ ] Use unchanged trusted full renderer with pinned snapshot for exact05a/05c/05e outputs and all permitted fixed substitutions, preserving other prose/input/marker bytes. Run actual generated tests/gate; no renderer/package/gate edit or counts=False workaround.
- [ ] Update ONLY FEAT-DATA-001 catalog Status/Last reviewed and this distinct PR traceability. Run both complete named common suites, meaningful existing compatibility suites, actual branch versus main docs-audit no-new and BASE PR-mode gate. Bind precise current source/body/spec/main identities.
- [ ] Root arranges fresh-context whole-branch peer, normal current-head external CODE review/CI/conversation resolution and normal publication/merge. Tick fourDoD only with executed evidence; producer/main/adoption/runtime/Scheduler/source/global completion remains pending separately. After actual merge close plan on normal DOC branch; never mark done on an open PR.
