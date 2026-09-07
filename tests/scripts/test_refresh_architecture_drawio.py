"""Regression tests for the drawio companion regenerator.

Every count on the diagrams has now gone stale at least once, and each time
the mechanism was the same: a number reachable only through a one-time
literal in REPLACEMENTS. Once that literal is consumed by the first
regeneration, the cell is unreachable forever and `--check` stays green
beside a diagram that contradicts itself.

The cases pinned here are the two Codex found on PR #1009:

  * `sec_box` read "Secret Manager - 21 secrets" while the subtitle on the
    same page read 22, and
  * `ext_gh` read "(5 workflows)" against six active YAMLs, because nothing
    ever populated `live["_workflows"]` -- so `gha_group` silently dropped
    its count too.

Both are asserted through `check()`, which is what a monthly run consults.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import scripts.maintenance.refresh_architecture_drawio as dw

REPO = Path(__file__).resolve().parents[2]
SNAPSHOT = REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json"


@pytest.fixture
def live() -> dict:
    d = json.loads(SNAPSHOT.read_text())
    d["_workflows"] = dw.active_workflows()
    return d


@pytest.fixture
def main_root() -> ET.Element:
    return ET.parse(dw.MAIN).getroot()


def _cell(root: ET.Element, cid: str) -> ET.Element:
    for c in root.iter("mxCell"):
        if c.get("id") == cid:
            return c
    raise AssertionError(f"cell {cid} not in the diagram")


def test_the_committed_diagram_agrees_with_the_snapshot(main_root, live):
    assert dw.check(main_root, live) == []


def test_a_stale_secret_count_in_any_cell_is_caught(main_root, live):
    """sec_box said 21 while the subtitle said 22, and check() was silent."""
    c = _cell(main_root, "sec_box")
    c.set("value", c.get("value").replace("22 secrets", "21 secrets", 1))
    problems = dw.check(main_root, live)
    assert any("sec_box says 21 secrets, live is 22" in p for p in problems), problems


def test_a_stale_workflow_count_is_caught(main_root, live):
    # Derived from the fixture, not written as a literal: adding a workflow to
    # the repo used to break this test rather than exercise it, which is the
    # failure the test below is specifically about.
    n = len(live["_workflows"])
    c = _cell(main_root, "ext_gh")
    c.set("value", c.get("value").replace(f"({n} workflows)", f"({n - 1} workflows)", 1))
    problems = dw.check(main_root, live)
    assert any(f"ext_gh says {n - 1} workflows" in p for p in problems), problems


def test_the_workflow_count_tracks_the_repo_not_a_literal(main_root, live):
    """One more workflow must move the cell, not just the assertion.

    The earlier fix wrote the count once from REPLACEMENTS; this asserts the
    value is derived, by moving the input and requiring the output to follow.
    Both counts here come from the fixture for the same reason -- pinning them
    made the test itself the literal it was written to forbid.
    """
    n = len(live["_workflows"])
    live_plus = dict(live, _workflows=live["_workflows"] + ["a-new-one.yml"])
    assert any(f"ext_gh says {n} workflows, live is {n + 1}" in p
               for p in dw.check(main_root, live_plus))
    dw._rewrite_main_counts(main_root, live_plus)
    assert f"({n + 1} workflows)" in _cell(main_root, "ext_gh").get("value")
    assert dw._check_main_counts(main_root, live_plus) == []


def test_active_workflows_excludes_retired_files(tmp_path):
    """`*.yml.disabled` is the repo's retirement convention (CLAUDE.md)."""
    wf = tmp_path / ".github/workflows"
    wf.mkdir(parents=True)
    (wf / "live-one.yml").write_text("name: x\n")
    (wf / "also-live.yaml").write_text("name: y\n")
    (wf / "retired.yml.disabled").write_text("name: z\n")
    assert dw.active_workflows(tmp_path) == ["live-one.yml"]


def test_every_count_bearing_main_cell_is_rewritten(main_root, live):
    """No count-bearing cell may be reachable only through REPLACEMENTS.

    Scans the committed diagram for the patterns the rewrite understands and
    requires the rewrite to own every occurrence -- the property that was
    missing when sec_box drifted.
    """
    stale = 0
    for c in main_root.iter("mxCell"):
        v = c.get("value") or ""
        for pat, key, _noun in dw.MAIN_COUNT_PATTERNS:
            import re
            for m in re.finditer(pat, v):
                bumped = m.group(0).replace(m.group(1), str(int(m.group(1)) + 1), 1)
                c.set("value", v.replace(m.group(0), bumped, 1))
                stale += 1
                break
    assert stale, "the diagram carries no count-bearing cells — the scan is wrong"
    assert dw._check_main_counts(main_root, live), "a bumped count went unnoticed"
    dw._rewrite_main_counts(main_root, live)
    assert dw._check_main_counts(main_root, live) == []


def test_a_stale_service_count_is_caught(main_root, live):
    """svc_group reads "Cloud Run Services (4; ...)" and was not in the rewrite
    set, so a fifth service would move the subtitle and leave it at four.
    (Codex, PR #1009.)"""
    live5 = dict(live, counts=dict(live["counts"], services=5))
    problems = dw.check(main_root, live5)
    assert any("svc_group says 4 Cloud Run Services, live is 5" in p for p in problems), problems
    dw._rewrite_main_counts(main_root, live5)
    assert "Cloud Run Services (5;" in _cell(main_root, "svc_group").get("value")


def test_the_deleted_prod_service_name_is_rejected(main_root, live):
    """`trading-platform` the SERVICE is deleted; check() rejected only
    `trading-platform-staging`, so three cells kept the dead name."""
    c = _cell(main_root, "svc_tp")
    c.set("value", c.get("value").replace("solyra-api-prod", "trading-platform", 1))
    problems = dw.check(main_root, live)
    assert any("trading-platform" in p and "deleted" in p for p in problems), problems


def test_the_service_account_name_is_not_mistaken_for_the_service(main_root, live):
    """`trading-platform-svc@` is live and must not trip the stale-name check."""
    assert "trading-platform-svc" in ET.tostring(main_root, encoding="unicode")
    assert dw.check(main_root, live) == []


def test_every_live_service_must_be_drawn(main_root, live):
    live5 = dict(live, services=dict(live["services"], **{"brand-new-svc": {}}),
                 counts=dict(live["counts"], services=5))
    problems = dw.check(main_root, live5)
    assert any("brand-new-svc" in p for p in problems), problems
