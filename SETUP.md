# Setup — auto-doc refresh workflow

One-time setup for `.github/workflows/refresh-architecture-docs.yml`. After this is done, the workflow runs itself on the 1st of every month and opens a PR if anything substantive changed.

> **Skip this if you don't care about auto-docs.** The repo works fine without the workflow firing — you'd just have to regenerate the docs manually using the prompts in `.github/prompts/`.

---

## What the workflow needs

1. **A GCP service account** with read-only access to: Cloud Asset Inventory, IAM, BigQuery (for the billing-export query), and Vertex AI (for the Gemini doc-generation calls)
2. **Workload Identity Federation (WIF)** so GitHub Actions can impersonate that service account without a long-lived JSON key
3. **Two GitHub repository secrets** holding the WIF config — no separate `GEMINI_API_KEY` is needed because the workflow uses Vertex AI, which authenticates via the same WIF-derived ADC
4. **Two enabled APIs** (Cloud Asset + Vertex AI) — the rest are typically already on for any GCP project

Total operator time: ~30 minutes for a first-time WIF setup, ~10 minutes if you've done WIF before.

---

## 1. Enable the Cloud Asset + Vertex AI APIs

```bash
gcloud services enable cloudasset.googleapis.com aiplatform.googleapis.com \
  --project=adept-mountain-474619-d4
```

The other APIs the workflow uses (`iam.googleapis.com`, `bigquery.googleapis.com`, `iamcredentials.googleapis.com`) are typically already on. If a step fails with a `... API has not been used in project ...` error, enable the named API the same way.

---

## 2. Create the dedicated service account

This SA only exists to run the doc refresh. Don't reuse `trading-system` — least-privilege is worth the 30 seconds.

```bash
PROJECT=adept-mountain-474619-d4
SA_NAME=arch-refresh-bot

gcloud iam service-accounts create "${SA_NAME}" \
  --project="${PROJECT}" \
  --display-name="Architecture doc refresh bot"

SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
echo "SA_EMAIL=${SA_EMAIL}"   # save this — you'll need it as a GitHub secret
```

---

## 3. Grant the IAM roles

Five roles cover everything the workflow does:

```bash
# Read asset inventory
gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudasset.viewer"

# Read IAM policy (needed to dump gcp_iam.json)
gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/iam.securityReviewer"

# Run the BigQuery billing-export rollup
gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.dataViewer"

gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.jobUser"

# Call Vertex AI Gemini for doc generation
gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.user"
```

> **Note on `roles/bigquery.dataViewer`:** This grant is project-wide. If you'd rather scope tighter, grant it on the `billing_export` dataset specifically:
> ```bash
> bq add-iam-policy-binding \
>   --member="serviceAccount:${SA_EMAIL}" \
>   --role="roles/bigquery.dataViewer" \
>   "${PROJECT}:billing_export"
> ```
> Either works. Project-wide is simpler; dataset-scoped is more paranoid.

---

## 4. Set up Workload Identity Federation

WIF lets GitHub Actions impersonate the SA without a JSON key. Two steps: create the pool/provider, then bind it to the SA.

### 4a. Create the WIF pool + provider

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
  --attribute-condition="assertion.repository=='${GH_REPO}'"
