# Setup: Workload Identity Federation for the deploy and verify workflows

**Last reviewed:** unknown · **Last scanned:** 2026-11-03 · **Owner:** TBD

One-time setup of the Workload Identity Federation (WIF) trust that `.github/workflows/deploy-staging.yml` and `.github/workflows/verify-docs-against-live.yml` use to reach GCP without a long-lived JSON key. The monthly documentation refresh this file was first written for was retired on 2026-11-10; its Vertex AI, Gemini and billing-export steps are gone, and what remains is the identity both workflows still share.

---

## What the workflows need

1. **A GCP service account** the workflows impersonate, with read access to the live project (the verifier) and the deploy grants listed in the header of `deploy-staging.yml`
2. **Workload Identity Federation** so GitHub Actions can impersonate that service account without a JSON key
3. **Two GitHub repository secrets** holding the WIF config

---

## 1. Create the service account

Don't reuse `trading-system`; least privilege is worth the 30 seconds.

```bash
PROJECT=adept-mountain-474619-d4
SA_NAME=arch-refresh-bot

gcloud iam service-accounts create "${SA_NAME}" \
  --project="${PROJECT}" \
  --display-name="GitHub Actions WIF identity"

SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
echo "SA_EMAIL=${SA_EMAIL}"   # save this, you'll need it as a GitHub secret
```

---

## 2. Grant the read-only roles

`verify-docs-against-live.yml` reads Cloud Run, Cloud Scheduler, Cloud Build, Cloud SQL, Secret Manager, Pub/Sub, Logging, Cloud Tasks and Artifact Registry through `scripts/maintenance/doc_inventory.py`, so the identity needs viewer roles on each. The loop is idempotent; re-run it whenever the service account is rebuilt:

```bash
for ROLE in roles/run.viewer roles/cloudscheduler.viewer roles/cloudbuild.builds.viewer \
            roles/cloudsql.viewer roles/cloudsql.client roles/secretmanager.viewer \
            roles/pubsub.viewer roles/logging.viewer roles/cloudtasks.viewer \
            roles/artifactregistry.reader; do
  gcloud projects add-iam-policy-binding "${PROJECT}" \
    --member="serviceAccount:${SA_EMAIL}" --role="${ROLE}" --condition=None
done
# sql-dumps listing (pg_dump health line)
gcloud storage buckets add-iam-policy-binding "gs://${PROJECT}-trading-data" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/storage.objectViewer"
```

The deploy path needs more than viewer roles; the header of `deploy-staging.yml` lists them. The Cloud SQL GitHub secrets (`CLOUD_SQL_CONNECTION_NAME`, `DB_USER`, `DB_PASS`, `DB_NAME`) that `deploy-staging.yml` uses are stored separately; nothing here adds to them.

---

## 3. Set up Workload Identity Federation

WIF lets GitHub Actions impersonate the SA without a JSON key. Two steps: create the pool/provider, then bind it to the SA.

### 3a. Create the WIF pool + provider

```bash
PROJECT=adept-mountain-474619-d4
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT}" --format='value(projectNumber)')
GH_REPO=TeneikaAskew/stocks    # owner/repo

# 1. Create the pool (one per project — reuse if you already have one)
gcloud iam workload-identity-pools create "github-pool" \
  --project="${PROJECT}" --location="global" \
  --display-name="GitHub Actions"

# 2. Create the provider for this specific repo
gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --project="${PROJECT}" --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub OIDC" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository=='${GH_REPO}' && assertion.ref=='refs/heads/main'"
```

The `attribute-condition` clamp is the security boundary — only tokens issued
for `TeneikaAskew/stocks` **runs on `main`** can use this provider. Don't skip
either half: the repository clause alone is not enough once the SA holds
deploy powers, because `workflow_dispatch` executes the workflow file from
whatever ref the caller selects — a write-capable actor could push a branch
whose workflow drops its own in-file ref guard and dispatch that (Codex,
PR #983). `assertion.ref` is only issued for branch/tag refs, so this
condition also inherently blocks `pull_request`-triggered tokens. Every
workflow using this provider must run from `main` (both current ones do:
`verify-docs-against-live.yml`, and `deploy-staging.yml` dispatch-only with a
fail-loud main guard as its UX rail).

If the provider already exists (it does in this project), roll the condition
forward instead of recreating:

```bash
gcloud iam workload-identity-pools providers update-oidc "github-provider" \
  --project="${PROJECT}" --location="global" \
  --workload-identity-pool="github-pool" \
  --attribute-condition="assertion.repository=='${GH_REPO}' && assertion.ref=='refs/heads/main'"
```

### 3b. Bind the SA to the provider

```bash
gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --project="${PROJECT}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${GH_REPO}"
```

### 3c. Get the WIF provider name (you'll need this)

```bash
WIF_PROVIDER="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/providers/github-provider"
echo "WIF_PROVIDER=${WIF_PROVIDER}"
```

Save both `WIF_PROVIDER` and `SA_EMAIL` — they go in GitHub secrets next.

---

## 4. Add two GitHub repository secrets

Repo → Settings → Secrets and variables → Actions → New repository secret. Add:

| Secret name | Value |
|---|---|
| `GCP_WIF_PROVIDER` | The `WIF_PROVIDER` string from step 3c |
| `GCP_WIF_SA_EMAIL` | The `SA_EMAIL` from step 1 |

---

## 5. Rotation and ongoing maintenance

| Resource | Rotation cadence | How |
|---|---|---|
| WIF provider trust | Never (the OIDC issuer is Google's) | n/a |
| Service account roles | Audit annually | `gcloud projects get-iam-policy ${PROJECT} --flatten=bindings --filter=bindings.members:serviceAccount:${SA_EMAIL}` |

The workflows are checked into git; changes to their behavior go through the normal PR flow.

### Failure modes you'll hit

| Symptom | Likely cause | Fix |
|---|---|---|
| `403 ... iamcredentials.generateAccessToken` | WIF binding wrong | Step 3b: verify `attribute.repository` matches your repo |
| `The given credential is rejected by the attribute condition` | Dispatched from a branch other than `main` | Merge first, then dispatch from `main` |
| `Permission denied on resource project ${PROJECT}` | A viewer role from step 2 is missing | Re-run the step 2 loop |
