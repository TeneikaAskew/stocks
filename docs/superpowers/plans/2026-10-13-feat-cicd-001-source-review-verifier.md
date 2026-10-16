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
- [x] Run complete affected snapshot/audit/gate suites and unchanged BASE suite; retain cold/ordinary actual CLI counts/bytes/runtime and actual bound-failure controls. No timeout/drop-assertions/alternate-checker substitute.
- [x] Preserve registry285second and existing full-render60second/512MiB acceptance contracts; run their required actual checks where the shared gate change requires them, coordinated with core author.

## Task 13: Delivery records, sidecar and initial bootstrap evidence
Spec: § Audit routing and bootstrap, Stage2; § Local identity and external review are separate. Advances done_when[4,7].
- [ ] Update only own catalog/PR traceability, ready plan PR number and sidecar. Initial implementation edits NO SITE, registry watcher, pinned workflow or initializer; all watched changes stay within the fixed six-file bootstrap allowlist while trusted policy lacks verifier. Produce/commit/verify sidecar binding existing SITE body and final scoped source; rerun on any later watched-source change.
- [ ] Capture actual branch/main audits with no new findings and authoritative unchanged BASE `--pr` verdict, preserving source identity vs external CODE review vs rollout-pending labels.

Historical checkpoint971eb656/488f15a2 used module SHA256f529472eed39b5807d2070c8da4fa3128db6468c2e0e22234b4079a0795d545d and source suite SHA256d73872968daeafd70cb1d0313c08476fdade4c455e07233a55c28a8fcc4a1a28. Its complete affected suite passed794 tests (outer466.5429seconds), but four independent frozen488f peers subsequently identified final installation cleanup outside the deadline, deliberate fixture descendants left unreaped, and terminal future dates not checked against today. Those findings invalidated that candidate's complete-lifecycle claim; they are not waived by its earlier green suites. Actual current MAINe27e9e77 was integrated normally; its changed SITE input was exercised by the actual complete original-normalizer producer test (1passed/0.76seconds). Historical proposed98 passed171.11seconds (outer171.8532); unchanged MAIN96 suite SHA2567ee523785cc0b3c4d90528120da74e3d5de5fa4c00aaa71c708ec066312bdc3b passed174.15seconds (outer174.4660). The exporter implementation and41-test suite remain byte-identical to MAIN; the complete unchanged exporter suite passed90.11seconds. This change edits no renderer, generated inputs, workflows, pinned files or initializer; existing full-render60second/512MiB contracts remain intact.

The single consolidated correction uses module SHA256743bc0ab5c25edced651ac1d460f2ecda820bced766ef9e5d68ffdf0e813b605 and source suite SHA256b472516cd481cc3ec9cb5386d7f9e8ccced6191b38fa6f1c1ac569c41cce8966. New actual-CLI regressions first produced7failures/3passes; corrected focused controls passed29. Final native source162 plus auditor642 passed804 (150.00seconds, outer150.8853); proposed98 passed171.94seconds (outer172.6634), exact unchanged BASE96 passed169.13seconds (outer169.4811), both below285seconds. Every final run left zero new zombies. A preceding804 pass exposed one native failing-promisor-transport orphan; an isolated adopter reproduced and reaped it before the same scoped fixture correction was extended and the complete suite rerun. The test-only Linux adopter contains deliberate fixture descendants; actual production CLI process-group/refusal behavior and original assertions remain exercised. No production platform, global/PID1 or OS setting was changed.

Successful cleanup precedes the final verdict inside the original five-second guard; retained charged old bytes allow atomic recovery even after the backup was physically unlinked. Actual old/new records differ in rollback controls. An attempted/partial stdout write followed by refusal is nonzero and cannot be accepted; no contradictory second JSON is appended. Default-five-second synchronous error-unwind controls with0.25second injected restoration latency returned1 with one unverified JSON and truthful elapsed5.2504/5.2517seconds, no post-deadline verification/Git work, exact absent/previous-valid output and restored caller timers. Mandatory rollback/reaping is synchronous error unwind, not a renewed verification budget or positive acknowledgement; no universal arbitrary-filesystem failure walltime is claimed. Corrected actual repo sidecar/default-audit evidence follows; the older identity evidence below remains historical.

