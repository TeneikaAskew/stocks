---
feat_id: FEAT-DEPLOY-001
req_ids: [REQ-GOV-002, REQ-DEPLOY-001, REQ-CAP-001, REQ-CAP-002, REQ-CAP-003, REQ-OBS-001, REQ-FRESH-001]
issues: [1365]
canvases:
  - https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN
done_when:
  - "P1: tests/gcp/test_data_refresh_deploy.py proves create/update convergence for the sequence and due-macro jobs, exact runtime commands, service identity, image, secrets references, resource budgets and max-retries 0"
  - "P2: tests/gcp/test_data_refresh_deploy.py proves av-options-daily targets the completion-gated sequence, direct gamma-levels-daily and strat-engine-daily offsets stay disabled across repeated deploys, unrelated schedules are preserved and every target resolves"
  - "P3: tests/gcp/test_data_refresh_deploy.py proves the due-macro dispatcher runs at */15 8-17 * * 1-5 America/New_York after release while economic-events-daily retains schedule collection, with bounded runtime arguments and no added unbounded historical scan"
  - "P4: tests/integration/test_refresh_deployment_acceptance.py runs commands emitted by the actual deploy script against isolated SQL and a recording control-plane transport, proving exact upstream execution/receipt gating, failed-upstream suppression, overlap locking and bounded postrelease refresh"
  - "P5: docs/validation/2026-10-12-feat-deploy-001-data-refresh-evidence.md records rendered configuration, create/update dry-run results, measured driver/query/runtime/resource budgets and filled volume, velocity, wall-clock and monthly-cost estimates"
  - "P6: docs/runbooks/data-refresh-deployment.md records reversible rollout, disabled-offset inventory, exact production operational-proof queries and pending verification ledger; FEAT-DEPLOY-001 catalog and traceability record this PR and distinguish premerge isolated proof from postmerge production activation"
status: approved
supersedes: null
---

# Deploy completion-gated data refresh and bounded postrelease actuals

## Approval and scheduling prerequisite

