---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-REVIEW-001]
issues: [1795, 1796]
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "Test margins: in tests/scripts/test_doc_source_snapshot.py, test_actual_fallback_parser_cpu_deadline_preserves_absent_or_valid_record builds its fixture with complex_body_repo(..., 80000, existing), runs produce with --max-seconds 0.75 and asserts elapsed_seconds < 0.85; every other assertion of that test is unchanged, its comment states why the cap and the body size were chosen, and no other test in the file changes. Both parameters pass ten consecutive runs on the PR head."
  - "Reproduced first: the PR records, with the commands and their output, main's test failing where a host finishes the bounded work under its 2-second cap (the main test body at 20000 lines and --max-seconds 2 exits 0 with status identity-matched, so assert refused.returncode != 0 fails as it did on #1791 and #1802), and the head's test refusing at the same stand-in for a faster host (20000 and 40000 lines at --max-seconds 0.75 refuse with the reason whole verification CPU deadline exceeded and a source_identity_sha256)."
  - "Margins recorded: the PR records, from the head's unchanged CLI on the 80000-line fixture, the lowest of 0.15, 0.2 and 0.25 seconds at which the refusal still carries a source_identity_sha256, the completion time at the default five-second cap for 20000, 40000 and 60000 lines, and the resulting margins of the 0.75-second cap against both, stated against the fastest hosted runner seen (1.91 s for 40000 lines on #1802)."
  - "Source identity (SHARED-01): on the PR head, the existing bounded producer and verifier (scripts/maintenance/doc_source_snapshot.py produce, then verify with the fixed ceilings, run from the committed HEAD) prove committed source and SITE body identity bound to this approved spec at the actual merge base, where its blob equals the one on current main; the plan binds this spec; the only SITE change is the FEAT-CICD-001 / SHARED-01 row of the Implementation-source notes table, updated with the prefix source_identity_sha256=<current source hash> and nonempty prose that describes only this PR's test change, followed by ' Earlier: ' and the row's previous text, in which the one sentence that is false on the PR head (tests/meta/test_model_registry_consistency.py pins this document at one dead path) is reworded in the past tense, naming the PR that removed the pin, and every other sentence is kept; every other SITE byte is unchanged; the sidecar is produced from the final committed SITE body and committed; the registry docs/DOC_REGISTRY.md blob, mode and type equal main's."
  - "Matched audits: python3 scripts/maintenance/docs_audit.py --no-owning-job-check --json with one issues capture on the PR head and on main reports no finding on the head that main does not."
  - "Suites: on the PR head, python3 -m pytest tests/scripts/test_doc_source_snapshot.py and python3 -m pytest tests/meta pass, and python3 scripts/gate/spec_gate.py --pr origin/main reports spec gate ok in ready mode."
  - "Records: the FEAT-CICD-001 record in docs/product/02-FEATURE-CATALOG.md shows a current Status and Last reviewed, and docs/product/12-PR-ISSUE-TRACEABILITY.md lists the PR under FEAT-CICD-001; no other capability's row or record changes."
status: approved
supersedes: null
---

# Give the CPU-deadline refusal test a measured margin, and reword the stale FEAT-CICD-001 note (FEAT-CICD-001)

## Problem

`tests/scripts/test_doc_source_snapshot.py::test_actual_fallback_parser_cpu_deadline_preserves_absent_or_valid_record`
builds a SITE body of 40,000 extra lines and expects `doc_source_snapshot.py produce --max-seconds 2` to be interrupted
by its CPU deadline and refuse. It assumes the bounded work takes longer than two seconds on every host. Hosted runners
broke that assumption twice on 2026-11-11, both on documentation-only PRs whose one changed file the test never reads:

- TeneikaAskew/stocks#1791, job 130512139505: `"elapsed_seconds": 1.9875584510000408`, `status: identity-matched`,
  `assert 0 != 0`.
- TeneikaAskew/stocks#1802, job 130574335307: `"elapsed_seconds": 1.9126568529999304`, the same assertion.

One re-run passed each time, and #1796 tracks the failure. A test that goes red when the runner is fast enough blocks
unrelated PRs and teaches people to re-run red CI.

