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
# Every block each document must carry. A balanced-pairs check alone lets a
# block vanish when both its markers are deleted together (Codex, PR #1009).
EXPECTED_MARKERS = {
    "ARCHITECTURE.md": ("jobs", "schedulers", "tables", "dbtables", "routes", "services", "reconcile", "modules"),
    "DATA_DEPENDENCIES.md": ("tables", "dbtables", "writes", "reads", "multiwriter", "orphans", "blast"),
    "docs/API.md": ("routers", "routes"),
}
SIZE_FLOOR = 0.80
# README.md is a pointer map by design (2026-09-07); its length is not a
# content signal, so it is exempt from the size floor (headings still apply).
SIZE_FLOOR_EXEMPT = ("README.md",)

# An update that rewrites most of a document is a regeneration wearing an
# update's clothes: the 2026-09-02 run replaced 394 lines with 158 and every
# gate passed on the result because each gate looked at the OUTPUT, not at the
# transition. Churn is removed_lines / previous_lines, so a doc that keeps its
# length while replacing every line reads as 1.0 here and 1.0 on the size
# floor's scale reads as "fine". Anything above this ceiling stops the run and
# the report says which sections moved.
CHURN_CEILING = 0.50
# Documents that are wholly rendered from the inventory legitimately churn
# hard when the fleet changes, so they carry a higher ceiling.
# Two documents are legitimately re-derived in full every month rather than
# edited in place, so a high churn there is normal and a 50% ceiling would
# block the refresh for doing its job:
#   docs/API.md      — every line comes from the router files
#   COST_ANALYSIS.md — written wholesale from the billing CSVs; when the SKU
#                      ordering shifts, most of its table rows change
# They are not unprotected: the size floor is the real guard for
# COST_ANALYSIS.md, and it catches the degradation that matters. In the
# 2026-09-02 incident it fell 163 -> 103 lines (63% of its previous size,
# under the 80% floor) and would have been stopped on that alone.
CHURN_CEILING_RENDERED = {"docs/API.md": 0.90, "COST_ANALYSIS.md": 0.85}
DIFF_DOCS = DOCS + ("docs/API.md",)
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
# Every in-repo target .github/prompts/readme.md mandates a row for. Three
# were missing (GCP_IMPLEMENTATION_GUIDE, docs/audits/, cloudbuild/README):
# dropping those rows left no dead link, kept the headings, and README is
# exempt from the size floor, so a shortened map passed every gate.
# (Codex, PR #1009.) The solyra repo row is an external URL, not a path.
README_REQUIRED_LINKS = (
    "ARCHITECTURE.md", "DATA_DEPENDENCIES.md", "COST_ANALYSIS.md", "RUNBOOK.md",
    "ERD.md", "docs/PIPELINE.md", "docs/DATA_PIPELINE.md", "docs/API.md",
    "docs/GCP_IMPLEMENTATION_GUIDE.md", "docs/product/README.md", "docs/audits/",
    "gcp/cloudbuild/README.md", "CLAUDE.md", "SETUP.md",
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
            # Counted, not tested for membership: insert_blocks rewrites the
            # FIRST match only (count=1), so a duplicated block keeps its
            # second copy verbatim through the fresh-render comparison, and
            # the added lines never trip a removal-based churn ceiling. A
            # doubled job or route table would publish. (Codex, PR #1009)
            ns = text.count(inv.MARKER_START.format(name=name))
            ne = text.count(inv.MARKER_END.format(name=name))
            if ns != ne:
                out.append(f"{doc}: unbalanced markers for inventory:{name} ({ns} start, {ne} end)")
            elif ns > 1:
                out.append(f"{doc}: inventory:{name} appears {ns} times — a block must occur exactly once")
        for name in EXPECTED_MARKERS.get(doc, ()):
            if inv.MARKER_START.format(name=name) not in text:
                out.append(f"{doc}: inventory:{name} block is missing entirely (both markers deleted)")
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


def diff_stats(root: pathlib.Path, previous_dir: pathlib.Path | None) -> list[dict]:
    """Per-document added/removed accounting for this run.

    Byte and line counts on both sides plus the headings and marker blocks
    that appeared or vanished, so a reviewer can see WHAT the run did rather
    than only whether the result passed. Feeds both the budget gate below and
    the run's markdown report.
    """
    import difflib

    out: list[dict] = []
    if previous_dir is None:
        return out
    for doc in DIFF_DOCS:
        prev, cur = previous_dir / doc, root / doc
        if not prev.exists() or not cur.exists():
            continue
        old_text, new_text = prev.read_text(), cur.read_text()
        old_lines, new_lines = old_text.splitlines(), new_text.splitlines()
        added = removed = 0
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
                None, old_lines, new_lines, autojunk=False).get_opcodes():
            if tag in ("replace", "delete"):
                removed += i2 - i1
            if tag in ("replace", "insert"):
                added += j2 - j1
        old_heads, new_heads = set(_headings(old_text)), set(_headings(new_text))
        old_marks = set(re.findall(r"<!-- inventory:([a-z]+):start -->", old_text))
        new_marks = set(re.findall(r"<!-- inventory:([a-z]+):start -->", new_text))
        out.append({
            "doc": doc,
            "lines_before": len(old_lines), "lines_after": len(new_lines),
            "bytes_before": len(old_text.encode()), "bytes_after": len(new_text.encode()),
            "added": added, "removed": removed,
            "churn": (removed / len(old_lines)) if old_lines else 0.0,
            "headings_removed": sorted(old_heads - new_heads),
            "headings_added": sorted(new_heads - old_heads),
            "blocks_removed": sorted(old_marks - new_marks),
            "blocks_added": sorted(new_marks - old_marks),
        })
    return out


