#!/usr/bin/env python3
"""Spec gate: refuses code changes that have no FEAT-ID, approved spec, and plan.

Usage:
  python3 scripts/gate/spec_gate.py --commit              # pre-commit hook: the staged tree
  python3 scripts/gate/spec_gate.py --pr [BASE [HEAD]]    # a PR's diff (default origin/main HEAD)
  python3 scripts/gate/spec_gate.py --check-spec <path>   # validate one spec file's frontmatter

Exit 0 = ok, 1 = blocked, 2 = usage. Prints what to do next.

Every changed file is gated except documentation: docs/**, *.md, *.drawio,
LICENSE* and .gitignore. A gated file needs a feature/<feat-id>-<slug> or
fix/<feat-id>-<slug> branch whose plan and approved spec validate, unless the
branch prefix allows that path:

  chore/             dependency manifests, lockfiles, and the gate's own files; in a
                     manifest only the dependency fields, never scripts or tool config
  bot/superpowers-   the vendored skills under .claude/skills/
  spike/             anything, for local commits only: a spike opens no PR

No branch is exempt by name. A pull request from a fork gets no prefix
allowance. A detached HEAD that stages gated files is blocked: name the branch
with SPEC_GATE_BRANCH=<branch> git commit ...

--commit reads the plan from the index, so it validates what is being
committed; the catalog row and the approved spec are read from HEAD (during a
merge, from MERGE_HEAD). --pr reads the plan from the PR head's git objects and
the catalog row and spec from the merge base, so a PR cannot add its own
capability or approve its own spec, and CI runs this script from the base
branch without checking the PR out. In CI the branch
comes from PR_HEAD_REF, fork detection from PR_HEAD_REPO and PR_BASE_REPO, and
PR_TITLE, PR_BODY, PR_NUMBER and PR_DRAFT drive the metadata and close-out
checks, and PR_BASE_REF must be main. Any harness (Claude Code, Codex, a human) hits the same check.
"""
from __future__ import annotations

import json
import datetime
import os
import pathlib
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPECS = "docs/superpowers/specs"
PLANS = "docs/superpowers/plans"
CATALOG = "docs/product/02-FEATURE-CATALOG.md"
REQUIREMENTS = "docs/product/01-PRODUCT-REQUIREMENTS.md"
TRACEABILITY = "docs/product/12-PR-ISSUE-TRACEABILITY.md"
CANVASES = "docs/product/canvases.yml"
MAIN = "main"
# The product documents a feature change may touch, besides its own catalog row and record
# and its own traceability section: the machine-owned registry the exporter reads, and what
# it generates. Everything else under docs/product/ changes on its own docs/ branch.
PRODUCT_DOCS = "docs/product/"
REGISTRY_DOCS = ("docs/product/07-MODEL-REGISTRY.md", "docs/product/generated/model-registry.json")

FEAT_ROW = re.compile(r"^\|\s*\[?(FEAT-[A-Z]+-\d{3})\b", re.M)
FEAT_IDS = re.compile(r"\bFEAT-[A-Z]+-\d{3}\b")
BRANCH = re.compile(r"^(feature|fix)/(feat-[a-z]+-\d{3})-[a-z0-9][a-z0-9._-]*$")   # lowercase: git refs are case-sensitive
REQ_SHAPE = re.compile(r"^REQ-[A-Z]+-\d{3}$")
REQ_DEFINITION = re.compile(r"\*\*(REQ-[A-Z]+-\d{3}):\*\*")
CHECKBOX = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.*\S)\s*$")
HEADING = re.compile(r"^(#{1,6})\s")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PR_REF = re.compile(r"^#?(\d+)$")
PR_MENTION = re.compile(r"#(\d+)(?![\w])")   # #123abc names nothing
CLOSE_OUT_FIELDS = ("Status", "Last reviewed")

MANIFEST = re.compile(
    r"(^|/)(package(-lock)?\.json|requirements[^/]*\.(txt|lock)|pyproject\.toml|poetry\.lock"
    r"|yarn\.lock|pnpm-lock\.yaml|bun\.lockb?)$"
)
GATE_FILES = (
    "scripts/gate/",
    ".githooks/",
    ".github/workflows/spec-gate.yml",
    ".github/workflows/registry-check.yml",
    "tests/scripts/test_spec_gate.py",
    "tests/scripts/test_export_model_registry.py",
)
# Every branch a pull request may come from, in full: feature/ and fix/ carry a FEAT-ID
# (BRANCH), the rest a kebab-case slug. spike/ is refused before this in PR mode.
OTHER_BRANCH = re.compile(r"^((docs|chore)/[a-z0-9]+(-[a-z0-9]+)*|bot/superpowers-[a-z0-9]+(-[a-z0-9]+)*)$")
# The files the gate runs from: no change may delete one, whatever its branch, or the
# base's copy judges the deletion green and every later PR runs without a gate.
GATE_ENTRYPOINTS = (
    "scripts/gate/spec_gate.py",
    ".githooks/pre-commit",
    ".github/workflows/spec-gate.yml",
    ".github/workflows/registry-check.yml",
    "tests/scripts/test_spec_gate.py",   # the suite CI runs on a proposed gate
)
# The manifest fields a chore/ branch may change. Anything else in package.json or
# pyproject.toml (scripts, build config, tool tables) is executable configuration that
# CI runs from the checkout, so it is a CHANGE.
NPM_DEPENDENCY_KEYS = frozenset((
    "dependencies", "devDependencies", "peerDependencies", "peerDependenciesMeta",
    "optionalDependencies", "bundledDependencies", "bundleDependencies", "overrides",
    "resolutions",
))
PYPROJECT_DEPENDENCY_PATHS = (
    ("project", "dependencies"), ("project", "optional-dependencies"), ("dependency-groups",),
    ("build-system", "requires"), ("tool", "poetry", "dependencies"), ("tool", "poetry", "group"),
    ("tool", "uv", "sources"), ("tool", "uv", "dev-dependencies"),
)
CANVAS_MARKERS = {"refresh": "Canvas refresh pending:", "report-only": "Canvas check pending (report-only):"}
# A ticked done_when line that defers the work is not done (CLAUDE.md rule 0 names these phrases).
DEFERRAL = re.compile(
    r"\b(future[- ]work|follow[- ]?up|non[- ]?blocking|for now|deferred|later PR|next PR|separate PR|TODO|TBD"
    r"|not (?:yet )?(?:run|done|implemented|verified|tested|complete|completed|finished|started|applied|merged|shipped)"
    r"|unfinished|incomplete|untested|unverified|outstanding|pending|skipped|still open|to be done)\b", re.I)
