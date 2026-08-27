# 08 — Infra Drift: deployed GCP vs repo

Project `adept-mountain-474619-d4`, region `us-east1`. Read-only audit —
no `gcloud run jobs update`, `ALTER TABLE`, or scheduler mutations were
run. All calls used `env -u CLOUDSDK_AUTH_ACCESS_TOKEN`.

## CRITICAL

### D1 — `signal-quality-report-hourly` is PAUSED live; the repo has no record this is intentional
- Repo (`gcp/deploy.sh:3660-3661`): created as an enabled hourly
  trigger `0 10-16 * * 1-5`. No comment anywhere (deploy.sh,
  `docs/plans/SIGNAL_QUALITY_TEST_PLAN.md`,
  `docs/audit/2026-05-08/track-F.md`) suggesting a pause.
- GCP: `state: PAUSED`.
- Corroborated by execution history, not just scheduler state: every
  `signal-quality-report` execution for 3+ weeks (back to 2026-08-07)
  fires at exactly 05:00 UTC — the nightly `--mode=historical` cron
  only. **Zero rolling-mode executions during market hours.**
- Consequence: the Phase 0.5 rolling `signal_metrics` classification
  (60m/90m/120m/240m windows) has not updated intraday for 3+ weeks.
  **Silent** — a paused scheduler never runs and never errors, so no
  failure-notifier issue fires. `_schedule()`'s create branch is a no-op
  when the resource exists, so re-running `./gcp/deploy.sh schedulers`
  will **not** self-heal it; needs an explicit
  `gcloud scheduler jobs resume signal-quality-report-hourly`.

> **VERIFIED BY CLAUDE:** `gcloud scheduler jobs describe
> signal-quality-report-hourly` → `PAUSED  0 10-16 * * 1-5`. Confirmed.

### D2 — `p2-build-gamma-levels`: daily production job with zero infra-as-code
- GCP: exists, scheduled daily (`gamma-levels-daily`, `30 22 * * 1-5`),
  image `:research`, succeeding every weekday through 2026-08-27.
- Repo: **no** `gcloud run jobs create p2-build-gamma-levels` anywhere.
  `deploy_schedulers()` references the job by name but nothing creates
  it.
- Consequence: it writes `gamma_levels_eod`, which `strat-engine-daily`
  consumes 65 minutes later for gamma/vex/vix features on every
  production bar — the exact dependency whose breakage caused the
  2026-05-22 four-week silent NULL-out. If this job spec is deleted or
  its `:research` tag garbage-collected, **there is no
  `./gcp/deploy.sh` command to recreate it.**

> **VERIFIED BY CLAUDE — with important additional context.**
> Confirmed the job exists live and the scheduler targets it. Also
> checked what report 04 could not: the job's last execution
> (2026-08-27 02:30) ran digest
> `sha256:b7288ec5…`, **identical to the current `:research` image**
> built after the #798/#800 merges, and `gamma_levels_eod` for
> 2026-08-24..27 has **zero** `gamma_balance_price` nulls across
> IWM/SPY/QQQ. So the gamma pipeline is running current code and is
> healthy — the risk here is disaster-recovery and manageability, not
> an active outage. Cross-references report 04 CRITICAL #1, whose
> stated "404 every night" consequence is **wrong**.

### D3 — `fetch-fred-rates` pinned to a 3.5-month-old image tag
- Repo (`deploy_fetch_fred_rates`, `gcp/deploy.sh:1909-1926`):
  `--image "${IMAGE}"` (untagged, tracks `:latest`).
- GCP: `trading-system:spx-removal-fred-20260516` — a dated one-off tag
  from 2026-05-16.
- The job runs daily and **succeeds**, so it never surfaces as failing;
  it just silently runs stale code. 15 commits touching
  `gcp/database.py`, `lib/`, and `requirements-gcp.txt` have landed
  since. This is the incident class `gcp/audit_infra_drift.py`'s own
  docstring names — except 3+ months rather than 12 hours.
- Fix: `./gcp/deploy.sh fred-rates` re-pins to `:latest`.

> **VERIFIED BY CLAUDE — image pin confirmed; my root-cause claim was
> WRONG and is withdrawn.**
> The image tag is confirmed verbatim, so the drift finding stands.
>
> I initially wrote that this "likely root-causes issue #783" because
> `daily_rates` had only 4 rows in the last 7 days. **Codex challenged
> that and was correct.** Pulling the actual dates shows a clean,
> gapless business-day series:
> `2026-08-12 Wed, 08-13 Thu, 08-14 Fri, 08-17 Mon, 08-18 Tue,
> 08-19 Wed, 08-20 Thu, 08-21 Fri, 08-24 Mon, 08-25 Tue`.
> The "4 in 7 days" was simply the weekend (Aug 22-23) plus normal FRED
> publication lag for 08-26/27 — not staleness. The job succeeds, and
> its pinned entrypoint still performs the same 14-day DGS3MO
> fetch/upsert.
>
> **Correct status:** infra drift is real (a daily job has run
> 3.5-month-old code for months, and 15 commits to shared libs are
> absent from its image), but there is **no evidence it is causing a
> data problem**, and it should **not** be presented as the root cause
> of #783. Establishing causality would require diffing the pinned
> image's fetcher behaviour or reading its response/write logs.
> Severity re-rated **CRITICAL → HIGH** (drift/maintainability, not an
> active data outage).

