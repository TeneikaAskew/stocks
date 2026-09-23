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

A snapshot carries the time it was captured and EXPIRES: reading one more than
``ISSUE_SNAPSHOT_MAX_AGE_DAYS`` old is exit 2, not a clean run. Issue state
moves, and a report dated today off a week-old capture is a fabricated clean
bill of health -- the outcome this tool exists to stop.
"""
from __future__ import annotations

import argparse
import bisect
import datetime
import fnmatch
import functools
import html
import json
import os
import pathlib
import posixpath
import re
import subprocess
import sys
import unicodedata
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

# Up to three leading spaces, as CommonMark renders and `heading_anchors`
# already admitted. At column zero only, `  # Title` gave no H1, so the audit
# reported a missing marker while --stamp answered `skipped-no-h1` and could
# not repair its own finding. Four spaces is indented code, so the bound holds.
H1_RE = re.compile(r"^ {0,3}#\s+\S")
_URI_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)

# A reference only counts as a staleness finding when the surrounding line
# presents it as live work. A changelog saying "fixed #123" is not a defect.
# Whole cues, not substrings. An unbounded alternation matched inside
# `nonblocking` and `not blocked by`, so a line stating an issue is NOT a
# blocker produced a P1 against it once it closed -- a finding whose own
# source line says the opposite. `\b` alone stops `nonblocking`; the negator
# scan in has_blocking_cue stops the spaced and hyphenated forms.
#
# `\s+` between the words, not a literal space, and `blocked on`, `blocker`
# and `blockers` beside `blocked by`. Both came from the Node twin
# (solyra#69), where Codex filed them; the same probe showed both gaps live
# here. `Blocked on <url>` is the same statement as `blocked by`, and a
# single space stopped matching the moment markup was reduced in place --
# `still **open**` arrives as `still   open`, because the reduction blanks
# delimiters rather than removing them so offsets survive. A closed issue the
# prose plainly calls live then produced no finding at all.
BLOCKING_CUE_RE = re.compile(
    r"\b(?:blocking|blocked\s+(?:by|on)|blocker|blockers|open\s+issues?"
    r"|still\s+open|outstanding|in\s+progress|not\s+started|pending)\b",
    re.I,
)
# Text immediately before a cue that inverts it. `not started` is itself a cue,
# so what precedes THAT phrase is what is tested -- its own leading `not` is
# never read as negating the phrase it belongs to.
# An adverb may sit between the negator and the cue: `is not yet resolved` and
# `has not yet merged` both say the citation is LIVE, and requiring the negator
# flush against the cue read the positive substring as a completion cue --
# suppressing the finding on a closed blocker whose own clause says otherwise.
# Bounded to one intervening word so a negation cannot reach across a clause it
# does not govern.
# An ARTICLE may sit there too: `is not an open issue` and `is no longer an
# open issue` both say the citation is finished, and without the article the
# positive `open issue` substring read as a live-work cue -- a gating P1 on
# text that says the exact opposite. One adverb and one article, in that order
# (`not yet an open issue`), and the whole thing stays anchored to the end of
# the prefix so a negator elsewhere in the sentence cannot reach the cue.
# CONTRACTIONS too. `isn't blocking release` says exactly what `is not
# blocking release` says, and the negator list held only the spelled-out form
# -- so the contracted sentence read as live work and a closed issue produced
# a P1 whose own source line states the opposite. The apostrophe may be typed
# or curly; a document written in either renders the same word. Codex filed it
# on the Node twin (solyra#69); the same gap was live here.
CUE_NEGATOR_RE = re.compile(
    r"\b(?:not|non|never|no longer|without|un|\w+n['\u2019]t)[\s-]*"
    r"(?:(?:yet|still|quite)[\s-]*)?"
    r"(?:(?:an?|the)[\s-]*)?$", re.I)
# `not only X but also Y` AFFIRMS X, and Codex filed a carve-out for it on the
# Node twin (solyra#69), whose window admits any two `\w+` between negator and
# cue. THIS pattern admits a fixed vocabulary instead -- one of
# `yet|still|quite`, then an article -- so `not only ` never reaches a cue and
# the carve-out would be code no test could remove. Probed rather than ported:
# the mutation came back GREEN, which is what said the defect is not here.


_CLOSING_TAG_RE = re.compile(r"</[a-zA-Z][a-zA-Z0-9-]*\s*>")
_INLINE_LINK_RE = re.compile(r"\[([^\[\]]*)\]\([^()\s]*(?:\s+[^()]*)?\)")
_REF_USE_RE = re.compile(r"\[([^\[\]]*)\]\[[^\[\]]*\]")


def strip_inline_markup(line: str) -> str:
    """The line with emphasis, inline LINK and HTML markup blanked.

    A cue is what a READER sees. `is still **open**`, `Still [open](x.md):`
    and `Still <strong>open</strong>:` all render as prose plainly calling
    the citation live, and the classifier saw the delimiters between the
    words and found no cue at all -- so a closed issue vanished from the
    audit entirely, the direction that hides findings. Codex filed the link
    and HTML halves on the Node twin (solyra#69); the emphasis half was
    missing here too, which the same probe showed.

    Blanked to SPACES, never removed: every offset the caller holds is an
    offset into this line. A link's DESTINATION is blanked even though the
    citation scan keeps it visible -- those two read different strings, and a
    URL written as a destination is still found in the unmarked copy.
    """
    def blank(m: re.Match) -> str:
        return " " * len(m.group(0))

    def keep_label(m: re.Match) -> str:
        label = m.group(1)
        return " " + label + " " * (len(m.group(0)) - len(label) - 1)

    out = re.sub(r"\*+", blank, line)
    out = re.sub(r"(?<!\w)_+|_+(?!\w)", blank, out)
    out = _INLINE_LINK_RE.sub(keep_label, out)
    out = _REF_USE_RE.sub(keep_label, out)
    return _CLOSING_TAG_RE.sub(blank, _TAG_OPEN_RE.sub(blank, out))


def _is_negated(prefix: str) -> bool:
    """Does the text immediately before a cue invert it?

    One predicate, so `has_blocking_cue` and `is_settled` cannot disagree
    about what a negation is -- they already shared `CUE_NEGATOR_RE`, and a
    rule that lives in two call sites grows two versions.
    """
    return bool(CUE_NEGATOR_RE.search(prefix))


def has_blocking_cue(line: str) -> bool:
    """Does this line cite live work?

    True when at least ONE cue occurrence is not negated: a line may say one
    issue still blocks and another no longer does.
    """
    return any(not _is_negated(line[:mm.start()])
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
# `closure` and `resolution` are the NOUN forms of two cues already here, and
# the blocking vocabulary carries `blocker`/`blockers` beside `blocking` for
# exactly this reason. Without them, `... is tracked as outstanding work, not
# as part of the closure` -- a sentence whose own words say the citation is
# closed -- was read as live work once the cue analysis moved to the rendered
# paragraph and could see the `outstanding` six lines up. Measured on
# docs/product/12-PR-ISSUE-TRACEABILITY.md.
SETTLED_CUE_RE = re.compile(
    r"\b(?:closed|closure|resolved|resolution|superseded|merged|moved to"
    r"|relocated|duplicate of|completed)\b", re.I)


def is_settled(clause: str) -> bool:
    """Does this clause say the citation is finished?

    True only when at least one settled cue is not negated: `not resolved` and
    `never merged` say the opposite of the word they contain.
    """
    return any(not _is_negated(clause[:mm.start()])
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
# Case-INSENSITIVE, because `ISSUE_URL_RE` beside it is. `HTTPS://...` was
# left unmasked here, so the periods inside it became clause boundaries and a
# second citation on the line lost the cue it shared -- the stale claim passed
# while the identical lowercase spelling was reported. Two patterns reading
# the same URLs and disagreeing about which ones are URLs.
_URL_RE = re.compile(r"https?://[^\s|]*[^\s|.,;:!?)\]]", re.I)
# Case-insensitive, because GitHub resolves `teneikaaskew/Stocks` to the same
# repository and a document may cite it that way. The `i` flag ALONE would be
# worse than the bug: the captured name would index states["Stocks"], miss, and
# fabricate a "could not be resolved" P2 against a live issue. Both captures
# are lower-cased at the call site.
# Anchored to a HOST boundary. Unanchored, any other site whose path embeds the
# string matched: `https://example.com/archive/github.com/<owner>/stocks/issues/1`
# produced a stale-blocker finding against stocks#1 although the document links
# only to example.com. The bare-host spelling (`github.com/...` with no scheme)
# is deliberately still accepted -- documents here write it -- so the boundary
# is "start, whitespace, or a scheme/`//`", not "https:// only".
ISSUE_URL_RE = re.compile(
    # The `//` must be the SCHEME's. Any double slash satisfied the old
    # lookbehind, so `https://example.com//github.com/<owner>/stocks/issues/1`
    # read as a citation of stocks#1 and a closed issue 1 produced a gating
    # stale-blocker finding for a URL whose host is example.com. The bare-host
    # spelling this repo's docs use is still admitted, by the
    # start/whitespace/bracket alternatives beside it. Parity with the Node
    # twin (solyra#69).
    r"(?:(?<=^)|(?<=[\s(\[<])|(?<=://))"
    # And the number ENDS where the number ends. Without a trailing boundary
    # `.../issues/1foo` captured the numeric prefix and was read as a citation
    # of issue 1 -- so a closed issue 1 produced a gating stale-blocker finding
    # for a URL that identifies no issue at all. A query, a fragment,
    # punctuation and whitespace are legitimate suffixes, so the boundary is
    # "not another word character", not "end of string".
    r"github\.com/" + OWNER + r"/(?P<repo>solyra|stocks)/(?P<kind>issues|pull)/(?P<num>\d+)"
    r"(?![\w-])",
    re.I,
)
# The shorthand a document uses when it is talking about its OWN repository:
# docs/product/16-CONSOLIDATION-AUDIT.md calls `#940` outstanding and blocking
# without linking it, and a URL-only pattern never saw it -- so closing the
# issue produced no finding. Read only on a line that already carries a
# blocking cue, because `#940` in ordinary prose (a section number, a column)
# is not a citation; the cue is what makes it one. Not preceded by a word
# character, so `abc#940` and a URL's own `#fragment` are left alone.
# `\b` is not the right closing boundary: it holds between the `6` and the `-`
# of the heading anchor `(#16-outstanding-work--known-gaps)`, so a table of
# contents read as a citation of stocks#16. An issue number is followed by
# neither a word character nor a hyphen.
SHORTHAND_ISSUE_RE = re.compile(r"(?<![\w#/-])#(?P<num>\d{1,6})(?![\w-])")
# `stocks#861` and `solyra#8`: repository-qualified shorthand, which GitHub
# renders as a link to that issue and which carries everything needed to
# resolve it -- the state map is already loaded. The scan recognised only full
# URLs, so a blocker written that way went unreported once the issue closed.
# Only the QUALIFIED form; the bare one above keeps its much stricter clause
# rule, because `#123` may be a section number. The owner prefix is optional
# because `TeneikaAskew/stocks#861` is the same citation. The lookbehind
# refuses a path component (`docs/stocks#861`) and a second `#`. Codex filed
# it on the Node twin (solyra#69).
QUALIFIED_ISSUE_RE = re.compile(
    rf"(?<![\w#/-])(?:{OWNER}/)?(?P<repo>solyra|stocks)#(?P<num>\d{{1,6}})(?![\w-])",
    re.I)
# A `#N` that belongs to some OTHER numbering. Measured on this tree, a bare
# scan reported `Plan #4`, `plans #5 and #10` and `PRs #81` as issue citations;
# they are plan and PR numbering that happens to share the spelling. PR words
# are here too because a shorthand cannot tell an issue from a PR, and the
# URL pass already holds PRs to a stricter cue rule.
SHORTHAND_OTHER_DOMAIN_RE = re.compile(
    r"\b(?:plans?|prs?|pull|pulls|sections?|phases?|steps?|items?|figures?|"
    r"tables?|chapters?|slides?|rules?|rows?|questions?|parts?|versions?|"
    r"revs?|chapters?)\s+(?:and\s+)?$", re.I)
# What may sit between two `#N`s that name the same thing: `#5 and #10`,
# `#5, #10`, `#818/#816`.
_COORDINATOR_RE = re.compile(r"[\s,;/&]*(?:and|or)?[\s,;/&]*")
# The fragment is CAPTURED, not discarded. Dropping it meant a link to a real
# file but a heading that does not exist always passed -- 35 such links in this
# tree, including all 16 feature links in docs/product/02-FEATURE-CATALOG.md,
# whose targets in 12-PR-ISSUE-TRACEABILITY.md carry an em dash and a slash
# that GitHub's anchor rule turns into DOUBLED hyphens.
# The optional TITLE is admitted and discarded. `[guide](missing.md "Guide")`
# is standard CommonMark; requiring `)` straight after the destination meant
# the pattern did not match at all, so a missing target reported clean rather
# than dead. Raised on the Node twin (solyra#69).
# A Markdown inline link, scanned rather than matched by one pattern. The
# destination may nest parentheses to ANY depth -- `docs/a(b(c(d))).md` is a
# valid destination CommonMark resolves -- and a fixed-depth alternative could
# not match such a link at all, so a deleted target spelled that way produced
# no finding. Python's `re` has no recursion, so the balance is walked with
# the same `_balanced_close` the heading-link stripper uses; one scanner, so
# the depth limit cannot come back in one caller and not the other.
#
# One level of BALANCED brackets in the LABEL. `[^\]]*` stopped at the first
# `]`, so a link whose text contains brackets never matched at all and its
# target was never checked -- docs/gamma_levels.md writes
# ``[`lib/agents/prompts.py:ANALYST_PROMPTS["gamma"]`](../lib/agents/prompts.py)``
# and deleting that target reported clean.
# An ESCAPED bracket is label TEXT: `[a \] b](x.md)` renders a link and the
# structural class read the `]` as the label's end.
# A SCAN, not a fixed nesting depth. The pattern here handled one level of
# nested brackets, which covered ``[`ANALYST_PROMPTS["gamma"]`](...)`` and
# nothing deeper -- so `[a [b [c]]](missing.md)`, a link CommonMark renders,
# did not match AT ALL and its deleted target passed the audit clean. The
# hiding direction, and a depth limit is the kind of number that is wrong
# again the moment someone writes one more bracket. Codex filed it.
_MD_LINK_PAREN_RE = re.compile(r"\(\s*")


def _md_link_open(text: str, pos: int, hi: int) -> tuple[int, int] | None:
    """The next `[label](` in `text[pos:hi]`, as (start, end of the `(`).

    The label is walked with a depth counter rather than matched, so nesting
    has no limit to get wrong; a backslash escapes the character after it,
    there as everywhere. An unbalanced or unfollowed `[` is not an opening,
    and the walk resumes one character past it -- the same restart `md_links`
    already makes when a candidate fails to complete.
    """
    i = pos
    while i < hi:
        start = text.find("[", i, hi)
        if start < 0 or start >= hi:
            return None
        depth = 0
        k = start
        close = -1
        while k < hi:
            ch = text[k]
            if ch == "\\":
                k += 2
                continue
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    close = k
                    break
            k += 1
        if close < 0:
            i = start + 1
            continue
        paren = _MD_LINK_PAREN_RE.match(text, close + 1, hi)
        if paren is None:
            i = start + 1
            continue
        return start, paren.end()
    return None
# `<...>` is a distinct destination form: it is how CommonMark writes a
# destination containing a space -- `[g](<docs/removed guide.md>)` -- and the
# bare form rejects whitespace, so such a link did not match at all and a
# missing target reported clean.
# NO line endings. `<...>` may hold a space, which is why an author uses it,
# but CommonMark forbids a newline there -- so `[x](<missing\n.md>)` is
# literal text, and the multiline pass matched it anyway and emitted a gating
# dead-link finding over something no reader can click.
# A BACKSLASH ESCAPE is destination content: `[x](<a\>b.md>)` resolves to
# `a>b.md`, and stopping at the escaped `>` left the candidate unmatched
# altogether, so a missing target produced no finding. Consumed as a unit
# before the fragment split, so `\#` stays in the path as well.
_MD_LINK_ANGLE_RE = re.compile(
    r"<(?P<btarget>(?:&\#?[0-9A-Za-z]{1,32};|\\[^\r\n]|[^<>#\\\r\n])*)"
    r"(?:#(?P<bfrag>[^>\s]*))?>")
# One atom of a BARE destination. A CHARACTER REFERENCE is matched as a unit
# before the fragment split, so the `#` inside `&#38;` is not read as the
# separator: `[x](foo&#38;bar.md)` renders as a link to `foo&bar.md` and was
# split into the path `foo&` and the fragment `38;bar.md`, reporting a tracked
# file dead. An ESCAPED hash is part of the PATH for the same reason:
# `[x](a\#b.md)` resolves to the tracked `a#b.md`.
# The escape is restricted to ASCII PUNCTUATION, which is the only thing
# CommonMark lets a backslash escape. `\\.` consumed a backslash-space, so
# `[x](missing\\ file.md)` matched as one destination -- but CommonMark does
# not escape the space there, the bare destination ends at it, and the whole
# spelling renders as literal text. The audit emitted a gating dead-link
# finding for prose no reader can click. Codex filed it.
_ASCII_PUNCT = r"!-/:-@\[-`{-~"
_MD_DEST_ATOM_RE = re.compile(
    rf"&\#?[0-9A-Za-z]{{1,32}};|\\[{_ASCII_PUNCT}]|[^()#\s]")
# A TITLE may contain its own delimiter when the delimiter is escaped:
# `[x](missing.md "a \" quote")` is a valid link. Stopping at the escaped
# quote left the whole candidate unmatched, so the missing destination passed
# the audit -- the hiding direction. Each of the three title forms consumes
# escapes as units, exactly as the destination scan does.
# The fragment of a bare destination. Named rather than compiled inside the
# scan loop, so `_inline_link_end` asks the same pattern `md_links` does.
# The same atom as the destination, minus the `#` exclusion: a fragment may
# carry one (`#a#b` is the fragment `a#b`), and it may carry BALANCED
# parentheses, which `[^)\s]` could not. `[x](#foo(bar))` names the id
# `foo(bar)` and the scan stopped at the first `)`, recorded `foo(bar`, and
# consumed that parenthesis as the link's closer -- so a working link to an
# explicit `id="foo(bar)"` was a gating dead anchor. Codex filed it.
_MD_FRAG_ATOM_RE = re.compile(
    rf"&\#?[0-9A-Za-z]{{1,32}};|\\[{_ASCII_PUNCT}]|[^()\s]")


def _bare_fragment(text: str, i: int, end: int) -> int:
    """End of the balanced bare fragment starting at `i`.

    The same walk `_bare_destination` makes, over the atom above: a
    parenthesised run is consumed whole however deeply it nests, and a run
    carrying whitespace is not part of the fragment because CommonMark forbids
    whitespace anywhere in an unbracketed destination.
    """
    j = i
    while j < end:
        m = _MD_FRAG_ATOM_RE.match(text, j, end)
        if m:
            j = m.end()
            continue
        if text[j] == "(":
            k = _balanced_close(text, j)
            if k == -1 or k > end or any(c.isspace() for c in text[j:k]):
                return j
            j = k
            continue
        break
    return j


_MD_LINK_TAIL_RE = re.compile(
    r"""(?:\s+(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'"""
    r"""|\((?:\\.|[^)\\])*\)))?\s*\)""")


class _LinkMatch:
    """The pieces `check_target` reads, with `re.Match`'s accessors."""

    __slots__ = ("_text", "_start", "_end", "_groups", "dest_start", "dest_end",
                 "label_end")

    def __init__(self, text: str, start: int, end: int, groups: dict,
                 dest_start: int = -1, dest_end: int = -1, label_end: int = -1):
        self._text, self._start, self._end, self._groups = text, start, end, groups
        # Where the LABEL stopped -- the `]` before `(`. The label is rendered
        # TEXT, so a backticked path inside one is the link's own subject and
        # the inline pass has already reported its destination; the backtick
        # passes read this to avoid reporting the same broken citation twice.
        # Carried here rather than recovered by a second scan, because the
        # label walk is the only thing that knows where it ended.
        self.label_end = label_end
        # Where the DESTINATION began and stopped, so a caller can tell a
        # link's followable part from its metadata without rescanning.
        # `link_meta_spans` is the one that needs them; carrying them here is
        # what keeps that scan from becoming a second, drifting copy of this
        # one.
        self.dest_start, self.dest_end = dest_start, dest_end

    def start(self) -> int:
        return self._start

    def end(self) -> int:
        return self._end

    def group(self, key: int | str = 0) -> str | None:
        if key == 0:
            return self._text[self._start:self._end]
        return self._groups.get(key)


def _bare_destination(text: str, i: int, end: int) -> int:
    """End of the balanced bare destination starting at `i`.

    A parenthesised run is consumed whole, however deeply it nests. CommonMark
    forbids ASCII whitespace anywhere in an unbracketed destination, inside
    the parentheses included, so a run carrying any is not part of it.
    """
    j = i
    while j < end:
        m = _MD_DEST_ATOM_RE.match(text, j, end)
        if m:
            j = m.end()
            continue
        if text[j] == "(":
            k = _balanced_close(text, j)
            if k == -1 or k > end or any(c.isspace() for c in text[j:k]):
                return j
            j = k
            continue
        break
    return j


def md_links(text: str, lo: int = 0, hi: int | None = None):
    """Every inline link in `text[lo:hi]`, left to right.

    A failed completion restarts one character past the opening `[` rather
    than past the whole candidate, which is what a single pattern's
    backtracking did.
    """
    hi = len(text) if hi is None else hi
    pos = lo
    while pos < hi:
        opening = _md_link_open(text, pos, hi)
        if opening is None:
            return
        open_start, open_end = opening
        groups: dict[str, str | None] = {
            "btarget": None, "bfrag": None, "target": None, "frag": None}
        at = open_end
        dest_start = at
        angle = _MD_LINK_ANGLE_RE.match(text, at, hi)
        if angle is not None:
            groups["btarget"] = angle.group("btarget")
            groups["bfrag"] = angle.group("bfrag")
            at = angle.end()
        else:
            stop = _bare_destination(text, at, hi)
            groups["target"] = text[at:stop]
            at = stop
            if at < hi and text[at] == "#":
                stop_frag = _bare_fragment(text, at + 1, hi)
                groups["frag"] = text[at + 1:stop_frag]
                at = stop_frag
        dest_end = at
        tail = _MD_LINK_TAIL_RE.match(text, at, hi)
        if tail is None:
            pos = open_start + 1
            continue
        # `open_end` is just past `](`, so the label's closing bracket is two
        # characters back.
        yield _LinkMatch(text, open_start, tail.end(), groups,
                         dest_start, dest_end, open_end - 2)
        pos = tail.end()
# Reference-style Markdown, both halves. The definition's label may not open
# with `^`: that is a footnote, which defines a note rather than a destination.
# The destination may be angle-bracketed, which is how one containing a space
# is written: `[g]: <docs/my guide.md>`. `\S+` stopped at the first space and
# validated `docs/my`, so a tracked file was reported dead. The brackets are
# part of the capture and `strip("<>")` at the call site removes them, as it
# already did for the bare form.
# The whitespace after the colon is OPTIONAL. CommonMark registers
# `[g]:missing.md` and resolves `[x][g]` against it, but `\s+` skipped the
# definition -- and because reference USES are deliberately not scanned, its
# broken destination produced no finding at all. The head form below still
# matches when nothing follows the colon, because `\S+` needs a character.
# A BACKSLASH ESCAPE inside the angle-bracketed form is destination
# content, not the delimiter: CommonMark resolves `[g]: <a\\>b.md>` to
# `a>b.md`. `[^>]*` stopped at the escaped `>`, captured `<a\\>` and
# reported a tracked file dead -- the false direction. An unescaped `<`
# is not destination content either, so it ends the alternative too.
# What may follow the destination: nothing, or an optional title, to the end
# of the line. CommonMark renders a definition with any other suffix as
# ORDINARY TEXT -- `[g]: missing.md nonsense` defines nothing and links
# nowhere -- while a prefix-only match registered the destination and reported
# a gating dead link for a target no reader can reach. Codex filed it twice on
# this line.
REF_DEF_TAIL_RE = re.compile(
    r"""[ \t]*(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\((?:\\.|[^)\\])*\))?[ \t]*$""")
REF_DEF_RE = re.compile(
    r"^ {0,3}\[(?P<label>(?:\\.|[^\]\\^])(?:\\.|[^\]\\])*)\]:[ \t]*"
    r"(?P<target><(?:\\.|[^<>\\\n])*>|\S+)")
# The same definition with its destination on the FOLLOWING line, which
# CommonMark resolves and a per-line pattern cannot see. Split in two so the
# continuation is read through the same exclusions as any other line.
# A RENDERED HTML link. `<a href="...">` is a link a reader clicks, so a broken
# one is the same defect as a broken `[x](y)` -- and only Markdown syntax was
# scanned, so the audit reported clean over it. The unquoted attribute form is
# admitted too: `<a href=guide.md>` is valid HTML and renders a real link. An
# unquoted value ends at whitespace or any of `"\'=<>` and a backtick, which is
# what HTML says delimits it. Ported from the Node twin (solyra#69).
# `href` must be a whole ATTRIBUTE NAME, not a suffix of one and not text
# inside another attribute's value. `[^>]*?` matched the `href` in
# `<a data-href="missing.md">`, which is not a clickable link, and would match
# one written inside `<a title="href=x.md">` too -- both produced a gating
# dead-link finding for a destination no reader can reach. So the attributes
# before it are walked as whole name/value pairs, atomically, which both puts
# `href` at a real boundary and keeps the walk from backtracking into a
# quoted value.
# Each attribute is preceded by whitespace, and so is `href`. Without that
# separator the name could backtrack to the `data-` of `data-href` and match
# the rest as a real attribute -- the very case this exists to reject.
_HTML_ATTR = (r"""[a-zA-Z_:][-\w:.]*(?:\s*=\s*(?:"[^"]*"|'[^']*'"""
              r"""|[^\s"'`=<>]+))?""")
# `<img src>` rides the same scanner as `<a href>`. Both are destinations a
# reader resolves -- a missing image is exactly as broken as a missing link,
# and the audit was loud about one and silent about the other. Changing the
# PRESENTATION syntax should not change what the audit sees. The tag name and
# its attribute are one alternation rather than two patterns, so the two cannot
# drift apart. Parity with the Node twin (solyra#69).
HTML_HREF_RE = re.compile(
    rf"""<(?:a(?:\s+{_HTML_ATTR})*?\s+href|img(?:\s+{_HTML_ATTR})*?\s+src)\s*=\s*"""
    r"""(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<bare>[^\s"'`=<>]+))""",
    re.I | re.S)
# A label may carry an ESCAPED bracket: `[x\]]: missing.md` is a definition
# CommonMark registers, and stopping at that bracket collected nothing -- so a
# missing destination behind that spelling produced no finding at all.
REF_DEF_HEAD_RE = re.compile(
    r"^ {0,3}\[(?P<label>(?:\\.|[^\]\\^])(?:\\.|[^\]\\])*)\]:[ \t]*$")
REF_DEF_CONT_RE = re.compile(
    r"^[ \t]*(?P<target><(?:\\.|[^<>\\\n])*>|\S+)")
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
# A space is admitted in the FINAL segment only. `docs/Morning Checklist
# Updated.md` is tracked in this tree and cited in docs/BRIEFING_DECK.md, and
# the no-space pattern never matched it, so deleting the target reported clean.
# Spaces stay out of the directory part on purpose: the whole code span has to
# match, and a directory part that admitted them would let `run docs/a.md and
# docs/b.md` parse as one path and be reported dead -- a fabricated finding.
# With the restriction, that span fails at the leading `run `, where it should.
# `\w` rather than `A-Za-z0-9_`, because Python's `re` is Unicode by default
# and a tracked path may hold a non-ASCII character. The ASCII-only class never
# recognised a citation of a path like `docs/cafe.md` spelled with an accent,
# so deleting or renaming that file produced no dead-link finding at all --
# while the git inventory is deliberately decoded to preserve exactly such
# filenames and the equivalent percent-encoded Markdown link IS checked. The
# extension stays ASCII: a suffix is, and widening it would let ordinary prose
# end a "path".
# A git path may contain a SPACE, in EVERY segment and not only the filename.
# `docs/user guides/old.md` and a spaced root file `old guide.md` matched
# neither scanner, so a deleted citation written that way was reported clean --
# the hiding direction, and the same gap the filename fix closed one segment
# over. A space is admitted only BETWEEN name characters, never at either end,
# and the repository-layout guard downstream still requires the first segment
# to be a directory this tree actually has, which is what keeps ordinary
# backticked prose from reading as a path. Parity with the Node twin
# (solyra#69); Codex filed it here.
_PW = r"\w"
_PWS = rf"(?:{_PW}|[.-])(?:(?:{_PW}|[.-])| (?=(?:{_PW}|[.-])))*"
# The root form must still START with a name character, so a backticked
# `.eslintrc`-shaped string does not become a root-file citation.
_PWS_ROOT = rf"{_PW}(?:(?:{_PW}|[.-])| (?=(?:{_PW}|[.-])))*"
_LINE_SUFFIX = r"(?::\d+(?:-\d+)?)?"
BACKTICK_PATH_RE = re.compile(
    rf"`(?P<path>(?:{_PWS}/)+{_PWS}\.[A-Za-z0-9]{{1,10}}{_LINE_SUFFIX})`")

# The other shape a citation takes: a bare root-level filename. Requiring a
# slash meant `requirements-gcp.txt` and `alert_config.json` -- both cited
# exactly that way here -- could never produce a finding when deleted. A bare
# name is checked ONLY against the root files this tree actually tracks (see
# check_dead_links), because `v1.2` and `api.md` in prose are otherwise
# indistinguishable from a path.
BACKTICK_ROOT_FILE_RE = re.compile(
    rf"`(?P<path>{_PWS_ROOT}\.[A-Za-z0-9]{{1,10}}{_LINE_SUFFIX})`")

# The `:line` or `:start-end` suffix above, which is a citation's coordinate
# inside the file and not part of its path.
LINE_SUFFIX_RE = re.compile(r":\d+(?:-\d+)?$")

CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".mjs", ".sql", ".sh", ".yml", ".yaml", ".json", ".md"}


# A COMBINING MARK is part of the letter before it, not punctuation. An NFD
# heading -- `Cafe` + U+0301 -- renders as `Café` and GitHub's identifier
# keeps the mark, but `\w` does not match category M, so the slug came out
# `cafe`: the working encoded fragment rejected AND a `#cafe` the page does
# not expose accepted, wrong in both directions. Python's `re` has no
# `\p{M}`, so the marks are tested by category; the cache keeps that off the
# per-character path for the ASCII text that is almost all of it. Codex filed
# it on the Node twin (solyra#69), where `\p{M}` says the same thing.
_SLUG_STRIP_RE = re.compile(r"[^\w\s-]")


@functools.lru_cache(maxsize=4096)
def _is_combining(ch: str) -> bool:
    return unicodedata.category(ch).startswith("M")
# `## Install ##` renders as `Install`, and GitHub's anchor is `install`.
# Passing `Install ##` to heading_slug recorded `install-`, so a valid link to
# `#install` was reported dead. Raised on the Node twin (solyra#69).
# Up to three leading spaces, which CommonMark renders as a heading and the
# fence and Setext parsers here already admit. Requiring column zero meant
# `  ## Details` offered no anchor and a working link to `#details` was a
# gating finding. Four spaces is indented code, so the bound is load-bearing.
_HEADING_RE = re.compile(r"^ {0,3}#{1,6}\s+(.*?)(?:\s+#+)?\s*$", re.M)


# Well-formed references only -- `&name;`, `&#12;`, `&#x1F;`. A bare `&` is
# an ampersand and must stay one: `html.unescape` alone also decodes the
# semicolon-less legacy forms, so `AT&T Corp` would lose the `T`.
_CHAR_REF_RE = re.compile(r"&(?:[A-Za-z][A-Za-z0-9]{1,31}|#[0-9]{1,7}|#[Xx][0-9A-Fa-f]{1,6});")


def decode_char_refs(text: str) -> str:
    """HTML character references decoded, as a Markdown renderer decodes them."""
    return _CHAR_REF_RE.sub(lambda m: html.unescape(m.group(0)), text)



def decode_with_map(text: str) -> tuple[str, list[int] | None]:
    """The text with character references decoded, plus a map to the source.

    A destination is decoded before the reader's browser ever sees it, so
    `https://github&#46;com/TeneikaAskew/stocks/issues/1` is a link to the
    real issue -- but `ISSUE_URL_RE` scanned the SOURCE, where `github&#46;com`
    is not `github.com`, and a stale blocker cited that way passed the audit
    clean. Decoding alone is not enough: every offset the caller then uses --
    the hidden-span test, the clause the citation sits in -- indexes the
    source line, so the decoded index has to come back.

    `imap[i]` is the source index of decoded character `i`; a reference
    collapses to its OPENING index, so a citation spelled with one reports
    the position a reader would point at. `imap[len(decoded)]` is the end
    sentinel, which is what makes a match's exclusive end mappable. Text with
    no `&` in it cannot carry a reference and returns a None map, meaning
    "identity" -- which is every line of both corpora today, so the common
    path is byte-identical to the scan this replaced.

    Indexed in CODE POINTS, unlike the Node twin, where `out` is indexed in
    UTF-16 units and an astral character needs two entries (solyra#69).
    """
    if "&" not in text:
        return text, None
    out: list[str] = []
    imap: list[int] = []
    last = 0
    for m in _CHAR_REF_RE.finditer(text):
        for k in range(last, m.start()):
            out.append(text[k])
            imap.append(k)
        for ch in decode_char_refs(m.group(0)):
            out.append(ch)
            imap.append(m.start())
        last = m.end()
    if not imap:
        return text, None
    for k in range(last, len(text)):
        out.append(text[k])
        imap.append(k)
    imap.append(len(text))
    return "".join(out), imap


def _src_at(imap: list[int] | None, k: int) -> int:
    """A decoded index read back as a source index."""
    return k if imap is None else imap[k]


def _ref_key(label: str) -> str:
    """A reference label reduced to what CommonMark compares.

    Case-folded, trimmed, and with internal whitespace collapsed to one space
    -- `[foo bar]` and `[foo   bar]` are the SAME label, so keying on the raw
    text validated a duplicate definition independently and reported a
    destination no rendered reference resolves to. Every place that keys a
    label goes through here so the definition side and the use side cannot
    drift apart.
    """
    # CASEFOLD, not lower(). CommonMark compares labels by Unicode case
    # folding, under which `Stra\u00dfe` and `STRASSE` are the same label --
    # `.lower()` leaves the sharp s alone and made them two, so a heading
    # resolving one of them recorded the invented anchor `titlestrasse` and a
    # valid link to `#title` was reported dead. Codex filed it here.
    return re.sub(r"\s+", " ", label).strip().casefold()


def _balanced_close(text: str, at: int) -> int:
    """Index just past the `)` that closes the `(` at `at`, or -1.

    CommonMark allows a destination to carry balanced parentheses to any
    depth, and the regex alternative that handled it stopped at two -- so
    `[x](a(b(c)).md)` did not match at all and a deleted target with that
    spelling passed the audit clean. A scan has no depth limit to get wrong.
    A backslash escapes the character after it, there as everywhere.
    """
    depth = 0
    i, n = at, len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def _inline_link_end(text: str, at: int) -> int:
    """Index just past the `)` of a VALID inline-link suffix at `at`, or -1.

    `_balanced_close` alone answers a narrower question: it finds a matching
    parenthesis, not a link. `## [x](foo bar)` and `## [x](foo "unclosed)`
    both have one, and CommonMark renders each source literally -- so the
    heading stripper removed a suffix that is VISIBLE text, recorded `x`, and
    rejected a link to the real anchor while accepting a `#x` the page does
    not expose. The destination and title rules live in the `md_links`
    patterns; this shares them rather than restating them, so the two cannot
    come to disagree about what a link is. Codex filed it on the Node twin
    (solyra#69); the same hole was live here.
    """
    if at >= len(text) or text[at] != "(":
        return -1
    j = at + 1
    while j < len(text) and text[j].isspace():
        j += 1
    angle = _MD_LINK_ANGLE_RE.match(text, j)
    if angle:
        j = angle.end()
    else:
        j = _bare_destination(text, j, len(text))
        if j < len(text) and text[j] == "#":
            # The same balanced walk `md_links` makes. This was the second
            # implementation of one rule, so it stopped at a `)` inside a
            # fragment while the other did not -- and the two disagreed about
            # where a link ENDS, which is worse than either being wrong alone.
            j = _bare_fragment(text, j + 1, len(text))
    tail = _MD_LINK_TAIL_RE.match(text, j)
    return tail.end() if tail else -1


def _label_close(text: str, at: int) -> int:
    """Index of the `]` closing the `[` at `at`, honouring escapes, or -1.

    `str.find("]")` stops at an ESCAPED bracket, so `## [Guide][my\\]ref]`
    with a matching `[my\\]ref]: README.md` definition failed to resolve and
    slugged as `guidemyref`, while the page exposes `guide`. The label walk
    above this one already skipped escapes; this second scan did not.
    """
    j = at + 1
    while j < len(text):
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == "]":
            return j
        j += 1
    return -1


def _strip_heading_links(s: str, ref_labels: frozenset[str]) -> str:
    """A heading's visible text, with link syntax removed but labels kept.

    `## See [x](guide.md) now` renders as "See x now". Two shapes were wrong:
    a destination containing parentheses ended the old pattern at the first
    `)` and left `.md)` in the slug, and a REFERENCE link (`[guide][g]` with
    `[g]` defined) was not recognised at all, so its second label survived as
    `guideg`. Both were wrong in the same two directions -- a working fragment
    reported dead, and one the page does not expose accepted.

    A SHORTCUT reference (`[guide]` alone) is deliberately not resolved. This
    corpus is full of bracketed prose that is indistinguishable from one, and
    the existing REF_USE_RE measurement is why uses are not scanned elsewhere.
    """
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        # An escaped bracket is literal text, so it opens nothing.
        if ch == "\\" and i + 1 < n:
            out.append(s[i:i + 2])
            i += 2
            continue
        if ch != "[":
            out.append(ch)
            i += 1
            continue
        depth, j, end = 0, i, -1
        while j < n:
            if s[j] == "\\":
                j += 2
                continue
            if s[j] == "[":
                depth += 1
            elif s[j] == "]":
                depth -= 1
                if depth == 0:
                    end = j
                    break
            j += 1
        if end == -1:
            out.append(ch)
            i += 1
            continue
        label, k = s[i + 1:end], end + 1
        if k < n and s[k] == "(":
            close = _inline_link_end(s, k)
            if close != -1:
                out.append(label)
                i = close
                continue
        if k < n and s[k] == "[":
            shut = _label_close(s, k)
            if shut != -1:
                # A COLLAPSED reference (`[guide][]`) names itself.
                # Internal whitespace COLLAPSED, as CommonMark collapses it
                # when matching labels -- `[guide][my   ref]` resolves against
                # `[my ref]:`. Normalising only the DEFINITIONS left the use
                # unmatched, so the reference stayed literal bracket syntax
                # and slugged as `see-guidemy---ref`. Both sides key the same
                # way now, which is what makes them comparable at all.
                ref = _ref_key(s[k + 1:shut] or label)
                if ref in ref_labels:
                    out.append(label)
                    i = shut + 1
                    continue
        out.append(ch)
        i += 1
    return "".join(out)


# A code span delimited by a matching run of backticks, contents in group 2.
_CODE_SPAN_RUN_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.S)


