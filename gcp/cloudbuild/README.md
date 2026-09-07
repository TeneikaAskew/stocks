# Cloud Build inline configs

These YAML files are the inline `build` configs for the Cloud Build
triggers that replace some of the GitHub Actions workflows in this
repo. They live here for traceability / version control; the
authoritative copies are the trigger definitions in Cloud Build
itself (`gcloud builds triggers describe <NAME>`).

| File | Trigger | GHA workflow replaced |
|------|---------|----------------------|
| `apply-schema-cloudbuild.yaml`           | `apply-schema-on-change` (push to main on `gcp/schema.sql`) | `.github/workflows/apply-schema-migrations-on-change.yml` |
| `deploy-solyra-api-staging-cloudbuild.yaml` | `deploy-solyra-api-staging` (push to main on `platform/`, `lib/`, etc.) | `.github/workflows/deploy-platform-staging.yml` |
| `deploy-solyra-api-prod-cloudbuild.yaml`  | `deploy-solyra-api-prod` (manual) | `.github/workflows/promote-platform-prod.yml` |

## Required IAM grants on `trading-runner@adept-mountain-474619-d4.iam.gserviceaccount.com`

The triggers use `CLOUD_LOGGING_ONLY` logging because user-owned bucket
logging needs `roles/storage.admin` on the bucket and the regional
auto-bucket path requires explicit access too. Cloud Logging is the
cleanest path — but the SA needs to be able to write to Cloud Logging.

The `apply-schema-on-change` trigger has been proven end-to-end
without any extra grants (the SA already has `roles/run.developer`
which covers `run.jobs.run`, and the build output is small enough
that the missing `logging.logWriter` only produces a warning).

### What `trading-runner@` actually holds (read live 2026-09-05)

This list was previously incomplete, which is a real hazard for a project
rebuild and produced a false alarm on review (Codex, PR #990): reading only the
two grants below, the staging trigger's inline `docker push` looks like it must
fail for want of Artifact Registry write access. It does not — the SA holds
`artifactregistry.writer` at project level, which covers `uploadArtifacts` on
the Artifact-Registry-backed `gcr.io` repo. Verified:

```
$ gcloud projects get-iam-policy adept-mountain-474619-d4 \
    --flatten="bindings[].members" \
    --filter="bindings.members:trading-runner@..."
roles/aiplatform.user            roles/logging.logWriter
roles/artifactregistry.writer    roles/run.developer
roles/cloudbuild.builds.editor   roles/run.invoker
roles/cloudsql.client            roles/secretmanager.secretAccessor
roles/cloudsql.editor            roles/serviceusage.serviceUsageConsumer
                                 roles/storage.objectAdmin
```

The two that the staging trigger depends on and that a rebuild must not omit
are `artifactregistry.writer` (the `docker push` step, which now runs inline as
this SA rather than delegating to a nested Cloud Build) and `run.developer`
(the `gcloud run deploy` step). Re-verify before relying on this; a grant can
be revoked without any repo change.

The `deploy-solyra-api-staging` and `deploy-solyra-api-prod` triggers
need these grants before they'll run successfully:

```bash
SA=trading-runner@adept-mountain-474619-d4.iam.gserviceaccount.com

# 1) Write to Cloud Logging from within builds (required for CLOUD_LOGGING_ONLY).
gcloud projects add-iam-policy-binding adept-mountain-474619-d4 \
  --member="serviceAccount:${SA}" \
  --role='roles/logging.logWriter' \
  --condition=None

# 2) Start sub-builds. Kept for the historical deploy path that shelled out to
#    platform/deploy.sh (which calls `gcloud builds submit`). The staging
#    trigger now builds inline with gcr.io/cloud-builders/docker, so this is
#    no longer load-bearing for it, but platform/deploy.sh still needs it when
#    an operator runs it directly.
gcloud projects add-iam-policy-binding adept-mountain-474619-d4 \
  --member="serviceAccount:${SA}" \
  --role='roles/cloudbuild.builds.editor' \
  --condition=None
```

These bindings need `roles/resourcemanager.projectIamAdmin` (or
`roles/owner`) to set. The sandbox `claude-web@` SA only has
`roles/editor` which lacks `setIamPolicy` — must be applied by an
account with broader permissions.

After granting both, test:

```bash
gcloud builds triggers run deploy-solyra-api-staging --branch=main
# Then watch:
gcloud builds list --limit=1 --format='value(id,status)'
```

The third trigger (`deploy-solyra-api-prod`) is manual-only and is the ONLY
path that changes prod:

```bash
gcloud builds triggers run deploy-solyra-api-prod --branch=main
```

It no longer shifts traffic between tags on one service. It reads the image
digest currently serving `solyra-api-staging` and deploys that exact digest to
`solyra-api-prod`, so prod ships the bits staging validated rather than a fresh
build of whatever has since merged to main. The same IAM grants above cover it.

## Two staging deploy paths, and how they are kept from interleaving

`solyra-api-staging` is deployed by **two** things that cannot see each other:

* the `deploy-solyra-api-staging` trigger, on push to main
* `.github/workflows/deploy-staging.yml`, dispatched by an operator, which
  runs `platform/deploy.sh` → `gcloud builds submit platform/cloudbuild.yaml`

The workflow's `concurrency: deploy-staging` group serialises the workflow
against itself and has no reach over a Cloud Build run (Codex, PR #990). Two
mechanisms close the gap:

1. **Immutable tags, deploy by digest.** Both paths used to build, push and
   deploy the bare image — `:latest`, a mutable pointer both of them write. Two
   overlapping runs could push over each other between one run's push and its
   deploy, so `gcloud run deploy --image …:latest` resolved to an image that
   run never built. Since the promote trigger above deliberately promotes
   whatever digest is serving staging, a mutable tag put an unvalidated image
   one click from production. Both paths now tag with the commit
   (`$SHORT_SHA`, or `git rev-parse --short HEAD` in `platform/deploy.sh`),
   resolve that tag to its `sha256` digest, and deploy the **digest** — so a
   revision is pinned to exactly the artifact its run built.

2. **A shared interlock.** `assert_no_concurrent_staging_deploy.sh` runs first
   in both paths and fails loud if another deploy build is in flight. Both
   paths are Cloud Build runs in this project, so one can see the other through
   the build tags in the two configs (`solyra-api-staging-deploy` in the
   trigger config, `solyra-api-image-build` in `platform/cloudbuild.yaml` —
   `gcloud builds submit` has no flag for build tags, so each tag has to live
   in its own file, and the script scans for both). It needs
   `cloudbuild.builds.list`, which `roles/cloudbuild.builds.editor` already
   grants to both `trading-runner@` and the workflow's WIF SA — no new grants.

   It refuses rather than queues: a deploy that silently starts twenty minutes
   later is harder to reason about than one an operator re-runs. Because
   `platform/cloudbuild.yaml` serves prod as well and its tag is static, a prod
   deploy also blocks a concurrent staging deploy — conservative rather than
   wrong, since both are manual and both publish into the same repository.
