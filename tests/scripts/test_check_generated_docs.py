"""Gates for the monthly doc refresh (scripts/maintenance/check_generated_docs.py).

Each test reproduces one way the 2026-09-02 regeneration went wrong and
asserts the gate now turns it into a finding.
"""
from __future__ import annotations

import json
import pathlib
import shutil

import pytest

from scripts.maintenance import check_generated_docs as gate
from scripts.maintenance import doc_inventory as inv

REPO = pathlib.Path(__file__).resolve().parents[2]
SNAPSHOT = REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
DOCS = gate.DIFF_DOCS   # derived, so a relocation moves the fixtures with it


def _copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst)


@pytest.fixture()
def live():
    return json.loads(SNAPSHOT.read_text())


@pytest.fixture()
def repo():
    return inv.repo_inventory(REPO)


def test_committed_docs_pass_every_gate(live, repo, tmp_path):
    prev = tmp_path / "previous"
    prev.mkdir()
    for d in DOCS:
        _copy(REPO / d, prev / d)
    findings = gate.run(REPO, SNAPSHOT, prev, None)
    assert findings == [], "\n".join(findings)


def test_missing_job_name_is_a_finding(live, repo):
    findings = gate.gate_coverage(REPO, repo, live)
    assert findings == []
    live2 = json.loads(json.dumps(live))
    live2["jobs"]["ghost-job"] = live2["jobs"]["signal-monitor"]
    assert any("ghost-job" in f for f in gate.gate_coverage(REPO, repo, live2))


def test_editing_inside_a_marker_block_is_a_finding(live, repo, tmp_path):
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    text = (root / gate.ARCH).read_text()
    s = inv.MARKER_START.format(name="jobs")
    text = text.replace(s, s + "\n| `hand-edited-row` | x | x | x | x | x |", 1)
    (root / gate.ARCH).write_text(text)
    assert any("marker block differs" in f for f in gate.gate_markers(root, repo, live))


def test_removing_both_markers_of_a_block_is_a_finding(live, repo, tmp_path):
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    text = (root / gate.DEPS).read_text()
    s, e = inv.MARKER_START.format(name="orphans"), inv.MARKER_END.format(name="orphans")
    import re
    text = re.sub(re.escape(s) + r".*?" + re.escape(e), "", text, flags=re.S)
    (root / gate.DEPS).write_text(text)
    findings = gate.gate_markers(root, repo, live)
    assert any("inventory:orphans block is missing entirely" in f for f in findings), findings


def test_a_duplicated_block_is_a_finding(live, repo, tmp_path):
    """A doubled inventory block survived every other gate.

    insert_blocks rewrites the FIRST match only (count=1), so the second copy
    passes through the fresh-render comparison byte-identical; the old
    membership check saw both markers present and said nothing; and the churn
    ceiling scores REMOVED lines, so pure duplication cannot trip it either.
    """
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    import re
    text = (root / gate.ARCH).read_text()
    s, e = inv.MARKER_START.format(name="jobs"), inv.MARKER_END.format(name="jobs")
    block = re.search(re.escape(s) + r".*?" + re.escape(e), text, re.S).group(0)
    (root / gate.ARCH).write_text(text.replace(block, block + "\n\n" + block, 1))
    findings = gate.gate_markers(root, repo, live)
    assert any("inventory:jobs appears 2 times" in f for f in findings), findings


def test_a_rewrite_that_keeps_its_length_is_a_finding(tmp_path):
    """The 2026-09-02 failure mode: a doc replaced rather than updated.

    The size floor cannot see this one -- the line count is unchanged -- and
    the heading gate cannot either if the headings are kept. Churn can.
    """
    root, prev = tmp_path, tmp_path / "previous"
    prev.mkdir()
    for d in DOCS:
        _copy(REPO / d, root / d)
        _copy(REPO / d, prev / d)
    old = (prev / gate.ARCH).read_text().splitlines()
    heads = [ln for ln in old if ln.startswith("#")]
    body = ["Every other line replaced with different prose." for _ in range(len(old) - len(heads))]
    (root / gate.ARCH).write_text("\n".join(heads + body) + "\n")
    stats = {st["doc"]: st for st in gate.diff_stats(root, prev)}
    assert stats[gate.ARCH]["churn"] > 0.5
    findings = gate.gate_diff_budget(list(stats.values()))
    assert any(gate.ARCH in f and "rewrite" in f for f in findings), findings
    # ...and a human reconstructing that one doc can say so, for that doc only
    assert gate.gate_diff_budget(list(stats.values()), allow_rewrite=(gate.ARCH,)) == []


