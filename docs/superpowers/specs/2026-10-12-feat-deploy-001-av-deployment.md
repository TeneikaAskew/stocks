---
feat_id: FEAT-DEPLOY-001
req_ids: ["REQ-SECRET-001", "REQ-DEPLOY-001", "REQ-CAP-001", "REQ-CAP-002", "REQ-CAP-003", "REQ-OBS-001"]
issues: [1201]
canvases: ["https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN"]
done_when:
  - "Stubbed deployment tests prove targeted create/update convergence, safe Secret Manager usage and unrelated-resource isolation."
  - "Audit scheduler IAM failures are propagated and only the exact least-privilege reader grant is requested."
  - "New AV schedules and closing-only behavior have explicit CLI, timezone, capacity and rollback documentation."
  - "The targeted rollout verifier checks actual deployed settings and the FEAT-DEPLOY-001 record records rollout evidence."
status: approved
supersedes: null
---

# Converge targeted AV jobs, secrets, audit IAM and bounded schedules

## Authorization and intake

This records the scope of the six-stage remediation plan presented after the live AV/GCP audit and authorized by the user on 2026-10-12: "Proceed with the plan, executing inn parallel". Execution method: parallel isolated worktrees, one author and PR per capability. Capability: FEAT-DEPLOY-001; matching catalog row in docs/product/02-FEATURE-CATALOG.md. The listed issues are touched, not claimed closed without their own acceptance evidence.

## Problem

Three deployed news jobs use inline API keys despite source deployment functions defining secret references. Scheduler audit IAM is not ensured reliably. Required indicator/reference refresh and closing options jobs have no deployment path.

## Non-goals

No expansion to all 128 APIs, change to strategy/model promotion or risk calibration, fabricated financial values, blind rewrite of historical timestamps, unrelated IAM/audience changes, or unbounded backfill. API failures and historical-only exclusions remain explicit.

## Approaches considered

1. Targeted contract repair, independent reviewed streams, bounded source-backed repair and selective deployment — chosen to preserve the verified working paths.
2. Replace the complete ingestion platform — excessive scope and operational risk.
3. Change schedules without repairing data contracts — leaves the demonstrated corruption and observability gaps.

## Design

Add a selective av-remediation deployment path that converges only the authorized AV feeds/auditor and new bounded refresh jobs, preserving unrelated services and audience/IAM. Use Secret Manager references and safe env replacement for all three news jobs; set identical runtime/args controls in create and update paths, zero retries for incomplete-sensitive feeds. Grant the existing auditor identity the minimal scheduler-reader role when needed and fail closed on inability to read or update that exact policy. Configure GCS raw-response bucket and a 90-day object-age lifecycle rule scoped only to the exact av/raw/ prefix, preserving existing bucket lifecycle entries. Wire sibling module CLIs only when their reviewed implementation exists: indicators incremental Tue–Sat 02:45 ET; native indices weekdays 23:15 ET; ETF/actions/listing weekly Sunday 05:15 ET; bounded estimates weekdays 06:15 ET. Add a separate closing-only options job with a 13:00–16:00 hourly trigger guarded by the actual exchange close (including half-days); regular job uses the shared RTH guard. Leave AV_INDICATOR_COVERAGE_ENABLED false until the first scheduled-writer bounded refresh is verified; then enable it on the existing watchdog. Stage targeted rollout from reviewed source and verify actual deployed flags/secrets/IAM/schedule targets.

### File ownership

gcp/deploy.sh and its focused deployment tests; deployment runbooks; generated inventory blocks only if permitted by the current gate. No unrelated service deployment.

### Capacity and cost

Indicator: 54 calls, <=350s, timeout1800s. Index: ~3 calls/incremental dates, <=185s, timeout1200s. ETF/reference: ~10 calls/<=20k listing rows, <=675s including SQL margin, timeout2700s. Estimates: <=100calls,~270s,timeout1800s. All oneCPU512Mi zero retries. Insider/news capped300 responses, <=810s typical bounded estimate, timeout3600s. Existing earnings-history long timeout remains. Closing job only actual-close calls 3 vendors, otherwise explicit skip, <=150s target timeout600s. New Cloud Run schedules estimated <=$0.55/month; report archive storage at measured and worst-case rates separately.

### Validation and rollout

Reproduce each defect before its fix, run focused contract and I/O-shape tests, perform independent revision-specific review, and run the repository delivery/docs checks. Preserve existing valid rows and record exact CLI/source revision/parameters for production smokes and backfills. Roll out schema before dependent jobs, one bounded group first, then proceed only after the specific output reconciles to AV. Partial or refused groups are reported; they are never described as completed repairs.

## Risks

Vendor revisions may invalidate old-value equality; archive/source failures may prevent a safe repair; missing permissions may block rollout. Tests must reject guesses, preserve durable completed groups and report incomplete results. Parallel changes share only additive schema blocks and integration interfaces; merge them without discarding sibling definitions.
