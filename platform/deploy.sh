#!/usr/bin/env bash
# Build and deploy the trading platform to Cloud Run.
# Run from repo root:  ./platform/deploy.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-adept-mountain-474619-d4}"
REGION="${REGION:-us-east1}"
SERVICE="${SERVICE:-trading-platform}"
INSTANCE="${INSTANCE:-${PROJECT_ID}:${REGION}:trading-db}"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE}"

# DB credentials — set DB_USER / DB_NAME in env, store DB_PASS in Secret Manager.
DB_USER="${DB_USER:?set DB_USER (e.g. export DB_USER=postgres)}"
DB_NAME="${DB_NAME:?set DB_NAME (e.g. export DB_NAME=trading)}"
DB_PASS_SECRET="${DB_PASS_SECRET:-trading-db-pass}"

# Auth: PUBLIC=1 ./deploy.sh skips the IAM gate (then put IAP or app-level auth in front).
ALLOW_UNAUTH_FLAG="--no-allow-unauthenticated"
if [[ "${PUBLIC:-0}" == "1" ]]; then
  ALLOW_UNAUTH_FLAG="--allow-unauthenticated"
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

# 3. Deploy
echo ">> deploying to Cloud Run"
gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --add-cloudsql-instances "${INSTANCE}" \
  --set-env-vars "CLOUD_SQL_CONNECTION_NAME=${INSTANCE},DB_USER=${DB_USER},DB_NAME=${DB_NAME},GCS_BUCKET=${PROJECT_ID}-trading-data,GCP_PROJECT_ID=${PROJECT_ID},PLAYWRIGHT_TESTER_SA=playwright-tester@${PROJECT_ID}.iam.gserviceaccount.com,IAP_OAUTH_CLIENT_ID=369001918367-t5qrahnqdaasaifvk6akpqkpjk9vli58.apps.googleusercontent.com" \
  --set-secrets "DB_PASS=${DB_PASS_SECRET}:latest" \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 5 \
  ${ALLOW_UNAUTH_FLAG}

echo ">> done"
gcloud run services describe "${SERVICE}" --region "${REGION}" --format='value(status.url)'
