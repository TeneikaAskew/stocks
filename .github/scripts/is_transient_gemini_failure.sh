#!/usr/bin/env bash
# Did a monthly-doc-refresh run fail because Vertex stalled, or because the
# repo's own gates/prompts failed?
#
# Usage: is_transient_gemini_failure.sh <run_id> [attempt]
#
# EXIT CODES -- three, and callers must branch on all three:
#
#   0  transient: an attributable CLI transport record in the failed step
#   1  not transient: the evidence was read and holds no such record
#   2  could not classify: an API call or a log read failed, so there IS no
#      evidence to rule on
#
# 1 and 2 were one code once, and `gh` itself exits 1 on any failed request,
# so a 403 or a momentarily unavailable log looked exactly like "the repo's
# own failure": the caller took its negative branch and the recovery went
# green having examined nothing. The ERR trap below makes 2 the code for
# ANYTHING unexpected; only the two deliberate `exit 1`s mean "not
# transient". (Codex, PR #1032, round 11.)
#
# NOTE ON WHERE THIS LIVES. An earlier design put a helper in .github/scripts/
# and had refresh-architecture-docs.yml execute it BETWEEN Gemini invocations,
# which let a prompt-injected tool call rewrite it and the next step run it as
# bash (Codex, PR #1032). That does not apply here: this script runs only in
# rerun-transient-doc-refresh.yml, which never invokes a model and whose
# checkout no model has ever written to.
#
# WHERE IT LOOKS
#
# Inside the FAILED STEP's own section of the failed job's log, and nowhere
# else. The section is cut by the step's `started_at`/`completed_at` from the
# jobs API against the timestamp the RUNNER prefixes onto every log line --
# both sides come from GitHub, not from the stream.
#
# An earlier version took the last 40 lines of the whole job instead. The
# refresh job runs "Upload the regenerated documents when a gate fails" and
# then the runner's own post-job cleanup AFTER the Gemini step dies, and all of
# it lands in the same log after the fatal record: the committed sample in
# .github/workflows/logs.txt:427-442 is 16 cleanup lines with no upload step at
# all. A real stall would routinely scroll out of that window, the classifier
# would call it "the repo's own failure", and the whole re-run would be a
# silent no-op. (Codex, PR #1032.)
#
# WHAT IT MATCHES, AND WHAT THAT IS WORTH
#
# One attributable CLI error record on ONE line: the CLI's emitter, the path of
# the report only the CLI writes, and the transport cause. The prefix alone
# never discriminated -- the CLI emits it for internal errors too. Two real
# samples from this project:
#
#   ...gemini-client-error-<id>.json TypeError: terminated    <- transport
#   ...gemini-client-error-<id>.json RetryableQuotaError: ... <- vendor 429, retried out
#   ...gemini-client-error-<id>.json Error: Couldn't ...      <- internal
#
# This is a TEXTUAL shape in a stream that merges the model's stdout with the
# CLI's stderr, so it is forgeable in principle: a model that emitted the whole
# line verbatim, with a plausible report path, would be believed. Separating
# the CLI's diagnostics from model stdout would need the refresh workflow to
# capture stderr independently, and that file would sit in the workspace the
# model can write to, so it is not obviously stronger.
#
# What bounds the damage is that nothing with lasting effect is decided on
# this match. A false positive costs one re-run; it cannot publish anything,
# because the re-run goes through every gate exactly as a first attempt does.
# The annotate job runs this check again against attempt 1 only to WORD its
# comment -- the same classifier over the same log is not independent evidence,
# which is why that job annotates a failure PR and never closes one. (Codex,
# PR #1032, round 11.)
set -euo pipefail
trap 'echo "cannot classify run ${RUN_ID:-?}: unexpected failure (exit $?) at line ${LINENO}" >&2; exit 2' ERR

# Every API read goes through this so an operational failure is exit 2 with
# the request named, never the bare exit 1 of gh.
api() {
  gh api "$@" || {
    echo "cannot classify run ${RUN_ID}: request ${1} failed (exit $?)" >&2
    exit 2
  }
}

RUN_ID="${1:?run id required}"
ATTEMPT="${2:-}"
REPO="${REPO:?REPO required}"