# Changing these is changing a workload; the PR body must then carry the rule 0 capacity numbers.
WORKLOAD_PREFIXES = ("gcp/", ".github/workflows/")
CAPACITY_LABELS = ("Volume", "Velocity", "Wall-clock", "30")
REQUIRED_SPEC_KEYS = ("feat_id", "req_ids", "done_when", "status")
REQUIRED_PLAN_KEYS = ("feat_id", "spec", "branch", "status")
SPEC_STATUSES = ("draft", "approved", "superseded")
PLAN_STATUSES = ("ready", "done")
WORKTREE = "worktree"


class GitFailed(Exception):
    """A git command the gate depends on failed. Never treated as an empty result."""


def git(*args: str) -> subprocess.CompletedProcess:
    # utf-8 regardless of locale: the specs carry curly quotes and emoji, and cp1252
    # (Windows) would raise on them and block every commit.
    return subprocess.run(["git", *args], capture_output=True, encoding="utf-8", errors="replace", cwd=ROOT)


def git_out(*args: str) -> str:
    """stdout of a git command that must succeed: a failed diff or listing is not an empty one."""
    r = git(*args)
    if r.returncode != 0:
        raise GitFailed(f"git {' '.join(args[:2])} failed ({r.returncode}): {r.stderr.strip() or 'no output'}; "
                        "refusing to pass on a diff the gate could not compute")
    return r.stdout


def catalog_ids(text: str | None) -> set[str]:
    """FEAT-IDs from the first cell of the catalog's table rows. A FEAT-ID mentioned
    anywhere else (prose, a link, a comment) is not a catalog entry."""
    return set(FEAT_ROW.findall(visible(text or "")))


LICENSE_FILE = re.compile(r"^(LICENSE|LICENCE|COPYING)(-[A-Za-z0-9]+)*(\.(md|txt|rst))?$")
WORKFLOWS = ".github/workflows/"


