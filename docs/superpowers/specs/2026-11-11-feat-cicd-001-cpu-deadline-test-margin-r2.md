---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-REVIEW-001]
issues: [1795, 1796]
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "Escalating caps: in tests/scripts/test_doc_source_snapshot.py, test_actual_fallback_parser_cpu_deadline_preserves_absent_or_valid_record builds its fixture with complex_body_repo(..., 80000, existing) and runs produce at --max-seconds 0.75, 1.5, 3 and 5 in that order, stopping at the first attempt whose refusal carries a source_identity_sha256 and counted_bytes of at least the body's length; every attempt must exit nonzero with status unverified and the reason whole verification CPU deadline exceeded or whole verification deadline exceeded, and leave the record absent or byte-identical; the stopping attempt asserts the reason whole verification CPU deadline exceeded, counted_bytes at most MAX_BYTES and elapsed_seconds below its cap plus 0.1; when no cap up to 5 seconds lands after the body was read, the test fails with a message carrying the last verdict. Its comment says why the caps escalate and why the body is 80,000 lines, and no other test in the file changes. Both parameters pass ten consecutive runs on the PR head."
  - "Reproduced first: the PR records, with the commands and their output, (a) main's test failing at a fast-host stand-in (the main test body at 20000 lines and --max-seconds 2 exits 0 with status identity-matched, so assert refused.returncode != 0 fails, as on #1791 and #1802), (b) the fixed 0.75-second version at f780118c failing on a loaded host (the run pinned to one CPU core beside three busy loops, with counted_bytes below the 80000-line body's length, the failure Codex reported on #1814), and (c) the head's test passing at those fast-host stand-ins (20000 and 40000 lines) and on that loaded host."
  - "Margins recorded: the PR records, from the head's unchanged CLI on the 80000-line fixture, unloaded and on the loaded host, the lowest of the four caps whose refusal carries a source identity and the whole body, and, unloaded, the completion time at the default five-second cap for 20000, 40000 and 60000 lines, and states at which step each host stops, against the fastest hosted runner seen (1.91 s for 40000 lines on #1802)."
  - "Source identity (SHARED-01): on the PR head, the existing bounded producer and verifier (scripts/maintenance/doc_source_snapshot.py produce, then verify with the fixed ceilings, run from the committed HEAD) prove committed source and SITE body identity bound to this approved spec at the actual merge base, where its blob equals the one on current main; the plan binds this spec; the only SITE change is the FEAT-CICD-001 / SHARED-01 row of the Implementation-source notes table, updated with the prefix source_identity_sha256=<current source hash> and nonempty prose that describes only this PR's test change, followed by ' Earlier: ' and the row's previous text, in which the one sentence that is false on the PR head (tests/meta/test_model_registry_consistency.py pins this document at one dead path) is reworded in the past tense, naming the PR that removed the pin, and every other sentence is kept; every other SITE byte is unchanged; the sidecar is produced from the final committed SITE body and committed; the registry docs/DOC_REGISTRY.md blob, mode and type equal main's."
  - "Matched audits: python3 scripts/maintenance/docs_audit.py --no-owning-job-check --json with one issues capture on the PR head and on main reports no finding on the head that main does not."
  - "Suites: on the PR head, python3 -m pytest tests/scripts/test_doc_source_snapshot.py and python3 -m pytest tests/meta pass, and python3 scripts/gate/spec_gate.py --pr origin/main reports spec gate ok in ready mode."
  - "Records: the FEAT-CICD-001 record in docs/product/02-FEATURE-CATALOG.md shows a current Status and Last reviewed, and docs/product/12-PR-ISSUE-TRACEABILITY.md lists the PR under FEAT-CICD-001; no other capability's row or record changes."
status: approved
supersedes: docs/superpowers/specs/2026-11-11-feat-cicd-001-cpu-deadline-test-margin.md
---

# Let the CPU-deadline refusal test find its cap on any host, and reword the stale FEAT-CICD-001 note (FEAT-CICD-001, revision 2)

## Why a revision

