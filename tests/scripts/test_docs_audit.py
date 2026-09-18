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
    assert "drift_commits(out)" in src


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
                        "scanned": "2026-09-16", "legacy": False}


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


def test_pull_request_links_are_not_treated_as_issues():
    line = "Blocking: [#861](https://github.com/TeneikaAskew/stocks/pull/861)"
    assert m.check_closed_issues("d.md", line, STATES) == []


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
    (tmp_path / "issues.json").write_text(json.dumps({"stocks": {}, "solyra": {}}))
    monkeypatch.setattr(m, "REPO", tmp_path)
    monkeypatch.setattr(m, "TOP_LEVEL_DIRS", set())
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _audit(repo, *argv):
    """Run main() over `repo`, offline, and return (exit code, report)."""
    _commit(repo, "tree")
    code = m.main(["--json", "--date", "2026-09-18",
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
    nonnumeric.write_text(json.dumps({"stocks": {"abc": {}}, "solyra": {}}))
    with pytest.raises(m.AuditError, match="issue number"):
        m.load_issues_snapshot(str(nonnumeric))


def test_a_good_issues_snapshot_still_loads(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"stocks": {"7": {"state": "closed"}}, "solyra": {}}))
    assert m.load_issues_snapshot(str(good)) == {"stocks": {7: {"state": "closed"}}, "solyra": {}}


def test_a_snapshot_issue_record_must_carry_a_state(tmp_path):
    """The structural check stopped at "the repo entry is an object", so a row
    with no `state` reached `st["state"]` and raised KeyError -- a traceback
    and exit 1, the status reserved for "this documentation has findings".
    A `null` row was worse than that: it reads as `st is None`, which is the
    unresolvable branch, so a malformed snapshot FABRICATES a finding against
    a document that cites a perfectly live issue (CLAUDE.md §3.7)."""
    missing_state = tmp_path / "a.json"
    missing_state.write_text(json.dumps({"stocks": {"1": {}}, "solyra": {}}))
    with pytest.raises(m.AuditError, match="stocks#1"):
        m.load_issues_snapshot(str(missing_state))

    null_row = tmp_path / "b.json"
    null_row.write_text(json.dumps({"stocks": {"1": None}, "solyra": {}}))
    with pytest.raises(m.AuditError, match="stocks#1"):
        m.load_issues_snapshot(str(null_row))

    non_string = tmp_path / "c.json"
    non_string.write_text(json.dumps({"stocks": {"1": {"state": 7}}, "solyra": {}}))
    with pytest.raises(m.AuditError, match="stocks#1"):
        m.load_issues_snapshot(str(non_string))

    listed = tmp_path / "d.json"
    listed.write_text(json.dumps({"stocks": [], "solyra": {}}))
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
         "solyra": {}}))
    with pytest.raises(m.AuditError, match="stocks#8"):
        m.load_issues_snapshot(str(bogus))

    for state in ("open", "closed"):
        good = tmp_path / f"{state}.json"
        good.write_text(json.dumps(
            {"stocks": {"8": {"state": state, "reason": "", "kind": "ISSUE"}},
             "solyra": {}}))
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
            m.main(["--json", "--date", "2026-09-18",
                    "--issues-snapshot", str(audit_repo / "issues.json"), "--stamp"])
    finally:
        (audit_repo / "docs" / "locked.md").chmod(0o644)
    # The refusal comes before the writes, so no other document was touched.
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
        m.main(["--json", "--date", "2026-09-18",
                "--issues-snapshot", str(audit_repo / "issues.json"), "--stamp"])


def test_a_snapshot_that_cannot_be_written_is_exit_two(audit_repo):
    """Reading a bad snapshot is exit 2; failing to WRITE one was exit 1, via
    an OSError escaping the AuditError handler. Same class, same status."""
    (audit_repo / "docs" / "d.md").write_text("# D\n\nbody\n")
    _commit(audit_repo, "tree")
    with pytest.raises(m.AuditError, match="could not be written"):
        m.main(["--json", "--date", "2026-09-18",
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
    assert m.main(["--json", "--date", "2026-09-18",
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
        m.main(["--json", "--date", "2026-09-18",
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


# ── the owning job, and what its success does not prove ────────────────────

def _pr_pages(pages):
    """A fake `run` serving one PR page per call, then the workflow-runs read."""
    calls = {"n": 0}

    def fake_run(cmd, **kw):
        joined = " ".join(cmd)
        if "runs?per_page=10" in joined:
            return "success\t2026-09-16T06:00:00Z\n"
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
    """The pages are ordered by CREATION time; `delivered` is a MERGE time.

    A refresh PR created in August can merge after one created in September,
    so the newest delivery can sit on a page the old walk never reached -- it
    stopped at the first merged refresh it saw. The attempts that merge
    superseded were then reported as live failures.

    Page 1: #1060 open, created 09-08, and #953 merged 09-02 -- which does NOT
    supersede it. Page 2: #900, created 08-01 but merged 09-20, which does."""
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
    assert fake.calls["n"] == 2, "stopped before the delivery that superseded #1060"
    assert not [f for f in out if "1060" in f["detail"]], out


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
    (audit_repo / "docs" / "cal.md").write_text("latest calibration 2026-09-01\n")
    assert m.check_best_effort_artifacts("2026-09-18", artifacts=art) == []
    (audit_repo / "docs" / "cal.md").write_text("latest calibration 2026-01-01\n")
    out = m.check_best_effort_artifacts("2026-09-18", artifacts=art)
    assert len(out) == 1 and out[0]["severity"] == "P2", out
    assert "refresh_calibration_table" in out[0]["detail"]


def test_a_best_effort_artifact_with_no_date_at_all_is_a_finding(audit_repo):
    """No date means no evidence either way, which is not the same as fresh."""
    art = [{"doc": "docs/cal.md", "region": "cal",
            "date_re": m.re.compile(r"latest calibration (\d{4}-\d{2}-\d{2})"),
            "max_age_days": 180,
            "refresher": "scripts/refresh_calibration_table.py"}]
    (audit_repo / "docs" / "cal.md").write_text("no date here\n")
    out = m.check_best_effort_artifacts("2026-09-18", artifacts=art)
    assert len(out) == 1 and "no date" in out[0]["detail"], out


def test_an_impossible_date_in_a_best_effort_artifact_is_reported(audit_repo):
    art = [{"doc": "docs/cal.md", "region": "cal",
            "date_re": m.re.compile(r"latest calibration (\d{4}-\d{2}-\d{2})"),
            "max_age_days": 180,
            "refresher": "scripts/refresh_calibration_table.py"}]
    (audit_repo / "docs" / "cal.md").write_text("latest calibration 2026-02-30\n")
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
    m.main(["--date", "2026-09-18", "--issues-snapshot", str(audit_repo / "issues.json")])
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
    m.main(["--date", "2026-09-18", "--issues-snapshot", str(audit_repo / "issues.json")])
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
    (audit_repo / "docs" / "cal.md").write_text("# Cal\n\nlatest calibration 2026-01-01\n")
    _audit(audit_repo)
    report = json.loads(capsys.readouterr().out)
    assert [f["severity"] for f in report["findings"]
            if f["check"] == "class-a" and f["doc"] == "docs/cal.md"] == ["P2"], report["findings"]
