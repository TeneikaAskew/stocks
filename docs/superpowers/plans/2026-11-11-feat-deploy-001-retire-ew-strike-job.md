---
feat_id: FEAT-DEPLOY-001
spec: docs/superpowers/specs/2026-11-01-feat-deploy-001-retire-ew-evaluator-source-note.md
branch: fix/feat-deploy-001-retire-ew-strike-job
pr: null
status: ready
---

# Retire the evaluate-ew-strikes deployment (fresh cut from main): implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

This plan re-cuts the closed stocks#1658 on a fresh branch from current main, at the owner's request
(2026-11-11: close #1658, open a fresh PR that removes the nightly EarningsWhispers job). It binds the
approved spec above from its first commit, so no plan is rebound in place. The implementation is #1658's,
carried onto main 7794e673: the six `gcp/deploy.sh` hunks, `tests/gcp/test_deploy_ew_evaluator.py` and the
test fixture edits, with one conflict resolved by keeping main's `earnings-calendar)` arm and help entry
(#1789) beside the retirement stub. Wherever the spec names #1658 for item 8, this branch's PR is that
implementation PR.

Rules carried: no Cloud Run job, scheduler or secret is read or mutated by this branch;
`gcp/fetchers/evaluate_ew_strikes.py`, `docs/product/05-INFRASTRUCTURE.md` and the MODEL-EWV-001 model
row are other specs' work; the three `deploy_fetch_news_sentiment*` bodies are not edited.

## Task 1: deploy.sh retirement and its tests
Spec: § Retained text of the 2026-10-31 spec. Advances done_when[0], done_when[1], done_when[2], done_when[4].
- [ ] Apply #1658's `gcp/deploy.sh` hunks to main: delete `deploy_evaluate_ew_strikes`, its call in
      `deploy_fetchers` and its `_schedule` line; add `_unschedule "evaluate-ew-strikes-daily"`; make the
      dispatcher arm a RETIRED stub that exits 1; add the target to the `_NEEDS_DEPLOY_CREDS=0` list;
      drop its help entry. Keep main's `earnings-calendar)` arm and help entry.
- [ ] Add `tests/gcp/test_deploy_ew_evaluator.py`; move `tests/gcp/test_deploy_image_pinning.py`'s two
      sample tests to `deploy_fetch_fred_rates` with unchanged assertions.
- [ ] Run: `DEPLOY_BASELINE_REV=<merge base> pytest tests/gcp/test_deploy_ew_evaluator.py tests/gcp/test_deploy_reachability.py tests/gcp/test_deploy_image_pinning.py -q` (expect PASS)

## Task 2: registry and generated inventories
Spec: § Retained text. Advances done_when[3].
- [ ] Remove the `evaluate-ew-strikes-daily` scheduler row from `docs/product/07-MODEL-REGISTRY.md`;
      run `python3 scripts/gate/export_model_registry.py`.
- [ ] Re-render the 05-a and 05-c inventory blocks with main's `scripts/maintenance/doc_inventory.py`.
- [ ] Run: `pytest tests/meta/test_model_registry_consistency.py tests/scripts/test_doc_inventory.py tests/scripts/test_check_generated_docs.py -q`

## Task 3: source identity (SHARED-07)
Spec: § Source identity and close-out. Advances done_when[7].
- [ ] Update the `(FEAT-DEPLOY-001, SHARED-07)` row of the Implementation-source notes table with the
      producer's current source hash and prose describing only this retirement and its tests.
- [ ] Produce, commit and verify `docs/review-evidence/site-source-snapshot.json`.

## Task 4: close
Spec: § Done when. Advances done_when[5], done_when[6].
- [ ] Update the FEAT-DEPLOY-001 catalog record (Status, Last reviewed); add this PR to 12-PR-ISSUE-TRACEABILITY.
- [ ] Docs audit reports nothing new over origin/main (`python3 scripts/maintenance/docs_audit.py`).
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`
- [ ] Post-merge, separately authorized: pause, then delete the `evaluate-ew-strikes-daily` scheduler and
      the `evaluate-ew-strikes` Cloud Run job (RUNTIME-QUALIFICATION-PLAN.md section 2).