# One complete HTML tag: a name, optional attributes whose quoted values may
# contain `>`, and the close. Walked rather than excluded, because `[^<>]*`
# stopped inside `data-x="a>b"` and left `b">` to be slugged as visible text.
# The attribute grammar CommonMark actually specifies, not "anything that is
# not an angle bracket". `## A <span ???>B` renders the tag-shaped text
# LITERALLY and anchors `a-span-b`, but the permissive form matched it and
# recorded `a-b` -- a valid fragment link rejected and a nonexistent one
# accepted, the usual pair. An attribute is a name, optionally followed by a
# value that is unquoted, single-quoted or double-quoted. Codex filed it on
# the Node twin (solyra#69); the same pattern was here.
_HTML_TAG_RE = re.compile(
    r"""<[A-Za-z][A-Za-z0-9-]*"""
    r"""(?:\s+[A-Za-z_:][A-Za-z0-9_.:-]*"""
    r"""(?:\s*=\s*(?:[^\s"'=<>`]+|'[^']*'|"[^"]*"))?)*"""
    r"""\s*/?>"""
    r"""|</[A-Za-z][A-Za-z0-9-]*\s*>""")


def _strip_heading_tags(s: str) -> str:
    r"""Inline HTML removed from heading text, escapes left as they are.

    `## Hello <em>world</em>` renders as "Hello world", so the tag names are
    not part of the anchor. An ESCAPED `<` opens nothing: CommonMark renders
    `## \<em>foo` as the literal text `<em>foo`, whose id is `emfoo`, and an
    unconditional substitution removed the tag-shaped run and recorded `foo`
    -- a working `#emfoo` link rejected and a nonexistent `#foo` accepted.
    An AUTOLINK is not a tag either: `## <https://example.com>` renders as the
    URL, and only a tag NAME is matched, never a `<scheme:...>`.
    """
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        if s[i] == "\\" and i + 1 < n:
            out.append(s[i:i + 2])
            i += 2
            continue
        m = _HTML_TAG_RE.match(s, i)
        if m:
            i = m.end()
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def _code_span_text(body: str) -> str:
    """A code span's contents as they RENDER.

    CommonMark strips one leading AND trailing space when the content begins
    and ends with one and is not all spaces, so `` ` foo ` `` renders `foo`
    and anchors `a-foo-b` rather than `a--foo--b`. Line endings inside a span
    render as spaces for the same reason the surrounding text's do.
    """
    body = re.sub(r"\r\n|\r|\n", " ", body)
    if len(body) >= 2 and body[0] == " " and body[-1] == " " and body.strip():
        body = body[1:-1]
    return body


def _heading_markup(part: str, ref_labels: frozenset[str]) -> str:
    """The markup passes that must NOT see code-span contents.

    Character references, link syntax and inline HTML are all markup in
    ordinary heading text and literal characters inside a code span, so each
    runs per part rather than over the whole heading.
    """
    # Tags BEFORE character references are decoded. A `<` that a reference
    # PRODUCES is literal text, not markup: `## &lt;em&gt;foo` renders the
    # characters `<em>foo` and anchors `emfoo`, and decoding first handed the
    # tag stripper something the source never contained -- recording `foo`,
    # so a working link was rejected and a nonexistent one accepted.
    part = _strip_heading_tags(part)
    part = decode_char_refs(part)
    # See _strip_heading_links: the destination is scanned rather than
    # matched, so parentheses inside it cannot end it early, and a DEFINED
    # reference link resolves to its visible label.
    return _strip_heading_links(part, ref_labels)


def heading_slug(heading: str,
                 ref_labels: frozenset[str] = frozenset()) -> str:
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
    # A character reference is RENDERED before GitHub derives the id, so
    # `## AT&amp;T` is `AT&T` on the page and its working fragment is `#att`.
    # Keeping the letters `amp` recorded `atampt` instead -- wrong in both
    # directions at once: a valid link to `#att` read as a dead anchor, and a
    # bogus `#atampt` was accepted. Outside code spans only, because
    # CommonMark treats a reference inside one as literal text: `` `&amp;` ``
    # renders the six characters, not an ampersand.
    # Tokenised on a matching backtick RUN, and the parts are processed
    # separately. A code span renders its contents LITERALLY, so the link, tag
    # and character-reference passes below must not see them: unwrapping the
    # span first handed `` `[x](y)` `` to the link stripper, which discarded
    # the destination and recorded `x` where GitHub exposes `xy`. The run form
    # matters too -- `` ``[x](y)`` `` is one span, and a single-backtick
    # pattern saw no span at all.
    literal: list[str] = []
    at = 0
    for mm in _CODE_SPAN_RUN_RE.finditer(heading):
        literal.append(_heading_markup(heading[at:mm.start()], ref_labels))
        literal.append(_code_span_text(mm.group(2)))
        at = mm.end()
    literal.append(_heading_markup(heading[at:], ref_labels))
    s = "".join(literal)
    # Only where the opening bracket is NOT escaped. `## Literal \\[x](guide.md)`
    # renders the brackets and the destination as TEXT -- CommonMark makes no
    # link -- so GitHub's anchor includes `xguidemd`, while stripping the
    # destination unconditionally recorded `literal-x`: a working fragment
    # reported dead AND an anchor the page does not expose accepted.
    # Inline HTML is MARKUP and does not belong to the visible text:
    # `## Hello <em>world</em>` renders as "Hello world" and GitHub's id is
    # `hello-world`, but keeping the tag names recorded `hello-emworldem` --
    # a valid link to `#hello-world` reported dead AND the invented fragment
    # accepted. An AUTOLINK is not a tag: `## <https://example.com>` renders
    # as the URL and derives a real anchor from it, so only a tag NAME is
    # stripped, never a `<scheme:...>` or a bare `<` in prose.
    # Quoted attribute values may CONTAIN `>`. `[^<>]*` stopped at the one
    # inside `data-x="a>b"` and left `b">` to be slugged as visible text, so
    # `## <span data-x="a>b">Hello</span>` recorded `bhello` -- the valid
    # fragment rejected and one the page does not expose accepted.
    # Emphasis MARKUP only. Stripping every underscore turned `## API_FIELD`
    # into `apifield`, so a valid link to `#api_field` read as a dead anchor
    # AND an incorrect `#apifield` was accepted -- wrong in both directions.
    # CommonMark does not treat an intraword `_` as emphasis.
    # UNESCAPED first. CommonMark removes the escape and renders
    # `## API\_FIELD` as `API_FIELD`, whose slug keeps the intraword
    # underscore -- but the raw backslash sat between the letter and the `_`,
    # so the lookbehind saw no word character, the underscore was stripped as
    # emphasis and the audit recorded `apifield`: a valid link to `#api_field`
    # rejected AND a nonexistent `#apifield` accepted. The escape is markup
    # either way, so removing it before the classification loses nothing.
    # An ESCAPED emphasis character is literal text and must survive the
    # strip below. Unescaping first was right for the INTRAWORD case
    # (`API\_FIELD` keeps its underscore) and wrong at a boundary: `## \_foo`
    # renders `_foo`, whose GitHub id keeps the underscore, but the escape was
    # gone by the time the boundary rule ran and the audit recorded `foo` --
    # a working `#_foo` link rejected and a nonexistent `#foo` accepted. The
    # escaped characters are parked out of the pattern's reach instead, which
    # leaves the intraword case exactly as it was.
    # Only the underscore is parked: an asterisk is stripped by the slug rule
    # below whether or not the emphasis pass removed it, so protecting one
    # would change no output -- measured, not assumed.
    s = re.sub(r"\\_", "\x00", s)
    s = unescape_markdown(s)
    s = re.sub(r"\*", "", s)
    s = re.sub(r"(?<!\w)_+|_+(?!\w)", "", s)
    s = s.replace("\x00", "_").strip().lower()
    # EVERY run of rendered whitespace, not only the literal space.
    # `## Hello<TAB>World` anchors as `hello-world` on GitHub, but keeping the
    # tab recorded an unusable slug -- so a valid `#hello-world` link was a
    # gating dead anchor while the tab-bearing spelling nothing exposes was
    # accepted. Parity with the Node twin (solyra#69).
    return re.sub(r"\s", "-",
                  _SLUG_STRIP_RE.sub(
                      lambda m: m.group(0) if _is_combining(m.group(0)) else "", s))


def _drop_spans(line: str, spans: list[tuple[int, int]]) -> str:
    """The line with `spans` REMOVED rather than blanked.

    `mask_spans` keeps every other offset where it was, which is what a
    scanner reporting positions needs. A heading's SLUG is whitespace
    sensitive -- runs are not collapsed -- so blanking turned
    `## Hello <!-- note --> Real` into `hello---------------real` where GitHub
    exposes `hello--real`, and pushed a comment sitting before the `#` past
    the three-column limit so the heading stopped matching at all. Nothing
    downstream of this reads an offset.
    """
    out: list[str] = []
    at = 0
    for lo, hi in sorted(spans):
        if lo > at:
            out.append(line[at:lo])
        at = max(at, hi)
    out.append(line[at:])
    return "".join(out)


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
    # Indented code too. `    Fake` followed by `---` is a code block and a
    # thematic break, not a Setext heading -- omitted here,
    # is_setext_underline recorded a `fake` anchor that the rendered document
    # does not offer, so a link to it PASSED. marker_window already excludes
    # indented code for the same reason.
    # And raw HTML blocks. `<pre>` or `<div>` makes the Markdown inside render
    # literally, so `# Heading` there is text -- recording its slug invented an
    # anchor the document does not offer and a link to that fragment PASSED.
    fenced = (fenced_lines(lines) | commented_lines(lines)
              | indented_code_lines(lines) | raw_html_block_lines(lines)
              # And YAML front matter, which GitHub renders as a metadata
              # table rather than as Markdown -- a `# note` inside it exposes
              # no anchor, and recording one let a link to it pass.
              | front_matter_lines(lines))
    # The reference labels this document DEFINES, so a heading carrying
    # `[guide][g]` can resolve to its visible label. Undefined ones must not
    # resolve: CommonMark renders `[guide][g]` literally when `[g]` is not
    # defined, and the slug keeps both labels. Read through the same
    # exclusions as everything else here -- a definition inside a fence or a
    # comment defines nothing.
    # And only where a definition may BEGIN. `paragraph` then `[g]: x.md`
    # renders literally -- CommonMark registers no reference there -- so
    # collecting it let `## [Guide][g]` resolve to `guide` when the page
    # actually exposes `guideg`. The dead-link scan's own definition collector
    # is the other half of this rule and validated such a line as a live
    # destination -- a gating finding over text that produces no link -- until
    # it was given the same test; the two now share `_paragraph_blocks` so
    # they cannot disagree about where a definition may begin.
    _blocks = _paragraph_blocks(lines, fenced)
    # Which line each paragraph block STARTS on, for the Setext branch below.
    _setext_starts = {i: lo for lo, hi in _blocks for i in range(lo, hi + 1)}
    _def_starts = {lo for lo, _ in _blocks}
    _def_seen: set[int] = set()
    _labels: set[str] = set()
    for i, ln in enumerate(lines):
        if i in fenced:
            continue
        stripped = _LIST_MARKER_RE.sub(
            "", _BLOCKQUOTE_PREFIX_RE.sub("", ln, count=1), count=1)
        mm = REF_DEF_RE.match(stripped)
        # The REMAINDER has to be a definition too -- see REF_DEF_TAIL_RE.
        if mm is not None and not REF_DEF_TAIL_RE.match(stripped, mm.end()):
            mm = None
        # The destination may sit on the FOLLOWING line. `[g]:` over
        # `  guide.md` defines `g`, so `## See [guide][g]` renders anchored
        # `see-guide` -- and reading only the single-line form recorded
        # `see-guideg` and reported a working fragment link dead. The
        # dead-link pass has read both forms since it was raised; this
        # collector read one, which is the same two-halves shape as the
        # block-start rule it sits beside.
        last = i
        if mm is None:
            head = REF_DEF_HEAD_RE.match(stripped)
            j = i + 1
            if (head and j < len(lines) and j not in fenced
                    and REF_DEF_CONT_RE.match(
                        _BLOCKQUOTE_PREFIX_RE.sub("", lines[j], count=1))):
                mm, last = head, j
        if not mm or not (i in _def_starts or (i - 1) in _def_seen):
            continue
        _def_seen.add(last)
        _labels.add(_ref_key(mm.group("label")))
    ref_labels = frozenset(_labels)
    # A comment INSIDE a rendered heading is not part of its text. `## <!-- note
    # --> Real` slugged to `---note----real`, so a valid link to `#real` was
    # emitted as a gating dead-anchor finding AND the fabricated anchor was
    # accepted -- wrong in both directions at once. Spans, because the heading
    # around the comment still renders.
    heading_hidden = comment_spans(lines)
    for i, line in enumerate(lines):
        if i in fenced:
            continue
        line = _drop_spans(line, heading_hidden.get(i, []))
        # Setext (`Title` over `===` or `---`) renders as a heading and
        # GitHub exposes its anchor, but an ATX-only scan recorded none -- so a
        # valid link to one was emitted as a gating dead-anchor finding.
        # The blockquote container is stripped: `> ## Quoted` RENDERS as a
        # heading and GitHub exposes its anchor, but matching the raw line
        # recorded none -- so a valid link to it was emitted as a gating
        # dead-anchor finding, the direction that makes an audit untrustworthy
        # rather than incomplete. The Node twin has read these since solyra#69.
        line = _BLOCKQUOTE_PREFIX_RE.sub("", line, count=1)
        setext = (i + 1 < len(lines)
                  and is_setext_underline(lines, i + 1, fenced))
        # A LIST MARKER is a container prefix too. `- # Install` and
        # `1. ## Setup` render real headings and GitHub exposes their anchors,
        # but stripping only the blockquote prefix left the marker in front of
        # the ATX syntax -- so the anchor was omitted and a valid link to it
        # was a gating dead-anchor finding. The ATX branch only: for Setext,
        # `- Example` over a column-zero `---` ENDS the list and renders a
        # thematic break, which is_setext_underline already refuses, and
        # stripping the marker there would invent a heading. Ported from the
        # Node twin (solyra#69).
        m = _HEADING_RE.match(_LIST_MARKER_RE.sub("", line, count=1))
        if not (m or setext):
            continue
        # The LIST MARKER is stripped for a Setext heading too. `- Title`
        # over an indented `===` is a heading is_setext_underline deliberately
        # accepts, but the raw `- Title` reached the slug and recorded
        # `--title` -- so a working `#title` fragment was reported dead while
        # a `#--title` the page does not expose was accepted. Safe here
        # precisely because is_setext_underline already refuses the case the
        # ATX-only comment above was guarding: `- Example` over a column-zero
        # `---` ends the list and renders a thematic break.
        # A Setext heading is the WHOLE paragraph above its underline, not
        # just the last line: `Hello` over `world` over `---` renders one
        # heading anchored `hello-world`. Slugging the final line alone
        # recorded `world`, so the real fragment was reported dead and one the
        # page does not expose was accepted. The lines are joined with a
        # space, which is how the soft break renders.
        if setext:
            lo = _setext_starts.get(i, i)
            # Each line read through the SAME comment mask the ATX branch
            # applies. This branch rereads the raw text, so `Hello <!-- note
            # -->` over `---` slugged `hello----note---`: the valid `#hello`
            # fragment reported dead and an anchor the page does not expose
            # accepted -- wrong in both directions, from one pass missing a
            # mask its sibling already had.
            text = " ".join(
                _BLOCKQUOTE_PREFIX_RE.sub(
                    "", _drop_spans(ln, heading_hidden.get(k, [])),
                    count=1).strip()
                for k, ln in enumerate(lines[lo:i + 1], lo))
            head_text = _LIST_MARKER_RE.sub("", text.strip(), count=1)
        else:
            head_text = m.group(1)
        base = heading_slug(head_text, ref_labels)
        n = seen.get(base, 0)
        slug = base if n == 0 else f"{base}-{n}"
        while slug in out:
            n += 1
            slug = f"{base}-{n}"
        seen[base] = n + 1
        out.add(slug)
    # EXPLICIT HTML anchors. `<a name="legacy"></a>` and any `id="..."` are
    # rendered destinations a browser honours, so `[x](#legacy)` is valid with
    # no heading of that name -- and indexing only heading slugs made the
    # dead-anchor check reject it and fail --check. Ported from the Node twin
    # (solyra#69).
    out |= html_anchors(lines)
    return out


def html_anchors(lines: list[str]) -> set[str]:
    """Ids a RENDERED document exposes through `id=` or `name=` attributes.

    Tokenised through the same tag scanner the attribute mask uses, rather
    than by searching for `id=` in arbitrary text. A loose search invented
    anchors from `<div data-note=" id=fake">`, where the text sits inside
    ANOTHER attribute's value, and missed the real one in
    `<div title="a > b" id="section">`, where the `>` inside a quoted value
    ended the search early -- wrong in both directions at once, and the
    invented ids were the worse half, because a link to one PASSED.

    `id` exposes a fragment destination on any element. `name` does so only
    on an anchor: `<meta name="viewport">` is not a destination, and
    recording it let a link to `#viewport` pass against nothing. An ESCAPED
    opener is not an element at all.

    A NARROWER mask than the heading scan's: a type-6 or type-7 block such as
    `<div id="x">` IS the anchor, so masking every HTML line would discard the
    very thing being read. Only the raw-text kinds -- `<pre>`, `<script>`,
    `<style>`, `<textarea>` -- display their contents instead of rendering
    them, and only those hide an id.

    One scan over the joined document, so an element whose `id` sits on a
    LATER physical line is read as the one tag it is.
    """
    # The raw-text OPENERS are held back from the whole-line mask: the opening
    # tag is rendered, so `<pre id="sample">code</pre>` offers `sample` while
    # only `code` is literal -- and masking the whole line reported a working
    # link to `#sample` as a gating dead anchor. Codex filed it. The content
    # after the tag is still masked below, so a `<pre><a id="fake"></a></pre>`
    # written on one line still invents nothing.
    raw_open: dict[int, int] = {}
    literal = (raw_html_block_lines(lines, raw_text_only=True, openers=raw_open)
               | fenced_lines(lines) | indented_code_lines(lines)
               | front_matter_lines(lines))
    wrapped = code_span_lines(lines)
    comments = comment_spans(lines)
    # Comment SPANS as well as code spans. `text <!-- <a id="fake"></a> -->`
    # shares a line with prose, so a whole-line exclusion never reached it and
    # `fake` was registered as a destination the document does not offer.
    # A link's DESTINATION and TITLE are metadata: tag-shaped text in either
    # renders inside a URL or a `title` attribute, never as an element, and
    # reading it as one invented an anchor a link could then resolve against.
    link_meta = link_meta_spans(lines, title_only=False)
    def _literal_span(i: int, line: str) -> list[tuple[int, int]]:
        start = raw_open.get(i)
        if start is None:
            return [(0, len(line))]
        tag = _TAG_OPEN_RE.match(line, start)
        # An unparseable opener offers no id anyway, so the whole tag is
        # masked with its contents; text BEFORE it is live prose either way.
        return [(start if tag is None else tag.end(), len(line))]

    joined = "\n".join(
        mask_spans(line, _literal_span(i, line)) if i in literal
        else mask_spans(line, code_spans(line) + wrapped.get(i, [])
                        + comments.get(i, []) + link_meta.get(i, []))
        for i, line in enumerate(lines))
    out: set[str] = set()
    for tag in _TAG_OPEN_RE.finditer(joined):
        # `\<div id="fake">` is TEXT. CommonMark renders the escaped `<`
        # literally and creates no element, so there is nothing for `#fake` to
        # reach -- but the scan parsed it like any other tag and registered the
        # id, which made a link to a destination the document does not offer
        # PASS. Documents that demonstrate tag syntax escape it exactly this
        # way, so the invented anchors land in the docs most likely to be
        # audited for them.
        if is_escaped(joined, tag.start()):
            continue
        name = _TAG_NAME_RE.match(tag.group(0))
        anchor = bool(name) and name.group(1).lower() == "a"
        # The FIRST occurrence of a repeated attribute is the one that exists.
        # HTML parsing drops the later duplicates, so `<div id="real"
        # id="fake">` offers only `real` -- and recording both let a link to
        # `#fake` pass the dead-anchor check against a destination the page
        # does not have. Codex filed it on the Node twin (solyra#69).
        seen: set[str] = set()
        for attr in _TAG_ATTR_RE.finditer(tag.group(0)):
            key = attr.group(1).lower()
            if key in seen:
                continue
            seen.add(key)
            if key != "id" and not (key == "name" and anchor):
                continue
            value = attr.group(2)
            if value is None:
                value = attr.group(3)
            if value is None:
                value = attr.group(4)
            # Character references DECODED, as the heading slug already
            # decodes them: `<div id="a&amp;b">` exposes `a&b`, and recording
            # the raw value reported a valid `[x](#a%26b)` dead. Case is
            # PRESERVED: a browser matches an explicit id exactly, so
            # `<a name="Install">` is reached by `#Install` and not `#install`.
            ident = decode_char_refs(value or "")
            if ident:
                out.add(ident)
    return out


def link_meta_spans(lines: list[str], *, title_only: bool = True
                    ) -> dict[int, list[tuple[int, int]]]:
    """Offset ranges covering an inline link's metadata, per line index.

    A TITLE renders as the anchor's `title` attribute -- a tooltip, not body
    text, and never a followable citation. With `title_only` off the
    DESTINATION goes too, which is what the anchor scan wants: tag-shaped
    text in either renders inside a URL or a `title` attribute rather than as
    an element, so `[x](README.md "<div id=fake>")` was registering an anchor
    that exists nowhere and a link to `#fake` passed against it.

    The destination is deliberately KEPT visible for the blocker scan: an
    issue URL written there is a link a reader can follow, so it is a
    citation. That is the same split `tag_attribute_spans` makes for `href`,
    one syntax over. Codex filed both halves on the Node twin (solyra#69).
    """
    out: dict[int, list[tuple[int, int]]] = {}
    for i, line in enumerate(lines):
        spans = []
        for m in md_links(line):
            lo = m.dest_end if title_only else m.dest_start
            hi = m.end() - 1
            if hi > lo:
                spans.append((lo, hi))
        if spans:
            out[i] = spans
    return out


def decode_fragment(frag: str) -> str:
    """The anchor a browser resolves, from the spelling a link carries.

    `#caf%C3%A9` is how a link to `## Caf\u00e9` is written, and it works;
    comparing the encoded spelling against the decoded slug reported it dead.
    `unquote` leaves an invalid escape (`100%-done`) exactly as it is, which is
    what makes this safe to apply to every fragment rather than guessing which
    ones are encoded.
    """
    # And character references: `#caf&eacute;` is how a link to `## Café` may
    # be written and it resolves, while comparing the encoded spelling against
    # the decoded slug reported it dead.
    # And MARKDOWN ESCAPES, which the destination path has consumed for rounds
    # and this had not: `[x](#foo\:bar)` reaches `id="foo:bar"`, and comparing
    # the source spelling reported a working link as a gating dead anchor.
    # Same order the destination uses, and the order RENDERING uses: escapes
    # and references are resolved when the link is parsed, percent-decoding is
    # the browser's and comes last. The reference pass used to run after
    # `unquote`, which is the browser's step happening before the parser's.
    # Codex filed the missing escape pass on the Node twin (solyra#69); the
    # same gap was live here, and the order is now identical in both.
    return urllib.parse.unquote(decode_char_refs(unescape_markdown(frag)))