def gate_diff_budget(stats: list[dict], allow_rewrite: tuple[str, ...] = ()) -> list[str]:
    """Refuse a run that rewrote a document instead of updating it.

    `allow_rewrite` names documents a HUMAN is deliberately reconstructing.
    The refresh workflow never passes it, so the monthly bot can never exempt
    itself; it exists for a one-off rebuild done under review.
    """
    out = []
    for st in stats:
        ceiling = CHURN_CEILING_RENDERED.get(st["doc"], CHURN_CEILING)
        if st["doc"] in allow_rewrite:
            continue
        if st["churn"] > ceiling:
            out.append(
                f"{st['doc']}: {st['removed']} of {st['lines_before']} previous lines were replaced "
                f"or deleted ({st['churn']:.0%} churn, ceiling {ceiling:.0%}) — this is a rewrite, "
                f"not an in-place update"
            )
        if st["blocks_removed"]:
            out.append(f"{st['doc']}: inventory block(s) disappeared since the previous version: "
                       + ", ".join(st["blocks_removed"]))
    return out


def render_report(stats: list[dict]) -> str:
    """Markdown accounting of what this run added and removed."""
    if not stats:
        return "_no previous versions supplied — nothing to diff_\n"
    rows = ["| Document | Lines | Bytes | +added | -removed | Churn |",
            "|---|---|---|---|---|---|"]
    for st in stats:
        dl = st["lines_after"] - st["lines_before"]
        db = st["bytes_after"] - st["bytes_before"]
        rows.append(
            f"| `{st['doc']}` | {st['lines_before']} → {st['lines_after']} ({dl:+d}) "
            f"| {st['bytes_before']:,} → {st['bytes_after']:,} ({db:+,d}) "
            f"| {st['added']} | {st['removed']} | {st['churn']:.0%} |")
    body = ["## What this run changed", "", *rows, ""]
    for st in stats:
        notes = []
        if st["headings_removed"]:
            notes.append("removed headings: " + ", ".join(f"`{h}`" for h in st["headings_removed"]))
        if st["headings_added"]:
            notes.append("new headings: " + ", ".join(f"`{h}`" for h in st["headings_added"]))
        if st["blocks_added"]:
            notes.append("new inventory blocks: " + ", ".join(st["blocks_added"]))
        if notes:
            body.append(f"**`{st['doc']}`** — " + "; ".join(notes))
    return "\n".join(body) + "\n"