The user approved the [GCP repair review](https://chatgpt.com/space/page_531ea2540b4c8191a4e5267eb24f1b89) and on 2026-10-12 requested, “Execute the plan with test driven development.” This is a capability-ownership split of the approved completion-gated refresh and after-release actuals repair, not additional product scope. FEAT-DEPLOY-001 owns deploy scripts/configuration; the companion FEAT-DATA-001 owns runtime financial/source logic.

The [canonical six-issue candidate inventory](https://github.com/TeneikaAskew/stocks/blob/main/docs/product/12-PR-ISSUE-TRACEABILITY.md#gcp-repair-scheduling-pass-2026-10-12) must publish from its separate docs branch before this approved-scope specification is accepted/published or implementation is scheduled. Record its merged revision in controller preflight. The bounded pass covers #1259/#1260/#1302/#1303/#1365/#1295; this spec touches #1365 only, whose docs-only candidate #1396 is not a runtime fix. This deployment alone does not diagnose or close every cause of the recorded watchdog failure.

## Problem

Reviewed `gcp/deploy.sh` registers `av-options-daily` at 21:00 ET, `gamma-levels-daily` at 22:30 ET and `strat-engine-daily` at 23:35 ET. Elapsed offsets do not establish successful upstream completion or complete source partitions. `economic-events-daily` at 07:00 ET cannot observe later released actuals. The reviewed repair requires actual scheduler wiring; merely adding callable runtime code leaves both failures in production.

## Non-goals

No financial algorithms, provider contracts, history rebuild, trigger/gate governance changes, unrelated job rewiring, new credentials, general workflow engine or automatic issue closure. Do not edit the data/report/research specifications from the implementation branch. Preserve existing monthly options and unrelated STRAT enrichment schedules unless the scoped dependency tests establish that a named duplicate launcher must be disabled and documented.

## Approaches considered

1. Keep fixed offsets: rejected because successful completion is unproven.
2. Replace all workflows: outside the approved scope.
3. Wire the approved runtime orchestrator through existing deployment helpers, disable its duplicate direct launchers and add a bounded due-release dispatcher: selected.

## Design

### A. Ownership, interfaces and merge order

Modify only deployment ownership surfaces: `gcp/deploy.sh`, its directly associated deployment tests and FEAT-DEPLOY-001 documentation. Use existing image/service-account/secret-reference/region helpers and create/update conventions. Do not create another gamma/STRAT implementation or provider adapter. After the data implementation merges, consume its production commands:

- `python -m gcp.data_refresh_sequence scheduled-sequence [--dry-run]`: launch existing `fetch-av-options-backfill`, capture its actual execution ID, wait for its successful terminal state and expected complete partition receipts, then launch existing `p2-build-gamma-levels` followed by bounded dependent `strat-engine` work. Runtime owns scope, locks, clocks, receipts and the five-session validation lookback.
- `python -m gcp.data_refresh_sequence sequence --manifest <path> [--dry-run]`: explicit bounded repair manifest; never the recurring scheduler's hardcoded October 8 backfill.
- `python -m gcp.data_refresh_sequence due-macro [--dry-run]`: persisted due releases, at most 3 attempts/event through 60 minutes, ≤3 pages/3,000 rows and ≤6 SQL round-trips/invocation, preserving late/unavailable actual status.

Publication/merge DAG: canonical inventory → separate approved specs → data runtime implementation → this deployment implementation. Data runtime D11 does not wait for this configuration or live activation. Tolerant solyra UI can deploy against the old backend and must precede nullable report backend merge (report I7); this deployment is not a prerequisite for that compatibility release. Tests can use merged source fixtures without requiring production data mutation.

### B. Reproducible configuration

Create/update bounded Cloud Run jobs `data-refresh-sequence` and `economic-actuals-refresh` using the existing production image containing the merged runtime and minimal existing identity/secret references. Commands select the two modes above; arguments are equivalent on create and update, including clearing stale args. Explicit max-retries is 0. Resolve job existence and image revision before enabling scheduler targets; unavailable runtime/image fails dry-run/rollout rather than launching stale code.

Retarget existing `av-options-daily` (21:00 ET weekdays) to `data-refresh-sequence`; retain its daily cadence and existing selected universe. Explicitly pause/remove direct `gamma-levels-daily` and `strat-engine-daily` scheduler launchers in this deployment path, and ensure subsequent idempotent deployments do not recreate/reactivate them. Their jobs remain available to the runtime launcher and explicit bounded manual repair. Retain unrelated schedules and `av-options-monthly`; overlap with another options run must remain lock/receipt safe, and an unrelated run ID must not unlock this sequence. Existing `strat-enrich-daily` is not silently treated as the dependent feature-builder launch; inventory its distinct role in the runbook.

Keep `economic-events-daily` 07:00 ET schedule retrieval. Configure one `economic-actuals-refresh` scheduler at `*/15 8-17 * * 1-5` in `America/New_York`, targeting the identically named job. Configure existing authenticated scheduler-to-job identity consistently with current helpers; no public job endpoint. All target URIs resolve to jobs created by the same configuration. Dry-run emits redacted commands/diffs without changing Cloud resources or resolving secret values into logs.

### C. Capacity and limits

These are planning ceilings, to be replaced by measured production-driver results in P5. Apply Rule 0: if measured estimate exceeds one quarter of the configured task timeout, reduce budgets/refactor; do not raise a timeout to conceal excessive work.

| Workload | Volume | Velocity | Wall-clock and cost |
|---|---|---|---|
| Due-release active invocation | ≤3,000 observations ×1KB ≈3MB | ≤3 HTTP pages, ≤6 batched SQL calls, ≤3 attempts/event across dispatcher runs | 90s HTTP failure bounds +12s SQL +10s compute =112s; proposed 1vCPU/512Mi/600s timeout, 112<150s. At $0.000024/vCPU-s+$0.0000025/GiB-s: ≤$0.00283/run ×40/day ×30 = $3.40/month upper active ceiling |
| No releases due | One indexed due query, no payload | 1 SQL, 0 provider requests | Assumed ≤2s, $0.0000505/run; ≤$0.061/month using40×30 upper count |
| Sequence controller | Exact manifest and receipts, ≤1MB per invocation | 3 job launches maximum; batched status/receipt reads, at most one poll per30s and120 polls total | Proposed 1vCPU/512Mi/14400s timeout; must measure total wait+driver time <3600s, otherwise do not enable recurring activation. A3600s ceiling costs≤$0.0909/run ×1/day ×30=$2.73/month, excluding existing worker jobs |

The sequence controller's 60-minute polling bound fails closed with resumable status if upstream is still running. Persist execution IDs before returning; retry/resume checks the same run rather than launching duplicates. Existing worker jobs retain their reviewed resources and existing cost baseline; data spec capacity bounds apply to repair/refresh worker slices. The proposed new controller/dispatcher ceiling is ~$6.13/month; this is incremental compute only, excluding existing workers, always-on SQL and provider charges. Verify actual resources, monthly weekday count and p95 execution durations before activation. If existing normal worker duration cannot fit, revise bounded orchestration architecture before declaring P5 done; do not silently expand polling/timeouts or force daily scope into the one-off repair budget.

### D. Executable acceptance and operational proof

`tests/gcp/test_data_refresh_deploy.py` executes actual deployment functions with a fake `gcloud` executable and redacted environment, captures argv for create and existing-job update paths and compares effective configuration. Tests assert target existence, exact modes, preserved unrelated schedulers, disabled duplicates after two deployments, ET timezone including DST, retry/resource bounds and zero mutating calls in dry-run. A grep-only assertion is insufficient.

`tests/integration/test_refresh_deployment_acceptance.py` executes the rendered runtime commands with isolated PostgreSQL and a recording control-plane transport. Assert exact upstream success+complete receipts before gamma, gamma success before STRAT, failed/partial/unrelated upstream suppresses dependents, two overlapping schedulers produce one sequence, resume does not relaunch completed steps, 07:00 schedule retrieval produces no actual claim, 08:30 release dispatch can persist a proved actual, three-attempt/60-minute limits and late/unpublished receipt status. Use the production runtime/source code and pinned fixtures, not duplicate scheduler business logic. Record execution IDs, receipt IDs, ordering and measured I/O in P4/P5 evidence.

Premerge P1–P5 are reproducible isolated/configuration proof; P6 is a reviewable operational runbook and verification ledger. After reviewed merge/deployment, the controller records actual image revision, enabled/disabled scheduler descriptions, Cloud execution IDs/timestamps, source partition/availability receipts and downstream IDs in that ledger. Query for zero downstream launches associated with failed/incomplete upstream, successful due-release actual after its release time and watchdog source degradation/alert behavior. Until those checks actually run, **production activation acceptance and approved cross-repository gate6 remain pending**; neither a dry-run nor these docs constitutes live proof. This separation avoids requiring a postmerge deployment as a premerge test while retaining the reviewed operational acceptance.

### E. Rollout and rollback

Dry-run first; verify deployed image/runtime availability and exact source schema from the data release. Apply job definitions with dispatch paused, compare effective create/update configuration, then pause duplicate offsets before enabling the retargeted daily dispatcher and due-release schedule. Never run both new and duplicate direct launchers as a rollout shortcut. The runbook includes a redacted manifest and bounded owner-authorized first execution; documentation preparation performs no deployment or data writes.

Rollback pauses both new dispatchers, captures active execution/receipt IDs, and leaves last-good data intact. Restore prior job/config references if required; unsafe fixed-offset downstream schedules remain paused until an operator verifies the relevant upstream receipts or runs a bounded sequence. Do not relabel stale data current or erase failed receipts. Document recovery of interrupted locks and due-release attempt cursors using existing runtime semantics.

## Risks

Repeated deploy could recreate old offsets, create/update divergence could leave stale arguments, DST could miss release windows, and waiting controllers could consume excessive timeout/cost. P1–P5 test/measure these boundaries. Operational checks remain required before declaring the overall repair deployed and healthy. This specification changes neither issue definitions nor catalog capability ownership.
