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
* size          each doc is at least 80% of its previous line count; a
                REGENERATED doc is measured in bytes instead, since its
                headings carry the month's data
* structure     a regenerated doc carries every numbered section its prompt
                promises, derived from the prompt
* elision       no prose line is only an ellipsis: a `replace` that writes
                `...` deletes the paragraph it stood in (run 27)
* prose floor   prose outside the marker blocks keeps 80% of its characters
* tail          no line is the tail of the line above it: a `replace` that
                rewrote a span and left the end of the old text (run 28)
* as-of         the "Live <date>" and "read on <date>" labels in prose name
                the snapshot this run actually read (run 28)
* stale         no retired name or phrase appears outside history context
* scaling       no doc states a fixed min-instances for a service whose
                minInstanceCount is PATCHed on a schedule
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

# The infrastructure documents live under docs/product/infrastructure/ and are
# named to slot under the numbered product series (05-INFRASTRUCTURE.md). Named
# once here so a future move is one edit rather than forty.
INFRA = "docs/product/infrastructure"
ARCH = f"{INFRA}/05-a-ARCHITECTURE.md"
DEPS = f"{INFRA}/05-c-DATA_DEPENDENCIES.md"
COST = f"{INFRA}/05-d-COST_ANALYSIS.md"
API = f"{INFRA}/05-e-API.md"

DOCS = (ARCH, DEPS, COST, "README.md")
MARKER_DOCS = (ARCH, DEPS, API)
# Every block each document must carry. A balanced-pairs check alone lets a
# block vanish when both its markers are deleted together (Codex, PR #1009).
# Spelled-out counts appear in the generated prose ("`2` for one"), so the
# gates must read them; the verifier already carries the same table.
WORD_NUMBERS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "eleven": 11, "twelve": 12}

EXPECTED_MARKERS = {
    ARCH: ("jobs", "schedulers", "tables", "dbtables", "routes", "services", "reconcile", "modules"),
    DEPS: ("tables", "dbtables", "writes", "reads", "multiwriter", "orphans", "blast", "graph"),
    API: ("routers", "routes"),
}
SIZE_FLOOR = 0.80
# README.md is a pointer map by design (2026-09-07); its length is not a
# content signal, so it is exempt from the size floor (headings still apply).
SIZE_FLOOR_EXEMPT = ("README.md",)
# COST_ANALYSIS.md is REGENERATED from the month's billing digests -- its own
# prompt says "Regenerate", not "update in place" -- and its headings carry
# that month's values: `Cloud Run (Jobs & Services) — $94.26`,
# `## 2. Top 10 cost line items by SKU (Partial August data)`,
# `#1 — Implement Artifact Registry retention policies (estimated saving: $20-25/mo)`.
# Demanding those persist demands this month's report keep last month's
# numbers, and run 17 failed on twelve of them plus a line-count floor while
# the document GREW 31% in bytes (6,143 -> 8,027 over 103 -> 82 lines). The
# churn ceiling already treated it as regenerated at 0.85; these two gates did
# not. What replaces them is stricter about the thing that matters: every
# numbered section the prompt promises must be present, and the byte mass may
# not collapse. (Run 17, 2026-09-07.)
REGENERATED = (COST,)
BYTE_FLOOR = 0.80

# Prose outside the rendered marker blocks. The same 80% as SIZE_FLOOR, and
# deliberately not tighter: an earlier revision set 0.90 and described it as
# "lower than SIZE_FLOOR", which it is not -- a higher floor permits LESS
# shrinkage, so it would have failed a refresh that legitimately retires a
# prose-heavy section, including on the two documents SIZE_FLOOR exempts.
# Run 27's damage is caught at 80% regardless. (Codex, PR #1061.)
PROSE_FLOOR = 0.80

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
#   05-e-API.md      — every line comes from the router files
#   COST_ANALYSIS.md — written wholesale from the billing CSVs; when the SKU
#                      ordering shifts, most of its table rows change
# They are not unprotected: the size floor is the real guard for
# COST_ANALYSIS.md, and it catches the degradation that matters. In the
# 2026-09-02 incident it fell 163 -> 103 lines (63% of its previous size,
# under the 80% floor) and would have been stopped on that alone.
CHURN_CEILING_RENDERED = {API: 0.90, COST: 0.85}
DIFF_DOCS = DOCS + (API,)
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
    ARCH, DEPS, COST, "RUNBOOK.md",
    f"{INFRA}/05-b-ERD.md", f"{INFRA}/05-f-PIPELINE.md", f"{INFRA}/05-g-DATA_PIPELINE.md", API,
    f"{INFRA}/05-i-GCP_IMPLEMENTATION_GUIDE.md", "docs/product/README.md", "docs/audits/",
    "gcp/cloudbuild/README.md", "CLAUDE.md", "SETUP.md",
)
LINK = re.compile(r"\]\(([^)#\s]+)(#[^)]*)?\)")


