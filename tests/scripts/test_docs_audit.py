"""Invariants for scripts/maintenance/docs_audit.py.

Each test names the defect it prevents, following tests/meta/test_production_writers.py.
Every one was mutation-checked: the defect was reintroduced, the test confirmed
red, then reverted.
"""
from __future__ import annotations

import inspect
import json
import os
import pathlib
import subprocess

import pytest

from scripts.maintenance import docs_audit as m


# ── registry parsing ────────────────────────────────────────────────────────

REGISTRY = """
# Documentation registry

Prose above the registry, including a table that also starts rows with a class
letter:

| Class | Meaning | What the audit does |
|---|---|---|
| **A** | **Machine-owned.** A job regenerates it. | Routes the fix. |
| **C** | **Dated record.** True on its date. | Never rewritten. |

## Registry

| Class | Path glob | Declared code paths |
|---|---|---|
| A | README.md | gcp/deploy.sh |
| B | docs/product/infrastructure/manual/* | |
| C | docs/archive/* | |
| D | docs/product/02-FEATURE-CATALOG.md | lib, platform/api |
| D | docs/models/*.md | lib/strategies |
"""


def test_trailing_glob_star_survives_cell_cleaning():
    """`.strip("`* ")` turns `docs/archive/*` into `docs/archive/`.

    That looks like harmless whitespace cleanup and is not: the glob then
    matches nothing and 182 documents silently fall into "unclassified", which
    reads as "the registry is incomplete" rather than "the parser is broken".
    """
    rows = m.load_registry(REGISTRY)
    globs = [r["glob"] for r in rows]
    assert "docs/archive/*" in globs
    assert "docs/product/infrastructure/manual/*" in globs
    assert m.classify("docs/archive/2026/old.md", rows)[0] == "C"


def test_prose_tables_above_the_registry_are_not_parsed_as_rules():
    """The explainer table's rows also begin with A/B/C/D.

    Parsed as registry rows they register whole English sentences as path
    globs, and because the matcher prefers the longest glob those bogus rules
    outrank real ones.
    """
    rows = m.load_registry(REGISTRY)
    assert all(" " not in r["glob"] or r["glob"].endswith(".md") for r in rows), \
        [r["glob"] for r in rows if " " in r["glob"]]
    assert len(rows) == 5


def test_most_specific_glob_wins():
    """A file rule must beat the directory rule that also covers it."""
    rows = m.load_registry(REGISTRY + "| D | docs/archive/LIVE.md | lib |\n")
    assert m.classify("docs/archive/LIVE.md", rows)[0] == "D"
    assert m.classify("docs/archive/other.md", rows)[0] == "C"


def test_declared_code_paths_are_split_and_cleaned():
    rows = m.load_registry(REGISTRY)
    _, paths, _ = m.classify("docs/product/02-FEATURE-CATALOG.md", rows)
    assert paths == ["lib", "platform/api"]


def test_a_registry_without_the_region_column_still_parses():
    """The fourth column is additive. A three-column row must keep working.

    Both tables above are three columns wide; a parser that indexed cells[3]
    unconditionally would have turned every existing row into an IndexError,
    i.e. a tool that reports zero documents rather than a tool that fails.
    """
    rows = m.load_registry(REGISTRY)
    assert m.classify("README.md", rows) == ("A", ["gcp/deploy.sh"], [])


def test_region_specs_split_on_semicolons_not_commas():
    """Code paths are comma-separated, so regions cannot be.

    `line:^Generated \\d{4}-\\d{2}-\\d{2}` contains no comma, but
    `inventory:*; prose:...` must stay two specs while
    `gcp/deploy.sh, gcp/schema.sql` stays two paths on the same row.
    """
    rows = m.load_registry(
        REGISTRY + "| A | X.md | gcp/deploy.sh, gcp/schema.sql | inventory:*; prose:p.md |\n"
    )
    cls, paths, regions = m.classify("X.md", rows)
    assert (cls, paths, regions) == ("A", ["gcp/deploy.sh", "gcp/schema.sql"],
                                     ["inventory:*", "prose:p.md"])


# ── generated regions (Class A) ─────────────────────────────────────────────

INVENTORY_DOC = """# Title

Prose the refresh never touches.

<!-- inventory:jobs:start -->
| job | schedule |
|---|---|
<!-- inventory:jobs:end -->

Closing prose.
"""


def test_inventory_blocks_are_owned_and_the_prose_around_them_is_not():
    """The whole point: a Class A file is mixed, not uniformly machine-owned.

    05-e-API.md is 160 lines of which 130 are inventory blocks; treating the
    file as owned hid the other 30 from every audit while no job wrote them.
    """
    owned, unmatched, prompt, _, _ = m.owned_lines(INVENTORY_DOC, ["inventory:*"])
    assert unmatched == [] and prompt is None
    assert owned == {5, 6, 7, 8}
    assert m.unowned_spans(INVENTORY_DOC, owned) == [(1, 4), (9, 10)]


def test_a_declared_region_that_matches_nothing_is_a_finding():
    """A renderer that stops emitting its block leaves the registry lying.

    Silently treating the spec as satisfied is the failure this whole module
    exists to catch, one level up: the registry would claim coverage that no
    longer exists and the span would never be audited.
    """
    _, unmatched, _, _, _ = m.owned_lines(INVENTORY_DOC, ["inventory:*", "mark:gone"])
    assert unmatched == ["mark:gone"]
    findings, _, _, _ = m.check_regions("d.md", INVENTORY_DOC, ["inventory:*", "mark:gone"])
    assert any(f["severity"] == "P1" and "matched nothing" in f["detail"] for f in findings)


def test_a_doc_whose_blocks_all_balance_reports_no_orphans():
    _, _, _, orphans, _ = m.owned_lines(INVENTORY_DOC, ["inventory:*"])
    assert orphans == []


def test_an_exhaustive_doc_reports_its_complement_as_a_defect():
    """`exhaustive` is the opposite declaration to a mixed Class A doc.

    A wholly machine-owned file has no legitimate hand-written half, so a line
    outside its regions is content the next regeneration discards with nobody
    able to say what it was.
    """
    doc = "<!-- BEGIN gen -->\nx\n<!-- END gen -->\nA note that will not survive.\n"
    findings, _, _, _ = m.check_regions("owned.md", doc, ["mark:gen", "exhaustive"])
    assert any(f["severity"] == "P1" and "wholly machine-owned" in f["detail"] for f in findings)


def test_a_mixed_doc_without_exhaustive_keeps_its_complement_silent():
    doc = "<!-- BEGIN gen -->\nx\n<!-- END gen -->\nExpected hand-written prose.\n"
    findings, _, _, rm = m.check_regions("mixed.md", doc, ["mark:gen"])
    assert findings == []
    assert rm["unowned_lines"] == 1


def test_prose_spec_claims_the_remainder_so_nothing_reads_as_unowned():
    """05-a/05-c/05-d have a model writing their prose; that IS an owner.

    Without `prose:`, every line Gemini rewrites would be reported as prose
    nobody owns, and the freshness PR would start editing text the next refresh
    overwrites.
    """
    findings, owned, prompt, _ = m.check_regions(
        "05-a.md", INVENTORY_DOC, ["inventory:*", "prose:.github/prompts/architecture.md"])
    assert prompt == ".github/prompts/architecture.md"
    assert not [f for f in findings if "no generated region" in f["detail"]]
    assert m.region_of(1, owned, prompt) == "model-prose"
    assert m.region_of(5, owned, prompt) == "generated"


def test_unowned_lines_route_to_the_document_itself():
    _, owned, prompt, _ = m.check_regions("05-e.md", INVENTORY_DOC, ["inventory:*"])
    assert m.region_of(1, owned, prompt) == "unowned"
    assert m.region_of(6, owned, prompt) == "generated"


def test_the_unowned_complement_is_reported_as_a_map_not_as_defects():
    """A mixed Class A doc's hand-written prose is its expected shape.

    Emitting a P2 per span gave README, INVESTMENT_MODELS_SUMMARY and 05-e ten
    permanent findings that no amount of reviewing could clear, so --check
    could never return 0 and the gate was worthless. The spans still drive
    routing and stamping; they are just not defects.
    """
    findings, _, _, region_map = m.check_regions("05-e.md", INVENTORY_DOC, ["inventory:*"])
    assert findings == []
    assert region_map["unowned_spans"] == [[1, 4], [9, 10]]
    assert region_map["unowned_lines"] == 6
    assert region_map["generated"] == 4


def test_an_unbalanced_inventory_block_is_a_finding_even_when_others_pair_up():
    """One valid pair must not vouch for the rest of the wildcard.

    A renderer that drops a block, or emits a start with no end, leaves a span
    that in a `prose:` file then routes silently as model prose.
    """
    doc = ("<!-- inventory:a:start -->\nx\n<!-- inventory:a:end -->\n"
           "<!-- inventory:b:start -->\ny\n")
    _, _, _, orphans, _ = m.owned_lines(doc, ["inventory:*"])
    assert orphans == ["inventory:b starts at line 4 with no end"]
    findings, _, _, _ = m.check_regions("05-a.md", doc, ["inventory:*"])
    assert any(f["severity"] == "P1" and "unbalanced" in f["detail"] for f in findings)


def test_an_orphan_end_marker_is_a_finding():
    doc = "prose\n<!-- inventory:a:end -->\n<!-- inventory:b:start -->\nz\n<!-- inventory:b:end -->\n"
    _, _, _, orphans, _ = m.owned_lines(doc, ["inventory:*"])
    assert orphans == ["inventory:a ends at line 2 with no start"]


def test_two_review_markers_stop_the_stamp(audit_repo):
    """`find_marker` picks the first and the update path rewrote only that
    line, so `--stamp --verify` returned "updated" and exited successfully
    while leaving a second, contradictory date and SHA in place -- in a
    document the same run had already reported as carrying duplicates. The
    INSERTION path has refused a misplaced marker for rounds on exactly this
    reasoning; the update path had no such check, so the refusal was a
    property of which branch the document took. Codex filed it on the Node
    twin (solyra#69)."""
    two = ("# T\n\n**Last reviewed:** 2026-01-01 · **Depth:** scanned "
           "· **Last scanned:** 2026-01-01\n**Last reviewed:** 2026-02-02 "
           "· **Depth:** scanned · **Last scanned:** 2026-02-02\n\nbody\n")
    text, action = m.stamp(two, "2026-09-18", "scanned", "abc1234", False)
    assert action == "skipped-duplicate-marker"
    assert text == two
    # One marker is still updated, so this refuses a shape rather than
    # switching the update path off.
    one = ("# T\n\n**Last reviewed:** 2026-01-01 · **Depth:** scanned "
           "· **Last scanned:** 2026-01-01\n\nbody\n")
    assert m.stamp(one, "2026-09-18", "scanned", "abc1234", False)[1] == "updated"


def test_a_fragment_written_as_a_character_reference_is_a_fragment(tmp_path, monkeypatch):
    """`&#35;` resolves to `#` when the link is constructed, so
    `[x](README.md&#35;tests)` gives the href `README.md#tests` and the browser
    splits there -- while this looked for a tracked file literally named
    `README.md#tests` and reported a gating dead link against one that exists.
    `split_outside_refs` consumes references as UNITS, deliberately, so it
    cannot see this one."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    (tmp_path / "README.md").write_text("# Target\n\n## Tests\n\nbody\n")
    checks = lambda doc: [f["check"] for f in
                          m.check_dead_links("d.md", doc, {"d.md", "README.md"})]
    assert checks("[x](README.md&#35;tests)\n") == []
    # And the anchor is CHECKED rather than merely skipped.
    assert checks("[x](README.md&#35;gone)\n") == ["dead-anchor"]
    # A BACKSLASH-escaped hash is left alone: whether CommonMark
    # percent-encodes it is a question I have not put to a reference
    # implementation, and an assertion elsewhere says `[x](a\\#b.md)` targets
    # the tracked `a#b.md`. That is why the decode runs in two steps -- the
    # references, the split, then the escapes.
    assert [f["check"] for f in
            m.check_dead_links("d.md", "[x](a\\#b.md)\n", {"d.md", "a#b.md"})] == []


def test_tag_shaped_text_that_is_not_a_tag_stays_in_the_slug():
    """`## A <span ???>B` renders the tag-shaped text LITERALLY and anchors
    `a-span-b`, but a pattern that accepted "anything that is not an angle
    bracket" after the name matched it and recorded `a-b` -- a valid fragment
    link rejected and a nonexistent one accepted. The attribute grammar
    CommonMark specifies is a name plus an optional unquoted, single-quoted or
    double-quoted value. Codex filed it on the Node twin (solyra#69)."""
    assert m.heading_slug("A <span ???>B") == "a-span-b"
    # The real forms are still markup, so this narrows the pattern to the
    # spec rather than switching it off.
    assert m.heading_slug("Hello <em>world</em>") == "hello-world"
    assert m.heading_slug('A <span class="x">B') == "a-b"
    assert m.heading_slug("A <span data-x=1>B") == "a-b"
    assert m.heading_slug("A <br/> B") == "a--b"
    # And an AUTOLINK is still not a tag: it renders as the URL.
    assert m.heading_slug("A <https://example.com> B") == "a-httpsexamplecom-b"


def test_a_tag_in_a_link_destination_or_title_offers_no_anchor():
    """A link's destination and title are metadata: tag-shaped text in either
    renders inside a URL or a `title` attribute, never as an element. The scan
    read it as one and registered `fake`, so a later `[y](#fake)` passed
    against a destination that exists nowhere."""
    assert m.html_anchors(['[x](README.md "<div id=fake>")']) == set()
    assert m.html_anchors(["[x](<div id=fake>)"]) == set()
    # A real tag OUTSIDE a link, and one in the visible LABEL, are both still
    # elements -- the mask covers the metadata and nothing else.
    assert m.html_anchors(["<div id=real>"]) == {"real"}
    assert m.html_anchors(["[<div id=inlabel>](README.md)"]) == {"inlabel"}


def test_a_link_title_is_not_prose_the_blocker_scan_reads(tmp_path, monkeypatch):
    """A title renders as the anchor's `title` attribute -- a tooltip, never a
    followable citation -- so it says nothing about live work. The scan read
    the cue and the URL as ordinary prose and emitted a gating finding once
    that issue closed. The DESTINATION stays visible, because an issue URL
    written there is a link a reader can follow: the same split
    `tag_attribute_spans` makes for `href`, one syntax over."""
    states = {"solyra": {"1": {"state": "closed", "reason": "completed",
                               "kind": "ISSUE"}}}
    url = "https://github.com/TeneikaAskew/solyra/issues/1"
    checks = lambda doc: [f["check"] for f in
                          m.check_closed_issues("d.md", doc, states)]
    assert checks(f'[x](README.md "Still open {url}")\n') == []
    assert checks(f"Blocked by [issue 1]({url})\n") == ["closed-issue"]
    assert checks(f"Still open {url}\n") == ["closed-issue"]


def test_a_heading_suffix_is_stripped_only_when_it_is_a_link():
    """`_balanced_close` answers a narrower question than the one being asked:
    it finds a matching parenthesis, not a link. `## [x](foo bar)` and
    `## [x](foo "unclosed)` both have one, and CommonMark renders each source
    literally -- so the stripper removed a suffix that is VISIBLE text,
    recorded `x`, and rejected a link to the real anchor while accepting a
    `#x` the page does not expose. Codex filed it on the Node twin
    (solyra#69); the same hole was live here."""
    # A destination may not carry whitespace unbracketed, and an unclosed
    # title is not a title -- neither source is a link.
    assert m.heading_slug('[x](foo bar)') == "xfoo-bar"
    assert m.heading_slug('[x](foo "unclosed)') == "xfoo-unclosed"
    # The real shapes are still stripped, so this narrows the rule to what
    # CommonMark accepts rather than switching it off.
    assert m.heading_slug("[x](foo.md)") == "x"
    assert m.heading_slug('[x](foo.md "t")') == "x"
    assert m.heading_slug("Real [x](guide.md)") == "real-x"


def test_a_reference_label_may_carry_an_escaped_bracket():
    """`str.find("]")` stops at an ESCAPED bracket, so `## [Guide][my\\]ref]`
    with a matching `[my\\]ref]: README.md` definition failed to resolve and
    slugged as `guidemyref` while the page exposes `guide`. The label walk
    beside this one already skipped escapes; this second scan did not."""
    labels = frozenset({r"my\]ref"})
    assert m.heading_slug(r"[Guide][my\]ref]", labels) == "guide"
    # An UNDEFINED label is still left as literal text, which is the rule
    # that keeps bracketed prose from being read as a reference.
    assert m.heading_slug(r"[Guide][my\]ref]", frozenset()) == "guidemyref"


def test_a_combining_mark_stays_in_the_slug():
    """An NFD heading -- `Cafe` + U+0301 -- renders as `Café` and GitHub's
    identifier keeps the mark. `\\w` does not match category M, so the slug came
    out `cafe`: the working encoded fragment rejected AND a `#cafe` the page
    does not expose accepted, wrong in both directions at once. Codex filed it
    on the Node twin (solyra#69); the same allowlist was here."""
    # NFD in, NFD out: the mark is KEPT, not folded into a precomposed
    # letter. GitHub does not normalise either, so a `#café` written NFC
    # against an NFD heading genuinely does not navigate -- preserving the
    # spelling is what makes the audit agree with the page.
    assert m.heading_slug("Cafe\u0301") == "cafe\u0301"
    # The precomposed spelling was already right and still is.
    assert m.heading_slug("Caf\u00e9") == "caf\u00e9"
    # Ordinary punctuation is still stripped, so this widens the allowlist by
    # exactly one category rather than loosening it.
    assert m.heading_slug("Dogs & Cats") == "dogs--cats"


def test_a_fragment_is_decoded_the_way_the_link_renders():
    """A Markdown escape and a character reference are both resolved when the
    link is PARSED; percent-decoding is the browser's and comes last. The
    escape pass was missing entirely, so `[x](#foo\\:bar)` -- which reaches
    `id="foo:bar"` -- was reported as a gating dead anchor; and the reference
    pass ran AFTER `unquote`, which is the browser's step happening before the
    parser's. Codex filed the missing escape pass on the Node twin
    (solyra#69); the order is now identical in both."""
    assert m.decode_fragment(r"foo\:bar") == "foo:bar"
    assert m.decode_fragment("a&amp;b") == "a&b"
    assert m.decode_fragment("caf%C3%A9") == "caf\u00e9"
    # A fragment that needs none of the three is unchanged, which is what
    # makes this safe to apply to every fragment rather than guessing.
    assert m.decode_fragment("plain-slug") == "plain-slug"
    assert m.decode_fragment("100%-done") == "100%-done"


def test_a_registry_row_shown_as_an_example_is_not_a_rule():
    """The registry documents its own format, and every way of SHOWING a
    sample row was executed as live configuration: a fenced block, an indented
    sample, a raw-text `<pre>`, and an `Examples` section introduced by a
    Setext heading. That produces a fabricated missing-path finding, or worse,
    a classification silently applied to a real path -- visible explanatory
    prose becoming executable rules. The Node twin (solyra#69) grew these
    exclusions one at a time; this collector had none of them."""
    reg = ("## Registry\n\n| Class | Path |\n|---|---|\n| D | real.md |\n"
           "\n```\n| D | fenced.md |\n```\n"
           "\n    | D | indented.md |\n"
           "\n<pre>\n| D | raw.md |\n</pre>\n"
           "\n<!-- | D | commented.md | -->\n"
           "\nExamples\n--------\n\n| D | setext.md |\n")
    assert [r["glob"] for r in m.load_registry(reg)] == ["real.md"]
    # A RENDERED block is not an example: `<div>` shows a table as a table,
    # so a row there is a declaration like any other. Both directions, so
    # this is not "ignore anything near a tag".
    rendered = ("## Registry\n\n| Class | Path |\n|---|---|\n| D | real.md |\n"
                "\n<div>\n\n| D | live.md |\n\n</div>\n")
    assert [r["glob"] for r in m.load_registry(rendered)] == ["real.md", "live.md"]


def test_a_marker_shaped_example_in_a_raw_html_block_is_not_malformed(audit_repo):
    """`<div>` around `**Last reviewed:** 2026-9-1` SHOWS the shape without
    writing a marker. `find_markers` excludes raw HTML blocks and
    `marker_shaped_lines` did not, so the valid-marker path correctly found
    none while this path counted it: a gating finding, and `stamp()` returning
    `skipped-malformed-marker` -- which meant the document demonstrating a bad
    marker could never be given a good one."""
    lines = ["# T", "", "<div>", "**Last reviewed:** 2026-9-1", "</div>", "", "Body."]
    assert m.marker_shaped_lines(lines) == []
    # Outside the block the same line IS a malformed marker, so the exclusion
    # is about the container rather than about the text.
    assert m.marker_shaped_lines(["# T", "", "**Last reviewed:** 2026-9-1"]) == [2]


def test_a_generated_region_shown_in_a_raw_text_block_is_not_the_region():
    """A Class A document that has LOST its real region but demonstrates the
    pair inside `<pre>` had the EXAMPLE registered as the region: the declared
    region read as matched, the missing-region P1 was suppressed, and the
    sample's own lines routed to the renderer as generated. Fenced and
    indented examples were excluded; raw-text blocks were not."""
    raw = ("# T\n\n<pre>\n<!-- inventory:x:start -->\nsample\n"
           "<!-- inventory:x:end -->\n</pre>\n")
    owned, unmatched, _, _, _ = m.owned_lines(raw, ["inventory:x"])
    assert owned == set()
    assert unmatched == ["inventory:x"]
    # The `mark:` scanner beside it carried the same omission.
    mark = "# T\n\n<pre>\n<!-- BEGIN gen -->\nsample\n<!-- END gen -->\n</pre>\n"
    assert m.owned_lines(mark, ["mark:gen"])[0] == set()
    # And a real pair is still a region.
    real = "# T\n\n<!-- inventory:x:start -->\nr\n<!-- inventory:x:end -->\n"
    assert m.owned_lines(real, ["inventory:x"])[0] == {3, 4, 5}


def test_a_repeated_anchor_attribute_keeps_only_the_first():
    """HTML parsing drops a repeated attribute after its first occurrence, so
    `<div id="real" id="fake">` offers `real` and nothing else. Recording both
    let a link to `#fake` pass the dead-anchor check against a destination the
    page does not have. Codex filed it on the Node twin (solyra#69)."""
    assert m.html_anchors(['<div id="real" id="fake">']) == {"real"}
    assert m.html_anchors(['<a name="real" name="fake">']) == {"real"}
    # Two DIFFERENT tags each keep their own, so the rule is per tag.
    assert m.html_anchors(['<div id="a"><div id="b">']) == {"a", "b"}


def test_a_contraction_negates_a_blocking_cue():
    """`isn't blocking release` says exactly what `is not blocking release`
    says. The negator list held only the spelled-out form, so the contracted
    sentence read as live work and a closed issue produced a P1 whose own
    source line states the opposite. And `not only X but also Y` AFFIRMS X --
    the generic `not` branch read it as a negation and dropped a citation the
    prose calls blocking, which is the direction that HIDES a finding."""
    assert not m.has_blocking_cue("isn't blocking release")
    assert not m.has_blocking_cue("wasn't blocking")
    assert not m.has_blocking_cue("aren't open issues")
    # A curly apostrophe is the same word.
    assert not m.has_blocking_cue("wasn\u2019t blocking")
    # `not only X but also Y` AFFIRMS X. Codex filed a carve-out for this on
    # the Node twin, whose window admits any two words between negator and
    # cue; THIS pattern admits a fixed vocabulary, so `not only ` never
    # reaches a cue and no carve-out is needed. Asserted rather than assumed,
    # because that is the claim -- and a widening of the window here would
    # turn this line red rather than silently reintroducing the defect.
    assert m.has_blocking_cue("is not only blocking release but also deploys")
    assert not m.has_blocking_cue("is not blocking release")
    assert m.has_blocking_cue("is blocking release")
    # The settled-cue reader shares the predicate, so it cannot disagree.
    assert not m.is_settled("it isn't closed")
    assert m.is_settled("not only closed but archived")


def test_an_inline_code_span_does_not_pair_across_a_fenced_block(tmp_path, monkeypatch):
    """A fenced code block interrupts a paragraph exactly as a blank line
    does, so an inline span cannot pair across one. `code_span_lines` windowed
    its scan by paragraph but with NO fence set, so an unmatched backtick above
    a fence paired with one below it and masked everything between -- including
    a live `[x](missing.md)`, which the gating dead-link check then never saw:
    a broken link reported clean. Codex filed it on the Node twin (solyra#69);
    the same hole was live here."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    check = lambda text: [f["check"] for f in
                          m.check_dead_links("d.md", text, {"d.md"})]
    doc = "a ` tick\n```\nfenced\n```\n[x](missing.md) ` tail\n"
    assert check(doc) == ["dead-link"]
    # A TILDE fence and an INDENTED block are code blocks too, and the
    # unmatched delimiter may sit inside one rather than beside it -- the
    # shape Codex named.
    tilde = "~~~\n` sample\n~~~\n[x](missing.md) `\n"
    assert check(tilde) == ["dead-link"]
    indented = "    ` sample\n\n[x](missing.md) `\n"
    assert check(indented) == ["dead-link"]
    # The boundary is real, not "fences disable masking": a span opened and
    # closed on the SAME side of the fence still masks its contents.
    same_side = "a ` tick [x](missing.md) tail `\n```\nfenced\n```\n"
    assert check(same_side) == []


def test_a_comment_opener_shown_as_an_example_hides_nothing(tmp_path, monkeypatch):
    """`` `<!--` `` is inline code and `\\<!--` is an escaped delimiter; neither
    opens a comment. Read as real, either one made the raw-HTML block scan
    treat the rest of the document as commented out -- so the `<pre>` below
    was never recognised, and the link it DISPLAYS became a gating dead-link
    finding for something no reader can click. `comment_spans` and
    `_comment_hidden` have both carried this rule for rounds; this third copy
    did not. Codex filed it on the Node twin (solyra#69)."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    check = lambda text: [f["check"] for f in
                          m.check_dead_links("d.md", text, {"d.md"})]
    assert check("The opener is `<!--`.\n\n<pre>\n[x](missing.md)\n</pre>\n") == []
    assert check("The opener is \\<!-- here.\n\n<pre>\n[x](missing.md)\n</pre>\n") == []
    # A REAL unclosed opener still hides what follows, so the rule has both
    # directions and this is not simply "never believe an opener".
    assert check("Before <!-- opened\n\n<pre>\n[x](missing.md)\n</pre>\n") == []
    # And the link is live when nothing hides it at all.
    assert check("prose\n\n[x](missing.md)\n") == ["dead-link"]


def test_an_escaped_region_delimiter_is_text_not_a_boundary():
    """`\\<!-- BEGIN gen -->` renders literally. It is how a Class A document
    shows its own convention OUTSIDE a code span, and reading the pair as real
    classified every hand-written line between them as generated -- which
    under `exhaustive` suppressed the finding saying regeneration would
    discard that prose. The comment and link scanners have applied the escape
    rule for rounds; these two scanners each carried a copy without it. Codex
    filed it on the Node twin (solyra#69); the same hole was live here."""
    escaped = "# T\n\n\\<!-- BEGIN gen -->\nhand written\n\\<!-- END gen -->\n"
    owned, unmatched, _, _, _ = m.owned_lines(escaped, ["mark:gen"])
    assert owned == set()
    assert unmatched == ["mark:gen"]
    # And the real pair is still a region, so the rule has both directions.
    real = "# T\n\n<!-- BEGIN gen -->\ngenerated\n<!-- END gen -->\n"
    assert m.owned_lines(real, ["mark:gen"])[0] == {3, 4, 5}
    # The inventory scanner beside it carried the same copy.
    inv = ("# T\n\n\\<!-- inventory:x:start -->\nhand written\n"
           "\\<!-- inventory:x:end -->\n")
    owned, _, _, orphans, _ = m.owned_lines(inv, ["inventory:*"])
    assert owned == set()
    assert orphans == []


def test_class_a_doc_with_no_declared_regions_is_a_finding_not_a_free_pass():
    """An empty region cell must not read as "the whole file is generated".

    That is the Rule 3.7 shape: the absence of information becoming a
    permissive default nobody can distinguish from a deliberate one.
    """
    findings, owned, prompt, _ = m.check_regions("d.md", INVENTORY_DOC, [])
    assert owned == set() and prompt is None
    assert findings and "no generated regions declared" in findings[0]["detail"]


def test_line_specs_own_individual_lines():
    """README's badges are five scattered lines, not a block."""
    doc = "# T\n\n![a](https://img.shields.io/badge/x-blue)\n\nProse.\n"
    owned, unmatched, _, _, _ = m.owned_lines(doc, [r"line:img\.shields\.io"])
    assert owned == {3} and unmatched == []


def test_mark_pair_owns_the_calibration_table_only():
    """refresh_calibration_table.py replaces one marked table in 1,247 lines."""
    doc = "# T\n\nProse.\n<!-- BEGIN tbl -->\n| a |\n<!-- END tbl -->\nMore prose.\n"
    owned, unmatched, _, _, _ = m.owned_lines(doc, ["mark:tbl"])
    assert owned == {4, 5, 6} and unmatched == []


def test_a_trailing_newline_does_not_invent_a_line():
    """`split("\\n")` on a newline-terminated file yields a phantom final "".

    Counting it reported README as 65 lines and INVESTMENT_MODELS_SUMMARY as
    1,248 — one more than either file has, which makes every number the audit
    prints untrustworthy.
    """
    assert len(m.doc_lines("a\nb\n")) == 2
    assert len(m.doc_lines("a\nb")) == 2


def test_blank_only_gaps_between_generated_blocks_are_not_reported_as_prose():
    """A blank line between two rendered tables is not undocumented prose."""
    doc = "<!-- inventory:a:start -->\nx\n<!-- inventory:a:end -->\n\n" \
          "<!-- inventory:b:start -->\ny\n<!-- inventory:b:end -->\n"
    owned, _, _, _, _ = m.owned_lines(doc, ["inventory:*"])
    assert m.unowned_spans(doc, owned) == []


# ── the base ref ────────────────────────────────────────────────────────────

def test_base_ref_falls_back_when_origin_main_is_absent():
    """A shallow or detached checkout has no origin/main and must still audit.

    Hard-coding it aborted every documented invocation with exit 2 before
    reading a single document -- the actions/checkout case this module's own
    run() docstring describes. --since did not work around it either, because
    ls-tree, ancestry and drift named the ref separately.

    The resolver is injected rather than shelling out, because the first
    version of this test asserted that `origin/main` resolves -- in the very
    test for behaviour when it does not. It passed locally and turned CI red
    in the one environment the fix was written for.
    """
    assert m.resolve_base_ref(("origin/main", "main", "HEAD"),
                              exists=lambda r: r == "HEAD") == "HEAD"


def test_base_ref_prefers_the_trunk_when_it_is_there():
    assert m.resolve_base_ref(("origin/main", "main", "HEAD"),
                              exists=lambda r: True) == "origin/main"
    assert m.resolve_base_ref(("origin/main", "main", "HEAD"),
                              exists=lambda r: r in {"main", "HEAD"}) == "main"


def test_base_ref_resolution_is_not_hard_coded_to_this_checkout():
    """Whatever this environment has, the real resolver must agree with git."""
    ref = m.resolve_base_ref()
    assert ref in m.BASE_REF_CANDIDATES
    assert m._ref_exists(ref)


def test_no_resolvable_ref_raises_rather_than_guessing():
    """Falling back to a ref is fine; inventing one is the silent fallback."""
    with pytest.raises(m.AuditError, match="nothing to audit against"):
        m.resolve_base_ref(("no-such-ref-a", "no-such-ref-b"))


# ── drift ───────────────────────────────────────────────────────────────────

def test_drift_filter_covers_additions_and_deletions_not_just_edits():
    """A declared path GAINING or LOSING a module is drift.

    `--diff-filter=M` alone queued neither, so a new module under `lib` or a
    deleted one under `platform/api` left the describing document unflagged.
    Renames are asked for and then filtered by SCORE, because git files a
    move-with-an-edit under R and only a pure `R100` is not drift.
    """
    src = inspect.getsource(m.check_changed_since)
    assert "--diff-filter=AMDR" in src
    assert "--diff-filter=M\"" not in src
    # The call carries the declared paths since round 15: the log query is
    # widened to the containing directory so rename PAIRS survive, and
    # drift_commits narrows the answer back.
    assert "drift_commits(out, code_paths)" in src


# ── what gates and what does not ────────────────────────────────────────────

def test_check_gates_on_p1_and_p2_but_not_p3():
    """A gate that can never go green is not a gate.

    Incomplete provenance has to be REPORTED -- otherwise --stamp clears the
    missing-marker finding with nobody having reviewed anything -- but 98
    never-reviewed documents must not hold a build red forever. That is the
    same objection that moved the unowned complement out of `findings`.
    """
    gating = [f for f in [{"severity": "P3"}, {"severity": "P3"}]
              if f["severity"] in {"P1", "P2"}]
    assert gating == []
    src = inspect.getsource(m.main)
    assert 'f["severity"] in {"P1", "P2"}' in src


def test_incomplete_provenance_is_p3_not_p2():
    """It is a worklist item, not a defect blocking a build."""
    src = inspect.getsource(m.main)
    i = src.index("incomplete provenance")
    assert '"severity": "P3"' in src[max(0, i - 400):i]


# ── the registry must name real things ──────────────────────────────────────

def test_a_deleted_registry_named_document_is_reported():
    """An exactly-named Class A artefact that is GONE must be a finding.

    `document_set` is a predicate over files that still exist, so a deleted
    Architecture.drawio simply never appeared -- the audit written to notice
    the loss of a refresh-owned artefact reported nothing.
    """
    rows = m.load_registry(REGISTRY + "| A | Architecture.drawio | gcp/deploy.sh | all |\n")
    out = m.check_registry_paths({"README.md", "gcp/deploy.sh"}, rows)
    assert any(f["doc"] == "Architecture.drawio" and f["severity"] == "P1" for f in out)


def test_a_present_registry_named_document_is_not_reported():
    rows = m.load_registry(REGISTRY + "| A | Architecture.drawio | gcp/deploy.sh | all |\n")
    out = m.check_registry_paths({"README.md", "Architecture.drawio", "gcp/deploy.sh"}, rows)
    assert [f for f in out if f["doc"] == "Architecture.drawio"] == []


def test_a_declared_code_path_that_does_not_exist_is_reported():
    """`git log -- lib/options` exits 0 with empty output.

    So four options documents declared a path that does not exist and could
    never be queued for re-review, no matter what the options code did. A
    vacuous check reads exactly like a passing one.
    """
    rows = m.load_registry(REGISTRY + "| D | docs/opt.md | lib/options |  |\n")
    out = m.check_registry_paths({"docs/opt.md", "lib/options_greeks.py"}, rows)
    assert any("lib/options" in f["detail"] and "never fire" in f["detail"] for f in out)


def test_a_declared_directory_prefix_counts_as_existing():
    """`lib` is a real declaration even though no file is named exactly `lib`."""
    rows = m.load_registry(REGISTRY + "| D | docs/x.md | lib |  |\n")
    out = m.check_registry_paths({"docs/x.md", "lib/indicators.py"}, rows)
    assert [f for f in out if f["doc"] == "docs/x.md"] == []


def test_the_reviewed_revision_prefers_head_over_the_trunk():
    """The audit reads the WORKING TREE, so the revision it reviews is this
    branch's. Stamping origin/main recorded a commit whose contents were never
    read, and enumerating it hid every document the branch adds."""
    assert m.BASE_REF_CANDIDATES[0] == "HEAD"


# ── markers ─────────────────────────────────────────────────────────────────

def test_marker_roundtrips_through_the_parser():
    line = m.render_marker("2026-09-16", "verified", "aa60569", "2026-09-16", "TBD")
    found = m.find_marker(["# T", "", line])
    assert found is not None
    assert found[1] == {"date": "2026-09-16", "depth": "verified", "sha": "aa60569",
                        "scanned": "2026-09-16", "rest": " · **Owner:** TBD",
                        "legacy": False}
    # `rest` is the unmatched tail, carried so check_marker_fields can see a
    # field the parser recognised the name of but could not read. Owner is not
    # one of MARKER_RE's own fields, so a marker carrying it is not malformed.
    assert m.check_marker_fields("d.md", found[1]) == []


def test_a_scan_never_overwrites_an_existing_review_date():
    """The whole point of the marker is to say when someone last CONFIRMED the
    doc. A weekly script that stamps its own pass as "Last reviewed" destroys
    that signal on every run and dresses an unread document as freshly
    checked -- §3.11 ("a doc is a claim, not evidence") with a green badge."""
    text = "# T\n\n**Last reviewed:** 2026-08-31 \u00b7 **Owner:** TBD\n\nBody\n"
    out, _ = m.stamp(text, "2026-09-16", "scanned", "aa60569", reviewed=False)
    assert "**Last reviewed:** 2026-08-31" in out
    assert "**Last scanned:** 2026-09-16" in out


def test_a_real_review_does_move_the_review_date():
    text = "# T\n\n**Last reviewed:** 2026-08-31 \u00b7 **Owner:** TBD\n\nBody\n"
    out, _ = m.stamp(text, "2026-09-16", "verified", "aa60569", reviewed=True)
    assert "**Last reviewed:** 2026-09-16" in out
    assert "**Depth:** verified" in out and "**Against:** `aa60569`" in out


def test_never_reviewed_doc_says_unknown_not_today():
    """Stamping today on a doc nobody has read is a fabricated claim. "unknown"
    is the honest value and is exactly what §3.11 permits."""
    out, action = m.stamp("# T\n\nBody\n", "2026-09-16", "scanned", "aa60569")
    assert action == "inserted"
    assert "**Last reviewed:** unknown" in out
    assert "**Last scanned:** 2026-09-16" in out
    assert "**Depth:**" not in out


def test_existing_bare_last_reviewed_line_still_parses():
    """13 product docs carry the two-field form. Introducing Depth/Against must
    not orphan them."""
    found = m.find_marker(["# T", "", "**Last reviewed:** 2026-08-31 · **Owner:** TBD"])
    assert found is not None and found[1]["date"] == "2026-08-31"
    assert found[1]["depth"] is None


@pytest.mark.parametrize("label", ["Last updated", "Last Updated", "Last refreshed", "Verified"])
def test_legacy_review_labels_are_recognised(label):
    found = m.find_marker(["# T", "", f"**{label}:** 2026-05-01 · more"])
    assert found is not None and found[1]["legacy"] is True


def test_an_indented_marker_example_is_not_the_documents_marker():
    """`line.strip()` before matching threw away the only thing separating a
    marker from an example of one. A sample in the opening section counted as
    the marker, suppressed the real missing-marker finding, and --stamp then
    REPLACED the example with an unindented live marker."""
    lines = ["# T", "", "Example:", "",
             "    **Last reviewed:** 2026-01-01 \u00b7 **Owner:** TBD", "", "body"]
    assert m.find_marker(lines) is None


def test_a_fenced_marker_example_is_not_the_documents_marker():
    lines = ["# T", "", "```",
             "**Last reviewed:** 2026-01-01 \u00b7 **Owner:** TBD", "```", "", "body"]
    assert m.find_marker(lines) is None


def test_a_real_unindented_marker_is_still_found():
    lines = ["# T", "", "**Last reviewed:** 2026-01-01 \u00b7 **Owner:** TBD", "", "body"]
    assert m.find_marker(lines) is not None


def test_fenced_lines_covers_the_fence_and_its_contents():
    assert m.fenced_lines(["a", "```", "x", "```", "b"]) == {1, 2, 3}


def test_generated_footer_is_not_a_review_marker():
    """`Generated <date>` is the refresh job's signature. Treating it as a
    review marker would let a machine stamp stand in for a human review."""
    assert m.find_marker(["# T", "", "**Generated 2026-09-07** from gcp/schema.sql"]) is None


def test_creation_date_stamp_is_not_a_review_marker():
    """Dated records open with `**Date:**`. Bumping one rewrites history."""
    assert m.find_marker(["# T", "", "**Date:** 2026-08-27 · **Owner:** TBD"]) is None


# ── marker placement ────────────────────────────────────────────────────────

def test_marker_goes_after_the_h1_not_at_a_fixed_line():
    """7 of solyra's living docs open with an HTML comment and carry their H1
    on line 9. A literal line-3 insert writes the marker INSIDE the comment,
    where it is both invisible and unparseable."""
    text = "<!-- moved from the other repo\n     second line of comment -->\n\n# Title\n\nBody.\n"
    out, action = m.stamp(text, "2026-09-16", "scanned", "abc1234")
    assert action == "inserted"
    lines = out.split("\n")
    h1 = lines.index("# Title")
    assert lines[h1 + 2].startswith("**Last reviewed:**")
    assert "Last reviewed" not in "\n".join(lines[:h1])


def test_a_later_sections_date_is_not_the_documents_review_marker():
    """RESEARCH_COMPENDIUM.md opens with its real H1, then `# PART A` with its
    own date on line 13. A flat 40-line scan accepted that as the whole
    document's provenance, so Part B was never covered and no marker was ever
    inserted after the real H1.
    """
    doc = ("# Research Compendium\n\nIntro.\n\n"
           "# PART A\n\n**Last reviewed:** 2026-06-05 · **Owner:** TBD\n\nBody.\n")
    assert m.find_marker(doc.split("\n")) is None
    new, action = m.stamp(doc, "2026-09-17", "scanned", "abc1234")
    assert action == "inserted"
    lines = new.split("\n")
    assert lines[2].startswith("**Last reviewed:** unknown")
    assert "**Last reviewed:** 2026-06-05" in new  # Part A's own date survives


def test_a_marker_in_the_documents_own_first_section_is_still_found():
    doc = "# Title\n\n**Last reviewed:** 2026-08-31 · **Owner:** TBD\n\n## Next\n"
    found = m.find_marker(doc.split("\n"))
    assert found is not None and found[1]["date"] == "2026-08-31"


def test_doc_without_an_h1_is_skipped_not_guessed():
    """AGENTS.md is a Lovable-regenerated fence with no H1; writing into it
    would be clobbered and could break the editor sync."""
    out, action = m.stamp("<!-- LOVABLE:BEGIN -->\nrules\n", "2026-09-16", "scanned", "abc1234")
    assert action == "skipped-no-h1"
    assert "Last reviewed" not in out


def test_restamping_an_unchanged_marker_is_a_no_op():
    """A weekly routine that rewrites an identical line produces an empty diff
    on every doc and a PR nobody can review."""
    text = ("# T\n\n" + m.render_marker("unknown", None, None, "2026-09-16", "TBD")
            + "\n\nBody\n")
    out, action = m.stamp(text, "2026-09-16", "scanned", "abc1234")
    assert action == "unchanged" and out == text


def test_existing_owner_is_preserved_when_restamping():
    text = "# T\n\n**Last reviewed:** 2026-01-01 · **Owner:** teneika\n\nBody\n"
    out, _ = m.stamp(text, "2026-09-16", "verified", "abc1234", reviewed=True)
    assert "**Owner:** teneika" in out
    assert "**Last reviewed:** 2026-09-16" in out


def test_stamp_touches_only_the_marker_line():
    body = "# T\n\nParagraph one.\n\n## Section\n\n| a | b |\n"
    out, _ = m.stamp(body, "2026-09-16", "scanned", "abc1234")
    removed = set(body.split("\n")) - set(out.split("\n"))
    assert removed == set()


# ── closed-issue detection ──────────────────────────────────────────────────

STATES = {
    "stocks": {
        861: {"state": "closed", "reason": "completed", "kind": "ISSUE"},
        812: {"state": "open", "reason": "", "kind": "ISSUE"},
        999: {"state": "closed", "reason": "not_planned", "kind": "ISSUE"},
    },
    "solyra": {26: {"state": "closed", "reason": "completed", "kind": "ISSUE"}},
}
U = "https://github.com/TeneikaAskew/{}/issues/{}"


def test_closed_issue_cited_as_blocking_is_flagged():
    """24 such citations existed in this repo's living docs when the check was
    written, incl. the only blocker listed against FEAT-PLAYBOOK-001."""
    line = f"| Blocking issues | [#861]({U.format('stocks', 861)}) |"
    out = m.check_closed_issues("d.md", line, STATES)
    assert len(out) == 1 and out[0]["ref"] == "stocks#861" and out[0]["severity"] == "P1"


def test_open_issue_cited_as_blocking_is_not_flagged():
    line = f"| Blocking issues | [#812]({U.format('stocks', 812)}) |"
    assert m.check_closed_issues("d.md", line, STATES) == []


def test_closed_issue_outside_a_blocking_context_is_not_flagged():
    """A changelog saying "fixed #861" is a true statement, not drift. Without
    the cue gate the check reports every historical reference in the repo."""
    line = f"Fixed in [#861]({U.format('stocks', 861)}) last April."
    assert m.check_closed_issues("d.md", line, STATES) == []


def test_not_planned_closure_is_a_separate_severity():
    """`not_planned` usually means the claim still stands and only the citation
    is wrong -- the opposite remediation from a completed fix."""
    line = f"Blocking: [#999]({U.format('stocks', 999)})"
    out = m.check_closed_issues("d.md", line, STATES)
    assert out[0]["reason"] == "not_planned" and out[0]["severity"] == "P2"


def test_cross_repo_citation_is_resolved_against_the_sibling_repo():
    line = f"Blocking issues: [solyra#26]({U.format('solyra', 26)})"
    out = m.check_closed_issues("d.md", line, STATES)
    assert len(out) == 1 and out[0]["ref"] == "solyra#26"


def test_unresolvable_reference_is_reported_not_silently_passed():
    """Rule 3.7: an unknown number must not read as "fine"."""
    line = f"Blocking: [#4242]({U.format('stocks', 4242)})"
    out = m.check_closed_issues("d.md", line, STATES)
    assert len(out) == 1 and "could not be resolved" in out[0]["detail"]


def test_a_pull_request_cited_as_live_work_is_checked():
    """`/pull/` used to be skipped outright, so a document calling PR #937 the
    open candidate stayed clean after #937 closed -- though the issue-state
    read already carries PR rows and their state."""
    line = "Blocking: [#937](https://github.com/TeneikaAskew/stocks/pull/937)"
    states = {"stocks": {937: {"state": "closed", "reason": "merged"}}}
    out = m.check_closed_issues("d.md", line, states)
    assert len(out) == 1 and "(PR)" in out[0]["detail"], out


def test_ordinary_pull_request_lineage_is_still_ignored():
    """What keeps `fixed in #123` out is the blocking-cue filter, not the URL
    shape -- which is why checking PRs does not flood the report."""
    line = "Fixed in [#861](https://github.com/TeneikaAskew/stocks/pull/861)."
    states = {"stocks": {861: {"state": "closed", "reason": "merged"}}}
    assert m.check_closed_issues("d.md", line, states) == []


# ── owning-job delivery ─────────────────────────────────────────────────────

def test_owning_job_check_flags_an_unmerged_refresh_pr(monkeypatch):
    """PR #1060 sat open and unmerged for 8 days while 05-a/05-c still said
    `Generated 2026-09-07`. A Generated stamp records that a job ran, not that
    its output ever landed, and nothing was watching that gap."""
    def fake_run(cmd, **kw):
        if "runs?per_page=10" in " ".join(cmd):
            return "success\t2026-09-09T13:46:36Z\n"
        return "1060\topen\t\t2026-09-08T15:46:57Z\tMonthly architecture doc refresh: 2026-09\n"
    monkeypatch.setattr(m, "run", fake_run)
    monkeypatch.setattr(m.pathlib.Path, "exists", lambda self: False)
    out = m.check_owning_job("2026-09-16")
    assert any(f["severity"] == "P1" and "#1060" in f["detail"] and "8d" in f["detail"] for f in out)


def test_owning_job_check_flags_a_failed_last_run(monkeypatch):
    def fake_run(cmd, **kw):
        if "runs?per_page=10" in " ".join(cmd):
            return "failure\t2026-09-09T12:41:22Z\n"
        return ""
    monkeypatch.setattr(m, "run", fake_run)
    monkeypatch.setattr(m.pathlib.Path, "exists", lambda self: False)
    out = m.check_owning_job("2026-09-16")
    assert any(f["severity"] == "P1" and "failure" in f["detail"] for f in out)


def test_owning_job_check_is_quiet_when_the_job_delivered(monkeypatch):
    def fake_run(cmd, **kw):
        if "runs?per_page=10" in " ".join(cmd):
            return "success\t2026-09-16T06:00:00Z\n"
        return "1200\tclosed\t2026-09-16T07:00:00Z\t2026-09-16T06:10:00Z\tMonthly architecture doc refresh: 2026-09\n"
    monkeypatch.setattr(m, "run", fake_run)
    monkeypatch.setattr(m.pathlib.Path, "exists", lambda self: False)
    assert m.check_owning_job("2026-09-16") == []


def test_run_returns_empty_for_a_tolerated_non_zero_exit():
    """`git grep` exits 1 for "ran fine, matched nothing". That is a result."""
    assert m.run(["git", "grep", "-lE", "zzz-no-such-string-zzz", "HEAD", "--", "README.md"],
                 ok_exit_codes=(1,)) == ""


def test_run_raises_for_an_exit_code_the_caller_did_not_tolerate():
    """A read that could not happen is never a measurement.

    The boolean `check=False` collapsed exit 1 ("no matches") and exit 128
    ("unable to resolve revision") into the same empty string, and every
    caller read that as zero. The Node twin shipped the same shape and CI
    caught it: actions/checkout's shallow clone has no `origin/main`, so the
    count check reported 0 where the answer was 37 and would have flagged a
    correct document as wrong.
    """
    with pytest.raises(m.AuditError, match="128"):
        m.run(["git", "grep", "-lE", "x", "no-such-ref-zzz", "--", "README.md"],
              ok_exit_codes=(1,))


def test_run_raises_on_any_failure_when_nothing_is_tolerated():
    with pytest.raises(m.AuditError, match="exited 1"):
        m.run(["git", "grep", "-lE", "zzz-no-such-string-zzz", "HEAD", "--", "README.md"])


def test_changed_since_aborts_on_an_unknown_sha_rather_than_reporting_no_drift():
    """Reporting "nothing changed since <sha>" for a SHA git never read is the
    same fabrication as a count of zero. The marker check reports the unknown
    SHA separately, so this path aborts instead of returning [].
    """
    with pytest.raises(m.AuditError):
        m.check_changed_since("d.md", "0000000", ["lib"], "HEAD")


def test_a_failed_refresh_superseded_by_a_later_delivery_is_not_reported(monkeypatch):
    """#963/#1012/#1021 failed, then a later refresh merged. They are history.

    Reporting them forever kept --check red with findings whose only remedy
    would be reviving obsolete PRs.
    """
    prs = "\n".join([
        "1060\tclosed\t2026-09-10T00:00:00Z\t2026-09-08T00:00:00Z\tMonthly architecture doc refresh: 2026-09",
        "1021\tclosed\t\t2026-09-05T00:00:00Z\tFix: Monthly architecture doc refresh failed",
        "963\tclosed\t\t2026-08-20T00:00:00Z\tFix: Monthly architecture doc refresh failed",
    ])
    monkeypatch.setattr(m, "run", lambda cmd, **k: "success\t2026-09-10T00:00:00Z\n"
                        if "runs?" in " ".join(cmd) else prs)
    findings = m.check_owning_job("2026-09-17")
    assert [f for f in findings if "963" in f["detail"] or "1021" in f["detail"]] == []


def test_a_failed_refresh_with_no_later_delivery_is_still_reported(monkeypatch):
    """The supersede rule must not swallow the case the check exists for."""
    prs = "\n".join([
        "1060\topen\t\t2026-09-08T00:00:00Z\tMonthly architecture doc refresh: 2026-09",
        "1021\tclosed\t\t2026-09-05T00:00:00Z\tFix: Monthly architecture doc refresh failed",
    ])
    monkeypatch.setattr(m, "run", lambda cmd, **k: "success\t2026-09-10T00:00:00Z\n"
                        if "runs?" in " ".join(cmd) else prs)
    findings = m.check_owning_job("2026-09-17")
    assert any("1060" in f["detail"] and f["severity"] == "P1" for f in findings)
    assert any("1021" in f["detail"] for f in findings)


def test_registered_non_markdown_artifacts_are_in_the_document_set():
    """The .drawio companions are Class A with `all` ownership.

    A bare `.md` filter dropped them before classification, so the refresh
    could lose one and the audit that exists to notice would not.
    """
    rows = m.load_registry(REGISTRY + "| A | Architecture.drawio | gcp/deploy.sh | all |\n")
    tracked = {"README.md", "Architecture.drawio", "docs/archive/note.png", "src/app.ts"}
    docs = m.document_set(tracked, rows)
    assert "Architecture.drawio" in docs
    assert "README.md" in docs
    # A glob row is a directory rule, not a licence to audit every file under it.
    assert "docs/archive/note.png" not in docs
    assert "src/app.ts" not in docs
    assert m.classify("Architecture.drawio", rows) == ("A", ["gcp/deploy.sh"], ["all"])


def test_unknown_is_not_a_future_review_date():
    """"unknown" > "2026-09-17" lexicographically.

    The unguarded comparison reported every newly stamped, never-reviewed
    document as P1 future-dated -- 77 of them -- so --check could not go green.
    """
    assert m.is_future_date("unknown", "2026-09-17") is False
    assert m.is_future_date("2026-09-18", "2026-09-17") is True
    assert m.is_future_date("2026-09-16", "2026-09-17") is False


def test_an_owning_job_read_failure_aborts_instead_of_becoming_a_finding(monkeypatch):
    """"The docs are stale" and "I never learned whether they are" differ.

    Collapsing them let a default run exit 0 and a --check run exit 1, neither
    of which is the documented exit 2 for an incomplete audit, so a caller
    could not tell a stale document from an audit that never ran.
    """
    def boom(cmd, **k):
        raise m.AuditError("gh: authentication failed")
    monkeypatch.setattr(m, "run", boom)
    with pytest.raises(m.AuditError, match="authentication"):
        m.check_owning_job("2026-09-18")


def test_zero_byte_generated_artifact_has_no_lines():
    """`"".split("\\n")` is `[""]`, one phantom line, which let an `all` region
    claim line 1 of a truncated file and report a successful match."""
    assert m.doc_lines("") == []
    owned, unmatched, _, _, _ = m.owned_lines("", ["all"])
    assert owned == set()
    assert unmatched == ["all"]


def test_every_mark_occurrence_is_validated_not_just_the_first():
    """A duplicate pair left a generated block classed as hand-written prose,
    and refresh_calibration_table rewrites only the first pair, so the stale
    duplicate would persist indefinitely."""
    doc = "<!-- BEGIN t -->\na\n<!-- END t -->\n<!-- BEGIN t -->\nb\n<!-- END t -->\n"
    _, _, _, orphans, _ = m.owned_lines(doc, ["mark:t"])
    assert any("2x BEGIN" in o for o in orphans)


def test_an_unbalanced_mark_pair_is_reported():
    doc = "<!-- BEGIN t -->\na\n"
    _, _, _, orphans, _ = m.owned_lines(doc, ["mark:t"])
    assert any("1 BEGIN and 0 END" in o for o in orphans)


def test_a_prose_owner_that_does_not_exist_owns_nothing():
    """A misspelled or deleted prompt silently claimed the whole complement:
    spans suppressed, stamping disabled, findings routed to an absent owner."""
    owned, unmatched, prompt, _, _ = m.owned_lines(
        "x\n", ["prose:.github/prompts/gone.md"], prompt_exists=lambda p: False)
    assert unmatched == ["prose:.github/prompts/gone.md"]
    assert prompt is None


def test_a_prose_owner_that_exists_still_claims_the_remainder():
    _, unmatched, prompt, _, _ = m.owned_lines(
        "x\n", ["prose:.github/prompts/architecture.md"], prompt_exists=lambda p: True)
    assert unmatched == [] and prompt == ".github/prompts/architecture.md"


def test_a_failed_github_read_aborts_rather_than_reporting_clean():
    """Rule 3.7. An empty issue map would mark every citation resolvable and
    the run would report a clean bill of health on no data at all."""
    with pytest.raises(m.AuditError):
        m.fetch_issue_states.__wrapped__ if hasattr(m.fetch_issue_states, "__wrapped__") else None
        raise m.AuditError("simulated")


def test_empty_issue_response_raises(monkeypatch):
    monkeypatch.setattr(m, "run", lambda *a, **k: "")
    with pytest.raises(m.AuditError):
        m.fetch_issue_states("stocks")


def test_legacy_line_carrying_content_is_never_rewritten():
    """`05-j-GCP_IMPLEMENTATION_STATUS.md` keeps ~900 characters of deployment
    detail after `**Last Updated**:`, and `16-CONSOLIDATION-AUDIT.md` keeps the
    baseline and follow-up PR links. A normalising rewrite deletes that prose
    and looks like a tidy one-line diff."""
    text = ("# T\n\n**Last Updated**: 2026-09-01 (PR #811 deployed: verified by "
            "replaying 2026-08-28; 4,083 passed)\n\nBody\n")
    out, action = m.stamp(text, "2026-09-16", "scanned", "abc1234")
    assert action == "skipped-legacy-content"
    assert out == text
    assert "PR #811 deployed" in out


def test_bare_legacy_line_is_normalised_and_keeps_its_date():
    text = "# T\n\n**Last refreshed:** 2026-05-22\n\nBody\n"
    out, action = m.stamp(text, "2026-09-16", "scanned", "abc1234")
    assert action == "updated"
    assert "**Last reviewed:** 2026-05-22" in out
    assert "**Last scanned:** 2026-09-16" in out


def test_legacy_line_with_only_owner_and_a_period_counts_as_bare():
    assert m.legacy_tail_is_bare(".")
    assert m.legacy_tail_is_bare(" \u00b7 **Owner:** TBD")
    assert not m.legacy_tail_is_bare(" (post the retirement in PR #211)")
    assert not m.legacy_tail_is_bare(" \u00b7 **Merged baseline:** [#931](x)")


def test_unrecognised_marker_fields_survive_a_restamp():
    """09 carries `**Trust status:**` on its marker line, 10 carries
    `**Status:**`, and 13/14 each carry a planning caveat sentence. Rebuilding
    the line from only the fields this script knows about deletes them --
    the same data loss as rewriting a legacy line, on the format we do own."""
    text = ("# T\n\n**Last reviewed:** 2026-09-04 · **Owner:** TBD · "
            "**Trust status:** Production but needs remediation\n\nBody\n")
    out, _ = m.stamp(text, "2026-09-16", "scanned", "abc1234")
    assert "**Trust status:** Production but needs remediation" in out
    assert "**Last reviewed:** 2026-09-04" in out
    assert "**Last scanned:** 2026-09-16" in out


def test_prose_clause_on_a_marker_line_survives():
    text = ("# T\n\n**Last reviewed:** 2026-08-31 · Dates, releases and owners "
            "are **TBD**. Status is planning status.\n\nBody\n")
    out, _ = m.stamp(text, "2026-09-16", "scanned", "abc1234")
    assert "Dates, releases and owners are **TBD**." in out


# ── follow-ups to the Codex findings on 2f14ccf ─────────────────────────────

def _git(cwd, *args) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A throwaway repo on a branch called `work`: no `main`, no `origin/main`."""
    _git(tmp_path, "init", "-q", "-b", "work")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    return tmp_path


def _commit(cwd, msg: str) -> str:
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-q", "-m", msg)
    return _git(cwd, "rev-parse", "--short", "HEAD")


def test_a_marker_sha_the_checkout_lacks_is_reported_not_fatal(repo):
    """Finding 2, the half `resolve_base_ref` did not reach.

    A depth-1 checkout resolves HEAD fine and then aborts on the first marker
    whose `Against:` SHA it does not hold, because `git log <sha>..HEAD` exits
    128 -- measured on 2f14ccf: `fatal: bad revision 'aa60569..HEAD'`, exit 2,
    nothing reported. That SHA is one explicit finding for that document, and
    the drift since it is declared unmeasurable; everything else still runs.
    """
    (repo / "a.md").write_text("# A\n")
    _commit(repo, "one")
    findings, measurable = m.check_marker_sha("d.md", "aa60569", "HEAD", cwd=repo)
    assert measurable is False
    assert len(findings) == 1 and "not in this checkout" in findings[0]["detail"], findings


def test_a_marker_sha_off_the_base_ref_is_the_ordinary_ancestry_finding(repo):
    (repo / "a.md").write_text("# A\n")
    base = _commit(repo, "one")
    _git(repo, "checkout", "-q", "-b", "side")
    (repo / "b.md").write_text("# B\n")
    side = _commit(repo, "two")
    _git(repo, "checkout", "-q", "work")
    findings, measurable = m.check_marker_sha("d.md", side, "work", cwd=repo)
    assert measurable is True
    assert len(findings) == 1 and "not an ancestor of work" in findings[0]["detail"]
    assert m.check_marker_sha("d.md", base, "work", cwd=repo) == ([], True)


def test_drift_counts_added_and_deleted_modules_but_not_pure_renames(repo):
    """Finding 3, driven through git rather than through the source text.

    `test_drift_filter_covers_additions_and_deletions_not_just_edits` pins the
    flag by reading the function's source; this one proves the flag does what
    the finding asked, with `--find-renames` so a pure rename stays excluded
    whatever `diff.renames` is set to on the machine running the audit.
    """
    (repo / "lib").mkdir()
    (repo / "lib" / "a.py").write_text("x = 1\n" * 20)
    reviewed = _commit(repo, "base")
    _git(repo, "mv", "lib/a.py", "lib/b.py")
    _commit(repo, "pure rename")
    assert m.check_changed_since("d.md", reviewed, ["lib"], "HEAD", cwd=repo) == []
    (repo / "lib" / "c.py").write_text("y = 2\n")
    _commit(repo, "add a module")
    (repo / "lib" / "b.py").unlink()
    _commit(repo, "delete a module")
    out = m.check_changed_since("d.md", reviewed, ["lib"], "HEAD", cwd=repo)
    assert len(out) == 1 and out[0]["detail"].startswith("2 content commit(s)"), out


def test_a_whole_inventory_block_dropped_cleanly_is_a_finding_when_it_is_named():
    """Finding 6, the case orphan tracking cannot see.

    A renderer that stops emitting a block removes BOTH markers, so nothing is
    unbalanced and `inventory:*` is satisfied by whatever blocks remain --
    measured on 2f14ccf: 05-e with its `routes` block deleted outright reports
    nothing. `inventory:NAME` declares the blocks a renderer must emit, so the
    registry, not the surviving markers, says what coverage exists.
    """
    doc = "# T\n<!-- inventory:routers:start -->\nx\n<!-- inventory:routers:end -->\n"
    silent, _, _, _ = m.check_regions("05-e.md", doc, ["inventory:*"])
    assert silent == []
    findings, owned, _, _ = m.check_regions(
        "05-e.md", doc, ["inventory:*", "inventory:routers", "inventory:routes"])
    assert owned == {2, 3, 4}
    assert [f["severity"] for f in findings] == ["P1"]
    assert "`inventory:routes` matched nothing" in findings[0]["detail"]


def test_registry_declares_every_inventory_block_the_renderer_emits():
    """The three inventory-backed rows name their blocks, and the names agree
    with what the documents on this tree actually carry: a spec the registry
    forgot would let a dropped block go unnoticed again."""
    rows = m.load_registry((m.REPO / m.REGISTRY).read_text(encoding="utf-8"))
    for doc in ("docs/product/infrastructure/05-a-ARCHITECTURE.md",
                "docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md",
                "docs/product/infrastructure/05-e-API.md"):
        _, _, regions = m.classify(doc, rows)
        named = {r[10:] for r in regions if r.startswith("inventory:") and r != "inventory:*"}
        present = {mm.group("name") for mm in m.INVENTORY_RE.finditer(
            (m.REPO / doc).read_text(encoding="utf-8"))}
        assert named == present, (doc, named ^ present)


# ── follow-ups to the Codex findings on bd730589 and f1c2bf8e ───────────────

def test_a_date_shaped_impossible_day_is_not_a_calendar_date():
    """`2025-02-31` matches MARKER_RE and sorts below today, so a marker could
    record a day that does not exist and pass every check forever."""
    assert m.is_calendar_date("2026-09-18") is True
    assert m.is_calendar_date("2025-02-31") is False
    assert m.is_calendar_date("2026-13-01") is False
    assert m.is_calendar_date("unknown") is False
    # A shortened form round-trips through fromisoformat on 3.11+ but is not
    # the format the marker declares, so it must not pass either.
    assert m.is_calendar_date("2026-9-18") is False


def test_an_impossible_marker_date_is_reported():
    assert m.check_marker_dates("d.md", {"date": "2025-02-31", "scanned": None}) != []
    assert m.check_marker_dates("d.md", {"date": "2026-09-18", "scanned": "2026-09-18"}) == []
    assert m.check_marker_dates("d.md", {"date": "unknown", "scanned": "2026-09-18"}) == []
    bad = m.check_marker_dates("d.md", {"date": "unknown", "scanned": "2026-02-30"})
    assert len(bad) == 1 and "2026-02-30" in bad[0]["detail"], bad


def test_a_future_date_test_never_fires_on_an_impossible_day():
    """The lexicographic compare said `2027-02-31` is in the future, which is
    a true-shaped answer about a day that does not exist. Only real days are
    compared; the impossible one is reported by check_marker_dates instead."""
    assert m.is_future_date("2026-09-19", "2026-09-18") is True
    assert m.is_future_date("2027-02-31", "2026-09-18") is False
    assert m.is_future_date("unknown", "2026-09-18") is False


def test_an_impossible_override_date_aborts_rather_than_being_written():
    """`--date 2026-02-30` would be written into every marker as Last scanned."""
    with pytest.raises(m.AuditError, match="not a calendar day"):
        m.main(["--date", "2026-02-30"])


def test_an_inserted_marker_keeps_a_blank_line_on_both_sides():
    """With the H1 followed straight by body text the marker got a leading
    blank and no trailing one, so Markdown ran the marker and the opening
    sentence together as one paragraph."""
    out, action = m.stamp("# Title\nbody text\n", "2026-09-18", "scanned", "abc1234")
    assert action == "inserted"
    lines = out.split("\n")
    assert lines[0] == "# Title"
    assert lines[1] == ""
    assert lines[2].startswith("**Last reviewed:**")
    assert lines[3] == "", lines
    assert lines[4] == "body text"


def test_the_blank_the_h1_already_has_is_still_reused():
    """The other branch must not gain a second blank line."""
    out, _ = m.stamp("# Title\n\nbody text\n", "2026-09-18", "scanned", "abc1234")
    lines = out.split("\n")
    assert lines[:2] == ["# Title", ""]
    assert lines[2].startswith("**Last reviewed:**")
    assert lines[3] == "" and lines[4] == "body text", lines


# ── end to end: main() against a throwaway tree ─────────────────────────────

E2E_REGISTRY = """
# Documentation registry

## Registry

| Class | Path glob | Declared code paths | Generated regions |
|---|---|---|---|
| D | docs/DOC_REGISTRY.md | | |
| D | docs/*.md | scripts | |
| A | gen/*.md | | inventory:* |
"""


@pytest.fixture
def audit_repo(tmp_path, monkeypatch):
    """A tree main() can audit end to end without touching this checkout.

    The main() wiring -- which findings are appended, which documents are
    stampable, what the plain output prints -- is where several of these
    defects live, and a test that calls the helper directly cannot see it.
    Reverting the fix has to turn a test red THROUGH main(), not beside it.
    """
    _git(tmp_path, "init", "-q", "-b", "work")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "docs").mkdir()
    (tmp_path / "gen").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "tool.py").write_text("x = 1\n")
    (tmp_path / "docs" / "DOC_REGISTRY.md").write_text(E2E_REGISTRY)
    (tmp_path / "issues.json").write_text(
        json.dumps({"stocks": {"1": {"state": "open"}}, "solyra": {"9": {"state": "open"}}}))
    monkeypatch.setattr(m, "REPO", tmp_path)
    monkeypatch.setattr(m, "TOP_LEVEL_DIRS", set())
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _audit(repo, *argv):
    """Run main() over `repo`, offline, and return (exit code, report)."""
    _commit(repo, "tree")
    code = m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
                   "--issues-snapshot", str(repo / "issues.json"), *argv])
    return code


def test_an_impossible_marker_date_is_reported_by_a_whole_run(audit_repo, capsys):
    """Through main(), not beside it: the check has to be wired in."""
    (audit_repo / "docs" / "d.md").write_text(
        "# D\n\n**Last reviewed:** 2025-02-31 · **Last scanned:** 2026-09-18\n")
    _audit(audit_repo)
    report = json.loads(capsys.readouterr().out)
    bad = [f for f in report["findings"]
           if f["check"] == "marker" and "not a real calendar day" in f["detail"]]
    assert len(bad) == 1 and bad[0]["severity"] == "P2", report["findings"]


# ── the CLI contract: bad input is exit 2, never a finding and never silent ──

def test_a_missing_issues_snapshot_is_exit_two_not_a_traceback(tmp_path):
    """Exit 1 is documented as "there are findings"; a snapshot that cannot be
    read is "the audit did not happen". Automation could not tell them apart,
    and --json produced no report at all -- FileNotFoundError escaped past the
    AuditError handler and Python exited 1 with a traceback."""
    with pytest.raises(m.AuditError, match="could not be read"):
        m.load_issues_snapshot(str(tmp_path / "nope.json"))


def test_a_malformed_issues_snapshot_is_exit_two(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json at all")
    with pytest.raises(m.AuditError, match="could not be read"):
        m.load_issues_snapshot(str(bad))


def test_a_structurally_wrong_issues_snapshot_is_exit_two(tmp_path):
    """A JSON file with no `stocks` entry makes every stocks citation read as
    unresolvable -- 24 fabricated findings, not an empty result."""
    half = tmp_path / "half.json"
    half.write_text(json.dumps({"solyra": {"1": {"state": "open"}}}))
    with pytest.raises(m.AuditError, match='no "stocks" entry'):
        m.load_issues_snapshot(str(half))
    nonnumeric = tmp_path / "keys.json"
    nonnumeric.write_text(json.dumps({"stocks": {"abc": {}}, "solyra": {"9": {"state": "open"}}}))
    with pytest.raises(m.AuditError, match="issue number"):
        m.load_issues_snapshot(str(nonnumeric))


def test_a_good_issues_snapshot_still_loads(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"stocks": {"7": {"state": "closed"}}, "solyra": {"9": {"state": "open"}}}))
    assert m.load_issues_snapshot(str(good)) == {"stocks": {7: {"state": "closed"}},
                                                 "solyra": {9: {"state": "open"}}}


def test_a_snapshot_issue_record_must_carry_a_state(tmp_path):
    """The structural check stopped at "the repo entry is an object", so a row
    with no `state` reached `st["state"]` and raised KeyError -- a traceback
    and exit 1, the status reserved for "this documentation has findings".
    A `null` row was worse than that: it reads as `st is None`, which is the
    unresolvable branch, so a malformed snapshot FABRICATES a finding against
    a document that cites a perfectly live issue (CLAUDE.md §3.7)."""
    missing_state = tmp_path / "a.json"
    missing_state.write_text(json.dumps({"stocks": {"1": {}}, "solyra": {"9": {"state": "open"}}}))
    with pytest.raises(m.AuditError, match="stocks#1"):
        m.load_issues_snapshot(str(missing_state))

    null_row = tmp_path / "b.json"
    null_row.write_text(json.dumps({"stocks": {"1": None}, "solyra": {"9": {"state": "open"}}}))
    with pytest.raises(m.AuditError, match="stocks#1"):
        m.load_issues_snapshot(str(null_row))

    non_string = tmp_path / "c.json"
    non_string.write_text(json.dumps({"stocks": {"1": {"state": 7}}, "solyra": {"9": {"state": "open"}}}))
    with pytest.raises(m.AuditError, match="stocks#1"):
        m.load_issues_snapshot(str(non_string))

    listed = tmp_path / "d.json"
    listed.write_text(json.dumps({"stocks": [], "solyra": {"9": {"state": "open"}}}))
    with pytest.raises(m.AuditError, match='no "stocks" entry'):
        m.load_issues_snapshot(str(listed))


def test_a_snapshot_state_must_be_one_the_checks_understand(tmp_path):
    """Requiring a string was not enough. `check_closed_issues` branches only
    on `== "closed"`, so a row reading `bogus` is neither closed nor
    unresolved and the cited blocker DISAPPEARS from the report -- the same
    clean bill of health the row check exists to stop, one value in.

    Reproduced against the string-only validator: a `bogus` row loaded fine
    and a line citing that issue as blocking produced zero findings.
    """
    bogus = tmp_path / "bogus.json"
    bogus.write_text(json.dumps(
        {"stocks": {"8": {"state": "bogus", "reason": "", "kind": "ISSUE"}},
         "solyra": {"9": {"state": "open"}}}))
    with pytest.raises(m.AuditError, match="stocks#8"):
        m.load_issues_snapshot(str(bogus))

    for state in ("open", "closed"):
        good = tmp_path / f"{state}.json"
        good.write_text(json.dumps(
            {"stocks": {"8": {"state": state, "reason": "", "kind": "ISSUE"}},
             "solyra": {"9": {"state": "open"}}}))
        assert m.load_issues_snapshot(str(good))["stocks"][8]["state"] == state


def test_a_document_that_cannot_be_stamped_is_refused_before_any_write(audit_repo):
    """`--stamp` wrote each marker with a bare write_text, so a read-only or
    deleted document raised OSError past the AuditError handler and exited 1 --
    the status reserved for findings. Worse, the writes are sequential, so it
    could stop partway and leave the tree half stamped with nothing saying so.

    Every target is checked before any is written."""
    (audit_repo / "docs" / "d.md").write_text("# D\n\nbody\n")
    (audit_repo / "docs" / "locked.md").write_text("# L\n\nbody\n")
    _commit(audit_repo, "tree")
    before = (audit_repo / "docs" / "d.md").read_text()
    (audit_repo / "docs" / "locked.md").chmod(0o444)
    try:
        if os.access(audit_repo / "docs" / "locked.md", os.W_OK):
            pytest.skip("running as root: mode 444 is still writable, so the "
                        "pre-flight cannot see it")
        with pytest.raises(m.AuditError, match="not writable"):
            m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
                    "--issues-snapshot", str(audit_repo / "issues.json"), "--stamp"])
    finally:
        (audit_repo / "docs" / "locked.md").chmod(0o644)
    # The refusal comes before the writes, so no other document was touched.
    assert (audit_repo / "docs" / "d.md").read_text() == before


def test_the_unwritable_preflight_runs_as_any_user(audit_repo, monkeypatch):
    """The chmod version of this test SKIPS as root, so it runs only in CI --
    and a CI-only test is one I cannot reproduce a failure in locally. That is
    exactly how the --no-owning-job-check regression reached CI green-looking:
    the sibling test never executed here. This drives the same guard through
    main() with os.access stubbed, so it binds on every machine.
    """
    (audit_repo / "docs" / "d.md").write_text("# D\n\nbody\n")
    (audit_repo / "docs" / "locked.md").write_text("# L\n\nbody\n")
    _commit(audit_repo, "tree")
    before = (audit_repo / "docs" / "d.md").read_text()
    real_access = os.access
    monkeypatch.setattr(
        os, "access",
        lambda p, mode, **kw: False if str(p).endswith("locked.md") else real_access(p, mode))
    with pytest.raises(m.AuditError, match="not writable"):
        m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
                "--issues-snapshot", str(audit_repo / "issues.json"), "--stamp"])
    assert (audit_repo / "docs" / "d.md").read_text() == before


def test_a_write_that_fails_mid_stamp_says_what_was_already_written(audit_repo, monkeypatch):
    """The pre-flight narrows the window but cannot close it -- a full disk
    fails mid-loop, and os.access answers for the calling uid, which under
    root calls a mode-444 file writable. So the residual failure is an
    AuditError that states how far it got, never a traceback."""
    (audit_repo / "docs" / "a.md").write_text("# A\n\nbody\n")
    (audit_repo / "docs" / "b.md").write_text("# B\n\nbody\n")
    _commit(audit_repo, "tree")

    # Patched at `write_stamp`, which is where the write now happens: the
    # stamped text is written through it so the document's existing line
    # endings survive, and a Path.write_text patch stopped intercepting
    # anything when that landed.
    real = m.write_stamp
    seen: list[str] = []

    def explode(doc, new):
        seen.append(doc)
        if len(seen) > 1:
            raise OSError(28, "No space left on device")
        return real(doc, new)

    monkeypatch.setattr(m, "write_stamp", explode)
    with pytest.raises(m.AuditError, match="were already stamped"):
        m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
                "--issues-snapshot", str(audit_repo / "issues.json"), "--stamp"])


def test_a_snapshot_that_cannot_be_written_is_exit_two(audit_repo):
    """Reading a bad snapshot is exit 2; failing to WRITE one was exit 1, via
    an OSError escaping the AuditError handler. Same class, same status."""
    (audit_repo / "docs" / "d.md").write_text("# D\n\nbody\n")
    _commit(audit_repo, "tree")
    with pytest.raises(m.AuditError, match="could not be written"):
        m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
                "--issues-snapshot", str(audit_repo / "issues.json"),
                "--write-issues-snapshot", str(audit_repo / "nodir" / "out.json")])


def test_verify_without_stamp_is_refused(audit_repo):
    """A review is recorded by WRITING a marker. `--verify` alone wrote
    nothing and exited 0, so the audit reported success for a human
    verification it never recorded."""
    (audit_repo / "docs" / "d.md").write_text("# D\n\nbody\n")
    with pytest.raises(m.AuditError, match="requires --stamp"):
        _audit(audit_repo, "--verify", "docs/d.md")


def test_a_verify_target_that_was_never_stamped_is_refused(audit_repo):
    """A misspelled path, or one the audit skips, stamped everything else
    scan-only and exited 0 without a word about the review it dropped."""
    (audit_repo / "docs" / "d.md").write_text("# D\n\nbody\n")
    with pytest.raises(m.AuditError, match="docs/typo.md"):
        _audit(audit_repo, "--stamp", "--verify", "docs/typo.md")


def test_a_verify_target_that_is_stamped_is_accepted(audit_repo):
    (audit_repo / "docs" / "d.md").write_text("# D\n\nbody\n")
    assert _audit(audit_repo, "--stamp", "--verify", "./docs/d.md") in (0, 1)
    assert "**Depth:** verified" in (audit_repo / "docs" / "d.md").read_text()


def test_nothing_is_written_when_a_verify_target_is_missing(audit_repo):
    """The refusal has to come before the writes, or half the tree is stamped
    and the run still aborts."""
    (audit_repo / "docs" / "d.md").write_text("# D\n\nbody\n")
    before = (audit_repo / "docs" / "d.md").read_text()
    with pytest.raises(m.AuditError):
        _audit(audit_repo, "--stamp", "--verify", "docs/typo.md")
    assert (audit_repo / "docs" / "d.md").read_text() == before


def test_a_verify_target_stamping_could_not_record_is_refused(audit_repo):
    """`stamp_targets` was filled before `stamp()` ran, so a document whose
    marker cannot be written -- no H1, or a legacy line carrying prose -- still
    consumed the request. `--stamp --verify` then exited 0 having written
    nothing, which is the ignored-verification behaviour the unmatched-target
    check exists to prevent, one layer in."""
    (audit_repo / "docs" / "d.md").write_text("# D\n\nbody\n")
    (audit_repo / "docs" / "noh1.md").write_text("<!-- fenced -->\nrules\n")
    with pytest.raises(m.AuditError, match="no H1"):
        _audit(audit_repo, "--stamp", "--verify", "docs/noh1.md")

    (audit_repo / "docs" / "legacy.md").write_text(
        "# L\n\n**Last updated:** 2026-05-01 by the release script\n\nbody\n")
    with pytest.raises(m.AuditError, match="legacy"):
        _audit(audit_repo, "--stamp", "--verify", "docs/legacy.md")


def test_nothing_is_written_when_a_verify_target_cannot_be_stamped(audit_repo):
    """Same ordering guarantee as the misspelled-path case: the refusal comes
    before the writes, so the rest of the tree is not stamped by a run that
    aborts."""
    (audit_repo / "docs" / "d.md").write_text("# D\n\nbody\n")
    (audit_repo / "docs" / "noh1.md").write_text("<!-- fenced -->\nrules\n")
    before = (audit_repo / "docs" / "d.md").read_text()
    with pytest.raises(m.AuditError):
        _audit(audit_repo, "--stamp", "--verify", "docs/noh1.md")
    assert (audit_repo / "docs" / "d.md").read_text() == before


def test_a_verify_target_already_carrying_the_review_is_accepted(audit_repo):
    """`unchanged` records nothing because the marker is already exactly what
    would be written. Refusing it would fail a re-run of a review that IS on
    disk, so the target counts as consumed."""
    (audit_repo / "docs" / "d.md").write_text("# D\n\nbody\n")
    assert _audit(audit_repo, "--stamp", "--verify", "docs/d.md") in (0, 1)
    first = (audit_repo / "docs" / "d.md").read_text()
    assert "**Depth:** verified" in first
    # Re-run without a new commit, so the head SHA and therefore the rendered
    # marker are identical and `stamp()` returns `unchanged` rather than
    # `updated`. That is the action this test exists to keep accepted.
    assert m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
                   "--issues-snapshot", str(audit_repo / "issues.json"),
                   "--stamp", "--verify", "docs/d.md"]) in (0, 1)
    assert (audit_repo / "docs" / "d.md").read_text() == first


def test_a_class_a_doc_with_no_region_map_is_never_stamped(audit_repo, capsys):
    """`prompt is None` meant "no model owns this prose", so every nonblank
    complement was stampable -- including the machine-owned document whose
    safe writable region could not be established at all. An empty region map
    can put that marker inside content the next regeneration discards."""
    (audit_repo / "gen" / "G.md").write_text("# G\n\ngenerated body\n")
    reg = audit_repo / "docs" / "DOC_REGISTRY.md"
    reg.write_text(reg.read_text().replace("| A | gen/*.md | | inventory:* |",
                                           "| A | gen/*.md | | |"))
    _audit(audit_repo, "--stamp")
    report = json.loads(capsys.readouterr().out)
    assert [s for s in report["stamped"] if s["doc"] == "gen/G.md"] == [], report["stamped"]
    assert "**Last reviewed:**" not in (audit_repo / "gen" / "G.md").read_text()


def test_a_class_a_doc_whose_declared_region_matched_nothing_is_never_stamped(audit_repo, capsys):
    """The invalid-`prose:`-owner branch feeds the same `prompt is None`."""
    (audit_repo / "gen" / "G.md").write_text("# G\n\ngenerated body\n")
    reg = audit_repo / "docs" / "DOC_REGISTRY.md"
    reg.write_text(reg.read_text().replace("| A | gen/*.md | | inventory:* |",
                                           "| A | gen/*.md | | prose:prompts/gone.md |"))
    _audit(audit_repo, "--stamp")
    report = json.loads(capsys.readouterr().out)
    assert any(f["severity"] == "P1" and f["doc"] == "gen/G.md" for f in report["findings"])
    assert [s for s in report["stamped"] if s["doc"] == "gen/G.md"] == [], report["stamped"]
    assert "**Last reviewed:**" not in (audit_repo / "gen" / "G.md").read_text()


def test_a_class_a_doc_with_a_valid_region_map_is_still_stamped(audit_repo, capsys):
    """The guard must not stop the mixed Class A documents this audit exists
    to stamp -- README's hand-written complement is the whole point."""
    (audit_repo / "gen" / "G.md").write_text(
        "# G\n\nhand written prose\n\n<!-- inventory:x:start -->\nrendered\n"
        "<!-- inventory:x:end -->\n")
    _audit(audit_repo, "--stamp")
    report = json.loads(capsys.readouterr().out)
    assert [s["doc"] for s in report["stamped"] if s["doc"] == "gen/G.md"] == ["gen/G.md"]
    assert "**Last reviewed:**" in (audit_repo / "gen" / "G.md").read_text()


def test_a_whole_run_with_an_unreadable_snapshot_is_exit_two(audit_repo):
    """Through main(): the helper existing is not the same as main() using it.

    Reverting the call site alone left the direct helper tests green, which is
    the "asserting around the code rather than through it" failure the earlier
    round on this file recorded.
    """
    (audit_repo / "docs" / "d.md").write_text("# D\n\nbody\n")
    _commit(audit_repo, "tree")
    with pytest.raises(m.AuditError, match="could not be read"):
        m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
                "--issues-snapshot", str(audit_repo / "nope.json")])


# ── what the checks can actually see ────────────────────────────────────────

def test_a_root_relative_backticked_path_is_checked_like_any_other():
    """`./scripts/tool.py` is the same repository path as `scripts/tool.py`.

    The existence check failed, and then `p.split("/", 1)[0]` was `.` rather
    than `scripts`, so the citation was discarded as if it pointed outside
    this repo. CLAUDE.md alone carries 9 backticked `./...` citations.
    """
    m.TOP_LEVEL_DIRS.update({"scripts"})
    out = m.check_dead_links("d.md", "see `./scripts/gone_forever.py`\n", set())
    assert len(out) == 1, out
    # The finding quotes the citation as written, so it can be found in the file.
    assert "./scripts/gone_forever.py" in out[0]["detail"]


def test_a_root_relative_backticked_path_that_exists_is_still_quiet():
    m.TOP_LEVEL_DIRS.update({"scripts"})
    assert m.check_dead_links("d.md", "see `./scripts/here.py`\n", {"scripts/here.py"}) == []


def test_a_genuine_cross_repo_citation_is_still_not_reported():
    """The root filter is what keeps a deliberate solyra citation quiet."""
    m.TOP_LEVEL_DIRS.update({"scripts"})
    assert m.check_dead_links("d.md", "see `src/lib/format.ts`\n", set()) == []


def test_two_complete_blocks_with_the_same_name_are_a_finding():
    """Neither pair is unbalanced, so the second silently replaced the first in
    the region map. `insert_blocks()` refreshes only the first occurrence
    (`count=1`), so the second copy can stay stale indefinitely while the
    audit reports the map as valid.
    """
    doc = ("# T\n<!-- inventory:x:start -->\nfresh\n<!-- inventory:x:end -->\n"
           "prose\n<!-- inventory:x:start -->\nstale\n<!-- inventory:x:end -->\n")
    pairs, unbalanced = m.inventory_blocks(m.doc_lines(doc))
    assert len(unbalanced) == 1 and "second time" in unbalanced[0], unbalanced
    # The pair kept is the FIRST one -- the one the renderer refreshes.
    assert pairs == {"x": (2, 4)}
    findings, owned, _, _ = m.check_regions("t.md", doc, ["inventory:*", "inventory:x"])
    assert [f["severity"] for f in findings] == ["P1"], findings
    assert "second time" in findings[0]["detail"]


def test_one_block_of_each_name_is_still_silent():
    doc = ("# T\n<!-- inventory:x:start -->\na\n<!-- inventory:x:end -->\n"
           "<!-- inventory:y:start -->\nb\n<!-- inventory:y:end -->\n")
    pairs, unbalanced = m.inventory_blocks(m.doc_lines(doc))
    assert unbalanced == [] and pairs == {"x": (2, 4), "y": (5, 7)}


def test_drift_commits_counts_a_move_with_an_edit_but_not_a_pure_move():
    out = ("aaa1111\tmove and edit\n\nR096\tlib/a.py\tlib/b.py\n"
           "bbb2222\tpure move\n\nR100\tlib/c.py\tlib/d.py\n"
           "ccc3333\tordinary edit\n\nM\tlib/e.py\n")
    assert m.drift_commits(out) == ["aaa1111\tmove and edit", "ccc3333\tordinary edit"]


def test_a_rename_with_an_edit_is_drift(repo):
    """Measured on git 2.43.0: a one-line edit during a move files as R096,
    and `--diff-filter=AMD` returned no commit at all, so the documentation
    was never queued for review although the implementation had changed."""
    (repo / "lib").mkdir()
    (repo / "lib" / "a.py").write_text("x = 1\n" * 30)
    reviewed = _commit(repo, "base")
    _git(repo, "mv", "lib/a.py", "lib/b.py")
    (repo / "lib" / "b.py").write_text("x = 1\n" * 30 + "x = 999\n")
    _commit(repo, "move and edit")
    out = m.check_changed_since("d.md", reviewed, ["lib"], "HEAD", cwd=repo)
    assert len(out) == 1 and out[0]["detail"].startswith("1 content commit(s)"), out


# ── the marker a run writes has to be one the parser reads back ────────────

def test_the_marker_sha_is_a_length_the_parser_accepts(monkeypatch):
    """`--short` honours core.abbrev, which can be set below 7.

    `git -c core.abbrev=4 rev-parse --short HEAD` emits four characters, and
    MARKER_RE requires 7-40. A marker written with a shorter id loses BOTH the
    `Against` field and the `Last scanned` field after it to the unmatched
    tail, so a verified review reports as having no reviewed-against SHA and
    its drift check silently stops running.
    """
    seen = {}

    def fake(argv):
        seen["argv"] = argv
        return "0123456789ab\n"

    assert m.resolve_marker_sha(None, "HEAD", runner=fake) == "0123456789ab"
    assert f"--short={m.MARKER_SHA_LEN}" in seen["argv"]
    assert m.MARKER_SHA_LEN >= 7


def test_a_since_value_git_cannot_place_is_refused_before_any_write():
    """`--since not-a-sha` was written straight into `Against:`, where it does
    not match MARKER_RE -- so the review it was asked to record immediately
    read back as having no SHA at all."""
    with pytest.raises(m.AuditError, match="not-a-sha"):
        m.resolve_marker_sha("not-a-sha", "HEAD", runner=lambda argv: "")


def test_a_resolved_sha_the_parser_cannot_read_is_refused():
    """The round trip is the check, not the length arithmetic: whatever git
    returns has to parse back out of a rendered marker."""
    with pytest.raises(m.AuditError, match="not a form the marker parser"):
        m.resolve_marker_sha(None, "HEAD", runner=lambda argv: "zzzz\n")


def test_a_future_last_scanned_date_is_reported():
    """The future check read `info["date"]` only, so a marker claiming a
    mechanical scan in 2099 passed every check and the document reported clean
    provenance for a scan that has not happened."""
    out = m.check_marker_dates("d.md", {"date": "2026-01-01", "scanned": "2099-01-01"},
                               "2026-09-18")
    assert [f["severity"] for f in out] == ["P1"], out
    assert "last-scanned date 2099-01-01 is in the future" in out[0]["detail"]


def test_a_past_last_scanned_date_is_quiet():
    assert m.check_marker_dates("d.md", {"date": "2026-01-01", "scanned": "2026-09-18"},
                                "2026-09-18") == []


def test_a_second_marker_in_the_window_is_reported(audit_repo, capsys):
    """find_marker stopped at the first match, so a second marker carrying a
    different date or SHA sat below it unreported -- and `--stamp` would
    rewrite the first, report success, and leave the contradiction."""
    (audit_repo / "docs" / "d.md").write_text(
        "# D\n\n**Last reviewed:** 2026-09-01 · **Owner:** TBD\n"
        "**Last reviewed:** 2026-01-01 · **Owner:** TBD\n\nbody\n")
    _audit(audit_repo)
    report = json.loads(capsys.readouterr().out)
    dupes = [f for f in report["findings"]
             if f["doc"] == "docs/d.md" and "review markers in the marker window" in f["detail"]]
    assert len(dupes) == 1 and dupes[0]["severity"] == "P2", report["findings"]


def test_a_document_with_two_markers_is_not_stamped(audit_repo, capsys):
    """Rewriting one of two leaves the other, so the run would report success
    for provenance that is still ambiguous."""
    body = ("# D\n\n**Last reviewed:** 2026-09-01 · **Owner:** TBD\n"
            "**Last reviewed:** 2026-01-01 · **Owner:** TBD\n\nbody\n")
    (audit_repo / "docs" / "d.md").write_text(body)
    _audit(audit_repo, "--stamp")
    report = json.loads(capsys.readouterr().out)
    assert [s for s in report["stamped"] if s["doc"] == "docs/d.md"] == [], report["stamped"]
    assert (audit_repo / "docs" / "d.md").read_text() == body


# ── citations the dead-link check could not see ────────────────────────────

def test_a_line_qualified_backticked_path_is_checked():
    """`gcp/database.py:88-102` never matched BACKTICK_PATH_RE at all, because
    the closing backtick had to follow the extension. 1,207 such citations are
    in this tree, so a rename or deletion of any of those files was invisible.
    """
    m.TOP_LEVEL_DIRS.update({"gcp"})
    out = m.check_dead_links("d.md", "see `gcp/gone_forever.py:88-102`\n", set())
    assert len(out) == 1, out
    assert "gcp/gone_forever.py:88-102" in out[0]["detail"]


def test_a_line_qualified_path_that_exists_is_quiet():
    m.TOP_LEVEL_DIRS.update({"scripts"})
    assert m.check_dead_links("d.md", "see `scripts/tool.py:12`\n", {"scripts/tool.py"}) == []


def test_a_parent_relative_backticked_path_resolves_from_the_document():
    """`../../docs/API.md` was left unchanged, checked as `REPO/../../...`,
    then discarded because its first component is `..` and never a tracked
    top-level directory."""
    m.TOP_LEVEL_DIRS.update({"docs"})
    out = m.check_dead_links("docs/product/infrastructure/d.md",
                             "see `../../gone_forever.md`\n", set())
    assert len(out) == 1, out
    assert "../../gone_forever.md" in out[0]["detail"]


def test_a_parent_relative_path_that_exists_is_quiet():
    m.TOP_LEVEL_DIRS.update({"docs"})
    assert m.check_dead_links("docs/product/d.md", "see `../API.md`\n", {"docs/API.md"}) == []


def test_a_citation_that_climbs_above_the_repo_is_not_a_finding():
    """`../../../../README.md` from a doc two levels down leaves the
    repository: deliberate cross-repo prose, not rot."""
    m.TOP_LEVEL_DIRS.update({"docs"})
    assert m.check_dead_links("docs/d.md", "see `../../../../elsewhere.md`\n", set()) == []


# ── the delivery audit, round three ────────────────────────────────────────

def test_ten_dry_runs_cannot_push_the_last_delivery_out_of_view(monkeypatch, tmp_path):
    """A fixed ten-run window plus the dry-run filter is a hole the two open
    together and neither has alone: the workflow permits repeated manual dry
    runs, and ten of them hide the failed scheduled refresh behind them."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    monkeypatch.setattr(m, "OWNING_JOB", {**m.OWNING_JOB, "docs": []})
    page1 = "\n".join(["success\t2026-09-18T06:00:00Z\tworkflow_dispatch\ttrue"] * 10)
    page2 = "failure\t2026-09-16T06:00:00Z\tschedule\t"
    pages = {1: page1, 2: page2}

    def fake(cmd, **kw):
        joined = " ".join(cmd)
        if "runs?per_page" in joined:
            return pages.get(int(joined.split("&page=")[1].split()[0]), "")
        return ""

    monkeypatch.setattr(m, "run", fake)
    out = m.check_owning_job("2026-09-18")
    assert [f for f in out if "failure" in f["detail"]], out


def test_the_run_walk_stops_at_the_first_delivering_run(monkeypatch, tmp_path):
    """Cost scales with the answer: once a non-dry run is in hand there is
    nothing older that can change the verdict."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    monkeypatch.setattr(m, "OWNING_JOB", {**m.OWNING_JOB, "docs": []})
    calls = {"n": 0}

    def fake(cmd, **kw):
        if "runs?per_page" in " ".join(cmd):
            calls["n"] += 1
            return "success\t2026-09-18T06:00:00Z\tschedule\t"
        return ""

    monkeypatch.setattr(m, "run", fake)
    m.check_owning_job("2026-09-18")
    assert calls["n"] == 1


def test_a_repair_pr_does_not_count_as_a_delivery():
    """The broad pattern catches failed ATTEMPTS, which belong on the report.
    It also matches maintenance like "fix architecture doc refresh
    authentication", and computing `delivered` from every merged match let a
    workflow repair supersede a refresh that never delivered a document."""
    assert m.OWNING_JOB["pr_title_re"].search("Fix architecture doc refresh authentication")
    assert not m.OWNING_JOB["delivery_title_re"].search(
        "Fix architecture doc refresh authentication")
    assert m.OWNING_JOB["delivery_title_re"].search(
        "Monthly architecture doc refresh: 2026-09")


def test_a_merged_repair_pr_does_not_supersede_an_open_refresh(monkeypatch, tmp_path):
    """Through check_owning_job, not just against the two regexes: `delivered`
    is computed from merged matches, so a merged workflow REPAIR could hide a
    refresh that never delivered a document."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    monkeypatch.setattr(m, "OWNING_JOB", {**m.OWNING_JOB, "docs": []})
    pages = ["\n".join([
        "1060\topen\t\t2026-09-08T00:00:00Z\tMonthly architecture doc refresh: 2026-09",
        "1059\tclosed\t2026-09-10T00:00:00Z\t2026-09-09T00:00:00Z\t"
        "Fix architecture doc refresh authentication",
    ])]
    monkeypatch.setattr(m, "run", _pr_pages(pages))
    out = m.check_owning_job("2026-09-17")
    assert [f for f in out if "1060" in f["detail"]], out


def test_a_merged_refresh_still_supersedes(monkeypatch, tmp_path):
    """The stricter delivery pattern must not stop a real delivery from
    clearing older attempts."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    monkeypatch.setattr(m, "OWNING_JOB", {**m.OWNING_JOB, "docs": []})
    pages = ["\n".join([
        "1060\topen\t\t2026-09-08T00:00:00Z\tMonthly architecture doc refresh: 2026-09",
        "1059\tclosed\t2026-09-10T00:00:00Z\t2026-09-09T00:00:00Z\t"
        "Monthly architecture doc refresh: 2026-09",
    ])]
    monkeypatch.setattr(m, "run", _pr_pages(pages))
    assert [f for f in m.check_owning_job("2026-09-17") if "1060" in f["detail"]] == []


def test_disagreeing_generated_stamps_are_reported(tmp_path, monkeypatch):
    """05-c carries a stamp in its header AND its footer. max() reads the
    document as current when a partial refresh moved only one, while the other
    visible provenance claim stays stale."""
    out = _owning_doc(tmp_path, monkeypatch,
                      "# G\n\nGenerated 2026-09-15\n\nbody\n\nGenerated 2026-08-01\n")
    assert [f for f in out if "stamps disagree" in f["detail"]], out


def test_agreeing_generated_stamps_are_quiet(tmp_path, monkeypatch):
    out = _owning_doc(tmp_path, monkeypatch,
                      "# G\n\nGenerated 2026-09-15\n\nbody\n\nGenerated 2026-09-15\n")
    assert [f for f in out if f["doc"] == "g.md"] == [], out


def test_a_type_change_is_drift(tmp_path, monkeypatch):
    """git files a regular-file-to-symlink conversion as T, which AMDR dropped
    before drift_commits could look at it. Both halves have to hold: the query
    must ASK for T, and the parser must count it -- testing only the parser
    left the filter free to drop the commit before it ever arrived."""
    assert m.drift_commits("abc1234\tsubject\nT\tlib/x.py\n") == ["abc1234\tsubject"]
    seen = {}
    monkeypatch.setattr(m, "run", lambda cmd, **kw: seen.setdefault("cmd", cmd) and "")
    m.check_changed_since("d.md", "abc1234", ["lib"], "HEAD")
    assert "--diff-filter=AMDRT" in seen["cmd"], seen["cmd"]


# ── a review covers prose, not only the code it describes ──────────────────

def test_a_document_edited_after_its_review_is_drift(tmp_path, monkeypatch):
    """The drift check queried the declared code paths only, so prose rewritten
    after its `Against` SHA kept the old review date -- and a registry row with
    an empty declared-path column could never produce a drift finding at all."""
    _git(tmp_path, "init", "-q", "-b", "work")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "d.md").write_text("# D\n\noriginal prose\n")
    _commit(tmp_path, "one")
    sha = _git(tmp_path, "rev-parse", "HEAD").strip()
    monkeypatch.setattr(m, "REPO", tmp_path)
    assert m.check_doc_changed_since("d.md", sha, "HEAD", cwd=tmp_path) == []
    (tmp_path / "d.md").write_text("# D\n\nrewritten prose\n")
    out = m.check_doc_changed_since("d.md", sha, "HEAD", cwd=tmp_path)
    assert len(out) == 1 and out[0]["check"] == "changed-since", out


def test_a_document_edit_is_reported_by_a_whole_run(audit_repo, capsys):
    """Through main(). Two tests calling check_doc_changed_since directly
    stayed green when its call site was deleted -- the same assert-around-the
    -code failure this file has now recorded three times."""
    (audit_repo / "docs" / "d.md").write_text("# D\n\noriginal prose\n")
    _commit(audit_repo, "one")
    sha = _git(audit_repo, "rev-parse", "--short=12", "HEAD").strip()
    (audit_repo / "docs" / "d.md").write_text(
        "# D\n\n" + m.render_marker("2026-09-01", "verified", sha, "2026-09-18", "TBD")
        + "\n\nrewritten prose\n")
    _audit(audit_repo)
    report = json.loads(capsys.readouterr().out)
    drift = [f for f in report["findings"]
             if f["doc"] == "docs/d.md" and f["check"] == "changed-since"]
    assert len(drift) == 1 and "the document itself changed" in drift[0]["detail"], \
        report["findings"]


def test_a_marker_only_edit_is_not_drift(tmp_path, monkeypatch):
    """The marker line is what --stamp rewrites on every scheduled run.
    Counting it would mark every document stale the moment the weekly scan
    touched it."""
    _git(tmp_path, "init", "-q", "-b", "work")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    before = "# D\n\n" + m.render_marker("2026-01-01", None, None, "2026-01-01", "TBD") + "\n\nprose\n"
    (tmp_path / "d.md").write_text(before)
    _commit(tmp_path, "one")
    sha = _git(tmp_path, "rev-parse", "HEAD").strip()
    monkeypatch.setattr(m, "REPO", tmp_path)
    after = "# D\n\n" + m.render_marker("2026-01-01", None, None, "2026-09-18", "TBD") + "\n\nprose\n"
    (tmp_path / "d.md").write_text(after)
    assert after != before
    assert m.check_doc_changed_since("d.md", sha, "HEAD", cwd=tmp_path) == []


# ── provenance that looks present and is invisible ─────────────────────────

def test_a_malformed_marker_field_is_reported_not_read_as_absent():
    """Every optional group in MARKER_RE declines SILENTLY. `**Against:**
    `zzzz`` does not fail to parse -- it captures nothing and `rest` swallows
    that field and everything after it, so the document reports only the
    non-gating P3 worklist item and `--check` passes while drift detection is
    off for it."""
    line = "**Last reviewed:** 2026-09-16 · **Against:** `zzzz` · **Last scanned:** 2026-09-17"
    found = m.find_marker(["# T", "", line])
    assert found is not None and found[1]["sha"] is None
    out = m.check_marker_fields("d.md", found[1])
    assert len(out) == 1 and out[0]["severity"] == "P2", out
    assert "against" in out[0]["detail"] and "last scanned" in out[0]["detail"]


def test_a_well_formed_marker_reports_no_malformed_fields():
    line = m.render_marker("2026-09-16", "verified", "aa60569abc12", "2026-09-17", "TBD")
    assert m.check_marker_fields("d.md", m.find_marker(["# T", "", line])[1]) == []


def test_a_malformed_marker_field_is_reported_by_a_whole_run(audit_repo, capsys):
    """Through main(), not beside it. Two tests calling check_marker_fields
    directly stayed green when the call site was deleted, which is the
    assert-around-the-code failure this file has hit before."""
    (audit_repo / "docs" / "d.md").write_text(
        "# D\n\n**Last reviewed:** 2026-09-16 · **Against:** `zzzz` · "
        "**Last scanned:** 2026-09-17\n\nbody\n")
    _audit(audit_repo)
    report = json.loads(capsys.readouterr().out)
    bad = [f for f in report["findings"]
           if f["doc"] == "docs/d.md" and "could not be parsed" in f["detail"]]
    assert len(bad) == 1 and bad[0]["severity"] == "P2", report["findings"]


def test_a_marker_inside_a_generated_region_is_never_rewritten(audit_repo, capsys):
    """The proximity guard compares the FIRST generated line with the H1, which
    says nothing about a marker further down inside a block that starts later.
    `stamp` would replace it in place, report a --verify successful, and the
    renderer would discard that provenance on its next run."""
    body = ("# G\n\nhand written prose\n\n<!-- inventory:x:start -->\n"
            "**Last reviewed:** 2026-01-01 · **Owner:** TBD\nrendered\n"
            "<!-- inventory:x:end -->\n")
    (audit_repo / "gen" / "G.md").write_text(body)
    _audit(audit_repo, "--stamp")
    report = json.loads(capsys.readouterr().out)
    assert [s for s in report["stamped"] if s["doc"] == "gen/G.md"] == [], report["stamped"]
    assert (audit_repo / "gen" / "G.md").read_text() == body
    assert [f for f in report["findings"]
            if f["doc"] == "gen/G.md" and "inside a generated region" in f["detail"]]


# ── a cue belongs to a citation, not to a line ─────────────────────────────

def test_a_citation_the_prose_calls_closed_is_not_reported_as_live_work():
    """docs/product/12-PR-ISSUE-TRACEABILITY.md:48 says three stocks records
    "are closed as not planned with the work still open in solyra". The
    line-level cue applied "still open" to every citation on the line and
    reported truthful traceability history as stale documentation."""
    line = ("after the split, [#683](" + U.format("stocks", 683) + ") moved to "
            "[solyra#26](" + U.format("solyra", 26) + "); all stocks records are "
            "closed as not planned with the work still open in solyra.")
    states = {"stocks": {683: {"state": "closed", "reason": "not_planned", "kind": "ISSUE"}},
              "solyra": {26: {"state": "open", "reason": "", "kind": "ISSUE"}}}
    assert m.check_closed_issues("d.md", line, states) == []


def test_a_genuine_blocker_is_still_reported():
    """The suppression is deliberately narrow: only prose that explicitly
    settles a reference silences it, so it can remove a false finding and
    never a true one."""
    line = f"| Blocking issues | [#861]({U.format('stocks', 861)}) |"
    out = m.check_closed_issues("d.md", line, STATES)
    assert len(out) == 1 and out[0]["severity"] == "P1", out


def test_the_clause_splitter_does_not_cut_inside_a_url():
    """Every citation IS a URL full of dots, so splitting the raw line cuts
    each clause inside `github.com` and the prose around the citation -- the
    only thing being asked about -- falls outside it. Measured on the real
    line 48 before this: #683 was still reported while #685 and #868 were
    correctly suppressed, which is the tell that the window was wrong rather
    than the rule."""
    line = ("moved to [solyra#26](https://github.com/TeneikaAskew/solyra/issues/26) "
            "and canonical [#868](https://github.com/TeneikaAskew/stocks/issues/868) "
            "is still open")
    i = line.index("https://github.com/TeneikaAskew/stocks")
    assert "moved to" in m.citation_clause(line, i, i + 50)


def test_the_real_traceability_line_reports_nothing(monkeypatch):
    """The line Codex cited, through the real check rather than a fixture."""
    doc = "docs/product/12-PR-ISSUE-TRACEABILITY.md"
    path = m.REPO / doc
    if not path.exists():
        pytest.skip("not this checkout")
    line = path.read_text(encoding="utf-8").split("\n")[47]
    if "closed as not planned" not in line:
        pytest.skip("the cited line has moved; the unit tests above still pin the rule")
    states = {
        "stocks": {n: {"state": "closed", "reason": "not_planned", "kind": "ISSUE"}
                   for n in (683, 685, 868)},
        "solyra": {n: {"state": "open", "reason": "", "kind": "ISSUE"} for n in (26, 27, 28)},
    }
    assert m.check_closed_issues(doc, line, states) == []


def test_the_clause_is_bounded_by_the_citation_not_the_sentence():
    line = "Blocked by A; [#861](" + U.format("stocks", 861) + ") is still open."
    assert "Blocked by A" not in m.citation_clause(line, line.index("[#861]"), len(line))


# ── the delivery audit answers to its own flag ─────────────────────────────

def test_a_null_conclusion_does_not_shift_the_columns(monkeypatch, tmp_path):
    """A queued or in-progress run has a null conclusion, so its TSV row BEGINS
    with a tab. Stripping the whole response removes that tab from the first
    row and every column shifts left, so the timestamp reads as the conclusion
    and the run is reported as a failure concluding "2026-09-18T..."."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    monkeypatch.setattr(m, "OWNING_JOB", {**m.OWNING_JOB, "docs": []})
    runs = "\t2026-09-18T06:00:00Z\tschedule\t\nsuccess\t2026-09-17T06:00:00Z\tschedule\t\n"
    monkeypatch.setattr(m, "run", _pr_pages([""], runs=runs))
    out = m.check_owning_job("2026-09-18")
    assert [f for f in out if "2026-09-18T06:00:00Z" in f["detail"]] == [], out


def test_the_owning_job_check_is_not_disabled_by_the_issues_snapshot(audit_repo):
    """Keying the Class A delivery audit off an unrelated flag meant an offline
    issue run reported Class A clean however badly the refresh was failing."""
    (audit_repo / "docs" / "d.md").write_text("# D\n\nbody\n")
    _commit(audit_repo, "tree")
    calls = []
    real = m.run

    def fake_run(cmd, **kw):
        joined = " ".join(cmd)
        calls.append(joined)
        # Let the local git reads through; only the GitHub calls are faked, so
        # the run reaches the delivery audit instead of aborting before it.
        if cmd[0] == "git":
            return real(cmd, **kw)
        return ""

    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(m, "run", fake_run)
        try:
            # Deliberately WITHOUT --no-owning-job-check: the point of this
            # test is that --issues-snapshot alone no longer suppresses the
            # delivery audit. `run` is faked, so no network is touched.
            m.main(["--json", "--date", "2026-09-18",
                    "--issues-snapshot", str(audit_repo / "issues.json")])
        except Exception:
            pass
    assert any("actions/workflows" in c for c in calls), calls[-5:]


def test_the_owning_job_check_can_still_be_turned_off(audit_repo):
    """It needs the GitHub API, so an offline run has to be able to skip it --
    just not as a side effect of an unrelated flag."""
    (audit_repo / "docs" / "d.md").write_text("# D\n\nbody\n")
    _commit(audit_repo, "tree")
    calls = []
    real = m.run

    def fake_run(cmd, **kw):
        calls.append(" ".join(cmd))
        return real(cmd, **kw) if cmd[0] == "git" else ""

    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(m, "run", fake_run)
        m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
                "--issues-snapshot", str(audit_repo / "issues.json")])
    assert not [c for c in calls if "actions/workflows" in c], calls


# ── anchors, and the links that pointed at headings nobody has ─────────────

def test_github_anchor_rule_does_not_collapse_separator_runs():
    """The order is the whole point: GitHub strips punctuation, THEN replaces
    each space with a hyphen. Runs are not collapsed, so an em dash and a
    slash leave DOUBLED hyphens. Collapsing whitespace here would reproduce
    the broken links' spelling and call all 16 of them valid."""
    assert m.heading_slug("FEAT-AUTH-001 — Auth / security (8 open)") == \
        "feat-auth-001--auth--security-8-open"
    assert m.heading_slug("Data Sources & Inputs") == "data-sources--inputs"
    assert m.heading_slug("`code` and **bold**") == "code-and-bold"


def test_repeated_headings_are_numbered_as_github_numbers_them():
    out = m.heading_anchors("# Notes\n\n## Notes\n\n## Notes\n")
    assert out == {"notes", "notes-1", "notes-2"}


def test_numbering_does_not_collide_with_a_naturally_suffixed_heading():
    """A per-base counter emits `notes-1` twice and never `notes-2`, which is
    what GitHub gives the third heading -- so a valid link to it reads as dead.
    A false finding, which is worse than a missed one."""
    assert m.heading_anchors("## Notes\n## Notes-1\n## Notes\n") == {
        "notes", "notes-1", "notes-2"}


def test_a_link_to_a_heading_that_does_not_exist_is_reported(tmp_path, monkeypatch):
    """The fragment was stripped before the target was checked, so a link to a
    real file and a nonexistent heading always passed. 35 such links are in
    this tree, including all 16 feature links in 02-FEATURE-CATALOG.md."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    (tmp_path / "t.md").write_text("# T\n\n## FEAT-AUTH-001 — Auth / security (8 open)\n")
    tracked = {"d.md", "t.md"}
    out = m.check_dead_links(
        "d.md", "see [x](t.md#feat-auth-001-auth-security-8-open)\n", tracked)
    assert len(out) == 1 and out[0]["check"] == "dead-anchor", out


def test_a_link_to_a_heading_that_exists_is_quiet(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "REPO", tmp_path)
    (tmp_path / "t.md").write_text("# T\n\n## FEAT-AUTH-001 — Auth / security (8 open)\n")
    out = m.check_dead_links(
        "d.md", "see [x](t.md#feat-auth-001--auth--security-8-open)\n", {"d.md", "t.md"})
    assert out == [], out


def test_a_same_document_fragment_is_still_checked(tmp_path, monkeypatch):
    """`[x](#heading)` has no path to resolve, which is why it used to be
    skipped outright -- but the anchor is still checkable."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    (tmp_path / "d.md").write_text("# D\n\n## Real Heading\n\nsee [x](#nope)\n")
    out = m.check_dead_links("d.md", (tmp_path / "d.md").read_text(), {"d.md"})
    assert len(out) == 1 and out[0]["check"] == "dead-anchor", out


def test_a_dead_file_does_not_also_report_a_dead_anchor(tmp_path, monkeypatch):
    """One finding per broken link. A missing file cannot have a heading, and
    reporting both would double-count every dead link that carries one."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    out = m.check_dead_links("d.md", "see [x](gone.md#anything)\n", {"d.md"})
    assert len(out) == 1 and out[0]["check"] == "dead-link", out


def test_a_parent_relative_link_is_normalised_before_the_tracked_check(tmp_path, monkeypatch):
    """PurePosixPath keeps `..` segments verbatim; the old code leaned on the
    filesystem to resolve them, which requiring a tracked target removed.
    Measured on this tree: without normalisation, 3,259 live links reported as
    dead -- `.github/workflows/README.md` linking `../../docs/...` resolved to
    `.github/workflows/../../docs/...`, which is in no tracked set."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    tracked = {"a/b/d.md", "docs/API.md"}
    assert m.check_dead_links("a/b/d.md", "see [x](../../docs/API.md)\n", tracked) == []
    out = m.check_dead_links("a/b/d.md", "see [x](../../docs/GONE.md)\n", tracked)
    assert len(out) == 1 and out[0]["check"] == "dead-link", out


def test_a_link_climbing_out_of_the_repo_is_not_a_finding(tmp_path, monkeypatch):
    """Cross-repo prose this repository cannot resolve, and must not call rot.
    Matches the boundary the backticked-path branch already draws."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    assert m.check_dead_links("d.md", "see [x](../../../elsewhere.md)\n", {"d.md"}) == []


def test_an_untracked_file_does_not_satisfy_a_link(tmp_path, monkeypatch):
    """An ignored or generated file, or one recreated after a staged deletion,
    exists locally and is absent for everyone who clones."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    (tmp_path / "built.md").write_text("# B\n")
    out = m.check_dead_links("d.md", "see [x](built.md)\n", {"d.md"})
    assert len(out) == 1 and out[0]["check"] == "dead-link", out


def test_a_directory_target_still_resolves(tmp_path, monkeypatch):
    """git tracks no directories, which is the only reason the filesystem
    check was reachable for links at all."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    assert m.check_dead_links("d.md", "see [x](lib/)\n", {"d.md", "lib/a.py"}) == []


# ── the owning job, and what its success does not prove ────────────────────

def _pr_pages(pages, runs="success\t2026-09-16T06:00:00Z\tschedule\t\n"):
    """A fake `run` serving one PR page per call, then the workflow-runs read."""
    calls = {"n": 0}

    def fake_run(cmd, **kw):
        joined = " ".join(cmd)
        if "runs?per_page=10" in joined:
            return runs
        calls["n"] += 1
        return pages[calls["n"] - 1] if calls["n"] <= len(pages) else ""
    fake_run.calls = calls
    return fake_run


def test_the_refresh_pr_lookup_reads_past_the_first_page(monkeypatch):
    """A single `per_page=100` page covers the 100 newest PRs of ANY kind.

    Measured on this repo on 2026-09-18: page 1 reaches #1130 down to #959, a
    15-day window, and the refresh PR that actually delivered (#953, merged
    2026-09-02) is on page 2 -- invisible to the single-page lookup, so the
    supersede rule saw no delivery at all.
    """
    page1 = "\n".join(
        [f"{n}\tclosed\t2026-09-1{n % 10}T00:00:00Z\t"
         f"2026-09-1{n % 10}T00:00:00Z\tfix: unrelated {n}"
         for n in range(1130, 1030, -1)])
    page2 = "\n".join([
        "1021\tclosed\t\t2026-09-07T13:07:48Z\tFix: Monthly architecture doc refresh failed",
        "953\tclosed\t2026-09-02T22:27:07Z\t2026-09-01T06:24:17Z\t"
        "Monthly architecture doc refresh: 2026-09",
    ])
    monkeypatch.setattr(m, "run", _pr_pages([page1, page2]))
    monkeypatch.setattr(m.pathlib.Path, "exists", lambda self: False)
    out = m.check_owning_job("2026-09-17")
    assert any("1021" in f["detail"] for f in out), out


def _filler(lo, hi, created="2026-09-01T00:00:00Z"):
    return [f"{n}\tclosed\t\t{created}\tfix: filler {n}" for n in range(lo, hi)]


def test_the_pr_lookup_stops_once_every_pending_refresh_is_superseded(monkeypatch):
    """Cost scales with the answer (CLAUDE.md §3.8), but the stop rule is
    "every pending candidate is already superseded", not "a merge exists".

    Here the open refresh was CREATED before the merge that delivered, so the
    supersede rule skips it and no later page can change that: a later page
    holds only older-created PRs, which the same merge supersedes too."""
    pages = ["\n".join([
        "1060\topen\t\t2026-09-01T00:00:00Z\tMonthly architecture doc refresh: 2026-09",
        "953\tclosed\t2026-09-10T22:27:07Z\t2026-08-28T06:24:17Z\t"
        "Monthly architecture doc refresh: 2026-09",
    ] + _filler(900, 998))]
    fake = _pr_pages(pages)
    monkeypatch.setattr(m, "run", fake)
    monkeypatch.setattr(m.pathlib.Path, "exists", lambda self: False)
    m.check_owning_job("2026-09-17")
    assert fake.calls["n"] == 1


def test_the_pr_lookup_reads_on_while_a_pending_refresh_postdates_every_merge(monkeypatch):
    """The walk must not stop while an unsuperseded refresh is still pending.

    Page 1 holds #1060 (open, `refresh: 2026-09`, created 09-08) and #953
    (`refresh: 2026-09`, merged 09-02) -- which does NOT supersede it, because
    a September refresh opened AFTER a September refresh merged is a
    re-attempt. So the walk reads on.

    What #900 on page 2 does NOT do is supersede it either, and that changed in
    round 13: it is `refresh: 2026-08`, and an August delivery cannot establish
    that September's documents landed, however late it merged. Before that this
    case asserted #1060 was silenced, on a pure creation-versus-merge
    comparison -- and the round-13 generation fix kept it green for the WRONG
    reason, because delivered_gen was a max over ALL deliveries and #953 put
    2026-09 into it. Making supersession per-delivery is what exposed that.
    """
    pages = ["\n".join([
        "1060\topen\t\t2026-09-08T15:46:57Z\tMonthly architecture doc refresh: 2026-09",
        "953\tclosed\t2026-09-02T22:27:07Z\t2026-09-01T06:24:17Z\t"
        "Monthly architecture doc refresh: 2026-09",
    ] + _filler(1000, 1098)),
        "900\tclosed\t2026-09-20T00:00:00Z\t2026-08-01T00:00:00Z\t"
        "Monthly architecture doc refresh: 2026-08"]
    fake = _pr_pages(pages)
    monkeypatch.setattr(m, "run", fake)
    monkeypatch.setattr(m.pathlib.Path, "exists", lambda self: False)
    out = m.check_owning_job("2026-09-21")
    assert fake.calls["n"] == 2, "stopped while an unsuperseded refresh was pending"
    assert [f for f in out if "1060" in f["detail"]], out


def _owning_doc(tmp_path, monkeypatch, body):
    """check_owning_job over a single throwaway owned document."""
    (tmp_path / "g.md").write_text(body)
    monkeypatch.setattr(m, "REPO", tmp_path)
    monkeypatch.setattr(m, "OWNING_JOB", {**m.OWNING_JOB, "docs": ["g.md"]})
    monkeypatch.setattr(m, "run", _pr_pages([
        "1060\tclosed\t2026-09-10T00:00:00Z\t2026-09-01T00:00:00Z\t"
        "Monthly architecture doc refresh: 2026-09"]))
    return m.check_owning_job("2026-09-17")


def test_an_owned_document_with_no_generated_stamp_is_reported(tmp_path, monkeypatch):
    """`if not stamps: continue` is a clean run produced by missing evidence.

    For 05-a, 05-c and 05-d the stamp is not a separately declared generated
    region, so a refresh that dropped it leaves a green workflow, a merged PR,
    and a document carrying nothing about when it was produced. All four owned
    docs carry a stamp today, so this changes no current finding.
    """
    out = _owning_doc(tmp_path, monkeypatch, "# G\n\nno stamp here\n")
    assert [f["detail"] for f in out if "no `Generated <date>` stamp" in f["detail"]], out


def test_an_impossible_generated_date_is_a_finding_not_a_traceback(tmp_path, monkeypatch):
    """`fromisoformat("2026-02-31")` raised straight past the AuditError
    handler, so documentation corruption exited 1 with a traceback -- the
    status that means "the docs have findings" -- instead of being one."""
    out = _owning_doc(tmp_path, monkeypatch, "# G\n\nGenerated 2026-02-31\n")
    assert [f for f in out if "not a real calendar day" in f["detail"]], out


def test_a_future_generated_date_cannot_pass_forever(tmp_path, monkeypatch):
    """A future stamp yields a negative age, which is under every staleness
    threshold permanently: the one value that can never go stale."""
    out = _owning_doc(tmp_path, monkeypatch, "# G\n\nGenerated 2099-01-01\n")
    assert [f for f in out if "in the future" in f["detail"]], out


def test_a_current_generated_date_is_quiet(tmp_path, monkeypatch):
    out = _owning_doc(tmp_path, monkeypatch, "# G\n\nGenerated 2026-09-15\n")
    assert [f for f in out if f["doc"] == "g.md"] == [], out


def test_a_dry_run_is_not_evidence_that_the_refresh_delivered(monkeypatch, tmp_path):
    """refresh-architecture-docs.yml declares a `dry_run` input and skips its
    "Open refresh PR" step for it, so a successful manual dry run opens no PR
    and delivers nothing. Reading only the most recent run let one erase a
    failed scheduled refresh from the report until the 40-day stamp threshold
    fired."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    monkeypatch.setattr(m, "OWNING_JOB", {**m.OWNING_JOB, "docs": []})
    runs = ("success\t2026-09-17T06:00:00Z\tworkflow_dispatch\ttrue\n"
            "failure\t2026-09-16T06:00:00Z\tschedule\t\n")
    monkeypatch.setattr(m, "run", _pr_pages([""], runs=runs))
    out = m.check_owning_job("2026-09-17")
    assert [f for f in out if "failure" in f["detail"]], out


def test_a_real_run_after_a_dry_one_still_clears_it(monkeypatch, tmp_path):
    """The guard must not make a genuine recovery invisible."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    monkeypatch.setattr(m, "OWNING_JOB", {**m.OWNING_JOB, "docs": []})
    runs = ("success\t2026-09-17T06:00:00Z\tschedule\t\n"
            "failure\t2026-09-16T06:00:00Z\tschedule\t\n")
    monkeypatch.setattr(m, "run", _pr_pages([""], runs=runs))
    assert [f for f in m.check_owning_job("2026-09-17") if "failure" in f["detail"]] == []


def test_dry_run_false_is_a_delivering_run():
    """`inputs` carries STRINGS, so "false" is a real value and must not read
    as truthy."""
    assert m._is_dry_run(["success", "t", "workflow_dispatch", "false"]) is False
    assert m._is_dry_run(["success", "t", "workflow_dispatch", "true"]) is True
    assert m._is_dry_run(["success", "t", "schedule", ""]) is False
    # A row from a read that predates the column is treated as delivering,
    # which can only keep a failure on the report.
    assert m._is_dry_run(["success", "t"]) is False


def test_the_issue_walk_has_no_silent_ceiling(monkeypatch):
    """`range(1, 40)` stopped at 3,900 combined issues and PRs and said
    nothing, so every older cited blocker past that point would read as
    "could not be resolved" -- fabricated findings from a silent cap."""
    pages = {}
    for i in range(1, 45):
        pages[i] = "\n".join(
            f"{i * 100 + k}\topen\t\tISSUE" for k in range(m.ISSUE_PAGE_SIZE))
    pages[45] = "1\topen\t\tISSUE"

    def fake(cmd, **kw):
        page = int(cmd[2].rsplit("&page=", 1)[1])
        return pages.get(page, "")

    monkeypatch.setattr(m, "run", fake)
    states = m.fetch_issue_states("stocks")
    assert len(states) > 4000, len(states)


def test_the_issue_walk_refuses_rather_than_truncating(monkeypatch):
    """A guard that fires means the assumption behind it is wrong, so the
    result cannot be trusted: exit 2, never a short answer."""
    monkeypatch.setattr(m, "ISSUE_PAGE_GUARD", 3)
    monkeypatch.setattr(m, "run", lambda cmd, **kw: "\n".join(
        f"{k}\topen\t\tISSUE" for k in range(m.ISSUE_PAGE_SIZE)))
    with pytest.raises(m.AuditError, match="truncated read"):
        m.fetch_issue_states("stocks")


def test_a_short_page_ends_the_pr_lookup(monkeypatch):
    """A page holding fewer than 100 rows is the last page; asking for the
    next one is a request that cannot return anything."""
    fake = _pr_pages(["1060\topen\t\t2026-09-08T15:46:57Z\t"
                      "Monthly architecture doc refresh: 2026-09"])
    monkeypatch.setattr(m, "run", fake)
    monkeypatch.setattr(m.pathlib.Path, "exists", lambda self: False)
    out = m.check_owning_job("2026-09-17")
    assert fake.calls["n"] == 1
    assert any("1060" in f["detail"] for f in out), out


CAL_REGION = ("<!-- BEGIN cal -->\nlatest calibration {}\n<!-- END cal -->\n")


def test_a_best_effort_date_outside_the_declared_region_does_not_count(audit_repo):
    """A whole-file search accepted a date from an unrelated paragraph, so a
    generated block that lost its own provenance still reported fresh. The
    artifact's evidence has to come from the artifact."""
    art = [{"doc": "docs/cal.md", "region": "cal",
            "date_re": m.re.compile(r"latest calibration (\d{4}-\d{2}-\d{2})"),
            "max_age_days": 180,
            "refresher": "scripts/refresh_calibration_table.py"}]
    (audit_repo / "docs" / "cal.md").write_text(
        "latest calibration 2026-09-01\n\n<!-- BEGIN cal -->\nthe table\n<!-- END cal -->\n")
    out = m.check_best_effort_artifacts("2026-09-18", artifacts=art)
    assert len(out) == 1 and "carries no date" in out[0]["detail"], out


def test_a_best_effort_region_that_is_absent_is_a_finding(audit_repo):
    art = [{"doc": "docs/cal.md", "region": "cal",
            "date_re": m.re.compile(r"latest calibration (\d{4}-\d{2}-\d{2})"),
            "max_age_days": 180,
            "refresher": "scripts/refresh_calibration_table.py"}]
    (audit_repo / "docs" / "cal.md").write_text("latest calibration 2026-09-01\n")
    out = m.check_best_effort_artifacts("2026-09-18", artifacts=art)
    assert len(out) == 1 and "is not in the document" in out[0]["detail"], out


def test_a_best_effort_artifact_carries_its_own_freshness_evidence(audit_repo):
    """refresh-architecture-docs.yml runs `scripts.refresh_calibration_table`
    followed by `|| echo ... continuing`, so a Cloud SQL outage leaves
    docs/INVESTMENT_MODELS_SUMMARY.md stale while the run still concludes
    success AND the refresh PR still merges. Workflow success is not evidence
    that THIS artifact was refreshed; the only evidence is the date the
    artifact itself carries.
    """
    art = [{"doc": "docs/cal.md", "region": "cal",
            "date_re": m.re.compile(r"latest calibration (\d{4}-\d{2}-\d{2})"),
            "max_age_days": 180,
            "refresher": "scripts/refresh_calibration_table.py"}]
    (audit_repo / "docs" / "cal.md").write_text(CAL_REGION.format("2026-09-01"))
    assert m.check_best_effort_artifacts("2026-09-18", artifacts=art) == []
    (audit_repo / "docs" / "cal.md").write_text(CAL_REGION.format("2026-01-01"))
    out = m.check_best_effort_artifacts("2026-09-18", artifacts=art)
    assert len(out) == 1 and out[0]["severity"] == "P2", out
    assert "refresh_calibration_table" in out[0]["detail"]


def test_a_best_effort_artifact_with_no_date_at_all_is_a_finding(audit_repo):
    """No date means no evidence either way, which is not the same as fresh."""
    art = [{"doc": "docs/cal.md", "region": "cal",
            "date_re": m.re.compile(r"latest calibration (\d{4}-\d{2}-\d{2})"),
            "max_age_days": 180,
            "refresher": "scripts/refresh_calibration_table.py"}]
    (audit_repo / "docs" / "cal.md").write_text("<!-- BEGIN cal -->\nno date here\n<!-- END cal -->\n")
    out = m.check_best_effort_artifacts("2026-09-18", artifacts=art)
    assert len(out) == 1 and "no date" in out[0]["detail"], out


def test_an_impossible_date_in_a_best_effort_artifact_is_reported(audit_repo):
    art = [{"doc": "docs/cal.md", "region": "cal",
            "date_re": m.re.compile(r"latest calibration (\d{4}-\d{2}-\d{2})"),
            "max_age_days": 180,
            "refresher": "scripts/refresh_calibration_table.py"}]
    (audit_repo / "docs" / "cal.md").write_text(CAL_REGION.format("2026-02-30"))
    out = m.check_best_effort_artifacts("2026-09-18", artifacts=art)
    assert len(out) == 1 and "not a real calendar day" in out[0]["detail"], out


def test_the_calibration_staleness_bound_is_the_renderers_own():
    """The threshold is not invented here: past STALE_DAYS the renderer itself
    writes `B (stale)`, so a block older than that which still claims Tier A
    is proof the renderer has not re-rendered it."""
    src = (m.REPO / "scripts" / "refresh_calibration_table.py").read_text(encoding="utf-8")
    declared = int(m.re.search(r"^STALE_DAYS = (\d+)", src, m.re.M).group(1))
    assert m.BEST_EFFORT_ARTIFACTS[0]["max_age_days"] == declared


def test_the_registered_best_effort_artifact_is_the_calibration_table():
    assert [a["doc"] for a in m.BEST_EFFORT_ARTIFACTS] == ["docs/INVESTMENT_MODELS_SUMMARY.md"]
    doc = (m.REPO / "docs/INVESTMENT_MODELS_SUMMARY.md").read_text(encoding="utf-8")
    assert m.BEST_EFFORT_ARTIFACTS[0]["date_re"].search(doc), \
        "the artifact no longer carries the date this check reads"


# ── the plain output has to say where a finding must be fixed ──────────────

def test_plain_output_names_the_region_and_its_owner(audit_repo, capsys):
    """`--check` printed only the document and the detail, so a dead link
    inside generated inventory looked identical to an editable prose finding,
    which is the opposite of the rule never to edit a generated region."""
    (audit_repo / "gen" / "G.md").write_text(
        "# G\n\nprose\n\n<!-- inventory:x:start -->\nsee `scripts/gone.py`\n"
        "<!-- inventory:x:end -->\n")
    _commit(audit_repo, "tree")
    m.main(["--date", "2026-09-18", "--no-owning-job-check", "--issues-snapshot", str(audit_repo / "issues.json")])
    out = capsys.readouterr().out
    line = [row for row in out.split("\n") if "gone.py" in row]
    assert len(line) == 1, out
    assert "region: generated" in line[0], line
    assert m.OWNING_JOB["workflow"] in line[0], line


def test_plain_output_names_the_prompt_for_a_model_prose_finding(audit_repo, capsys):
    (audit_repo / "gen" / "G.md").write_text("# G\n\nsee `scripts/gone.py`\n")
    reg = audit_repo / "docs" / "DOC_REGISTRY.md"
    reg.write_text(reg.read_text().replace("| A | gen/*.md | | inventory:* |",
                                           "| A | gen/*.md | | prose:scripts/tool.py |"))
    _commit(audit_repo, "tree")
    m.main(["--date", "2026-09-18", "--no-owning-job-check", "--issues-snapshot", str(audit_repo / "issues.json")])
    out = capsys.readouterr().out
    line = [row for row in out.split("\n") if "gone.py" in row]
    assert len(line) == 1, out
    assert "region: model-prose" in line[0] and "scripts/tool.py" in line[0], line


def test_the_region_owner_is_carried_in_json_too(audit_repo, capsys):
    (audit_repo / "gen" / "G.md").write_text(
        "# G\n\nprose\n\n<!-- inventory:x:start -->\nsee `scripts/gone.py`\n"
        "<!-- inventory:x:end -->\n")
    _audit(audit_repo)
    report = json.loads(capsys.readouterr().out)
    dead = [f for f in report["findings"] if f["check"] == "dead-link"]
    assert len(dead) == 1 and dead[0]["region"] == "generated"
    assert dead[0]["region_owner"] == m.OWNING_JOB["workflow"], dead


def test_a_stale_best_effort_artifact_is_reported_by_a_whole_run(audit_repo, capsys, monkeypatch):
    """Through main(), and under --issues-snapshot: the evidence is what the
    artifact says about itself, so it must not be gated on the GitHub reads
    the way check_owning_job is."""
    monkeypatch.setattr(m, "BEST_EFFORT_ARTIFACTS", [{
        "doc": "docs/cal.md", "region": "cal",
        "date_re": m.re.compile(r"latest calibration (\d{4}-\d{2}-\d{2})"),
        "max_age_days": 180, "refresher": "scripts/refresh_calibration_table.py"}])
    (audit_repo / "docs" / "cal.md").write_text("# Cal\n\n" + CAL_REGION.format("2026-01-01"))
    _audit(audit_repo)
    report = json.loads(capsys.readouterr().out)
    assert [f["severity"] for f in report["findings"]
            if f["check"] == "class-a" and f["doc"] == "docs/cal.md"] == ["P2"], report["findings"]


# ── round 10 parity with the Node twin (solyra#69) ──────────────────────────


def test_a_snapshot_that_names_both_repos_but_records_nothing_is_bad_input(tmp_path):
    """fetch_issue_states refuses to report on a repository that returned zero
    issues; a snapshot read may not be laxer than the live path it stands in
    for. With an empty map every citation becomes a fabricated "could not be
    resolved" P2 and --check exits 1 for findings that do not exist."""
    f = tmp_path / "snap.json"
    f.write_text(json.dumps({"solyra": {}, "stocks": {}}))
    with pytest.raises(m.AuditError, match=r'empty "stocks" map'):
        m.load_issues_snapshot(str(f))


def test_a_snapshot_with_one_record_per_repo_still_loads(tmp_path):
    f = tmp_path / "snap.json"
    f.write_text(json.dumps({"solyra": {"1": {"state": "open"}},
                             "stocks": {"2": {"state": "closed"}}}))
    assert m.load_issues_snapshot(str(f))["stocks"][2]["state"] == "closed"


def test_an_issue_url_in_a_casing_github_accepts_resolves(tmp_path):
    """github.com/teneikaaskew/Stocks/issues/8 is the same issue. A
    case-sensitive match dropped the blocker; the `i` flag ALONE would index
    states['Stocks'], miss, and fabricate "could not be resolved"."""
    states = {"stocks": {8: {"state": "closed", "reason": "completed"}}}
    out = m.check_closed_issues(
        "d.md", "blocked by https://github.com/teneikaaskew/Stocks/issues/8\n", states)
    assert [f["severity"] for f in out] == ["P1"], out
    assert out[0]["ref"] == "stocks#8"


@pytest.mark.parametrize("prose", [
    "This is not blocked by",
    "nonblocking:",
    "A non-blocking note on",
    "No longer blocking:",
])
def test_a_negated_blocking_cue_is_not_a_citation_of_live_work(prose):
    """An unbounded substring match saw `blocked by` inside `not blocked by`
    and `blocking` inside `non-blocking`, so a line stating the opposite
    produced a P1 against the issue it exonerates."""
    states = {"stocks": {8: {"state": "closed", "reason": "completed"}}}
    line = f"{prose} https://github.com/TeneikaAskew/stocks/issues/8\n"
    assert m.check_closed_issues("d.md", line, states) == []


@pytest.mark.parametrize("prose", ["blocked by", "Blocking:", "Work not started on",
                                   "Still open:"])
def test_an_unnegated_cue_is_still_read_as_live_work(prose):
    states = {"stocks": {8: {"state": "closed", "reason": "completed"}}}
    line = f"{prose} https://github.com/TeneikaAskew/stocks/issues/8\n"
    assert len(m.check_closed_issues("d.md", line, states)) == 1


def test_a_link_example_inside_a_fence_is_not_a_dead_link():
    """A document showing Markdown syntax is not citing a path. The marker and
    heading checks already skip fenced lines; this one did not, so a syntax
    example failed --check over the document's own teaching material."""
    tracked = {"src/a.ts"}
    doc = "# T\n\n```md\n[x](missing.md)\n`nowhere/gone.py`\n```\n\nbody\n"
    assert m.check_dead_links("d.md", doc, tracked) == []


def test_the_same_link_outside_the_fence_is_still_flagged():
    assert len(m.check_dead_links("d.md", "# T\n\n[x](missing.md)\n", {"src/a.ts"})) == 1


def test_a_reference_style_definition_that_does_not_resolve_is_a_dead_link():
    """`[guide][g]` plus `[g]: missing.md` matches neither MD_LINK_RE nor the
    backticked-path pass, so the audit read clean over a link broken for every
    reader."""
    out = m.check_dead_links("d.md", "# T\n\nSee [guide][g].\n\n[g]: missing.md\n",
                             {"src/a.ts"})
    assert len(out) == 1 and "missing.md" in out[0]["detail"], out


def test_a_bracket_pair_that_is_not_a_reference_use_is_left_alone():
    """The USE half is deliberately unchecked. Measured over the 322 markdown
    documents in this tree: 1 reference definition, 204 bracket pairs, almost
    all issue-title tags -- `| #906 | P0 | [P0][Replay] Quarantine ...` is a
    title, not a link. Flagging undefined uses produced 79 fabricated findings,
    so only the definition's destination is validated."""
    doc = "# T\n\n| [#906](https://x/906) | P0 | [P0][Replay] Quarantine it |\n"
    assert m.check_dead_links("d.md", doc, {"src/a.ts"}) == []


def test_open_issues_plural_still_carries_a_blocking_cue():
    """Giving the cue alternation word boundaries dropped `Open issues`, whose
    trailing `s` leaves no boundary after `issue`. Caught by diffing findings
    over this tree: stocks#838, cited under `| Open issues |` in
    docs/product/09-SECURITY-AUTH.md, silently stopped being reported."""
    assert m.has_blocking_cue("| Open issues | [#838](x) |")
    assert m.has_blocking_cue("one open issue remains")


def test_an_inline_dead_anchor_keeps_its_original_wording():
    """Sharing the message builder with reference links relabelled every
    inline anchor finding `relative link ->`, churning 19 findings on this
    tree for no behaviour change."""
    # A real file, because the anchor set is read from disk and an unreadable
    # target skips the check entirely.
    out = m.check_dead_links("d.md", "# T\n\n[x](README.md#no-such-heading-here)\n",
                             {"README.md"})
    assert len(out) == 1, out
    assert out[0]["detail"].startswith("link -> README.md#no-such-heading-here"), out[0]


def test_a_reference_style_definition_that_resolves_is_quiet():
    assert m.check_dead_links("d.md", "# T\n\nSee [guide][g].\n\n[g]: src/a.ts\n",
                              {"src/a.ts"}) == []


def test_a_reference_style_definition_pointing_off_the_web_is_left_alone():
    assert m.check_dead_links("d.md", "# T\n\nSee [g][g].\n\n[g]: https://example.com/x\n",
                              {"src/a.ts"}) == []


def test_a_registry_glob_that_covers_nothing_is_a_finding():
    """`.claude/agents/*.md` can stop matching any tracked path -- every agent
    deleted, or the glob mistyped -- and no document reaches classify() to
    expose the inert declaration."""
    rows = [{"cls": "A", "glob": ".claude/agents/*.md", "code_paths": []}]
    out = m.check_registry_paths({"docs/x.md"}, rows)
    assert len(out) == 1 and "matches no tracked document" in out[0]["detail"], out


def test_a_registry_glob_that_covers_something_is_quiet():
    rows = [{"cls": "A", "glob": "docs/*.md", "code_paths": []}]
    assert m.check_registry_paths({"docs/x.md"}, rows) == []


def test_an_inline_link_carrying_a_title_is_still_checked():
    """`[guide](missing.md "Guide")` is standard CommonMark. Requiring `)`
    straight after the destination meant the pattern did not match at all, so
    the audit reported clean over a missing target. Raised on the Node twin
    (solyra#69)."""
    out = m.check_dead_links("d.md", '# T\n\n[guide](missing.md "Guide")\n', {"src/a.ts"})
    assert len(out) == 1 and "missing.md" in out[0]["detail"], out


def test_a_titled_inline_link_keeps_its_fragment_checkable():
    out = m.check_dead_links("d.md", "# T\n\n[x](README.md#no-such-heading 'T')\n",
                             {"README.md"})
    assert [f["check"] for f in out] == ["dead-anchor"], out


def test_a_titled_inline_link_that_resolves_is_quiet():
    assert m.check_dead_links("d.md", '# T\n\n[a](README.md "The readme")\n',
                              {"README.md"}) == []


def test_a_blocker_example_inside_a_fence_is_not_a_citation():
    """--check gates on closed-issue findings, so a document demonstrating what
    a blocking citation looks like failed the audit over its own example."""
    states = {"stocks": {8: {"state": "closed", "reason": "completed"}}}
    doc = "# T\n\n```md\nBlocked by https://github.com/TeneikaAskew/stocks/issues/8\n```\n"
    assert m.check_closed_issues("d.md", doc, states) == []


def test_the_same_blocker_outside_the_fence_is_still_reported():
    states = {"stocks": {8: {"state": "closed", "reason": "completed"}}}
    doc = "# T\n\nBlocked by https://github.com/TeneikaAskew/stocks/issues/8\n"
    assert len(m.check_closed_issues("d.md", doc, states)) == 1


# ── round 12 ────────────────────────────────────────────────────────────────


def test_a_fence_closes_only_on_a_compatible_delimiter():
    """A `~~~` line inside a ``` example is CODE. Toggling on any fence-looking
    line closed the block there, so the rest of the example read as prose and
    the prose after the real closing fence read as code."""
    assert sorted(m.fenced_lines(["```md", "~~~ ex", "```", "prose"])) == [0, 1, 2]
    assert sorted(m.fenced_lines(["~~~ts", "code", "~~~", "prose"])) == [0, 1, 2]


def test_a_heading_inside_a_fence_offers_no_anchor():
    """Recording it invented an anchor, so a link to a fragment the rendered
    document does not have PASSED the dead-anchor check."""
    assert sorted(m.heading_anchors("```md\n# Example\n```\n# Real\n")) == ["real"]


def test_a_heading_with_closing_atx_markers_anchors_on_its_text():
    """`## Install ##` renders as `Install`; GitHub's anchor is `#install`."""
    assert sorted(m.heading_anchors("## Install ##\n")) == ["install"]


def test_the_document_h1_is_not_a_heading_inside_a_fence():
    """--stamp would insert the provenance marker INSIDE the code block: the
    example rewritten, the document left effectively unstamped."""
    assert m.h1_index(["```md", "# Example", "```", "# Real Title"]) == 3


def test_a_malformed_line_region_is_an_audit_error():
    """re.error walks past the AuditError handler, so the CLI printed a
    traceback and exited 1 -- the status it documents for findings."""
    with pytest.raises(m.AuditError, match="not a valid regular"):
        m.owned_lines("# T\nbody\n", ["line:[unclosed"])
    m.owned_lines("# T\nbody\n", ["line:^body$"])


def test_unresolved_does_not_settle_a_citation():
    """An unbounded alternation matched `resolved` inside `unresolved`, so
    `Outstanding: <url> remains unresolved` settled the citation and a closed
    issue cited as live work produced no finding."""
    states = {"stocks": {1: {"state": "closed", "reason": "completed"}}}
    line = "Outstanding: https://github.com/TeneikaAskew/stocks/issues/1 remains unresolved\n"
    assert len(m.check_closed_issues("d.md", line, states)) == 1


def test_a_settled_word_embedded_in_a_longer_one_does_not_settle():
    """`unresolved` is caught by the negator scan, so it does not on its own
    prove the word boundary is doing anything. `enclosed` does: nothing before
    it is a negator, and an unbounded `closed` matches inside it, which settles
    a citation over prose that says nothing of the kind.

    Found by mutation-checking the boundary change and getting 0 failures --
    the test written for it was passing for the other reason.
    """
    states = {"stocks": {1: {"state": "closed", "reason": "completed"}}}
    line = ("Outstanding: https://github.com/TeneikaAskew/stocks/issues/1, "
            "enclosed in the table\n")
    assert len(m.check_closed_issues("d.md", line, states)) == 1


def test_a_genuinely_settled_citation_is_still_suppressed():
    states = {"stocks": {1: {"state": "closed", "reason": "completed"}}}
    line = "Outstanding: https://github.com/TeneikaAskew/stocks/issues/1 is now closed\n"
    assert m.check_closed_issues("d.md", line, states) == []


def test_two_citations_on_one_line_are_read_against_their_own_clauses():
    """One boolean for the whole line gave the closed #1 a P1 from #2's cue,
    on a line that says in so many words that #1 no longer blocks."""
    u = "https://github.com/TeneikaAskew/stocks/issues"
    states = {"stocks": {1: {"state": "closed", "reason": "completed"},
                         2: {"state": "open", "reason": ""}}}
    line = f"#1 {u}/1 is no longer blocking; #2 {u}/2 is still open\n"
    assert m.check_closed_issues("d.md", line, states) == []


def test_a_clause_with_no_cue_still_falls_back_to_the_line():
    """A table row puts the cue and the citations in different cells, and
    `| Open issues | #1 |` is a real finding -- it is how stocks#838 is
    reported on this tree. Scoping strictly to the clause would lose it."""
    u = "https://github.com/TeneikaAskew/stocks/issues/1"
    states = {"stocks": {1: {"state": "closed", "reason": "completed"}}}
    assert len(m.check_closed_issues("d.md", f"| Open issues | [#1]({u}) |\n", states)) == 1


@pytest.mark.parametrize("tgt", ["tel:+15551234", "ftp://example.com/x",
                                 "HTTPS://example.com/a", "//example.com/page"])
def test_a_destination_that_is_not_a_repository_path_is_left_alone(tgt):
    """A narrow, case-sensitive http/https/mailto allowlist sent all four down
    the repository-path branch and produced a P2 for a file never meant to
    exist locally."""
    assert m.check_dead_links("d.md", f"# T\n\n[x]({tgt})\n", {"src/a.py"}) == []


def test_a_percent_encoded_destination_resolves_against_the_decoded_name():
    """git reports the DECODED filename, so `Morning%20Checklist.md` was
    compared against a tracked `Morning Checklist.md` and reported dead."""
    assert m.check_dead_links("d.md", "# T\n\n[x](Morning%20Checklist.md)\n",
                              {"Morning Checklist.md"}) == []


def test_a_percent_encoded_destination_that_is_really_missing_is_still_dead():
    out = m.check_dead_links("d.md", "# T\n\n[x](Gone%20File.md)\n", {"src/a.py"})
    assert len(out) == 1
    # The ORIGINAL spelling is what the reader has to find in the document.
    assert "Gone%20File.md" in out[0]["detail"], out[0]["detail"]


def test_the_first_reference_definition_is_the_one_markdown_uses():
    """Overwriting with the last meant `[g]: missing.md` followed by
    `[g]: README.md` rendered as a broken link while the audit validated only
    the second and reported clean."""
    out = m.check_dead_links("d.md", "# T\n\nSee [g][g].\n\n[g]: missing.md\n[g]: README.md\n",
                             {"README.md"})
    assert len(out) == 1 and "missing.md" in out[0]["detail"], out


def test_two_registry_rules_of_equal_specificity_are_a_finding():
    """classify() keeps the FIRST of two equal-length matches, so a duplicate
    or equally long overlapping glob can park a document in Class X, suppress
    all auditing of it, and leave the conflicting Class D declaration ignored
    by table order alone."""
    reg = [{"cls": "X", "glob": "docs/a*.md", "code_paths": [], "regions": []},
           {"cls": "D", "glob": "docs/*a.md", "code_paths": [], "regions": []}]
    out = [f for f in m.check_registry_paths({"docs/aa.md"}, reg)
           if "equal specificity" in f["detail"]]
    assert len(out) == 1 and out[0]["doc"] == "docs/aa.md", out


def test_rules_of_different_specificity_are_not_ambiguous():
    reg = [{"cls": "X", "glob": "docs/*", "code_paths": [], "regions": []},
           {"cls": "D", "glob": "docs/aa.md", "code_paths": [], "regions": []}]
    assert [f for f in m.check_registry_paths({"docs/aa.md"}, reg)
            if "equal specificity" in f["detail"]] == []


def test_a_workflow_with_no_runs_at_all_is_refused(monkeypatch):
    """Returning [] made check_owning_job emit no run-status finding, so the
    delivery audit passed with no evidence the owning job ever executed."""
    monkeypatch.setattr(m, "run", lambda *a, **k: "")
    with pytest.raises(m.AuditError, match="no runs at all"):
        m.fetch_owning_runs(page_size=2)


def test_a_run_history_that_is_all_dry_runs_is_refused(monkeypatch):
    """Exhausting the page limit with nothing but dry runs is a TRUNCATED read.
    Returning it silently let consecutive manual dry runs hide a failed
    scheduled run behind them."""
    monkeypatch.setattr(m, "run",
                        lambda *a, **k: "success\t2026-01-01\tworkflow_dispatch\ttrue\n" * 2)
    with pytest.raises(m.AuditError, match="every one is a dry run"):
        m.fetch_owning_runs(page_size=2)


def test_a_history_with_a_delivering_run_still_returns(monkeypatch):
    monkeypatch.setattr(m, "run",
                        lambda *a, **k: "success\t2026-01-01\tschedule\t\n")
    assert len(m.fetch_owning_runs(page_size=2)) == 1


def test_a_document_deleted_from_the_working_tree_is_simply_gone(audit_repo, capsys):
    """Round 12 made this an AuditError, because the list came from HEAD and
    the contents from the working tree so an ordinary deletion raised
    FileNotFoundError. Round 17 went further and removed deleted paths from the
    audited tree, which is the better answer: a deletion is a normal edit, not
    a reason the audit cannot run. The guard it replaced still stands for a
    document that IS in the tree and cannot be read."""
    (audit_repo / "docs" / "d.md").write_text("# D\n\nbody\n")
    subprocess.run(["git", "add", "-A"], cwd=audit_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "doc"], cwd=audit_repo, check=True)
    (audit_repo / "docs" / "d.md").unlink()
    m.main(["--date", "2026-09-18", "--json", "--no-owning-job-check",
            "--issues-snapshot", str(audit_repo / "issues.json")])
    report = json.loads(capsys.readouterr().out)
    assert [f for f in report["findings"] if f["doc"] == "docs/d.md"] == [], report["findings"]


def test_a_cited_path_is_checked_on_any_extension_the_tree_tracks():
    """A hardcoded allowlist skipped `notebooks/x.ipynb` entirely, so deleting
    that notebook produced no finding though `notebooks` is plainly one of this
    repo's directories."""
    m.TOP_LEVEL_DIRS.add("notebooks")
    try:
        out = m.check_dead_links("d.md", "# T\n\n`notebooks/gone.ipynb`\n",
                                 {"notebooks/kept.ipynb"})
        assert len(out) == 1 and "gone.ipynb" in out[0]["detail"], out
    finally:
        m.TOP_LEVEL_DIRS.discard("notebooks")


def test_the_refresh_pr_limit_applies_after_the_merged_filter(monkeypatch):
    """Slicing the raw list meant six newer merged maintenance PRs -- which the
    attempt pattern is deliberately broad enough to match, and which never
    contribute to the strict `delivered` timestamp -- pushed an older
    unsuperseded OPEN refresh PR out of view."""
    # Six merged maintenance PRs the BROAD attempt pattern matches, newest
    # first as the API returns them, then the old open refresh at position 7.
    merged = "\n".join(
        f"{i}\tclosed\t2026-09-1{i}T00:00:00Z\t2026-09-1{i}T00:00:00Z\t"
        "fix architecture doc refresh authentication" for i in range(1, 7))
    stale_open = ("99\topen\t\t2026-01-01T00:00:00Z\t"
                  "Fix: Monthly architecture doc refresh failed")

    def fake_run(cmd, **kw):
        if "runs?per_page=10" in " ".join(cmd):
            return "success\t2026-09-18T06:00:00Z\tschedule\t\n"
        return f"{merged}\n{stale_open}\n"

    monkeypatch.setattr(m, "run", fake_run)
    monkeypatch.setattr(m.pathlib.Path, "exists", lambda self: False)
    out = m.check_owning_job("2026-09-18")
    assert any("#99" in f["detail"] for f in out), [f["detail"] for f in out]


def test_a_pr_needs_a_cue_in_its_own_clause_not_the_rows():
    """Measured on docs/product/12-PR-ISSUE-TRACEABILITY.md: extending the
    line-level fallback to PRs attributed a row's cue to whichever PR shared
    the row, producing four findings whose own source line says the opposite --
    `| #816 | #933 | merged default-no-op mechanism | ... outstanding |` is
    accurate prose about a merged PR. Issues keep the fallback: it is what
    reports stocks#838 under `| Open issues | ... |`, where the cue IS the row
    label."""
    u = "https://github.com/TeneikaAskew/stocks"
    states = {"stocks": {933: {"state": "closed", "reason": "merged"},
                         816: {"state": "open", "reason": ""}}}
    row = f"| [#816]({u}/issues/816) | [#933]({u}/pull/933) | merged mechanism | outstanding |"
    assert m.check_closed_issues("d.md", row, states) == []


def test_a_url_mask_stops_before_trailing_sentence_punctuation():
    """`\\S+` swallowed the `).` after a URL, so citation_clause ran into the
    NEXT sentence and picked up cues belonging to a different citation. Found
    by reading the one finding that survived the PR-clause rule."""
    line = "subsumes [#936](https://github.com/TeneikaAskew/stocks/pull/936). Still open."
    start = line.index("https")
    clause = m.citation_clause(line, start, start + len("https://github.com/TeneikaAskew/stocks/pull/936"))
    assert "Still open" not in clause, clause


def test_verify_without_stamp_is_rejected_before_any_side_effect(audit_repo, tmp_path):
    """The check ran after the issue-state reads, the snapshot write and the
    owning-job API calls, so an invalid invocation could fail with an unrelated
    GitHub authentication error -- and write the snapshot first."""
    out = tmp_path / "written.json"
    with pytest.raises(m.AuditError, match="requires --stamp"):
        m.main(["--date", "2026-09-18", "--verify", "docs/x.md",
                "--write-issues-snapshot", str(out)])
    assert not out.exists(), "a rejected invocation wrote its snapshot anyway"


def test_a_new_working_tree_document_is_audited(audit_repo, capsys):
    """`git ls-tree HEAD` does not list a staged or untracked document, so a
    contributor could run the audit clean and then commit a new unclassified
    document with no marker and dead links."""
    # The fixture tree has to be committed first, so the new document is the
    # only thing git does NOT have at HEAD.
    subprocess.run(["git", "add", "-A"], cwd=audit_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "tree"], cwd=audit_repo, check=True)
    (audit_repo / "docs" / "brand-new.md").write_text("# New\n\nbody\n")
    m.main(["--date", "2026-09-18", "--json", "--no-owning-job-check",
            "--issues-snapshot", str(audit_repo / "issues.json")])
    report = json.loads(capsys.readouterr().out)
    assert any(f["doc"] == "docs/brand-new.md" for f in report["findings"]), report["findings"]


# ── round 13 ────────────────────────────────────────────────────────────────


def test_a_marker_inside_an_html_comment_is_not_provenance():
    """It renders as nothing. Accepting it passed the missing-marker check, and
    --stamp then rewrote the line still inside the comment: success reported
    over a document with no rendered provenance at all."""
    lines = ["# T", "", "<!--", "**Last reviewed:** 2026-01-01 · **Owner:** X", "-->",
             "", "body"]
    assert m.find_markers(lines) == []


def test_a_marker_outside_the_comment_is_still_found():
    lines = ["# T", "", "<!-- a note -->", "**Last reviewed:** 2026-01-01 · **Owner:** X",
             "", "body"]
    assert [i for i, _ in m.find_markers(lines)] == [3]


def test_a_fenced_heading_does_not_end_the_marker_window():
    """Treating an example heading as the next section ended the search early,
    so an existing marker below the fence was reported missing and --stamp
    inserted a second one above it: contradictory provenance."""
    lines = ["# T", "```md", "## Example", "```", "**Last reviewed:** 2026-01-01", "body"]
    assert 4 in m.marker_window(lines)
    assert [i for i, _ in m.find_markers(lines)] == [4]


def test_link_syntax_shown_as_inline_code_is_not_a_link():
    """`` `[x](missing.md)` `` renders the brackets literally. Scanning it
    produced a gating dead-link finding over a document's own syntax example."""
    assert m.check_dead_links("d.md", "# T\n\nUse `[x](missing.md)` for links.\n",
                              {"src/a.py"}) == []


def test_escaped_link_syntax_is_not_a_link():
    assert m.check_dead_links("d.md", "# T\n\n\\[x](missing.md)\n", {"src/a.py"}) == []


def test_a_real_link_beside_a_code_span_is_still_checked():
    """The mask applies to the link pass only; a genuine link on the same line
    must survive it."""
    out = m.check_dead_links("d.md", "# T\n\nUse `[x](a.md)` then [y](missing.md).\n",
                             {"src/a.py"})
    assert len(out) == 1 and "missing.md" in out[0]["detail"], out


def test_tied_registry_rules_that_disagree_on_code_paths_are_a_finding():
    """The ambiguity check compared only `cls`, so duplicate Class D rows
    naming `lib/a` and `lib/b` produced no finding and changes under `lib/b`
    could never trigger drift."""
    reg = [{"cls": "D", "glob": "docs/a*.md", "code_paths": ["lib/a"], "regions": []},
           {"cls": "D", "glob": "docs/*a.md", "code_paths": ["lib/b"], "regions": []}]
    out = [f for f in m.check_registry_paths({"docs/aa.md", "lib/a", "lib/b"}, reg)
           if "equal specificity" in f["detail"]]
    assert len(out) == 1, out


def test_tied_registry_rules_that_agree_entirely_are_not_a_finding():
    reg = [{"cls": "D", "glob": "docs/a*.md", "code_paths": ["lib/a"], "regions": []},
           {"cls": "D", "glob": "docs/*a.md", "code_paths": ["lib/a"], "regions": []}]
    assert [f for f in m.check_registry_paths({"docs/aa.md", "lib/a"}, reg)
            if "equal specificity" in f["detail"]] == []


def test_a_since_commit_that_is_not_an_ancestor_is_refused():
    """Resolvable is not reviewable. A commit from another branch resolves
    fine, and writing it into a marker records a review against content this
    run never read -- which the next run reports as an invalid marker."""
    def fake_run(cmd, **kw):
        return "abcdef123456"
    orig = m.subprocess.run

    class Refused:
        returncode = 1

    m.subprocess.run = lambda *a, **k: (Refused() if a and "merge-base" in a[0]
                                        else orig(*a, **k))
    try:
        with pytest.raises(m.AuditError, match="not an ancestor"):
            m.resolve_marker_sha("other-branch", "HEAD", runner=fake_run)
    finally:
        m.subprocess.run = orig


def test_an_august_delivery_does_not_supersede_a_september_refresh(monkeypatch):
    """Comparing September's creation time with August's merge time treated the
    older delivery as superseding the newer attempt, so a still-unmerged
    September refresh was skipped -- though August's output says nothing about
    whether September's documents landed."""
    prs = "\n".join([
        "1100\topen\t\t2026-09-01T00:00:00Z\tMonthly architecture doc refresh: 2026-09",
        "1050\tclosed\t2026-09-10T00:00:00Z\t2026-08-01T00:00:00Z\t"
        "Monthly architecture doc refresh: 2026-08",
    ])
    monkeypatch.setattr(m, "run", lambda cmd, **k: "success\t2026-09-10T00:00:00Z\n"
                        if "runs?" in " ".join(cmd) else prs)
    monkeypatch.setattr(m.pathlib.Path, "exists", lambda self: False)
    findings = m.check_owning_job("2026-09-17")
    assert any("#1100" in f["detail"] for f in findings), [f["detail"] for f in findings]


def test_only_a_written_stamp_counts_as_changed(audit_repo, capsys):
    """`skipped-legacy-content` and `skipped-no-h1` queue no write, and several
    living documents return the former deliberately, so a routine --stamp
    reported them changed when no write existed."""
    # Behavioural, through main(): a document with no H1 cannot be stamped, so
    # a --stamp run over it must report 0 changed and say it was skipped.
    (audit_repo / "docs" / "noh1.md").write_text("no heading here\n\nbody\n")
    subprocess.run(["git", "add", "-A"], cwd=audit_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "doc"], cwd=audit_repo, check=True)
    m.main(["--date", "2026-09-18", "--no-owning-job-check", "--stamp",
            "--issues-snapshot", str(audit_repo / "issues.json")])
    out = capsys.readouterr().out
    # The registry document IS stamped, so one write happened. The point is
    # that noh1.md is NOT in that count: under the old rule it read
    # "2 changed", because every action other than `unchanged` was a change.
    assert "1 changed" in out, out
    assert "1 skipped" in out, out


def test_stamping_refuses_a_document_that_is_not_valid_utf8(audit_repo):
    """errors="replace" substitutes U+FFFD for any invalid byte, and --stamp
    writes the whole decoded string back -- corrupting bytes far outside the
    marker, which is the one thing stamping promises not to touch."""
    bad = audit_repo / "docs" / "bad.md"
    bad.write_bytes(b"# T\n\nca\xe9 body\n")
    subprocess.run(["git", "add", "-A"], cwd=audit_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "doc"], cwd=audit_repo, check=True)
    with pytest.raises(m.AuditError, match="not valid UTF-8"):
        m.main(["--date", "2026-09-18", "--no-owning-job-check", "--stamp",
                "--issues-snapshot", str(audit_repo / "issues.json")])
    # And the bytes are untouched, because nothing was written.
    assert bad.read_bytes() == b"# T\n\nca\xe9 body\n"


def test_a_read_only_run_still_reports_on_a_lossily_decoded_document(audit_repo, capsys):
    """No write follows, so replacement is harmless and refusing would make the
    audit unable to report on a document at all."""
    (audit_repo / "docs" / "bad.md").write_bytes(b"# T\n\nca\xe9 body\n")
    subprocess.run(["git", "add", "-A"], cwd=audit_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "doc"], cwd=audit_repo, check=True)
    m.main(["--date", "2026-09-18", "--json", "--no-owning-job-check",
            "--issues-snapshot", str(audit_repo / "issues.json")])
    report = json.loads(capsys.readouterr().out)
    assert any(f["doc"] == "docs/bad.md" for f in report["findings"]), report["findings"]


# ── round 14 ────────────────────────────────────────────────────────────────


def test_a_staged_new_document_is_audited(audit_repo, capsys):
    """`git ls-files --others` is UNTRACKED only, so `git add docs/new.md`
    moved the path into the index where it was neither "other" nor in HEAD --
    and the document fell out of both inventories at the moment before
    committing, which is exactly when the check is worth having."""
    subprocess.run(["git", "add", "-A"], cwd=audit_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "tree"], cwd=audit_repo, check=True)
    (audit_repo / "docs" / "staged.md").write_text("# Staged\n\nbody\n")
    subprocess.run(["git", "add", "docs/staged.md"], cwd=audit_repo, check=True)
    m.main(["--date", "2026-09-18", "--json", "--no-owning-job-check",
            "--issues-snapshot", str(audit_repo / "issues.json")])
    report = json.loads(capsys.readouterr().out)
    assert any(f["doc"] == "docs/staged.md" for f in report["findings"]), report["findings"]


@pytest.mark.parametrize("dest", ["<README.md>", "README.md?plain=1"])
def test_a_destination_that_is_not_a_bare_path_still_resolves(dest):
    """Angle brackets are delimiters -- the standard form when the path has a
    space -- and a query string is not part of the path. Both were compared
    against the tracked set verbatim and reported dead."""
    assert m.check_dead_links("d.md", f"# T\n\n[g]({dest})\n", {"README.md"}) == []


@pytest.mark.parametrize("dest", ["<gone.md>", "gone.md?x=1"])
def test_a_missing_target_written_either_way_is_still_dead(dest):
    assert len(m.check_dead_links("d.md", f"# T\n\n[g]({dest})\n", {"README.md"})) == 1


def test_inserting_a_marker_does_not_make_the_document_look_changed():
    """stamp() inserts the marker WITH a separating blank line, so dropping
    only the marker line left the normalised working copy carrying a blank the
    reviewed revision does not have -- and the very next audit reported
    changed-since for a document whose only edit was the audit's own marker."""
    before = "# T\n\nbody\n"
    after, _ = m.stamp(before, "2026-09-18", "scanned", "abc1234", False)
    assert after != before
    assert m._without_marker(after) == m._without_marker(before)


# ── round 15 ────────────────────────────────────────────────────────────────


def test_a_heading_inside_an_html_comment_is_not_the_document_h1():
    """--stamp would insert the marker inside the comment, report the document
    stamped, and leave the visible document without provenance."""
    assert m.h1_index(["<!--", "# Old title", "-->", "# Real"]) == 3


def test_a_comment_after_the_heading_does_not_hide_the_heading():
    """commented_lines is whole-line because that is the question a marker or
    an H1 asks. Treating any line CONTAINING a comment as commented would lose
    the H1 on `# Real Title <!-- note -->` and make the document unstampable."""
    assert m.h1_index(["# Real Title <!-- note -->", "body"]) == 0
    assert m.find_markers(["# T", "", "**Last reviewed:** 2026-01-01 <!-- ok -->", "body"])


def test_a_link_inside_an_html_comment_is_not_a_link():
    """Retired Markdown kept in a comment is not rendered, so --check could
    fail over content no reader can see."""
    assert m.check_dead_links("d.md", "# T\n\n<!-- [old](deleted.md) -->\n",
                              {"src/a.py"}) == []


def test_an_inline_comment_example_does_not_hide_the_rest_of_its_line():
    """SPANS, not whole lines. A line-level rule cost a real finding on
    docs/product/infrastructure/05-a-ARCHITECTURE.md:5, which mentions
    `<!-- inventory:*:start/end -->` inside backticks as an EXAMPLE and carries
    an ordinary citation beside it -- caught by diffing findings, not by
    reading the diff."""
    m.TOP_LEVEL_DIRS.add("docs")
    try:
        # A `<!--` inside BACKTICKS is not a comment at all, so the whole line
        # is live and both citations on it are checked.
        line = "> between `<!-- inventory:*:start/end -->` markers, see `docs/GONE.md`"
        out = m.check_dead_links("d.md", f"# T\n\n{line}\n", {"docs/kept.md"})
        assert len(out) == 1 and "docs/GONE.md" in out[0]["detail"], out

        # A GENUINE mid-line comment: the commented span is invisible, the rest
        # of the line is not. This is what makes the rule span-based rather
        # than line-based, for links and backticked paths alike.
        mixed = "See `docs/GONE.md` <!-- and `docs/HIDDEN.md` and [x](docs/HID.md) -->"
        out = m.check_dead_links("d.md", f"# T\n\n{mixed}\n", {"docs/kept.md"})
        details = " ".join(f["detail"] for f in out)
        assert "docs/GONE.md" in details, out
        assert "HIDDEN" not in details and "HID.md" not in details, out
    finally:
        m.TOP_LEVEL_DIRS.discard("docs")


def test_an_unknown_registry_class_is_refused():
    """A mistyped class was discarded in silence, so if the document it meant
    to cover also matches a broad fallback rule it is classified by THAT rule
    with no finding -- a fumbled Class A declaration landing as Class D lets
    the audit stamp and route fixes into machine-generated content."""
    with pytest.raises(m.AuditError, match="not one of A, B, C, D, X"):
        m.load_registry("## Registry\n\n| Class | Path glob | Declared code paths |\n"
                        "|---|---|---|\n| AA | docs/x.md | lib |\n")


def test_the_registry_header_and_delimiter_are_still_skipped_silently():
    reg = m.load_registry("## Registry\n\n| Class | Path glob | Declared code paths |\n"
                          "|---|---|---|\n| A | docs/x.md | lib |\n")
    assert [r["cls"] for r in reg] == ["A"], reg


def test_two_different_prose_owners_are_an_invalid_region_declaration():
    """The later assignment silently replaced the first, so the audit reported
    a valid region map, suppressed every unowned span, and routed all prose
    findings to one prompt while the registry claimed two."""
    _, unmatched, _, _, _ = m.owned_lines("# T\nbody\n", ["prose:p/a.md", "prose:p/b.md"],
                                          prompt_exists=lambda p: True)
    assert "prose:p/b.md" in unmatched, unmatched


def test_the_same_prose_owner_twice_is_not_a_conflict():
    _, unmatched, prompt, _, _ = m.owned_lines("# T\nbody\n",
                                               ["prose:p/a.md", "prose:p/a.md"],
                                               prompt_exists=lambda p: True)
    assert unmatched == [] and prompt == "p/a.md"


def test_a_pure_rename_into_a_declared_path_is_not_drift(tmp_path):
    """A path-limited log drops the old side of the pair, so `git log -- new.py`
    reports `A new.py` rather than `R100 old.py new.py` and drift_commits
    called a pure rename content drift -- the one case the R100 rule excludes.
    Reproduced against real git, not reasoned about."""
    def g(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@e.com")
    g("config", "user.name", "t")
    g("config", "commit.gpgsign", "false")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "old.py").write_text("x = 1\n")
    (tmp_path / "lib" / "other.py").write_text("y = 2\n")
    g("add", "-A")
    g("commit", "-qm", "base")
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                         capture_output=True, text=True).stdout.strip()
    g("mv", "lib/old.py", "lib/new.py")
    g("commit", "-qm", "pure rename")
    assert m.check_changed_since("d.md", sha, ["lib/new.py"], "HEAD", cwd=tmp_path) == []
    # And widening the query to the directory must not widen the ANSWER. An
    # EDIT to a sibling, not a rename: a pure rename would be excluded by the
    # R100 score anyway, so only an edit proves the narrowing is doing the work.
    (tmp_path / "lib" / "other.py").write_text("y = 3\n")
    g("add", "-A")
    g("commit", "-qm", "unrelated edit")
    assert m.check_changed_since("d.md", sha, ["lib/new.py"], "HEAD", cwd=tmp_path) == []
    # A real edit under the declared path is still drift.
    (tmp_path / "lib" / "new.py").write_text("x = 2\n")
    g("add", "-A")
    g("commit", "-qm", "edit")
    assert len(m.check_changed_since("d.md", sha, ["lib/new.py"], "HEAD", cwd=tmp_path)) == 1


def test_an_unfinished_run_does_not_end_the_walk(monkeypatch):
    """A queued or in-progress run has an empty conclusion. Stopping on it
    treated "the rerun has not finished" as sufficient history, so a completed
    delivering run that FAILED, pushed onto an earlier page by dry runs, was
    never examined."""
    pages = {1: "\t2026-09-18T00:00:00Z\tschedule\t\n\t2026-09-17T00:00:00Z\tschedule\t\n",
             2: "failure\t2026-09-16T00:00:00Z\tschedule\t\n"}
    seen = []

    def fake_run(cmd, **kw):
        joined = " ".join(cmd)
        # `&page=`, not `page=`: the URL also carries `per_page=2`, and matching
        # the bare substring sent EVERY call to page 2 -- so the first version
        # of this test asserted `2 in seen` against a walk that never visited
        # page 1 and passed no matter what the pagination did.
        page = 2 if "&page=2" in joined else 1
        seen.append(page)
        return pages[page]

    monkeypatch.setattr(m, "run", fake_run)
    rows = m.fetch_owning_runs(page_size=2)
    assert seen == [1, 2], seen
    assert any(r[0] == "failure" for r in rows), rows


def test_a_successful_no_op_refresh_is_freshness_evidence(audit_repo, monkeypatch):
    """refresh-architecture-docs.yml reverts every timestamp-only file and
    opens its PR only when `meaningful == '1'`, so a month that regenerated
    identical content leaves the old Generated date in place BY DESIGN. Two of
    those in a row put every owned document past 40 days and the audit called
    them all stale -- a finding whose only remedy would be forcing a cosmetic
    change."""
    (audit_repo / "docs" / "arch.md").write_text("# A\n\nGenerated 2026-07-01\n")
    monkeypatch.setattr(m, "OWNING_JOB", {**m.OWNING_JOB, "docs": ["docs/arch.md"]})
    monkeypatch.setattr(m, "run", lambda cmd, **k: (
        "success\t2026-09-15T00:00:00Z\tschedule\t\n" if "runs?" in " ".join(cmd) else ""))
    out = [f for f in m.check_owning_job("2026-09-18") if f["doc"] == "docs/arch.md"]
    assert [f["severity"] for f in out] == ["P3"], out
    assert "no-op refresh" in out[0]["detail"], out[0]["detail"]


def test_an_old_stamp_with_no_recent_success_is_still_stale(audit_repo, monkeypatch):
    """The no-op allowance must not swallow the case the check exists for."""
    (audit_repo / "docs" / "arch.md").write_text("# A\n\nGenerated 2026-07-01\n")
    monkeypatch.setattr(m, "OWNING_JOB", {**m.OWNING_JOB, "docs": ["docs/arch.md"]})
    monkeypatch.setattr(m, "run", lambda cmd, **k: (
        "success\t2026-07-01T00:00:00Z\tschedule\t\n" if "runs?" in " ".join(cmd) else ""))
    out = [f for f in m.check_owning_job("2026-09-18") if f["doc"] == "docs/arch.md"]
    assert [f["severity"] for f in out] == ["P2"], out


# ── round 16 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("before", ["# T\n\nbody\n", "# T\nbody\n"])
def test_stamping_never_makes_a_document_look_changed(before):
    """`stamp` inserts a blank AFTER the marker, and one BEFORE it as well when
    the document had none -- and the two cases produce byte-identical output,
    so the stamped text cannot say which happened. Removing only the trailing
    blank left `# T\n\nbody` where the reviewed revision was `# T\nbody`."""
    after, _ = m.stamp(before, "2026-09-18", "scanned", "abc1234", False)
    assert after != before
    assert m._without_marker(after) == m._without_marker(before)


def test_a_heading_inside_an_html_comment_offers_no_anchor():
    """A link to `#hidden` passed the dead-anchor audit even though the
    rendered document exposes no such anchor."""
    assert sorted(m.heading_anchors("<!--\n# Hidden\n-->\n# Real\n")) == ["real"]


def test_a_staged_addition_satisfies_a_link(audit_repo, capsys):
    """An index addition is part of the content about to be committed, so it
    resolves links as any tracked file does. Otherwise a multi-file
    documentation change cannot be audited cleanly before it is committed --
    the one moment the audit is most useful. An UNTRACKED file is different."""
    subprocess.run(["git", "add", "-A"], cwd=audit_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "tree"], cwd=audit_repo, check=True)
    (audit_repo / "docs" / "target.md").write_text("# Target\n\nbody\n")
    (audit_repo / "docs" / "source.md").write_text("# Source\n\nSee [t](target.md).\n")
    subprocess.run(["git", "add", "docs/target.md", "docs/source.md"],
                   cwd=audit_repo, check=True)
    m.main(["--date", "2026-09-18", "--json", "--no-owning-job-check",
            "--issues-snapshot", str(audit_repo / "issues.json")])
    report = json.loads(capsys.readouterr().out)
    dead = [f for f in report["findings"] if f["check"] == "dead-link"]
    assert dead == [], dead
    # And both are still audited.
    assert {f["doc"] for f in report["findings"]} >= {"docs/source.md", "docs/target.md"}


def test_an_untracked_file_still_does_not_satisfy_a_link(audit_repo, capsys):
    """It may never be committed, and letting it satisfy a link is the bug
    is_tracked_dir was written to close."""
    subprocess.run(["git", "add", "-A"], cwd=audit_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "tree"], cwd=audit_repo, check=True)
    (audit_repo / "docs" / "target.md").write_text("# Target\n\nbody\n")
    (audit_repo / "docs" / "source.md").write_text("# Source\n\nSee [t](target.md).\n")
    subprocess.run(["git", "add", "docs/source.md"], cwd=audit_repo, check=True)
    m.main(["--date", "2026-09-18", "--json", "--no-owning-job-check",
            "--issues-snapshot", str(audit_repo / "issues.json")])
    report = json.loads(capsys.readouterr().out)
    assert [f for f in report["findings"] if f["check"] == "dead-link"], report["findings"]


def test_the_shipped_registry_declares_no_rule_that_covers_nothing():
    """docs/models/*.md declared a rule for documents that live only on an
    unmerged branch, so it covered nothing on main -- found by the checker
    added in this same PR, and fixed at the source rather than exempted."""
    tracked = set(m.run(["git", "ls-tree", "-r", "HEAD", "--name-only"]).strip().split("\n"))
    registry = m.load_registry((m.REPO / m.REGISTRY).read_text(encoding="utf-8"))
    inert = [f for f in m.check_registry_paths(tracked, registry)
             if "covers nothing" in f["detail"]]
    assert inert == [], inert


# ── round 17 ────────────────────────────────────────────────────────────────


def test_a_commented_heading_does_not_bound_the_marker_window():
    """Treating it as the next section excluded the real marker from the
    search, so the audit reported it missing and --stamp inserted a second one
    above the comment."""
    lines = ["# T", "<!--", "# Hidden", "-->", "**Last reviewed:** 2026-01-01", "body"]
    assert 4 in m.marker_window(lines)
    assert [i for i, _ in m.find_markers(lines)] == [4]


def test_a_setext_heading_offers_an_anchor():
    """GitHub renders it and exposes the anchor; an ATX-only scan recorded none,
    so a valid link to it was a gating dead-anchor finding."""
    assert sorted(m.heading_anchors("Install\n=======\n\nOther\n-------\n")) == \
        ["install", "other"]


def test_a_table_delimiter_is_not_a_setext_heading():
    assert sorted(m.heading_anchors("| a |\n|---|\n")) == []


def test_a_destination_with_balanced_parentheses_resolves():
    """Stopping at the first `)` validated `guide(v2` and called a tracked file
    dead."""
    assert m.check_dead_links("d.md", "# T\n\n[g](guide(v2).md)\n",
                              {"guide(v2).md"}) == []


def test_a_missing_parenthesised_destination_is_still_dead():
    out = m.check_dead_links("d.md", "# T\n\n[g](gone(v2).md)\n", {"guide(v2).md"})
    assert len(out) == 1, out


def test_an_empty_line_region_is_refused():
    """`re.compile("")` matches EVERY line, so the region map called the whole
    document generated and valid: the hand-written complement suppressed,
    stamping disabled, every finding routed to the renderer."""
    with pytest.raises(m.AuditError, match="has no pattern"):
        m.owned_lines("# T\nbody\n", ["line:"])


def test_a_commented_reference_definition_is_not_a_definition():
    """The inline and backticked passes mask commented spans; this separate
    pass did not, so a non-rendered definition still produced a gating finding."""
    # Multi-line, so the definition sits at column 0 and REF_DEF_RE does match
    # it -- the single-line form never matched, so a test using it passed
    # whatever the comment handling did.
    doc = "# T\n\nSee [g][guide].\n\n<!--\n[guide]: deleted.md\n-->\n"
    assert m.check_dead_links("d.md", doc, {"src/a.py"}) == []


def test_a_generated_date_in_an_example_is_not_provenance(audit_repo, monkeypatch):
    """A whole-document scan let any `Generated YYYY-MM-DD` in sample output
    stand in for a missing footer, so removing the real stamp while keeping a
    recent example passed the freshness check with no production date."""
    # Through check_owning_job, because recomputing the filter in the test
    # proves only that the expression works, not that anything calls it.
    (audit_repo / "docs" / "arch.md").write_text(
        "# A\n\n```\nGenerated 2026-09-17\n```\n\n<!-- Generated 2026-09-16 -->\n")
    monkeypatch.setattr(m, "OWNING_JOB", {**m.OWNING_JOB, "docs": ["docs/arch.md"]})
    monkeypatch.setattr(m, "run", lambda cmd, **k: (
        "success\t2026-09-18T00:00:00Z\tschedule\t\n" if "runs?" in " ".join(cmd) else ""))
    out = [f for f in m.check_owning_job("2026-09-18") if f["doc"] == "docs/arch.md"]
    assert [f["detail"] for f in out] == [
        "no `Generated <date>` stamp, so nothing in the document shows when the "
        "owning job produced it"], out


def test_a_registered_non_markdown_artifact_skips_the_markdown_checks(audit_repo, capsys):
    """A registered `.drawio` is XML. Scanning it as Markdown turned a diagram
    label reading `[x](missing.md)` into a gating dead-link finding for a
    construct nothing renders."""
    (audit_repo / "docs" / "Arch.drawio").write_text(
        '<mxfile><root><mxCell value="[x](missing.md)"/></root></mxfile>\n')
    (audit_repo / "docs" / "DOC_REGISTRY.md").write_text(
        (audit_repo / "docs" / "DOC_REGISTRY.md").read_text()
        + "| D | docs/Arch.drawio | src |  |\n")
    subprocess.run(["git", "add", "-A"], cwd=audit_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "art"], cwd=audit_repo, check=True)
    m.main(["--date", "2026-09-18", "--json", "--no-owning-job-check",
            "--issues-snapshot", str(audit_repo / "issues.json")])
    report = json.loads(capsys.readouterr().out)
    assert [f for f in report["findings"]
            if f["doc"] == "docs/Arch.drawio" and f["check"] == "dead-link"] == []


def test_a_staged_deletion_leaves_the_audited_tree(audit_repo, capsys):
    """Keeping a deleted path in `tracked` let a surviving document link to an
    asset that is gone and pass."""
    (audit_repo / "docs" / "target.md").write_text("# Target\n\nbody\n")
    (audit_repo / "docs" / "source.md").write_text("# Source\n\nSee [t](target.md).\n")
    subprocess.run(["git", "add", "-A"], cwd=audit_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "docs"], cwd=audit_repo, check=True)
    subprocess.run(["git", "rm", "-q", "docs/target.md"], cwd=audit_repo, check=True)
    m.main(["--date", "2026-09-18", "--json", "--no-owning-job-check",
            "--issues-snapshot", str(audit_repo / "issues.json")])
    report = json.loads(capsys.readouterr().out)
    assert [f for f in report["findings"] if f["check"] == "dead-link"], report["findings"]


@pytest.mark.parametrize("delivery,expected", [
    # Same generation merged BEFORE the attempt opened: a re-attempt, live.
    (("2026-09", "2026-09-02T00:00:00Z"), False),
    # Older generation merged after: says nothing about this generation.
    (("2026-08", "2026-09-20T00:00:00Z"), False),
    # Newer generation: this attempt is history.
    (("2026-10", "2026-10-02T00:00:00Z"), True),
    # Same generation merged after the attempt opened: delivered.
    (("2026-09", "2026-09-20T00:00:00Z"), True),
])
def test_supersession_needs_both_generation_and_time(delivery, expected):
    """Each half was learned from a case, and the per-delivery form is what
    exposed that the round-13 generation fix had been passing an existing test
    for the wrong reason -- delivered_gen was a max over ALL deliveries."""
    gen, merged = delivery
    pr = {"num": "1060", "title": "Monthly architecture doc refresh: 2026-09",
          "merged": "", "created": "2026-09-08T00:00:00Z"}
    d = [{"num": "d", "title": f"Monthly architecture doc refresh: {gen}",
          "merged": merged, "created": "2026-01-01T00:00:00Z"}]
    assert m.superseded(pr, d) is expected


def test_the_walk_stops_on_the_same_rule_that_reports(monkeypatch):
    """A timestamp stop and a generation report can disagree, and when they do
    the walk ends before the PR the report would name.

    Page 1: #1200 open (`refresh: 2026-10`, created 10-01) and #900 merged
    (`refresh: 2026-08`, merged 10-05). Under a creation-versus-merge stop the
    walk ends here -- 10-01 < 10-05 -- while the report says #1200 is NOT
    superseded, because August's output cannot establish that October's
    documents landed. The walk must read on."""
    pages = ["\n".join([
        "1200\topen\t\t2026-10-01T00:00:00Z\tMonthly architecture doc refresh: 2026-10",
        "900\tclosed\t2026-10-05T00:00:00Z\t2026-08-01T00:00:00Z\t"
        "Monthly architecture doc refresh: 2026-08",
    ] + _filler(1000, 1098)),
        "800\tclosed\t2026-07-02T00:00:00Z\t2026-07-01T00:00:00Z\t"
        "Monthly architecture doc refresh: 2026-07"]
    fake = _pr_pages(pages)
    monkeypatch.setattr(m, "run", fake)
    monkeypatch.setattr(m.pathlib.Path, "exists", lambda self: False)
    out = m.check_owning_job("2026-10-20")
    assert fake.calls["n"] == 2, "stopped on a rule the report does not use"
    assert [f for f in out if "1200" in f["detail"]], out


def test_an_intraword_underscore_survives_into_the_anchor():
    """Stripping every `_` turned `## API_FIELD` into `apifield`, so a valid
    link to `#api_field` read as a dead anchor AND an incorrect `#apifield` was
    accepted -- wrong in both directions at once."""
    assert m.heading_slug("API_FIELD") == "api_field"
    assert m.heading_slug("_em_") == "em"
    assert m.heading_slug("**Bold** thing") == "bold-thing"


def test_a_table_row_with_no_padding_keeps_its_cells_separate():
    """`\\S*` swallowed the `|` with the URL, so citation_clause merged adjacent
    cells and an issue described as no longer blocking inherited a live-work
    cue from the next one."""
    u = "https://github.com/TeneikaAskew/stocks/issues/"
    line = f"| {u}1| still open {u}2|"
    clause = m.citation_clause(line, line.index(u), line.index(u) + len(u) + 1)
    assert "still open" not in clause, clause


def test_a_setext_h1_is_the_document_heading():
    """Without it the audit reported a missing marker while --stamp answered
    `skipped-no-h1`, so the command could not repair its own finding."""
    assert m.h1_index(["Title", "=====", "body"]) == 0
    assert m.h1_index(["Title", "-----", "body"]) is None


def test_a_title_section_longer_than_the_limit_still_contains_its_marker():
    """A document opening with more than 40 lines of HTML metadata had its real
    marker excluded from the window, so the audit reported it missing and
    --stamp inserted a second one."""
    lines = ["# T", *["x"] * 45, "**Last reviewed:** 2026-01-01"]
    assert 46 in m.marker_window(lines)
    assert [i for i, _ in m.find_markers(lines)] == [46]


def test_the_marker_window_still_stops_at_the_next_heading():
    lines = ["# T", "body", "## Next", "**Last reviewed:** 2026-01-01"]
    assert list(m.marker_window(lines)) == [1]


# ── round 19 ────────────────────────────────────────────────────────────────

def test_a_tracked_extension_longer_than_five_characters_is_citable():
    """The backticked-path regex capped the extension at five characters, so
    `docs/STRAT_ENGINE_ERD.drawio` never matched and could not be checked --
    though this tree tracks five `.drawio` files and check_dead_links derives
    its allowlist from the tree precisely so those are covered."""
    assert m.BACKTICK_PATH_RE.findall("see `docs/gone.drawio` here") == ["docs/gone.drawio"]
    assert m.BACKTICK_PATH_RE.findall("`a/b.properties`") == ["a/b.properties"]
    assert m.BACKTICK_PATH_RE.findall("`docs/x.py:88-102`") == ["docs/x.py:88-102"]


def test_a_citation_of_a_long_extension_that_is_gone_is_reported():
    """The regex is only half of it: the extension must also survive the
    tree-derived allowlist, so this drives check_dead_links rather than the
    pattern."""
    m.TOP_LEVEL_DIRS.update({"docs"})
    tracked = {"docs/here.drawio", "docs/d.md"}
    out = m.check_dead_links("docs/d.md", "See `docs/gone.drawio`.\n", tracked)
    assert [f["detail"] for f in out] == ["backticked path -> docs/gone.drawio"], out
    assert m.check_dead_links("docs/d.md", "See `docs/here.drawio`.\n", tracked) == []


def test_a_fenced_inventory_example_does_not_form_a_region():
    """A document SHOWING what a generated block looks like had its example
    read as a real one, so the renderer's region check ran against prose and
    the marker-placement test measured against a line that is a code sample."""
    lines = ["# T", "```", "<!-- inventory:demo:start -->",
             "<!-- inventory:demo:end -->", "```"]
    assert m.inventory_blocks(lines) == ({}, [])


def test_an_unbalanced_inventory_marker_outside_a_fence_is_still_reported():
    """Skipping fenced lines must not swallow the real finding next to them."""
    lines = ["# T", "```", "<!-- inventory:demo:start -->", "```",
             "<!-- inventory:real:start -->"]
    pairs, unbalanced = m.inventory_blocks(lines)
    assert pairs == {}
    assert len(unbalanced) == 1 and "inventory:real" in unbalanced[0], unbalanced


def test_a_retired_blocker_inside_an_html_comment_does_not_gate():
    """--check gates on closed-issue findings, so text commented OUT -- the
    normal way to retire a blocker list without losing it -- held the build
    red over prose that no longer renders."""
    u = "https://github.com/TeneikaAskew/stocks/issues/838"
    states = {"stocks": {838: {"state": "closed", "reason": "completed"}}}
    assert m.check_closed_issues("d.md", f"# T\n\n<!-- was: still open {u} -->\n",
                                 states) == []
    live = m.check_closed_issues("d.md", f"# T\n\nstill open {u}\n", states)
    assert len(live) == 1 and live[0]["severity"] == "P1", live


def test_a_setext_titled_document_can_be_stamped():
    """h1_index learning setext is not the same as --stamp placing a marker:
    the abort Codex reported is in stamp(), and only driving stamp() binds it.

    The first version of this test asserted the marker's POSITION and nothing
    else, and passed on a stamp that wrote the marker BETWEEN the title and its
    `===` underline -- splitting the heading, leaving the document with no H1
    at all. Codex caught that on the next round. What the test has to assert is
    that the heading survives, which is the thing the stamp was for.
    """
    new, action = m.stamp("Title\n=====\n\nBody.\n", "2026-09-18", "verified",
                          "abc1234", reviewed=True)
    assert action == "inserted", action
    lines = new.split("\n")
    assert lines[:2] == ["Title", "====="], lines
    assert m.h1_index(lines) == 0, new
    assert lines[3].startswith("**Last reviewed:** 2026-09-18"), new


def test_a_staged_rename_audits_the_new_path_and_not_the_old(audit_repo, capsys):
    """`git mv docs/old.md docs/new.md` reports as `R100`, which neither the
    `--diff-filter=A` nor the `--diff-filter=D` query consumes. The old path
    therefore stayed in the inventory and the new one was absent, so the run
    opened a document that is no longer on disk -- exit 2, on the one workflow
    (audit before you commit) the staged-addition support exists for."""
    (audit_repo / "docs" / "old.md").write_text("# Old\n\nSee `scripts/tool.py`.\n")
    _commit(audit_repo, "tree")
    _git(audit_repo, "mv", "docs/old.md", "docs/new.md")
    code = m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
                   "--issues-snapshot", str(audit_repo / "issues.json")])
    assert code != 2, capsys.readouterr()
    report = json.loads(capsys.readouterr().out)
    docs = {f["doc"] for f in report["findings"]}
    assert "docs/old.md" not in docs, report["findings"]


def test_a_staged_rename_target_resolves_a_link(audit_repo, capsys):
    """The other half: the new path must also COUNT as tracked, or every
    citation of it reads as dead the moment the rename is staged."""
    (audit_repo / "docs" / "old.md").write_text("# Old\n")
    (audit_repo / "docs" / "d.md").write_text("# D\n\nSee `docs/new.md`.\n")
    _commit(audit_repo, "tree")
    _git(audit_repo, "mv", "docs/old.md", "docs/new.md")
    m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
            "--issues-snapshot", str(audit_repo / "issues.json")])
    report = json.loads(capsys.readouterr().out)
    dead = [f for f in report["findings"] if f["check"] == "dead-link"]
    assert dead == [], dead


def test_a_review_is_not_recorded_against_a_commit_predating_the_document(
        audit_repo, capsys):
    """`--stamp --verify` on a staged-new document wrote `Against: <HEAD>`,
    a commit that does not contain it. `git show <sha>:<doc>` then exits 128
    forever after and check_doc_changed_since reads that as "no drift", so the
    document permanently claims a verification against a revision in which it
    did not exist."""
    (audit_repo / "docs" / "d.md").write_text("# D\n")
    _commit(audit_repo, "tree")
    (audit_repo / "docs" / "new.md").write_text("# New\n")
    _git(audit_repo, "add", "docs/new.md")
    with pytest.raises(m.AuditError, match="baseline predating it"):
        m.main(["--date", "2026-09-18", "--no-owning-job-check", "--stamp",
                "--verify", "docs/new.md",
                "--issues-snapshot", str(audit_repo / "issues.json")])
    assert "**Last reviewed:**" not in (audit_repo / "docs" / "new.md").read_text()


def test_a_baseline_that_predates_the_document_is_reported_not_silent(audit_repo,
                                                                     capsys):
    """A marker already carrying such a SHA (written before the refusal above,
    or by hand) must say so rather than reporting a clean drift check it never
    ran."""
    (audit_repo / "docs" / "d.md").write_text("# D\n")
    first = _commit(audit_repo, "tree")
    (audit_repo / "docs" / "new.md").write_text(
        f"# New\n\n**Last reviewed:** 2026-09-01 · **Depth:** verified · "
        f"**Against:** `{first}` · **Last scanned:** 2026-09-18\n")
    _audit(audit_repo)
    report = json.loads(capsys.readouterr().out)
    bad = [f for f in report["findings"]
           if f["doc"] == "docs/new.md" and "does not exist at" in f["detail"]]
    assert len(bad) == 1 and bad[0]["severity"] == "P2", report["findings"]


def test_a_generated_region_under_a_setext_title_still_blocks_the_stamp(audit_repo,
                                                                       capsys):
    """The proximity guard has to measure from the line the marker actually
    lands on. A Setext H1 occupies two lines, so measuring from the title lets
    a generated region beginning immediately after the underline pass the
    guard -- and the marker is then written into content the renderer
    overwrites on its next run."""
    (audit_repo / "gen" / "g.md").write_text(
        "Title\n=====\n<!-- inventory:x:start -->\nbody\n<!-- inventory:x:end -->\n")
    _commit(audit_repo, "tree")
    m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check", "--stamp",
            "--issues-snapshot", str(audit_repo / "issues.json")])
    report = json.loads(capsys.readouterr().out)
    blocked = [f for f in report["findings"]
               if f["doc"] == "gen/g.md" and "too close to the H1" in f["detail"]]
    assert len(blocked) == 1, report["findings"]
    assert "line 3" in blocked[0]["detail"] and "H1 on line 2" in blocked[0]["detail"], \
        blocked[0]["detail"]
    assert "**Last reviewed:**" not in (audit_repo / "gen" / "g.md").read_text()


# ── round 20 ────────────────────────────────────────────────────────────────

def test_a_setext_section_heading_ends_the_marker_window():
    """The window stops at the next SECTION, and Setext is a section heading
    too. Reading only `#` let a date inside the following section stand in for
    the document's provenance -- the same defect the `# PART A` case in
    marker_window's own docstring describes, one syntax over."""
    lines = ["# T", "body", "Details", "-------", "**Last reviewed:** 2026-01-01"]
    assert list(m.marker_window(lines)) == [1]
    assert m.find_markers(lines) == []


def test_an_underline_is_not_a_section_heading_without_text_above_it():
    """A `---` after a blank line is a thematic break, and a table's delimiter
    row is not a heading either. Ending the window on those would cut it at the
    first table, which several documents open with."""
    assert list(m.marker_window(["# T", "", "---", "**Last reviewed:** 2026-01-01"])) \
        == [1, 2, 3]
    assert list(m.marker_window(["# T", "| a | b |", "|---|---|",
                                 "**Last reviewed:** 2026-01-01"])) == [1, 2, 3]


def test_an_unmatched_comment_opener_inside_a_fence_comments_nothing():
    """`<!--` shown inside a code block is a code sample. Read as a real
    opener it ran to end of file, so every heading, marker and link after that
    fence was treated as invisible: false marker findings AND suppressed
    content findings, from one example line."""
    lines = ["# T", "```", "<!-- unbalanced", "```", "## Real", "[x](missing.md)"]
    spans = m.comment_spans(lines)
    assert 4 not in spans and 5 not in spans, spans


def test_a_real_comment_spanning_a_fence_still_hides_what_it_encloses():
    """Masking fences must not break a comment that legitimately contains one."""
    lines = ["# T", "<!-- retired:", "```", "[x](missing.md)", "```", "-->", "after"]
    spans = m.comment_spans(lines)
    assert 3 in spans and 6 not in spans, spans


def test_content_sharing_the_marker_line_still_counts_as_drift():
    """`stamp` deliberately preserves extra segments on the marker line --
    `Trust status` on docs/product/09-SECURITY-AUTH.md is real content that a
    review is about. Deleting the whole line before comparing made a change to
    that content invisible to the drift check."""
    a = "# T\n\n**Last reviewed:** 2026-01-01 · **Trust status:** GREEN\n"
    b = "# T\n\n**Last reviewed:** 2026-01-01 · **Trust status:** RED\n"
    assert m._without_marker(a) != m._without_marker(b)


def test_moving_only_the_audit_owned_fields_is_still_not_drift():
    """The other direction, which is why the line is normalised at all: the
    weekly scan rewrites `Last scanned` on every document."""
    a = "# T\n\n**Last reviewed:** 2026-01-01 · **Last scanned:** 2026-01-02\n"
    b = "# T\n\n**Last reviewed:** 2026-01-01 · **Last scanned:** 2026-09-18\n"
    assert m._without_marker(a) == m._without_marker(b)


def test_a_link_in_an_indented_code_block_is_not_a_link():
    """A four-space-indented block is a code block in CommonMark, and the
    documents here use that form for examples. Both link passes scanned it."""
    m.TOP_LEVEL_DIRS.update({"docs"})
    text = "# T\n\nExample:\n\n    [demo](missing.md)\n    see `docs/gone.md`\n"
    assert m.check_dead_links("docs/d.md", text, {"docs/d.md"}) == []


def test_an_indented_continuation_of_a_list_item_is_still_prose():
    """Indented code cannot interrupt a paragraph or a list item's own
    continuation, so the rule must not swallow an ordinary wrapped bullet."""
    m.TOP_LEVEL_DIRS.update({"docs"})
    text = "# T\n\n- a bullet\n    [demo](missing.md)\n"
    out = m.check_dead_links("docs/d.md", text, {"docs/d.md"})
    assert [f["detail"] for f in out] == ["relative link -> missing.md"], out


def test_decode_fragment_leaves_a_stray_percent_alone():
    """Decoding is applied to every fragment rather than guessed at, which is
    only safe because an invalid escape passes through untouched."""
    assert m.decode_fragment("caf%C3%A9") == "café"
    assert m.decode_fragment("plain-anchor") == "plain-anchor"
    assert m.decode_fragment("100%-done") == "100%-done"


def test_a_percent_encoded_fragment_resolves_to_its_heading(audit_repo):
    """`#caf%C3%A9` is how a link to `## Café` is written, and it works.
    Comparing the encoded spelling against the decoded slug reported it dead.

    Driven through check_dead_links, not decode_fragment: the helper had a test
    and the CALL SITE did not, so a mutation restoring the raw comparison left
    the suite green.
    """
    m.TOP_LEVEL_DIRS.update({"docs"})
    (audit_repo / "docs" / "t.md").write_text("# T\n\n## Café\n")
    tracked = {"docs/d.md", "docs/t.md"}
    assert m.check_dead_links("docs/d.md", "See [x](t.md#caf%C3%A9).\n", tracked) == []
    dead = m.check_dead_links("docs/d.md", "See [x](t.md#caf%C3%A8).\n", tracked)
    assert len(dead) == 1 and dead[0]["check"] == "dead-anchor", dead


def test_a_short_core_abbrev_does_not_silence_the_drift_check():
    """`%h` honours `core.abbrev`, and below seven characters the header
    pattern rejected every commit line -- so the name-status lines that follow
    were attributed to nothing and real code drift produced no finding."""
    out = "abcd\tsubject\nM\tlib/x.py\n"
    assert m.drift_commits(out) == ["abcd\tsubject"], m.drift_commits(out)


def test_the_drift_log_asks_for_a_full_commit_id():
    """The parser is widened so it can read output a caller produced, but the
    audit's own query must not depend on local config at all: `%h` honours
    `core.abbrev` and this tool is run on other people's checkouts."""
    src = inspect.getsource(m.check_changed_since)
    assert "--format=%H%x09%s" in src, src
    assert "%h%x09" not in src, src


def test_a_comment_closed_on_an_indented_line_still_closes():
    """The reason the comment scan is ORDERED rather than a wholesale mask.

    Masking every code line destroyed a `-->` sitting on an indented
    continuation of the comment that opened above it, so the comment ran to end
    of file and every later finding vanished. Measured on the Node twin's
    docs/UI-SCREENS.md, which opens exactly this way: five real closed-issue
    findings disappeared, and only the findings diff caught it.
    """
    lines = ["<!-- Moved from the stocks repo", "",
             "     which stayed there. -->", "still blocked by #1"]
    # The closer's own line IS indented code by the rule above -- a blank line
    # precedes it and the text before that is no list item. That is precisely
    # why a wholesale mask destroyed it, so the fixture has to reproduce it.
    assert 2 in m.indented_code_lines(lines)
    spans = m.comment_spans(lines)
    # The blank line carries no range because it has no offsets; what matters
    # is that the comment CLOSED, so the prose below it is not swallowed.
    assert sorted(spans) == [0, 2], spans
    assert 3 not in spans, spans


def test_a_comment_cannot_be_opened_from_inside_a_code_block():
    """The other direction, which is what the ordering buys: a code line may
    close a comment but may not open one."""
    assert m.comment_spans(["# T", "```", "<!-- unbalanced", "```", "## Real"]) == {}
    # The blank line matters: indented code cannot interrupt a paragraph, so
    # without it the indented line is prose and its `<!--` is a real opener.
    assert m.comment_spans(["# T", "", "    <!-- indented sample", "",
                            "## Real"]) == {}


# ── round 21 ────────────────────────────────────────────────────────────────

def test_a_setext_title_does_not_empty_its_own_marker_window():
    """A regression I introduced last round, and the sharpest kind: the fix for
    "stop at a Setext SECTION heading" made the document's OWN `=====` the
    first line scanned, so the window closed before it opened and the marker
    `stamp` had just placed correctly was reported missing -- the next run
    would insert a duplicate. The boundary scan starts after the whole H1, not
    after its title line."""
    lines = ["Title", "=====", "", "**Last reviewed:** 2026-01-01", "", "body"]
    assert list(m.marker_window(lines)) == [2, 3, 4, 5]
    assert [i for i, _ in m.find_markers(lines)] == [3]


def test_a_setext_titled_document_round_trips_through_stamp():
    """The two halves together: stamp places the marker, and the next run finds
    it rather than inserting a second. Neither helper test catches that."""
    text = "Title\n=====\n\nBody.\n"
    once, a1 = m.stamp(text, "2026-09-18", "scanned", "abc1234")
    twice, a2 = m.stamp(once, "2026-09-18", "scanned", "abc1234")
    assert (a1, a2) == ("inserted", "unchanged"), (a1, a2)
    assert once == twice, twice
    assert once.count("**Last reviewed:**") == 1, once


def test_an_inline_code_inventory_example_forms_no_region():
    """The fenced case was fixed last round; the same example written as inline
    code was still read as real delimiters. A document explaining the
    convention shows it both ways."""
    lines = ["# T", "Shows `<!-- inventory:x:start -->` and `<!-- inventory:x:end -->`."]
    assert m.inventory_blocks(lines) == ({}, [])


def test_a_real_inventory_marker_beside_a_backticked_one_is_still_read():
    """Masking code spans must not swallow the delimiter next to the example."""
    lines = ["# T", "like `<!-- inventory:x:start -->` -- <!-- inventory:real:start -->",
             "<!-- inventory:real:end -->"]
    pairs, unbalanced = m.inventory_blocks(lines)
    assert pairs == {"real": (2, 3)} and unbalanced == [], (pairs, unbalanced)


def test_an_indented_atx_heading_offers_its_anchor():
    """CommonMark admits up to three leading spaces, and the fence and Setext
    parsers here already do. A link to `#details` was reported dead."""
    assert m.heading_anchors("# T\n\n  ## Details\n") == {"t", "details"}
    # Four spaces is indented code, not a heading.
    assert m.heading_anchors("# T\n\n    ## Code\n") == {"t"}


def test_a_fence_inside_a_block_quote_is_still_code():
    """`> ```bash` is the shape SETUP.md and CLAUDE.md already use, and the
    leading `>` hid the fence entirely -- so a link or blocker citation in the
    sample was audited as live prose."""
    assert sorted(m.fenced_lines(["> ```bash", "> [x](missing.md)", "> ```"])) == [0, 1, 2]
    assert sorted(m.fenced_lines(["> ```", "> x", "> ```", "> after"])) == [0, 1, 2]


def test_an_angle_bracketed_destination_with_a_space_is_checked():
    """`[g](<docs/removed guide.md>)` is how a destination containing a space is
    written. The pattern rejected the whitespace, so the link never matched and
    a missing target reported clean."""
    m.TOP_LEVEL_DIRS.update({"docs"})
    out = m.check_dead_links("docs/d.md", "See [g](<removed guide.md>).\n", {"docs/d.md"})
    assert [f["check"] for f in out] == ["dead-link"], out
    assert m.check_dead_links("docs/d.md", "See [g](<here.md>).\n",
                              {"docs/d.md", "docs/here.md"}) == []


def test_a_backticked_root_file_is_checked_against_the_root_files_tracked():
    """`requirements-gcp.txt` and `alert_config.json` are cited exactly that
    way here, and requiring a slash meant deleting either produced no finding.
    Only names the tree's ROOT actually holds are checked, so ordinary dotted
    prose is not mistaken for a path."""
    tracked = {"docs/d.md", "requirements.txt", "alert_config.json"}
    # The base ref's root held `requirements-gcp.txt`; the working tree no
    # longer does, which is the rot being reported.
    base_root = {"requirements.txt", "requirements-gcp.txt", "alert_config.json"}
    out = m.check_dead_links("docs/d.md", "See `requirements-gcp.txt`.\n",
                             tracked, base_root)
    assert [f["detail"] for f in out] == ["backticked path -> requirements-gcp.txt"], out
    assert m.check_dead_links("docs/d.md", "See `requirements.txt`.\n",
                              tracked, base_root) == []


def test_a_bare_basename_of_a_subdirectory_file_is_not_a_root_citation():
    """The discriminator, and the reason the first version of this check was
    wrong. Keying on the EXTENSION produced 304 fabricated findings on this
    tree in one run -- `db-query.yml`, `MODEL_REGISTRY.md`, `05-a-ARCHITECTURE.md`
    -- every one a real file cited without its directory. Only a name the
    ROOT actually held is this repo's to resolve bare."""
    m.TOP_LEVEL_DIRS.update({"docs"})
    tracked = {"docs/d.md", ".github/workflows/db-query.yml", "docs/MODEL_REGISTRY.md"}
    base_root = {"README.md"}
    for cite in ("db-query.yml", "MODEL_REGISTRY.md", "v1.2"):
        assert m.check_dead_links("docs/d.md", f"See `{cite}`.\n",
                                  tracked, base_root) == [], cite


def test_a_registry_row_with_an_empty_glob_is_bad_input():
    """Dropping the row silently discarded its region ownership and code paths,
    so a Class A document could fall through to a broader Class D rule and be
    stamped as hand-written content with no finding at all."""
    with pytest.raises(m.AuditError, match="empty path glob"):
        m.load_registry("## Registry\n\n| Class | Path glob | Declared code paths |\n"
                        "|---|---|---|\n| A |  | lib |\n")


def test_a_marker_shaped_line_that_does_not_parse_is_refused():
    """`**Last reviewed:** 2026-9-1` matches neither marker pattern, so the
    audit called the marker absent and --stamp inserted a valid one ABOVE it --
    leaving two contradictory review claims that the duplicate check cannot
    see, because only one of them parses."""
    text = "# T\n\n**Last reviewed:** 2026-9-1\n\nbody\n"
    new, action = m.stamp(text, "2026-09-18", "scanned", "abc1234")
    assert action == "skipped-malformed-marker", action
    assert new == text
    assert m.check_marker_shape("d.md", text.split("\n"))[0]["severity"] == "P2"


def test_a_well_formed_marker_is_not_called_malformed():
    text = "# T\n\n**Last reviewed:** 2026-09-01 · **Last scanned:** 2026-09-18\n"
    assert m.check_marker_shape("d.md", text.split("\n")) == []


def test_stamping_a_crlf_document_rewrites_only_the_marker(tmp_path, monkeypatch):
    """`read_text` performs universal-newline conversion, so `write_text` then
    rewrote every line ending in the file -- a whole-file diff for a one-line
    stamp, and the opposite of what --stamp promises."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    doc = tmp_path / "d.md"
    doc.write_bytes(b"# T\r\n\r\nbody\r\n")
    m.write_stamp("d.md", "# T\n\n**Last reviewed:** x\n\nbody\n")
    raw = doc.read_bytes()
    assert raw == b"# T\r\n\r\n**Last reviewed:** x\r\n\r\nbody\r\n", raw


def test_stamping_an_lf_document_does_not_gain_carriage_returns(tmp_path, monkeypatch):
    """The other direction: the file is the authority, so an LF document stays
    LF whatever the platform would default to."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    doc = tmp_path / "d.md"
    doc.write_bytes(b"# T\n\nbody\n")
    m.write_stamp("d.md", "# T\n\n**Last reviewed:** x\n\nbody\n")
    assert b"\r" not in doc.read_bytes()


def test_a_delivery_title_must_match_the_workflow_output_exactly():
    """`Fix Monthly architecture doc refresh: 2026-09 authentication` is a
    repair PR, not a delivery. Counting it let a repair supersede an unmerged
    refresh with no generated document having landed."""
    assert m._refresh_generation("Monthly architecture doc refresh: 2026-09") == "2026-09"
    assert m._refresh_generation("Fix Monthly architecture doc refresh: 2026-09 auth") == ""
    assert m._refresh_generation("chore: bump 2026-09 deps") == ""


def test_an_unparsed_marker_is_reported_by_a_whole_run(audit_repo, capsys):
    """Through main(), not beside it. The helper had a test and the call site
    did not, so a mutation deleting the wiring left the suite green -- the same
    shape that has now cost four tests this session."""
    (audit_repo / "docs" / "d.md").write_text("# D\n\n**Last reviewed:** 2026-9-1\n\nbody\n")
    _audit(audit_repo)
    report = json.loads(capsys.readouterr().out)
    bad = [f for f in report["findings"]
           if f["doc"] == "docs/d.md" and "parses as neither" in f["detail"]]
    assert len(bad) == 1 and bad[0]["severity"] == "P2", report["findings"]


def test_a_run_still_in_flight_does_not_hide_the_failure_beneath_it(monkeypatch):
    """`delivering[0][0] not in {"success", ""}` accepted an empty conclusion,
    which is what a queued or in-progress run has. The completed run beneath
    it -- the one that actually failed -- was never examined, so the delivery
    audit reported clean while the rerun had delivered nothing. The pagination
    fix fetched that row; this condition ignored it."""
    rows = [["", "2026-09-18T10:00:00Z"], ["failure", "2026-09-17T10:00:00Z"]]
    monkeypatch.setattr(m, "fetch_owning_runs", lambda **k: rows)
    monkeypatch.setattr(m, "run", lambda *a, **k: "")
    monkeypatch.setattr(m.pathlib.Path, "exists", lambda self: False)
    out = m.check_owning_job("2026-09-18")
    bad = [f for f in out if "concluded failure" in f["detail"]]
    assert len(bad) == 1 and bad[0]["severity"] == "P1", out


def test_a_completed_success_beneath_an_in_flight_run_is_still_clean():
    """The other direction: an in-flight run is not evidence of a problem
    either, so the last COMPLETED delivering run is what decides."""
    rows = [("", "2026-09-18T10:00:00Z"), ("success", "2026-09-17T10:00:00Z")]
    assert m.last_delivering_conclusion(rows) == ("success", "2026-09-17T10:00:00Z")
    assert m.last_delivering_conclusion([("", "x")]) is None


# ── round 22 ────────────────────────────────────────────────────────────────

def test_stamping_refuses_a_symlinked_document(tmp_path, monkeypatch):
    """The write follows the link, so `--stamp` edited the TARGET rather than a
    repository document -- and a symlink committed on a branch can point
    anywhere writable. `is_file()` follows symlinks too, so the preflight did
    not stop it. Codex filed this as a P1 on the Node twin (solyra#69) and the
    same hazard was live here."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n\nuntouched\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "link.md").symlink_to(outside)
    with pytest.raises(m.AuditError, match="symlink"):
        m.write_stamps([("docs/link.md", "# X\n")])
    assert outside.read_text() == "# Outside\n\nuntouched\n"


def test_stamping_still_writes_an_ordinary_document(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "REPO", tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "d.md").write_text("# D\n")
    m.write_stamps([("docs/d.md", "# D\n\nmarker\n")])
    assert (tmp_path / "docs" / "d.md").read_text() == "# D\n\nmarker\n"


def test_not_yet_resolved_is_not_settled():
    """`is not yet resolved and still blocking` says the issue is live, and the
    positive substring `resolved` read as a completion cue -- so a closed
    blocker described this way produced no finding at all."""
    assert not m.is_settled("is not yet resolved and still blocking")
    assert not m.is_settled("has not yet merged")
    assert m.is_settled("resolved in #12")


def test_indented_code_inside_a_list_item_is_still_code():
    """The previous rule excluded every run whose preceding content was a list
    marker, which is right for a wrapped bullet and wrong for a code block
    nested IN the item: after `- item` and a blank line, four spaces past the
    item's content indent is CommonMark indented code."""
    m.TOP_LEVEL_DIRS.update({"docs"})
    lines = ["- item", "", "      [demo](missing.md)"]
    assert sorted(m.indented_code_lines(lines)) == [2], lines
    text = "# T\n\n- item\n\n      [demo](missing.md)\n"
    assert m.check_dead_links("docs/d.md", text, {"docs/d.md"}) == []
    # And the floor has to MOVE with the item, not sit at 4: four spaces is
    # short of this item's content column plus four, so it is a second
    # paragraph OF the item and still prose. A fixed floor of 4 calls it code
    # and loses the link -- which is why the assertion above cannot stand
    # alone, it passes under either floor.
    assert m.indented_code_lines(["- item", "", "    [demo](missing.md)"]) == set()
    lazy = "# T\n\n- item\n\n    [demo](missing.md)\n"
    assert [f["detail"] for f in m.check_dead_links("docs/d.md", lazy, {"docs/d.md"})] \
        == ["relative link -> missing.md"]


def test_a_wrapped_bullet_is_still_prose():
    """The case the exclusion existed for: a continuation indented to the
    item's content column is the bullet's own text, not a code block."""
    m.TOP_LEVEL_DIRS.update({"docs"})
    text = "# T\n\n- item\n  [demo](missing.md)\n"
    out = m.check_dead_links("docs/d.md", text, {"docs/d.md"})
    assert [f["detail"] for f in out] == ["relative link -> missing.md"], out


def test_a_single_hyphen_underlines_a_setext_heading():
    """CommonMark allows one `-` when nonblank heading text precedes it, and
    the preceding-line check is what tells it from a list marker."""
    assert m.heading_anchors("# T\n\nTitle\n-\n") == {"t", "title"}
    # A `-` after a blank line is a list bullet, not an underline.
    assert m.heading_anchors("# T\n\n-\n") == {"t"}


def test_an_indented_atx_h1_is_the_document_heading():
    """heading_anchors learned the three-space prefix; H1_RE did not, so the
    audit reported a missing marker while --stamp answered `skipped-no-h1` and
    could not repair its own finding."""
    assert m.h1_index(["  # Title", "body"]) == 0
    assert m.h1_index(["    # Code", "body"]) is None


def test_an_angle_bracketed_reference_definition_keeps_its_spaces():
    """`[g]: <docs/my guide.md>` is the form a destination with a space takes,
    and `\\S+` stopped at the first space and validated `docs/my`."""
    mo = m.REF_DEF_RE.match("[g]: <docs/my guide.md>")
    assert mo and mo.group("target") == "<docs/my guide.md>", mo
    plain = m.REF_DEF_RE.match("[g]: docs/guide.md")
    assert plain and plain.group("target") == "docs/guide.md"


def test_a_shorthand_blocker_reference_is_resolved():
    """`#940` is how docs/product/16-CONSOLIDATION-AUDIT.md cites a blocker,
    and a URL-only pattern never saw it -- so closing the issue produced no
    finding. Only on a line that already carries a blocking cue, because a
    bare `#940` in ordinary prose is not a citation."""
    states = {"stocks": {940: {"state": "closed", "reason": "completed"}}}
    out = m.check_closed_issues("d.md", "# T\n\nStill blocked by #940.\n", states)
    assert len(out) == 1 and out[0]["ref"] == "stocks#940", out
    assert m.check_closed_issues("d.md", "# T\n\nsection #940 of the spec\n",
                                 states) == []


def test_one_citation_written_both_ways_is_reported_once():
    """`[#861](.../issues/861)` is the ordinary Markdown shape and carries the
    shorthand AND the URL. Read independently the two passes reported one
    citation twice, which double-counted every blocker row in
    docs/product/12-PR-ISSUE-TRACEABILITY.md. The URL-span guard could not see
    it: the `#861` in the link LABEL sits outside the URL it hides."""
    states = {"stocks": {861: {"state": "closed", "reason": "completed"}}}
    line = f"| Blocking issues | [#861]({U.format('stocks', 861)}) |"
    out = m.check_closed_issues("d.md", f"# T\n\n{line}\n", states)
    assert len(out) == 1 and out[0]["ref"] == "stocks#861", out
    # Two DIFFERENT numbers on one line stay two findings.
    states["stocks"][940] = {"state": "closed", "reason": "completed"}
    both = m.check_closed_issues(
        "d.md", f"# T\n\nBlocked by #940 and [#861]({U.format('stocks', 861)}).\n",
        states)
    assert sorted(f["ref"] for f in both) == ["stocks#861", "stocks#940"], both


def test_a_document_whose_name_is_not_ascii_is_audited(audit_repo, capsys):
    """git C-QUOTES a non-ASCII path unless the read passes `-z`, so
    `docs/café.md` came back as the literal `"docs/caf\\303\\251.md"`. That name
    is in no inventory, resolves no link, and the document itself was never
    opened -- it simply vanished from the audit. Through main(), because the
    quoting happens in the git reads main() does."""
    (audit_repo / "docs" / "café.md").write_text(
        "# Café\n\n<!-- docs-audit: reviewed 2026-09-18 -->\n\n[x](missing.md)\n",
        encoding="utf-8")
    _audit(audit_repo)
    report = json.loads(capsys.readouterr().out)
    docs = {f["doc"] for f in report["findings"]}
    assert "docs/café.md" in docs, sorted(docs)


def test_a_shorthand_is_held_to_its_own_clause_not_the_line():
    """A bare `#N` is weaker evidence than a URL, so it carries the stricter
    cue rule the URL pass reserves for PRs. Measured on this tree, the
    line-level fallback attributed one row's `open` to every number in a long
    sentence: `ten more canonical issues closed ... (#820, #833, ...)` was
    reported as live work, which is the opposite of what the line says."""
    states = {"stocks": {820: {"state": "closed", "reason": "completed"}}}
    # The citation's own clause carries NO cue either way, so only the absent
    # line-level fallback can decide it. A clause that says `closed` would be
    # caught by the settled-cue test instead and prove nothing about the
    # fallback.
    line = "Outstanding work remains; the #820 primitive shipped in September."
    i = line.index("#820")
    assert m.cites_live_work(line, i, i + 4) is True, "the fallback must fire here"
    assert m.check_closed_issues("d.md", f"# T\n\n{line}\n", states) == []
    # The cue in the citation's OWN clause still reports.
    assert len(m.check_closed_issues(
        "d.md", "# T\n\nThe shared #820 primitive is outstanding.\n", states)) == 1


def test_a_heading_anchor_is_not_a_shorthand_citation():
    """`\\b` holds between the `6` and the `-` of
    `(#16-outstanding-work--known-gaps)`, so a table of contents read as a
    citation of stocks#16 -- on a line whose own word `Outstanding` supplied
    the cue."""
    states = {"stocks": {16: {"state": "closed", "reason": "completed"}}}
    toc = "16. [Outstanding Work & Known Gaps](#16-outstanding-work--known-gaps)"
    assert m.check_closed_issues("d.md", f"# T\n\n{toc}\n", states) == []


def test_a_number_from_another_numbering_domain_is_not_an_issue():
    """`Plan #4` and `plans #5 and #10` are plan numbering that happens to
    share the spelling. The second number is reached by coordination, so
    testing only the text immediately before each `#` skipped half a list and
    reported the other half."""
    states = {"stocks": {n: {"state": "closed", "reason": "completed"}
                         for n in (4, 5, 10)}}
    assert m.check_closed_issues(
        "d.md", "# T\n\nPlan #4 is still outstanding.\n", states) == []
    assert m.check_closed_issues(
        "d.md", "# T\n\nOutstanding: closes the gap in plans #5 and #10.\n",
        states) == []


def test_a_parenthetical_is_a_clause_boundary_for_a_shorthand():
    """`In progress -- the provenance half is done (#1095: every API-served
    table now labels replay rows)` gave the shorthand the row's `In progress`.
    The innermost parenthetical containing the citation is its real clause."""
    states = {"stocks": {1095: {"state": "closed", "reason": "completed"}}}
    line = ("| In progress -- the **provenance half is done** "
            "(#1095: every API-served table now labels replay rows) |")
    assert m.check_closed_issues("d.md", f"# T\n\n{line}\n", states) == []
    # "a (b (c) d) e" -- the inner pair is 5..7, and it is the one returned
    # even though the outer pair also contains the span.
    assert m.enclosing_parenthetical("a (b (c) d) e", 6, 7) == (6, 7)
    assert m.enclosing_parenthetical("a (b c d) e", 5, 6) == (3, 8)
    assert m.enclosing_parenthetical("no parens here", 3, 6) is None


def test_a_backticked_path_may_carry_spaces_in_its_basename():
    """`docs/Morning Checklist Updated.md` is tracked in this tree and cited in
    docs/BRIEFING_DECK.md; the no-space pattern never matched it, so deleting
    the target reported clean. The directory part still refuses spaces, or
    `run docs/a.md and docs/b.md` parses as one path and is reported dead."""
    m.TOP_LEVEL_DIRS.update({"docs"})
    text = "# T\n\nSee `docs/Morning Checklist Updated.md` for the routine.\n"
    out = m.check_dead_links("docs/d.md", text, {"docs/d.md"})
    assert [f["detail"] for f in out] == [
        "backticked path -> docs/Morning Checklist Updated.md"], out
    assert m.check_dead_links(
        "docs/d.md", "# T\n\nSee `docs/Morning Checklist Updated.md`.\n",
        {"docs/d.md", "docs/Morning Checklist Updated.md"}) == []
    assert m.BACKTICK_PATH_RE.search("`run docs/a.md and docs/b.md`") is None


def test_a_link_label_may_contain_brackets():
    """`[^\\]]*` stopped at the first `]`, so a link whose text carries brackets
    never matched and its target went unchecked. docs/gamma_levels.md writes
    ``[`ANALYST_PROMPTS[\"gamma\"]`](../lib/agents/prompts.py)``."""
    m.TOP_LEVEL_DIRS.update({"docs"})
    text = '# T\n\n[`ANALYST_PROMPTS["gamma"]`](gone.md) is the prompt.\n'
    out = m.check_dead_links("docs/d.md", text, {"docs/d.md"})
    assert [f["detail"] for f in out] == ["relative link -> gone.md"], out


def test_a_closed_issue_in_indented_code_is_not_a_finding():
    """Only fences were excluded, so a four-space example carrying blocker
    prose and a closed issue URL emitted a GATING P1 over content that renders
    as code -- the same construct the dead-link pass already skips."""
    states = {"stocks": {940: {"state": "closed", "reason": "completed"}}}
    text = ("# T\n\nHow a blocker row is written:\n\n"
            f"    | Blocked by | {U.format('stocks', 940)} |\n")
    assert m.check_closed_issues("docs/d.md", text, states) == []
    # Unindented, the same row is still reported.
    live = f"# T\n\n| Blocked by | {U.format('stocks', 940)} |\n"
    assert len(m.check_closed_issues("docs/d.md", live, states)) == 1


def test_a_fenced_example_of_a_mark_pair_is_not_the_generated_region():
    """A Class A document whose real block went missing had its own fenced
    EXAMPLE of the pair accepted as the `mark:` region: the unmatched-region
    finding was suppressed and the sample classified as renderer-owned."""
    text = ("# T\n\nThe renderer writes:\n\n```\n<!-- BEGIN CAL -->\nrows\n"
            "<!-- END CAL -->\n```\n\nand nothing else.\n")
    owned, unmatched, prompt, exhaustive, orphans = m.owned_lines(text, ["mark:CAL"])
    assert unmatched == ["mark:CAL"], (unmatched, owned)
    # An INLINE-code mention is documentation too: "write `<!-- BEGIN CAL -->`
    # above the block". Only the fence exclusion catches the block form.
    inline = ("# T\n\nWrite `<!-- BEGIN CAL -->` above it and "
              "`<!-- END CAL -->` below.\n")
    _, unmatched_inline, _, _, _ = m.owned_lines(inline, ["mark:CAL"])
    assert unmatched_inline == ["mark:CAL"], unmatched_inline
    # The real pair, outside a fence, still matches.
    real = "# T\n\n<!-- BEGIN CAL -->\nrows\n<!-- END CAL -->\n"
    owned2, unmatched2, _, _, _ = m.owned_lines(real, ["mark:CAL"])
    assert unmatched2 == [] and owned2, (unmatched2, owned2)


def test_a_registry_path_with_spaces_survives_whatever_its_extension():
    """The row was kept only when it ended `.md`, so a Class A
    `docs/Generated Diagram.drawio` was silently dropped and fell through to a
    broader rule, losing its code paths and region ownership."""
    table = (f"{m.REGISTRY_HEADING}\n\n"
             "| Class | Path glob | Declared code paths | Generated regions |\n"
             "|---|---|---|---|\n"
             "| A | docs/Generated Diagram.drawio | scripts/render.py | mark:DIAGRAM |\n")
    rows = m.load_registry(table)
    assert [r["glob"] for r in rows] == ["docs/Generated Diagram.drawio"], rows
    assert rows[0]["regions"] == ["mark:DIAGRAM"] and rows[0]["cls"] == "A"


def test_a_registry_glob_that_is_prose_is_refused_not_dropped():
    """What the extension test was standing in for. A cell that is neither a
    directory nor a filename cannot be a glob, and a silent skip is how a
    declaration disappears; this is bad input, so it is exit 2."""
    table = (f"{m.REGISTRY_HEADING}\n\n"
             "| Class | Path glob | Declared code paths | Generated regions |\n"
             "|---|---|---|---|\n"
             "| A | every deck we hand write | | |\n")
    with pytest.raises(m.AuditError, match="neither a directory nor an extension"):
        m.load_registry(table)


def test_a_settled_half_does_not_settle_the_blocking_half():
    """One clause may carry both verdicts, and the first read wins for every
    citation in it. The living sentence in 12-PR-ISSUE-TRACEABILITY.md says
    three stocks records are closed WITH the work still open in solyra; the
    solyra citation was being settled off the stocks half."""
    line = ("All three stocks records are closed as not planned with the work "
            f"still open in [solyra#28]({U.format('solyra', 28)}).")
    i = line.index("[solyra#28]")
    assert m.citation_clause(line, i, i + 11).startswith("with the work")
    assert m.cites_live_work(line, i, i + 11) is True
    states = {"solyra": {28: {"state": "closed", "reason": "completed"}}}
    assert len(m.check_closed_issues("d.md", f"# T\n\n{line}\n", states)) == 1
    # A clause carrying only ONE verdict is not re-split.
    plain = "The work is still open with no owner assigned."
    j = plain.index("open")
    # The sentence-ending period is the clause boundary, so it is not included.
    assert m.citation_clause(plain, j, j + 4) == plain[:-1]


def test_an_indented_atx_heading_closes_the_marker_window():
    """`  ## Later` renders as a heading, but a column-zero test did not close
    the window at it, so a `Last reviewed` inside that section stood in for the
    whole document's provenance -- suppressing the missing-marker finding and
    letting --stamp rewrite the section's metadata. Four spaces is code, not a
    heading, and must NOT close it."""
    lines = ["# T", "", "  ## Later", "**Last reviewed:** 2026-01-01"]
    assert m.marker_window(lines) == range(1, 2)
    assert m.find_marker(lines) is None
    code = ["# T", "", "    # Code", "**Last reviewed:** 2026-01-01"]
    assert m.marker_window(code) == range(1, 4)


def test_a_second_prose_owner_is_reported_once():
    """Two `prose:` specs on one Class A row is a contradiction the registry
    cannot express, and it is reported -- but it was reported TWICE, because
    the branch appended to `unmatched` and then fell through to the
    end-of-loop `if not hit` append. One contradiction, one finding."""
    owned, unmatched, prompt, orphans, exhaustive = m.owned_lines(
        "# T\n\nprose\n", ["prose:a.md", "prose:b.md"])
    assert unmatched == ["prose:b.md"], unmatched
    assert prompt == "a.md"
    # The same owner named twice is not a contradiction.
    assert m.owned_lines("# T\n\nprose\n", ["prose:a.md", "prose:a.md"])[1] == []


def test_an_inventory_pair_in_indented_code_is_not_a_region():
    """A four-space example of the pair was accepted as the real generated
    region, so a Class A document whose renderer-owned block had gone missing
    had its own sample suppress the unmatched-region finding. `mark:` and the
    link scanners already excluded both code constructs."""
    text = ("# T\n\nThe renderer writes:\n\n"
            "    <!-- inventory:routes:start -->\n    rows\n"
            "    <!-- inventory:routes:end -->\n")
    pairs, unbalanced = m.inventory_blocks(m.doc_lines(text))
    assert pairs == {} and unbalanced == [], (pairs, unbalanced)
    real = ("# T\n\n<!-- inventory:routes:start -->\nrows\n"
            "<!-- inventory:routes:end -->\n")
    assert m.inventory_blocks(m.doc_lines(real))[0] == {"routes": (3, 5)}


def test_a_blocker_citation_in_inline_code_is_not_a_citation():
    """Inline code renders literally, never as a live citation, so a document
    explaining what a blocker row looks like drew a gating P1 once its sample
    issue closed. Both the URL pass and the shorthand pass read `hidden`."""
    states = {"stocks": {123: {"state": "closed", "reason": "completed"}}}
    url = f"See `{U.format('stocks', 123)} is still open` as an example."
    assert m.check_closed_issues("d.md", f"# T\n\n{url}\n", states) == []
    assert m.check_closed_issues(
        "d.md", "# T\n\nStill blocked by `#123` in the example.\n", states) == []
    live = f"Blocked by {U.format('stocks', 123)}, still open."
    assert len(m.check_closed_issues("d.md", f"# T\n\n{live}\n", states)) == 1


def test_a_site_absolute_link_is_not_a_repository_path():
    """GitHub resolves a leading `/` from the HOST root. Stripping it and
    looking the result up in `tracked` answered a different question:
    `/docs/guide.md` passed because `docs/guide.md` exists although the link
    navigates to github.com/docs/guide.md, and `/settings/profile` was called
    dead. Neither verdict is available without knowing the host."""
    m.TOP_LEVEL_DIRS.update({"docs"})
    assert m.check_dead_links(
        "docs/d.md", "# T\n\n[g](/docs/guide.md)\n", {"docs/d.md"}) == []
    assert m.check_dead_links(
        "docs/d.md", "# T\n\n[s](/settings/profile)\n", {"docs/d.md"}) == []
    # A repo-relative link is still checked.
    assert [f["detail"] for f in m.check_dead_links(
        "docs/d.md", "# T\n\n[g](gone.md)\n", {"docs/d.md"})] == [
            "relative link -> gone.md"]


def test_an_unreadable_registry_is_exit_two_not_a_traceback(audit_repo):
    """Unguarded, an OSError or UnicodeDecodeError walks past the AuditError
    handler: the CLI printed a traceback and exited 1, the status it documents
    for FINDINGS, making a run that could not happen indistinguishable from
    detected drift."""
    # Committed first, so the base ref resolves and the registry read is the
    # only thing that can fail.
    _commit(audit_repo, "tree")
    (audit_repo / "docs" / "DOC_REGISTRY.md").write_bytes(b"\xff\xfe not utf-8 \xff")
    with pytest.raises(m.AuditError, match="could not be read"):
        m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
                "--issues-snapshot", str(audit_repo / "issues.json")])


def test_a_hashtag_is_not_a_heading_that_closes_the_marker_window():
    """A regression in my own indented-ATX fix: `^ {0,3}#` admits `#123
    remains open` and `####### x`, neither of which CommonMark renders as a
    heading. The window went empty, the real marker was reported missing, and
    --stamp would have inserted a second one above the hashtag."""
    tag = ["# T", "", "#123 remains open", "**Last reviewed:** 2026-01-01"]
    assert m.marker_window(tag) == range(1, 4)
    assert m.find_marker(tag)[0] == 3
    seven = ["# T", "", "####### x", "**Last reviewed:** 2026-01-01"]
    assert m.find_marker(seven)[0] == 3
    # A real heading, indented or not, still closes it.
    assert m.marker_window(["# T", "", "  ## Later", "x"]) == range(1, 2)
    assert m.marker_window(["# T", "", "#", "x"]) == range(1, 2)


def test_every_inventory_delimiter_on_a_line_is_read():
    """`break` after the first non-code match read a complete pair written on
    one line as a start with no end, and hid a duplicate or orphan sharing a
    line with a real delimiter from the balance check."""
    one_line = "# T\n\n<!-- inventory:x:start --><!-- inventory:x:end -->\n"
    pairs, unbalanced = m.inventory_blocks(m.doc_lines(one_line))
    assert pairs == {"x": (3, 3)} and unbalanced == [], (pairs, unbalanced)
    # The ordinary multi-line pair is unchanged, and an orphan still reports.
    assert m.inventory_blocks(m.doc_lines(
        "# T\n\n<!-- inventory:x:start -->\nrow\n<!-- inventory:x:end -->\n"))[0] \
        == {"x": (3, 5)}
    assert m.inventory_blocks(m.doc_lines("# T\n\n<!-- inventory:x:start -->\n"))[1] \
        == ["inventory:x starts at line 3 with no end"]


def test_a_malformed_claim_beside_a_valid_marker_blocks_stamping():
    """The refusal was conditioned on there being NO valid marker, so a
    document carrying one valid marker and a second unparseable claim was
    still writable: --stamp updated the valid one, --verify counted the target
    as consumed, and the contradiction stayed on the page."""
    both = ("# T\n\n**Last reviewed:** 2026-01-01 · **Owner:** TBD\n"
            "**Last reviewed:** 2026-1-1\n")
    assert m.stamp(both, "2026-09-18", "scanned", "abc1234")[1] \
        == "skipped-malformed-marker"
    # A clean marker still stamps, and a malformed one alone still refuses.
    clean = "# T\n\n**Last reviewed:** 2026-01-01 · **Owner:** TBD\n"
    assert m.stamp(clean, "2026-09-18", "scanned", "abc1234")[1] == "updated"
    assert m.stamp("# T\n\n**Last reviewed:** 2026-1-1\n", "2026-09-18",
                   "scanned", "abc1234")[1] == "skipped-malformed-marker"


def test_an_anchor_fragment_is_compared_case_sensitively(audit_repo):
    """A browser matches a fragment against an element id case-SENSITIVELY, so
    `#Details` does not navigate to the heading whose generated id is
    `details`. Folding the case accepted a link that does not work.

    Driven through check_dead_links, not against heading_anchors: the first
    version of this test asserted the anchor SET, which is lowercase either
    way, so it passed with the fix reverted."""
    (audit_repo / "docs" / "t.md").write_text("# Details\n\nbody\n")
    m.TOP_LEVEL_DIRS.update({"docs"})
    tracked = {"docs/d.md", "docs/t.md"}
    bad = m.check_dead_links("docs/d.md", "# D\n\n[x](t.md#Details)\n", tracked)
    assert [f["check"] for f in bad] == ["dead-anchor"], bad
    assert m.check_dead_links("docs/d.md", "# D\n\n[x](t.md#details)\n", tracked) == []


def test_an_anchored_delivery_title_excludes_a_repair_pr():
    """Only the generation regex had been anchored; the filter actually passed
    to fetch_owned_prs stayed unanchored, so a merged `Fix Monthly architecture
    doc refresh: 2026-09 authentication` entered `deliveries` while carrying no
    generation -- and superseded() then fell back to merge time."""
    rx = m.OWNING_JOB["delivery_title_re"]
    assert rx.search("Monthly architecture doc refresh: 2026-09")
    assert not rx.search("Fix Monthly architecture doc refresh: 2026-09 authentication")
    # The broad ATTEMPT pattern still matches the repair, which is its job.
    assert m.OWNING_JOB["pr_title_re"].search(
        "Fix: Monthly architecture doc refresh failed")


def test_an_extension_emptied_by_a_deletion_is_still_checkable():
    """`tracked` has staged deletions removed, so deriving the allowed suffixes
    from it alone defeated the guarantee in the case it was written for:
    deleting the last `.ipynb` took `.ipynb` out of the set and the surviving
    citations to the deleted file were skipped rather than reported."""
    m.TOP_LEVEL_DIRS.update({"docs"})
    text = "# T\n\nSee `docs/analysis.ipynb` for the workings.\n"
    # The deletion is already applied to `tracked`; the base ref still had it.
    assert m.check_dead_links("docs/d.md", text, {"docs/d.md"}) == []
    out = m.check_dead_links("docs/d.md", text, {"docs/d.md"}, None, {".ipynb"})
    assert [f["detail"] for f in out] == [
        "backticked path -> docs/analysis.ipynb"], out


_MARK = ("**Last reviewed:** 2026-01-01 · **Depth:** scanned · "
         "**Against:** `abc123def456` · **Last scanned:** 2026-02-02 · **Owner:** me")


def test_a_line_region_does_not_claim_a_code_example():
    """A Class A document that LOST its generated content but kept a matching
    sample still set `hit`, so the registry's claim of coverage survived the
    content's disappearance: no unmatched-region finding, and the example's
    lines routed to the renderer as though a job wrote them."""
    fenced = "# T\n\nprose\n\n```md\n![b](https://img.shields.io/x)\n```\n\nmore\n"
    owned, unmatched = m.owned_lines(fenced, ["line:img\\.shields\\.io"])[:2]
    assert sorted(owned) == []
    assert unmatched == ["line:img\\.shields\\.io"]
    # The fix is not "line: matches nothing": a real badge still claims its line.
    owned, unmatched = m.owned_lines(
        "# T\n\n![b](https://img.shields.io/x)\n\nmore\n",
        ["line:img\\.shields\\.io"])[:2]
    assert sorted(owned) == [3]
    assert unmatched == []


def test_a_blocker_cue_hidden_in_a_comment_does_not_arm_a_visible_citation():
    """Masking the CITATION is not enough: a hidden span can supply the cue for
    a different, visible citation. `See <url> <!-- still open -->` renders as a
    bare URL, yet the raw-line precheck read `still open` and a closed issue was
    reported as a live blocker."""
    hidden = f"See {U.format('stocks', 861)} <!-- still open -->"
    assert m.check_closed_issues("d.md", hidden, STATES) == []
    # The same line with the cue VISIBLE is still a P1 -- the fix is not
    # "never report a blocker".
    visible = f"See {U.format('stocks', 861)}, still open"
    out = m.check_closed_issues("d.md", visible, STATES)
    assert len(out) == 1 and out[0]["severity"] == "P1", out
    # And the inline-code form, which shares the `hidden` span list.
    assert m.check_closed_issues(
        "d.md", f"See {U.format('stocks', 861)} `still open`", STATES) == []
    # Masking preserves offsets, which every span computed afterwards needs.
    assert m.mask_spans("abcdef", [(1, 3)]) == "a  def"


@pytest.mark.parametrize("line,cue", [
    ("#12 is not an open issue", False),
    ("#12 is no longer an open issue", False),
    ("#12 is not a blocker", False),
    ("#12 is not yet resolved", False),
    ("#12 is an open issue", True),
    ("#12 is still open", True),
])
def test_an_article_between_the_negator_and_the_cue_still_negates(line, cue):
    """`is not an open issue` left `an` between the negator and the cue, which
    the pattern did not admit, so the positive substring read as live work and
    produced a gating P1 on text saying the exact opposite."""
    assert m.has_blocking_cue(line) is cue


def test_a_marker_indented_one_to_three_spaces_is_still_the_marker():
    """CommonMark needs a tab or four spaces for indented code; one to three
    still render as an ordinary paragraph. Treating any leading whitespace as
    an example made find_marker and marker_shaped_lines both see nothing, so
    --stamp inserted a second marker ABOVE the still-visible original.
    Parity with the Node twin (solyra#69)."""
    two = ["# T", "", "  " + _MARK, "", "Body."]
    assert m.find_marker(two) is not None
    assert m.stamp("\n".join(two), "2026-03-03", None, None)[1] == "updated"
    # Real indented code is still an example, in both recognizers.
    assert m.find_marker(["# T", "", "    " + _MARK, "", "Body."]) is None
    assert m.find_marker(["# T", "", "\t" + _MARK, "", "Body."]) is None
    assert (m.is_code_indented("    x"), m.is_code_indented("\tx"),
            m.is_code_indented("  x"), m.is_code_indented("")) == (
        True, True, False, False)
    # marker_shaped_lines carries its OWN copy of the guard, and a test that
    # drives only find_marker passes with that copy still broken: a visibly
    # rendered malformed claim has to block stamping.
    malformed = ["# T", "", "  **Last reviewed:** 2026-9-1", "", "Body."]
    assert m.marker_shaped_lines(malformed) == [2]
    assert m.stamp("\n".join(malformed), "2026-03-03", None,
                   None)[1] == "skipped-malformed-marker"
    # Indented four spaces it is an example again, and stamping proceeds.
    example = ["# T", "", "    **Last reviewed:** 2026-9-1", "", "Body."]
    assert m.marker_shaped_lines(example) == []


def test_a_c_quoted_path_is_compared_decoded():
    """git C-quotes any path with a non-ASCII byte, so `src/café.py` arrives as
    `"src/caf\\303\\251.py"` and the comparison against the decoded registry path
    matched nothing -- drift silently invisible for every non-ASCII declared
    path."""
    assert m._git_unquote('"src/caf\\303\\251.py"') == "src/café.py"
    assert m._git_unquote("src/a.py") == "src/a.py"
    assert m._touches('M\t"src/caf\\303\\251.py"', ["src/café.py"])
    # And a sibling is still not a match, so the decode did not widen anything.
    assert not m._touches("M\tsrc/other.py", ["src/café.py"])


def test_a_history_with_no_finished_run_is_refused(monkeypatch):
    """A history of only QUEUED or in-progress non-dry runs is not a dry-run
    history, so that guard is false -- but last_delivering_conclusion() yields
    None and the delivery audit passed with no completed execution behind it."""
    def rows(rs):
        return lambda cmd, **kw: "\n".join("\t".join(r) for r in rs)

    monkeypatch.setattr(m, "run", rows([["", "2026-09-20T00:00:00Z", "schedule", ""]] * 3))
    with pytest.raises(m.AuditError, match="completed delivering execution"):
        m.fetch_owning_runs(page_size=10)
    # The dry-run case is a subset and keeps its own, more specific message.
    monkeypatch.setattr(m, "run", rows(
        [["success", "2026-09-20T00:00:00Z", "workflow_dispatch", "true"]] * 2))
    with pytest.raises(m.AuditError, match="dry run"):
        m.fetch_owning_runs(page_size=10)
    # One finished delivering run is evidence, so the walk returns.
    monkeypatch.setattr(m, "run", rows([
        ["", "2026-09-20T00:00:00Z", "schedule", ""],
        ["failure", "2026-09-19T00:00:00Z", "schedule", ""]]))
    assert len(m.fetch_owning_runs(page_size=10)) == 2


def test_an_indented_generated_date_is_not_production_provenance():
    """`indented_code_lines` was missing from the freshness scan's filter, so a
    four-space example carrying a recent `Generated` date stood in for a missing
    real stamp -- the same defect as the fenced case, one syntax over."""
    def drive(doc_body, monkeypatch):
        def fake_run(cmd, **kw):
            if "runs?per_page=10" in " ".join(cmd):
                return "success\t2026-09-16T06:00:00Z\t schedule\t\n"
            return ("1200\tclosed\t2026-09-16T07:00:00Z\t2026-09-16T06:10:00Z\t"
                    "Monthly architecture doc refresh: 2026-09\n")
        monkeypatch.setattr(m, "run", fake_run)
        monkeypatch.setattr(m.pathlib.Path, "exists", lambda self: True)
        monkeypatch.setattr(m.pathlib.Path, "read_text",
                            lambda self, **kw: doc_body)
        return m.check_owning_job("2026-09-16")

    with pytest.MonkeyPatch.context() as mp:
        # No real stamp anywhere, only one inside an indented example.
        out = drive("# T\n\nprose\n\n    Generated 2026-09-16\n\nmore\n", mp)
        assert any(f["check"] == "class-a" for f in out), out
    with pytest.MonkeyPatch.context() as mp:
        # A REAL stamp is still read, so the fix is not "never find one".
        assert drive("# T\n\nGenerated 2026-09-16\n\nprose\n", mp) == []


_M29 = ("**Last reviewed:** 2026-01-01 · **Depth:** scanned · "
        "**Against:** `abc123def456` · **Last scanned:** 2026-02-02 · **Owner:** me")


def test_an_indented_code_line_is_not_a_setext_heading_in_the_marker_window():
    """An indented line followed by `---` is a code block and a thematic break.
    Omitted from the skip set, is_setext_underline read it as a heading, closed
    the window above a real marker below it, and --stamp inserted a second
    contradictory marker."""
    lines = ["# T", "", "    sample code", "---", "", _M29, "", "Body."]
    assert 5 in list(m.marker_window(lines))
    assert m.find_marker(lines) is not None
    # A REAL Setext heading still closes it, so the fix is not "never close".
    assert 5 not in list(m.marker_window(["# T", "", "Sub", "---", "", _M29, "", "B."]))


def test_a_cross_repo_url_does_not_suppress_a_shorthand_of_this_repo():
    """The dedup set was repository-blind, so a solyra URL sharing the number
    suppressed the stocks shorthand -- with stocks#123 closed and solyra#123
    open, NEITHER citation reported and a stale blocker passed the audit."""
    states = {"stocks": {123: {"state": "closed", "reason": "completed", "kind": "ISSUE"}},
              "solyra": {123: {"state": "open", "reason": "", "kind": "ISSUE"}}}
    line = ("stocks #123 is still open; "
            "https://github.com/TeneikaAskew/solyra/issues/123 is still open")
    out = m.check_closed_issues("d.md", line, states)
    assert any(f.get("ref") == "stocks#123" for f in out), out
    # A URL naming the SAME repository still dedups to one finding, which is
    # what the set exists for.
    same = "#123 is still open https://github.com/TeneikaAskew/stocks/issues/123"
    assert len(m.check_closed_issues("d.md", same, states)) == 1


def test_a_list_continuation_keeps_the_items_code_floor():
    """Resetting the floor to four on a continuation meant the next four-space
    line after a blank read as a code block, although a `- ` item needs six to
    open one -- so rendered continuation content was skipped by the dead-link
    and blocker checks."""
    # The floor governs the line AFTER the continuation, so that is what this
    # asserts -- a test on the continuation line itself passes either way,
    # because the add happens in the branch the floor already failed.
    doc = ["# T", "", "- item text", "", "    continuation", "",
           "    [x](missing.md) still in the item", ""]
    assert 6 not in m.indented_code_lines(doc), sorted(m.indented_code_lines(doc))
    # Six spaces inside the item IS code, and a plain four-space block outside
    # a list still is -- the fix is not "nothing is ever indented code".
    assert 6 in m.indented_code_lines(
        ["# T", "", "- item", "", "      cont", "", "      code", ""])
    assert 2 in m.indented_code_lines(["# T", "", "    code"])
    # And the list ENDS at an unindented line, so a four-space block after it
    # is code again.
    ended = ["# T", "", "- item", "", "back to prose", "", "    code", ""]
    assert 6 in m.indented_code_lines(ended), sorted(m.indented_code_lines(ended))


def test_a_backticked_path_may_hold_a_non_ascii_character():
    """The ASCII-only class never recognised a citation of a path spelled with
    an accent, so deleting or renaming that file produced no dead-link finding
    -- while the git inventory is deliberately decoded to preserve exactly such
    filenames."""
    hit = m.BACKTICK_PATH_RE.search("see `docs/café.md` for detail")
    assert hit and hit.group("path") == "docs/café.md"
    assert m.BACKTICK_PATH_RE.search("`docs/a.md`").group("path") == "docs/a.md"
    # Prose is still not a path: the directory part admits no spaces, so
    # `run docs/a.md and docs/b.md` does not parse as one.
    prose = m.BACKTICK_PATH_RE.search("`run docs/a.md and docs/b.md`")
    assert prose is None or prose.group("path") != "run docs/a.md and docs/b.md"


def test_the_pr_walk_continues_past_an_older_generation_delivery(monkeypatch):
    """The old stop reasoned that a later page holds only older-CREATED PRs,
    which the same delivery supersedes too. That is about time; `superseded` is
    about GENERATION. A 2026-10 attempt created BEFORE a later-created 2026-09
    delivery sits on a later page and nothing seen so far supersedes it."""
    pages = [
        "\n".join([
            "1200\tclosed\t2026-10-05T00:00:00Z\t2026-09-20T00:00:00Z\t"
            "Monthly architecture doc refresh: 2026-09",
        ] + _filler(1000, 1099)),
        "\n".join([
            "900\topen\t\t2026-09-01T00:00:00Z\t"
            "Monthly architecture doc refresh: 2026-10",
        ]),
    ]
    fake = _pr_pages(pages)
    monkeypatch.setattr(m, "run", fake)
    monkeypatch.setattr(m.pathlib.Path, "exists", lambda self: False)
    out = m.check_owning_job("2026-10-06")
    assert fake.calls["n"] > 1, "the walk stopped before the newer-generation attempt"
    assert any("#900" in f["detail"] for f in out), out


def test_the_pr_walk_still_stops_once_the_current_generation_delivered(monkeypatch):
    """The bound has to keep the cost optimisation it replaced: with this
    month's refresh merged, nothing newer can exist and one request is enough
    (CLAUDE.md §3.8)."""
    pages = ["\n".join([
        "1060\topen\t\t2026-09-01T00:00:00Z\tMonthly architecture doc refresh: 2026-09",
        "953\tclosed\t2026-09-10T22:27:07Z\t2026-08-28T06:24:17Z\t"
        "Monthly architecture doc refresh: 2026-09",
    ] + _filler(900, 998))]
    fake = _pr_pages(pages)
    monkeypatch.setattr(m, "run", fake)
    monkeypatch.setattr(m.pathlib.Path, "exists", lambda self: False)
    m.check_owning_job("2026-09-17")
    assert fake.calls["n"] == 1


def test_a_staged_directory_is_a_directory_of_this_repository(audit_repo, capsys):
    """TOP_LEVEL_DIRS came from the base commit only, so a citation of a
    missing path under a directory the change set CREATES was read as
    cross-repository prose and skipped -- the pre-commit audit passed although
    the staged tree is what says the directory belongs here."""
    # Through main(), because the widening is in main() -- a test that
    # performs the widening itself asserts nothing about the code.
    (audit_repo / "docs" / "d.md").write_text(
        "# D\n\nSee `platform/api/gone.py` for the handler.\n")
    _commit(audit_repo, "doc")
    # A STAGED addition establishing a new top-level directory.
    (audit_repo / "platform").mkdir()
    (audit_repo / "platform" / "api.py").write_text("x = 1\n")
    _git(audit_repo, "add", "platform/api.py")
    m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
            "--issues-snapshot", str(audit_repo / "issues.json")])
    report = json.loads(capsys.readouterr().out)
    dead = [f for f in report["findings"]
            if f["check"] == "dead-link" and "platform/api/gone.py" in f["detail"]]
    assert len(dead) == 1, report["findings"]


def test_verify_refuses_a_document_whose_prose_is_uncommitted(audit_repo, capsys):
    """The path existing at `head` is not enough. With staged or unstaged prose
    edits the old guard passed, `head` was recorded as the reviewed baseline,
    and the moment those edits and the marker were committed
    check_doc_changed_since diffed the document at `head` against the newly
    committed prose and reported changed-since -- invalidating the very review
    that wrote it."""
    doc = audit_repo / "docs" / "d.md"
    doc.write_text("# D\n\nOriginal prose.\n")
    _commit(audit_repo, "add d")
    # Edit the prose WITHOUT committing, then ask for a verified stamp.
    doc.write_text("# D\n\nRewritten prose the review is actually about.\n")
    with pytest.raises(m.AuditError, match="prose differs from"):
        m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
                "--issues-snapshot", str(audit_repo / "issues.json"),
                "--stamp", "--verify", "docs/d.md"])
    # Nothing was written: the refusal has to precede the write, or the
    # document carries a marker naming a baseline it does not match.
    assert "Last reviewed" not in doc.read_text()

    # Committed, the same request succeeds -- the fix is not "never verify".
    _commit(audit_repo, "edit d")
    m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
            "--issues-snapshot", str(audit_repo / "issues.json"),
            "--stamp", "--verify", "docs/d.md"])
    capsys.readouterr()
    assert "**Depth:** verified" in doc.read_text()


_U31 = "https://github.com/TeneikaAskew/stocks/issues/{}"
_ST31 = {"stocks": {1: {"state": "closed", "reason": "completed", "kind": "ISSUE"},
                    123: {"state": "closed", "reason": "completed", "kind": "ISSUE"}},
         "solyra": {}}


def test_a_hidden_settled_cue_does_not_suppress_a_visible_citation():
    """The PRECHECK was masked a round ago and the per-citation analysis was
    not, so a hidden settled cue still reached it: `<url> is still open
    <!-- resolved -->` renders as live work, passed the precheck, and was
    then suppressed by a phrase no reader can see."""
    assert len(m.check_closed_issues(
        "d.md", f"{_U31.format(1)} is still open <!-- resolved -->", _ST31)) == 1
    assert len(m.check_closed_issues(
        "d.md", f"{_U31.format(1)} is still open `resolved`", _ST31)) == 1
    # The SHORTHAND pass carries its own clause computation, and a test
    # driving only the URL pass passes with that copy still reading raw text.
    assert len(m.check_closed_issues(
        "d.md", "#1 is still open <!-- resolved -->", _ST31)) == 1
    # A VISIBLE settled cue still settles, and a plain live blocker is still
    # reported -- the fix is not "ignore settled cues". Both spellings.
    assert m.check_closed_issues(
        "d.md", f"{_U31.format(1)} was still open, now resolved", _ST31) == []
    assert m.check_closed_issues("d.md", "#1 was still open, now resolved", _ST31) == []
    assert len(m.check_closed_issues("d.md", f"{_U31.format(1)} is still open", _ST31)) == 1
    assert len(m.check_closed_issues("d.md", "#1 is still open", _ST31)) == 1


def test_a_code_span_that_crosses_a_line_break_is_still_code():
    """`code_spans` is per physical line and cannot see either delimiter of a
    span opened on one line and closed on the next, so a blocker-shaped URL or
    a link inside one was audited as live prose."""
    assert m.check_closed_issues("d.md", f"`still open {_U31.format(1)}\n`", _ST31) == []
    assert len(m.check_closed_issues("d.md", f"still open {_U31.format(1)}", _ST31)) == 1
    m.TOP_LEVEL_DIRS.update({"docs"})
    assert m.check_dead_links("docs/d.md", "# T\n\n`see\n[x](missing.md)`\n",
                              {"docs/d.md"}) == []
    assert [f["detail"] for f in m.check_dead_links(
        "docs/d.md", "# T\n\n[x](missing.md)\n", {"docs/d.md"})] == [
        "relative link -> missing.md"]
    assert m.code_span_lines(["`a", "b`"]) == {0: [(0, 2)], 1: [(0, 2)]}


def test_a_fence_delimiter_inside_a_comment_opens_nothing():
    """An unmatched ``` inside `<!-- ... -->` opened a fence, and every visible
    line after the comment was then classified as code -- dead-link, blocker,
    marker and heading checks all suppressed until another fence occurred."""
    assert m.fenced_lines(["# T", "<!--", "```", "-->", "", "[x](m.md)", "",
                           "[y](n.md)"]) == set()
    # A real fence still opens, and a comment INSIDE a fence is part of the
    # example rather than a reason to stop.
    assert m.fenced_lines(["# T", "", "```", "x", "```", ""]) == {2, 3, 4}
    assert m.fenced_lines(["```", "<!-- x -->", "```"]) == {0, 1, 2}


def test_a_line_region_does_not_match_an_inline_code_example():
    """A pattern surviving only inside inline code kept the region's claim of
    coverage alive after the real content went away, and routed the sample's
    line to the renderer as generated."""
    owned, unmatched = m.owned_lines(
        "# T\n\nExample: `https://img.shields.io/x`\n\nmore\n",
        ["line:img\\.shields\\.io"])[:2]
    assert sorted(owned) == []
    assert unmatched == ["line:img\\.shields\\.io"]
    # A real badge still claims its line.
    owned, unmatched = m.owned_lines(
        "# T\n\n![b](https://img.shields.io/x)\n\nmore\n",
        ["line:img\\.shields\\.io"])[:2]
    assert sorted(owned) == [3] and unmatched == []


def test_an_indented_code_line_offers_no_heading_anchor():
    """`    Fake` followed by `---` is a code block and a thematic break, not a
    Setext heading -- omitted from the skip set, a `fake` anchor the rendered
    document does not offer was recorded and a link to it PASSED."""
    assert sorted(m.heading_anchors("# T\n\n    Fake\n---\n")) == ["t"]
    # A real Setext heading still offers its anchor.
    assert sorted(m.heading_anchors("# T\n\nSub\n---\n")) == ["sub", "t"]


def test_a_hidden_url_does_not_dedup_a_visible_shorthand():
    """A commented URL ending in the same number suppressed the visible
    shorthand, while the URL pass skips the hidden citation too -- so a closed
    issue produced no finding from either spelling."""
    assert len(m.check_closed_issues(
        "d.md", f"#123 is still open <!-- {_U31.format(123)} -->", _ST31)) == 1
    # A VISIBLE URL still dedups to one finding, which is what the set is for.
    assert len(m.check_closed_issues(
        "d.md", f"#123 is still open {_U31.format(123)}", _ST31)) == 1


def test_a_command_that_cannot_launch_is_an_audit_error():
    """`gh` missing from PATH raises before a result exists, and that exception
    went past the AuditError handler: a traceback and exit 1, the status
    documented for FINDINGS, so automation could not tell "the audit did not
    run" from "the documentation is wrong"."""
    with pytest.raises(m.AuditError, match="could not be run"):
        m.run(["definitely-not-a-real-command-zzz", "--version"])


def test_a_link_path_with_backslash_escapes_resolves():
    """CommonMark removes the escapes when the destination renders, so
    `[x](docs/a\\(b\\).md)` resolves to the tracked `docs/a(b).md`."""
    m.TOP_LEVEL_DIRS.update({"docs"})
    assert m.check_dead_links("docs/d.md", "# T\n\n[x](a\\(b\\).md)\n",
                              {"docs/d.md", "docs/a(b).md"}) == []
    # A genuinely missing one is still dead, and a backslash before a
    # non-punctuation character is a literal character.
    assert len(m.check_dead_links("docs/d.md", "# T\n\n[x](no\\(z\\).md)\n",
                                  {"docs/d.md", "docs/a(b).md"})) == 1
    assert m.unescape_markdown("a\\qb") == "a\\qb"


def test_verify_refuses_uncommitted_declared_code(audit_repo, capsys):
    """The document matching `head` is not enough: check_changed_since reads
    committed history, so a staged change under a declared path is invisible
    to it, `head` is recorded as the baseline, and the moment that code and
    the marker are committed the next audit reports drift."""
    (audit_repo / "docs" / "d.md").write_text("# D\n\nProse.\n")
    _commit(audit_repo, "add d")
    # A declared code path with an uncommitted edit.
    (audit_repo / "scripts" / "tool.py").write_text("x = 2\n")
    with pytest.raises(m.AuditError, match="declared code path has uncommitted"):
        m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
                "--issues-snapshot", str(audit_repo / "issues.json"),
                "--stamp", "--verify", "docs/d.md"])
    assert "Last reviewed" not in (audit_repo / "docs" / "d.md").read_text()
    # Committed, the same request succeeds.
    _commit(audit_repo, "edit tool")
    m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
            "--issues-snapshot", str(audit_repo / "issues.json"),
            "--stamp", "--verify", "docs/d.md"])
    capsys.readouterr()
    assert "**Depth:** verified" in (audit_repo / "docs" / "d.md").read_text()


# ── round 33 (parity with solyra#69 `bd0126a`) ──────────────────────────────

def test_a_tracked_symlink_is_refused_on_read_not_only_when_stamping(audit_repo):
    """write_stamps refused symlinks from round 22 and the READ path did not,
    which made the refusal a property of the COMMAND rather than of the tree:
    --stamp was guarded and an ordinary read-only --check followed the link.
    Following one audits the TARGET's machine-local bytes as though they were
    committed under this path, so a clean result is one another clone does not
    reproduce -- and the read can leave the checkout entirely. Codex made the
    reproducibility argument on the Node twin; it changed the call there and
    the same hazard was live here."""
    (audit_repo / "docs" / "real.md").write_text("# Real\n\nbody\n")
    (audit_repo / "docs" / "d.md").symlink_to("real.md")
    _commit(audit_repo, "doc")
    with pytest.raises(m.AuditError, match="tracked symlink"):
        m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
                "--issues-snapshot", str(audit_repo / "issues.json")])


def test_a_symlinked_ancestor_directory_is_refused_too(audit_repo, tmp_path):
    """The final-component check reports an ordinary file here: the kernel has
    already resolved every parent before it looks at the last name. So a
    checkout that replaces a tracked DIRECTORY with a link to somewhere
    writable had both the read guard and --stamp travel straight through it --
    the temp file created and renamed on the far side, outside the repository,
    with the document-level guard passing the whole way. Codex filed this as a
    P1 on the Node twin (solyra#69); the same hole was live here."""
    outside = tmp_path.parent / "outside_docs"
    outside.mkdir()
    (outside / "d.md").write_text("# Outside\n\nuntouched\n")
    (audit_repo / "docs" / "sub").symlink_to(outside, target_is_directory=True)
    # The hole itself, asserted rather than described.
    assert not (audit_repo / "docs" / "sub" / "d.md").is_symlink()
    assert m.symlinked_component("docs/sub/d.md") == "docs/sub"
    with pytest.raises(m.AuditError, match=r"through docs/sub"):
        m.write_stamps([("docs/sub/d.md", "# X\n")])
    with pytest.raises(m.AuditError, match=r"through docs/sub"):
        m.refuse_symlink("docs/sub/d.md")
    assert (outside / "d.md").read_text() == "# Outside\n\nuntouched\n"


def test_an_ordinary_document_is_still_read(audit_repo, capsys):
    """The half that keeps the guard from being 'never read anything'."""
    (audit_repo / "docs" / "d.md").write_text("# D\n\nbody\n")
    _commit(audit_repo, "doc")
    m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
            "--issues-snapshot", str(audit_repo / "issues.json")])
    report = json.loads(capsys.readouterr().out)
    assert any(f["doc"] == "docs/d.md" for f in report["findings"]), report


# ── round 34 (Codex on 3f39d446) ────────────────────────────────────────────

def test_an_inline_generated_example_is_not_production_evidence(tmp_path, monkeypatch):
    """A third syntax for a defect already fixed twice, after the fenced and
    indented forms. A document that LOST its real footer but still shows
    `` `Generated 2026-09-20` `` as an example had the example accepted as
    evidence, so the delivery audit reported it current although readers see
    no production date in it at all.

    Driven through check_owning_job, not the comprehension: the skip set and
    the span set are computed there, and a test asserting code_spans alone
    passes with the call site still reading raw lines."""
    doc = m.OWNING_JOB["docs"][0]
    monkeypatch.setattr(m, "REPO", tmp_path)
    (tmp_path / doc).parent.mkdir(parents=True)
    monkeypatch.setattr(m, "run", lambda cmd, **k: "success\t2026-09-10T00:00:00Z\n"
                        if "runs?" in " ".join(cmd) else "")
    (tmp_path / doc).write_text(
        "# A\n\nThe footer reads `Generated 2026-09-20`.\n")
    detail = [f["detail"] for f in m.check_owning_job("2026-09-21")
              if f["doc"] == doc]
    assert any("no `Generated <date>` stamp" in d for d in detail), detail
    # A REAL stamp is still evidence -- the fix is not "never find one".
    (tmp_path / doc).write_text("# A\n\nGenerated 2026-09-20\n")
    assert [f for f in m.check_owning_job("2026-09-21")
            if f["doc"] == doc and "no `Generated" in f["detail"]] == []


def test_a_registry_cell_may_carry_an_escaped_pipe():
    """A raw `split("|")` cut `line:^(foo\\|bar)$` at the escaped pipe, so the
    region was truncated to `line:^(foo\\` and the row raised an audit error
    instead of applying the ownership rule it declares.

    Driven through load_registry, since the split is there. The second
    assertion is the one that keeps the fix narrow: these cells hold REGULAR
    EXPRESSIONS, so unescaping anything but `\\|` would silently widen them."""
    rows = m.load_registry(
        REGISTRY + r"| A | gen/x.md | lib | line:^(foo\|bar)$ |" + "\n")
    row = [r for r in rows if r["glob"] == "gen/x.md"][0]
    assert row["regions"] == [r"line:^(foo|bar)$"], row
    kept = m.load_registry(REGISTRY + r"| A | gen/y.md | lib | line:^\.env |" + "\n")
    assert [r for r in kept if r["glob"] == "gen/y.md"][0]["regions"] == [r"line:^\.env"]


def test_a_fence_opened_in_a_blockquote_closes_with_the_quote():
    """CommonMark ends a quoted code block with its container, closing fence or
    not. Holding it open classified everything after the quote as code, so the
    dead link, the heading and any marker below it were silently skipped --
    the hiding direction, which is the worse one."""
    lines = ["# T", "", "> ```", "> sample", "",
             "[guide](missing.md)", "", "## Real"]
    assert sorted(m.fenced_lines(lines)) == [2, 3]
    # An ordinary fence is untouched: it opens at depth 0 and nothing is below
    # 0, so its blank lines and its content still read as code.
    assert sorted(m.fenced_lines(
        ["# T", "```", "code", "", "more", "```", "after"])) == [1, 2, 3, 4, 5]
    # And a quoted fence that DOES close normally still closes there.
    assert sorted(m.fenced_lines(["# T", "> ```", "> s", "> ```", "> prose"])) == [1, 2, 3]


def test_an_h1_hidden_in_a_partial_comment_is_not_the_h1():
    """A comment closing partway through a heading-shaped line leaves a visible
    suffix, so commented_lines does not exclude the line while H1_RE still
    matches the hidden prefix. --stamp then inserted the marker after a heading
    no reader can see and above the document's real H1."""
    assert m.h1_index(["<!--", "# Fake --> visible", "", "# Real Title", ""]) == 3
    # The ordinary and fenced cases still behave: a change to H1 selection is
    # dangerous in both directions.
    assert m.h1_index(["# Real", "", "body"]) == 0
    assert m.h1_index(["```", "# Fake", "```", "", "# Real"]) == 4


def test_a_heading_character_reference_is_decoded_before_slugging():
    """`## AT&amp;T` renders as `AT&T`, so GitHub's id is `att`. Keeping the
    letters `amp` recorded `atampt` -- wrong in BOTH directions at once: a
    valid link to `#att` read as a dead anchor and a bogus `#atampt` was
    accepted."""
    assert sorted(m.heading_anchors("# T\n\n## AT&amp;T\n")) == ["att", "t"]
    # A bare ampersand is an ampersand: `html.unescape` alone also decodes the
    # semicolon-less legacy forms, which would eat the second T here.
    assert m.heading_slug("AT&T Corp") == "att-corp"
    # And a reference inside a code span is literal text per CommonMark, so it
    # keeps its letters.
    assert m.heading_slug("the `&amp;` operator") == "the-amp-operator"


def test_verify_refuses_a_since_baseline_that_predates_code_drift(audit_repo):
    """`--since` names an ancestor, so the worktree can be clean and the
    document identical at that revision while a declared code path has commits
    between it and the base. The marker then records a baseline the very next
    audit reports `changed-since` against, invalidating the review that just
    wrote it -- the same self-defeating stamp as the uncommitted guards,
    reached by committed rather than pending work."""
    (audit_repo / "docs" / "d.md").write_text("# D\n\nProse.\n")
    _commit(audit_repo, "add d")
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=audit_repo,
                          capture_output=True, text=True).stdout.strip()
    # A committed change under the declared path, AFTER that baseline.
    (audit_repo / "scripts" / "tool.py").write_text("x = 2\n")
    _commit(audit_repo, "edit tool")
    with pytest.raises(m.AuditError, match="commits between"):
        m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
                "--issues-snapshot", str(audit_repo / "issues.json"),
                "--since", base, "--stamp", "--verify", "docs/d.md"])
    assert "Last reviewed" not in (audit_repo / "docs" / "d.md").read_text()


# ── round 35 (Codex on 3b70d46c) ────────────────────────────────────────────

def test_a_comment_opener_inside_a_wrapped_code_span_opens_nothing():
    """The scanner masked only same-line code spans, so a literal `<!--` on the
    middle line of a VALID wrapped span read as a real opener: everything below
    was masked to the closing `-->` or to EOF, and the dead links, blocker
    citations, headings and markers in between were silently suppressed. The
    hiding direction. The content checks already used code_span_lines; this
    scanner did not."""
    lines = ["# T", "", "`opening", "x <!--", "closing`", "", "[x](missing.md)", ""]
    assert dict(m.comment_spans(lines)) == {}
    # A real inline comment is still a comment.
    assert dict(m.comment_spans(["# T", "", "text <!-- hidden -->", ""])) == {2: [(5, 20)]}


def test_an_even_run_of_backslashes_does_not_escape_a_link():
    """CommonMark counts them: in `\\\\[guide](missing.md)` the first backslash
    escapes the second and the link RENDERS, so a one-character look-back
    skipped a genuinely broken link. Parity, not presence."""
    assert len(m.check_dead_links("d.md", "# T\n\n\\\\[guide](missing.md)\n", set())) == 1
    # An odd run still escapes: the bracket is literal text and there is no link.
    assert m.check_dead_links("d.md", "# T\n\n\\[guide](missing.md)\n", set()) == []
    assert [m.is_escaped("\\[x", 1), m.is_escaped("\\\\[x", 2),
            m.is_escaped("a[x", 1)] == [True, False, False]


def test_a_setext_underline_must_share_its_headings_container():
    """`> Example` followed by an unquoted `---` ends the blockquote and renders
    a THEMATIC BREAK. Reading it as a heading closed marker_window above a real
    marker below the break, so the audit reported the marker missing and
    --stamp could insert a contradictory second one."""
    assert m.is_setext_underline(["> Example", "---"], 1) is False
    assert m.is_setext_underline(["- Example", "---"], 1) is False
    # An ordinary Setext heading is untouched, and an underline indented to a
    # list item's CONTENT column is still an underline -- this is an
    # indentation rule, not a ban on underlines near lists.
    assert m.is_setext_underline(["Title", "---"], 1) is True
    assert m.is_setext_underline(["- Example", "  ---"], 1) is True
    # The consequence, through the window rather than beside it: the marker
    # below the break is inside it.
    lines = ["# T", "", "> Example", "---", "",
             "**Last reviewed:** 2026-01-01 · **Owner:** TBD", ""]
    assert 5 in m.marker_window(lines)


def test_a_malformed_legacy_claim_is_marker_shaped():
    """`**Last Updated:** 2026-9-1` parses as neither form and was not
    marker-shaped either, so --stamp inserted a valid marker ABOVE it and the
    document visibly carried two contradictory provenance lines. The
    current-format spelling was already refused."""
    assert m._MARKER_SHAPE_RE.match("**Last Updated:** 2026-9-1")
    text, action = m.stamp("# T\n\n**Last Updated:** 2026-9-1\n\nbody\n",
                           "2026-09-22", "scanned", "abc1234", reviewed=False)
    assert action == "skipped-malformed-marker"
    assert text == "# T\n\n**Last Updated:** 2026-9-1\n\nbody\n"
    # A WELL-FORMED legacy line still stamps -- the fix is not "never rewrite
    # a legacy marker".
    assert m.stamp("# T\n\n**Last updated:** 2026-01-01\n\nbody\n",
                   "2026-09-22", "scanned", "abc1234", reviewed=False)[1] != \
        "skipped-malformed-marker"


def test_a_marker_whose_tail_holds_owned_fields_is_not_rewritten():
    """MARKER_RE is not end-anchored, so `**Depth:** VERIFIED` declines the
    optional group and pushes itself AND the valid Against / Last scanned after
    it into `rest`, where extra_segments drops every owned-looking segment. The
    scan-only rewrite then rebuilt the line without them and permanently
    deleted the reviewed-against SHA, disabling the drift checks -- while the
    audit reported the malformed marker as a P2."""
    mk = ("**Last reviewed:** 2026-01-01 · **Depth:** VERIFIED "
          "· **Against:** `abc1234` · **Last scanned:** 2026-01-01")
    text, action = m.stamp(f"# T\n\n{mk}\n\nbody\n", "2026-09-22", "scanned",
                           "def5678", reviewed=False)
    assert action == "skipped-malformed-marker"
    assert "abc1234" in text          # the SHA is still on disk
    # A well-formed marker still stamps.
    ok = ("**Last reviewed:** 2026-01-01 · **Depth:** scanned "
          "· **Against:** `abc1234` · **Last scanned:** 2026-01-01 · **Owner:** TBD")
    assert m.stamp(f"# T\n\n{ok}\n\nbody\n", "2026-09-22", "scanned", "def5678",
                   reviewed=False)[1] != "skipped-malformed-marker"


def _states():
    return {"stocks": {123: {"state": "closed", "reason": "completed"},
                       861: {"state": "closed", "reason": "completed"},
                       1: {"state": "open"}},
            "solyra": {}}


def test_a_url_in_another_clause_does_not_suppress_a_live_shorthand():
    """A repo-wide number set went far beyond deduplicating the linked form: on
    `#123 is still open; <url 123> is resolved` it suppressed the live
    shorthand because the number appeared in a SEPARATE clause, the URL pass
    then correctly skipped its own settled clause, and the contradiction
    produced no finding at all."""
    url = "https://github.com/TeneikaAskew/stocks/issues/123"
    out = m.check_closed_issues("d.md", f"#123 is still open; {url} is resolved\n",
                                _states())
    assert [f["ref"] for f in out] == ["stocks#123"]
    # The linked form is still ONE finding, not two: that is what the dedup is
    # for, and it must keep working.
    linked = "https://github.com/TeneikaAskew/stocks/issues/861"
    assert len(m.check_closed_issues("d.md", f"[#861]({linked}) is still open\n",
                                     _states())) == 1


def test_a_hidden_cue_is_not_a_prs_own_evidence():
    """With a visible cue elsewhere on the line, the line-level fallback let
    `cites_live_work` through and this PR-only guard then read the RAW clause,
    accepting a commented phrase as the PR's local evidence -- a fabricated P1
    against a PR no visible prose calls live."""
    pr = "https://github.com/TeneikaAskew/stocks/pull/937"
    st = _states()
    st["stocks"][937] = {"state": "closed", "reason": "completed"}
    assert m.check_closed_issues(
        "d.md", f"#1 is still open; {pr} <!-- is still open -->\n", st) == []
    # A VISIBLE cue in the PR's own clause still reports it.
    assert len(m.check_closed_issues(
        "d.md", f"#1 is still open; {pr} is still open\n", st)) == 1


# ── round 36 parity (solyra#69 `2cd73fa`) ──────────────────────────────────

def test_a_hash_prefixed_line_that_is_not_a_heading_keeps_the_registry_open():
    """`#123 remains open` renders as ordinary prose -- a hash run needs
    whitespace after it -- and it switched section mode off, so every
    declaration below it was silently dropped. A row that vanishes takes its
    class, its code paths and its region ownership with it, and nothing reports
    the skip. Codex found this on the Node twin."""
    head = ("## Registry\n\n| Class | Path glob | Declared code paths |\n"
            "|---|---|---|\n| D | docs/a.md | src |\n\n")
    tail = "\n| D | docs/b.md | src |\n"
    assert [r["glob"] for r in m.load_registry(head + "#123 remains open\n" + tail)] \
        == ["docs/a.md", "docs/b.md"]
    # A REAL heading still ends it, which is what the gate is for.
    assert [r["glob"] for r in m.load_registry(head + "## Examples\n" + tail)] \
        == ["docs/a.md"]


def test_indentation_mixing_spaces_and_a_tab_is_measured_in_columns():
    """A tab counted as four only in column zero, so ` \\t[x](missing.md)`
    measured 1 -- CommonMark advances the tab to column 4 and renders the line
    as code, so the link and blocker scans inspected an example as live
    prose."""
    assert [m.indent_columns(" \tx"), m.indent_columns("\tx"),
            m.indent_columns("   x")] == [4, 4, 3]
    assert m.is_code_indented(" \tx") is True
    assert sorted(m.indented_code_lines(["# T", "", " \t[x](missing.md)", ""])) == [2]
    # Three spaces is still a paragraph.
    assert m.is_code_indented("   x") is False


def test_a_quoted_h1_is_the_document_h1():
    """`> # Quoted title` RENDERS as an H1 and heading_anchors already read it
    that way, but h1_index tested the raw line -- so the document was reported
    as having no H1 while --stamp answered `skipped-no-h1`, leaving the command
    unable to repair its own finding."""
    assert m.h1_index(["> # Quoted title", "", "body"]) == 0
    # Unquoted and fenced documents are unaffected: a change to H1 selection is
    # dangerous in both directions.
    assert m.h1_index(["# Real", "", "body"]) == 0
    assert m.h1_index(["```", "> # Fake", "```", "", "# Real"]) == 4
    # And an indented H1 is a CODE BLOCK, not a heading. The counting quote
    # pattern matches the empty prefix by design, so stripping with it also ate
    # up to three leading spaces and turned `    # Indented` into the H1 -- my
    # own regression, caught by an existing test.
    assert m.h1_index(["    # Indented", "", "# Real"]) == 2
    # A quoted HEADING offers its anchor too: matching the raw line recorded
    # none, so a valid link to it was emitted as a gating dead-anchor finding.
    assert m.heading_anchors("# T\n\n> ## Quoted section\n") == {"t", "quoted-section"}


# ── round 37 (Codex on c0713ae1) ────────────────────────────────────────────

_MK37 = "**Last reviewed:** 2026-09-01 · **Owner:** TBD"


def test_a_marker_inside_a_wrapped_code_span_is_an_example():
    """A span that opens above the marker-shaped line and closes below it makes
    that line an EXAMPLE of a marker. Accepting it suppressed the
    missing-marker finding and --stamp then rewrote the example, leaving the
    document with no rendered provenance -- the same failure the fenced and
    commented exclusions beside it exist to prevent, a third hiding mechanism
    over. The content checks learned about wrapped spans a round earlier."""
    assert m.find_markers(["# T", "", "`open", _MK37, "close`", ""]) == []
    # A real marker is still found, and a fenced example is still excluded.
    assert len(m.find_markers(["# T", "", _MK37, ""])) == 1
    assert m.find_markers(["# T", "", "```", _MK37, "```", ""]) == []


def test_a_destination_character_reference_is_decoded():
    """`[t](caf&eacute;.md)` RENDERS as a link to `café.md`, and normalising
    only percent escapes and backslashes reported a tracked file dead."""
    assert m.check_dead_links("d.md", "[t](caf&eacute;.md)\n", {"café.md"}) == []
    # A destination that really is missing is still reported.
    assert len(m.check_dead_links("d.md", "[t](gone&eacute;.md)\n", {"café.md"})) == 1
    # And the fragment side, which has the same omission.
    assert m.decode_fragment("caf&eacute;") == "café"
    assert m.decode_fragment("caf%C3%A9") == "café"


def test_a_class_a_freshness_read_refuses_a_symlink(tmp_path, monkeypatch):
    """The Class A reads happen BEFORE the per-document loop, so its guard is
    not reached -- and a link to a non-terminating special file can hang or
    exhaust memory, which means it is never reached at all rather than merely
    late."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "real.md").write_text("# Real\n")
    (tmp_path / "docs" / "art.md").symlink_to("real.md")
    spec = dict(m.BEST_EFFORT_ARTIFACTS[0])
    with pytest.raises(m.AuditError, match="tracked symlink"):
        m.check_best_effort_artifacts("2026-09-22", [{**spec, "doc": "docs/art.md"}])
    # An ordinary file is still read: no exception, and it reports the missing
    # region rather than aborting.
    (tmp_path / "docs" / "art2.md").write_text("# A\n\nbody\n")
    out = m.check_best_effort_artifacts(
        "2026-09-22", [{**spec, "doc": "docs/art2.md"}])
    assert all(f["doc"] == "docs/art2.md" for f in out)


def test_a_comma_separates_two_citations_but_not_one_statement():
    """`#1 is resolved, #2 is still open` carries no contrast word, so the whole
    sentence was returned for both citations and each was settled by the first
    `resolved` it saw -- a stale live claim about #2 producing no finding.

    The narrowing is the load-bearing half: only a comma with a citation on
    EACH side splits. `#1 was still open, now resolved` is one statement about
    one citation, and splitting there invents a finding."""
    assert m.citation_clause("#1 is resolved, #2 is still open", 16, 18).strip() \
        == "#2 is still open"
    assert m.citation_clause("#1 is resolved, #2 is still open", 0, 2).strip() \
        == "#1 is resolved,"
    # One citation, a comma introducing its resolution: not a boundary.
    assert m.citation_clause("#1 was still open, now resolved", 0, 2).strip() \
        == "#1 was still open, now resolved"


def test_a_comment_inside_a_heading_is_not_part_of_its_anchor():
    """`## <!-- note --> Real` slugged to `---note----real`, so a valid link to
    `#real` was emitted as a gating dead-anchor finding AND the fabricated
    anchor was accepted -- wrong in both directions at once."""
    assert m.heading_anchors("# T\n\n## <!-- note --> Real\n") == {"t", "real"}
    # An ordinary heading is unchanged.
    assert m.heading_anchors("# T\n\n## Real\n") == {"t", "real"}


def test_an_escaped_backtick_does_not_open_a_code_span():
    """`` \\` [x](y.md) \\` `` renders two literal backticks and a LIVE link, and
    masking the range between them made the dead-link and blocker passes skip a
    real citation -- the hiding direction."""
    assert m.code_spans("\\` [guide](missing.md) \\`") == []
    # A real span still masks, and a literal backslash still opens one.
    assert m.code_spans("a `code` b") == [(2, 8)]
    assert len(m.check_dead_links("d.md", "\\` [guide](missing.md) \\`\n", set())) == 1


def test_an_indented_code_block_inside_a_blockquote_is_code():
    """The raw line has zero leading spaces because of the `>` prefix, and `>`
    alone was not seen as the blank line a code run must start after -- so the
    block never entered indented_code_lines and the link and blocker checks
    audited a rendered code example as live prose."""
    assert sorted(m.indented_code_lines(
        ["# T", ">", ">     [guide](missing.md)", ">"])) == [2]
    # Unquoted indented code still works, and quoted PROSE is not code.
    assert sorted(m.indented_code_lines(["# T", "", "    [x](y.md)", ""])) == [2]
    assert sorted(m.indented_code_lines(["# T", ">", "> ordinary prose", ">"])) == []


def test_an_inline_comment_example_opens_no_comment_for_the_fence_scan():
    """`` `<!--` `` in prose was read as a real unclosed comment, so
    fenced_lines ignored every later fence delimiter -- a heading inside the
    fenced example could then terminate marker_window before the real marker
    and --stamp inserted a second, contradictory one. comment_spans learned
    this a round ago; this standalone helper, which exists to break the
    recursion between the two, did not."""
    doc = ["# T", "", "see `<!--` here", "", "```", "# Fake", "```", "", "# Real"]
    assert sorted(m._comment_hidden(doc)) == []
    assert sorted(m.fenced_lines(doc)) == [4, 5, 6]
    # A REAL unclosed comment still hides what follows it.
    assert sorted(m._comment_hidden(["# T", "<!-- open", "still hidden"])) == [1, 2]


# ── round 38 parity (solyra#69 `a00b8b3`) ──────────────────────────────────

def test_a_character_reference_in_a_destination_is_not_split_as_a_fragment():
    """The `#` inside `&#38;` was read as the fragment separator BEFORE
    decode_char_refs ran, so `[x](foo&#38;bar.md)` -- a link to tracked
    `foo&bar.md` -- was split into the path `foo&` and the fragment `38;bar.md`
    and reported dead. A downstream decoder cannot undo a split that already
    happened, so the reference is matched as a unit in the pattern."""
    assert m.check_dead_links("d.md", "[x](foo&#38;bar.md)\n", {"foo&bar.md"}) == []
    # A destination that really is missing is still reported, and a REAL
    # fragment is still a fragment.
    assert len(m.check_dead_links("d.md", "[x](gone&#38;bar.md)\n", {"foo&bar.md"})) == 1


def test_a_quoted_setext_h1_is_the_document_h1():
    """The ATX test read the stripped copy and the Setext branch still tested
    the raw quoted lines, so `> Quoted title` over `> ====` returned None: the
    audit reported no H1 and --stamp answered `skipped-no-h1`."""
    assert m.h1_index(["> Quoted title", "> ====", "", "body"]) == 0
    assert m.h1_index(["Title", "====", "", "body"]) == 0
    # An indented H1 is a code block: the strip must not eat indentation.
    assert m.h1_index(["    # Indented", "", "# Real"]) == 2


def test_a_markdown_link_that_crosses_a_line_break_is_still_a_link():
    """CommonMark lets a label run over a newline and lets whitespace follow
    the opening parenthesis, so both shapes render as clickable links -- and a
    per-line scan can never see either. MD_LINK_RE already admitted both; what
    it never had was a subject spanning more than one physical line."""
    def run(t):
        return [f["check"] for f in m.check_dead_links("d.md", t, {"docs/a.md"})]
    assert run("[long\nlabel](missing.md)\n") == ["dead-link"]
    assert run("[x](\nmissing.md)\n") == ["dead-link"]
    # A single-line link is reported ONCE, not by both passes.
    assert run("[x](missing.md)\n") == ["dead-link"]
    # A resolving one stays quiet, and the exclusions still apply.
    assert run("[long\nlabel](docs/a.md)\n") == []
    assert run("```\n[long\nlabel](missing.md)\n```\n") == []
    assert run("`[long\nlabel](missing.md)`\n") == []


def test_stamping_refuses_an_ambiguous_classification(audit_repo):
    """check_registry_paths already reported two equally specific rows
    disagreeing, and a finding was all it did: classify still took the first by
    TABLE ORDER, so with a `D` row above a conflicting `A` row --stamp treated
    a machine-owned document as hand-written and rewrote a marker in generated
    content -- the one write this module exists to prevent."""
    reg = ("# Documentation registry\n\n## Registry\n\n"
           "| Class | Path glob | Declared code paths | Generated regions |\n"
           "|---|---|---|---|\n"
           "| D | docs/DOC_REGISTRY.md | | |\n"
           "| D | docs/tie.md | scripts | |\n"
           "| A | docs/tie.md | | all |\n")
    (audit_repo / "docs" / "DOC_REGISTRY.md").write_text(reg)
    (audit_repo / "docs" / "tie.md").write_text("# Tie\n\nProse.\n")
    _commit(audit_repo, "tie")
    with pytest.raises(m.AuditError, match="disagree about what it is"):
        m.main(["--json", "--date", "2026-09-18", "--no-owning-job-check",
                "--issues-snapshot", str(audit_repo / "issues.json"),
                "--stamp", "--verify", "docs/tie.md"])
    assert "Last reviewed" not in (audit_repo / "docs" / "tie.md").read_text()
    # The predicate itself, both ways: rows that AGREE are not ambiguous, so an
    # ordinary duplicate row does not stop a stamp.
    rows = m.load_registry(reg)
    assert m.classification_is_ambiguous("docs/tie.md", rows) is True
    assert m.classification_is_ambiguous("docs/DOC_REGISTRY.md", rows) is False


def test_an_escaped_backtick_does_not_consume_the_real_span_opener():
    """Filtering escaped openers AFTER the scan cannot recover the opener the
    rejected match already ate: the escaped tick paired with the real opener,
    the pair was discarded, and the genuine span went unmasked -- so the
    example link inside it was reported dead. Restarting one character past a
    rejected opener is what lets the real one pair."""
    line = r"\` literal ` [x](y.md) `"
    assert m.code_spans(line) == [(11, 24)]
    assert line[11:24] == "` [x](y.md) `"


def test_the_standalone_comment_scan_also_reads_wrapped_code_spans():
    """`comment_spans` learned this a round ago and `_comment_hidden`, the
    standalone scan that exists to break the recursion between the two, did
    not. It masked single-line spans only. A literal `<!--` on the
    middle line of a span that opens above it and closes below read as a real
    unclosed comment, so fenced_lines ignored every later delimiter."""
    assert m._comment_hidden(["`a", "<!--", "b`", "live"]) == set()
    # And a genuinely unclosed comment still hides what follows it.
    assert m._comment_hidden(["a", "<!--", "b"]) == {1, 2}


def test_inventory_delimiters_inside_a_wrapped_code_span_are_examples():
    """A span holding sample start/end markers across a line break had both
    read as real delimiters, so a Class A document that had LOST its real
    region looked healthy instead of producing the intended P1."""
    lines = ["`x", "<!-- inventory:a:start -->", "<!-- inventory:a:end -->", "y`"]
    assert m.inventory_blocks(lines) == ({}, [])
    # Unwrapped, the same two lines are a real region.
    real = ["<!-- inventory:a:start -->", "<!-- inventory:a:end -->"]
    pairs, unbalanced = m.inventory_blocks(real)
    assert pairs == {"a": (1, 2)} and unbalanced == []


def test_a_link_to_a_tracked_symlink_is_refused_before_its_headings_are_read(
        tmp_path, monkeypatch):
    """The preflight guards the document being SCANNED, not the ones it cites.
    Collecting a linked document's headings opened it directly, so a link to a
    tracked symlink audited the target's machine-local bytes -- and one
    pointing at a non-terminating special file hangs here."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    (tmp_path / "real.md").write_text("# Real\n")
    (tmp_path / "link.md").symlink_to("real.md")
    with pytest.raises(m.AuditError, match="tracked symlink"):
        m.check_dead_links("d.md", "see [x](link.md#real)\n", {"d.md", "link.md"})
    # A regular file is read as before.
    assert m.check_dead_links("d.md", "see [x](real.md#real)\n",
                              {"d.md", "real.md"}) == []


def test_a_quoted_setext_heading_is_read_and_a_quoted_break_is_not():
    """Both halves of one change. Matching the raw underline always failed on
    the `>`, so a quoted Setext heading exposed no anchor; comparing the
    depths on the STRIPPED copies then read 0 for every line, which accepted
    `> Example` over an unquoted `---` across a container boundary."""
    assert m.is_setext_underline(["> Title", "> ==="], 1, set()) is True
    assert m.is_setext_underline(["> Example", "---"], 1, set()) is False
    assert m.heading_anchors("> Title\n> ===\n") == {"title"}


def test_a_code_span_does_not_pair_across_a_paragraph_boundary():
    """Inline content cannot cross a blank line, so an unmatched backtick in
    one paragraph paired with another far below it -- masking every live link
    in between and silently dropping their findings."""
    assert m.code_span_lines(["a ` b", "", "c ` d"]) == {}
    # Within one paragraph it still wraps.
    assert m.code_span_lines(["a ` b", "c ` d"]) != {}


def test_an_escaped_bracket_is_label_text_not_the_label_end():
    """`[a \\] b](x.md)` renders a link; the structural class read the escaped
    `]` as the label's end, so the link never matched and a deleted target
    passed the audit."""
    mm = next(m.md_links(r"[a \] b](x.md)"), None)
    assert mm is not None and mm.group("target") == "x.md"


def test_an_escaped_hash_stays_in_the_path_and_parentheses_nest_freely():
    """Splitting on the hash before consuming the escape gave the target `a\\`.
    And a destination nests parentheses to any depth -- `docs/a(b(c(d))).md`
    is one CommonMark resolves, and a fixed-depth alternative could not match
    such a link at all, so a deleted target spelled that way produced no
    finding."""
    mm = next(m.md_links(r"[x](a\#b.md)"))
    assert mm.group("target") == r"a\#b.md" and mm.group("frag") is None
    for dest in ("docs/a(b).md", "docs/a(b(c)).md", "docs/a(b(c(d))).md"):
        assert next(m.md_links(f"[x]({dest})")).group("target") == dest
        assert [f["detail"] for f in m.check_dead_links(
            "d.md", f"# T\n\n[x]({dest})\n", {"d.md"})] == \
            [f"relative link -> {dest}"]
    # An UNBALANCED destination still ends at the first unmatched `)`, which
    # is where the rendered link ends.
    assert next(m.md_links("[x](a.md)b)")).group(0) == "[x](a.md)"


def test_inline_html_is_markup_and_an_autolink_is_not():
    """`## Hello <em>world</em>` renders as "Hello world" and GitHub's id is
    `hello-world`; keeping the tag names recorded `hello-emworldem`, so a
    valid link to `#hello-world` reported dead AND the invented fragment was
    accepted. An autolink is text, not a tag."""
    assert m.heading_slug("Hello <em>world</em>") == "hello-world"
    assert m.heading_slug('A <span class="x">tag</span>') == "a-tag"
    assert m.heading_slug("<https://example.com>") == "httpsexamplecom"


def test_the_marker_gap_is_measured_from_after_a_two_line_heading():
    """A Setext H1 is two lines. Starting the blank-run skip at the TITLE
    stopped immediately on the non-blank underline, so a document with no
    blank after `===` compared unstamped against stamped and the review read
    as stale the moment it was recorded."""
    assert m._without_marker("Title\n===\nbody\n") == \
        m._without_marker("Title\n===\n\nbody\n")


def test_an_issue_url_must_sit_at_a_host_boundary():
    """Unanchored, any site whose PATH embeds the string matched, so a link to
    example.com produced a stale-blocker finding against stocks#1. The bare
    host spelling is still accepted -- documents here write it."""
    embedded = ("Blocking issues: https://example.com/archive/"
                "github.com/TeneikaAskew/stocks/issues/861")
    assert m.check_closed_issues("d.md", embedded, STATES) == []
    bare = "Blocking issues: github.com/TeneikaAskew/stocks/issues/861"
    assert [f["ref"] for f in m.check_closed_issues("d.md", bare, STATES)] == \
        ["stocks#861"]


def test_a_section_sharing_the_registry_heading_prefix_is_not_the_registry():
    """`## Registry examples` shares the prefix, so a `startswith` test
    re-entered registry mode and parsed the illustrative table as live
    classification rules -- explanatory prose becoming configuration."""
    head = ("| Class | Path glob | Declared code paths | Generated regions |\n"
            "|---|---|---|---|\n")
    text = ("# D\n\n## Registry\n\n" + head + "| D | docs/a.md | | |\n"
            "\n## Registry examples\n\n" + head + "| A | docs/fake.md | | all |\n")
    assert [r["glob"] for r in m.load_registry(text)] == ["docs/a.md"]
    # The closing-hash spelling of the real heading still enters.
    closed = ("# D\n\n## Registry ##\n\n" + head + "| D | docs/a.md | | |\n")
    assert [r["glob"] for r in m.load_registry(closed)] == ["docs/a.md"]


def test_a_marker_hidden_in_a_partly_commented_line_is_not_provenance():
    """A comment closed PART WAY through a line leaves visible text after the
    `-->`, so the line is not wholly commented -- and stripping it put the
    hidden marker prefix first, where MARKER_RE matched it and the `-->`
    landed harmlessly in `rest`."""
    hidden = ["# T", "<!-- retired",
              "**Last reviewed:** 2026-09-20 (depth: full) --> tail"]
    assert m.find_markers(hidden) == []
    visible = ["# T", "**Last reviewed:** 2026-09-20 (depth: full)"]
    assert len(m.find_markers(visible)) == 1


def test_a_heading_inside_a_raw_html_block_offers_no_anchor():
    """`<pre>` and `<div>` make the Markdown inside render literally, so
    `# Heading` there is text. Recording its slug invented an anchor the
    document does not offer, and a link to that fragment PASSED."""
    assert m.raw_html_block_lines(["<pre>", "# Fake", "</pre>"]) == {0, 1, 2}
    assert m.heading_anchors("<pre>\n# Fake\n</pre>\n\n# Real\n") == {"real"}
    assert m.heading_anchors("<div>\n# Fake\n</div>\n\n# Real\n") == {"real"}
    # Type 7 -- an unknown tag alone on a line -- opens a block too, and both
    # type 6 and type 7 end at the next BLANK line rather than at a close tag.
    assert m.raw_html_block_lines(["<x-widget>", "# Fake", "", "# Real"]) == {0, 1}


def test_a_reference_definition_inside_a_wrapped_code_span_defines_nothing():
    """`[g]: missing.md` displayed inside a span that opens above it and closes
    below was validated as a live destination. The single-line form cannot
    match anyway -- the opening backtick sits where the pattern needs a
    bracket -- so the wrapped case is the whole of the gap."""
    assert m.check_dead_links("d.md", "`a\n[g]: missing.md\nb`\n", {"d.md"}) == []
    out = m.check_dead_links("d.md", "[g]: missing.md\n", {"d.md"})
    assert [f["check"] for f in out] == ["dead-link"]


def test_a_reference_definition_inside_a_blockquote_still_defines():
    """`> [g]: docs/g.md` renders as a working reference. The anchored pattern
    saw `>` where it needs a bracket, so every quoted definition went
    unchecked -- and a quoted use resolving to a dead path is exactly as
    broken as an unquoted one."""
    out = m.check_dead_links("d.md", "> [g]: missing.md\n", {"d.md"})
    assert [f["detail"] for f in out] == ["reference link [g] -> missing.md"]
    assert m.check_dead_links("d.md", "> [g]: ok.md\n", {"d.md", "ok.md"}) == []


def test_a_link_does_not_pair_across_a_paragraph_boundary():
    """A `[` in one paragraph and a `](missing.md)` in the next render as
    literal brackets. Scanning the whole document as one string paired them
    and reported a destination no reader can click."""
    assert m.check_dead_links("d.md", "text [label\n\nmore](missing.md)\n",
                              {"d.md"}) == []
    out = m.check_dead_links("d.md", "text [label\nmore](missing.md)\n", {"d.md"})
    assert [f["check"] for f in out] == ["dead-link"]


def test_a_query_only_destination_still_has_its_fragment_checked(
        tmp_path, monkeypatch):
    """Stripping the query empties the path, and returning there skipped the
    anchor check entirely -- so `[x](?plain=1#missing)`, which navigates
    within THIS document exactly as `#missing` does, passed."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    (tmp_path / "d.md").write_text("# Real\n\nsee [x](?plain=1#missing)\n")
    out = m.check_dead_links("d.md", (tmp_path / "d.md").read_text(), {"d.md"})
    assert [f["check"] for f in out] == ["dead-anchor"]
    (tmp_path / "e.md").write_text("# Real\n\nsee [x](?plain=1#real)\n")
    assert m.check_dead_links("e.md", (tmp_path / "e.md").read_text(),
                              {"e.md"}) == []


def test_a_fence_opened_in_a_list_item_ends_with_the_item():
    """CommonMark ends the block where the item ends, closing fence or not.
    Holding it open classified the rest of the document as code and suppressed
    every dead link, blocker, heading and marker below it."""
    unclosed = ["- item", "  ```", "  code", "", "after [x](missing.md)"]
    assert 4 not in m.fenced_lines(unclosed)
    # A blank line does NOT end the item, so indented content after one is
    # still inside the block.
    held = ["- item", "  ```", "  code", "", "  more", "  ```", "after"]
    assert m.fenced_lines(held) == {1, 2, 3, 4, 5}
    # And a legally indented TOP-LEVEL fence, whose content may sit at column
    # zero, is untouched: `_list_content_col` returns 0 and disables the rule.
    assert m.fenced_lines([" ```", "code", " ```", "after"]) == {0, 1, 2}


def test_an_internal_parent_segment_resolves_from_the_repository_root():
    """`docs/../scripts/tool.py` IS `scripts/tool.py`. It was routed through
    the document-relative branch and joined to the citing document's
    directory, so a valid citation of a tracked file was reported dead."""
    assert m.strip_dot_segments("docs/../scripts/tool.py") == "scripts/tool.py"
    assert m.repo_relative("docs/../scripts/tool.py", "docs/d.md") == \
        "scripts/tool.py"
    # A LEADING `../` is still document-relative, and one that climbs out of
    # the repository is still declined.
    assert m.repo_relative("../scripts/tool.py", "docs/d.md") == "scripts/tool.py"
    assert m.repo_relative("../../elsewhere/tool.py", "docs/d.md") is None


def test_a_link_inside_a_raw_html_block_is_not_a_link():
    """CommonMark does not parse Markdown inside an HTML block, so `<div>`
    followed by `[x](missing.md)` renders the bracket syntax LITERALLY -- and
    the destination was reported dead over a link no reader can click. Every
    kind, not only the raw-text ones."""
    assert m.check_dead_links("d.md", "<div>\n[x](missing.md)\n</div>\n", {"d.md"}) == []
    assert m.check_dead_links("d.md", "<pre>\n[x](missing.md)\n</pre>\n", {"d.md"}) == []
    # Outside one it is still a link.
    out = m.check_dead_links("d.md", "<div>\n</div>\n\n[x](missing.md)\n", {"d.md"})
    assert [f["check"] for f in out] == ["dead-link"], out


def test_a_blocker_cited_in_a_rendered_html_block_is_still_checked():
    """A `<div>` around `Blocked by <a href=".../issues/861">#861</a>` produces
    a clickable citation a reader acts on, so masking every HTML block would
    suppress a real closed blocker. Only pre/script/style/textarea -- and the
    PI/declaration/CDATA kinds the same option covers -- display their contents
    literally."""
    url = U.format("stocks", 861)
    rendered = f'<div>\nBlocking issues: <a href="{url}">#861</a>\n</div>\n'
    assert [f["ref"] for f in m.check_closed_issues("d.md", rendered, STATES)] == \
        ["stocks#861"]
    raw = f"<pre>\nBlocking issues: {url}\n</pre>\n"
    assert m.check_closed_issues("d.md", raw, STATES) == []


def test_a_case_variant_marker_field_refuses_the_stamp():
    """`check_marker_fields` carries `re.I` deliberately, so `**depth:**
    verified` is a field the reader recognises and the parser declines. A
    case-SENSITIVE refusal let --stamp keep it as extra prose AND add a
    canonical `**Depth:**` beside it: the line then carried two contradictory
    depth fields and the next audit reported the same P2 again."""
    text = ("# T\n\n**Last reviewed:** 2026-08-31 · **depth:** verified · "
            "**Owner:** TBD\n\nBody\n")
    out, action = m.stamp(text, "2026-09-18", "scanned", "abc1234")
    assert action == "skipped-malformed-marker" and out == text
    # The reader reports it, which is what asks a human to fix it.
    found = m.find_marker(m.doc_lines(text))
    assert [f["check"] for f in m.check_marker_fields("d.md", found[1])] == ["marker"]


def test_the_registry_is_refused_BEFORE_it_is_read(audit_repo, monkeypatch):
    """ORDER is the whole finding, so order is what this asserts. The
    per-document loop refuses a symlinked registry too -- it is a tracked
    document -- but it does so AFTER this read has already taken the target's
    classification and ownership rules for the whole run, and a target such as
    `/dev/zero` hangs here before that loop is ever reached. A test that only
    checked "the run refuses" passed with the early guard removed; that is what
    made this the ordering test it should have been.
    """
    trace = []
    real_refuse = m.refuse_symlink
    real_load = m.load_registry
    monkeypatch.setattr(m, "refuse_symlink",
                        lambda doc: (trace.append(("refuse", doc)), real_refuse(doc))[1])
    monkeypatch.setattr(m, "load_registry",
                        lambda text: (trace.append(("registry-loaded",)), real_load(text))[1])
    (audit_repo / "docs" / "d.md").write_text("# D\n\nBody\n")
    _audit(audit_repo)
    assert trace[0] == ("refuse", m.REGISTRY), trace[:4]
    assert trace.index(("refuse", m.REGISTRY)) < trace.index(("registry-loaded",)), trace[:4]


def test_a_symlinked_registry_is_refused(audit_repo):
    """The behaviour the ordering test above leaves implicit: a symlinked
    registry stops the run rather than supplying machine-local rules."""
    reg = audit_repo / "docs" / "DOC_REGISTRY.md"
    real = audit_repo / "docs" / "elsewhere.md"
    real.write_text(reg.read_text())
    reg.unlink()
    reg.symlink_to("elsewhere.md")
    with pytest.raises(m.AuditError, match="tracked symlink"):
        _audit(audit_repo)


def test_git_output_that_is_not_utf8_is_read_leniently(repo, monkeypatch):
    """`text=True` decodes strictly, so `git show` on a document containing
    invalid UTF-8 raised UnicodeDecodeError -- past the AuditError handler, a
    traceback and exit 1, the status documented for FINDINGS. The working-tree
    read of the same document already uses `errors="replace"`, so the two
    halves of one comparison disagreed about whether the file is readable."""
    monkeypatch.setattr(m, "REPO", repo)
    (repo / "d.md").write_bytes(b"# T\n\nCaf\xe9 body\n")
    sha = _commit(repo, "bad bytes")
    # The read itself no longer raises, and the comparison completes.
    assert "Caf" in m.run(["git", "show", f"{sha}:d.md"], cwd=repo)
    assert m.check_changed_since("d.md", sha, ["scripts"], sha, cwd=repo) == []


def test_an_unknown_review_date_cannot_carry_a_depth_or_a_baseline():
    """`Last reviewed: unknown` says no review happened; a Depth or an Against
    beside it claims one at a named baseline. Every field parses, so nothing
    reported it, and the run emitted only the non-gating P3 -- so it passed
    --check while a drift calculation ran off provenance `stamp` never writes."""
    line = ("**Last reviewed:** unknown · **Depth:** verified · "
            "**Against:** `abc1234` · **Last scanned:** 2026-09-18 · **Owner:** TBD")
    found = m.find_marker(["# T", "", line])
    out = m.check_marker_fields("d.md", found[1])
    assert [f["severity"] for f in out] == ["P2"], out
    assert "did not happen" in out[0]["detail"]
    # A real review date carrying the same fields is fine.
    ok = line.replace("unknown", "2026-08-31")
    assert m.check_marker_fields("d.md", m.find_marker(["# T", "", ok])[1]) == []


def test_yaml_front_matter_is_not_where_the_h1_lives():
    """GitHub renders front matter as a metadata table, not as Markdown, so a
    `# note` comment inside it is not a heading. Treating one as the H1 put
    --stamp's marker and its blank lines INSIDE the `---` delimiters,
    corrupting the front matter and leaving the real H1 unstamped."""
    lines = ["---", "title: x", "# note", "---", "", "# Real title", ""]
    assert sorted(m.front_matter_lines(lines)) == [0, 1, 2, 3]
    assert m.h1_index(lines) == 5
    assert m.heading_anchors("\n".join(lines)) == {"real-title"}
    # A marker-shaped line inside it is invisible to a reader too.
    assert m.find_markers(["---", "**Last reviewed:** 2026-09-20 (depth: full)",
                           "---", "", "# T"]) == []
    # An UNTERMINATED opener is a thematic break, not front matter: masking the
    # whole document would hide every finding below it.
    assert m.front_matter_lines(["---", "a", "b"]) == set()


def test_the_remaining_commonmark_html_block_types_mask_their_contents():
    """A processing instruction, a declaration and a CDATA section each run raw
    to their own closer, so Markdown inside one renders literally. None was
    recognised, and `[x](missing.md)` in such a block produced a false gating
    dead-link finding over content displayed verbatim."""
    assert m.raw_html_block_lines(["<?php", "[x](m.md)", "?>", "# Real"]) == {0, 1, 2}
    assert m.raw_html_block_lines(["<![CDATA[", "[x](m.md)", "]]>", "# Real"]) == {0, 1, 2}
    assert m.raw_html_block_lines(["<!DOCTYPE html>", "[x](m.md)"]) == {0}
    # They display their contents, so the raw-text-only callers want them too.
    assert m.raw_html_block_lines(["<?php", "x", "?>"], raw_text_only=True) == {0, 1, 2}
    assert m.raw_html_block_lines(["<div>", "x"], raw_text_only=True) == set()


def test_a_quoted_type_7_block_opens_after_a_quoted_blank_line():
    """Inside a blockquote the blank line is spelled `>`, which is nonempty
    raw -- so the interruption check saw a paragraph still open, the custom tag
    started nothing, and `[x](missing.md)` inside the block was audited as a
    live link."""
    assert m.raw_html_block_lines(
        ["> prose", ">", "> <x-widget>", "> [x](m.md)"]) == {2, 3}


def test_a_heading_introduced_by_a_list_marker_is_a_heading():
    """`- # Install` and `1. ## Setup` render real headings and GitHub exposes
    their anchors, but stripping only the blockquote prefix left the marker in
    front of the ATX syntax -- so a valid link to `#install` was a gating
    dead-anchor finding."""
    assert m.heading_anchors("- # Install\n") == {"install"}
    assert m.heading_anchors("1. ## Setup\n") == {"setup"}
    # The ATX branch only: `- Example` over a column-zero `---` ENDS the list
    # and renders a thematic break, so stripping the marker there would invent
    # a heading.
    assert m.heading_anchors("- Example\n---\n") == set()
    assert m.heading_anchors("Title\n---\n") == {"title"}


def test_a_reference_definition_may_put_its_destination_on_the_next_line():
    """`[guide]:` then `  missing.md` is a definition CommonMark resolves, and
    a per-line pattern could not capture it -- so, because reference USES are
    deliberately not scanned, the broken destination produced no finding at
    all. The finding is reported against the destination's line."""
    out = m.check_dead_links("d.md", "[guide]:\n  missing.md\n", {"d.md"})
    assert [(f["check"], f["line"]) for f in out] == [("dead-link", 2)], out
    assert m.check_dead_links("d.md", "[guide]:\n  ok.md\n", {"d.md", "ok.md"}) == []
    # A label with a BLANK line after it defines nothing.
    assert m.check_dead_links("d.md", "[g]:\n\nmissing.md\n", {"d.md"}) == []
    # And the continuation is read through the same exclusions as any line.
    assert m.check_dead_links("d.md", "`a\n[g]:\n  missing.md\nb`\n", {"d.md"}) == []


def test_a_heading_inside_a_raw_html_block_does_not_end_the_marker_window():
    """A `<div>` sample carrying `## Fake` above an existing marker closed the
    window at the sample, so the real marker below the block was reported
    missing and --stamp would insert a duplicate above it. h1_index and
    heading_anchors already excluded these."""
    doc = ["# T", "<div>", "## Fake", "</div>", "",
           "**Last reviewed:** 2026-09-20 · **Depth:** scanned · **Owner:** TBD",
           "", "## Next"]
    assert [i for i, _ in m.find_markers(doc)] == [5], m.find_markers(doc)
    assert m.find_marker(doc)[0] == 5


def test_mark_region_delimiters_inside_a_wrapped_span_are_examples():
    """A `mark:NAME` document showing `<!-- BEGIN NAME -->` and `<!-- END NAME
    -->` inside a span that opens above them and closes below had both read as
    real delimiters, so a document that had LOST its region produced no
    unmatched-region P1 and the example was classified as renderer-owned. The
    `inventory:` scanner beside it learned that a round earlier."""
    wrapped = "# A\n\n`sample:\n<!-- BEGIN X -->\nhand written\n<!-- END X -->\n`\n"
    owned, unmatched, _, _, _ = m.owned_lines(wrapped, ["mark:X"])
    assert owned == set() and unmatched == ["mark:X"], (owned, unmatched)
    real = "# A\n\n<!-- BEGIN X -->\ngenerated\n<!-- END X -->\n"
    owned2, unmatched2, _, _, _ = m.owned_lines(real, ["mark:X"])
    assert owned2 and not unmatched2, (owned2, unmatched2)


def test_a_reference_destination_is_decoded_before_its_fragment_is_split():
    """A reference definition bypasses MD_LINK_RE, so it was the one
    destination still split before escapes and character references were
    consumed: `[g]: a\\#b.md` targets the tracked `a#b.md` and was reported dead
    as `a\\`."""
    assert m.check_dead_links("d.md", "[g]: a\\#b.md\n", {"d.md", "a#b.md"}) == []
    # `&#35;` is NOT the same case, and this line used to assert it was. A
    # character reference resolves to `#` when the link is constructed, so the
    # href is `a#b.md` and the browser splits there: the destination names a
    # file called `a` with the fragment `b.md`, not a file called `a#b.md`. A
    # filename really containing a hash has to be written `a%23b.md`. Codex
    # made that argument on the Node twin (solyra#69) and it is right; the
    # expectation here encoded the older belief.
    out = m.check_dead_links("d.md", "[g]: a&#35;b.md\n", {"d.md", "a#b.md"})
    assert [f["detail"] for f in out] == ["reference link [g] -> a&#35;b.md"], out
    # The percent-encoded spelling is the one that names the file, and it is
    # still resolved -- so this is a split on the DECODED reference rather
    # than on any hash.
    assert m.check_dead_links("d.md", "[g]: a%23b.md\n", {"d.md", "a#b.md"}) == []
    # A real fragment still separates.
    out = m.check_dead_links("d.md", "[g]: gone.md#x\n", {"d.md"})
    assert [f["detail"] for f in out] == ["reference link [g] -> gone.md"], out
    assert m.split_outside_refs("a.md#frag", "#") == ("a.md", "frag")
    assert m.split_outside_refs("a\\#b.md", "#") == ("a\\#b.md", None)


def test_a_backticked_path_nested_in_a_wider_span_is_a_sample(monkeypatch):
    """``example `scripts/missing.py` here`` renders the inner backticks and
    the path literally, so reporting it failed --check over a document's own
    illustration. STRICT enclosure, because an ordinary single-backtick
    citation IS its own span -- testing mere overlap would skip every
    backticked path in the corpus."""
    monkeypatch.setattr(m, "TOP_LEVEL_DIRS", {"scripts"})
    nested = "see ``example `scripts/missing.py` here``\n"
    assert m.check_dead_links("d.md", nested, {"d.md"}) == []
    out = m.check_dead_links("d.md", "see `scripts/missing.py`\n", {"d.md"})
    assert [f["detail"] for f in out] == ["backticked path -> scripts/missing.py"], out


def test_a_rendered_html_href_is_a_destination_to_check(tmp_path, monkeypatch):
    """`<a href="...">` is a link a reader clicks, so a broken one is the same
    defect as a broken `[x](y)` -- and only Markdown syntax was scanned, so the
    audit reported clean over it. Ported from the Node twin."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    check = lambda text, tracked: [f["check"] for f in
                                   m.check_dead_links("d.md", text, tracked)]
    assert check('<a href="missing.md">g</a>\n', {"d.md"}) == ["dead-link"]
    assert check('<a href="ok.md">g</a>\n', {"d.md", "ok.md"}) == []
    # The unquoted attribute form is valid HTML and renders a real link.
    assert check("<a href=missing.md>g</a>\n", {"d.md"}) == ["dead-link"]
    # A RENDERED block still resolves its hrefs; a raw-TEXT block displays the
    # tag rather than rendering it, and a commented-out one renders nothing.
    assert check('<div>\n<a href="missing.md">g</a>\n</div>\n', {"d.md"}) == ["dead-link"]
    assert check('<pre>\n<a href="missing.md">g</a>\n</pre>\n', {"d.md"}) == []
    assert check('<div>\n<!-- <a href="missing.md">g</a> -->\n</div>\n', {"d.md"}) == []
    # And Markdown syntax in the same rendered block is still NOT parsed.
    assert check("<div>\n[x](missing.md)\n</div>\n", {"d.md"}) == []
    # An anchor whose attributes begin on the NEXT physical line renders one
    # clickable link, and a per-line scan can never see the tag and its href
    # together -- so this broken destination produced no finding at all.
    assert check('<a\n href="missing.md">g</a>\n', {"d.md"}) == ["dead-link"]
    assert check('<a\n href="ok.md">g</a>\n', {"d.md", "ok.md"}) == []
    # Reported ONCE. The single-line pass owns the single-line shape, so a
    # second report here would double the finding and the summary count.
    assert check('<a href="missing.md">g</a>\n', {"d.md"}) == ["dead-link"]
    # An escaped opener is TEXT, in this pass as in the single-line one.
    assert check('\\<a\n href="missing.md">g</a>\n', {"d.md"}) == []
    # A blank line ends the tag as it ends a paragraph, so these are two
    # fragments of prose rather than one anchor.
    assert check('<a\n\n href="missing.md">g</a>\n', {"d.md"}) == []


def test_an_escaped_link_in_a_heading_keeps_its_destination():
    """`## Literal \\[x](guide.md)` renders the brackets and the destination as
    TEXT -- CommonMark makes no link -- so GitHub's anchor includes `xguidemd`,
    while stripping the destination unconditionally recorded `literal-x`: a
    working fragment reported dead AND an anchor the page does not expose
    accepted."""
    assert m.heading_slug("Literal \\[x](guide.md)") == "literal-xguidemd"
    assert m.heading_slug("Real [x](guide.md)") == "real-x"


def test_an_issue_url_ends_where_its_number_ends():
    """`.../issues/1foo` identifies no issue, but without a trailing boundary
    the pattern captured the numeric prefix and read it as a citation of issue
    1 -- so a closed issue 1 produced a gating stale-blocker finding for a URL
    that points at nothing. A query, a fragment and punctuation ARE legitimate
    suffixes, so the boundary is "not another word character"."""
    states = {"stocks": {1: {"state": "closed", "reason": "completed",
                             "kind": "ISSUE"}}}
    blocking = "Blocking: https://github.com/TeneikaAskew/stocks/issues/1{}"
    assert m.check_closed_issues("d.md", blocking.format("foo"), states) == []
    assert m.check_closed_issues("d.md", blocking.format("-2"), states) == []
    # The real citation, and the suffixes that do not change which issue it is.
    for suffix in ("", "?x=1", "#comment", ".", ")"):
        out = m.check_closed_issues("d.md", blocking.format(suffix), states)
        assert [f["ref"] for f in out] == ["stocks#1"], (suffix, out)


def test_an_escaped_underscore_in_a_heading_survives_slugging():
    """CommonMark removes the escape and renders `## API\\_FIELD` as
    `API_FIELD`, whose GitHub id keeps the intraword underscore. The raw
    backslash sat between the letter and the `_`, so the lookbehind saw no
    word character, the underscore was stripped as emphasis and the audit
    recorded `apifield` -- a valid link to `#api_field` rejected AND a
    nonexistent `#apifield` accepted."""
    assert m.heading_slug("API\\_FIELD") == "api_field"
    assert m.heading_slug("API_FIELD") == "api_field"
    # A LEADING underscore is still emphasis syntax once unescaped, and an
    # escaped one is a literal the slug drops as punctuation either way.
    assert m.heading_slug("_Note_") == "note"


def test_a_type_7_html_block_opens_after_a_completed_block():
    """A type-7 opener may not INTERRUPT a paragraph, but it may begin right
    after a block that has ended -- `# Title` then `<x-widget>` needs no blank
    line between them. The blank-previous-line proxy missed exactly that, so
    the sample below the tag was audited as live prose."""
    assert m.raw_html_block_lines(["# Title", "<x-widget>", "[x](m.md)"]) == {1, 2}
    assert m.raw_html_block_lines(["---", "<x-widget>", "[x](m.md)"]) == {1, 2}
    # Interrupting real prose still opens nothing, which is the whole rule.
    assert m.raw_html_block_lines(["prose", "<x-widget>", "[x](m.md)"]) == set()


def test_a_reference_definition_introduced_by_a_list_marker_still_defines():
    """`- [g]: missing.md` is the first content of a list item, and CommonMark
    resolves a use of `[g]` inside that item as a clickable link. The anchored
    pattern saw the marker where it needs a bracket, so such a definition went
    unparsed -- and because reference USES are deliberately not scanned, its
    broken destination produced no finding at all."""
    for marker in ("- ", "* ", "1. ", "2) "):
        out = m.check_dead_links("d.md", f"{marker}[g]: missing.md\n", {"d.md"})
        assert [f["detail"] for f in out] == ["reference link [g] -> missing.md"], marker
    assert m.check_dead_links("d.md", "- [g]: ok.md\n", {"d.md", "ok.md"}) == []


def test_inline_content_ends_at_a_heading_not_only_at_a_blank_line():
    """A heading and a thematic break are blocks of their OWN, so inline
    content cannot span one. An unmatched backtick above `# Heading` paired
    with another below it and masked every live link in between -- none of
    those lines is blank, so the blank-line rule alone never reached it."""
    assert m.code_span_lines(["a ` b", "# H", "c ` d"]) == {}
    assert m.code_span_lines(["a ` b", "---", "c ` d"]) == {}
    # Within one paragraph the span still wraps across the line break.
    assert m.code_span_lines(["a ` b", "c ` d"]) != {}
    # And the link scan reads the same boundary: the brackets do not pair.
    assert m.check_dead_links("d.md", "text [label\n# H\nmore](missing.md)\n",
                              {"d.md"}) == []


def test_a_quoted_setext_underline_is_still_an_underline():
    """`> Title` over `> ===` is a Setext H1 and `h1_index` recognises it, but
    the anchor tested the RAW next line, saw the `>`, matched no underline and
    returned the title. `--stamp` then inserted the marker BETWEEN the title
    and its underline, destroying the H1 while reporting the stamp inserted."""
    quoted = ["> Title", "> ===", "", "> body"]
    assert m.marker_anchor(quoted) == 1
    assert m.marker_anchor(["Title", "===", "", "body"]) == 1
    # The property the index exists for: inserting AFTER it leaves an H1.
    at = m.marker_anchor(quoted)
    assert m.h1_index(quoted[:at + 1] + ["", "**marker**"] + quoted[at + 1:]) == 0
    # An underline at a DIFFERENT quote depth belongs to neither heading. This
    # once expected 0 -- `> Title` treated as a one-line H1 -- which followed
    # `h1_index` returning 0 for it. That was the defect: the quote ENDS at
    # the unquoted `===`, so the document renders no H1 at all and there is
    # nothing to anchor a marker to. `--stamp` answers `skipped-no-h1`, which
    # is the honest refusal.
    assert m.h1_index(["> Title", "===", "", "body"]) is None
    assert m.marker_anchor(["> Title", "===", "", "body"]) is None
    # A list container behaves the same way: a column-zero `===` ends the list.
    assert m.h1_index(["- Title", "===", "", "body"]) is None
    # Indented to the item's content column it is still an underline.
    assert m.h1_index(["- Title", "  ===", "", "body"]) == 0
    # An ATX H1 followed by a line of `===` does not own it: the underline
    # needs a PARAGRAPH above, and a heading is not one. Anchoring past it
    # would put the marker below a stray paragraph rather than after the H1.
    assert m.marker_anchor(["# Title", "===", "", "body"]) == 0


def test_a_line_region_reads_through_a_wrapped_code_span():
    """A `line:` pattern surviving only inside a span that opens above it and
    closes below still matched the raw line, so the region's claim of coverage
    outlived the real generated content: no unmatched-region finding, and the
    example's line routed to the renderer as though generated."""
    spec = ["line:img\\.shields\\.io"]
    owned, unmatched, _, _, _ = m.owned_lines(
        "# T\n\n`a\nhttps://img.shields.io/x\nb`\n", spec)
    assert owned == set() and unmatched == spec
    # Real generated content still matches and still counts as covered.
    owned, unmatched, _, _, _ = m.owned_lines(
        "# T\n\nhttps://img.shields.io/x\n", spec)
    assert owned == {3} and unmatched == []


def test_a_malformed_marker_inside_a_wrapped_code_span_is_an_example():
    """`find_markers` has excluded span-covered lines since it learned about
    wrapped spans; this shape check did not. A document DEMONSTRATING a
    malformed marker therefore emitted a gating finding and `stamp()` returned
    `skipped-malformed-marker`, so it could never be given a real one."""
    doc = ["# T", "`a", "**Last reviewed:** 2026-1-1", "b`", "", "## Next"]
    assert m.marker_shaped_lines(doc) == []
    # An unwrapped one is still the malformed marker this check exists for.
    live = ["# T", "", "**Last reviewed:** 2026-1-1", "", "## Next"]
    assert m.marker_shaped_lines(live) == [2]


def test_a_fence_delimiter_inside_a_raw_html_block_opens_nothing():
    """CommonMark does not parse Markdown inside an HTML block, so a literal
    ``` between `<div>` and `</div>` is displayed text. Opening on it left a
    fence that outlived the block's terminating blank line and swallowed every
    later link, blocker, heading and marker as "code"."""
    doc = ["<div>", "```", "</div>", "", "[x](missing.md)"]
    assert m.fenced_lines(doc) == set()
    assert m.raw_html_block_lines(doc) == {0, 1, 2}
    out = m.check_dead_links("d.md", "\n".join(doc) + "\n", {"d.md"})
    assert [f["check"] for f in out] == ["dead-link"]


def test_an_html_opener_inside_a_real_fence_still_opens_nothing():
    """The other direction, and the reason the fence scan runs twice rather
    than once against an HTML set computed without fences: a `<div>` inside a
    fenced EXAMPLE must not open a block, because a block there would suppress
    the next real fence and route its contents back to live prose."""
    doc = ["```text", "<div>", "```", "prose", "```py", "code", "```", "",
           "[x](missing.md)"]
    assert m.fenced_lines(doc) == {0, 1, 2, 4, 5, 6}
    out = m.check_dead_links("d.md", "\n".join(doc) + "\n", {"d.md"})
    assert [f["check"] for f in out] == ["dead-link"]
    # And the ordinary cases the two passes must leave exactly as they were.
    assert m.fenced_lines(["```", "x", "```", "y"]) == {0, 1, 2}
    assert m.fenced_lines(["~~~", "```", "~~~", "y"]) == {0, 1, 2}


def test_href_must_be_a_whole_attribute_name(monkeypatch, tmp_path):
    """`<a data-href="missing.md">` is not a clickable link, but the pattern
    matched the `href` suffix and emitted a gating dead-link finding for a
    destination no reader can reach. The same held for an `href=` written
    inside another attribute's VALUE."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    check = lambda text: [f["check"] for f in
                          m.check_dead_links("d.md", text, {"d.md"})]
    assert check('<a data-href="missing.md">x</a>\n') == []
    assert check('<a title="href=missing.md">x</a>\n') == []
    # A real href is still a real link, quoted or not, and so is one that
    # follows other attributes.
    assert check('<a href="missing.md">x</a>\n') == ["dead-link"]
    assert check("<a href=missing.md>x</a>\n") == ["dead-link"]
    assert check('<a class="c" data-x=\'1\' href="missing.md">x</a>\n') == ["dead-link"]


def test_front_matter_is_metadata_not_a_body_link():
    """GitHub renders YAML front matter as a metadata table, so
    `title: "[guide](missing.md)"` is not a link a reader can click. The link
    scan omitted the exclusion that heading discovery already applies, and
    emitted a gating finding over nothing."""
    fm = '---\ntitle: "[guide](missing.md)"\n---\n\n# T\n'
    assert m.check_dead_links("d.md", fm, {"d.md"}) == []
    # A definition in front matter defines nothing either.
    assert m.check_dead_links("d.md", "---\n[g]: missing.md\n---\n\n# T\n", {"d.md"}) == []
    # The same link in the BODY is still a real link.
    out = m.check_dead_links("d.md", "# T\n\n[guide](missing.md)\n", {"d.md"})
    assert [f["check"] for f in out] == ["dead-link"]


def test_a_generated_date_in_a_raw_text_html_example_is_not_provenance(
        tmp_path, monkeypatch):
    """A `<pre>` block displays its contents literally, so the date in it is
    sample output. Accepting it let a document that lost its real stamp report
    as current though readers see no production date in it."""
    out = _owning_doc(tmp_path, monkeypatch,
                      "# G\n\n<pre>\nGenerated 2026-09-15\n</pre>\n")
    assert [f["detail"] for f in out if "no `Generated <date>` stamp" in f["detail"]], out
    # A RENDERED block shows its text, so a stamp inside one is a stamp.
    out = _owning_doc(tmp_path, monkeypatch,
                      "# G\n\n<div>\nGenerated 2026-09-15\n</div>\n")
    assert [f for f in out if "no `Generated <date>` stamp" in f["detail"]] == [], out


def test_a_crlf_document_is_detected_past_an_eight_kilobyte_line(tmp_path):
    """A fixed 8 KiB sample of a document whose first line is longer than that
    holds no line ending at all, so a CRLF file was reported LF and
    `write_stamp` rewrote every ending in it -- the whole-file diff this
    helper exists to prevent."""
    crlf = tmp_path / "crlf.md"
    crlf.write_bytes(b"# " + b"x" * 9000 + b"\r\nbody\r\n")
    assert m.existing_newline(crlf) == "\r\n"
    lf = tmp_path / "lf.md"
    lf.write_bytes(b"# " + b"x" * 9000 + b"\nbody\n")
    assert m.existing_newline(lf) == "\n"
    # A file with no newline at all, and one that cannot be read, are both LF.
    (tmp_path / "bare.md").write_bytes(b"# Title")
    assert m.existing_newline(tmp_path / "bare.md") == "\n"
    assert m.existing_newline(tmp_path / "nope.md") == "\n"


def test_a_tab_list_marker_is_measured_in_columns():
    """CommonMark advances `-\\titem` to column 4, but counting characters said
    2 and set the nested-code floor to 6 instead of 8 -- so a six-space
    rendered paragraph after a blank line was classified as code and skipped
    by the dead-link and blocker audits. `_list_content_col` already measured
    it this way."""
    doc = ["-\titem", "", "      [x](missing.md)"]
    assert m.indented_code_lines(doc) == set()
    out = m.check_dead_links("d.md", "\n".join(doc) + "\n", {"d.md"})
    assert [f["check"] for f in out] == ["dead-link"]
    # A SPACE marker puts the floor at 6, so six spaces there really is code.
    assert m.indented_code_lines(["- item", "", "      [x](missing.md)"]) == {2}


def test_a_byte_order_mark_is_not_heading_text():
    """A BOM sits before the `#`, so `H1_RE` saw no heading: the document was
    reported as missing its marker while `--stamp` answered `skipped-no-h1`,
    the finding it raises and then refuses to act on."""
    assert m.h1_index(["﻿# Title", "", "body"]) == 0
    # Only the FIRST line carries one; a stray BOM further down is not a
    # heading marker, and the line above still wins.
    assert m.h1_index(["﻿# First", "﻿# Second"]) == 0
    assert m.h1_index(["# Plain", "", "body"]) == 0


def test_a_heading_link_destination_may_carry_parentheses():
    """`## See [x](a(b).md) now` renders as "See x now", but the pattern
    stopped at the first `)` and left `.md)` in the slug -- so a working
    fragment was reported dead while one the page does not expose was
    accepted. A scan has no depth limit to get wrong."""
    assert m.heading_slug("See [x](a(b).md) now") == "see-x-now"
    assert m.heading_slug("See [x](a(b(c)).md) now") == "see-x-now"
    # The controls from the rounds that shaped this: an ESCAPED bracket makes
    # no link, and an ordinary one still loses its destination.
    assert m.heading_slug("Literal \\[x](guide.md)") == "literal-xguidemd"
    assert m.heading_slug("Real [x](guide.md)") == "real-x"


def test_a_defined_reference_link_in_a_heading_slugs_by_its_label():
    """`## See [guide][g]` with `[g]` defined renders as "See guide", but only
    inline destinations were stripped, so the second label survived as
    `see-guideg`. Definedness is what decides it: CommonMark renders an
    UNDEFINED reference literally, and the slug keeps both labels."""
    defined = "# T\n\n## See [guide][g]\n\n[g]: guide.md\n"
    assert sorted(m.heading_anchors(defined)) == ["see-guide", "t"]
    assert sorted(m.heading_anchors("# T\n\n## See [guide][g]\n")) == \
        ["see-guideg", "t"]
    # A definition inside a fence defines nothing, so the reference stays
    # literal -- the same exclusion every other read here applies.
    fenced = "# T\n\n## See [guide][g]\n\n```\n[g]: guide.md\n```\n"
    assert sorted(m.heading_anchors(fenced)) == ["see-guideg", "t"]
    # The collapsed form names itself.
    assert m.heading_slug("See [guide][]", frozenset({"guide"})) == "see-guide"
    # A SHORTCUT reference is deliberately not resolved: bracketed prose in
    # this corpus cannot be told apart from one.
    assert m.heading_slug("See [guide]", frozenset({"guide"})) == "see-guide"


def test_a_setext_heading_opening_a_list_item_drops_its_marker():
    """`- Title` over an indented `===` is a heading `is_setext_underline`
    deliberately accepts, but the raw `- Title` reached the slug and recorded
    `--title` -- so a working `#title` fragment was reported dead while a
    `#--title` the page does not expose was accepted."""
    assert sorted(m.heading_anchors("- Title\n  ===\n")) == ["title"]
    # The case the ATX-only rule was guarding is still refused: `- Example`
    # over a column-zero `---` ends the list and renders a thematic break.
    assert m.heading_anchors("- Example\n---\n") == set()
    assert sorted(m.heading_anchors("Title\n===\n")) == ["title"]


def test_the_github_host_boundary_belongs_to_the_url_scheme():
    """Any double slash satisfied the lookbehind, so a URL whose host is
    example.com read as a citation of stocks#1 and a closed issue 1 produced
    a gating stale-blocker finding for it."""
    states = {"stocks": {1: {"state": "closed", "reason": "completed",
                             "kind": "ISSUE"}}}
    ref = lambda line: [f["ref"] for f in m.check_closed_issues("d.md", line, states)]
    assert ref("Blocked by https://example.com//github.com/TeneikaAskew/stocks/issues/1") == []
    # The real URL, and the bare-host spelling this repo's docs use.
    assert ref("Blocked by https://github.com/TeneikaAskew/stocks/issues/1") == ["stocks#1"]
    assert ref("Blocked by github.com/TeneikaAskew/stocks/issues/1") == ["stocks#1"]


def test_two_leading_dots_are_traversal_only_as_a_parent_component():
    """`..missing.md` is a legal repository filename that normalises to
    itself, and treating it as traversal meant a deleted or misspelled
    dot-prefixed target was never reported at all."""
    out = m.check_dead_links("d.md", "[x](..missing.md)\n", {"d.md"})
    assert [f["check"] for f in out] == ["dead-link"]
    # A real parent component still leaves the repository and is exempt.
    assert m.check_dead_links("d.md", "[x](../outside.md)\n", {"d.md"}) == []
    # And a tracked dot-prefixed file is not a finding.
    assert m.check_dead_links("d.md", "[x](..missing.md)\n",
                              {"d.md", "..missing.md"}) == []


def test_every_kind_of_heading_whitespace_becomes_a_hyphen():
    """`## Hello<TAB>World` anchors as `hello-world` on GitHub, but only the
    literal space was hyphenated -- so a valid `#hello-world` link was a
    gating dead anchor while the tab-bearing slug was accepted."""
    assert m.heading_slug("Hello\tWorld") == "hello-world"
    assert m.heading_slug("Hello World") == "hello-world"


def test_a_raw_html_block_ends_with_its_blockquote():
    """CommonMark ends a nested block where its container ends, so `> <pre>`
    is closed by the quote whether or not a `</pre>` ever arrives. Holding it
    open added every later line to the block, so the dead-link, heading,
    marker and blocker scans suppressed live body content to the end of the
    document. The fence scanner has had this rule for rounds."""
    doc = ["> <pre>", "> sample", "", "[x](missing.md)"]
    assert m.raw_html_block_lines(doc) == {0, 1}
    out = m.check_dead_links("d.md", "\n".join(doc) + "\n", {"d.md"})
    assert [f["check"] for f in out] == ["dead-link"]
    # An UNQUOTED block opens at depth 0 and nothing is below 0, so it still
    # runs to its closing tag across blank lines.
    assert m.raw_html_block_lines(["<pre>", "a", "", "b", "</pre>"]) == {0, 1, 2, 3, 4}


def test_inline_content_ends_at_a_container_boundary():
    """A new list item opens its own paragraph, and so does a change of
    blockquote depth. Grouping them into one block paired delimiters across
    the boundary: `- [open` over `- label](missing.md)` became a link no
    reader can click, and a stray backtick masked a live one."""
    assert m._paragraph_blocks(["- [open", "- label](missing.md)"], set()) == \
        [(0, 0), (1, 1)]
    assert m.check_dead_links("d.md", "- [open\n- label](missing.md)\n", {"d.md"}) == []
    # The masking direction: a backtick before the item no longer swallows it.
    out = m.check_dead_links("d.md", "a ` b\n- [x](missing.md) `\n", {"d.md"})
    assert [f["check"] for f in out] == ["dead-link"]
    # A quote-depth change splits too.
    assert m._paragraph_blocks(["> a ` b", "c ` d"], set()) == [(0, 0), (1, 1)]
    # A CONTINUATION of an item carries no marker and stays in its block.
    assert m._paragraph_blocks(["- one", "  two"], set()) == [(0, 1)]


def test_a_reference_definition_needs_no_space_after_its_colon(monkeypatch, tmp_path):
    """CommonMark registers `[g]:missing.md` and resolves `[x][g]` against it,
    but `\\s+` skipped the definition -- and because reference USES are
    deliberately not scanned, its broken destination produced no finding."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    check = lambda text: [f["check"] for f in
                          m.check_dead_links("d.md", text, {"d.md"})]
    assert check("[g]:missing.md\n") == ["dead-link"]
    assert check("[g]: missing.md\n") == ["dead-link"]
    # A colon with NOTHING after it is still the two-line head form, not a
    # definition in its own right.
    assert check("[g]:\n\nmissing.md\n") == []


def test_an_escaped_html_anchor_is_literal_text(monkeypatch, tmp_path):
    """`\\<a href="missing.md">` escapes the `<`, so CommonMark renders the tag
    as text and there is no clickable link. The Markdown pass has applied this
    check for rounds; the href pass did not, so the same escape produced a
    gating finding there."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    check = lambda text: [f["check"] for f in
                          m.check_dead_links("d.md", text, {"d.md"})]
    assert check('\\<a href="missing.md">x</a>\n') == []
    assert check('<a href="missing.md">x</a>\n') == ["dead-link"]


def test_a_fence_openers_indentation_is_measured_in_columns():
    """CommonMark expands a tab to four columns, so `\\t```` is an indented
    code line rather than a fence opener. Counting the tab as one of three
    allowed characters opened a false fence that held across live paragraphs
    and suppressed their findings."""
    # The tab line opens nothing; the column-zero fence on line 2 opens one
    # that runs to the end of the document, which is line 2 alone.
    assert m.fenced_lines(["\t```", "x", "```"]) == {2}
    # Three SPACES are still a legal opener, and four are indented code.
    assert m.fenced_lines(["   ```", "x", "```"]) == {0, 1, 2}
    assert m.fenced_lines(["    ```", "x", "```"]) == {2}


def test_an_angle_bracket_destination_may_not_span_lines():
    """`<...>` may hold a space, which is why an author reaches for it, but
    CommonMark forbids a line ending there -- so `[x](<missing\\n.md>)` is
    literal text. The multiline pass matched it and reported a destination
    over something no reader can click."""
    assert m.check_dead_links("d.md", "[x](<missing\n.md>)\n", {"d.md"}) == []
    # On ONE line the space is still allowed, which is the form this exists for.
    out = m.check_dead_links("d.md", "[x](<my missing.md>)\n", {"d.md"})
    assert [f["check"] for f in out] == ["dead-link"]


def test_front_matter_delimiters_sit_at_column_zero():
    """An indented `---` is a thematic break, not a front-matter opener, but
    trimming the line accepted it -- so every line to the next indented `---`
    was excluded as metadata and a rendered link between them passed."""
    assert m.front_matter_lines(["  ---", "[x](missing.md)", "  ---"]) == set()
    out = m.check_dead_links("d.md", "  ---\n[x](missing.md)\n  ---\n", {"d.md"})
    assert [f["check"] for f in out] == ["dead-link"]
    # A real opener at column zero still delimits metadata.
    assert m.front_matter_lines(["---", "a: 1", "---"]) == {0, 1, 2}


def test_a_heading_tag_may_quote_a_greater_than_sign():
    """`[^<>]*` stopped at the `>` inside `data-x="a>b"` and left `b">` to be
    slugged as visible text, so the heading recorded `bhello` -- the valid
    fragment rejected and one the page does not expose accepted."""
    assert m.heading_slug('<span data-x="a>b">Hello</span>') == "hello"
    assert m.heading_slug("Hello <em>world</em>") == "hello-world"
    # An AUTOLINK is text, not a tag, and must survive -- the control from the
    # round that shaped this strip.
    assert m.heading_slug("<https://example.com>") != ""


def test_a_heading_reference_label_is_keyed_like_a_definition():
    """CommonMark collapses internal whitespace when matching labels, so
    `[guide][my   ref]` resolves against `[my ref]:`. Normalising only the
    DEFINITIONS left the use unmatched, so the reference stayed literal
    bracket syntax and slugged as `see-guidemy---ref` -- a working fragment
    reported dead and one the page does not expose accepted."""
    doc = "# T\n\n## See [guide][my   ref]\n\n[my ref]: guide.md\n"
    assert sorted(m.heading_anchors(doc)) == ["see-guide", "t"]
    # Both sides go through the same key, so the exact spelling still works
    # and an UNDEFINED label is still left literal.
    assert sorted(m.heading_anchors("# T\n\n## See [guide][g]\n\n[g]: guide.md\n")) == \
        ["see-guide", "t"]
    assert sorted(m.heading_anchors("# T\n\n## See [guide][g]\n")) == \
        ["see-guideg", "t"]
    assert m._ref_key("  Foo   BAR ") == "foo bar"


def test_a_heading_code_span_keeps_its_contents_literal():
    """A code span renders its contents LITERALLY, so link and tag syntax
    inside one is text. Unwrapping the span before the markup passes handed
    `` `[x](y)` `` to the link stripper, which discarded the destination and
    recorded `x` where GitHub exposes `xy`."""
    assert m.heading_slug("`[x](y)`") == "xy"
    # The RUN form is one span too; a single-backtick pattern saw none at all.
    assert m.heading_slug("``[x](missing.md)``") == "xmissingmd"
    # Outside a span all three passes still apply, which is the whole point of
    # doing them per part rather than dropping them.
    assert m.heading_slug("Real [x](guide.md)") == "real-x"
    assert m.heading_slug("Hello <em>world</em>") == "hello-world"
    assert sorted(m.heading_anchors("# T\n\n## AT&amp;T\n")) == ["att", "t"]


def test_an_h1_introduced_by_a_list_marker_is_the_h1():
    """`- # Title` renders a real H1 and `heading_anchors` has read it that way
    for rounds, but this tested the unstripped line -- so the audit reported
    the marker missing while `--stamp` answered `skipped-no-h1` and could not
    repair its own finding."""
    assert m.h1_index(["- # Title", "", "body"]) == 0
    assert m.h1_index(["1. # Title", "", "body"]) == 0
    assert m.h1_index(["# Title", "", "body"]) == 0
    # A list item that is NOT a heading is still not one.
    assert m.h1_index(["- item", "", "body"]) is None


def test_a_heading_reference_definition_must_open_a_block():
    """`paragraph` then `[g]: x.md` renders literally -- CommonMark registers
    no reference there -- so collecting it let `## [Guide][g]` resolve to
    `guide` when the page actually exposes `guideg`. The dead-link scan's own
    collector is the other half of the rule and got the same test a round
    later."""
    interrupted = "paragraph\n[g]: README.md\n\n## [Guide][g]\n"
    assert sorted(m.heading_anchors(interrupted)) == ["guideg"]
    # A definition that DOES open a block still defines, colon space or not.
    assert sorted(m.heading_anchors("# T\n\n[g]: README.md\n\n## [Guide][g]\n")) == \
        ["guide", "t"]
    assert sorted(m.heading_anchors("# T\n\n[g]:README.md\n\n## [Guide][g]\n")) == \
        ["guide", "t"]


def test_every_reference_label_goes_through_one_key():
    """The dead-link definition map was the THIRD place keying a label its own
    way, so `[my ref]` and `[my   ref]` were stored as two definitions and the
    second -- which CommonMark never resolves, the first wins -- was validated
    and reported dead. Found by sweeping for the pattern rather than waiting
    for it to be reported a third time."""
    out = m.check_dead_links("d.md", "[my ref]: ok.md\n\n[my   ref]: missing.md\n",
                             {"d.md", "ok.md"})
    assert out == []
    # Genuinely distinct labels are still both checked.
    out = m.check_dead_links("d.md", "[a]: ok.md\n\n[b]: missing.md\n",
                             {"d.md", "ok.md"})
    assert [f["check"] for f in out] == ["dead-link"]


def test_a_front_matter_closing_delimiter_sits_at_column_zero():
    """An indented `---` is not a delimiter, but `strip()` accepted one -- so
    everything through that line was masked as metadata and a rendered link,
    heading or marker inside the span was silently excluded. The OPENER has
    required column zero since it was raised; the closer did not."""
    assert m.front_matter_lines(["---", "a: 1", "  ---", "[x](missing.md)"]) == set()
    out = m.check_dead_links(
        "d.md", "---\na: 1\n  ---\n[x](missing.md)\n", {"d.md"})
    assert [f["check"] for f in out] == ["dead-link"]
    # A real closer at column zero, in both spellings, still delimits.
    assert m.front_matter_lines(["---", "a: 1", "---"]) == {0, 1, 2}
    assert m.front_matter_lines(["---", "a: 1", "..."]) == {0, 1, 2}


def test_a_setext_heading_is_its_whole_paragraph():
    """`Hello` over `world` over `---` renders ONE heading anchored
    `hello-world`. Slugging the final line alone recorded `world`, so the real
    fragment was reported dead and one the page does not expose accepted."""
    assert sorted(m.heading_anchors("Hello\nworld\n---\n")) == ["hello-world"]
    # The single-line forms this grew out of are unchanged.
    assert sorted(m.heading_anchors("Title\n===\n")) == ["title"]
    assert sorted(m.heading_anchors("- Title\n  ===\n")) == ["title"]
    assert sorted(m.heading_anchors("# T\n\n## Sub\n")) == ["sub", "t"]


def test_a_dead_link_definition_must_open_a_block_too():
    """CommonMark does not let a definition interrupt a paragraph, so
    `paragraph` over `[g]: missing.md` renders as prose and registers no
    reference. This loop validated it anyway and emitted a gating dead-link
    finding for text that produces no link. `heading_anchors` had the rule;
    its other half did not."""
    assert m.check_dead_links(
        "d.md", "# T\n\nparagraph\n[g]: missing.md\n", {"d.md"}) == []
    # A definition that DOES open a block is still checked, in every container.
    for text in ("# T\n\n[g]: missing.md\n",
                 "# T\n\n> [g]: missing.md\n",
                 "# T\n\n- [g]: missing.md\n"):
        assert [f["check"] for f in m.check_dead_links("d.md", text, {"d.md"})] \
            == ["dead-link"], text
    # Consecutive definitions are one run: the second opens off the first.
    out = m.check_dead_links("d.md", "# T\n\n[a]: m1.md\n[b]: m2.md\n", {"d.md"})
    assert [f["line"] for f in out] == [3, 4]
    # And the two-line form opens the line after its DESTINATION, not its label.
    out = m.check_dead_links("d.md", "# T\n\n[a]:\n  m1.md\n[b]: m2.md\n", {"d.md"})
    assert [f["line"] for f in out] == [4, 5]


def test_a_raw_html_block_opens_through_a_list_marker():
    """`- <pre>` opens a raw-text block whose contents display literally, so
    the `[x](missing.md)` inside it is an EXAMPLE. Stripping only blockquotes
    left the opener unrecognised and produced a gating dead-link finding for a
    link no reader can click."""
    assert m.raw_html_block_lines(
        ["- <pre>", "  [x](missing.md)", "  </pre>"]) == {0, 1, 2}
    assert m.check_dead_links(
        "d.md", "# T\n\n- <pre>\n  [x](missing.md)\n  </pre>\n", {"d.md"}) == []
    # The containers it already handled are unchanged.
    assert m.raw_html_block_lines(["<pre>", "x", "</pre>"]) == {0, 1, 2}
    assert m.raw_html_block_lines(["> <pre>", "> x", "> </pre>"]) == {0, 1, 2}


def test_a_fence_opens_directly_after_a_list_marker():
    """CommonMark strips the list container before parsing the fence, so
    `- ```' opens one. Matching the physical line missed the opener and then
    read the indented CLOSING delimiter as a new one -- the example's headings
    were indexed as real anchors and --stamp could aim at one."""
    assert m.fenced_lines(["- ```", "  # Example", "  ```", ""]) == {0, 1, 2}
    assert m.heading_anchors("# Real\n\n- ```\n  # Example\n  ```\n") == {"real"}
    # The item ends the fence, closing delimiter or not.
    assert m.fenced_lines(["- ```", "  x", "next"]) == {0, 1}
    # A fence on a LATER line of an item sits at the item's content column.
    assert m.fenced_lines(["- item", "", "  ```", "  x", "  ```", ""]) == {2, 3, 4}
    # Four columns with no container is still an indented code line, not a
    # fence -- opening on one masks every finding below it.
    assert m.fenced_lines(["    ```", "x", "```"]) == {2}
    assert m.fenced_lines(["\t```", "x", "```"]) == {2}


def test_an_escaped_comment_opener_opens_no_comment():
    """`\\<!--` displays the delimiter literally and leaves the rest of the
    line live Markdown. Reading it as a real comment masked content through
    `-->` or to EOF, suppressing the dead-link, blocker, heading and marker
    findings in between."""
    assert m.comment_spans([r"\<!-- [x](missing.md)"]) == {}
    assert m._comment_hidden([r"\<!--", "a"]) == set()
    assert [f["check"] for f in m.check_dead_links(
        "d.md", "# T\n\n\\<!-- [x](missing.md)\n", {"d.md"})] == ["dead-link"]
    # A real opener still opens, and PARITY still decides: `\\\\<!--` is a
    # literal backslash followed by a live comment.
    assert m.comment_spans(["<!-- [x](missing.md)"]) == {0: [(0, 20)]}
    assert m.comment_spans([r"\\<!-- x"]) == {0: [(2, 8)]}
    # Through `fenced_lines`, which reads the standalone copy of this scan
    # in `_comment_hidden`: a false comment there swallows every later fence
    # delimiter, so the example below it is audited as live content.
    assert m.fenced_lines([r"\<!--", "```", "x", "```"]) == {1, 2, 3}
    assert m.fenced_lines(["<!--", "```", "x", "```"]) == set()


def test_an_escaped_angle_bracket_is_reference_destination_content():
    """`[g]: <a\\>b.md>` resolves to `a>b.md`. `[^>]*` stopped at the escaped
    `>`, captured `<a\\>` and reported a tracked file dead."""
    assert m.REF_DEF_RE.match(r"[g]: <a\>b.md>").group("target") == r"<a\>b.md>"
    assert m.REF_DEF_CONT_RE.match(r"  <a\>b.md>").group("target") == r"<a\>b.md>"
    assert m.check_dead_links(
        "d.md", "# T\n\n[g]: <a\\>b.md>\n", {"d.md", "a>b.md"}) == []
    # The forms it already accepted are unchanged.
    assert m.REF_DEF_RE.match("[g]: <a b.md>").group("target") == "<a b.md>"
    assert m.REF_DEF_RE.match("[g]: plain.md").group("target") == "plain.md"


def test_a_uri_scheme_is_read_off_the_rendered_destination():
    """`[x](https&#58;//example.com)` renders as an ordinary HTTPS link. The
    scheme test ran on the encoded spelling, so the audit resolved it as a
    repository-relative path and emitted a gating dead-link finding for a file
    no one meant to exist locally."""
    assert m.check_dead_links(
        "d.md", "# T\n\n[x](https&#58;//example.com)\n", {"d.md"}) == []
    assert m.check_dead_links(
        "d.md", "# T\n\n[x](https\\://example.com)\n", {"d.md"}) == []
    # A genuinely relative destination is still resolved and still checked.
    assert [f["check"] for f in m.check_dead_links(
        "d.md", "# T\n\n[x](missing.md)\n", {"d.md"})] == ["dead-link"]


def test_a_setext_underline_ends_the_inline_parsing_block():
    """An unmatched backtick in a multiline Setext heading paired with one in
    the paragraph BELOW the underline, and code_span_lines masked a live
    `[x](missing.md)` between them out of the audit."""
    lines = ["Head `a", "====", "[x](missing.md) `b"]
    assert m._paragraph_blocks(lines, frozenset()) == [(0, 1), (2, 2)]
    # A thematic break needs a blank line above it to BE one: `a` over `---`
    # is a Setext H2, so the heading and its underline are ONE block.
    assert m._paragraph_blocks(["a", "", "---", "b"], frozenset()) == \
        [(0, 0), (2, 2), (3, 3)]
    assert m._paragraph_blocks(["a", "---", "b"], frozenset()) == [(0, 1), (2, 2)]
    assert m.code_span_lines(lines) == {}
    assert [f["check"] for f in m.check_dead_links(
        "d.md", "Head `a\n====\n[x](missing.md) `b\n", {"d.md"})] == ["dead-link"]
    # The heading itself is still its whole paragraph.
    assert m.heading_anchors("Head\nTwo\n===\n\npara\n") == {"head-two"}
    assert m.heading_anchors("Head Two\n---\n") == {"head-two"}


def test_a_case_variant_owner_is_read_rather_than_duplicated():
    """`**owner:** Alice` is a field every reader recognises. Reading it
    case-sensitively returned None, the variant was kept as free text, and
    --stamp wrote a canonical `**Owner:** TBD` beside it -- one line asserting
    two different owners, reported as updated."""
    line = "**Last reviewed:** 2026-01-01 · **owner:** Alice"
    assert m.owner_of(["# T", "", line], 2) == "Alice"
    assert m.extra_segments(line) == []
    out, _ = m.stamp("# T\n\n" + line + "\n\nBody.\n",
                     "2026-09-22", "scanned", "abc1234")
    assert "**Owner:** Alice" in out
    assert "**Owner:** TBD" not in out
    assert out.count("wner:**") == 1
    # The canonical spelling still reads.
    assert m.owner_of(["**Owner:** Bob"], 0) == "Bob"


def test_the_document_h1_is_not_one_displayed_inside_raw_html():
    """`<pre>` displays `# Example` literally, so GitHub renders no heading
    there -- taking one as the H1 put the provenance marker INSIDE the block,
    where nothing renders it, and a later audit could accept that misplaced
    marker. heading_anchors and marker_window excluded these; this did not."""
    assert m.h1_index(["<pre>", "# Example", "</pre>", "", "# Real"]) == 4
    # The exclusions it already had are unchanged, and an ordinary H1 still
    # wins from line zero.
    assert m.h1_index(["```", "# Example", "```", "", "# Real"]) == 4
    assert m.h1_index(["# Real", "", "body"]) == 0


def test_an_explicit_html_anchor_is_a_destination_the_page_offers():
    """`<a name="legacy"></a>` and any `id="..."` are rendered destinations a
    browser honours, so `[x](#legacy)` is valid with no heading of that name.
    Indexing only heading slugs made the dead-anchor check reject it."""
    assert m.heading_anchors('<a name="custom"></a>\n\n# T\n') == {"custom", "t"}
    # The unquoted attribute form is valid HTML and the browser exposes it.
    assert m.html_anchors(["<div id=section>"]) == {"section"}
    # Tokenised as real attributes, not searched for as text. `id=` inside
    # ANOTHER attribute's value invented an anchor a link could then resolve
    # against, and a `>` inside a quoted value hid a real one.
    assert m.html_anchors(['<div data-note=" id=fake">']) == set()
    assert m.html_anchors(["<div title=' id=\"fake\"'>"]) == set()
    assert m.html_anchors(['<div title="a > b" id="section">']) == {"section"}
    # `id` names a destination on any element; `name` only on an anchor.
    assert m.html_anchors(['<meta name="viewport">']) == set()
    assert m.html_anchors(['<a name="legacy">']) == {"legacy"}
    # Case is PRESERVED: a browser matches an explicit id exactly.
    assert m.html_anchors(['<a name="Install">']) == {"Install"}
    # And an attribute on a LATER physical line, which no per-line scan sees.
    assert m.html_anchors(["<div", '  id="section">']) == {"section"}
    # Character references are decoded, as a heading slug already decodes them.
    assert m.html_anchors(['<div id="a&amp;b">']) == {"a&b"}
    # An anchor a reader cannot see is not a destination: raw-text blocks,
    # comment spans and code spans each hide one.
    assert m.html_anchors(["<pre>", '<a id="fake"></a>', "</pre>"]) == set()
    assert m.html_anchors(['text <!-- <a id="fake"></a> -->']) == set()
    assert m.html_anchors(['see `<a id="fake">`']) == set()
    # And an ESCAPED opener is not an element. `\\<div id="fake">` renders the
    # `<` literally, so there is no element and `#fake` reaches nothing -- but
    # the tokeniser parsed it like any other tag and registered the id, which
    # is how a link to a destination the document does not offer PASSED. A doc
    # demonstrating tag syntax escapes it exactly this way.
    assert m.html_anchors(['\\<div id="fake">']) == set()
    assert m.html_anchors(['\\\\<div id="real">']) == {"real"}


def test_a_heading_label_reads_the_two_line_definition_form():
    """`[g]:` over `  guide.md` defines `g`, so `## See [guide][g]` renders
    anchored `see-guide`. Reading only the single-line form recorded
    `see-guideg` and reported a working fragment link dead -- the dead-link
    pass has read both forms since it was raised."""
    assert m.heading_anchors("[g]:\n  guide.md\n\n## See [guide][g]\n") == \
        {"see-guide"}
    # The single-line form is unchanged, and an UNDEFINED label still keeps
    # both halves in the slug, which is how CommonMark renders it.
    assert m.heading_anchors("[g]: guide.md\n\n## See [guide][g]\n") == \
        {"see-guide"}
    assert m.heading_anchors("## See [guide][g]\n") == {"see-guideg"}


def test_a_code_span_renders_without_its_boundary_spaces():
    """CommonMark strips ONE leading and trailing space when a span's content
    begins and ends with one, so ``## A ` foo ` B`` anchors `a-foo-b`.
    Appending the raw capture recorded `a--foo--b` -- a working fragment
    rejected and one GitHub does not expose accepted."""
    assert m.heading_slug("A ` foo ` B") == "a-foo-b"
    # Content that is ENTIRELY spaces is left alone, which is the rule's own
    # exception, so the rendered width is unchanged.
    assert m.heading_slug("a `  ` b") == "a----b"
    assert m.heading_slug("A `x` B") == "a-x-b"


def test_an_escaped_emphasis_character_is_heading_text():
    """`## \\_foo` renders `_foo` and GitHub's id keeps the underscore.
    Unescaping before the boundary rule ran recorded `foo`, so a working
    `#_foo` link was rejected and a nonexistent `#foo` accepted."""
    assert m.heading_slug("\\_foo") == "_foo"
    assert m.heading_slug("foo\\_") == "foo_"
    # The intraword case this grew out of, and genuine emphasis, are unchanged.
    assert m.heading_slug("API\\_FIELD") == "api_field"
    assert m.heading_slug("API_FIELD") == "api_field"
    assert m.heading_slug("_emphasis_") == "emphasis"


def test_only_source_html_is_stripped_from_a_heading():
    """`## \\<em>foo` and `## &lt;em&gt;foo` both render the characters
    `<em>foo`, whose id is `emfoo`. Stripping the tag-shaped run regardless of
    the escape, and after decoding, recorded `foo` -- reversing the validity
    of `#emfoo` and `#foo`."""
    assert m.heading_slug("\\<em>foo") == "emfoo"
    assert m.heading_slug("&lt;em&gt;foo") == "emfoo"
    # Real inline HTML is still markup, an autolink is still not a tag, and a
    # quoted attribute value may still contain `>`.
    assert m.heading_slug("Hello <em>world</em>") == "hello-world"
    assert m.heading_slug("<https://example.com>") == "httpsexamplecom"
    assert m.heading_slug('<span data-x="a>b">Hello</span>') == "hello"


def test_a_heading_comment_is_removed_from_the_text_not_blanked():
    """A slug does not collapse whitespace runs, so blanking a comment to keep
    offsets recorded `hello---------------real` where GitHub exposes
    `hello--real`. The Setext branch reread the raw line and did not mask at
    all, recording `hello----note---`."""
    assert m.heading_anchors("Hello <!-- note -->\n---\n") == {"hello"}
    assert m.heading_anchors("## Hello <!-- note --> Real\n") == {"hello--real"}
    # A comment BEFORE the `#` no longer pushes the heading past the
    # three-column limit, so it is still a heading.
    assert m.heading_anchors("<!-- x --> ## H\n") == {"h"}
    assert m.heading_anchors("Hello\nworld\n---\n") == {"hello-world"}


def test_a_stamp_write_is_atomic_and_refuses_a_symlinked_temp_path(
        tmp_path, monkeypatch):
    """The write went straight at the document, so a failure part-way through
    left it truncated. It goes through a temp file and a rename now -- and
    that path is created EXCLUSIVELY, because an ordinary open would follow a
    symlink found there and truncate a file anywhere writable before renaming
    the link itself into place as the document. Codex filed that as a P1 on
    the Node twin."""
    monkeypatch.setattr(m, "REPO", tmp_path)
    (tmp_path / "a.md").write_text("# A\n")
    canary = tmp_path / "canary.txt"
    canary.write_text("do not touch\n")
    # The temp name carries a random suffix, so the attack is reproduced by
    # pinning the randomness, capturing the name one run picks and
    # pre-creating THAT path as a link on the next.
    monkeypatch.setattr(m.os, "urandom", lambda n: b"\xab" * n)
    m.write_stamp("a.md", "first\n")
    assert (tmp_path / "a.md").read_text() == "first\n"
    # The rename leaves no litter behind.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.md", "canary.txt"]
    tmp = tmp_path / f".a.md.{os.getpid()}-abababab.stamp-tmp"
    assert tmp.name != ".a.md.stamp-tmp"
    tmp.symlink_to(canary)
    with pytest.raises(OSError):
        m.write_stamp("a.md", "second\n")
    assert canary.read_text() == "do not touch\n"
    assert (tmp_path / "a.md").read_text() == "first\n"
    # The refusal's cleanup already removed the planted link -- it removes the
    # link, never its target, which the canary above is what proves.
    assert not tmp.is_symlink()
    # And the write is ATOMIC: a failure at the rename leaves the document as
    # it was rather than truncated, which is what writing in place did.
    def boom(*_a, **_k):
        raise OSError("ENOSPC")
    monkeypatch.setattr(m.os, "replace", boom)
    with pytest.raises(OSError):
        m.write_stamp("a.md", "third\n")
    assert (tmp_path / "a.md").read_text() == "first\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.md", "canary.txt"]


def test_an_html_attribute_value_is_metadata_not_a_citation():
    """`<div data-issue="https://.../issues/1">Outstanding</div>` shows a
    reader the word `Outstanding` and nothing else: the URL is neither visible
    nor clickable, and scanning it produced a gating stale-blocker finding
    from something no reader can act on."""
    states = {"TeneikaAskew/stocks": {1: {"state": "closed", "reason": "completed",
                                          "kind": "issue"}}}
    url = "https://github.com/TeneikaAskew/stocks/issues/1"

    def findings(body):
        return m.check_closed_issues("d.md", f"# T\n\n{body}\n", states)

    assert findings(f'<div data-issue="{url}">Outstanding</div>') == []
    # `href` is exempt only on an ANCHOR: `<a href>` is a citation readers
    # follow, and on any other element it renders no link at all.
    assert findings(f'<a href="{url}">Outstanding</a>') != []
    assert findings(f'<div href="{url}">Outstanding</div>') == []
    # Ordinary prose is still scanned, which is what the check is for.
    assert findings(f"Outstanding: {url}") != []
    # An opening tag may span physical lines, so the scan reads the joined
    # document: a per-line one finds no opener on the second line at all.
    assert m.tag_attribute_spans(["<div", '  data-note="Still open">']) == \
        {1: [(13, 23)]}


def test_a_generated_stamp_inside_markup_is_not_a_stamp():
    """A document that lost its real stamp but still carries `<div
    title="Generated 2026-09-20">` had that date suppress BOTH the
    missing-stamp and the stale-stamp finding, while a reader sees no
    Generated line at all."""
    assert m.visible_generated_stamps(
        ['<div title="Generated 2026-09-20">x</div>']) == []
    # A stamp a reader CAN see is still evidence, including inside a rendered
    # `<div>`, whose text is visible even though Markdown is not parsed there.
    assert m.visible_generated_stamps(["Generated 2026-09-20"]) == ["2026-09-20"]
    assert m.visible_generated_stamps(
        ["<div>", "Generated 2026-09-20", "</div>"]) == ["2026-09-20"]
    # The four hiding mechanisms this rule already knew are unchanged.
    assert m.visible_generated_stamps(["```", "Generated 2026-09-20", "```"]) == []
    assert m.visible_generated_stamps(["x <!-- Generated 2026-09-20 -->"]) == []
    assert m.visible_generated_stamps(["see `Generated 2026-09-20`"]) == []
    assert m.visible_generated_stamps(
        ["<pre>", "Generated 2026-09-20", "</pre>"]) == []


def test_a_marker_inside_raw_html_is_not_the_documents_provenance():
    """Markdown inside `<pre>` or `<div>` is not parsed, so a marker-shaped
    line there renders as literal characters. Accepting it let `--stamp
    --verify` rewrite it and report the document covered while it still had no
    rendered marker."""
    marker = "**Last reviewed:** 2026-09-01 · **Owner:** X"
    for tag in ("pre", "div"):
        assert m.find_markers(["# Real", "", f"<{tag}>", marker,
                               f"</{tag}>", "", "body"]) == []
    # The fenced equivalent was already excluded, and a real marker is found.
    assert m.find_markers(["# Real", "", "```", marker, "```"]) == []
    assert len(m.find_markers(["# Real", "", marker])) == 1


def test_a_query_is_removed_from_the_rendered_destination():
    """`&#63;` IS a `?`, so `[x](guide.md&#63;plain=1)` renders a URL whose
    PATH is `guide.md`. Splitting the raw destination left the nonexistent
    `guide.md?plain=1` once decoded -- a gating dead link against a tracked
    file."""
    tracked = {"d.md", "guide.md"}
    for dest in ("guide.md&#63;plain=1", "guide.md?plain=1"):
        assert m.check_dead_links("d.md", f"# T\n\n[x]({dest})\n", tracked) == []
    # A percent-escaped `?` is NOT a delimiter: a file really named that way
    # keeps its name.
    assert [f["check"] for f in m.check_dead_links(
        "d.md", "# T\n\n[x](guide.md%3Fplain=1)\n", tracked)] == ["dead-link"]


def test_a_backslash_escape_survives_every_link_delimiter():
    """Three delimiters stopped at an ESCAPED copy of themselves, and each
    failure left the whole link unmatched -- so a missing destination produced
    no finding at all, which is the hiding direction."""
    tracked = {"d.md", "a>b.md", "g.md"}

    def dead(body):
        return [f["detail"] for f in m.check_dead_links(
            "d.md", f"# T\n\n{body}\n", tracked)]

    # An angle-bracketed destination: `[x](<a\>b.md>)` resolves to `a>b.md`.
    assert dead(r"[x](<a\>b.md>)") == []
    assert m.check_dead_links("d.md", "# T\n\n[x](<a\\>b.md>)\n", {"d.md"}) != []
    # A title may carry its own delimiter when escaped, in all three forms.
    assert dead(r'[x](g.md "a \" quote")') == []
    assert dead(r"[x](g.md 'a \' quote')") == []
    assert dead(r"[x](g.md (a \) title))") == []
    assert dead(r'[x](missing.md "a \" quote")') == ["relative link -> missing.md"]
    # A reference label may carry an escaped bracket.
    assert dead(r"[x\]]: missing.md") == [r"reference link [x\]] -> missing.md"]
    assert m.REF_DEF_HEAD_RE.match(r"[x\]]:") is not None
    # And the forms these grew out of are unchanged: a footnote still defines
    # no destination, a plain title still closes a link, and the angle form
    # still admits a space.
    assert m.REF_DEF_RE.match("[^1]: note") is None
    assert next(m.md_links('[x](g.md "t")')).group("target") == "g.md"
    assert next(m.md_links("[x](<my guide.md>)")).group("btarget") == "my guide.md"


def test_a_verified_stamp_is_refused_over_a_claim_the_audit_disproved(
        audit_repo, capsys):
    """`--verify` writes `Depth: verified` and today's date, which says "I read
    this and its claims hold". A dead link is a claim this audit has
    mechanically DISPROVEN, so writing that sentence over it is the tool lying
    about itself -- and without --check the command exited 0 having done it.
    Raised on the Node twin."""
    doc = audit_repo / "docs" / "d.md"
    doc.write_text("# D\n\n[x](missing.md)\n")
    before = doc.read_text()
    with pytest.raises(m.AuditError, match="disproved a claim"):
        _audit(audit_repo, "--stamp", "--verify", "docs/d.md")
    # Nothing was written: the whole batch is refused, not half of it.
    assert doc.read_text() == before


def test_a_verified_stamp_still_lands_when_the_document_holds_up(
        audit_repo, capsys):
    """The refusal has to be narrow. A document whose only findings are the
    MISSING provenance the stamp itself supplies must still be stampable, or
    --verify becomes impossible on exactly the documents that need it."""
    doc = audit_repo / "docs" / "d.md"
    doc.write_text("# D\n\nbody\n")
    _audit(audit_repo, "--stamp", "--verify", "docs/d.md")
    report = json.loads(capsys.readouterr().out)
    assert [s["doc"] for s in report["stamped"] if s["doc"] == "docs/d.md"] == \
        ["docs/d.md"]
    assert "**Depth:** verified" in doc.read_text()


def test_a_carriage_return_only_document_keeps_its_line_endings(tmp_path):
    """A lone `\\r` is a line ending too, and `readline` does not stop at one --
    so the "first line" was the whole file and the CRLF test then reported LF,
    making `write_stamp` rewrite every ending in it: the whole-file diff this
    helper exists to prevent, in the one format it did not recognise."""
    cases = {"cr.md": (b"# T\rbody\r", "\r"), "crlf.md": (b"# T\r\nbody\r\n", "\r\n"),
             "lf.md": (b"# T\nbody\n", "\n"), "none.md": (b"# T", "\n"),
             # A first line longer than one read chunk is still answered.
             "long.md": (b"x" * 20000 + b"\r\n", "\r\n")}
    for name, (data, want) in cases.items():
        (tmp_path / name).write_bytes(data)
        assert m.existing_newline(tmp_path / name) == want, name


def test_a_marker_that_names_an_owned_field_twice_is_not_rewritten():
    """Both copies parse, so the malformed-tail refusal cannot see them --
    `extra_segments` CONSUMES a parseable owned value and left no tail. The
    rewrite kept the FIRST and deleted the second, resolving a contradiction
    the document states by discarding half of it, and reported it updated."""
    dup = "**Last reviewed:** 2026-01-01 · **Owner:** Alice · **Owner:** Bob"
    assert m.repeated_owned_fields(dup) == ["Owner:"]
    out, action = m.stamp(f"# T\n\n{dup}\n\nBody.\n", "2026-09-22", "scanned",
                          "abc1234")
    assert action == "skipped-malformed-marker"
    assert "Bob" in out and out == f"# T\n\n{dup}\n\nBody.\n"
    # And it is REPORTED, so --check sees the contradiction rather than only
    # --stamp declining to touch it.
    found = m.find_marker([dup])
    assert [f["check"] for f in m.check_marker_fields("d.md", found[1], dup)] == \
        ["marker"]
    # One copy of each field still stamps.
    single = "**Last reviewed:** 2026-01-01 · **Owner:** Alice"
    assert m.stamp(f"# T\n\n{single}\n\nBody.\n", "2026-09-22", "scanned",
                   "abc1234")[1] == "updated"
    assert m.repeated_owned_fields(single) == []


def test_a_root_file_citation_may_carry_a_non_ascii_name():
    """`known_root` holds a deleted root file specifically so a citation to it
    can be reported, but an ASCII-only pattern never reached that check -- so
    a broken `café.md` citation passed cleanly. BACKTICK_PATH_RE has used the
    Unicode classes for rounds."""
    assert m.BACKTICK_ROOT_FILE_RE.search("see `café.md` here") is not None
    assert m.BACKTICK_ROOT_FILE_RE.search("see `vite.config.ts` here") is not None
    # The narrowings that keep this from matching prose are unchanged: it
    # needs an extension, and a path with a slash belongs to the other pattern.
    assert m.BACKTICK_ROOT_FILE_RE.search("see `hello world` here") is None
    assert m.BACKTICK_ROOT_FILE_RE.search("see `docs/g.md` here") is None


def test_registry_specificity_is_not_pattern_length():
    """`docs/[a-z]*.md` is LONGER than `docs/a.md`, so a wildcard row outranked
    the exact row it overlaps -- and because the lengths differ, the tie that
    would have raised an ambiguity finding never happened, so a machine-owned
    document could be classified writable and --stamp could modify it. The
    Node twin has ranked this way for rounds."""
    def wins(a, b):
        return m.glob_specificity(a) > m.glob_specificity(b)
    assert wins("docs/a.md", "docs/[a-z]*.md")       # exact beats any wildcard
    assert wins("docs/*.md", "docs/**/*.md")         # narrower beats recursive
    assert wins("docs/??.md", "docs/*.md")           # fixed width beats open
    # Adding alternatives to a bracket must not raise specificity, or a
    # broader row silently outranks a narrower one instead of tying.
    assert m.glob_specificity("docs/[ab].md") == m.glob_specificity("docs/[a].md")


def test_two_registry_rows_declaring_the_same_sets_do_not_disagree():
    """`lib/a, lib/b` and `lib/b, lib/a` declare the same thing and drive
    identical checks, yet compared unequal -- a gating P1 that made
    `classification_is_ambiguous` refuse --stamp over a disagreement the
    registry does not contain."""
    # Two rows of EQUAL specificity -- the same glob twice is the clearest
    # case -- declaring the same two code paths in different orders.
    rows = [{"glob": "docs/*.md", "cls": "D", "code_paths": ["lib/a", "lib/b"],
             "regions": []},
            {"glob": "docs/*.md", "cls": "D", "code_paths": ["lib/b", "lib/a"],
             "regions": []}]
    tracked = {"docs/x.md", "lib/a", "lib/b", "lib/c"}
    assert [f for f in m.check_registry_paths(tracked, rows)
            if "equal specificity" in f["detail"]] == []
    assert not m.classification_is_ambiguous("docs/x.md", rows)
    # A genuine disagreement is still reported, and still blocks --stamp.
    rows[1]["code_paths"] = ["lib/c"]
    assert [f["severity"] for f in m.check_registry_paths(tracked, rows)
            if "equal specificity" in f["detail"]] == ["P1"]
    assert m.classification_is_ambiguous("docs/x.md", rows)


def test_a_drift_reread_that_fails_is_not_a_clean_result(tmp_path, monkeypatch):
    """If the document became unreadable between the main-loop read and this
    one, the OSError branch returned the same empty result as an UNCHANGED
    document -- so the audit could report clean having never compared the
    prose against the reviewed revision at all."""
    monkeypatch.setattr(m, "REPO", tmp_path)

    def boom(*_a, **_k):
        raise OSError("ENOENT")

    monkeypatch.setattr(m, "path_in_commit", lambda *a, **k: True)
    monkeypatch.setattr(m, "run", lambda *a, **k: "old prose\n")
    monkeypatch.setattr(m.pathlib.Path, "read_text", boom)
    with pytest.raises(m.AuditError, match="could not be read to measure drift"):
        m.check_doc_changed_since("docs/d.md", "abc1234", "origin/main")
