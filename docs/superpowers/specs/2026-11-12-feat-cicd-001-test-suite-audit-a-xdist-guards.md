---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-004]
issues: [1847]
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "The PR body records the experiment on main 3471ba19 with pytest 9.2.0 and pytest-xdist 3.8.0 installed: a root `xdist/` or `execnet/` package is imported in place of the installed one by `python3 -m pytest tests/scripts/test_spec_gate.py -q -p no:cacheprovider --noconftest`, serially and with `-n 4`; a root `setproctitle.py` is imported by every `-n 4` run; and `addopts = --co` in each of pytest.ini, .pytest.ini, pytest.toml, .pytest.toml, tox.ini, setup.cfg and pyproject.toml at the root, tests/ and tests/scripts/ (21 paths) makes that command run no test and exit 0."
  - "scripts/gate/spec_gate.py counts as process files, so only FEAT-CICD-001 may change them: a module or package named xdist, execnet, setproctitle or psutil wherever the gate already treats a startup import name as one (the root, scripts/, scripts/maintenance/, tests/ and tests/scripts/), and each of the 21 pytest config paths above; the same names in any other folder stay ordinary code."
  - "New tests in tests/scripts/test_spec_gate.py check every name and path above, a real gate run refusing a feature PR of another capability that adds one, and controls elsewhere that stay accepted; each is recorded failing on main and passing on the head, and failing on a recorded one-line gate mutation for each import name dropped, each config name dropped, each folder dropped, the config rule removed, and the rule widened to any folder or to a suffix match."
  - "Every existing test, case and assertion in tests/scripts/test_spec_gate.py stays and passes; the suite passes serially and with `-n 4` (in a clean environment of exactly pytest, pyyaml and pytest-xdist==3.8.0) on the exact head with the same node ids; .github/workflows/registry-check.yml, .github/workflows/spec-gate.yml, scripts/gate/pinned/registry-check.yml and scripts/gate/pinned/spec-gate.yml stay byte-identical to MAIN; beyond the gate and its suite the PR changes only its own plan and the delivery records (FEAT-CICD-001 catalog and traceability entries, SHARED-01 note row and its sidecar)."
  - "Own delivery records, ordinary SHARED-01 source proof, full-default main and proposed docs audits with no new finding, the gate-file red-team pass on the frozen head, current-head review as CLAUDE.md section 2.5 counts it, every required check and zero unresolved threads are complete; no criterion of the test suite audit spec is claimed by this PR."
status: approved
supersedes: null
---

# Test suite audit, Part A prerequisite: what pytest-xdist and pytest config read from the checkout is process

## Authority

The Part A gate-policy stage (#1853) red-team pass found two gaps that predate it and lie outside
`docs/superpowers/specs/2026-11-12-feat-cicd-001-test-suite-audit-r2.md`, whose pin stage may change
only the two pinned workflow copies. The owner asked that the gaps the audit found be fixed (thread
"Time the slowest registry check tests", 18:57 UTC) and to start the next stage (23:42 UTC). This
spec is that fix, delivered before the pin stage so that pytest-xdist is never installed in a gate
job while the files it imports, and the files that set the suite's options, are outside FEAT-CICD-001.
It adds no criterion to the parent and claims none of the parent's.

## Problem

The gate suite runs as `python3 -m pytest tests/scripts/test_spec_gate.py ...`, which puts the
checkout first on `sys.path`. With pytest-xdist installed, pytest loads the `xdist` plugin, which
imports `execnet`; a root `xdist/` or `execnet/` package is imported in place of the installed one,
even on a serial run, and each worker imports a root `setproctitle.py` when one exists. `psutil` is
imported when xdist counts CPUs (not with `-n 4`, but cheaply covered). None of these names is in
SOURCE_IMPORT_NAMES, so any feature PR may add one and every later gate-suite run imports it.

pytest also takes its options from the first config file in the suites' folder or a parent up to
the checkout. None of the seven config names is a process file, so a feature PR may add
`addopts = --co` beside the suites; from then on the suite contract command collects every test,
runs none and passes, and the base-suite job judges every later proposed gate with it.

## Design

Add `xdist`, `execnet`, `setproctitle` and `psutil` to SOURCE_IMPORT_NAMES, so the existing startup
import rule (root, scripts/, scripts/maintenance/, tests/, tests/scripts/; module, package and cache
forms) covers them. Add the 21 pytest config paths to `is_process_file()` by exact path. Nothing
else in the gate changes: no workflow, pinned copy, PYTEST_ARGS or suite command changes, and the
suite still runs serially in CI.

## Capacity

No workload changes: the suite still runs serially in CI. Two new tests, each one in-process check
of the rule plus two gate runs, add about one second.

## Risks

- **A future root pyproject.toml becomes FEAT-CICD-001's work.** Intended: pytest reads it as config.
  None exists today.
- **A later xdist release imports another name.** The pin stage installs one exact version; a version
  change is a reviewed gate change that repeats this experiment.

## Rollback

Revert the PR. Nothing outside the gate and its suite changes.
