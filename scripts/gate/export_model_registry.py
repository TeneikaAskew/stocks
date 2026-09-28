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
tables happen to match. Both documents are canonical inputs: if either is
missing at the rev being read, generation and --check fail naming the path,
so the JSON never carries a null source blob (CLAUDE.md §3.7).

A PR head contains main, so one registry edit that reaches main without its
JSON would fail every later PR. With --base, a stale head fails only when the
PR itself touches a source or the JSON, or when the base was fresh and the
head made it stale (a merge of a stale main it carries); otherwise the notice
names main and the check passes.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
REGISTRY = "docs/product/07-MODEL-REGISTRY.md"
EXPERIMENTS = "docs/EXPERIMENT_REGISTRY.md"
OUT = "docs/product/generated/model-registry.json"
SELF = "scripts/gate/export_model_registry.py"

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

    def require(self, path: str) -> str:
        """The document's text; a canonical source that is missing fails the run rather than exporting a null blob."""
        text = self.read(path)
        if text is None:
            where = f"at {self.rev}" if self.rev is not None else "in the working tree"
            raise SystemExit(f"{path} not found {where}; both registry sources must exist to export or check")
        return text

    def blob(self, path: str) -> str | None:
        if self.rev is None:
            r = git("hash-object", "--", path)
        else:
            r = git("rev-parse", f"{self.rev}:{path}")
        return r.stdout.strip() if r.returncode == 0 else None


# The tiers the registry is organized in (its `## ` sections holding model tables); each keeps
# at least one row, so a table deleted whole is refused rather than exported as an empty tier.
MODEL_TIERS = ("Deterministic and heuristic systems", "Learned models", "LLM nodes")


def clean(cell: str) -> str:
    # An HTML comment is audit markup, not content: canvases.yml maps cells straight
    # onto card text, so a hidden directive would be published on a card.
    cell = re.sub(r"<!--.*?-->", "", cell, flags=re.S)
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


