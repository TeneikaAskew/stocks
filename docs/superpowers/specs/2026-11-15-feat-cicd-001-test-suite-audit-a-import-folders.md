---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-004]
issues: [1847]
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "The PR body records the experiment on main 2eba6ebb with pytest 9.2.0 and pytest-xdist 3.8.0 installed, running `python3 -m pytest tests/scripts/test_spec_gate.py -q -p no:cacheprovider --noconftest` serially and with `-n 4`, and `python3 -m pytest tests/scripts/test_export_model_registry.py -q -p no:cacheprovider --noconftest`: a root `setproctitle/setproctitle.py` with no `__init__.py` runs in the controller and every worker of the `-n 4` run and not in the serial run, and a payload there makes the gate suite report every test passed without running one; a root `nt/_getfullpathname.py` runs in every one of those runs, serial included; a root `zzq-1.0.dist-info` folder whose `entry_points.txt` names a root module under `[pytest11]` loads that module as a pytest plugin in every one of those runs; and, as controls, a root `platform/x.py` and a root `json/decoder.py` do not run, because the regular standard-library module of that name is found first."
  - "scripts/gate/spec_gate.py counts as process files, so only FEAT-CICD-001 may change them: every path under a folder named after a startup import name, at each location where the gate already treats that name as one (the root, scripts/, scripts/maintenance/, tests/ and tests/scripts/), when the name is not in sys.stdlib_module_names or when the gate's own interpreter cannot find a regular module or package of that name outside the checkout; and every path under a root folder, or a root file, whose name ends in `.dist-info` or `.egg-info`. A folder named after a standard-library module the interpreter does find (the 36 tracked files under `platform/` today) stays ordinary code, and the existing initializer and module rules are unchanged."
  - "New tests in tests/scripts/test_spec_gate.py check each shape above, a real gate run refusing a feature PR of another capability that adds `setproctitle/setproctitle.py`, `psutil/x.py`, `xdist/x.py`, `execnet/x.py`, `nt/_getfullpathname.py`, `tests/scripts/setproctitle/setproctitle.py` or `zzq-1.0.dist-info/entry_points.txt`, and controls that stay accepted (`platform/x.py`, `json/decoder.py`, `lib/setproctitle/x.py`, `docs/zzq.dist-info.md`); each is recorded failing on main and passing on the head, and failing on a recorded one-line gate mutation for: the folder rule removed, the third-party names exempted, the availability check inverted, each location dropped, the `.dist-info` suffix dropped and the `.egg-info` suffix dropped."
  - "Every existing test, case and assertion in tests/scripts/test_spec_gate.py stays and passes; the suite passes serially and with `-n 4` (in a clean environment of exactly pytest, pyyaml and pytest-xdist==3.8.0) on the exact head with the same node ids; .github/workflows/registry-check.yml, .github/workflows/spec-gate.yml, scripts/gate/pinned/registry-check.yml and scripts/gate/pinned/spec-gate.yml stay byte-identical to MAIN; beyond the gate and its suite the PR changes only its own plan and the delivery records (FEAT-CICD-001 catalog and traceability entries, SHARED-01 note row and its sidecar)."
  - "Own delivery records, ordinary SHARED-01 source proof, full-default main and proposed docs audits with no new finding, the gate-file red-team pass on the frozen head, current-head review as CLAUDE.md section 2.5 counts it, every required check and zero unresolved threads are complete; no criterion of the test suite audit spec is claimed by this PR."
status: approved
supersedes: null
---

# Test suite audit, Part A prerequisite follow-up: folders the gate suites can import from the checkout

## Authority

A prerequisite of Part A's live stage under
`docs/superpowers/specs/2026-11-12-feat-cicd-001-test-suite-audit-r2.md` (done_when item 6), in the
same role as the prerequisite revision merged in #1856 and delivered in #1858. The gate-file
red-team pass on the live stage's frozen head (#1968, 5d18e713) found that the four-worker command
runs a file a PR of any capability can add, so the live stage (spec merged in #1966) waits for this
change. It adds no criterion to the parent and claims none of the parent's. Issue #1847.

## Problem

Reproduced on main 2eba6ebb with pytest 9.2.0 and pytest-xdist 3.8.0:

- **A namespace folder stands in for a missing optional import.** Every pytest-xdist worker runs
  `from setproctitle import setproctitle` and carries on without it when it is not installed. A root
  folder `setproctitle/` with no `__init__.py` is a namespace package, so that line imports
  `setproctitle/setproctitle.py` from the checkout in the controller and in all four workers. A
  payload there that stubs the test call and marks every report passed makes the gate suite report
  "194 passed" in about 12 seconds. The gate counts `setproctitle.py` and `setproctitle/__init__.py`
  as process files, not other paths under the folder, so another capability's PR that adds it is
  accepted. The serial command on main never runs that import; the live stage makes it run in the
  registry job of every PR and, once such a file is on main, in every base-suite run.
- **The same holds for any standard-library name the runner does not have.** `ntpath`, which every
  run imports through `pathlib`, runs `from nt import _getfullpathname` inside a try block on Linux;
  a root `nt/_getfullpathname.py` runs in every suite run today, serial included. On Linux the
  missing names include `nt`, `msvcrt`, `_winapi` and `_wmi`.
- **A root `*.dist-info` folder registers a pytest plugin.** `python3 -m pytest` puts the checkout
  first on `sys.path`, and pytest loads every `pytest11` entry point it finds there, so a root
  `zzq-1.0.dist-info/entry_points.txt` naming a root module loads it as a plugin in both suite
  commands, serially too. No rule covers `.dist-info` or `.egg-info`.

A namespace folder does not stand in for a module the interpreter does find: `platform/` (an
application folder here) and `json/` are passed over for the regular standard-library modules, as
the gate's own `source_import_shadow` comment says.

## Design

`source_import_shadow()` keeps its module and initializer rules and adds one: a path under a folder
named after a startup import name, at the locations it already checks, is a process file when the
name is not a standard-library name (pytest-xdist, its optional imports and the other third-party
names in `SOURCE_IMPORT_NAMES`) or when `importlib.machinery.PathFinder.find_spec` on the gate's
own `sys.path` without the checkout finds no regular module or package of that name and it is not a
built-in module. `is_process_file()` also counts a root path whose first component ends in
`.dist-info` or `.egg-info`. No workflow, pinned copy, PYTEST_ARGS or suite command changes.

## Capacity

No workload changes: CI still runs the gate suite serially until the live stage. The rule calls
`find_spec` at most once per standard-library name per gate run, and the new tests add a few
seconds.

## Risks

- **The gate job and the suite jobs could run different interpreters.** Both run `python3` on
  ubuntu-latest today. If a later runner had a standard-library module the suite's runner lacks,
  the gate would pass over a folder of that name; the third-party names are counted whatever is
  installed.
- **A future application folder named after a missing standard-library or third-party name becomes
  FEAT-CICD-001's work.** None exists today; `platform/` is unaffected.
- **Older gaps stay open.** A gate-workflow step that writes a pytest config before the suite step
  (`tests/tox.ini` serially, `4/tox.ini` with four workers) needs a change to the gate workflows
  themselves and goes to the spec for the gaps listed in #1903, with them.

## Rollback

Revert the PR. Nothing outside the gate and its suite changes.
