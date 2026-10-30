---
feat_id: FEAT-DEPLOY-001
req_ids: [REQ-DEPLOY-001, REQ-SECRET-001, REQ-CAP-001, REQ-REVIEW-001]
issues: []
site_source_notes: [SHARED-07]
canvases:
  - https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN
done_when:
  - "tests/gcp/test_news_retry_coupling.py executes the actual three news deployment functions with a local gcloud stub and proves max-retries0 on every emitted create and update call, including existing-job fallback and earnings/topics environment updates; baseline missing/nonzero retries fail these controls."
  - "tests/gcp/test_news_retry_coupling.py proves only fetch-news-sentiment, fetch-news-sentiment-earnings and fetch-news-sentiment-topics are addressed and all other emitted arguments match the pinned baseline, including image reference, command, args, service identity, region, resources, environment and secret references."
  - "The reviewed rollout record binds this retry configuration to the approved typed-news producer, defines exact three-job current/intended/rollback immutable-image verification and drift/active-execution refusal, applies and verifies retry0 before typed-image activation, and restores the logger-hardened image before any prior retry setting on rollback; actual live readbacks remain a separate post-merge requirement."
  - "The implementation contains only the three gcp/deploy.sh function edits, their focused behavioral tests and required own delivery records; normal source-bound FEAT-DEPLOY-001/SHARED-07 traceability, unchanged BASE gate and no-new branch-versus-main docs audit pass without claiming broad AV remediation acceptance."
  - "Exact historical and current review lineage is recorded without reset or borrowed allowance; an authorized independent final review, authenticated current-head CODE/SEC review and required CI pass before normal release."
status: draft
supersedes: null
---

# Preserve zero whole-job retries for typed news outcomes

## Status and derivation

Author admission draft. The user approved the requested bounded continuation at 2026-10-30 02:30:26 UTC: three additional aggregate passes and two hosted CODE rounds plus current security review for this narrow retry-policy/runtime lineage. No review has been triggered or spent by this author; historical counts are preserved. Root owns normal specification publication before runtime publication. No deployment is claimed. This extracts the already approved zero-retry policy from `2026-10-12-feat-deploy-001-av-deployment.md` Design line79 and pairs it with `2026-10-24-feat-data-001-news-outcomes.md` Whole-task retry safety and release. It neither supersedes nor edits either approved spec; all27 broad DEP acceptance criteria remain intact for their original scope.

Root supplied the bounded lineage evidence: DEP spec PR1471 merged at25cea4fc after reviewed head e3be4a2/CODE2 and explicitly contained no implementation. PR1457 is unrelated notifier deployment work. No AV runtime plan exists in pinned MAIN or root's bounded PR search. DATA spec1600CODE3 and old unmerged runtime1430head7e002a remain distinct preserved history. This document does not establish a fresh numeric budget; root/owner adjudicates the applicable continuing lineage before invoking a review.

## Problem

The approved typed-news producer makes source or persistence uncertainty nonzero after preserving successful siblings. Existing deployment functions create each NEWS job with max-retries1, while update paths omit the flag. Activating truthful failure exits under that configuration can replay the entire job and its already successful sources. The preserved local baseline harness demonstrates both defects without provider or cloud access.

The repository's unchanged gate assigns gcp/deploy.sh to FEAT-DEPLOY-001 and requires every done_when item of the selected spec when ready for review. Attaching the bounded retry patch to the DATA plan is invalid; declaring all27 broad AV items done from it is also invalid. This small derived contract is a normal separately admitted configuration slice, not a waiver or broader product redesign.

## Non-goals

No source/API/SQL/data-schema changes; no generic or per-source retry policy; no new jobs or schedules; no IAM, credentials, secrets rotation, timeout, memory, CPU, universe, provider request, source-selection or financial calculation change. No broad av-remediation dispatcher, streaming/news expansion, calendar/options/catalyst/watchdog work or closure of their issues. No manual provider/job replay. No changes to trusted gate/reviewer policy or to the original27-item spec.

## Approaches considered

1. Keep the deployment functions unchanged and apply only a one-time operational retry setting. Rejected for this reproducibility repair because a later normal create/update would not maintain the approved setting.
2. Complete the entire broad AV deployment specification before this safety coupling. Not required by the bounded producer objective and not admitted by this task.
3. Use a separate narrow DEP specification derived from the existing approved retry policy. Chosen to give the precise source/configuration change truthful, executable acceptance while preserving the broad contract and all prior review history.

## Design

Change only `gcp/deploy.sh::deploy_fetch_news_sentiment`, `deploy_fetch_news_sentiment_earnings` and `deploy_fetch_news_sentiment_topics`: create uses `--max-retries 0`; every update invocation explicitly carries the same flag, including the earnings/topics environment-only updates. Preserve every other argument and command ordering. The existing immutable IMAGE_REF contract stays in force; no deployment command executes during implementation tests.

Focused test `tests/gcp/test_news_retry_coupling.py` extracts and executes the actual shell function bodies with a shell-local gcloud stub. Exercise successful create and simulated existing-job create failure followed by update. The existing functions emit five calls in the all-create-success scenario and eight in the all-existing scenario; all13 observations must address exactly the three allowed names and carry retries0. Compare all other argument arrays against pinned MAINb483989ea26edc6b44a4cbf17f9c7aa2e4b07285. No provider, SQL, image build, cloud SDK or remote tool call is needed for this proof. Test files and the narrow patch must be adapted to the final admitted implementation base without weakening these behavioral assertions.

Operational release is coupled to the approved DATA producer. Before typed image activation, capture the actual configuration and logger-hardened rollback image for exactly three named jobs; verify expected identities, current retry values and no conflicting active execution; refuse unknown/drift. Apply the narrowly reviewed zero-retry setting and verify it for all three before switching to the reviewed typed image. Then verify intended immutable image identity and unchanged surrounding configuration. Do not run a blanket deployment target. Rollback restores the captured logger-hardened image first and verifies it before restoring prior retry values. Source tests alone never attest any live setting or image.

## Capacity and cost

This configuration change adds zero rows, stored bytes, SQL calls, provider requests or recurring fires. It changes no request timeout, data cap, task sizing or cadence. The source functions retain their existing five/eight configuration-call shapes; the only new data is a retry flag on existing calls. Removing whole-task retries removes replay permission, but no measured performance/cost saving or full production capacity fit is asserted. Existing producer capacity/coverage prerequisites remain owned by their contracts; no timeout increase is used to bypass them.

## Risks and validation

A create-only fix would leave existing jobs retrying; an update-only fix would make newly created jobs unsafe. Executable tests cover both and every secondary environment update. Broad text replacements could alter other jobs; exact target-set and all-other-argument comparisons catch this. A runtime image deployed before retry verification could replay siblings; the paired rollout order is mandatory. The source patch is not permission to change unrelated cloud state or certify broad AV acceptance.

## Delivery and post-merge close-out

Root owns normal specification admission/approval/MAIN and then the narrow implementation plan/PR, with exact lineage reconciliation and authorized review counts. No review is triggered by this draft. Keep DATA and DEP source ownership separate and gate each against its actual approved MAIN spec. Required delivery records may update only the capability's own declared SHARED-07 implementation-source note; preserve historical records and unrelated SITE bytes. Generate source-bound identities only from the eventual final committed source.

After actual source merge, record real three-job retry/image/configuration verification and rollback targets through the approved operational path. Natural schedules and existing allowed exports remain the verification mechanism; do not infer persisted coverage from task success. This mandatory operational close-out is separate from pre-merge test/check acceptance and remains unticked until supported by genuine evidence.
