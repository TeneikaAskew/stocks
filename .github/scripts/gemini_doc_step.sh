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
# Each attempt starts from the same baseline: every document a prompt may
# write, exactly as this step found it. A failed attempt can leave one
# half-edited, and a retry that compounded that would be worse than the
# timeout. It is the whole set and not just this step's own document because
# every invocation holds write_file/replace over the checkout and the
# post-model scan allowlists all four collectively -- so a failed
# data-dependencies attempt could alter 05-a-ARCHITECTURE.md, retry cleanly,
# and leave that edit eligible for publication. (Codex, PR #1032.)
#
# refresh-inputs/ is checked rather than restored. The model can write there
# too, and that tree is the one place the stray-write scan deliberately does
# not look; the frozen copy is restored only AFTER all four runs, so tampering
# would be erased without correcting the document already generated from it.
# A retry reading altered billing or snapshot data is a different failure from
# a transport stall, so it fails and names the files instead of quietly
# starting over. (Codex, PR #1032.)
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
SNAP_DIR="${RUNNER_TEMP:?RUNNER_TEMP required}/gemini-baseline/${PROMPT}"
# The documents a prompt may write, derived from check_generated_docs.DOCS and
# captured by the freeze step BEFORE the model ran -- reading it from the
# checkout here would re-open the hole the frozen script closes.
WRITABLE_LIST="${GEMINI_WRITABLE_DOCS_FILE:-${RUNNER_TEMP}/frozen/writable_docs.txt}"
FROZEN_INPUTS="${RUNNER_TEMP}/frozen/refresh-inputs"
MAX_ATTEMPTS="${GEMINI_MAX_ATTEMPTS:-2}"
# Seconds of backoff before a retry. Only the tests set this (to 0); the
# workflow uses the default, because a transport stall that just timed out is
# worth pausing on rather than reconnecting into instantly.
RETRY_SLEEP="${GEMINI_RETRY_SLEEP:-20}"

# A transport failure is recognised as a STRUCTURED CLI ERROR RECORD, not as a
# string anywhere in the transcript. The transcript is mixed stdout/stderr and
# the model can echo anything into it -- including, since it can read the
# checkout, the signature list in this very file. A whole-transcript grep let a
# model quote a code and then fail for an internal reason, and the run would
# blame Vertex and retry. (Codex, PR #1032.)
#
# Two things must both hold, and only in the tail, because the CLI emits its
# fatal record last and then exits:
#   FATAL     the CLI's own error emitter, line-anchored
#   TRANSPORT the undici cause underneath it
FATAL='^(Error when talking to Gemini API|An unexpected critical error occurred)'
TRANSPORT="UND_ERR_BODY_TIMEOUT|UND_ERR_HEADERS_TIMEOUT|UND_ERR_CONNECT_TIMEOUT|UND_ERR_SOCKET|TypeError: terminated|ECONNRESET|socket hang up"
TAIL_LINES="${GEMINI_TAIL_LINES:-40}"

# Did this attempt die of a vendor transport failure? Reads only the tail.
is_transport_failure() {
  local tail_txt
  tail_txt=$(tail -n "$TAIL_LINES" "$LOG")
  printf '%s\n' "$tail_txt" | grep -qE "$FATAL" \
    && printf '%s\n' "$tail_txt" | grep -qE "$TRANSPORT"
}

test -f "$PROMPT_FILE" || { echo "::error::no prompt at ${PROMPT_FILE}"; exit 1; }
test -s "$WRITABLE_LIST" || {
  echo "::error::no writable-document list at ${WRITABLE_LIST}; the freeze step must record it before any prompt runs"
  exit 1; }
mkdir -p "$(dirname "$LOG")" "$SNAP_DIR"

# The post-render, pre-model state of every writable document, captured before
# attempt 1 so a retry can put all of them back byte-for-byte.
WRITABLE=()
while IFS= read -r D; do [ -n "$D" ] && WRITABLE+=("$D"); done < "$WRITABLE_LIST"
case " ${WRITABLE[*]} " in
  *" ${DOC} "*) ;;
  *) echo "::error::${DOC} is not in ${WRITABLE_LIST}; a prompt writing a document the gates do not score is a bug, not a retryable failure"; exit 1;;
esac
for D in "${WRITABLE[@]}"; do
  if [ ! -f "$D" ]; then
    echo "::error::${D} does not exist; the render step should have left every writable document in place"
    exit 1
  fi
  cp "$D" "${SNAP_DIR}/$(printf '%s' "$D" | tr '/' '_')"
done
# The shape of the whole working tree before the model ran. A retry starts a
# FRESH CLI process, which re-reads project configuration from the workspace --
# and .gemini/settings.json can define command-backed MCP servers, which the
# new process would spawn with this job's GCP and GitHub credentials, before
# the post-model stray-write scan ever runs. Rather than enumerate that one
# path, nothing outside the writable documents may differ at all. (Codex, PR
# #1032.)
git status --porcelain | sort > "${SNAP_DIR}/status.before"

