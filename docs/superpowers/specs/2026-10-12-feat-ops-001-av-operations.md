---
feat_id: FEAT-OPS-001
req_ids: ["REQ-DATA-001", "REQ-FRESH-001", "REQ-FRESH-002", "REQ-OBS-001", "REQ-CAP-001", "REQ-CAP-002"]
issues: [922]
canvases: ["https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN"]
done_when:
  - "Infrastructure auditor regressions prove failed checks cannot be reported as a complete successful audit."
  - "Strict freshness regressions prove unknown, empty and database-error results fail without changing display compatibility."
  - "Batched AV adjusted-close and indicator coverage checks report missing fields/sessions with bounded query counts."
  - "Operations runbooks and the FEAT-OPS-001 record distinguish active, incomplete and historical-only data."
status: approved
supersedes: null
---

# Make AV audit completeness and field coverage observable

## Authorization and intake

This records the scope of the six-stage remediation plan presented after the live AV/GCP audit and authorized by the user on 2026-10-12: "Proceed with the plan, executing inn parallel". Execution method: parallel isolated worktrees, one author and PR per capability. Capability: FEAT-OPS-001; matching catalog row in docs/product/02-FEATURE-CATALOG.md. The listed issues are touched, not claimed closed without their own acceptance evidence.

## Problem

audit-infra-drift cannot list scheduler jobs but exits zero and reports no findings. Strict freshness can pass unknown check results, and several reads swallow database errors. Required adjusted-close/AV-indicator fields have no complete coverage check.

## Non-goals

No expansion to all 128 APIs, change to strategy/model promotion or risk calibration, fabricated financial values, blind rewrite of historical timestamps, unrelated IAM/audience changes, or unbounded backfill. API failures and historical-only exclusions remain explicit.

## Approaches considered

1. Targeted contract repair, independent reviewed streams, bounded source-backed repair and selective deployment — chosen to preserve the verified working paths.
2. Replace the complete ingestion platform — excessive scope and operational risk.
3. Change schedules without repairing data contracts — leaves the demonstrated corruption and observability gaps.

## Design

Report infrastructure audit check errors as incomplete and exit nonzero, distinct from ordinary drift findings. Use strict bounded SQL in freshness paths so database failures surface as unknown rather than empty/stale/pass. Strict freshness fails whenever any unknown result or an empty report exists, even when aggregate display status is warn/stale. Add batched settled-session coverage for AV-source adjusted_close across the broad universe and required AV indicator fields for SPY/IWM/QQQ daily/15min. Use existing shared session/freshness primitives, respect genuinely historical-only datasets, and coordinate gamma no-crossing semantics with the options stream. Indicator coverage activates only through AV_INDICATOR_COVERAGE_ENABLED (default false); before the scheduled writer is configured and its first bounded refresh verified, emit a visible planned/historical skipped check. Settle at 04:00 Eastern and check the previous completed Eastern market date, using daily UTC-midnight keys and DST-aware Eastern intraday bounds. Adjusted-close coverage is already active and always checked. No new overlapping UI freshness implementation.

### File ownership

gcp/audit_infra_drift.py; scripts/audit_data_freshness.py; relevant tests; existing operations runbooks. IAM/deployment belongs to FEAT-DEPLOY-001; feed telemetry belongs to FEAT-CATALYST-001.

### Capacity and cost

At most three extra grouped SQL coverage queries per watchdog run, bounded by a settled date and configured core tickers, aggregate result <=~0.26 MB for 2,600 symbols. Expected extra 1.5–6 seconds plus bounded scan time; maintain explicit query timeout. No new API calls or job schedules; incremental runtime estimate <=$0.06/month.

### Validation and rollout

Reproduce each defect before its fix, run focused contract and I/O-shape tests, perform independent revision-specific review, and run the repository delivery/docs checks. Preserve existing valid rows and record exact CLI/source revision/parameters for production smokes and backfills. Roll out schema before dependent jobs, one bounded group first, then proceed only after the specific output reconciles to AV. Partial or refused groups are reported; they are never described as completed repairs.

## Risks

Vendor revisions may invalidate old-value equality; archive/source failures may prevent a safe repair; missing permissions may block rollout. Tests must reject guesses, preserve durable completed groups and report incomplete results. Parallel changes share only additive schema blocks and integration interfaces; merge them without discarding sibling definitions.
