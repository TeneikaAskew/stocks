# Cloud Build inline configs

These YAML files are the inline `build` configs for the Cloud Build
triggers that replace some of the GitHub Actions workflows in this
repo. They live here for traceability / version control; the
authoritative copies are the trigger definitions in Cloud Build
itself (`gcloud builds triggers describe <NAME>`).

| File | Trigger | GHA workflow replaced |
|------|---------|----------------------|
| `apply-schema-cloudbuild.yaml`           | `apply-schema-on-change` (push to main on `gcp/schema.sql`) | `.github/workflows/apply-schema-migrations-on-change.yml` |
| `deploy-platform-staging-cloudbuild.yaml` | `deploy-platform-staging` (push to main on `platform/`, `lib/`, etc.) | `.github/workflows/deploy-platform-staging.yml` |
| `promote-platform-prod-cloudbuild.yaml`  | `promote-platform-prod` (manual) | `.github/workflows/promote-platform-prod.yml` |

## Required IAM grants on `trading-runner@adept-mountain-474619-d4.iam.gserviceaccount.com`

The triggers use `CLOUD_LOGGING_ONLY` logging because user-owned bucket
logging needs `roles/storage.admin` on the bucket and the regional
auto-bucket path requires explicit access too. Cloud Logging is the
cleanest path — but the SA needs to be able to write to Cloud Logging.

The `apply-schema-on-change` trigger has been proven end-to-end
without any extra grants (the SA already has `roles/run.developer`
which covers `run.jobs.run`, and the build output is small enough
that the missing `logging.logWriter` only produces a warning).

The `deploy-platform-staging` and `promote-platform-prod` triggers
need these grants before they'll run successfully:

```bash
SA=trading-runner@adept-mountain-474619-d4.iam.gserviceaccount.com

# 1) Write to Cloud Logging from within builds (required for CLOUD_LOGGING_ONLY).
gcloud projects add-iam-policy-binding adept-mountain-474619-d4 \
  --member="serviceAccount:${SA}" \
  --role='roles/logging.logWriter' \
  --condition=None

# 2) Start sub-builds (platform/deploy.sh internally calls `gcloud builds submit`
#    to build the trading-platform Docker image). Without this, deploy-platform-
#    staging fails at the sub-build step.
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
gcloud builds triggers run deploy-platform-staging --branch=main
# Then watch:
gcloud builds list --limit=1 --format='value(id,status)'
```

The third trigger (`promote-platform-prod`) is manual-only; invoke
with `gcloud builds triggers run promote-platform-prod` whenever
you want to route 100% traffic to the current `staging`-tagged
revision. The same IAM grants above cover it.
