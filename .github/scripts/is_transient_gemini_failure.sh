#!/usr/bin/env bash
# Did a monthly-doc-refresh run fail because Vertex stalled, or because the
# repo's own gates/prompts failed? Exit 0 for transient, 1 for anything else.
#
# Usage: is_transient_gemini_failure.sh <run_id> [attempt]
#
# NOTE ON WHERE THIS LIVES. An earlier design put a helper in .github/scripts/
# and had refresh-architecture-docs.yml execute it BETWEEN Gemini invocations,
# which let a prompt-injected tool call rewrite it and the next step run it as
# bash (Codex, PR #1032). That does not apply here: this script runs only in
# rerun-transient-doc-refresh.yml, which never invokes a model and whose
# checkout no model has ever written to.
#
# WHAT IT MATCHES, AND WHAT THAT IS WORTH
#
# One attributable CLI error record on ONE line: the CLI's emitter, the path of
# the report only the CLI writes, and the transport cause. The prefix alone
# never discriminated -- the CLI emits it for internal errors too. Two real
# samples from this project:
#
#   ...gemini-client-error-<id>.json TypeError: terminated    <- transport
#   ...gemini-client-error-<id>.json Error: Couldn't ...      <- internal
#
# This is a TEXTUAL shape in a stream that merges the model's stdout with the
# CLI's stderr, so it is forgeable in principle: a model that emitted the whole
# line verbatim, with a plausible report path, would be believed. Separating
# the CLI's diagnostics from model stdout would need the refresh workflow to
# capture stderr independently, and that file would sit in the workspace the
# model can write to, so it is not obviously stronger.
#
# What bounds the damage is the job-level design rather than the match. A false
# positive costs one re-run; it cannot publish anything, because the re-run
# goes through every gate exactly as a first attempt does. And the cleanup job
# re-runs this check against attempt 1 before closing anything, so a forgery
# cannot get a still-actionable failure PR closed.
set -euo pipefail

RUN_ID="${1:?run id required}"
ATTEMPT="${2:-}"
REPO="${REPO:?REPO required}"

# Only the tail: the CLI emits its fatal record last and then exits.
TAIL_LINES="${TAIL_LINES:-40}"
RECORD='^Error when talking to Gemini API Full report available at: /tmp/gemini-client-error-[^ ]+ '
TRANSPORT='(TypeError: terminated|ECONNRESET|socket hang up|UND_ERR_BODY_TIMEOUT|UND_ERR_HEADERS_TIMEOUT|UND_ERR_CONNECT_TIMEOUT|UND_ERR_SOCKET)'

if [ -n "$ATTEMPT" ]; then
  JOBS_URL="repos/${REPO}/actions/runs/${RUN_ID}/attempts/${ATTEMPT}/jobs?per_page=100"
else
  JOBS_URL="repos/${REPO}/actions/runs/${RUN_ID}/jobs?per_page=100"
fi

# RAW per-job logs. `gh run view --log-failed` prefixes every line with job and
# step columns (`<job>\t<step>\t<timestamp> ...`), which defeats a start-
# anchored match entirely and would make this a silent no-op. (Codex, #1032.)
gh api "$JOBS_URL" --jq '.jobs[] | select(.conclusion == "failure") | .id' > /tmp/failed_jobs.txt
: > /tmp/failed.log
while read -r JOB_ID; do
  [ -n "$JOB_ID" ] || continue
  gh api "repos/${REPO}/actions/jobs/${JOB_ID}/logs" >> /tmp/failed.log
done < /tmp/failed_jobs.txt

if [ ! -s /tmp/failed.log ]; then
  echo "no failed-job logs for run ${RUN_ID}${ATTEMPT:+ attempt ${ATTEMPT}}; not classifying as transient"
  exit 1
fi

TAIL=$(sed -E 's/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+Z //' /tmp/failed.log | tail -n "$TAIL_LINES")

if printf '%s\n' "$TAIL" | grep -qE "${RECORD}${TRANSPORT}"; then
  CAUSE=$(printf '%s\n' "$TAIL" | grep -oE "${RECORD}${TRANSPORT}" | grep -oE "$TRANSPORT" | sort -u | tr '\n' ' ')
  echo "transient Vertex transport stall: ${CAUSE}"
  exit 0
fi

echo "no attributable CLI transport-error record in the last ${TAIL_LINES} lines; this is the repo's own failure"
exit 1
