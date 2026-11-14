---
feat_id: FEAT-DEPLOY-001
req_ids: [REQ-DEPLOY-001]
issues: []
canvases: []
site_source_notes: [SHARED-07]
done_when:
  - "gcp/deploy.sh gains deploy_fetch_watched_tickers(): a gcloud run jobs create ... || gcloud run jobs update ... pair for the Cloud Run Job fetch-watched-tickers with --memory 512Mi --cpu 1 --max-retries 0 --task-timeout 2400, the command python,-m,gcp.fetchers.fetch_watched_tickers, the fetchers' service account and DB secret flag, and --set-env-vars \"${ENV_STRING},WATCHED_TICKERS_MAX=50,AV_BACKFILL_SLEEP_SECS=1.0\"; the update branch repeats the image, the region, --max-retries 0, the task timeout, the command, the secret flag and the env vars; the function sets no new secret, no WATCHED_TICKERS_URL and no WATCHED_TICKERS_READ_SECRET"
  - "deploy_fetchers() lists deploy_fetch_watched_tickers so the all target creates the job; the dispatch case gains the arm watched-tickers) _run build_image deploy_fetch_watched_tickers deploy_fetch_market_data deploy_fetch_earnings_history deploy_freshness_watchdog ;; (one build of main, then the ingest job and the three jobs that run the same image's fetch_market_data._run_backfill or scripts/audit_data_freshness.py code paths), and the help text names the arm"
  - "deploy_schedulers() gains _schedule \"watched-tickers-nightly\" \"45 23 * * 1-5\" \"fetch-watched-tickers\" (America/New_York through _schedule), beside the other nightly fetcher schedules"
  - "tests/gcp/test_deploy_reachability.py gains test_watched_tickers_target_deploys_the_ingest_job_and_the_jobs_sharing_its_code, asserting that the watched-tickers arm creates or updates exactly fetch-watched-tickers, fetch-market-data, fetch-earnings-history and freshness-watchdog, that both branches of deploy_fetch_watched_tickers carry --max-retries 0, --task-timeout 2400 and --command python,-m,gcp.fetchers.fetch_watched_tickers, that the function sets no WATCHED_TICKERS_URL and no WATCHED_TICKERS_READ_SECRET, and that deploy_schedulers() holds exactly the line _schedule \"watched-tickers-nightly\" \"45 23 * * 1-5\" \"fetch-watched-tickers\" (the helper passes --time-zone America/New_York, which the test reads from the helper); test_every_schedule_target_is_created_by_some_deploy_function and test_all_target_creates_every_scheduled_job_and_service stay green; bash -n gcp/deploy.sh passes"
  - "docs/product/03-SITE-TRACEABILITY.md updates its existing FEAT-DEPLOY-001 SHARED-07 row in the Implementation-source notes table (keeping its sentence) to begin source_identity_sha256=<the PR head's source identity>; describing the fetch-watched-tickers deploy function, its dispatch arm and its scheduler as the element's backend source with tests/gcp/test_deploy_reachability.py as the test, with no other byte of the document changed, and docs/review-evidence/site-source-snapshot.json is produced from that head and verifies (scripts/maintenance/doc_source_snapshot.py verify exits 0 with status identity-matched)"
  - "The FEAT-DEPLOY-001 catalog record and the PR traceability entry are updated, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing new over origin/main, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: null
---

# Deploy wiring for the fetch-watched-tickers job: deploy function, dispatch arm, nightly scheduler

## Authority and status

