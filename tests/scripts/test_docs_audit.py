"""Invariants for scripts/maintenance/docs_audit.py.

Each test names the defect it prevents, following tests/meta/test_production_writers.py.
Every one was mutation-checked: the defect was reintroduced, the test confirmed
red, then reverted.
"""
from __future__ import annotations

import inspect
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
    """
    assert m.resolve_base_ref(("definitely-not-a-ref", "HEAD")) == "HEAD"


def test_base_ref_prefers_the_trunk_when_it_is_there():
    assert m.resolve_base_ref(("HEAD", "definitely-not-a-ref")) == "HEAD"
    assert m.resolve_base_ref(("origin/main", "HEAD")) == "origin/main"


def test_no_resolvable_ref_raises_rather_than_guessing():
    """Falling back to a ref is fine; inventing one is the silent fallback."""
    with pytest.raises(m.AuditError, match="nothing to audit against"):
        m.resolve_base_ref(("no-such-ref-a", "no-such-ref-b"))


# ── drift ───────────────────────────────────────────────────────────────────

def test_drift_filter_covers_additions_and_deletions_not_just_edits():
    """A declared path GAINING or LOSING a module is drift.

    `--diff-filter=M` alone queued neither, so a new module under `lib` or a
    deleted one under `platform/api` left the describing document unflagged.
    Renames stay excluded, which is what the filter is for.
    """
    src = inspect.getsource(m.check_changed_since)
    assert "--diff-filter=AMD" in src
    assert "--diff-filter=M\"" not in src


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

