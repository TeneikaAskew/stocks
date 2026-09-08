"""Gates for the monthly doc refresh (scripts/maintenance/check_generated_docs.py).

Each test reproduces one way the 2026-09-02 regeneration went wrong and
asserts the gate now turns it into a finding.
"""
from __future__ import annotations

import json
import pathlib
import re
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
    findings = gate.gate_markers(root, repo, live)
    # Named, with the first differing line: run 24 reported "an inventory
    # marker block differs" for 05-c and nothing more, and the artifact that
    # held the answer was behind an endpoint the sandbox cannot reach.
    assert any("inventory:jobs block differs" in f and "hand-edited-row" in f for f in findings), findings


def test_a_model_edited_block_is_restored_from_the_fresh_render_by_name(live, repo, tmp_path):
    """Run 24's fix. The blocks are the workflow's, rendered from the frozen
    snapshot before the model runs; a model edit inside one is overwritten
    with the authoritative render and REPORTED, rather than failing the
    refresh. Only blocks that differ are named, and after the restore the
    marker gate has nothing to say."""
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    text = (root / gate.ARCH).read_text()
    s = inv.MARKER_START.format(name="jobs")
    text = text.replace(s, s + "\n| `hand-edited-row` | x | x | x | x | x |", 1)
    (root / gate.ARCH).write_text(text)
    assert [n for n, _ in inv.differing_blocks(root / gate.ARCH, repo, live, root=root)] == ["jobs"]
    assert inv.restore_blocks(root / gate.ARCH, repo, live, root=root) == ["jobs"]
    assert "hand-edited-row" not in (root / gate.ARCH).read_text()
    assert gate.gate_markers(root, repo, live) == []
    # Idempotent: a second restore touches nothing and names nothing.
    assert inv.restore_blocks(root / gate.ARCH, repo, live, root=root) == []


def test_a_block_without_its_end_marker_cannot_be_restored_and_is_a_finding(live, repo, tmp_path):
    """The one shape a restore must not paper over: with no end marker the
    block cannot be located, so nothing can say where the render should go."""
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    text = (root / gate.ARCH).read_text()
    text = text.replace(inv.MARKER_END.format(name="jobs"), "", 1)
    (root / gate.ARCH).write_text(text)
    with pytest.raises(ValueError):
        inv.restore_blocks(root / gate.ARCH, repo, live, root=root)
    assert any("inventory:jobs:start --> without" in f for f in gate.gate_markers(root, repo, live))


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

def test_prose_replaced_by_an_ellipsis_is_a_finding(tmp_path):
    """Run 27 passed every gate — churn budget, heading persistence, marker
    restore, live verifier — with five section introductions and four bullets
    in 05-c replaced by a bare `...`, destroying 4,035 characters. Whole-file
    size did not notice: the document is 137 KB of which ~120 KB is rendered
    blocks, so the loss moved its line count by under 1%. (Run 27.)"""
    doc = tmp_path / gate.DEPS
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("## 2. Write graph\n...\n\n"
                   "## 4. Multi-writer\n"
                   "- **`market_data_daily`** ...\n"
                   "- **`etf_options_snapshots`** — `fetch_av_historical_options` upserts nightly.\n")
    out = gate.gate_elided_prose(tmp_path)
    assert len(out) == 2, out
    assert all(gate.DEPS in f for f in out)
    assert any("'...'" in f for f in out)
    assert any("market_data_daily" in f for f in out)
    # the bullet that says something real is not flagged
    assert not any("etf_options_snapshots" in f for f in out), out


def test_a_mid_sentence_ellipsis_is_ordinary_prose(tmp_path):
    """`gamma_levels_eod`, … inside a sentence is how these documents already
    elide a list, and flagging it would fail every run. Only a line that is
    ENTIRELY an ellipsis is an elided paragraph."""
    doc = tmp_path / gate.DEPS
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("27 runtime-created relations (`strat_features_*`, `gamma_levels_eod`, …) "
                   "are outside `gcp/schema.sql`.\n"
                   "The fetchers run at 08:20, 08:30, ... and 23:00.\n")
    assert gate.gate_elided_prose(tmp_path) == []


