---
feat_id: FEAT-DEPLOY-001
spec: docs/superpowers/specs/2026-11-09-feat-deploy-001-retire-ew-bindings-own-scope.md
branch: fix/feat-deploy-001-ew-calendar-bindings-own-scope
pr: null
status: ready
---

# EW calendar binding retirement implementation plan

Use executing-plans with the sole existing jobs author in this isolated worktree.

Goal: remove only EW calendar credential reads/bindings and provide calendar-only release preparation.
Architecture: keep all existing calendar arguments except EW env additions; add one dispatcher arm/help entry. Preserve shared calendar, news bodies, secret resources and historical data.
Tech stack: Bash; pytest stub/differential controls; committed Git source-proof fixtures.

## Global constraints and review focus
The ten acceptance items of the bound specification are immutable. All 34 original AV/EW contract items remain unclaimed. Original items 28/31 require a separately admitted successor after this implementation merges. No gate/policy/renderer changes. No production operation in implementation preparation. Merge/release follows P-A. Preserve #1659 review lineage; remaining external review allowance must be established before any triggering event, not reset by this fresh branch.
Review focus: create/update parity, sentinel leakage, shell-startup isolation, unchanged news/dispatcher bodies, and premature source/rollout attestations. Dedicated bindings and delivery-contract tests cover these classes.

## Task 1: calendar-only source and tests
Spec: Design, items 1–4.
- [ ] Port gcp/deploy.sh only within calendar function, earnings-calendar dispatcher and help.
- [ ] Add tests/gcp/test_deploy_ew_bindings.py with stub create/update, secret/env/sentinel checks, baseline argv and unrelated-body preservation.
- [ ] Verify audited helper/closure unchanged from independently cleared preparation; run owned tests with actual merge-base DEPLOY_BASELINE_REV and unchanged reachability tests.

## Task 2: source-proof delivery controls
Spec: Source identity, items 8–9.
- [ ] Add tests/scripts/test_deploy_ew_delivery_contract.py exercising actual producer/verifier/audit/trusted BASE against committed fixture repositories.
- [ ] Run 20 own controls and unchanged compatibility modules test_spec_gate.py, test_doc_source_snapshot.py, test_check_generated_docs.py, test_docs_audit.py; retain failures without waivers.
- [ ] Record Gov/Counter and bridge/Cost approved spec/blob/CODE identities on actual base.

## Task 3: documentation and committed identity
Spec: Design and Source identity, items 5–10.
- [ ] Update RUNBOOK.md retained-secret and unfinished main/staging close-out text; preserve all other prose.
- [ ] Update only FEAT-DEPLOY-001 catalog status/date and new PR lineage after Draft creation.
- [ ] Add only own SHARED-07 source note, preserving earlier accurate own content and every other SITE byte; derive actual source hash, commit final body, produce/commit/verify sidecar with fixed limits.
- [ ] Run matched main/branch docs audit and trusted BASE PR gate with exact ten-item unchecked Draft body and strict Capacity fields.
- [ ] Run commit gate before every commit; publish Draft only if gates and verified remaining review budget permit. Bind actual PR number in next commit.

## Task 4: separately authorized release and close-out
Spec: Source identity and close-out; post-merge obligations only.
- [ ] After P-A and this implementation merge, separately qualify/release only earnings-calendar; record built digest, deployed names-only evidence, successful business output and preserved history separately.
- [ ] Verify actual squash main/fresh-clone identity and real staging; lawful DOC-only sidecar retirement, then docs-branch plan completion. Do not mark these pre-merge complete.
