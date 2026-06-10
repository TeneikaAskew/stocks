#!/usr/bin/env bash
# Build and deploy the trading platform to Cloud Run.
# Run from repo root:  ./platform/deploy.sh
#
# Modes:
#   ./platform/deploy.sh                  prod deploy (trading-platform; AUTH_MODE=iap, behind IAP)
#   STAGING=1 ./platform/deploy.sh        prod service, new revision tagged `staging`,
#                                         no traffic — shares prod's IAP (see note below)
#   STAGING_SERVICE=1 ./platform/deploy.sh  SEPARATE PUBLIC staging service
#                                         (trading-platform-staging) with the in-app
#                                         Firebase login (AUTH_MODE=firebase). Prod
#                                         untouched. Requires the Firebase web config +
#                                         a read-only DB role, e.g.:
#                                           FIREBASE_API_KEY=… FIREBASE_AUTH_DOMAIN=… FIREBASE_APP_ID=… \
#                                           DB_USER=staging_readonly DB_PASS_SECRET=trading-db-pass \
#                                           STAGING_SERVICE=1 ./platform/deploy.sh
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

# ── Separate PUBLIC staging service with the in-app Firebase login ───────────
# trading-platform-staging is a SEPARATE service so prod (trading-platform)'s
# IAP is untouched (IAP is service-level and can't be dropped per-revision).
# It runs --allow-unauthenticated so an anonymous browser can load the login
# page; AUTH_MODE=firebase then gates the API by verifying Firebase ID tokens.
# Point it at a READ-ONLY DB role (DB_USER/DB_PASS_SECRET) so a stray write
# can't mutate prod — it connects to the same trading-db instance.
#
# One-time operator prerequisites (Owner / run.admin + firebaseauth.admin):
#   1. gcloud services enable identitytoolkit.googleapis.com --project ${PROJECT_ID}
#   2. Identity Platform console: enable the Google + Email/Password providers,
#      and add the staging Cloud Run host under Authorized domains.
#   3. --allow-unauthenticated needs run.services.setIamPolicy; may be blocked
#      by a DRS org policy (iam.allowedPolicyMemberDomains) — if so, front the
#      private service with an external HTTPS LB instead.
if [[ "${STAGING_SERVICE:-0}" == "1" ]]; then
  SERVICE="trading-platform-staging"
  PUBLIC=1   # public ingress so the login page loads; AUTH_MODE=firebase gates the API
  AUTH_MODE_VAL="firebase"
  echo ">> STAGING_SERVICE mode: PUBLIC ${SERVICE} (in-app Firebase login)"
else
  # Prod stays on IAP unless explicitly overridden. Pinning this (not the code
  # default) ensures the auth middleware is a pass-through and IAP stays in charge.
  AUTH_MODE_VAL="${AUTH_MODE:-iap}"
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

# ── Env vars + secrets ──────────────────────────────────────────────────────
ENV_VARS="CLOUD_SQL_CONNECTION_NAME=${INSTANCE},DB_USER=${DB_USER},DB_NAME=${DB_NAME},GCS_BUCKET=${PROJECT_ID}-trading-data,GCP_PROJECT_ID=${PROJECT_ID},PLAYWRIGHT_TESTER_SA=playwright-tester@${PROJECT_ID}.iam.gserviceaccount.com,IAP_OAUTH_CLIENT_ID=369001918367-t5qrahnqdaasaifvk6akpqkpjk9vli58.apps.googleusercontent.com,AUTH_MODE=${AUTH_MODE_VAL}"
SECRETS="DB_PASS=${DB_PASS_SECRET}:latest,AV_API_KEY=av-api-key:latest,ALPHA_VANTAGE_API_KEY=av-api-key:latest"

# Firebase web config for the in-app login (the API key is an identifier, safe
# in plaintext env). firebase-admin verifies tokens via the runtime SA — no key.
if [[ "${AUTH_MODE_VAL}" == "firebase" ]]; then
  : "${FIREBASE_API_KEY:?set FIREBASE_API_KEY for AUTH_MODE=firebase (console → Project settings → Web app)}"
  : "${FIREBASE_AUTH_DOMAIN:?set FIREBASE_AUTH_DOMAIN}"
  : "${FIREBASE_APP_ID:?set FIREBASE_APP_ID}"
  ENV_VARS="${ENV_VARS},FIREBASE_PROJECT_ID=${FIREBASE_PROJECT_ID:-${PROJECT_ID}},FIREBASE_API_KEY=${FIREBASE_API_KEY},FIREBASE_AUTH_DOMAIN=${FIREBASE_AUTH_DOMAIN},FIREBASE_APP_ID=${FIREBASE_APP_ID},AUTH_OPEN_SIGNUP=${AUTH_OPEN_SIGNUP:-1}"
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
