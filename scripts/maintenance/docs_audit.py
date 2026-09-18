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
import os
import pathlib
import posixpath
import re
import subprocess
import sys
import urllib.parse

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
_URI_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)

# A reference only counts as a staleness finding when the surrounding line
# presents it as live work. A changelog saying "fixed #123" is not a defect.
# Whole cues, not substrings. An unbounded alternation matched inside
# `nonblocking` and `not blocked by`, so a line stating an issue is NOT a
# blocker produced a P1 against it once it closed -- a finding whose own
# source line says the opposite. `\b` alone stops `nonblocking`; the negator
# scan in has_blocking_cue stops the spaced and hyphenated forms.
BLOCKING_CUE_RE = re.compile(
    r"\b(?:blocking|blocked by|open issues?|still open|outstanding|in progress"
    r"|not started|pending)\b",
    re.I,
)
# Text immediately before a cue that inverts it. `not started` is itself a cue,
# so what precedes THAT phrase is what is tested -- its own leading `not` is
# never read as negating the phrase it belongs to.
CUE_NEGATOR_RE = re.compile(r"\b(?:not|non|never|no longer|without|un)[\s-]*$", re.I)


def has_blocking_cue(line: str) -> bool:
    """Does this line cite live work?

    True when at least ONE cue occurrence is not negated: a line may say one
    issue still blocks and another no longer does.
    """
    return any(not CUE_NEGATOR_RE.search(line[:mm.start()])
               for mm in BLOCKING_CUE_RE.finditer(line))
# Prose that says a citation is finished. Checked against the citation's own
# clause, never the whole line: `docs/product/12-PR-ISSUE-TRACEABILITY.md:48`
# says three stocks records "are closed as not planned with the work still
# open in solyra", and the line-level cue applied "still open" to all five
# citations on it -- reporting truthful traceability history as stale docs.
# Whole words, and negation-aware. An unbounded alternation matched `resolved`
# inside `unresolved`, so `Outstanding: <url> remains unresolved` SETTLED the
# citation and a closed issue cited as live work produced no finding -- a
# suppression, which is the worse direction. Raised on the Node twin's
# blocking-cue equivalent first (solyra#69).
SETTLED_CUE_RE = re.compile(
    r"\b(?:closed|resolved|superseded|merged|moved to|relocated|duplicate of"
    r"|completed)\b", re.I)


def is_settled(clause: str) -> bool:
    """Does this clause say the citation is finished?

    True only when at least one settled cue is not negated: `not resolved` and
    `never merged` say the opposite of the word they contain.
    """
    return any(not CUE_NEGATOR_RE.search(clause[:mm.start()])
               for mm in SETTLED_CUE_RE.finditer(clause))
# What bounds a clause: sentence punctuation, a semicolon, or a table-cell
# edge. Not a comma -- the example above puts the closed and open halves in
# one comma-free clause pair separated by "with".
_CLAUSE_SPLIT_RE = re.compile(r"[.;|]")
# `\S+` is greedy and swallowed the punctuation AFTER a URL: on
# docs/product/12-PR-ISSUE-TRACEABILITY.md:98 it masked `.../pull/936).` up to
# and including the full stop, so citation_clause ran straight into the next
# sentence and picked up cues belonging to a different citation. A URL ends
# before trailing sentence punctuation.
# Not `\S*`: a table may omit padding (`| .../issues/1| still open ...|`), and
# swallowing the `|` merged adjacent cells -- so an issue described as no
# longer blocking inherited a live-work cue from the next one.
_URL_RE = re.compile(r"https?://[^\s|]*[^\s|.,;:!?)\]]")
# Case-insensitive, because GitHub resolves `teneikaaskew/Stocks` to the same
# repository and a document may cite it that way. The `i` flag ALONE would be
# worse than the bug: the captured name would index states["Stocks"], miss, and
# fabricate a "could not be resolved" P2 against a live issue. Both captures
# are lower-cased at the call site.
ISSUE_URL_RE = re.compile(
    r"github\.com/" + OWNER + r"/(?P<repo>solyra|stocks)/(?P<kind>issues|pull)/(?P<num>\d+)",
    re.I,
)
# The fragment is CAPTURED, not discarded. Dropping it meant a link to a real
# file but a heading that does not exist always passed -- 35 such links in this
# tree, including all 16 feature links in docs/product/02-FEATURE-CATALOG.md,
# whose targets in 12-PR-ISSUE-TRACEABILITY.md carry an em dash and a slash
# that GitHub's anchor rule turns into DOUBLED hyphens.
# The optional TITLE is admitted and discarded. `[guide](missing.md "Guide")`
# is standard CommonMark; requiring `)` straight after the destination meant
# the pattern did not match at all, so a missing target reported clean rather
# than dead. Raised on the Node twin (solyra#69).
MD_LINK_RE = re.compile(
    # One level of BALANCED parentheses in the destination: `guide(v2).md` is a
    # valid local link, and stopping at the first `)` validated `guide(v2` and
    # called a tracked file dead.
    r"\[[^\]]*\]\((?P<target>(?:[^()#\s]|\([^()\s]*\))*)(?:#(?P<frag>[^)\s]+))?"
    r"""(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\)""")
# Reference-style Markdown, both halves. The definition's label may not open
# with `^`: that is a footnote, which defines a note rather than a destination.
REF_DEF_RE = re.compile(r"^ {0,3}\[(?P<label>[^\]^][^\]]*)\]:\s+(?P<target>\S+)")
# A USE (`[text][label]`) is deliberately NOT checked. Measured over the 322
# markdown documents in this tree: 1 reference definition, 204 bracket pairs.
# Almost every pair is an issue-title tag -- `[P0][Replay]`, `[audit] R2 --` --
# which is indistinguishable from a full reference use, and flagging them
# produced 79 fabricated findings. The definition's destination is the half
# that certainly names a path, so that is the half this checks.
# A backticked path: has a slash and a file-ish extension, no spaces or globs.
# The trailing `:12` / `:88-102` is optional and part of the match: without it
# the closing backtick had to follow the extension, so every line-qualified
# citation failed to match at all and was never checked. There are 1,207 of
# them in this tree, `gcp/database.py:88-102` in CLAUDE.md among them, and a
# rename or deletion of any of those files produced no finding.
# The extension bound is 10, not 5. At 5 a citation of `docs/STRAT_ENGINE_ERD.drawio`
# did not match the pattern at all, so it was never checked -- though this tree
# tracks five `.drawio` files and `check_dead_links` derives its allowlist FROM
# the tree exactly so extensions like that are covered. The allowlist is what
# keeps the wider bound honest: an extension this tree does not track is
# skipped there, so widening the pattern adds reach, not false positives.
BACKTICK_PATH_RE = re.compile(
    r"`(?P<path>[A-Za-z0-9_./-]+/[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,10}"
    r"(?::\d+(?:-\d+)?)?)`")

# The `:line` or `:start-end` suffix above, which is a citation's coordinate
# inside the file and not part of its path.
LINE_SUFFIX_RE = re.compile(r":\d+(?:-\d+)?$")

CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".mjs", ".sql", ".sh", ".yml", ".yaml", ".json", ".md"}


