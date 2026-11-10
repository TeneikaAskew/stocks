"""Tests for scripts/maintenance/architecture_export.py (FEAT-CICD-001).

Spec: docs/superpowers/specs/2026-11-10-feat-cicd-001-architecture-export.md

The export replaces the monthly model-written ARCHITECTURE.md refresh as the
source for the backend diagram. Each test below pins one done_when item of
the spec: the export's shape, that it takes every fact from doc_inventory
(no second parser), that it keeps unresolved table families and scheduler
targets as the inventory has them, that it is deterministic, that it records
and enforces its provenance, and that live counts it never read stay null.

The real-repo runs use a temporary clone of HEAD so the provenance check sees
a clean tree whatever the developer has uncommitted, and share one clone and
one inventory per module because an inventory of the real tree takes ~17s.
"""
from __future__ import annotations

import ast
import copy
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

from scripts.maintenance import architecture_export as ax
from scripts.maintenance import doc_inventory as inv
from tests.scripts.test_doc_inventory import DEPLOY_SNIPPET, SCHEMA_SNIPPET, _write

REPO = pathlib.Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
MODULE = REPO / "scripts/maintenance/architecture_export.py"
STUB_SOURCES = {"commit": "0" * 40, "files": {}}
LINE_CITE = re.compile(r"[\w./-]+\.(py|sh|sql):\d+")


def _git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


# ── shared real-repo fixtures ───────────────────────────────────────────────

@pytest.fixture(scope="module")
def clone(tmp_path_factory) -> pathlib.Path:
    """A clean clone of this checkout's HEAD (works from a shallow CI checkout)."""
    dest = tmp_path_factory.mktemp("clone") / "repo"
    head = _git(REPO, "rev-parse", "HEAD")
    subprocess.run(["git", "clone", "--quiet", "--no-checkout", str(REPO), str(dest)],
                   check=True, capture_output=True)
    _git(dest, "checkout", "--quiet", "--detach", head)
    return dest


@pytest.fixture(scope="module")
def clone_inventory(clone):
    return inv.repo_inventory(clone)


@pytest.fixture(scope="module")
def fixture_runs(clone, tmp_path_factory):
    """Two exporter runs on the same commit and the same snapshot."""
    out = tmp_path_factory.mktemp("runs")
    paths = []
    for i in (1, 2):
        p = out / f"export{i}.json"
        assert ax.main(["--root", str(clone), "--snapshot", str(FIXTURE),
                        "--output", str(p), "--summary", str(out / f"summary{i}.md")]) == 0
        paths.append(p)
    return paths


@pytest.fixture(scope="module")
def fixture_export(fixture_runs):
    return json.loads(fixture_runs[0].read_text())


# ── shape and counts ────────────────────────────────────────────────────────

def test_export_has_every_key_and_declared_counts_match_the_inventory(fixture_export, clone_inventory):
    e = fixture_export
    assert e["schema"] == "architecture-export/1"
    assert set(e) == {"schema", "sources", "jobs", "services", "schedulers", "tables", "counts", "drift"}
    assert set(e["counts"]) == {"declared", "live"}
    assert set(e["drift"]) == set(ax.DRIFT_KEYS)
    c = clone_inventory["counts"]
    assert e["counts"]["declared"] == {k: c[k] for k in ("jobs", "services", "schedulers", "tables", "routes")}
    assert sum(j["declared"] for j in e["jobs"]) == c["jobs"]
    assert sum(s["declared"] for s in e["schedulers"]) == c["schedulers"]
    assert sum(s["declared"] for s in e["services"]) == c["services"]


