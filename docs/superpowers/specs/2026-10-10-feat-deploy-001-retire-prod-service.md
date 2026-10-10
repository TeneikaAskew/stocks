---
feat_id: FEAT-DEPLOY-001
req_ids: [REQ-DEPLOY-001, REQ-AUTH-001]
issues: []
canvases: []
done_when:
  - "tests/gcp/test_platform_deploy_service_config.py asserts that platform/deploy.sh run with no mode variable, and run with STAGING=1, exits non-zero naming STAGING_SERVICE=1 before any gcloud builds submit or gcloud run deploy, and still asserts the solyra-api-staging deploy configuration and the SETUP_IAM=1 grant"
  - "tests/gcp/test_staging_deploy_paths.py asserts that gcp/cloudbuild/deploy-solyra-api-prod-cloudbuild.yaml does not exist and that gcp/deploy.sh registers no deploy-solyra-api-prod Cloud Build trigger, and its remaining tests pass against the staging path alone"
  - "Each new or changed assertion is shown failing against the code on origin/main when the PR opens, and the Backtest Pipeline Run Tests job is green on the PR head"
  - "gcloud run services describe solyra-api-prod and gcloud builds triggers describe deploy-solyra-api-prod both answer NOT_FOUND, shown in a PR comment that also records the service's last configuration, read before the deletion"
  - "tests/api/test_platform_auth.py asserts that the CORS origin pattern in firebase mode fully matches https://stocks.insightscollective.org and does not match http://stocks.insightscollective.org, https://stocks.insightscollective.org.evil.com or https://evil-stocks.insightscollective.org, and that the iap-mode pattern does not match it"
  - "The FEAT-DEPLOY-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed and names the retired service, and 12-PR-ISSUE-TRACEABILITY lists this PR under FEAT-DEPLOY-001"
status: approved
supersedes: null
---

# Retire the solyra-api-prod service and serve the site from stocks.insightscollective.org

## Problem

The repository deploys two API services, and only one of them is used. Read live on
2026-10-10:

- The website, `https://solyra-stocks.lovable.app`, sends every `/api/*` request to
  `solyra-api-staging`. The frontend has no other API origin: solyra
  `src/lib/apiTargets.ts` defines `LOCAL_API` and `STAGING_API` and nothing else.
- `solyra-api-prod` answers `/` with a 302 to Google sign-in (IAP), serves no website (the image
  copies no `dist/`, `platform/Dockerfile`), and was last deployed 2026-09-15, while staging
  redeploys from `main`. No Cloud Scheduler job, Cloud Run job, service environment or domain
  mapping references it.
- Both services read and write the same Cloud SQL database, so "prod" separates nothing.

The owner's instruction on 2026-10-10: tear down `solyra-api-prod`; there is no prod separation;
keep the existing names. Deleting the service alone does not hold, because three things in this
repository recreate it:

1. `platform/deploy.sh` defaults `SERVICE` to `solyra-api-prod` and `AUTH_MODE` to `iap`, so
   running it with no mode variable deploys prod. Its legacy `STAGING=1` mode deploys a
   no-traffic tagged revision on that same service.
2. The manual Cloud Build trigger `deploy-solyra-api-prod`, which promotes the digest serving
   staging onto prod, from `gcp/cloudbuild/deploy-solyra-api-prod-cloudbuild.yaml`.
3. `gcp/deploy.sh cloudbuild-triggers`, which imports that file into that trigger and fails when
   the trigger is missing.

The same day the owner connected `stocks.insightscollective.org` to the Lovable project, so the
one live site gets an address on the owner's domain (Lovable domain settings; the A record
`185.158.133.1` and the `_lovable` TXT record resolve at Squarespace DNS). The site calls this
API cross-origin from there, and `_cors_origin_regex` in `platform/api/main.py` admits only
Lovable and Codespaces origins, so every call from the new address would be blocked by the
browser.

## Non-goals

- No rename. `solyra-api-staging` keeps its name, URL and domain mapping
  (`api.stocks.insightscollective.org`); the owner chose to keep names.
- Not the `iap` auth mode in `platform/api/auth.py` and `main.py`. Nothing deploys it after this,
  but removing an application mode is its own change with its own tests.
- Not the documentation: the product docs, both CLAUDE.md files, the site traceability matrix
  (146 cells name `solyra-api-prod`) and the solyra docs are corrected on `docs/` branches after
  this merges and the service is gone, so they describe what exists.
- Not the architecture diagram generator (`scripts/maintenance/refresh_architecture_drawio.py`),
  whose label map still draws the prod service. It is documentation tooling with its own tests,
  and it changes on its own branch.
- Not stale comments in files this change does not otherwise touch (`platform/api/main.py`,
  `platform/api/routers/earnings.py`, `gcp/schema.sql`), per the stale-reference policy.
