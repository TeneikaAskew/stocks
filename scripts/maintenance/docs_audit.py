#!/usr/bin/env python3
"""Audit documentation against the current repo, its issues and its PRs.

Why this exists
---------------
Three existing tools already check documentation, and none of them checks the
thing that rots fastest:

* ``scripts/verify_docs_against_live.py`` compares docs to **live GCP**.
* ``scripts/maintenance/check_generated_docs.py`` gates the monthly refresh on
  **structure** — churn, headings, links, marker-block byte-equality.
* ``scripts/maintenance/doc_inventory.py`` **counts** things deterministically.

What nothing covered, in the words of PR #1111 about its own new test suite:

    What it cannot check is whether a document's prose matches the code it
    describes ... The suite says the registry is internally consistent, not
    that it is true.

This module closes the mechanical half of that gap: it reconciles documentation
against the **repository** and against **issue/PR state**, and it records review
provenance so a human (or the next run) knows which claims were last confirmed
and against which commit. The judgment half — does this prose still describe
this code — stays with the reviewer; this script hands them the worklist.

Concretely, at the time it was written, 24 issues cited as live blockers in this
repo's docs were already closed, and 102 of 139 living docs carried no review
marker at all.

Checks
------
``unclassified``   a doc under scope that ``docs/DOC_REGISTRY.md`` does not place
``marker``         missing / malformed / future-dated / unknown-SHA review marker
``closed-issue``   an issue cited on a "blocking"-shaped line that is CLOSED
``dead-link``      a relative markdown link, or a backticked repo path, that
                   resolves to nothing (the backtick case is where the rot
                   actually lives and no link checker sees it)
``changed-since``  the doc's declared code paths moved after its reviewed SHA
``class-a``        a machine-owned doc whose owning job has not delivered
``unowned``        a span inside a Class A doc that **no** job writes, so the
                   "machine-owned" label keeps it out of review while nothing
                   regenerates it. 1,325 such lines when this check landed.

Class A is a property of a REGION, not of a file
------------------------------------------------
``README.md`` is 64 lines of which the refresh writes 5 (four badges and the
closing date); the file says so itself at line 49, "the prose and the
documentation map are hand-written and no model touches them".
``docs/INVESTMENT_MODELS_SUMMARY.md`` is 1,247 lines of which
``scripts/refresh_calibration_table.py`` writes 11. ``05-e-API.md`` is 160 of
which 130 are inventory blocks. Treating the whole file as machine-owned
excluded 1,325 hand-written lines from every audit while no job would ever fix
them -- which is a rot trap, not a safeguard.

So the registry declares each Class A doc's generated regions and this module
reports the complement. Findings in an unowned span are ordinary Class D work;
findings in a generated span route to the renderer or the prompt that writes it,
and are never edited in place.

Exit codes: 0 clean, 1 a P1/P2 finding (so it can gate CI), 2 the run itself
failed. P3 is the standing worklist -- unreviewed documents and legacy marker
lines awaiting a human -- reported but never gating.
A failed ``gh`` read is exit 2 and never a silent empty result (CLAUDE.md §3.7),
and so is bad input: an unreadable ``--issues-snapshot``, a ``--date`` that is
not a calendar day, a ``--verify`` path no document consumed. Exit 1 means the
documentation has findings; none of those are findings about documentation.

``--verify`` requires ``--stamp``, because a review is recorded only by writing
a marker. Nothing is written until every ``--verify`` path has a document to
land on, so a misspelled target aborts the run rather than half of it.

Usage
-----
    python -m scripts.maintenance.docs_audit --json
    python -m scripts.maintenance.docs_audit --check
    python -m scripts.maintenance.docs_audit --stamp
    python -m scripts.maintenance.docs_audit --stamp --verify docs/product/07-MODEL-REGISTRY.md
    python -m scripts.maintenance.docs_audit --write-issues-snapshot issues.json
    python -m scripts.maintenance.docs_audit --issues-snapshot issues.json --json
"""
from __future__ import annotations

import argparse
import datetime
import fnmatch
import json
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
OWNER = "TeneikaAskew"
THIS_REPO = "stocks"
SIBLING_REPO = "solyra"
REGISTRY = "docs/DOC_REGISTRY.md"

# U+00B7. The separator the existing `**Last reviewed:**` lines already use.
DOT = "·"

MARKER_RE = re.compile(
    r"^\*\*Last reviewed:\*\*\s*(?P<date>\d{4}-\d{2}-\d{2}|unknown)"
    r"(?:\s*·\s*\*\*Depth:\*\*\s*(?P<depth>verified|scanned))?"
    r"(?:\s*·\s*\*\*Against:\*\*\s*`(?P<sha>[0-9a-f]{7,40})`)?"
    r"(?:\s*·\s*\*\*Last scanned:\*\*\s*(?P<scanned>\d{4}-\d{2}-\d{2}))?"
    r"(?P<rest>.*)$"
)

# Older human-review labels this script normalises onto `**Last reviewed:**`.
# `Generated <date>` footers and `**Date:**` creation stamps are deliberately
# NOT here: they are different facts with different owners.
LEGACY_MARKER_RE = re.compile(
    r"^\*\*(?:Last updated|Last Updated|Last refreshed|Last verified|Verified)"
    r":?\*\*:?\s*(?P<date>\d{4}-\d{2}-\d{2})(?P<rest>.*)$"
)

# Everything a bare legacy line is allowed to carry after its date before the
# line counts as content-bearing: sentence punctuation and an Owner field.
_BARE_TAIL_RE = re.compile(r"^[.\s]*(?:\u00b7\s*\*\*Owner:\*\*[^\u00b7]*)?[.\s]*$")


def legacy_tail_is_bare(rest: str) -> bool:
    """Can this legacy marker be rewritten without losing anything?

    Several legacy lines are not just a date. `05-j-GCP_IMPLEMENTATION_STATUS.md`
    carries ~900 characters of deployment detail after its `**Last Updated**:`,
    and `16-CONSOLIDATION-AUDIT.md` carries the baseline and follow-up PR links.
    Normalising those in place deletes a paragraph of real content and reads in
    the diff as a tidy one-line change. Only a bare line is rewritten; anything
    else is reported for a human to merge.
    """
    return bool(_BARE_TAIL_RE.match(rest or ""))

H1_RE = re.compile(r"^#\s+\S")

# A reference only counts as a staleness finding when the surrounding line
# presents it as live work. A changelog saying "fixed #123" is not a defect.
BLOCKING_CUE_RE = re.compile(
    r"blocking|blocked by|open issue|still open|outstanding|in progress|not started|pending",
    re.I,
)
ISSUE_URL_RE = re.compile(
    r"github\.com/" + OWNER + r"/(?P<repo>solyra|stocks)/(?P<kind>issues|pull)/(?P<num>\d+)"
)
MD_LINK_RE = re.compile(r"\[[^\]]*\]\((?P<target>[^)#\s]+)(?:#[^)\s]*)?\)")
# A backticked path: has a slash and a file-ish extension, no spaces or globs.
BACKTICK_PATH_RE = re.compile(r"`(?P<path>[A-Za-z0-9_./-]+/[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,5})`")

CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".mjs", ".sql", ".sh", ".yml", ".yaml", ".json", ".md"}


def strip_dot_segments(path: str) -> str:
    """`./scripts/tool.py` and `scripts/tool.py` are the same repository path.

    Callers compare against `git ls-tree` output, which never carries a
    leading `./`, and split on the first `/` to find the top-level directory.
    Without this the root-relative form yields the component `.`.
    """
    while path.startswith("./"):
        path = path[2:]
    return path


class AuditError(RuntimeError):
    """The run itself could not be completed. Never degrades to empty results."""