def test_the_exporter_parses_nothing_itself():
    """Facts come from doc_inventory: no regex and no direct read of the
    deploy scripts, the schema or the API tree."""
    tree = ast.parse(MODULE.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported |= {f"{node.module}.{a.name}" for a in node.names}
    assert "re" not in imported and not any(m.startswith("re.") for m in imported), imported
    assert "scripts.maintenance.doc_inventory" in imported
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute)):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            assert name not in {"compile", "findall", "finditer", "search", "match", "fullmatch", "sub"}, \
                f"line {node.lineno} calls {name}"
            assert name not in {"open", "read_text", "read_bytes"} or "snapshot" in ast.unparse(node), \
                f"line {node.lineno} reads a file itself: {ast.unparse(node)}"
    for s in ("deploy.sh", "schema.sql"):
        lits = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        # Only the provenance tuples may name them (as git object paths).
        assert all(v in ax.SOURCE_BLOBS for v in lits if v.endswith(s)), lits


# ── services ───────────────────────────────────────────────────────────────

@pytest.fixture()
def mini(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "gcp").mkdir()
    (tmp_path / "gcp/deploy.sh").write_text(DEPLOY_SNIPPET)
    (tmp_path / "gcp/schema.sql").write_text(SCHEMA_SNIPPET)
    (tmp_path / "platform/api/routers").mkdir(parents=True)
    (tmp_path / "platform/api/main.py").write_text("")
    (tmp_path / "scripts/discord").mkdir(parents=True)
    (tmp_path / "scripts/discord/register_commands.py").write_text("")
    return tmp_path


def _live(jobs=(), services=(), schedulers=None):
    ok = {"command": "python", "args": "", "last_execution": {"result": "ok", "time": "2026-11-10T00:00:00Z"}}
    return {"read_at": "2026-11-10T00:00:00Z", "project": "p", "region": "us-east1",
            "jobs": {j: dict(ok) for j in jobs},
            "services": {s: {"auth_mode": "", "iap": "false", "invokers": [], "min_instances": "0",
                             "max_instances": "1", "created": "2026-01-01T00:00:00Z"} for s in services},
            "schedulers": schedulers or {}}


def test_declared_and_live_services_are_both_kept_and_drift_names_each_once(mini):
    _write(mini, "platform/deploy.sh", 'SERVICE="svc-a"\ngcloud run deploy "${SERVICE}" --image x\n'
                                       "gcloud run deploy svc-b \\\n  --image x\n")
    repo = inv.repo_inventory(mini)
    assert [s["name"] for s in repo["services"]] == ["svc-a", "svc-b"]
    e = ax.build_export(repo, _live(jobs=("alpha", "beta", "gamma"), services=("svc-b", "svc-x")), STUB_SOURCES)
    s = {x["name"]: x for x in e["services"]}
    assert s["svc-a"]["declared"] is True and s["svc-a"]["live"] is None
    assert s["svc-x"]["declared"] is False and s["svc-x"]["live"]["max_instances"] == "1"
    assert s["svc-b"]["declared"] is True and s["svc-b"]["live"] is not None
    assert e["drift"]["declared_not_live"] == ["svc-a"]
    assert e["drift"]["live_not_declared"] == ["svc-x"]


# ── table families and scheduler targets ────────────────────────────────────

def test_an_unresolved_family_is_possible_not_asserted(mini):
    """Same mini repo as test_an_unresolved_template_is_marked_instead_of_asserting_every_relation,
    with the relations declared so the inventory scans their dynamic forms."""
    names = ["demo_1m", "demo_5m", "strat_features_1m", "strat_features_5m"]
    (mini / "gcp/schema.sql").write_text(SCHEMA_SNIPPET + "".join(f"CREATE TABLE {n} (id INT);\n" for n in names))
    _write(mini, "gcp/research/alpha.py", "from gcp.helpers import main\n\ndef run():\n    main(None)\n")
    _write(mini, "gcp/helpers.py",
           'TFS = ("1m", "5m")\n'
           "\n"
           "def read_all(conn):\n"
           "    for tf in TFS:\n"
           '        conn.execute(f"SELECT * FROM demo_{tf}")\n'
           "\n"
           "def read_one(conn, tf):\n"
           '    conn.execute(f"SELECT * FROM strat_features_{tf}")\n'
           "\n"
           "def main(conn):\n"
           "    read_all(conn)\n"
           "    read_one(conn, _from_env())\n")
    e = ax.build_export(inv.repo_inventory(mini), None, STUB_SOURCES)
    alpha = next(j for j in e["jobs"] if j["name"] == "alpha")
    assert alpha["reads"] == ["demo_1m", "demo_5m"], "TFS fixes the placeholder, so these are asserted"
    assert alpha["possible_reads"] == {"strat_features_1m": "strat_features_{tf}",
                                       "strat_features_5m": "strat_features_{tf}"}
    assert not set(alpha["possible_reads"]) & set(alpha["reads"])
    t = {x["name"]: x for x in e["tables"]}
    assert t["demo_1m"]["readers"] == ["alpha"] and t["demo_1m"]["possible_readers"] == []
    assert t["strat_features_1m"]["readers"] == [] and t["strat_features_1m"]["possible_readers"] == ["alpha"]


