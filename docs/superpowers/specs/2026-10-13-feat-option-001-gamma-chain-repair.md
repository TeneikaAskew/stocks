---
feat_id: FEAT-OPTION-001
req_ids: [REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-GOV-001]
issues: []
canvases: []
site_source_notes: [OPTIONS-01, OPTIONS-02, OPTIONS-05]
done_when:
  - "Partial-chain collector tests prove calls-only and puts-only success responses fail before persistence, fail the job, and never log request credentials; actual PostgreSQL tests prove skip-existing and resume cursors require both sides."
  - "Gamma summary, grid, analyst and API tests prove partial chains are unavailable; captured complete-chain replays produce valid flips and all 78 next-session feature values per ticker."
  - "Actual PostgreSQL tests prove unavailable dates block older snapshots, atomic snapshot replacement rolls back on insert failure, recovery removes obsolete markers, and repeated bounded backfills converge."
  - "Affected tests pass; normal current-head CODE review, required CI, own catalog/PR records, actual BASE gate and branch-versus-main documentation audit pass without waivers."
status: approved
supersedes: null
---

# Repair partial options chains and gamma propagation

## Decision and problem

The owner authorized implementation and testing, reviewed the concrete local result, and instructed "Fix it" on October13,2026. This contract covers that repair and the ingestion defect established by production logs. It does not replace or widen any approved AV market-data, telemetry, DATA-integrity or CICD contract.

At 2026-10-09 01:01UTC, HISTORICAL_OPTIONS returned only 6580 SPY and 2874 IWM contracts for October8. The collector stored exactly those counts and reported success. The database contains only calls for those two snapshots. Current authenticated production refetches return 13160 SPY and5748 IWM rows with both sides. The original raw responses were not retained; logs establish received/persisted counts, not the upstream vendor's reason for incompleteness.

October9 feature rows use October8 inputs and have0/78 flips per affected ticker. A separate reproduced shift-join defect loses a valid prior snapshot when the current-day snapshot is absent. Local implementation1a7a5f49 passed265 affected tests and a real PostgreSQL replay; these are local evidence, not deployment certification.

## Design

1. Require both call and put contract sides before a success response is normalized/persisted. A one-sided response raises a typed incomplete_chain error; main records failure/nonzero exit. Existing HTTP/no-data handling is preserved except that diagnostic messages cannot contain credential-bearing exception URLs/vendor text. No automatic retries or new API calls.
2. Skip an existing EOD date only when both calls and puts are present. Derive resume watermarks from dates with both sides. This handles incomplete tails; historical gaps behind a later complete watermark require an explicit bounded date repair.
3. Canonical summary/grid return unknown regime, nullable directional totals and explicit warnings for partial chains. Preserve independently available spot. Keep existing sign conventions and BS crossing calculation; a valid chain can legitimately have no crossing.
4. Select the latest strictly prior gamma/VEX snapshot independently of current-day coverage. Preserve NULL values from that selected snapshot. Never use same/future dates or fill past a present unavailable row.
5. Emit a nontradable unavailable date marker keyed to an actual source strike. Replace only successfully computed ticker/date partitions in one transaction, removing stale levels/markers on failure/recovery. Adapt Strat/P7/outcomes/analyst and Levels/Grid/Nodes schemas to preserve unavailability.
6. Package captured fixtures portably with hashes and revised-history timestamps. No production credential is a fixture. Use measured historical rate inputs for operational reconstruction; local fixed-rate controls remain identified as test assumptions.

## Bounded operational recovery and capacity

Initial scope: IWM/SPY EOD October8 and dependent October9 gamma context. Two provider calls;18908 returned records total. Existing tables/jobs are retained. No scheduler, IAM, bucket policy, schema or model-promotion changes. Archive actual refetch bytes/hashes/capture times and an exact pre-write backup; session snapshot markers are not fetch-availability timestamps. New source rows retain current insertion time and derived rows current computation time. Recovery is revised historical data, never a claim that missing puts were available originally.

Compute and test the exact write set before committing it. Validate source hashes, both sides, unique keys, measured rates, expected existing scope and unchanged unrelated rows. Dry-run first with rollback; real PostgreSQL verification must exercise the same bounded transaction. Source plus affected gamma rows and dependent context are updated atomically or remain unchanged; retain rollback evidence. A resumed invocation must converge rather than duplicate. Refuse stale/concurrent unexpected scope, invalid financial inputs or unsupported columns.

Raw JSON at conservative1KiB/record is<19MiB. Double/quadruple copies plus the largest BS vector grid fit within512MiB; measure actual working set in the intended image. Use batch writes, never18908 per-row network round trips. Bound operation to two tickers/one source date/one dependent session; estimate<=60 application round trips at2seconds plus local calculation/serialization60seconds =180seconds, requiring existing task-timeout>=720seconds or reduce the measured path before execution. Existing job retries/schedules remain unchanged. No recurring new spend; bound each one-off execution to the recorded actual resource sizing and task timeout and record its cost estimate before launch.

## Delivery and close-out

The code branch uses this immutable main-approved spec and a separate ready plan. Existing protected files/pins/specs remain untouched. Only after the separately reviewed source-identity verifier is actually on main may declared implementation-source note rows/sidecar be used; spec/policy publication alone grants no allowance. Keep historical SITE marker/frontend/deployment claims unchanged. No source-only bootstrap, audit waiver or unrelated generated-count permission.

Post-merge operational close-out records actual source commit/image digest, narrow job/service deployment, provider receipts, dry-run, committed backfill, downstream tables/API and unchanged-scope comparisons. Never tick a deployment claim from local tests. Keep the original source-provider root cause and historical-as-available limitations explicit. The historical gap is not issue-wide/options/UI remediation completion.
