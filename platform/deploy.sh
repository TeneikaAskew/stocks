#!/usr/bin/env bash
# Build and deploy the trading platform to Cloud Run.
# Run from repo root:  ./platform/deploy.sh
#
# Modes:
#   ./platform/deploy.sh                  prod deploy (trading-platform, behind IAP)
#   STAGING=1 ./platform/deploy.sh        prod service, new revision tagged `staging`,
#                                         no traffic — shares prod's IAP (see note below)
#   STAGING_SERVICE=1 ./platform/deploy.sh  SEPARATE public staging service
#                                         (trading-platform-staging) with NO IAP +
#                                         the app-level passcode gate. Prod untouched.
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

# ── Separate public staging service ────────────────────────────────────────
# trading-platform-staging runs WITHOUT IAP (--allow-unauthenticated) because
# IAP on Cloud Run is service-level and can't be dropped per-revision. The
# app-level passcode gate (ALLOW_AUTH_BYPASS=1 + STAGING_PASSCODE) re-protects
# the API so the service isn't wide-open. Prod (trading-platform) is untouched
# and stays behind IAP.
#
# One-time prerequisites (run by an operator with run.admin — NOT the CI SA):
#   1. Create the passcode secret:
#        printf '%s' 'YOUR_PASSCODE' | gcloud secrets create staging-passcode \
#          --data-file=- --project=${PROJECT_ID}
#   2. Let the runtime SA read it:
#        gcloud secrets add-iam-policy-binding staging-passcode \
#          --member="serviceAccount:trading-platform-svc@${PROJECT_ID}.iam.gserviceaccount.com" \
#          --role=roles/secretmanager.secretAccessor --project=${PROJECT_ID}
#   3. --allow-unauthenticated needs run.services.setIamPolicy; deploying as a
#      run.admin principal grants allUsers invoker automatically. (If org policy
#      DRS blocks allUsers, the public service can't be created — escalate.)
if [[ "${STAGING_SERVICE:-0}" == "1" ]]; then
  SERVICE="trading-platform-staging"
  PUBLIC=1   # public ingress; the passcode gate is the access control
  echo ">> STAGING_SERVICE mode: deploying public ${SERVICE} (no IAP, passcode-gated)"
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

if [[ "${STAGING_SERVICE:-0}" == "1" ]]; then
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

# 2b. Staging service requires the passcode secret to exist
if [[ "${STAGING_SERVICE:-0}" == "1" ]]; then
  if ! gcloud secrets describe "${STAGING_PASSCODE_SECRET}" >/dev/null 2>&1; then
    echo ">> secret '${STAGING_PASSCODE_SECRET}' not found — create it with:"
    echo "   printf '%s' 'YOUR_STAGING_PASSCODE' | gcloud secrets create ${STAGING_PASSCODE_SECRET} --data-file=- --project=${PROJECT_ID}"
    exit 1
  fi
fi

# 3. Deploy
# --memory 2Gi: /api/options/{ticker}/{date}/levels loads the full options
# chain (all expiries) and computes GEX across it; for the latest/largest
# snapshot this peaks just over 1 GiB. At 1Gi the instance OOM-killed mid-request
# (503 + cascading connection errors on co-located requests). 2Gi gives headroom.
echo ">> deploying to Cloud Run"
gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --add-cloudsql-instances "${INSTANCE}" \
  --service-account "${RUN_SA:-trading-platform-svc@${PROJECT_ID}.iam.gserviceaccount.com}" \
  --set-env-vars "${ENV_VARS}" \
  --set-secrets "${SECRETS}" \
  --memory 2Gi \
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
