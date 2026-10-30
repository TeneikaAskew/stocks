---
feat_id: FEAT-PLAYBOOK-001
spec: docs/superpowers/specs/2026-10-30-feat-playbook-001-market-date.md
branch: fix/feat-playbook-001-market-date
pr: null
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