Separately, #1795: the FEAT-CICD-001 / SHARED-01 row of the Implementation-source notes table in
`docs/product/03-SITE-TRACEABILITY.md` (written by #1788) says "`tests/meta/test_model_registry_consistency.py` pins
this document at one dead path, the FEAT-DEPLOY-001 note's citation of the deleted prompt renderer (owner decision on
#1788)." #1794 removed that pin, so the sentence is now false. Only a FEAT-CICD-001 change whose approved spec
declares SHARED-01 may edit that row (`doc_source_snapshot.note_delta` refuses a foreign row). The test fix above is
such a change: `tests` is a watched path, so its PR must update this row anyway.

## Measurements (sandbox, 2026-11-11, main f0ecbe56)

Read-only runs of the unchanged CLI on the test's own `complex_body_repo` fixture:

| Lines | Cap (s) | Result | elapsed_seconds | source identity at refusal |
|---|---|---|---|---|
| 0 | 5 | identity-matched | 0.12 to 0.16 | set |
| 20,000 | 5 | identity-matched | 1.33 to 1.47 | set |
| 40,000 | 5 | identity-matched | 2.94 to 3.12 | set |
| 60,000 | 5 | identity-matched | 3.79 to 3.86 | set |
| 80,000 | 0.15 | refused, CPU deadline | 0.150 | not set |
| 80,000 | 0.2 | refused, CPU deadline | 0.200 to 0.206 | set |
| 80,000 | 0.75 (x3, both parameters) | refused, CPU deadline | 0.750 | set |

The sandbox is slower than the fastest runner seen: 3.0 s here against 1.91 s on #1802 for 40,000 lines, a factor of
about 1.6. Two bounds follow. The cap must be later than the point where the source identity is computed (0.15 to
0.2 s here, earlier on a faster host), or the assertion `source_identity_sha256 is not None` fails. The cap must also
be earlier than the end of the whole bounded work on the fastest host, or the run succeeds and the test fails as it did
on #1791 and #1802. At 20,000 lines the sandbox finishes in about 1.4 s, under the current 2 s cap, which reproduces the
hosted failure here.

## Non-goals

- No change to `scripts/maintenance/doc_source_snapshot.py`, its deadline, its ceilings or its CLI.
- No change to any other test in `tests/scripts/test_doc_source_snapshot.py`, including the other timing controls.
- No change to any other sentence of the FEAT-CICD-001 / SHARED-01 row, to any other row, or to any SITE cell outside
  the Implementation-source notes table.
- No deployment: a test and documentation change only.

## Approaches considered

1. **Lower the cap and grow the body (chosen):** 80,000 lines and `--max-seconds 0.75`. The cap is 3.75 times the
   slowest measured source-identity point (0.2 s) and, scaling 40,000 lines at 1.91 s, about 4 to 5 times under the
   fastest runner's estimated completion (about 3.0 to 3.8 s). At refusal, `counted_bytes` is 5,676,910, well under
   `MAX_BYTES` (12,582,912).
2. Lower the cap only (`0.5` at 40,000 lines, as #1796 proposed): margins of about 2.5 and 3.8 times. Workable, but
   the fast-host side has less headroom for little saving.
3. Grow the body only (keep `2`): the byte ceiling limits the body to about 94,000 lines, a margin of about 2 times at
   best. Rejected.
4. Make the test independent of speed by mocking the clock or the parser: rejected, because the test exists to drive
   the real CLI and its real `SIGALRM` deadline.

## Design

Branch `fix/feat-cicd-001-cpu-deadline-margin`, opened after this spec merges, one plan, one PR.

1. `tests/scripts/test_doc_source_snapshot.py`: in the one test, `40000` becomes `80000`, `"2"` becomes `"0.75"`,
   `< 2.1` becomes `< 0.85`, and the comment above the elapsed assertion is rewritten to say the cap must fall after
   the source identity is computed and before the bounded work can finish on a fast host, with the measured figures.
   TDD order: record main's failure at the faster-host stand-in first (done_when 2), then change the test and show both
   parameters passing ten times.
2. `docs/product/03-SITE-TRACEABILITY.md`, the FEAT-CICD-001 / SHARED-01 row only: new prefix
   `source_identity_sha256=<hash from produce>; `, prose naming this PR's one test change, then ` Earlier: ` and the
   previous text after its old prefix with the pin sentence reworded, for example: "`tests/meta/test_model_registry_consistency.py`
   pinned this document at one dead path, the FEAT-DEPLOY-001 note's citation of the deleted prompt renderer (owner
   decision on #1788), until #1794 removed the pin." No backticked path to a file that does not exist on the head;
   no `|`.
3. Commit, `produce` again, commit `docs/review-evidence/site-source-snapshot.json`, then `verify` with the fixed
   ceilings (`--max-seconds 5 --max-input-bytes 12582912 --max-entries 20000`).
4. Records: FEAT-CICD-001 Status clause and Last reviewed in the catalog; the PR under FEAT-CICD-001 in the
   traceability file. The PR body closes #1795 and #1796.

Capacity: n/a, one test's constants and documentation; no job, query, schedule or cloud call. The test's own fixture
writes about 5 MB into a temporary repository per parameter and its CLI run stops at 0.75 s.

## Source identity and close-out

Pre-merge: done_when items 4 and 5. After the merge, tracked on the PR and never ticked before the evidence exists:
verify main's source and body identity in a fresh clone; set the plan `status: done` on a `docs/` branch; confirm #1795
and #1796 closed.

## Risks

- A host much slower than the sandbox, where computing the source identity takes longer than 0.75 s: the refusal
  would carry no source identity and the test would fail. The sandbox, the slowest host measured, reaches it by 0.2 s.
- A host more than four times faster than the fastest runner seen: the run could finish inside 0.75 s. The PR records
  the margins so a future failure can be judged against them.
- Another lane changes watched paths on main before this merges: the sidecar becomes historical. Caught by done_when 4
  (verify against current main); the remedy is merging main and producing the sidecar again.
- The reworded sentence introduces a dead path: caught by done_when 5.
