---
feat_id: FEAT-DEPLOY-001
req_ids: ["REQ-SECRET-001", "REQ-DEPLOY-001", "REQ-DATA-004", "REQ-CAP-001", "REQ-CAP-002", "REQ-CAP-003", "REQ-OBS-001"]
issues: [1201, 853, 854, 858]
canvases: ["https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN"]
done_when:
  - "python -m pytest tests/gcp/test_deploy_av_remediation.py proves av-remediation reaches only the resource allowlist below, identical create/update flags, all three news jobs use av-api-key secret references with no literal AV key env value, 3600s timeout and zero retries."
  - "python -m pytest tests/gcp/test_deploy_audit_infra_drift.py proves only roles/cloudscheduler.viewer is added for the deployed auditor service account, existing unrelated bindings are unchanged, and read/grant failures exit nonzero."
  - "python -m pytest tests/gcp/test_av_bucket_lifecycle.py proves av-remediation, setup_cloud_sql.sh and setup_pg_dump_iam preserve unrelated existing rules and converge av/raw/ Delete age 90 without losing raw/ age 730 or sql-dumps/ age 30 rules."
  - "python -m pytest tests/gcp/test_deploy_av_remediation.py asserts every schedule, timezone, timeout and retry value in the contract table, the OPTION shared-calendar dependency, and refusal to activate new schedules without sibling terminal-telemetry evidence."
  - "docs/AV_REMEDIATION_RUNBOOK.md names TeneikaAskew as accountable av-api-key rotation owner, gives rotation/verification/rollback commands and the per-run cost calculation, and links tests for half-days, holidays, DST and delayed-start closing capture."
  - "tests/gcp/test_deploy_av_remediation.py verifies scripts/maintenance/verify_av_remediation.py rejects settings that differ from the contract and emits the required redacted report fields; docs/AV_REMEDIATION_RUNBOOK.md gives the exact post-merge verification command and pending/verified rollout states; FEAT-DEPLOY-001 links code acceptance and rollout/rollback instructions without claiming unperformed deployment."
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

Add a selective `av-remediation` deployment path whose resource allowlist is the five new jobs in the table below, `fetch-news-sentiment`, `fetch-news-sentiment-topics`, `fetch-news-sentiment-earnings`, `fetch-insider-transactions`, `fetch-earnings-history`, `av-options-realtime`, `audit-infra-drift`, and the existing `freshness-watchdog` coverage flag. Existing schedule names/targets remain unchanged except explicitly identified AV wiring. Preserve unrelated services, audience configuration and IAM bindings. The related issues #853 (retries), #854 (create/update convergence), #858 (realtime scheduling) and #1201 (auditor IAM) are touched; closure requires each issue's own acceptance evidence.

Use Secret Manager references for every AV consumer: map the module's required AV environment name to `av-api-key:latest`, remove any conflicting literal key env value, and never print secret values during discovery or verification. All three news jobs converge to 3600s timeout and zero task retries on both create and update. Insider converges to 3600s and zero retries. Preserve the existing earnings-history 28800s timeout and chained-backfill settings; the short estimates timeout must never be applied to that job. Grant only `roles/cloudscheduler.viewer` at the configured project to the service account resolved from the deployed auditor job. Failed policy reads or grants fail the targeted deployment; do not grant editor/admin roles or change unrelated bindings.

`docs/AV_REMEDIATION_RUNBOOK.md` records project owner TeneikaAskew as the accountable `av-api-key` rotation owner. Its operator procedure creates a Secret Manager version, verifies only the allowlisted consumers and rolls back to the last working version if needed; the document distinguishes this operational assignment from evidence that a rotation was actually performed.

### Sibling prerequisites and activation

The producer contracts are `docs/superpowers/specs/2026-10-12-feat-data-001-av-indicators.md`, `2026-10-12-feat-data-001-av-market-data.md`, `2026-10-12-feat-catalyst-001-av-catalysts.md` and `2026-10-12-feat-option-001-av-options.md` in that same directory. The watchdog contract is `2026-10-12-feat-ops-001-av-operations.md`. Merge each relevant implementation before wiring its CLI; use its reviewed bounds and exact module arguments. Deployment never imports an unmerged sibling.