```

The `attribute-condition` clamp is the security boundary — only tokens issued for `TeneikaAskew/stocks` can use this provider. Don't skip it.

### 4b. Bind the SA to the provider

```bash
gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --project="${PROJECT}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${GH_REPO}"
```

### 4c. Get the WIF provider name (you'll need this)

```bash
WIF_PROVIDER="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/providers/github-provider"
echo "WIF_PROVIDER=${WIF_PROVIDER}"
```

Save both `WIF_PROVIDER` and `SA_EMAIL` — they go in GitHub secrets next.

---

## 5. Add two GitHub repository secrets

The workflow calls Vertex AI Gemini using the same WIF-derived ADC it already has — there is **no `GEMINI_API_KEY` secret to create.** That's the whole point of routing Gemini through Vertex instead of the public Generative Language API. Just two secrets:

Repo → Settings → Secrets and variables → Actions → New repository secret. Add:

| Secret name | Value |
|---|---|
| `GCP_WIF_PROVIDER` | The `WIF_PROVIDER` string from step 4c |
| `GCP_WIF_SA_EMAIL` | The `SA_EMAIL` from step 2 |

> **Why no API key?** Gemini is invoked with `GOOGLE_GENAI_USE_VERTEXAI=true`, which makes the Gemini CLI / SDK use Vertex AI as the provider. Vertex authenticates with Application Default Credentials, and the WIF auth step already populates ADC for the runner. One auth path covers asset inventory, BigQuery, and Gemini — strictly less secret sprawl than the previous Anthropic-key flow.

---

## 6. Test the workflow end-to-end before relying on it

The workflow has a `dry_run` input that generates the docs but skips the PR. Use it for the first run.

### Trigger a dry-run manually

GitHub UI: Repo → Actions → "Monthly architecture doc refresh" → Run workflow → set `dry_run=true` → Run.

CLI:
```bash
gh workflow run refresh-architecture-docs.yml -f dry_run=true
gh run watch
```

### What "passing" looks like

1. **Job completes in 10-25 minutes.** First run is at the high end (Gemini CLI cold-start + first BigQuery query authorization + Vertex AI cold-call).
2. **Step "Dump asset inventory" prints** `Inventory rows: 700-1000ish`. If it fails with permission errors → re-check the `cloudasset.viewer` grant.
3. **Step "Dump 90-day billing rollup" prints** `wrote billing_90d.json with N rows`. If it fails with `404 Not found: Dataset billing_export` → BigQuery billing export isn't enabled for this project; turn it on at Cloud Console → Billing → Billing Export → BigQuery → choose dataset `billing_export`. It needs ~24 hours of warmup before the first row appears.
4. **Steps "Regenerate ARCHITECTURE.md / DATA_DEPENDENCIES.md / COST_ANALYSIS.md / README.md" each take 1-6 minutes** and write the file. README runs last so it can read the freshly-regenerated other docs to populate its doc-map table + Mermaid embed + cost headlines. If a step fails with `403 PERMISSION_DENIED ... Vertex AI` → re-check the `roles/aiplatform.user` grant. If it fails with `404 model not found: gemini-2.5-pro` → confirm the model is available in `GCP_LOCATION` (`us-east1`); falling back to `us-central1` is safe.
5. **Step "Detect meaningful changes" reports** which files changed. On the first run after this PR lands, the docs are already current → expect "no meaningful changes" or only minor wording shifts.

### Validate the dry-run output

Even though the dry-run skips the PR, the regenerated files exist on the runner. To inspect:

```bash
# Pull the artifacts (you'd need to add an `actions/upload-artifact` step
# to the workflow if you want artifacts available — by default they aren't)
```

In practice: run `dry_run=false` once after dry-run passes, review the resulting PR carefully, merge it, then trust the monthly cadence.

### Failure modes you'll hit

| Symptom | Likely cause | Fix |
|---|---|---|
| `Permission denied on resource project ${PROJECT}` (asset step) | `cloudasset.viewer` not granted | Step 3, first command |
| `403 ... iamcredentials.generateAccessToken` | WIF binding wrong | Step 4b — verify `attribute.repository` matches your repo |
| `404 Not found: Dataset billing_export` | Billing export not enabled | Cloud Console → Billing → Billing Export |
| `403 PERMISSION_DENIED ... aiplatform.googleapis.com` | `roles/aiplatform.user` not granted, or Vertex AI API not enabled | Step 1 + Step 3 last command |
| `404 model not found: gemini-2.5-pro` | Model not available in `GCP_LOCATION` | Edit the workflow to set `GCP_LOCATION: us-central1` |
| Workflow runs but docs don't change | Gemini returned text without writing the file | Check the Gemini CLI logs in the step output — usually the model added preamble before the markdown instead of calling the Write tool. Tighten the relevant prompt under `.github/prompts/`. |

---

## 7. Rotation + ongoing maintenance

| Resource | Rotation cadence | How |
|---|---|---|
| WIF provider trust | Never (the OIDC issuer is Google's) | n/a |
| Service account roles | Audit annually — confirm the 5 grants in step 3 are the only ones | `gcloud projects get-iam-policy ${PROJECT} --flatten=bindings --filter=bindings.members:serviceAccount:${SA_EMAIL}` |
| Gemini model pin | Bump when a newer GA model lands (Gemini 2.5 Pro → 2.6 Pro etc.) | Edit `GEMINI_MODEL` in the workflow `env:` block, run a `dry_run=true`, merge if the diff looks reasonable |

The workflow itself is checked into git — changes to its behavior go through the normal PR flow. Same for the prompts under `.github/prompts/` (edit a prompt, the next refresh picks it up).

---

## Costs

The workflow runs once per month plus any manual triggers. Per run:
- **GitHub Actions**: ~15-30 min on `ubuntu-latest` (free tier covers ~2000 min/month; this is rounding error)
- **GCP (non-AI)**: cents (asset inventory + IAM read + one BigQuery query against ~1k rows)
- **Vertex AI Gemini 2.5 Pro**: ~$0.50–$1.00 per run for 4 doc regenerations. Pricing at the time of this writing is $1.25/M input tokens (≤200K context) and $10/M output tokens; a typical run reads ~200K context tokens (gcp_inventory.json + IAM dump + repo source files) and writes ~40K output tokens across all four files

Total: **~$0.50–$1.00/month** in Vertex AI spend on a monthly cadence, $0-1/month in GCP infra, $0 in GitHub Actions. Roughly half the cost of the previous Anthropic-keyed flow at comparable quality. Verify current pricing at [`ai.google.dev/pricing`](https://ai.google.dev/pricing) before assuming this is still accurate.
