---
feat_id: FEAT-IND-001
req_ids: ["REQ-DATA-001", "REQ-DATA-003", "REQ-DATA-004", "REQ-CAP-001", "REQ-CAP-002", "REQ-CAP-003", "REQ-FRESH-001", "REQ-OBS-001"]
issues: []
canvases: []
done_when:
  - "Indicator regressions cover ADOSC mapping, summer/winter UTC conversion and unchanged daily business dates."
  - "Bounded monthly and failure tests prove known values are preserved; provenance/as-of tests retain vendor revisions, isolate configuration hashes and roll back journal/cache writes together."
  - "Legacy repair tests reject unverified or concurrently changed source rows and use atomic bounded replacement."
  - "The incremental CLI, capacity estimate, repair runbook and FEAT-IND-001 record are documented and exercised."
status: approved
supersedes: null
---

# Restore AV indicator contracts, UTC alignment and bounded refresh

## Authorization and intake

This records the scope of the six-stage remediation plan presented after the live AV/GCP audit and authorized by the user on 2026-10-12: "Proceed with the plan, executing inn parallel". Execution method: parallel isolated worktrees, one author and PR per capability. Capability: FEAT-IND-001; matching catalog row in docs/product/02-FEATURE-CATALOG.md. The listed issues are touched, not claimed closed without their own acceptance evidence.

## Problem

ADOSC is entirely NULL because the parser expects Chaikin A/D instead of ADOSC. Intraday Eastern timestamps are labeled UTC. The stored daily and 15-minute history stops May 27 and May 26; the fetcher is unscheduled and lacks per-month history.

## Non-goals

No expansion to all 128 APIs, change to strategy/model promotion or risk calibration, fabricated financial values, blind rewrite of historical timestamps, unrelated IAM/audience changes, or unbounded backfill. API failures and historical-only exclusions remain explicit.

## Approaches considered

1. Targeted contract repair, independent reviewed streams, bounded source-backed repair and selective deployment — chosen to preserve the verified working paths.
2. Replace the complete ingestion platform — excessive scope and operational risk.
3. Change schedules without repairing data contracts — leaves the demonstrated corruption and observability gaps.

## Design

Fetch ADX, MFI, ADOSC, AROON, ROC and BBANDS using exact response keys and strict complete-group validation. Keep daily date keys at midnight UTC, convert intraday Eastern wall stamps with the shared DST-aware helper. Add bounded incremental and date/month backfill modes with explicit max-months, conservative pacing, per-group telemetry and nonzero incomplete exit. Persist only known per-function values to prevent warmup or partial-response NULL overwrites. Legacy timestamp replacement is an explicit repair mode: verify non-ADOSC existing values against newly fetched monthly vendor data, verify unchanged source rows in the transaction, and reuse the existing bounded atomic replacement utility. Refuse revised/unverifiable histories rather than delete guesses. Scheduled interface: --all --intervals=daily,15min --mode=incremental --lookback-days=7 --max-months=2.

### Immutable observation provenance

Add av_indicator_observations with immutable fetch UUID/timestamp identity, ticker, interval, function, known field values, safe parameters, configuration SHA256, aware UTC retrieval/as-of clock, source, pipeline version, code/artifact hash and payload hash. Latest market_data_indicators rows retain a function-to-fetch-reference JSONB map. One SQL statement per bounded chunk atomically appends journal rows and updates only known function fields/reference; retries of the same fetch are immutable and later vendor observations retain previous versions. Verified timestamp replacement journals its observations and references in the existing atomic transaction. A bounded selector requires an explicit aware as_of and expected configuration hashes, selects only observations retrieved by that clock, and never falls back to latest cache history. Unversioned legacy rows cannot establish past knowledge.

### File ownership

gcp/fetchers/fetch_av_indicators.py; gcp/schema.sql and gcp/queries/magnitude_engine_schema.sql (indicator journal/cache-reference block); tests/gcp/test_fetch_av_indicators.py and related timezone/integration tests; existing AV runbooks. Deployment wiring belongs to FEAT-DEPLOY-001.

### Capacity and cost

Three tickers, six functions, daily plus at most two intraday months => at most 54 calls and <=72 bounded function-group write chunks. Estimate <=350 seconds with shared-key conservative pacing and pg8000 round trips; one CPU, 512 MiB and 1,800-second timeout, zero task retries. Peak one ticker/function/month plus ~7,000 daily records, under tens of MiB. Historical depth is sharded <=3 months per invocation, never an unlimited one-task 25-year backfill. New daily Cloud Run schedule estimated ~$0.15/month. Incremental journal upper bound 8,190 rows x ~600 bytes =~4.9 MB/run (~147 MB/month before indexes); retain one round trip per chunk to keep the <=350-second estimate. Historical journal chunks remain bounded.

### Validation and rollout

Reproduce each defect before its fix, run focused contract and I/O-shape tests, perform independent revision-specific review, and run the repository delivery/docs checks. Preserve existing valid rows and record exact CLI/source revision/parameters for production smokes and backfills. Roll out schema before dependent jobs, one bounded group first, then proceed only after the specific output reconciles to AV. Partial or refused groups are reported; they are never described as completed repairs.

## Risks

Vendor revisions may invalidate old-value equality; archive/source failures may prevent a safe repair; missing permissions may block rollout. Tests must reject guesses, preserve durable completed groups and report incomplete results. Parallel changes share only additive schema blocks and integration interfaces; merge them without discarding sibling definitions.