New schedules stay paused until the deployed immutable image has passing sibling contract tests and a bounded smoke proving REQ-OBS-001 terminal telemetry. Evidence must include run identity, input/processed/failed/written counts, data watermark (explicitly unavailable when no data was obtained), duration, error class, retry count and terminal success/partial/failure/skipped status. Test success, valid empty, failure before the first group and partial failure after a durable group, using `record_job_run` or an equivalent durable run record. `tests/gcp/test_deploy_av_remediation.py` tests the activation gate with missing and passing evidence; the verifier checks the report against the deployed image digest and refuses activation on missing or mismatched evidence. The runbook links the exact sibling test paths and redacted smoke records.

The closing and regular realtime guards depend on the single fail-closed shared exchange-calendar API delivered by the OPTION spec. Do not duplicate weekday or fixed-hour logic in deployment. OPTION's calendar tests must cover a normal close, the November early close, a holiday, DST and unavailable calendar data. Closing capture uses deterministic close slots, actual retrieval clocks, an intended session date, and a close-inclusive, close+30-minutes-exclusive recovery window. The fixed Scheduler trigger launches the reviewed OPTION CLI; its tested session-intent contract governs delayed startup. Before-close invocations emit skipped telemetry; after-cutoff missed capture emits incomplete telemetry. Keep the closing schedule paused if that dependency cannot satisfy these checks.

All new schedules use `America/New_York`, one CPU, 512 MiB and zero Cloud Run task retries. Job and Scheduler resource names are identical in this table; job commands/args must be copied from the merged producer CLI contract and verified against the table's bounded purpose.

| Job and Scheduler name | Cron | Bounded purpose | Task timeout |
|---|---|---|---|
| `fetch-av-indicators` | `45 2 * * 2-6` | `gcp.fetchers.fetch_av_indicators --all --intervals=daily,15min --mode=incremental --lookback-days=7 --max-months=2` | 1800s |
| `fetch-av-indices` | `15 23 * * 1-5` | Native SPX/VIX incremental reference CLI | 1200s |
| `fetch-av-reference-data` | `15 5 * * 0` | SPY/IWM/QQQ ETF/actions plus bounded listing/catalog CLI | 2700s |
| `fetch-av-earnings-estimates` | `15 6 * * 1-5` | Estimates CLI with at most 100 tickers | 1800s |
| `av-options-closing` | `0 13-16 * * 1-5` | Realtime options CLI `--closing-only`; actual session-close guard | 600s |

The table's resource names are the deployment contract; producer CLI implementations retain their own FEAT ownership. Leave `AV_INDICATOR_COVERAGE_ENABLED=false` until corrected timestamp normalization and the first scheduled-writer bounded refresh are verified. Then enable it on `freshness-watchdog` and verify the OPS coverage check is active. Paused schedules and skipped coverage are explicitly incomplete rollout evidence, not successful full deployment.

### Lifecycle convergence

The configured raw archive bucket receives a `Delete` rule with object age 90 and exact `matchesPrefix: ["av/raw/"]`. Include every supported lifecycle writer: the targeted AV path, `gcp/setup_cloud_sql.sh`, and `setup_pg_dump_iam` in `gcp/deploy.sh`. Each must read the existing lifecycle, preserve unrelated entries and converge its owned rules through a shared merge helper; never replace the policy with a hard-coded subset. Preserve existing `raw/` age 730 and `sql-dumps/` age 30 rules when present. New buckets receive the same baseline rules so applying the writers in any order converges. A policy read/parse/update failure returns nonzero and must not replace the policy with an empty/default result. `tests/gcp/test_av_bucket_lifecycle.py` exercises each caller and both orders with an unrelated sentinel rule, repeated application and failed reads/writes.

### File ownership