Corrected source8593b1db produced a DIFFERENT real record over the prior installed valid sidecar, accepted0.2472seconds/5,235,380admitted bytes under the unchanged default5second cap. Committed9db542e0 verification accepted0.5514seconds/7,193,195bytes/1428entries. Source identity505c0ac302034de95da646ada4b20e3f69d8ab612dd0c25f874f236208476d0c, unchanged full body f23df410cbbbdfa626077302946c4baa1655847b69b895f820ae7766ff2bfdc7, sidecar SHA256103fcdd39ac873af9183d50bcb586144864b5939431e07fb961287b2c4ca4dd0, actual current ancestral baseline MAINe27e9e77. Both actual unchanged MAIN BASE and proposed `--pr` checkers passed9db542e0/nine paths with real draft metadata. Actual default audits (`--json` only, owning-job and all other checks enabled) compared MAIN445docs/286findings against corrected HEAD446docs/284findings: entire-multiset NEW=[], only the two SITE source/body drift findings replaced by eligible initial-bootstrap context. Its audit identity used0.5531seconds/7,230,088bytes. The initial network-denied main-audit attempt produced no JSON and was retained as a failure; supported per-command network access then allowed the ordinary existing GitHub issue reads without changing proxy/CA/credentials or audit predicates. These local results authenticate no external reviewer or deployment; fresh four-seat review, actual source CI/current-head external CODE review and post-merge close-out remain Task14.

Git2.52 ordinary commit maintenance was independently reproduced as one detached Git zombie per local commit. The documented invocation-only `maintenance.autoDetach=false` and `gc.autoDetach=false` controls preserve maintenance in the foreground; three controlled commits and both complete gate suites produced zero new Git zombies. Inherited Git configuration is retained and only these two entries are appended for local harness processes. No global/home config, OS limits, sandbox protections or gate predicates were changed. The earlier proposed-suite run (23passed/11failed/64errors) is retained: every one of its75 failure/error diagnostics contained actual fork BlockingIOError/EAGAIN, without TimeoutExpired; it was never claimed as a gate pass.

Historical frozen488f producer and committed verifier bound actual ancestral/current MAINe27e9e77, complete source identity ba4342e75c1b25a0bb85624588ef535e1aa87f5bb1b4a27f89e4a01b211b6731 and body f23df410cbbbdfa626077302946c4baa1655847b69b895f820ae7766ff2bfdc7. Its default producer passed0.2727seconds/5,235,380actual bytes and committed verifier0.5878seconds/7,192,543bytes, combined1428entries. Both unchanged actual MAIN and proposed `--pr` checkers passed its nine-path initial bootstrap. Its actual default audits (`--json` formatting only) compared MAIN445docs/286findings against branch446docs/284findings: no NEW finding; only SITE's two original source/body changed-since findings were replaced by independently matched initial-bootstrap identity (0.5786seconds/7,229,436bytes), explicitly rollout pending. Full finding multisets were compared; no owning-job, source, scope or audit exception was used. These historical outputs do not certify the corrected source until Task13 is repeated.

Earlier genuine deadline failures at5.0705,5.1766 and5.0189seconds and the original CPU-normalization overshoot are retained. Immutable-object work sharing and the same-budget reentrant hard CPU alarm corrected those paths without raising5seconds/8388608bytes/20000entries. Actual large fallback parser refusals preserved absent/existing valid sidecars; smaller complete-body controls accepted. Actual caller handler/timer/mask restoration, active/blocked-timer and unsupported-thread refusals, atomic final-output rollback, spawned-child setup/selector/cleanup failure and kill/reap/sentinel controls all passed. Existing116 original source-test cases retained their assertions. Task14 independent peers, authenticated external reviews, CI, merge and actual main/staging close-out remain incomplete.

Published ec84e9e2 passed all four independent local seats, with full exact-hash reports publicly attached before the ordinary source push. Its actual source CI passed gate, BASE suite, registry, integration and research, but core Run Tests failed:1failed/5681passed/67skipped/99warnings225.66seconds. The sole observed failure was `tests/meta/test_timezone_boundaries.py::test_no_new_timezone_relabels_and_the_backlog_only_shrinks`, which correctly flagged our newly introduced unannotated terminal `datetime.date.today()` as a new host-clock site. No READY or authenticated CODE/SEC review was triggered. The authentic CI log and failing result remain retained, not reclassified as a pass.

