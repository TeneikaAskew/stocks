---
feat_id: FEAT-DATA-001
req_ids: ["REQ-DATA-001", "REQ-DATA-002", "REQ-DATA-003", "REQ-DATA-004", "REQ-CAP-001", "REQ-CAP-002", "REQ-CAP-003", "REQ-FRESH-001", "REQ-OBS-001"]
issues: [919]
canvases: ["https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN"]
done_when:
  - "pytest tests/gcp/test_fetch_av_indicators.py proves ADOSC mapping, summer/winter UTC conversion, unchanged daily business dates and split-fixture rejection of incompatible price bases."
  - "tests/gcp/test_fetch_av_indicators.py monthly/failure cases pass; its test_as_of_retains_vendor_revision, test_as_of_rejects_configuration_mismatch and isolated-PostgreSQL test_journal_cache_atomic_rollback prove immutable versions, explicit observation clocks and atomic known-field writes."
  - "tests/gcp/test_fetch_av_indicators.py::test_repair_rejects_unverified_rows and ::test_repair_rejects_concurrent_change pass and an isolated-PostgreSQL repair case verifies bounded atomic replacement, journal references and unchanged adjacent windows."
  - "tests/gcp/test_fetch_av_indicators.py::test_cli_incremental_bounded and ::test_main_records_every_terminal_path pass; docs/alpha-vantage-data-fetching.md records the exact incremental/backfill/repair commands, expected outcomes and reproducible capacity/cost calculation; docs/product/02-FEATURE-CATALOG.md FEAT-DATA-001 record has updated Status and Last reviewed and docs/product/12-PR-ISSUE-TRACEABILITY.md records this PR and touched issue 919."
status: approved
supersedes: null
---

# Restore AV indicator contracts, UTC alignment and bounded refresh

## Authorization and intake

This records the scope of the six-stage remediation plan presented after the live AV/GCP audit and authorized by the user on 2026-10-12: "Proceed with the plan, executing inn parallel". Execution method: parallel isolated worktrees, one author and PR per plan. Capability: FEAT-DATA-001, whose catalog row defines "Ingestion, storage, freshness" and owns fetcher jobs, gcp/fetchers/ and gcp/schema.sql. This is the separate AV-indicator ingestion spec/plan, not the broader data-platform remediation spec. Issue #919 is touched because this restores its unfed market_data_indicators table; it is not closed because other unfed tables remain outside this stream. FEAT-IND-001's application indicator stack in lib/indicators.py and lib/signals.py is unchanged.

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

An incremental run covers seven inclusive calendar dates ending yesterday on the Eastern clock: start=end minus six days. --max-months caps the distinct intraday request months before network or persistence begins. Backfill --start-date and --end-date are inclusive, mandatory, and limited to at most three distinct months per invocation; larger scopes fail explicitly and are split into independent rerunnable invocations. A successful empty selection is no_data only when the requested window contains no NYSE sessions; an empty or incomplete response for a window requiring session observations is error. Validate the group before any of its six function writes, retain previously durable complete groups after a later failure, and report partial/error rather than a false success.

### Price basis and corporate actions