def test_an_ellipsis_inside_a_rendered_block_is_not_the_models_doing(tmp_path):
    """The blocks are rendered by the workflow and restored after the model, so
    an ellipsis inside one came from the renderer, not from an elided edit."""
    doc = tmp_path / gate.DEPS
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("<!-- inventory:blast:start -->\n...\n<!-- inventory:blast:end -->\n")
    assert gate.gate_elided_prose(tmp_path) == []


def test_collapsing_prose_outside_the_blocks_is_a_finding(tmp_path):
    """The companion to the elision gate: a paragraph deleted outright rather
    than replaced by a marker. Measured on run 27 with the corrected marker
    matching, 05-c fell 11,046 -> 6,867 prose characters (-37.8%) while its
    line count barely moved; the 8,876 figure this docstring first carried was
    produced by the substring bug. (Codex, PR #1061.)"""
    prev, cur = tmp_path / "prev", tmp_path / "cur"
    for d in (prev, cur):
        (d / gate.DEPS).parent.mkdir(parents=True, exist_ok=True)
    body = "Notes on the ones that matter operationally: " + ("x" * 4000) + "\n"
    (prev / gate.DEPS).write_text(body)
    (cur / gate.DEPS).write_text("Notes on the ones that matter operationally:\n")
    out = gate.gate_prose_floor(cur, prev)
    assert len(out) == 1 and "shrank" in out[0], out
    # unchanged prose passes
    (cur / gate.DEPS).write_text(body)
    assert gate.gate_prose_floor(cur, prev) == []


def test_the_prose_floor_ignores_growth_inside_a_rendered_block(tmp_path):
    """A month that adds twenty jobs grows the blocks enormously and must not
    thereby mask prose that was deleted beside them."""
    prev, cur = tmp_path / "prev", tmp_path / "cur"
    for d in (prev, cur):
        (d / gate.DEPS).parent.mkdir(parents=True, exist_ok=True)
    (prev / gate.DEPS).write_text("A real paragraph explaining the graph. " * 40 +
                                "\n<!-- inventory:blast:start -->\nsmall\n<!-- inventory:blast:end -->\n")
    (cur / gate.DEPS).write_text("\n<!-- inventory:blast:start -->\n" + ("| row |\n" * 500) +
                               "<!-- inventory:blast:end -->\n")
    out = gate.gate_prose_floor(cur, prev)
    assert len(out) == 1, out


def test_prose_that_mentions_a_marker_is_not_a_marker(tmp_path):
    """Both documents describe their own markers in prose -- 05-a line 5 says
    "the tables between `<!-- inventory:*:start/end -->` markers". A substring
    test read that sentence as opening a block and skipped everything to the
    next real end marker, keeping 76 of 05-c's 1,403 lines, so an elision in
    the hidden region was invisible to both gates. (Codex, PR #1061.)"""
    doc = tmp_path / gate.DEPS
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "The tables between `<!-- inventory:*:start/end -->` markers are rendered.\n"
        "...\n"
        "<!-- inventory:blast:start -->\n"
        "| a | b |\n"
        "<!-- inventory:blast:end -->\n"
        "A closing paragraph.\n")
    kept = gate._prose_lines(doc.read_text())
    assert "| a | b |" not in kept, "the real block must still be skipped"
    assert any(l.startswith("The tables between") for l in kept)
    assert "A closing paragraph." in kept
    # and the elision beside the descriptive sentence is now visible
    assert len(gate.gate_elided_prose(tmp_path)) == 1, gate.gate_elided_prose(tmp_path)


def test_an_ordered_list_elision_is_a_finding(tmp_path):
    """`1. ...` is the same destruction as `- ...`; 05-a carries numbered prose
    lists and one replaced item can be too small to move the prose floor.
    (Codex, PR #1061.)"""
    doc = tmp_path / gate.ARCH
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("1. ...\n2) …\n3. A real numbered point that says something.\n")
    out = gate.gate_elided_prose(tmp_path)
    assert len(out) == 2, out


def test_a_gutted_fenced_diagram_is_a_finding(tmp_path):
    """05-a's Mermaid topology and flow diagrams are hand-authored inside
    fences. Skipping fenced content hid a diagram replaced by a bare `...` from
    both gates, and each diagram is far too small to move the whole-document
    floor by itself. (Codex, PR #1061.)"""
    doc = tmp_path / gate.ARCH
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("## 2. Topology\n\n```mermaid\n...\n```\n")
    out = gate.gate_elided_prose(tmp_path)
    assert len(out) == 1, out


