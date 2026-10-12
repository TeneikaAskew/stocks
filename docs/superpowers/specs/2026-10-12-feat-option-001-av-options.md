---
feat_id: FEAT-OPTION-001
req_ids: ["REQ-DATA-001", "REQ-DATA-002", "REQ-DATA-003", "REQ-DATA-004", "REQ-CAP-001", "REQ-CAP-002", "REQ-CAP-003", "REQ-FRESH-001", "REQ-OBS-001"]
issues: [919]
canvases: []
done_when:
  - "Source-backed gamma diagnosis is documented and regressions distinguish genuine unavailable/no-crossing data from defects."
  - "Point-in-time flow/GEX and earnings prior-session tests cover Monday, holiday, expired-contract and missing-chain cases."
  - "Realtime options tests cover session boundaries, half-days, delayed startup, intended session, duplicate delivery and partial retry without backdating retrieval availability."
  - "Bounded repair CLI and event provenance preserve existing financial rows; FEAT-OPTION-001 record and consumer lifecycle runbooks are updated."
status: approved
supersedes: null
---

# Correct point-in-time options dependencies and closing-session capture

## Authorization and intake

This records the scope of the six-stage remediation plan presented after the live AV/GCP audit and authorized by the user on 2026-10-12: "Proceed with the plan, executing inn parallel". Execution method: parallel isolated worktrees, one author and PR per capability. Capability: FEAT-OPTION-001; matching catalog row in docs/product/02-FEATURE-CATALOG.md. The listed issues are touched, not claimed closed without their own acceptance evidence.

## Problem

IWM/SPY October9 feature gamma_flip is NULL while QQQ is populated; this needs source-backed diagnosis rather than fabricated filling. Flow/GEX stores stopped June4–5, and historical earnings options stopped May14 despite a production materialized-view consumer. Earnings T-1 chain logic uses calendar days, which fails Mondays and holidays.

## Non-goals

No expansion to all 128 APIs, change to strategy/model promotion or risk calibration, fabricated financial values, blind rewrite of historical timestamps, unrelated IAM/audience changes, or unbounded backfill. API failures and historical-only exclusions remain explicit.

## Approaches considered

1. Targeted contract repair, independent reviewed streams, bounded source-backed repair and selective deployment — chosen to preserve the verified working paths.
2. Replace the complete ingestion platform — excessive scope and operational risk.
3. Change schedules without repairing data contracts — leaves the demonstrated corruption and observability gaps.

## Design

Trace gamma missingness through prior-session chain, actual crossing, rates and builder joins. Preserve legitimate no-crossing NULLs with explicit availability semantics; repair only a demonstrated parser/join/computation defect and coordinate its freshness expectation. Correct required flow/GEX builders to filter minute interval, valid unexpired contracts and exact prior trading session with explicit gap handling; refresh only bounded consumer-required slices and classify historical-only stores without unnecessary new recurring jobs. Use existing shared exchange calendar for earnings T-1 snapshots. Add event_reported_date provenance to new earnings-chain rows and update earnings_event_outcomes joins to the exact event/session mapping, preserving existing verified legacy coverage. Add bounded --since/--limit recent-event backfill and safe completeness checks. Add shared-calendar realtime RTH guard. Closing captures use deterministic capture_slot_ts=actual NYSE session close plus a unique slot/contract key; snapshot_ts remains the actual retrieval/availability clock. Completed slots skip duplicates; partial slots can recover without overwriting the first known contract value. --closing-only accepts an intended --session-date and a bounded close<=retrieval<close+30minutes recovery window, including early closes. Earlier non-closing launches explicitly skip; a missed required capture after cutoff is unavailable/incomplete, not a successful capture. Tests cover duplicate delivery, partial retry and delayed startup. Source completeness also rejects one-sided core ETF EOD chains and only skips verified complete snapshots; derive requested dates from completed Eastern sessions, not UTC date.today.

### File ownership

gcp/fetchers/fetch_av_realtime_options.py; fetch_av_earnings_options_backfill.py; fetch_av_historical_options.py (gamma-source completeness and session bounds); required flow/GEX/gamma builders; gcp/schema.sql (options event provenance/view block only); related tests/runbooks. Deployment wiring belongs to FEAT-DEPLOY-001.

### Capacity and cost

All repairs are bounded ticker/session or recent-event slices, default <=30 sessions/core ticker and explicit event limit; reuse batched chains/rates/minute reads, never per bar DB/AV reads. Closing snapshot3calls and <=42kcontracts (~<30 MB working data), grouped batch upserts, target <150s and timeout600s. Do not run the entire ~41,756-event multi-year earnings backfill in one repair task; estimate and shard before execution. No new recurring research workload unless active consumer requirement is demonstrated.

### Validation and rollout

Reproduce each defect before its fix, run focused contract and I/O-shape tests, perform independent revision-specific review, and run the repository delivery/docs checks. Preserve existing valid rows and record exact CLI/source revision/parameters for production smokes and backfills. Roll out schema before dependent jobs, one bounded group first, then proceed only after the specific output reconciles to AV. Partial or refused groups are reported; they are never described as completed repairs.

## Issue intake and artifact disposition

Issue #919 remains open and is touched for earnings snapshots and research flow/GEX only; indicators, cross-asset, correlation and gamma-events are separate capabilities. Its merged candidate PR #1097 is a documentation reverification, not an implementation recovery. The existing manual research builders are recovered as explicitly bounded on-demand paths with source/session guards; no new recurring workload is implied. Affected historical research artifacts remain UNKNOWN until mapped or regenerated, and no old result is promoted as valid by this repair.

## Risks

Vendor revisions may invalidate old-value equality; archive/source failures may prevent a safe repair; missing permissions may block rollout. Tests must reject guesses, preserve durable completed groups and report incomplete results. Parallel changes share only additive schema blocks and integration interfaces; merge them without discarding sibling definitions.