The FEAT-DATA-001 spec `docs/superpowers/specs/2026-11-14-feat-data-001-watched-ticker-ingest-v2.md`
(approved through stocks #1904) defines the `fetch-watched-tickers` Cloud Run Job and, in its section
"Entry point and schedule", the deploy function, the `watched-tickers` dispatch arm and the
`watched-tickers-nightly` scheduler that `gcp/deploy.sh` gains for it. Its plan (#1908) carried that
wiring as Task 9 of the FEAT-DATA-001 branch. The spec gate routes every change to `gcp/deploy.sh`
through FEAT-DEPLOY-001 (`scripts/gate/spec_gate.py`, the `DEPLOY_FILE` rule: "deploy change(s)
belong to FEAT-DEPLOY-001, not FEAT-DATA-001; the deploy surface is that capability's work"), and
every change to that file since the gate landed came through a FEAT-DEPLOY-001 pull request
(#1366, #1457, #1789, #1813, #1834). This spec therefore carries the deploy wiring of the ingest spec
word for word as FEAT-DEPLOY-001 work, so the ingest job's code PR holds no deploy change and this
PR holds nothing else. The ingest spec is superseded by its v3
(`docs/superpowers/specs/2026-11-14-feat-data-001-watched-ticker-ingest-v3.md`), whose deploy item
points at this spec instead of requiring the wiring in the ingest PR. Order: the ingest code PR merges
first; this spec's implementation merges after it, because `deploy_fetchers()` and `deploy_schedulers()`
run unconditionally under the `all)` target that `RUNBOOK.md` names as the recovery command, so the
wiring must not reach main before the module it names is in the image (Codex on #1918); only then
does the ingest spec's post-merge close-out run `./gcp/deploy.sh watched-tickers`, the manual run and
`./gcp/deploy.sh schedulers`, under the owner's authorization of 2026-11-14.

Written 2026-11-14 from that gate finding on the ingest branch. Status `approved` under the owner's
standing instruction of 2026-11-14 to work the open pull requests to completion; the content decides
nothing new, it relocates an approved section to the capability the gate assigns it to.

## Problem

`gcp/fetchers/fetch_watched_tickers.py` (the FEAT-DATA-001 ingest v2 implementation) runs as a Cloud
Run Job that nothing creates, schedules or redeploys: `gcp/deploy.sh` has no `deploy_fetch_watched_tickers`,
no `watched-tickers` arm and no `watched-tickers-nightly` schedule, and
`tests/gcp/test_deploy_reachability.py::test_every_schedule_target_is_created_by_some_deploy_function`
would fail the moment a schedule named the job without a deploy function. The ingest spec's section
"Steps" also requires the two fetch jobs that run `fetch_market_data._run_backfill` inside their own
images (`fetch-market-data`, and `fetch-earnings-history` through `gcp/fetchers/fetch_earnings_history.py:558`)
to carry the all-history union exclusion before any watched ticker exists, and the `freshness-watchdog`
job (`scripts/audit_data_freshness.py`) to carry the heartbeat check before the scheduler exists, which
is why the arm redeploys all four from one build.

## Non-goals

- The job's code: `gcp/fetchers/fetch_watched_tickers.py`, its tests, the `_run_backfill` keywords,
  the all-history union clause and the watchdog heartbeat are the FEAT-DATA-001 ingest v2 PR's.
- Running the deploy. `./gcp/deploy.sh watched-tickers`, the one manual execution and
  `./gcp/deploy.sh schedulers` are the ingest spec's post-merge close-out steps, run after both PRs
  merge and after the per-user watchlist API's schema (`watched_tickers`, `user_watchlists`) is applied.
- Any other job's flags, schedule or image.
- Any new secret: the Alpha Vantage key and the database binding arrive the way the other fetchers get
  them (`${ENV_STRING}` and `${DB_SECRET_FLAG}`).

## Approaches considered

1. Keep the deploy wiring in the FEAT-DATA-001 PR. Refused by the gate; every prior deploy.sh change
   went through FEAT-DEPLOY-001.
2. Keep the ingest v2 spec and let its deploy item cite this spec's merge. Refused: that forces this wiring
   to merge first, and a `./gcp/deploy.sh all` between the two merges would schedule a job whose module is
   not in the image. The ingest spec is superseded by a v3 whose deploy item points here instead.
3. This spec: the deploy section relocated under FEAT-DEPLOY-001 with its own plan and PR, merged after
   the ingest code PR so no shared target can schedule a job whose module is missing. Chosen.

## Design

Everything below is `gcp/deploy.sh` text and one test; the exact values are the ingest spec's.

`deploy_fetch_watched_tickers()` beside `deploy_backfill_daily_indicators()`:

```bash
gcloud run jobs create fetch-watched-tickers --image "${IMAGE_REF:?...}" --region "${REGION}" \
  --memory 512Mi --cpu 1 --max-retries 0 --task-timeout 2400 --service-account "${SA_EMAIL}" \
  --command "python,-m,gcp.fetchers.fetch_watched_tickers" ${DB_SECRET_FLAG} \
  --set-env-vars "${ENV_STRING},WATCHED_TICKERS_MAX=50,AV_BACKFILL_SLEEP_SECS=1.0" --quiet 2>/dev/null \
|| gcloud run jobs update fetch-watched-tickers ... (the same image, region, --max-retries 0, task
   timeout, command, secret flag and env vars)
```

`deploy_fetchers()` lists the function so `all` creates the job. The dispatch `case` gains
`watched-tickers) _run build_image deploy_fetch_watched_tickers deploy_fetch_market_data deploy_fetch_earnings_history deploy_freshness_watchdog ;;`
and the help text names it. `deploy_schedulers()` gains
`_schedule "watched-tickers-nightly" "45 23 * * 1-5" "fetch-watched-tickers"`; `_schedule` passes
`--time-zone America/New_York` as it does for every other line.

`tests/gcp/test_deploy_reachability.py` gains
`test_watched_tickers_target_deploys_the_ingest_job_and_the_jobs_sharing_its_code`, built on the
file's `_dispatch_arms()` parser the way `test_backfill_ticker_declares_max_retries_zero_on_both_branches`
is.

Sizing (CLAUDE.md rule 0, from the ingest spec's section Capacity): at most 50 watched tickers, one
Alpha Vantage call each with a 1.0 s sleep, plus the indicator and verification queries; 2400 s is at
least four times that wall-clock; 512 MiB is the gen2 floor and the job's working set is a few
hundred rows per ticker; `--max-retries 0` because a re-run after a partial failure converges through
the upserts and a double run doubles the vendor calls.

## Capacity

No workload runs from this change: the script text is merged, and nothing executes it until the ingest
spec's close-out runs the arm by hand. The job's own numbers (Volume, Velocity, Wall-clock, cost) are the
ingest spec's section Capacity and go in its PR body; this PR's Capacity section says `n/a` with that
reason.

## Risks

- The arm redeploys three existing jobs from a fresh build of main. Their code is whatever main holds;
  this spec changes none of it. The ingest spec requires exactly that redeploy, so a watched ticker never
  reaches a `fetch-market-data` or `fetch-earnings-history` image that lacks the union exclusion.
- A flag typo would fail the create and the update alike and stop the arm; `bash -n` and the
  reachability test catch the script shape, and the close-out's `gcloud run jobs describe` (ingest spec,
  close-out step 2) catches the deployed image.
- The scheduler is created by `./gcp/deploy.sh schedulers` and by the `all` target, and `all` also runs
  `deploy_fetchers()`; both are unconditional, so this implementation merges only after the ingest code is
  on main and the job's module is in every image `all` would build. The ingest close-out then runs the
  arm, the manual execution and `./gcp/deploy.sh schedulers` in that order.
