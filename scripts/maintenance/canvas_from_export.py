"""Update the backend architecture diagram's data from an architecture export.

Spec: FEAT-CICD-001 (architecture export, diagram step).

The diagram is a bundled claude.ai page. Its data lives in one JavaScript asset
(gzip + base64 inside the page's `__bundler/manifest`) that defines

    const JOBS = { fetch: [J(...), ...], compute: [...], research: [...] };
    const CRONS = [ C(name, cron, job, args?), ... ];

This tool rewrites only data the export states exactly, and reports the rest:

  applied   CRONS is rebuilt from export.schedulers (existing order kept,
            removed triggers dropped, new ones appended).
            J cards for jobs the repo no longer declares are removed.
            A stub J card is added for a declared job the page does not
            describe anywhere.
            The provenance comment above CRONS names the export's commit.
  reported  J card schedule text that disagrees with the job's triggers,
            page text that still names a removed job, services and tables
            the page does not name, and the export's live drift.

Prose (card notes, node summaries, lineage) is never rewritten: the report
lists it for a person to fix. The page's layout, template and every other
asset are carried over byte for byte.

Usage
-----
    python3 -m scripts.maintenance.canvas_from_export \
        --export export.json --canvas page.html \
        --output page.new.html --report report.md
    ... --check     # exit 1 when the page would change (no files written)

Publishing the result is a separate, approved step (refresh-canvas skill).
"""
from __future__ import annotations

import argparse
import base64
import dataclasses
import gzip
import json
import re
import sys
from typing import Any

SCHEMA = "architecture-export/1"

_MANIFEST_RE = re.compile(r'(<script type="__bundler/manifest">\s*)(.*?)(\s*</script>)', re.DOTALL)
_TEMPLATE_RE = re.compile(r'(<script type="__bundler/template">\s*)(.*?)(\s*</script>)', re.DOTALL)

_CRONS_OPEN = "const CRONS = [\n"
_JOBS_OPEN = "const JOBS = {\n"
_STAMP_RE = re.compile(r"^// Cloud Scheduler triggers as declared in gcp/deploy\.sh deploy_schedulers\(\).*$", re.MULTILINE)
_J_LINE_RE = re.compile(r"^    J\('([^'\\]+)',\s*'((?:[^'\\]|\\.)*)'", re.MULTILINE)
_C_LINE_RE = re.compile(r"^  C\('([^'\\]+)',", re.MULTILINE)
_CATEGORY_RE = re.compile(r"^  (\w+): \[$", re.MULTILINE)


class CanvasError(ValueError):
    """The page or the export is not in the shape this tool edits."""


# ─────────────────────────────────────────────────────────────────────────────
# the bundled page
# ─────────────────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class Bundle:
    html: str
    manifest: dict[str, Any]
    asset_id: str
    js: str

    @classmethod
    def parse(cls, html: str) -> Bundle:
        m = _MANIFEST_RE.search(html)
        if not m:
            raise CanvasError("no __bundler/manifest block: not a bundled page")
        manifest = json.loads(m.group(2))
        hits = []
        for uuid, entry in manifest.items():
            if "javascript" not in entry.get("mime", ""):
                continue
            text = _decode(entry)
            if _CRONS_OPEN in text and _JOBS_OPEN in text:
                hits.append((uuid, text))
        if len(hits) != 1:
            raise CanvasError(f"expected one asset defining JOBS and CRONS, found {len(hits)}")
        return cls(html=html, manifest=manifest, asset_id=hits[0][0], js=hits[0][1])

    def render(self, js: str) -> str:
        """The page with the data asset replaced and every other byte kept."""
        entry = dict(self.manifest[self.asset_id])
        raw = js.encode("utf-8")
        if entry.get("compressed"):
            raw = gzip.compress(raw, mtime=0)
        entry["data"] = base64.b64encode(raw).decode("ascii")
        manifest = dict(self.manifest)
        manifest[self.asset_id] = entry
        m = _MANIFEST_RE.search(self.html)
        body = json.dumps(manifest, separators=(",", ":"))
        return self.html[:m.start(2)] + body + self.html[m.end(2):]


