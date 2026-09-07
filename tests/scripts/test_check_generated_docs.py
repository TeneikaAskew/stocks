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
