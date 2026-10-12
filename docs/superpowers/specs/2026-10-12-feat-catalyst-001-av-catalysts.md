---
feat_id: FEAT-CATALYST-001
req_ids: ["REQ-DATA-001", "REQ-DATA-002", "REQ-DATA-003", "REQ-DATA-004", "REQ-CAP-001", "REQ-CAP-002", "REQ-CAP-003", "REQ-OBS-001", "REQ-SECRET-001"]
issues: []
canvases: []
done_when:
  - "Earnings tests prove delayed actuals and vendor revisions are selected, updated and bounded with one eligibility query."
  - "Feed tests distinguish valid empty from failures, persist successful groups durably, and return nonzero for incomplete executions."
  - "Raw provenance tests prove exact payload capture, safe parameters/logs, dry-run isolation and archive-failure handling."
  - "Earnings-estimate contracts and the preserved weekly calendar subset pass regression tests; rollout/runbook and FEAT-CATALYST-001 record are updated."
status: approved
supersedes: null
---

# Reconcile AV earnings revisions and make catalyst ingestion reproducible

## Authorization and intake

This records the scope of the six-stage remediation plan presented after the live AV/GCP audit and authorized by the user on 2026-10-12: "Proceed with the plan, executing inn parallel". Execution method: parallel isolated worktrees, one author and PR per capability. Capability: FEAT-CATALYST-001; matching catalog row in docs/product/02-FEATURE-CATALOG.md. The listed issues are touched, not claimed closed without their own acceptance evidence.

## Problem

AAPL June-quarter actual EPS is NULL in Cloud SQL but 2.02 in AV; older quarter values also changed. Existing history is permanently skipped outside the current reporting window. News article sets and scores differ from current AV responses, and failures/empty responses can report success. Exception logging may print API keys.

## Non-goals

No expansion to all 128 APIs, change to strategy/model promotion or risk calibration, fabricated financial values, blind rewrite of historical timestamps, unrelated IAM/audience changes, or unbounded backfill. API failures and historical-only exclusions remain explicit.

## Approaches considered

1. Targeted contract repair, independent reviewed streams, bounded source-backed repair and selective deployment — chosen to preserve the verified working paths.
2. Replace the complete ingestion platform — excessive scope and operational risk.
3. Change schedules without repairing data contracts — leaves the demonstrated corruption and observability gaps.

## Design

Introduce strict safe AV request/outcome handling for earnings, news and insider feeds: legitimate validated empty differs from transport, throttle, vendor or malformed failure. Persist per ticker before advancing, classify partial/empty/failure truthfully in existing job_runs, and fail incomplete executions without losing completed groups. Refresh recently reported incomplete quarters on a daily lookback and reconcile at most 100 oldest/revised tickers weekly using one batched eligibility query and explicit fetched-at clocks. Preserve --force. Archive exact mutable NEWS_SENTIMENT and EARNINGS payloads and the complete three-month EARNINGS_CALENDAR response as immutable gzip GCS objects with safe parameters, UTC retrieval time, URI and SHA256; archive failure must not claim provenance-complete persistence. Preserve the verified weekly calendar trading subset and source dates. Add bounded EARNINGS_ESTIMATES ingestion based on the tested estimates array, keyed by ticker/date/horizon, retaining raw fields and provenance. Add only additive schema columns/table in the catalyst-owned block. Never log credential-bearing params or request URLs. Retain raw archives for 90 days under a dedicated prefix.

### File ownership

gcp/fetchers/_av_ingestion.py; fetch_earnings_history.py; fetch_news_sentiment.py; fetch_insider_transactions.py; fetch_av_earnings_estimates.py; scripts/fetch_earnings_calendar.py; gcp/schema.sql (catalyst provenance/estimates block); corresponding tests and runbooks

### Capacity and cost

Weekly revision <=100 tickers, one eligibility read plus one request/archive/upsert per ticker, ~270 seconds, 1,800 seconds minimum timeout. Insider <=300 tickers, one response/ticker and per-group chunks, <=810 seconds estimate with 3,600-second timeout. News response cap 1,000 articles and one request response in memory (<~2 MB raw plus ticker expansion); saturation is partial unless window splitting proves completion. Existing news jobs use bounded scopes, 3,600-second timeout and zero retries. Worst-case archive ceiling ~1.3 GB/day at all configured caps (~117 GB/90 days); report actual measured workload separately. Estimates <=100 tickers/~4,100 records (~3 MB), ~270 seconds, 1,800-second timeout, ~$0.15/month scheduled Cloud Run.

### Validation and rollout

Reproduce each defect before its fix, run focused contract and I/O-shape tests, perform independent revision-specific review, and run the repository delivery/docs checks. Preserve existing valid rows and record exact CLI/source revision/parameters for production smokes and backfills. Roll out schema before dependent jobs, one bounded group first, then proceed only after the specific output reconciles to AV. Partial or refused groups are reported; they are never described as completed repairs.

## Risks

Vendor revisions may invalidate old-value equality; archive/source failures may prevent a safe repair; missing permissions may block rollout. Tests must reject guesses, preserve durable completed groups and report incomplete results. Parallel changes share only additive schema blocks and integration interfaces; merge them without discarding sibling definitions.