RECORD='^Error when talking to Gemini API Full report available at: /tmp/gemini-client-error-[^ ]+ '
# RetryableQuotaError is the CLI's own name for a 429 RESOURCE_EXHAUSTED it
# already retried ten times with backoff before giving up. Run 25 died on one
# after six minutes, the vendor's page says "try again later", and one bounded
# re-run ~15 minutes on (the time attempt 2 takes to reach the same call) is
# the same remedy as for a stalled body. (Run 25, 2026-09-07.)
TRANSPORT='(TypeError: terminated|ECONNRESET|socket hang up|UND_ERR_BODY_TIMEOUT|UND_ERR_HEADERS_TIMEOUT|UND_ERR_CONNECT_TIMEOUT|UND_ERR_SOCKET|RetryableQuotaError)'
FAILED_STEP_JQ='.steps[]? | select(.conclusion == "failure") | select(.started_at and .completed_at) | "\(.started_at)\t\(.completed_at)"'

if [ -n "$ATTEMPT" ]; then
  JOBS_URL="repos/${REPO}/actions/runs/${RUN_ID}/attempts/${ATTEMPT}/jobs?per_page=100"
else
  JOBS_URL="repos/${REPO}/actions/runs/${RUN_ID}/jobs?per_page=100"
fi

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# RAW per-job logs. `gh run view --log-failed` prefixes every line with job and
# step columns (`<job>\t<step>\t<timestamp> ...`), which defeats a start-
# anchored match entirely and would make this a silent no-op. (Codex, #1032.)
api "$JOBS_URL" --jq '.jobs[] | select(.conclusion == "failure") | .id' > "$WORK/failed_jobs.txt"
: > "$WORK/failed_steps.log"
while read -r JOB_ID; do
  [ -n "$JOB_ID" ] || continue
  api "repos/${REPO}/actions/jobs/${JOB_ID}" --jq "$FAILED_STEP_JQ" > "$WORK/windows.txt"
  # --allow-escape-sequences: the raw log carries the runner's ANSI colour
  # codes on every `##[group]Run` echo, and gh refuses to print a body with
  # escape sequences without it ("pass --allow-escape-sequences to output it
  # anyway", exit 1). The first production run of this classifier died there:
  # exit 2 on every real log, so it could never have re-run anything. The test
  # stub now refuses exactly as gh does. (Run 24, 2026-09-07.)
  api "repos/${REPO}/actions/jobs/${JOB_ID}/logs" --allow-escape-sequences > "$WORK/job.log"
  # Keep only the lines the runner stamped inside a failed step of THIS job.
  # Compared on YYYY-MM-DDTHH:MM:SS: the log carries sub-second precision and
  # the API does not, and a naive string compare would then drop every line in
  # the step's first and last second.
  awk -F'\t' 'NR==FNR { lo[++n]=substr($1,1,19); hi[n]=substr($2,1,19); next }
              { split($0, f, " "); ts = substr(f[1], 1, 19)
                for (i = 1; i <= n; i++) if (ts >= lo[i] && ts <= hi[i]) { print; next } }' \
      "$WORK/windows.txt" "$WORK/job.log" >> "$WORK/failed_steps.log"
done < "$WORK/failed_jobs.txt"

if [ ! -s "$WORK/failed_steps.log" ]; then
  echo "no failed-step log section for run ${RUN_ID}${ATTEMPT:+ attempt ${ATTEMPT}}; not classifying as transient"
  exit 1
fi

# Scanned from a FILE, never through a pipe. `printf "$SECTION" | grep -q`
# under pipefail read a confirmed stall as "not transient" whenever more than
# a pipe buffer of output followed the record: grep exits on its first match,
# printf takes SIGPIPE, the pipeline is non-zero, and an `if` condition does
# not reach the ERR trap. (Codex, PR #1032, round 12.)
# ANSI sequences stripped before the timestamp: a coloured line starts with
# the runner's timestamp and then the colour code, and the record anchor is
# start-of-line.
sed -E 's/\x1b\[[0-9;]*[A-Za-z]//g; s/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+Z //' "$WORK/failed_steps.log" > "$WORK/section.log"

if grep -qE "${RECORD}${TRANSPORT}" "$WORK/section.log"; then
  CAUSE=$(grep -oE "${RECORD}${TRANSPORT}" "$WORK/section.log" | grep -oE "$TRANSPORT" | sort -u | tr '\n' ' ')
  echo "transient Vertex transport stall: ${CAUSE}"
  exit 0
fi

echo "no attributable CLI transport-error record in the failed step; this is the repo's own failure"
exit 1
