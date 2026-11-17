---
feat_id: FEAT-DEPLOY-001
req_ids: [REQ-CAP-001, REQ-CAP-003, REQ-DATA-001, REQ-DEPLOY-001]
issues: [2060]
canvases:
  - https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN
site_source_notes: [CATALYSTS-01, CATALYSTS-04, DASHBOARD-01]
done_when:
  - "tests/gcp/test_compute_earnings_reactions.py::test_splits_requested_only_for_a_checkable_window passes: populate_for_tickers over stubbed earnings_history rows and daily windows for AAA (one BMO event whose completed window is non-empty), NOB (every window empty), UNK (every event of unknown timing) and SES (every report dated on a day that is not an exchange session) requests SPLITS for AAA only, writes AAA's reaction, emits write_skipped receipts for NOB, UNK and SES with the reasons main gives them (insufficient_surrounding_daily_bars, unknown_event_timing, report_date_is_not_exchange_session), and logs splits_unavailable=0 of 1 tickers (on main it requests SPLITS for all four tickers)"
  - "tests/gcp/test_compute_earnings_reactions.py::test_vendor_failures_stop_the_run passes: over twelve tickers each with a checkable window and requests.get stubbed so that the SPLITS requests of the third, fourth and fifth tickers raise requests.ConnectTimeout, compute_earnings_reactions.main() makes exactly five SPLITS requests, upserts the reactions of the first two tickers, emits split_status_unavailable for every event of the other ten, logs one line holding vendor_requests_stopped, consecutive=3 and the seven tickers never requested, and returns 1; with twenty tickers whose odd-numbered requests raise requests.ReadTimeout it stops after the tenth failure (nineteen requests) and returns 1; with twelve tickers whose replies all hold Information it requests all twelve (a vendor refusal is not counted) and returns 1 as on main; with three tickers and one ConnectTimeout it requests all three and returns 0 (on main every case requests every ticker)"
  - "tests/gcp/test_deploy_reachability.py::test_compute_earnings_reactions_declares_its_sizing_on_both_branches passes: deploy_compute_earnings_reactions executed under bash with a local gcloud stub, once with the create succeeding and once with it failing so the update runs, emits create and update calls for compute-earnings-reactions only, each carrying --task-timeout 19800, --max-retries 0, --memory 2Gi and --cpu 1 (on main the create passes 1800, --max-retries 1 and 1Gi, and the update passes 1800 with neither --max-retries nor --memory)"
  - "tests/gcp/test_earnings_sunday_chain.py::test_consumers_start_after_the_reaction_execution passes: gcp.earnings_sunday_chain.main() with a fake Cloud Run client and a fake Eastern clock on Sunday 2026-11-22 starts compute-earnings-reactions at 19:30 and, with its execution completing at 20:40 (the 70-minute peak), starts earnings-long-watchlist, refresh-earnings-views, earnings-sweep with args ['--options-insights'] and premarket-brief with env BRIEF_TRIGGERED_BY=cloud-scheduler:earnings-sunday-chain in that order, each only after its predecessor's execution completed and none before 19:45, 20:00, 20:30 and 21:00 ET respectively; with the reaction completing at 19:38 the four start at 19:45, 20:00, 20:30 and 21:00; a failed consumer does not stop the next one and main() returns 1; a reaction still running at 22:30 ET is logged as reactions_unfinished, the four still start, and main() returns 1; on a Monday main() returns 2 and starts nothing (the module does not exist on main)"
  - "tests/gcp/test_deploy_reachability.py::test_sunday_chain_replaces_the_five_sunday_entries passes: deploy_schedulers under the gcloud stub, with the earnings-sunday-chain job present, creates and reads back the earnings-sunday-chain scheduler (30 19 * * 0, America/New_York, target job earnings-sunday-chain, ENABLED) before it deletes weekly-earnings-refresh-reactions, earnings-long-watchlist-sunday, refresh-earnings-views-weekly, earnings-sweep-sunday and premarket-brief-sunday; with the job absent it creates no chain scheduler, deletes none of the five and counts a scheduler failure; with the job present but the chain scheduler's create failing, and again with its readback differing (another schedule, time zone, target or state), it deletes none of the five, counts a scheduler failure, and deploy_schedulers returns nonzero; in both runs it neither creates, updates nor deletes daily-earnings-refresh-history or daily-earnings-refresh-reactions; and test_every_schedule_target_is_created_by_some_deploy_function passes with earnings-sunday-chain created by deploy_fetchers (on main deploy_schedulers creates all seven of these entries when they are absent)"
  - "tests/gcp/test_deploy_reachability.py::test_retire_weekday_earnings_target passes: ./gcp/deploy.sh retire-weekday-earnings under the gcloud stub deletes daily-earnings-refresh-history and daily-earnings-refresh-reactions, reads each back as NOT_FOUND, builds no image, touches no other scheduler or job, and exits non-zero when either delete fails (the target does not exist on main)"
  - "make test passes on the PR head; the generated inventory blocks are re-rendered with scripts/maintenance/doc_inventory.py and tests/scripts/test_check_generated_docs.py passes; the cases changed in tests/gcp/test_deploy_reachability.py, tests/scripts/test_doc_inventory.py and tests/scripts/test_verify_docs_against_live.py that pinned a retired scheduler are listed in the PR body each with the line it pinned"
  - "The PR body's Capacity section gives the reaction run's ticker counts and durations read through gcloud on the day the PR opens (the per-run log lines and the executions list, each pasted with its read time), the stop rule's failure bound in seconds, the chain's wall-clock at the measured consumer durations, and the cost a run and a month of the reaction job and the chain"
  - "02-FEATURE-CATALOG FEAT-DEPLOY-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the implementation-source notes of 03-SITE-TRACEABILITY.md hold a (FEAT-DEPLOY-001, component) row for each of the three declared components that begins with the current source hash (a row an earlier change left is extended: the new hash and this change's prose first, then 'Earlier:' and the earlier prose unchanged), docs/review-evidence/site-source-snapshot.json is regenerated and scripts/maintenance/doc_source_snapshot.py verify accepts it, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing that origin/main does not, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: null
