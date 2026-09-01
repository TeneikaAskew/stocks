#!/bin/bash
# CR-native ad-hoc SQL dispatcher. Replaces dispatching db-query.yml.
#
# Usage:
#   # inline SQL
#   ./scripts/db_query_cr.sh -q "SELECT count(*) FROM trades"
#   # SQL file (relative to repo root; will be passed by content not path)
#   ./scripts/db_query_cr.sh -f gcp/queries/check_daily_rates_nulls.sql
#   # commit a write
#   ./scripts/db_query_cr.sh -q "UPDATE x SET y=1" --commit
#
# Routes the request to the `db-query` Cloud Run Job (entrypoint
# gcp/db_query_job.py), waits for completion, and pulls the summary
# from GCS. The Cloud Run Job control plane is hit over 443, which
# works from any sandbox; reading the GCS result is also 443.
#
# Exit code mirrors the job: 0 on success / user-error, non-zero on
# system error.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-east1}"
JOB="db-query"

usage() {
    cat <<EOF
Usage: $0 (-q SQL | -f SQL_FILE) [--commit] [--timeout SECONDS]
          [--wait-timeout SECONDS] [--quiet]

Options:
  -q SQL               inline SQL (multi-statement separated by ;)
  -f SQL_FILE          path to .sql file (sent as ONE statement, supports DO blocks)
  --commit             persist writes (default: rollback)
  --timeout SECS       per-statement statement_timeout (default 120)
  --wait-timeout SECS  give up waiting for the execution (default: timeout + 180)
  --quiet              suppress progress logs; the summary still prints
EOF
    exit 2
}

SQL=""
SQL_FILE=""
COMMIT="false"
TIMEOUT_S="120"
WAIT_MAX_S=""      # defaults to TIMEOUT_S + 180 once args are parsed
QUIET="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -q) SQL="$2"; shift 2 ;;
        -f) SQL_FILE="$2"; shift 2 ;;
        --commit) COMMIT="true"; shift ;;
        --timeout) TIMEOUT_S="$2"; shift 2 ;;
        --wait-timeout) WAIT_MAX_S="$2"; shift 2 ;;
        --quiet) QUIET="true"; shift ;;
        -h|--help) usage ;;
        *) echo "unknown arg: $1" >&2; usage ;;
    esac
done

# Container start + query + result upload all happen inside the wait window,
# so give the statement timeout meaningful headroom rather than racing it.
: "${WAIT_MAX_S:=$(( TIMEOUT_S + 180 ))}"

if [[ -z "$SQL" && -z "$SQL_FILE" ]]; then
    echo "error: provide -q SQL or -f SQL_FILE" >&2
    exit 2
fi
if [[ -n "$SQL" && -n "$SQL_FILE" ]]; then
    echo "error: -q and -f are mutually exclusive" >&2
    exit 2
fi

# If a file was provided, read its content (Cloud Run Job runs in a different
# container; passing the path won't work unless the file is in the image).
if [[ -n "$SQL_FILE" ]]; then
    if [[ ! -f "$SQL_FILE" ]]; then
        echo "error: SQL_FILE not found: $SQL_FILE" >&2
        exit 2
    fi
    SQL="$(cat "$SQL_FILE")"
fi

# NOTE: written as an `if`, not `[[ ... ]] && echo`. The && form returns the
# status of the failed test when QUIET=true, and under `set -e` that aborted
# the whole script at the first log call — so `--quiet` exited 1 immediately,
# before dispatching anything, with no output at all. It looked like a hang.
log() {
    if [[ "$QUIET" != "true" ]]; then
        echo "$@" >&2
    fi
}

# Build env-var overrides. Use the ^|^ delimiter so embedded commas in the
# SQL don't confuse gcloud's default CSV parsing.
ENV_OVERRIDES="^|^DB_QUERY_SQL=${SQL}|DB_QUERY_COMMIT=${COMMIT}|DB_QUERY_TIMEOUT_SECONDS=${TIMEOUT_S}"

log "dispatching db-query CR Job (commit=$COMMIT, timeout=${TIMEOUT_S}s, sql=${#SQL} chars)..."

# `executions` is GA, but older SDKs only expose it under `beta` — and on a
# machine where the beta component is not installed, every beta call errors.
# That silently starved the poll loop below of a status and made a job that had
# already SUCCEEDED look like a timeout. Resolve the working form once.
EXEC_CMD=""
_resolve_exec_cmd() {
    if gcloud run jobs executions list --job="$JOB" --region="$REGION"             --limit=1 --format="value(name)" >/dev/null 2>&1; then
        EXEC_CMD="gcloud run jobs executions"
    elif gcloud beta run jobs executions list --job="$JOB" --region="$REGION"             --limit=1 --format="value(name)" >/dev/null 2>&1; then
        EXEC_CMD="gcloud beta run jobs executions"
    else
        echo "error: cannot list Cloud Run job executions with either the GA or" >&2
        echo "       beta gcloud command. Check auth and 'gcloud components install beta'." >&2
        exit 1
    fi
}
_resolve_exec_cmd