def run(cmd: list[str], *, cwd: pathlib.Path | None = None,
        ok_exit_codes: tuple[int, ...] = ()) -> str:
    """Run a command, treating only the listed non-zero exits as answers.

    `ok_exit_codes` replaced a boolean `check`, which conflated two different
    things. `git grep` exits 1 for "ran fine, no matches" and 128 for "could
    not resolve that revision"; returning stdout for both made a broken read
    look like a result of zero. The Node twin hit exactly that in CI, where
    actions/checkout's shallow clone has no `origin/main` ref: every grep
    exited 128 and the count check reported 0 where the answer was 37, which
    would have flagged a correct document as wrong. A read that could not
    happen is never a measurement (CLAUDE.md §3.7).
    """
    # `cwd=REPO` as a default ARGUMENT binds the repo root at import time, so
    # a test that points the module at a throwaway tree still shelled out
    # against this checkout. Resolved per call instead.
    proc = subprocess.run(cmd, cwd=cwd or REPO, capture_output=True, text=True)
    if proc.returncode != 0 and proc.returncode not in ok_exit_codes:
        raise AuditError(f"{' '.join(cmd[:4])}... exited {proc.returncode}: {proc.stderr.strip()[:400]}")
    return proc.stdout


# ── the base ref ────────────────────────────────────────────────────────────

# HEAD first, deliberately. The audit READS THE WORKING TREE, so the revision
# it reviews is this branch's, not the trunk's. Enumerating and stamping
# `origin/main` instead had two consequences, both measured on this branch:
# a document added here (`docs/DOC_REGISTRY.md`) was absent from `ls-tree
# origin/main` and so was never classified, marked or link-checked at all; and
# every document stamped here recorded a SHA that predates this branch, so the
# branch's own code changes land in `<stamped>..origin/main` and mark the
# freshly reviewed documents stale the moment it merges.
BASE_REF_CANDIDATES = ("HEAD", "origin/main", "main")


def _ref_exists(ref: str) -> bool:
    return subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref],
                          cwd=REPO, capture_output=True).returncode == 0


def resolve_base_ref(candidates: tuple[str, ...] = BASE_REF_CANDIDATES,
                     exists=_ref_exists) -> str:
    """The revision this run reviews: the first candidate git can resolve.

    Hard-coding `origin/main` made every documented invocation abort with exit
    2 in a detached or shallow checkout -- including the actions/checkout case
    this module's own `run()` docstring describes. `--since` did not work
    around it either, because the ls-tree, ancestry and drift reads named the
    ref separately.

    Falling back is not a silent fallback: the ref actually used is reported in
    the run's output, so a run against `HEAD` can never be mistaken for a run
    against the trunk. What would be a fallback is inventing an answer when no
    ref resolves, so that raises.
    """
    for ref in candidates:
        if exists(ref):
            return ref
    raise AuditError(
        f"none of {', '.join(candidates)} resolves in this checkout; there is "
        "nothing to audit against")


# ── registry ────────────────────────────────────────────────────────────────

REGISTRY_HEADING = "## Registry"


def _cell(raw: str) -> str:
    """Strip markdown emphasis and code ticks without eating a trailing glob `*`.

    `.strip("`* ")` looks right and is not: it turns the glob `docs/archive/*`
    into `docs/archive/`, which then matches nothing and silently drops 100+
    documents into "unclassified". Bold markers are removed as pairs instead.
    """
    text = raw.strip()
    text = re.sub(r"^\*\*(.*?)\*\*$", r"\1", text).strip()
    return text.strip("`").strip()


def load_registry(text: str) -> list[dict]:
    """Parse the pipe table under `## Registry` in docs/DOC_REGISTRY.md.

    Only that section is read. The explanatory tables above it also start their
    rows with A/B/C/D, and parsing those registered prose sentences as path
    globs.

    Columns: Class | Path glob | Declared code paths | Generated regions.

    The fourth column is optional and only meaningful for Class A. It is
    semicolon-separated so commas stay available to the code-path column.
    """
    rows: list[dict] = []
    in_registry = False
    for raw in text.split("\n"):
        line = raw.strip()
        if line.startswith("#"):
            in_registry = line.startswith(REGISTRY_HEADING)
            continue
        if not in_registry or not line.startswith("|"):
            continue
        cells = [c for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        cls = _cell(cells[0]).upper()
        if cls not in {"A", "B", "C", "D", "X"}:
            continue
        glob = _cell(cells[1])
        if not glob or " " in glob and not glob.endswith(".md"):
            continue
        paths = []
        if len(cells) > 2 and _cell(cells[2]) not in {"", "—", "-"}:
            paths = [_cell(p) for p in cells[2].split(",") if _cell(p)]
        regions = []
        if len(cells) > 3 and _cell(cells[3]) not in {"", "—", "-"}:
            regions = [_cell(r) for r in cells[3].split(";") if _cell(r)]
        rows.append({"cls": cls, "glob": glob, "code_paths": paths, "regions": regions})
    return rows


def check_registry_paths(tracked: set[str], registry: list[dict]) -> list[dict]:
    """Every explicit registry declaration must name something that exists.

    Two silent failures, both measured on this tree:

    * An exactly-named Class A artefact that has been DELETED is absent from
      `tracked`, so `document_set` never yields it and the audit reports no
      missing document -- the loss of a refresh-owned `.drawio` is invisible to
      the check written to notice it.
    * A declared code path that does not exist makes the drift check vacuous:
      `git log -- lib/options` exits 0 with empty output, so the four options
      documents citing it can never be queued for re-review no matter what the
      options implementation does.

    Both are the same shape -- a declaration that resolves to nothing, read as
    "nothing to report" rather than "this declaration is wrong".
    """
    dirs = set()
    for path in tracked:
        parts = path.split("/")
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))

    out: list[dict] = []
    for row in registry:
        glob = row["glob"]
        if not any(c in glob for c in "*?[") and glob not in tracked:
            out.append({"check": "registry", "doc": glob, "severity": "P1",
                        "detail": "registry names this document exactly, but it is not in "
                                  "the audited tree -- it was deleted, moved, or never existed"})
        for cp in row["code_paths"]:
            if cp not in tracked and cp not in dirs:
                out.append({"check": "registry", "doc": glob, "severity": "P2",
                            "detail": f"declared code path `{cp}` does not exist, so the "
                                      "drift check for this document can never fire"})
    return out


def document_set(tracked: set[str], registry: list[dict]) -> list[str]:
    """Every file this audit treats as a document.

    Markdown, plus any file the registry names outright. The two
    `Architecture*.drawio` companions are Class A with `all` ownership and
    `owned_lines` has a branch for them, but a bare `.md` filter dropped them
    before classification -- so the refresh could lose one and the audit that
    exists to notice would not.

    Glob rows are deliberately not expanded: `docs/archive/*` is a directory
    rule, and running the content checks over every file beneath it is a
    different and much larger question.
    """
    named = {r["glob"] for r in registry if not any(c in r["glob"] for c in "*?[")}
    return sorted(p for p in tracked if p.endswith(".md") or p in named)


def classify(doc: str, registry: list[dict]) -> tuple[str | None, list[str], list[str]]:
    """Most specific match wins, so a file rule beats the directory rule."""
    best: tuple[int, dict] | None = None
    for row in registry:
        if fnmatch.fnmatch(doc, row["glob"]):
            score = len(row["glob"])
            if best is None or score > best[0]:
                best = (score, row)
    if best is None:
        return (None, [], [])
    return (best[1]["cls"], best[1]["code_paths"], best[1]["regions"])


# ── generated regions (Class A) ─────────────────────────────────────────────

INVENTORY_RE = re.compile(r"<!--\s*inventory:(?P<name>[\w.-]+):(?P<edge>start|end)\s*-->")


def doc_lines(text: str) -> list[str]:
    """Lines as `wc -l` counts them: a trailing newline does not add a line.

    `text.split("\\n")` on a file ending in a newline yields a final "" that is
    not a line of the document. Counting it made every reported total one
    higher than the file, which is exactly the kind of off-by-one that makes a
    measurement untrustworthy.
    """
    if not text:
        # `"".split("\n")` is `[""]`, one phantom line. A truncated zero-byte
        # Architecture.drawio then let the `all` region claim line 1 and pass
        # validation, so the loss of a generated artefact looked like success.
        return []
    return text[:-1].split("\n") if text.endswith("\n") else text.split("\n")


