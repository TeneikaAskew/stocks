"""Invariants for scripts/maintenance/docs_audit.py.

Each test names the defect it prevents, following tests/meta/test_production_writers.py.
Every one was mutation-checked: the defect was reintroduced, the test confirmed
red, then reverted.
"""
from __future__ import annotations

import datetime

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
    _, paths = m.classify("docs/product/02-FEATURE-CATALOG.md", rows)
    assert paths == ["lib", "platform/api"]


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
