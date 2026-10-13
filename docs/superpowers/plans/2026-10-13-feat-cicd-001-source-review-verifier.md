---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-13-feat-cicd-001-source-review-verifier.md
branch: feature/feat-cicd-001-source-review-verifier
pr: 1470
status: ready
---

# Committed-source documentation identity implementation plan

The approved verifier specification SHA2568609bae9976547eb45c88f9dc8a561da0d43d6e666366458b444c7cbb7ef718f and completed Policy A CODE are actually main at fdbcdaa797e30f1bcdf3842246e698e582dc60c7. This is one fresh standalone branch from that main. Sole implementation author: gate_shell_followup; root alone publishes DOC close-out and merges. Core renderer remains review_deploy's separate unmerged work and is not copied here.

> For agentic workers: use superpowers:executing-plans, meaningful real-CLI TDD and fresh four-seat whole-branch review before implementation source push.

**Goal:** Bind SITE implementation notes to exact committed watched source/body while preserving normal external CODE review and separate deployed close-out.

**Architecture:** One stdlib-only protected producer/verifier module, narrow existing auditor integration and trusted BASE SITE-note/ownership checks. Committed record data is independently re-derived from actual trusted-policy/current/baseline Git trees; it never authenticates reviewers or deployment.

**Tech stack:** Python stdlib and Git, actual snapshot/audit/BASE-gate CLIs, real disposable repositories and existing pytest suites.

**Spec:** `docs/superpowers/specs/2026-10-13-feat-cicd-001-source-review-verifier.md`.

## Global constraints

- Single shared monotonic5second whole-verification deadline; combined8388608actual input bytes (including repeated reads and every policy/eligibility blob); combined20000current/baseline entries. No caller raises ceilings. Stream bounded reads, inspect sizes before contents and reap deadline children.
- Initial actual bootstrap changes watched source only within six paths: snapshot module, docs_audit, spec_gate and their three suites. No SITE content, registry watchers, initializer bytes, pinned workflows, renderer or unrelated gate-predicate changes.
- Source registry blob/mode/type equals trusted POLICY exactly; approved binding exists unchanged at actual ancestral-main baseline/currentPOLICY/SOURCE. No self-approved spec or unavailable feature-SHA proof.
- Only genuinely changed declared own notes with exact current source hash admit ordinary CODE identity. DOC close-out independently has exactly SITE+sidecar committed delta and complete SOURCE==MAIN. Landed bootstrap/notes require complete SOURCE/BODY==MAIN; no future bootstrap reuse.
- Ordinary genuine current-trunk marker plus zero original source/body drift takes precedence; absence of sidecar is legal there. Existing marker/ref/description/test predicates and every other document remain unchanged.
- No auth/network/vendor service call, new deployed workload or cryptographic review attestation. Actual external CODE review, CI and unresolved-thread guards remain ordinary prerequisites.
- Preserve separate registry285seconds and trusted full-render60seconds/512MiB. No alternative compiled pytest, omitted assertion or synthetic successful proof.

## Review focus

- Squash removes feature objects: Task11 uses actual squash/fresh clone plus independently verified ancestral-main baseline and SHA-1/SHA-256 accepted controls.
- Well-formed authored record can lie: Tasks3/4/8 mutate actual committed source/notes/spec/registry and must retain findings.
- Budget gaps/partial producer can corrupt a last valid record: Tasks5/6 exercise all actual bytes, timeout/partial/nonzero and absent/existing-sidecar preservation.
- Git can lazily fetch missing promised objects: Task5 refuses promisor/partial state before object plumbing, verifies supported no-lazy-fetch guard and a sensitive local remote-access sentinel.
- Dirty staged SITE or premature DOC retirement can misstate verification: Tasks7/11 check index and worktree independently, DOC-only body-first/stamp phases and terminal precedence without a record.

## Task 1: Verify main prerequisites and overlapping-file sequence
Spec: § Audit routing and bootstrap, Stage1/2. Advances done_when[4,7].
- [x] Independently verify actual main fdbcdaa7 contains approved verifier8609 and completed Policy A exact skill65ef/template4b4e, approved own FEAT/requirements and immutable policy/verifier specs.
- [x] Confirm review_deploy's renderer/main sequencing and additive protected-file interface before editing shared `scripts/gate/spec_gate.py` or `tests/scripts/test_spec_gate.py`; preserve current trusted BASE checker/exporter/init/renderer semantics.
- [x] Create one isolated named implementation branch from that main; stage ONLY this canonical fourteen-task ready plan, run actual commit gate and hook (expect PASS), and commit before implementation. Open one draft PR, then bind its real pr number in the next gated commit. No shared-branch/source push before four-seat review.

