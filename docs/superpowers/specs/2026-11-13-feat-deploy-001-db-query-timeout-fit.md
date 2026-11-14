---
feat_id: FEAT-DEPLOY-001
req_ids: [REQ-DEPLOY-001]
issues: [1861]
canvases: []
done_when:
  - "scripts/db_query_cr.sh refuses, with exit status 2 and before any Cloud Run dispatch, a --timeout that the db-query job's --task-timeout cannot reach: the bound is that task timeout less a fixed allowance for connector setup and artifact upload, and the message names the value given, the task timeout, the largest accepted value, and both remedies (lower --timeout, or raise --task-timeout in gcp/deploy.sh and redeploy)."
  - "scripts/db_query_cr.sh refuses, with exit status 2 and before any dispatch, a --timeout that is not a positive whole number of seconds; on the base an empty value dispatched a job with an empty DB_QUERY_TIMEOUT_SECONDS."
  - "The bound the script carries is the task timeout gcp/deploy.sh actually deploys for db-query: tests/scripts/test_db_query_cr_timeout_fit.py reads --task-timeout out of deploy_db_query and fails if the two disagree, so raising one without the other is caught in CI rather than in production."
  - "The guard bounds one statement and says so, in the script and in the spec: statement_timeout is per statement, so a multi-statement batch can still exceed the task budget in total, and that case stays Cloud Run's to report."
  - "Reproduced first: tests/scripts/test_db_query_cr_timeout_fit.py is run against the base's dispatcher and 8 of its 10 tests fail there, the #1861 invocation (--timeout 900) among them, and all 10 pass on the PR head. Both runs are recorded on the PR with their output."
  - "Hermetic: the tests run the real script with a stub gcloud on PATH that records its arguments and exits nonzero on `run jobs execute`, so no Cloud Run job is dispatched and no Cloud SQL connection is made. python3 -m pytest tests/scripts/ passes on the PR head."
  - "Records: the FEAT-DEPLOY-001 record in docs/product/02-FEATURE-CATALOG.md shows a current Last reviewed, and docs/product/12-PR-ISSUE-TRACEABILITY.md lists the PR under FEAT-DEPLOY-001; no other capability's row changes."
status: approved
---

# Refuse a db-query statement timeout the task timeout can never reach (FEAT-DEPLOY-001)

## Problem

`scripts/db_query_cr.sh` takes `--timeout SECS` and plumbs it to the db-query Cloud Run Job
as `DB_QUERY_TIMEOUT_SECONDS`, which `gcp/db_query_job.py` turns into Postgres
`statement_timeout`. The job is deployed with `--task-timeout 600`
(`gcp/deploy.sh`, `deploy_db_query`). The dispatcher never compares the two.

On 2026-11-13 two executions were dispatched with `DB_QUERY_TIMEOUT_SECONDS=900`:

| Execution | Dispatched | Cloud Run terminated it | Elapsed |
|---|---|---|---|
| `db-query-cb2fs` | 12:27:50.503Z | 12:37:50.348Z | 599.8s |
| `db-query-szg6b` | 12:33:09.850Z | 12:43:10.297Z | 600.4s |

Both logged exactly one line, the dispatch, and then
`Terminating task because it has reached the maximum timeout of 600 seconds`.
`statement_timeout` could not fire, so `run_query`'s reportable `57014` path was
unreachable; nothing was written to GCS; the operator waited ten minutes for
nothing; and `gcp/failure_notifier.py` opened issue #1861 and three comments for a
configuration that could never have worked.

A `--timeout` above the task budget is not a longer budget. It is a guaranteed hard
kill with no results, and the dispatcher can see that before it spends anything.

## Design

In `scripts/db_query_cr.sh`, after argument parsing and before anything is
dispatched:

- `TASK_TIMEOUT_S=600`, the value `gcp/deploy.sh` deploys, with the measurement that
  establishes the clock starts at container start.
- `OVERHEAD_S=60`, the allowance for everything else inside the task's budget.
- Refuse `--timeout` that is not a positive whole number.
- Refuse `--timeout` greater than `TASK_TIMEOUT_S - OVERHEAD_S` (540), with both
  remedies and a pointer to CLAUDE.md 3.8, since a query needing more than 540s
  usually wants a narrower scan rather than a longer clock.

The allowance is measured, not guessed. On four executions that succeeded on
2026-11-13 (`2wm4f`, `bfb29`, `52v8m`, `nsdzw`), dispatch to the `done:` line took
7.4-9.2s for two statements, and `done:` to container exit took 1.3-1.6s. 60s is
about six times the largest of those, so a statement granted the whole remaining
budget still leaves room for a large result upload.

## Non-goals

- Raising the db-query task timeout. Nothing here says 600s is the right size; the
  query that hit it is an analysis query over `historical_signals` and belongs under
  CLAUDE.md 3.8, not under a longer clock.
- Bounding a multi-statement batch. `statement_timeout` is per statement, so N
  statements can still exceed the task budget in total. Cloud Run reports that when
  it happens; predicting it would need a cost model the dispatcher does not have.
- Reading the task timeout live from the API. The dispatcher must refuse before it
  spends anything, and a test that reads `gcp/deploy.sh` catches drift without a
  network call in CI.

## Risks

- The bound and the deploy drift apart. The contract test fails CI if they do.
- An operator who genuinely needs a longer statement is now stopped. That is the
  point: on the base they were stopped too, ten minutes later and with an issue
  filed. The message names the supported way to get one.
