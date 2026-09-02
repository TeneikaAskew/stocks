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
# A nonce only this dispatch's execution can carry. Used below to PROVE that a
# recovered execution id is ours; nothing in the job reads it.
DISPATCH_ID="d$(date -u +%s)-$$-${RANDOM}"
ENV_OVERRIDES="^|^DB_QUERY_SQL=${SQL}|DB_QUERY_COMMIT=${COMMIT}|DB_QUERY_TIMEOUT_SECONDS=${TIMEOUT_S}|DB_QUERY_DISPATCH_ID=${DISPATCH_ID}"

# Claude Code Remote / Cowork sessions export CLOUDSDK_AUTH_ACCESS_TOKEN as a
# short placeholder rather than a real OAuth token, and every gcloud call then
# fails UNAUTHENTICATED. Without this the failure surfaces at the GA/beta probe
# below, which blames a missing beta component -- the wrong cause, and one that
# sends an operator to install something they already have.
#
# Whether the token is usable is decided by ASKING THE API, not by inspecting
# the token. Two representation tests were tried first and both were wrong: a
# `ya29.` prefix (a convention, not a contract) and a minimum length (no
# contract either). An opaque value is precisely what you cannot validate by
# looking at it. This describe is read-only, so a failure here cannot have
# started anything.
#
# Two auth failures that must NOT be treated alike:
#
#   ACCESS_TOKEN_TYPE_UNSUPPORTED — the value is not a usable token at all.
#       Nothing is being substituted for a credential, because it never was
#       one. Safe to ignore and continue.
#
#   any other UNAUTHENTICATED — a real credential that has expired or been
#       revoked. Dropping it would run the query under gcloud's configured
#       principal instead: a DIFFERENT identity, possibly more privileged than
#       the one the caller deliberately selected by setting the variable. For
#       a --commit run that means writes executed as somebody else. An
#       expired token proves the token is unusable; it proves nothing about
#       whether switching identities is acceptable, so this stops instead.
#
# PERMISSION_DENIED likewise does not qualify: the token is valid and its
# identity lacks a role, and substituting another identity would hide exactly
# the problem the operator needs to see.
if [[ -n "${CLOUDSDK_AUTH_ACCESS_TOKEN:-}" ]]; then
    PROBE_ERR=$(mktemp)
    if ! gcloud run jobs describe "$JOB" --region="$REGION" \
             --format="value(metadata.name)" >/dev/null 2>"$PROBE_ERR"; then
        # TWO conditions, both required, because neither is sufficient alone.
        #
        # The API says the value is unusable AND the value is far too short to
        # have ever been a credential. Measured: a `ya29.`-shaped 58-character
        # string returns ACCESS_TOKEN_TYPE_UNSUPPORTED too, so that reason on
        # its own does NOT separate "harness placeholder" from "real token that
        # expired" — I could not obtain an expired token to establish that it
        # reports something different, so this does not rely on it. Length is
        # not being used to judge validity (the API already did that); it is
        # being used to establish that nothing the caller chose is being
        # discarded. Real access tokens run to hundreds of characters.
        if grep -q 'ACCESS_TOKEN_TYPE_UNSUPPORTED' "$PROBE_ERR" \
           && (( ${#CLOUDSDK_AUTH_ACCESS_TOKEN} < 40 )); then
            echo "note: CLOUDSDK_AUTH_ACCESS_TOKEN is ${#CLOUDSDK_AUTH_ACCESS_TOKEN} characters and the API" >&2
            echo "      rejected it as ACCESS_TOKEN_TYPE_UNSUPPORTED — a harness" >&2
            echo "      placeholder, not a credential. Ignoring it and using" >&2
            echo "      gcloud's configured credentials instead." >&2
            unset CLOUDSDK_AUTH_ACCESS_TOKEN
        elif grep -qE '^ERROR: \(gcloud\.[a-z.]+\) (UNAUTHENTICATED|UNAUTHORIZED)' "$PROBE_ERR"; then
            if [[ "${DB_QUERY_ALLOW_IDENTITY_FALLBACK:-}" == "1" ]]; then
                echo "note: CLOUDSDK_AUTH_ACCESS_TOKEN was rejected (UNAUTHENTICATED)." >&2
                echo "      DB_QUERY_ALLOW_IDENTITY_FALLBACK=1 is set, so continuing" >&2
                echo "      under gcloud's configured identity instead." >&2
                unset CLOUDSDK_AUTH_ACCESS_TOKEN
            else
                echo "error: CLOUDSDK_AUTH_ACCESS_TOKEN was rejected by the API, and it" >&2
                echo "       is ${#CLOUDSDK_AUTH_ACCESS_TOKEN} characters — long enough to be a real credential" >&2
                echo "       that has expired or been revoked. Refusing to silently run as a" >&2
                echo "       different principal — you set that variable on purpose, and" >&2
                echo "       gcloud's configured identity may hold different privileges." >&2
                echo "       Refresh the token, or unset it yourself, or re-run with" >&2
                echo "       DB_QUERY_ALLOW_IDENTITY_FALLBACK=1 to accept the switch." >&2
                sed 's/^/       | /' "$PROBE_ERR" >&2
                rm -f "$PROBE_ERR"
                exit 1
            fi
        fi
        # Anything else — network, PERMISSION_DENIED, an outage — leaves the
        # token alone so the real error surfaces below rather than here.
    fi
    rm -f "$PROBE_ERR"
fi

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
#
# Recovering it must not become "adopt whatever execution exists". Listing the
# most recent one is what this script used to do, and it printed a PREVIOUS
# query's summary as the answer to the one just asked -- a wrong answer that
# looks right, which is the whole reason this file is being changed
# (CLAUDE.md Rule 3.7). Two guards instead:
#
#   1. Match only gcloud's own message forms, ANCHORED AT LINE START. stderr is
#      not a trusted channel: with HTTP logging on it carries the request body,
#      hence this invocation's SQL, so an unanchored scan would let the query
#      text name the execution. A logged payload appears mid-line and cannot
#      match.
#   2. Confirm the candidate carries THIS dispatch's id. Timing cannot
#      establish ownership -- db-query is a shared job, so a concurrent
#      execution would satisfy any time window.
if [[ -z "$EXEC_NAME" ]]; then
    RECOVERED=$(grep -oE "^(Execution \[|gcloud( beta)? run jobs executions describe )${JOB}-[a-z0-9]{5}" "$EXEC_ERR" 2>/dev/null \
                | grep -oE "${JOB}-[a-z0-9]{5}" | head -1 || true)
    if [[ -n "$RECOVERED" ]] && $EXEC_CMD describe "$RECOVERED" \
            --region="$REGION" --format=json 2>/dev/null \
        | python3 -c 'import sys, json
d = json.load(sys.stdin)
want = sys.argv[1]
for c in d.get("spec", {}).get("template", {}).get("spec", {}).get("containers", []):
    for e in c.get("env", []):
        if e.get("name") == "DB_QUERY_DISPATCH_ID" and e.get("value") == want:
            sys.exit(0)
sys.exit(1)' "$DISPATCH_ID"; then
        EXEC_NAME="$RECOVERED"
        log "recovered execution $EXEC_NAME from stderr, confirmed ours by dispatch id"
    fi
fi

if [[ -z "$EXEC_NAME" ]]; then
    # Do not claim the query did not run. The dispatch call SUCCEEDED; only the
    # name is missing, so an execution may well be running right now. Under
    # --commit, telling the caller nothing happened invites a retry that
    # applies the writes twice.
    echo "error: dispatched successfully, but the execution name is UNKNOWN." >&2
    echo "       An execution may be running now. Do not assume nothing ran." >&2
    if [[ -n "$RECOVERED" ]]; then
        echo "       stderr mentioned $RECOVERED, but it does not carry this" >&2
        echo "       dispatch's id, so it is NOT being treated as yours." >&2
    fi
    if [[ "$COMMIT" == "true" ]]; then
        echo "       This was a --commit run: DO NOT RETRY before reconciling," >&2
        echo "       or the writes may be applied twice." >&2
    fi
    echo "       Yours, if it exists, is the execution whose DB_QUERY_DISPATCH_ID is" >&2
    echo "         $DISPATCH_ID" >&2
    echo "       Find it with:" >&2
    echo "         $EXEC_CMD list --job=$JOB --region=$REGION \\" >&2
    echo "           --format='value(name)' | while read -r n; do" >&2
    echo "             $EXEC_CMD describe \$n --region=$REGION --format=json \\" >&2
    echo "               | grep -q '$DISPATCH_ID' && echo \$n; done" >&2
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

# Require NON-EMPTY output, not merely a zero exit. A reader that succeeds and
# prints nothing (a zero-byte object, a truncated transfer) would otherwise be
# indistinguishable from a summary, and the script would exit 0 having shown
# the caller no result at all.
SUMMARY_FILE=$(mktemp)
if _read_summary_gcloud >"$SUMMARY_FILE" 2>/dev/null && [[ -s "$SUMMARY_FILE" ]]; then
    cat "$SUMMARY_FILE"
elif _read_summary_api >"$SUMMARY_FILE" 2>/dev/null && [[ -s "$SUMMARY_FILE" ]]; then
    cat "$SUMMARY_FILE"
else
    # A failed READ is not evidence the object is absent, and neither one says
    # anything about whether the query ran. The outcome is already known from
    # the poll above, so report it here rather than leaving the caller to infer
    # a failure from a missing artifact -- under --commit that inference is
    # what triggers a retry that applies the writes twice.
    echo "error: could not read ${PREFIX}/summary.md via gcloud storage or the" >&2
    echo "       Storage JSON API. That is a failure to FETCH the result, not" >&2
    echo "       evidence the query did not run." >&2
    if [[ "$CONCLUSION" == "True" ]]; then
        echo "       Execution $EXEC_NAME COMPLETED SUCCESSFULLY" >&2
        echo "       (succeeded=${SUCCEEDED_N:-0} failed=${FAILED_N:-0})." >&2
        if [[ "$COMMIT" == "true" ]]; then
            echo "       This was a --commit run and it succeeded: THE WRITES ARE" >&2
            echo "       APPLIED. Do NOT retry — that would apply them twice." >&2
        fi
        echo "       Retry the READ instead:" >&2
        echo "         gcloud storage cat ${PREFIX}/summary.md" >&2
    else
        echo "       Execution $EXEC_NAME did not complete successfully; under" >&2
        echo "       --commit, statements before the failure may still have persisted." >&2
    fi
    echo "       Artifacts are at ${PREFIX}/" >&2
fi
rm -f "$SUMMARY_FILE"

[[ "$CONCLUSION" == "True" ]] && exit 0 || exit 1
