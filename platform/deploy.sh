#!/usr/bin/env bash
# Build and deploy the trading platform to Cloud Run.
# Run from repo root:  ./platform/deploy.sh
#
# Modes:
#   ./platform/deploy.sh                  prod deploy (trading-platform, behind IAP)
#   STAGING=1 ./platform/deploy.sh        prod service, new revision tagged `staging`,
#                                         no traffic — shares prod's IAP (see note below)
#   STAGING_SERVICE=1 ./platform/deploy.sh  SEPARATE staging service
#                                         (trading-platform-staging). PRIVATE by
#                                         default (Cloud Run IAM; reach via
#                                         `gcloud run services proxy`). Add
#                                         STAGING_PUBLIC=1 for the public,
#                                         passcode-gated variant. Prod untouched.
#                                         Point it at a read-only DB role with:
#                                           DB_USER=staging_readonly \
#                                           DB_PASS_SECRET=staging-db-readonly-pass
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-adept-mountain-474619-d4}"
REGION="${REGION:-us-east1}"
SERVICE="${SERVICE:-trading-platform}"
INSTANCE="${INSTANCE:-${PROJECT_ID}:${REGION}:trading-db}"
# The image is the same app for every service — build once, reuse for staging.
IMAGE_NAME="${IMAGE_NAME:-trading-platform}"
IMAGE="gcr.io/${PROJECT_ID}/${IMAGE_NAME}"

# DB credentials — set DB_USER / DB_NAME in env, store DB_PASS in Secret Manager.
DB_USER="${DB_USER:?set DB_USER (e.g. export DB_USER=postgres)}"
DB_NAME="${DB_NAME:?set DB_NAME (e.g. export DB_NAME=trading)}"
DB_PASS_SECRET="${DB_PASS_SECRET:-trading-db-pass}"
STAGING_PASSCODE_SECRET="${STAGING_PASSCODE_SECRET:-staging-passcode}"

# ── Separate staging service ────────────────────────────────────────────────
# trading-platform-staging is a SEPARATE service so prod (trading-platform)'s
# IAP is untouched (IAP is service-level and can't be dropped per-revision).
#
# Two variants:
#   * PRIVATE (default): --no-allow-unauthenticated. Cloud Run IAM gates it, so
#     it's reachable from the sandbox via `gcloud run services proxy` (which
#     `claude-web@`/editor can do — no run.services.setIamPolicy needed). The
#     app-level passcode gate is left OFF because IAM already gates every call.
#   * PUBLIC (STAGING_PUBLIC=1): --allow-unauthenticated + the passcode gate
#     (ALLOW_AUTH_BYPASS=1 + STAGING_PASSCODE) re-protects the now-internet-
#     facing API. Needs run.admin for --allow-unauthenticated and may be
#     blocked by the DRS org policy (iam.allowedPolicyMemberDomains).
#
# Either way, point staging at a READ-ONLY DB role (DB_USER/DB_PASS_SECRET) so a
# stray write spec can't mutate prod data — the connection is to the same
# trading-db instance.
#
# Public-variant one-time prerequisite (operator with run.admin):
#   printf '%s' 'YOUR_PASSCODE' | gcloud secrets create staging-passcode \
#     --data-file=- --project=${PROJECT_ID}
#   gcloud secrets add-iam-policy-binding staging-passcode \
#     --member="serviceAccount:trading-platform-svc@${PROJECT_ID}.iam.gserviceaccount.com" \
#     --role=roles/secretmanager.secretAccessor --project=${PROJECT_ID}
if [[ "${STAGING_SERVICE:-0}" == "1" ]]; then
  SERVICE="trading-platform-staging"
  if [[ "${STAGING_PUBLIC:-0}" == "1" ]]; then
    PUBLIC=1   # internet-facing; the passcode gate is the access control
    BYPASS=1   # enable ALLOW_AUTH_BYPASS + mount the passcode secret
    echo ">> STAGING_SERVICE mode: PUBLIC ${SERVICE} (no IAP, passcode-gated)"
  else
    echo ">> STAGING_SERVICE mode: PRIVATE ${SERVICE} (Cloud Run IAM; reach via 'gcloud run services proxy')"
  fi
fi

# Auth: PUBLIC=1 ./deploy.sh skips the IAM gate (then put IAP or app-level auth in front).
# In STAGING (revision-tag) mode the service-level IAM policy is left untouched — a staging
# revision shares the service's existing auth posture, and re-asserting it
# would need run.services.setIamPolicy, which the CI deploy SA does not hold.
AUTH_FLAGS=()
if [[ "${STAGING:-0}" != "1" ]]; then
  if [[ "${PUBLIC:-0}" == "1" ]]; then
    AUTH_FLAGS=(--allow-unauthenticated)
  else
    AUTH_FLAGS=(--no-allow-unauthenticated)
  fi
