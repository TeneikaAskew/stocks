#!/usr/bin/env bash
# Serialize every build that mutates the apply-schema-migrations job: wait
# until every such build that STARTED BEFORE this one has finished, then
# proceed. Two triggers mutate that job:
#   apply-schema-on-change      (gcp/cloudbuild/apply-schema-cloudbuild.yaml)
#   deploy-solyra-api-staging   (gcp/cloudbuild/deploy-solyra-api-staging-
#                                cloudbuild.yaml, `migrate` step, so the API
#                                revision cannot exist before its schema)
# so this script scans both tags: whichever build started first applies
# first, and for a push that fires both, the schema is applied before the
# API deploys regardless of which trigger won the start.
#
# Two schema-changing pushes landing minutes apart start two builds that
# cannot see each other by default. Both would `jobs update` the shared
# apply-schema-migrations job and execute it, so COMPLETION order, not
# commit order, would decide which digest each execution ran and which
# stayed configured; an older build finishing last would roll every
# CREATE OR REPLACE view/function in schema.sql back to the older text
# (Codex on #1022). The staging deploy refuses to overlap
# (assert_no_concurrent_staging_deploy.sh); a schema build must not refuse,
# because the newer schema then never gets applied, so it WAITS instead:
# builds apply in start order, which for pushes to main is commit order.
#
# Only builds that started earlier are waited on. A build that started
# later waits on us in turn, so the ordering is total and there is no
# deadlock.
#
# FAILS CLOSED: if the build list cannot be read, or an earlier build has
# not finished within the budget, exit non-zero. A guard that cannot see
# its peers must stop rather than reassure (same rule as the staging
# interlock, Codex on PR #990).
#
# BUDGET: the wait starts AFTER the image build and push, and is followed
# by the apply job (its own --task-timeout, 1800 s in gcp/deploy.sh) plus
# the pin or deploy step. A fixed wait budget ignored all of that, so the
# outer Cloud Build timeout could kill the build in the middle of the apply
# (Codex on #1022). The budget is therefore read from the build itself:
# createTime and timeout from `gcloud builds describe`, and the wait stops
# once the time left before the build's own timeout falls below
# RESERVE_SECONDS, which covers the apply job and the step after it.
set -euo pipefail

SELF="${1:-}"
TAGS="apply-schema-on-change solyra-api-staging-deploy"
POLL_SECONDS="${POLL_SECONDS:-20}"
RESERVE_SECONDS="${RESERVE_SECONDS:-2100}"   # apply job 1800 s + deploy/pin 300 s

if [ -z "${SELF}" ]; then
  echo "usage: $0 <this build id>" >&2
  exit 2
fi

if ! self_desc=$(gcloud builds describe "${SELF}" --format='value(createTime,timeout)' 2>&1); then
  echo "ERROR: cannot describe this build (${SELF}); cannot order it against its peers." >&2
  echo "       ${self_desc}" >&2
  exit 1
fi
self_start=$(printf '%s' "${self_desc}" | cut -f1)
self_timeout=$(printf '%s' "${self_desc}" | cut -f2 | sed 's/[^0-9].*$//')
if [ -z "${self_start}" ] || [ -z "${self_timeout}" ]; then
  echo "ERROR: build ${SELF} has no createTime/timeout (${self_desc}); refusing to guess." >&2
  exit 1
fi
if ! self_epoch=$(date -u -d "${self_start}" +%s 2>&1); then
  echo "ERROR: cannot parse createTime '${self_start}': ${self_epoch}" >&2
  exit 1
fi
deadline_epoch=$((self_epoch + self_timeout - RESERVE_SECONDS))
echo "build ${SELF}: created ${self_start}, timeout ${self_timeout}s, reserving ${RESERVE_SECONDS}s;" \
     "will wait at most $((deadline_epoch - $(date -u +%s)))s for earlier schema builds"

while :; do
  earlier=""
  for tag in ${TAGS}; do
    if ! ongoing=$(gcloud builds list --ongoing \
                     --filter="tags='${tag}' AND createTime<'${self_start}'" \
                     --format='value(id)' 2>&1); then
      echo "ERROR: cannot list builds tagged '${tag}', so an earlier schema build" >&2
      echo "       cannot be ruled out. Refusing rather than assuming none." >&2
      echo "       ${ongoing}" >&2
      exit 1
    fi
    for id in ${ongoing}; do
      [ "${id}" = "${SELF}" ] || earlier="${earlier} ${id}"
    done
  done
  if [ -z "${earlier}" ]; then
    echo "no earlier schema-mutating build in flight — proceeding"
    exit 0
  fi
  now=$(date -u +%s)
  if [ "${now}" -ge "${deadline_epoch}" ]; then
    echo "ERROR: earlier schema build(s) still running with only $((self_epoch + self_timeout - now))s" >&2
    echo "       of this build's timeout left, below the ${RESERVE_SECONDS}s the apply and" >&2
    echo "       deploy need:${earlier}" >&2
    echo "       Not applying this revision's schema out of order. Re-run this" >&2
    echo "       build once they finish (gcloud builds log <id>)." >&2
    exit 1
  fi
  echo "waiting ${POLL_SECONDS}s for earlier schema build(s):${earlier} ($((deadline_epoch - now))s of budget left)"
  sleep "${POLL_SECONDS}"
done
