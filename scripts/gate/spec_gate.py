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

  chore/             dependency manifests, lockfiles, and the gate's own files
  bot/superpowers-   the vendored skills under .claude/skills/
  spike/             anything, for local commits only: a spike opens no PR

No branch is exempt by name. A pull request from a fork gets no prefix
allowance. A detached HEAD that stages gated files is blocked: name the branch
with SPEC_GATE_BRANCH=<branch> git commit ...

--commit reads the catalog, specs and plans from the index, so it validates
what is being committed. --pr reads them from HEAD's git objects, so CI runs
this script from the base branch without checking the PR out. In CI the branch
comes from PR_HEAD_REF, fork detection from PR_HEAD_REPO and PR_BASE_REPO, and
PR_TITLE, PR_BODY, PR_NUMBER and PR_DRAFT drive the metadata and close-out
checks. Any harness (Claude Code, Codex, a human) hits the same check.
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPECS = "docs/superpowers/specs"
PLANS = "docs/superpowers/plans"
CATALOG = "docs/product/02-FEATURE-CATALOG.md"
REQUIREMENTS = "docs/product/01-PRODUCT-REQUIREMENTS.md"
TRACEABILITY = "docs/product/12-PR-ISSUE-TRACEABILITY.md"

FEAT_ROW = re.compile(r"^\|\s*\[?(FEAT-[A-Z]+-\d{3})\b", re.M)
BRANCH = re.compile(r"^(feature|fix)/(feat-[a-z]+-\d{3})-[a-z0-9][a-z0-9._-]*$", re.I)
REQ_SHAPE = re.compile(r"^REQ-[A-Z]+-\d{3}$")
REQ_DEFINITION = re.compile(r"\*\*(REQ-[A-Z]+-\d{3}):\*\*")
CHECKBOX = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.*\S)\s*$")
HEADING = re.compile(r"^(#{1,6})\s")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PR_REF = re.compile(r"^#?(\d+)$")
CLOSE_OUT_FIELDS = ("Status", "Last reviewed")

MANIFEST = re.compile(
    r"(^|/)(package(-lock)?\.json|requirements[^/]*\.(txt|lock)|pyproject\.toml|poetry\.lock"
    r"|yarn\.lock|pnpm-lock\.yaml|bun\.lockb?)$"
)
GATE_FILES = (
    "scripts/gate/",
    ".githooks/",
    ".github/workflows/spec-gate.yml",
    "tests/scripts/test_spec_gate.py",
    "tests/scripts/test_export_model_registry.py",
)
ALLOWANCES = (
    ("chore/", lambda p: bool(MANIFEST.search(p)) or p.startswith(GATE_FILES)),
    ("bot/superpowers-", lambda p: p.startswith(".claude/skills/")),
)
REQUIRED_SPEC_KEYS = ("feat_id", "req_ids", "done_when", "status")
REQUIRED_PLAN_KEYS = ("feat_id", "spec", "branch", "status")
SPEC_STATUSES = ("draft", "approved", "superseded")
PLAN_STATUSES = ("ready", "done")
WORKTREE = "worktree"


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=ROOT)


def catalog_ids(text: str | None) -> set[str]:
    """FEAT-IDs from the first cell of the catalog's table rows. A FEAT-ID mentioned
    anywhere else (prose, a link, a comment) is not a catalog entry."""
    return set(FEAT_ROW.findall(text or ""))