def owned_lines(text: str, specs: list[str], prompt_exists=None
               ) -> tuple[set[int], list[str], str | None, list[str], bool]:
    """Which 1-based lines a job writes, which specs matched nothing, and the prompt.

    The spec grammar is deliberately tiny, because the registry is read by
    people before it is read by this function:

    ``all``            every line (a wholly rendered artefact, e.g. a .drawio)
    ``inventory:*``    every ``<!-- inventory:NAME:start/end -->`` pair
    ``inventory:NAME`` that pair, which must exist. The wildcard is satisfied
                       by whatever blocks survive, so a renderer that stops
                       emitting a block -- both markers gone, nothing
                       unbalanced -- is invisible to it. Naming the blocks
                       makes the registry, not the surviving markers, say
                       what coverage exists.
    ``mark:NAME``      the ``<!-- BEGIN NAME -->``..``<!-- END NAME -->`` pair
    ``line:REGEX``     every line matching REGEX (README's badges, its footer)
    ``prose:PATH``     everything not otherwise claimed is model-written, by
                       the prompt at PATH. Declaring it is what distinguishes
                       "a model owns this prose" from "nobody owns it".
    ``exhaustive``     the file is wholly machine-owned: ANY line outside the
                       declared regions is a defect, not expected prose.

    A spec that matches nothing is returned as unmatched rather than ignored:
    a renderer that stopped emitting a block leaves the registry claiming
    coverage that no longer exists, which is the same silent rot the whole
    module is about.
    """
    lines = doc_lines(text)
    owned: set[int] = set()
    unmatched: list[str] = []
    orphans: list[str] = []
    prompt: str | None = None
    exhaustive = False
    pairs, unbalanced = inventory_blocks(lines)

    for spec in specs:
        hit = False
        if spec == "all":
            owned.update(range(1, len(lines) + 1))
            hit = bool(lines)
        elif spec == "inventory:*":
            # Every block has to balance, not just one of them. Treating the
            # wildcard as satisfied by the first valid pair let a renderer
            # emit a start with no end while the remaining pairs kept `hit`
            # true -- and in a `prose:` file the abandoned span then routed
            # silently as model prose.
            for lo, hi in pairs.values():
                owned.update(range(lo, hi + 1))
                hit = True
            orphans.extend(o for o in unbalanced if o not in orphans)
        elif spec.startswith("inventory:"):
            name = spec[10:]
            if name in pairs:
                lo, hi = pairs[name]
                owned.update(range(lo, hi + 1))
                hit = True
            orphans.extend(o for o in unbalanced
                           if o.startswith(f"inventory:{name} ") and o not in orphans)
        elif spec.startswith("mark:"):
            # Every occurrence, not the first. `next(...)` validated one pair
            # and set hit, so a duplicate or unmatched marker left a generated
            # block classified as hand-written complement -- and because
            # refresh_calibration_table._replace_section also rewrites only the
            # first pair, a stale duplicate could persist indefinitely.
            name = spec[5:]
            begin = re.compile(rf"<!--\s*BEGIN {re.escape(name)}\s*-->")
            end = re.compile(rf"<!--\s*END {re.escape(name)}\s*-->")
            starts = [n for n, l in enumerate(lines, 1) if begin.search(l)]
            ends = [n for n, l in enumerate(lines, 1) if end.search(l)]
            if len(starts) > 1 or len(ends) > 1:
                orphans.append(f"{name} appears {len(starts)}x BEGIN / {len(ends)}x END; "
                               "exactly one balanced pair is expected")
            for lo, hi in zip(starts, ends):
                if hi >= lo:
                    owned.update(range(lo, hi + 1))
                    hit = True
            if len(starts) != len(ends):
                orphans.append(f"{name} has {len(starts)} BEGIN and {len(ends)} END markers")
        elif spec.startswith("line:"):
            pat = re.compile(spec[5:])
            for n, line in enumerate(lines, 1):
                if pat.search(line):
                    owned.add(n)
                    hit = True
        elif spec.startswith("prose:") and prompt_exists is not None \
                and not prompt_exists(spec[6:]):
            # A misspelled or deleted prompt path silently claimed the entire
            # complement: spans suppressed, stamping disabled, and findings
            # routed to an owner that is not there -- the exact silent
            # ownership gap the region map exists to prevent.
            unmatched.append(spec)
            continue
        elif spec == "exhaustive":
            exhaustive = True
            hit = True
        elif spec.startswith("prose:"):
            prompt = spec[6:]
            hit = True
        else:
            unmatched.append(spec)
            continue
        if not hit:
            unmatched.append(spec)
    return owned, unmatched, prompt, orphans, exhaustive


def inventory_blocks(lines: list[str]) -> tuple[dict[str, tuple[int, int]], list[str]]:
    """Balanced `<!-- inventory:NAME:start/end -->` pairs by name, and every
    marker with no partner, each described with its line so the finding can
    be acted on. Read once per document; both the wildcard and the named
    specs consume it."""
    pairs: dict[str, tuple[int, int]] = {}
    unbalanced: list[str] = []
    open_at: dict[str, int] = {}
    for n, line in enumerate(lines, 1):
        m = INVENTORY_RE.search(line)
        if not m:
            continue
        name = m.group("name")
        if m.group("edge") == "start":
            if name in open_at:
                unbalanced.append(f"inventory:{name} opened twice (lines "
                                  f"{open_at[name]} and {n})")
            open_at[name] = n
        elif name in open_at:
            lo = open_at.pop(name)
            if name in pairs:
                # Neither pair is unbalanced, so this assignment used to
                # replace the first silently. `insert_blocks()` refreshes only
                # the FIRST occurrence (`count=1`), so the copy that is not
                # refreshed can stay stale indefinitely while the region map
                # reports itself valid. Keep the pair the renderer actually
                # writes and report the duplicate.
                unbalanced.append(f"inventory:{name} completes a second time (lines "
                                  f"{lo}-{n}); the renderer refreshes only the first "
                                  f"pair at {pairs[name][0]}-{pairs[name][1]}, so this "
                                  "copy can never be refreshed")
                continue
            pairs[name] = (lo, n)
        else:
            unbalanced.append(f"inventory:{name} ends at line {n} with no start")
    for name, n in sorted(open_at.items(), key=lambda kv: kv[1]):
        unbalanced.append(f"inventory:{name} starts at line {n} with no end")
    return pairs, unbalanced


def unowned_spans(text: str, owned: set[int]) -> list[tuple[int, int]]:
    """Contiguous runs of lines no job writes, ignoring blank-only runs.

    A blank line between two generated blocks is not documentation, and
    reporting it as unowned prose would bury the spans that matter.
    """
    lines = doc_lines(text)
    spans, start = [], None
    for n in range(1, len(lines) + 1):
        if n in owned:
            if start is not None:
                spans.append((start, n - 1))
                start = None
        elif start is None:
            start = n
    if start is not None:
        spans.append((start, len(lines)))
    return [(a, b) for a, b in spans if any(lines[i - 1].strip() for i in range(a, b + 1))]


def region_of(line: int, owned: set[int], prompt: str | None) -> str:
    """Where a finding on this line must be fixed."""
    if line in owned:
        return "generated"
    return "model-prose" if prompt else "unowned"


def region_owner(region: str, prompt: str | None) -> str:
    """Who must make the fix -- the renderer, the prompt, or a human here.

    The region alone is half the answer, and it was the half the plain output
    dropped: "generated" without naming the job still leaves the reader
    looking for the text in the document, where editing it is exactly what
    the region rule forbids.
    """
    if region == "generated":
        return OWNING_JOB["workflow"]
    if region == "model-prose":
        return prompt or "an undeclared prompt"
    return "this document (hand-written, audit as Class D)"