fi

# Staging (revision-tag): STAGING=1 ./deploy.sh deploys a new revision tagged
# `staging` that receives NO production traffic. The prod URL keeps serving the
# current 100%-traffic revision. Promote later with:
#   gcloud run services update-traffic "${SERVICE}" --region "${REGION}" --to-tags=staging=100
STAGING_FLAGS=()
if [[ "${STAGING:-0}" == "1" ]]; then
  STAGING_FLAGS=(--no-traffic --tag staging)
  echo ">> STAGING mode: new revision tagged 'staging', no production traffic"
fi

# ── Env vars + secrets (composed so staging can append its own) ────────────
ENV_VARS="CLOUD_SQL_CONNECTION_NAME=${INSTANCE},DB_USER=${DB_USER},DB_NAME=${DB_NAME},GCS_BUCKET=${PROJECT_ID}-trading-data,GCP_PROJECT_ID=${PROJECT_ID},PLAYWRIGHT_TESTER_SA=playwright-tester@${PROJECT_ID}.iam.gserviceaccount.com,IAP_OAUTH_CLIENT_ID=369001918367-t5qrahnqdaasaifvk6akpqkpjk9vli58.apps.googleusercontent.com"
SECRETS="DB_PASS=${DB_PASS_SECRET}:latest,AV_API_KEY=av-api-key:latest,ALPHA_VANTAGE_API_KEY=av-api-key:latest"

if [[ "${BYPASS:-0}" == "1" ]]; then
  ENV_VARS="${ENV_VARS},ALLOW_AUTH_BYPASS=1"
  SECRETS="${SECRETS},STAGING_PASSCODE=${STAGING_PASSCODE_SECRET}:latest"
fi

echo ">> project=${PROJECT_ID} region=${REGION} service=${SERVICE}"
gcloud config set project "${PROJECT_ID}" >/dev/null

# 1. Build image (uses repo-root .dockerignore, build context is repo root)
echo ">> building ${IMAGE}"
gcloud builds submit \
  --config platform/cloudbuild.yaml \
  --substitutions "_IMAGE=${IMAGE}" \
  .

# 2. One-time: create the password secret if missing
if ! gcloud secrets describe "${DB_PASS_SECRET}" >/dev/null 2>&1; then
  echo ">> secret '${DB_PASS_SECRET}' not found — create it with:"
  echo "   echo -n 'YOUR_DB_PASSWORD' | gcloud secrets create ${DB_PASS_SECRET} --data-file=-"
  exit 1
fi

# 2b. Public staging variant requires the passcode secret to exist
if [[ "${BYPASS:-0}" == "1" ]]; then
  if ! gcloud secrets describe "${STAGING_PASSCODE_SECRET}" >/dev/null 2>&1; then
    echo ">> secret '${STAGING_PASSCODE_SECRET}' not found — create it with:"
    echo "   printf '%s' 'YOUR_STAGING_PASSCODE' | gcloud secrets create ${STAGING_PASSCODE_SECRET} --data-file=- --project=${PROJECT_ID}"
    exit 1
  fi
fi

# 3. Deploy
echo ">> deploying to Cloud Run"
gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --add-cloudsql-instances "${INSTANCE}" \
  --service-account "${RUN_SA:-trading-platform-svc@${PROJECT_ID}.iam.gserviceaccount.com}" \
  --set-env-vars "${ENV_VARS}" \
  --set-secrets "${SECRETS}" \
  --memory 1Gi \
  --cpu 1 \
  --cpu-throttling \
  --timeout 300 \
  --min-instances 0 \
  --max-instances 5 \
  ${AUTH_FLAGS[@]+"${AUTH_FLAGS[@]}"} \
  ${STAGING_FLAGS[@]+"${STAGING_FLAGS[@]}"}

echo ">> done"
if [[ "${STAGING:-0}" == "1" ]]; then
  echo ">> staging revision URL (no production traffic):"
  # The staging-tagged revision is reachable at the service URL with a
  # `staging---` host prefix — Cloud Run's stable tag-URL convention.
  base_url="$(gcloud run services describe "${SERVICE}" --region "${REGION}" --format='value(status.url)')"
  echo "https://staging---${base_url#https://}"
else
  gcloud run services describe "${SERVICE}" --region "${REGION}" --format='value(status.url)'
fi