---

# Earnings reactions: a bounded run, a 19,800 s timeout, the Sunday consumers after it, and the weekday runs retired (spec C)

## Approval

Approved 2026-11-17. The owner wrote "Overcome all blockers" on 2026-11-17, and this spec is the companion that the approved `docs/superpowers/specs/2026-11-16-feat-data-001-spy-qqq-iwm-only-r2.md` (r2) already names as required: its "Split and separate specs" item C and its Close-out step 1. PR #2047's body names the same companion ("spec C (weekday earnings schedulers retired, `compute-earnings-reactions` timeout at least 16,800 s)").

## Where this comes from, and what this spec takes

- **r2, Split item C (FEAT-DEPLOY-001)** lists: the unread job variables, `fetch-watched-tickers`, `intraday-bulk-backfill`, the weekday earnings schedulers, the reaction job's timeout ("at least 4 times its peak run, about 16,800 s"), the four Sunday consumers started after the reaction execution, and #1963. This spec takes the four items that concern the reaction job: the timeout, the weekday retirement, the Sunday ordering, and the #2060 hold. The other items are not in it (Non-goals) and need their own spec before r2's Close-out step 1.
- **Issue #2060** (open): #2047 gives `compute-earnings-reactions` one AlphaVantage `SPLITS` call per ticker before anything shows the ticker can produce a row, each with `timeout=30` and no early stop, and the run writes in one upsert at its end. A transport brownout costs about 30 s per ticker, so about 60 tickers reach the 1,800 s task timeout and the run loses every row. Its three fix options: (1) call `fetch_splits` lazily; (2) stop after N consecutive transport failures and name the remaining tickers unavailable; (3) make the deploy order mechanical. Until one lands: no `./gcp/deploy.sh fetchers` from a main that contains #2047 before spec C is deployed.
- **The two comments on #2060 (2026-11-17)**: `gcp/deploy.sh` passes `--task-timeout 1800` on both the create and the update path of `deploy_compute_earnings_reactions`, so raising the live timeout alone would be reset by the next deploy; the safe path must cover both branches, the coordinated scheduler and ticker transition, and completion-ordered Sunday consumers, then a live readback.
- **The FEAT-ID.** r2 and the no-adjusted spec (`docs/superpowers/specs/2026-11-16-feat-data-001-no-adjusted-prices-r2.md`, "#1977's spec C (FEAT-DEPLOY-001)") name this spec FEAT-DEPLOY-001, and the gate refuses a change to `gcp/deploy.sh` on any other FEAT's branch (`DEPLOY_FEAT` and `DEPLOY_FILE`, `scripts/gate/spec_gate.py:1118-1119`, enforced at `:4879-4882`; read). The reaction job's code change rides in the same PR, which the gate allows, so the code and the timeout always deploy together.

## Problem

### 1. The live job and the schedulers (read 2026-11-17, read only)

`env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud run jobs describe compute-earnings-reactions --region=us-east1`:

- `generation: 38`, `run.googleapis.com/lastUpdatedTime: '2026-11-17T12:41:13.719313Z'`, lastModifier `claude-web@adept-mountain-474619-d4.iam.gserviceaccount.com`
- `timeoutSeconds: '1800'`, `maxRetries: 0`, `taskCount: 1`, `cpu: '1'`, `memory: 2Gi`, `execution-environment: gen2`
- image `us-east1-docker.pkg.dev/adept-mountain-474619-d4/trading/trading-system@sha256:1ffd80ad22b0ef22aa3d6e2a1a5f40de4eff3f1715550bf8e4835b245aad40bf`, command `python -m gcp.fetchers.compute_earnings_reactions`, service account `trading-runner@adept-mountain-474619-d4.iam.gserviceaccount.com`
- `latestCreatedExecution`: `compute-earnings-reactions-m5s8z`, `EXECUTION_SUCCEEDED`, created `2026-11-17T00:30:03.904289Z`, completed `2026-11-17T00:33:15.652131Z`