def check_regions(doc: str, text: str, specs: list[str], prompt_exists=None
                  ) -> tuple[list[dict], set[int], str | None, dict]:
    """Findings, the owned line set, the prompt, and the region map.

    The unowned complement is **not** a finding. It is the expected shape of a
    mixed Class A document -- README's prose, INVESTMENT_MODELS_SUMMARY's
    hand-merged record -- and emitting a P2 for each span meant those three
    documents produced ten permanent findings that no amount of reviewing could
    clear, so `--check` could never go green and the gate was worthless. The
    spans are what the run uses to route and to stamp; they are reported as a
    `regions` map, not as defects.

    What IS a finding is a declared region that no longer exists, or a document
    the registry cannot describe at all. Those mean the map itself is wrong.
    """
    if not specs:
        return ([{"check": "unowned", "doc": doc, "severity": "P2",
                  "detail": "Class A doc with no generated regions declared; "
                            "the registry cannot say which lines a job writes"}],
                set(), None, {})
    owned, unmatched, prompt, orphans, exhaustive = owned_lines(text, specs, prompt_exists)
    out = [{"check": "unowned", "doc": doc, "severity": "P1",
            "detail": f"declared region `{spec}` matched nothing -- a renderer "
                      f"stopped emitting it, or the registry is stale"}
           for spec in unmatched]
    out += [{"check": "unowned", "doc": doc, "severity": "P1",
             "detail": f"unbalanced generated region: {o}"} for o in orphans]
    spans = [] if prompt else unowned_spans(text, owned)
    # A doc declared `exhaustive` has no legitimate complement: it is wholly
    # machine-owned, so anything outside the regions is content a regeneration
    # will discard with nobody able to say what it was. The opposite of a mixed
    # doc, where the complement is the hand-written half and reporting it makes
    # --check permanently red.
    if exhaustive:
        out += [{"check": "unowned", "doc": doc, "line": lo, "severity": "P1",
                 "detail": f"lines {lo}-{hi} sit outside every declared region of a "
                           "wholly machine-owned file; the next regeneration will "
                           "discard them"} for lo, hi in spans]
    region_map = {
        "lines": len(doc_lines(text)),
        "generated": len(owned),
        "prompt": prompt,
        "unowned_spans": [[lo, hi] for lo, hi in spans],
        "unowned_lines": sum(hi - lo + 1 for lo, hi in spans),
    }
    return out, owned, prompt, region_map


# ── markers ─────────────────────────────────────────────────────────────────

def marker_window(lines: list[str], limit: int = 40) -> range:
    """Where a DOCUMENT-level marker may live: after the H1, before §2.

    Scanning the first 40 lines flatly let section metadata stand in for the
    document's provenance. `docs/RESEARCH_COMPENDIUM.md` opens with its real H1
    on line 1, then `# PART A` on line 10 with that part's own date on line 13 --
    which the audit accepted as the whole document's review marker, so Part B
    was never covered and no marker was ever inserted after the real H1.
    """
    h1 = h1_index(lines)
    if h1 is None:
        return range(0, min(limit, len(lines)))
    stop = len(lines)
    for j in range(h1 + 1, min(h1 + 1 + limit, len(lines))):
        if lines[j].startswith("#"):
            stop = j
            break
    return range(h1 + 1, min(stop, h1 + 1 + limit, len(lines)))


def is_calendar_date(value: str | None) -> bool:
    """Is this a real day, and written the way the marker declares it?

    `MARKER_RE` only checks the SHAPE `\\d{4}-\\d{2}-\\d{2}`, so `2025-02-31`
    parses as a marker date, and every comparison the audit then makes is
    lexicographic -- it sorts below today, so it is not "future", and with a
    valid `Against:` SHA nothing else looks at it. An impossible day is
    recorded as review provenance permanently.

    The round-trip is what makes this a check rather than a shape test:
    `fromisoformat` accepts `2026-9-18` on 3.11+, which is not the format the
    marker declares and would not sort against the others.
    """
    if not value:
        return False
    try:
        return datetime.date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def check_marker_dates(doc: str, info: dict) -> list[dict]:
    """Every date a marker carries has to be a day that exists.

    P2, not P3: this is not an absent review, it is a recorded one that cannot
    be true. A date nobody can place is worse than `unknown`, which at least
    says so.
    """
    out = []
    for field, label in (("date", "review date"), ("scanned", "last-scanned date")):
        value = info.get(field)
        if value in (None, "", "unknown"):
            continue
        if not is_calendar_date(value):
            out.append({"check": "marker", "doc": doc, "severity": "P2",
                        "detail": f"{label} {value} is not a real calendar day"})
    return out


def is_future_date(date: str, today: str) -> bool:
    """Is this marker date actually in the future?

    "unknown" sorts after any date beginning with a digit, so the unguarded
    comparison reported every never-reviewed document as future-dated -- 77 of
    them on the tree this landed against, which alone kept --check red.

    Only real days are compared. `2027-02-31` sorts after today and is not a
    day, so calling it future-dated is a true-shaped answer about nothing;
    `check_marker_dates` reports it for what it is instead.
    """
    return is_calendar_date(date) and date > today


def find_marker(lines: list[str]) -> tuple[int, dict] | None:
    for i in marker_window(lines):
        line = lines[i]
        m = MARKER_RE.match(line.strip())
        if m:
            return i, {"date": m.group("date"), "depth": m.group("depth"),
                       "sha": m.group("sha"), "scanned": m.group("scanned"), "legacy": False}
        m = LEGACY_MARKER_RE.match(line.strip())
        if m:
            return i, {"date": m.group("date"), "depth": None, "sha": None,
                       "scanned": None, "legacy": True,
                       "bare": legacy_tail_is_bare(m.group("rest"))}
    return None


def h1_index(lines: list[str]) -> int | None:
    """Index of the first H1.

    Not a fixed line number on purpose: several docs open with an HTML comment
    and carry their H1 on line 9, where a line-3 insert lands inside the
    comment. A doc with no H1 is skipped by the caller entirely.
    """
    for i, line in enumerate(lines):
        if H1_RE.match(line):
            return i
    return None


def render_marker(date: str, depth: str | None, sha: str | None,
                  scanned: str, owner: str | None, extras: list[str] | None = None) -> str:
    """Two facts, kept apart on purpose.

    `Last reviewed` is when someone last confirmed the claims, and it is only
    ever moved by an actual review. `Last scanned` is when the mechanical
    checks last ran, and it moves every week. Collapsing them lets a weekly
    script overwrite a human's review date with its own automated pass, which
    is the §3.11 failure ("a doc is a claim, not evidence") wearing a
    freshness badge. `unknown` is the honest value for a doc nobody has
    reviewed -- "I have not checked this" is a complete answer.
    """
    parts = [f"**Last reviewed:** {date}"]
    if depth:
        parts.append(f"**Depth:** {depth}")
    if sha:
        parts.append(f"**Against:** `{sha}`")
    parts.append(f"**Last scanned:** {scanned}")
    if owner:
        parts.append(f"**Owner:** {owner}")
    parts.extend(extras or [])
    return f" {DOT} ".join(parts)


OWNED_FIELDS = ("Last reviewed:", "Depth:", "Against:", "Last scanned:", "Owner:")


def extra_segments(line: str) -> list[str]:
    """Segments of an existing marker line this script does not own.

    Four product docs carry real content on the marker line -- 09's
    `**Trust status:** Production but needs remediation`, 10's `**Status:**
    Incomplete`, and a planning caveat sentence each in 13 and 14. Rebuilding
    the line from the fields the script knows about silently deletes them,
    which is the same data loss as rewriting a legacy line, just on the
    format the script does own.
    """
    out = []
    for seg in line.split(DOT):
        seg = seg.strip()
        if not seg or any(seg.startswith(f"**{f}") for f in OWNED_FIELDS):
            continue
        out.append(seg)
    return out


def owner_of(lines: list[str], marker_idx: int | None) -> str | None:
    if marker_idx is None:
        return None
    m = re.search(r"\*\*Owner:\*\*\s*([^·]+)", lines[marker_idx])
    return m.group(1).strip() if m else None