The approved spec (#1811) fixed the test at 80,000 lines and `--max-seconds 0.75`. Its implementation, TeneikaAskew/stocks#1814, fixed the fast-runner failure. Codex's code review of #1814's head `f780118c` then found the opposite failure, and I reproduced it:
- Finding: thread 4540511662, P2.
- What happens: on a slow or loaded host, the 0.75-second deadline fires while the 5 MB body is still being read. `counted_bytes` stays below the body's length, and the unchanged assertion `counted_bytes >= len(body)` fails.
- Codex's environment: `counted_bytes == 4779860` against a 4,960,282-byte body.

Reproduced in the sandbox on 2026-11-11, with the run pinned to one CPU core beside three busy loops:

| Lines | Cap (s) | Result | counted_bytes | source identity |
|---|---|---|---|---|
| 80,000 | 0.75 | refused, CPU deadline | 4,255,572 | set |
| 80,000 | 0.75 | refused, CPU deadline | 715,630 | not set |
| 80,000 | 0.75 (six busy loops, two runs) | refused, CPU deadline | 712,622 | not set |
| 40,000 | 2 (main's values) | refused, CPU deadline | 3,196,910 | set |
| 80,000 | 1.5 | refused, CPU deadline | 5,676,910 | set |
| 80,000 | 3 | refused, CPU deadline | 5,676,910 | set |

Unloaded, 80,000 lines at 1.5 s and 3 s also refuse after the body is read, but the fastest hosted runner seen would finish 80,000 lines in about 3.2 to 3.8 s. That leaves 3 s no margin on the fast side.

A fixed cap has to sit after the body read on the slowest host and before the end of the work on the fastest. On one host the two points are about 25 to 30 times apart: the sandbox reads the body by 0.15 s and finishes 80,000 lines in about 5 s. Across hosts, though, speed varies by more than that ratio, so no single value serves both a fast runner and a loaded machine.

The rest of the original spec stands: the problem it describes (#1796), the 80,000-line body, the #1795 rewording and its source-identity and record obligations.

## Non-goals

- No change to `scripts/maintenance/doc_source_snapshot.py`, its deadline, its ceilings or its CLI.
- No change to any other test in `tests/scripts/test_doc_source_snapshot.py`.
- No change to any other sentence of the FEAT-CICD-001 / SHARED-01 row, to any other row, or to any SITE cell outside the Implementation-source notes table.
- No deployment: a test and documentation change only.

## Approaches considered

1. **Escalating caps (chosen; owner approval 2026-11-11).** The test tries caps of 0.75, 1.5, 3 and 5 seconds and stops at the first refusal that lands after the body was read.
   - A fast host stops at 0.75 s, about 4 to 5 times under the fastest runner's completion.
   - A loaded host moves on to 1.5 s or 3 s.
   - The test fails only when no cap up to the tool's own five-second ceiling interrupts the parse, or when the first attempt finishes the work. The second case means a host about 4 times faster than any runner seen.
2. Fixed 40,000 lines and 1 s: about 2 times headroom on each side. Simpler, but it trades one flake for two smaller ones.
3. Keep 0.75 s and answer the finding: rejected; it knowingly ships a slow-host flake.
4. Measure the host first and derive the cap: rejected; the measurement would be a second timing assumption to keep stable.

## Design

Branch `fix/feat-cicd-001-cpu-deadline-margin` (#1814), its plan repointed at this spec. The test becomes, in substance:

```python
CPU_DEADLINE = "whole verification CPU deadline exceeded"
WALL_DEADLINE = "whole verification deadline exceeded"
for cap in ("0.75", "1.5", "3", "5"):
    refused = repo.cli("produce", "--max-seconds", cap)
    verdict = json.loads(refused.stdout)
    assert refused.returncode != 0, refused.stdout + refused.stderr
    assert verdict["status"] == "unverified"
    assert verdict["reason"] in (CPU_DEADLINE, WALL_DEADLINE)
    # the record is untouched by every refusal, as before
    if verdict["source_identity_sha256"] is not None and verdict["counted_bytes"] >= len(body):
        break
else:
    pytest.fail(f"no cap up to 5 s interrupted the parse after the body was read: {verdict}")
assert verdict["reason"] == CPU_DEADLINE
assert verdict["counted_bytes"] <= MAX_BYTES
assert verdict["elapsed_seconds"] < float(cap) + 0.1
```

The record checks after each attempt are the ones the test already makes: absent when `existing` is False, byte-identical when True, and no `.source-snapshot-*` leftovers. The comment says the caps escalate because hosts differ by more than the read-to-finish ratio of one run. It also keeps the reason for 80,000 lines.

The note row: as in the original spec, plus prose naming the escalation. The prefix is the source hash `produce` reports for the head.

Capacity: n/a, one test and documentation; no job, query, schedule or cloud call. The test's CLI time is at most the sum of the caps, 10.25 s, and on a fast host one 0.75 s attempt.

## Source identity and close-out

Pre-merge: done_when items 4 and 5. After the merge, tracked on the PR and never ticked before the evidence exists: verify main's source and body identity in a fresh clone; set the plan `status: done` on a `docs/` branch; confirm #1795 and #1796 closed.

## Risks

- A host so slow that reading the body takes more than five seconds fails the test. That host cannot run the tool within its own default deadline either, so the failure is real information.
- A host about 4 times faster than the fastest runner seen finishes inside 0.75 s and fails the test, as before; the PR records the margins.
- Main moving before merge makes the sidecar historical; merge main and produce it again.
- The reworded sentence introducing a dead path is caught by done_when 5.
