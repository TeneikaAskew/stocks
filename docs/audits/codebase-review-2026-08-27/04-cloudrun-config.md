# 04 — Cloud Run Config Audit (`gcp/deploy.sh`, all 3,981 lines)

2 services, 69 job-producing `deploy_*` functions, 1 scheduler block
(49 distinct targets). `git blame` confirms every secret-handling
finding predates this session — existing production risk, not new
regressions.

**Result: 3 critical / 3 high / 3 medium.**

## CRITICAL

### K1 — Scheduler `gamma-levels-daily` targets a job `deploy.sh` never creates
`gcp/deploy.sh:3326` schedules `p2-build-gamma-levels`; no
`gcloud run jobs create` for that name exists anywhere in the repo, and
there is no `deploy_p2_build_gamma_levels()` function. The source module
`gcp/research/p2_build_gamma_levels.py` has a real `main()`.

The agent concluded: *"every weekday-night trigger calls the Jobs `:run`
API against a job that doesn't exist → 404 … `gamma_levels_eod` never
gets written."*

> **VERIFIED BY CLAUDE — THE STATED CONSEQUENCE IS WRONG.**
> `gcloud run jobs list` shows **`p2-build-gamma-levels` exists** and is
> succeeding every weekday (last run 2026-08-27 02:30). It was created
> by hand outside `deploy.sh`. Nothing is 404-ing and `gamma_levels_eod`
> is being written — verified: zero `gamma_balance_price` nulls for
> 2026-08-24..27 across IWM/SPY/QQQ, and the last execution ran the
> current `:research` digest (`sha256:b7288ec5…`), i.e. this week's
> gamma fix **is** live in the nightly writer.
>
> **The real finding survives in a different form:** `./gcp/deploy.sh`
> cannot resize, re-secret, or repoint this job, and a rebuilt
> environment loses it silently. Disaster-recovery/manageability gap,
> not an outage. Re-rated from "silent outage" to **HIGH**. See report
> 08 D2 for the same finding reached independently from the GCP side.

### K2 — `DISCORD_BOT_TOKEN` and `DISCORD_PUBLIC_KEY` via `--set-env-vars` on a public service
`deploy_discord_interactions`, `gcp/deploy.sh:513,532-533,556`. This
service is deployed `--allow-unauthenticated` (:551).
`DISCORD_BOT_TOKEN` grants full control of the bot identity, and anyone
with `roles/run.viewer` can read it in plaintext via
`gcloud run services describe`; it also lands in the Cloud Audit Log for
every deploy. Every *other* secret in the file uses `_build_secret_flag`
/ `DB_SECRET_FLAG` (:397-457) — this function was never migrated.
Ironically it correctly implements `--min-instances 1` +
`--no-cpu-throttling` (:536-548).
**Fix:** the secrets already exist in Secret Manager (setup doc at
:497-500) — switch to
`--set-secrets=DISCORD_PUBLIC_KEY=discord-public-key:latest,DISCORD_BOT_TOKEN=discord-bot-token:latest`.
(`DISCORD_APP_ID` is a public identifier — fine as-is.)

### K3 — `deploy_backfill_ticker`, `deploy_validate_brief`, `deploy_backtest` are dead code
`gcp/deploy.sh:576,602,628` — the only job-producing functions with
**zero** call sites: not in the case table, not in `all`, not
cross-called. Not deprecated (unlike
`deploy_p7b_classifier_DEPRECATED`, which says so). Meanwhile
`gcp/discord_interactions/main.py` dispatches these exact job names:
`:459 backfill-ticker`, `:774 validate-brief`, `:801 backtest`.
Consequence as stated: `/replay`, `/validate`, `/backtest` slash
commands 404 on any environment built purely from `./gcp/deploy.sh`.

> **VERIFIED BY CLAUDE — partially corrected.** All three jobs **exist
> live** (hand-created), so the Discord commands work today. The gap is
> the same as K1: unmanageable by the deploy script, lost on rebuild.
> Re-rated **HIGH**.
> **Fix:** `discord) build_image && deploy_discord_interactions && deploy_backfill_ticker && deploy_validate_brief && deploy_backtest ;;`

