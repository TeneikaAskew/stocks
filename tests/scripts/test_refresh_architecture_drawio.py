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
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import scripts.maintenance.refresh_architecture_drawio as dw

REPO = Path(__file__).resolve().parents[2]
# The diagrams are generated from this read (2026-10-11, after #1366 deleted
# solyra-api-prod). live_gcp_snapshot_2026-09-07.json stays for the suites
# that share it; this test moved to the fresh read.
SNAPSHOT = REPO / "tests/fixtures/live_gcp_snapshot_2026-10-11.json"
DIAGRAMS = ("Architecture.drawio", "Architecture-icons.drawio")
RETIRED_SERVICE = "solyra-api-prod"
RETIRED_TRIGGER = "deploy-solyra-api-prod"
# svc_tp draws the one live API service and keeps the edges it always had.
API_SERVICE_EDGES = {"e_browser_tp", "e_tp_sql", "e_tp_ct", "e_lib_tp"}
# Text the generator may no longer write: the retired service, the two-service
# label, and the IAP auth mode no deployed service runs.
FORBIDDEN = ("solyra-api-prod", "staging / -prod", "IAP", "AUTH_MODE iap", "AUTH_MODE=iap")


def _diagram_copies(tmp_path: Path, monkeypatch) -> list[tuple[Path, Path]]:
    """Point the generator at copies of both committed diagrams, so a test
    that runs main() can show what it would have written without touching
    the files in the repo. Returns (committed, copy) pairs."""
    pairs = []
    for name, attr in zip(DIAGRAMS, ("MAIN", "ICONS")):
        committed = REPO / name
        copy = tmp_path / name
        shutil.copyfile(committed, copy)
        monkeypatch.setattr(dw, attr, copy)
        pairs.append((committed, copy))
    return pairs


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
    assert dw.check_icons(ET.parse(dw.ICONS).getroot(), live) == []


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
    n = live["counts"]["services"]
    live_plus = dict(live, counts=dict(live["counts"], services=n + 1))
    problems = dw.check(main_root, live_plus)
    assert any(f"svc_group says {n} Cloud Run Services, live is {n + 1}" in p for p in problems), problems
    dw._rewrite_main_counts(main_root, live_plus)
    assert f"Cloud Run Services ({n + 1};" in _cell(main_root, "svc_group").get("value")


def test_the_deleted_prod_service_name_is_rejected(main_root, live):
    """`trading-platform` the SERVICE is deleted; check() rejected only
    `trading-platform-staging`, so three cells kept the dead name."""
    c = _cell(main_root, "svc_tp")
    c.set("value", c.get("value").replace("solyra-api-staging", "trading-platform", 1))
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


@pytest.mark.parametrize("tables", [None, {}], ids=["missing", "empty"])
def test_main_refuses_a_snapshot_without_db_tables(tmp_path, monkeypatch, tables):
    """A snapshot taken without table statistics (the sandbox default) used
    to regenerate both diagrams as "0 relations" and pass check(): a silent
    fallback (Rule 3.7). main() must refuse it and write neither file."""
    snap = json.loads(SNAPSHOT.read_text())
    if tables is None:
        del snap["db_tables"]
    else:
        snap["db_tables"] = tables
    path = tmp_path / "live.json"
    path.write_text(json.dumps(snap))
    pairs = _diagram_copies(tmp_path, monkeypatch)
    assert dw.main(["--snapshot", str(path)]) != 0
    for committed, copy in pairs:
        assert copy.read_bytes() == committed.read_bytes(), committed.name


def test_an_add_on_job_is_labelled_by_digest_prefix_or_tag(main_root, live):
    """Every live job now runs an image pinned by digest. The grid took the
    text after the first `:` as the tag, so a digest printed all 64 hex
    characters in a 240-pixel box, and `name:tag@sha256:...` printed
    `research@sha256`."""
    page = main_root.findall("diagram")[0]

    def cards() -> dict[str, str]:
        return {c.get("value").split("\n")[0].replace(" ★", ""): c.get("value")
                for c in page.iter("mxCell") if (c.get("id") or "").startswith("addon_job_")}

    pinned, tagged, both = sorted(cards())[:3]
    digest = "0123456789ab" + "c" * 52
    repo = "us-east1-docker.pkg.dev/p/trading/trading-system"
    jobs = dict(live["jobs"])
    jobs[pinned] = dict(jobs[pinned], image=f"{repo}@sha256:{digest}")
    jobs[tagged] = dict(jobs[tagged], image=f"{repo}:research")
    jobs[both] = dict(jobs[both], image=f"{repo}:research@sha256:{digest}")
    dw.refresh_main(main_root, dict(live, jobs=jobs))
    assert "• sha256:0123456789ab •" in cards()[pinned]
    assert digest not in cards()[pinned]
    assert "• research •" in cards()[tagged]
    assert "• sha256:0123456789ab •" in cards()[both]


