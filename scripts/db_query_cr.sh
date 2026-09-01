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

# Claude Code Remote / Cowork sessions export CLOUDSDK_AUTH_ACCESS_TOKEN as a
# short placeholder, not a real OAuth token. Bare `gcloud` then fails with
# ACCESS_TOKEN_TYPE_UNSUPPORTED.
#
# Discriminate on LENGTH, not on a `ya29.` prefix. Google access tokens are
# opaque: the prefix is a convention, not a contract, so a prefix test would
# silently discard a legitimate token in some other format and fall back to
# whatever ambient account gcloud has — a different identity, or none. Length
# is format-agnostic and the gap is not close: the placeholder is 14
# characters, real access tokens run to hundreds. Anything under 40 is not a
# credential in any format.
_TOKEN_MIN_LEN=40
if [[ -n "${CLOUDSDK_AUTH_ACCESS_TOKEN:-}" \
      && ${#CLOUDSDK_AUTH_ACCESS_TOKEN} -lt $_TOKEN_MIN_LEN ]]; then
    echo "note: CLOUDSDK_AUTH_ACCESS_TOKEN is ${#CLOUDSDK_AUTH_ACCESS_TOKEN} chars," >&2
    echo "      too short to be a real access token — ignoring it and using" >&2
    echo "      gcloud's configured credentials instead." >&2
    unset CLOUDSDK_AUTH_ACCESS_TOKEN
fi

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

# NB: the `if` matters. Written as `[[ ... ]] && echo`, this function returns 1
# whenever QUIET is true, and under `set -e` that aborted the script at the
# first log call -- so `--quiet` exited 1 having printed nothing at all, which
# a caller could easily read as "the query returned no rows".
log() { if [[ "$QUIET" != "true" ]]; then echo "$@" >&2; fi; }

# Build env-var overrides. Use the ^|^ delimiter so embedded commas in the
# SQL don't confuse gcloud's default CSV parsing.
ENV_OVERRIDES="^|^DB_QUERY_SQL=${SQL}|DB_QUERY_COMMIT=${COMMIT}|DB_QUERY_TIMEOUT_SECONDS=${TIMEOUT_S}"

log "dispatching db-query CR Job (commit=$COMMIT, timeout=${TIMEOUT_S}s, sql=${#SQL} chars)..."

# Create the execution with --async so the execution id comes from the CREATE
# call. `--wait` cannot supply it: when the execution's task fails, gcloud exits
# non-zero and prints NOTHING to stdout, so a --wait dispatcher cannot tell
# "no execution was created" from "an execution ran and failed". Those two need
# opposite handling — the second one has a summary in GCS and, under --commit,
# may have already persisted statements (gcp/queries/run_query.py commits each
# statement independently and halts the batch on a system error). Reporting it
# as "nothing ran" hides that record and invites a retry that re-commits.
#
# The previous version compounded this: it sent stderr to /dev/null and, when
# the name came back empty, fell back to `executions list --limit=1` — i.e. to
# whatever execution already existed, printing a PREVIOUS run's summary as the
# answer to the query you just asked. A wrong answer that looks right is worse
# than no answer (CLAUDE.md Rule 3.7).
ERR_FILE=$(mktemp)
# Bounds the candidate set for the ambiguous case below, and verifies any id
# recovered from stderr. Backed off 60s so clock skew between here and GCP
# cannot make a genuinely new execution look old.
START_TS=$(date -u -d '60 seconds ago' +%Y-%m-%dT%H:%M:%S 2>/dev/null \
           || date -u -v-60S +%Y-%m-%dT%H:%M:%S)
set +e
EXEC_NAME=$(gcloud run jobs execute "$JOB" \
    --region="$REGION" \
    --update-env-vars="$ENV_OVERRIDES" \
    --async \
    --format="value(metadata.name)" 2>"$ERR_FILE")
RC=$?
set -e

# A non-zero exit does not by itself prove the execution was never created.
# If the API accepted the request and the response was then lost — connection
# reset, timeout, the CLI interrupted — gcloud exits non-zero with nothing on
# stdout while the execution runs on regardless. Claiming "nothing ran" there
# is the same false negative this script exists to remove, and under --commit
# it invites a retry that applies the writes twice. So: prove it, or say the
# outcome is unknown. Three tiers, conservative by default.
if [[ $RC -ne 0 || -z "$EXEC_NAME" ]]; then
    # Both tiers below read gcloud's stderr, and stderr is NOT a trusted
    # channel: with HTTP logging on it carries the request payload, which
    # carries this invocation's SQL. An unanchored scan would let the query
    # text decide the dispatcher's behaviour — SQL containing something shaped
    # like an execution id would be adopted as one, and SQL containing the word
    # NOT_FOUND would be read as a rejection. Both recreate the stale-result
    # and unsafe-retry defects this script exists to remove. So match only
    # against gcloud's own message forms, anchored at line start, and then
    # verify the result against the API rather than trusting the text.
    ERROR_LINES=$(grep -E '^ERROR: \(gcloud\.' "$ERR_FILE" || true)

    # 1. gcloud names the execution in two known message forms. Extract from
    #    those only, then confirm with the API that the candidate is real and
    #    was created in this dispatch window — an id echoed from the payload
    #    would name an older execution and fail the window check.
    #    Anchored at line start, because that is where gcloud puts them:
    #      Execution [db-query-gc6ns] is being started asynchronously.
    #      gcloud run jobs executions describe db-query-gc6ns
    #    A logged request payload appears mid-line after `body:` or a JSON
    #    key, so it cannot match. (Verified: SQL containing the text
    #    `Execution [db-query-xxxxx]` was adopted before this anchor and is
    #    rejected after it.)
    RECOVERED=$(grep -oE "^(Execution \[|gcloud( beta)? run jobs executions describe )${JOB}-[a-z0-9]{5}" "$ERR_FILE" 2>/dev/null \
                | grep -oE "${JOB}-[a-z0-9]{5}" | head -1 || true)
    RECOVERED_CREATED=""
    if [[ -n "$RECOVERED" ]]; then
        RECOVERED_CREATED=$(gcloud beta run jobs executions describe "$RECOVERED" \
            --region="$REGION" --format="value(metadata.creationTimestamp)" 2>/dev/null \
            | cut -c1-19 || true)
    fi

    if [[ -n "$RECOVERED" && -n "$RECOVERED_CREATED" \
          && ! "$RECOVERED_CREATED" < "$START_TS" ]]; then
        EXEC_NAME="$RECOVERED"
        log "gcloud exited $RC but named execution $EXEC_NAME (created $RECOVERED_CREATED) — using it"
    elif grep -qE '^ERROR: \(gcloud\.[a-z.]+\) (UNAUTHENTICATED|PERMISSION_DENIED|INVALID_ARGUMENT|NOT_FOUND|FAILED_PRECONDITION)\b' <<<"$ERROR_LINES" \
      || grep -qE '^(ERROR: )?.*(unrecognized arguments|argument .*: expected|Invalid choice)' <<<"$ERROR_LINES"; then
        # 2. The API rejected the request, or gcloud refused to send one.
        #    These are the only cases where "nothing ran" is provable — and
        #    only when the status appears in gcloud's own ERROR: line, not
        #    anywhere in the stream.
        echo "error: the request was rejected before any execution was created" >&2
        echo "       (gcloud exit $RC). No query was run." >&2
        sed 's/^/       | /' "$ERR_FILE" >&2
        rm -f "$ERR_FILE"
        exit 1
    else
        # 3. Ambiguous. Do not claim either outcome.
        echo "error: dispatch outcome is UNKNOWN (gcloud exit $RC, no execution id)." >&2
        echo "       The request may have been accepted and may be running now." >&2
        if [[ -n "$RECOVERED" ]]; then
            echo "       stderr mentioned $RECOVERED, but it could not be confirmed as" >&2
            echo "       created by this dispatch, so it is NOT being treated as yours." >&2
        fi
        if [[ "$COMMIT" == "true" ]]; then
            echo "       This was a --commit run: DO NOT RETRY before reconciling," >&2
            echo "       or the writes may be applied twice." >&2
        fi
        echo "       Executions created at or after $START_TS are CANDIDATES — the" >&2
        echo "       job is shared, so others may appear in the same window and none" >&2
        echo "       of them is identified as yours by timing alone. List them:" >&2
        echo "         gcloud beta run jobs executions list --job=$JOB --region=$REGION \\" >&2
        echo "           --format='table(name,metadata.creationTimestamp,status.conditions[0].status)'" >&2
        echo "       Identify yours by matching your SQL against each candidate's" >&2
        echo "       DB_QUERY_SQL override:" >&2
        echo "         gcloud beta run jobs executions describe <name> --region=$REGION \\" >&2
        echo "           --format='value(spec.template.spec.template.spec.containers[0].env)'" >&2
        sed 's/^/       | /' "$ERR_FILE" >&2
        rm -f "$ERR_FILE"
        exit 1
    fi
fi
rm -f "$ERR_FILE"
log "execution: $EXEC_NAME"

# From here the execution EXISTS. Every exit path below names it, and none of
# them may claim that nothing ran.
completed_status() {
    gcloud beta run jobs executions describe "$EXEC_NAME" \
        --region="$REGION" --format=json 2>/dev/null \
    | python3 -c 'import sys, json
d = json.load(sys.stdin)
for c in d.get("status", {}).get("conditions", []):
    if c.get("type") == "Completed":
        print(c.get("status") or "Unknown")
        break'
}

# Budget from the JOB'S TASK TIMEOUT, not from TIMEOUT_S. TIMEOUT_S is a
# per-statement `statement_timeout`, applied independently to each statement
# in a multi-statement batch, so `TIMEOUT_S + slack` can be exceeded by a
# batch that is behaving perfectly — abandoning a healthy execution before
# its summary exists. The task timeout is the real ceiling: nothing this job
# runs can outlast it. Add slack for image pull and provisioning.
TASK_TIMEOUT_S=$(gcloud run jobs describe "$JOB" --region="$REGION" \
    --format="value(spec.template.spec.template.spec.timeoutSeconds)" 2>/dev/null || true)
if ! [[ "$TASK_TIMEOUT_S" =~ ^[0-9]+$ ]]; then
    # Could not read it — take a generous constant rather than a tight guess.
    # Waiting too long costs a slow failure; waiting too little reports an
    # unknown outcome for a run that was fine.
    TASK_TIMEOUT_S=3600
    log "could not read $JOB task timeout; assuming ${TASK_TIMEOUT_S}s"
fi
WAIT_BUDGET_S=$(( TASK_TIMEOUT_S + 900 ))
log "waiting up to ${WAIT_BUDGET_S}s for $EXEC_NAME..."
CONCLUSION=""
while [[ "$CONCLUSION" != "True" && "$CONCLUSION" != "False" ]]; do
    if (( SECONDS >= WAIT_BUDGET_S )); then
        echo "error: execution $EXEC_NAME did not reach a terminal state within" >&2
        echo "       ${WAIT_BUDGET_S}s. It WAS created and may still be running; under" >&2
        echo "       --commit some statements may already have persisted. Do not retry" >&2
        echo "       before checking:" >&2
        echo "         gcloud beta run jobs executions describe $EXEC_NAME --region=$REGION" >&2
        exit 1
    fi
    sleep 5
    CONCLUSION=$(completed_status || true)
done

PREFIX="gs://${PROJECT_ID}-trading-data/query-results/${EXEC_NAME}"
log "results at: $PREFIX"

# Emit the summary for a FAILED execution too. gcp/db_query_job.py uploads the
# artifacts before propagating the runner's exit code, so a failed execution
# still has one — and under --commit its per-statement records are the only
# evidence of which statements persisted before the batch halted.
# The summary is read from the execution THIS invocation created, so it can
# never be another run's output.
if ! gcloud storage cat "${PREFIX}/summary.md" 2>/dev/null; then
    echo "error: ${PREFIX}/summary.md not found — execution $EXEC_NAME wrote no summary." >&2
    echo "       Do not treat any earlier output as the answer to this query." >&2
    exit 1
fi

if [[ "$CONCLUSION" != "True" ]]; then
    echo "error: execution $EXEC_NAME failed. The summary above is that execution's own" >&2
    echo "       record, not a previous run's — statements it reports as committed HAVE" >&2
    echo "       persisted. Read it before retrying." >&2
    exit 1
fi
exit 0