def rendered(text: str) -> str:
    """The document as it renders: HTML comments and fenced code removed, so a table
    retired inside either is not exported and published on a card."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<!--.*\Z", "", text, flags=re.S)
    text = re.sub(r"^[ \t]*(`{3,}).*?^[ \t]*\1`*[ \t]*$", "", text, flags=re.S | re.M)
    text = re.sub(r"^[ \t]*(~{3,}).*?^[ \t]*\1~*[ \t]*$", "", text, flags=re.S | re.M)
    return re.sub(r"^[ \t]*(`{3,}|~{3,}).*\Z", "", text, flags=re.S | re.M)


def last_reviewed(text: str) -> str:
    """The visible `**Last reviewed:**` stamp, a calendar date or `unknown`: read from the
    rendered text so a commented-out earlier stamp cannot supply it (stocks#1205 r4120381528)."""
    m = re.search(r"\*\*Last reviewed:\*\*\s*(\S+)", rendered(text))
    value = m.group(1) if m else None
    if value != "unknown":
        try:
            datetime.date.fromisoformat(value or "")
        except ValueError:
            raise SystemExit(f"{REGISTRY}: the visible **Last reviewed:** stamp reads {value!r}; it is a YYYY-MM-DD date or `unknown`")
    return value


REQUIRED_KEYS = {
    # the fields canvases.yml routes onto a card: a dropped column would leave every record
    # without the path the refresh writes (stocks#1205 r4120381495)
    "finding": ("id", "doc", "kind", "sev", "models"),
    "disposition": ("id", "disposition", "why"),
    "traceability": ("model", "experiments", "primary_code", "deep_doc", "recorded_verdict"),
}


def tables_with_headings(text: str):
    """Yield (heading_path, header_cells, rows) for every markdown table that renders."""
    heading: list[str] = []
    lines = rendered(text).splitlines()
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


def header_keys(header: list[str]) -> list[str]:
    return [re.sub(r"[^a-z0-9]+", "_", h.lower()).strip("_") or "col" for h in header]


def duplicate_keys(header: list[str]) -> list[str]:
    """Header cells that normalize to a key another cell already took: the later cell would
    silently overwrite the earlier field (stocks#1205 r4119966296)."""
    keys = header_keys(header)
    return sorted({k for k in keys if keys.count(k) > 1})


def row_to_record(header: list[str], raw: list[str]) -> dict:
    rec: dict = {}
    for key, cell in zip(header_keys(header), raw):
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
    for line in rendered(text).splitlines():   # a heading inside a fence is an example, not an entry (r4120660287)
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
    text = src.require(REGISTRY)
    etext = src.require(EXPERIMENTS)
    out: dict = {
        "generated_from": [REGISTRY, EXPERIMENTS],
        # The exporter is a source too: a changed exporter is a changed output, so a base
        # that changed it without regenerating reads stale rather than fresh.
        "sources": {path: src.blob(path) for path in (REGISTRY, EXPERIMENTS, SELF)},
        "registry_last_reviewed": last_reviewed(text),
        "models": {},
        "experiment_traceability": {},
        "findings": [],
        "dispositions": {},
        "schedulers": [],
        "excluded_schedulers": [],
        "tables": [],
    }
    grouped: dict = {}
    unrouted: list[str] = []   # MODEL-/DOC- rows no table shape claimed: a malformed registry
    malformed: list[str] = []  # rows narrower or wider than their header, duplicate model IDs
    for heading, header, rows in tables_with_headings(text):
        h0 = header[0].lower() if header else ""
        section = " / ".join(heading)
        out["tables"].append({"section": section, "columns": header, "rows": len(rows)})
        for raw in rows:
            if not raw:
                continue
            first = clean(raw[0])
            # Width is checked on the rows that route (models, findings, dispositions,
            # schedulers): a prose table elsewhere in the document is not a record.
            routable = first.startswith(("MODEL-", "DOC-")) or h0 == "scheduler"
            if routable and len(raw) != len(header):
                malformed.append(f"{first} under '{section}' has {len(raw)} cell(s), header has {len(header)}")
                continue
            if routable and (dup := duplicate_keys(header)):
                malformed.append(f"table under '{section}' has two columns keyed {dup[0]}; one cell would overwrite the other")
                continue
            rec = row_to_record(header, raw)
            kind = ("traceability" if first.startswith("MODEL-") and h0 == "model"
                    else "finding" if first.startswith("DOC-") and ("concern" in " ".join(header).lower() or "claim" in " ".join(header).lower())
                    else "disposition" if first.startswith("DOC-") and "disposition" in " ".join(header).lower() else None)
            if kind and (missing := [k for k in REQUIRED_KEYS[kind] if k not in header_keys(header)]):
                malformed.append(f"the {kind} table under '{section}' lacks the {', '.join(missing)} column(s) the cards route")
                continue
            if first.startswith("MODEL-") and h0 == "id":
                if first in out["models"]:
                    malformed.append(f"{first} appears twice (second under '{section}')")
                    continue
                rec["tier"] = heading[-1] if heading else ""
                out["models"][first] = canonical(rec)
            elif first.startswith("MODEL-") and h0 == "model":
                if first in out["experiment_traceability"]:
                    malformed.append(f"{first} has two experiment-traceability rows (second under '{section}')")
                    continue
                out["experiment_traceability"][first] = rec
            elif first.startswith("DOC-") and h0 == "id" and "concern" in " ".join(header).lower() or (
                first.startswith("DOC-") and "claim" in " ".join(header).lower()
            ):
                ids = doc_ids(raw[0])
                if len(ids) != 1:
                    # stocks#1205 r4120913740: a cell naming two concerns is two rows, not one
                    # card that drops the second; only disposition rows group findings
                    malformed.append(f"finding row {first!r} under '{section}' names {len(ids)} IDs; one finding per row")
                    continue
                rec["id"] = ids[0]
                rec["label"] = first
                out["findings"].append(rec)
            elif first.startswith("DOC-") and "disposition" in " ".join(header).lower():
                ids = doc_ids(raw[0])
                rec["label"] = first
                # A row naming one finding wins over a row that names it in a group.
                if len(ids) == 1 and ids[0] in out["dispositions"]:
                    # stocks#1205 r4119966278: two verdicts for one finding is a conflict, not a
                    # fallback; only a grouped row yields to a specific one
                    malformed.append(f"{ids[0]} has two disposition rows (second under '{section}')")
                    continue
                if len(ids) > 1 and (shared := sorted(set(ids) & set(grouped))):
                    # stocks#1205 r4120381475: two grouped rows naming one finding is the same conflict
                    malformed.append(f"{shared[0]} is named by two grouped disposition rows (second under '{section}')")
                    continue
                target = out["dispositions"] if len(ids) == 1 else grouped
                for fid in ids:
                    target.setdefault(fid, rec)
            elif h0 == "scheduler" and "serves" in " ".join(header).lower():
                # From the Serves column itself, not the last cell: a column added after it
                # would otherwise silently empty every scheduler's model list.
                serves = next(cell for h, cell in zip(header, raw) if "serves" in h.lower())
                rec["models"] = sorted(set(re.findall(r"MODEL-[A-Z0-9-]+", clean(serves))))
                out["schedulers"].append(rec)
            elif h0 == "scheduler":
                out["excluded_schedulers"].append(rec)
            elif first.startswith(("MODEL-", "DOC-")):
                unrouted.append(f"{first} under '{section}' (columns: {', '.join(header)})")
    for fid, rec in grouped.items():
        out["dispositions"].setdefault(fid, rec)
    seen_findings: set[str] = set()
    for rec in out["findings"]:
        # stocks#1205 r4119634446: the Concerns board is keyed by id, so two rows with one
        # ID would leave one finding overwritten on refresh while the ID-set check passed.
        if rec["id"] in seen_findings:
            malformed.append(f"finding {rec['id']} appears twice")
        seen_findings.add(rec["id"])
    ledger = set(experiment_ids(etext))
    for mid, rec in out["experiment_traceability"].items():
        # stocks#1205 r4119634454: a misspelled E-nn in a traceability row would let a card
        # claim evidence from an experiment the ledger never recorded.
        cited = set(expand_ids(clean(" ".join(str(v) for v in rec.values())), EXP_ID, EXP_RANGE, "E-{:02d}"))
        unknown_exp = sorted(cited - ledger)
        if unknown_exp:
            malformed.append(f"{mid} traceability cites experiment(s) not in the ledger: {', '.join(unknown_exp)}")
    if malformed:
        raise SystemExit(f"{REGISTRY}: {len(malformed)} malformed row(s): {'; '.join(malformed[:3])}. "
                         "A row has exactly its header's cells and a model ID names one row; fix the table "
                         "rather than exporting a shifted or overwritten record")
    finding_ids, disposition_ids = {f["id"] for f in out["findings"]}, set(out["dispositions"])
    if not finding_ids:
        # stocks#1205 r4120166753: two empty sets are equal, so a registry that lost both
        # concern tables would otherwise export an empty Concerns board as current
        raise SystemExit(f"{REGISTRY}: no finding rows parsed; the Findings and Disposition tables are part of the "
                         "registry, so their absence is a deleted table, not an empty board")
    if finding_ids != disposition_ids:
        raise SystemExit(f"{REGISTRY}: findings and dispositions name different IDs; without a disposition: "
                         f"{', '.join(sorted(finding_ids - disposition_ids)) or 'none'}; without a finding: "
                         f"{', '.join(sorted(disposition_ids - finding_ids)) or 'none'}. Every finding carries its verdict")
    tiers = {m["tier"] for m in out["models"].values()}
    missing_tiers = [t for t in MODEL_TIERS if t not in tiers]
    if missing_tiers:
        # Every tier the registry is organized in still carries models: a deleted table
        # would otherwise drop every card in it and --check would call the result current.
        raise SystemExit(f"{REGISTRY}: no model rows under {', '.join(missing_tiers)}; the registry keeps a table "
                         "for each of its tiers, so a missing one is a deleted table, not an empty tier")
    if not out["schedulers"]:
        # stocks#1205 r4119634461: a deleted model-bearing scheduler table, or a renamed
        # Serves header, would otherwise route every row to excluded_schedulers and export
        # every card without a scheduled surface, and --check would call that current.
        raise SystemExit(f"{REGISTRY}: no scheduler row routes to a model; the scheduled-surfaces table starts with "
                         "a `Scheduler` column and carries a `Serves` column. The registry is malformed; fix it "
                         "rather than exporting it")
    unknown = sorted({m for sched in out["schedulers"] for m in sched["models"] if m not in out["models"]})
    if unknown:
        raise SystemExit(f"{REGISTRY}: scheduler Serves cells name model(s) not in the registry: {', '.join(unknown)}; "
                         "a misspelled ID would silently drop the model from its scheduled surface")
    if not out["experiment_traceability"]:
        # stocks#1205 r4120660295: no rows is a deleted table; every card would lose its experiments
        raise SystemExit(f"{REGISTRY}: no experiment-traceability rows parsed; the table is part of the registry, so its "
                         "absence is a deleted table, not an empty one")
    orphans = sorted(set(out["experiment_traceability"]) - set(out["models"]))
    if orphans:
        # canvases.yml looks experiment fields up under the model's ID, so a misspelled
        # traceability key drops that card's experiment data without any other symptom.
        raise SystemExit(f"{REGISTRY}: experiment traceability names model(s) not in the registry: "
                         f"{', '.join(orphans)}; fix the ID rather than exporting an orphan row")
    if unrouted or not out["models"]:
        # A renamed `ID` header or a dropped section would otherwise export a partial or
        # empty models object, --check would call it current, and the canvas would
        # silently lose its cards. Zero recognized rows is a malformed source, not data.
        raise SystemExit(f"{REGISTRY}: {len(unrouted)} MODEL-/DOC- row(s) sit in a table shape the exporter does not "
                         f"recognize ({'; '.join(unrouted[:3])}) and {len(out['models'])} model(s) parsed; a model table "
                         "starts with an `ID` column. The registry is malformed; fix it rather than exporting it")
    resolve_scheduler_models(out["schedulers"], out["models"])
    out["experiment_ids"] = experiment_ids(etext)
    return out


def fresh_at(rev: str) -> bool:
    """Whether the JSON at `rev` was exported from the sources at `rev`: its recorded blob ids match theirs."""
    src = Source(rev)
    committed = src.read(OUT)
    if committed is None:
        return False
    return json.loads(committed).get("sources") == {path: src.blob(path) for path in (REGISTRY, EXPERIMENTS, SELF)}


def touched_since(base: str, rev: str) -> list[str]:
    """The registry sources, the JSON and this exporter that `rev` changed since it forked
    from `base` (the PR's own edits): a changed exporter is a changed output."""
    r = git("diff", "--name-only", f"{base}...{rev}", "--", REGISTRY, EXPERIMENTS, OUT, SELF)
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
