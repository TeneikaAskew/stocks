#!/usr/bin/env bash
# Refuse to start a staging deploy while another one is in flight.
#
# `solyra-api-staging` has TWO deploy paths and they cannot see each other:
#
#   * the `deploy-solyra-api-staging` Cloud Build trigger, on push to main
#   * `.github/workflows/deploy-staging.yml`, dispatched by an operator,
#     which runs `platform/deploy.sh` -> `gcloud builds submit`
#
# The workflow's `concurrency: deploy-staging` group serialises the workflow
# against itself and has no reach over a Cloud Build run. So an operator
# redeploy overlapping a push to main could interleave: the later build's
# image lands first and the earlier build's deploy runs last, leaving staging
# on code from neither run as anyone observed it. Deploying by DIGEST (see
# both build configs) makes each revision's artifact unambiguous; this makes
# the ORDER unambiguous too.
#
# Both paths are Cloud Build runs in the same project, so one can see the
# other -- they are tagged `solyra-api-staging-deploy` for exactly that.
#
# Fails loud rather than waiting: a queued deploy that silently starts twenty
# minutes later is harder to reason about than one an operator re-runs.
set -euo pipefail

# `gcloud builds submit` has no flag for build tags, so each path's tag has to
# live in its own config file and the two differ:
#   solyra-api-staging-deploy  the trigger config
#   solyra-api-image-build     platform/cloudbuild.yaml, used by the workflow
# Scanning for both is what makes the visibility symmetric.
SELF="${1:-}"          # this build's BUILD_ID, excluded from the scan
TAGS="solyra-api-staging-deploy solyra-api-image-build"

# FAIL CLOSED. This used to end in `|| true`, which turned a revoked
# `cloudbuild.builds.list`, an expired credential or a transient API error
# into an empty result -- so in exactly the environment where the interlock
# CANNOT see peer builds, it announced that there were none and let both
# paths deploy (Codex, PR #990). A guard that cannot check must stop, not
# reassure.
others=""
for tag in ${TAGS}; do
  if ! ongoing=$(gcloud builds list --ongoing \
                   --filter="tags='${tag}'" \
                   --format='value(id)' 2>&1); then
    echo "ERROR: cannot list builds tagged '${tag}', so a concurrent deploy" >&2
    echo "       cannot be ruled out. Refusing rather than assuming none." >&2
    echo "       ${ongoing}" >&2
    exit 1
  fi
  for id in ${ongoing}; do
    [ "${id}" = "${SELF}" ] || others="${others} ${id}"
  done
done

if [ -n "${others}" ]; then
  echo "ERROR: another solyra-api deploy build is already running:${others}" >&2
  echo "       Two deploys of this image must not overlap. Wait for it to" >&2
  echo "       finish (gcloud builds log <id>) and re-run this one." >&2
  exit 1
fi
echo "no concurrent solyra-api deploy build — proceeding"
