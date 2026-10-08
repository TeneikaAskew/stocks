---
feat_id: FEAT-DEPLOY-001
req_ids: [REQ-DEPLOY-001, REQ-SECRET-001, REQ-AUTH-001]
issues: [1345]
canvases: []
done_when:
  - "tests/gcp/test_platform_deploy_service_config.py passes in the Backtest Pipeline run on this PR, and each of its tests is shown failing against a copy of platform/deploy.sh with the setting it pins changed"
  - "The production deploy (no mode variable set) is asserted to run gcloud run deploy for solyra-api-prod as trading-platform-svc@ with AUTH_MODE=iap and MOVEMENT_STATEMENT_ENABLED=true in --set-env-vars, av-api-key mapped to AV_API_KEY and ALPHA_VANTAGE_API_KEY in --set-secrets and absent from --set-env-vars, and --no-allow-unauthenticated"
  - "The public staging deploy (STAGING_SERVICE=1) is asserted to run gcloud run deploy for solyra-api-staging as trading-platform-svc@ with AUTH_MODE=firebase, FIREBASE_API_KEY, FIREBASE_AUTH_DOMAIN, FIREBASE_PROJECT_ID, FIREBASE_APP_ID and MOVEMENT_STATEMENT_ENABLED=true in --set-env-vars, the same av-api-key secret, and --allow-unauthenticated"
  - "A staging deploy without FIREBASE_API_KEY is asserted to exit non-zero naming FIREBASE_API_KEY before any gcloud builds submit or gcloud run deploy"
  - "SETUP_IAM=1 is asserted to grant roles/firebaseauth.admin on the project to trading-platform-svc@ and to exit 0 without a gcloud builds submit or gcloud run deploy"
  - "The FEAT-DEPLOY-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed and names the new test, and 12-PR-ISSUE-TRACEABILITY lists this PR under FEAT-DEPLOY-001"
status: approved
supersedes: null
---

# Deploy service configuration test

## Problem

Eleven rows of the site traceability matrix (`docs/product/03-SITE-TRACEABILITY.md`) are
unticked at Te because their chains cross configuration that `platform/deploy.sh` gives the two
API services, and no test asserts it (stocks#1345 item 4, unticked in #1347): SHARED-01 (the
services' `AUTH_MODE` and service account), AUTH-01 (the `FIREBASE_*` environment), DASHBOARD-21
(the `MOVEMENT_STATEMENT_ENABLED` flag), LIVE-05, LIVE-06, LIVE-08, CHARTS-03, OPTIONS-08 and
PLAYBOOK-05 (the `av-api-key` secret), ADMIN-01 and ADMIN-05 (the `roles/firebaseauth.admin`
grant to the runtime service account).

`tests/gcp/test_staging_deploy_paths.py` covers the deploy paths' interlock, digest pinning and
the routine Cloud Build files' movement flag. Nothing runs `platform/deploy.sh` and checks what it
hands Cloud Run. That script is the path that sets the services' environment, secrets, service
account and ingress: the routine Cloud Build deploys change the image and merge one environment
key, and leave the rest of the service configuration as this script last set it.

## Non-goals

- No change to `platform/deploy.sh`. The script accepts an explicit `AUTH_MODE` override and the
  application's default is `open`; refusing `open` outside local development (the second
  sentence of REQ-AUTH-001) is stocks#911 and stays there.
- Not the routine Cloud Build deploy files (`gcp/cloudbuild/deploy-solyra-api-*-cloudbuild.yaml`)
  or `gcp/deploy.sh`'s jobs and schedulers; the first are covered by
  `tests/gcp/test_staging_deploy_paths.py`, the second are not cited by these rows.
- Not whether the live services match the script. That is an observation of the deployed state,
  which the matrix records under V, and drift between the two is the infra drift check's job.
- Not the matrix itself. A feature branch may not edit rows of other capabilities; the eleven
  rows are re-ticked on a `docs/` branch after this merges, citing this test and the CI run that
  ran it, together with the plan's `status: done`.

## Approaches considered

