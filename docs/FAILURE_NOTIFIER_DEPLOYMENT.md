# Failure Notifier Deployment Plan

Step-by-step guide to deploy the GCP Cloud Run Job failure notifier, which sends Discord alerts and creates GitHub issues whenever any Cloud Run Job fails.

## Architecture Overview

```
Cloud Run Job fails
  → Cloud Logging (severity >= ERROR)
    → Logging Sink (filter: resource.type="cloud_run_job")
      → Pub/Sub topic (gcp-job-failures)
        → Push subscription (OIDC auth)
          → failure-notifier Cloud Run Service
            ├─ Discord webhook (embed with error + log link)
            └─ GitHub issue (create or comment on existing)
```

**Dead-letter path:** After 5 failed delivery attempts, messages go to `gcp-job-failures-dlq` instead of retrying forever.

---

## Prerequisites

### 1. GCP CLI authenticated

```bash
gcloud auth login
gcloud config set project adept-mountain-474619-d4
```

Verify:
```bash
gcloud config get-value project
# Expected: adept-mountain-474619-d4
```

### 2. Base infrastructure already provisioned

The following must exist before deploying the notifier (created by `./gcp/deploy.sh setup`):

- Cloud SQL instance with `trading` database
- GCS bucket `adept-mountain-474619-d4-trading-data`
- Service account `trading-runner@adept-mountain-474619-d4.iam.gserviceaccount.com`
- Artifact Registry repo `us-east1-docker.pkg.dev/adept-mountain-474619-d4/trading/trading-system`

Verify:
```bash
gcloud iam service-accounts describe trading-runner@adept-mountain-474619-d4.iam.gserviceaccount.com
gcloud artifacts repositories describe trading --location=us-east1
```

### 3. Discord webhook URL stored in Secret Manager

The notifier reads `DISCORD_WEBHOOK_URL` from the dedicated `discord-webhook-gcp` secret (a separate Discord channel for GCP job failures). The shared `discord-webhook-insights` secret is used by the rest of the platform (briefs, signal alerts) but NOT by the failure-notifier. Verify the GCP-errors secret exists:
```bash
gcloud secrets versions access latest --secret=discord-webhook-gcp --quiet | head -c 30
# Should print the beginning of your webhook URL
```

If missing, create it:
```bash
printf 'https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN' \
  | gcloud secrets create discord-webhook-gcp --replication-policy=automatic --data-file=-
```

### 4. Docker installed (for local testing only)

```bash
docker --version
```

---

## Deployment Steps

### Step 1: Store GitHub PAT in Secret Manager

This creates two secrets: `github-pat` (for creating issues) and `github-repo` (the target repo slug).

```bash
make setup-notifier
```

**What happens automatically:**
1. PAT is pulled from GCP Secret Manager (`gh-stocks-repo-pat` in project `28960574877`)
2. Repo slug is auto-detected from `git remote get-url origin` → `TeneikaAskew/stocks`
3. Both values are stored as new secrets in your project's Secret Manager

**Verify:**
```bash
gcloud secrets describe github-pat --quiet
gcloud secrets describe github-repo --quiet
gcloud secrets versions access latest --secret=github-repo --quiet
# Expected: TeneikaAskew/stocks
```

**Alternative (if auto-detection fails):**
```bash
# Pass PAT via env var
STOCKS_REPO_PAT=ghp_xxxx make setup-notifier
```

### Step 2: Build and deploy the notifier

```bash
make notifier
```

**What this does (in order):**
1. Builds Docker image and pushes to Artifact Registry
2. Deploys `failure-notifier` Cloud Run Service (512Mi, 0-3 instances, unauthenticated access blocked)
3. Mounts `github-pat` and `github-repo` from Secret Manager via `--set-secrets`
4. Creates Pub/Sub topic `gcp-job-failures`
5. Grants Pub/Sub service account `roles/run.invoker` on the service
6. Creates dead-letter topic `gcp-job-failures-dlq`
7. Creates push subscription `gcp-job-failures-push` with OIDC auth and max 5 delivery attempts
8. Grants Pub/Sub SA publish/subscribe permissions on DLQ and subscription
9. Creates Cloud Logging sink `gcp-job-failures-sink` with filter:
   ```
   resource.type="cloud_run_job" AND severity>=ERROR AND resource.labels.job_name!="failure-notifier"
   ```
