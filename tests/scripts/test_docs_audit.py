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

    real = pathlib.Path.write_text
    seen: list[str] = []

    def explode(self, *a, **kw):
        if self.suffix == ".md":
            seen.append(self.name)
            if len(seen) > 1:
                raise OSError(28, "No space left on device")
        return real(self, *a, **kw)

    monkeypatch.setattr(pathlib.Path, "write_text", explode)
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