def stamp(text: str, date: str, depth: str, sha: str,
          reviewed: bool = False) -> tuple[str, str]:
    """Return (new_text, action). Never inserts into a doc with no H1.

    `reviewed=False` (the default, and what a scheduled run does for most docs)
    moves only `Last scanned` and leaves any existing review claim untouched.
    """
    lines = text.split("\n")
    found = find_marker(lines)
    owner = owner_of(lines, found[0] if found else None) or "TBD"
    prev = found[1] if found else None

    # A content-bearing legacy line is left exactly as it is. Rewriting it
    # would delete the prose it carries; the audit reports it instead.
    if prev and prev.get("legacy") and not prev.get("bare", True):
        return text, "skipped-legacy-content"

    if reviewed:
        r_date, r_depth, r_sha = date, depth, sha
    elif prev and prev["date"] != "unknown":
        # Preserve the stronger, existing claim. A scan is not a review.
        r_date = prev["date"]
        r_depth = prev["depth"]
        r_sha = prev["sha"]
    else:
        r_date, r_depth, r_sha = "unknown", None, None

    extras = extra_segments(lines[found[0]]) if found and not prev.get("legacy") else []
    marker = render_marker(r_date, r_depth, r_sha, date, owner, extras)
    if found:
        idx, _ = found
        if lines[idx].strip() == marker:
            return text, "unchanged"
        lines[idx] = marker
        return "\n".join(lines), "updated"
    h1 = h1_index(lines)
    if h1 is None:
        return text, "skipped-no-h1"
    # Target shape:  "# Title" / "" / marker / "" / body.
    # Reuse the blank line the H1 already has rather than adding a second one.
    if h1 + 1 < len(lines) and lines[h1 + 1].strip() == "":
        lines[h1 + 2:h1 + 2] = [marker, ""]
    else:
        # Both blanks, not just the leading one. An H1 followed straight by
        # body text got `# Title` / "" / marker / body, and Markdown renders
        # the marker and the opening sentence as a single paragraph.
        lines[h1 + 1:h1 + 1] = ["", marker, ""]
    return "\n".join(lines), "inserted"


# ── github state ────────────────────────────────────────────────────────────

def load_issues_snapshot(file: str) -> dict[str, dict[int, dict]]:
    """Read a snapshot written by --write-issues-snapshot, or say why not.

    A missing, malformed or structurally wrong file raised FileNotFoundError,
    JSONDecodeError or ValueError straight past the AuditError handler, and
    Python exited 1 with a traceback and no report. Exit 1 is documented as
    "this documentation has findings"; automation could not tell that from
    "the audit never ran". Bad input is exit 2.

    The structural check is not ceremony: a file with no `stocks` entry makes
    every stocks citation unresolvable, which is 24 fabricated findings rather
    than an empty result (CLAUDE.md §3.7).
    """
    try:
        raw = json.loads(pathlib.Path(file).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AuditError(f"--issues-snapshot {file} could not be read: {exc}") from exc
    states: dict[str, dict[int, dict]] = {}
    for repo in (THIS_REPO, SIBLING_REPO):
        entry = raw.get(repo) if isinstance(raw, dict) else None
        if not isinstance(entry, dict):
            raise AuditError(f'--issues-snapshot {file} has no "{repo}" entry; every '
                             f"{repo} citation would read as unresolvable")
        try:
            rows = {int(k): v for k, v in entry.items()}
        except (TypeError, ValueError) as exc:
            raise AuditError(f'--issues-snapshot {file}: "{repo}" is not keyed by '
                             f"issue number: {exc}") from exc
        # Numeric keys are not enough. `check_closed_issues` reads st["state"]
        # once it has decided the row is not None, so a row with no state
        # raises KeyError -- a traceback and exit 1, the status that means
        # "this documentation has findings". A `null` row is worse: it takes
        # the `st is None` branch and reports a live issue as unresolvable,
        # fabricating a finding from a malformed file (CLAUDE.md §3.7).
        for num, rec in sorted(rows.items()):
            if not isinstance(rec, dict) or not isinstance(rec.get("state"), str):
                raise AuditError(
                    f"--issues-snapshot {file}: {repo}#{num} has no usable state "
                    f"({rec!r}); a row the audit cannot read is not a row it may "
                    "report on")
        states[repo] = rows
    return states


def fetch_issue_states(repo: str) -> dict[int, dict]:
    """One paginated read per repo, never one call per reference (Rule 0)."""
    states: dict[int, dict] = {}
    for page in range(1, 40):
        out = run([
            "gh", "api",
            f"repos/{OWNER}/{repo}/issues?state=all&per_page=100&page={page}",
            "--jq", '.[] | [.number, .state, (.state_reason // ""), '
                    '(if .pull_request then "PR" else "ISSUE" end)] | @tsv',
        ])
        rows = [r for r in out.strip().split("\n") if r.strip()]
        if not rows:
            break
        for row in rows:
            parts = row.split("\t")
            if len(parts) != 4:
                continue
            states[int(parts[0])] = {"state": parts[1], "reason": parts[2], "kind": parts[3]}
    if not states:
        raise AuditError(f"no issues returned for {repo}; refusing to report a clean run on no data")
    return states


# ── checks ──────────────────────────────────────────────────────────────────

def check_closed_issues(doc: str, text: str, states: dict[str, dict]) -> list[dict]:
    out = []
    for n, line in enumerate(text.split("\n"), 1):
        if not BLOCKING_CUE_RE.search(line):
            continue
        for m in ISSUE_URL_RE.finditer(line):
            if m.group("kind") != "issues":
                continue
            repo, num = m.group("repo"), int(m.group("num"))
            st = states.get(repo, {}).get(num)
            if st is None:
                out.append({"check": "closed-issue", "doc": doc, "line": n,
                            "detail": f"{repo}#{num} could not be resolved", "severity": "P2"})
            elif st["state"] == "closed":
                reason = st.get("reason") or "completed"
                out.append({"check": "closed-issue", "doc": doc, "line": n,
                            "detail": f"{repo}#{num} is CLOSED ({reason}) but cited as live work",
                            "severity": "P1" if reason != "not_planned" else "P2",
                            "ref": f"{repo}#{num}", "reason": reason})
    return out


def check_dead_links(doc: str, text: str, tracked: set[str]) -> list[dict]:
    out = []
    base = pathlib.PurePosixPath(doc).parent
    for n, line in enumerate(text.split("\n"), 1):
        for m in MD_LINK_RE.finditer(line):
            tgt = m.group("target")
            if tgt.startswith(("http://", "https://", "mailto:", "#")):
                continue
            resolved = str((base / tgt)) if not tgt.startswith("/") else tgt.lstrip("/")
            norm = str(pathlib.PurePosixPath(resolved))
            try:
                norm = str(pathlib.PurePosixPath(*pathlib.PurePosixPath(norm).parts))
            except Exception:
                pass
            if norm not in tracked and not (REPO / norm).exists():
                out.append({"check": "dead-link", "doc": doc, "line": n,
                            "detail": f"relative link -> {tgt}", "severity": "P2"})
        for m in BACKTICK_PATH_RE.finditer(line):
            cited = m.group("path")
            # `./scripts/tool.py` is the root-relative spelling of the same
            # path. Without this the existence check failed and then the root
            # component was `.`, never a tracked top-level directory, so the
            # citation was discarded as if it pointed outside this repo --
            # silently exempting a convention CLAUDE.md alone uses 9 times.
            p = strip_dot_segments(cited)
            if pathlib.PurePosixPath(p).suffix not in CODE_EXTS:
                continue
            if p in tracked or (REPO / p).exists():
                continue
            # Only flag paths that look like they belong to THIS repo's layout,
            # so a deliberate cross-repo citation is not reported as rot.
            root = p.split("/", 1)[0]
            if root in TOP_LEVEL_DIRS:
                out.append({"check": "dead-link", "doc": doc, "line": n,
                            "detail": f"backticked path -> {cited}", "severity": "P2"})
    return out


def check_marker_sha(doc: str, sha: str | None, base_ref: str, *,
                     cwd: pathlib.Path | None = None) -> tuple[list[dict], bool]:
    """Findings on a marker's `Against:` SHA, and whether drift since it can be measured.

    Two different answers, kept apart. A SHA this checkout does not hold (a
    depth-1 clone, or a marker stamped against a branch since rewritten) is
    reported for that document and the drift since it declared unmeasurable;
    asking `git log` about it exits 128 and aborted the whole run, which is
    what a depth-1 checkout of this branch did on 2f14ccf right after
    `resolve_base_ref` had let it get that far. A SHA that IS here but is not
    an ancestor of the base ref is the ordinary finding, and drift is measured.
    """
    if not sha:
        return [], True
    known = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"],
                           cwd=cwd or REPO, capture_output=True).returncode == 0
    if not known:
        return [{"check": "marker", "doc": doc, "severity": "P2",
                 "detail": f"reviewed-against {sha} is not in this checkout; drift since "
                           f"it cannot be measured (shallow clone?)"}], False
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", sha, base_ref],
                              cwd=cwd or REPO, capture_output=True).returncode == 0
    if not ancestor:
        return [{"check": "marker", "doc": doc, "severity": "P2",
                 "detail": f"reviewed-against {sha} is not an ancestor of {base_ref}"}], True
    return [], True


