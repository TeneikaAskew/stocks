# Pull-request landing-order audit — 2026-09-07

## Scope and snapshot

This audit answers a point-in-time question.  The GitHub snapshot was taken at
**2026-09-07 02:12 UTC** and covers:

* every open pull request in `TeneikaAskew/stocks` (8 PRs: #990, #991, #992,
  #993, #994, #999, #1006, and #1007); and
* every pull request merged in the preceding 24 hours, back to 2026-09-06
  02:12 UTC (7 PRs: #997, #998, #1000, #1001, #1002, #1004, and #1005).

For each PR, the audit compared the commit graph, changed paths, current GitHub
mergeability/check state, PR description, and a local three-way merge against
`origin/main` at `edb8d5c`.  Pairwise synthetic merges were also used for all
currently clean open PRs.  A clean textual merge is not treated as proof of
semantic independence: shared deployment workflows, API contracts, schema, and
tests were inspected as separate risk surfaces.

## Executive decision

Do **not** merge the queue in PR-number or creation order.  Use these lanes and
gates:

1. **Infrastructure lane:** repair/rebase **#990**, merge #990, then rebase and
   merge **#1007**, then refresh and merge **#1006**.
2. **API performance/correctness lane:** merge **#992**, rebase **#991** onto the
   result while preserving both implementations, merge #991, then rebase and
   merge **#994**.
3. **Timezone lane:** **#993** is independent enough to land at any point, but
   landing it before the final #994 rebase makes the one shared
   `lib/strat_levels.py` edit part of #994's final validation base.
4. **Contract-test gate:** rebase/fix **#999 last**, after all API handler PRs in
   this snapshot.  It is currently red because merged #1005 intentionally
   changed `/api/playbook/IWM` from the test's expected 502 to 503.

Thus a conservative single queue is:

> **#990 → #1007 → #1006 → #992 → #991 → #993 → #994 → #999**

The lanes may run concurrently only at the stated rebase gates.  The important
hard/semantic constraints are **#990 before #1007**, **#992 before the final
integration of #991**, **#991 before the final integration of #994**, and
**#999 last**.

## Open PR findings

| PR | Current state at snapshot | Order risk | Required treatment |
|---|---|---|---|
| #990 — named staging/prod services | `DIRTY`; conflicts with current main in `docs/EARNINGS_PIPELINE.md`, `platform/GCP_DATA_DICTIONARY.md`, and `platform/deploy.sh` | **High.** It establishes the renamed services and new staging workflow that #1007 documents and hardens. A careless resolution can restore retired service names or discard #1004's image-pinning hooks. | Rebase onto current main first. Resolve deployment files by retaining #1004 pin-before-tag-move behavior and #990's named-service/manual-prod design. Run deployment-script, workflow, doc-drift, and full CI checks before merge. |
| #1007 — retired-package-safe pin sweep | `CLEAN`; CI green | **Hard operational dependency on #990.** Its own warning says the break-glass staging workflow must not be dispatched before #990. Merging it first is textually possible, but exposes a workflow/config combination the PR says must not be run. It also creates four direct overlap points with #990. | Merge only after #990, rebase, and verify `.github/workflows/deploy-staging.yml`, `gcp/deploy.sh`, and `gcp/cloudbuild/README.md` contain both PRs' intent. |
| #1006 — auth email templates | `CLEAN`; CI green | Runtime code is independent, but it overlaps #990 in both architecture diagrams and `docs/GCP_ARCHITECTURE.md`. If landed first, #990 becomes harder to resolve and can erase the new API/domain nodes in binary-ish drawio XML. | Prefer after #990/#1007; rebase and visually inspect both diagrams plus the architecture doc. Template code/tests can otherwise land independently. |
| #992 — bounded options/date scans | `CLEAN`; CI green | **Semantic dependency for #991.** #991 explicitly calls #992 the real market-dates/query fix, while both edit `platform/api/main.py`, `platform/api/routers/options.py`, `gcp/schema.sql`, and `tests/api/test_platform_api.py`. Merging an old #991 resolution afterward can put back its interim one-hour TTL/query behavior. | Merge #992 first. Treat its bounded SQL, strict failure behavior, cache invalidation, and schema index as authoritative during #991's rebase. |
| #991 — threadpool migration | `DIRTY`; conflict in `platform/api/routers/playbook.py` with merged #1005 | **High.** It touches 31 files and 69 handlers, overlaps #992, #994, and #999, and currently predates the final two merged PRs. A conflict resolution that chooses one side wholesale can remove #1005's freshness/503 contract or #992's query fix. | Rebase after #992. In `playbook.py`, preserve #1005's freshness metadata/status semantics while applying #991's synchronous threadpool dispatch and concurrency safety. Validate all shared options/main/schema tests. |
| #993 — named Eastern timezone | `CLEAN`; CI green | Low. Only one-line overlap with #994 in `lib/strat_levels.py` and deployment-script overlap with the infrastructure lane. Synthetic merges are clean. | May land independently. Prefer before #994's final rebase; rerun its AST timezone guard after infrastructure changes because `gcp/deploy.sh` is shared. |
| #994 — silent-fallback fixes | `CLEAN`; GitHub checks failed before test startup at the snapshot | **Medium/high semantic overlap with #991.** It changes `grid.py`, `journal.py`, `live.py`, and platform API tests that #991 also changes. Its formatting commit even anticipates #991. Merging it first is possible, but makes the much larger #991 responsible for preserving later correctness fixes. | Integrate after #991 so the smaller correctness PR is reviewed against the final dispatch/concurrency shape. Rebase, rerun the fallback scanner and full CI, and investigate/rerun the three no-log, three-second check failures before merge. |
| #999 — API route coverage | `CLEAN` according to Git, but branch-protection `BLOCKED`; unit CI red | **Must be last in the API lane.** Its route contract already drifted after #1005: it expects 502 for `/api/playbook/IWM`, while main correctly returns 503. It also shares admin/dashboard/insights handlers with #991. | Rebase after #991/#994 and update the playbook expectation to the intentional #1005 contract. Run the complete route sweep against the final route table; do not merely change the number without retaining the JSON/error-body assertions. |

## What can actually be reverted or lost

GitHub currently blocks the two direct textual hazards (#990 and #991), so a
normal merge cannot silently land their unresolved conflicts.  The meaningful
reversion risk is in **manual conflict resolution or an out-of-date branch being
merged after a newer semantic replacement**:

### 1. #990 / #1004 / #1007 deployment chain

* **Wrong order:** merge #1007 before #990, or resolve #990's deployment
  conflicts by taking the #990 side wholesale.
* **Consequence:** the break-glass workflow can be dispatched against the old
  service layout; alternatively, #1004/#1007's fail-closed image pinning can be
  dropped before tags move.  That reopens deletion of an untagged digest still
  used by a Cloud Run job/service, or deploys/promotes the wrong service.
* **Resolution:** make #990 current first; then replay #1007.  Review the merged
  workflow command-by-command for pin, build/push, staging deploy, and manual
  production promotion.  Never resolve the files using whole-file `ours` or
  `theirs`.

### 2. #992 / #991 options and market-date implementation

* **Wrong order:** merge #991 after #992 without rebasing and intentionally
  reconciling their four shared files.
* **Consequence:** #992's measured bounded scan, data-driven cache freshness,
  ticker-wide invalidation, strict 503 behavior, or index declaration can be
  replaced by #991's acknowledged interim solution.  The likely symptom is the
  return of multi-second table scans/stale dates or misleading fallback output.
* **Resolution:** #992 is authoritative for query/cache semantics; #991 is
  authoritative for handler dispatch, thread safety, single-flight behavior,
  and race fixes.  Combine both, then run both PRs' focused tests and full CI.

### 3. #1005 / #991 / #999 playbook contract

* **Wrong order:** force-resolve #991's `playbook.py` conflict using its side, or
  merge #999 without updating its pre-#1005 expected response.
* **Consequence:** stale playbook cards can again appear current, freshness
  metadata can disappear, or CI encodes the obsolete GCS/502 contract.  #999's
  current failure is a useful stop signal, not a flaky test.
* **Resolution:** retain #1005's strict Cloud SQL source, freshness fields, and
  503 semantics; layer #991's safe dispatch on that handler; update #999 only
  after the final endpoint behavior is present.

### 4. #991 / #994 correctness fixes

* **Wrong order:** land #994 and later use broad conflict resolutions while
  refreshing #991.
* **Consequence:** finite-Greeks validation and explicit error handling in grid,
  journal, or live routes can regress to silent defaults while all code remains
  syntactically valid.
* **Resolution:** land the large mechanical/concurrency migration first and the
  focused no-silent-fallback patch second.  Require the fallback audit plus the
  combined route tests on the final tree.

### 5. #990 / #1006 architecture documentation

* **Wrong order:** land #1006 first and accept #990's diagram/doc versions during
  conflict resolution.
* **Consequence:** no runtime outage, but the branded auth domain/API node is
  erased from architecture documentation, causing operational setup drift.
* **Resolution:** rebase #1006 after the service rename and inspect rendered
  diagrams, not only XML/text diffs.

## Merged-in-the-last-24-hours review

| PR | Landing assessment |
|---|---|
| #1000 — dev role | Independent when landed. #991 has already incorporated its `/api/me` behavior on the branch and must retain the synchronous Cloud SQL lookup under threadpool dispatch. |
| #997 — ignore-file cleanup | Independent; no current open PR changes its three paths. No ordering consequence found. |
| #998 — Earnings Whispers exports | Independent data/archive change; no overlap with the open queue. No ordering consequence found. |
| #1002 — repaired test references | Conceptually depended on #1001 but GitHub recorded it merged **16 minutes before** #1001. Its merge commit is not an ancestor of current main. However, a tree comparison of all 85 paths changed by #1002 found no difference between #1002's merged tree and current main for those paths: #1001's eventual tree already contained the same reference repairs. Therefore no fix was reverted, but the history is misleading. Do not cherry-pick #1002; preserve the current tree. |
| #1001 — test-suite reorganization | The prerequisite for #1002's path repairs and the common merge base of six open branches. Its content currently includes the repairs, so no recovery PR is needed. Open branches based here must still rebase over #1005/#1004. |
| #1005 — playbook freshness and Wave 1 fixes | Landed cleanly before #1004. It creates the current conflicts/failing expectation in #991/#999. Those are downstream refresh requirements, not evidence #1005 should be reverted. |
| #1004 — registry/scheduler/cost audit | Landed after #1005 without overlap loss. #1007 is a direct corrective follow-up; #990 must preserve its pinning and scheduler work when resolving current conflicts. |

## Pairwise merge evidence

Against current main, #992, #993, #994, #999, #1006, and #1007 merge
textually clean. #990 has three conflicts and #991 has one.  Synthetic
second-merge tests show the important future collisions:

* #992 then #991 conflicts in `platform/api/main.py`,
  `platform/api/routers/options.py`, `platform/api/routers/playbook.py`, and
  `tests/api/test_platform_api.py`;
* #1007 then #990 adds a conflict in `.github/workflows/deploy-staging.yml` to
  #990's existing three conflicts;
* #1006 then #990 adds conflicts in `Architecture.drawio` and
  `docs/GCP_ARCHITECTURE.md`; and
* every current clean PR followed by stale #991 still reaches the merged #1005
  `playbook.py` conflict.

These results explain why “mergeable now” is not the same as “safe in any
order.” Rebase-and-rerun is part of the order, not an optional cleanup step.

## Final merge checklist

For every rebase/merge candidate:

1. Fetch main again and verify the reviewed SHA is still the PR head.
2. Re-run three-way and shared-path analysis against that main.
3. Reject whole-file conflict resolutions on deployment, schema, route, and
   contract-test files.
4. Run focused tests from both sides of every overlap, then the repository's
   full unit, research, and ephemeral-Postgres jobs.
5. Require all checks green on the rebased SHA. At this snapshot #994 and #999
   do not satisfy that gate; #990 and #991 have no current check suite because
   they are conflicting.
6. After #990/#1007, validate the staging and manual-production workflows without
   dispatching an unsafe pre-#990 workflow. After #991/#994/#999, rerun route
   coverage against the final application tree.

