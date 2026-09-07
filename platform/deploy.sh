#!/usr/bin/env bash
# Build and deploy the trading platform to Cloud Run.
# Run from repo root:  ./platform/deploy.sh
#
# Modes:
#   ./platform/deploy.sh                  prod deploy (solyra-api-prod, behind IAP)
#   STAGING=1 ./platform/deploy.sh        prod service, new revision tagged `staging`,
#                                         no traffic — shares prod's IAP (see note below)
#   STAGING_SERVICE=1 ./platform/deploy.sh  SEPARATE public staging service
#                                         (solyra-api-staging) NO IAP, gated by
#                                         in-app Firebase login (AUTH_MODE=firebase).
#                                         Prod untouched. Needs FIREBASE_API_KEY,
#                                         FIREBASE_AUTH_DOMAIN, FIREBASE_APP_ID (+ optional
#                                         AUTH_ALLOWED_EMAILS) in env.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-adept-mountain-474619-d4}"
REGION="${REGION:-us-east1}"
SERVICE="${SERVICE:-solyra-api-prod}"
INSTANCE="${INSTANCE:-${PROJECT_ID}:${REGION}:trading-db}"
# The image is the same app for every service — build once, reuse for staging.
IMAGE_NAME="${IMAGE_NAME:-solyra-api}"
IMAGE="gcr.io/${PROJECT_ID}/${IMAGE_NAME}"

