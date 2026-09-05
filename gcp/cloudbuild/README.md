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
