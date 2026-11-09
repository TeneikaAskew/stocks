---
feat_id: FEAT-CATALYST-001
spec: docs/superpowers/specs/2026-11-03-feat-catalyst-001-retire-ew-source-own-scope.md
branch: fix/feat-catalyst-001-ew-only-retirement
pr: 1758
status: ready
---

# EarningsWhispers-only retirement implementation plan

> For agentic workers: use superpowers:executing-plans for this preserved and tested implementation.

**Goal:** Stop EW ingestion and exclude its two verified aliases from the six owned readers, retaining historical rows and non-EW behavior.
**Architecture:** One null-safe shared SQL predicate; remove the retired fetch path; five unavailable score-dependent outputs remain NULL. Preserve current main's event-bound earnings and atomic snapshot behavior.
**Tech stack:** Python, PostgreSQL, FastAPI, pytest and the unchanged documentation verifier.
**Spec:** docs/superpowers/specs/2026-11-03-feat-catalyst-001-retire-ew-source-own-scope.md

## Global constraints

Fresh binding after spec merge59bfb52a; no rebind of #1681 or reset of its spent review budget. The original consolidated51-item spec remains approved and unchanged; none of its items is ticked, waived or claimed here. No other reader lane, shared calendar, gate, policy or resource limit changes. Renderer60seconds/512MiB; verifier5seconds/12582912combined bytes/20000entries. Normal two-round review policy applies to this fresh re-cut. No production authorization is conveyed.

## Review focus

NULL/unknown and near-alias sources stay visible; stale EW hydration cannot contaminate current rows; unavailable scores never become bullish recommendations; daily-path and atomic refresh behavior remain intact; source identity does not certify rollout. Tests in tasks1–3 exercise these cases.

## Task 1: ingestion and alias controls
Spec: Design; done_when[0–1].
- [x] Reconcile existing CLI/removal and exact shared predicate against actual main.
- [x] Run CLI, finite-number and eight-alias controls; preserve normalize_earnings_time.
- [x] Verify focused tests on successor committed head:312 passed, plus25 local PostgreSQL passed/1 private capture skip.

## Task 2: six readers and nullable outputs
Spec: Design; done_when[2–5].
- [x] Carry per-site discriminating fixtures and non-EW equality controls; preserve historical rows.
- [x] Verify five NULL fields, actual source labels and routed responses, including local PostgreSQL.
- [x] Preserve #1608 calendar shim, atomic replacement and daily_path_v1;24 local PG controls pass, private ANGO capture case skipped.
- [x] Reverify actual-main reconciliation; runtime source unchanged from tested preservation candidate.

## Task 3: retirement docs and generated inventories
Spec: Design owned files; done_when[6,9].
- [x] Reconcile owned retirement prose and line pointers; regenerate05-a/05-c/05-e with unchanged renderer.
- [x] Run generated-document suite140pass and model-registry68pass.
- [x] Verify committed renderer output on successor:140 generated checks passed.

## Task 4: own source note and delivery records
Spec: Source identity; done_when[7,9].
- [x] Update only own catalog/lineage and CATALYSTS-04 note, preserving earlier accurate content.
- [ ] Commit source, preflight producer, commit note hash, produce final-body sidecar, commit and bounded verify.
- [ ] Matched full docs audits report no new finding; registry blob/mode/type equals actual main.

## Task 5: retained obligations and release disclosure
Spec: Design and delivery dependencies; done_when[8,10–12].
- [ ] Record exact Gov/verifier/inventory/Cost main identities and original43–49/51 crosswalk in PR.
- [ ] Disclose watched platform/lib staging build, full schema apply/MV rebuild from comment digest, and Solyra contract sync; no execution authorized here.

## Task 6: ordinary acceptance
Spec: Source identity and Done when; done_when[9,12].
- [ ] Trusted actualBASE PR gate; fresh draft PR and actual lineage/plan number.
- [ ] Ordinary authenticated exact-head CODE review, required green CI and resolved conversations; no approval invented.

## Separate post-merge close-out

Not pre-merge acceptance: independently verify actual main in fresh clone after squash; owner-authorized staging/source/data checks and lawful sidecar retirement; plan status done on docs branch after merge. No CODE retirement or fabricated staging proof. The user separately authorized full EW removal and deployment; actual merge and release still require normal current-head review/CI and validated EW-specific steps. No production action has been performed yet.