def test_the_prose_floor_matches_the_size_floor(tmp_path):
    """An earlier revision set 0.90 and called it "lower than SIZE_FLOOR". A
    HIGHER floor permits LESS shrinkage, so it was stricter than the gate it
    claimed to be looser than, and would have failed a refresh that
    legitimately retires a prose-heavy section -- including on the two
    documents SIZE_FLOOR exempts. (Codex, PR #1061.)"""
    assert gate.PROSE_FLOOR == gate.SIZE_FLOOR == 0.80


def test_an_elision_after_the_bullet_separator_is_a_finding(tmp_path):
    """05-c's real bullet style is `- **`name`** — text`. An updater that keeps
    the em dash and elides only the body writes `- **`name`** — ...`, which the
    first regex missed because it required the ellipsis immediately after the
    bold label. One such bullet is far too small to move the prose floor.
    (Codex, PR #1061.)"""
    doc = tmp_path / gate.DEPS
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("- **`market_data_daily`** — ...\n"
                   "- **`etf_options_snapshots`**: …\n"
                   "- **`signal_alerts`** - ...\n"
                   "- **`watchlists`** — `backfill_ticker` manages it; soft-delete via `removed_at`.\n")
    out = gate.gate_elided_prose(tmp_path)
    assert len(out) == 3, out
    assert not any("watchlists" in f for f in out), out


def test_the_prose_floor_honours_the_readme_exemption(tmp_path):
    """README is SIZE_FLOOR_EXEMPT because its length is not a content signal:
    it is a pointer map, and a refresh that retires obsolete rows legitimately
    shortens it. The floor must not reject that. The elision gate still covers
    README, and that signal is exact rather than proportional.
    (Codex, PR #1061.)"""
    prev, cur = tmp_path / "prev", tmp_path / "cur"
    prev.mkdir(); cur.mkdir()
    (prev / "README.md").write_text("A pointer map. " * 400)
    (cur / "README.md").write_text("A pointer map. " * 100)      # -75%
    assert gate.gate_prose_floor(cur, prev) == []
    # but an ellipsis in it is still caught
    (cur / "README.md").write_text("## Docs\n...\n")
    assert len(gate.gate_elided_prose(cur)) == 1


def test_an_elision_inside_a_blockquote_is_a_finding(tmp_path):
    """05-c:7-11 is three blockquoted callouts -- Partition handling, Runtime
    tables, Ad-hoc access -- and 05-a carries five blockquote lines of its own.
    The Runtime tables callout is exactly the kind of content run 27 rewrote.
    Eliding one as `> ...` or `> **Runtime tables.** ...` matched nothing,
    because only list prefixes were accepted, and one callout is too small to
    breach the aggregate floor. (Codex, PR #1061.)"""
    doc = tmp_path / gate.DEPS
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("> ...\n"
                   "> **Runtime tables.** ...\n"
                   ">> …\n"
                   "> **Ad-hoc access.** `db_query_cr.sh` reaches Cloud SQL over 443.\n")
    out = gate.gate_elided_prose(tmp_path)
    assert len(out) == 3, out
    assert not any("Ad-hoc" in f for f in out), out