10. Grants sink writer identity `roles/pubsub.publisher` on the topic

**Expected output (last lines):**
```
  Service URL: https://failure-notifier-XXXXXXXXXX-ue.a.run.app
  ...
failure-notifier deployed and wired to Cloud Logging.
```

### Step 3: Verify the deployment

Run these checks to confirm everything is wired correctly:

```bash
# 3a. Service is deployed and healthy
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "$(gcloud run services describe failure-notifier --region us-east1 --format='value(status.url)')"
# Expected: 200

# 3b. Pub/Sub topic exists
gcloud pubsub topics describe gcp-job-failures --quiet
# Should return topic metadata

# 3c. Subscription is wired to the service
gcloud pubsub subscriptions describe gcp-job-failures-push --quiet \
  --format='value(pushConfig.pushEndpoint)'
# Should print the failure-notifier service URL

# 3d. Dead-letter topic exists
gcloud pubsub topics describe gcp-job-failures-dlq --quiet

# 3e. Logging sink is active
gcloud logging sinks describe gcp-job-failures-sink \
  --format='yaml(filter,destination,writerIdentity)'

# 3f. Secrets are mounted (not visible in env vars)
gcloud run services describe failure-notifier --region us-east1 \
  --format='yaml(spec.template.spec.containers[0].env)'
# GITHUB_PAT and GITHUB_REPO should NOT appear here (they're in --set-secrets)
```

---

## Testing

### Test 1: Unit tests (local, no GCP needed)

```bash
python -m pytest tests/test_failure_notifier.py -v
```

**Expected:** 11/11 passing. Covers:
- Pub/Sub envelope parsing (valid JSON, empty data, non-JSON payload)
- Log entry field extraction and Cloud Console URL building
- Discord payload truncation for long error messages
- GitHub issue dedup (existing issue → comment, no match → create)
- Self-loop suppression (`job_name == "failure-notifier"` → skip)
- Graceful skip when env vars missing
- End-to-end handler fires both Discord and GitHub channels

### Test 2: Health check (after deployment)

```bash
SERVICE_URL=$(gcloud run services describe failure-notifier --region us-east1 --format='value(status.url)')
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" "${SERVICE_URL}"
# Expected: "ok"
```

### Test 3: Force a real job failure

Trigger a deliberate error on any Cloud Run Job to verify the full pipeline:

```bash
# Option A: Execute a job with a bad command (will fail immediately)
gcloud run jobs update fetch-market-data --region us-east1 \
  --command "python,-c,import sys; sys.exit(1)" --quiet
gcloud run jobs execute fetch-market-data --region us-east1

# IMPORTANT: Restore the original command after testing!
gcloud run jobs update fetch-market-data --region us-east1 \
  --command "python,-m,gcp.fetchers.fetch_market_data" --quiet
```

```bash
# Option B: Safer — create a throwaway test job
gcloud run jobs create test-failure-notifier \
  --image us-east1-docker.pkg.dev/adept-mountain-474619-d4/trading/trading-system \
  --region us-east1 --memory 256Mi --cpu 1 --max-retries 0 \
  --command "python,-c,raise Exception('notifier test')" --quiet

gcloud run jobs execute test-failure-notifier --region us-east1

# Clean up after test
gcloud run jobs delete test-failure-notifier --region us-east1 --quiet
```

**Within ~60 seconds, verify:**

1. **Discord:** A red embed appears in your webhook channel with:
   - Title: "GCP job failed: test-failure-notifier" (or fetch-market-data)
   - Error snippet in a code block
   - Clickable "View logs" link to Cloud Console

2. **GitHub issue:** A new issue is created at `TeneikaAskew/stocks` with:
   - Title: "GCP job failed: test-failure-notifier"
   - Labels: `gcp-job-failure`, `test-failure-notifier`, `automated`
   - Body with job name, execution name, error, and log link

