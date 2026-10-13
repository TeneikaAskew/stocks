---
feat_id: FEAT-OPS-001
spec: docs/superpowers/specs/2026-10-12-feat-ops-001-freshness-alerts.md
branch: fix/feat-ops-001-freshness-alerts
pr: 1456
status: ready
---

# Freshness Audit Alert Implementation Plan

> For agentic workers: use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Report completed, failed freshness audits distinctly from job execution failures.

**Architecture:** Enrich existing watchdog notifications using bounded Cloud Logging
reads for the exact execution. Share the classification across GitHub and Discord
rendering, preserving existing grouping and recovery.

**Tech stack:** Python, requests, Google ADC, pytest, existing Cloud Run notifier.

**Spec:** docs/superpowers/specs/2026-10-12-feat-ops-001-freshness-alerts.md

## Global constraints

- Confirm Overall: STALE plus stale rows; job name or exit 1 alone is insufficient.
- One Logging request, up to 200 entries and 256 KiB processed evidence.
- Credential refresh and Logging request each bounded to 5s; no SQL or new schedules.
- Retain gcp-job-failure grouping labels and close-on-success reconciliation.
- Lookup failures remain visible and never suppress the execution failure alert.

## Review focus

1. ANSI formatting and writer lines must parse the actual October 10/11 output.
2. Logs from another execution must never classify this notification.
3. Truncated, paginated or malformed evidence must remain unclassified.
4. Crashes and timeouts after audit output must not be reported as audit findings.
5. Existing issues and other jobs must keep their grouping and recovery behavior.

## Task 1: Evidence lookup and classification

Spec: Design, exact-execution evidence. Advances done_when[1] and [2].
Files: gcp/failure_notifier.py; tests/gcp/test_failure_notifier.py.
Interfaces: enrich_freshness_failure(details: dict) -> dict; consumes extracted
notification details and returns details with classification and finding text.

- [ ] Add failing tests using the actual complete audit output: STALE findings,
  OK, absent summary, traceback/timeout, wrong execution, excessive response size,
  nextPageToken, malformed responses, denied access and credential failure.
- [ ] Run pytest tests/gcp/test_failure_notifier.py -k freshness; expect failures.
- [ ] Implement one execution-scoped Logging entries:list call using ADC and
  bounded refresh/HTTP timeouts. Validate resource labels and execution identity
  locally as well as in the request filter. Limit decoded evidence size and reject
  incomplete responses. Parse ANSI-stripped terminal lines, stale rows, writer
  lines and exit evidence; require intentional exit 1 without execution-error
  evidence. Handle only relevant watchdog notifications and preserve other jobs.
- [ ] Assert request filter, pageSize, timeout, credential timeout and single
  request count in tests; include handler delivery on unavailable evidence.
- [ ] Re-run the focused tests; expect pass.

## Task 2: Alert copy and deployment access

Spec: Design, notification wording and complete diagnostic evidence. Advances done_when[0] and [2].
Files: gcp/failure_notifier.py; scripts/audit_data_freshness.py;
tests/gcp/test_failure_notifier.py; tests/audits/test_audit_data_freshness.py.
Interfaces: existing renderers consume enriched details from Task 1.

- [ ] Add failing tests asserting Freshness Audit Failed in GitHub titles/body,
  repeat comments and Discord title, findings with table/ticker/values/writer,
  original execution context and visible unavailable-classification text.
- [ ] Test existing issue grouping labels, ordinary execution-failure copy,
  race-dedup routing and reconciliation compatibility.
- [ ] Run focused tests; expect failures on new copy assertions.
- [ ] Implement shared title/heading/finding rendering and invoke enrichment
  before delivering notifications. Preserve output limits and existing labels.
- [ ] Preserve complete diagnostic details in stale terminal rows and their alerts.
- [ ] Deliver deployment/access separately under the FEAT-DEPLOY-001 notifier-audit-access plan; this OPS branch changes no deploy configuration.
- [ ] Run pytest tests/gcp/test_failure_notifier.py
  tests/audits/test_audit_data_freshness.py; expect pass.

## Task 3: Reviewable delivery

Spec: Risks and done_when. Advances done_when[3].
Files: this plan; docs/product/02-FEATURE-CATALOG.md;
docs/product/12-PR-ISSUE-TRACEABILITY.md.

- [ ] Commit the approved spec alone, run its delivery gate, and merge the spec
  through its documentation PR before opening the implementation branch.
- [ ] Implement on fix/feat-ops-001-freshness-alerts based on the merged spec.
- [ ] Validate parsing against the saved read-only production evidence from both
  failed executions without sending notifications. Record the bounded I/O shape.
- [ ] Run the required docs audit on the branch and origin/main, commit gate and
  PR gate; resolve new findings. Review the whole change against the spec.
- [ ] Open one draft PR with spec, plan, capacity estimate and evidence for every
  done_when item; set this plan's pr field. Update only the FEAT-OPS-001 catalog
  record (Status and Last reviewed) and its PR traceability entry.
- [ ] Include Canvas check pending (report-only):
  https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN in the PR body.
- [ ] Mark the PR ready once checks and evidence pass. Report the PR and tests;
  production deployment remains a separate step.
