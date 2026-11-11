---
feat_id: FEAT-DEPLOY-001
req_ids: [REQ-CAP-001, REQ-CAP-003, REQ-DATA-001, REQ-DEPLOY-001, REQ-FRESH-001, REQ-GOV-004, REQ-OBS-001, REQ-SECRET-001]
issues: [1259, 1260]
canvases:
  - https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN
site_source_notes: [SHARED-07]
done_when:
  - "P1 jobs: tests/gcp/test_data_refresh_deploy.py runs the real deploy functions with a fake gcloud and proves create and update of data-refresh-sequence and economic-actuals-refresh converge to the same image, command, service account, secret references, 1 vCPU, 512Mi and --max-retries 0, with update clearing stale args; that insight-pipeline create and update both carry --max-retries 0 (a preexisting retries 1 job converges to 0), that update sets --task-timeout 1800 when the job's current timeout is above 1800, keeps a current timeout at or below 1800, and refuses to continue when the current timeout cannot be read; and that the effective IAM preflight fails closed (no scheduler mutation) when the scheduler identity cannot run the controller with overrides or the controller identity cannot run, get or list executions of each child, including when the permission check itself is unavailable; fails on origin/main, where neither job exists and insight-pipeline update omits retries and timeout"
  - "P2 cutover: tests/gcp/test_data_refresh_deploy.py proves av-options-daily (0 21 * * 1-5) targets data-refresh-sequence with the override --phase options-gamma, strat-engine-daily (35 23 * * 1-5) targets it with --phase strat, gamma-levels-daily is paused, a second deploy restores neither direct target nor drops an override, every other scheduler's name, cron and target is unchanged, and an injected failure at each cutover mutation (job create or update, pause, scheduler update or create, resume) never leaves a new phase launcher enabled while a direct gamma or STRAT launcher is enabled; an ordinary all or schedulers deploy leaves the new launchers paused, and the explicit activation command refuses, with no mutation, when any recorded prerequisite is missing (merged DATA Part 3 revision, RETRY_SPLIT on main, IAM preflight, alert route); fails on origin/main"
  - "P3 macro dispatcher: tests/gcp/test_data_refresh_deploy.py proves the scheduler economic-actuals-refresh runs */15 8-18 * * 1-5 in America/New_York (last run 18:45 ET, so a release admitted at or before 17:45 ET gets its release plus 60 minutes attempt) targeting the job of the same name with the due-macro command, and that economic-events-daily keeps its 0 7 * * 1-5 schedule collection; fails on origin/main"
  - "P4 composed acceptance: tests/integration/test_refresh_deployment_acceptance.py runs the commands the deploy script emits against isolated PostgreSQL and a recording Cloud Run transport, using the merged FEAT-DATA-001 controller, and proves one options-gamma and one strat execution per session under overlapping triggers, no gamma after a failed or one-sided options run, no STRAT before matching gamma and complete same-session market coverage, gamma waiting for the 22:00 scanner when its p95 run would cross 22:00 and then being launched after that scanner's terminal state and completing, and, with the rendered notifier log filter and the real gcp.failure_notifier.reconcile_closures, that a failed options-gamma phase opens an issue that a later successful strat phase does not close and that two consecutive overdue due-macro runs both fail without closing it, while a persisted actual of 0 lets the next run succeed and close it; fails on origin/main"
  - "P5 generated records: on the implementation head, scripts/maintenance/doc_inventory.py --insert has re-rendered the 05-a, 05-c and 05-e inventory blocks and the 05-a retry split through RETRY_SPLIT with check_generated_docs.gate_derived_numbers empty, the MODEL-TYPE-001 and MODEL-GAMMA-001 scheduler rows in docs/product/07-MODEL-REGISTRY.md and docs/product/generated/model-registry.json name the phased launchers, and tests/meta/test_model_registry_consistency.py and tests/scripts/test_check_generated_docs.py pass; the implementation PR body records the rendered configuration, a dry-run of create and update and the measured controller and due-macro durations against the Capacity table"
  - "P6 records: docs/RUNBOOK_DATA_REFRESH.md (registered in docs/DOC_REGISTRY.md) holds the activation order, the rollback, the disabled-offset inventory and the production verification queries; the FEAT-DEPLOY-001 catalog record and 12-PR-ISSUE-TRACEABILITY list the implementation PR; the (FEAT-DEPLOY-001, SHARED-07) implementation-source note carries a source identity produced and verified from the committed head; python3 scripts/gate/spec_gate.py --pr origin/main passes"
  - "P7 insider SEC identity: tests/gcp/test_data_refresh_deploy.py runs deploy_fetch_insider_transactions with a fake gcloud and a fake secret lookup and proves create and update both pass SEC_USER_AGENT from the sec-user-agent secret in --set-env-vars when the secret exists, omit it with a WARN when it does not, and leave every other flag unchanged; fails on origin/main, where the job's environment has no SEC_USER_AGENT"
