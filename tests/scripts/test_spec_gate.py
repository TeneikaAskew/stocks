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

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

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
    assert list(workflow.get("on", workflow.get(True))) == ["pull_request_target"]
    checkout = next(s for s in workflow["jobs"]["gate"]["steps"] if s.get("uses", "").startswith("actions/checkout"))
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.base.sha }}"


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
    manifest = {"package.json": "{}\n"}
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
    r = pr(repo, BRANCH, {**CODE, newer: spec(status="draft", supersedes=SPEC)})
    assert r.returncode == 1 and f"{SPEC} is superseded by {newer}" in r.stdout, r.stdout
    r = pr(repo, BRANCH, {**CODE, SPEC: spec(status="superseded")})
    assert r.returncode == 1 and "is status: superseded" in r.stdout, r.stdout


def test_the_plan_names_the_spec_that_is_enforced(repo):
    """stocks#1205 r4116983576 (spec_gate.py:111); solyra#72 r4116980726 (:151, P1).

    The old gate found an approved spec by FEAT-ID on its own and only checked
    that the plan's `spec:` path existed, so a plan could point at another
    feature's spec, or at a newer draft, and still pass.
    """
    other = "docs/superpowers/specs/2026-09-02-data-nulls.md"
    r = pr(repo, BRANCH, {**CODE, other: spec(feat_id="FEAT-DATA-001", req_ids="[REQ-DATA-001]"),
                          PLAN: plan(spec=other)})
    assert r.returncode == 1 and "the plan's spec serves FEAT-DATA-001, not FEAT-MODEL-001" in r.stdout, r.stdout
    draft = "docs/superpowers/specs/2026-09-20-model-decisions-v2.md"
    r = pr(repo, BRANCH, {**CODE, draft: spec(status="draft"), PLAN: plan(spec=draft)})
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
    r = pr(repo, BRANCH, {**CODE, second: plan(branch="feature/feat-model-001-other")})
    assert r.returncode == 0, r.stdout
    r = pr(repo, BRANCH, {**CODE, second: plan()})
    assert r.returncode == 1 and "one plan = one branch" in r.stdout, r.stdout


def test_done_when_and_the_other_list_fields_must_be_lists(repo):
    """stocks#1205 r4116983587 (spec_gate.py:102); solyra#72 r4116980740 (:102).

    The old gate checked emptiness only when done_when parsed as a list, so
    `done_when: TBD` or `done_when: ""` authorized code with nothing to
    verify. issues and canvases get the same type check.
    """
    for value in ("TBD", '""'):
        r = pr(repo, BRANCH, {**CODE, SPEC: spec(done_when=value)})
        assert r.returncode == 1 and "done_when must be a non-empty list" in r.stdout, (value, r.stdout)
    r = pr(repo, BRANCH, {**CODE, SPEC: spec(issues="#12")})
    assert r.returncode == 1 and "issues must be a list" in r.stdout, r.stdout


def test_req_ids_name_defined_requirements(repo):
    """stocks#1205 r4117591702 (spec_gate.py:98).

    The old gate never read req_ids. Each must be shaped REQ-XXX-000 and, where
    the requirements doc defines IDs (stocks), be one of them. Solyra has no
    requirements doc, so there the check is shape only.
    """
    r = pr(repo, BRANCH, {**CODE, SPEC: spec(req_ids="[REQ-FAKE-999]")})
    assert r.returncode == 1 and "req_ids not defined in" in r.stdout, r.stdout
    r = pr(repo, BRANCH, {**CODE, SPEC: spec(req_ids="[REQ-DOES-NOT-EXIST-999]")})
    assert r.returncode == 1 and "not shaped REQ-XXX-000" in r.stdout, r.stdout
    r = pr(repo, BRANCH, {**CODE, SPEC: spec(req_ids="[]")})
    assert r.returncode == 1 and "req_ids must be a non-empty list" in r.stdout, r.stdout
    r = pr(repo, BRANCH, {**CODE, SPEC: spec(req_ids="[REQ-FAKE-999]"), REQUIREMENTS: None})
    assert r.returncode == 0, r.stdout


def test_commit_mode_reads_what_is_staged(repo):
    """stocks#1205 r4117017699 (spec_gate.py:85); solyra#72 r4117710096 (:179).

    The old gate listed the staged files but read specs and plans from the
    working tree, so a spec staged as draft and flipped to approved on disk
    passed, although the commit carries the draft.
    """
    _git(repo, "checkout", "-q", "-B", BRANCH, "base")
    write(repo, SPEC, spec(status="draft"))
    write(repo, "lib/model.py", CODE["lib/model.py"])
    _git(repo, "add", SPEC, "lib/model.py")
    write(repo, SPEC, spec())
    r = gate(repo, "--commit")
    assert r.returncode == 1 and "is still status: draft" in r.stdout, r.stdout
    _git(repo, "add", SPEC)
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
    assert "each done_when item as a '- [ ]' line" in r.stdout


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

    row = CATALOG_TEXT.replace("| Models | Production | unknown | none |", "| Models | Production | 2026-09-28 | #42 |")
    assert pr(repo, BRANCH, {**recorded, CATALOG: row}, **meta, PR_DRAFT="false").returncode == 0
    r = pr(repo, BRANCH, {**recorded, CATALOG: row}, **{**meta, "PR_BODY": body()}, PR_DRAFT="false")
    assert r.returncode == 1 and "done_when item(s) not ticked" in r.stdout, r.stdout

    trace = "# Traceability\n\n## FEAT-MODEL-001\n\n- none\n\n## FEAT-DATA-001\n\n- #42 state each model's decision\n"
    r = pr(repo, BRANCH, {**recorded, CATALOG: row, TRACEABILITY: trace}, **meta, PR_DRAFT="false")
    assert r.returncode == 1 and "add this PR (#42) under the FEAT-MODEL-001 section" in r.stdout, r.stdout
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
    unset = stocks_catalog.replace("| Status | Production |", "| Status | TBD |").replace("2026-08-30", "2026-09-28")
    r = pr(repo, BRANCH, {**base, CATALOG: unset}, **meta)
    assert r.returncode == 1 and "Status" in r.stdout, r.stdout
    stamped = stocks_catalog.replace("2026-08-30", "2026-09-28")
    r = pr(repo, BRANCH, {**base, CATALOG: stamped}, **meta)
    assert r.returncode == 0, r.stdout


def test_the_plan_records_its_pr(repo):
    """solyra#72 r4117890536 (spec_gate.py:70).

    Nothing read the plan's `pr:` field, so it could stay null or name another
    PR. It must be null or a PR number; a number that is not this PR fails in
    any PR run, and once the PR is ready it must be this PR.
    """
    meta = {"PR_TITLE": "FEAT-MODEL-001: x", "PR_BODY": body(ticked=True), "PR_NUMBER": "42"}
    row = CATALOG_TEXT.replace("| Models | Production | unknown | none |", "| Models | Production | 2026-09-28 | #42 |")
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
    assert pr(repo, "chore/bump-deps", {"package-lock.json": "{}\n"}).returncode == 0
    assert pr(repo, "bot/superpowers-v5", skill_file).returncode == 0
    assert pr(repo, "bot/superpowers-v5", {**skill_file, **CODE}).returncode == 1
    assert pr(repo, "chore/refactor", CODE).returncode == 1
    assert pr(repo, "test/more-cases", {"tests/test_x.py": "def test(): pass\n"}).returncode == 1
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
