# GitHub Actions workflows

Scheduled data fetching and analysis moved from GitHub Actions to Cloud Run Jobs driven by Cloud Scheduler (66 entries live on 2026-09-07); see [ARCHITECTURE.md §6](../../ARCHITECTURE.md#6-cloud-run-jobs) and [§8](../../ARCHITECTURE.md#8-cloud-scheduler-timeline). What remains here is CI, two manual bridges, the shared failure handler, a daily docs-vs-live check and the monthly documentation refresh. [ARCHITECTURE.md §14](../../ARCHITECTURE.md#14-ci-cloud-build-and-github-actions) carries the same inventory next to the Cloud Build triggers.

## Live workflows

| File | Trigger | What it does |
|---|---|---|
| [`backtest-pipeline.yml`](backtest-pipeline.yml) | push to `main` or `claude/**` touching `lib/`, `scripts/`, `tests/`; pull requests; a nightly canary | Runs the hermetic test suite (`Run Tests`), the integration tests against an ephemeral Postgres with `gcp/schema.sql` applied, and the research tests with the real ML stack. The heavy report generation it used to run lives in the `backtest-pipeline` Cloud Run job. |
| [`deploy-staging.yml`](deploy-staging.yml) | `workflow_dispatch` on `main` only, Workload Identity Federation | Manual redeploy of `solyra-api-staging`: optional schema apply, materialized-view repopulate, `STAGING_SERVICE=1 ./platform/deploy.sh` (build by digest, pin in-use images, deploy), health check. The routine path is the `deploy-solyra-api-staging` Cloud Build trigger on push to `main`; this is the break-glass. Its header carries the IAM grants the deploy SA needs. |
| [`gh-api.yml`](gh-api.yml) | `workflow_dispatch` | Runs one GitHub REST call on a runner and prints the body to the job log, for sandboxes whose `api.github.com` access is fenced (CLAUDE.md "GitHub API access from the sandbox"). `GET` by default; mutations need `confirm_write=true`. |
| [`handle-workflow-failure.yml`](handle-workflow-failure.yml) | `workflow_call` from the `handle-failure` job of every other workflow | Opens or updates a `workflow-failure` issue with the failed step's logs and, unless `create_pr: false`, a draft `fix/workflow-<name>-<run>` branch and PR (`scripts/handle_workflow_failure.py`). Authenticates with `PR_WORKFLOW_TOKEN` because the default token cannot create PRs here. |
| [`verify-docs-against-live.yml`](verify-docs-against-live.yml) | weekdays 09:00 ET (`0 13 * * 1-5` UTC), `workflow_dispatch`, and push to `main` touching the verifier or its tests | Runs `scripts/verify_docs_against_live.py` against live GCP (WIF, read-only) so a doc claim about a schedule, count or service name that drifts from the project turns the run red and names the line; uploads the live snapshot as an artifact. Added by #990. It has no `handle-failure` job yet, so a red run is visible only on the Actions page. |
| [`refresh-architecture-docs.yml`](refresh-architecture-docs.yml) | 1st of the month 06:00 UTC, and `workflow_dispatch` (`dry_run` input) | Snapshots live GCP (jobs, schedulers, services, SQL, IAM, billing), renders the inventory blocks in `ARCHITECTURE.md`, `DATA_DEPENDENCIES.md` and `docs/API.md` from the code, has Gemini update the prose of the four generated docs in place, runs the loss and drift gates (`scripts/maintenance/check_generated_docs.py`, `scripts/verify_docs_against_live.py`) and opens a `bot/arch-refresh-YYYY-MM` PR. Setup and IAM: [SETUP.md](../../SETUP.md). |

Every workflow with a main job should end in a `handle-failure` job wired to `handle-workflow-failure.yml` (CLAUDE.md "Automated Workflow Failure Handling"); a workflow without one fails silently, which is how the 2026-06 and 2026-07 doc refreshes went unnoticed for two months.

## Retired workflows

Files renamed to `*.yml.disabled` are ignored by GitHub Actions and kept for the history in their header comments:

| File | Replaced by |
|---|---|
| `fetch-market-data.yml.disabled` | the `fetch-market-data` Cloud Run job (`fetch-market-data-daily`, 23:00 ET) |

Other workflows that once lived here (earnings options analytics, economic-events calendar, Google Sheets download, the `db-query.yml` SQL runner, the platform staging/promote deploys) were deleted outright when their Cloud Run or Cloud Build replacements landed; `git log -- .github/workflows/<name>.yml` recovers any of them. `logs.txt` in this directory is a runner log accidentally committed in 2025 and is not read by anything.

## Conventions when adding a workflow

- Keep `workflow_dispatch:` and drop `schedule:` when the workload runs in Cloud Run (CLAUDE.md "Workflow retirement / Cloud-Run-migration convention"); rename to `.yml.disabled` only for a full retirement.
- Add the `handle-failure` job with `actions: read`, `issues: write`, `pull-requests: write` and unique `issue_labels`.
- No `continue-on-error: true` on a fetch or validation step (CLAUDE.md Rule 3.7).
- `workflow_dispatch` only registers once the file is on `main`; a dispatch before that returns 404.
