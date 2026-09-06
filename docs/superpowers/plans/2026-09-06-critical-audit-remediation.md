# Critical Audit Remediation Plan — 2026-09-06

> Companion to `docs/audit/2026-08-27/issue-reconciliation.md`, which owns the
> finding → issue → stream mapping. This document is the execution plan for the
> open `severity:critical` issues from the 2026-08-27 review, starting with #861.
> Every "verified" line below was re-checked on 2026-09-06 against `main`
> (`88bd5c4`), live GCP, and Cloud SQL via `scripts/db_query_cr.sh`.

## 1. Where things stand

| Measure | 2026-09-06 |
|---|---:|
| Open `severity:critical` issues | 21 |
| Of those with **no** remediation PR at all | 17 |
| Partially remediated (code landed, data/policy work open) | 4 (#812, #815, #816, #835) |
| Findings in the critical set that are **wrong or partly wrong** as filed | 2 (#831 proposal 1, #813 "in-sample" wording) |
| Codex candidate fixes referenced in issue threads that never reached `origin` | 3 (#830 `1cacaed`, #835 `ffa366d`, #861 `effc499`) |

The reconciliation counted 100 canonical issues with no PR on 2026-08-30. A week
later that number is unchanged for the critical set. Nothing has touched
`gcp/deploy.sh` since the audit.

## 2. #861 — playbook_cards served stale as today's setups

### Verified state (2026-09-06)

```sql
SELECT max(analysis_date), current_date - max(analysis_date), count(*) FROM playbook_cards;
-- 2026-06-13 | 85 | 36        (one analysis_date; 12 cards × 3 tickers)
```

- `phase6-playbook` Cloud Run Job exists; its six executions are all on
  2026-06-14 (the as-of backfills). **No Cloud Scheduler entry** in GCP and none
  in `gcp/deploy.sh`. The job was never in the `all)` deploy target either.
- Root cause #1 is therefore **never scheduled**. The `#848` silent-failure
  hypothesis in the issue is ruled out for the June stop: there are no failed
  executions because there were no executions.
- Root cause #2 surfaced when the job was re-run on 2026-09-06 on the current
  image: **OOM-killed (signal 9) at 8Gi on the second ticker** after IWM
  completed in 5m00s. `market_data_intraday` now holds 2.0M / 2.3M / 2.4M
  raw 1-min bars for IWM / QQQ / SPY (2015 → today, extended hours included;
  the June capacity note assumed ~1.25M RTH bars). The first ticker's frame is
  not returned to the OS, so a single process walking three tickers grows its
  working set with the ticker count. Had the scheduler existed, the job would
  have started failing at some point over the summer instead of silently not
  running — a different failure with the same user-facing result.
- Consumers are live: `solyra` `DashboardPage.tsx` (top setup tile, also in
  review mode with `?date=`) and `PlaybookPage.tsx`. Both read
  `/api/playbook/{ticker}`, which resolved `max(analysis_date)` with no floor and
  omitted the date from the response.
- `playbook_cards` was not in `scripts/audit_data_freshness.py` CHECKS, so the
  watchdog could not have caught it.

### Fix (this branch, `claude/playbook-cards-audit-plan-alii6h` in both repos)

**stocks**

1. `platform/api/routers/playbook.py`
   - Selects `analysis_date` + `generated_at`; response now carries
     `analysis_date`, `generated_at`, `age_days`, `max_age_days` (and `as_of`
     in review mode).
   - `MAX_PLAYBOOK_AGE_DAYS = 7`: a set older than that, relative to today or
     to the requested `?date=`, is a **503** whose detail names the date, the
     age, and the writer job. The cache re-checks on every hit.
   - Strict DB query (`query_to_dataframe_strict`): a DB failure is a 5xx, not
     "no rows". No rows is a 404 naming the job. Bad `?date=` is a 422.
   - The undated GCS-markdown bridge is removed: it is written by the same job
     and could only re-serve the same stale cards with the age hidden.
2. `gcp/deploy.sh`: `_schedule "phase6-playbook-daily" "30 4 * * 1-5"
   "phase6-playbook"` and `deploy_phase6_playbook` in `all)`. The job now
   runs as `--tasks 3` (one ticker per task, `select_tickers_for_task` in
   `scripts/analysis/phase6_playbook.py`, keyed off `CLOUD_RUN_TASK_INDEX`)
   at 16Gi / 4 CPU, with the sizing flags on both the create and update
   branches (the #854 pattern). Capacity math is in the deploy.sh comment.
3. `scripts/audit_data_freshness.py`: `playbook_cards` CHECKS entry
   (per ticker, `writer_job: phase6-playbook`, `min_rows_per_day: 12`,
   `settle_hour_et: 5`).
4. Tests: `tests/test_playbook_evaluate.py` (freshness contract, boundary,
   cache re-check, as-of relative age, 404/422/503 paths, strict-query
   propagation), `tests/test_platform_api.py` (wire shape),
   `tests/test_phase6_playbook_scheduler.py` (scheduler, `all)` target, job
   args, watchdog entry).

**solyra**

5. `DashboardPage.tsx` / `PlaybookPage.tsx`: render "Cards as of <date> (Nd
   old)" from the server fields (`snapshotAgeLabel` in `src/lib/dates.ts`,
   unit-tested); a failed fetch shows the server's `detail` (the stale reason)
   instead of a generic "no setups" / "not found".
6. E2E: `tests/dashboard/dashboard.spec.ts` and `tests/playbook/playbook.spec.ts`
   cover the age label and the 503 refusal; fixtures in `src/mocks/dashboard.ts`.

**production (this session, after the code is pushed)**

7. Re-resolve the job image to the current `:latest` digest, raise the live
   job to 16Gi, execute it, verify `max(analysis_date) = current_date` for all
   three tickers, create the `phase6-playbook-daily` scheduler. Recorded on
   the issue. Until the stocks branch is built and deployed, the live job is
   the single-task 16Gi shape (the `--tasks 3` split needs the new image);
   `./gcp/deploy.sh phase6-playbook` converges it after merge.

### Definition of done (from the issue) — status

- [x] Render is guarded: stale rows are refused (503), never rendered.
- [x] Max-age guard fails loud (503 + log.error), and the watchdog sees the table.
- [ ] Writer is scheduled and the table is current (step 7, this session).
- [ ] Deployed: `solyra-api-prod` picks up the router change on the next
      stocks deploy; `phase6-playbook-daily` is created by
      `./gcp/deploy.sh schedulers` or by hand (step 7).

### Threshold rationale

Daily weekday cadence makes a healthy table 0–1 days old; the longest legitimate
gap (long weekend + holiday) is 4. Seven calendar days tolerates one missed run
and still fails within a week. The watchdog flags a missed run the same morning
(`min_rows_per_day`), so the 503 is the backstop, not the alarm.

## 3. The other open critical issues — verified triage

Effort: **S** < 1 h, code-only, hermetic tests · **M** half a day, or needs
production data work · **L** multi-day, or a policy/research decision.

### Wave 1 — small, code-only, ship now (each its own PR)

| Issue | Verified at HEAD | Fix | Files |
|---|---|---|---|
| #825 C-N1 fabricated $100 spot | yes, verbatim `grid.py:1090`; `/grid/timeseries` still has no frontend caller | return `_unavailable_envelope()` (already at `grid.py:184`) when `estimate_spot` has no price | `platform/api/routers/grid.py` + test |
| #826 C-N2 `or 0` on gamma/OI | yes, `grid.py:1058,1102` | delete the inline math; call `lib/gamma.greeks_coverage` / `aggregate_by_strike`, which already gate on coverage. Same endpoint as #825: one PR | same |
| #819 R2 ORB window vs UTC index | yes, `gcp/signal_monitor.py:850-853` | reuse the replay-aware `times_et` pattern already at `:400-403` / `:588-589` in `check_orb`; test with a UTC-indexed frame | `gcp/signal_monitor.py` + test |
| #822 R5 as-of leak in `summarize_backtest_metrics` | yes, `lib/agents/summarizers.py:926` `date <= :cutoff` | `<` (or thread `inclusive_today` like the other four sections); boundary test seeding a row dated exactly `as_of` | `lib/agents/summarizers.py` + test |
| #830 K2 Discord bot token via `--set-env-vars` | yes (code `deploy.sh:519-556`, live `secretKeyRef` empty) | move only `DISCORD_BOT_TOKEN` to `--set-secrets` (public key is a verification key, not a credential). Then: deploy → rotate token in the Dev Portal → new secret version → redeploy. Codex's `1cacaed` was never pushed; redo | `gcp/deploy.sh` |
| #833 D1 `signal-quality-report-hourly` PAUSED | yes; it is the **only** non-ENABLED scheduler of 84 | needs one decision: resume, or record the pause in `deploy.sh:3660`. Either way add a scheduler-state check to `gcp/audit_infra_drift.py` (nothing reads `state` today) | `gcp/deploy.sh`, `gcp/audit_infra_drift.py` |
| #835 D3 `fetch-fred-rates` on a May image tag | live-only drift; code already uses `${IMAGE}` | `./gcp/deploy.sh fred-rates` re-pins. Detector gap is real (`audit_infra_drift.py:200` skips tag-form images); Codex's `ffa366d` never landed | deploy op + `gcp/audit_infra_drift.py` |

### Wave 2 — medium; code is small, the data or decision is the work

| Issue | Verified | Fix | Note |
|---|---|---|---|
| #829 K1 + #834 D2 gamma-levels job has no IaC | yes; `deploy.sh:3326` is the only line naming `p2-build-gamma-levels` | add `deploy_p2_build_gamma_levels()` reproducing the live spec verbatim (research image, `-m gcp.research.p2_build_gamma_levels`, 2 CPU / 2Gi, retries 0, timeout 5400, `trading-runner@`), a `gamma-levels)` target, and `all)` | one PR for both |
| #831 K3 dead deploy fns / discord missing from `all)` | **half wrong**: `deploy_backfill_ticker` / `deploy_validate_brief` / `deploy_backtest` are the Discord service's backing jobs (`gcp/discord_interactions/main.py:459,774,801`) | do the **opposite** of proposal 1: wire all three plus `deploy_discord_interactions` into `discord)` and `all)`; add the reachability assertion (every `_schedule` target and every `deploy_*` reachable from `all)`) | correct the issue before acting |
| #812 T1 gamma-flip underflow | code fixed in #942 (`lib/gamma.py:766-800`, tests at `tests/test_gamma.py:803-908`) | remaining is data: rerun the >20 %-from-spot query on `gamma_levels_eod`, recompute or NULL the 54 rows, record on the issue | production data only |
| #823 R6 `refresh_level_map` uses today's daily bars | yes, `signal_monitor.py:727` unbounded load, `:759` `iloc[-1]` | bound the frame to `< analysis_date` before `calculate_historical_levels`; the re-anchor shadow values inherit the leak (#811) | code S, re-derivation M |
| #820 R3 `backfill_signals.py` scores zero into prod | yes; column-name divergence intact, `signal_alerts` has no `run_kind`/`source` column | quantify contaminated rows first, add a provenance column, then delete the script | data first |
| #821 R4 `compare_tier_fires.py` throwaway | yes | delete (S); re-derive the calibration conclusion via `scripts/replay_signal_monitor.py` (M) | pairs with #824 under #923 |
| #824 R7 `backfill_and_replay.py` divergent fetcher | yes | call `gcp.fetchers.fetch_market_data --date` (S); indicator-by-indicator diff + affected rows (M/L) | diff before delete |
| #815 T4 no live stop-loss | #937 landed docs that **raise** the bar rather than accept the policy | blocked on #814 (realistic fills) for the counterfactual | policy |

### Wave 3 — large; research or policy, do not start piecemeal

| Issue | Note |
|---|---|
| #813 T2 + #817 T6 | **Same root cause.** `_run_anchored_folds` does no fitting; the defect is selection on the same fold set with no untouched holdout, reported as "out-of-sample". Fix together: holdout + multiple-testing control in `scripts/run_param_sweep.py`; reuse `promotion_verdict` (`mag_walk_forward.py:368`) rather than a second gate. **S sub-task now:** flip `--apply` default to False (`run_param_sweep.py:235-238` auto-writes `exit_config_overrides` that live reads). |
| #814 T3 same-bar fills, zero costs | `lib/backtest.py:804` entries at signal-bar close, exits at `close_price`; no cost symbol in the file. Gates #815, #908, #882. |
| #816 T5 risk controls | #933 mechanism is a proven no-op by default; `daily_pnl` still realized-only (`:1059` vs `:1911`). **S sub-task now:** point the daily-loss check at `mtm_pnl` (`:1563`); delete dead `daily_profit_target`. Lowering any ceiling is gated on #940. Shadow data lands mid-September. |

## 4. Order of work

1. **#861** (this branch) — code pushed, job run, scheduler created, issue updated.
2. **Wave 1**, one PR each, in this order: #825+#826 (one PR), #819, #822, #830,
   #835 (deploy op + detector), #833 (after the owner answers resume-or-record).
3. **Wave 2**: #829+#834, #831 (with the issue corrected first), #823, #812 data
   work, then #820 → #821 → #824 (data quantification before any deletion).
4. **Wave 3** as decisions land; take the two S sub-tasks (#813 `--apply`
   default, #816 `mtm_pnl`) immediately as their own PRs.

## 5. Rules applied

- No fix without a reproducing test first (CLAUDE.md §2.5, §4).
- No `except: return empty` / `or 0` / undated fallback added or extended (§3.7).
- Production writes only through the production job (§3.6), idempotent upserts.
- Every stale-served surface gets the same three controls #861 now has:
  a scheduler, a watchdog entry, and a read-side max-age refusal with the date in
  the response. That is the shared read-side primitive PR-0 in the reconciliation
  asks for; `playbook.py` is its first instance and `#863`'s `#938` guard the second.
