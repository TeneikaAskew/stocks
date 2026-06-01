# Pipeline Failure Audit — 2026-06-01

Triage of every Cloud Run Job failure observed in the window
**2026-05-31 17:00 UTC → 2026-06-01 14:00 UTC**, plus the chronic
issues that the rolling failure-notifier hourly cron has been flagging.

## Scope

Today's failures across the ~55 Cloud Run Jobs in
`adept-mountain-474619-d4`. Each item is classified by:

- **Severity** — does it harm production, or is it operator-only?
- **Root cause** — code bug, config bug, capacity, data quality, image drift, user error
- **Recurring?** — has the failure-notifier opened an issue more than once?

## Findings

### F1 · [HIGH · IMAGE-DRIFT] `fetch-earnings-history-5t2hr` chained `_run_backfill` still running pre-PR-#580 code

**When**: 2026-05-31 23:15 UTC → 2026-06-01 01:15 UTC (2h47m wall-clock, hit retry-1 succeed after task-0 timeout).

**Symptom**: Chain log line shows `Estimated wall clock: 325 min (13s rate limit)` — the *old* log format that pre-dates PR #580. The new code emits `AV sleep: 1.00s/call (env=AV_BACKFILL_SLEEP_SECS)` followed by `Estimated wall clock: N min` (no "13s rate limit" suffix).

**Cause**: PR #580 was merged at 2026-05-31 16:30 UTC. The image pinned to the `fetch-earnings-history` job spec is *still* the pre-#580 digest because no `deploy_fetch_earnings_history` ran after the merge. Cloud Run resolves `:latest` at *job-update* time, not execute time — so even though `:latest` was rebuilt by post-#580 merges, the job spec holds a stale digest.

Env var `AV_BACKFILL_SLEEP_SECS=1.0` *is* set on the job (verified), but the running container has no code that reads it.

**Fix**: Run `./gcp/deploy.sh fetch-earnings-history` from a workstation. The deploy stanza re-pins to the current `:latest` digest, which now contains PR #580 + #581.

**Verification**: After re-deploy, the next scheduled run at 23:15 UTC should finish in ~10–30 min (not 2h47m).

### F2 · [MEDIUM · CONFIG] `freshness-watchdog-nd4x2` hit 900s task-timeout

**When**: 2026-06-01 13:00 UTC. Hourly cron `0 9-19 * * 1-5`.

**Symptom**: `Terminating task because it has reached the maximum timeout of 900 seconds.` Recent successful runs of the same job take 8m–14m9s.

**Recurring**: Yes — issue #576 (today), plus a similar timeout on 2026-05-30 15:50 (rndfd, 900s exact).

**Cause**: The job was migrated from GHA to Cloud Run on 2026-05-30 with a 900s task-timeout. Observed wall-clock floats between 8 and 14 minutes — variance >50% on a budget with 1.07× headroom. Per **CLAUDE.md Rule 0.5** (task-timeout ≥ 4× wall-clock), 900s is undersized for a 14m typical run.

**Fix**: Bump `deploy_freshness_watchdog` task-timeout to **3600s** (4× 15 min). Cloud Run charges runtime, not the cap; headroom is free.

### F3 · [HIGH · RECURRING · CAPACITY] `strat-engine-rrjlc` killed by OOM at 8Gi (`Container terminated on signal 9`)

**When**: 2026-06-01 05:53 UTC. Manual operator dispatch with `--rebuild --start-date=2016-01-01`.

**Symptom**: Loaded 996,924 1-min SPY RTH bars + 2,858 dates of gamma context, then killed during 1m TF featurize.

