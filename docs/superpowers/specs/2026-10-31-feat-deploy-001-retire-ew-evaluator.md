---
feat_id: FEAT-DEPLOY-001
req_ids: [REQ-DEPLOY-001, REQ-CAP-003]
issues: []
canvases: []
done_when:
  - "gcp/deploy.sh no longer defines deploy_evaluate_ew_strikes, deploy_fetchers no longer calls it, deploy_schedulers no longer calls _schedule for evaluate-ew-strikes-daily and instead issues the retired-schedule deletion in the existing L4179-4188 pattern (NOT_FOUND tolerated), the dispatcher case evaluate-ew-strikes) is a retirement stub that echoes a message containing RETIRED and exits 1 in the shape of the existing p7b-classifier stub, including an evaluate-ew-strikes entry in the _NEEDS_DEPLOY_CREDS=0 list at L1090-1094 (as p7b-classifier has at L1092) so that tests/gcp/test_deploy_reachability.py::test_targets_that_read_no_secret_are_exempt_from_the_eager_probe (L342-360) passes unchanged, and the help text has no evaluate-ew-strikes entry; the unrelated scheduler-block comment at L4732 is unchanged"
  - "tests/gcp/test_deploy_ew_evaluator.py (new, created by this PR alone; the bindings PR has its own tests/gcp/test_deploy_ew_bindings.py), with the repo's gcloud stub, proves: deploy_fetchers issues no run jobs create or update naming evaluate-ew-strikes; deploy_schedulers issues the delete and no create or update for evaluate-ew-strikes-daily; ./deploy.sh evaluate-ew-strikes exits 1, prints the RETIRED message and runs no gcloud command; ./deploy.sh help output contains no evaluate-ew-strikes; every other scheduler and job argument equals the argv captured on origin/main; the three deploy_fetch_news_sentiment* function bodies are byte-identical to the merge base"
  - "tests/gcp/test_deploy_image_pinning.py keeps test_a_deploy_names_the_built_digest and test_a_deploy_without_a_build_mutates_nothing with unchanged assertions against deploy_fetch_fred_rates, and its collected test count equals main's"
  - "07-MODEL-REGISTRY.md has no evaluate-ew-strikes-daily scheduler row (L370 removed; the MODEL-EWV-001 model row at L47 is changed by the FEAT-DATA-001 retire-ew-module-shim spec, not here); docs/product/05-INFRASTRUCTURE.md is not changed by this PR (check_product_scope, scripts/gate/spec_gate.py L4222-4227, refuses it on a fix branch; its L192 evaluate-ew-strikes row is removed by the docs-only PR P-J after this PR merges, RETIREMENT-DESIGN.md section 6.1); 05-a and 05-c inventory blocks equal scripts/maintenance/doc_inventory.py output (test_check_generated_docs.py::test_committed_docs_pass_every_gate)"
  - "gcp/fetchers/evaluate_ew_strikes.py is not changed by this spec"
  - "No Cloud Run job, scheduler or secret is mutated by this PR; RUNTIME-QUALIFICATION-PLAN.md section 2 (pause, delete scheduler, delete job) is linked from the PR as separately authorized close-out, and must be complete before the FEAT-DATA-001 module-shim PR's image ships"
  - "02-FEATURE-CATALOG FEAT-DEPLOY-001 record shows Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists this PR"
status: draft
supersedes: null
---

# Retire the evaluate-ew-strikes job, scheduler and dispatcher; leave the module to its DATA owner

P-C in RETIREMENT-DESIGN.md rev 3.9 sections 4, 6 and 7. Scope is gcp/deploy.sh and the deploy-side docs only; the gate assigns gcp/deploy.sh to FEAT-DEPLOY-001 (spec_gate.py:1099, 4698-4701). The module gcp/fetchers/evaluate_ew_strikes.py is under gcp/fetchers/, FEAT-DATA-001's Code path (02-FEATURE-CATALOG.md:523), so its strip to the nyse_sessions shim and the MODEL-EWV-001 model-row change are the FEAT-DATA-001 spec 2026-10-31-feat-data-001-retire-ew-module-shim.md (P-I). No dependency on PR #1546 or lib.eastern_time. The dispatcher case is a retirement stub rather than a deletion so that an operator or scheduler invoking the old name fails loudly with the reason, matching the p7b-classifier precedent in gcp/deploy.sh (~L5415). Acceptance is behavioural: the earlier "exactly two grep lines" expectation was wrong because the unrelated comment at L4732 also contains the job name and is deliberately left alone.