- Not the sign-in domain (`auth.stocks.insightscollective.org` on Firebase Hosting, the Firebase
  Auth authorized domains, the OAuth redirect URI, the service's `FIREBASE_AUTH_DOMAIN`). Those
  are project settings, not repository content; they are recorded in the docs pass.
- Not the solyra side of the new address (its static-host list); that is solyra's own change.
- Not the IAP OAuth client, the `trading-platform-svc` service account or the images in the
  registry. The staging service uses the first two, and the images let the service be redeployed
  if it is ever wanted again.

## Approaches considered

1. Delete the service and the trigger and leave the code. Rejected: one run of
   `./platform/deploy.sh` with no variables recreates it, and the trigger sync fails on the
   missing trigger.
2. Make the no-variable run deploy the staging service. Rejected: an operator who remembers the
   old default and expects the IAP-gated service would deploy the public one without being told.
3. Require `STAGING_SERVICE=1` and refuse every other mode with a message naming the retirement,
   remove the prod Cloud Build file and its trigger registration, then delete the live service and
   trigger. Chosen: the only remaining target is named explicitly, and every way back to prod is
   closed in the same change.

Chosen on 2026-10-10 under the owner's instruction above.

## Design

`platform/deploy.sh`:

- `SETUP_IAM=1` keeps working with no other variable; it grants and exits before any mode check.
- After that block, the script exits 1 unless `STAGING_SERVICE=1`, printing that
  `solyra-api-prod` was retired on 2026-10-10, that `solyra-api-staging` is the only API service,
  and the command to run. `STAGING=1` is refused the same way, with or without
  `STAGING_SERVICE=1`, since it only ever targeted the prod service. Both refusals happen before
  the `DB_USER` check and before any `gcloud` call.
- The `STAGING` revision-tag code (`STAGING_FLAGS`, the tagged-URL print) is removed.
  `SERVICE` and `AUTH_MODE_VAL` lose their prod defaults; the `STAGING_SERVICE` branch sets them
  as today. The header comment describes the one mode.

`gcp/cloudbuild/deploy-solyra-api-prod-cloudbuild.yaml` is deleted. In `gcp/deploy.sh` the
trigger list drops its entry, and the legacy-image cleanup's error message stops naming the prod
trigger. `gcp/cloudbuild/README.md` drops the prod trigger section.

Tests:

- `tests/gcp/test_platform_deploy_service_config.py`: the prod-deploy test becomes two refusal
  tests (no mode variable; `STAGING=1`), each asserting a non-zero exit, `STAGING_SERVICE=1` in
  the output and no `gcloud builds submit` or `gcloud run deploy` recorded. The staging and
  `SETUP_IAM=1` tests stay.
- `tests/gcp/test_staging_deploy_paths.py`: the tests that read the prod promote file are removed
  or narrowed to the staging trigger, and one test asserts the file is absent and the trigger list
  in `gcp/deploy.sh` has no `deploy-solyra-api-prod` entry, so neither comes back unnoticed.

`platform/api/main.py`, `_cors_origin_regex`: in non-`iap` modes the pattern gains the exact
origin `https://stocks\.insightscollective\.org`, beside the Lovable branches and under the same
auth-mode gate, so the docstring's reasoning (gated endpoints still need a verified Firebase
token) covers it unchanged. One exact host, not `*.insightscollective.org`: the apex serves a
different Lovable site, and a wildcard would admit every future subdomain. Starlette fullmatches
the pattern, so suffix and scheme variants do not match; the test pins that.

Live, after CI is green on the PR and before it merges:

1. Record `gcloud run services describe solyra-api-prod --format=yaml` and the trigger's
   description in a PR comment (image digest, environment names without values, service account,
   IAP state).
2. `gcloud builds triggers delete deploy-solyra-api-prod`, then
   `gcloud run services delete solyra-api-prod --region=us-east1`.
3. Show both `describe` calls answering NOT_FOUND in the same comment.

Deleting before the merge is safe because nothing automatic deploys prod: the trigger is manual
and `platform/deploy.sh` is run by hand or by `deploy-staging.yml`, which passes
`STAGING_SERVICE=1`. It lets the done_when item be ticked with evidence instead of after the fact.

Capacity (CLAUDE.md rule 0): no job, query or schedule is added. The deleted service had
`min-instances 0`, so its standing cost was near zero; the change removes a deploy target, not
load.

## Risks

- Something calls prod that the live read missed. Checked 2026-10-10: schedulers, Cloud Run job
  and service environments, domain mappings and the frontend. A miss would show as errors in the
  caller's logs after the deletion; the recorded configuration is enough to redeploy the same
  digest with `platform/deploy.sh` at the commit before this one.
- An operator runs the old default. The refusal names the change and the command to use.
- The new origin admits more than intended. The test asserts the scheme, suffix and prefix
  variants do not match, and that iap mode does not admit it.
- `deploy-staging.yml` breaks. It runs `STAGING_SERVICE=1 ./platform/deploy.sh`, which the staging
  test keeps asserting end to end.
