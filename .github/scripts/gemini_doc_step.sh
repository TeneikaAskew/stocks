#!/usr/bin/env bash
# Run one .github/prompts/<name>.md through the Gemini CLI, with a bounded
# retry for VENDOR TRANSPORT failures only.
#
# Why this exists. Run 20 (2026-09-07) died at "Regenerate
# 05-c-DATA_DEPENDENCIES.md" after 6m45s of silence:
#
#   Error when talking to Gemini API ... TypeError: terminated
#     [cause]: BodyTimeoutError  code: 'UND_ERR_BODY_TIMEOUT'
#   An unexpected critical error occurred:[object Object]
#
# The Vertex streaming response body stalled and the Gemini CLI exits 1.
# Run 19, twenty minutes earlier, had run the identical prompt against the
# identical file in 28 seconds. One vendor transport blip threw away a
# 13-minute run -- and on the 1st of the month it would throw away the whole
# monthly refresh with nobody watching, which is the one thing this workflow
# exists to do unattended.
#
# CLAUDE.md 3.7 draws the line this script implements. EXTERNAL (a vendor API
# we do not control) may be retried; INTERNAL (our prompt, our repo, our tool
# policy) must fail loud. So the retry fires ONLY when the transcript carries
# a transport signature. A model that refused, wrote to the wrong path, or hit
# the tool policy still fails on the first attempt, exactly as it does today:
# runs 15 and 16 must still go red, and a retry that swallowed those would be
# the silent fallback the rule forbids.
#
# Each attempt starts from the same baseline: the document exactly as this
# step found it. A failed attempt can leave it half-edited, and a retry that
# compounded that would be worse than the timeout.
#
# The baseline is snapshotted HERE, not taken from refresh-inputs/previous/.
# That directory is written by "Save previous doc versions", which runs BEFORE
# "Render inventory blocks", so it holds the committed PRE-render document. In
# any month where the inventory changed, restoring it would put the stale
# marker blocks back; the prompts correctly forbid editing inside a marker
# block, so a successful retry would carry those stale blocks to gate_markers()
# and fail against the fresh render -- the retry would still lose the refresh,
# just with a different error. (Codex, PR #1032.) Snapshotting what is on disk
# when this step starts is post-render by construction and needs no assumption
# about step order.
#
# Usage: gemini_doc_step.sh <prompt-basename> <doc-path-from-repo-root>
set -uo pipefail

PROMPT="${1:?prompt basename required}"
DOC="${2:?document path required}"
PROMPT_FILE=".github/prompts/${PROMPT}.md"
LOG="${RUNNER_TEMP:?RUNNER_TEMP required}/transcripts/${PROMPT}.log"
BASELINE="${RUNNER_TEMP:?RUNNER_TEMP required}/gemini-baseline/${PROMPT}"
MAX_ATTEMPTS="${GEMINI_MAX_ATTEMPTS:-2}"
# Seconds of backoff before a retry. Only the tests set this (to 0); the
# workflow uses the default, because a transport stall that just timed out is
# worth pausing on rather than reconnecting into instantly.
RETRY_SLEEP="${GEMINI_RETRY_SLEEP:-20}"

# Signatures of the Gemini CLI's undici HTTP client giving up on the Vertex
# connection. Every one is a transport failure with no response body, which
# is why none of them can be confused with a model that answered badly.
TRANSIENT='UND_ERR_BODY_TIMEOUT|UND_ERR_HEADERS_TIMEOUT|UND_ERR_CONNECT_TIMEOUT|UND_ERR_SOCKET|TypeError: terminated|ECONNRESET|socket hang up|Error when talking to Gemini API'

test -f "$PROMPT_FILE" || { echo "::error::no prompt at ${PROMPT_FILE}"; exit 1; }
mkdir -p "$(dirname "$LOG")" "$(dirname "$BASELINE")"

# The post-render, pre-model state. Captured before attempt 1 so a retry can
# put it back byte-for-byte.
if [ -f "$DOC" ]; then
  cp "$DOC" "$BASELINE"
else
  echo "::error::${DOC} does not exist; the render step should have left it in place"
  exit 1
fi

for ATTEMPT in $(seq 1 "$MAX_ATTEMPTS"); do
  if [ "$ATTEMPT" -gt 1 ]; then
    if [ ! -f "$BASELINE" ]; then
      echo "::error::no baseline snapshot at ${BASELINE}; refusing to retry ${PROMPT} against a workspace the failed attempt may have half-edited"
      exit 1
    fi
    cp "$BASELINE" "$DOC"
    echo "restored ${DOC} from the pre-attempt snapshot so attempt ${ATTEMPT} starts from the same baseline as attempt 1"
    sleep $(( (ATTEMPT - 1) * RETRY_SLEEP ))
  fi

  echo "gemini ${PROMPT} -> ${DOC} (attempt ${ATTEMPT}/${MAX_ATTEMPTS})"
  gemini --model "${GEMINI_MODEL}" --prompt "$(cat "$PROMPT_FILE")" 2>&1 | tee "$LOG"
  RC=${PIPESTATUS[0]}
  if [ "$RC" -eq 0 ]; then
    exit 0
  fi

  if ! grep -qE "$TRANSIENT" "$LOG"; then
    echo "::error::gemini ${PROMPT} failed (exit ${RC}) and its transcript carries no vendor-transport signature, so this is not a retryable failure. The transcript is above and is uploaded with the run."
    exit "$RC"
  fi
  echo "::warning::gemini ${PROMPT} hit a vendor transport failure on attempt ${ATTEMPT}/${MAX_ATTEMPTS} (exit ${RC}): $(grep -oE "$TRANSIENT" "$LOG" | sort -u | tr '\n' ' ')"
done

echo "::error::gemini ${PROMPT} failed ${MAX_ATTEMPTS} times, every time with a vendor transport failure. Vertex in ${GOOGLE_CLOUD_LOCATION:-?} is not answering; this is not a repo problem and re-running later is the fix."
exit 1