# Dispatch with --async, then poll under our own deadline.
#
# --wait polls forever: a job that never reaches a terminal state (stuck
# pull, quota wait, an image that won't start) blocks the caller with no
# output and no way out but Ctrl-C. Owning the loop means a stall fails
# loudly with the execution name still printed, so it stays diagnosable.
EXEC_ERR="$(mktemp)"
if ! EXEC_NAME=$(gcloud run jobs execute "$JOB" \
        --region="$REGION" \
        --update-env-vars="$ENV_OVERRIDES" \
        --async \
        --format="value(metadata.name)" 2>"$EXEC_ERR"); then
    echo "error: dispatching the db-query job failed:" >&2
    cat "$EXEC_ERR" >&2
    rm -f "$EXEC_ERR"
    exit 1
fi

# Some gcloud versions print the execution name on stderr rather than stdout.
if [[ -z "$EXEC_NAME" ]]; then
    EXEC_NAME=$($EXEC_CMD list --job="$JOB" \
        --region="$REGION" --limit=1 --format="value(name)" 2>/dev/null || true)
fi
if [[ -z "$EXEC_NAME" ]]; then
    echo "error: dispatched, but could not determine the execution name:" >&2
    cat "$EXEC_ERR" >&2
    rm -f "$EXEC_ERR"
    exit 1
fi
rm -f "$EXEC_ERR"
log "execution: $EXEC_NAME"

# Poll for TERMINALITY via completionTime, not the Completed condition.
#
# Cloud Run reports Completed=False while an execution is still RUNNING, so
# treating False as an outcome ends the wait early: the script reported
# failure for a job that went on to succeed, and read the GCS summary before
# it had been uploaded. completionTime is only set once the execution has
# actually finished; succeeded/failed counts then give the real outcome.
DEADLINE=$(( $(date +%s) + WAIT_MAX_S ))
while :; do
    COMPLETION=$($EXEC_CMD describe "$EXEC_NAME"         --region="$REGION"         --format="value(status.completionTime)" 2>/dev/null || true)
    if [[ -n "$COMPLETION" ]]; then
        break
    fi
    if (( $(date +%s) >= DEADLINE )); then
        echo "error: execution $EXEC_NAME did not finish within ${WAIT_MAX_S}s." >&2
        echo "       It may still be running. Inspect with:" >&2
        echo "       $EXEC_CMD describe $EXEC_NAME --region=$REGION" >&2
        exit 124
    fi
    sleep 3
done

FAILED_N=$($EXEC_CMD describe "$EXEC_NAME" --region="$REGION"     --format="value(status.failedCount)" 2>/dev/null || true)
SUCCEEDED_N=$($EXEC_CMD describe "$EXEC_NAME" --region="$REGION"     --format="value(status.succeededCount)" 2>/dev/null || true)
if [[ "${FAILED_N:-0}" -gt 0 || "${SUCCEEDED_N:-0}" -lt 1 ]]; then
    CONCLUSION="False"
else
    CONCLUSION="True"
fi
log "execution finished: succeeded=${SUCCEEDED_N:-0} failed=${FAILED_N:-0}"

PREFIX="gs://${PROJECT_ID}-trading-data/query-results/${EXEC_NAME}"
log "results at: $PREFIX"

# Always emit the summary to stdout — it has the result tables either way.
#
# Bounded, with a fallback. `gcloud storage` is a separate component: it can be
# absent, and it has been observed hanging here long enough to stall the script
# AFTER the query had already succeeded. An unbounded read at this point throws
# away work that is finished and paid for. The Storage JSON API needs only curl
# and a token, and is equally 443-only, so it is a genuinely different path
# rather than a retry of the same tool.
BUCKET="${PROJECT_ID}-trading-data"
OBJECT="query-results/${EXEC_NAME}/summary.md"

_read_summary_gcloud() {
    if command -v timeout >/dev/null 2>&1; then
        timeout 60 gcloud storage cat "${PREFIX}/summary.md" 2>/dev/null
    else
        gcloud storage cat "${PREFIX}/summary.md" 2>/dev/null
    fi
}

_read_summary_api() {
    local token encoded
    token=$(gcloud auth print-access-token 2>/dev/null) || return 1
    # The JSON API's single-object GET needs the path percent-encoded.
    encoded=${OBJECT//\//%2F}
    curl -fsS --max-time 60 -H "Authorization: Bearer ${token}" \
        "https://storage.googleapis.com/storage/v1/b/${BUCKET}/o/${encoded}?alt=media"
}

if ! _read_summary_gcloud && ! _read_summary_api; then
    echo "warn: could not read ${PREFIX}/summary.md via gcloud storage or the" >&2
    echo "      Storage JSON API. The query itself may still have succeeded;" >&2
    echo "      results are at ${PREFIX}/" >&2
fi

[[ "$CONCLUSION" == "True" ]] && exit 0 || exit 1