def test_every_prose_line_shape_in_the_real_documents_can_be_caught():
    """Derived from the corpus, not from the incident.

    Four review rounds each found another shape the matcher missed -- ordered
    lists, fenced diagrams, the em-dash bullet style, blockquotes -- because it
    was written against the nine lines run 27 happened to damage rather than
    against the shapes these documents actually use. This enumerates the
    leading structure of every prose line in the four regenerated documents and
    asserts an elision in each of them is caught, so a shape the corpus already
    contains cannot slip past again. (Codex, PR #1061.)
    """
    root = pathlib.Path(__file__).resolve().parents[2]
    shapes = set()
    for doc in gate.DOCS:
        for line in gate._prose_lines((root / doc).read_text()):
            if not line.strip():
                continue
            if line.strip().startswith("|"):
                # a table row elides by cell, not at end of line; flattening it
                # to a bare "..." is what hid that gap from this test before
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                row = "| " + " | ".join(["..."] + cells[1:]) + " |"
                assert gate._is_elided(row), f"an elided table row is not caught: {row!r}"
                continue
            m = re.match(r"^(\s*(?:>\s*)*)((?:[-*+]|\d+[.)])\s+)?(.*)$", line)
            bq, lst, body = bool(m.group(1).strip()), bool(m.group(2)), m.group(3)
            # The label FORM matters, not just its presence. An earlier version
            # of this test recognised only `**bold**` as a label, so it could
            # not discover the inline-code (15 lines) and plain-text (4) list
            # labels the corpus also uses -- the same blind spot as the matcher
            # it was written to police. (Codex, PR #1061.)
            if body.startswith("**"):
                label = "**x**"
            elif body.startswith("`"):
                # a REAL code label, dots and all: normalising it to `x` is
                # what hid a dotted filename from this test
                label = re.match(r"^(`[^`]*`)", body).group(1)
            elif re.match(r"^[A-Za-z][^.!?]{0,60}?[—–:-]\s", body):
                label = "Open paths:"
            else:
                label = ""
            shapes.add((bq, lst, label))
    assert shapes, "no prose found — the marker matching is broken"
    for bq, lst, label in sorted(shapes):
        for sep in ("", " — "):
            line = (("> " if bq else "") + ("- " if lst else "")
                    + (label + sep if label else "") + "...")
            if not (bq or lst) and label not in ("**x**", ""):
                continue   # a free-form label is only read as one behind a marker
            assert gate._is_elided(line), \
                f"a shape the documents already use is not caught: {line!r}"


def test_an_elision_after_a_non_bold_label_is_a_finding(tmp_path):
    """The corpus labels list items four ways, and only one is bold: measured
    on the four documents, 30 bullets open with `**bold**`, 30 with plain text,
    15 with `inline code` and 4 with a plain label and a separator. Successive
    revisions of the matcher each covered the form the last incident used, so
    `- `AUTH_MODE` — ...` and `- Open paths: ...` still went through.
    (Codex, PR #1061.)"""
    doc = tmp_path / gate.ARCH
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("- `AUTH_MODE` — ...\n"
                   "- Open paths: ...\n"
                   "1. `strat_combo_results` ...\n"
                   "- `AUTH_MODE` is one of `iap`, `firebase` or `open` (auth.py:34).\n")
    out = gate.gate_elided_prose(tmp_path)
    assert len(out) == 3, out
    assert not any("firebase" in f for f in out), out


def test_a_sentence_ending_in_an_ellipsis_is_not_a_finding(tmp_path):
    """The broad label form is only safe because it cannot swallow a real
    sentence. Measured: no line in the four documents ends in an ellipsis
    today, and a label may not carry sentence-ending punctuation, so prose
    that happens to trail off is still prose. (Codex, PR #1061.)"""
    doc = tmp_path / gate.ARCH
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("The fetchers run at 08:20, 08:30, ... and 23:00.\n"
                   "- **`watchlists`** — `backfill_ticker` manages it; soft-delete via `removed_at`.\n"
                   "27 runtime-created relations (`strat_features_*`, `gamma_levels_eod`, …) are outside.\n")
    assert gate.gate_elided_prose(tmp_path) == []


def test_bare_prose_ending_in_an_ellipsis_is_not_an_elision(tmp_path):
    """The free-form label is only a label behind a blockquote or list marker.
    Allowing it on a bare line made any short sentence without terminal
    punctuation match, so `Loading...` and `This section continues…` would have
    failed a legitimate refresh. My earlier "must not match" test did not
    exercise this: none of its lines actually ended in an ellipsis, so it
    proved nothing about the case that mattered. (Codex, PR #1061.)"""
    doc = tmp_path / gate.ARCH
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("Loading...\n"
                   "This section continues…\n"
                   "See the runbook for the rest ...\n")
    assert gate.gate_elided_prose(tmp_path) == []
    # behind a marker the same text IS a label, and the line is an elision
    doc.write_text("- Loading: ...\n")
    assert len(gate.gate_elided_prose(tmp_path)) == 1