`gcp/deploy.sh`; `gcp/setup_cloud_sql.sh`; one narrowly scoped shared lifecycle merge helper under `gcp/`; `scripts/maintenance/verify_av_remediation.py`; `tests/gcp/test_deploy_av_remediation.py`, `tests/gcp/test_deploy_audit_infra_drift.py`, `tests/gcp/test_av_bucket_lifecycle.py`; `docs/AV_REMEDIATION_RUNBOOK.md`; the FEAT-DEPLOY-001 catalog/traceability record. Generated inventory blocks only if permitted by the current gate. No producer business-logic edits or unrelated service deployment.

### Capacity and cost

Indicator: 54 calls, <=350s, timeout 1800s. Index: approximately 3 calls/incremental dates, <=185s, timeout 1200s. ETF/reference: approximately 10 calls/<=20,000 listing rows, <=675s including SQL margin, timeout 2700s. Estimates: <=100 calls, <=270s, timeout 1800s. All new jobs use one CPU, 512 MiB, zero task retries, and timeout at least four times the estimate. Insider/news are bounded to 300 responses, <=810s estimated runtime and timeout 3600s. Existing earnings-history's chained workload retains its 28800s timeout. Closing capture makes three ticker requests, <=42,000 contracts, <=150s and timeout 600s; the other three weekday launches skip without vendor requests. Producer specs own rows/bytes and batched I/O contracts; deployment verifies the configured bounds against those contracts.

Illustrative gross Cloud Run estimate, excluding free-tier credits: assume $0.000018/vCPU-second plus $0.000002/GiB-second, hence $0.000019/second at one CPU and 0.5 GiB, with a minimum 60-second charge per job execution. Calendar cadence uses 5/7 runs/day for weekday jobs and 1/7 for weekly jobs; holidays reduce actual active captures.

| Workload | Estimated dollars/run | Runs/day for budget | Dollars/run x runs/day x 30 |
|---|---|---|---|
| Indicators, 350s | 0.006650 | 5/7 | 0.1425 |
| Indices, 185s | 0.003515 | 5/7 | 0.0753 |
| Reference, 675s | 0.012825 | 1/7 | 0.0550 |
| Estimates, 270s | 0.005130 | 5/7 | 0.1099 |
| Closing active capture, 150s | 0.002850 | 5/7 | 0.0611 |
| Closing skipped launches, 60s billing floor | 0.001140 | 15/7 | 0.0733 |

Total estimated new Cloud Run compute is approximately $0.52/month. At an assumed $0.10/job/month, five additional Scheduler jobs add up to $0.50/month before free allowances. Existing prepaid AV entitlement is assumed to have zero marginal subscription cost; an entitlement change requires a revised estimate. Image storage, archive storage/operations and network charges are separate. Report archive storage at measured and worst-case retained rates from the CATALYST spec. Record actual billing-region prices and measured smokes in the runbook; the assumptions above are estimates, not a billing guarantee.

### Validation and rollout

Reproduce each defect before its fix, run focused contract and I/O-shape tests, perform independent revision-specific review, and run the repository delivery/docs checks. Preserve existing valid rows and record exact CLI/source revision/parameters for production smokes and backfills. Roll out schema before dependent jobs, one bounded group first, then proceed only after the specific output reconciles to AV. Partial or refused groups are reported; they are never described as completed repairs. Implementation PR acceptance consists of executable deployment/verifier tests and the reviewed rollout procedure; it does not require deploying its own unmerged code. After the required implementations merge, run `python scripts/maintenance/verify_av_remediation.py --output work/av-remediation-rollout.json`. The redacted report must record actual image digest, args, timeout, retries, secret references, auditor identity/role, lifecycle and enabled Scheduler targets. Overall remediation completion requires the enabled schedules, producer smokes and active monitoring evidence; code merge or paused resources alone never satisfy production completion.

## Risks

Vendor revisions may invalidate old-value equality; archive/source failures may prevent a safe repair; missing permissions may block rollout. Tests must reject guesses, preserve durable completed groups and report incomplete results. Parallel changes share only additive schema blocks and integration interfaces; merge them without discarding sibling definitions.
