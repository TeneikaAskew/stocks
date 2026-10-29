---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-26-feat-cicd-001-metadata-successor.md
branch: fix/feat-cicd-001-earnings-metadata-successor
pr: null
status: ready
---

# Exact earnings metadata successor implementation plan

> For agentic workers: use superpowers:executing-plans. Preserve all prior review receipts and reserve the mandatory gate red-team cohort before dispatch or publication.

**Goal:** Admit the single approved metadata-only successor without changing the original earnings plan, financial acceptance, source-proof identity or resource ceilings.

**Architecture:** A pure exact-pair validator in the existing gate consumes pinned raw specification bytes and original plan metadata. Gate tracing and the source verifier independently obtain their trusted inputs; the verifier uses its bounded Git reader. Registry scope is restricted to the existing scheduler exclusion row.

**Tech Stack:** Python, existing Git readers and hermetic pytest repository/CLI fixtures.

**Spec:** `docs/superpowers/specs/2026-10-26-feat-cicd-001-metadata-successor.md`, merged in #1612 at `784bb63b6a34c3cb41c0808581d2fe1ee89e99c5`.

## Global Constraints

- Original spec SHA256: `b5701d90da14d2a372156ad6c130e239e49748533dd631db882a6f70c20157a6`.
- Successor SHA256: `14e8f6f7b96fd49b640e860a5e97a3b4453556e9e418c1ab6fac55c631f35408`.
- Preserve original earnings plan path, spec, branch, PR #1608 and ready/done protection; this PR does not edit that plan or earnings runtime.
- Only four runtime/test files change: `scripts/gate/spec_gate.py`, `tests/scripts/test_spec_gate.py`, `scripts/maintenance/doc_source_snapshot.py`, `tests/scripts/test_doc_source_snapshot.py`.
- Required delivery records may change only FEAT-CICD-001 and the SHARED-01 source note. No workflow, hook, schema, credential, ceiling or record-format change.
- Current MAIN is the authority; proposed files and authored sidecars cannot grant admission. Keep source proof at 8,388,608 logical bytes, 5 seconds and 20,000 entries.
- #1612 spec CODE1–CODE4 remain consumed. #1608's preserved LOCAL1–LOCAL5 remain consumed. Neither is reset by this implementation. Verified old-owner ledger and fresh registrations show zero gate-runtime CODE/LOCAL cohorts used, with its ordinary two CODE rounds available.

## Review Focus

- A symlink or executable blob at a pinned path must fail, even if decoded text matches: Task 1 and Task 2 negative controls.
- A second successor arriving after branch creation must fail independently in trace and landed verification: Task 1 and Task 2 controls.
- A squash with no surviving feature branch must preserve original plan/blob identity and reject a changed binding: Task 2 fresh-clone controls.
- A registry change hiding an extra row in prose, a delimiter or disposition must fail: Task 3 controls.
- Midnight or changed HEAD must not leave stale closeout evidence: Task 4 uses full PR environment and actual final head date.

## Task 1: Exact gate binding

Spec: Exact trusted pair and plan; Runtime scope. Advances done_when[0:2].
Files: gate and its existing test file.
Interface: `validated_metadata_successor(plan_path, plan_fm, original_bytes, successor_bytes) -> str | None` validates the exact immutable pair; absence returns None, malformed or unsupported presence raises ValueError. Gate adapters separately require trusted regular blobs on base and proposed tree.
- [ ] Write real commit/PR fixtures using the two exact approved blobs and original #1608 plan identity. Assert accepted tracing retains original spec path/frontmatter.
- [ ] Add negatives for absent, null/list/duplicate/unnormalized links, modified/unmerged specs, foreign FEAT/branch/PR, changed original bindings, reopened done plan, chains, cycles, extra successors and nonregular blobs.
- [ ] Run the new tests against MAIN; expect the exact valid pair to fail ordinary supersession while existing rejection controls pass.
- [ ] Implement the pure validator, optional-field validation and trace coverage. Keep `plan_stays_bound` unchanged; retain ordinary supersession rejection for every other case.
- [ ] Run the new tests and original supersession/selected-spec/immutable-plan regressions; expect all pass.
- [ ] Run commit gate and commit the tested task locally; no push.

## Task 2: Independent bounded source-proof admission

Spec: Independent source-proof binding. Advances done_when[3:5].
Files: verifier and its existing CLI test file; consumes Task 1's pure validator only.
Interface: `Snapshot.spec_binding` independently reads the committed original plan and exact pair from baseline/POLICY/SOURCE through `self.git`, preserving its return value and record schema.
- [ ] Add actual CLI preflight/produce/commit/verify fixtures and a real squash/fresh-clone verification. Assert original eligibility spec path/blob and CATALYSTS-04 component IDs.
- [ ] Run positives against MAIN verifier; expect its independent trusted-POLICY supersession refusal.
- [ ] Add negatives for missing/malformed link, changed plan/spec, uncovered successor, wrong source hash, absent/unchanged/foreign note, source/body/policy drift and raised ceilings.
- [ ] Implement bounded independent reads and exact coverage; preserve selected-binding and ordinary routes.
- [ ] Run new controls and the full existing source-proof suite; expect all pass with unchanged resource limits.
- [ ] Run commit gate and commit locally; no push.

## Task 3: Narrow registry clarification

Spec: Runtime scope registry paragraph. Advances done_when[2].
Files: gate and its existing test file; consumes separately validated metadata scope from Task 1.
- [ ] Add red/green controls permitting only the existing daily/weekly earnings-reactions exclusion-row clarification with unchanged scheduler/job identities, MODEL-EARN-001, Inputs-only and no-position semantics.
- [ ] Reject other rows, promotions, headers, delimiters, dispositions, stray prose and changed generated JSON; retain the normal exporter check.
- [ ] Implement the exact-row allowance without broadening ordinary selected-spec registry scope.
- [ ] Run affected registry controls and full spec-gate suite; expect all pass.
- [ ] Run commit gate and commit locally; no push.

## Task 4: Integrated proof and bounded publication

Spec: Gate implementation-source note ownership; Verification and risks. Advances done_when[5:7].
- [ ] Reconcile preserved runtime review ledger and reserve the required shell, YAML/Actions and exporter/policy red-team cohort within its actual allowance; no implicit new grant.
- [ ] Run concrete bypass probes in that cohort, preserve every finding, and repair only within the remaining allowance.
- [ ] Produce actual final source identity; update only SHARED-01; commit and verify the normal generated sidecar.
- [ ] Update own catalog/traceability and eventual PR number, matching Last reviewed to the actual final head date.
- [ ] Compare committed branch/MAIN documentation audits; expect zero new findings. Run full PR-mode gate with exact base/head SHAs and PR environment, not only the abbreviated local invocation.
- [ ] Publish only after the reserved review prerequisites pass. Obtain current-head CODE/SEC and required checks; ordinary protected merge only, with no formal APPROVE or override.
- [ ] Report this as gate behavior only. Earnings #1608 source integration and deployed acceptance remain separate and preserve their inherited ledger.
