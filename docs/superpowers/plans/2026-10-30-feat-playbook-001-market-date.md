---
feat_id: FEAT-PLAYBOOK-001
spec: docs/superpowers/specs/2026-10-30-feat-playbook-001-market-date.md
branch: fix/feat-playbook-001-market-date
pr: 1640
status: ready
---

# Playbook market-date implementation plan

Specification #1637 merged as 19f349db770639ace6affb4d3320393903f0ff91 before this runtime branch. The designated fresh-runtime owner is sole remote publisher.

Consumer handoff: packet SHA256 559a10315fc21759ff7ad74c30425d4162e888fab850b461c73d9aeacb12d613; all 11 embedded hashes and both beforeimages verified against producer base 54fa457c57ae2f244c76f7e6a614c2fabeb6a669 and main 19f349db770639ace6affb4d3320393903f0ff91. The exact runtime patch is retained unchanged. Original issue #1308 linked-history reconciliation found no earlier repair PR; unrelated completed router history remains recorded in the handoff. Runtime hosted CODE consumed before this branch: 0.

Consumer validation: new midnight tests against unchanged main router yielded 2 failed / 2 passed; exact candidate yielded all 53 playbook tests passing. No provider or production query and no deployed acceptance is claimed.

## Task 1: establish final baseline and preserve reproduction
Spec: Problem/Design; advances done_when[0].
- [ ] Reconcile issue1308 linked PR/review lineage; retain actual consumed cohorts. Do not borrow unrelated briefing or collector allowances.
- [ ] Start from final MAIN after spec merge, never stack on another open PR. Preserve SPIKE patch e49b3787cf55d39ea8ab54738eee583a10e7e5a1b13aec009b5375a53663caa4.
- [ ] Carry test_playbook_age_uses_market_midnight first; preserve /workspace/playbook-timezone-red.log with2failed/2passed on original MAIN.

## Task 2: integrate canonical reference and invariant coverage
Spec: Design/Risks; advances done_when[0:2].
- [ ] Apply only canonical market_today import/reference and clock fixture adaptation from the preserved two-file SPIKE after conflict inspection.
- [ ] Run python3 -m pytest tests/api/test_playbook_evaluate.py -q --disable-warnings. Preserve all53existing/candidate controls, including seven-day boundary, cache, historical, nullable/generated_at coverage. No provider/production queries.
- [ ] Confirm diff leaves explicit dates, generated_at, UTC storage, response schema, max age and frontend unchanged.

## Task 3: normal publication readiness
Spec: Source identity/Close-out; advances done_when[2].
- [ ] Update only own catalog Status/Last reviewed/evidence and traceability with actual PR number; set plan pr after draft creation.
- [ ] Update own declared PLAYBOOK-09 source note, run existing producer twice for byte equality and verifier within original limits, then compare docs audit to exact MAIN.
- [ ] Run commit/full PR-context gate with actual PR metadata. Obtain independent/current required reviews and checks within reconciled ordinary per-lineage allowance; no formal APPROVE, cap bypass or duplicate trigger.
- [ ] Root performs normal protected merge only when eligible; retain all review history.

## Task 4: separately evidenced close-out
Spec: Close-out; post-merge only.
- [ ] Record MAIN and deployed immutable image/source relationship, normal build/deployment terminal outcomes and permitted live age verification.
- [ ] Complete actual source-protocol close-out/retirement and plan done only after required evidence exists. Do not label local53tests as live acceptance.

## CI fixture correction after runtime CODE1

CODE1 and SEC1 completed clean on 27e7cbc2; first receipts 6514061319 and 6514061598 remain preserved. Full CI run 40995521285 exposed an older wire-shape fixture that used the runner UTC date as a market date, yielding age -1 before Eastern midnight. Consumer reproduced the exact failure, then pinned both playbook fixtures in tests/api/test_platform_api.py to a fixed market date and UTC generated timestamp. The router implementation remains byte-identical to the producer patch. Combined playbook/platform API suites pass 135 tests. This test-only correction and refreshed source evidence use the remaining runtime CODE2/current SEC; no allowance reset. Full suite and hosted checks remain required before merge.

## Authorized inventory correction: runtime CODE3 plus security

CODE2 completed clean on53e1256c at03:28:06.740540UTC; SEC completed03:31:41.417139UTC. Full CI40997408039 then failed the complete committed-docs gate after6120passed/68skipped because all three generated inventories retained earlier playbook source-line references. The previous receipts and failed run remain evidence; matched-audit zero-new findings was insufficient qualification.

User approved one additional repair/review cycle at2026-10-30 09:40:10UTC, replying to the exact request for CODE3 plus security limited to inventory regeneration and all required checks. Reserve that single additional aggregate/current-head CODE3+SEC cycle; no formal APPROVE or protection waiver. Required current-main source-identity preflight also requires normal reconciliation with already-landed Signals main05830d8d. Preserve its runtime/security repair and source notes; no new runtime design is introduced. Regenerate ARCHITECTURE, DATA_DEPENDENCIES and API with the existing frozen snapshot, then run the complete committed-docs gate and actual ready-mode metadata gate on final committed source before the one publication. The separate GCP owner retains deployment verification; no deployment is inferred from these checks.