# ── One-time IAM for the admin endpoints (api/routers/admin.py) ────────────
#   SETUP_IAM=1 ./platform/deploy.sh     (grants only; exits without deploying)
# Two grants the runtime SA needs, neither covered by its data-plane roles:
#   1. roles/firebaseauth.admin — GET/PUT /api/admin/users* manage Firebase
#      Auth accounts (list_users / update_user / revoke_refresh_tokens) via
#      the Admin SDK; ADC alone does NOT authorize the Identity Toolkit
#      user-management APIs, so without this every Users-tab call 503s.
#   2. roles/run.invoker on each allowlisted fetcher job — POST
#      /api/admin/data-sources/{id}/refresh dispatches them; the list below
#      MUST stay in sync with _DATA_SOURCES in api/routers/admin.py.
# Run as an operator with project IAM admin (NOT the CI SA). Idempotent.
if [[ "${SETUP_IAM:-0}" == "1" ]]; then
  IAM_SA="${RUN_SA:-trading-platform-svc@${PROJECT_ID}.iam.gserviceaccount.com}"
  echo ">> granting roles/firebaseauth.admin to ${IAM_SA}"
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${IAM_SA}" --role=roles/firebaseauth.admin \
    --condition=None >/dev/null
  IAM_MISSED=()
  for REFRESH_JOB in fetch-market-data fetch-av-options-backfill \
      fetch-fred-rates fetch-economic-events fetch-earnings-calendar \
      strat-engine historical-signals-watchlist; do
    echo ">> granting roles/run.invoker on ${REFRESH_JOB} to ${IAM_SA}"
    # Per-job continue (set -e would otherwise abort the loop half-granted
    # when a job isn't deployed in this project yet); missed jobs are
    # reported at the end and the script exits non-zero so partial setup
    # never reads as success.
    if ! gcloud run jobs add-iam-policy-binding "${REFRESH_JOB}" \
        --region "${REGION}" --project "${PROJECT_ID}" \
        --member="serviceAccount:${IAM_SA}" --role=roles/run.invoker >/dev/null; then
      echo ">> WARN: grant failed for ${REFRESH_JOB} (job not deployed here yet?)"
      IAM_MISSED+=("${REFRESH_JOB}")
    fi
  done
  if [[ ${#IAM_MISSED[@]} -gt 0 ]]; then
    echo ">> IAM setup INCOMPLETE — re-run SETUP_IAM=1 after deploying: ${IAM_MISSED[*]}"
    exit 1
  fi
  echo ">> IAM setup done"
  exit 0
fi

# DB credentials — set DB_USER / DB_NAME in env, store DB_PASS in Secret Manager.
DB_USER="${DB_USER:?set DB_USER (e.g. export DB_USER=postgres)}"
DB_NAME="${DB_NAME:?set DB_NAME (e.g. export DB_NAME=trading)}"
DB_PASS_SECRET="${DB_PASS_SECRET:-trading-db-pass}"

# ── Separate public staging service ────────────────────────────────────────
# solyra-api-staging runs WITHOUT IAP (--allow-unauthenticated) because
# IAP on Cloud Run is service-level and can't be dropped per-revision. Instead,
# AUTH_MODE=firebase re-protects the API: api/auth.py verifies a Firebase ID
# token on every gated /api/* request, so the service is NOT wide-open even
# though anyone can load the login page. Access defaults to OPEN self-signup —
# any user who signs in (Google or email/password) is allowed; flip to an
# allow-list with AUTH_OPEN_SIGNUP=0 + AUTH_ALLOWED_EMAILS. Prod
# (solyra-api-prod) is untouched and stays behind IAP.
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
  SERVICE="solyra-api-staging"
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
# `staging` on the PROD service that receives NO production traffic. The prod
# URL keeps serving the current 100%-traffic revision. Promote later with:
#   gcloud run services update-traffic "${SERVICE}" --region "${REGION}" --to-tags=staging=100
#
# LEGACY as of 2026-09-05, kept for one-off operator use only. The routine
# staging path is now the separate solyra-api-staging SERVICE (STAGING_SERVICE=1
# above, and the deploy-solyra-api-staging Cloud Build trigger on merge to main),
# not a tag on prod. This mode is what made the old setup so easy to misread:
# a `staging` tag says nothing about traffic, and when --no-traffic was dropped
# from the Cloud Build trigger on 2026-08-25 the "staging" tag silently ended up
# carrying 100% of production. If you use this mode, the tag is doing nothing to
# protect prod on its own — the --no-traffic below is.
STAGING_FLAGS=()
if [[ "${STAGING:-0}" == "1" ]]; then
  STAGING_FLAGS=(--no-traffic --tag staging)
  echo ">> STAGING mode: new revision tagged 'staging', no production traffic"
fi

# ── Env vars + secrets (composed so staging can append its own) ────────────
# MOVEMENT_STATEMENT_ENABLED=false since 2026-08-28. The card was enabled
# 2026-07-12 on a validated model, but every magnitude cell currently serving
# it is argmax-collapsed: `magnitude-engine-c49qf` (promoted 2026-08-27 from a
# calibration=isotonic run) predicted TIGHT on 588/588 live bars with fold
# accuracy equal to the base rate, and audit-magnitude-drift flags every other
# live cell HIGH or MEDIUM on modal dominance too. Rendering a constant bucket
# to users is worse than rendering nothing.
#
# Re-enable (set back to true) once a retrain PASSES the promotion gate added
# in gcp/research/magnitude_engine/mag_walk_forward.promotion_verdict and
# audit-magnitude-drift reports no HIGH modal-dominance finding for the served
# cells. The render-layer backstop in lib/movement_statement._model_degeneracy
# will withhold a collapsed bucket even if the flag is on, but the flag is the
# instant lever and stays off until there is something worth showing.
# --set-env-vars replaces the whole set on each deploy, so the flag must live
# here to persist across deploys.
# GCP_REGION rides along with GCP_PROJECT_ID so the admin refresh dispatch
# (api/routers/admin.py _run_refresh_job) targets THIS deployment's project
# and region — without it a PROJECT_ID/REGION-overridden deploy would
# silently dispatch jobs in the hardcoded prod defaults (Codex, PR #972).
#
# Pairs are joined with "|" and passed as --set-env-vars "^|^..." (gcloud's
# alternate-delimiter syntax) because VALUES may legitimately contain commas:
# AUTH_ALLOWED_EMAILS=a@x.com,b@y.com is the documented multi-user allowlist,
# and under the default comma delimiter gcloud parses its second email as a
# malformed extra pair, failing the deploy AFTER the build (Codex, PR #983).
# No key or value may contain "|".
ENV_VARS="CLOUD_SQL_CONNECTION_NAME=${INSTANCE}|DB_USER=${DB_USER}|DB_NAME=${DB_NAME}|GCS_BUCKET=${PROJECT_ID}-trading-data|GCP_PROJECT_ID=${PROJECT_ID}|GCP_REGION=${REGION}|PLAYWRIGHT_TESTER_SA=playwright-tester@${PROJECT_ID}.iam.gserviceaccount.com|IAP_OAUTH_CLIENT_ID=369001918367-t5qrahnqdaasaifvk6akpqkpjk9vli58.apps.googleusercontent.com|AUTH_MODE=${AUTH_MODE_VAL}|MOVEMENT_STATEMENT_ENABLED=false"

# Who gets /api/admin/* and the is_admin flag on /api/me. Must be deployed
# here rather than patched on afterwards: this script uses --set-env-vars,
# which REPLACES the whole set, so a hand-applied --update-env-vars would be
# silently dropped by the next deploy. Falls back to the same default the app
# uses, so omitting it changes nothing.
ENV_VARS="${ENV_VARS}|ADMIN_EMAIL=${ADMIN_EMAIL:-teneika@bictech.org}"
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
  ENV_VARS="${ENV_VARS}|FIREBASE_PROJECT_ID=${FIREBASE_PROJECT_ID:-${PROJECT_ID}}|FIREBASE_API_KEY=${FIREBASE_API_KEY}|FIREBASE_AUTH_DOMAIN=${FIREBASE_AUTH_DOMAIN}|FIREBASE_APP_ID=${FIREBASE_APP_ID}|AUTH_OPEN_SIGNUP=${AUTH_OPEN_SIGNUP:-1}|AUTH_ALLOWED_EMAILS=${AUTH_ALLOWED_EMAILS:-}"
fi

echo ">> project=${PROJECT_ID} region=${REGION} service=${SERVICE}"
gcloud config set project "${PROJECT_ID}" >/dev/null

# An immutable per-build tag. This used to build, push and deploy the bare
# ${IMAGE} -- i.e. :latest -- which the deploy-solyra-api-staging Cloud Build
# trigger writes too. Two overlapping runs could then push over each other
# between one run's push and its deploy, so `gcloud run deploy --image
# ...:latest` resolved to an image that run never built. The prod promote
# trigger promotes whatever digest is serving staging, so a mutable tag put an
# unvalidated image one click from production.
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%dT%H%M%SZ)}"

# A FAST-FAIL courtesy check, not the interlock.
#
# The authoritative check is the first step of platform/cloudbuild.yaml, which
# runs INSIDE the submitted build. This one only exists so an operator finds
# out before uploading a source tarball; it cannot be the guard, because at
# this point the build does not exist and carries no tag, so a trigger
# starting in the window between here and `gcloud builds submit` would see
# nothing and proceed (Codex, PR #990).
#
# STAGING_SERVICE, not STAGING: the former deploys solyra-api-staging (what
# the trigger also deploys); the latter is the legacy revision-tag mode on
# prod. Non-fatal here -- the in-build check is what decides.
if [[ "${STAGING_SERVICE:-0}" == "1" ]]; then
  bash "$(dirname "${BASH_SOURCE[0]}")/../gcp/cloudbuild/assert_no_concurrent_staging_deploy.sh" \
    || { echo ">> a concurrent deploy was detected before submitting; aborting early"; exit 1; }
fi

# 0. Pin every image digest a Cloud Run job or service still runs, so the
#    Artifact Registry cleanup policy (gcp/deploy.sh setup_registry_cleanup)
#    cannot delete a digest something is serving: it removes untagged
#    versions older than 14 days, and a digest whose only tag moves away
#    becomes untagged. Fails closed: no pin, no build.
#
#    #1004 added this because THIS script moved ${IMAGE}:latest. It no longer
#    does -- the build above pushes an immutable ${IMAGE}:${IMAGE_TAG} and the
#    deploy below resolves it to a digest -- so this path is not itself the
#    tag mover any more. The step stays because the repository is shared: the
#    deploy-solyra-api-staging trigger and gcp/deploy.sh both still move tags
#    in it, and the revision this run replaces is exactly the digest that
#    needs to already carry its inuse-* tag when they do.
#
#    --no-sweep: the deploy-solyra-api-staging Cloud Build trigger runs this
#    as trading-runner@, whose roles/artifactregistry.writer can create and
#    move tags but not delete them; releasing stale pins is done by the
#    interactive gcp/deploy.sh path instead (see gcp/cloudbuild/README.md).
./gcp/deploy.sh pin-images --no-sweep

# Reads ${SERVICE} and prints the state a compare-and-swap can compare against:
# `serving <revision>` or `absent`.
#
# FAILS CLOSED. `2>/dev/null` plus a bare `else` treated EVERY nonzero exit as
# "the service does not exist": a transient API error, an expired credential or
# a missing role all left the baseline empty, which silently skipped the
# compare-and-swap below and re-opened the window it exists to close. Only an
# explicit not-found is the create case; anything else stops the deploy
# (Codex, PR #990).
describe_deploy_state() {
  local err out rev
  err="$(mktemp)"
  if out="$(gcloud run services describe "${SERVICE}" --region "${REGION}" \
              --format=json 2>"${err}")"; then
    rm -f "${err}"
    # A nonzero exit from serving_revision.py -- nothing serving, or traffic
    # split across revisions -- fails the assignment below and aborts under
    # `set -e`, and should: a compare-and-swap has no baseline to compare
    # against in either case, and deploying over an ambiguous service is what
    # this guard is for.
    rev="$(printf '%s' "${out}" | python3 gcp/cloudbuild/serving_revision.py)" || return 1
    printf 'serving %s\n' "${rev}"
  elif grep -qiE 'NOT_FOUND|could not be found|does not exist' "${err}"; then
    rm -f "${err}"
    printf 'absent\n'
  else
    echo ">> ERROR: could not read ${SERVICE} to establish a deploy baseline." >&2
    echo "          Not treating an unreadable service as an absent one: that" >&2
    echo "          would skip the compare-and-swap and let a concurrent deploy" >&2
    echo "          be overwritten silently." >&2
    cat "${err}" >&2
    rm -f "${err}"
    return 1
  fi
}

# The state this run is about to replace, read BEFORE the build so it can be
# compared with the state at deploy time. See the compare-and-swap in step 3.
#
# ABSENCE IS A STATE, not an empty string. Representing "the service does not
# exist yet" as an empty baseline skipped the comparison entirely on the create
# path, so a peer that created and deployed the service while this build ran
# was overwritten by this older invocation -- first creation being exactly the
# case the previous fix left open (Codex, PR #990). Comparing the whole state
# means the create path is guarded by "still absent" the same way the replace
# path is guarded by "still the same revision".
DEPLOY_BASELINE="$(describe_deploy_state)"
if [[ "${DEPLOY_BASELINE}" == "absent" ]]; then
  echo ">> ${SERVICE} does not exist yet; this run creates it"
else
  echo ">> ${SERVICE} is currently ${DEPLOY_BASELINE}"
fi

# 1. Build image (uses repo-root .dockerignore, build context is repo root)
echo ">> building ${IMAGE}:${IMAGE_TAG}"
gcloud builds submit \
  --config platform/cloudbuild.yaml \
  --substitutions "_IMAGE=${IMAGE},_TAG=${IMAGE_TAG}" \
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
# Deploy the DIGEST, not the tag: the revision is then pinned to exactly the
# artifact this run built, whatever else writes the repository afterwards.
IMAGE_DIGEST=$(gcloud container images describe "${IMAGE}:${IMAGE_TAG}" \
                 --format='value(image_summary.fully_qualified_digest)')
if [[ -z "${IMAGE_DIGEST}" ]]; then
  echo ">> ERROR: could not resolve ${IMAGE}:${IMAGE_TAG} to a digest" >&2
  exit 1
fi

# The interlock, AGAIN, and a compare-and-swap on the service.
#
# Moving the interlock inside platform/cloudbuild.yaml made the IMAGE BUILD
# visible to a concurrent trigger. It did not cover this deploy, which happens
# after that build has finished and is therefore no longer ongoing: a trigger
# starting in the gap sees nothing, builds, deploys -- and then this older
# invocation deploys last and wins, which is the exact ordering failure the
# interlock exists to prevent (Codex, PR #990). Two checks close it from both
# sides. The build scan catches a peer that is still running; the revision
# comparison catches one that already finished and deployed, because the
# service is then serving a revision this run never saw.
#
# The remaining window is between this comparison and `gcloud run deploy`
# returning -- seconds, against the minutes a build takes. Cloud Run has no
# conditional-deploy primitive to close it completely; this narrows it to the
# point where the losing path is the one that started second, not the one that
# started first.
if [[ "${STAGING_SERVICE:-0}" == "1" ]]; then
  bash "$(dirname "${BASH_SOURCE[0]}")/../gcp/cloudbuild/assert_no_concurrent_staging_deploy.sh"
fi

DEPLOY_NOW="$(describe_deploy_state)"
if [[ "${DEPLOY_NOW}" != "${DEPLOY_BASELINE}" ]]; then
  echo ">> ERROR: ${SERVICE} moved while this build ran." >&2
  echo "          before the build: ${DEPLOY_BASELINE}" >&2
  echo "          now:              ${DEPLOY_NOW}" >&2
  echo "          Another deploy path landed in the gap; deploying now would" >&2
  echo "          put this older build's image over it. Re-run this deploy on" >&2
  echo "          top of the new revision instead." >&2
  exit 1
fi

echo ">> deploying to Cloud Run: ${IMAGE_DIGEST}"
gcloud run deploy "${SERVICE}" \
  --image "${IMAGE_DIGEST}" \
  --region "${REGION}" \
  --platform managed \
  --add-cloudsql-instances "${INSTANCE}" \
  --service-account "${RUN_SA:-trading-platform-svc@${PROJECT_ID}.iam.gserviceaccount.com}" \
  --set-env-vars "^|^${ENV_VARS}" \
  --set-secrets "${SECRETS}" \
  --memory 2Gi \
  --cpu 1 \
  --cpu-throttling \
  --timeout 300 \
  --min-instances 0 \
  --max-instances 5 \
  ${AUTH_FLAGS[@]+"${AUTH_FLAGS[@]}"} \
  ${STAGING_FLAGS[@]+"${STAGING_FLAGS[@]}"}

# Pin the digest this deploy just made current. The `pin-images` call above runs
# BEFORE the build, so it tags the revision this run replaces -- the new digest
# is not in the service inventory yet and comes out of that sweep with no
# `inuse-svc-*` tag at all. Against the 30-day delete rule this PR adds to the
# gcr.io cleanup policy, an unpinned digest is deletable while it is still the
# serving revision, so the manual and break-glass paths pin again here. The
# automatic staging and prod triggers do the same as their own last step
# (Codex, PR #990).
./gcp/deploy.sh pin-images --no-sweep

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
