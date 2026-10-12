---
feat_id: FEAT-DATA-001
req_ids: ["REQ-DATA-001", "REQ-DATA-003", "REQ-DATA-004", "REQ-CAP-001", "REQ-CAP-002", "REQ-CAP-003", "REQ-FRESH-001", "REQ-OBS-001"]
issues: [913]
canvases: ["https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN"]
done_when:
  - "Daily adjusted-close repair and batched I/O tests pass; split/dividend fixtures prove adjusted daily OHLC and continuous metrics, raw execution values, restored price units, unavailable-factor rejection and unchanged intraday parity."
  - "Native indices retain canonical aliases, AV provenance and NULL volume; reference parsers retain the tested AV contracts."
  - "The endpoint registry accounts for all 128 distinct AV functions and validates its table keys and lifecycle classification."
  - "A bounded dry-run/production smoke report and updated FEAT-DATA-001 record document rollout and unresolved source exceptions."
status: approved
supersedes: null
---

# Preserve AV daily adjustments and ingest selected reference endpoints

## Authorization and intake

This records the scope of the six-stage remediation plan presented after the live AV/GCP audit and authorized by the user on 2026-10-12: "Proceed with the plan, executing inn parallel". Execution method: parallel isolated worktrees, one author and PR per capability. Capability: FEAT-DATA-001; matching catalog row in docs/product/02-FEATURE-CATALOG.md. The listed issues are touched, not claimed closed without their own acceptance evidence.

## Problem

The production audit found 12,628 of 12,930 AV daily rows for October 5–9 without adjusted_close. The broad daily parser requests TIME_SERIES_DAILY_ADJUSTED but drops its adjusted close. INDEX_DATA and INDEX_CATALOG work with the production key, while no native index ingestion exists. Selected metadata endpoints have no ingestion contract.

## Non-goals

No expansion to all 128 APIs, change to strategy/model promotion or risk calibration, fabricated financial values, blind rewrite of historical timestamps, unrelated IAM/audience changes, or unbounded backfill. API failures and historical-only exclusions remain explicit.

## Approaches considered

1. Targeted contract repair, independent reviewed streams, bounded source-backed repair and selective deployment — chosen to preserve the verified working paths.
2. Replace the complete ingestion platform — excessive scope and operational risk.
3. Change schedules without repairing data contracts — leaves the demonstrated corruption and observability gaps.

## Design

Preserve adjusted_close in every AV daily writer. Add a bounded explicit-ticker/date repair that updates existing rows only, defaults to a reviewable dry-run, and commits per ticker with idempotent batch SQL. Add native SPX and VIX daily index routing preserving the existing ^VIX stored alias, raw OHLC and absent volume as NULL; retain explicit AV index provenance and reject silent Yahoo fallback. Add bounded INDEX_CATALOG, INDEX_DATA, ETF_PROFILE, DIVIDENDS, SPLITS and LISTING_STATUS ingestion using actual vendor contracts. Store normalized reference records and safe request/raw response/fetched UTC/SHA256 provenance in an additive SQL journal; limit journal retention to 90 days. Produce a 128-function registry with parameters, entitlement, symbol scope, timezone, table/key, cadence, owner, retained fields and excluded/historical-only reasons. Planned endpoint status is not called active until deployment evidence exists. Broad daily backfill and repair publish complete/partial/error counts and fail nonzero for failed requested groups. Registry format is version 1 with a functions mapping; lifecycle is one of active, planned, on_demand, historical_only or excluded, and keys are validated against declared table contracts. No imports from an unmerged sibling branch.

### Raw versus adjusted consumer policy

Store canonical OHLCV as traded for session levels, strikes, execution and daily STRAT structures. Continuous daily returns and price indicators use all OHLC scaled consistently by adjusted_close/close; never replace only Close. Preserve raw volume. A shared price-basis helper rejects absent/nonfinite/nonpositive factors. Persist price-dimensional EMA/SMA/ATR/MACD/Bollinger outputs back in the raw current-row price units; dimensionless metrics retain their values. The daily loader exposes an explicit adjusted mode and consistently rescales price-dimensional enrichment columns, with raw remaining the execution/levels default. Generic intraday behavior and golden parity are unchanged. Revised current adjusted history is not claimed point-in-time safe; historical artifact revalidation remains required. Issue #913 is touched, not claimed closed for its broader replay/corporate-action accounting scope.

### File ownership

gcp/fetchers/fetch_market_data.py; scripts/deep_backfill_ticker.py; lib/price_basis.py; lib/data_loader.py; gcp/fetchers/backfill_daily_indicators.py; gcp/fetchers/fetch_av_reference_data.py; gcp/schema.sql (market/reference block only); config/alphavantage_endpoints.json; related tests; existing AV runbooks

### Capacity and cost

Daily repair: cap 50 tickers/window, one AV request per ticker, one bounded existing-row read and batch update per ticker; compact 100-bar window is at most 5,000 rows (~0.8 MB), about 200 seconds. Full-history repair remains per ticker, chunks at most 5,000 SQL rows and explicitly estimates the selected window before execute. Index input: SPX ~7,450 and VIX ~9,287 historical rows (~2.35 MB raw total); one response at a time, incremental dates bounded. Weekly reference default is SPY/IWM/QQQ plus one catalog/listing call, ~10 calls and <=20,000 listing rows. No per-row requests or SQL. Runtime caps must be at least 4x measured/estimated group time; new reference schedules estimated <=$0.18/month Cloud Run excluding storage/API subscription.

### Validation and rollout

Reproduce each defect before its fix, run focused contract and I/O-shape tests, perform independent revision-specific review, and run the repository delivery/docs checks. Preserve existing valid rows and record exact CLI/source revision/parameters for production smokes and backfills. Roll out schema before dependent jobs, one bounded group first, then proceed only after the specific output reconciles to AV. Partial or refused groups are reported; they are never described as completed repairs.

## Risks

Vendor revisions may invalidate old-value equality; archive/source failures may prevent a safe repair; missing permissions may block rollout. Tests must reject guesses, preserve durable completed groups and report incomplete results. Parallel changes share only additive schema blocks and integration interfaces; merge them without discarding sibling definitions.