The second #2060 comment found the same generation, timeout, retries and image, and that this image's reaction writer has no `fetch_splits`: the deployed job is not running #2047.

`env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud scheduler jobs list --location=us-east1`, the earnings and Sunday rows (name, schedule, time zone, state, last attempt):

```
daily-earnings-refresh-calendar     0 19 * * 1-5   America/New_York  ENABLED  2026-11-17T00:00:13.098020Z
daily-earnings-refresh-history      15 19 * * 1-5  America/New_York  ENABLED  2026-11-17T00:15:04.606742Z
daily-earnings-refresh-reactions    30 19 * * 1-5  America/New_York  ENABLED  2026-11-17T00:30:03.759859Z
weekly-earnings-refresh-calendar    0 19 * * 0     America/New_York  ENABLED  2026-11-16T00:00:29.117833Z
weekly-earnings-refresh-history     15 19 * * 0    America/New_York  ENABLED  2026-11-16T00:15:06.823265Z
weekly-earnings-refresh-reactions   30 19 * * 0    America/New_York  ENABLED  2026-11-16T00:30:03.168358Z
earnings-long-watchlist-sunday      45 19 * * 0    America/New_York  ENABLED  2026-11-16T00:45:04.277909Z
refresh-earnings-views-weekly       0 20 * * 0     America/New_York  ENABLED  2026-11-16T01:00:13.358672Z
earnings-sweep-sunday               30 20 * * 0    America/New_York  ENABLED  2026-11-16T01:30:02.149330Z
premarket-brief-sunday              0 21 * * 0     America/New_York  ENABLED  2026-11-16T02:00:03.982171Z
```

`gcloud scheduler jobs describe` of the two reaction entries and the two history entries: `httpMethod: POST` to `.../jobs/compute-earnings-reactions:run` (and `fetch-earnings-history:run`), no body, `attemptDeadline: 180s`, `retryConfig.maxRetryDuration: 0s`.

### 2. The repository