The authorized follow-on correction is exactly one nonmarket documentation-date annotation on that call, matching the existing ordinary auditor's explicit `tz-ok` review-date context. No runtime/date semantics, meta guard or meta baseline changed. Whole-module runtime AST SHA256 remains EXACTLYc534c0e9c3878cbef1f9f0f34ab97d577c63fd57d43a770d57bdf812b472666d; module bytes now SHA256ed04286cf30f2fc7323efd025509023f5b48821a98ae4b6579ab5e41f3cdb798. Actual local meta suite first reproduced1failure/5passes7.17seconds, then passed all6 in6.80seconds after annotation; six real current-terminal/future/impossible date/squash-retirement controls passed12.83seconds. Prior804/98/96 complete runtime evidence is reused only because this is a verified comment-only AST-identical change; new source identity/sidecar/default audits and four exact-new-head peer checks remain required before another source push, followed by authentic full source CI. Task13 was reopened until the refresh below completed; Task14 remains incomplete.

The comment-only source6313e653 produced a new valid sidecar194bee9c21287354b3700beb04e1a0c676d19ae093084080e82d451257a2225f in0.271554seconds/5,235,380bytes. Committed8d9c2e4b verified in0.542974seconds/7,193,747bytes/1428entries, binding source a5f40e2068416dd22dd5b0aa226d30548688177eecd81d9a13e99c90a63c3301 and the unchanged complete SITE body/policy. Fresh actual default MAINe27e9e77 and branch audits used only `--json`: 286 versus284 findings, whole-multiset NEW=[]; original SITE drift replacement remains independently eligible bootstrap identity. Actual unchanged MAIN BASE and proposed PR gates both passed the nine-path committed delta. Task13 local refresh is complete; final exact-head packet and four targeted rechecks remain required before another source push. Actual full source CI must subsequently pass; the prior failed CI, external CODE/SEC and post-merge Task14 are not preticked.

Published ffa1158d passed five required CI checks, but actual full core CI failed1/6100passed/68skipped/103warnings773.22seconds at the terminal date test: collection saved October15 while the genuine auditor stamped October16. Both reviewed/scanned cases reproduced deterministically by setting only the test module's saved DAY to yesterday; actual terminal CLI acceptance preceded the stale-token assertion. Runtime verifier, auditor, gate, meta guard and baseline were unchanged. The test-only correction locates the unique date token from the genuine accepted stamp, validates its calendar value against actual before/after stamp days, and retains every native refusal/audit assertion. Eight combinations cover both fields, future/impossible dates and normal/stale import day. Complete source166 plus timezone6 passed172 in162.68seconds. Global accounting observed two unrelated containerd-shim zombies and is retained separately; no Git/Python fixture orphan was identified.

Separate actual DOC core CI exposed the existing gate-suite import-TODAY/real-commit-date race. The unchanged actual CLI reproduced it: a catalog date October15 was refused against a real October16 head. The approved six-file scope includes tests/scripts/test_spec_gate.py. Only its local fixture _git helper now defaults test author/committer dates to the immutable fixture day; inherited and explicit per-call dates retain precedence. A real-Git regression verifies stale-day acceptance, wrong LastReviewed refusal, and independent inherited/per-call date overrides. Whole proposed99 passed under the unchanged285second contract (189.679634seconds outer), with zero owned adopted/escaped children under an isolated invocation-only adopter. Runtime predicates and all prior gate assertions remain intact; unchanged MAIN BASE suite remains separate. Own catalog date advances to the actual new head-commit day; no product commit is backdated. Source identity/default audits must now be refreshed before Task13 closes again. All new raw peer reports stay local; no authenticated review or post-merge completion is claimed.

## Task 14: Independent review, merge and post-merge close-out
Spec: § Audit routing and bootstrap; § Bounds and acceptance controls. Advances done_when[4,7].
- [ ] Four independent current-head reviewers run concrete accepted/refused actual controls for shell/import, policy/ownership, source/exporter identity and resource/audit boundaries. Resolve findings in one batch before push; respect two-round cap and fresh-cut rules.
- [ ] Root handles approved publication/merge after normal authenticated current-head CODE review, green CI, complete acceptance evidence and resolved conversations; sole author pushes only its own implementation branch.
- [ ] After squash independently verify actual main in fresh clone; separate DOC close-out updates historical trunk/staging evidence only after genuine checks, using exact no-CODE-change SITE+sidecar pending route for a body-first DOC if needed, then actual body-containing current-trunk stamp+record retirement. Plan-done is a separate DOC commit. Source identity alone does not finish rollout.