### Test 4: Verify dedup (repeat failure → comment, not new issue)

```bash
# Run the same failing job again
gcloud run jobs execute test-failure-notifier --region us-east1
```

**Verify:** A **comment** is appended to the existing open issue (not a new issue created).

### Test 5: Verify self-loop protection

```bash
# Check the logging sink filter excludes the notifier
gcloud logging sinks describe gcp-job-failures-sink --format='value(filter)'
# Must contain: resource.labels.job_name!="failure-notifier"

# Also confirm the notifier is a Service (not Job) — its logs use
# resource.type="cloud_run_revision", which the sink filter
# (resource.type="cloud_run_job") already excludes
gcloud run services describe failure-notifier --region us-east1 \
  --format='value(kind)'
# Expected: Service
```

### Test 6: Verify dead-letter queue works

```bash
# Check subscription config
gcloud pubsub subscriptions describe gcp-job-failures-push \
  --format='yaml(deadLetterPolicy)'
# Expected:
#   deadLetterPolicy:
#     deadLetterTopic: projects/adept-mountain-474619-d4/topics/gcp-job-failures-dlq
#     maxDeliveryAttempts: 5
```

---

## Rollback

If something goes wrong, tear down in reverse order:

```bash
# Delete the logging sink
gcloud logging sinks delete gcp-job-failures-sink --quiet

# Delete the Pub/Sub subscription
gcloud pubsub subscriptions delete gcp-job-failures-push --quiet

# Delete the Pub/Sub topics
gcloud pubsub topics delete gcp-job-failures-dlq --quiet
gcloud pubsub topics delete gcp-job-failures --quiet

# Delete the Cloud Run service
gcloud run services delete failure-notifier --region us-east1 --quiet

# Optionally delete the secrets (only if you want to redo setup-notifier)
gcloud secrets delete github-pat --quiet
gcloud secrets delete github-repo --quiet
```

---

## Monitoring & Ongoing Operations

### Check notifier logs

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="failure-notifier"' \
  --limit=20 --format='table(timestamp,severity,textPayload)'
```

### Check dead-letter messages (messages that failed all 5 attempts)

```bash
# Create a temporary pull subscription to inspect DLQ
gcloud pubsub subscriptions create dlq-reader \
  --topic=gcp-job-failures-dlq --quiet
gcloud pubsub subscriptions pull dlq-reader --auto-ack --limit=10
gcloud pubsub subscriptions delete dlq-reader --quiet
```

### Rotate the GitHub PAT

```bash
# Add a new version (the :latest alias auto-updates)
printf 'ghp_NEW_TOKEN_HERE' | gcloud secrets versions add github-pat --data-file=-

# The next cold-started instance will pick up the new token automatically
# (no redeployment needed thanks to --set-secrets)
```

### Check which jobs are monitored

Every Cloud Run Job with `severity >= ERROR` is automatically captured. List all jobs:
```bash
gcloud run jobs list --region us-east1 --format='table(name,status.latestCreatedExecution.name)'
```

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `make setup-notifier` | One-time: store PAT + repo in Secret Manager |
| `make notifier` | Build + deploy everything |
| `make test` | Run all unit tests (includes notifier tests) |
| `./gcp/deploy.sh notifier` | Deploy without rebuilding Docker image |
| `./gcp/deploy.sh setup-notifier-secrets` | Same as `make setup-notifier` |

| Resource | Name |
|----------|------|
| Cloud Run Service | `failure-notifier` |
| Pub/Sub Topic | `gcp-job-failures` |
| Pub/Sub DLQ Topic | `gcp-job-failures-dlq` |
| Pub/Sub Subscription | `gcp-job-failures-push` |
| Logging Sink | `gcp-job-failures-sink` |
| Secret (PAT) | `github-pat` |
| Secret (repo) | `github-repo` |
| Secret (PAT source) | `gh-stocks-repo-pat` (project 28960574877) |
