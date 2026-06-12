#!/usr/bin/env bash
# Mint a Firebase ID token for the persistent staging E2E test user, so any
# session running as claude-web@ can authenticate against the public staging
# service without a browser.
#
#   TOKEN=$(bash scripts/staging_e2e_token.sh)
#   curl -H "Authorization: Bearer $TOKEN" "$STAGING_URL/api/market/dates/SPY"
#
# Or drive Playwright's cloud project against staging:
#   STAGING_BEARER=$(bash scripts/staging_e2e_token.sh) \
#     CLOUD_RUN_URL=https://trading-platform-staging-28960574877.us-east1.run.app \
#     npm --prefix platform run e2e:cloud
#
# Credentials live in Secret Manager (staging-e2e-login); claude-web@ reads them
# over 443. The Firebase web apiKey is public and read from the staging config
# endpoint, so nothing secret is hardcoded here.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-adept-mountain-474619-d4}"
STAGING_URL="${STAGING_URL:-https://trading-platform-staging-28960574877.us-east1.run.app}"
SECRET="${E2E_LOGIN_SECRET:-staging-e2e-login}"

API_KEY="$(curl -fsS "${STAGING_URL}/api/config/firebase" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["firebase"]["apiKey"])')"

CREDS="$(gcloud secrets versions access latest --secret="${SECRET}" --project="${PROJECT_ID}")"
EMAIL="$(printf '%s' "$CREDS" | python3 -c 'import sys,json; print(json.load(sys.stdin)["email"])')"
PASSWORD="$(printf '%s' "$CREDS" | python3 -c 'import sys,json; print(json.load(sys.stdin)["password"])')"

# Body via stdin (--data-binary @-) so the password never lands in argv/proc.
printf '{"email":"%s","password":"%s","returnSecureToken":true}' "$EMAIL" "$PASSWORD" \
  | curl -fsS "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=${API_KEY}" \
      -H 'Content-Type: application/json' --data-binary @- \
  | python3 -c '
import sys, json
d = json.load(sys.stdin)
tok = d.get("idToken")
if not tok:
    sys.stderr.write("sign-in failed: " + json.dumps(d.get("error", d)) + "\n")
    sys.exit(1)
print(tok)'