**Recurring**: Yes — 7 open issues (#557–#563) all on `strat-engine`. The recurrent root cause is `--rebuild` doing a single-shot in-memory featurize across 10 years.

**Cause**: The full-history rebuild path loads all bars at once before featurizing. Memory cap 8Gi is enough for the daily/incremental path (the production cron) but NOT for the operator's full-history rebuild flag.

**Fix options** (in increasing order of effort):

1. **Document**: `--rebuild --start-date=2016-01-01` requires temporarily bumping memory to 32Gi (operator-discretion, not scheduled). Add a runbook line to deploy.sh comment.
2. **Stream**: rewrite the featurize loop to chunk by year (50–90% memory reduction). Larger PR.

For this audit: pick (1). The scheduled production cron uses incremental mode and is not affected.

### F4 · [LOW · USER-ERROR] `strat-engine-jwr6x` + `-48lmn` argparse `unrecognized arguments: SPY QQQ`

**When**: 2026-05-31 18:27 (jwr6x), 2026-06-01 11:53 (48lmn).

**Symptom**: `strat_data_builder.py: error: unrecognized arguments: SPY QQQ` (or `bb20_bandwidth realized_vol_z …`).

**Cause**: Operator invoked `gcloud run jobs execute strat-engine --args="--tickers=IWM,SPY,QQQ,--rebuild"` thinking commas would be preserved as values. Per **CLAUDE.md Rule 0.4**, `gcloud --args` splits on commas; to keep commas inside a single arg you must use `^|^value` syntax. The deployed job spec uses correctly-quoted args, so the *scheduled* cron is fine — only ad-hoc dispatches hit this.

**Fix**: No code change needed. Operator runbook clarification.

### F5 · [LOW · IMAGE-OLDER] `strat-engine-x7g54` `NameError: name 'os' is not defined`

**When**: 2026-05-31 18:10 UTC.

**Symptom**: `NameError: name 'os' is not defined` at line 694 (an `os.environ.get(...)` default).

**Cause**: That code is gated by `import os` at line 50 of `strat_data_builder.py`. HEAD has the import. The execution was pinned to image `caf622f14…` — an older revision that did not yet include both the import and the line-694 usage. The job has since been re-deployed and subsequent runs succeed against the current `:latest`/`:research`.

**Fix**: No action — already healed by image rebuild.

### F6 · [MEDIUM · DATA-QUALITY] `backfill-daily-indicators-wfj2n` exit 1 from a single ticker error (`ONON`)

**When**: 2026-05-31 17:58 → 19:28 UTC (1h29m).

**Symptom**: `Done. tickers=1679 rows_upserted=3028414 errors=1` — only ONON failed. Container exited 1, triggering the auto-failure-issue (issue #574).

**Recurring**: Single ticker errors are routine. The job currently treats *any* non-zero error count as a job-level failure, which spams the failure-notifier.

**Cause**: Exit-non-zero-on-any-error is *correct* per **CLAUDE.md §3.7** (no silent fallbacks) — we want failures to surface — but the *granularity* is wrong. A single ticker's AV symbol mismatch or delisting shouldn't page on a job that successfully processed 1,678/1,679.

**Fix options**:

1. **Threshold**: exit 0 if `errors/tickers < 0.5%`, else exit 1. Surfaces real outages, ignores per-ticker dead-symbol noise. Document the threshold in the log.
2. **Classify**: treat AV `Invalid API call` (delisted/unknown symbol) as `OUTCOME_DEAD`, treat retryable errors as `OUTCOME_RETRY`, exit 1 only on systemic.

(2) is the pattern from PR #553 (`intraday-bulk-backfill` typed failure classification). The right long-term fix; out of scope for this audit.

For this audit: defer to a follow-up. Comment the issue (#574) with the diagnosis so it doesn't get duplicated.

### F7 · [INFO · DEPRECATED] `p7b-next-candle-classifier` (issue #555)

The job is deprecated per `deploy.sh` (replaced by `strat-engine`). It still has an active scheduler from before deprecation, so it fires + fails. Close the scheduler or delete the job.

### F8 · [INFO · INSPECT] `magnitude-engine` (issues #569, #570, #571), `fetch-av-options-historical-intraday` (#573), `options-exec-backtest` (#572)

Not investigated in detail in this audit; logged here for the issue-cleanup pass.

## Summary table

| # | Job | Severity | Cause class | Fix | Status |
|---|---|---|---|---|---|
| F1 | `fetch-earnings-history` | HIGH | Image-drift | Re-deploy from workstation | Action needed |
| F2 | `freshness-watchdog` | MEDIUM | Config (timeout) | Bump 900 → 3600s | ✅ Fixed in this branch |
| F3 | `strat-engine` (OOM) | HIGH | Capacity (operator-mode) | Document `--rebuild` mem footprint | ✅ Doc'd in this branch |
| F4 | `strat-engine` (argparse) | LOW | User error | Runbook clarification | Doc only |
| F5 | `strat-engine` (NameError) | LOW | Image-older | Self-heals | None needed |
| F6 | `backfill-daily-indicators` (ONON) | MEDIUM | Data-quality (granularity) | Typed-outcome classification | Follow-up PR |
| F7 | `p7b-next-candle-classifier` | INFO | Deprecated scheduler | Disable scheduler | Follow-up |
| F8 | magnitude-engine + 2 | INFO | Triage backlog | Per-issue investigation | Follow-up |

## What this PR ships

- **Bumps `freshness-watchdog` task-timeout 900 → 3600s** (F2) — cures the recurring transient timeout.
- **Documents `strat-engine --rebuild` memory footprint** in deploy.sh comment (F3) — guidance for operators.
- **This audit doc** as the durable record.

## What this PR does NOT ship

- The `fetch-earnings-history` re-deploy (F1) — requires `gcloud` from a workstation with `roles/run.developer` to re-pin the image digest. The deploy stanza is unchanged.
- The `backfill-daily-indicators` typed-outcome refactor (F6) — out-of-scope for an audit PR. Will follow the `intraday-bulk-backfill` pattern from PR #553.
- `p7b-next-candle-classifier` scheduler cleanup (F7) — also out-of-scope; trivial follow-up.
- magnitude-engine + 2 deep-dives (F8) — separate triages.

## Post-merge actions

1. Operator runs `./gcp/deploy.sh freshness-watchdog` to apply F2.
2. Operator runs `./gcp/deploy.sh fetch-earnings-history` to fix F1 (image re-pin).
3. Verify F1 fix: next 23:15 UTC cron completes in ~10–30 min, not 2h47m.
4. Verify F2 fix: next hourly freshness-watchdog clears in <30 min consistently.

## Open follow-ups (separate branches)

- `backfill-daily-indicators` typed-outcome refactor (F6)
- `p7b-next-candle-classifier` scheduler removal (F7)
- magnitude-engine / fetch-av-options-historical-intraday / options-exec-backtest deep-dives (F8)
- `strat-engine` streaming-featurize so `--rebuild` doesn't OOM (F3 long-term)