def split_outside_refs(text: str, delim: str) -> tuple[str, str | None]:
    """Split at the first `delim` that is neither escaped nor inside a reference.

    A backslash escape and a character reference are each consumed as a UNIT,
    exactly as the inline-link destination scan consumes them: `a\\#b.md` targets
    the tracked `a#b.md`, and `a&\\#35;b.md` keeps its reference. A raw
    `partition("#")` split both at the `#` inside the escape and reported the
    path `a\\` dead. The search runs over a copy with each unit blanked to the
    same length, so the index still applies to the ORIGINAL and the caller
    decodes exactly what it decoded before.
    """
    probe = re.sub(r"\\.|&\#?[0-9A-Za-z]{1,32};",
                   lambda m: "_" * len(m.group(0)), text)
    at = probe.find(delim)
    return (text, None) if at == -1 else (text[:at], text[at + 1:])


def strip_dot_segments(path: str) -> str:
    """`./scripts/tool.py` and `scripts/tool.py` are the same repository path.

    Callers compare against `git ls-tree` output, which never carries a
    leading `./`, and split on the first `/` to find the top-level directory.
    Without this the root-relative form yields the component `.`.
    """
    while path.startswith("./"):
        path = path[2:]
    # And an INTERNAL parent segment, which is the same repository path written
    # the long way: `docs/../scripts/tool.py` IS `scripts/tool.py`. It used to
    # be routed through the document-relative branch instead and resolved
    # against the citing document's directory, so a valid citation of a tracked
    # file was reported dead. normpath resolves from the repository root, which
    # is what a path with no leading `../` already means; one that climbs out
    # is not this repository's to resolve and the caller declines it.
    # And an INTERNAL current-directory segment, for the same reason:
    # `scripts/./tool.py` NAMES the tracked `scripts/tool.py`, and leaving the
    # long spelling alone meant the citation was absent from `tracked` and
    # reported as a gating dead link against a file that exists. Only the
    # leading one was stripped, above, and only `/../` was normalised below --
    # two thirds of one rule. Codex filed it (stocks#1121).
    if "/../" in path or "/./" in path:
        path = posixpath.normpath(path)
        if path.startswith(".."):
            return path
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
    # Only a LEADING `../` is document-relative. An internal parent segment in
    # an otherwise repo-relative path -- `docs/../scripts/tool.py` -- was joined
    # to the citing document's directory and resolved to
    # `docs/scripts/tool.py`, so a valid citation of the tracked
    # `scripts/tool.py` was reported dead. Internal dot segments normalise from
    # the repository root, which is what the path already meant.
    if cited.startswith("../"):
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
    # A command that cannot be LAUNCHED raises before a result exists --
    # `gh` missing from PATH is the reachable case, since the issue and
    # owning-job reads need it on the default invocation. That exception went
    # past the AuditError handler, printed a traceback and exited 1: the
    # status documented for FINDINGS, so automation could not tell "the audit
    # did not run" from "the documentation is wrong".
    # Bytes, decoded LENIENTLY. `text=True` decodes strictly, so `git show`
    # on a document containing invalid UTF-8 raised UnicodeDecodeError -- past
    # the AuditError handler, a traceback and exit 1, the status documented for
    # FINDINGS. The working-tree read of the same document already uses
    # `errors="replace"`, so strict decoding here made the two halves of one
    # comparison disagree about whether the file is readable at all. This is
    # not a silent fallback: the lossy read is the contract the other half
    # already states, and the alternative is a crash rather than an answer.
    try:
        proc = subprocess.run(cmd, cwd=cwd or REPO, capture_output=True)
    except OSError as exc:
        raise AuditError(
            f"{cmd[0]} could not be run ({exc}); the audit did not happen") from exc
    stderr = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode != 0 and proc.returncode not in ok_exit_codes:
        raise AuditError(f"{' '.join(cmd[:4])}... exited {proc.returncode}: {stderr.strip()[:400]}")
    return proc.stdout.decode("utf-8", errors="replace")


def git_paths(cmd: list[str]) -> list[str]:
    r"""Paths from a `-z` git read, NUL-split.

    Without `-z`, git C-QUOTES any path outside the configured charset and
    wraps it in double quotes: `docs/caf\u00e9.md` comes back as the eleven
    literal characters `"docs/caf\303\251.md"`. Newline-separated output then
    splits fine and every downstream comparison misses -- the document is
    absent from the inventory, its links resolve against a name nothing holds,
    and a link TO it reads as dead. `-z` disables the quoting entirely and
    terminates each record with NUL, which no path may contain, so this is
    also the only split that survives a path with a newline in it.

    Measured on this tree: `git ls-tree -r HEAD --name-only` returns
    `"docs/caf\303\251.md"`; the same read with `-z` returns `docs/caf\u00e9.md`.
    """
    # Inserted after the SUBCOMMAND, not appended: `git ls-files ... -- "*.md"`
    # ends in a pathspec, and a trailing `-z` there is read as another pathspec
    # rather than as a flag. That silently left the output newline-separated,
    # so the single `.split("\0")` returned one string with the newline still
    # on it and every path carried a trailing blank line.
    return [p for p in run(cmd[:2] + ["-z"] + cmd[2:]).split("\0") if p]


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


def split_table_row(line: str) -> list[str]:
    """Cells of a GFM table row, splitting on unescaped pipes only.

    `split("|")` cut `line:^(foo\\|bar)$` in half at the escaped pipe, so the
    region was truncated to `line:^(foo\\` -- which then raised an audit error
    instead of applying the ownership rule the row declares. GFM: a pipe is
    included in a cell by escaping it, including inside other inline spans.

    Only `\\|` is unescaped. Every other backslash pair is left exactly as
    written, because these cells carry REGULAR EXPRESSIONS: unescaping `\\.`
    to `.` would silently widen `line:^\\.env` to match any character.
    """
    cells: list[str] = []
    cur: list[str] = []
    k = 0
    while k < len(line):
        ch = line[k]
        if ch == "\\" and k + 1 < len(line):
            cur.append("|" if line[k + 1] == "|" else line[k:k + 2])
            k += 2
            continue
        if ch == "|":
            cells.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        k += 1
    cells.append("".join(cur))
    # The leading and trailing delimiters produce empty edge cells, which the
    # `strip("|")` this replaced removed. Exactly-empty, not blank: a cell of
    # spaces is a declared-empty column and the caller reports it.
    while cells and cells[0] == "":
        cells.pop(0)
    while cells and cells[-1] == "":
        cells.pop()
    return cells


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
    all_lines = text.split("\n")
    # A row SHOWN rather than declared is not a rule. The registry documents
    # its own format, and every way of showing a sample row -- a fenced block,
    # an indented sample, a raw-text `<pre>`, a comment -- was executed as live
    # configuration: a fabricated missing-path finding, or worse, a
    # classification silently applied to a real path. A heading-shaped line
    # inside the same example could also switch the section off and drop every
    # real row below it. The Node twin (solyra#69) grew these four one at a
    # time; this collector had none of them.
    example = (fenced_lines(all_lines) | commented_lines(all_lines)
               | indented_code_lines(all_lines)
               | raw_html_block_lines(all_lines, raw_text_only=True))
    for i, raw in enumerate(all_lines):
        if i in example:
            continue
        line = raw.strip()
        # A SETEXT heading ends the section too. Neither `Examples` nor its
        # `--------` underline starts with `#`, so section mode stayed on and
        # an illustrative table below it was executed as live classification.
        # The heading is the line ABOVE the underline, so the section ends
        # there.
        if is_setext_underline(all_lines, i, example):
            in_registry = False
            continue
        # ATX SYNTAX, not a leading "#". A hash run needs whitespace or an
        # end of line after it to render as a heading, so `#123 remains open`
        # is ordinary prose -- and it switched section mode off, silently
        # dropping every declaration below it. A row that vanishes takes its
        # class, its code paths and its region ownership with it, and nothing
        # reports the skip. Ported from the Node twin (solyra#69).
        if re.match(r"#{1,6}(?:\s|$)", line):
            # EXACTLY, allowing only the optional closing-hash form. A later
            # `## Registry examples` section shares the prefix, so it re-entered
            # registry mode and parsed its illustrative table as live
            # classification rules -- explanatory prose becoming executable
            # configuration.
            in_registry = bool(re.fullmatch(
                re.escape(REGISTRY_HEADING) + r"\s*#*\s*", line))
            continue
        if not in_registry or not line.startswith("|"):
            continue
        cells = split_table_row(line)
        if len(cells) < 2:
            continue
        # And no MORE than the four declared columns. An unescaped pipe in a
        # value -- a `line:^foo|bar$` region pattern is the shape -- splits
        # into a fifth cell, and the parser silently kept `line:^foo` and
        # dropped `bar$`: a BROADER ownership map than the row displays, so
        # hand-written lines routed as generated and stamping decisions came
        # from a declaration nobody wrote. Refused rather than truncated,
        # because the truncation is invisible in the rendered table.
        if len(cells) > 4 and _cell(cells[0]).upper() in {"A", "B", "C", "D", "X"}:
            raise AuditError(
                f"{REGISTRY}: a class {_cell(cells[0]).upper()} row has "
                f"{len(cells)} cells where the table declares 4 -- an unescaped "
                "`|` in a value splits it, and the parser would read a broader "
                "declaration than the row displays; escape it as `\\|`")
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
        if not glob:
            # Dropping the row silently discarded its region ownership and its
            # declared code paths with it, so a Class A document could fall
            # through to a broader Class D rule and be stamped and routed as
            # hand-written content with no finding that the row was malformed.
            raise AuditError(
                f"{REGISTRY}: a class {cls} row has an empty path glob, so it "
                "declares ownership of nothing; give it a glob or remove the row")
        # A glob with a space used to be kept only when it ended `.md`, which
        # silently dropped every other real path carrying one -- a Class A
        # `docs/Generated Diagram.drawio` fell through to a broader Class D
        # rule and lost its code paths and region ownership with no finding
        # anywhere. A space is valid in a git path, so the extension decides
        # nothing; what the row must still look like is a PATH.
        if " " in glob and not ("/" in glob or "." in glob):
            raise AuditError(
                f"{REGISTRY}: a class {cls} row declares `{glob}`, which carries a "
                "space but has neither a directory nor an extension, so it cannot "
                "be a path glob; the registry table takes paths, not prose")
        paths = []
        if len(cells) > 2 and _cell(cells[2]) not in {"", "—", "-"}:
            paths = [_cell(p) for p in cells[2].split(",") if _cell(p)]
        regions = []
        if len(cells) > 3 and _cell(cells[3]) not in {"", "—", "-"}:
            regions = [_cell(r) for r in cells[3].split(";") if _cell(r)]
        rows.append({"cls": cls, "glob": glob, "code_paths": paths, "regions": regions})
    return rows


def registry_rule_key(row: dict) -> tuple:
    """What a registry row DECLARES, for comparing two equally specific rows.

    The code-path and region columns are SETS: `lib/a, lib/b` and
    `lib/b, lib/a` declare the same thing and drive identical checks, yet a
    positional tuple compared them unequal and raised a gating P1 over a
    disagreement the registry does not contain -- which also made
    `classification_is_ambiguous` refuse `--stamp`. Sorted, so order is not a
    decision.

    Named, because `classification_is_ambiguous` carried a COPY of this tuple
    and its docstring claimed the two could not disagree about what a tie
    means. They could, and after the sort went into one of them they did.
    """
    return (row["cls"], tuple(sorted(row.get("code_paths") or ())),
            tuple(sorted(row.get("regions") or ())))


def glob_specificity(glob: str) -> tuple:
    """How specific a registry glob is, most significant first.

    Raw character length is not specificity: `docs/[a-z]*.md` is longer than
    `docs/a.md`, so a wildcard row outranked the exact row it overlaps -- and
    because the lengths DIFFER, the tie that would have raised an ambiguity
    finding never happened, so a machine-owned document could be classified
    writable and `--stamp` could modify it. An exact row wins outright; among
    wildcards, the one matching more literal characters, and failing that the
    one using fewer open-ended wildcards, is the more specific.

    Ported from the Node twin (solyra#69), which has ranked this way for
    rounds; this side still compared `len(glob)`. The comments there record
    the four narrowings each of which was its own defect: a `**/` segment is
    ranked DOWN rather than counted as literal, a bracket expression counts as
    ONE position rather than as its contents, and `?` is counted with the
    literals it stands in for because it constrains width where `*` does not.
    """
    wildcards = len(re.findall(r"[*?\[]", glob))
    recursive = len(re.findall(r"\*\*", glob))
    literals = len(re.sub(r"[*?]", "",
                          re.sub(r"\[[^\]]*\]", "",
                                 re.sub(r"\*\*/", "", glob))))
    fixed = len(re.findall(r"\?", glob)) + len(re.findall(r"\[[^\]]*\]", glob))
    stars = wildcards - fixed
    return (1 if wildcards == 0 else 0, -recursive, literals + fixed,
            -stars, -wildcards)


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
        top = max(glob_specificity(r["glob"]) for r in matches)
        tied = [r for r in matches if glob_specificity(r["glob"]) == top]
        # What classify() hands the caller. Two tied rows agreeing on the class
        # but declaring different code paths still silently drop one set:
        # duplicate Class D rows naming `lib/a` and `lib/b` produced no
        # finding, and changes under `lib/b` could never trigger drift.
        if len({registry_rule_key(r) for r in tied}) > 1:
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


def registry_rules(doc: str, registry: list[dict]) -> list[dict]:
    """Every top-ranked row for `doc`, so a caller can see a tie.

    `classify` collapses these to one; the tie itself is what decides whether a
    WRITE is safe, which is a different question from what class to report.
    """
    matches = [r for r in registry if fnmatch.fnmatch(doc, r["glob"])]
    if not matches:
        return []
    top = max(glob_specificity(r["glob"]) for r in matches)
    return [r for r in matches if glob_specificity(r["glob"]) == top]


def classification_is_ambiguous(doc: str, registry: list[dict]) -> bool:
    """Do the top-ranked rows disagree about what this document IS?

    check_registry_paths already reports the disagreement as a P1, and a
    finding was all it did: `classify` still took the first row by TABLE ORDER,
    so with a `D` row above a conflicting `A` row `--stamp` treated a
    machine-owned document as hand-written and inserted or rewrote a marker in
    generated content -- the one write this module exists to prevent. A
    disagreement the audit cannot resolve must disable the writes that depend
    on it, not merely be mentioned.

    The comparison is `registry_rule_key`, which `check_registry_paths` calls
    too -- one function rather than two copies, so the finding and the refusal
    cannot disagree about what a tie means. They were copies until a sort went
    into one of them and not the other, which is how this file keeps failing.
    """
    tied = registry_rules(doc, registry)
    return len({registry_rule_key(r) for r in tied}) > 1


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
            # A fenced EXAMPLE of the marker pair is documentation, not the
            # generated block. Unfiltered, a Class A document whose real block
            # had gone missing had the example accepted as its `mark:` region:
            # the unmatched-region finding was suppressed and the code sample
            # was classified as renderer-owned. The inventory scanner already
            # excludes both; so does this one now.
            # Raw-TEXT blocks too, for the reason inventory_blocks gives.
            code = (fenced_lines(lines) | indented_code_lines(lines)
                    | raw_html_block_lines(lines, raw_text_only=True))
            # WRAPPED spans as well as single-line ones. A `mark:NAME` document
            # showing `<!-- BEGIN NAME -->` and `<!-- END NAME -->` inside a
            # span that opens above them and closes below had both read as real
            # delimiters, so a document that had LOST its region produced no
            # unmatched-region P1 and the example's lines were classified as
            # renderer-owned. The `inventory:` scanner beside this one learned
            # that a round ago; this parallel scanner did not.
            _mark_wrapped = code_span_lines(lines)

            # And an ESCAPED opener is not a delimiter. `\\<!-- BEGIN NAME -->`
            # renders as TEXT, which is how a Class A document shows its own
            # convention OUTSIDE a code span -- and reading the pair as real
            # classified every hand-written line between them as generated,
            # which under `exhaustive` suppressed the finding saying
            # regeneration would discard that prose. The comment and link
            # scanners have applied this rule for rounds; these two copies did
            # not. Codex filed it on the Node twin (solyra#69).
            def _marker_lines(pat: re.Pattern[str]) -> list[int]:
                out = []
                for n, l in enumerate(lines, 1):
                    if n - 1 in code:
                        continue
                    spans = code_spans(l) + _mark_wrapped.get(n - 1, [])
                    if any(not any(lo <= mm.start() < hi for lo, hi in spans)
                           and not is_escaped(l, mm.start())
                           for mm in pat.finditer(l)):
                        out.append(n)
                return out

            starts = _marker_lines(begin)
            ends = _marker_lines(end)
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
            # Not inside a fenced or indented example, and not commented
            # out -- the `mark:` and `inventory:` scanners already filter
            # these. A Class A document that LOST its real generated content
            # but kept a matching sample (a fenced `img.shields.io` line in
            # README) still set `hit`, so the registry's claim of coverage
            # survived the content's disappearance: no unmatched-region
            # finding, and the example's lines routed to the renderer as
            # though generated.
            example = fenced_lines(lines) | indented_code_lines(lines)
            # SPANS as well as whole lines. A pattern surviving only inside
            # inline code or a partial comment -- ``Example:
            # `https://img.shields.io/x` `` -- still matched the raw line, so
            # the missing-region finding stayed suppressed after the real
            # content went away and the sample's line was routed and stamped
            # as generated. Blanked rather than removed, since `pat` may be
            # anchored and a shorter line would move what it anchors to.
            spans = comment_spans(lines)
            # Spans that OPEN on an earlier line too. `code_spans` is
            # line-local, so a sample surviving only inside a wrapped span --
            # a `https://img.shields.io/x` between a backtick above it and one
            # below -- still matched the raw line. The region's claim of
            # coverage then outlived the real generated content: no unmatched
            # -region P1, and the example's line routed to the renderer as
            # though generated. The `mark:` and `inventory:` scanners above
            # already read `code_span_lines`; this one did not.
            wrapped = code_span_lines(lines)
            for n, line in enumerate(lines, 1):
                if n - 1 in example:
                    continue
                visible_line = mask_spans(
                    line, spans.get(n - 1, []) + code_spans(line)
                    + wrapped.get(n - 1, []))
                if pat.search(visible_line):
                    owned.add(n)
                    hit = True
        elif spec.startswith("prose:") and prompt is not None \
                and spec[6:] != prompt:
            # A second, DIFFERENT prose owner: the later assignment silently
            # replaced the first, so the audit reported a valid region map,
            # suppressed every unowned span and routed all prose findings to
            # one prompt while the registry claimed two.
            # `continue`, like the neighbouring prompt-missing branch: without
            # it `hit` is still False at the foot of the loop and the same spec
            # was appended a SECOND time, so one contradiction reported twice.
            unmatched.append(spec)
            continue
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
    # Indented code as well as fenced. A four-space example of the pair was
    # accepted as the real generated region, so a Class A document whose
    # renderer-owned block had gone missing had its own sample suppress the
    # unmatched-region finding and get classified as generated content. The
    # `mark:` and link scanners already exclude both constructs.
    # A RAW-TEXT block is the third way to SHOW a delimiter without declaring
    # one. A Class A document that had lost its real region but demonstrated
    # the pair inside `<pre>` had the example registered as the region: the
    # declared region counted as matched, the missing-region P1 was
    # suppressed, and the sample's own lines routed to the renderer as
    # generated. Fenced and indented were covered; this was not.
    fenced = (fenced_lines(lines) | indented_code_lines(lines)
              | raw_html_block_lines(lines, raw_text_only=True))
    pairs: dict[str, tuple[int, int]] = {}
    unbalanced: list[str] = []
    open_at: dict[str, int] = {}
    _inv_wrapped = code_span_lines(lines)
    for n, line in enumerate(lines, 1):
        if n - 1 in fenced:
            continue
        # An INLINE-code example is the other way a document explaining the
        # convention writes it, and EVERY visible delimiter on the line is
        # read. `.search` saw only the first; so did a `break` after the first
        # non-code match, which read
        # `<!-- inventory:x:start --><!-- inventory:x:end -->` -- a complete
        # pair on one line -- as a start with no end, and hid a duplicate or
        # orphan sharing a line with a real delimiter from the balance check.
        # WRAPPED spans as well as single-line ones. A span holding sample
        # start/end markers across a line break had both read as real
        # delimiters, so a Class A document that lost its real region looked
        # healthy instead of producing the intended P1 and the example's lines
        # were routed as renderer-owned.
        spans = code_spans(line) + _inv_wrapped.get(n - 1, [])
        for m in INVENTORY_RE.finditer(line):
            if any(lo <= m.start() < hi for lo, hi in spans):
                continue
            # An escaped opener renders as text; see the `mark:` scanner.
            if is_escaped(line, m.start()):
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
                    # replace the first silently. `insert_blocks()` refreshes
                    # only the FIRST occurrence (`count=1`), so the copy that is
                    # not refreshed can stay stale indefinitely while the region
                    # map reports itself valid. Keep the pair the renderer
                    # actually writes and report the duplicate.
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
    # The whole H1, not its title line. A Setext H1 is two lines, so scanning
    # from `h1_index + 1` started on the document's OWN `=====` underline,
    # recognised it as a Setext heading, and closed the window before it opened
    # -- the marker `stamp` had just placed correctly was then reported missing
    # and the next --stamp inserted a duplicate. A regression from the
    # section-boundary fix one round earlier, caught by Codex on the same PR.
    h1 = marker_anchor(lines)
    if h1 is None:
        return range(0, min(limit, len(lines)))
    # A heading inside a FENCE is an example, not the next section. Treating it
    # as one ended the search early, so an existing marker below the fence was
    # reported missing and --stamp inserted a second one above it, leaving
    # contradictory provenance in the document.
    # Indented code as well. An indented line followed by `---` is a code
    # block and a thematic break, not a Setext heading -- but omitted from
    # the skip set, `is_setext_underline` read it as one, closed the window
    # above a real marker below it, and --stamp inserted a second
    # contradictory marker.
    # And a raw HTML block, which renders literally: a `<div>` sample carrying
    # `## Fake` above an existing marker closed the window at the sample, so
    # the real marker below the block was reported missing and --stamp inserted
    # a duplicate above it. h1_index and heading_anchors already exclude these.
    fenced = (fenced_lines(lines) | commented_lines(lines)
              | indented_code_lines(lines) | raw_html_block_lines(lines))
    # To the next HEADING, with no additional line cap. A document opening
    # with more than `limit` lines of HTML metadata before its marker had the
    # real marker excluded from the window, so the audit reported it missing
    # and --stamp inserted a second one. The section boundary is the thing
    # being asked about; the line count was a proxy for it.
    # Where each Setext heading STARTS, not where its underline is. A Setext
    # heading's text is the whole paragraph the underline promotes, and that
    # paragraph may be several lines: `**Last reviewed:** ...` / `More title`
    # / `---` is ONE H2 whose first line is the marker-shaped one. Stopping at
    # `underline - 1` left that line inside the document window, so a line
    # belonging to the next section's HEADING stood in for the whole
    # document's provenance -- and `--stamp` then rewrote heading text instead
    # of inserting a real marker. `_paragraph_blocks` already closes a block
    # ON the underline, so the block's first line is the answer and the two
    # cannot disagree about where a heading begins. Codex filed it
    # (stocks#1121).
    setext_starts = {lo for lo, hi in _paragraph_blocks(lines, fenced)
                     if hi > lo and is_setext_underline(lines, hi, fenced)}
    stop = len(lines)
    for j in range(h1 + 1, len(lines)):
        if j in fenced:
            continue
        # The same one-to-three-space prefix ATX admits everywhere else. A
        # column-zero test did not close the window at `  ## Later`, though
        # CommonMark renders it as a heading, so a `Last reviewed` inside that
        # section stood in for the whole document's provenance -- suppressing
        # the missing-marker finding and letting --stamp rewrite the section's
        # metadata instead of placing the document's own marker.
        # Valid ATX syntax, not merely a leading `#`. CommonMark requires one
        # to six hashes followed by whitespace or end of line, so `#123 remains
        # open` and `####### x` are ordinary prose -- and my first version of
        # this boundary closed the window on both, emptying it so the real
        # marker was reported missing and --stamp inserted a second one above
        # the hashtag. Same rule _HEADING_RE uses.
        # Read THROUGH the blockquote container, as every other block test
        # here is. `heading_anchors` recognises `> ## Later` as a real heading
        # and this raw-line test did not, so a `Last reviewed` inside that
        # quoted section stayed in the document-level window -- suppressing
        # the missing-marker finding, and letting --stamp rewrite the
        # section's metadata instead of placing the document's own marker
        # under the H1. Codex filed it (stocks#1121).
        if re.match(r"^ {0,3}#{1,6}(?:\s|$)",
                    _QUOTE_PREFIX_RE.sub("", lines[j], count=1)):
            stop = j
            break
        # Setext is a section heading too, and its underline marks the heading
        # written on the line ABOVE -- so the next section starts there, not at
        # the underline. Reading only `#` let a `Last reviewed` line inside
        # that section stand in for the whole document's provenance, which is
        # the `# PART A` defect above in the other heading syntax.
        if j in setext_starts:
            stop = j
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


def repeated_owned_fields(line: str) -> list[str]:
    """Owned fields the marker line carries more than once.

    `extra_segments` CONSUMES a parseable owned value and pushes only its
    tail, so `**Owner:** Alice · **Owner:** Bob` left no extra text at all:
    nothing reported it, and the rewrite kept the FIRST and deleted the
    second -- arbitrarily discarding a contradictory ownership claim while
    reporting the document updated. Case-insensitively, for the same reason
    every other owned-field test here is.
    """
    seen: dict[str, int] = {}
    for raw in line.split(DOT):
        seg = raw.strip().lower()
        field = next((f for f in OWNED_FIELDS
                      if seg.startswith(f"**{f}".lower())), None)
        if field:
            seen[field] = seen.get(field, 0) + 1
    return sorted(f for f, n in seen.items() if n > 1)


def check_marker_fields(doc: str, info: dict, line: str | None = None) -> list[dict]:
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
    out: list[dict] = []
    rest = info.get("rest") or ""
    names = sorted({m.group(1).lower() for m in _MARKER_FIELD_RE.finditer(rest)})
    if names:
        out.append({"check": "marker", "doc": doc, "severity": "P2",
                    "detail": f"marker field(s) {', '.join(names)} could not be parsed and were "
                              f"read as free text ({rest.strip()[:60]!r}); the values they carry "
                              "are invisible to every check"})
    # A marker that CONTRADICTS itself. `Last reviewed: unknown` says no review
    # has happened; a `Depth` or an `Against` beside it claims one at a named
    # baseline. Every field parses, so nothing above reports it, and the run
    # emitted only the non-gating P3 for the unknown date -- so it passed
    # --check while a drift calculation ran off provenance `stamp` never
    # writes. A combination the writer cannot produce is malformed on read.
    # A field written TWICE, both copies well formed. Every one of them
    # parses, so the tail check above sees nothing, and the parser silently
    # takes the first -- a document asserting two different owners, or two
    # different review dates, that no check reported and `--stamp` resolved by
    # deleting one of them.
    for field in repeated_owned_fields(line or ""):
        out.append({"check": "marker", "doc": doc, "severity": "P2",
                    "detail": f"the marker carries {field.rstrip(':')} twice; the parser "
                              "reads the first and a restamp would delete the rest, so "
                              "which one is true has to be decided by hand"})
    claims = [f for f, v in (("Depth", info.get("depth")), ("Against", info.get("sha"))) if v]
    if info.get("date") == "unknown" and claims:
        out.append({"check": "marker", "doc": doc, "severity": "P2",
                    "detail": f"the marker records no review (`unknown`) and still carries "
                              f"{' and '.join(claims)}; those claim a review that the same "
                              "line says did not happen"})
    return out


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


# A block-quote prefix is a CONTAINER, not content: `> ```bash` opens a fence
# inside the quote, and SETUP.md and CLAUDE.md both use that shape. Seeing the
# `>` instead of the fence marked none of the block as code, so links and
# blocker citations in the sample were audited as live prose.
# `\s{0,3}` counts a TAB as one character, but CommonMark expands it to four
# columns -- so `\t```` is an indented code line, not a fence opener. Opening
# on it held a false fence across live paragraphs and suppressed their
# findings. The lead is captured instead and measured in columns by the
# caller, which is the same rule indentedCodeLines and _list_content_col use.
# A LIST MARKER is a container prefix too, and CommonMark strips it before
# parsing the fence: `- ```md` opens one as the first content of the item.
# Matching the physical line missed that opener and then read the indented
# CLOSING delimiter as a new one, so the example's headings were indexed as
# real anchors and --stamp could insert the review marker inside the code
# block. The Node twin has admitted the marker for rounds; this did not.
_FENCE_RE = re.compile(
    r"^(?P<pre>[ \t]*)(?P<quote>(?:> ?)*)"
    r"(?P<item>(?:[-*+]|\d{1,9}[.)])\s+)?"
    r"(?P<lead>[ \t]*)(?P<delim>`{3,}|~{3,})(?P<info>.*)$")
_QUOTE_PREFIX_RE = re.compile(r"^ {0,3}((?:> ?)*)")
# At least ONE marker, for STRIPPING the container. The counting pattern above
# matches the empty prefix by design, so using it to strip also ate up to three
# leading spaces -- which turned `    # Indented`, a code block, into an H1.
_BLOCKQUOTE_PREFIX_RE = re.compile(r"^(?: {0,3}> ?)+")