def _decode(entry: dict[str, Any]) -> str:
    raw = base64.b64decode(entry["data"])
    if entry.get("compressed"):
        raw = gzip.decompress(raw)
    return raw.decode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# JS literal helpers
# ─────────────────────────────────────────────────────────────────────────────

def js_str(value: str) -> str:
    """A single-quoted JS string literal."""
    out = value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    return "'" + out + "'"


def _block(js: str, opener: str, closer: str) -> tuple[int, int]:
    start = js.find(opener)
    if start < 0:
        raise CanvasError(f"missing {opener.strip()!r}")
    body = start + len(opener)
    end = js.find(closer, body)
    if end < 0:
        raise CanvasError(f"unterminated {opener.strip()!r}")
    return body, end


# ─────────────────────────────────────────────────────────────────────────────
# the export
# ─────────────────────────────────────────────────────────────────────────────

def load_export(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise CanvasError("export is not a JSON object")
    if data.get("schema") != SCHEMA:
        raise CanvasError(f"export schema is {data.get('schema')!r}, expected {SCHEMA!r}")
    for key in ("jobs", "schedulers", "services", "tables", "sources", "drift"):
        if key not in data:
            raise CanvasError(f"export has no {key!r}")
    if not (data["sources"] or {}).get("commit"):
        raise CanvasError("export has no sources.commit")
    return data


def _declared(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("declared")]


def _trigger_detail(s: dict[str, Any]) -> str | None:
    """What the page shows beside a trigger: its args, or for a service
    target without args, the path it calls (`${service_url}/reconcile`)."""
    if s.get("args"):
        return s["args"]
    target = s.get("target") or {}
    uri = target.get("uri") or ""
    if target.get("kind") == "service" and "${service_url}" in uri:
        path = uri.split("${service_url}", 1)[1]
        return path or None
    return None


def cron_line(s: dict[str, Any]) -> str:
    target = (s.get("target") or {}).get("name") or ""
    parts = [js_str(s["name"]), js_str(s["cron"]), js_str(target)]
    detail = _trigger_detail(s)
    if detail:
        parts.append(js_str(detail))
    return "  C(" + ", ".join(parts) + "),"


def _cron_field(field: str, lo: int, hi: int) -> tuple[set[int], bool] | None:
    """Values of one cron field and whether it is a plain list of numbers.

    Handles `*`, `a-b`, `*/n`, `a-b/n`, `a/n` and comma lists. None when the
    field has any other form, so the caller can treat the times as unknown.
    """
    values: set[int] = set()
    plain = True
    for part in field.split(","):
        m = re.fullmatch(r"(\*|\d+(?:-\d+)?)(?:/(\d+))?", part)
        if not m:
            return None
        rng, step = m.group(1), m.group(2)
        if rng == "*":
            a, b = lo, hi
        elif "-" in rng:
            a, b = map(int, rng.split("-"))
        else:
            a = int(rng)
            b = hi if step else a
        n = int(step) if step else 1
        if n < 1 or a < lo or b > hi or a > b:
            return None
        if rng == "*" or "-" in rng or step:
            plain = False
        values |= set(range(a, b + 1, n))
    return values, plain


def _cron_times(cron: str) -> tuple[set[str], set[str]] | None:
    """(exact, possible) HH:MM times of a 5-field cron, or None if unknown.

    possible: every time the trigger can fire at, with wildcards, ranges and
    steps expanded, so a label time outside it is wrong.
    exact: times a label must show; only when minute and hour are plain
    numbers (a range or step has no single time a label must name).
    """
    fields = cron.split()
    if len(fields) != 5:
        return None
    minutes = _cron_field(fields[0], 0, 59)
    hours = _cron_field(fields[1], 0, 23)
    if minutes is None or hours is None:
        return None
    possible = {f"{h:02d}:{m:02d}" for h in hours[0] for m in minutes[0]}
    exact = possible if (minutes[1] and hours[1]) else set()
    return exact, possible


_LABEL_TIME_RE = re.compile(r"\b(\d{2}):(\d{2})\b")
_ON_DEMAND_RE = re.compile(r"^(on demand|one-shot)", re.IGNORECASE)


def label_disagrees(label: str, crons: list[str]) -> bool:
    """True when a card's schedule text contradicts the job's triggers.

    Generic text ("Scheduled", "After close") never disagrees. Text that says
    on demand while triggers exist does, as does text that names a time no
    trigger fires at, or omits the exact time of a single-time trigger when it
    names times at all.
    """
    if not crons:
        return False
    if _ON_DEMAND_RE.match(label.strip()):
        return True
    shown = {f"{h}:{m}" for h, m in _LABEL_TIME_RE.findall(label)}
    if not shown:
        return False
    exact, possible = set(), set()
    for c in crons:
        times = _cron_times(c)
        if times is None:
            return False  # a form this check cannot expand: unknown, not wrong
        exact |= times[0]
        possible |= times[1]
    return bool(shown - possible) or bool(exact - shown)


def _resources(job: dict[str, Any]) -> str:
    res = job.get("resources") or {}
    mem = res.get("memory") or ""
    mem = mem.replace("Gi", " GiB").replace("Mi", " MiB")
    timeout = res.get("timeout")
    bits = [mem] if mem else []
    if timeout and str(timeout).isdigit():
        secs = int(timeout)
        bits.append(f"{secs // 3600} hr" if secs % 3600 == 0 else f"{secs // 60} min")
    return " / ".join(bits)


def stub_card(job: dict[str, Any]) -> str:
    sched = "Scheduled" if job.get("schedules") else "On demand"
    res = _resources(job)
    if res:
        sched += " · " + res
    module = (job.get("module") or "").replace(".", "/")
    module = module + ".py" if module else None
    reads = " · ".join(job.get("reads") or []) or "—"
    writes = " · ".join(job.get("writes") or []) or "—"
    args = [js_str(job["name"]), js_str(sched),
            js_str("Declared in gcp/deploy.sh; not yet described on this page."),
            js_str(reads), js_str(writes),
            js_str(module) if module else "undefined",
            js_str(res or "—"), js_str("—")]
    return "    J(" + ", ".join(args) + "),"


# ─────────────────────────────────────────────────────────────────────────────
# the update
# ─────────────────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class Result:
    js: str
    crons_added: list[str]
    crons_removed: list[str]
    crons_changed: list[tuple[str, str, str]]
    cards_removed: list[str]
    cards_added: list[str]
    labels_to_check: list[tuple[str, str, list[str]]]
    stale_mentions: list[tuple[str, int]]
    services_not_named: list[str]
    tables_not_named: list[str]
    stamp: str
    stamp_old: str | None = None

    @property
    def stamp_changed(self) -> bool:
        return self.stamp_old != self.stamp

    @property
    def changed(self) -> bool:
        return bool(self.crons_added or self.crons_removed or self.crons_changed
                    or self.cards_removed or self.cards_added) or self.stamp_changed


def update(js: str, export: dict[str, Any], run_label: str | None = None) -> Result:
    export = load_export(export)
    jobs = {j["name"]: j for j in _declared(export["jobs"])}
    scheds = {s["name"]: s for s in _declared(export["schedulers"])}

    # Which jobs the page already names outside JOBS, read before any rewrite,
    # so a trigger this run adds never counts as a description of its job.
    j_body0, j_end0 = _block(js, _JOBS_OPEN, "\n};")
    named_before = js[:j_body0] + js[j_end0:]

    # CRONS ───────────────────────────────────────────────────────────────
    c_body, c_end = _block(js, _CRONS_OPEN, "];")
    old_lines = js[c_body:c_end].splitlines()
    old_order: list[str] = []
    old_text: dict[str, str] = {}
    for line in old_lines:
        if not line.strip():
            continue
        m = _C_LINE_RE.match(line)
        if not m:
            raise CanvasError(f"unexpected line in CRONS: {line[:80]!r}")
        old_order.append(m.group(1))
        old_text[m.group(1)] = line
    new_lines, changed = [], []
    for name in old_order:
        if name in scheds:
            line = cron_line(scheds[name])
            if line != old_text[name]:
                changed.append((name, old_text[name].strip(), line.strip()))
            new_lines.append(line)
    added = [n for n in scheds if n not in old_text]
    new_lines += [cron_line(scheds[n]) for n in added]
    removed = [n for n in old_order if n not in scheds]
    js = js[:c_body] + "".join(line + "\n" for line in new_lines) + js[c_end:]

    # stamp ───────────────────────────────────────────────────────────────
    commit = export["sources"]["commit"]
    stamp = ("// Cloud Scheduler triggers as declared in gcp/deploy.sh deploy_schedulers() at "
             f"main {commit[:8]}, from the architecture export"
             + (f" ({run_label})" if run_label else "") + ".")
    sm = _STAMP_RE.search(js)
    stamp_old = sm.group(0) if sm else None
    if sm:
        js = js[:sm.start()] + stamp + js[sm.end():]
    else:
        c_at = js.find(_CRONS_OPEN)
        js = js[:c_at] + stamp + "\n" + js[c_at:]

    # JOBS ────────────────────────────────────────────────────────────────
    j_body, j_end = _block(js, _JOBS_OPEN, "\n};")
    block = js[j_body:j_end]
    cards: dict[str, str] = {}
    kept_lines, cards_removed = [], []
    for line in block.split("\n"):
        if line.lstrip().startswith("J(") and not (line.startswith("    J(") and line.rstrip().endswith("),")):
            raise CanvasError(f"job card not on one line, which this tool cannot edit safely: {line.strip()[:80]!r}")
        m = _J_LINE_RE.match(line)
        if m:
            cards[m.group(1)] = m.group(2)
            if m.group(1) not in jobs:
                cards_removed.append(m.group(1))
                continue
        kept_lines.append(line)
    block = "\n".join(kept_lines)

    missing = [n for n in jobs if n not in cards and f"'{n}'" not in named_before]
    cards_added = []
    if missing:
        cats = {m.group(1): m.end() for m in _CATEGORY_RE.finditer(block)}
        for name in missing:
            cat = "fetch" if jobs[name].get("kind") == "fetcher" else "compute"
            if cat not in cats:
                raise CanvasError(f"JOBS has no {cat!r} group for new job {name!r}")
            close = block.find("\n  ],", cats[cat])
            if close < 0:
                raise CanvasError(f"JOBS group {cat!r} is not closed")
            block = block[:close] + "\n" + stub_card(jobs[name]) + block[close:]
            cards_added.append(name)
            cats = {m.group(1): m.end() for m in _CATEGORY_RE.finditer(block)}
    js = js[:j_body] + block + js[j_end:]

    # report-only checks ──────────────────────────────────────────────────
    labels = []
    for name, sched in cards.items():
        if name not in jobs:
            continue
        crons = [s["cron"] for s in scheds.values() if (s.get("target") or {}).get("name") == name]
        if label_disagrees(sched, crons):
            labels.append((name, sched, crons))
    stale = []
    for name in cards_removed:
        n = len(re.findall(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", js))
        if n:
            stale.append((name, n))
    services = [s["name"] for s in _declared(export["services"]) if s["name"] not in js]
    tables = [t["name"] for t in export["tables"] if t.get("kind") == "table" and t.get("declared", True)
              and t["name"] not in js]

    res = Result(js=js, crons_added=added, crons_removed=removed, crons_changed=changed,
                 cards_removed=cards_removed, cards_added=cards_added, labels_to_check=labels,
                 stale_mentions=stale, services_not_named=services, tables_not_named=tables,
                 stamp=stamp, stamp_old=stamp_old)
    return res


# ─────────────────────────────────────────────────────────────────────────────
# report
# ─────────────────────────────────────────────────────────────────────────────

def report(res: Result, export: dict[str, Any], template_text: str = "") -> str:
    out = ["## Diagram update from the architecture export", "",
           f"Export commit `{export['sources']['commit']}`.", ""]

    def section(title: str, items: list[str]) -> None:
        out.append(f"### {title}")
        out.extend(items if items else ["- none"])
        out.append("")

    section("Applied: provenance comment",
            [f"- `{res.stamp_old or '(none)'}` → `{res.stamp}`"] if res.stamp_changed else [])
    section("Applied: triggers added", [f"- `{n}`" for n in res.crons_added])
    section("Applied: triggers removed", [f"- `{n}`" for n in res.crons_removed])
    section("Applied: triggers changed", [f"- `{n}`: `{a}` → `{b}`" for n, a, b in res.crons_changed])
    section("Applied: job cards removed (no longer declared)", [f"- `{n}`" for n in res.cards_removed])
    section("Applied: stub job cards added (describe them)", [f"- `{n}`" for n in res.cards_added])
    section("Check: card schedule text vs triggers",
            [f"- `{n}`: says “{s}”; triggers {', '.join(f'`{c}`' for c in cr)}" for n, s, cr in res.labels_to_check])
    stale = list(res.stale_mentions)
    for name in res.cards_removed:
        k = len(re.findall(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", template_text))
        if k:
            stale.append((name + " (layout)", k))
    section("Check: page text still naming removed jobs", [f"- `{n}`: {k} mention(s)" for n, k in stale])
    names = [f"- `{n}`" for n in res.services_not_named]
    in_layout = [n for n in res.services_not_named if n in template_text]
    section("Check: declared services the page data does not name",
            [f"{s} (in layout)" if n in in_layout else s for s, n in zip(names, res.services_not_named)])
    section("Check: declared tables the page does not name by name (it may group them)",
            [f"- {len(res.tables_not_named)}: " + ", ".join(f"`{n}`" for n in res.tables_not_named)]
            if res.tables_not_named else [])
    drift = export.get("drift") or {}
    live = (export["sources"] or {}).get("live")
    if live:
        section("Live drift (from the export, nothing changed)", [
            f"- {k.replace('_', ' ')}: " + (", ".join(f"`{x}`" for x in v) if v else "none")
            for k, v in drift.items()])
    else:
        out += ["### Live drift", "- not read (repo-only export)", ""]
    return "\n".join(out).rstrip() + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--export", required=True)
    ap.add_argument("--canvas", required=True, help="the bundled diagram page (HTML)")
    ap.add_argument("--output", help="write the updated page here")
    ap.add_argument("--report", help="write the Markdown report here (default: stdout)")
    ap.add_argument("--run-label", help="e.g. 'run 43354574977', added to the provenance comment")
    ap.add_argument("--check", action="store_true", help="exit 1 when the page would change; write nothing")
    a = ap.parse_args(argv)
    if not a.check and not a.output:
        ap.error("--output is required unless --check")

    try:
        with open(a.export, encoding="utf-8") as f:
            export = load_export(json.load(f))
        with open(a.canvas, encoding="utf-8", newline="") as f:
            html = f.read()
        bundle = Bundle.parse(html)
        res = update(bundle.js, export, a.run_label)
    except (CanvasError, OSError, ValueError) as exc:
        # Exit 2, not 1: under --check, 1 means "the page would change".
        sys.stderr.write(f"canvas_from_export: refused: {exc}\n")
        return 2
    tm = _TEMPLATE_RE.search(html)
    tpl = json.loads(tm.group(2)) if tm else ""
    text = report(res, export, tpl)
    if a.check:
        sys.stdout.write(text)
        return 1 if res.changed else 0
    with open(a.output, "w", encoding="utf-8", newline="") as f:
        f.write(bundle.render(res.js) if res.js != bundle.js else html)
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