def test_diff_stats_report_names_what_moved(tmp_path):
    root, prev = tmp_path, tmp_path / "previous"
    prev.mkdir()
    for d in DOCS:
        _copy(REPO / d, root / d)
        _copy(REPO / d, prev / d)
    text = (root / gate.COST).read_text()
    (root / gate.COST).write_text(text + "\n## A brand new section\n\nbody\n")
    stats = gate.diff_stats(root, prev)
    report = gate.render_report(stats)
    assert "A brand new section" in report and "+added" in report
    cost = next(st for st in stats if st["doc"] == gate.COST)
    assert cost["added"] >= 3 and cost["removed"] == 0 and cost["churn"] == 0.0


def test_the_2026_09_02_regeneration_would_have_been_stopped(tmp_path):
    """The incident this gate exists for, measured against the real commits.

    b3b5271 -> e50c759 (#953) is the monthly refresh that shrank
    ARCHITECTURE.md from 394 lines to 158 while every gate of the day passed.
    Churn on the four docs was 87 / 88 / 75 / 70 percent. Each must be caught
    either by the churn ceiling or, for the documents legitimately re-derived
    in full, by the size floor.
    """
    import subprocess
    root, prev = tmp_path, tmp_path / "previous"
    prev.mkdir()
    # b3b5271/e50c759 predate the move into docs/product/infrastructure/, so
    # the historical blobs are read at their old paths and laid down at the
    # paths the gate reads today.
    four = (("ARCHITECTURE.md", gate.ARCH),
            ("DATA_DEPENDENCIES.md", gate.DEPS),
            ("COST_ANALYSIS.md", gate.COST),
            ("README.md", "README.md"))
    for was, now in four:
        for rev, dest in (("b3b5271", prev), ("e50c759", root)):
            out = subprocess.run(["git", "show", f"{rev}:{was}"], cwd=REPO,
                                 capture_output=True, text=True)
            if out.returncode:
                pytest.skip(f"{was} not present at {rev} in this clone")
            (dest / now).parent.mkdir(parents=True, exist_ok=True)
            (dest / now).write_text(out.stdout)

    stats = {st["doc"]: st for st in gate.diff_stats(root, prev)}
    assert stats[gate.ARCH]["churn"] > 0.80, stats[gate.ARCH]["churn"]
    assert stats[gate.DEPS]["churn"] > 0.80

    caught = set()
    for f in gate.gate_diff_budget(list(stats.values())) + gate.gate_headings_and_size(root, prev):
        caught.add(f.split(":")[0])
    for _, now in four:
        assert now in caught, f"{now} would have shipped unnoticed; caught={caught}"


def test_lost_heading_and_shrink_are_findings(tmp_path):
    root = tmp_path
    prev = tmp_path / "previous"
    prev.mkdir()
    for d in DOCS:
        _copy(REPO / d, root / d)
        _copy(REPO / d, prev / d)
    text = (root / gate.ARCH).read_text()
    cut = text.find("## 10. Data flows")
    (root / gate.ARCH).write_text(text[:cut] + "\n## 10. Data flows\n\n## 19. Glossary\n")
    findings = gate.gate_headings_and_size(root, prev)
    assert any("heading lost" in f and "Failure handling" in f for f in findings)
    assert any("shrank" in f for f in findings)


def test_stale_reference_outside_history_context_is_a_finding(tmp_path):
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    (root / "README.md").write_text((root / "README.md").read_text() + "\nDispatch `.github/workflows/db-query.yml` to run SQL.\n")
    assert any("db-query.yml" in f for f in gate.gate_stale(root))
    (root / "README.md").write_text((REPO / "README.md").read_text() + "\nThe old `db-query.yml` workflow was deleted 2026-05-30.\n")
    assert not any("db-query.yml" in f for f in gate.gate_stale(root)), "history context is allowed"