def test_scheduler_targets_keep_their_kind(fixture_export, clone):
    s = {x["name"]: x for x in fixture_export["schedulers"]}
    for name in ("discord-warm-open", "discord-warm-close"):
        assert s[name]["target"]["kind"] == "service" and s[name]["target"]["name"] == "discord-interactions", s[name]
    r = s["reconcile-failure-notifier-hourly"]["target"]
    assert r["kind"] == "service" and r["name"] == "failure-notifier", r
    for x in fixture_export["schedulers"]:
        if x["target"] is not None:
            assert x["target"]["kind"] in {"job", "service", "uri"}
            assert set(x["target"]) == {"kind", "name", "uri"}
    for d in inv.deploy_schedulers(clone):
        if d.get("target_job") or d.get("target_service") or d.get("target_uri"):
            assert s[d["name"]]["target"], f"{d['name']} lost its target"


def test_mini_repo_service_scheduler_target(mini):
    e = ax.build_export(inv.repo_inventory(mini), None, STUB_SOURCES)
    s = {x["name"]: x for x in e["schedulers"]}
    assert s["warm-open"]["target"]["kind"] == "service"
    assert s["warm-open"]["target"]["name"] == "discord-interactions"
    assert s["alpha-daily"]["target"] == {"kind": "job", "name": "alpha", "uri": None}


# ── determinism ─────────────────────────────────────────────────────────────

def test_two_runs_are_byte_identical(fixture_runs):
    a, b = (p.read_bytes() for p in fixture_runs)
    assert a == b
    assert a.decode().endswith("}\n")


def test_no_string_in_the_export_cites_a_file_and_line(fixture_export):
    bad = []

    def walk(v):
        if isinstance(v, str):
            if LINE_CITE.search(v):
                bad.append(v)
        elif isinstance(v, dict):
            for k, x in v.items():
                walk(k)
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(fixture_export)
    assert not bad, bad[:10]


# ── provenance ──────────────────────────────────────────────────────────────

def test_sources_record_head_and_the_source_object_ids(fixture_export, clone):
    src = fixture_export["sources"]
    assert src["commit"] == _git(clone, "rev-parse", "HEAD")
    assert src["files"] == {p: _git(clone, "rev-parse", f"HEAD:{p}")
                            for p in ("gcp/deploy.sh", "gcp/schema.sql", "platform/api", "platform/deploy.sh")}
    assert _git(clone, "cat-file", "-t", src["files"]["platform/api"]) == "tree"
    snap = json.loads(FIXTURE.read_text())
    assert src["live"] == {"read_at": snap["read_at"], "project": snap["project"], "region": snap["region"]}


@pytest.mark.parametrize("rel", ["gcp/deploy.sh", "lib/__init__.py", "scripts/new_untracked.py",
                                 "platform/api/main.py", "platform/deploy.sh"])
