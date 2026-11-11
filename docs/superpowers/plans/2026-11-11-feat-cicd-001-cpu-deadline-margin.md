---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-11-feat-cicd-001-cpu-deadline-test-margin-r2.md
branch: fix/feat-cicd-001-cpu-deadline-margin
pr: 1814
status: ready
---

# CPU-deadline refusal test margin and the stale SHARED-01 pin sentence: implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

**Goal:** stop `test_actual_fallback_parser_cpu_deadline_preserves_absent_or_valid_record` failing on fast runners
(#1796), and reword the FEAT-CICD-001 / SHARED-01 note sentence that #1794 made false (#1795), in one PR.

**Architecture:** three constants and one comment in one test; the FEAT-CICD-001 / SHARED-01 note row then takes a new
source-identity prefix, prose for this test change, and the reworded sentence in its earlier text; the sidecar is
produced from the final committed SITE body.

**Tech stack:** pytest, `scripts/maintenance/doc_source_snapshot.py`, `scripts/maintenance/docs_audit.py`,
`scripts/gate/spec_gate.py`.

**Spec:** docs/superpowers/specs/2026-11-11-feat-cicd-001-cpu-deadline-test-margin-r2.md (revision 2, merged in #1817, superseding docs/superpowers/specs/2026-11-11-feat-cicd-001-cpu-deadline-test-margin.md)

**Preconditions:** the spec is on main; the branch is cut from that main.

## Global Constraints

- Only these files change: `tests/scripts/test_doc_source_snapshot.py` (the one test), `docs/product/03-SITE-TRACEABILITY.md`
  (the FEAT-CICD-001 / SHARED-01 row only), `docs/review-evidence/site-source-snapshot.json`,
  `docs/product/02-FEATURE-CATALOG.md` (FEAT-CICD-001 record only), `docs/product/12-PR-ISSUE-TRACEABILITY.md`
  (FEAT-CICD-001 lineage only) and this plan.
- New values, verbatim: `80000` lines, `"--max-seconds", "0.75"`, `assert verdict["elapsed_seconds"] < 0.85`.
- `scripts/maintenance/doc_source_snapshot.py` and every other test are unchanged.
- No backticked path to a file absent on the head, no `|` in the row, no em or en dash anywhere this plan writes.
- Verifier ceilings, verbatim: `--max-seconds 5 --max-input-bytes 12582912 --max-entries 20000`.
- No gate file changes (`scripts/gate/`, `.githooks/pre-commit`, the two gate workflows, their suites).

## Review Focus

- The cap set before the source identity is computed on a slow host: the refusal carries no
  `source_identity_sha256` and the test fails. Task 3 records the lowest cap that still carries it.
- The cap set after the bounded work can finish on a fast host: the run succeeds and the test fails as on #1791 and
  #1802. Task 1 reproduces that failure for main's values; Task 2 shows the new values refuse at the same stand-in.
- A weakened assertion: every assertion other than the elapsed bound must read exactly as on main.
- A changed byte outside the FEAT-CICD-001 / SHARED-01 row: `note_delta` refuses a foreign row change.
- Main moving before merge: the sidecar goes historical; merge main and produce again.

## Task 1: reproduce main's failure first
Spec: § Measurements, § Design 1. Advances done_when 2.
- [ ] With the test file as on main, change only `40000` to `20000` in the one test (a stand-in for a host about twice
      as fast), run `python3 -m pytest "tests/scripts/test_doc_source_snapshot.py::test_actual_fallback_parser_cpu_deadline_preserves_absent_or_valid_record" -q`.
      Expected: both parameters FAIL with `assert 0 != 0` and an `identity-matched` verdict whose `elapsed_seconds`
      is under 2. Record the output, then `git checkout -- tests/scripts/test_doc_source_snapshot.py`. Nothing is committed.

## Task 2: the new margin
Spec: § Design 1. Advances done_when 1 and 2.
- [ ] In the one test: `40000` to `80000`, `"2"` to `"0.75"`, `< 2.1` to `< 0.85`, and replace the four comment lines
      above the elapsed assertion with a comment saying the cap must fall after the source identity is computed and
      before the bounded work can finish on a fast host, citing the measured figures (source identity by 0.2 s in the
      sandbox at 80,000 lines; 1.91 s for 40,000 lines on the fastest runner seen) and #1796.
- [ ] Stand-ins for a faster host: temporarily set `80000` to `40000`, then to `20000`, and run the test each time.
      Expected: PASS (refusal with the CPU-deadline reason and a source identity). Restore `80000`.
- [ ] Run the test ten times (`for i in $(seq 10); do python3 -m pytest "<test id>" -q || break; done`). Expected:
      20 passed in total (two parameters per run).
- [ ] `python3 -m pytest tests/scripts/test_doc_source_snapshot.py -q`. Expected: all pass.
- [ ] Commit: `test(snapshot): give the CPU-deadline refusal a measured margin`.

## Task 3: record the margins
Spec: § Measurements. Advances done_when 3.
- [ ] With the head's CLI on the test's own `complex_body_repo` fixture (a read-only scratch driver outside the repo),
      record for 80,000 lines the refusals at `--max-seconds` 0.15, 0.2 and 0.25 (which carry a source identity) and
      the completion time at the default cap for 20,000, 40,000 and 60,000 lines. State the margins of 0.75 s against
      both in the PR body. Nothing is committed.

## Task 4: note row and sidecar
Spec: § Design 2 and 3. Advances done_when 4.
- [ ] `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`;
      take its `source_identity_sha256`, then `git checkout -- docs/review-evidence/site-source-snapshot.json`.
- [ ] In the FEAT-CICD-001 / SHARED-01 row, the cell becomes `source_identity_sha256=<hash>; ` + prose naming the one
      test change (the test, the new body size, cap and elapsed bound, and why) + ` Earlier: ` + the cell's previous
      text after its old prefix, byte for byte except that exactly
      "`tests/meta/test_model_registry_consistency.py` pins this document at one dead path, the FEAT-DEPLOY-001 note's citation of the deleted prompt renderer (owner decision on #1788)."
      becomes
      "`tests/meta/test_model_registry_consistency.py` pinned this document at one dead path, the FEAT-DEPLOY-001 note's citation of the deleted prompt renderer (owner decision on #1788), until #1794 removed the pin."
      Check that the old sentence occurred exactly once. Commit: `docs(site): bind the FEAT-CICD-001 note to the CPU-deadline test margin`.
- [ ] `produce` again with the same arguments; commit the sidecar: `docs(site): commit the FEAT-CICD-001 source identity sidecar`.
- [ ] `verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000`.
      Expected: exit 0, `identity-matched`, `eligible_route: declared-note`, `source_identity_sha256` equal to the prefix.
      `git diff --exit-code origin/main -- docs/DOC_REGISTRY.md` exits 0; `git diff origin/main -- docs/product/03-SITE-TRACEABILITY.md`
      changes the FEAT-CICD-001 / SHARED-01 row only.

## Task 5: close
Spec: § Done when. Advances done_when 5, 6 and 7.
- [ ] Catalog: in the FEAT-CICD-001 record, add the clause "CPU-deadline refusal test given a measured margin (#<this PR>)"
      to Status and set Last reviewed to the head commit's date; traceability: this PR under FEAT-CICD-001's lineage.
      Touch no other record or row. Set this plan's `pr` to the PR number. Commit.
- [ ] `docs_audit.py --issues-snapshot <capture under a day old> --no-owning-job-check --json` on the head and on main
      with one capture, diffed by (check, document, severity, detail): `NEW 0`.
- [ ] `python3 -m pytest tests/scripts/test_doc_source_snapshot.py tests/meta -q` passes.
      `python3 scripts/gate/spec_gate.py --pr origin/main` in ready mode passes; tick every done_when box in the PR
      body with its evidence; the body closes #1795 and #1796.

## Revision 2 (spec 2026-11-11-feat-cicd-001-cpu-deadline-test-margin-r2.md, merged in #1817)

Codex's code review of `f780118c` (thread 4540511662) showed the fixed 0.75-second cap failing on a loaded host. Tasks 1 to 5 above stand as done; Tasks 6 to 8 move the test to escalating caps and refresh the evidence, the note and the records.

## Task 6: escalating caps, red first
Spec: § Design (revision 2). Advances done_when 1 and 2.
- [ ] Red, at `f780118c`'s test: pinned to one CPU core beside six busy loops
      (`taskset -c 0` for the test and each `sh -c 'while :; do :; done'`), both parameters fail at
      `assert verdict["source_identity_sha256"] is not None`. Beside three busy loops, record every run, passes included,
      and the driver runs of the same `produce` call (counted 4,255,572 and 715,630, below the 4,960,282-byte body).
- [ ] In the one test, replace the single `produce --max-seconds 0.75` call and its reason, source-identity,
      counted-bytes and elapsed assertions with the loop in spec r2 § Design. Exact behaviour:
      - caps `("0.75", "1.5", "3", "5")`, in that order;
      - each attempt asserts a nonzero exit, `status == "unverified"`, and a reason in
        (`whole verification CPU deadline exceeded`, `whole verification deadline exceeded`);
      - each attempt checks the record: absent when `old is None`, else byte-equal to `old`;
      - stop at the first verdict with a source identity and `counted_bytes >= len(body.encode("utf-8"))`;
      - with no stop, `pytest.fail` with the last verdict;
      - after the loop, assert the CPU-deadline reason, `counted_bytes <= MAX_BYTES` and
        `elapsed_seconds < float(cap) + 0.1`, then the unchanged no-leftover check.
      The comment says the caps escalate because hosts differ by more than the read-to-finish ratio of one run, and keeps
      why the body is 80,000 lines. No other test changes.
- [ ] Green:
      - six busy loops: both parameters pass (stopping at 1.5 s);
      - unloaded: the fast-host stand-ins at 20000 and 40000 lines pass;
      - ten consecutive unloaded runs pass;
      - the whole file passes.
- [ ] Commit: `test(snapshot): escalate the CPU-deadline cap until it lands after the body read`.

## Task 7: note and sidecar
Spec: § Design (revision 2). Advances done_when 3 and 4.
- [ ] Margins on the head's CLI: 80,000 lines at caps 0.75, 1.5, 3 and 5, unloaded and beside six busy loops, and at which
      step each stops. The unloaded completions for 20000, 40000 and 60000 lines stand from Task 3.
- [ ] In the FEAT-CICD-001 / SHARED-01 row, replace this PR's prose (between the prefix and ` Earlier: `) with prose
      naming the escalation; keep ` Earlier: ` and everything after it byte for byte. Take the source hash from
      `produce`, rebind the prefix, commit, `produce` again, commit the sidecar alone, `verify` with the fixed ceilings.

## Task 8: records and close
Spec: § Done when (revision 2). Advances done_when 5, 6 and 7.
- [ ] Catalog Status clause and lineage entry name the revised spec (#1817); Last reviewed the head commit's date.
- [ ] Audit pair with one fresh capture: `NEW 0`. Suites on the head pass. The ready-mode gate passes with every r2
      done_when box ticked and its evidence. Reply on thread 4540511662 with the fix commit and resolve it.
