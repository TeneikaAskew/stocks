#!/usr/bin/env bash
# Serialize apply-schema-on-change builds: wait until every build of this
# trigger that STARTED BEFORE this one has finished, then proceed.
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
# not finished within the deadline, exit non-zero. A guard that cannot see
# its peers must stop rather than reassure (same rule as the staging
# interlock, Codex on PR #990).
set -euo pipefail

SELF="${1:-}"
TAG="apply-schema-on-change"
POLL_SECONDS="${POLL_SECONDS:-20}"
DEADLINE_SECONDS="${DEADLINE_SECONDS:-1500}"   # below the build's 1800 s timeout

if [ -z "${SELF}" ]; then
  echo "usage: $0 <this build id>" >&2
  exit 2
fi

if ! self_start=$(gcloud builds describe "${SELF}" --format='value(createTime)' 2>&1); then
  echo "ERROR: cannot describe this build (${SELF}); cannot order it against its peers." >&2
  echo "       ${self_start}" >&2
  exit 1
fi
if [ -z "${self_start}" ]; then
  echo "ERROR: build ${SELF} has no createTime; refusing to guess the order." >&2
  exit 1
fi

waited=0
while :; do
  if ! ongoing=$(gcloud builds list --ongoing \
                   --filter="tags='${TAG}' AND createTime<'${self_start}'" \
                   --format='value(id)' 2>&1); then
    echo "ERROR: cannot list builds tagged '${TAG}', so an earlier schema build" >&2
    echo "       cannot be ruled out. Refusing rather than assuming none." >&2
    echo "       ${ongoing}" >&2
    exit 1
  fi
  earlier=""
  for id in ${ongoing}; do
    [ "${id}" = "${SELF}" ] || earlier="${earlier} ${id}"
  done
  if [ -z "${earlier}" ]; then
    echo "no earlier apply-schema-on-change build in flight — proceeding"
    exit 0
  fi
  if [ "${waited}" -ge "${DEADLINE_SECONDS}" ]; then
    echo "ERROR: earlier schema build(s) still running after ${waited}s:${earlier}" >&2
    echo "       Not applying this revision's schema out of order. Re-run this" >&2
    echo "       build once they finish (gcloud builds log <id>)." >&2
    exit 1
  fi
  echo "waiting ${POLL_SECONDS}s for earlier schema build(s):${earlier}"
  sleep "${POLL_SECONDS}"
  waited=$((waited + POLL_SECONDS))
done