## HIGH

- **D4 — `magnitude-recal` carries drifted `--command`/`--args`**, the
  same pattern as the `backtest-pipeline` mis-pin found earlier today.
  Repo says
  `-m gcp.research.magnitude_engine.mag_walk_forward --phase=phase0
  --all-cells --calibration=isotonic`; GCP has `command=['python']`,
  `args=['-c', "import os,json;…assemble_movement_statement…"]` — an
  unrelated inline diagnostic, last modified 2026-07-10. Dormant since
  2026-07-12, so no active impact, but anyone running
  `gcloud run jobs execute magnitude-recal` while trusting the name
  silently runs the wrong script. Fix: `./gcp/deploy.sh magnitude-recal`.
- **D5 — `options-exec-backtest` was never deployed** (404 live) despite
  being wired into `deploy_fetchers()`. A different orphan
  `exec-backtest` exists instead (image `:research-exec-backtest`, last
  run 2026-05-27) with no `deploy_*` function. Implies
  `./gcp/deploy.sh fetchers`/`all` has never completed end-to-end since
  that function was added.
- **D6 — `db-query` resources bumped 16× live**: repo `512Mi/1cpu`, GCP
  `8Gi/2cpu`. This is the tool CLAUDE.md instructs using constantly;
  re-running `./gcp/deploy.sh db-query` would silently downsize it and
  risk OOM at the documented 50,000-row cap.
- **D7 — `compute-earnings-reactions` bumped live**: repo
  `1Gi/1800s/retries 1`, GCP `2Gi/5400s/retries 0`. Redeploying would
  regress it and likely reintroduce the timeout the bump fixed.
- **D8 — `build-options-greeks` timeout bumped live**: repo 3600s, GCP
  7200s. Redeploying halves its budget.

## MEDIUM

- **D9 — live columns absent from `gcp/schema.sql`**:
  `market_data_daily` has `return`, `intraday_return`, `rvol_10`,
  `volatility_30min`, `volatility_day`, `volume_ma_10`, `volume_ma_20`,
  `volume_usd` (8); `signal_alerts` has `level_state`,
  `opp_level_state` (2). No current production code reads or writes them
  (naming matches the legacy `scripts/fetch_market_data.py`, not the
  production fetcher), so low active risk — but `gcp/apply_schema.py`,
  the documented source of truth for disaster recovery, would not
  recreate them.
- **D10 — `gamma_levels_eod` (16 live cols) and
  `magnitude_per_bar_predictions` (13 live cols) have no entry at all in
  `gcp/schema.sql`** — not even the "built at runtime" disclaimer that
  `strat_features_<tf>` gets. Both work in production; this is a
  schema-as-source-of-truth completeness gap.
- **D11 — `gcp/queries/p7_schema.sql` still documents applying itself
  via `gh workflow run db-query.yml`**, a workflow deleted 2026-05-30.
  Correct path is `./scripts/db_query_cr.sh -f … --commit`.

## LOW — dormant orphans, no active impact

Cloud Run Jobs live with no `deploy_*` function, all dormant since the
May 2026 research programs wound down: `exec-backtest`,
`backtest-playability`, `compare-tier-fires`, `p2-outcomes-grid`,
`p45-deep-ds`, `p7-analyze-tf`, `p7-build-multi-tf-features`,
`p7a-iwm-30m-pipeline`, `strat-dir-features`.
(`p7b-next-candle-classifier` is **not** drift — it has a documented
no-op deploy stub and an explicitly commented-out scheduler.)
`compute-spx-greeks-backfill` has a deploy function but was never run
(404 live) — on-demand tool, low risk.

## Confirmed healthy

- The five jobs re-pinned today — `freshness-watchdog`,
  `fetch-av-options-realtime`, `magnitude-engine`,
  `magnitude-inference`, `backtest-pipeline` — all match `deploy.sh`
  exactly (image, command/args, memory/cpu, timeout, retries).
  **`backtest-pipeline` confirmed running `scripts.run_pipeline`**, so
  this morning's mis-pin fix held.
- All **84** Cloud Scheduler entries match repo-declared name + cron +
  target 1:1 — no orphan or missing schedulers apart from D1's paused
  state.
- GCS top-level structure matches what the code references.
- `cloud-sql-weekly-export` matches spec and is running (last dump
  2026-08-23, 58.7 GiB across 4 recent dumps).
- `market_data_intraday`, `etf_options_snapshots`, `premarket_analysis`,
  `insight_reports`, `job_runs` schemas match `gcp/schema.sql` exactly.
