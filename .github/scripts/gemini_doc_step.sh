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
# Each attempt starts from the same baseline. Before a retry the document is
# restored from refresh-inputs/previous/, so a half-applied edit from the
# failed attempt cannot compound into a double-applied one. If that frozen
# copy is missing the script refuses to retry rather than running the prompt
# against a workspace of unknown state.
#
# Usage: gemini_doc_step.sh <prompt-basename> <doc-path-from-repo-root>
set -uo pipefail

PROMPT="${1:?prompt basename required}"
DOC="${2:?document path required}"
PROMPT_FILE=".github/prompts/${PROMPT}.md"
LOG="${RUNNER_TEMP:?RUNNER_TEMP required}/transcripts/${PROMPT}.log"
PREV="refresh-inputs/previous/${DOC}"
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
mkdir -p "$(dirname "$LOG")"

for ATTEMPT in $(seq 1 "$MAX_ATTEMPTS"); do
  if [ "$ATTEMPT" -gt 1 ]; then
    if [ ! -f "$PREV" ]; then
      echo "::error::no frozen previous copy at ${PREV}; refusing to retry ${PROMPT} against a workspace the failed attempt may have half-edited"
      exit 1
    fi
    cp "$PREV" "$DOC"
    echo "restored ${DOC} from ${PREV} so attempt ${ATTEMPT} starts from the same baseline as attempt 1"
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
