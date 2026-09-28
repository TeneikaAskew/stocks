"""export_model_registry.py turns the model registry's tables into the JSON the canvas refresh reads.

Every test RUNS the exporter in a throwaway git repository holding a small
registry and experiment ledger shaped like the real ones: the same table
headers per tier and the same ID notations (ranges, lists, decorated IDs).
Nothing is stubbed.

One test per Codex finding on stocks#1205, named in its docstring. Each was
run against the exporter at 71a9bbce first and failed there for the reason
its finding gives.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
EXPORTER = REPO / "scripts/gate/export_model_registry.py"
WORKFLOW = REPO / ".github/workflows/registry-check.yml"
CANVASES = REPO / "docs/product/canvases.yml"
REGISTRY = "docs/product/07-MODEL-REGISTRY.md"
EXPERIMENTS = "docs/EXPERIMENT_REGISTRY.md"
OUT = "docs/product/generated/model-registry.json"

REGISTRY_TEXT = """\
# Model and Algorithm Registry

**Last reviewed:** 2026-09-20 · **Owner:** TBD

Every row names the decision its model produces.

## Deterministic and heuristic systems

| ID | Name | Type | Decision produced | Code | Status | Rec | Doc | Blocking issues |
|---|---|---|---|---|---|---|---|---|
| MODEL-GAMMA-001 | Gamma levels | Deterministic | King and Gate strikes | `lib/gamma.py` | Production | Keep | DOC-01 | [#942](https://github.com/TeneikaAskew/stocks/issues/942) |

## Learned models

| ID | Name | Type | Decision produced | Code / artifact | Status | Rec | Doc | Evidence |
|---|---|---|---|---|---|---|---|---|
| MODEL-MAG-001 | Magnitude | Gradient boosting | Expected move size | `lib/magnitude.py` | Invalidated | Retrain | DOC-02 | [#813](https://github.com/TeneikaAskew/stocks/issues/813) |

## LLM nodes

| ID | Nodes | Count | Code | Numeric authority | Status |
|---|---|---|---|---|---|
| MODEL-LLM-001 | Insight writer | 3 | `lib/agents/insight.py` | none | Experimental |
| MODEL-SUM-001 | summarizers | — | `lib/agents/summarizers.py` | preserve supplied values | Experimental |

## Scheduled surfaces

| Scheduler | Cron (`America/New_York`) | Job | Serves |
|---|---|---|---|
| `gamma-levels-daily` | `30 22 * * 1-5` | `p2-build-gamma-levels` | MODEL-GAMMA-001 |
| `gamma-levels-sunday` | `0 21 * * 0` | `p2-build-gamma-levels` | the same job, weekend refresh |
| `insight-pipeline-daily` | `45 8 * * 1-5` | `insight-pipeline` | **all 4 LLM nodes** — `run_insight_pipeline` |
| `regime-combo-weekly` | `0 5 * * 0` | `regime-combo` | combo mining (E-22) — owned by the ledger, not by a `MODEL-*` row |

## Documentation coverage and freshness

### Findings

| ID | Doc | Claim → actual | Kind | Sev | Models |
|---|---|---|---|---|---|
| DOC-01 | a.md | 3 levels → 4 | stale | P2 | MODEL-GAMMA-001 |
| DOC-02 | b.md | trained → invalidated | wrong | P1 | MODEL-MAG-001 |
| DOC-03 | c.md | weekly → daily | stale | P3 | MODEL-MAG-001 |
| DOC-09 | d.md | open PR → merged | stale | P3 | MODEL-GAMMA-001 |
| DOC-15 | e.md | 7 nodes → 3 | stale | P3 | MODEL-LLM-001 |
| DOC-16 | f.md | cron → queue | stale | P3 | MODEL-LLM-001 |
| DOC-17 | g.md | GPT → Claude | stale | P3 | MODEL-LLM-001 |

### Disposition

| ID | Disposition | Why |
|---|---|---|
| DOC-01…DOC-03 | Fixed | one pass over the three docs |
| DOC-02 | Deferred | waits for the retrain |
| DOC-09 (#1118) | Fixed | the citation names the merged PR |
| DOC-15, DOC-16, DOC-17 | Won't fix | the pages are retired |
"""

EXPERIMENTS_TEXT = """\
# Experiment Registry

Next free ID is **E-36**. An `E-26` in prose is a reference, not an entry.

## E-01 · STRAT-TYPE

Superseded by E-35 in a later session.

## E-02 · STRAT-TYPE variants

# 2026-07-06 SESSION (E-26 … E-31, E-33 + P0.1)
"""


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def write(repo: Path, path: str, text: str) -> None:
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    """The exporter, a registry and an experiment ledger, committed on `main`."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    write(tmp_path, "scripts/gate/export_model_registry.py", EXPORTER.read_text(encoding="utf-8"))
    write(tmp_path, REGISTRY, REGISTRY_TEXT)
    write(tmp_path, EXPERIMENTS, EXPERIMENTS_TEXT)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "registry")
    return tmp_path


def export(repo: Path, *args: str) -> subprocess.CompletedProcess:
    inherited = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run([sys.executable, "scripts/gate/export_model_registry.py", *args], cwd=repo,
                          env=inherited, capture_output=True, text=True)


def exported(repo: Path) -> dict:
    r = export(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads((repo / OUT).read_text(encoding="utf-8"))


def test_provenance_is_the_blob_id_of_each_source(repo):
    """stocks#1205 r4116983563 (export_model_registry.py:92).

    The old exporter recorded `git rev-parse HEAD`: the commit BEFORE the one
    that carries a registry edit and its regenerated JSON together, and not an
    ancestor of main at all after a squash merge. It now records each source's
    git blob id, which every commit holding that content shares. --check
    compares it, so an edit that parses to the same tables still reads stale.
    """
    write(repo, REGISTRY, REGISTRY_TEXT.replace("Every row names", "Each row names"))
    data = exported(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "edit the registry and regenerate its JSON")
    assert data["sources"] == {REGISTRY: _git(repo, "rev-parse", f"HEAD:{REGISTRY}"),
                               EXPERIMENTS: _git(repo, "rev-parse", f"HEAD:{EXPERIMENTS}")}
    assert export(repo, "--check").returncode == 0
    write(repo, REGISTRY, REGISTRY_TEXT + "\nA note that changes no table.\n")
    r = export(repo, "--check")
    assert r.returncode == 1 and "is stale" in r.stdout, r.stdout


def test_grouped_and_decorated_disposition_ids_reach_their_findings(repo):
    """stocks#1205 r4116983572 (export_model_registry.py:122).

    Disposition rows name findings as a range (DOC-01…DOC-03), a list
    (DOC-15, DOC-16, DOC-17) or a decorated ID (DOC-09 (#1118)). The old
    exporter keyed each row by its raw first cell, so those findings had no
    disposition. A finding's own row wins over a group that also names it.
    """
    data = exported(repo)
    assert sorted(f["id"] for f in data["findings"]) == sorted(data["dispositions"])
    disposition = {fid: rec["disposition"] for fid, rec in data["dispositions"].items()}
    assert disposition == {"DOC-01": "Fixed", "DOC-02": "Deferred", "DOC-03": "Fixed", "DOC-09": "Fixed",
                           "DOC-15": "Won't fix", "DOC-16": "Won't fix", "DOC-17": "Won't fix"}


def test_every_model_card_path_resolves_on_every_tier(repo):
    """stocks#1205 r4116983568 (canvases.yml:29).

    The tiers' tables differ: learned models say `Code / artifact` and
    `Evidence`, LLM nodes have no name, type or decision columns. canvases.yml
    maps one set of `models.<id>.<field>` paths, so every model now carries
    every one of those fields, null where its tier has no such column, with
    `code_artifact_paths` aliased to `code_paths`.
    """
    boards = yaml.safe_load(CANVASES.read_text(encoding="utf-8"))["canvases"][0]["boards"]
    paths = [p for b in boards for p in b["repo_fields"].values() if isinstance(p, str)]
    fields = [p.split(".", 2)[2] for p in paths if p.startswith("models.<id>.")]
    assert fields, paths
    models = exported(repo)["models"]
    missing = {mid: [f for f in fields if f not in rec] for mid, rec in models.items()}
    assert not any(missing.values()), missing
    assert models["MODEL-MAG-001"]["code_paths"] == ["lib/magnitude.py"]
    assert models["MODEL-LLM-001"]["name"] is None


def test_ci_checks_the_pr_head_commit(repo):
    """stocks#1205 r4116983574 (spec-gate.yml:28).

    Nothing in CI ran the freshness check, so a registry edit without its
    regenerated JSON merged green. The spec-gate workflow runs
    `--check --rev <head sha>`, which reads the sources and the committed JSON
    from that commit, because CI checks out the base, not the PR.
    """
    exported(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "regenerate")
    fresh = _git(repo, "rev-parse", "HEAD")
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| Production | Keep |", "| Retired | Drop |"))
    _git(repo, "commit", "-qam", "edit the registry, forget the JSON")
    stale = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", fresh)
    r = export(repo, "--check", "--rev", stale)
    assert r.returncode == 1 and "is stale" in r.stdout, r.stdout
    assert export(repo, "--check", "--rev", fresh).returncode == 0

    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    # The exporter the PR ships judges the JSON it ships, so this runs in its own
    # unprivileged pull_request workflow checked out at the head, not in the gate job.
    assert list(workflow.get("on", workflow.get(True))) == ["pull_request"]
    assert list(jobs) == ["registry"]
    checkout = next(s for s in jobs["registry"]["steps"] if s.get("uses", "").startswith("actions/checkout"))
    assert "ref" not in checkout.get("with", {})
    steps = jobs["registry"]["steps"]
    check = next(s for s in steps if 'export_model_registry.py --check --rev "$HEAD_SHA" --base "$BASE_SHA"' in s.get("run", ""))
    # stocks#1205 r4118661311: not `if: hashFiles(...)`, which reads the head
    # checkout and would skip the only check when a PR deletes the exporter.
    # The step itself decides: run it from the head, fail when the base has an
    # exporter the head lacks, and skip only when neither side has one.
    assert "if" not in check
    assert 'git cat-file -e "$HEAD_SHA:$exporter"' in check["run"]
    assert 'git cat-file -e "$BASE_SHA:$exporter"' in check["run"] and "exit 1" in check["run"]


def test_a_stale_main_fails_only_the_pr_that_made_it_stale(repo):
    """Adversarial review of #1205, B1 (spec-gate.yml:45, export_model_registry.py:226).

    The PR head contains main, so one registry edit that reaches main without
    its JSON (a direct-to-main typo fix, which CLAUDE.md allows) turned every
    later PR red, docs-only PRs included. With --base, a stale head fails only
    when the PR itself touches a source or the JSON, or when the base was
    fresh and the head made it stale; otherwise it names main and passes.
    """
    exported(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "regenerate")
    fresh_main = _git(repo, "rev-parse", "HEAD")
    write(repo, REGISTRY, REGISTRY_TEXT.replace("Every row names", "Each row names"))
    _git(repo, "commit", "-qam", "typo fix straight to main, JSON not regenerated")
    stale_main = _git(repo, "rev-parse", "HEAD")

    # An unrelated docs PR cut from the stale main: not this PR's fault.
    _git(repo, "checkout", "-qb", "docs/unrelated")
    write(repo, "docs/README.md", "unrelated\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "docs")
    r = export(repo, "--check", "--rev", "HEAD", "--base", stale_main)
    assert r.returncode == 0 and "main" in r.stdout and "regenerate" in r.stdout, r.stdout
    assert export(repo, "--check", "--rev", "HEAD").returncode == 1

    # A PR from the same stale main that edits the registry owns the staleness.
    _git(repo, "checkout", "-qb", "docs/edits-registry", stale_main)
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| Production | Keep |", "| Retired | Drop |"))
    _git(repo, "commit", "-qam", "edit the registry, forget the JSON")
    r = export(repo, "--check", "--rev", "HEAD", "--base", stale_main)
    assert r.returncode == 1 and "is stale" in r.stdout, r.stdout

    # A PR from a FRESH main that makes it stale fails, and passes once regenerated.
    _git(repo, "checkout", "-qb", "docs/from-fresh", fresh_main)
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| Production | Keep |", "| Retired | Drop |"))
    _git(repo, "commit", "-qam", "edit the registry, forget the JSON")
    r = export(repo, "--check", "--rev", "HEAD", "--base", fresh_main)
    assert r.returncode == 1 and "is stale" in r.stdout, r.stdout
    exported(repo)
    _git(repo, "commit", "-qam", "regenerate")
    assert export(repo, "--check", "--rev", "HEAD", "--base", fresh_main).returncode == 0


def test_experiment_ids_come_from_entry_headings(repo):
    """stocks#1205 r4117591699 (export_model_registry.py:130).

    The old exporter took every E-NN anywhere in the ledger, so "Next free ID
    is E-36" exported a phantom E-36. IDs come from headings only, with a
    heading's range (E-26 … E-31) expanded, as grouped entries are headed.
    """
    assert exported(repo)["experiment_ids"] == [
        "E-01", "E-02", "E-26", "E-27", "E-28", "E-29", "E-30", "E-31", "E-33"]


def test_scheduler_models_expand_llm_group_and_same_job_rows(repo):
    """stocks#1205 r4118289666 (export_model_registry.py:206).

    Scheduler membership came only from literal MODEL-* tokens in Serves, so
    `insight-pipeline-daily` ("all 14 LLM nodes") and `premarket-brief-sunday`
    ("the same job") exported empty `models` and fell off every LLM card. A
    row naming the LLM node group now expands to every id in the LLM nodes
    tier, a row running another row's Job inherits its models, and prose that
    matches neither keeps `models` empty with a `models_note` carrying the
    Serves text.
    """
    by_name = {s["scheduler"]: s for s in exported(repo)["schedulers"]}
    assert by_name["`gamma-levels-daily`"]["models"] == ["MODEL-GAMMA-001"]
    assert by_name["`gamma-levels-sunday`"]["models"] == ["MODEL-GAMMA-001"]
    assert by_name["`insight-pipeline-daily`"]["models"] == ["MODEL-LLM-001", "MODEL-SUM-001"]
    assert by_name["`regime-combo-weekly`"]["models"] == []
    assert "owned by the ledger" in by_name["`regime-combo-weekly`"]["models_note"]
    assert not any("models_note" in s for n, s in by_name.items() if n != "`regime-combo-weekly`")


def test_a_missing_source_fails_generation_and_the_check(repo):
    """stocks#1205 r4118420401 (export_model_registry.py:252).

    The ledger was optional: with docs/EXPERIMENT_REGISTRY.md deleted the
    exporter exited 0, wrote a null blob for it under `sources`, left out
    `experiment_ids`, and once that JSON was committed --check passed. Both
    canonical sources must exist at the rev being read; a missing one fails
    generation and --check alike, naming the path, and the JSON on disk is
    left as it was rather than rewritten with a null source blob.
    """
    before = json.dumps(exported(repo), sort_keys=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "regenerate")
    fresh = _git(repo, "rev-parse", "HEAD")

    _git(repo, "rm", "-q", EXPERIMENTS)
    r = export(repo)
    assert r.returncode != 0 and EXPERIMENTS in r.stdout + r.stderr, r.stdout + r.stderr
    assert json.dumps(json.loads((repo / OUT).read_text(encoding="utf-8")), sort_keys=True) == before
    r = export(repo, "--check")
    assert r.returncode != 0 and EXPERIMENTS in r.stdout + r.stderr, r.stdout + r.stderr
    _git(repo, "commit", "-qm", "delete the ledger, keep the JSON")
    r = export(repo, "--check", "--rev", "HEAD")
    assert r.returncode != 0 and EXPERIMENTS in r.stdout + r.stderr, r.stdout + r.stderr
    assert export(repo, "--check", "--rev", fresh).returncode == 0

    _git(repo, "checkout", "-q", fresh)
    _git(repo, "rm", "-q", REGISTRY)
    r = export(repo)
    assert r.returncode != 0 and REGISTRY in r.stdout + r.stderr, r.stdout + r.stderr


def test_an_exporter_change_counts_as_touching_the_registry(repo):
    """stocks#1205 r4118475506 (export_model_registry.py:274).

    With a stale base, a PR that changed only the exporter reported no touched
    registry path, so the stale-base waiver let a behaviour change merge with
    the old JSON. The exporter is one of the paths the waiver looks at.
    """
    exported(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "regenerate")
    write(repo, REGISTRY, REGISTRY_TEXT + "\nA prose edit, JSON not regenerated.\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "stale main")
    stale_main = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "chore/exporter", stale_main)
    exporter = repo / "scripts/gate/export_model_registry.py"
    exporter.write_text(exporter.read_text(encoding="utf-8") + "\n# a behaviour change\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "change the exporter only")
    r = export(repo, "--check", "--rev", "HEAD", "--base", stale_main)
    assert r.returncode == 1 and "is stale" in r.stdout, r.stdout