def test_an_elided_table_row_is_a_finding(tmp_path):
    """A row keeps its label cell and loses its explanation:
    `| Cloud SQL | ... |`. The end-of-line matcher cannot see it because the
    row ends in a pipe. Measured, the corpus carries 171 prose table rows over
    503 cells and not one cell is an ellipsis today, so an ellipsis-only cell
    is an elision rather than a truncation mark. (Codex, PR #1061.)"""
    doc = tmp_path / gate.ARCH
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("| Component | Notes |\n|---|---|\n"
                   "| Cloud SQL | ... |\n"
                   "| Cloud Run | … |\n"
                   "| Scheduler | 65 jobs, all reconciled against `deploy.sh`. |\n")
    out = gate.gate_elided_prose(tmp_path)
    assert len(out) == 2, out
    assert not any("Scheduler" in f for f in out), out


def test_a_markdown_wrapped_ellipsis_is_an_elision(tmp_path):
    """`- **...**` and `` - `...` `` render as an ellipsis-only body: the
    updater kept the emphasis or code wrapper and deleted the text inside it.
    A syntax-enumerating matcher treated the bold form as a label with no
    ellipsis after it and rejected the code form outright, which is why this
    check now strips decoration and then asks one question. (Codex, PR #1061.)"""
    doc = tmp_path / gate.DEPS
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("- **...**\n- `...`\n**…**\n"
                   "- **`watchlists`** — `backfill_ticker` manages it.\n")
    out = gate.gate_elided_prose(tmp_path)
    assert len(out) == 3, out
    assert not any("watchlists" in f for f in out), out


def test_a_dotted_label_is_still_a_label(tmp_path):
    """A period inside a code span or a bold run belongs to a name, not to a
    sentence: `gcp/fetchers/fetch_rss_news.py` is a filename and
    **Runtime tables.** is a callout label. Rejecting every period lost list
    and blockquote shapes both documents already use, while a genuine sentence
    before an ellipsis must still be left alone. (Codex, PR #1061.)"""
    doc = tmp_path / gate.ARCH
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("3. `gcp/fetchers/fetch_rss_news.py` ...\n"
                   "> **Runtime tables.** ...\n"
                   "**Note.** ...\n"
                   "This is a complete sentence. ...\n")
    out = gate.gate_elided_prose(tmp_path)
    assert len(out) == 3, out
    assert not any("complete sentence" in f for f in out), out


def test_a_line_that_is_the_tail_of_the_one_above_is_a_finding(tmp_path):
    """Run 28's 05-a ended with the last line's own tail, starting mid-word:

        ... from the 2026-09-08 live snapshot. The monthly refresh updates this line.
        pshot. The monthly refresh updates this line.

    A `replace` rewrote the trailing span and left the end of the old text
    behind. The elision gate does not see it, the churn was 12%, the headings
    were intact, and it names no infrastructure, so the live verifier had
    nothing to check either. It reached the artifact with 0 findings.
    """
    doc = tmp_path / gate.ARCH
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "Generated 2026-09-08; inventory blocks rendered by `doc_inventory.py` "
        "from the 2026-09-08 live snapshot. The monthly refresh updates this line.\n"
        "pshot. The monthly refresh updates this line.\n")
    out = gate.gate_duplicated_tail(tmp_path)
    assert len(out) == 1, out
    assert "tail of the one above" in out[0]


def test_the_committed_documents_carry_no_duplicated_tail(tmp_path):
    """Calibration, not decoration. The threshold and the single direction were
    chosen by measuring every markdown file under `docs/` plus README against
    all four shapes: this one fires once, on the real defect. A future
    loosening that starts flagging honest prose fails here."""
    assert gate.gate_duplicated_tail(gate.REPO) == []


def test_a_repeated_command_prefix_is_not_a_duplicated_tail(tmp_path):
    """Both lines below are lifted from the committed corpus, because an
    invented example proves nothing about it -- a first draft of this test
    hand-wrote a `gcloud` continuation that WAS a duplicated tail, which the
    real file at `COST_AUDIT_2026-09-06.md:260` is not.

    `docs/alpha-vantage-quickstart.md:26` shows the same command twice with an
    extra flag, so each line is a PREFIX of the next; `COST_AUDIT` wraps a
    `gcloud` invocation so the following line ENDS WITH the one before it.
    Gating on either shape would fail an honest document, so neither is gated.
    """
    doc = tmp_path / gate.ARCH
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "python scripts/fetch_alphavantage_intraday.py --symbol IWM --show\n"
        "python scripts/fetch_alphavantage_intraday.py --symbol IWM --show --rows 200\n"
        "    trading-runner@adept-mountain-474619-d4.iam.gserviceaccount.com \\\n"
        "    --member=serviceAccount:trading-runner@adept-mountain-474619-d4.iam"
        ".gserviceaccount.com \\\n")
    assert gate.gate_duplicated_tail(tmp_path) == []


