#!/usr/bin/env python3
"""Export the model registry tables to docs/product/generated/model-registry.json.

Machine-owned (DOC_REGISTRY class A). Regenerate whenever
docs/product/07-MODEL-REGISTRY.md or docs/EXPERIMENT_REGISTRY.md changes:

    python3 scripts/gate/export_model_registry.py            # write the JSON
    python3 scripts/gate/export_model_registry.py --check    # exit 1 if the committed JSON is stale

The refresh-canvas skill reads this file from main and merges it into the
"Stocks models diagram" canvas field by field. Nothing here is re-measured;
it is a parse of the markdown tables, with markdown links reduced to text
and issue/PR numbers extracted.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs" / "product" / "07-MODEL-REGISTRY.md"
EXPERIMENTS = ROOT / "docs" / "EXPERIMENT_REGISTRY.md"
OUT = ROOT / "docs" / "product" / "generated" / "model-registry.json"

LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
ISSUE = re.compile(r"#(\d{2,5})")
CODE = re.compile(r"`([^`]+)`")


def sh(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=ROOT).stdout.strip()


def clean(cell: str) -> str:
    cell = LINK.sub(r"\1", cell)
    cell = cell.replace("**", "").replace("~~", "")
    return re.sub(r"\s+", " ", cell).strip()


def split_row(line: str) -> list[str]:
    # split on unescaped pipes
    parts = re.split(r"(?<!\\)\|", line.strip())
    return [p.replace("\\|", "|").strip() for p in parts[1:-1]]


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


def build() -> dict:
    text = REGISTRY.read_text(encoding="utf-8", errors="replace")
    out: dict = {
        "generated_from": [str(REGISTRY.relative_to(ROOT)), str(EXPERIMENTS.relative_to(ROOT))],
        "source_sha": sh("git rev-parse --short HEAD"),
        "source_branch": sh("git rev-parse --abbrev-ref HEAD"),
        "registry_last_reviewed": (re.search(r"Last reviewed:\*\*\s*([0-9-]+|unknown)", text) or [None, None])[1],
        "models": {},
        "experiment_traceability": {},
        "findings": [],
        "dispositions": {},
        "schedulers": [],
        "excluded_schedulers": [],
        "tables": [],
    }
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
                tier = heading[-1] if heading else ""
                rec["tier"] = tier
                out["models"][first] = rec
            elif first.startswith("MODEL-") and h0 == "model":
                out["experiment_traceability"][first] = rec
            elif first.startswith("DOC-") and h0 == "id" and "concern" in " ".join(header).lower() or (
                first.startswith("DOC-") and "claim" in " ".join(header).lower()
            ):
                rec["id"] = first
                out["findings"].append(rec)
            elif first.startswith("DOC-") and "disposition" in " ".join(header).lower():
                out["dispositions"][first] = rec
            elif h0 == "scheduler" and "serves" in " ".join(header).lower():
                rec["models"] = sorted(set(re.findall(r"MODEL-[A-Z0-9-]+", clean(raw[-1]))))
                out["schedulers"].append(rec)
            elif h0 == "scheduler":
                out["excluded_schedulers"].append(rec)
    if EXPERIMENTS.exists():
        etext = EXPERIMENTS.read_text(encoding="utf-8", errors="replace")
        out["experiment_ids"] = sorted(set(re.findall(r"\bE-\d{2}\b", etext)))
    return out


def main(argv: list[str]) -> int:
    data = build()
    payload = json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    if "--check" in argv:
        if not OUT.exists():
            print(f"missing {OUT.relative_to(ROOT)}; run export_model_registry.py")
            return 1
        current = json.loads(OUT.read_text(encoding="utf-8"))
        fresh = json.loads(payload)
        for k in ("source_sha", "source_branch"):
            current.pop(k, None); fresh.pop(k, None)
        if current != fresh:
            print(f"{OUT.relative_to(ROOT)} is stale; run export_model_registry.py and commit")
            return 1
        print("model-registry.json is current")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(payload, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(data['models'])} models, "
          f"{len(data['experiment_traceability'])} traceability rows, {len(data['findings'])} findings, "
          f"{len(data['dispositions'])} dispositions, {len(data['schedulers'])} schedulers")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
