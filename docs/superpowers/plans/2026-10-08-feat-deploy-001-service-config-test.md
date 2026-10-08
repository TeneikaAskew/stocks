---
feat_id: FEAT-DEPLOY-001
spec: docs/superpowers/specs/2026-10-08-feat-deploy-001-service-config-test.md
branch: feature/feat-deploy-001-service-config-test
pr: null
status: ready
---

# Deploy service configuration test implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

## Task 1: harness and the production deploy
Spec: § Design, "Harness" and `test_prod_deploy_configures_solyra_api_prod`. Advances done_when[0] and [1].
- [ ] Write `tests/gcp/test_platform_deploy_service_config.py` with `_run(tmp_path, **mode)` (scratch tree, byte-for-byte copy of `platform/deploy.sh`, stub `gcp/deploy.sh` and interlock, recording stub `gcloud`, clean environment) and `_deploy(calls)` (the single `run deploy` call parsed into service, service account, env pairs, secret pairs, args)
- [ ] Write `test_prod_deploy_configures_solyra_api_prod`
- [ ] Run: `python -m pytest tests/gcp/test_platform_deploy_service_config.py -q` (expect PASS against the current script)
- [ ] Mutate a scratch copy (auth mode `open`, flag dropped, secret renamed or moved into env, ingress public, service account changed) and run again (expect FAIL each time)

## Task 2: the public staging service
Spec: § Design, `test_staging_service_deploy_configures_solyra_api_staging`. Advances done_when[0] and [2].
- [ ] Write the test with `STAGING_SERVICE=1` and the three required Firebase variables
- [ ] Run (expect PASS); mutate the staging auth mode, `PUBLIC=1` and `FIREBASE_PROJECT_ID` (expect FAIL)

## Task 3: staging without its Firebase config
Spec: § Design, `test_staging_service_deploy_refuses_without_firebase_config`. Advances done_when[0] and [3].
- [ ] Write the test without `FIREBASE_API_KEY`
- [ ] Run (expect PASS); mutate the guard to default the key to empty (expect FAIL)

## Task 4: the IAM grant
Spec: § Design, `test_setup_iam_grants_firebaseauth_admin_and_does_not_deploy`. Advances done_when[0] and [4].
- [ ] Write the test with `SETUP_IAM=1`
- [ ] Run (expect PASS); mutate the role and remove the early exit (expect FAIL)
- [ ] Commit: `test(deploy): assert the service configuration platform/deploy.sh deploys`

## Task 5: close
Spec: § Done when. Closes done_when[5].
- [ ] Update the FEAT-DEPLOY-001 record in 02-FEATURE-CATALOG (Status, Last reviewed, Tests naming the new file)
- [ ] Add this PR to the FEAT-DEPLOY-001 PR lineage in 12-PR-ISSUE-TRACEABILITY
- [ ] Docs audit reports nothing new over origin/main (`python -m scripts.maintenance.docs_audit`)
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`
