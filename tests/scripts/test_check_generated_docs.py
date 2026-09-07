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
DOCS = ("ARCHITECTURE.md", "DATA_DEPENDENCIES.md", "COST_ANALYSIS.md", "README.md", "docs/API.md")


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
    text = (root / "ARCHITECTURE.md").read_text()
    s = inv.MARKER_START.format(name="jobs")
    text = text.replace(s, s + "\n| `hand-edited-row` | x | x | x | x | x |", 1)
    (root / "ARCHITECTURE.md").write_text(text)
    assert any("marker block differs" in f for f in gate.gate_markers(root, repo, live))


def test_removing_both_markers_of_a_block_is_a_finding(live, repo, tmp_path):
    root = tmp_path
    for d in DOCS:
        _copy(REPO / d, root / d)
    text = (root / "DATA_DEPENDENCIES.md").read_text()
    s, e = inv.MARKER_START.format(name="orphans"), inv.MARKER_END.format(name="orphans")
    import re
    text = re.sub(re.escape(s) + r".*?" + re.escape(e), "", text, flags=re.S)
    (root / "DATA_DEPENDENCIES.md").write_text(text)
    findings = gate.gate_markers(root, repo, live)
    assert any("inventory:orphans block is missing entirely" in f for f in findings), findings


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
    old = (prev / "ARCHITECTURE.md").read_text().splitlines()
    heads = [ln for ln in old if ln.startswith("#")]
    body = ["Every other line replaced with different prose." for _ in range(len(old) - len(heads))]
    (root / "ARCHITECTURE.md").write_text("\n".join(heads + body) + "\n")
    stats = {st["doc"]: st for st in gate.diff_stats(root, prev)}
    assert stats["ARCHITECTURE.md"]["churn"] > 0.5
    findings = gate.gate_diff_budget(list(stats.values()))
    assert any("ARCHITECTURE.md" in f and "rewrite" in f for f in findings), findings
    # ...and a human reconstructing that one doc can say so, for that doc only
    assert gate.gate_diff_budget(list(stats.values()), allow_rewrite=("ARCHITECTURE.md",)) == []


def test_diff_stats_report_names_what_moved(tmp_path):
    root, prev = tmp_path, tmp_path / "previous"
    prev.mkdir()
    for d in DOCS:
        _copy(REPO / d, root / d)
        _copy(REPO / d, prev / d)
    text = (root / "COST_ANALYSIS.md").read_text()
    (root / "COST_ANALYSIS.md").write_text(text + "\n## A brand new section\n\nbody\n")
    stats = gate.diff_stats(root, prev)
    report = gate.render_report(stats)
    assert "A brand new section" in report and "+added" in report
    cost = next(st for st in stats if st["doc"] == "COST_ANALYSIS.md")
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
    four = ("ARCHITECTURE.md", "DATA_DEPENDENCIES.md", "COST_ANALYSIS.md", "README.md")
    for d in four:
        for rev, dest in (("b3b5271", prev), ("e50c759", root)):
            out = subprocess.run(["git", "show", f"{rev}:{d}"], cwd=REPO,
                                 capture_output=True, text=True)
            if out.returncode:
                pytest.skip(f"{d} not present at {rev} in this clone")
            (dest / d).parent.mkdir(parents=True, exist_ok=True)
            (dest / d).write_text(out.stdout)

    stats = {st["doc"]: st for st in gate.diff_stats(root, prev)}
    assert stats["ARCHITECTURE.md"]["churn"] > 0.80, stats["ARCHITECTURE.md"]["churn"]
    assert stats["DATA_DEPENDENCIES.md"]["churn"] > 0.80

    caught = set()
    for f in gate.gate_diff_budget(list(stats.values())) + gate.gate_headings_and_size(root, prev):
        caught.add(f.split(":")[0])
    for d in four:
        assert d in caught, f"{d} would have shipped unnoticed; caught={caught}"


def test_lost_heading_and_shrink_are_findings(tmp_path):
    root = tmp_path
    prev = tmp_path / "previous"
    prev.mkdir()
    for d in DOCS:
        _copy(REPO / d, root / d)
        _copy(REPO / d, prev / d)
    text = (root / "ARCHITECTURE.md").read_text()
    cut = text.find("## 10. Data flows")
    (root / "ARCHITECTURE.md").write_text(text[:cut] + "\n## 10. Data flows\n\n## 19. Glossary\n")
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