## Task 2: Real committed-repository fixtures and initial refusals
Spec: § Bounds and acceptance controls. Advances done_when[0,1,6].
- [x] Add disposable real Git repo builders to `tests/scripts/test_doc_source_snapshot.py`, not successful verifier substitutes. Seed actual `docs/DOC_REGISTRY.md`, SITE, watched source and genuine trunk history.
- [x] Run initially failing actual-CLI controls for absent producer/record, committed-vs-dirty source and unresolved refs; retain meaningful expected exit/finding assertions.

## Task 3: Strict canonical record and path contracts
Spec: § Exact record and committed-source contract. Advances done_when[0,1,6].
- [x] Implement version1 schema/canonical identity calculations in new stdlib-only `scripts/maintenance/doc_source_snapshot.py`; strict keys/types/duplicates/UTF-8/paths/object-format/modes/entry order.
- [x] Test malformed/unknown/duplicate/oversized records, floats/bool integers, paths and unsupported entry types through actual CLI. Real SHA-1 and SHA-256 repositories must accept exact OID widths and refuse malformed/wrong-width OIDs; literal scripts/café.py UTF-8 canonical bytes pass, alternate Unicode/solidus escapes refuse.

## Task 4: Trusted policy and exact current/baseline manifests
Spec: § Exact record and committed-source contract. Advances done_when[0,1].
- [x] Derive the entire SITE watcher declaration from trusted `docs/DOC_REGISTRY.md`, preserving exact/descendant semantics and new descendants; independently enumerate committed paths/modes/OIDs/type/size through Git argv plumbing.
- [x] Verify source/policy hashes and actual ancestral baseline.main_commit_oid/tree/spec; require current main baseline for branch routes, unchanged approved FEAT/spec copies and SOURCE registry blob/mode/type exactly equal POLICY. Accept landed route only when source AND body match independently measured current policy tree. No caller-selected merge bypass or required vanished feature SHA.
- [x] Exercise actual new/deleted/renamed/mode-changed blobs, narrowed scope, source-registry blob/mode/type inequality, unavailable ancestral baseline and changed trusted policy refusals.

## Task 5: Deadline, byte accounting and Git-state refusal
Spec: § Bounds and acceptance controls. Advances done_when[5,6].
- [x] Enforce a single monotonic5second whole-operation budget, combined8388608input bytes and20000current/baseline entries, including record/listing/metadata/body/repeated reads/output admission. Tests may lower limits only.
- [x] Count EVERY actual policy/eligibility input byte, including each registry/selected plan/current-baseline-POLICY-SOURCE spec/initializer-policy read and repeated reads; reject oversized inputs before buffering/parsing. Actual oversized registry, selected plan and each required spec revision refuse; accepted below-bound controls use the same CLI.
- [x] Bound/reap Git children, reject partial output and replacement/graft/unsupported shallow state. Exercise real slow/large/partial controls without sandbox changes or partial success.
- [x] Before object-inspecting Git plumbing refuse partial-clone/promisor/config/pack state, verify a supported no-lazy-fetch capability and apply it to every producer/verifier Git child. Preserve inherited credentials/proxy/CA. Real missing-watched-blob promisor fixture with instrumented LOCAL remote must leave access sentinel absent on actual producer/verifier/audit refusal; unprotected actual Git lazy fetch must detect access, complete ordinary repo must accept. No production/network action.

## Task 6: Producer and committed verifier CLI
Spec: § Exact record and committed-source contract. Advances done_when[0,5,6].
- [x] Implement exact approved produce/verify argv; producer writes only the fixed sidecar, installs atomically after complete success, and verifier reads it from committed source ref.
- [x] Report actual verdict/reason/count/bytes/source-policy-body identities/elapsed time. Actual nonzero/timeout/partial failures start BOTH absent and valid installed output: absent remains absent, existing valid bytes remain exact after EVERY failure. Do not open/truncate/delete destination before complete success; temporary output atomically replaces only on verified success. Corrupt/fake output cannot pass real verifier/audit.

## Task 7: Body normalization and dirty-document protection
Spec: § Exact record and committed-source contract, document identity. Advances done_when[0,1].
- [x] Reuse existing `_without_marker` semantics without widening ignored metadata or importing untrusted HEAD startup inputs into the trusted gate; protect any necessary local initialization inputs.
- [x] Hash strict UTF-8 complete committed SITE body, preserve extra marker prose and reject dirty SITE before identity OR terminal verified routes. Actual audit controls modify SITE separately only in index, only unstaged, and staged then restored worktree; paired clean identical committed-record control passes. Real note/frontend/progress/extra-marker changes invalidate identity.

## Task 8: Narrow docs-audit routing
Spec: § Local identity and external review are separate; § Audit routing and bootstrap. Advances done_when[0,4,7].
- [x] First accept independently valid ordinary verified current-trunk marker plus zero original source/body drift with no sidecar requirement. Otherwise route SITE's two changed-since checks only on complete eligible declared-note/bootstrap/DOC-closeout identity; invalid/missing records retain originals plus needed provenance finding. Preserve ordinary marker/date/ancestry/reference/description/test checks and all other documents.
- [x] Add actual audit CLI controls for valid and stale proof plus unrelated finding; labels never claim authenticated external review/deployment and stamping remains trunk-only.

