---
feat_id: FEAT-OPTION-001
req_ids: ["REQ-DATA-001", "REQ-DATA-002", "REQ-DATA-003", "REQ-DATA-004", "REQ-CAP-001", "REQ-CAP-002", "REQ-CAP-003", "REQ-FRESH-001", "REQ-OBS-001"]
issues: [919]
canvases: []
done_when:
  - "tests/gcp/test_av_options_source_contracts.py proves two-sided complete publication and genuine missing/no-crossing gamma semantics; docs/runbooks/av-options-remediation.md records the Oct8 SPY/IWM source-backed diagnosis."
  - "tests/gcp/test_av_options_session_contracts.py proves shared NYSE Monday/holiday/half-day selection, raw spot/strike split parity, expired-contract filtering, exact prior-chain gaps and unchanged verified legacy event coverage."
  - "tests/gcp/test_av_options_closing_contracts.py proves delayed/duplicate closing delivery, atomic whole-ticker rollback/retry, actual availability clocks and a MAX(snapshot_ts) reader returning a complete chain; local PostgreSQL verifies the online partial-index conflict key."
  - "tests/gcp/test_av_options_observability.py verifies all terminal run records and derived provenance; docs/runbooks/av-options-remediation.md contains bounded repair, index rollout and exact DEPLOY/OPS prerequisite verification commands."
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

Trace gamma missingness through prior-session chain, actual crossing, rates and builder joins. Preserve legitimate no-crossing NULLs with explicit availability semantics; repair only a demonstrated parser/join/computation defect and coordinate its freshness expectation. Correct required flow/GEX builders to filter minute interval, valid unexpired contracts and exact prior trading session with explicit gap handling; refresh only bounded consumer-required slices and classify historical-only stores without unnecessary new recurring jobs. Use existing shared exchange calendar for earnings T-1 snapshots. Add event_reported_date provenance to new earnings-chain rows and update earnings_event_outcomes joins to the exact event/session mapping, preserving existing verified legacy coverage. Add bounded --since/--limit recent-event backfill and safe completeness checks. Add shared-calendar realtime RTH guard. Closing captures use deterministic capture_slot_ts=actual NYSE session close plus a unique slot/contract key; snapshot_ts remains the actual retrieval/availability clock. Publish a complete validated ticker chain and its slot-completion marker atomically in one database transaction across bounded chunks; on failure roll back that entire ticker chain. Partial recovery is across whole tickers, not mixed contract retrieval timestamps within one ticker. Completed ticker slots skip duplicate delivery; unfinished tickers can retry and publish a full chain at one actual retrieval timestamp. Existing MAX(snapshot_ts) readers must see the whole completed chain after recovery. Apply equivalent complete-chain publication to ordinary realtime ingestion where needed to prevent a partial latest snapshot. --closing-only accepts an intended --session-date and a bounded close<=retrieval<close+30minutes recovery window, including early closes. Earlier non-closing launches explicitly skip; a missed required capture after cutoff is unavailable/incomplete, not a successful capture. Tests cover duplicate delivery, partial retry and delayed startup. Source completeness also rejects one-sided core ETF EOD chains and only skips verified complete snapshots; derive requested dates from completed Eastern sessions, not UTC date.today.


### Explicit dependencies and storage safety

All affected earnings-date selection, historical fetch bounds, realtime RTH/closing guards and builders use the fail-closed `gcp.fetchers.evaluate_ew_strikes.nyse_sessions` NYSE schedule primitive. A missing calendar dependency or invalid schedule is an error; remove the historical-options weekday fallback. Tests cover 2026-11-27 early close, a 2027 holiday and DST. No second holiday list is introduced.

Option strikes and spot inputs must share as-traded, unadjusted units at the source session. Daily spot is canonical raw OHLC. Current intraday AV ingestion may have requested adjusted data: do not label those historical rows raw or repair GEX across an unverified split. The DATA market-data spec owns explicit `adjusted=false` intraday requests, raw-basis provenance and a bounded source-verified repair; this stream rejects unknown/mismatched basis at corporate-action boundaries and records unavailable output until source parity is verified. A split-date fixture proves equal spot/strike units and forbids double adjustment. A basis requirement is enforced by builder input validation, not assumed from column names.

On the large `etf_options_snapshots` table, add only a nullable closing-slot column in transactional schema. Build the slot/contract unique index outside `apply_schema.py` using `CREATE UNIQUE INDEX CONCURRENTLY ... WHERE capture_slot_ts IS NOT NULL`, after a read-only duplicate preflight; do not add a full-table ordinary UNIQUE constraint. Match the partial-index predicate in `ON CONFLICT`. The deployment runbook verifies index validity before enabling closing captures and specifies a lock timeout, failure recovery and rollback. Unit and local PostgreSQL tests prove duplicate-slot convergence; production rollout must record index duration and never claim a concurrent index ran inside the transactional schema command.

