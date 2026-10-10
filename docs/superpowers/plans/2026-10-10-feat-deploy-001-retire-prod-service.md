---
feat_id: FEAT-DEPLOY-001
spec: docs/superpowers/specs/2026-10-10-feat-deploy-001-retire-prod-service.md
branch: feature/feat-deploy-001-retire-prod
pr: 1366
status: ready
---

# Retire solyra-api-prod and admit the custom domain origin: implementation plan

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the
> done_when item it advances.

## Task 1: refusal tests, then the deploy script
Spec: § Design, `platform/deploy.sh`. Advances done_when[0] and [4].
- [ ] In `tests/gcp/test_platform_deploy_service_config.py`, replace the prod-deploy test with
      `test_a_run_with_no_mode_is_refused_now_prod_is_retired`,
      `test_the_legacy_staging_tag_mode_is_refused` and
      `test_the_legacy_staging_tag_mode_is_refused_alongside_staging_service`, each asserting a
      non-zero exit, `STAGING_SERVICE=1` and `solyra-api-prod` in the output, and an empty stub
      call log
- [ ] Run them against `origin/main`'s script (expect FAIL)
- [ ] Edit `platform/deploy.sh`: refuse unless `STAGING_SERVICE=1`, refuse `STAGING=1`, both after
      `SETUP_IAM` and before the `DB_USER` check; drop the revision-tag code and the prod defaults
- [ ] Run (expect PASS, the staging, missing-Firebase-key and `SETUP_IAM=1` tests unchanged)

## Task 2: the prod Cloud Build path and the documents that name it
Spec: § Design, the Cloud Build file, trigger list, `RUNBOOK.md`. Advances done_when[1], [3], [4].
- [ ] In `tests/gcp/test_staging_deploy_paths.py`, add `test_the_retired_prod_service_has_no_deploy_path`
      and narrow the promote-file tests to the staging trigger; in
      `tests/scripts/test_doc_inventory.py` assert the inventory has no `deploy-solyra-api-prod`
- [ ] Run against `origin/main` (expect FAIL on the new assertions)
- [ ] Delete `gcp/cloudbuild/deploy-solyra-api-prod-cloudbuild.yaml`; drop its trigger entry and the
      prod wording from `gcp/deploy.sh`, the staging Cloud Build file's header,
      `gcp/cloudbuild/serving_revision.py`'s docstring and `gcp/cloudbuild/README.md`
- [ ] `RUNBOOK.md`: three services in the services row, the rebuild step runs
      `STAGING_SERVICE=1 ./platform/deploy.sh` only
- [ ] Run (expect PASS)

## Task 3: the custom domain origin
Spec: § Design, `_cors_origin_regex`. Advances done_when[2] and [4].
- [ ] In `tests/api/test_platform_auth.py`, add `test_cors_regex_admits_the_custom_domain_exactly`
- [ ] Run (expect FAIL)
- [ ] Add `https://stocks\.insightscollective\.org` to the non-iap branch of `_cors_origin_regex`
- [ ] Run (expect PASS)

## Task 4: product records
Spec: done_when[5]. Advances done_when[5].
- [ ] FEAT-DEPLOY-001 record in `docs/product/02-FEATURE-CATALOG.md`: Status, Last reviewed, the
      retired service; `docs/product/12-PR-ISSUE-TRACEABILITY.md`: this PR under FEAT-DEPLOY-001
- [ ] `spec_gate.py --pr origin/main` and the docs audit on the branch and on `origin/main`

## After merge (spec § Design, "Live"; not a done_when item)
- [ ] Export the service, its IAM policy (`gcloud run services get-iam-policy solyra-api-prod
      --project=adept-mountain-474619-d4 --region=us-east1 --format=json`, restored with
      `set-iam-policy` after a `replace`, so the IAP service agent keeps `roles/run.invoker`) and
      the trigger to `gs://adept-mountain-474619-d4-trading-data/retired/2026-10-10/`
- [ ] Delete the trigger, then the service, every command naming the project (and `--region=global`
      for the trigger); show both describes answering NOT_FOUND in a comment on this PR