def test_every_prompt_mandated_map_target_is_gated(tmp_path):
    """The README prompt and the gate must name the same set.

    Dropping a map row leaves no dead link, keeps the headings, and README is
    exempt from the size floor -- so an ungated target could vanish silently.
    (Codex, PR #1009.)
    """
    import re
    prompt = (REPO / ".github/prompts/readme.md").read_text()
    line = next(ln for ln in prompt.splitlines() if "Documentation map" in ln)
    # Only the "Must link ..." clause names required targets; the sentence
    # after it ("Add a row for any new top-level or `docs/` reference
    # document") is guidance, and its bare `docs/` is not a map row.
    clause = line.split("Must link", 1)[1].split("Add a row", 1)[0]
    mandated = {m for m in re.findall(r"`([^`]+)`", clause) if "/" in m or m.endswith(".md")}
    missing = sorted(mandated - set(gate.README_REQUIRED_LINKS))
    assert not missing, f"prompt mandates rows the gate does not check: {missing}"


def test_dropping_a_map_row_is_a_finding(tmp_path):
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    guide = f"{gate.INFRA}/05-i-GCP_IMPLEMENTATION_GUIDE.md"
    text = (root / "README.md").read_text()
    assert f"({guide})" in text
    (root / "README.md").write_text(text.replace(f"({guide})", f"({gate.ARCH})"))
    findings = gate.gate_readme(root)
    assert any(guide in f for f in findings), findings


def test_dead_link_and_readme_mermaid_are_findings(tmp_path):
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    (root / "README.md").write_text((root / "README.md").read_text() + "\nSee [x](docs/DOES_NOT_EXIST.md).\n```mermaid\nflowchart LR\n```\n")
    assert any("dead relative link" in f for f in gate.gate_links(root))
    assert any("mermaid" in f for f in gate.gate_readme(root))


def test_truncated_transcript_is_a_finding(tmp_path):
    t = tmp_path / "transcripts"
    t.mkdir()
    (t / "architecture.log").write_text("Reading refresh-inputs/inventory.json ... [output truncated]\n")
    assert gate.gate_transcripts(t)
    (t / "architecture.log").write_text("all good\n")
    assert gate.gate_transcripts(t) == []


def test_the_retry_split_must_match_deploy_sh(live, repo, tmp_path):
    """Three rounds each corrected ONE instance of this number and left
    another standing, because the corrections were made by reading rather than
    by deriving: §9 said 41/25/1 while §6 still said 56/27, a total of 83
    against 67 declared jobs. (Codex, PR #1009.)
    """
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    assert gate.gate_derived_numbers(root, repo, live) == []
    a = root / gate.ARCH
    a.write_text(a.read_text().replace(
        "`--max-retries 0` for 43 of the 68 declared jobs, `1` for 24",
        "`--max-retries 0` for 56 jobs and `1` for 27"))
    findings = gate.gate_derived_numbers(root, repo, live)
    assert any("claims 56 jobs at --max-retries 0" in f for f in findings), findings


def test_the_runtime_relation_count_must_match_the_snapshot(live, repo, tmp_path):
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    a = root / gate.ARCH
    a.write_text(a.read_text().replace("Live table drift (26 runtime relations)",
                                       "Live table drift (28 runtime relations)"))
    findings = gate.gate_derived_numbers(root, repo, live)
    assert any("claims 28 runtime relations" in f and "is 26" in f for f in findings), findings


def test_the_retry_claim_is_caught_in_either_clause_order(live, repo, tmp_path):
    """The first version required the flag to precede the count, so
    "56 jobs use `--max-retries 0`" -- a phrasing no prompt forbids -- passed
    the gate that exists to catch that number. (Codex, PR #1009.)"""
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    a = root / gate.ARCH
    a.write_text("56 jobs use `--max-retries 0` today.\n" + a.read_text())
    findings = gate.gate_derived_numbers(root, repo, live)
    assert any("claims 56 jobs at --max-retries 0" in f for f in findings), findings