def is_documentation(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if path.startswith(WORKFLOWS) and not name.endswith(".md"):
        return False   # a workflow is executable configuration whatever its name
    if path.startswith(".claude/"):
        return False   # skills and agents are the process agents execute, not its description
    return (path.startswith("docs/") or path.endswith((".md", ".drawio"))
            or bool(LICENSE_FILE.match(name))
            or path == ".gitignore")


class Tree:
    """One revision's files: the index (rev None), the working tree, or a commit."""

    def __init__(self, rev: str | None):
        self.rev = rev

    def read(self, path: str) -> str | None:
        if self.rev == WORKTREE:
            p = ROOT / path
            return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
        r = git("show", f":{path}" if self.rev is None else f"{self.rev}:{path}")
        return r.stdout if r.returncode == 0 else None

    def list(self, folder: str) -> list[str]:
        if self.rev == WORKTREE:
            base = ROOT / folder
            found = [str(p.relative_to(ROOT)) for p in base.glob("*.md")] if base.is_dir() else []
        elif self.rev is None:
            found = git_out("ls-files", "--", folder).splitlines()
        else:
            r = git("ls-tree", "-r", "--name-only", self.rev, "--", folder)
            found = r.stdout.splitlines() if r.returncode == 0 else []   # a rev without the folder
        return sorted(p for p in found if p.endswith(".md"))


def frontmatter(text: str | None) -> dict:
    """Minimal YAML frontmatter reader: top-level `key: value` and `key:` + `  - item` lists."""
    if not text:
        return {}
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    fm: dict = {}
    current = None
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        if line.startswith((" ", "\t")):
            item = line.strip()
            if item.startswith("- ") and current:
                fm.setdefault(current, [])
                if isinstance(fm[current], list):
                    fm[current].append(item[2:].strip().strip('"'))
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            current = k
            if v == "":
                fm[k] = []
            elif v in ("null", "~"):
                fm[k] = None
            elif v.startswith("[") and v.endswith("]"):
                fm[k] = [x.strip().strip('"') for x in v[1:-1].split(",") if x.strip()]
            else:
                fm[k] = v.strip('"')
    return fm


def requirement_defs(tree: "Tree") -> set[str] | None:
    """The REQ-IDs the requirements registry defines; None where the repository has
    no registry (solyra), so req_ids are checked for shape only. A registry that
    exists but defines nothing fails closed rather than passing every ID."""
    text = tree.read(REQUIREMENTS)
    return None if text is None else set(REQ_DEFINITION.findall(visible(text)))


def validate_spec(fm: dict, name: str, catalog: set[str], req_defs: set[str] | None) -> list[str]:
    errs = [f"{name}: missing frontmatter key '{k}'" for k in REQUIRED_SPEC_KEYS if k not in fm]
    if "feat_id" in fm and not isinstance(fm["feat_id"], str):
        errs.append(f"{name}: feat_id must be one FEAT-ID, not a list")
    elif "feat_id" in fm and fm["feat_id"] not in catalog:
        errs.append(f"{name}: feat_id {fm['feat_id']!r} is not in {CATALOG}")
    if fm.get("status") not in SPEC_STATUSES:
        errs.append(f"{name}: status must be draft | approved | superseded")
    done = fm.get("done_when")
    if "done_when" in fm and (not isinstance(done, list) or not done or not all(str(x).strip() for x in done)):
        errs.append(f"{name}: done_when must be a non-empty list of non-empty items; "
                    "a spec without verifiable done_when items cannot be closed")
    reqs = fm.get("req_ids")
    if "req_ids" in fm:
        if not isinstance(reqs, list) or not reqs:
            errs.append(f"{name}: req_ids must be a non-empty list of REQ-IDs")
        else:
            bad = [r for r in reqs if not REQ_SHAPE.match(r)]
            unknown = [r for r in reqs if REQ_SHAPE.match(r) and req_defs is not None and r not in req_defs]
            if bad:
                errs.append(f"{name}: req_ids not shaped REQ-XXX-000: {', '.join(bad)}")
            if req_defs is not None and not req_defs:
                errs.append(f"{name}: {REQUIREMENTS} defines no REQ-IDs (**REQ-XXX-000:** lines), "
                            "so req_ids cannot be checked; restore the registry")
            elif unknown:
                errs.append(f"{name}: req_ids not defined in {REQUIREMENTS}: {', '.join(unknown)}")
    for key in ("issues", "canvases"):
        if key in fm and fm[key] is not None and not isinstance(fm[key], list):
            errs.append(f"{name}: {key} must be a list")
    return errs


def plan_stays_bound(name: str, fm: dict, base_fm: dict, branch: str) -> list[str]:
    """A plan already on the base binds one branch and one PR for good: a change cannot
    re-point it at its own branch, swap its PR number, or reopen it once it is done."""
    if not base_fm:
        return []
    errs = []
    if base_fm.get("branch") != branch:
        errs.append(f"{name}: names branch '{base_fm.get('branch')}' on the base; a plan binds one branch, "
                    f"so '{branch}' needs its own plan")
    if base_fm.get("pr") is not None and str(fm.get("pr")) != str(base_fm.get("pr")):
        errs.append(f"{name}: records PR #{base_fm.get('pr')} on the base; a plan binds one PR")
    if base_fm.get("status") == "done":
        errs.append(f"{name}: is status: done on the base (its PR merged); further work needs a new plan")
    return errs


def validate_plan(fm: dict, name: str, feat_id: str, tree: Tree) -> list[str]:
    errs = [f"{name}: missing frontmatter key '{k}'" for k in REQUIRED_PLAN_KEYS if k not in fm]
    if "feat_id" in fm and fm["feat_id"] != feat_id:
        errs.append(f"{name}: feat_id is {fm['feat_id']!r} but the branch serves {feat_id}")
    status = fm.get("status")
    if status not in PLAN_STATUSES:
        errs.append(f"{name}: status must be ready | done")
    elif status != "ready":
        errs.append(f"{name}: status is '{status}'; a plan authorizes implementation only while "
                    "status: ready (done means its PR merged)")
    pr = fm.get("pr")
    if pr is not None and not PR_REF.match(str(pr)):
        errs.append(f"{name}: pr must be null or a PR number, not '{pr}'")
    spec = fm.get("spec")
    if "spec" in fm and (not isinstance(spec, str) or not spec.strip()):
        errs.append(f"{name}: spec must name the approved spec's path, not '{spec}'")
    elif spec and not (spec.startswith(SPECS + "/") and spec.endswith(".md")):
        errs.append(f"{name}: spec must be a file under {SPECS}/, not {spec}")
    elif spec and tree.read(spec) is None:
        errs.append(f"{name}: spec path does not exist: {spec}")
    return errs


@dataclass
class Change:
    mode: str               # "commit" or "pr"
    branch: str
    changed: list[str]
    tree: Tree
    base: Tree              # policy: the catalog, specs and requirements are read here
    before: Tree            # the files as they were before the change: HEAD, or the merge base
    trusted: bool = True    # False for a PR from a fork: no prefix allowances


@dataclass
class Traced:
    feat_id: str
    spec_path: str
    spec_fm: dict
    plan_path: str
    plan_fm: dict


def _without(d: dict, path: tuple[str, ...]) -> dict:
    """`d` with the nested key `path` removed, when present."""
    if len(path) == 1:
        return {k: v for k, v in d.items() if k != path[0]}
    inner = d.get(path[0])
    if not isinstance(inner, dict):
        return d
    return {**d, path[0]: _without(inner, path[1:])}


def non_dependency_edit(path: str, before: str | None, after: str | None) -> str | None:
    """Why this manifest edit is more than a dependency update, or None when it is not.
    Lockfiles and requirements files hold nothing but dependencies; package.json and
    pyproject.toml also carry scripts and tool configuration, which CI executes."""
    name = path.rsplit("/", 1)[-1]
    if name not in ("package.json", "pyproject.toml"):
        return None
    if before is None:
        return f"{path}: a new manifest is a new project, not a dependency update"
    if after is None:
        return f"{path}: removing the manifest is not a dependency update"
    try:
        if name == "package.json":
            b, a = json.loads(before), json.loads(after)
            if not isinstance(b, dict) or not isinstance(a, dict):
                return f"{path}: is not a JSON object on both sides; that is not a dependency update"
            b = {k: v for k, v in b.items() if k not in NPM_DEPENDENCY_KEYS}
            a = {k: v for k, v in a.items() if k not in NPM_DEPENDENCY_KEYS}
        else:
            b, a = tomllib.loads(before), tomllib.loads(after)
            for dep_path in PYPROJECT_DEPENDENCY_PATHS:
                b, a = _without(b, dep_path), _without(a, dep_path)
    except (ValueError, tomllib.TOMLDecodeError) as e:
        return f"{path}: cannot be parsed ({e}); the gate does not guess what changed"
    changed = sorted(k for k in set(b) | set(a) if b.get(k) != a.get(k))
    if changed:
        return f"{path}: changes {', '.join(changed)}, not only dependencies; a scripts or config edit is a CHANGE"
    return None


def is_gate_file(path: str) -> bool:
    """A directory entry in GATE_FILES covers its contents; a file entry is that file
    exactly, so `.github/workflows/spec-gate.yml-else.yaml` is not the gate's workflow."""
    return any(path.startswith(g) if g.endswith("/") else path == g for g in GATE_FILES)


def chore_allows(path: str, ch: "Change") -> str | None:
    """None when chore/ may carry this file; otherwise why not ("" when it is simply not a
    manifest or gate file, a reason naming the file when it is a manifest edited beyond
    its dependency fields)."""
    if is_gate_file(path):
        return None
    if not MANIFEST.search(path):
        return ""
    # Against the merge base, not the current base: a scripts edit main made after the
    # fork is main's, not this PR's, and must not fail an otherwise permitted bump.
    return non_dependency_edit(path, ch.before.read(path), ch.tree.read(path))


# Skills this repository owns: the weekly vendored-skills update never touches them.
LOCAL_SKILLS = (".claude/skills/product-delivery/", ".claude/skills/refresh-canvas/")

ALLOWANCES = (
    ("chore/", chore_allows),
    ("bot/superpowers-", lambda p, ch: None if p.startswith(".claude/skills/") and not p.startswith(LOCAL_SKILLS) else ""),
)


def summarize(paths: list[str]) -> str:
    shown = ", ".join(paths[:3])
    return shown + (f" and {len(paths) - 3} more" if len(paths) > 3 else "")


def check_changed_specs(ch: Change) -> list[str]:
    """validate_spec over every spec the change adds or edits, read at the head."""
    errs: list[str] = []
    catalog, req_defs = None, None
    for path in ch.changed:
        if not (path.startswith(SPECS + "/") and path.endswith(".md")):
            continue
        text = ch.tree.read(path)
        if text is None:
            continue
        if catalog is None:
            catalog, req_defs = catalog_ids(ch.base.read(CATALOG)), requirement_defs(ch.base)
        errs += validate_spec(frontmatter(text), path, catalog, req_defs)
        base_text = ch.base.read(path)
        if base_text is not None and frontmatter(base_text).get("status") == "approved" and text != base_text:
            # The one edit an approved spec takes is its status moving to superseded when the
            # spec that replaces it lands; anything else is a new contract nobody approved.
            strip = lambda t: re.sub(r"^status:.*$", "", t, flags=re.M)
            if not (frontmatter(text).get("status") == "superseded" and strip(text) == strip(base_text)):
                errs.append(f"{path}: an approved spec does not change in place; write a new spec that names it in "
                            "`supersedes` and get that one approved, then mark this one superseded")
    return errs


def check(ch: Change) -> tuple[list[str], Traced | None]:
    if ch.mode == "pr" and ch.branch.startswith("spike/"):
        return [f"branch '{ch.branch}' is a spike: local investigation commits only, never a pull request. "
                "Re-cut the work on a feature/ or fix/ branch with a plan, or a docs/ branch for its write-up."], None
    removed = [f for f in ch.changed if f in GATE_ENTRYPOINTS and ch.tree.read(f) is None]
    if removed:
        return [f"{summarize(removed)}: the gate's own entrypoints cannot be removed by a change; "
                "retiring the gate is a decision taken on main, not in a branch"], None
    # A spec is documentation that becomes policy once merged, so every changed spec is
    # validated here, before the documentation-only return, against the base's catalog
    # and requirements; a malformed spec must not land and then block or mislead the
    # implementation that cites it.
    errs_specs = check_changed_specs(ch)
    gated = [f for f in ch.changed if not is_documentation(f)]
    if not gated:
        if errs_specs:
            return errs_specs, None
        # Documentation alone is exempt from the trace, not from the branch rule: a PR
        # still comes from a delivery branch, so `main` or `typo` is not a way in.
        if ch.mode == "pr" and not (BRANCH.match(ch.branch) or OTHER_BRANCH.match(ch.branch)):
            return [f"branch '{ch.branch}' is not a delivery branch; a pull request comes from feature/<feat-id>-<slug>, "
                    "fix/<feat-id>-<slug>, docs/<slug>, chore/<slug> or bot/superpowers-<tag>, documentation included"], None
        return [], None
    if ch.mode == "commit" and ch.branch == "HEAD":
        return [
            f"detached HEAD with {len(gated)} staged gated file(s) ({summarize(gated)}): "
            "the gate cannot tell which branch this commit is for.",
            "Name it for this commit: SPEC_GATE_BRANCH=feature/<feat-id>-<slug> git commit ...",
        ], None
    if ch.mode == "commit" and ch.branch.startswith("spike/"):
        return [], None
    # An allowance needs the full branch shape (OTHER_BRANCH): `chore/` or `chore/a/b`
    # gets none, so a malformed name cannot carry a gate file through.
    allowed = (next((ok for prefix, ok in ALLOWANCES if ch.branch.startswith(prefix)), None)
               if ch.trusted and OTHER_BRANCH.match(ch.branch) else None)
    refused = {f: (allowed(f, ch) if allowed else "") for f in gated}
    remaining = [f for f, why in refused.items() if why is not None]
    if not remaining:
        return [], None
    m = BRANCH.match(ch.branch)
    if not m:
        why = " A pull request from a fork gets no prefix allowance." if not ch.trusted else ""
        return [
            f"branch '{ch.branch}' changes {len(remaining)} gated file(s) ({summarize(remaining)}) "
            "but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>." + why,
            *[reason for reason in refused.values() if reason],
            "docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), "
            "lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.",
        ], None
    feat_id = m.group(2).upper()
    errs: list[str] = list(errs_specs)
    # The catalog row and the approved spec are read from the BASE (HEAD for a commit, the
    # merge base for a PR): a change cannot add its own capability or approve its own spec
    # in the same diff. Phase 2 commits the approved spec alone, before any code.
    where = "HEAD" if ch.mode == "commit" else "the base branch"
    catalog_text = ch.base.read(CATALOG)
    catalog = catalog_ids(catalog_text)
    if catalog_text is None:
        errs.append(f"{CATALOG} is missing at {where}")
    elif feat_id not in catalog:
        errs.append(f"{feat_id} is not a row in {CATALOG} at {where}; a capability is added before the work that uses it")
    plans = [p for p in ch.tree.list(PLANS) if frontmatter(ch.tree.read(p)).get("branch") == ch.branch]
    if not plans:
        errs.append(f"no plan in {PLANS} names branch '{ch.branch}'")
        return errs, None
    if len(plans) > 1:
        errs.append(f"{len(plans)} plans name branch '{ch.branch}' ({', '.join(plans)}); one plan = one branch")
        return errs, None
    plan_path = plans[0]
    plan_fm = frontmatter(ch.tree.read(plan_path))
    errs += validate_plan(plan_fm, plan_path, feat_id, ch.tree)
    errs += plan_stays_bound(plan_path, plan_fm, frontmatter(ch.base.read(plan_path)), ch.branch)
    spec_path = plan_fm.get("spec") if isinstance(plan_fm.get("spec"), str) else None
    spec_text = ch.base.read(spec_path) if spec_path else None
    if spec_text is None:
        if spec_path and ch.tree.read(spec_path) is not None:
            errs.append(f"{spec_path} is new in this change; an approved spec lands alone first (Phase 2), "
                        f"then the code that implements it")
        return errs, None
    if ch.tree.read(spec_path) != spec_text:
        errs.append(f"{spec_path} at this change differs from the base's copy; a spec changes on its own docs/ "
                    f"branch, so merge the base or drop the edit")
    other_specs = [f for f in ch.changed if f.startswith(SPECS + "/") and f != spec_path]
    if other_specs:
        errs.append(f"spec(s) change alongside code ({summarize(other_specs)}); a spec lands alone on a docs/ branch, "
                    "never with an implementation")
    other_plans = [f for f in ch.changed if f.startswith(PLANS + "/") and f != plan_path]
    if other_plans:
        errs.append(f"other plan(s) change alongside code ({summarize(other_plans)}); a change edits only the plan "
                    "that names its branch")
    spec_fm = frontmatter(spec_text)
    if spec_fm.get("feat_id") != feat_id:
        errs.append(f"{spec_path}: the plan's spec serves {spec_fm.get('feat_id')}, not {feat_id}")
    if spec_fm.get("status") == "draft":
        errs.append(f"{spec_path} is still status: draft; get it approved first")
    elif spec_fm.get("status") == "superseded":
        errs.append(f"{spec_path} is status: superseded; point the plan at the spec that replaced it")
    # Supersession is policy too: a spec that replaced this one on the base branch after the
    # fork is what the change must be judged against, so the base's spec list is scanned.
    # Only an APPROVED spec for the SAME FEAT replaces this one: a draft, or another
    # feature's spec that names it by mistake, cannot block the capability.
    newer = [s for s in ch.base.list(SPECS) if s != spec_path
             and (nfm := frontmatter(ch.base.read(s))).get("supersedes") == spec_path
             and nfm.get("status") == "approved" and nfm.get("feat_id") == feat_id]
    if newer:
        errs.append(f"{spec_path} is superseded by {', '.join(newer)}; point the plan at the current spec")
    errs += validate_spec(spec_fm, spec_path, catalog, requirement_defs(ch.base))
    return errs, Traced(feat_id, spec_path, spec_fm, plan_path, plan_fm)


def norm(text: str) -> str:
    return " ".join(text.split())


def visible(body: str) -> str:
    """The PR body as it renders: HTML comments and fenced code blocks removed, so a
    checkbox inside the template's comments or a code example is not a checkbox."""
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r"<!--.*\Z", "", body, flags=re.S)   # an unclosed comment runs to the end, as GitHub renders it
    # A fence opens with 3+ backticks or tildes after up to three spaces and closes with a
    # fence of the same character at least as long; an unclosed fence runs to the end.
    # (`{3,} and ~{3,} separately: a closer mixing the two characters does not close a
    # fence for Markdown, so it must not close one here either)
    # ([ \t]*, not up to three spaces: a fence nested under a list item is indented by the
    # item's content offset and still renders as code)
    body = re.sub(r"^[ \t]*(`{3,}).*?^[ \t]*\1`*[ \t]*$", "", body, flags=re.S | re.M)
    body = re.sub(r"^[ \t]*(~{3,}).*?^[ \t]*\1~*[ \t]*$", "", body, flags=re.S | re.M)
    body = re.sub(r"^[ \t]*(`{3,}|~{3,}).*\Z", "", body, flags=re.S | re.M)
    # An indented code block: lines indented four spaces or a tab after a blank line, until
    # the next unindented text. Those render as code, not as links or checkboxes.
    kept, in_code, prev_blank = [], False, True
    for line in body.splitlines():
        indented = line.startswith(("    ", "\t"))
        if in_code and (indented or not line.strip()):
            continue
        in_code = indented and prev_blank
        if not in_code:
            kept.append(line)
        prev_blank = not line.strip()
    return "\n".join(kept)


