---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-004]
issues: []
canvases: []
done_when:
  - "`scripts/verify_docs_against_live.py` defines `DATED_RECORD_DOCS = {\"docs/product/03-SITE-TRACEABILITY.md\", \"docs/product/12-PR-ISSUE-TRACEABILITY.md\"}` and `doc_paths()` drops exactly those two paths after expanding `LIVE_STATE_DOCS` and `LIVE_STATE_GLOBS`; no glob, other list entry, check, pattern, marker rule or live read changes."
  - "`tests/scripts/test_verify_docs_against_live.py::test_dated_records_are_not_live_state_docs` runs `doc_paths()` on a temporary tree holding `docs/product/03-SITE-TRACEABILITY.md`, `docs/product/12-PR-ISSUE-TRACEABILITY.md` and `docs/product/02-FEATURE-CATALOG.md`, and asserts the first two are absent and the third present; the same test on main's unchanged script fails (recorded in the implementation PR as the red run)."
  - "`tests/scripts/test_verify_docs_against_live.py::test_repository_scope_keeps_every_other_product_doc` asserts that, on the real repository root, the set returned by `doc_paths()` equals main's set minus exactly the two dated records, so a later rename or a third exclusion fails the test."
  - "The complete unchanged `tests/scripts/test_verify_docs_against_live.py` suite passes on the implementation head with no assertion removed or weakened."
  - "The implementation PR records one `python scripts/verify_docs_against_live.py --snapshot <file>` run on its head against a recorded live snapshot, listing every remaining finding by file and check; none is in either dated record, and any remaining finding is named in the PR as live drift, not hidden."
  - "Normal authenticated external CODE review on the current head, green required CI and resolved conversations complete the implementation PR; no workflow, schedule, secret, IAM binding or GCP resource changes."
status: approved
supersedes: null
---

# Live-docs check: leave the two dated traceability records out

## Authority

Proposed on 2026-11-05 by the FEAT-CICD-001 delivery lane that traced the failing `Verify docs against live GCP`
workflow. The owner delegated delivery decisions on 2026-11-04 ("Do what you think would best benefit the project")
and the coordinating session chose this smaller option over rewriting the two records. This file is not
self-approved: it takes effect only when the owner authorizes the merge of this spec-only change.

## Problem

The daily `Verify docs against live GCP` workflow (`.github/workflows/verify-docs-against-live.yml`) has failed on
every scheduled run on main since 2026-10-07. Three causes stack up, and PR #1701 fixes the two that are real doc
drift (the retired `solyra-api-prod` service and the 66th scheduler, `earnings-sweep-sunday`, first read live
2026-10-19). The third cause is scope.

`scripts/verify_docs_against_live.py` checks every file matched by `LIVE_STATE_GLOBS`, which includes
`docs/product/*.md`. Its own header says the check is for documents that describe the current system, and that a
dated record "whose whole purpose is to state what was true on its date" is deliberately out of scope. Two such
records sit inside that glob and were enrolled automatically:

- `docs/product/03-SITE-TRACEABILITY.md` (added 2026-10-07) records observed evidence: timestamps of past runs,
  Cloud SQL instance names, execution IDs and review results, each against a dated commit.
- `docs/product/12-PR-ISSUE-TRACEABILITY.md` records PR, issue and audit history.

On the PR #1701 branch, with a snapshot that reproduces the CI run's live state, every remaining finding is in these
two files: 75 in 03 and 3 in 12. They are false positives of the checker on evidence rows, not drift:
`trading-db` is a Cloud SQL instance, `db-query-*` names are execution IDs, `admin-ui` matches the prefix of a secret
name, observed run timestamps are read as schedules, and a day qualifier after a time is read as part of the
schedule. Marking 78 evidence rows with `verify-docs-ok` comments would bury the records in exemptions and would
have to be repeated for every new row.

## Non-goals

- No change to any check, pattern, suppression rule, count rule, the live reads, the workflow, its schedule or its
  credentials.
- No edit of either record. Both keep their content; they stay under the docs audit and the spec gate as today.
- No exclusion by pattern. Only the two named paths leave scope, so a new current-state document under
  `docs/product/` is still enrolled automatically.
- Not a fix for live findings that are real. As of 2026-11-05 the live `signal-monitor-daily` scheduler is PAUSED
  (paused 2026-11-04 21:44:59 UTC, cause under investigation), which the check reports as 31 findings in
  current-state documents. This spec does not suppress them.

## Approaches considered

1. Mark each evidence row with `verify-docs-ok`. 78 markers now and more with every new row; the records become
   harder to read and the exemptions say nothing true about the system.
2. Teach the checker to tell evidence rows from claims. Larger and riskier; the false positives come from five
   different checks.
3. Chosen: name the two dated records as out of scope, which is what the script's own header already says dated
   records are.

## Design

In `scripts/verify_docs_against_live.py`, next to `LIVE_STATE_GLOBS`:

```python
# Dated evidence records that live under docs/product/ but state what was observed on a date, not what is
# running now. They are out of scope for the same reason as every other dated record.
DATED_RECORD_DOCS = {
    "docs/product/03-SITE-TRACEABILITY.md",
    "docs/product/12-PR-ISSUE-TRACEABILITY.md",
}
```

`doc_paths(root)` expands `LIVE_STATE_DOCS` and `LIVE_STATE_GLOBS` as today, then drops any path whose
root-relative POSIX form is in `DATED_RECORD_DOCS`. Order of the remaining paths is unchanged.

Tests in `tests/scripts/test_verify_docs_against_live.py` as listed in done_when items 2 and 3.

## Capacity and cost

- Volume: two fewer files read per run (about 1.1 MB less text scanned).
- Velocity: unchanged, one run per weekday plus manual and push runs.
- Wall-clock: no measurable change; the run is dominated by the gcloud reads.
- Cost: $0. No GCP workload, schedule or resource is added or changed.

## Risks

- A real current-state claim written into one of the two records would no longer be checked. Both records are
  evidence logs whose rows are dated; current-state claims belong in the current-state documents, which stay in
  scope.
- Once #1701 and this change land, the daily check still fails while `signal-monitor-daily` stays paused. That is a
  true finding and is reported, not hidden; done_when item 5 requires the implementation PR to name it.

## Validation and rollout

1. This spec-only change, on branch `docs/spec-feat-cicd-001-verify-docs-records`, holds this file only.
2. It passes `python3 scripts/gate/spec_gate.py --check-spec` and `--pr origin/main`, and merges only on owner
   authorization.
3. The implementation then follows on a `fix/feat-cicd-001-verify-docs-dated-records` branch with its plan bound to
   this spec.
4. No production action.
