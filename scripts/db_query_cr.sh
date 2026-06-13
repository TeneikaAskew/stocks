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
Usage: $0 (-q SQL | -f SQL_FILE) [--commit] [--timeout SECONDS] [--quiet]

Options:
  -q SQL          inline SQL (multi-statement separated by ;)
  -f SQL_FILE     path to .sql file (sent as ONE statement, supports DO blocks)
  --commit        persist writes (default: rollback)
  --timeout SECS  per-statement statement_timeout (default 120)
  --quiet         suppress all output except the final summary path
EOF
    exit 2
}

SQL=""
SQL_FILE=""
COMMIT="false"
TIMEOUT_S="120"
QUIET="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -q) SQL="$2"; shift 2 ;;
        -f) SQL_FILE="$2"; shift 2 ;;
        --commit) COMMIT="true"; shift ;;
        --timeout) TIMEOUT_S="$2"; shift 2 ;;
        --quiet) QUIET="true"; shift ;;
        -h|--help) usage ;;
        *) echo "unknown arg: $1" >&2; usage ;;
    esac
done

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

log() { [[ "$QUIET" != "true" ]] && echo "$@" >&2; }

# Build env-var overrides. Use the ^|^ delimiter so embedded commas in the
# SQL don't confuse gcloud's default CSV parsing.
ENV_OVERRIDES="^|^DB_QUERY_SQL=${SQL}|DB_QUERY_COMMIT=${COMMIT}|DB_QUERY_TIMEOUT_SECONDS=${TIMEOUT_S}"

log "dispatching db-query CR Job (commit=$COMMIT, timeout=${TIMEOUT_S}s, sql=${#SQL} chars)..."

# Execute synchronously (--wait); capture the execution id from output.
EXEC_NAME=$(gcloud run jobs execute "$JOB" \
    --region="$REGION" \
    --update-env-vars="$ENV_OVERRIDES" \
    --wait \
    --format="value(metadata.name)" 2>/dev/null)

# Some gcloud versions return the execution name as the last line of stderr
# instead of stdout. Fall back to listing the most recent execution.
if [[ -z "$EXEC_NAME" ]]; then
    EXEC_NAME=$(gcloud beta run jobs executions list --job="$JOB" \
        --region="$REGION" --limit=1 --format="value(name)" 2>/dev/null)
fi
log "execution: $EXEC_NAME"

CONCLUSION=$(gcloud beta run jobs executions describe "$EXEC_NAME" \
    --region="$REGION" \
    --format="value(status.conditions[0].status)" 2>/dev/null)

PREFIX="gs://${PROJECT_ID}-trading-data/query-results/${EXEC_NAME}"
log "results at: $PREFIX"

# Always emit the summary to stdout — it has the result tables either way.
gcloud storage cat "${PREFIX}/summary.md" 2>/dev/null || \
    echo "warn: ${PREFIX}/summary.md not found" >&2

[[ "$CONCLUSION" == "True" ]] && exit 0 || exit 1