def quote_depth(line: str) -> int:
    """How many blockquote levels this line sits inside."""
    return _QUOTE_PREFIX_RE.match(line).group(1).count(">")


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
    # RAW-TEXT blocks too, and only those among the HTML kinds. A `<!--`
    # inside `<script>` or `<pre>` is DISPLAYED, not parsed -- and reading one
    # as an opener masked the closing tag and every line after it, so a live
    # broken link, stale blocker, heading or marker below the script was
    # silently skipped while CommonMark ends the block at `</script>`. A type-6
    # or type-7 block is different: Markdown is not parsed there but an HTML
    # comment inside one still hides its contents, so masking those would send
    # retired markup to the href pass as visible content. The Node twin has
    # carried this distinction for rounds. Codex filed it here.
    code = (fenced_lines(lines) | indented_code_lines(lines)
            | raw_html_block_lines(lines, raw_text_only=True))
    out: dict[int, list[tuple[int, int]]] = {}

    def add(i: int, a: int, b: int) -> None:
        if a < b:
            out.setdefault(i, []).append((a, b))

    # Code spans that CROSS a line break, as well as the per-line ones. A
    # valid span opened on one line, carrying a literal `<!--` on the next and
    # closing on a third, had that opener read as LIVE: everything below was
    # then masked to the closing `-->` or to EOF, and the dead links, blocker
    # citations, headings and markers in between were silently suppressed.
    # The content checks already used code_span_lines; this scanner did not.
    # It depends on nothing in this chain, so it is not the recursion
    # raw-block masking has to avoid.
    wrapped_code = code_span_lines(lines)
    open_at: tuple[int, int] | None = None
    for i, line in enumerate(lines):
        pos = 0
        while True:
            if open_at is None:
                if i in code:
                    break
                spans = code_spans(line) + wrapped_code.get(i, [])
                a = line.find("<!--", pos)
                # An ESCAPED opener opens nothing: `\\<!--` displays the
                # delimiter literally and the rest of the line stays live
                # Markdown. Reading it as a comment masked content through
                # `-->` or to EOF and suppressed the dead-link, blocker,
                # heading and marker findings in between. `_comment_hidden`,
                # the standalone copy of this scan, carries the same rule.
                while a >= 0 and (any(lo <= a < hi for lo, hi in spans)
                                  or is_escaped(line, a)):
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

    Indented code cannot interrupt a paragraph, so a run starts only after a
    blank line. Inside a list item the indentation is partly the LIST's: the
    item opens a container whose content column is where the text after the
    bullet begins, and a code block within it starts four columns past THAT.
    Excluding every run after a list marker -- the first version of this, and
    right only for a wrapped bullet -- turned a code block nested in an item
    back into live prose. Ported from the Node twin (solyra#69) and corrected
    here first.
    """
    out: set[int] = set()
    list_indent = 0
    blank_seen = True
    # Only a PARAGRAPH cannot be interrupted by indented code. After a
    # completed block no blank line is needed, so `# Example` followed
    # directly by a four-space sample IS code -- and requiring the blank left
    # the sample unmasked, so the link and blocker checks emitted gating
    # findings from a rendered example. Codex filed it; the Node twin
    # (solyra#69) has carried this since it was raised there.
    last_was_heading = False
    floor = 4
    in_code = False
    for i, raw in enumerate(lines):
        # Every measurement reads the CONTENT, not the raw line. Counting
        # indentation on the raw line returned zero for a QUOTED example, and
        # `>` alone was not seen as the blank line that a code run must start
        # after -- so `>` then `>     [guide](missing.md)` never entered a code
        # run at all and the link and blocker checks audited a rendered code
        # example as live prose. Leaving the blank/heading/list tracking on the
        # raw line would be worse than either: the two views would disagree
        # about where a block starts. Ported from the Node twin (solyra#69).
        line = _BLOCKQUOTE_PREFIX_RE.sub("", raw, count=1)
        if not line.strip():
            blank_seen = True
            continue
        # COLUMNS, with tab stops, so the floor logic and is_code_indented
        # cannot disagree about what four columns means.
        indent = indent_columns(line)
        if in_code and indent >= floor:
            out.add(i)
            continue
        in_code = False
        if indent >= floor and (blank_seen or last_was_heading):
            in_code = True
            out.add(i)
        else:
            # A table row is not a container, so it leaves the floor alone; a
            # list marker sets it to its own content column plus four.
            bullet = re.match(r"^(\s*(?:[-*+]|\d{1,9}[.)])\s+)", line)
            if bullet:
                # COLUMNS, as every other measurement here is. `-\titem`
                # advances the tab to column 4, but counting characters said
                # 2 and set the nested-code floor to 6 instead of 8 -- so a
                # six-space rendered paragraph after a blank line was
                # classified as code and skipped by the dead-link and blocker
                # audits. `_list_content_col` already measured it this way.
                list_indent = _column_width(bullet.group(1))
                floor = list_indent + 4
            elif indent >= list_indent > 0:
                # A CONTINUATION of the item, which carries no new bullet.
                # Resetting the floor to four here meant the next four-space
                # line after a blank read as a code block, although a `- `
                # item needs six to open one -- so rendered continuation
                # content was skipped by the dead-link and blocker checks.
                pass
            else:
                list_indent = 0
                floor = 4
        blank_seen = False
        # A HEADING is a block of its own, ATX or Setext, so the next line
        # starts a new block whether or not a blank separates them. The same
        # pair of patterns the Node twin tests.
        last_was_heading = bool(re.match(r"^ {0,3}#{1,6}\s", line)
                                or re.match(r"^ {0,3}(?:=+|-+)\s*$", line))
    return out


# CommonMark HTML blocks. Type 1 is raw TEXT: everything between `<pre>` and
# `</pre>` renders literally, so Markdown syntax inside one is not syntax.
_RAW_TEXT_OPEN_RE = re.compile(r"^ {0,3}<(pre|script|style|textarea)(?:[\s>/]|$)", re.I)

# Type 6: a known block-level tag, opened or closed, running to the next BLANK
# line rather than to a matching close tag. `<div>` followed by
# `[x](missing.md)` and `</div>` with no blank line between them renders the
# bracket syntax literally exactly as `<pre>` does.
_HTML_BLOCK_TAGS = frozenset((
    "address article aside base basefont blockquote body caption "
    "center col colgroup dd details dialog dir div dl dt fieldset figcaption figure footer "
    "form frame frameset h1 h2 h3 h4 h5 h6 head header hr html iframe legend li link main "
    "menu menuitem nav noframes ol optgroup option p param search section summary table "
    "tbody td tfoot th thead title tr track ul").split())

_HTML_BLOCK_OPEN_RE = re.compile(r"^ {0,3}</?([a-zA-Z][a-zA-Z0-9-]*)(?:[\s/>]|$)")

# Type 7: a line that is a COMPLETE open or closing tag and nothing else. The
# tag name is unrestricted, which is the point -- a custom element like
# `<x-widget>` is in no tag list. It ends at a blank line like type 6, and per
# CommonMark it cannot INTERRUPT a paragraph, which is the condition that keeps
# it from swallowing ordinary prose.
# A type-7 opener is a COMPLETE tag, and its attributes follow the same grammar
# every other tag scan here uses. `[^<>]*?` was not that grammar: a quoted value
# may contain `>` -- `<x-widget title=">">` is ONE tag -- and rejecting it opened
# no block, so the Markdown-looking lines below it were audited as live content
# and `[x](missing.md)` in the example became a gating dead link. It was also too
# LAX in the other direction, accepting `<x-widget ===>`, which CommonMark does
# not; that line really does start live Markdown. Reusing `_HTML_ATTR` fixes both
# and means one grammar rather than two.
_HTML_TYPE7_RE = re.compile(
    rf"^ {{0,3}}</?[a-zA-Z][a-zA-Z0-9-]*(?:\s+{_HTML_ATTR})*\s*/?>\s*$")

# Types 3, 4 and 5 -- processing instruction, document declaration and CDATA.
# Each runs raw to its OWN closer, over as many lines as it takes, so Markdown
# inside one renders literally; none was recognised, and `[x](missing.md)` in
# such a block produced a false gating dead-link finding over content displayed
# verbatim. Type 2 is the HTML comment, which this scanner tracks separately.
# CDATA is tested before the declaration form because `<![CDATA[` also opens
# `<!`; the declaration pattern requires a LETTER after it, so they cannot
# collide, and the order is belt and braces.
_HTML_RAW_DELIMITED = (
    (re.compile(r"^ {0,3}<\?"), "?>"),
    (re.compile(r"^ {0,3}<!\[CDATA\["), "]]>"),
    (re.compile(r"^ {0,3}<![A-Za-z]"), ">"),
)


def raw_html_block_lines(lines: list[str], *, raw_text_only: bool = False,
                         fenced: frozenset[int] | set[int] | None = None,
                         openers: dict[int, int] | None = None) -> set[int]:
    """Indices inside a raw HTML block, whose Markdown renders literally.

    A `# Heading` inside `<pre>` or `<div>` is TEXT, not a heading, and
    recording its slug invented an anchor the rendered document does not
    offer -- so a link to that fragment PASSED the dead-anchor check, the
    direction that makes an audit untrustworthy rather than incomplete.

    Comment state is tracked in THIS pass rather than read from
    `commented_lines`, so the two cannot become mutually recursive once the
    comment scan learns about raw blocks. An HTML comment is itself a raw-text
    block, so tracking it here costs nothing. Ported from the Node twin
    (solyra#69).

    `openers`, when given, receives `line index -> column the opening tag
    STARTS at` for each raw-TEXT block (`<pre>`, `<script>`, ...). The tag
    itself is RENDERED -- `<pre id="sample">` offers the id `sample` -- while
    everything after it on that line is displayed literally, and a caller
    masking whole lines therefore threw the id away with the content. The
    START rather than the end, because where the tag ENDS is a question the
    tag scanner already answers and this scan should not answer a second way.
    Only this scan knows where a block opens, so that much is recorded here.
    """
    out: set[int] = set()
    # `fenced_lines` passes its PROVISIONAL set, computed without HTML, and
    # relies on this scan to correct it -- so taking it as a parameter is what
    # keeps the two from recursing.
    if fenced is None:
        fenced = fenced_lines(lines)
    # An INDENTED example of an opener is an example, not a block.
    indented = indented_code_lines(lines)
    # Where a paragraph could START. A type-7 block may not INTERRUPT one, but
    # it may begin right after a completed block -- `# Title` then
    # `<x-widget>` -- and the blank-previous-line proxy missed exactly that, so
    # the example below it was audited as live prose. A heading and a thematic
    # break are blocks of their own to _paragraph_blocks, so the line after
    # either starts a new block.
    block_starts = {lo for lo, _ in _paragraph_blocks(lines, fenced)}
    in_comment = False
    open_tag: str | None = None
    # The quote depth the open block STARTED at. A raw HTML block opened
    # inside a blockquote ends with that quote, closing tag or not: CommonMark
    # ends the nested block where its container ends. Holding it open added
    # every later line to the block, so the dead-link, heading, marker and
    # blocker scans suppressed live body content -- potentially to the end of
    # the document. The fence scanner has had this rule for rounds; this is
    # the same rule one construct over. An unquoted block opens at depth 0 and
    # nothing is below 0, so it is untouched.
    open_depth = 0
    # The closer a type-3/4/5 block waits for. None for the tag-closed and
    # blank-line-closed kinds.
    closer: str | None = None
    for i, raw in enumerate(lines):
        # Only while NOTHING is open. Inside a block, Markdown is not parsed,
        # so a line the fence scan called fenced is displayed text and the
        # block walks straight through it -- that is how the provisional set's
        # false fence gets corrected. An opener sitting inside a REAL fence is
        # still skipped, because there no block is open.
        if open_tag is None and not in_comment and i in fenced:
            continue
        # The CONTAINER prefix is stripped, as the fence and indented-code
        # scanners already do: `> <pre>` opens a raw-text block whose Markdown
        # renders literally, and testing the physical line saw the `>` and
        # recognised no opener.
        line = _BLOCKQUOTE_PREFIX_RE.sub("", raw, count=1)
        if open_tag is not None and quote_depth(raw) < open_depth:
            open_tag, closer = None, None
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if open_tag is None:
            # A LIST MARKER is a container prefix too, and CommonMark removes
            # it before parsing the block: `- <pre>` opens a raw-text block
            # whose contents display literally, so a `[x](missing.md)` inside
            # it is an EXAMPLE and produced a gating dead-link finding for a
            # link no reader can click. Only while nothing is open -- inside a
            # block the line is displayed text and its leading `-` is content.
            # Every branch below returns, so the stripped text reaches no
            # closer test. The fence scanner learned the same rule this round.
            line = _LIST_MARKER_RE.sub("", line, count=1)
            # Whatever opens on THIS line opens at this line's depth. Recorded
            # before the opener tests rather than at each of the four places a
            # block can start, so none of them can be missed; it is only read
            # while a block is open, so a line that opens nothing leaves a
            # stale value nothing consults.
            open_depth = quote_depth(raw)
            if i in indented:
                continue
            # A comment OPENING on this line hides anything after it, including
            # a `<pre>` on a later line of the same comment.
            # An opener shown as `` `<!--` `` or escaped as `\\<!--` opens
            # nothing: the first is inline code, the second displays the
            # delimiter literally. Read as real, either one hid a later
            # `<pre>` from this scan, so the raw-text block was never
            # recognised and a `[x](missing.md)` DISPLAYED inside it became a
            # gating dead-link finding for a link no reader can click.
            # `comment_spans` and `_comment_hidden` have both carried this
            # rule for rounds; this third copy did not. Line-local
            # `code_spans` only -- `code_span_lines` reaches `fenced_lines`,
            # which reaches this function, and `_comment_hidden` exists
            # precisely to break that cycle.
            c = _visible_comment_open(line)
            if c != -1 and "-->" not in line[c:]:
                in_comment = True
                # Text BEFORE the opener is still live, so an opener there
                # still starts a block.
                if not _RAW_TEXT_OPEN_RE.match(line[:c]):
                    continue
            m = _RAW_TEXT_OPEN_RE.match(line)
            if not m:
                # Types 3, 4 and 5, BEFORE the raw_text_only gate: each renders
                # its contents literally exactly as `<pre>` does, so a caller
                # asking for "only blocks that display their contents" wants
                # these too.
                delim = next(((p, c) for p, c in _HTML_RAW_DELIMITED
                              if p.match(line)), None)
                if delim is not None:
                    out.add(i)
                    if delim[1] not in line:
                        open_tag, closer = "\x01", delim[1]
                    continue
                if raw_text_only:
                    continue
                b = _HTML_BLOCK_OPEN_RE.match(line)
                if b and b.group(1).lower() in _HTML_BLOCK_TAGS:
                    # Sentinel rather than a tag name, because the block does
                    # not close on one -- a blank line ends it whatever tags
                    # are inside.
                    open_tag = "\0"
                    out.add(i)
                    continue
                # The previous line is read THROUGH its container, as this
                # line already is. Inside a blockquote the blank line is
                # spelled `>`, which is nonempty raw -- so a quoted
                # `<x-widget>` after a quoted blank opened nothing and a
                # `[x](missing.md)` inside the block was audited as live.
                prev = _BLOCKQUOTE_PREFIX_RE.sub("", lines[i - 1] or "", count=1)
                if _HTML_TYPE7_RE.match(line) and (
                        i == 0 or not prev.strip() or i in block_starts):
                    open_tag = "\0"
                    out.add(i)
                continue
            open_tag = m.group(1).lower()
            out.add(i)
            if openers is not None:
                # In RAW coordinates. `line` has had its blockquote and list
                # prefixes stripped, and both are prefixes, so the difference
                # in length is the offset the caller needs.
                openers[i] = (len(raw) - len(line)) + m.start()
            # A one-line block: `<pre>...</pre>` closes on the line it opened.
            if re.search(rf"</{open_tag}\s*>", line[m.end():], re.I):
                open_tag = None
            continue
        out.add(i)
        if closer is not None:
            if closer in line:
                open_tag, closer = None, None
            continue
        if open_tag == "\0":
            if not line.strip():
                out.discard(i)
                open_tag = None
            continue
        if re.search(rf"</{open_tag}\s*>", line, re.I):
            open_tag = None
    return out


def _visible_comment_open(line: str) -> int:
    """Offset of the first `<!--` a reader sees as a comment opener, or -1.

    Line-local `code_spans` only, and no wrapped-span map: `code_span_lines`
    reaches `fenced_lines`, which reaches `raw_html_block_lines`, which calls
    this. An opener inside a span that OPENS on another line is therefore
    still read here; that is the cycle's price, and the single-line form is
    the one documents actually write.
    """
    spans = code_spans(line)
    at = line.find("<!--")
    while at != -1 and (any(lo <= at < hi for lo, hi in spans)
                        or is_escaped(line, at)):
        at = line.find("<!--", at + 1)
    return at


def _comment_hidden(lines: list[str]) -> set[int]:
    """Indices wholly inside an HTML comment, computed WITHOUT the fence scan.

    `fenced_lines` needs this and `commented_lines` cannot supply it: the two
    would be mutually recursive. An HTML comment is delimited by text, not by
    block structure, so a standalone scan is enough for the one question the
    fence scan asks -- is this delimiter commented out?
    """
    # WRAPPED spans as well as single-line ones. A literal `<!--` on the middle
    # line of a span that opens above it and closes below was read as a real
    # unclosed comment, so fenced_lines ignored every later fence delimiter --
    # a heading inside the fenced example could then terminate marker_window
    # before the real marker and --stamp inserted a duplicate. code_span_lines
    # depends on nothing in this chain, so it reintroduces no cycle.
    _wrapped = code_span_lines(lines)
    out: set[int] = set()
    inside = False
    for i, line in enumerate(lines):
        if inside:
            out.add(i)
            if "-->" in line:
                inside = False
            continue
        spans = code_spans(line) + _wrapped.get(i, [])
        at = line.find("<!--")
        # An inline EXAMPLE opens nothing: `` `<!--` `` in prose was read as a
        # real unclosed comment, so fenced_lines ignored every later fence
        # delimiter -- a heading inside the fenced example could then terminate
        # marker_window before the real marker and --stamp inserted a second,
        # contradictory one. comment_spans learned this a round ago; this
        # standalone helper, which exists to break the recursion between the
        # two, did not. `code_spans` is line-local and depends on nothing here.
        # An ESCAPED opener opens nothing either: `\\<!--` displays the
        # delimiter literally and leaves the rest of the line live Markdown.
        # Reading it as a real comment masked everything through `-->` or to
        # EOF, suppressing the dead-link, blocker, heading and marker findings
        # in between -- the direction that hides defects.
        while at != -1 and (any(lo <= at < hi for lo, hi in spans)
                            or is_escaped(line, at)):
            at = line.find("<!--", at + 1)
        if at != -1 and "-->" not in line[at:]:
            # The comment opens here and does not close on this line, so this
            # line and everything up to the closing delimiter is hidden.
            out.add(i)
            inside = True
    return out


# NINE digits at most. CommonMark caps an ordered-list marker there, so
# `1234567890. # Fake` is ordinary paragraph text -- while stripping it as a
# container let `h1_index` invent an H1, `heading_anchors` invent `#fake`, and
# `--stamp` place provenance after a heading that does not exist. Codex filed
# it here.
_LIST_MARKER_RE = re.compile(r"^(\s*(?:[-*+]|\d{1,9}[.)])\s+)")


def _column_width(text: str) -> int:
    """Width of `text` in COLUMNS, expanding tabs to the next stop."""
    col = 0
    for ch in text:
        col += (_TAB_STOP - (col % _TAB_STOP)) if ch == "\t" else 1
    return col


def _list_content_col(lines: list[str], i: int) -> int:
    """Content column of the list item a fence on line `i` opens inside, else 0.

    A fence indented one to three columns at the TOP level is legal and its
    content need not be indented at all, so indentation alone cannot say a
    block has ended. Inside a list item it can: the item ends at the first
    non-blank line left of its content column, and the fence ends with it.
    Zero means "not in an item", which disables the rule rather than guessing.
    """
    target = indent_columns(_BLOCKQUOTE_PREFIX_RE.sub("", lines[i], count=1))
    if target == 0:
        return 0
    for j in range(i - 1, -1, -1):
        body = _BLOCKQUOTE_PREFIX_RE.sub("", lines[j], count=1)
        if not body.strip():
            continue
        if indent_columns(body) >= target:
            # A continuation of the same item, or deeper content; keep looking
            # for the line that actually opened the container.
            continue
        bullet = _LIST_MARKER_RE.match(body)
        return _column_width(bullet.group(1)) if bullet else 0
    return 0


def fenced_lines(lines: list[str]) -> set[int]:
    """Indices inside a fenced code block, which are examples, not content.

    Two passes, because a fence and an HTML block can each hide the other. A
    literal ``` inside `<div>...</div>` is displayed text, not a fence -- but
    the scan that would know it is inside an HTML block needs a fence set to
    run. So: scan once ignoring HTML, use that provisional set to find the
    blocks, then scan again refusing to OPEN a fence inside one. The HTML scan
    ignores the provisional set while a block is open, which is what lets it
    walk through the very lines the false fence claimed. A fence that really
    is a fence is unaffected: an HTML opener inside one is still skipped,
    because there no block is open to walk through.
    """
    provisional = _fenced_scan(lines, frozenset())
    return _fenced_scan(lines, raw_html_block_lines(lines, fenced=provisional))


def _fenced_scan(lines: list[str], html: frozenset[int] | set[int]) -> set[int]:
    """One fence pass, refusing to open a fence on a line inside `html`.

    The OPENING delimiter is remembered. Toggling on any fence-looking line
    meant a `~~~` inside a ``` example closed the block there, so the rest of
    the example read as prose and the prose after the real closing fence read
    as code -- false findings and suppressed ones from one line. CommonMark: a
    fence closes only on the same character, at least as long, with no info
    string. Raised on the Node twin (solyra#69).
    """
    out: set[int] = set()
    # A delimiter inside an HTML COMMENT is commented-out HTML, not a fence.
    # An unmatched ``` inside `<!-- ... -->` opened one, and every visible
    # line after the comment was then classified as code -- dead-link,
    # blocker, marker and heading checks all suppressed until another fence
    # happened to occur. Computed standalone because commented_lines reaches
    # comment_spans, which reaches back here.
    hidden = _comment_hidden(lines)
    open_fence: str | None = None
    open_depth = 0
    open_list_col = 0
    for i, line in enumerate(lines):
        m = None if i in hidden else _FENCE_RE.match(line)
        # A fence opened INSIDE a blockquote ends with its container, closing
        # fence or not: CommonMark ends the quoted code block where the quote
        # ends. Holding it open classified everything after the quote as code,
        # so dead links, blocker citations, headings and markers below it were
        # all silently skipped until some later line happened to look like a
        # matching fence. A blank line drops to depth 0 and ends the quote,
        # which is why this is a depth comparison rather than a `>` test.
        # Unquoted fences open at depth 0 and nothing is below 0, so they are
        # untouched.
        if open_fence is not None and quote_depth(line) < open_depth:
            open_fence = None
        # A fence opened inside a LIST ITEM ends with that item, closing fence
        # or not, exactly as a quoted one ends with its quote. The item ends at
        # the first non-blank line left of its content column, so holding the
        # fence open past that classified the rest of the document as code and
        # suppressed every dead link, blocker, heading and marker below it.
        # `_list_content_col` returns 0 when the fence is not in an item, which
        # is what keeps a legally indented top-level fence -- whose content may
        # sit at column zero -- from ending on its own first content line.
        if (open_fence is not None and open_list_col and line.strip()
                and indent_columns(
                    _BLOCKQUOTE_PREFIX_RE.sub("", line, count=1)) < open_list_col):
            open_fence = None
        if open_fence is None:
            # An opening ``` fence may not carry a backtick in its info string.
            # And a delimiter inside a raw HTML block is displayed text:
            # CommonMark does not parse Markdown there, so opening on it left
            # a fence that outlived the block and swallowed every later link,
            # blocker, heading and marker as "code".
            if (m and i not in html
                    and not (m.group("delim")[0] == "`"
                             and "`" in m.group("info"))):
                # Indentation measured RELATIVE to the container, which is what
                # CommonMark's "up to three spaces" means. A blockquote prefix
                # or a list marker on THIS line is itself the container, so its
                # own lead is the baseline; otherwise the baseline is the
                # content column of the enclosing item, where a fence on a
                # later line of that item legally sits. A flat cap rejected
                # those and then misread the closing delimiter as an opener.
                base = (_column_width(m.group("pre"))
                        if m.group("quote") or m.group("item")
                        else _list_content_col(lines, i))
                if _column_width(m.group("pre")) - base > 3:
                    continue
                # Inside a blockquote the container is the QUOTE, so what
                # counts is the indentation AFTER the marker: `>     ```" is an
                # indented code line carrying literal backticks.
                if m.group("quote") and _column_width(m.group("lead")) > 3:
                    continue
                open_fence = m.group("delim")
                open_depth = quote_depth(line)
                # A fence opening ON the marker line sits at that item's
                # content column; `_list_content_col` scans BACKWARD for an
                # enclosing item and so reports 0 here, which would disable
                # the item-end rule for exactly the fences this round added.
                open_list_col = (
                    _column_width(m.group("pre")) + _column_width(m.group("item"))
                    if m.group("item") else _list_content_col(lines, i))
                out.add(i)
            continue
        out.add(i)
        if (m and m.group("delim")[0] == open_fence[0]
                and len(m.group("delim")) >= len(open_fence)
                and not m.group("info").strip()):
            open_fence = None
    return out


def _span_hidden(lines: list[str]) -> set[int]:
    """Lines a code span covers ENTIRELY, single-line or wrapped.

    A marker-shaped line inside a span that opens above it and closes below is
    an EXAMPLE of a marker. Accepting it suppressed the missing-marker finding
    and `--stamp` then rewrote the example, leaving the document with no
    rendered provenance at all -- the same failure the fenced and commented
    exclusions beside it exist to prevent, a third hiding mechanism over.
    """
    wrapped = code_span_lines(lines)
    out: set[int] = set()
    for i, line in enumerate(lines):
        spans = code_spans(line) + wrapped.get(i, [])
        stop = len(line.rstrip())
        if stop and any(lo <= 0 and hi >= stop for lo, hi in spans):
            out.add(i)
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
    # RAW HTML blocks too. Markdown inside `<pre>` or `<div>` is not parsed --
    # `**Last reviewed:** 2026-09-01` there renders as literal characters, not
    # as the document's provenance -- yet a marker-shaped line in one was
    # accepted, so `--stamp --verify` could rewrite it and report the document
    # covered while it still had no rendered marker. The fenced equivalent has
    # been excluded since this function was written; this is the same rule one
    # block type over.
    fenced = fenced_lines(lines) | raw_html_block_lines(lines)
    # A marker inside `<!-- ... -->` is invisible to every reader. Accepting it
    # passed the missing-marker check, and --stamp then rewrote the line still
    # inside the comment: the command reported success over a document with no
    # rendered provenance at all.
    commented = commented_lines(lines)
    # And one inside a code SPAN that opens above it and closes below. See
    # _span_hidden: it is the third hiding mechanism, and the content checks
    # learned about wrapped spans a round before marker discovery did.
    spanned = _span_hidden(lines)
    # And front matter, which renders as a metadata table: a marker-shaped line
    # inside it is invisible to a reader, so accepting it passed the provenance
    # check over a document that shows none.
    front = front_matter_lines(lines)
    # Whole-line commenting is not the only way a marker hides in a comment.
    # A comment opened on an earlier line and closed PART WAY through this one
    # leaves visible text after the `-->`, so the line is not wholly commented
    # -- and stripping it puts the hidden marker prefix first, where MARKER_RE
    # matches it and the `-->` lands harmlessly in `rest`. The document then
    # passes the missing-marker check carrying no rendered provenance, and
    # `--stamp` rewrites the line still inside the comment. The offset of the
    # match is what decides it, so the SPANS are needed, not the line set.
    comment_at = comment_spans(lines)
    for i in marker_window(lines):
        # An INDENTED marker-shaped line is an example of a marker, not the
        # document's provenance -- and stripping before matching threw away
        # the only thing that distinguishes them. A sample in the opening
        # section counted as the marker, suppressed the real missing-marker
        # finding, and `--stamp` then REPLACED the example with an unindented
        # live marker: a write straight through this module's one hard rule.
        # Fenced blocks are excluded for the same reason.
        if i in fenced or i in commented or i in spanned or i in front:
            continue
        raw = lines[i]
        # Read THROUGH the blockquote container, as every other block test in
        # this module does. `> **Last reviewed:** ...` renders as the
        # document's provenance and was recognised as nothing, so the
        # missing-marker finding fired over a document that visibly shows one
        # and `--stamp` inserted a SECOND, contradictory marker above the
        # quote -- measured on a quoted document before the fix. The indent
        # test runs on the stripped copy for the same reason: `> ` is a
        # container, not four columns of code indentation.
        bare = _BLOCKQUOTE_PREFIX_RE.sub("", raw, count=1)
        if is_code_indented(bare):
            continue
        col = len(raw) - len(bare.lstrip())
        if any(a <= col < b for a, b in comment_at.get(i, [])):
            continue
        line = bare.strip()
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


# Both spellings. A malformed LEGACY claim -- `**Last Updated:** 2026-9-1` --
# parses as neither form and was not marker-shaped either, so --stamp inserted
# a valid marker ABOVE it and the document visibly carried two contradictory
# provenance lines. The current-format case was already refused; the labels
# here are exactly the ones LEGACY_MARKER_RE accepts, so the two cannot drift.
_MARKER_SHAPE_RE = re.compile(
    r"^\*\*(?:Last reviewed|Last updated|Last refreshed|Last verified|Verified)"
    r":?\*\*", re.I)


# CommonMark advances a tab to the next multiple of four.
_TAB_STOP = 4


def indent_columns(line: str) -> int:
    """Leading indentation in COLUMNS, expanding tabs to the next stop.

    A tab counted as four only in column zero and as nothing elsewhere, so
    ` \t[x](missing.md)` measured 1 -- CommonMark advances the tab to column 4
    and renders the line as code, so the link and blocker scans inspected an
    example as live prose. Ported from the Node twin (solyra#69).
    """
    col = 0
    for ch in line or "":
        if ch == " ":
            col += 1
        elif ch == "\t":
            col += _TAB_STOP - (col % _TAB_STOP)
        else:
            break
    return col


def is_code_indented(line: str) -> bool:
    """Is this line indented ENOUGH to be a code example rather than a paragraph?

    Any leading whitespace used to disqualify a marker, but CommonMark needs a
    tab or four spaces for indented code -- one to three spaces still render as
    an ordinary paragraph. A visibly rendered marker written that way was
    dropped as an example, so `find_marker` and `marker_shaped_lines` both saw
    nothing, `--stamp` inserted a second marker ABOVE the still-visible
    original, and the document carried two contradictory review claims. The
    Node twin has had this rule since solyra#69; this is the parity fix.
    """
    return bool(line) and indent_columns(line) >= 4


def marker_shaped_lines(lines: list[str]) -> list[int]:
    """Indices that LOOK like a marker in the window but parse as neither form.

    `**Last reviewed:** 2026-9-1` is the shape: the date is not the format the
    marker declares, so `MARKER_RE` and `LEGACY_MARKER_RE` both decline and the
    audit concludes there is no marker at all. `--stamp` then inserted a valid
    one ABOVE it and the document visibly carried two contradictory review
    claims -- which the duplicate-marker check cannot see, because only one of
    the two parses.
    """
    # And a line a code SPAN covers entirely, which find_markers has excluded
    # since it learned about wrapped spans but this did not: a malformed
    # marker DEMONSTRATED inside a span that opens above it and closes below
    # is an example, and counting it emitted a gating finding and made
    # stamp() return `skipped-malformed-marker` -- so a document showing what
    # a bad marker looks like could not be given a real one.
    # And a RAW HTML BLOCK, which `find_markers` excludes and this did not:
    # `<div>` around `**Last reviewed:** 2026-9-1` shows the shape without
    # writing a marker, so the valid-marker path correctly found none while
    # this path counted it -- a gating finding, and `stamp()` returning
    # `skipped-malformed-marker`, which meant the document demonstrating a bad
    # marker could never be given a good one. Codex filed it on this side.
    fenced = (fenced_lines(lines) | commented_lines(lines) | _span_hidden(lines)
              | raw_html_block_lines(lines))
    out = []
    for i in marker_window(lines):
        if i in fenced or is_code_indented(lines[i]):
            continue
        line = lines[i].strip()
        if not _MARKER_SHAPE_RE.match(line):
            continue
        if MARKER_RE.match(line) or LEGACY_MARKER_RE.match(line):
            continue
        out.append(i)
    return out


def check_marker_shape(doc: str, lines: list[str]) -> list[dict]:
    """A marker-shaped line that does not parse, reported rather than ignored."""
    return [{"check": "marker", "doc": doc, "severity": "P2", "line": i + 1,
             "detail": "a line in the marker window reads as a review marker but "
                       "parses as neither the current nor the legacy format, so the "
                       "audit cannot see the claim it makes"}
            for i in marker_shaped_lines(lines)]


def find_marker(lines: list[str]) -> tuple[int, dict] | None:
    found = find_markers(lines)
    return found[0] if found else None


# `-` needs two or more: a single `-` under text is a list bullet's sibling far
# more often than a heading, and CommonMark's own `---` case is covered.
# One `-` is enough: CommonMark accepts it as a level-two underline, and the
# preceding-line check below is what tells it from a standalone list marker --
# a bullet has no heading text above it. Requiring two omitted a valid heading
# from the anchor index and made a working link to it a gating finding.
_SETEXT_UNDERLINE_RE = re.compile(r" {0,3}(?P<rule>=+|-+)\s*")


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
    # The blockquote container is stripped from BOTH lines. `> Title` over
    # `> ===` renders as a heading, and matching the raw underline always
    # failed on the `>` -- so heading_anchors omitted the rendered anchor (a
    # working fragment reported dead) and h1_index missed a quoted Setext H1.
    under = _BLOCKQUOTE_PREFIX_RE.sub("", lines[i] or "", count=1)
    if not _SETEXT_UNDERLINE_RE.fullmatch(under):
        return False
    above = _BLOCKQUOTE_PREFIX_RE.sub("", lines[i - 1] or "", count=1)
    if not (bool(above.strip()) and not above.lstrip().startswith("#")):
        return False
    # The underline must sit in the SAME container block. `> Example` followed
    # by an unquoted `---` ends the blockquote and renders a thematic break;
    # reading it as a heading closed marker_window above a real marker below
    # the break, so the audit reported it missing and --stamp could insert a
    # contradictory second one.
    # Compared on the RAW lines: the stripped copies above are for the PATTERN
    # tests only, and depth read off them is 0 for every line, which both
    # accepted `> Example` / `---` across a container boundary and rejected the
    # quoted heading this strip exists to admit.
    if quote_depth(lines[i - 1] or "") != quote_depth(lines[i] or ""):
        return False
    # A list item is a container too: `- Example` then `---` at column 0 ends
    # the list. An underline indented to the item's CONTENT column is still an
    # underline, which is why this is an indentation test rather than a ban.
    item = re.match(r"^(\s*)((?:[-*+]|\d{1,9}[.)])\s+)", above)
    if item and len(re.match(r"^\s*", under).group(0)) < len(item.group(0)):
        return False
    return True


def front_matter_lines(lines: list[str]) -> set[int]:
    """Indices of a leading YAML front-matter block, delimiters included.

    GitHub renders front matter as a metadata table, not as Markdown, so a
    `# note` comment inside it is not a heading. Treating one as the document
    H1 put `--stamp`'s marker and its surrounding blank lines INSIDE the `---`
    delimiters: the front matter is corrupted and the real H1 left unstamped.

    An UNTERMINATED opener is not front matter -- GitHub renders a lone `---`
    as a thematic break -- so this returns nothing rather than masking the
    whole document, which would hide every finding below it.
    """
    # COLUMN ZERO. An indented `---` is a thematic break, not a front-matter
    # opener, but trimming the line accepted it -- so every line to the next
    # indented `---` was excluded as metadata and a rendered link between them
    # passed the audit unchecked.
    # The BOM is stripped BEFORE the opener test, not after. A UTF-8 BOM
    # precedes `---` in a file some editors write, and testing the raw first
    # line returned nothing at all -- so the metadata was audited as body
    # Markdown, and a `# note` inside it became the document H1, which is
    # where `--stamp` writes the marker: inside the YAML block, corrupting
    # the front matter. Only line zero can carry one. Codex filed it
    # (stocks#1121).
    if not lines or lines[0].lstrip("\ufeff").rstrip() != "---":
        return set()
    for i in range(1, len(lines)):
        # COLUMN ZERO, as the opener already requires. An indented `---` is
        # not a delimiter, but `strip()` accepted one -- so everything through
        # that line was masked as metadata and a rendered link, heading or
        # marker inside the span was silently excluded.
        if lines[i].rstrip() in ("---", "..."):
            return set(range(0, i + 1))
    return set()


def h1_index(lines: list[str]) -> int | None:
    """Index of the first H1.

    Not a fixed line number on purpose: several docs open with an HTML comment
    and carry their H1 on line 9, where a line-3 insert lands inside the
    comment. A doc with no H1 is skipped by the caller entirely.
    """
    # A fenced `# Example` before the real title was returned as the H1, so
    # --stamp inserted the provenance marker INSIDE the code block: the example
    # was rewritten and the document left effectively unstamped.
    # Front matter too: a `# note` comment inside it is metadata, not a
    # heading, and taking it as the H1 made --stamp write inside the `---`
    # delimiters.
    # Raw HTML blocks too. `<pre>` displays `# Example` literally, so GitHub
    # renders no heading there -- taking one as the document H1 put the
    # provenance marker INSIDE the block, where nothing renders it, and a
    # later audit could then accept that misplaced marker. `heading_anchors`
    # and `marker_window` have excluded these for rounds; this did not.
    fenced = (fenced_lines(lines) | commented_lines(lines)
              | front_matter_lines(lines) | raw_html_block_lines(lines))
    # SPANS too, not only whole lines. A comment that closes partway through a
    # heading-shaped line -- `<!--` then `# Fake --> visible` -- leaves the
    # line with a visible suffix, so commented_lines does not exclude it while
    # H1_RE still matches the hidden `# Fake` prefix. --stamp then inserted the
    # marker after a heading no reader can see and above the document's real
    # H1, putting provenance outside the opening section.
    hidden_spans = comment_spans(lines)
    for i, line in enumerate(lines):
        if i in fenced:
            continue
        # The blockquote container is stripped first: `> # Quoted title`
        # RENDERS as an H1 and heading_anchors already reads it that way, but
        # this tested the raw line -- so such a document was reported as having
        # no H1 while --stamp answered `skipped-no-h1`, leaving the command
        # unable to repair its own finding. The mask is applied first so the
        # offsets it preserves still line up. Ported from the Node twin.
        bare = _BLOCKQUOTE_PREFIX_RE.sub("", mask_spans(line, hidden_spans.get(i, [])), count=1)
        # A leading BYTE ORDER MARK is encoding metadata, not heading text. It
        # sits before the `#`, so H1_RE saw no heading and the document was
        # reported as missing its marker while --stamp answered
        # `skipped-no-h1` -- the finding it raises and then refuses to act on.
        # Stripped after masking, which preserves offsets, so the spans above
        # still line up.
        if i == 0:
            bare = bare.lstrip("\ufeff")
        # The LIST MARKER is a container prefix too. `- # Title` renders a
        # real H1 and heading_anchors has read it that way for rounds, but
        # this tested the unstripped line -- so the audit reported the marker
        # missing while --stamp answered `skipped-no-h1` and could not repair
        # its own finding.
        if H1_RE.match(_LIST_MARKER_RE.sub("", bare, count=1)):
            return i
        # Setext level one (`Title` over `===`). Without it the audit reported
        # a missing marker on such a document while --stamp answered
        # `skipped-no-h1`, so the command could not repair its own finding.
        # The SETEXT branch reads the stripped copy too. `> Quoted title` over
        # `> ====` renders as an H1, and testing the raw quoted lines returned
        # None -- so the audit reported no H1 and --stamp answered
        # `skipped-no-h1`, the finding it raises and then refuses to act on.
        # Through `is_setext_underline`, not a third inline copy of the test.
        # That predicate carries the CONTAINER rules this one lacked: `> Title`
        # over an unquoted `===` is a quote that ENDS and a thematic-break-
        # shaped line, not a heading, and `- Title` over a column-zero `===`
        # is a list that ends. Both returned line 0 here, so the audit found
        # an H1 the document does not render and `--stamp` wrote provenance
        # after it. Level ONE only, which is the question this function asks;
        # the predicate accepts either underline.
        under = _BLOCKQUOTE_PREFIX_RE.sub("", lines[i + 1] or "", count=1) \
            if i + 1 < len(lines) else ""
        if (bare.strip() and not bare.lstrip().startswith("#")
                and i + 1 < len(lines)
                and is_setext_underline(lines, i + 1, fenced)
                and re.fullmatch(r" {0,3}=+\s*", under)):
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
    # Read THROUGH the container, as h1_index already does. A quoted Setext
    # H1 is `> Title` over `> ===`, and testing the raw line saw the `>`,
    # matched no underline and returned the TITLE as the insertion point -- so
    # --stamp inserted the marker between the title and its underline,
    # destroying the H1 while reporting the stamp inserted. The underline must
    # sit at the same quote depth as the title, or it belongs to neither.
    # Through `is_setext_underline`, which is where the container rules live:
    # this carried its own quote-depth test and none of the list ones, and a
    # local copy of a rule is how the two halves drift. Level ONE only, as in
    # `h1_index`; the predicate accepts either underline.
    under = (_BLOCKQUOTE_PREFIX_RE.sub("", lines[h1 + 1] or "", count=1)
             if h1 + 1 < len(lines) else "")
    if (h1 + 1 < len(lines) and is_setext_underline(lines, h1 + 1)
            and re.fullmatch(r" {0,3}=+\s*", under)):
        return h1 + 1
    return h1


def _container_prefix(line: str) -> tuple[str, str]:
    """What an inserted line needs to stay inside the H1's container.

    An H1 may sit inside a blockquote or a list item -- `> # Title`,
    `- # Title` -- and CommonMark ends that container at the first line
    lacking the prefix. Inserting a bare marker and bare blank lines after one
    moved the document's existing introduction OUT of the quote or the item:
    `--stamp` changed structure rather than only adding provenance, which is
    this module's one hard rule. Codex filed it (stocks#1121).

    TWO prefixes, because they are not the same string. A list item's
    continuation is indented to the marker's width and a blank line inside one
    is genuinely blank -- indenting it would add nothing but trailing
    whitespace. A blockquote's continuation is `> `, and a blank line inside
    one must still carry `>` or the quote ends there.

    Derived from whichever line the caller passes, so the Setext case works
    without a second rule: `marker_anchor` returns the `===` underline, and
    `> ===` carries the same container as the title above it.
    """
    quoted = _BLOCKQUOTE_PREFIX_RE.match(line)
    head = quoted.group(0) if quoted else ""
    rest = line[len(head):]
    item = _LIST_MARKER_RE.match(rest)
    # The marker is replaced by SPACES of its own width, which is the column
    # CommonMark parses the item's content at -- not stripped, which would put
    # the marker back at column zero and open a second list item.
    body = (" " * len(item.group(1)) if item
            else rest[:len(rest) - len(rest.lstrip())])
    lead = head + body
    return lead, lead.rstrip()


def _marker_body(lines: list[str], idx: int) -> str:
    """A marker line with its container removed, which is what the field
    readers are written against.

    `find_markers` reads through the container, so a quoted marker is found --
    and every consumer that re-reads the raw line then saw `> ` as content.
    `extra_segments` kept it as unowned prose and `--stamp` appended it to the
    rewritten marker, so each run grew the line by one more `> **Last
    reviewed:** unknown` segment. Reproduced by stamping a quoted document
    twice.
    """
    lead, _ = _container_prefix(lines[idx])
    return lines[idx][len(lead):]


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


# The checks a stamp does NOT answer; see the --verify refusal in main.
_DISPROVEN_BY_AUDIT = frozenset(
    {"dead-link", "dead-anchor", "closed-issue", "class-a"})

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
        # Case-insensitively, for the same reason `owner_of` is: a variant
        # this script's own parser declines is still a field the rewrite
        # OWNS, and keeping it as extra prose duplicated it beside the
        # canonical spelling.
        if not seg or any(seg.lower().startswith(f"**{f}".lower())
                          for f in OWNED_FIELDS):
            continue
        out.append(seg)
    return out


def owner_of(lines: list[str], marker_idx: int | None) -> str | None:
    if marker_idx is None:
        return None
    # Case-INSENSITIVELY, matching `_MARKER_FIELD_RE`, which carries `re.I`
    # deliberately. `**owner:** Alice` is a field every reader recognises;
    # reading it case-sensitively returned None, `extra_segments` then kept the
    # variant as free text, and `--stamp` wrote a canonical `**Owner:** TBD`
    # beside it -- one line asserting two different owners, reported as
    # updated.
    m = re.search(r"\*\*Owner:\*\*\s*([^·]+)", lines[marker_idx], re.I)
    return m.group(1).strip() if m else None


# Far past any real first line, and bounded so a file with no terminator at
# all is not read whole just to answer this.
_NEWLINE_SCAN_CAP = 1 << 20


def has_mixed_newlines(path: pathlib.Path, *, limit: int = 4 * 1024 * 1024) -> bool:
    """Does the file on disk use MORE THAN ONE line ending?

    `existing_newline` reads only the first line, and `write_stamp` applies
    that one style to every line of the rewritten text -- so a document
    beginning CRLF and continuing LF came back entirely CRLF. A one-line
    provenance stamp then carries a whole-file diff, which is the exact
    outcome `existing_newline` exists to prevent, in the one shape it cannot
    see. Codex filed it.

    Bounded: a file larger than `limit` is read up to that point only. Two
    endings in the first four megabytes are enough to answer yes, and a
    document that size is not one this tool should pull into memory twice.
    """
    try:
        raw = path.open("rb").read(limit)
    except OSError:
        # The caller is about to read the same file and will report the
        # failure properly; an unreadable file is not a mixed-ending one.
        return False
    # CRLF counted first and its CRs removed, so a CRLF file does not read as
    # holding both CR and LF.
    crlf = raw.count(b"\r\n")
    return sum(bool(x) for x in (crlf, raw.count(b"\n") - crlf,
                                 raw.count(b"\r") - crlf)) > 1


def existing_newline(path: pathlib.Path) -> str:
    """The line ending the file on disk already uses.

    `read_text` performs universal-newline conversion, so the text this script
    works on is always `\n`-terminated whatever the file holds. Writing that
    back rewrote EVERY line ending in a CRLF document -- a whole-file diff for
    a one-line stamp, and the opposite of what --stamp promises. The file is
    the authority on its own endings, so it is asked at write time.
    """
    # Through the FIRST LINE, however long it is. A fixed 8 KiB sample of a
    # document whose first line is longer than that holds no line ending at
    # all, so a CRLF file was reported LF and `write_stamp` rewrote every
    # ending in it -- the whole-file diff this helper exists to prevent.
    # `readline` stops at the first `\n`, so the read stays bounded by one
    # line rather than by the file.
    # A lone CR is a line ending too, and `readline` does not stop at one --
    # so on a classic-Mac document the "first line" it returned was the whole
    # file and the CRLF test then reported LF, which made `write_stamp`
    # rewrite every ending in it: the whole-file diff this helper exists to
    # prevent, in the one format it did not recognise. Read in chunks until
    # the first terminator of ANY kind, bounded so a file with none does not
    # pull itself into memory.
    sample = b""
    try:
        with path.open("rb") as fh:
            while len(sample) < _NEWLINE_SCAN_CAP:
                chunk = fh.read(8192)
                if not chunk:
                    break
                sample += chunk
                if b"\r" in sample or b"\n" in sample:
                    break
    except OSError:
        return "\n"
    at = min((i for i in (sample.find(b"\r"), sample.find(b"\n")) if i != -1),
             default=-1)
    if at == -1:
        return "\n"
    if sample[at:at + 1] == b"\n":
        return "\n"
    return "\r\n" if sample[at + 1:at + 2] == b"\n" else "\r"


def write_stamp(doc: str, new: str) -> None:
    """Write a stamped document, preserving the line endings it arrived with.

    Through a temp file in the SAME directory, then `os.replace`. Writing in
    place opens with O_TRUNC, so a failure part-way through -- a full disk is
    the ordinary cause -- left the document truncated while the error named
    only the documents already finished. A rename within a directory is
    atomic, so a failed stamp leaves the original byte-for-byte as it was.

    The temp file is created EXCLUSIVELY, under a name that is not
    predictable. `write_stamps` refuses a symlinked DOCUMENT; it does not
    cover this path, and an ordinary open would follow a symlink found here --
    truncating a file anywhere writable and then renaming the link itself into
    place as the document. Codex filed exactly that as a P1 on the Node twin
    (solyra#69); this side had no temp file at all, so it is ported with the
    guard already in it. `x` is O_CREAT|O_EXCL, which fails on an existing
    path, symlink included; the suffix keeps a stale temp file from a
    hard-killed run from turning that refusal into a permanent one.
    """
    path = REPO / doc
    nl = existing_newline(path)
    text = new if nl == "\n" else new.replace("\n", nl)
    tmp = path.with_name(f".{path.name}.{os.getpid()}-{os.urandom(4).hex()}"
                         ".stamp-tmp")
    try:
        with open(tmp, "x", encoding="utf-8", newline="") as fh:
            fh.write(text)
        # The temp file is created with default permissions and then REPLACES
        # the original, so stamping a tracked executable Markdown file would
        # turn it from mode 100755 to 100644 -- an unrelated diff, and a broken
        # consumer wherever the bit mattered. Best effort: a filesystem that
        # cannot report or set a mode is not a reason to refuse the stamp, and
        # the replace below is still atomic.
        try:
            os.chmod(tmp, path.stat().st_mode)
        except OSError:
            pass  # cleanup -- mode unavailable; the write itself still stands
        os.replace(tmp, path)
    except OSError:
        # Best effort, and never masking the original error: the temp file is
        # this function's litter, and failing to remove it is not the failure
        # worth reporting.
        try:
            tmp.unlink()
        except OSError:
            pass  # cleanup -- the original error is already propagating
        raise


def write_stamps(writes: list[tuple[str, str]]) -> None:
    """Write every stamped document, or refuse before writing any.

    A tracked `.md` SYMLINK is not a document this command may write: the open
    follows it, so `--stamp` edited the link's TARGET rather than a repository
    file -- and a symlink committed on a branch can point anywhere writable,
    inside the checkout or outside it. `is_file()` follows symlinks too, so the
    writability preflight did not stop it. Codex filed this as a P1 on the Node
    twin (solyra#69); the same hazard was live here.

    The refusal asks `symlinked_component`, so a symlinked ANCESTOR is refused
    as well: checking only the final name let a `docs/` replaced by a link
    report an ordinary file underneath it, and the temporary file and its
    rename then travelled through that link like any other write.

    Everything is checked before anything is written. A deleted or read-only
    document is the common case, and finding it on file 60 of 93 leaves the
    tree half stamped with no record of where it stopped. This narrows that
    window; it does not close it -- a full disk still fails mid-loop, and
    os.access answers for the calling uid, which under root calls a mode-444
    file writable. So the loop reports what it HAD written rather than
    pretending the operation was atomic.
    """
    links = sorted(f"{doc} (through {link})" if link != doc else doc
                   for doc, link in ((doc, symlinked_component(doc))
                                     for doc, _ in writes)
                   if link is not None)
    if links:
        raise AuditError(
            f"--stamp refuses {', '.join(links)}: a tracked symlink, so the write "
            "would land on its target rather than a document in this repository. "
            "Nothing was written.")
    unwritable = [doc for doc, _ in writes
                  if not (REPO / doc).is_file() or not os.access(REPO / doc, os.W_OK)]
    if unwritable:
        raise AuditError(
            f"--stamp cannot write {', '.join(sorted(unwritable))}: missing or "
            "not writable. Nothing was written.")
    done: list[str] = []
    for doc, new in writes:
        try:
            write_stamp(doc, new)
        except OSError as exc:
            # Exit 2, not the traceback-and-exit-1 that means "findings".
            raise AuditError(
                # `{doc} is unchanged` is now true, and was not before: the
                # write goes to a temp file and is renamed into place, so a
                # failure leaves the original byte-for-byte as it was. The
                # earlier wording said only "the tree is partially stamped",
                # which left a reader unable to tell whether the named
                # document had been truncated.
                f"--stamp failed writing {doc}: {exc}. {doc} is unchanged; "
                f"{len(done)} of {len(writes)} documents were already stamped"
                + (f" ({', '.join(done)})" if done else "")
                + "; the tree is partially stamped.") from exc
        done.append(doc)


def stamp(text: str, date: str, depth: str, sha: str,
          reviewed: bool = False) -> tuple[str, str]:
    """Return (new_text, action). Never inserts into a doc with no H1.

    `reviewed=False` (the default, and what a scheduled run does for most docs)
    moves only `Last scanned` and leaves any existing review claim untouched.
    """
    lines = text.split("\n")
    found = find_marker(lines)
    # Inserting a valid marker above one that merely fails to PARSE leaves the
    # document carrying two review claims, and the duplicate check cannot see
    # it because only one of them is a marker as far as this script knows.
    # ANY malformed claim left in the window, not only the case where it is
    # the sole one. Conditioning on `found is None` meant a document carrying a
    # valid marker AND a second line like `**Last reviewed:** 2026-1-1` was
    # still writable: --stamp updated the valid one, --verify counted the
    # target as consumed, and the contradictory claim stayed on the page where
    # the duplicate-marker check cannot see it -- only one of the two parses.
    malformed = [i for i in marker_shaped_lines(lines)
                 if found is None or i != found[0]]
    if malformed:
        return text, "skipped-malformed-marker"
    # And a marker that PARSES but leaves an owned field in its tail. MARKER_RE
    # is not end-anchored, so `**Depth:** VERIFIED` declines the optional group
    # and pushes itself AND the valid `Against` / `Last scanned` after it into
    # `rest` -- where extra_segments drops every owned-looking segment. The
    # scan-only rewrite then rebuilt the line without them and permanently
    # deleted the reviewed-against SHA, disabling the drift checks, while the
    # audit reported the malformed marker as a P2. Refusing keeps the evidence
    # on disk; the P2 is what asks a human to fix it.
    # `Owner:` is EXCLUDED: MARKER_RE has no group for it, so a well-formed
    # marker always carries it in the tail and testing the whole owned set
    # refused every document with an owner -- which is all of them.
    if found and not found[1].get("legacy"):
        tail = found[1].get("rest") or ""
        # Case-INSENSITIVELY, matching `_MARKER_FIELD_RE`, which carries
        # `re.I` deliberately. A case variant such as `**depth:** verified` is
        # a field the reader recognises and the parser declines, so a
        # case-sensitive refusal let `stamp` keep it as extra prose AND add a
        # canonical `**Depth:**` beside it: `--verify` reported the target
        # updated while the line now carried two contradictory depth fields,
        # and the next audit reported the same P2 again.
        if any(seg.strip().lower().startswith(f"**{f}".lower())
               for seg in tail.split(DOT)
               for f in OWNED_FIELDS if f != "Owner:"):
            return text, "skipped-malformed-marker"
        # And a field written TWICE, both copies well formed -- the case the
        # refusal above cannot see, because `extra_segments` consumes a
        # parseable owned value and leaves no tail. The rewrite would keep the
        # first and delete the rest, resolving a contradiction the document
        # states by discarding half of it. `check_marker_fields` reports it;
        # this declines to paper over it.
        if repeated_owned_fields(_marker_body(lines, found[0])):
            return text, "skipped-malformed-marker"
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

    extras = (extra_segments(_marker_body(lines, found[0]))
              if found and not prev.get("legacy") else [])
    marker = render_marker(r_date, r_depth, r_sha, date, owner, extras)
    if found:
        # TWO valid markers in the opening section. `find_marker` picks the
        # first and this path rewrites only that line, so `--stamp --verify`
        # returned "updated" and exited successfully while leaving a second,
        # contradictory date, owner and SHA in place -- in a document the same
        # run had already reported as carrying duplicate markers. The refusal
        # was a property of which branch the document took rather than of the
        # document. Codex filed it on the Node twin (solyra#69).
        if len(find_markers(lines)) > 1:
            return text, "skipped-duplicate-marker"
        idx, _ = found
        # The marker's OWN container, preserved. Rewriting `> **Last
        # reviewed:** ...` at column zero ends the blockquote there, and
        # rewriting an item's indented marker unindented ends the list item --
        # so a refresh that reports only "updated" would silently restructure
        # the document. The comparison reads the same stripped copy, or a
        # container line never equals the rendered marker and every run
        # reports `updated` over an unchanged document.
        lead, _ = _container_prefix(lines[idx])
        if _marker_body(lines, idx).strip() == marker:
            return text, "unchanged"
        lines[idx] = lead + marker
        return "\n".join(lines), "updated"
    h1 = marker_anchor(lines)
    if h1 is None:
        return text, "skipped-no-h1"
    # Target shape:  "# Title" / "" / marker / "" / body -- each line carrying
    # whatever container the H1 sits in, so an H1 inside a quote or a list item
    # keeps the body that follows it inside the same container.
    lead, blank = _container_prefix(lines[h1])
    # Reuse the blank line the H1 already has rather than adding a second one.
    # Read through the container here too: a quoted document's blank line is
    # `>`, which is not "" and made the reuse branch miss every time.
    nxt = (_BLOCKQUOTE_PREFIX_RE.sub("", lines[h1 + 1], count=1)
           if h1 + 1 < len(lines) else None)
    if nxt is not None and not nxt.strip():
        lines[h1 + 2:h1 + 2] = [lead + marker, blank]
    else:
        # Both blanks, not just the leading one. An H1 followed straight by
        # body text got `# Title` / "" / marker / body, and Markdown renders
        # the marker and the opening sentence as a single paragraph.
        lines[h1 + 1:h1 + 1] = [blank, lead + marker, blank]
    return "\n".join(lines), "inserted"


# ── github state ────────────────────────────────────────────────────────────

# The only values `check_closed_issues` branches on. "Any string" is not
# enough: it reads `st["state"] == "closed"` and falls through everything else,
# so a row reading `bogus` silently drops a cited blocker from the report -- the
# same clean-bill-of-health failure the row check above exists to stop, one
# value in. GitHub's issues API returns exactly these two.
ISSUE_STATES = frozenset({"open", "closed"})
# What `fetch_issue_states` records in the `kind` column, and nothing else.
ISSUE_KINDS = frozenset({"PR", "ISSUE"})


ISSUE_SNAPSHOT_MAX_AGE_DAYS = 1


def _check_snapshot_age(file: str, raw: object, *,
                        now: datetime.datetime | None = None) -> None:
    """Refuse a snapshot that cannot be dated, or that has expired.

    Every other guard below asks whether a ROW is usable. None asked whether
    the file still describes reality, and the format recorded nothing to
    answer with -- so a snapshot of any age loaded as current. An issue open
    when it was written and closed since produced no stale-blocker finding at
    all, under a report dated today: a fabricated clean bill of health, which
    is the one outcome this tool exists to prevent (CLAUDE.md §3.7). Codex
    filed it on the Node twin (solyra#69).

    Refused rather than flagged, because a finding is a claim about the
    documents and "I cannot tell" is not one of those.
    """
    captured = raw.get("capturedAt") if isinstance(raw, dict) else None
    # `is_calendar_date` on the day, not just a parse of the whole string: a
    # stamp naming a day that does not exist is the shape a hand-edited one
    # takes, and some parsers roll it over rather than refusing it.
    if (not isinstance(captured, str) or "T" not in captured
            or not is_calendar_date(captured[:10])):
        raise AuditError(
            f'--issues-snapshot {file} has no usable "capturedAt" ({captured!r}); '
            "without a capture time an arbitrarily old snapshot reads as current "
            "and a blocker that has since closed goes unreported")
    # Against the WALL CLOCK, not against --date. "Is this issue state still
    # current" is a question about now; a report dated in the past does not
    # make month-old issue data accurate, and keying the window to --date
    # would let one flag switch the guard off.
    on = (now or datetime.datetime.now(datetime.timezone.utc)).date()
    age = (on - datetime.date.fromisoformat(captured[:10])).days
    if age < 0:
        raise AuditError(
            f"--issues-snapshot {file} is stamped {captured[:10]}, which is after "
            f"today ({on.isoformat()}); a capture that has not happened yet "
            "describes nothing, and a hand-edited stamp is how an expired "
            "snapshot would be made to pass")
    if age > ISSUE_SNAPSHOT_MAX_AGE_DAYS:
        raise AuditError(
            f"--issues-snapshot {file} was captured {captured[:10]}, {age} days ago "
            f"(limit {ISSUE_SNAPSHOT_MAX_AGE_DAYS}); an issue that closed in between "
            "would be reported as live work, or a blocker that has closed would not "
            "be reported at all -- rewrite it with --write-issues-snapshot")


def write_issues_snapshot(file: str, states: dict[str, dict[int, dict]], *,
                          now: datetime.datetime | None = None) -> None:
    """Write a snapshot, stamped with the time it was captured.

    Reading an unusable snapshot is exit 2; failing to WRITE one was exit 1,
    because OSError walks straight past the AuditError handler. Same class of
    failure -- the run did not happen -- so the same status.

    The stamp sits BESIDE the repository maps rather than inside one: every
    consumer of a states map expects its values to be issue maps, and
    load_issues_snapshot returns only the maps for the same reason.
    """
    stamped = (now or datetime.datetime.now(datetime.timezone.utc)).isoformat()
    try:
        pathlib.Path(file).write_text(
            json.dumps({"capturedAt": stamped,
                        **{r: {str(k): v for k, v in d.items()}
                           for r, d in states.items()}}, indent=1),
            encoding="utf-8")
    except OSError as exc:
        raise AuditError(
            f"--write-issues-snapshot {file} could not be written: {exc}") from exc


def load_issues_snapshot(file: str, *,
                         now: datetime.datetime | None = None) -> dict[str, dict[int, dict]]:
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
    _check_snapshot_age(file, raw, now=now)
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
            # And `kind`, which the live read has always collected and nothing
            # used to check. A `/pull/N` citation backed by an ISSUE record
            # names no pull request at all, and that check reads this column
            # -- so a snapshot without it would silently switch the check off,
            # which is "missing data reads as fine" wearing a different hat
            # (CLAUDE.md §3.7).
            if rec.get("kind") not in ISSUE_KINDS:
                raise AuditError(
                    f"--issues-snapshot {file}: {repo}#{num} has no usable kind "
                    f"({rec.get('kind')!r}); expected one of {sorted(ISSUE_KINDS)}. "
                    "Without it a /pull/ citation backed by an issue cannot be told "
                    "from a real one, and the check would pass in silence")
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

# A word that turns a clause against itself. Used ONLY to separate a settled
# half from a blocking half inside one clause, never as a general split.
_CONTRAST_RE = re.compile(
    r"\b(?:while|whilst|whereas|but|though|although|however|with|without|"
    r"except|apart from|other than)\b", re.I)


def clause_bounds(line: str, start: int, end: int) -> tuple[int, int]:
    """Offsets of the clause a citation sits in.

    The bounds are where the split LIVES, and `citation_clause` is the slice.
    They were two implementations of one rule and they disagreed on the case
    that needs them most: the contrast split below ran only in the slice, so
    `#1 is still open but <url to #1> is resolved` gave the cue analysis two
    clauses while the deduplication -- which asks whether a shorthand and a URL
    are the SAME citation -- still saw one. It suppressed the live shorthand as
    a duplicate of the settled URL, the URL was then skipped as settled, and a
    closed issue described as open produced no finding at all. Codex filed it
    (stocks#1121).

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
    hi = nxt.start() if nxt else len(line)
    # One clause may still carry BOTH verdicts, and then the first one read
    # wins for every citation in it: `all three stocks records are closed as
    # not planned with the work still open in solyra` settles the solyra
    # citation off the stocks half. A contrast word is a boundary the sentence
    # split does not see, so it is applied -- only in that ambiguous case,
    # because splitting on `with` unconditionally would shred ordinary prose
    # and lose findings whose cue sits before one.
    span = line[lo:hi]
    if SETTLED_CUE_RE.search(span) and BLOCKING_CUE_RE.search(span):
        rel = start - lo
        # A COMMA is a boundary here too: `#1 is resolved, #2 is still open`
        # carries no contrast word, so the whole sentence was returned for both
        # citations and each was settled by the first `resolved` it saw -- a
        # stale live claim about #2 producing no finding at all.
        #
        # Only a comma that SEPARATES TWO CITATIONS, which is the narrowest
        # rule that fixes it. Splitting on every comma in this branch settles
        # nothing and breaks the opposite shape: `#1 was still open, now
        # resolved` is one statement about one citation, where the comma
        # introduces the resolution -- an existing test caught exactly that,
        # and it is the direction that INVENTS a finding.
        cite_at = [mm.start() for mm in SHORTHAND_ISSUE_RE.finditer(span)]
        cite_at += [mm.start() for mm in ISSUE_URL_RE.finditer(span)]
        commas = {mm.start() + 1 for mm in re.finditer(r",", span)
                  if any(c < mm.start() for c in cite_at)
                  and any(c > mm.start() for c in cite_at)}
        bounds = sorted({0, len(span)}
                        | {mm.start() for mm in _CONTRAST_RE.finditer(span)}
                        | commas)
        for a, b in zip(bounds, bounds[1:]):
            if a <= rel < b:
                return lo + a, lo + b
    return lo, hi


def citation_clause(line: str, start: int, end: int) -> str:
    """The clause a citation sits in, as text. `clause_bounds` decides where."""
    lo, hi = clause_bounds(line, start, end)
    return line[lo:hi]


def cites_live_work(line: str, start: int, end: int,
                    fallback: str | None = None) -> bool:
    """Is THIS citation cited as live work?

    A line-level answer put every URL on the line under one verdict, so
    `#1 is no longer blocking; #2 is still open` gave #1 a P1 from #2's cue.
    The clause decides when it carries a cue at all; otherwise the fallback
    does, because a table row puts the cue and the citations in different
    cells -- `| Open issues | #838 · #839 |` is a real finding whose citations
    sit in a clause with no cue of its own. Raised on the Node twin
    (solyra#69).

    `line` is the RENDERED PARAGRAPH and `fallback` the physical line, and the
    two must not be the same string. The clause analysis wants the paragraph,
    so a sentence split by a soft break is read whole. The fallback must stay
    LINE-scoped: it is the table-ROW rule, and a whole table is one paragraph
    block, so passing the paragraph let a `Blocking issues` column HEADER
    reach every citation in every row of the table -- measured at 43 fabricated
    P1s on this tree, in rows whose own cells say nothing of the kind.
    """
    clause = citation_clause(line, start, end)
    if SETTLED_CUE_RE.search(clause) and is_settled(clause):
        return False
    if BLOCKING_CUE_RE.search(clause):
        return has_blocking_cue(clause)
    return has_blocking_cue(line if fallback is None else fallback)


def enclosing_parenthetical(line: str, start: int, end: int) -> tuple[int, int] | None:
    """The innermost `(...)` containing this span, if any.

    A parenthetical is a clause boundary the sentence-level split does not
    see. `In progress -- the provenance half is done (#820, #1095: every
    API-served table now labels ...)` gave the shorthand a clause carrying the
    row's `In progress`, so a closed issue named INSIDE a parenthetical that
    says the work is done was reported as cited live. Scanning left to right
    and returning on the first pair that closes around the span yields the
    innermost one, because an inner pair always closes first.
    """
    opens: list[int] = []
    for i, ch in enumerate(line):
        if ch == "(":
            opens.append(i)
        elif ch == ")" and opens:
            o = opens.pop()
            if o < start and i >= end:
                return o + 1, i
    return None


# One complete OPENING tag, attributes and all. `re.S` because an opening tag
# may span physical lines -- `<div\n data-note="...">` is one tag, and a
# per-line scan sees no opener on the second line at all.
_TAG_OPEN_RE = re.compile(
    r"<[a-zA-Z][a-zA-Z0-9-]*"
    r"""(?:\s+[a-zA-Z_:][-\w:.]*(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'`=<>]+))?)*"""
    r"\s*/?>", re.S)
_TAG_ATTR_RE = re.compile(
    r"([a-zA-Z_:][-\w:.]*)\s*=\s*"
    r"""(?:"([^"]*)"|'([^']*)'|([^\s"'`=<>]+))""", re.S)
_TAG_NAME_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9-]*)")


def tag_attribute_spans(lines: list[str]) -> dict[int, list[tuple[int, int]]]:
    """Per line, the offsets of HTML attribute VALUES -- implementation
    metadata, not rendered text.

    `<div data-issue="https://.../issues/1">Outstanding</div>` shows a reader
    the word `Outstanding` and nothing else: the URL is neither visible nor
    clickable, and scanning it produced a gating stale-blocker finding from
    something no reader can act on. The same applies to a registered claim
    hidden in `<div data-note="3 routes">`.

    An `href` on an ANCHOR is exempt, because `<a href>` pointing at an issue
    IS a citation readers follow -- which is the whole reason the rendered-HTML
    passes exist. On any other element it is inert: `<div href="...">` renders
    no link, so exempting it there admitted the same hidden metadata the rest
    of this helper exists to hide. Ported from the Node twin (solyra#69) with
    that narrowing applied to both.

    Scanned over the JOINED document and split back per line, so a tag whose
    attributes begin on a later physical line is read as the one tag it is.
    """
    starts: list[int] = []
    at = 0
    for line in lines:
        starts.append(at)
        at += len(line) + 1
    joined = "\n".join(lines)
    out: dict[int, list[tuple[int, int]]] = {}
    for tag in _TAG_OPEN_RE.finditer(joined):
        name = _TAG_NAME_RE.match(tag.group(0))
        anchor = bool(name) and name.group(1).lower() == "a"
        for attr in _TAG_ATTR_RE.finditer(tag.group(0)):
            if anchor and attr.group(1).lower() == "href":
                continue
            for g in (2, 3, 4):
                if attr.group(g) is None:
                    continue
                lo = tag.start() + attr.start(g)
                hi = tag.start() + attr.end(g)
                # Back to per-line offsets, because every caller masks a line.
                i = bisect.bisect_right(starts, lo) - 1
                while i < len(lines) and starts[i] < hi:
                    a = max(lo, starts[i]) - starts[i]
                    b = min(hi, starts[i] + len(lines[i])) - starts[i]
                    if b > a:
                        out.setdefault(i, []).append((a, b))
                    i += 1
                break
    return out


def check_closed_issues(doc: str, text: str, states: dict[str, dict]) -> list[dict]:
    out = []
    lines = text.split("\n")
    # The SAME builder the dead-link scan uses, so the fence, comment,
    # code-span and paragraph-interrupt exclusions apply here without any of
    # them being restated. See the reference-use pass below.
    _ref_defs = reference_definitions(lines)
    # --check gates on these findings, so a document DEMONSTRATING what a
    # blocking citation looks like failed the audit over its own example. The
    # link, heading and marker checks already skip fenced lines.
    # Fenced AND indented code. Only fences were excluded, so a four-space
    # Markdown example carrying blocker prose and a closed issue URL emitted a
    # gating P1 over content that renders as code. The dead-link pass already
    # treats both constructs the same way.
    # RAW-TEXT HTML blocks too, and only those. `<pre>` displays a blocker URL
    # literally, so citing one inside an example produced a gating finding over
    # content nobody can act on -- while a type-6 or type-7 block is RENDERED:
    # `<div>` around `Blocked by <a href=".../issues/1">#1</a>` is a citation a
    # reader follows, and masking it would suppress a real closed blocker.
    # Same distinction the Node twin draws (solyra#69).
    fenced = (fenced_lines(lines) | indented_code_lines(lines)
              | raw_html_block_lines(lines, raw_text_only=True))
    # And commented-OUT text, which is how a blocker list is retired without
    # losing it: the prose no longer renders, but it still held the build red.
    # Span-based rather than whole-line, matching check_dead_links -- a row
    # retired with a trailing `<!-- superseded: ... -->` is the common shape,
    # and a whole-line rule cannot see it.
    commented = comment_spans(lines)
    # Code spans that CROSS line breaks. `code_spans` is per physical line and
    # cannot see either delimiter of a span opened on one line and closed on
    # the next, so a blocker-shaped URL inside one was audited as live prose.
    wrapped = code_span_lines(lines)
    # Attribute VALUES are implementation metadata: `<div data-issue="...">`
    # shows a reader nothing clickable, so a citation there is not a blocker.
    attr_spans = tag_attribute_spans(lines)
    title_spans = link_meta_spans(lines)
    # Per line, ONCE: the spans a reader cannot see, the line with them
    # blanked, and the cue text -- markup reduced, same length, so every
    # offset still indexes all three. Computed here rather than in the loop
    # because the PARAGRAPH join below needs every line's cue text before the
    # first line is classified.
    hidden_of = [commented.get(i, []) + code_spans(ln) + wrapped.get(i, [])
                 + attr_spans.get(i, []) + title_spans.get(i, [])
                 for i, ln in enumerate(lines)]
    visible_of = [mask_spans(ln, hidden_of[i]) for i, ln in enumerate(lines)]
    cue_of = [strip_inline_markup(v) for v in visible_of]
    # The RENDERED PARAGRAPH, not the physical line. A soft break renders as a
    # space, so `Blocked by` over `https://.../issues/123` is one sentence --
    # and a per-line scan found the cue on neither line, so a stale blocker
    # produced no finding at all. Codex filed that half.
    #
    # The SETTLED direction wraps just as often and is worse when it is
    # missed. Measured on this tree's docs/product/07-MODEL-REGISTRY.md:
    # `... as blockers when both had been` / `closed on 2026-09-14` reads as
    # live work on the first line alone, which is a FALSE gating P1 saying the
    # opposite of the sentence. That one appeared the moment the cue
    # vocabulary was widened to match the Node twin, which is how it was
    # found -- the findings diff, not a test.
    #
    # `_paragraph_blocks` is the same window the code-span scan uses, so the
    # two cannot disagree about where inline content ends. Offsets map back: a
    # citation found on line `i` at column `c` is read at `para_start[i] + c`
    # in the joined text, and the finding is still reported against line `i`.
    para_text: dict[int, str] = {}
    para_start: dict[int, int] = {}
    for lo, hi in _paragraph_blocks(lines, fenced):
        joined = ""
        for i in range(lo, hi + 1):
            if i > lo:
                joined += " "
            para_start[i] = len(joined)
            joined += cue_of[i]
        for i in range(lo, hi + 1):
            para_text[i] = joined
    for n, line in enumerate(lines, 1):
        if n - 1 in fenced:
            continue
        # Commented-out spans AND inline code. Inline code renders literally,
        # never as a live citation, so a document explaining what a blocker row
        # looks like -- `` `.../issues/123 is still open` `` -- drew a gating P1
        # once that sample issue closed. The fenced and indented forms of the
        # same example were already excluded; this is the third, and it covers
        # the shorthand pass and the URL pass alike because both read `hidden`.
        # And a Markdown link TITLE, which renders as a tooltip rather than
        # as body text -- see link_meta_spans. The DESTINATION stays visible,
        # because an issue URL written there is one a reader can follow.
        hidden = hidden_of[n - 1]
        # The cue precheck reads the line with those spans BLANKED, and that
        # ordering is the fix. Masking only the citation is not enough: a
        # hidden span can supply the CUE for a different, visible citation --
        # `See https://.../issues/1 <!-- still open -->` renders as a bare
        # URL and nothing else, yet the raw-line precheck saw `still open`,
        # and so did the clause analysis below, so a closed issue was reported
        # as a live blocker and could fail --check.
        # Spaces, not deletion: every span offset computed below is an offset
        # into this line, so the masked copy has to be the same length.
        visible = visible_of[n - 1]
        # The cue is what a READER sees, so markup is reduced before any cue
        # is read: emphasis, a link's brackets and destination, and an HTML
        # tag. Same length, so every offset below still indexes this copy the
        # way it indexes `visible`; the citation passes keep reading the
        # unmarked line, which is what keeps a URL written as a destination
        # findable.
        visible_cue = cue_of[n - 1]
        # The joined paragraph, and this line's offset into it. A line outside
        # any paragraph block falls back to itself, which is what this scan
        # did everywhere before.
        para_cue = para_text.get(n - 1, visible_cue)
        para_at = para_start.get(n - 1, 0)
        if not has_blocking_cue(para_cue):
            continue
        # URL spans, so a shorthand scan does not re-read the `/issues/940`
        # inside one it has already reported.
        url_spans = [(mm.start(), mm.end()) for mm in _URL_RE.finditer(line)]
        # And the numbers the URL pass below will name, so one citation
        # written in the ordinary Markdown shape -- `[#861](.../issues/861)`,
        # which carries BOTH spellings -- is reported once rather than twice.
        # The span guard alone cannot see this: it hides the digits inside the
        # URL, not the `#861` in the link label sitting outside it.
        # Only URLs naming THIS repository, because that is the only repository
        # a bare `#123` can mean. A repository-blind set let a solyra URL
        # sharing the number suppress the stocks shorthand -- so on
        # `stocks #123 is still open; .../solyra/issues/123 is still open`,
        # with stocks#123 closed and solyra#123 open, NEITHER citation
        # reported and a stale blocker passed the audit.
        # And not one inside a HIDDEN span. A commented or inline-code URL
        # ending in the same number suppressed the visible shorthand, while
        # the URL pass below skips the hidden citation too -- so a closed
        # issue produced no finding from either spelling. `hidden` is already
        # computed above; the dedup simply was not reading it.
        # Scoped to the same CLAUSE, not to the number anywhere on the line.
        # A shorthand and a URL in one clause are two spellings of one
        # citation -- `#123 is still open https://.../issues/123` -- and must
        # be reported once; that is what the dedup is for. A line-wide number
        # set went much further: on `#123 is still open; <.../issues/123> is
        # resolved` the two clauses say OPPOSITE things, and it suppressed the
        # live shorthand because the number appeared somewhere on the line.
        # The URL pass then correctly skipped its own settled clause, so the
        # contradiction produced no finding at all -- the hiding direction.
        # Same split citation_clause makes, so "one citation" means the same
        # thing to the dedup and to the cue analysis.
        # The DECODED line, because a destination is decoded before a reader
        # follows it: `https://github&#46;com/.../issues/1` is a link to the
        # real issue, and scanning the source spelling missed it entirely --
        # a stale blocker cited that way passed clean. Both ISSUE_URL_RE
        # passes read the same decoded copy, so the dedup below cannot see a
        # different set of citations than the pass it dedups against. Every
        # offset is mapped back, because `hidden`, `visible` and
        # `clause_bounds` all index the source line. Codex filed it on the
        # Node twin (solyra#69).
        scan, scan_map = decode_with_map(line)
        url_here = [(_src_at(scan_map, mm.start()), int(mm.group("num")))
                    for mm in ISSUE_URL_RE.finditer(scan)
                    if mm.group("repo").lower() == THIS_REPO
                    and not any(lo <= _src_at(scan_map, mm.start()) < hi
                                for lo, hi in hidden)]
        skipped_end: int | None = None
        for m in SHORTHAND_ISSUE_RE.finditer(line):
            if any(lo <= m.start() < hi for lo, hi in hidden + url_spans):
                continue
            # A shorthand is weaker evidence than a URL, so it carries the
            # stricter test the URL pass reserves for PRs: the cue must be in
            # the citation's OWN clause, with no line-level fallback. Without
            # it the fallback attributed one row's cue to every number in a
            # long sentence -- `ten more canonical issues closed ... (#820,
            # #825, ...)` was reported as live work off an `open` elsewhere in
            # the same line, which is the opposite of what it says.
            # `visible`, not `line`. The precheck was masked one round ago
            # and this was not, so a hidden SETTLED cue still reached the
            # clause analysis: `<url> is still open <!-- resolved -->`
            # renders as live work, passed the precheck, and was then
            # suppressed by a phrase no reader can see. Offsets are
            # preserved by the mask, so the same spans index both.
            paren = enclosing_parenthetical(
                para_cue, para_at + m.start(), para_at + m.end())
            clause = (para_cue[paren[0]:paren[1]] if paren
                      else citation_clause(
                          para_cue, para_at + m.start(), para_at + m.end()))
            # The same two cue families cites_live_work reads, against the
            # clause chosen above -- and with NO line-level fallback, which is
            # the stricter half of the rule.
            if SETTLED_CUE_RE.search(clause) and is_settled(clause):
                continue
            if not BLOCKING_CUE_RE.search(clause) or not has_blocking_cue(clause):
                continue
            # `plans #5 and #10` names the domain once and then coordinates.
            # Testing only the text immediately before each `#` saw `plans`
            # for #5 and `and` for #10, so half a list was skipped and half
            # reported. A coordinating separator inherits the decision.
            if SHORTHAND_OTHER_DOMAIN_RE.search(line[:m.start()]) or (
                    skipped_end is not None
                    and _COORDINATOR_RE.fullmatch(line[skipped_end:m.start()])):
                skipped_end = m.end()
                continue
            num = int(m.group("num"))
            c_lo, c_hi = clause_bounds(
                para_cue, para_at + m.start(), para_at + m.end())
            if any(n == num and c_lo <= para_at + at < c_hi
                   for at, n in url_here):
                continue
            st = states.get(THIS_REPO, {}).get(num)
            if st is None or st["state"] != "closed":
                # An unresolvable SHORTHAND is not reported: unlike a URL, it
                # may be a section number the cue happens to share a line with.
                continue
            reason = st.get("reason") or "completed"
            out.append({"check": "closed-issue", "doc": doc, "line": n,
                        "detail": f"{THIS_REPO}#{num} is CLOSED ({reason}) but cited "
                                  "as live work",
                        "severity": "P1" if reason != "not_planned" else "P2",
                        "ref": f"{THIS_REPO}#{num}", "reason": reason})
        # The QUALIFIED shorthand, before the URL pass so the two are read
        # against the same decoded copy. What the URL pass will name, and
        # where -- `[solyra#8](.../issues/8)` carries BOTH spellings of one
        # citation, and reporting it twice would double the finding. Measured
        # across both corpora: every cue-bearing qualified shorthand citing a
        # closed or unresolved issue ALREADY has its URL on the same line, so
        # the risk this carries is doubled findings, not missed ones. Scoped
        # to the CLAUSE for the same reason the bare pass is: two clauses can
        # say opposite things about one number.
        qual_here = [(_src_at(scan_map, mm.start()), mm.group("repo").lower(),
                      int(mm.group("num")))
                     for mm in ISSUE_URL_RE.finditer(scan)
                     if not any(lo <= _src_at(scan_map, mm.start()) < hi
                                for lo, hi in hidden)]
        for m in QUALIFIED_ISSUE_RE.finditer(scan):
            q_start = _src_at(scan_map, m.start())
            q_end = _src_at(scan_map, m.end())
            if any(lo <= q_start < hi for lo, hi in hidden + url_spans):
                continue
            repo, num = m.group("repo").lower(), int(m.group("num"))
            c_lo, c_hi = clause_bounds(
                para_cue, para_at + q_start, para_at + q_end)
            if any(u_repo == repo and u_num == num
                   and c_lo <= para_at + u_at < c_hi
                   for u_at, u_repo, u_num in qual_here):
                continue
            # `visible`, not `line`, for the reason the URL pass below reads
            # the mask: a HIDDEN cue is not evidence.
            if not cites_live_work(para_cue, para_at + q_start, para_at + q_end,
                                   visible_cue):
                continue
            st = states.get(repo, {}).get(num)
            label = f"{repo}#{num}"
            if st is None:
                # Unlike a bare number, this one IS reported: the qualified
                # form can only be an issue, so a number naming none is a
                # defect in the document rather than an ambiguous match.
                out.append({"check": "closed-issue", "doc": doc, "line": n,
                            "detail": f"{label} could not be resolved",
                            "severity": "P2"})
            elif st["state"] == "closed":
                reason = st.get("reason") or "completed"
                out.append({"check": "closed-issue", "doc": doc, "line": n,
                            "detail": f"{label} is CLOSED ({reason}) but cited "
                                      "as live work",
                            "severity": "P1" if reason != "not_planned" else "P2",
                            "ref": f"{repo}#{num}", "reason": reason})
        # Reference-style citations: `Blocked by [#1][issue]` with `[issue]:`
        # and the URL further down. That renders as a clickable issue link,
        # and neither half carries both pieces -- the cue line has no URL and
        # the definition line has no cue -- so a closed issue cited the
        # standard CommonMark way passed the audit clean. The SAME builder
        # the dead-link scan uses, rather than a second copy of the rules.
        # Codex filed it twice on the Node twin (solyra#69).
        for u_at, u_end, u_label in reference_uses(scan):
            target = _ref_defs.get(_ref_key(u_label))
            if target is None:
                continue
            # The destination as a READER resolves it, in the order every
            # other destination here is read in.
            dest = decode_char_refs(unescape_markdown(target[0]))
            hit = ISSUE_URL_RE.search(dest)
            if hit is None:
                continue
            r_start = _src_at(scan_map, u_at)
            r_end = _src_at(scan_map, u_end)
            if any(lo <= r_start < hi for lo, hi in hidden):
                continue
            repo, num = hit.group("repo").lower(), int(hit.group("num"))
            # One citation, however many spellings of it share the clause.
            c_lo, c_hi = clause_bounds(
                para_cue, para_at + r_start, para_at + r_end)
            if any(u_repo == repo and u_num == num
                   and c_lo <= para_at + u_at2 < c_hi
                   for u_at2, u_repo, u_num in qual_here):
                continue
            if not cites_live_work(para_cue, para_at + r_start, para_at + r_end,
                                   visible_cue):
                continue
            is_pr = hit.group("kind").lower() == "pull"
            # A `/pull/N` citation backed by an ISSUE record names no pull
            # request at all. GitHub's issues API returns issues and PRs from
            # one endpoint, so the lookup found the numbered ISSUE and
            # accepted its state -- and if that issue was open, a URL pointing
            # at a pull request that does not exist passed the audit clean.
            # `kind` was already collected and was the one column nothing
            # read. Only this direction: GitHub redirects `/issues/N` to
            # `/pull/N` for a PR, so that spelling IS a link that resolves.
            # Codex filed it (stocks#1121).
            st = states.get(repo, {}).get(num)
            if is_pr and st is not None and st.get("kind") == "ISSUE":
                st = None
            label = f"{repo}#{num}" + (" (PR)" if is_pr else "")
            if st is None:
                out.append({"check": "closed-issue", "doc": doc, "line": n,
                            "detail": f"{label} could not be resolved",
                            "severity": "P2"})
            elif st["state"] == "closed":
                reason = st.get("reason") or ("closed" if is_pr else "completed")
                out.append({"check": "closed-issue", "doc": doc, "line": n,
                            "detail": f"{label} is CLOSED ({reason}) but cited "
                                      "as live work",
                            "severity": "P1" if reason != "not_planned" else "P2",
                            "ref": f"{repo}#{num}", "reason": reason})
        for m in ISSUE_URL_RE.finditer(scan):
            m_start = _src_at(scan_map, m.start())
            m_end = _src_at(scan_map, m.end())
            if any(lo <= m_start < hi for lo, hi in hidden):
                continue
            # The line carries a live-work cue; does THIS citation's clause say
            # the opposite? Both cue families are read against the clause now
            # (see cites_live_work), with the line as the fallback when the
            # clause carries no cue of its own.
            # `visible`, not `line` -- this is the call Codex named. The
            # PRECHECK was masked one round ago and the per-citation analysis
            # was not, so a hidden SETTLED cue still reached it:
            # `<url> is still open <!-- resolved -->` renders as live work,
            # passed the precheck, and was then suppressed by a phrase no
            # reader can see. The mask preserves offsets, so the same spans
            # index both strings.
            if not cites_live_work(para_cue, para_at + m_start, para_at + m_end,
                                   visible_cue):
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
            # `visible`, not `line`, for the same reason cites_live_work above
            # reads the mask: a HIDDEN cue is not evidence. With a visible cue
            # elsewhere on the line, `#1 is still open; <PR url> <!-- is still
            # open -->` passed the line-level fallback and this guard then
            # accepted the commented phrase as the PR's own local evidence --
            # a fabricated P1 against a PR no visible prose calls live. The
            # mask preserves offsets, so the same spans index both strings.
            if is_pr and not BLOCKING_CUE_RE.search(
                    citation_clause(visible, m_start, m_end)):
                continue
            repo, num = m.group("repo").lower(), int(m.group("num"))
            label = f"{repo}#{num}" + (" (PR)" if is_pr else "")
            # Same kind check the reference pass applies; see there.
            st = states.get(repo, {}).get(num)
            if is_pr and st is not None and st.get("kind") == "ISSUE":
                st = None
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


def is_escaped(text: str, i: int) -> bool:
    """Is the character at `i` escaped by the backslashes before it?

    PARITY, not presence. `\\[x](y.md)` is a literal backslash followed by a
    real link -- the first backslash escapes the second -- so a one-character
    look-back called it escaped and skipped a genuinely broken rendered link.
    The Node twin has counted these since solyra#69.
    """
    n = 0
    k = i - 1
    while k >= 0 and text[k] == "\\":
        n += 1
        k -= 1
    return n % 2 == 1


def mask_spans(line: str, spans: list[tuple[int, int]]) -> str:
    """The line with `spans` blanked, keeping every other offset where it was.

    Spaces rather than deletion on purpose: the callers compute match offsets
    against the ORIGINAL line, so a shorter masked copy would silently shift
    every span that follows one.
    """
    if not spans:
        return line
    out = list(line)
    for lo, hi in spans:
        for i in range(max(lo, 0), min(hi, len(out))):
            out[i] = " "
    return "".join(out)


def _html_tag_spans(text: str) -> list[tuple[int, int]]:
    """Offsets of the COMPLETE HTML tags in `text`, escaped openers excluded.

    A backtick inside a tag is part of that tag, not a code-span delimiter:
    CommonMark gives code spans, raw HTML and autolinks equal precedence and
    lets whichever BEGINS FIRST win. `_TAG_OPEN_RE` carries `re.S`, so this
    answers for a joined document as well as for one line.
    """
    if "<" not in text:
        return []
    return [(mm.start(), mm.end()) for mm in _TAG_OPEN_RE.finditer(text)
            if not is_escaped(text, mm.start())]


def _tag_covering(tags: list[tuple[int, int]], start: int, pos: int) -> int | None:
    """End of the tag that owns a delimiter run at `start`, or None.

    Only a tag that begins at or after `pos` counts, because a tag opening
    inside an already-running span is literal text -- which is the same
    "begins first wins" rule read from the other side.
    """
    return next((hi for lo, hi in tags if pos <= lo <= start < hi), None)


def code_spans(line: str) -> list[tuple[int, int]]:
    """Offset ranges of inline code spans, CommonMark's backtick-run rule.

    A run of N backticks opens a span that only a run of exactly N closes, so
    ``` ``a ` b`` ``` is one span rather than two.
    """
    # An ESCAPED run is a literal backtick, not a delimiter. `` \` [x](y.md) \` ``
    # renders two backticks and a LIVE link, and masking the range between them
    # made the dead-link and blocker passes skip a real citation -- the hiding
    # direction. Parity, via is_escaped, so `\\\`` (a literal backslash) still
    # opens a span.
    #
    # Skipped while SCANNING, not filtered afterwards. A post-hoc filter cannot
    # recover an opener the rejected match already consumed: on
    # `` \` literal ` [x](y.md) ` `` the escaped tick paired with the real
    # opener, the pair was then discarded, and the genuine span went unmasked
    # -- so the example link inside it was reported dead. Restarting the search
    # one character past a rejected opener is what lets the real one pair.
    #
    # A backtick inside a COMPLETE HTML tag is part of that tag, not a
    # delimiter. In `<span title="`"> [x](missing.md) ` tail` the tag begins
    # at column 0 and owns its quoted backtick -- while pairing it with the
    # trailing one masked a live link out of the audit and the missing target
    # passed clean. Codex filed it.
    tags = _html_tag_spans(line)
    out: list[tuple[int, int]] = []
    pos = 0
    while pos < len(line):
        mm = _CODE_SPAN_RE.search(line, pos)
        if mm is None:
            break
        if is_escaped(line, mm.start()):
            pos = mm.start() + 1
            continue
        covering = _tag_covering(tags, mm.start(), pos)
        if covering is not None:
            pos = covering
            continue
        out.append((mm.start(), mm.end()))
        pos = mm.end()
    return out


# ATX syntax, the same shape marker_window tests with.
_ATX_HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?:\s|$)")
# Three or more `*`, `-` or `_`, optionally spaced, and nothing else.
_THEMATIC_BREAK_RE = re.compile(
    r"^ {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$")


def _paragraph_blocks(lines: list[str], fenced: set[int]) -> list[tuple[int, int]]:
    """Runs of consecutive lines that can hold ONE paragraph, as (first, last).

    A blank line ends a paragraph and a fence interrupts it, so inline syntax
    may not pair across either. Callers that scan the joined document need the
    boundary as a scan WINDOW rather than as masking: a blank line has no
    characters to mask, so masking leaves the neighbouring paragraphs adjacent
    and the pairing happens regardless.

    A HEADING and a thematic break are blocks of their OWN, not merely
    boundaries. An unmatched backtick, then `# Heading`, then a live
    `[x](missing.md)` had the two backticks paired across the heading and the
    broken link masked out of the audit -- none of those lines is blank, so
    the blank rule alone does not reach it. Making each its own block also
    gives the type-7 HTML scan the "a paragraph could start here" test it
    needs. Ported from the Node twin (solyra#69).
    """
    blocks: list[tuple[int, int]] = []
    start: int | None = None
    open_depth = 0

    def flush(end: int) -> None:
        nonlocal start
        if start is not None and end >= start:
            blocks.append((start, end))
        start = None

    for i, line in enumerate(lines):
        if (not line.strip()) or i in fenced:
            flush(i - 1)
            continue
        # Read through the container prefix, as every other block test here is.
        bare = _BLOCKQUOTE_PREFIX_RE.sub("", line, count=1)
        # A SETEXT UNDERLINE closes the heading it belongs to, and a heading is
        # a block of its own exactly as an ATX one is. Without this an
        # unmatched delimiter in the heading text paired with one in the
        # paragraph BELOW the underline, and code_span_lines masked a live
        # `[x](missing.md)` between them out of the audit. Tested BEFORE the
        # thematic break, which is what `---` under a paragraph would
        # otherwise be read as; `is_setext_underline` is the same predicate
        # heading_anchors uses, so the two cannot disagree about where a
        # heading ends.
        # The cheap shape test first: `is_setext_underline` strips the
        # container again and reads the line above, and this runs on every
        # non-blank line of every block scan. Same pattern the predicate
        # applies, against the copy already stripped here, so the guard
        # cannot disagree with it.
        if (start is not None and _SETEXT_UNDERLINE_RE.fullmatch(bare)
                and is_setext_underline(lines, i, fenced)):
            flush(i)
            continue
        # A LIST MARKER is a container prefix too, and CommonMark removes it
        # before parsing the block inside the item: `- # Heading` opens an ATX
        # heading as the item's first block. The prefix hid it, so an
        # unmatched backtick in that heading paired with one in the paragraph
        # below and `code_span_lines` masked a live `[x](missing.md)` between
        # them out of the audit -- the hiding direction. The marker is
        # stripped for the BLOCK tests only: the container-transition test
        # below has to keep seeing it, since a new item is a new paragraph.
        # Codex filed it.
        inner = _LIST_MARKER_RE.sub("", bare, count=1)
        if _ATX_HEADING_RE.match(inner) or _THEMATIC_BREAK_RE.match(inner):
            flush(i - 1)
            blocks.append((i, i))
            continue
        # A CONTAINER transition ends the block too. A new list item opens its
        # own paragraph, and so does a change of blockquote depth: `- [open`
        # over `- label](missing.md)` is two items, not one paragraph, and
        # joining them paired the brackets into a link no reader can click.
        # The same grouping feeds code_span_lines, where delimiters in
        # separate containers were masking live content between them.
        # DEEPER only. A line at a SHALLOWER quote depth than the open
        # paragraph is a LAZY CONTINUATION, not a container transition:
        # CommonMark lets a paragraph inside a blockquote continue on a line
        # that omits the `>`, so `> sample \`` over `[x](missing.md) \`` is
        # one paragraph holding one multi-line code span. Splitting them put
        # the two delimiters in separate windows, `code_span_lines` found no
        # span, and the audit emitted a gating dead-link finding for literal
        # code. Every line that could START a block rather than continue one
        # has already been handled above -- blank, fenced, heading, setext
        # underline, thematic break -- and a list marker is tested beside
        # this, so what reaches here at a lower depth can only be a
        # continuation. Codex filed it on the Node twin (solyra#69); the same
        # probe showed it live here.
        depth = quote_depth(line)
        if start is not None and (depth > open_depth
                                  or _LIST_MARKER_RE.match(bare)):
            flush(i - 1)
        if start is None:
            start = i
            open_depth = depth
    flush(len(lines) - 1)
    return blocks


_CODE_SPAN_MULTILINE_RE = re.compile(r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)", re.S)

_MD_ESCAPE_RE = re.compile(r"\\([!-/:-@\[-`{-~])")


def unescape_markdown(text: str) -> str:
    """CommonMark backslash escapes removed, as rendering removes them.

    `[x](docs/a\\(b\\).md)` links to the tracked `docs/a(b).md`; keeping the
    backslashes reported that valid link as dead. Only before ASCII
    punctuation, which is the whole set CommonMark allows an escape before --
    a backslash anywhere else is a literal character, and dropping it would
    name a different path.
    """
    return _MD_ESCAPE_RE.sub(r"\1", text)


def code_span_lines(lines: list[str],
                    fenced: set[int] | None = None) -> dict[int, list[tuple[int, int]]]:
    """Code-span ranges per line index, for spans that CROSS line breaks.

    `code_spans` is per physical line and so cannot see a span whose opening
    and closing backticks are on different lines -- a blocker-shaped URL or a
    `[x](missing.md)` inside one was audited as live prose and could fail
    --check. The document is scanned once here and the ranges split back per
    line, so every caller keeps its per-line offsets.
    """
    # A separate DOTALL pattern rather than widening the shared one: every
    # other caller passes a single line, where the two behave identically, and
    # a shared `re.S` would be a change none of them asked for.
    # PER PARAGRAPH, not across the whole document. Inline content cannot span
    # a blank line, so joining everything let an unmatched backtick in one
    # paragraph pair with another far below it -- masking every live link in
    # between and silently dropping their findings. Blank lines are kept in the
    # joined text (as blanks) so offsets still map back to a line; the scan is
    # simply restarted at each one.
    # The same block model the link scan uses, so the two cannot disagree
    # about where inline content ends. Half-open (first, last + 1) here, which
    # is what the slice arithmetic below expects.
    #
    # A FENCED BLOCK interrupts a paragraph exactly as a blank line does, so
    # an unmatched delimiter above a fence paired with one below it and masked
    # everything between -- including a live `[x](missing.md)`, which the
    # gating dead-link check then never saw. The set is a PARAMETER rather
    # than computed here: this function also runs UNDERNEATH `fenced_lines`
    # (through `comment_spans`), and computing one there would be a cycle. So
    # callers that already hold a fence set pass it, and the ones below the
    # fence scan pass nothing and keep today's behaviour -- which is the
    # honest shape of the constraint rather than a claim the cycle does not
    # exist.
    blocks = [(lo, hi + 1) for lo, hi in _paragraph_blocks(lines, fenced or set())]

    starts: list[int] = []
    at = 0
    for line in lines:
        starts.append(at)
        at += len(line) + 1
    text = "\n".join(lines)
    # The SAME tag rule `code_spans` applies, over the joined document rather
    # than one line. Two scanners for one rule is how they drift, and they had
    # already drifted here: fixing only the per-line one left the attribute
    # backtick pairing across lines and the live link masked anyway.
    tags = _html_tag_spans(text)
    out: dict[int, list[tuple[int, int]]] = {}
    for b_lo, b_hi in blocks:
        # The scan WINDOW is the block, so a delimiter can only pair with one
        # in the same paragraph. Searching the whole joined text and masking
        # the blanks is not equivalent: a blank line contributes no characters
        # to mask, so the two paragraphs still sit adjacent in the subject and
        # the pairing happened anyway -- measured.
        lo_at = starts[b_lo]
        hi_at = starts[b_hi - 1] + len(lines[b_hi - 1])
        pos = lo_at
        while pos < hi_at:
            m = _CODE_SPAN_MULTILINE_RE.search(text, pos, hi_at)
            if m is None:
                break
            # Escaped delimiters are literal here too -- same rule as
            # code_spans, and skipped while SCANNING for the same reason: a
            # rejected match must not consume the real opener.
            if is_escaped(text, m.start()):
                pos = m.start() + 1
                continue
            covering = _tag_covering(tags, m.start(), pos)
            if covering is not None:
                pos = covering
                continue
            lo, hi = m.start(), m.end()
            for i in range(b_lo, b_hi):
                a, b = starts[i], starts[i] + len(lines[i])
                if hi <= a or lo >= b:
                    continue
                out.setdefault(i, []).append(
                    (max(lo - a, 0), min(hi - a, len(lines[i]))))
            pos = m.end()
    return out


def _refdef_span_hidden(lines: list[str],
                        wrapped: dict[int, list[tuple[int, int]]], i: int) -> bool:
    """Is line `i` covered ENTIRELY by one code span, single-line or wrapped?

    A definition-shaped line inside a span is an EXAMPLE of a definition.
    Shared by the single-line form and by the continuation line of the
    two-line form, so the two cannot disagree about what is hidden.
    """
    line = lines[i]
    stop = len(line.rstrip())
    return bool(stop) and any(
        lo <= 0 and hi >= stop
        for lo, hi in code_spans(line) + wrapped.get(i, []))


def reference_uses(text: str):
    """Reference-style link USES in one line: `[t][label]`, `[label][]`, `[label]`.

    Yielded as `(at, end, label)` with the offsets of the WHOLE use, because
    that is where a reader sees the citation and what every gate around it
    indexes.

    The dead-link scan deliberately does NOT check uses -- measured on this
    corpus, 204 bracket pairs against 1 definition, nearly all of them
    issue-title tags like `[P0][Replay]`, and checking them produced 79
    fabricated findings. That reasoning does not carry to the blocker scan: a
    use is acted on there ONLY when its label resolves to a definition whose
    destination is an issue URL, and a title tag resolves to nothing. Ported
    from the Node twin (solyra#69).
    """
    i = 0
    while i < len(text):
        if text[i] != "[" or is_escaped(text, i):
            i += 1
            continue
        close = _label_close(text, i)
        if close == -1:
            i += 1
            continue
        after = text[close + 1] if close + 1 < len(text) else ""
        # An INLINE link is not a reference use: without this, `[issue](x.md)`
        # reads as a shortcut use of `issue` and invents a citation the
        # document does not make.
        #
        # The `:` half is NOT pinned by a test, and saying so is the honest
        # version: a definition is not a use of itself, but every input that
        # reaches it (`[g]: <url> "still open"`, the only definition shape
        # carrying a cue) is already collapsed to one finding by the clause
        # dedup, so no test can distinguish it. Kept because reading a
        # definition as a use is wrong about the grammar rather than merely
        # redundant.
        if after in ("(", ":"):
            i = close + 1
            continue
        label = text[i + 1:close]
        end = close + 1
        if after == "[":
            close2 = _label_close(text, close + 1)
            if close2 == -1:
                i = close + 1
                continue
            second = text[close + 2:close2]
            # FULL form takes the second label; COLLAPSED (`[label][]`) keeps
            # the first, which is what CommonMark resolves it by.
            if second.strip():
                label = second
            end = close2 + 1
        yield i, end, label
        i = end


def reference_definitions(lines: list[str]) -> dict[str, tuple[str, int]]:
    """Every reference definition in the document, keyed by its normalised label.

    ONE implementation, because two consumers now ask the same question and a
    second copy is how the two would drift: the dead-link scan validates a
    definition's destination, and the blocker scan resolves a reference USE to
    see whether it cites an issue. A definition is registered only where
    CommonMark registers one, and every exclusion below is a case where it
    does not. Ported from the Node twin (solyra#69).
    """
    fenced = (fenced_lines(lines) | indented_code_lines(lines)
              | raw_html_block_lines(lines) | front_matter_lines(lines))
    commented = comment_spans(lines)
    wrapped_code = code_span_lines(lines, fenced)
    # Reference-style Markdown: `[guide][g]` with `[g]: docs/guide.md` further
    # down. Neither shape is an inline link, so a broken reference link -- the
    # form CommonMark calls standard and readers see as an ordinary link --
    # produced a clean audit. The DEFINITION's destination is validated exactly
    # as an inline link's is. A footnote (`[^1]: ...`) is excluded: it defines
    # a note, not a destination. A
    # A use is excluded too -- see REF_USE_RE for the measurement that says
    # bracketed prose in this corpus cannot be told apart from one.
    ref_defs: dict[str, tuple[str, int]] = {}
    # And only where a definition may BEGIN. CommonMark does not let a
    # definition interrupt a paragraph, so `paragraph` over `[g]: missing.md`
    # renders both lines as prose and registers no reference at all -- yet
    # this loop validated the second line and emitted a gating dead-link
    # finding for text that produces no link. `heading_anchors` has applied
    # the rule since the round it was raised; this half of the same rule did
    # not, which is the two-implementations shape again. Consecutive
    # definitions still count: a block of them is one run, so each accepted
    # definition opens the line after it.
    _def_starts = {lo for lo, _ in _paragraph_blocks(lines, fenced)}
    _def_seen: set[int] = set()
    for n, line in enumerate(lines, 1):
        if n - 1 in fenced or (n - 1) in commented and any(
                a == 0 for a, _ in commented[n - 1]):
            continue
        # A definition-shaped line inside a code span is an EXAMPLE of one, not
        # a definition. The single-line form cannot match anyway -- the opening
        # backtick sits where `^ {0,3}\[` needs a bracket -- but a span opened
        # on an earlier line covers this one whole, and `[g]: missing.md`
        # displayed inside such a span was validated as a live destination.
        # Same mechanism the inline-link pass below already excludes.
        if _refdef_span_hidden(lines, wrapped_code, n - 1):
            continue
        # A definition inside a blockquote still defines: `> [g]: docs/g.md`
        # renders as a working reference for uses inside that quote. The
        # anchored pattern saw `>` where it needs a bracket, so every quoted
        # definition went unchecked -- and a quoted use resolving to a dead
        # path is exactly as broken as an unquoted one.
        line = _BLOCKQUOTE_PREFIX_RE.sub("", line, count=1)
        # A LIST MARKER is a container prefix too: `- [g]: missing.md` is the
        # first content of an item, and CommonMark resolves a use of `[g]`
        # inside that item as a clickable link. The anchored pattern saw the
        # marker where it needs a bracket, so such a definition went unparsed
        # -- and because reference USES are deliberately not scanned, its
        # broken destination produced no finding at all.
        line = _LIST_MARKER_RE.sub("", line, count=1)
        if not ((n - 1) in _def_starts or (n - 2) in _def_seen):
            continue
        rm = REF_DEF_RE.match(line)
        # The REMAINDER has to be a definition too. A prefix match accepted
        # `[g]: missing.md nonsense`, which CommonMark renders as ordinary
        # text -- no definition, no link -- and reported its destination as a
        # gating dead link for something no reader can click.
        if rm is not None and not REF_DEF_TAIL_RE.match(line, rm.end()):
            rm = None
        # The destination may sit on the FOLLOWING line: `[guide]:` then
        # `  missing.md` is a definition CommonMark resolves, and `[x][guide]`
        # renders as a clickable link to it. A per-line pattern could not
        # capture that, and because reference USES are deliberately not
        # scanned, the broken destination produced no finding at all. The
        # continuation is read through the same exclusions as any other line,
        # and the finding is reported against the line the destination is on,
        # which is where a fix goes. Ported from the Node twin (solyra#69).
        label = rm.group("label") if rm else None
        target = rm.group("target") if rm else None
        dest_line = n
        if rm is None:
            head = REF_DEF_HEAD_RE.match(line)
            j = n  # zero-based index of the NEXT line
            if (head and j < len(lines) and j not in fenced
                    and not (j in commented
                             and any(a == 0 for a, _ in commented[j]))
                    and not _refdef_span_hidden(lines, wrapped_code, j)):
                cont = _BLOCKQUOTE_PREFIX_RE.sub("", lines[j], count=1)
                dm = REF_DEF_CONT_RE.match(cont)
                if dm:
                    label, target, dest_line = head.group("label"), dm.group("target"), j + 1
        # The FIRST definition wins, as Markdown renders it. Overwriting with
        # the last meant `[g]: missing.md` followed by `[g]: good.md` rendered
        # as a broken link while the audit validated only `good.md`.
        if label is not None:
            # Through _ref_key, like every other label site. This map was the
            # third place keying a label its own way, so `[my ref]` and
            # `[my   ref]` were stored as two definitions and the second --
            # which CommonMark never resolves, the first wins -- was validated
            # and reported dead. Found by sweeping for the pattern rather than
            # by waiting for it to be reported a third time.
            # The LAST line this definition occupied, so the two-line form
            # opens the line after its destination rather than the line after
            # its label.
            _def_seen.add(dest_line - 1)
            ref_defs.setdefault(_ref_key(label),
                                (target.strip("<>"), dest_line))
    return ref_defs


def check_dead_links(doc: str, text: str, tracked: set[str],
                     root_files: set[str] | None = None,
                     base_exts: set[str] | None = None) -> list[dict]:
    out = []
    # Every extension this tree actually tracks. CODE_EXTS is the floor, so a
    # rename that empties an extension out of the tree does not make its
    # citations silently uncheckable.
    #
    # `tracked` has already had staged deletions removed, so deriving the set
    # from it alone defeated that guarantee in exactly the case it was written
    # for: deleting the last `.ipynb` took `.ipynb` out of the allowed
    # suffixes, and the surviving citations to the deleted file were skipped
    # rather than reported. The BASE REF's suffixes are passed in and unioned,
    # the same way its root filenames already are.
    cited_exts = CODE_EXTS | (base_exts or set()) | {
        pathlib.PurePosixPath(p).suffix for p in tracked
        if pathlib.PurePosixPath(p).suffix}
    # Names the BASE REF's root held. A bare citation is this repo's to resolve
    # only when the root actually had a file by that name, because a basename
    # alone is otherwise indistinguishable from prose -- and from a
    # subdirectory file cited by its basename, which this corpus does
    # constantly. Measured: keying on the EXTENSION instead produced 304
    # fabricated findings on this tree in one run, every one a real file named
    # without its directory (`db-query.yml`, `MODEL_REGISTRY.md`). The caller
    # passes the pre-deletion set, which is what makes a deleted root file
    # reportable at all; defaulting to `tracked` means no finding, not a wrong
    # one.
    known_root = root_files if root_files is not None else {
        p for p in tracked if "/" not in p}
    base = pathlib.PurePosixPath(doc).parent
    anchors: dict[str, set[str] | None] = {}

    def anchors_of(path: str) -> set[str] | None:
        if path not in anchors:
            # The LINKED document gets the same refusal the audited one does.
            # The preflight guards the doc being scanned, not the ones it
            # cites, so a link to a tracked symlink read the target's
            # machine-local bytes to collect its headings -- and a link
            # pointing at a non-terminating special file such as `/dev/zero`
            # hangs or exhausts memory here, which is the failure the guard
            # exists to prevent. OSError below cannot catch either one.
            refuse_symlink(path)
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
        # Against the RENDERED spelling as well as the written one. A
        # destination may encode the scheme separator as a character
        # reference or hide it behind a backslash escape --
        # `[x](https&#58;//example.com)` renders as an ordinary HTTPS link --
        # and testing only the raw text sent it down the repository-path
        # branch, where it became a gating dead-link finding for a file no
        # one ever meant to exist locally. Percent escapes are deliberately
        # NOT decoded here: `https%3A//x` stays percent-encoded in the href,
        # so a browser resolves it relative to this document, which is the
        # repository-path branch after all.
        rendered = decode_char_refs(unescape_markdown(tgt))
        if (_URI_SCHEME_RE.match(tgt) or tgt.startswith("//")
                or _URI_SCHEME_RE.match(rendered) or rendered.startswith("//")):
            return
        # `[x](#heading)` -- same document, so the anchor is still
        # checkable even though there is no path to resolve.
        # `[g](<guide.md>)` is the standard form for a destination with a
        # space, and the angle brackets are delimiters. A query string is not
        # part of the path either: the tracked lookup searched for the literal
        # `guide.md?plain=1`.
        # Stripping the query can empty the path outright -- `[x](?plain=1#h)`
        # is a link to THIS document carrying a query string. Returning on an
        # empty path skipped the fragment check entirely, so a dead anchor
        # spelled that way passed; it is the same same-document case as `#h`.
        bare = tgt[1:-1] if tgt.startswith("<") and tgt.endswith(">") else tgt
        # Decoded BEFORE the query is removed. `&#63;` IS a `?`, so
        # `[x](guide.md&#63;plain=1)` renders a URL whose PATH is `guide.md`,
        # and splitting the raw destination left the nonexistent
        # `guide.md?plain=1` once decoded -- a gating dead link against a
        # tracked file. Percent decoding stays AFTER, because `%3F` is not a
        # delimiter either: a file really named with a percent-escaped `?`
        # would otherwise lose its name. The Node twin has split in this order
        # since it was raised there.
        # A decoded `#` IS the fragment delimiter. `&#35;` resolves to `#`
        # when the link is constructed, so `[x](README.md&#35;tests)` gives
        # the href `README.md#tests` and the browser splits there -- while
        # this looked for a tracked file literally named `README.md#tests`
        # and reported a gating dead link against one that exists. The
        # caller's `split_outside_refs` consumes references as UNITS,
        # deliberately, so it cannot see this one; the split has to happen
        # after decoding.
        #
        # Only a reference, not a BACKSLASH escape. `[x](a\#b.md)` is
        # asserted elsewhere to target the tracked `a#b.md`, and whether
        # CommonMark percent-encodes that `#` is a question I have not put to
        # a reference implementation -- so the escape is left alone rather
        # than changed on an argument. That is why the decode happens in two
        # steps here: the references first, the split, then the escapes.
        # Codex filed it on the Node twin (solyra#69).
        decoded_ref = decode_char_refs(bare)
        cut = next((k for k, ch in enumerate(decoded_ref)
                    if ch == "#" and not is_escaped(decoded_ref, k)), -1)
        decoded_frag = decoded_ref[cut + 1:] or None if cut != -1 else None
        bare = unescape_markdown(
            decoded_ref if cut == -1 else decoded_ref[:cut]).split("?")[0]
        if not bare:
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
            # Backslash escapes as well as percent escapes: CommonMark
            # removes them when the destination renders, so
            # `[x](docs/a\(b\).md)` resolves to the tracked `docs/a(b).md`
            # and keeping them reported that valid link dead.
            # Character references too. `[t](caf&eacute;.md)` RENDERS as a
            # link to `café.md`, and normalising only percent escapes and
            # backslashes reported a tracked file dead.
            decoded = urllib.parse.unquote(bare)
            if decoded.startswith("/"):
                # Site-absolute. GitHub resolves it from the HOST root, not the
                # repository root, so stripping the slash and looking it up in
                # `tracked` answered a different question than the one asked:
                # `[g](/docs/guide.md)` passed because `docs/guide.md` exists
                # although the link navigates to github.com/docs/guide.md, and
                # a real host route like `/settings/profile` was called dead.
                # Neither verdict is available without knowing the host, so
                # this audit declines to give one. Zero such destinations exist
                # in this tree, measured; the change is reach, not a catch.
                return
            resolved = posixpath.join(str(base), decoded)
            norm = posixpath.normpath(resolved)
            # A PARENT component, not any name that starts with two dots.
            # `..missing.md` is a legal repository filename that normalises to
            # itself, and treating it as traversal meant a deleted or
            # misspelled dot-prefixed target was never reported at all. Parity
            # with the Node twin (solyra#69).
            if norm == ".." or norm.startswith("../"):
                # Climbs out of the repository: cross-repo prose, which
                # this repo cannot resolve and must not call rot.
                return
            if norm not in tracked and not is_tracked_dir(tracked, norm):
                out.append({"check": "dead-link", "doc": doc, "line": n,
                            "detail": what, "severity": "P2"})
                return
        # The target resolves; does the heading it names?
        # A fragment the DESTINATION carried as a character reference, which
        # the caller's reference-aware split could not separate.
        want_frag = frag or decoded_frag
        if want_frag and norm.endswith(".md"):
            have = anchors_of(norm)
            # The fragment as the BROWSER resolves it. `#caf%C3%A9` is the
            # ordinary spelling of a link to `## Cafe\u0301`, and comparing the
            # encoded form against the decoded slug reported a working link
            # dead -- the false direction, which is the one that makes an audit
            # untrustworthy rather than merely incomplete.
            # Decoded but NOT lowercased. A browser matches a fragment against
            # an element id case-SENSITIVELY, so `#Details` does not navigate
            # to the heading whose generated id is `details`; folding the case
            # accepted a link that does not work. `heading_anchors` already
            # yields the generated (lowercased) ids, so the comparison is
            # against what the renderer actually emits.
            if have is not None and decode_fragment(want_frag) not in have:
                out.append({"check": "dead-anchor", "doc": doc, "line": n,
                            "detail": f"{anchor_what}#{want_frag}: the target has no "
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
    # And a raw HTML block. `<div>` followed by `[x](missing.md)` with no blank
    # line between them renders the bracket syntax LITERALLY -- CommonMark does
    # not parse Markdown inside an HTML block -- so the destination was
    # reported dead over a link no reader can click. Every kind, not only the
    # raw-text ones: a type-6 or type-7 block suppresses Markdown parsing just
    # as `<pre>` does. That is the opposite of the blocker scan's rule, and
    # deliberately: an `<a href>` inside a rendered block IS a citation, while
    # Markdown syntax there is not.
    # And YAML FRONT MATTER, which GitHub renders as a metadata table rather
    # than as body text: `title: "[guide](missing.md)"` is not a link a reader
    # can click, so the destination produced a gating finding over nothing.
    # Heading discovery already excludes these lines; the link scan did not.
    _fence_only = fenced_lines(lines) | indented_code_lines(lines)
    fenced = (_fence_only | raw_html_block_lines(lines)
              | front_matter_lines(lines))
    # Retired Markdown kept in a comment is not rendered, so it is not a
    # citation -- but only the commented SPAN is invisible, not the line.
    commented = comment_spans(lines)
    # Every BLOCK boundary, not just the code ones. An unmatched backtick
    # above a fence paired with one below it and masked a live
    # `[x](missing.md)` in between out of this very check, and the comment
    # here used to say a rendered HTML block does not end a paragraph the way
    # a code block does. It does: CommonMark lets an HTML block of types 1
    # through 6 interrupt one, and type 7 only opens where a paragraph is not
    # already running -- which `raw_html_block_lines` already enforces. So
    # `` ` `` above `<pre></pre>` paired with one below it and hid the broken
    # link between them. Codex filed it on the Node twin (solyra#69).
    wrapped_code = code_span_lines(lines, fenced)

    ref_defs = reference_definitions(lines)
    for label, (target, n) in ref_defs.items():
        # Not `partition("#")`: a reference definition bypasses `md_links`, so
        # it was the one destination still split before escapes and character
        # references were consumed. `[g]: a\\#b.md` targets the tracked
        # `a#b.md` and was reported dead as `a\\`.
        tgt, frag = split_outside_refs(target, "#")
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
        # Wrapped spans too: a `[x](missing.md)` inside a code span opened on
        # one line and closed on the next was scanned as a live link.
        spans = (code_spans(line) + commented.get(n - 1, [])
                 + wrapped_code.get(n - 1, []))
        for m in md_links(line):
            if any(lo <= m.start() < hi for lo, hi in spans):
                continue
            if is_escaped(line, m.start()):
                continue
            # Either destination form. The angle-bracketed branch is separate
            # in the pattern because it admits a space; both name the same
            # thing here.
            tgt = m.group("btarget")
            frag = m.group("bfrag")
            if tgt is None:
                tgt, frag = m.group("target"), m.group("frag")
            check_target(tgt, frag, n)
        hidden = commented.get(n - 1, [])
        # Spans a backticked citation occupies purely as a Markdown link's
        # LABEL. ``[`platform/src/missing.ts`](../platform/src/missing.ts)``
        # is ONE broken link: the inline pass above has already reported its
        # destination, and reporting the label too doubles the finding and the
        # summary count, presenting one repair as two. The label spans come
        # from `md_links` rather than a second pattern, so the two passes
        # cannot disagree about where a label ends. The Node twin (solyra#69)
        # has carried this exclusion; Codex filed the gap here.
        label_spans = [(lm.start() + 1, lm.label_end) for lm in md_links(line)
                       if lm.label_end > lm.start() + 1]

        def _in_label(idx: int) -> bool:
            return any(lo <= idx < hi for lo, hi in label_spans)
        # A citation nested inside a WIDER code span is sample text, not a
        # citation: ``example `scripts/missing.py` here`` renders the inner
        # backticks and the path literally, and reporting it failed --check
        # over a document's own illustration. STRICT enclosure, because an
        # ordinary single-backtick citation IS its own span -- testing mere
        # overlap would skip every backticked path in the corpus.
        def _span_body(lo: int, hi: int) -> str:
            """What a code span at these offsets RENDERS, delimiters removed.

            The run length is read off the span itself rather than assumed to
            be one, because that is the whole question here.
            """
            run = len(line[lo:hi]) - len(line[lo:hi].lstrip("`"))
            return line[lo + run:hi - run] if run else line[lo:hi]

        def _nested(m: re.Match[str]) -> bool:
            # STRICT enclosure alone is not the test. A valid MULTI-backtick
            # span renders nothing but the path -- ``scripts/missing.py`` is a
            # citation, not a demonstration -- but `BACKTICK_PATH_RE` matches
            # from the second opening tick to the first closing one, which is
            # strictly inside it, so the path was classified as sample text
            # and deleting the target produced no finding at all. A span whose
            # COMPLETE rendered body is the cited path is the citation; only a
            # WIDER span, one that renders prose around an inner citation, is
            # the demonstration this exclusion exists for. Codex filed it.
            return any(lo < m.start() and hi > m.end()
                       and _span_body(lo, hi).strip() != m.group(0).strip("`").strip()
                       for lo, hi in code_spans(line) + wrapped_code.get(n - 1, []))
        # A bare root filename resolves against the tree's ROOT only. Anything
        # it does not hold is prose, not rot -- which is what makes the second
        # pattern safe to run at all.
        for m in BACKTICK_ROOT_FILE_RE.finditer(line):
            if (any(lo <= m.start() < hi for lo, hi in hidden) or _nested(m)
                    or _in_label(m.start())):
                continue
            cited = m.group("path")
            name = LINE_SUFFIX_RE.sub("", cited)
            if name in tracked or name not in known_root:
                continue
            out.append({"check": "dead-link", "doc": doc, "line": n,
                        "detail": f"backticked path -> {cited}", "severity": "P2"})
        for m in BACKTICK_PATH_RE.finditer(line):
            if (any(lo <= m.start() < hi for lo, hi in hidden) or _nested(m)
                    or _in_label(m.start())):
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

    # The RENDERED-HTML destinations, which no Markdown pattern sees. A
    # raw-TEXT block is excluded because a tag inside `<pre>` is DISPLAYED
    # rather than rendered; a type-6 or type-7 block is not, which is why this
    # loop has a skip set of its own rather than reusing `fenced` -- that one
    # now masks every HTML block, because Markdown syntax is not parsed there
    # while an `<a href>` in the same block still resolves.
    href_skip = (fenced_lines(lines) | indented_code_lines(lines)
                 | raw_html_block_lines(lines, raw_text_only=True))
    for n, line in enumerate(lines, 1):
        if n - 1 in href_skip:
            continue
        href_hidden = (code_spans(line) + commented.get(n - 1, [])
                       + wrapped_code.get(n - 1, []))
        for m in HTML_HREF_RE.finditer(line):
            if any(lo <= m.start() < hi for lo, hi in href_hidden):
                continue
            # `\<a href="missing.md">` escapes the `<`, so CommonMark renders
            # the tag as TEXT and there is no clickable link -- the Markdown
            # pass has applied this check for rounds and the href pass did
            # not, so the same escape produced a gating finding here.
            if is_escaped(line, m.start()):
                continue
            href = m.group("dq") or m.group("sq") or m.group("bare") or ""
            # The same unit-consuming split every other destination uses, so
            # `<a href="foo&#38;bar.md">` resolves to the tracked `foo&bar.md`
            # rather than being cut at the `#` inside the reference.
            htgt, hfrag = split_outside_refs(href, "#")
            if not htgt and not hfrag:
                continue
            check_target(htgt, hfrag, n)

    # Links that CROSS a line break. CommonMark lets a label run over a newline
    # and lets whitespace follow the opening parenthesis, so `[long\nlabel](x)`
    # and `[x](\nmissing.md)` both render as clickable links -- and a per-line
    # scan can never see either, so their broken destinations passed clean.
    # `md_links` already admits both shapes; what it never had was a subject
    # spanning more than one physical line.
    #
    # The document is masked LINE BY LINE first, at the same lengths, so every
    # exclusion the per-line pass makes still applies and the offsets still map
    # back to a line. Only matches that actually CONTAIN a newline are reported
    # here; the single-line ones belong to the pass above and reporting them
    # twice would double the finding and the summary count. Ported from the
    # Node twin (solyra#69).
    visible_doc: list[str] = []
    starts: list[int] = []
    at = 0
    for i, line in enumerate(lines):
        starts.append(at)
        at += len(line) + 1
        if i in fenced:
            visible_doc.append(" " * len(line))
            continue
        spans = (code_spans(line) + commented.get(i, [])
                 + wrapped_code.get(i, []))
        visible_doc.append(mask_spans(line, spans))
    joined = "\n".join(visible_doc)
    # Inline content does not cross a paragraph boundary. A blank line ends the
    # paragraph, so a `[` in one and a `](missing.md)` in the next render as
    # literal brackets, not a link -- and scanning the whole document as one
    # string paired them and reported a destination no reader can click.
    # A fence boundary interrupts a paragraph the same way.
    # Masking the blank line is not equivalent: it contributes no characters to
    # mask, so the two paragraphs stay adjacent in `joined` and pair anyway.
    # The scan is therefore windowed to one block at a time, which is what
    # makes the boundary real. Same mechanism as code_span_lines.
    for lo_i, hi_i in _paragraph_blocks(lines, fenced):
        lo = starts[lo_i]
        hi = starts[hi_i] + len(lines[hi_i])
        for mm in md_links(joined, lo, hi):
            if "\n" not in mm.group(0):
                continue
            if is_escaped(joined, mm.start()):
                continue
            tgt = mm.group("btarget")
            frag = mm.group("bfrag")
            if tgt is None:
                tgt, frag = mm.group("target"), mm.group("frag")
            n = bisect.bisect_right(starts, mm.start())
            check_target(tgt, frag, n)

    # And the same for RENDERED-HTML destinations. An anchor whose attributes
    # begin on another physical line -- `<a\n href="missing.md">` -- still
    # renders a clickable link, and the per-line pass above could never see the
    # opening tag and its `href` together, so a missing destination produced no
    # finding at all. `HTML_HREF_RE` is already multiline-capable; what it
    # never had was a subject spanning more than one line.
    #
    # A SEPARATE joined document from the Markdown one. That pass masks a
    # rendered HTML block whole, because Markdown syntax is not parsed inside
    # one -- while an `href` inside that same block is exactly what this
    # scans. Same paragraph windows, because an HTML tag may not span a blank
    # line either. Ported from the Node twin (solyra#69).
    html_block = raw_html_block_lines(lines)
    href_doc: list[str] = []
    for i, line in enumerate(lines):
        if (i in fenced and i not in html_block) or i in href_skip:
            href_doc.append(" " * len(line))
            continue
        href_doc.append(mask_spans(line, code_spans(line) + commented.get(i, [])
                                   + wrapped_code.get(i, [])))
    href_joined = "\n".join(href_doc)
    # Windowed WITHOUT the HTML-block lines as boundaries, unlike every other
    # scan here. `fenced` makes each of them a boundary, so a type-6 block
    # formed no window at all and `<div>` then `<a` then ` href="missing.md">`
    # -- a clickable link a reader follows -- was scanned by neither pass: the
    # per-line one cannot see the tag and its href together, and this one never
    # looked. An HTML block is exactly where an href lives. Nothing unsafe
    # widens with it: every line this pass may not read is already blanked in
    # `href_doc` above, and a blank line still ends both a paragraph and a
    # type-6 block, which is the constraint the windowing exists for. Codex
    # filed it here; the Node twin had the same defect.
    href_bounds = _fence_only | front_matter_lines(lines)
    for lo_i, hi_i in _paragraph_blocks(lines, href_bounds):
        lo = starts[lo_i]
        hi = starts[hi_i] + len(lines[hi_i])
        for mm in HTML_HREF_RE.finditer(href_joined, lo, hi):
            # The single-line ones belong to the pass above; reporting them
            # here too would double the finding and the summary count.
            if "\n" not in mm.group(0):
                continue
            if is_escaped(href_joined, mm.start()):
                continue
            href = mm.group("dq") or mm.group("sq") or mm.group("bare") or ""
            htgt, hfrag = split_outside_refs(href, "#")
            if not htgt and not hfrag:
                continue
            n = bisect.bisect_right(starts, mm.start())
            check_target(htgt, hfrag, n)
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


def _git_unquote(cell: str) -> str:
    """Decode git's C-style quoting of a path, if it used any.

    The readers set `core.quotePath=false`, which covers the non-ASCII case
    that prompted this. A path containing a quote, a backslash or a control
    character is still quoted regardless of that setting, so decoding here
    means neither half is load-bearing on its own. A cell that is not quoted,
    or that does not decode, is returned unchanged -- guessing at a path would
    be worse than comparing the spelling git actually gave.
    """
    if len(cell) < 2 or not (cell[0] == '"' and cell[-1] == '"'):
        return cell
    try:
        return cell[1:-1].encode("latin-1", "strict").decode("unicode_escape") \
            .encode("latin-1", "strict").decode("utf-8", "strict")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return cell


def _touches(status_line: str, paths: list[str]) -> bool:
    """Does this `--name-status` line name one of the declared paths?

    Both sides of a rename count: `R100 old.py new.py` is about the declared
    path whichever end carries it.
    """
    for cell in status_line.split("\t")[1:]:
        cell = _git_unquote(cell.strip())
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


def _add_is_a_pure_rename(commit: str, paths: list[str],
                          cwd: pathlib.Path | None = None) -> bool:
    """Was every declared path this commit touched arrived at by a pure move?

    Only asked about a commit the scoped log already called drift, so the
    unlimited read happens once per suspicious commit rather than once per
    audit. Rename detection needs both sides of the pair, and a cross-directory
    move puts the old one outside the declared path's parent.
    """
    # Same `core.quotePath=false` as the drift log: a C-quoted non-ASCII path
    # would fail the declared-path comparison here too, and this read decides
    # whether a commit is a PURE rename -- getting it wrong drops a real
    # content change off the drift list.
    out = run(["git", "-c", "core.quotePath=false",
               "show", "--format=", "--name-status", "-M", commit],
              cwd=cwd or REPO, ok_exit_codes=(128,))
    touched = [l for l in out.split("\n") if _touches(l, paths)]
    if not touched:
        return False
    for line in touched:
        status = _DRIFT_STATUS_RE.match(line)
        if not status:
            return False
        kind, score = status.group(1), status.group(2)
        if kind != "R" or int(score or 100) < 100:
            return False
    return True


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
    except OSError as exc:
        # A read that could not happen is not a measurement. The main loop
        # read this document a moment ago, so a failure here means it vanished
        # or became unreadable mid-run -- and returning the same empty result
        # as an UNCHANGED document let the audit report clean having never
        # compared the prose against the reviewed revision at all. Exit 2, the
        # status for "the audit could not run", not 0 for "nothing to report".
        raise AuditError(
            f"{doc} could not be read to measure drift since {sha} ({exc}); "
            "the comparison never happened, so no result for it is available"
        ) from exc
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
    # From after the WHOLE H1. A Setext H1 is two lines, and starting at the
    # title stopped immediately on the non-blank underline -- so a document
    # with no blank after `===` compared `Title\n===\nbody` at the recorded SHA
    # against the stamped `Title\n===\n\nbody`, and check_doc_changed_since
    # reported the review stale the moment it was recorded. marker_anchor
    # already knows where the heading ends; this asks it rather than assuming
    # the heading is one line.
    anchor = marker_anchor(lines)
    if anchor is not None:
        j = anchor + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        lines = lines[:anchor + 1] + lines[j:]
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
    # `-c core.quotePath=false`: git C-quotes any path with a non-ASCII byte,
    # so modifying `src/caf\u00e9.py` emits `M\t"src/caf\\303\\251.py"` and
    # `_touches` compared that escaped spelling against the decoded registry
    # path, matched nothing, and reported the document current -- drift
    # silently invisible for every non-ASCII declared path. `git_paths()`
    # already avoids this with `-z`, which `--name-status` cannot use here
    # without changing the record framing this parser depends on.
    out = run(["git", "-c", "core.quotePath=false",
               "log", "--format=%H%x09%s", "--name-status", "-M",
               # T as well: git files a regular-file-to-symlink conversion as a
               # TYPE change, and AMDR dropped the commit before drift_commits
               # could look at it -- so replacing a declared implementation path
               # with a symlink changed the surface and queued no review.
               "--diff-filter=AMDRT", f"{sha}..{base_ref}", "--"] + scopes,
              cwd=cwd or REPO)
    commits = drift_commits(out, code_paths)
    # The directory scope keeps a rename pair intact only while both sides
    # share a parent. A file moved BETWEEN directories, with the registry
    # updated to the new path, leaves the old side outside every scope, so git
    # reports `A new/path.py` and the pure-rename exemption never fires.
    # Re-read only the commits that an ADD put on the list, and only without a
    # path limit: cost scales with the suspicious answer rather than the tree.
    if commits:
        commits = [c for c in commits
                   if not _add_is_a_pure_rename(c.split("\t", 1)[0], code_paths, cwd)]
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
    # ANCHORED, like _REFRESH_GEN_RE. Unanchored, a merged maintenance PR
    # titled `Fix Monthly architecture doc refresh: 2026-09 authentication`
    # entered `deliveries` while _refresh_generation() read no generation from
    # it, so `superseded()` fell back to merge time and could hide a genuinely
    # unmerged refresh. Only the generation regex had been anchored; this is
    # the filter actually passed to fetch_owned_prs.
    "delivery_title_re": re.compile(r"^\s*Monthly architecture doc refresh:\s*\d{4}-\d{2}\s*$",
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
                    delivery_re: re.Pattern | None = None,
                    newest_gen: str | None = None) -> list[dict]:
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

    It stops once a MERGED delivery for `newest_gen` -- the current month, the
    newest generation any refresh can name -- is on hand and every unmerged
    candidate collected so far is superseded by a merge it has seen. The
    generation is what makes the stop sound: without it, a later page can hold
    a NEWER-generation attempt that no delivery seen so far supersedes, because
    pages are ordered by creation time and `superseded` is not. With no
    `newest_gen` the walk does not stop early at all. It is bounded by
    PR_PAGE_LIMIT either way (CLAUDE.md §3.8).
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
        # Stopping early needs a bound on what a LATER page could hold, and
        # the old condition did not have one. It stopped as soon as every
        # unmerged candidate on hand was superseded, reasoning that a later
        # page only adds older-CREATED PRs which the same delivery supersedes
        # too. That reasoning is about time; `superseded` is about GENERATION.
        # A next-generation attempt created BEFORE a later-created
        # older-generation delivery sits on a later page, and nothing seen so
        # far supersedes it -- so the walk stopped and a genuinely open
        # refresh PR was left off the report.
        #
        # `newest_gen` is the bound. No refresh can name a generation after
        # the current month, so once a MERGED delivery for that generation is
        # on hand, every refresh anywhere -- read or unread -- is for it or
        # older, and `superseded` settles all of them. In the healthy case
        # (this month's refresh merged) that is still one request.
        deliveries = [pr for pr in owned
                      if pr["merged"] and delivery_re.search(pr["title"])]
        pending = [pr for pr in owned if not pr["merged"]]
        if (newest_gen
                and any(_refresh_generation(pr["title"]) == newest_gen
                        for pr in deliveries)
                and all(superseded(pr, deliveries) for pr in pending)):
            break
    else:
        # Reaching the cap is NOT the same as reading a short final page, and
        # falling out of the loop treated them alike: every older page was
        # dropped in silence. An omitted merged delivery leaves superseded
        # failures looking actionable; an omitted unsuperseded refresh attempt
        # makes the Class A delivery audit report CLEAN. The second is the
        # direction that matters, and it is the one this whole check exists to
        # prevent. Loud, not short -- the same rule ISSUE_PAGE_GUARD already
        # follows one function over (CLAUDE.md §3.7). Codex filed it three
        # times.
        raise AuditError(
            f"{THIS_REPO}: still reading pull requests after {PR_PAGE_LIMIT} "
            f"pages of {page_size} without a short page or a bounded early "
            "stop; the history is truncated, and a refresh attempt on an "
            "unread page would make the Class A delivery audit report clean")
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
        refuse_symlink(art["doc"])
        doc_name = art["doc"]
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError) as exc:
            # Unreadable, or replaced in the working tree by a directory.
            # Left unguarded this walks past the AuditError handler, so the
            # CLI printed a traceback and exited 1 -- the status it documents
            # for FINDINGS, which makes a run that could not happen look like
            # a run that found something. The registry and per-document reads
            # have carried this guard for rounds. Codex filed it (stocks#1121).
            raise AuditError(f"{doc_name} could not be read ({exc}); its freshness "
                             "was never checked") from exc
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
    # A history made entirely of QUEUED or in-progress non-dry runs is not a
    # dry-run history, so the guard ABOVE is false -- but it is equally no
    # evidence: last_delivering_conclusion() yields None, no run-status finding
    # is produced, and recent stamps let the delivery audit pass without any
    # completed execution behind them. The walk above returns early on a
    # delivering run with a REAL conclusion, so reaching here with none means
    # the history holds none.
    if rows and not any(not _is_dry_run(r) and r[0].strip() for r in rows):
        raise AuditError(
            f"{OWNING_JOB['workflow']}: {len(rows)} runs read and not one is a "
            "completed delivering execution; refusing to report on a history with "
            "no finished run in it")
    return rows


# The WHOLE title, because a delivery is what the workflow emitted verbatim.
# Unanchored, `Fix Monthly architecture doc refresh: 2026-09 authentication`
# read as a delivery, so a repair PR could supersede an unmerged refresh with
# no generated document having landed.
_REFRESH_GEN_RE = re.compile(
    r"^\s*Monthly architecture doc refresh:\s*(\d{4})-(\d{2})\s*$", re.I)


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


def last_delivering_conclusion(rows: list) -> tuple[str, str] | None:
    """The most recent delivering run that has actually FINISHED.

    A queued or in-progress run has an empty conclusion, and accepting that as
    "nothing wrong" meant the completed run beneath it -- the one that failed --
    was never examined, so the delivery audit reported clean while the rerun
    had delivered nothing. An in-flight run is not evidence in either
    direction; the last completed one is what decides.
    """
    for row in rows:
        if not _is_dry_run(row) and row[0]:
            return row[0], row[1]
    return None


def symlinked_component(doc: str) -> str | None:
    """The first component of `doc` that is a symlink, or None.

    EVERY component, not just the last one. `is_symlink()` on the full path
    answers for the final name after the kernel has already resolved each
    parent, so a checkout replacing a tracked DIRECTORY -- `docs/` -> some
    writable path outside the repository -- reported the document as an
    ordinary file and both the read and the write went straight through it.
    Codex filed that as a P1 on the Node twin (solyra#69) after the
    final-component check had been in place for rounds; the hole is that the
    check answered a narrower question than the one being asked.

    Walking components is deliberate over comparing `realpath(parent)` against
    `realpath(REPO)`: the repository root itself is legitimately reached
    through a symlink on some platforms (`/tmp` on macOS, a worktree under a
    linked path), and a root comparison rejects those checkouts wholesale.
    What is being refused is a link INSIDE the tree.
    """
    walked = pathlib.PurePosixPath(doc).parts
    for i in range(1, len(walked) + 1):
        partial = pathlib.PurePosixPath(*walked[:i])
        if (REPO / partial).is_symlink():
            return str(partial)
    return None


def refuse_symlink(doc: str) -> None:
    """Refuse to READ a tracked symlink, before anything opens it.

    Following one audits the target's machine-local bytes as though they were
    committed under this path, so a clean result is one another clone does not
    reproduce -- and a link to a non-terminating special file such as
    `/dev/zero` can hang or exhaust memory, which means a guard placed only in
    the per-document loop is never reached at all. The Class A freshness reads
    happen BEFORE that loop, so they carry the preflight themselves.
    """
    link = symlinked_component(doc)
    if link is not None:
        through = "" if link == doc else f" (through {link})"
        raise AuditError(
            f"{doc} is a tracked symlink{through}, so reading it would audit its "
            "target rather than a document in this repository; the result would "
            "not reproduce in another clone")


def visible_generated_stamps(body_lines: list[str]) -> list[str]:
    """The `Generated <date>` stamps a READER can see, in order.

    A stamp is production evidence, so every syntax that displays its text
    literally has to be excluded or a document that lost its real stamp reads
    as current while showing readers no Generated line at all. Five hiding
    mechanisms, each of which was a finding in its turn: a fence, an indented
    block, a RAW-TEXT HTML block (a rendered `<div>` shows its text, so a
    stamp inside one IS a stamp), an HTML comment, and inline code -- and now
    an HTML ATTRIBUTE value, which renders as nothing at all.

    Named rather than inline so the rule can be exercised on its own: it lives
    inside a function that reaches the GitHub API, and the mask that was added
    last could be removed without a single test noticing.
    """
    skip = (fenced_lines(body_lines) | indented_code_lines(body_lines)
            | raw_html_block_lines(body_lines, raw_text_only=True))
    # Per MATCH against the comment SPANS, not per line: a comment can occupy
    # part of a visible line, so a whole-line rule let a hidden date stand in
    # for a missing stamp.
    hidden = comment_spans(body_lines)
    # Wrapped code spans included, since a span may cross a line break.
    wrapped = code_span_lines(body_lines)
    attrs = tag_attribute_spans(body_lines)
    return [mm.group(1) for i, line in enumerate(body_lines) if i not in skip
            for mm in GENERATED_RE.finditer(line)
            if not any(lo <= mm.start() < hi
                       for lo, hi in (hidden.get(i, []) + code_spans(line)
                                      + wrapped.get(i, []) + attrs.get(i, [])))]


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
                                    delivery_re=OWNING_JOB["delivery_title_re"],
                                    newest_gen=today[:7])
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
    last = last_delivering_conclusion(recent)
    if last and last[0] != "success":
        findings.append({"check": "class-a", "doc": OWNING_JOB["workflow"], "severity": "P1",
                         "detail": f"last delivering run concluded {last[0]} at {last[1]}"})

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
        refuse_symlink(doc)
        doc_name = doc
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError) as exc:
            # Unreadable, or replaced in the working tree by a directory.
            # Left unguarded this walks past the AuditError handler, so the
            # CLI printed a traceback and exited 1 -- the status it documents
            # for FINDINGS, which makes a run that could not happen look like
            # a run that found something. The registry and per-document reads
            # have carried this guard for rounds. Codex filed it (stocks#1121).
            raise AuditError(f"{doc_name} could not be read ({exc}); its freshness "
                             "was never checked") from exc
        # Not from a fenced example or an HTML comment. A scan of the whole
        # document let any `Generated YYYY-MM-DD` in sample output stand in for
        # a missing footer, so removing the real stamp while keeping a recent
        # example passed the freshness check with no production date at all.
        # Narrower than "the declared provenance location", which this module
        # does not model; it removes the non-rendered sources, which is the
        # case reported.
        body_lines = body.split("\n")
        # Indented code as well as fenced. `indented_code_lines` was missing
        # from this filter, so a four-space example carrying a recent
        # `Generated` date stood in for a missing real stamp and the freshness
        # check reported a document current although readers see no production
        # date in it at all -- the same defect as the fenced case, one syntax
        # over. The Node twin masks both wherever it masks either.
        stamps = visible_generated_stamps(body_lines)
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
    # The registry is a tracked document and gets the same refusal they do.
    # This read happens BEFORE the per-document loop, so `refuse_symlink` there
    # is not reached late but not at all: a symlinked DOC_REGISTRY.md supplied
    # machine-local classification and ownership rules for the whole run, and
    # one pointing at a non-terminating special file hangs here. Same shape as
    # the Class A freshness reads, which carry the preflight for the same
    # reason.
    refuse_symlink(REGISTRY)
    try:
        registry_text = reg_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # Unreadable, a directory, or not UTF-8. Left unguarded these walk past
        # the AuditError handler, so the CLI printed a traceback and exited 1 --
        # the status it documents for FINDINGS, which makes a run that could not
        # happen indistinguishable from detected drift.
        raise AuditError(
            f"{REGISTRY} could not be read: {exc}; without it every document is "
            "unclassified, so the audit did not run") from exc
    registry = load_registry(registry_text)

    tracked = set(git_paths(["git", "ls-tree", "-r", base_ref, "--name-only"]))
    TOP_LEVEL_DIRS.update(p.split("/", 1)[0] for p in tracked if "/" in p)
    # Root names as the BASE REF holds them, captured before the staged and
    # deleted adjustments below. That is what makes a bare citation of a root
    # file the working tree no longer has reportable: after the adjustment the
    # name is gone from `tracked`, and the audit would have nothing to compare
    # the citation against.
    base_root_files = {p for p in tracked if "/" not in p}
    # And the suffixes the base ref held, captured here for the same reason:
    # a staged deletion that empties an extension must not make the citations
    # to the deleted file uncheckable.
    base_exts = {pathlib.PurePosixPath(p).suffix for p in tracked
                 if pathlib.PurePosixPath(p).suffix}
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
    staged = set(git_paths(["git", "diff", "--cached", "--name-only",
                            "--diff-filter=A"]))
    # And a DELETION, staged or not, leaves it. Keeping a deleted path in
    # `tracked` let a surviving document link to an asset that is gone and
    # pass, let a deleted declared code path satisfy the registry check, and --
    # when the deleted path was itself a document -- aborted the whole audit on
    # the working-tree read instead.
    deleted = set(git_paths(["git", "diff", "--name-only", "--diff-filter=D",
                             "HEAD"]))
    # A pure RENAME is neither, and `--diff-filter` cannot express it: `git mv
    # docs/old.md docs/new.md` produces one `R100` line that both queries above
    # skip. The old path therefore stayed in the inventory while the new one
    # was absent, so the run opened a document no longer on disk and exited 2 --
    # on precisely the workflow (audit the change before committing it) that
    # staged-addition support exists for. Both sides are consumed here: the
    # source joins the deletions, the destination joins the additions.
    renamed_from: set[str] = set()
    # `--name-status -z` does NOT put a rename on one tab-separated line: it
    # emits three NUL-terminated records, `R100`, then the source, then the
    # destination. Walked as a token stream rather than split per line.
    toks = git_paths(["git", "diff", "--cached", "--name-status",
                      "--diff-filter=R"])
    i = 0
    while i < len(toks):
        status = toks[i]
        if status[:1] in ("R", "C") and i + 2 < len(toks):
            renamed_from.add(toks[i + 1])
            staged.add(toks[i + 2])
            i += 3
        else:
            i += 2
    deleted |= renamed_from
    if staged or deleted:
        tracked = (tracked | staged) - deleted
        # And the directories those additions establish. TOP_LEVEL_DIRS was
        # derived from the base commit only, so a citation of a missing path
        # under a directory this change set CREATES was read as cross-repository
        # prose and skipped -- the pre-commit audit passed although the staged
        # tree is what says the directory belongs to this repository. Not
        # narrowed by `deleted`: a directory the base ref held stays a
        # directory this repository has had, which is what the set is for.
        TOP_LEVEL_DIRS.update(p.split("/", 1)[0] for p in staged if "/" in p)
        docs = document_set(tracked, registry)
    untracked = git_paths(["git", "ls-files", "--others", "--exclude-standard",
                           "--", "*.md"])
    docs = sorted(set(docs) | set(untracked))

    if args.issues_snapshot:
        states = load_issues_snapshot(args.issues_snapshot)
    else:
        states = {THIS_REPO: fetch_issue_states(THIS_REPO), SIBLING_REPO: fetch_issue_states(SIBLING_REPO)}
    if args.write_issues_snapshot:
        write_issues_snapshot(args.write_issues_snapshot, states)

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
        # A tracked SYMLINK is refused before it is read, not only before it is
        # written. Following one audits the target's machine-local bytes as
        # though they were committed under this path, so a clean result is one
        # another clone does not reproduce -- and the read can leave the
        # checkout entirely. write_stamps already refuses them, which made the
        # refusal a property of the COMMAND rather than of the tree: --stamp
        # was guarded and a read-only --check was not. Ported from the Node
        # twin (solyra#69, `bd0126a`).
        # One helper, so the per-document guard and the Class A freshness
        # preflights cannot drift apart about what a refusal says.
        refuse_symlink(doc)
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
                    + check_dead_links(doc, text, tracked, base_root_files, base_exts))
                   if doc.endswith(".md") else [])
        if cls == "A":
            for f in content:
                f["region"] = region_of(f.get("line", 0), owned, prompt)
                f["region_owner"] = region_owner(f["region"], prompt)
        findings += content

        if not stampable:
            continue

        # A line that READS as a marker but parses as neither format, whether or
        # not a valid one exists beside it. Reported either way, because
        # "no review marker" is the wrong answer when the document plainly
        # carries one that this script cannot read.
        findings += check_marker_shape(doc, lines)

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
            findings += check_marker_fields(doc, info, _marker_body(lines, found[0]))
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
            # An AMBIGUOUS classification disables the write. Two equally
            # specific rows disagreeing about what this document is means the
            # audit does not know whether it is hand-written or machine-owned,
            # and taking the first by table order let --stamp rewrite generated
            # content when the `D` row happened to sit above the `A` row. The
            # P1 from check_registry_paths says the registry needs fixing; this
            # says the write waits until it is.
            if classification_is_ambiguous(doc, registry):
                stamp_refusals[doc] = "ambiguous-classification"
                continue
            reviewed = doc in verify
            # A review of prose this audit just DISPROVED is false provenance.
            # `--verify` writes `Depth: verified` and today's date, which says
            # "I read this document and its claims hold" -- so writing it over
            # a dead link, a closed issue cited as live work or a missing
            # Class A stamp is the tool lying about itself, and
            # `--stamp --verify docs/x.md` without `--check` exited 0 having
            # done exactly that. Raised on the Node twin (solyra#69), where
            # `count-claim` joins this set; there is no claims check here.
            #
            # `marker` and `changed-since` are deliberately absent: a missing,
            # stale or drifted marker is precisely what the stamp resolves, so
            # refusing on those would make --verify impossible on the
            # documents that most need it. The findings for this document have
            # all been added by now, so they can be asked about directly.
            # FIRST among the guards, and it applies to a scan-only stamp
            # too. A file using MORE THAN ONE ending cannot be rewritten
            # without choosing one for lines that did not ask: `write_stamp`
            # applies `existing_newline`, which reads the first line only, so
            # every other line would be converted to match it -- a whole-file
            # diff for a one-line stamp. Refused rather than guessed, and
            # recorded per DOCUMENT: a scan-only run skips that file and
            # carries on, while a `--verify` naming it aborts, which is what
            # every other refusal here already does.
            #
            # Before the content guard below, not after, because that one
            # fires on the same file for a MISLEADING reason: `read_text`
            # normalises endings, so a CRLF document never compares equal to
            # its own committed blob and the run reported "its prose differs"
            # about a file nobody had edited. Codex filed the rewrite; the
            # ordering is what makes the message true.
            if has_mixed_newlines(REPO / doc):
                stamp_refusals[doc] = "mixed-line-endings"
                continue
            if reviewed and any(f["doc"] == doc and f["check"] in _DISPROVEN_BY_AUDIT
                                for f in findings):
                stamp_refusals[doc] = "disproven-claim"
                continue
            # A review records "these claims were true against THIS revision".
            # For a document the revision does not contain, that sentence has
            # no meaning -- and the marker it would write is unfalsifiable,
            # because every later drift check finds nothing to diff against.
            # A staged-new document is the case that reaches here; the answer
            # is to commit it and stamp against a revision that holds it.
            if reviewed and not path_in_commit(head, doc):
                stamp_refusals[doc] = "baseline-predates-doc"
                continue
            # And the content at that revision has to BE what was reviewed.
            # The path existing at `head` is not enough: with staged or
            # unstaged prose edits the guard above passes, `head` is recorded
            # as the reviewed baseline, and the moment those edits and the
            # marker are committed, check_doc_changed_since diffs the document
            # at `head` against the newly committed prose and reports
            # `changed-since` -- invalidating the very review that wrote it.
            # Marker lines are excluded on both sides, exactly as that check
            # excludes them, so a restamp is not mistaken for an edit.
            if reviewed and _without_marker(
                    run(["git", "show", f"{head}:{doc}"], ok_exit_codes=(128,))
            ) != _without_marker(text):
                stamp_refusals[doc] = "uncommitted-content"
                continue
            # And the DECLARED CODE PATHS have to be committed too. The
            # document matching `head` is not enough: check_changed_since
            # reads committed history, so a staged or unstaged change under a
            # declared path is invisible to it, `head` is recorded as the
            # reviewed baseline, and the moment that code and the marker are
            # committed the next audit reports drift and invalidates the
            # review that just ran. Same shape as the document guard above,
            # one level out.
            if reviewed and code_paths and run(
                    ["git", "status", "--porcelain", "--"] + list(code_paths),
            ).strip():
                stamp_refusals[doc] = "uncommitted-code"
                continue
            # And the baseline must not PREDATE committed drift. `--since`
            # names an ancestor, so the worktree can be clean and the document
            # identical at that revision while a declared code path has
            # commits in `head..base_ref`. The marker then records a baseline
            # the very next audit reports `changed-since` against, invalidating
            # the review that just wrote it -- the same self-defeating stamp as
            # the two guards above, reached by committed rather than pending
            # work. Runs the same diff check_changed_since runs, so the guard
            # and the check it protects cannot disagree about what drift is.
            if reviewed and head != base_ref and check_changed_since(
                    doc, head, list(code_paths), base_ref):
                stamp_refusals[doc] = "code-drift-since-baseline"
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
            why = {"disproven-claim":
                       "the audit disproved a claim it makes, so a verified stamp "
                       "would record a review of prose that does not hold; fix the "
                       "findings for it first",
                   "baseline-predates-doc":
                       f"the document does not exist at {head}, so the review would "
                       "name a baseline predating it; commit it first",
                   "ambiguous-classification":
                       f"two equally specific {REGISTRY} rows disagree about what it is, "
                       "so the audit cannot tell hand-written content from generated; "
                       "fix the registry rows first",
                   "uncommitted-code":
                       "a declared code path has uncommitted changes, so the review "
                       f"would name {head} as its baseline and the next audit would "
                       "report drift against code that was reviewed; commit it first",
                   "code-drift-since-baseline":
                       f"a declared code path has commits between {head} and {base_ref}, "
                       f"so a review named against {head} would be reported as drifted by "
                       "the next audit; drop --since, or review against the current base",
                   "uncommitted-content":
                       f"its prose differs from {head}, so the review would name a "
                       "baseline that does not hold what was reviewed and the next "
                       "audit would report changed-since; commit the edits first",
                   "mixed-line-endings":
                       "the file uses more than one line ending, so writing a "
                       "one-line stamp would convert every other line to match "
                       "its first and carry a whole-file diff; normalise the "
                       "endings first",
                   "skipped-no-h1": "no H1 to place a marker after",
                   "skipped-legacy-content": "a legacy marker carrying prose that "
                                             "rewriting would delete",
                   "skipped-duplicate-marker": "two review markers in the opening "
                                               "section; rewriting one would leave "
                                               "the other contradicting it"}
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
        write_stamps(writes)

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