def test_a_short_repeated_ending_is_not_a_duplicated_tail(tmp_path):
    """Two rows ending in the same short cell are a table, not a botched
    replace. The 20-character floor is what separates them."""
    doc = tmp_path / gate.ARCH
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("| `signal-monitor` | main |\n| main |\n")
    assert gate.gate_duplicated_tail(tmp_path) == []


def test_an_asof_label_naming_an_older_snapshot_is_a_finding(tmp_path):
    """Run 28 updated 05-a's header to `read on **2026-09-08**` and left §3's
    table header at `Live 2026-09-07`, so a table of the current fleet
    announced itself as a day old. On the monthly cadence the label is a month
    out. The dates inside the marker blocks are rendered and were right; these
    two are prose."""
    doc = tmp_path / gate.ARCH
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("> Live state below was read on **2026-09-08** with `gcloud`.\n"
                   "\n| Service | Role | Live 2026-09-07 |\n")
    out = gate.gate_stale_asof(tmp_path, {"read_at": "2026-09-08T17:48:56Z"})
    assert len(out) == 1, out
    assert "Live 2026-09-07" in out[0]


def test_a_historical_date_is_not_an_asof_label(tmp_path):
    """05-a carries 33 occurrences of `2026-09-07`, and all but two record when
    something was corrected, deleted or audited. A gate that moved those would
    rewrite the document's history, so only the two literal label shapes are
    matched."""
    doc = tmp_path / gate.ARCH
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("Storage corrected 2026-09-07 in this doc, which had said 55 GB.\n"
                   "`signal-quality-report-hourly` deleted 2026-09-07.\n"
                   "See [the audit](../../audits/ARCHITECTURE_DOCS_AUDIT_2026-09-07.md).\n")
    assert gate.gate_stale_asof(tmp_path, {"read_at": "2026-09-08T17:48:56Z"}) == []


def test_the_committed_asof_labels_match_their_own_snapshot():
    """Calibration against the real corpus, in both directions: the committed
    documents are clean as of the date they were written, and both labels are
    caught the moment the snapshot moves. A gate that fired on neither, or on
    everything, would pass the constructed cases above just as well."""
    assert gate.gate_stale_asof(gate.REPO, {"read_at": "2026-09-07T04:35:16Z"}) == []
    # Three labels: the header note, §3's table column, and the snapshot date
    # in the closing line.
    assert len(gate.gate_stale_asof(gate.REPO, {"read_at": "2026-09-08T17:48:56Z"})) == 3


def test_no_snapshot_means_no_asof_finding(tmp_path):
    """A local run without `--snapshot` has nothing to compare against, and
    guessing today's date would fail every document written yesterday."""
    doc = tmp_path / gate.ARCH
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("| Service | Role | Live 2020-01-01 |\n")
    assert gate.gate_stale_asof(tmp_path, None) == []
    assert gate.gate_stale_asof(tmp_path, {}) == []


def test_the_relation_breakdown_must_sum_to_the_total(live, repo, tmp_path):
    """05-a §5 says `declares **70 relations** (67 tables, 2 materialized
    views, 1 view)`. Run 28 raised the total from 69 to 70 -- correctly,
    `gcp/schema.sql` had gained a table -- and left the breakdown at 66/2/1,
    which sums to 69. The sentence contradicted itself and every gate passed
    it: the total was right, the churn was 12%, and no other document repeats
    the split."""
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    assert gate.gate_derived_numbers(root, repo, live) == []
    a = root / gate.ARCH
    a.write_text(a.read_text().replace(
        "declares **70 relations** (67 tables,", "declares **70 relations** (66 tables,"))
    findings = gate.gate_derived_numbers(root, repo, live)
    assert any("claims 66 tables" in f for f in findings), findings


