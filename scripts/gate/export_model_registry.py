#!/usr/bin/env python3
"""Export the model registry tables to docs/product/generated/model-registry.json.

Machine-owned (DOC_REGISTRY class A). Regenerate whenever
docs/product/07-MODEL-REGISTRY.md or docs/EXPERIMENT_REGISTRY.md changes:

    python3 scripts/gate/export_model_registry.py                     # write the JSON
    python3 scripts/gate/export_model_registry.py --check             # exit 1 if the committed JSON is stale
    python3 scripts/gate/export_model_registry.py --check --rev SHA   # the same, read from a commit (CI)
    python3 scripts/gate/export_model_registry.py --check --rev SHA --base SHA  # stale only if this PR did it

The refresh-canvas skill reads this file from main and merges it into the
"Stocks models diagram" canvas field by field. Nothing here is re-measured;
it is a parse of the markdown tables, with markdown links reduced to text
and issue/PR numbers extracted.

Provenance is `sources`: the git blob id of each source document, which is
the same on every commit that carries that content. --check compares it too,
so a JSON exported from different source text is stale even when the parsed
tables happen to match.

A PR head contains main, so one registry edit that reaches main without its
JSON would fail every later PR. With --base, a stale head fails only when the
PR itself touches a source or the JSON, or when the base was fresh and the
head made it stale (a merge of a stale main it carries); otherwise the notice
names main and the check passes.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
REGISTRY = "docs/product/07-MODEL-REGISTRY.md"
EXPERIMENTS = "docs/EXPERIMENT_REGISTRY.md"
OUT = "docs/product/generated/model-registry.json"

LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
ISSUE = re.compile(r"#(\d{2,5})")
CODE = re.compile(r"`([^`]+)`")
DOC_ID = re.compile(r"DOC-(\d+)")
DOC_RANGE = re.compile(r"DOC-(\d+)\s*(?:…|\.\.\.?|–|—|\bto\b)\s*DOC-(\d+)")
EXP_ID = re.compile(r"\bE-(\d{2})\b")
EXP_RANGE = re.compile(r"\bE-(\d{2})\s*(?:…|\.\.\.?|–|—|\bto\b)\s*E-(\d{2})\b")

# Every model card reads these keys. A tier whose table has no column for one
# gets an explicit null: "the registry does not say", never a missing key.
CANONICAL = ("name", "type", "decision_produced", "code_paths", "status", "rec", "doc", "blocking_issues")
ALIASES = {"code_artifact": "code", "code_artifact_paths": "code_paths"}


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=ROOT)


class Source:
    """Reads the registry documents from the working tree, or from one commit."""

    def __init__(self, rev: str | None = None):
        self.rev = rev

    def read(self, path: str) -> str | None:
        if self.rev is None:
            p = ROOT / path
            return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
        r = git("show", f"{self.rev}:{path}")
        return r.stdout if r.returncode == 0 else None

    def blob(self, path: str) -> str | None:
        if self.rev is None:
            r = git("hash-object", "--", path)
        else:
            r = git("rev-parse", f"{self.rev}:{path}")
        return r.stdout.strip() if r.returncode == 0 else None


def clean(cell: str) -> str:
    cell = LINK.sub(r"\1", cell)
    cell = cell.replace("**", "").replace("~~", "")
    return re.sub(r"\s+", " ", cell).strip()


def split_row(line: str) -> list[str]:
    # split on unescaped pipes
    parts = re.split(r"(?<!\\)\|", line.strip())
    return [p.replace("\\|", "|").strip() for p in parts[1:-1]]


def expand_ids(cell: str, id_re: re.Pattern, range_re: re.Pattern, fmt: str,
               drop_parentheticals: bool = False) -> list[str]:
    """Every ID a cell names: ranges (`DOC-01…DOC-05`) expanded, lists split, and,
    where asked, parenthetical decorations such as `(#1118)` dropped."""
    text = clean(cell)
    ids: list[str] = []
    for a, b in range_re.findall(text):
        ids += [fmt.format(n) for n in range(int(a), int(b) + 1)]
    text = range_re.sub(" ", text)
    if drop_parentheticals:
        text = re.sub(r"\([^)]*\)", " ", text)
    ids += [fmt.format(int(n)) for n in id_re.findall(text)]
    return list(dict.fromkeys(ids))


def doc_ids(cell: str) -> list[str]:
    return expand_ids(cell, DOC_ID, DOC_RANGE, "DOC-{:02d}", drop_parentheticals=True)


def tables_with_headings(text: str):
    """Yield (heading_path, header_cells, rows) for every markdown table."""
    heading: list[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        hm = re.match(r"^(#{1,6})\s+(.*)$", line)
        if hm:
            level = len(hm.group(1))
            heading = heading[: level - 1] + [clean(hm.group(2))]
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            header = [clean(c) for c in split_row(line)]
            rows = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            yield list(heading), header, rows
            continue
        i += 1


def row_to_record(header: list[str], raw: list[str]) -> dict:
    rec: dict = {}
    for h, cell in zip(header, raw):
        key = re.sub(r"[^a-z0-9]+", "_", h.lower()).strip("_") or "col"
        rec[key] = clean(cell)
        if key in ("code", "code_artifact", "primary_code"):
            rec[key + "_paths"] = CODE.findall(cell)
        if key in ("blocking_issues", "evidence", "recorded_verdict", "note"):
            rec.setdefault("issue_numbers", [])
            rec["issue_numbers"] = sorted({int(n) for n in ISSUE.findall(cell)})
    return rec


def canonical(rec: dict) -> dict:
    for src, dst in ALIASES.items():
        if src in rec and dst not in rec:
            rec[dst] = rec[src]
    for key in CANONICAL:
        rec.setdefault(key, None)
    return rec


def experiment_ids(text: str) -> list[str]:
    """IDs from experiment headings only: prose such as "Next free ID is E-36" is not an experiment."""
    ids: set[str] = set()
    for line in text.splitlines():
        if re.match(r"^#{1,6}\s", line):
            ids.update(expand_ids(line, EXP_ID, EXP_RANGE, "E-{:02d}"))
    return sorted(ids)


LLM_GROUP = re.compile(r"\bLLM nodes\b")


def resolve_scheduler_models(schedulers: list[dict], models: dict) -> None:
    """Fill `models` for a scheduler whose Serves cell names no MODEL-* id.

    Two forms are expanded, both deterministic: a phrase naming the LLM node
    group ("all 14 LLM nodes", "the LLM nodes' delivery half") becomes every
    id in the `LLM nodes` tier, and a row that runs another row's Job (the
    Sunday refresh of a job whose weekday row lists its models, whether or not
    it says "the same job") inherits the ids those rows name literally. Any
    other prose is not guessed at: `models` stays empty and `models_note`
    carries the Serves text, so the canvas shows the gap instead of hiding it.
    """
    llm_ids = sorted(mid for mid, rec in models.items() if rec.get("tier") == "LLM nodes")
    by_job: dict[str, set[str]] = {}
    for rec in schedulers:
        if rec["models"]:
            by_job.setdefault(rec.get("job", ""), set()).update(rec["models"])
    for rec in schedulers:
        if rec["models"]:
            continue
        if LLM_GROUP.search(rec.get("serves", "")):
            rec["models"] = llm_ids
        elif by_job.get(rec.get("job", "")):
            rec["models"] = sorted(by_job[rec["job"]])
        else:
            rec["models_note"] = f"no registered model named in Serves: {rec.get('serves', '')}"


def build(src: Source) -> dict:
    text = src.read(REGISTRY)
    if text is None:
        raise SystemExit(f"{REGISTRY} not found")
    out: dict = {
        "generated_from": [REGISTRY, EXPERIMENTS],
        "sources": {path: src.blob(path) for path in (REGISTRY, EXPERIMENTS)},
        "registry_last_reviewed": (re.search(r"Last reviewed:\*\*\s*([0-9-]+|unknown)", text) or [None, None])[1],
        "models": {},
        "experiment_traceability": {},
        "findings": [],
        "dispositions": {},
        "schedulers": [],
        "excluded_schedulers": [],
        "tables": [],
    }
    grouped: dict = {}
    for heading, header, rows in tables_with_headings(text):
        h0 = header[0].lower() if header else ""
        section = " / ".join(heading)
        out["tables"].append({"section": section, "columns": header, "rows": len(rows)})
        for raw in rows:
            if not raw:
                continue
            rec = row_to_record(header, raw)
            first = clean(raw[0])
            if first.startswith("MODEL-") and h0 == "id":
                rec["tier"] = heading[-1] if heading else ""
                out["models"][first] = canonical(rec)
            elif first.startswith("MODEL-") and h0 == "model":
                out["experiment_traceability"][first] = rec
            elif first.startswith("DOC-") and h0 == "id" and "concern" in " ".join(header).lower() or (
                first.startswith("DOC-") and "claim" in " ".join(header).lower()
            ):
                ids = doc_ids(raw[0])
                rec["id"] = ids[0] if ids else first
                rec["label"] = first
                out["findings"].append(rec)
            elif first.startswith("DOC-") and "disposition" in " ".join(header).lower():
                ids = doc_ids(raw[0])
                rec["label"] = first
                # A row naming one finding wins over a row that names it in a group.
                target = out["dispositions"] if len(ids) == 1 else grouped
                for fid in ids:
                    target.setdefault(fid, rec)
            elif h0 == "scheduler" and "serves" in " ".join(header).lower():
                rec["models"] = sorted(set(re.findall(r"MODEL-[A-Z0-9-]+", clean(raw[-1]))))
                out["schedulers"].append(rec)
            elif h0 == "scheduler":
                out["excluded_schedulers"].append(rec)
    for fid, rec in grouped.items():
        out["dispositions"].setdefault(fid, rec)
    resolve_scheduler_models(out["schedulers"], out["models"])
    etext = src.read(EXPERIMENTS)
    if etext is not None:
        out["experiment_ids"] = experiment_ids(etext)
    return out


def fresh_at(rev: str) -> bool:
    """Whether the JSON at `rev` was exported from the sources at `rev`: its recorded blob ids match theirs."""
    src = Source(rev)
    committed = src.read(OUT)
    if committed is None:
        return False
    return json.loads(committed).get("sources") == {path: src.blob(path) for path in (REGISTRY, EXPERIMENTS)}


def touched_since(base: str, rev: str) -> list[str]:
    """The registry sources and the JSON that `rev` changed since it forked from `base` (the PR's own edits)."""
    r = git("diff", "--name-only", f"{base}...{rev}", "--", REGISTRY, EXPERIMENTS, OUT)
    if r.returncode != 0:
        raise SystemExit(r.stderr.strip() or f"git diff {base}...{rev} failed")
    return r.stdout.split()


def option(argv: list[str], flag: str) -> str | None:
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else None


def main(argv: list[str]) -> int:
    rev = option(argv, "--rev")
    if "--rev" in argv and rev is None:
        print("--rev needs a commit")
        return 2
    base = option(argv, "--base")
    if "--base" in argv and (base is None or rev is None or "--check" not in argv):
        print("--base needs a commit, and --check --rev")
        return 2
    src = Source(rev)
    data = build(src)
    payload = json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    if "--check" in argv:
        committed = src.read(OUT)
        if committed is None:
            print(f"missing {OUT}; run export_model_registry.py")
            return 1
        if json.loads(committed) != json.loads(payload):
            if base is not None and not touched_since(base, rev) and not fresh_at(base):
                print(f"{OUT} is already stale on the base branch (main at {base[:12]}), not in this PR; "
                      f"whoever last edited {REGISTRY} or {EXPERIMENTS} on main should regenerate it there: "
                      "run export_model_registry.py and commit the JSON")
                return 0
            print(f"{OUT} is stale; run export_model_registry.py and commit")
            return 1
        print("model-registry.json is current")
        return 0
    if rev is not None:
        print("--rev is read-only; use it with --check")
        return 2
    out = ROOT / OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload, encoding="utf-8")
    print(f"wrote {OUT}: {len(data['models'])} models, "
          f"{len(data['experiment_traceability'])} traceability rows, {len(data['findings'])} findings, "
          f"{len(data['dispositions'])} dispositions, {len(data['schedulers'])} schedulers")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
