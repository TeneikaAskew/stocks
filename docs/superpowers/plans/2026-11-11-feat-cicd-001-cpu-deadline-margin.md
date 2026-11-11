---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-11-feat-cicd-001-cpu-deadline-test-margin.md
branch: fix/feat-cicd-001-cpu-deadline-margin
pr: null
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

**Spec:** docs/superpowers/specs/2026-11-11-feat-cicd-001-cpu-deadline-test-margin.md

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