## HIGH

- **K4 — `ADMIN_TOKEN` via `--set-env-vars`** (`deploy_insight_pipeline`,
  :73,76-77,86,92). Reads the secret correctly from Secret Manager then
  plumbs the raw value through the plaintext path.
- **K5 — `EW_USER`/`EW_PASS` via `--set-env-vars`**
  (`deploy_fetch_earnings_calendar`, :1954,1957-1959,1972,1979).
  `EW_PASS` is a literal password.
- **K6 — Five jobs have no `--task-timeout`**, silently defaulting to
  Cloud Run's 600s: `fetch-news-sentiment` (:2303),
  `fetch-news-sentiment-earnings` (:2329 — most exposed,
  `MAX_TICKERS=300`), `fetch-news-sentiment-topics` (:2364),
  `fetch-economic-events` (:1928), `weekend-review` (:1317). This is the
  PR #342 (`fetch-earnings-history`) failure mode recurring; every other
  job in the file sizes its timeout explicitly. The three
  news-sentiment jobs also carry unjustified `--max-retries 1`, so a
  timeout triggers a retry that repeats the same truncation.

## MEDIUM

- **K7 — 19 `deploy_*` functions are reachable only via the bundled
  `fetchers` target**, with no standalone case entry — generalizing the
  `deploy_av_options_realtime` gap hit this week. Includes
  `deploy_av_options_realtime` (:1499) and `deploy_backtest_pipeline`
  (:2277). To fix a one-line sizing bug on any of them, the only
  dispatch path rebuilds the image and redeploys ~20 fetcher jobs.
  *(Note: `deploy_backtest_pipeline`'s entrypoint is currently
  **correct** — `scripts.run_pipeline`; the `scripts.calibrate_iwm_strat`
  mis-pin found this morning was live-only drift, already fixed, and is
  not present in the file.)*
- **K8 — Widespread unjustified non-zero `--max-retries`** (~23 jobs).
  Rule 0 default is 0, and the file demonstrates the correct pattern
  elsewhere (`indicator-correlation` :260, `regime-combo` :300,
  `fetch-top-movers` :2080 all carry a "why N is safe here" comment).
  Highest priority: **`fetch-market-data` `--max-retries 2`** (:1349) —
  combined with report 05's N+1 finding, a transient failure triggers 3
  full re-runs of a 500-800-ticker loop.
- **K9 — `update` branches inconsistently mirror `create` sizing flags**
  (e.g. `deploy_monitor` :757, `deploy_signal_monitor_eod_resolver`
  :791, `deploy_premarket_playbook_resolver` :824 pass
  timeout/memory/retries only on create). The file documents this exact
  risk at :1464-1468 — the fix wasn't applied everywhere. Determines
  whether a future correctness fix actually reaches a deployed job.

## Verified clean

- **min-instances on user-facing services:** only 2 `gcloud run deploy`
  blocks. `discord-interactions` is `--allow-unauthenticated` and
  correctly sets `--min-instances 1` with a comment citing the
  cold-start-vs-3s-deadline math. `failure-notifier` is
  `--no-allow-unauthenticated` (Pub/Sub push + OIDC), so
  `--min-instances 0` is correctly exempt.
- **BackgroundTasks:** only `discord_interactions/main.py` imports it,
  and its deploy sets `--no-cpu-throttling`.
- **`--args` quoting:** no live instances of the bug. Every value
  containing `=` already uses the `--args=` form; the space-form values
  that begin with `-` contain no `=`, which the file's own
  empirically-verified comment (:1475-1479) identifies as the actual
  trigger condition. PR #457's fix has held.
- **Memory:** zero jobs below 512Mi.
- **Scheduler targets:** all 49 cross-referenced against all 69 created
  job names — only `p2-build-gamma-levels` (K1) is unbacked by the
  script; no misspellings elsewhere.