## Task 9: Trusted spec selectors and SITE-note byte ownership
Spec: § Exact document allowance. Advances done_when[2].
- [x] Extend approved-spec validation for sorted unique `site_source_notes`; derive existing unique Chain IDs from trusted SITE and declarations only from immutable approved merge-base spec.
- [x] Extend `check_product_scope` for only own declared FEAT/component rows in the appended exact-header note table, preserving all other bytes. Require actual added/updated declared own notes bound to exact current source hash and unchanged approved FEAT/spec; no/empty declaration, unchanged notes or removal alone cannot clear CODE drift. Reject mixed existing Chain edits, frontend/checklist/marker changes, duplicate headings/rows, foreign removals, undeclared IDs and self-approved selectors with actual gate controls.

## Task 10: Protected CICD verifier/suite/init ownership
Spec: § Implementation boundary via bootstrap and done_when protected files. Advances done_when[3,4].
- [x] Add producer/verifier, docs_audit, their suites and actual local initialization dependency closure to existing process ownership without changing core renderer logic or broad watchers.
- [x] Actual unrelated-feature gate controls must refuse attempted code/suite/init changes; legitimate standalone CICD control must pass. Coordinate exact diff with review_deploy before either author pushes shared-file work.

## Task 11: Squash and fresh-clone acceptance
Spec: § Exact record and committed-source contract; § Audit routing and bootstrap, Stage3. Advances done_when[1,6].
- [x] Run actual producer → commit record → actual verify/audit/gate on feature, actual squash to main, clone without original feature commit and verify landed identity with trunk history sufficient for marker.
- [x] Mutated landed source/body/policy must fail; vanished feature SHA must not be fetched or assumed. Include actual corrupt producer-output negative paired with accepted record, no-note CODE branch refusal, bootstrap reuse refusal and exact six-file initial-bootstrap accepted/refused controls.
- [x] Run real DOC-only body-first close-out producer/merge, then genuine current-trunk stamp/record deletion. Refuse changed CODE masquerading as DOC, registry/type/mode changes, dirty/moved marker and premature retirement; genuine terminal original marker+zero source/body drift must pass without a record.

## Task 12: Complete verification and resource evidence
Spec: § Bounds and acceptance controls. Advances done_when[0,1,2,3,4,5,6].
- [ ] Run complete affected snapshot/audit/gate suites and unchanged BASE suite; retain cold/ordinary actual CLI counts/bytes/runtime and actual bound-failure controls. No timeout/drop-assertions/alternate-checker substitute.
- [ ] Preserve registry285second and existing full-render60second/512MiB acceptance contracts; run their required actual checks where the shared gate change requires them, coordinated with core author.

## Task 13: Delivery records, sidecar and initial bootstrap evidence
Spec: § Audit routing and bootstrap, Stage2; § Local identity and external review are separate. Advances done_when[4,7].
- [ ] Update only own catalog/PR traceability, ready plan PR number and sidecar. Initial implementation edits NO SITE, registry watcher, pinned workflow or initializer; all watched changes stay within the fixed six-file bootstrap allowlist while trusted policy lacks verifier. Produce/commit/verify sidecar binding existing SITE body and final scoped source; rerun on any later watched-source change.
- [ ] Capture actual branch/main audits with no new findings and authoritative unchanged BASE `--pr` verdict, preserving source identity vs external CODE review vs rollout-pending labels.

Prior local checkpoint2b1f9b63 passed733 affected tests, proposed98/269.87seconds, unchanged BASE96/269.48seconds, unchanged exporter41/90.11seconds and default284/284 finding equality. Its final actual current-repository verify then failed the mandatory5second ceiling at5.0705seconds; that failure is retained. The approved bounded immutable-object reuse and complete object batching correction requires fresh Task12/13 evidence before freeze. No ceiling or predicate was waived. Task14 external reviews, CI, merge and actual main/staging close-out remain incomplete.

## Task 14: Independent review, merge and post-merge close-out
Spec: § Audit routing and bootstrap; § Bounds and acceptance controls. Advances done_when[4,7].
- [ ] Four independent current-head reviewers run concrete accepted/refused actual controls for shell/import, policy/ownership, source/exporter identity and resource/audit boundaries. Resolve findings in one batch before push; respect two-round cap and fresh-cut rules.
- [ ] Root handles approved publication/merge after normal authenticated current-head CODE review, green CI, complete acceptance evidence and resolved conversations; sole author pushes only its own implementation branch.
- [ ] After squash independently verify actual main in fresh clone; separate DOC close-out updates historical trunk/staging evidence only after genuine checks, using exact no-CODE-change SITE+sidecar pending route for a body-first DOC if needed, then actual body-containing current-trunk stamp+record retirement. Plan-done is a separate DOC commit. Source identity alone does not finish rollout.
