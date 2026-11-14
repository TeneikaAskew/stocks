---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-004]
issues: [1847]
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "The PR body records the experiment on main 3471ba19 with pytest 9.2.0 and pytest-xdist 3.8.0 installed: a root `xdist/` or `execnet/` package is imported in place of the installed one by `python3 -m pytest tests/scripts/test_spec_gate.py -q -p no:cacheprovider --noconftest`, serially and with `-n 4`; a root `setproctitle.py` is imported by every `-n 4` run; and `addopts = --co` in each of pytest.ini, .pytest.ini, pytest.toml, .pytest.toml, tox.ini, setup.cfg and pyproject.toml at the root, tests/ and tests/scripts/ (21 paths) makes that command run no test and exit 0. It also records, on 126452d3 with the same tools, that the same command with `-n 4` runs no test and exits 0 when `4/pytest.ini`, `4/setup.cfg` or `4/pyproject.toml` holds `addopts = --co`, or when a symbolic link named `4` points to a folder holding such a file; and that a root `__init__.py` is imported by `python3 -m pytest tests/scripts/test_export_model_registry.py -q -p no:cacheprovider --noconftest`, where two lines in it make every test pass without running its body."
  - "scripts/gate/spec_gate.py counts as process files, so only FEAT-CICD-001 may change them: a module or package named xdist, execnet, setproctitle or psutil wherever the gate already treats a startup import name as one (the root, scripts/, scripts/maintenance/, tests/ and tests/scripts/); each of the 21 pytest config paths above; the path `4` and every path under `4/`; and the root `__init__.py`. The same import and config names in any other folder stay ordinary code."
  - "New tests in tests/scripts/test_spec_gate.py check every name and path above, a real gate run refusing a feature PR of another capability that adds a root `setproctitle.py`, `tests/scripts/pytest.ini`, `4/pytest.ini` or a root `__init__.py`, and controls elsewhere that stay accepted; each is recorded failing on main and passing on the head, and failing on a recorded one-line gate mutation for each import name dropped, each config name dropped, each folder dropped, the config rule removed, the rule widened to any folder or to a suffix match, the `4` rule removed and the root `__init__.py` rule removed."
  - "Every existing test, case and assertion in tests/scripts/test_spec_gate.py stays and passes; the suite passes serially and with `-n 4` (in a clean environment of exactly pytest, pyyaml and pytest-xdist==3.8.0) on the exact head with the same node ids; .github/workflows/registry-check.yml, .github/workflows/spec-gate.yml, scripts/gate/pinned/registry-check.yml and scripts/gate/pinned/spec-gate.yml stay byte-identical to MAIN; beyond the gate and its suite the PR changes only its own plan and the delivery records (FEAT-CICD-001 catalog and traceability entries, SHARED-01 note row and its sidecar)."
  - "Own delivery records, ordinary SHARED-01 source proof, full-default main and proposed docs audits with no new finding, the gate-file red-team pass on the frozen head, current-head review as CLAUDE.md section 2.5 counts it, every required check and zero unresolved threads are complete; no criterion of the test suite audit spec is claimed by this PR."
status: approved
supersedes: docs/superpowers/specs/2026-11-12-feat-cicd-001-test-suite-audit-a-xdist-guards.md
---

# Test suite audit, Part A prerequisite: what pytest-xdist and pytest config read from the checkout is process (revision 2)

## Authority

Revision 2 of the prerequisite merged in #1855, which it supersedes. The gate-file red-team pass on
that spec's frozen head (126452d3) found two more files the gate suite commands read from the
checkout that the first revision left out, one of which defeats the four-worker command the pin
stage installs. The owner asked that the gaps the audit found be fixed (thread "Time the slowest
registry check tests", 18:57 UTC on 2026-11-12) and to start the next stage (23:42 UTC). Where the
pin stage spec (`2026-11-12-feat-cicd-001-test-suite-audit-a-pin.md`) says it opens after the
prerequisite merges, this revision is that prerequisite. It adds no criterion to the parent and
claims none of the parent's.

## Problem

Unchanged from revision 1: with pytest-xdist installed, a root `xdist/` or `execnet/` package is
imported in place of the installed one, each `-n 4` worker imports a root `setproctitle.py`, and a
pytest config file beside the suites (`addopts = --co`) makes the suite contract command run nothing
and pass. None of those files is a process file on main.

Found by the red-team pass, reproduced on 126452d3 with pytest 9.2.0 and pytest-xdist 3.8.0:

- **The worker count is read as a path.** Before plugins load, pytest locates its config file from
  the command's arguments with only its own options known, so the `4` of `-n 4` is taken as a path.
  When `4` is a folder, or a symbolic link to one, holding a pytest config file, that file becomes
  the config: `4/pytest.ini` with `addopts = --co` turns the four-worker gate suite into
  "193 tests collected" with exit 0, and so do `4/setup.cfg` and `4/pyproject.toml`, and a link `4`
  to an ordinary folder holding `pytest.ini`. The serial commands are unaffected.
- **A root `__init__.py` is imported by both suite commands.** `tests/` and `tests/scripts/` are
  packages, so a root `__init__.py` makes pytest import the checkout itself as a package before the
  suite; two lines there that replace the test-call function make the exporter suite report
  "41 passed" in one second with every test body skipped. The startup import rule names
  `tests/__init__.py` and `tests/scripts/__init__.py`, not the root one.

## Design

As revision 1: `xdist`, `execnet`, `setproctitle` and `psutil` join SOURCE_IMPORT_NAMES, and the 21
pytest config paths are process files by exact path. In addition, `is_process_file()` counts the
path `4` and every path under `4/` (any file there could become the config, and a link at `4` can
point anywhere), and the root `__init__.py`. Nothing else in the gate changes: no workflow, pinned
copy, PYTEST_ARGS or suite command changes, and the suite still runs serially in CI.

The config names are matched by name, not by content. pytest reads a `pyproject.toml` with no
pytest section as its config when it finds no other (on 9.2.0 a `[tool.ruff]`-only
`tests/scripts/pyproject.toml` becomes the configfile and moves the rootdir), so a content check
would leave that open and add a parser to keep right.

## Capacity

No workload changes: the suite still runs serially in CI. The new tests, each an in-process check of
the rule plus gate runs, add a few seconds.

## Risks

- **A future root, tests/ or tests/scripts/ pyproject.toml, setup.cfg or tox.ini becomes
  FEAT-CICD-001's work, even one without a pytest section.** Intended, for the reason above. None
  exists today.
- **A future top-level folder named `4` becomes FEAT-CICD-001's work.** None exists today.
- **A later xdist release imports another name.** The pin stage installs one exact version; a version
  change is a reviewed gate change that repeats this experiment.

## Rollback

Revert the PR. Nothing outside the gate and its suite changes.