- `deploy_compute_earnings_reactions` (`gcp/deploy.sh:3001-3023`): the create passes `--memory 1Gi --cpu 1 --max-retries 1 --task-timeout 1800`; the update passes `--task-timeout 1800` and no `--memory` or `--max-retries`. The live job holds 2Gi and 0 retries, so the create and update paths do not converge on the live values (REQ-DEPLOY-001), and every deploy resets the timeout to 1,800 s.
- `deploy_schedulers` (`gcp/deploy.sh:4488`) declares the weekday and Sunday entries at `:4827-4859` and `premarket-brief-sunday` at `:4508`. `_schedule` (`:4101-4111`) only creates a missing entry: an entry removed from the file stays live until something deletes it. `_unschedule` (`:4160-4176`) and `_schedule_verified` (`:4183`) are the existing retire-after-verify pair (Codex on #1004).
- `populate_for_tickers` (`gcp/fetchers/compute_earnings_reactions.py:772-994`, on main d35d9ce2): for each ticker, `fetch_splits` (`:616-664`, `requests.get(..., timeout=30)` at `:635`) runs first (`:842`), paced at `AlphaVantageConfig().delay_between_calls` (`:833`, 0.4 s at the 150 RPM local allocation, `lib/config.py:122-123`), before the ticker's events are checked for timing, session or bars. All rows are upserted once, after the last ticker (`:987`). `main()` (`:1096-1159`) returns 1 only when every ticker's SPLITS failed.

### 3. How many tickers a run takes, and what a brownout costs

- Run sizes, from the job's own log line `compute_earnings_reactions: N tickers (after window-aware skip)` (`gcloud logging read`, 27 runs, 2026-10-18 to 2026-11-17 UTC): weekday runs 3 to 320 tickers (320 on the evening of 2026-11-05 ET); the three Sunday runs 132, 278 and 214.
- Reporters a weekday, from `earnings_calendar` joined to the tickers with a non-zero `reported_eps` in `earnings_history`, the last 365 days (`db-query-vzmt8`): 158 weekdays with a reporter, median 27, 95th percentile 246.7, max 379. Every weekday run also takes the 17 eligible tickers that have never had a reaction row (of 2,052 eligible, same execution), so the weekday peak is about 396 tickers.
- Durations without SPLITS (`gcloud run jobs executions list`, 40 executions, 2026-10-02 to 2026-11-17): 17 s to 12 min 55 s (`compute-earnings-reactions-dmdcc`, 775 s), every one succeeded.
- A brownout at 30 s a request plus 0.4 s pacing reaches 1,800 s at 59 tickers. 17 of the 27 runs above took more than 59 tickers. On today's schedule #2047's code would put most evenings one brownout away from a run that loses every row.
- After r2's implementation the run is Sunday only and fetches each reporter's daily series (r2 plan Task 10: `fetch_daily_series`, `timeout=60`) and its split list: median about 180 reporters, at most about 1,500, peak about 70 minutes (r2 Capacity, estimate). A brownout there costs about 60 s a reporter, so 16,800 s is reached at about 278 reporters. A timeout alone does not bound it.

### 4. The Sunday consumers start on their own clocks

The four Sunday jobs that read the reactions or what is built from them start at fixed times (r2 Design 8): `earnings-long-watchlist` 19:45, `refresh-earnings-views` 20:00, `earnings-sweep` 20:30, `premarket-brief` 21:00. Their recent Sunday executions (`executions list`, read): long watchlist 11 to 26 s, views 38 to 52 s, sweep 9 min 35 s to 10 min 57 s, brief 36 s to 1 min 50 s. The Sunday reaction runs took 4 min 50 s (2026-11-15 ET), 6 min 2 s (2026-10-25) and about 12 min 15 s (2026-10-18), so the 2026-10-18 run finished less than 3 minutes before the 19:45 job; #2047's split calls add about 1.4 s a ticker (estimate), and r2's peak is about 70 minutes, past 20:30.

## Non-goals

- r2 Split C's other items: removing `EARNINGS_WINDOW_DAYS`, `BACKFILL_ALL_HISTORY` and the other variables r2 leaves unread, retiring `fetch-watched-tickers` and `intraday-bulk-backfill`, settling #1963. None touches the reaction job or the #2060 hold, and each depends on r2's implementation making the variables unread. They need their own FEAT-DEPLOY-001 spec before r2's Close-out step 1.
- Per-ticker commits of the reaction rows. r2's Task 10 makes `populate_for_tickers` upsert each ticker before the next; on today's database windows this spec bounds the run instead (Design 2 and Capacity). Whichever lands second keeps both.
- The order of `fetch-earnings-history` (19:15, 65 to 89 minutes on each of the last twelve evenings, `executions list`) against the 19:30 reaction run. It overlaps today and is not changed here.
- No change to what a reaction contains, to the split check, to the price basis, or to any API response.
- The weekday calendar run (`daily-earnings-refresh-calendar`) and the Sunday calendar and history runs stay as they are (r2 Design 8).
- Moving the four consumers' crons later instead of chaining them (r2 Design 8 recommends against it).

## Approaches considered

1. **#2060 option 1 alone (lazy SPLITS).** Saves the call for a ticker that cannot produce a row, but a brownout still costs 30 s for every ticker that can; at today's weekday peak of about 396 tickers that is about 12,000 s. Not enough alone.
2. **#2060 option 2 alone (a stop after N consecutive transport failures).** Bounds a solid brownout, but a reply pattern that fails every other request never trips a consecutive counter: at the r2 Sunday peak of about 1,500 reporters it costs about 750 x 60 s. A total count is needed beside it.
3. **#2060 option 3 alone (a mechanical deploy order).** Keeps #2047's code off the job until the timeout is raised, but a raised timeout does not bound a brownout at r2's scope (about 278 reporters fill 16,800 s).
4. **Chosen: options 1 and 2 combined, with a total-failure bound beside the consecutive one, and the code shipped in the same PR as the timeout on both deploy branches.** Lazy SPLITS removes the calls that cannot help; the stop bounds what a brownout can cost (at most 10 failed requests in a run); and because `deploy_compute_earnings_reactions` sets the image and the timeout in one call, any `fetchers` deploy from a main containing this change carries both. That is option 3's effect without a new guard.

For the Sunday order:

5. **Chosen: one chain job (`earnings-sunday-chain`) fired at 19:30 Sunday that runs the reaction job and then the four consumers, each after its predecessor's execution has completed and not before its present time.** It uses the Cloud Run client the repo already uses (`gcp/discord_interactions/main.py:229-273`), runs as `trading-runner@`, which holds `roles/run.developer` (`gcloud projects get-iam-policy`, read 2026-11-17), whose permissions include `run.jobs.run`, `run.jobs.runWithOverrides`, `run.executions.get` and `run.operations.get` (`gcloud iam roles describe roles/run.developer`, read), so no IAM change.
6. A start check in each consumer that waits for that evening's reaction execution. Four code changes, four jobs idling while they wait, and each needs the reaction job's execution list. Rejected.
7. Cloud Workflows or an Eventarc trigger on execution completion. A new service and new IAM for one Sunday sequence; nothing in the repo uses either. Rejected.

For the weekday retirement:

8. **Chosen: `deploy_schedulers` stops declaring the two weekday entries, and a one-shot target `./gcp/deploy.sh retire-weekday-earnings` deletes them, run by the owner in the same session as r2's Close-out step 1.** Because `_schedule` never deletes, removing the two lines changes nothing live, and no routine `schedulers` or `all` deploy can retire them early.
9. `_unschedule` of the two inside `deploy_schedulers` (the #1004 pattern). The next routine `schedulers` deploy would retire them, possibly before r2's weekly history change is live, while only the weekday run captures last week's quarters (r2 Close-out step 1). Rejected.
10. Retire them now. Same loss as 9, from today. Rejected.

## Design

### 1. Lazy SPLITS (`gcp/fetchers/compute_earnings_reactions.py`)

- `populate_for_tickers` requests a ticker's split list at the first of its events that reaches the split check: event identity and timing known, report date an exchange session, and a daily window that is non-empty after the future-date and completed-session filters (today the check at `:896-897`). The `Splits` it returns is held for that ticker's remaining events, as today.
- A ticker none of whose events reaches that point makes no SPLITS request; each event is skipped for the reason main gives it today (`unknown_event_timing`, `invalid_event_identity`, `report_date_is_not_exchange_session`, `non_exchange_daily_session`, `insufficient_surrounding_daily_bars`).
- The daily windows are read before the split list (one query per ticker, as today), so a ticker whose SPLITS later fails has had its window read; that query is the existing one.
- Pacing: the sleep of `delay_between_calls` comes before every SPLITS request but the run's first, not before every ticker but the first.
- `counts['split_tickers']` counts requests made. A run that needed no split list (every ticker skipped earlier) has `split_tickers == 0` and is not an all-failed run.

### 2. The vendor-failure stop

- A small module-level class, `VendorRequestBudget` (consecutive limit 3, total limit 10, both module constants), records the outcome of each vendor request the run makes. It counts a failure only when the reason is a request failure: `SplitsUnavailable` whose reason starts `request_failed` (`_request_failure`, `:607-613`: an HTTP status error or a transport exception such as a connect or read timeout). A parsed vendor refusal (`Information`, `Note`, `Error Message`) or an unparseable reply is that ticker's own failure, returns in one round trip, and is not counted (CLAUDE.md 3.7: it is still named per event, as today). A success resets the consecutive count.
- When the budget is spent, the run makes no further vendor request. Every event of every ticker not yet requested is refused by name with the existing receipt reason `split_status_unavailable`, those tickers are counted in `splits_unavailable`, and the run logs one line `vendor_requests_stopped consecutive=<n> total=<m> remaining=<k> tickers=<list>` at ERROR. The rows already computed are still upserted.
- Exit code: `main()` returns 1 when the budget was spent, and keeps today's rules otherwise (1 when every requested ticker failed or the key is missing, else 0). A stopped run is a failed run, not a partial success.
- r2's implementation adds a second vendor request per ticker, the daily series. Its failures of the same class (an HTTP or transport error, `DailySeriesUnavailable` built the same way) are recorded in the same budget, so the bound holds for both requests. If this branch is cut after r2's implementation is on main, both tests drive its per-ticker body with `fetch_daily_series` stubbed in place of the database windows and keep every assertion; if it is cut before, r2's rebase keeps lazy SPLITS and the shared budget, and its PR body says so.

### 3. The reaction job's sizing (`gcp/deploy.sh`, both branches)

- `deploy_compute_earnings_reactions`: the create and the update both pass `--memory 2Gi --cpu 1 --max-retries 0 --task-timeout 19800`. 2Gi and 0 retries are the live values (Problem 1), so this changes only the timeout live and makes a fresh create match the live job.
- 19,800 s (5 h 30 min) is at least the 16,800 s r2 and #2047 name, and it is 4 times the bounded worst case at r2's scope: r2's 70-minute peak (4,200 s) plus the stop's bound of 10 failed requests at about 60.4 s (604 s), 4,804 s, times 4 is 19,216 s, rounded up to the half hour (CLAUDE.md rule 0.5). Cloud Run charges for the run, not the cap.
- The comment above the function is replaced: the job makes AlphaVantage calls now, and the numbers are the ones in Capacity.

### 4. The Sunday chain (`gcp/earnings_sunday_chain.py`, job `earnings-sunday-chain`)

- Entry point `python -m gcp.earnings_sunday_chain`. Five steps, in order, as module constants:

| Step | Job | Overrides | Not before (ET) |
|---|---|---|---|
| 1 | `compute-earnings-reactions` | none | 19:30 |
| 2 | `earnings-long-watchlist` | none | 19:45 |
| 3 | `refresh-earnings-views` | none (the job's default `--mode=weekly`, `gcp/deploy.sh:3048`) | 20:00 |
| 4 | `earnings-sweep` | args `['--options-insights']` (as `earnings-sweep-sunday` passes today, `:4850-4852`) | 20:30 |
| 5 | `premarket-brief` | env `BRIEF_TRIGGERED_BY=cloud-scheduler:earnings-sunday-chain` (the brief reads a `cloud-scheduler` prefix as a scheduled run, `gcp/premarket_brief.py:3853-3855`) | 21:00 |

- Each step waits until its not-before time on the run's Eastern date (through `lib.eastern_time`, CLAUDE.md 3.9), starts the job with `run_v2.JobsClient().run_job(request=RunJobRequest(name=..., overrides=...))`, and waits for that execution to complete. When the reaction finishes on time, every consumer starts at its present time; when it runs long, each starts after its predecessor. A step's outcome is read from the execution (succeeded or failed), and each step logs `step=<job> execution=<name> not_before=<ET> started=<ET> completed=<ET> outcome=<succeeded|failed|unfinished|not_started>`.
- A failed step does not stop the next one: today the five start independently, so a failed reaction run never kept the brief from running, and the chain keeps that. A step the API refuses to start is `not_started` with the exception class, and the next step still runs.
- **The reaction wait ends at 22:30 ET.** If step 1's execution has not completed by then, the chain logs `reactions_unfinished`, stops waiting (the execution keeps running under its own timeout) and starts the consumers. At their task timeouts (600, 1,200 and 1,800 s, `gcp/deploy.sh`) the brief then starts by 23:30, so it still builds Sunday's weekly brief: the brief chooses its weekly content by the weekday of its analysis date (`gcp/premarket_brief.py:1554-1557`, read, not executed). Waiting with no limit could start it after midnight as a Monday brief, beside the 08:30 Monday run.
- Exit code: 0 when all five steps succeeded, 1 otherwise. On a day that is not Sunday in Eastern time it exits 2 before starting anything; `--allow-any-day` lets a replay run it on purpose.
- Deploy: `deploy_earnings_sunday_chain` in `gcp/deploy.sh`, called from `deploy_fetchers` beside `deploy_compute_earnings_reactions`, create and update both `--memory 512Mi --cpu 1 --max-retries 0 --task-timeout 18000 --service-account ${SA_EMAIL}`. 18,000 s covers the reaction wait (at most 10,800 s from 19:30) plus the four consumers' task timeouts (5,400 s) plus five execution starts. It takes no database secret.

### 5. The schedulers (`gcp/deploy.sh`)

- `deploy_schedulers`, where the Sunday entries are declared today: when `gcloud run jobs describe earnings-sunday-chain` succeeds, `_schedule_verified "earnings-sunday-chain" "30 19 * * 0" "earnings-sunday-chain"` creates or updates the entry and reads it back; only after that read-back passes, `_unschedule` deletes `weekly-earnings-refresh-reactions`, `earnings-long-watchlist-sunday`, `refresh-earnings-views-weekly`, `earnings-sweep-sunday` and `premarket-brief-sunday`. When the job is absent or the read-back fails, nothing is deleted, the reason is printed, and `SCHEDULER_FAILURES` counts it, so a `schedulers` deploy run before the `fetchers` deploy keeps the five entries and fails loudly. The five `_schedule` lines go, so nothing re-creates them.
- The two weekday lines (`daily-earnings-refresh-history`, `daily-earnings-refresh-reactions`) are removed from `deploy_schedulers` and nothing there deletes them: live, they keep firing until the next step.
- `retire-weekday-earnings` is a new dispatcher arm (no image build, `_PIN_AFTER=0` like `schedulers`) that runs `_unschedule` on the two weekday names, then `gcloud scheduler jobs describe` of each and requires NOT_FOUND, and exits non-zero on any failure. It is run only in Close-out step 4.
- The comment block at `:4805-4826` is rewritten to say what runs now: the weekday chain is calendar, then history, then reactions until step 4; the Sunday chain is calendar and history on their crons, then `earnings-sunday-chain` at 19:30.

### 6. Order, and what lifts the #2060 hold

- With this change on main, a `./gcp/deploy.sh fetchers` deploys the reaction job's image with lazy SPLITS and the stop, and sets its timeout to 19,800 s, in the one `gcloud run jobs update` call. A weekday run is then bounded on today's schedule (Capacity: about 27 minutes at the measured peak with the worst failure pattern). So the hold on `fetchers` can be lifted at Close-out step 1. The no-adjusted spec's Order section says its split check deploys only after the weekday retirement and the timeout; its own Close-out step 1 still waits for both, and this spec does not change that. Whether a routine `fetchers` deploy may carry the split check before the weekday retirement is Decision 1.
- If r2's implementation is on main when Close-out step 1 runs, that `fetchers` deploy is r2's Close-out step 1 and waits for r2's other preconditions (spec D, and the rest of r2's Split C).
- The weekday retirement (Close-out step 4) runs in the same session as r2's Close-out step 1, after its `fetchers` deploy, never before: until r2's weekly history change is live, only the weekday run captures last week's quarters (r2 Close-out step 1).
- The chain does not depend on r2 and can be swapped in at Close-out step 2.

### 7. Site traceability

The declared components and what each note says (backend source and local tests only, rollout pending):

- `CATALYSTS-01`: the reaction job requests a ticker's splits only for an event it can check, stops its vendor requests after 3 consecutive or 10 request failures and names the rest unavailable, and runs under a 19,800 s timeout; the earnings history this page shows comes from those rows.
- `CATALYSTS-04`: on Sunday the views this page's timeline reads are refreshed by `earnings-sunday-chain` after that evening's reaction execution.
- `DASHBOARD-01`: the Sunday brief is started by `earnings-sunday-chain` at 21:00 or after the sweep, whichever is later; its existing FEAT-DEPLOY-001 note is extended with "Earlier:".

### 8. Capacity (CLAUDE.md rule 0)

| | Volume | Velocity | Wall-clock | Bound |
|---|---|---|---|---|
| weekday reaction run, today's code shape | at most about 396 tickers (379 reporters, max of 158 weekdays, plus 17 never reacted, `db-query-vzmt8`); measured 3 to 320 a run | at most 1 SPLITS request a ticker that reaches a checkable window, paced 0.4 s; 1 window query a ticker (unchanged); 1 upsert a run | measured 17 s to 775 s without SPLITS; plus about 1.4 s a request (0.4 s pacing plus latency, the no-adjusted spec's estimate, not measured): about 554 s at 396 tickers, so about 22 minutes at the peak | the stop adds at most 10 failed requests at about 30.4 s, 304 s: about 27 minutes worst case, against 19,800 s |
| Sunday reaction run after r2 | about 180 reporters median, about 1,500 at most (r2 Capacity) | 2 vendor requests a reporter (r2) | about 70 minutes peak (r2, estimate) | 604 s of failures at most; 4 x 4,804 s = 19,216 s, so 19,800 s |
| a brownout, without this spec | every remaining ticker | 1 request each at 30 s (60 s after r2) | 1,800 s at 59 tickers; 16,800 s at about 278 reporters after r2 | none: the run loses every row (#2060) |
| `earnings-sunday-chain` | 5 job executions a Sunday | 5 `run_job` calls and their operation polls | the longest measured run of each consumer, about 14 minutes in all; on time the chain runs 19:30 to about 21:02 (about 92 minutes, mostly waiting for the not-before times) | 18,000 s task timeout; reaction wait ends 22:30 |

- Cost: the reaction job at 1 vCPU and 2 GiB, about $0.000022 a second (list prices $0.000018 a vCPU-second and $0.000002 a GiB-second, not re-read): the measured longest run, 775 s, about $0.017; the weekday peak above, about $0.03; six runs a week, under $0.80 a month. The chain at 1 vCPU and 0.5 GiB idles about 92 minutes a Sunday: about $0.11 a run, about $0.46 a month. The stop changes no steady-state cost. No new SQL statement on any path.
- Vendor: the weekday peak adds about 396 SPLITS requests a run against the account's 600 RPM purchased allowance, paced locally at 150 RPM (`lib/config.py:122-123`); per-call billing not checked.

## Decisions for the owner

Each is written into the Design as recommended.

1. **Lift the `fetchers` hold at Close-out step 1, before the weekday retirement.** With lazy SPLITS, the stop and the 19,800 s timeout, a weekday run is bounded at about 27 minutes in the worst failure pattern. Alternative: keep the hold until r2's Close-out step 1, as the no-adjusted spec's Order section reads ("the split check is deployed only after both") and as the second #2060 comment lists, so every fetcher change waits for r2 and spec D.
2. **The chain stops waiting for the reaction at 22:30 ET** so the brief still runs on Sunday. Alternative: wait for the reaction with no limit (r2's "only after ... has completed" read strictly); a reaction run past about 23:45 would then start the brief after midnight.
3. **Stop limits: 3 consecutive or 10 request failures in a run.** Alternative: a higher total (for example 25) keeps more of a run in a patchy outage at the price of up to 25 x 60.4 s after r2.
4. **Timeout 19,800 s** rather than 16,800 s, from the 4 times rule over the bounded worst case (Design 3). Alternative: 16,800 s, the figure r2 and #2047 give.
5. **The create path matches the live 2Gi and 0 retries** (Design 3). Alternative: leave the create path's 1Gi and 1 retry, which a fresh project would get.

## Close-out (after the merge, each step on the owner's yes)

None runs from the implementation PR and none is a `done_when` box. Each step is recorded as a comment on the implementation PR with its output. Every command runs from a checkout of `main`, with `gcloud` prefixed `env -u CLOUDSDK_AUTH_ACCESS_TOKEN`.

1. **Deploy the reaction job and the chain job** (Decision 1): `./gcp/deploy.sh fetchers`.
   - Check: `gcloud run jobs describe compute-earnings-reactions --region=us-east1` reads `timeoutSeconds: '19800'`, `maxRetries: 0`, `memory: 2Gi`, `cpu: '1'` and the build's image digest; `gcloud run jobs describe earnings-sunday-chain --region=us-east1` exists with `timeoutSeconds: '18000'` and `maxRetries: 0`.
   - The next weekday reaction execution succeeds or fails for a named reason, and its log carries `splits_unavailable=<n> of <m> tickers` with `m` no larger than its ticker count; any `vendor_requests_stopped` line is posted on #2060.
   - Then comment on #2060 that the hold is lifted, with these readbacks.
2. **Swap the Sunday entries**: `./gcp/deploy.sh schedulers`.
   - Check: `gcloud scheduler jobs describe earnings-sunday-chain --location=us-east1` reads `30 19 * * 0`, `America/New_York`, `ENABLED`, target `earnings-sunday-chain:run`; `gcloud scheduler jobs list --location=us-east1` lists none of the five retired names and still lists `daily-earnings-refresh-history`, `daily-earnings-refresh-reactions`, `weekly-earnings-refresh-calendar` and `weekly-earnings-refresh-history`.
3. **The first Sunday after step 2.** `gcloud run jobs executions list` for `compute-earnings-reactions`, `earnings-long-watchlist`, `refresh-earnings-views`, `earnings-sweep` and `premarket-brief`: each Sunday execution starts after its predecessor's completion time and at or after its not-before time, and the chain's execution log has five `step=` lines. This is r2's acceptance case read on a live Sunday; its 70-minute case is the hermetic test of done_when 4.
4. **Retire the weekday runs, in the session of r2's Close-out step 1, after its `fetchers` deploy**: `./gcp/deploy.sh retire-weekday-earnings`.
   - Check: `gcloud scheduler jobs describe daily-earnings-refresh-history --location=us-east1` and the same for `daily-earnings-refresh-reactions` each answer NOT_FOUND; `daily-earnings-refresh-calendar` is still listed and ENABLED.
5. **Records**: close #2060 with the readbacks of steps 1 and 4; note on r2's implementation PR and on #2047 that spec C's parts of their preconditions are live; then, on a `docs/` branch, set the plan's `status: done`.

## Risks

- **The chain is one trigger for five Sunday jobs.** If it fails to start, none of them runs that Sunday. The swap happens only after the chain job exists and its entry reads back (done_when 5), the chain exits non-zero on any failed step, and step 3 reads the first live Sunday.
- **The docs and the live schedulers differ between the merge and step 4.** The inventory rendered from `gcp/deploy.sh` no longer lists the two weekday entries while they still fire; `scripts/verify_docs_against_live.py` reports them as live only for that interval. `gcp/audit_infra_drift.py` checks only orphans and paused entries (`:173-226`, read), and both entries stay ENABLED with their target job present.
- **A patchy vendor stops a run early.** Ten request failures end it; the rest are named unavailable and the run fails. On today's code a missed ticker's newest reaction waits for its next report or a `--force` run (the weekday scope skips tickers that already have a row, `:1068-1093`); after r2 the next Sunday selects it again within 60 days.
- **A slow but successful reply is not a failure.** At about 29.9 s a reply for each of 396 tickers a run would last about 12,000 s plus the database work, inside 19,800 s; after r2 a slow vendor across 1,500 reporters is not bounded by this spec, and r2's per-ticker commits keep each finished ticker.
- **`requests`' timeout bounds each read, not the whole reply**, so a reply that trickles bytes can take longer than 30 s. Not measured.
- **The weekday runs keep firing until r2's Close-out step 1.** Each now carries the split calls (Decision 1).

## What was not verified

- The latency of a SPLITS request: the 1.4 s a request is the no-adjusted spec's estimate.
- Whether `op.result()` of `run_job` raises on a failed execution or returns it with a failed count; the chain reads the execution's counts either way, and the hermetic test covers both.
- How many tickers a run would skip under lazy SPLITS on today's data: not measured; the 17 never-reacted tickers all have daily rows (`db-query-vzmt8`), so they may still request.
- The 24-hour ceiling on a Cloud Run job's task timeout is from the Cloud Run documentation, not re-read.
- The brief's analysis date after midnight was read in `gcp/premarket_brief.py:1554-1557`, not executed.
- Whether the four consumers read anything else the reaction run writes, beyond r2 Design 8's citations: not checked file by file.