_DRIFT_HEADER_RE = re.compile(r"^[0-9a-f]{7,40}\t")
_DRIFT_STATUS_RE = re.compile(r"^([AMDRCT])(\d{3})?\t")


def drift_commits(out: str) -> list[str]:
    """Commits in a `--name-status` listing that actually changed content.

    A pure rename (`R100`) is not drift; a moved file with an edit (`R096`) is
    exactly as much drift as the edit alone. `--diff-filter` cannot express
    that distinction -- it files the whole commit under R -- so the score is
    read per file here.
    """
    commits: list[tuple[str, bool]] = []
    for line in out.split("\n"):
        if _DRIFT_HEADER_RE.match(line):
            commits.append((line, False))
            continue
        status = _DRIFT_STATUS_RE.match(line)
        if not status or not commits:
            continue
        kind, score = status.group(1), status.group(2)
        if kind in "AMD" or (kind == "R" and int(score or 100) < 100):
            commits[-1] = (commits[-1][0], True)
    return [line for line, drift in commits if drift]


def check_changed_since(doc: str, sha: str | None, code_paths: list[str], base_ref: str,
                        *, cwd: pathlib.Path | None = None) -> list[dict]:
    if not sha or not code_paths:
        return []
    # `git log` exits 0 with empty output when the range holds no commits, so
    # no non-zero code here means "nothing changed". A SHA the repo does not
    # have exits 128, and swallowing that reported "nothing changed since
    # <sha>" for a commit that was never read. The marker check reports an
    # unknown SHA separately, so this one aborts.
    # AMDR with the rename score read per file, not AMD: a declared path
    # GAINING a module or LOSING one changes the documented surface just as
    # much as editing one, and a file moved WITH an edit is drift that git
    # files under `R<similarity>` -- measured on git 2.43.0, a one-line edit
    # during a move is `R096` and `--diff-filter=AMD` returned no commit at
    # all, so the document was never queued although the implementation had
    # changed. Only a pure rename (`R100`) stays excluded, which is what the
    # filter was for: the 2026-09-07 file-move wave must not flag every
    # document. `-M` asks for the score explicitly rather than trusting
    # `diff.renames` on whichever machine runs the audit.
    out = run(["git", "log", "--format=%h%x09%s", "--name-status", "-M",
               "--diff-filter=AMDR", f"{sha}..{base_ref}", "--"] + code_paths,
              cwd=cwd or REPO)
    commits = drift_commits(out)
    if not commits:
        return []
    return [{"check": "changed-since", "doc": doc,
             "detail": f"{len(commits)} content commit(s) to {', '.join(code_paths)} since {sha}",
             "severity": "P2", "commits": commits[:10]}]


TOP_LEVEL_DIRS: set[str] = set()

# The job that owns the Class A docs, and the PR title it opens.
OWNING_JOB = {
    "workflow": "refresh-architecture-docs.yml",
    "pr_title_re": re.compile(r"architecture doc refresh", re.I),
    "docs": [
        "docs/product/infrastructure/05-a-ARCHITECTURE.md",
        "docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md",
        "docs/product/infrastructure/05-d-COST_ANALYSIS.md",
        "README.md",
    ],
}
GENERATED_RE = re.compile(r"Generated (\d{4}-\d{2}-\d{2})")

# `gh api --paginate` is not the mechanism here: GitHub's Link header names
# `repositories/{id}/pulls`, which this sandbox's API proxy rejects with 403,
# so the page number is walked explicitly -- the same loop fetch_issue_states
# already uses.
PR_PAGE_SIZE = 100
PR_PAGE_LIMIT = 40


def fetch_owned_prs(title_re: re.Pattern, *, page_size: int = PR_PAGE_SIZE) -> list[dict]:
    """Every refresh PR the delivery check can act on, newest first.

    One `per_page=100` page covers the 100 newest PRs of ANY kind, not the 100
    newest refresh PRs. Measured on this repo on 2026-09-18: page 1 reaches
    #1130 down to #959, a 15-day window, and the refresh PR that actually
    delivered -- #953, merged 2026-09-02 -- is on page 2. The single-page
    lookup therefore saw no delivery at all, so the supersede rule could not
    fire and three long-superseded failed attempts stayed on the report.

    The walk stops at the first MERGED refresh PR, because every matching PR
    older than that one is created before `delivered` and is skipped by the
    supersede rule anyway: reading further costs requests and can change
    nothing (CLAUDE.md §3.8).
    """
    owned: list[dict] = []
    for page in range(1, PR_PAGE_LIMIT + 1):
        out = run([
            "gh", "api",
            f"repos/{OWNER}/{THIS_REPO}/pulls?state=all&per_page={page_size}"
            f"&sort=created&direction=desc&page={page}",
            "--jq", '.[] | [.number, .state, (.merged_at // ""), .created_at, .title] | @tsv',
        ])
        rows = [r for r in out.strip().split("\n") if r.strip()]
        for row in rows:
            parts = row.split("\t")
            if len(parts) >= 5 and title_re.search(parts[4]):
                owned.append({"num": parts[0], "state": parts[1], "merged": parts[2],
                              "created": parts[3], "title": parts[4]})
        if len(rows) < page_size or any(pr["merged"] for pr in owned):
            break
    return owned


# Artifacts the owning workflow refreshes BEST-EFFORT. The calibration step is
# written `python -m scripts.refresh_calibration_table || echo "::warning::
# ... continuing"` (refresh-architecture-docs.yml:895-896), so a Cloud SQL
# outage leaves the table stale while the step exits 0, the run concludes
# success, and the refresh PR still merges -- which also suppresses the
# PR-state checks above. Workflow success is evidence that the job ran, never
# that THIS artifact was refreshed. The only evidence is the date the artifact
# itself carries.
#
# The bound is the renderer's own: past `STALE_DAYS` scripts/
# refresh_calibration_table.py writes `B (stale)` for the row, so a block
# older than that is one the renderer has not re-rendered.
BEST_EFFORT_ARTIFACTS = [
    {
        "doc": "docs/INVESTMENT_MODELS_SUMMARY.md",
        "region": "ticker_calibration_resolved_values",
        "date_re": re.compile(r"latest calibration (\d{4}-\d{2}-\d{2})"),
        "max_age_days": 180,
        "refresher": "scripts/refresh_calibration_table.py",
    },
]


def check_best_effort_artifacts(today: str, artifacts: list[dict] | None = None) -> list[dict]:
    """Freshness for the documents whose refresh step cannot fail the run.

    Needs no network, so it runs even under `--issues-snapshot`: the question
    is what the artifact says about itself, not what GitHub says about the job.
    """
    findings: list[dict] = []
    for art in artifacts if artifacts is not None else BEST_EFFORT_ARTIFACTS:
        path = REPO / art["doc"]
        if not path.exists():
            continue
        dates = art["date_re"].findall(path.read_text(encoding="utf-8", errors="replace"))
        if not dates:
            findings.append({"check": "class-a", "doc": art["doc"], "severity": "P2",
                             "detail": f"`{art['region']}` carries no date, so nothing shows "
                                       f"whether {art['refresher']} ever refreshed it; its "
                                       "workflow step is best-effort and cannot fail the run"})
            continue
        bad = [d for d in dates if not is_calendar_date(d)]
        if bad:
            findings.append({"check": "class-a", "doc": art["doc"], "severity": "P2",
                             "detail": f"`{art['region']}` is dated {bad[0]}, which is not a "
                                       "real calendar day"})
            continue
        newest = max(dates)
        age = (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(newest)).days
        if age > art["max_age_days"]:
            findings.append({"check": "class-a", "doc": art["doc"], "severity": "P2",
                             "detail": f"`{art['region']}` is dated {newest}, {age}d old and past "
                                       f"the {art['max_age_days']}d the renderer itself calls "
                                       f"stale, so {art['refresher']} has not re-rendered it -- "
                                       "its workflow step is best-effort, so a green run and a "
                                       "merged refresh PR prove nothing about this block"})
    return findings