_SLUG_STRIP_RE = re.compile(r"[^\w\s-]")
# `## Install ##` renders as `Install`, and GitHub's anchor is `install`.
# Passing `Install ##` to heading_slug recorded `install-`, so a valid link to
# `#install` was reported dead. Raised on the Node twin (solyra#69).
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)(?:\s+#+)?\s*$", re.M)


def heading_slug(heading: str) -> str:
    """GitHub's anchor for a heading.

    The order is what matters and what makes this worth a helper: GitHub
    lowercases, strips everything that is not a word character, space or
    hyphen, and THEN replaces each space with a hyphen. Runs are not
    collapsed. So `FEAT-AUTH-001 — Auth / security (8 open)` loses the em dash
    and the slash and keeps the spaces either side of them, giving
    `feat-auth-001--auth--security-8-open` with DOUBLED hyphens -- while the
    16 links pointing at it spell single ones. Collapsing whitespace here
    reproduces the links' spelling and would call every one of them valid.
    """
    s = re.sub(r"`([^`]*)`", r"\1", heading)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    # Emphasis MARKUP only. Stripping every underscore turned `## API_FIELD`
    # into `apifield`, so a valid link to `#api_field` read as a dead anchor
    # AND an incorrect `#apifield` was accepted -- wrong in both directions.
    # CommonMark does not treat an intraword `_` as emphasis.
    s = re.sub(r"\*", "", s)
    s = re.sub(r"(?<!\w)_+|_+(?!\w)", "", s).strip().lower()
    return _SLUG_STRIP_RE.sub("", s).replace(" ", "-")


def heading_anchors(text: str) -> set[str]:
    """Every anchor a document offers, duplicates numbered as GitHub does.

    The suffix ADVANCES until it is unused rather than following a per-base
    count, because GitHub disambiguates against everything already assigned.
    `## Notes` / `## Notes-1` / `## Notes` gives `notes-1` twice under a
    counter and never emits `notes-2`, which is what GitHub gives the third --
    so a valid link to it reads as dead, which is a FALSE finding and the
    direction that makes an audit untrustworthy rather than incomplete.
    """
    seen: dict[str, int] = {}
    out: set[str] = set()
    # A `# ` line inside a fence is CODE. Recording it invented an anchor, so a
    # link to a fragment the rendered document does not have PASSED the
    # dead-anchor check. Marker parsing already excludes fenced lines; the Node
    # twin already excluded them here.
    lines = text.split("\n")
    fenced = fenced_lines(lines) | commented_lines(lines)
    for i, line in enumerate(lines):
        if i in fenced:
            continue
        # Setext (`Title` over `===` or `---`) renders as a heading and
        # GitHub exposes its anchor, but an ATX-only scan recorded none -- so a
        # valid link to one was emitted as a gating dead-anchor finding.
        setext = (i + 1 < len(lines)
                  and is_setext_underline(lines, i + 1, fenced))
        m = _HEADING_RE.match(line)
        if not (m or setext):
            continue
        base = heading_slug(line.strip() if setext else m.group(1))
        n = seen.get(base, 0)
        slug = base if n == 0 else f"{base}-{n}"
        while slug in out:
            n += 1
            slug = f"{base}-{n}"
        seen[base] = n + 1
        out.add(slug)
    return out


def decode_fragment(frag: str) -> str:
    """The anchor a browser resolves, from the spelling a link carries.

    `#caf%C3%A9` is how a link to `## Caf\u00e9` is written, and it works;
    comparing the encoded spelling against the decoded slug reported it dead.
    `unquote` leaves an invalid escape (`100%-done`) exactly as it is, which is
    what makes this safe to apply to every fragment rather than guessing which
    ones are encoded.
    """
    return urllib.parse.unquote(frag)


def strip_dot_segments(path: str) -> str:
    """`./scripts/tool.py` and `scripts/tool.py` are the same repository path.

    Callers compare against `git ls-tree` output, which never carries a
    leading `./`, and split on the first `/` to find the top-level directory.
    Without this the root-relative form yields the component `.`.
    """
    while path.startswith("./"):
        path = path[2:]
    return path


def repo_relative(cited: str, doc: str) -> str | None:
    """A backticked citation as a repository path, or None if it leaves the repo.

    Three spellings reach here and only the first used to work:

      scripts/tool.py           repo-relative
      ./scripts/tool.py         root-relative, handled by strip_dot_segments
      ../../docs/API.md         relative to the CITING DOCUMENT's directory

    The third was left unchanged, checked as `REPO/../../docs/API.md`, and then
    discarded because its first component is `..` and never a tracked top-level
    directory -- so a deleted target produced no finding. Living documents use
    it: `docs/STRAT_ENGINE_OPERATIONS.md` and the incident records under
    `docs/product/` cite their siblings this way.

    A citation that climbs above the repository root is deliberate cross-repo
    prose, not rot, and returns None rather than a path this repo could never
    hold. The `:line` suffix is a coordinate inside the file, so it is removed
    before anything is resolved -- otherwise the extension reads as `.py:88`
    and the citation is skipped as an unknown file type.
    """
    cited = LINE_SUFFIX_RE.sub("", cited)
    if cited.startswith("../") or "/../" in cited:
        resolved = posixpath.normpath(
            posixpath.join(str(pathlib.PurePosixPath(doc).parent), cited))
        return None if resolved.startswith("..") else resolved
    return strip_dot_segments(cited)


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


# Long enough to be unambiguous in a repo this size and comfortably inside
# MARKER_RE's 7-40, whatever core.abbrev says locally.
MARKER_SHA_LEN = 12


def resolve_marker_sha(since: str | None, base_ref: str, runner=None) -> str:
    """The SHA a marker will carry: resolved by git, never taken on trust.

    Both inputs could otherwise produce a marker this module's own parser
    cannot read back -- `--short` under a low `core.abbrev`, and any `--since`
    value at all. A marker whose `Against:` does not match MARKER_RE loses that
    field AND the `Last scanned` field after it to the unmatched tail, so the
    review reads as never-recorded and drift stops being checked, both without
    a word. Round-tripping through the parser is the check, not the shape.
    """
    runner = runner or (lambda argv: run(argv))
    ref = since or base_ref
    sha = runner(["git", "rev-parse", f"--short={MARKER_SHA_LEN}",
                  "--verify", "--quiet", f"{ref}^{{commit}}"]).strip()
    if not sha:
        raise AuditError(
            f"--since {since}: not a commit this checkout can resolve. Nothing "
            "was written." if since else
            f"{ref} does not resolve to a commit; the marker would name nothing")
    # The whole line still MATCHES with a bad SHA, because `Against` is an
    # optional group -- it just captures nothing and swallows the rest of the
    # line. Round-tripping means the group has to come back holding the value
    # that went in, not that the line parsed.
    parsed = MARKER_RE.match(f"**Last reviewed:** unknown · **Against:** `{sha}`")
    if not parsed or parsed.group("sha") != sha:
        raise AuditError(
            f"the resolved SHA {sha!r} is not a form the marker parser reads "
            f"back (expects 7-40 hex characters); refusing to write it")
    # Resolvable is not the same as REVIEWABLE. A commit from another branch
    # resolves fine, and writing it into a marker records a review against
    # content this run never read: check_marker_sha calls the marker invalid on
    # the next run, and the drift range `sha..base_ref` is not a baseline at
    # all. Only checked for an explicit --since, because base_ref is trivially
    # its own ancestor.
    if since and subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, base_ref],
            cwd=REPO, capture_output=True).returncode != 0:
        raise AuditError(
            f"--since {since} resolves to {sha}, which is not an ancestor of {base_ref}; "
            "a marker naming it would record a review against content this run did not "
            "read, and the next run would report it invalid. Nothing was written.")
    return sha


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
            # A mistyped class was discarded in silence. If the document it
            # meant to cover also matches a broad fallback rule it is then
            # classified by THAT rule with no finding anywhere -- so a
            # fumbled Class A declaration can land as Class D and let the
            # audit stamp and route fixes into machine-generated content.
            # The header and its delimiter are the only rows that may be
            # skipped without comment.
            if cls in {"CLASS", ""} or set(cls) <= set("-: "):
                continue
            raise AuditError(
                f"{REGISTRY}: row for `{_cell(cells[1]) if len(cells) > 1 else cls}` "
                f"declares class {cls!r}, which is not one of A, B, C, D, X; a class "
                "the audit does not know is a declaration it cannot act on")
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
    # Two matching rows of EQUAL glob length never replace `best` in classify,
    # so the first wins by table order alone. A duplicate or equally long
    # overlapping glob can therefore park a document in Class B/X, suppress all
    # auditing of it, and leave the conflicting Class A/D declaration silently
    # ignored. Table order is not a decision.
    for path in sorted(tracked):
        matches = [r for r in registry if fnmatch.fnmatch(path, r["glob"])]
        if not matches:
            continue
        top = max(len(r["glob"]) for r in matches)
        tied = [r for r in matches if len(r["glob"]) == top]
        def _rule(r: dict) -> tuple:
            # What classify() hands the caller. Two tied rows agreeing on the
            # class but declaring different code paths still silently drop one
            # set: duplicate Class D rows naming `lib/a` and `lib/b` produced
            # no finding, and changes under `lib/b` could never trigger drift.
            return (r["cls"], tuple(r.get("code_paths") or ()),
                    tuple(r.get("regions") or ()))

        if len({_rule(r) for r in tied}) > 1:
            rules = ", ".join(sorted({"{} -> {}".format(r["glob"], r["cls"])
                                      for r in tied}))
            out.append({"check": "registry", "doc": path, "severity": "P1",
                        "detail": "two registry rules of equal specificity disagree about "
                                  f"this document ({rules}); classify() takes the first by "
                                  "table order, so the other declaration is ignored "
                                  "without a finding"})

    for row in registry:
        glob = row["glob"]
        if not any(c in glob for c in "*?["):
            if glob not in tracked:
                out.append({"check": "registry", "doc": glob, "severity": "P1",
                            "detail": "registry names this document exactly, but it is not in "
                                      "the audited tree -- it was deleted, moved, or never "
                                      "existed"})
        # A wildcard row covering nothing is the same failure one step out:
        # every document it named has been deleted, or the glob is mistyped.
        # Nothing reaches classify(), so the declaration goes inert and the
        # audit reports no registry finding while a whole rule quietly stops
        # applying. Matched against `tracked` with the same fnmatch classify
        # uses, so the two agree on what a glob covers.
        elif not any(fnmatch.fnmatch(path, glob) for path in tracked):
            out.append({"check": "registry", "doc": glob, "severity": "P1",
                        "detail": "registry declaration matches no tracked document, so the "
                                  "rule it carries covers nothing"})
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
            # A registry typo is bad INPUT. re.compile raises re.error, which
            # walks past the AuditError handler, so the CLI printed a traceback
            # and exited 1 -- the status it documents for findings. The Node
            # twin already made this split.
            if not spec[5:]:
                # `re.compile("")` succeeds and matches EVERY line, so the
                # region map called the whole document generated and valid:
                # the hand-written complement suppressed, stamping disabled,
                # every content finding routed to the renderer.
                raise AuditError(
                    f"registry region `{spec}` has no pattern; an empty one matches every "
                    "line and would claim the entire document as generated")
            try:
                pat = re.compile(spec[5:])
            except re.error as exc:
                raise AuditError(f"registry region `{spec}` is not a valid regular "
                                 f"expression: {exc}") from exc
            for n, line in enumerate(lines, 1):
                if pat.search(line):
                    owned.add(n)
                    hit = True
        elif spec.startswith("prose:") and prompt is not None \
                and spec[6:] != prompt:
            # A second, DIFFERENT prose owner: the later assignment silently
            # replaced the first, so the audit reported a valid region map,
            # suppressed every unowned span and routed all prose findings to
            # one prompt while the registry claimed two.
            unmatched.append(spec)
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
    specs consume it.

    Fenced lines are skipped. A document explaining the convention shows the
    marker pair in a code block, and reading that example as a real region put
    the renderer's ownership check on prose: the span was reported generated,
    a marker landing inside it was called unstampable, and the audit measured
    region drift against a code sample. Every other check here already skips
    fences for the same reason.
    """
    fenced = fenced_lines(lines)
    pairs: dict[str, tuple[int, int]] = {}
    unbalanced: list[str] = []
    open_at: dict[str, int] = {}
    for n, line in enumerate(lines, 1):
        if n - 1 in fenced:
            continue
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
    # A heading inside a FENCE is an example, not the next section. Treating it
    # as one ended the search early, so an existing marker below the fence was
    # reported missing and --stamp inserted a second one above it, leaving
    # contradictory provenance in the document.
    fenced = fenced_lines(lines) | commented_lines(lines)
    # To the next HEADING, with no additional line cap. A document opening
    # with more than `limit` lines of HTML metadata before its marker had the
    # real marker excluded from the window, so the audit reported it missing
    # and --stamp inserted a second one. The section boundary is the thing
    # being asked about; the line count was a proxy for it.
    stop = len(lines)
    for j in range(h1 + 1, len(lines)):
        if j in fenced:
            continue
        if lines[j].startswith("#"):
            stop = j
            break
        # Setext is a section heading too, and its underline marks the heading
        # written on the line ABOVE -- so the next section starts there, not at
        # the underline. Reading only `#` let a `Last reviewed` line inside
        # that section stand in for the whole document's provenance, which is
        # the `# PART A` defect above in the other heading syntax.
        if is_setext_underline(lines, j, fenced):
            stop = j - 1
            break
    return range(h1 + 1, min(stop, len(lines)))


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


# The field names MARKER_RE owns. Finding one in the unmatched tail means the
# optional group declined it, which is malformed provenance, not absence.
_MARKER_FIELD_RE = re.compile(r"\*\*(Depth|Against|Last scanned|Last reviewed):\*\*", re.I)


def check_marker_fields(doc: str, info: dict) -> list[dict]:
    """A field the parser recognised the NAME of but could not read.

    Every optional group in MARKER_RE declines silently: `**Against:** `zzzz``
    does not fail to parse, it captures nothing and `rest` absorbs that field
    AND everything after it. The document then reports only the non-gating P3
    "no reviewed-against SHA" worklist item, so `--check` passes while drift
    detection is disabled for it -- provenance that looks present to a reader
    and is invisible to the audit.

    resolve_marker_sha guards the WRITE side; this is the read side, which
    sees markers written by hand or by an older version of this script.
    """
    rest = info.get("rest") or ""
    names = sorted({m.group(1).lower() for m in _MARKER_FIELD_RE.finditer(rest)})
    if not names:
        return []
    return [{"check": "marker", "doc": doc, "severity": "P2",
             "detail": f"marker field(s) {', '.join(names)} could not be parsed and were "
                       f"read as free text ({rest.strip()[:60]!r}); the values they carry "
                       "are invisible to every check"}]


def check_marker_dates(doc: str, info: dict, today: str | None = None) -> list[dict]:
    """Every date a marker carries has to be a day that exists, and be past.

    P2, not P3: this is not an absent review, it is a recorded one that cannot
    be true. A date nobody can place is worse than `unknown`, which at least
    says so.

    The future check covers BOTH fields. It used to be applied to the review
    date only, at the call site, so `Last scanned: 2099-01-01` passed every
    check and the document reported clean provenance claiming a mechanical
    scan that has not happened. A scan date is the one field a machine writes,
    so a future value there means the clock or the file is wrong, never that
    somebody was optimistic.
    """
    out = []
    for field, label in (("date", "review date"), ("scanned", "last-scanned date")):
        value = info.get(field)
        if value in (None, "", "unknown"):
            continue
        if not is_calendar_date(value):
            out.append({"check": "marker", "doc": doc, "severity": "P2",
                        "detail": f"{label} {value} is not a real calendar day"})
        elif today is not None and is_future_date(value, today):
            out.append({"check": "marker", "doc": doc, "severity": "P1",
                        "detail": f"{label} {value} is in the future"})
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


_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")


def comment_spans(lines: list[str]) -> dict[int, list[tuple[int, int]]]:
    """Offset ranges inside an HTML comment, per line index.

    SPANS, not whole lines. A line-level rule cost a real finding on
    `docs/product/infrastructure/05-a-ARCHITECTURE.md:5`, which mentions
    `<!-- inventory:*:start/end -->` inside backticks as an EXAMPLE and carries
    an ordinary citation beside it: the balanced inline comment marked the
    whole line invisible and the dead link on it stopped being reported.

    ONE ordered scan, because a fence and a comment compete for the same text
    and whichever opens first wins until it closes. A code line cannot OPEN a
    comment -- `<!--` shown inside a code block is a sample -- but it CAN close
    one, because inside a comment nothing is code. Masking every fenced line
    wholesale looked equivalent and was not: the Node twin's
    docs/UI-SCREENS.md opens with a multi-line comment whose closing `-->` sits
    on an indented continuation line, so masking destroyed the closer, the
    comment ran to end of file, and five real closed-issue findings vanished.
    The findings diff is what caught it (solyra#69).

    A `<!--` inside an inline code span is not an opener either, which is what
    makes the 05-a line above parse right.
    """
    code = fenced_lines(lines) | indented_code_lines(lines)
    out: dict[int, list[tuple[int, int]]] = {}

    def add(i: int, a: int, b: int) -> None:
        if a < b:
            out.setdefault(i, []).append((a, b))

    open_at: tuple[int, int] | None = None
    for i, line in enumerate(lines):
        pos = 0
        while True:
            if open_at is None:
                if i in code:
                    break
                spans = code_spans(line)
                a = line.find("<!--", pos)
                while a >= 0 and any(lo <= a < hi for lo, hi in spans):
                    a = line.find("<!--", a + 1)
                if a < 0:
                    break
                open_at = (i, a)
                pos = a + 4
            else:
                frm = open_at[1] if open_at[0] == i else 0
                b = line.find("-->", pos if open_at[0] == i else 0)
                if b < 0:
                    add(i, frm, len(line))
                    break
                add(i, frm, b + 3)
                open_at = None
                pos = b + 3
    return out


def commented_lines(lines: list[str]) -> set[int]:
    """Line indices ENTIRELY inside an HTML comment, which renders as nothing.

    A marker-shaped line inside `<!-- ... -->` was accepted as the document's
    provenance, so the missing-marker check passed and --stamp rewrote the line
    in place -- still inside the invisible comment. The command reported
    success and the document still had no rendered review marker.

    Whole-line, because that is the question a marker or an H1 asks. A line
    with a comment in the MIDDLE of it still renders, and the link checks use
    comment_spans so they can skip the commented part and read the rest.
    """
    spans = comment_spans(lines)
    out: set[int] = set()
    for i, line in enumerate(lines):
        stop = len(line.rstrip())
        for a, b in spans.get(i, []):
            if a == 0 and b >= stop:
                out.add(i)
                break
    return out


def indented_code_lines(lines: list[str]) -> set[int]:
    """Indices inside a four-space-indented code block.

    CommonMark's other code form, which `fenced_lines` does not see: an example
    written that way was inspected as live prose, so `[demo](missing.md)` or a
    backticked path in it could fail --check over content that renders as code.

    Deliberately narrow. Indented code cannot interrupt a paragraph, and inside
    a list item the indentation is the LIST's -- so a run starts only after a
    blank line whose own preceding content is neither a list item nor a table
    row. Anything less careful masks list continuations and turns real findings
    invisible, which is the worse direction. Ported from the Node twin
    (solyra#69).
    """
    out: set[int] = set()
    last_content: str | None = None
    blank_seen = True
    in_code = False
    for i, line in enumerate(lines):
        if not line.strip():
            blank_seen = True
            continue
        indented = bool(re.match(r"^ {4,}\S", line) or line.startswith("\t"))
        if in_code and indented:
            out.add(i)
            continue
        in_code = False
        if indented and blank_seen and not (
                last_content is not None
                and re.match(r"^\s*([-*+]|\d+[.)]|\|)", last_content)):
            in_code = True
            out.add(i)
        last_content = line
        blank_seen = False
    return out


def fenced_lines(lines: list[str]) -> set[int]:
    """Indices inside a fenced code block, which are examples, not content.

    The OPENING delimiter is remembered. Toggling on any fence-looking line
    meant a `~~~` inside a ``` example closed the block there, so the rest of
    the example read as prose and the prose after the real closing fence read
    as code -- false findings and suppressed ones from one line. CommonMark: a
    fence closes only on the same character, at least as long, with no info
    string. Raised on the Node twin (solyra#69).
    """
    out: set[int] = set()
    open_fence: str | None = None
    for i, line in enumerate(lines):
        m = _FENCE_RE.match(line)
        if open_fence is None:
            # An opening ``` fence may not carry a backtick in its info string.
            if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
                open_fence = m.group(1)
                out.add(i)
            continue
        out.add(i)
        if (m and m.group(1)[0] == open_fence[0]
                and len(m.group(1)) >= len(open_fence) and not m.group(2).strip()):
            open_fence = None
    return out


def find_markers(lines: list[str]) -> list[tuple[int, dict]]:
    """Every marker in the window, not just the first.

    `find_marker` stops at the first match, which is the right answer for
    reading a document's provenance and the wrong one for judging it: a second
    marker sitting immediately below carries a different date or SHA, and
    nothing said so. `--stamp --verify` would rewrite the first, return
    `unchanged` or `updated`, accept the target, and leave the contradiction
    in place -- a document that states two different review claims and passes.
    """
    out = []
    fenced = fenced_lines(lines)
    # A marker inside `<!-- ... -->` is invisible to every reader. Accepting it
    # passed the missing-marker check, and --stamp then rewrote the line still
    # inside the comment: the command reported success over a document with no
    # rendered provenance at all.
    commented = commented_lines(lines)
    for i in marker_window(lines):
        # An INDENTED marker-shaped line is an example of a marker, not the
        # document's provenance -- and stripping before matching threw away
        # the only thing that distinguishes them. A sample in the opening
        # section counted as the marker, suppressed the real missing-marker
        # finding, and `--stamp` then REPLACED the example with an unindented
        # live marker: a write straight through this module's one hard rule.
        # Fenced blocks are excluded for the same reason.
        if i in fenced or i in commented or (lines[i] and lines[i][0].isspace()):
            continue
        line = lines[i].strip()
        m = MARKER_RE.match(line)
        if m:
            out.append((i, {"date": m.group("date"), "depth": m.group("depth"),
                            "sha": m.group("sha"), "scanned": m.group("scanned"),
                            "rest": m.group("rest"), "legacy": False}))
            continue
        m = LEGACY_MARKER_RE.match(line)
        if m:
            out.append((i, {"date": m.group("date"), "depth": None, "sha": None,
                            "scanned": None, "legacy": True,
                            "bare": legacy_tail_is_bare(m.group("rest"))}))
    return out


def find_marker(lines: list[str]) -> tuple[int, dict] | None:
    found = find_markers(lines)
    return found[0] if found else None


# `-` needs two or more: a single `-` under text is a list bullet's sibling far
# more often than a heading, and CommonMark's own `---` case is covered.
_SETEXT_UNDERLINE_RE = re.compile(r" {0,3}(?P<rule>=+|-{2,})\s*")


def is_setext_underline(lines: list[str], i: int,
                        fenced: frozenset[int] | set[int] = frozenset()) -> bool:
    """Does line `i` underline a Setext heading written on line `i - 1`?

    Three things are NOT one: a thematic break (`---` after a blank line, with
    no heading text above it), a table's delimiter row (`|---|---|`, which the
    pattern rejects outright), and a real underline. The line above is what
    separates them.
    """
    if i <= 0 or i in fenced or (i - 1) in fenced:
        return False
    if not _SETEXT_UNDERLINE_RE.fullmatch(lines[i] or ""):
        return False
    above = lines[i - 1] or ""
    return bool(above.strip()) and not above.lstrip().startswith("#")


def h1_index(lines: list[str]) -> int | None:
    """Index of the first H1.

    Not a fixed line number on purpose: several docs open with an HTML comment
    and carry their H1 on line 9, where a line-3 insert lands inside the
    comment. A doc with no H1 is skipped by the caller entirely.
    """
    # A fenced `# Example` before the real title was returned as the H1, so
    # --stamp inserted the provenance marker INSIDE the code block: the example
    # was rewritten and the document left effectively unstamped.
    fenced = fenced_lines(lines) | commented_lines(lines)
    for i, line in enumerate(lines):
        if i in fenced:
            continue
        if H1_RE.match(line):
            return i
        # Setext level one (`Title` over `===`). Without it the audit reported
        # a missing marker on such a document while --stamp answered
        # `skipped-no-h1`, so the command could not repair its own finding.
        if (line.strip() and not line.lstrip().startswith("#")
                and i + 1 < len(lines) and (i + 1) not in fenced
                and re.fullmatch(r" {0,3}=+\s*", lines[i + 1] or "")):
            return i
    return None


def marker_anchor(lines: list[str]) -> int | None:
    """The line a new marker goes AFTER, which is not always the H1's line.

    A Setext H1 is TWO lines -- the title and its `===` underline -- so
    inserting after the title splits the heading in half and leaves the
    document with no H1 at all: `h1_index` returns None for the result. That is
    strictly worse than the `skipped-no-h1` this recognizer replaced, because
    it corrupts the document instead of declining to touch it.
    """
    h1 = h1_index(lines)
    if h1 is None:
        return None
    if h1 + 1 < len(lines) and re.fullmatch(r" {0,3}=+\s*", lines[h1 + 1] or ""):
        return h1 + 1
    return h1


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
    h1 = marker_anchor(lines)
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

# The only values `check_closed_issues` branches on. "Any string" is not
# enough: it reads `st["state"] == "closed"` and falls through everything else,
# so a row reading `bogus` silently drops a cited blocker from the report -- the
# same clean-bill-of-health failure the row check above exists to stop, one
# value in. GitHub's issues API returns exactly these two.
ISSUE_STATES = frozenset({"open", "closed"})


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
        # An empty map is not "a repository with no open work": fetch_issue_states
        # refuses to report on a repository that returned zero issues, and the
        # snapshot path may not be laxer than the live path it stands in for.
        # Accepting `{}` turns every citation of that repo into a fabricated
        # "could not be resolved" P2 and exits 1 for findings that do not
        # exist (CLAUDE.md §3.7).
        if not rows:
            raise AuditError(f'--issues-snapshot {file} has an empty "{repo}" map; the '
                             "live read refuses to report on zero issues and a snapshot "
                             f"may not either -- every {repo} citation would become a "
                             'fabricated "could not be resolved" finding')
        # Numeric keys are not enough. `check_closed_issues` reads st["state"]
        # once it has decided the row is not None, so a row with no state
        # raises KeyError -- a traceback and exit 1, the status that means
        # "this documentation has findings". A `null` row is worse: it takes
        # the `st is None` branch and reports a live issue as unresolvable,
        # fabricating a finding from a malformed file (CLAUDE.md §3.7).
        for num, rec in sorted(rows.items()):
            if not isinstance(rec, dict) or rec.get("state") not in ISSUE_STATES:
                raise AuditError(
                    f"--issues-snapshot {file}: {repo}#{num} has no usable state "
                    f"({rec!r}); expected one of {sorted(ISSUE_STATES)}. A row the "
                    "audit cannot read is not a row it may report on")
        states[repo] = rows
    return states


ISSUE_PAGE_SIZE = 100
# A runaway guard, not a ceiling on real data: 100,000 issues and PRs is far
# past anything either repo can hold, and reaching it raises rather than
# truncating.
ISSUE_PAGE_GUARD = 1000


def fetch_issue_states(repo: str) -> dict[int, dict]:
    """One paginated read per repo, never one call per reference (Rule 0)."""
    states: dict[int, dict] = {}
    # No arbitrary ceiling. `range(1, 40)` stopped at 3,900 combined issues and
    # PRs and said nothing, so every older cited blocker past that point would
    # read as "could not be resolved" -- fabricated findings from a silent cap,
    # which is the shape this module refuses everywhere else. The loop ends on
    # a short or empty page, which is the real end of the data; the counter is
    # only a runaway guard and is reported if it ever fires.
    page = 0
    while True:
        page += 1
        out = run([
            "gh", "api",
            f"repos/{OWNER}/{repo}/issues?state=all&per_page={ISSUE_PAGE_SIZE}&page={page}",
            "--jq", '.[] | [.number, .state, (.state_reason // ""), '
                    '(if .pull_request then "PR" else "ISSUE" end)] | @tsv',
        ])
        rows = [r for r in out.strip().split("\n") if r.strip()]
        for row in rows:
            parts = row.split("\t")
            if len(parts) != 4:
                continue
            states[int(parts[0])] = {"state": parts[1], "reason": parts[2], "kind": parts[3]}
        if len(rows) < ISSUE_PAGE_SIZE:
            break
        if page >= ISSUE_PAGE_GUARD:
            # Loud, not silent. The old ceiling truncated and carried on; a
            # guard that fires means the assumption behind it is wrong and the
            # result cannot be trusted, which is exit 2, not a short answer.
            raise AuditError(
                f"{repo}: still reading issues after {ISSUE_PAGE_GUARD} pages "
                f"({len(states)} so far); refusing to report on a truncated read")
    if not states:
        raise AuditError(f"no issues returned for {repo}; refusing to report a clean run on no data")
    return states


# ── checks ──────────────────────────────────────────────────────────────────

def citation_clause(line: str, start: int, end: int) -> str:
    """The clause a citation sits in, for judging what the prose says about IT.

    A cue evaluated once per line is applied to every citation on it, which
    turns mixed-status prose into false findings. The clause is bounded by
    sentence punctuation, a semicolon or a table-cell pipe, so each citation is
    read against the words around it rather than the words around its
    neighbours.
    """
    # URLs are masked first, at the same length so the offsets still line up.
    # Every citation IS a URL containing dots, so splitting the raw line cuts
    # each clause inside `github.com` and the prose around the citation --
    # which is the only thing being asked about -- falls outside it.
    masked = _URL_RE.sub(lambda m: "\x00" * len(m.group(0)), line)
    lo = max((m.end() for m in _CLAUSE_SPLIT_RE.finditer(masked, 0, start)), default=0)
    nxt = _CLAUSE_SPLIT_RE.search(masked, end)
    return line[lo:nxt.start() if nxt else len(line)]


def cites_live_work(line: str, start: int, end: int) -> bool:
    """Is THIS citation cited as live work?

    A line-level answer put every URL on the line under one verdict, so
    `#1 is no longer blocking; #2 is still open` gave #1 a P1 from #2's cue.
    The clause decides when it carries a cue at all; otherwise the line does,
    because a table row puts the cue and the citations in different cells --
    `| Open issues | #838 · #839 |` is a real finding whose citations sit in a
    clause with no cue of its own. Raised on the Node twin (solyra#69).
    """
    clause = citation_clause(line, start, end)
    if SETTLED_CUE_RE.search(clause) and is_settled(clause):
        return False
    if BLOCKING_CUE_RE.search(clause):
        return has_blocking_cue(clause)
    return has_blocking_cue(line)


def check_closed_issues(doc: str, text: str, states: dict[str, dict]) -> list[dict]:
    out = []
    lines = text.split("\n")
    # --check gates on these findings, so a document DEMONSTRATING what a
    # blocking citation looks like failed the audit over its own example. The
    # link, heading and marker checks already skip fenced lines.
    fenced = fenced_lines(lines)
    # And commented-OUT text, which is how a blocker list is retired without
    # losing it: the prose no longer renders, but it still held the build red.
    # Span-based rather than whole-line, matching check_dead_links -- a row
    # retired with a trailing `<!-- superseded: ... -->` is the common shape,
    # and a whole-line rule cannot see it.
    commented = comment_spans(lines)
    for n, line in enumerate(lines, 1):
        if n - 1 in fenced:
            continue
        if not has_blocking_cue(line):
            continue
        hidden = commented.get(n - 1, [])
        for m in ISSUE_URL_RE.finditer(line):
            if any(lo <= m.start() < hi for lo, hi in hidden):
                continue
            # The line carries a live-work cue; does THIS citation's clause say
            # the opposite? Both cue families are read against the clause now
            # (see cites_live_work), with the line as the fallback when the
            # clause carries no cue of its own.
            if not cites_live_work(line, m.start(), m.end()):
                continue
            # A pull request cited as a blocker is live work too. `/pull/`
            # used to be skipped outright, so a document calling PR #937 the
            # open candidate stayed clean after #937 closed -- though the
            # issue-state read already carries PR rows and their state. The
            # blocking-cue filter above is what keeps ordinary PR lineage
            # ("fixed in #123") out. The Node twin made this change first.
            is_pr = m.group("kind").lower() == "pull"
            # A PR needs a cue in its OWN clause; the line-level fallback does
            # not extend to it. Measured on docs/product/12-PR-ISSUE-TRACEABILITY.md:
            # the fallback attributed a row's cue to whichever PR shared the
            # row, producing four findings whose own source line says the
            # opposite -- `| #816 | #933 | merged default-no-op mechanism |
            # ... outstanding |` is accurate prose about a merged PR. Issues
            # keep the fallback: it is what reports stocks#838 under
            # `| Open issues | ... |`, where the cue IS the row label.
            if is_pr and not BLOCKING_CUE_RE.search(
                    citation_clause(line, m.start(), m.end())):
                continue
            repo, num = m.group("repo").lower(), int(m.group("num"))
            label = f"{repo}#{num}" + (" (PR)" if is_pr else "")
            st = states.get(repo, {}).get(num)
            if st is None:
                out.append({"check": "closed-issue", "doc": doc, "line": n,
                            "detail": f"{label} could not be resolved", "severity": "P2"})
            elif st["state"] == "closed":
                reason = st.get("reason") or ("closed" if is_pr else "completed")
                out.append({"check": "closed-issue", "doc": doc, "line": n,
                            "detail": f"{label} is CLOSED ({reason}) but cited as live work",
                            "severity": "P1" if reason != "not_planned" else "P2",
                            "ref": f"{repo}#{num}", "reason": reason})
    return out


def is_tracked_dir(tracked: set[str], norm: str) -> bool:
    """Does any tracked path live under this one? Then it is a real directory.

    Filesystem existence is only allowed to answer THIS question. git tracks
    no directories, which is the sole reason the existence check was there --
    and using it for files let an ignored or generated file, or one recreated
    after a staged deletion, satisfy a link that is broken in every clean
    clone. Codex raised this on the Node twin first (solyra#69).
    """
    prefix = f"{norm}/"
    return any(p.startswith(prefix) for p in tracked)


_CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)")


def code_spans(line: str) -> list[tuple[int, int]]:
    """Offset ranges of inline code spans, CommonMark's backtick-run rule.

    A run of N backticks opens a span that only a run of exactly N closes, so
    ``` ``a ` b`` ``` is one span rather than two.
    """
    return [(m.start(), m.end()) for m in _CODE_SPAN_RE.finditer(line)]


def check_dead_links(doc: str, text: str, tracked: set[str]) -> list[dict]:
    out = []
    # Every extension this tree actually tracks. CODE_EXTS is the floor, so a
    # rename that empties an extension out of the tree does not make its
    # citations silently uncheckable.
    cited_exts = CODE_EXTS | {pathlib.PurePosixPath(p).suffix for p in tracked
                              if pathlib.PurePosixPath(p).suffix}
    base = pathlib.PurePosixPath(doc).parent
    anchors: dict[str, set[str] | None] = {}

    def anchors_of(path: str) -> set[str] | None:
        if path not in anchors:
            try:
                anchors[path] = heading_anchors(
                    (REPO / path).read_text(encoding="utf-8", errors="replace"))
            except OSError:
                anchors[path] = None
        return anchors[path]

    def check_target(tgt: str, frag: str | None, n: int, label: str | None = None) -> None:
        """One destination, validated the way an inline link's is.

        Reference-style definitions resolve to the same tracked paths and the
        same anchors; a different spelling must not buy a laxer check.
        """
        what = (f"relative link -> {tgt}" if label is None
                else f"reference link [{label}] -> {tgt}")
        anchor_what = f"link -> {tgt}" if label is None else what
        # Any scheme, case-insensitively, plus a protocol-relative `//host/x`.
        # A narrow `http|https|mailto` allowlist sent `tel:`, `ftp:`, `HTTPS:`
        # and `//example.com/x` down the repository-path branch and produced a
        # P2 for a file never meant to exist locally.
        if _URI_SCHEME_RE.match(tgt) or tgt.startswith("//"):
            return
        if not tgt:
            # `[x](#heading)` -- same document, so the anchor is still
            # checkable even though there is no path to resolve.
            norm = doc
        else:
            # normpath, not PurePosixPath: the latter keeps `..` segments
            # verbatim, and the old code leaned on the filesystem to
            # resolve them. Requiring a tracked target exposed that --
            # `.github/workflows/README.md` linking `../../docs/...`
            # produced `.github/workflows/../../docs/...`, which is in no
            # tracked set, and 3,259 live links reported as dead.
            # Markdown percent-encodes spaces and other path characters, and
            # git reports the DECODED filename, so `Morning%20Checklist.md` was
            # compared against a tracked `Morning Checklist.md` and reported
            # dead. The original spelling stays in the message.
            # `[g](<guide.md>)` is the standard form for a destination with a
            # space, and the angle brackets are delimiters. A query string is
            # not part of the path either: the tracked lookup searched for the
            # literal `guide.md?plain=1`.
            bare = tgt[1:-1] if tgt.startswith("<") and tgt.endswith(">") else tgt
            bare = bare.split("?")[0]
            if not bare:
                return
            decoded = urllib.parse.unquote(bare)
            resolved = (decoded.lstrip("/") if decoded.startswith("/")
                        else posixpath.join(str(base), decoded))
            norm = posixpath.normpath(resolved)
            if norm.startswith(".."):
                # Climbs out of the repository: cross-repo prose, which
                # this repo cannot resolve and must not call rot.
                return
            if norm not in tracked and not is_tracked_dir(tracked, norm):
                out.append({"check": "dead-link", "doc": doc, "line": n,
                            "detail": what, "severity": "P2"})
                return
        # The target resolves; does the heading it names?
        if frag and norm.endswith(".md"):
            have = anchors_of(norm)
            # The fragment as the BROWSER resolves it. `#caf%C3%A9` is the
            # ordinary spelling of a link to `## Cafe\u0301`, and comparing the
            # encoded form against the decoded slug reported a working link
            # dead -- the false direction, which is the one that makes an audit
            # untrustworthy rather than merely incomplete.
            if have is not None and decode_fragment(frag).lower() not in have:
                out.append({"check": "dead-anchor", "doc": doc, "line": n,
                            "detail": f"{anchor_what}#{frag}: the target has no "
                                      "such heading",
                            "severity": "P2"})

    lines = text.split("\n")
    # Retired Markdown kept in an HTML comment is not rendered, so it is not a
    # citation: `<!-- [old](deleted.md) -->` produced a gating dead-link
    # finding over content no reader can see. Applies to the backticked pass
    # in the same loop, for the same reason.
    # A fenced block is an EXAMPLE, not a citation. A document demonstrating
    # Markdown syntax with `[x](missing.md)`, or showing a path that has since
    # moved, was read as rendered documentation and failed --check over its own
    # teaching material. The marker and heading checks already skip these.
    # Four-space-indented blocks are code too, and this repo's documents use
    # that form for examples: without it `    [demo](missing.md)` was read as a
    # rendered link. See indented_code_lines for why the rule is narrow.
    fenced = fenced_lines(lines) | indented_code_lines(lines)
    # Retired Markdown kept in a comment is not rendered, so it is not a
    # citation -- but only the commented SPAN is invisible, not the line.
    commented = comment_spans(lines)

    # Reference-style Markdown: `[guide][g]` with `[g]: docs/guide.md` further
    # down. Neither shape matches MD_LINK_RE, so a broken reference link -- the
    # form CommonMark calls standard and readers see as an ordinary link --
    # produced a clean audit. The DEFINITION's destination is validated exactly
    # as an inline link's is. A footnote (`[^1]: ...`) is excluded: it defines
    # a note, not a destination. A
    # A use is excluded too -- see REF_USE_RE for the measurement that says
    # bracketed prose in this corpus cannot be told apart from one.
    ref_defs: dict[str, tuple[str, int]] = {}
    for n, line in enumerate(lines, 1):
        if n - 1 in fenced or (n - 1) in commented and any(
                a == 0 for a, _ in commented[n - 1]):
            continue
        rm = REF_DEF_RE.match(line)
        # The FIRST definition wins, as Markdown renders it. Overwriting with
        # the last meant `[g]: missing.md` followed by `[g]: good.md` rendered
        # as a broken link while the audit validated only `good.md`.
        if rm:
            ref_defs.setdefault(rm.group("label").strip().lower(),
                                (rm.group("target").strip("<>"), n))
    for label, (target, n) in ref_defs.items():
        tgt, _, frag = target.partition("#")
        check_target(tgt, frag or None, n, label)
    for n, line in enumerate(lines, 1):
        if n - 1 in fenced:
            continue
        # Link SYNTAX shown as inline code or escaped is rendered literally,
        # not as a link: `` `[x](missing.md)` `` and `\[x](missing.md)` both
        # display the brackets. Scanning them produced gating dead-link
        # findings over a document's own syntax examples. Only this pass is
        # masked -- the backtick pass below needs those code spans, because a
        # backticked path IS its subject.
        spans = code_spans(line) + commented.get(n - 1, [])
        for m in MD_LINK_RE.finditer(line):
            if any(lo <= m.start() < hi for lo, hi in spans):
                continue
            if m.start() and line[m.start() - 1] == "\\":
                continue
            check_target(m.group("target"), m.group("frag"), n)
        hidden = commented.get(n - 1, [])
        for m in BACKTICK_PATH_RE.finditer(line):
            if any(lo <= m.start() < hi for lo, hi in hidden):
                continue
            cited = m.group("path")
            # Root-relative, parent-relative and line-qualified spellings all
            # name the same repository file as the plain form; see
            # repo_relative for what each one used to do instead.
            p = repo_relative(cited, doc)
            if p is None:
                continue
            # The allowlist is derived from the tree, not fixed. A hardcoded
            # set skipped a citation of `notebooks/strat_pred_diagnose.ipynb`
            # entirely, so deleting that notebook produced no finding though
            # `notebooks` is plainly one of this repo's directories.
            if pathlib.PurePosixPath(p).suffix not in cited_exts:
                continue
            if p in tracked or is_tracked_dir(tracked, p):
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


# Four, not seven: `%h` honours `core.abbrev`, and git's own floor is 4. Below
# seven the header line was rejected, so every name-status line after it was
# attributed to no commit and real code drift produced no finding at all. The
# log format below asks for `%H` so this does not depend on local config; the
# range is widened as well because the parser is public and is handed output
# the caller produced. No status line can collide: `--name-status` emits a
# letter or `R###`, and `R` is not a hex digit.
_DRIFT_HEADER_RE = re.compile(r"^[0-9a-f]{4,40}\t")
_DRIFT_STATUS_RE = re.compile(r"^([AMDRCT])(\d{3})?\t")


def _touches(status_line: str, paths: list[str]) -> bool:
    """Does this `--name-status` line name one of the declared paths?

    Both sides of a rename count: `R100 old.py new.py` is about the declared
    path whichever end carries it.
    """
    for cell in status_line.split("\t")[1:]:
        cell = cell.strip()
        if any(cell == p or cell.startswith(f"{p}/") for p in paths):
            return True
    return False


def drift_commits(out: str, paths: list[str] | None = None) -> list[str]:
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
        # The query may have been widened to a containing directory so rename
        # pairs survive (see check_doc_changed_since); the answer is narrowed
        # back here, so a commit that touched only a sibling file is not drift.
        if paths is not None and not _touches(line, paths):
            continue
        kind, score = status.group(1), status.group(2)
        if kind in "AMDT" or (kind == "R" and int(score or 100) < 100):
            commits[-1] = (commits[-1][0], True)
    return [line for line, drift in commits if drift]


def path_in_commit(sha: str, doc: str, *, cwd: pathlib.Path | None = None) -> bool:
    """Does this commit contain this path?

    `run(["git", "show", f"{sha}:{doc}"])` cannot answer it: the command exits
    128 for a path the commit lacks and returns an empty string, which is the
    same value an empty file gives. The two need telling apart, because one of
    them means the whole drift check is unmeasurable.
    """
    return subprocess.run(["git", "cat-file", "-e", f"{sha}:{doc}"],
                          cwd=cwd or REPO, capture_output=True).returncode == 0


def check_doc_changed_since(doc: str, sha: str | None, base_ref: str, *,
                           cwd: pathlib.Path | None = None) -> list[dict]:
    """Has the DOCUMENT itself changed since it was reviewed?

    The drift check queries the declared code paths only, so prose rewritten
    after its `Against` SHA kept the old review date and SHA -- and a registry
    row with an empty declared-path column could never produce a drift finding
    at all, whatever happened to the document.

    Marker-only edits are excluded rather than filtered per commit: the marker
    line is what `--stamp` rewrites on every scheduled run, so counting it
    would mark every document stale the moment the weekly scan touched it.
    Comparing the two texts with their marker lines removed answers the real
    question in one `git show`, and needs no per-commit diff inspection.
    """
    if not sha:
        return []
    # A baseline the document predates is not "no drift": `git show` exits 128,
    # `run` returns "", and reading that as clean let a document claim, for as
    # long as the marker stood, a verification against a revision in which it
    # did not exist -- with its drift check silently never running again.
    # `--stamp --verify` no longer writes such a SHA (see main); one already on
    # disk, or a document since renamed, is reported here.
    if not path_in_commit(sha, doc, cwd=cwd):
        return [{"check": "changed-since", "doc": doc, "severity": "P2",
                 "detail": f"the document does not exist at {sha}, so its review "
                           "names a baseline predating it and drift cannot be measured"}]
    old = run(["git", "show", f"{sha}:{doc}"], cwd=cwd, ok_exit_codes=(128,))
    try:
        new = (REPO / doc).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if _without_marker(old) == _without_marker(new):
        return []
    return [{"check": "changed-since", "doc": doc, "severity": "P2",
             "detail": f"the document itself changed since {sha}, so its review covers "
                       "prose that is no longer there"}]


def _without_marker(text: str) -> str:
    """The text a review is about: the marker's OWN fields removed, nothing else.

    Deleting the whole line deleted the content sharing it. `stamp` deliberately
    preserves extra segments -- 09-SECURITY-AUTH's `Trust status`, 10's
    `Status`, a planning caveat each in 13 and 14 -- because they are real
    prose a review is about. Dropping them here made a change to any of them
    invisible to the drift check, which is a silent fallback in the direction
    that matters: it reports a document current over content that moved.
    """
    lines = text.split("\n")
    found = find_marker(lines)
    if found is not None:
        i = found[0]
        extras = extra_segments(lines[i]) if not found[1].get("legacy") else []
        end = i + 1
        if end < len(lines) and not lines[end].strip():
            end += 1
        keep = [f" {DOT} ".join(extras)] if extras else []
        lines = lines[:i] + keep + lines[end:]
    # And every blank between the H1 and the first content line, on BOTH sides
    # of the comparison. `stamp` inserts the marker with a blank after it, and
    # with one BEFORE it as well when the document had none -- and the two
    # cases produce byte-identical output, so the stamped text cannot say which
    # happened. Normalising that run away is what makes `# T\n\nbody` and
    # `# T\nbody` compare equal once each has been stamped, which is the only
    # question this function is asked.
    h1 = h1_index(lines)
    if h1 is not None:
        j = h1 + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        lines = lines[:h1 + 1] + lines[j:]
    return "\n".join(lines)


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
    # Rename detection needs BOTH sides of the pair in the diff, and a
    # path-limited log drops the old one: after a pure `git mv old.py new.py`,
    # `git log -- new.py` reports `A new.py` rather than `R100 old.py new.py`,
    # so drift_commits called a pure rename content drift -- the one case the
    # R100 rule exists to exclude. Querying the containing DIRECTORY keeps the
    # pair intact, and the status lines are filtered back to the declared paths
    # afterwards, so the widened query never widens the answer.
    scopes = sorted({p if not posixpath.splitext(p)[1] else (posixpath.dirname(p) or ".")
                     for p in code_paths})
    out = run(["git", "log", "--format=%H%x09%s", "--name-status", "-M",
               # T as well: git files a regular-file-to-symlink conversion as a
               # TYPE change, and AMDR dropped the commit before drift_commits
               # could look at it -- so replacing a declared implementation path
               # with a symlink changed the surface and queued no review.
               "--diff-filter=AMDRT", f"{sha}..{base_ref}", "--"] + scopes,
              cwd=cwd or REPO)
    commits = drift_commits(out, code_paths)
    if not commits:
        return []
    return [{"check": "changed-since", "doc": doc,
             "detail": f"{len(commits)} content commit(s) to {', '.join(code_paths)} since {sha}",
             "severity": "P2", "commits": commits[:10]}]


TOP_LEVEL_DIRS: set[str] = set()

# The job that owns the Class A docs, and the PR title it opens.
OWNING_JOB = {
    "workflow": "refresh-architecture-docs.yml",
    # Broad, for ATTEMPTS: "Fix: Monthly architecture doc refresh failed" is a
    # failed attempt and belongs on the report.
    "pr_title_re": re.compile(r"architecture doc refresh", re.I),
    # Strict, for DELIVERIES. The workflow's own output PR is titled
    # `Monthly architecture doc refresh: YYYY-MM`; the broad pattern also
    # matches maintenance like "fix architecture doc refresh authentication",
    # and `delivered` was computed from every merged match -- so merging a
    # workflow REPAIR could supersede and hide a refresh that never delivered
    # a document.
    "delivery_title_re": re.compile(r"Monthly architecture doc refresh:\s*\d{4}-\d{2}",
                                    re.I),
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


def fetch_owned_prs(title_re: re.Pattern, *, page_size: int = PR_PAGE_SIZE,
                    delivery_re: re.Pattern | None = None) -> list[dict]:
    """Every refresh PR the delivery check can act on, newest first.

    One `per_page=100` page covers the 100 newest PRs of ANY kind, not the 100
    newest refresh PRs. Measured on this repo on 2026-09-18: page 1 reaches
    #1130 down to #959, a 15-day window, and the refresh PR that actually
    delivered -- #953, merged 2026-09-02 -- is on page 2. The single-page
    lookup therefore saw no delivery at all, so the supersede rule could not
    fire and three long-superseded failed attempts stayed on the report.

    The walk used to stop at the FIRST merged refresh PR, on the reasoning that
    everything older is created before `delivered` and skipped by the supersede
    rule anyway. That confuses two orderings. The pages are sorted by CREATION
    time; `delivered` is a MERGE time. A refresh PR created in August can merge
    after one created in September, so the newest delivery can sit on a page
    the walk never reached -- and the attempts it superseded are then reported
    as live failures.

    It now stops once every unmerged candidate collected so far is already
    superseded by a merge it has seen. That is sound rather than merely
    cheaper: a later page can only add OLDER-created PRs, which the same
    `delivered` supersedes too. It is still bounded by PR_PAGE_LIMIT
    (CLAUDE.md §3.8).
    """
    delivery_re = delivery_re or title_re
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
        if len(rows) < page_size:
            break
        # The SAME rule the reporting uses. Comparing a creation time against
        # a merge time here bypassed the generation comparison entirely, so the
        # walk could stop on an older-generation delivery while a newer,
        # unmerged refresh sat on a later page and was never read.
        deliveries = [pr for pr in owned
                      if pr["merged"] and delivery_re.search(pr["title"])]
        pending = [pr for pr in owned if not pr["merged"]]
        if deliveries and all(superseded(pr, deliveries) for pr in pending):
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


def region_text(body: str, name: str) -> str | None:
    """The text of one named generated region, or None when it is absent.

    Both delimiter spellings this repo uses: `<!-- BEGIN NAME -->` and
    `<!-- NAME:BEGIN -->`, with the inventory form as a third.
    """
    esc = re.escape(name)
    for begin, end in (
        (rf"<!--\s*BEGIN {esc}\s*-->", rf"<!--\s*END {esc}\s*-->"),
        (rf"<!--\s*{esc}:BEGIN\s*-->", rf"<!--\s*{esc}:END\s*-->"),
        (rf"<!--\s*inventory:{esc}:start\s*-->", rf"<!--\s*inventory:{esc}:end\s*-->"),
    ):
        lo = re.search(begin, body)
        hi = re.search(end, body)
        if lo and hi and hi.start() >= lo.end():
            return body[lo.end():hi.start()]
    return None


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
        body = path.read_text(encoding="utf-8", errors="replace")
        # Scoped to the DECLARED region. A whole-file search accepted a date
        # from an unrelated paragraph, so a generated block that lost its own
        # provenance still reported fresh -- the artifact's evidence has to
        # come from the artifact.
        region = region_text(body, art["region"])
        if region is None:
            findings.append({"check": "class-a", "doc": art["doc"], "severity": "P2",
                             "detail": f"`{art['region']}` is not in the document, so "
                                       f"nothing shows whether {art['refresher']} ever "
                                       "refreshed it"})
            continue
        dates = art["date_re"].findall(region)
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
        if is_future_date(newest, today):
            findings.append({"check": "class-a", "doc": art["doc"], "severity": "P2",
                             "detail": f"`{art['region']}` is dated {newest}, which is in the "
                                       "future, so its age can never reach the threshold"})
            continue
        age = (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(newest)).days
        if age > art["max_age_days"]:
            findings.append({"check": "class-a", "doc": art["doc"], "severity": "P2",
                             "detail": f"`{art['region']}` is dated {newest}, {age}d old and past "
                                       f"the {art['max_age_days']}d the renderer itself calls "
                                       f"stale, so {art['refresher']} has not re-rendered it -- "
                                       "its workflow step is best-effort, so a green run and a "
                                       "merged refresh PR prove nothing about this block"})
    return findings


def _is_dry_run(row: list[str]) -> bool:
    """Was this workflow run a dry run, which opens no PR and delivers nothing?

    The `inputs` map is present only on workflow_dispatch runs and carries
    strings, so `"false"` is a real value and must not read as truthy. A row
    from an older read that carries no such column is treated as delivering,
    which is the safe direction: it can only keep a failure on the report.
    """
    if len(row) < 4:
        return False
    return row[3].strip().lower() in {"true", "1", "yes"}


RUNS_PAGE_SIZE = 10
# Enough pages to get past a run of manual dry runs without reading history
# nobody will act on. Reaching it is reported, never silently truncated.
RUNS_PAGE_LIMIT = 10


def fetch_owning_runs(*, page_size: int = RUNS_PAGE_SIZE) -> list[list[str]]:
    """Recent runs of the owning workflow, read until one of them delivered.

    A fixed ten-run window plus the dry-run filter is a hole the two together
    open and neither has alone: the workflow permits repeated manual dry runs,
    and ten of them push the last DELIVERING execution out of view, so a failed
    scheduled refresh behind them reports nothing at all. The walk stops as
    soon as a non-dry run is in hand, so the common case is still one request.
    """
    rows: list[list[str]] = []
    for page in range(1, RUNS_PAGE_LIMIT + 1):
        out = run([
            "gh", "api",
            f"repos/{OWNER}/{THIS_REPO}/actions/workflows/{OWNING_JOB['workflow']}"
            f"/runs?per_page={page_size}&page={page}",
            "--jq", '.workflow_runs[] | [.conclusion, .created_at, '
                    '(.event // ""), ((.inputs // {}).dry_run // "")] | @tsv',
        ])
        # strip("\n"), not strip(). A queued or in-progress run has a null
        # conclusion, so its TSV row BEGINS with a tab -- and stripping the
        # whole response removes that tab from the first row, shifting every
        # column left. The timestamp then reads as the conclusion.
        page_rows = [r.split("\t") for r in out.strip("\n").split("\n") if r.strip()]
        rows += page_rows
        # A QUEUED or in-progress run has an empty conclusion. Stopping on it
        # treated "the rerun has not finished" as sufficient history, and
        # check_owning_job accepts that empty conclusion too -- so a completed
        # delivering run that FAILED, pushed onto an earlier page by dry runs,
        # was never examined and the delivery audit could report clean.
        if any(not _is_dry_run(r) and r[0].strip() for r in page_rows):
            return rows
        if len(page_rows) < page_size:
            break
    if not rows:
        # The workflow exists but has never run. Returning [] made
        # check_owning_job emit no run-status finding, so the delivery audit
        # passed without any evidence the owning job has ever executed --
        # the same clean-bill-of-health-on-no-data shape fetch_issue_states
        # already refuses.
        raise AuditError(
            f"{OWNING_JOB['workflow']} has no runs at all; refusing to report a clean "
            "delivery audit on no evidence that the owning job has ever executed")
    if all(_is_dry_run(r) for r in rows):
        # Exhausting the page limit with nothing but dry runs is a TRUNCATED
        # read, not a complete one. Returning it silently let 100 consecutive
        # manual dry runs hide a failed scheduled run behind them -- exactly
        # the hole the pagination was added to close, one level out.
        raise AuditError(
            f"{OWNING_JOB['workflow']}: {len(rows)} runs read across "
            f"{RUNS_PAGE_LIMIT} pages and every one is a dry run; refusing to report "
            "on a history with no delivering execution in it")
    return rows


_REFRESH_GEN_RE = re.compile(r"(\d{4})-(\d{2})")


def _refresh_generation(title: str) -> str:
    """The `YYYY-MM` a refresh PR title names, or "" when it names none.

    Supersession is a statement about which month's documents landed, and only
    a title carrying a generation can make it.
    """
    m = _REFRESH_GEN_RE.search(title or "")
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def superseded(pr: dict, deliveries: list[dict]) -> bool:
    """Has a later refresh made this attempt history?

    Per delivery, because the two facts that matter live on the same record.
    A delivery supersedes when it is a NEWER generation, or the same
    generation merged after this attempt was opened.

    Both halves are load-bearing and each was learned from a case:

    * Generation alone is wrong. #1060 (`refresh: 2026-09`, opened 09-08) is
      not superseded by #953 (`refresh: 2026-09`, merged 09-02): a September
      refresh opened AFTER a September refresh merged is a re-attempt, and its
      being unmerged is the thing worth reporting.
    * Time alone is wrong. #900 (`refresh: 2026-08`, merged 09-20) does not
      supersede #1060 either: August's output cannot establish that
      September's documents landed.

    A repair attempt (`Fix: Monthly architecture doc refresh failed`) names no
    generation, so there is nothing to compare but time -- the case the
    supersede rule was added for (#963/#1012/#1021).

    Shared with the PR walk on purpose: a walk that stops on a different rule
    from the one that reports can stop before the PR it would report.
    """
    gen = _refresh_generation(pr["title"])
    for d in deliveries:
        d_gen = _refresh_generation(d["title"])
        if gen and d_gen:
            if d_gen > gen or (d_gen == gen and d["merged"] > pr["created"]):
                return True
        elif d["merged"] and d["merged"] > pr["created"]:
            return True
    return False


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
        recent = fetch_owning_runs()
        owned_prs = fetch_owned_prs(OWNING_JOB["pr_title_re"],
                                    delivery_re=OWNING_JOB["delivery_title_re"])
    except AuditError:
        # Do NOT convert this into a finding. A finding means "the docs are
        # stale"; this means "the audit never learned whether they are", and
        # collapsing the two let a default run exit 0 and a --check run exit 1
        # -- neither of which is the documented exit 2 for an incomplete audit.
        raise


    # A dry run does not deliver: refresh-architecture-docs.yml declares a
    # `dry_run` input and skips its "Open refresh PR" step when it is set, so
    # reading `recent[0]` unconditionally let a successful manual dry run stand
    # as evidence that a failed scheduled refresh had recovered. The failure
    # then vanished from the report until the 40-day stamp threshold fired.
    # Delivery is judged from the latest NON-dry execution.
    delivering = [r for r in recent if not _is_dry_run(r)]
    # The most recent COMPLETED delivering run that succeeded. It is what says
    # a no-op month regenerated identical content, which no document can show
    # about itself because the workflow reverts timestamp-only files.
    last_success = max((r[1][:10] for r in delivering if r[0] == "success"), default="")
    if delivering and delivering[0][0] not in {"success", ""}:
        findings.append({"check": "class-a", "doc": OWNING_JOB["workflow"], "severity": "P1",
                         "detail": f"last delivering run concluded {delivering[0][0]} "
                                   f"at {delivering[0][1]}"})

    # A closed-unmerged attempt that a LATER refresh superseded is history, not
    # a live defect. Reporting #963/#1012/#1021 forever kept --check red with
    # findings whose only remedy would be reviving obsolete PRs.
    delivery_re = OWNING_JOB["delivery_title_re"]
    # By GENERATION, not by mixing one PR's creation time with another's merge
    # time. An August refresh that merges after September's PR was opened made
    # `created < delivered` true for September, so the still-unmerged September
    # refresh was skipped -- though August's output says nothing about whether
    # September's documents ever landed. The strict delivery title carries the
    # generation (`Monthly architecture doc refresh: YYYY-MM`); a PR whose
    # title has no generation cannot supersede anything.
    deliveries = [pr for pr in owned_prs
                  if pr["merged"] and delivery_re.search(pr["title"])]
    # Filter first, THEN limit. Slicing the raw list meant six newer merged
    # maintenance PRs -- which the attempt pattern is deliberately broad enough
    # to match, and which never contribute to the strict delivery set -- could
    # push an older unsuperseded open refresh PR out of view, so the audit
    # reported no delivery problem while that refresh sat unmerged.
    actionable = [pr for pr in owned_prs
                  if not pr["merged"] and not superseded(pr, deliveries)]
    for pr in actionable[:6]:
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
        body = path.read_text(encoding="utf-8", errors="replace")
        # Not from a fenced example or an HTML comment. A scan of the whole
        # document let any `Generated YYYY-MM-DD` in sample output stand in for
        # a missing footer, so removing the real stamp while keeping a recent
        # example passed the freshness check with no production date at all.
        # Narrower than "the declared provenance location", which this module
        # does not model; it removes the non-rendered sources, which is the
        # case reported.
        body_lines = body.split("\n")
        skip = fenced_lines(body_lines) | commented_lines(body_lines)
        stamps = [d for i, line in enumerate(body_lines) if i not in skip
                  for d in GENERATED_RE.findall(line)]
        if not stamps:
            # Silently skipping this is the same clean-run-on-no-evidence the
            # best-effort artifact check already refuses. For 05-a, 05-c and
            # 05-d the stamp is not a separately declared generated region, so
            # a refresh that dropped it leaves a green workflow, a merged PR,
            # and a document carrying no evidence at all of when it was made.
            # All four docs carry one today, so this changes no current finding.
            findings.append({"check": "class-a", "doc": doc, "severity": "P2",
                             "detail": "no `Generated <date>` stamp, so nothing in the document "
                                       "shows when the owning job produced it"})
            continue
        bad = [s for s in stamps if not is_calendar_date(s)]
        if bad:
            # fromisoformat raised here, so an impossible footer produced a
            # traceback and exit 1 -- the status that means "the docs have
            # findings" -- rather than the finding it is.
            findings.append({"check": "class-a", "doc": doc, "severity": "P2",
                             "detail": f"Generated {bad[0]} is not a real calendar day"})
            continue
        if len(set(stamps)) > 1:
            # 05-c carries a stamp in its header AND its footer. max() reads the
            # document as current when a partial refresh moved only one, while
            # the other visible provenance claim stays stale -- and the
            # workflow's own gate only requires ONE occurrence of today's date.
            findings.append({"check": "class-a", "doc": doc, "severity": "P2",
                             "detail": "generated stamps disagree ("
                                       + ", ".join(sorted(set(stamps)))
                                       + "); a partial refresh moved one and left the other"})
            continue
        newest = max(stamps)
        if is_future_date(newest, today):
            # A future stamp yields a negative age, which passes the threshold
            # below forever: the one value that can never go stale.
            findings.append({"check": "class-a", "doc": doc, "severity": "P2",
                             "detail": f"Generated {newest} is in the future, so its age can "
                                       "never reach the staleness threshold"})
            continue
        age = (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(newest)).days
        if age > 40:
            # A SUCCESSFUL no-op refresh is freshness evidence the document
            # cannot carry. refresh-architecture-docs.yml reverts every
            # timestamp-only file and opens its PR only when
            # `meaningful == '1'`, so a month that regenerated identical
            # content leaves the old Generated date in place by design. Two of
            # those in a row put every owned document past 40 days and the
            # audit called them all stale -- a finding whose only remedy would
            # be forcing a cosmetic change.
            if last_success and last_success >= newest:
                since = (datetime.date.fromisoformat(today)
                         - datetime.date.fromisoformat(last_success)).days
                if since <= 40:
                    findings.append({"check": "class-a", "doc": doc, "severity": "P3",
                                     "detail": f"Generated {newest} is {age}d old, but the "
                                               f"owning job last succeeded {since}d ago "
                                               f"({last_success}) without opening a PR -- a "
                                               "no-op refresh, which reverts timestamp-only "
                                               "files by design"})
                    continue
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
    ap.add_argument("--no-owning-job-check", action="store_true",
                    help="skip the Class A delivery audit, which needs the GitHub API")
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
    # Argument validation comes FIRST, before any git read, issue-state read,
    # snapshot write or owning-job API call. Running it late meant
    # `--verify docs/x.md` (invalid without --stamp) failed with an unrelated
    # GitHub authentication error, and combining it with
    # --write-issues-snapshot wrote that file before the command was rejected.
    # A rejected invocation must not have side effects.
    #
    # A review is recorded only by WRITING a marker, so `--verify` without
    # `--stamp` is a no-op that reads, on an otherwise clean audit, as if the
    # human verification had been recorded. It exits 2 instead.
    if args.verify is not None and not args.stamp:
        raise AuditError("--verify requires --stamp: a review is recorded by writing "
                         "a marker, and without --stamp nothing is written")
    if args.verify is not None and not args.verify:
        raise AuditError("--verify needs at least one path")

    base_ref = resolve_base_ref()
    # --short alone honours core.abbrev, which can be set below 7:
    # `git -c core.abbrev=4 rev-parse --short HEAD` emits four characters, and
    # MARKER_RE requires 7-40. A marker written with a shorter id parses with
    # `sha` unset and the rest of the line swallowed into the unmatched tail,
    # so the verified review it records reports as having no reviewed-against
    # SHA and its drift check silently stops running. The length is fixed here.
    #
    # --since is written straight into `Against:` too, so an unresolvable or
    # misspelled value lands in the marker with the same consequence. It is
    # resolved through git rather than trusted, and a value git cannot place
    # is exit 2 before anything is written.
    head = resolve_marker_sha(args.since, base_ref)

    reg_path = REPO / REGISTRY
    if not reg_path.exists():
        print(f"error: {REGISTRY} not found; every doc would be unclassified", file=sys.stderr)
        return 2
    registry = load_registry(reg_path.read_text(encoding="utf-8"))

    tracked = set(run(["git", "ls-tree", "-r", base_ref, "--name-only"]).strip().split("\n"))
    TOP_LEVEL_DIRS.update(p.split("/", 1)[0] for p in tracked if "/" in p)
    docs = document_set(tracked, registry)
    # A document staged or still untracked is absent from `ls-tree`, so a
    # contributor could run the audit clean and then commit a new unclassified
    # document with no marker and dead links. The rest of the command already
    # reads the WORKING TREE, so the inventory must come from there too.
    #
    # `tracked` itself is deliberately NOT widened: it is what decides whether
    # a LINK resolves, and letting an untracked file satisfy a link is the bug
    # is_tracked_dir was written to close -- present here, absent in every
    # clean clone.
    # An index ADDITION is part of the content about to be committed, so it
    # resolves links and satisfies registry declarations as any tracked file
    # does -- otherwise a multi-file documentation change cannot be audited
    # cleanly before it is committed, the one moment the audit is most useful.
    # An UNTRACKED file is different: it may never be committed, and letting it
    # satisfy a link is the bug is_tracked_dir was written to close.
    staged = {p for p in run(["git", "diff", "--cached", "--name-only",
                              "--diff-filter=A"]).strip().split("\n") if p}
    # And a DELETION, staged or not, leaves it. Keeping a deleted path in
    # `tracked` let a surviving document link to an asset that is gone and
    # pass, let a deleted declared code path satisfy the registry check, and --
    # when the deleted path was itself a document -- aborted the whole audit on
    # the working-tree read instead.
    deleted = {p for p in run(["git", "diff", "--name-only", "--diff-filter=D",
                               "HEAD"]).strip().split("\n") if p}
    # A pure RENAME is neither, and `--diff-filter` cannot express it: `git mv
    # docs/old.md docs/new.md` produces one `R100` line that both queries above
    # skip. The old path therefore stayed in the inventory while the new one
    # was absent, so the run opened a document no longer on disk and exited 2 --
    # on precisely the workflow (audit the change before committing it) that
    # staged-addition support exists for. Both sides are consumed here: the
    # source joins the deletions, the destination joins the additions.
    renamed_from: set[str] = set()
    for line in run(["git", "diff", "--cached", "--name-status",
                     "--diff-filter=R"]).strip().split("\n"):
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("R"):
            renamed_from.add(parts[1])
            staged.add(parts[2])
    deleted |= renamed_from
    if staged or deleted:
        tracked = (tracked | staged) - deleted
        docs = document_set(tracked, registry)
    untracked = [p for p in run(["git", "ls-files", "--others", "--exclude-standard",
                                 "--", "*.md"]).strip().split("\n") if p]
    docs = sorted(set(docs) | set(untracked))

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
    # Its own flag, not a side effect of --issues-snapshot. Keying the Class A
    # delivery audit off the issue-state flag meant an offline or deterministic
    # issue run reported Class A clean however badly the architecture refresh
    # was failing -- an unrelated check silently disabled by an unrelated
    # option, until a Generated stamp aged past 40 days.
    if not args.no_owning_job_check:
        findings += check_owning_job(today)
    stamped: list[dict] = []
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

        # The document list comes from HEAD and the contents from the working
        # tree, so an ordinary staged or unstaged deletion left the path in
        # `docs` and raised FileNotFoundError here: a traceback and exit 1, the
        # status reserved for documentation findings.
        try:
            # STRICT when a write may follow. errors="replace" substitutes
            # U+FFFD for any invalid byte, and --stamp writes the whole decoded
            # string back -- corrupting bytes far outside the marker, which is
            # the one thing stamping promises not to touch.
            text = (REPO / doc).read_text(
                encoding="utf-8", errors="strict" if args.stamp else "replace")
        except UnicodeDecodeError as exc:
            raise AuditError(
                f"{doc} is not valid UTF-8 ({exc}); --stamp would write back a lossy "
                "decode and corrupt bytes outside the marker. Fix the encoding first, "
                "or run without --stamp") from exc
        except OSError as exc:
            raise AuditError(
                f"{doc} is in the audited tree at HEAD but cannot be read from the "
                f"working tree ({exc}); the audit cannot report on a document it "
                "could not open") from exc
        lines = text.split("\n")
        markers = find_markers(lines)
        found = markers[0] if markers else None

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

        # A registered `.drawio` is XML. Scanning it as Markdown turned a
        # diagram label reading `[x](missing.md)` into a gating dead-link
        # finding for a construct nothing renders. Region, marker and delivery
        # checks still apply to these artefacts; only the MARKDOWN content
        # checks are skipped.
        content = ((check_closed_issues(doc, text, states)
                    + check_dead_links(doc, text, tracked))
                   if doc.endswith(".md") else [])
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
            # Both date fields, calendar validity and future-dating together:
            # the future check used to live here and read `info["date"]` only,
            # which left `Last scanned` in the future entirely unchecked.
            findings += check_marker_dates(doc, info, today)
            findings += check_marker_fields(doc, info)
            # A second marker in the window is a document making two review
            # claims at once. Reading the first and ignoring the rest let
            # `--stamp` rewrite the top one, report `updated` or `unchanged`,
            # and accept a --verify target while a conflicting older date or
            # SHA sat immediately below it.
            if len(markers) > 1:
                findings.append({
                    "check": "marker", "doc": doc, "severity": "P2",
                    "line": markers[1][0] + 1,
                    "detail": f"{len(markers)} review markers in the marker window "
                              f"(lines {', '.join(str(i + 1) for i, _ in markers)}); "
                              "the audit reads the first and the others contradict it"})
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
                # And the document itself, which the code-path query cannot
                # see -- and which is the ONLY drift signal a registry row
                # with no declared code paths has.
                findings += check_doc_changed_since(doc, info["sha"], base_ref)

        if args.stamp:
            # Never write a marker into a generated region. The marker goes
            # after the H1, so the check is whether anything a job owns sits
            # that high in the file -- on README the H1 is line 1 and the first
            # badge is line 5, which is why stamping it is safe at all.
            # Not stamped while the document contradicts itself: rewriting
            # one of two markers leaves the other, and the run would report
            # success for a review whose provenance is still ambiguous. The
            # finding above says which lines; a human merges them.
            if len(markers) > 1:
                continue
            # Where the EXISTING marker sits, not just where a new one would
            # go. The proximity test below compares the first generated line
            # with the H1, which says nothing about a marker further down
            # inside a block that starts later: `stamp` would replace it in
            # place, report success for a --verify, and the renderer would
            # overwrite that provenance on its next run.
            if found is not None and (found[0] + 1) in owned:
                findings.append({"check": "unowned", "doc": doc, "severity": "P2",
                                 "detail": f"not stamped: the existing marker on line "
                                           f"{found[0] + 1} is inside a generated region, so "
                                           "rewriting it would be discarded by the renderer"})
                continue
            h1 = marker_anchor(lines)
            if owned and h1 is not None and min(owned) <= h1 + 2:
                findings.append({"check": "unowned", "doc": doc, "severity": "P2",
                                 "detail": f"not stamped: a generated region starts at line "
                                           f"{min(owned)}, too close to the H1 on line {h1 + 1}"})
                continue
            reviewed = doc in verify
            # A review records "these claims were true against THIS revision".
            # For a document the revision does not contain, that sentence has
            # no meaning -- and the marker it would write is unfalsifiable,
            # because every later drift check finds nothing to diff against.
            # A staged-new document is the case that reaches here; the answer
            # is to commit it and stamp against a revision that holds it.
            if reviewed and not path_in_commit(head, doc):
                stamp_refusals[doc] = "baseline-predates-doc"
                continue
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
            why = {"baseline-predates-doc":
                       f"the document does not exist at {head}, so the review would "
                       "name a baseline predating it; commit it first",
                   "skipped-no-h1": "no H1 to place a marker after",
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
        # Every target is checked before any is written. A document that has
        # been deleted or made read-only is the common case here, and finding
        # it on file 60 of 93 leaves the tree half stamped with no record of
        # where it stopped. This narrows that window; it does not close it --
        # a full disk still fails mid-loop, and os.access answers for the
        # calling uid, which under root says "writable" about a mode-444 file.
        # So the loop reports what it had already written, rather than
        # pretending the operation was atomic.
        unwritable = [doc for doc, _ in writes
                      if not (REPO / doc).is_file() or not os.access(REPO / doc, os.W_OK)]
        if unwritable:
            raise AuditError(
                f"--stamp cannot write {', '.join(sorted(unwritable))}: missing or "
                "not writable. Nothing was written.")
        done: list[str] = []
        for doc, new in writes:
            try:
                (REPO / doc).write_text(new, encoding="utf-8")
            except OSError as exc:
                # Exit 2, not the traceback-and-exit-1 that means "findings".
                raise AuditError(
                    f"--stamp failed writing {doc}: {exc}. {len(done)} of "
                    f"{len(writes)} documents were already stamped"
                    + (f" ({', '.join(done)})" if done else "")
                    + "; the tree is partially stamped.") from exc
            done.append(doc)

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
            # Only a WRITE is a change. `skipped-legacy-content` and
            # `skipped-no-h1` queue nothing, and several living documents
            # return the former deliberately, so a routine --stamp reported
            # them changed when no write existed.
            acted = [s for s in stamped if s["action"] in {"inserted", "updated"}]
            refused = [s for s in stamped
                       if s["action"] not in {"inserted", "updated", "unchanged"}]
            skipped = len(refused)
            print(f"  stamped: {len(acted)} changed, "
                  f"{len(stamped) - len(acted) - skipped} unchanged"
                  + (f", {skipped} skipped" if skipped else ""))

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