def test_runtime_relations_are_a_set_difference(repo, tmp_path):
    """Subtracting totals undercounts when a declared relation is not yet
    live, rejecting correct prose and accepting a wrong number.
    (Codex, PR #1009.)"""
    import json as _json
    live = _json.loads((REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json").read_text())
    # drop one DECLARED relation from the live side, as a pending migration would
    declared = ({t["name"] for t in repo["tables"]}
                | {v["name"] for v in repo["materialized_views"]}
                | {v["name"] for v in repo["views"]})
    victim = next(n for n in live["db_tables"] if n in declared)
    live["db_tables"] = {k: v for k, v in live["db_tables"].items() if k != victim}
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    # the runtime count is unchanged: only a declared relation disappeared
    assert gate.gate_derived_numbers(root, repo, live) == [], \
        "a pending migration must not change the runtime-created count"


def test_a_model_written_suppression_is_a_finding(tmp_path):
    """`verify-docs-ok` silences the docs-vs-live checks for a line, and the
    model can edit all four generated documents. A marker it wrote would have
    removed a stale claim from the verifier under a clean run.
    (Codex, PR #1009.)"""
    root, prev = tmp_path / "r", tmp_path / "p"
    root.mkdir(); prev.mkdir()
    for d in DOCS:
        _copy(REPO / d, root / d); _copy(REPO / d, prev / d)
    assert gate.gate_new_suppressions(root, prev) == []
    a = root / gate.ARCH
    a.write_text("Live has 999 jobs. <!-- verify-docs-ok: the model says so -->\n" + a.read_text())
    findings = gate.gate_new_suppressions(root, prev)
    assert any("new verify-docs-ok exemption" in f for f in findings), findings


def test_a_spelled_out_retry_count_is_validated(live, repo, tmp_path):
    """The document's own shorthand is "`2` for one", so a word count is the
    shape already in use and digits-only let a rephrase defeat the gate."""
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    a = root / gate.ARCH
    a.write_text(a.read_text().replace("`2` for one", "`2` for two"))
    findings = gate.gate_derived_numbers(root, repo, live)
    assert any("claims 2 jobs at --max-retries 2" in f for f in findings), findings


def test_a_fixed_min_instances_for_a_windowed_service_is_a_finding(repo, tmp_path):
    """`discord-interactions` has its minInstanceCount PATCHed by two schedulers
    (`discord-warm-open` sets 1, `discord-warm-close` sets 0), so no single value
    is true all day. This exact claim was corrected five times on PR #1009,
    each time in the copy that had been read rather than as a class."""
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    assert gate.gate_scheduled_scaling(root, repo) == []
    a = root / gate.ARCH
    a.write_text(a.read_text().replace(
        "`discord-interactions` (min-instances 1 only inside the weekday warm window, 0 otherwise — §7.4)",
        "`discord-interactions` (min-instances 1)"))
    findings = gate.gate_scheduled_scaling(root, repo)
    assert any("states a fixed min-instances for 'discord-interactions'" in f for f in findings), findings


def test_the_windowed_set_is_derived_not_hardcoded(tmp_path):
    """A second service scaled on a schedule must be covered the day it is
    declared, so the gate reads `_schedule_min_instances` rather than a name."""
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    (root / gate.ARCH).write_text("The `solyra-api-prod` service runs min-instances 3.\n")
    plain = {"schedulers": [{"name": "x", "helper": "_schedule_min_instances",
                             "target_service": "solyra-api-prod"}]}
    assert any("solyra-api-prod" in f for f in gate.gate_scheduled_scaling(root, plain))
    none = {"schedulers": [{"name": "x", "helper": "_schedule_job", "target_service": ""}]}
    assert gate.gate_scheduled_scaling(root, none) == []


def _cost_pair(tmp_path):
    """The previous COST_ANALYSIS.md and a regeneration of it, in run 17's
    shape: the five promised sections kept, every data-bearing subheading
    changed, fewer lines but more bytes."""
    root, prev = tmp_path / "r", tmp_path / "p"
    (root / ".github/prompts").mkdir(parents=True); prev.mkdir()
    _copy(REPO / ".github/prompts/cost-analysis.md", root / ".github/prompts/cost-analysis.md")
    for d in (gate.ARCH, gate.DEPS, "README.md"):
        _copy(REPO / d, root / d); _copy(REPO / d, prev / d)
    _copy(REPO / gate.COST, prev / gate.COST)
    body = [
        "# Cost Analysis", "", "Total 90-day spend is $222.71.", "",
        "## 1. Total spend by month", "", "| Month | Spend | Notes |", "|---|---|---|", "",
        "## 2. Top 10 cost line items by SKU", "", "| Rank | Service | SKU |", "|---|---|---|", "",
        "## 3. Per-component cost estimate", "",
        "### Cloud Run (Jobs & Services) — $101.44", "", "Allocation by runs-per-month.", "",
        "### Cloud SQL (`trading-db`) — $68.10", "", "Tier db-g1-small.", "",
        "## 4. Anomalies", "", "### A. Artifact Registry down 59% month over month", "", "Cause.", "",
        "## 5. Cost-reduction recommendations", "",
        "### #1 — Optimize expensive Cloud Run jobs (estimated saving: $5-10/mo)", "", "Change.", "",
        "Generated 2026-09-07 by .github/workflows/refresh-architecture-docs.yml",
    ]
    while len(body) < 81:
        body.append("A detail line carrying real content from the billing export.")
    text = "\n".join(body) + "\n"
    text += "x" * max(0, 8027 - len(text.encode()))
    (root / gate.COST).write_text(text)
    return root, prev


def test_a_regenerated_cost_report_may_change_its_data_bearing_headings(tmp_path):
    """Run 17 failed COST_ANALYSIS.md on twelve "lost" headings, every one of
    which embeds that month's data — `Cloud Run (Jobs & Services) — $94.26`,
    `2. Top 10 cost line items by SKU (Partial August data)`. Its prompt says
    "Regenerate", not "update in place". Demanding those persist demands this
    month's report keep last month's numbers."""
    root, prev = _cost_pair(tmp_path)
    findings = gate.gate_headings_and_size(root, prev)
    assert [f for f in findings if gate.COST in f] == [], findings
    # and the previous behaviour is what run 17 saw
    saved = gate.REGENERATED
    try:
        gate.REGENERATED = ()
        assert len([f for f in gate.gate_headings_and_size(root, prev)
                    if gate.COST in f]) >= 12
    finally:
        gate.REGENERATED = saved


def test_a_regenerated_doc_is_measured_in_bytes_not_lines(tmp_path):
    """Run 17's regeneration lost 21 lines while gaining 1,884 bytes. Lines are
    the wrong unit for a document rebuilt from data; mass is the measure."""
    root, prev = _cost_pair(tmp_path)
    assert gate.gate_headings_and_size(root, prev) == []
    (root / gate.COST).write_text((root / gate.COST).read_text()[:3000])
    findings = gate.gate_headings_and_size(root, prev)
    assert any("bytes (< 80%)" in f and "not regenerated" in f for f in findings), findings


def test_a_regenerated_doc_must_carry_every_section_its_prompt_promises(tmp_path):
    """Dropping heading-persistence would leave the cost report unguarded, so
    the sections are checked against the prompt instead — derived from it, so a
    section added to the prompt moves the gate with it."""
    root, prev = _cost_pair(tmp_path)
    assert gate.gate_regenerated_structure(root) == []
    assert [n for n, _ in gate._promised_sections(root, "cost-analysis.md")] == list("12345")
    c = root / gate.COST
    c.write_text(c.read_text().replace("## 4. Anomalies", "## Anomalies of note"))
    findings = gate.gate_regenerated_structure(root)
    assert any("missing the section its prompt promises: 4. 'Anomalies'" in f for f in findings), findings


def test_the_other_documents_keep_heading_persistence(tmp_path):
    """The exemption is for the one regenerated document, not a general
    loosening: an in-place-updated doc that loses a heading still fails."""
    root, prev = _cost_pair(tmp_path)
    a = root / gate.ARCH
    heads = [h for h in gate._headings(a.read_text())]
    a.write_text(a.read_text().replace(f"## {heads[3]}", "## Something Else Entirely", 1))
    findings = gate.gate_headings_and_size(root, prev)
    assert any(f.startswith(f"{gate.ARCH}: heading lost") for f in findings), findings