def checklist(body: str) -> list[tuple[bool, str]]:
    """Each rendered task-list item: its checkbox line plus the indented continuation
    lines that render as part of it, so a deferral written under the box still counts."""
    items: list[tuple[bool, str]] = []
    for line in visible(body).splitlines():
        if (m := CHECKBOX.match(line)):
            items.append((m.group(1) in "xX", norm(m.group(2))))
        elif items and items[-1] is not None and line.strip() and line[0] in " \t":
            ticked, text = items[-1]
            items[-1] = (ticked, norm(f"{text} {line}"))
        else:
            items.append(None)   # a blank or unindented line ends the item
    return [i for i in items if i is not None]


def done_items(t: Traced) -> list[str]:
    items = t.spec_fm.get("done_when")
    return [norm(str(i)) for i in items] if isinstance(items, list) else []


def matched_boxes(items: list[str], boxes: list[tuple[bool, str]]) -> dict[str, tuple[bool, str] | None]:
    """Each done_when item's own checkbox line, or None. A line serves one item, and the
    longest item claims first, so `run the tests` cannot also tick `run the tests on 3.12`."""
    free = list(boxes)
    out: dict[str, tuple[bool, str] | None] = {i: None for i in items}
    for item in sorted(items, key=len, reverse=True):
        hit = next((b for b in free if b[1].startswith(item)), None)
        if hit is not None:
            free.remove(hit)
        out[item] = hit
    return out


