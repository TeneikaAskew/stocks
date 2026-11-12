---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-12-feat-cicd-001-test-suite-audit-a-gate-policy.md
branch: feature/feat-cicd-001-gate-four-workers
status: ready
pr: 1853
---

# Test suite audit, Part A stage one: the gate accepts exactly the four-worker suite command

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the done_when item it advances.

**Goal:** `scripts/gate/spec_gate.py` accepts the gate suite contract command `python3 -m pytest tests/scripts/test_spec_gate.py` with the extra pair `-n 4`, once, beside PYTEST_ARGS, and refuses every other worker form; a gate workflow installs `pytest-xdist` only at an exact `==` version; the suite gains the #1849 refusal tests for a spec with no `status` and a spec status outside draft, approved and superseded.

**Spec:** `docs/superpowers/specs/2026-11-12-feat-cicd-001-test-suite-audit-a-gate-policy.md` (approved stage primary, merged by #1850), under the parent `docs/superpowers/specs/2026-11-12-feat-cicd-001-test-suite-audit-r2.md` (items 3 and 4). Issues #1847 and #1849.

**Base:** main dfb78456. One branch, one PR, one author.

## Global constraints

- Gate changes: `invokes()` strips the first `-n 4` pair from the tail only for the suite contract command, and not where the pair follows `-p`; `tool_offence()` refuses any line whose words, read as the shell reads them (quotes and backslashes dropped, `\` continuations joined), name xdist other than as `pytest-xdist` (`-`, `_` or `.` joined, any case, optional extra) with exactly one `==` version, so the pin holds in a pip line, in any other installer's (`uv pip`, `pipx`) and in a file a line writes. Nothing else in the gate changes.
- `.github/workflows/registry-check.yml`, `.github/workflows/spec-gate.yml`, `scripts/gate/pinned/registry-check.yml` and `scripts/gate/pinned/spec-gate.yml` stay byte-identical to main. The suite still runs serially in CI until the pin and live stages.
- Every existing test, case and assertion stays. New tests sit at the end of `tests/scripts/test_spec_gate.py`, module-scope helpers only, real CLI and real Git.
- No hook bypass, no history rewrite. The gate-file red-team pass runs on the frozen head before the one push.

## Task 1: gate policy
Spec: § Design. Advances done_when 2.
- [ ] `SUITE_COMMAND` and `SUITE_WORKERS` constants and the `xdist_unpinned()` helper; `invokes()` and `tool_offence()` changes as in Global constraints.

## Task 2: acceptance and refusal tests with recorded mutations
Spec: § Design, § Risks. Advances done_when 2.
- [ ] `test_the_gate_suite_may_run_on_exactly_four_workers`: both gate workflows accept the suite with `-n 4`, alone and after an exactly pinned pytest-xdist install. Recorded failing on main's gate and passing on the head.
- [ ] `test_no_other_worker_form_runs_the_gate_suite` (each form in turn: `-n 3`, `-n auto`, `-n4`, `--numprocesses 4`, `--dist load`, `-p xdist`, `--maxprocesses 4`, a second `-n 4`, `-p -n 4`) and `test_four_workers_belong_to_the_gate_suite_alone`: each passing on the head and failing on a recorded one-line mutation that lets its form through.
- [ ] `test_pytest_xdist_installs_only_at_an_exact_version` (each unpinned spelling, in both workflows, through `uv pip` and `pipx`, and as the shell spells it with quotes, backslashes or a continuation): passing on the head, failing on main's gate and on the recorded mutations that turn the rule off, accept any text after `==`, or read the words without the shell's quote removal.

## Task 3: the #1849 tests
Spec: § Problem. Advances done_when 3.
- [ ] `test_a_spec_without_a_status_key_is_named_missing` and `test_a_spec_status_outside_the_three_is_refused` (each status in turn): passing on the head, failing on the mutation that removes `status` from REQUIRED_SPEC_KEYS or adds that status to SPEC_STATUSES.

## Task 4: suite and file identity
Spec: done_when 4. Advances done_when 4.
- [ ] Full suite on the exact head, serially and with `-n 4`: every node passes, the same node ids in both modes, and every node id on main is still present.
- [ ] `cmp` of the two live workflows and the two pinned copies against main: identical.

## Task 5: experiment record
Spec: § Authority. Advances done_when 1.
- [ ] The PR body records the Part A experiment on main 56d63397 (local and hosted run 43286379174): wall-clock of three serial and three `-n 4` runs, the 185 node ids in every run, the failing node ids of each mutated-gate control in both modes, and the median reductions.

## Task 6: red-team, records, audits, review, close
Spec: done_when 5. Advances done_when 5.
- [ ] Gate-file red-team pass on the frozen head: one reviewer per attack surface (shell, YAML and Actions, policy), each bypass proven by running the gate on a concrete snippet; findings fixed in one batch; then one push.
- [ ] Set this plan's `pr:`; catalog Status and Last reviewed for FEAT-CICD-001; PR-traceability lineage; `(FEAT-CICD-001, SHARED-01)` row rebound with this stage's prose, earlier content kept; sidecar produced from the committed body and `verify` identity-matched.
- [ ] Full-default `docs_audit.py` on main and on the head: nothing new on the head.
- [ ] `python3 scripts/gate/spec_gate.py --pr` with the PR body; current-head review as CLAUDE.md section 2.5 counts it; every required check; zero unresolved threads. The pin and live stages stay with their own PRs.