def test_a_wrong_relation_total_is_a_finding(live, repo, tmp_path):
    """The other half: the parts can agree with each other and disagree with
    the schema."""
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    a = root / gate.ARCH
    a.write_text(a.read_text().replace("declares **70 relations**", "declares **69 relations**"))
    findings = gate.gate_derived_numbers(root, repo, live)
    assert any("claims 69 declared relations" in f for f in findings), findings


def test_the_breakdown_is_matched_as_parts_not_a_fixed_triple(live, repo, tmp_path):
    """A schema that grows a second view must still be checked. Matching a
    literal `(N tables, N materialized views, N view)` shape would stop
    matching entirely on a reword and fail open, which is the worse
    direction for a gate."""
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    a = root / gate.ARCH
    a.write_text(a.read_text().replace(
        "declares **70 relations** (67 tables, 2 materialized views, 1 view)",
        "declares **70 relations** (1 view, 2 materialized views and 99 tables)"))
    findings = gate.gate_derived_numbers(root, repo, live)
    assert any("claims 99 tables" in f for f in findings), findings


def test_both_copies_of_the_relation_breakdown_are_checked(live, repo, tmp_path):
    """05-a states the schema arithmetic twice, in two shapes: §5's `declares
    **70 relations** (67 tables, ...)` and §3's table cell `95 relations (70
    declared in `gcp/schema.sql` — 67 tables, ...)`.

    A gate anchored on §5's phrasing alone left §3 unchecked, and I proved the
    point by hand: I corrected §5 to 70/67 and left §3 at 69/66 -- the same
    reading-instead-of-deriving mistake Codex named on #1009, made while
    fixing that exact sentence."""
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    assert gate.gate_derived_numbers(root, repo, live) == []
    a = root / gate.ARCH
    a.write_text(a.read_text().replace(
        "95 relations (70 declared in `gcp/schema.sql` — 67 tables,",
        "95 relations (69 declared in `gcp/schema.sql` — 66 tables,"))
    findings = gate.gate_derived_numbers(root, repo, live)
    assert any("claims 69 declared relations" in f for f in findings), findings
    assert any("claims 66 tables" in f for f in findings), findings


def test_a_subset_count_beside_a_view_count_is_not_a_breakdown(live, repo, tmp_path):
    """Parts are read only from the clause a DECLARED TOTAL introduces, bounded
    by the first `)` or `;` after it.

    An earlier version recognised the breakdown by shape alone -- a numbered
    table count somewhere near a numbered materialized-view count -- and then
    compared every number on that line against the whole-schema totals. Both
    documents count subsets in passing, so a sentence like the one below would
    have failed a refresh whose numbers were correct. Anchoring on the total
    means such a sentence is never examined at all. (Codex, PR #1062.)"""
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    a = root / gate.ARCH
    a.write_text(a.read_text() +
                 "\n12 runtime tables feed 2 materialized views on the weekly refresh.\n"
                 "\n`apply_schema.py` drops and recreates the two earnings materialized views.\n")
    assert gate.gate_derived_numbers(root, repo, live) == []


def test_the_snapshot_date_in_the_closing_line_is_an_asof_label(tmp_path):
    """05-a's closing line carries two dates: `Generated <date> ... from the
    <date> live snapshot`. A refresh that updated one and not the other would
    leave the line contradicting itself.

    Only the second is gated here. The first is already required to equal
    today by the workflow's own step 1, which greps all four documents for
    `Generated ${TODAY}` before this script runs, and gating it here would
    fail an honest tree: the committed 05-d carries `Generated 2026-09-02`,
    the last run that regenerated it. (Codex, PR #1062.)"""
    doc = tmp_path / gate.ARCH
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("Generated 2026-09-08 by the refresh; blocks rendered "
                   "from the 2026-09-07 live snapshot.\n")
    out = gate.gate_stale_asof(tmp_path, {"read_at": "2026-09-08T17:48:56Z"})
    assert len(out) == 1, out
    assert "2026-09-07 live snapshot" in out[0]
    doc.write_text(doc.read_text().replace("the 2026-09-07 live", "the 2026-09-08 live"))
    assert gate.gate_stale_asof(tmp_path, {"read_at": "2026-09-08T17:48:56Z"}) == []