for ATTEMPT in $(seq 1 "$MAX_ATTEMPTS"); do
  if [ "$ATTEMPT" -gt 1 ]; then
    # The inputs the next attempt will read must be the ones the freeze took.
    if [ ! -d "$FROZEN_INPUTS" ]; then
      echo "::error::no frozen refresh-inputs at ${FROZEN_INPUTS}; refusing to retry ${PROMPT} without a way to check the inputs the next attempt would read"
      exit 1
    fi
    git status --porcelain | sort > "${SNAP_DIR}/status.after"
    if ! diff <(grep -vF -f "$WRITABLE_LIST" "${SNAP_DIR}/status.before" || true) \
              <(grep -vF -f "$WRITABLE_LIST" "${SNAP_DIR}/status.after" || true) \
              > "${SNAP_DIR}/status.diff" 2>&1; then
      echo "::error::the failed ${PROMPT} attempt changed the working tree outside the generated documents. A retry starts a fresh Gemini process that re-reads workspace configuration, so this is not something to restore past. Not a transport failure; refusing."
      cat "${SNAP_DIR}/status.diff"
      exit 1
    fi
    if ! diff -r -q "$FROZEN_INPUTS" refresh-inputs > "${SNAP_DIR}/inputs.diff" 2>&1; then
      echo "::error::the failed ${PROMPT} attempt changed refresh-inputs/, which the stray-write scan does not cover and the post-model restore would erase. Retrying would generate prose from altered inputs. Not a transport failure; refusing."
      cat "${SNAP_DIR}/inputs.diff"
      exit 1
    fi
    for D in "${WRITABLE[@]}"; do
      SNAP="${SNAP_DIR}/$(printf '%s' "$D" | tr '/' '_')"
      if [ ! -f "$SNAP" ]; then
        echo "::error::no baseline snapshot for ${D}; refusing to retry ${PROMPT} against a workspace the failed attempt may have half-edited"
        exit 1
      fi
      cmp -s "$SNAP" "$D" || echo "  ${D} was changed by the failed attempt; restoring"
      cp "$SNAP" "$D"
    done
    echo "restored ${#WRITABLE[@]} writable document(s) from the pre-attempt snapshot so attempt ${ATTEMPT} starts from the same baseline as attempt 1"
    sleep $(( (ATTEMPT - 1) * RETRY_SLEEP ))
  fi

  echo "gemini ${PROMPT} -> ${DOC} (attempt ${ATTEMPT}/${MAX_ATTEMPTS})"
  gemini --model "${GEMINI_MODEL}" --prompt "$(cat "$PROMPT_FILE")" 2>&1 | tee "$LOG"
  # Both statuses in one read: any command after the pipeline -- an assignment
  # included -- resets PIPESTATUS, so taking them one at a time leaves
  # PIPESTATUS[1] unbound under `set -u`.
  PIPE=("${PIPESTATUS[@]}")
  RC=${PIPE[0]}
  TEE_RC=${PIPE[1]}
  # gate_transcripts() reads a missing log as "no findings", so a tee that
  # failed would silently disable the truncation and unreadable-input checks
  # for this document while the run went on to publish. Taking only
  # PIPESTATUS[0] made that invisible. (Codex, PR #1032.)
  if [ "$TEE_RC" -ne 0 ] || [ ! -s "$LOG" ]; then
    echo "::error::the transcript for ${PROMPT} was not captured (tee exit ${TEE_RC}, log $( [ -s "$LOG" ] && echo non-empty || echo empty )). gate_transcripts() reads an absent log as clean, so this run cannot be verified."
    exit 1
  fi
  if [ "$RC" -eq 0 ]; then
    exit 0
  fi

  if ! is_transport_failure; then
    echo "::error::gemini ${PROMPT} failed (exit ${RC}) without a CLI transport-error record in the last ${TAIL_LINES} lines, so this is not a retryable failure. The transcript is above and is uploaded with the run."
    exit "$RC"
  fi
  echo "::warning::gemini ${PROMPT} hit a vendor transport failure on attempt ${ATTEMPT}/${MAX_ATTEMPTS} (exit ${RC}): $(tail -n "$TAIL_LINES" "$LOG" | grep -oE "$TRANSPORT" | sort -u | tr '\n' ' ')"
done

echo "::error::gemini ${PROMPT} failed ${MAX_ATTEMPTS} times, every time with a vendor transport failure. Vertex in ${GOOGLE_CLOUD_LOCATION:-?} is not answering; this is not a repo problem and re-running later is the fix."
exit 1