def _err(msg: str) -> None:
    print(f"::error::{msg}")


def _headings(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", h.strip()) for h in re.findall(r"^#{2,3} +(.+)$", text, re.M)]


def gate_coverage(root: pathlib.Path, repo: dict, live: dict | None) -> list[str]:
    arch = (root / ARCH).read_text()
    deps = (root / DEPS).read_text()
    out = []
    names = {j["name"] for j in repo["jobs"]} | set((live or {}).get("jobs", {}))
    miss = sorted(n for n in names if f"`{n}`" not in arch)
    if miss:
        out.append(f"{ARCH} does not name these jobs: {' '.join(miss)}")
    miss = sorted(t["name"] for t in repo["tables"] if f"`{t['name']}`" not in arch)
    if miss:
        out.append(f"{ARCH} does not name these tables: {' '.join(miss)}")
    miss = sorted(r for r in repo["routers"] if f"routers/{r}.py" not in arch)
    if miss:
        out.append(f"{ARCH} does not name these routers: {' '.join(miss)}")
    sched = {s["name"] for s in repo["schedulers"]} | set((live or {}).get("schedulers", {}))
    miss = sorted(n for n in sched if f"`{n}`" not in arch)
    if miss:
        out.append(f"{ARCH} does not name these schedulers: {' '.join(miss)}")
    svc = set((live or {}).get("services", {}))
    miss = sorted(n for n in svc if f"`{n}`" not in arch)
    if miss:
        out.append(f"{ARCH} does not name these services: {' '.join(miss)}")
    blast_start = deps.find("inventory:blast:start")
    blast = deps[blast_start:] if blast_start >= 0 else ""
    miss = sorted(j["name"] for j in repo["jobs"] if f"| `{j['name']}` |" not in blast)
    if miss:
        out.append(f"{DEPS} blast-radius block lacks rows for: {' '.join(miss)}")
    return out


def gate_subsections(root: pathlib.Path, repo: dict) -> list[str]:
    deps = (root / DEPS).read_text()
    out = []
    names = [t["name"] for t in repo["tables"]] + [v["name"] for v in repo["materialized_views"]] + [v["name"] for v in repo["views"]]
    for t in names:
        n = len(re.findall(rf"^### `{re.escape(t)}`\s*$", deps, re.M))
        if n < 2:
            out.append(f"{DEPS} has {n} `### `{t}`` subsection(s); needs one in §2 and one in §3")
    return out


def relation_counts(repo: dict, live: dict) -> tuple[int, int]:
    """(declared, runtime-created) relation counts, the way the gate checks
    them and the way the prompts now state them.

    A SET difference, not a subtraction of totals: a relation declared in
    schema.sql but not yet migrated live would make the subtraction
    undercount, rejecting correct prose and accepting a wrong number. (Codex,
    PR #1009.) Declared means tables, views AND materialized views -- run 24
    wrote 26, 28 and 30 "runtime relations" against a true 27 because the
    model was handed the live and table counts and left to derive this one.
    """
    declared_names = inv.declared_relation_names(repo)
    return len(declared_names), len(inv.runtime_relations(repo, live))


def gate_markers(root: pathlib.Path, repo: dict, live: dict | None) -> list[str]:
    out = []
    for doc in MARKER_DOCS:
        # Per block, by name. Run 24 reported "an inventory marker block
        # differs" for 05-c and nothing else, and the artifact holding the
        # answer is behind an endpoint this sandbox cannot reach; a finding
        # that names the block and the first differing line is the difference
        # between a fix and a guess.
        try:
            for name, first_diff in inv.differing_blocks(root / doc, repo, live, root=root):
                out.append(f"{doc}: inventory:{name} block differs from a fresh render "
                           f"(the model edited inside it); first difference: {first_diff}")
        except ValueError as e:
            out.append(f"{doc}: {e}")
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
        for h in [] if doc in REGENERATED else _headings(old):
            core = re.sub(r"^[\d.]+\s*", "", h)
            if h.lower() in new_heads or core.lower() in {re.sub(r"^[\d.]+\s*", "", x) for x in new_heads}:
                continue
            if core and core.lower() in removed_section.lower():
                continue
            out.append(f"{doc}: heading lost since the previous version and not listed under '{REMOVED_HEADING}': {h!r}")
        if doc in REGENERATED:
            # Lines are the wrong unit for a document rebuilt from data: run 17
            # lost 21 lines while gaining 1,884 bytes. Mass is the measure.
            ob, nb = len(old.encode()), len(new.encode())
            if nb < ob * BYTE_FLOOR:
                out.append(f"{doc}: shrank from {ob} to {nb} bytes "
                           f"(< {int(BYTE_FLOOR*100)}%) — content was dropped, not regenerated")
            continue
        o, n = len(old.splitlines()), len(new.splitlines())
        if doc not in SIZE_FLOOR_EXEMPT and n < o * SIZE_FLOOR:
            out.append(f"{doc}: shrank from {o} to {n} lines (< {int(SIZE_FLOOR*100)}%) — content was dropped, not updated")
    return out


# A line whose ENTIRE content is an ellipsis, optionally behind a list marker
# and a bold label. Run 27 wrote exactly these, five as bare section intros and
# four as `- **`market_data_daily`** ...`, eliding 4,035 characters of prose
# that had taken the place of real sentences. A mid-sentence ellipsis is
# ordinary prose ("`gamma_levels_eod`, …") and is NOT matched: the whole line
# has to be the elision. (Run 27.)
# An elided line: one whose body has been replaced by an ellipsis.
#
# NORMALISE, then test. Seven review rounds each added an alternation to a
# single regex -- ordered lists, fenced diagrams, the em-dash bullet style,
# blockquotes, non-bold labels, table rows -- and each round found another
# shape the corpus already used: a dotted filename in a code label that a
# blanket "no periods" rule rejected, an ellipsis wrapped as `**...**` or
# `` `...` ``. Enumerating syntax was the wrong shape for this check. Strip
# the decoration, then ask one question: is what remains only an ellipsis?
# (Codex, PR #1061.)
_ELL_ONLY = re.compile(r"^(?:\.\.\.|…)$")
_DECORATION = re.compile(r"[*_`]+")
_MARKER = re.compile(r"^\s*(?:>\s*)*(?:(?:[-*+]|\d+[.)])\s+)?")
_SEPARATOR = re.compile(r"\s*[—–:-]\s*")
# Spans whose punctuation belongs to a name, not to a sentence: `a.py` and
# **Runtime tables.** both carry a period that does not end anything.
_LABEL_SPAN = re.compile(r"`[^`]*`|\*\*[^*]+\*\*")


def _is_ellipsis(text: str) -> bool:
    """Whether `text` is an ellipsis once Markdown decoration is removed, so
    `...`, `**...**` and `` `...` `` all read alike."""
    return bool(_ELL_ONLY.match(_DECORATION.sub("", text).strip()))


def _is_label(text: str) -> bool:
    """A short lead-in rather than a sentence. Sentence-ending punctuation is
    judged with code and emphasis spans removed first:
    `gcp/fetchers/fetch_rss_news.py` is a filename inside backticks and
    **Runtime tables.** is a bold callout label -- neither period ends a
    sentence, and rejecting every period lost list and blockquote shapes both
    documents already use."""
    bare = _LABEL_SPAN.sub("", text)
    return len(text) <= 80 and not any(c in bare for c in ".!?")


def _is_elided(line: str) -> bool:
    st = line.strip()
    if st.startswith("|"):
        # a row elides by CELL: `| Cloud SQL | ... |` keeps its label cell and
        # loses the explanation, and never ends in an ellipsis
        return any(_is_ellipsis(c) for c in st.strip("|").split("|"))
    body = _MARKER.sub("", line, count=1).strip()
    structured = line.strip() != body or _DECORATION.match(body or " ")
    if _is_ellipsis(body):
        return True
    # `<label><separator><ellipsis>`, e.g. `- **`market_data_daily`** — ...`.
    # A free-form label is only read as one behind a marker or emphasis: on a
    # bare line it would make any short sentence match, and `Loading...` is
    # prose, not an elision.
    parts = _SEPARATOR.split(body)
    if len(parts) >= 2 and _is_ellipsis(parts[-1]):
        head = _SEPARATOR.sub(" ", " ".join(parts[:-1])).strip()
        if _is_label(head) and (structured or _DECORATION.match(head or " ")):
            return True
    # `- <label> ...` with no separator at all
    head, _, tail = body.rpartition(" ")
    if structured and head and _is_ellipsis(tail) and _is_label(head):
        return True
    # `**label**...` -- no space either. Safe without a marker because the head
    # is a COMPLETE emphasis or code span, which is what separates it from
    # `Loading...`, where the head is a bare word and the line is prose.
    for ell in ("...", "…"):
        if body.endswith(ell):
            head = body[: -len(ell)].strip()
            if head and _LABEL_SPAN.fullmatch(head):
                return True
    return False


# A COMPLETE marker comment line, not any line that mentions one. Both
# documents describe their own markers in prose -- 05-a line 5 says "the tables
# between `<!-- inventory:*:start/end -->` markers", 05-c says the same in its
# header -- and a substring test treated those sentences as opening a block,
# swallowing everything to the next real end marker. Measured: it kept 76 of
# 05-c's 1,403 lines and 258 of 05-a's 1,129, so an elision in the hidden
# regions was invisible to both gates. (Codex, PR #1061.)
_MARKER_LINE = re.compile(r"^\s*<!--\s*inventory:[A-Za-z0-9_]+:(start|end)\s*-->\s*$")


def _prose_lines(text: str) -> list[str]:
    """The document's own sentences: everything outside the rendered marker
    blocks. Whole-document size is the wrong unit for these files -- 05-c is
    137 KB of which most is rendered blocks, so deleting every explanatory
    paragraph in it moved the line count by less than 1% and the existing size
    floor did not notice. (Run 27.)

    Fenced blocks are KEPT. 05-a carries hand-authored Mermaid diagrams and a
    runbook block inside fences; a diagram replaced by a bare `...` is exactly
    the damage this gate exists to catch, and skipping fences hid it from both
    gates while each diagram is far too small to move the whole-document floor
    on its own. (Codex, PR #1061.)
    """
    out, in_block = [], False
    for line in text.split("\n"):
        m = _MARKER_LINE.match(line)
        if m:
            in_block = m.group(1) == "start"
            continue
        if not in_block:
            out.append(line)
    return out


def gate_elided_prose(root: pathlib.Path) -> list[str]:
    """Prose replaced by an ellipsis instead of rewritten.

    The model is asked to update prose in place with targeted `replace` calls.
    A `...` written where a paragraph was is the summarising habit leaking into
    a file edit, and it destroys content while leaving every other gate green:
    run 27 passed the churn budget, the heading check, the marker restore and
    the live verifier with five sections gutted this way.
    """
    out = []
    for doc in DOCS:
        f = root / doc
        if not f.exists():
            continue
        for i, line in enumerate(_prose_lines(f.read_text()), 1):
            if _is_elided(line):
                out.append(f"{doc}: prose replaced by an ellipsis: {line.strip()!r} "
                           f"(prose line {i}) — the paragraph that belongs here was deleted")
    return out


# A leftover fragment is only a fragment if it is long enough to be one. Below
# this, `...` and short repeated table cells start matching. Measured over every
# markdown file in docs/ plus README.md plus run 28's four regenerated
# documents: exactly one hit, the real one.
TAIL_FRAGMENT_MIN = 20


def gate_duplicated_tail(root: pathlib.Path) -> list[str]:
    """A line that is the tail of the line above it — a botched `replace`.

    Run 28 finished 05-a-ARCHITECTURE.md with:

        Generated 2026-09-08 ... from the 2026-09-08 live snapshot. The
        monthly refresh updates this line.
        pshot. The monthly refresh updates this line.

    The model replaced the trailing span and left the tail of the old text
    behind as its own line, beginning mid-word. Every other gate passed it:
    it is not an ellipsis, the churn was 12%, the headings were intact and it
    names no infrastructure, so `verify_docs_against_live.py` had nothing to
    check. It is caught here as a shape — a line whose whole text is the end
    of the line before it, which no sentence in this corpus legitimately is.

    Only this direction is checked. A line that is a PREFIX of its neighbour
    is a repeated CLI example (`docs/alpha-vantage-quickstart.md` has eleven),
    and a line the NEXT one ends with is a wrapped shell continuation
    (`COST_AUDIT_2026-09-06.md:262`). Both shapes are legitimate here, so
    gating on them would fail honest documents.
    """
    out = []
    for doc in DOCS:
        f = root / doc
        if not f.exists():
            continue
        lines = _prose_lines(f.read_text())
        for i in range(1, len(lines)):
            prev, cur = lines[i - 1].strip(), lines[i].strip()
            if len(cur) >= TAIL_FRAGMENT_MIN and cur != prev and prev.endswith(cur):
                out.append(f"{doc}: line is the tail of the one above it: {cur!r} "
                           f"(prose line {i + 1}) — a `replace` rewrote the span and "
                           "left the end of the old text behind")
    return out


# The three "as of" labels a human wrote into the prose, every one of which has
# to track the snapshot the run was taken from. Deliberately literal: a looser
# pattern would sweep up the historical dates beside them -- 05-a carries 33
# occurrences of `2026-09-07`, and all but these are records of when something
# was corrected, deleted or audited and must NOT move.
ASOF_LABELS = (re.compile(r"\bLive (\d{4}-\d{2}-\d{2})\b"),
               re.compile(r"read on \*\*(\d{4}-\d{2}-\d{2})\*\*"),
               # 05-a's closing line carries TWO dates: "Generated <date> ...
               # from the <date> live snapshot". The first is already required
               # to be today by the workflow's own step 1, which greps every
               # one of the four documents for `Generated ${TODAY}` before
               # this script runs; the second is checked nowhere else, and a
               # refresh that updated only one of the pair would leave the
               # line self-contradicting. Only the second is added here: the
               # committed 05-d legitimately carries `Generated 2026-09-02`
               # (the last run that regenerated it), so gating the first would
               # fail an honest tree outside the workflow. (Codex, PR #1062.)
               re.compile(r"from the (\d{4}-\d{2}-\d{2}) live snapshot"))
# 05-a must carry all three: they are the header note, §3's table column and
# the closing line, and the architecture prompt names each one. The other
# documents state no live as-of label, so nothing is required of them.
REQUIRED_ASOF = {ARCH: ASOF_LABELS}


def gate_stale_asof(root: pathlib.Path, live: dict | None) -> list[str]:
    """An "as of" label that still names an older snapshot.

    Run 28 updated 05-a's header to `read on **2026-09-08**` and left §3's
    table header at `| Service | Role | Live 2026-09-07 |`, so a table of the
    current fleet announced itself as a day old. On a monthly cadence that
    label is a month out, which is long enough for a reader to discount a
    table that is in fact current.

    The dates the marker blocks carry are rendered, so they are already right;
    these three are prose and were not. All are checked against `read_at` from
    the same snapshot the blocks were rendered from -- and `read_at`, not
    today, because a run that snapshots before UTC midnight and writes after
    it has two different days. The prompt is handed the same value.
    """
    out = []
    if not live or not live.get("read_at"):
        return out
    day = live["read_at"][:10]
    for doc in DOCS:
        f = root / doc
        if not f.exists():
            continue
        matched = {pat: 0 for pat in ASOF_LABELS}
        for i, line in enumerate(_prose_lines(f.read_text()), 1):
            for pat in ASOF_LABELS:
                for m in pat.finditer(line):
                    matched[pat] += 1
                    if m.group(1) != day:
                        out.append(f"{doc}: as-of label says {m.group(1)} but this run read "
                                   f"live state on {day} (prose line {i}): {m.group(0)!r}")
        # A date gate that only compares dates fails OPEN on a reword: change
        # §3's column header to `| Service | Role | Current |` and no pattern
        # matches, so the document loses its freshness provenance and the gate
        # reports clean. 05-a is required to carry all three. (Codex, #1062.)
        for pat in REQUIRED_ASOF.get(doc, ()):  # noqa: SIM118 -- keys are patterns
            if not matched[pat]:
                out.append(f"{doc}: no as-of label matching {pat.pattern!r}. That location "
                           "states when the live state below it was read; rewording it away "
                           "leaves the reader no way to tell how fresh the table is")
    return out


def gate_prose_floor(root: pathlib.Path, previous_dir: pathlib.Path | None) -> list[str]:
    """Prose outside the rendered blocks must not collapse.

    The companion to the elision gate: it catches a paragraph that was deleted
    outright rather than replaced with a marker. Measured on the run-27 damage
    with the corrected marker matching, 05-c fell 11,046 -> 6,867 characters
    (-37.8%) while its line count moved by less than 1%, so the floor is on
    prose characters, not on the file. The 8,876 / -22.6% figures this
    docstring first carried came from the substring bug fixed above -- the
    numbers the fix itself disproved. (Codex, PR #1061.)
    """
    out = []
    if previous_dir is None:
        return out
    for doc in DOCS:
        # README is SIZE_FLOOR_EXEMPT because its length is not a content
        # signal -- it is a pointer map, and a refresh that retires obsolete
        # rows legitimately shortens it. Honour that exemption here too, or a
        # valid refresh fails on a document whose headings and links are
        # intact. The elision gate still covers README, and that signal is
        # exact rather than proportional. (Codex, PR #1061.)
        if doc in SIZE_FLOOR_EXEMPT:
            continue
        prev, cur = previous_dir / doc, root / doc
        if not prev.exists() or not cur.exists():
            continue
        o = sum(len(l) for l in _prose_lines(prev.read_text()))
        n = sum(len(l) for l in _prose_lines(cur.read_text()))
        if o and n < o * PROSE_FLOOR:
            out.append(f"{doc}: prose outside the rendered blocks shrank from {o} to {n} "
                       f"characters (< {int(PROSE_FLOOR*100)}%) — paragraphs were dropped, not updated")
    return out


def _promised_sections(root: pathlib.Path, prompt: str) -> list[tuple[str, str]]:
    """The numbered sections a regeneration prompt promises to produce.

    Derived from the prompt rather than written down here, so a section added
    to or removed from the prompt moves the gate with it.
    """
    f = root / ".github/prompts" / prompt
    if not f.exists():
        return []          # reported as a finding by the caller, not swallowed
    body = f.read_text().split("## What to produce", 1)[-1].split("\n## ", 1)[0]
    return re.findall(r"^#{2,4} (\d+)\. (.+)$", body, re.M)


def gate_regenerated_structure(root: pathlib.Path) -> list[str]:
    """A regenerated document loses the heading-persistence gate, so its
    sections are checked against what its prompt promises instead. The titles
    are matched without any data suffix -- "(Partial August data)" is this
    month's caveat, not part of the section's identity."""
    out = []
    for doc, prompt in ((COST, "cost-analysis.md"),):
        promised = _promised_sections(root, prompt)
        if not promised:
            out.append(f"{prompt}: no numbered sections found; the structure gate for {doc} is not running")
            continue
        heads = [h.lower() for h in _headings((root / doc).read_text())]
        for num, title in promised:
            want = f"{num}. {title.strip().lower()}"
            if not any(h.startswith(want) for h in heads):
                out.append(f"{doc}: missing the section its prompt promises: {num}. {title.strip()!r}")
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


SUPPRESS_RE = re.compile(r"<!--\s*verify-docs-ok:\s*(.+?)\s*-->")


def gate_new_suppressions(root: pathlib.Path, previous_dir: pathlib.Path | None) -> list[str]:
    """A suppression the MODEL wrote is not a reviewed exemption.

    `verify-docs-ok` markers silence the docs-vs-live checks for a line, and
    every regeneration can edit the four generated documents. A model that
    wrote one above a stale schedule, service or count claim would have removed
    that claim from the verifier and published a run reporting clean, with no
    human having approved the exemption. So a marker text that was not in the
    previous version of the file fails the run. (Codex, PR #1009.)
    """
    if previous_dir is None:
        return []
    out = []
    for doc in DOCS:
        prev = previous_dir / doc
        if not prev.exists():
            continue
        was = set(SUPPRESS_RE.findall(prev.read_text()))
        now = set(SUPPRESS_RE.findall((root / doc).read_text()))
        for added in sorted(now - was):
            out.append(f"{doc}: a new verify-docs-ok exemption appeared in a generated doc "
                       f"({added!r}) — an exemption is a human decision, not a model's")
    return out


# The self-contained arithmetic about `gcp/schema.sql`, which 05-a states in
# TWO places and in two different shapes: §5's "declares **70 relations** (67
# tables, ...)" and §3's table cell "95 relations (69 declared in
# `gcp/schema.sql` — 66 tables, ...)". Anchoring on §5's phrasing alone left
# the §3 copy unchecked, which is the same reading-not-deriving mistake
# Codex named on #1009 and which I then repeated while fixing this very
# sentence: I corrected §5 to 70/67 and left §3 at 69/66.
#
# Parts are matched as a list rather than a fixed 3-tuple, so a schema that
# grows a second view or loses its only one is still checked instead of
# silently unmatched -- a gate that stops matching on a reword fails open.
# Longest kind first: "materialized views" ends in "views".
RELATION_TOTAL = re.compile(r"declares \*\*(\d+) relations?\*\*|"
                            r"\b(\d+) declared in `gcp/schema\.sql`")
RELATION_PART = re.compile(r"(\d+)\s+(materialized views?|tables?|views?)")
# What may sit between a declared total and the first of its parts: an opening
# bracket, a dash, a colon.
PART_LEAD = re.compile(r"^[\s(:\u2014\u2013-]*")
# What continues the list: a comma, an "and", or both. Anything else ends it.
# The bare "and" matters -- "67 tables, 2 materialized views and 1 view" is a
# natural rephrase, and requiring the comma would silently drop the last part
# from the check rather than fail, which is the direction that loses.
PART_SEP = re.compile(r"^(?:\s*,\s*(?:and\s+)?|\s+and\s+)")


def declared_parts(rest: str) -> list[tuple[int, str]]:
    """The parts a declared total introduces, as a contiguous comma-separated run.

    Delimiting on the first `)` or `;` was still too generous: §3's breakdown
    ends at an EM DASH inside the outer parenthetical, so the scan ran on
    through the sentence's tail. It happens not to match today ("plus 26
    created at runtime"), but a rephrase to "plus 26 tables created at
    runtime" would compare that 26 against the 67 declared tables and abort a
    monthly refresh whose numbers were correct.

    Consuming the run itself has no such boundary to get wrong: the list ends
    at the first thing that is not another `N kind` after a comma, whatever
    punctuation follows. (Codex, PR #1062.)
    """
    out: list[tuple[int, str]] = []
    rest = PART_LEAD.sub("", rest, count=1)
    while True:
        m = RELATION_PART.match(rest)
        if not m:
            return out
        out.append((int(m.group(1)), m.group(2)))
        rest = rest[m.end():]
        sep = PART_SEP.match(rest)
        if not sep:
            return out
        rest = rest[sep.end():]


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
    text = (root / ARCH).read_text()

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
    # The document's own shorthand is "`2` for one", so a word count is the
    # shape already in use; accepting only digits let a rephrase to "`2` for
    # two" defeat the gate. (Codex, PR #1009.)
    for m in re.finditer(r"`--max-retries \d`[^.\n]*", text):
        for m2 in re.finditer(r"`(\d)`\s+for\s+(\d+|[a-z]+)", m.group(0)):
            n = WORD_NUMBERS.get(m2.group(2).lower(), m2.group(2))
            if str(n).isdigit():
                claims.append((m2.group(1), str(n)))
    for flag, claimed in claims:
        want = counts.get(flag, 0)
        if int(claimed) != want:
            out.append(f"{ARCH}: claims {claimed} jobs at --max-retries {flag}; "
                       f"gcp/deploy.sh declares {want}")

    # "declares **70 relations** (66 tables, 2 materialized views, 1 view)".
    # Run 28 raised the total from 69 to 70 -- correctly, `gcp/schema.sql` had
    # gained a table -- and left the breakdown at 66/2/1, which sums to 69. The
    # sentence contradicted itself, and every gate passed it: the total was
    # right, the churn was 12%, and no other document repeats the split. All
    # four numbers are computable from the same parse the rendered table comes
    # from, so none of them should be a prose claim anyone keeps in sync.
    kinds = {"table": len(repo["tables"]), "materialized view": len(repo["materialized_views"]),
             "view": len(repo["views"])}
    total = sum(kinds.values())
    breakdown = ", ".join(f"{v} {k}" + ("s" if v != 1 else "") for k, v in kinds.items())
    for doc in (ARCH, DEPS):
        for i, line in enumerate(_prose_lines((root / doc).read_text()), 1):
            for m in RELATION_TOTAL.finditer(line):
                claimed = m.group(1) or m.group(2)
                if int(claimed) != total:
                    out.append(f"{doc}: claims {claimed} declared relations (prose line {i}); "
                               f"gcp/schema.sql declares {total} ({breakdown})")
                parts = declared_parts(line[m.end():])
                for n, kind_word in parts:
                    kind = kind_word.rstrip("s")
                    if n != kinds[kind]:
                        out.append(f"{doc}: claims {n} {kind_word} in gcp/schema.sql "
                                   f"(prose line {i}); it declares {kinds[kind]} ({breakdown})")
                # Every part being individually right does not make the list
                # complete: "70 relations (67 tables, 2 materialized views)"
                # passes each comparison while the parts shown sum to 69 -- the
                # same self-contradiction this gate was added for, recreated by
                # dropping a category instead of mistyping one. (Codex, #1062.)
                seen = {k.rstrip("s") for _, k in parts}
                want = {k for k, v in kinds.items() if v}
                if parts and seen != want:
                    missing = ", ".join(sorted(want - seen)) or "-"
                    out.append(f"{doc}: the breakdown beside {claimed} relations omits "
                               f"{missing} (prose line {i}); gcp/schema.sql declares "
                               f"{total} ({breakdown}) and every kind belongs in the list")

    if live and live.get("db_tables"):
        declared, runtime = relation_counts(repo, live)
        for doc in (ARCH, DEPS):
            body = (root / doc).read_text()
            # The same compiled pattern the renderer rewrites, imported rather
            # than repeated: a gate matching a different shape from the render
            # would flag a number the render had already fixed.
            for m in inv.RUNTIME_RELATION_COUNT.finditer(body):
                if int(m.group(1)) != runtime:
                    out.append(f"{doc}: claims {m.group(1)} runtime relations; "
                               f"{len(live['db_tables'])} live minus {declared} declared is {runtime}")
    return out


# A service whose minInstanceCount is PATCHed on a schedule has no single
# scaling value, so any prose stating one is wrong half the day. This claim
# about `discord-interactions` was corrected five separate times on PR #1009 --
# §3, §7, the diagram, and twice more -- because each correction fixed the copy
# that had been read rather than the class. The windowed set is derived from
# `_schedule_min_instances` in gcp/deploy.sh, so a second scheduled service is
# covered the day it is declared.
SCALING_CLAIM = re.compile(r"min[- ]instances?\s*[=:]?\s*(\d+)|minInstanceCount\s*[=:]\s*(\d+)", re.I)
WINDOW_OK = re.compile(r"window|warm|weekday|market hours|from the clock|inside|outside|schedul", re.I)


def gate_scheduled_scaling(root: pathlib.Path, repo: dict) -> list[str]:
    windowed = {s["target_service"] for s in repo["schedulers"]
                if s.get("helper") == "_schedule_min_instances" and s.get("target_service")}
    if not windowed:
        return []
    out = []
    for doc in DOCS:
        for i, line in enumerate((root / doc).read_text().splitlines(), 1):
            for svc in windowed:
                if svc not in line or not SCALING_CLAIM.search(line):
                    continue
                if WINDOW_OK.search(line) or HISTORY_OK.search(line):
                    continue
                out.append(f"{doc}:{i}: states a fixed min-instances for {svc!r}, whose "
                           f"minInstanceCount is PATCHed on a schedule "
                           f"(_schedule_min_instances in gcp/deploy.sh) — say which window it holds in")
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
        out.append("README.md embeds a mermaid block; it is a pointer map, the diagram lives in docs/product/infrastructure/05-a-ARCHITECTURE.md")
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
    findings += gate_elided_prose(root)
    findings += gate_duplicated_tail(root)
    findings += gate_stale_asof(root, live)
    findings += gate_prose_floor(root, previous_dir)
    findings += gate_regenerated_structure(root)
    findings += gate_derived_numbers(root, repo, live)
    findings += gate_new_suppressions(root, previous_dir)
    findings += gate_scheduled_scaling(root, repo)
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