def canvas_modes(text: str | None) -> dict[str, str]:
    """canvases.yml as {url: "refresh" | "report-only"}. Read line by line: the gate has
    no YAML dependency, and the file is a list of `- name:` entries with flat fields."""
    modes: dict[str, str] = {}
    url = mode = None
    for line in (text or "").splitlines() + ["- name:"]:
        if re.match(r"^\s*-\s+name:", line):
            if url:
                modes[url] = mode or "refresh"
            url = mode = None
        elif (m := re.match(r"^\s+url:\s*(\S+)", line)):
            url = m.group(1)
        elif (m := re.match(r"^\s+mode:\s*(\S+)", line)):
            mode = m.group(1)
    return modes


def check_canvas_handoff(t: Traced, body: str, tree: Tree) -> list[str]:
    """A spec that lists canvases hands their refresh to Phase 5: the PR body carries
    `Canvas refresh pending: <url>`, or the report-only marker for a report-only canvas."""
    urls = t.spec_fm.get("canvases")
    if not isinstance(urls, list) or not urls:
        return []
    modes = canvas_modes(tree.read(CANVASES))
    lines = visible(body).splitlines()
    errs: list[str] = []
    for url in urls:
        mode = modes.get(url)
        if mode is None:
            errs.append(f"{t.spec_path} lists canvas {url}, which is not in {CANVASES}")
            continue
        marker = CANVAS_MARKERS.get(mode, CANVAS_MARKERS["refresh"])
        if not any(line.strip().startswith(marker) and url in line for line in lines):
            errs.append(f"PR body must carry '{marker} {url}': the spec lists that canvas, so its Phase 5 handoff is due")
    return errs


def links_path(shown: str, path: str) -> bool:
    """The path appears as a whole token: `expected.md.old` or `expected.md-v2` names another
    file. A preceding `/` is allowed so a link to the file on the forge still counts."""
    return re.search(rf"(?<![\w.-]){re.escape(path)}(?![\w.-])", shown) is not None


