---
feat_id: FEAT-DEPLOY-001
spec: docs/superpowers/specs/2026-11-14-feat-deploy-001-watched-tickers-deploy.md
branch: feature/feat-deploy-001-watched-tickers-deploy
pr: null
status: ready
---

# Deploy wiring for fetch-watched-tickers, implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances (done_when[0] is the first item).

**Goal:** `gcp/deploy.sh` creates, updates and schedules the `fetch-watched-tickers` Cloud Run Job and redeploys the three jobs that share its image's code paths from one build, with the reachability test pinning the arm.

**Architecture:** one deploy function beside `deploy_backfill_daily_indicators()`, one entry in `deploy_fetchers()`, one dispatch arm, one `_schedule` line, one help-text line; one test in `tests/gcp/test_deploy_reachability.py`. The script text already exists as commit 16a2dc1c on the retired FEAT-DATA-001 branch (reviewed there as its Task 9); Task 1 applies it here.

**Tech Stack:** bash (`gcp/deploy.sh`, `bash -n`), pytest (`tests/gcp/test_deploy_reachability.py`, its `_dispatch_arms()` parser).

**Spec:** `docs/superpowers/specs/2026-11-14-feat-deploy-001-watched-tickers-deploy.md` (approved).

**Cross-repo order:** merges after the FEAT-DATA-001 ingest v3 code PR (its module must be in every image the `all` target would build before `deploy_fetchers()` and `deploy_schedulers()` name the job); nothing runs until the ingest spec's post-merge close-out executes the arm.

## Global Constraints

- Values verbatim from the spec: `fetch-watched-tickers`, `--memory 512Mi --cpu 1 --max-retries 0 --task-timeout 2400`, command `python,-m,gcp.fetchers.fetch_watched_tickers`, env `${ENV_STRING},WATCHED_TICKERS_MAX=50,AV_BACKFILL_SLEEP_SECS=1.0`, the existing `${DB_SECRET_FLAG}` and `${SA_EMAIL}`; scheduler `watched-tickers-nightly` at `45 23 * * 1-5`; arm `watched-tickers) _run build_image deploy_fetch_watched_tickers deploy_fetch_market_data deploy_fetch_earnings_history deploy_freshness_watchdog ;;`.
- No other job's flags, schedule or image changes; no new secret; no `WATCHED_TICKERS_URL`, no `WATCHED_TICKERS_READ_SECRET`.
- No em or en dashes in code or docs.

## Review Focus

1. Both the create and the update branch carry `--max-retries 0`, the task timeout, the command, the secret flag and the env vars; the existing `deploy_backfill_daily_indicators()` update branch drops `--max-retries 0`, and this function must not copy that. Pinned in Task 1.
2. The arm's first word is `build_image`; `_run` executes the functions in order so the four jobs deploy from the same image. Pinned in Task 1.

---

### Task 1: The deploy function, the arm, the scheduler and the test

Spec: § Design. Advances done_when[0], [1], [2], [3].

**Files:**
- Modify: `gcp/deploy.sh` (`deploy_fetch_watched_tickers()` beside `deploy_backfill_daily_indicators()`; `deploy_fetchers()`; the dispatch `case`; `deploy_schedulers()`; help text)
- Modify: `tests/gcp/test_deploy_reachability.py`

- [ ] **Step 1: Write the failing test** `test_watched_tickers_target_deploys_the_ingest_job_and_the_jobs_sharing_its_code` on the file's `_dispatch_arms()` parser, as `test_backfill_ticker_declares_max_retries_zero_on_both_branches` is built: the arm creates or updates exactly `{"fetch-watched-tickers", "fetch-market-data", "fetch-earnings-history", "freshness-watchdog"}`, both branches of the new function carry `--max-retries 0`, `--task-timeout 2400` and `--command "python,-m,gcp.fetchers.fetch_watched_tickers"`, the function text holds neither `WATCHED_TICKERS_URL` nor `WATCHED_TICKERS_READ_SECRET`, `deploy_schedulers()` holds exactly the line `_schedule "watched-tickers-nightly" "45 23 * * 1-5" "fetch-watched-tickers"`, and the `_schedule` helper passes `--time-zone America/New_York` (Codex on #1918: without the command and the cron, a function running another module every minute would pass).
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_deploy_reachability.py -v`; expected FAIL (`KeyError: 'watched-tickers'`).
- [ ] **Step 3: Implement** the function, the `deploy_fetchers()` entry, the arm, the `_schedule` line and the help text; `git cherry-pick 16a2dc1c` from the retired FEAT-DATA-001 v2 branch yields that text, and the test gains the command, task-timeout and schedule-line assertions on top of it.
- [ ] **Step 4: Run** the file (PASS, including `test_every_schedule_target_is_created_by_some_deploy_function` and `test_all_target_creates_every_scheduled_job_and_service`) and `bash -n gcp/deploy.sh`.
- [ ] **Step 5: Commit** `feat(deploy): fetch-watched-tickers job and its nightly scheduler`

### Task 2: Implementation-source note and source snapshot

Spec: done_when[4] (the FEAT-CICD-001 documentation identity protocol).

- [ ] **Step 1: Preflight**: `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`; copy the head's source identity.
- [ ] **Step 2: Update the existing FEAT-DEPLOY-001 SHARED-07 row** in place: its hash replaced, its sentence kept, appended `fetch-watched-tickers is created, updated and scheduled by gcp/deploy.sh (deploy_fetch_watched_tickers, the watched-tickers arm, watched-tickers-nightly); test: tests/gcp/test_deploy_reachability.py.`; commit `docs(site): SHARED-07 implementation-source note for the fetch-watched-tickers deploy`.
- [ ] **Step 3: Produce** the snapshot and commit `docs(evidence): site source snapshot for the fetch-watched-tickers deploy`.
- [ ] **Step 4: Verify** with the protocol's verify command: `status identity-matched`; docs audit on the branch reports nothing `origin/main` does not.

### Task 3: Close

Spec: § Done when. Closes done_when[5].

- [ ] Update the FEAT-DEPLOY-001 record in `docs/product/02-FEATURE-CATALOG.md` (Status, Last reviewed) and the FEAT-DEPLOY-001 PR lineage in `docs/product/12-PR-ISSUE-TRACEABILITY.md`; set this plan's `pr`.
- [ ] `python3 scripts/maintenance/docs_audit.py` on the branch and on `origin/main`: nothing new; `python3 scripts/gate/spec_gate.py --pr origin/main` ok; `python3 -m pytest tests/gcp/test_deploy_reachability.py -q` green.
- [ ] PR body: Capacity `n/a: no workload runs from the script text; the ingest spec's close-out runs the arm by hand`; every done_when line ticked with its evidence.
