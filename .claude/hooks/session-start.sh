#!/bin/bash
# SessionStart hook — activates GCP credentials for Claude Code Web sessions.
# Reads CLAUDE_CODE_WEB_GCP_SA_KEY (service-account JSON, raw or base64-encoded),
# writes it to credentials/gcp-service-account.json, activates gcloud, and exports
# GOOGLE_APPLICATION_CREDENTIALS for Python client libs (gcp/database.py, fetchers).
#
# Failure mode: if the secret isn't present, log a warning and exit 0 so the
# session still starts (Claude can still do non-GCP work).
set -uo pipefail

PROJECT_ID="adept-mountain-474619-d4"
KEY_PATH="${CLAUDE_PROJECT_DIR:-$(pwd)}/credentials/gcp-service-account.json"

log() { echo "[session-start gcp] $*" >&2; }

# Web-only — local dev uses gcloud auth login directly.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  log "skip: not a remote session (CLAUDE_CODE_REMOTE!=true)"
  exit 0
fi

if [ -z "${CLAUDE_CODE_WEB_GCP_SA_KEY:-}" ]; then
  log "warning: CLAUDE_CODE_WEB_GCP_SA_KEY not set — GCP commands will be unauthenticated"
  log "  configure the secret in Claude Code Web repo settings to enable auto-auth"
  exit 0
fi

mkdir -p "$(dirname "$KEY_PATH")"

# Accept either raw JSON or base64-encoded JSON. Detect by checking for '{'.
if [[ "${CLAUDE_CODE_WEB_GCP_SA_KEY}" == *"{"* ]]; then
  printf '%s' "${CLAUDE_CODE_WEB_GCP_SA_KEY}" > "$KEY_PATH"
else
  if ! printf '%s' "${CLAUDE_CODE_WEB_GCP_SA_KEY}" | base64 -d > "$KEY_PATH" 2>/dev/null; then
    log "error: secret is neither valid JSON nor base64"
    exit 1
  fi
fi

# Sanity-check it parsed as a real SA key.
if ! python3 -c "import json,sys; d=json.load(open('$KEY_PATH')); assert d.get('type')=='service_account', 'not a service_account key'; print(d.get('client_email'))" >/dev/null 2>&1; then
  log "error: key file does not look like a service-account JSON"
  rm -f "$KEY_PATH"
  exit 1
fi

chmod 600 "$KEY_PATH"

if ! gcloud auth activate-service-account --key-file="$KEY_PATH" --quiet >/dev/null 2>&1; then
  log "error: gcloud auth activate-service-account failed"
  exit 1
fi

gcloud config set project "$PROJECT_ID" --quiet >/dev/null 2>&1 || true

# Persist env vars for the Claude session (Python libs use ADC via this path).
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export GOOGLE_APPLICATION_CREDENTIALS=\"$KEY_PATH\""
    echo "export GOOGLE_CLOUD_PROJECT=\"$PROJECT_ID\""
    echo "export CLOUDSDK_CORE_PROJECT=\"$PROJECT_ID\""
  } >> "$CLAUDE_ENV_FILE"
fi

ACTIVE_ACCT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | head -1)
log "activated $ACTIVE_ACCT on project $PROJECT_ID"

# Read-only smoke test — non-fatal if it fails (e.g. transient network).
if gcloud projects describe "$PROJECT_ID" --format="value(projectId)" >/dev/null 2>&1; then
  log "smoke test ok: projects.describe reachable"
else
  log "warning: projects.describe failed — SA may lack roles/viewer or network is blocked"
fi