1. Read `platform/deploy.sh` as text and assert the strings, as most of the existing config tests
   do. Rejected: it proves the text, not what the script passes to `gcloud` in each mode. The mode
   logic (`STAGING_SERVICE=1` switches the service, the ingress and the auth mode together) is
   exactly where a text test passes over a regression.
2. Run the script against a stub `gcloud` that records every invocation, and assert the recorded
   `gcloud run deploy` and IAM calls per mode. Chosen: it executes the real script, so the
   assertions are about runtime behaviour (CLAUDE.md §3.11.1), and it stays hermetic.
3. Describe the live services with `gcloud run services describe`. Rejected for Te: it needs
   credentials and the network, so it cannot run in the pull-request suite; it is what V records.

Chosen on 2026-10-08 under the owner's instruction to make the best choice for the ideal outcome.

## Design

One new file, `tests/gcp/test_platform_deploy_service_config.py`, following the repository's one
file per deploy concern (`test_deploy_image_pinning.py`, `test_deploy_reachability.py`,
`test_staging_deploy_paths.py`). The existing staging-paths file is about two deploy paths not
interleaving; what the script configures on each service is a different responsibility.

Harness, built per test in `tmp_path`:

- A tree holding a byte-for-byte copy of `platform/deploy.sh` at `platform/deploy.sh`, a stub
  `gcp/deploy.sh` (the script calls `./gcp/deploy.sh pin-images --no-sweep` twice; the stub exits
  0) and a stub `gcp/cloudbuild/assert_no_concurrent_staging_deploy.sh` (exits 0). The copy is
  read from the repository at test time, so the test always exercises the current script.
- A stub `gcloud` first on `PATH`, a Python script that appends its arguments as one JSON array
  per line to a log, then answers: `run services describe … --format=json` with a NOT_FOUND
  error and exit 1 (the create path, so the compare-and-swap reads `absent` both times);
  `run services describe … --format=value(status.url)` with a URL; `container images describe`
  with a `gcr.io/…@sha256:<64 hex>` digest; anything else with exit 0.
- A clean environment, not the caller's: `PATH`, `HOME`, `DB_USER`, `DB_NAME`, `IMAGE_TAG`, plus
  the mode variables a test sets. `PROJECT_ID` and `RUN_SA` stay unset so the assertions are
  about the script's production defaults (`adept-mountain-474619-d4`,
  `trading-platform-svc@adept-mountain-474619-d4.iam.gserviceaccount.com`), and no CI variable
  such as an inherited `AUTH_MODE` can change the result.

A helper parses the recorded `run deploy` call into the service name, the `--service-account`
value, the `--set-env-vars` pairs (the value starts with gcloud's `^|^` delimiter marker and
splits on `|`), the `--set-secrets` pairs (split on `,`) and the ingress flag. The tests:

- `test_prod_deploy_configures_solyra_api_prod`: the production deploy, done_when item 2.
- `test_staging_service_deploy_configures_solyra_api_staging`: `STAGING_SERVICE=1` with the
  three required Firebase variables set; `FIREBASE_PROJECT_ID` defaults to the project. Item 3.
- `test_staging_service_deploy_refuses_without_firebase_config`: item 4.
- `test_setup_iam_grants_firebaseauth_admin_and_does_not_deploy`: item 5.

Each test is shown to fail, in the PR, against a scratch copy of the script with the setting it
pins changed (the auth mode, the flag, the secret, the ingress, the guard, the role), so none of
them passes vacuously.

Capacity (CLAUDE.md rule 0): n/a. The change adds a hermetic test and runs no workload; a run
spawns the script four times with a few dozen stub calls, well under a second each.

## Risks

- The script gains a call to a new sibling file: the copied tree lacks it, the run fails, and the
  test fails loudly naming the missing path. That is the intended direction; the fix is to add
  the file to the harness.
- The script's create path is what runs (the stub answers NOT_FOUND). The replace path differs
  only in the compare-and-swap baseline, which `test_staging_deploy_paths.py` covers; the
  configuration passed to `gcloud run deploy` is the same on both paths.
- A future mode variable that changes the configuration without these tests noticing: the
  assertions name every value the eleven rows cite, so a change to any of them fails a test.