status: approved
supersedes: null
---

# Deploy the completion-gated data refresh and the due-release macro dispatcher

## Status and authority

Approved by the owner on 2026-11-11 in stocks#1828. It claims no review or evidence it did not produce and takes effect when it merges. It is the deployment half of `docs/superpowers/specs/2026-11-11-feat-data-001-data-integrity.md` (FEAT-DATA-001, approved, same PR) and replaces stocks#1443 (re-cut 2 of `2026-10-12-feat-deploy-001-data-refresh.md`, from #1423). It deploys the runtime §J of that DATA spec defines and the SEC contact identity §G's fallback needs (§A here), and nothing else; the two are proposed together so the deployment is bound to an actual DATA spec on the same base.

## Problem (verified on main be2dd4d1)

- Dependents run on fixed offsets: `av-options-daily` 21:00 ET (`gcp/deploy.sh:4690`, `fetch-av-options-backfill`), `gamma-levels-daily` 22:30 (`:4522`, `p2-build-gamma-levels`), `fetch-market-data-daily` 23:00 (`:4645`), `strat-engine-daily` 23:35 (`:4524`, `strat-engine`). Snapshot scanners run at 22:00 (`options-daily-features`, `:4723`) and 23:15 (`options-daily-greeks`, `:4739`). Nothing stops gamma or STRAT after a failed or one-sided options run (#1259, #1260).
- Macro actuals are never refetched after release: `economic-events-daily` runs once at 07:00 (`:4771`).
- `insight-pipeline` create sets `--max-retries 1 --task-timeout 1800` (`gcp/deploy.sh:615` to 618) while update (`:624` to 630) sets neither, so an existing job keeps whatever retries and timeout it had; FEAT-INSIGHT-001's fenced report generation needs retries 0 and a timeout no higher than 1800.
- The declared retry split is stated in 05-a prose (`docs/product/infrastructure/05-a-ARCHITECTURE.md`: 43 of 68 jobs at retries 0, 24 at 1, one at 2) and checked by `check_generated_docs.gate_derived_numbers`; any job added or changed here moves it.

## Non-goals

No runtime logic (FEAT-DATA-001 §J owns it), no change to any worker job's resources, no new options collection, no IAM grant (the preflight reads effective permissions and blocks; operators grant through the existing reviewed process), no change to the notifier's issue policy, and no hand-typed retry counts.

## Design

### A. Jobs

`deploy_data_refresh_sequence` and `deploy_economic_actuals_refresh` create or update `data-refresh-sequence` (`python -m gcp.data_refresh_sequence scheduled-sequence`) and `economic-actuals-refresh` (`python -m gcp.data_refresh_sequence due-macro`) on the existing image and service account, existing secret references only (AV, Benzinga and FRED keys through the existing `_optional_secret_pair` helpers), 1 vCPU, 512Mi, `--max-retries 0`, task timeout 36000 s for the controller (the options-gamma phase can run from 21:00 to 23:15 ET, 8100 s, which must stay under a quarter of it) and 600 s for due-macro. Create and update carry the same flags and update clears stale args.

`deploy_fetch_insider_transactions` adds `SEC_USER_AGENT` from the existing `sec-user-agent` secret to the job's environment on create and update, the same way `deploy_fetch_sec_filings` does (`gcp/deploy.sh:2944` to 2951), so the DATA §G fallback has its contact identity in production. When the secret is absent it logs a WARN and leaves the variable out, and the fallback records `unavailable`. Its other flags are unchanged.

`deploy_insight_pipeline` sets `--max-retries 0` on both create and update. Update reads the current task timeout first: above 1800 it sets `--task-timeout 1800`; at or below 1800 it keeps it; unreadable stops the deploy with an error. The image, 2 vCPU, 8Gi and secrets are unchanged.

### B. Schedulers and cutover

- `av-options-daily` (`0 21 * * 1-5`) targets `data-refresh-sequence` with execution overrides `--phase options-gamma`; `strat-engine-daily` (`35 23 * * 1-5`) targets it with `--phase strat`. Each scheduler body carries its own complete argument array.
- `gamma-levels-daily` is paused; the direct `strat-engine` target is replaced by the retarget. `p2-build-gamma-levels` and `strat-engine` stay deployed for the controller and for manual bounded runs.
- New `economic-actuals-refresh` at `*/15 8-18 * * 1-5`, America/New_York. Its last run is 18:45, which covers the release plus 60 minutes attempt of every release the DATA spec admits (scheduled at or before 17:45). `economic-events-daily` keeps 07:00.
- `av-options-monthly`, `fetch-market-data-daily`, the scanners and every other scheduler are unchanged.

Activation is a separate explicit command. An ordinary `all` or `schedulers` deploy creates the jobs and leaves the new launchers paused. Activation refuses, with no mutation, unless these are recorded: the merged DATA Part 3 revision in the deployed image, the RETRY_SPLIT implementation on main, a passing IAM preflight, and a verified alert route. It then pauses the affected launchers, applies the retargets, pauses `gamma-levels-daily`, checks no direct gamma or STRAT target is enabled, and only then resumes the phase launchers and the dispatcher. Scheduler mutations are not atomic: on any failure it converges to the old topology if every new launcher is confirmed paused, otherwise to all affected launchers paused, and never to old and new both enabled.

**IAM preflight.** Read-only, through the effective permission check, never by role name: the scheduler identity needs `run.jobs.run` and `run.jobs.runWithOverrides` on `data-refresh-sequence`; the controller identity needs `run.jobs.run`, `run.executions.get` and `run.executions.list` on `fetch-av-options-backfill`, `p2-build-gamma-levels` and `strat-engine`, and read access to the executions of `fetch-market-data`, `build-options-daily-features` and `build-options-greeks`. Denied or indeterminate blocks activation and prints the missing permission.

**Alerts.** The controller and due-macro emit a structured ERROR and exit nonzero on failure; the existing `gcp-job-failures-sink` (cloud_run_job ERROR and failed RunJob events) routes them through `failure-notifier`. P4 composes the rendered filter with the real `reconcile_closures`.

### C. Retry split through RETRY_SPLIT

This change adds two retries-0 jobs and moves `insight-pipeline` from retries 1 to 0, which changes the 05-a split. The approved `2026-10-31-feat-cicd-001-retry-split-substitution.md` makes that split a renderer-owned substitution of `scripts/maintenance/doc_inventory.py`; its implementation (stage 3) is not on main at be2dd4d1. The implementation PR for this spec opens only after it is, and carries the rendered split; no number is typed and no exception is claimed. This replaces the predecessors' numeric-count exception, which was never approved.

### D. Topology documents

The feature PR edits only what the gate admits: the inventory blocks, the RETRY_SPLIT counts, the two registry rows, its own catalog and traceability records, its SITE note, and `docs/EARNINGS_PIPELINE.md` and the new runbook outside `docs/product`. Prose outside those (05-a's 22:00 / 22:30 schedule line and manual `docs/product/infrastructure/manual/05-a-ARCHITECTURE.md`, `docs/product/05-INFRASTRUCTURE.md`, `docs/product/infrastructure/05-g-DATA_PIPELINE.md`, the SHARED-07 chain text in `docs/product/03-SITE-TRACEABILITY.md`, and `docs/STRAT_ENGINE_ARCHITECTURE.drawio`) is updated by one docs PR after the implementation merges and before activation.

## Capacity and cost (Rule 0)

Planning ceilings; P5 replaces them with measured values. A measured duration above a quarter of its timeout is reduced, never hidden by a larger timeout.

| Workload | Volume | Velocity | Wall clock and cost |
|---|---|---|---|
| Controller, two phases per weekday | receipts and intents, under 1 MB per run | at most 120 control-plane requests and 120 SQL rounds per phase, one poll per 30 s | options-gamma at most 8100 s (21:00 to 23:15 ET, mostly waiting) and strat at most 3600 s, inside a 36000 s timeout; at $0.000024 per vCPU-s and $0.0000025 per GiB-s, at most $0.2045 and $0.0909 per run, about $8.86 per month |
| Due-macro with due work | at most 3000 observations, about 3 MB | at most 3 pages and 6 SQL batches per run | at most 112 s per run inside 600 s; at most $0.00283 per run, at most 44 runs per weekday, about $3.40 per month ceiling |
| Due-macro with nothing due | one indexed query | 1 SQL round | about 2 s, under $0.07 per month |

Incremental compute ceiling about $12.26 per month, excluding the existing worker jobs, Cloud SQL and provider plans. Existing workers keep their resources.

## Risks

- A partial cutover could run gamma twice: the order above and P2's failure injection prevent old and new being enabled together.
- An inherited insight timeout above 1800 would outlive the report fence: update clamps it and refuses when it cannot read it.
- The success of one phase could close the other phase's incident because both share a job name: the DATA controller stays nonzero over the prior 5 sessions' unresolved failures, and P4 proves it with the real notifier.
- The dispatcher window could miss a late release: admission stops at 17:45 and the last run is 18:45.

## Delivery

1. This spec PR (with the DATA spec).
2. FEAT-DATA-001 Parts 1 to 3 merge.
3. The RETRY_SPLIT implementation is on main.
4. `feature/feat-deploy-001-data-refresh` implementation PR with its plan (P1 to P7).
5. The topology docs PR (§D).
6. Owner-directed activation, recorded in the runbook.

## Open questions for the owner

1. Is waiting for the RETRY_SPLIT implementation acceptable, or should this implementation be re-sequenced behind another plan?
2. Is the activation order (docs PR merged before activation) acceptable, or should activation precede the docs PR?

## Close-out

Not done_when items: production activation, the first week of phase execution IDs and receipts recorded in the runbook's verification ledger, and the plan's `status: done` on a `docs/` branch after merge.