New earnings snapshots carry explicit event_reported_date. Existing legacy rows remain visible through the exact existing NULL-only `snapshot_date+1` view fallback while a bounded migration verifies each mapping against reported earnings date and the shared prior-session calendar. An ambiguous legacy mapping remains unknown; it is not rewritten by guess. The selector does not skip a group merely because legacy rows exist. A before/after event-count and ATM-value regression proves no loss of previously verified coverage and validates Monday/holiday corrected groups.

Derived flow/GEX tables retain source snapshot/session/as-of, pipeline identifier/version, safe configuration hash, rule/model identifier (explicit not-applicable where no model), source artifact/hash and code revision. These fields are additive; old rows have unknown provenance until bounded regeneration. Each entry-point invocation emits durable `record_job_run` run identity, input/output counts, watermark, duration, error class, retry count and terminal complete/partial/empty/skipped/failed status. A failure before the first group is recorded; telemetry delivery failures are explicit nonzero, with structured local logs preserving failure evidence.

The closing schedule is a deployment prerequisite in `docs/superpowers/specs/2026-10-12-feat-deploy-001-av-deployment.md`: a dedicated `--closing-only` job invoked at 13:00–16:00 hourly America/New_York, guarded by actual NYSE close, with 600-second timeout and zero retries. This stream's code can merge before deployment, but closing production completion requires the deployed scheduler verifier and a complete slot smoke. Served earnings-options freshness is owned by the OPS spec: a batched expected-event/prior-session completeness check, data owner TeneikaAskew/project owner, alert on missing eligible events after the settled producer window, existing freshness alert delivery, and bounded repair instructions. On-demand research flow/GEX stays historical-only, with no unsupported daily-age promise. Dependency checks must be satisfied before reporting overall plan completion.

### File ownership

gcp/fetchers/fetch_av_realtime_options.py; gcp/fetchers/fetch_av_earnings_options_backfill.py; gcp/fetchers/fetch_av_historical_options.py (gamma-source completeness and session bounds); required flow/GEX/gamma builders; gcp/schema.sql (options event provenance/view and derived-provenance blocks); gcp/migrations/av_closing_slot_index.sql (online nontransactional migration); related tests/runbooks. Deployment wiring belongs to FEAT-DEPLOY-001.

### Capacity and cost

All repairs are bounded ticker/session or recent-event slices, default <=30 sessions/core ticker and explicit event limit; reuse batched chains/rates/minute reads, never per bar DB/AV reads. Closing snapshot3calls and <=42kcontracts (~<30 MB working data), grouped batch upserts, target <150s and timeout600s. Do not run the entire ~41,756-event multi-year earnings backfill in one repair task; estimate and shard before execution. No new recurring research workload unless active consumer requirement is demonstrated. Closing workload compute at 1 vCPU/0.5 GiB and 150 seconds uses $0.000018/vCPU-second plus $0.000002/GiB-second: about $0.00285/run × 5/7 runs/day × 30 = $0.061/month, excluding free tier, vendor subscription, build and storage. Guard-only hourly launches add measured startup cost, reported separately; zero automatic retries. Online concurrent index migration performs two retained-table scans and waits for existing transactions; it creates entries only for non-null closing slots, and is separately timed and monitored rather than hidden in the 150-second capture estimate.

### Validation and rollout

Reproduce each defect before its fix, run focused contract and I/O-shape tests, perform independent revision-specific review, and run the repository delivery/docs checks. Preserve existing valid rows and record exact CLI/source revision/parameters for production smokes and backfills. Roll out schema before dependent jobs, one bounded group first, then proceed only after the specific output reconciles to AV. Partial or refused groups are reported; they are never described as completed repairs.

## Issue intake and artifact disposition

Issue #919 remains open and is touched for earnings snapshots and research flow/GEX only; indicators, cross-asset, correlation and gamma-events are separate capabilities. Its merged candidate PR #1097 is a documentation reverification, not an implementation recovery. The existing manual research builders are recovered as explicitly bounded on-demand paths with source/session guards; no new recurring workload is implied. Affected historical research artifacts remain UNKNOWN until mapped or regenerated, and no old result is promoted as valid by this repair.

## Risks

Vendor revisions may invalidate old-value equality; archive/source failures may prevent a safe repair; missing permissions may block rollout. Tests must reject guesses, preserve durable completed groups and report incomplete results. Parallel changes share only additive schema blocks and integration interfaces; merge them without discarding sibling definitions.