def check_pr_metadata(t: Traced, env: dict, tree: Tree) -> list[str]:
    """CI only: the PR title and body must name what the gate validated."""
    title, body = env.get("PR_TITLE"), env.get("PR_BODY")
    errs: list[str] = []
    if title is not None and not title.startswith(f"{t.feat_id}:"):
        errs.append(f"PR title must start with '{t.feat_id}:', the branch's FEAT-ID, e.g. '{t.feat_id}: <what changed>'")
    if body is not None:
        shown = visible(body)   # what the reviewer reads: no HTML comments, no code examples
        if not links_path(shown, t.spec_path):
            errs.append(f"PR body must link the spec the plan names: {t.spec_path}")
        if not links_path(shown, t.plan_path):
            errs.append(f"PR body must link the plan: {t.plan_path}")
        matched = matched_boxes(done_items(t), checklist(shown))
        missing = [i for i, box in matched.items() if box is None]
        if missing:
            errs.append("PR body must carry each done_when item as its own '- [ ]' line starting with its text; "
                        "missing: " + "; ".join(missing))
        # Scanned past the item's own words: a done_when that says "no pending jobs" is the
        # spec's wording, not a deferral; what the author wrote after it is.
        deferred = [box[1] for item, box in matched.items() if box and box[0] and DEFERRAL.search(box[1][len(item):])]
        if deferred:
            errs.append("a ticked done_when item defers its work, so it is not done: " + "; ".join(deferred))
        errs += check_canvas_handoff(t, body, tree)
    return errs


def section(body: str, title: str) -> str | None:
    """The text under the first heading containing `title` (case-insensitive), HTML comments removed."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if (h := HEADING.match(line)) and title.lower() in line.lower():
            level = len(h.group(1))
            out = []
            for later in lines[i + 1:]:
                if (hh := HEADING.match(later)) and len(hh.group(1)) <= level:
                    break   # a nested heading (### Volume under ## Capacity) is part of the section
                out.append(later)
            return "\n".join(out)
    return None


def check_capacity(body: str | None, changed: list[str]) -> list[str]:
    """CI only: a change under gcp/ or the workflows is a workload change, and CLAUDE.md
    rule 0 wants its three numbers and cost in the PR body, or an `n/a` with the reason."""
    # Documentation under a workload prefix (a README beside the workflows or a job)
    # runs nothing, so a docs/ branch editing it needs no numbers.
    workloads = [f for f in changed if f.startswith(WORKLOAD_PREFIXES) and not is_documentation(f)]
    if body is None or not workloads:
        return []
    text = section(visible(body), "capacity")
    if text is None:
        return [f"PR body needs a Capacity section: the change touches a workload ({summarize(workloads)})"]
    if re.search(r"\bn/a\b[ \t]*[\u2014:-][ \t]*\w", text, re.I):
        return []
    # [ \t]*, not \s*: a value is on the label's own line, so a blank `Volume:` followed by
    # `Velocity: 2/day` on the next line does not borrow the next label as its value.
    blank = [label for label in CAPACITY_LABELS
             if not re.search(r"\b" + re.escape(label) + r"\**:\**[ \t]*[^\s\u00b7|]", text)]
    if blank:
        return ["PR body's Capacity section leaves " + ", ".join(blank) + " blank; give the numbers, "
                "or write 'n/a: <why no workload runs differently>'"]
    return []


def changed_lines(merge_base: str, head: str, path: str) -> list[tuple[str, int, str]]:
    """("-", line in base, text) for every line the change removes from path and
    ("+", line in head, text) for every line it adds."""
    out, old, new = [], 0, 0
    for line in git_out("diff", "-U0", merge_base, head, "--", path).splitlines():
        hunk = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)", line)
        if hunk:
            old, new = int(hunk.group(1)), int(hunk.group(2))
        elif line.startswith("-") and not line.startswith("---"):
            out.append(("-", old, line[1:]))
            old += 1
        elif line.startswith("+") and not line.startswith("+++"):
            out.append(("+", new, line[1:]))
            new += 1
    return out


def feat_span(text: str, feat_id: str) -> set[int]:
    """1-based line numbers that belong to feat_id in a product document: its table rows,
    and every section whose heading names it, up to the next heading of that level or higher."""
    lines = text.splitlines()
    span: set[int] = set()
    level = None
    for n, line in enumerate(lines, 1):
        h = HEADING.match(line)
        if h:
            if level is not None and len(h.group(1)) <= level:
                level = None
            if feat_id in line:
                level = len(h.group(1))
        if level is not None or (FEAT_ROW.match(line) and FEAT_ROW.match(line).group(1) == feat_id):
            span.add(n)
    return span


def feat_headings(text: str, feat_id: str) -> tuple[int, int]:
    """(headings naming the FEAT, table rows keyed by it): one record, one of each."""
    lines = text.splitlines()
    return (sum(1 for line in lines if HEADING.match(line) and feat_id in line),
            sum(1 for line in lines if (m := FEAT_ROW.match(line)) and m.group(1) == feat_id))


def check_product_scope(feat_id: str, ch: Change, merge_base: str, head: str) -> list[str]:
    """CI only: a feature change edits its own catalog record and traceability section, and
    nothing else's. The requirements document changes on its own docs/ branch. Runs on a
    feature/ or fix/ PR whether or not it carries code, so a docs-only one is scoped too."""
    errs: list[str] = []
    for path in ch.changed:
        if path == REQUIREMENTS:
            errs.append(f"{path} changes in this feature change; requirements change on their own docs/ branch, "
                        "before the work that cites them")
        elif path in (CATALOG, TRACEABILITY):
            before_text, after_text = Tree(merge_base).read(path) or "", ch.tree.read(path) or ""
            had, has = feat_headings(before_text, feat_id), feat_headings(after_text, feat_id)
            if any(before and after > before for before, after in zip(had, has)):
                errs.append(f"{path}: adds a second heading or row for {feat_id}; a capability has one record, "
                            "so extend the existing one rather than opening another")
                continue
            spans = {"-": feat_span(before_text, feat_id), "+": feat_span(after_text, feat_id)}
            # A line is outside the FEAT's scope when it sits outside its span, or names
            # another FEAT-ID: an added heading naming this FEAT cannot widen the span
            # over another capability's row or record.
            outside = [f"{side}{n}" for side, n, text in changed_lines(merge_base, head, path)
                       if text.strip() and (n not in spans[side] or any(f != feat_id for f in FEAT_IDS.findall(text)))]
            if outside:
                errs.append(f"{path}: lines outside {feat_id}'s row and record change ({summarize(outside)}); "
                            "a feature change edits only its own record")
        elif path.startswith(PRODUCT_DOCS) and path not in REGISTRY_DOCS:
            errs.append(f"{path} changes in this feature change; under {PRODUCT_DOCS} only the FEAT's own catalog "
                        "and traceability records, the model registry and its generated files may change here")
    return errs


def check_plan_pr(t: Traced, env: dict, ready: bool) -> list[str]:
    """CI only: the plan records the PR it belongs to. A draft may still say null,
    because the number exists only once the PR is open; a ready PR may not."""
    n = env.get("PR_NUMBER")
    if not n:
        return []
    m = PR_REF.match(str(t.plan_fm.get("pr"))) if t.plan_fm.get("pr") is not None else None
    if m and m.group(1) != n:
        return [f"{t.plan_path}: names PR #{m.group(1)}, but this is PR #{n}"]
    if ready and not m:
        return [f"{t.plan_path}: set the plan's pr to {n} before marking the PR ready"]
    return []


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def row_fields(text: str, feat_id: str) -> dict[str, str]:
    """The FEAT's catalog row as {column header: cell}."""
    lines = text.splitlines()
    header = None
    for line in lines:
        if not line.startswith("|"):
            header = None
            continue
        row = cells(line)
        if header is None:
            header = row
        elif (m := FEAT_ROW.match(line)) and m.group(1) == feat_id:
            return dict(zip(header, row))
    return {}


