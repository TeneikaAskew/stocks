---
feat_id: FEAT-DEPLOY-001
spec: docs/superpowers/specs/2026-11-13-feat-deploy-001-db-query-timeout-fit.md
branch: fix/feat-deploy-001-db-query-timeout-fit
status: ready
---

# Refuse a db-query statement timeout the task timeout can never reach (implementation plan)

**Goal:** `scripts/db_query_cr.sh` refuses a `--timeout` the db-query job's 600s
`--task-timeout` cannot reach, before it dispatches anything, instead of spending ten
minutes of Cloud Run on a configuration that can only end in a SIGKILL with no results.

**Spec:** `docs/superpowers/specs/2026-11-13-feat-deploy-001-db-query-timeout-fit.md`.

**Requirement:** REQ-DEPLOY-001.

**Issue:** #1861.

## Task 1: the guard
Spec: § Design. Advances done_when[0], done_when[1], done_when[3].
- [ ] `TASK_TIMEOUT_S` and `OVERHEAD_S` beside the existing defaults, each carrying the
      measurement that justifies it.
- [ ] Refuse a `--timeout` that is not a positive whole number, exit 2.
- [ ] Refuse a `--timeout` above `TASK_TIMEOUT_S - OVERHEAD_S`, exit 2, naming both
      remedies; state in the comment that this bounds one statement, not a batch.
- [ ] Both refusals sit before the dispatch and before `WAIT_MAX_S` is derived.

## Task 2: tests
Spec: § Design, § Risks. Advances done_when[2], done_when[4], done_when[5].
- [ ] `tests/scripts/test_db_query_cr_timeout_fit.py` drives the real script with a stub
      `gcloud` that records arguments and refuses `run jobs execute`.
- [ ] The #1861 invocation, the bound, one second over it, the default, and five
      non-numeric values.
- [ ] A contract test reading `--task-timeout` out of `deploy_db_query`.
- [ ] Record the suite failing against the base's dispatcher and passing on the head.

## Task 3: evidence
Spec: § Delivery. Advances done_when[6].
- [ ] `python3 -m pytest tests/scripts/` on the head.
- [ ] Gate passes; catalog Last reviewed and 12-PR lineage updated; the PR answers #1861.
