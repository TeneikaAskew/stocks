#!/usr/bin/env python3
"""Structural gates for the monthly architecture-doc refresh.

Run by `.github/workflows/refresh-architecture-docs.yml` after Gemini has
updated the prose, and runnable locally against a saved live snapshot:

    python scripts/maintenance/check_generated_docs.py --snapshot live.json \
        --previous-dir refresh-inputs/previous --transcripts-dir refresh-inputs/transcripts

Each gate turns one of the 2026-09-02 failure modes into a red run:

* coverage      every declared and live job, every schema table, every
                router and every scheduler is named in ARCHITECTURE.md; every
                declared job has a blast-radius row in DATA_DEPENDENCIES.md
* subsections   DATA_DEPENDENCIES.md has a `### `table`` heading in both the
                write graph and the read graph for every table
* markers       the <!-- inventory:*:start/end --> blocks are byte-identical to
                a fresh render (the model must not edit inside them)
* headings      no H2/H3 present in the previous version is missing, unless it
                is listed under "Removed since last refresh"
* size          each doc is at least 80% of its previous line count
* stale         no retired name or phrase appears outside history context
* links         every relative markdown link resolves
* readme        README.md is a pointer map: links the required docs, embeds
                no mermaid block, does not describe a Vite frontend here
* transcripts   Gemini never reported a truncated input file

Exit code is 1 when any gate fails. Findings are printed as GitHub
workflow-command errors so they surface inline in the run.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.maintenance import doc_inventory as inv  # noqa: E402

DOCS = ("ARCHITECTURE.md", "DATA_DEPENDENCIES.md", "COST_ANALYSIS.md", "README.md")
MARKER_DOCS = ("ARCHITECTURE.md", "DATA_DEPENDENCIES.md", "docs/API.md")
SIZE_FLOOR = 0.80
# README.md is a pointer map by design (2026-09-07); its length is not a
# content signal, so it is exempt from the size floor (headings still apply).
SIZE_FLOOR_EXEMPT = ("README.md",)
REMOVED_HEADING = "Removed since last refresh"

# Names and phrases that describe a surface this repo no longer has. A line
# may still carry one when it is explicitly about history.
STALE_STRINGS = (
    "db-query.yml",
    "platform/src",
    "X-Admin-Token",
    "deploy-platform-staging.yml",
    "promote-platform-prod.yml",
    "download-google-sheets.yml",
    "`/watch`",
    "FastAPI + React",
    "Vite frontend",
    "make dev` to start the FastAPI backend and Vite",
    "no public authentication",
    "trading-platform-staging",
)
HISTORY_OK = re.compile(
    r"\b(was|were|formerly|previously|renamed|retired|deleted|predates|replaced|"
    r"superseded|old|legacy|until|removed|dropped|paused|missing|deprecated|"
    r"no longer|merged|stub|history|since)\b|Removed since last refresh|verify-docs-ok",
    re.I,
)
README_REQUIRED_LINKS = (
    "ARCHITECTURE.md", "DATA_DEPENDENCIES.md", "COST_ANALYSIS.md", "RUNBOOK.md",
    "ERD.md", "docs/PIPELINE.md", "docs/DATA_PIPELINE.md", "docs/API.md",
    "docs/product/README.md", "CLAUDE.md", "SETUP.md",
)
LINK = re.compile(r"\]\(([^)#\s]+)(#[^)]*)?\)")


def _err(msg: str) -> None:
    print(f"::error::{msg}")


def _headings(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", h.strip()) for h in re.findall(r"^#{2,3} +(.+)$", text, re.M)]


def gate_coverage(root: pathlib.Path, repo: dict, live: dict | None) -> list[str]:
    arch = (root / "ARCHITECTURE.md").read_text()
    deps = (root / "DATA_DEPENDENCIES.md").read_text()
    out = []
    names = {j["name"] for j in repo["jobs"]} | set((live or {}).get("jobs", {}))
    miss = sorted(n for n in names if f"`{n}`" not in arch)
    if miss:
        out.append(f"ARCHITECTURE.md does not name these jobs: {' '.join(miss)}")
    miss = sorted(t["name"] for t in repo["tables"] if f"`{t['name']}`" not in arch)
    if miss:
        out.append(f"ARCHITECTURE.md does not name these tables: {' '.join(miss)}")
    miss = sorted(r for r in repo["routers"] if f"routers/{r}.py" not in arch)
    if miss:
        out.append(f"ARCHITECTURE.md does not name these routers: {' '.join(miss)}")
    sched = {s["name"] for s in repo["schedulers"]} | set((live or {}).get("schedulers", {}))
    miss = sorted(n for n in sched if f"`{n}`" not in arch)
    if miss:
        out.append(f"ARCHITECTURE.md does not name these schedulers: {' '.join(miss)}")
    svc = set((live or {}).get("services", {}))
    miss = sorted(n for n in svc if f"`{n}`" not in arch)
    if miss:
        out.append(f"ARCHITECTURE.md does not name these services: {' '.join(miss)}")
    blast_start = deps.find("inventory:blast:start")
    blast = deps[blast_start:] if blast_start >= 0 else ""
    miss = sorted(j["name"] for j in repo["jobs"] if f"| `{j['name']}` |" not in blast)
    if miss:
        out.append(f"DATA_DEPENDENCIES.md blast-radius block lacks rows for: {' '.join(miss)}")
    return out


def gate_subsections(root: pathlib.Path, repo: dict) -> list[str]:
    deps = (root / "DATA_DEPENDENCIES.md").read_text()
    out = []
    names = [t["name"] for t in repo["tables"]] + [v["name"] for v in repo["materialized_views"]] + [v["name"] for v in repo["views"]]
    for t in names:
        n = len(re.findall(rf"^### `{re.escape(t)}`\s*$", deps, re.M))
        if n < 2:
            out.append(f"DATA_DEPENDENCIES.md has {n} `### `{t}`` subsection(s); needs one in §2 and one in §3")
    return out


def gate_markers(root: pathlib.Path, repo: dict, live: dict | None) -> list[str]:
    out = []
    for doc in MARKER_DOCS:
        src = root / doc
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td) / doc
            tmp.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, tmp)
            inv.insert_blocks(tmp, repo, live, root=pathlib.Path(td))
            if tmp.read_text() != src.read_text():
                out.append(f"{doc}: an inventory marker block differs from a fresh render — the model edited inside a block, or a block is missing its end marker")
    for doc in MARKER_DOCS:
        text = (root / doc).read_text()
        for name in inv.SECTIONS:
            s, e = inv.MARKER_START.format(name=name), inv.MARKER_END.format(name=name)
            if (s in text) != (e in text):
                out.append(f"{doc}: unbalanced markers for inventory:{name}")
    return out


def gate_headings_and_size(root: pathlib.Path, previous_dir: pathlib.Path | None) -> list[str]:
    out = []
    if previous_dir is None:
        return out
    for doc in DOCS:
        prev = previous_dir / doc
        if not prev.exists():
            continue
        old, new = prev.read_text(), (root / doc).read_text()
        removed_section = new[new.find(REMOVED_HEADING):] if REMOVED_HEADING in new else ""
        new_heads = {h.lower() for h in _headings(new)}
        for h in _headings(old):
            core = re.sub(r"^[\d.]+\s*", "", h)
            if h.lower() in new_heads or core.lower() in {re.sub(r"^[\d.]+\s*", "", x) for x in new_heads}:
                continue
            if core and core.lower() in removed_section.lower():
                continue
            out.append(f"{doc}: heading lost since the previous version and not listed under '{REMOVED_HEADING}': {h!r}")
        o, n = len(old.splitlines()), len(new.splitlines())
        if doc not in SIZE_FLOOR_EXEMPT and n < o * SIZE_FLOOR:
            out.append(f"{doc}: shrank from {o} to {n} lines (< {int(SIZE_FLOOR*100)}%) — content was dropped, not updated")
    return out


def gate_stale(root: pathlib.Path) -> list[str]:
    out = []
    for doc in DOCS:
        for i, line in enumerate((root / doc).read_text().splitlines(), 1):
            for s in STALE_STRINGS:
                if s in line and not HISTORY_OK.search(line):
                    out.append(f"{doc}:{i}: stale reference {s!r} outside history context")
    return out


def gate_links(root: pathlib.Path) -> list[str]:
    out = []
    for doc in DOCS:
        text = (root / doc).read_text()
        base = (root / doc).parent
        for m in LINK.finditer(text):
            t = m.group(1)
            if t.startswith(("http://", "https://", "mailto:")):
                continue
            if not (base / t).exists() and not (root / t).exists():
                out.append(f"{doc}: dead relative link {t}")
    return sorted(set(out))


def gate_readme(root: pathlib.Path) -> list[str]:
    text = (root / "README.md").read_text()
    out = []
    for req in README_REQUIRED_LINKS:
        if f"({req})" not in text:
            out.append(f"README.md documentation map does not link {req}")
    if "```mermaid" in text:
        out.append("README.md embeds a mermaid block; it is a pointer map, the diagram lives in ARCHITECTURE.md")
    return out


def gate_transcripts(transcripts_dir: pathlib.Path | None) -> list[str]:
    out = []
    if transcripts_dir is None or not transcripts_dir.exists():
        return out
    for f in sorted(transcripts_dir.glob("*.log")):
        text = f.read_text(errors="replace")
        if re.search(r"truncat", text, re.I) and re.search(r"refresh-inputs|\.json|\.md", text):
            out.append(f"{f.name}: the model reported a truncated input — digest that file smaller instead of accepting a partial read")
        if re.search(r"ignored by configured ignore patterns", text):
            out.append(f"{f.name}: the model could not read an input file (gitignored)")
    return out


def run(root: pathlib.Path, snapshot: pathlib.Path | None, previous_dir: pathlib.Path | None,
        transcripts_dir: pathlib.Path | None) -> list[str]:
    repo = inv.repo_inventory(root)
    live = json.loads(snapshot.read_text()) if snapshot else None
    findings: list[str] = []
    findings += gate_coverage(root, repo, live)
    findings += gate_subsections(root, repo)
    findings += gate_markers(root, repo, live)
    findings += gate_headings_and_size(root, previous_dir)
    findings += gate_stale(root)
    findings += gate_links(root)
    findings += gate_readme(root)
    findings += gate_transcripts(transcripts_dir)
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--snapshot", help="live snapshot JSON from doc_inventory --write-snapshot")
    ap.add_argument("--previous-dir", help="directory holding the previous versions of the four docs")
    ap.add_argument("--transcripts-dir", help="directory holding the Gemini run transcripts")
    a = ap.parse_args(argv)
    findings = run(pathlib.Path(a.root), pathlib.Path(a.snapshot) if a.snapshot else None,
                   pathlib.Path(a.previous_dir) if a.previous_dir else None,
                   pathlib.Path(a.transcripts_dir) if a.transcripts_dir else None)
    for f in findings:
        _err(f)
    print(f"check_generated_docs: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
