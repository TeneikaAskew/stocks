---
feat_id: FEAT-DEPLOY-001
req_ids: [REQ-OBS-001, REQ-FRESH-001]
issues: [1365]
canvases:
  - https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN
done_when:
  - "Notifier deployment tests prove its runtime identity is dedicated and only its three notification secrets and Logging/Run viewer roles are granted"
  - "Notifier deployment tests prove access setup failures abort before deploying the revision and existing Pub/Sub and scheduler invocation identities remain compatible"
  - "bash -n gcp/deploy.sh and the delivery gate pass with FEAT-DEPLOY-001 catalog and PR traceability records updated"
status: approved
supersedes: null
---

# Notifier audit access: deployment ownership split

## Problem

The user approved the freshness alert specification and implementation plan in
this session. Its deployment/access portion must use FEAT-DEPLOY-001 because
the delivery gate assigns gcp/deploy.sh to that capability. This document
separates that already approved portion into an independently reviewable PR;
it adds no new functional scope to the original approved design.

## Non-goals

Do not change audit checks, schedules, exit codes or notification rendering.
Do not deploy, mutate production IAM or rewrite historical issues during PR
preparation. Do not add log access to the shared trading-runner identity.

## Approaches considered

Granting the shared runner log access would broaden every job's access. A
dedicated notifier runtime account is chosen, matching the notifier-only access
contract and preserving its current external invoking identities.

## Design

In deploy_notifier, provision failure-notifier@PROJECT_ID.iam.gserviceaccount.com
idempotently. Grant it access to github-pat, github-repo and discord-webhook-gcp
only, and the read-only roles/run.viewer and roles/logging.viewer roles. Complete
these grants before deploying the service so denied setup cannot publish a
revision with missing access. Remove unrelated trading/database secrets and
environment from this service's deployment configuration. Use the dedicated
account as the service's runtime identity. Preserve shared SA_EMAIL for existing
Pub/Sub push and reconciler scheduler OIDC, and preserve their invoker grants.

The alert-rendering portion remains under the approved FEAT-OPS-001 freshness
specification. These branches are independently based on main; neither PR is
stacked. This configuration works with the existing notifier as well as the
new rendering implementation.

Capacity: one existing service, one dedicated service account, three secret
bindings and two viewer bindings. At most four additional setup CLI calls
relative to the existing deployment (account describe/create, dedicated webhook
access and Logging viewer); no per-row requests, SQL, new job or schedule. With
a 1–5s setup API estimate this adds roughly 4–20s to deployment. Runtime CPU,
512 MiB memory and maximum three instances are unchanged; service-account/IAM
configuration adds no recurring workload cost. The related evidence-read cost
is documented in the OPS PR.

## Risks

The deployer needs account creation/binding and actAs permissions. Setup failures
must abort visibly, without publishing the revision. Hermetic bash/gcloud-stub
tests verify dedicated identity, minimal secrets, grant-before-deploy ordering,
failure propagation and preservation of existing authenticated invocation paths.
Production deployment is a separate normal workflow step.
