#!/usr/bin/env python3
"""Spec gate: refuses code changes that have no FEAT-ID, approved spec, and plan.

Usage:
  python3 scripts/gate/spec_gate.py --commit                 # pre-commit hook: staged files
  python3 scripts/gate/spec_gate.py --pr [origin/main]       # CI: files changed vs base;
                                                              #     also checks PR_TITLE / PR_BODY env if set
  python3 scripts/gate/spec_gate.py --check-spec <path>      # validate one spec file's frontmatter

Exit 0 = ok, 1 = blocked. Prints what to do next.

Exempt branches (no spec needed): main (exact), docs/*, chore/*, spike/*.
Only diffs that touch CODE_DIRS are gated; a doc-only diff on any branch passes.
Any harness (Claude Code, Codex, a human) hits the same check.
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPECS = ROOT / "docs" / "superpowers" / "specs"
PLANS = ROOT / "docs" / "superpowers" / "plans"
CATALOG = ROOT / "docs" / "product" / "02-FEATURE-CATALOG.md"

FEAT = re.compile(r"FEAT-[A-Z]+-\d{3}")
EXEMPT_BRANCHES = ("main", "master", "HEAD")
EXEMPT_BRANCH_PREFIXES = ("docs/", "chore/", "spike/", "dependabot/", "renovate/")
CODE_DIRS = ("lib/", "gcp/", "platform/", "scripts/", "src/", "tradingview-pine-scripts/")
GATE_SELF = ("scripts/gate/",)  # the gate may change itself on a chore/ branch
REQUIRED_SPEC_KEYS = ("feat_id", "req_ids", "done_when", "status")
REQUIRED_PLAN_KEYS = ("feat_id", "spec", "branch", "status")


def sh(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=ROOT).stdout.strip()


def frontmatter(path: pathlib.Path) -> dict:
    """Minimal YAML frontmatter reader: top-level `key: value` and `key:` + `  - item` lists."""
    text = path.read_text(encoding="utf-8", errors="replace")
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
            elif v.startswith("[") and v.endswith("]"):
                fm[k] = [x.strip().strip('"') for x in v[1:-1].split(",") if x.strip()]
            else:
                fm[k] = v.strip('"')
    return fm


def catalog_ids() -> set[str]:
    if not CATALOG.exists():
        return set()
    return set(FEAT.findall(CATALOG.read_text(encoding="utf-8", errors="replace")))


def find_doc(folder: pathlib.Path, feat_id: str, statuses: tuple[str, ...] | None = None):
    """Return (path, frontmatter) of the newest doc for feat_id, optionally requiring a status."""
    hits = []
    if not folder.exists():
        return None
    for p in sorted(folder.glob("*.md")):
        fm = frontmatter(p)
        if fm.get("feat_id") != feat_id:
            continue
        if statuses and fm.get("status") not in statuses:
            continue
        hits.append((p, fm))
    return hits[-1] if hits else None


def validate_spec(path: pathlib.Path) -> list[str]:
    fm = frontmatter(path)
    errs = [f"{path.name}: missing frontmatter key '{k}'" for k in REQUIRED_SPEC_KEYS if k not in fm]
    if fm.get("feat_id") and fm["feat_id"] not in catalog_ids():
        errs.append(f"{path.name}: feat_id {fm['feat_id']} is not in {CATALOG.relative_to(ROOT)}")
    if fm.get("status") not in ("draft", "approved", "superseded"):
        errs.append(f"{path.name}: status must be draft | approved | superseded")
    if isinstance(fm.get("done_when"), list) and len(fm["done_when"]) == 0:
        errs.append(f"{path.name}: done_when is empty; a spec with no done_when cannot be closed")
    return errs


def validate_plan(path: pathlib.Path) -> list[str]:
    fm = frontmatter(path)
    errs = [f"{path.name}: missing frontmatter key '{k}'" for k in REQUIRED_PLAN_KEYS if k not in fm]
    spec = fm.get("spec")
    if spec and not (ROOT / spec).exists():
        errs.append(f"{path.name}: spec path does not exist: {spec}")
    return errs


def gated_files(changed: list[str]) -> list[str]:
    return [f for f in changed if f.startswith(CODE_DIRS) and not f.startswith(GATE_SELF)]


def check_pr_metadata(branch: str, changed: list[str]) -> list[str]:
    """CI only: PR title/body rules, read from PR_TITLE / PR_BODY env. Fire only when code is touched."""
    if branch in EXEMPT_BRANCHES or branch.startswith(EXEMPT_BRANCH_PREFIXES) or not gated_files(changed):
        return []
    title, body = os.environ.get("PR_TITLE"), os.environ.get("PR_BODY")
    errs: list[str] = []
    if title is not None and not FEAT.search(title):
        errs.append("PR title must carry the FEAT-ID, e.g. 'FEAT-SIGNAL-001: share golden fixtures'")
    if body is not None:
        if "- [" not in body:
            errs.append("PR body must paste the spec's done_when as a '- [ ]' checklist")
        if "docs/superpowers/specs/" not in body:
            errs.append("PR body must link the spec under docs/superpowers/specs/")
    return errs


def check(branch: str, changed: list[str]) -> list[str]:
    if branch in EXEMPT_BRANCHES or branch.startswith(EXEMPT_BRANCH_PREFIXES):
        return []
    gated = gated_files(changed)
    if not gated:
        return []
    m = FEAT.search(branch.upper())
    if not m:
        return [
            f"branch '{branch}' touches code ({len(gated)} file(s)) but carries no FEAT-ID.",
            "Name the branch feature/<feat-id>-<slug> or fix/<feat-id>-<slug>, or use docs/ chore/ spike/ for exempt work.",
        ]
    feat_id = m.group(0)
    errs: list[str] = []
    if feat_id not in catalog_ids():
        errs.append(f"{feat_id} is not a row in {CATALOG.relative_to(ROOT)}")
    spec = find_doc(SPECS, feat_id, ("approved",))
    if not spec:
        drafted = find_doc(SPECS, feat_id, ("draft",))
        if drafted:
            errs.append(f"spec for {feat_id} exists but is still status: draft ({drafted[0].name}); get it approved first")
        else:
            errs.append(f"no approved spec for {feat_id} in {SPECS.relative_to(ROOT)}")
    else:
        errs += validate_spec(spec[0])
    plan = find_doc(PLANS, feat_id)
    if not plan:
        errs.append(f"no plan for {feat_id} in {PLANS.relative_to(ROOT)}")
    else:
        errs += validate_plan(plan[0])
        if plan[1].get("branch") and plan[1]["branch"] != branch:
            errs.append(f"plan {plan[0].name} names branch '{plan[1]['branch']}' but you are on '{branch}'")
    return errs


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--commit"
    if mode == "--check-spec":
        errs = validate_spec(pathlib.Path(argv[2]))
        print("\n".join(errs) if errs else "spec ok")
        return 1 if errs else 0

    branch = sh("git rev-parse --abbrev-ref HEAD")
    if mode == "--commit":
        changed = sh("git diff --cached --name-only").splitlines()
    elif mode == "--pr":
        base = argv[2] if len(argv) > 2 else "origin/main"
        if subprocess.run(["git", "rev-parse", "--verify", "--quiet", base], cwd=ROOT, capture_output=True).returncode != 0:
            print(f"SPEC GATE FAILED\n - base ref '{base}' does not exist in this checkout; cannot compute the diff.")
            print("   Fetch it (git fetch origin main) or pass the right base. Refusing to pass on an empty diff.")
            return 1
        merge_base = sh(f"git merge-base {base} HEAD")
        if not merge_base:
            print(f"SPEC GATE FAILED\n - no merge base between {base} and HEAD (shallow clone?). Use fetch-depth: 0.")
            return 1
        changed = sh(f"git diff --name-only {merge_base} HEAD").splitlines()
    else:
        print(__doc__)
        return 2

    errs = check(branch, changed)
    if mode == "--pr":
        errs += check_pr_metadata(branch, changed)
    if errs:
        print("SPEC GATE FAILED")
        for e in errs:
            print(" -", e)
        print("\nRun the product-delivery skill (Phase 1 to 3) before continuing.")
        return 1
    print(f"spec gate ok (branch={branch}, {len(changed)} changed file(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