The [AV technical-indicator documentation](https://www.alphavantage.co/documentation/#technical-indicators), checked 2026-10-12, states: "All indicators are calculated from adjusted time series data to eliminate artificial price/volume perturbations from historical split and dividend events." Therefore all six functions retain AV's adjusted vendor values in both intervals. Store explicit interval-specific metadata: daily uses price_basis=av_adjusted_daily, corporate_action_policy=vendor_split_dividend_adjusted, interval=daily; 15min uses price_basis=av_adjusted_intraday, corporate_action_policy=vendor_split_dividend_adjusted, interval=15min. Record the vendor's own interval/timezone metadata, the policy/version identifier and the documentation reference alongside the safe request parameters, and include the basis/policy in the configuration hash. These indicator endpoints have no supported adjusted=false switch; do not invent one or substitute locally recomputed indicators. Journal retrieval time identifies which vendor revision was knowable, including later corporate-action revisions.

As-of selection requires the caller's expected interval, configuration hashes and price basis; it rejects incompatible raw, unknown or differently adjusted basis rather than silently joining to the downstream magnitude dataset. Daily raw OHLC fields from TIME_SERIES_DAILY_ADJUSTED do not become adjusted merely because the endpoint also returns adjusted_close. Downstream model promotion remains outside this spec, and no experiment is declared compatible unless its price-basis contract matches. A frozen synthetic two-for-one split fixture includes raw closes 100 before/50 after and vendor-adjusted closes 50/50, plus explicitly labeled synthetic AV-shaped indicator responses. It proves that the supplied values and basis survive ingestion and revision retrieval, and that a raw-price or wrong-interval basis request fails explicitly. The fixture tests compatibility, not local calculation of an AV replacement or a claim of live vendor reconciliation.

### Immutable observation provenance

Add av_indicator_observations with immutable fetch UUID/timestamp identity, ticker, interval, function, known field values, safe parameters, explicit price-basis/vendor metadata, configuration SHA256, aware UTC retrieval/as-of clock, source, pipeline version, code/artifact hash and payload hash. Latest market_data_indicators rows retain a function-to-fetch-reference JSONB map. One SQL statement per bounded chunk atomically appends journal rows and updates only known function fields/reference; retries of the same fetch are immutable and later vendor observations retain previous versions. Verified timestamp replacement journals its observations and references in the existing atomic transaction. A bounded selector requires an explicit aware finite as_of, expected configuration hashes, interval and compatible price basis, selects only observations retrieved by that clock, and never falls back to latest cache history. Its date range is limited to three months per call. Unversioned legacy rows cannot establish past knowledge; today's capture is never backdated to an earlier observation clock.

The configuration hash covers calculation-relevant function/period/series/band parameters, interval and basis/policy version. Request month, selected date window, fetch identity and retrieval time remain captured provenance but are excluded from that hash so unchanged indicator configuration is comparable across monthly requests.

### Run-level observability

Every ingestion invocation records its terminal outcome through gcp.database.record_job_run in a finally path, including startup configuration failure before the first group, vendor/transport/schema failure, partial durable progress, successful nonempty runs, valid no-data windows and refused/concurrently changed repairs. Job name is fetch-av-indicators and variant is the explicit mode. Supply aware UTC started_at, items_total, items_processed, items_failed and rows_written; the helper supplies finished_at and duration_s. A safe structured JSON note contains the Cloud Run execution name or generated local UUID, per-interval/ticker data-date and UTC observation watermarks, request/observation/chunk counts, error class, retry count (zero unless a bounded application retry actually happened) and terminal status. Status is success, no_data, partial or error, consistent with exit 0 only for complete success or validated no_data and exit 1 for partial/error. Never serialize request URLs, credentials or exception objects containing them.

Telemetry-write failure preserves the already determined ingestion exit status and emits a credential-safe structured warning containing the run identity and intended terminal record, matching record_job_run's existing cleanup-path semantics. tests/gcp/test_fetch_av_indicators.py::test_main_records_every_terminal_path parametrizes every listed path and asserts one terminal telemetry call, all required fields and the exact exit classification; a separate telemetry-failure case asserts the warning and unchanged outcome.

### Freshness and cross-stream dependencies

Operational owner is the FEAT-DATA-001 AV-indicator ingestion capability; record its maintainer role as Data platform operations in docs/alpha-vantage-data-fetching.md, with recovery commands and escalation through the existing freshness-watchdog alert path. For SPY, IWM and QQQ, both daily and 15min must reach the expected settled NYSE market date with all nine required vendor fields known: av_adx, av_mfi, av_chaikin_ad_osc, av_aroon_up, av_aroon_down, av_roc, av_bbands_upper, av_bbands_middle and av_bbands_lower. The separately derived bandwidth may legitimately be unavailable for a zero middle band and is not part of these nine vendor-field completeness checks. The measured watermark uses daily ts::date in its documented UTC-midnight convention, and 15min (ts AT TIME ZONE 'America/New_York')::date. Also report retrieval age and latest successful job_runs observation, so stopped invocation is distinguishable from a vendor-date problem.

Settlement is 04:00 America/New_York following a session. At or after 04:00, use the latest NYSE session on or before yesterday's Eastern date; before 04:00, use the latest NYSE session on or before the Eastern date two days earlier. Resolve holidays and half-days with the shared NYSE exchange calendar, not a weekday approximation or a single-year holiday list. Half-days remain sessions. Missing calendar, database or coverage results are unknown and fail the strict check. Missing required fields or a watermark behind the expected settled session is status stale with warning alert severity; lag of at least two NYSE sessions has critical alert severity. Any stale result is strict exit 1 and any unknown result is strict exit 2, consistent with the operations dependency. A current date alone cannot satisfy required-field coverage.

Watchdog code and its calendar/settlement/coverage tests are exclusively owned by docs/superpowers/specs/2026-10-12-feat-ops-001-av-operations.md (FEAT-OPS-001). Its scripts/audit_data_freshness.py AV indicator coverage remains visibly planned/historical while AV_INDICATOR_COVERAGE_ENABLED is false, and becomes active only after the writer's first verified bounded refresh. Job/scheduler creation, image promotion, zero retry configuration and enabling that watchdog flag are exclusively owned by docs/superpowers/specs/2026-10-12-feat-deploy-001-av-deployment.md (FEAT-DEPLOY-001). That dependency wires the explicit incremental CLI at 02:45 America/New_York Tuesday through Saturday and activates monitoring after its smoke evidence. This ingestion PR proves the executable and data contract; it does not claim the feed is operationally restored until both dependency rollout checks pass. It imports no unmerged broader FEAT-DATA-001 implementation.

### File ownership

gcp/fetchers/fetch_av_indicators.py; gcp/schema.sql and gcp/queries/magnitude_engine_schema.sql (indicator journal/cache-reference/price-basis block); tests/gcp/test_fetch_av_indicators.py and related timezone/integration tests; docs/alpha-vantage-data-fetching.md (indicator section); FEAT-DATA-001's owned capability/PR traceability records. Deployment wiring and watchdog implementation remain with their exclusive dependency specs above. Do not modify lib/indicators.py, other capability definitions or the broad data stream's unmerged code.

### Capacity and cost

Three tickers, six functions, daily plus at most two intraday months => at most 54 calls and <=72 bounded function-group write chunks. Estimate <=350 seconds with shared-key conservative pacing and pg8000 round trips; one CPU, 512 MiB and 1,800-second timeout, zero task retries. Peak one ticker/function/month plus ~7,000 daily records, under tens of MiB. Historical depth is sharded <=3 months per invocation, never an unlimited one-task 25-year backfill. Incremental journal upper bound 8,190 rows x ~600 bytes =~4.9 MB/run (~147 MB per 30 daily runs before indexes); retain one round trip per chunk to keep the <=350-second estimate. Historical journal chunks remain bounded; a 63-session three-month/core-three shard is <=73,710 observations x ~600 bytes =~44.2 MB durable journal input, processed one function/month/chunk at a time.

Cloud Run Jobs estimate, excluding free-tier discounts: 350 billed seconds x (1 vCPU x $0.000018/vCPU-second + 0.5 GiB x $0.000002/GiB-second) = $0.00665/run. Tuesday-Saturday cadence is 5/7 runs/day on average: $0.00665/run x (5/7 runs/day) x 30 = $0.1425/month. A conservative daily-run budget is $0.00665 x 1 x 30 = $0.1995/month. This excludes the existing AV subscription: no new per-call vendor charge is assumed within its entitlement; any plan upgrade must be explicitly costed before rollout. Separately budget up to $0.10/month for an additional Cloud Scheduler job outside its free allowance. Cloud SQL is already provisioned, so queries incur no separate per-query bill; journal growth is retained history, approximately 1.8 GB/year before indexes at the conservative daily ceiling, and allocated storage/autogrowth plus index overhead must be measured in rollout evidence rather than represented as zero storage forever. Confirm regional billing rates and measured billed duration in the deployment PR.

### Validation and rollout

Reproduce each defect before its fix, run focused contract and I/O-shape tests, perform independent revision-specific review, and run the repository delivery/docs checks. Preserve existing valid rows and record exact CLI/source revision/parameters for production smokes and backfills. Roll out schema before dependent jobs, one bounded group first, then proceed only after the specific output reconciles to AV. Partial or refused groups are reported; they are never described as completed repairs.

Concrete CLI acceptance uses the production main entrypoint with a deterministic AV transport and isolated PostgreSQL, never a parallel reimplementation: tests/gcp/test_fetch_av_indicators.py::test_cli_incremental_bounded invokes --all --intervals=daily,15min --mode=incremental --lookback-days=7 --max-months=2, asserts at most 54 requests, bounded chunks, correct data dates, six-function observation references, terminal status success and exit 0. A separate failure run asserts partial/error with exit 1 and durable prior completed groups. The runbook at docs/alpha-vantage-data-fetching.md records these exact executable forms:

- python -m gcp.fetchers.fetch_av_indicators --all --intervals=daily,15min --mode=incremental --lookback-days=7 --max-months=2
- python -m gcp.fetchers.fetch_av_indicators --ticker=IWM --intervals=daily,15min --mode=backfill --start-date=2026-05-01 --end-date=2026-05-31 --max-months=1
- python -m gcp.fetchers.fetch_av_indicators --ticker=IWM --intervals=15min --mode=backfill --start-date=2026-05-01 --end-date=2026-05-31 --max-months=1 --repair-legacy-timestamps

The runbook explains required secrets/schema, inclusive date bounds, month sharding, expected success/no_data/partial/error results, safe refusal recovery, and post-run queries for ADOSC non-nullness, exact per-function journal references, revision retention and Eastern market dates. Repair is never the incremental default. pytest tests/gcp/test_fetch_av_indicators.py is the focused contract check; isolated PostgreSQL integration cases must exercise the actual single-statement journal/cache write and rollback before merge. After capability close-out, production restoration evidence belongs to the linked deployment and operations dependency acceptance checks.

## Risks

Vendor revisions may invalidate old-value equality; archive/source failures may prevent a safe repair; missing permissions may block rollout. Tests must reject guesses, preserve durable completed groups and report incomplete results. Parallel changes share only additive schema blocks and integration interfaces; merge them without discarding sibling definitions.