def feat_record(text: str | None, feat_id: str) -> str:
    """The FEAT's catalog record as rendered: its section where the catalog has one
    (stocks) and its table rows (solyra); what a close-out must change."""
    shown = visible(text or "")
    lines = shown.splitlines()
    section = [lines[ln - 1] for ln in section_of(shown, feat_id) if ln <= len(lines)]
    rows = [line for line in lines if line.startswith("|") and feat_id in line]
    return "\n".join(section + rows)


def feat_fields(text: str | None, feat_id: str) -> dict[str, str]:
    """The FEAT's Status and Last reviewed: from its record's field table where the
    record has one (stocks), otherwise from its catalog row's columns (solyra).
    Read as rendered: a row inside an HTML comment or a code block is not a field."""
    text = visible(text or "")
    lines = text.splitlines()
    fields = {}
    for ln in section_of(text, feat_id):
        row = cells(lines[ln - 1]) if lines[ln - 1].startswith("|") else []
        if len(row) == 2 and row[0] in CLOSE_OUT_FIELDS:
            fields[row[0]] = row[1]
    if fields:
        return fields
    return {h: v for h, v in row_fields(text, feat_id).items() if h in CLOSE_OUT_FIELDS}


def added_lines(merge_base: str, head: str, path: str) -> list[tuple[int, str]]:
    """(line number in head, text) for every line the PR adds to path."""
    out, lineno = [], 0
    for line in git_out("diff", "-U0", merge_base, head, "--", path).splitlines():
        hunk = re.match(r"^@@ -\S+ \+(\d+)", line)
        if hunk:
            lineno = int(hunk.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            out.append((lineno, line[1:]))
            lineno += 1
    return out


def section_of(text: str, feat_id: str) -> range:
    """Line numbers (1-based) of the section whose heading names feat_id."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        h = HEADING.match(line)
        if h and feat_id in line:
            level = len(h.group(1))
            end = next((j for j in range(i + 1, len(lines))
                        if (hh := HEADING.match(lines[j])) and len(hh.group(1)) <= level), len(lines))
            return range(i + 1, end + 1)
    return range(0)


def lineage_refs(text: str, feat_id: str) -> set[str]:
    """The PR entries in the FEAT's traceability section as rendered: each `**PR lineage:**`
    line or list item in the visible section, so a `<!-- #N -->` is not an entry."""
    shown = visible(text)
    lines = shown.splitlines()
    return {line.strip() for ln in section_of(shown, feat_id)
            if ln <= len(lines) and re.match(r"^\s*(\*\*PR lineage:\*\*|[-*]\s)", (line := lines[ln - 1]))}


def calendar_date(value: str) -> bool:
    """True for a real YYYY-MM-DD date: 2026-99-99 is shaped like one and is not one."""
    if not ISO_DATE.match(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def check_close_out(t: Traced, ch: Change, merge_base: str, head: str, env: dict) -> list[str]:
    """CI only, once the PR is ready for review: the Phase 5 records exist in this PR."""
    n = env["PR_NUMBER"]
    pr_ref = re.compile(rf"#{re.escape(n)}(?![\w])")
    errs: list[str] = []
    matched = matched_boxes(done_items(t), checklist(env.get("PR_BODY") or ""))
    unticked = [i for i, box in matched.items() if not (box and box[0])]
    if unticked:
        errs.append("ready for review with done_when item(s) not ticked: " + "; ".join(unticked))
    now = feat_fields(ch.tree.read(CATALOG), t.feat_id)
    before = feat_fields(Tree(merge_base).read(CATALOG), t.feat_id)
    reviewed, status = now.get("Last reviewed", ""), now.get("Status", "").strip("* ")
    head_day = git_out("show", "-s", "--format=%cs", head).strip()
    # The head commit's date, exactly: any other date, past or future, is a false freshness record.
    if not calendar_date(reviewed) or reviewed != head_day:
        errs.append(f"{CATALOG}: set the {t.feat_id} Last reviewed to this PR's head commit date {head_day} in "
                    f"its row or record (it reads '{reviewed or 'nothing'}')")
    elif feat_record(ch.tree.read(CATALOG), t.feat_id) == feat_record(Tree(merge_base).read(CATALOG), t.feat_id):
        errs.append(f"{CATALOG}: the {t.feat_id} record is unchanged from the base although it already reads "
                    f"{head_day}; a second PR the same day still updates its record (its PRs, Status or notes)")
    if status.lower() in ("", "unknown", "tbd"):
        errs.append(f"{CATALOG}: set the {t.feat_id} Status in its row or record (it reads '{status or 'nothing'}')")
    # Which record carries the lineage is policy, read at the base: a repository that
    # keeps it in the catalog row (solyra) cannot be moved off that check by a PR that
    # brings its own traceability document.
    if ch.base.read(TRACEABILITY) is not None:
        now_lineage = lineage_refs(ch.tree.read(TRACEABILITY) or "", t.feat_id)
        before_lineage = lineage_refs(Tree(merge_base).read(TRACEABILITY) or "", t.feat_id)
        if not any(pr_ref.search(entry) for entry in now_lineage - before_lineage):
            errs.append(f"{TRACEABILITY}: add this PR (#{n}) to the {t.feat_id} section's PR lineage "
                        "(a `**PR lineage:**` line or a list item; a comment or prose mention does not count)")
        # Every PR the lineage named before is still named: a `**PR lineage:**` line grows
        # in place, so entries are compared by the PRs they mention, not by their text.
        mentioned = lambda entries: {m for e in entries for m in PR_MENTION.findall(e)}
        lost = sorted(mentioned(before_lineage) - mentioned(now_lineage), key=int)
        if lost:
            errs.append(f"{TRACEABILITY}: the {t.feat_id} PR lineage loses earlier PR(s) "
                        f"#{', #'.join(lost)}; lineage only grows")
    else:
        prs = row_fields(visible(ch.tree.read(CATALOG) or ""), t.feat_id).get("PRs", "")
        if not pr_ref.search(prs):
            errs.append(f"{CATALOG}: add this PR (#{n}) to the {t.feat_id} row's PRs column (it reads '{prs or 'nothing'}')")
        before_prs = set(PR_MENTION.findall(row_fields(visible(Tree(merge_base).read(CATALOG) or ""), t.feat_id).get("PRs", "")))
        lost = sorted(before_prs - set(PR_MENTION.findall(prs)), key=int)
        if lost:
            errs.append(f"{CATALOG}: the {t.feat_id} row's PRs column loses earlier PR(s) "
                        f"#{', #'.join(lost)}; the column only grows")
    return errs


def merges_main() -> bool:
    """During a merge: is MERGE_HEAD a commit of main (origin/main, else main)?"""
    for main in ("origin/main", "main"):
        if resolve(main):
            return git("merge-base", "--is-ancestor", "MERGE_HEAD", main).returncode == 0
    return False


def resolve(rev: str) -> str | None:
    r = git("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    return r.stdout.strip() if r.returncode == 0 else None


def fail(errs: list[str]) -> int:
    print("SPEC GATE FAILED")
    for e in errs:
        print(" -", e)
    print("\nRun the product-delivery skill (Phase 1 to 3) before continuing.")
    return 1


def main(argv: list[str]) -> int:
    try:
        return run(argv)
    except GitFailed as e:
        return fail([str(e)])


def run(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--commit"
    env = os.environ
    if mode == "--check-spec":
        if len(argv) < 3:
            print(__doc__)
            return 2
        tree = Tree(WORKTREE)
        path = pathlib.Path(argv[2])
        fm = frontmatter(path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None)
        errs = validate_spec(fm, path.name, catalog_ids(tree.read(CATALOG)), requirement_defs(tree))
        print("\n".join(errs) if errs else "spec ok")
        return 1 if errs else 0
    if mode == "--commit":
        real = git_out("rev-parse", "--abbrev-ref", "HEAD").strip()
        override = env.get("SPEC_GATE_BRANCH")
        if override and real != "HEAD":
            return fail([f"SPEC_GATE_BRANCH={override} is set, but HEAD is on branch '{real}'; "
                         "the override names a detached commit only. Unset it, or check the branch out."])
        branch = override if real == "HEAD" and override else real
        # --no-renames: a rename is listed as its deleted source and its added destination,
        # so moving code out to a documentation path is still seen as a change to that code.
        # A merge in progress (MERGE_HEAD exists): merging main into the branch stages
        # everything main brings in, so the branch's own contribution is the index measured
        # against main's side. Merging anything else (another branch into this one) IS this
        # branch taking on that code, and is measured against HEAD like any commit. Nothing
        # merges into main locally: main takes pull requests.
        against = []
        if resolve("MERGE_HEAD"):
            if branch == "main":
                return fail(["a merge into main is committed locally; main takes pull requests, "
                             "not local merges. Abort it (git merge --abort) and open a PR."])
            if merges_main():
                against = ["MERGE_HEAD"]
        staged = git_out("diff", "--cached", "--name-only", "--no-renames", *against).splitlines()
        before = Tree(against[0] if against else "HEAD")
        ch = Change("commit", branch, staged, Tree(None), before, before)
        errs, _ = check(ch)
    elif mode == "--pr":
        base_arg = argv[2] if len(argv) > 2 else "origin/main"
        head_arg = argv[3] if len(argv) > 3 else "HEAD"
        base, head = resolve(base_arg), resolve(head_arg)
        missing = [r for r, sha in ((base_arg, base), (head_arg, head)) if sha is None]
        if missing:
            return fail([f"ref(s) {', '.join(missing)} do not exist in this checkout; cannot compute the diff. "
                         "Fetch them (git fetch origin main) or pass the right refs. Refusing to pass on an empty diff."])
        merge_base = git("merge-base", base, head).stdout.strip()
        if not merge_base:
            return fail([f"no merge base between {base_arg} and {head_arg} (shallow clone?). Use fetch-depth: 0."])
        branch = env.get("PR_HEAD_REF") or git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        head_repo, base_repo = env.get("PR_HEAD_REPO"), env.get("PR_BASE_REPO")
        trusted = not (base_repo and head_repo != base_repo)
        changed = git_out("diff", "--name-only", "--no-renames", merge_base, head).splitlines()
        # Policy (the catalog row, the approved spec, the requirements) is read at the PR's
        # CURRENT base, so a spec superseded on main after the branch forked is seen; the
        # diff is still measured from the merge base.
        # A PR targets the integration branch only: a stacked PR onto another branch would
        # be judged against that branch's catalog and specs as if they were policy.
        base_ref = env.get("PR_BASE_REF")
        if base_ref and base_ref != MAIN:
            return fail([f"this PR targets '{base_ref}'; pull requests here target {MAIN} only. Re-target it, "
                         "or wait for the branch it stacks on to merge."])
        ch = Change("pr", branch, changed, Tree(head), Tree(base), Tree(merge_base), trusted)
        errs, traced = check(ch)
        if (m := BRANCH.match(branch)):
            errs += check_product_scope(m.group(2).upper(), ch, merge_base, head)
        # The checks below read the traced plan and spec; without them the errors from
        # check() already say what is missing.
        # A workload change wants its numbers whatever the branch: a chore/ PR editing
        # the gate's workflows is untraced and still changes what CI runs.
        errs += check_capacity(env.get("PR_BODY"), ch.changed)
        if traced:
            errs += check_pr_metadata(traced, env, ch.tree)
            ready = env.get("PR_DRAFT") == "false"
            errs += check_plan_pr(traced, env, ready)
            if env.get("PR_NUMBER") and ready:
                errs += check_close_out(traced, ch, merge_base, head, env)
    else:
        print(__doc__)
        return 2
    if errs:
        return fail(errs)
    print(f"spec gate ok (branch={ch.branch}, {len(ch.changed)} changed file(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