def test_the_snapshot_lists_no_retired_service(live):
    """solyra-api-prod and its promote trigger were deleted on 2026-10-10
    (#1366); the snapshot the diagrams are generated from must not list them."""
    assert RETIRED_SERVICE not in live["services"]
    assert RETIRED_TRIGGER not in {t["name"] for t in live["cloudbuild_triggers"]}


def test_no_generated_text_names_the_retired_service(main_root, live):
    """Every label the generator writes: REPLACEMENTS targets, NEW_CELLS, the
    add-on notes and cards it regenerates on the main page, and the icon
    page's reconciliation notes."""
    dw.refresh_main(main_root, live)
    notes = [c.get("value") for c in main_root.iter("mxCell")
             if (c.get("id") or "").startswith(dw.ADDON_PREFIX)]
    icons = ET.parse(dw.ICONS).getroot()
    dw.refresh_icons(icons, live)
    notes += [c.get("value") for c in icons.iter("mxCell")
              if "reconciliation note" in (c.get("value") or "").lower()]
    written = [rep for _old, rep in dw.REPLACEMENTS] + [cell[1] for cell in dw.NEW_CELLS] + notes
    assert [(bad, t) for t in written for bad in FORBIDDEN if bad in t] == []


@pytest.mark.parametrize("stale", ["solyra-api-prod", "staging / -prod"])
def test_check_reports_a_cell_naming_the_retired_service(main_root, live, stale):
    c = _cell(main_root, "svc_tp")
    c.set("value", c.get("value") + "\n" + stale)
    assert f"stale label still present: {stale}" in dw.check(main_root, live)


@pytest.mark.parametrize("stale", ["solyra-api-prod", "staging / -prod"])
def test_check_icons_reports_a_cell_naming_the_retired_service(live, stale):
    icons = ET.parse(dw.ICONS).getroot()
    c = _cell(icons, "ic_tp")
    c.set("value", c.get("value") + " " + stale)
    assert f"icons: stale label {stale!r}" in dw.check_icons(icons, live)


@pytest.mark.parametrize("name", DIAGRAMS)
def test_the_committed_diagrams_do_not_draw_the_retired_service(name):
    text = (REPO / name).read_text(encoding="utf-8")
    for gone in ("solyra-api-prod", "staging / -prod", "2026-09-07"):
        assert gone not in text, gone


@pytest.mark.parametrize("path,cid", [(dw.MAIN, "p4_tp"), (dw.ICONS, "tp_txt")], ids=["p4_tp", "tp_txt"])
def test_the_api_cells_describe_no_prod_or_iap_service(path, cid):
    value = _cell(ET.parse(path).getroot(), cid).get("value")
    assert not re.search(r"\bprod\b|IAP", value), value


def test_a_stale_relation_count_on_the_icon_page_is_caught_and_rewritten(live):
    """The icon subtitle `sub` reads "N-relation Cloud SQL". refresh_icons and
    check_icons knew "N relations" only, so the 2026-10-11 regeneration left
    it at 95 while every note read 98."""
    icons = ET.parse(dw.ICONS).getroot()
    n = len(live["db_tables"])
    sub = _cell(icons, "sub")
    sub.set("value", re.sub(r"\b\d+-relation\b", f"{n - 1}-relation", sub.get("value")))
    assert f"icons: cell sub says {n - 1} relations, live is {n}" in dw.check_icons(icons, live)
    dw.refresh_icons(icons, live)
    assert f"{n}-relation Cloud SQL" in sub.get("value")
    assert dw.check_icons(icons, live) == []


def test_the_main_page_draws_one_box_per_live_api_service(main_root, live):
    """svc_tp is the staging service box and keeps its four edges; svc_st, a
    second box for the same service, and gha_dep, the deleted prod promote
    trigger, are gone, so gha_ds is the only deploy-solyra-api-staging box."""
    page = main_root.findall("diagram")[0]
    api = {s for s in live["services"] if s.startswith("solyra-api-")}
    boxes = sorted(c.get("id") for c in page.iter("mxCell")
                   if c.get("vertex") == "1" and (c.get("value") or "").split("\n")[0] in api)
    assert boxes == ["svc_tp"]
    edges = {c.get("id") for c in page.iter("mxCell")
             if "svc_tp" in (c.get("source"), c.get("target"))}
    assert API_SERVICE_EDGES <= edges, API_SERVICE_EDGES - edges
    deploys = sorted(c.get("id") for c in page.iter("mxCell")
                     if (c.get("value") or "").startswith("Cloud Build: deploy-solyra-api-staging"))
    assert deploys == ["gha_ds"]