def gate_derived_numbers(root: pathlib.Path, repo: dict, live: dict | None) -> list[str]:
    """Prose figures that are DERIVED from the inventory must match it.

    Three review rounds each corrected one instance of the same wrong number
    and left another standing, because the corrections were made by reading
    rather than by deriving: §9 said 41/25/1 retries while §6 still said 56/27
    (a total of 83 against 67 declared jobs), and §5 and §17 said 26 runtime
    relations while §15 still said 28. Both are computable, so neither should
    ever have been a prose claim a human had to keep in sync. (Codex, #1009.)
    """
    import collections
    out = []
    text = (root / "ARCHITECTURE.md").read_text()

    counts = collections.Counter(j.get("max_retries") for j in repo["jobs"])
    # Both clause orders. The first version required the flag to precede the
    # count, so "56 jobs use `--max-retries 0`" -- a phrasing no prompt forbids
    # -- would have sailed past the gate that exists to catch exactly that
    # number. (Codex, PR #1009.)
    claims: list[tuple[str, str]] = []
    # flag first: "`--max-retries 0` for 41 ...", "`--max-retries 0` is the norm (41 of ..."
    claims += [(m.group(1), m.group(2)) for m in
               re.finditer(r"`--max-retries (\d)`\s*(?:is the norm\s*\(|for\s+)(\d+)", text)]
    # count first: "the 25 `--max-retries 1` jobs", "56 jobs use `--max-retries 0`"
    claims += [(m.group(2), m.group(1)) for m in
               re.finditer(r"\b(\d+)\s+`--max-retries (\d)`", text)]
    claims += [(m.group(2), m.group(1)) for m in
               re.finditer(r"\b(\d+)\s+jobs?\s+(?:use|have|are at|run with)\s+`--max-retries (\d)`", text)]
    # the trailing shorthand of a list: "... `1` for 25 and `2` for one"
    for m in re.finditer(r"`--max-retries \d`[^.\n]*", text):
        for m2 in re.finditer(r"`(\d)`\s+for\s+(\d+)", m.group(0)):
            claims.append((m2.group(1), m2.group(2)))
    for flag, claimed in claims:
        want = counts.get(flag, 0)
        if int(claimed) != want:
            out.append(f"ARCHITECTURE.md: claims {claimed} jobs at --max-retries {flag}; "
                       f"gcp/deploy.sh declares {want}")

    if live and live.get("db_tables"):
        # A SET difference, not a subtraction of totals: a relation declared in
        # schema.sql but not yet migrated live would make the subtraction
        # undercount, rejecting correct prose and accepting a wrong number.
        # (Codex, PR #1009.)
        declared_names = ({t_["name"] for t_ in repo["tables"]}
                          | {v["name"] for v in repo["materialized_views"]}
                          | {v["name"] for v in repo["views"]})
        declared = len(declared_names)
        runtime = len(set(live["db_tables"]) - declared_names)
        for doc in ("ARCHITECTURE.md", "DATA_DEPENDENCIES.md"):
            body = (root / doc).read_text()
            for m in re.finditer(r"(\d+) runtime[- ](?:created )?relations", body):
                if int(m.group(1)) != runtime:
                    out.append(f"{doc}: claims {m.group(1)} runtime relations; "
                               f"{len(live['db_tables'])} live minus {declared} declared is {runtime}")
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
        transcripts_dir: pathlib.Path | None, allow_rewrite: tuple[str, ...] = ()) -> list[str]:
    repo = inv.repo_inventory(root)
    live = json.loads(snapshot.read_text()) if snapshot else None
    findings: list[str] = []
    findings += gate_coverage(root, repo, live)
    findings += gate_subsections(root, repo)
    findings += gate_markers(root, repo, live)
    findings += gate_diff_budget(diff_stats(root, previous_dir), allow_rewrite)
    findings += gate_headings_and_size(root, previous_dir)
    findings += gate_derived_numbers(root, repo, live)
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
    ap.add_argument("--report", help="write the added/removed accounting here as markdown")
    ap.add_argument("--allow-rewrite", action="append", default=[], metavar="DOC",
                    help="a document a human is deliberately reconstructing; exempt it from the "
                         "churn ceiling. The refresh workflow never passes this.")
    a = ap.parse_args(argv)
    root = pathlib.Path(a.root)
    previous_dir = pathlib.Path(a.previous_dir) if a.previous_dir else None
    findings = run(root, pathlib.Path(a.snapshot) if a.snapshot else None, previous_dir,
                   pathlib.Path(a.transcripts_dir) if a.transcripts_dir else None,
                   tuple(a.allow_rewrite))
    # The accounting is written whether or not the gates passed: on a failure
    # it is the first thing a reviewer needs.
    report = render_report(diff_stats(root, previous_dir))
    if a.report:
        pathlib.Path(a.report).write_text(report)
    print(report)
    for f in findings:
        _err(f)
    print(f"check_generated_docs: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
