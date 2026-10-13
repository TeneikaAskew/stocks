---
feat_id: FEAT-OPS-001
req_ids: [REQ-FRESH-001, REQ-OBS-001]
issues: [1365]
canvases:
  - https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN
done_when:
  - "Notifier tests prove confirmed stale audit results use Freshness Audit Failed in GitHub titles, bodies, repeat comments and Discord embeds, including findings and writer jobs"
  - "Notifier tests prove crashes, timeouts, missing audit evidence and failed evidence lookups retain execution-failure wording"
  - "Notifier tests prove evidence lookup is bounded and scoped to the alerted execution and existing issue grouping and recovery remain compatible"
  - "FEAT-OPS-001 catalog and PR traceability records include this change and required delivery checks pass"
status: approved
supersedes: null
---

# Distinguish freshness audit findings from execution failures

## Problem

Issue #1365 reports generic Cloud Run failures for freshness-watchdog-pzbwr
and freshness-watchdog-nl8lw on October 10 and 11, 2026. Both executions
completed their checks, reported Overall: STALE, then deliberately exited 1.
The finding was strat_features_5m.gamma_flip: 0/78 non-NULL rows for both IWM
and SPY, owned by strat-engine. Timestamp freshness checks passed.
gcp/failure_notifier.py hardcodes Job Failed regardless of the audit outcome.

## Non-goals

Change no freshness thresholds, SQL checks, schedules, exit codes or Cloud Run
execution status. Do not repair gamma_flip data, rewrite historical issue bodies,
send manual notifications, or deploy without the normal deployment workflow.

## Approaches considered

1. Rename all watchdog failures: small, but mislabels crashes and timeouts.
2. Emit an additional alert from the audit: risks duplicate notifications from
   the existing execution-failure sink.
3. Enrich the existing notification with the exact execution's audit evidence:
   chosen because it preserves the existing alert and distinguishes outcomes.

## Design

Delivery ownership: notification and audit code is FEAT-OPS-001. The already
approved deployment/access portion below is delivered independently under
docs/superpowers/specs/2026-10-12-feat-deploy-001-notifier-audit-access.md;
gcp/deploy.sh changes do not belong in the OPS implementation PR.

For freshness-watchdog execution-failure notifications, use Application Default
Credentials to read Cloud Logging evidence scoped to project, region, job and
the exact execution name. Never classify using a different or latest run.
Use a bounded query for terminal audit output. Strip ANSI formatting when
reading the existing terminal table; require an Overall: STALE result and
extract its stale rows and associated writer-job lines. Extend terminal output
with full diagnostic detail lines for stale rows, including last_row_at,
expected_latest and row_count_recent, so display truncation does not erase the
finding. Continue supporting the older table output for historical executions.
Inspect structured errors and all explicit task/attempt identities too; a
structured crash or ambiguous retry must not become an audit finding.
Preserve the original
Cloud Run failure message as execution context. Exit code 1 or job name alone
is insufficient evidence of an audit finding.

When confirmed, GitHub title and body heading and Discord embed title use
Freshness Audit Failed. Repeat comments use Additional freshness audit failure.
The finding section includes table/column, ticker, diagnostic values and writer.
On a new repeat, PATCH the current grouped issue title to match that event's
classification before appending its comment; do not edit old bodies or comments.
For #1365's evidence the message identifies 0/78 populated gamma_flip rows for
IWM and SPY and strat-engine as the responsible writer. An audit may flag
missing values or duration regressions, so describe the actual finding instead
of claiming every finding is old timestamps.

Crashes, timeouts and failures without conclusive audit evidence retain current
execution-failure wording. An unavailable evidence lookup must log the cause and
visibly state that audit classification is unavailable while still delivering
the original execution failure. This explicitly includes delayed log ingestion:
one lookup is the latency/cost contract; unavailable evidence is reported as
unclassified, never as proof of a crash or a passed audit. No polling or deferred
reclassification is part of this change. Other jobs retain their current notifications.
Keep existing labels, grouping by job and close-on-success reconciliation so
open issues created before this change continue to receive updates and close.

Extend deploy_notifier in gcp/deploy.sh to grant its service account the read-only
Cloud Logging access required by the query, using the existing fail-visible IAM
binding pattern. Provision a dedicated failure-notifier runtime service account;
do not add Logging viewer access to the shared trading-runner identity. Give the
notifier only its GitHub PAT/repository and dedicated Discord webhook secrets,
plus the Run viewer access needed for existing recovery reconciliation. Preserve
the existing Pub/Sub and scheduler invoking identities and their Run invoker grants.
Add classification and rendering tests to the existing notifier
suite, including complete October 10/11-style output, genuine execution errors,
cross-execution isolation, lookup failure and bounded response handling.

Capacity: at most 200 log entries and 256 KiB of processed evidence per relevant
notification. One Logging request and one credential refresh, no SQL, no new
scheduler or per-finding network requests. Bound Logging request timeout to 5s;
bound credential refresh separately to 5s and truncate rendered messages within
existing GitHub/Discord limits. If the response is incomplete, retain execution
failure classification. Added wall-clock budget is at most 10s per notification;
at 13 notifications/day this adds at most 130 service-seconds/day. Assuming
1 vCPU at $0.000024/vCPU-second, CPU cost ceiling is about $0.094/month plus
memory and existing platform pricing. Actual additional compute cost is lower
when no watchdog notification occurs. No change to audit-job runtime or cost.

## Risks

Audit text changes could prevent classification: tests pin the current output
and unknown evidence remains visibly unclassified. Logging lag or denied IAM
must never suppress notifications. Preserve labels to avoid breaking recovery
and deduplication. A later execution must never determine an earlier alert's
classification. Deployment validation includes reviewing a read-only query of
the two known executions; hermetic fixtures cover their outcomes without sending
production messages.
