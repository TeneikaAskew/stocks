---
feat_id: FEAT-DEPLOY-001
spec: docs/superpowers/specs/2026-10-12-feat-deploy-001-notifier-audit-access.md
branch: fix/feat-deploy-001-notifier-audit-access
pr: 1457
status: ready
---

# Notifier Audit Access Implementation Plan

> For agentic workers: use superpowers:executing-plans.

**Goal:** Give only the notifier the access required to classify audit outcomes.
**Architecture:** Dedicated runtime identity, minimal secrets and read-only
Logging/Run grants before deployment; existing invoking identities remain intact.
**Tech stack:** bash, gcloud, pytest.
**Spec:** docs/superpowers/specs/2026-10-12-feat-deploy-001-notifier-audit-access.md

## Global constraints

- No production deployment or IAM mutation during PR preparation.
- Grant only three notification secrets and Logging/Run viewer access.
- Preserve Pub/Sub and scheduler OIDC identities and invoker grants.
- Base independently on main; do not stack on the OPS rendering PR.

## Review focus

- Missing service account must be created idempotently.
- Denied account, secret or role setup must stop before deployment.
- Runtime service must not receive trading database secrets.
- Existing push/reconcile calls must retain their authorized identities.
- Setup changes must not alter runtime capacity or introduce schedules.

## Task 1: Isolated runtime identity and access

Spec: Design; advances done_when[0] and [1].
Files: gcp/deploy.sh; tests/gcp/test_notifier_sink_filter.py.
Interfaces: existing deploy_notifier function, validated against a hermetic
gcloud stub; no notifier Python interface change.

- [ ] Write dedicated-identity/minimal-secret and failure-propagation tests.
- [ ] Observe RED against the pre-fix deployment configuration.
- [ ] Provision notifier account and grant required access before service deploy;
  mount only its three notification secrets, preserve existing invoker identities.
- [ ] Run the sink/deployment tests and bash -n; expect pass.
- [ ] Run the commit delivery gate and commit the deployment changes.

## Task 2: Reviewable delivery

Spec: Risks and done_when; advances done_when[2].
Files: this plan; docs/product/02-FEATURE-CATALOG.md;
docs/product/12-PR-ISSUE-TRACEABILITY.md.

- [ ] Review the complete branch, fix substantive findings with failing
  regression tests and re-run the suite.
- [ ] Open one draft PR after approved specs land on main; set this plan's pr.
- [ ] Update only FEAT-DEPLOY-001 status/review date and its PR lineage.
- [ ] Run docs audit and the delivery PR gate, recording the prescribed
  post-merge source-review queue separately from content defects.
- [ ] Include spec, plan, all done_when evidence, capacity figures and Canvas
  check pending (report-only): https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN.
- [ ] Mark ready for review once checks pass; production deployment is separate.
