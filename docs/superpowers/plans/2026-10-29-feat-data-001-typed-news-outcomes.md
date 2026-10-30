---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-10-24-feat-data-001-news-outcomes.md
branch: fix/feat-data-001-typed-news-outcomes
pr: null
status: ready
---

# Typed news outcomes implementation plan

> For agentic workers: use superpowers:executing-plans. Single author; root owns publication and later final review.

## Scope and admission

Approved FEAT-DATA-001, REQ-DATA-001, REQ-REL-001, REQ-SECRET-001 and REQ-CAP-001. Preserve request selection, one HTTP attempt, 30-second timeout, topic AND semantics, incremental bounds and existing upsert identity. Source requalified on MAIN b483989ea26edc6b44a4cbf17f9c7aa2e4b07285, with all preserved runtime/test bytes unchanged and92 focused controls passing; original baseline was8bbe09ce4cef9e569ae93c00ba825e3cc8bebd2f; recovered prototype is an author artifact, not reviewed code. Preserve historical spec #1600 CODE3 and historical separate CAT runtime #1430 lineage; no automatic review allowance transfer/reset.

Deployment coupling belongs to FEAT-DEPLOY-001 under scripts/gate/spec_gate.py ownership. Approved 2026-10-12-feat-deploy-001-av-deployment.md §Design explicitly covers all three news jobs' create/update retries0. Prepare a private narrow patch and stub evidence for its own plan; do not combine deploy.sh into this DATA branch or claim broader AV acceptance. Existing broad spec acceptance requires all27 criteria, so the private derived retry-only draft needs normal admission before separate narrow DEP publication; historical1471CODE2 remains recorded without reset. Typed runtime activation requires confirmed zero whole-job retries first. No live provider/SQL, remote writes, job updates or spec edits in this author task.

## Task 1: Recover native failing controls
Spec: §Design typed outcomes and CLI aggregation; advances done_when[0,1].
- [x] Adapt preserved scheduled-entry controls into tests/gcp/test_news_sentiment_outcomes.py against native module.
- [x] Run all ten entry controls on baseline; retain observed RED and successful empty/nonempty controls.
- [x] Apply only hash-verified fetcher prototype patch and adapt directly affected native tests.
- [x] Run focused outcome, argument, incremental, explode and phase2 news tests under HTTP/SQL guards; retain GREEN.

## Task 2: Safe failures and acknowledgement
Spec: §Design safe diagnostics and persistence; advances done_when[1,2].
- [x] Integrate preserved malformed-feed, provider-envelope, HTTP429/503, timeout/JSON, fake-key and ambiguous ACK controls.
- [x] Adapt existing logger-only controls to approved typed semantics without weakening secret-safety assertions.
- [x] Add any demonstrated missing source-isolation or CLI diagnostic control before its minimal fix.
- [x] Verify successful siblings persist once, upsert identity is unchanged, and uncertain writes never trigger refetch/replay.
- [x] Follow-up:8 fake-key/malformed-identifier controls fail before cursor/floor logging repair; remove raw ticker only from those diagnostics and run all92 affected controls with unchanged SQL/request/bounds.

## Task 3: Coupling handoff and close-out prerequisites
Spec: §Rollout/rollback and §Done when; advances done_when[3,4].
- [x] Prepare private exact-three-job retry0 patch, execute create/update paths with local gcloud stub and compare all other arguments to baseline.
- [x] Record exact per-lineage admission, source/test identities and pending separate DEP plan/gate ownership.
- [ ] Root later commits, publishes own source-bound SHARED-07 note, records traceability/catalog updates, docs audit and source gate; no source hash from uncommitted files.
- [ ] Root later obtains one authorized final independent review and current CODE/CI before release; no review invoked by this author task.
- [ ] Rollout owner verifies old/intended immutable images and actual retry0 settings for exactly three jobs before typed image activation; rollback logger-hardened image first, then old retry setting. No manual replay or coverage claim.

## Final review focus

Provider notices alongside a feed remain errors. A malformed late member must not write a successful prefix. Successful sibling persistence must precede partial failure, including uncertain ACK without replay. Actual zero sentiment remains data. Requests, topic AND/truncation and incremental bounds remain unchanged. Three-job retry coupling must be separately admitted and verified before activation; source tests do not prove deployed state.

## Consumer preparation — 2026-10-30

Consumer base: `63d1dbf7e04ba48ec73023ff0386231dcbcfb606`. The six producer afterimages were matched byte-for-byte before delivery metadata preparation. Packet SHA256: `4f4f12779cc9700e220f6ef4659ff5606982a063dbbaa19c0c6d5eeafecd8ab1` (332611 bytes, 43 records). Consumer baseline: 8 failures and 2 passes in `/tmp/news-consumer-red.log`; candidate: 92 passes and 10 deselections in `/tmp/news-consumer-green-complete.log`. These are deterministic mocked tests, not a new judgment review or deployed evidence.

Historical separate CAT runtime #1430 remains unmerged at head prefix `7e002a`; specification #1600 consumed CODE3. No review allowance is reset or pooled with the separate deployment lineage. DATA hosted-review allowance reconciliation remains with the root publisher; this local draft retains `pr: null`. Deployment retry source is excluded. Exact-three-job retry0 verification must precede typed runtime activation under separate deployment admission.

Local preparation covers own catalog, traceability and source-bound SHARED-07 note with committed-source proof. Full remote docs audit, independent review, hosted CODE/SEC, CI, publication and deployment remain root-owned prerequisites. Offline audit results, if recorded, do not certify remote issue state or owning-job status.