def test_a_dirty_tree_is_refused_and_nothing_is_written(clone, tmp_path, rel):
    f = clone / rel
    existed = f.exists()
    before = f.read_bytes() if existed else None
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes((before or b"") + b"\n# local edit\n")
        out = tmp_path / "export.json"
        assert ax.main(["--root", str(clone), "--output", str(out)]) == 2
        assert not out.exists()
    finally:
        if existed:
            f.write_bytes(before)
        else:
            f.unlink()
    assert not _git(clone, "status", "--porcelain", "--", *ax.WATCHED_PATHS)


# ── live counts that were never read ────────────────────────────────────────

def test_unread_live_counts_are_null_and_the_summary_says_not_read(clone, clone_inventory, tmp_path):
    snap = json.loads(FIXTURE.read_text())
    snap.pop("db_tables")
    e = ax.build_export(clone_inventory, snap, ax.provenance(clone))
    live = e["counts"]["live"]
    assert live["tables"] is None and live["routes"] is None
    assert live["jobs"] == len(snap["jobs"]) == 76
    assert live["services"] == len(snap["services"]) and live["schedulers"] == len(snap["schedulers"])
    md = ax.summary_markdown(e)
    assert re.search(r"^\| tables \| \d+ \| not read \|$", md, re.M), md
    assert re.search(r"^\| routes \| \d+ \| not read \|$", md, re.M), md
    assert "not read" not in md.split("| routes |")[1].split("\n", 1)[1], "drift was read"


def test_fixture_live_counts_are_null_for_tables_and_routes_even_with_db_tables(fixture_export):
    assert fixture_export["counts"]["live"]["tables"] is None
    assert fixture_export["counts"]["live"]["routes"] is None


# ── repo-only mode ──────────────────────────────────────────────────────────

def test_repo_only_mode_needs_no_gcloud(clone, tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("git",):
        os.symlink(shutil.which(tool), bindir / tool)
    env = {k: v for k, v in os.environ.items() if k != "PATH"}
    env["PATH"] = str(bindir)
    env["PYTHONPATH"] = str(REPO)
    out = tmp_path / "export.json"
    summary = tmp_path / "summary.md"
    r = subprocess.run([sys.executable, "-m", "scripts.maintenance.architecture_export", "--root", str(clone),
                        "--output", str(out), "--summary", str(summary)],
                       cwd=REPO, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert shutil.which("gcloud", path=env["PATH"]) is None
    e = json.loads(out.read_text())
    assert e["sources"]["live"] is None
    assert all(j["live"] is None for j in e["jobs"])
    assert all(s["live"] is None for s in e["services"] + e["schedulers"])
    assert set(e["counts"]["live"].values()) == {None}
    assert e["drift"] == {k: [] for k in ax.DRIFT_KEYS}
    assert "Repo only" in summary.read_text()


# ── drift ───────────────────────────────────────────────────────────────────

def test_drift_names_exactly_the_synthetic_differences(mini):
    repo = inv.repo_inventory(mini)
    declared_jobs = [j["name"] for j in repo["jobs"]]
    assert declared_jobs == ["alpha", "beta", "gamma"]
    sched = {s["name"]: {"cron": s["cron"], "state": "ENABLED", "time_zone": "America/New_York",
                         "target_job": s.get("target_job", ""), "target_service": s.get("target_service", ""),
                         "target_uri": s.get("target_uri", "")} for s in repo["schedulers"]}
    sched = copy.deepcopy(sched)
    sched["orb-15m"]["state"] = "PAUSED"
    live = _live(jobs=("alpha", "beta", "hand-made"), schedulers=sched)
    e = ax.build_export(repo, live, STUB_SOURCES)
    assert e["drift"] == {"declared_not_live": ["gamma"], "live_not_declared": ["hand-made"],
                          "paused_schedulers": ["orb-15m"]}
    hand = next(j for j in e["jobs"] if j["name"] == "hand-made")
    assert hand["declared"] is False and hand["live"]["exists"] is True
    gamma = next(j for j in e["jobs"] if j["name"] == "gamma")
    assert gamma["declared"] is True and gamma["live"] == {"exists": False, "last_execution": None}