def is_documentation(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (path.startswith("docs/") or path.endswith((".md", ".drawio"))
            or name.startswith("LICENSE") or path == ".gitignore")


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
            found = git("ls-files", "--", folder).stdout.splitlines()
        else:
            found = git("ls-tree", "-r", "--name-only", self.rev, "--", folder).stdout.splitlines()
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


def validate_spec(fm: dict, name: str, catalog: set[str], req_defs: set[str]) -> list[str]:
    errs = [f"{name}: missing frontmatter key '{k}'" for k in REQUIRED_SPEC_KEYS if k not in fm]
    if fm.get("feat_id") and fm["feat_id"] not in catalog:
        errs.append(f"{name}: feat_id {fm['feat_id']} is not in {CATALOG}")
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
            unknown = [r for r in reqs if REQ_SHAPE.match(r) and req_defs and r not in req_defs]
            if bad:
                errs.append(f"{name}: req_ids not shaped REQ-XXX-000: {', '.join(bad)}")
            if unknown:
                errs.append(f"{name}: req_ids not defined in {REQUIREMENTS}: {', '.join(unknown)}")
    for key in ("issues", "canvases"):
        if key in fm and fm[key] is not None and not isinstance(fm[key], list):
            errs.append(f"{name}: {key} must be a list")
    return errs


def validate_plan(fm: dict, name: str, feat_id: str, tree: Tree) -> list[str]:
    errs = [f"{name}: missing frontmatter key '{k}'" for k in REQUIRED_PLAN_KEYS if k not in fm]
    if fm.get("feat_id") and fm["feat_id"] != feat_id:
        errs.append(f"{name}: feat_id is {fm['feat_id']} but the branch serves {feat_id}")
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
    if spec and tree.read(spec) is None:
        errs.append(f"{name}: spec path does not exist: {spec}")
    return errs


@dataclass
class Change:
    mode: str               # "commit" or "pr"
    branch: str
    changed: list[str]
    tree: Tree
    trusted: bool = True    # False for a PR from a fork: no prefix allowances


@dataclass
class Traced:
    feat_id: str
    spec_path: str
    spec_fm: dict
    plan_path: str
    plan_fm: dict


def summarize(paths: list[str]) -> str:
    shown = ", ".join(paths[:3])
    return shown + (f" and {len(paths) - 3} more" if len(paths) > 3 else "")


def check(ch: Change) -> tuple[list[str], Traced | None]:
    gated = [f for f in ch.changed if not is_documentation(f)]
    if not gated:
        return [], None
    if ch.mode == "commit" and ch.branch == "HEAD":
        return [
            f"detached HEAD with {len(gated)} staged gated file(s) ({summarize(gated)}): "
            "the gate cannot tell which branch this commit is for.",
            "Name it for this commit: SPEC_GATE_BRANCH=feature/<feat-id>-<slug> git commit ...",
        ], None
    if ch.mode == "commit" and ch.branch.startswith("spike/"):
        return [], None
    allowed = next((ok for prefix, ok in ALLOWANCES if ch.branch.startswith(prefix)), None) if ch.trusted else None
    remaining = [f for f in gated if not (allowed and allowed(f))]
    if not remaining:
        return [], None
    m = BRANCH.match(ch.branch)
    if not m:
        why = " A pull request from a fork gets no prefix allowance." if not ch.trusted else ""
        return [
            f"branch '{ch.branch}' changes {len(remaining)} gated file(s) ({summarize(remaining)}) "
            "but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>." + why,
            "docs/ carries documentation only; chore/ covers dependency manifests, lockfiles and the "
            "gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.",
        ], None
    feat_id = m.group(2).upper()
    errs: list[str] = []
    catalog_text = ch.tree.read(CATALOG)
    catalog = catalog_ids(catalog_text)
    if catalog_text is None:
        errs.append(f"{CATALOG} is missing")
    elif feat_id not in catalog:
        errs.append(f"{feat_id} is not a row in {CATALOG}")
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
    spec_path = plan_fm.get("spec")
    spec_text = ch.tree.read(spec_path) if spec_path else None
    if spec_text is None:
        return errs, None
    spec_fm = frontmatter(spec_text)
    if spec_fm.get("feat_id") != feat_id:
        errs.append(f"{spec_path}: the plan's spec serves {spec_fm.get('feat_id')}, not {feat_id}")
    if spec_fm.get("status") == "draft":
        errs.append(f"{spec_path} is still status: draft; get it approved first")
    elif spec_fm.get("status") == "superseded":
        errs.append(f"{spec_path} is status: superseded; point the plan at the spec that replaced it")
    newer = [s for s in ch.tree.list(SPECS) if s != spec_path
             and frontmatter(ch.tree.read(s)).get("supersedes") == spec_path]
    if newer:
        errs.append(f"{spec_path} is superseded by {', '.join(newer)}; point the plan at the current spec")
    req_defs = set(REQ_DEFINITION.findall(ch.tree.read(REQUIREMENTS) or ""))
    errs += validate_spec(spec_fm, spec_path, catalog, req_defs)
    return errs, Traced(feat_id, spec_path, spec_fm, plan_path, plan_fm)


def norm(text: str) -> str:
    return " ".join(text.split())


def checklist(body: str) -> list[tuple[bool, str]]:
    return [(m.group(1) in "xX", norm(m.group(2))) for line in body.splitlines() if (m := CHECKBOX.match(line))]


def done_items(t: Traced) -> list[str]:
    items = t.spec_fm.get("done_when")
    return [norm(str(i)) for i in items] if isinstance(items, list) else []


def check_pr_metadata(t: Traced, env: dict) -> list[str]:
    """CI only: the PR title and body must name what the gate validated."""
    title, body = env.get("PR_TITLE"), env.get("PR_BODY")
    errs: list[str] = []
    if title is not None and not title.startswith(f"{t.feat_id}:"):
        errs.append(f"PR title must start with '{t.feat_id}:', the branch's FEAT-ID, e.g. '{t.feat_id}: <what changed>'")
    if body is not None:
        if t.spec_path not in body:
            errs.append(f"PR body must link the spec the plan names: {t.spec_path}")
        if t.plan_path not in body:
            errs.append(f"PR body must link the plan: {t.plan_path}")
        boxes = checklist(body)
        missing = [i for i in done_items(t) if not any(text.startswith(i) for _, text in boxes)]
        if missing:
            errs.append("PR body must carry each done_when item as a '- [ ]' line starting with its text; "
                        "missing: " + "; ".join(missing))
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


def feat_fields(text: str | None, feat_id: str) -> dict[str, str]:
    """The FEAT's Status and Last reviewed: from its record's field table where the
    record has one (stocks), otherwise from its catalog row's columns (solyra)."""
    text = text or ""
    lines = text.splitlines()
    fields = {}
    for ln in section_of(text, feat_id):
        row = cells(lines[ln - 1]) if lines[ln - 1].startswith("|") else []
        if len(row) == 2 and row[0] in CLOSE_OUT_FIELDS:
            fields[row[0]] = row[1]
    if fields:
        return fields
    header = None
    for line in lines:
        if not line.startswith("|"):
            header = None
            continue
        row = cells(line)
        if header is None:
            header = row
        elif (m := FEAT_ROW.match(line)) and m.group(1) == feat_id:
            return {h: v for h, v in zip(header, row) if h in CLOSE_OUT_FIELDS}
    return {}


def added_lines(merge_base: str, head: str, path: str) -> list[tuple[int, str]]:
    """(line number in head, text) for every line the PR adds to path."""
    out, lineno = [], 0
    for line in git("diff", "-U0", merge_base, head, "--", path).stdout.splitlines():
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


def check_close_out(t: Traced, ch: Change, merge_base: str, head: str, env: dict) -> list[str]:
    """CI only, once the PR is ready for review: the Phase 5 records exist in this PR."""
    n = env["PR_NUMBER"]
    pr_ref = re.compile(rf"#{re.escape(n)}(?!\d)")
    errs: list[str] = []
    boxes = checklist(env.get("PR_BODY") or "")
    unticked = [i for i in done_items(t) if not any(ticked and text.startswith(i) for ticked, text in boxes)]
    if unticked:
        errs.append("ready for review with done_when item(s) not ticked: " + "; ".join(unticked))
    cat_added = added_lines(merge_base, head, CATALOG)
    now = feat_fields(ch.tree.read(CATALOG), t.feat_id)
    before = feat_fields(Tree(merge_base).read(CATALOG), t.feat_id)
    reviewed, status = now.get("Last reviewed", ""), now.get("Status", "").strip("* ")
    head_day = git("show", "-s", "--format=%cs", head).stdout.strip()
    # Changed from the base, or already today's date (a second PR for this FEAT the same day).
    if not ISO_DATE.match(reviewed) or (reviewed == before.get("Last reviewed") and reviewed != head_day):
        errs.append(f"{CATALOG}: set the {t.feat_id} Last reviewed to this PR's review date in its row or "
                    f"record (it reads '{reviewed or 'nothing'}')")
    if status.lower() in ("", "unknown", "tbd"):
        errs.append(f"{CATALOG}: set the {t.feat_id} Status in its row or record (it reads '{status or 'nothing'}')")
    trace_text = ch.tree.read(TRACEABILITY)
    if trace_text is not None:
        section = section_of(trace_text, t.feat_id)
        if not any(ln in section and pr_ref.search(text) for ln, text in added_lines(merge_base, head, TRACEABILITY)):
            errs.append(f"{TRACEABILITY}: add this PR (#{n}) under the {t.feat_id} section")
    elif not any(t.feat_id in text and pr_ref.search(text) for _, text in cat_added):
        errs.append(f"{CATALOG}: add this PR (#{n}) to the {t.feat_id} row's PRs column")
    return errs


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
    mode = argv[1] if len(argv) > 1 else "--commit"
    env = os.environ
    if mode == "--check-spec":
        if len(argv) < 3:
            print(__doc__)
            return 2
        tree = Tree(WORKTREE)
        path = pathlib.Path(argv[2])
        fm = frontmatter(path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None)
        errs = validate_spec(fm, path.name, catalog_ids(tree.read(CATALOG)),
                             set(REQ_DEFINITION.findall(tree.read(REQUIREMENTS) or "")))
        print("\n".join(errs) if errs else "spec ok")
        return 1 if errs else 0
    if mode == "--commit":
        branch = env.get("SPEC_GATE_BRANCH") or git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        # --no-renames: a rename is listed as its deleted source and its added destination,
        # so moving code out to a documentation path is still seen as a change to that code.
        staged = git("diff", "--cached", "--name-only", "--no-renames").stdout.splitlines()
        ch = Change("commit", branch, staged, Tree(None))
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
        changed = git("diff", "--name-only", "--no-renames", merge_base, head).stdout.splitlines()
        ch = Change("pr", branch, changed, Tree(head), trusted)
        errs, traced = check(ch)
        if traced:
            errs += check_pr_metadata(traced, env)
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
