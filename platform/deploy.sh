#!/usr/bin/env bash
# Build and deploy the trading platform to Cloud Run.
# Run from repo root:  ./platform/deploy.sh
#
# Modes:
#   ./platform/deploy.sh                  prod deploy (trading-platform, behind IAP)
#   STAGING=1 ./platform/deploy.sh        prod service, new revision tagged `staging`,
#                                         no traffic — shares prod's IAP (see note below)
#   STAGING_SERVICE=1 ./platform/deploy.sh  SEPARATE public staging service
#                                         (trading-platform-staging) NO IAP, gated by
#                                         in-app Firebase login (AUTH_MODE=firebase).
#                                         Prod untouched. Needs FIREBASE_API_KEY,
#                                         FIREBASE_AUTH_DOMAIN, FIREBASE_APP_ID (+ optional
#                                         AUTH_ALLOWED_EMAILS) in env.
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

# ── Separate public staging service ────────────────────────────────────────
# trading-platform-staging runs WITHOUT IAP (--allow-unauthenticated) because
# IAP on Cloud Run is service-level and can't be dropped per-revision. Instead,
# AUTH_MODE=firebase re-protects the API: api/auth.py verifies a Firebase ID
# token on every gated /api/* request, so the service is NOT wide-open even
# though anyone can load the login page. Access defaults to OPEN self-signup —
# any user who signs in (Google or email/password) is allowed; flip to an
# allow-list with AUTH_OPEN_SIGNUP=0 + AUTH_ALLOWED_EMAILS. Prod
# (trading-platform) is untouched and stays behind IAP.
#
# One-time prerequisites (operator with run.admin — NOT the CI SA):
#   1. Create a Firebase web app (console -> Project settings -> Web app) and
#      pass its config via env at deploy time:
#        FIREBASE_API_KEY=… FIREBASE_AUTH_DOMAIN=… FIREBASE_APP_ID=… \
#          STAGING_SERVICE=1 ./platform/deploy.sh
#   2. --allow-unauthenticated needs run.services.setIamPolicy; deploying as a
#      run.admin principal grants allUsers invoker automatically. (If org policy
#      DRS blocks allUsers, the public service can't be created — escalate.)
# Auth mode (read by api/auth.py): prod = iap (IAP gates at the edge; identity
# comes from the IAP header). The public staging service flips to firebase below.
AUTH_MODE_VAL="${AUTH_MODE:-iap}"

if [[ "${STAGING_SERVICE:-0}" == "1" ]]; then
  SERVICE="trading-platform-staging"
  PUBLIC=1                   # public ingress so the login page can load
  AUTH_MODE_VAL="firebase"   # in-app Firebase login gates the API (verify ID token)
  echo ">> STAGING_SERVICE mode: deploying PUBLIC ${SERVICE} (no IAP; Firebase login gates the API)"
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
ENV_VARS="CLOUD_SQL_CONNECTION_NAME=${INSTANCE},DB_USER=${DB_USER},DB_NAME=${DB_NAME},GCS_BUCKET=${PROJECT_ID}-trading-data,GCP_PROJECT_ID=${PROJECT_ID},PLAYWRIGHT_TESTER_SA=playwright-tester@${PROJECT_ID}.iam.gserviceaccount.com,IAP_OAUTH_CLIENT_ID=369001918367-t5qrahnqdaasaifvk6akpqkpjk9vli58.apps.googleusercontent.com,AUTH_MODE=${AUTH_MODE_VAL}"
SECRETS="DB_PASS=${DB_PASS_SECRET}:latest,AV_API_KEY=av-api-key:latest,ALPHA_VANTAGE_API_KEY=av-api-key:latest"

# Firebase-mode services need the web SDK config (apiKey/authDomain/appId are
# PUBLIC identifiers — access is enforced server-side by token verification +
# the allow-list, not by hiding these). Fail fast if a firebase deploy is missing
# them rather than shipping a login page that can't initialize.
if [[ "${AUTH_MODE_VAL}" == "firebase" ]]; then
  : "${FIREBASE_API_KEY:?set FIREBASE_API_KEY for AUTH_MODE=firebase (console -> Project settings -> Web app)}"
  : "${FIREBASE_AUTH_DOMAIN:?set FIREBASE_AUTH_DOMAIN}"
  : "${FIREBASE_APP_ID:?set FIREBASE_APP_ID}"
  # Access policy: OPEN self-signup by default — any user who signs in (Google or
  # email/password) is allowed. Restrict to an allow-list instead by deploying
  # with AUTH_OPEN_SIGNUP=0 AUTH_ALLOWED_EMAILS=a@x.com,b@y.com.
  ENV_VARS="${ENV_VARS},FIREBASE_PROJECT_ID=${FIREBASE_PROJECT_ID:-${PROJECT_ID}},FIREBASE_API_KEY=${FIREBASE_API_KEY},FIREBASE_AUTH_DOMAIN=${FIREBASE_AUTH_DOMAIN},FIREBASE_APP_ID=${FIREBASE_APP_ID},AUTH_OPEN_SIGNUP=${AUTH_OPEN_SIGNUP:-1},AUTH_ALLOWED_EMAILS=${AUTH_ALLOWED_EMAILS:-}"
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
