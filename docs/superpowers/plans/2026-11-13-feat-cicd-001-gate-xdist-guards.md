---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-13-feat-cicd-001-test-suite-audit-a-xdist-guards-r2.md
branch: feature/feat-cicd-001-gate-xdist-guards
status: ready
pr: 1858
---

# Test suite audit, Part A prerequisite: what pytest-xdist and pytest config read from the checkout is process

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the done_when item it advances.

**Goal:** before any gate job installs pytest-xdist, the modules it imports from the checkout (`xdist`, `execnet`, `setproctitle`, `psutil`), the pytest config files beside the gate suites, the path `4` that pytest reads from `-n 4`, and the root `__init__.py` are FEAT-CICD-001 process files, so no other capability's PR can change how the gate suites run.

**Spec:** `docs/superpowers/specs/2026-11-13-feat-cicd-001-test-suite-audit-a-xdist-guards-r2.md` (approved, merged by #1856; it supersedes revision 1, merged by #1855). Issue #1847.

**Base:** main ec430899. One branch, one PR, one author.

## Global constraints

- Gate changes: `xdist`, `execnet`, `setproctitle` and `psutil` join SOURCE_IMPORT_NAMES; `is_process_file()` also counts `is_pytest_config()`, which is true for exactly pytest.ini, .pytest.ini, pytest.toml, .pytest.toml, tox.ini, setup.cfg and pyproject.toml at the root, tests/ and tests/scripts/; `is_suite_path_input()` is true for the path `4`, every path under `4/` and the root `__init__.py`. Nothing else in the gate changes.
- `.github/workflows/registry-check.yml`, `.github/workflows/spec-gate.yml`, `scripts/gate/pinned/registry-check.yml` and `scripts/gate/pinned/spec-gate.yml` stay byte-identical to main. The suite still runs serially in CI.
- Every existing test, case and assertion stays. New tests sit at the end of `tests/scripts/test_spec_gate.py`, module-scope helpers only, real CLI and real Git.
- No hook bypass, no history rewrite. The gate-file red-team pass runs on the frozen head before the one push.

## Task 1: experiment record
Spec: § Problem. Advances done_when 1.
- [ ] The PR body records, on main 3471ba19 with pytest 9.2.0 and pytest-xdist 3.8.0, which root modules the suite command imports serially and with `-n 4`, and that `addopts = --co` in each of the 21 config paths runs no test and exits 0; and, on 126452d3, the `4/` config files and the link `4` under `-n 4`, and a root `__init__.py` under the serial exporter suite.

## Task 2: gate rule
Spec: § Design. Advances done_when 2.
- [ ] The four import names in SOURCE_IMPORT_NAMES; `PYTEST_CONFIG_NAMES`, `is_pytest_config()`, `is_suite_path_input()` and their use in `is_process_file()`.

## Task 3: tests with recorded mutations
Spec: § Design. Advances done_when 3.
- [ ] `test_the_modules_pytest_xdist_imports_are_process_files`: every name as a module and a package at the root, tests/ and tests/scripts/ is a process file, the same names under lib/ are not, a real gate run refuses another capability's PR adding a root `setproctitle.py`, and one adding `lib/setproctitle.py` passes.
- [ ] `test_a_pytest_config_beside_the_gate_suites_is_a_process_file`: all 21 paths are process files, config names elsewhere and look-alike names are not, a real gate run refuses another capability's PR adding `tests/scripts/pytest.ini`, and one adding `lib/pytest.ini` passes.
- [ ] `test_the_worker_count_path_and_a_root_package_initializer_are_process_files`: `4`, paths under `4/` and the root `__init__.py` are process files, `40`, `44/pytest.ini`, `lib/4/pytest.ini` and other `__init__.py` files are not, real gate runs refuse another capability's PR adding `4/pytest.ini` or a root `__init__.py`, and one adding `lib/4/pytest.ini` and `lib/__init__.py` passes.
- [ ] All three recorded failing on main and passing on the head; each failing on its recorded one-line mutations (each import name dropped, each config name and folder dropped, the config rule removed, widened to any folder, widened to a suffix match, the `4` rule removed, the root `__init__.py` rule removed, `4/` widened to any name starting with `4`).

## Task 4: suite and file identity
Spec: done_when 4. Advances done_when 4.
- [ ] Full suite on the exact head serially and with `-n 4` in a clean environment of pytest, pyyaml and pytest-xdist==3.8.0: every node passes, the same node ids in both modes, every node id on main still present.
- [ ] `cmp` of the two live workflows and the two pinned copies against main: identical.

## Task 5: red-team, records, audits, review, close
Spec: done_when 5. Advances done_when 5.
- [ ] Gate-file red-team pass on the frozen head, each bypass proven by running the gate on a concrete change; findings fixed in one batch; then one push.
- [ ] Set this plan's `pr:`; catalog Status and Last reviewed for FEAT-CICD-001; PR-traceability lineage; `(FEAT-CICD-001, SHARED-01)` row rebound with this PR's prose, earlier content kept; sidecar produced from the committed body and `verify` identity-matched.
- [ ] Full-default `docs_audit.py` on main and on the head: nothing new on the head.
- [ ] `python3 scripts/gate/spec_gate.py --pr` with the PR body; current-head review as CLAUDE.md section 2.5 counts it; every required check; zero unresolved threads. The pin stage follows in its own PR.