def check_owning_job(today: str) -> list[dict]:
    """Did the job that owns the Class A docs actually deliver?

    A `Generated <date>` stamp records that a job RAN, not that its output ever
    reached main. On 2026-09-16 the September refresh PR (#1060) had been open
    and unmerged for 8 days and three earlier "refresh failed" PRs were closed
    without merging, while the docs still advertised `Generated 2026-09-07`.
    Nothing was watching that gap; this is the check that watches it.
    """
    findings: list[dict] = []
    try:
        runs = run([
            "gh", "api",
            f"repos/{OWNER}/{THIS_REPO}/actions/workflows/{OWNING_JOB['workflow']}/runs?per_page=10",
            "--jq", '.workflow_runs[] | [.conclusion, .created_at] | @tsv',
        ])
        owned_prs = fetch_owned_prs(OWNING_JOB["pr_title_re"])
    except AuditError:
        # Do NOT convert this into a finding. A finding means "the docs are
        # stale"; this means "the audit never learned whether they are", and
        # collapsing the two let a default run exit 0 and a --check run exit 1
        # -- neither of which is the documented exit 2 for an incomplete audit.
        raise

    recent = [r.split("\t") for r in runs.strip().split("\n") if r.strip()]
    if recent and recent[0][0] not in {"success", ""}:
        findings.append({"check": "class-a", "doc": OWNING_JOB["workflow"], "severity": "P1",
                         "detail": f"last run concluded {recent[0][0]} at {recent[0][1]}"})

    # A closed-unmerged attempt that a LATER refresh superseded is history, not
    # a live defect. Reporting #963/#1012/#1021 forever kept --check red with
    # findings whose only remedy would be reviving obsolete PRs.
    delivered = max((pr["merged"] for pr in owned_prs if pr["merged"]), default="")
    for pr in owned_prs[:6]:
        if pr["merged"]:
            continue
        if delivered and pr["created"] < delivered:
            continue
        age = (datetime.date.fromisoformat(today)
               - datetime.date.fromisoformat(pr["created"][:10])).days
        if pr["state"] == "open":
            findings.append({"check": "class-a", "doc": "|".join(OWNING_JOB["docs"][:2]),
                             "severity": "P1",
                             "detail": f"refresh PR #{pr['num']} open and unmerged for {age}d "
                                       f"-- the Generated stamp on the Class A docs is not current"})
        else:
            findings.append({"check": "class-a", "doc": OWNING_JOB["workflow"], "severity": "P2",
                             "detail": f"refresh PR #{pr['num']} was closed without merging "
                                       f"({pr['title'][:60]})"})

    for doc in OWNING_JOB["docs"]:
        path = REPO / doc
        if not path.exists():
            continue
        stamps = GENERATED_RE.findall(path.read_text(encoding="utf-8", errors="replace"))
        if not stamps:
            continue
        newest = max(stamps)
        age = (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(newest)).days
        if age > 40:
            findings.append({"check": "class-a", "doc": doc, "severity": "P2",
                             "detail": f"Generated {newest} is {age}d old; the refresh is monthly"})
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="machine-readable findings on stdout")
    ap.add_argument("--check", action="store_true", help="exit 1 when any finding is reported")
    ap.add_argument("--stamp", action="store_true", help="write review markers in place")
    ap.add_argument("--verify", nargs="*", default=None, metavar="PATH",
                    help="mark these docs Depth: verified (default is scanned); requires --stamp")
    ap.add_argument("--since", metavar="SHA", help="override the reviewed-against SHA")
    ap.add_argument("--issues-snapshot", metavar="FILE", help="read issue state from FILE (offline)")
    ap.add_argument("--write-issues-snapshot", metavar="FILE", help="save the issue state read")
    ap.add_argument("--date", metavar="YYYY-MM-DD", help="override today's date (tests)")
    args = ap.parse_args(argv)

    # `--stamp --date 2026-02-30` wrote that value into every marker as
    # `Last scanned`, and the next run's MARKER_RE stopped at the prefix while
    # extra_segments kept the malformed remainder as prose. A day that does not
    # exist is bad input, not a finding: exit 2, the documented status for a
    # run that could not happen.
    if args.date is not None and not is_calendar_date(args.date):
        raise AuditError(f"--date {args.date} is not a calendar day (YYYY-MM-DD)")
    today = args.date or datetime.date.today().isoformat()
    # The revision being reviewed: what gets enumerated, diffed against and
    # stamped. One value, so the marker can never name a commit whose contents
    # the run did not read.
    base_ref = resolve_base_ref()
    head = args.since or run(["git", "rev-parse", "--short", base_ref]).strip()

    reg_path = REPO / REGISTRY
    if not reg_path.exists():
        print(f"error: {REGISTRY} not found; every doc would be unclassified", file=sys.stderr)
        return 2
    registry = load_registry(reg_path.read_text(encoding="utf-8"))

    tracked = set(run(["git", "ls-tree", "-r", base_ref, "--name-only"]).strip().split("\n"))
    TOP_LEVEL_DIRS.update(p.split("/", 1)[0] for p in tracked if "/" in p)
    docs = document_set(tracked, registry)

    if args.issues_snapshot:
        states = load_issues_snapshot(args.issues_snapshot)
    else:
        states = {THIS_REPO: fetch_issue_states(THIS_REPO), SIBLING_REPO: fetch_issue_states(SIBLING_REPO)}
    if args.write_issues_snapshot:
        # Reading an unusable snapshot is exit 2; failing to write one was
        # exit 1, because OSError walks straight past the AuditError handler.
        # Same class of failure -- the run did not happen -- so same status.
        try:
            pathlib.Path(args.write_issues_snapshot).write_text(
                json.dumps({r: {str(k): v for k, v in d.items()} for r, d in states.items()},
                           indent=1),
                encoding="utf-8")
        except OSError as exc:
            raise AuditError(
                f"--write-issues-snapshot {args.write_issues_snapshot} could not "
                f"be written: {exc}") from exc

    findings: list[dict] = check_registry_paths(tracked, registry)
    region_maps: dict[str, dict] = {}
    # Needs no network: it asks the artifact what it says about itself, which
    # is the only evidence a best-effort refresh step leaves behind.
    findings += check_best_effort_artifacts(today)
    if not args.issues_snapshot:
        findings += check_owning_job(today)
    stamped: list[dict] = []
    # A review is recorded only by WRITING a marker, so `--verify` without
    # `--stamp` is a no-op that reads, on an otherwise clean audit, as if the
    # human verification had been recorded. It exits 2 instead.
    if args.verify is not None and not args.stamp:
        raise AuditError("--verify requires --stamp: a review is recorded by writing "
                         "a marker, and without --stamp nothing is written")
    if args.verify is not None and not args.verify:
        raise AuditError("--verify needs at least one path")
    verify = {strip_dot_segments(v) for v in (args.verify or [])}
    # Every --verify path must be consumed by a document this run actually
    # stamps. A misspelled path, one outside `docs`, or one that resolves to a
    # class with nowhere to stamp used to leave everything else scan-only and
    # exit 0 without a word about the review it dropped.
    stamp_targets: set[str] = set()
    # doc -> the action `stamp` returned when it declined, so the refusal can
    # name the reason rather than listing the path and leaving the caller to
    # guess which of five causes applies.
    stamp_refusals: dict[str, str] = {}
    writes: list[tuple[str, str]] = []
    counts = {"A": 0, "B": 0, "C": 0, "D": 0, "X": 0, "unclassified": 0}

    for doc in docs:
        cls, code_paths, regions = classify(doc, registry)
        if cls is None:
            counts["unclassified"] += 1
            findings.append({"check": "unclassified", "doc": doc, "severity": "P2",
                             "detail": "no rule in docs/DOC_REGISTRY.md covers this doc"})
            continue
        counts[cls] += 1
        # X is a deliberate exclusion, B is a frozen snapshot. Both are silent.
        # Keeping them distinct from "unclassified" matters: unclassified means
        # the registry has a gap, and that is a finding worth acting on.
        if cls in {"B", "X"}:
            continue

        text = (REPO / doc).read_text(encoding="utf-8", errors="replace")
        lines = text.split("\n")
        found = find_marker(lines)

        # Class C is deliberately exempt from the content checks, not merely
        # exempt from rewriting. A 2026-04 changelog citing an issue that has
        # since closed, or a path that has since moved, was TRUE on its date --
        # reporting it produces a backlog nobody can action without destroying
        # the record. Running these checks over dated records inflated the
        # closed-issue count from 24 to 29 and dead links from 302 to 649,
        # entirely with findings whose only correct resolution is "leave it".
        if cls == "C":
            continue

        # Class A is write-restricted per REGION, not per file. Map the regions
        # first: the complement is prose no job writes, and that prose is Class
        # D in everything but the label -- audited, corrected and stamped here.
        # Findings inside a generated region are still reported, tagged with
        # where the fix belongs, and never edited in place.
        owned: set[int] = set()
        prompt: str | None = None
        stampable = cls == "D"
        if cls == "A":
            reg_findings, owned, prompt, region_map = check_regions(
                doc, text, regions, prompt_exists=lambda p: p in tracked)
            findings += reg_findings
            if region_map:
                region_maps[doc] = region_map
            # A region map that could NOT be established is not a licence to
            # write. `prompt is None` means "no model owns this prose", and it
            # is also what a Class A row with no region specs and a row whose
            # `prose:` owner is missing both leave behind -- so the marker went
            # into precisely the machine-owned document whose safe writable
            # region the audit had just reported it could not find, where the
            # next regeneration discards it without anyone able to say what it
            # was.
            map_valid = bool(region_map) and not any(
                f["severity"] == "P1" for f in reg_findings)
            stampable = map_valid and prompt is None and bool(unowned_spans(text, owned))

        content = check_closed_issues(doc, text, states) + check_dead_links(doc, text, tracked)
        if cls == "A":
            for f in content:
                f["region"] = region_of(f.get("line", 0), owned, prompt)
                f["region_owner"] = region_owner(f["region"], prompt)
        findings += content

        if not stampable:
            continue

        if found is None:
            findings.append({"check": "marker", "doc": doc, "severity": "P2",
                             "detail": "no review marker"})
        else:
            info = found[1]
            if info["legacy"]:
                findings.append({"check": "marker", "doc": doc, "severity": "P3",
                                 "detail": f"legacy label, date {info['date']}; normalise to Last reviewed"})
            findings += check_marker_dates(doc, info)
            if is_future_date(info["date"], today):
                findings.append({"check": "marker", "doc": doc, "severity": "P1",
                                 "detail": f"review date {info['date']} is in the future"})
            # Their check_marker_sha supersedes the inline ancestry test: a
            # SHA this checkout does not hold is a finding for that document,
            # not an abort for the whole run, and drift is skipped for it.
            sha_findings, measurable = check_marker_sha(doc, info["sha"], base_ref)
            findings += sha_findings
            # Separately: a marker with `unknown` or no `Against` passes every
            # check above while supporting no drift check at all, so --stamp
            # could clear the missing-marker finding with nobody having
            # reviewed anything. Say what is still owed instead of going quiet.
            # P3, because --check gates on P1/P2: 98 never-reviewed documents
            # belong on the worklist and must not hold a build red forever.
            if info["date"] == "unknown" or not info["sha"]:
                missing = []
                if info["date"] == "unknown":
                    missing.append("never reviewed")
                if not info["sha"]:
                    missing.append("no reviewed-against SHA, so drift cannot be checked")
                findings.append({"check": "marker", "doc": doc, "severity": "P3",
                                 "detail": "incomplete provenance: " + "; ".join(missing)})
            if measurable:
                findings += check_changed_since(doc, info["sha"], code_paths, base_ref)

        if args.stamp:
            # Never write a marker into a generated region. The marker goes
            # after the H1, so the check is whether anything a job owns sits
            # that high in the file -- on README the H1 is line 1 and the first
            # badge is line 5, which is why stamping it is safe at all.
            h1 = h1_index(lines)
            if owned and h1 is not None and min(owned) <= h1 + 2:
                findings.append({"check": "unowned", "doc": doc, "severity": "P2",
                                 "detail": f"not stamped: a generated region starts at line "
                                           f"{min(owned)}, too close to the H1 on line {h1 + 1}"})
                continue
            reviewed = doc in verify
            new, action = stamp(text, today, "verified" if reviewed else "scanned",
                                head, reviewed=reviewed)
            # Consumed only if the review was actually recorded. `stamp` can
            # decline -- no H1 to place a marker after, or a legacy line
            # carrying prose that rewriting would delete -- and counting the
            # target before reading that answer let `--verify` exit 0 having
            # written nothing. `unchanged` counts: the marker on disk is
            # already exactly what would be written.
            if action in {"inserted", "updated", "unchanged"}:
                stamp_targets.add(doc)
            else:
                stamp_refusals[doc] = action
            if action in {"inserted", "updated"}:
                writes.append((doc, new))
            stamped.append({"doc": doc, "action": action,
                            "depth": "verified" if reviewed else "scan-only"})

    # Nothing is written until every requested review has a document to land
    # on, so a misspelled --verify aborts the run rather than half of it.
    if args.stamp:
        missing = sorted(verify - stamp_targets)
        if missing:
            why = {"skipped-no-h1": "no H1 to place a marker after",
                   "skipped-legacy-content": "a legacy marker carrying prose that "
                                             "rewriting would delete"}
            named = ", ".join(
                f"{d} ({why.get(stamp_refusals[d], stamp_refusals[d])})"
                if d in stamp_refusals else d
                for d in missing)
            raise AuditError(
                f"--verify {named}: the review could not be recorded (not a "
                "tracked doc, or Class B/C/X, or a machine-owned file with nowhere "
                "to stamp). Nothing was written.")
        for doc, new in writes:
            (REPO / doc).write_text(new, encoding="utf-8")

    report = {
        "date": today, "base_ref": base_ref, "head": head, "docs": len(docs),
        "classes": counts, "regions": region_maps,
        "findings": findings, "stamped": stamped,
        "summary": {k: sum(1 for f in findings if f["check"] == k)
                    for k in sorted({f["check"] for f in findings})},
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"docs {len(docs)}  classes {counts}  head {head} ({base_ref})")
        for d, rm in sorted(region_maps.items()):
            if rm["unowned_lines"]:
                print(f"  region: {d} — {rm['unowned_lines']} of {rm['lines']} lines "
                      f"hand-written (audit as Class D)")
        for k, v in report["summary"].items():
            print(f"  {k}: {v}")
        for f in findings:
            loc = f":{f['line']}" if f.get("line") else ""
            # Where the fix belongs, not just what is wrong. Without it a dead
            # link inside generated inventory reads exactly like an editable
            # prose finding, and the safety rule is never to edit a generated
            # region in place.
            where = (f" (region: {f['region']}, owner: {f['region_owner']})"
                     if f.get("region") else "")
            print(f"  [{f['severity']}] {f['check']}: {f['doc']}{loc}{where} — {f['detail']}")
        if stamped:
            acted = [s for s in stamped if s["action"] != "unchanged"]
            print(f"  stamped: {len(acted)} changed, {len(stamped) - len(acted)} unchanged")

    # --check gates on P1 and P2. P3 is the standing worklist: legacy lines a
    # human must merge, and documents nobody has reviewed yet. Both are real
    # and both are reported; neither is a reason to fail a build, and a gate
    # that can never go green is not a gate.
    if args.check and [f for f in findings if f["severity"] in {"P1", "P2"}]:
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AuditError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
